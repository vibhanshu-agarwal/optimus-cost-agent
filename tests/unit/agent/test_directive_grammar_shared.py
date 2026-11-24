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


# #575: the bullet prefixes are one tuple, and a VALID MCP_LIST / MCP_CALL line takes spaces or tabs in both modules.
# Malformed and bare MCP lines are NOT classified alike at the WRITE boundary; see the characterization test below.
def test_planning_loop_uses_the_directives_bullet_prefixes() -> None:
    assert planning_loop.BULLET_PREFIXES is directives.BULLET_PREFIXES


@pytest.mark.parametrize("bullet", ["- ", "* ", "+ "])  # literal, so shrinking the shared tuple fails here
def test_a_bulleted_directive_line_ends_a_write_body_in_both_modules(bullet: str) -> None:
    plan = parse_agent_plan(f"WRITE a.txt\nbody\n{bullet}READ b.txt\n", edit_base="forbidden")
    assert plan.read_paths == ("b.txt",)
    assert plan.write.content == "body\n"
    # planning turn: the READ line ends the body, so the OBSERVE behind it is seen (not hidden as body text)
    assert _classify(f"WRITE a.txt\nbody\n{bullet}READ b.txt\nOBSERVE: x") == "INTERMEDIATE_UNSUPPORTED_DIRECTIVE"


MCP_LINES = [
    "MCP_LIST server",
    "MCP_LIST\tserver",
    "MCP_LIST \t server \t",
    "MCP_CALL server tool {}",
    "MCP_CALL\tserver\ttool\t{}",
    "MCP_CALL \t server \t tool \t {} \t",
]
MCP_PLAN_ERROR = "MCP directives are not valid in a final mutation plan"


@pytest.mark.parametrize("line", MCP_LINES)
def test_valid_mcp_lines_are_classified_alike_by_both_modules(line: str) -> None:
    # whole reply: the planning turn is an MCP request; the final-plan parser refuses it
    assert _classify(line) == "MCP_TOOL"
    with pytest.raises(AgentDirectiveParseError, match=MCP_PLAN_ERROR):
        parse_agent_plan(f"{line}\n", edit_base="forbidden")
    # in a WRITE body: exactly these outcomes, so an unrelated parse error cannot pass
    assert _classify(f"WRITE a.txt\nbody\n{line}\nOBSERVE: x") == "MCP_MIXED_DIRECTIVES"
    with pytest.raises(AgentDirectiveParseError, match=MCP_PLAN_ERROR):
        parse_agent_plan(f"WRITE a.txt\nbody\n{line}\n", edit_base="forbidden")
    # behind a bullet the planning turn only sees a valid line through its WRITE-body scan: it must end the body
    assert _classify(f"WRITE a.txt\nbody\n- {line}\nOBSERVE: x") == "INTERMEDIATE_UNSUPPORTED_DIRECTIVE"
    with pytest.raises(AgentDirectiveParseError, match=MCP_PLAN_ERROR):
        parse_agent_plan(f"WRITE a.txt\nbody\n- {line}\n", edit_base="forbidden")


NBSP = " "
# Malformed (MCP_LIST takes exactly one argument, MCP_CALL three) or not separated by a space or tab: body text.
NOT_MCP_LINES = [
    "MCP_LIST\tList configured servers",
    "MCP_CALL\tserver",
    f"MCP_LIST{NBSP}server",
    f"MCP_CALL{NBSP}server tool {{}}",
]


@pytest.mark.parametrize("line", NOT_MCP_LINES)
def test_a_malformed_mcp_line_behind_a_bullet_stays_in_a_write_body(line: str) -> None:
    # A realistic Markdown body: both modules keep the bullet and the OBSERVE line as WRITE content.
    body = f"body\n- {line}\nOBSERVE: Record the result here\n"
    turn = parse_planning_turn(f"WRITE a.txt\n{body}")
    assert turn.kind.value == "FINAL_PLAN"
    assert turn.directives.write.content == body
    assert parse_agent_plan(f"WRITE a.txt\n{body}", edit_base="forbidden").write.content == body


@pytest.mark.parametrize("line", ["MCP_LIST List configured servers", "MCP_LIST", "MCP_CALL server", "MCP_CALL"])
def test_known_disagreement_bare_and_malformed_mcp_lines_end_the_planning_turns_write_body(line: str) -> None:
    # Characterization, NOT an endorsement (#575): parse_planning_turn treats a bulleted bare or space-separated
    # malformed MCP line as a directive line, so it ends the WRITE body and the OBSERVE behind it is rejected;
    # parse_agent_plan keeps the same lines as body text. Fixing the disagreement must change this test.
    assert _classify(f"WRITE a.txt\nbody\n- {line}\nOBSERVE: x\n") == "INTERMEDIATE_UNSUPPORTED_DIRECTIVE"
    kept = parse_agent_plan(f"WRITE a.txt\nbody\n- {line}\n", edit_base="forbidden").write.content
    assert kept == f"body\n- {line}\n"
