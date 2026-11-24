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


# #575 Part A: the bullet prefixes are one tuple shared by both parsers (behaviour-neutral).
# The MCP_LIST / MCP_CALL lines are a pinned, unresolved disagreement between the parsers; see the end of the file.
def test_planning_loop_uses_the_directives_bullet_prefixes() -> None:
    assert planning_loop.BULLET_PREFIXES is directives.BULLET_PREFIXES


@pytest.mark.parametrize("bullet", ["- ", "* ", "+ "])  # literal, so shrinking the shared tuple fails here
def test_a_bulleted_directive_line_ends_a_write_body_in_both_modules(bullet: str) -> None:
    plan = parse_agent_plan(f"WRITE a.txt\nbody\n{bullet}READ b.txt\n", edit_base="forbidden")
    assert plan.read_paths == ("b.txt",)
    assert plan.write.content == "body\n"
    # planning turn: the READ line ends the body, so the OBSERVE behind it is seen (not hidden as body text)
    assert _classify(f"WRITE a.txt\nbody\n{bullet}READ b.txt\nOBSERVE: x") == "INTERMEDIATE_UNSUPPORTED_DIRECTIVE"


# Characterization tests: they pin what the code does TODAY for MCP lines behind a bullet in a WRITE body. The two
# parsers disagree for several of these rows, and that disagreement is tracked in #575 (it is unresolved, and nothing
# below endorses it). Each case sends the SAME reply text to both real parsers. Whoever resolves the disagreement
# must change these expectations deliberately.
NBSP = " "
MCP_PLAN_ERROR = "MCP directives are not valid in a final mutation plan"
FINAL = "FINAL_PLAN"
UNSUPPORTED = "INTERMEDIATE_UNSUPPORTED_DIRECTIVE"
# (line behind "- ", planning-turn outcome, plan-parser outcome): an error message, or None when the plan parser
# keeps the whole body (everything after "WRITE a.txt\n") as the WRITE content.
BULLETED_MCP_LINES = [
    ("MCP_LIST server", UNSUPPORTED, MCP_PLAN_ERROR),
    ("MCP_LIST\tserver", "GRAMMAR_UNRECOGNIZED", MCP_PLAN_ERROR),
    ("MCP_LIST", UNSUPPORTED, None),
    ("MCP_LIST a b", UNSUPPORTED, None),
    ("MCP_LIST\ta b", FINAL, None),
    (f"MCP_LIST{NBSP}server", FINAL, None),
    ("MCP_CALL server tool {}", UNSUPPORTED, MCP_PLAN_ERROR),
    ("MCP_CALL\tserver tool {}", "GRAMMAR_UNRECOGNIZED", MCP_PLAN_ERROR),
    ("MCP_CALL", UNSUPPORTED, None),
    ("MCP_CALL server", UNSUPPORTED, None),
    ("MCP_CALL\tserver", FINAL, None),
    (f"MCP_CALL{NBSP}server tool {{}}", FINAL, None),
]


@pytest.mark.parametrize(("line", "turn_outcome", "plan_error"), BULLETED_MCP_LINES)
def test_known_disagreement_bulleted_mcp_line_in_a_write_body_followed_by_observe(
    line: str, turn_outcome: str, plan_error: str | None
) -> None:
    reply = f"WRITE a.txt\nbody\n- {line}\nOBSERVE: x\n"
    body = f"body\n- {line}\nOBSERVE: x\n"
    assert _classify(reply) == turn_outcome
    if turn_outcome == FINAL:
        assert parse_planning_turn(reply).directives.write.content == body
    if plan_error is None:
        assert parse_agent_plan(reply, edit_base="forbidden").write.content == body
    else:
        with pytest.raises(AgentDirectiveParseError) as excinfo:
            parse_agent_plan(reply, edit_base="forbidden")
        assert str(excinfo.value) == plan_error


def test_known_disagreement_pin_bare_cr_edit_example_body_with_a_tab_mcp_line_is_kept_whole() -> None:
    # Pins main's behaviour (#575): a WRITE body holding a literal EDIT example whose END marker is followed by a bare
    # CR and then a bulleted tab-form MCP_LIST line stays one FINAL_PLAN in both parsers.
    body = "<<<<<<< OLD\na\n======= NEW\nb\n>>>>>>> END\r- MCP_LIST\tserver\nOBSERVE: x\n"
    reply = f"WRITE notes.md\n{body}"
    assert _classify(reply) == FINAL
    assert parse_planning_turn(reply).directives.write.content == body
    assert parse_agent_plan(reply, edit_base="forbidden").write.content == body


def test_known_disagreement_pin_fenced_write_followed_outside_the_fence_by_a_tab_mcp_line() -> None:
    # Pins main's behaviour (#575): text after the closing fence is not read as part of the WRITE.
    reply = "```\nWRITE a.txt\nbody\n```\n- MCP_LIST\tserver\nOBSERVE: x\n"
    assert _classify(reply) == FINAL
    assert parse_planning_turn(reply).directives.write.content == "body\n"
    assert parse_agent_plan(reply, edit_base="forbidden").write.content == "body\n"
