"""Complete-turn rendering and partitioning (Plan 12.2 Task 7; design spec 6.1-6.4).

One canonical rendering per ordinary turn and per protected record. It is what the host's estimator
measures, and what maintenance input carries, so an allocation and the bytes behind it never disagree.
Partitioning works on whole turns only: a turn is never cut to meet an allocation.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from .contracts import OrdinaryTurn, ProtectedTurnState


def render_ordinary_turn(turn: OrdinaryTurn) -> str:
    """A complete ordinary turn as untrusted data, fields in their real order."""
    record = {"seq": turn.seq, "user_prompt": turn.user_prompt, "plan_text": turn.plan_text, "completion_text": turn.completion_text}
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def render_protected_state(state: ProtectedTurnState) -> str:
    """One turn's exact authority, carried verbatim."""
    record = {"seq": state.seq, "outcome": state.outcome, "effect_state": state.effect_state, "approval_facts": list(state.approval_facts)}
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def newest_suffix_start(costs: Sequence[int], budget: int) -> int:
    """Where the longest run of newest whole turns fitting `budget` starts; `len(costs)` if none fits.

    It stops at the first turn that does not fit, so an oversized newer turn is never skipped to keep
    older ones."""
    total, start = 0, len(costs)
    for index in range(len(costs) - 1, -1, -1):
        if total + costs[index] > budget:
            break
        total += costs[index]
        start = index
    return start
