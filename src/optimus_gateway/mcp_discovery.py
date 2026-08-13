"""Complete, bounded MCP tools discovery for Gateway-owned profiles."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from time import monotonic
from typing import Protocol

from optimus_gateway.mcp_models import (
    MCPDiscoverRequest,
    MCPDiscoverResponse,
    MCPToolDescriptor,
    compute_manifest_hash,
    namespace_tool_name,
)
from optimus_gateway.mcp_profiles import MCPProfile, MCPProfileRegistry, MCPProfileState

MCP_PROTOCOL_FLOOR = "2026-07-28"
_PROTOCOL_VERSION = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TRANSIENT_ERRORS = (ConnectionError, TimeoutError, OSError)


class MCPDiscoveryError(ValueError):
    """Raised when discovery cannot produce a complete approvable manifest."""

    def __init__(self, disposition: str, detail: str = "") -> None:
        self.disposition = disposition
        self.detail = detail
        super().__init__(f"{disposition}: {detail}" if detail else disposition)


class MCPTransport(Protocol):
    def server_discover(self, *, protocol_version: str, client_meta: dict[str, object]) -> dict[str, object]: ...

    def tools_list(
        self, *, cursor: str | None, protocol_version: str, client_meta: dict[str, object]
    ) -> dict[str, object]: ...


@dataclass(frozen=True)
class CompleteToolSet:
    descriptors: tuple[MCPToolDescriptor, ...]
    protocol_version: str
    unmatched_allowlist: tuple[str, ...]


class MCPDiscoveryPaginator:
    def __init__(
        self,
        *,
        max_pages: int = 100,
        max_tools: int = 1000,
        max_descriptor_bytes: int = 1_048_576,
        retry_attempts: int = 3,
        clock=monotonic,
    ) -> None:
        self.max_pages = max_pages
        self.max_tools = max_tools
        self.max_descriptor_bytes = max_descriptor_bytes
        self.retry_attempts = retry_attempts
        self.clock = clock

    def collect_tools(self, *, transport: MCPTransport, profile: MCPProfile) -> CompleteToolSet:
        started = self.clock()
        client_meta = {
            "name": "optimus-gateway",
            "version": "1.0",
            "capabilities": {"tools": {}},
        }
        server_info = self._with_retries(
            lambda: transport.server_discover(protocol_version=MCP_PROTOCOL_FLOOR, client_meta=client_meta),
            phase="server/discover",
        )
        protocol_version = self._validate_server_discover(server_info)

        descriptors: list[MCPToolDescriptor] = []
        seen_names: set[str] = set()
        seen_cursors: set[str] = set()
        cursor: str | None = None
        page_count = 0
        descriptor_bytes = 0

        while True:
            if page_count >= min(self.max_pages, profile.limits.max_pages):
                raise MCPDiscoveryError("mcp.discovery_budget_exceeded", "page limit")
            if self.clock() - started > profile.limits.max_elapsed_seconds:
                raise MCPDiscoveryError("mcp.discovery_budget_exceeded", "elapsed-time limit")

            page = self._with_retries(
                lambda cursor=cursor: transport.tools_list(
                    cursor=cursor,
                    protocol_version=protocol_version,
                    client_meta=client_meta,
                ),
                phase="tools/list",
            )
            page_count += 1
            page_tools, next_cursor = self._validate_page(page, cursor=cursor)

            for raw_tool in page_tools:
                descriptor_bytes += self._descriptor_size(raw_tool)
                if descriptor_bytes > min(self.max_descriptor_bytes, profile.limits.max_descriptor_bytes):
                    raise MCPDiscoveryError("mcp.discovery_budget_exceeded", "descriptor-byte limit")
                descriptor = self._descriptor_from_tool(raw_tool)
                if descriptor.name in seen_names:
                    raise MCPDiscoveryError("mcp.discovery_cursor_invalid", "duplicate tool name")
                seen_names.add(descriptor.name)
                if len(seen_names) > min(self.max_tools, profile.limits.max_tools):
                    raise MCPDiscoveryError("mcp.discovery_budget_exceeded", "tool limit")
                if descriptor.name in profile.upstream_allowlist:
                    descriptors.append(descriptor)

            if next_cursor is None:
                break
            if next_cursor in seen_cursors:
                raise MCPDiscoveryError("mcp.discovery_cursor_invalid", "repeated cursor")
            seen_cursors.add(next_cursor)
            cursor = next_cursor

        unmatched = tuple(name for name in profile.upstream_allowlist if name not in seen_names)
        return CompleteToolSet(
            descriptors=tuple(descriptors),
            protocol_version=protocol_version,
            unmatched_allowlist=unmatched,
        )

    def _with_retries(self, operation, *, phase: str) -> dict[str, object]:
        for attempt in range(self.retry_attempts):
            try:
                result = operation()
                if not isinstance(result, dict):
                    raise MCPDiscoveryError("mcp.discovery_malformed", f"{phase} must return an object")
                return result
            except MCPDiscoveryError:
                raise
            except _TRANSIENT_ERRORS as exc:
                if attempt == self.retry_attempts - 1:
                    raise MCPDiscoveryError("mcp.discovery_transient_failure", f"{phase} exhausted retries") from exc
        raise MCPDiscoveryError("mcp.discovery_transient_failure", f"{phase} exhausted retries")

    @staticmethod
    def _validate_server_discover(server_info: dict[str, object]) -> str:
        protocol_version = MCPDiscoveryPaginator._normalize_protocol_version(server_info)
        capabilities = server_info.get("capabilities")
        if not isinstance(capabilities, dict) or "tools" not in capabilities:
            raise MCPDiscoveryError("mcp.tools_capability_missing")
        return protocol_version

    @staticmethod
    def _normalize_protocol_version(server_info: dict[str, object]) -> str:
        singular = server_info.get("protocolVersion")
        supported = server_info.get("supportedVersions")
        if supported is not None:
            selected = MCPDiscoveryPaginator._select_supported_version(supported)
            if singular is not None and singular != selected:
                raise MCPDiscoveryError("mcp.protocol_version_unsupported")
            return selected
        if not isinstance(singular, str) or _PROTOCOL_VERSION.fullmatch(singular) is None:
            raise MCPDiscoveryError("mcp.protocol_version_unsupported")
        if singular < MCP_PROTOCOL_FLOOR:
            raise MCPDiscoveryError("mcp.protocol_version_unsupported")
        return singular

    @staticmethod
    def _select_supported_version(supported: object) -> str:
        if not isinstance(supported, list) or not supported:
            raise MCPDiscoveryError("mcp.protocol_version_unsupported")
        seen: set[str] = set()
        for item in supported:
            if not isinstance(item, str) or _PROTOCOL_VERSION.fullmatch(item) is None:
                raise MCPDiscoveryError("mcp.protocol_version_unsupported")
            if item in seen:
                raise MCPDiscoveryError("mcp.protocol_version_unsupported")
            seen.add(item)
        if MCP_PROTOCOL_FLOOR not in seen:
            raise MCPDiscoveryError("mcp.protocol_version_unsupported")
        return MCP_PROTOCOL_FLOOR

    @staticmethod
    def _validate_page(page: dict[str, object], *, cursor: str | None) -> tuple[list[object], str | None]:
        tools = page.get("tools")
        if not isinstance(tools, list):
            raise MCPDiscoveryError("mcp.discovery_malformed", "tools/list tools must be an array")
        next_cursor = page.get("nextCursor")
        if next_cursor is not None and (not isinstance(next_cursor, str) or not next_cursor):
            raise MCPDiscoveryError("mcp.discovery_cursor_invalid", "nextCursor must be a non-empty string")
        if cursor is not None and next_cursor == cursor:
            raise MCPDiscoveryError("mcp.discovery_cursor_invalid", "cursor did not advance")
        return tools, next_cursor

    @staticmethod
    def _descriptor_size(raw_tool: object) -> int:
        try:
            return len(json.dumps(raw_tool, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise MCPDiscoveryError("mcp.discovery_invalid_definition", "tool is not JSON-compatible") from exc

    @staticmethod
    def _descriptor_from_tool(raw_tool: object) -> MCPToolDescriptor:
        if not isinstance(raw_tool, dict):
            raise MCPDiscoveryError("mcp.discovery_invalid_definition", "tool definition must be an object")
        name = raw_tool.get("name")
        input_schema = raw_tool.get("inputSchema")
        if not isinstance(name, str) or not name.strip() or not isinstance(input_schema, dict):
            raise MCPDiscoveryError("mcp.discovery_invalid_definition", "tool name/inputSchema is invalid")
        description = raw_tool.get("description", "")
        annotations = raw_tool.get("annotations", {})
        if not isinstance(description, str) or not isinstance(annotations, dict):
            raise MCPDiscoveryError("mcp.discovery_invalid_definition", "description/annotations is invalid")
        MCPDiscoveryPaginator._validate_headers(annotations)
        side_effect_class = annotations.get("side_effect_class", "read")
        if not isinstance(side_effect_class, str) or side_effect_class not in {"read", "network", "write"}:
            raise MCPDiscoveryError("mcp.discovery_invalid_definition", "side effect class is invalid")
        try:
            return MCPToolDescriptor(
                name=name,
                description=description,
                input_schema=input_schema,
                annotations=annotations,
                side_effect_class=side_effect_class,
            )
        except ValueError as exc:
            raise MCPDiscoveryError("mcp.discovery_invalid_definition", str(exc)) from exc

    @staticmethod
    def _validate_headers(annotations: dict[str, object]) -> None:
        headers = annotations.get("x-mcp-header")
        if headers is None:
            return
        if not isinstance(headers, dict):
            raise MCPDiscoveryError("mcp.discovery_invalid_header", "x-mcp-header must be an object")
        for name, value in headers.items():
            if (
                not isinstance(name, str)
                or not name.strip()
                or not isinstance(value, str)
                or not value.strip()
                or name.lower().startswith("mcp-param-")
            ):
                raise MCPDiscoveryError("mcp.discovery_invalid_header", "invalid x-mcp-header requirement")


class MCPDiscoveryBroker:
    def __init__(self, *, paginator: MCPDiscoveryPaginator | None = None) -> None:
        self.paginator = paginator or MCPDiscoveryPaginator()

    def discover(self, *, request: MCPDiscoverRequest, registry: MCPProfileRegistry, connection_manager) -> MCPDiscoverResponse:
        admission = registry.for_discovery(request)
        if not admission.accepted or admission.profile is None:
            raise MCPDiscoveryError(admission.disposition)
        profile = admission.profile
        try:
            complete = self.paginator.collect_tools(
                transport=connection_manager.open_for(profile),
                profile=profile,
            )
        except MCPDiscoveryError as exc:
            if profile.state == MCPProfileState.ACTIVE:
                registry.mark_stale(profile_id=profile.profile_id, revision=profile.revision, reason=exc.disposition)
            raise

        descriptors = tuple(
            descriptor.model_copy(
                update={"name": namespace_tool_name(profile_id=profile.profile_id, tool_name=descriptor.name)}
            )
            for descriptor in complete.descriptors
        )
        response = MCPDiscoverResponse(
            profile_id=profile.profile_id,
            profile_revision=profile.revision,
            transport=profile.transport,
            protocol_version=complete.protocol_version,
            descriptors=descriptors,
            unmatched_allowlist=complete.unmatched_allowlist,
            manifest_hash="0" * 64,
            freshness="fresh",
            disposition="mcp.discover.complete",
        )
        manifest_hash = compute_manifest_hash(response)
        if profile.manifest_hash is None:
            freshness = "fresh"
            disposition = "mcp.discover.complete"
        elif manifest_hash == profile.manifest_hash:
            freshness = "unchanged"
            disposition = "mcp.discover.unchanged"
        else:
            registry.mark_stale(profile_id=profile.profile_id, revision=profile.revision, reason="manifest drift")
            freshness = "stale"
            disposition = "mcp.discover.drift"
        return response.model_copy(update={"manifest_hash": manifest_hash, "freshness": freshness, "disposition": disposition})


__all__ = [
    "CompleteToolSet",
    "MCPDiscoveryBroker",
    "MCPDiscoveryError",
    "MCPDiscoveryPaginator",
    "MCPTransport",
]
