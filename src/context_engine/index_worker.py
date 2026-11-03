"""The resumable index worker (Plan 12.10 Task 3; ADR-037). Neutral: the host injects its file policy, storage and embedder as ports.

A pass compares the source with what the building epoch already holds, so a cancelled, killed or paused worker resumes by doing only
what is still different. Open and named files go first, and the first indexed file is published at once. Writers hold a fenced
lease, so a replaced worker can change nothing. A storage outage pauses the worker; it never reports missing data as complete.

Indexing reads disk and calls the local embedder and the storage port. It makes no generative or provider call.
"""

from __future__ import annotations

import base64
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

from .code_index import IndexRecord, ParsedFile, digest, parse_file, path_id

SCHEMA_VERSION: Final = 1
BATCH_RECORDS: Final = 128  # agent-selected, frozen by the pilot; the route's own limit is 256
BATCH_BYTES: Final = 700_000
# A batch costs its longest text, so real code embeds about twice as fast grouped by length (the pilot's sample). The window bounds how far
# order can move and how much work a cancel can waste; the wire order never changes, because a file record must follow its symbols.
EMBED_BATCH: Final = 16
EMBED_WINDOW: Final = 128
PUBLISH_SECONDS: Final = 15.0
LEASE_MS: Final = 60_000
RENEW_SECONDS: Final = 15.0
_CATALOGUE_PAGE: Final = 256


class StorageUnavailableError(RuntimeError):
    """The storage port cannot be reached right now. Pauses the worker."""


class StorageRefusedError(RuntimeError):
    """The storage port refused with a stable code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class IndexStorage(Protocol):
    def call(self, op: str, **fields: Any) -> dict[str, Any]: ...


class Embedder(Protocol):
    identity: str
    dimensions: int

    def embed(self, texts: Sequence[str]) -> list[bytes]: ...


@dataclass(frozen=True)
class SourceFile:
    path: str
    modified: int | None = None


class IndexSource(Protocol):
    """The host's authorized view of one workspace. `read` returns None when policy no longer admits the file."""

    def files(self) -> Iterable[SourceFile]: ...

    def read(self, path: str) -> bytes | None: ...

    def revision(self) -> tuple[str, bool]: ...


@dataclass
class Coverage:
    files_total: int = 0
    files_indexed: int = 0
    records: int = 0
    unsupported: int = 0
    excluded: int = 0
    parsed_loc: dict[str, int] = field(default_factory=dict)

    def report(self, *, complete: bool) -> dict[str, Any]:
        return {"complete": complete, "files_indexed": self.files_indexed, "files_total": self.files_total, "records": self.records,
                "unsupported": self.unsupported, "excluded": self.excluded, "parsed_loc": dict(self.parsed_loc)}


@dataclass(frozen=True)
class WorkerOutcome:
    state: str  # "complete", "cancelled", "paused", "held" or "refused"
    detail: str = ""
    epoch: int | None = None
    files_written: int = 0
    records_written: int = 0
    coverage: dict[str, Any] | None = None


class _Cancelled(Exception):
    """A cancel arrived between embedding batches."""

    def __init__(self, window: list[IndexRecord]) -> None:
        super().__init__("cancelled")
        self.window = window


@dataclass
class _Batch:
    records: list[dict[str, Any]] = field(default_factory=list)
    removals: list[dict[str, str]] = field(default_factory=list)
    size: int = 0


class IndexWorker:
    def __init__(self, source: IndexSource, storage: IndexStorage, embedder: Embedder, *, owner: str, cold_admission: bool = True,
                 priority: Callable[[], Sequence[str]] = tuple, foreground_busy: Callable[[], bool] = lambda: False,
                 pause: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> None:
        self._source = source
        self._storage = storage
        self._embedder = embedder
        self._owner = owner
        self._cold_admission = cold_admission
        self._priority = priority
        self._foreground_busy = foreground_busy
        self._pause = pause
        self._clock = clock
        self._token = 0
        self._cold_token: int | None = None
        self._epoch = 0
        self._cancel = threading.Event()
        self._heartbeat_stop = threading.Event()
        self._heartbeat: threading.Thread | None = None
        self._lease_lost = False
        self._published_at = 0.0
        self._published_any = False
        self._coverage = Coverage()
        self._revision = ("0" * 64, False)
        self._files_written = 0
        self._records_written = 0

    def run(self, cancel: threading.Event) -> WorkerOutcome:
        self._cancel = cancel
        try:
            return self._run(cancel)
        except _Cancelled:
            return WorkerOutcome("cancelled", "", self._epoch or None, self._files_written, self._records_written)
        except StorageUnavailableError as exc:
            return WorkerOutcome("paused", str(exc), self._epoch or None, self._files_written, self._records_written)
        except StorageRefusedError as exc:
            state = "held" if exc.code in {"LEASE_HELD", "LEASE_LOST"} else "refused"
            return WorkerOutcome(state, exc.code, self._epoch or None, self._files_written, self._records_written)
        finally:
            self._release()

    def _beat(self) -> None:
        """The lease means this process is alive, however long one file's parse or embedding takes. A brief outage is tried again; a
        lease that is gone, including the machine's cold slot, which no write is fenced by, stops the worker at its next step."""
        while not self._heartbeat_stop.wait(RENEW_SECONDS):
            try:
                self._storage.call("lease", action="renew", owner=self._owner, ttl_ms=LEASE_MS, kind="scope", token=self._token)
                if self._cold_token:
                    self._storage.call("lease", action="renew", owner=self._owner, ttl_ms=LEASE_MS, kind="cold", token=self._cold_token)
            except StorageUnavailableError:
                continue
            except StorageRefusedError:
                self._lease_lost = True
                return

    def _release(self) -> None:
        self._heartbeat_stop.set()
        if self._heartbeat is not None:
            self._heartbeat.join(5)
        for kind, token in (("scope", self._token), ("cold", self._cold_token)):
            if token:
                try:
                    self._storage.call("lease", action="release", owner=self._owner, kind=kind, token=token)
                except (StorageUnavailableError, StorageRefusedError):
                    pass  # it expires on its own
        self._token, self._cold_token = 0, None

    def _run(self, cancel: threading.Event) -> WorkerOutcome:
        opened = self._storage.call("generation", action="open", embedding=self._embedder.identity, dimensions=self._embedder.dimensions,
                                    schema_version=SCHEMA_VERSION)
        current = opened.get("current")
        self._published_any = current is not None
        self._token = self._storage.call("lease", action="acquire", owner=self._owner, ttl_ms=LEASE_MS, kind="scope")["token"]
        # The first file is published at once, so only a complete publication means the cold build is over.
        if self._cold_admission and not (current and current["coverage"].get("complete")):
            self._cold_token = self._storage.call("lease", action="acquire", owner=self._owner, ttl_ms=LEASE_MS, kind="cold")["token"]
        self._heartbeat = threading.Thread(target=self._beat, name="index-lease", daemon=True)
        self._heartbeat.start()
        self._published_at = self._clock()
        self._revision = self._source.revision()
        self._epoch = self._storage.call("generation", action="begin", token=self._token)["epoch"]
        self._progress("catalogue")
        held = self._load_catalogue()
        self._coverage = Coverage()
        wanted = self._ordered_files()
        self._coverage.files_total = len(wanted)
        batch = _Batch()
        pending: list[IndexRecord] = []
        self._progress("embedding")
        seen: set[str] = set()
        contents: dict[str, str | None] = {}
        for source_file in wanted:
            identity = path_id(source_file.path)
            seen.add(identity)
            if cancel.is_set():
                return WorkerOutcome("cancelled", "", self._epoch, self._files_written, self._records_written)
            self._yield_to_foreground(cancel)
            data = self._source.read(source_file.path)
            contents[source_file.path] = None if data is None else digest(data)
            if data is None:  # the policy changed since listing
                self._coverage.files_total -= 1
                self._coverage.excluded += 1
                seen.discard(identity)
                continue
            parsed = parse_file(source_file.path, data, modified=source_file.modified)
            self._count(parsed)
            known = held.get(identity)
            if known == parsed.file_hash:
                self._coverage.files_indexed += 1
                self._coverage.records += len(parsed.records)
                continue
            # Always named for removal: a crash may have left part of this file in the building epoch, with no file record to show it.
            # The file record goes last, so one that exists proves the whole file arrived and a resume can skip it.
            batch.removals.append({"path_id": identity, "keep_hash": parsed.file_hash})
            pending.extend((*parsed.records[1:], parsed.records[0]))
            self._coverage.files_indexed += 1
            self._coverage.records += len(parsed.records)
            self._files_written += 1
            self._flush(pending, batch)
            if not self._published_any or self._clock() - self._published_at >= PUBLISH_SECONDS:
                self._flush(pending, batch, force=True)
                self._publish(complete=False)
                self._epoch = self._storage.call("generation", action="begin", token=self._token)["epoch"]
        for identity in sorted(set(held) - seen):
            batch.removals.append({"path_id": identity})
            if len(batch.removals) >= BATCH_RECORDS:
                self._flush(pending, batch, force=True)
        self._flush(pending, batch, force=True)
        unchanged = self._source.revision() == self._revision and self._still_what_was_read(contents)
        current = self._publish(complete=unchanged)
        self._progress("idle")
        self._prune()
        return WorkerOutcome("complete" if unchanged else "paused", "" if unchanged else "the source changed during this pass", current,
                             self._files_written, self._records_written, self._coverage.report(complete=unchanged))

    def _still_what_was_read(self, contents: dict[str, str | None]) -> bool:
        """The final word on `complete`: the same files with the same bytes. A file's size and time can stay the same when its contents do not."""
        if {item.path for item in self._source.files()} != set(contents):
            return False
        for path, expected in contents.items():
            data = self._source.read(path)
            if (None if data is None else digest(data)) != expected:
                return False
        return True

    def _ordered_files(self) -> list[SourceFile]:
        """Open and named files first, then the catalogue order, so the first file a person cares about is the first published."""
        files = {item.path: item for item in self._source.files()}
        first = [files[path] for path in self._priority() if path in files]
        chosen = {item.path for item in first}
        return first + [files[path] for path in sorted(files) if path not in chosen]

    def _load_catalogue(self) -> dict[str, str]:
        held: dict[str, str] = {}
        cursor = None
        while True:
            page = self._storage.call("catalogue", epoch=self._epoch, limit=_CATALOGUE_PAGE, **({} if cursor is None else {"cursor": cursor}))
            for item in page["files"]:
                held[item["path_id"]] = item["file_hash"]
            for identity in page.get("unfinished", ()):  # no hash matches this, so it is redone if still wanted and removed if not
                held[identity] = ""
            cursor = page.get("cursor")
            if cursor is None:
                return held

    def _count(self, parsed: ParsedFile) -> None:
        if parsed.language == "unsupported":
            self._coverage.unsupported += 1
        elif parsed.parsed_lines:
            self._coverage.parsed_loc[parsed.language] = self._coverage.parsed_loc.get(parsed.language, 0) + parsed.parsed_lines

    def _flush(self, pending: list[IndexRecord], batch: _Batch, *, force: bool = False) -> None:
        while pending and (force or len(pending) >= EMBED_WINDOW):
            window, pending[:] = pending[:EMBED_WINDOW], pending[EMBED_WINDOW:]
            self._embed_into(window, batch)
        if batch.records or batch.removals:
            if force or len(batch.records) >= BATCH_RECORDS or batch.size >= BATCH_BYTES:
                self._send(batch)

    def _embed_into(self, window: list[IndexRecord], batch: _Batch) -> None:
        wanting = sorted((index for index, record in enumerate(window) if record.embed_text), key=lambda index: len(window[index].embed_text or ""))
        vectors: dict[int, bytes] = {}
        for start in range(0, len(wanting), EMBED_BATCH):
            group = wanting[start:start + EMBED_BATCH]
            if self._cancel.is_set():
                # Nothing of this window was sent, so a resume redoes it whole and no file looks finished.
                pending_again = window
                raise _Cancelled(pending_again)
            self._yield_to_foreground(self._cancel)
            vectors.update(zip(group, self._embedder.embed([window[index].embed_text or "" for index in group]), strict=True))
        for index, record in enumerate(window):
            wire = record.wire()
            if index in vectors:
                wire["vector"] = base64.b64encode(vectors[index]).decode("ascii")
            size = sum(len(str(value)) for value in wire.values()) + 128
            if batch.records and (len(batch.records) >= BATCH_RECORDS or batch.size + size >= BATCH_BYTES):
                self._send(batch)
            batch.records.append(wire)
            batch.size += size

    def _send(self, batch: _Batch) -> None:
        self._storage.call("batch", token=self._token, epoch=self._epoch, records=batch.records, removals=batch.removals)
        self._records_written += len(batch.records)
        batch.records, batch.removals, batch.size = [], [], 0
        self._progress("embedding")

    def _publish(self, *, complete: bool) -> int:
        revision, dirty = self._revision
        result = self._storage.call("generation", action="publish", token=self._token, epoch=self._epoch, revision=revision, dirty=dirty,
                                    coverage=self._coverage.report(complete=complete))
        self._published_any = True
        self._published_at = self._clock()
        epoch: int = result["current"]["epoch"]
        return epoch

    def _progress(self, phase: str) -> None:
        value = {"phase": phase, "counts": {"files_indexed": self._coverage.files_indexed, "files_total": self._coverage.files_total}}
        self._storage.call("cursor", action="set", token=self._token, value=value)

    def _prune(self) -> None:
        cursor = None
        while True:
            step = self._storage.call("cleanup", token=self._token, action="prune", **({} if cursor is None else {"cursor": cursor}))
            cursor = step.get("cursor")
            if cursor is None:
                return

    def _yield_to_foreground(self, cancel: threading.Event) -> None:
        """Cooperative: while the person's turn is busy, wait in short steps. The heartbeat keeps the lease meanwhile."""
        if self._lease_lost:
            raise StorageRefusedError("LEASE_LOST")
        while self._foreground_busy() and not cancel.is_set():
            self._pause(0.05)
