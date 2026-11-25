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


@pytest.mark.parametrize("name", ["READ_DIRECTIVE", "WRITE_DIRECTIVE", "TEST_DIRECTIVE", "is_directive_line"])
def test_planning_loop_uses_the_directives_compiled_patterns(name: str) -> None:
    assert getattr(planning_loop, name) is getattr(directives, name)


# #575 Part A: the bullet prefixes are one tuple shared by both parsers (behaviour-neutral).
def test_planning_loop_uses_the_directives_bullet_prefixes() -> None:
    assert planning_loop.BULLET_PREFIXES is directives.BULLET_PREFIXES


@pytest.mark.parametrize("bullet", ["- ", "* ", "+ "])  # literal, so shrinking the shared tuple fails here
def test_a_bulleted_directive_line_ends_a_write_body_in_both_modules(bullet: str) -> None:
    plan = parse_agent_plan(f"WRITE a.txt\nbody\n{bullet}READ b.txt\n", edit_base="forbidden")
    assert plan.read_paths == ("b.txt",)
    assert plan.write.content == "body\n"
    # planning turn: the READ line ends the body, so the OBSERVE behind it is seen (not hidden as body text)
    assert _classify(f"WRITE a.txt\nbody\n{bullet}READ b.txt\nOBSERVE: x") == "INTERMEDIATE_UNSUPPORTED_DIRECTIVE"


# #575: the final-plan parser decides where a WRITE body ends, and the planning turn defers to it. Each case sends
# the SAME reply to both real parsers. A whole MCP directive ends the body, so both reject the reply; any other line
# that only starts like one is file content, and both keep the same body.
NBSP = chr(0xA0)
MCP_PLAN_ERROR = "MCP directives are not valid in a final mutation plan"
FINAL = "FINAL_PLAN"
TURN_REJECTIONS = {"INTERMEDIATE_UNSUPPORTED_DIRECTIVE", "MCP_MIXED_DIRECTIVES", "GRAMMAR_UNRECOGNIZED"}
# (line, is a whole MCP directive)
MCP_LINES = [
    ("MCP_LIST server", True),
    ("MCP_LIST\tserver", True),
    ("MCP_LIST", False),
    ("MCP_LIST a b", False),
    ("MCP_LIST\ta b", False),
    (f"MCP_LIST{NBSP}server", False),
    ("MCP_LIST is a directive", False),
    ("MCP_LISTING things", False),
    ("MCP_CALL server tool {}", True),
    ("MCP_CALL\tserver tool {}", True),
    ("MCP_CALL", False),
    ("MCP_CALL server", False),
    ("MCP_CALL\tserver", False),
    (f"MCP_CALL{NBSP}server tool {{}}", False),
]


@pytest.mark.parametrize("tail", ["OBSERVE: x\n", "more\n"], ids=["then-observe", "then-text"])
@pytest.mark.parametrize("bullet", ["- ", ""], ids=["bulleted", "plain"])
@pytest.mark.parametrize(("line", "directive"), MCP_LINES)
def test_both_parsers_agree_on_an_mcp_looking_line_in_a_write_body(line: str, directive: bool, bullet: str, tail: str) -> None:
    body = f"body\n{bullet}{line}\n{tail}"
    reply = f"WRITE a.txt\n{body}"
    if directive:
        assert _classify(reply) in TURN_REJECTIONS
        with pytest.raises(AgentDirectiveParseError) as excinfo:
            parse_agent_plan(reply, edit_base="forbidden")
        assert str(excinfo.value) == MCP_PLAN_ERROR
    else:
        assert _classify(reply) == FINAL
        assert parse_planning_turn(reply).directives.write.content == body
        assert parse_agent_plan(reply, edit_base="forbidden").write.content == body


def test_a_markdown_body_that_describes_mcp_lines_is_one_final_plan() -> None:
    # The reply shape that a review of the first attempt at #575 found being rejected.
    body = "- MCP_LIST\tList configured servers\nOBSERVE: Record the result here\n"
    reply = f"WRITE notes.md\n{body}"
    assert _classify(reply) == FINAL
    assert parse_planning_turn(reply).directives.write.content == body
    assert parse_agent_plan(reply, edit_base="forbidden").write.content == body


def test_a_write_body_holding_an_edit_example_and_a_bare_cr_is_kept_whole() -> None:
    # A literal EDIT example is body text. Its END marker is followed by a bare CR, which is content (#410 R1), so the
    # MCP_LIST text after it is not a line of its own and the body does not end there.
    body = "<<<<<<< OLD\na\n======= NEW\nb\n>>>>>>> END\r- MCP_LIST\tserver\nOBSERVE: x\n"
    reply = f"WRITE notes.md\n{body}"
    assert _classify(reply) == FINAL
    assert parse_planning_turn(reply).directives.write.content == body
    assert parse_agent_plan(reply, edit_base="forbidden").write.content == body


@pytest.mark.parametrize("postscript", ["- MCP_LIST\tserver", "- MCP_LIST server", "READ b.txt"])
def test_text_after_a_fenced_write_is_not_part_of_the_plan_in_either_parser(postscript: str) -> None:
    reply = f"```\nWRITE a.txt\nbody\n```\n{postscript}\nOBSERVE: x\n"
    assert _classify(reply) == FINAL
    assert parse_planning_turn(reply).directives.write.content == "body\n"
    assert parse_agent_plan(reply, edit_base="forbidden").write.content == "body\n"


def test_a_write_line_inside_an_edit_block_does_not_hide_what_follows_the_block() -> None:
    # The WRITE text is the EDIT block's content, so the OBSERVE after the block is still seen and the turn is refused
    # with the same code as before #575.
    reply = "EDIT a.py\n<<<<<<< OLD\nWRITE x.txt\n======= NEW\nb\n>>>>>>> END\nOBSERVE: y\n"
    assert _classify(reply) == "INTERMEDIATE_UNRECOGNIZED_CONTENT"


@pytest.mark.parametrize("line", ["MCP_LIST server", "MCP_CALL server tool {}"])
def test_an_mcp_line_next_to_a_write_is_still_refused(line: str) -> None:
    assert _classify(f"{line}\nWRITE a.txt\nbody\n") == "MCP_NOT_EXACTLY_ONE"
    assert _classify(f"READ: a.py\n{line}\n") == "MCP_MIXED_DIRECTIVES"


# Replies found in review of #575 where the planner's own line scans and the final parser's lines differ (EDIT markers
# and bare carriage returns). Each must be classified exactly as before #575: the final parser's reading may lift a
# refusal, and nothing else.
CR = chr(13)
UNCHANGED_BY_575 = {
    "fenced-mcp-with-hidden-write": (f"```\nMCP_LIST demo\n<<<<<<< OLD{CR}text\nWRITE a.txt\n```\n", "MCP_MIXED_DIRECTIVES"),
    "mcp-after-lf-end-marker": (f"<<<<<<< OLD{CR}text\nWRITE a.txt\n>>>>>>> END\nMCP_LIST demo\n", "MCP_TOOL"),
    "mcp-after-cr-end-marker": (f"<<<<<<< OLD{CR}text\nWRITE a.txt\n>>>>>>> END{CR}MCP_LIST demo\n", "MCP_TOOL"),
    "write-body-opening-an-edit-example": ("WRITE a.txt\n<<<<<<< OLD\nREAD b.txt\nOBSERVE: x\n", FINAL),
    "write-body-opening-an-edit-example-crlf": (
        "WRITE a.txt\r\n<<<<<<< OLD\r\nREAD b.txt\r\nMCP_LISTING things\r\n",
        FINAL,
    ),
    "edit-with-cr-marker-and-write-text": (
        f"EDIT a.py{CR}<<<<<<< OLD\nWRITE x.txt\n======= NEW\nb\n>>>>>>> END\nOBSERVE: x\nREAD: b.py#bytes=0:1\n",
        "INTERMEDIATE_UNRECOGNIZED_CONTENT",
    ),
}


@pytest.mark.parametrize(("reply", "outcome"), UNCHANGED_BY_575.values(), ids=UNCHANGED_BY_575.keys())
def test_replies_whose_classification_575_must_not_change(reply: str, outcome: str) -> None:
    assert _classify(reply) == outcome
