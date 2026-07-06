from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Generic, TypeVar

from optimus.gates.fitness import CompositeGateError, CompositeGateResult, FitnessCheck
from optimus.gates.mutation_flow import ShadowWorkspaceMutationRunner
from optimus.retry.policy import RetryAction, RetryDecision, RetryPolicy, classify_failure
from optimus.runtime.state import RuntimeContext
from optimus.telemetry.events import TelemetryEvent

T = TypeVar("T")


@dataclass(frozen=True)
class GatedAttempt(Generic[T]):
    attempt: int
    candidate: T
    gate_result: CompositeGateResult
    failure_summary: str | None
    cost_usd: Decimal = Decimal("0")


@dataclass(frozen=True)
class GatedRetryResult(Generic[T]):
    succeeded: bool
    retry_count: int
    attempts: tuple[GatedAttempt[T], ...]
    runtime_context: RuntimeContext

    @property
    def final_attempt(self) -> GatedAttempt[T]:
        return self.attempts[-1]


class GatedRetryRunner:
    def __init__(
        self,
        *,
        policy: RetryPolicy | None = None,
        sleep_ms: Callable[[int], None] | None = None,
        event_sink: Callable[[TelemetryEvent], None] | None = None,
        run_id: str = "gated-retry",
        session_id: str | None = None,
    ) -> None:
        self._policy = policy or RetryPolicy()
        self._sleep_ms = sleep_ms or _sleep_ms
        self._event_sink = event_sink
        self._run_id = run_id
        self._session_id = session_id

    def run(
        self,
        *,
        context: RuntimeContext,
        workspace_root: str | Path,
        checks_factory: Callable[[T, Path], tuple[FitnessCheck, ...]],
        plan_candidate: Callable[[int, tuple[str, ...]], T],
        apply_candidate: Callable[[T, Path], object],
        candidate_cost_usd: Callable[[T], Decimal],
    ) -> GatedRetryResult[T]:
        attempts: list[GatedAttempt[T]] = []
        prior_failure_summaries: list[str] = []
        attempt = 1
        while True:
            candidate = plan_candidate(attempt, tuple(prior_failure_summaries))
            cost_usd = candidate_cost_usd(candidate)
            gate_result = ShadowWorkspaceMutationRunner(
                checks_factory=lambda shadow_root, bound_candidate=candidate: checks_factory(bound_candidate, shadow_root)
            ).run(
                context=context,
                workspace_root=workspace_root,
                apply_candidate=lambda shadow_root, bound_candidate=candidate: apply_candidate(bound_candidate, shadow_root),
            )
            self._emit_fitness_gate(gate_result=gate_result, attempt=attempt, cost_usd=cost_usd)
            failure_summary = None
            if gate_result.passed:
                attempts.append(
                    GatedAttempt(
                        attempt=attempt,
                        candidate=candidate,
                        gate_result=gate_result,
                        failure_summary=None,
                        cost_usd=cost_usd,
                    )
                )
                return GatedRetryResult(
                    succeeded=True,
                    retry_count=attempt - 1,
                    attempts=tuple(attempts),
                    runtime_context=replace(
                        context,
                        retry_count=attempt - 1,
                        failure_context=None,
                        user_escalation=False,
                    ),
                )

            failure_error = CompositeGateError(gate_result)
            failure_summary = str(failure_error)
            prior_failure_summaries.append(failure_summary)
            attempts.append(
                GatedAttempt(
                    attempt=attempt,
                    candidate=candidate,
                    gate_result=gate_result,
                    failure_summary=failure_summary,
                    cost_usd=cost_usd,
                )
            )
            decision = self._policy.decide(classify_failure(failure_error), attempt=attempt)
            self._emit_retry_decision(decision=decision, retry_count=max(attempt - 1, 0))
            if decision.action is not RetryAction.RETRY:
                return GatedRetryResult(
                    succeeded=False,
                    retry_count=max(attempt - 1, 0),
                    attempts=tuple(attempts),
                    runtime_context=replace(
                        context,
                        retry_count=max(attempt - 1, 0),
                        failure_context=failure_summary,
                        user_escalation=True,
                    ),
                )
            self._sleep_ms(decision.delay_ms)
            attempt += 1

    def _emit_retry_decision(self, *, decision: RetryDecision, retry_count: int) -> None:
        if self._event_sink is None:
            return
        self._event_sink(
            TelemetryEvent.retry_decision(
                run_id=self._run_id,
                session_id=self._session_id,
                request_id=f"attempt-{decision.attempt}",
                occurred_at=datetime.now(tz=UTC),
                attempt=decision.attempt,
                retry_count=retry_count,
                failure_kind=decision.classification.kind.value,
                action=decision.action.value,
                delay_ms=decision.delay_ms,
                disposition=decision.reason,
            )
        )

    def _emit_fitness_gate(self, *, gate_result: CompositeGateResult, attempt: int, cost_usd: Decimal) -> None:
        if self._event_sink is None:
            return
        self._event_sink(
            TelemetryEvent.fitness_gate(
                run_id=self._run_id,
                session_id=self._session_id,
                request_id=f"attempt-{attempt}",
                occurred_at=datetime.now(tz=UTC),
                passed=gate_result.passed,
                required_gate_names=gate_result.required_gate_names,
                failed_gate_names=gate_result.failed_gate_names,
                duration_ms=gate_result.duration_ms,
                cost_usd=cost_usd,
            )
        )


def _sleep_ms(delay_ms: int) -> None:
    import time

    time.sleep(delay_ms / 1000)
