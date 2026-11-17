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
        """Every verified record for one item, from every Gateway's stream, in time order. An unverified tail of a dead writer's
        stream is left out: its fsync never returned, so nothing it named was dispatched."""
        found: list[dict[str, Any]] = []
        for directory in ob.stream_dirs(self._root):
            own = self._writer is not None and directory.name == self._writer.stream_id
            handle = None if own else ob.claim(directory)
            try:
                scan = ob.scan_stream(directory, orphan=handle is not None)
            finally:
                if handle is not None:
                    ob.release(handle)
            for record in scan.records:
                payload = dict(record.payload)
                if payload.get("kind") != KIND:
                    continue
                mac = payload.pop("mac", "")
                if not hmac.compare_digest(str(mac), _mac(self._key, payload)):
                    raise JournalError("MEMORY_JOURNAL_INVALID")
                if payload["project"] == project and payload["item"] == item:
                    found.append(payload)
        return sorted(found, key=lambda entry: (entry["at_ms"], PHASES.index(entry["phase"])))

    def close(self) -> None:
        with self._lock:
            if self._writer is not None:
                self._writer.close()
                self._writer = None
