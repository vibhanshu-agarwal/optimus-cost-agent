"""#512: the planning turn's ANSWER form. It is the whole reply, bounded, never mixed with a directive, and held to
#583's character rule with line breaks and tabs permitted. Special characters are built with chr()."""

from __future__ import annotations

import pytest

from optimus.agent.planning_loop import ANSWER_MAX_BYTES, PlanningTurnKind, PlanningTurnParseError, parse_planning_turn

NL, CR, TAB = chr(10), chr(13), chr(9)


def _code(text: str) -> str:
    with pytest.raises(PlanningTurnParseError) as caught:
        parse_planning_turn(text)
    return caught.value.code


@pytest.mark.parametrize("text", [
    "ANSWER: Yes.",
    "ANSWER: Yes." + NL + TAB + "Run the tests first." + NL + NL + "That is all.",
    "ANSWER: Yes." + CR + NL + "Line two.",
    "ANSWER:" + NL + "The answer starts on the next line.",
    "ANSWER: It reads " + chr(0x200D) + " fine.",  # ZWJ is allowed, as in #583
])
def test_an_answer_is_accepted_whole(text: str) -> None:
    decision = parse_planning_turn(text)
    assert decision.kind is PlanningTurnKind.ANSWER
    assert decision.reason == text[len("ANSWER:"):].strip().replace(CR + NL, NL)


def test_an_answer_at_its_bound_is_accepted_and_one_byte_over_is_refused() -> None:
    assert parse_planning_turn("ANSWER: " + "a" * ANSWER_MAX_BYTES).kind is PlanningTurnKind.ANSWER
    assert _code("ANSWER: " + "a" * (ANSWER_MAX_BYTES + 1)) == "ANSWER_TOO_LONG"
    assert _code("ANSWER: " + chr(0xE9) * (ANSWER_MAX_BYTES // 2 + 1)) == "ANSWER_TOO_LONG"  # bytes, not characters


@pytest.mark.parametrize("text", ["ANSWER:", "ANSWER:   ", "ANSWER:" + NL + TAB + NL, "ANSWER: " + chr(0xA0), "ANSWER:" + NL + chr(0x3000)])
def test_an_empty_answer_is_refused(text: str) -> None:
    assert _code(text) == "ANSWER_EMPTY"


@pytest.mark.parametrize("line", [
    "READ README.md", "READ: README.md#bytes=0:10", "WRITE a.py", "EDIT a.py", "TEST pytest -q", "OBSERVE: x",
    "MCP_LIST server", "MCP_CALL server tool {}", "MCP_LIST", "REFUSE: no", "ANSWER: again", "PLAN: x", "- WRITE a.py",
    "EDIT" + TAB + "a.py", "SEARCH needle", "OUTLINE README.md", "SYMBOLS main", "LIST .",  # Codex review 1, finding 2
])
def test_an_answer_never_holds_a_directive_line(line: str) -> None:
    assert _code("ANSWER: Yes." + NL + line) == "ANSWER_HAS_DIRECTIVE"


@pytest.mark.parametrize("char", [CR, chr(0), chr(0x1B), chr(0x202E), chr(0x2066), chr(0x2028), chr(0x200B), chr(0x3164), chr(0xE000)])
def test_an_answer_with_an_unsafe_character_is_refused(char: str) -> None:
    assert _code("ANSWER: Yes" + char + "no.") == "ANSWER_UNSAFE_TEXT"


@pytest.mark.parametrize("text", ["ANSWER: Yes." + CR, "ANSWER: " + chr(0x2028) + "Yes.", "ANSWER: Yes." + chr(0x2029)])
def test_an_unsafe_character_at_either_edge_is_refused_not_trimmed_away(text: str) -> None:
    """Codex review 1, finding 3: only a reply's padding (spaces, tabs, LF/CRLF) is trimmed before the rule runs."""
    assert _code(text) == "ANSWER_UNSAFE_TEXT"


def test_a_fenced_answer_is_an_answer_and_a_fenced_mixed_one_is_refused() -> None:
    """Codex review 1, finding 1: the final-plan parser would skip the answer line as prose and keep the TEST."""
    fence = "`" * 3
    assert parse_planning_turn(NL.join([fence, "ANSWER: Yes.", fence])).reason == "Yes."
    assert _code(NL.join([fence, "ANSWER: Here is my advice.", "TEST pytest -q", fence])) == "ANSWER_HAS_DIRECTIVE"


def test_a_fenced_answer_with_anything_after_its_closing_fence_is_not_an_answer() -> None:
    """Codex review 2, finding 3: the suffix keeps the reply out of the answer path, as on the parent."""
    fence = "`" * 3
    assert _code(NL.join([fence, "ANSWER: Yes.", fence, "MCP_LIST docs"])) == "MCP_MIXED_DIRECTIVES"


def test_a_directive_behind_leading_blanks_is_still_a_directive() -> None:
    """Codex review 2, finding 5: the intermediate parser strips U+00A0, so the answer scan does too."""
    assert _code("ANSWER: Yes." + NL + chr(0xA0) + "READ: README.md#bytes=0:10") == "ANSWER_HAS_DIRECTIVE"


def test_an_answer_with_a_lone_surrogate_is_refused_not_a_crash() -> None:
    assert _code("ANSWER: " + chr(0xD800)) == "ANSWER_UNSAFE_TEXT"


def test_a_refusal_is_still_a_refusal_and_prose_is_still_unrecognized() -> None:
    decision = parse_planning_turn("REFUSE: The evidence is not enough.")
    assert (decision.kind, decision.reason) == (PlanningTurnKind.REFUSE, "The evidence is not enough.")
    assert _code("Yes, run the tests.") == "GRAMMAR_UNRECOGNIZED"
    assert _code("The answer is ANSWER: yes.") == "GRAMMAR_UNRECOGNIZED"  # the form starts the reply or it is not one
