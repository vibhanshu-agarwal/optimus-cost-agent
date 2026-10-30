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
Trust = Literal["user-authored", "agent-derived", "legacy-import"]  # origin class; switching off never erases it
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


class ExpectedSavings(_Record):
    """The savings claim the report must make, computed by the case author from the declared reference."""

    label: Literal["estimated", "measured"]
    basis: Literal["same_tokens_repriced", "matched_run"]
    amount_usd: Decimal
    reference_price_snapshot_id: Id


class ExpectedCost(_Record):
    known_usd: Decimal
    complete: bool | None
    savings: ExpectedSavings | None  # None: the report must carry no savings claim


class ExpectedMemory(_Record):
    """One version of a memory item in its final state; ``absent`` means no version may exist at all.

    ``off`` is the switch state and keeps the origin in ``trust``; ``supersedes`` names the
    version of the same key that this one replaced, so supersession keeps its history.
    """

    key: Id
    project_id: Id
    version: int | None = Field(ge=1)
    trust: Trust | Literal["absent"]
    status: MemoryStatus | None
    off: bool
    supersedes: int | None = Field(ge=1)

    @model_validator(mode="after")
    def _absent_has_no_state(self) -> ExpectedMemory:
        absent = self.trust == "absent"
        if absent != (self.status is None) or absent != (self.version is None) or (absent and (self.off or self.supersedes)):
            raise ValueError("an absent item has no version, status, switch state or supersession; a present one has version and status")
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


class RouteProvenance(_Record):
    """Which route supplied one receipt, as the Gateway reported it; every unreported fact stays null."""

    attempt_id: Id
    provider: str | None
    requested_model: str | None
    resolved_provider: str | None
    resolved_model: str | None
    model_version: str | None
    cache_hit: bool | None
    billing_units: int | None = Field(ge=0)


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
    expected_rank: tuple[Id, ...]  # memory keys in their required relative order within served_memory
    expected_cost: ExpectedCost | None
    verification: str = Field(min_length=1)
    provenance: Provenance

    @model_validator(mode="after")
    def _ordered_unique(self) -> GoldenCase:
        seqs = [item.seq for item in self.inputs]
        if seqs != sorted(set(seqs)):
            raise ValueError("input seq values must be strictly increasing")
        keys = [(item.key, item.project_id, item.version) for item in self.expected_memory]
        if len(keys) != len(set(keys)):
            raise ValueError("expected_memory repeats a key version")
        if len(self.expected_rank) != len(set(self.expected_rank)):
            raise ValueError("expected_rank repeats a key")
        if set(self.required_facts) & set(self.prohibited_claims) or set(self.required_events) & set(self.prohibited_events):
            raise ValueError("an id is both required and prohibited")
        if self.expected_action == "abstain" and self.required_facts:
            raise ValueError("an abstention cannot require facts")
        asserts = (self.required_facts, self.required_evidence, self.prohibited_claims, self.required_events,
                   self.prohibited_events, self.expected_memory, self.expected_rank)
        if not any(asserts) and self.expected_cost is None and self.expected_action == "answer":
            raise ValueError("the case asserts nothing beyond answering")
        return self


class MemoryStateObservation(_Record):
    """One version of an item as the host's authoritative state reports it."""

    key: Id
    project_id: Id
    version: int = Field(ge=1)
    trust: Trust
    status: MemoryStatus
    off: bool
    supersedes: int | None = Field(ge=1)


class TraceEvent(_Record):
    """One host event. Memory events name the item version they concern; others leave those null."""

    seq: int = Field(ge=0)
    type: Id
    memory_key: Id | None
    project_id: Id | None
    version: int | None = Field(ge=1)  # an item version, or a key generation for rotation events
    rotation_id: Id | None  # rotation events name their rotation; others leave it null


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
    """One served item in rank order; ``memory_id`` is the item key used in ``memory_state``."""

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
    support_extracted: bool  # an extractor or judge produced supported_by; False leaves citation support undecided
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
    provenance: tuple[RouteProvenance, ...]  # exactly one per distinct receipt identity
    reported_cost: ReportedCost
    coverage_complete: bool | None
    missing_coverage: tuple[str, ...]
    timing_ms: int | None = Field(ge=0)

    @model_validator(mode="after")
    def _one_state_per_memory(self) -> ObservedTrace:
        keys = [(item.key, item.project_id, item.version) for item in self.memory_state]
        if len(keys) != len(set(keys)):
            raise ValueError("memory_state repeats a key version")
        routes = [item.attempt_id for item in self.provenance]
        if len(routes) != len(set(routes)) or set(routes) != {attempt.attempt_id for attempt in self.attempts}:
            raise ValueError("provenance needs exactly one record per receipt identity")
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
    provenance: tuple[RouteProvenance, ...]


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
