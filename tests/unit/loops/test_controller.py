from datetime import UTC, datetime, timedelta
from decimal import Decimal

from optimus.loops.controller import GoalLoopController
from optimus.loops.ledger import InMemoryProgressLedger
from optimus.loops.models import (
    CompletionEvaluation,
    IterationOutcome,
    IterationState,
    LoopBudgetPolicy,
    LoopStopReason,
    LoopToolExecutorProtocol,
)


class StaticRunner:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def run_iteration(self, state: IterationState, tools: LoopToolExecutorProtocol) -> IterationOutcome:
        self.calls += 1
        return self.outcomes.pop(0)


class StaticEvaluator:
    def __init__(self, evaluations):
        self.evaluations = list(evaluations)

    def evaluate(self, state: IterationState, ledger: InMemoryProgressLedger) -> CompletionEvaluation:
        return self.evaluations.pop(0)


def state(started_at: datetime | None = None) -> IterationState:
    return IterationState(
        run_id="run-1",
        session_id="session-1",
        goal="Migrate auth call sites",
        completion_condition="tests/unit/auth pass",
        started_at=started_at or datetime(2026, 7, 6, tzinfo=UTC),
    )


def policy() -> LoopBudgetPolicy:
    return LoopBudgetPolicy(max_iterations=3, max_budget_credits=Decimal("1.0"), max_wall_clock_minutes=10)


class FakeLoopTools:
    pass


def loop_tools(tmp_path) -> LoopToolExecutorProtocol:
    _ = tmp_path
    return FakeLoopTools()


def test_loop_stops_on_completion(tmp_path):
    ledger = InMemoryProgressLedger()
    runner = StaticRunner([IterationOutcome(summary="updated", cost_credits=Decimal("0.1"))])
    evaluator = StaticEvaluator([CompletionEvaluation(completed=True, reason="tests pass", cost_credits=Decimal("0.01"))])
    controller = GoalLoopController(policy=policy(), runner=runner, tools=loop_tools(tmp_path), evaluator=evaluator, ledger=ledger, now=lambda: datetime(2026, 7, 6, tzinfo=UTC))

    result = controller.run(state())

    assert result.stop_reason is LoopStopReason.COMPLETED
    assert result.state.iteration == 1
    assert result.state.credits_spent == Decimal("0.11")
    assert ledger.entries(run_id="run-1")[-1].stop_reason is LoopStopReason.COMPLETED


def test_loop_stops_on_max_iterations(tmp_path):
    ledger = InMemoryProgressLedger()
    runner = StaticRunner([IterationOutcome(summary="not done"), IterationOutcome(summary="not done"), IterationOutcome(summary="not done")])
    evaluator = StaticEvaluator([CompletionEvaluation(completed=False, reason="not done")] * 3)
    controller = GoalLoopController(policy=policy(), runner=runner, tools=loop_tools(tmp_path), evaluator=evaluator, ledger=ledger, now=lambda: datetime(2026, 7, 6, tzinfo=UTC))

    result = controller.run(state())

    assert result.stop_reason is LoopStopReason.MAX_ITERATIONS
    assert runner.calls == 3


def test_loop_stops_on_budget_exhaustion(tmp_path):
    ledger = InMemoryProgressLedger()
    runner = StaticRunner([IterationOutcome(summary="expensive", cost_credits=Decimal("1.25"))])
    evaluator = StaticEvaluator([])
    controller = GoalLoopController(policy=policy(), runner=runner, tools=loop_tools(tmp_path), evaluator=evaluator, ledger=ledger, now=lambda: datetime(2026, 7, 6, tzinfo=UTC))

    result = controller.run(state())

    assert result.stop_reason is LoopStopReason.BUDGET_EXHAUSTED
    assert evaluator.evaluations == []


def test_loop_stops_on_deterministic_completion_without_evaluator(tmp_path):
    ledger = InMemoryProgressLedger()
    runner = StaticRunner([IterationOutcome(summary="tests pass", deterministic_completion=True, evidence={"pytest": "passed"})])
    evaluator = StaticEvaluator([])
    controller = GoalLoopController(policy=policy(), runner=runner, tools=loop_tools(tmp_path), evaluator=evaluator, ledger=ledger, now=lambda: datetime(2026, 7, 6, tzinfo=UTC))

    result = controller.run(state())

    assert result.stop_reason is LoopStopReason.COMPLETED
    assert evaluator.evaluations == []
    assert ledger.entries(run_id="run-1")[-1].evidence == {"pytest": "passed"}


def test_loop_stops_on_wall_clock_before_next_iteration(tmp_path):
    start = datetime(2026, 7, 6, tzinfo=UTC)
    ledger = InMemoryProgressLedger()
    runner = StaticRunner([IterationOutcome(summary="should not run")])
    evaluator = StaticEvaluator([])
    controller = GoalLoopController(
        policy=policy(),
        runner=runner,
        tools=loop_tools(tmp_path),
        evaluator=evaluator,
        ledger=ledger,
        now=lambda: start + timedelta(minutes=11),
    )

    result = controller.run(state(started_at=start))

    assert result.stop_reason is LoopStopReason.WALL_CLOCK
    assert runner.calls == 0


def test_loop_stops_on_repeated_failure(tmp_path):
    ledger = InMemoryProgressLedger()
    runner = StaticRunner(
        [
            IterationOutcome(summary="failed", failure_signature="same"),
            IterationOutcome(summary="failed", failure_signature="same"),
            IterationOutcome(summary="failed", failure_signature="same"),
        ]
    )
    evaluator = StaticEvaluator([CompletionEvaluation(completed=False, reason="not done")] * 2)
    controller = GoalLoopController(policy=policy(), runner=runner, tools=loop_tools(tmp_path), evaluator=evaluator, ledger=ledger, now=lambda: datetime(2026, 7, 6, tzinfo=UTC))

    result = controller.run(state())

    assert result.stop_reason is LoopStopReason.REPEATED_FAILURE
    assert result.state.repeated_failure_count == 3
    assert len(evaluator.evaluations) == 0


def test_loop_stops_on_human_halt(tmp_path):
    ledger = InMemoryProgressLedger()
    runner = StaticRunner([])
    evaluator = StaticEvaluator([])
    controller = GoalLoopController(policy=policy(), runner=runner, tools=loop_tools(tmp_path), evaluator=evaluator, ledger=ledger, now=lambda: datetime(2026, 7, 6, tzinfo=UTC))

    result = controller.run(state().request_halt())

    assert result.stop_reason is LoopStopReason.HUMAN_HALT
    assert runner.calls == 0


def test_stop_reason_precedence_when_multiple_limits_hold(tmp_path):
    start = datetime(2026, 7, 6, tzinfo=UTC)
    state_with_all_limits = IterationState(
        run_id="run-1",
        session_id="session-1",
        goal="Migrate auth call sites",
        completion_condition="tests/unit/auth pass",
        started_at=start,
        iteration=3,
        credits_spent=Decimal("1.25"),
        repeated_failure_count=3,
    )
    controller = GoalLoopController(
        policy=policy(),
        runner=StaticRunner([]),
        tools=loop_tools(tmp_path),
        evaluator=StaticEvaluator([]),
        ledger=InMemoryProgressLedger(),
        now=lambda: start + timedelta(minutes=11),
    )

    result = controller.run(state_with_all_limits)

    assert result.stop_reason is LoopStopReason.REPEATED_FAILURE


def test_mid_loop_human_halt_is_checked_between_iterations(tmp_path):
    ledger = InMemoryProgressLedger()
    runner = StaticRunner([IterationOutcome(summary="first"), IterationOutcome(summary="should not run")])
    evaluator = StaticEvaluator([CompletionEvaluation(completed=False, reason="not done")])
    checks = iter((False, False, True))
    controller = GoalLoopController(
        policy=policy(),
        runner=runner,
        tools=loop_tools(tmp_path),
        evaluator=evaluator,
        ledger=ledger,
        halt_requested=lambda: next(checks),
        now=lambda: datetime(2026, 7, 6, tzinfo=UTC),
    )

    result = controller.run(state())

    assert result.stop_reason is LoopStopReason.HUMAN_HALT
    assert runner.calls == 1
