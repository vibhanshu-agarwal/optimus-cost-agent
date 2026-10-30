"""Causal ownership schedules for reader and physical worker failure observation."""
import asyncio
import io
import json
import threading
import uuid

import pytest

from optimus.acp import debug_trace, spec
from optimus.acp.lifecycle import TurnControl
from optimus.acp.process_lifecycle import ProcessLifecycle, StopReason
from optimus.acp.spec import AcpDuplexAdapter, AcpPromptTurn, AcpSpecSession, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.telemetry.jsonl import JsonlTelemetryWriter
from tests.integration.acp.test_server_stream import MemoryLineWriter, configured_test_agent_server


async def loop_barrier():
    completed = asyncio.Event()
    asyncio.get_running_loop().call_soon(completed.set)
    await completed.wait()


@pytest.mark.parametrize('diagnostic', ['healthy', 'stderr_failure', 'sanitizer_failure'])
@pytest.mark.parametrize('cleanup_failure', [False, True])
async def test_reader_failure_keeps_primary_and_runs_cleanup(tmp_path, monkeypatch, diagnostic, cleanup_failure):
    from optimus.acp import server
    configured = configured_test_agent_server(tmp_path, output_text='unused')
    original = OSError('reader-private-canary')
    cause = ValueError('cause-private-canary')
    original.__cause__ = cause
    stages = []
    class Reader:
        async def readline(self):
            raise original
    class BadStderr(io.StringIO):
        def write(self, value):
            raise RuntimeError('diagnostic-private-canary')
    if diagnostic == 'stderr_failure':
        monkeypatch.setattr(server.sys, 'stderr', BadStderr())
    if diagnostic == 'sanitizer_failure':
        monkeypatch.setattr(server, 'sanitize_protocol_error_message', lambda value: (_ for _ in ()).throw(RuntimeError('sanitize failed')))
    close_adapter = spec.AcpDuplexAdapter.aclose
    async def adapter_close(adapter):
        stages.append('adapter')
        await close_adapter(adapter)
    monkeypatch.setattr(spec.AcpDuplexAdapter, 'aclose', adapter_close)
    close_redis = configured.server._close_redis_runtime_stage
    async def redis_close():
        stages.append('redis')
        await close_redis()
        if cleanup_failure:
            raise RuntimeError('secondary-private-canary')
    monkeypatch.setattr(configured.server, '_close_redis_runtime_stage', redis_close)
    lifecycle = ProcessLifecycle()
    serving = asyncio.create_task(configured.server.serve_ndjson(Reader(), MemoryLineWriter(), lifecycle=lifecycle))
    lifecycle.bind(asyncio.get_running_loop(), serving)
    with pytest.raises(OSError) as caught:
        await asyncio.wait_for(serving, 2)
    assert caught.value is original and original.__cause__ is cause
    assert lifecycle.reason is StopReason.ERROR
    assert stages == ['adapter', 'redis']
    if cleanup_failure:
        assert 'secondary-private-canary' not in ' '.join(original.__notes__)


def worker_owner(tmp_path):
    debug_trace.reset_debug_trace_context()
    sessions = InMemoryAcpSpecSessionStore()
    session = AcpSpecSession(session_id=f'session-{uuid.uuid4().hex}', cwd=tmp_path)
    sessions._sessions[session.session_id] = session
    turn = AcpPromptTurn(session_id=session.session_id, turn_seq=1,
        turn_control=TurnControl(session_id=session.session_id, turn_seq=1))
    adapter = AcpDuplexAdapter(runner=object(), workspace_root=tmp_path, sessions=sessions,
        outbound=RecordingOutboundChannel(), failure_telemetry=JsonlTelemetryWriter.for_workspace(tmp_path))
    return adapter, session, turn


@pytest.mark.parametrize('schedule', ['attached', 'detach_first', 'completion_first', 'cancel_supervisor'])
@pytest.mark.parametrize('fails', [False, True])
async def test_worker_outcome_observed_at_shared_owner(tmp_path, schedule, fails, capsys):
    adapter, session, turn = worker_owner(tmp_path)
    entered, release = threading.Event(), threading.Event()
    calls = []
    failure = OSError('worker-private-canary')
    custody = set()
    def worker():
        calls.append(True)
        entered.set()
        assert release.wait(5), 'fixture failed to release its worker'
        if fails:
            raise failure
        return 'result'
    token = spec.request_worker_custody.set(custody)
    try:
        waiting = asyncio.create_task(adapter._in_worker(session, turn, worker))
    finally:
        spec.request_worker_custody.reset(token)
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        [owned] = adapter._worker_tasks
        assert owned in custody
        if schedule in ('detach_first', 'cancel_supervisor'):
            if schedule == 'cancel_supervisor':
                owned.cancel()
            waiting.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiting
            await loop_barrier()
            assert not owned.done() and owned in adapter._worker_tasks and owned in custody
            assert session.cost_settlement.settle_turn(turn.run_id).pending_invocations == 1
        elif schedule == 'completion_first':
            owned.add_done_callback(lambda task: waiting.cancel())
        release.set()
        if schedule in ('detach_first', 'cancel_supervisor', 'completion_first'):
            with pytest.raises(asyncio.CancelledError):
                await waiting
        elif fails:
            with pytest.raises(OSError) as caught:
                await waiting
            assert caught.value is failure
        else:
            assert await waiting == 'result'
        await asyncio.wait_for(adapter.aclose(), 2)
        await loop_barrier()
        assert owned.done() and not adapter._worker_tasks and not custody
        assert session.cost_settlement.settle_turn(turn.run_id).pending_invocations == 0
        assert calls == [True]
        path = tmp_path/'.optimus/telemetry.jsonl'
        events = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        expected = int(fails and schedule != 'attached')
        assert len(events) == expected
        text = capsys.readouterr().err
        assert text.count('worker failed after waiter detached') == expected
        assert 'worker-private-canary' not in text
        if expected:
            assert events[0]['run_id'] == turn.run_id
            assert events[0]['error_type'] == 'late_worker_failure'
            assert json.loads(events[0]['message']) == {'run_id':turn.run_id, 'outcome':'failed_after_detach'}
            assert 'worker-private-canary' not in path.read_text()
    finally:
        release.set()
        await asyncio.gather(waiting, return_exceptions=True)
        await adapter.aclose()
        debug_trace.reset_debug_trace_context()


@pytest.mark.parametrize('sink_fault', ['operator', 'trace', 'telemetry'])
async def test_detached_failure_channels_are_independent(tmp_path, monkeypatch, sink_fault, capsys):
    adapter, session, turn = worker_owner(tmp_path)
    trace = tmp_path/'trace.ndjson'
    debug_trace.configure_debug_trace(enabled=True, log_path=trace, provenance_root=tmp_path)
    def fail_sink(*args, **kwargs):
        raise OSError('diagnostic-private-canary')
    if sink_fault == 'operator':
        monkeypatch.setattr(spec, '_operator_line', fail_sink)
    elif sink_fault == 'trace':
        monkeypatch.setattr(debug_trace, 'acp_debug_log', fail_sink)
    else:
        monkeypatch.setattr(JsonlTelemetryWriter, 'append', fail_sink)
    entered, release = threading.Event(), threading.Event()
    def worker():
        entered.set()
        assert release.wait(5)
        raise OSError('worker-private-canary')
    waiting = asyncio.create_task(adapter._in_worker(session, turn, worker))
    closing = None
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        closing = asyncio.create_task(adapter.aclose())
        await loop_barrier()
        assert not closing.done() and adapter._worker_tasks
        assert session.cost_settlement.settle_turn(turn.run_id).pending_invocations == 1
        release.set()
        await asyncio.wait_for(closing, 2)
        await loop_barrier()
        assert not adapter._worker_tasks
        assert session.cost_settlement.settle_turn(turn.run_id).pending_invocations == 0
        text = capsys.readouterr().err
        assert text.count('worker failed after waiter detached') == int(sink_fault != 'operator')
        trace_rows = [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []
        trace_rows = [row for row in trace_rows if row.get('location') == 'debug_trace.py:log_late_worker_failure']
        assert len(trace_rows) == int(sink_fault != 'trace')
        telemetry = tmp_path/'.optimus/telemetry.jsonl'
        events = [json.loads(line) for line in telemetry.read_text().splitlines()] if telemetry.exists() else []
        assert len(events) == int(sink_fault != 'telemetry')
        if trace_rows:
            assert trace_rows[0]['data'] == {'run_id':turn.run_id, 'outcome':'failed_after_detach'}
        persisted = text + (trace.read_text() if trace.exists() else '') + (telemetry.read_text() if telemetry.exists() else '')
        assert 'worker-private-canary' not in persisted and 'diagnostic-private-canary' not in persisted
    finally:
        release.set()
        await asyncio.gather(waiting, return_exceptions=True)
        if closing is not None:
            await closing
        await adapter.aclose()
        debug_trace.reset_debug_trace_context()


@pytest.mark.parametrize('detached', [False, True])
async def test_executor_failure_is_consumed_without_duplicate_reporting(tmp_path, monkeypatch, detached, capsys):
    adapter, session, turn = worker_owner(tmp_path)
    physical = asyncio.get_running_loop().create_future()
    monkeypatch.setattr(asyncio.get_running_loop(), 'run_in_executor', lambda *args: physical)
    failure = OSError('executor-private-canary')
    waiting = asyncio.create_task(adapter._in_worker(session, turn, lambda: None))
    await loop_barrier()
    await loop_barrier()
    try:
        if detached:
            waiting.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiting
        physical.set_exception(failure)
        if not detached:
            with pytest.raises(OSError) as caught:
                await waiting
            assert caught.value is failure
        await adapter.aclose()
        await loop_barrier()
        assert not adapter._worker_tasks
        text = capsys.readouterr().err
        assert text.count('worker failed after waiter detached') == int(detached)
        assert 'executor-private-canary' not in text
        path = tmp_path/'.optimus/telemetry.jsonl'
        events = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        assert len(events) == int(detached)
    finally:
        if not physical.done():
            physical.set_result((True, None))
        await asyncio.gather(waiting, return_exceptions=True)
        await adapter.aclose()
