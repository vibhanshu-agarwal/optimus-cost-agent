"""Versioned records for Plan 12.5 golden cases, observed traces and verdicts.

Every record is frozen and rejects unknown fields. Authority and coverage fields have no
defaults: a fixture or trace that omits them is rejected rather than read optimistically.
A nullable field (for example ``coverage_complete``) must still be present, so "unknown"
is always an explicit statement.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Id = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")]
Status = Literal["PASS", "FAIL", "INCONCLUSIVE", "UNRUN"]
Layer = Literal["authority", "retrieval", "answer", "cost"]


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class EvidenceRequirement(_Record):
    requirement_id: Id
    any_of: tuple[Id, ...] = Field(min_length=1)


class Provenance(_Record):
    drafted_by: Id
    verified_by: Id | None
    source: str = Field(min_length=1)


class ExpectedCost(_Record):
    known_usd: Decimal
    complete: bool | None


class GoldenCase(_Record):
    """One versioned case. Source-dependent gold is pointers and IDs, never source bodies."""

    schema_id: Literal["plan12-memory-case/1"] = Field(alias="schema")
    case_id: Id
    version: int = Field(ge=1)
    family: Id
    split: Literal["train", "development", "held_out"]
    kind: Literal["lifecycle", "localization", "accounting"]
    input_ref: str = Field(min_length=1)
    project_id: Id
    snapshot: Id
    cutoff: AwareDatetime
    expected_action: Literal["answer", "abstain"]
    required_facts: tuple[Id, ...]
    required_evidence: tuple[EvidenceRequirement, ...]
    prohibited_claims: tuple[Id, ...]
    required_events: tuple[Id, ...]
    prohibited_events: tuple[Id, ...]
    expected_cost: ExpectedCost | None
    verification: str = Field(min_length=1)
    provenance: Provenance


class TraceEvent(_Record):
    seq: int = Field(ge=0)
    type: Id


class ObservedEvidence(_Record):
    evidence_id: Id
    project_id: Id
    revision: Id
    observed_at: AwareDatetime
    supports: tuple[Id, ...]


class MemoryRef(_Record):
    memory_id: Id
    version: int = Field(ge=1)
    project_id: Id


class MemoryCitation(_Record):
    memory_id: Id
    version: int = Field(ge=1)


class AnswerObservation(_Record):
    """Structured answer facts; ``claims`` come from a deterministic extractor or a judge."""

    action: Literal["answer", "abstain"]
    claims: tuple[Id, ...]
    supported_by: tuple[MemoryCitation, ...]
    citations: tuple[MemoryCitation, ...]
    judge_status: Literal["ok", "error", "uncertain"]


class AttemptReceipt(_Record):
    """One model attempt. Token categories are nullable and a null is never read as zero."""

    attempt_id: Id
    gateway_request_id: Id | None
    state: Literal["settled", "intent_only", "late"]
    input_tokens: int | None = Field(ge=0)
    output_tokens: int | None = Field(ge=0)
    cache_tokens: int | None = Field(ge=0)
    reasoning_tokens: int | None = Field(ge=0)
    price_snapshot_id: Id | None
    cost_usd: Decimal | None


class SavingsClaim(_Record):
    label: Literal["estimated", "measured"]
    basis: Literal["same_tokens_repriced", "matched_run"]
    amount_usd: Decimal
    reference_price_snapshot_id: Id | None
    counterfactual_tokens_inferred: bool


class ReportedCost(_Record):
    """What the system under test reported; graded against the receipts and any gold."""

    known_usd: Decimal
    complete: bool | None
    savings: SavingsClaim | None


class ObservedTrace(_Record):
    schema_id: Literal["plan12-memory-trace/1"] = Field(alias="schema")
    case_id: Id
    case_version: int = Field(ge=1)
    source_id: Id
    config_id: Id
    events: tuple[TraceEvent, ...]
    evidence: tuple[ObservedEvidence, ...]
    served_memory: tuple[MemoryRef, ...]
    answer: AnswerObservation
    attempts: tuple[AttemptReceipt, ...]
    reported_cost: ReportedCost
    coverage_complete: bool | None
    missing_coverage: tuple[str, ...]
    timing_ms: int | None = Field(ge=0)


class LayerVerdict(_Record):
    status: Status
    reasons: tuple[str, ...]


class Measurements(_Record):
    known_cost_usd: Decimal
    cost_complete: bool
    savings_usd: Decimal | None
    timing_ms: int | None
    retrieval_recall: Decimal | None
    retrieval_precision: Decimal | None


class CaseVerdict(_Record):
    """Execution result for one case. Fixture validity is reported separately by ``validate_cases``."""

    case_id: Id
    case_version: int
    execution_status: Status
    layers: dict[Layer, LayerVerdict]
    reasons: tuple[str, ...]
    evidence_ids: tuple[Id, ...]
    measurements: Measurements | None


class ValidationReport(_Record):
    files: tuple[str, ...]
    case_count: int
    kind_counts: tuple[tuple[str, int], ...]
    split_counts: tuple[tuple[str, int], ...]
    errors: tuple[str, ...]
