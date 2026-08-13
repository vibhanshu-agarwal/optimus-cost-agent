"""Plan 11.11 Gateway-originated Context7 MCP compatibility probe.

Uses the existing ``GatewayClient`` and ``serve_gateway`` path only. This
module does not implement an upstream MCP server or a project-authored MCP
client. It is Plan 11.11 compatibility evidence, not Plan 11.8 release closure.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES, OptimusGatewaySettings
from optimus.gateway.client import GatewayClient
from optimus.gateway.mcp_models import MCPDiscoverRequest
from optimus_gateway.mcp_connections import MCPConnectionManager
from optimus_gateway.mcp_discovery import MCPDiscoveryBroker
from optimus_gateway.mcp_handlers import GatewayMCPDependencies
from optimus_gateway.mcp_invocation import MCPInvocationBroker
from optimus_gateway.mcp_profiles import (
    MCPAttributionPolicy,
    MCPHTTPProfile,
    MCPProfile,
    MCPProfileRegistry,
    MCPProfileState,
    MCPResourceLimits,
)
from optimus_gateway.mcp_usage import InMemoryMCPUsageWriter
from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.server import serve_gateway
from tests.integration.optimus_gateway.gateway_env import load_gateway_env_file

_CONTEXT7_PROFILE_ID = "context7"
_CONTEXT7_REVISION = "rev-11-11-context7-1"
_CONTEXT7_ALLOWLIST = ("resolve-library-id", "query-docs")


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.fail(f"{name} is required for this real dependency tier")
    return value


def _gateway_material() -> tuple[str, str]:
    configured = load_gateway_env_file()
    shared_secret = (
        os.environ.get("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", "").strip()
        or configured.get("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", "").strip()
    )
    provider_key = (
        os.environ.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "").strip()
        or configured.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "").strip()
    )
    if not shared_secret or not provider_key:
        pytest.fail(
            "the existing Gateway secret/configuration mechanism must provide "
            "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET and OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY"
        )
    return shared_secret, provider_key


def _assert_agent_one_key_boundary() -> None:
    present = sorted(name for name in LOCAL_PROVIDER_KEY_NAMES if os.environ.get(name))
    assert not present, f"local provider keys are present in the live test environment: {present}"


def _context7_none_profile(endpoint: str) -> MCPProfile:
    return MCPProfile(
        profile_id=_CONTEXT7_PROFILE_ID,
        revision=_CONTEXT7_REVISION,
        state=MCPProfileState.PENDING_REGISTRATION,
        transport="http",
        credential_ref=None,
        upstream_allowlist=_CONTEXT7_ALLOWLIST,
        manifest_hash=None,
        limits=MCPResourceLimits(
            max_pages=10,
            max_tools=20,
            max_descriptor_bytes=65536,
            max_elapsed_seconds=30.0,
            max_call_duration_seconds=30.0,
            max_result_bytes=65536,
        ),
        attribution_policy=MCPAttributionPolicy(allow_unattributed_spend=True),
        transport_config=MCPHTTPProfile(endpoint=endpoint, auth_mode="none"),
    )


def _discover_request(profile: MCPProfile) -> MCPDiscoverRequest:
    return MCPDiscoverRequest(
        profile_id=profile.profile_id,
        profile_revision=profile.revision,
        manifest_hash=None,
    )


@contextmanager
def _running_gateway(
    *,
    profile: MCPProfile,
    credential_resolver: Callable[[str | None], str | dict[str, str]],
) -> Iterator[SimpleNamespace]:
    shared_secret, provider_key = _gateway_material()
    registry = MCPProfileRegistry((profile,))
    connection_manager = MCPConnectionManager(credential_resolver=credential_resolver)
    usage_writer = InMemoryMCPUsageWriter()
    dependencies = GatewayMCPDependencies(
        registry=registry,
        discovery_broker=MCPDiscoveryBroker(),
        connection_manager=connection_manager,
        invocation_broker=MCPInvocationBroker(),
        usage_writer=usage_writer,
    )
    config = GatewayServiceConfig(
        bind_host="127.0.0.1",
        bind_port=0,
        shared_secret=shared_secret,
        provider="openrouter",
        provider_api_key=provider_key,
        base_url="https://openrouter.ai/api/v1",
    )
    server = serve_gateway(config=config, mcp_registry=registry, mcp_dependencies=dependencies)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    settings_env = {"OPTIMUS_GATEWAY_URL": f"http://{host}:{port}", "OPTIMUS_API_KEY": shared_secret}
    client = GatewayClient(settings=OptimusGatewaySettings.from_env(settings_env))
    try:
        yield SimpleNamespace(client=client)
    finally:
        connection_manager.close_all()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.requires_gateway
@pytest.mark.requires_mcp_context7
def test_context7_discovery_is_gateway_originated_and_unauthenticated():
    _assert_agent_one_key_boundary()
    assert not os.environ.get("OPTIMUS_MCP_CONTEXT7_BEARER", "").strip()
    endpoint = _required_env("OPTIMUS_MCP_CONTEXT7_URL")
    profile = _context7_none_profile(endpoint)
    resolver_calls: list[str | None] = []

    def resolver(ref: str | None):
        resolver_calls.append(ref)
        raise AssertionError("unauthenticated Context7 profile requested a credential")

    with _running_gateway(profile=profile, credential_resolver=resolver) as gateway:
        # Brief transcription fix: GatewayClient.discover_mcp is keyword-only (`request=`).
        response = gateway.client.discover_mcp(request=_discover_request(profile))

    assert response.protocol_version == "2026-07-28"
    assert response.descriptors
    assert response.unmatched_allowlist == ()
    assert response.disposition in {"mcp.discover.complete", "mcp.discover.unchanged"}
    assert resolver_calls == []
    assert {descriptor.name for descriptor in response.descriptors} == {
        f"{_CONTEXT7_PROFILE_ID}.{name}" for name in _CONTEXT7_ALLOWLIST
    }
