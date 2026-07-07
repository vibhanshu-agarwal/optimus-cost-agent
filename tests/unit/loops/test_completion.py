from datetime import UTC, datetime
from decimal import Decimal

import pytest

from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import GatewayClient
from optimus.loops.completion import DeterministicCompletionEvaluator, GatewayCompletionEvaluator
from optimus.loops.ledger import InMemoryProgressLedger
from optimus.loops.models import CompletionEvaluation, IterationState


class FakeTransport:
    def __init__(self, body):
        self.body = body
        self.requests = []

    def post_json(self, request):
        self.requests.append(request)
        return self.body


def state() -> IterationState:
    return IterationState(
        run_id="run-1",
        session_id="session-1",
        goal="Migrate auth call sites",
        completion_condition="tests/unit/auth pass",
        started_at=datetime(2026, 7, 6, tzinfo=UTC),
    )


def settings() -> OptimusGatewaySettings:
    return OptimusGatewaySettings(
        gateway_url="https://gateway.optimus.ai",
        optimus_api_key="optimus-key",
        production_mode=True,
    )


def test_deterministic_completion_evaluator_is_zero_cost():
    evaluator = DeterministicCompletionEvaluator(completed=True, reason="predicate passed")

    result = evaluator.evaluate(state(), InMemoryProgressLedger())

    assert result == CompletionEvaluation(completed=True, reason="predicate passed")


def test_gateway_completion_evaluator_routes_through_gateway_and_returns_usage():
    transport = FakeTransport(
        {
            "id": "resp-1",
            "output_text": '{"completed": true, "reason": "tests pass", "confidence": "0.98"}',
            "gateway_usage": {
                "gateway_request_id": "gw-1",
                "provider": "openai",
                "billing_units": 7,
                "cost_usd": "0.002",
                "optimus_credits_debited": "0.03",
                "service": "responses",
                "native_unit": "tokens",
                "price_snapshot_id": "prices-1",
            },
        }
    )
    evaluator = GatewayCompletionEvaluator(
        client=GatewayClient(settings=settings(), transport=transport),
        model="cheap-evaluator",
    )

    result = evaluator.evaluate(state(), InMemoryProgressLedger())

    assert result.completed is True
    assert result.reason == "tests pass"
    assert result.cost_credits == Decimal("0.03")
    assert result.gateway_request_id == "gw-1"
    assert transport.requests[0].headers["Authorization"] == "Bearer optimus-key"
    assert transport.requests[0].payload["metadata"]["purpose"] == "goal_loop_completion_evaluation"


def test_gateway_completion_evaluator_rejects_string_boolean():
    transport = FakeTransport(
        {
            "id": "resp-1",
            "output_text": '{"completed": "false", "reason": "string boolean", "confidence": "0.98"}',
            "gateway_usage": {
                "gateway_request_id": "gw-1",
                "provider": "openai",
                "billing_units": 7,
                "cost_usd": "0.002",
            },
        }
    )
    evaluator = GatewayCompletionEvaluator(
        client=GatewayClient(settings=settings(), transport=transport),
        model="cheap-evaluator",
    )

    with pytest.raises(ValueError, match="completed must be a JSON boolean"):
        evaluator.evaluate(state(), InMemoryProgressLedger())


def test_gateway_completion_evaluator_rejects_invalid_confidence():
    transport = FakeTransport(
        {
            "id": "resp-1",
            "output_text": '{"completed": false, "reason": "not done", "confidence": "high"}',
            "gateway_usage": {
                "gateway_request_id": "gw-1",
                "provider": "openai",
                "billing_units": 7,
                "cost_usd": "0.002",
            },
        }
    )
    evaluator = GatewayCompletionEvaluator(
        client=GatewayClient(settings=settings(), transport=transport),
        model="cheap-evaluator",
    )

    with pytest.raises(ValueError, match="confidence must be a decimal"):
        evaluator.evaluate(state(), InMemoryProgressLedger())


def test_gateway_completion_evaluator_cannot_override_failed_deterministic_evidence():
    transport = FakeTransport(
        {
            "id": "resp-1",
            "output_text": '{"completed": true, "reason": "model says done", "confidence": "0.99"}',
            "gateway_usage": {
                "gateway_request_id": "gw-1",
                "provider": "openai",
                "billing_units": 7,
                "cost_usd": "0.002",
            },
        }
    )
    evaluator = GatewayCompletionEvaluator(
        client=GatewayClient(settings=settings(), transport=transport),
        model="cheap-evaluator",
        deterministic_predicate=lambda state, ledger: CompletionEvaluation(completed=False, reason="pytest failed"),
    )

    result = evaluator.evaluate(state(), InMemoryProgressLedger())

    assert result.completed is False
    assert result.reason == "pytest failed"
    assert transport.requests == []


def test_gateway_completion_evaluator_fails_closed_on_non_json_output():
    transport = FakeTransport(
        {
            "id": "resp-1",
            "output_text": "yes, done",
            "gateway_usage": {
                "gateway_request_id": "gw-1",
                "provider": "openai",
                "billing_units": 7,
                "cost_usd": "0.002",
            },
        }
    )
    evaluator = GatewayCompletionEvaluator(
        client=GatewayClient(settings=settings(), transport=transport),
        model="cheap-evaluator",
    )

    with pytest.raises(ValueError, match="completion evaluator returned invalid JSON"):
        evaluator.evaluate(state(), InMemoryProgressLedger())
