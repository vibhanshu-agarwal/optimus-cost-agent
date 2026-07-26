from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from optimus.gateway.models import parse_gateway_response, parse_gateway_usage
from optimus_gateway import responses
from optimus_gateway.chat_completions import handle_chat_completions_request
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


def _openai_config() -> GatewayServiceConfig:
    return GatewayServiceConfig(
        bind_host="127.0.0.1",
        bind_port=8765,
        shared_secret="local-shared-secret",
        provider="openai",
        provider_api_key="oai-test",
        base_url="https://api.openai.com/v1",
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
    assert client.calls == [{"model": "anthropic/claude-haiku-4.5", "input_text": "hello"}]


def test_handle_responses_request_rejects_unsupported_model():
    status, body = handle_responses_request(
        authorization_header="Bearer local-shared-secret",
        request_body={"model": "unknown-model", "input": "hello"},
        config=_openrouter_config(),
        upstream_client=FakeUpstreamClient(FakeProviderResult("msg-1", "hi", 1, 1)),
    )

    assert status == 400
    assert "unsupported gateway model" in str(body)


def test_handle_responses_request_sanitizes_upstream_error_and_fails_closed(monkeypatch):
    class FailingUpstreamClient:
        def create_message(self, *, model: str, input_text: str) -> FakeProviderResult:
            raise RuntimeError("OPTIMUS_API_KEY=top-secret-canary redis://user:top-secret-canary@host/0")

    status, body = handle_responses_request(
        authorization_header="Bearer local-shared-secret",
        request_body={"model": "claude-haiku", "input": "hello"},
        config=_anthropic_config(),
        upstream_client=FailingUpstreamClient(),
    )

    assert status == 502
    assert body["error"]
    assert "top-secret-canary" not in str(body)

    monkeypatch.setattr(
        responses,
        "sanitize_for_persistence",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("sanitizer failure")),
    )
    failed_status, failed_body = handle_responses_request(
        authorization_header="Bearer local-shared-secret",
        request_body={"model": "claude-haiku", "input": "hello"},
        config=_anthropic_config(),
        upstream_client=FailingUpstreamClient(),
    )

    assert failed_status == 502
    assert failed_body == {"error": "internal gateway error"}


def test_handle_responses_request_rejects_unpriced_passthrough_before_upstream_call():
    client = FakeUpstreamClient(FakeProviderResult("chatcmpl-1", "ok", 10, 5))
    status, body = handle_responses_request(
        authorization_header="Bearer local-shared-secret",
        request_body={"model": "gpt-4o", "input": "hello"},
        config=_openai_config(),
        upstream_client=client,
    )

    assert status == 500
    assert "no pricing snapshot" in str(body)
    assert client.calls == []


def test_handle_responses_request_rejects_messages_field():
    client = FakeUpstreamClient(FakeProviderResult("msg-1", "hi", 1, 1))
    status, body = handle_responses_request(
        authorization_header="Bearer local-shared-secret",
        request_body={
            "model": "claude-haiku",
            "input": "hello",
            "messages": [{"role": "user", "content": "hello"}],
        },
        config=_anthropic_config(),
        upstream_client=client,
    )
    assert status == 400
    assert "messages" in str(body)
    assert client.calls == []


def test_handle_responses_request_tolerates_unknown_top_level_and_metadata_keys():
    client = FakeUpstreamClient(FakeProviderResult("msg-1", "hi", 1, 1))
    status, body = handle_responses_request(
        authorization_header="Bearer local-shared-secret",
        request_body={
            "model": "claude-haiku",
            "input": "hello",
            "metadata": {"run_id": "r1", "org_id": "future"},
            "stream": False,
        },
        config=_anthropic_config(),
        upstream_client=client,
    )
    assert status == 200
    assert body["output_text"] == "hi"
    assert client.calls


def test_handle_chat_completions_request_returns_openai_compatible_payload():
    client = FakeUpstreamClient(FakeProviderResult("msg-chat-1", "assistant-hi", 4, 2))
    status, body = handle_chat_completions_request(
        authorization_header="Bearer local-shared-secret",
        request_body={
            "model": "claude-haiku",
            "messages": [{"role": "user", "content": "hello"}],
            "metadata": {"session_id": "s1", "extra": "ok"},
            "temperature": 0.1,
        },
        config=_openrouter_config(),
        upstream_client=client,
    )

    assert status == 200
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"] == {"role": "assistant", "content": "assistant-hi"}
    usage = parse_gateway_usage(body["gateway_usage"])
    assert usage.provider == "openrouter"
    assert usage.billing_units == 6
    assert usage.cost_usd > Decimal("0")
    assert client.calls == [{"model": "anthropic/claude-haiku-4.5", "input_text": "hello"}]


def test_handle_chat_completions_request_rejects_input_field():
    client = FakeUpstreamClient(FakeProviderResult("msg-1", "hi", 1, 1))
    status, body = handle_chat_completions_request(
        authorization_header="Bearer local-shared-secret",
        request_body={
            "model": "claude-haiku",
            "messages": [{"role": "user", "content": "hello"}],
            "input": "nope",
        },
        config=_openrouter_config(),
        upstream_client=client,
    )
    assert status == 400
    assert "input" in str(body)
    assert client.calls == []


def test_handle_chat_completions_request_uses_shared_bearer_auth():
    status, body = handle_chat_completions_request(
        authorization_header="Bearer wrong",
        request_body={"model": "claude-haiku", "messages": [{"role": "user", "content": "hello"}]},
        config=_openrouter_config(),
        upstream_client=FakeUpstreamClient(FakeProviderResult("msg-1", "hi", 1, 1)),
    )
    assert status == 401
    assert "error" in body


def test_successful_model_responses_carry_required_usage_contract_fields():
    responses_client = FakeUpstreamClient(FakeProviderResult("msg-1", "hi", 3, 2))
    status, body = handle_responses_request(
        authorization_header="Bearer local-shared-secret",
        request_body={"model": "claude-haiku", "input": "hello"},
        config=_openrouter_config(),
        upstream_client=responses_client,
    )
    assert status == 200
    usage = body["gateway_usage"]
    assert usage["gateway_request_id"]
    assert usage["provider"] == "openrouter"
    assert usage["cache_hit"] is False
    assert usage["billing_units"] == 5
    assert usage["cost_usd"] is not None
    assert Decimal(usage["cost_usd"]) >= Decimal("0")

    chat_client = FakeUpstreamClient(FakeProviderResult("msg-2", "hi", 4, 1))
    status, body = handle_chat_completions_request(
        authorization_header="Bearer local-shared-secret",
        request_body={"model": "claude-haiku", "messages": [{"role": "user", "content": "hello"}]},
        config=_openrouter_config(),
        upstream_client=chat_client,
    )
    assert status == 200
    usage = body["gateway_usage"]
    assert usage["gateway_request_id"]
    assert usage["provider"] == "openrouter"
    assert usage["billing_units"] == 5
    assert usage["cost_usd"] is not None


def test_run_model_completion_fails_closed_when_usage_envelope_is_incomplete(monkeypatch):
    client = FakeUpstreamClient(FakeProviderResult("msg-1", "hi", 1, 1))

    def _broken_format(_cost: Decimal) -> None:
        return None  # type: ignore[return-value]

    monkeypatch.setattr(responses, "format_cost_usd", _broken_format)
    status, body = handle_responses_request(
        authorization_header="Bearer local-shared-secret",
        request_body={"model": "claude-haiku", "input": "hello"},
        config=_openrouter_config(),
        upstream_client=client,
    )
    assert status == 500
    assert "error" in body
    assert "gateway_usage" not in body
    assert client.calls  # upstream already ran; fail closed before emitting envelope
