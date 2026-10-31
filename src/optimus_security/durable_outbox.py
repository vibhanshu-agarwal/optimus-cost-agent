"""Fsynced, append-only outbox streams (Plan 12.8 Task 1; memory design v4 section 7; ADR-032). Neutral mechanics shared
by the ACP host and the Gateway: framing, locking, fsync, verified-prefix recovery, gaps, acknowledgements and
compaction. No accounting types or debit logic live here.

Layout under the injected root: one directory per stream, ``<root>/<stream_id>/``, holding ``stream.lock`` (held by
its one writer for the writer's lifetime), ``seg-NNNNNN.log`` segments and an append-only ``ack.log``. A new writer
always starts a new stream, so nothing is ever appended behind another process's tail.

A record is one line, ``<sha256 hex> <canonical JSON>\\n``. The JSON carries the stream, a strictly increasing
sequence, an event UUID, the schema version, the previous record's digest and the payload; the digest covers the
JSON bytes, so a record proves its own bytes and its place in the chain. A record is confirmed only after flush and
fsync. After a failed write the segment is abandoned with whatever bytes it holds, and the next append opens a
successor segment whose first record is an explicit gap naming the unconfirmed sequences; a reader accepts a
discontinuity only when such a gap explains it.

Acknowledgements are appended, never replaced: the last verified ``ack.log`` line wins. That avoids relying on a
rename being written through, which Windows does not guarantee (the project registry's documented limit). Directory
entries are fsynced on POSIX; on Windows a new file's directory entry is NTFS metadata and is not separately flushed.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import queue
import sys
import threading
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

SCHEMA_VERSION = 1
SEGMENT_BYTES = 16 * 1024 * 1024  # agent-selected (Plan 12.8)
QUEUE_RECORDS = 1024  # agent-selected
ACK_WAIT_SECONDS = 0.25  # agent-selected
GENESIS = "0" * 64
GAP_KIND = "outbox.gap"
_LOCK_NAME = "stream.lock"
_ACK_NAME = "ack.log"
_SEGMENT_PREFIX = "seg-"
_SEGMENT_SUFFIX = ".log"
_CONTENTION_ERRNOS = frozenset({errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK, errno.EDEADLK})


class OutboxError(Exception):
    """``code``: LOCK_FAILED, LOCK_CONTENTION, WRITE_FAILED, CLOSED or INVALID; never carries a payload."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Record:
    stream_id: str
    sequence: int
    event_id: str
    prev: str
    digest: str
    payload: Mapping[str, Any]
    line: bytes


@dataclass(frozen=True)
class Damage:
    """A segment that did not verify to its end: ``reason`` is torn, checksum, malformed, chain, sequence or schema."""

    segment: str
    offset: int
    reason: str


@dataclass(frozen=True)
class SegmentScan:
    name: str
    first_sequence: int | None
    last_sequence: int | None


@dataclass(frozen=True)
class StreamScan:
    stream_id: str
    records: tuple[Record, ...]
    segments: tuple[SegmentScan, ...]
    damage: tuple[Damage, ...]

    @property
    def verified_sequence(self) -> int:
        return self.records[-1].sequence if self.records else 0

    @property
    def verified_digest(self) -> str:
        return self.records[-1].digest if self.records else GENESIS


def _canonical(document: Mapping[str, Any]) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def frame(stream_id: str, sequence: int, prev: str, payload: Mapping[str, Any], *, event_id: str | None = None) -> Record:
    body = _canonical(
        {"stream": stream_id, "seq": sequence, "event_id": event_id or uuid.uuid4().hex, "schema": SCHEMA_VERSION, "prev": prev, "payload": payload}
    )
    digest = hashlib.sha256(body).hexdigest()
    document = json.loads(body)
    return Record(stream_id, sequence, document["event_id"], prev, digest, document["payload"], digest.encode("ascii") + b" " + body + b"\n")


def parse_line(line: bytes) -> Record:
    """One framed line (with its newline) or ``ValueError`` naming why it does not verify."""
    if not line.endswith(b"\n"):
        raise ValueError("torn")
    digest, sep, body = line[:-1].partition(b" ")
    if not sep or len(digest) != 64:
        raise ValueError("malformed")
    if hashlib.sha256(body).hexdigest().encode("ascii") != digest:
        raise ValueError("checksum")
    try:
        document = json.loads(body)
    except ValueError:
        raise ValueError("malformed") from None
    if not isinstance(document, dict) or document.get("schema") != SCHEMA_VERSION:
        raise ValueError("schema")
    sequence, payload = document.get("seq"), document.get("payload")
    if type(sequence) is not int or sequence < 1 or not isinstance(payload, dict):
        raise ValueError("malformed")
    if not all(isinstance(document.get(key), str) for key in ("stream", "event_id", "prev")):
        raise ValueError("malformed")
    return Record(document["stream"], sequence, document["event_id"], document["prev"], digest.decode("ascii"), payload, line)


def _segment_names(stream_dir: Path) -> list[str]:
    return sorted(
        entry.name
        for entry in stream_dir.iterdir()
        if entry.name.startswith(_SEGMENT_PREFIX) and entry.name.endswith(_SEGMENT_SUFFIX) and entry.is_file()
    )


def scan_stream(stream_dir: Path) -> StreamScan:
    """Every verified record of a stream, in order, plus where verification stopped.

    A damaged segment contributes its verified prefix. A gap record opens each successor segment the writer started
    after a failure: it retracts the sequences it names (bytes that landed although their fsync failed are still
    unconfirmed) and must chain to the last record before them. A segment that follows damage without such a gap, or
    any other break in sequence or chain, ends the scan: later bytes cannot be placed in the stream. A compacted stream
    starts at its first remaining record, which must lie within the acknowledged prefix plus one."""
    stream_id = stream_dir.name
    ack = read_ack(stream_dir)
    acked = ack.get("sequence") if ack else None
    compacted_limit = acked + 1 if type(acked) is int and acked > 0 else 1
    placed: list[tuple[str, Record]] = []
    damage: list[Damage] = []
    names = _segment_names(stream_dir)
    after_damage = False
    for name in names:
        data = (stream_dir / name).read_bytes()
        offset = 0
        while offset < len(data):
            end = data.find(b"\n", offset)
            line = data[offset:] if end < 0 else data[offset : end + 1]
            try:
                record = parse_line(line)
            except ValueError as exc:
                damage.append(Damage(name, offset, str(exc)))
                after_damage = True
                break
            reason = _place(record, stream_id, placed, opens_segment=offset == 0, after_damage=after_damage,
                            compacted_limit=compacted_limit)
            if reason:
                damage.append(Damage(name, offset, reason))
                return _scan(stream_id, names, placed, damage)
            after_damage = False
            placed.append((name, record))
            offset += len(line)
    return _scan(stream_id, names, placed, damage)


def _place(record: Record, stream_id: str, placed: list[tuple[str, Record]], *, opens_segment: bool, after_damage: bool,
           compacted_limit: int = 1) -> str:
    """Why ``record`` cannot follow ``placed`` (an empty string when it can); a gap truncates ``placed`` in place."""
    if record.stream_id != stream_id:
        return "stream"
    if record.payload.get("kind") == GAP_KIND:
        first, last = record.payload.get("unconfirmed_from"), record.payload.get("unconfirmed_to")
        if not (opens_segment and type(first) is int and type(last) is int and 1 <= first <= last + 1 and record.sequence == last + 1):
            return "sequence"
        if placed and placed[-1][1].sequence >= first:
            del placed[next(i for i, (_, item) in enumerate(placed) if item.sequence >= first) :]
        base_seq, base_digest = (placed[-1][1].sequence, placed[-1][1].digest) if placed else (0, GENESIS)
        if base_seq != first - 1:
            return "sequence"
        return "" if record.prev == base_digest else "chain"
    if after_damage:
        return "sequence"  # a successor of a damaged segment must open with the gap that explains it
    if not placed and 1 < record.sequence <= compacted_limit:
        return ""  # its acknowledged predecessors were compacted away
    base_seq, base_digest = (placed[-1][1].sequence, placed[-1][1].digest) if placed else (0, GENESIS)
    if record.sequence != base_seq + 1:
        return "sequence"
    return "" if record.prev == base_digest else "chain"


def follows(record: Record, base_sequence: int, base_digest: str) -> str:
    """Why an already verified record cannot directly follow a committed prefix ending at ``base_sequence`` /
    ``base_digest`` (an empty string when it can). The ledger uses this: a gap reaching it may only explain sequences
    after that prefix, never retract a committed record."""
    if record.payload.get("kind") == GAP_KIND:
        first, last = record.payload.get("unconfirmed_from"), record.payload.get("unconfirmed_to")
        if not (type(first) is int and type(last) is int and first == base_sequence + 1 and first <= last + 1 and record.sequence == last + 1):
            return "sequence"
    elif record.sequence != base_sequence + 1:
        return "sequence"
    return "" if record.prev == base_digest else "chain"


def _scan(stream_id: str, names: list[str], placed: list[tuple[str, Record]], damage: list[Damage]) -> StreamScan:
    segments = []
    for name in names:
        sequences = [record.sequence for segment, record in placed if segment == name]
        segments.append(SegmentScan(name, sequences[0] if sequences else None, sequences[-1] if sequences else None))
    return StreamScan(stream_id, tuple(record for _, record in placed), tuple(segments), tuple(damage))


def _lock(handle: BinaryIO) -> None:
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(handle: BinaryIO) -> None:
    if sys.platform == "win32":
        import msvcrt

        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    handle.close()


def claim(stream_dir: Path) -> BinaryIO | None:
    """The stream's lock if no live writer holds it (the writer ended or died), else None. The caller owns the
    returned handle and releases it with ``release``."""
    try:
        handle = open(stream_dir / _LOCK_NAME, "a+b")  # noqa: SIM115
    except OSError as exc:
        raise OutboxError("LOCK_FAILED", f"cannot open a stream lock (errno {exc.errno})") from None
    try:
        handle.seek(0)
        _lock(handle)
    except OSError as exc:
        handle.close()
        if exc.errno in _CONTENTION_ERRNOS:
            return None
        raise OutboxError("LOCK_FAILED", f"cannot lock a stream (errno {exc.errno})") from None
    return handle


def release(handle: BinaryIO) -> None:
    _unlock(handle)


def _fsync_directory(directory: Path) -> None:
    if sys.platform == "win32":
        return  # see the module docstring's Windows metadata limit
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _append_durably(path: Path, data: bytes) -> None:
    with open(path, "ab") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


class StreamWriter:
    """The one writer of one new stream. Not thread-safe: ``OutboxWriter`` serializes it on its own thread."""

    def __init__(self, root: Path, *, segment_bytes: int = SEGMENT_BYTES) -> None:
        self.stream_id = uuid.uuid4().hex
        self.directory = root / self.stream_id
        self._segment_bytes = segment_bytes
        self._lock_handle: BinaryIO | None = None
        self._segment: BinaryIO | None = None
        self._segment_index = 0
        self._segment_size = 0
        self._next_seq = 1
        self._prev = GENESIS
        self._confirmed = 0
        self._broken_from: int | None = None
        self._closed = False

    @property
    def confirmed_sequence(self) -> int:
        return self._confirmed

    def _open(self) -> None:
        try:
            self.directory.mkdir(parents=True, exist_ok=False)
            _fsync_directory(self.directory.parent)
        except OSError as exc:
            raise OutboxError("WRITE_FAILED", f"cannot create the stream directory (errno {exc.errno})") from None
        handle = claim(self.directory)
        if handle is None:
            raise OutboxError("LOCK_CONTENTION", "a fresh stream is already locked")
        self._lock_handle = handle

    def _roll(self) -> None:
        if self._segment is not None:
            self._segment.close()
        self._segment_index += 1
        path = self.directory / f"{_SEGMENT_PREFIX}{self._segment_index:06d}{_SEGMENT_SUFFIX}"
        try:
            self._segment = open(path, "xb")  # noqa: SIM115
            _fsync_directory(self.directory)
        except OSError as exc:
            self._segment = None
            raise OutboxError("WRITE_FAILED", f"cannot open a segment (errno {exc.errno})") from None
        self._segment_size = 0

    def append(self, payload: Mapping[str, Any], *, event_id: str | None = None) -> Record:
        """Append and fsync one record; returns it once durable. On failure the record is unconfirmed, the segment is
        abandoned and the next append starts a successor segment with a gap record."""
        if self._closed:
            raise OutboxError("CLOSED", "the stream writer is closed")
        if self._lock_handle is None:
            self._open()
        if self._broken_from is not None:
            gap = {"kind": GAP_KIND, "unconfirmed_from": self._broken_from, "unconfirmed_to": self._next_seq - 1}
            self._abandon_segment()  # keep the damaged segment's bytes as they are
            self._write(gap, None, force_roll=True)
            self._broken_from = None
        return self._write(payload, event_id, force_roll=False)

    def _write(self, payload: Mapping[str, Any], event_id: str | None, *, force_roll: bool) -> Record:
        record = frame(self.stream_id, self._next_seq, self._prev, payload, event_id=event_id)
        self._next_seq += 1  # a sequence is consumed even if its write fails; a gap record explains it
        try:
            if force_roll or self._segment is None or (self._segment_size and self._segment_size + len(record.line) > self._segment_bytes):
                self._roll()
            assert self._segment is not None
            self._segment.write(record.line)
            self._segment.flush()
            os.fsync(self._segment.fileno())
        except (OSError, OutboxError) as exc:
            if self._broken_from is None:
                self._broken_from = record.sequence
            errno_value = getattr(exc, "errno", None)
            raise OutboxError("WRITE_FAILED", f"a record was not confirmed (errno {errno_value})") from None
        self._segment_size += len(record.line)
        self._prev = record.digest
        self._confirmed = record.sequence
        return record

    def _abandon_segment(self) -> None:
        if self._segment is not None:
            try:
                self._segment.close()
            except OSError:
                pass  # its bytes stay as they are; the reader verifies them
            self._segment = None

    def close(self) -> None:
        self._closed = True
        self._abandon_segment()
        if self._lock_handle is not None:
            release(self._lock_handle)
            self._lock_handle = None


def read_ack(stream_dir: Path) -> Mapping[str, Any] | None:
    """The last verified acknowledgement, or None. A torn or corrupt trailing line is ignored, never trusted."""
    path = stream_dir / _ACK_NAME
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    latest: Mapping[str, Any] | None = None
    for raw in data.splitlines(keepends=True):
        try:
            latest = parse_line(raw).payload
        except ValueError:
            continue
    return latest


def write_ack(stream_dir: Path, ack: Mapping[str, Any]) -> None:
    """Durably append one acknowledgement (ledger instance, sequence, digest) before any compaction relies on it."""
    record = frame(stream_dir.name, 1, GENESIS, ack)
    try:
        _append_durably(stream_dir / _ACK_NAME, record.line)
    except OSError as exc:
        raise OutboxError("WRITE_FAILED", f"an acknowledgement was not recorded (errno {exc.errno})") from None


def compact(stream_dir: Path, scan: StreamScan, acked_sequence: int, *, active_segment: str | None) -> list[str]:
    """Delete closed segments whose every verified record is acknowledged; never the active segment, never a segment
    holding unverified bytes. Returns the deleted names."""
    damaged = {item.segment for item in scan.damage}
    deleted: list[str] = []
    for segment in scan.segments:
        if segment.name == active_segment or segment.name in damaged:
            continue
        if segment.last_sequence is None or segment.last_sequence > acked_sequence:
            break  # acknowledgement is a contiguous prefix: nothing later can be fully acknowledged
        (stream_dir / segment.name).unlink(missing_ok=True)
        deleted.append(segment.name)
    if deleted:
        _fsync_directory(stream_dir)
    return deleted


def stream_dirs(root: Path) -> Iterator[Path]:
    try:
        entries = sorted(root.iterdir())
    except FileNotFoundError:
        return
    for entry in entries:
        if entry.is_dir() and len(entry.name) == 32:
            yield entry


@dataclass
class Ticket:
    """One submitted record. ``wait`` returns True only once it is durable; a record confirmed after the caller stopped
    waiting stays unconfirmed for that caller's purpose."""

    _event: threading.Event = field(default_factory=threading.Event)
    record: Record | None = None
    failure: str | None = None

    def wait(self, timeout: float) -> bool:
        return self._event.wait(timeout) and self.record is not None

    def _resolve(self, record: Record | None, failure: str | None) -> None:
        self.record, self.failure = record, failure
        self._event.set()


@dataclass
class WriterStats:
    confirmed_sequence: int = 0
    pending: int = 0
    rejected_full: int = 0
    write_failures: int = 0
    last_failure: str | None = None


class OutboxWriter:
    """One owned writer thread per process and stream, with bounded admission. ``submit`` never blocks: a full queue
    or a closed writer returns an already failed ticket. Nothing touches the filesystem until the first record."""

    def __init__(self, root: Path, *, queue_records: int = QUEUE_RECORDS, segment_bytes: int = SEGMENT_BYTES,
                 on_failure: Callable[[str], None] | None = None) -> None:
        self._writer = StreamWriter(root, segment_bytes=segment_bytes)
        self._queue: queue.Queue[tuple[Mapping[str, Any], str | None, Ticket] | None] = queue.Queue(maxsize=queue_records)
        self._stats = WriterStats()
        self._stats_lock = threading.Lock()
        self._on_failure = on_failure
        self._thread: threading.Thread | None = None
        self._start_lock = threading.Lock()
        self._closed = False

    @property
    def stream_id(self) -> str:
        return self._writer.stream_id

    @property
    def directory(self) -> Path:
        return self._writer.directory

    def stats(self) -> WriterStats:
        with self._stats_lock:
            return WriterStats(**vars(self._stats))

    def submit(self, payload: Mapping[str, Any], *, event_id: str | None = None) -> Ticket:
        ticket = Ticket()
        if self._closed:
            ticket._resolve(None, "CLOSED")
            return ticket
        self._ensure_thread()
        try:
            self._queue.put_nowait((payload, event_id, ticket))
        except queue.Full:
            with self._stats_lock:
                self._stats.rejected_full += 1
                self._stats.last_failure = "QUEUE_FULL"
            ticket._resolve(None, "QUEUE_FULL")
            return ticket
        with self._stats_lock:
            self._stats.pending += 1
        return ticket

    def _ensure_thread(self) -> None:
        with self._start_lock:
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name=f"outbox-{self._writer.stream_id[:8]}", daemon=True)
                self._thread.start()

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            payload, event_id, ticket = item
            try:
                record = self._writer.append(payload, event_id=event_id)
            except OutboxError as exc:
                with self._stats_lock:
                    self._stats.pending -= 1
                    self._stats.write_failures += 1
                    self._stats.last_failure = exc.code
                ticket._resolve(None, exc.code)
                if self._on_failure is not None:
                    self._on_failure(exc.code)
                continue
            with self._stats_lock:
                self._stats.pending -= 1
                self._stats.confirmed_sequence = record.sequence
            ticket._resolve(record, None)

    def close(self, timeout: float = 5.0) -> None:
        """Stop admitting, write what is queued within ``timeout``, then release the stream."""
        self._closed = True
        thread = self._thread
        if thread is not None:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    self._queue.put(None, timeout=max(0.0, deadline - time.monotonic()))
                    break
                except queue.Full:
                    if time.monotonic() >= deadline:
                        break
            thread.join(max(0.0, deadline - time.monotonic()))
            if thread.is_alive():
                return  # a blocked write keeps its lock; the stream is recovered as orphaned on a later start
        self._writer.close()
