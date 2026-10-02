"""Bounded records for the pytest run context: one writer, one reader, one registry location.

Test tooling only. A record is a fixed set of typed fields: run ID, worktree, commit, process ID
plus creation time, job facts, counters and outcomes. The same field table is enforced when a
record is written and when one is read:

- a field that is not in the table, at any depth, rejects the whole record;
- every text field must match its own bounded pattern (identifiers, timestamps, a path without
  control characters), so free text, command lines and exception text have no field to live in;
- the writer also passes the record through the project's shared persistence sanitizer and
  refuses to write a record that the sanitizer would change; and
- `schema` is reserved: a caller cannot supply or replace it.

A rejection names the field's place in the table, never the offending value. Every record is
written atomically and read with a size limit.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Callable
from pathlib import Path

SCHEMA = "test-run-context-v1"
MAX_RECORD_BYTES = 256 * 1024
MAX_REGISTRY_ENTRIES = 512
MAX_MEMBERS = 4096
REJECTED = "TEST_RUN_CONTEXT_RECORD_REJECTED"
TOO_LARGE = "TEST_RUN_CONTEXT_RECORD_TOO_LARGE"

RUN_ID = re.compile(r"\d{8}T\d{6}-(?P<pid>\d{1,10})-[0-9a-f]{6}")
JOB_NAME = re.compile(r"optimus-test-run-\d{8}T\d{6}-\d{1,10}-[0-9a-f]{6}")
BRANCH = re.compile(r"[A-Za-z0-9._/-]{1,200}")
AGENT = re.compile(r"[A-Za-z0-9._-]{1,64}")
COMMIT = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")
IMAGE = re.compile(r"[A-Za-z0-9._ ()+-]{1,128}")
WORKTREE = re.compile(r"[^\x00-\x1f\x7f]{1,400}")
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?\+00:00")
_TOKEN = re.compile(r"[A-Za-z0-9_]{1,48}")

_Check = Callable[[object], bool]


def _text(pattern: re.Pattern[str]) -> _Check:
    return lambda value: isinstance(value, str) and pattern.fullmatch(value) is not None


def _one_of(*allowed: str) -> _Check:
    return lambda value: isinstance(value, str) and value in allowed


def _optional(check: _Check) -> _Check:
    return lambda value: value is None or check(value)


def _flag(value: object) -> bool:
    return isinstance(value, bool)


def _count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and -(2**31) <= value < 2**64


def _seconds(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value < 1e12


_IDENTITY: dict[str, object] = {
    "pid": _count, "creation_time": _optional(_count), "image": _optional(_text(IMAGE)),
    "error": _optional(_count), "live": _optional(_flag),
}
_FIELDS: dict[str, object] = {
    "schema": _one_of(SCHEMA),
    "checkpoint": _one_of("start", "terminal"),
    "run_id": _text(RUN_ID),
    "mode": _one_of("active", "passive"),
    "reason": _text(_TOKEN),
    "session_index": _count,
    "started_utc": _text(_TIMESTAMP),
    "finished_utc": _text(_TIMESTAMP),
    "worktree": _optional(_text(WORKTREE)),
    "branch": _optional(_text(BRANCH)),
    "head": _optional(_text(COMMIT)),
    "declared_agent": _optional(_text(AGENT)),
    "withheld": [_one_of("worktree", "branch", "head", "declared_agent")],
    "platform": _text(_TOKEN),
    "root": _IDENTITY,
    "root_parent": _IDENTITY,
    "parent_run": {
        "status": _one_of("parent", "none", "not_found", "UNKNOWN", "same_interpreter", "unsupported"),
        "run_id": _text(RUN_ID), "method": _one_of("validated_process_ancestry"), "reason": _text(_TOKEN),
    },
    "native": {
        "supported": _flag, "attempted": _flag, "enrolled": _flag, "valid": _flag, "job_name": _text(JOB_NAME),
        "reused_from_earlier_session": _flag, "created": _flag, "create_error": _optional(_count),
        "name_already_existed": _flag, "handle_inheritable": _optional(_flag), "limits_set": _flag,
        "limits_error": _optional(_count), "assigned": _flag, "assign_error": _optional(_count),
        "self_is_member": _optional(_flag), "kill_on_close": _flag, "breakaway_ok": _flag,
        "silent_breakaway_ok": _flag, "flags_error": _count,
    },
    "guard_mode": _text(_TOKEN),
    "exit_status": _count,
    "accounting": {
        "ok": _flag, "error": lambda value: _count(value) or _text(_TOKEN)(value), "total_processes": _count,
        "active_processes": _count, "user_seconds": _seconds, "kernel_seconds": _seconds,
        "io": {name: _count for name in (
            "read_operations", "write_operations", "other_operations", "read_bytes", "write_bytes", "other_bytes")},
    },
    "members": {"ok": _flag, "complete": _flag, "error": _optional(_count), "identities": [_IDENTITY]},
}
_REQUIRED = ("schema", "checkpoint", "run_id", "mode", "reason")


def _violation(value: object, rule: object, place: str) -> str | None:
    """Where a value first breaks the field table, or None. Never returns the value itself."""
    if isinstance(rule, dict):
        if not isinstance(value, dict):
            return place
        for name, item in value.items():
            if name not in rule:
                return f"{place}.<unlisted>"
            found = _violation(item, rule[name], f"{place}.{name}")
            if found is not None:
                return found
        return None
    if isinstance(rule, list):
        if not isinstance(value, list) or len(value) > MAX_MEMBERS:
            return place
        for item in value:
            found = _violation(item, rule[0], f"{place}[]")
            if found is not None:
                return found
        return None
    return None if rule(value) else place  # type: ignore[operator]


def violation(record: object) -> str | None:
    """The first place a whole record breaks the field table, or None when it conforms."""
    found = _violation(record, _FIELDS, "record")
    if found is not None:
        return found
    assert isinstance(record, dict)
    missing = [name for name in _REQUIRED if name not in record]
    if missing:
        return f"record.{missing[0]}"
    # A run ID carries its root's process ID; an entry whose two halves disagree is not a run's own.
    root, matched = record.get("root"), RUN_ID.fullmatch(str(record["run_id"]))
    if isinstance(root, dict) and "pid" in root and matched is not None and int(matched.group("pid")) != root["pid"]:
        return "record.run_id"
    return None


def unchanged_by_shared_sanitizer(value: object) -> bool:
    """Whether the project's shared persistence sanitizer leaves a value exactly as it is."""
    from optimus_security.sanitization import sanitize_for_persistence

    return sanitize_for_persistence(value, known_secrets=()).value == value


def registry_root() -> Path:
    """Where runs announce themselves. A temporary folder, outside every protected application folder."""
    return Path(tempfile.gettempdir()) / "optimus-test-runs" / "registry"


def write_record(target: Path, payload: dict[str, object]) -> None:
    """Persist one conforming record atomically. The single persistence sink of the run context."""
    if "schema" in payload:
        raise ValueError(f"{REJECTED}:record.schema")
    record = {"schema": SCHEMA, **payload}
    found = violation(record)
    if found is not None:
        raise ValueError(f"{REJECTED}:{found}")
    if not unchanged_by_shared_sanitizer(record):
        raise ValueError(f"{REJECTED}:shared_sanitizer")
    body = json.dumps(record, indent=1, sort_keys=True)
    if len(body.encode("utf-8")) > MAX_RECORD_BYTES:
        raise ValueError(TOO_LARGE)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + f".{os.getpid()}.tmp")
    temporary.write_text(body, encoding="utf-8")
    os.replace(temporary, target)


def read_record(source: Path) -> dict[str, object] | None:
    """Read one record, or None when it is missing, too large, malformed or breaks the field table."""
    try:
        if source.stat().st_size > MAX_RECORD_BYTES:
            return None
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if violation(payload) is not None:
        return None
    return payload


def registry_entries(exclude_run_id: str) -> list[dict[str, object]]:
    """Other runs' registry entries that conform and are filed under their own run ID. Never deletes."""
    root = registry_root()
    try:
        candidates = sorted(root.glob("*.json"))[-MAX_REGISTRY_ENTRIES:]
    except OSError:
        return []
    entries: list[dict[str, object]] = []
    for candidate in candidates:
        entry = read_record(candidate)
        if entry is not None and entry["run_id"] != exclude_run_id and candidate.name == f"{entry['run_id']}.json":
            entries.append(entry)
    return entries
