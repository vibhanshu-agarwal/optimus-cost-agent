"""Neutral, immutable Context Engine contracts (Plan 12.2 Task 6; design spec 5; Task 1 contracts 2).

Only exact `str`/`int`/`bool`, tuples and frozen dataclasses cross this boundary; a host enum, which
is a `str` subclass, is refused. Protected host facts (outcome, effect state, approval facts) arrive
as exact opaque strings the engine never interprets. Records validate themselves on construction: a
malformed snapshot is a `ContractError`, never an unavailable view.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, fields
from itertools import pairwise
from typing import Protocol

STRATEGIES = ("compaction", "hybrid", "sliding_window")
SUMMARIZING_STRATEGIES = ("compaction", "hybrid")

_DIGEST = re.compile(r"[0-9a-f]{64}")
_TURN_DOMAIN = b"context-engine/turn-source/v1\x00"
_HISTORY_DOMAIN = b"context-engine/history/v1\x00"
_PARAMETERS_DOMAIN = "context-engine/strategy-parameters/v1"


class ContractError(ValueError):
    """A record outside the engine contract: a validation failure, not an unavailable view."""


def _int(owner: str, name: str, value: object, *, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ContractError(f"{owner}.{name} must be an int >= {minimum}")


def _text(owner: str, name: str, value: object, *, nonempty: bool = False) -> None:
    if type(value) is not str:
        raise ContractError(f"{owner}.{name} must be a plain str")
    if nonempty and not value:
        raise ContractError(f"{owner}.{name} must not be empty")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ContractError(f"{owner}.{name} is not encodable as UTF-8") from exc


def _digest(owner: str, name: str, value: object) -> None:
    if type(value) is not str or not _DIGEST.fullmatch(value):
        raise ContractError(f"{owner}.{name} must be a lowercase SHA-256 hex digest")


def _ids(owner: str, name: str, value: object, *, nonempty: bool = False) -> None:
    if type(value) is not tuple:
        raise ContractError(f"{owner}.{name} must be a tuple")
    for item in value:
        _int(owner, name, item, minimum=1)
    if any(b <= a for a, b in pairwise(value)):
        raise ContractError(f"{owner}.{name} must be strictly increasing")
    if nonempty and not value:
        raise ContractError(f"{owner}.{name} must not be empty")


def _frame(*parts: bytes) -> bytes:
    """Length-prefixed fields, so no boundary between adjacent fields is ambiguous."""
    return b"".join(len(part).to_bytes(8, "big") + part for part in parts)


@dataclass(frozen=True, slots=True)
class HistoryRevision:
    """The committed history a snapshot was taken from: opaque session key, committed generation,
    last committed turn and the digest of its sanitized content (`history_digest`)."""

    session_key: str
    generation: int
    last_committed_seq: int
    digest: str

    def __post_init__(self) -> None:
        _text("HistoryRevision", "session_key", self.session_key, nonempty=True)
        _int("HistoryRevision", "generation", self.generation)
        _int("HistoryRevision", "last_committed_seq", self.last_committed_seq)
        _digest("HistoryRevision", "digest", self.digest)


@dataclass(frozen=True, slots=True)
class OrdinaryTurn:
    """A complete committed turn's sanitized ordinary text. Untrusted data, never authority."""

    seq: int
    user_prompt: str
    plan_text: str
    completion_text: str

    def __post_init__(self) -> None:
        _int("OrdinaryTurn", "seq", self.seq, minimum=1)
        for name in ("user_prompt", "plan_text", "completion_text"):
            _text("OrdinaryTurn", name, getattr(self, name))


@dataclass(frozen=True, slots=True)
class ProtectedTurnState:
    """One committed turn's exact host authority: outcome, effect state and host-issued approval
    facts, each an exact host-rendered string. Never summarized, never omitted."""

    seq: int
    outcome: str
    effect_state: str
    approval_facts: tuple[str, ...]

    def __post_init__(self) -> None:
        _int("ProtectedTurnState", "seq", self.seq, minimum=1)
        _text("ProtectedTurnState", "outcome", self.outcome, nonempty=True)
        _text("ProtectedTurnState", "effect_state", self.effect_state, nonempty=True)
        if type(self.approval_facts) is not tuple:
            raise ContractError("ProtectedTurnState.approval_facts must be a tuple")
        for fact in self.approval_facts:
            _text("ProtectedTurnState", "approval_facts", fact, nonempty=True)


def turn_source_digest(turn: OrdinaryTurn) -> str:
    """The identity of one turn's ordinary source, which a checkpoint's coverage is bound to."""
    parts = (str(turn.seq), turn.user_prompt, turn.plan_text, turn.completion_text)
    return hashlib.sha256(_TURN_DOMAIN + _frame(*(part.encode("utf-8") for part in parts))).hexdigest()


def history_digest(turns: tuple[OrdinaryTurn, ...], protected: tuple[ProtectedTurnState, ...]) -> str:
    """The digest of a sanitized snapshot's ordinary and protected content. A separate domain from
    the host's storage serializer and from any plan approval hash."""
    digest = hashlib.sha256(_HISTORY_DOMAIN)
    digest.update(len(turns).to_bytes(8, "big"))
    for turn, state in zip(turns, protected, strict=True):
        facts = (str(len(state.approval_facts)), *state.approval_facts)
        digest.update(
            _frame(
                turn_source_digest(turn).encode("ascii"),
                str(state.seq).encode("ascii"),
                state.outcome.encode("utf-8"),
                state.effect_state.encode("utf-8"),
                _frame(*(fact.encode("utf-8") for fact in facts)),
            )
        )
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class HistorySnapshot:
    """A frozen committed history: ordinary turns and exactly one protected record per turn, with the
    same complete IDs in the same order. No provisional current prompt belongs here."""

    revision: HistoryRevision
    turns: tuple[OrdinaryTurn, ...]
    protected: tuple[ProtectedTurnState, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.revision, HistoryRevision):
            raise ContractError("HistorySnapshot.revision must be a HistoryRevision")
        if type(self.turns) is not tuple or not all(isinstance(t, OrdinaryTurn) for t in self.turns):
            raise ContractError("HistorySnapshot.turns must be a tuple of OrdinaryTurn")
        if type(self.protected) is not tuple or not all(isinstance(p, ProtectedTurnState) for p in self.protected):
            raise ContractError("HistorySnapshot.protected must be a tuple of ProtectedTurnState")
        ids = tuple(turn.seq for turn in self.turns)
        _ids("HistorySnapshot", "turn ids", ids)
        if tuple(state.seq for state in self.protected) != ids:
            raise ContractError("HistorySnapshot needs exactly one protected record per committed turn")
        if self.revision.last_committed_seq != (ids[-1] if ids else 0):
            raise ContractError("HistorySnapshot.revision.last_committed_seq does not match the turns")
        if self.revision.digest != history_digest(self.turns, self.protected):
            raise ContractError("HistorySnapshot.revision.digest does not match the content")

    @property
    def ids(self) -> tuple[int, ...]:
        return tuple(turn.seq for turn in self.turns)


@dataclass(frozen=True, slots=True)
class StrategyParameters:
    """Explicit strategy allocations and maintenance allowance. Values are supplied by reviewed policy
    (D1/D2) or by tests; none is a shipped default."""

    anchor_input_tokens: int
    compaction_tail_input_tokens: int
    hybrid_tail_input_tokens: int
    summary_output_tokens: int
    max_maintenance_calls: int
    prompt_version: str
    format_version: str

    def __post_init__(self) -> None:
        for name in ("anchor_input_tokens", "compaction_tail_input_tokens", "hybrid_tail_input_tokens", "max_maintenance_calls"):
            _int("StrategyParameters", name, getattr(self, name))
        _int("StrategyParameters", "summary_output_tokens", self.summary_output_tokens, minimum=1)
        _text("StrategyParameters", "prompt_version", self.prompt_version, nonempty=True)
        _text("StrategyParameters", "format_version", self.format_version, nonempty=True)

    @property
    def digest(self) -> str:
        values = {field.name: getattr(self, field.name) for field in fields(self)}
        canonical = json.dumps({"domain": _PARAMETERS_DOMAIN, **values}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ViewLimits:
    """Finite bounds for one view, and the host's verified history estimator.

    `summary_max_bytes` bounds the UTF-8 length of a complete sanitized summary, fresh or reused, beside
    its token bound: a token bound is not a byte bound, and every maintenance input must fit both
    `maintenance_input_tokens` and `transient_max_bytes` (Codex's final corrections C2). The host derives
    it from its verified estimator, `floor(S / r)` for a `ceil(r * UTF-8 bytes)` profile and summary
    token cap `S`, so the byte bound never rejects a summary the token bound admits.

    `estimate_history` must be subadditive over the complete strings given to the engine:
    `estimate_history(a + b) <= estimate_history(a) + estimate_history(b)`. The engine relies on it to
    count a maintenance input as the sum of its pieces; a `ceil(r * UTF-8 bytes)` profile with
    non-negative overhead satisfies it. Each assembled input is still checked before its call."""

    history_input_tokens: int
    source_max_bytes: int
    transient_max_bytes: int
    maintenance_input_tokens: int
    maintenance_output_tokens: int
    summary_max_bytes: int
    estimate_history: Callable[[str], int]
    estimator_id: str

    def __post_init__(self) -> None:
        for name in ("history_input_tokens", "source_max_bytes", "transient_max_bytes", "maintenance_input_tokens", "maintenance_output_tokens"):
            _int("ViewLimits", name, getattr(self, name))
        _int("ViewLimits", "summary_max_bytes", self.summary_max_bytes, minimum=1)
        if self.summary_max_bytes >= self.transient_max_bytes:
            raise ContractError("ViewLimits.summary_max_bytes must be below transient_max_bytes")
        if not callable(self.estimate_history):
            raise ContractError("ViewLimits.estimate_history must be callable")
        _text("ViewLimits", "estimator_id", self.estimator_id, nonempty=True)


@dataclass(frozen=True, slots=True)
class MaintenanceRequest:
    """One summarization call: complete sanitized input, host-computed coverage. The model cannot
    supply coverage metadata."""

    input_text: str
    covered_turn_ids: tuple[int, ...]
    max_output_tokens: int
    prompt_version: str
    format_version: str

    def __post_init__(self) -> None:
        _text("MaintenanceRequest", "input_text", self.input_text, nonempty=True)
        _ids("MaintenanceRequest", "covered_turn_ids", self.covered_turn_ids, nonempty=True)
        _int("MaintenanceRequest", "max_output_tokens", self.max_output_tokens, minimum=1)
        _text("MaintenanceRequest", "prompt_version", self.prompt_version, nonempty=True)
        _text("MaintenanceRequest", "format_version", self.format_version, nonempty=True)


@dataclass(frozen=True, slots=True)
class MaintenanceResult:
    """What a maintenance call returned. Money stays in the host's receipts; `attempt_ids` correlate."""

    summary_text: str | None
    attempt_ids: tuple[str, ...]
    status: str
    finish_status: str | None

    def __post_init__(self) -> None:
        if self.summary_text is not None:
            _text("MaintenanceResult", "summary_text", self.summary_text)
        if type(self.attempt_ids) is not tuple:
            raise ContractError("MaintenanceResult.attempt_ids must be a tuple")
        for attempt in self.attempt_ids:
            _text("MaintenanceResult", "attempt_ids", attempt, nonempty=True)
        _text("MaintenanceResult", "status", self.status, nonempty=True)
        if self.finish_status is not None:
            _text("MaintenanceResult", "finish_status", self.finish_status, nonempty=True)


class MaintenanceCallback(Protocol):
    """Synchronous, invoked off the ACP event loop. The host owns accounting and cancellation."""

    def __call__(self, request: MaintenanceRequest) -> MaintenanceResult: ...


@dataclass(frozen=True, slots=True)
class SummaryCheckpoint:
    """A derived, revision-bound summary of complete turns. Coverage and digests are host-computed;
    the summary text is sanitized, inert and untrusted."""

    revision: HistoryRevision
    covered_turn_ids: tuple[int, ...]
    source_digests: tuple[str, ...]
    strategy: str
    parameters_digest: str
    format_version: str
    summary_text: str

    def __post_init__(self) -> None:
        if not isinstance(self.revision, HistoryRevision):
            raise ContractError("SummaryCheckpoint.revision must be a HistoryRevision")
        _ids("SummaryCheckpoint", "covered_turn_ids", self.covered_turn_ids, nonempty=True)
        if type(self.source_digests) is not tuple or len(self.source_digests) != len(self.covered_turn_ids):
            raise ContractError("SummaryCheckpoint needs one source digest per covered turn")
        for digest in self.source_digests:
            _digest("SummaryCheckpoint", "source_digests", digest)
        if type(self.strategy) is not str or self.strategy not in SUMMARIZING_STRATEGIES:
            raise ContractError("SummaryCheckpoint.strategy must be a summarizing strategy")
        _digest("SummaryCheckpoint", "parameters_digest", self.parameters_digest)
        _text("SummaryCheckpoint", "format_version", self.format_version, nonempty=True)
        _text("SummaryCheckpoint", "summary_text", self.summary_text, nonempty=True)


@dataclass(frozen=True, slots=True)
class PreparedView:
    """The engine's chosen view: exact head/tail turns, an optional summary covering others, turns
    omitted from model context, and every protected record. The four partitions never overlap."""

    head_turn_ids: tuple[int, ...]
    tail_turn_ids: tuple[int, ...]
    checkpoint: SummaryCheckpoint | None
    protected: tuple[ProtectedTurnState, ...]
    covered_turn_ids: tuple[int, ...]
    omitted_turn_ids: tuple[int, ...]
    available: bool
    reason: str | None

    def __post_init__(self) -> None:
        partitions = {
            "head": self.head_turn_ids,
            "tail": self.tail_turn_ids,
            "covered": self.covered_turn_ids,
            "omitted": self.omitted_turn_ids,
        }
        for name, ids in partitions.items():
            _ids("PreparedView", f"{name}_turn_ids", ids)
        seen: set[int] = set()
        for ids in partitions.values():
            if seen & set(ids):
                raise ContractError("PreparedView partitions overlap")
            seen |= set(ids)
        if self.checkpoint is not None and not isinstance(self.checkpoint, SummaryCheckpoint):
            raise ContractError("PreparedView.checkpoint must be a SummaryCheckpoint")
        covered_by_checkpoint = self.checkpoint.covered_turn_ids if self.checkpoint is not None else ()
        if covered_by_checkpoint != self.covered_turn_ids:
            raise ContractError("PreparedView.covered_turn_ids must be exactly its checkpoint's coverage")
        if type(self.protected) is not tuple or not all(isinstance(p, ProtectedTurnState) for p in self.protected):
            raise ContractError("PreparedView.protected must be a tuple of ProtectedTurnState")
        if type(self.available) is not bool:
            raise ContractError("PreparedView.available must be a bool")
        if not self.available and not self.reason:
            raise ContractError("an unavailable PreparedView must state its reason")
        if self.reason is not None:
            _text("PreparedView", "reason", self.reason, nonempty=True)
