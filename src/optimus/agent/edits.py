"""Apply an approved EDIT's blocks to a file's raw text (#407).

The text is the file's exact content, read with ``newline=""``. Every OLD block must match whole lines
exactly once, blocks must not overlap, and every byte outside the matched lines is kept as it was.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from optimus.agent.directives import AgentEditBlock

# Closed reason codes for an EDIT that cannot be applied; the run stops with EDIT_NOT_APPLICABLE.
EDIT_FAILURE_CODES = frozenset(
    {
        "EDIT_TARGET_MISSING",
        "EDIT_NOT_UTF8",
        "EDIT_SOURCE_UNSEEN",
        "EDIT_SOURCE_CHANGED",
        "EDIT_OLD_NOT_FOUND",
        "EDIT_OLD_NOT_UNIQUE",
        "EDIT_BLOCKS_OVERLAP",
    }
)

# (why the change was not made, what the person can do next). LLD v2.48 §4B.5 still states the old text: #576.
_FAILURE_TEXT = {
    "EDIT_TARGET_MISSING": ("that path is missing or is not a file", "Check the path, then send your request again"),
    "EDIT_NOT_UTF8": (
        "the file is not UTF-8 text",
        "Save the file as UTF-8 and send your request again, or make this change yourself",
    ),
    "EDIT_SOURCE_UNSEEN": (
        "the change was planned without the file's contents to hand",
        "Send your request again and name the file, so it is read first",
    ),
    "EDIT_SOURCE_CHANGED": ("the file changed after it was read", "Send your request again so the file is read as it is now"),
    "EDIT_OLD_NOT_FOUND": (
        "the lines it replaces are not in the file exactly as planned",
        "Send your request again to get a new plan",
    ),
    "EDIT_OLD_NOT_UNIQUE": (
        "the lines it replaces appear in the file more than once",
        "Send your request again and say which place to change",
    ),
    "EDIT_BLOCKS_OVERLAP": (
        "two parts of the planned change replace the same lines",
        "Send your request again to get a new plan",
    ),
}
assert set(_FAILURE_TEXT) == EDIT_FAILURE_CODES

_BOM = "﻿"
_LINE = re.compile(r"([^\r\n]*)(\r\n|\n|\r|$)")


class EditNotApplicable(Exception):
    def __init__(self, code: str) -> None:
        if code not in EDIT_FAILURE_CODES:
            raise ValueError(f"unknown EDIT failure code: {code}")
        super().__init__(code)
        self.code = code


def edit_failure_text(code: str, path: str) -> str:
    """The text an EDIT_NOT_APPLICABLE run shows: a fixed sentence per code, built only from the code and the path the
    plan named, never file content. The closed code ends it, so the next turn's history still carries it.

    The path is quoted so the history sanitizer cannot read "<secret-like name> was not" as an assignment and mask the
    negation. The second sentence speaks for this plan only: an earlier planning round may have run approved tools."""
    reason, next_step = _FAILURE_TEXT[code]
    return (
        f'The change to "{path}" was not made because {reason}. The plan made no changes and ran none of its tests. {next_step}. ({code})'
    )


def apply_edit_blocks(text: str, blocks: Sequence[AgentEditBlock]) -> str:
    bom = _BOM if text.startswith(_BOM) else ""
    lines = _split_lines(text[len(bom) :])
    contents = [content for content, _ in lines]
    spans = sorted(((_locate(contents, block.old_lines), block) for block in blocks), key=lambda item: item[0])
    for (previous, _), (current, _) in zip(spans, spans[1:], strict=False):
        if current[0] < previous[1]:
            raise EditNotApplicable("EDIT_BLOCKS_OVERLAP")

    result: list[tuple[str, str]] = []
    cursor = 0
    for (start, end), block in spans:
        result.extend(lines[cursor:start])
        result.extend(_replacement(block.new_lines, first=lines[start][1], last=lines[end - 1][1]))
        cursor = end
    result.extend(lines[cursor:])
    if not result:  # every line deleted: zero bytes, the BOM included
        return ""
    return bom + "".join(content + terminator for content, terminator in result)


def _split_lines(text: str) -> list[tuple[str, str]]:
    """(content, terminator) pairs. Only CRLF, LF and CR end a line, so other control characters stay content."""
    if not text:
        return []
    lines: list[tuple[str, str]] = []
    position = 0
    while position < len(text):
        match = _LINE.match(text, position)
        assert match is not None  # the pattern matches the empty string at any position
        lines.append((match.group(1), match.group(2)))
        position = match.end()
    return lines


def _locate(contents: list[str], old_lines: tuple[str, ...]) -> tuple[int, int]:
    width = len(old_lines)
    starts = [
        start
        for start in range(len(contents) - width + 1)
        if contents[start] == old_lines[0] and tuple(contents[start : start + width]) == old_lines
    ]
    if not starts:
        raise EditNotApplicable("EDIT_OLD_NOT_FOUND")
    if len(starts) > 1:
        raise EditNotApplicable("EDIT_OLD_NOT_UNIQUE")
    return starts[0], starts[0] + width


def _replacement(new_lines: tuple[str, ...], *, first: str, last: str) -> list[tuple[str, str]]:
    # NEW lines take the first matched line's terminator (LF when it has none: it was the unterminated last
    # line), and the last NEW line keeps the last matched line's, so the end-of-file state is unchanged.
    if not new_lines:
        return []
    separator = first or "\n"
    return [(line, separator) for line in new_lines[:-1]] + [(new_lines[-1], last)]
