"""Derive and enforce diagnostic coverage of ACP serving ownership boundaries."""

from __future__ import annotations

import ast
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from importlib.util import resolve_name
from pathlib import Path
from typing import Literal

# Scope is stated at the owner level. The contractual callables are derived below.
_OWNERS = {
    "optimus.acp.dispatcher": ("JsonRpcDispatcher",),
    "optimus.acp.server": ("AcpStreamServer", "NdjsonOutboundChannel"),
    "optimus.acp.spec": ("AcpDuplexAdapter",),
    "optimus.acp.outbound_writer": ("DedicatedOutboundWriter",),
    "optimus.acp.process_lifecycle": ("ProcessLifecycle",),
    "optimus.acp.session_retention": ("SessionRetentionOwner",),
    "optimus.mcp.client_disposition": ("ClientMcpRuntime",),
    "optimus.mcp.client_sdk": ("ClientMcpSdkAdapter",),
}
_DEFINED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_CALLABLE = (ast.FunctionDef, ast.AsyncFunctionDef)
_OBSERVER = "optimus.acp.debug_trace.observe_operation"
_REQUEST_SCOPE = "optimus.acp.debug_trace.observe_request"
_DESCRIPTOR = frozenset({"builtins.classmethod", "builtins.staticmethod"})
_INNER = frozenset({"functools.cache", "functools.lru_cache"})
_EXPLICIT = frozenset({
    "optimus.acp.dispatcher:JsonRpcDispatcher.dispatch",
    "optimus.acp.server:AcpStreamServer._serve_ndjson.owned_request",
})
_EXCLUSIONS = {
    "JsonRpcDispatcher.audit_events": "Reads the existing audit buffer; observation would add activity to a passive inspection path.",
    "AcpStreamServer.handle_one": "Framed transport delegates request observation to JsonRpcDispatcher.dispatch.",
    "AcpStreamServer.serve": "Long-lived framed transport; request lifecycles are observed by the dispatcher.",
    "AcpStreamServer.serve_ndjson": "Long-lived transport; the scheduled owned_request task owns its request diagnostics.",
    "NdjsonOutboundChannel.allocate_permission_request": "Permission custody and interactive-send allocation are handled by their existing owners.",
    "NdjsonOutboundChannel.submit_message": "Hot sender admission path; terminal delivery is observed by the request owner.",
    "NdjsonOutboundChannel.notify": "Streaming notification path; measuring the outer request covers its awaited sends.",
    "NdjsonOutboundChannel.cancel_request": "Synchronous permission cancellation and future settlement path.",
    "NdjsonOutboundChannel.deliver_client_response": "Raw client response enters permission custody here; the request waits at the observed request boundary.",
    "AcpDuplexAdapter.record_turn_commit": "In-memory turn commit bookkeeping; settlement facts are emitted by the settlement owner.",
    "AcpDuplexAdapter.note_turn_delivered": "Delivery custody bookkeeping already measured at the request terminal boundary.",
    "AcpDuplexAdapter.handle_client_request": "The direct ownership path re-enters this entry point; request scopes and route methods own the records.",
    "AcpDuplexAdapter.sweep_idle_mcp_once": "Periodic background poll; MCP close operations own the boundary record.",
    "AcpDuplexAdapter.after_response": "Post-send ownership bookkeeping already classified by the NDJSON terminal record.",
    "AcpDuplexAdapter._handle_client_request": "Routing and ownership adapter for the observed request and its route-specific methods.",
    "DedicatedOutboundWriter.set_admission_failure_callback": "Configuration-only callback registration.",
    "DedicatedOutboundWriter.observe_closed": "Hot shutdown polling path; the writer close operation owns the record.",
    "DedicatedOutboundWriter.submit": "Per-message physical writer queue hot path; terminal delivery belongs to NDJSON request observation.",
    "ProcessLifecycle.bind": "Event-loop and cleanup task registration only.",
    "ProcessLifecycle.request_stop": "Used by the process signal handler; keep file I/O outside the signal callback.",
    "ProcessLifecycle.record": "Writes the already-derived shutdown snapshot in memory.",
    "ProcessLifecycle.remaining": "Deadline arithmetic used during cleanup polling.",
    "ProcessLifecycle.observe_at_exit": "Interpreter-exit fallback; diagnostics may depend on modules being torn down.",
    "SessionRetentionOwner.is_active": "Per-request lease-admission lookup.",
    "SessionRetentionOwner.acquire": "Per-request lease acquisition hot path; the enclosing request scope observes the outcome.",
    "SessionRetentionOwner.retain_setup_state": "Transfers setup-state custody without performing a boundary operation.",
    "SessionRetentionOwner.retain_close_result": "Stores a recorded close result; the close operation owns its observation.",
    "SessionRetentionOwner.precheck_sync": "Repeated lease/custody invariant check with no boundary operation.",
    "ClientMcpSdkAdapter.stdio_warning_channel_observable": "Platform capability predicate, used by the diagnostics wiring.",
    "ClientMcpSdkAdapter.record_diagnostic": "Diagnostic sink entry point; observing it would create diagnostic recursion.",
    "ClientMcpSdkAdapter.pending_connections": "Passive snapshot of connection custody.",
    "ClientMcpSdkAdapter.has_pending_connections_for_session": "Passive predicate for retention sweeps.",
    "ClientMcpSdkAdapter.read_streamed_bytes_for_tests": "Test-only raw transport inspection seam.",
}


class CoverageError(ValueError):
    """A selected callable or its disposition could not be verified."""


@dataclass(frozen=True)
class Disposition:
    kind: Literal["INSTRUMENTED", "EXPLICIT_BODY", "EXCLUDED"]
    reason: str


def audit_instrumentation(project_root: Path) -> dict[str, Disposition]:
    """Re-scan serving sources and require a current disposition for each callable."""
    coverage = {}
    for module in _OWNERS:
        source = project_root.joinpath("src", *module.split(".")).with_suffix(".py")
        coverage.update(classify_source(module, source.read_text(encoding="utf-8")))
    missing = _EXPLICIT - coverage.keys()
    if missing:
        raise CoverageError(f"missing explicit scopes: {sorted(missing)}")
    stale = _EXCLUSIONS.keys() - {key.split(":", 1)[1] for key in coverage}
    if stale:
        raise CoverageError(f"stale operation exclusions: {sorted(stale)}")
    return coverage


def classify_source(module: str, source: str) -> dict[str, Disposition]:
    tree = ast.parse(source)
    owners = _OWNERS[module]
    builtins = {
        name: f"builtins.{name}" for name in ("property", "staticmethod", "classmethod", "setattr", "delattr")
    }
    bindings = _bindings(tree.body, module, builtins)
    coverage: dict[str, Disposition] = {}
    for owner in owners:
        classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == owner]
        if len(classes) != 1:
            raise CoverageError(f"{module}: expected one definition of {owner}")
        cls = classes[0]
        position = tree.body.index(cls)
        decoration_scope = _bindings(tree.body[:position], module, builtins)
        names = {node.name for node in cls.body if isinstance(node, _CALLABLE) and _selected(owner, node.name)}
        _reject_method_rebinding(owner, names, cls.body, tree.body[position + 1:], bindings)
        for index, node in enumerate(cls.body):
            if not isinstance(node, _CALLABLE):
                continue
            if _selected(owner, node.name):
                key = f"{module}:{owner}.{node.name}"
                class_bindings = _bindings(cls.body[:index], module, decoration_scope)
                _add(coverage, key, _classify(key, node, class_bindings, bindings, module))
            if owner == "AcpStreamServer" and node.name == "_serve_ndjson":
                inner = [x for x in _walk_scope(node.body) if isinstance(x, ast.AsyncFunctionDef) and x.name == "owned_request"]
                if len(inner) != 1:
                    raise CoverageError(f"{module}:{owner}.{node.name}: expected one owned_request")
                key = f"{module}:{owner}.{node.name}.owned_request"
                enclosing = _function_bindings(node, module, bindings)
                _reject_method_rebinding(key.rsplit(".", 1)[0], {"owned_request"}, node.body, [], enclosing)
                _add(coverage, key, _classify(key, inner[0], enclosing, enclosing, module))
    return coverage


def _selected(owner: str, name: str) -> bool:
    return not name.startswith("_") or (owner == "AcpDuplexAdapter" and name.startswith("_handle_"))


def _reject_method_rebinding(
    owner: str, names: set[str], body: list[ast.stmt], after: list[ast.stmt], bindings: Mapping[str, str],
) -> None:
    for node in _walk_scope(body):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)) and node.id in names:
            raise CoverageError(f"callable rebound in defining scope: {owner}.{node.id}")
    for node in _walk_scope(after):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, (ast.Store, ast.Del))
            and isinstance(node.value, ast.Name)
            and node.value.id == owner
            and node.attr in names
        ):
            raise CoverageError(f"callable rebound after owner declaration: {owner}.{node.attr}")
        if (
            isinstance(node, ast.Call)
            and _resolve(node.func, bindings) in {"builtins.setattr", "builtins.delattr"}
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == owner
        ):
            attr = node.args[1]
            name = attr.value if isinstance(attr, ast.Constant) and isinstance(attr.value, str) else None
            if name is None or name in names:
                raise CoverageError(f"callable rebound after owner declaration: {owner}.{name or '*'}")


def _add(coverage: dict[str, Disposition], key: str, decision: Disposition) -> None:
    if key in coverage:
        raise CoverageError(f"duplicate callable: {key}")
    coverage[key] = decision


def _classify(
    key: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    decorators: Mapping[str, str],
    bindings: Mapping[str, str],
    module: str,
) -> Disposition:
    stack = [_resolve(d.func if isinstance(d, ast.Call) else d, decorators) for d in node.decorator_list]
    if key in _EXPLICIT:
        local_bindings = _function_bindings(node, module, bindings)
        count = sum(
            isinstance(statement, ast.With)
            and any(
                isinstance(item.context_expr, ast.Call)
                and _resolve(item.context_expr.func, local_bindings) == _REQUEST_SCOPE
                for item in statement.items
            )
            for statement in _walk_scope(node.body)
        )
        if _OBSERVER in stack or count != 1:
            raise CoverageError(f"missing or duplicated explicit scope: {key}")
        return Disposition("EXPLICIT_BODY", "Uses the shared request observation scope at the ingress boundary.")
    if stack == ["builtins.property"] and isinstance(node.decorator_list[0], (ast.Name, ast.Attribute)):
        return Disposition("EXCLUDED", "Descriptor exposes existing state without an operation boundary.")
    reason = _EXCLUSIONS.get(key.split(":", 1)[1])
    if reason is not None:
        if _OBSERVER in stack:
            raise CoverageError(f"excluded callable wrapped: {key}")
        return Disposition("EXCLUDED", reason)
    if _OBSERVER not in stack:
        raise CoverageError(f"unclassified callable: {key}")
    index = 1 if stack[0] in _DESCRIPTOR else 0
    if (
        stack.count(_OBSERVER) != 1
        or stack[index] != _OBSERVER
        or (index == 1 and isinstance(node.decorator_list[0], ast.Call))
        or not isinstance(node.decorator_list[index], (ast.Name, ast.Attribute))
        or any(d not in _INNER for d in stack[index + 1:])
        or (isinstance(node, ast.AsyncFunctionDef) and len(stack) > index + 1)
        or any(isinstance(n, (ast.Yield, ast.YieldFrom)) for n in _walk_scope(node.body))
    ):
        raise CoverageError(f"invalid operation decorator stack: {key}")
    return Disposition("INSTRUMENTED", "Observes one logical call through the local DEBUG sink.")


def _resolve(node: ast.expr, bindings: Mapping[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return bindings.get(node.id)
    if isinstance(node, ast.Attribute):
        owner = _resolve(node.value, bindings)
        return f"{owner}.{node.attr}" if owner else None
    return None


def _function_bindings(
    function: ast.FunctionDef | ast.AsyncFunctionDef, module: str, outer: Mapping[str, str],
) -> dict[str, str]:
    args = function.args
    names = [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]
    shadowed = {arg.arg for arg in names if arg is not None}
    return _bindings(function.body, module, {name: value for name, value in outer.items() if name not in shadowed})


def _bindings(statements: list[ast.stmt], module: str, outer: Mapping[str, str]) -> dict[str, str]:
    resolved = dict(outer)
    for statement in statements:
        if isinstance(statement, ast.Import):
            for item in statement.names:
                root = item.name.split(".", 1)[0]
                resolved[item.asname or root] = item.name if item.asname else root
        elif isinstance(statement, ast.ImportFrom):
            imported = statement.module or ""
            if statement.level:
                imported = resolve_name("." * statement.level + imported, module.rpartition(".")[0])
            for item in statement.names:
                if item.name == "*":
                    resolved.clear()
                else:
                    resolved[item.asname or item.name] = f"{imported}.{item.name}"
        else:
            for node in _walk_scope([statement]):
                if isinstance(node, _DEFINED):
                    resolved.pop(node.name, None)
                elif isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, (ast.Store, ast.Del)):
                    if identity := _resolve(node, resolved):
                        for name, value in tuple(resolved.items()):
                            if value == identity or identity.startswith(value + ".") or value.startswith(identity + "."):
                                resolved.pop(name)
                    if isinstance(node, ast.Name):
                        resolved.pop(node.id, None)
                elif isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)) and node.name:
                    resolved.pop(node.name, None)
                elif isinstance(node, ast.MatchMapping) and node.rest:
                    resolved.pop(node.rest, None)
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    for alias in node.names:
                        if alias.name == "*":
                            resolved.clear()
                        else:
                            resolved.pop(alias.asname or alias.name.split(".", 1)[0], None)
    return resolved


def _walk_scope(statements: list[ast.stmt]) -> Iterator[ast.AST]:
    stack: list[ast.AST] = list(reversed(statements))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, (*_DEFINED, ast.Lambda)):
            stack.extend(reversed(tuple(ast.iter_child_nodes(node))))
