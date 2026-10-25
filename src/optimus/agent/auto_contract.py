"""The Auto classifier's input contract, frozen at Plan 12.4 Task 0 (v7 Design 3; ADR-007:73-74).

One bounded representation shared by the pilot's labelled set, its optimisers and production. It never carries
history or file contents: only the current prompt (cut to the excerpt budget), the session mode, an attachment
summary and the previous turn's routed tier. Changing anything here is a new contract version, never an edit.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePath
from typing import Final, Literal

# Standard library only: the pilot's separate DSPy environment loads this file by path (Plan 12.4 v7 Design 3).

__all__ = [
    "CONTRACT_VERSION",
    "MAX_EXTENSIONS",
    "PROMPT_EXCERPT_MAX_BYTES",
    "ClassifierInput",
    "build_classifier_input",
]

CONTRACT_VERSION: Final = "auto-input-v1"
PROMPT_EXCERPT_MAX_BYTES: Final = 4096
"""The prompt excerpt is at most its first 4 KB of UTF-8, whatever budget a configuration leaves."""
MAX_EXTENSIONS: Final = 5

Mode = Literal["CHAT", "AGENT"]
"""The ACP session modes (``ExecutionMode`` values); PLAN is not selectable from ACP (``acp/spec.py:129``)."""
SizeBucket = Literal["<4KB", "<64KB", "larger"]
Tier = Literal["easy", "medium", "complex"]

_MODES: Final[dict[str, Mode]] = {"CHAT": "CHAT", "AGENT": "AGENT"}
_TIERS: Final[dict[str, Tier]] = {"easy": "easy", "medium": "medium", "complex": "complex"}


@dataclass(frozen=True, slots=True)
class ClassifierInput:
    prompt: str
    truncated: bool
    mode: Mode
    attachment_count: int
    attachment_size: SizeBucket
    attachment_extensions: tuple[str, ...]
    previous_tier: Tier | None

    def to_json(self) -> str:
        """The canonical serialization every arm and production send: fixed field order, compact, UTF-8."""
        return json.dumps(
            {
                "contract": CONTRACT_VERSION,
                "prompt": self.prompt,
                "truncated": self.truncated,
                "mode": self.mode,
                "attachments": {
                    "count": self.attachment_count,
                    "size": self.attachment_size,
                    "extensions": list(self.attachment_extensions),
                },
                "previous_tier": self.previous_tier,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )


def _excerpt(prompt: str, budget_bytes: int) -> tuple[str, bool]:
    encoded = prompt.encode("utf-8")
    if len(encoded) <= budget_bytes:
        return prompt, False
    # Cut on a character boundary: a multi-byte character that does not fit whole is dropped.
    return encoded[:budget_bytes].decode("utf-8", errors="ignore"), True


def _size_bucket(total_bytes: int) -> SizeBucket:
    if total_bytes < 4096:
        return "<4KB"
    if total_bytes < 65536:
        return "<64KB"
    return "larger"


def build_classifier_input(
    prompt: str,
    *,
    mode: str,
    attachments: Iterable[tuple[str, int]] = (),
    previous_tier: str | None = None,
    excerpt_budget_bytes: int = PROMPT_EXCERPT_MAX_BYTES,
) -> ClassifierInput:
    """Build the contract for one turn.

    ``attachments`` are ``(path, size_bytes)`` for each attached file or range; their contents are never read.
    ``excerpt_budget_bytes`` is what a frozen configuration's fixed parts leave for the excerpt (Design 3). A budget
    of zero or less makes the configuration invalid, so it is refused here rather than sent without a prompt.
    """
    if excerpt_budget_bytes <= 0:
        raise ValueError("the configuration leaves no excerpt budget")
    checked_mode = _MODES.get(mode)
    if checked_mode is None:
        raise ValueError(f"mode {mode!r} is not an ACP session mode")
    checked_tier = None if previous_tier is None else _TIERS.get(previous_tier)
    if previous_tier is not None and checked_tier is None:
        raise ValueError(f"previous tier {previous_tier!r} is not a routable tier")
    items = list(attachments)
    if any(size < 0 for _, size in items):
        raise ValueError("an attachment size is negative")
    excerpt, truncated = _excerpt(prompt, min(excerpt_budget_bytes, PROMPT_EXCERPT_MAX_BYTES))
    # Sorted, so the same attachments give the same contract whatever order the client sent them in.
    extensions = sorted({PurePath(path).suffix.lower() for path, _ in items} - {""})[:MAX_EXTENSIONS]
    return ClassifierInput(
        prompt=excerpt,
        truncated=truncated,
        mode=checked_mode,
        attachment_count=len(items),
        attachment_size=_size_bucket(sum(size for _, size in items)),
        attachment_extensions=tuple(extensions),
        previous_tier=checked_tier,
    )
