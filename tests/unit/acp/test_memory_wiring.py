"""Plan 12.10 Task 4: how the ACP host wires one session's context index. The session and the client channel are test doubles; the adapter, its
turn handling and its retention are real. What the index itself does is proved in tests/unit/context and tests/integration/context."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest

from optimus.acp import spec
from optimus.acp.session_retention import RetirementReason, RetirementStatus, SessionCloseResult
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.context.memory_session import GroundingReport
from tests.support.contract_doubles import checked_agent_runner
from tests.unit.acp.test_context_engine_admission import Runner, make_attachment, new_session, prompt_request, rpc


class FakeTurn:
    def __init__(self, session: FakeSession, cancelled: Any) -> None:
        self.session = session
        self.cancelled = cancelled
        self.on_tool: Any = None
        self.read_buffer: Any = None

    def status(self) -> str:
        return self.session.state

    def ground(self, text: str) -> GroundingReport:
        self.session.grounded.append(text)
        return self.session.report


class FakeSession:
    def __init__(self) -> None:
        self.state = "Context index: building, 1 of 9 files."
        self.report = GroundingReport()
        self.started = 0
        self.stopped = 0
        self.turns: list[FakeTurn] = []
        self.grounded: list[str] = []

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1

    def turn(self, *, cancelled: Any) -> FakeTurn:
        self.turns.append(FakeTurn(self, cancelled))
        return self.turns[-1]


class MemoryRunner(Runner):
    """Does, on the same worker thread the real runner uses, whatever the test gives it."""

    def __init__(self, during: Any = None) -> None:
        super().__init__()
        self.during = during
        self.packers: list[Any] = []

    def run(self, request: Any, **kwargs: Any) -> Any:
        self.packers.append(kwargs.get("context_packer"))
        if self.during is not None:
            self.during(kwargs["context_packer"].memory)
        return super().run(request, **kwargs)


def _adapter(tmp_path: Path, factory: Any, *, runner: MemoryRunner | None = None, attached: bool = True) -> tuple[AcpDuplexAdapter, RecordingOutboundChannel]:
    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(
        runner=checked_agent_runner(runner or MemoryRunner()), workspace_root=tmp_path, sessions=InMemoryAcpSpecSessionStore(), outbound=outbound,
        context_attachment=make_attachment() if attached else None, memory_factory=factory,
    )
    return adapter, outbound


async def _initialize(adapter: AcpDuplexAdapter, capabilities: Any) -> None:
    params = {"protocolVersion": 1, **({} if capabilities is None else {"clientCapabilities": capabilities})}
    assert "result" in await rpc(adapter, {"jsonrpc": "2.0", "id": "i", "method": "initialize", "params": params})


async def _chat(adapter: AcpDuplexAdapter, session_id: str, request_id: str, text: str = "hello") -> dict[str, Any]:
    return await rpc(adapter, prompt_request(session_id, text, request_id))


def _updates(outbound: RecordingOutboundChannel) -> list[dict[str, Any]]:
    return [note["params"]["update"] for note in outbound.notifications if note["method"] == "session/update"]


def _texts(outbound: RecordingOutboundChannel) -> list[str]:
    return [update["content"]["text"] for update in _updates(outbound) if update.get("sessionUpdate") == "agent_message_chunk"]


def test_a_new_session_starts_its_index_for_its_own_workspace(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = FakeSession()
        opened: list[Path] = []

        def factory(workspace: Path) -> FakeSession:
            opened.append(workspace)
            return session

        adapter, _outbound = _adapter(tmp_path, factory)
        await new_session(adapter, tmp_path, mode="chat")
        assert opened == [tmp_path] and session.started == 1

    asyncio.run(scenario())


def test_a_workspace_with_no_index_is_an_ordinary_session(tmp_path: Path) -> None:
    async def scenario() -> None:
        adapter, outbound = _adapter(tmp_path, lambda workspace: None)
        session_id = await new_session(adapter, tmp_path, mode="chat")
        assert (await _chat(adapter, session_id, "p1"))["result"]["stopReason"] == "end_turn"
        assert not any("Context index" in text for text in _texts(outbound))

    asyncio.run(scenario())


def test_without_the_attached_context_no_index_is_opened(tmp_path: Path) -> None:
    """The index needs the attached path's budget and estimator, so the factory is never even called without them."""

    async def scenario() -> None:
        def factory(workspace: Path) -> None:
            raise AssertionError("opened without an attachment")

        adapter, _outbound = _adapter(tmp_path, factory, attached=False)
        await new_session(adapter, tmp_path, mode="chat")

    asyncio.run(scenario())


def test_a_turn_reaches_the_runner_with_its_index_and_cancel(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = FakeSession()
        runner = MemoryRunner()
        adapter, _outbound = _adapter(tmp_path, lambda workspace: session, runner=runner)
        session_id = await new_session(adapter, tmp_path, mode="chat")
        await _chat(adapter, session_id, "p1")
        assert runner.packers[0].memory is session.turns[0]
        assert session.turns[0].cancelled() is False

    asyncio.run(scenario())


def test_the_status_line_shows_only_when_the_state_changes(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = FakeSession()
        adapter, outbound = _adapter(tmp_path, lambda workspace: session)
        session_id = await new_session(adapter, tmp_path, mode="chat")
        await _chat(adapter, session_id, "p1")
        session.state = "Context index: building, 5 of 9 files."
        await _chat(adapter, session_id, "p2")  # the same state with newer counts
        session.state = "Context index: ready, 9 of 9 files."
        await _chat(adapter, session_id, "p3")
        shown = [text for text in _texts(outbound) if text.startswith("Context index")]
        assert shown == ["Context index: building, 1 of 9 files.\n\n", "Context index: ready, 9 of 9 files.\n\n"]

    asyncio.run(scenario())


def test_a_tool_gets_a_started_card_and_its_ending_on_one_id(tmp_path: Path) -> None:
    def during(memory: Any) -> None:
        memory.on_tool("tool-one", "started", "SEARCH", "first_function", "")
        memory.on_tool("tool-one", "completed", "SEARCH", "first_function", "3 lines in 4 ms")

    async def scenario() -> None:
        adapter, outbound = _adapter(tmp_path, lambda workspace: FakeSession(), runner=MemoryRunner(during))
        session_id = await new_session(adapter, tmp_path, mode="chat")
        await _chat(adapter, session_id, "p1")
        await asyncio.sleep(0)
        updates = _updates(outbound)
        started = next(update for update in updates if update.get("sessionUpdate") == "tool_call" and update["title"].startswith("SEARCH"))
        ended = next(update for update in updates if update.get("sessionUpdate") == "tool_call_update" and update["toolCallId"] == started["toolCallId"])
        assert started["toolCallId"] == "tool-one"  # the id its telemetry carries
        assert started["title"] == "SEARCH first_function" and started["status"] == "in_progress" and started["kind"] == "search"
        assert ended["status"] == "completed" and "3 lines in 4 ms" in str(ended["content"])

    asyncio.run(scenario())


@pytest.mark.parametrize(("tool", "kind"), [("SEARCH", "search"), ("OUTLINE", "read"), ("SYMBOLS", "search"), ("LIST", "read")])
def test_every_tool_has_a_kind_the_client_knows(tmp_path: Path, tool: str, kind: str) -> None:
    def during(memory: Any) -> None:
        memory.on_tool("tool-one", "started", tool, "x", "")
        memory.on_tool("tool-one", "completed", tool, "x", "1 line")

    async def scenario() -> None:
        adapter, outbound = _adapter(tmp_path, lambda workspace: FakeSession(), runner=MemoryRunner(during))
        session_id = await new_session(adapter, tmp_path, mode="chat")
        await _chat(adapter, session_id, "p1")
        await asyncio.sleep(0)
        assert next(update for update in _updates(outbound) if update.get("title", "").startswith(tool))["kind"] == kind

    asyncio.run(scenario())


def test_a_reply_citing_what_is_not_there_gets_a_card(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = FakeSession()
        session.report = GroundingReport(unresolved=("gone.py",))
        adapter, outbound = _adapter(tmp_path, lambda workspace: session)
        session_id = await new_session(adapter, tmp_path, mode="chat")
        await _chat(adapter, session_id, "p1")
        card = next(update for update in _updates(outbound) if update.get("title") == "grounding_check")
        assert "gone.py" in str(card)
        assert session.grounded == ["Answer 1."]

    asyncio.run(scenario())


def test_a_reply_with_nothing_to_report_gets_no_card(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = FakeSession()
        adapter, outbound = _adapter(tmp_path, lambda workspace: session)
        session_id = await new_session(adapter, tmp_path, mode="chat")
        await _chat(adapter, session_id, "p1")
        assert session.grounded == ["Answer 1."]
        assert not any(update.get("title") == "grounding_check" for update in _updates(outbound))

    asyncio.run(scenario())


def test_grounding_that_fails_never_fails_the_turn(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = FakeSession()

        def broken(text: str) -> GroundingReport:
            raise RuntimeError("the check broke")

        real_turn = session.turn

        def turn(*, cancelled: Any) -> FakeTurn:
            made = real_turn(cancelled=cancelled)
            made.ground = broken  # type: ignore[method-assign]
            return made

        session.turn = turn  # type: ignore[method-assign]
        adapter, outbound = _adapter(tmp_path, lambda workspace: session)
        session_id = await new_session(adapter, tmp_path, mode="chat")
        assert (await _chat(adapter, session_id, "p1"))["result"]["stopReason"] == "end_turn"
        assert "Answer 1." in "".join(_texts(outbound))

    asyncio.run(scenario())


def test_removing_a_session_pauses_its_index(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = FakeSession()
        adapter, _outbound = _adapter(tmp_path, lambda workspace: session)
        session_id = await new_session(adapter, tmp_path, mode="chat")
        assert session.stopped == 0
        adapter.retention.request_retire(session_id, reason=RetirementReason.EXPLICIT_REMOVE)
        await adapter.retention.wait_retired(session_id)
        assert session.stopped >= 1

    asyncio.run(scenario())


@pytest.mark.parametrize("capabilities", [None, {}, {"fs": {}}, {"fs": {"readTextFile": False}}, {"fs": {"readTextFile": "true"}}, {"fs": True}, "fs"])
def test_a_client_that_did_not_advertise_reading_is_never_asked(tmp_path: Path, capabilities: Any) -> None:
    async def scenario() -> None:
        session = FakeSession()
        adapter, outbound = _adapter(tmp_path, lambda workspace: session)
        await _initialize(adapter, capabilities)
        session_id = await new_session(adapter, tmp_path, mode="chat")
        await _chat(adapter, session_id, "p1")
        assert session.turns[0].read_buffer is None
        assert not any(request["method"] == "fs/read_text_file" for request in outbound.requests)

    asyncio.run(scenario())


def _reader_scenario(tmp_path: Path, answer: Any, *, seconds: float = 5.0) -> tuple[list[Any], list[dict[str, Any]]]:
    results: list[Any] = []
    seen: list[dict[str, Any]] = []

    def during(memory: Any) -> None:
        results.append(memory.read_buffer(str(tmp_path / "a.py")))

    async def scenario() -> None:
        adapter, outbound = _adapter(tmp_path, lambda workspace: FakeSession(), runner=MemoryRunner(during))
        await _initialize(adapter, {"fs": {"readTextFile": True}})
        session_id = await new_session(adapter, tmp_path, mode="chat")
        prompt = asyncio.create_task(_chat(adapter, session_id, "p1"))
        request = await asyncio.wait_for(outbound.wait_for_request("fs/read_text_file"), timeout=5)
        seen.append(request)
        answer(outbound, request)
        assert (await asyncio.wait_for(prompt, timeout=5))["result"]["stopReason"] == "end_turn"

    original = spec.BUFFER_READ_SECONDS
    spec.BUFFER_READ_SECONDS = seconds
    try:
        asyncio.run(scenario())
    finally:
        spec.BUFFER_READ_SECONDS = original
    return results, seen


def test_a_client_that_advertised_it_is_asked_for_that_file_in_that_session(tmp_path: Path) -> None:
    results, seen = _reader_scenario(tmp_path, lambda outbound, request: outbound.respond(request["id"], {"content": "unsaved text"}))
    assert results == ["unsaved text"]
    assert seen[0]["params"]["path"] == str(tmp_path / "a.py") and isinstance(seen[0]["params"]["sessionId"], str)


@pytest.mark.parametrize("reply", [{}, {"content": 3}, {"content": None}, "text"])
def test_a_malformed_reply_means_disk(tmp_path: Path, reply: Any) -> None:
    results, _seen = _reader_scenario(tmp_path, lambda outbound, request: outbound.respond(request["id"], reply))
    assert results == [None]


def test_a_refusal_means_disk_and_the_turn_goes_on(tmp_path: Path) -> None:
    results, _seen = _reader_scenario(tmp_path, lambda outbound, request: outbound._futures[request["id"]].set_exception(RuntimeError("refused")))
    assert results == [None]


def test_an_editor_that_never_answers_costs_one_wait_and_means_disk(tmp_path: Path) -> None:
    results, _seen = _reader_scenario(tmp_path, lambda outbound, request: None, seconds=0.05)
    assert results == [None]


def test_a_session_whose_cleanup_fails_still_stops_indexing(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = FakeSession()
        adapter, _outbound = _adapter(tmp_path, lambda workspace: session)
        session_id = await new_session(adapter, tmp_path, mode="chat")
        spec_session = adapter._sessions.get(session_id)

        async def fails(*_args: Any, **_kwargs: Any) -> Any:
            return SessionCloseResult(("CONTROLLED",), True)

        adapter.retention._close_session = fails
        adapter.retention.request_retire(session_id, reason=RetirementReason.EXPLICIT_REMOVE)
        result = await adapter.retention.wait_retired(session_id)
        assert result.status is RetirementStatus.QUARANTINED and spec_session is not None
        assert session.stopped == 1, "a quarantined session kept indexing"
        adapter.retention._entries.clear()

    asyncio.run(scenario())


def test_a_cancel_ends_the_wait_for_the_editor_at_once_and_takes_back_the_request(tmp_path: Path) -> None:
    results: list[Any] = []
    waited: list[float] = []

    def during(memory: Any) -> None:
        started = time.monotonic()
        results.append(memory.read_buffer(str(tmp_path / "a.py")))
        waited.append(time.monotonic() - started)

    async def scenario() -> None:
        adapter, outbound = _adapter(tmp_path, lambda workspace: FakeSession(), runner=MemoryRunner(during))
        await _initialize(adapter, {"fs": {"readTextFile": True}})
        session_id = await new_session(adapter, tmp_path, mode="chat")
        prompt = asyncio.create_task(_chat(adapter, session_id, "p1"))
        request = await asyncio.wait_for(outbound.wait_for_request("fs/read_text_file"), timeout=5)
        await adapter.handle_client_notification({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": session_id}})
        await asyncio.wait_for(prompt, timeout=5)
        await asyncio.sleep(0)
        assert outbound._futures[request["id"]].cancelled(), "the request is still waiting for a reply nobody wants"

    asyncio.run(scenario())
    assert results == [None] and waited[0] < 1.5
