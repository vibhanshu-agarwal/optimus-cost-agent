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

_FAILURE_TEXT = {
    "EDIT_TARGET_MISSING": "the file does not exist",
    "EDIT_NOT_UTF8": "the file is not UTF-8 text",
    "EDIT_SOURCE_UNSEEN": "the plan was not made on raw evidence of this file",
    "EDIT_SOURCE_CHANGED": "the file changed after the model read it",
    "EDIT_OLD_NOT_FOUND": "an OLD block does not match the file's lines",
    "EDIT_OLD_NOT_UNIQUE": "an OLD block matches the file more than once",
    "EDIT_BLOCKS_OVERLAP": "two OLD blocks overlap",
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
    """The fixed text an EDIT_NOT_APPLICABLE run shows: the closed code and why, never file or model content."""
    return f"EDIT not applied to {path} ({code}): {_FAILURE_TEXT[code]}. Nothing was written."


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
