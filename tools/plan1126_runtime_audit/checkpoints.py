"""Conflict-aware atomic JSON checkpoints."""

from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


class CheckpointConflict(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Checkpoint:
    revision: int
    entries: Mapping[str, Any]


class CheckpointStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def read(self) -> Checkpoint:
        if not self.path.exists():
            return Checkpoint(revision=0, entries={})
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if set(payload) != {"schema_version", "revision", "entries"} or payload["schema_version"] != "plan-11-26-checkpoint-v1":
            raise ValueError("checkpoint schema is invalid")
        return Checkpoint(revision=payload["revision"], entries=payload["entries"])

    @contextmanager
    def _exclusive_lock(self):
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        deadline = time.monotonic() + 5.0
        descriptor: int | None = None
        while descriptor is None:
            try:
                descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError as exc:
                if time.monotonic() >= deadline:
                    raise CheckpointConflict("checkpoint lock unavailable") from exc
                time.sleep(0.01)
        try:
            os.write(descriptor, str(os.getpid()).encode("ascii"))
            os.fsync(descriptor)
            yield
        finally:
            os.close(descriptor)
            lock_path.unlink(missing_ok=True)

    def append(self, record_id: str, payload: Any, *, expected_revision: int) -> Checkpoint:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._exclusive_lock():
            current = self.read()
            if current.revision != expected_revision:
                raise CheckpointConflict(f"expected revision {expected_revision}; found {current.revision}")
            entries = dict(current.entries)
            entries[record_id] = payload
            updated = Checkpoint(revision=current.revision + 1, entries=entries)
            document = {"schema_version": "plan-11-26-checkpoint-v1", "revision": updated.revision, "entries": entries}
            encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
            descriptor, temporary_name = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.path)
            except BaseException:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                temporary.unlink(missing_ok=True)
                raise
            return updated
