"""The rebuildable memory projection (Plan 12.11 Task 1; design spec v4 §4-§5): a pure fold of authoritative events.

The event stream is the record; this view is derived and may be rebuilt at any time. Folding is strict: a version that does not
follow its predecessor, a change to an item that was never admitted, or a project that changes under an item is a
`ContractError`, never a silently repaired view. Serving decisions (`servable`) read only this fold, so an item is served only at
its authoritative current version.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

from context_engine.contracts import ContractError
from context_engine.memory_contracts import MemoryEvent, ServedMemory


@dataclass(frozen=True)
class ItemState:
    project: str
    item: str
    version: int
    trust: str
    status: str
    kind: str
    title: str
    statement: str
    scope: str
    anchors: tuple[str, ...]
    lineage: tuple[str, ...]
    valid_from_ms: int
    valid_until_ms: int

    @property
    def live(self) -> bool:
        """Can still be changed: not withdrawn, superseded or purged."""
        return self.status in ("active", "reverify", "conflicted")

    @property
    def servable(self) -> bool:
        """May enter a prompt: vouched for and active. A reverify item is at most an explicitly unverified hint, decided by the
        host, so it is not servable here."""
        return self.trust != "off" and self.status == "active"

    def served(self) -> ServedMemory:
        """The served form; only a servable item has one."""
        if not self.servable:
            raise ContractError(f"item {self.item} is not servable")
        return ServedMemory(self.project, self.item, self.version, self.trust, self.kind, self.scope, self.title, self.statement,
                            self.anchors)


def fold(events: Iterable[MemoryEvent]) -> dict[str, ItemState]:
    """Every item's current state, in stream order."""
    items: dict[str, ItemState] = {}
    for event in events:
        current = items.get(event.item)
        expected = 1 if current is None else current.version + 1
        if event.version != expected:
            raise ContractError(f"item {event.item} jumps from version {expected - 1} to {event.version}")
        if current is not None and current.project != event.project:
            raise ContractError(f"item {event.item} changed project")
        if current is None and event.action not in ("admit", "off"):
            raise ContractError(f"item {event.item} was changed before it was admitted")
        if current is not None and current.status == "purged":
            raise ContractError(f"item {event.item} changed after it was purged")
        if event.action == "withdraw" and current is not None:
            state = replace(current, version=event.version, status="withdrawn")  # the view keeps what was said; the event carries nothing
        elif event.action == "tombstone" and current is not None:
            state = replace(current, version=event.version, status="purged", title="", statement="", anchors=())
        else:
            state = ItemState(event.project, event.item, event.version, event.trust, event.status, event.kind, event.title, event.statement,
                              event.scope, event.anchors, event.lineage, event.valid_from_ms, event.valid_until_ms)
        items[event.item] = state
    return items
