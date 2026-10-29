"""Idle admission/flush joins on real adapter state, with controlled peer edges."""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
from decimal import Decimal
from multiprocessing.connection import Client
from unittest.mock import Mock

import pytest

from optimus.acp import launch_policy
from optimus.acp.errors import AcpOutboundError
from optimus.acp.lifecycle import ResponseOwnershipSlot
from optimus.acp.outbound_writer import SendOutcome
from optimus.acp.server import NdjsonOutboundChannel
from optimus.acp.settlement import RpcResponseDelivery, SendState
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.agent.models import AgentRunResult, AgentRunStatus
from optimus.mcp.client_config import ClientMcpConfigNormalizer
from optimus.mcp.client_disposition import ClientMcpDisposition, ClientMcpRuntime
from optimus.mcp.client_sdk import ClientMcpSdkAdapter
from optimus.mcp.client_supervisor import MCPAsyncSupervisor
from optimus.mcp.client_trust import ClientMcpDurableStore, ClientMcpLeaseAuthority
from optimus.mcp.local_ipc import LocalIpcError, PendingClientMcpCandidateEndpoint
from optimus.runtime.modes import ExecutionMode
from tests.support.contract_doubles import checked_agent_runner
from tests.support.idle_mcp import context_attachment


class CompletedRunner:
    def __init__(self):
        self.requests = []
        self.runtime_kwargs = []
    def run(self, request, **kwargs):
        self.requests.append(request)
        self.runtime_kwargs.append(kwargs)
        return AgentRunResult(run_id=request.run_id, session_id=request.session_id, execution_mode=request.execution_mode,
                              status=AgentRunStatus.COMPLETED, final_state="CHAT_ONLY", output_text="done",
                              tool_calls=(), total_cost_usd=Decimal("0"), mutation_count=0, provider_keys_resolvable=())


@pytest.fixture
async def composed(tmp_path):
    class ReadOnlyKeyring:
        def get_password(self, _service, _key):
            return None
        def set_password(self, *_args):
            raise AssertionError("renewal must never write durable trust")
    supervisor = MCPAsyncSupervisor()
    supervisor.start()
    sdk = ClientMcpSdkAdapter(supervisor=supervisor, session_factory=lambda _: None,
                              http_client_factory=lambda: None, stdio_transport_factory=lambda _: None,
                              process_control=Mock(spec_set=["terminate_tree"]))
    disposition = ClientMcpDisposition(normalizer=ClientMcpConfigNormalizer(),
        lease_authority=ClientMcpLeaseAuthority(store=ClientMcpDurableStore(keyring_backend=ReadOnlyKeyring(), hmac_key=b"i" * 32)),
        hmac_key=b"i" * 32, controlled_path=str(tmp_path), workspace_digest="d" * 64)
    runtime = ClientMcpRuntime(disposition=disposition, sdk_adapter=sdk, supervisor=supervisor)
    clock = [100.0]
    sessions = InMemoryAcpSpecSessionStore()
    outbound = RecordingOutboundChannel()
    runner = CompletedRunner()
    adapter = AcpDuplexAdapter(runner=checked_agent_runner(runner), workspace_root=tmp_path,
                              sessions=sessions, outbound=outbound, client_mcp_runtime=runtime,
                              mcp_idle_seconds=10, monotonic_clock=lambda: clock[0])
    session = sessions.create(cwd=tmp_path, conversation=adapter._new_conversation())
    async def allow(_params):
        return "allow"
    session.client_mcp_state = await disposition.disposition_for_new_session(session.session_id, tmp_path,
        [{"type": "http", "name": "peer", "url": "https://mcp.example.com/a", "headers": []}], allow)
    try:
        yield adapter, session, clock, outbound, runner
    finally:
        await adapter.aclose()
        runtime.close()


async def prompt(adapter, session, request_id=1, *, defer_response=False):
    return await adapter.handle_client_request({"jsonrpc": "2.0", "id": request_id, "method": "session/prompt",
        "params": {"sessionId": session.session_id, "prompt": [{"type": "text", "text": "hello"}]}},
        ownership_slot=ResponseOwnershipSlot() if defer_response else None)


def flush(control):
    lease = control.start_response_send()
    assert lease.granted and lease.send_key is not None
    assert control.claim_write_started(lease.send_key) is SendState.WRITE_STARTED
    control.publish_authoritative(lease.send_key, SendOutcome.FLUSHED)
    control.finalize_once()


def suspend(state):
    state.register_close_hook(lambda: None, peer=True)
    for hook in state.prepare_suspend():
        hook()
    assert state.complete_suspend(())


class PermissionWire:
    def __init__(self):
        self.requests = asyncio.Queue()
    async def write_line(self, message):
        if message.get("method") == "session/request_permission":
            self.requests.put_nowait(message)


@pytest.mark.parametrize("answer", ["reject", "cancel"])
async def test_refused_or_cancelled_renewal_allocates_nothing_and_cleans_future(composed, answer):
    adapter, session, _, _, runner = composed
    state = session.client_mcp_state
    suspend(state)
    wire = PermissionWire()
    adapter._outbound = channel = NdjsonOutboundChannel(wire)
    before = session.conversation.next_turn_seq, session.conversation.records
    task = asyncio.create_task(prompt(adapter, session))
    pending = await asyncio.wait_for(wire.requests.get(), 1)
    if answer == "cancel":
        await adapter.handle_client_notification({"method": "session/cancel", "params": {"sessionId": session.session_id}})
    else:
        channel.deliver_client_response({"id": pending["id"], "result": {"outcome": {"outcome": "selected", "optionId": "reject_once"}}})
    response = await asyncio.wait_for(task, 1)
    if answer == "cancel":
        assert response.response["result"] == {"stopReason": "cancelled"}
    else:
        assert response.response["error"]["code"] == -32912
    assert before == (session.conversation.next_turn_seq, session.conversation.records)
    assert state.suspended and not runner.requests
    assert channel._futures == {} and adapter._reopen_reservations == {}


async def test_setter_during_renewal_preserves_admitted_mode_and_chat_has_no_mcp(composed):
    adapter, session, _, _, runner = composed
    suspend(session.client_mcp_state)
    wire = PermissionWire()
    adapter._outbound = channel = NdjsonOutboundChannel(wire)
    task = asyncio.create_task(prompt(adapter, session))
    pending = await asyncio.wait_for(wire.requests.get(), 1)
    setter = await asyncio.wait_for(adapter.handle_client_request({"jsonrpc": "2.0", "id": 2, "method": "session/set_mode",
        "params": {"sessionId": session.session_id, "modeId": "chat"}}), 0.25)
    assert "result" in setter.response and not task.done()
    channel.deliver_client_response({"id": pending["id"], "result": {"outcome": {"outcome": "selected", "optionId": "allow_once"}}})
    assert "result" in (await task).response
    assert runner.requests[-1].execution_mode is ExecutionMode.AGENT
    await prompt(adapter, session, 3)
    assert runner.requests[-1].execution_mode is ExecutionMode.CHAT
    assert runner.runtime_kwargs[-1].get("client_mcp_service") is None
    assert runner.runtime_kwargs[-1].get("mcp_permission_broker") is None
    assert channel._futures == {}


async def test_second_shutdown_cancellation_keeps_worker_owned_until_release(composed):
    adapter, session, _, _, _ = composed
    entered, release = threading.Event(), threading.Event()
    def held_close():
        entered.set()
        assert release.wait(2)
    session.client_mcp_state.register_close_hook(held_close, peer=True)
    task = asyncio.create_task(adapter.aclose())
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done() and adapter._mcp_close_tasks
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not adapter._mcp_close_tasks


async def test_failed_owned_close_does_not_skip_other_session_hooks(composed):
    adapter, session, _, _, _ = composed
    release = asyncio.Event()
    failure = RuntimeError("controlled owned-close failure")
    closed = []
    session.client_mcp_state.register_close_hook(lambda: closed.append("peer"), peer=True)
    async def fail_close():
        await release.wait()
        raise failure
    owned = asyncio.create_task(fail_close())
    adapter._mcp_close_tasks.add(owned)
    closing = asyncio.create_task(adapter.aclose())
    await asyncio.sleep(0)
    release.set()
    with pytest.raises(RuntimeError) as caught:
        await closing
    assert caught.value is failure
    assert closed == ["peer"]


async def test_strategy_setter_during_renewal_applies_only_to_next_prompt(composed):
    adapter, session, _, _, runner = composed
    adapter._context_attachment = context_attachment()
    session.context_strategy = "compaction"
    session.conversation = adapter._new_conversation()
    suspend(session.client_mcp_state)
    wire = PermissionWire()
    adapter._outbound = channel = NdjsonOutboundChannel(wire)
    task = asyncio.create_task(prompt(adapter, session))
    pending = await asyncio.wait_for(wire.requests.get(), 1)
    setter = await asyncio.wait_for(adapter.handle_client_request({"jsonrpc": "2.0", "id": 2,
        "method": "session/set_config_option", "params": {"sessionId": session.session_id,
        "configId": "context_strategy", "value": "sliding_window"}}), 0.25)
    assert "result" in setter.response and not task.done()
    channel.deliver_client_response({"id": pending["id"], "result": {"outcome": {"outcome": "selected", "optionId": "allow_once"}}})
    assert "result" in (await task).response
    assert runner.runtime_kwargs[-1]["context_packer"].strategy == "compaction"
    assert session.sliding_notice_pending
    await prompt(adapter, session, 3)
    assert runner.runtime_kwargs[-1]["context_packer"].strategy == "sliding_window"
    assert not session.sliding_notice_pending


async def test_known_noncommit_normal_error_envelope_can_arm_after_flush(composed, monkeypatch):
    adapter, session, clock, _, runner = composed
    closed = []
    session.client_mcp_state.register_close_hook(lambda: closed.append("peer"), peer=True)
    def refused(*_args, **_kwargs):
        raise AcpOutboundError(code=-32800, message="controlled refusal")
    monkeypatch.setattr(runner, "run", refused)
    envelope = await prompt(adapter, session, defer_response=True)
    assert "error" in envelope.response and not session.conversation.records
    flush(envelope.turn_control)
    adapter.note_turn_delivered(envelope.turn_control)
    clock[0] += 10
    await adapter.sweep_idle_mcp_once()
    assert closed == ["peer"]


@pytest.mark.parametrize("failure_point", ["prepare", "postcommit_notice"])
async def test_real_commit_marker_survives_prepare_failure_or_postcommit_cancellation(composed, monkeypatch, failure_point):
    adapter, session, clock, _, _ = composed
    closed = []
    session.client_mcp_state.register_close_hook(lambda: closed.append("peer"), peer=True)
    if failure_point == "prepare":
        def fail_prepare(*_args, **_kwargs):
            raise RuntimeError("controlled prepare failure")
        monkeypatch.setattr(session.conversation, "prepare_commit", fail_prepare)
        expected = RuntimeError
    else:
        async def cancel_notice(**_kwargs):
            raise asyncio.CancelledError
        monkeypatch.setattr(adapter, "_emit_usage_update", cancel_notice)
        expected = asyncio.CancelledError
    with pytest.raises(expected):
        await prompt(adapter, session)
    marker = adapter._idle_mcp[session.session_id]
    assert marker.marker_seen
    assert marker.committed is (None if failure_point == "prepare" else True)
    assert bool(session.conversation.records) is (failure_point == "postcommit_notice")
    clock[0] += 20
    await adapter.sweep_idle_mcp_once()
    assert not closed


async def test_pending_sdk_release_quarantines_and_blocks_future_prompts(composed, monkeypatch):
    adapter, session, clock, _, runner = composed
    session.client_mcp_state.register_close_hook(lambda: None, peer=True)
    envelope = await prompt(adapter, session, defer_response=True)
    flush(envelope.turn_control)
    adapter.note_turn_delivered(envelope.turn_control)
    monkeypatch.setattr(adapter._client_mcp_runtime.sdk_adapter, "has_pending_connections_for_session", lambda _: True)
    clock[0] += 10
    await adapter.sweep_idle_mcp_once()
    refusal = await prompt(adapter, session, 2)
    assert refusal.response["error"]["data"]["reason"] == "mcp_cleanup_uncertain"
    assert len(runner.requests) == 1


async def test_unobservable_warning_preflight_keeps_peer_open_until_a_later_turn_rearms(composed, monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="mcp.client.stdio")
    adapter, session, clock, _, _ = composed
    async def allow(_params):
        return "allow"
    runtime = adapter._client_mcp_runtime
    session.client_mcp_state = await runtime.disposition.disposition_for_new_session(session.session_id, session.cwd,
        [{"name": "peer", "command": sys.executable, "args": [], "env": []}], allow)
    closed = []
    session.client_mcp_state.register_close_hook(lambda: closed.append("peer"), peer=True)
    response = await prompt(adapter, session, defer_response=True)
    flush(response.turn_control)
    adapter.note_turn_delivered(response.turn_control)
    clock[0] += 10
    with monkeypatch.context() as patch:
        patch.setattr(runtime.sdk_adapter, "stdio_warning_channel_observable", lambda: False)
        await adapter.sweep_idle_mcp_once()
    assert not closed and runtime.sdk_adapter.diagnostics[-1] == "WARNING_UNOBSERVABLE"
    response = await prompt(adapter, session, 2, defer_response=True)
    flush(response.turn_control)
    adapter.note_turn_delivered(response.turn_control)
    clock[0] += 10
    await adapter.sweep_idle_mcp_once()
    assert closed == ["peer"]


async def test_pre_admission_capacity_refusal_preserves_deadline_and_asks_no_permission(composed):
    adapter, session, _, outbound, _ = composed
    session.client_mcp_state.register_close_hook(lambda: None, peer=True)
    envelope = await prompt(adapter, session, defer_response=True)
    flush(envelope.turn_control)
    adapter.note_turn_delivered(envelope.turn_control)
    deadline = adapter._idle_mcp[session.session_id].deadline
    from optimus.acp.conversation import ConversationDisposition
    session.conversation._disposition = ConversationDisposition.CAP_CLOSED
    await prompt(adapter, session, 2)
    assert adapter._idle_mcp[session.session_id].deadline == deadline
    assert not outbound.requests


async def test_unknown_marker_and_cancelled_delivery_never_arm(composed):
    adapter, session, clock, _, _ = composed
    closed = []
    session.client_mcp_state.register_close_hook(lambda: closed.append("peer"), peer=True)
    for unknown, cancelled in [(True, False), (False, True)]:
        response = await prompt(adapter, session, defer_response=True)
        if unknown:
            adapter.record_turn_commit(session.session_id, response.turn_control.turn_seq, committed=None)
        flush(response.turn_control)
        adapter.note_turn_delivered(response.turn_control, cancelled=cancelled)
        clock[0] += 20
        await adapter.sweep_idle_mcp_once()
    assert not closed


async def test_never_opened_lease_does_not_arm_or_renew(composed):
    adapter, session, clock, outbound, _ = composed
    response = await prompt(adapter, session, defer_response=True)
    flush(response.turn_control)
    adapter.note_turn_delivered(response.turn_control)
    clock[0] += 20
    await adapter.sweep_idle_mcp_once()
    assert not session.client_mcp_state.suspended and outbound.requests == []


async def test_idle_requires_actual_flush_and_exact_deadline(composed):
    adapter, session, clock, _, _ = composed
    closed = []
    session.client_mcp_state.register_close_hook(lambda: closed.append("peer"), peer=True)
    envelope = await prompt(adapter, session)
    adapter.note_turn_delivered(envelope.turn_control)
    clock[0] = 1000
    await adapter.sweep_idle_mcp_once()
    assert closed == []
    envelope = await prompt(adapter, session, 2, defer_response=True)
    flush(envelope.turn_control)
    adapter.note_turn_delivered(envelope.turn_control)
    clock[0] = 1009.999
    await adapter.sweep_idle_mcp_once()
    assert closed == []
    clock[0] = 1010
    await adapter.sweep_idle_mcp_once()
    assert closed == ["peer"] and session.client_mcp_state.suspended


@pytest.mark.parametrize("stale", [False, True], ids=["current", "stale"])
async def test_new_prompt_invalidates_late_older_flush(composed, stale):
    """Delay delivery observation of an authoritative flush; late physical publication is covered separately."""
    adapter, session, clock, _, _ = composed
    closed = []
    session.client_mcp_state.register_close_hook(lambda: closed.append("peer"), peer=True)
    old = await prompt(adapter, session, defer_response=True)
    flush(old.turn_control)
    current = await prompt(adapter, session, 2, defer_response=True)
    flush(current.turn_control)
    assert old.turn_control.rpc_response_delivery is RpcResponseDelivery.FLUSHED
    assert current.turn_control.rpc_response_delivery is RpcResponseDelivery.FLUSHED
    idle = adapter._idle_mcp[session.session_id]
    assert idle.turn_seq == current.turn_control.turn_seq != old.turn_control.turn_seq
    assert idle.marker_seen and idle.committed is True
    assert idle.turn_epoch == idle.idle_epoch
    assert idle.phase == "ACTIVE" and idle.deadline is None
    assert session.session_id not in adapter._active_turns
    assert session.client_mcp_state.has_open_peer()
    adapter.note_turn_delivered(old.turn_control if stale else current.turn_control)
    assert idle.deadline == (None if stale else 110)
    clock[0] = 109.999
    await adapter.sweep_idle_mcp_once()
    assert closed == []
    clock[0] = 110
    await adapter.sweep_idle_mcp_once()
    assert closed == ([] if stale else ["peer"])
    assert session.client_mcp_state.suspended is (not stale)


async def test_suspended_chat_stays_suspended_without_permission(composed):
    adapter, session, _, outbound, runner = composed
    session.client_mcp_state.register_close_hook(lambda: None, peer=True)
    hooks = session.client_mcp_state.prepare_suspend()
    for hook in hooks:
        hook()
    session.client_mcp_state.complete_suspend(())
    session.execution_mode = ExecutionMode.CHAT
    result = await prompt(adapter, session)
    assert "result" in result.response
    assert session.client_mcp_state.suspended
    assert outbound.requests == [] and runner.requests[-1].execution_mode is ExecutionMode.CHAT


@pytest.mark.parametrize("uncertain_peer", [False, True])
async def test_retained_shared_listener_does_not_quarantine_released_peers(composed, tmp_path, monkeypatch, uncertain_peer):
    adapter, session, clock, outbound, runner = composed
    runtime = adapter._client_mcp_runtime
    endpoint = PendingClientMcpCandidateEndpoint(authkey=b"held-shared-permission-listener")
    runtime.candidate_endpoint = endpoint
    runtime.disposition._candidate_endpoint = endpoint
    async def allow(_params):
        return "allow"
    state = session.client_mcp_state = await runtime.disposition.disposition_for_new_session(
        session.session_id, tmp_path,
        [{"type": "http", "name": "peer", "url": "https://mcp.example.com/a", "headers": []}], allow,
    )
    peer = None
    owner = None
    try:
        address = endpoint.endpoint_address[1]
        owner = endpoint._thread
        generation = endpoint._generation
        assert owner is not None
        peer = Client(address)
        assert peer.poll(1) and peer.recv_bytes(), "peer must hold the actual listener's authentication"
        state.register_close_hook(lambda: None, peer=True)
        if uncertain_peer:
            monkeypatch.setattr(runtime.sdk_adapter, "has_pending_connections_for_session", lambda _sid: True)
        envelope = await prompt(adapter, session, defer_response=True)
        flush(envelope.turn_control)
        adapter.note_turn_delivered(envelope.turn_control)
        clock[0] += 11
        await adapter.sweep_idle_mcp_once()
        assert endpoint.pending_count == 0
        assert endpoint._thread is owner and owner.is_alive()
        assert endpoint._generation == generation
        with pytest.raises(LocalIpcError, match="ipc_stop_incomplete"):
            _ = endpoint.endpoint_address
        session.execution_mode = ExecutionMode.CHAT
        result = await prompt(adapter, session, 2)
        if uncertain_peer:
            assert not state.suspended and "error" in result.response
        else:
            assert state.suspended and "result" in result.response
            assert runner.requests[-1].execution_mode is ExecutionMode.CHAT
            assert runner.runtime_kwargs[-1].get("client_mcp_service") is None
            assert runner.runtime_kwargs[-1].get("mcp_permission_broker") is None
            assert outbound.requests == [] and not runtime.disposition.close_failure_recorded
        outcome = await asyncio.to_thread(runtime.close)
        assert not outcome.complete and not outcome.endpoint_closed
        peer.close()
        peer = None
        await asyncio.to_thread(owner.join, 5)
        assert not owner.is_alive()
        assert not (await asyncio.to_thread(runtime.close)).complete, "observed final-close failure is sticky"
    finally:
        if peer is not None:
            peer.close()
        if owner is not None:
            await asyncio.to_thread(owner.join, 5)
        endpoint.close()
        assert owner is None or not owner.is_alive()


async def test_slow_close_leaves_serving_loop_responsive(composed):
    adapter, session, clock, _, _ = composed
    entered, release = threading.Event(), threading.Event()
    def slow_peer():
        entered.set()
        assert release.wait(0.5)
    session.client_mcp_state.register_close_hook(slow_peer, peer=True)
    envelope = await prompt(adapter, session, defer_response=True)
    flush(envelope.turn_control)
    adapter.note_turn_delivered(envelope.turn_control)
    clock[0] = 110
    sweep = asyncio.create_task(adapter.sweep_idle_mcp_once())
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        other = adapter._sessions.create(cwd=session.cwd, conversation=adapter._new_conversation())
        response = await asyncio.wait_for(prompt(adapter, other), 0.25)
        assert "result" in response.response and not sweep.done()
    finally:
        release.set()
        await sweep


@pytest.mark.parametrize("raw", ["0", "-1", "off", "", "1.5", "2592001"])
def test_idle_policy_rejects_invalid_values(raw):
    with pytest.raises(ValueError):
        launch_policy.resolve_acp_mcp_idle_seconds({"OPTIMUS_ACP_MCP_IDLE_SECONDS": raw})


def test_idle_policy_default_and_bounds():
    assert launch_policy.resolve_acp_mcp_idle_seconds({}) == 3600
    assert launch_policy.resolve_acp_mcp_idle_seconds({"OPTIMUS_ACP_MCP_IDLE_SECONDS": "1"}) == 1
    assert launch_policy.resolve_acp_mcp_idle_seconds({"OPTIMUS_ACP_MCP_IDLE_SECONDS": "2592000"}) == 2592000
