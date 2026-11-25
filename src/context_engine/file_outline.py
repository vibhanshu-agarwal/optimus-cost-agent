"""The overflow outline (Plan 12.14, D4): a disclosed structural outline of one required file too large for the pack's hard ceiling. Pure.

Only a direct summary task, exactly `Summarize "<workspace-relative path>"`, can ask for it, and only for that one file. The outline is
built each time from the bytes just read, from the index parser's own structure (symbol signatures, document headings), never generated,
cached or kept. It says what it is, the source's hash and length, each entry's line range, and what it leaves out; nothing in it is the
file's body. A file the parser does not understand gets no outline, so its turn keeps today's too-large handling.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from .code_index import parse_file

OUTLINE_VERSION: Final = "m2b-outline-v1"
OUTLINE_MAX_TOKENS: Final = 2_048
DISCLOSURE: Final = "Outline only; full file not included. Read exact ranges before relying on omitted details."
_LINE_CHARS: Final = 160
_SUMMARIZE: Final = re.compile(r'Summarize "([^"\r\n]+)"')


def summary_target(task: str) -> str | None:
    """The path a task asks to summarize, when the whole task is that request and nothing else: no other words, quotes or lines."""
    match = _SUMMARIZE.fullmatch(task.strip())
    return match.group(1) if match else None


@dataclass(frozen=True)
class Outline:
    text: str
    language: str
    source_sha256: str
    source_bytes: int
    representation_sha256: str
    ranges: tuple[tuple[int, int], ...]  # the line range of every entry shown, in file order
    entries_total: int

    def metadata(self, path: str) -> dict[str, object]:
        """What /why and the manifest may keep: identities, ranges and counts, never the outline's text."""
        return {"path": path, "generator": OUTLINE_VERSION, "language": self.language, "source_sha256": self.source_sha256, "source_bytes": self.source_bytes,
                "representation_sha256": self.representation_sha256, "ranges": [list(item) for item in self.ranges], "entries_shown": len(self.ranges),
                "entries_omitted": self.entries_total - len(self.ranges), "bodies_omitted": True, "reread_required": True}


def build_outline(path: str, data: bytes, *, estimate: Callable[[str], int], max_tokens: int) -> Outline | None:
    """The outline of `data` within `max_tokens` (and never above OUTLINE_MAX_TOKENS), or None when the parser finds no structure or not
    even the first entry fits. Entries are kept in file order until the next would not fit; the rest are counted as omitted."""
    limit = min(max_tokens, OUTLINE_MAX_TOKENS)
    parsed = parse_file(path, data)
    entries = sorted((record for record in parsed.records if record.kind != "file" and record.start_line is not None),
                     key=lambda record: (record.start_line or 0, record.symbol or ""))
    if not entries:
        return None
    source = hashlib.sha256(data).hexdigest()
    head = [f"--- {path} (outline: {len(entries)} entries) ---", DISCLOSURE,
            f"Source: sha256 {source}, {len(data)} bytes, language {parsed.language}. Shown: each entry's line range and its signature or heading; every body is omitted."]
    lines: list[str] = []
    ranges: list[tuple[int, int]] = []

    def render(shown: list[str], omitted: int) -> str:
        tail = [f"Omitted: the {omitted} later entries, not listed here."] if omitted else []
        return "\n".join([*head, *shown, *tail])

    for record in entries:
        start, end = record.start_line or 0, record.end_line or record.start_line or 0
        label = " ".join((record.signature or record.symbol or record.kind).split())[:_LINE_CHARS]
        candidate = [*lines, f"{start}-{end} {label}"]
        if estimate(render(candidate, len(entries) - len(candidate))) > limit:
            break
        lines, ranges = candidate, [*ranges, (start, end)]
    if not lines:
        return None
    text = render(lines, len(entries) - len(lines))
    return Outline(text, parsed.language, source, len(data), hashlib.sha256(text.encode("utf-8")).hexdigest(), tuple(ranges), len(entries))
