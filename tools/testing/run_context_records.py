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
MAX_STREAM_BYTES = 32 * 1024 * 1024
MAX_OTHER_RUNS = 64
MAX_RUN_FOLDERS = 2000
REJECTED = "TEST_RUN_CONTEXT_RECORD_REJECTED"
TOO_LARGE = "TEST_RUN_CONTEXT_RECORD_TOO_LARGE"

RUN_ID = re.compile(r"\d{8}T\d{6}-(?P<pid>\d{1,10})-[0-9a-f]{6}")
JOB_NAME = re.compile(r"optimus-test-run-\d{8}T\d{6}-\d{1,10}-[0-9a-f]{6}")
BRANCH = re.compile(r"[A-Za-z0-9._/-]{1,200}")
AGENT = re.compile(r"[A-Za-z0-9._-]{1,64}")
COMMIT = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")
IMAGE = re.compile(r"[A-Za-z0-9._ ()+-]{1,128}")
WORKTREE = re.compile(r"[^\x00-\x1f\x7f]{1,400}")
LABEL = re.compile(r"[A-Za-z0-9_./:\[\]-]{1,200}")
REASON = re.compile(r"[ -~]{0,200}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_VERSION = re.compile(r"[A-Za-z0-9.+-]{1,40}")
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?\+00:00")
_TOKEN = re.compile(r"[A-Za-z0-9_]{1,48}")

_Check = Callable[[object], bool]


class RecordTooLarge(ValueError):
    """A record or a stream would pass its size ceiling. Carries only the fixed code."""


class _Table(dict):  # type: ignore[type-arg]
    """A table of fields, with the names that must be present."""

    def __init__(self, fields: dict[str, object], required: tuple[str, ...] = ()) -> None:
        super().__init__(fields)
        self.required = required


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


# An identity always names its process and always states its creation time, even when that time
# could not be read (null). A consumer may therefore index both without checking.
_IDENTITY = _Table({
    "pid": _count, "creation_time": _optional(_count), "image": _optional(_text(IMAGE)),
    "error": _optional(_count), "live": _optional(_flag),
}, required=("pid", "creation_time"))
_ACCOUNTING: dict[str, object] = {
    "ok": _flag, "error": lambda value: _count(value) or _text(_TOKEN)(value), "total_processes": _count,
    "active_processes": _count, "user_seconds": _seconds, "kernel_seconds": _seconds,
    "io": {name: _count for name in (
        "read_operations", "write_operations", "other_operations", "read_bytes", "write_bytes", "other_bytes")},
}
# The three append-only streams beside a run record. Each line is one entry of exactly one table.
_STREAMS: dict[str, _Table] = {
    # Every collected test: an exact digest of its node ID, and a display label that may be withheld.
    "nodes": _Table({
        "node": _text(_DIGEST), "label": _optional(_text(LABEL)), "state": _one_of("selected", "deselected"),
    }, required=("node", "label", "state")),
    # One test phase as pytest reported it. `at` and `seconds` are relative to the start of the run.
    "phases": _Table({
        "node": _text(_DIGEST), "when": _one_of("setup", "call", "teardown"),
        "outcome": _one_of("passed", "failed", "skipped"), "at": _seconds, "seconds": _seconds,
        "reason": _text(REASON),
    }, required=("node", "when", "outcome", "at", "seconds")),
    # What else was running, read at a phase boundary. `gap` is the time since the previous sample.
    "samples": _Table({
        "at": _seconds, "gap": _seconds, "checkpoint": _one_of("start", "phase", "terminal"),
        "accounting": _ACCOUNTING,
        "others": [_Table({
            "run_id": _text(RUN_ID), "relation": _one_of("own_job", "outside", "unverified"),
            "declared_agent": _optional(_text(AGENT)), "worktree": _optional(_text(WORKTREE)),
        }, required=("run_id", "relation"))],
        "others_not_listed": _count, "registry_error": _flag,
    }, required=("at", "gap", "checkpoint", "others")),
}
_FIELDS = _Table({
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
    "parent_run": _Table({
        "status": _one_of("parent", "none", "not_found", "UNKNOWN", "same_interpreter", "unsupported"),
        "run_id": _text(RUN_ID), "method": _one_of("validated_process_ancestry"), "reason": _text(_TOKEN),
    }, required=("status",)),
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
    "accounting": _ACCOUNTING,
    "accounting_baseline": _ACCOUNTING,
    "python": _text(_VERSION), "pytest": _text(_VERSION),
    "lock_sha256": _optional(_text(_DIGEST)), "config_sha256": _optional(_text(_DIGEST)),
    "selection_sha256": _text(_DIGEST),
    "protected_roots": _count, "protection": _one_of("full", "reduced", "none"),
    "selected": _count, "deselected": _count, "collection_errors": _count,
    "streams": {"nodes": _count, "phases": _count, "samples": _count, "truncated": _flag},
    "recording_errors": _count, "deferred_appends": _count, "last_sample_at": _seconds,
    "completeness": _one_of("COMPLETE", "TRUNCATED", "INVALID"),
    "members": {"ok": _flag, "complete": _flag, "error": _optional(_count), "identities": [_IDENTITY]},
}, required=("schema", "checkpoint", "run_id", "mode", "reason", "root"))


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
        for name in getattr(rule, "required", ()):
            if name not in value:
                return f"{place}.{name}"
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
    # A run ID carries its root's process ID; an entry whose two halves disagree is not a run's own.
    matched = RUN_ID.fullmatch(record["run_id"])
    if matched is None or int(matched.group("pid")) != record["root"]["pid"]:
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
        raise RecordTooLarge(TOO_LARGE)
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


def append_entries(target: Path, stream: str, entries: list[dict[str, object]], *, max_bytes: int = MAX_STREAM_BYTES) -> None:
    """Append conforming entries to one of a run's streams. The run context's only other sink.

    Every entry is checked against its stream's table, the batch must be left unchanged by the
    shared sanitizer, and the file may not grow past its ceiling. Nothing is written otherwise.
    """
    table = _STREAMS[stream]
    for entry in entries:
        found = _violation(entry, table, stream)
        if found is not None:
            raise ValueError(f"{REJECTED}:{found}")
    if not unchanged_by_shared_sanitizer(entries):
        raise ValueError(f"{REJECTED}:shared_sanitizer")
    body = "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in entries)
    existing = target.stat().st_size if target.exists() else 0
    if existing + len(body.encode("utf-8")) > max_bytes:
        raise RecordTooLarge(TOO_LARGE)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as stream_file:
        stream_file.write(body)


def read_entries(source: Path, stream: str) -> tuple[list[dict[str, object]], int]:
    """A stream's conforming entries and the number of lines refused (malformed, cut short or foreign)."""
    table = _STREAMS[stream]
    try:
        if source.stat().st_size > MAX_STREAM_BYTES:
            return [], 1
        lines = source.read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return [], 0
    entries: list[dict[str, object]] = []
    refused = 0
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            refused += 1
            continue
        if _violation(entry, table, stream) is None:
            entries.append(entry)
        else:
            refused += 1
    return entries, refused


def sanitized_text(value: str) -> str:
    """Free text as the shared persistence sanitizer leaves it."""
    from optimus_security.sanitization import sanitize_for_persistence

    return str(sanitize_for_persistence(value, known_secrets=()).value)


def remove_own_registry_entry(run_id: str) -> None:
    """A finished run withdraws its own announcement. No other run's entry is ever removed."""
    if RUN_ID.fullmatch(run_id) is not None:
        (registry_root() / f"{run_id}.json").unlink(missing_ok=True)


def prune_run_folders(runs_root: Path, keep_run_id: str, *, ceiling: int = MAX_RUN_FOLDERS) -> int:
    """Keep this worktree's newest run folders, up to the ceiling. Returns how many were removed.

    Only folders named as run IDs are considered, the current run is never removed, and a folder
    without a terminal record is kept: it may belong to a run that is still going.
    """
    import shutil

    try:
        folders = sorted(entry for entry in runs_root.iterdir() if entry.is_dir() and RUN_ID.fullmatch(entry.name))
    except OSError:
        return 0
    removed = 0
    for folder in folders[: max(0, len(folders) - ceiling)]:
        record = read_record(folder / "run.json")
        if folder.name == keep_run_id or record is None or record.get("checkpoint") != "terminal":
            continue
        shutil.rmtree(folder, ignore_errors=True)
        removed += 1
    return removed


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
