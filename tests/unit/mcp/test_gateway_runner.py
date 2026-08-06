from __future__ import annotations

from decimal import Decimal

import pytest

from optimus.gateway.mcp_models import (
    MCPBindingSummary,
    MCPCallResponse,
    MCPContent,
    MCPDiscoverResponse,
    MCPUsageRecordSummary,
)
from optimus.gateway.mcp_models import MCPToolDescriptor as GatewayToolDescriptor
from optimus.guardrails.mcp_trust import MCPServerManifest, MCPToolDescriptor
from optimus.mcp.runtime import GatewayClientMCPRunner, MCPRuntimeBlocked, MCPRuntimeTrustContext
from optimus.runtime.modes import ExecutionMode


def _manifest() -> MCPServerManifest:
    return MCPServerManifest(
        server_id="packages",
        command=("docker", "run"),
        tools=(
            MCPToolDescriptor(
                name="search",
                description="Search approved package metadata.",
                input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
                side_effect_class="read",
            ),
        ),
    )


_GATEWAY_MANIFEST_HASH = "b" * 64


def _response(*, revision: str = "rev-1", manifest_hash: str = _GATEWAY_MANIFEST_HASH) -> MCPCallResponse:
    return MCPCallResponse(
        result_type="complete",
        content=(MCPContent(type="text", text="ok"),),
        disposition="mcp.call.complete",
        binding=MCPBindingSummary(
            profile_id="packages", profile_revision=revision, manifest_hash=manifest_hash
        ),
        transport="stdio",
        protocol_version="2026-07-28",
        attribution="explicit_zero",
        usage=MCPUsageRecordSummary(
            gateway_request_id="gw-mcp-1", attribution="explicit_zero", billing_units=0, cost_usd=Decimal("0")
        ),
    )


class _Runner:
    def __init__(self) -> None:
        self.requests = []

    def discover(self, request):
        self.requests.append(request)
        return {"discovered": True}

    def call(self, request):
        self.requests.append(request)
        return _response()


def _context(tmp_path, *, revision: str = "rev-1") -> tuple[MCPRuntimeTrustContext, MCPServerManifest]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    context = MCPRuntimeTrustContext.for_workspace(workspace_root=workspace, allowed_network_hosts=())
    current = _manifest()
    context.register_explicit_manifest(
        current,
        manifest_path=tmp_path / "approved" / "packages.mcp.json",
        allowed_tools=("search",),
        permission_scope="read_only_metadata",
        approved_by="maintainer",
        profile_revision=revision,
        manifest_text='{"mcpServers": {"packages": {"command": "docker"}}}',
    )
    context.bind_gateway_discovery(
        manifest=current,
        discovery=MCPDiscoverResponse(
            profile_id="packages",
            profile_revision=revision,
            transport="stdio",
            protocol_version="2026-07-28",
            descriptors=(
                GatewayToolDescriptor(
                    name="packages.search",
                    description="Search approved package metadata.",
                    input_schema={"type": "object"},
                ),
            ),
            manifest_hash=_GATEWAY_MANIFEST_HASH,
            freshness="fresh",
            disposition="mcp.discover.complete",
        ),
    )
    return context, current


def test_gateway_runner_adapter_uses_typed_client_methods() -> None:
    class _Client:
        def discover_mcp(self, *, request):
            return request

        def call_mcp(self, *, request):
            return request

    runner = GatewayClientMCPRunner(client=_Client())
    request = object()
    assert runner.discover(request) is request
    assert runner.call(request) is request


def test_runtime_denies_before_typed_gateway_runner_when_local_approval_is_missing(tmp_path) -> None:
    context, current = _context(tmp_path)
    runner = _Runner()

    with pytest.raises(MCPRuntimeBlocked):
        context.execute_tool(
            run_id="run-1",
            session_id="session-1",
            request_id="request-1",
            profile_revision="rev-1",
            manifest=current,
            tool_name="search",
            arguments={"query": "pytest"},
            execution_mode=ExecutionMode.AGENT,
            approval_granted=False,
            runner=runner,
        )

    assert runner.requests == []


def test_runtime_sends_typed_gateway_call_after_local_guard_and_preserves_binding(tmp_path) -> None:
    context, current = _context(tmp_path)
    runner = _Runner()

    result = context.execute_tool(
        run_id="run-1",
        session_id="session-1",
        request_id="request-1",
        profile_revision="rev-1",
        manifest=current,
        tool_name="search",
        arguments={"query": "pytest"},
        execution_mode=ExecutionMode.AGENT,
        approval_granted=True,
        runner=runner,
    )

    request = runner.requests[0]
    assert request.run_id == "run-1"
    assert request.session_id == "session-1"
    assert request.request_id == "request-1"
    assert request.profile_id == "packages"
    assert request.profile_revision == "rev-1"
    assert request.manifest_hash == _GATEWAY_MANIFEST_HASH
    assert request.manifest_hash != current.manifest_hash()
    assert request.tool_name == "packages.search"
    assert request.arguments == {"query": "pytest"}
    assert result.binding.profile_revision == "rev-1"


def test_runtime_holds_revision_drift_before_gateway_runner(tmp_path) -> None:
    context, current = _context(tmp_path, revision="rev-1")
    runner = _Runner()

    with pytest.raises(MCPRuntimeBlocked, match="revision"):
        context.execute_tool(
            run_id="run-1",
            session_id=None,
            request_id="request-1",
            profile_revision="rev-2",
            manifest=current,
            tool_name="search",
            arguments={},
            execution_mode=ExecutionMode.AGENT,
            approval_granted=True,
            runner=runner,
        )

    assert runner.requests == []
