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
from optimus.acp.shapes import build_tool_call_notification, tool_call_text_content

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
    """One line of plain text that renders as itself, at most `MAX_LABEL_CHARS` characters before escaping."""
    return escape_text(text, MAX_LABEL_CHARS)


def escape_text(text: str, limit: int) -> str:
    """One line of plain text that renders as itself: no controls, bidi overrides or zero-width marks, Markdown escaped,
    at most `limit` characters before escaping."""
    kept = "".join(" " if unicodedata.category(c).startswith("Z") or unicodedata.category(c) == "Cc" else c
                   for c in text if c not in _INVISIBLE and unicodedata.category(c) not in ("Cf", "Co", "Cs", "Cn"))
    kept = " ".join(kept.split())
    # Zed auto-links bare addresses even when Markdown is escaped (Z0, Zed 1.28.1): show them inert, as `http[:]//x`
    kept = _WWW.sub(r"\1[.]", _SCHEME.sub(r"\1[:]", kept))
    if len(kept) > limit:
        kept = kept[: limit - 1].rstrip() + "\u2026"
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


def card(session_id: str, notice: MemoryNotice, label: str, *, imported: bool = False) -> dict[str, Any]:
    """A commit's card. `imported`: an import's commit, headed "Imported", never the word the user's own items use."""
    head = "Imported" if imported and notice.saved and notice.action == "admit" else headline(notice)
    title = f"{head}: {escape_label(label)}" if label else head
    summary = f"{citation(notice)} \u00b7 {notice.durable_state}, {notice.projection_state}"
    return build_tool_call_notification(session_id=session_id, tool_call_id=f"{CARD_PREFIX}{notice.event_id}", title=title,
                                        summary=summary, kind="other", status="completed" if notice.saved else "failed")


def appended_text(notice: MemoryNotice, label: str) -> str:
    """The fallback for a client without cards: a final paragraph of host text, after the model's answer."""
    named = f" \u201c{escape_label(label)}\u201d" if label else ""
    return f"\n\n> **Memory:** {headline(notice)}{named} {citation(notice)}"


def confirm_permission_params(session_id: str, *, kind: str, title: str, text: str, meta: dict[str, Any], nonce: str, option: str,
                              cancel_option: str) -> dict[str, Any]:
    """A recovery action's one-shot `session/request_permission` (setting the copy's location with any sync consent, or
    restoring one generation): a host-only tool-call id, what it is bound to, and exactly two options, never an "always" one."""
    return {
        "sessionId": session_id,
        "toolCall": {"toolCallId": f"{CARD_PREFIX}{kind}-{nonce}", "title": escape_label(title), "kind": "edit", "status": "pending",
                     "content": [tool_call_text_content(text)]},
        "options": [{"optionId": option, "name": "Go ahead", "kind": "allow_once"},
                    {"optionId": cancel_option, "name": "Cancel", "kind": "reject_once"}],
        "_meta": {f"memory{kind.capitalize()}": meta},
    }


def purge_permission_params(session_id: str, *, project: str, item: str, version: int, title: str, nonce: str, option: str,
                            cancel_option: str) -> dict[str, Any]:
    """The purge's one-shot `session/request_permission` (plan v4, Commands): a host-only tool-call id, the project, item,
    version and deletion boundary it is bound to, and exactly two options, never an "always" one. Nothing the model writes can
    create it, and only the response to this request can answer it."""
    named = f" \u201c{escape_label(title)}\u201d" if title else ""
    text = (f"Delete the text of memory {item} version {version}{named}? It is withdrawn from use first. Its text is then removed "
            "from the memory store and its disk files; copies outside the store (synced folders, recycle bins, other copies) "
            "cannot be checked. This cannot be undone.")
    return {
        "sessionId": session_id,
        "toolCall": {"toolCallId": f"{CARD_PREFIX}purge-{nonce}", "title": f"Delete memory {item}@{version}?", "kind": "delete",
                     "status": "pending", "content": [tool_call_text_content(text)]},
        "options": [{"optionId": option, "name": "Purge", "kind": "allow_once"},
                    {"optionId": cancel_option, "name": "Cancel", "kind": "reject_once"}],
        "_meta": {"memoryPurge": {"project": project, "item": item, "version": version, "boundary": "memory-store-and-its-disk-files"}},
    }
