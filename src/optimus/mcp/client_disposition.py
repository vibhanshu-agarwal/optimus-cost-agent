"""Shared ClientMcpDisposition seam for session/new (and future session/load)."""

from __future__ import annotations

import asyncio
import secrets
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field, replace
from functools import partial
from pathlib import Path
from time import monotonic
from typing import Any, Literal, Protocol

from optimus.acp.shapes import build_client_mcp_permission_params
from optimus.guardrails.pre_tool import PreToolGuard, PreToolRequest
from optimus.mcp.client_catalog import (
    AdapterBackedClientMcpToolService,
    ClientMcpCallAuthorizer,
    ClientMcpCatalog,
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
from optimus.mcp.client_sdk import ClientMcpConnection, ClientMcpSdkAdapter
from optimus.mcp.client_supervisor import MCPAsyncSupervisor, MCPSupervisorState
from optimus.mcp.client_trust import (
    ClientMcpDurableRecord,
    ClientMcpLeaseAuthority,
    ClientMcpSessionLease,
    compute_identity_fingerprint,
)
from optimus.mcp.local_ipc import PendingClientMcpCandidate, PendingClientMcpCandidateEndpoint

PermissionOutcome = Literal["allow", "reject", "timeout", "outbound_failure"]
RequestPermissionFn = Callable[[dict[str, Any]], Awaitable[PermissionOutcome | str | dict[str, Any]]]


def run_close_hooks(hooks: tuple[Callable[[], None], ...]) -> tuple[str, ...]:
    failures: list[str] = []
    control_failure: BaseException | None = None
    for hook in hooks:
        try:
            hook()
        except BaseException as exc:
            failures.append("SESSION_CLOSE_FAILED")
            if not isinstance(exc, Exception) and control_failure is None:
                control_failure = exc
    if control_failure is not None:
        raise control_failure
    return tuple(failures)


class ClientMcpServiceFactory(Protocol):
    def __call__(
        self,
        *,
        guard: PreToolGuard,
        catalog: ClientMcpCatalog,
        authorizer: ClientMcpCallAuthorizer,
    ) -> ClientMcpToolService:
        ...


ClientMcpServiceFactoryBuilder = Callable[
    [ClientMcpSdkAdapter, ClientMcpConnection],
    ClientMcpServiceFactory,
]


@dataclass
class ClientMcpSessionState:
    """Opaque per-session client-MCP disposition; never serialized onto ACP payloads."""

    session_id: str
    _servers: dict[str, _ServerEntry] = field(default_factory=dict)
    _tool_service: ClientMcpSessionService = field(default_factory=ClientMcpSessionService)
    _closed: bool = False
    _close_hooks: list[Callable[[], None]] = field(default_factory=list)
    _capabilities: list[ClientMcpRuntimeCapability] = field(default_factory=list)
    _workspace_root: Path | None = None
    _record_close_failure: Callable[[], None] | None = field(default=None, repr=False)
    _open_peers: int = 0
    _suspending: bool = False
    suspended: bool = False
    _former_servers: dict[str, _ServerEntry] = field(default_factory=dict, repr=False)
    _resolver_adapter: ClientMcpSdkAdapter | None = field(default=None, repr=False)
    _candidate_cleanup_registered: bool = False

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

    def register_close_hook(self, hook: Callable[[], None], *, peer: bool = False) -> bool:
        if self._closed or self._suspending or self.suspended:
            hook()
            return False
        self._close_hooks.append(hook)
        self._open_peers += int(peer)
        return True

    def has_open_peer(self) -> bool:
        return self._open_peers > 0

    def own_candidate_cleanup(self, hook: Callable[[], None]) -> None:
        if self._closed:
            hook()
        elif not self._candidate_cleanup_registered:
            self._candidate_cleanup_registered = True
            self._close_hooks.append(hook)

    def has_leased_stdio_server(self) -> bool:
        return any(cap.safe_identity.transport == "stdio" and self.is_leased(cap.safe_identity.server_name)
                   for cap in self._capabilities)

    def _detach_hooks(self) -> tuple[Callable[[], None], ...]:
        hooks = tuple(self._close_hooks)
        self._close_hooks.clear()
        self._open_peers = 0
        self._candidate_cleanup_registered = False
        self._tool_service = self._tool_service.retire()
        return hooks

    def prepare_suspend(self) -> tuple[Callable[[], None], ...] | None:
        if self._closed or self._suspending or self.suspended or not self.has_open_peer():
            return None
        self._suspending = True
        self._former_servers = dict(self._servers)
        self._servers = {name: replace(entry, lease=None) for name, entry in self._servers.items()}
        return self._detach_hooks()

    def complete_suspend(self, failures: tuple[str, ...]) -> bool:
        if failures and self._record_close_failure is not None:
            self._record_close_failure()
        self._suspending = False
        self.suspended = not failures and not self._closed
        return self.suspended

    def restore_suspended(self) -> None:
        if not self._closed:
            self._servers = {name: replace(entry, lease=None) for name, entry in self._former_servers.items()}
            self._tool_service = self._tool_service.retire()
            self.suspended = True

    def prepare_close(self) -> tuple[Callable[[], None], ...]:
        if self._closed:
            return ()
        self._closed = True
        self.suspended = False
        self._former_servers.clear()
        self._capabilities.clear()
        self._servers.clear()
        self._resolver_adapter = None
        return self._detach_hooks()

    def complete_close(self, failures: tuple[str, ...]) -> None:
        if failures and self._record_close_failure is not None:
            self._record_close_failure()

    def _capability_for(self, server_name: str) -> ClientMcpRuntimeCapability | None:
        return next(
            (
                capability
                for capability in self._capabilities
                if capability.safe_identity.server_name == server_name
            ),
            None,
        )

    def close(self) -> None:
        hooks = self.prepare_close()
        try:
            failures = run_close_hooks(hooks)
        except BaseException:
            self.complete_close(("SESSION_CLOSE_FAILED",))
            raise
        self.complete_close(failures)


@dataclass
class _ServerEntry:
    server_name: str
    outcome: Literal["leased", "unavailable"]
    lease: ClientMcpSessionLease | None = None
    durable: ClientMcpDurableRecord | None = None
    identity_fingerprint: str | None = None


@dataclass(frozen=True)
class ClientMcpShutdownOutcome:
    """Aggregate result of ``ClientMcpRuntime.close()``.

    ``sdk_closed``, ``endpoint_closed`` and ``supervisor_closed`` record whether the
    respective stage calls returned normally; an absent endpoint counts as success.
    They do not independently prove that every connection or operating-system
    resource has closed. In particular, ``supervisor_closed=True`` can coexist with
    ``STOPPING``. ``complete`` additionally requires terminal ``DEAD`` and no ordinary
    stage failure recorded by this or any earlier close. Pending supervision without a
    stage exception is not a sticky failure and may complete on a later close.
    """

    sdk_closed: bool
    endpoint_closed: bool
    supervisor_closed: bool
    supervisor_state: MCPSupervisorState
    complete: bool


@dataclass
class ClientMcpRuntime:
    """Process-lifetime client-MCP wiring owned by bootstrap / AcpStreamServer."""

    disposition: ClientMcpDisposition
    supervisor: MCPAsyncSupervisor
    sdk_adapter: ClientMcpSdkAdapter
    mcp_http_enabled: bool = False
    mcp_sse_enabled: bool = False
    candidate_endpoint: PendingClientMcpCandidateEndpoint | None = None
    # Sticky record: once any close stage raises, this runtime can never again
    # report a clean shutdown without independently established recovery (which
    # this package does not provide). A still-pending supervisor does NOT set it.
    _stage_failure_recorded: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.sdk_adapter is None:
            raise ValueError("sdk_adapter is required")

    def close(self) -> ClientMcpShutdownOutcome:
        """Attempt every cleanup stage in order despite ordinary failures.

        Stages run SDK -> endpoint (when present) -> supervisor; each ordinary
        (`Exception`) failure is contained and recorded, and later stages are still
        attempted. Control-flow / BaseException still propagate. Returns an aggregate
        outcome that retains any failure across repeated calls.
        """
        sdk_closed = True
        try:
            self.sdk_adapter.close_all()
            if isinstance(self.sdk_adapter, ClientMcpSdkAdapter):
                sdk_closed = not self.sdk_adapter.pending_connections() and not self.sdk_adapter.close_failure_recorded
        except Exception:
            sdk_closed = False

        endpoint_closed = True
        if self.candidate_endpoint is not None:
            try:
                self.candidate_endpoint.close()
            except Exception:
                endpoint_closed = False

        supervisor_closed = True
        try:
            self.supervisor.close()
        except Exception:
            supervisor_closed = False
        supervisor_state = self.supervisor.state

        if not (sdk_closed and endpoint_closed and supervisor_closed):
            self._stage_failure_recorded = True
        if isinstance(self.disposition, ClientMcpDisposition) and self.disposition.close_failure_recorded:
            self._stage_failure_recorded = True
        complete = (not self._stage_failure_recorded) and (
            supervisor_state is MCPSupervisorState.DEAD
        )
        return ClientMcpShutdownOutcome(
            sdk_closed=sdk_closed,
            endpoint_closed=endpoint_closed,
            supervisor_closed=supervisor_closed,
            supervisor_state=supervisor_state,
            complete=complete,
        )


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
        self.close_failure_recorded = False
        self._cleanup_lock = asyncio.Lock()
        self._jobs: set[asyncio.Task[Any]] = set()

    def record_session_close_failure(self) -> None:
        self.close_failure_recorded = True

    async def run_blocking(self, operation: Callable[[], Any]) -> Any:
        """One off-loop lane; cancellation cannot abandon the underlying work."""
        async with self._cleanup_lock:
            job = asyncio.create_task(asyncio.to_thread(operation))
            self._jobs.add(job)
            cancelled = False
            try:
                while not job.done():
                    try:
                        await asyncio.shield(job)
                    except asyncio.CancelledError:
                        cancelled = True
                result = job.result()
                if cancelled:
                    raise asyncio.CancelledError
                return result
            finally:
                self._jobs.discard(job)

    async def drain(self) -> None:
        while self._jobs:
            for job in tuple(self._jobs):
                while not job.done():
                    try:
                        await asyncio.shield(job)
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        break
                self._jobs.discard(job)

    def _own_candidates(self, state: ClientMcpSessionState) -> None:
        endpoint = self._candidate_endpoint
        if endpoint is not None:
            session_id = state.session_id
            def retire() -> None:
                endpoint.retire_session(session_id)
            state.own_candidate_cleanup(retire)

    async def disposition_for_new_session(
        self,
        session_id: str,
        cwd: Path,
        entries: Sequence[Mapping[str, object]] | None,
        request_permission: RequestPermissionFn,
    ) -> ClientMcpSessionState:
        workspace_root = cwd.resolve()
        state = ClientMcpSessionState(session_id=session_id, _workspace_root=workspace_root,
                                     _record_close_failure=self.record_session_close_failure)
        self._own_candidates(state)
        if entries is None or len(entries) == 0:
            return state

        try:
            capabilities = self._normalizer.normalize(
                entries,
                workspace_root=workspace_root,
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
        except BaseException as primary:
            hooks = state.prepare_close()
            try:
                failures = await self.run_blocking(partial(run_close_hooks, hooks))
            except BaseException:
                state.complete_close(("SESSION_CLOSE_FAILED",))
            else:
                state.complete_close(failures)
            raise primary


    async def reopen_suspended(
        self, state: ClientMcpSessionState, request_permission: RequestPermissionFn,
    ) -> PermissionOutcome:
        if state._closed or not state.suspended:
            return "reject"
        self._own_candidates(state)
        renewed = dict(state._former_servers)
        for name, entry in state._former_servers.items():
            if entry.lease is None:
                continue
            capability = state._capability_for(name)
            if capability is None or entry.identity_fingerprint is None:
                return "reject"
            candidate_id = uuid.uuid4().hex
            if self._candidate_endpoint is not None:
                endpoint = self._candidate_endpoint
                view = capability.safe_view()
                candidate = PendingClientMcpCandidate(
                    workspace_digest=self._workspace_digest, session_id=state.session_id,
                    identity=capability.safe_identity, rendered_fingerprint=entry.identity_fingerprint,
                    provenance=view.provenance, scanner_rule_ids=view.scanner_rule_ids,
                )
                candidate_id = await self.run_blocking(partial(endpoint.publish, candidate))
            params = build_client_mcp_permission_params(
                session_id=state.session_id, candidate_id=candidate_id, server_name=name,
                transport=capability.safe_identity.transport, identity_fingerprint=entry.identity_fingerprint,
            )
            outcome = await self._await_permission(request_permission, params)
            if outcome != "allow":
                return outcome
            durable = await self.run_blocking(partial(self._lease_authority.lookup_durable,
                self._workspace_digest, name, entry.identity_fingerprint,
            ))
            lease = self._lease_authority.acquire_allow_once(
                session_id=state.session_id, workspace_digest=self._workspace_digest,
                identity=capability.safe_identity, identity_fingerprint=entry.identity_fingerprint,
            )
            if durable is not None:
                lease = replace(lease, effect_ceiling=durable.effect_ceiling)
            renewed[name] = replace(entry, lease=lease, durable=durable)
        if state._closed:
            return "reject"
        state._servers = renewed
        state._tool_service = state._tool_service.retire()
        state.suspended = False
        self._own_candidates(state)
        if state._resolver_adapter is not None:
            self.attach_runtime_resolver(state, sdk_adapter=state._resolver_adapter)
        return "allow"

    def materialize_tool_service(
        self,
        state: ClientMcpSessionState,
        *,
        identity: ClientMcpSafeIdentity,
        raw_tools: Sequence[Mapping[str, object]],
        workspace_root: Path,
        elapsed_seconds: float = 0.0,
        service_factory: ClientMcpServiceFactory,
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
        except ClientMcpCatalogError as exc:
            state.tool_service._record_resolution_failure(server_name, exc)
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
        service = service_factory(guard=guard, catalog=catalog, authorizer=authorizer)
        service_catalog: ClientMcpCatalog = object.__getattribute__(service, "_catalog")
        if service_catalog is not catalog:
            raise ClientMcpCatalogError("SERVICE_CATALOG_MISMATCH")
        state.tool_service.register(service)
        return service

    def attach_runtime_resolver(
        self,
        state: ClientMcpSessionState,
        *,
        sdk_adapter: ClientMcpSdkAdapter,
        service_factory_builder: ClientMcpServiceFactoryBuilder | None = None,
    ) -> None:
        """Attach a transport-opening resolver only after disposition has succeeded."""
        builder = service_factory_builder or _adapter_backed_service_factory
        state._resolver_adapter = sdk_adapter

        def resolve(server: str) -> ClientMcpToolService | None:
            return self._resolve_server(
                state,
                server=server,
                sdk_adapter=sdk_adapter,
                service_factory_builder=builder,
            )

        state.tool_service.attach_resolver(resolve)

    def _resolve_server(
        self,
        state: ClientMcpSessionState,
        *,
        server: str,
        sdk_adapter: ClientMcpSdkAdapter,
        service_factory_builder: ClientMcpServiceFactoryBuilder,
    ) -> ClientMcpToolService | None:
        if state._closed or not state.is_leased(server):
            return None
        capability = state._capability_for(server)
        workspace_root = state._workspace_root
        if capability is None or workspace_root is None:
            return None

        connection: ClientMcpConnection | None = None
        service: ClientMcpToolService | None = None
        try:
            connection = sdk_adapter.open(capability, session_id=state.session_id)
            started = monotonic()
            raw_tools = sdk_adapter.discover(connection)
            elapsed_seconds = monotonic() - started
            service_factory = service_factory_builder(sdk_adapter, connection)
            service = self.materialize_tool_service(
                state,
                identity=capability.safe_identity,
                raw_tools=raw_tools,
                workspace_root=workspace_root,
                service_factory=service_factory,
                elapsed_seconds=elapsed_seconds,
            )
            if service is None:
                raise ClientMcpCatalogError("SERVICE_UNAVAILABLE")
            def close_opened(
                adapter: ClientMcpSdkAdapter = sdk_adapter,
                opened: ClientMcpConnection = connection,
            ) -> None:
                adapter.close(opened)

            close_registered = state.register_close_hook(close_opened, peer=True)
            if not close_registered:
                state.tool_service.unregister(service)
                return None
            return service
        except Exception as exc:
            state.tool_service._record_resolution_failure(server, exc)
            if service is not None:
                state.tool_service.unregister(service)
            if connection is not None:
                with suppress(Exception):
                    sdk_adapter.close(connection)
            return None

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


def _adapter_backed_service_factory(
    adapter: ClientMcpSdkAdapter,
    connection: ClientMcpConnection,
) -> ClientMcpServiceFactory:
    def create(
        *,
        guard: PreToolGuard,
        catalog: ClientMcpCatalog,
        authorizer: ClientMcpCallAuthorizer,
    ) -> ClientMcpToolService:
        return AdapterBackedClientMcpToolService(
            guard=guard,
            catalog=catalog,
            authorizer=authorizer,
            adapter=adapter,
            connection=connection,
        )

    return create


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
    "ClientMcpShutdownOutcome",
    "ClientMcpConfigError",
]
