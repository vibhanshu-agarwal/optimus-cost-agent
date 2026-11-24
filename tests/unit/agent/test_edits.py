"""Applying EDIT blocks to a file's raw text (#407): exact, unique, non-overlapping, byte-preserving."""

import pytest

from optimus.agent.directives import AgentEditBlock
from optimus.agent.edits import EDIT_FAILURE_CODES, EditNotApplicable, apply_edit_blocks, edit_failure_text


def _block(old: str, new: str | None) -> AgentEditBlock:
    return AgentEditBlock(old_lines=tuple(old.split("\n")), new_lines=() if new is None else tuple(new.split("\n")))


def _apply(text: str, *blocks: AgentEditBlock) -> str:
    return apply_edit_blocks(text, blocks)


def _code(text: str, *blocks: AgentEditBlock) -> str:
    with pytest.raises(EditNotApplicable) as caught:
        _apply(text, *blocks)
    return caught.value.code


def test_one_block_replaces_only_its_lines():
    assert _apply("a\nb\nc\n", _block("b", "B1\nB2")) == "a\nB1\nB2\nc\n"


def test_untouched_bytes_stay_identical_in_a_large_file():
    head = "".join(f"line {i}  \t\n" for i in range(3000))
    tail = "".join(f"tail {i}\n" for i in range(3000))
    text = head + "target\n" + tail

    assert _apply(text, _block("target", "changed")) == head + "changed\n" + tail


def test_several_blocks_apply_to_the_base_in_any_order():
    text = "a\nb\nc\nd\n"

    assert _apply(text, _block("d", "D"), _block("a\nb", "AB")) == "AB\nc\nD\n"


def test_old_must_match_exactly_once():
    assert _code("a\nb\n", _block("x", "y")) == "EDIT_OLD_NOT_FOUND"
    assert _code("a\nb\na\n", _block("a", "y")) == "EDIT_OLD_NOT_UNIQUE"
    # Whole lines only: a substring of a line is not a match, nor is trailing whitespace ignored.
    assert _code("abc\n", _block("b", "y")) == "EDIT_OLD_NOT_FOUND"
    assert _code("a \n", _block("a", "y")) == "EDIT_OLD_NOT_FOUND"


def test_overlapping_blocks_are_rejected():
    assert _code("a\nb\nc\n", _block("a\nb", "x"), _block("b\nc", "y")) == "EDIT_BLOCKS_OVERLAP"
    assert _code("a\nb\n", _block("a", "x"), _block("a", "y")) == "EDIT_BLOCKS_OVERLAP"


def test_crlf_files_keep_crlf_and_new_lines_take_it():
    assert _apply("a\r\nb\r\nc\r\n", _block("b", "B1\nB2")) == "a\r\nB1\r\nB2\r\nc\r\n"


def test_mixed_endings_take_the_first_matched_lines_terminator_and_keep_the_last_state():
    text = "a\nb\r\nc\nd\n"

    assert _apply(text, _block("b\nc", "x\ny\nz")) == "a\nx\r\ny\r\nz\nd\n"


def test_the_final_newline_state_is_kept():
    assert _apply("a\nb", _block("b", "B")) == "a\nB"
    assert _apply("a\nb\n", _block("b", "B")) == "a\nB\n"


def test_an_unterminated_single_line_replaced_by_several_uses_lf_between_them():
    assert _apply("only", _block("only", "x\ny")) == "x\ny"
    assert _apply("a\r\nlast", _block("last", "x\ny")) == "a\r\nx\ny"


def test_deleting_lines_keeps_the_neighbours_bytes():
    assert _apply("a\nb\nc\n", _block("b", None)) == "a\nc\n"
    # Deleting trailing lines keeps the newly exposed line's own terminator.
    assert _apply("a\nb\nc", _block("b\nc", None)) == "a\n"
    assert _apply("a\r\nb", _block("b", None)) == "a\r\n"


def test_deleting_every_line_gives_zero_bytes_even_with_a_bom():
    assert _apply("a\nb\n", _block("a\nb", None)) == ""
    assert _apply("﻿a\n", _block("a", None)) == ""


def test_a_bom_is_kept_and_excluded_from_matching():
    assert _apply("﻿a\nb\n", _block("a", "A")) == "﻿A\nb\n"


def test_an_empty_replacement_line_is_a_line():
    assert _apply("a\nb\n", _block("a", "")) == "\nb\n"


def test_lone_cr_terminators_are_line_breaks():
    assert _apply("a\rb\rc", _block("b", "B")) == "a\rB\rc"


def test_an_empty_file_has_nothing_to_match():
    assert _code("", _block("a", "b")) == "EDIT_OLD_NOT_FOUND"


def test_one_empty_unterminated_replacement_line_keeps_the_bom():
    assert _apply("\ufeffa", _block("a", "")) == "\ufeff"


def test_separators_other_than_cr_and_lf_stay_inside_a_line():
    assert _apply("x\u2028y\nz\n", _block("x\u2028y", "a\x0cb")) == "a\x0cb\nz\n"


_PATH = "src/pkg/small.py"
_NEXT_STEPS = {
    "EDIT_TARGET_MISSING": "Check the path, then send your request again.",
    "EDIT_NOT_UTF8": "Save the file as UTF-8 and send your request again, or make this change yourself.",
    "EDIT_SOURCE_UNSEEN": "Send your request again and name the file, so it is read first.",
    "EDIT_SOURCE_CHANGED": "Send your request again so the file is read as it is now.",
    "EDIT_OLD_NOT_FOUND": "Send your request again to get a new plan.",
    "EDIT_OLD_NOT_UNIQUE": "Send your request again and say which place to change.",
    "EDIT_BLOCKS_OVERLAP": "Send your request again to get a new plan.",
}
_REASONS = {
    "EDIT_TARGET_MISSING": "that path is missing or is not a file",
    "EDIT_NOT_UTF8": "the file is not UTF-8 text",
    "EDIT_SOURCE_UNSEEN": "the change was planned without the file's contents to hand",
    "EDIT_SOURCE_CHANGED": "the file changed after it was read",
    "EDIT_OLD_NOT_FOUND": "the lines it replaces are not in the file exactly as planned",
    "EDIT_OLD_NOT_UNIQUE": "the lines it replaces appear in the file more than once",
    "EDIT_BLOCKS_OVERLAP": "two parts of the planned change replace the same lines",
}


def test_every_failure_code_has_a_pinned_text():
    assert set(_NEXT_STEPS) == set(_REASONS) == EDIT_FAILURE_CODES


@pytest.mark.parametrize("code", sorted(EDIT_FAILURE_CODES))
def test_the_failure_text_says_why_and_what_to_do_next_in_plain_words(code):
    """#574: the person reads this text in their editor; the closed code stays at the end for tools and the next turn."""
    text = edit_failure_text(code, _PATH)

    assert text == (
        f'The change to "{_PATH}" was not made because {_REASONS[code]}. '
        f"The plan made no changes and ran none of its tests. {_NEXT_STEPS[code]} ({code})"
    )
    assert f'"{_PATH}"' in text
    assert text.endswith(f"({code})")
    assert _NEXT_STEPS[code] in text
    prose = text.removesuffix(f"({code})")
    for jargon in ("EDIT ", "OLD block", "raw evidence", "directive"):
        assert jargon not in prose
