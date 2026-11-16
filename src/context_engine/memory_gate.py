"""The memory Gate's decision (Plan 12.11 Task 1; design spec v4 §4): the only path to a memory write.

Pure: given a candidate, what the host verified about it and the item it names (if any), the Gate says what event to append,
or why nothing is appended. It never reads files, calls a model or touches the store; the host supplies the verdict, and the
store's single fenced append is the commit (§5). Repetition, tests, compaction, pinning, type and citations never raise
trust: nothing here can turn an agent or imported candidate into a user-authored one.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from context_engine.contracts import ContractError
from context_engine.memory_contracts import (
    ADMITTING_ACTS,
    AGENT_KINDS,
    USER_KINDS,
    HostVerdict,
    MemoryCandidate,
)
from context_engine.memory_projection import ItemState

OUTCOMES = ("append", "none", "refuse")
_BLOCKED_TITLE = "(withheld: blocked by a scan)"


@dataclass(frozen=True)
class EventDraft:
    """The event the store should append, before it assigns an event id. `expected_version` is what the item must be at."""

    item: str
    expected_version: int
    action: str
    trust: str
    status: str
    kind: str
    title: str
    statement: str


@dataclass(frozen=True)
class GateDecision:
    outcome: str  # "append", "none" (nothing to remember) or "refuse" (not allowed here)
    reason: str
    draft: EventDraft | None = None


def item_id(project: str, idempotency_key: str) -> str:
    """A new item's id: deterministic, so a retried candidate names the same item and the store's idempotency check sees it."""
    return "m-" + hashlib.sha256(f"context-engine/memory-item/v1\0{project}\0{idempotency_key}".encode()).hexdigest()[:16]


def _off(candidate: MemoryCandidate, reason: str, *, scanned: bool) -> GateDecision:
    """An off record: pointer and scanned title only, never the payload (§4)."""
    title = candidate.title if scanned else _BLOCKED_TITLE
    draft = EventDraft(item_id(candidate.project, candidate.idempotency_key), 0, "off", "off", "active", candidate.kind, title, "")
    return GateDecision("append", reason, draft)


def admit(candidate: MemoryCandidate, verdict: HostVerdict, target: ItemState | None = None) -> GateDecision:
    """Decide one candidate. `target` is the current authoritative state of `candidate.target`, or None when it names none or
    the item does not exist."""
    if not verdict.workspace_trusted:
        return GateDecision("refuse", "WORKSPACE_UNTRUSTED")  # untrusted workspaces are read-only for memory
    if not verdict.scope_valid:
        return GateDecision("refuse", "SCOPE_INVALID")
    user = candidate.trust == "user-authored"
    if (user and candidate.kind not in USER_KINDS) or (candidate.trust == "agent-derived" and candidate.kind not in AGENT_KINDS):
        return GateDecision("refuse", "ORIGIN_KIND_INVALID")
    if candidate.speech_act in ("question", "hypothetical"):
        return GateDecision("none", "NO_RULE")  # questions and hypotheticals create no rules
    if not verdict.scans_passed:
        return _off(candidate, "SCAN_BLOCKED", scanned=False)
    if candidate.speech_act == "quotation":
        return _off(candidate, "QUOTATION", scanned=True)
    if user and not verdict.spans_verified:
        return _off(candidate, "SPANS_UNVERIFIED", scanned=True)  # model assertions outside the spans gain no user provenance
    if candidate.trust == "agent-derived" and not verdict.lineage_complete:
        return _off(candidate, "LINEAGE_UNRESOLVED", scanned=True)

    if candidate.target is not None:
        if target is None or target.item != candidate.target or target.project != candidate.project or not target.live:
            return _off(candidate, "TARGET_UNAVAILABLE", scanned=True)  # ambiguity leaves an off candidate
        if target.trust == "user-authored" and not user:
            return _off(candidate, "CONFLICTS_WITH_USER", scanned=True)  # agent conflicts go off without prompting
        if candidate.speech_act == "retraction":
            draft = EventDraft(target.item, target.version, "withdraw", target.trust, "withdrawn", target.kind, "", "")
            return GateDecision("append", "RETRACTED", draft)
        draft = EventDraft(target.item, target.version, "update", candidate.trust, "active", candidate.kind, candidate.title,
                           candidate.statement)
        return GateDecision("append", "SUPERSEDED", draft)  # a new version of the same item; history keeps the old one

    if candidate.speech_act == "retraction":
        return _off(candidate, "TARGET_UNAVAILABLE", scanned=True)
    if candidate.speech_act not in ADMITTING_ACTS:  # pragma: no cover - every speech act is handled above
        raise ContractError(f"unhandled speech act {candidate.speech_act}")
    draft = EventDraft(item_id(candidate.project, candidate.idempotency_key), 0, "admit", candidate.trust, "active", candidate.kind,
                       candidate.title, candidate.statement)
    return GateDecision("append", "ADMITTED", draft)
