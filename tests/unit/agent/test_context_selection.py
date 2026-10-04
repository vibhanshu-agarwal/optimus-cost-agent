"""Plan 12.2 Task 9: exact selection, separate from model history (design spec 7; Task 1 contracts 5).

An attached turn has three inputs. The current prompt is the task. The selection text (current prompt,
exact head/tail turns, every protected record) drives workspace files and skills. The rendered view
(including an inert summary) is model history only. Summary text and omitted turns never select a file
or skill, so a follow-up that refers only to dropped context gets no file hint: a disclosed limitation,
not full-history selection.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from context_engine import (
    MaintenanceRequest,
    MaintenanceResult,
    PreparedView,
    StrategyParameters,
    ViewLimits,
)
from context_engine.engine import ContextEngine
from context_engine.summary import PROMPT_VERSION, SECTIONS, SUMMARY_FORMAT, WRAPPER_OPEN
from optimus.acp.conversation import (
    INERT_PLAN_OPEN,
    ConversationOutcome,
    ConversationSanitizer,
    ConversationSanitizerInputs,
    ConversationTurn,
)
from optimus.acp.settlement import EffectState
from optimus.agent.models import AgentRunRequest
from optimus.agent.runner import AgentRunner
from optimus.context.adapter import ApprovalDecision, ApprovalFact, make_history_snapshot
from optimus.context.assembly import build_selection_text, render_context_view
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.runtime.modes import ExecutionMode

SANITIZER = ConversationSanitizer(ConversationSanitizerInputs(known_secrets=(), path_aliases=(), known_pii=()))


def estimate(text: str) -> int:
    return (len(text.encode("utf-8")) + 3) // 4


def summary_text(*lines: str) -> str:
    body = {name: "None." for name in SECTIONS}
    if lines:
        body["Constraints and changes"] = "\n".join(lines)
    return "\n".join(f"## {name}\n{body[name]}" for name in SECTIONS)


def parameters(*, tail: int = 60, hybrid_tail: int = 80, calls: int = 4) -> StrategyParameters:
    return StrategyParameters(
        anchor_input_tokens=200,
        compaction_tail_input_tokens=tail,
        hybrid_tail_input_tokens=hybrid_tail,
        summary_output_tokens=300,
        max_maintenance_calls=calls,
        prompt_version=PROMPT_VERSION,
        format_version=SUMMARY_FORMAT,
    )


def limits(history: int = 2000) -> ViewLimits:
    return ViewLimits(
        history_input_tokens=history,
        source_max_bytes=1_000_000,
        transient_max_bytes=1_000_000,
        maintenance_input_tokens=4000,
        maintenance_output_tokens=300,
        summary_max_bytes=1200,  # floor(300 / 0.25) for this ceil(bytes / 4) estimator
        estimate_history=estimate,
        estimator_id="utf8-bytes-div-4-test",
    )


class FakeSummarizer:
    def __init__(self, text: str) -> None:
        self.text = text
        self.requests: list[MaintenanceRequest] = []

    def __call__(self, request: MaintenanceRequest) -> MaintenanceResult:
        self.requests.append(request)
        return MaintenanceResult(summary_text=self.text, attempt_ids=(f"a{len(self.requests)}",), status="completed", finish_status="stop")


def turn(prompt: str, plan: str = "", completion: str = "Done.") -> ConversationTurn:
    return ConversationTurn(
        user_prompt=prompt,
        plan_text=plan,
        completion_text=completion,
        outcome=ConversationOutcome.COMPLETED,
        effect_state=EffectState.COMPLETE if plan else EffectState.NONE,
    )


RECORDS = {
    1: turn("Round with old_calc.py everywhere; keep HALF_UP.", plan="WRITE old_calc.py\nrounding = 'HALF_UP'"),
    2: turn("Also add type hints to old_calc.py please, and docstrings for every public function."),
    3: turn("Correction: the rounding rule now lives in new_calc.py, use HALF_EVEN there."),
}
APPROVALS = {1: (ApprovalFact(turn_seq=1, artifact_hash="a" * 64, decision=ApprovalDecision.GRANTED),)}


def exact_budget(snap, *newest: int) -> int:
    """A history budget that holds every protected record and exactly the given newest turns."""
    from context_engine.selection import render_ordinary_turn, render_protected_state

    by_seq = {t.seq: t for t in snap.turns}
    authority = sum(estimate(render_protected_state(state)) for state in snap.protected)
    return authority + sum(estimate(render_ordinary_turn(by_seq[seq])) for seq in newest) + 1


def snapshot(records=RECORDS, approvals=APPROVALS):
    return make_history_snapshot(session_key="session-1", generation=len(records), records=records, approvals=approvals, sanitizer=SANITIZER)


def compaction_view(summarizer: FakeSummarizer, records=RECORDS) -> tuple[object, PreparedView]:
    snap = snapshot(records)
    view = ContextEngine().prepare_view(
        snap,
        strategy="compaction",
        parameters=parameters(),
        limits=limits(),
        checkpoint=None,
        maintenance=summarizer,
        cancelled=lambda: False,
    )
    assert view.available, view.reason
    assert view.covered_turn_ids and view.tail_turn_ids, view
    return snap, view


# --- Rendering and selection ------------------------------------------------------------------


def test_selection_holds_the_prompt_exact_turns_and_every_protected_record_but_no_summary():
    summarizer = FakeSummarizer(summary_text("Rounding moved; summary mentions invented.py."))
    snap, view = compaction_view(summarizer)

    selection = build_selection_text("Now fix new_calc.py", snap, view)

    assert selection.startswith("Now fix new_calc.py")
    assert "Correction: the rounding rule now lives in new_calc.py" in selection  # exact tail
    assert "invented.py" not in selection  # summary text never selects
    assert "Round with old_calc.py" not in selection  # a summarized turn's ordinary text
    assert "a" * 64 in selection  # every protected record, including summarized turns
    for seq in snap.ids:
        assert f'"seq":{seq}' in selection


def test_the_rendered_view_wraps_the_summary_inert_and_keeps_plans_inert():
    summarizer = FakeSummarizer(summary_text("Use HALF_EVEN; HALF_UP is superseded."))
    snap, view = compaction_view(summarizer)

    rendered = render_context_view(snap, view)

    assert WRAPPER_OPEN in rendered and 'trust="untrusted-summary"' in rendered
    assert "HALF_UP is superseded." in rendered
    assert "Correction: the rounding rule now lives in new_calc.py" in rendered
    # Every protected record is present, exact, for summarized turns too.
    for state in snap.protected:
        assert json.dumps({"seq": state.seq, "outcome": state.outcome, "effect_state": state.effect_state, "approval_facts": list(state.approval_facts)}, ensure_ascii=False, separators=(",", ":")) in rendered
    # The manifest says which turns are exact, summarized or omitted.
    assert "summarized turns: 1, 2" in rendered and "exact turns: 3" in rendered


def test_a_pinned_hybrid_head_keeps_its_plan_inert():
    summarizer = FakeSummarizer(summary_text("Docstrings were requested."))
    snap = snapshot()
    view = ContextEngine().prepare_view(
        snap,
        strategy="hybrid",
        parameters=parameters(tail=40, hybrid_tail=40),
        limits=limits(),
        checkpoint=None,
        maintenance=summarizer,
        cancelled=lambda: False,
    )
    assert view.head_turn_ids == (1,), view

    rendered = render_context_view(snap, view)

    assert f"{INERT_PLAN_OPEN}WRITE old_calc.py" in rendered
    assert "WRITE old_calc.py" in build_selection_text("next", snap, view)  # a pinned head is exact


def test_sliding_omits_older_turns_from_both_history_and_selection():
    snap = snapshot()
    view = ContextEngine().prepare_view(
        snap,
        strategy="sliding_window",
        parameters=parameters(),
        limits=limits(history=exact_budget(snap, 3)),
        checkpoint=None,
        maintenance=FakeSummarizer(summary_text()),
        cancelled=lambda: False,
    )
    assert view.omitted_turn_ids == (1, 2) and view.tail_turn_ids == (3,), view

    rendered = render_context_view(snap, view)
    selection = build_selection_text("Fix it", snap, view)

    assert "old_calc.py" not in selection
    assert "Round with old_calc.py" not in rendered
    assert "omitted turns: 1, 2" in rendered
    assert "a" * 64 in rendered and "a" * 64 in selection  # the omitted turn's approval stays exact


# --- The runner consumes the selection, never the history -------------------------------------


def _workspace(tmp_path: Path) -> Path:
    for name in ("old_calc.py", "new_calc.py", "invented.py", "legacy.py"):
        (tmp_path / name).write_text(f"# {name}\n", encoding="utf-8")
    return tmp_path


class _Gateway:
    def __init__(self, output_text: str) -> None:
        self.calls: list[dict[str, object]] = []
        self.output_text = output_text

    def create_response(self, *, model: str, input_text: str, metadata=None) -> GatewayResponse:
        self.calls.append({"model": model, "input_text": input_text, "metadata": metadata})
        usage = GatewayUsage(gateway_request_id=f"gw-{len(self.calls)}", provider="openrouter", billing_units=10, cost_usd=Decimal("0.001"))
        return GatewayResponse(response_id=f"r{len(self.calls)}", output_text=self.output_text, gateway_usage=usage, raw={})


def _attached_request(tmp_path: Path, mode: ExecutionMode, *, prompt: str, selection: str, envelope: str) -> AgentRunRequest:
    return AgentRunRequest(
        run_id="session-1:4",
        session_id="session-1",
        task=prompt,
        execution_mode=mode,
        workspace_root=tmp_path,
        conversation_envelope=envelope,
        selection_text=selection,
        context_digest="c" * 64,
    )


def _run_and_observe(tmp_path: Path, request: AgentRunRequest, output_text: str):
    observed: list[object] = []
    gateway = _Gateway(output_text)
    runner = AgentRunner(gateway_client=gateway, model="m", workspace_context_observer=lambda req, ctx: observed.append(ctx))
    result = runner.run(request)
    assert len(observed) == 1
    return observed[0], gateway, result


@pytest.mark.parametrize("mode", [ExecutionMode.CHAT, ExecutionMode.AGENT])
def test_a_late_correction_selects_only_the_exact_path(tmp_path, mode):
    summarizer = FakeSummarizer(summary_text("Rounding used to be HALF_UP in old_calc.py."))
    snap, view = compaction_view(summarizer)
    prompt = "Apply the rounding rule now."
    request = _attached_request(
        _workspace(tmp_path), mode, prompt=prompt, selection=build_selection_text(prompt, snap, view), envelope=render_context_view(snap, view)
    )

    context, gateway, _ = _run_and_observe(tmp_path, request, "It uses HALF_EVEN." if mode is ExecutionMode.CHAT else "REFUSE: test")

    assert context.prioritized_paths == ("new_calc.py",)
    # The model still sees the history, summary included, separately from the task.
    model_input = gateway.calls[0]["input_text"]
    assert "Rounding used to be HALF_UP in old_calc.py." in model_input
    if mode is ExecutionMode.CHAT:
        assert gateway.calls[0]["metadata"]["task"] == prompt
        assert f"Current question: {prompt}" in model_input
    else:
        assert f"Task: {prompt}\n" in model_input


@pytest.mark.parametrize("mode", [ExecutionMode.CHAT, ExecutionMode.AGENT])
def test_a_summary_invented_path_is_never_selected(tmp_path, mode):
    summarizer = FakeSummarizer(summary_text("The user also wanted invented.py rewritten."))
    snap, view = compaction_view(summarizer)
    prompt = "Carry on."
    request = _attached_request(
        _workspace(tmp_path), mode, prompt=prompt, selection=build_selection_text(prompt, snap, view), envelope=render_context_view(snap, view)
    )

    context, _, _ = _run_and_observe(tmp_path, request, "Carrying on." if mode is ExecutionMode.CHAT else "REFUSE: test")

    assert "invented.py" not in context.prioritized_paths
    assert context.prioritized_paths == ("new_calc.py",)


@pytest.mark.parametrize("mode", [ExecutionMode.CHAT, ExecutionMode.AGENT])
def test_an_omitted_only_path_is_not_selected_and_that_file_gets_no_hint(tmp_path, mode):
    records = {1: turn("Please look at legacy.py first."), 2: turn("Thanks, that is clear now. " + "x" * 400)}
    snap = snapshot(records, approvals={})
    view = ContextEngine().prepare_view(
        snap,
        strategy="sliding_window",
        parameters=parameters(),
        limits=limits(history=exact_budget(snap, 2)),
        checkpoint=None,
        maintenance=FakeSummarizer(summary_text()),
        cancelled=lambda: False,
    )
    assert view.omitted_turn_ids == (1,), view
    prompt = "Now fix that file."
    request = _attached_request(
        _workspace(tmp_path), mode, prompt=prompt, selection=build_selection_text(prompt, snap, view), envelope=render_context_view(snap, view)
    )

    context, gateway, result = _run_and_observe(tmp_path, request, "Which file do you mean?" if mode is ExecutionMode.CHAT else "REFUSE: which file?")

    assert context.prioritized_paths == ()
    assert context.diagnostics == ()
    assert "legacy.py" not in gateway.calls[0]["input_text"].split("Prior conversation")[0]
    assert [call for call in result.tool_calls if call.tool_name == "file_reader"] == []
    assert result.plan_hash is None


def test_absent_chat_keeps_its_full_envelope_selection(tmp_path):
    envelope = '{"1":{"user_prompt":"Look at legacy.py","plan_text":"","completion_text":"ok","outcome":"completed","effect_state":"none"}}'
    request = AgentRunRequest(
        run_id="session-1:2",
        session_id="session-1",
        task="What does it do?",
        execution_mode=ExecutionMode.CHAT,
        workspace_root=_workspace(tmp_path),
        conversation_envelope=envelope,
    )

    context, _, _ = _run_and_observe(tmp_path, request, "It is legacy code.")

    assert context.prioritized_paths == ("legacy.py",)


def test_skills_match_the_selection_not_the_summary(tmp_path):
    skill = tmp_path / "skills" / "pytest" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: pytest-debugging\ndescription: Debug failing pytest tests.\nkeywords:\n  - pytest\n  - debug\n"
        "globs:\n  - tests/**/*.py\nallowed_tools:\n  - file_read\nowner: maintainer\nversion: 1.0.0\n"
        "trust_level: trusted\n---\n\n# Pytest\n",
        encoding="utf-8",
    )
    runner = AgentRunner(gateway_client=_Gateway("unused"), model="m")

    def matched(selection: str) -> tuple[str, ...]:
        request = AgentRunRequest(
            run_id="r",
            task="Carry on.",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
            skill_paths=(skill,),
            conversation_envelope="summary: debug the failing pytest suite",
            selection_text=selection,
        )
        return runner._match_skills(request)  # noqa: SLF001

    assert matched("Carry on.") == ()
    assert matched("Carry on.\nPlease debug the failing pytest test") == ("pytest-debugging",)


# --- Growth: the complete request is packed under the captured revision ----------------------------


class _SummarizerCall:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def __call__(self, *, prompt: str, max_output_tokens: int):
        from optimus.context.maintenance import SummarizerAttempt, SummarizerResponse

        self.prompts.append(prompt)
        attempt = SummarizerAttempt(attempt_id=f"s{len(self.prompts)}", gateway_request_id=None, outcome="completed", cost_usd=Decimal("0.0001"))
        return SummarizerResponse(text=summary_text("Merged."), finish_status="stop", attempts=(attempt,))


def _attached_turn(*, usable: int, calls: int = 3, tail: int = 400, summarizer=None, receipts=None, max_repacks: int = 2, estimate_request=estimate):
    from optimus.context.assembly import AttachedTurn, ContextAttachment, SummarizerRoute

    summarizer = summarizer if summarizer is not None else _SummarizerCall()
    attachment = ContextAttachment(
        engine=ContextEngine(),
        parameters=parameters(tail=tail, calls=calls),
        limits=limits(history=4000),
        source_max_bytes=1_000_000,
        record_reservation_bytes=0,
        usable_input_tokens=usable,
        estimate_request=estimate_request,
        registry_hash="e" * 64,
        model_id="test/planner",
        summarizer=lambda identity, deliver_notice: summarizer,
        summarizer_route=SummarizerRoute(model_id="test/summarizer", role="summarizer", route=("p",), reasoning=None, quantizations=("fp8",)),
        record_receipt=(receipts if receipts is not None else []).append,
        max_repacks=max_repacks,
    )
    records = {seq: turn(f"Turn {seq} " + "w" * 360) for seq in range(1, 7)}
    attached = AttachedTurn.capture(
        attachment=attachment,
        session_key="session-1",
        records=records,
        approvals={},
        generation=6,
        sanitizer=SANITIZER,
        strategy="compaction",
        mode=ExecutionMode.AGENT,
        checkpoint=None,
        current_prompt="Go on.",
        turn_seq=7,
        cancelled=lambda: False,
    )
    return attached, summarizer


def _build(evidence_bytes: int):
    return lambda envelope: f"FRAME\n{envelope}\nEVIDENCE:{'e' * evidence_bytes}\nTask: Go on."


def test_added_evidence_repacks_the_view_under_the_captured_revision():
    attached, summarizer = _attached_turn(usable=1100)
    outcome = attached.prepare()
    assert outcome.kind == "view"
    admitted = attached.admitted
    first = attached.fit(_build(100))
    assert first is not None and admitted.conversation_envelope in first
    assert attached.repacks == 0

    grown = attached.fit(_build(3000))

    assert grown is not None and estimate(grown) <= 1100
    assert admitted.conversation_envelope not in grown  # a smaller view
    assert attached.repacks == 1
    assert attached.admitted is admitted  # the admitted identity never changes
    assert attached.candidate is not None and attached.candidate.covered_turn_ids == admitted.view.covered_turn_ids
    assert len(summarizer.prompts) == attached.maintenance_calls <= 3


def test_a_repack_never_exceeds_the_turn_maintenance_allowance():
    from optimus.context.assembly import ContextFault

    attached, summarizer = _attached_turn(usable=1100, calls=1)
    assert attached.prepare().kind == "view"
    assert attached.maintenance_calls == 1

    assert attached.fit(_build(3000)) is None  # it would need another summary
    assert len(summarizer.prompts) == 1
    # Refused by the engine's whole-plan preflight against the remaining allowance (zero), before any
    # callback, as the allowance reason (release supplement V3).
    assert attached.take_faults() == (ContextFault("repack", "maintenance_unavailable"),)


def test_a_repack_keeps_the_parameters_digest_and_summarizes_only_new_turns():
    """Release supplement V3: the remaining allowance travels in ViewLimits, so the repack reuses the
    admitted view's summary and pays only for the turns it newly covers."""
    attached, summarizer = _attached_turn(usable=1100, calls=4)
    assert attached.prepare().kind == "view"
    initial = attached.admitted.view.checkpoint
    assert initial is not None and len(summarizer.prompts) == 1
    first_covered = initial.covered_turn_ids

    assert attached.fit(_build(3000)) is not None and attached.repacks == 1
    repacked = attached._view.checkpoint
    assert repacked is not None and repacked.parameters_digest == initial.parameters_digest == attached._attachment.parameters.digest
    assert repacked.covered_turn_ids[: len(first_covered)] == first_covered and len(repacked.covered_turn_ids) > len(first_covered)
    repack_prompts = summarizer.prompts[1:]
    assert repack_prompts and attached.maintenance_calls == len(summarizer.prompts) <= 4
    for seq in first_covered:  # an already summarized turn is never sent again
        assert all(f"Turn {seq} " not in prompt for prompt in repack_prompts)
    assert attached.candidate is initial  # a repack's checkpoint is never the one published


def _lighter_request_estimate(text: str) -> int:
    """Test-only: a request estimator lighter than the view's, so a repack sized from the request's
    excess removes too little and only a second repack fits."""
    return (len(text.encode("utf-8")) + 7) // 8


def test_the_accepted_single_repack_within_the_shared_allowance():
    """Task 12 accepted values, read from the checker-validated proposal: one finite repack after the
    initial packing, inside the turn's shared call allowance. A request one repack fits is sent after
    exactly one. A request only a second repack would fit is refused after that one, and the same
    request fits when a second is allowed, so the one-repack limit is what refuses (Fable m4)."""
    from tests.unit.context_engine.test_limits import PROPOSAL

    accepted, allowance = PROPOSAL["max_repacks"], PROPOSAL["max_maintenance_calls"]
    fitting, _ = _attached_turn(usable=1100, calls=allowance, max_repacks=accepted)
    assert fitting.prepare().kind == "view"
    assert fitting.fit(_build(3000)) is not None and fitting.repacks == 1
    assert fitting.maintenance_calls <= allowance

    refused, summarizer = _attached_turn(usable=600, calls=allowance, max_repacks=accepted, estimate_request=_lighter_request_estimate)
    assert refused.prepare().kind == "view"
    assert refused.fit(_build(3500)) is None
    assert refused.repacks == accepted == 1 and len(summarizer.prompts) == refused.maintenance_calls == 2

    allowed, _ = _attached_turn(usable=600, calls=allowance, max_repacks=accepted + 1, estimate_request=_lighter_request_estimate)
    assert allowed.prepare().kind == "view"
    assert allowed.fit(_build(3500)) is not None and allowed.repacks == 2


def test_a_request_whose_fixed_part_cannot_fit_is_refused_without_looping():
    attached, summarizer = _attached_turn(usable=1100)
    assert attached.prepare().kind == "view"

    assert attached.fit(_build(10_000)) is None
    assert attached.repacks <= 2
    assert len(summarizer.prompts) <= 3


class _FakePacker:
    def __init__(self, envelope: str, *, refuse: bool = False) -> None:
        self.envelope = envelope
        self.refuse = refuse
        self.inputs: list[str] = []
        self.dispatched: list[str] = []

    def fit(self, build):
        text = build(self.envelope)
        self.inputs.append(text)
        return None if self.refuse else text

    def record_dispatch(self, text: str) -> None:
        self.dispatched.append(text)


def test_the_agent_planner_gets_history_in_its_own_section_and_packs_every_round(tmp_path):
    (tmp_path / "big.py").write_text("b" * 200, encoding="utf-8")
    gateway = _Gateway("OBSERVE: need it\nREAD: big.py#bytes=0:200\n")
    runner = AgentRunner(gateway_client=gateway, model="m")
    request = _attached_request(tmp_path, ExecutionMode.AGENT, prompt="Go on.", selection="Go on.", envelope="HISTORY-VIEW")
    packer = _FakePacker("HISTORY-VIEW")

    runner.run(request, context_packer=packer)

    assert len(gateway.calls) >= 2
    assert packer.inputs == [call["input_text"] for call in gateway.calls]  # every round, as sent
    first = gateway.calls[0]["input_text"]
    assert "Task: Go on.\n" in first and "HISTORY-VIEW" in first
    assert first.index("HISTORY-VIEW") < first.index("Task: Go on.")


@pytest.mark.parametrize("mode", [ExecutionMode.AGENT, ExecutionMode.CHAT])
def test_a_request_the_packer_cannot_fit_is_not_dispatched(tmp_path, mode):
    gateway = _Gateway("unused")
    runner = AgentRunner(gateway_client=gateway, model="m")
    request = _attached_request(tmp_path, mode, prompt="Go on.", selection="Go on.", envelope="HISTORY-VIEW")

    result = runner.run(request, context_packer=_FakePacker("HISTORY-VIEW", refuse=True))

    assert gateway.calls == []
    assert result.stop_reason == ("CONTEXT_CAPACITY_EXCEEDED" if mode is ExecutionMode.AGENT else "CHAT_CONTEXT_CAPACITY_EXCEEDED")
    assert "was not sent" in result.output_text
    assert result.output_text.endswith(  # Codex's final corrections C1: the recovery that can help
        " A shorter prompt or a narrower request that involves fewer workspace files may help. "
        "If earlier conversation history is the cause, start a new thread."
    )


def test_an_absent_agent_planner_input_is_unchanged(tmp_path):
    from optimus.agent.prompts import build_multi_turn_planner_input

    kwargs = dict(planning_turn=1, max_planning_turns=3, remaining_wall_clock_minutes=30)
    assert build_multi_turn_planner_input("task", conversation_envelope="", **kwargs) == build_multi_turn_planner_input("task", **kwargs)
    assert "Prior conversation" not in build_multi_turn_planner_input("task", **kwargs)


# --- Fable CP3 review fixes -------------------------------------------------------------------------


def test_a_non_attached_agent_caller_keeps_its_existing_planner_input(tmp_path):
    gateway = _Gateway("REFUSE: no")
    request = AgentRunRequest(
        run_id="r", session_id="s", task="Plan it", execution_mode=ExecutionMode.AGENT, workspace_root=tmp_path,
        conversation_envelope="CLIENT-SUPPLIED-HISTORY",
    )  # fmt: skip

    AgentRunner(gateway_client=gateway, model="m").run(request)

    assert "CLIENT-SUPPLIED-HISTORY" not in gateway.calls[0]["input_text"]
    assert "Prior conversation" not in gateway.calls[0]["input_text"]


@pytest.mark.parametrize("mode", [ExecutionMode.AGENT, ExecutionMode.CHAT])
def test_a_request_not_fitted_because_the_turn_was_halted_reports_a_halt(tmp_path, mode):
    gateway = _Gateway("unused")
    request = _attached_request(tmp_path, mode, prompt="Go on.", selection="Go on.", envelope="HISTORY-VIEW")
    halted: list[bool] = []

    class HaltedWhileFitting(_FakePacker):
        def fit(self, build):
            halted.append(True)  # the user cancels while the request is being fitted
            return None

    result = AgentRunner(gateway_client=gateway, model="m").run(
        request, context_packer=HaltedWhileFitting("HISTORY-VIEW"), halt_requested=lambda: bool(halted)
    )

    assert gateway.calls == []
    assert result.stop_reason in {"PLANNING_HALTED", "CHAT_HALTED"}
