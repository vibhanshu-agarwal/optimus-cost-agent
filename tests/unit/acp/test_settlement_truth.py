"""Settlement facts must agree with real history and the physical writer at response exit."""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import threading
from dataclasses import replace

import pytest

from optimus.acp.admission import DEFAULT_LIMITS, AdmissionClass
from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.acp.lifecycle import TurnControl, TurnSendKey
from optimus.acp.outbound_writer import DedicatedOutboundWriter, OutboundQueueItem
from optimus.acp.server import AcpStreamServer
from optimus.acp.settlement import FinalDelivery, SendOutcome, SendState
from optimus.acp.shapes import AGENT_MESSAGE_BLOCK_SEPARATOR
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.agent.models import AgentRunResult, AgentRunStatus, AgentToolCall
from optimus.telemetry.events import TelemetryEventKind
from tests.integration.acp.test_server_stream import InteractiveLineReader
from tests.support.contract_doubles import checked_agent_runner


async def tick():
    event = asyncio.Event()
    asyncio.get_running_loop().call_soon(event.set)
    await event.wait()


class Script:
    def __init__(self, status=AgentRunStatus.COMPLETED):
        self.status = status
        self.cancel = False

    def run(self, request, *, operation_control=None, **kwargs):
        if self.cancel:
            operation_control.request_session_cancel()
        if self.status == "exception":
            raise ValueError("runner failed")
        return AgentRunResult(run_id=request.run_id, session_id=request.session_id,
            execution_mode=request.execution_mode, status=self.status, final_state=self.status.value,
            output_text="answer", plan_hash="plan" if self.status is AgentRunStatus.AWAITING_APPROVAL else None)


class PhysicalTransport:
    def __init__(self):
        self.loop = asyncio.get_running_loop()
        self.flushed = asyncio.Queue()
        self.writes = []
        self.flushes = []
        self.hold = lambda message: False
        self.fail = lambda message: False
        self.entered = asyncio.Event()
        self.release = threading.Event()
        self.release.set()

    def write_bytes(self, data):
        self.writes.append(json.loads(data))

    def flush(self):
        message = self.writes[-1]
        if self.hold(message):
            self.loop.call_soon_threadsafe(self.entered.set)
            if not self.release.wait(5):
                raise TimeoutError("test barrier unreleased")
        if self.fail(message):
            raise OSError("physical flush failed")
        self.flushes.append(message)
        self.loop.call_soon_threadsafe(self.flushed.put_nowait, message)

    async def write_line(self, message):
        raise AssertionError("server must use dedicated physical writer")

    async def until(self, predicate):
        while True:
            message = await asyncio.wait_for(self.flushed.get(), 3)
            if predicate(message):
                return message


class ServerTurn:
    def __init__(self, tmp_path, monkeypatch, script=None):
        self.script = script or Script()
        self.transport = PhysicalTransport()
        self.reader = InteractiveLineReader()
        self.events = []
        self.sink_errors = []
        self.settled = asyncio.Event()
        self.expect = {}
        original = AcpDuplexAdapter.__init__
        owner = self
        def capture(adapter, *args, **kwargs):
            original(adapter, *args, **kwargs)
            owner.adapter = adapter
        monkeypatch.setattr(AcpDuplexAdapter, "__init__", capture)
        original_remove = AcpDuplexAdapter._remove_active_turn
        def observe_retirement(adapter, session_id, turn_seq, control):
            owner.retired_control = control
            return original_remove(adapter, session_id, turn_seq, control)
        monkeypatch.setattr(AcpDuplexAdapter, "_remove_active_turn", observe_retirement)
        runner = checked_agent_runner(self.script)
        runner.event_sink = self.sink
        self.server = AcpStreamServer(dispatcher=JsonRpcDispatcher(agent_runner=runner, workspace_root=tmp_path))
        self.tmp_path = tmp_path

    def sink(self, event):
        if event.kind is not TelemetryEventKind.ACP_TURN_SETTLEMENT:
            return
        self.events.append(event)
        try:
            assert len(event.payload) == 11
            for key, value in self.expect.items():
                assert event.payload[key] == value, (key, event.payload)
            records = self.adapter._sessions.get(event.session_id).conversation.records
            assert bool(records) == (event.payload["conversation_commit"] == "committed")
            assert event.session_id not in self.adapter._active_turns
            control = self.retired_control
            assert control.session_id == event.session_id and control.turn_seq == event.payload["turn_seq"]
            assert control.final_delivery.value == event.payload["final_delivery"]
            assert control.rpc_response_delivery.value == event.payload["rpc_response_delivery"]
            response_state = control.send_slot(TurnSendKey("protocol_response", "response")).authoritative.value
            assert response_state == ("suppressed" if event.payload["rpc_response_delivery"] == "not_attempted"
                                      else event.payload["rpc_response_delivery"])
            if event.payload["rpc_response_delivery"] == "flushed":
                assert any(m.get("id") == "prompt" for m in self.transport.flushes)
        except AssertionError as exc:
            self.sink_errors.append(exc)
        finally:
            self.settled.set()

    async def start(self):
        self.task = asyncio.create_task(self.server.serve_ndjson(self.reader, self.transport))
        await self.reader.send({"jsonrpc": "2.0", "id": "new", "method": "session/new", "params": {"cwd": str(self.tmp_path)}})
        response = await self.transport.until(lambda m: m.get("id") == "new")
        self.session_id = response["result"]["sessionId"]

    async def prompt(self):
        await self.reader.send({"jsonrpc": "2.0", "id": "prompt", "method": "session/prompt", "params": {
            "sessionId": self.session_id, "prompt": [{"type": "text", "text": "Explain"}]}})

    async def close(self):
        self.transport.release.set()
        self.reader.close()
        await asyncio.wait_for(asyncio.gather(self.task, return_exceptions=True), 5)


@pytest.mark.parametrize(("status", "settlement"), [
    (AgentRunStatus.COMPLETED, "completed"), (AgentRunStatus.FAILED, "failed"), ("exception", "failed")])
async def test_server_settlement_matches_real_history_and_response(tmp_path, monkeypatch, status, settlement):
    h = ServerTurn(tmp_path, monkeypatch, Script(status))
    h.expect = {"settlement": settlement, "conversation_commit": "not_committed" if status == "exception" else "committed",
        "rpc_response_delivery": "flushed", "final_delivery": "not_attempted" if status == "exception" else "flushed"}
    await h.start()
    try:
        await h.prompt()
        await asyncio.wait_for(h.settled.wait(), 3)
        assert not h.sink_errors
        assert len(h.events) == 1
    finally:
        await h.close()


@pytest.mark.parametrize("boundary", ["terminal", "response"])
async def test_held_flush_keeps_turn_active_and_settlement_unclaimed(tmp_path, monkeypatch, boundary):
    h = ServerTurn(tmp_path, monkeypatch)
    await h.start()
    h.transport.hold = (lambda m: m.get("id") == "prompt") if boundary == "response" else (
        lambda m: m.get("params", {}).get("update", {}).get("sessionUpdate") == "agent_message_chunk")
    h.transport.release.clear()
    try:
        await h.prompt()
        await asyncio.wait_for(h.transport.entered.wait(), 3)
        assert not h.events
        turn = h.adapter._active_turns[h.session_id]
        records = h.adapter._sessions.get(h.session_id).conversation.records
        assert bool(records) == (boundary == "response")
        key = TurnSendKey("protocol_response", "response") if boundary == "response" else TurnSendKey("terminal_set", "final_text")
        assert turn.turn_control.send_slot(key).authoritative is SendState.WRITE_STARTED
        h.transport.release.set()
        await asyncio.wait_for(h.settled.wait(), 3)
        assert not h.sink_errors
    finally:
        await h.close()


@pytest.mark.parametrize(("cancel", "expected"), [(False, "rejected"), (True, "cancelled")])
async def test_uncommitted_semantic_outcome_survives_permission_or_cancel(tmp_path, monkeypatch, cancel, expected):
    script = Script(AgentRunStatus.AWAITING_APPROVAL)
    script.cancel = cancel
    h = ServerTurn(tmp_path, monkeypatch, script)
    h.expect = {"settlement": expected, "conversation_commit": "not_committed", "final_delivery": "not_attempted",
        "rpc_response_delivery": "flushed"}
    await h.start()
    try:
        await h.prompt()
        if not cancel:
            request = await h.transport.until(lambda m: m.get("method") == "session/request_permission")
            await h.reader.send({"jsonrpc": "2.0", "id": request["id"], "result": {"outcome": {"outcome": "cancelled"}}})
        await asyncio.wait_for(h.settled.wait(), 3)
        assert not h.sink_errors
    finally:
        await h.close()


async def test_committed_history_survives_failed_rpc_flush(tmp_path, monkeypatch):
    h = ServerTurn(tmp_path, monkeypatch)
    h.expect = {"settlement": "completed", "conversation_commit": "committed", "rpc_response_delivery": "ambiguous"}
    await h.start()
    h.transport.fail = lambda m: m.get("id") == "prompt"
    try:
        await h.prompt()
        await asyncio.wait_for(h.settled.wait(), 3)
        assert not h.sink_errors
        assert sum(m.get("id") == "prompt" for m in h.transport.writes) == 1
    finally:
        await h.close()


async def test_bare_notify_return_does_not_fabricate_terminal_flush(tmp_path):
    class Bare(RecordingOutboundChannel):
        async def notify(self, method, params, *, require_flushed=False):
            return None
    events = []
    sessions = InMemoryAcpSpecSessionStore()
    adapter = AcpDuplexAdapter(runner=checked_agent_runner(Script()), workspace_root=tmp_path,
        sessions=sessions, outbound=Bare(), settlement_sink=events.append)
    new = await adapter.handle_client_request({"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path)}})
    sid = new.response["result"]["sessionId"]
    await adapter.handle_client_request({"jsonrpc": "2.0", "id": 2, "method": "session/prompt", "params": {
        "sessionId": sid, "prompt": [{"type": "text", "text": "Explain"}]}})
    assert not sessions.get(sid).conversation.records
    assert events[-1].payload["conversation_commit"] == "not_committed"
    assert events[-1].payload["rpc_response_delivery"] == "not_attempted"


@pytest.mark.parametrize("outcome", [SendOutcome.CONCLUSIVE_FAILURE, SendOutcome.AMBIGUOUS])
def test_terminal_set_never_promotes_partial_or_ambiguous_to_flushed(outcome):
    control = TurnControl(session_id="s", turn_seq=1)
    control.seal_final_delivery()
    first = control.start_terminal_message("one").send_key
    second = control.start_terminal_message("two").send_key
    control.publish_authoritative(first, outcome)
    control.publish_authoritative(second, SendOutcome.FLUSHED)
    assert control.final_delivery is (FinalDelivery.AMBIGUOUS if outcome is SendOutcome.AMBIGUOUS else FinalDelivery.PARTIAL)


def test_writer_exception_fallback_publishes_before_source_completion():
    class BrokenClaim(TurnControl):
        def claim_write_started(self, key):
            raise ValueError("owner claim failure")
    control = BrokenClaim(session_id="s", turn_seq=1)
    lease = control.start_response_send()
    source = concurrent.futures.Future()
    observed = []
    source.add_done_callback(lambda f: observed.append(control.send_slot(lease.send_key).authoritative))
    class Unused:
        def write_bytes(self, data):
            raise AssertionError("must not write")
        def flush(self):
            raise AssertionError("must not flush")
    writer = DedicatedOutboundWriter(Unused())
    writer.start()
    try:
        writer.submit(OutboundQueueItem(payload={}, send_key=lease.send_key, owner=control, source_future=source))
        assert source.result(timeout=3).outcome is SendOutcome.AMBIGUOUS
    finally:
        writer.close_and_join()
    assert observed == [SendState.AMBIGUOUS]

@pytest.mark.parametrize("failure", ["preparation", "flush"])
async def test_second_required_message_failure_never_commits_prefix(tmp_path, monkeypatch, failure):
    h = ServerTurn(tmp_path, monkeypatch)
    h.expect = {"settlement": "completed", "conversation_commit": "not_committed",
        "final_delivery": "partial" if failure == "preparation" else "ambiguous", "rpc_response_delivery": "flushed"}
    await h.start()
    def final(m):
        return m.get("params", {}).get("update", {}).get("sessionUpdate") == "agent_message_chunk"
    if failure == "flush":
        h.transport.fail = final
    else:
        original = DedicatedOutboundWriter.submit
        def fail_preparation(writer, item):
            if final(item.payload):
                item.prepare_error = ValueError("serialization refused")
            return original(writer, item)
        monkeypatch.setattr(DedicatedOutboundWriter, "submit", fail_preparation)
    try:
        await h.prompt()
        await asyncio.wait_for(h.settled.wait(), 3)
        assert not h.sink_errors
        assert any(m.get("params", {}).get("update", {}).get("sessionUpdate") == "plan" for m in h.transport.flushes)
    finally:
        await h.close()


@pytest.mark.parametrize("phase", ["queued", "write_started"])
async def test_response_cancellation_freezes_commit_before_late_flush(tmp_path, monkeypatch, phase):
    h = ServerTurn(tmp_path, monkeypatch)
    h.expect = {"settlement": "transport_abandoned", "conversation_commit": "committed",
        "rpc_response_delivery": "ambiguous" if phase == "write_started" else "not_attempted"}
    await h.start()
    h.transport.release.clear()
    h.transport.hold = lambda m: m.get("id") == ("prompt" if phase == "write_started" else "blocker")
    response_submitted = asyncio.Event()
    if phase == "queued":
        original = DedicatedOutboundWriter.submit
        def queue_blocker(writer, item):
            if item.payload.get("id") == "prompt":
                blocker = TurnControl(session_id="blocker", turn_seq=1)
                lease = blocker.start_response_send()
                original(writer, OutboundQueueItem(payload={"id": "blocker"}, send_key=lease.send_key,
                    owner=blocker, source_future=concurrent.futures.Future()))
                result = original(writer, item)
                response_submitted.set()
                return result
            return original(writer, item)
        monkeypatch.setattr(DedicatedOutboundWriter, "submit", queue_blocker)
    try:
        await h.prompt()
        await asyncio.wait_for(h.transport.entered.wait(), 3)
        if phase == "queued":
            await asyncio.wait_for(response_submitted.wait(), 3)
        control = h.adapter._active_turns[h.session_id].turn_control
        h.task.cancel()
        await asyncio.wait_for(h.settled.wait(), 3)
        assert not h.sink_errors
        frozen = h.events[0].payload.copy()
        h.transport.release.set()
        await asyncio.wait_for(asyncio.gather(h.task, return_exceptions=True), 5)
        assert h.events[0].payload == frozen
        assert len(h.events) == 1
        if phase == "queued":
            assert not any(m.get("id") == "prompt" for m in h.transport.writes)
        else:
            assert control.send_slot(TurnSendKey("protocol_response", "response")).diagnostic is SendOutcome.FLUSHED
    finally:
        await h.close()


@pytest.mark.parametrize("reserve_exhausted", [False, True])
async def test_terminal_submission_uses_required_reserve(tmp_path, reserve_exhausted, request):
    from optimus.acp.server import NdjsonOutboundChannel
    from optimus.acp.spec import AcpPromptTurn
    transport = PhysicalTransport()
    transport.release.clear()
    transport.hold = lambda m: True
    limits = replace(DEFAULT_LIMITS, outbound_items=1, control_items=1)
    writer = DedicatedOutboundWriter(transport, limits=limits)
    request.addfinalizer(lambda: (transport.release.set(), writer.close_and_join()))
    writer.start()
    occupied = []
    for index in range(2 if reserve_exhausted else 1):
        control = TurnControl(session_id="block", turn_seq=index)
        lease = control.start_response_send()
        future = concurrent.futures.Future()
        writer.submit(OutboundQueueItem(payload={"id": index}, send_key=lease.send_key, owner=control,
            source_future=future, admission_class=AdmissionClass.REQUIRED))
        occupied.append(future)
    await asyncio.wait_for(transport.entered.wait(), 3)
    control = TurnControl(session_id="s", turn_seq=1)
    turn = AcpPromptTurn(session_id="s", turn_seq=1, turn_control=control)
    adapter = AcpDuplexAdapter(runner=checked_agent_runner(Script()), workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(), outbound=NdjsonOutboundChannel(transport, dedicated_writer=writer))
    call = asyncio.create_task(adapter._emit_final_text(session_id="s", text="answer", turn=turn))
    try:
        await tick()
        if reserve_exhausted:
            result = await asyncio.gather(call, return_exceptions=True)
            assert isinstance(result[0], Exception)
            assert control.final_delivery is FinalDelivery.CONCLUSIVE_FAILURE
            assert writer.admission_failure.done()
        else:
            assert not call.done()
            assert writer._admission.count == 2
        transport.release.set()
        await asyncio.gather(call, return_exceptions=True)
        if not reserve_exhausted:
            assert control.final_delivery is FinalDelivery.FLUSHED
    finally:
        transport.release.set()
        await asyncio.gather(call, return_exceptions=True)
        await asyncio.to_thread(writer.close_and_join)

async def test_direct_and_transport_owned_completion_boundaries(tmp_path):
    from optimus.acp.lifecycle import ResponseOwnershipSlot
    events = []
    sessions = InMemoryAcpSpecSessionStore()
    adapter = AcpDuplexAdapter(runner=checked_agent_runner(Script()), workspace_root=tmp_path,
        sessions=sessions, outbound=RecordingOutboundChannel(), settlement_sink=events.append)
    new = await adapter.handle_client_request({"jsonrpc": "2.0", "id": "reuse", "method": "session/new", "params": {"cwd": str(tmp_path)}})
    sid = new.response["result"]["sessionId"]
    request = {"jsonrpc": "2.0", "id": "reuse", "method": "session/prompt", "params": {
        "sessionId": sid, "prompt": [{"type": "text", "text": "Explain"}]}}
    await adapter.handle_client_request(request)
    assert len(events) == 1 and events[0].payload["rpc_response_delivery"] == "not_attempted"
    assert events[0].payload["conversation_commit"] == "committed"
    slot = ResponseOwnershipSlot()
    envelope = await adapter.handle_client_request(request, ownership_slot=slot)
    assert len(events) == 1 and sid in adapter._active_turns
    busy = await adapter.handle_client_request(request)
    assert busy.response["error"]["message"] == "a turn is already in progress"
    old = slot.turn_control
    old.finalize_once()
    assert len(events) == 2 and sid not in adapter._active_turns
    next_slot = ResponseOwnershipSlot()
    await adapter.handle_client_request(request, ownership_slot=next_slot)
    assert next_slot.turn_control is not old
    old.finalize_once()
    assert adapter._active_turns[sid].turn_control is next_slot.turn_control
    assert adapter._remove_active_turn(sid, next_slot.turn_control.turn_seq, old) is False
    next_slot.turn_control.finalize_once()
    assert len(events) == 3
    assert envelope.turn_control is old


@pytest.mark.parametrize("failure", ["insertion", "decision"])
async def test_no_commit_fact_without_successful_canonical_insertion(tmp_path, monkeypatch, failure):
    from optimus.acp.conversation import ConversationState
    original = ConversationState.prepare_commit
    if failure == "decision":
        def reject(state, *args, **kwargs):
            return replace(original(state, *args, **kwargs), commit=False)
        monkeypatch.setattr(ConversationState, "prepare_commit", reject)
    else:
        def fail(state, decision):
            raise ValueError("canonical insertion failed")
        monkeypatch.setattr(ConversationState, "commit_after_final_flush", fail)
    h = ServerTurn(tmp_path, monkeypatch)
    h.expect = {"settlement": "completed", "conversation_commit": "not_committed", "final_delivery": "flushed",
        "rpc_response_delivery": "flushed"}
    await h.start()
    try:
        await h.prompt()
        await asyncio.wait_for(h.settled.wait(), 3)
        assert not h.sink_errors
        assert not h.adapter._sessions.get(h.session_id).auto_routes
    finally:
        await h.close()


@pytest.mark.parametrize("raised", [RuntimeError, asyncio.CancelledError])
async def test_direct_settlement_sink_exception_contract(tmp_path, raised):
    calls = []
    def sink(event):
        calls.append(event)
        raise raised("sink failure")
    adapter = AcpDuplexAdapter(runner=checked_agent_runner(Script()), workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(), outbound=RecordingOutboundChannel(), settlement_sink=sink)
    new = await adapter.handle_client_request({"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path)}})
    sid = new.response["result"]["sessionId"]
    request = {"jsonrpc": "2.0", "id": 2, "method": "session/prompt", "params": {
        "sessionId": sid, "prompt": [{"type": "text", "text": "Explain"}]}}
    if raised is asyncio.CancelledError:
        with pytest.raises(asyncio.CancelledError):
            await adapter.handle_client_request(request)
    else:
        await adapter.handle_client_request(request)
    assert len(calls) == 1 and sid not in adapter._active_turns
    assert calls[0].payload["conversation_commit"] == "committed"


async def test_chat_single_terminal_message_commits_only_after_flush(tmp_path, monkeypatch):
    h = ServerTurn(tmp_path, monkeypatch)
    await h.start()
    await h.adapter.handle_client_request({"jsonrpc": "2.0", "id": "mode", "method": "session/set_mode", "params": {
        "sessionId": h.session_id, "modeId": "chat"}})
    h.transport.hold = lambda m: m.get("params", {}).get("update", {}).get("sessionUpdate") == "agent_message_chunk"
    h.transport.release.clear()
    h.expect = {"settlement": "completed", "conversation_commit": "committed", "final_delivery": "flushed"}
    try:
        await h.prompt()
        await asyncio.wait_for(h.transport.entered.wait(), 3)
        assert not h.adapter._sessions.get(h.session_id).conversation.records
        assert not h.events
        h.transport.release.set()
        await asyncio.wait_for(h.settled.wait(), 3)
        assert not h.sink_errors
        finals = [m for m in h.transport.flushes if m.get("params", {}).get("update", {}).get("sessionUpdate") in {"agent_message_chunk", "plan"}]
        assert len(finals) == 1
    finally:
        await h.close()


def test_fail_closed_future_agrees_with_already_frozen_owner():
    class TeardownDuringClaim(TurnControl):
        def claim_write_started(self, key):
            if not self.transport_abandoned():
                self.request_transport_teardown()
                raise ValueError("failed after teardown")
            return super().claim_write_started(key)
    owner = TeardownDuringClaim(session_id="s", turn_seq=1)
    lease = owner.start_response_send()
    source = concurrent.futures.Future()
    class Unused:
        def write_bytes(self, data):
            raise AssertionError("unexpected write")
        def flush(self):
            raise AssertionError("unexpected flush")
    writer = DedicatedOutboundWriter(Unused())
    writer.start()
    try:
        writer.submit(OutboundQueueItem(payload={}, send_key=lease.send_key, owner=owner, source_future=source))
        assert source.result(timeout=3).outcome is SendOutcome.SUPPRESSED
    finally:
        writer.close_and_join()


def test_finalized_pending_sends_cannot_rewrite_authoritative_facts():
    control = TurnControl(session_id="s", turn_seq=1)
    control.seal_final_delivery()
    lease = control.start_terminal_message("final_text")
    snapshot = control.finalize_once()
    control.publish_authoritative(lease.send_key, SendOutcome.FLUSHED)
    assert control.final_delivery is snapshot.final_delivery
    assert control.send_slot(lease.send_key).diagnostic is SendOutcome.FLUSHED

def test_direct_completion_cannot_grant_a_late_physical_send():
    control = TurnControl(session_id="s", turn_seq=1)
    control.seal_final_delivery()
    control.finalize_once()
    assert not control.start_response_send().granted
    assert not control.start_terminal_message("late").granted


@pytest.mark.parametrize("typed_stop", [False, True])
async def test_safe_mcp_activity_keeps_terminal_text_and_settlement_gates(tmp_path, monkeypatch, typed_stop):
    audit = AgentToolCall(tool_name="mcp_call:lookup", summary="MCP call held.", authorization_outcome="HOLD")
    expected_text = "Cannot safely continue." if typed_stop else "Tool activity:\n- MCP call held."

    class RetainedMcpScript(Script):
        def run(self, request, **kwargs):
            return super().run(request, **kwargs).model_copy(update={
                "tool_calls": (audit,), "output_text": "Cannot safely continue." if typed_stop else "answer",
                "stop_reason": "PLANNING_MODEL_REFUSED" if typed_stop else None,
            })

    status = AgentRunStatus.FAILED if typed_stop else AgentRunStatus.COMPLETED
    h = ServerTurn(tmp_path, monkeypatch, RetainedMcpScript(status))
    terminal_entered, terminal_release = h.transport.entered, h.transport.release
    rpc_entered, rpc_release = asyncio.Event(), threading.Event()

    def hold(message):
        if message.get("id") == "prompt":
            h.transport.entered, h.transport.release = rpc_entered, rpc_release
            return True
        return message.get("params", {}).get("update", {}).get("sessionUpdate") == "agent_message_chunk"

    h.transport.hold = hold
    terminal_release.clear()
    h.expect = {"settlement": "failed" if typed_stop else "completed", "conversation_commit": "committed",
                "final_delivery": "flushed", "rpc_response_delivery": "flushed"}
    await h.start()
    try:
        await h.prompt()
        await asyncio.wait_for(terminal_entered.wait(), 3)
        assert not h.events
        conversation = h.adapter._sessions.get(h.session_id).conversation
        assert not conversation.records
        turn = h.adapter._active_turns[h.session_id]
        assert turn.turn_control.send_slot(TurnSendKey("terminal_set", "final_text")).authoritative is SendState.WRITE_STARTED
        terminal = h.transport.writes[-1]
        assert terminal["params"]["update"]["content"]["text"] == expected_text + AGENT_MESSAGE_BLOCK_SEPARATOR
        terminal_release.set()
        await asyncio.wait_for(rpc_entered.wait(), 3)
        assert not h.events and h.session_id in h.adapter._active_turns
        assert len(conversation.records) == 1
        assert conversation.records[turn.turn_seq].completion_text == expected_text
        assert terminal in h.transport.flushes
        rpc_release.set()
        await asyncio.wait_for(h.settled.wait(), 3)
        assert not h.sink_errors and len(h.events) == 1
        assert sum(message.get("id") == "prompt" for message in h.transport.writes) == 1
    finally:
        terminal_release.set()
        rpc_release.set()
        await h.close()
