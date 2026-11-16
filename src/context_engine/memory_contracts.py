"""Neutral, immutable memory contracts (Plan 12.11 Task 1; design spec v4 §4-§5).

Trust and status are independent (§4): trust is who vouches for an item, status is where it stands. Only the Gate commits, so
these records describe what the host asserts and what the store confirmed; the engine never decides whether a save happened.
Every record validates itself on construction: a malformed one is a `ContractError`, never a degraded view. Unknown fields
cannot be expressed (frozen dataclasses), and every closed vocabulary is checked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from context_engine.contracts import ContractError

TRUST = ("user-authored", "agent-derived", "legacy-import", "off")
STATUS = ("active", "reverify", "conflicted", "superseded", "withdrawn", "purged")
USER_KINDS = ("fact", "preference", "decision", "constraint")
AGENT_KINDS = ("episode", "procedure", "lesson")  # always optional (§4)
KINDS = USER_KINDS + AGENT_KINDS
SPEECH_ACTS = ("assertion", "preference", "decision", "quotation", "question", "hypothetical", "retraction")
ADMITTING_ACTS = ("assertion", "preference", "decision")
ACTIONS = ("admit", "update", "withdraw", "tombstone", "off")
DURABLE_STATES = ("confirmed", "unconfirmed", "refused")
PROJECTION_STATES = ("current", "pending")

MAX_STATEMENT_CHARS = 2000
MAX_TITLE_CHARS = 120
_OPAQUE = re.compile(r"[A-Za-z0-9._:@/-]{1,128}")  # host-issued identities: project, scope, block, evidence, session, branch
_ITEM = re.compile(r"m-[0-9a-f]{16}")
_DIGEST = re.compile(r"[0-9a-f]{64}")


def _choice(owner: str, name: str, value: object, allowed: tuple[str, ...]) -> None:
    if type(value) is not str or value not in allowed:
        raise ContractError(f"{owner}.{name} must be one of {allowed}")


def _opaque(owner: str, name: str, value: object) -> None:
    if type(value) is not str or not _OPAQUE.fullmatch(value):
        raise ContractError(f"{owner}.{name} must be a host-issued identity")


def _item(owner: str, name: str, value: object) -> None:
    if type(value) is not str or not _ITEM.fullmatch(value):
        raise ContractError(f"{owner}.{name} must be a memory item id")


def _bounded(owner: str, name: str, value: object, limit: int) -> None:
    if type(value) is not str or len(value) > limit or any(ord(c) < 32 and c not in "\t" for c in value):
        raise ContractError(f"{owner}.{name} must be one line of at most {limit} characters")


def _count(owner: str, name: str, value: object, *, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ContractError(f"{owner}.{name} must be an int >= {minimum}")


def _tuple_of(owner: str, name: str, value: object, check: type) -> None:
    if type(value) is not tuple or not all(type(entry) is check for entry in value):
        raise ContractError(f"{owner}.{name} must be a tuple of {check.__name__}")


@dataclass(frozen=True)
class Span:
    """Where a user-origin statement came from: a host-issued raw user block and a character range in it."""

    block: str
    start: int
    end: int

    def __post_init__(self) -> None:
        _opaque("Span", "block", self.block)
        _count("Span", "start", self.start)
        _count("Span", "end", self.end, minimum=self.start + 1)


@dataclass(frozen=True)
class MemoryCandidate:
    """What extraction or a command proposes. It is not memory until the Gate admits it and the store confirms it."""

    project: str
    scope: str
    trust: str  # who would vouch: never "off" on the way in
    kind: str
    speech_act: str
    statement: str
    title: str
    spans: tuple[Span, ...] = ()  # user-authored: the exact supporting text
    evidence: tuple[str, ...] = ()  # agent-derived: host-issued evidence references
    target: str | None = None  # the item a retraction or update names
    idempotency_key: str = ""

    def __post_init__(self) -> None:
        owner = "MemoryCandidate"
        _opaque(owner, "project", self.project)
        _opaque(owner, "scope", self.scope)
        _choice(owner, "trust", self.trust, TRUST[:3])
        _choice(owner, "kind", self.kind, KINDS)
        _choice(owner, "speech_act", self.speech_act, SPEECH_ACTS)
        _bounded(owner, "statement", self.statement, MAX_STATEMENT_CHARS)
        _bounded(owner, "title", self.title, MAX_TITLE_CHARS)
        _tuple_of(owner, "spans", self.spans, Span)
        _tuple_of(owner, "evidence", self.evidence, str)
        for reference in self.evidence:
            _opaque(owner, "evidence", reference)
        if self.target is not None:
            _item(owner, "target", self.target)
        if type(self.idempotency_key) is not str or not _DIGEST.fullmatch(self.idempotency_key):
            raise ContractError(f"{owner}.idempotency_key must be a lowercase SHA-256 hex digest")


@dataclass(frozen=True)
class HostVerdict:
    """What the host established about a candidate before the Gate decides. The engine cannot check any of it itself."""

    workspace_trusted: bool
    scope_valid: bool
    spans_verified: bool  # every span is real raw user text and supports the statement
    lineage_complete: bool  # every transitive evidence dependency is host-issued and resolved
    scans_passed: bool  # injection, secret and B1 source-overlap checks

    def __post_init__(self) -> None:
        for name in ("workspace_trusted", "scope_valid", "spans_verified", "lineage_complete", "scans_passed"):
            if type(getattr(self, name)) is not bool:
                raise ContractError(f"HostVerdict.{name} must be a bool")


@dataclass(frozen=True)
class MemoryEvent:
    """One immutable, versioned change to one item: the only thing the store appends. `statement` is empty for an off record and
    after a tombstone, so neither carries a payload."""

    event_id: str
    project: str
    item: str
    version: int
    action: str
    trust: str
    status: str
    kind: str
    title: str
    statement: str

    def __post_init__(self) -> None:
        owner = "MemoryEvent"
        _opaque(owner, "event_id", self.event_id)
        _opaque(owner, "project", self.project)
        _item(owner, "item", self.item)
        _count(owner, "version", self.version, minimum=1)
        _choice(owner, "action", self.action, ACTIONS)
        _choice(owner, "trust", self.trust, TRUST)
        _choice(owner, "status", self.status, STATUS)
        _choice(owner, "kind", self.kind, KINDS)
        _bounded(owner, "title", self.title, MAX_TITLE_CHARS)
        _bounded(owner, "statement", self.statement, MAX_STATEMENT_CHARS)
        if self.trust == "off" and self.statement:
            raise ContractError("an off record carries no payload")
        if self.action in ("withdraw", "tombstone") and (self.statement or self.title):
            raise ContractError("a withdrawal or tombstone carries no payload; the history is in earlier events")
        if (self.action == "withdraw") != (self.status == "withdrawn") or (self.action == "tombstone") != (self.status == "purged"):
            raise ContractError("a withdrawal marks the item withdrawn and a tombstone marks it purged")
        if (self.action == "admit") != (self.version == 1) and self.action != "off":
            raise ContractError("only an item's first event admits it")


@dataclass(frozen=True)
class MemoryCommitResult:
    """What the store reports for one append. Only `confirmed` means the event is on disk."""

    event_id: str
    item: str
    version: int
    durable_state: str
    projection_state: str

    def __post_init__(self) -> None:
        _opaque("MemoryCommitResult", "event_id", self.event_id)
        _item("MemoryCommitResult", "item", self.item)
        _count("MemoryCommitResult", "version", self.version, minimum=1)
        _choice("MemoryCommitResult", "durable_state", self.durable_state, DURABLE_STATES)
        _choice("MemoryCommitResult", "projection_state", self.projection_state, PROJECTION_STATES)


@dataclass(frozen=True)
class MemoryNotice:
    """The host's notice of a commit (§5), built from a `MemoryCommitResult`, never from model prose."""

    event_id: str
    item: str
    version: int
    action: str
    durable_state: str
    projection_state: str

    def __post_init__(self) -> None:
        MemoryCommitResult(self.event_id, self.item, self.version, self.durable_state, self.projection_state)
        _choice("MemoryNotice", "action", self.action, ACTIONS)

    @classmethod
    def of(cls, result: MemoryCommitResult, action: str) -> MemoryNotice:
        return cls(result.event_id, result.item, result.version, action, result.durable_state, result.projection_state)

    @property
    def saved(self) -> bool:
        """Only an fsync-confirmed commit may say Remembered or Updated."""
        return self.durable_state == "confirmed"


@dataclass(frozen=True)
class ContinuationCheckpoint:
    """The deterministic checkpoint written at every turn settlement (§5), from host state only. References are opaque host
    identities; no source text or model prose is carried."""

    project: str
    session: str
    sequence: int
    branch: str
    worktree: str
    baseline: str  # the commit the turn settled on, or "" when there is none
    settled_at_ms: int
    outcome: str
    objective: str  # a host reference to the objective, never its text
    pending: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        owner = "ContinuationCheckpoint"
        for name in ("project", "session", "branch", "worktree", "outcome", "objective"):
            _opaque(owner, name, getattr(self, name))
        _count(owner, "sequence", self.sequence, minimum=1)
        _count(owner, "settled_at_ms", self.settled_at_ms)
        if type(self.baseline) is not str or (self.baseline and not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", self.baseline)):
            raise ContractError(f"{owner}.baseline must be a commit id or empty")
        _tuple_of(owner, "pending", self.pending, str)
        for reference in self.pending:
            _opaque(owner, "pending", reference)
