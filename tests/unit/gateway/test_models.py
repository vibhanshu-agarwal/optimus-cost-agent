from decimal import Decimal

import pytest
from pydantic import ValidationError

from optimus.gateway.errors import GatewayResponseError
from optimus.gateway.models import (
    GatewayResponse,
    GatewayUsage,
    build_chat_completions_payload,
    build_responses_payload,
    parse_gateway_response,
)


def test_responses_payload_uses_input_not_messages():
    payload = build_responses_payload(
        model="glm-5.2",
        input_text="Explain the change.",
        metadata={"run_id": "run-1"},
    )

    assert payload == {
        "model": "glm-5.2",
        "input": "Explain the change.",
        "metadata": {"run_id": "run-1"},
    }
    assert "messages" not in payload


def test_chat_completions_payload_uses_messages_not_input():
    messages = [{"role": "user", "content": "hello"}]

    payload = build_chat_completions_payload(model="claude-haiku", messages=messages)

    assert payload == {"model": "claude-haiku", "messages": messages}
    assert "input" not in payload


def test_gateway_usage_rejects_negative_values():
    with pytest.raises(ValidationError):
        GatewayUsage(
            gateway_request_id="gw-1",
            provider="openai",
            cache_hit=False,
            billing_units=-1,
            cost_usd=Decimal("0.01"),
        )

    with pytest.raises(ValidationError):
        GatewayUsage(
            gateway_request_id="gw-1",
            provider="openai",
            cache_hit=False,
            billing_units=1,
            cost_usd=Decimal("-0.01"),
        )


def test_parse_gateway_response_extracts_output_and_usage():
    parsed = parse_gateway_response(
        {
            "id": "resp-1",
            "output_text": "done",
            "gateway_usage": {
                "gateway_request_id": "gw-1",
                "provider": "glm",
                "provider_request_id": "provider-1",
                "cache_hit": False,
                "billing_units": 42,
                "cost_usd": "0.0042",
            },
        }
    )

    assert parsed == GatewayResponse(
        response_id="resp-1",
        output_text="done",
        gateway_usage=GatewayUsage(
            gateway_request_id="gw-1",
            provider="glm",
            provider_request_id="provider-1",
            cache_hit=False,
            billing_units=42,
            cost_usd=Decimal("0.0042"),
        ),
        raw={
            "id": "resp-1",
            "output_text": "done",
            "gateway_usage": {
                "gateway_request_id": "gw-1",
                "provider": "glm",
                "provider_request_id": "provider-1",
                "cache_hit": False,
                "billing_units": 42,
                "cost_usd": "0.0042",
            },
        },
    )


def test_parse_gateway_response_extracts_responses_output_array_when_output_text_absent():
    parsed = parse_gateway_response(
        {
            "id": "resp-1",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "hello "},
                        {"type": "text", "text": "world"},
                    ],
                }
            ],
            "gateway_usage": {
                "gateway_request_id": "gw-1",
                "provider": "glm",
                "cache_hit": False,
                "billing_units": 2,
                "cost_usd": "0.0002",
            },
        }
    )

    assert parsed.output_text == "hello world"
    assert parsed.gateway_usage.gateway_request_id == "gw-1"


@pytest.mark.parametrize(
    "body, message",
    [
        ({"id": "resp-1", "output_text": "done"}, "gateway_usage missing"),
        ({"id": "resp-1", "output_text": "done", "gateway_usage": {}}, "gateway_request_id"),
        (
            {
                "id": "resp-1",
                "output_text": "done",
                "gateway_usage": {
                    "gateway_request_id": "",
                    "provider": "glm",
                    "cache_hit": False,
                    "billing_units": 1,
                    "cost_usd": "0.01",
                },
            },
            "gateway_request_id",
        ),
        (
            {
                "id": "resp-1",
                "output_text": "done",
                "gateway_usage": {
                    "gateway_request_id": "gw-1",
                    "provider": "glm",
                    "cache_hit": False,
                    "billing_units": 1,
                    "cost_usd": None,
                },
            },
            "cost_usd",
        ),
    ],
)
def test_parse_gateway_response_fails_closed_for_malformed_usage(body, message):
    with pytest.raises(GatewayResponseError, match=message):
        parse_gateway_response(body)
