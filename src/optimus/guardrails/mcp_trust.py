from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from optimus.guardrails.prompt_injection import ConfigTrustScanner, TrustScanSubject, TrustScanVerdict


class MCPTrustError(ValueError):
    pass


_PERMISSION_SCOPE_LIMITS = {
    "read_only_metadata": "read",
    "network_read": "network",
}
_SIDE_EFFECT_RANK = {"read": 0, "network": 1, "write": 2}
_WRITE_HINTS = ("write", "delete", "remove", "create", "update", "mutate", "patch", "upload", "send", "execute", "run")
_NETWORK_HINTS = ("fetch", "download", "http", "url", "request")


@dataclass(frozen=True)
class MCPToolDescriptor:
    name: str
    description: str
    input_schema: dict[str, Any]
    side_effect_class: str = "read"

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "side_effect_class": self.side_effect_class,
        }


@dataclass(frozen=True)
class MCPServerManifest:
    """Trust-boundary artifact for an MCP server under an "approve what you see" model.

    Design intent:
    - Explicit approval: servers are not auto-trusted; registration requires a human-chosen tool allowlist.
    - Tamper detection: any change to the declared surface (command, launch args, cwd, env, tools) breaks
      ``manifest_hash`` and forces reapproval.
    - Injection resistance: ``descriptor_text()`` feeds ``ConfigTrustScanner``; descriptions and config are untrusted.
    - Least privilege: only tools within the approved allowlist and permission scope reach the planner.

    Everything else in this module operates on this object as the canonical record of what was evaluated and approved.
    """

    server_id: str
    command: tuple[str, ...]
    tools: tuple[MCPToolDescriptor, ...]
    launch_args: tuple[str, ...] = ()
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)

    def manifest_hash(self) -> str:
        payload = {
            "server_id": self.server_id,
            "command": list(self.command),
            "launch_args": list(self.launch_args),
            "cwd": self.cwd,
            "env": {key: _secret_digest(value) for key, value in sorted(self.env.items())},
            "tools": [tool.canonical_payload() for tool in self.tools],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def descriptor_text(self) -> str:
        parts = [self.server_id, " ".join((*self.command, *self.launch_args))]
        if self.cwd:
            parts.append(f"cwd={self.cwd}")
        for key in sorted(self.env):
            parts.append(f"env:{key}=<redacted:{_secret_digest(self.env[key])}>")
        for tool in self.tools:
            parts.append(tool.name)
            parts.append(tool.description)
            parts.append(json.dumps(tool.input_schema, sort_keys=True))
            parts.append(f"side_effect_class={tool.side_effect_class}")
        return "\n".join(parts)

    def tool_by_name(self, tool_name: str) -> MCPToolDescriptor | None:
        return next((tool for tool in self.tools if tool.name == tool_name), None)


@dataclass(frozen=True)
class MCPServerTrustRecord:
    server_id: str
    manifest_hash: str
    allowed_tools: frozenset[str]
    permission_scope: str
    approved_tool_effects: dict[str, str]
    approved: bool
    approved_by: str
    scan_summary: str


@dataclass(frozen=True)
class MCPTrustDecision:
    allowed: bool
    rule_id: str
    reason: str
    requires_human_approval: bool = False


class MCPTrustRegistry:
    def __init__(self, *, scanner: ConfigTrustScanner) -> None:
        self._scanner = scanner
        self._records: dict[str, MCPServerTrustRecord] = {}

    def register(
        self,
        manifest: MCPServerManifest,
        *,
        allowed_tools: tuple[str, ...],
        permission_scope: str,
        approved_by: str,
    ) -> MCPServerTrustRecord:
        _validate_permission_scope(permission_scope)
        scan = self._scanner.scan_text(
            manifest.descriptor_text(),
            subject=TrustScanSubject.MCP_DESCRIPTOR,
            source_path=f"mcp:{manifest.server_id}",
        )
        if scan.verdict is TrustScanVerdict.BLOCK:
            rules = ",".join(finding.rule_id for finding in scan.findings)
            raise MCPTrustError(f"MCP descriptor rejected: {rules}")
        declared_tools = {tool.name for tool in manifest.tools}
        unknown_allowed = set(allowed_tools) - declared_tools
        if unknown_allowed:
            raise MCPTrustError(f"allowed tools not declared by manifest: {sorted(unknown_allowed)}")
        approved_effects: dict[str, str] = {}
        for tool_name in allowed_tools:
            tool = manifest.tool_by_name(tool_name)
            if tool is None:
                raise MCPTrustError(f"allowed tools not declared by manifest: {tool_name}")
            effect_class = _effective_side_effect_class(tool)
            if not _scope_allows(permission_scope, effect_class):
                raise MCPTrustError(f"mcp.scope_violation: {tool_name} has {effect_class} effects outside {permission_scope}")
            approved_effects[tool_name] = effect_class
        record = MCPServerTrustRecord(
            server_id=manifest.server_id,
            manifest_hash=manifest.manifest_hash(),
            allowed_tools=frozenset(allowed_tools),
            permission_scope=permission_scope,
            approved_tool_effects=approved_effects,
            approved=True,
            approved_by=approved_by,
            scan_summary=f"{scan.sanitized_summary}; tool_effects={approved_effects}",
        )
        self._records[manifest.server_id] = record
        return record

    def validate_tool_call(self, *, server_id: str, manifest: MCPServerManifest, tool_name: str) -> MCPTrustDecision:
        record = self._records.get(server_id)
        if record is None:
            return MCPTrustDecision(False, "mcp.server_not_registered", "MCP server requires explicit approval", True)
        if not record.approved:
            return MCPTrustDecision(False, "mcp.server_not_approved", "MCP server is not approved", True)
        if record.manifest_hash != manifest.manifest_hash():
            return MCPTrustDecision(False, "mcp.manifest_hash_changed", "MCP manifest changed and requires reapproval", True)
        if tool_name not in record.allowed_tools:
            return MCPTrustDecision(False, "mcp.tool_not_allowed", "MCP tool is outside the approved allowlist")
        tool = manifest.tool_by_name(tool_name)
        if tool is None:
            return MCPTrustDecision(False, "mcp.tool_missing_from_manifest", "MCP tool is missing from manifest")
        approved_effect = record.approved_tool_effects.get(tool_name)
        if approved_effect is None or not _scope_allows(record.permission_scope, approved_effect):
            return MCPTrustDecision(False, "mcp.scope_violation", "MCP tool side-effect class exceeds approved permission scope")
        scan = self._scanner.scan_text(
            manifest.descriptor_text(),
            subject=TrustScanSubject.MCP_DESCRIPTOR,
            source_path=f"mcp:{server_id}",
        )
        if scan.verdict is TrustScanVerdict.BLOCK:
            rules = ",".join(finding.rule_id for finding in scan.findings)
            return MCPTrustDecision(False, "mcp.descriptor_injection", f"MCP descriptor rejected: {rules}")
        return MCPTrustDecision(True, "mcp.trusted_tool_allowed", "MCP tool is approved for this server")

    def trusted_descriptors_for_planner(self, *, server_id: str, manifest: MCPServerManifest) -> tuple[MCPToolDescriptor, ...]:
        exposed: list[MCPToolDescriptor] = []
        for tool in manifest.tools:
            decision = self.validate_tool_call(server_id=server_id, manifest=manifest, tool_name=tool.name)
            if decision.allowed:
                exposed.append(tool)
        return tuple(exposed)


class MCPAutoloadGuard:
    def __init__(self, *, workspace_root: str | Path) -> None:
        self._workspace_root = Path(workspace_root).resolve()

    def evaluate_autoload_path(self, manifest_path: str | Path) -> MCPTrustDecision:
        candidate = Path(manifest_path).resolve(strict=False)
        try:
            candidate.relative_to(self._workspace_root)
        except ValueError:
            return MCPTrustDecision(False, "mcp.autoload.outside_workspace", "external MCP manifests require explicit approval", True)
        return MCPTrustDecision(False, "mcp.autoload.cloned_repo_denied", "MCP servers bundled in cloned repositories never auto-load", True)


class MCPConfigIngestionGuard:
    def __init__(self, *, workspace_root: str | Path, scanner: ConfigTrustScanner) -> None:
        self._autoload = MCPAutoloadGuard(workspace_root=workspace_root)
        self._scanner = scanner

    def deny_autoload_path(self, manifest_path: str | Path) -> MCPTrustDecision:
        return self._autoload.evaluate_autoload_path(manifest_path)

    def scan_manifest_path(self, manifest_path: str | Path) -> MCPTrustDecision:
        path = Path(manifest_path)
        if not path.is_file():
            return MCPTrustDecision(
                False,
                "injection.unscannable_path",
                f"MCP config path is not a readable file: {path.as_posix()}",
            )
        text = path.read_text(encoding="utf-8", errors="replace")
        return self.scan_manifest_text(text, source_path=str(path))

    def scan_manifest_text(self, text: str, *, source_path: str) -> MCPTrustDecision:
        scan = self._scanner.scan_text(text, subject=TrustScanSubject.CONFIG_FILE, source_path=source_path)
        if not scan.allowed:
            rules = ",".join(finding.rule_id for finding in scan.findings)
            return MCPTrustDecision(False, "mcp.config_injection", f"MCP config rejected: {rules}")
        return MCPTrustDecision(True, "mcp.config_scan_clean", "MCP config may proceed to explicit registration")


class MCPDescriptorExposureGuard:
    def __init__(self, *, registry: MCPTrustRegistry) -> None:
        self._registry = registry

    def expose_trusted_descriptors(self, *, server_id: str, manifest: MCPServerManifest) -> tuple[MCPToolDescriptor, ...]:
        return self._registry.trusted_descriptors_for_planner(server_id=server_id, manifest=manifest)


def _secret_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validate_permission_scope(permission_scope: str) -> None:
    if permission_scope not in _PERMISSION_SCOPE_LIMITS:
        raise MCPTrustError(f"mcp.unknown_permission_scope: {permission_scope}")


def _effective_side_effect_class(tool: MCPToolDescriptor) -> str:
    declared = _normalize_side_effect_class(tool.side_effect_class)
    derived = _derive_side_effect_class(tool)
    return max((declared, derived), key=lambda effect: _SIDE_EFFECT_RANK[effect])


def _normalize_side_effect_class(side_effect_class: str) -> str:
    normalized = side_effect_class.lower().strip()
    if normalized not in _SIDE_EFFECT_RANK:
        raise MCPTrustError(f"mcp.unknown_side_effect_class: {side_effect_class}")
    return normalized


def _derive_side_effect_class(tool: MCPToolDescriptor) -> str:
    haystack = " ".join(
        (
            tool.name,
            tool.description,
            json.dumps(tool.input_schema, sort_keys=True),
        )
    ).lower()
    if any(hint in haystack for hint in _WRITE_HINTS):
        return "write"
    if any(hint in haystack for hint in _NETWORK_HINTS):
        return "network"
    return "read"


def _scope_allows(permission_scope: str, side_effect_class: str) -> bool:
    _validate_permission_scope(permission_scope)
    return _SIDE_EFFECT_RANK[side_effect_class] <= _SIDE_EFFECT_RANK[_PERMISSION_SCOPE_LIMITS[permission_scope]]
