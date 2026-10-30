"""Versioned records for Plan 12.5 golden cases, observed traces and verdicts.

Every record is frozen and rejects unknown fields. Authority and coverage fields have no
defaults: a fixture or trace that omits them is rejected rather than read optimistically.
A nullable field (for example ``coverage_complete``) must still be present, so "unknown"
is always an explicit statement.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, model_validator


def _no_parent_segment(value: str) -> str:
    if ".." in value:
        raise ValueError("an id never contains '..'")
    return value


# Repository paths are allowed ("path:src/x.py"), but never "..".
Id = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$"), AfterValidator(_no_parent_segment)]
Status = Literal["PASS", "FAIL", "INCONCLUSIVE", "UNRUN"]
Layer = Literal["authority", "retrieval", "answer", "cost"]
Oracle = Literal["K1", "K2", "K3", "K4", "K5", "K6"]
Trust = Literal["user-authored", "agent-derived", "legacy-import", "off"]
MemoryStatus = Literal["active", "reverify", "conflicted", "superseded", "withdrawn", "purged", "archived"]


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
    savings_usd: Decimal | None  # None: the report must carry no savings figure


class ExpectedMemory(_Record):
    """The memory item's final state; ``absent`` means it must not exist at all."""

    key: Id
    project_id: Id
    trust: Trust | Literal["absent"]
    status: MemoryStatus | None

    @model_validator(mode="after")
    def _absent_has_no_status(self) -> ExpectedMemory:
        if (self.trust == "absent") != (self.status is None):
            raise ValueError("status is null exactly when trust is absent")
        return self


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


class CaseInput(_Record):
    """One ordered input: synthetic text, or a receipt the accounting path ingests."""

    seq: int = Field(ge=0)
    actor: Literal["user", "assistant", "tool", "import", "host", "gateway", "clock"]
    text: str | None = Field(min_length=1)
    attempt: AttemptReceipt | None

    @model_validator(mode="after")
    def _one_payload(self) -> CaseInput:
        if (self.text is None) == (self.attempt is None):
            raise ValueError("exactly one of text and attempt")
        return self


class GoldenCase(_Record):
    """One versioned case. Source-dependent gold is pointers and IDs, never source bodies.

    A ``control`` exercises the allowed path, so a ``probe`` that is refused proves denial
    rather than a system that refuses everything.
    """

    schema_id: Literal["plan12-memory-case/1"] = Field(alias="schema")
    case_id: Id
    version: int = Field(ge=1)
    family: Id
    split: Literal["train", "development", "held_out"]
    kind: Literal["lifecycle", "localization", "accounting"]
    role: Literal["probe", "control"]
    oracles: tuple[Oracle, ...] = Field(min_length=1)
    inputs: tuple[CaseInput, ...] = Field(min_length=1)
    project_id: Id
    snapshot: Id
    cutoff: AwareDatetime
    expected_action: Literal["answer", "abstain"]
    required_facts: tuple[Id, ...]
    required_evidence: tuple[EvidenceRequirement, ...]
    prohibited_claims: tuple[Id, ...]
    required_events: tuple[Id, ...]
    prohibited_events: tuple[Id, ...]
    expected_memory: tuple[ExpectedMemory, ...]
    expected_cost: ExpectedCost | None
    verification: str = Field(min_length=1)
    provenance: Provenance

    @model_validator(mode="after")
    def _ordered_unique(self) -> GoldenCase:
        seqs = [item.seq for item in self.inputs]
        if seqs != sorted(set(seqs)):
            raise ValueError("input seq values must be strictly increasing")
        keys = [(item.key, item.project_id) for item in self.expected_memory]
        if len(keys) != len(set(keys)):
            raise ValueError("expected_memory repeats a key")
        if set(self.required_facts) & set(self.prohibited_claims) or set(self.required_events) & set(self.prohibited_events):
            raise ValueError("an id is both required and prohibited")
        if self.expected_action == "abstain" and self.required_facts:
            raise ValueError("an abstention cannot require facts")
        asserts = (self.required_facts, self.required_evidence, self.prohibited_claims, self.required_events,
                   self.prohibited_events, self.expected_memory)
        if not any(asserts) and self.expected_cost is None and self.expected_action == "answer":
            raise ValueError("the case asserts nothing beyond answering")
        return self


class MemoryStateObservation(_Record):
    key: Id
    project_id: Id
    trust: Trust
    status: MemoryStatus


class TraceEvent(_Record):
    seq: int = Field(ge=0)
    type: Id


class ObservedEvidence(_Record):
    """One retrieved item, in rank order within the trace.

    ``observed_at`` is when the item was current inside the case's world (its revision's commit
    time, or a synthetic memory's write time), never the clock time a run read it.
    """

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
    """Structured answer facts. ``claims`` and ``supported_by`` come from a deterministic extractor or
    a judge, never from the system under test describing its own answer."""

    action: Literal["answer", "abstain"]
    claims: tuple[Id, ...]
    supported_by: tuple[MemoryCitation, ...]
    citations: tuple[MemoryCitation, ...]
    judge_status: Literal["ok", "error", "uncertain"]


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
    memory_state: tuple[MemoryStateObservation, ...]
    answer: AnswerObservation
    attempts: tuple[AttemptReceipt, ...]
    reported_cost: ReportedCost
    coverage_complete: bool | None
    missing_coverage: tuple[str, ...]
    timing_ms: int | None = Field(ge=0)

    @model_validator(mode="after")
    def _one_state_per_memory(self) -> ObservedTrace:
        keys = [(item.key, item.project_id) for item in self.memory_state]
        if len(keys) != len(set(keys)):
            raise ValueError("memory_state repeats a key")
        return self


class GatewayRoute(_Record):
    """One arm-D route: an exact registry model ID (a run input), the bound snapshot and its output cap."""

    model_id: str = Field(min_length=1)
    registry_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_cap: int = Field(ge=1)


class GatewayReply(_Record):
    """One Gateway reply as the harness sees it: text on success, an error code otherwise, and receipts."""

    status: int
    content: str | None
    finish_reason: str | None
    error_code: str | None
    attempts: tuple[AttemptReceipt, ...]


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


class SplitManifest(_Record):
    """The versioned family-to-split assignment that every fixture case must match."""

    schema_id: Literal["plan12-memory-splits/1"] = Field(alias="schema")
    version: int = Field(ge=1)
    families: dict[Literal["train", "development", "held_out"], tuple[Id, ...]]
    expected_family_counts: dict[Literal["lifecycle", "localization", "accounting"], int]
    chronological_kinds: tuple[Literal["lifecycle", "localization", "accounting"], ...]


class ValidationReport(_Record):
    files: tuple[str, ...]
    case_count: int
    kind_counts: tuple[tuple[str, int], ...]
    family_counts: tuple[tuple[str, int], ...]
    split_counts: tuple[tuple[str, int], ...]
    errors: tuple[str, ...]
