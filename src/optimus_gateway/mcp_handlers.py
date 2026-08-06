"""Authenticated typed handlers for the two Gateway MCP routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from pydantic import ValidationError

from optimus_gateway.mcp_connections import MCPConnectionManager
from optimus_gateway.mcp_discovery import MCPDiscoveryBroker, MCPDiscoveryError
from optimus_gateway.mcp_invocation import MCPInvocationBroker, MCPInvocationError
from optimus_gateway.mcp_models import MCPCallRequest, MCPDiscoverRequest
from optimus_gateway.mcp_profiles import MCPProfileRegistry
from optimus_gateway.models import GatewayServiceConfig, authorize_bearer
from optimus_gateway.responses import sanitize_error_message

MCP_ROUTE_PATHS = frozenset({"/v1/tools/mcp/discover", "/v1/tools/mcp/call"})


@dataclass(frozen=True)
class GatewayMCPDependencies:
    registry: MCPProfileRegistry
    discovery_broker: MCPDiscoveryBroker
    connection_manager: MCPConnectionManager
    invocation_broker: MCPInvocationBroker
    usage_writer: object


def handle_mcp_request(
    *,
    authorization_header: str | None,
    path: str,
    request_body: Mapping[str, Any],
    config: GatewayServiceConfig,
    dependencies: GatewayMCPDependencies,
) -> tuple[int, dict[str, Any]]:
    if not authorize_bearer(authorization_header=authorization_header, shared_secret=config.shared_secret):
        return 401, {"error": "unauthorized"}
    if path not in MCP_ROUTE_PATHS:
        return 404, {"error": "not found"}

    if path == "/v1/tools/mcp/discover":
        try:
            request = MCPDiscoverRequest.model_validate(dict(request_body))
        except ValidationError as exc:
            return 400, {"error": _validation_message(exc)}
        try:
            response = dependencies.discovery_broker.discover(
                request=request,
                registry=dependencies.registry,
                connection_manager=dependencies.connection_manager,
            )
        except MCPDiscoveryError as exc:
            return _discovery_error(exc)
        except Exception:  # noqa: BLE001 - no upstream detail crosses the route boundary
            return 502, {"error": "mcp discovery failed"}
        return 200, response.model_dump(mode="json")

    try:
        request = MCPCallRequest.model_validate(dict(request_body))
    except ValidationError as exc:
        return 400, {"error": _validation_message(exc)}
    try:
        response = dependencies.invocation_broker.call(
            request=request,
            registry=dependencies.registry,
            connection_manager=dependencies.connection_manager,
            usage_writer=dependencies.usage_writer,
        )
    except MCPInvocationError as exc:
        return exc.status, {"error": exc.disposition}
    except Exception:  # noqa: BLE001 - no upstream detail crosses the route boundary
        return 502, {"error": "mcp invocation failed"}
    return 200, response.model_dump(mode="json")


def _discovery_error(exc: MCPDiscoveryError) -> tuple[int, dict[str, Any]]:
    disposition = str(getattr(exc, "disposition", "mcp.discovery_failed"))
    status = 429 if "budget" in disposition else 422
    return status, {"error": sanitize_error_message(disposition)}


def _validation_message(exc: ValidationError) -> str:
    fields = [str(error.get("loc", "request")) for error in exc.errors()]
    return sanitize_error_message("invalid MCP request: " + ", ".join(fields))


__all__ = ["GatewayMCPDependencies", "MCP_ROUTE_PATHS", "handle_mcp_request"]
