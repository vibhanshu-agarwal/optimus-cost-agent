from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from optimus.gateway.models import GatewayUsage
from optimus.usage.models import ProviderUsage


def gateway_usage() -> GatewayUsage:
    return GatewayUsage(
        gateway_request_id="gw-1",
        provider="glm",
        provider_request_id="provider-1",
        cache_hit=True,
        billing_units=123,
        cost_usd=Decimal("0.0123"),
        model="glm-5.2",
        model_version="2026-06-01",
    )


def gateway_usage_with_resolved_fields() -> GatewayUsage:
    return GatewayUsage(
        gateway_request_id="gw-resolved-1",
        provider="openrouter",
        billing_units=10,
        cost_usd=Decimal("0.002"),
        resolved_provider="provider-a",
        resolved_model="model-v1",
        input_tokens=3,
        output_tokens=7,
        total_tokens=10,
    )


def test_provider_usage_copies_gateway_fields_and_adds_run_attribution():
    usage = ProviderUsage.from_gateway_usage(
        gateway_usage(),
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        service="responses",
        native_unit="tokens",
        price_snapshot_id="prices-2026-07-04",
    )

    assert usage.run_id == "run-1"
    assert usage.session_id == "session-1"
    assert usage.request_id == "req-1"
    assert usage.gateway_request_id == "gw-1"
    assert usage.provider == "glm"
    assert usage.cache_hit is True
    assert usage.billing_units == 123
    assert usage.cost_usd == Decimal("0.0123")
    assert usage.service == "responses"
    assert usage.native_unit == "tokens"
    assert usage.model == "glm-5.2"
    assert usage.model_version == "2026-06-01"
    assert usage.price_snapshot_id == "prices-2026-07-04"


def test_provider_usage_uses_caller_context_when_gateway_fields_are_absent():
    usage = ProviderUsage.from_gateway_usage(
        GatewayUsage(
            gateway_request_id="gw-1", provider="openrouter", billing_units=10,
            cost_usd=Decimal("0.002"),
        ),
        run_id="run-1", session_id="session-1", request_id="req-1",
        occurred_at=datetime(2026, 7, 28, tzinfo=UTC),
        service="agent.model", native_unit="tokens",
    )
    assert usage.service == "agent.model"
    assert usage.native_unit == "tokens"
    assert usage.price_snapshot_id is None


def test_provider_usage_copies_resolved_provider_model_and_token_detail():
    usage = ProviderUsage.from_gateway_usage(
        gateway_usage_with_resolved_fields(),
        run_id="run-1", session_id=None, request_id="req-1",
        occurred_at=datetime(2026, 7, 28, tzinfo=UTC),
        service="agent.model", native_unit="tokens",
    )
    assert usage.resolved_provider == "provider-a"
    assert usage.resolved_model == "model-v1"
    assert usage.input_tokens == 3
    assert usage.output_tokens == 7
    assert usage.total_tokens == 10


def test_provider_usage_rejects_negative_values():
    with pytest.raises(ValidationError):
        ProviderUsage(
            run_id="run-1",
            session_id=None,
            request_id="req-1",
            occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
            gateway_request_id="gw-1",
            provider="glm",
            cache_hit=False,
            billing_units=-1,
            cost_usd=Decimal("0"),
            service="responses",
            native_unit="tokens",
        )


def test_provider_usage_requires_service_and_native_unit():
    with pytest.raises(ValidationError):
        ProviderUsage(
            run_id="run-1",
            session_id=None,
            request_id="req-1",
            occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
            gateway_request_id="gw-1",
            provider="glm",
            cache_hit=False,
            billing_units=1,
            cost_usd=Decimal("0.001"),
            service="",
            native_unit="",
        )
