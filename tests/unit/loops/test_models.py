from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from optimus.loops.models import IterationOutcome, IterationState, LoopBudgetPolicy, LoopStopReason


def test_loop_budget_policy_requires_positive_bounds():
    with pytest.raises(ValidationError):
        LoopBudgetPolicy(max_iterations=0, max_budget_credits=Decimal("1"), max_wall_clock_minutes=5)

    with pytest.raises(ValidationError):
        LoopBudgetPolicy(max_iterations=1, max_budget_credits=Decimal("0"), max_wall_clock_minutes=5)

    with pytest.raises(ValidationError):
        LoopBudgetPolicy(max_iterations=1, max_budget_credits=Decimal("1"), max_wall_clock_minutes=0)


def test_iteration_state_requires_timezone_aware_start_time():
    with pytest.raises(ValidationError, match="started_at must be timezone-aware"):
        IterationState(
            run_id="run-1",
            session_id=None,
            goal="Migrate auth call sites",
            completion_condition="tests/unit/auth pass",
            started_at=datetime(2026, 7, 6),
        )


def test_iteration_state_tracks_budget_and_repeated_failures():
    started = datetime.now(tz=UTC)
    state = IterationState(
        run_id="run-1",
        session_id="session-1",
        goal="Migrate auth call sites",
        completion_condition="tests/unit/auth pass",
        started_at=started,
    )

    failed_once = state.record_outcome(
        IterationOutcome(
            summary="pytest failed",
            cost_credits=Decimal("0.25"),
            failure_signature="tests/unit/auth/test_login.py::test_login",
        )
    )
    failed_twice = failed_once.record_outcome(
        IterationOutcome(
            summary="same pytest failed",
            cost_credits=Decimal("0.10"),
            failure_signature="tests/unit/auth/test_login.py::test_login",
        )
    )

    assert failed_twice.iteration == 2
    assert failed_twice.credits_spent == Decimal("0.35")
    assert failed_twice.repeated_failure_count == 2
    assert failed_twice.last_failure_signature == "tests/unit/auth/test_login.py::test_login"
    assert failed_twice.elapsed_minutes(now=started + timedelta(minutes=3)) == 3


def test_loop_stop_reason_values_are_stable_for_traces():
    assert {reason.value for reason in LoopStopReason} == {
        "COMPLETED",
        "MAX_ITERATIONS",
        "BUDGET_EXHAUSTED",
        "WALL_CLOCK",
        "REPEATED_FAILURE",
        "HUMAN_HALT",
    }
