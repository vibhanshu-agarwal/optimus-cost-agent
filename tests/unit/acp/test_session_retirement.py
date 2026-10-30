"""Serving custody and rollback against real store/adapter/transport owners."""

from __future__ import annotations

import asyncio
import gc
import threading
import weakref
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from optimus.acp.session_retention import RetirementReason, RetirementStatus, SessionCapacityError, SessionRetentionPolicy
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.agent.models import AgentRunResult, AgentRunStatus
from optimus.mcp.client_config import ClientMcpConfigNormalizer
from optimus.mcp.client_disposition import ClientMcpDisposition, ClientMcpRuntime, ClientMcpSessionState
from optimus.mcp.client_sdk import ClientMcpSdkAdapter
from optimus.mcp.client_supervisor import MCPAsyncSupervisor
from optimus.mcp.client_trust import ClientMcpDurableStore, ClientMcpLeaseAuthority
from tests.support.contract_doubles import checked_agent_runner
from tests.support.idle_mcp import context_attachment


class CompletedRunner:
    def run(self, request, **kwargs):
        return AgentRunResult(run_id=request.run_id, session_id=request.session_id,
                              execution_mode=request.execution_mode, status=AgentRunStatus.COMPLETED,
                              final_state='COMPLETED', output_text='done', total_cost_usd=Decimal('0'))


def make_adapter(tmp_path, **kwargs):
    store, outbound = InMemoryAcpSpecSessionStore(), RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(runner=checked_agent_runner(CompletedRunner()), workspace_root=tmp_path,
                               sessions=store, outbound=outbound, **kwargs)
    return adapter, store, outbound


def new_request(tmp_path, servers=()):
    return {'jsonrpc': '2.0', 'id': 'new', 'method': 'session/new',
            'params': {'cwd': str(tmp_path), 'mcpServers': list(servers)}}


@pytest.fixture
def runtime(tmp_path):
    class ReadOnlyKeyring:
        def get_password(self, *_args):
            return None

        def set_password(self, *_args):
            raise AssertionError('no durable writes')

    supervisor = MCPAsyncSupervisor()
    supervisor.start()
    sdk = ClientMcpSdkAdapter(supervisor=supervisor, session_factory=lambda _: None,
                              http_client_factory=lambda: None, stdio_transport_factory=lambda _: None,
                              process_control=None)
    disposition = ClientMcpDisposition(normalizer=ClientMcpConfigNormalizer(),
        lease_authority=ClientMcpLeaseAuthority(store=ClientMcpDurableStore(
            keyring_backend=ReadOnlyKeyring(), hmac_key=b'r' * 32)),
        hmac_key=b'r' * 32, controlled_path=str(tmp_path), workspace_digest='d' * 64)
    result = ClientMcpRuntime(disposition=disposition, sdk_adapter=sdk, supervisor=supervisor)
    yield result
    result.close()


async def test_cap_refusal_allocates_no_session_or_permission(tmp_path, monkeypatch):
    adapter, store, outbound = make_adapter(tmp_path)
    for _ in range(64):
        store.create(cwd=tmp_path)
    allocations = []
    original = adapter._new_conversation

    def conversation():
        allocations.append('conversation')
        return original()

    monkeypatch.setattr(adapter, '_new_conversation', conversation)
    response = await adapter.handle_client_request(new_request(tmp_path, [
        {'type': 'http', 'name': 'tools', 'url': 'https://mcp.example.com/a', 'headers': []}]))
    assert response.response['error'] == {'code': -32800, 'message': 'Server busy',
                                           'data': {'reason': 'SESSION_CAPACITY'}}
    assert allocations == [] and outbound.requests == [] and len(store._sessions) == 64
    await adapter.aclose()


async def test_session_seeder_exception_rolls_back_before_return(tmp_path):
    failure = ValueError('controlled seeder failure')

    def seed(session):
        raise failure

    adapter, store, _ = make_adapter(tmp_path, context_attachment=context_attachment(), session_seeder=seed)
    with pytest.raises(ValueError) as caught:
        await adapter.handle_client_request(new_request(tmp_path))
    assert caught.value is failure
    assert store._sessions == {}
    await adapter.aclose()


@pytest.mark.parametrize('failed_close', [False, True], ids=['clean', 'failed'])
async def test_disposition_never_returned_state_has_attributable_clean_or_failed_close(tmp_path, runtime, monkeypatch, failed_close):
    adapter, store, _ = make_adapter(tmp_path, client_mcp_runtime=runtime)
    states, closed = [], []
    original = runtime.disposition._own_candidates

    def candidate_failure(state):
        original(state)
        entry = adapter.retention._entries[state.session_id]
        assert any(owned is state for owned in entry.setup_states)
        states.append(state)

        def close():
            closed.append(state.session_id)
            if failed_close:
                raise OSError('controlled cleanup failure')

        state.register_close_hook(close)
        raise ValueError('controlled candidate-registration failure')

    monkeypatch.setattr(runtime.disposition, '_own_candidates', candidate_failure)
    response = await adapter.handle_client_request(new_request(tmp_path, [
        {'type': 'http', 'name': 'tools', 'url': 'https://mcp.example.com/a', 'headers': []}]))
    assert response.response['error']['code'] == -32600
    assert len(states) == len(closed) == 1
    assert states[0]._closed
    assert adapter.retention.retained_count == (1 if failed_close else 0)
    assert len(store._sessions) == (1 if failed_close else 0)
    if failed_close:
        first, = await adapter.retention.drain()
        assert first.status is RetirementStatus.QUARANTINED
        with pytest.raises(RuntimeError, match='session cleanup incomplete'):
            await adapter.aclose()
        assert await adapter.retention.drain() == (first,)
    else:
        await adapter.aclose()
    assert len(closed) == 1


@pytest.mark.parametrize('failure_point', ['runtime', 'configuration', 'resolver', 'resolver-cancel', 'seeder', 'conversation'])
async def test_every_session_new_failure_retires_both_distinct_states(tmp_path, runtime, monkeypatch, failure_point):
    failure = asyncio.CancelledError('controlled cancel') if failure_point == 'resolver-cancel' else ValueError('controlled failure')

    class AllowOutbound(RecordingOutboundChannel):
        async def request(self, method, params):
            return {'outcome': {'outcome': 'selected', 'optionId': 'allow_once'}}

    def seed(session):
        if failure_point == 'seeder':
            raise failure
        return None

    adapter, store, _ = make_adapter(tmp_path, client_mcp_runtime=None if failure_point == 'runtime' else runtime,
                                     context_attachment=context_attachment(), session_seeder=seed)
    adapter._outbound = AllowOutbound()
    closed = []
    original_close = ClientMcpSessionState.close

    def close(state):
        closed.append(state)
        return original_close(state)

    monkeypatch.setattr(ClientMcpSessionState, 'close', close)
    if failure_point.startswith('resolver'):
        original_resolver = runtime.disposition.attach_runtime_resolver

        def attach(state, **kwargs):
            original_resolver(state, **kwargs)
            raise failure

        monkeypatch.setattr(runtime.disposition, 'attach_runtime_resolver', attach)
    if failure_point == 'conversation':
        def conversation():
            raise failure
        monkeypatch.setattr(adapter, '_new_conversation', conversation)
    servers = [{'type': 'http', 'name': 'tools', 'url': 'https://mcp.example.com/a', 'headers': []}]
    if failure_point == 'configuration':
        servers.append({**servers[0], 'url': 'https://mcp.example.com/b'})
    if failure_point in ('resolver-cancel', 'seeder', 'conversation'):
        with pytest.raises(type(failure)) as caught:
            await adapter.handle_client_request(new_request(tmp_path, servers))
        assert caught.value is failure
    else:
        response = await adapter.handle_client_request(new_request(tmp_path, servers))
        assert response.response['error']['code'] == -32600
    assert store._sessions == {} and adapter.retention.retained_count == 0
    assert len(closed) == (2 if failure_point in ('configuration', 'resolver', 'resolver-cancel') else 1)
    assert len({id(state) for state in closed}) == len(closed)
    assert all(state.prepare_owned_close().result.result() == () for state in closed)
    await adapter.aclose()


async def test_other_session_failure_does_not_poison_clean_rollback(tmp_path, runtime, monkeypatch):
    adapter, store, _ = make_adapter(tmp_path, client_mcp_runtime=runtime)
    broken = store.create(cwd=tmp_path)
    broken.client_mcp_state = ClientMcpSessionState(broken.session_id)

    def fail():
        raise OSError('controlled broken session')

    broken.client_mcp_state.register_close_hook(fail)
    adapter.retention.request_retire(broken.session_id, reason=RetirementReason.EXPLICIT_REMOVE)
    first = await adapter.retention.wait_retired(broken.session_id)
    assert first.status is RetirementStatus.QUARANTINED
    servers = [{'type': 'http', 'name': 'tools', 'url': 'https://mcp.example.com/a', 'headers': []}]
    response = await adapter.handle_client_request(new_request(tmp_path, [servers[0], {**servers[0], 'url': 'https://mcp.example.com/b'}]))
    assert response.response['error']['code'] == -32600
    assert list(store._sessions) == [broken.session_id] and adapter.retention.retained_count == 1
    with pytest.raises(RuntimeError, match='session cleanup incomplete'):
        await adapter.aclose()


async def test_repeated_empty_close_cannot_complete_running_close(tmp_path, runtime):
    adapter, store, _ = make_adapter(tmp_path, client_mcp_runtime=runtime, session_retention_policy=SessionRetentionPolicy(1))
    session = store.create(cwd=tmp_path)
    state = session.client_mcp_state = ClientMcpSessionState(session.session_id)
    entered, release = threading.Event(), threading.Event()
    calls = []

    def close():
        calls.append('first')
        entered.set()
        assert release.wait(3)

    state.register_close_hook(close)
    adapter.retention.request_retire(session.session_id, reason=RetirementReason.EXPLICIT_REMOVE)
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        operation = state.prepare_owned_close()
        state.close()
        assert state.prepare_owned_close() is operation and not operation.result.done()
        assert adapter.retention.retained_count == 1 and store.get(session.session_id) is session
        assert adapter.retention.request_retire(session.session_id, reason=RetirementReason.SHUTDOWN) is RetirementStatus.RETIRING
    finally:
        release.set()
        result = await adapter.retention.wait_retired(session.session_id)
    assert result.status is RetirementStatus.RELEASED and calls == ['first']
    await adapter.aclose()


async def test_shutdown_joins_existing_retirements_and_preserves_failures(tmp_path, runtime):
    adapter, store, _ = make_adapter(tmp_path, client_mcp_runtime=runtime)
    broken, live = store.create(cwd=tmp_path), store.create(cwd=tmp_path)
    calls = []
    broken.client_mcp_state = ClientMcpSessionState(broken.session_id)
    live.client_mcp_state = ClientMcpSessionState(live.session_id)

    def fail():
        calls.append('broken')
        raise RuntimeError('controlled first failure')

    broken.client_mcp_state.register_close_hook(fail)
    live.client_mcp_state.register_close_hook(lambda: calls.append('live'))
    adapter.retention.request_retire(broken.session_id, reason=RetirementReason.EXPLICIT_REMOVE)
    first = await adapter.retention.wait_retired(broken.session_id)
    assert first.status is RetirementStatus.QUARANTINED
    with pytest.raises(RuntimeError, match='session cleanup incomplete') as caught:
        await adapter.aclose()
    with pytest.raises(RuntimeError) as repeated:
        await adapter.aclose()
    assert repeated.value is caught.value
    assert store.get(live.session_id) is None and store.get(broken.session_id) is broken
    assert calls == ['broken', 'live'] and adapter.retention.retained_count == 1


@pytest.mark.parametrize('real_lane', [False, True], ids=['injected-no-lane', 'real-disposition'])
@pytest.mark.parametrize('fails', [False, True], ids=['clean', 'failed-close'])
async def test_owned_close_joins_off_loop_for_real_or_injected_runtime(tmp_path, runtime, monkeypatch, real_lane, fails):
    loop_thread = threading.get_ident()
    entered, release = threading.Event(), threading.Event()
    calls, lanes = [], []
    original = runtime.disposition.run_blocking
    async def observe(operation):
        lanes.append(operation)
        return await original(operation)
    monkeypatch.setattr(runtime.disposition, 'run_blocking', observe)
    provided = runtime if real_lane else ClientMcpRuntime(disposition=object(),
        sdk_adapter=runtime.sdk_adapter, supervisor=runtime.supervisor)
    adapter, store, _ = make_adapter(tmp_path, client_mcp_runtime=provided)
    session = store.create(cwd=tmp_path)
    state = session.client_mcp_state = ClientMcpSessionState(session.session_id)
    def physical_close():
        calls.append(threading.get_ident())
        entered.set()
        assert release.wait(2)
        if fails:
            raise OSError('controlled owned close failure')
    state.register_close_hook(physical_close)
    adapter.retention.request_retire(session.session_id, reason=RetirementReason.EXPLICIT_REMOVE)
    observer = asyncio.create_task(adapter.retention.wait_retired(session.session_id))
    observed_shutdown_failure = None
    try:
        did_enter = await asyncio.to_thread(entered.wait, 1)
        if not did_enter:
            await observer  # Preserve the actual owner error rather than a barrier failure.
        assert did_enter and len(calls) == 1 and calls[0] != loop_thread
        assert store.get(session.session_id) is session and not observer.done()
        assert len(lanes) == int(real_lane)
        observer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await observer
        assert not state.prepare_owned_close().result.done()
        assert store.get(session.session_id) is session
        release.set()
        result = await adapter.retention.wait_retired(session.session_id)
        assert len(calls) == 1
        if fails:
            assert result.status is RetirementStatus.QUARANTINED
            assert state.prepare_owned_close().result.result() == ('SESSION_CLOSE_FAILED',)
            assert store.get(session.session_id) is session and adapter.retention.retained_count == 1
            with pytest.raises(RuntimeError, match='session cleanup incomplete') as caught:
                await adapter.aclose()
            observed_shutdown_failure = caught.value
        else:
            assert result is None or result.status is RetirementStatus.RELEASED
            assert state.prepare_owned_close().result.result() == ()
            assert store.get(session.session_id) is None
    finally:
        release.set()
        await asyncio.gather(observer, return_exceptions=True)
        if observed_shutdown_failure is None:
            await adapter.aclose()
        else:
            with pytest.raises(RuntimeError) as repeated:
                await adapter.aclose()
            assert repeated.value is observed_shutdown_failure
@pytest.mark.parametrize('operation', ['config', 'renewal'])
async def test_config_and_renewal_are_owned(tmp_path, runtime, operation):
    adapter, store, outbound = make_adapter(tmp_path, client_mcp_runtime=runtime)
    session = store.create(cwd=tmp_path, conversation=adapter._new_conversation())
    entered, release = asyncio.Event(), asyncio.Event()
    if operation == 'config':
        class HeldOutbound(RecordingOutboundChannel):
            async def notify(self, method, params, **kwargs):
                entered.set()
                await release.wait()
                return await super().notify(method, params, **kwargs)
        adapter._outbound = HeldOutbound()
        request = {'jsonrpc': '2.0', 'id': 1, 'method': 'session/set_mode',
                   'params': {'sessionId': session.session_id, 'modeId': 'chat'}}
    else:
        async def allow(_params):
            return 'allow'
        state = session.client_mcp_state = await runtime.disposition.disposition_for_new_session(
            session.session_id, tmp_path,
            [{'type': 'http', 'name': 'tools', 'url': 'https://mcp.example.com/a', 'headers': []}], allow)
        state.register_close_hook(lambda: None, peer=True)
        for hook in state.prepare_suspend():
            hook()
        assert state.complete_suspend(())
        request = {'jsonrpc': '2.0', 'id': 1, 'method': 'session/prompt',
                   'params': {'sessionId': session.session_id, 'prompt': [{'type': 'text', 'text': 'hello'}]}}
    task = asyncio.create_task(adapter.handle_client_request(request))
    if operation == 'config':
        await asyncio.wait_for(entered.wait(), 1)
    else:
        pending = await asyncio.wait_for(outbound.wait_for_request('session/request_permission'), 1)
    assert adapter.retention.request_retire(session.session_id, reason=RetirementReason.EXPLICIT_REMOVE) is RetirementStatus.DEFERRED
    assert store.get(session.session_id) is session
    with pytest.raises(RuntimeError, match='requires await aclose'):
        store.remove(session.session_id)
    if operation == 'config':
        release.set()
    else:
        outbound.respond(pending['id'], {'outcome': {'outcome': 'selected', 'optionId': 'reject_once'}})
    await task
    result = await adapter.retention.wait_retired(session.session_id)
    assert result is None or result.status is RetirementStatus.RELEASED
    assert adapter.retention.retained_count == 0
    await adapter.aclose()


async def test_queued_and_pre_registration_use_blocks_retirement(tmp_path, monkeypatch):
    from tests.unit.acp.test_settlement_truth import ServerTurn

    h = ServerTurn(tmp_path, monkeypatch)
    await h.start()
    entered, release = asyncio.Event(), asyncio.Event()
    tasks = {}
    original = AcpDuplexAdapter.handle_client_request

    async def handle(adapter, message, **kwargs):
        tasks[message.get('id')] = asyncio.current_task()
        if message.get('id') == 'prompt':
            assert h.session_id not in adapter._active_turns
            entered.set()
            await release.wait()
        return await original(adapter, message, **kwargs)

    monkeypatch.setattr(AcpDuplexAdapter, 'handle_client_request', handle)
    try:
        await h.prompt()
        await asyncio.wait_for(entered.wait(), 1)
        await h.reader.send({'jsonrpc': '2.0', 'id': 'followup', 'method': 'session/prompt',
                             'params': {'sessionId': h.session_id, 'prompt': [{'type': 'text', 'text': 'queued'}]}})
        await h.reader.send({'jsonrpc': '2.0', 'id': 'setter', 'method': 'session/set_mode',
                             'params': {'sessionId': h.session_id, 'modeId': 'chat'}})
        await h.transport.until(lambda message: message.get('id') == 'setter')
        await tasks['setter']
        entry = h.adapter.retention._entries[h.session_id]
        assert entry.uses == 2
        assert h.adapter.retention.request_retire(h.session_id, reason=RetirementReason.EXPLICIT_REMOVE) is RetirementStatus.DEFERRED
        h.transport.hold = lambda message: message.get('id') == 'followup'
        h.transport.release.clear()
        await h.reader.send({'method': 'session/cancel', 'params': {'sessionId': h.session_id}})
        await asyncio.wait_for(h.transport.entered.wait(), 1)
        tasks['prompt'].cancel()
        await asyncio.gather(tasks['prompt'], return_exceptions=True)
        assert entry.uses == 1
        assert h.adapter._sessions.get(h.session_id) is entry.session
        h.transport.release.set()
        response = await h.transport.until(lambda message: message.get('id') == 'followup')
        assert response['result'] == {'stopReason': 'cancelled'}
        result = await h.adapter.retention.wait_retired(h.session_id)
        assert result is None or result.status is RetirementStatus.RELEASED
        assert h.adapter.retention.retained_count == 0
    finally:
        release.set()
        h.transport.release.set()
        await h.close()


async def test_observe_false_writer_future_pins_session_until_real_completion(tmp_path, monkeypatch):
    from optimus.acp.admission import AdmissionLimits
    from tests.unit.acp.test_settlement_truth import ServerTurn

    h = ServerTurn(tmp_path, monkeypatch)
    h.server._admission_limits = replace(AdmissionLimits(), pending_items=1, active_requests=1)
    await h.start()
    entered, release = asyncio.Event(), asyncio.Event()
    original = AcpDuplexAdapter.handle_client_request

    async def handle(adapter, message, **kwargs):
        if message.get('id') == 'blocked':
            entered.set()
            await release.wait()
        return await original(adapter, message, **kwargs)

    monkeypatch.setattr(AcpDuplexAdapter, 'handle_client_request', handle)
    h.transport.hold = lambda message: message.get('id') == 'busy'
    h.transport.release.clear()
    try:
        for request_id in ('blocked', 'queued', 'busy'):
            await h.reader.send({'jsonrpc': '2.0', 'id': request_id, 'method': 'session/set_mode',
                                 'params': {'sessionId': h.session_id, 'modeId': 'chat'}})
            if request_id == 'blocked':
                await asyncio.wait_for(entered.wait(), 1)
        await asyncio.wait_for(h.transport.entered.wait(), 1)
        assert h.adapter.retention.request_retire(h.session_id, reason=RetirementReason.EXPLICIT_REMOVE) is RetirementStatus.DEFERRED
        h.reader.close()

        async def drained():
            while h.server._inbound_admission.count:
                await asyncio.sleep(0)

        await asyncio.wait_for(drained(), 1)
        assert h.adapter._sessions.get(h.session_id) is not None
        entry = h.adapter.retention._entries[h.session_id]
        assert entry.uses == 1
        assert h.adapter._sessions.get(h.session_id) is entry.session
        assert not h.task.done()
        h.transport.release.set()
        response = await h.transport.until(lambda message: message.get('id') == 'busy')
        assert response['error']['data'] == {'reason': 'QUEUE_FULL'}
        await asyncio.wait_for(h.task, 2)
        assert h.adapter.retention.retained_count == 0
    finally:
        release.set()
        h.transport.release.set()
        await h.close()


async def test_cancelled_prompt_pins_until_late_worker_receipt(tmp_path, monkeypatch):
    from optimus.acp.spec import request_worker_custody
    from optimus.usage.turn_settlement import StageReceipt
    from tests.unit.acp.test_settlement_truth import ServerTurn

    entered, release = threading.Event(), threading.Event()
    data = {}

    def physical():
        entered.set()
        assert release.wait(4)
        data['record'](StageReceipt(session_id=data['session_id'], turn_id=data['run_id'], stage='planning',
                                    attempt_id='late-owned-attempt', gateway_request_id=None, outcome='completed',
                                    reported_cost_usd=Decimal('0.25'), recorded_at=datetime.now(timezone.utc)))

    worker = asyncio.create_task(asyncio.to_thread(physical))
    assert await asyncio.to_thread(entered.wait, 1)

    class Script(CompletedRunner):
        def run(self, request, *, stage_receipts=None, **kwargs):
            data.update(record=stage_receipts, session_id=request.session_id, run_id=request.run_id)
            request_worker_custody.get().add(worker)
            return super().run(request, **kwargs)

    h = ServerTurn(tmp_path, monkeypatch, Script())
    await h.start()
    tasks = {}
    original = AcpDuplexAdapter.handle_client_request

    async def handle(adapter, message, **kwargs):
        tasks[message.get('id')] = asyncio.current_task()
        return await original(adapter, message, **kwargs)

    monkeypatch.setattr(AcpDuplexAdapter, 'handle_client_request', handle)
    try:
        await h.prompt()
        await h.transport.until(lambda message: message.get('id') == 'prompt')
        await asyncio.wait_for(h.settled.wait(), 1)
        session = h.adapter._sessions.get(h.session_id)
        tasks['prompt'].cancel()
        assert h.adapter.retention.request_retire(h.session_id, reason=RetirementReason.EXPLICIT_REMOVE) is RetirementStatus.DEFERRED
        await asyncio.sleep(0)
        assert not worker.done() and h.adapter._sessions.get(h.session_id) is session
        assert h.adapter.retention.retained_count == 1
        release.set()
        await worker
        await asyncio.gather(tasks['prompt'], return_exceptions=True)
        result = await h.adapter.retention.wait_retired(h.session_id)
        assert result is None or result.status is RetirementStatus.RELEASED
        receipts = session.cost_settlement.receipts(data['run_id'])
        assert len(receipts) == 1 and receipts[0].reported_cost_usd == Decimal('0.25')
        assert h.adapter.retention.retained_count == 0
        assert not h.sink_errors
    finally:
        release.set()
        await worker
        await h.close()


def test_lazy_binding_rejects_adopted_over_cap_store_atomically(tmp_path):
    adapter, store, _ = make_adapter(tmp_path)
    originals = [store.create(cwd=tmp_path) for _ in range(65)]
    assert store._retention is None and adapter._retention is None
    with pytest.raises(SessionCapacityError):
        asyncio.run(adapter.handle_client_request({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}}))
    assert store._retention is None and adapter._retention is None
    assert len(store._sessions) == 65
    assert all(store.get(session.session_id) is session for session in originals)


def test_standalone_sync_adapter_close_preserves_unattached_store(tmp_path):
    adapter, store, _ = make_adapter(tmp_path)
    session = store.create(cwd=tmp_path)
    session.client_mcp_state = ClientMcpSessionState(session.session_id)
    closed = []
    session.client_mcp_state.register_close_hook(lambda: closed.append('closed'))
    adapter.close_all()
    adapter.close_all()
    assert closed == ['closed'] and store.get(session.session_id) is session
    assert store._retention is None and adapter._retention is None


async def test_failed_retirement_keeps_other_session_usable(tmp_path, runtime):
    adapter, store, _ = make_adapter(tmp_path, client_mcp_runtime=runtime)
    broken = store.create(cwd=tmp_path)
    broken.client_mcp_state = ClientMcpSessionState(broken.session_id)
    live = store.create(cwd=tmp_path, conversation=adapter._new_conversation())

    def fail():
        raise OSError('controlled failure')

    broken.client_mcp_state.register_close_hook(fail)
    adapter.retention.request_retire(broken.session_id, reason=RetirementReason.EXPLICIT_REMOVE)
    assert (await adapter.retention.wait_retired(broken.session_id)).status is RetirementStatus.QUARANTINED
    response = await adapter.handle_client_request({'jsonrpc': '2.0', 'id': 1, 'method': 'session/prompt',
        'params': {'sessionId': live.session_id, 'prompt': [{'type': 'text', 'text': 'hello'}]}})
    assert 'result' in response.response
    with pytest.raises(RuntimeError, match='session cleanup incomplete'):
        await adapter.aclose()
    assert store.get(live.session_id) is None and store.get(broken.session_id) is broken


async def test_retirement_detaches_and_releases_real_session(tmp_path, monkeypatch):
    from tests.unit.acp.test_settlement_truth import ServerTurn

    h = ServerTurn(tmp_path, monkeypatch)
    await h.start()
    try:
        await h.prompt()
        await h.transport.until(lambda message: message.get('id') == 'prompt')

        async def done():
            while h.server._inbound_admission.count:
                await asyncio.sleep(0)

        await asyncio.wait_for(done(), 1)
        assert h.adapter._runner.run.call_count == 1
        # The test-owned autospec records callback arguments that retain the session graph.
        h.adapter._runner.reset_mock()
        session = h.adapter._sessions.get(h.session_id)
        assert session.conversation.records
        session_ref, history_ref = weakref.ref(session), weakref.ref(session.conversation)
        h.adapter.retention.request_retire(h.session_id, reason=RetirementReason.EXPLICIT_REMOVE)
        await h.adapter.retention.wait_retired(h.session_id)
        assert h.adapter._sessions.get(h.session_id) is None
        del session
        await asyncio.sleep(0)
        gc.collect()
        assert session_ref() is None and history_ref() is None
    finally:
        await h.close()


async def test_retirement_releases_real_history_and_session_owned_graph(tmp_path, runtime, monkeypatch):
    from optimus.acp.auto_composition import AutoDecision
    from optimus.context.adapter import approval_fact_from_permission
    from optimus.mcp.client_catalog import ClientMcpToolService
    from optimus.usage.turn_settlement import StageReceipt
    from tests.unit.acp.test_settlement_truth import ServerTurn

    run_ids = {}
    class PaidRunner(CompletedRunner):
        def run(self, request, *, stage_receipts=None, **kwargs):
            run_ids[request.session_id] = request.run_id
            stage_receipts(StageReceipt(session_id=request.session_id, turn_id=request.run_id,
                stage='planning', attempt_id=request.run_id, gateway_request_id=None, outcome='completed',
                reported_cost_usd=Decimal('0.25'), recorded_at=datetime.now(timezone.utc)))
            return super().run(request, **kwargs)

    original = AcpDuplexAdapter.__init__
    def configured(adapter, *args, **kwargs):
        kwargs.update(client_mcp_runtime=runtime, context_attachment=context_attachment())
        original(adapter, *args, **kwargs)
    monkeypatch.setattr(AcpDuplexAdapter, '__init__', configured)
    h = ServerTurn(tmp_path, monkeypatch, PaidRunner())
    await h.start()

    async def complete_prompt():
        h.settled.clear()
        await h.prompt()
        await h.transport.until(lambda message: message.get('id') == 'prompt')
        await asyncio.wait_for(h.settled.wait(), 2)
        while h.server._inbound_admission.count:
            await asyncio.sleep(0)
        assert not h.sink_errors

    try:
        retired_id = h.session_id
        await complete_prompt()
        await h.reader.send(dict(new_request(tmp_path), id='live-new'))
        live_response = await h.transport.until(lambda message: message.get('id') == 'live-new')
        h.session_id = live_id = live_response['result']['sessionId']
        await complete_prompt()
        live = h.adapter._sessions.get(live_id)
        live_records = dict(live.conversation.records)
        live_receipts = live.cost_settlement.receipts(run_ids[live_id])
        assert live_records and live_receipts[0].reported_cost_usd == Decimal('0.25')
        assert h.adapter._runner.run.call_count == 2
        # Only the test autospec's recorded callback arguments are released here.
        h.adapter._runner.reset_mock()

        async def retire_nonempty_graph():
            session = h.adapter._sessions.get(retired_id)
            assert session.conversation.records
            receipts = session.cost_settlement.receipts(run_ids[retired_id])
            assert receipts[0].reported_cost_usd == Decimal('0.25')
            session.context_approvals[1] = (approval_fact_from_permission(turn_seq=1,
                artifact_hash='owned-plan', permission_result={'outcome': {'outcome': 'selected', 'optionId': 'approve'}},
                halted=False),)
            session.auto_routes[1] = AutoDecision(classifier_tier='easy', confidence_band='high',
                routed_up_for_confidence=False, failure_kind=None, escalations=(), default_fallback=False,
                tier='easy', role='implementer_easy', model_id='test/planner', answered_by='rules')
            async def allow(_params):
                return 'allow'
            state = await runtime.disposition.disposition_for_new_session(retired_id, tmp_path,
                [{'type': 'http', 'name': 'owned-catalog', 'url': 'https://mcp.example.invalid/catalog'}], allow)
            session.client_mcp_state = state
            service = runtime.disposition.materialize_tool_service(state, identity=state._capabilities[0].safe_identity,
                raw_tools=[{'tools': [{'name': 'echo', 'description': 'Echo owned text', 'inputSchema': {'type': 'object'}}]}],
                workspace_root=tmp_path, service_factory=ClientMcpToolService)
            assert service is not None
            facade = state.tool_service
            catalog = object.__getattribute__(service, '_catalog')
            assert catalog.tools and session.context_approvals and session.auto_routes
            # A real subscriber closes a cycle over its session, as host cost projections do.
            session.cost_settlement.subscribe(lambda _turn, _summary: session.session_id)
            refs = tuple(weakref.ref(value) for value in
                         (session, session.conversation, facade, catalog, h.adapter.retention._entries[retired_id]))
            h.adapter.retention.request_retire(retired_id, reason=RetirementReason.EXPLICIT_REMOVE)
            result = await h.adapter.retention.wait_retired(retired_id)
            assert result is None or result.status is RetirementStatus.RELEASED
            assert h.adapter._sessions.get(retired_id) is None
            assert receipts[0].reported_cost_usd == Decimal('0.25')
            return refs

        refs = await retire_nonempty_graph()
        for _ in range(5):
            await asyncio.sleep(0)
            gc.collect()
        assert all(ref() is None for ref in refs), [type(ref()).__name__ for ref in refs if ref() is not None]
        assert h.adapter._sessions.get(live_id) is live
        assert live.conversation.records == live_records
        assert live.cost_settlement.receipts(run_ids[live_id]) == live_receipts
        await complete_prompt()
        assert len(live.conversation.records) == len(live_records) + 1
        assert h.adapter._runner.run.call_count == 1
        h.adapter._runner.reset_mock()
    finally:
        await h.close()


async def test_retained_population_is_flat_after_8_and_16_retirements(tmp_path, runtime):
    adapter, store, _ = make_adapter(tmp_path, client_mcp_runtime=runtime)
    async def create():
        reply = await adapter.handle_client_request(new_request(tmp_path))
        return reply.response['result']['sessionId']
    try:
        live = {await create(), await create()}
        refs = []
        for cycle in range(1, 17):
            session_id = await create()
            session = store.get(session_id)
            refs.append(weakref.ref(session))
            assert adapter.retention.retained_count == 3
            adapter.retention.request_retire(session_id, reason=RetirementReason.EXPLICIT_REMOVE)
            result = await adapter.retention.wait_retired(session_id)
            assert result is None or result.status is RetirementStatus.RELEASED
            del session
            await asyncio.sleep(0)
            assert set(store._sessions) == set(adapter.retention.session_ids) == live
            assert adapter.retention.retained_count == 2
            assert store._closed_state_ids <= live
            assert set(adapter._idle_mcp) <= live
            assert set(adapter._active_turns) <= live
            assert set(adapter._reopen_reservations) <= live
            assert adapter._reopen_cancelled <= live
            assert not adapter._worker_tasks and not adapter._progress_lanes
            if cycle in (8, 16):
                gc.collect()
                assert all(ref() is None for ref in refs)
        assert all(store.get(session_id) is not None for session_id in live)
    finally:
        await adapter.aclose()


async def test_provisional_session_is_unavailable_until_setup_activates(tmp_path, runtime):
    adapter, store, outbound = make_adapter(tmp_path, client_mcp_runtime=runtime)
    creating = asyncio.create_task(adapter.handle_client_request(new_request(tmp_path, [
        {'type': 'http', 'name': 'tools', 'url': 'https://mcp.example.com/a', 'headers': []}])))
    pending = await asyncio.wait_for(outbound.wait_for_request('session/request_permission'), 1)
    session_id, = adapter.retention.session_ids
    assert store.get(session_id) is not None and not adapter.retention.is_active(session_id)
    response = await adapter.handle_client_request({'jsonrpc': '2.0', 'id': 2, 'method': 'session/prompt',
        'params': {'sessionId': session_id, 'prompt': [{'type': 'text', 'text': 'premature'}]}})
    assert response.response['error'] == {'code': -32600, 'message': 'unknown session'}
    assert adapter._active_turns == {}
    outbound.respond(pending['id'], {'outcome': {'outcome': 'selected', 'optionId': 'allow_once'}})
    response = await creating
    assert response.response['result']['sessionId'] == session_id and adapter.retention.is_active(session_id)
    await adapter.aclose()


async def test_control_failure_retains_all_distinct_state_close_verdicts(tmp_path, runtime):
    adapter, store, _ = make_adapter(tmp_path, client_mcp_runtime=runtime)
    session = store.create(cwd=tmp_path)
    first, second = ClientMcpSessionState(session.session_id), ClientMcpSessionState(session.session_id)
    session.client_mcp_state = second
    adapter.retention.retain_setup_state(session.session_id, first)
    adapter.retention.retain_setup_state(session.session_id, second)
    closed = []

    def ordinary():
        closed.append('ordinary')
        raise OSError('controlled secondary failure')

    def control():
        closed.append('control')
        raise asyncio.CancelledError('controlled close cancellation')

    first.register_close_hook(ordinary)
    second.register_close_hook(control)
    adapter.retention.request_retire(session.session_id, reason=RetirementReason.EXPLICIT_REMOVE)
    with pytest.raises(asyncio.CancelledError):
        await adapter.retention.wait_retired(session.session_id)
    entry = adapter.retention._entries[session.session_id]
    assert entry.result.status is RetirementStatus.QUARANTINED
    assert entry.result.close.failures == ('SESSION_CLOSE_FAILED', 'SESSION_CLOSE_FAILED')
    assert closed == ['control', 'ordinary']
    with pytest.raises(asyncio.CancelledError):
        await adapter.aclose()


def _observe_real_rejections(writer, monkeypatch):
    rejected, errors = [], []
    entered = asyncio.Event()
    original = writer.submit

    def submit(item):
        try:
            return original(item)
        except RuntimeError as exc:
            assert item.reservation is None and not item.source_future.running()
            rejected.append(item)
            errors.append(exc)
            entered.set()
            raise

    monkeypatch.setattr(writer, 'submit', submit)
    return rejected, errors, entered


def _rescue_rejected_test_sources(rejected):
    # Teardown only, after assertions: broken-source REDs otherwise leave their serving task hung.
    from optimus.acp.lifecycle import SendCompletion
    from optimus.acp.settlement import SendOutcome

    for item in rejected:
        if not item.source_future.done():
            item.owner.publish_authoritative(item.send_key, SendOutcome.CONCLUSIVE_FAILURE)
            item.source_future.set_result(SendCompletion(send_key=item.send_key, outcome=SendOutcome.CONCLUSIVE_FAILURE))
        if item.writer_token is not None:
            item.writer_token.release()
        if item.handle is not None:
            item.handle.finalize_once(item.source_future.result())


@pytest.mark.parametrize('writer_state', ['not-started', 'closed'])
async def test_rejected_new_response_resolves_source_and_does_not_strand_shutdown(tmp_path, monkeypatch, writer_state):
    from optimus.acp.outbound_writer import DedicatedOutboundWriter
    from optimus.acp.settlement import SendOutcome
    from tests.unit.acp.test_settlement_truth import ServerTurn

    h = ServerTurn(tmp_path, monkeypatch)
    writer = DedicatedOutboundWriter(h.transport)
    if writer_state == 'closed':
        writer.request_close()
    rejected, errors, entered = _observe_real_rejections(writer, monkeypatch)
    h.task = asyncio.create_task(h.server.serve_ndjson(h.reader, h.transport,
                                dedicated_writer=writer, join_dedicated_writer=False))
    try:
        await h.reader.send(new_request(tmp_path))
        await asyncio.wait_for(entered.wait(), 1)

        async def request_finished():
            while h.server._inbound_admission.count:
                await asyncio.sleep(0)

        await asyncio.wait_for(request_finished(), 1)
        assert errors and str(errors[0]) == ('dedicated outbound writer is closed' if writer_state == 'closed'
                                           else 'dedicated outbound writer not started')
        assert rejected and all(item.source_future.done() for item in rejected)
        assert all(item.source_future.result().outcome is SendOutcome.CONCLUSIVE_FAILURE for item in rejected)
        assert all(item.handle._finalized and item.handle._join_ready_locked() for item in rejected if item.handle)
        session_id, = h.adapter.retention.session_ids
        assert h.adapter.retention._entries[session_id].uses == 0
        h.reader.close()
        await asyncio.wait_for(h.task, 2)
        assert h.adapter.retention.retained_count == 0
        assert h.transport.writes == []
    finally:
        _rescue_rejected_test_sources(rejected)
        h.reader.close()
        await asyncio.wait_for(asyncio.gather(h.task, return_exceptions=True), 2)
        writer.request_close()
        assert writer.observe_closed(1)


async def test_rejected_turn_response_resolves_source_and_preserves_failure(tmp_path, monkeypatch):
    from optimus.acp.outbound_writer import DedicatedOutboundWriter
    from optimus.acp.settlement import SendOutcome
    from tests.unit.acp.test_settlement_truth import ServerTurn

    h = ServerTurn(tmp_path, monkeypatch)
    writer = DedicatedOutboundWriter(h.transport)
    writer.start()
    actual = writer.submit

    def close_before_response(item):
        if item.payload.get('id') == 'prompt':
            writer.request_close()
        return actual(item)

    monkeypatch.setattr(writer, 'submit', close_before_response)
    rejected, errors, entered = _observe_real_rejections(writer, monkeypatch)
    h.task = asyncio.create_task(h.server.serve_ndjson(h.reader, h.transport,
                                dedicated_writer=writer, join_dedicated_writer=False))
    try:
        await h.reader.send(new_request(tmp_path))
        response = await h.transport.until(lambda message: message.get('id') == 'new')
        h.session_id = response['result']['sessionId']
        await h.prompt()
        await asyncio.wait_for(entered.wait(), 1)

        async def request_finished():
            while h.server._inbound_admission.count:
                await asyncio.sleep(0)

        await asyncio.wait_for(request_finished(), 1)
        assert len(errors) == 1 and str(errors[0]) == 'dedicated outbound writer is closed'
        assert len(rejected) == 1 and rejected[0].source_future.done()
        assert rejected[0].source_future.result().outcome is SendOutcome.CONCLUSIVE_FAILURE
        assert rejected[0].owner.rpc_response_delivery.value == 'conclusive_failure'
        assert h.adapter.retention._entries[h.session_id].uses == 0
        h.reader.close()
        await asyncio.wait_for(h.task, 2)
        assert h.adapter.retention.retained_count == 0
    finally:
        _rescue_rejected_test_sources(rejected)
        h.reader.close()
        await asyncio.wait_for(asyncio.gather(h.task, return_exceptions=True), 2)
        writer.request_close()
        assert writer.observe_closed(1)


@pytest.mark.parametrize('writer_state', ['not-started', 'closed'])
@pytest.mark.parametrize('operation', ['config', 'permission'])
async def test_rejected_channel_send_balances_custody_and_preserves_error(tmp_path, monkeypatch, writer_state, operation):
    from optimus.acp.outbound_writer import DedicatedOutboundWriter
    from optimus.acp.server import NdjsonOutboundChannel
    from optimus.acp.settlement import SendOutcome
    from optimus.acp.spec import request_session_custody
    from tests.unit.acp.test_settlement_truth import PhysicalTransport

    transport = PhysicalTransport()
    writer = DedicatedOutboundWriter(transport)
    if writer_state == 'closed':
        writer.request_close()
    rejected, errors, _ = _observe_real_rejections(writer, monkeypatch)
    adapter, store, _ = make_adapter(tmp_path)
    channel = adapter._outbound = NdjsonOutboundChannel(transport, dedicated_writer=writer)
    session = store.create(cwd=tmp_path, conversation=adapter._new_conversation())
    try:
        if operation == 'config':
            with pytest.raises(RuntimeError) as caught:
                await adapter.handle_client_request({'jsonrpc': '2.0', 'id': 1, 'method': 'session/set_mode',
                    'params': {'sessionId': session.session_id, 'modeId': 'chat'}})
        else:
            use = adapter.retention.acquire(session.session_id)
            token = request_session_custody.set([use])
            try:
                with pytest.raises(RuntimeError) as caught:
                    await channel.request('session/request_permission', {'sessionId': session.session_id})
            finally:
                request_session_custody.reset(token)
                use.release()
        assert caught.value is errors[0]
        assert str(caught.value) == ('dedicated outbound writer is closed' if writer_state == 'closed'
                                    else 'dedicated outbound writer not started')
        assert len(rejected) == 1 and rejected[0].source_future.done()
        assert rejected[0].source_future.result().outcome is SendOutcome.CONCLUSIVE_FAILURE
        await asyncio.sleep(0)
        assert adapter.retention._entries[session.session_id].uses == 0
        assert channel._futures == {}
        adapter.retention.request_retire(session.session_id, reason=RetirementReason.EXPLICIT_REMOVE)
        result = await asyncio.wait_for(adapter.retention.wait_retired(session.session_id), 1)
        assert result is None or result.status is RetirementStatus.RELEASED
        await asyncio.wait_for(adapter.aclose(), 1)
        assert transport.writes == []
    finally:
        _rescue_rejected_test_sources(rejected)
        await asyncio.wait_for(adapter.aclose(), 2)
        writer.request_close()
        assert writer.observe_closed(1)


@pytest.mark.parametrize('accepted_phase', ['running', 'queued'])
async def test_accepted_submit_error_and_later_refusal_keep_physical_custody_distinct(tmp_path, monkeypatch, accepted_phase):
    import concurrent.futures

    from optimus.acp.outbound_writer import DedicatedOutboundWriter, EphemeralSendOwner, OutboundQueueItem, next_ephemeral_send_key
    from optimus.acp.server import NdjsonOutboundChannel
    from optimus.acp.settlement import SendOutcome
    from tests.unit.acp.test_settlement_truth import PhysicalTransport

    transport = PhysicalTransport()
    transport.hold = lambda _: True
    transport.release.clear()
    writer = DedicatedOutboundWriter(transport)
    writer.start()
    if accepted_phase == 'queued':
        blocker_owner = EphemeralSendOwner()
        blocker_key = next_ephemeral_send_key('test-blocker')
        blocker_owner.create_queued(blocker_key)
        writer.submit(OutboundQueueItem(payload={'owned': 'blocker'}, send_key=blocker_key, owner=blocker_owner,
                                        source_future=concurrent.futures.Future()))
        await asyncio.wait_for(transport.entered.wait(), 1)
    accepted, rejected = [], []
    primary = RuntimeError('controlled error after real acceptance')
    actual = writer.submit

    def submit(item):
        try:
            actual(item)
        except RuntimeError:
            rejected.append(item)
            raise
        accepted.append(item)
        raise primary

    monkeypatch.setattr(writer, 'submit', submit)
    adapter, store, _ = make_adapter(tmp_path)
    adapter._outbound = NdjsonOutboundChannel(transport, dedicated_writer=writer)
    session = store.create(cwd=tmp_path, conversation=adapter._new_conversation())
    try:
        with pytest.raises(RuntimeError) as caught:
            await adapter.handle_client_request({'jsonrpc': '2.0', 'id': 1, 'method': 'session/set_mode',
                'params': {'sessionId': session.session_id, 'modeId': 'chat'}})
        assert caught.value is primary
        await asyncio.wait_for(transport.entered.wait(), 1)
        assert len(accepted) == 1 and accepted[0].reservation is not None
        assert not accepted[0].source_future.done()
        assert accepted[0].source_future.running() is (accepted_phase == 'running')
        writer.request_close()
        with pytest.raises(RuntimeError, match='dedicated outbound writer is closed'):
            await adapter.handle_client_request({'jsonrpc': '2.0', 'id': 2, 'method': 'session/set_mode',
                'params': {'sessionId': session.session_id, 'modeId': 'agent'}})
        assert len(rejected) == 1 and rejected[0].source_future.done()
        assert rejected[0].source_future.result().outcome is SendOutcome.CONCLUSIVE_FAILURE
        assert not accepted[0].source_future.done()
        await asyncio.sleep(0)
        assert adapter.retention._entries[session.session_id].uses == 1
        assert adapter.retention.request_retire(session.session_id, reason=RetirementReason.EXPLICIT_REMOVE) is RetirementStatus.DEFERRED
        waiting = asyncio.create_task(adapter.retention.wait_retired(session.session_id))
        await asyncio.sleep(0)
        assert not waiting.done() and store.get(session.session_id) is session
        transport.release.set()
        result = await asyncio.wait_for(waiting, 1)
        assert result is None or result.status is RetirementStatus.RELEASED
        assert accepted[0].source_future.result().outcome is SendOutcome.FLUSHED
        await asyncio.wait_for(adapter.aclose(), 1)
    finally:
        _rescue_rejected_test_sources(rejected)
        transport.release.set()
        await asyncio.wait_for(adapter.aclose(), 2)
        writer.request_close()
        assert writer.observe_closed(1)


async def test_rejected_progress_source_keeps_suppressed_semantics(tmp_path, monkeypatch):
    from optimus.acp.lifecycle import SendKind, TurnControl
    from optimus.acp.outbound_writer import DedicatedOutboundWriter
    from optimus.acp.server import NdjsonOutboundChannel
    from optimus.acp.settlement import SendOutcome, SendState
    from optimus.acp.spec import ProgressAdmission, ProgressSubmission, progress_submission, request_session_custody
    from tests.unit.acp.test_settlement_truth import PhysicalTransport

    transport = PhysicalTransport()
    writer = DedicatedOutboundWriter(transport)
    rejected, errors, _ = _observe_real_rejections(writer, monkeypatch)
    adapter, store, _ = make_adapter(tmp_path)
    channel = NdjsonOutboundChannel(transport, dedicated_writer=writer)
    session = store.create(cwd=tmp_path)
    control = TurnControl(session_id=session.session_id, turn_seq=1)
    send = control.try_start(SendKind.PROGRESS, 'progress')
    assert send.granted and send.send_key is not None
    admission = ProgressAdmission()
    use = adapter.retention.acquire(session.session_id)
    use_token = request_session_custody.set([use])
    progress_token = progress_submission.set(ProgressSubmission(control, send.send_key, admission))
    try:
        outcome = await channel._submit_payload({'method': 'session/update', 'params': {}}, kind='notify')
        assert outcome is SendOutcome.SUPPRESSED
        assert len(errors) == 1 and str(errors[0]) == 'dedicated outbound writer not started'
        assert admission.is_set() and admission.physical_future is rejected[0].source_future
        assert rejected[0].source_future.result().outcome is SendOutcome.SUPPRESSED
        assert control.send_slot(send.send_key).authoritative is SendState.SUPPRESSED
    finally:
        progress_submission.reset(progress_token)
        request_session_custody.reset(use_token)
        use.release()
        _rescue_rejected_test_sources(rejected)
        await asyncio.sleep(0)
        await asyncio.wait_for(adapter.aclose(), 1)
        writer.request_close()
        assert writer.observe_closed(1)


async def test_framed_writer_lifecycle_rejection_resolves_unowned_source(monkeypatch):
    import io

    from optimus.acp.server import StdioByteWriter
    from optimus.acp.settlement import SendOutcome

    writer = StdioByteWriter(io.BytesIO())
    actual_start = writer._dedicated.start

    def start_then_close():
        actual_start()
        writer._dedicated.request_close()

    monkeypatch.setattr(writer._dedicated, 'start', start_then_close)
    rejected, errors, _ = _observe_real_rejections(writer._dedicated, monkeypatch)
    try:
        with pytest.raises(RuntimeError) as caught:
            writer.write(b'owned framed test payload')
        assert caught.value is errors[0]
        assert len(rejected) == 1 and rejected[0].source_future.done()
        assert rejected[0].source_future.result().outcome is SendOutcome.CONCLUSIVE_FAILURE
        await writer.drain()
    finally:
        _rescue_rejected_test_sources(rejected)
        writer.request_close()
        assert writer.observe_closed(1)


async def test_accepted_progress_submit_error_preserves_source_and_original_error(tmp_path, monkeypatch):
    from optimus.acp.lifecycle import SendKind, TurnControl
    from optimus.acp.outbound_writer import DedicatedOutboundWriter
    from optimus.acp.server import NdjsonOutboundChannel
    from optimus.acp.settlement import SendOutcome
    from optimus.acp.spec import ProgressAdmission, ProgressSubmission, progress_submission, request_session_custody
    from tests.unit.acp.test_settlement_truth import PhysicalTransport

    transport = PhysicalTransport()
    transport.hold = lambda _: True
    transport.release.clear()
    writer = DedicatedOutboundWriter(transport)
    writer.start()
    primary = RuntimeError('controlled accepted progress error')
    actual = writer.submit

    def submit(item):
        actual(item)
        raise primary

    monkeypatch.setattr(writer, 'submit', submit)
    adapter, store, _ = make_adapter(tmp_path)
    channel = NdjsonOutboundChannel(transport, dedicated_writer=writer)
    session = store.create(cwd=tmp_path)
    control = TurnControl(session_id=session.session_id, turn_seq=1)
    send = control.try_start(SendKind.PROGRESS, 'progress')
    admission = ProgressAdmission()
    use = adapter.retention.acquire(session.session_id)
    use_token = request_session_custody.set([use])
    progress_token = progress_submission.set(ProgressSubmission(control, send.send_key, admission))
    try:
        try:
            with pytest.raises(RuntimeError) as caught:
                await channel._submit_payload({'method': 'session/update', 'params': {}}, kind='notify')
            assert caught.value is primary
        finally:
            progress_submission.reset(progress_token)
            request_session_custody.reset(use_token)
            use.release()
        await asyncio.wait_for(transport.entered.wait(), 1)
        assert admission.is_set() and not admission.physical_future.done()
        assert adapter.retention._entries[session.session_id].uses == 1
        assert adapter.retention.request_retire(session.session_id, reason=RetirementReason.EXPLICIT_REMOVE) is RetirementStatus.DEFERRED
        transport.release.set()
        await asyncio.wait_for(adapter.retention.wait_retired(session.session_id), 1)
        assert admission.physical_future.result().outcome is SendOutcome.FLUSHED
    finally:
        transport.release.set()
        await asyncio.wait_for(adapter.aclose(), 2)
        writer.request_close()
        assert writer.observe_closed(1)
