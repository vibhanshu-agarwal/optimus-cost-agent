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
    def __init__(self) -> None:
        self._lock = Lock()
        self._events: list[ToolInvocationAuditEvent] = []

    def append(self, event: ToolInvocationAuditEvent) -> None:
        with self._lock:
            self._events.append(event)

    def events(self) -> tuple[ToolInvocationAuditEvent, ...]:
        with self._lock:
            return tuple(self._events)
