from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest

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
    total_tokens: int | None
    billing_units: int
    cost_usd: Decimal
    provider: str
    resolved_provider: str | None
    requested_model: str
    resolved_model: str | None
    model_version: str | None
    cache_hit: bool
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None
    cache_age_seconds: int | None = None


class FakeUpstreamClient:
    def __init__(self, result: FakeProviderResult) -> None:
        self.calls: list[dict[str, object]] = []
        self._result = result

    def create_message(self, *, model: str, input_text: str) -> FakeProviderResult:
        self.calls.append({"model": model, "input_text": input_text})
        return self._result


def _openrouter_config() -> GatewayServiceConfig:
    return GatewayServiceConfig(
        bind_host="127.0.0.1",
        bind_port=8765,
        shared_secret="local-shared-secret",
        provider="openrouter",
        provider_api_key="or-test",
        base_url="https://openrouter.ai/api/v1",
    )


def _provider_result(**overrides: object) -> FakeProviderResult:
    fields: dict[str, object] = {
        "message_id": "gen-1",
        "output_text": "ok",
        "input_tokens": 42,
        "output_tokens": 18,
        "total_tokens": 60,
        "billing_units": 60,
        "cost_usd": Decimal("0.00042"),
        "provider": "openrouter",
        "resolved_provider": "Anthropic",
        "requested_model": "claude-haiku",
        "resolved_model": "anthropic/claude-haiku-4.5",
        "model_version": None,
        "cache_hit": True,
    }
    fields.update(overrides)
    return FakeProviderResult(**fields)  # type: ignore[arg-type]


def test_handle_responses_request_rejects_missing_authorization():
    status, body = handle_responses_request(
        authorization_header=None,
        request_body={"model": "claude-haiku", "input": "hello"},
        config=_openrouter_config(),
        upstream_client=FakeUpstreamClient(_provider_result()),
    )

    assert status == 401
    assert "error" in body


def test_handle_responses_request_rejects_wrong_shared_secret():
    status, body = handle_responses_request(
        authorization_header="Bearer wrong-secret",
        request_body={"model": "claude-haiku", "input": "hello"},
        config=_openrouter_config(),
        upstream_client=FakeUpstreamClient(_provider_result()),
    )

    assert status == 401
    assert "error" in body


def test_handle_responses_request_uses_provider_reported_accounting():
    client = FakeUpstreamClient(
        _provider_result(
            message_id="msg-provider-1",
            output_text="WRITE calculator.py\ndef add(a, b):\n    return a + b\n",
            cached_tokens=7,
            reasoning_tokens=5,
            cache_age_seconds=30,
        )
    )
    status, body = handle_responses_request(
        authorization_header="Bearer local-shared-secret",
        request_body={
            "model": "claude-haiku",
            "input": "Create calculator.py",
            "metadata": {"purpose": "unit-test"},
        },
        config=_openrouter_config(),
        upstream_client=client,
    )

    assert status == 200
    parsed = parse_gateway_response(body)
    assert parsed.response_id
    assert parsed.output_text.startswith("WRITE calculator.py")
    assert parsed.gateway_usage.provider == "openrouter"
    assert parsed.gateway_usage.resolved_provider == "Anthropic"
    assert parsed.gateway_usage.provider_request_id == "msg-provider-1"
    assert parsed.gateway_usage.model == "claude-haiku"
    assert parsed.gateway_usage.resolved_model == "anthropic/claude-haiku-4.5"
    assert parsed.gateway_usage.model_version is None
    assert parsed.gateway_usage.billing_units == 60
    assert parsed.gateway_usage.cost_usd == Decimal("0.00042")
    assert parsed.gateway_usage.cache_hit is True
    assert parsed.gateway_usage.input_tokens == 42
    assert parsed.gateway_usage.output_tokens == 18
    assert parsed.gateway_usage.total_tokens == 60
    assert parsed.gateway_usage.cached_tokens == 7
    assert parsed.gateway_usage.reasoning_tokens == 5
    assert parsed.gateway_usage.cache_age_seconds == 30
    assert client.calls == [
        {
            "model": "anthropic/claude-haiku-4.5",
            "input_text": "Create calculator.py",
        }
    ]


def test_handle_responses_request_openrouter_alias_and_provider_field():
    client = FakeUpstreamClient(_provider_result(message_id="chatcmpl-1"))
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
        upstream_client=FakeUpstreamClient(_provider_result()),
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
        config=_openrouter_config(),
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
        config=_openrouter_config(),
        upstream_client=FailingUpstreamClient(),
    )

    assert failed_status == 502
    assert failed_body == {"error": "internal gateway error"}


def test_handle_responses_request_does_not_require_local_pricing_before_upstream_call():
    client = FakeUpstreamClient(_provider_result())
    status, body = handle_responses_request(
        authorization_header="Bearer local-shared-secret",
        request_body={"model": "claude-haiku", "input": "hello"},
        config=_openrouter_config(),
        upstream_client=client,
    )

    assert status == 200
    assert body["gateway_usage"]["cost_usd"] == "0.00042"
    assert client.calls == [{"model": "anthropic/claude-haiku-4.5", "input_text": "hello"}]


def test_handle_responses_request_rejects_messages_field():
    client = FakeUpstreamClient(_provider_result())
    status, body = handle_responses_request(
        authorization_header="Bearer local-shared-secret",
        request_body={
            "model": "claude-haiku",
            "input": "hello",
            "messages": [{"role": "user", "content": "hello"}],
        },
        config=_openrouter_config(),
        upstream_client=client,
    )
    assert status == 400
    assert "messages" in str(body)
    assert client.calls == []


def test_handle_responses_request_sanitizes_validation_errors(monkeypatch):
    """ModelRequestValidationError must go through sanitize_error_message, not bare str(exc)."""
    monkeypatch.setattr(
        responses,
        "sanitize_for_persistence",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("sanitizer failure")),
    )
    client = FakeUpstreamClient(_provider_result())
    status, body = handle_responses_request(
        authorization_header="Bearer local-shared-secret",
        request_body={
            "model": "claude-haiku",
            "input": "hello",
            "messages": [{"role": "user", "content": "hello"}],
        },
        config=_openrouter_config(),
        upstream_client=client,
    )
    assert status == 400
    assert body == {"error": "internal gateway error"}
    assert client.calls == []


def test_handle_responses_request_tolerates_unknown_top_level_and_metadata_keys():
    client = FakeUpstreamClient(_provider_result(output_text="hi"))
    status, body = handle_responses_request(
        authorization_header="Bearer local-shared-secret",
        request_body={
            "model": "claude-haiku",
            "input": "hello",
            "metadata": {"run_id": "r1", "org_id": "future"},
            "stream": False,
        },
        config=_openrouter_config(),
        upstream_client=client,
    )
    assert status == 200
    assert body["output_text"] == "hi"
    assert client.calls


def test_handle_chat_completions_request_returns_openai_compatible_payload():
    client = FakeUpstreamClient(
        _provider_result(
            message_id="msg-chat-1",
            output_text="assistant-hi",
            input_tokens=4,
            output_tokens=2,
            total_tokens=6,
            billing_units=6,
        )
    )
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
    client = FakeUpstreamClient(_provider_result())
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


def test_handle_chat_completions_request_sanitizes_validation_errors(monkeypatch):
    """ModelRequestValidationError must go through sanitize_error_message, not bare str(exc)."""
    monkeypatch.setattr(
        responses,
        "sanitize_for_persistence",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("sanitizer failure")),
    )
    client = FakeUpstreamClient(_provider_result())
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
    assert body == {"error": "internal gateway error"}
    assert client.calls == []


def test_handle_chat_completions_request_uses_shared_bearer_auth():
    status, body = handle_chat_completions_request(
        authorization_header="Bearer wrong",
        request_body={"model": "claude-haiku", "messages": [{"role": "user", "content": "hello"}]},
        config=_openrouter_config(),
        upstream_client=FakeUpstreamClient(_provider_result()),
    )
    assert status == 401
    assert "error" in body


def test_successful_model_responses_carry_required_usage_contract_fields():
    responses_client = FakeUpstreamClient(
        _provider_result(message_id="msg-1", output_text="hi", input_tokens=3, output_tokens=2, billing_units=5)
    )
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
    assert usage["cache_hit"] is True
    assert usage["billing_units"] == 5
    assert usage["cost_usd"] is not None
    assert Decimal(usage["cost_usd"]) >= Decimal("0")

    chat_client = FakeUpstreamClient(
        _provider_result(message_id="msg-2", output_text="hi", input_tokens=4, output_tokens=1, billing_units=5)
    )
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


def test_run_model_completion_fails_closed_for_malformed_provider_accounting():
    client = FakeUpstreamClient(_provider_result(cost_usd=Decimal("NaN")))
    status, body = handle_responses_request(
        authorization_header="Bearer local-shared-secret",
        request_body={"model": "claude-haiku", "input": "hello"},
        config=_openrouter_config(),
        upstream_client=client,
    )
    assert status == 502
    assert "error" in body
    assert "gateway_usage" not in body
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    "overrides",
    (
        {"cost_usd": None},
        {"cost_usd": "not-a-decimal"},
        {"cost_usd": Decimal("Infinity")},
        {"cost_usd": Decimal("-Infinity")},
        {"cost_usd": Decimal("-0.00001")},
        {"billing_units": None},
        {"billing_units": True},
        {"billing_units": -1},
    ),
)
def test_malformed_provider_accounting_is_a_sanitized_permanent_failure(overrides: dict[str, object]):
    client = FakeUpstreamClient(_provider_result(**overrides))

    status, body = handle_responses_request(
        authorization_header="Bearer local-shared-secret",
        request_body={"model": "claude-haiku", "input": "hello"},
        config=_openrouter_config(),
        upstream_client=client,
    )

    assert status == 502
    assert body["error"]
    assert "gateway_usage" not in body
    assert len(client.calls) == 1


def test_core_does_not_reject_budget_org_or_plan_mode_metadata():
    """CORE authenticates and preserves metadata; it does not enforce TOOLS/budget policy."""
    client = FakeUpstreamClient(_provider_result(message_id="msg-1", output_text="hi", input_tokens=2, output_tokens=1, billing_units=3))
    status, body = handle_responses_request(
        authorization_header="Bearer local-shared-secret",
        request_body={
            "model": "claude-haiku",
            "input": "hello",
            "metadata": {
                "run_id": "run-1",
                "session_id": "session-1",
                "execution_mode": "plan",
                "org_id": "org-future",
                "project_id": "proj-future",
                "budget_usd": "0.01",
                "model_permission": "denied",
            },
        },
        config=_openrouter_config(),
        upstream_client=client,
    )
    assert status == 200
    assert body["output_text"] == "hi"
    assert client.calls
    assert "or-test" not in str(body)


def test_mixed_request_shape_does_not_call_upstream():
    client = FakeUpstreamClient(_provider_result())
    mixed_status, _ = handle_responses_request(
        authorization_header="Bearer local-shared-secret",
        request_body={
            "model": "claude-haiku",
            "input": "hello",
            "messages": [{"role": "user", "content": "hello"}],
        },
        config=_openrouter_config(),
        upstream_client=client,
    )
    assert mixed_status == 400
    assert client.calls == []


def test_error_bodies_never_echo_provider_api_key():
    config = _openrouter_config()
    assert config.provider_api_key == "or-test"
    status, body = handle_responses_request(
        authorization_header="Bearer wrong",
        request_body={"model": "claude-haiku", "input": "hello"},
        config=config,
        upstream_client=FakeUpstreamClient(_provider_result()),
    )
    assert status == 401
    assert "or-test" not in str(body)
    assert "provider_api_key" not in str(body)