"""Shared loopback Gateway settings helpers for tests.

Production ``OptimusGatewaySettings`` accepts only http(s) loopback gateway URLs.
Tests must not hardcode hosted hosts or retired fields; construct settings through
this module so the canonical loopback value lives in one place.
"""

from __future__ import annotations

from collections.abc import Mapping

from optimus.config.gateway import OptimusGatewaySettings

# Matches OptimusGatewaySettings production default (strict loopback).
LOOPBACK_GATEWAY_URL = "http://127.0.0.1:8765"

# Historical alias used by evidence/telemetry fixtures.
TRUSTED_GATEWAY_ORIGIN = LOOPBACK_GATEWAY_URL


def gateway_settings(
    *,
    optimus_api_key: str = "opt-test",
    gateway_url: str | None = None,
) -> OptimusGatewaySettings:
    """Build valid ``OptimusGatewaySettings`` for tests.

    Prefer omitting ``gateway_url`` so the production default applies. Pass an
    explicit loopback URL only when the test must assert a specific origin.
    """
    if gateway_url is None:
        return OptimusGatewaySettings(optimus_api_key=optimus_api_key)
    return OptimusGatewaySettings(gateway_url=gateway_url, optimus_api_key=optimus_api_key)


def gateway_env(
    *,
    optimus_api_key: str = "opt-test",
    gateway_url: str = LOOPBACK_GATEWAY_URL,
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Minimal env dict with loopback ``OPTIMUS_GATEWAY_URL`` and ``OPTIMUS_API_KEY``."""
    env = {
        "OPTIMUS_GATEWAY_URL": gateway_url,
        "OPTIMUS_API_KEY": optimus_api_key,
    }
    if extra:
        env.update(dict(extra))
    return env
