from __future__ import annotations

from decimal import Decimal

from optimus.gates.fitness import GateResult
from optimus.retry.gated_run import GatedAttempt, GatedRetryRunner
from optimus.retry.policy import RetryPolicy
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.state import AgentState, RuntimeContext
from optimus.telemetry.events import TelemetryEventKind


class SequenceGate:
    def __init__(self) -> None:
        self.calls = 0

    @property
    def name(self) -> str:
        return "fitness"

    @property
    def required(self) -> bool:
        return True

    def run(self) -> GateResult:
        self.calls += 1
        if self.calls < 3:
            return GateResult.fail(name=self.name, summary=f"failure {self.calls}")
        return GateResult.pass_(name=self.name, summary="passed")


def approved_context() -> RuntimeContext:
    return RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.EXECUTING,
        approval_granted=True,
        user_approval_id="approval-1",
    )


def test_gate_failures_replan_with_prior_failure_summaries(tmp_path):
    gate = SequenceGate()
    candidates: list[tuple[int, tuple[str, ...]]] = []

    def plan_candidate(attempt: int, prior_failures: tuple[str, ...]) -> str:
        candidates.append((attempt, prior_failures))
        return f"candidate-{attempt}"

    runner = GatedRetryRunner(
        policy=RetryPolicy(max_retries=3, base_delay_ms=1, jitter_ms=(0,)),
        sleep_ms=lambda delay_ms: None,
    )

    workspace = tmp_path
    result = runner.run(
        context=approved_context(),
        workspace_root=workspace,
        checks_factory=lambda candidate, shadow_root: (gate,),
        plan_candidate=plan_candidate,
        apply_candidate=lambda candidate, shadow_root: (shadow_root / "candidate.txt").write_text(candidate, encoding="utf-8"),
        candidate_cost_usd=lambda candidate: Decimal("0"),
    )
    assert result.retry_count == 2
    assert result.runtime_context.retry_count == 2
    assert result.runtime_context.user_escalation is False
    assert candidates == [
        (1, ()),
        (2, ("required fitness gates failed: fitness",)),
        (3, ("required fitness gates failed: fitness", "required fitness gates failed: fitness")),
    ]
    assert (workspace / "candidate.txt").read_text(encoding="utf-8") == "candidate-3"


def test_retry_runner_returns_failed_attempt_without_promoting_when_budget_exhausted(tmp_path):
    target = tmp_path / "candidate.txt"

    class AlwaysFailingGate:
        name = "fitness"
        required = True

        def run(self) -> GateResult:
            return GateResult.fail(name=self.name, summary="still failing")

    runner = GatedRetryRunner(
        policy=RetryPolicy(max_retries=1, base_delay_ms=1, jitter_ms=(0,)),
        sleep_ms=lambda delay_ms: None,
    )

    result = runner.run(
        context=approved_context(),
        workspace_root=tmp_path,
        checks_factory=lambda candidate, shadow_root: (AlwaysFailingGate(),),
        plan_candidate=lambda attempt, prior_failures: f"candidate-{attempt}",
        apply_candidate=lambda candidate, shadow_root: (shadow_root / "candidate.txt").write_text(candidate, encoding="utf-8"),
        candidate_cost_usd=lambda candidate: Decimal("0"),
    )

    assert result.succeeded is False
    assert result.retry_count == 1
    assert result.runtime_context.retry_count == 1
    assert result.runtime_context.user_escalation is True
    assert result.runtime_context.failure_context == "required fitness gates failed: fitness"
    assert isinstance(result.final_attempt, GatedAttempt)
    assert not target.exists()


def test_fitness_gate_telemetry_uses_candidate_cost(tmp_path):
    events = []

    class PassingGate:
        name = "fitness"
        required = True

        def run(self) -> GateResult:
            return GateResult.pass_(name=self.name, summary="passed")

    runner = GatedRetryRunner(
        policy=RetryPolicy(max_retries=1, base_delay_ms=1, jitter_ms=(0,)),
        sleep_ms=lambda delay_ms: None,
        event_sink=events.append,
    )

    result = runner.run(
        context=approved_context(),
        workspace_root=tmp_path,
        checks_factory=lambda candidate, shadow_root: (PassingGate(),),
        plan_candidate=lambda attempt, prior_failures: "candidate",
        apply_candidate=lambda candidate, shadow_root: (shadow_root / "candidate.txt").write_text(candidate, encoding="utf-8"),
        candidate_cost_usd=lambda candidate: Decimal("0.019"),
    )

    assert result.succeeded is True
    fitness_events = [event for event in events if event.kind is TelemetryEventKind.FITNESS_GATE]
    assert fitness_events
    assert fitness_events[0].payload["cost_usd"] == Decimal("0.019")
