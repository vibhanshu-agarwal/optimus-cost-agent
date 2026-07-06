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
