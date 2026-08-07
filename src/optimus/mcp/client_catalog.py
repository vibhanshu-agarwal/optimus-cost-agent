"""Client-supplied ACP MCP catalogs, call authorization, and one-call write approval."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from optimus.agent.models import AgentToolCall
from optimus.guardrails.mcp_trust import (
    SIDE_EFFECT_RANK,
    assemble_tool_descriptor_scan_text,
    normalize_side_effect_class,
)
from optimus.guardrails.pre_tool import PreToolGuard, PreToolRequest, PreToolResult, PreToolVerdict
from optimus.guardrails.prompt_injection import ConfigTrustScanner, TrustScanSubject, TrustScanVerdict
from optimus.mcp.client_config import ClientMcpSafeIdentity
from optimus.mcp.client_trust import ClientMcpDurableRecord, ClientMcpSessionLease, EffectCeiling
from optimus.runtime.modes import ExecutionMode, GenerationScope

MAX_CATALOG_PAGES = 100
MAX_CATALOG_TOOLS = 1000
MAX_DESCRIPTOR_BYTES = 16 * 1024
MAX_AGGREGATE_DESCRIPTOR_BYTES = 1 * 1024 * 1024
MAX_CATALOG_ELAPSED_SECONDS = 30.0

_TOKEN_SPLIT = re.compile(r"[^A-Za-z0-9]+")
_WRITE_NAME_TOKENS = frozenset(
    {
        "write",
        "delete",
        "remove",
        "create",
        "update",
        "mutate",
        "patch",
        "upload",
        "send",
        "execute",
        "run",
        "apply",
    }
)
_NETWORK_NAME_TOKENS = frozenset({"fetch", "download", "http", "url", "request"})

McpAuthority = Literal["legacy_manifest", "client_session"]
ToolAvailability = Literal["available", "ceiling_elevation_required"]


class ClientMcpCatalogError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __repr__(self) -> str:
        return f"ClientMcpCatalogError(code={self.code!r})"

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True)
class ClientMcpSoftDrop:
    name: str | None
    reason: str


@dataclass(frozen=True)
class ClientMcpCatalogTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    side_effect_class: str
    availability: ToolAvailability


@dataclass(frozen=True)
class ClientMcpCatalog:
    identity: ClientMcpSafeIdentity
    identity_fingerprint: str
    effect_ceiling: EffectCeiling
    tools: tuple[ClientMcpCatalogTool, ...]
    soft_drops: tuple[ClientMcpSoftDrop, ...] = ()

    def tool_by_name(self, name: str) -> ClientMcpCatalogTool | None:
        return next((tool for tool in self.tools if tool.name == name), None)


@dataclass(frozen=True)
class ClientMcpAuthorizeDecision:
    allowed: bool
    verdict: str
    rule_id: str
    reason: str
    effective_effect: str
    requires_human_approval: bool = False


@dataclass(frozen=True)
class ClientMcpOneCallApproval:
    token: str
    session_id: str
    identity_fingerprint: str
    tool_name: str
    arguments_digest: str


@dataclass(frozen=True)
class AgentMcpToolOutput:
    """Bounded, safe, untrusted in-memory MCP observation (Task 4 minimal)."""

    server_name: str
    tool_name: str
    text: str
    untrusted: bool = True


def arguments_digest(arguments: Mapping[str, Any] | None) -> str:
    payload = json.dumps(arguments or {}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def classify_client_tool_effect(
    *,
    name: str,
    annotations: Mapping[str, Any] | None = None,
    side_effect_class: str | None = None,
) -> str:
    """Restrictive max of declared metadata and tokenized tool-name evidence only."""
    declared = _declared_effect_from_metadata(annotations=annotations, side_effect_class=side_effect_class)
    named = _effect_from_tool_name(name)
    return max((declared, named), key=lambda effect: SIDE_EFFECT_RANK[effect])


def _declared_effect_from_metadata(
    *,
    annotations: Mapping[str, Any] | None,
    side_effect_class: str | None,
) -> str:
    effect = "read"
    if side_effect_class is not None:
        effect = normalize_side_effect_class(side_effect_class)
    if annotations:
        nested = annotations.get("side_effect_class")
        if isinstance(nested, str):
            effect = max((effect, normalize_side_effect_class(nested)), key=lambda e: SIDE_EFFECT_RANK[e])
        if annotations.get("destructiveHint") is True:
            effect = "write"
        elif annotations.get("openWorldHint") is True:
            effect = max((effect, "network"), key=lambda e: SIDE_EFFECT_RANK[e])
        elif annotations.get("readOnlyHint") is True:
            effect = max((effect, "read"), key=lambda e: SIDE_EFFECT_RANK[e])
    return effect


def _effect_from_tool_name(name: str) -> str:
    tokens = {token.lower() for token in _TOKEN_SPLIT.split(name) if token}
    if tokens & _WRITE_NAME_TOKENS:
        return "write"
    if tokens & _NETWORK_NAME_TOKENS:
        return "network"
    return "read"


def _availability_for(effect: str, ceiling: EffectCeiling) -> ToolAvailability:
    if effect == "write" and ceiling == "non_mutating":
        return "ceiling_elevation_required"
    return "available"


class ClientMcpDescriptorExposureAdapter:
    def __init__(self, *, scanner: ConfigTrustScanner | None = None) -> None:
        self._scanner = scanner or ConfigTrustScanner()

    def build(
        self,
        identity: ClientMcpSafeIdentity,
        raw_tools: Sequence[Mapping[str, Any]],
        *,
        effect_ceiling: EffectCeiling = "non_mutating",
        identity_fingerprint: str = "",
        elapsed_seconds: float = 0.0,
    ) -> ClientMcpCatalog:
        if elapsed_seconds > MAX_CATALOG_ELAPSED_SECONDS:
            raise ClientMcpCatalogError("CATALOG_BUDGET_EXCEEDED")
        if len(raw_tools) > MAX_CATALOG_PAGES:
            raise ClientMcpCatalogError("CATALOG_BUDGET_EXCEEDED")

        seen_cursors: set[str] = set()
        admitted: list[ClientMcpCatalogTool] = []
        soft_drops: list[ClientMcpSoftDrop] = []
        seen_names: set[str] = set()
        aggregate_bytes = 0

        for page in raw_tools:
            if not isinstance(page, Mapping):
                raise ClientMcpCatalogError("CATALOG_MALFORMED_PAGE")
            tools_raw = page.get("tools")
            if not isinstance(tools_raw, list):
                raise ClientMcpCatalogError("CATALOG_MALFORMED_PAGE")

            cursor = page.get("nextCursor")
            if isinstance(cursor, str) and cursor:
                if cursor in seen_cursors:
                    raise ClientMcpCatalogError("CATALOG_CURSOR_LOOP")
                seen_cursors.add(cursor)

            for raw in tools_raw:
                if not isinstance(raw, Mapping):
                    soft_drops.append(ClientMcpSoftDrop(name=None, reason="malformed_descriptor"))
                    continue
                name = raw.get("name")
                if not isinstance(name, str) or not name.strip():
                    soft_drops.append(ClientMcpSoftDrop(name=None, reason="malformed_descriptor"))
                    continue
                if name in seen_names:
                    raise ClientMcpCatalogError("CATALOG_DUPLICATE_TOOL")
                if len(seen_names) >= MAX_CATALOG_TOOLS:
                    raise ClientMcpCatalogError("CATALOG_BUDGET_EXCEEDED")
                seen_names.add(name)

                description = raw.get("description", "")
                if not isinstance(description, str):
                    soft_drops.append(ClientMcpSoftDrop(name=name, reason="malformed_descriptor"))
                    continue
                schema = raw.get("inputSchema", raw.get("input_schema", {}))
                if not isinstance(schema, dict):
                    soft_drops.append(ClientMcpSoftDrop(name=name, reason="malformed_descriptor"))
                    continue

                annotations = raw.get("annotations")
                if annotations is not None and not isinstance(annotations, dict):
                    soft_drops.append(ClientMcpSoftDrop(name=name, reason="malformed_descriptor"))
                    continue
                declared = raw.get("side_effect_class")
                if declared is not None and not isinstance(declared, str):
                    soft_drops.append(ClientMcpSoftDrop(name=name, reason="malformed_descriptor"))
                    continue

                try:
                    effect = classify_client_tool_effect(
                        name=name,
                        annotations=annotations,
                        side_effect_class=declared if isinstance(declared, str) else None,
                    )
                except Exception:
                    soft_drops.append(ClientMcpSoftDrop(name=name, reason="malformed_descriptor"))
                    continue

                scan_text = assemble_tool_descriptor_scan_text(
                    name=name,
                    description=description,
                    input_schema=schema,
                    side_effect_class=effect,
                )
                descriptor_bytes = len(scan_text.encode("utf-8"))
                if descriptor_bytes > MAX_DESCRIPTOR_BYTES:
                    raise ClientMcpCatalogError("CATALOG_BUDGET_EXCEEDED")
                aggregate_bytes += descriptor_bytes
                if aggregate_bytes > MAX_AGGREGATE_DESCRIPTOR_BYTES:
                    raise ClientMcpCatalogError("CATALOG_BUDGET_EXCEEDED")

                scan = self._scanner.scan_text(
                    scan_text,
                    subject=TrustScanSubject.MCP_DESCRIPTOR,
                    source_path=f"client-mcp:{identity.server_name}:{name}",
                )
                if scan.verdict is TrustScanVerdict.BLOCK:
                    rules = ",".join(finding.rule_id for finding in scan.findings) or "scanner_blocked"
                    soft_drops.append(ClientMcpSoftDrop(name=name, reason=rules))
                    continue

                admitted.append(
                    ClientMcpCatalogTool(
                        name=name,
                        description=description,
                        input_schema=dict(schema),
                        side_effect_class=effect,
                        availability=_availability_for(effect, effect_ceiling),
                    )
                )

        # Complete-or-absent: every discovered name counts toward the tool budget.
        if len(seen_names) > MAX_CATALOG_TOOLS:
            raise ClientMcpCatalogError("CATALOG_BUDGET_EXCEEDED")
        if len(admitted) > MAX_CATALOG_TOOLS:
            raise ClientMcpCatalogError("CATALOG_BUDGET_EXCEEDED")

        return ClientMcpCatalog(
            identity=identity,
            identity_fingerprint=identity_fingerprint,
            effect_ceiling=effect_ceiling,
            tools=tuple(admitted),
            soft_drops=tuple(soft_drops),
        )


class McpPermissionBroker(ABC):
    @abstractmethod
    def request_write(self, request: PreToolRequest) -> ClientMcpOneCallApproval | None:
        """Request a one-call write approval; ACP concrete impl is Task 6."""


class ClientMcpCallAuthorizer:
    def __init__(
        self,
        *,
        catalog: ClientMcpCatalog,
        lease: ClientMcpSessionLease | None = None,
        durable: ClientMcpDurableRecord | None = None,
    ) -> None:
        self._catalog = catalog
        self._lease = lease
        self._durable = durable
        self._tokens: dict[str, ClientMcpOneCallApproval] = {}
        self._consumed: set[str] = set()

    @property
    def catalog(self) -> ClientMcpCatalog:
        return self._catalog

    def issue_one_call_approval(
        self,
        *,
        session_id: str,
        tool_name: str,
        arguments: Mapping[str, Any] | None,
    ) -> ClientMcpOneCallApproval:
        approval = ClientMcpOneCallApproval(
            token=secrets.token_urlsafe(24),
            session_id=session_id,
            identity_fingerprint=self._catalog.identity_fingerprint,
            tool_name=tool_name,
            arguments_digest=arguments_digest(arguments),
        )
        self._tokens[approval.token] = approval
        return approval

    def authorize(self, request: PreToolRequest) -> ClientMcpAuthorizeDecision:
        ceiling = self._resolve_ceiling()
        if ceiling is None:
            return ClientMcpAuthorizeDecision(
                allowed=False,
                verdict="HOLD",
                rule_id="mcp.client.lease_required",
                reason="client MCP call requires an active session lease or durable ceiling",
                effective_effect="write",
                requires_human_approval=True,
            )

        lease_fp = None
        if self._lease is not None:
            if request.session_id != self._lease.session_id:
                return ClientMcpAuthorizeDecision(
                    allowed=False,
                    verdict="BLOCK",
                    rule_id="mcp.client.session_mismatch",
                    reason="client MCP lease session does not match request",
                    effective_effect="write",
                )
            lease_fp = self._lease.identity_fingerprint
        elif self._durable is not None:
            lease_fp = self._durable.identity_fingerprint

        if lease_fp != self._catalog.identity_fingerprint:
            return ClientMcpAuthorizeDecision(
                allowed=False,
                verdict="BLOCK",
                rule_id="mcp.client.identity_mismatch",
                reason="client MCP catalog identity does not match lease/durable fingerprint",
                effective_effect="write",
            )

        tool_name = request.mcp_tool_name
        if not tool_name:
            return ClientMcpAuthorizeDecision(
                allowed=False,
                verdict="HOLD",
                rule_id="mcp.client.missing_tool",
                reason="client MCP call requires a tool name",
                effective_effect="write",
                requires_human_approval=True,
            )
        tool = self._catalog.tool_by_name(tool_name)
        if tool is None:
            return ClientMcpAuthorizeDecision(
                allowed=False,
                verdict="BLOCK",
                rule_id="mcp.client.tool_not_in_catalog",
                reason="client MCP tool is not in the identity-bound catalog",
                effective_effect="write",
            )

        effect = tool.side_effect_class
        if effect == "write" and ceiling == "non_mutating":
            return ClientMcpAuthorizeDecision(
                allowed=False,
                verdict="HOLD",
                rule_id="mcp.client.ceiling_elevation_required",
                reason="write-classified client MCP tool requires durable ceiling elevation",
                effective_effect=effect,
                requires_human_approval=True,
            )

        if effect in {"read", "network"}:
            return ClientMcpAuthorizeDecision(
                allowed=True,
                verdict="ALLOW",
                rule_id="mcp.client.non_mutating_allowed",
                reason="client MCP read/network call permitted under active lease",
                effective_effect=effect,
            )

        # write under side_effect_eligible: require bound one-call token
        token = request.mcp_one_call_approval
        if not token:
            return ClientMcpAuthorizeDecision(
                allowed=False,
                verdict="HOLD",
                rule_id="mcp.client.write_one_call_required",
                reason="write-classified client MCP call requires a one-call approval token",
                effective_effect=effect,
                requires_human_approval=True,
            )
        return self._consume_one_call(request, token=token, tool_name=tool_name, effect=effect)

    def _resolve_ceiling(self) -> EffectCeiling | None:
        if self._lease is not None:
            return self._lease.effect_ceiling
        if self._durable is not None:
            return self._durable.effect_ceiling
        return None

    def _consume_one_call(
        self,
        request: PreToolRequest,
        *,
        token: str,
        tool_name: str,
        effect: str,
    ) -> ClientMcpAuthorizeDecision:
        if token in self._consumed:
            return ClientMcpAuthorizeDecision(
                allowed=False,
                verdict="BLOCK",
                rule_id="mcp.client.one_call_replay",
                reason="one-call approval token already consumed",
                effective_effect=effect,
            )
        approval = self._tokens.get(token)
        if approval is None:
            return ClientMcpAuthorizeDecision(
                allowed=False,
                verdict="BLOCK",
                rule_id="mcp.client.one_call_unknown",
                reason="one-call approval token is not recognized",
                effective_effect=effect,
            )
        if approval.session_id != (request.session_id or ""):
            return ClientMcpAuthorizeDecision(
                allowed=False,
                verdict="BLOCK",
                rule_id="mcp.client.one_call_session_mismatch",
                reason="one-call approval token session mismatch",
                effective_effect=effect,
            )
        if approval.identity_fingerprint != self._catalog.identity_fingerprint:
            return ClientMcpAuthorizeDecision(
                allowed=False,
                verdict="BLOCK",
                rule_id="mcp.client.one_call_identity_mismatch",
                reason="one-call approval token identity mismatch",
                effective_effect=effect,
            )
        if approval.tool_name != tool_name:
            return ClientMcpAuthorizeDecision(
                allowed=False,
                verdict="BLOCK",
                rule_id="mcp.client.one_call_tool_mismatch",
                reason="one-call approval token tool mismatch",
                effective_effect=effect,
            )
        digest = arguments_digest(request.mcp_arguments)
        if approval.arguments_digest != digest:
            return ClientMcpAuthorizeDecision(
                allowed=False,
                verdict="BLOCK",
                rule_id="mcp.client.one_call_arguments_mismatch",
                reason="one-call approval token arguments mismatch",
                effective_effect=effect,
            )
        self._consumed.add(token)
        self._tokens.pop(token, None)
        return ClientMcpAuthorizeDecision(
            allowed=True,
            verdict="ALLOW",
            rule_id="mcp.client.write_one_call_allowed",
            reason="write-classified client MCP call permitted with one-call approval",
            effective_effect=effect,
        )


class ClientMcpToolService:
    """Non-serializable session runtime: authorize via PreToolGuard then return safe output + audit call."""

    __slots__ = ("_guard", "_catalog", "_authorizer")

    def __init__(
        self,
        *,
        guard: PreToolGuard,
        catalog: ClientMcpCatalog,
        authorizer: ClientMcpCallAuthorizer,
    ) -> None:
        object.__setattr__(self, "_guard", guard)
        object.__setattr__(self, "_catalog", catalog)
        object.__setattr__(self, "_authorizer", authorizer)

    def __setattr__(self, name: str, value: object) -> None:
        raise TypeError("client mcp tool service is immutable")

    def __delattr__(self, name: str) -> None:
        raise TypeError("client mcp tool service is immutable")

    def __getattribute__(self, name: str) -> object:
        if name == "__dict__":
            raise TypeError("client mcp tool service is not serializable")
        return object.__getattribute__(self, name)

    def _dispatch(self, tool_name: str, arguments: dict[str, Any]) -> str:
        raise NotImplementedError("ClientMcpToolService subclasses must implement _dispatch")

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> tuple[AgentMcpToolOutput, AgentToolCall]:
        from optimus.guardrails.permissions import ToolSurface

        catalog: ClientMcpCatalog = object.__getattribute__(self, "_catalog")
        guard: PreToolGuard = object.__getattribute__(self, "_guard")
        authorizer: ClientMcpCallAuthorizer = object.__getattribute__(self, "_authorizer")
        lease = authorizer._lease
        request = PreToolRequest(
            run_id="client-mcp-service",
            session_id=None if lease is None else lease.session_id,
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.MCP,
            action=f"{catalog.identity.server_name}.{tool_name}",
            generation_scope=GenerationScope.INLINE_SNIPPET,
            approval_granted=False,
            mcp_authority="client_session",
            mcp_server_id=catalog.identity.server_name,
            mcp_tool_name=tool_name,
            mcp_arguments=arguments,
        )
        result: PreToolResult = guard.check(request)
        if result.verdict is not PreToolVerdict.ALLOW:
            return (
                AgentMcpToolOutput(
                    server_name=catalog.identity.server_name,
                    tool_name=tool_name,
                    text=f"unavailable:{result.rule_id}",
                ),
                AgentToolCall(
                    tool_name=f"mcp_call:{tool_name}",
                    summary=result.reason,
                    authorization_outcome=result.verdict.value,
                ),
            )
        text = type(self)._dispatch(self, tool_name, arguments)
        return (
            AgentMcpToolOutput(
                server_name=catalog.identity.server_name,
                tool_name=tool_name,
                text=text,
            ),
            AgentToolCall(
                tool_name=f"mcp_call:{tool_name}",
                summary=f"authorized client mcp call: {tool_name}",
                authorization_outcome="ALLOW",
            ),
        )
