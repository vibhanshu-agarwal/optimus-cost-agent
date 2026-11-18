"""The memory store's deletion journal (Plan 12.11 Task 2; ADR-042): payload-free purge records, fsynced before each step is
dispatched, kept outside the Redis volume so a later restore can still learn what was purged.

It reuses the durable outbox's streams (one per Gateway process, fsynced, hash-chained, verified-prefix recovery) under
`<memory-store root>/journal/`. Each record also carries an HMAC with a key derived from the Gateway's generated ACL password, so
a record the Gateway did not write is refused rather than believed. A record names a project by the same hash as its Redis
keys, an item id, a version, the purge's idempotency key, stream ids and persistence counters: never a title or a statement.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from optimus_security import durable_outbox as ob

KIND: Final = "memory.purge"
PHASES: Final = ("intent", "tombstoned", "physical", "completed")


class JournalError(RuntimeError):
    """`code` is MEMORY_JOURNAL_UNAVAILABLE (cannot write) or MEMORY_JOURNAL_INVALID (a record fails its HMAC)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def journal_key(password: str) -> bytes:
    return hashlib.sha256(b"optimus-memory-journal-v1\0" + password.encode("utf-8")).digest()


def _mac(key: bytes, facts: Mapping[str, Any]) -> str:
    body = json.dumps(facts, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hmac.new(key, body, hashlib.sha256).hexdigest()


class PurgeJournal:
    def __init__(self, root: Path, key: bytes) -> None:
        self._root = root
        self._key = key
        self._lock = threading.Lock()
        self._writer: ob.StreamWriter | None = None

    def record(self, project: str, item: str, phase: str, **facts: Any) -> None:
        """Append one fsynced record; returns only once it is durable. Raises JournalError when it cannot be written, so the
        caller dispatches nothing."""
        assert phase in PHASES
        body = {"kind": KIND, "project": project, "item": item, "phase": phase, "at_ms": int(time.time() * 1000), **facts}
        payload = {**body, "mac": _mac(self._key, body)}
        with self._lock:
            try:
                if self._writer is None:
                    self._writer = ob.StreamWriter(self._root)
                self._writer.append(payload)
            except ob.OutboxError:
                raise JournalError("MEMORY_JOURNAL_UNAVAILABLE") from None

    def entries(self, project: str, item: str) -> list[dict[str, Any]]:
        """Every record for one item, from every Gateway's stream, in time order. A dead writer's last record is kept too when its
        HMAC verifies: the outbox withholds it only because it cannot tell whether its fsync returned, and every phase records
        a fact that already holds or is conservative (an intent may be followed by nothing), so believing it never loses a
        purge. A journal that names a purge Redis never received only makes purge_status ask for the retry."""
        found: list[dict[str, Any]] = []
        for directory in ob.stream_dirs(self._root):
            own = self._writer is not None and directory.name == self._writer.stream_id
            handle = None if own else ob.claim(directory)
            try:
                scan = ob.scan_stream(directory, orphan=handle is not None)
            finally:
                if handle is not None:
                    ob.release(handle)
            for record in (*scan.records, *((scan.unverified_tail,) if scan.unverified_tail is not None else ())):
                payload = dict(record.payload)
                if payload.get("kind") != KIND:
                    continue
                mac = payload.pop("mac", "")
                if not hmac.compare_digest(str(mac), _mac(self._key, payload)):
                    raise JournalError("MEMORY_JOURNAL_INVALID")
                if payload["project"] == project and payload["item"] == item:
                    found.append(payload)
        return sorted(found, key=lambda entry: (entry["at_ms"], PHASES.index(entry["phase"])))

    def project_entries(self, project: str) -> list[dict[str, Any]]:
        """Every record for one project, from every Gateway's stream, in time order, for a restore, which applies them all. It
        fails closed (Codex CP3 review 1, finding 1): a stream whose verification stopped at damage may have lost a later
        record, so the journal is MEMORY_JOURNAL_DAMAGED rather than a shorter list."""
        found: list[dict[str, Any]] = []
        if not self._root.is_dir():
            return found  # nothing was ever journalled here; the generation's journal frontier decides whether that is enough
        for directory in ob.stream_dirs(self._root):
            own = self._writer is not None and directory.name == self._writer.stream_id
            handle = None if own else ob.claim(directory)
            try:
                scan = ob.scan_stream(directory, orphan=handle is not None)
            finally:
                if handle is not None:
                    ob.release(handle)
            if any(damage.reason != "torn" or damage is not scan.damage[-1] for damage in scan.damage):
                raise JournalError("MEMORY_JOURNAL_DAMAGED")
            for record in (*scan.records, *((scan.unverified_tail,) if scan.unverified_tail is not None else ())):
                payload = dict(record.payload)
                if payload.get("kind") != KIND:
                    continue
                mac = payload.pop("mac", "")
                if not hmac.compare_digest(str(mac), _mac(self._key, payload)):
                    raise JournalError("MEMORY_JOURNAL_INVALID")
                if payload["project"] == project:
                    found.append(payload)
        return sorted(found, key=lambda entry: (entry["at_ms"], PHASES.index(entry["phase"])))

    def close(self) -> None:
        with self._lock:
            if self._writer is not None:
                self._writer.close()
                self._writer = None
