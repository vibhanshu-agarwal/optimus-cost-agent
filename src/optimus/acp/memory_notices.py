"""Host memory notices (Plan 12.11; design spec v4 \u00a75): what the user sees when memory changes, built only from a
`MemoryNotice` the store confirmed, never from model prose.

Two surfaces. A model-free ACP tool-call card whose id is reserved (`memory/<event_id>`), so no model tool call can
create, update or impersonate it; and the same words appended to the turn's text, for a client that does not render
cards (P5-c's fallback). A label comes from user text, so it is escaped for Markdown and stripped of control, bidi and
zero-width characters before it is bounded: dropping a prefix is not enough when the rest can still render as markup.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Final

from context_engine.memory_contracts import MemoryNotice
from optimus.acp.shapes import build_tool_call_notification

CARD_PREFIX: Final = "memory/"
MAX_LABEL_CHARS: Final = 60
_MARKDOWN = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~&])")
_SCHEME = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*):(?=//)")
_WWW = re.compile(r"(?i)\b(www)\.")
_INVISIBLE = frozenset("\u061c\u200b\u200c\u200d\u200e\u200f\u2060\ufeff") | {chr(c) for c in range(0x202A, 0x202F)} | {
    chr(c) for c in range(0x2066, 0x206A)}

_WORDS: Final = {
    ("admit", "confirmed"): "Remembered",
    ("update", "confirmed"): "Updated",
    ("withdraw", "confirmed"): "Forgotten",
    ("tombstone", "confirmed"): "Deleted",
    ("off", "confirmed"): "Not remembered",
}


def is_memory_card(tool_call_id: object) -> bool:
    """A model's tool call never uses this prefix; the host refuses one that does."""
    return isinstance(tool_call_id, str) and tool_call_id.startswith(CARD_PREFIX)


def escape_label(text: str) -> str:
    """One line of plain text that renders as itself: no controls, bidi overrides or zero-width marks, Markdown escaped,
    at most `MAX_LABEL_CHARS` characters before escaping."""
    kept = "".join(" " if unicodedata.category(c).startswith("Z") or unicodedata.category(c) == "Cc" else c
                   for c in text if c not in _INVISIBLE and unicodedata.category(c) not in ("Cf", "Co", "Cs", "Cn"))
    kept = " ".join(kept.split())
    # Zed auto-links bare addresses even when Markdown is escaped (Z0, Zed 1.28.1): show them inert, as `http[:]//x`
    kept = _WWW.sub(r"\1[.]", _SCHEME.sub(r"\1[:]", kept))
    if len(kept) > MAX_LABEL_CHARS:
        kept = kept[: MAX_LABEL_CHARS - 1].rstrip() + "\u2026"
    return _MARKDOWN.sub(r"\\\1", kept)


def headline(notice: MemoryNotice) -> str:
    """Only an fsync-confirmed commit may say Remembered or Updated; anything else says what is still uncertain."""
    if notice.saved:
        return _WORDS[(notice.action, "confirmed")]
    if notice.durable_state == "unconfirmed":
        return "Not saved yet: the store has not confirmed it is on disk"
    return "Not saved"


def citation(notice: MemoryNotice) -> str:
    return f"[memory:{notice.item}@{notice.version}]"


def card(session_id: str, notice: MemoryNotice, label: str) -> dict[str, Any]:
    title = f"{headline(notice)}: {escape_label(label)}" if label else headline(notice)
    summary = f"{citation(notice)} \u00b7 {notice.durable_state}, {notice.projection_state}"
    return build_tool_call_notification(session_id=session_id, tool_call_id=f"{CARD_PREFIX}{notice.event_id}", title=title,
                                        summary=summary, kind="other", status="completed" if notice.saved else "failed")


def appended_text(notice: MemoryNotice, label: str) -> str:
    """The fallback for a client without cards: a final paragraph of host text, after the model's answer."""
    named = f" \u201c{escape_label(label)}\u201d" if label else ""
    return f"\n\n> **Memory:** {headline(notice)}{named} {citation(notice)}"
