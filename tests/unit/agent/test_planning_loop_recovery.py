"""Plan 12.3 interactive loop recovery, through the real planning runner: detect, one nudge, then a
Continue/Stop check-in (Designs 1-4 and 7; ADR-024)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from optimus.agent.models import AgentMcpToolOutput, AgentToolCall
from optimus.agent.planning_loop import CheckInDecision, PlanningCheckIn, PlanningLoopPolicy, PlanningLoopRunner
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.guardrails.pre_tool import PreToolGuard
from optimus.loops.detector import LoopThresholds
from optimus.runtime.modes import ExecutionMode
from optimus.telemetry.events import TelemetryEvent, TelemetryEventKind

NOTE = "Loop recovery note (from Optimus, not the user):"
FINAL_PLAN = "READ a.py\nWRITE a.py\nupdated\n"
READ_A = "OBSERVE: need the header\nREAD: a.py#bytes=0:5\n"
READ_B = "OBSERVE: need the body\nREAD: a.py#bytes=5:10\n"
PROSE = "Here is prose only."
Step = str | tuple[str, Callable[[], None]]


class Gateway:
    """Scripted replies; a step may first run a hook, such as changing a file between reads."""

    def __init__(self, steps: list[Step]) -> None:
        self._steps = list(steps)
        self.prompts: list[str] = []

    def create_response(self, *, model, input_text, metadata=None):
        if not self._steps:
            raise AssertionError("the planning loop made more requests than scripted")
        step = self._steps.pop(0)
        text, hook = (step, None) if isinstance(step, str) else step
        if hook is not None:
            hook()
        self.prompts.append(input_text)
        n = len(self.prompts)
        return GatewayResponse(
            response_id=f"gw-{n}",
            output_text=text,
            gateway_usage=GatewayUsage(gateway_request_id=f"gw-{n}", provider="glm", billing_units=1, cost_usd=Decimal("0.001")),
            raw={"id": f"gw-{n}"},
        )


class Mcp:
    def __init__(self, outputs: dict[str, list[str]]) -> None:
        self._outputs = outputs

    def list_tools(self, server):
        return (
            AgentMcpToolOutput(server_name=server, tool_name="mcp_list_tools", text='{"tools":["t1","t2","t3"]}'),
            AgentToolCall(tool_name="mcp_list_tools", summary="listed", authorization_outcome="ALLOW"),
        )

    def call_tool(self, server, tool, arguments, one_call_approval=None):
        queue = self._outputs[tool]
        text = queue.pop(0) if len(queue) > 1 else queue[0]
        return (
            AgentMcpToolOutput(server_name=server, tool_name=tool, text=text),
            AgentToolCall(tool_name="mcp_call", summary=f"called {tool}", authorization_outcome="ALLOW"),
        )


class CheckIns:
    def __init__(self, *decisions: CheckInDecision, on_ask: Callable[[], None] | None = None) -> None:
        self._decisions = list(decisions)
        self._on_ask = on_ask
        self.asked: list[PlanningCheckIn] = []

    def __call__(self, checkin: PlanningCheckIn) -> CheckInDecision:
        self.asked.append(checkin)
        if self._on_ask is not None:
            self._on_ask()
        return self._decisions.pop(0)


def _run(
    tmp_path: Path,
    gateway: Gateway,
    checkins: CheckIns | None,
    *,
    policy: PlanningLoopPolicy | None = None,
    mcp: Mcp | None = None,
    now: Callable[[], datetime] | None = None,
    halt: Callable[[], bool] | None = None,
    events: list[TelemetryEvent] | None = None,
):
    return PlanningLoopRunner(
        gateway_client=gateway,
        model="glm-5.2",
        policy=policy or PlanningLoopPolicy(),
        workspace_root=tmp_path,
        execution_mode=ExecutionMode.AGENT,
        guard=PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=()),
        client_mcp_service=mcp,
        now=now,
        halt_requested=halt,
        recovery_checkin=checkins,
        loop_event_sink=None if events is None else events.append,
    ).run(run_id="run-123", session_id="session-123", task="Update a.py")


@pytest.fixture
def source(tmp_path: Path) -> Path:
    target = tmp_path / "a.py"
    target.write_text("0123456789abcdef", encoding="utf-8")
    return target


def _rewrite(target: Path, n: int) -> Callable[[], None]:
    return lambda: target.write_text(f"{n:05d}6789abcdef", encoding="utf-8")


def _nudged(gateway: Gateway) -> list[int]:
    return [i + 1 for i, prompt in enumerate(gateway.prompts) if NOTE in prompt]


# --- what is not detected: legitimate repetition and progress ---


def test_polling_a_changing_file_never_fires(tmp_path, source):
    gateway = Gateway([(READ_A, _rewrite(source, n)) for n in range(5)] + [FINAL_PLAN])
    checkins = CheckIns()
    result = _run(tmp_path, gateway, checkins, policy=PlanningLoopPolicy(max_planning_turns=6))
    assert (result.stop_reason, result.settled_turns, checkins.asked, _nudged(gateway)) == (None, 6, [], [])


def test_a_changed_file_re_read_is_progress(tmp_path, source):
    gateway = Gateway([READ_A, READ_A, (READ_A, _rewrite(source, 7)), FINAL_PLAN])
    checkins = CheckIns()
    result = _run(tmp_path, gateway, checkins, policy=PlanningLoopPolicy(max_planning_turns=4))
    assert (result.stop_reason, checkins.asked, _nudged(gateway)) == (None, [], [])


def test_three_previously_unread_ranges_of_one_unchanged_file_are_progress(tmp_path, source):
    reads = [f"OBSERVE: part {n}\nREAD: a.py#bytes={start}:{start + 5}\n" for n, start in enumerate((0, 5, 10))]
    gateway = Gateway([*reads, FINAL_PLAN])
    checkins = CheckIns()
    result = _run(tmp_path, gateway, checkins, policy=PlanningLoopPolicy(max_planning_turns=4))
    assert (result.stop_reason, checkins.asked, _nudged(gateway)) == (None, [], [])


def test_polling_an_mcp_tool_with_changing_results_never_fires(tmp_path, source):
    mcp = Mcp({"t1": ["one", "two", "three", "four"]})
    gateway = Gateway(['MCP_CALL tools t1 {"q":"x"}\n'] * 4 + [FINAL_PLAN])
    checkins = CheckIns()
    result = _run(tmp_path, gateway, checkins, policy=PlanningLoopPolicy(max_planning_turns=5), mcp=mcp)
    assert (result.stop_reason, checkins.asked, _nudged(gateway)) == (None, [], [])


def test_polling_an_mcp_tool_whose_result_flips_back_never_fires(tmp_path, source):
    mcp = Mcp({"t1": ["running", "idle", "running", "idle", "running"]})
    gateway = Gateway(['MCP_CALL tools t1 {"q":"x"}\n'] * 5 + [FINAL_PLAN])
    checkins = CheckIns()
    result = _run(tmp_path, gateway, checkins, policy=PlanningLoopPolicy(max_planning_turns=6), mcp=mcp)
    assert (result.stop_reason, checkins.asked, _nudged(gateway)) == (None, [], [])


def test_re_reading_a_file_that_flips_back_to_earlier_content_never_fires(tmp_path, source):
    gateway = Gateway([(READ_A, _rewrite(source, n % 2)) for n in range(5)] + [FINAL_PLAN])
    checkins = CheckIns()
    result = _run(tmp_path, gateway, checkins, policy=PlanningLoopPolicy(max_planning_turns=6))
    assert (result.stop_reason, checkins.asked, _nudged(gateway)) == (None, [], [])


def test_distinct_mcp_tools_on_one_server_are_progress(tmp_path, source):
    mcp = Mcp({"t1": ["same"], "t2": ["same"], "t3": ["same"]})
    calls = [f'MCP_CALL tools {tool} {{"q":"x"}}\n' for tool in ("t1", "t2", "t3")]
    gateway = Gateway([*calls, FINAL_PLAN])
    checkins = CheckIns()
    result = _run(tmp_path, gateway, checkins, policy=PlanningLoopPolicy(max_planning_turns=4), mcp=mcp)
    assert (result.stop_reason, checkins.asked, _nudged(gateway)) == (None, [], [])


# --- what is detected; every episode's nudge comes before its check-in ---


def test_a_repeat_on_the_allowances_last_step_gets_one_budgeted_nudge_step_then_the_check_in(tmp_path, source):
    gateway = Gateway([READ_A] * 4)
    checkins = CheckIns(CheckInDecision.STOP)
    result = _run(tmp_path, gateway, checkins)

    assert len(gateway.prompts) == 4  # 3 steps, plus exactly one nudge step
    assert _nudged(gateway) == [4]
    assert "repeated the read of a.py#bytes=0:5 with unchanged results" in gateway.prompts[3]
    assert "Planning turn: 4 of 4" in gateway.prompts[3]
    [checkin] = checkins.asked
    assert (checkin.cause, checkin.planning_steps, checkin.plan_waiting) == ("REPEATED_READ", 4, False)
    assert result.stop_reason == "PLANNING_REPEATED_READ_REQUEST"
    assert "a.py#bytes=0:5" in result.corrective_text
    assert result.settled_turns == 4


def test_a_repeated_mcp_call_is_named_as_mcp(tmp_path, source):
    mcp = Mcp({"t1": ["same"]})
    gateway = Gateway(['MCP_CALL tools t1 {"q":"x"}\n'] * 4)
    checkins = CheckIns(CheckInDecision.STOP)
    result = _run(tmp_path, gateway, checkins, mcp=mcp)
    assert checkins.asked[0].cause == "REPEATED_MCP"
    assert result.stop_reason == "PLANNING_REPEATED_MCP_REQUEST"
    assert "tools.t1" in result.corrective_text


def test_an_a_b_cycle_over_three_cycles_is_detected(tmp_path, source):
    policy = PlanningLoopPolicy(max_planning_turns=8, loop_thresholds=LoopThresholds(no_progress=10))
    gateway = Gateway([READ_A, READ_B] * 3 + [READ_A])
    checkins = CheckIns(CheckInDecision.STOP)
    result = _run(tmp_path, gateway, checkins, policy=policy)
    assert _nudged(gateway) == [7]
    assert checkins.asked[0].cause == "CYCLE"
    assert result.stop_reason == "PLANNING_ACTION_CYCLE"


def test_fully_covered_re_reads_are_no_progress(tmp_path, source):
    covered = ["OBSERVE: again\nREAD: a.py#bytes=0:5\n", "OBSERVE: again\nREAD: a.py#bytes=5:10\n", "OBSERVE: again\nREAD: a.py#bytes=2:8\n"]
    gateway = Gateway(["OBSERVE: all\nREAD: a.py#bytes=0:10\n", *covered, FINAL_PLAN])
    checkins = CheckIns(CheckInDecision.STOP)
    result = _run(tmp_path, gateway, checkins, policy=PlanningLoopPolicy(max_planning_turns=5))
    assert _nudged(gateway) == [5]
    assert checkins.asked[0].cause == "NO_PROGRESS"
    assert result.stop_reason == "PLANNING_NO_PROGRESS"


def test_a_parse_failure_recovers_through_its_nudge_and_the_plan_waits_for_the_check_in(tmp_path, source):
    gateway = Gateway([PROSE] * 3 + [FINAL_PLAN])
    checkins = CheckIns(CheckInDecision.CONTINUE)
    result = _run(tmp_path, gateway, checkins)

    assert _nudged(gateway) == [4]
    assert "parser reason GRAMMAR_UNRECOGNIZED" in gateway.prompts[3]
    [checkin] = checkins.asked
    assert (checkin.cause, checkin.plan_waiting) == ("REPEATED_PARSE_ERROR", True)
    assert "Continue shows it for your approval" in checkin.text
    assert result.stop_reason is None
    assert result.plan_text == FINAL_PLAN  # kept, for the normal plan approval


def test_each_turn_after_a_parse_failure_carries_its_notice_and_the_nudge_turn_carries_both(tmp_path, source):
    """#403 with Plan 12.3: the fixed notice follows every unparseable turn, the episode's nudge still comes once."""
    from optimus.agent.planning_loop import PLANNING_PARSE_FEEDBACK
    from optimus.agent.prompts import CORRECTION_NOTICE_HEADER

    gateway = Gateway([PROSE] * 3 + [FINAL_PLAN])
    result = _run(tmp_path, gateway, CheckIns(CheckInDecision.CONTINUE))

    notice = f"{CORRECTION_NOTICE_HEADER} {PLANNING_PARSE_FEEDBACK['GRAMMAR_UNRECOGNIZED']}"
    assert [notice in prompt for prompt in gateway.prompts] == [False, True, True, True]
    assert _nudged(gateway) == [4]
    assert gateway.prompts[3].index(notice) < gateway.prompts[3].index(NOTE)
    assert result.plan_text == FINAL_PLAN


REFUSE = "REFUSE: The evidence is not enough for a safe change.\n"


def test_a_refusal_after_the_nudge_waits_for_the_check_in_and_stop_keeps_it(tmp_path, source):
    gateway = Gateway([PROSE] * 3 + [REFUSE])
    checkins = CheckIns(CheckInDecision.STOP)
    result = _run(tmp_path, gateway, checkins)
    [checkin] = checkins.asked
    assert (checkin.cause, checkin.refusal_waiting, checkin.plan_waiting) == ("REPEATED_PARSE_ERROR", True, False)
    assert "The model then refused: The evidence is not enough for a safe change." in checkin.text
    assert (result.stop_reason, result.refusal_reason) == (
        "PLANNING_MODEL_REFUSED",
        "The evidence is not enough for a safe change.",
    )


@pytest.mark.parametrize(
    ("decision", "ending"),
    [(CheckInDecision.UNAVAILABLE, "could not be shown"), (CheckInDecision.INVALID, "was not recognised")],
)
def test_a_waiting_refusal_keeps_the_explanation_of_a_check_in_that_could_not_be_answered(tmp_path, source, decision, ending):
    """Codex Checkpoint B, 4."""
    result = _run(tmp_path, Gateway([PROSE] * 3 + [REFUSE]), CheckIns(decision))
    assert (result.stop_reason, result.refusal_reason) == ("PLANNING_MODEL_REFUSED", "The evidence is not enough for a safe change.")
    assert result.corrective_text.startswith("The evidence is not enough for a safe change.")
    assert ending in result.corrective_text


def test_continue_sets_a_waiting_refusal_aside_and_grants_more_steps(tmp_path, source):
    gateway = Gateway([PROSE] * 3 + [REFUSE, READ_A, FINAL_PLAN])
    checkins = CheckIns(CheckInDecision.CONTINUE)
    result = _run(tmp_path, gateway, checkins)
    assert len(checkins.asked) == 1
    assert (result.stop_reason, result.plan_text, result.settled_turns) == (None, FINAL_PLAN, 6)


def test_an_evaluation_cap_covers_the_whole_turn_across_continue(tmp_path, source):
    reads = [f"OBSERVE: part {n}\nREAD: a.py#bytes={n}:{n + 1}\n" for n in range(4)]
    gateway = Gateway([*reads, FINAL_PLAN])
    result = PlanningLoopRunner(
        gateway_client=gateway,
        model="glm-5.2",
        policy=PlanningLoopPolicy(),
        workspace_root=tmp_path,
        execution_mode=ExecutionMode.AGENT,
        guard=PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=()),
        max_cost_usd=Decimal("0.004"),
        recovery_checkin=CheckIns(CheckInDecision.CONTINUE),
    ).run(run_id="run-123", session_id=None, task="Update a.py")
    assert (result.stop_reason, len(gateway.prompts)) == ("PLANNING_BUDGET_EXHAUSTED", 4)


def test_stop_at_a_check_in_with_a_waiting_plan_ends_the_turn_without_it(tmp_path, source):
    gateway = Gateway([PROSE] * 3 + [FINAL_PLAN])
    result = _run(tmp_path, gateway, CheckIns(CheckInDecision.STOP))
    assert (result.stop_reason, result.plan_text, result.plan_hash) == ("PLANNING_UNPARSEABLE_RESPONSE", None, None)


def test_a_second_detection_after_the_nudge_goes_to_the_check_in(tmp_path, source):
    gateway = Gateway([READ_A] * 3 + [READ_A])
    policy = PlanningLoopPolicy(max_planning_turns=6)
    checkins = CheckIns(CheckInDecision.STOP)
    _run(tmp_path, gateway, checkins, policy=policy)
    assert len(gateway.prompts) == 4  # the nudge step repeated again: no further step before asking
    assert _nudged(gateway) == [4]
    assert len(checkins.asked) == 1


# --- the check-in transitions ---


def test_the_allowance_running_out_becomes_a_check_in_and_continue_grants_three_more_steps(tmp_path, source):
    reads = [f"OBSERVE: part {n}\nREAD: a.py#bytes={n}:{n + 1}\n" for n in range(5)]
    gateway = Gateway([*reads, FINAL_PLAN])
    checkins = CheckIns(CheckInDecision.CONTINUE)
    result = _run(tmp_path, gateway, checkins)

    [checkin] = checkins.asked
    assert (checkin.cause, checkin.planning_steps) == ("TURN_LIMIT", 3)
    assert "Continue grants 3 more planning steps and 30 minutes" in checkin.text
    assert "Planning turn: 4 of 6" in gateway.prompts[3]
    assert _nudged(gateway) == []
    assert (result.stop_reason, result.settled_turns, result.plan_text) == (None, 6, FINAL_PLAN)
    # Costs, receipts and carried evidence are preserved across Continue.
    assert result.total_cost_usd == Decimal("0.006")
    assert result.gateway_request_ids == tuple(f"gw-{n}" for n in range(1, 7))
    assert "OBS_RECORD path=a.py bytes=0:1" in gateway.prompts[5]


def test_each_check_in_cycle_is_at_most_four_planning_steps_and_continue_starts_a_new_episode(tmp_path, source):
    gateway = Gateway([READ_A] * 8)
    checkins = CheckIns(CheckInDecision.CONTINUE, CheckInDecision.STOP)
    result = _run(tmp_path, gateway, checkins)

    assert [c.planning_steps for c in checkins.asked] == [4, 8]
    assert _nudged(gateway) == [4, 8]  # the second episode gets its own nudge
    assert result.stop_reason == "PLANNING_REPEATED_READ_REQUEST"
    assert result.settled_turns == 8


def test_repeated_continues_are_each_asked(tmp_path, source):
    reads = [f"OBSERVE: part {n}\nREAD: a.py#bytes={n}:{n + 1}\n" for n in range(9)]
    gateway = Gateway(reads)
    checkins = CheckIns(CheckInDecision.CONTINUE, CheckInDecision.CONTINUE, CheckInDecision.STOP)
    result = _run(tmp_path, gateway, checkins)
    assert [c.planning_steps for c in checkins.asked] == [3, 6, 9]
    assert result.stop_reason == "PLANNING_TURN_LIMIT_EXHAUSTED"


def test_the_wall_clock_running_out_becomes_a_check_in(tmp_path, source):
    clock = [datetime(2026, 10, 23, tzinfo=UTC)]
    gateway = Gateway([("OBSERVE: a\nREAD: a.py#bytes=0:1\n", lambda: clock.__setitem__(0, clock[0] + timedelta(minutes=31)))])
    checkins = CheckIns(CheckInDecision.STOP)
    result = _run(tmp_path, gateway, checkins, now=lambda: clock[0])
    assert checkins.asked[0].cause == "WALL_CLOCK"
    assert result.stop_reason == "PLANNING_WALL_CLOCK_EXHAUSTED"


def test_continue_after_the_clock_ran_out_starts_a_fresh_clock(tmp_path, source):
    clock = [datetime(2026, 10, 23, tzinfo=UTC)]
    late = ("OBSERVE: a\nREAD: a.py#bytes=0:1\n", lambda: clock.__setitem__(0, clock[0] + timedelta(minutes=31)))
    gateway = Gateway([late, "OBSERVE: b\nREAD: a.py#bytes=1:2\n", FINAL_PLAN])
    checkins = CheckIns(CheckInDecision.CONTINUE)
    result = _run(tmp_path, gateway, checkins, now=lambda: clock[0])
    assert [c.cause for c in checkins.asked] == ["WALL_CLOCK"]
    assert "Remaining wall-clock minutes: 30" in gateway.prompts[1]
    assert (result.stop_reason, result.plan_text, len(gateway.prompts)) == (None, FINAL_PLAN, 3)


def test_a_detection_after_the_clock_expired_still_gets_its_nudge_step(tmp_path, source):
    clock = [datetime(2026, 10, 23, tzinfo=UTC)]
    late = (READ_A, lambda: clock.__setitem__(0, clock[0] + timedelta(minutes=31)))
    gateway = Gateway([READ_A, READ_A, late, READ_A])
    checkins = CheckIns(CheckInDecision.STOP)
    _run(tmp_path, gateway, checkins, policy=PlanningLoopPolicy(max_planning_turns=6), now=lambda: clock[0])
    assert _nudged(gateway) == [4]
    assert "Remaining wall-clock minutes: 0" in gateway.prompts[3]
    assert checkins.asked[0].cause == "REPEATED_READ"


def test_an_interactive_final_plan_in_the_step_where_the_clock_expired_is_kept(tmp_path, source):
    clock = [datetime(2026, 10, 23, tzinfo=UTC)]
    gateway = Gateway([(FINAL_PLAN, lambda: clock.__setitem__(0, clock[0] + timedelta(minutes=31)))])
    result = _run(tmp_path, gateway, CheckIns(), now=lambda: clock[0])
    assert (result.stop_reason, result.plan_text) == (None, FINAL_PLAN)


def test_a_headless_final_plan_in_the_step_where_the_clock_expired_is_still_discarded(tmp_path, source):
    clock = [datetime(2026, 10, 23, tzinfo=UTC)]
    gateway = Gateway([(FINAL_PLAN, lambda: clock.__setitem__(0, clock[0] + timedelta(minutes=31)))])
    result = _run(tmp_path, gateway, None, now=lambda: clock[0])
    assert (result.stop_reason, result.plan_text) == ("PLANNING_WALL_CLOCK_EXHAUSTED", None)


def test_headless_keeps_its_hard_caps(tmp_path, source):
    result = _run(tmp_path, Gateway([READ_A] * 2), None)
    assert (result.stop_reason, result.settled_turns) == ("PLANNING_REPEATED_READ_REQUEST", 2)
    result = _run(tmp_path, Gateway([f"OBSERVE: p\nREAD: a.py#bytes={n}:{n + 1}\n" for n in range(3)]), None)
    assert (result.stop_reason, result.settled_turns) == ("PLANNING_TURN_LIMIT_EXHAUSTED", 3)


def test_headless_names_a_repeated_mcp_call_as_mcp(tmp_path, source):
    result = _run(tmp_path, Gateway(['MCP_CALL tools t1 {"q":"x"}\n'] * 2), None, mcp=Mcp({"t1": ["same"]}))
    assert result.stop_reason == "PLANNING_REPEATED_MCP_REQUEST"


def test_a_late_continue_after_cancel_does_not_resume(tmp_path, source):
    halted = [False]
    gateway = Gateway([READ_A] * 4)
    checkins = CheckIns(CheckInDecision.CONTINUE, on_ask=lambda: halted.__setitem__(0, True))
    result = _run(tmp_path, gateway, checkins, halt=lambda: halted[0])
    assert result.stop_reason == "PLANNING_HALTED"
    assert len(gateway.prompts) == 4


@pytest.mark.parametrize("decision", [CheckInDecision.UNAVAILABLE, "garbage", RuntimeError("client went away")])
def test_a_check_in_that_cannot_be_presented_ends_the_turn_recoverably(tmp_path, source, decision):
    def ask(checkin: PlanningCheckIn) -> CheckInDecision:
        if isinstance(decision, Exception):
            raise decision
        return decision  # type: ignore[return-value]

    gateway = Gateway([READ_A] * 4)
    result = _run(tmp_path, gateway, ask)  # type: ignore[arg-type]
    assert result.stop_reason == "PLANNING_REPEATED_READ_REQUEST"
    assert len(gateway.prompts) == 4  # it does not spin
    expected = "was not recognised" if decision == "garbage" else "check-in to continue could not be shown"
    assert expected in result.corrective_text


def test_first_occurrence_typed_failures_stay_stops(tmp_path, source):
    checkins = CheckIns()
    result = _run(tmp_path, Gateway(["OBSERVE: x\nREAD: missing.py#bytes=0:5\n"]), checkins)
    assert (result.stop_reason, checkins.asked) == ("PLANNING_READ_FILE_NOT_FOUND", [])


def test_detections_and_decisions_are_recorded_without_content(tmp_path, source):
    events: list[TelemetryEvent] = []
    _run(tmp_path, Gateway([READ_A] * 4), CheckIns(CheckInDecision.STOP), events=events)
    assert [e.kind for e in events] == [TelemetryEventKind.LOOP_RECOVERY] * 3
    assert [e.payload for e in events] == [
        {"record": "detection", "signal": "REPEATED_READ", "planning_step": 3},
        {"record": "detection", "signal": "REPEATED_READ", "planning_step": 4},
        {"record": "check_in", "signal": "REPEATED_READ", "planning_step": 4, "decision": "stop"},
    ]
    assert "a.py" not in str([e.model_dump() for e in events])
