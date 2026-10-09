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
        # The documented router-metadata shape (openrouter.ai/docs/guides/features/router-metadata,
        # captured 2026-10-09 in stage-a-haiku-inspection): the provider is the selected endpoint's.
        "openrouter_metadata": {
            "requested": "anthropic/claude-haiku-4.5",
            "strategy": "direct",
            "attempt": 1,
            "endpoints": {"total": 1, "available": [{"provider": "Anthropic", "model": "anthropic/claude-haiku-4.5", "selected": True}]},
        },
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
    assert result.router_attempt == 1
    assert result.router_pipeline == ()


def test_the_resolved_provider_is_the_selected_endpoint_among_several() -> None:
    body = _openrouter_body()
    body["openrouter_metadata"]["endpoints"] = {  # type: ignore[index]
        "total": 2,
        "available": [
            {"provider": "Google", "model": "anthropic/claude-haiku-4.5", "selected": False},
            {"provider": "Anthropic", "model": "anthropic/claude-haiku-4.5", "selected": True},
        ],
    }

    result = parse_openai_chat_completion(body, _openrouter_headers(), requested_model="claude-haiku")

    assert result.resolved_provider == "Anthropic"


def test_no_selected_endpoint_leaves_the_provider_unresolved() -> None:
    body = _openrouter_body()
    body["openrouter_metadata"]["endpoints"]["available"][0]["selected"] = False  # type: ignore[index]

    result = parse_openai_chat_completion(body, _openrouter_headers(), requested_model="claude-haiku")

    assert result.resolved_provider is None


def test_router_pipeline_stages_and_fallback_attempts_are_reported() -> None:
    body = _openrouter_body()
    metadata = body["openrouter_metadata"]
    metadata["attempt"] = 2  # type: ignore[index]
    metadata["pipeline"] = [{"type": "context_compression", "name": "context-compression", "data": {}}]  # type: ignore[index]

    result = parse_openai_chat_completion(body, _openrouter_headers(), requested_model="claude-haiku")

    assert (result.router_attempt, result.router_pipeline) == (2, ("context_compression",))


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


_SECOND_SELECTED = {"provider": "Google", "model": "anthropic/claude-haiku-4.5", "selected": True}


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("openrouter_metadata",), "Anthropic"),
        (("openrouter_metadata", "endpoints", "available", 0, "provider"), 42),
        (("openrouter_metadata", "endpoints", "available"), "Anthropic"),
        (("openrouter_metadata", "endpoints", "available", 0, "selected"), "yes"),
        (("openrouter_metadata", "endpoints", "available", 1), _SECOND_SELECTED),
        (("openrouter_metadata", "attempt"), "1"),
        (("openrouter_metadata", "pipeline"), {"type": "x"}),
    ],
    ids=["not-an-object", "provider", "endpoints", "selection", "ambiguous-selection", "attempt", "pipeline"],
)
def test_malformed_router_metadata_keeps_the_billing_and_reports_the_defect(path: tuple[str | int, ...], value: object) -> None:
    """Routing evidence is not billing (Codex Haiku Stage A review M1): metadata that cannot be read
    leaves every routing field unknown and says why, never guessing a provider, while the reply's valid
    usage and cost are kept."""
    body = _openrouter_body()
    target: object = body
    for segment in path[:-1]:
        target = target[segment]  # type: ignore[index]
    if isinstance(target, list) and path[-1] == len(target):
        target.append(value)
    else:
        target[path[-1]] = value  # type: ignore[index]

    result = parse_openai_chat_completion(body, _openrouter_headers(), requested_model="claude-haiku")

    assert (result.input_tokens, result.output_tokens, result.cost_usd) == (42, 18, Decimal("0.00042"))
    assert (result.resolved_provider, result.router_attempt, result.router_pipeline) == (None, None, None)
    assert result.router_metadata_error and "router metadata" in result.router_metadata_error


def test_readable_or_absent_router_metadata_reports_no_defect() -> None:
    body = _openrouter_body()
    assert parse_openai_chat_completion(body, _openrouter_headers(), requested_model="m").router_metadata_error is None
    del body["openrouter_metadata"]
    assert parse_openai_chat_completion(body, _openrouter_headers(), requested_model="m").router_metadata_error is None


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
    assert (result.router_attempt, result.router_pipeline) == (None, None)


def test_direct_anthropic_adapter_is_absent() -> None:
    assert not hasattr(upstream_client, "UrllibAnthropicClient")
    assert not hasattr(upstream_client, "parse_anthropic_message")
    assert not hasattr(upstream_client, "_extract_anthropic_output_text")
