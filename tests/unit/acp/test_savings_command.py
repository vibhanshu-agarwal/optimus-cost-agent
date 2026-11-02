"""Plan 12.9 Task 4: `/savings` in the ACP host (ADR-034, D1). Advertised after the session/new response, answered
locally before admission or classification, and never a turn: no conversation record, accounting epoch, model, tool
or classifier call. Cancellation, a concurrent prompt, a closing server and an outbound failure leave nothing late.
Reports come from the real Gateway handler over synthetic facts; no model is named."""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.usage import savings_report as sr
from optimus.usage.durable_capture import DurableCapture, host_outbox_root
from optimus_gateway import usage_price_snapshots
from optimus_gateway import usage_report as gateway_report
from optimus_security import durable_outbox as ob
from optimus_security import usage_capture_contract as uc
from optimus_security import usage_report_contract as urc
from tests.support.contract_doubles import checked_agent_runner
from tests.unit.acp.test_auto_turn_routing import Classifier, _router
from tests.unit.acp.test_context_engine_admission import Runner, new_session, prompt, prompt_request, rpc, session_of, texts
from tests.unit.optimus_gateway.test_usage_report import _facts, _references

_AT = datetime(2026, 11, 1, tzinfo=UTC)


class _Store:
    """A ledger answering every session with one session's facts (the Gateway scopes by the request's session)."""

    def __init__(self, gate: threading.Event | None = None) -> None:
        self.gate, self.calls = gate, 0

    def report_facts(self, session_id, turn_id, *, frontier, deadline, max_attempts, max_turns):
        self.calls += 1
        if self.gate is not None:
            self.gate.wait(10)
        return _facts()


@pytest.fixture(autouse=True)
def synthetic_references(monkeypatch):
    monkeypatch.setattr(usage_price_snapshots, "configured_references", lambda: _references(5))


def _gateway_post(store: Any):
    """The real Gateway handler as the host's transport: the report route's own parsing, cursors and validation."""
    config = SimpleNamespace(usage_store=store, shared_secret="host-key")  # pragma: allowlist secret

    def post(body: bytes):
        return gateway_report.handle_usage_report_request(raw_body=body, config=config)

    return post


def _adapter(tmp_path, *, store: Any = None, outbound=None, auto: bool = False, reports: Any = "default"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    outbound = outbound or RecordingOutboundChannel()
    runner = Runner()
    capture = DurableCapture(ob.OutboxWriter(host_outbox_root(tmp_path / "config")), ack_wait=5.0, clock=lambda: _AT)
    capture.enable_report_context()
    classifier = Classifier(["easy"])
    usage_reports = sr.SavingsReports(_gateway_post(store or _Store()), lambda s: (2, (("f" * 32, 9),))) if reports == "default" else reports
    adapter = AcpDuplexAdapter(
        runner=checked_agent_runner(runner), workspace_root=tmp_path, sessions=InMemoryAcpSpecSessionStore(capture=capture),
        outbound=outbound, auto_router=_router(classifier) if auto else None, usage_reports=usage_reports,
    )
    return SimpleNamespace(adapter=adapter, outbound=outbound, runner=runner, capture=capture, classifier=classifier)


def _capture_kinds(capture: DurableCapture) -> list[str]:
    capture.stop()
    return [] if not capture.writer.directory.exists() else [r.payload["kind"] for r in ob.scan_stream(capture.writer.directory).records]


# --- Advertising ---------------------------------------------------------------------------------------------------


async def test_the_command_is_advertised_only_after_the_session_new_response_and_only_when_reports_exist(tmp_path):
    with_reports, without = _adapter(tmp_path / "a"), _adapter(tmp_path / "b", reports=None)
    for case, root in ((with_reports, tmp_path / "a"), (without, tmp_path / "b")):
        response = await rpc(case.adapter, {"jsonrpc": "2.0", "id": "n", "method": "session/new", "params": {"cwd": str(root), "mcpServers": []}})
        case.before = len(case.outbound.notifications)  # what the response itself carried, sent before it
        await case.adapter.after_response("session/new", response)
        case.session_id = response["result"]["sessionId"]

    adverts = [n["params"] for n in with_reports.outbound.notifications[with_reports.before:]
               if n["params"]["update"]["sessionUpdate"] == "available_commands_update"]
    assert adverts == [{"sessionId": with_reports.session_id, "update": {"sessionUpdate": "available_commands_update",
                        "availableCommands": [{"name": "savings", "description": sr.COMMAND_DESCRIPTION, "input": {"hint": sr.COMMAND_HINT}}]}}]
    assert not any(n["params"]["update"]["sessionUpdate"] == "available_commands_update" for n in with_reports.outbound.notifications[:with_reports.before])
    assert not any(n["params"]["update"]["sessionUpdate"] == "available_commands_update" for n in without.outbound.notifications)
    await with_reports.adapter.after_response("session/new", {"error": {"code": -1}})  # a failed setup advertises nothing
    await with_reports.adapter.after_response("session/prompt", {"result": {"sessionId": with_reports.session_id}})
    assert len(adverts) == 1


# --- The command -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["agent", "chat"])
@pytest.mark.parametrize("auto", [False, True])
async def test_savings_answers_locally_and_is_never_a_turn(tmp_path, mode, auto):
    case = _adapter(tmp_path, auto=auto)
    session_id = await new_session(case.adapter, tmp_path, mode=mode)
    records_before = len(session_of(case.adapter, session_id).conversation.records) if session_of(case.adapter, session_id).conversation else 0

    response = await prompt(case.adapter, case.outbound, session_id, "/savings", "s1")

    assert response["result"]["stopReason"] == "end_turn"
    [report] = texts(case.outbound)
    assert report.startswith("## Usage and savings for this session") and urc.LABELS["b1"] in report
    assert case.runner.requests == [] and case.classifier.contracts == [], "no model, tool or classifier call"
    conversation = session_of(case.adapter, session_id).conversation
    assert (len(conversation.records) if conversation else 0) == records_before, "nothing enters the conversation"
    assert uc.EPOCH_BEGIN not in _capture_kinds(case.capture), "no accounting epoch"


@pytest.mark.parametrize("text", ["/savings please", "/savings turn", "/savings next nope"])
async def test_a_malformed_command_answers_usage_locally(tmp_path, text):
    case = _adapter(tmp_path)
    session_id = await new_session(case.adapter, tmp_path)

    response = await prompt(case.adapter, case.outbound, session_id, text, "s1")

    assert response["result"]["stopReason"] == "end_turn" and texts(case.outbound) == [sr.USAGE] and case.runner.requests == []


async def test_an_attachment_makes_the_command_malformed(tmp_path):
    case = _adapter(tmp_path)
    session_id = await new_session(case.adapter, tmp_path)
    request = prompt_request(session_id, "/savings", "s1")
    request["params"]["prompt"].append({"type": "resource_link", "uri": "file:///a.txt", "name": "a.txt"})

    response = await asyncio.wait_for(rpc(case.adapter, request), 5)

    assert response["result"]["stopReason"] == "end_turn" and texts(case.outbound) == [sr.USAGE]


async def test_an_unknown_command_or_an_unconfigured_host_keeps_existing_behavior(tmp_path):
    configured, unconfigured = _adapter(tmp_path / "a"), _adapter(tmp_path / "b", reports=None)
    for case, text, root in ((configured, "/save this", tmp_path / "a"), (unconfigured, "/savings", tmp_path / "b")):
        session_id = await new_session(case.adapter, root, mode="chat")
        await prompt(case.adapter, case.outbound, session_id, text, "p1")
        assert len(case.runner.requests) == 1, "an ordinary prompt"


async def test_an_unavailable_ledger_is_stated(tmp_path):
    class Down:
        def report_facts(self, *args, **kwargs):
            from optimus_gateway.usage_store import StoreError

            raise StoreError("unavailable")

    case = _adapter(tmp_path, store=Down())
    session_id = await new_session(case.adapter, tmp_path)

    await prompt(case.adapter, case.outbound, session_id, "/savings", "s1")

    assert texts(case.outbound) == [sr._FAILURES["LEDGER_UNAVAILABLE"]]  # noqa: SLF001


async def test_a_cursor_continues_only_its_own_session(tmp_path):
    case = _adapter(tmp_path)
    first, second = await new_session(case.adapter, tmp_path), await new_session(case.adapter, tmp_path)
    await prompt(case.adapter, case.outbound, first, "/savings", "s1")
    cursor = texts(case.outbound)[-1].split("`/savings next ")[1].split("`")[0]

    await prompt(case.adapter, case.outbound, first, f"/savings next {cursor}", "s2")
    await prompt(case.adapter, case.outbound, second, f"/savings next {cursor}", "s3")

    assert "References 4–5 of 5" in texts(case.outbound)[-2]
    assert texts(case.outbound)[-1] == sr._FAILURES["REPORT_CHANGED"]  # noqa: SLF001


async def test_a_plain_next_continues_this_sessions_last_report_and_only_while_it_has_more(tmp_path):
    case = _adapter(tmp_path)
    first, second = await new_session(case.adapter, tmp_path), await new_session(case.adapter, tmp_path)

    await prompt(case.adapter, case.outbound, first, "/savings next", "s1")
    assert texts(case.outbound)[-1] == sr.NOTHING_TO_CONTINUE

    await prompt(case.adapter, case.outbound, first, "/savings", "s2")
    await prompt(case.adapter, case.outbound, second, "/savings next", "s3")
    assert texts(case.outbound)[-1] == sr.NOTHING_TO_CONTINUE, "another session's report never continues here"

    await prompt(case.adapter, case.outbound, first, "/savings next", "s4")
    assert "References 4–5 of 5" in texts(case.outbound)[-1]

    await prompt(case.adapter, case.outbound, first, "/savings next", "s5")
    assert texts(case.outbound)[-1] == sr.NOTHING_TO_CONTINUE, "the last page offered nothing more"


# --- Lifecycle -------------------------------------------------------------------------------------------------------


async def _slow(tmp_path):
    gate = threading.Event()
    case = _adapter(tmp_path, store=_Store(gate))
    session_id = await new_session(case.adapter, tmp_path, mode="chat")  # a prompt that runs needs no approval
    task = asyncio.create_task(asyncio.wait_for(rpc(case.adapter, prompt_request(session_id, "/savings", "s1")), 15))
    for _ in range(100):
        await asyncio.sleep(0.01)
        if session_id in case.adapter._report_cancels:  # noqa: SLF001
            break
    return case, session_id, task, gate


async def test_a_cancel_ends_the_wait_and_nothing_late_is_sent(tmp_path):
    case, session_id, task, gate = await _slow(tmp_path)

    await case.adapter.handle_client_notification({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": session_id}})
    response = await asyncio.wait_for(task, 5)
    gate.set()
    await asyncio.sleep(0.3)  # the dropped read finishes in its thread

    assert response["result"]["stopReason"] == "cancelled" and texts(case.outbound) == []
    assert session_id not in case.adapter._report_cancels  # noqa: SLF001


async def test_a_prompt_during_a_report_is_refused_and_the_report_still_answers(tmp_path):
    case, session_id, task, gate = await _slow(tmp_path)

    refused = await asyncio.wait_for(rpc(case.adapter, prompt_request(session_id, "Hello?", "p1")), 5)
    gate.set()
    response = await asyncio.wait_for(task, 5)

    assert "error" in refused and case.runner.requests == []
    assert response["result"]["stopReason"] == "end_turn" and len(texts(case.outbound)) == 1


async def test_a_report_finishing_after_the_server_closed_sends_nothing(tmp_path):
    case, session_id, task, gate = await _slow(tmp_path)

    case.adapter._closed = True  # noqa: SLF001 - as close_all marks it, while the read is outstanding
    gate.set()  # the read then completes normally: no cancel arrives
    response = await asyncio.wait_for(task, 5)

    assert response["result"]["stopReason"] == "cancelled" and texts(case.outbound) == []


async def test_an_undeliverable_report_fails_its_own_request_only(tmp_path):
    class Failing(RecordingOutboundChannel):
        failed = False

        async def notify(self, method, params, *, require_flushed=False):
            if not self.failed and params.get("update", {}).get("sessionUpdate") == "agent_message_chunk":
                self.failed = True  # the report's chunk only
                raise ConnectionResetError("client gone")
            await super().notify(method, params, require_flushed=require_flushed)

    case = _adapter(tmp_path, outbound=Failing())
    session_id = await new_session(case.adapter, tmp_path, mode="chat")

    response = await asyncio.wait_for(rpc(case.adapter, prompt_request(session_id, "/savings", "s1")), 5)
    after = await prompt(case.adapter, case.outbound, session_id, "Hello?", "p2")

    assert response["error"]["message"] == "the usage report could not be delivered"
    assert session_id not in case.adapter._report_cancels and len(case.runner.requests) == 1  # noqa: SLF001
    assert after["result"]["stopReason"] == "end_turn"


async def test_on_the_wire_the_advertisement_follows_the_session_new_response(tmp_path):
    """The real stream server writes the session/new response first, then `available_commands_update`
    (zed-industries/zed#60199: Zed drops commands sent before it)."""
    from optimus.acp.server import AcpStreamServer
    from tests.integration.acp.test_server_stream import InteractiveLineReader, MemoryLineWriter, configured_test_agent_server

    configured = configured_test_agent_server(tmp_path, output_text="ok")
    server = AcpStreamServer(dispatcher=configured.server._dispatcher,  # noqa: SLF001
                             usage_reports=sr.SavingsReports(_gateway_post(_Store()), lambda s: (0, ())))
    reader, writer = InteractiveLineReader(), MemoryLineWriter()
    serving = asyncio.create_task(server.serve_ndjson(reader, writer))
    try:
        await reader.send({"jsonrpc": "2.0", "id": "n", "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}})
        response = await asyncio.wait_for(writer.wait_for_response("n"), 5)
        for _ in range(100):
            if any(m.get("params", {}).get("update", {}).get("sessionUpdate") == "available_commands_update" for m in writer.messages):
                break
            await asyncio.sleep(0.01)
    finally:
        reader.close()
        await asyncio.wait_for(serving, 5)

    order = [i for i, m in enumerate(writer.messages)
             if m is response or m.get("params", {}).get("update", {}).get("sessionUpdate") == "available_commands_update"]
    assert len(order) == 2 and writer.messages[order[0]] is response, "the response is written first"



# --- Checkpoint B round 94 ------------------------------------------------------------------------------------------


class _TurnStore(_Store):
    """A ledger holding one turn with ``rows`` requests."""

    def __init__(self, rows: int) -> None:
        super().__init__()
        self.rows = rows

    def report_facts(self, session_id, turn_id, *, frontier, deadline, max_attempts, max_turns):
        from tests.unit.optimus_gateway.test_usage_report import _payload

        self.calls += 1
        receipts = [(_payload(f"a{n:03d}", "t1"), False, False) for n in range(self.rows)]
        return _facts(receipts, epochs={"t1": ("complete",)}, selections={"t1": ("auto",)})


@pytest.mark.parametrize(("rows", "pages"), [(1, 2), (30, 3)])  # reference groups, then detail rows past one page
async def test_a_turn_report_continues_as_a_turn_report(tmp_path, rows, pages):
    case = _adapter(tmp_path, store=_TurnStore(rows))
    session_id = await new_session(case.adapter, tmp_path, mode="chat")

    await prompt(case.adapter, case.outbound, session_id, "/savings turn t1", "s1")
    for n in range(pages - 1):
        cursor = texts(case.outbound)[-1].split("`/savings next ")[1].split("`")[0]
        await prompt(case.adapter, case.outbound, session_id, f"/savings next {cursor}", f"s{n + 2}")

    reports = texts(case.outbound)
    assert len(reports) == pages and all(r.startswith("## Usage and savings for turn t1") for r in reports), reports[-1][:200]
    assert "/savings next" not in reports[-1]
    shown = [line for r in reports for line in r.splitlines() if line.startswith("| t1 |")]
    assert len(shown) == rows


class _Parked(RecordingOutboundChannel):
    """A writer that parks the report's chunk, before (queued) or after (already writing) its write begins."""

    def __init__(self, *, started: bool) -> None:
        super().__init__()
        self.started, self.parked, self.release = started, asyncio.Event(), asyncio.Event()

    async def notify(self, method, params, *, require_flushed=False):
        if params.get("update", {}).get("sessionUpdate") != "agent_message_chunk":
            return await super().notify(method, params, require_flushed=require_flushed)
        if self.started:
            await super().notify(method, params, require_flushed=require_flushed)  # the write begins and lands
        self.parked.set()
        await self.release.wait()
        if not self.started:
            await super().notify(method, params, require_flushed=require_flushed)  # the queued write, reached later


@pytest.mark.parametrize(("started", "stop_reason", "shown"), [
    (False, "cancelled", 0),  # queued behind a blocked writer: the cancel suppresses it
    (True, "end_turn", 1),  # already being written: the write is authoritative
])
async def test_a_cancel_during_delivery_suppresses_an_unwritten_report_only(tmp_path, started, stop_reason, shown):
    case = _adapter(tmp_path, outbound=_Parked(started=started))
    session_id = await new_session(case.adapter, tmp_path, mode="chat")
    task = asyncio.create_task(asyncio.wait_for(rpc(case.adapter, prompt_request(session_id, "/savings", "s1")), 15))
    await asyncio.wait_for(case.outbound.parked.wait(), 5)

    await case.adapter.handle_client_notification({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": session_id}})
    await asyncio.sleep(0.05)
    case.outbound.release.set()
    response = await task

    assert response["result"]["stopReason"] == stop_reason and len(texts(case.outbound)) == shown


async def test_an_ambiguous_send_on_the_real_channel_is_never_a_successful_report(tmp_path):
    from optimus.acp.server import NdjsonOutboundChannel

    class Breaks:
        async def write_line(self, message):
            if message.get("params", {}).get("update", {}).get("sessionUpdate") == "agent_message_chunk":
                raise ConnectionResetError("the pipe broke mid-write")

    case = _adapter(tmp_path, outbound=NdjsonOutboundChannel(Breaks()))
    session_id = await new_session(case.adapter, tmp_path, mode="chat")

    response = await asyncio.wait_for(rpc(case.adapter, prompt_request(session_id, "/savings", "s1")), 5)

    assert response["error"]["message"] == "the usage report could not be delivered"


async def test_a_report_that_cannot_finish_in_time_says_so(tmp_path, monkeypatch):
    from optimus.acp import spec as spec_module

    monkeypatch.setattr(spec_module, "SAVINGS_WAIT_SECONDS", 0.2)
    gate = threading.Event()
    case = _adapter(tmp_path, store=_Store(gate))
    session_id = await new_session(case.adapter, tmp_path, mode="chat")
    try:
        response = await asyncio.wait_for(rpc(case.adapter, prompt_request(session_id, "/savings", "s1")), 5)
    finally:
        gate.set()

    assert response["result"]["stopReason"] == "end_turn" and texts(case.outbound) == [spec_module.SAVINGS_TIMEOUT_TEXT]



async def test_a_report_succeeds_only_on_a_confirmed_flush(tmp_path):
    class Records(RecordingOutboundChannel):
        required: list[bool] = []

        async def notify(self, method, params, *, require_flushed=False):
            if params.get("update", {}).get("sessionUpdate") == "agent_message_chunk":
                self.required.append(require_flushed)
            await super().notify(method, params, require_flushed=require_flushed)

    case = _adapter(tmp_path, outbound=Records())
    session_id = await new_session(case.adapter, tmp_path, mode="chat")

    await prompt(case.adapter, case.outbound, session_id, "/savings", "s1")

    assert case.outbound.required == [True], "a suppressed or ambiguous send raises on the real channel"



async def test_a_report_never_reaches_a_session_whose_retirement_began(tmp_path):
    """Checkpoint B pass 2 finding 3: the report's own lease keeps the entry while retirement is pending, so retirement is
    read from the retention state, and the session retires once the report's custody is released."""
    from optimus.acp.session_retention import RetirementReason

    case, session_id, task, gate = await _slow(tmp_path)

    case.adapter.retention.request_retire(session_id, reason=RetirementReason.EXPLICIT_REMOVE)
    gate.set()
    response = await task
    for _ in range(100):
        if case.adapter._sessions.get(session_id) is None:  # noqa: SLF001
            break
        await asyncio.sleep(0.01)

    assert response["result"]["stopReason"] == "cancelled" and texts(case.outbound) == []
    assert not case.adapter.retention.is_active(session_id) and case.adapter._sessions.get(session_id) is None  # noqa: SLF001


async def test_after_the_client_hangs_up_a_queued_report_is_never_written(tmp_path):
    """Checkpoint B pass 2 finding 2, on the real stream server and its dedicated writer: the report's chunk waits behind
    a blocked write, the client hangs up (EOF), teardown cancels the request, and the writer is then released. The
    report's chunk is never written."""
    import json as json_module

    from optimus.acp.admission import AdmissionLimits
    from optimus.acp.outbound_writer import DedicatedOutboundWriter
    from optimus.acp.server import AcpStreamServer
    from tests.integration.acp.test_server_stream import InteractiveLineReader, MemoryLineWriter, configured_test_agent_server
    from tests.unit.acp.test_outbound_writer import ControllableTransport

    fetched = threading.Event()

    def post(body: bytes):
        status, reply = _gateway_post(_Store())(body)
        fetched.set()
        return status, reply

    configured = configured_test_agent_server(tmp_path, output_text="ok")
    server = AcpStreamServer(dispatcher=configured.server._dispatcher,  # noqa: SLF001
                             usage_reports=sr.SavingsReports(post, lambda s: (0, ())))
    transport = ControllableTransport()
    writer = DedicatedOutboundWriter(transport, limits=AdmissionLimits())
    writer.start()
    reader = InteractiveLineReader()
    serving = asyncio.create_task(server.serve_ndjson(reader, MemoryLineWriter(), dedicated_writer=writer, join_dedicated_writer=False))

    def written() -> list[dict]:
        return [json_module.loads(line) for chunk in list(transport.writes) for line in chunk.decode("utf-8").splitlines() if line]

    async def until(predicate) -> None:
        for _ in range(500):
            if predicate():
                return
            await asyncio.sleep(0.01)
        raise AssertionError("timed out")

    try:
        await reader.send({"jsonrpc": "2.0", "id": "init", "method": "initialize", "params": {"protocolVersion": 1}})
        await reader.send({"jsonrpc": "2.0", "id": "new", "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}})
        await until(lambda: any(m.get("id") == "new" for m in written()))
        session_id = next(m for m in written() if m.get("id") == "new")["result"]["sessionId"]
        await until(lambda: any(m.get("params", {}).get("update", {}).get("sessionUpdate") == "available_commands_update" for m in written()))

        transport.allow_write.clear()  # the next physical write blocks, and everything after it queues
        transport.write_entered.clear()
        await reader.send({"jsonrpc": "2.0", "id": "mode", "method": "session/set_mode", "params": {"sessionId": session_id, "modeId": "chat"}})
        await asyncio.to_thread(transport.write_entered.wait, 5)
        await reader.send({"jsonrpc": "2.0", "id": "s1", "method": "session/prompt",
                           "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "/savings"}]}})
        assert await asyncio.to_thread(fetched.wait, 5)
        await asyncio.sleep(0.2)  # the report's chunk is now queued behind the blocked write

        reader.close()  # the client hangs up
        await asyncio.wait_for(serving, 10)
    finally:
        transport.allow_write.set()
        await asyncio.sleep(0.3)  # the writer drains what is still queued
        writer.close_and_join()

    chunks = [m for m in written() if m.get("params", {}).get("update", {}).get("sessionUpdate") == "agent_message_chunk"]
    assert not any("Usage and savings" in c["params"]["update"]["content"]["text"] for c in chunks), "nothing late"



async def test_a_queued_report_is_not_written_once_its_session_starts_retiring(tmp_path):
    """The writer asks the report's send owner at the moment of writing: a session that began retiring while the chunk
    waited in the queue gets nothing, with no cancel involved."""
    from optimus.acp.session_retention import RetirementReason

    case = _adapter(tmp_path, outbound=_Parked(started=False))
    session_id = await new_session(case.adapter, tmp_path, mode="chat")
    task = asyncio.create_task(asyncio.wait_for(rpc(case.adapter, prompt_request(session_id, "/savings", "s1")), 15))
    await asyncio.wait_for(case.outbound.parked.wait(), 5)

    case.adapter.retention.request_retire(session_id, reason=RetirementReason.EXPLICIT_REMOVE)
    case.outbound.release.set()
    response = await task

    assert response["result"]["stopReason"] == "cancelled" and texts(case.outbound) == []



async def test_a_cancelled_request_never_writes_its_queued_report_and_keeps_custody_of_the_send(tmp_path):
    """The request task itself is cancelled (no session/cancel, no server close) while its chunk is queued: the unwritten
    report is suppressed, and its send stays in the adapter's custody until it completes."""
    case = _adapter(tmp_path, outbound=_Parked(started=False))
    session_id = await new_session(case.adapter, tmp_path, mode="chat")
    task = asyncio.create_task(rpc(case.adapter, prompt_request(session_id, "/savings", "s1")))
    await asyncio.wait_for(case.outbound.parked.wait(), 5)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(case.adapter._report_sends) == 1, "held until the send completes"  # noqa: SLF001
    case.outbound.release.set()
    for _ in range(100):
        if not case.adapter._report_sends:  # noqa: SLF001
            break
        await asyncio.sleep(0.01)

    assert texts(case.outbound) == [] and not case.adapter._report_sends  # noqa: SLF001
