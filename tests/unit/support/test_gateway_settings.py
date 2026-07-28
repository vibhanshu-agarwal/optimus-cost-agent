"""Unit coverage for the shared Gateway settings test helpers."""

from optimus.config.gateway import OptimusGatewaySettings
from tests.support.gateway_settings import (
    LOOPBACK_GATEWAY_URL,
    TRUSTED_GATEWAY_ORIGIN,
    gateway_env,
    gateway_settings,
)


def test_loopback_constant_matches_production_default():
    assert LOOPBACK_GATEWAY_URL == OptimusGatewaySettings(optimus_api_key="x").gateway_url
    assert TRUSTED_GATEWAY_ORIGIN == LOOPBACK_GATEWAY_URL


def test_gateway_settings_omitting_url_uses_production_default():
    settings = gateway_settings(optimus_api_key="optimus-key")

    assert settings.gateway_url == LOOPBACK_GATEWAY_URL
    assert settings.auth_headers() == {"Authorization": "Bearer optimus-key"}


def test_gateway_settings_accepts_explicit_loopback_url():
    settings = gateway_settings(
        gateway_url="http://127.0.0.1:9876",
        optimus_api_key="opt-test",
    )

    assert settings.gateway_url == "http://127.0.0.1:9876"


def test_gateway_env_includes_loopback_contract():
    assert gateway_env() == {
        "OPTIMUS_GATEWAY_URL": LOOPBACK_GATEWAY_URL,
        "OPTIMUS_API_KEY": "opt-test",
    }
    assert gateway_env(extra={"OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0"})[
        "OPTIMUS_REDIS_URL"
    ] == "redis://127.0.0.1:6379/0"
