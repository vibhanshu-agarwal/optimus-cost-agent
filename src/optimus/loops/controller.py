from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from optimus.loops.ledger import ProgressLedger, ProgressLedgerEntry
from optimus.loops.models import (
    CompletionEvaluatorProtocol,
    IterationOutcome,
    IterationState,
    LoopBudgetPolicy,
    LoopStopReason,
    LoopToolExecutorProtocol,
)
from optimus.telemetry.events import TelemetryEvent


class IterationRunner(Protocol):
    def run_iteration(self, state: IterationState, tools: LoopToolExecutorProtocol) -> IterationOutcome:
        raise NotImplementedError


class GoalLoopResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    state: IterationState
    stop_reason: LoopStopReason
    summary: str


class GoalLoopController:
    """
    Manages and executes bounded goal-oriented loops while enforcing limits defined by
    a policy, and evaluating progress and outcomes with configurable tools and evaluators.

    This controller interacts with an iteration runner, tools, an evaluator, and a ledger
    to facilitate iterative execution of a goal loop. It also supports runtime stop checks
    through user-provided callbacks to ensure flexible termination based on external
    conditions. The goal loop concludes either when deterministic completion is achieved
    or when any termination condition specified by the policy is met.

    :ivar _policy: Loop budget policy defining iteration constraints and limits.
    :type _policy: LoopBudgetPolicy
    :ivar _runner: Runner responsible for executing individual iterations.
    :type _runner: IterationRunner
    :ivar _tools: Executor protocol providing guarded tools for loop execution.
    :type _tools: LoopToolExecutorProtocol
    :ivar _evaluator: Evaluator for assessing intermediate and final loop completions.
    :type _evaluator: CompletionEvaluatorProtocol
    :ivar _ledger: Progress ledger for recording milestones and loop state progressions.
    :type _ledger: ProgressLedger
    :ivar _halt_requested: Optional callable indicating if a halt is requested externally.
    :type _halt_requested: Callable[[], bool] | None
    :ivar _now: Optional callable to fetch the current time for time-related checks.
    :type _now: Callable[[], datetime] | None
    :ivar _event_sink: Optional telemetry event sink for emitting loop termination data.
    :type _event_sink: Callable[[TelemetryEvent], None] | None
    """
    def __init__(
        self,
        *,
        policy: LoopBudgetPolicy,
        runner: IterationRunner,
        tools: LoopToolExecutorProtocol,
        evaluator: CompletionEvaluatorProtocol,
        ledger: ProgressLedger,
        halt_requested: Callable[[], bool] | None = None,
        now: Callable[[], datetime] | None = None,
        event_sink: Callable[[TelemetryEvent], None] | None = None,
    ) -> None:
        """Run bounded goal loops with guarded tools and completion evaluation.

        ``halt_requested`` and ``now`` may be invoked more than once per iteration
        because stop checks run before and after each turn. Keep both callbacks cheap
        and idempotent-safe.
        """
        self._policy = policy
        self._runner = runner
        self._tools = tools
        self._evaluator = evaluator
        self._ledger = ledger
        self._halt_requested = halt_requested or (lambda: False)
        self._now = now or (lambda: datetime.now(tz=UTC))
        self._event_sink = event_sink

    def run(self, initial_state: IterationState) -> GoalLoopResult:
        state = initial_state
        # Executes iterative goal loop with termination and evaluation checks
        while True:
            pre_stop = self._stop_reason(state)
            if pre_stop is not None:
                self._record(state=state, summary=f"stopped before iteration: {pre_stop.value}", stop_reason=pre_stop)
                self._emit_stop(state=state, stop_reason=pre_stop, summary=pre_stop.value)
                return GoalLoopResult(state=state, stop_reason=pre_stop, summary=pre_stop.value)

            outcome = self._runner.run_iteration(state.with_runtime_limits(policy=self._policy), self._tools)
            state = state.record_outcome(outcome)
            self._record(
                state=state,
                summary=outcome.summary,
                stop_reason=None,
                failure_signature=outcome.failure_signature,
                cost_credits=outcome.cost_credits,
                evidence=outcome.evidence,
            )

            if outcome.deterministic_completion:
                self._record(
                    state=state,
                    summary=outcome.summary,
                    stop_reason=LoopStopReason.COMPLETED,
                    evidence=outcome.evidence,
                )
                self._emit_stop(state=state, stop_reason=LoopStopReason.COMPLETED, summary=outcome.summary)
                return GoalLoopResult(state=state, stop_reason=LoopStopReason.COMPLETED, summary=outcome.summary)

            post_stop = self._stop_reason(state)
            if post_stop is not None:
                self._record(state=state, summary=f"stopped after iteration: {post_stop.value}", stop_reason=post_stop)
                self._emit_stop(state=state, stop_reason=post_stop, summary=post_stop.value)
                return GoalLoopResult(state=state, stop_reason=post_stop, summary=post_stop.value)

            evaluation = self._evaluator.evaluate(state, self._ledger)
            state = state.record_completion_evaluation(evaluation)
            self._record(
                state=state,
                summary=f"completion evaluation: {evaluation.reason}",
                stop_reason=None,
                cost_credits=evaluation.cost_credits,
            )
            if evaluation.completed:
                self._record(state=state, summary=evaluation.reason, stop_reason=LoopStopReason.COMPLETED)
                self._emit_stop(state=state, stop_reason=LoopStopReason.COMPLETED, summary=evaluation.reason)
                return GoalLoopResult(state=state, stop_reason=LoopStopReason.COMPLETED, summary=evaluation.reason)

    def _emit_stop(self, *, state: IterationState, stop_reason: LoopStopReason, summary: str) -> None:
        if self._event_sink is None:
            return
        self._event_sink(
            TelemetryEvent.goal_loop(
                run_id=state.run_id,
                session_id=state.session_id,
                request_id=f"{state.run_id}:loop:{state.iteration}",
                occurred_at=self._now(),
                iteration=state.iteration,
                stop_reason=stop_reason.value,
                credits_spent=state.credits_spent,
                max_budget_credits=self._policy.max_budget_credits,
                summary=summary,
            )
        )

    def _stop_reason(self, state: IterationState) -> LoopStopReason | None:
        """Evaluates termination conditions against policy and state constraints"""
        if state.human_halt_requested or self._halt_requested():
            return LoopStopReason.HUMAN_HALT
        if state.repeated_failure_count >= self._policy.repeated_failure_limit:
            return LoopStopReason.REPEATED_FAILURE
        if state.credits_spent >= self._policy.max_budget_credits:
            return LoopStopReason.BUDGET_EXHAUSTED
        if state.elapsed_minutes(now=self._now()) >= self._policy.max_wall_clock_minutes:
            return LoopStopReason.WALL_CLOCK
        if state.iteration >= self._policy.max_iterations:
            return LoopStopReason.MAX_ITERATIONS
        return None

    def _record(
        self,
        *,
        state: IterationState,
        summary: str,
        stop_reason: LoopStopReason | None,
        failure_signature: str | None = None,
        cost_credits: Decimal = Decimal("0"),
        evidence: dict[str, str] | None = None,
    ) -> None:
        self._ledger.append(
            ProgressLedgerEntry(
                run_id=state.run_id,
                session_id=state.session_id,
                iteration=state.iteration,
                goal=state.goal,
                summary=summary,
                cost_credits=cost_credits,
                stop_reason=stop_reason,
                failure_signature=failure_signature,
                evidence=evidence or {},
                occurred_at=self._now(),
            )
        )
