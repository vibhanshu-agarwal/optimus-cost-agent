"""Plan 12.2 Task 7: complete-turn rendering and the newest-suffix rule (design spec 6.1, 6.4)."""

from __future__ import annotations

import json

import pytest

from context_engine import OrdinaryTurn, ProtectedTurnState
from context_engine.selection import newest_suffix_start, render_ordinary_turn, render_protected_state


def test_an_ordinary_turn_renders_whole_in_its_real_field_order() -> None:
    turn = OrdinaryTurn(seq=12, user_prompt="Fix rounding", plan_text="WRITE calc.py", completion_text="Done — 2.34")
    text = render_ordinary_turn(turn)
    assert text == '{"seq":12,"user_prompt":"Fix rounding","plan_text":"WRITE calc.py","completion_text":"Done — 2.34"}'
    assert list(json.loads(text)) == ["seq", "user_prompt", "plan_text", "completion_text"]


def test_protected_state_renders_every_fact_verbatim() -> None:
    fact = '{"artifact_hash":"h","decision":"denied","scope":[],"turn_seq":3}'
    state = ProtectedTurnState(seq=3, outcome="rejected", effect_state="none", approval_facts=(fact,))
    rendered = json.loads(render_protected_state(state))
    assert rendered == {"seq": 3, "outcome": "rejected", "effect_state": "none", "approval_facts": [fact]}


@pytest.mark.parametrize(
    "costs, budget, start",
    [
        ([], 100, 0),
        ([10, 10, 10], 30, 0),
        ([10, 10, 10], 29, 1),
        ([10, 10, 10], 0, 3),
        ([10, 50, 10], 25, 2),  # stops at the oversized middle turn; never skips it to reach the first
        ([10, 10, 50], 30, 3),  # an oversized newest turn leaves no tail at all
    ],
    ids=["empty", "all-fit", "one-short", "zero-budget", "stops-at-oversized", "oversized-newest"],
)
def test_the_newest_suffix_stops_at_the_first_turn_that_does_not_fit(costs, budget, start) -> None:
    assert newest_suffix_start(costs, budget) == start
