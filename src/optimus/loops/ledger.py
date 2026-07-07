"""Append-only progress records for bounded goal loops.

Conceptually, ProgressLedger is the audit trail for bounded goal loops: each loop
iteration appends what happened (progress, cost, why it stopped), and
evaluators/controllers can read prior entries for a run_id to decide whether to
continue, stop, or detect stagnation.

In short: ProgressLedger is the storage contract; ProgressLedgerEntry is the
record shape; InMemoryProgressLedger and JsonlProgressLedger are the two backends.

On completion, the controller may append both an outcome row and a stop-reason row
for the same iteration number. Downstream consumers should treat those as related
records rather than assuming one ledger row per iteration.
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from threading import Lock
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from optimus.loops.models import LoopStopReason
from optimus.telemetry.redaction import redact_for_telemetry
from optimus.telemetry.serialization import json_safe
from optimus.telemetry.subjects import sanitize_workspace_text


class ProgressLedgerEntry(BaseModel):
    """One iteration's progress snapshot: goal context, cost, stop reason, and evidence."""

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    session_id: str | None
    iteration: int = Field(ge=0)
    goal: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    cost_credits: Decimal = Field(ge=Decimal("0"))
    stop_reason: LoopStopReason | None
    failure_signature: str | None
    evidence: dict[str, str] = Field(default_factory=dict)
    occurred_at: datetime

    def to_json_dict(self) -> dict[str, object]:
        data = self.model_dump(mode="json")
        return json_safe(redact_for_telemetry(data))


class ProgressLedger(Protocol):
    """Storage contract: append entries and read back all entries for a run_id."""

    def append(self, entry: ProgressLedgerEntry) -> None:
        raise NotImplementedError

    def entries(self, *, run_id: str) -> tuple[ProgressLedgerEntry, ...]:
        raise NotImplementedError


class InMemoryProgressLedger:
    """In-process backend for tests and ephemeral loop runs."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._entries: list[ProgressLedgerEntry] = []

    def append(self, entry: ProgressLedgerEntry) -> None:
        with self._lock:
            self._entries.append(entry)

    def entries(self, *, run_id: str) -> tuple[ProgressLedgerEntry, ...]:
        with self._lock:
            return tuple(entry for entry in self._entries if entry.run_id == run_id)


class JsonlProgressLedger:
    """Persistent JSONL backend under workspace_root, with redacted append-time writes."""

    def __init__(self, path: str | Path, *, workspace_root: str | Path) -> None:
        root = Path(workspace_root).resolve()
        candidate = Path(path).resolve(strict=False)
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("progress ledger path must stay under workspace_root") from exc
        self._path = candidate
        self._workspace_root = root
        self._lock = Lock()

    def append(self, entry: ProgressLedgerEntry) -> None:
        # Redaction is idempotent; append-time sanitization adds the workspace-root context.
        payload = _sanitize_workspace_paths(entry.to_json_dict(), workspace_root=self._workspace_root)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.write("\n")

    def entries(self, *, run_id: str) -> tuple[ProgressLedgerEntry, ...]:
        if not self._path.exists():
            return ()
        decoded: list[ProgressLedgerEntry] = []
        with self._path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                entry = ProgressLedgerEntry.model_validate_json(line)
                if entry.run_id == run_id:
                    decoded.append(entry)
        return tuple(decoded)


def _sanitize_workspace_paths(value: object, *, workspace_root: Path) -> object:
    if isinstance(value, dict):
        return {key: _sanitize_workspace_paths(child, workspace_root=workspace_root) for key, child in value.items()}
    if isinstance(value, list):
        return [_sanitize_workspace_paths(child, workspace_root=workspace_root) for child in value]
    if isinstance(value, str):
        return sanitize_workspace_text(value, workspace_root=workspace_root)
    return value
