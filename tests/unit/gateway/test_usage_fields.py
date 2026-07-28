"""Gateway usage normalized-field parsing tests.

"Normalized" here means the gateway-supplied usage extensions beyond the core
wire envelope (gateway_request_id, provider, cache_hit, billing_units,
cost_usd):

- service
- native_unit
- model
- model_version
- price_snapshot_id

All are optional at the wire layer. Legacy tool responses may omit some of
them; the parametrized legacy test covers the two most commonly absent
(service, native_unit). Persisted accounting (``ProviderUsage``) takes
``service``/``native_unit`` from explicit caller context rather than from
these optional wire fields; ``price_snapshot_id`` remains optional
diagnostic metadata at both layers. The legacy ``optimus_credits_debited``
field has been removed from the wire envelope entirely (Plan 11.5 Task 2).
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
        model="glm-5.2",
        model_version="2026-06-01",
        price_snapshot_id="prices-2026-07-04",
        resolved_provider="OpenRouter",
        resolved_model="z-ai/glm-5.2",
        input_tokens=100,
        output_tokens=23,
        total_tokens=123,
        reasoning_tokens=10,
        cached_tokens=7,
        cache_age_seconds=30,
    )

    assert usage.service == "responses"
    assert usage.native_unit == "tokens"
    assert usage.model == "glm-5.2"
    assert usage.model_version == "2026-06-01"
    assert usage.price_snapshot_id == "prices-2026-07-04"
    assert usage.resolved_provider == "OpenRouter"
    assert usage.resolved_model == "z-ai/glm-5.2"
    assert usage.total_tokens == 123
    assert usage.cached_tokens == 7
    assert not hasattr(usage, "optimus_credits_debited")


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
                "model": "glm-5.2",
                "model_version": "2026-06-01",
                "price_snapshot_id": "prices-2026-07-04",
            },
        }
    )

    assert parsed.gateway_usage.service == "responses"
    assert parsed.gateway_usage.native_unit == "tokens"
    assert parsed.gateway_usage.model == "glm-5.2"
    assert parsed.gateway_usage.model_version == "2026-06-01"
    assert parsed.gateway_usage.price_snapshot_id == "prices-2026-07-04"


@pytest.mark.parametrize("field", ["service", "native_unit"])
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
        },
    }
    body["gateway_usage"].pop(field)

    parsed = parse_gateway_response(body)

    assert getattr(parsed.gateway_usage, field) is None


def test_gateway_usage_rejects_negative_cost_usd():
    with pytest.raises(GatewayResponseError):
        parse_gateway_response(
            {
                "id": "resp-1",
                "output_text": "done",
                "gateway_usage": {
                    "gateway_request_id": "gw-1",
                    "provider": "glm",
                    "cache_hit": False,
                    "billing_units": 1,
                    "cost_usd": "-1",
                },
            }
        )


# --- Plan 9.95 Task 1 Step 1: usage-preserving malformed response tests ---


def test_missing_output_preserves_valid_gateway_usage_on_response_error():
    """Valid usage is preserved when output_text is missing/malformed."""
    body = {
        "id": "resp-1",
        "gateway_usage": {
            "gateway_request_id": "gw-failed-1",
            "provider": "glm",
            "cache_hit": False,
            "billing_units": 10,
            "cost_usd": "0.001",
        },
    }

    with pytest.raises(GatewayResponseError) as exc_info:
        parse_gateway_response(body)

    assert exc_info.value.gateway_usage is not None
    assert exc_info.value.gateway_usage.gateway_request_id == "gw-failed-1"


def test_invalid_response_id_preserves_valid_gateway_usage_on_response_error():
    """Valid usage is preserved when the response id field is non-string."""
    body = {
        "id": 12345,
        "output_text": "done",
        "gateway_usage": {
            "gateway_request_id": "gw-failed-1",
            "provider": "glm",
            "cache_hit": False,
            "billing_units": 10,
            "cost_usd": "0.001",
        },
    }

    with pytest.raises(GatewayResponseError) as exc_info:
        parse_gateway_response(body)

    assert exc_info.value.gateway_usage is not None
    assert exc_info.value.gateway_usage.gateway_request_id == "gw-failed-1"


def test_invalid_gateway_usage_has_no_partial_usage():
    """When gateway_usage itself is invalid, no partial usage is attached."""
    body = {
        "id": "resp-1",
        "output_text": "done",
        "gateway_usage": {
            "gateway_request_id": "",
            "provider": "glm",
            "cache_hit": False,
            "billing_units": 10,
            "cost_usd": "0.001",
        },
    }

    with pytest.raises(GatewayResponseError) as exc_info:
        parse_gateway_response(body)

    assert exc_info.value.gateway_usage is None
