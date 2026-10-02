"""Bounded records for the pytest run context: one writer, one reader, one registry location.

Test tooling only. Records hold identifiers and counters: run ID, worktree, commit, process ID plus
creation time, job facts and outcomes. They never hold a command line, an environment value or an
exception's text. Every record is written atomically and read with a size limit.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

SCHEMA = "test-run-context-v1"
MAX_RECORD_BYTES = 256 * 1024
MAX_REGISTRY_ENTRIES = 512


def registry_root() -> Path:
    """Where runs announce themselves. A temporary folder, outside every protected application folder."""
    return Path(tempfile.gettempdir()) / "optimus-test-runs" / "registry"


def write_record(target: Path, payload: dict[str, object]) -> None:
    """Persist one record atomically. The single persistence sink of the run context."""
    body = json.dumps({"schema": SCHEMA, **payload}, indent=1, sort_keys=True)
    if len(body.encode("utf-8")) > MAX_RECORD_BYTES:
        raise ValueError("TEST_RUN_CONTEXT_RECORD_TOO_LARGE")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + f".{os.getpid()}.tmp")
    temporary.write_text(body, encoding="utf-8")
    os.replace(temporary, target)


def read_record(source: Path) -> dict[str, object] | None:
    """Read one record, or None when it is missing, too large, malformed or of another schema."""
    try:
        if source.stat().st_size > MAX_RECORD_BYTES:
            return None
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        return None
    return payload


def registry_entries(exclude_run_id: str) -> list[dict[str, object]]:
    """Other runs' registry entries that pass the size and schema checks. Never deletes anything."""
    root = registry_root()
    try:
        candidates = sorted(root.glob("*.json"))[-MAX_REGISTRY_ENTRIES:]
    except OSError:
        return []
    entries: list[dict[str, object]] = []
    for candidate in candidates:
        entry = read_record(candidate)
        if entry is not None and entry.get("run_id") != exclude_run_id:
            entries.append(entry)
    return entries
