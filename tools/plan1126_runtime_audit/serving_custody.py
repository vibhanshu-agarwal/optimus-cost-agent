"""S1 serving custody, measured on CURRENT source (Seam 2, checkpoint B, round 2).

The historical Plan 11.26 H5 record rules S1 -- "the serving graph retains and closes
``RedisRuntime`` last" -- MISSING on the merged baseline and PROVISIONAL_OVERLAY on the
sandbox overlay. Those rulings are bound to their historical commits and never change.
This module is the *current* counterpart: a fresh measurement entry whose classification
is DERIVED from what the measured revision's source shows AND what its serving lifecycle
demonstrates when actually executed. Nothing here is hard-coded to either verdict.

Round 2 corrections (R2):

* the configured handoff is measured through the REAL ``build_configured_server`` --
  the runtime the composition built must be the object the server retains and the object
  the runner's store and sink submit to; a null or foreign handle is NOT_DEMONSTRATED;
* the rollback scenario records the runtime's disposition BEFORE any probe fallback
  cleanup runs, so probe cleanup can never manufacture the product's rollback;
* a failing earlier teardown stage is its own scenario: Redis must still close and the
  stage's failure must survive.

Round 2 correction (R3): every scenario runs under an execution-closure recorder; the
measurement refuses to produce evidence when anything it executed -- product file or
installed distribution -- is outside the verified binding.

Execution runs on a real ``RedisRuntime`` whose pool and client are counting fakes. That is
evidence about the measured revision's lifecycle wiring only: not live Redis acceptance,
not proof of physical socket behaviour, and not a claim about any baseline.
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import hashlib
import json
import re
import tempfile
import threading
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

from .measurement import ExecutionClosureRecorder, VerifiedExecution, verify_execution_closure
from .source import ExecutingSourceMismatch, SourceTree, source_fingerprint, verify_executing_module

#: The allowlisted measurement entry whose context authorizes this module's execution.
S1_MEASUREMENT_ENTRY = "s1.serving_custody"

#: The serving-custody surface: where the runtime is built, retained, consumed and closed.
S1_SOURCE_PATHS = (
    "src/optimus/acp/bootstrap.py",
    "src/optimus/acp/failure_notes.py",
    "src/optimus/acp/harness_runtime.py",
    "src/optimus/acp/operator_verify.py",
    "src/optimus/acp/preflight.py",
    "src/optimus/acp/server.py",
    "src/optimus/agent/state_store.py",
    "src/optimus/redis/async_bridge.py",
    "src/optimus/redis/runtime.py",
    "src/optimus/telemetry/redis_sink.py",
)

INVENTORY_KIND = "serving-custody"


class CustodyScenario(StrEnum):
    """The universe of observations. Identifiers derive from THIS enum, never from rows."""

    SOURCE_RETENTION = "source_retention"
    CONFIGURED_HANDOFF_TEARDOWN = "configured_handoff_teardown"
    NORMAL_EOF_TEARDOWN = "normal_eof_teardown"
    CANCELLATION_TEARDOWN = "cancellation_teardown"
    PRIOR_STAGE_FAILURE_TEARDOWN = "prior_stage_failure_teardown"
    LATE_SUBMISSION_AFTER_CLOSE = "late_submission_after_close"
    STARTUP_ROLLBACK = "startup_rollback"


class CustodyOutcome(StrEnum):
    DEMONSTRATED = "DEMONSTRATED"
    NOT_DEMONSTRATED = "NOT_DEMONSTRATED"


class CustodySiteKind(StrEnum):
    RETAINED_HANDLE_CONSTRUCTION = "RETAINED_HANDLE_CONSTRUCTION"
    RETAINED_HANDLE_FIELD = "RETAINED_HANDLE_FIELD"
    TEARDOWN_STAGE_CALL = "TEARDOWN_STAGE_CALL"
    SUBMISSION_INJECTION = "SUBMISSION_INJECTION"
    SHARED_LOOP_REACH = "SHARED_LOOP_REACH"
    NULL_HANDLE_CONSTRUCTION = "NULL_HANDLE_CONSTRUCTION"


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CustodySite:
    path: str
    line: int
    symbol: str
    kind: CustodySiteKind
    reference: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path, "line": self.line, "symbol": self.symbol,
            "kind": self.kind.value, "reference": self.reference,
        }


@dataclass(frozen=True, slots=True)
class ServingCustodyInventory:
    """Static facts about the measured tree, derived by AST -- never by line literal."""

    source_fingerprint: str
    sites: tuple[CustodySite, ...]
    serving_shutdown_order: tuple[str, ...]

    @property
    def retained_handle(self) -> bool:
        kinds = {site.kind for site in self.sites}
        return (
            CustodySiteKind.RETAINED_HANDLE_CONSTRUCTION in kinds
            and CustodySiteKind.RETAINED_HANDLE_FIELD in kinds
            and CustodySiteKind.NULL_HANDLE_CONSTRUCTION not in kinds
        )

    @property
    def redis_stage_last(self) -> bool:
        return bool(self.serving_shutdown_order) and self.serving_shutdown_order[-1] == "redis_runtime"

    @property
    def shared_loop_reaches(self) -> int:
        return sum(site.kind is CustodySiteKind.SHARED_LOOP_REACH for site in self.sites)

    @property
    def submission_injections(self) -> int:
        return sum(site.kind is CustodySiteKind.SUBMISSION_INJECTION for site in self.sites)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": INVENTORY_KIND,
            "source_fingerprint": self.source_fingerprint,
            "sites": [site.to_dict() for site in self.sites],
            "serving_shutdown_order": list(self.serving_shutdown_order),
            "retained_handle": self.retained_handle,
            "redis_stage_last": self.redis_stage_last,
            "shared_loop_reaches": self.shared_loop_reaches,
            "submission_injections": self.submission_injections,
        }


# --- static discovery ----------------------------------------------------------------


class _CustodyVisitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.scope: list[str] = []
        self.sites: list[CustodySite] = []

    def _symbol(self) -> str:
        module = self.path.removesuffix(".py").replace("/", ".")
        return ".".join((module, *self.scope))

    def _add(self, node: ast.AST, kind: CustodySiteKind, reference: str) -> None:
        self.sites.append(CustodySite(self.path, node.lineno, self._symbol(), kind, reference))

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
                and "redis_runtime" in target.attr
                and self.scope
                and self.scope[-1] == "__init__"
            ):
                self._add(node, CustodySiteKind.RETAINED_HANDLE_FIELD, f"self.{target.attr}")
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name) and node.target.id == "redis_runtime" and self.scope:
            self._add(node, CustodySiteKind.RETAINED_HANDLE_FIELD, f"{self.scope[-1]}.redis_runtime")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        reference = ast.unparse(node.func)
        leaf = reference.rsplit(".", 1)[-1]
        keywords = {keyword.arg: keyword.value for keyword in node.keywords if keyword.arg}
        if leaf == "AcpStreamServer" and "redis_runtime" in keywords:
            value = keywords["redis_runtime"]
            # R2: keyword PRESENCE proved nothing -- `redis_runtime=None` passed the check.
            # A literal None (or any constant) is a null handle, recorded as such.
            if isinstance(value, ast.Constant):
                self._add(node, CustodySiteKind.NULL_HANDLE_CONSTRUCTION, f"AcpStreamServer(redis_runtime={value.value!r})")
            else:
                self._add(node, CustodySiteKind.RETAINED_HANDLE_CONSTRUCTION, f"AcpStreamServer(redis_runtime={ast.unparse(value)})")
        if leaf in {"close_async", "close"} and "redis_runtime" in reference:
            self._add(node, CustodySiteKind.TEARDOWN_STAGE_CALL, reference)
        if leaf == "_close_redis_runtime_stage":
            self._add(node, CustodySiteKind.TEARDOWN_STAGE_CALL, reference)
        if "submit" in keywords and leaf in {"RedisTelemetryEventSink", "RedisAgentStateStore"}:
            self._add(node, CustodySiteKind.SUBMISSION_INJECTION, f"{leaf}(submit=...)")
        if leaf == "sync_await":
            self._add(node, CustodySiteKind.SHARED_LOOP_REACH, reference)
        self.generic_visit(node)


_STAGE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("adapter", r"(?:self\._adapter|adapter)\.(?:close_all|aclose)\("),
    ("client_mcp_runtime", r"client_mcp_runtime\.close\("),
    ("dedicated_writer", r"dedicated\.close_and_join\("),
    ("reader_task", r"await\s+reader_task"),
    ("redis_runtime", r"_close_redis_runtime_stage\(|redis_runtime\.close(?:_async)?\("),
)


def _spans(tree: ast.AST, names: tuple[str, ...]) -> dict[str, tuple[int, int]]:
    found: dict[str, tuple[int, int]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name in names:
            found[node.name] = (node.lineno, node.end_lineno or node.lineno)
    return found


def _serving_shutdown_order(server_text: str) -> tuple[str, ...]:
    """The stage order of the NDJSON serving lifetime, inner body first, then its enclosing finally.

    Round 2 (R1) moved the Redis stage into the public entry's own ``finally`` around the
    serving body ``_serve_ndjson``. Semantically the body's stages run before that finally,
    so the order is: occurrences inside the body, then occurrences in the entry outside it.
    """
    tree = ast.parse(server_text)
    spans = _spans(tree, ("serve_ndjson", "_serve_ndjson"))
    if "serve_ndjson" not in spans:
        return ()
    lines = server_text.splitlines()

    def occurrences(span: tuple[int, int], exclude: tuple[int, int] | None) -> list[tuple[int, str]]:
        rows: list[tuple[int, str]] = []
        for line_number in range(span[0], span[1] + 1):
            if exclude is not None and exclude[0] <= line_number <= exclude[1]:
                continue
            for name, pattern in _STAGE_PATTERNS:
                if re.search(pattern, lines[line_number - 1]):
                    rows.append((line_number, name))
        return sorted(rows)

    ordered: list[tuple[int, str]] = []
    inner = spans.get("_serve_ndjson")
    if inner is not None:
        ordered.extend(occurrences(inner, None))
    ordered.extend(occurrences(spans["serve_ndjson"], inner))
    order: list[str] = []
    for _line, name in ordered:
        if not order or order[-1] != name:
            order.append(name)
    return tuple(order)


def discover_serving_custody_inventory(source: SourceTree) -> ServingCustodyInventory:
    sites: list[CustodySite] = []
    for path in source.paths():
        visitor = _CustodyVisitor(path)
        visitor.visit(ast.parse(source.read_text(path), filename=path))
        sites.extend(visitor.sites)
    server_path = "src/optimus/acp/server.py"
    order = _serving_shutdown_order(source.read_text(server_path)) if server_path in source.paths() else ()
    return ServingCustodyInventory(
        source_fingerprint=source_fingerprint(source, source.paths()),
        sites=tuple(sorted(sites, key=lambda item: (item.path, item.line, item.kind.value, item.reference))),
        serving_shutdown_order=order,
    )


# --- observation rows ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CustodyObservation:
    scenario: CustodyScenario
    outcome: CustodyOutcome
    detail: str
    evidence_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.scenario.value,
            "scenario": self.scenario.value,
            "outcome": self.outcome.value,
            "detail": self.detail,
            "evidence_digest": self.evidence_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CustodyObservation:
        return cls(
            scenario=CustodyScenario(payload["scenario"]),
            outcome=CustodyOutcome(payload["outcome"]),
            detail=str(payload["detail"]),
            evidence_digest=str(payload["evidence_digest"]),
        )


#: Round 7, R15: the ONLY error information a custody observation may retain. Derived from the
#: exception's TYPE (by isinstance against a fixed list, never from its name, message or repr),
#: so no diagnostic text -- however long or sensitive -- can reach the observation detail and,
#: through it, the persisted evidence sidecar. Unknown types collapse to "other".
_ERROR_CATEGORIES: tuple[tuple[str, type[BaseException]], ...] = (
    ("cancelled", asyncio.CancelledError),
    ("timeout", TimeoutError),
    ("os-error", OSError),
    ("value-error", ValueError),
    ("runtime-error", RuntimeError),
)
TASK_OUTCOME_VOCABULARY: frozenset[str] = frozenset({"pending", "cancelled", "returned"})
ERROR_CATEGORY_VOCABULARY: frozenset[str] = frozenset(
    {"none", *(name for name, _ in _ERROR_CATEGORIES), "other"}
)
REFUSAL_VOCABULARY: frozenset[str] = frozenset({"RedisLoopOwnerClosed", "ADMITTED", "other-exception"})


def error_category(exc: BaseException | None) -> str:
    """A content-free, allowlisted category for an exception -- by TYPE only, never by text."""
    if exc is None:
        return "none"
    for name, kind in _ERROR_CATEGORIES:
        if isinstance(exc, kind):
            return name
    return "other"


def _observation(scenario: CustodyScenario, demonstrated: bool, facts: Mapping[str, Any]) -> CustodyObservation:
    outcome = CustodyOutcome.DEMONSTRATED if demonstrated else CustodyOutcome.NOT_DEMONSTRATED
    detail = ";".join(f"{key}={facts[key]}" for key in sorted(facts))
    return CustodyObservation(scenario, outcome, detail, _digest({"scenario": scenario.value, **dict(facts)}))


# --- classification and ruling: DERIVED, never asserted ------------------------------


def _outcomes(observations) -> dict[str, str]:
    outcomes: dict[str, str] = {}
    for row in observations:
        if isinstance(row, CustodyObservation):
            outcomes[row.scenario.value] = row.outcome.value
        else:
            outcomes[str(row["scenario"])] = str(row["outcome"])
    return outcomes


def derive_s1_classification(observations: tuple[CustodyObservation, ...] | tuple[Mapping[str, Any], ...]) -> str:
    """CANONICAL only when EVERY scenario in the universe is demonstrated; otherwise MISSING."""
    outcomes = _outcomes(observations)
    universe = [scenario.value for scenario in CustodyScenario]
    if all(outcomes.get(name) == CustodyOutcome.DEMONSTRATED.value for name in universe):
        return "CANONICAL"
    return "MISSING"


def derive_s1_ruling(
    observations: tuple[CustodyObservation, ...] | tuple[Mapping[str, Any], ...],
    inventory: Mapping[str, Any],
) -> str:
    """The record's ruling text, built from the rows and the inventory facts only."""
    classification = derive_s1_classification(observations)
    outcomes = _outcomes(observations)
    demonstrated = sorted(name for name, value in outcomes.items() if value == "DEMONSTRATED")
    missing = sorted(
        scenario.value for scenario in CustodyScenario if outcomes.get(scenario.value) != "DEMONSTRATED"
    )
    return (
        f"S1 serving RedisRuntime custody on the measured revision: {classification}. "
        f"Demonstrated: {', '.join(demonstrated) or 'none'}. "
        f"Not demonstrated: {', '.join(missing) or 'none'}. "
        f"Source facts: retained_handle={bool(inventory.get('retained_handle'))}, "
        f"redis_stage_last={bool(inventory.get('redis_stage_last'))}, "
        f"shared_loop_reaches={int(inventory.get('shared_loop_reaches', 0))}, "
        f"serving_shutdown_order={list(inventory.get('serving_shutdown_order', ()))}. "
        "Measured in a fresh child interpreter under a verified execution context on offline "
        "counting fakes with a real loop owner; this is evidence about the measured revision's "
        "lifecycle wiring only -- not live Redis acceptance, not physical socket behaviour, and "
        "not a claim about any historical baseline."
    )


# --- execution -------------------------------------------------------------------------


class _CountingResource:
    def __init__(self) -> None:
        self.count = 0
        self.threads: list[int] = []

    async def aclose(self) -> None:
        self.count += 1
        self.threads.append(threading.get_ident())


class _EofReader:
    async def readline(self) -> bytes:
        return b""


class _NeverReader:
    """A reader that never yields; teardown must come from cancellation."""

    def __init__(self) -> None:
        self._event = asyncio.Event()

    async def readline(self) -> bytes:
        await self._event.wait()
        return b""


class _NullWriter:
    async def write_line(self, message: Mapping[str, Any]) -> None:
        return None


class _StubGateway:
    def create_response(self, **kwargs: Any) -> Any:  # pragma: no cover - never reached offline
        raise AssertionError("the serving custody probe never calls the Gateway")


class _OfflineMcpRuntime:
    """A client-MCP runtime double for the configured composition: counts its closes."""

    disposition = object()
    supervisor = object()
    mcp_http_enabled = False
    mcp_sse_enabled = False

    def __init__(self) -> None:
        self.closes = 0

    def close(self) -> Any:
        self.closes += 1
        from optimus.mcp.client_disposition import ClientMcpShutdownOutcome
        from optimus.mcp.client_supervisor import MCPSupervisorState

        return ClientMcpShutdownOutcome(
            sdk_closed=True, endpoint_closed=True, supervisor_closed=True,
            supervisor_state=MCPSupervisorState.DEAD, complete=True,
        )


_PROBE_ENVIRON = {
    "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
    "OPTIMUS_API_KEY": "plan1126-s1-probe",  # pragma: allowlist secret - offline probe credential
    "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
}


def _fresh_runtime():
    from optimus.redis.async_bridge import RedisLoopOwner
    from optimus.redis.runtime import RedisRuntime

    client, pool = _CountingResource(), _CountingResource()
    runtime = RedisRuntime(pool=pool, client=client, owner=RedisLoopOwner(name="plan1126-s1-probe"))
    return runtime, client, pool


def _server_for(runtime: Any, workspace: Path) -> Any:
    from optimus.acp.dispatcher import JsonRpcDispatcher
    from optimus.acp.server import AcpStreamServer
    from optimus.agent.runner import AgentRunner
    from optimus.agent.state_store import InMemoryAgentStateStore
    from optimus.guardrails.pre_tool import PreToolGuard

    gateway = _StubGateway()
    guard = PreToolGuard.for_workspace(workspace_root=workspace, allowed_network_hosts=())
    runner = AgentRunner(gateway_client=gateway, model="glm-5.2", guard=guard, state_store=InMemoryAgentStateStore())
    dispatcher = JsonRpcDispatcher(
        gateway_client=gateway, agent_runner=runner, pre_tool_guard=guard, workspace_root=workspace
    )
    return AcpStreamServer(dispatcher=dispatcher, redis_runtime=runtime)


@contextlib.contextmanager
def _stage_spy():
    """Record the order of the adapter stage and the Redis stage, restoring both afterwards."""
    from optimus.acp import spec
    from optimus.redis.runtime import RedisRuntime

    sequence: list[str] = []
    real_close_all = vars(spec.AcpDuplexAdapter)["close_all"]
    real_close_async = vars(RedisRuntime)["close_async"]

    def spy_close_all(inner_self):
        sequence.append("adapter")
        return real_close_all(inner_self)

    async def spy_close_async(inner_self, *, timeout=None):
        sequence.append("redis_runtime")
        return await real_close_async(inner_self, timeout=timeout)

    spec.AcpDuplexAdapter.close_all = spy_close_all  # type: ignore[method-assign]
    RedisRuntime.close_async = spy_close_async  # type: ignore[method-assign]
    try:
        yield sequence
    finally:
        spec.AcpDuplexAdapter.close_all = real_close_all  # type: ignore[method-assign]
        RedisRuntime.close_async = real_close_async  # type: ignore[method-assign]


@contextlib.contextmanager
def _composition_patches(runtime: Any, mcp: _OfflineMcpRuntime):
    """Patch ONLY the live edges of the real composition: preflight, from_url, client MCP."""
    from optimus.acp import bootstrap, preflight
    from optimus.redis.runtime import RedisRuntime

    real_preflight = preflight.run_preflight
    real_from_url = vars(RedisRuntime)["from_url"]
    real_mcp = bootstrap.build_client_mcp_runtime
    preflight.run_preflight = lambda environ, **kwargs: _PROBE_ENVIRON["OPTIMUS_REDIS_URL"]  # type: ignore[assignment]
    RedisRuntime.from_url = classmethod(lambda cls, url, **kwargs: runtime)  # type: ignore[method-assign]
    bootstrap.build_client_mcp_runtime = lambda **kwargs: mcp  # type: ignore[assignment]
    try:
        yield
    finally:
        preflight.run_preflight = real_preflight  # type: ignore[assignment]
        RedisRuntime.from_url = real_from_url  # type: ignore[method-assign]
        bootstrap.build_client_mcp_runtime = real_mcp  # type: ignore[assignment]


def _shared_owner_untouched() -> bool:
    from optimus.redis import async_bridge

    return async_bridge._shared_tool_owner is None


def _disposition(runtime: Any, client: _CountingResource, pool: _CountingResource) -> dict[str, Any]:
    record = runtime.teardown_record
    return {
        "state": runtime.state.value,
        "record_clean": bool(record is not None and record.is_clean),
        "client_closes": client.count,
        "pool_closes": pool.count,
        "owner_terminated": runtime.owner.is_terminated,
    }


def _closed_once(facts: Mapping[str, Any]) -> bool:
    return (
        facts["state"] == "CLOSED" and facts["record_clean"] and facts["client_closes"] == 1
        and facts["pool_closes"] == 1 and facts["owner_terminated"]
    )


def _probe_configured_handoff(workspace: Path) -> CustodyObservation:
    """R2: the REAL bootstrap-to-server handoff, with object identity proved end to end."""
    from optimus.acp import bootstrap

    runtime, client, pool = _fresh_runtime()
    mcp = _OfflineMcpRuntime()
    facts: dict[str, Any] = {}
    try:
        with _composition_patches(runtime, mcp):
            server = bootstrap.build_configured_server(environ=dict(_PROBE_ENVIRON), workspace_root=workspace, model="glm-5.2")
        runner = server._dispatcher.agent_runner  # noqa: SLF001 - the composed runner, read only
        store = getattr(runner, "_state_store", None)
        sink = getattr(getattr(runner, "event_sink", None), "redis_sink", None)
        facts["server_holds_same_runtime"] = server.redis_runtime is runtime
        facts["store_submits_to_runtime"] = getattr(store, "_submit", None) == runtime.run_sync
        facts["sink_submits_to_runtime"] = getattr(sink, "submit", None) == runtime.run_sync
        with _stage_spy() as sequence:
            asyncio.run(server.serve_ndjson(_EofReader(), _NullWriter()))
        facts["stage_sequence"] = sequence
        facts["mcp_closes"] = mcp.closes
        facts.update(_disposition(runtime, client, pool))
        facts["shared_owner_untouched"] = _shared_owner_untouched()
    finally:
        # Fallback cleanup for a broken tree. It runs AFTER every fact above was recorded,
        # so it cannot contribute to what is demonstrated.
        with contextlib.suppress(Exception):
            runtime.close(timeout=10.0)
    demonstrated = (
        facts.get("server_holds_same_runtime") is True and facts.get("store_submits_to_runtime") is True
        and facts.get("sink_submits_to_runtime") is True and _closed_once(facts)
        and facts.get("stage_sequence") == ["adapter", "redis_runtime"] and facts.get("mcp_closes") == 1
        and facts.get("shared_owner_untouched") is True
    )
    return _observation(CustodyScenario.CONFIGURED_HANDOFF_TEARDOWN, demonstrated, facts)


def _probe_normal_eof(workspace: Path) -> CustodyObservation:
    runtime, client, pool = _fresh_runtime()
    facts: dict[str, Any] = {}
    try:
        with _stage_spy() as sequence:
            asyncio.run(_server_for(runtime, workspace).serve_ndjson(_EofReader(), _NullWriter()))
        facts.update(_disposition(runtime, client, pool))
        facts["closed_on_owner"] = client.threads == [runtime.owner.thread.ident]
        facts["stage_sequence"] = sequence
        facts["shared_owner_untouched"] = _shared_owner_untouched()
    finally:
        with contextlib.suppress(Exception):
            runtime.close(timeout=10.0)
    demonstrated = (
        _closed_once(facts) and facts.get("closed_on_owner") is True
        and facts.get("stage_sequence") == ["adapter", "redis_runtime"] and facts.get("shared_owner_untouched") is True
    )
    return _observation(CustodyScenario.NORMAL_EOF_TEARDOWN, demonstrated, facts)


#: How long the cancellation probe waits for the cancelled serving task to settle.
_CANCELLATION_SETTLE_SECONDS = 15.0


def _probe_cancellation(workspace: Path) -> CustodyObservation:
    runtime, client, pool = _fresh_runtime()
    facts: dict[str, Any] = {}

    async def _drive() -> tuple[str, str]:
        task = asyncio.create_task(_server_for(runtime, workspace).serve_ndjson(_NeverReader(), _NullWriter()))
        await asyncio.sleep(0.05)
        task.cancel()
        _done, pending = await asyncio.wait({task}, timeout=_CANCELLATION_SETTLE_SECONDS)
        if pending:
            return "pending", "none"
        if task.cancelled():
            return "cancelled", "none"
        # Round 7, R15: a task that RETURNED (with or without an exception) is a visible failure of
        # this scenario, but only an allowlisted category of it is retained -- never the exception's
        # text. `task.exception()` is consulted for its TYPE alone.
        return "returned", error_category(task.exception())

    try:
        with _stage_spy() as sequence:
            facts["task_outcome"], facts["task_error_category"] = asyncio.run(_drive())
        facts.update(_disposition(runtime, client, pool))
        facts["stage_sequence"] = sequence
    finally:
        with contextlib.suppress(Exception):
            runtime.close(timeout=10.0)
    demonstrated = (
        facts.get("task_outcome") == "cancelled" and _closed_once(facts)
        and facts.get("stage_sequence") == ["adapter", "redis_runtime"]
    )
    return _observation(CustodyScenario.CANCELLATION_TEARDOWN, demonstrated, facts)


def _probe_prior_stage_failure(workspace: Path) -> CustodyObservation:
    """R1/R2: an earlier teardown stage raises; Redis must still close and the failure must survive."""
    from optimus.acp import spec

    runtime, client, pool = _fresh_runtime()
    facts: dict[str, Any] = {}
    real_close_all = vars(spec.AcpDuplexAdapter)["close_all"]

    def failing_close_all(inner_self):
        real_close_all(inner_self)
        raise ValueError("plan1126-s1-prior-stage-fault")

    spec.AcpDuplexAdapter.close_all = failing_close_all  # type: ignore[method-assign]
    try:
        try:
            asyncio.run(_server_for(runtime, workspace).serve_ndjson(_EofReader(), _NullWriter()))
        except ValueError as exc:
            facts["earlier_failure_preserved"] = str(exc) == "plan1126-s1-prior-stage-fault"
        else:
            facts["earlier_failure_preserved"] = False
        facts.update(_disposition(runtime, client, pool))
    finally:
        spec.AcpDuplexAdapter.close_all = real_close_all  # type: ignore[method-assign]
        with contextlib.suppress(Exception):
            runtime.close(timeout=10.0)
    demonstrated = facts.get("earlier_failure_preserved") is True and _closed_once(facts)
    return _observation(CustodyScenario.PRIOR_STAGE_FAILURE_TEARDOWN, demonstrated, facts)


def _probe_late_submission(workspace: Path) -> CustodyObservation:
    from optimus.redis.async_bridge import RedisLoopOwnerClosed

    runtime, client, pool = _fresh_runtime()
    owner = runtime.owner
    store = runtime.sync_state_store()
    facts: dict[str, Any] = {}
    try:
        asyncio.run(_server_for(runtime, workspace).serve_ndjson(_EofReader(), _NullWriter()))

        async def _late() -> None:  # pragma: no cover - must never be entered
            raise AssertionError("work was admitted after serving teardown")

        try:
            store.submit(lambda: _late())
        except RedisLoopOwnerClosed:
            facts["refusal"] = "RedisLoopOwnerClosed"
        except Exception:  # noqa: BLE001 - R15: any OTHER refusal is recorded content-free
            facts["refusal"] = "other-exception"
        else:
            facts["refusal"] = "ADMITTED"
        facts["same_owner"] = runtime.owner is owner
        facts["shared_owner_untouched"] = _shared_owner_untouched()
        facts.update(_disposition(runtime, client, pool))
    finally:
        with contextlib.suppress(Exception):
            runtime.close(timeout=10.0)
    demonstrated = (
        facts.get("refusal") == "RedisLoopOwnerClosed" and facts.get("same_owner") is True
        and facts.get("shared_owner_untouched") is True and _closed_once(facts)
    )
    return _observation(CustodyScenario.LATE_SUBMISSION_AFTER_CLOSE, demonstrated, facts)


def _probe_startup_rollback(workspace: Path) -> CustodyObservation:
    """Drive the REAL bootstrap composition with a failure after the runtime exists.

    R2: the disposition is recorded IMMEDIATELY after the composition raises -- before the
    fallback cleanup in ``finally`` -- so probe cleanup can never stand in for the
    product's rollback. ``fallback_cleanup_needed`` records whether that cleanup had
    anything left to do; a demonstrated rollback leaves it False.
    """
    from optimus.acp import bootstrap
    from optimus.guardrails.pre_tool import PreToolGuard

    runtime, client, pool = _fresh_runtime()
    mcp = _OfflineMcpRuntime()
    facts: dict[str, Any] = {}
    real_for_workspace = vars(PreToolGuard)["for_workspace"]

    def _boom(**kwargs: Any) -> Any:
        raise RuntimeError("plan1126-s1-rollback-probe")

    PreToolGuard.for_workspace = classmethod(lambda cls, **kwargs: _boom(**kwargs))  # type: ignore[method-assign]
    try:
        with _composition_patches(runtime, mcp):
            try:
                bootstrap.build_agent_harness_runtime(
                    environ=dict(_PROBE_ENVIRON), workspace_root=workspace, model="glm-5.2"
                )
            except RuntimeError as exc:
                facts["original_error_preserved"] = str(exc) == "plan1126-s1-rollback-probe"
            else:
                facts["original_error_preserved"] = False
        # Observed BEFORE any fallback cleanup: this is the product's rollback, or its absence.
        facts.update(_disposition(runtime, client, pool))
        facts["fallback_cleanup_needed"] = runtime.state.value != "CLOSED"
    finally:
        PreToolGuard.for_workspace = real_for_workspace  # type: ignore[method-assign]
        with contextlib.suppress(Exception):
            runtime.close(timeout=10.0)
    demonstrated = (
        facts.get("original_error_preserved") is True and _closed_once(facts)
        and facts.get("fallback_cleanup_needed") is False
    )
    return _observation(CustodyScenario.STARTUP_ROLLBACK, demonstrated, facts)


def _source_retention(inventory: ServingCustodyInventory) -> CustodyObservation:
    facts = {
        "retained_handle": inventory.retained_handle,
        "redis_stage_last": inventory.redis_stage_last,
        "shared_loop_reaches": inventory.shared_loop_reaches,
        "submission_injections": inventory.submission_injections,
        "serving_shutdown_order": list(inventory.serving_shutdown_order),
    }
    demonstrated = (
        inventory.retained_handle and inventory.redis_stage_last
        and inventory.shared_loop_reaches == 0 and inventory.submission_injections >= 2
    )
    return _observation(CustodyScenario.SOURCE_RETENTION, demonstrated, facts)


_EXECUTING_MODULES = (
    ("src/optimus/acp/bootstrap.py", "optimus.acp.bootstrap"),
    ("src/optimus/acp/harness_runtime.py", "optimus.acp.harness_runtime"),
    ("src/optimus/acp/server.py", "optimus.acp.server"),
    ("src/optimus/agent/state_store.py", "optimus.agent.state_store"),
    ("src/optimus/redis/async_bridge.py", "optimus.redis.async_bridge"),
    ("src/optimus/redis/runtime.py", "optimus.redis.runtime"),
    ("src/optimus/telemetry/redis_sink.py", "optimus.telemetry.redis_sink"),
)

_PROBES = (
    _probe_configured_handoff,
    _probe_normal_eof,
    _probe_cancellation,
    _probe_prior_stage_failure,
    _probe_late_submission,
    _probe_startup_rollback,
)


def serving_custody_observations(
    *, inventory: ServingCustodyInventory, source: SourceTree, execution: VerifiedExecution
) -> tuple[CustodyObservation, ...]:
    """Execute the six lifecycle scenarios under the closure recorder; pair with the static row."""
    import importlib

    if not isinstance(execution, VerifiedExecution):
        raise ExecutingSourceMismatch(
            "serving_custody_observations requires a verified execution context obtained from "
            "establish_verified_execution(); a supplied environment binding is a claim, not provenance"
        )
    execution.authorizes(S1_MEASUREMENT_ENTRY)
    binding = execution.binding
    if inventory.source_fingerprint != binding.source_fingerprint:
        raise ExecutingSourceMismatch(
            "the serving custody inventory was discovered from a different tree than this "
            "measurement is bound to"
        )
    if source_fingerprint(source, source.paths()) != binding.source_fingerprint:
        raise ExecutingSourceMismatch("the supplied source does not match the environment binding")
    for path, module_name in _EXECUTING_MODULES:
        if path in source.paths():
            verify_executing_module(source, path, importlib.import_module(module_name))
    rows = [_source_retention(inventory)]
    repository_root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="plan1126-s1-workspace-") as workspace_text:
        workspace = Path(workspace_text).resolve()
        # R3: everything the scenarios execute is recorded and checked against the binding
        # BEFORE any row is returned. An executed product file or distribution outside the
        # binding is a refused measurement, not a demonstrated scenario.
        with ExecutionClosureRecorder(repository_root) as recorder:
            for probe in _PROBES:
                rows.append(probe(workspace))
    verify_execution_closure(recorder, binding)
    return tuple(rows)
