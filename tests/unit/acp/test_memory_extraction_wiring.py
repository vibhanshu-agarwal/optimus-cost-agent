"""Plan 12.11 Task 3: how the ACP host hands a delivered turn to the session's memory extractor. The adapter, its turn handling,
settlement and retention are real; the extractor is a recording double (the real one is proved in tests/unit/context)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from optimus.acp.session_retention import RetirementReason
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.context.maintenance import SummarizerResponse
from optimus.context.memory_extraction import Decision, TurnInput
from tests.support.contract_doubles import checked_agent_runner
from tests.unit.acp.test_context_engine_admission import Runner, make_attachment, new_session, prompt_request, rpc


class RecordingExtractor:
    def __init__(self, *, fail: bool = False) -> None:
        self.submitted: list[TurnInput] = []
        self.closed = 0
        self.fail = fail

    def submit(self, turn: TurnInput) -> tuple[Decision, Decision]:
        if self.fail:
            raise RuntimeError("extractor broke")
        self.submitted.append(turn)
        return Decision(True, "test"), Decision(False, "test")

    def close(self, timeout: float = 5.0) -> None:
        self.closed += 1


def _summarizer(*, prompt: str, max_output_tokens: int, purpose: str | None = None) -> SummarizerResponse:
    return SummarizerResponse(text=None, finish_status=None, attempts=())


def _adapter(tmp_path: Path, factory: Any, *, attached: bool = True) -> AcpDuplexAdapter:
    return AcpDuplexAdapter(
        runner=checked_agent_runner(Runner()), workspace_root=tmp_path, sessions=InMemoryAcpSpecSessionStore(), outbound=RecordingOutboundChannel(),
        context_attachment=make_attachment(summarizer=_summarizer) if attached else None, memory_extractor_factory=factory,
    )


def test_a_delivered_turn_reaches_the_extractor_with_its_own_words_and_the_turn_s_hooks(tmp_path: Path) -> None:
    async def scenario() -> None:
        extractor = RecordingExtractor()
        opened: list[tuple[Path, dict[str, Any]]] = []

        def factory(workspace: Path, **kwargs: Any) -> RecordingExtractor:
            opened.append((workspace, kwargs))
            return extractor

        adapter = _adapter(tmp_path, factory)
        session_id = await new_session(adapter, tmp_path, mode="chat")
        assert "result" in await rpc(adapter, prompt_request(session_id, "From now on we use uv everywhere.", "p-1"))
        (workspace, kwargs), = opened
        assert workspace == tmp_path and kwargs["session_id"] == session_id and set(kwargs) == {"settlement", "sanitize", "session_id", "report"}
        (turn,) = extractor.submitted
        assert turn.turn_id == f"{session_id}:1" and turn.scope == "project" and turn.trusted
        assert [(block.block, block.text) for block in turn.blocks] == [(f"{session_id}:1:user", "From now on we use uv everywhere.")]
        assert turn.work is None and turn.call is _summarizer and turn.record is not None
        assert all("From now on we use uv everywhere." not in source for source in turn.sources)  # the user's own words are no source

    asyncio.run(scenario())


def test_without_the_attached_context_no_extractor_is_opened(tmp_path: Path) -> None:
    async def scenario() -> None:
        def factory(workspace: Path, **kwargs: Any) -> None:
            raise AssertionError("opened without an attachment")

        adapter = _adapter(tmp_path, factory, attached=False)
        await new_session(adapter, tmp_path, mode="chat")

    asyncio.run(scenario())


def test_an_extractor_that_fails_never_fails_the_turn(tmp_path: Path) -> None:
    async def scenario() -> None:
        adapter = _adapter(tmp_path, lambda workspace, **kwargs: RecordingExtractor(fail=True))
        session_id = await new_session(adapter, tmp_path, mode="chat")
        reply = await rpc(adapter, prompt_request(session_id, "We always tag releases.", "p-1"))
        assert reply["result"]["stopReason"] == "end_turn"

    asyncio.run(scenario())


def test_a_workspace_without_an_extractor_runs_its_turns_unchanged(tmp_path: Path) -> None:
    async def scenario() -> None:
        adapter = _adapter(tmp_path, lambda workspace, **kwargs: None)  # unregistered or untrusted: memory stays read-only
        session_id = await new_session(adapter, tmp_path, mode="chat")
        assert (await rpc(adapter, prompt_request(session_id, "We always tag releases.", "p-1")))["result"]["stopReason"] == "end_turn"

    asyncio.run(scenario())


def test_removing_a_session_closes_its_extractor(tmp_path: Path) -> None:
    async def scenario() -> None:
        extractor = RecordingExtractor()
        adapter = _adapter(tmp_path, lambda workspace, **kwargs: extractor)
        session_id = await new_session(adapter, tmp_path, mode="chat")
        adapter.retention.request_retire(session_id, reason=RetirementReason.EXPLICIT_REMOVE)
        await adapter.retention.wait_retired(session_id)
        assert extractor.closed >= 1

    asyncio.run(scenario())
