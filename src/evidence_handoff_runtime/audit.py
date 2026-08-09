"""Narrow content-free audit recorder for review-ruling append/read (Task 7).

Records only kind, schema, digest, counts, identity IDs, sequence, and stable
failure code. Delivery/cursor/integrity/lifecycle fields belong to later tasks.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_ALLOWED_FIELDS = frozenset(
    {
        "kind",
        "schema_id",
        "digest",
        "counts",
        "principal_id",
        "agent_id",
        "sequence",
        "failure_code",
    }
)
_FORBIDDEN_SUBSTRINGS = frozenset(
    {
        "raw_body",
        "exception",
        "traceback",
        "authorization",
        "password",
        "token",
        "secret",
    }
)


class AuditRecorder:
    """Append-only JSONL audit writer with a closed field set."""

    def __init__(self, *, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: Mapping[str, Any]) -> None:
        if not isinstance(event, Mapping):
            raise ValueError("audit_event_invalid")
        keys = set(event)
        if not keys <= _ALLOWED_FIELDS:
            raise ValueError("audit_field_rejected")
        for key in keys:
            if key.lower() in _FORBIDDEN_SUBSTRINGS:
                raise ValueError("audit_field_rejected")
        # Reject forbidden payload keys even if somehow aliased later.
        lowered = {str(key).lower() for key in keys}
        if lowered & _FORBIDDEN_SUBSTRINGS:
            raise ValueError("audit_field_rejected")
        payload = {key: event[key] for key in sorted(keys)}
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        lower = serialized.lower()
        for needle in ("raw_body", "exception"):
            if needle in lower:
                raise ValueError("audit_field_rejected")
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.write("\n")


__all__ = ["AuditRecorder"]
