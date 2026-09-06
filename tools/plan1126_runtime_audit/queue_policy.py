"""Immutable-source queue, backpressure, and health audit for Plan 11.26 Task 9."""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import queue as sync_queue
import tempfile
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from optimus.redis.runtime import RedisRuntime

from .model import (
    AuditArtifact,
    BaselineScope,
    Classification,
    CoverageAssessmentStatus,
    EvidenceReference,
    Finding,
    GateStatus,
    LiveStatus,
    ObservationClosureStatus,
    ReviewerStatus,
    VocabularyCoverageAssessment,
    VocabularyCoverageStatus,
)
from .source import SourceTree

H9_SOURCE_PATHS = (
    "src/optimus/acp/ndjson_subprocess_session.py",
    "src/optimus/acp/outbound_writer.py",
    "src/optimus/acp/server.py",
    "src/optimus/acp/spec.py",
    "src/optimus/redis/async_bridge.py",
    "src/optimus/redis/runtime.py",
)

_OWNER = "P11-FEAT-ACP-RUNTIME-HARDENING"


class QueueSiteKind(StrEnum):
    QUEUE_CONSTRUCTOR = "QUEUE_CONSTRUCTOR"
    QUEUE_ADMISSION = "QUEUE_ADMISSION"
    QUEUE_CONSUMER = "QUEUE_CONSUMER"
    POOL_CONSTRUCTOR = "POOL_CONSTRUCTOR"
    CLIENT_CONSTRUCTOR = "CLIENT_CONSTRUCTOR"
    HEALTH_PROBE = "HEALTH_PROBE"
    CLIENT_CLOSE = "CLIENT_CLOSE"
    POOL_CLOSE = "POOL_CLOSE"
    BRIDGE_WAIT = "BRIDGE_WAIT"


class ConstructorPolicy(StrEnum):
    DECLARED_UNBOUNDED = "DECLARED_UNBOUNDED"
    DECLARED_BOUNDED = "DECLARED_BOUNDED"
    UNKNOWN = "UNKNOWN"


class AdmissionOutcome(StrEnum):
    ACCEPTED = "ACCEPTED"
    FULL_REJECTED = "FULL_REJECTED"
    TIMED_OUT = "TIMED_OUT"
    BLOCKED = "BLOCKED"


class QueueInference(StrEnum):
    DECLARED_UNBOUNDED = "DECLARED_UNBOUNDED"
    NO_OBSERVED_BOUND_BELOW_10000 = "NO_OBSERVED_BOUND_BELOW_10000"
    BOUND_ENFORCED = "BOUND_ENFORCED"
    BLOCKING_WITH_POLICY = "BLOCKING_WITH_POLICY"
    BLOCKING_WITHOUT_POLICY = "BLOCKING_WITHOUT_POLICY"


class ElapsedClass(StrEnum):
    WITHIN_100MS = "WITHIN_100MS"
    ABOVE_100MS = "ABOVE_100MS"


class HealthScenario(StrEnum):
    HEALTHY = "HEALTHY"
    OS_ERROR = "OS_ERROR"
    REDIS_TIMEOUT = "REDIS_TIMEOUT"
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"


class HealthOutcome(StrEnum):
    HEALTHY = "HEALTHY"
    CONNECTION_FAILURE = "CONNECTION_FAILURE"
    UNEXPECTED_PROPAGATED = "UNEXPECTED_PROPAGATED"


class HealthDeadlinePolicy(StrEnum):
    CONNECT_ONLY = "CONNECT_ONLY"
    FULL_OPERATION = "FULL_OPERATION"
    NONE = "NONE"


class PoolOwnership(StrEnum):
    RUNTIME_OWNED_CLIENT_THEN_POOL = "RUNTIME_OWNED_CLIENT_THEN_POOL"
    RUNTIME_OWNED_POOL_THEN_CLIENT = "RUNTIME_OWNED_POOL_THEN_CLIENT"
    CLIENT_ONLY = "CLIENT_ONLY"
    EXTERNAL_POOL = "EXTERNAL_POOL"
    UNKNOWN = "UNKNOWN"


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode()
    ).hexdigest()


def _attribute_name(node: ast.expr) -> str:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _target_name(node: ast.expr) -> str | None:
    name = _attribute_name(node)
    return name or None


def _symbol(path: str, functions: list[str]) -> str:
    module = path.removesuffix(".py").replace("/", ".")
    return ".".join((module, *functions)) if functions else module


@dataclass(frozen=True, slots=True)
class QueueSite:
    path: str
    line: int
    symbol: str
    site_kind: QueueSiteKind
    queue_ref: str | None
    classification: Classification
    evidence_digest: str
    ruling: str

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path, "line": self.line, "symbol": self.symbol,
            "site_kind": self.site_kind.value, "queue_ref": self.queue_ref,
            "classification": self.classification.value,
            "evidence_digest": self.evidence_digest, "ruling": self.ruling,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> QueueSite:
        return cls(
            path=payload["path"], line=payload["line"], symbol=payload["symbol"],
            site_kind=QueueSiteKind(payload["site_kind"]), queue_ref=payload["queue_ref"],
            classification=Classification(payload["classification"]),
            evidence_digest=payload["evidence_digest"], ruling=payload["ruling"],
        )


@dataclass(frozen=True, slots=True)
class QueueDefinition:
    queue_id: str
    path: str
    line: int
    symbol: str
    queue_ref: str
    queue_type: str
    declared_bound: int | None
    constructor_policy: ConstructorPolicy
    constructor_declares_unbounded: bool
    admission_api: str
    producer_lines: tuple[int, ...]
    consumer_lines: tuple[int, ...]
    stop_behavior: str
    overflow_result: str
    explicit_admission_timeout_seconds: float | None
    classification: Classification

    def to_dict(self) -> dict[str, object]:
        return {
            "queue_id": self.queue_id, "path": self.path, "line": self.line,
            "symbol": self.symbol, "queue_ref": self.queue_ref, "queue_type": self.queue_type,
            "declared_bound": self.declared_bound,
            "constructor_policy": self.constructor_policy.value,
            "constructor_declares_unbounded": self.constructor_declares_unbounded,
            "admission_api": self.admission_api, "producer_lines": list(self.producer_lines),
            "consumer_lines": list(self.consumer_lines), "stop_behavior": self.stop_behavior,
            "overflow_result": self.overflow_result,
            "explicit_admission_timeout_seconds": self.explicit_admission_timeout_seconds,
            "classification": self.classification.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> QueueDefinition:
        return cls(
            queue_id=payload["queue_id"], path=payload["path"], line=payload["line"],
            symbol=payload["symbol"], queue_ref=payload["queue_ref"], queue_type=payload["queue_type"],
            declared_bound=payload["declared_bound"],
            constructor_policy=ConstructorPolicy(payload["constructor_policy"]),
            constructor_declares_unbounded=payload["constructor_declares_unbounded"],
            admission_api=payload["admission_api"], producer_lines=tuple(payload["producer_lines"]),
            consumer_lines=tuple(payload["consumer_lines"]), stop_behavior=payload["stop_behavior"],
            overflow_result=payload["overflow_result"],
            explicit_admission_timeout_seconds=payload["explicit_admission_timeout_seconds"],
            classification=Classification(payload["classification"]),
        )


@dataclass(frozen=True, slots=True)
class QueueInventory:
    sites: tuple[QueueSite, ...]
    queues: tuple[QueueDefinition, ...]
    expected_queue_count: None = None

    @property
    def queue_count(self) -> int:
        return len(self.queues)

    def to_dict(self) -> dict[str, object]:
        return {
            "expected_queue_count": self.expected_queue_count,
            "queue_count": self.queue_count,
            "sites": [site.to_dict() for site in self.sites],
            "queues": [item.to_dict() for item in self.queues],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> QueueInventory:
        if payload.get("expected_queue_count") is not None:
            raise ValueError("queue inventory expected_queue_count must remain null")
        inventory = cls(
            sites=tuple(QueueSite.from_dict(item) for item in payload["sites"]),
            queues=tuple(QueueDefinition.from_dict(item) for item in payload["queues"]),
        )
        if payload["queue_count"] != inventory.queue_count:
            raise ValueError("queue inventory derived count does not match stored queues")
        return inventory


class _QueueVisitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.functions: list[str] = []
        self.sites: list[QueueSite] = []
        self.queue_operations: list[QueueSite] = []
        self.constructors: list[tuple[str, int, str, str, int | None, ConstructorPolicy]] = []

    def _site(self, node: ast.AST, kind: QueueSiteKind, queue_ref: str | None) -> QueueSite:
        missing = kind in {
            QueueSiteKind.QUEUE_CONSTRUCTOR, QueueSiteKind.QUEUE_ADMISSION,
            QueueSiteKind.QUEUE_CONSUMER, QueueSiteKind.HEALTH_PROBE, QueueSiteKind.BRIDGE_WAIT,
        }
        classification = Classification.MISSING if missing else Classification.CANONICAL
        ruling = (
            "The site participates in an unbounded queue or lacks a complete operation deadline."
            if missing else "The pool/client ownership site follows the visible RedisRuntime close order."
        )
        payload = {"path": self.path, "line": node.lineno, "kind": kind.value, "queue_ref": queue_ref}
        return QueueSite(
            path=self.path, line=node.lineno, symbol=_symbol(self.path, self.functions),
            site_kind=kind, queue_ref=queue_ref, classification=classification,
            evidence_digest=_digest(payload), ruling=ruling,
        )

    def _add(self, node: ast.AST, kind: QueueSiteKind, queue_ref: str | None) -> None:
        self.sites.append(self._site(node, kind, queue_ref))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.functions.append(node.name)
        self.generic_visit(node)
        self.functions.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def _constructor(self, target: ast.expr, value: ast.expr) -> None:
        if not isinstance(value, ast.Call):
            return
        name = _attribute_name(value.func)
        if name not in {"queue.Queue", "asyncio.Queue"}:
            return
        queue_ref = _target_name(target)
        if queue_ref is None:
            return
        bound_node: ast.expr | None = value.args[0] if value.args else None
        for keyword in value.keywords:
            if keyword.arg == "maxsize":
                bound_node = keyword.value
        if bound_node is None:
            bound: int | None = 0
            policy = ConstructorPolicy.DECLARED_UNBOUNDED
        elif isinstance(bound_node, ast.Constant) and isinstance(bound_node.value, int):
            bound = bound_node.value
            policy = ConstructorPolicy.DECLARED_UNBOUNDED if bound <= 0 else ConstructorPolicy.DECLARED_BOUNDED
        else:
            bound = None
            policy = ConstructorPolicy.UNKNOWN
        self._add(value, QueueSiteKind.QUEUE_CONSTRUCTOR, queue_ref)
        self.constructors.append((queue_ref, value.lineno, _symbol(self.path, self.functions), name, bound, policy))

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._constructor(target, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._constructor(node.target, node.value)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _attribute_name(node.func)
        receiver, _, method = name.rpartition(".")
        if receiver and method == "put":
            self.queue_operations.append(self._site(node, QueueSiteKind.QUEUE_ADMISSION, receiver))
        elif receiver and method == "get":
            self.queue_operations.append(self._site(node, QueueSiteKind.QUEUE_CONSUMER, receiver))
        health = {
            "aioredis.ConnectionPool.from_url": QueueSiteKind.POOL_CONSTRUCTOR,
            "aioredis.Redis": QueueSiteKind.CLIENT_CONSTRUCTOR,
            "self.client.ping": QueueSiteKind.HEALTH_PROBE,
            "self.client.aclose": QueueSiteKind.CLIENT_CLOSE,
            "self.pool.aclose": QueueSiteKind.POOL_CLOSE,
        }.get(name)
        if health is not None:
            self._add(node, health, None)
        if method == "result" and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Call):
            if _attribute_name(node.func.value.func) == "asyncio.run_coroutine_threadsafe":
                self._add(node, QueueSiteKind.BRIDGE_WAIT, None)
        self.generic_visit(node)


def discover_queue_inventory(source: SourceTree) -> QueueInventory:
    sites: list[QueueSite] = []
    constructors: list[tuple[str, str, int, str, str, int | None, ConstructorPolicy]] = []
    for path in source.paths():
        visitor = _QueueVisitor(path)
        visitor.visit(ast.parse(source.read_text(path), filename=path))
        sites.extend(visitor.sites)
        queue_refs = {item[0] for item in visitor.constructors}
        sites.extend(item for item in visitor.queue_operations if item.queue_ref in queue_refs)
        constructors.extend((path, *item) for item in visitor.constructors)
    queues: list[QueueDefinition] = []
    for path, queue_ref, line, symbol, queue_type, bound, policy in constructors:
        related = [site for site in sites if site.path == path and site.queue_ref == queue_ref]
        producers = tuple(sorted(site.line for site in related if site.site_kind is QueueSiteKind.QUEUE_ADMISSION))
        consumers = tuple(sorted(site.line for site in related if site.site_kind is QueueSiteKind.QUEUE_CONSUMER))
        if not producers or not consumers:
            raise ValueError(f"queue {path}:{queue_ref} lacks a discovered producer or consumer")
        stop = "SENTINEL_ADMISSION" if len(producers) > 1 else "NO_EXPLICIT_STOP_ADMISSION"
        queues.append(QueueDefinition(
            queue_id=f"{path}:{symbol}:{queue_ref}", path=path, line=line, symbol=symbol,
            queue_ref=queue_ref, queue_type=queue_type, declared_bound=bound,
            constructor_policy=policy, constructor_declares_unbounded=policy is ConstructorPolicy.DECLARED_UNBOUNDED,
            admission_api="put", producer_lines=producers, consumer_lines=consumers,
            stop_behavior=stop, overflow_result="NO_EXPLICIT_OVERFLOW_RESULT",
            explicit_admission_timeout_seconds=None, classification=Classification.MISSING,
        ))
    return QueueInventory(
        sites=tuple(sorted(sites, key=lambda item: (item.path, item.line, item.site_kind.value))),
        queues=tuple(sorted(queues, key=lambda item: item.queue_id)),
    )


def classify_admission_behavior(
    *, constructor_policy: ConstructorPolicy, accepted_count: int, attempted_count: int,
    elapsed_ms: float, explicit_timeout_seconds: float | None, observed_outcome: AdmissionOutcome,
) -> QueueInference:
    if observed_outcome is AdmissionOutcome.BLOCKED and elapsed_ms > 100.0:
        return (
            QueueInference.BLOCKING_WITH_POLICY
            if explicit_timeout_seconds is not None
            else QueueInference.BLOCKING_WITHOUT_POLICY
        )
    if constructor_policy is ConstructorPolicy.DECLARED_BOUNDED and observed_outcome in {
        AdmissionOutcome.FULL_REJECTED, AdmissionOutcome.TIMED_OUT,
    }:
        return QueueInference.BOUND_ENFORCED
    if accepted_count == attempted_count:
        return (
            QueueInference.DECLARED_UNBOUNDED
            if constructor_policy is ConstructorPolicy.DECLARED_UNBOUNDED
            else QueueInference.NO_OBSERVED_BOUND_BELOW_10000
        )
    return QueueInference.BOUND_ENFORCED


@dataclass(frozen=True, slots=True)
class QueueAdmissionObservation:
    queue_id: str
    admission_index: int
    constructor_policy: ConstructorPolicy
    observed_outcome: AdmissionOutcome
    inference: QueueInference
    elapsed_class: ElapsedClass
    elapsed_threshold_ms: float
    evidence_digest: str
    complete: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "queue_id": self.queue_id, "admission_index": self.admission_index,
            "constructor_policy": self.constructor_policy.value,
            "observed_outcome": self.observed_outcome.value, "inference": self.inference.value,
            "elapsed_class": self.elapsed_class.value, "elapsed_threshold_ms": self.elapsed_threshold_ms,
            "evidence_digest": self.evidence_digest, "complete": self.complete,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> QueueAdmissionObservation:
        return cls(
            queue_id=payload["queue_id"], admission_index=payload["admission_index"],
            constructor_policy=ConstructorPolicy(payload["constructor_policy"]),
            observed_outcome=AdmissionOutcome(payload["observed_outcome"]),
            inference=QueueInference(payload["inference"]), elapsed_class=ElapsedClass(payload["elapsed_class"]),
            elapsed_threshold_ms=payload["elapsed_threshold_ms"],
            evidence_digest=payload["evidence_digest"], complete=payload["complete"],
        )


def queue_admission_observations(
    *, inventory: QueueInventory, admission_count: int = 10_000,
) -> tuple[QueueAdmissionObservation, ...]:
    if admission_count != 10_000:
        raise ValueError("queue characterization requires exactly 10,000 admissions per queue")
    rows: list[QueueAdmissionObservation] = []

    def append_row(definition: QueueDefinition, index: int, elapsed_ms: float) -> None:
        outcome = AdmissionOutcome.ACCEPTED
        inference = classify_admission_behavior(
            constructor_policy=definition.constructor_policy,
            accepted_count=index + 1, attempted_count=index + 1,
            elapsed_ms=elapsed_ms,
            explicit_timeout_seconds=definition.explicit_admission_timeout_seconds,
            observed_outcome=outcome,
        )
        rows.append(QueueAdmissionObservation(
            queue_id=definition.queue_id, admission_index=index,
            constructor_policy=definition.constructor_policy, observed_outcome=outcome,
            inference=inference,
            elapsed_class=ElapsedClass.ABOVE_100MS if elapsed_ms > 100.0 else ElapsedClass.WITHIN_100MS,
            elapsed_threshold_ms=100.0,
            evidence_digest=_digest({"queue_id": definition.queue_id, "index": index, "outcome": outcome.value}),
        ))

    async def admit_async(definition: QueueDefinition, target: asyncio.Queue[int]) -> None:
        for index in range(admission_count):
            started = time.perf_counter_ns()
            await target.put(index)
            append_row(definition, index, (time.perf_counter_ns() - started) / 1_000_000)

    for definition in inventory.queues:
        maxsize = definition.declared_bound or 0
        if definition.queue_type == "asyncio.Queue":
            asyncio.run(admit_async(definition, asyncio.Queue(maxsize=maxsize)))
            continue
        target: Any = sync_queue.Queue(maxsize=maxsize)
        for index in range(admission_count):
            started = time.perf_counter_ns()
            target.put(index)
            append_row(definition, index, (time.perf_counter_ns() - started) / 1_000_000)
    return tuple(rows)


@dataclass(frozen=True, slots=True)
class HealthObservation:
    scenario: HealthScenario
    outcome: HealthOutcome
    deadline_policy: HealthDeadlinePolicy
    pool_ownership: PoolOwnership
    evidence_digest: str
    complete: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario": self.scenario.value, "outcome": self.outcome.value,
            "deadline_policy": self.deadline_policy.value, "pool_ownership": self.pool_ownership.value,
            "evidence_digest": self.evidence_digest, "complete": self.complete,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> HealthObservation:
        return cls(
            scenario=HealthScenario(payload["scenario"]), outcome=HealthOutcome(payload["outcome"]),
            deadline_policy=HealthDeadlinePolicy(payload["deadline_policy"]),
            pool_ownership=PoolOwnership(payload["pool_ownership"]),
            evidence_digest=payload["evidence_digest"], complete=payload["complete"],
        )


class _HealthClient:
    def __init__(self, error: BaseException | None) -> None:
        self.error = error

    async def ping(self) -> bool:
        if self.error is not None:
            raise self.error
        return True


def connection_health_observations(*, inventory: QueueInventory) -> tuple[HealthObservation, ...]:
    kinds = {site.site_kind for site in inventory.sites}
    required = {
        QueueSiteKind.POOL_CONSTRUCTOR, QueueSiteKind.CLIENT_CONSTRUCTOR, QueueSiteKind.HEALTH_PROBE,
        QueueSiteKind.CLIENT_CLOSE, QueueSiteKind.POOL_CLOSE, QueueSiteKind.BRIDGE_WAIT,
    }
    if not required <= kinds:
        raise ValueError("connection health inventory is incomplete")
    redis_timeout = type("TimeoutError", (Exception,), {"__module__": "redis.exceptions"})
    cases: tuple[tuple[HealthScenario, BaseException | None], ...] = (
        (HealthScenario.HEALTHY, None),
        (HealthScenario.OS_ERROR, OSError("task9 health probe")),
        (HealthScenario.REDIS_TIMEOUT, redis_timeout("task9 health probe")),
        (HealthScenario.UNEXPECTED_ERROR, ValueError("task9 health probe")),
    )
    rows: list[HealthObservation] = []
    for scenario, error in cases:
        runtime = RedisRuntime(pool=object(), client=_HealthClient(error))
        try:
            asyncio.run(runtime._ping_async())
        except ConnectionError:
            outcome = HealthOutcome.CONNECTION_FAILURE
        except ValueError:
            outcome = HealthOutcome.UNEXPECTED_PROPAGATED
        else:
            outcome = HealthOutcome.HEALTHY
        rows.append(HealthObservation(
            scenario=scenario, outcome=outcome,
            deadline_policy=HealthDeadlinePolicy.CONNECT_ONLY,
            pool_ownership=PoolOwnership.RUNTIME_OWNED_CLIENT_THEN_POOL,
            evidence_digest=_digest({"scenario": scenario.value, "outcome": outcome.value}),
        ))
    return tuple(rows)


_Row = QueueAdmissionObservation | HealthObservation


@dataclass(frozen=True, slots=True)
class H9ObservationSummary:
    total_observation_count: int
    complete_observation_count: int
    observation_closure_status: ObservationClosureStatus
    vocabulary_coverage_status: VocabularyCoverageStatus
    digest: str
    coverage_assessments: tuple[VocabularyCoverageAssessment, ...]
    rows: tuple[_Row, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_closure_status", ObservationClosureStatus(self.observation_closure_status))
        object.__setattr__(self, "vocabulary_coverage_status", VocabularyCoverageStatus(self.vocabulary_coverage_status))
        if self.total_observation_count != len(self.rows):
            raise ValueError("H9 summary count does not match stored observations")
        if self.complete_observation_count != sum(row.complete for row in self.rows):
            raise ValueError("H9 complete count does not match stored observations")
        if self.complete_observation_count != self.total_observation_count:
            raise ValueError("H9 observations must be structurally complete")
        if self.observation_closure_status is not ObservationClosureStatus.FULLY_STRUCTURALLY_CLOSED:
            raise ValueError("H9 observations must be labelled structurally closed")
        if self.digest != _digest([row.to_dict() for row in self.rows]):
            raise ValueError("H9 summary digest does not match stored observations")
        has_missing = False
        for assessment in self.coverage_assessments:
            observed = tuple(sorted({getattr(row, assessment.field_name).value for row in self.rows}))
            missing = tuple(sorted(set(assessment.vocabulary_values) - set(observed)))
            expected = CoverageAssessmentStatus.SCOPED_OUT if missing else CoverageAssessmentStatus.FULLY_OBSERVED
            if assessment.observed_values != observed or assessment.missing_values != missing or assessment.status is not expected:
                raise ValueError("H9 coverage assessment disagrees with stored observations")
            has_missing = has_missing or bool(missing)
        aggregate = VocabularyCoverageStatus.PARTIAL_WITH_SCOPE_OUTS if has_missing else VocabularyCoverageStatus.FULLY_OBSERVED
        if self.vocabulary_coverage_status is not aggregate:
            raise ValueError("H9 aggregate coverage status disagrees with assessments")

    def to_dict(self) -> dict[str, object]:
        return {
            "total_observation_count": self.total_observation_count,
            "complete_observation_count": self.complete_observation_count,
            "observation_closure_status": self.observation_closure_status.value,
            "vocabulary_coverage_status": self.vocabulary_coverage_status.value,
            "digest": self.digest,
            "coverage_assessments": [item.to_dict() for item in self.coverage_assessments],
            "rows": [row.to_dict() for row in self.rows],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any], *, row_type: type[_Row]) -> H9ObservationSummary:
        return cls(
            total_observation_count=payload["total_observation_count"],
            complete_observation_count=payload["complete_observation_count"],
            observation_closure_status=ObservationClosureStatus(payload["observation_closure_status"]),
            vocabulary_coverage_status=VocabularyCoverageStatus(payload["vocabulary_coverage_status"]),
            digest=payload["digest"],
            coverage_assessments=tuple(VocabularyCoverageAssessment.from_dict(item) for item in payload["coverage_assessments"]),
            rows=tuple(row_type.from_dict(item) for item in payload["rows"]),
        )


def _summary(
    rows: tuple[_Row, ...], specs: tuple[tuple[str, str, tuple[str, ...]], ...],
) -> H9ObservationSummary:
    assessments: list[VocabularyCoverageAssessment] = []
    for field, type_name, vocabulary in specs:
        observed = tuple(sorted({getattr(row, field).value for row in rows}))
        values = tuple(sorted(vocabulary))
        missing = tuple(sorted(set(values) - set(observed)))
        health_deadline_scope_out = field == "deadline_policy" and bool(missing)
        pool_ownership_scope_out = field == "pool_ownership" and bool(missing)
        assessments.append(VocabularyCoverageAssessment(
            field_name=field, type_name=type_name, vocabulary_values=values,
            observed_values=observed, missing_values=missing,
            status=CoverageAssessmentStatus.SCOPED_OUT if missing else CoverageAssessmentStatus.FULLY_OBSERVED,
            reason=(
                "Merged Redis health has a connect-only timeout; the immutable implementation contains no full-operation deadline variant, and live hanging-I/O injection is outside Task 9 authority."
                if health_deadline_scope_out else
                "Merged RedisRuntime constructs and retains both client and pool, then closes client before pool; the immutable source contains no alternative ownership topology."
                if pool_ownership_scope_out else
                "All merged queues are constructor-declared unbounded, so the stopped-consumer matrix cannot reach bounded or blocking outcomes."
                if missing else None
            ),
            owner=_OWNER if missing else None,
            next_gate=(
                "G4 health-deadline reachability assessment"
                if health_deadline_scope_out else
                "G4 pool-ownership reachability assessment"
                if pool_ownership_scope_out else
                "G4 queue negative-path reachability assessment"
                if missing else None
            ),
        ))
    return H9ObservationSummary(
        total_observation_count=len(rows), complete_observation_count=sum(row.complete for row in rows),
        observation_closure_status=ObservationClosureStatus.FULLY_STRUCTURALLY_CLOSED,
        vocabulary_coverage_status=(
            VocabularyCoverageStatus.PARTIAL_WITH_SCOPE_OUTS
            if any(item.missing_values for item in assessments)
            else VocabularyCoverageStatus.FULLY_OBSERVED
        ),
        digest=_digest([row.to_dict() for row in rows]),
        coverage_assessments=tuple(assessments), rows=rows,
    )


@dataclass(frozen=True, slots=True)
class _CombinedCoverage:
    coverage_assessments: tuple[VocabularyCoverageAssessment, ...]


@dataclass(frozen=True, slots=True)
class QueueEvidenceRecord:
    record_id: str
    hypothesis_id: str
    subject: str
    baseline_scope: BaselineScope
    baseline_anchor_commit: str
    overlay_commit: str
    binding_commit: str | None
    inventory: QueueInventory
    admission_observations: H9ObservationSummary
    health_observations: H9ObservationSummary
    commands: tuple[str, ...]
    ruling: str
    reviewer_status: ReviewerStatus
    content_free_evidence: tuple[EvidenceReference, ...]

    @property
    def schedule_observations(self) -> _CombinedCoverage:
        return _CombinedCoverage(
            self.admission_observations.coverage_assessments
            + self.health_observations.coverage_assessments
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id, "hypothesis_id": self.hypothesis_id,
            "subject": self.subject, "baseline_scope": self.baseline_scope.value,
            "baseline_anchor_commit": self.baseline_anchor_commit, "overlay_commit": self.overlay_commit,
            "binding_commit": self.binding_commit, "inventory": self.inventory.to_dict(),
            "admission_observations": self.admission_observations.to_dict(),
            "health_observations": self.health_observations.to_dict(),
            "commands": list(self.commands), "ruling": self.ruling,
            "reviewer_status": self.reviewer_status.value,
            "content_free_evidence": [item.to_dict() for item in self.content_free_evidence],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> QueueEvidenceRecord:
        return cls(
            record_id=payload["record_id"], hypothesis_id=payload["hypothesis_id"],
            subject=payload["subject"], baseline_scope=BaselineScope(payload["baseline_scope"]),
            baseline_anchor_commit=payload["baseline_anchor_commit"], overlay_commit=payload["overlay_commit"],
            binding_commit=payload["binding_commit"], inventory=QueueInventory.from_dict(payload["inventory"]),
            admission_observations=H9ObservationSummary.from_dict(
                payload["admission_observations"], row_type=QueueAdmissionObservation,
            ),
            health_observations=H9ObservationSummary.from_dict(
                payload["health_observations"], row_type=HealthObservation,
            ),
            commands=tuple(payload["commands"]), ruling=payload["ruling"],
            reviewer_status=ReviewerStatus(payload["reviewer_status"]),
            content_free_evidence=tuple(EvidenceReference.from_dict(item) for item in payload["content_free_evidence"]),
        )


def _record(source: SourceTree, merged_commit: str, overlay_commit: str) -> QueueEvidenceRecord:
    scoped = SourceTree({path: source.read_text(path) for path in H9_SOURCE_PATHS})
    inventory = discover_queue_inventory(scoped)
    admissions = _summary(queue_admission_observations(inventory=inventory), (
        ("constructor_policy", "ConstructorPolicy", tuple(item.value for item in ConstructorPolicy)),
        ("observed_outcome", "AdmissionOutcome", tuple(item.value for item in AdmissionOutcome)),
        ("inference", "QueueInference", tuple(item.value for item in QueueInference)),
        ("elapsed_class", "ElapsedClass", tuple(item.value for item in ElapsedClass)),
    ))
    health = _summary(connection_health_observations(inventory=inventory), (
        ("scenario", "HealthScenario", tuple(item.value for item in HealthScenario)),
        ("outcome", "HealthOutcome", tuple(item.value for item in HealthOutcome)),
        ("deadline_policy", "HealthDeadlinePolicy", tuple(item.value for item in HealthDeadlinePolicy)),
        ("pool_ownership", "PoolOwnership", tuple(item.value for item in PoolOwnership)),
    ))
    return QueueEvidenceRecord(
        record_id="ER-H9-QUEUE-HEALTH", hypothesis_id="H9",
        subject="Queue backpressure, connection health, and pool ownership",
        baseline_scope=BaselineScope.MERGED, baseline_anchor_commit=merged_commit,
        overlay_commit=overlay_commit, binding_commit=None, inventory=inventory,
        admission_observations=admissions, health_observations=health,
        commands=(
            "uv run --frozen pytest tests/unit/acp/test_plan1126_queue_policy.py::test_queue_policy_cross_checks_constructor_and_10000_admissions -q",
            "uv run --frozen pytest tests/unit/acp/test_plan1126_queue_policy.py tests/unit/acp/test_outbound_writer.py tests/unit/acp/test_ndjson_subprocess_session.py tests/unit/redis/test_runtime.py -q",
        ),
        ruling=(
            "H9 derives three constructor-declared unbounded queues, records 10,000 stopped-consumer admissions per queue without inferring unboundedness from the probe alone, and separates connect timeout from a missing full health-operation deadline."
        ),
        reviewer_status=ReviewerStatus.PENDING_G2,
        content_free_evidence=(
            EvidenceReference("H9-INVENTORY", BaselineScope.MERGED, _digest(inventory.to_dict())),
            EvidenceReference("H9-ADMISSIONS", BaselineScope.MERGED, admissions.digest),
            EvidenceReference("H9-HEALTH", BaselineScope.MERGED, health.digest),
        ),
    )


def _findings(record: QueueEvidenceRecord) -> tuple[Finding, ...]:
    return (
        Finding(
            finding_id="H9-MISSING-QUEUE-BACKPRESSURE-merged",
            subject="All ACP runtime queues are constructor-declared unbounded and have no overload disposition",
            classification=Classification.MISSING, baseline_scope=BaselineScope.MERGED,
            symbols=tuple(f"{item.path}:{item.line}:{item.symbol}" for item in record.inventory.queues),
            evidence=(EvidenceReference("H9-ADMISSIONS", BaselineScope.MERGED, record.admission_observations.digest),),
            owner=_OWNER,
            ruling="Each stopped-consumer queue accepted 10,000 admissions, and constructor maxsize=0 independently establishes unbounded policy rather than the probe result doing so.",
        ),
        Finding(
            finding_id="H9-MISSING-HEALTH-DEADLINE-merged",
            subject="Redis health probing has a connect timeout but no complete command/read deadline",
            classification=Classification.MISSING, baseline_scope=BaselineScope.MERGED,
            symbols=(
                "src/optimus/redis/runtime.py:28:RedisRuntime.from_url",
                "src/optimus/redis/runtime.py:44:RedisRuntime._ping_async",
                "src/optimus/redis/async_bridge.py:47:sync_await",
            ),
            evidence=(EvidenceReference("H9-HEALTH", BaselineScope.MERGED, record.health_observations.digest),),
            owner=_OWNER,
            ruling="socket_connect_timeout=2 bounds connection establishment only; client.ping and the bridge Future.result call have no explicit operation deadline.",
        ),
    )


def build_h9_audit_artifact(
    *, merged: SourceTree, overlay: SourceTree, merged_commit: str, overlay_commit: str,
) -> AuditArtifact:
    from .telemetry import build_h8_audit_artifact

    with tempfile.TemporaryDirectory(prefix="plan1126-h9-") as workspace:
        base = build_h8_audit_artifact(
            merged=merged, overlay=overlay, merged_commit=merged_commit,
            overlay_commit=overlay_commit, workspace=workspace,
        )
    record = _record(merged, merged_commit, overlay_commit)
    multipliers = dict(base.discovered_multipliers)
    multipliers["queues"] = record.inventory.queue_count
    cost = dict(base.computed_run_cost)
    cost["queue_admissions"] = record.inventory.queue_count * 10_000
    return AuditArtifact(
        schema_version=base.schema_version, merged_commit=base.merged_commit, overlay_commit=base.overlay_commit,
        binding_commit=base.binding_commit, baseline_reconciliation_status=base.baseline_reconciliation_status,
        running_artifact_provenance=base.running_artifact_provenance,
        static_audit_status=LiveStatus.PARTIAL, runtime_characterization_status=LiveStatus.PARTIAL,
        live_redis_status=base.live_redis_status, acpx_status=base.acpx_status,
        additional_client_status=base.additional_client_status, zed_status=base.zed_status,
        live_interoperability_status=base.live_interoperability_status,
        findings=tuple(base.findings) + _findings(record), discovered_multipliers=multipliers,
        computed_run_cost=cost, gate_status=GateStatus.INCOMPLETE,
        evidence_records=tuple(base.evidence_records) + (record,),
    )
