"""Fsynced, append-only outbox streams (Plan 12.8 Task 1; memory design v4 section 7; ADR-032). Neutral mechanics shared
by the ACP host and the Gateway: framing, locking, fsync, verified-prefix recovery, gaps, acknowledgements and
compaction. No accounting types or debit logic live here.

Layout under the injected root: one directory per stream, ``<root>/<stream_id>/``, holding ``stream.lock`` (held by
its one writer for the writer's lifetime), ``seg-NNNNNN.log`` segments and an append-only ``ack.log``. A new writer
always starts a new stream, so nothing is ever appended behind another process's tail.

A record is one line, ``<sha256 hex> <canonical JSON>\\n``. The JSON carries exactly the stream, a strictly increasing
sequence, an event UUID, the schema version, the previous record's digest and the payload; the digest covers the JSON
bytes, so a record proves its own bytes and its place in the chain. A record is confirmed only after flush and fsync.
After a failed write the segment is abandoned with whatever bytes it holds, and the next append opens a successor
segment whose first record is an explicit gap naming the unconfirmed sequences; a reader retracts them and accepts a
discontinuity only when such a gap explains it.

What a reader may trust: the writer appends record k+1 only after k's fsync returned, and after a failure it appends a
gap first, so every record followed by another is settled. Only a stream's last record can have landed without a
confirmed fsync. A live writer's own drain stops at its confirmed sequence; for an orphaned stream (its writer died)
the last record is an unverified tail unless it is the writer's orderly ``stream.end``.

Acknowledgements are appended, never replaced: the last verified ``ack.log`` line wins. That avoids relying on a
rename being written through, which Windows does not guarantee (the project registry's documented limit). An
acknowledgement must name a record this stream holds, and compaction deletes only closed segments within the stored
acknowledgement of the expected ledger instance. The acknowledgement also anchors a compacted stream's first record.
Directory entries are fsynced on POSIX; on Windows a new file's directory entry is NTFS metadata and is not
separately flushed.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import queue
import re
import sys
import threading
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

SCHEMA_VERSION = 1
SEGMENT_BYTES = 16 * 1024 * 1024  # agent-selected (Plan 12.8)
MAX_RECORD_BYTES = 256 * 1024  # agent-selected: any one record always fits in one upload batch
QUEUE_RECORDS = 1024  # agent-selected
ACK_WAIT_SECONDS = 0.25  # agent-selected
GENESIS = "0" * 64
GAP_KIND = "outbox.gap"
STREAM_END_KIND = "stream.end"
_LOCK_NAME = "stream.lock"
_ACK_NAME = "ack.log"
_SEGMENT_PREFIX = "seg-"
_SEGMENT_SUFFIX = ".log"
_CONTENTION_ERRNOS = frozenset({errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK, errno.EDEADLK})
_FRAME_KEYS = frozenset({"stream", "seq", "event_id", "schema", "prev", "payload"})
_HEX32 = re.compile(r"[0-9a-f]{32}")
_HEX64 = re.compile(r"[0-9a-f]{64}")


class OutboxError(Exception):
    """``code``: LOCK_FAILED, LOCK_CONTENTION, WRITE_FAILED, CLOSED, TOO_LARGE or INVALID; never carries a payload."""

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
    """Where verification stopped: ``reason`` is torn, checksum, malformed, schema, stream, chain, sequence or anchor."""

    segment: str
    offset: int
    reason: str


@dataclass(frozen=True)
class SegmentScan:
    name: str
    first_sequence: int | None
    last_sequence: int | None


@dataclass(frozen=True)
class Ack:
    """A stored acknowledgement: the ledger instance committed this stream through ``sequence`` / ``digest``."""

    ledger_instance: str
    stream_id: str
    sequence: int
    digest: str


@dataclass(frozen=True)
class StreamScan:
    stream_id: str
    records: tuple[Record, ...]
    segments: tuple[SegmentScan, ...]
    damage: tuple[Damage, ...]
    unverified_tail: Record | None = None
    tail_segment: str | None = None

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
    """One framed line (with its newline) or ``ValueError`` naming why it does not verify. The frame carries exactly
    its six fields; payload content is the capture contract's to validate."""
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
    if set(document) != _FRAME_KEYS:
        raise ValueError("malformed")
    stream, sequence, event_id, prev, payload = (document[k] for k in ("stream", "seq", "event_id", "prev", "payload"))
    if type(sequence) is not int or sequence < 1 or not isinstance(payload, dict):
        raise ValueError("malformed")
    if not (isinstance(stream, str) and _HEX32.fullmatch(stream) and isinstance(event_id, str) and _HEX32.fullmatch(event_id)):
        raise ValueError("malformed")
    if not (isinstance(prev, str) and _HEX64.fullmatch(prev)):
        raise ValueError("malformed")
    return Record(stream, sequence, event_id, prev, digest.decode("ascii"), payload, line)


def _segment_names(stream_dir: Path) -> list[str]:
    return sorted(
        entry.name
        for entry in stream_dir.iterdir()
        if entry.name.startswith(_SEGMENT_PREFIX) and entry.name.endswith(_SEGMENT_SUFFIX) and entry.is_file()
    )


def scan_stream(stream_dir: Path, *, orphan: bool = False) -> StreamScan:
    """Every verified record of a stream, in order, plus where verification stopped.

    A damaged segment contributes its verified prefix. A gap record opens each successor segment the writer started
    after a failure: it retracts the sequences it names (bytes that landed although their fsync failed are still
    unconfirmed) and must chain to the last record before them. A segment that follows damage without such a gap, or
    any other break in sequence or chain, ends the scan. A compacted stream's first record is anchored by the stored
    acknowledgement. With ``orphan`` (the writer died), the last record is withheld as ``unverified_tail`` unless it is
    the orderly stream end; a withheld gap's retraction still applies."""
    stream_id = stream_dir.name
    ack = read_ack(stream_dir)
    placed: list[tuple[str, Record]] = []
    damage: list[Damage] = []
    names = _segment_names(stream_dir)
    after_damage = False
    stopped = False
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
            reason = _place(record, stream_id, placed, opens_segment=offset == 0, after_damage=after_damage, ack=ack)
            if reason:
                damage.append(Damage(name, offset, reason))
                stopped = True
                break
            after_damage = False
            placed.append((name, record))
            offset += len(line)
        if stopped:
            break
    if ack is not None and placed and placed[0][1].sequence <= ack.sequence:
        anchored = [record for _, record in placed if record.sequence == ack.sequence]
        if not anchored or anchored[0].digest != ack.digest:
            damage.append(Damage(placed[0][0], 0, "anchor"))
            placed = []
    tail: tuple[str, Record] | None = None
    if orphan and placed and placed[-1][1].payload.get("kind") != STREAM_END_KIND:
        last = placed[-1][1]
        if ack is None or (last.sequence, last.digest) != (ack.sequence, ack.digest):
            tail = placed.pop()  # an acknowledged last record was committed, so it is settled
    return _scan(stream_id, names, placed, damage, tail)


def _base(placed: list[tuple[str, Record]]) -> tuple[int, str]:
    return (placed[-1][1].sequence, placed[-1][1].digest) if placed else (0, GENESIS)


def _place(record: Record, stream_id: str, placed: list[tuple[str, Record]], *, opens_segment: bool, after_damage: bool,
           ack: Ack | None) -> str:
    """Why ``record`` cannot follow ``placed`` (an empty string when it can). A valid gap truncates ``placed`` in
    place; an invalid one changes nothing."""
    if record.stream_id != stream_id:
        return "stream"
    is_gap = record.payload.get("kind") == GAP_KIND
    if is_gap:
        first, last = record.payload.get("unconfirmed_from"), record.payload.get("unconfirmed_to")
        if not (opens_segment and type(first) is int and type(last) is int and 1 <= first <= last + 1 and record.sequence == last + 1):
            return "sequence"
        keep = next((i for i, (_, item) in enumerate(placed) if item.sequence >= first), len(placed))
        kept = placed[:keep]
        if kept or first == 1:
            base_seq, base_digest = _base(kept)
            if base_seq != first - 1:
                return "sequence"
            if record.prev != base_digest:
                return "chain"
        elif not _compacted_start(record, first - 1, ack):
            return "sequence"
        del placed[keep:]
        return ""
    if after_damage:
        return "sequence"  # a successor of a damaged segment must open with the gap that explains it
    if not placed and record.sequence != 1:
        return "" if _compacted_start(record, record.sequence - 1, ack) else "sequence"
    base_seq, base_digest = _base(placed)
    if record.sequence != base_seq + 1:
        return "sequence"
    return "" if record.prev == base_digest else "chain"


def _compacted_start(record: Record, predecessor: int, ack: Ack | None) -> bool:
    """A first remaining record whose predecessors were acknowledged and compacted away. At the boundary it must chain
    to the acknowledgement; inside the acknowledged prefix the anchor check in ``scan_stream`` verifies it."""
    if ack is None or predecessor > ack.sequence:
        return False
    return predecessor < ack.sequence or record.prev == ack.digest


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


def _scan(stream_id: str, names: list[str], placed: list[tuple[str, Record]], damage: list[Damage],
          tail: tuple[str, Record] | None) -> StreamScan:
    segments = []
    for name in names:
        sequences = [record.sequence for segment, record in placed if segment == name]
        segments.append(SegmentScan(name, sequences[0] if sequences else None, sequences[-1] if sequences else None))
    return StreamScan(stream_id, tuple(record for _, record in placed), tuple(segments), tuple(damage),
                      tail[1] if tail else None, tail[0] if tail else None)


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
        """Create and lock this writer's own directory. Retryable: the name is this writer's alone, so an earlier
        attempt that created the directory but failed to fsync or lock it is simply completed."""
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            _fsync_directory(self.directory.parent)
        except OSError as exc:
            raise OutboxError("WRITE_FAILED", f"cannot create the stream directory (errno {exc.errno})") from None
        handle = claim(self.directory)
        if handle is None:
            raise OutboxError("LOCK_CONTENTION", "this writer's stream is locked by another handle")
        self._lock_handle = handle

    def _roll(self) -> None:
        self._abandon_segment()
        self._segment_index += 1
        path = self.directory / f"{_SEGMENT_PREFIX}{self._segment_index:06d}{_SEGMENT_SUFFIX}"
        try:
            self._segment = open(path, "xb")  # noqa: SIM115
            _fsync_directory(self.directory)
        except OSError as exc:
            self._abandon_segment()
            raise OutboxError("WRITE_FAILED", f"cannot open a segment (errno {exc.errno})") from None
        self._segment_size = 0

    def append(self, payload: Mapping[str, Any], *, event_id: str | None = None) -> Record:
        """Append and fsync one record; returns it once durable. On failure the record is unconfirmed, the segment is
        abandoned and the next append starts a successor segment with a gap record. A record over
        ``MAX_RECORD_BYTES`` is refused before it consumes a sequence."""
        if self._closed:
            raise OutboxError("CLOSED", "the stream writer is closed")
        if self._lock_handle is None:
            self._open()
        if len(frame(self.stream_id, self._next_seq, self._prev, payload, event_id=event_id).line) > MAX_RECORD_BYTES:
            raise OutboxError("TOO_LARGE", "a record exceeds the per-record limit")
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
            self._abandon_segment()
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


def read_ack(stream_dir: Path) -> Ack | None:
    """The last verified acknowledgement for this stream, or None. A torn, corrupt or foreign line is never trusted."""
    try:
        data = (stream_dir / _ACK_NAME).read_bytes()
    except FileNotFoundError:
        return None
    latest: Ack | None = None
    for raw in data.splitlines(keepends=True):
        try:
            payload = parse_line(raw).payload
        except ValueError:
            continue
        ledger, stream, sequence, digest = (payload.get(k) for k in ("ledger_instance", "stream_id", "sequence", "digest"))
        if not (isinstance(ledger, str) and _HEX32.fullmatch(ledger) and stream == stream_dir.name):
            continue
        if type(sequence) is int and sequence >= 1 and isinstance(digest, str) and _HEX64.fullmatch(digest):
            latest = Ack(ledger, stream, sequence, digest)
    return latest


def write_ack(stream_dir: Path, scan: StreamScan, *, ledger_instance: str, sequence: int, digest: str) -> bool:
    """Durably append one acknowledgement before any compaction relies on it. It must name a record this stream holds,
    with that record's digest; one that does not advance past the stored acknowledgement is not written (False)."""
    if not (_HEX32.fullmatch(ledger_instance) and _HEX64.fullmatch(digest)) or type(sequence) is not int:
        raise OutboxError("INVALID", "an acknowledgement has a malformed field")
    if not _scan_of(stream_dir, scan):
        raise OutboxError("INVALID", "an acknowledgement needs this stream's own scan")
    if not any(record.sequence == sequence and record.digest == digest for record in scan.records):
        raise OutboxError("INVALID", "an acknowledgement names no record this stream holds")
    stored = read_ack(stream_dir)
    if stored is not None and sequence <= stored.sequence:
        return False
    payload = {"ledger_instance": ledger_instance, "stream_id": stream_dir.name, "sequence": sequence, "digest": digest}
    try:
        _append_durably(stream_dir / _ACK_NAME, frame(stream_dir.name, 1, GENESIS, payload).line)
    except OSError as exc:
        raise OutboxError("WRITE_FAILED", f"an acknowledgement was not recorded (errno {exc.errno})") from None
    return True


def compact(stream_dir: Path, scan: StreamScan, *, ledger_instance: str, active_segment: str | None) -> list[str]:
    """Delete closed segments whose every verified record lies within the stored acknowledgement of
    ``ledger_instance``; never the active segment, never a damaged one, never anything without that authority.
    Returns the deleted names."""
    if not _scan_of(stream_dir, scan):
        return []  # another stream's scan authorizes nothing here
    ack = read_ack(stream_dir)
    if ack is None or ack.ledger_instance != ledger_instance:
        return []
    if not any(record.sequence == ack.sequence and record.digest == ack.digest for record in scan.records):
        first = scan.records[0].sequence if scan.records else None
        if first is None or first <= ack.sequence:
            return []  # the stored acknowledgement does not match what this stream holds
    keep = {item.segment for item in scan.damage} | ({scan.tail_segment} if scan.tail_segment else set())
    deleted: list[str] = []
    for segment in scan.segments:
        if segment.name == active_segment or segment.name in keep:
            continue
        if segment.last_sequence is None or segment.last_sequence > ack.sequence:
            break  # acknowledgement is a contiguous prefix: nothing later can be fully acknowledged
        (stream_dir / segment.name).unlink(missing_ok=True)
        deleted.append(segment.name)
    if deleted:
        _fsync_directory(stream_dir)
    return deleted


def _scan_of(stream_dir: Path, scan: StreamScan) -> bool:
    """Whether ``scan`` is this stream's: its own identity and every record it holds."""
    records = (*scan.records, *((scan.unverified_tail,) if scan.unverified_tail else ()))
    return scan.stream_id == stream_dir.name and all(record.stream_id == stream_dir.name for record in records)


def stream_dirs(root: Path) -> Iterator[Path]:
    try:
        entries = sorted(root.iterdir())
    except FileNotFoundError:
        return
    for entry in entries:
        if entry.is_dir() and _HEX32.fullmatch(entry.name):
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

    @property
    def resolved(self) -> bool:
        return self._event.is_set()

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
    or a closed writer returns an already failed ticket. Nothing touches the filesystem until the first record. The
    thread owns shutdown: once closed it writes what was admitted, then releases the stream itself, even if ``close``
    stopped waiting for it."""

    _POLL_SECONDS = 0.05

    def __init__(self, root: Path, *, queue_records: int = QUEUE_RECORDS, segment_bytes: int = SEGMENT_BYTES,
                 on_failure: Callable[[str], None] | None = None) -> None:
        self._writer = StreamWriter(root, segment_bytes=segment_bytes)
        self._queue: queue.Queue[tuple[Mapping[str, Any], str | None, Ticket]] = queue.Queue(maxsize=queue_records)
        self._stats = WriterStats()
        self._lock = threading.Lock()  # admission, stats and shutdown
        self._on_failure = on_failure
        self._thread: threading.Thread | None = None
        self._closed = False

    @property
    def stream_id(self) -> str:
        return self._writer.stream_id

    @property
    def directory(self) -> Path:
        return self._writer.directory

    def stats(self) -> WriterStats:
        with self._lock:
            return WriterStats(**vars(self._stats))

    def submit(self, payload: Mapping[str, Any], *, event_id: str | None = None) -> Ticket:
        ticket = Ticket()
        with self._lock:
            if self._closed:
                ticket._resolve(None, "CLOSED")
                return ticket
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name=f"outbox-{self._writer.stream_id[:8]}", daemon=True)
                self._thread.start()
            try:
                self._queue.put_nowait((payload, event_id, ticket))
            except queue.Full:
                self._stats.rejected_full += 1
                self._stats.last_failure = "QUEUE_FULL"
                ticket._resolve(None, "QUEUE_FULL")
                return ticket
            self._stats.pending += 1
        return ticket

    def _run(self) -> None:
        while True:
            try:
                payload, event_id, ticket = self._queue.get(timeout=self._POLL_SECONDS)
            except queue.Empty:
                with self._lock:
                    if self._closed and self._queue.empty():
                        break
                continue
            try:
                record = self._writer.append(payload, event_id=event_id)
            except OutboxError as exc:
                with self._lock:
                    self._stats.pending -= 1
                    self._stats.write_failures += 1
                    self._stats.last_failure = exc.code
                ticket._resolve(None, exc.code)
                if self._on_failure is not None:
                    self._on_failure(exc.code)
                continue
            with self._lock:
                self._stats.pending -= 1
                self._stats.confirmed_sequence = record.sequence
            ticket._resolve(record, None)
        self._writer.close()

    def close(self, timeout: float = 5.0) -> bool:
        """Stop admitting and wait up to ``timeout`` for the thread to write what was admitted and release the stream.
        False if it is still working; it then finishes and releases the stream on its own."""
        with self._lock:
            self._closed = True
            thread = self._thread
        if thread is None:
            self._writer.close()
            return True
        thread.join(timeout)
        return not thread.is_alive()
