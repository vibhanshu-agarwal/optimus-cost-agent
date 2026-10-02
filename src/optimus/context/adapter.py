"""Host adapter: canonical records and exact authority into engine snapshots (Plan 12.2 Task 6).

Design spec 4.1 and 5; Task 1 contracts 2. The canonical five-field `ConversationTurn` stays the
authority, and a summary never replaces it. Approval facts are host decisions taken from real
permission results, never read from a user's or model's prose. The engine receives them as exact
canonical strings it does not interpret. Ordinary text is re-sanitized on the way out (idempotent on
already-sanitized records), and the revision digest is the engine's own `history_digest`, separate from
the storage serializer and from the plan approval hash.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from context_engine import HistoryRevision, HistorySnapshot, OrdinaryTurn, ProtectedTurnState, history_digest
from optimus.acp.conversation import ConversationSanitizer, ConversationTurn


class ApprovalDecision(StrEnum):
    GRANTED = "granted"
    DENIED = "denied"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ApprovalFact:
    """One host-issued approval decision for a committed turn's artifact, and its granted scope.

    Historical facts describe what happened; they never authorize a new action."""

    turn_seq: int
    artifact_hash: str
    decision: ApprovalDecision
    scope: tuple[str, ...] = ()

    def render(self) -> str:
        """The exact canonical form the engine carries verbatim."""
        return json.dumps(
            {"artifact_hash": self.artifact_hash, "decision": self.decision.value, "scope": list(self.scope), "turn_seq": self.turn_seq},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


def approval_fact_from_permission(
    *, turn_seq: int, artifact_hash: str, permission_result: Mapping[str, Any], halted: bool, scope: tuple[str, ...] = ()
) -> ApprovalFact:
    """The fact a `session/request_permission` result establishes, decided exactly as the ACP session
    decides whether to apply the plan (`spec._permission_approved`, then the halt check)."""
    outcome = permission_result.get("outcome")
    if halted:
        decision = ApprovalDecision.CANCELLED
    elif isinstance(outcome, Mapping) and outcome.get("outcome") == "cancelled":
        decision = ApprovalDecision.CANCELLED
    elif isinstance(outcome, Mapping) and outcome.get("outcome") == "selected" and outcome.get("optionId") == "approve":
        decision = ApprovalDecision.GRANTED
    else:
        decision = ApprovalDecision.DENIED
    return ApprovalFact(turn_seq=turn_seq, artifact_hash=artifact_hash, decision=decision, scope=scope)


def make_history_snapshot(
    *,
    session_key: str,
    generation: int,
    records: Mapping[int, ConversationTurn],
    approvals: Mapping[int, Sequence[ApprovalFact]],
    sanitizer: ConversationSanitizer,
) -> HistorySnapshot:
    """Project committed records and host approval facts into one immutable engine snapshot."""
    for seq, facts in approvals.items():
        if seq not in records:
            raise ValueError(f"approval facts for uncommitted turn {seq}")
        if any(fact.turn_seq != seq for fact in facts):
            raise ValueError(f"approval fact filed under turn {seq} belongs to another turn")
    turns: list[OrdinaryTurn] = []
    protected: list[ProtectedTurnState] = []
    for seq in sorted(records):
        record = records[seq]
        turns.append(
            OrdinaryTurn(
                seq=seq,
                user_prompt=sanitizer.sanitize(record.user_prompt),
                plan_text=sanitizer.sanitize(record.plan_text) if record.plan_text else "",
                completion_text=sanitizer.sanitize(record.completion_text),
            )
        )
        protected.append(
            ProtectedTurnState(
                seq=seq,
                outcome=str(record.outcome.value),
                effect_state=str(record.effect_state.value),
                approval_facts=tuple(fact.render() for fact in approvals.get(seq, ())),
            )
        )
    turns_t, protected_t = tuple(turns), tuple(protected)
    revision = HistoryRevision(
        session_key=session_key,
        generation=generation,
        last_committed_seq=turns_t[-1].seq if turns_t else 0,
        digest=history_digest(turns_t, protected_t),
    )
    return HistorySnapshot(revision=revision, turns=turns_t, protected=protected_t)
