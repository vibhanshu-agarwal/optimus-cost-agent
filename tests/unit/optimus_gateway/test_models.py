import pytest

from optimus_gateway.models import GatewayServiceConfig, map_agent_model_id


def test_map_agent_model_id_resolves_claude_haiku():
    assert map_agent_model_id("claude-haiku") == "claude-haiku-4-5-20251001"


def test_map_agent_model_id_rejects_unknown_model():
    with pytest.raises(ValueError, match="unsupported gateway model"):
        map_agent_model_id("unknown-model")


def test_gateway_service_config_rejects_non_loopback_bind():
    with pytest.raises(ValueError, match="bind host must be loopback"):
        GatewayServiceConfig(
            bind_host="0.0.0.0",
            bind_port=8765,
            shared_secret="secret",
            anthropic_api_key="sk-ant",
        )
