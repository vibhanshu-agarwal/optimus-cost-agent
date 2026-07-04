from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

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
        )

    def expose_descriptors(self, *, server_id: str, manifest: MCPServerManifest) -> tuple[MCPToolDescriptor, ...]:
        return self.exposure_guard.expose_trusted_descriptors(server_id=server_id, manifest=manifest)

    def execute_tool(
        self,
        *,
        run_id: str,
        session_id: str | None,
        manifest: MCPServerManifest,
        tool_name: str,
        arguments: dict[str, Any],
        execution_mode: ExecutionMode,
        approval_granted: bool,
        runner: MCPToolRunner,
    ) -> dict[str, Any]:
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
        return runner(manifest.server_id, tool_name, arguments)
