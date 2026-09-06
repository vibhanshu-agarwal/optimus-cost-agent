"""Shared AST and token inventory framework for offline audit discovery."""

from __future__ import annotations

import ast
import hashlib
import io
import tokenize
from dataclasses import dataclass, replace
from typing import Callable, Mapping

from .model import BaselineScope, Classification, DeliveryPhase, DiscoveredSite, InventoryKind
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

_SETTLED_DELIVERY_VOCABULARY = frozenset({
    "SendState",
    "SendOutcome",
    "Settlement",
    "FinalDelivery",
    "RpcResponseDelivery",
    "ConversationCommit",
    "EffectState",
})


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
                return " ".join(self.comments[candidate].split())
        return None if self.invariant is None else " ".join(self.invariant.split())

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


def _annotation_parts(node: ast.expr | None) -> tuple[str, ...]:
    if node is None:
        return ()
    return tuple(item.id for item in ast.walk(node) if isinstance(item, ast.Name)) + tuple(
        item.attr for item in ast.walk(node) if isinstance(item, ast.Attribute)
    )


def _target_reference(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        _, dotted = _call_name(node)
        return dotted
    return None


def _annotation_role(node: ast.expr | None) -> str | None:
    parts = _annotation_parts(node)
    if "Queue" in parts:
        return "queue"
    if "Future" in parts:
        return "future"
    return parts[-1] if parts else None


def _constructor_role(node: ast.expr) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    leaf, _ = _call_name(node.func)
    if leaf == "Queue":
        return "queue"
    if leaf in {"Future", "create_future"}:
        return "future"
    return leaf or None


def _global_class_fields(sources: Mapping[str, str]) -> dict[tuple[str, str], str]:
    """Resolve field owner types without collapsing them to a shared leaf name."""

    trees = {path: ast.parse(source, filename=path) for path, source in sources.items()}
    fields: dict[tuple[str, str], str] = {}
    parameter_fields: dict[tuple[str, str], str] = {}
    constructor_parameters: dict[str, tuple[str, ...]] = {}
    for tree in trees.values():
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for statement in node.body:
                if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                    if role := _annotation_role(statement.annotation):
                        fields[(node.name, statement.target.id)] = role
                if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                parameters = tuple(
                    argument.arg
                    for argument in (*statement.args.posonlyargs, *statement.args.args)
                    if argument.arg != "self"
                )
                if statement.name == "__init__":
                    constructor_parameters[node.name] = parameters
                annotations = {
                    argument.arg: _annotation_role(argument.annotation)
                    for argument in (*statement.args.posonlyargs, *statement.args.args, *statement.args.kwonlyargs)
                }
                for assignment in ast.walk(statement):
                    if not isinstance(assignment, (ast.Assign, ast.AnnAssign)):
                        continue
                    targets = assignment.targets if isinstance(assignment, ast.Assign) else [assignment.target]
                    value = assignment.value
                    for target in targets:
                        if not (
                            isinstance(target, ast.Attribute)
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "self"
                        ):
                            continue
                        annotation = assignment.annotation if isinstance(assignment, ast.AnnAssign) else None
                        role = _annotation_role(annotation)
                        if isinstance(value, ast.Name):
                            parameter_fields[(node.name, value.id)] = target.attr
                            role = role or annotations.get(value.id)
                        role = role or (_constructor_role(value) if value is not None else None)
                        if role:
                            fields[(node.name, target.attr)] = role

    def expression_role(expression: ast.expr, roles: Mapping[str, str]) -> str | None:
        if isinstance(expression, ast.Name):
            return roles.get(expression.id)
        if isinstance(expression, ast.Call):
            return _constructor_role(expression)
        if isinstance(expression, ast.Attribute):
            owner = expression_role(expression.value, roles)
            if owner:
                return fields.get((owner, expression.attr))
        return None

    # Constructor call sites can narrow deliberately generic constructor parameters.
    # Keep the class+field key so an unrelated class using the same field/method leaf
    # can never inherit delivery semantics.
    changed = True
    while changed:
        changed = False
        for tree in trees.values():
            function_owners = {
                id(statement): node.name
                for node in tree.body
                if isinstance(node, ast.ClassDef)
                for statement in node.body
                if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            functions = [
                node for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            for function in functions:
                role_candidates = {
                    argument.arg: {role}
                    for argument in (*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs)
                    if (role := _annotation_role(argument.annotation)) is not None
                }
                if owner := function_owners.get(id(function)):
                    role_candidates["self"] = {owner}
                local_changed = True
                while local_changed:
                    local_changed = False
                    roles = {
                        name: next(iter(candidates))
                        for name, candidates in role_candidates.items()
                        if len(candidates) == 1
                    }
                    for assignment in ast.walk(function):
                        if not isinstance(assignment, (ast.Assign, ast.AnnAssign)):
                            continue
                        value = assignment.value
                        if value is None:
                            continue
                        role = expression_role(value, roles)
                        if isinstance(assignment, ast.AnnAssign):
                            role = _annotation_role(assignment.annotation) or role
                            targets = [assignment.target]
                        else:
                            targets = assignment.targets
                        for target in targets:
                            if isinstance(target, ast.Name) and role:
                                candidates = role_candidates.setdefault(target.id, set())
                                if role not in candidates:
                                    candidates.add(role)
                                    local_changed = True
                roles = {
                    name: next(iter(candidates))
                    for name, candidates in role_candidates.items()
                    if len(candidates) == 1
                }
                for call in (item for item in ast.walk(function) if isinstance(item, ast.Call)):
                    class_name, _ = _call_name(call.func)
                    parameters = constructor_parameters.get(class_name, ())
                    arguments = {
                        parameter: argument
                        for parameter, argument in zip(parameters, call.args, strict=False)
                    }
                    arguments.update(
                        (keyword.arg, keyword.value)
                        for keyword in call.keywords
                        if keyword.arg is not None
                    )
                    for parameter, argument in arguments.items():
                        field = parameter_fields.get((class_name, parameter))
                        role = expression_role(argument, roles)
                        key = (class_name, field or "")
                        if not field or not role or role in {"Any", "object", "None"}:
                            continue
                        if fields.get(key) in {None, "Any", "object", "None"}:
                            fields[key] = role
                            changed = True
    return fields


def _enum_phase(root: str, member: str | None = None) -> DeliveryPhase:
    if root in {"FinalDelivery", "RpcResponseDelivery"}:
        return DeliveryPhase.FINAL_RESPONSE
    if root == "ConversationCommit":
        return DeliveryPhase.CONVERSATION_COMMIT
    if root == "EffectState":
        return DeliveryPhase.EFFECT_SETTLEMENT
    if root == "Settlement":
        if member in {"CANCELLED", "TRANSPORT_ABANDONED"}:
            return DeliveryPhase.CANCELLATION
        return DeliveryPhase.EFFECT_SETTLEMENT
    if member == "QUEUED":
        return DeliveryPhase.QUEUE_ADMISSION
    if member in {"SUPPRESSED"}:
        return DeliveryPhase.CANCELLATION
    if member == "WRITE_STARTED":
        return DeliveryPhase.PHYSICAL_WRITE
    return DeliveryPhase.PUBLICATION


def _delivery_kind(phase: DeliveryPhase) -> InventoryKind:
    if phase is DeliveryPhase.QUEUE_ADMISSION:
        return InventoryKind.DELIVERY_START
    if phase in {DeliveryPhase.PUBLICATION, DeliveryPhase.PHYSICAL_WRITE, DeliveryPhase.FLUSH}:
        return InventoryKind.DELIVERY_PUBLICATION
    return InventoryKind.DELIVERY_SETTLEMENT


def _immediate_annotation_phase(names: set[str]) -> DeliveryPhase | None:
    """Map a method's typed public boundary to one immediate delivery phase."""

    typed_phases = (
        ({"CancelResult"}, DeliveryPhase.CANCELLATION),
        ({"StartLease", "SendTicket"}, DeliveryPhase.QUEUE_ADMISSION),
        ({"SendOutcome"}, DeliveryPhase.PUBLICATION),
        ({"SendState"}, DeliveryPhase.PHYSICAL_WRITE),
        ({"FinalDelivery", "RpcResponseDelivery"}, DeliveryPhase.FINAL_RESPONSE),
        ({"CommitDecision", "ConversationCommit", "ConversationOutcome"}, DeliveryPhase.CONVERSATION_COMMIT),
        ({"EffectState", "Settlement", "TurnSettlementSnapshot"}, DeliveryPhase.EFFECT_SETTLEMENT),
    )
    matches = [phase for types, phase in typed_phases if names & types]
    return matches[0] if matches else None


class _DeliveryVisitor(ast.NodeVisitor):
    def __init__(
        self,
        *,
        path: str,
        source: str,
        scope: BaselineScope,
        external_class_fields: Mapping[tuple[str, str], str],
        external_method_phases: Mapping[tuple[str, str], frozenset[DeliveryPhase]],
    ) -> None:
        self.path = path
        self.source = source
        self.scope = scope
        self.comments = _comments(source)
        self.function_stack: list[tuple[str, str | None]] = []
        self.function_nodes: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
        self.class_stack: list[str] = []
        self.role_scopes: list[dict[str, str]] = []
        self.sites: list[DiscoveredSite] = []
        self._conceptual_sites: dict[tuple[int, str, str], DiscoveredSite] = {}
        self.external_class_fields = external_class_fields
        self.external_method_phases = external_method_phases
        tree = ast.parse(source, filename=path)
        self.class_fields: dict[str, dict[str, str]] = {}
        self.method_phases: dict[tuple[str, str], frozenset[DeliveryPhase]] = {}
        self.protocol_methods: dict[tuple[str, str], DeliveryPhase] = {}
        self._derive_module_semantics(tree)

    def _derive_module_semantics(self, tree: ast.Module) -> None:
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            fields = self.class_fields.setdefault(node.name, {})
            is_protocol = any(_call_name(base)[0] == "Protocol" for base in node.bases)
            for statement in node.body:
                if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                    role = _annotation_role(statement.annotation)
                    if role:
                        fields[statement.target.id] = role
                if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if is_protocol:
                    argument_parts = {
                        part
                        for argument in (*statement.args.posonlyargs, *statement.args.args, *statement.args.kwonlyargs)
                        for part in _annotation_parts(argument.annotation)
                    }
                    if "bytes" in argument_parts or "Mapping" in argument_parts:
                        self.protocol_methods[(node.name, statement.name)] = DeliveryPhase.PHYSICAL_WRITE
                    elif statement.name in {"flush", "drain"}:
                        self.protocol_methods[(node.name, statement.name)] = DeliveryPhase.FLUSH
        # Constructor assignments propagate annotated parameter roles to owner fields.
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            fields = self.class_fields.setdefault(node.name, {})
            for statement in node.body:
                if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                arguments = {
                    argument.arg: _annotation_role(argument.annotation)
                    for argument in (*statement.args.posonlyargs, *statement.args.args, *statement.args.kwonlyargs)
                }
                for assignment in ast.walk(statement):
                    if not isinstance(assignment, (ast.Assign, ast.AnnAssign)):
                        continue
                    targets = assignment.targets if isinstance(assignment, ast.Assign) else [assignment.target]
                    value = assignment.value
                    role = _constructor_role(value) if value is not None else None
                    if isinstance(value, ast.Name):
                        role = arguments.get(value.id)
                    annotation = assignment.annotation if isinstance(assignment, ast.AnnAssign) else None
                    role = _annotation_role(annotation) or role
                    for target in targets:
                        if (
                            role
                            and isinstance(target, ast.Attribute)
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "self"
                        ):
                            fields[target.attr] = role
        # A method exposes one immediate phase from its typed boundary or a direct
        # queue/future/physical operation. Callee-transitive phases are deliberately
        # not propagated: a call expression is one conceptual delivery site.
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for statement in node.body:
                if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                key = (node.name, statement.name)
                annotation_names = {
                    part
                    for argument in (*statement.args.posonlyargs, *statement.args.args, *statement.args.kwonlyargs)
                    for part in _annotation_parts(argument.annotation)
                }
                annotation_names.update(_annotation_parts(statement.returns))
                phase = _immediate_annotation_phase(annotation_names)
                direct_phases: list[DeliveryPhase] = []
                for candidate in ast.walk(statement):
                    if not isinstance(candidate, ast.Call) or not isinstance(candidate.func, ast.Attribute):
                        continue
                    receiver = candidate.func.value
                    receiver_role = None
                    if (
                        isinstance(receiver, ast.Attribute)
                        and isinstance(receiver.value, ast.Name)
                        and receiver.value.id == "self"
                    ):
                        receiver_role = self.class_fields.get(node.name, {}).get(receiver.attr)
                    if candidate.func.attr in {"put", "put_nowait"} and receiver_role == "queue":
                        direct_phases.append(DeliveryPhase.QUEUE_ADMISSION)
                    if candidate.func.attr == "set_result" and receiver_role == "future":
                        direct_phases.append(DeliveryPhase.PUBLICATION)
                    role_phase = self.protocol_methods.get((receiver_role or "", candidate.func.attr))
                    if role_phase is not None:
                        direct_phases.append(role_phase)
                if phase is None and direct_phases:
                    phase = direct_phases[0]
                if phase is not None:
                    self.method_phases[key] = frozenset({phase})

    @property
    def symbol(self) -> str:
        module = self.path.removesuffix(".py").replace("/", ".")
        suffix = ".".join(item[0] for item in self.function_stack)
        return f"{module}.{suffix}" if suffix else module

    @property
    def invariant(self) -> str | None:
        return self.function_stack[-1][1] if self.function_stack else None

    def _invariant_for(self, line: int) -> str | None:
        del line
        return self.invariant

    def _add(self, node: ast.AST, reference: str) -> None:
        raise AssertionError("delivery phase must be derived from a semantic role")

    def _record(
        self,
        node: ast.AST,
        reference: str,
        phase: DeliveryPhase,
        *,
        rationale: str,
    ) -> None:
        invariant = rationale
        material = (
            f"{self.path}\0{self.symbol}\0{reference}\0{phase.value}\0"
            f"{ast.dump(node, include_attributes=False)}\0{rationale}"
        )
        site = DiscoveredSite(
            path=self.path,
            symbol=self.symbol,
            line=node.lineno,
            kind=_delivery_kind(phase),
            baseline_scope=self.scope,
            evidence_digest="sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest(),
            invariant=invariant,
            reference=reference,
            delivery_phase=phase,
        )
        conceptual_key = (node.lineno, self.symbol, reference)
        prior = self._conceptual_sites.get(conceptual_key)
        if prior is not None:
            if prior.delivery_phase is not phase or prior.evidence_digest != site.evidence_digest:
                raise ValueError("one baseline variant produced conflicting conceptual delivery sites")
            return
        self._conceptual_sites[conceptual_key] = site
        self.sites.append(site)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.function_stack.append((node.name, ast.get_docstring(node, clean=True)))
        self.function_nodes.append(node)
        roles = {
            argument.arg: role
            for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
            if (role := _annotation_role(argument.annotation)) is not None
        }
        self.role_scopes.append(roles)
        self.generic_visit(node)
        self.role_scopes.pop()
        self.function_nodes.pop()
        self.function_stack.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        reference = _target_reference(node.target)
        role = _annotation_role(node.annotation) or (_constructor_role(node.value) if node.value else None)
        if reference and role and self.role_scopes:
            self.role_scopes[-1][reference] = role
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        role = _constructor_role(node.value)
        if role is None and isinstance(node.value, (ast.Name, ast.Attribute)):
            role = self._receiver_role(node.value)
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute):
            container_role = self._receiver_role(node.value.func.value)
            if node.value.func.attr in {"get", "pop"} and container_role == "future":
                role = "future"
        if isinstance(node.value, ast.Subscript) and self._receiver_role(node.value.value) == "future":
            role = "future"
        if role and self.role_scopes:
            for target in node.targets:
                reference = _target_reference(target)
                if reference:
                    self.role_scopes[-1][reference] = role
        self.generic_visit(node)

    def _receiver_role(self, receiver: ast.expr) -> str | None:
        reference = _target_reference(receiver)
        if reference is None:
            return None
        for roles in reversed(self.role_scopes):
            if reference in roles:
                return roles[reference]
        if isinstance(receiver, ast.Name):
            for roles in reversed(self.role_scopes):
                if receiver.id in roles:
                    return roles[receiver.id]
        if isinstance(receiver, ast.Attribute):
            if isinstance(receiver.value, ast.Name) and receiver.value.id == "self" and self.class_stack:
                owner_type = self.class_stack[-1]
            else:
                owner_type = self._receiver_role(receiver.value)
            if owner_type:
                local = self.class_fields.get(owner_type, {}).get(receiver.attr)
                external = self.external_class_fields.get((owner_type, receiver.attr))
                if external and local in {None, "Any", "object", "None"}:
                    return external
                return local or external
        return None

    def _has_following_authoritative_settlement(self, node: ast.Call) -> bool:
        if not self.function_nodes:
            return False
        function = self.function_nodes[-1]

        def containing_block(
            statements: list[ast.stmt], line: int,
        ) -> tuple[list[ast.stmt], int] | None:
            for index, statement in enumerate(statements):
                if not (statement.lineno <= line <= getattr(statement, "end_lineno", statement.lineno)):
                    continue
                child_blocks: list[list[ast.stmt]] = []
                for field in ("body", "orelse", "finalbody"):
                    value = getattr(statement, field, None)
                    if isinstance(value, list) and all(isinstance(item, ast.stmt) for item in value):
                        child_blocks.append(value)
                if isinstance(statement, ast.Try):
                    child_blocks.extend(handler.body for handler in statement.handlers)
                for child in child_blocks:
                    nested = containing_block(child, line)
                    if nested is not None:
                        return nested
                return statements, index
            return None

        located = containing_block(function.body, node.lineno)
        if located is None:
            return False
        statements, write_index = located
        lease_owners: dict[str, str] = {}
        for candidate in ast.walk(function):
            if not isinstance(candidate, ast.Assign) or candidate.lineno >= node.lineno:
                continue
            if len(candidate.targets) != 1 or not isinstance(candidate.targets[0], ast.Name):
                continue
            if not isinstance(candidate.value, ast.Call) or not isinstance(candidate.value.func, ast.Attribute):
                continue
            if candidate.value.func.attr not in {"start_response_send", "start_terminal_message"}:
                continue
            owner = _target_reference(candidate.value.func.value)
            if owner:
                lease_owners[candidate.targets[0].id] = owner
        for statement in statements[write_index + 1:]:
            for candidate in ast.walk(statement):
                if not isinstance(candidate, ast.Call) or not isinstance(candidate.func, ast.Attribute):
                    continue
                if candidate.func.attr != "publish_authoritative" or len(candidate.args) < 2:
                    continue
                owner = _target_reference(candidate.func.value)
                key = candidate.args[0]
                outcome = candidate.args[1]
                if not (
                    isinstance(key, ast.Attribute)
                    and isinstance(key.value, ast.Name)
                    and key.attr == "send_key"
                    and lease_owners.get(key.value.id) == owner
                    and isinstance(outcome, ast.Attribute)
                    and isinstance(outcome.value, ast.Name)
                    and outcome.value.id == "SendOutcome"
                    and outcome.attr == "FLUSHED"
                ):
                    continue
                return True
        return False

    def visit_Call(self, node: ast.Call) -> None:
        leaf, dotted = _call_name(node.func)
        reference = dotted or leaf
        if leaf in _SETTLED_DELIVERY_VOCABULARY:
            self._record(node, reference, _enum_phase(leaf), rationale="settled-enum-construction")
        if isinstance(node.func, ast.Attribute):
            receiver_role = self._receiver_role(node.func.value)
            if leaf in {"put", "put_nowait"} and receiver_role == "queue":
                self._record(node, reference, DeliveryPhase.QUEUE_ADMISSION, rationale="typed-queue-admission")
            elif leaf == "set_result" and receiver_role == "future":
                self._record(node, reference, DeliveryPhase.PUBLICATION, rationale="typed-future-publication")
            elif leaf == "cancel":
                self._record(node, reference, DeliveryPhase.CANCELLATION, rationale="task-cancellation")
            else:
                owner_type = receiver_role
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "self" and self.class_stack:
                    owner_type = self.class_stack[-1]
                method_key = (owner_type or "", leaf)
                role_phase = self.protocol_methods.get(method_key)
                phases = self.method_phases.get(method_key, frozenset())
                if not phases:
                    phases = self.external_method_phases.get(method_key, frozenset())
                if role_phase is not None:
                    rationale = "physical-boundary"
                    if role_phase is DeliveryPhase.PHYSICAL_WRITE and self._has_following_authoritative_settlement(node):
                        rationale = "settled-physical-bypass"
                    elif role_phase is DeliveryPhase.PHYSICAL_WRITE and owner_type != "PhysicalNdjsonTransport":
                        rationale = "unsettled-physical-bypass"
                    self._record(node, reference, role_phase, rationale=rationale)
                elif phases:
                    phase = next(iter(phases))
                    self._record(node, reference, phase, rationale="settled-owner-operation")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.value, ast.Name) and node.value.id in _SETTLED_DELIVERY_VOCABULARY:
            self._record(
                node,
                f"{node.value.id}.{node.attr}",
                _enum_phase(node.value.id, node.attr),
                rationale="settled-enum-consumer",
            )
        self.generic_visit(node)


def _discover_delivery(source_tree: SourceTree, scope: BaselineScope) -> list[DiscoveredSite]:
    discovered: list[DiscoveredSite] = []
    sources = {
        path: source_tree.read_text(path)
        for path in source_tree.paths()
        if path.endswith(".py")
    }
    class_fields = _global_class_fields(sources)
    seed_visitors = [
        _DeliveryVisitor(
            path=path,
            source=source,
            scope=scope,
            external_class_fields=class_fields,
            external_method_phases={},
        )
        for path, source in sources.items()
    ]
    global_method_phases: dict[tuple[str, str], set[DeliveryPhase]] = {}
    for visitor in seed_visitors:
        for method, phases in visitor.method_phases.items():
            global_method_phases.setdefault(method, set()).update(phases)
    shared_method_phases = {
        method: frozenset(phases) for method, phases in global_method_phases.items()
    }
    for path, source in sources.items():
        visitor = _DeliveryVisitor(
            path=path,
            source=source,
            scope=scope,
            external_class_fields=class_fields,
            external_method_phases=shared_method_phases,
        )
        visitor.visit(ast.parse(source, filename=path))
        discovered.extend(visitor.sites)
    return discovered


def _delivery_classification(site: DiscoveredSite) -> Classification:
    if site.baseline_scope is BaselineScope.OVERLAY:
        return Classification.PROVISIONAL_OVERLAY
    if site.baseline_scope is BaselineScope.MERGED:
        return Classification.NOT_PRESENT
    if site.invariant == "unsettled-physical-bypass":
        return Classification.CONTRADICTORY
    if site.invariant == "settled-physical-bypass":
        return Classification.CANONICAL_BYPASSED
    return Classification.CANONICAL


def discover_delivery_sites(
    source: SourceTree,
    *,
    overlay: SourceTree,
) -> tuple[DiscoveredSite, ...]:
    """Derive and classify every delivery reference from two immutable trees."""

    merged_sites = _discover_delivery(source, BaselineScope.MERGED)
    overlay_sites = _discover_delivery(overlay, BaselineScope.OVERLAY)
    merged_groups: dict[tuple[str, str, str | None], list[DiscoveredSite]] = {}
    overlay_groups: dict[tuple[str, str, str | None], list[DiscoveredSite]] = {}
    for site in merged_sites:
        merged_groups.setdefault((site.path, site.symbol, site.reference), []).append(site)
    for site in overlay_sites:
        overlay_groups.setdefault((site.path, site.symbol, site.reference), []).append(site)
    combined: list[DiscoveredSite] = []
    group_keys = sorted(set(merged_groups) | set(overlay_groups))
    for group_key in group_keys:
        merged_group = sorted(merged_groups.get(group_key, ()), key=lambda site: site.line)
        overlay_group = sorted(overlay_groups.get(group_key, ()), key=lambda site: site.line)
        for index in range(max(len(merged_group), len(overlay_group))):
            merged_site = merged_group[index] if index < len(merged_group) else None
            overlay_site = overlay_group[index] if index < len(overlay_group) else None
            if merged_site is not None and overlay_site is not None:
                if merged_site.evidence_digest == overlay_site.evidence_digest:
                    combined.append(replace(merged_site, baseline_scope=BaselineScope.BOTH_ALIGNED))
                else:
                    combined.extend((
                        replace(merged_site, baseline_scope=BaselineScope.BOTH_DIVERGENT),
                        replace(overlay_site, baseline_scope=BaselineScope.BOTH_DIVERGENT),
                    ))
            elif merged_site is not None:
                combined.append(merged_site)
            elif overlay_site is not None:
                combined.append(overlay_site)

    classified = [
        replace(site, classification=_delivery_classification(site))
        for site in combined
    ]
    return tuple(sorted(
        classified,
        key=lambda site: (site.path, site.symbol, site.line, site.reference or ""),
    ))
