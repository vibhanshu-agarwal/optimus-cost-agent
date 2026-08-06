from __future__ import annotations

import json

import pytest

from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import GatewayClient, GatewayRequest
from optimus.gateway.errors import GatewayResponseError
from optimus.gateway.mcp_models import MCPCallRequest, MCPDiscoverRequest


class _Transport:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.requests: list[GatewayRequest] = []

    def post_json(self, request: GatewayRequest) -> dict[str, object]:
        self.requests.append(request)
        return self.response


def _settings() -> OptimusGatewaySettings:
    return OptimusGatewaySettings(gateway_url="http://127.0.0.1:8765", optimus_api_key="opt_live_agent_secret")


def _discover_response() -> dict[str, object]:
    return {
        "profile_id": "packages",
        "profile_revision": "rev-1",
        "transport": "stdio",
        "protocol_version": "2026-07-28",
        "descriptors": [
            {
                "name": "packages.search",
                "description": "Search packages.",
                "input_schema": {"type": "object"},
                "annotations": {},
                "side_effect_class": "read",
            }
        ],
        "unmatched_allowlist": [],
        "manifest_hash": "a" * 64,
        "freshness": "fresh",
        "disposition": "mcp.discover.complete",
    }


def _call_response() -> dict[str, object]:
    return {
        "result_type": "complete",
        "content": [{"type": "text", "text": "ok"}],
        "disposition": "mcp.call.complete",
        "binding": {"profile_id": "packages", "profile_revision": "rev-1", "manifest_hash": "a" * 64},
        "transport": "stdio",
        "protocol_version": "2026-07-28",
        "attribution": "explicit_zero",
        "usage": {"gateway_request_id": "gw-1", "attribution": "explicit_zero", "billing_units": 0, "cost_usd": "0"},
    }


def test_typed_mcp_client_uses_exact_authenticated_routes_and_canonical_payloads() -> None:
    transport = _Transport(_discover_response())
    client = GatewayClient(settings=_settings(), transport=transport)
    request = MCPDiscoverRequest(profile_id="packages", profile_revision="rev-1")

    response = client.discover_mcp(request=request)

    sent = transport.requests[0]
    assert sent.method == "POST"
    assert sent.url == "http://127.0.0.1:8765/v1/tools/mcp/discover"
    assert sent.headers == {
        "Authorization": "Bearer opt_live_agent_secret",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    assert sent.payload == {"profile_id": "packages", "profile_revision": "rev-1"}
    assert response.profile_id == "packages"
    assert "opt_live_agent_secret" not in repr(sent)
    assert json.loads(sent.body_bytes()) == sent.payload


def test_typed_mcp_call_payload_contains_only_binding_context_and_arguments() -> None:
    transport = _Transport(_call_response())
    client = GatewayClient(settings=_settings(), transport=transport)
    request = MCPCallRequest(
        run_id="run-1",
        session_id="session-1",
        request_id="request-1",
        profile_id="packages",
        profile_revision="rev-1",
        manifest_hash="a" * 64,
        tool_name="packages.search",
        arguments={"query": "pytest"},
    )

    response = client.call_mcp(request=request)

    sent = transport.requests[0]
    assert sent.url == "http://127.0.0.1:8765/v1/tools/mcp/call"
    assert set(sent.payload) == {
        "run_id", "session_id", "request_id", "profile_id", "profile_revision", "manifest_hash", "tool_name", "arguments"
    }
    assert "credential" not in json.dumps(sent.payload).lower()
    assert response.binding.manifest_hash == "a" * 64


def test_generic_tool_proxy_rejects_mcp_paths_and_invalid_typed_responses() -> None:
    transport = _Transport({"unexpected": True})
    client = GatewayClient(settings=_settings(), transport=transport)

    with pytest.raises(ValueError, match="typed MCP"):
        client.post_tool_json(path="/v1/tools/mcp/other", payload={})
    with pytest.raises(GatewayResponseError, match="MCP response"):
        client.discover_mcp(request=MCPDiscoverRequest(profile_id="packages", profile_revision="rev-1"))
