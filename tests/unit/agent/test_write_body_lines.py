"""#410: the WRITE body keeps its own line terminators (design v3, R1-R2)."""

from __future__ import annotations

import pytest

from optimus.agent.directives import parse_agent_plan


def _body(plan: str) -> str:
    write = parse_agent_plan(plan).write
    assert write is not None
    return write.content


@pytest.mark.parametrize(
    ("plan", "body"),
    [
        ("WRITE a.py\nx", "x"),  # the reply ends without a newline
        ("WRITE a.py\nx\n", "x\n"),
        ("WRITE a.py\nx\n\n", "x\n\n"),  # at the end of the reply nothing is dropped
        ("WRITE a.py\nx\nTEST pytest t.py", "x\n"),
        ("WRITE a.py\nx\n\nTEST pytest t.py", "x\n"),  # one empty line before a directive separates it
        ("WRITE a.py\nx\n\n\nTEST pytest t.py", "x\n\n"),  # a second empty line is content
        ("WRITE a.py\nx\n  \nTEST pytest t.py", "x\n  \n"),  # a spaces-only line is content
        ("WRITE a.py\nx\n\t\nTEST pytest t.py", "x\n\t\n"),
    ],
)
def test_the_body_extent_and_the_one_empty_line_separator(plan: str, body: str) -> None:
    assert _body(plan) == body


def test_a_crlf_reply_parses_the_same_directives_and_keeps_its_terminators() -> None:
    directives = parse_agent_plan("READ a.py\r\nWRITE a.py\r\nA\r\nb\r\n\r\nTEST pytest t.py\r\n")

    assert directives.read_paths == ("a.py",)
    assert directives.write is not None and directives.write.content == "A\r\nb\r\n"
    assert directives.tests == (("pytest", "t.py"),)


@pytest.mark.parametrize(
    ("plan", "body"),
    [
        ("```\nWRITE a.py\nA\nb\n```", "A\nb\n"),
        ("```text\r\nWRITE a.py\r\nA\r\nb\r\n```\r\n", "A\r\nb\r\n"),
    ],
)
def test_fenced_bodies_keep_their_terminators(plan: str, body: str) -> None:
    assert _body(plan) == body


@pytest.mark.parametrize("separator", ["\r", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"])
def test_only_lf_and_crlf_end_lines(separator: str) -> None:
    assert _body(f"WRITE a.py\nx{separator}y\n") == f"x{separator}y\n"


def test_a_separator_character_never_starts_a_directive() -> None:
    directives = parse_agent_plan("WRITE a.py\nx\u2028TEST pytest t.py\n")

    assert directives.tests == ()
    assert directives.write is not None and directives.write.content == "x\u2028TEST pytest t.py\n"


_CONTENT_SEPARATORS = ["\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"]


@pytest.mark.parametrize("separator", _CONTENT_SEPARATORS)
@pytest.mark.parametrize("directive", ["TEST pytest t.py", "READ b.txt", "WRITE c.txt", "MCP_LIST tools"])
def test_a_separator_before_directive_like_text_stays_body_content(separator: str, directive: str) -> None:
    """Codex round 50, finding 1: a preserved separator is never stripped into directive syntax."""
    for text in (f"WRITE a.txt\nx\n{separator}{directive}\n", f"WRITE a.txt\nx{separator}{directive}\n"):
        directives = parse_agent_plan(text)
        assert (directives.read_paths, directives.tests) == ((), ())
        assert directives.write is not None and directives.write.path == "a.txt"
        assert directives.write.content == text.removeprefix("WRITE a.txt\n")


@pytest.mark.parametrize("separator", _CONTENT_SEPARATORS)
@pytest.mark.parametrize("directive", ["TEST pytest t.py", "MCP_LIST tools", "MCP_CALL tools t {}", "OBSERVE: y", "READ: b.txt#bytes=0:1"])
def test_a_planning_turn_keeps_the_separator_in_the_final_plan_body(separator: str, directive: str) -> None:
    """The same, through the multi-turn preprocessing that routes a reply before final-plan parsing."""
    from optimus.agent.planning_loop import PlanningTurnKind, parse_planning_turn

    for text in (f"READ a.txt\nWRITE a.txt\nx\n{separator}{directive}\n", f"READ a.txt\nWRITE a.txt\nx{separator}{directive}\n"):
        decision = parse_planning_turn(text)
        assert decision.kind is PlanningTurnKind.FINAL_PLAN
        assert decision.directives is not None and decision.directives.tests == ()
        assert decision.directives.write is not None
        assert decision.directives.write.content == text.removeprefix("READ a.txt\nWRITE a.txt\n")
