from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from optimus.gateway.models import parse_gateway_response
from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.responses import handle_responses_request


@dataclass(frozen=True)
class FakeProviderResult:
    message_id: str
    output_text: str
    input_tokens: int
    output_tokens: int


class FakeUpstreamClient:
    def __init__(self, result: FakeProviderResult) -> None:
        self.calls: list[dict[str, object]] = []
        self._result = result

    def create_message(self, *, model: str, input_text: str) -> FakeProviderResult:
        self.calls.append({"model": model, "input_text": input_text})
        return self._result


def _anthropic_config() -> GatewayServiceConfig:
    return GatewayServiceConfig(
        bind_host="127.0.0.1",
        bind_port=8765,
        shared_secret="local-shared-secret",
        provider="anthropic",
        provider_api_key="sk-ant-test",
        base_url=None,
    )


def _openrouter_config() -> GatewayServiceConfig:
    return GatewayServiceConfig(
        bind_host="127.0.0.1",
        bind_port=8765,
        shared_secret="local-shared-secret",
        provider="openrouter",
        provider_api_key="or-test",
        base_url="https://openrouter.ai/api/v1",
    )


def test_handle_responses_request_rejects_missing_authorization():
    status, body = handle_responses_request(
        authorization_header=None,
        request_body={"model": "claude-haiku", "input": "hello"},
        config=_anthropic_config(),
        upstream_client=FakeUpstreamClient(FakeProviderResult("msg-1", "hi", 1, 1)),
    )

    assert status == 401
    assert "error" in body


def test_handle_responses_request_rejects_wrong_shared_secret():
    status, body = handle_responses_request(
        authorization_header="Bearer wrong-secret",
        request_body={"model": "claude-haiku", "input": "hello"},
        config=_anthropic_config(),
        upstream_client=FakeUpstreamClient(FakeProviderResult("msg-1", "hi", 1, 1)),
    )

    assert status == 401
    assert "error" in body


def test_handle_responses_request_returns_parseable_gateway_payload_for_anthropic():
    client = FakeUpstreamClient(
        FakeProviderResult(
            message_id="msg-provider-1",
            output_text="WRITE calculator.py\ndef add(a, b):\n    return a + b\n",
            input_tokens=42,
            output_tokens=18,
        )
    )
    status, body = handle_responses_request(
        authorization_header="Bearer local-shared-secret",
        request_body={
            "model": "claude-haiku",
            "input": "Create calculator.py",
            "metadata": {"purpose": "unit-test"},
        },
        config=_anthropic_config(),
        upstream_client=client,
    )

    assert status == 200
    parsed = parse_gateway_response(body)
    assert parsed.response_id
    assert parsed.output_text.startswith("WRITE calculator.py")
    assert parsed.gateway_usage.provider == "anthropic"
    assert parsed.gateway_usage.billing_units == 60
    assert parsed.gateway_usage.cost_usd > Decimal("0")
    assert client.calls == [
        {
            "model": "claude-haiku-4-5-20251001",
            "input_text": "Create calculator.py",
        }
    ]


def test_handle_responses_request_openrouter_alias_and_provider_field():
    client = FakeUpstreamClient(FakeProviderResult("chatcmpl-1", "ok", 10, 5))
    status, body = handle_responses_request(
        authorization_header="Bearer local-shared-secret",
        request_body={"model": "claude-haiku", "input": "hello"},
        config=_openrouter_config(),
        upstream_client=client,
    )

    assert status == 200
    parsed = parse_gateway_response(body)
    assert parsed.gateway_usage.provider == "openrouter"
    assert client.calls == [{"model": "anthropic/claude-3.5-haiku", "input_text": "hello"}]


def test_handle_responses_request_rejects_unsupported_model():
    status, body = handle_responses_request(
        authorization_header="Bearer local-shared-secret",
        request_body={"model": "unknown-model", "input": "hello"},
        config=_openrouter_config(),
        upstream_client=FakeUpstreamClient(FakeProviderResult("msg-1", "hi", 1, 1)),
    )

    assert status == 400
    assert "unsupported gateway model" in str(body)
