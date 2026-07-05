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
        service="responses",
        native_unit="tokens",
        optimus_credits_debited=Decimal("1.23"),
        model="glm-5.2",
        model_version="2026-06-01",
        price_snapshot_id="prices-2026-07-04",
    )


def test_provider_usage_copies_gateway_fields_and_adds_run_attribution():
    usage = ProviderUsage.from_gateway_usage(
        gateway_usage(),
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
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
    assert usage.optimus_credits_debited == Decimal("1.23")
    assert usage.model == "glm-5.2"
    assert usage.model_version == "2026-06-01"
    assert usage.price_snapshot_id == "prices-2026-07-04"


@pytest.mark.parametrize("field", ["service", "native_unit", "optimus_credits_debited", "price_snapshot_id"])
def test_provider_usage_requires_normalized_fields_for_persistence(field):
    incomplete = gateway_usage().model_copy(update={field: None})

    with pytest.raises(ValueError, match=field):
        ProviderUsage.from_gateway_usage(
            incomplete,
            run_id="run-1",
            session_id=None,
            request_id="req-1",
            occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        )


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
            optimus_credits_debited=Decimal("0"),
            price_snapshot_id="prices-2026-07-04",
        )
