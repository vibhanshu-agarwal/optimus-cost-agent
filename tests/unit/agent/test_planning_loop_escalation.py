"""#397, loop control Phase 3 (ADR-009 rung 2), through the real planning runner: when an episode's nudge has not
helped, the rest of the turn moves once to a stronger model, and the episode still ends at the check-in.

The host's escalation callback is scripted here; the target rule and the switch's host side are tested in
`tests/unit/acp/test_auto_escalation.py`.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import pytest

from optimus.agent.planning_loop import (
    CheckInDecision,
    EscalationGrant,
    EscalationRefusal,
    PlanningEscalation,
    PlanningLoopPolicy,
    PlanningLoopRunner,
)
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.guardrails.pre_tool import PreToolGuard
from optimus.runtime.modes import ExecutionMode
from optimus.telemetry.events import TelemetryEvent
from tests.unit.agent.test_planning_loop_recovery import FINAL_PLAN, READ_A, READ_B, CheckIns

WEAK, STRONG = "weak/model", "strong/model"
ESCALATED = "moved this planning to you"


@pytest.fixture
def source(tmp_path: Path) -> Path:
    target = tmp_path / "a.py"
    target.write_text("0123456789abcdef", encoding="utf-8")
    return target


class Gateway:
    """Scripted replies, recording which model each request was sent to."""

    def __init__(self, steps: list[str]) -> None:
        self._steps = list(steps)
        self.prompts: list[str] = []
        self.models: list[str] = []

    def create_response(self, *, model, input_text, metadata=None):
        if not self._steps:
            raise AssertionError("the planning loop made more requests than scripted")
        self.prompts.append(input_text)
        self.models.append(model)
        n = len(self.prompts)
        return GatewayResponse(
            response_id=f"gw-{n}",
            output_text=self._steps.pop(0),
            gateway_usage=GatewayUsage(gateway_request_id=f"gw-{n}", provider="glm", billing_units=1, cost_usd=Decimal("0.001")),
            raw={"id": f"gw-{n}"},
        )


class Escalations:
    """The host's callback: answers each move with the next scripted outcome."""

    def __init__(self, *outcomes: EscalationGrant | EscalationRefusal, on_ask: Callable[[], None] | None = None) -> None:
        self._outcomes = list(outcomes)
        self._on_ask = on_ask
        self.asked: list[PlanningEscalation] = []

    def __call__(self, move: PlanningEscalation) -> EscalationGrant | EscalationRefusal:
        self.asked.append(move)
        if self._on_ask is not None:
            self._on_ask()
        return self._outcomes.pop(0)


GRANT = EscalationGrant(model_id=STRONG, route_binder=None)


def _run(tmp_path: Path, gateway: Gateway, checkins: CheckIns, escalations: Escalations | None, *, policy=None, halt=None, events=None):
    return PlanningLoopRunner(
        gateway_client=gateway,
        model=WEAK,
        policy=policy or PlanningLoopPolicy(),
        workspace_root=tmp_path,
        execution_mode=ExecutionMode.AGENT,
        guard=PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=()),
        halt_requested=halt,
        recovery_checkin=checkins,
        recovery_escalation=escalations,
        loop_event_sink=None if events is None else events.append,
    ).run(run_id="run-123", session_id="session-123", task="Update a.py")


def test_a_repeat_after_the_nudge_escalates_once_then_the_escalated_steps_end_at_the_check_in(tmp_path, source):
    gateway = Gateway([READ_A] * 7)
    checkins, escalations = CheckIns(CheckInDecision.STOP), Escalations(GRANT)
    result = _run(tmp_path, gateway, checkins, escalations)

    # 3 steps, the nudge step, then 3 fresh steps on the stronger model; its own repeats end at the check-in.
    assert gateway.models == [WEAK] * 4 + [STRONG] * 3
    [move] = escalations.asked
    assert (move.cause, move.planning_steps) == ("REPEATED_READ", 4)
    assert "repeated the read of a.py#bytes=0:5 with unchanged results" in move.what
    assert ESCALATED in gateway.prompts[4] and all(ESCALATED not in p for p in gateway.prompts[5:])
    assert "Planning turn: 5 of 7" in gateway.prompts[4]
    [checkin] = checkins.asked
    assert checkin.planning_steps == 7
    assert "then moved to strong/model" in checkin.text
    assert result.stop_reason == "PLANNING_REPEATED_READ_REQUEST"
    assert result.settled_turns == 7


def test_the_allowance_ending_after_the_nudge_without_a_plan_escalates(tmp_path, source):
    # Detected on step 3; the nudge's step 4 makes a different read, so there is no second detection.
    gateway = Gateway([READ_A] * 3 + [READ_B, FINAL_PLAN])
    checkins, escalations = CheckIns(CheckInDecision.CONTINUE), Escalations(GRANT)
    result = _run(tmp_path, gateway, checkins, escalations)

    assert gateway.models == [WEAK] * 4 + [STRONG]
    assert len(escalations.asked) == 1
    # The stronger model's plan still waits for the episode's check-in.
    [checkin] = checkins.asked
    assert checkin.plan_waiting
    assert (result.stop_reason, result.plan_text) == (None, FINAL_PLAN)


def test_a_plan_settled_by_the_nudge_goes_to_the_check_in_without_escalating(tmp_path, source):
    gateway = Gateway([READ_A] * 3 + [FINAL_PLAN])
    checkins, escalations = CheckIns(CheckInDecision.CONTINUE), Escalations()
    _run(tmp_path, gateway, checkins, escalations)
    assert escalations.asked == [] and gateway.models == [WEAK] * 4
    assert checkins.asked[0].plan_waiting


def test_no_target_goes_straight_to_the_check_in_and_says_so(tmp_path, source):
    gateway = Gateway([READ_A] * 4)
    checkins, escalations = CheckIns(CheckInDecision.STOP), Escalations(EscalationRefusal.NO_TARGET)
    _run(tmp_path, gateway, checkins, escalations)
    assert gateway.models == [WEAK] * 4
    [checkin] = checkins.asked
    assert "Auto had no stronger eligible model to try." in checkin.text


def test_a_host_that_fails_to_move_the_turn_leaves_it_to_the_check_in(tmp_path, source):
    def broken(move: PlanningEscalation) -> EscalationGrant:
        raise RuntimeError("the host could not build the route")

    gateway = Gateway([READ_A] * 4)
    checkins = CheckIns(CheckInDecision.STOP)
    _run(tmp_path, gateway, checkins, broken)  # type: ignore[arg-type]
    assert gateway.models == [WEAK] * 4
    assert "no stronger" not in checkins.asked[0].text and "moved to" not in checkins.asked[0].text


def test_a_turn_limit_check_in_without_a_detection_never_escalates(tmp_path, source):
    reads = [f"OBSERVE: part {n}\nREAD: a.py#bytes={n}:{n + 1}\n" for n in range(3)]
    checkins, escalations = CheckIns(CheckInDecision.STOP), Escalations()
    _run(tmp_path, Gateway(reads), checkins, escalations)
    assert escalations.asked == [] and checkins.asked[0].cause == "TURN_LIMIT"


def test_one_switch_per_turn_continue_on_the_stronger_model_gets_phase_ones_nudge_and_check_in(tmp_path, source):
    gateway = Gateway([READ_A] * 11)
    checkins = CheckIns(CheckInDecision.CONTINUE, CheckInDecision.STOP)
    escalations = Escalations(GRANT)
    _run(tmp_path, gateway, checkins, escalations)
    # Episode 1: steps 1-7 (escalated at 4). Episode 2 on the stronger model: its 3 granted steps detect at 10, the
    # nudge step 11 repeats, and the check-in follows without asking to move again.
    assert gateway.models == [WEAK] * 4 + [STRONG] * 7
    assert [m.planning_steps for m in escalations.asked] == [4]
    assert [c.planning_steps for c in checkins.asked] == [7, 11]
    assert "moved to" not in checkins.asked[1].text and "no stronger" not in checkins.asked[1].text


def test_without_an_escalation_callback_phase_one_is_unchanged(tmp_path, source):
    gateway = Gateway([READ_A] * 4)
    checkins = CheckIns(CheckInDecision.STOP)
    _run(tmp_path, gateway, checkins, None)
    assert gateway.models == [WEAK] * 4 and len(checkins.asked) == 1
    assert "moved to" not in checkins.asked[0].text and "no stronger" not in checkins.asked[0].text


def test_a_halted_refusal_ends_the_run_rather_than_going_to_the_check_in(tmp_path, source):
    halted = []
    gateway, checkins = Gateway([READ_A] * 4), CheckIns()

    def halting(move: PlanningEscalation) -> EscalationRefusal:
        halted.append(True)
        return EscalationRefusal.HALTED

    result = _run(tmp_path, gateway, checkins, halting, halt=lambda: bool(halted))  # type: ignore[arg-type]
    assert checkins.asked == [] and result.stop_reason == "PLANNING_HALTED"


def test_a_host_halted_answer_is_terminal_even_when_the_runs_own_predicate_is_still_false(tmp_path, source):
    gateway, checkins = Gateway([READ_A] * 4), CheckIns(CheckInDecision.CONTINUE)
    result = _run(tmp_path, gateway, checkins, Escalations(EscalationRefusal.HALTED))
    assert checkins.asked == [] and gateway.models == [WEAK] * 4  # never a check-in, never resumed by Continue
    assert result.stop_reason == "PLANNING_HALTED"


def test_a_cancel_during_the_escalation_stops_without_the_stronger_model(tmp_path, source):
    halted = []
    gateway = Gateway([READ_A] * 4)
    checkins = CheckIns()
    result = _run(tmp_path, gateway, checkins, Escalations(GRANT, on_ask=lambda: halted.append(True)), halt=lambda: bool(halted))
    assert gateway.models == [WEAK] * 4 and checkins.asked == []
    assert result.stop_reason == "PLANNING_HALTED"


def test_the_escalation_is_recorded_without_content(tmp_path, source):
    events: list[TelemetryEvent] = []
    _run(tmp_path, Gateway([READ_A] * 7), CheckIns(CheckInDecision.STOP), Escalations(GRANT), events=events)
    assert [e.payload for e in events] == [
        {"record": "detection", "signal": "REPEATED_READ", "planning_step": 3},
        {"record": "detection", "signal": "REPEATED_READ", "planning_step": 4},
        {
            "record": "escalation",
            "signal": "REPEATED_READ",
            "planning_step": 4,
            "decision": "granted",
            "from_model": WEAK,
            "to_model": STRONG,
            "notice_delivered": False,
        },
        {"record": "detection", "signal": "REPEATED_READ", "planning_step": 7},
        {"record": "check_in", "signal": "REPEATED_READ", "planning_step": 7, "decision": "stop"},
    ]
    assert "a.py" not in str([e.model_dump() for e in events])


# --- r5: a refusal settled after the nudge also takes the episode's one escalation ------------------------------------

REFUSE = "REFUSE: The evidence is not enough for a safe change.\n"
STRONG_REFUSE = "REFUSE: The word is still not published.\n"


def test_a_refusal_after_the_nudge_escalates_and_the_stronger_model_settles_the_plan(tmp_path, source):
    # Repeats at steps 1-3 open the episode; the nudge step 4 refuses; the grant sets that refusal aside.
    gateway = Gateway([READ_A] * 3 + [REFUSE, FINAL_PLAN])
    checkins, escalations = CheckIns(CheckInDecision.CONTINUE), Escalations(GRANT)
    result = _run(tmp_path, gateway, checkins, escalations)

    assert gateway.models == [WEAK] * 4 + [STRONG]
    [move] = escalations.asked
    assert move.planning_steps == 4
    [checkin] = checkins.asked
    assert checkin.plan_waiting and not checkin.refusal_waiting and "then moved to strong/model" in checkin.text
    assert (result.stop_reason, result.plan_text, result.refusal_reason) == (None, FINAL_PLAN, None)


def test_a_refusal_after_the_nudge_escalates_and_the_stronger_models_own_refusal_waits_for_the_check_in(tmp_path, source):
    gateway = Gateway([READ_A] * 3 + [REFUSE, STRONG_REFUSE])
    checkins = CheckIns(CheckInDecision.STOP)
    result = _run(tmp_path, gateway, checkins, Escalations(GRANT))

    assert gateway.models == [WEAK] * 4 + [STRONG]
    [checkin] = checkins.asked
    assert checkin.refusal_waiting and "then moved to strong/model" in checkin.text
    assert "The model then refused: The word is still not published." in checkin.text
    assert (result.stop_reason, result.refusal_reason) == ("PLANNING_MODEL_REFUSED", "The word is still not published.")


@pytest.mark.parametrize("refusal", [EscalationRefusal.NO_TARGET, EscalationRefusal.FAILED])
def test_a_refusal_after_the_nudge_with_no_grant_keeps_the_original_refusal_for_the_check_in(tmp_path, source, refusal):
    gateway = Gateway([READ_A] * 3 + [REFUSE])
    checkins = CheckIns(CheckInDecision.STOP)
    result = _run(tmp_path, gateway, checkins, Escalations(refusal))

    assert gateway.models == [WEAK] * 4
    [checkin] = checkins.asked
    assert checkin.refusal_waiting and "The model then refused: The evidence is not enough for a safe change." in checkin.text
    assert ("Auto had no stronger eligible model to try." in checkin.text) is (refusal is EscalationRefusal.NO_TARGET)
    assert (result.stop_reason, result.refusal_reason) == ("PLANNING_MODEL_REFUSED", "The evidence is not enough for a safe change.")


def test_a_first_refusal_with_no_episode_stays_a_refusal_and_never_escalates(tmp_path, source):
    escalations = Escalations()
    result = _run(tmp_path, Gateway([REFUSE]), CheckIns(), escalations)
    assert escalations.asked == []
    assert (result.stop_reason, result.refusal_reason) == ("PLANNING_MODEL_REFUSED", "The evidence is not enough for a safe change.")


def test_without_an_escalation_callback_a_refusal_after_the_nudge_waits_for_the_check_in_as_in_phase_one(tmp_path, source):
    checkins = CheckIns(CheckInDecision.STOP)
    gateway = Gateway([READ_A] * 3 + [REFUSE])
    _run(tmp_path, gateway, checkins, None)
    assert gateway.models == [WEAK] * 4 and checkins.asked[0].refusal_waiting
