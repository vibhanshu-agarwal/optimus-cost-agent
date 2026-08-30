"""Closed vocabularies and canonical models for the Plan 11.26 audit."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from .corpus import derived_seed, literal_seeds


class BaselineScope(StrEnum):
    MERGED = "merged"
    OVERLAY = "overlay"
    BOTH_ALIGNED = "both-aligned"
    BOTH_DIVERGENT = "both-divergent"
    BINDING = "binding"


class Classification(StrEnum):
    CANONICAL = "CANONICAL"
    CANONICAL_BYPASSED = "CANONICAL_BYPASSED"
    DUPLICATED = "DUPLICATED"
    CONTRADICTORY = "CONTRADICTORY"
    MISSING = "MISSING"
    INTENTIONALLY_EXCEPTIONAL = "INTENTIONALLY_EXCEPTIONAL"
    PROVISIONAL_OVERLAY = "PROVISIONAL_OVERLAY"
    NOT_PRESENT = "NOT_PRESENT"
    SUPERSEDED = "SUPERSEDED"
    UNCLASSIFIED = "UNCLASSIFIED"


class LiveStatus(StrEnum):
    UNRUN = "UNRUN"
    PARTIAL = "PARTIAL"
    INVALID = "INVALID"
    COMPLETE = "COMPLETE"


class GateStatus(StrEnum):
    PASS = "PASS"
    PASS_WITH_FINDINGS = "PASS_WITH_FINDINGS"
    INCOMPLETE = "INCOMPLETE"


class ReviewerStatus(StrEnum):
    PENDING_G2 = "PENDING_G2"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    SCOPED_OUT = "SCOPED_OUT"


class PrerequisiteStatus(StrEnum):
    """Accepted Task 1 prerequisite states; near-synonyms are not interchangeable."""

    SATISFIED = "SATISFIED"
    SATISFIED_AT_PICKUP = "SATISFIED_AT_PICKUP"
    UNRESOLVED = "UNRESOLVED"
    DEFERRED_TASK_3 = "DEFERRED_TASK_3"
    UNAVAILABLE = "UNAVAILABLE"
    UNAUTHORIZED = "UNAUTHORIZED"
    UNAVAILABLE_AND_UNAUTHORIZED = "UNAVAILABLE_AND_UNAUTHORIZED"
    NOT_YET_IMPLEMENTED = "NOT_YET_IMPLEMENTED"


class InventoryKind(StrEnum):
    TASK_CREATE = "TASK_CREATE"
    CANCELLATION_POINT = "CANCELLATION_POINT"
    QUEUE = "QUEUE"
    RESOURCE_CONSTRUCT = "RESOURCE_CONSTRUCT"
    RESOURCE_TRANSFER = "RESOURCE_TRANSFER"
    RESOURCE_CLOSE = "RESOURCE_CLOSE"
    BROAD_CATCH = "BROAD_CATCH"
    SEMANTIC_WIRE_SELECTION = "SEMANTIC_WIRE_SELECTION"
    REDIS_CLIENT = "REDIS_CLIENT"
    REDIS_POOL = "REDIS_POOL"
    TELEMETRY = "TELEMETRY"
    DEBUG = "DEBUG"
    STDERR = "STDERR"
    REDACTION = "REDACTION"
    SINK = "SINK"
    DELIVERY_START = "DELIVERY_START"
    DELIVERY_PUBLICATION = "DELIVERY_PUBLICATION"
    DELIVERY_SETTLEMENT = "DELIVERY_SETTLEMENT"


class DeliveryPhase(StrEnum):
    QUEUE_ADMISSION = "QUEUE_ADMISSION"
    PUBLICATION = "PUBLICATION"
    PHYSICAL_WRITE = "PHYSICAL_WRITE"
    FLUSH = "FLUSH"
    CANCELLATION = "CANCELLATION"
    FINAL_RESPONSE = "FINAL_RESPONSE"
    CONVERSATION_COMMIT = "CONVERSATION_COMMIT"
    EFFECT_SETTLEMENT = "EFFECT_SETTLEMENT"


class CoverageAssessmentStatus(StrEnum):
    FULLY_OBSERVED = "FULLY_OBSERVED"
    SCOPED_OUT = "SCOPED_OUT"


class VocabularyCoverageStatus(StrEnum):
    FULLY_OBSERVED = "FULLY_OBSERVED"
    PARTIAL_WITH_SCOPE_OUTS = "PARTIAL_WITH_SCOPE_OUTS"


class ObservationClosureStatus(StrEnum):
    FULLY_STRUCTURALLY_CLOSED = "FULLY_STRUCTURALLY_CLOSED"


class MetadataClaimStatus(StrEnum):
    NOT_A_VOCABULARY_CLAIM = "NOT_A_VOCABULARY_CLAIM"


class ScopeOutReachability(StrEnum):
    REACHABLE = "REACHABLE"
    NOT_REACHABLE = "NOT_REACHABLE"
    NOT_YET_ASSESSED = "NOT_YET_ASSESSED"


def _closed_enum(enum_type: type[StrEnum], value: object, field: str) -> StrEnum:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must use the closed {enum_type.__name__} vocabulary") from exc


def _is_hex(value: object, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(character in "0123456789abcdef" for character in value)


def _nonnegative_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _required_string(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")


_FORBIDDEN_PERSISTED_TEXT = re.compile(
    r"(?ix)(?:"
    r"\b(?:api[_-]?key|password|passwd|access[_-]?token|refresh[_-]?token|authorization|cookie|secret)\b\s*[:=]"
    r"|\bbearer\s+[a-z0-9._~+/=-]{8,}"
    r"|(?:^|[^a-z0-9])sk-[a-z0-9_-]{8,}"
    r"|\b(?:prompt|response|request|payload)\s+(?:body|content)\b"
    r"|\braw\s+(?:prompt|response|request|payload)\b"
    r"|-----begin\s+[a-z ]*private\s+key-----"
    r")"
)


def _content_free_string(value: object, field: str) -> None:
    _required_string(value, field)
    assert isinstance(value, str)
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"{field} must not contain control characters")
    if _FORBIDDEN_PERSISTED_TEXT.search(value):
        raise ValueError(f"{field} must remain content-free")


def _json_object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a JSON object")
    return value


def _json_array(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a JSON array")
    return value


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    evidence_id: str
    baseline_scope: BaselineScope
    digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "baseline_scope", _closed_enum(BaselineScope, self.baseline_scope, "evidence baseline_scope"))
        _content_free_string(self.evidence_id, "evidence_id")
        if not _is_hex(self.digest, 64):
            raise ValueError("evidence digest must be lowercase SHA-256")

    def to_dict(self) -> dict[str, str]:
        return {"evidence_id": self.evidence_id, "baseline_scope": self.baseline_scope.value, "digest": self.digest}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> EvidenceReference:
        payload = _json_object(payload, "evidence")
        if set(payload) != {"evidence_id", "baseline_scope", "digest"}:
            raise ValueError("evidence fields do not match the canonical schema")
        return cls(evidence_id=payload["evidence_id"], baseline_scope=payload["baseline_scope"], digest=payload["digest"])


@dataclass(frozen=True, slots=True)
class Finding:
    finding_id: str
    subject: str
    classification: Classification
    baseline_scope: BaselineScope
    symbols: tuple[str, ...]
    evidence: tuple[EvidenceReference, ...]
    owner: str
    ruling: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "classification", _closed_enum(Classification, self.classification, "classification"))
        object.__setattr__(self, "baseline_scope", _closed_enum(BaselineScope, self.baseline_scope, "baseline_scope"))
        for field in ("finding_id", "subject", "owner", "ruling"):
            _content_free_string(getattr(self, field), field)
        if not self.symbols:
            raise ValueError("symbols are required")
        for symbol in self.symbols:
            _content_free_string(symbol, "finding symbol")
        object.__setattr__(self, "evidence", tuple(self.evidence))
        if not self.evidence:
            raise ValueError("evidence is required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "subject": self.subject,
            "classification": self.classification.value,
            "baseline_scope": self.baseline_scope.value,
            "symbols": sorted(self.symbols),
            "evidence": [item.to_dict() for item in sorted(self.evidence, key=lambda item: item.evidence_id)],
            "owner": self.owner,
            "ruling": self.ruling,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Finding:
        payload = _json_object(payload, "finding")
        expected = {"finding_id", "subject", "classification", "baseline_scope", "symbols", "evidence", "owner", "ruling"}
        if set(payload) != expected:
            raise ValueError("finding fields do not match the canonical schema")
        symbols = _json_array(payload["symbols"], "finding symbols")
        evidence = _json_array(payload["evidence"], "finding evidence")
        return cls(
            finding_id=payload["finding_id"],
            subject=payload["subject"],
            classification=payload["classification"],
            baseline_scope=payload["baseline_scope"],
            symbols=tuple(symbols),
            evidence=tuple(EvidenceReference.from_dict(item) for item in evidence),
            owner=payload["owner"],
            ruling=payload["ruling"],
        )


@dataclass(frozen=True, slots=True)
class DiscoveredSite:
    path: str
    symbol: str
    line: int
    kind: InventoryKind
    baseline_scope: BaselineScope
    evidence_digest: str
    classification: Classification = Classification.UNCLASSIFIED
    invariant: str | None = None
    reference: str | None = None
    delivery_phase: DeliveryPhase | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _closed_enum(InventoryKind, self.kind, "kind"))
        object.__setattr__(self, "baseline_scope", _closed_enum(BaselineScope, self.baseline_scope, "baseline_scope"))
        object.__setattr__(self, "classification", _closed_enum(Classification, self.classification, "classification"))
        if self.delivery_phase is not None:
            object.__setattr__(
                self,
                "delivery_phase",
                _closed_enum(DeliveryPhase, self.delivery_phase, "delivery_phase"),
            )
        _content_free_string(self.path, "path")
        _content_free_string(self.symbol, "symbol")
        if not (
            isinstance(self.evidence_digest, str)
            and self.evidence_digest.startswith("sha256:")
            and _is_hex(self.evidence_digest.removeprefix("sha256:"), 64)
        ):
            raise ValueError("evidence_digest must be sha256:<lowercase SHA-256>")
        if self.invariant is not None:
            _content_free_string(self.invariant, "invariant")
        if self.reference is not None:
            _content_free_string(self.reference, "reference")
        if not _nonnegative_integer(self.line) or self.line < 1:
            raise ValueError("line must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "symbol": self.symbol,
            "line": self.line,
            "kind": self.kind.value,
            "baseline_scope": self.baseline_scope.value,
            "evidence_digest": self.evidence_digest,
            "classification": self.classification.value,
            "invariant": self.invariant,
            "reference": self.reference,
            "delivery_phase": None if self.delivery_phase is None else self.delivery_phase.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> DiscoveredSite:
        payload = _json_object(payload, "discovered site")
        expected = {
            "path", "symbol", "line", "kind", "baseline_scope", "evidence_digest",
            "classification", "invariant", "reference", "delivery_phase",
        }
        if set(payload) != expected:
            raise ValueError("discovered site fields do not match the canonical schema")
        return cls(**payload)


@dataclass(frozen=True, slots=True)
class ContradictionSearchRecord:
    searched_reference_count: int
    contradictory_site_count: int
    contradictory_citations: tuple[str, ...]
    conclusion: str

    def __post_init__(self) -> None:
        if not _nonnegative_integer(self.searched_reference_count):
            raise ValueError("searched_reference_count must be nonnegative")
        if not _nonnegative_integer(self.contradictory_site_count):
            raise ValueError("contradictory_site_count must be nonnegative")
        if self.contradictory_site_count != len(self.contradictory_citations):
            raise ValueError("contradiction count does not match citations")
        for citation in self.contradictory_citations:
            _content_free_string(citation, "contradictory citation")
        _content_free_string(self.conclusion, "contradiction conclusion")

    def to_dict(self) -> dict[str, Any]:
        return {
            "searched_reference_count": self.searched_reference_count,
            "contradictory_site_count": self.contradictory_site_count,
            "contradictory_citations": sorted(self.contradictory_citations),
            "conclusion": self.conclusion,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ContradictionSearchRecord:
        payload = _json_object(payload, "contradiction search")
        expected = {"searched_reference_count", "contradictory_site_count", "contradictory_citations", "conclusion"}
        if set(payload) != expected:
            raise ValueError("contradiction search fields do not match the canonical schema")
        citations = _json_array(payload["contradictory_citations"], "contradictory citations")
        return cls(
            searched_reference_count=payload["searched_reference_count"],
            contradictory_site_count=payload["contradictory_site_count"],
            contradictory_citations=tuple(citations),
            conclusion=payload["conclusion"],
        )


@dataclass(frozen=True, slots=True)
class ScheduleOperation:
    phase: DeliveryPhase
    operation: str
    citation: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "phase", _closed_enum(DeliveryPhase, self.phase, "operation phase"))
        _content_free_string(self.operation, "operation")
        _content_free_string(self.citation, "operation citation")

    def to_dict(self) -> dict[str, str]:
        return {"phase": self.phase.value, "operation": self.operation, "citation": self.citation}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ScheduleOperation:
        payload = _json_object(payload, "schedule operation")
        if set(payload) != {"phase", "operation", "citation"}:
            raise ValueError("schedule operation fields do not match the canonical schema")
        return cls(**payload)


_H4_SCENARIOS = frozenset({
    "success-known-effect",
    "success-unknown-effect",
    "preparation-failure",
    "write-failure",
    "flush-failure",
    "session-cancel-before-protocol-write",
    "cancel-after-publication",
    "transport-teardown",
})
_CANCELLATION_TIMINGS = frozenset({"before-write", "during-write", "during-flush", "after-publication"})
_CANCELLATION_RESULTS = frozenset({"accepted", "ignored_after_cutoff", "not_attempted"})


@dataclass(frozen=True, slots=True)
class DeliveryObservation:
    seed: int
    seed_source: str
    anchor_commit: str
    schedule: tuple[DeliveryPhase, ...]
    operations: tuple[ScheduleOperation, ...]
    site_citations: tuple[str, ...]
    vocabulary_names: tuple[str, ...]
    scenario: str
    write_attempted: bool
    flush_attempted: bool
    cancellation_timing: str
    cancellation_result: str
    primary_conversation_record_count: int
    send_state: str
    send_outcome: str
    settlement: str
    final_delivery: str
    rpc_response_delivery: str
    conversation_commit: str
    effect_state: str
    classification: Classification
    contradiction: str | None

    def __post_init__(self) -> None:
        if not _nonnegative_integer(self.seed):
            raise ValueError("observation seed must be a nonnegative integer")
        if self.seed_source not in {"frozen-literal", "commit-derived"}:
            raise ValueError("observation seed_source is invalid")
        if not _is_hex(self.anchor_commit, 40):
            raise ValueError("observation anchor_commit is invalid")
        object.__setattr__(self, "schedule", tuple(_closed_enum(DeliveryPhase, phase, "schedule phase") for phase in self.schedule))
        object.__setattr__(self, "operations", tuple(self.operations))
        object.__setattr__(self, "classification", _closed_enum(Classification, self.classification, "observation classification"))
        if tuple(operation.phase for operation in self.operations) != self.schedule:
            raise ValueError("ordered operations must exactly match the schedule phases")
        if len(self.schedule) != len(DeliveryPhase) or set(self.schedule) != set(DeliveryPhase):
            raise ValueError("observation schedule must cover every delivery phase exactly once")
        if self.site_citations != tuple(operation.citation for operation in self.operations):
            raise ValueError("operation citations must exactly match site_citations")
        if self.scenario not in _H4_SCENARIOS:
            raise ValueError("observation scenario is invalid")
        if type(self.write_attempted) is not bool or type(self.flush_attempted) is not bool:
            raise ValueError("observation attempt fields must be booleans")
        if self.flush_attempted and not self.write_attempted:
            raise ValueError("flush cannot be attempted without a primary write attempt")
        if self.cancellation_timing not in _CANCELLATION_TIMINGS:
            raise ValueError("observation cancellation timing is invalid")
        if self.cancellation_result not in _CANCELLATION_RESULTS:
            raise ValueError("observation cancellation result is invalid")
        if self.primary_conversation_record_count not in {0, 1}:
            raise ValueError("primary conversation record count must be zero or one")
        operation_by_phase = {operation.phase: operation.operation for operation in self.operations}
        if any(
            forbidden in operation.operation
            for operation in self.operations
            for forbidden in ("control", "substitute")
        ):
            raise ValueError("observation operations must use only the primary object graph")
        write_prefix = "write_attempted_" if self.write_attempted else "write_not_attempted_"
        flush_prefix = "flush_attempted_" if self.flush_attempted else "flush_not_attempted_"
        if not operation_by_phase[DeliveryPhase.PHYSICAL_WRITE].startswith(write_prefix):
            raise ValueError("write attempt field disagrees with the primary operation")
        if not operation_by_phase[DeliveryPhase.FLUSH].startswith(flush_prefix):
            raise ValueError("flush attempt field disagrees with the primary operation")
        cancellation_operation = operation_by_phase[DeliveryPhase.CANCELLATION]
        if (
            self.cancellation_timing not in cancellation_operation
            or self.cancellation_result not in cancellation_operation
        ):
            raise ValueError("cancellation fields disagree with the primary operation")
        committed = self.conversation_commit == "committed"
        if committed != (self.primary_conversation_record_count == 1):
            raise ValueError("conversation commit disagrees with the primary conversation state")
        commit_prefix = "commit_after_final_flush_" if committed else "commit_withheld_after_prepare_"
        if not operation_by_phase[DeliveryPhase.CONVERSATION_COMMIT].startswith(commit_prefix):
            raise ValueError("conversation commit disagrees with the primary operation")
        if self.classification is Classification.UNCLASSIFIED:
            raise ValueError("observation may not remain UNCLASSIFIED")
        if (self.classification is Classification.CONTRADICTORY) != (self.contradiction is not None):
            raise ValueError("observation contradiction and classification disagree")
        if self.contradiction is not None:
            _content_free_string(self.contradiction, "observation contradiction")
        for field in (
            "send_state", "send_outcome", "settlement", "final_delivery", "rpc_response_delivery",
            "conversation_commit", "effect_state",
        ):
            _required_string(getattr(self, field), field)

    @property
    def complete(self) -> bool:
        return (
            len(self.schedule) == len(DeliveryPhase)
            and set(self.schedule) == set(DeliveryPhase)
            and tuple(operation.phase for operation in self.operations) == self.schedule
            and tuple(operation.citation for operation in self.operations) == self.site_citations
            and self.classification is not Classification.UNCLASSIFIED
            and (self.classification is Classification.CONTRADICTORY) == (self.contradiction is not None)
            and all(
                isinstance(value, str) and bool(value)
                for value in (
                    self.send_state, self.send_outcome, self.settlement, self.final_delivery,
                    self.rpc_response_delivery, self.conversation_commit, self.effect_state,
                )
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "seed_source": self.seed_source,
            "anchor_commit": self.anchor_commit,
            "schedule": [phase.value for phase in self.schedule],
            "operations": [operation.to_dict() for operation in self.operations],
            "site_citations": list(self.site_citations),
            "vocabulary_names": list(self.vocabulary_names),
            "scenario": self.scenario,
            "write_attempted": self.write_attempted,
            "flush_attempted": self.flush_attempted,
            "cancellation_timing": self.cancellation_timing,
            "cancellation_result": self.cancellation_result,
            "primary_conversation_record_count": self.primary_conversation_record_count,
            "send_state": self.send_state,
            "send_outcome": self.send_outcome,
            "settlement": self.settlement,
            "final_delivery": self.final_delivery,
            "rpc_response_delivery": self.rpc_response_delivery,
            "conversation_commit": self.conversation_commit,
            "effect_state": self.effect_state,
            "classification": self.classification.value,
            "contradiction": self.contradiction,
            "complete": self.complete,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> DeliveryObservation:
        payload = _json_object(payload, "delivery observation")
        expected = {
            "seed", "seed_source", "anchor_commit", "schedule", "operations", "site_citations",
            "vocabulary_names", "scenario", "write_attempted", "flush_attempted",
            "cancellation_timing", "cancellation_result", "primary_conversation_record_count",
            "send_state", "send_outcome", "settlement", "final_delivery",
            "rpc_response_delivery", "conversation_commit", "effect_state", "classification",
            "contradiction", "complete",
        }
        if set(payload) != expected or payload["complete"] is not True:
            raise ValueError("delivery observation fields do not match the canonical complete schema")
        return cls(
            seed=payload["seed"], seed_source=payload["seed_source"], anchor_commit=payload["anchor_commit"],
            schedule=tuple(_json_array(payload["schedule"], "observation schedule")),
            operations=tuple(ScheduleOperation.from_dict(item) for item in _json_array(payload["operations"], "observation operations")),
            site_citations=tuple(_json_array(payload["site_citations"], "observation citations")),
            vocabulary_names=tuple(_json_array(payload["vocabulary_names"], "observation vocabulary")),
            scenario=payload["scenario"], write_attempted=payload["write_attempted"],
            flush_attempted=payload["flush_attempted"],
            cancellation_timing=payload["cancellation_timing"],
            cancellation_result=payload["cancellation_result"],
            primary_conversation_record_count=payload["primary_conversation_record_count"],
            send_state=payload["send_state"], send_outcome=payload["send_outcome"], settlement=payload["settlement"],
            final_delivery=payload["final_delivery"], rpc_response_delivery=payload["rpc_response_delivery"],
            conversation_commit=payload["conversation_commit"], effect_state=payload["effect_state"],
            classification=payload["classification"], contradiction=payload["contradiction"],
        )


_H4_VOCABULARY_NAMES = frozenset({
    "SendState", "SendOutcome", "Settlement", "FinalDelivery", "RpcResponseDelivery",
    "ConversationCommit", "EffectState",
})
_H4_COVERAGE_FIELDS = (
    ("conversation_commit", "ConversationCommit"),
    ("effect_state", "EffectState"),
    ("final_delivery", "FinalDelivery"),
    ("rpc_response_delivery", "RpcResponseDelivery"),
    ("send_outcome", "SendOutcome"),
    ("send_state", "SendState"),
    ("settlement", "Settlement"),
)
_H4_CONSTANT_METADATA_FIELDS = frozenset({"classification", "complete", "contradiction"})
_H4_COVERAGE_OWNER = "P11-FEAT-ACP-RUNTIME-HARDENING"


@dataclass(frozen=True, slots=True)
class VocabularyCoverageAssessment:
    field_name: str
    type_name: str
    vocabulary_values: tuple[str, ...]
    observed_values: tuple[str, ...]
    missing_values: tuple[str, ...]
    status: CoverageAssessmentStatus
    reason: str | None
    owner: str | None
    next_gate: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "status", _closed_enum(CoverageAssessmentStatus, self.status, "coverage status"),
        )
        _content_free_string(self.field_name, "coverage field_name")
        _content_free_string(self.type_name, "coverage type_name")
        for field in ("vocabulary_values", "observed_values", "missing_values"):
            values = tuple(getattr(self, field))
            object.__setattr__(self, field, values)
            if values != tuple(sorted(set(values))):
                raise ValueError(f"coverage {field} must contain unique canonical strings")
            for value in values:
                _content_free_string(value, f"coverage {field}")
        if not self.vocabulary_values:
            raise ValueError("coverage vocabulary_values must not be empty")
        vocabulary = set(self.vocabulary_values)
        observed = set(self.observed_values)
        missing = set(self.missing_values)
        if not observed or not observed <= vocabulary or missing != vocabulary - observed:
            raise ValueError("coverage observed and missing values must partition the vocabulary")
        if self.status is CoverageAssessmentStatus.FULLY_OBSERVED:
            if missing or any(value is not None for value in (self.reason, self.owner, self.next_gate)):
                raise ValueError("fully observed coverage must have no missing values or scope-out ownership")
        else:
            if not missing:
                raise ValueError("scoped-out coverage must name missing values")
            for field in ("reason", "owner", "next_gate"):
                _content_free_string(getattr(self, field), f"coverage {field}")
            if self.owner != _H4_COVERAGE_OWNER:
                raise ValueError("scoped-out coverage must use the canonical owner")

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_name": self.field_name,
            "type_name": self.type_name,
            "vocabulary_values": list(self.vocabulary_values),
            "observed_values": list(self.observed_values),
            "missing_values": list(self.missing_values),
            "status": self.status.value,
            "reason": self.reason,
            "owner": self.owner,
            "next_gate": self.next_gate,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> VocabularyCoverageAssessment:
        payload = _json_object(payload, "vocabulary coverage assessment")
        expected = {
            "field_name", "type_name", "vocabulary_values", "observed_values", "missing_values",
            "status", "reason", "owner", "next_gate",
        }
        if set(payload) != expected:
            raise ValueError("vocabulary coverage assessment fields do not match the canonical schema")
        return cls(
            field_name=payload["field_name"],
            type_name=payload["type_name"],
            vocabulary_values=tuple(_json_array(payload["vocabulary_values"], "coverage vocabulary values")),
            observed_values=tuple(_json_array(payload["observed_values"], "coverage observed values")),
            missing_values=tuple(_json_array(payload["missing_values"], "coverage missing values")),
            status=payload["status"],
            reason=payload["reason"],
            owner=payload["owner"],
            next_gate=payload["next_gate"],
        )


@dataclass(frozen=True, slots=True)
class ScopeOutRegisterEntry:
    hypothesis_id: str
    field_name: str
    owning_gate: str
    missing_values: tuple[str, ...]
    owner: str
    reachable_in_gate: ScopeOutReachability
    reachability_reason: str

    def __post_init__(self) -> None:
        for field in (
            "hypothesis_id", "field_name", "owning_gate", "owner", "reachability_reason",
        ):
            _content_free_string(getattr(self, field), f"scope-out {field}")
        object.__setattr__(self, "missing_values", tuple(self.missing_values))
        object.__setattr__(
            self,
            "reachable_in_gate",
            _closed_enum(ScopeOutReachability, self.reachable_in_gate, "scope-out reachable_in_gate"),
        )
        if self.missing_values != tuple(sorted(set(self.missing_values))) or not self.missing_values:
            raise ValueError("scope-out missing_values must be non-empty canonical strings")
        for value in self.missing_values:
            _content_free_string(value, "scope-out missing value")

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "field_name": self.field_name,
            "owning_gate": self.owning_gate,
            "missing_values": list(self.missing_values),
            "owner": self.owner,
            "reachable_in_gate": self.reachable_in_gate.value,
            "reachability_reason": self.reachability_reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ScopeOutRegisterEntry:
        payload = _json_object(payload, "scope-out register entry")
        expected = {
            "hypothesis_id", "field_name", "owning_gate", "missing_values", "owner",
            "reachable_in_gate", "reachability_reason",
        }
        if set(payload) != expected:
            raise ValueError("scope-out register fields do not match the canonical schema")
        return cls(
            hypothesis_id=payload["hypothesis_id"],
            field_name=payload["field_name"],
            owning_gate=payload["owning_gate"],
            missing_values=tuple(_json_array(payload["missing_values"], "scope-out missing values")),
            owner=payload["owner"],
            reachable_in_gate=payload["reachable_in_gate"],
            reachability_reason=payload["reachability_reason"],
        )


@dataclass(frozen=True, slots=True)
class ConstantMetadataNote:
    field_name: str
    constant_value: str | bool | None
    claim_status: MetadataClaimStatus
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "claim_status", _closed_enum(MetadataClaimStatus, self.claim_status, "metadata claim status"),
        )
        if self.field_name not in _H4_CONSTANT_METADATA_FIELDS:
            raise ValueError("constant metadata note field_name is invalid")
        if self.constant_value is not None and not isinstance(self.constant_value, (str, bool)):
            raise ValueError("constant metadata note value is invalid")
        _content_free_string(self.reason, "constant metadata note reason")

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_name": self.field_name,
            "constant_value": self.constant_value,
            "claim_status": self.claim_status.value,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ConstantMetadataNote:
        payload = _json_object(payload, "constant metadata note")
        if set(payload) != {"field_name", "constant_value", "claim_status", "reason"}:
            raise ValueError("constant metadata note fields do not match the canonical schema")
        return cls(**payload)


@dataclass(frozen=True, slots=True)
class ScheduleObservationSummary:
    literal_seeds: tuple[int, ...]
    derived_seed_count: int
    derived_seed_anchor_commit: str
    total_observation_count: int
    complete_observation_count: int
    observation_closure_status: ObservationClosureStatus
    vocabulary_coverage_status: VocabularyCoverageStatus
    classification_counts: Mapping[str, int]
    digest: str
    vocabulary: Mapping[str, Mapping[str, str]]
    coverage_assessments: tuple[VocabularyCoverageAssessment, ...]
    constant_metadata_notes: tuple[ConstantMetadataNote, ...]
    observations: tuple[DeliveryObservation, ...]

    def __post_init__(self) -> None:
        if any(not _nonnegative_integer(seed) for seed in self.literal_seeds):
            raise ValueError("literal seeds must be nonnegative integers")
        for field in ("derived_seed_count", "total_observation_count", "complete_observation_count"):
            if not _nonnegative_integer(getattr(self, field)):
                raise ValueError(f"{field} must be nonnegative")
        if self.total_observation_count != len(self.literal_seeds) + self.derived_seed_count:
            raise ValueError("observation count does not match literal and derived schedules")
        if self.complete_observation_count != self.total_observation_count:
            raise ValueError("every schedule observation must be complete")
        object.__setattr__(
            self,
            "observation_closure_status",
            _closed_enum(
                ObservationClosureStatus,
                self.observation_closure_status,
                "observation closure status",
            ),
        )
        object.__setattr__(
            self,
            "vocabulary_coverage_status",
            _closed_enum(
                VocabularyCoverageStatus,
                self.vocabulary_coverage_status,
                "vocabulary coverage status",
            ),
        )
        if not _is_hex(self.derived_seed_anchor_commit, 40):
            raise ValueError("derived seed anchor must be a lowercase 40-hex commit")
        if not isinstance(self.classification_counts, dict) or set(self.classification_counts) != {
            classification.value for classification in Classification
        }:
            raise ValueError("schedule classification counts must use the closed vocabulary")
        if any(not _nonnegative_integer(value) for value in self.classification_counts.values()):
            raise ValueError("schedule classification counts must be nonnegative")
        if sum(self.classification_counts.values()) != self.total_observation_count:
            raise ValueError("schedule classification counts do not match observations")
        if self.classification_counts[Classification.UNCLASSIFIED.value] != 0:
            raise ValueError("schedule observations may not remain UNCLASSIFIED")
        if not _is_hex(self.digest, 64):
            raise ValueError("schedule digest must be lowercase SHA-256")
        if not isinstance(self.vocabulary, dict) or set(self.vocabulary) != _H4_VOCABULARY_NAMES:
            raise ValueError("schedule vocabulary must contain exactly the seven settled types")
        for name, members in self.vocabulary.items():
            if (
                not isinstance(members, dict)
                or not members
                or any(not isinstance(member, str) or not member or not isinstance(value, str) or not value for member, value in members.items())
            ):
                raise ValueError(f"schedule vocabulary {name} is invalid")
        object.__setattr__(self, "observations", tuple(self.observations))
        if len(self.observations) != self.total_observation_count:
            raise ValueError("stored observations do not match total_observation_count")
        expected_seeds = tuple(self.literal_seeds) + tuple(
            derived_seed(self.derived_seed_anchor_commit, "H4-delivery", index)
            for index in range(self.derived_seed_count)
        )
        if tuple(observation.seed for observation in self.observations) != expected_seeds:
            raise ValueError("stored observation seed sequence is invalid")
        expected_sources = ("frozen-literal",) * len(self.literal_seeds) + ("commit-derived",) * self.derived_seed_count
        if tuple(observation.seed_source for observation in self.observations) != expected_sources:
            raise ValueError("stored observation seed sources are invalid")
        if any(observation.anchor_commit != self.derived_seed_anchor_commit for observation in self.observations):
            raise ValueError("stored observation anchor commits are invalid")
        counts = Counter(observation.classification.value for observation in self.observations)
        if dict(self.classification_counts) != {
            classification.value: counts[classification.value] for classification in Classification
        }:
            raise ValueError("schedule classification counts do not match stored observations")
        if self.complete_observation_count != sum(observation.complete for observation in self.observations):
            raise ValueError("complete observation count does not match stored observations")
        if self.digest != _canonical_digest([observation.to_dict() for observation in self.observations]):
            raise ValueError("schedule digest does not match stored observations")
        for observation in self.observations:
            if set(observation.vocabulary_names) != _H4_VOCABULARY_NAMES:
                raise ValueError("observation vocabulary names drifted")
            values = (
                ("SendState", observation.send_state), ("SendOutcome", observation.send_outcome),
                ("Settlement", observation.settlement), ("FinalDelivery", observation.final_delivery),
                ("RpcResponseDelivery", observation.rpc_response_delivery),
                ("ConversationCommit", observation.conversation_commit), ("EffectState", observation.effect_state),
            )
            if any(value not in self.vocabulary[name].values() for name, value in values):
                raise ValueError("observation uses a value outside the source-derived vocabulary")
        object.__setattr__(self, "coverage_assessments", tuple(self.coverage_assessments))
        assessments = {assessment.field_name: assessment for assessment in self.coverage_assessments}
        expected_fields = {field_name for field_name, _ in _H4_COVERAGE_FIELDS}
        if len(assessments) != len(self.coverage_assessments) or set(assessments) != expected_fields:
            raise ValueError("coverage assessments must contain exactly the seven settled fields")
        has_scope_out = False
        for field_name, type_name in _H4_COVERAGE_FIELDS:
            assessment = assessments[field_name]
            vocabulary_values = tuple(sorted(set(self.vocabulary[type_name].values())))
            observed_values = tuple(sorted({getattr(item, field_name) for item in self.observations}))
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
                raise ValueError("coverage assessment disagrees with observations or source vocabulary")
        expected_coverage_status = (
            VocabularyCoverageStatus.PARTIAL_WITH_SCOPE_OUTS
            if has_scope_out
            else VocabularyCoverageStatus.FULLY_OBSERVED
        )
        if self.vocabulary_coverage_status is not expected_coverage_status:
            raise ValueError("aggregate vocabulary coverage status disagrees with assessments")
        if self.observation_closure_status is not ObservationClosureStatus.FULLY_STRUCTURALLY_CLOSED:
            raise ValueError("complete observations must be labelled structurally closed")
        object.__setattr__(self, "constant_metadata_notes", tuple(self.constant_metadata_notes))
        notes = {note.field_name: note for note in self.constant_metadata_notes}
        if len(notes) != len(self.constant_metadata_notes) or set(notes) != _H4_CONSTANT_METADATA_FIELDS:
            raise ValueError("constant metadata notes must contain exactly the closed dimensions")
        metadata_values = {
            "classification": {item.classification.value for item in self.observations},
            "complete": {item.complete for item in self.observations},
            "contradiction": {item.contradiction for item in self.observations},
        }
        for field_name, values in metadata_values.items():
            if len(values) != 1 or notes[field_name].constant_value != next(iter(values)):
                raise ValueError("constant metadata note disagrees with stored observations")

    def to_dict(self) -> dict[str, Any]:
        return {
            "literal_seeds": list(self.literal_seeds),
            "derived_seed_count": self.derived_seed_count,
            "derived_seed_anchor_commit": self.derived_seed_anchor_commit,
            "total_observation_count": self.total_observation_count,
            "complete_observation_count": self.complete_observation_count,
            "observation_closure_status": self.observation_closure_status.value,
            "vocabulary_coverage_status": self.vocabulary_coverage_status.value,
            "classification_counts": _canonical(self.classification_counts),
            "digest": self.digest,
            "vocabulary": _canonical(self.vocabulary),
            "coverage_assessments": [
                assessment.to_dict()
                for assessment in sorted(self.coverage_assessments, key=lambda item: item.field_name)
            ],
            "constant_metadata_notes": [
                note.to_dict()
                for note in sorted(self.constant_metadata_notes, key=lambda item: item.field_name)
            ],
            "observations": [observation.to_dict() for observation in self.observations],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ScheduleObservationSummary:
        payload = _json_object(payload, "schedule observations")
        expected = {
            "literal_seeds", "derived_seed_count", "derived_seed_anchor_commit", "total_observation_count",
            "complete_observation_count", "observation_closure_status", "vocabulary_coverage_status",
            "classification_counts", "digest", "vocabulary", "coverage_assessments",
            "constant_metadata_notes", "observations",
        }
        if set(payload) != expected:
            raise ValueError("schedule observation fields do not match the canonical schema")
        seeds = _json_array(payload["literal_seeds"], "literal seeds")
        counts = _json_object(payload["classification_counts"], "schedule classification counts")
        return cls(
            literal_seeds=tuple(seeds),
            derived_seed_count=payload["derived_seed_count"],
            derived_seed_anchor_commit=payload["derived_seed_anchor_commit"],
            total_observation_count=payload["total_observation_count"],
            complete_observation_count=payload["complete_observation_count"],
            observation_closure_status=payload["observation_closure_status"],
            vocabulary_coverage_status=payload["vocabulary_coverage_status"],
            classification_counts=counts,
            digest=payload["digest"],
            vocabulary=_json_object(payload["vocabulary"], "schedule vocabulary"),
            coverage_assessments=tuple(
                VocabularyCoverageAssessment.from_dict(item)
                for item in _json_array(payload["coverage_assessments"], "coverage assessments")
            ),
            constant_metadata_notes=tuple(
                ConstantMetadataNote.from_dict(item)
                for item in _json_array(payload["constant_metadata_notes"], "constant metadata notes")
            ),
            observations=tuple(
                DeliveryObservation.from_dict(item)
                for item in _json_array(payload["observations"], "stored schedule observations")
            ),
        )


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    record_id: str
    hypothesis_id: str
    subject: str
    baseline_scope: BaselineScope
    baseline_anchor_commit: str
    overlay_commit: str
    binding_commit: str | None
    vocabulary_names: tuple[str, ...]
    symbol_citations: tuple[str, ...]
    discovered_sites: tuple[DiscoveredSite, ...]
    contradiction_search: ContradictionSearchRecord
    schedule_observations: ScheduleObservationSummary
    commands: tuple[str, ...]
    ruling: str
    reviewer_status: ReviewerStatus
    content_free_evidence: tuple[EvidenceReference, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "baseline_scope", _closed_enum(BaselineScope, self.baseline_scope, "evidence record baseline_scope"))
        object.__setattr__(self, "reviewer_status", _closed_enum(ReviewerStatus, self.reviewer_status, "reviewer_status"))
        for field in ("record_id", "hypothesis_id", "subject", "ruling"):
            _content_free_string(getattr(self, field), field)
        if not _is_hex(self.baseline_anchor_commit, 40) or not _is_hex(self.overlay_commit, 40):
            raise ValueError("evidence record commits must be lowercase 40-hex")
        if self.binding_commit is not None and not _is_hex(self.binding_commit, 40):
            raise ValueError("evidence record binding_commit is invalid")
        for field in ("vocabulary_names", "symbol_citations", "commands"):
            values = getattr(self, field)
            if not values:
                raise ValueError(f"{field} must contain non-empty strings")
            for value in values:
                _content_free_string(value, field)
        if not self.discovered_sites or any(site.delivery_phase is None for site in self.discovered_sites):
            raise ValueError("evidence record requires phase-labelled discovered sites")
        if any(site.classification is Classification.UNCLASSIFIED for site in self.discovered_sites):
            raise ValueError("evidence record discovered sites may not remain UNCLASSIFIED")
        conceptual_groups: dict[tuple[str, int, str, str | None], list[DiscoveredSite]] = {}
        for site in self.discovered_sites:
            key = (site.path, site.line, site.symbol, site.reference)
            conceptual_groups.setdefault(key, []).append(site)
        for variants in conceptual_groups.values():
            valid_divergence = (
                len(variants) == 2
                and all(site.baseline_scope is BaselineScope.BOTH_DIVERGENT for site in variants)
                and len({site.evidence_digest for site in variants}) == 2
            )
            if len(variants) != 1 and not valid_divergence:
                raise ValueError("discovered sites contain a duplicate conceptual site")
        expected_citations = tuple(sorted(
            f"{site.path}:{site.line}:{site.symbol}:{site.reference}" for site in self.discovered_sites
        ))
        if tuple(sorted(self.symbol_citations)) != expected_citations:
            raise ValueError("symbol citations must cover every discovered site exactly once")
        contradictory = tuple(sorted(
            f"{site.path}:{site.line}:{site.symbol}:{site.reference}"
            for site in self.discovered_sites
            if site.classification is Classification.CONTRADICTORY
        ))
        if self.contradiction_search.searched_reference_count != len(self.discovered_sites):
            raise ValueError("contradiction search count must equal discovered sites")
        if self.contradiction_search.contradictory_citations != contradictory:
            raise ValueError("contradiction citations must equal the contradictory discovered-site subset")
        if self.contradiction_search.contradictory_site_count != len(contradictory):
            raise ValueError("contradiction site count must equal the contradictory discovered-site subset")
        if not self.content_free_evidence:
            raise ValueError("content_free_evidence is required")
        if self.hypothesis_id == "H4":
            if set(self.vocabulary_names) != _H4_VOCABULARY_NAMES:
                raise ValueError("H4 vocabulary must be exactly the seven settled type names")
            if self.schedule_observations.literal_seeds != literal_seeds():
                raise ValueError("H4 literal seeds must match the frozen corpus in order")
            if self.schedule_observations.derived_seed_count != 1_000:
                raise ValueError("H4 requires exactly 1,000 derived seeds")
            if self.schedule_observations.derived_seed_anchor_commit != self.baseline_anchor_commit:
                raise ValueError("H4 seed anchor must equal its merged baseline anchor")
        evidence = {item.evidence_id: item for item in self.content_free_evidence}
        inventory = evidence.get("H4-AST-INVENTORY")
        schedule = evidence.get("H4-SCHEDULE-OBSERVATIONS")
        if self.hypothesis_id == "H4" and (inventory is None or schedule is None):
            raise ValueError("H4 requires inventory and schedule content-free evidence")
        if inventory is not None and inventory.digest != _canonical_digest(
            [site.to_dict() for site in self.discovered_sites]
        ):
            raise ValueError("inventory evidence digest does not match discovered sites")
        if schedule is not None and schedule.digest != self.schedule_observations.digest:
            raise ValueError("schedule evidence digest does not match stored observations")

    def to_dict(self) -> dict[str, Any]:
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
            "contradiction_search": self.contradiction_search.to_dict(),
            "schedule_observations": self.schedule_observations.to_dict(),
            "commands": list(self.commands),
            "ruling": self.ruling,
            "reviewer_status": self.reviewer_status.value,
            "content_free_evidence": [item.to_dict() for item in self.content_free_evidence],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> EvidenceRecord:
        payload = _json_object(payload, "evidence record")
        expected = {
            "record_id", "hypothesis_id", "subject", "baseline_scope", "baseline_anchor_commit",
            "overlay_commit", "binding_commit", "vocabulary_names", "symbol_citations", "discovered_sites",
            "contradiction_search", "schedule_observations", "commands", "ruling", "reviewer_status",
            "content_free_evidence",
        }
        if set(payload) != expected:
            raise ValueError("evidence record fields do not match the canonical schema")
        return cls(
            record_id=payload["record_id"],
            hypothesis_id=payload["hypothesis_id"],
            subject=payload["subject"],
            baseline_scope=payload["baseline_scope"],
            baseline_anchor_commit=payload["baseline_anchor_commit"],
            overlay_commit=payload["overlay_commit"],
            binding_commit=payload["binding_commit"],
            vocabulary_names=tuple(_json_array(payload["vocabulary_names"], "vocabulary names")),
            symbol_citations=tuple(_json_array(payload["symbol_citations"], "symbol citations")),
            discovered_sites=tuple(DiscoveredSite.from_dict(item) for item in _json_array(payload["discovered_sites"], "discovered sites")),
            contradiction_search=ContradictionSearchRecord.from_dict(payload["contradiction_search"]),
            schedule_observations=ScheduleObservationSummary.from_dict(payload["schedule_observations"]),
            commands=tuple(_json_array(payload["commands"], "commands")),
            ruling=payload["ruling"],
            reviewer_status=payload["reviewer_status"],
            content_free_evidence=tuple(EvidenceReference.from_dict(item) for item in _json_array(payload["content_free_evidence"], "content-free evidence")),
        )


_PROVENANCE_REQUIRED = {
    "binding_commit",
    "executable_path",
    "executable_sha256",
    "package_name",
    "package_version",
    "package_metadata_sha256",
    "build_manifest_sha256",
    "embedded_commit",
    "embedded_commit_sha256",
    "launcher_sha256",
    "client_provenance",
    "environment_fingerprint",
}
_MULTIPLIER_FIELDS = {"cancellation_points", "queues", "sinks", "close_paths"}
_COST_FIELDS = {
    "cancellation_concurrency_levels",
    "cancellation_schedules",
    "cancellation_control_schedules",
    "queue_admissions",
    "sink_failure_runs",
    "idempotent_close_invocations",
    "scenario_p50_ms",
    "scenario_p95_ms",
}


def _default_scope_out_register(records: tuple[object, ...]) -> tuple[ScopeOutRegisterEntry, ...]:
    entries: list[ScopeOutRegisterEntry] = []
    for record in records:
        hypothesis_id = record.hypothesis_id
        summary = getattr(record, "schedule_observations", None)
        for assessment in getattr(summary, "coverage_assessments", ()):
            if assessment.status is not CoverageAssessmentStatus.SCOPED_OUT:
                continue
            assert assessment.next_gate is not None
            assert assessment.owner is not None
            entries.append(
                ScopeOutRegisterEntry(
                    hypothesis_id=hypothesis_id,
                    field_name=assessment.field_name,
                    owning_gate=assessment.next_gate,
                    missing_values=assessment.missing_values,
                    owner=assessment.owner,
                    reachable_in_gate=ScopeOutReachability.NOT_YET_ASSESSED,
                    reachability_reason=(
                        f"Reachability against {assessment.next_gate} remains an explicit open obligation; "
                        "the owning gate must prove it from raw observations."
                    ),
                )
            )
    return tuple(entries)


def assert_scope_out_register_ready_for_g4(entries: tuple[ScopeOutRegisterEntry, ...]) -> None:
    """Reject a G4 close while vocabulary debt lacks a reachability ruling."""

    unresolved = tuple(
        sorted(
            f"{entry.hypothesis_id}:{entry.field_name}"
            for entry in entries
            if entry.reachable_in_gate is ScopeOutReachability.NOT_YET_ASSESSED
        )
    )
    if unresolved:
        raise ValueError(f"G4 scope-out register contains NOT_YET_ASSESSED entries: {', '.join(unresolved)}")


@dataclass(frozen=True, slots=True)
class AuditArtifact:
    schema_version: str
    merged_commit: str
    overlay_commit: str
    binding_commit: str | None
    baseline_reconciliation_status: str
    running_artifact_provenance: Mapping[str, Any] | None
    static_audit_status: LiveStatus
    runtime_characterization_status: LiveStatus
    live_redis_status: LiveStatus
    acpx_status: LiveStatus
    additional_client_status: LiveStatus
    zed_status: LiveStatus
    live_interoperability_status: LiveStatus
    findings: tuple[Finding, ...]
    discovered_multipliers: Mapping[str, int]
    computed_run_cost: Mapping[str, Any]
    gate_status: GateStatus
    evidence_records: tuple[EvidenceRecord, ...] = ()
    scope_out_register: tuple[ScopeOutRegisterEntry, ...] | None = None

    def __post_init__(self) -> None:
        if self.schema_version != "plan-11-26-runtime-audit-v1":
            raise ValueError("schema_version is invalid")
        if not _is_hex(self.merged_commit, 40) or not _is_hex(self.overlay_commit, 40):
            raise ValueError("merged_commit and overlay_commit must be lowercase 40-hex commits")
        if self.binding_commit is not None and not _is_hex(self.binding_commit, 40):
            raise ValueError("binding_commit must be null or a lowercase 40-hex commit")
        if not isinstance(self.baseline_reconciliation_status, str) or not self.baseline_reconciliation_status:
            raise ValueError("baseline_reconciliation_status is required")
        for field in (
            "static_audit_status", "runtime_characterization_status", "live_redis_status", "acpx_status",
            "additional_client_status", "zed_status", "live_interoperability_status",
        ):
            object.__setattr__(self, field, _closed_enum(LiveStatus, getattr(self, field), field))
        live_evidence_statuses = (
            self.live_redis_status,
            self.acpx_status,
            self.additional_client_status,
            self.zed_status,
            self.live_interoperability_status,
        )
        if any(status in {LiveStatus.PARTIAL, LiveStatus.COMPLETE} for status in live_evidence_statuses) and (
            self.binding_commit is None or self.running_artifact_provenance is None
        ):
            raise ValueError("live evidence requires binding_commit and running_artifact_provenance")
        object.__setattr__(self, "gate_status", _closed_enum(GateStatus, self.gate_status, "gate_status"))
        object.__setattr__(self, "findings", tuple(self.findings))
        object.__setattr__(self, "evidence_records", tuple(self.evidence_records))
        if self.scope_out_register is None:
            object.__setattr__(self, "scope_out_register", _default_scope_out_register(self.evidence_records))
        else:
            object.__setattr__(self, "scope_out_register", tuple(self.scope_out_register))
        if (
            self.static_audit_status in {LiveStatus.PARTIAL, LiveStatus.COMPLETE}
            or self.runtime_characterization_status in {LiveStatus.PARTIAL, LiveStatus.COMPLETE}
        ) and not self.evidence_records:
            raise ValueError("partial or complete static/runtime characterization requires evidence_records")
        if len({record.hypothesis_id for record in self.evidence_records}) != len(self.evidence_records):
            raise ValueError("evidence_records must contain at most one record per hypothesis")
        if not isinstance(self.discovered_multipliers, dict) or set(self.discovered_multipliers) != _MULTIPLIER_FIELDS:
            raise ValueError("discovered_multipliers fields do not match the canonical schema")
        if any(not _nonnegative_integer(value) for value in self.discovered_multipliers.values()):
            raise ValueError("discovered_multipliers must be nonnegative integers")
        if not isinstance(self.computed_run_cost, dict) or set(self.computed_run_cost) != _COST_FIELDS:
            raise ValueError("computed_run_cost fields do not match the canonical schema")
        if (
            not isinstance(self.computed_run_cost["cancellation_concurrency_levels"], list)
            or self.computed_run_cost["cancellation_concurrency_levels"] != [2, 4, 8]
        ):
            raise ValueError("cancellation_concurrency_levels must be exactly [2, 4, 8]")
        for field in (
            "cancellation_schedules", "cancellation_control_schedules", "queue_admissions",
            "sink_failure_runs", "idempotent_close_invocations",
        ):
            if not _nonnegative_integer(self.computed_run_cost[field]):
                raise ValueError(f"{field} must be a nonnegative integer")
        for field in ("scenario_p50_ms", "scenario_p95_ms"):
            durations = self.computed_run_cost[field]
            if not isinstance(durations, dict) or any(
                not isinstance(name, str) or not name or not isinstance(value, (int, float))
                or isinstance(value, bool) or value < 0 or not math.isfinite(value)
                for name, value in durations.items()
            ):
                raise ValueError(f"{field} must contain nonnegative finite durations")
        if self.running_artifact_provenance is not None and (
            not isinstance(self.running_artifact_provenance, dict)
            or set(self.running_artifact_provenance) != _PROVENANCE_REQUIRED
        ):
            raise ValueError("running_artifact_provenance must be external and complete; workspace git_sha is insufficient")
        if self.running_artifact_provenance is not None:
            provenance = self.running_artifact_provenance
            for field in ("executable_path", "package_name", "package_version"):
                if not isinstance(provenance[field], str) or not provenance[field]:
                    raise ValueError(f"running_artifact_provenance {field} is invalid")
            for field in (
                "executable_sha256", "package_metadata_sha256", "build_manifest_sha256",
                "embedded_commit_sha256", "launcher_sha256", "environment_fingerprint",
            ):
                if not _is_hex(provenance[field], 64):
                    raise ValueError(f"running_artifact_provenance {field} is invalid")
            if not _is_hex(provenance["binding_commit"], 40) or not _is_hex(provenance["embedded_commit"], 40):
                raise ValueError("running_artifact_provenance commit identity is invalid")
            if provenance["binding_commit"] != self.binding_commit or provenance["embedded_commit"] != self.binding_commit:
                raise ValueError("running_artifact_provenance does not match binding_commit")
            client = provenance["client_provenance"]
            if not isinstance(client, dict) or set(client) != {"name", "version", "path", "sha256", "metadata_sha256"}:
                raise ValueError("running_artifact_provenance client_provenance is invalid")
            if any(not isinstance(client[field], str) or not client[field] for field in ("name", "version", "path")):
                raise ValueError("running_artifact_provenance client identity is invalid")
            if not _is_hex(client["sha256"], 64) or not _is_hex(client["metadata_sha256"], 64):
                raise ValueError("running_artifact_provenance client digests are invalid")
        for finding in self.findings:
            if finding.baseline_scope is BaselineScope.BINDING and self.binding_commit is None:
                raise ValueError("binding_commit is required for a binding-scoped finding")
            if finding.baseline_scope is BaselineScope.BINDING and any(
                evidence.baseline_scope is not BaselineScope.BINDING for evidence in finding.evidence
            ):
                raise ValueError("binding evidence lineage must contain only binding-scoped evidence")
            if self.binding_commit is not None and finding.baseline_scope in {BaselineScope.OVERLAY, BaselineScope.BOTH_DIVERGENT} and finding.classification not in {Classification.PROVISIONAL_OVERLAY, Classification.NOT_PRESENT, Classification.SUPERSEDED}:
                raise ValueError("binding finding cannot be justified by overlay-only evidence")
            if any(evidence.baseline_scope is not finding.baseline_scope for evidence in finding.evidence):
                raise ValueError("finding evidence scope must preserve finding lineage")
        for record in self.evidence_records:
            if record.baseline_anchor_commit != self.merged_commit or record.overlay_commit != self.overlay_commit:
                raise ValueError("evidence record commit identities must match the artifact")
            if record.binding_commit != self.binding_commit:
                raise ValueError("evidence record binding identity must match the artifact")
            if record.baseline_scope is BaselineScope.BINDING and self.binding_commit is None:
                raise ValueError("binding-scoped evidence record requires a global binding commit")
            if record.hypothesis_id == "H4" and (
                record.baseline_scope is not BaselineScope.BOTH_ALIGNED or record.binding_commit is not None
            ):
                raise ValueError("H4 is both-aligned with no binding commit")
            if record.hypothesis_id == "H4" and record.schedule_observations.derived_seed_anchor_commit != self.merged_commit:
                raise ValueError("H4 derived seed anchor must match artifact merged_commit")
            if record.hypothesis_id == "H3":
                if (
                    record.baseline_scope is not BaselineScope.BOTH_ALIGNED
                    or record.binding_commit is not None
                    or record.schedule_observations.derived_seed_anchor_commit != self.merged_commit
                ):
                    raise ValueError("H3 is both-aligned, unbound, and anchored to merged_commit")
                if self.discovered_multipliers["cancellation_points"] != record.cancellation_point_count:
                    raise ValueError("global N_cancellation_points disagrees with H3 inventory")
                if (
                    self.computed_run_cost["cancellation_schedules"]
                    != record.schedule_observations.derived_race_schedule_count
                    or self.computed_run_cost["cancellation_control_schedules"]
                    != record.schedule_observations.derived_control_schedule_count
                ):
                    raise ValueError("global cancellation cost disagrees with H3 derived schedules")
            if record.hypothesis_id == "H5":
                if record.baseline_scope is not BaselineScope.BOTH_DIVERGENT or record.binding_commit is not None:
                    raise ValueError("H5 is both-divergent and unbound")
                if self.discovered_multipliers["close_paths"] != record.close_path_count:
                    raise ValueError("global N_close_paths disagrees with H5 inventory")
                if self.computed_run_cost["idempotent_close_invocations"] != record.close_path_count * 3 * 5:
                    raise ValueError("global close cost disagrees with H5 derived schedules")
            if record.hypothesis_id == "H8":
                if record.baseline_scope is not BaselineScope.MERGED or record.binding_commit is not None:
                    raise ValueError("H8 is merged and unbound")
                if self.discovered_multipliers["sinks"] != record.inventory.sink_count:
                    raise ValueError("global N_sinks disagrees with H8 inventory")
                if self.computed_run_cost["sink_failure_runs"] != record.inventory.sink_count * 100:
                    raise ValueError("global sink cost disagrees with H8 derived schedules")
            if record.reviewer_status is ReviewerStatus.PENDING_G2 and self.gate_status is not GateStatus.INCOMPLETE:
                raise ValueError("pending external review requires an incomplete global gate")
        expected_scope_outs: set[tuple[object, ...]] = set()
        for record in self.evidence_records:
            summary = getattr(record, "schedule_observations", None)
            for assessment in getattr(summary, "coverage_assessments", ()):
                if assessment.status is CoverageAssessmentStatus.SCOPED_OUT:
                    expected_scope_outs.add((
                        record.hypothesis_id,
                        assessment.field_name,
                        assessment.next_gate,
                        assessment.missing_values,
                        assessment.owner,
                    ))
        assert self.scope_out_register is not None
        actual_scope_outs = {
            (
                entry.hypothesis_id,
                entry.field_name,
                entry.owning_gate,
                entry.missing_values,
                entry.owner,
            )
            for entry in self.scope_out_register
        }
        if len(actual_scope_outs) != len(self.scope_out_register) or actual_scope_outs != expected_scope_outs:
            raise ValueError("scope-out register must contain exactly one entry per scoped-out assessment")
        if self.gate_status is not GateStatus.INCOMPLETE and self.unclassified_finding_count:
            raise ValueError("UNCLASSIFIED findings must be zero at a passing gate")

    @property
    def finding_counts_by_classification(self) -> dict[str, int]:
        counts = Counter(finding.classification.value for finding in self.findings)
        return {classification.value: counts[classification.value] for classification in Classification}

    @property
    def unclassified_finding_count(self) -> int:
        return self.finding_counts_by_classification[Classification.UNCLASSIFIED.value]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "merged_commit": self.merged_commit,
            "overlay_commit": self.overlay_commit,
            "binding_commit": self.binding_commit,
            "baseline_reconciliation_status": self.baseline_reconciliation_status,
            "running_artifact_provenance": None if self.running_artifact_provenance is None else _canonical(self.running_artifact_provenance),
            "static_audit_status": self.static_audit_status.value,
            "runtime_characterization_status": self.runtime_characterization_status.value,
            "live_redis_status": self.live_redis_status.value,
            "acpx_status": self.acpx_status.value,
            "additional_client_status": self.additional_client_status.value,
            "zed_status": self.zed_status.value,
            "live_interoperability_status": self.live_interoperability_status.value,
            "unclassified_finding_count": self.unclassified_finding_count,
            "finding_counts_by_classification": self.finding_counts_by_classification,
            "findings": [finding.to_dict() for finding in sorted(self.findings, key=lambda item: item.finding_id)],
            "discovered_multipliers": _canonical(self.discovered_multipliers),
            "computed_run_cost": _canonical(self.computed_run_cost),
            "gate_status": self.gate_status.value,
            "evidence_records": [
                record.to_dict() for record in sorted(self.evidence_records, key=lambda item: item.hypothesis_id)
            ],
            "scope_out_register": [
                entry.to_dict()
                for entry in sorted(
                    self.scope_out_register or (),
                    key=lambda item: (item.hypothesis_id, item.field_name),
                )
            ],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AuditArtifact:
        payload = _json_object(payload, "artifact")
        expected = {
            "schema_version", "merged_commit", "overlay_commit", "binding_commit", "baseline_reconciliation_status",
            "running_artifact_provenance", "static_audit_status", "runtime_characterization_status", "live_redis_status",
            "acpx_status", "additional_client_status", "zed_status", "live_interoperability_status",
            "unclassified_finding_count", "finding_counts_by_classification", "findings", "discovered_multipliers",
            "computed_run_cost", "gate_status", "evidence_records", "scope_out_register",
        }
        if set(payload) != expected:
            raise ValueError("artifact fields do not match the canonical schema")
        counts = payload["finding_counts_by_classification"]
        if (
            not _nonnegative_integer(payload["unclassified_finding_count"])
            or not isinstance(counts, dict)
            or set(counts) != {classification.value for classification in Classification}
            or any(not _nonnegative_integer(value) for value in counts.values())
        ):
            raise ValueError("finding counts must be closed nonnegative integer records")
        findings = _json_array(payload["findings"], "findings")
        evidence_records = _json_array(payload["evidence_records"], "evidence records")
        scope_out_register = _json_array(payload["scope_out_register"], "scope-out register")
        _json_object(payload["discovered_multipliers"], "discovered_multipliers")
        _json_object(payload["computed_run_cost"], "computed_run_cost")
        if payload["running_artifact_provenance"] is not None:
            _json_object(payload["running_artifact_provenance"], "running_artifact_provenance")
        parsed_records: list[Any] = []
        for item in evidence_records:
            if isinstance(item, dict) and item.get("hypothesis_id") == "H3":
                from .cancellation import CancellationEvidenceRecord

                parsed_records.append(CancellationEvidenceRecord.from_dict(item))
            elif isinstance(item, dict) and item.get("hypothesis_id") == "H5":
                from .shutdown import ShutdownEvidenceRecord

                parsed_records.append(ShutdownEvidenceRecord.from_dict(item))
            elif isinstance(item, dict) and item.get("hypothesis_id") == "H6":
                from .semantic_errors import AuthorityEvidenceRecord

                parsed_records.append(AuthorityEvidenceRecord.from_dict(item))
            elif isinstance(item, dict) and item.get("hypothesis_id") == "H7":
                from .semantic_errors import SemanticEvidenceRecord

                parsed_records.append(SemanticEvidenceRecord.from_dict(item))
            elif isinstance(item, dict) and item.get("hypothesis_id") == "H8":
                from .telemetry import TelemetryEvidenceRecord

                parsed_records.append(TelemetryEvidenceRecord.from_dict(item))
            else:
                parsed_records.append(EvidenceRecord.from_dict(item))
        artifact = cls(
            schema_version=payload["schema_version"], merged_commit=payload["merged_commit"], overlay_commit=payload["overlay_commit"],
            binding_commit=payload["binding_commit"], baseline_reconciliation_status=payload["baseline_reconciliation_status"],
            running_artifact_provenance=payload["running_artifact_provenance"], static_audit_status=payload["static_audit_status"],
            runtime_characterization_status=payload["runtime_characterization_status"], live_redis_status=payload["live_redis_status"],
            acpx_status=payload["acpx_status"], additional_client_status=payload["additional_client_status"], zed_status=payload["zed_status"],
            live_interoperability_status=payload["live_interoperability_status"], findings=tuple(Finding.from_dict(item) for item in findings),
            discovered_multipliers=payload["discovered_multipliers"], computed_run_cost=payload["computed_run_cost"], gate_status=payload["gate_status"],
            evidence_records=tuple(parsed_records),
            scope_out_register=tuple(ScopeOutRegisterEntry.from_dict(item) for item in scope_out_register),
        )
        if payload["unclassified_finding_count"] != artifact.unclassified_finding_count:
            raise ValueError("unclassified_finding_count mismatch")
        if payload["finding_counts_by_classification"] != artifact.finding_counts_by_classification:
            raise ValueError("finding_counts_by_classification mismatch")
        return artifact
