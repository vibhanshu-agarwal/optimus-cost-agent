from decimal import Decimal

import pytest

from optimus_gateway import upstream_client
from optimus_gateway.upstream_client import parse_openai_chat_completion


def _openrouter_body() -> dict[str, object]:
    return {
        "id": "gen-1",
        "model": "anthropic/claude-haiku-4.5",
        "choices": [{"message": {"role": "assistant", "content": "hello"}}],
        "usage": {
            "prompt_tokens": 42,
            "completion_tokens": 18,
            "total_tokens": 60,
            "cost": "0.00042",
            "prompt_tokens_details": {"cached_tokens": 12},
        },
        "openrouter_metadata": {"provider": "Anthropic", "model": "claude-haiku-4.5"},
    }


def _openrouter_headers() -> dict[str, str]:
    return {
        "X-OpenRouter-Cache-Status": "HIT",
        "X-OpenRouter-Cache-Age": "31",
    }


def test_parse_openai_chat_completion_preserves_openrouter_accounting_and_metadata():
    result = parse_openai_chat_completion(
        _openrouter_body(),
        _openrouter_headers(),
        requested_model="claude-haiku",
    )

    assert result.message_id == "gen-1"
    assert result.output_text == "hello"
    assert result.input_tokens == 42
    assert result.output_tokens == 18
    assert result.total_tokens == 60
    assert result.billing_units == 60
    assert result.cost_usd == Decimal("0.00042")
    assert result.provider == "openrouter"
    assert result.resolved_provider == "Anthropic"
    assert result.requested_model == "claude-haiku"
    assert result.resolved_model == "anthropic/claude-haiku-4.5"
    assert result.model_version is None
    assert result.cached_tokens == 12
    assert result.cache_hit is True
    assert result.cache_age_seconds == 31


@pytest.mark.parametrize(
    ("cost", "error"),
    [
        (None, "cost"),
        (-1, "cost"),
        ("NaN", "cost"),
        ("Infinity", "cost"),
        (True, "cost"),
        ("invalid", "cost"),
    ],
)
def test_parse_openai_chat_completion_rejects_invalid_provider_cost(
    cost: object, error: str
) -> None:
    body = _openrouter_body()
    usage = body["usage"]
    assert isinstance(usage, dict)
    usage["cost"] = cost

    with pytest.raises(RuntimeError, match=error):
        parse_openai_chat_completion(body, _openrouter_headers(), requested_model="claude-haiku")


def test_parse_openai_chat_completion_rejects_absent_provider_cost() -> None:
    body = _openrouter_body()
    usage = body["usage"]
    assert isinstance(usage, dict)
    del usage["cost"]

    with pytest.raises(RuntimeError, match="cost"):
        parse_openai_chat_completion(body, _openrouter_headers(), requested_model="claude-haiku")


@pytest.mark.parametrize(
    ("path", "value", "error"),
    [
        (("usage",), None, "usage"),
        (("usage", "total_tokens"), None, "billing"),
        (("usage", "prompt_tokens"), True, "token"),
        (("usage", "completion_tokens"), "18", "token"),
        (("id",), "", "id"),
        (("choices",), [], "choices"),
        (("choices", 0, "message"), None, "message"),
        (("choices", 0, "message", "content"), None, "content"),
        (("openrouter_metadata",), {"provider": 42}, "metadata"),
    ],
)
def test_parse_openai_chat_completion_rejects_malformed_required_fields(
    path: tuple[str | int, ...], value: object, error: str
) -> None:
    body = _openrouter_body()
    target: object = body
    for segment in path[:-1]:
        target = target[segment]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]

    with pytest.raises(RuntimeError, match=error):
        parse_openai_chat_completion(body, _openrouter_headers(), requested_model="claude-haiku")


def test_parse_openai_chat_completion_accepts_unknown_additive_fields() -> None:
    body = _openrouter_body()
    body["future_field"] = {"ignored": True}

    result = parse_openai_chat_completion(body, _openrouter_headers(), requested_model="claude-haiku")

    assert result.cost_usd == Decimal("0.00042")


def test_parse_openai_chat_completion_preserves_openrouter_without_resolved_provider() -> None:
    body = _openrouter_body()
    del body["openrouter_metadata"]

    result = parse_openai_chat_completion(body, _openrouter_headers(), requested_model="claude-haiku")

    assert result.provider == "openrouter"
    assert result.resolved_provider is None


def test_direct_anthropic_adapter_is_absent() -> None:
    assert not hasattr(upstream_client, "UrllibAnthropicClient")
    assert not hasattr(upstream_client, "parse_anthropic_message")
    assert not hasattr(upstream_client, "_extract_anthropic_output_text")
