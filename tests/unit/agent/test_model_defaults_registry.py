"""Plan 12.2 Task 5: the agent model default and the host's route-binding wire.

Haiku stays today's default while registry enforcement is inactive (operator decision 2026-10-02).
Under an enforced registry the default is its cheapest eligible medium model, configured models must
be exact eligible IDs, and ``auto`` is refused because no accepted resolver is installed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from optimus.acp.local_infra import apply_local_defaults
from optimus.agent.defaults import (
    DEFAULT_AGENT_MODEL,
    AgentModelError,
    default_agent_model,
    resolve_agent_model,
    resolve_model_for_registry,
)
from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import GatewayClient, GatewayRequest
from optimus_model_policy.binding import RouteBinding
from tests.unit.optimus_gateway.model_policy_support import VERIFIED_POLICY, verified_snapshot


def test_inactive_defaults_are_unchanged(tmp_path: Path) -> None:
    assert resolve_agent_model({}) == DEFAULT_AGENT_MODEL == "claude-haiku"
    assert resolve_agent_model({"OPTIMUS_AGENT_MODEL": "vendor/any"}) == "vendor/any"
    assert resolve_agent_model({}, cli_model=" auto ") == "auto", "inactive: today's rules, Gateway decides"
    assert apply_local_defaults({}, config_root=tmp_path)["OPTIMUS_AGENT_MODEL"] == "claude-haiku"


def test_enforced_default_is_the_cheapest_eligible_medium_model(tmp_path: Path) -> None:
    registry = verified_snapshot(tmp_path)
    assert default_agent_model(registry) == "cn/alpha"
    assert resolve_model_for_registry({}, registry=registry) == "cn/alpha"


@pytest.mark.parametrize("configured", ["claude-haiku", "anthropic/claude-haiku-4.5", "us/idle"])
def test_enforced_registry_refuses_models_it_does_not_make_eligible(tmp_path: Path, configured: str) -> None:
    registry = verified_snapshot(tmp_path)
    with pytest.raises(AgentModelError, match="not eligible"):
        resolve_model_for_registry({"OPTIMUS_AGENT_MODEL": configured}, registry=registry)


def test_enforced_registry_accepts_an_eligible_configured_model(tmp_path: Path) -> None:
    registry = verified_snapshot(tmp_path)
    assert resolve_model_for_registry({"OPTIMUS_AGENT_MODEL": "us/idle"}, cli_model="us/contrib", registry=registry) == "us/contrib"


def test_auto_is_refused_without_an_accepted_resolver(tmp_path: Path) -> None:
    with pytest.raises(AgentModelError, match="resolver"):
        resolve_model_for_registry({}, cli_model="auto", registry=verified_snapshot(tmp_path))


def test_no_eligible_medium_model_is_an_error_not_a_silent_fallback(tmp_path: Path) -> None:
    registry = verified_snapshot(tmp_path, VERIFIED_POLICY.replace("medium: [cn/alpha, us/contrib, cn/nullquant]", "easy: [cn/alpha]"))
    with pytest.raises(AgentModelError, match="medium"):
        default_agent_model(registry)


class _Transport:
    def __init__(self) -> None:
        self.requests: list[GatewayRequest] = []

    def post_json(self, request: GatewayRequest) -> dict[str, Any]:
        self.requests.append(request)
        return {
            "output_text": "ok",
            "finish_reason": "stop",
            "gateway_usage": {"gateway_request_id": "gw-1", "provider": "openrouter", "billing_units": 1, "cost_usd": "0.0001"},
        }


def _client(transport: _Transport) -> GatewayClient:
    settings = OptimusGatewaySettings.from_env(
        {"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765", "OPTIMUS_API_KEY": "k"}  # pragma: allowlist secret - synthetic test fixture
    )
    return GatewayClient(settings=settings, transport=transport)


def test_host_sends_no_binding_unless_given_one() -> None:
    transport = _Transport()
    _client(transport).create_response(model="claude-haiku", input_text="hi")
    assert "route_binding" not in transport.requests[0].payload


def test_host_sends_the_binding_in_its_wire_form() -> None:
    transport = _Transport()
    route_binding = RouteBinding(registry_hash="a" * 64, request_id="req-9", output_cap=512)
    _client(transport).create_response(model="cn/alpha", input_text="hi", route_binding=route_binding)
    assert transport.requests[0].payload["route_binding"] == route_binding.to_wire()
