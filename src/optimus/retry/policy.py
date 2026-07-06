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
