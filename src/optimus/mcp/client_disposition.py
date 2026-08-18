"""Shared ClientMcpDisposition seam for session/new (and future session/load)."""

from __future__ import annotations

import asyncio
import secrets
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

from optimus.acp.shapes import build_client_mcp_permission_params
from optimus.guardrails.pre_tool import PreToolGuard, PreToolRequest
from optimus.mcp.client_catalog import (
    ClientMcpCallAuthorizer,
    ClientMcpCatalogError,
    ClientMcpDescriptorExposureAdapter,
    ClientMcpOneCallApproval,
    ClientMcpSessionService,
    ClientMcpToolService,
    McpPermissionBroker,
)
from optimus.mcp.client_config import (
    ClientMcpConfigError,
    ClientMcpConfigNormalizer,
    ClientMcpRuntimeCapability,
    ClientMcpSafeIdentity,
)
from optimus.mcp.client_sdk import ClientMcpSdkAdapter
from optimus.mcp.client_supervisor import MCPAsyncSupervisor
from optimus.mcp.client_trust import (
    ClientMcpDurableRecord,
    ClientMcpLeaseAuthority,
    ClientMcpSessionLease,
    compute_identity_fingerprint,
)
from optimus.mcp.local_ipc import PendingClientMcpCandidate, PendingClientMcpCandidateEndpoint

PermissionOutcome = Literal["allow", "reject", "timeout", "outbound_failure"]
RequestPermissionFn = Callable[[dict[str, Any]], Awaitable[PermissionOutcome | str | dict[str, Any]]]


@dataclass
class ClientMcpSessionState:
    """Opaque per-session client-MCP disposition; never serialized onto ACP payloads."""

    session_id: str
    _servers: dict[str, _ServerEntry] = field(default_factory=dict)
    _tool_service: ClientMcpSessionService = field(default_factory=ClientMcpSessionService)
    _closed: bool = False
    _close_hooks: list[Callable[[], None]] = field(default_factory=list)
    _capabilities: list[ClientMcpRuntimeCapability] = field(default_factory=list)

    @property
    def tool_service(self) -> ClientMcpSessionService:
        return self._tool_service

    def server_names(self) -> tuple[str, ...]:
        return tuple(self._servers)

    def is_leased(self, server_name: str) -> bool:
        entry = self._servers.get(server_name)
        return entry is not None and entry.lease is not None

    def is_unavailable(self, server_name: str) -> bool:
        entry = self._servers.get(server_name)
        return entry is not None and entry.lease is None and entry.outcome == "unavailable"

    def lease_for(self, server_name: str) -> ClientMcpSessionLease | None:
        entry = self._servers.get(server_name)
        return None if entry is None else entry.lease

    def durable_for(self, server_name: str) -> ClientMcpDurableRecord | None:
        entry = self._servers.get(server_name)
        return None if entry is None else entry.durable

    def register_close_hook(self, hook: Callable[[], None]) -> None:
        self._close_hooks.append(hook)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for hook in list(self._close_hooks):
            hook()
        self._capabilities.clear()


@dataclass
class _ServerEntry:
    server_name: str
    outcome: Literal["leased", "unavailable"]
    lease: ClientMcpSessionLease | None = None
    durable: ClientMcpDurableRecord | None = None
    identity_fingerprint: str | None = None


@dataclass
class ClientMcpRuntime:
    """Process-lifetime client-MCP wiring owned by bootstrap / AcpStreamServer."""

    disposition: ClientMcpDisposition
    supervisor: MCPAsyncSupervisor
    sdk_adapter: ClientMcpSdkAdapter | None = None
    mcp_http_enabled: bool = False
    mcp_sse_enabled: bool = False
    candidate_endpoint: PendingClientMcpCandidateEndpoint | None = None

    def close(self) -> None:
        if self.sdk_adapter is not None:
            self.sdk_adapter.close_all()
        if self.candidate_endpoint is not None:
            self.candidate_endpoint.close()
        self.supervisor.close()


class ClientMcpDisposition:
    """Normalize + permission-bound disposition without opening transport."""

    def __init__(
        self,
        *,
        normalizer: ClientMcpConfigNormalizer,
        lease_authority: ClientMcpLeaseAuthority,
        hmac_key: bytes,
        controlled_path: str,
        workspace_digest: str,
        permission_timeout_seconds: float = 30.0,
        candidate_endpoint: PendingClientMcpCandidateEndpoint | None = None,
    ) -> None:
        self._normalizer = normalizer
        self._lease_authority = lease_authority
        self._hmac_key = hmac_key
        self._controlled_path = controlled_path
        self._workspace_digest = workspace_digest
        self._permission_timeout_seconds = permission_timeout_seconds
        self._candidate_endpoint = candidate_endpoint

    async def disposition_for_new_session(
        self,
        session_id: str,
        cwd: Path,
        entries: Sequence[Mapping[str, object]] | None,
        request_permission: RequestPermissionFn,
    ) -> ClientMcpSessionState:
        del cwd  # reserved for future load/cwd binding; workspace_digest is authoritative now
        state = ClientMcpSessionState(session_id=session_id)
        if entries is None or len(entries) == 0:
            return state

        capabilities = self._normalizer.normalize(
            entries,
            workspace_root=Path("."),
            controlled_path=self._controlled_path,
            hmac_key=self._hmac_key,
        )
        state._capabilities.extend(capabilities)

        for capability in capabilities:
            identity = capability.safe_identity
            fingerprint = compute_identity_fingerprint(identity, hmac_key=self._hmac_key)
            candidate_id = uuid.uuid4().hex
            if self._candidate_endpoint is not None:
                view = capability.safe_view()
                candidate_id = self._candidate_endpoint.publish(
                    PendingClientMcpCandidate(
                        workspace_digest=self._workspace_digest,
                        session_id=session_id,
                        identity=identity,
                        rendered_fingerprint=fingerprint,
                        provenance=view.provenance,
                        scanner_rule_ids=view.scanner_rule_ids,
                    )
                )
            params = build_client_mcp_permission_params(
                session_id=session_id,
                candidate_id=candidate_id,
                server_name=identity.server_name,
                transport=identity.transport,
                identity_fingerprint=fingerprint,
            )
            outcome = await self._await_permission(request_permission, params)
            if outcome == "allow":
                lease = self._lease_authority.acquire_allow_once(
                    session_id=session_id,
                    workspace_digest=self._workspace_digest,
                    identity=identity,
                    identity_fingerprint=fingerprint,
                )
                durable = self._lease_authority.lookup_durable(
                    self._workspace_digest,
                    identity.server_name,
                    fingerprint,
                )
                if durable is not None:
                    lease = replace(lease, effect_ceiling=durable.effect_ceiling)
                state._servers[identity.server_name] = _ServerEntry(
                    server_name=identity.server_name,
                    outcome="leased",
                    lease=lease,
                    durable=durable,
                    identity_fingerprint=fingerprint,
                )
            else:
                state._servers[identity.server_name] = _ServerEntry(
                    server_name=identity.server_name,
                    outcome="unavailable",
                    identity_fingerprint=fingerprint,
                )
        return state

    def materialize_tool_service(
        self,
        state: ClientMcpSessionState,
        *,
        identity: ClientMcpSafeIdentity,
        raw_tools: Sequence[Mapping[str, object]],
        workspace_root: Path,
        elapsed_seconds: float = 0.0,
        service_cls: type[ClientMcpToolService] = ClientMcpToolService,
    ) -> ClientMcpToolService | None:
        """Register one identity-bound service after catalog scan/budget admission.

        Does not open transport or discover catalogs. Rejected, unavailable, and
        no-catalog paths leave the session registry unchanged.
        """
        server_name = identity.server_name
        if not state.is_leased(server_name):
            return None
        lease = state.lease_for(server_name)
        if lease is None:
            return None
        fingerprint = compute_identity_fingerprint(identity, hmac_key=self._hmac_key)
        if fingerprint != lease.identity_fingerprint:
            return None
        try:
            catalog = ClientMcpDescriptorExposureAdapter().build(
                identity,
                raw_tools,
                effect_ceiling=lease.effect_ceiling,
                identity_fingerprint=lease.identity_fingerprint,
                elapsed_seconds=elapsed_seconds,
            )
        except ClientMcpCatalogError:
            return None
        authorizer = ClientMcpCallAuthorizer(
            catalog=catalog,
            lease=lease,
            durable=state.durable_for(server_name),
        )
        guard = PreToolGuard.for_workspace(
            workspace_root=workspace_root,
            allowed_network_hosts=(),
            client_mcp_authorizer=authorizer,
        )
        service = service_cls(guard=guard, catalog=catalog, authorizer=authorizer)
        state.tool_service.register(service)
        return service

    async def _await_permission(
        self,
        request_permission: RequestPermissionFn,
        params: dict[str, Any],
    ) -> PermissionOutcome:
        try:
            raw = await asyncio.wait_for(
                request_permission(params),
                timeout=self._permission_timeout_seconds,
            )
        except TimeoutError:
            return "timeout"
        except Exception:
            return "outbound_failure"
        return _normalize_permission_outcome(raw)


def _normalize_permission_outcome(raw: PermissionOutcome | str | dict[str, Any]) -> PermissionOutcome:
    if isinstance(raw, str):
        if raw in {"allow", "reject", "timeout", "outbound_failure"}:
            return raw  # type: ignore[return-value]
        if raw in {"allow_once", "approve"}:
            return "allow"
        if raw in {"reject_once", "cancel", "cancelled"}:
            return "reject"
        return "reject"
    if isinstance(raw, dict):
        outcome = raw.get("outcome")
        if isinstance(outcome, dict):
            if outcome.get("outcome") == "cancelled":
                return "reject"
            if outcome.get("outcome") == "selected":
                option = outcome.get("optionId")
                if option in {"allow_once", "approve"}:
                    return "allow"
                return "reject"
        return "reject"
    return "reject"


class AcpMcpPermissionBroker(McpPermissionBroker):
    """Translate a HOLD write into one 30s-bounded allow_once/reject_once ACP round-trip."""

    def __init__(
        self,
        *,
        session_id: str,
        request_permission: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
        issue_approval: Callable[[PreToolRequest], ClientMcpOneCallApproval | None],
        timeout_seconds: float = 30.0,
        loop: asyncio.AbstractEventLoop | None = None,
        server_name: str = "client-mcp",
        transport: str = "stdio",
        identity_fingerprint: str = "",
    ) -> None:
        self._session_id = session_id
        self._request_permission = request_permission
        self._issue_approval = issue_approval
        self._timeout_seconds = timeout_seconds
        self._loop = loop
        self._server_name = server_name
        self._transport = transport
        self._identity_fingerprint = identity_fingerprint

    def request_write(self, request: PreToolRequest) -> ClientMcpOneCallApproval | None:
        params = build_client_mcp_permission_params(
            session_id=self._session_id,
            candidate_id=secrets.token_hex(8),
            server_name=request.mcp_server_id or self._server_name,
            transport=self._transport,
            identity_fingerprint=self._identity_fingerprint or "write-call",
            tool_name=request.mcp_tool_name,
            effect="write",
        )
        loop = self._loop
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

        async def _ask() -> dict[str, Any]:
            return await asyncio.wait_for(
                self._request_permission(params),
                timeout=self._timeout_seconds,
            )

        try:
            if loop is not None and loop.is_running():
                future = asyncio.run_coroutine_threadsafe(_ask(), loop)
                result = future.result(timeout=self._timeout_seconds + 1.0)
            else:
                result = asyncio.run(_ask())
        except Exception:
            return None

        if _normalize_permission_outcome(result) != "allow":
            return None
        return self._issue_approval(request)


__all__ = [
    "AcpMcpPermissionBroker",
    "ClientMcpDisposition",
    "ClientMcpRuntime",
    "ClientMcpSessionState",
    "ClientMcpConfigError",
]
