# Retry, Fitness Gates, Golden Tasks, and Release Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bounded retry/fail-closed behavior, composite fitness-gate execution, golden-task regression checks, and a one-key Phase 1 release-gate runner.

**Architecture:** Build a deterministic validation layer around the existing runtime, gateway, guardrail, usage, and telemetry modules. Retry policy classifies failures before side effects; fitness gates evaluate candidate outputs before mutation callbacks run; golden tasks validate expected mode/tools/cost/final state from versioned fixtures; the release runner composes transport, mode, gateway, evidence, cost, telemetry, coverage, guardrail, golden-task, and one-key credential gates into a single report.

**Tech Stack:** Python >=3.14, pydantic >=2.8, pytest, pytest-asyncio, coverage.py, pytest-cov, stdlib `dataclasses`, stdlib `datetime`, stdlib `decimal`, stdlib `enum`, stdlib `json`, stdlib `os`, stdlib `pathlib`, stdlib `subprocess`, stdlib `time`, existing `optimus.gateway`, `optimus.runtime`, `optimus.tools`, `optimus.guardrails`, `optimus.usage`, and `optimus.telemetry` modules. No new runtime dependency is required for the initial deterministic golden-task evaluator.

---

## Source Anchors

- `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, Plan 8: implement failure classification, retry/backoff policy, max 3 transient retries, composite gate results, golden task fixtures, and release-gate runner.
- `docs/superpowers/plans/2026-07-04-usage-accounting-evidence-ledger-observability.md`: Plan 7 provides usage accounting, telemetry events, JSONL writer, Redis adapter boundaries, and Gateway-managed observability export that Plan 8 should compose.
- `docs/Optimus-Cost-Agent-Architecture-v2.15.pdf`, sections 3, 6, 9, 11A, and 12: generated code is validated by architectural fitness functions before working-tree mutation; retry and validation traces go through Gateway-managed observability; coverage is a release gate and not a substitute for agent-quality evals.
- `docs/Optimus-Cost-Agent-LLD-v2.38.pdf`, section 11: Sprint 1 checklist and final release gate require composite-gate fail-closed behavior, usage/cost reconciliation, coverage >= 80%, Gateway-managed LangSmith trace export, and one-key Plan-mode plus Agent-mode runs with no provider keys locally.
- `docs/Optimus-Cost-Agent-Test-Strategy-v1.4.pdf`, sections 9, 12, and 13: transient vs permanent failure classification, retry cap of 3, no partial writes on failure, golden task expected mode/tools/cost/final state, ordered Phase 1 release gates, and final one-key go/no-go gate.
- `docs/agent-evaluation-tooling-research.md`: initial Plan 8 golden-task scoring should be deterministic and keyless; LLM-judged evaluation remains Gateway-routed only and must not require local provider or LangSmith keys.
- `AGENTS.md`: local runtime credentials remain limited to `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; failed fitness gates must not leave partial writes in the working tree; mutation paths pass through `MutationGuard` / `assert_mutation_allowed()`.

## Scope

### In Scope

- Failure classification for transient gateway/provider failures, rate limits, permanent gateway failures, policy violations, budget exhaustion, malformed gateway responses, and composite fitness-gate failures.
- Retry decisions with bounded transient retries, exponential backoff with deterministic jitter injection for tests, no retry for permanent failures, and user escalation after retry exhaustion.
- Retry metadata suitable for telemetry and run metadata: attempt number, retry count, failure kind, decision action, delay, final disposition, and prior failure summaries.
- Composite fitness-gate result models and a gate runner that records every check result, fails closed on exceptions, and blocks mutation unless every required gate passes.
- A validated mutation flow that applies candidates in a shadow workspace, runs gates against that shadow state, and promotes changes to the real workspace only after all required gates pass.
- Golden task fixture schema, deterministic evaluator, and release-runner adapter that evaluates actual `GoldenTaskResult` records produced by a golden-task harness instead of merely counting fixtures.
- Release-gate runner with ordered gates, command/callable adapters, JSON report output, and a default Phase 1 gate list.
- One-key local credential scanner that fails if any provider key is resolvable from environment, selected local config files, or serialized process-state snapshots used by the runner, including `.env`, JSON, YAML, and Python/PowerShell assignment forms.
- Telemetry event constructors plus runner integration for retry decisions, fitness-gate outcomes, golden-task results, and release-gate reports.
- Tests for narrow unit behavior, integration retry/gate flows, golden fixture evaluation, release-runner ordering, and focused coverage.

### Out of Scope

- Real staging Gateway calls in unit tests. The release runner supports staging commands, but unit/integration tests inject fakes.
- Adding DeepEval, Ragas, PyRIT, or LangSmith SDK dependencies. Deterministic golden-task checks are implemented now; LLM-scored evaluation remains a Gateway-only extension.
- Context Window Optimization thresholds from Plan 10. Plan 8 reserves report fields for future offline promotion gates but does not enforce cost-savings, regret, latency, or cache-hit calibration placeholders.
- Plan 9 bounded loop and skill-loading implementation. Plan 8 may evaluate retry loops and release gates, but it does not implement `GoalLoopController` or `SkillRegistry`.
- Rewriting existing guardrail, MCP trust, usage accounting, or telemetry behavior from Plans 5, 6, 6.5, and 7.

### Dependency Notes

- Plan 7 artifacts are present in `src/optimus/usage` and `src/optimus/telemetry`; Plan 8 should extend those modules, not create a second telemetry path.
- Existing mutation primitives live in `src/optimus/tools/mutation_tools.py` and already call `assert_mutation_allowed()` plus `PreToolGuard`.
- Existing `RuntimeContext` has `retry_count`, `max_retries`, `failure_context`, and `user_escalation`; Plan 8 should reuse these fields where useful and avoid incompatible state names.
- Existing `GatewayHttpError` has `status_code`; classification should map 408, 409, 425, 429, and 5xx to transient by default, and map 400, 401, 403, 404, 422, and malformed response errors to permanent unless a narrower policy says otherwise.

## File Structure

- Create: `src/optimus/retry/__init__.py` - public retry exports.
- Create: `src/optimus/retry/policy.py` - failure classes, classifier, retry decisions, backoff policy, and `RetryController`.
- Create: `src/optimus/retry/gated_run.py` - retry orchestration that replans candidates after gate failures and mutates only after validation succeeds.
- Create: `src/optimus/gates/__init__.py` - public gate exports.
- Create: `src/optimus/gates/fitness.py` - gate result models, composite gate runner, and fail-closed error handling.
- Create: `src/optimus/gates/mutation_flow.py` - validated mutation wrapper that promotes shadow-workspace changes only after composite gates pass.
- Create: `src/optimus/gates/shadow_workspace.py` - temporary shadow workspace creation, candidate application, diff capture, and promotion/rollback boundary.
- Create: `src/optimus/golden/__init__.py` - public golden-task exports.
- Create: `src/optimus/golden/tasks.py` - golden task fixture models, loader, tool trajectory evaluator, and cost/final-state checks.
- Create: `src/optimus/golden/runner.py` - golden task harness Protocol and suite evaluator used by the release gate.
- Create: `src/optimus/release/__init__.py` - public release-gate exports.
- Create: `src/optimus/release/credentials.py` - one-key provider credential scanner.
- Create: `src/optimus/release/runner.py` - release gate model, command/callable adapters, runner, and JSON report model.
- Create: `src/optimus/release/defaults.py` - default Phase 1 release-gate command list and golden-task callable gate builder.
- Create: `src/optimus/telemetry/redaction.py` - public redaction helper shared by telemetry events and release reports.
- Modify: `src/optimus/telemetry/events.py` - add retry, fitness, golden-task, and release-gate event kinds and constructors using the public redaction helper.
- Modify: `src/optimus/telemetry/__init__.py` - export `redact_for_telemetry` and any newly public telemetry event names if needed.
- Create: `tests/fixtures/golden_tasks/phase1_golden_tasks.json` - versioned deterministic golden-task expectations from Test Strategy section 12.
- Create: `tools/run_phase1_release_gate.py` - local entry point for the ordered release-gate runner.
- Modify: `README.md` - add a short Phase 1 release-gate usage note.
- Create: `tests/unit/retry/test_policy.py` - retry classification/backoff tests.
- Create: `tests/unit/retry/test_gated_run.py` - retry orchestration and failure-context injection tests.
- Create: `tests/unit/gates/test_fitness.py` - composite gate result tests.
- Create: `tests/unit/gates/test_mutation_flow.py` - gate failure and mid-promote failures prevent partial writes.
- Create: `tests/unit/golden/test_tasks.py` - fixture loading and deterministic golden-task evaluation tests.
- Create: `tests/unit/golden/test_runner.py` - golden harness result evaluation tests.
- Create: `tests/unit/release/test_credentials.py` - one-key credential scanner tests.
- Create: `tests/unit/release/test_runner.py` - ordered release-gate runner tests.
- Create: `tests/unit/release/test_defaults.py` - default Phase 1 command list tests.
- Modify: `tests/unit/telemetry/test_events.py` - new telemetry constructors and redaction checks.
- Create: `tests/integration/retry/test_gateway_retry_flow.py` - 503/503/200 retry flow with no writes before success.
- Create: `tests/integration/gates/test_composite_gate_failure_flow.py` - composite gate failure leaves working tree untouched.
- Create: `tests/integration/release/test_phase1_release_runner.py` - injected release runner executes golden and one-key gates.

## Human Agile Sizing

This plan is sized for roughly 2-3 weeks of human development effort:

- Days 1-3: failure classification, retry policy, telemetry event additions.
- Days 4-6: composite fitness gate models, gate runner, and validated mutation wrapper.
- Days 7-9: gated retry orchestration and failure-context injection.
- Days 10-12: golden task fixtures, evaluator, and deterministic trajectory checks.
- Days 13-15: release gate runner, one-key scanner, script, docs, and coverage hardening.

## Commit Policy for Execution

Each task includes a commit step because the Superpowers workflow favors small reviewable checkpoints. In this repository, commit steps are approval-gated: do not run `git commit`, push, delete branches, or rewrite history unless the user explicitly approves that action. If commit approval has not been granted, treat each commit step as a local checkpoint: run the narrow tests, inspect `git diff --check`, leave changes unstaged or stage only with explicit approval, and continue.

## Task 1: Failure Classification And Retry Policy

**Files:**
- Create: `src/optimus/retry/__init__.py`
- Create: `src/optimus/retry/policy.py`
- Test: `tests/unit/retry/test_policy.py`

- [x] **Step 1: Write failing retry policy tests**

Create `tests/unit/retry/test_policy.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest

from optimus.gateway.errors import GatewayHttpError, GatewayResponseError
from optimus.retry.policy import (
    BudgetExhaustedError,
    FailureKind,
    FailureSeverity,
    PermanentGatewayError,
    PolicyViolationError,
    ProviderRateLimitError,
    RetryAction,
    RetryController,
    RetryPolicy,
    TransientGatewayError,
    classify_failure,
)


def test_gateway_503_is_transient_and_retryable():
    classification = classify_failure(GatewayHttpError(503, "temporary outage"))

    assert classification.kind is FailureKind.TRANSIENT
    assert classification.severity is FailureSeverity.RETRYABLE
    assert classification.retryable is True
    assert classification.summary == "GatewayHttpError: temporary outage"


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
def test_gateway_permanent_status_aborts(status_code):
    classification = classify_failure(GatewayHttpError(status_code, "bad request"))

    assert classification.kind is FailureKind.PERMANENT
    assert classification.retryable is False


def test_gateway_response_error_is_permanent():
    classification = classify_failure(GatewayResponseError("missing usage"))

    assert classification.kind is FailureKind.PERMANENT
    assert classification.retryable is False


def test_named_failure_classes_map_to_expected_kinds():
    assert classify_failure(TransientGatewayError("try again")).kind is FailureKind.TRANSIENT
    assert classify_failure(ProviderRateLimitError("slow down")).kind is FailureKind.RATE_LIMIT
    assert classify_failure(PermanentGatewayError("bad auth")).kind is FailureKind.PERMANENT
    assert classify_failure(PolicyViolationError("blocked")).kind is FailureKind.POLICY_VIOLATION
    assert classify_failure(BudgetExhaustedError("cap reached", cost_usd=Decimal("0.041"))).kind is FailureKind.BUDGET_EXHAUSTED


def test_retry_policy_retries_transient_failures_up_to_three_attempts():
    policy = RetryPolicy(max_retries=3, base_delay_ms=500, jitter_ms=(0, 25, 50))

    first = policy.decide(classify_failure(TransientGatewayError("first")), attempt=1)
    second = policy.decide(classify_failure(TransientGatewayError("second")), attempt=2)
    third = policy.decide(classify_failure(TransientGatewayError("third")), attempt=3)
    fourth = policy.decide(classify_failure(TransientGatewayError("fourth")), attempt=4)

    assert first.action is RetryAction.RETRY
    assert first.delay_ms == 500
    assert second.delay_ms == 1025
    assert third.delay_ms == 2050
    assert fourth.action is RetryAction.ESCALATE_TO_USER
    assert fourth.delay_ms == 0


def test_retry_policy_never_retries_permanent_failures():
    policy = RetryPolicy(max_retries=3, base_delay_ms=500, jitter_ms=(0,))

    decision = policy.decide(classify_failure(PolicyViolationError("blocked")), attempt=1)

    assert decision.action is RetryAction.ABORT_WITH_REPORT
    assert decision.delay_ms == 0


def test_retry_policy_escalates_unknown_failures():
    policy = RetryPolicy(max_retries=3, base_delay_ms=500, jitter_ms=(0,))

    decision = policy.decide(classify_failure(RuntimeError("unexpected")), attempt=1)

    assert decision.action is RetryAction.ESCALATE_TO_USER
    assert decision.delay_ms == 0


def test_retry_controller_succeeds_on_third_attempt_without_sleeping_real_time():
    attempts: list[int] = []
    slept: list[int] = []

    def operation() -> str:
        attempts.append(len(attempts) + 1)
        if len(attempts) < 3:
            raise GatewayHttpError(503, "temporary outage")
        return "ok"

    controller = RetryController(
        policy=RetryPolicy(max_retries=3, base_delay_ms=500, jitter_ms=(0, 0, 0)),
        sleep_ms=slept.append,
    )

    result = controller.run(operation)

    assert result.value == "ok"
    assert result.attempts == 3
    assert result.retry_count == 2
    assert result.final_decision.action is RetryAction.SUCCESS
    assert [failure.classification.kind for failure in result.prior_failures] == [
        FailureKind.TRANSIENT,
        FailureKind.TRANSIENT,
    ]
    assert slept == [500, 1000]


def test_retry_controller_escalates_after_retry_budget_exhausted():
    @dataclass
    class FailingOperation:
        calls: int = 0

        def __call__(self) -> str:
            self.calls += 1
            raise GatewayHttpError(503, "temporary outage")

    operation = FailingOperation()
    controller = RetryController(
        policy=RetryPolicy(max_retries=3, base_delay_ms=1, jitter_ms=(0,)),
        sleep_ms=lambda delay_ms: None,
    )

    result = controller.run(operation)

    assert result.value is None
    assert result.final_decision.action is RetryAction.ESCALATE_TO_USER
    assert result.attempts == 4
    assert result.retry_count == 3
    assert operation.calls == 4
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/retry/test_policy.py -v
```

Expected: FAIL because `optimus.retry.policy` does not exist.

- [x] **Step 3: Implement retry policy**

Create `src/optimus/retry/policy.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Generic, TypeVar

from optimus.gateway.errors import GatewayHttpError, GatewayResponseError

T = TypeVar("T")


class FailureKind(StrEnum):
    SUCCESS = "success"
    TRANSIENT = "transient"
    RATE_LIMIT = "rate_limit"
    PERMANENT = "permanent"
    POLICY_VIOLATION = "policy_violation"
    BUDGET_EXHAUSTED = "budget_exhausted"
    FITNESS_GATE = "fitness_gate"
    UNKNOWN = "unknown"


class FailureSeverity(StrEnum):
    RETRYABLE = "retryable"
    TERMINAL = "terminal"
    ESCALATE = "escalate"


class RetryAction(StrEnum):
    SUCCESS = "success"
    RETRY = "retry"
    ABORT_WITH_REPORT = "abort_with_report"
    ESCALATE_TO_USER = "escalate_to_user"


class TransientGatewayError(Exception):
    """A temporary gateway or provider failure that may succeed on retry."""


class ProviderRateLimitError(Exception):
    """A provider or gateway rate-limit response."""


class PermanentGatewayError(Exception):
    """A non-retryable gateway failure."""


class PolicyViolationError(Exception):
    """A deterministic policy denial."""


class BudgetExhaustedError(Exception):
    def __init__(self, message: str, *, cost_usd: Decimal) -> None:
        self.cost_usd = cost_usd
        super().__init__(message)


@dataclass(frozen=True)
class FailureClassification:
    kind: FailureKind
    severity: FailureSeverity
    error_type: str
    message: str
    cost_usd: Decimal | None = None

    @property
    def retryable(self) -> bool:
        return self.severity is FailureSeverity.RETRYABLE

    @property
    def summary(self) -> str:
        return f"{self.error_type}: {self.message}"


@dataclass(frozen=True)
class RetryDecision:
    action: RetryAction
    classification: FailureClassification
    attempt: int
    delay_ms: int
    reason: str


@dataclass(frozen=True)
class RetryFailure:
    attempt: int
    classification: FailureClassification
    decision: RetryDecision


@dataclass(frozen=True)
class RetryResult(Generic[T]):
    value: T | None
    attempts: int
    retry_count: int
    prior_failures: tuple[RetryFailure, ...]
    final_decision: RetryDecision


TRANSIENT_HTTP_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
PERMANENT_HTTP_STATUS_CODES = frozenset({400, 401, 403, 404, 422})


def classify_failure(error: BaseException) -> FailureClassification:
    if isinstance(error, TransientGatewayError):
        return _classification(FailureKind.TRANSIENT, FailureSeverity.RETRYABLE, error)
    if isinstance(error, ProviderRateLimitError):
        return _classification(FailureKind.RATE_LIMIT, FailureSeverity.RETRYABLE, error)
    if isinstance(error, PermanentGatewayError | GatewayResponseError):
        return _classification(FailureKind.PERMANENT, FailureSeverity.TERMINAL, error)
    if isinstance(error, PolicyViolationError):
        return _classification(FailureKind.POLICY_VIOLATION, FailureSeverity.TERMINAL, error)
    if isinstance(error, BudgetExhaustedError):
        return _classification(
            FailureKind.BUDGET_EXHAUSTED,
            FailureSeverity.TERMINAL,
            error,
            cost_usd=error.cost_usd,
        )
    if isinstance(error, GatewayHttpError):
        if error.status_code in TRANSIENT_HTTP_STATUS_CODES:
            kind = FailureKind.RATE_LIMIT if error.status_code == 429 else FailureKind.TRANSIENT
            return _classification(kind, FailureSeverity.RETRYABLE, error)
        if error.status_code in PERMANENT_HTTP_STATUS_CODES:
            return _classification(FailureKind.PERMANENT, FailureSeverity.TERMINAL, error)
    return _classification(FailureKind.UNKNOWN, FailureSeverity.ESCALATE, error)


def _classification(
    kind: FailureKind,
    severity: FailureSeverity,
    error: BaseException,
    *,
    cost_usd: Decimal | None = None,
) -> FailureClassification:
    return FailureClassification(
        kind=kind,
        severity=severity,
        error_type=type(error).__name__,
        message=str(error),
        cost_usd=cost_usd,
    )


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 3
    base_delay_ms: int = 500
    jitter_ms: tuple[int, ...] = (0, 25, 50, 75)

    def decide(self, classification: FailureClassification, *, attempt: int) -> RetryDecision:
        if classification.severity is FailureSeverity.ESCALATE:
            return RetryDecision(
                action=RetryAction.ESCALATE_TO_USER,
                classification=classification,
                attempt=attempt,
                delay_ms=0,
                reason=f"{classification.kind.value} failures require user escalation",
            )
        if not classification.retryable:
            return RetryDecision(
                action=RetryAction.ABORT_WITH_REPORT,
                classification=classification,
                attempt=attempt,
                delay_ms=0,
                reason=f"{classification.kind.value} failures are not retryable",
            )
        if attempt > self.max_retries:
            return RetryDecision(
                action=RetryAction.ESCALATE_TO_USER,
                classification=classification,
                attempt=attempt,
                delay_ms=0,
                reason="retry budget exhausted",
            )
        return RetryDecision(
            action=RetryAction.RETRY,
            classification=classification,
            attempt=attempt,
            delay_ms=self._delay_ms(attempt),
            reason="transient failure within retry budget",
        )

    def _delay_ms(self, attempt: int) -> int:
        exponent = max(attempt - 1, 0)
        jitter = self.jitter_ms[(attempt - 1) % len(self.jitter_ms)] if self.jitter_ms else 0
        return self.base_delay_ms * (2**exponent) + jitter


class RetryController(Generic[T]):
    def __init__(
        self,
        *,
        policy: RetryPolicy | None = None,
        sleep_ms: Callable[[int], None] | None = None,
    ) -> None:
        self._policy = policy or RetryPolicy()
        self._sleep_ms = sleep_ms or _sleep_ms

    def run(self, operation: Callable[[], T]) -> RetryResult[T]:
        failures: list[RetryFailure] = []
        attempt = 1
        while True:
            try:
                value = operation()
                return RetryResult(
                    value=value,
                    attempts=attempt,
                    retry_count=len(failures),
                    prior_failures=tuple(failures),
                    final_decision=RetryDecision(
                        action=RetryAction.SUCCESS,
                        classification=FailureClassification(
                            kind=FailureKind.SUCCESS,
                            severity=FailureSeverity.TERMINAL,
                            error_type="None",
                            message="operation succeeded",
                        ),
                        attempt=attempt,
                        delay_ms=0,
                        reason="operation succeeded",
                    ),
                )
            except Exception as exc:
                classification = classify_failure(exc)
                decision = self._policy.decide(classification, attempt=attempt)
                failures.append(RetryFailure(attempt=attempt, classification=classification, decision=decision))
                if decision.action is not RetryAction.RETRY:
                    return RetryResult(
                        value=None,
                        attempts=attempt,
                        retry_count=max(attempt - 1, 0),
                        prior_failures=tuple(failures),
                        final_decision=decision,
                    )
                self._sleep_ms(decision.delay_ms)
                attempt += 1


def _sleep_ms(delay_ms: int) -> None:
    import time

    time.sleep(delay_ms / 1000)
```

Create `src/optimus/retry/__init__.py`:

```python
from optimus.retry.policy import (
    BudgetExhaustedError,
    FailureClassification,
    FailureKind,
    FailureSeverity,
    PermanentGatewayError,
    PolicyViolationError,
    ProviderRateLimitError,
    RetryAction,
    RetryController,
    RetryDecision,
    RetryFailure,
    RetryPolicy,
    RetryResult,
    TransientGatewayError,
    classify_failure,
)

__all__ = [
    "BudgetExhaustedError",
    "FailureClassification",
    "FailureKind",
    "FailureSeverity",
    "PermanentGatewayError",
    "PolicyViolationError",
    "ProviderRateLimitError",
    "RetryAction",
    "RetryController",
    "RetryDecision",
    "RetryFailure",
    "RetryPolicy",
    "RetryResult",
    "TransientGatewayError",
    "classify_failure",
]
```

- [x] **Step 4: Run retry policy tests**

Run:

```bash
pytest tests/unit/retry/test_policy.py -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/optimus/retry/__init__.py src/optimus/retry/policy.py tests/unit/retry/test_policy.py
git commit -m "Add bounded retry failure classification."
```

## Task 2: Retry, Fitness, Golden, And Release Telemetry Events

**Files:**
- Create: `src/optimus/telemetry/redaction.py`
- Modify: `src/optimus/telemetry/events.py`
- Modify: `src/optimus/telemetry/__init__.py`
- Test: `tests/unit/telemetry/test_events.py`

- [x] **Step 1: Write failing telemetry event tests**

Append to `tests/unit/telemetry/test_events.py`:

```python
from datetime import UTC, datetime
from decimal import Decimal

from optimus.telemetry.events import TelemetryEvent, TelemetryEventKind
from optimus.telemetry.redaction import redact_for_telemetry


def test_retry_decision_event_serializes_failure_classification():
    event = TelemetryEvent.retry_decision(
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 5, tzinfo=UTC),
        attempt=2,
        retry_count=1,
        failure_kind="transient",
        action="retry",
        delay_ms=1000,
        disposition="retrying",
    )

    payload = event.to_json_dict()

    assert event.kind is TelemetryEventKind.RETRY_DECISION
    assert payload["attempt"] == 2
    assert payload["failure_kind"] == "transient"
    assert payload["action"] == "retry"


def test_fitness_gate_event_serializes_gate_names_and_cost():
    event = TelemetryEvent.fitness_gate(
        run_id="run-1",
        session_id=None,
        request_id="req-1",
        occurred_at=datetime(2026, 7, 5, tzinfo=UTC),
        passed=False,
        required_gate_names=("tests", "coverage"),
        failed_gate_names=("coverage",),
        duration_ms=125,
        cost_usd=Decimal("0.000"),
    )

    payload = event.to_json_dict()

    assert event.kind is TelemetryEventKind.FITNESS_GATE
    assert payload["passed"] is False
    assert payload["failed_gate_names"] == ["coverage"]
    assert payload["cost_usd"] == "0.000"


def test_golden_task_event_serializes_expected_and_actual_outcome():
    event = TelemetryEvent.golden_task(
        run_id="run-1",
        session_id=None,
        request_id="golden-docstring",
        occurred_at=datetime(2026, 7, 5, tzinfo=UTC),
        task_id="docstring-single-function",
        passed=True,
        expected_mode="agent",
        actual_mode="agent",
        expected_tools=("file_reader", "write_file"),
        actual_tools=("file_reader", "write_file"),
        max_cost_usd=Decimal("0.012"),
        actual_cost_usd=Decimal("0.009"),
        expected_final_state="completed",
        actual_final_state="completed",
    )

    payload = event.to_json_dict()

    assert event.kind is TelemetryEventKind.GOLDEN_TASK
    assert payload["task_id"] == "docstring-single-function"
    assert payload["passed"] is True


def test_release_gate_event_redacts_secret_environment_details():
    event = TelemetryEvent.release_gate(
        run_id="run-1",
        session_id=None,
        request_id="release",
        occurred_at=datetime(2026, 7, 5, tzinfo=UTC),
        gate_name="one-key",
        passed=False,
        duration_ms=10,
        output_summary="OPENAI_API_KEY=sk-live leaked",
    )

    payload = event.to_json_dict()

    assert event.kind is TelemetryEventKind.RELEASE_GATE
    assert payload["gate_name"] == "one-key"
    assert "sk-live" not in payload["output_summary"]
    assert "**********" in payload["output_summary"]


def test_public_redaction_helper_masks_provider_key_assignments():
    payload = redact_for_telemetry({"stdout": "OPENAI_API_KEY=sk-live"})

    assert payload == {"stdout": "OPENAI_API_KEY=**********"}
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/telemetry/test_events.py -v
```

Expected: FAIL because the new event kinds, constructors, and public redaction helper do not exist.

- [x] **Step 3: Add public telemetry redaction helper**

Create `src/optimus/telemetry/redaction.py` by moving the existing private redaction helpers out of `events.py`:

```python
from __future__ import annotations

import re
from typing import Any

from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES

_EXACT_SECRET_KEYS = {
    "authorization",
    "auth_header",
    "x-api-key",
}

_SECRET_KEY_PARTS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "credential",
    "optimus_api_key",
)

_REDACT_ENV_KEY_NAMES = frozenset({*LOCAL_PROVIDER_KEY_NAMES, "OPTIMUS_API_KEY"})
_REDACT_ENV_KEY_NAMES_LOWER = frozenset(name.lower().replace("-", "_") for name in _REDACT_ENV_KEY_NAMES)
_ENV_ASSIGNMENT_PATTERN = re.compile(
    rf"\b({'|'.join(sorted(_REDACT_ENV_KEY_NAMES, key=len, reverse=True))})\s*=\s*\S+",
    re.IGNORECASE,
)
_API_KEY_HEADER_PATTERN = re.compile(r"(?i)(api[_-]?key)\s*:\s*\S+")
_X_API_KEY_HEADER_PATTERN = re.compile(r"(?i)x-api-key:\s*\S+")
_BEARER_TOKEN_PATTERN = re.compile(r"(?i)(authorization:\s*bearer\s+|bearer\s+)[^\s]+")


def redact_for_telemetry(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key).lower()
            if _is_secret_dict_key(key_text):
                redacted[key] = "**********"
            else:
                redacted[key] = redact_for_telemetry(child)
        return redacted
    if isinstance(value, (list, tuple)):
        return [redact_for_telemetry(child) for child in value]
    if isinstance(value, str):
        return _redact_free_text(value)
    return value


def _redact_free_text(text: str) -> str:
    redacted = _BEARER_TOKEN_PATTERN.sub(r"\1**********", text)
    redacted = _ENV_ASSIGNMENT_PATTERN.sub(r"\1=**********", redacted)
    redacted = _API_KEY_HEADER_PATTERN.sub(r"\1: **********", redacted)
    redacted = _X_API_KEY_HEADER_PATTERN.sub("x-api-key: **********", redacted)
    return redacted


def _is_secret_dict_key(key_text: str) -> bool:
    if key_text in _EXACT_SECRET_KEYS:
        return True
    normalized = key_text.replace("-", "_")
    if normalized in _REDACT_ENV_KEY_NAMES_LOWER:
        return True
    if normalized in _SECRET_KEY_PARTS:
        return True
    segments = normalized.split("_")
    return any(segment in _SECRET_KEY_PARTS for segment in segments)
```

- [x] **Step 4: Extend telemetry events**

Modify `TelemetryEventKind` in `src/optimus/telemetry/events.py`:

```python
class TelemetryEventKind(StrEnum):
    MODEL_CALL = "model_call"
    TOOL_CALL = "tool_call"
    GATEWAY_USAGE = "gateway_usage"
    GUARDRAIL_AUDIT = "guardrail_audit"
    RECONCILIATION = "reconciliation"
    ERROR = "error"
    PRICING_FALLBACK = "pricing_fallback"
    RETRY_DECISION = "retry_decision"
    FITNESS_GATE = "fitness_gate"
    GOLDEN_TASK = "golden_task"
    RELEASE_GATE = "release_gate"
```

Import the public helper at the top of `src/optimus/telemetry/events.py`:

```python
from optimus.telemetry.redaction import redact_for_telemetry
```

Change `to_json_dict()` to call the public helper:

```python
    def to_json_dict(self) -> dict[str, Any]:
        encoded = {
            "kind": self.kind.value,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "occurred_at": self.occurred_at.isoformat(),
            **self.payload,
        }
        return _json_safe(redact_for_telemetry(encoded))
```

Remove the private `_redact*` helpers from `events.py` after moving them to `redaction.py`.

Add these classmethods to `TelemetryEvent`:

```python
    @classmethod
    def retry_decision(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        attempt: int,
        retry_count: int,
        failure_kind: str,
        action: str,
        delay_ms: int,
        disposition: str,
    ) -> "TelemetryEvent":
        return cls(
            kind=TelemetryEventKind.RETRY_DECISION,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={
                "attempt": attempt,
                "retry_count": retry_count,
                "failure_kind": failure_kind,
                "action": action,
                "delay_ms": delay_ms,
                "disposition": disposition,
            },
        )

    @classmethod
    def fitness_gate(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        passed: bool,
        required_gate_names: tuple[str, ...],
        failed_gate_names: tuple[str, ...],
        duration_ms: int,
        cost_usd: Decimal,
    ) -> "TelemetryEvent":
        return cls(
            kind=TelemetryEventKind.FITNESS_GATE,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={
                "passed": passed,
                "required_gate_names": required_gate_names,
                "failed_gate_names": failed_gate_names,
                "duration_ms": duration_ms,
                "cost_usd": cost_usd,
            },
        )

    @classmethod
    def golden_task(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        task_id: str,
        passed: bool,
        expected_mode: str,
        actual_mode: str,
        expected_tools: tuple[str, ...],
        actual_tools: tuple[str, ...],
        max_cost_usd: Decimal,
        actual_cost_usd: Decimal,
        expected_final_state: str,
        actual_final_state: str,
    ) -> "TelemetryEvent":
        return cls(
            kind=TelemetryEventKind.GOLDEN_TASK,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={
                "task_id": task_id,
                "passed": passed,
                "expected_mode": expected_mode,
                "actual_mode": actual_mode,
                "expected_tools": expected_tools,
                "actual_tools": actual_tools,
                "max_cost_usd": max_cost_usd,
                "actual_cost_usd": actual_cost_usd,
                "expected_final_state": expected_final_state,
                "actual_final_state": actual_final_state,
            },
        )

    @classmethod
    def release_gate(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        gate_name: str,
        passed: bool,
        duration_ms: int,
        output_summary: str,
    ) -> "TelemetryEvent":
        return cls(
            kind=TelemetryEventKind.RELEASE_GATE,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={
                "gate_name": gate_name,
                "passed": passed,
                "duration_ms": duration_ms,
                "output_summary": output_summary,
            },
        )
```

- [x] **Step 5: Export redaction helper**

Update `src/optimus/telemetry/__init__.py`:

```python
from optimus.telemetry.redaction import redact_for_telemetry
```

Append to `__all__`:

```python
    "redact_for_telemetry",
```

- [x] **Step 6: Run telemetry tests**

Run:

```bash
pytest tests/unit/telemetry/test_events.py -v
```

Expected: PASS.

- [x] **Step 7: Commit**

```bash
git add src/optimus/telemetry/__init__.py src/optimus/telemetry/events.py src/optimus/telemetry/redaction.py tests/unit/telemetry/test_events.py
git commit -m "Record retry and release gate telemetry."
```

## Task 3: Composite Fitness Gate Results

**Files:**
- Create: `src/optimus/gates/__init__.py`
- Create: `src/optimus/gates/fitness.py`
- Test: `tests/unit/gates/test_fitness.py`

- [x] **Step 1: Write failing composite gate tests**

Create `tests/unit/gates/test_fitness.py`:

```python
from __future__ import annotations

from optimus.gates.fitness import (
    CompositeGateError,
    FitnessCheck,
    FitnessGateRunner,
    GateResult,
    GateStatus,
)


class PassingCheck:
    name = "unit-tests"
    required = True

    def run(self) -> GateResult:
        return GateResult.pass_(name=self.name, summary="tests passed", duration_ms=12)


class FailingCheck:
    name = "coverage"
    required = True

    def run(self) -> GateResult:
        return GateResult.fail(name=self.name, summary="coverage below threshold", duration_ms=8)


class OptionalFailingCheck:
    name = "future-context-regret"
    required = False

    def run(self) -> GateResult:
        return GateResult.fail(name=self.name, summary="future Plan 10 signal", duration_ms=1)


class RaisingCheck:
    name = "architecture"
    required = True

    def run(self) -> GateResult:
        raise RuntimeError("tool crashed")


def test_composite_gate_passes_when_required_checks_pass():
    result = FitnessGateRunner(checks=(PassingCheck(),)).run()

    assert result.passed is True
    assert result.required_gate_names == ("unit-tests",)
    assert result.failed_gate_names == ()
    assert result.results[0].status is GateStatus.PASS


def test_required_gate_failure_fails_composite_result():
    result = FitnessGateRunner(checks=(PassingCheck(), FailingCheck())).run()

    assert result.passed is False
    assert result.failed_gate_names == ("coverage",)


def test_optional_gate_failure_does_not_block_composite_result():
    result = FitnessGateRunner(checks=(PassingCheck(), OptionalFailingCheck())).run()

    assert result.passed is True
    assert result.failed_gate_names == ()
    assert result.warning_gate_names == ("future-context-regret",)


def test_gate_exception_fails_closed():
    result = FitnessGateRunner(checks=(RaisingCheck(),)).run()

    assert result.passed is False
    assert result.failed_gate_names == ("architecture",)
    assert result.results[0].status is GateStatus.ERROR
    assert "RuntimeError" in result.results[0].summary


def test_raise_for_failure_uses_tight_failure_summary():
    result = FitnessGateRunner(checks=(FailingCheck(),)).run()

    try:
        result.raise_for_failure()
    except CompositeGateError as exc:
        assert exc.result == result
        assert str(exc) == "required fitness gates failed: coverage"
    else:
        raise AssertionError("expected CompositeGateError")


def test_protocol_accepts_fitness_check_instances():
    check: FitnessCheck = PassingCheck()

    assert check.name == "unit-tests"
    assert check.required is True
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/gates/test_fitness.py -v
```

Expected: FAIL because `optimus.gates.fitness` does not exist.

- [x] **Step 3: Implement composite fitness gates**

Create `src/optimus/gates/fitness.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class GateStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIP = "skip"


@dataclass(frozen=True)
class GateResult:
    name: str
    status: GateStatus
    summary: str
    duration_ms: int = 0
    required: bool = True

    @classmethod
    def pass_(cls, *, name: str, summary: str, duration_ms: int = 0, required: bool = True) -> "GateResult":
        return cls(name=name, status=GateStatus.PASS, summary=summary, duration_ms=duration_ms, required=required)

    @classmethod
    def fail(cls, *, name: str, summary: str, duration_ms: int = 0, required: bool = True) -> "GateResult":
        return cls(name=name, status=GateStatus.FAIL, summary=summary, duration_ms=duration_ms, required=required)

    @classmethod
    def error(cls, *, name: str, summary: str, duration_ms: int = 0, required: bool = True) -> "GateResult":
        return cls(name=name, status=GateStatus.ERROR, summary=summary, duration_ms=duration_ms, required=required)


class FitnessCheck(Protocol):
    name: str
    required: bool

    def run(self) -> GateResult:
        raise NotImplementedError


@dataclass(frozen=True)
class CompositeGateResult:
    results: tuple[GateResult, ...]

    @property
    def passed(self) -> bool:
        return not self.failed_gate_names

    @property
    def required_gate_names(self) -> tuple[str, ...]:
        return tuple(result.name for result in self.results if result.required)

    @property
    def failed_gate_names(self) -> tuple[str, ...]:
        return tuple(
            result.name
            for result in self.results
            if result.required and result.status in {GateStatus.FAIL, GateStatus.ERROR}
        )

    @property
    def warning_gate_names(self) -> tuple[str, ...]:
        return tuple(
            result.name
            for result in self.results
            if not result.required and result.status in {GateStatus.FAIL, GateStatus.ERROR}
        )

    @property
    def duration_ms(self) -> int:
        return sum(result.duration_ms for result in self.results)

    def raise_for_failure(self) -> None:
        if not self.passed:
            raise CompositeGateError(self)


class CompositeGateError(Exception):
    def __init__(self, result: CompositeGateResult) -> None:
        self.result = result
        super().__init__(f"required fitness gates failed: {', '.join(result.failed_gate_names)}")


class FitnessGateRunner:
    def __init__(self, *, checks: tuple[FitnessCheck, ...]) -> None:
        self._checks = checks

    def run(self) -> CompositeGateResult:
        results: list[GateResult] = []
        for check in self._checks:
            try:
                result = check.run()
            except Exception as exc:
                result = GateResult.error(
                    name=check.name,
                    summary=f"{type(exc).__name__}: {exc}",
                    required=check.required,
                )
            if result.required != check.required:
                result = GateResult(
                    name=result.name,
                    status=result.status,
                    summary=result.summary,
                    duration_ms=result.duration_ms,
                    required=check.required,
                )
            results.append(result)
        return CompositeGateResult(results=tuple(results))
```

Create `src/optimus/gates/__init__.py`:

```python
from optimus.gates.fitness import (
    CompositeGateError,
    CompositeGateResult,
    FitnessCheck,
    FitnessGateRunner,
    GateResult,
    GateStatus,
)

__all__ = [
    "CompositeGateError",
    "CompositeGateResult",
    "FitnessCheck",
    "FitnessGateRunner",
    "GateResult",
    "GateStatus",
]
```

- [x] **Step 4: Run gate tests**

Run:

```bash
pytest tests/unit/gates/test_fitness.py -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/optimus/gates/__init__.py src/optimus/gates/fitness.py tests/unit/gates/test_fitness.py
git commit -m "Add composite fitness gate results."
```

## Task 4: Shadow Workspace Mutation Flow Blocks Partial Writes

**Files:**
- Create: `src/optimus/gates/shadow_workspace.py`
- Create: `src/optimus/gates/mutation_flow.py`
- Modify: `src/optimus/gates/__init__.py`
- Test: `tests/unit/gates/test_mutation_flow.py`
- Test: `tests/integration/gates/test_composite_gate_failure_flow.py`

- [x] **Step 1: Write failing mutation flow tests**

Create `tests/unit/gates/test_mutation_flow.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from optimus.gates.fitness import GateResult
from optimus.gates.mutation_flow import ShadowWorkspaceMutationRunner
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.mutation import MutationForbidden
from optimus.runtime.state import AgentState, RuntimeContext


class PassingCheck:
    name = "tests"
    required = True

    def run(self) -> GateResult:
        return GateResult.pass_(name=self.name, summary="passed")


class FailingCheck:
    name = "tests"
    required = True

    def run(self) -> GateResult:
        return GateResult.fail(name=self.name, summary="failed")


def approved_context() -> RuntimeContext:
    return RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.EXECUTING,
        approval_granted=True,
        user_approval_id="approval-1",
    )


def test_shadow_changes_promote_only_after_gates_pass(tmp_path):
    target = tmp_path / "module.py"
    target.write_text("value = 1\n", encoding="utf-8")
    runner = ShadowWorkspaceMutationRunner(checks_factory=lambda shadow_root: (PassingCheck(),))

    result = runner.run(
        context=approved_context(),
        workspace_root=tmp_path,
        apply_candidate=lambda shadow_root: (shadow_root / "module.py").write_text("value = 2\n", encoding="utf-8"),
    )

    assert result.passed is True
    assert target.read_text(encoding="utf-8") == "value = 2\n"


def test_gate_failure_discards_shadow_changes(tmp_path):
    target = tmp_path / "module.py"
    target.write_text("value = 1\n", encoding="utf-8")
    runner = ShadowWorkspaceMutationRunner(checks_factory=lambda shadow_root: (FailingCheck(),))

    result = runner.run(
        context=approved_context(),
        workspace_root=tmp_path,
        apply_candidate=lambda shadow_root: (shadow_root / "module.py").write_text("value = 2\n", encoding="utf-8"),
    )

    assert result.passed is False
    assert target.read_text(encoding="utf-8") == "value = 1\n"


def test_promote_failure_rolls_back_previous_file(tmp_path):
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    first.write_text("value = 1\n", encoding="utf-8")
    second.write_text("value = 1\n", encoding="utf-8")
    runner = ShadowWorkspaceMutationRunner(
        checks_factory=lambda shadow_root: (PassingCheck(),),
        fail_after_promoted_paths=1,
    )

    with pytest.raises(RuntimeError, match="simulated promotion failure"):
        runner.run(
            context=approved_context(),
            workspace_root=tmp_path,
            apply_candidate=lambda shadow_root: (
                (shadow_root / "first.py").write_text("value = 2\n", encoding="utf-8"),
                (shadow_root / "second.py").write_text("value = 2\n", encoding="utf-8"),
            ),
        )

    assert first.read_text(encoding="utf-8") == "value = 1\n"
    assert second.read_text(encoding="utf-8") == "value = 1\n"


def test_plan_mode_blocks_before_gates_and_mutation(tmp_path):
    target = tmp_path / "changed.txt"
    runner = ShadowWorkspaceMutationRunner(checks_factory=lambda shadow_root: (PassingCheck(),))
    context = RuntimeContext(execution_mode=ExecutionMode.PLAN, state=AgentState.PLANNING)

    with pytest.raises(MutationForbidden, match="mutation forbidden"):
        runner.run(
            context=context,
            workspace_root=tmp_path,
            apply_candidate=lambda shadow_root: (shadow_root / "changed.txt").write_text("changed", encoding="utf-8"),
        )

    assert not target.exists()
```

Create `tests/integration/gates/test_composite_gate_failure_flow.py`:

```python
from __future__ import annotations

from optimus.gates.fitness import GateResult
from optimus.gates.mutation_flow import ShadowWorkspaceMutationRunner
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.state import AgentState, RuntimeContext


class FailingCompositeCheck:
    name = "coverage"
    required = True

    def run(self) -> GateResult:
        return GateResult.fail(name=self.name, summary="aggregate coverage below 80")


def test_composite_gate_failure_leaves_working_file_untouched(tmp_path):
    target = tmp_path / "module.py"
    original = "def value():\n    return 1\n"
    target.write_text(original, encoding="utf-8")
    runner = ShadowWorkspaceMutationRunner(checks_factory=lambda shadow_root: (FailingCompositeCheck(),))
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.EXECUTING,
        approval_granted=True,
        user_approval_id="approval-1",
    )

    result = runner.run(
        context=context,
        workspace_root=tmp_path,
        apply_candidate=lambda shadow_root: (shadow_root / "module.py").write_text("def value():\n    return 2\n", encoding="utf-8"),
    )

    assert result.passed is False
    assert target.read_text(encoding="utf-8") == original
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/gates/test_mutation_flow.py tests/integration/gates/test_composite_gate_failure_flow.py -v
```

Expected: FAIL because `optimus.gates.shadow_workspace` and `optimus.gates.mutation_flow` do not exist.

- [x] **Step 3: Implement shadow workspace helpers**

Create `src/optimus/gates/shadow_workspace.py`:

```python
from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ShadowPromotionPlan:
    workspace_root: Path
    shadow_root: Path
    changed_paths: tuple[Path, ...]


class ShadowWorkspace:
    def __init__(self, *, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.shadow_root = Path(self._temporary_directory.name) / self.workspace_root.name
        shutil.copytree(self.workspace_root, self.shadow_root, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))

    def changed_paths(self) -> tuple[Path, ...]:
        changed: list[Path] = []
        for shadow_path in self.shadow_root.rglob("*"):
            if not shadow_path.is_file():
                continue
            relative = shadow_path.relative_to(self.shadow_root)
            workspace_path = self.workspace_root / relative
            if not workspace_path.exists() or shadow_path.read_bytes() != workspace_path.read_bytes():
                changed.append(relative)
        return tuple(sorted(changed))

    def promotion_plan(self) -> ShadowPromotionPlan:
        return ShadowPromotionPlan(
            workspace_root=self.workspace_root,
            shadow_root=self.shadow_root,
            changed_paths=self.changed_paths(),
        )

    def cleanup(self) -> None:
        self._temporary_directory.cleanup()


def promote_shadow_changes(plan: ShadowPromotionPlan, *, fail_after_promoted_paths: int | None = None) -> None:
    backups: list[tuple[Path, bytes | None]] = []
    promoted_count = 0
    try:
        for relative in plan.changed_paths:
            source = plan.shadow_root / relative
            target = plan.workspace_root / relative
            backups.append((target, target.read_bytes() if target.exists() else None))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            promoted_count += 1
            if fail_after_promoted_paths is not None and promoted_count >= fail_after_promoted_paths:
                raise RuntimeError("simulated promotion failure")
    except Exception:
        _restore_backups(backups)
        raise


def _restore_backups(backups: Iterable[tuple[Path, bytes | None]]) -> None:
    for target, content in reversed(tuple(backups)):
        if content is None:
            target.unlink(missing_ok=True)
        else:
            target.write_bytes(content)
```

- [x] **Step 4: Implement validated mutation runner**

Create `src/optimus/gates/mutation_flow.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from optimus.gates.fitness import CompositeGateResult, FitnessCheck, FitnessGateRunner
from optimus.gates.shadow_workspace import ShadowWorkspace, promote_shadow_changes
from optimus.runtime.mutation import MutationKind, assert_mutation_allowed
from optimus.runtime.state import RuntimeContext

T = TypeVar("T")


class ShadowWorkspaceMutationRunner:
    def __init__(
        self,
        *,
        checks_factory: Callable[[Path], tuple[FitnessCheck, ...]],
        fail_after_promoted_paths: int | None = None,
    ) -> None:
        self._checks_factory = checks_factory
        self._fail_after_promoted_paths = fail_after_promoted_paths

    def run(
        self,
        *,
        context: RuntimeContext,
        workspace_root: str | Path,
        apply_candidate: Callable[[Path], object],
    ) -> CompositeGateResult:
        assert_mutation_allowed(context, MutationKind.WRITE_FILE)
        shadow = ShadowWorkspace(workspace_root=Path(workspace_root))
        try:
            apply_candidate(shadow.shadow_root)
            result = FitnessGateRunner(checks=self._checks_factory(shadow.shadow_root)).run()
            if result.passed:
                promote_shadow_changes(
                    shadow.promotion_plan(),
                    fail_after_promoted_paths=self._fail_after_promoted_paths,
                )
            return result
        finally:
            shadow.cleanup()
```

Update `src/optimus/gates/__init__.py`:

```python
from optimus.gates.mutation_flow import ShadowWorkspaceMutationRunner
from optimus.gates.shadow_workspace import ShadowPromotionPlan, ShadowWorkspace, promote_shadow_changes
```

Append to `__all__`:

```python
    "ShadowPromotionPlan",
    "ShadowWorkspace",
    "ShadowWorkspaceMutationRunner",
    "promote_shadow_changes",
```

- [x] **Step 5: Run mutation flow tests**

Run:

```bash
pytest tests/unit/gates/test_mutation_flow.py tests/integration/gates/test_composite_gate_failure_flow.py -v
```

Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add src/optimus/gates/__init__.py src/optimus/gates/mutation_flow.py src/optimus/gates/shadow_workspace.py tests/unit/gates/test_mutation_flow.py tests/integration/gates/test_composite_gate_failure_flow.py
git commit -m "Block mutation until fitness gates pass."
```

## Task 5: Retry Orchestration With Gate Failure Replanning

**Files:**
- Create: `src/optimus/retry/gated_run.py`
- Modify: `src/optimus/retry/__init__.py`
- Test: `tests/unit/retry/test_gated_run.py`
- Test: `tests/integration/retry/test_gateway_retry_flow.py`

- [x] **Step 1: Write failing gated retry tests**

Create `tests/unit/retry/test_gated_run.py`:

```python
from __future__ import annotations

from optimus.gates.fitness import GateResult
from optimus.retry.gated_run import GatedAttempt, GatedRetryRunner
from optimus.retry.policy import RetryPolicy
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.state import AgentState, RuntimeContext


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
    )

    assert result.succeeded is True
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
    )

    assert result.succeeded is False
    assert result.retry_count == 1
    assert result.runtime_context.retry_count == 1
    assert result.runtime_context.user_escalation is True
    assert result.runtime_context.failure_context == "required fitness gates failed: fitness"
    assert isinstance(result.final_attempt, GatedAttempt)
    assert not target.exists()
```

Create `tests/integration/retry/test_gateway_retry_flow.py`:

```python
from __future__ import annotations

from pathlib import Path

from optimus.gateway.errors import GatewayHttpError
from optimus.retry.policy import RetryController, RetryPolicy


def test_gateway_503_twice_then_success_does_not_write_until_success(tmp_path):
    target = tmp_path / "result.txt"
    calls: list[int] = []

    def gateway_then_write() -> str:
        calls.append(len(calls) + 1)
        if len(calls) < 3:
            assert not target.exists()
            raise GatewayHttpError(503, "temporary outage")
        target.write_text("success", encoding="utf-8")
        return "success"

    result = RetryController(
        policy=RetryPolicy(max_retries=3, base_delay_ms=1, jitter_ms=(0,)),
        sleep_ms=lambda delay_ms: None,
    ).run(gateway_then_write)

    assert result.value == "success"
    assert result.retry_count == 2
    assert Path(target).read_text(encoding="utf-8") == "success"
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/retry/test_gated_run.py tests/integration/retry/test_gateway_retry_flow.py -v
```

Expected: FAIL because `optimus.retry.gated_run` does not exist.

- [x] **Step 3: Implement gated retry runner**

Create `src/optimus/retry/gated_run.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Generic, TypeVar

from optimus.gates.fitness import CompositeGateError, CompositeGateResult, FitnessCheck
from optimus.gates.mutation_flow import ShadowWorkspaceMutationRunner
from optimus.runtime.state import RuntimeContext
from optimus.retry.policy import RetryAction, RetryDecision, RetryPolicy, classify_failure
from optimus.telemetry.events import TelemetryEvent

T = TypeVar("T")


@dataclass(frozen=True)
class GatedAttempt(Generic[T]):
    attempt: int
    candidate: T
    gate_result: CompositeGateResult
    failure_summary: str | None


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
    ) -> GatedRetryResult[T]:
        attempts: list[GatedAttempt[T]] = []
        prior_failure_summaries: list[str] = []
        attempt = 1
        while True:
            candidate = plan_candidate(attempt, tuple(prior_failure_summaries))
            gate_result = ShadowWorkspaceMutationRunner(
                checks_factory=lambda shadow_root: checks_factory(candidate, shadow_root)
            ).run(
                context=context,
                workspace_root=workspace_root,
                apply_candidate=lambda shadow_root: apply_candidate(candidate, shadow_root),
            )
            self._emit_fitness_gate(gate_result=gate_result, attempt=attempt)
            failure_summary = None
            if gate_result.passed:
                attempts.append(GatedAttempt(attempt=attempt, candidate=candidate, gate_result=gate_result, failure_summary=None))
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

    def _emit_fitness_gate(self, *, gate_result: CompositeGateResult, attempt: int) -> None:
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
                cost_usd=Decimal("0"),
            )
        )


def _sleep_ms(delay_ms: int) -> None:
    import time

    time.sleep(delay_ms / 1000)
```

Modify `classify_failure()` in `src/optimus/retry/policy.py` to classify `CompositeGateError` as retryable:

```python
def classify_failure(error: BaseException) -> FailureClassification:
    from optimus.gates.fitness import CompositeGateError

    if isinstance(error, CompositeGateError):
        return _classification(FailureKind.FITNESS_GATE, FailureSeverity.RETRYABLE, error)
```

Keep the existing classification branches after this new branch.

Update `src/optimus/retry/__init__.py`:

```python
from optimus.retry.gated_run import GatedAttempt, GatedRetryResult, GatedRetryRunner
```

Append to `__all__`:

```python
    "GatedAttempt",
    "GatedRetryResult",
    "GatedRetryRunner",
```

- [x] **Step 4: Run retry integration tests**

Run:

```bash
pytest tests/unit/retry/test_policy.py tests/unit/retry/test_gated_run.py tests/integration/retry/test_gateway_retry_flow.py -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/optimus/retry/__init__.py src/optimus/retry/gated_run.py src/optimus/retry/policy.py tests/unit/retry/test_policy.py tests/unit/retry/test_gated_run.py tests/integration/retry/test_gateway_retry_flow.py
git commit -m "Retry gated candidates without partial writes."
```

## Task 6: Golden Task Fixtures And Deterministic Evaluator

**Files:**
- Create: `src/optimus/golden/__init__.py`
- Create: `src/optimus/golden/tasks.py`
- Create: `src/optimus/golden/runner.py`
- Create: `tests/fixtures/golden_tasks/phase1_golden_tasks.json`
- Test: `tests/unit/golden/test_tasks.py`
- Test: `tests/unit/golden/test_runner.py`

- [x] **Step 1: Write failing golden task tests**

Create `tests/unit/golden/test_tasks.py`:

```python
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from optimus.golden.tasks import GoldenTaskResult, evaluate_golden_task, load_golden_tasks


FIXTURE_PATH = Path("tests/fixtures/golden_tasks/phase1_golden_tasks.json")


def test_phase1_golden_tasks_fixture_loads_expected_release_gate_case():
    tasks = load_golden_tasks(FIXTURE_PATH)

    assert len(tasks) == 10
    assert tasks[-1].task_id == "one-key-release-gate"
    assert tasks[-1].release_gate is True
    assert tasks[-1].max_cost_usd == Decimal("0.050")


def test_golden_task_evaluator_passes_expected_agent_outcome():
    task = next(task for task in load_golden_tasks(FIXTURE_PATH) if task.task_id == "docstring-single-function")
    result = GoldenTaskResult(
        task_id=task.task_id,
        actual_mode="agent",
        actual_tools=("file_reader", "write_file"),
        actual_cost_usd=Decimal("0.009"),
        actual_final_state="completed",
        mutation_count=1,
        provider_keys_resolvable=(),
    )

    evaluation = evaluate_golden_task(task, result)

    assert evaluation.passed is True
    assert evaluation.failures == ()


def test_golden_task_evaluator_fails_on_extra_cost_and_wrong_tool():
    task = next(task for task in load_golden_tasks(FIXTURE_PATH) if task.task_id == "dependency-version-lookup")
    result = GoldenTaskResult(
        task_id=task.task_id,
        actual_mode="plan_chat",
        actual_tools=("file_reader", "web_extract"),
        actual_cost_usd=Decimal("0.020"),
        actual_final_state="chat_only",
        mutation_count=0,
        provider_keys_resolvable=(),
    )

    evaluation = evaluate_golden_task(task, result)

    assert evaluation.passed is False
    assert "expected tool web_search at position 2, got web_extract" in evaluation.failures
    assert "actual cost 0.020 exceeds max 0.008" in evaluation.failures


def test_release_gate_task_fails_when_provider_key_is_resolvable():
    task = next(task for task in load_golden_tasks(FIXTURE_PATH) if task.task_id == "one-key-release-gate")
    result = GoldenTaskResult(
        task_id=task.task_id,
        actual_mode="agent",
        actual_tools=tuple(task.expected_tools),
        actual_cost_usd=Decimal("0.020"),
        actual_final_state="completed",
        mutation_count=1,
        provider_keys_resolvable=("OPENAI_API_KEY",),
    )

    evaluation = evaluate_golden_task(task, result)

    assert evaluation.passed is False
    assert "provider keys resolvable: OPENAI_API_KEY" in evaluation.failures
```

- [x] **Step 2: Add failing fixture**

Create `tests/fixtures/golden_tasks/phase1_golden_tasks.json`:

```json
{
  "version": "2026-07-05",
  "pricing_snapshot_id": "phase1-golden-2026-07-05",
  "cache_policy": "cold-cache-per-scenario",
  "tasks": [
    {
      "task_id": "explain-small-function",
      "description": "Explain a function under 15 lines.",
      "expected_mode": "plan_chat",
      "expected_tools": ["file_reader"],
      "max_cost_usd": "0.005",
      "expected_final_state": "chat_only",
      "mutation_expected": false,
      "release_gate": false
    },
    {
      "task_id": "docstring-single-function",
      "description": "Add a docstring to one function.",
      "expected_mode": "agent",
      "expected_tools": ["file_reader", "write_file"],
      "max_cost_usd": "0.012",
      "expected_final_state": "completed",
      "mutation_expected": true,
      "release_gate": false
    },
    {
      "task_id": "single-file-bugfix",
      "description": "Fix a known bug in a single file.",
      "expected_mode": "agent",
      "expected_tools": ["file_reader", "shadow_apply", "write_file"],
      "max_cost_usd": "0.018",
      "expected_final_state": "completed",
      "mutation_expected": true,
      "release_gate": false
    },
    {
      "task_id": "two-file-refactor",
      "description": "Refactor across two files.",
      "expected_mode": "agent",
      "expected_tools": ["file_reader", "shadow_apply", "write_file", "write_file", "test_runner"],
      "max_cost_usd": "0.035",
      "expected_final_state": "completed",
      "mutation_expected": true,
      "release_gate": false
    },
    {
      "task_id": "dependency-version-lookup",
      "description": "Lookup a dependency version with PACKAGE_VERSION reason.",
      "expected_mode": "plan_chat",
      "expected_tools": ["file_reader", "web_search"],
      "max_cost_usd": "0.008",
      "expected_final_state": "chat_only",
      "mutation_expected": false,
      "release_gate": false
    },
    {
      "task_id": "security-advisory-check",
      "description": "Check a security advisory with SECURITY_ADVISORY reason.",
      "expected_mode": "plan_chat",
      "expected_tools": ["web_search"],
      "max_cost_usd": "0.010",
      "expected_final_state": "chat_only",
      "mutation_expected": false,
      "release_gate": false
    },
    {
      "task_id": "multi-file-changeset",
      "description": "Execute a multi-file changeset with reflection bounds.",
      "expected_mode": "agent",
      "expected_tools": ["file_reader", "shadow_apply", "write_file", "write_file", "write_file", "test_runner", "reflection"],
      "max_cost_usd": "0.055",
      "expected_final_state": "completed",
      "mutation_expected": true,
      "release_gate": false
    },
    {
      "task_id": "plan-then-approve-agent",
      "description": "Produce plan text, receive approval, then mutate.",
      "expected_mode": "agent",
      "expected_tools": ["file_reader", "write_file"],
      "max_cost_usd": "0.020",
      "expected_final_state": "completed",
      "mutation_expected": true,
      "release_gate": false
    },
    {
      "task_id": "budget-exhausted",
      "description": "Terminate cleanly when budget is exhausted.",
      "expected_mode": "agent",
      "expected_tools": ["file_reader"],
      "max_cost_usd": "0.001",
      "expected_final_state": "terminated",
      "mutation_expected": false,
      "release_gate": false
    },
    {
      "task_id": "one-key-release-gate",
      "description": "Run release gate with only Optimus credentials.",
      "expected_mode": "agent",
      "expected_tools": ["file_reader", "shadow_apply", "write_file", "test_runner", "release_gate"],
      "max_cost_usd": "0.050",
      "expected_final_state": "completed",
      "mutation_expected": true,
      "release_gate": true
    }
  ]
}
```

- [x] **Step 3: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/golden/test_tasks.py -v
```

Expected: FAIL because `optimus.golden.tasks` does not exist.

- [x] **Step 4: Implement golden task evaluator**

Create `src/optimus/golden/tasks.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class GoldenTask(BaseModel):
    model_config = ConfigDict(frozen=True)

    task_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    expected_mode: str = Field(min_length=1)
    expected_tools: tuple[str, ...]
    max_cost_usd: Decimal = Field(ge=Decimal("0"))
    expected_final_state: str = Field(min_length=1)
    mutation_expected: bool
    release_gate: bool = False


@dataclass(frozen=True)
class GoldenTaskResult:
    task_id: str
    actual_mode: str
    actual_tools: tuple[str, ...]
    actual_cost_usd: Decimal
    actual_final_state: str
    mutation_count: int
    provider_keys_resolvable: tuple[str, ...]


@dataclass(frozen=True)
class GoldenTaskEvaluation:
    task: GoldenTask
    result: GoldenTaskResult
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


def load_golden_tasks(path: str | Path) -> tuple[GoldenTask, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"), parse_float=Decimal)
    return tuple(GoldenTask.model_validate(task) for task in payload["tasks"])


def evaluate_golden_task(task: GoldenTask, result: GoldenTaskResult) -> GoldenTaskEvaluation:
    failures: list[str] = []
    if result.task_id != task.task_id:
        failures.append(f"expected task_id {task.task_id}, got {result.task_id}")
    if result.actual_mode != task.expected_mode:
        failures.append(f"expected mode {task.expected_mode}, got {result.actual_mode}")
    failures.extend(_tool_failures(task.expected_tools, result.actual_tools))
    if result.actual_cost_usd > task.max_cost_usd:
        failures.append(f"actual cost {result.actual_cost_usd} exceeds max {task.max_cost_usd}")
    if result.actual_final_state != task.expected_final_state:
        failures.append(f"expected final state {task.expected_final_state}, got {result.actual_final_state}")
    if task.mutation_expected and result.mutation_count <= 0:
        failures.append("expected at least one mutation")
    if not task.mutation_expected and result.mutation_count != 0:
        failures.append(f"expected zero mutations, got {result.mutation_count}")
    if task.release_gate and result.provider_keys_resolvable:
        failures.append(f"provider keys resolvable: {', '.join(sorted(result.provider_keys_resolvable))}")
    return GoldenTaskEvaluation(task=task, result=result, failures=tuple(failures))


def _tool_failures(expected: tuple[str, ...], actual: tuple[str, ...]) -> tuple[str, ...]:
    failures: list[str] = []
    for index, expected_tool in enumerate(expected):
        if index >= len(actual):
            failures.append(f"missing expected tool {expected_tool} at position {index + 1}")
            continue
        actual_tool = actual[index]
        if actual_tool != expected_tool:
            failures.append(f"expected tool {expected_tool} at position {index + 1}, got {actual_tool}")
    if len(actual) > len(expected):
        extra = ", ".join(actual[len(expected) :])
        failures.append(f"unexpected extra tools: {extra}")
    return tuple(failures)
```

Create `src/optimus/golden/__init__.py`:

```python
from optimus.golden.tasks import (
    GoldenTask,
    GoldenTaskEvaluation,
    GoldenTaskResult,
    evaluate_golden_task,
    load_golden_tasks,
)

__all__ = [
    "GoldenTask",
    "GoldenTaskEvaluation",
    "GoldenTaskResult",
    "evaluate_golden_task",
    "load_golden_tasks",
]
```

- [x] **Step 5: Write failing golden suite runner tests**

Create `tests/unit/golden/test_runner.py`:

```python
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from optimus.golden.runner import GoldenTaskHarness, evaluate_golden_task_suite
from optimus.golden.tasks import GoldenTask, GoldenTaskResult, load_golden_tasks


FIXTURE_PATH = Path("tests/fixtures/golden_tasks/phase1_golden_tasks.json")


class FakeHarness:
    def run(self, task: GoldenTask) -> GoldenTaskResult:
        return GoldenTaskResult(
            task_id=task.task_id,
            actual_mode=task.expected_mode,
            actual_tools=tuple(task.expected_tools),
            actual_cost_usd=task.max_cost_usd,
            actual_final_state=task.expected_final_state,
            mutation_count=1 if task.mutation_expected else 0,
            provider_keys_resolvable=(),
        )


class LeakyHarness:
    def run(self, task: GoldenTask) -> GoldenTaskResult:
        return GoldenTaskResult(
            task_id=task.task_id,
            actual_mode=task.expected_mode,
            actual_tools=tuple(task.expected_tools),
            actual_cost_usd=Decimal("0"),
            actual_final_state=task.expected_final_state,
            mutation_count=1 if task.mutation_expected else 0,
            provider_keys_resolvable=("OPENAI_API_KEY",) if task.release_gate else (),
        )


def test_fake_harness_satisfies_golden_task_protocol():
    harness: GoldenTaskHarness = FakeHarness()
    task = load_golden_tasks(FIXTURE_PATH)[0]

    assert harness.run(task).task_id == task.task_id


def test_evaluate_golden_task_suite_passes_when_harness_matches_expectations():
    report = evaluate_golden_task_suite(load_golden_tasks(FIXTURE_PATH), harness=FakeHarness())

    assert report.passed is True
    assert len(report.evaluations) == 10


def test_evaluate_golden_task_suite_fails_when_release_gate_result_leaks_provider_key():
    report = evaluate_golden_task_suite(load_golden_tasks(FIXTURE_PATH), harness=LeakyHarness())

    assert report.passed is False
    assert any("provider keys resolvable" in failure for evaluation in report.evaluations for failure in evaluation.failures)
```

- [x] **Step 6: Implement golden suite runner**

Create `src/optimus/golden/runner.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from optimus.golden.tasks import GoldenTask, GoldenTaskEvaluation, GoldenTaskResult, evaluate_golden_task
from optimus.telemetry.events import TelemetryEvent


class GoldenTaskHarness(Protocol):
    def run(self, task: GoldenTask) -> GoldenTaskResult:
        raise NotImplementedError


@dataclass(frozen=True)
class GoldenTaskSuiteReport:
    evaluations: tuple[GoldenTaskEvaluation, ...]

    @property
    def passed(self) -> bool:
        return all(evaluation.passed for evaluation in self.evaluations)

    @property
    def failure_summary(self) -> str:
        failures = [
            f"{evaluation.task.task_id}: {'; '.join(evaluation.failures)}"
            for evaluation in self.evaluations
            if not evaluation.passed
        ]
        return "all golden tasks passed" if not failures else " | ".join(failures)


def evaluate_golden_task_suite(
    tasks: tuple[GoldenTask, ...],
    *,
    harness: GoldenTaskHarness,
    event_sink: Callable[[TelemetryEvent], None] | None = None,
    run_id: str = "golden-task-suite",
    session_id: str | None = None,
) -> GoldenTaskSuiteReport:
    evaluations: list[GoldenTaskEvaluation] = []
    for task in tasks:
        evaluation = evaluate_golden_task(task, harness.run(task))
        evaluations.append(evaluation)
        if event_sink is not None:
            event_sink(
                TelemetryEvent.golden_task(
                    run_id=run_id,
                    session_id=session_id,
                    request_id=task.task_id,
                    occurred_at=datetime.now(tz=UTC),
                    task_id=task.task_id,
                    passed=evaluation.passed,
                    expected_mode=task.expected_mode,
                    actual_mode=evaluation.result.actual_mode,
                    expected_tools=tuple(task.expected_tools),
                    actual_tools=evaluation.result.actual_tools,
                    max_cost_usd=task.max_cost_usd,
                    actual_cost_usd=evaluation.result.actual_cost_usd,
                    expected_final_state=task.expected_final_state,
                    actual_final_state=evaluation.result.actual_final_state,
                )
            )
    return GoldenTaskSuiteReport(
        evaluations=tuple(evaluations)
    )
```

Update `src/optimus/golden/__init__.py`:

```python
from optimus.golden.runner import GoldenTaskHarness, GoldenTaskSuiteReport, evaluate_golden_task_suite
```

Append to `__all__`:

```python
    "GoldenTaskHarness",
    "GoldenTaskSuiteReport",
    "evaluate_golden_task_suite",
```

- [x] **Step 7: Run golden task tests**

Run:

```bash
pytest tests/unit/golden/test_tasks.py tests/unit/golden/test_runner.py -v
```

Expected: PASS.

- [x] **Step 8: Commit**

```bash
git add src/optimus/golden/__init__.py src/optimus/golden/tasks.py src/optimus/golden/runner.py tests/fixtures/golden_tasks/phase1_golden_tasks.json tests/unit/golden/test_tasks.py tests/unit/golden/test_runner.py
git commit -m "Add deterministic golden task evaluator."
```

## Task 7: One-Key Credential Scanner

**Files:**
- Create: `src/optimus/release/__init__.py`
- Create: `src/optimus/release/credentials.py`
- Test: `tests/unit/release/test_credentials.py`

- [x] **Step 1: Write failing credential scanner tests**

Create `tests/unit/release/test_credentials.py`:

```python
from __future__ import annotations

from optimus.release.credentials import (
    ALLOWED_LOCAL_CREDENTIAL_NAMES,
    PROVIDER_CREDENTIAL_NAMES,
    scan_local_credentials,
)


def test_scanner_allows_only_optimus_gateway_credentials(monkeypatch):
    for key in PROVIDER_CREDENTIAL_NAMES | ALLOWED_LOCAL_CREDENTIAL_NAMES:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "https://gateway.optimus.ai")
    monkeypatch.setenv("OPTIMUS_API_KEY", "opt-test")

    result = scan_local_credentials()

    assert result.passed is True
    assert result.allowed_present == ("OPTIMUS_API_KEY", "OPTIMUS_GATEWAY_URL")
    assert result.provider_keys_resolvable == ()


def test_scanner_fails_when_provider_key_is_resolvable(monkeypatch):
    for key in PROVIDER_CREDENTIAL_NAMES | ALLOWED_LOCAL_CREDENTIAL_NAMES:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "https://gateway.optimus.ai")
    monkeypatch.setenv("OPTIMUS_API_KEY", "opt-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    result = scan_local_credentials()

    assert result.passed is False
    assert result.provider_keys_resolvable == ("OPENAI_API_KEY",)


def test_scanner_honors_explicit_empty_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real-env")

    result = scan_local_credentials(environ={})

    assert result.passed is True
    assert result.allowed_present == ()
    assert result.provider_keys_resolvable == ()


def test_scanner_checks_selected_config_text_without_returning_secret_values(tmp_path, monkeypatch):
    for key in PROVIDER_CREDENTIAL_NAMES | ALLOWED_LOCAL_CREDENTIAL_NAMES:
        monkeypatch.delenv(key, raising=False)
    config = tmp_path / ".env"
    config.write_text("LANGSMITH_API_KEY=ls-test\nOPTIMUS_API_KEY=opt-test\n", encoding="utf-8")

    result = scan_local_credentials(config_paths=(config,))

    assert result.passed is False
    assert result.provider_keys_resolvable == ("LANGSMITH_API_KEY",)
    assert "ls-test" not in result.summary
    assert "LANGSMITH_API_KEY" in result.summary


def test_scanner_detects_json_and_yaml_process_snapshot_keys(tmp_path, monkeypatch):
    for key in PROVIDER_CREDENTIAL_NAMES | ALLOWED_LOCAL_CREDENTIAL_NAMES:
        monkeypatch.delenv(key, raising=False)
    snapshot = tmp_path / "process-state.json"
    snapshot.write_text('{"env": {"OPENROUTER_API_KEY": "or-test"}, "yaml": "TAVILY_API_KEY: tvly-test"}', encoding="utf-8")

    result = scan_local_credentials(config_paths=(snapshot,))

    assert result.passed is False
    assert result.provider_keys_resolvable == ("OPENROUTER_API_KEY", "TAVILY_API_KEY")
    assert "or-test" not in result.summary
    assert "tvly-test" not in result.summary
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/release/test_credentials.py -v
```

Expected: FAIL because `optimus.release.credentials` does not exist.

- [x] **Step 3: Implement credential scanner**

Create `src/optimus/release/credentials.py`:

```python
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES

ALLOWED_LOCAL_CREDENTIAL_NAMES = frozenset({"OPTIMUS_GATEWAY_URL", "OPTIMUS_API_KEY"})
PROVIDER_CREDENTIAL_NAMES = frozenset(
    {
        *LOCAL_PROVIDER_KEY_NAMES,
        "ANTHROPIC_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "LANGSMITH_API_KEY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "TAVILY_API_KEY",
        "GLM_API_KEY",
    }
)


@dataclass(frozen=True)
class CredentialScanResult:
    allowed_present: tuple[str, ...]
    provider_keys_resolvable: tuple[str, ...]
    config_hits: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.provider_keys_resolvable

    @property
    def summary(self) -> str:
        if self.passed:
            return f"allowed Optimus credentials present: {', '.join(self.allowed_present)}"
        return f"provider credentials resolvable: {', '.join(self.provider_keys_resolvable)}"


def scan_local_credentials(
    *,
    environ: dict[str, str] | None = None,
    config_paths: tuple[str | Path, ...] = (),
) -> CredentialScanResult:
    active_environ = dict(os.environ) if environ is None else environ
    allowed_present = tuple(sorted(key for key in ALLOWED_LOCAL_CREDENTIAL_NAMES if active_environ.get(key)))
    provider_hits = set(key for key in PROVIDER_CREDENTIAL_NAMES if active_environ.get(key))
    config_hits = _scan_config_files(config_paths)
    provider_hits.update(config_hits)
    return CredentialScanResult(
        allowed_present=allowed_present,
        provider_keys_resolvable=tuple(sorted(provider_hits)),
        config_hits=tuple(sorted(config_hits)),
    )


def _scan_config_files(config_paths: tuple[str | Path, ...]) -> set[str]:
    hits: set[str] = set()
    names_pattern = "|".join(re.escape(name) for name in sorted(PROVIDER_CREDENTIAL_NAMES, key=len, reverse=True))
    pattern = re.compile(rf'["\']?\b({names_pattern})\b["\']?\s*[:=]', re.IGNORECASE)
    for config_path in config_paths:
        path = Path(config_path)
        if not path.exists() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in pattern.finditer(text):
            canonical = _canonical_name(match.group(1))
            hits.add(canonical)
    return hits


def _canonical_name(name: str) -> str:
    upper = name.upper()
    for candidate in PROVIDER_CREDENTIAL_NAMES:
        if candidate.upper() == upper:
            return candidate
    return upper
```

Create `src/optimus/release/__init__.py`:

```python
from optimus.release.credentials import (
    ALLOWED_LOCAL_CREDENTIAL_NAMES,
    PROVIDER_CREDENTIAL_NAMES,
    CredentialScanResult,
    scan_local_credentials,
)

__all__ = [
    "ALLOWED_LOCAL_CREDENTIAL_NAMES",
    "PROVIDER_CREDENTIAL_NAMES",
    "CredentialScanResult",
    "scan_local_credentials",
]
```

- [x] **Step 4: Run credential tests**

Run:

```bash
pytest tests/unit/release/test_credentials.py -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/optimus/release/__init__.py src/optimus/release/credentials.py tests/unit/release/test_credentials.py
git commit -m "Add one-key credential scanner."
```

## Task 8: Release Gate Runner And Defaults

**Files:**
- Create: `src/optimus/release/runner.py`
- Create: `src/optimus/release/defaults.py`
- Modify: `src/optimus/release/__init__.py`
- Test: `tests/unit/release/test_runner.py`
- Test: `tests/unit/release/test_defaults.py`
- Test: `tests/integration/release/test_phase1_release_runner.py`

- [x] **Step 1: Write failing release runner tests**

Create `tests/unit/release/test_runner.py`:

```python
from __future__ import annotations

from optimus.release.runner import CallableGate, CommandGate, ReleaseGateRunner


def test_release_runner_executes_gates_in_order_and_reports_pass():
    seen: list[str] = []
    gates = (
        CallableGate(name="first", run=lambda: seen.append("first") or (True, "ok")),
        CallableGate(name="second", run=lambda: seen.append("second") or (True, "ok")),
    )

    report = ReleaseGateRunner(gates=gates).run()

    assert report.passed is True
    assert seen == ["first", "second"]
    assert [result.name for result in report.results] == ["first", "second"]


def test_release_runner_continues_after_failure_to_collect_full_report():
    gates = (
        CallableGate(name="first", run=lambda: (False, "failed")),
        CallableGate(name="second", run=lambda: (True, "ok")),
    )

    report = ReleaseGateRunner(gates=gates).run()

    assert report.passed is False
    assert [(result.name, result.passed) for result in report.results] == [("first", False), ("second", True)]


def test_command_gate_uses_injected_executor_and_redacts_output():
    commands: list[tuple[str, ...]] = []

    def executor(command: tuple[str, ...]) -> tuple[int, str, str]:
        commands.append(command)
        return (1, "OPENAI_API_KEY=sk-test", "")

    gate = CommandGate(name="provider-key-check", command=("python", "-c", "print('x')"), executor=executor)

    result = gate.run()

    assert result.passed is False
    assert commands == [("python", "-c", "print('x')")]
    assert "sk-test" not in result.output_summary
    assert "**********" in result.output_summary


def test_release_report_serializes_to_json_dict():
    report = ReleaseGateRunner(gates=(CallableGate(name="gate", run=lambda: (True, "ok")),)).run()

    assert report.to_json_dict()["passed"] is True
    assert report.to_json_dict()["results"][0]["name"] == "gate"
```

Create `tests/unit/release/test_defaults.py`:

```python
from __future__ import annotations

from optimus.release.defaults import build_phase1_release_gates


def test_default_phase1_release_gates_include_coverage_golden_and_one_key():
    gates = build_phase1_release_gates()
    names = [gate.name for gate in gates]

    assert "unit-and-integration-tests" in names
    assert "coverage-80" in names
    assert "golden-task-suite" in names
    assert "one-key-credential-scan" in names
    assert names[-1] == "one-key-credential-scan"


def test_default_golden_gate_fails_when_no_harness_is_configured():
    gates = build_phase1_release_gates()
    golden_gate = next(gate for gate in gates if gate.name == "golden-task-suite")

    result = golden_gate.run()

    assert result.passed is False
    assert "golden task harness not configured" in result.output_summary
```

Create `tests/integration/release/test_phase1_release_runner.py`:

```python
from __future__ import annotations

from optimus.release.runner import CallableGate, ReleaseGateRunner


def test_injected_phase1_release_runner_reports_golden_and_one_key_results():
    report = ReleaseGateRunner(
        gates=(
            CallableGate(name="golden-task-suite", run=lambda: (True, "10 golden tasks evaluated")),
            CallableGate(name="one-key-credential-scan", run=lambda: (True, "allowed Optimus credentials present")),
        )
    ).run()

    assert report.passed is True
    assert [result.name for result in report.results] == ["golden-task-suite", "one-key-credential-scan"]
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/release/test_runner.py tests/unit/release/test_defaults.py tests/integration/release/test_phase1_release_runner.py -v
```

Expected: FAIL because `optimus.release.runner` and defaults do not exist.

- [x] **Step 3: Implement release runner**

Create `src/optimus/release/runner.py`:

```python
from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from optimus.telemetry.events import TelemetryEvent
from optimus.telemetry.redaction import redact_for_telemetry


@dataclass(frozen=True)
class ReleaseGateResult:
    name: str
    passed: bool
    output_summary: str
    duration_ms: int

    def to_json_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "passed": self.passed,
            "output_summary": self.output_summary,
            "duration_ms": self.duration_ms,
        }


class ReleaseGate(Protocol):
    name: str

    def run(self) -> ReleaseGateResult:
        raise NotImplementedError


class CallableGate:
    def __init__(self, *, name: str, run: Callable[[], tuple[bool, str]]) -> None:
        self.name = name
        self._run = run

    def run(self) -> ReleaseGateResult:
        started = datetime.now(tz=UTC)
        passed, summary = self._run()
        return ReleaseGateResult(
            name=self.name,
            passed=passed,
            output_summary=_safe_summary(summary),
            duration_ms=_duration_ms(started),
        )


@dataclass(frozen=True)
class CommandGate:
    name: str
    command: tuple[str, ...]
    executor: Callable[[tuple[str, ...]], tuple[int, str, str]] | None = None

    def run(self) -> ReleaseGateResult:
        started = datetime.now(tz=UTC)
        exit_code, stdout, stderr = (self.executor or _run_command)(self.command)
        output = "\n".join(part for part in (stdout.strip(), stderr.strip()) if part)
        return ReleaseGateResult(
            name=self.name,
            passed=exit_code == 0,
            output_summary=_safe_summary(output or f"exit_code={exit_code}"),
            duration_ms=_duration_ms(started),
        )


@dataclass(frozen=True)
class ReleaseGateReport:
    results: tuple[ReleaseGateResult, ...]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    def to_json_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "results": [result.to_json_dict() for result in self.results],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_json_dict(), sort_keys=True, indent=2)


class ReleaseGateRunner:
    def __init__(
        self,
        *,
        gates: tuple[ReleaseGate, ...],
        event_sink: Callable[[TelemetryEvent], None] | None = None,
        run_id: str = "release-gate",
        session_id: str | None = None,
    ) -> None:
        self._gates = gates
        self._event_sink = event_sink
        self._run_id = run_id
        self._session_id = session_id

    def run(self) -> ReleaseGateReport:
        results: list[ReleaseGateResult] = []
        for gate in self._gates:
            result = gate.run()
            results.append(result)
            if self._event_sink is not None:
                self._event_sink(
                    TelemetryEvent.release_gate(
                        run_id=self._run_id,
                        session_id=self._session_id,
                        request_id=gate.name,
                        occurred_at=datetime.now(tz=UTC),
                        gate_name=gate.name,
                        passed=result.passed,
                        duration_ms=result.duration_ms,
                        output_summary=result.output_summary,
                    )
                )
        return ReleaseGateReport(results=tuple(results))


def _run_command(command: tuple[str, ...]) -> tuple[int, str, str]:
    completed = subprocess.run(command, check=False, text=True, capture_output=True)
    return completed.returncode, completed.stdout, completed.stderr


def _duration_ms(started: datetime) -> int:
    return max(int((datetime.now(tz=UTC) - started).total_seconds() * 1000), 0)


def _safe_summary(summary: str) -> str:
    redacted = redact_for_telemetry(summary)
    return str(redacted)
```

- [x] **Step 4: Implement default gate list**

Create `src/optimus/release/defaults.py`:

```python
from __future__ import annotations

from pathlib import Path

from optimus.golden.runner import GoldenTaskHarness, evaluate_golden_task_suite
from optimus.golden.tasks import load_golden_tasks
from optimus.release.credentials import scan_local_credentials
from optimus.release.runner import CallableGate, CommandGate, ReleaseGate


def build_phase1_release_gates(
    *,
    python_executable: str = "python",
    golden_harness: GoldenTaskHarness | None = None,
) -> tuple[ReleaseGate, ...]:
    return (
        CommandGate(
            name="unit-and-integration-tests",
            command=(python_executable, "-m", "pytest", "tests/unit", "tests/integration", "-q"),
        ),
        CommandGate(
            name="coverage-80",
            command=(
                python_executable,
                "-m",
                "pytest",
                "--cov=optimus",
                "--cov-branch",
                "--cov-report=term-missing",
                "--cov-fail-under=80",
                "-q",
            ),
        ),
        CommandGate(
            name="diff-whitespace-check",
            command=("git", "diff", "--check"),
        ),
        CallableGate(name="golden-task-suite", run=lambda: _golden_task_suite_gate(golden_harness)),
        CallableGate(name="one-key-credential-scan", run=_one_key_credential_gate),
    )


def _golden_task_suite_gate(golden_harness: GoldenTaskHarness | None) -> tuple[bool, str]:
    if golden_harness is None:
        return False, "golden task harness not configured"
    tasks = load_golden_tasks(Path("tests/fixtures/golden_tasks/phase1_golden_tasks.json"))
    report = evaluate_golden_task_suite(tasks, harness=golden_harness)
    return report.passed, report.failure_summary


def _one_key_credential_gate() -> tuple[bool, str]:
    result = scan_local_credentials(
        config_paths=(
            Path(".env"),
            Path(".env.local"),
            Path("pyproject.toml"),
        )
    )
    return result.passed, result.summary
```

Update `src/optimus/release/__init__.py`:

```python
from optimus.release.defaults import build_phase1_release_gates
from optimus.release.runner import CallableGate, CommandGate, ReleaseGateReport, ReleaseGateResult, ReleaseGateRunner
```

Append to `__all__`:

```python
    "CallableGate",
    "CommandGate",
    "ReleaseGateReport",
    "ReleaseGateResult",
    "ReleaseGateRunner",
    "build_phase1_release_gates",
```

- [x] **Step 5: Run release runner tests**

Run:

```bash
pytest tests/unit/release/test_runner.py tests/unit/release/test_defaults.py tests/integration/release/test_phase1_release_runner.py -v
```

Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add src/optimus/release/__init__.py src/optimus/release/runner.py src/optimus/release/defaults.py tests/unit/release/test_runner.py tests/unit/release/test_defaults.py tests/integration/release/test_phase1_release_runner.py
git commit -m "Add ordered Phase 1 release gate runner."
```

## Task 9: Release Gate CLI And README

**Files:**
- Create: `tools/run_phase1_release_gate.py`
- Modify: `README.md`
- Test: `tests/unit/release/test_defaults.py`

- [x] **Step 1: Write failing CLI smoke test**

Append to `tests/unit/release/test_defaults.py`:

```python
from pathlib import Path


def test_phase1_release_gate_script_exists_and_uses_default_builder():
    script = Path("tools/run_phase1_release_gate.py")
    text = script.read_text(encoding="utf-8")

    assert "build_phase1_release_gates" in text
    assert "ReleaseGateRunner" in text
    assert "return 0 if report.passed else 1" in text
    assert "raise SystemExit(main())" in text
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/unit/release/test_defaults.py -v
```

Expected: FAIL because the script does not exist.

- [x] **Step 3: Add release gate script**

Create `tools/run_phase1_release_gate.py`:

```python
from __future__ import annotations

from optimus.release.defaults import build_phase1_release_gates
from optimus.release.runner import ReleaseGateRunner


def main() -> int:
    report = ReleaseGateRunner(gates=build_phase1_release_gates()).run()
    print(report.to_json())
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [x] **Step 4: Add README release-gate note**

Append to `README.md`:

```markdown
### Phase 1 Release Gate

Plan 8 adds a local release-gate runner for Sprint 1 sign-off. The runner
executes the ordered unit, integration, coverage, golden-task-suite, and one-key
credential checks and emits a JSON report.

```bash
python tools/run_phase1_release_gate.py
```

The default CLI is fail-closed until a golden-task harness is configured. A
run with no harness exits non-zero with `golden task harness not configured`;
the Sprint 1 PASS state requires wiring a deterministic local/staging harness
that produces `GoldenTaskResult` records for every fixture.

The final go/no-go rule is strict: a Plan-mode and Agent-mode release run must
complete with only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` available
locally. Provider keys such as Tavily, OpenAI, OpenRouter, GLM, Anthropic, and
LangSmith must remain Gateway-side and must not be resolvable from the local
environment, selected local config files, or serialized process-state snapshots.
```

- [x] **Step 5: Run README/script tests**

Run:

```bash
pytest tests/unit/release/test_defaults.py -v
```

Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add README.md tools/run_phase1_release_gate.py tests/unit/release/test_defaults.py
git commit -m "Document Phase 1 release gate runner."
```

## Task 10: Focused Verification And Coverage

**Files:**
- Verify: `src/optimus/retry`
- Verify: `src/optimus/gates`
- Verify: `src/optimus/golden`
- Verify: `src/optimus/release`
- Verify: `src/optimus/telemetry/events.py`

- [ ] **Step 1: Run focused Plan 8 tests**

Run:

```bash
pytest tests/unit/retry tests/unit/gates tests/unit/golden tests/unit/release tests/integration/retry tests/integration/gates tests/integration/release -v
```

Expected: PASS.

- [ ] **Step 2: Run telemetry regression tests**

Run:

```bash
pytest tests/unit/telemetry tests/integration/telemetry -v
```

Expected: PASS.

- [ ] **Step 3: Run safety-critical coverage for Plan 8 modules**

Run:

```bash
pytest tests/unit/retry tests/unit/gates tests/unit/golden tests/unit/release tests/integration/retry tests/integration/gates tests/integration/release --cov=optimus.retry --cov=optimus.gates --cov=optimus.golden --cov=optimus.release --cov=optimus.telemetry --cov-branch --cov-report=term-missing --cov-fail-under=80
```

Expected: PASS with no Plan 8 module below the project aggregate threshold.

- [ ] **Step 4: Run full package coverage gate**

Run:

```bash
pytest --cov=optimus --cov-branch --cov-report=term-missing -v
```

Expected: PASS with aggregate Python production-code coverage at or above 80%.

- [ ] **Step 5: Run local release-gate script with injected Optimus-only environment**

Run after clearing provider keys from the shell, before a golden-task harness is configured:

```bash
python tools/run_phase1_release_gate.py
```

Expected: FAIL with exit code 1 and a JSON report where `golden-task-suite` is the only failing gate, with output summary `golden task harness not configured`, assuming the unit, integration, coverage, diff, and one-key credential gates pass. This confirms the CLI fails closed instead of silently passing a fixture-count check.

Run again after wiring a deterministic local/staging golden-task harness into `build_phase1_release_gates(golden_harness=...)` or an equivalent CLI option:

```bash
python tools/run_phase1_release_gate.py
```

Expected: PASS when `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` are present, no provider keys are resolvable, all golden fixtures produce passing `GoldenTaskResult` records, and the normal unit/integration/coverage/diff gates pass. If staging Gateway E2E credentials are not available, report that the real Gateway portion was not run and include the injected/mock release-runner integration result instead.

- [ ] **Step 6: Check diff hygiene**

Run:

```bash
git status --short
git diff --check
```

Expected: only intentional Plan 8 files are modified or added, with no whitespace errors. Pre-existing unrelated IDE or agent metadata remains untouched.

- [ ] **Step 7: Commit**

```bash
git add src/optimus/retry src/optimus/gates src/optimus/golden src/optimus/release src/optimus/telemetry/events.py src/optimus/telemetry/redaction.py src/optimus/telemetry/__init__.py tests/unit/retry tests/unit/gates tests/unit/golden tests/unit/release tests/integration/retry tests/integration/gates tests/integration/release tests/fixtures/golden_tasks tools/run_phase1_release_gate.py README.md
git commit -m "Add retry gates golden tasks and release runner."
```

## Deferred Follow-Ups

These items are accepted Plan 8 limitations. They should be tracked with the stable IDs below during execution and converted into GitHub issues or the project task tracker before the Plan 8 branch is merged. They do not block Plan 8 unless the implementation or release gates show that one of them affects correctness for the current sprint.

### P8-FU-1: Propagate deletions from shadow workspaces

**Current limitation:** `ShadowWorkspace.changed_paths()` detects additions and modifications by comparing files present in the shadow workspace against the original workspace. It does not detect a file that existed in the original workspace and was deleted by a mutation candidate in the shadow workspace.

**Why deferred:** Plan 8's primary safety requirement is to prevent partial writes and only promote validated candidates. Addition and modification promotion covers the expected Phase 1 mutation flow; deletion propagation can be added as a hardening improvement without changing the gate architecture.

**Acceptance criteria:**
- A candidate that deletes a tracked file in the shadow workspace produces a deletion entry in the promotion plan.
- Promotion removes that file from the real workspace only after `assert_mutation_allowed()` and required composite gates pass.
- Rollback restores deleted files when promotion fails midway.
- Tests cover delete-only, modify-and-delete, and rollback-after-delete scenarios.

**Target:** Plan 9 or the mutation-flow hardening backlog.

### P8-FU-2: Make shadow copy ignore rules configurable

**Current limitation:** `ShadowWorkspace.create()` uses a fixed `shutil.copytree(..., ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))` ignore set. Large local directories such as `.venv`, `node_modules`, `.mypy_cache`, `.ruff_cache`, or project-specific build outputs are not configurable in the Plan 8 API.

**Why deferred:** The fixed ignore set is sufficient for the focused Plan 8 tests and preserves a small implementation surface. Configurable ignore rules are operational hardening for larger local workspaces.

**Acceptance criteria:**
- Callers can pass additional ignore patterns without replacing the default safety ignore set.
- Defaults still ignore `.git`, `__pycache__`, and `.pytest_cache`.
- Tests verify that configured large directories are skipped and that source files remain copied into the shadow workspace.
- README or developer docs describe how to add local ignore patterns for heavy directories.

**Target:** Plan 9 or the local-runtime performance backlog.

### P8-FU-3: Remove promotion failure test hook from production API surface

**Current limitation:** `fail_after_promoted_paths` is a test hook on the shadow promotion path. It exists to force deterministic mid-promotion failures and prove backup/rollback behavior, but it exposes test-only behavior through production-callable signatures.

**Why deferred:** The hook keeps Plan 8 rollback tests deterministic without introducing a larger fault-injection abstraction. It is acceptable for the first implementation as long as the behavior is documented and not used by runtime code paths.

**Acceptance criteria:**
- Runtime promotion APIs no longer expose `fail_after_promoted_paths`.
- Rollback tests still force deterministic mid-promotion failure through a test-only seam, such as an injected file copier, promotion strategy, or private test helper.
- Production runtime code cannot trigger artificial promotion failure through public parameters.
- Existing rollback coverage remains equivalent or stronger.

**Target:** Plan 9 or the mutation-flow API cleanup backlog.

## Self-Review

- Spec coverage: The plan maps every Plan 8 roadmap deliverable to executable tasks: failure classification and max-3 retry in Task 1, telemetry constructors and public redaction in Task 2, composite gate results in Task 3, shadow-workspace no-partial-write mutation flow in Task 4, gate failure replanning with `RuntimeContext` retry state in Task 5, golden task fixtures plus suite-result evaluation in Task 6, one-key environment/config/snapshot scanning in Task 7, release runner in Task 8, CLI/docs in Task 9, and coverage/release verification in Task 10.
- Source-of-truth discipline: Gateway/provider usage remains Plan 7-owned; Plan 8 consumes telemetry and cost fields without estimating tokens or cost.
- One-key model: Local runtime still allows only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; provider and LangSmith keys are treated as release-gate failures.
- Fail-closed behavior: gate exceptions become failed required gate results; candidates are applied to a shadow workspace and real workspace promotion occurs only after `assert_mutation_allowed()` and required composite gates pass, with rollback on promotion errors.
- Golden-task scoring: deterministic fixture evaluation is implemented without adding new local provider keys or LLM-judge dependencies, and the release gate requires actual `GoldenTaskResult` records from a harness rather than fixture-count checks.
- Context optimization boundary: Plan 10 promotion fields are reserved only as optional warnings; no calibration placeholder becomes a binding release gate in Plan 8.
- Type consistency: retry decisions use `FailureKind`, `FailureSeverity`, and `RetryAction.SUCCESS` for success; gate failures use `CompositeGateError`; golden outcomes use `GoldenTaskResult`; release output uses `ReleaseGateReport`.
- Red-flag scan: The plan contains concrete file paths, test code, implementation code, commands, expected outcomes, and no unresolved placeholders.
- TDD compliance: Every production change starts with a failing unit or integration test, followed by minimal implementation and verification.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-05-retry-fitness-gates-golden-tasks-release-gate.md`. Two execution options:

**1. Subagent-Driven (recommended when available)** - dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - execute tasks in this session task-by-task with checkpoints. Use `superpowers:executing-plans` if available; otherwise follow this plan directly with the same red/green/refactor discipline.

Plan 8 should start after Plan 7 is accepted or merged because it composes the usage and telemetry modules from Plan 7. If executing in a new worktree, create it from latest `main` using the branch/worktree conventions in `CONTRIBUTING.md`.
