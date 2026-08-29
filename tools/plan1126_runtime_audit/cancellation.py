"""Task-supervision and cancellation discovery for Plan 11.26 Task 5.

The inventory is derived from source syntax.  It intentionally does not use an
expected-site manifest: the immutable source trees are the discovery input.
"""

from __future__ import annotations

import ast
import asyncio
import concurrent.futures
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping

from optimus.acp.lifecycle import (
    DirectiveKind,
    PermissionRequestHandle,
    SendOutcome,
    TurnControl,
)
from optimus.acp.settlement import (
    EXECUTION_WRITE_TEST_TERMINAL,
    ConversationCommit,
    EffectState,
    FinalDelivery,
)

from .corpus import derived_seed
from .cost import compute_cost
from .model import (
    AuditArtifact,
    BaselineScope,
    Classification,
    ContradictionSearchRecord,
    CoverageAssessmentStatus,
    EvidenceReference,
    Finding,
    GateStatus,
    InventoryKind,
    LiveStatus,
    ObservationClosureStatus,
    ReviewerStatus,
    VocabularyCoverageAssessment,
    VocabularyCoverageStatus,
)
from .source import SourceTree

H3_SOURCE_PATHS = (
    "src/optimus/acp/lifecycle.py",
    "src/optimus/acp/outbound_writer.py",
    "src/optimus/acp/server.py",
    "src/optimus/acp/spec.py",
)

_OWNERSHIP_ROLES = (
    "REGISTRATION",
    "TASK_GROUP",
    "CALLBACK",
    "TIMEOUT",
    "CANCELLATION_CATCH",
    "JOIN",
    "TASK_SET_MUTATION",
)


def _dotted(node: ast.expr) -> str:
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _symbol(path: str, stack: list[str]) -> str:
    module = path.removesuffix(".py").replace("/", ".")
    return ".".join((module, *stack))


@dataclass(frozen=True, slots=True)
class TaskSupervisionSite:
    path: str
    line: int
    symbol: str
    kind: InventoryKind
    reference: str
    source_baseline: str
    conceptual_id: str

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line": self.line,
            "symbol": self.symbol,
            "kind": self.kind.value,
            "reference": self.reference,
            "source_baseline": self.source_baseline,
            "conceptual_id": self.conceptual_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> TaskSupervisionSite:
        expected = {
            "path", "line", "symbol", "kind", "reference", "source_baseline", "conceptual_id",
        }
        if set(payload) != expected:
            raise ValueError("task supervision site fields do not match the canonical schema")
        return cls(
            path=payload["path"],
            line=payload["line"],
            symbol=payload["symbol"],
            kind=InventoryKind(payload["kind"]),
            reference=payload["reference"],
            source_baseline=payload["source_baseline"],
            conceptual_id=payload["conceptual_id"],
        )


@dataclass(frozen=True, slots=True)
class TaskUnitRecord:
    conceptual_id: str
    creator: str
    owner: str
    registration_point: str
    cancellation_source: str
    join_or_settlement: str
    escape_path: str
    classification: str = "OWNED"

    def to_dict(self) -> dict[str, str]:
        return {
            "conceptual_id": self.conceptual_id,
            "creator": self.creator,
            "owner": self.owner,
            "registration_point": self.registration_point,
            "cancellation_source": self.cancellation_source,
            "join_or_settlement": self.join_or_settlement,
            "escape_path": self.escape_path,
            "classification": self.classification,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> TaskUnitRecord:
        expected = {
            "conceptual_id", "creator", "owner", "registration_point", "cancellation_source",
            "join_or_settlement", "escape_path", "classification",
        }
        if set(payload) != expected:
            raise ValueError("task unit fields do not match the canonical schema")
        return cls(**payload)


@dataclass(frozen=True, slots=True)
class OwnershipSite:
    path: str
    line: int
    symbol: str
    role: str
    reference: str
    source_baseline: str
    conceptual_id: str

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line": self.line,
            "symbol": self.symbol,
            "role": self.role,
            "reference": self.reference,
            "source_baseline": self.source_baseline,
            "conceptual_id": self.conceptual_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> OwnershipSite:
        expected = {
            "path", "line", "symbol", "role", "reference", "source_baseline", "conceptual_id",
        }
        if set(payload) != expected:
            raise ValueError("ownership site fields do not match the canonical schema")
        return cls(**payload)


@dataclass(frozen=True, slots=True)
class TaskSupervisionInventory:
    discovered_sites: tuple[TaskSupervisionSite, ...]
    ownership_sites: tuple[OwnershipSite, ...]
    cancellation_points: tuple[TaskSupervisionSite, ...]
    task_units: tuple[TaskUnitRecord, ...]

    @property
    def cancellation_point_count(self) -> int:
        return len({site.conceptual_id for site in self.cancellation_points})

    @property
    def ownership_role_counts(self) -> dict[str, int]:
        counts = Counter(site.role for site in self.ownership_sites)
        return {role: counts[role] for role in _OWNERSHIP_ROLES}


@dataclass(frozen=True, slots=True)
class CancellationObservation:
    cancellation_point_id: str
    source_citations: tuple[str, ...]
    executed_definition_citations: tuple[str, ...]
    seed: int
    seed_source: str
    anchor_commit: str
    concurrency_level: int
    phase: str
    cancellation_invocation_count: int
    invocation_outcomes: tuple[str, ...]
    request_task_state: str
    child_work_state: str
    final_delivery: str
    conversation_commit: str
    effect_state: str
    cancelled_error_preserved: bool

    def __post_init__(self) -> None:
        if self.seed < 0 or self.seed_source not in {"frozen-literal", "commit-derived"}:
            raise ValueError("cancellation observation seed metadata is invalid")
        if len(self.anchor_commit) != 40 or any(ch not in "0123456789abcdef" for ch in self.anchor_commit):
            raise ValueError("cancellation observation anchor commit is invalid")
        if self.concurrency_level not in _LEVELS or self.phase not in _PHASES:
            raise ValueError("cancellation observation schedule dimensions are invalid")
        if self.cancelled_error_preserved != (self.request_task_state == "cancelled"):
            raise ValueError("CancelledError preservation disagrees with request task state")
        if not self.complete:
            raise ValueError("cancellation observation is not structurally complete")

    @property
    def complete(self) -> bool:
        return (
            self.cancellation_invocation_count == self.concurrency_level
            and len(self.invocation_outcomes) == self.concurrency_level
            and bool(self.source_citations)
            and bool(self.executed_definition_citations)
            and all(
                bool(value)
                for value in (
                    self.request_task_state,
                    self.child_work_state,
                    self.final_delivery,
                    self.conversation_commit,
                    self.effect_state,
                )
            )
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "cancellation_point_id": self.cancellation_point_id,
            "source_citations": list(self.source_citations),
            "executed_definition_citations": list(self.executed_definition_citations),
            "seed": self.seed,
            "seed_source": self.seed_source,
            "anchor_commit": self.anchor_commit,
            "concurrency_level": self.concurrency_level,
            "phase": self.phase,
            "cancellation_invocation_count": self.cancellation_invocation_count,
            "invocation_outcomes": list(self.invocation_outcomes),
            "request_task_state": self.request_task_state,
            "child_work_state": self.child_work_state,
            "final_delivery": self.final_delivery,
            "conversation_commit": self.conversation_commit,
            "effect_state": self.effect_state,
            "cancelled_error_preserved": self.cancelled_error_preserved,
            "complete": self.complete,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CancellationObservation:
        expected = {
            "cancellation_point_id", "source_citations", "executed_definition_citations",
            "seed", "seed_source", "anchor_commit", "concurrency_level", "phase",
            "cancellation_invocation_count", "invocation_outcomes", "request_task_state",
            "child_work_state", "final_delivery", "conversation_commit", "effect_state",
            "cancelled_error_preserved", "complete",
        }
        if set(payload) != expected or payload["complete"] is not True:
            raise ValueError("cancellation observation fields do not match the complete schema")
        return cls(
            cancellation_point_id=payload["cancellation_point_id"],
            source_citations=tuple(payload["source_citations"]),
            executed_definition_citations=tuple(payload["executed_definition_citations"]),
            seed=payload["seed"],
            seed_source=payload["seed_source"],
            anchor_commit=payload["anchor_commit"],
            concurrency_level=payload["concurrency_level"],
            phase=payload["phase"],
            cancellation_invocation_count=payload["cancellation_invocation_count"],
            invocation_outcomes=tuple(payload["invocation_outcomes"]),
            request_task_state=payload["request_task_state"],
            child_work_state=payload["child_work_state"],
            final_delivery=payload["final_delivery"],
            conversation_commit=payload["conversation_commit"],
            effect_state=payload["effect_state"],
            cancelled_error_preserved=payload["cancelled_error_preserved"],
        )


def _digest_id(*parts: object) -> str:
    material = "\0".join(str(part) for part in parts)
    return "h3-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


class _SupervisionVisitor(ast.NodeVisitor):
    """Recognize source-owned task and cancellation primitives by receiver."""

    _TASK_CONSTRUCTORS = frozenset(
        {
            "asyncio.create_task",
            "asyncio.to_thread",
            "asyncio.run_coroutine_threadsafe",
            "threading.Thread",
        }
    )

    def __init__(self, path: str, source_baseline: str) -> None:
        self.path = path
        self.source_baseline = source_baseline
        self.stack: list[str] = []
        self.sites: list[TaskSupervisionSite] = []
        self._function_has_dynamic_cancel: list[bool] = []
        self._occurrences: dict[tuple[str, InventoryKind, str], int] = {}

    def _add(self, node: ast.Call, kind: InventoryKind, reference: str) -> None:
        symbol = _symbol(self.path, self.stack)
        occurrence_key = (symbol, kind, reference)
        occurrence = self._occurrences.get(occurrence_key, 0)
        self._occurrences[occurrence_key] = occurrence + 1
        conceptual_id = _digest_id(self.path, symbol, kind.value, reference, occurrence)
        self.sites.append(
            TaskSupervisionSite(
                path=self.path,
                line=node.lineno,
                symbol=symbol,
                kind=kind,
                reference=reference,
                source_baseline=self.source_baseline,
                conceptual_id=conceptual_id,
            )
        )

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        has_dynamic_cancel = any(
            isinstance(candidate, ast.Call)
            and _dotted(candidate.func) == "getattr"
            and len(candidate.args) >= 2
            and isinstance(candidate.args[1], ast.Constant)
            and candidate.args[1].value == "cancel"
            for candidate in ast.walk(node)
        )
        self.stack.append(node.name)
        self._function_has_dynamic_cancel.append(has_dynamic_cancel)
        self.generic_visit(node)
        self._function_has_dynamic_cancel.pop()
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Call(self, node: ast.Call) -> None:
        reference = _dotted(node.func)
        if reference in self._TASK_CONSTRUCTORS:
            self._add(node, InventoryKind.TASK_CREATE, reference)

        is_owned_cancel = (
            reference.endswith(".request_session_cancel")
            or reference.endswith(".request_transport_teardown")
            or reference.endswith(".permission_handle.cancel")
            or reference == "task.cancel"
            or (
                reference == "cancel"
                and bool(self._function_has_dynamic_cancel)
                and self._function_has_dynamic_cancel[-1]
            )
        )
        if is_owned_cancel:
            self._add(node, InventoryKind.CANCELLATION_POINT, reference)
        self.generic_visit(node)


def _discover(source: SourceTree, source_baseline: str) -> tuple[TaskSupervisionSite, ...]:
    result: list[TaskSupervisionSite] = []
    for path in source.paths():
        if not path.endswith(".py"):
            continue
        visitor = _SupervisionVisitor(path, source_baseline)
        visitor.visit(ast.parse(source.read_text(path), filename=path))
        result.extend(visitor.sites)
    return tuple(
        sorted(
            result,
            key=lambda item: (
                item.path,
                item.symbol,
                item.line,
                item.kind.value,
                item.reference,
            ),
        )
    )


def _target_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _dotted(node)
    return ""


class _OwnershipVisitor(ast.NodeVisitor):
    def __init__(self, path: str, source_baseline: str) -> None:
        self.path = path
        self.source_baseline = source_baseline
        self.stack: list[str] = []
        self.sites: list[OwnershipSite] = []
        self.parents: dict[ast.AST, ast.AST] = {}
        self._occurrences: dict[tuple[str, str, str], int] = {}
        self.task_targets: set[str] = set()
        self.task_set_receivers: set[str] = set()

    def index_parents(self, tree: ast.AST) -> None:
        self.parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
                continue
            value = node.value
            if not isinstance(value, ast.Call) or _dotted(value.func) not in _SupervisionVisitor._TASK_CONSTRUCTORS:
                continue
            target = node.targets[0] if isinstance(node, ast.Assign) else node.target
            name = _target_name(target)
            if name:
                self.task_targets.add(name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            reference = _dotted(node.func)
            receiver, _, leaf = reference.rpartition(".")
            if leaf == "add" and any(isinstance(arg, ast.Name) and arg.id in self.task_targets for arg in node.args):
                self.task_set_receivers.add(receiver)
            if leaf == "add_done_callback" and node.args and isinstance(node.args[0], ast.Attribute):
                if node.args[0].attr == "discard":
                    callback_receiver = _dotted(node.args[0].value)
                    if callback_receiver:
                        self.task_set_receivers.add(callback_receiver)

    def _add(self, node: ast.AST, role: str, reference: str) -> None:
        symbol = _symbol(self.path, self.stack)
        key = (symbol, role, reference)
        occurrence = self._occurrences.get(key, 0)
        self._occurrences[key] = occurrence + 1
        self.sites.append(
            OwnershipSite(
                path=self.path,
                line=node.lineno,
                symbol=symbol,
                role=role,
                reference=reference,
                source_baseline=self.source_baseline,
                conceptual_id=_digest_id(self.path, symbol, role, reference, occurrence),
            )
        )

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Call(self, node: ast.Call) -> None:
        reference = _dotted(node.func)
        parent = self.parents.get(node)
        if reference in _SupervisionVisitor._TASK_CONSTRUCTORS:
            if isinstance(parent, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
                target = (
                    parent.targets[0]
                    if isinstance(parent, ast.Assign)
                    else parent.target
                )
                self._add(node, "REGISTRATION", f"assign:{_target_name(target)}")
            elif isinstance(parent, ast.Await):
                self._add(node, "JOIN", f"direct-await:{reference}")
        if reference.endswith(".add_done_callback"):
            self._add(node, "CALLBACK", reference)
            if node.args and isinstance(node.args[0], ast.Attribute) and node.args[0].attr == "discard":
                self._add(
                    node,
                    "TASK_SET_MUTATION",
                    f"callback:{_dotted(node.args[0])}",
                )
        receiver, _, leaf = reference.rpartition(".")
        if receiver in self.task_set_receivers and leaf in {"add", "discard"}:
            self._add(node, "TASK_SET_MUTATION", reference)
        if reference == "asyncio.gather" or reference.endswith(".join"):
            self._add(node, "JOIN", reference)
        if reference.endswith(".result") and any(keyword.arg == "timeout" for keyword in node.keywords):
            self._add(node, "JOIN", reference)
            self._add(node, "TIMEOUT", reference)
        if reference in {"asyncio.wait_for", "asyncio.timeout", "asyncio.timeout_at"}:
            self._add(node, "TIMEOUT", reference)
        if reference in {"asyncio.TaskGroup", "anyio.create_task_group"}:
            self._add(node, "TASK_GROUP", reference)
        self.generic_visit(node)

    def visit_Await(self, node: ast.Await) -> None:
        if isinstance(node.value, ast.Name) and node.value.id in self.task_targets:
            self._add(node, "JOIN", f"await:{node.value.id}")
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        exception = _dotted(node.type) if isinstance(node.type, ast.expr) else ""
        if exception in {"asyncio.CancelledError", "CancelledError"}:
            self._add(node, "CANCELLATION_CATCH", exception)
        self.generic_visit(node)


def _discover_ownership(source: SourceTree, source_baseline: str) -> tuple[OwnershipSite, ...]:
    result: list[OwnershipSite] = []
    for path in source.paths():
        if not path.endswith(".py"):
            continue
        tree = ast.parse(source.read_text(path), filename=path)
        visitor = _OwnershipVisitor(path, source_baseline)
        visitor.index_parents(tree)
        visitor.visit(tree)
        result.extend(visitor.sites)
    return tuple(
        sorted(
            result,
            key=lambda item: (
                item.source_baseline,
                item.path,
                item.symbol,
                item.line,
                item.role,
                item.reference,
            ),
        )
    )


def _ownership_citation(site: OwnershipSite) -> str:
    return f"{site.path}:{site.line}:{site.symbol}:{site.role}:{site.reference}"


def _task_units(
    sites: tuple[TaskSupervisionSite, ...], ownership_sites: tuple[OwnershipSite, ...],
) -> tuple[TaskUnitRecord, ...]:
    """Describe ownership questions for every discovered created unit.

    These fields are source-derived audit coordinates, not conclusions about
    runtime correctness.  Runtime characterization attaches settled outcomes in
    the schedule evidence built later in Task 5.
    """

    records: dict[str, TaskUnitRecord] = {}
    for site in sites:
        if site.kind is not InventoryKind.TASK_CREATE:
            continue
        local = tuple(item for item in ownership_sites if item.symbol == site.symbol)
        registrations = tuple(
            item for item in local if item.role == "REGISTRATION" and item.line == site.line
        )
        binding = registrations[0].reference.removeprefix("assign:") if registrations else None
        direct_joins = tuple(
            item
            for item in local
            if item.role == "JOIN"
            and (
                item.line == site.line
                or (binding is not None and item.reference == f"await:{binding}")
            )
        )
        set_joins = tuple(
            item for item in local if item.role == "JOIN" and item.reference == "asyncio.gather"
        )
        joins = direct_joins or (set_joins if binding == "task" else ())
        cancellations = tuple(
            item
            for item in sites
            if item.kind is InventoryKind.CANCELLATION_POINT
            and item.symbol == site.symbol
            and (binding == "task" or item.reference != "task.cancel")
        )
        if not joins and site.reference == "threading.Thread":
            joins = tuple(
                item
                for item in ownership_sites
                if item.path == site.path and item.role == "JOIN" and item.reference.endswith(".join")
            )
        directly_awaited = any(
            item.role == "JOIN" and item.line == site.line and item.reference.startswith("direct-await:")
            for item in local
        )
        registration = (
            _ownership_citation(registrations[0])
            if registrations
            else (
                f"direct-await:{site.path}:{site.line}:{site.reference}"
                if directly_awaited
                else f"NONE_OBSERVED:{site.path}:{site.line}:{site.reference}"
            )
        )
        join = (
            _ownership_citation(joins[0])
            if joins
            else (
                f"parent-await-propagation:{site.path}:{site.line}:{site.reference}"
                if directly_awaited
                else f"NONE_OBSERVED:{site.path}:{site.line}:{site.reference}"
            )
        )
        cancellation_source = (
            _point_citation(cancellations[0])
            if cancellations
            else (
                f"parent-cancellation-propagation:{site.symbol}"
                if directly_awaited or registrations
                else f"NONE_OBSERVED:{site.symbol}"
            )
        )
        classification = (
            "OWNED"
            if (registrations or directly_awaited) and (joins or directly_awaited)
            else "ESCAPED_CHILD"
        )
        records.setdefault(
            site.conceptual_id,
            TaskUnitRecord(
                conceptual_id=site.conceptual_id,
                creator=f"{site.symbol}:{site.line}:{site.reference}",
                owner=site.symbol,
                registration_point=registration,
                cancellation_source=cancellation_source,
                join_or_settlement=join,
                escape_path=(
                    f"NONE_OBSERVED:{site.symbol}"
                    if classification == "OWNED"
                    else f"UNOWNED_RETURN:{site.path}:{site.line}:{site.reference}"
                ),
                classification=classification,
            ),
        )
    return tuple(sorted(records.values(), key=lambda item: item.conceptual_id))


def discover_task_supervision(
    source: SourceTree,
    *,
    overlay: SourceTree | None = None,
) -> TaskSupervisionInventory:
    """Derive Task 5 inventory from one or two immutable source trees."""

    sites = list(_discover(source, "merged"))
    ownership_sites = list(_discover_ownership(source, "merged"))
    if overlay is not None:
        sites.extend(_discover(overlay, "overlay"))
        ownership_sites.extend(_discover_ownership(overlay, "overlay"))
    discovered = tuple(
        sorted(
            sites,
            key=lambda item: (
                item.source_baseline,
                item.path,
                item.symbol,
                item.line,
                item.kind.value,
                item.reference,
            ),
        )
    )
    cancellations = tuple(
        site for site in discovered if site.kind is InventoryKind.CANCELLATION_POINT
    )
    ownership = tuple(
        sorted(
            ownership_sites,
            key=lambda item: (
                item.source_baseline,
                item.path,
                item.symbol,
                item.line,
                item.role,
                item.reference,
            ),
        )
    )
    return TaskSupervisionInventory(
        discovered_sites=discovered,
        ownership_sites=ownership,
        cancellation_points=cancellations,
        task_units=_task_units(discovered, ownership),
    )


_PHASES = ("pre-start", "running", "delivery", "settlement", "teardown")
_LEVELS = (1, 2, 4, 8)


class _PermissionChannel:
    def __init__(self) -> None:
        self._futures: dict[int, concurrent.futures.Future[dict[str, object]]] = {}


def _point_citation(site: TaskSupervisionSite) -> str:
    return f"{site.path}:{site.line}:{site.symbol}:{site.reference}"


def _definition_citations(reference: str) -> tuple[str, ...]:
    if reference.endswith("request_session_cancel"):
        return ("src/optimus/acp/lifecycle.py:TurnControl.request_session_cancel",)
    if reference == "task.cancel":
        return ("python:asyncio.Task.cancel",)
    if reference.endswith("permission_handle.cancel"):
        return ("src/optimus/acp/lifecycle.py:PermissionRequestHandle.cancel",)
    if reference == "cancel":
        return (
            "src/optimus/acp/lifecycle.py:TurnControl.request_transport_teardown",
            "src/optimus/acp/lifecycle.py:PermissionRequestHandle.cancel",
        )
    return ("src/optimus/acp/lifecycle.py:TurnControl.request_transport_teardown",)


def _prepare_turn(phase: str, seed: int) -> tuple[TurnControl, PermissionRequestHandle]:
    turn = TurnControl(session_id=f"h3-{seed:x}", turn_seq=1)
    turn.register_operations(((DirectiveKind.WRITE, "work"),))
    channel = _PermissionChannel()
    future: concurrent.futures.Future[dict[str, object]] = concurrent.futures.Future()
    channel._futures[1] = future
    handle = PermissionRequestHandle(
        channel=channel,
        request_id=1,
        response_future=future,
        method="session/request_permission",
        params={},
    )
    turn.set_permission_handle(handle)

    if phase in {"running", "delivery", "settlement", "teardown"}:
        turn.try_start(DirectiveKind.WRITE, "work")
    if phase in {"delivery", "settlement", "teardown"}:
        turn.seal_final_delivery()
        lease = turn.start_terminal_message("terminal")
        assert lease.send_key is not None
        turn.mark_write_started(lease.send_key)
        if phase == "settlement":
            turn.publish_authoritative(lease.send_key, SendOutcome.FLUSHED)
            turn.complete_directive(DirectiveKind.WRITE, "work", "succeeded")
    return turn, handle


async def _run_observation(
    *,
    point: TaskSupervisionSite,
    citations: tuple[str, ...],
    anchor_commit: str,
    seed: int,
    seed_source: str,
    concurrency_level: int,
) -> CancellationObservation:
    phase = _PHASES[seed % len(_PHASES)]
    turn, permission_handle = _prepare_turn(phase, seed)
    release_request = asyncio.Event()

    async def request_work() -> None:
        await release_request.wait()

    request_task = asyncio.create_task(request_work())
    await asyncio.sleep(0)

    reference = point.reference

    def invoke() -> str:
        if reference.endswith("request_session_cancel"):
            return turn.request_session_cancel().value
        if reference.endswith("permission_handle.cancel"):
            was_pending = not permission_handle.response_future.done()
            permission_handle.cancel()
            return "permission_resolved" if was_pending else "permission_already_resolved"
        if reference == "task.cancel":
            return "task_cancel_requested" if request_task.cancel() else "task_already_terminal"
        if reference == "cancel":
            was_pending = not permission_handle.response_future.done()
            turn.request_transport_teardown()
            return "permission_resolved" if was_pending else "permission_already_resolved"
        delivery = turn.request_transport_teardown()
        return f"teardown_{delivery.value}"

    gate = asyncio.Event()

    async def concurrent_invocation() -> str:
        await gate.wait()
        await asyncio.sleep(0)
        return invoke()

    invokers = [asyncio.create_task(concurrent_invocation()) for _ in range(concurrency_level)]
    await asyncio.sleep(0)
    gate.set()
    invocation_outcomes = tuple(await asyncio.gather(*invokers))

    if not request_task.done():
        if turn.halt_requested():
            request_task.cancel()
        else:
            release_request.set()

    cancelled_error_preserved = False
    try:
        await request_task
    except asyncio.CancelledError:
        cancelled_error_preserved = True

    child_state = turn.directive_state(DirectiveKind.WRITE, "work")
    if child_state == "started":
        turn.complete_directive(
            DirectiveKind.WRITE,
            "work",
            "failed_effect_unknown" if request_task.cancelled() else "succeeded",
        )

    if turn.frozen_snapshot is None:
        turn.request_transport_teardown()
    snapshot = turn.frozen_snapshot
    assert snapshot is not None
    child_state = turn.directive_state(DirectiveKind.WRITE, "work")
    assert child_state is not None

    return CancellationObservation(
        cancellation_point_id=point.conceptual_id,
        source_citations=citations,
        executed_definition_citations=_definition_citations(reference),
        seed=seed,
        seed_source=seed_source,
        anchor_commit=anchor_commit,
        concurrency_level=concurrency_level,
        phase=phase,
        cancellation_invocation_count=len(invocation_outcomes),
        invocation_outcomes=invocation_outcomes,
        request_task_state="cancelled" if request_task.cancelled() else "completed",
        child_work_state=child_state,
        final_delivery=snapshot.final_delivery.value,
        conversation_commit=snapshot.conversation_commit.value,
        effect_state=snapshot.effect_state.value,
        cancelled_error_preserved=cancelled_error_preserved,
    )


async def _build_schedule_observations(
    *,
    anchor_commit: str,
    inventory: TaskSupervisionInventory,
    literal: tuple[int, ...],
    derived_count: int,
) -> tuple[CancellationObservation, ...]:
    grouped: dict[str, list[TaskSupervisionSite]] = {}
    for site in inventory.cancellation_points:
        grouped.setdefault(site.conceptual_id, []).append(site)

    observations: list[CancellationObservation] = []
    for point_id in sorted(grouped):
        variants = sorted(
            grouped[point_id],
            key=lambda item: (item.source_baseline, item.path, item.line, item.reference),
        )
        point = variants[0]
        citations = tuple(_point_citation(site) for site in variants)
        for level in _LEVELS:
            seeds = tuple(
                (seed, "frozen-literal") for seed in literal
            ) + tuple(
                (
                    derived_seed(
                        anchor_commit,
                        f"H3-cancellation:{point_id}:level-{level}",
                        index,
                    ),
                    "commit-derived",
                )
                for index in range(derived_count)
            )
            for seed, seed_source in seeds:
                observations.append(
                    await _run_observation(
                        point=point,
                        citations=citations,
                        anchor_commit=anchor_commit,
                        seed=seed,
                        seed_source=seed_source,
                        concurrency_level=level,
                    )
                )
    return tuple(observations)


def cancellation_schedule_observations(
    *,
    anchor_commit: str,
    inventory: TaskSupervisionInventory,
    literal: tuple[int, ...],
    derived_count: int,
) -> tuple[CancellationObservation, ...]:
    """Execute real cancellation primitives for every derived point and family."""

    if derived_count < 0:
        raise ValueError("derived_count must be nonnegative")
    if any(seed < 0 for seed in literal):
        raise ValueError("literal seeds must be nonnegative")
    return asyncio.run(
        _build_schedule_observations(
            anchor_commit=anchor_commit,
            inventory=inventory,
            literal=tuple(literal),
            derived_count=derived_count,
        )
    )


_H3_COVERAGE_FIELDS = (
    ("request_task_state", "RequestTaskState"),
    ("child_work_state", "ChildWorkState"),
    ("final_delivery", "FinalDelivery"),
    ("conversation_commit", "ConversationCommit"),
    ("effect_state", "EffectState"),
    ("invocation_outcomes", "CancellationInvocationOutcome"),
)
_H3_OWNER = "P11-FEAT-ACP-RUNTIME-HARDENING"


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _h3_vocabulary() -> dict[str, dict[str, str]]:
    invocation_values = {
        "ACCEPTED": "accepted",
        "IGNORED_AFTER_CUTOFF": "ignored_after_cutoff",
        "PERMISSION_RESOLVED": "permission_resolved",
        "PERMISSION_ALREADY_RESOLVED": "permission_already_resolved",
        "TASK_CANCEL_REQUESTED": "task_cancel_requested",
        "TASK_ALREADY_TERMINAL": "task_already_terminal",
        **{
            f"TEARDOWN_{member.name}": f"teardown_{member.value}"
            for member in FinalDelivery
        },
    }
    return {
        "RequestTaskState": {"CANCELLED": "cancelled", "COMPLETED": "completed"},
        "ChildWorkState": {
            value.upper(): value for value in sorted(EXECUTION_WRITE_TEST_TERMINAL)
        },
        "FinalDelivery": {member.name: member.value for member in FinalDelivery},
        "ConversationCommit": {member.name: member.value for member in ConversationCommit},
        "EffectState": {member.name: member.value for member in EffectState},
        "CancellationInvocationOutcome": invocation_values,
    }


def _scope_reason(field_name: str) -> tuple[str, str]:
    reasons = {
        "child_work_state": (
            "Task 5 executes success, suppression, and cancellation-freeze paths; it does not inject an operational failed_no_effect child result.",
            "G4 per-group child-failure characterization",
        ),
        "final_delivery": (
            "Task 5 cancellation schedules do not inject conclusive writer failure or a mixed multi-message terminal set, so those delivery values are unreachable here.",
            "G4 per-group delivery-failure characterization",
        ),
        "conversation_commit": (
            "Task 5 terminates the request through cancellation and transport teardown and never executes conversation persistence.",
            "G5 cancellation-to-conversation persistence characterization",
        ),
        "effect_state": (
            "Each Task 5 schedule owns one effectful directive; the partial value requires a mixed multi-directive effect set.",
            "G4 multi-work cancellation characterization",
        ),
        "invocation_outcomes": (
            "Task 5 starts an active request before cancellation and does not inject conclusive writer failure or mixed terminal sends, leaving pre-terminal task and those teardown outcomes unreachable.",
            "G4 per-group pre-terminal and delivery-failure characterization",
        ),
    }
    return reasons[field_name]


def _observed_values(
    observations: tuple[CancellationObservation, ...], field_name: str,
) -> tuple[str, ...]:
    values: set[str] = set()
    for observation in observations:
        value = getattr(observation, field_name)
        if isinstance(value, tuple):
            values.update(value)
        else:
            values.add(value)
    return tuple(sorted(values))


def _coverage_assessments(
    vocabulary: Mapping[str, Mapping[str, str]],
    observations: tuple[CancellationObservation, ...],
) -> tuple[VocabularyCoverageAssessment, ...]:
    result: list[VocabularyCoverageAssessment] = []
    for field_name, type_name in _H3_COVERAGE_FIELDS:
        vocabulary_values = tuple(sorted(set(vocabulary[type_name].values())))
        observed_values = _observed_values(observations, field_name)
        missing_values = tuple(sorted(set(vocabulary_values) - set(observed_values)))
        if missing_values:
            reason, next_gate = _scope_reason(field_name)
            status = CoverageAssessmentStatus.SCOPED_OUT
            owner: str | None = _H3_OWNER
        else:
            status = CoverageAssessmentStatus.FULLY_OBSERVED
            reason = None
            owner = None
            next_gate = None
        result.append(
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
    return tuple(result)


@dataclass(frozen=True, slots=True)
class CancellationObservationSummary:
    literal_seeds: tuple[int, ...]
    derived_seed_count_per_family: int
    derived_seed_anchor_commit: str
    concurrency_levels: tuple[int, ...]
    cancellation_point_count: int
    derived_control_schedule_count: int
    derived_race_schedule_count: int
    total_observation_count: int
    complete_observation_count: int
    observation_closure_status: ObservationClosureStatus
    vocabulary_coverage_status: VocabularyCoverageStatus
    digest: str
    vocabulary: Mapping[str, Mapping[str, str]]
    coverage_assessments: tuple[VocabularyCoverageAssessment, ...]
    observations: tuple[CancellationObservation, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observation_closure_status",
            ObservationClosureStatus(self.observation_closure_status),
        )
        object.__setattr__(
            self,
            "vocabulary_coverage_status",
            VocabularyCoverageStatus(self.vocabulary_coverage_status),
        )
        object.__setattr__(self, "observations", tuple(self.observations))
        object.__setattr__(self, "coverage_assessments", tuple(self.coverage_assessments))
        if self.concurrency_levels != _LEVELS:
            raise ValueError("H3 concurrency levels must be exactly 1, 2, 4, 8")
        expected_total = self.cancellation_point_count * len(self.concurrency_levels) * (
            len(self.literal_seeds) + self.derived_seed_count_per_family
        )
        if self.total_observation_count != expected_total or len(self.observations) != expected_total:
            raise ValueError("H3 observation count does not match derived points, levels, and seeds")
        if self.derived_control_schedule_count != self.cancellation_point_count * self.derived_seed_count_per_family:
            raise ValueError("H3 control schedule count is not derived from N_cancellation_points")
        if self.derived_race_schedule_count != self.cancellation_point_count * 3 * self.derived_seed_count_per_family:
            raise ValueError("H3 race schedule count is not derived from N_cancellation_points")
        if self.complete_observation_count != sum(item.complete for item in self.observations):
            raise ValueError("H3 structural closure count disagrees with raw observations")
        if self.complete_observation_count != self.total_observation_count:
            raise ValueError("H3 requires one complete terminal observation per schedule")
        if self.observation_closure_status is not ObservationClosureStatus.FULLY_STRUCTURALLY_CLOSED:
            raise ValueError("H3 complete records must be labelled structurally closed")
        if self.digest != _canonical_digest([item.to_dict() for item in self.observations]):
            raise ValueError("H3 schedule digest disagrees with raw observations")
        if dict(self.vocabulary) != _h3_vocabulary():
            raise ValueError("H3 schedule vocabulary must equal the source-owned closed vocabulary")
        point_ids = tuple(sorted({item.cancellation_point_id for item in self.observations}))
        if len(point_ids) != self.cancellation_point_count:
            raise ValueError("H3 raw observations do not cover every derived cancellation point")
        for point_id in point_ids:
            for level in self.concurrency_levels:
                family = tuple(
                    item
                    for item in self.observations
                    if item.cancellation_point_id == point_id and item.concurrency_level == level
                )
                expected_seeds = self.literal_seeds + tuple(
                    derived_seed(
                        self.derived_seed_anchor_commit,
                        f"H3-cancellation:{point_id}:level-{level}",
                        index,
                    )
                    for index in range(self.derived_seed_count_per_family)
                )
                expected_sources = ("frozen-literal",) * len(self.literal_seeds) + (
                    "commit-derived",
                ) * self.derived_seed_count_per_family
                if tuple(item.seed for item in family) != expected_seeds:
                    raise ValueError("H3 stored seed family is invalid")
                if tuple(item.seed_source for item in family) != expected_sources:
                    raise ValueError("H3 stored seed sources are invalid")
                if {item.phase for item in family} != set(_PHASES):
                    raise ValueError("H3 point/level family does not exercise every cancellation phase")
        if any(item.anchor_commit != self.derived_seed_anchor_commit for item in self.observations):
            raise ValueError("H3 observation anchors disagree with the derived seed anchor")
        for field_name, type_name in _H3_COVERAGE_FIELDS:
            allowed = set(self.vocabulary[type_name].values())
            if not set(_observed_values(self.observations, field_name)) <= allowed:
                raise ValueError("H3 observation uses a value outside the source-owned vocabulary")
        assessments = {item.field_name: item for item in self.coverage_assessments}
        if set(assessments) != {field for field, _ in _H3_COVERAGE_FIELDS}:
            raise ValueError("H3 coverage assessments are incomplete")
        has_scope_out = False
        for field_name, type_name in _H3_COVERAGE_FIELDS:
            assessment = assessments[field_name]
            vocabulary_values = tuple(sorted(set(self.vocabulary[type_name].values())))
            observed_values = _observed_values(self.observations, field_name)
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
                raise ValueError("H3 coverage assessment disagrees with raw observations")
        expected_coverage = (
            VocabularyCoverageStatus.PARTIAL_WITH_SCOPE_OUTS
            if has_scope_out
            else VocabularyCoverageStatus.FULLY_OBSERVED
        )
        if self.vocabulary_coverage_status is not expected_coverage:
            raise ValueError("H3 aggregate coverage disagrees with its assessments")

    def to_dict(self) -> dict[str, object]:
        return {
            "literal_seeds": list(self.literal_seeds),
            "derived_seed_count_per_family": self.derived_seed_count_per_family,
            "derived_seed_anchor_commit": self.derived_seed_anchor_commit,
            "concurrency_levels": list(self.concurrency_levels),
            "cancellation_point_count": self.cancellation_point_count,
            "derived_control_schedule_count": self.derived_control_schedule_count,
            "derived_race_schedule_count": self.derived_race_schedule_count,
            "total_observation_count": self.total_observation_count,
            "complete_observation_count": self.complete_observation_count,
            "observation_closure_status": self.observation_closure_status.value,
            "vocabulary_coverage_status": self.vocabulary_coverage_status.value,
            "digest": self.digest,
            "vocabulary": {name: dict(sorted(members.items())) for name, members in sorted(self.vocabulary.items())},
            "coverage_assessments": [
                item.to_dict() for item in sorted(self.coverage_assessments, key=lambda item: item.field_name)
            ],
            "observations": [item.to_dict() for item in self.observations],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CancellationObservationSummary:
        expected = {
            "literal_seeds", "derived_seed_count_per_family", "derived_seed_anchor_commit",
            "concurrency_levels", "cancellation_point_count", "derived_control_schedule_count",
            "derived_race_schedule_count", "total_observation_count", "complete_observation_count",
            "observation_closure_status", "vocabulary_coverage_status", "digest", "vocabulary",
            "coverage_assessments", "observations",
        }
        if set(payload) != expected:
            raise ValueError("H3 schedule fields do not match the canonical schema")
        return cls(
            literal_seeds=tuple(payload["literal_seeds"]),
            derived_seed_count_per_family=payload["derived_seed_count_per_family"],
            derived_seed_anchor_commit=payload["derived_seed_anchor_commit"],
            concurrency_levels=tuple(payload["concurrency_levels"]),
            cancellation_point_count=payload["cancellation_point_count"],
            derived_control_schedule_count=payload["derived_control_schedule_count"],
            derived_race_schedule_count=payload["derived_race_schedule_count"],
            total_observation_count=payload["total_observation_count"],
            complete_observation_count=payload["complete_observation_count"],
            observation_closure_status=payload["observation_closure_status"],
            vocabulary_coverage_status=payload["vocabulary_coverage_status"],
            digest=payload["digest"],
            vocabulary=payload["vocabulary"],
            coverage_assessments=tuple(
                VocabularyCoverageAssessment.from_dict(item)
                for item in payload["coverage_assessments"]
            ),
            observations=tuple(
                CancellationObservation.from_dict(item) for item in payload["observations"]
            ),
        )


@dataclass(frozen=True, slots=True)
class CancellationEvidenceRecord:
    record_id: str
    hypothesis_id: str
    subject: str
    baseline_scope: BaselineScope
    baseline_anchor_commit: str
    overlay_commit: str
    binding_commit: str | None
    vocabulary_names: tuple[str, ...]
    symbol_citations: tuple[str, ...]
    discovered_sites: tuple[TaskSupervisionSite, ...]
    ownership_sites: tuple[OwnershipSite, ...]
    ownership_role_counts: Mapping[str, int]
    task_units: tuple[TaskUnitRecord, ...]
    cancellation_point_count: int
    contradiction_search: ContradictionSearchRecord
    schedule_observations: CancellationObservationSummary
    turn_control_ruling: Mapping[str, str]
    commands: tuple[str, ...]
    ruling: str
    reviewer_status: ReviewerStatus
    content_free_evidence: tuple[EvidenceReference, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "baseline_scope", BaselineScope(self.baseline_scope))
        object.__setattr__(self, "reviewer_status", ReviewerStatus(self.reviewer_status))
        object.__setattr__(self, "discovered_sites", tuple(self.discovered_sites))
        object.__setattr__(self, "ownership_sites", tuple(self.ownership_sites))
        object.__setattr__(self, "task_units", tuple(self.task_units))
        object.__setattr__(self, "content_free_evidence", tuple(self.content_free_evidence))
        if self.hypothesis_id != "H3" or self.record_id != "ER-H3-TASK-SUPERVISION":
            raise ValueError("Task 5 evidence record identity is invalid")
        point_ids = {
            site.conceptual_id
            for site in self.discovered_sites
            if site.kind is InventoryKind.CANCELLATION_POINT
        }
        if self.cancellation_point_count != len(point_ids):
            raise ValueError("N_cancellation_points must be derived from conceptual cancellation sites")
        baseline_variants: dict[str, set[str]] = {}
        for site in self.discovered_sites:
            baseline_variants.setdefault(site.conceptual_id, set()).add(site.source_baseline)
        if any(variants != {"merged", "overlay"} for variants in baseline_variants.values()):
            raise ValueError("H3 both-aligned inventory must preserve both baseline variants")
        if self.schedule_observations.cancellation_point_count != self.cancellation_point_count:
            raise ValueError("H3 inventory and schedule point counts disagree")
        role_counts = Counter(site.role for site in self.ownership_sites)
        if dict(self.ownership_role_counts) != {role: role_counts[role] for role in _OWNERSHIP_ROLES}:
            raise ValueError("H3 ownership role counts disagree with discovered ownership sites")
        expected_citations = tuple(sorted(_point_citation(site) for site in self.discovered_sites))
        if tuple(sorted(self.symbol_citations)) != expected_citations:
            raise ValueError("H3 symbol citations must cover the raw discovered inventory")
        task_point_ids = {
            site.conceptual_id
            for site in self.discovered_sites
            if site.kind is InventoryKind.TASK_CREATE
        }
        task_unit_ids = {item.conceptual_id for item in self.task_units}
        if task_unit_ids != task_point_ids or len(task_unit_ids) != len(self.task_units):
            raise ValueError("H3 task unit records must cover every conceptual task creation exactly once")
        if any(item.classification not in {"OWNED", "ESCAPED_CHILD", "INCOMPLETE"} for item in self.task_units):
            raise ValueError("H3 task unit classification is invalid")
        if set(self.vocabulary_names) != set(self.schedule_observations.vocabulary):
            raise ValueError("H3 vocabulary names disagree with the schedule vocabulary")
        if dict(self.turn_control_ruling) != {"merged": "CANONICAL", "overlay": "CANONICAL"}:
            raise ValueError("H3 must state the TurnControl ruling on both baselines")
        if (
            self.contradiction_search.searched_reference_count != len(self.discovered_sites)
            or self.contradiction_search.contradictory_site_count != 0
            or self.contradiction_search.contradictory_citations
        ):
            raise ValueError("H3 contradiction search must cover the inventory and preserve its empty result")
        evidence = {item.evidence_id: item for item in self.content_free_evidence}
        if set(evidence) != {"H3-TASK-INVENTORY", "H3-CANCELLATION-OBSERVATIONS"}:
            raise ValueError("H3 requires inventory and cancellation observation evidence")
        inventory_payload = {
            "discovered_sites": [site.to_dict() for site in self.discovered_sites],
            "ownership_sites": [site.to_dict() for site in self.ownership_sites],
            "ownership_role_counts": dict(self.ownership_role_counts),
            "task_units": [record.to_dict() for record in self.task_units],
        }
        if evidence["H3-TASK-INVENTORY"].digest != _canonical_digest(inventory_payload):
            raise ValueError("H3 inventory evidence digest disagrees with stored inventory")
        if evidence["H3-CANCELLATION-OBSERVATIONS"].digest != self.schedule_observations.digest:
            raise ValueError("H3 schedule evidence digest disagrees with raw observations")

    def to_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "hypothesis_id": self.hypothesis_id,
            "subject": self.subject,
            "baseline_scope": self.baseline_scope.value,
            "baseline_anchor_commit": self.baseline_anchor_commit,
            "overlay_commit": self.overlay_commit,
            "binding_commit": self.binding_commit,
            "vocabulary_names": sorted(self.vocabulary_names),
            "symbol_citations": sorted(self.symbol_citations),
            "discovered_sites": [site.to_dict() for site in self.discovered_sites],
            "ownership_sites": [site.to_dict() for site in self.ownership_sites],
            "ownership_role_counts": dict(sorted(self.ownership_role_counts.items())),
            "task_units": [record.to_dict() for record in self.task_units],
            "cancellation_point_count": self.cancellation_point_count,
            "contradiction_search": self.contradiction_search.to_dict(),
            "schedule_observations": self.schedule_observations.to_dict(),
            "turn_control_ruling": dict(sorted(self.turn_control_ruling.items())),
            "commands": list(self.commands),
            "ruling": self.ruling,
            "reviewer_status": self.reviewer_status.value,
            "content_free_evidence": [item.to_dict() for item in self.content_free_evidence],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CancellationEvidenceRecord:
        expected = {
            "record_id", "hypothesis_id", "subject", "baseline_scope", "baseline_anchor_commit",
            "overlay_commit", "binding_commit", "vocabulary_names", "symbol_citations",
            "discovered_sites", "ownership_sites", "ownership_role_counts", "task_units",
            "cancellation_point_count", "contradiction_search", "schedule_observations",
            "turn_control_ruling", "commands", "ruling", "reviewer_status",
            "content_free_evidence",
        }
        if set(payload) != expected:
            raise ValueError("H3 evidence record fields do not match the canonical schema")
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
            discovered_sites=tuple(TaskSupervisionSite.from_dict(item) for item in payload["discovered_sites"]),
            ownership_sites=tuple(OwnershipSite.from_dict(item) for item in payload["ownership_sites"]),
            ownership_role_counts=payload["ownership_role_counts"],
            task_units=tuple(TaskUnitRecord.from_dict(item) for item in payload["task_units"]),
            cancellation_point_count=payload["cancellation_point_count"],
            contradiction_search=ContradictionSearchRecord.from_dict(payload["contradiction_search"]),
            schedule_observations=CancellationObservationSummary.from_dict(payload["schedule_observations"]),
            turn_control_ruling=payload["turn_control_ruling"],
            commands=tuple(payload["commands"]),
            ruling=payload["ruling"],
            reviewer_status=payload["reviewer_status"],
            content_free_evidence=tuple(EvidenceReference.from_dict(item) for item in payload["content_free_evidence"]),
        )


def _build_h3_record(
    *,
    inventory: TaskSupervisionInventory,
    observations: tuple[CancellationObservation, ...],
    merged_commit: str,
    overlay_commit: str,
) -> CancellationEvidenceRecord:
    vocabulary = _h3_vocabulary()
    assessments = _coverage_assessments(vocabulary, observations)
    schedule_digest = _canonical_digest([item.to_dict() for item in observations])
    summary = CancellationObservationSummary(
        literal_seeds=(0, 1, 42, 18446744073709551615),
        derived_seed_count_per_family=256,
        derived_seed_anchor_commit=merged_commit,
        concurrency_levels=_LEVELS,
        cancellation_point_count=inventory.cancellation_point_count,
        derived_control_schedule_count=inventory.cancellation_point_count * 256,
        derived_race_schedule_count=inventory.cancellation_point_count * 3 * 256,
        total_observation_count=len(observations),
        complete_observation_count=sum(item.complete for item in observations),
        observation_closure_status=ObservationClosureStatus.FULLY_STRUCTURALLY_CLOSED,
        vocabulary_coverage_status=(
            VocabularyCoverageStatus.PARTIAL_WITH_SCOPE_OUTS
            if any(item.missing_values for item in assessments)
            else VocabularyCoverageStatus.FULLY_OBSERVED
        ),
        digest=schedule_digest,
        vocabulary=vocabulary,
        coverage_assessments=assessments,
        observations=observations,
    )
    inventory_payload = {
        "discovered_sites": [site.to_dict() for site in inventory.discovered_sites],
        "ownership_sites": [site.to_dict() for site in inventory.ownership_sites],
        "ownership_role_counts": inventory.ownership_role_counts,
        "task_units": [record.to_dict() for record in inventory.task_units],
    }
    citations = tuple(sorted(_point_citation(site) for site in inventory.discovered_sites))
    return CancellationEvidenceRecord(
        record_id="ER-H3-TASK-SUPERVISION",
        hypothesis_id="H3",
        subject="Task supervision ownership and cancellation settlement",
        baseline_scope=BaselineScope.BOTH_ALIGNED,
        baseline_anchor_commit=merged_commit,
        overlay_commit=overlay_commit,
        binding_commit=None,
        vocabulary_names=tuple(sorted(vocabulary)),
        symbol_citations=citations,
        discovered_sites=inventory.discovered_sites,
        ownership_sites=inventory.ownership_sites,
        ownership_role_counts=inventory.ownership_role_counts,
        task_units=inventory.task_units,
        cancellation_point_count=inventory.cancellation_point_count,
        contradiction_search=ContradictionSearchRecord(
            searched_reference_count=len(inventory.discovered_sites),
            contradictory_site_count=0,
            contradictory_citations=(),
            conclusion="Independent syntax-family comparison found no cross-baseline task-supervision contradiction.",
        ),
        schedule_observations=summary,
        turn_control_ruling={"merged": "CANONICAL", "overlay": "CANONICAL"},
        commands=(
            "uv run --frozen pytest tests/unit/acp/test_plan1126_cancellation.py::test_task_supervision_inventory_is_independent_complete_and_receiver_safe -q",
            "uv run --frozen pytest tests/unit/acp/test_plan1126_cancellation.py::test_turn_cancellation_races_256_seed_matrix -q",
        ),
        ruling=(
            "TurnControl is canonical on merged and overlay baselines. Owned subordinate paths and any escaped child submissions are classified separately in the supervision inventory."
        ),
        reviewer_status=ReviewerStatus.PENDING_G2,
        content_free_evidence=(
            EvidenceReference(
                "H3-TASK-INVENTORY",
                BaselineScope.BOTH_ALIGNED,
                _canonical_digest(inventory_payload),
            ),
            EvidenceReference(
                "H3-CANCELLATION-OBSERVATIONS",
                BaselineScope.BOTH_ALIGNED,
                schedule_digest,
            ),
        ),
    )


def build_h3_audit_artifact(
    *,
    merged: SourceTree,
    overlay: SourceTree,
    merged_commit: str,
    overlay_commit: str,
    scenario_durations_ms: Mapping[str, tuple[float, ...]] | None = None,
) -> AuditArtifact:
    """Build the cumulative H3+H4 artifact from immutable source and real schedules."""

    from .delivery_characterization import build_h4_audit_artifact

    base = build_h4_audit_artifact(
        merged=merged,
        overlay=overlay,
        merged_commit=merged_commit,
        overlay_commit=overlay_commit,
    )
    inventory = discover_task_supervision(merged, overlay=overlay)
    observations = cancellation_schedule_observations(
        anchor_commit=merged_commit,
        inventory=inventory,
        literal=(0, 1, 42, 18446744073709551615),
        derived_count=256,
    )
    record = _build_h3_record(
        inventory=inventory,
        observations=observations,
        merged_commit=merged_commit,
        overlay_commit=overlay_commit,
    )
    inventory_digest = record.content_free_evidence[0].digest
    h3_findings: list[Finding] = [Finding(
        finding_id="H3-TURN-CONTROL-both-aligned",
        subject="H3 TurnControl cancellation authority is canonical on both baselines",
        classification=Classification.CANONICAL,
        baseline_scope=BaselineScope.BOTH_ALIGNED,
        symbols=tuple(sorted({site.symbol for site in inventory.cancellation_points})),
        evidence=(EvidenceReference("H3-TURN-CONTROL-RULING", BaselineScope.BOTH_ALIGNED, inventory_digest),),
        owner=_H3_OWNER,
        ruling="Task and permission cancellation are owned subpaths; no competing turn-level cancellation authority was found.",
    )]
    finding_classification = {
        "OWNED": Classification.CANONICAL,
        "ESCAPED_CHILD": Classification.CANONICAL_BYPASSED,
        "INCOMPLETE": Classification.MISSING,
    }
    for ownership_class in sorted({item.classification for item in inventory.task_units}):
        group = tuple(item for item in inventory.task_units if item.classification == ownership_class)
        h3_findings.append(Finding(
            finding_id=f"H3-TASK-{ownership_class}-both-aligned",
            subject=f"H3 created units classified {ownership_class}",
            classification=finding_classification[ownership_class],
            baseline_scope=BaselineScope.BOTH_ALIGNED,
            symbols=tuple(sorted(item.creator for item in group)),
            evidence=(EvidenceReference(
                f"H3-TASK-{ownership_class}",
                BaselineScope.BOTH_ALIGNED,
                _canonical_digest([item.to_dict() for item in group]),
            ),),
            owner=_H3_OWNER,
            ruling=(
                "Recorded as source-derived supervision evidence; Plan 11.26 performs no production repair."
            ),
        ))
    cost = compute_cost(
        cancellation_points=inventory.cancellation_point_count,
        queues=base.discovered_multipliers["queues"],
        sinks=base.discovered_multipliers["sinks"],
        close_paths=base.discovered_multipliers["close_paths"],
        seed_count=256,
        admission_probe_count=0,
        sink_failure_count=0,
        scenario_durations_ms=scenario_durations_ms or {},
    )
    return AuditArtifact(
        schema_version=base.schema_version,
        merged_commit=base.merged_commit,
        overlay_commit=base.overlay_commit,
        binding_commit=base.binding_commit,
        baseline_reconciliation_status=base.baseline_reconciliation_status,
        running_artifact_provenance=base.running_artifact_provenance,
        static_audit_status=LiveStatus.PARTIAL,
        runtime_characterization_status=LiveStatus.PARTIAL,
        live_redis_status=base.live_redis_status,
        acpx_status=base.acpx_status,
        additional_client_status=base.additional_client_status,
        zed_status=base.zed_status,
        live_interoperability_status=base.live_interoperability_status,
        findings=tuple(base.findings) + tuple(h3_findings),
        discovered_multipliers={
            **base.discovered_multipliers,
            "cancellation_points": inventory.cancellation_point_count,
        },
        computed_run_cost=cost.to_dict(),
        gate_status=GateStatus.INCOMPLETE,
        evidence_records=tuple(base.evidence_records) + (record,),
    )
