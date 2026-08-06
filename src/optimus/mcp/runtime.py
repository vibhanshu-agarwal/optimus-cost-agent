from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from optimus.gateway.client import GatewayClient
from optimus.gateway.mcp_models import (
    MCPCallRequest,
    MCPCallResponse,
    MCPDiscoverRequest,
    MCPDiscoverResponse,
    namespace_tool_name,
)
from optimus.guardrails.mcp_trust import (
    MCPConfigIngestionGuard,
    MCPDescriptorExposureGuard,
    MCPServerManifest,
    MCPServerTrustRecord,
    MCPToolDescriptor,
    MCPTrustDecision,
    MCPTrustRegistry,
)
from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard, PreToolRequest, PreToolVerdict
from optimus.guardrails.prompt_injection import ConfigTrustScanner
from optimus.runtime.modes import ExecutionMode

MCPToolRunner = Callable[[str, str, dict[str, Any]], dict[str, Any]]


class MCPGatewayRunner(Protocol):
    def discover(self, request: MCPDiscoverRequest) -> MCPDiscoverResponse: ...

    def call(self, request: MCPCallRequest) -> MCPCallResponse: ...


class GatewayClientMCPRunner:
    def __init__(self, *, client: GatewayClient) -> None:
        self._client = client

    def discover(self, request: MCPDiscoverRequest) -> MCPDiscoverResponse:
        return self._client.discover_mcp(request=request)

    def call(self, request: MCPCallRequest) -> MCPCallResponse:
        return self._client.call_mcp(request=request)


class MCPRuntimeBlocked(RuntimeError):
    pass


class MCPRuntimeTrustContext:
    def __init__(
        self,
        *,
        registry: MCPTrustRegistry,
        ingestion_guard: MCPConfigIngestionGuard,
        exposure_guard: MCPDescriptorExposureGuard,
        pre_tool_guard: PreToolGuard,
    ) -> None:
        self.registry = registry
        self.ingestion_guard = ingestion_guard
        self.exposure_guard = exposure_guard
        self.pre_tool_guard = pre_tool_guard

    @classmethod
    def for_workspace(cls, *, workspace_root: str | Path, allowed_network_hosts: tuple[str, ...]) -> MCPRuntimeTrustContext:
        scanner = ConfigTrustScanner()
        registry = MCPTrustRegistry(scanner=scanner)
        return cls(
            registry=registry,
            ingestion_guard=MCPConfigIngestionGuard(workspace_root=workspace_root, scanner=scanner),
            exposure_guard=MCPDescriptorExposureGuard(registry=registry),
            pre_tool_guard=PreToolGuard.for_workspace(
                workspace_root=workspace_root,
                allowed_network_hosts=allowed_network_hosts,
                mcp_trust_registry=registry,
            ),
        )

    def deny_autoload_manifest(self, manifest_path: str | Path) -> MCPTrustDecision:
        return self.ingestion_guard.deny_autoload_path(manifest_path)

    def register_explicit_manifest(
        self,
        manifest: MCPServerManifest,
        *,
        manifest_path: str | Path,
        allowed_tools: tuple[str, ...],
        permission_scope: str,
        approved_by: str,
        profile_revision: str = "legacy",
        manifest_text: str | None = None,
    ) -> MCPServerTrustRecord:
        path = Path(manifest_path)
        if self.ingestion_guard.is_workspace_bundled_path(path):
            autoload_decision = self.ingestion_guard.deny_autoload_path(path)
            raise MCPRuntimeBlocked(f"{autoload_decision.rule_id}: {autoload_decision.reason}")
        if manifest_text is not None:
            decision = self.ingestion_guard.scan_manifest_text(manifest_text, source_path=path.as_posix())
            if not decision.allowed:
                raise MCPRuntimeBlocked(f"{decision.rule_id}: {decision.reason}")
        else:
            decision = self.ingestion_guard.scan_manifest_path(path)
            if not decision.allowed:
                raise MCPRuntimeBlocked(f"{decision.rule_id}: {decision.reason}")
        return self.registry.register(
            manifest,
            allowed_tools=allowed_tools,
            permission_scope=permission_scope,
            approved_by=approved_by,
            profile_revision=profile_revision,
        )

    def expose_descriptors(self, *, server_id: str, manifest: MCPServerManifest) -> tuple[MCPToolDescriptor, ...]:
        return self.exposure_guard.expose_trusted_descriptors(server_id=server_id, manifest=manifest)

    def bind_gateway_discovery(self, *, manifest: MCPServerManifest, discovery: MCPDiscoverResponse) -> MCPServerTrustRecord:
        if discovery.profile_id != manifest.server_id:
            raise MCPRuntimeBlocked("mcp.gateway_profile_mismatch: discovery profile does not match local server")
        decision = self.registry.bind_gateway_manifest(
            server_id=manifest.server_id,
            manifest=manifest,
            profile_revision=discovery.profile_revision,
            gateway_manifest_hash=discovery.manifest_hash,
        )
        if not decision.allowed:
            raise MCPRuntimeBlocked(f"{decision.rule_id}: {decision.reason}")
        record = self.registry.record_for(manifest.server_id)
        if record is None:
            raise MCPRuntimeBlocked("mcp.gateway_manifest_unbound: local approval disappeared")
        return record

    def execute_tool(
        self,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str | None = None,
        profile_revision: str = "legacy",
        manifest: MCPServerManifest,
        tool_name: str,
        arguments: dict[str, Any],
        execution_mode: ExecutionMode,
        approval_granted: bool,
        runner: MCPToolRunner | MCPGatewayRunner,
    ) -> dict[str, Any] | MCPCallResponse:
        binding = self.registry.validate_tool_call(
            server_id=manifest.server_id,
            manifest=manifest,
            tool_name=tool_name,
            profile_revision=profile_revision,
        )
        if not binding.allowed:
            raise MCPRuntimeBlocked(f"{binding.rule_id}: {binding.reason}")
        result = self.pre_tool_guard.check(
            PreToolRequest(
                run_id=run_id,
                session_id=session_id,
                execution_mode=execution_mode,
                tool_surface=ToolSurface.MCP,
                action=f"mcp:{manifest.server_id}/{tool_name}",
                approval_granted=approval_granted,
                mcp_server_id=manifest.server_id,
                mcp_tool_name=tool_name,
                mcp_manifest=manifest,
            )
        )
        if result.verdict is not PreToolVerdict.ALLOW:
            raise MCPRuntimeBlocked(f"{result.rule_id}: {result.reason}")
        if hasattr(runner, "call"):
            gateway_manifest_hash = self.registry.gateway_manifest_hash_for(manifest.server_id)
            if gateway_manifest_hash is None:
                raise MCPRuntimeBlocked("mcp.gateway_manifest_unbound: typed calls require Gateway discovery binding")
            request = MCPCallRequest(
                run_id=run_id,
                session_id=session_id,
                request_id=request_id or f"{run_id}:{manifest.server_id}:{tool_name}",
                profile_id=manifest.server_id,
                profile_revision=profile_revision,
                manifest_hash=gateway_manifest_hash,
                tool_name=namespace_tool_name(profile_id=manifest.server_id, tool_name=tool_name),
                arguments=arguments,
            )
            response = runner.call(request)
            if not isinstance(response, MCPCallResponse):
                raise MCPRuntimeBlocked("mcp.gateway_response_invalid: typed MCP response required")
            if (
                response.binding.profile_id != request.profile_id
                or response.binding.profile_revision != request.profile_revision
                or response.binding.manifest_hash != request.manifest_hash
            ):
                raise MCPRuntimeBlocked("mcp.gateway_binding_drift: Gateway response binding changed")
            return response
        return runner(manifest.server_id, tool_name, arguments)
