"""#343: the plan parser and the planning-turn classifier share one READ / WRITE / TEST directive grammar."""

from __future__ import annotations

import pytest

from optimus.agent import directives, planning_loop
from optimus.agent.directives import AgentDirectiveParseError, parse_agent_plan
from optimus.agent.planning_loop import PlanningTurnParseError, parse_planning_turn

# (line, is a directive). #410 R1: only spaces and tabs separate the keyword from its argument.
CASES = [
    ("READ a.txt", True),
    ("READ \t a.txt \t", True),
    ("READ\fa.txt", False),
    ("READ a.txt", False),
    ("READ", False),
    ("WRITE a.txt", True),
    ("WRITE\ta.txt \t", True),
    ("WRITE\fa.txt", False),
    ("WRITE a.txt", False),
    ("WRITE", False),
    ("TEST pytest", True),
    ("TEST\tpytest -q", True),
    ("TEST\fpytest", False),
    ("TEST pytest", False),
    ("TEST", False),
]


def _plan_parser_accepts(line: str) -> bool:
    try:
        parse_agent_plan(f"{line}\n", edit_base="forbidden")
    except AgentDirectiveParseError:
        return False
    return True


def _classify(text: str) -> str:
    try:
        return parse_planning_turn(text).kind.value
    except PlanningTurnParseError as exc:
        return exc.code


def _planning_turn_accepts(line: str) -> bool:
    """A directive line ends a WRITE body, so the OBSERVE behind it is seen; a non-directive line is body text."""
    if line.startswith("WRITE"):
        # as the opener: a WRITE line hides the OBSERVE in its body; anything else leaves it in view
        return _classify(f"{line}\nbody\nOBSERVE: x") == "FINAL_PLAN"
    # in a WRITE body: exactly these two outcomes, so an unrelated parse error cannot pass for either
    kind = _classify(f"WRITE a.txt\nbody\n{line}\nOBSERVE: x")
    assert kind in ("INTERMEDIATE_UNSUPPORTED_DIRECTIVE", "FINAL_PLAN"), kind
    return kind == "INTERMEDIATE_UNSUPPORTED_DIRECTIVE"


@pytest.mark.parametrize(("line", "valid"), CASES)
def test_both_modules_accept_and_reject_the_same_lines(line: str, valid: bool) -> None:
    assert _plan_parser_accepts(line) is valid
    assert _planning_turn_accepts(line) is valid


def test_a_bare_write_keyword_inside_a_write_body_stays_body_text() -> None:
    # A looser boundary check (a prefix match) would end the body here and expose the OBSERVE line.
    turn = parse_planning_turn("WRITE a.txt\nbody\nWRITE\nOBSERVE: x")
    assert turn.kind.value == "FINAL_PLAN"
    assert turn.directives.write.content == "body\nWRITE\nOBSERVE: x"


@pytest.mark.parametrize("name", ["READ_DIRECTIVE", "WRITE_DIRECTIVE", "TEST_DIRECTIVE"])
def test_planning_loop_uses_the_directives_compiled_patterns(name: str) -> None:
    assert getattr(planning_loop, name) is getattr(directives, name)
