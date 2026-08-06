"""Plan 11.8 live MCP Gateway evidence.

The upstream HTTP and stdio dependencies are operator-provided independent
fixtures. This module intentionally contains no MCP server or MCP client;
``GatewayClient`` is the only client used to drive the two Gateway routes.

The independent fixtures expose the small, stable contract used here: a
multi-page tools catalog containing ``echo`` and ``read_only`` and an echo
``tools/call`` accepting ``{"text": ...}``. The stdio fixture image is
digest-pinned and exposes the same contract through its configured
``mcp-test-server`` command.
"""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from dataclasses import asdict
from typing import Iterator
from urllib.parse import urlsplit

import keyring
import pytest

from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES, OptimusGatewaySettings
from optimus.gateway.client import GatewayClient
from optimus.gateway.errors import GatewayHttpError
from optimus.gateway.mcp_models import MCPCallRequest, MCPDiscoverRequest
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
    MCPStdioProfile,
)
from optimus_gateway.mcp_usage import InMemoryMCPUsageWriter
from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.server import serve_gateway
from tests.integration.optimus_gateway.gateway_env import load_gateway_env_file

_HTTP_PROFILE_ID = "plan118-http"
_STDIO_PROFILE_ID = "plan118-stdio"
_HTTP_REVISION = "rev-http-live-1"
_STDIO_REVISION = "rev-stdio-live-1"
_HTTP_ALLOWLIST = ("echo", "read_only")
_STDIO_ALLOWLIST = ("echo", "read_only")
_CALL_ARGUMENTS = {"text": "plan-11-8-gateway-mcp"}
_STDIO_COMMAND = "mcp-test-server"
_STDIO_ENV_NAME = "MCP_TEST_CREDENTIAL"


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.fail(f"{name} is required for this real MCP dependency tier")
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


def _limits() -> MCPResourceLimits:
    return MCPResourceLimits(
        max_pages=10,
        max_tools=20,
        max_descriptor_bytes=65_536,
        max_elapsed_seconds=30.0,
        max_call_duration_seconds=30.0,
        max_result_bytes=65_536,
    )


def _http_profile(*, revision: str = _HTTP_REVISION, manifest_hash: str | None = None) -> MCPProfile:
    endpoint = _required_env("OPTIMUS_MCP_HTTP_TEST_URL")
    return MCPProfile(
        profile_id=_HTTP_PROFILE_ID,
        revision=revision,
        state=MCPProfileState.PENDING_REGISTRATION,
        transport="http",
        credential_ref="gateway://plan118/http-test",
        upstream_allowlist=_HTTP_ALLOWLIST,
        manifest_hash=manifest_hash,
        limits=_limits(),
        attribution_policy=MCPAttributionPolicy(allow_unattributed_spend=True),
        transport_config=MCPHTTPProfile(
            endpoint=endpoint,
            allow_insecure_loopback=urlsplit(endpoint).hostname in {"127.0.0.1", "localhost", "::1"},
        ),
    )


def _stdio_profile(*, revision: str = _STDIO_REVISION, manifest_hash: str | None = None) -> MCPProfile:
    return MCPProfile(
        profile_id=_STDIO_PROFILE_ID,
        revision=revision,
        state=MCPProfileState.PENDING_REGISTRATION,
        transport="stdio",
        credential_ref=_required_env("OPTIMUS_MCP_STDIO_CREDENTIAL_REF"),
        upstream_allowlist=_STDIO_ALLOWLIST,
        manifest_hash=manifest_hash,
        limits=_limits(),
        attribution_policy=MCPAttributionPolicy(allow_unattributed_spend=True),
        transport_config=MCPStdioProfile(
            image=_required_env("OPTIMUS_MCP_STDIO_IMAGE_DIGEST"),
            command=_STDIO_COMMAND,
            environment_names=(_STDIO_ENV_NAME,),
        ),
    )


def _profile_metadata(profile: MCPProfile, *, manifest_hash: str) -> dict[str, object]:
    config = profile.transport_config
    transport_config = asdict(config)
    values: dict[str, object] = {
        "profile_id": profile.profile_id,
        "revision": profile.revision,
        "state": MCPProfileState.PENDING_REGISTRATION.value,
        "transport": profile.transport,
        "credential_ref": profile.credential_ref,
        "upstream_allowlist": list(profile.upstream_allowlist),
        "manifest_hash": manifest_hash,
        "limits": asdict(profile.limits),
        "attribution_policy": asdict(profile.attribution_policy),
        "transport_config": transport_config,
    }
    return values


def _credential_resolver(profile: MCPProfile, ref: str) -> str | dict[str, str]:
    if ref == profile.credential_ref and profile.transport == "http":
        return _required_env("OPTIMUS_MCP_HTTP_TEST_BEARER")
    if ref == profile.credential_ref and profile.transport == "stdio":
        # The reference is an operator-approved keyring account in the
        # existing Gateway secret mechanism; the raw value never enters the
        # agent environment or a test report.
        value = keyring.get_password("optimus-cost-agent", ref)
        if not value:
            pytest.fail("OPTIMUS_MCP_STDIO_CREDENTIAL_REF has no Gateway keyring value")
        return {_STDIO_ENV_NAME: value}
    raise AssertionError("unexpected MCP credential reference")


@contextmanager
def _running_gateway(
    *, profile: MCPProfile, shared_secret: str, provider_key: str
) -> Iterator[tuple[GatewayClient, str, MCPProfileRegistry, MCPConnectionManager, InMemoryMCPUsageWriter]]:
    registry = MCPProfileRegistry((profile,))
    connection_manager = MCPConnectionManager(
        credential_resolver=lambda ref: _credential_resolver(profile, ref)
    )
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
        yield client, settings_env["OPTIMUS_GATEWAY_URL"], registry, connection_manager, usage_writer
    finally:
        connection_manager.close_all()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _discover(client: GatewayClient, profile: MCPProfile, *, manifest_hash: str | None = None):
    return client.discover_mcp(
        request=MCPDiscoverRequest(
            profile_id=profile.profile_id,
            profile_revision=profile.revision,
            manifest_hash=manifest_hash,
        )
    )


def _call(client: GatewayClient, profile: MCPProfile, manifest_hash: str):
    return client.call_mcp(
        request=MCPCallRequest(
            run_id="plan118-live-run",
            session_id="plan118-live-session",
            request_id="plan118-live-request",
            profile_id=profile.profile_id,
            profile_revision=profile.revision,
            manifest_hash=manifest_hash,
            tool_name=f"{profile.profile_id}.echo",
            arguments=_CALL_ARGUMENTS,
        )
    )


@pytest.mark.requires_gateway
@pytest.mark.requires_mcp_http
def test_http_pending_approval_restart_refresh_and_call() -> None:
    _assert_agent_one_key_boundary()
    shared_secret, provider_key = _gateway_material()
    pending = _http_profile()

    with _running_gateway(profile=pending, shared_secret=shared_secret, provider_key=provider_key) as (
        client,
        _gateway_url,
        registry,
        _connections,
        _writer,
    ):
        discovered = _discover(client, pending)
        assert discovered.protocol_version == "2026-07-28"
        assert {descriptor.name for descriptor in discovered.descriptors} == {
            f"{_HTTP_PROFILE_ID}.{name}" for name in _HTTP_ALLOWLIST
        }
        assert discovered.unmatched_allowlist == ()
        assert discovered.freshness == "fresh"
        assert discovered.disposition == "mcp.discover.complete"
        startup_metadata = _profile_metadata(pending, manifest_hash=discovered.manifest_hash)
        assert registry.get(_HTTP_PROFILE_ID).state is MCPProfileState.PENDING_REGISTRATION

    active = MCPProfileRegistry.from_startup_metadata([startup_metadata]).get(_HTTP_PROFILE_ID)
    with _running_gateway(profile=active, shared_secret=shared_secret, provider_key=provider_key) as (
        client,
        gateway_url,
        _registry,
        _connections,
        writer,
    ):
        refreshed = _discover(client, active, manifest_hash=discovered.manifest_hash)
        assert refreshed.freshness == "unchanged"
        assert refreshed.disposition == "mcp.discover.unchanged"

        with pytest.raises(GatewayHttpError) as unauthorized:
            bad_client = GatewayClient(
                settings=OptimusGatewaySettings.from_env(
                    {
                        "OPTIMUS_GATEWAY_URL": gateway_url,
                        "OPTIMUS_API_KEY": "wrong-bearer",
                    }
                )
            )
            _discover(bad_client, active, manifest_hash=discovered.manifest_hash)
        assert unauthorized.value.status_code == 401

        response = _call(client, active, discovered.manifest_hash)
        assert response.result_type == "complete"
        assert response.protocol_version == "2026-07-28"
        assert response.binding.manifest_hash == discovered.manifest_hash
        assert response.usage.gateway_request_id
        assert writer.record_for(response.usage.gateway_request_id) is not None


@pytest.mark.requires_gateway
@pytest.mark.requires_mcp_http
def test_http_revision_drift_denies_old_binding_and_reopens_connection_axis() -> None:
    _assert_agent_one_key_boundary()
    shared_secret, provider_key = _gateway_material()
    profile = _http_profile()

    with _running_gateway(profile=profile, shared_secret=shared_secret, provider_key=provider_key) as (
        client,
        _gateway_url,
        registry,
        connections,
        _writer,
    ):
        discovered = _discover(client, profile)
        registry.activate_from_startup(
            profile_id=profile.profile_id,
            revision=profile.revision,
            manifest_hash=discovered.manifest_hash,
        )
        active = registry.get(profile.profile_id)
        first_connection = connections.open_for(active)
        replacement = registry.update_profile(profile_id=profile.profile_id, upstream_allowlist=_HTTP_ALLOWLIST)
        second_connection = connections.open_for(replacement)
        assert second_connection is not first_connection
        assert replacement.revision != active.revision

        with pytest.raises(GatewayHttpError) as denied:
            _call(client, active, discovered.manifest_hash)
        assert denied.value.status_code == 403


@pytest.mark.requires_gateway
@pytest.mark.requires_mcp_stdio
def test_stdio_digest_pinned_discovery_call_and_deterministic_teardown() -> None:
    _assert_agent_one_key_boundary()
    shared_secret, provider_key = _gateway_material()
    profile = _stdio_profile()

    with _running_gateway(profile=profile, shared_secret=shared_secret, provider_key=provider_key) as (
        client,
        _gateway_url,
        registry,
        connections,
        writer,
    ):
        discovered = _discover(client, profile)
        assert discovered.protocol_version == "2026-07-28"
        assert discovered.unmatched_allowlist == ()
        registry.activate_from_startup(
            profile_id=profile.profile_id,
            revision=profile.revision,
            manifest_hash=discovered.manifest_hash,
        )
        active = registry.get(profile.profile_id)
        response = _call(client, active, discovered.manifest_hash)
        assert response.result_type == "complete"
        assert response.transport == "stdio"
        assert writer.record_for(response.usage.gateway_request_id) is not None
        connections.close_profile(profile_id=active.profile_id, revision=active.revision)
        assert connections._connections == {}  # noqa: SLF001 - teardown evidence
