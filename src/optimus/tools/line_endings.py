"""Agent-mode WRITE keeps the target's line endings, final newline and BOM (#410, design v3, R3-R5).

The body's line breaks are LF or CRLF only; every other character is content. The rules are pure, so each case
means the same bytes on every platform; the write itself is exact (`mutation_tools.write_file`).
"""

from __future__ import annotations

from typing import Literal

WRITE_LINE_ENDINGS_MIXED = "WRITE_LINE_ENDINGS_MIXED"

LineEndingStyle = Literal["lf", "crlf", "mixed", "none"]

_BOM = "\ufeff"
_BOM_BYTES = _BOM.encode("utf-8")


def line_ending_style(data: bytes) -> LineEndingStyle:
    """The file's style: one kind of terminator, none at all, or mixed (both kinds, or any lone CR)."""
    crlf = data.count(b"\r\n")
    lf = data.count(b"\n") - crlf
    if data.count(b"\r") > crlf or (crlf and lf):
        return "mixed"
    if crlf:
        return "crlf"
    return "lf" if lf else "none"


def fit_body_to_file(body: str, existing: bytes | None) -> str:
    """The text to write for `body`: a new file (`existing` None) is LF and ends as the body does; an existing file
    keeps its style, its BOM and its final newline: the body's last terminator is replaced by the file's own."""
    text = body.replace("\r\n", "\n")
    if existing is None:
        return text
    style = line_ending_style(existing)
    if style == "mixed":
        raise ValueError("a file with mixed line endings is never rewritten")
    bom = _BOM if existing.startswith(_BOM_BYTES) and not text.startswith(_BOM) else ""
    if not text:
        return bom  # emptying a file gives zero bytes, apart from its BOM
    eol = "\r\n" if style == "crlf" else "\n"
    text = text.removesuffix("\n").replace("\n", eol)
    return bom + text + (eol if existing.endswith(b"\n") else "")
