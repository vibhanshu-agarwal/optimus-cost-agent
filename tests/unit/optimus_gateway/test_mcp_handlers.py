from __future__ import annotations

from typing import Any

from optimus_gateway.mcp_handlers import GatewayMCPDependencies, handle_mcp_request
from optimus_gateway.mcp_models import MCPDiscoverResponse
from optimus_gateway.models import GatewayServiceConfig


def _config() -> GatewayServiceConfig:
    return GatewayServiceConfig(
        bind_host="127.0.0.1",
        bind_port=0,
        shared_secret="gateway-secret",
        provider="openrouter",
        provider_api_key="provider-only-gateway-secret",
        base_url="https://openrouter.ai/api/v1",
    )


class _Discovery:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def discover(self, *, request: object, registry: object, connection_manager: object) -> MCPDiscoverResponse:
        self.calls.append(request)
        return MCPDiscoverResponse(
            profile_id="context7",
            profile_revision="rev-1",
            transport="http",
            protocol_version="2026-07-28",
            descriptors=(),
            manifest_hash="a" * 64,
            freshness="fresh",
            disposition="mcp.discover.complete",
        )


class _Invocation:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def call(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return kwargs["response"] if "response" in kwargs else {
            "result_type": "complete"
        }


class _Unused:
    pass


def _dependencies(*, discovery: object | None = None, invocation: object | None = None) -> GatewayMCPDependencies:
    return GatewayMCPDependencies(
        registry=_Unused(),
        discovery_broker=discovery or _Discovery(),
        connection_manager=_Unused(),
        invocation_broker=invocation or _Unused(),
        usage_writer=_Unused(),
    )


def test_mcp_handler_authenticates_before_parsing_or_dispatching():
    discovery = _Discovery()
    status, body = handle_mcp_request(
        authorization_header="Bearer wrong",
        path="/v1/tools/mcp/discover",
        request_body={"profile_id": "context7", "profile_revision": "rev-1"},
        config=_config(),
        dependencies=_dependencies(discovery=discovery),
    )

    assert (status, body) == (401, {"error": "unauthorized"})
    assert discovery.calls == []


def test_mcp_handler_rejects_wrong_route_and_malformed_typed_body():
    dependencies = _dependencies()

    assert handle_mcp_request(
        authorization_header="Bearer gateway-secret",
        path="/v1/tools/mcp/other",
        request_body={},
        config=_config(),
        dependencies=dependencies,
    ) == (404, {"error": "not found"})
    status, body = handle_mcp_request(
        authorization_header="Bearer gateway-secret",
        path="/v1/tools/mcp/discover",
        request_body={"profile_id": "context7", "unexpected": True},
        config=_config(),
        dependencies=dependencies,
    )
    assert status == 400
    assert "unexpected" in body["error"]


def test_discover_handler_returns_typed_json_and_never_returns_profile_secrets():
    discovery = _Discovery()
    status, body = handle_mcp_request(
        authorization_header="Bearer gateway-secret",
        path="/v1/tools/mcp/discover",
        request_body={"profile_id": "context7", "profile_revision": "rev-1"},
        config=_config(),
        dependencies=_dependencies(discovery=discovery),
    )

    assert status == 200
    assert body["disposition"] == "mcp.discover.complete"
    serialized = str(body)
    assert "provider-only-gateway-secret" not in serialized
    assert "credential_ref" not in serialized


def test_handler_sanitizes_broker_failures_and_does_not_echo_server_text():
    class _BrokenDiscovery:
        def discover(self, **_kwargs: Any) -> object:
            raise RuntimeError("server text secret=top-secret Authorization: Bearer abc")

    status, body = handle_mcp_request(
        authorization_header="Bearer gateway-secret",
        path="/v1/tools/mcp/discover",
        request_body={"profile_id": "context7", "profile_revision": "rev-1"},
        config=_config(),
        dependencies=_dependencies(discovery=_BrokenDiscovery()),
    )

    assert status == 502
    serialized = str(body)
    assert "top-secret" not in serialized
    assert "Bearer abc" not in serialized
