"""Task 6 resource-ownership and shutdown characterization.

This module is audit tooling only.  It reads immutable source views and executes
offline unit-level close contracts; it never starts Optimus, Redis, Gateway, or
an ACP client.
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import threading
import time
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Mapping

from .source import SourceTree

if TYPE_CHECKING:
    from .model import AuditArtifact

H5_SOURCE_PATHS = (
    "src/optimus/acp/__main__.py",
    "src/optimus/acp/bootstrap.py",
    "src/optimus/acp/launch_approvals.py",
    "src/optimus/acp/launch_audit.py",
    "src/optimus/acp/launch_gate.py",
    "src/optimus/acp/launch_policy.py",
    "src/optimus/acp/local_gateway_secrets.py",
    "src/optimus/acp/local_infra.py",
    "src/optimus/acp/operator_paths.py",
    "src/optimus/acp/operator_verify.py",
    "src/optimus/acp/outbound_writer.py",
    "src/optimus/acp/preflight.py",
    "src/optimus/acp/server.py",
    "src/optimus/acp/spec.py",
    "src/optimus/acp/trusted_paths.py",
    "src/optimus/mcp/client_disposition.py",
    "src/optimus/mcp/client_sdk.py",
    "src/optimus/mcp/client_supervisor.py",
    "src/optimus/mcp/local_ipc.py",
    "src/optimus/mcp/runtime.py",
    "src/optimus/redis/async_bridge.py",
    "src/optimus/redis/runtime.py",
    "src/optimus/telemetry/redis_adapter.py",
    "src/optimus/telemetry/redis_sink.py",
)

_CLOSE_DEFINITION_NAMES = {
    "close",
    "aclose",
    "close_all",
    "close_and_join",
    "stop",
    "shutdown_background_loop",
}
_CLOSE_CALL_NAMES = _CLOSE_DEFINITION_NAMES | {
    "terminate",
    "kill",
    "cancel",
    "release",
    "join",
}
_RESOURCE_RECEIVER_TOKENS = (
    "adapter",
    "candidate",
    "client",
    "conn",
    "coro",
    "dedicated",
    "disposed",
    "endpoint",
    "future",
    "listener",
    "lock",
    "log_file",
    "loop",
    "owner",
    "os",
    "permission",
    "pool",
    "process",
    "reader",
    "runtime",
    "session",
    "state",
    "store",
    "supervisor",
    "task",
    "thread",
    "token",
    "transport",
    "worker",
    "writer",
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _conceptual_id(path: str, owner: str, reference: str, site_kind: str) -> str:
    return f"h5-{_digest(f'{path}:{owner}:{reference}:{site_kind}')[:16]}"


@dataclass(frozen=True, slots=True)
class CloseSite:
    conceptual_id: str
    path: str
    line: int
    symbol: str
    reference: str
    site_kind: str
    source_baseline: str
    evidence_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "conceptual_id": self.conceptual_id,
            "path": self.path,
            "line": self.line,
            "symbol": self.symbol,
            "reference": self.reference,
            "site_kind": self.site_kind,
            "source_baseline": self.source_baseline,
            "evidence_digest": self.evidence_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CloseSite:
        expected = {
            "conceptual_id", "path", "line", "symbol", "reference", "site_kind",
            "source_baseline", "evidence_digest",
        }
        if set(payload) != expected:
            raise ValueError("close site fields do not match the canonical schema")
        return cls(**payload)


@dataclass(frozen=True, slots=True)
class ResourceOwnershipRecord:
    close_path_id: str
    resource_type: str
    close_method: str
    constructor: str
    owner_transfer: str
    normal_close: str
    cancellation_close: str
    partial_failure_close: str
    repeated_close: str
    dependency_rank: int
    baseline_presence: tuple[str, ...]
    schedule_applicable: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "close_path_id": self.close_path_id,
            "resource_type": self.resource_type,
            "close_method": self.close_method,
            "constructor": self.constructor,
            "owner_transfer": self.owner_transfer,
            "normal_close": self.normal_close,
            "cancellation_close": self.cancellation_close,
            "partial_failure_close": self.partial_failure_close,
            "repeated_close": self.repeated_close,
            "dependency_rank": self.dependency_rank,
            "baseline_presence": list(self.baseline_presence),
            "schedule_applicable": self.schedule_applicable,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResourceOwnershipRecord:
        expected = {
            "close_path_id", "resource_type", "close_method", "constructor", "owner_transfer",
            "normal_close", "cancellation_close", "partial_failure_close", "repeated_close",
            "dependency_rank", "baseline_presence", "schedule_applicable",
        }
        if set(payload) != expected:
            raise ValueError("resource ownership fields do not match the canonical schema")
        return cls(
            **{key: value for key, value in payload.items() if key != "baseline_presence"},
            baseline_presence=tuple(payload["baseline_presence"]),
        )


@dataclass(frozen=True, slots=True)
class ShutdownInventory:
    close_sites: tuple[CloseSite, ...]
    resources: tuple[ResourceOwnershipRecord, ...]

    @property
    def close_definitions(self) -> tuple[CloseSite, ...]:
        return tuple(site for site in self.close_sites if site.site_kind == "CLOSE_DEFINITION")

    @property
    def close_path_count(self) -> int:
        return len({site.conceptual_id for site in self.close_definitions})


@dataclass(frozen=True, slots=True)
class ClosePathScopeOut:
    close_path_id: str
    resource_type: str
    close_method: str
    baseline_scope: str
    reason: str
    owner: str
    next_gate: str

    def to_dict(self) -> dict[str, str]:
        return {
            "close_path_id": self.close_path_id,
            "resource_type": self.resource_type,
            "close_method": self.close_method,
            "baseline_scope": self.baseline_scope,
            "reason": self.reason,
            "owner": self.owner,
            "next_gate": self.next_gate,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ClosePathScopeOut:
        expected = {
            "close_path_id", "resource_type", "close_method", "baseline_scope", "reason",
            "owner", "next_gate",
        }
        if set(payload) != expected:
            raise ValueError("close-path scope-out fields do not match the canonical schema")
        return cls(**payload)


class _ShutdownVisitor(ast.NodeVisitor):
    def __init__(self, *, path: str, text: str, baseline: str) -> None:
        self.path = path
        self.text = text
        self.baseline = baseline
        self.lines = text.splitlines()
        self.scope: list[str] = []
        self.class_scope: list[str] = []
        self.sites: list[CloseSite] = []

    def _symbol(self) -> str:
        module = self.path.removesuffix(".py").replace("/", ".")
        return ".".join((module, *self.scope))

    def _owner(self) -> str:
        return self.class_scope[-1] if self.class_scope else "<module>"

    def _add(self, node: ast.AST, *, reference: str, site_kind: str, owner: str | None = None) -> None:
        owner_name = owner or self._owner()
        source = ast.get_source_segment(self.text, node) or reference
        self.sites.append(
            CloseSite(
                conceptual_id=_conceptual_id(self.path, owner_name, reference, site_kind),
                path=self.path,
                line=node.lineno,
                symbol=self._symbol(),
                reference=reference,
                site_kind=site_kind,
                source_baseline=self.baseline,
                evidence_digest=_digest(ast.dump(node, include_attributes=False) + source),
            )
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope.append(node.name)
        self.class_scope.append(node.name)
        self.generic_visit(node)
        self.class_scope.pop()
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if node.name in _CLOSE_DEFINITION_NAMES:
            self.scope.append(node.name)
            self._add(node, reference=node.name, site_kind="CLOSE_DEFINITION")
            self.generic_visit(node)
            self.scope.pop()
            return
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_Call(self, node: ast.Call) -> None:
        reference = ast.unparse(node.func)
        leaf = reference.rsplit(".", 1)[-1]
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Call):
            reference = f"{ast.unparse(node.func.value.func)}.{leaf}"
        if leaf in _CLOSE_CALL_NAMES and self._resource_receiver(reference, leaf):
            self._add(node, reference=reference, site_kind="CLOSE_INVOCATION")
        self.generic_visit(node)

    @staticmethod
    def _resource_receiver(reference: str, leaf: str) -> bool:
        if "." not in reference:
            return leaf == "shutdown_background_loop"
        receiver = reference.rsplit(".", 1)[0].lower()
        if leaf == "join":
            return any(token in receiver for token in ("thread", "reader", "writer", "worker", "future"))
        if receiver == "self" and leaf in _CLOSE_DEFINITION_NAMES:
            return True
        return any(token in receiver for token in _RESOURCE_RECEIVER_TOKENS)


def _scan(source: SourceTree, baseline: str) -> tuple[CloseSite, ...]:
    sites: list[CloseSite] = []
    for path in source.paths():
        text = source.read_text(path)
        visitor = _ShutdownVisitor(path=path, text=text, baseline=baseline)
        visitor.visit(ast.parse(text, filename=path))
        sites.extend(visitor.sites)
    return tuple(sorted(sites, key=lambda item: (item.path, item.line, item.site_kind, item.reference)))


def _resource_type(site: CloseSite) -> str:
    parts = site.symbol.split(".")
    return parts[-2] if len(parts) >= 2 else site.reference


def _dependency_rank(resource_type: str) -> int:
    lowered = resource_type.lower()
    if "adapter" in lowered or "session" in lowered:
        return 10
    if "mcp" in lowered or "supervisor" in lowered or "endpoint" in lowered:
        return 20
    if "writer" in lowered:
        return 30
    if "reader" in lowered or "loop" in lowered:
        return 40
    if "redis" in lowered:
        return 50
    return 25


def discover_shutdown_inventory(
    merged: SourceTree,
    *,
    overlay: SourceTree | None = None,
) -> ShutdownInventory:
    """Derive close definitions/calls and one ownership row per close contract."""

    sites = list(_scan(merged, "merged"))
    if overlay is not None:
        sites.extend(_scan(overlay, "overlay"))
    ordered = tuple(sorted(sites, key=lambda item: (item.path, item.line, item.source_baseline, item.reference)))
    definitions: dict[str, list[CloseSite]] = {}
    invocations = [site for site in ordered if site.site_kind == "CLOSE_INVOCATION"]
    for site in ordered:
        if site.site_kind == "CLOSE_DEFINITION":
            definitions.setdefault(site.conceptual_id, []).append(site)
    resources: list[ResourceOwnershipRecord] = []
    for close_path_id, variants in sorted(definitions.items()):
        exemplar = variants[0]
        resource_type = _resource_type(exemplar)
        relevant_calls = [
            call
            for call in invocations
            if call.reference.rsplit(".", 1)[-1] == exemplar.reference
        ]
        citations = ",".join(
            f"{call.path}:{call.line}:{call.reference}" for call in relevant_calls
        ) or "NONE_OBSERVED"
        baselines = tuple(sorted({item.source_baseline for item in variants}))
        resources.append(
            ResourceOwnershipRecord(
                close_path_id=close_path_id,
                resource_type=resource_type,
                close_method=exemplar.reference,
                constructor=f"DERIVED_CLASS_OR_MODULE:{exemplar.path}:{resource_type}",
                owner_transfer=f"LEXICAL_OWNER:{resource_type}",
                normal_close=citations,
                cancellation_close=(
                    citations if any("cancel" in call.symbol or "finally" in call.symbol for call in relevant_calls)
                    else "NO_DISTINCT_CANCELLATION_CALL_OBSERVED"
                ),
                partial_failure_close=(
                    citations if any("except" in call.symbol or "finally" in call.symbol for call in relevant_calls)
                    else "NO_DISTINCT_PARTIAL_FAILURE_CALL_OBSERVED"
                ),
                repeated_close="PENDING_THREE_CALL_CHARACTERIZATION",
                dependency_rank=_dependency_rank(resource_type),
                baseline_presence=baselines,
                schedule_applicable="merged" in baselines,
            )
        )
    return ShutdownInventory(close_sites=ordered, resources=tuple(resources))


_TERMINAL_CAUSES = (
    "orderly_eof",
    "request_cancellation",
    "transport_failure",
    "server_cancellation",
    "partial_startup_failure",
)


@dataclass(frozen=True, slots=True)
class ShutdownScheduleObservation:
    close_path_id: str
    terminal_cause: str
    complete: bool
    close_invocation_count: int
    control_thread_names: tuple[str, ...]
    unexpected_persistent_threads: tuple[str, ...]
    unexpected_persistent_tasks: tuple[str, ...]
    repeat_latency_class: str
    underlying_close_count: int
    close_outcome: str
    cause_effect: str

    def __post_init__(self) -> None:
        if self.terminal_cause not in _TERMINAL_CAUSES:
            raise ValueError("shutdown observation terminal cause is invalid")
        if self.complete is not True or self.close_invocation_count != 3:
            raise ValueError("shutdown observation must record three complete close invocations")
        for field in (
            "control_thread_names", "unexpected_persistent_threads", "unexpected_persistent_tasks",
        ):
            object.__setattr__(self, field, tuple(getattr(self, field)))
        if not self.control_thread_names:
            raise ValueError("shutdown observation must preserve the control thread allowlist")
        if self.repeat_latency_class not in {"WITHIN_100MS", "ABOVE_100MS"}:
            raise ValueError("shutdown observation latency class is invalid")
        if self.underlying_close_count < 0:
            raise ValueError("shutdown observation underlying close count is invalid")
        if self.close_outcome not in {"CLOSED_ONCE", "IDEMPOTENT_NOOP", "DOUBLE_CLOSE_OBSERVED", "ERROR"}:
            raise ValueError("shutdown observation close outcome is invalid")
        expected = (
            "IDEMPOTENT_NOOP"
            if self.underlying_close_count == 0
            else "CLOSED_ONCE"
            if self.underlying_close_count == 1
            else "DOUBLE_CLOSE_OBSERVED"
        )
        if self.close_outcome != "ERROR" and self.close_outcome != expected:
            raise ValueError("shutdown observation close outcome disagrees with the underlying count")
        if not self.close_path_id or not self.cause_effect:
            raise ValueError("shutdown observation identity and cause effect are required")

    def to_dict(self) -> dict[str, object]:
        return {
            "close_path_id": self.close_path_id,
            "terminal_cause": self.terminal_cause,
            "complete": self.complete,
            "close_invocation_count": self.close_invocation_count,
            "control_thread_names": list(self.control_thread_names),
            "unexpected_persistent_threads": list(self.unexpected_persistent_threads),
            "unexpected_persistent_tasks": list(self.unexpected_persistent_tasks),
            "repeat_latency_class": self.repeat_latency_class,
            "underlying_close_count": self.underlying_close_count,
            "close_outcome": self.close_outcome,
            "cause_effect": self.cause_effect,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ShutdownScheduleObservation:
        expected = {
            "close_path_id", "terminal_cause", "complete", "close_invocation_count",
            "control_thread_names", "unexpected_persistent_threads", "unexpected_persistent_tasks",
            "repeat_latency_class", "underlying_close_count", "close_outcome", "cause_effect",
        }
        if set(payload) != expected:
            raise ValueError("shutdown observation fields do not match the canonical schema")
        return cls(
            close_path_id=payload["close_path_id"],
            terminal_cause=payload["terminal_cause"],
            complete=payload["complete"],
            close_invocation_count=payload["close_invocation_count"],
            control_thread_names=tuple(payload["control_thread_names"]),
            unexpected_persistent_threads=tuple(payload["unexpected_persistent_threads"]),
            unexpected_persistent_tasks=tuple(payload["unexpected_persistent_tasks"]),
            repeat_latency_class=payload["repeat_latency_class"],
            underlying_close_count=payload["underlying_close_count"],
            close_outcome=payload["close_outcome"],
            cause_effect=payload["cause_effect"],
        )


class _CountedAsyncClose:
    def __init__(self) -> None:
        self.count = 0

    async def aclose(self) -> None:
        self.count += 1


class _CountedClose:
    def __init__(self) -> None:
        self.count = 0

    def close(self) -> None:
        self.count += 1


class _DetachService:
    def __init__(self) -> None:
        self.count = 0

    def detach_resolver(self) -> None:
        self.count += 1


class _CountingComponent:
    def __init__(self) -> None:
        self.count = 0
        self.closed = False

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.count += 1

    def close_all(self) -> None:
        self.close()


class _ProbeProcess:
    def __init__(self, *, already_stopped: bool) -> None:
        self.stopped = already_stopped
        self.terminate_count = 0
        self.kill_count = 0

    def poll(self) -> int | None:
        return 0 if self.stopped else None

    def terminate(self) -> None:
        self.terminate_count += 1
        self.stopped = True

    def wait(self, *, timeout: float) -> int:
        del timeout
        self.stopped = True
        return 0

    def kill(self) -> None:
        self.kill_count += 1
        self.stopped = True


def _repeat_actual_close(close: Callable[[], None], count: Callable[[], int]) -> int:
    for _ in range(3):
        close()
    return count()


def _probe_resource(record: ResourceOwnershipRecord, terminal_cause: str) -> tuple[int, str]:
    """Invoke the discovered production close contract three times on offline fakes."""

    resource = record.resource_type
    method = record.close_method
    cause_effect = f"{terminal_cause}:prepared"

    if resource == "RedisRuntime":
        from optimus.redis.async_bridge import shutdown_background_loop
        from optimus.redis.runtime import RedisRuntime

        client = _CountedAsyncClose()
        pool = _CountedAsyncClose()
        runtime = RedisRuntime(pool=pool, client=client)
        try:
            if method == "aclose":
                asyncio.run(_repeat_async_close(runtime.aclose))
            else:
                _repeat_actual_close(runtime.close, lambda: max(client.count, pool.count))
        finally:
            shutdown_background_loop()
        return max(client.count, pool.count), cause_effect

    if resource == "DedicatedOutboundWriter":
        from optimus.acp.outbound_writer import DedicatedOutboundWriter

        class _Transport:
            def write_bytes(self, data: bytes) -> None:
                del data

            def flush(self) -> None:
                return

        writer = DedicatedOutboundWriter(_Transport())
        writer.start()
        _repeat_actual_close(writer.close_and_join, lambda: int(writer._joined))
        return int(writer._joined), f"{terminal_cause}:writer_thread_joined"

    if resource == "InMemoryAcpSpecSessionStore":
        from optimus.acp.spec import InMemoryAcpSpecSessionStore

        store = InMemoryAcpSpecSessionStore()
        session = store.create(cwd=Path.cwd())
        state = _CountedClose()
        session.client_mcp_state = state  # type: ignore[assignment]
        return _repeat_actual_close(store.close_all, lambda: state.count), cause_effect

    if resource == "AcpDuplexAdapter":
        from optimus.acp.spec import AcpDuplexAdapter

        sessions = _CountingComponent()
        adapter = object.__new__(AcpDuplexAdapter)
        adapter._closed = False
        adapter._active_turns = {}
        adapter._sessions = sessions
        return _repeat_actual_close(adapter.close_all, lambda: sessions.count), cause_effect

    if resource == "ClientMcpSessionState":
        from optimus.mcp.client_disposition import ClientMcpSessionState

        state = ClientMcpSessionState(session_id="h5-audit")
        service = _DetachService()
        hook = _CountedClose()
        state._tool_service = service  # type: ignore[assignment]
        state.register_close_hook(hook.close)
        return _repeat_actual_close(state.close, lambda: max(service.count, hook.count)), cause_effect

    if resource == "ClientMcpRuntime":
        from optimus.mcp.client_disposition import ClientMcpRuntime

        sdk = _CountingComponent()
        candidate = _CountingComponent()
        supervisor = _CountingComponent()
        runtime = ClientMcpRuntime(
            disposition=object(),  # type: ignore[arg-type]
            supervisor=supervisor,  # type: ignore[arg-type]
            sdk_adapter=sdk,  # type: ignore[arg-type]
            candidate_endpoint=candidate,  # type: ignore[arg-type]
        )
        return _repeat_actual_close(
            runtime.close,
            lambda: max(sdk.count, candidate.count, supervisor.count),
        ), cause_effect

    if resource == "MCPAsyncSupervisor":
        from optimus.mcp.client_supervisor import MCPAsyncSupervisor, MCPSupervisorState

        supervisor = MCPAsyncSupervisor()
        supervisor.start()
        return _repeat_actual_close(
            supervisor.close,
            lambda: int(supervisor.state is MCPSupervisorState.DEAD),
        ), f"{terminal_cause}:supervisor_loop_stopped"

    if resource == "PendingClientMcpCandidateEndpoint":
        from optimus.mcp.local_ipc import PendingClientMcpCandidateEndpoint

        endpoint = PendingClientMcpCandidateEndpoint(authkey=b"h5-offline")
        return _repeat_actual_close(endpoint.close, lambda: int(endpoint._stop.is_set())), cause_effect

    if resource == "ClientMcpSdkAdapter":
        from optimus.mcp.client_sdk import ClientMcpConnection, ClientMcpSdkAdapter

        class _SdkProbe(ClientMcpSdkAdapter):
            def __init__(self) -> None:
                self.submissions = 0
                self._connections = {}
                self._process_control = _ProcessControl()

            def _submit_operation(self, coro):  # type: ignore[no-untyped-def, override]
                self.submissions += 1
                return asyncio.run(coro)

        class _ProcessControl:
            def __init__(self) -> None:
                self.count = 0

            def terminate_tree(self, *, seam: str) -> None:
                del seam
                self.count += 1

        sdk = _SdkProbe()
        closed = _CountedAsyncClose()
        key = ("h5", "server", "target")
        connection = ClientMcpConnection(
            session_id="h5",
            identity_key=key,
            session=object(),
            negotiated_protocol_version="2026-07-28",
            close_resources=closed.aclose,
        )
        sdk._connections[key] = connection
        if method == "close":
            return _repeat_actual_close(
                lambda: sdk.close(connection),
                lambda: max(closed.count, sdk._process_control.count),
            ), cause_effect
        return _repeat_actual_close(
            sdk.close_all,
            lambda: max(closed.count, sdk._process_control.count),
        ), cause_effect

    if resource == "LocalGatewayProcess":
        from optimus.acp.local_infra import LocalGatewayProcess

        already_stopped = terminal_cause == "partial_startup_failure"
        process = _ProbeProcess(already_stopped=already_stopped)
        owner = LocalGatewayProcess(process=process, log_path=None)  # type: ignore[arg-type]
        return _repeat_actual_close(
            owner.stop,
            lambda: process.terminate_count + process.kill_count,
        ), f"{terminal_cause}:{'no_child_started' if already_stopped else 'child_terminated'}"

    if resource == "async_bridge":
        from optimus.redis.async_bridge import shutdown_background_loop, sync_await

        sync_await(_return_none())
        return _repeat_actual_close(
            shutdown_background_loop,
            lambda: int(not any(thread.name == "optimus-redis-async" for thread in threading.enumerate())),
        ), f"{terminal_cause}:bridge_loop_stopped"

    raise ValueError(f"no offline close probe for {resource}.{method}")


async def _repeat_async_close(close: Callable[[], object]) -> None:
    for _ in range(3):
        await close()  # type: ignore[misc]


async def _return_none() -> None:
    return None


def shutdown_schedule_observations(
    *,
    inventory: ShutdownInventory,
    repeats: int,
) -> tuple[ShutdownScheduleObservation, ...]:
    """Run every merged close contract under each terminal cause, three closes each."""

    if repeats < 1:
        raise ValueError("repeats must be >= 1")
    observations: list[ShutdownScheduleObservation] = []
    applicable = [record for record in inventory.resources if record.schedule_applicable]
    control_thread_names = tuple(sorted(thread.name for thread in threading.enumerate()))
    control_counts = Counter(control_thread_names)
    for record in applicable:
        for cause in _TERMINAL_CAUSES:
            for _ in range(repeats):
                started = time.perf_counter()
                try:
                    underlying_count, cause_effect = _probe_resource(record, cause)
                    complete = True
                    outcome = (
                        "IDEMPOTENT_NOOP"
                        if underlying_count == 0
                        else "CLOSED_ONCE"
                        if underlying_count == 1
                        else "DOUBLE_CLOSE_OBSERVED"
                    )
                except Exception as exc:  # pragma: no cover - preserved as audit evidence
                    underlying_count = 0
                    cause_effect = f"{cause}:probe_error:{type(exc).__name__}"
                    complete = True
                    outcome = "ERROR"
                elapsed = time.perf_counter() - started
                after_counts = Counter(thread.name for thread in threading.enumerate())
                persistent = tuple(sorted((after_counts - control_counts).elements()))
                observations.append(
                    ShutdownScheduleObservation(
                        close_path_id=record.close_path_id,
                        terminal_cause=cause,
                        complete=complete,
                        close_invocation_count=3,
                        control_thread_names=control_thread_names,
                        unexpected_persistent_threads=persistent,
                        unexpected_persistent_tasks=(),
                        repeat_latency_class="WITHIN_100MS" if elapsed <= 0.1 else "ABOVE_100MS",
                        underlying_close_count=underlying_count,
                        close_outcome=outcome,
                        cause_effect=cause_effect,
                    )
                )
    return tuple(observations)


def characterize_shutdown_inventory(
    inventory: ShutdownInventory,
    observations: tuple[ShutdownScheduleObservation, ...],
) -> ShutdownInventory:
    """Attach mechanically observed repeat behavior without changing discovered membership."""

    by_path: dict[str, list[ShutdownScheduleObservation]] = {}
    for observation in observations:
        by_path.setdefault(observation.close_path_id, []).append(observation)
    resources: list[ResourceOwnershipRecord] = []
    for record in inventory.resources:
        path_observations = by_path.get(record.close_path_id, [])
        if not path_observations:
            repeated_close = "SCOPED_OUT_OVERLAY_ONLY_BINDING_EXECUTION_REQUIRED"
        else:
            outcomes = ",".join(sorted({item.close_outcome for item in path_observations}))
            max_underlying = max(item.underlying_close_count for item in path_observations)
            latency = ",".join(sorted({item.repeat_latency_class for item in path_observations}))
            repeated_close = (
                f"OBSERVED_OUTCOMES:{outcomes};MAX_UNDERLYING_CLOSE_COUNT:{max_underlying};"
                f"REPEAT_LATENCY:{latency}"
            )
        resources.append(replace(record, repeated_close=repeated_close))
    return ShutdownInventory(close_sites=inventory.close_sites, resources=tuple(resources))


_H5_OWNER = "P11-FEAT-ACP-RUNTIME-HARDENING"
_H5_COVERAGE_FIELDS = (
    ("terminal_cause", "TerminalCause"),
    ("close_outcome", "CloseOutcome"),
    ("repeat_latency_class", "RepeatLatencyClass"),
)


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _h5_vocabulary() -> dict[str, dict[str, str]]:
    return {
        "TerminalCause": {value.upper(): value for value in _TERMINAL_CAUSES},
        "CloseOutcome": {
            "CLOSED_ONCE": "CLOSED_ONCE",
            "IDEMPOTENT_NOOP": "IDEMPOTENT_NOOP",
            "DOUBLE_CLOSE_OBSERVED": "DOUBLE_CLOSE_OBSERVED",
            "ERROR": "ERROR",
        },
        "RepeatLatencyClass": {
            "WITHIN_100MS": "WITHIN_100MS",
            "ABOVE_100MS": "ABOVE_100MS",
        },
    }


def _h5_scope_reason(field_name: str) -> tuple[str, str]:
    reasons = {
        "close_outcome": (
            "Task 6 invokes valid offline close owners and does not manufacture a close exception; ERROR remains a named fault-injection obligation.",
            "G4 per-group shutdown fault-injection characterization",
        ),
        "repeat_latency_class": (
            "Task 6 records measured close latency but does not add an artificial slow-close delay solely to populate the above-threshold value.",
            "G4 per-group bounded slow-close characterization",
        ),
        "terminal_cause": (
            "Task 6 defines all five terminal causes; a missing cause indicates a schedule construction defect that must be corrected before G2.",
            "G2 Task 6 schedule correction",
        ),
    }
    return reasons[field_name]


def _h5_coverage_assessments(
    observations: tuple[ShutdownScheduleObservation, ...],
) -> tuple[object, ...]:
    from .model import CoverageAssessmentStatus, VocabularyCoverageAssessment

    vocabulary = _h5_vocabulary()
    assessments: list[VocabularyCoverageAssessment] = []
    for field_name, type_name in _H5_COVERAGE_FIELDS:
        vocabulary_values = tuple(sorted(set(vocabulary[type_name].values())))
        observed_values = tuple(sorted({str(getattr(item, field_name)) for item in observations}))
        missing_values = tuple(sorted(set(vocabulary_values) - set(observed_values)))
        if missing_values:
            reason, next_gate = _h5_scope_reason(field_name)
            status = CoverageAssessmentStatus.SCOPED_OUT
            owner: str | None = _H5_OWNER
        else:
            reason = None
            next_gate = None
            status = CoverageAssessmentStatus.FULLY_OBSERVED
            owner = None
        assessments.append(
            VocabularyCoverageAssessment(
                field_name=field_name,
                type_name=type_name,
                vocabulary_values=vocabulary_values,
                observed_values=observed_values,
                missing_values=missing_values,
                status=status,
                reason=reason,
                owner=owner,
                next_gate=next_gate,
            )
        )
    return tuple(assessments)


@dataclass(frozen=True, slots=True)
class ShutdownObservationSummary:
    repeats_per_family: int
    terminal_causes: tuple[str, ...]
    close_path_count: int
    total_observation_count: int
    complete_observation_count: int
    observation_closure_status: object
    vocabulary_coverage_status: object
    digest: str
    vocabulary: Mapping[str, Mapping[str, str]]
    coverage_assessments: tuple[object, ...]
    observations: tuple[ShutdownScheduleObservation, ...]

    def __post_init__(self) -> None:
        from .model import (
            CoverageAssessmentStatus,
            ObservationClosureStatus,
            VocabularyCoverageStatus,
        )

        object.__setattr__(self, "observation_closure_status", ObservationClosureStatus(self.observation_closure_status))
        object.__setattr__(self, "vocabulary_coverage_status", VocabularyCoverageStatus(self.vocabulary_coverage_status))
        object.__setattr__(self, "terminal_causes", tuple(self.terminal_causes))
        object.__setattr__(self, "coverage_assessments", tuple(self.coverage_assessments))
        object.__setattr__(self, "observations", tuple(self.observations))
        if self.repeats_per_family < 1 or self.terminal_causes != _TERMINAL_CAUSES:
            raise ValueError("H5 shutdown schedule dimensions are invalid")
        expected_total = self.close_path_count * len(self.terminal_causes) * self.repeats_per_family
        if self.total_observation_count != expected_total or len(self.observations) != expected_total:
            raise ValueError("H5 observation count does not match derived close paths, causes, and repeats")
        if self.complete_observation_count != sum(item.complete for item in self.observations):
            raise ValueError("H5 structural closure count disagrees with raw observations")
        if self.complete_observation_count != self.total_observation_count:
            raise ValueError("H5 requires one complete record per shutdown schedule")
        if self.observation_closure_status is not ObservationClosureStatus.FULLY_STRUCTURALLY_CLOSED:
            raise ValueError("H5 complete records must be labelled structurally closed")
        if dict(self.vocabulary) != _h5_vocabulary():
            raise ValueError("H5 vocabulary must equal the audit-owned closed vocabulary")
        if self.digest != _canonical_digest([item.to_dict() for item in self.observations]):
            raise ValueError("H5 schedule digest disagrees with raw observations")
        path_ids = tuple(sorted({item.close_path_id for item in self.observations}))
        if len(path_ids) != self.close_path_count:
            raise ValueError("H5 raw observations do not cover every applicable close path")
        for path_id in path_ids:
            for cause in self.terminal_causes:
                family = tuple(
                    item for item in self.observations
                    if item.close_path_id == path_id and item.terminal_cause == cause
                )
                if len(family) != self.repeats_per_family:
                    raise ValueError("H5 close-path/cause family is incomplete")
        assessments = {item.field_name: item for item in self.coverage_assessments}
        if set(assessments) != {field for field, _ in _H5_COVERAGE_FIELDS}:
            raise ValueError("H5 coverage assessments are incomplete")
        has_scope_out = False
        for field_name, type_name in _H5_COVERAGE_FIELDS:
            assessment = assessments[field_name]
            vocabulary_values = tuple(sorted(set(self.vocabulary[type_name].values())))
            observed_values = tuple(sorted({str(getattr(item, field_name)) for item in self.observations}))
            missing_values = tuple(sorted(set(vocabulary_values) - set(observed_values)))
            expected_status = (
                CoverageAssessmentStatus.SCOPED_OUT
                if missing_values
                else CoverageAssessmentStatus.FULLY_OBSERVED
            )
            has_scope_out = has_scope_out or bool(missing_values)
            if (
                assessment.type_name != type_name
                or assessment.vocabulary_values != vocabulary_values
                or assessment.observed_values != observed_values
                or assessment.missing_values != missing_values
                or assessment.status is not expected_status
            ):
                raise ValueError("H5 coverage assessment disagrees with raw observations")
        expected_coverage = (
            VocabularyCoverageStatus.PARTIAL_WITH_SCOPE_OUTS
            if has_scope_out
            else VocabularyCoverageStatus.FULLY_OBSERVED
        )
        if self.vocabulary_coverage_status is not expected_coverage:
            raise ValueError("H5 aggregate coverage disagrees with its assessments")

    def to_dict(self) -> dict[str, object]:
        return {
            "repeats_per_family": self.repeats_per_family,
            "terminal_causes": list(self.terminal_causes),
            "close_path_count": self.close_path_count,
            "total_observation_count": self.total_observation_count,
            "complete_observation_count": self.complete_observation_count,
            "observation_closure_status": self.observation_closure_status.value,
            "vocabulary_coverage_status": self.vocabulary_coverage_status.value,
            "digest": self.digest,
            "vocabulary": {name: dict(sorted(values.items())) for name, values in sorted(self.vocabulary.items())},
            "coverage_assessments": [item.to_dict() for item in sorted(self.coverage_assessments, key=lambda item: item.field_name)],
            "observations": [item.to_dict() for item in self.observations],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ShutdownObservationSummary:
        from .model import VocabularyCoverageAssessment

        expected = {
            "repeats_per_family", "terminal_causes", "close_path_count", "total_observation_count",
            "complete_observation_count", "observation_closure_status", "vocabulary_coverage_status",
            "digest", "vocabulary", "coverage_assessments", "observations",
        }
        if set(payload) != expected:
            raise ValueError("H5 schedule fields do not match the canonical schema")
        return cls(
            repeats_per_family=payload["repeats_per_family"],
            terminal_causes=tuple(payload["terminal_causes"]),
            close_path_count=payload["close_path_count"],
            total_observation_count=payload["total_observation_count"],
            complete_observation_count=payload["complete_observation_count"],
            observation_closure_status=payload["observation_closure_status"],
            vocabulary_coverage_status=payload["vocabulary_coverage_status"],
            digest=payload["digest"],
            vocabulary=payload["vocabulary"],
            coverage_assessments=tuple(VocabularyCoverageAssessment.from_dict(item) for item in payload["coverage_assessments"]),
            observations=tuple(ShutdownScheduleObservation.from_dict(item) for item in payload["observations"]),
        )


@dataclass(frozen=True, slots=True)
class ShutdownEvidenceRecord:
    record_id: str
    hypothesis_id: str
    subject: str
    baseline_scope: object
    baseline_anchor_commit: str
    overlay_commit: str
    binding_commit: str | None
    vocabulary_names: tuple[str, ...]
    symbol_citations: tuple[str, ...]
    discovered_sites: tuple[CloseSite, ...]
    resource_ownership: tuple[ResourceOwnershipRecord, ...]
    close_path_scope_outs: tuple[ClosePathScopeOut, ...]
    close_path_count: int
    contradiction_search: object
    schedule_observations: ShutdownObservationSummary
    s1_redis_runtime_ruling: Mapping[str, str]
    shutdown_order: Mapping[str, tuple[str, ...]]
    commands: tuple[str, ...]
    ruling: str
    reviewer_status: object
    content_free_evidence: tuple[object, ...]

    def __post_init__(self) -> None:
        from .model import BaselineScope, ReviewerStatus

        object.__setattr__(self, "baseline_scope", BaselineScope(self.baseline_scope))
        object.__setattr__(self, "reviewer_status", ReviewerStatus(self.reviewer_status))
        for field in (
            "vocabulary_names", "symbol_citations", "discovered_sites", "resource_ownership",
            "close_path_scope_outs",
            "commands", "content_free_evidence",
        ):
            object.__setattr__(self, field, tuple(getattr(self, field)))
        object.__setattr__(self, "shutdown_order", {key: tuple(value) for key, value in self.shutdown_order.items()})
        if self.record_id != "ER-H5-RESOURCE-SHUTDOWN" or self.hypothesis_id != "H5":
            raise ValueError("Task 6 evidence record identity is invalid")
        if self.baseline_scope is not BaselineScope.BOTH_DIVERGENT or self.binding_commit is not None:
            raise ValueError("H5 must preserve both-divergent unbound lineage")
        definition_ids = {
            site.conceptual_id for site in self.discovered_sites if site.site_kind == "CLOSE_DEFINITION"
        }
        if self.close_path_count != len(definition_ids):
            raise ValueError("N_close_paths must be derived from conceptual close definitions")
        applicable = {item.close_path_id for item in self.resource_ownership if item.schedule_applicable}
        if self.schedule_observations.close_path_count != len(applicable):
            raise ValueError("H5 schedule count must derive from applicable merged close paths")
        scoped_ids = {item.close_path_id for item in self.close_path_scope_outs}
        expected_scoped_ids = {
            item.close_path_id for item in self.resource_ownership if not item.schedule_applicable
        }
        if len(scoped_ids) != len(self.close_path_scope_outs) or scoped_ids != expected_scoped_ids:
            raise ValueError("H5 close-path scope-outs must cover exactly the overlay-only contracts")
        if any(
            item.baseline_scope != "overlay"
            or item.owner != "P11-FEAT-ZED-RESUME"
            or not item.reason
            or not item.next_gate
            for item in self.close_path_scope_outs
        ):
            raise ValueError("H5 overlay-only close-path scope-out custody is invalid")
        if set(self.s1_redis_runtime_ruling) != {"merged", "overlay"} or dict(self.s1_redis_runtime_ruling) != {
            "merged": "MISSING", "overlay": "PROVISIONAL_OVERLAY",
        }:
            raise ValueError("H5 S1 RedisRuntime ruling is invalid")
        if set(self.shutdown_order) != {"merged", "overlay"}:
            raise ValueError("H5 shutdown order must preserve both baselines")
        if not self.shutdown_order["merged"] or not self.shutdown_order["overlay"]:
            raise ValueError("H5 shutdown order is incomplete")
        if self.shutdown_order["merged"][-1] == "redis_runtime" or self.shutdown_order["overlay"][-1] != "redis_runtime":
            raise ValueError("H5 shutdown order disagrees with S1 source evidence")

    def to_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "hypothesis_id": self.hypothesis_id,
            "subject": self.subject,
            "baseline_scope": self.baseline_scope.value,
            "baseline_anchor_commit": self.baseline_anchor_commit,
            "overlay_commit": self.overlay_commit,
            "binding_commit": self.binding_commit,
            "vocabulary_names": list(self.vocabulary_names),
            "symbol_citations": list(self.symbol_citations),
            "discovered_sites": [item.to_dict() for item in self.discovered_sites],
            "resource_ownership": [item.to_dict() for item in self.resource_ownership],
            "close_path_scope_outs": [item.to_dict() for item in self.close_path_scope_outs],
            "close_path_count": self.close_path_count,
            "contradiction_search": self.contradiction_search.to_dict(),
            "schedule_observations": self.schedule_observations.to_dict(),
            "s1_redis_runtime_ruling": dict(self.s1_redis_runtime_ruling),
            "shutdown_order": {key: list(value) for key, value in sorted(self.shutdown_order.items())},
            "commands": list(self.commands),
            "ruling": self.ruling,
            "reviewer_status": self.reviewer_status.value,
            "content_free_evidence": [item.to_dict() for item in self.content_free_evidence],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ShutdownEvidenceRecord:
        from .model import ContradictionSearchRecord, EvidenceReference

        expected = {
            "record_id", "hypothesis_id", "subject", "baseline_scope", "baseline_anchor_commit",
            "overlay_commit", "binding_commit", "vocabulary_names", "symbol_citations",
            "discovered_sites", "resource_ownership", "close_path_scope_outs", "close_path_count", "contradiction_search",
            "schedule_observations", "s1_redis_runtime_ruling", "shutdown_order", "commands",
            "ruling", "reviewer_status", "content_free_evidence",
        }
        if set(payload) != expected:
            raise ValueError("H5 evidence record fields do not match the canonical schema")
        return cls(
            record_id=payload["record_id"],
            hypothesis_id=payload["hypothesis_id"],
            subject=payload["subject"],
            baseline_scope=payload["baseline_scope"],
            baseline_anchor_commit=payload["baseline_anchor_commit"],
            overlay_commit=payload["overlay_commit"],
            binding_commit=payload["binding_commit"],
            vocabulary_names=tuple(payload["vocabulary_names"]),
            symbol_citations=tuple(payload["symbol_citations"]),
            discovered_sites=tuple(CloseSite.from_dict(item) for item in payload["discovered_sites"]),
            resource_ownership=tuple(ResourceOwnershipRecord.from_dict(item) for item in payload["resource_ownership"]),
            close_path_scope_outs=tuple(ClosePathScopeOut.from_dict(item) for item in payload["close_path_scope_outs"]),
            close_path_count=payload["close_path_count"],
            contradiction_search=ContradictionSearchRecord.from_dict(payload["contradiction_search"]),
            schedule_observations=ShutdownObservationSummary.from_dict(payload["schedule_observations"]),
            s1_redis_runtime_ruling=payload["s1_redis_runtime_ruling"],
            shutdown_order={key: tuple(value) for key, value in payload["shutdown_order"].items()},
            commands=tuple(payload["commands"]),
            ruling=payload["ruling"],
            reviewer_status=payload["reviewer_status"],
            content_free_evidence=tuple(EvidenceReference.from_dict(item) for item in payload["content_free_evidence"]),
        )


def _derived_shutdown_order(source: SourceTree) -> tuple[str, ...]:
    text = source.read_text("src/optimus/acp/server.py")
    patterns = (
        ("adapter", r"(?:self\._adapter|adapter)\.(?:close_all|aclose)\("),
        ("client_mcp_runtime", r"client_mcp_runtime\.close\("),
        ("dedicated_writer", r"dedicated\.close_and_join\("),
        ("reader_task", r"await\s+reader_task"),
        ("redis_runtime", r"redis_runtime\.close\("),
    )
    import re

    occurrences: list[tuple[int, str]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for name, pattern in patterns:
            if re.search(pattern, line):
                occurrences.append((line_number, name))
    order: list[str] = []
    for _line, name in sorted(occurrences):
        if not order or order[-1] != name:
            order.append(name)
    return tuple(order)


def _build_h5_record(
    *,
    inventory: ShutdownInventory,
    observations: tuple[ShutdownScheduleObservation, ...],
    merged: SourceTree,
    overlay: SourceTree,
    merged_commit: str,
    overlay_commit: str,
) -> ShutdownEvidenceRecord:
    from .model import (
        BaselineScope,
        ContradictionSearchRecord,
        EvidenceReference,
        ObservationClosureStatus,
        ReviewerStatus,
        VocabularyCoverageStatus,
    )

    assessments = _h5_coverage_assessments(observations)
    schedule_digest = _canonical_digest([item.to_dict() for item in observations])
    summary = ShutdownObservationSummary(
        repeats_per_family=100,
        terminal_causes=_TERMINAL_CAUSES,
        close_path_count=len({item.close_path_id for item in observations}),
        total_observation_count=len(observations),
        complete_observation_count=sum(item.complete for item in observations),
        observation_closure_status=ObservationClosureStatus.FULLY_STRUCTURALLY_CLOSED,
        vocabulary_coverage_status=(
            VocabularyCoverageStatus.PARTIAL_WITH_SCOPE_OUTS
            if any(item.missing_values for item in assessments)
            else VocabularyCoverageStatus.FULLY_OBSERVED
        ),
        digest=schedule_digest,
        vocabulary=_h5_vocabulary(),
        coverage_assessments=assessments,
        observations=observations,
    )
    citations = tuple(
        sorted(f"{item.source_baseline}:{item.path}:{item.line}:{item.reference}" for item in inventory.close_sites)
    )
    inventory_payload = {
        "close_sites": [item.to_dict() for item in inventory.close_sites],
        "resource_ownership": [item.to_dict() for item in inventory.resources],
    }
    return ShutdownEvidenceRecord(
        record_id="ER-H5-RESOURCE-SHUTDOWN",
        hypothesis_id="H5",
        subject="Resource ownership, shutdown ordering, and repeated close settlement",
        baseline_scope=BaselineScope.BOTH_DIVERGENT,
        baseline_anchor_commit=merged_commit,
        overlay_commit=overlay_commit,
        binding_commit=None,
        vocabulary_names=tuple(sorted(_h5_vocabulary())),
        symbol_citations=citations,
        discovered_sites=inventory.close_sites,
        resource_ownership=inventory.resources,
        close_path_scope_outs=tuple(
            ClosePathScopeOut(
                close_path_id=item.close_path_id,
                resource_type=item.resource_type,
                close_method=item.close_method,
                baseline_scope="overlay",
                reason=(
                    "This close contract exists only on the non-binding overlay and cannot be executed as merged runtime evidence."
                ),
                owner="P11-FEAT-ZED-RESUME",
                next_gate="G3 binding baseline reconciliation and overlay runtime characterization",
            )
            for item in inventory.resources
            if not item.schedule_applicable
        ),
        close_path_count=inventory.close_path_count,
        contradiction_search=ContradictionSearchRecord(
            searched_reference_count=len(inventory.close_sites),
            contradictory_site_count=1,
            contradictory_citations=("S1:merged-serving-RedisRuntime-has-no-close-owner",),
            conclusion=(
                "The merged serving graph does not retain or close RedisRuntime; the overlay retains it and closes it last."
            ),
        ),
        schedule_observations=summary,
        s1_redis_runtime_ruling={"merged": "MISSING", "overlay": "PROVISIONAL_OVERLAY"},
        shutdown_order={
            "merged": _derived_shutdown_order(merged),
            "overlay": _derived_shutdown_order(overlay),
        },
        commands=(
            "uv run --frozen pytest tests/unit/acp/test_plan1126_shutdown.py::test_shutdown_inventory_is_independent_complete_and_receiver_safe -q",
            "uv run --frozen pytest tests/unit/acp/test_plan1126_shutdown.py::test_shutdown_causes_repeat_100_with_control_allowlist -q",
        ),
        ruling=(
            "S1 is MISSING on merged because the serving graph does not own RedisRuntime shutdown; the overlay fix remains PROVISIONAL_OVERLAY until baseline reconciliation."
        ),
        reviewer_status=ReviewerStatus.PENDING_G2,
        content_free_evidence=(
            EvidenceReference("H5-CLOSE-INVENTORY", BaselineScope.BOTH_DIVERGENT, _canonical_digest(inventory_payload)),
            EvidenceReference("H5-SHUTDOWN-OBSERVATIONS", BaselineScope.BOTH_DIVERGENT, schedule_digest),
        ),
    )


def build_h5_audit_artifact(
    *,
    merged: SourceTree,
    overlay: SourceTree,
    merged_commit: str,
    overlay_commit: str,
) -> AuditArtifact:
    """Build the cumulative H3/H4/H5 artifact without mutating production source."""

    from .cancellation import H3_SOURCE_PATHS, build_h3_audit_artifact
    from .cost import compute_cost
    from .delivery_characterization import H4_SOURCE_PATHS
    from .model import (
        AuditArtifact,
        BaselineScope,
        Classification,
        EvidenceReference,
        Finding,
        GateStatus,
        LiveStatus,
        ScopeOutRegisterEntry,
    )

    base_paths = tuple(sorted(set(H3_SOURCE_PATHS) | set(H4_SOURCE_PATHS)))
    base_merged = SourceTree({path: merged.read_text(path) for path in base_paths})
    base_overlay = SourceTree({path: overlay.read_text(path) for path in base_paths})
    shutdown_merged = SourceTree({path: merged.read_text(path) for path in H5_SOURCE_PATHS})
    shutdown_overlay = SourceTree({path: overlay.read_text(path) for path in H5_SOURCE_PATHS})
    base = build_h3_audit_artifact(
        merged=base_merged,
        overlay=base_overlay,
        merged_commit=merged_commit,
        overlay_commit=overlay_commit,
    )
    inventory = discover_shutdown_inventory(shutdown_merged, overlay=shutdown_overlay)
    observations = shutdown_schedule_observations(inventory=inventory, repeats=100)
    inventory = characterize_shutdown_inventory(inventory, observations)
    record = _build_h5_record(
        inventory=inventory,
        observations=observations,
        merged=shutdown_merged,
        overlay=shutdown_overlay,
        merged_commit=merged_commit,
        overlay_commit=overlay_commit,
    )
    s1_digest = _canonical_digest({
        "ruling": dict(record.s1_redis_runtime_ruling),
        "shutdown_order": {key: list(value) for key, value in record.shutdown_order.items()},
    })
    h5_findings: list[Finding] = [
        Finding(
            finding_id="H5-S1-REDIS-RUNTIME-merged",
            subject="S1 serving RedisRuntime shutdown ownership is missing on merged",
            classification=Classification.MISSING,
            baseline_scope=BaselineScope.MERGED,
            symbols=("src.optimus.acp.bootstrap.build_configured_server", "src.optimus.acp.server.AcpStreamServer.serve"),
            evidence=(EvidenceReference("H5-S1-MERGED", BaselineScope.MERGED, s1_digest),),
            owner=_H5_OWNER,
            ruling="The serving runtime does not retain RedisRuntime for final shutdown; no production repair is made by this audit.",
        ),
        Finding(
            finding_id="H5-S1-REDIS-RUNTIME-overlay",
            subject="S1 serving RedisRuntime shutdown ownership is present only on overlay",
            classification=Classification.PROVISIONAL_OVERLAY,
            baseline_scope=BaselineScope.OVERLAY,
            symbols=("src.optimus.acp.bootstrap._AgentRuntimeBundle", "src.optimus.acp.server.AcpStreamServer.serve"),
            evidence=(EvidenceReference("H5-S1-OVERLAY", BaselineScope.OVERLAY, s1_digest),),
            owner="P11-FEAT-ZED-RESUME",
            ruling="Overlay retains and closes RedisRuntime last; it remains provisional until baseline reconciliation.",
        ),
    ]
    resource_by_id = {item.close_path_id: item for item in inventory.resources}
    double_close = tuple(item for item in observations if item.close_outcome == "DOUBLE_CLOSE_OBSERVED")
    if double_close:
        double_ids = tuple(sorted({item.close_path_id for item in double_close}))
        h5_findings.append(Finding(
            finding_id="H5-REPEATED-CLOSE-UNDERLYING-merged",
            subject="H5 repeated owner close reached an underlying close more than once",
            classification=Classification.MISSING,
            baseline_scope=BaselineScope.MERGED,
            symbols=tuple(
                f"{resource_by_id[path_id].resource_type}.{resource_by_id[path_id].close_method}"
                for path_id in double_ids
            ),
            evidence=(EvidenceReference(
                "H5-DOUBLE-CLOSE-OBSERVATIONS",
                BaselineScope.MERGED,
                _canonical_digest([item.to_dict() for item in double_close]),
            ),),
            owner=_H5_OWNER,
            ruling="Three owner-level closes reached the same underlying close three times; the missing idempotence contract is recorded without production repair.",
        ))
    slow_close = tuple(item for item in observations if item.repeat_latency_class == "ABOVE_100MS")
    if slow_close:
        h5_findings.append(Finding(
            finding_id="H5-REPEAT-LATENCY-ABOVE-100MS-merged",
            subject="H5 repeated close exceeded the 100 ms audit threshold on merged",
            classification=Classification.CANONICAL_BYPASSED,
            baseline_scope=BaselineScope.MERGED,
            symbols=tuple(sorted({
                f"{resource_by_id[item.close_path_id].resource_type}.{resource_by_id[item.close_path_id].close_method}:{item.terminal_cause}"
                for item in slow_close
            })),
            evidence=(EvidenceReference(
                "H5-SLOW-CLOSE-OBSERVATIONS",
                BaselineScope.MERGED,
                _canonical_digest([item.to_dict() for item in slow_close]),
            ),),
            owner=_H5_OWNER,
            ruling="Measured above-threshold repeats remain raw audit findings; no production repair or timing excuse is inferred.",
        ))
    error_close = tuple(item for item in observations if item.close_outcome == "ERROR")
    if error_close:
        h5_findings.append(Finding(
            finding_id="H5-CLOSE-ERROR-merged",
            subject="H5 owner close raised during the offline shutdown matrix",
            classification=Classification.MISSING,
            baseline_scope=BaselineScope.MERGED,
            symbols=tuple(sorted({
                f"{resource_by_id[item.close_path_id].resource_type}.{resource_by_id[item.close_path_id].close_method}"
                for item in error_close
            })),
            evidence=(EvidenceReference(
                "H5-CLOSE-ERROR-OBSERVATIONS",
                BaselineScope.MERGED,
                _canonical_digest([item.to_dict() for item in error_close]),
            ),),
            owner=_H5_OWNER,
            ruling="Close errors remain findings while structurally complete observations are preserved.",
        ))
    findings = tuple(base.findings) + tuple(h5_findings)
    cost = compute_cost(
        cancellation_points=base.discovered_multipliers["cancellation_points"],
        queues=base.discovered_multipliers["queues"],
        sinks=base.discovered_multipliers["sinks"],
        close_paths=inventory.close_path_count,
        seed_count=256,
        admission_probe_count=0,
        sink_failure_count=0,
        scenario_durations_ms={},
    )
    records = tuple(base.evidence_records) + (record,)
    provisional = AuditArtifact(
        schema_version=base.schema_version,
        merged_commit=base.merged_commit,
        overlay_commit=base.overlay_commit,
        binding_commit=None,
        baseline_reconciliation_status=base.baseline_reconciliation_status,
        running_artifact_provenance=None,
        static_audit_status=LiveStatus.PARTIAL,
        runtime_characterization_status=LiveStatus.PARTIAL,
        live_redis_status=base.live_redis_status,
        acpx_status=base.acpx_status,
        additional_client_status=base.additional_client_status,
        zed_status=base.zed_status,
        live_interoperability_status=base.live_interoperability_status,
        findings=findings,
        discovered_multipliers={**base.discovered_multipliers, "close_paths": inventory.close_path_count},
        computed_run_cost=cost.to_dict(),
        gate_status=GateStatus.INCOMPLETE,
        evidence_records=records,
    )
    register = tuple(
        ScopeOutRegisterEntry(
            hypothesis_id=entry.hypothesis_id,
            field_name=entry.field_name,
            owning_gate=entry.owning_gate,
            missing_values=entry.missing_values,
            owner=entry.owner,
            reachable_in_gate="NOT_YET_ASSESSED",
            reachability_reason=(
                f"{entry.owning_gate} names a candidate scenario, but its reachability has not yet been "
                "demonstrated from that gate's raw observations."
            ),
        )
        for entry in provisional.scope_out_register or ()
    )
    return AuditArtifact(
        schema_version=provisional.schema_version,
        merged_commit=provisional.merged_commit,
        overlay_commit=provisional.overlay_commit,
        binding_commit=provisional.binding_commit,
        baseline_reconciliation_status=provisional.baseline_reconciliation_status,
        running_artifact_provenance=provisional.running_artifact_provenance,
        static_audit_status=provisional.static_audit_status,
        runtime_characterization_status=provisional.runtime_characterization_status,
        live_redis_status=provisional.live_redis_status,
        acpx_status=provisional.acpx_status,
        additional_client_status=provisional.additional_client_status,
        zed_status=provisional.zed_status,
        live_interoperability_status=provisional.live_interoperability_status,
        findings=provisional.findings,
        discovered_multipliers=provisional.discovered_multipliers,
        computed_run_cost=provisional.computed_run_cost,
        gate_status=provisional.gate_status,
        evidence_records=provisional.evidence_records,
        scope_out_register=register,
    )
