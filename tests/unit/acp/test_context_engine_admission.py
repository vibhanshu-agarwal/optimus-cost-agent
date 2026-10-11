"""Plan 12.2 Task 9: attached-engine admission in the ACP host (design spec 4.2, 7, 8; Task 1 contracts 5).

An attached session keeps its storage class through any engine fault. A healthy turn gets a view; an
unavailable one is checked by a pure floor probe over the full history plus the provisional prompt:
at most 524288 bytes falls back to full history with a notice, anything larger is refused with zero
planning/answer calls and the thread stays OPEN. Genuine source exhaustion and indeterminate delivery
keep their dispositions; a reservation shortfall is recoverable. Settings are captured before any await,
a cancelled turn dispatches and publishes nothing, and the current prompt never enters a checkpoint.
"""

from __future__ import annotations

import asyncio
import dataclasses
import threading
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from context_engine import PreparedView, StrategyParameters, ViewLimits
from context_engine.engine import ContextEngine
from context_engine.summary import PROMPT_VERSION, SECTIONS, SUMMARY_FORMAT, WRAPPER_OPEN
from optimus.acp.conversation import (
    CONVERSATION_MAX_BYTES,
    ConversationDisposition,
    ConversationOutcome,
)
from optimus.acp.settlement import EffectState
from optimus.acp.shapes import AGENT_MESSAGE_BLOCK_SEPARATOR
from optimus.acp.spec import (
    ATTACHED_STORAGE_REFUSAL_TEXT,
    CONTEXT_FALLBACK_TEXT,
    CONTEXT_RESERVATION_TEXT,
    CONTEXT_UNAVAILABLE_ENDING,
    CONTEXT_UNAVAILABLE_TEXTS,
    AcpDuplexAdapter,
    InMemoryAcpSpecSessionStore,
    RecordingOutboundChannel,
    context_unavailable_text,
)
from optimus.agent.models import AgentRunResult, AgentRunStatus
from optimus.context.assembly import ContextAttachment, SummarizerRoute, probe_floor
from optimus.context.maintenance import SummarizerAttempt, SummarizerResponse
from optimus.runtime.modes import ExecutionMode


def estimate(text: str) -> int:
    return (len(text.encode("utf-8")) + 3) // 4


SUMMARY = "\n".join(f"## {name}\nNone." for name in SECTIONS)


class SummarizerCall:
    """The injected summarizer: records each prompt; may run a hook inside the call."""

    def __init__(self, text: str = SUMMARY, *, during=None) -> None:
        self.text = text
        self.prompts: list[str] = []
        self._during = during

    def __call__(self, *, prompt: str, max_output_tokens: int) -> SummarizerResponse:
        self.prompts.append(prompt)
        if self._during is not None:
            self._during()
        n = len(self.prompts)
        attempt = SummarizerAttempt(attempt_id=f"s{n}", gateway_request_id=f"gw-s{n}", outcome="completed", cost_usd=Decimal("0.0001"))
        return SummarizerResponse(text=self.text, finish_status="stop", attempts=(attempt,))


class FlakyEngine:
    """Unavailable, for `reason`, for the first `failures` turns, then the real engine."""

    def __init__(self, failures: int, reason: str = "maintenance failed") -> None:
        self.failures = failures
        self.reason = reason
        self.calls = 0

    def prepare_view(self, snapshot, **kwargs) -> PreparedView:
        self.calls += 1
        if self.calls <= self.failures:
            return PreparedView((), (), None, snapshot.protected, (), (), False, self.reason)
        return ContextEngine().prepare_view(snapshot, **kwargs)


def make_attachment(
    *,
    engine: Any = None,
    summarizer: SummarizerCall | None = None,
    source_max: int = 2_000_000,
    reservation: int = 0,
    tail: int = 30,
    receipts: list | None = None,
) -> ContextAttachment:
    return ContextAttachment(
        engine=engine if engine is not None else ContextEngine(),
        parameters=StrategyParameters(
            anchor_input_tokens=200,
            compaction_tail_input_tokens=tail,
            hybrid_tail_input_tokens=tail,
            summary_output_tokens=300,
            max_maintenance_calls=4,
            prompt_version=PROMPT_VERSION,
            format_version=SUMMARY_FORMAT,
        ),
        limits=ViewLimits(
            history_input_tokens=4000,
            source_max_bytes=source_max,
            transient_max_bytes=source_max,
            maintenance_input_tokens=400_000,
            maintenance_output_tokens=300,
            summary_max_bytes=1200,  # floor(300 / 0.25) for this ceil(bytes / 4) estimator
            estimate_history=estimate,
            estimator_id="utf8-bytes-div-4-test",
        ),
        source_max_bytes=source_max,
        record_reservation_bytes=reservation,
        usable_input_tokens=500_000,
        estimate_request=estimate,
        registry_hash="e" * 64,
        model_id="test/planner",
        summarizer=(lambda identity, deliver_notice: summarizer) if summarizer is not None else None,
        summarizer_route=SummarizerRoute(
            model_id="test/summarizer", role="summarizer", route=("provider-a",), reasoning=None, quantizations=("fp8",)
        ),
        record_receipt=(receipts if receipts is not None else []).append,
        max_repacks=2,
    )


class Runner:
    """Records every request and its runtime kwargs; answers Chat, plans Agent."""

    def __init__(self, *, plan_text: str = "WRITE example.py\ncontent") -> None:
        self.requests: list[Any] = []
        self.kwargs: list[dict[str, Any]] = []
        self.plan_text = plan_text

    def run(self, request, **kwargs):
        self.requests.append(request)
        self.kwargs.append(kwargs)
        common = dict(run_id=request.run_id, session_id=request.session_id, tool_calls=(), mutation_count=0, provider_keys_resolvable=())
        if request.execution_mode is ExecutionMode.CHAT:
            return AgentRunResult(
                execution_mode=ExecutionMode.CHAT, status=AgentRunStatus.COMPLETED, final_state="CHAT_ONLY",
                output_text=f"Answer {len(self.requests)}.", total_cost_usd=Decimal("0.001"), **common,
            )  # fmt: skip
        if not request.approval.approved:
            return AgentRunResult(
                execution_mode=ExecutionMode.AGENT, status=AgentRunStatus.AWAITING_APPROVAL, final_state="AWAITING_APPROVAL",
                output_text=self.plan_text, total_cost_usd=Decimal("0.002"), plan_hash="hash-1",
                candidate_plan_text=self.plan_text, **common,
            )  # fmt: skip
        return AgentRunResult(
            execution_mode=ExecutionMode.AGENT, status=AgentRunStatus.COMPLETED, final_state="COMPLETED",
            output_text="done", total_cost_usd=Decimal("0.002"), plan_hash="hash-1", **common,
        )  # fmt: skip

    def planning(self) -> list[Any]:
        return [r for r in self.requests if not r.approval.approved]


def make_adapter(tmp_path: Path, attachment: ContextAttachment | None, runner: Runner | None = None):
    outbound = RecordingOutboundChannel()
    runner = runner or Runner()
    adapter = AcpDuplexAdapter(
        runner=runner,
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=outbound,
        context_attachment=attachment,
    )
    return adapter, outbound, runner


async def rpc(adapter: AcpDuplexAdapter, request: dict[str, Any]) -> dict[str, Any]:
    return (await adapter.handle_client_request(request)).response


async def new_session(adapter: AcpDuplexAdapter, tmp_path: Path, *, mode: str = "agent") -> str:
    result = (await rpc(adapter, {"jsonrpc": "2.0", "id": "new", "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}}))["result"]
    session_id = result["sessionId"]
    if mode != "agent":
        set_mode = {"jsonrpc": "2.0", "id": "m", "method": "session/set_mode", "params": {"sessionId": session_id, "modeId": mode}}
        assert "result" in await rpc(adapter, set_mode)
    return session_id


def prompt_request(session_id: str, text: str, request_id: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "method": "session/prompt", "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": text}]}}


async def prompt(adapter, outbound, session_id, text, request_id, *, approve=False) -> dict[str, Any]:
    task = asyncio.create_task(rpc(adapter, prompt_request(session_id, text, request_id)))
    if approve:
        permission = await asyncio.wait_for(outbound.wait_for_request("session/request_permission"), timeout=5)
        outbound.respond(permission["id"], {"outcome": {"outcome": "selected", "optionId": "approve"}})
        outbound.requests.clear()
    return await asyncio.wait_for(task, timeout=5)


def texts(outbound: RecordingOutboundChannel) -> list[str]:
    updates = [n["params"]["update"] for n in outbound.notifications if n["method"] == "session/update"]
    chunks = [u["content"]["text"] for u in updates if u["sessionUpdate"] == "agent_message_chunk"]
    return [chunk.removesuffix(AGENT_MESSAGE_BLOCK_SEPARATOR) for chunk in chunks]


def session_of(adapter: AcpDuplexAdapter, session_id: str):
    return adapter._sessions.get(session_id)  # noqa: SLF001


def commit_record(conversation, text: str) -> None:
    seq = conversation.allocate_turn_seq()
    decision = conversation.prepare_commit(
        seq,
        sanitized_user_prompt="history",
        sanitized_plan_text="",
        sanitized_completion_text=text,
        outcome=ConversationOutcome.COMPLETED,
        effect_state=EffectState.NONE,
    )
    conversation.commit_after_final_flush(decision)


# --- Request shapes ----------------------------------------------------------------------------


async def test_absent_agent_keeps_the_full_envelope_in_its_task(tmp_path):
    adapter, outbound, runner = make_adapter(tmp_path, None)
    session_id = await new_session(adapter, tmp_path)
    await prompt(adapter, outbound, session_id, "First", "p1", approve=True)
    conversation = session_of(adapter, session_id).conversation
    envelope = conversation.planner_envelope()

    await prompt(adapter, outbound, session_id, "Second", "p2", approve=True)

    request = runner.planning()[-1]
    assert request.task == f"{envelope}\nSecond"
    assert request.conversation_envelope == ""
    assert request.selection_text is None and request.context_digest is None
    assert "context_packer" not in runner.kwargs[-2]
    assert session_of(adapter, session_id).context_strategy is None


async def test_absent_chat_keeps_its_separate_envelope(tmp_path):
    adapter, outbound, runner = make_adapter(tmp_path, None)
    session_id = await new_session(adapter, tmp_path, mode="chat")
    await prompt(adapter, outbound, session_id, "First", "p1")
    envelope = session_of(adapter, session_id).conversation.planner_envelope()

    await prompt(adapter, outbound, session_id, "Second", "p2")

    request = runner.requests[-1]
    assert (request.task, request.conversation_envelope) == ("Second", envelope)
    assert request.selection_text is None and request.context_digest is None


@pytest.mark.parametrize("mode", ["chat", "agent"])
async def test_attached_requests_split_prompt_selection_and_history(tmp_path, mode):
    summarizer = SummarizerCall()
    adapter, outbound, runner = make_adapter(tmp_path, make_attachment(summarizer=summarizer))
    session_id = await new_session(adapter, tmp_path, mode=mode)
    for n in range(3):
        await prompt(adapter, outbound, session_id, f"Earlier prompt {n}", f"p{n}", approve=mode == "agent")

    await prompt(adapter, outbound, session_id, "The current prompt", "now", approve=mode == "agent")

    request = runner.planning()[-1]
    assert request.task == "The current prompt"
    assert request.execution_mode is (ExecutionMode.CHAT if mode == "chat" else ExecutionMode.AGENT)
    assert WRAPPER_OPEN in request.conversation_envelope  # the inert summary is model history
    assert request.selection_text.startswith("The current prompt")
    assert "## Task context" not in request.selection_text  # never the summary
    assert "Earlier prompt 2" in request.selection_text  # the exact tail
    assert "Earlier prompt 0" not in request.selection_text  # a summarized turn
    assert len(request.context_digest) == 64
    assert runner.kwargs[runner.requests.index(request)]["context_packer"] is not None
    assert session_of(adapter, session_id).context_strategy == "compaction"


# --- The pure floor probe ------------------------------------------------------------------------


def test_probe_floor_measures_full_history_plus_the_provisional_prompt_without_mutating():
    from optimus.acp.conversation import ConversationSanitizer, ConversationSanitizerInputs, ConversationState

    conversation = ConversationState(ConversationSanitizer(ConversationSanitizerInputs(known_secrets=(), path_aliases=(), known_pii=())))
    commit_record(conversation, "x" * 1000)
    records = dict(conversation.records)

    floor = probe_floor(conversation.records, "next prompt", turn_seq=2)

    assert floor == conversation.prepare_admission("next prompt").projected_bytes
    assert dict(conversation.records) == records
    assert probe_floor(conversation.records, "next prompt") == floor  # the next sequence by default


async def _session_at_floor(tmp_path, *, failures: int, prompt_bytes: int):
    """An attached sliding session whose next prompt projects exactly `prompt_bytes` floor bytes."""
    engine = FlakyEngine(failures)
    adapter, outbound, runner = make_adapter(tmp_path, make_attachment(engine=engine))
    session_id = await new_session(adapter, tmp_path, mode="chat")
    session = session_of(adapter, session_id)
    session.context_strategy = "sliding_window"  # sliding needs no summarizer
    conversation = session.conversation
    # Space-separated filler: the shared sanitizer is quadratic on one long unbroken token (an existing
    # owner's item, P11-REMEDIATION-SECURITY-TEXT-POLICY), and an attached snapshot re-sanitizes history.
    commit_record(conversation, ("history " * CONVERSATION_MAX_BYTES)[: CONVERSATION_MAX_BYTES - 2000])
    base = probe_floor(conversation.records, "")
    text = "p" * (prompt_bytes - base)
    assert probe_floor(conversation.records, text) == prompt_bytes
    return adapter, outbound, runner, session_id, conversation, engine, text


async def test_an_unavailable_engine_at_exactly_the_floor_falls_back_to_full_history(tmp_path):
    adapter, outbound, runner, session_id, conversation, _, text = await _session_at_floor(tmp_path, failures=1, prompt_bytes=CONVERSATION_MAX_BYTES)

    response = await prompt(adapter, outbound, session_id, text, "p1")

    assert response["result"]["stopReason"] == "end_turn"
    assert len(runner.requests) == 1
    request = runner.requests[0]
    assert "history " * 100 in request.conversation_envelope  # full history, not a view
    assert texts(outbound)[0] == CONTEXT_FALLBACK_TEXT.format(strategy="sliding window")
    assert conversation.disposition is ConversationDisposition.OPEN


async def test_unavailable_engine_refusals_above_the_floor_stay_open_until_a_healthy_view(tmp_path):
    adapter, outbound, runner, session_id, conversation, engine, text = await _session_at_floor(
        tmp_path, failures=3, prompt_bytes=CONVERSATION_MAX_BYTES + 1
    )
    records_before = dict(conversation.records)

    for n in range(3):
        outbound.notifications.clear()
        response = await prompt(adapter, outbound, session_id, text, f"r{n}")
        assert response["result"]["stopReason"] == "end_turn"
        assert texts(outbound) == [context_unavailable_text("maintenance failed", "sliding window")]
        assert conversation.disposition is ConversationDisposition.OPEN
        assert runner.requests == []  # zero planning/answer calls
        assert dict(conversation.records) == records_before  # nothing evicted, nothing committed

    response = await prompt(adapter, outbound, session_id, text, "healthy")

    assert response["result"]["stopReason"] == "end_turn"
    assert len(runner.requests) == 1 and engine.calls == 4
    assert conversation.disposition is ConversationDisposition.OPEN


async def test_genuine_source_exhaustion_is_not_overridden_by_a_healthy_engine(tmp_path):
    adapter, outbound, runner = make_adapter(tmp_path, make_attachment(source_max=4096))
    session_id = await new_session(adapter, tmp_path, mode="chat")
    conversation = session_of(adapter, session_id).conversation

    response = await prompt(adapter, outbound, session_id, "x" * 5000, "big")
    assert response["result"]["stopReason"] == "end_turn"
    assert conversation.disposition is ConversationDisposition.CAP_CLOSED

    outbound.notifications.clear()
    response = await prompt(adapter, outbound, session_id, "small", "small")

    assert response["result"]["stopReason"] == "end_turn"
    assert texts(outbound) == [ATTACHED_STORAGE_REFUSAL_TEXT]  # names storage (Task 10)
    assert runner.requests == []


async def test_delivery_indeterminate_is_not_overridden_by_a_healthy_engine(tmp_path):
    adapter, outbound, runner = make_adapter(tmp_path, make_attachment())
    session_id = await new_session(adapter, tmp_path, mode="chat")
    session_of(adapter, session_id).conversation.latch_delivery_indeterminate()

    response = await prompt(adapter, outbound, session_id, "hello", "p1")

    assert response["result"]["stopReason"] == "refusal"
    assert runner.requests == []


async def test_a_reservation_shortfall_is_recoverable(tmp_path):
    adapter, outbound, runner = make_adapter(tmp_path, make_attachment(source_max=4096, reservation=1000))
    session_id = await new_session(adapter, tmp_path, mode="chat")
    conversation = session_of(adapter, session_id).conversation

    response = await prompt(adapter, outbound, session_id, "x" * 3500, "big")

    assert response["result"]["stopReason"] == "end_turn"
    assert texts(outbound) == [CONTEXT_RESERVATION_TEXT]
    assert conversation.disposition is ConversationDisposition.OPEN
    assert runner.requests == []

    await prompt(adapter, outbound, session_id, "short", "short")
    assert len(runner.requests) == 1


def test_an_attached_session_measures_its_warning_against_its_own_source_class(tmp_path):
    adapter, _, _ = make_adapter(tmp_path, make_attachment(source_max=10_000))

    async def run() -> None:
        session_id = await new_session(adapter, tmp_path, mode="chat")
        conversation = session_of(adapter, session_id).conversation
        assert conversation.source_max_bytes == 10_000
        admission = conversation.prepare_admission("y" * 8100)
        assert admission.admitted and admission.crosses_warning

    asyncio.run(run())


# --- Growth, cancellation and fallback ------------------------------------------------------------


async def test_a_cancel_during_maintenance_dispatches_and_publishes_nothing_but_keeps_receipts(tmp_path):
    entered, release = threading.Event(), threading.Event()

    def block() -> None:
        entered.set()
        assert release.wait(5)

    receipts: list = []
    summarizer = SummarizerCall()
    adapter, outbound, runner = make_adapter(tmp_path, make_attachment(summarizer=summarizer, receipts=receipts))
    session_id = await new_session(adapter, tmp_path, mode="chat")
    for n in range(3):
        await prompt(adapter, outbound, session_id, f"Earlier prompt {n}", f"p{n}")
    session = session_of(adapter, session_id)
    checkpoint_before = session.context_checkpoint
    calls_before, receipts_before = len(runner.requests), len(receipts)
    summarizer._during = block  # noqa: SLF001

    task = asyncio.create_task(rpc(adapter, prompt_request(session_id, "Cancel me", "c1")))
    assert await asyncio.to_thread(entered.wait, 5)
    await adapter.handle_client_notification({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": session_id}})
    release.set()
    response = await asyncio.wait_for(task, timeout=5)

    assert response["result"]["stopReason"] == "cancelled"
    assert len(runner.requests) == calls_before  # no planning/answer dispatch
    assert session.context_checkpoint is checkpoint_before  # nothing published
    assert len(receipts) == receipts_before + 1  # the summarizer attempt still settles
    record = session.conversation.records[max(session.conversation.records)]
    assert record.user_prompt == "Cancel me" and record.outcome is ConversationOutcome.CANCELLED


async def test_a_missing_summarizer_uses_the_stated_fallback(tmp_path):
    adapter, outbound, runner = make_adapter(tmp_path, make_attachment(summarizer=None))
    session_id = await new_session(adapter, tmp_path, mode="chat")
    for n in range(3):
        await prompt(adapter, outbound, session_id, f"Earlier prompt {n}", f"p{n}")
    outbound.notifications.clear()

    await prompt(adapter, outbound, session_id, "Now", "now")

    assert texts(outbound)[0] == CONTEXT_FALLBACK_TEXT.format(strategy="compaction")
    request = runner.requests[-1]
    assert all(f"Earlier prompt {n}" in request.conversation_envelope for n in range(3))
    assert WRAPPER_OPEN not in request.conversation_envelope


async def test_no_current_prompt_enters_a_checkpoint_and_receipts_carry_the_route(tmp_path):
    receipts: list = []
    summarizer = SummarizerCall()
    adapter, outbound, runner = make_adapter(tmp_path, make_attachment(summarizer=summarizer, receipts=receipts))
    session_id = await new_session(adapter, tmp_path, mode="chat")
    for n in range(3):
        await prompt(adapter, outbound, session_id, f"Earlier prompt {n}", f"p{n}")

    await prompt(adapter, outbound, session_id, "UNIQUE-CURRENT-PROMPT", "now")

    session = session_of(adapter, session_id)
    assert summarizer.prompts and all("UNIQUE-CURRENT-PROMPT" not in p for p in summarizer.prompts)
    checkpoint = session.context_checkpoint
    assert checkpoint is not None
    current_seq = max(session.conversation.records)
    assert max(checkpoint.covered_turn_ids) < current_seq
    assert checkpoint.revision.last_committed_seq < current_seq
    identity = receipts[-1].identity
    assert (identity.session_id, identity.model_id, identity.role, identity.route, identity.quantizations) == (
        session_id, "test/summarizer", "summarizer", ("provider-a",), ("fp8",),
    )  # fmt: skip
    assert identity.turn_seq == current_seq and identity.strategy == "compaction"


async def test_a_published_checkpoint_is_reused_by_the_next_turn(tmp_path):
    summarizer = SummarizerCall()
    adapter, outbound, _ = make_adapter(tmp_path, make_attachment(summarizer=summarizer))
    session_id = await new_session(adapter, tmp_path, mode="chat")
    for n in range(4):
        await prompt(adapter, outbound, session_id, f"Earlier prompt {n}", f"p{n}")
    calls = len(summarizer.prompts)

    await prompt(adapter, outbound, session_id, "Next", "next")

    assert len(summarizer.prompts) == calls + 1
    assert "prior summary:" in summarizer.prompts[-1]  # merged, not rebuilt from source


async def test_settings_are_captured_before_the_warning_await(tmp_path):
    """A setter that runs while the turn awaits its first notice changes the next turn only."""
    adapter, outbound, runner = make_adapter(tmp_path, make_attachment(source_max=10_000, summarizer=SummarizerCall()))
    session_id = await new_session(adapter, tmp_path, mode="chat")
    session = session_of(adapter, session_id)
    original_notify = outbound.notify

    async def notify(method, params, *, require_flushed=False):
        session.context_strategy = "sliding_window"
        await original_notify(method, params, require_flushed=require_flushed)

    outbound.notify = notify  # type: ignore[method-assign]
    await prompt(adapter, outbound, session_id, "y" * 8100, "warn")  # crosses 80% of 10_000

    request = runner.requests[-1]
    assert request.context_digest is not None
    assert session.context_strategy == "sliding_window"
    assert runner.kwargs[-1]["context_packer"].admitted.strategy == "compaction"


async def test_a_plan_too_large_for_its_record_fails_before_approval(tmp_path):
    runner = Runner(plan_text="WRITE example.py\n" + "z" * 6000)
    adapter, outbound, _ = make_adapter(tmp_path, make_attachment(source_max=4096), runner)
    session_id = await new_session(adapter, tmp_path)

    response = await prompt(adapter, outbound, session_id, "Make a big change", "p1")

    assert response["result"]["stopReason"] == "end_turn"
    assert [r for r in outbound.requests if r["method"] == "session/request_permission"] == []
    assert len(runner.requests) == 1  # never applied
    conversation = session_of(adapter, session_id).conversation
    record = conversation.records[1]
    assert record.outcome is ConversationOutcome.FAILED and record.plan_text == ""
    assert record.effect_state is EffectState.NONE
    assert conversation.disposition is ConversationDisposition.OPEN


@pytest.mark.parametrize(
    ("field", "value"),
    [("source_max_bytes", 0), ("record_reservation_bytes", -1), ("record_reservation_bytes", 2_000_000), ("usable_input_tokens", 0), ("initial_strategy", "auto")],
)
def test_the_attachment_rejects_an_invalid_configuration(field, value):
    with pytest.raises(ValueError):
        dataclasses.replace(make_attachment(), **{field: value})


async def test_an_engine_that_raises_is_an_unavailable_view_not_a_closed_thread(tmp_path):
    class BrokenEngine:
        def prepare_view(self, snapshot, **kwargs):
            raise RuntimeError("engine defect")

    adapter, outbound, runner = make_adapter(tmp_path, make_attachment(engine=BrokenEngine()))
    session_id = await new_session(adapter, tmp_path, mode="chat")

    response = await prompt(adapter, outbound, session_id, "hello", "p1")

    assert response["result"]["stopReason"] == "end_turn"
    assert texts(outbound)[0] == CONTEXT_FALLBACK_TEXT.format(strategy="compaction")
    assert len(runner.requests) == 1  # under the floor: full history, and the thread stays OPEN
    assert session_of(adapter, session_id).conversation.disposition is ConversationDisposition.OPEN


# --- Fable CP3 review fixes -------------------------------------------------------------------------


class _LongReplyRunner(Runner):
    """Plans a plan that fits, then applies it with a long reply (many write summaries)."""

    def run(self, request, **kwargs):
        result = super().run(request, **kwargs)
        if not request.approval.approved:
            return result
        from optimus.agent.models import AgentToolCall

        calls = tuple(AgentToolCall(tool_name="write_file", summary=f"wrote module_{n}.py with its new docstrings and type hints") for n in range(14))
        # As production application does (runner._apply_stored_plan), the applied result carries the plan.
        return result.model_copy(update={"tool_calls": calls, "mutation_count": len(calls), "candidate_plan_text": self.plan_text})


async def test_a_plan_that_fits_keeps_its_record_within_storage_by_shortening_only_the_reply(tmp_path):
    from optimus.acp.conversation import COMPLETION_TRUNCATION_MARKER, rendered_byte_length

    runner = _LongReplyRunner(plan_text="WRITE example.py\n" + "plan line\n" * 130)
    adapter, outbound, _ = make_adapter(tmp_path, make_attachment(source_max=4096, reservation=800), runner)
    session_id = await new_session(adapter, tmp_path)
    conversation = session_of(adapter, session_id).conversation
    commit_record(conversation, ("history " * 400)[:2200])
    assert conversation.plan_fits(2, sanitized_user_prompt="Make a big change", sanitized_plan_text=runner.plan_text)

    response = await prompt(adapter, outbound, session_id, "Make a big change", "p1", approve=True)

    assert response["result"]["stopReason"] == "end_turn"
    record = conversation.records[2]
    assert record.outcome is ConversationOutcome.COMPLETED and record.plan_text.endswith("plan line\n")  # the plan is kept whole
    assert record.completion_text.endswith(COMPLETION_TRUNCATION_MARKER)  # only the reply message is shortened
    assert rendered_byte_length(conversation.records) <= 4096
    assert conversation.disposition is ConversationDisposition.OPEN


async def test_a_plan_whose_result_could_not_be_kept_fails_before_approval(tmp_path):
    runner = Runner(plan_text="WRITE example.py\n" + "plan line\n" * 170)
    adapter, outbound, _ = make_adapter(tmp_path, make_attachment(source_max=4096, reservation=800), runner)
    session_id = await new_session(adapter, tmp_path)
    conversation = session_of(adapter, session_id).conversation
    commit_record(conversation, ("history " * 400)[:2200])
    assert not conversation.plan_fits(2, sanitized_user_prompt="Make a big change", sanitized_plan_text=runner.plan_text)

    response = await prompt(adapter, outbound, session_id, "Make a big change", "p1")

    assert response["result"]["stopReason"] == "end_turn"
    assert [r for r in outbound.requests if r["method"] == "session/request_permission"] == []
    assert conversation.records[2].outcome is ConversationOutcome.FAILED and conversation.records[2].plan_text == ""


async def test_storage_no_prompt_can_use_is_exhaustion_and_closes_the_thread(tmp_path):
    from optimus.acp.spec import ATTACHED_STORAGE_REFUSAL_TEXT

    adapter, outbound, runner = make_adapter(tmp_path, make_attachment(source_max=4096, reservation=1000))
    session_id = await new_session(adapter, tmp_path, mode="chat")
    conversation = session_of(adapter, session_id).conversation
    commit_record(conversation, ("history " * 400)[:3100])  # even an empty prompt leaves no room for a reply

    response = await prompt(adapter, outbound, session_id, "x", "p1")

    assert response["result"]["stopReason"] == "end_turn"
    assert texts(outbound) == [ATTACHED_STORAGE_REFUSAL_TEXT]
    assert conversation.disposition is ConversationDisposition.CAP_CLOSED
    assert runner.requests == []


async def test_a_conflicting_summary_receipt_is_an_integrity_error_never_a_silent_fallback(tmp_path):
    from optimus.usage.turn_settlement import ReceiptConflictError

    class ReusedIdentity(SummarizerCall):
        def __call__(self, *, prompt: str, max_output_tokens: int) -> SummarizerResponse:
            self.prompts.append(prompt)
            attempt = SummarizerAttempt(attempt_id="same-id", gateway_request_id="gw-same", outcome="completed", cost_usd=Decimal("0.0001"))
            return SummarizerResponse(text=self.text, finish_status="stop", attempts=(attempt,))

    adapter, outbound, runner = make_adapter(tmp_path, make_attachment(summarizer=ReusedIdentity()))
    session_id = await new_session(adapter, tmp_path, mode="chat")
    for n in range(3):
        await prompt(adapter, outbound, session_id, f"Earlier prompt {n}", f"p{n}")  # turn 3 records "same-id"
    calls = len(runner.requests)

    with pytest.raises(ReceiptConflictError):
        await prompt(adapter, outbound, session_id, "Next", "next")  # turn 4 claims it again

    assert len(runner.requests) == calls  # nothing dispatched on a broken ledger


# --- Reason-specific refusals (CP4 correction C1) -------------------------------------------------
#
# Codex's final corrections (2026-10-04) fix one message per known engine reason. The expected texts
# are spelled out here, not read back from the module, so a wording change is a visible test change.

_ENDING = "This thread stays open. No answer or plan was requested for this prompt."
_SLIDING_OR_NEW = "Choose Sliding window to continue with less ordinary conversation history, or start a new thread."
_RETRYABLE = (
    "The compaction summary could not be completed or accepted. Retrying may help and may incur another "
    "summarization charge. You can also choose Sliding window to continue with less ordinary conversation history."
)
EXPECTED_REFUSALS = {
    "turn exceeds maintenance input": (
        "An earlier turn is too large for compaction to summarize with the current limits. "
        f"{_SLIDING_OR_NEW} Sliding window may omit all ordinary history if even the newest turn does not fit."
    ),
    "exact authority exceeds history capacity": (
        "The recorded execution outcomes and approval facts exceed this thread's context allowance. Start a new "
        "thread; changing context strategy will not make those required facts smaller."
    ),
    "history capacity too small for a summary": (
        f"The compaction summary and required history do not fit this thread's context allowance. {_SLIDING_OR_NEW}"
    ),
    "maintenance input exceeded": (
        f"The compaction strategy cannot summarize this history within its input or call limits. {_SLIDING_OR_NEW}"
    ),
    "maintenance allowance exceeded": (
        f"The compaction strategy cannot summarize this history within its input or call limits. {_SLIDING_OR_NEW}"
    ),
    "maintenance failed": _RETRYABLE,
    "summary malformed": _RETRYABLE,
    "summary exceeds bound": _RETRYABLE,
    "maintenance unavailable": (
        "Summarization is unavailable with this thread's current model and settings. Choose Sliding window to "
        "continue with less ordinary conversation history, or retry after summarization becomes available."
    ),
    "source exceeds limit": "The stored conversation exceeds the context engine's source limit. Start a new thread.",
}
_UNKNOWN = (
    "The compaction context strategy could not prepare this conversation. You can try Sliding window with less "
    "ordinary conversation history, or start a new thread."
)


@pytest.mark.parametrize("reason", sorted(EXPECTED_REFUSALS))
def test_each_known_reason_has_its_fixed_message_and_the_common_ending(reason):
    assert CONTEXT_UNAVAILABLE_ENDING == _ENDING
    assert context_unavailable_text(reason, "compaction") == f"{EXPECTED_REFUSALS[reason]} {_ENDING}"


@pytest.mark.parametrize("reason", [None, "", "engine fault", "cancelled", "a reason nobody wrote yet"])
def test_an_unknown_reason_gets_the_generic_message_never_the_reason_itself(reason):
    text = context_unavailable_text(reason, "compaction")
    assert text == f"{_UNKNOWN} {_ENDING}"
    if reason:
        assert reason not in text


def test_every_reason_the_engine_can_give_has_a_message():
    """A new engine reason must get a fixed message: parsed from the engine's own raise sites."""
    import re

    import context_engine.engine as engine_module

    source = Path(engine_module.__file__).read_text(encoding="utf-8")
    raised = set(re.findall(r'_Unavailable\("([^"]+)"\)', source)) - {"cancelled"}  # cancel has its own path
    raised |= {"summary exceeds bound", "summary malformed"}  # returned by _text_rejection, then raised
    assert raised == set(CONTEXT_UNAVAILABLE_TEXTS) == set(EXPECTED_REFUSALS)


def test_the_fallback_notice_does_not_claim_the_history_was_already_sent():
    assert CONTEXT_FALLBACK_TEXT.format(strategy="compaction") == (
        "The compaction context strategy is unavailable for this prompt. The full conversation history will be "
        "used if it fits the model's request limit."
    )


async def _compaction_session_over_floor(tmp_path, attachment: ContextAttachment):
    """An attached compaction Chat session holding one ~522 KB turn, whose next prompt projects one byte
    over the 524288-byte floor, so an unavailable view is refused rather than falling back."""
    adapter, outbound, runner = make_adapter(tmp_path, attachment)
    session_id = await new_session(adapter, tmp_path, mode="chat")
    conversation = session_of(adapter, session_id).conversation
    # Space-separated filler: the shared sanitizer is quadratic on one long unbroken token
    # (P11-REMEDIATION-SECURITY-TEXT-POLICY).
    commit_record(conversation, ("history " * CONVERSATION_MAX_BYTES)[: CONVERSATION_MAX_BYTES - 2000])
    text = "p" * (CONVERSATION_MAX_BYTES + 1 - probe_floor(conversation.records, ""))
    assert probe_floor(conversation.records, text) == CONVERSATION_MAX_BYTES + 1
    return adapter, outbound, runner, session_id, conversation, text


async def test_an_oversized_earlier_turn_is_refused_with_its_recovery_and_recurs_unchanged(tmp_path):
    summarizer = SummarizerCall()
    attachment = make_attachment(summarizer=summarizer)
    # The one ~130,000-token turn cannot enter a 100,000-token maintenance input.
    attachment = dataclasses.replace(attachment, limits=dataclasses.replace(attachment.limits, maintenance_input_tokens=100_000))
    adapter, outbound, runner, session_id, conversation, text = await _compaction_session_over_floor(tmp_path, attachment)
    records_before = dict(conversation.records)

    for n in range(2):  # a deterministic capacity reason recurs while nothing changes
        outbound.notifications.clear()
        response = await prompt(adapter, outbound, session_id, text, f"r{n}")
        assert response["result"]["stopReason"] == "end_turn"
        assert texts(outbound) == [f"{EXPECTED_REFUSALS['turn exceeds maintenance input']} {_ENDING}"]
        assert conversation.disposition is ConversationDisposition.OPEN
        assert runner.requests == []  # zero planning/answer dispatch
        assert summarizer.prompts == []  # refused before any maintenance call
        assert dict(conversation.records) == records_before  # the refused prompt is not committed


async def test_a_missing_summarizer_is_unavailable_not_a_failure_to_retry(tmp_path):
    adapter, outbound, runner, session_id, conversation, text = await _compaction_session_over_floor(
        tmp_path, make_attachment(summarizer=None)
    )

    for n in range(2):
        outbound.notifications.clear()
        response = await prompt(adapter, outbound, session_id, text, f"r{n}")
        assert response["result"]["stopReason"] == "end_turn"
        assert texts(outbound) == [f"{EXPECTED_REFUSALS['maintenance unavailable']} {_ENDING}"]
        assert "Retrying may help" not in texts(outbound)[0]
        assert conversation.disposition is ConversationDisposition.OPEN
        assert runner.requests == []


async def test_an_unsupported_summary_prompt_version_is_unavailable_with_zero_provider_calls(tmp_path):
    receipts: list = []
    summarizer = SummarizerCall()
    attachment = make_attachment(summarizer=summarizer, receipts=receipts)
    attachment = dataclasses.replace(attachment, parameters=dataclasses.replace(attachment.parameters, prompt_version="summary-prompt-v0"))
    adapter, outbound, runner, session_id, conversation, text = await _compaction_session_over_floor(tmp_path, attachment)

    response = await prompt(adapter, outbound, session_id, text, "r0")

    assert response["result"]["stopReason"] == "end_turn"
    assert texts(outbound) == [f"{EXPECTED_REFUSALS['maintenance unavailable']} {_ENDING}"]
    assert summarizer.prompts == [] and receipts == []  # the host refused the version before any provider call
    assert runner.requests == []


async def test_a_rejected_summary_keeps_its_receipt_and_claims_no_absence_of_model_activity(tmp_path):
    receipts: list = []
    summarizer = SummarizerCall(text="not a context-summary-v1 summary")
    adapter, outbound, runner, session_id, conversation, text = await _compaction_session_over_floor(
        tmp_path, make_attachment(summarizer=summarizer, receipts=receipts)
    )

    response = await prompt(adapter, outbound, session_id, text, "r0")

    assert response["result"]["stopReason"] == "end_turn"
    assert texts(outbound) == [f"{EXPECTED_REFUSALS['summary malformed']} {_ENDING}"]
    assert len(summarizer.prompts) == 1 and len(receipts) == 1  # the paid attempt is kept
    assert "Nothing was sent" not in texts(outbound)[0]
    assert runner.requests == []
    assert conversation.disposition is ConversationDisposition.OPEN


async def test_an_unknown_engine_reason_reaches_the_user_only_as_the_generic_message(tmp_path):
    engine = FlakyEngine(failures=1, reason="a reason nobody wrote yet")
    adapter, outbound, runner, session_id, conversation, text = await _compaction_session_over_floor(
        tmp_path, make_attachment(engine=engine)
    )

    response = await prompt(adapter, outbound, session_id, text, "r0")

    assert response["result"]["stopReason"] == "end_turn"
    assert texts(outbound) == [f"{_UNKNOWN} {_ENDING}"]
    assert "a reason nobody wrote yet" not in texts(outbound)[0]
    assert runner.requests == []
