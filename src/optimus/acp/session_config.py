"""One full-set ACP session configuration publication (Plan 12.2 Task 10; design spec 10).

`SessionConfigSnapshot` holds every advertised selector: the mode, and the context strategy only for a
session with a configured attached engine. Every `session/new` result, setter response and
`config_option_update` carries the whole set built from one snapshot, so a change to one picker never
erases another. The strategy select's wire option `id` and the setter's `configId` are both
`context_strategy`, under the custom category `_context_strategy`, as the pinned ACP schema allows.

The registry enables no user model choice today (no selectable-model field; D5 open), so no model
selector is advertised: a picker that could not change the model would be a fake one.

`ConfigPublication` is the one resync state shared by every setter. A committed change stays pending
until its updates are confirmed as flushed; a mode change pends both `current_mode_update` and the full
set, a strategy-only change only the full set. Each send carries the revision it was made at, and only
a confirmation at the current revision clears the pending state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from optimus.acp.shapes import SESSION_MODE_CHOICES, build_mode_config_options

STRATEGY_CONFIG_ID = "context_strategy"
STRATEGY_CATEGORY = "_context_strategy"
SLIDING_DESCRIPTION = (
    "Keeps only the newest complete ordinary turns that fit. Older ordinary conversation content is dropped "
    "from model context."
)
SLIDING_ACTIVE_TEXT = (
    "Sliding window is active. Older ordinary conversation content may be omitted; execution outcomes and "
    "approval facts remain exact."
)
STRATEGY_CHOICES: tuple[tuple[str, str, str], ...] = (
    (
        "compaction",
        "Compaction",
        "Summarizes older complete turns and keeps the newest turns exact. Execution outcomes and approval "
        "facts remain exact.",
    ),
    (
        "hybrid",
        "Hybrid",
        "Keeps the first turn and a larger set of the newest turns exact, and summarizes the turns between "
        "them. Execution outcomes and approval facts remain exact.",
    ),
    ("sliding_window", "Sliding window", SLIDING_DESCRIPTION),
)
STRATEGY_IDS = tuple(value for value, _, _ in STRATEGY_CHOICES)
_MODE_IDS = tuple(mode_id for mode_id, _, _ in SESSION_MODE_CHOICES)


@dataclass(frozen=True, slots=True)
class SessionConfigSnapshot:
    """Every advertised selector's current value. `strategy` is None without an attached engine."""

    mode_id: str
    strategy: str | None

    def __post_init__(self) -> None:
        if self.mode_id not in _MODE_IDS:
            raise ValueError(f"unknown mode {self.mode_id!r}")
        if self.strategy is not None and self.strategy not in STRATEGY_IDS:
            raise ValueError(f"unknown strategy {self.strategy!r}")


def build_session_config_options(snapshot: SessionConfigSnapshot) -> list[dict[str, Any]]:
    """The full `configOptions` set for `snapshot`, in a stable order: mode, then strategy."""
    options = build_mode_config_options(current_mode_id=snapshot.mode_id)
    if snapshot.strategy is not None:
        options.append(
            {
                "id": STRATEGY_CONFIG_ID,
                "name": "Context strategy",
                "category": STRATEGY_CATEGORY,
                "type": "select",
                "currentValue": snapshot.strategy,
                "options": [
                    {"value": value, "name": name, "description": description}
                    for value, name, description in STRATEGY_CHOICES
                ],
            }
        )
    return options


class ConfigPublication:
    """One session's publication state: the committed revision and what is still unconfirmed."""

    def __init__(self) -> None:
        self.revision = 0
        self._mode_pending = False
        self._options_pending = False

    def commit(self, *, mode_changed: bool) -> int:
        """Record a committed change; returns the revision its sends must carry."""
        self.revision += 1
        self._options_pending = True
        if mode_changed:
            self._mode_pending = True
        return self.revision

    def pending_updates(self) -> tuple[str, ...]:
        if self._mode_pending:
            return ("current_mode_update", "config_option_update")
        if self._options_pending:
            return ("config_option_update",)
        return ()

    def confirmed(self, revision: int) -> None:
        """Every pending update was flushed at `revision`; an older revision clears nothing."""
        if revision == self.revision:
            self._mode_pending = False
            self._options_pending = False
