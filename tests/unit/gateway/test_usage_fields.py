"""Gateway usage normalized-field parsing tests.

"Normalized" here means the six gateway-supplied usage extensions beyond the
core wire envelope (gateway_request_id, provider, cache_hit, billing_units,
cost_usd):

- service
- native_unit
- optimus_credits_debited
- model
- model_version
- price_snapshot_id

For GatewayUsage parsing, all six are optional. Legacy tool responses may omit
some of them; the parametrized legacy test covers the three most commonly
absent (service, native_unit, optimus_credits_debited).

For persisted accounting (ProviderUsage, Plan 7), four become required:
service, native_unit, optimus_credits_debited, and price_snapshot_id.
model and model_version stay optional at the gateway layer—they are copied
through when present but are not part of the "missing normalized fields" check
for persistence.
"""
from decimal import Decimal

import pytest

from optimus.gateway.errors import GatewayResponseError
from optimus.gateway.models import GatewayUsage, parse_gateway_response


def test_gateway_usage_accepts_normalized_cost_fields():
    usage = GatewayUsage(
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

    assert usage.service == "responses"
    assert usage.native_unit == "tokens"
    assert usage.optimus_credits_debited == Decimal("1.23")
    assert usage.model == "glm-5.2"
    assert usage.model_version == "2026-06-01"
    assert usage.price_snapshot_id == "prices-2026-07-04"


def test_parse_gateway_response_preserves_normalized_usage_fields():
    parsed = parse_gateway_response(
        {
            "id": "resp-1",
            "output_text": "done",
            "gateway_usage": {
                "gateway_request_id": "gw-1",
                "provider": "glm",
                "provider_request_id": "provider-1",
                "cache_hit": True,
                "billing_units": 123,
                "cost_usd": "0.0123",
                "service": "responses",
                "native_unit": "tokens",
                "optimus_credits_debited": "1.23",
                "model": "glm-5.2",
                "model_version": "2026-06-01",
                "price_snapshot_id": "prices-2026-07-04",
            },
        }
    )

    assert parsed.gateway_usage.service == "responses"
    assert parsed.gateway_usage.native_unit == "tokens"
    assert parsed.gateway_usage.optimus_credits_debited == Decimal("1.23")
    assert parsed.gateway_usage.model == "glm-5.2"
    assert parsed.gateway_usage.model_version == "2026-06-01"
    assert parsed.gateway_usage.price_snapshot_id == "prices-2026-07-04"


@pytest.mark.parametrize("field", ["service", "native_unit", "optimus_credits_debited"])
def test_gateway_usage_normalized_fields_may_be_absent_for_legacy_tool_responses(field):
    body = {
        "id": "resp-1",
        "output_text": "done",
        "gateway_usage": {
            "gateway_request_id": "gw-1",
            "provider": "tavily",
            "cache_hit": False,
            "billing_units": 2,
            "cost_usd": "0.002",
            "service": "web.search",
            "native_unit": "tavily_credits",
            "optimus_credits_debited": "0.2",
        },
    }
    body["gateway_usage"].pop(field)

    parsed = parse_gateway_response(body)

    assert getattr(parsed.gateway_usage, field) is None


def test_gateway_usage_rejects_negative_optimus_credits():
    with pytest.raises(GatewayResponseError, match="optimus_credits_debited"):
        parse_gateway_response(
            {
                "id": "resp-1",
                "output_text": "done",
                "gateway_usage": {
                    "gateway_request_id": "gw-1",
                    "provider": "glm",
                    "cache_hit": False,
                    "billing_units": 1,
                    "cost_usd": "0.001",
                    "optimus_credits_debited": "-1",
                },
            }
        )
