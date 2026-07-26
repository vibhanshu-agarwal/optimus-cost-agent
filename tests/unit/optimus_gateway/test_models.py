import pytest

from optimus.agent.defaults import DEFAULT_AGENT_MODEL
from optimus_gateway.model_mapping import is_plausible_passthrough, resolve_model_id
from optimus_gateway.models import (
    GatewayServiceConfig,
    ModelRequestValidationError,
    authorize_bearer,
    validate_chat_completions_envelope,
    validate_responses_envelope,
)


def test_resolve_model_id_anthropic_alias():
    assert resolve_model_id(provider="anthropic", model="claude-haiku") == "claude-haiku-4-5-20251001"


def test_resolve_model_id_openrouter_alias():
    assert resolve_model_id(provider="openrouter", model="claude-haiku") == "anthropic/claude-haiku-4.5"


def test_resolve_model_id_openai_alias():
    assert resolve_model_id(provider="openai", model="claude-haiku") == "gpt-4o-mini"


def test_resolve_model_id_accepts_shared_agent_default_for_every_provider():
    assert resolve_model_id(provider="anthropic", model=DEFAULT_AGENT_MODEL) == "claude-haiku-4-5-20251001"
    assert resolve_model_id(provider="openrouter", model=DEFAULT_AGENT_MODEL) == "anthropic/claude-haiku-4.5"
    assert resolve_model_id(provider="openai", model=DEFAULT_AGENT_MODEL) == "gpt-4o-mini"


def test_resolve_model_id_openrouter_passthrough():
    assert resolve_model_id(provider="openrouter", model="openai/gpt-4o-mini") == "openai/gpt-4o-mini"


def test_resolve_model_id_rejects_unknown_model():
    with pytest.raises(ValueError, match="unsupported gateway model"):
        resolve_model_id(provider="openrouter", model="unknown-model")


def test_is_plausible_passthrough_openai_prefix():
    assert is_plausible_passthrough("openai", "gpt-4o-mini") is True


def test_gateway_service_config_rejects_non_loopback_bind():
    with pytest.raises(ValueError, match="bind host must be loopback"):
        GatewayServiceConfig(
            bind_host="0.0.0.0",
            bind_port=8765,
            shared_secret="secret",
            provider="openrouter",
            provider_api_key="or-key",
            base_url="https://openrouter.ai/api/v1",
        )


def test_gateway_service_config_from_env_defaults_to_openrouter():
    config = GatewayServiceConfig.from_env(
        {
            "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "secret",
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "or-key",
        },
        bind_host="127.0.0.1",
        bind_port=8765,
    )
    assert config.provider == "openrouter"
    assert config.base_url == "https://openrouter.ai/api/v1"


def test_gateway_service_config_from_env_anthropic_requires_native_key():
    config = GatewayServiceConfig.from_env(
        {
            "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "secret",
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER": "anthropic",
            "ANTHROPIC_API_KEY": "sk-ant",
        },
        bind_host="127.0.0.1",
        bind_port=8765,
    )
    assert config.provider == "anthropic"
    assert config.base_url is None


def test_gateway_service_config_from_env_never_reads_bind_env_vars():
    """Plan 9.96 Task 5 Step 4: bind_host/bind_port are explicit parameters,
    never read from OPTIMUS_LOCAL_GATEWAY_BIND_HOST/PORT even if present."""
    config = GatewayServiceConfig.from_env(
        {
            "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "secret",
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "or-key",
            "OPTIMUS_LOCAL_GATEWAY_BIND_HOST": "0.0.0.0",
            "OPTIMUS_LOCAL_GATEWAY_PORT": "9999",
        },
        bind_host="127.0.0.1",
        bind_port=8765,
    )
    assert config.bind_host == "127.0.0.1"
    assert config.bind_port == 8765


def test_validate_responses_envelope_accepts_input_and_unknown_fields():
    model, input_text, metadata = validate_responses_envelope(
        {
            "model": "claude-haiku",
            "input": "hello",
            "metadata": {"run_id": "r1", "future_key": "ok"},
            "unknown_top_level": 123,
        }
    )
    assert model == "claude-haiku"
    assert input_text == "hello"
    assert metadata == {"run_id": "r1", "future_key": "ok"}


def test_validate_responses_envelope_rejects_messages_mix():
    with pytest.raises(ModelRequestValidationError, match="messages"):
        validate_responses_envelope(
            {"model": "claude-haiku", "input": "hello", "messages": [{"role": "user", "content": "x"}]}
        )


def test_validate_responses_envelope_rejects_missing_model_and_input():
    with pytest.raises(ModelRequestValidationError, match="model"):
        validate_responses_envelope({"input": "hello"})
    with pytest.raises(ModelRequestValidationError, match="input"):
        validate_responses_envelope({"model": "claude-haiku"})


def test_validate_responses_envelope_rejects_non_object_metadata():
    with pytest.raises(ModelRequestValidationError, match="metadata"):
        validate_responses_envelope({"model": "claude-haiku", "input": "hello", "metadata": "bad"})


def test_validate_chat_completions_envelope_accepts_messages_and_unknown_fields():
    model, messages, metadata = validate_chat_completions_envelope(
        {
            "model": "claude-haiku",
            "messages": [{"role": "user", "content": "hello"}],
            "metadata": {"session_id": "s1", "extra": True},
            "temperature": 0.2,
        }
    )
    assert model == "claude-haiku"
    assert messages == [{"role": "user", "content": "hello"}]
    assert metadata == {"session_id": "s1", "extra": True}


def test_validate_chat_completions_envelope_rejects_input_mix():
    with pytest.raises(ModelRequestValidationError, match="input"):
        validate_chat_completions_envelope(
            {
                "model": "claude-haiku",
                "messages": [{"role": "user", "content": "hello"}],
                "input": "nope",
            }
        )


def test_validate_chat_completions_envelope_rejects_missing_or_empty_messages():
    with pytest.raises(ModelRequestValidationError, match="messages"):
        validate_chat_completions_envelope({"model": "claude-haiku"})
    with pytest.raises(ModelRequestValidationError, match="messages"):
        validate_chat_completions_envelope({"model": "claude-haiku", "messages": []})


@pytest.mark.parametrize(
    ("header", "secret", "expected"),
    (
        (None, "secret", False),
        ("", "secret", False),
        ("Basic secret", "secret", False),
        ("Bearer wrong", "secret", False),
        ("Bearer secret", "secret", True),
        ("Bearer  secret  ", "secret", True),
    ),
)
def test_authorize_bearer_missing_and_wrong_token(header: str | None, secret: str, expected: bool):
    assert authorize_bearer(authorization_header=header, shared_secret=secret) is expected


def test_authorize_bearer_uses_constant_time_compare(monkeypatch):
    calls: list[tuple[str, str]] = []

    def tracking_compare(left: str, right: str) -> bool:
        calls.append((left, right))
        return left == right

    monkeypatch.setattr("optimus_gateway.models.secrets.compare_digest", tracking_compare)
    assert authorize_bearer(authorization_header="Bearer token-a", shared_secret="token-b") is False
    assert calls == [("token-a", "token-b")]
