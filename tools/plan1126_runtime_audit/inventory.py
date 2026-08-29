"""Shared AST and token inventory framework for offline audit discovery."""

from __future__ import annotations

import ast
import hashlib
import io
import tokenize
from dataclasses import dataclass, replace
from typing import Callable, Mapping

from .model import BaselineScope, Classification, DiscoveredSite, InventoryKind
from .source import SourceTree


@dataclass(frozen=True, slots=True)
class _CallContext:
    leaf: str
    dotted: str
    node: ast.Call


@dataclass(frozen=True, slots=True)
class InventoryRule:
    kind: InventoryKind
    matches: Callable[[_CallContext], bool]


def _call_name(node: ast.expr) -> tuple[str, str]:
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    parts.reverse()
    dotted = ".".join(parts)
    return (parts[-1] if parts else "", dotted)


def _leaf_in(*names: str) -> Callable[[_CallContext], bool]:
    accepted = frozenset(names)
    return lambda context: context.leaf in accepted


def _contains(*fragments: str) -> Callable[[_CallContext], bool]:
    lowered = tuple(fragment.lower() for fragment in fragments)
    return lambda context: any(fragment in context.dotted.lower() for fragment in lowered)


_CALL_RULES = (
    InventoryRule(InventoryKind.TASK_CREATE, _leaf_in("create_task", "start_soon", "submit", "ensure_future")),
    InventoryRule(InventoryKind.CANCELLATION_POINT, _leaf_in("cancel", "cancel_scope", "request_session_cancel", "request_transport_teardown")),
    InventoryRule(InventoryKind.QUEUE, _leaf_in("Queue", "PriorityQueue", "LifoQueue")),
    InventoryRule(InventoryKind.RESOURCE_CONSTRUCT, _leaf_in("RedisRuntime", "OutboundWriter", "AcpDuplexAdapter")),
    InventoryRule(InventoryKind.RESOURCE_CLOSE, _leaf_in("close", "aclose", "release", "close_all")),
    InventoryRule(InventoryKind.SEMANTIC_WIRE_SELECTION, _contains("error_response", "wire_error", "select_error")),
    InventoryRule(InventoryKind.REDIS_CLIENT, _leaf_in("Redis", "RedisRuntime")),
    InventoryRule(InventoryKind.REDIS_POOL, _leaf_in("ConnectionPool", "BlockingConnectionPool")),
    InventoryRule(InventoryKind.TELEMETRY, _leaf_in("emit", "record_event", "TelemetryEvent")),
    InventoryRule(InventoryKind.DEBUG, _contains("debug_trace", ".debug")),
    InventoryRule(InventoryKind.REDACTION, _contains("redact", "sanitize")),
    InventoryRule(InventoryKind.SINK, _leaf_in("export", "write_event", "append_event", "fanout")),
    InventoryRule(InventoryKind.DELIVERY_START, _contains("start_delivery", "begin_delivery")),
    InventoryRule(InventoryKind.DELIVERY_PUBLICATION, _contains("publish_response", "publication", "enqueue_response")),
    InventoryRule(InventoryKind.DELIVERY_SETTLEMENT, _contains("settle_delivery", "settlement", "commit_delivery")),
)


def _comments(source: str) -> dict[int, str]:
    result: dict[int, str] = {}
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            text = token.string.lstrip("#").strip()
            if text:
                result[token.start[0]] = text
    return result


class _Visitor(ast.NodeVisitor):
    def __init__(self, *, path: str, source: str, scope: BaselineScope) -> None:
        self.path = path
        self.source = source
        self.scope = scope
        self.comments = _comments(source)
        self.function_stack: list[tuple[str, str | None]] = []
        self.sites: list[DiscoveredSite] = []

    @property
    def symbol(self) -> str:
        suffix = ".".join(item[0] for item in self.function_stack)
        module = self.path.removesuffix(".py").replace("/", ".")
        return f"{module}.{suffix}" if suffix else module

    @property
    def invariant(self) -> str | None:
        return self.function_stack[-1][1] if self.function_stack else None

    def _invariant_for(self, line: int) -> str | None:
        for candidate in range(line - 1, max(0, line - 3), -1):
            if candidate in self.comments:
                return self.comments[candidate]
        return self.invariant

    def _add(self, node: ast.AST, kind: InventoryKind) -> None:
        invariant = self._invariant_for(node.lineno)
        material = f"{self.path}\0{self.symbol}\0{kind.value}\0{ast.dump(node, include_attributes=False)}\0{invariant or ''}"
        self.sites.append(DiscoveredSite(
            path=self.path,
            symbol=self.symbol,
            line=node.lineno,
            kind=kind,
            baseline_scope=self.scope,
            evidence_digest="sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest(),
            invariant=invariant,
        ))

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.function_stack.append((node.name, ast.get_docstring(node, clean=True)))
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Call(self, node: ast.Call) -> None:
        leaf, dotted = _call_name(node.func)
        context = _CallContext(leaf=leaf, dotted=dotted, node=node)
        for rule in _CALL_RULES:
            if rule.matches(context):
                self._add(node, rule.kind)
        if leaf == "print" and any(keyword.arg == "file" and isinstance(keyword.value, ast.Attribute) and keyword.value.attr == "stderr" for keyword in node.keywords):
            self._add(node, InventoryKind.STDERR)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if any(isinstance(target, ast.Attribute) for target in node.targets):
            self._add(node, InventoryKind.RESOURCE_TRANSFER)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if _is_broad_exception_type(node.type):
            self._add(node, InventoryKind.BROAD_CATCH)
        self.generic_visit(node)


def _is_broad_exception_type(node: ast.expr | None) -> bool:
    if node is None:
        return True
    if isinstance(node, ast.Name):
        return node.id in {"Exception", "BaseException"}
    if isinstance(node, ast.Attribute):
        return node.attr in {"Exception", "BaseException"}
    if isinstance(node, ast.Tuple):
        return any(_is_broad_exception_type(item) for item in node.elts)
    return False


def _discover(source_tree: SourceTree, scope: BaselineScope) -> list[DiscoveredSite]:
    discovered: list[DiscoveredSite] = []
    for path in source_tree.paths():
        if not path.endswith(".py"):
            continue
        source = source_tree.read_text(path)
        tree = ast.parse(source, filename=path)
        visitor = _Visitor(path=path, source=source, scope=scope)
        visitor.visit(tree)
        discovered.extend(visitor.sites)
    return discovered


def _key(site: DiscoveredSite) -> tuple[str, str, int, InventoryKind]:
    return (site.path, site.symbol, site.line, site.kind)


def discover_sites(
    source: SourceTree,
    *,
    overlay: SourceTree | None = None,
    default_scope: BaselineScope = BaselineScope.MERGED,
    classifications: Mapping[tuple[str, str, int, InventoryKind], Classification] | None = None,
) -> tuple[DiscoveredSite, ...]:
    """Derive inventory records from syntax; no expected-site list participates in discovery."""

    merged_sites = _discover(source, default_scope)
    if overlay is None:
        combined = merged_sites
    else:
        overlay_sites = _discover(overlay, BaselineScope.OVERLAY)
        merged_groups: dict[tuple[str, str, InventoryKind], list[DiscoveredSite]] = {}
        overlay_groups: dict[tuple[str, str, InventoryKind], list[DiscoveredSite]] = {}
        for site in merged_sites:
            merged_groups.setdefault((site.path, site.symbol, site.kind), []).append(site)
        for site in overlay_sites:
            overlay_groups.setdefault((site.path, site.symbol, site.kind), []).append(site)
        combined = []
        group_keys = sorted(set(merged_groups) | set(overlay_groups), key=lambda item: (item[0], item[1], item[2].value))
        for group_key in group_keys:
            merged_group = sorted(merged_groups.get(group_key, ()), key=lambda site: site.line)
            overlay_group = sorted(overlay_groups.get(group_key, ()), key=lambda site: site.line)
            for index in range(max(len(merged_group), len(overlay_group))):
                merged_site = merged_group[index] if index < len(merged_group) else None
                overlay_site = overlay_group[index] if index < len(overlay_group) else None
                if merged_site and overlay_site:
                    scope = BaselineScope.BOTH_ALIGNED if merged_site.evidence_digest == overlay_site.evidence_digest else BaselineScope.BOTH_DIVERGENT
                    combined.append(replace(merged_site, baseline_scope=scope))
                    if scope is BaselineScope.BOTH_DIVERGENT:
                        combined.append(replace(overlay_site, baseline_scope=scope))
                elif merged_site:
                    combined.append(merged_site)
                elif overlay_site:
                    combined.append(overlay_site)
    classified = [
        replace(site, classification=(classifications or {}).get(_key(site), Classification.UNCLASSIFIED))
        for site in combined
    ]
    unique = {(site.path, site.symbol, site.line, site.kind.value, site.evidence_digest): site for site in classified}
    return tuple(sorted(unique.values(), key=lambda site: (site.path, site.symbol, site.line, site.kind.value, site.evidence_digest)))
