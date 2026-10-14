from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class ToolInvocationAuditEvent:
    run_id: str
    session_id: str | None
    tool_surface: str
    verdict: str
    layer: str
    rule_id: str
    reason: str
    failed_checks: tuple[str, ...]
    sanitized_subject: str
    requires_human_approval: bool
    approver: str | None = None


class InMemoryAuditSink:
    """Thread-safe recent audit view; durable audit storage is a separate concern."""

    def __init__(self, *, max_events: int = 16) -> None:
        if max_events < 1:
            raise ValueError("max_events must be >= 1")
        self._lock = Lock()
        self.max_events = max_events
        self._events: list[ToolInvocationAuditEvent] = []
        self._dropped = 0

    def append(self, event: ToolInvocationAuditEvent) -> None:
        with self._lock:
            self._events.append(event)
            if len(self._events) > self.max_events:
                del self._events[0]
                self._dropped += 1

    def events(self) -> tuple[ToolInvocationAuditEvent, ...]:
        with self._lock:
            return tuple(self._events)

    @property
    def dropped_count(self) -> int:
        with self._lock:
            return self._dropped
