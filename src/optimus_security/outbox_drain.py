"""Draining outbox streams to the ledger with committed acknowledgements (Plan 12.8; ADR-032). Neutral: the host sends
through its Gateway URL and key, the Gateway commits its own stream directly; both drain the same way.

Each pass reads every stream under the root. This process's own live stream is sent only up to its writer's confirmed
sequence; a stream whose writer has ended or died is claimed by its lock and scanned as an orphan, so its unverified
tail is withheld; another live process's stream is left alone. Records after the stored acknowledgement go out in
batches bounded by the contract's count and byte limits. Only a committed acknowledgement naming the batch's last
record is stored, and only a stored acknowledgement of the same ledger instance compacts closed segments. A refused or
failed batch leaves every record in place; the next pass resends. Passes run on one owned background thread, at most
three transient attempts per trigger.

Each pass also reports the backlog it leaves: unacknowledged events and bytes, the oldest pending record's time, this
process's local and committed watermarks, the last delivery failure and the free disk space. Crossing 256 MiB pending
or 24 hours oldest pending is reported once through ``warn``, and so is falling back below. These are visibility
thresholds only: nothing unacknowledged is ever deleted, and no model call waits on them.
"""

from __future__ import annotations

import contextlib
import json
import shutil
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from optimus_security import durable_outbox as ob
from optimus_security import usage_capture_contract as uc

PASS_SECONDS = 15.0  # agent-selected
MAX_ATTEMPTS = 3
_BATCH_BUDGET = uc.MAX_BODY_BYTES - 4096
WARN_PENDING_BYTES = 256 * 1024 * 1024  # agent-selected visibility thresholds (memory design v4 section 7)
WARN_PENDING_AGE = timedelta(hours=24)

# send(stream_id, believed ledger instance, committed prefix, records) -> the ledger's committed acknowledgement.
Send = Callable[[str, str | None, tuple[int, str], list[ob.Record]], uc.CaptureAck]


class DrainStop(Exception):
    """This stream cannot advance now; ``reason`` is reported and the next pass retries."""

    def __init__(self, reason: str, *, transient: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.transient = transient


@dataclass
class Backlog:
    pending_events: int = 0  # records on disk not yet acknowledged by the ledger
    pending_bytes: int = 0
    oldest_pending_at: datetime | None = None
    local_watermark: int = 0  # this process's stream: its writer's confirmed sequence
    committed_watermark: int = 0  # and its stored acknowledgement
    last_failure: str | None = None  # the most recent delivery failure, kept after later successes
    free_bytes: int | None = None
    warnings: tuple[str, ...] = ()  # the thresholds currently crossed: pending_bytes, pending_age


@dataclass
class DrainReport:
    committed: int = 0
    compacted: int = 0
    pending_streams: int = 0
    failures: list[str] = field(default_factory=list)
    backlog: Backlog = field(default_factory=Backlog)


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


class OutboxDrain:
    def __init__(self, writer: ob.OutboxWriter, send: Send, *, pass_seconds: float = PASS_SECONDS, name: str = "outbox-drain",
                 warn: Callable[[str], None] | None = None, clock: Callable[[], datetime] = _utc_now,
                 warn_bytes: int = WARN_PENDING_BYTES, warn_age: timedelta = WARN_PENDING_AGE) -> None:
        self._writer = writer
        self._send = send
        self._root = writer.directory.parent
        self._pass_seconds = pass_seconds
        self._name = name
        self._warn = warn
        self._clock = clock
        self._warn_bytes = warn_bytes
        self._warn_age = warn_age
        self._last_failure: str | None = None
        self._crossed: set[str] = set()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_report = DrainReport()

    def drain_once(self) -> DrainReport:
        """One pass over every stream; never raises for a delivery failure, which is reported and retried later."""
        report = DrainReport()
        for stream_dir in ob.stream_dirs(self._root):
            with self._readable(stream_dir) as reading:
                if reading is None:
                    continue
                scan, bound, active = reading
                try:
                    self._deliver(stream_dir, scan, bound, active, report)
                except DrainStop as stop:
                    report.failures.append(stop.reason)
                    report.pending_streams += 1
                self._count(stream_dir, scan, report.backlog)
        self._observe(report)
        self.last_report = report
        return report

    def _count(self, stream_dir: Path, scan: ob.StreamScan, backlog: Backlog) -> None:
        ack = ob.read_ack(stream_dir)
        acknowledged = ack.sequence if ack is not None else 0
        for record in scan.records:
            if record.sequence <= acknowledged:
                continue
            backlog.pending_events += 1
            backlog.pending_bytes += len(record.line) + 1
            with contextlib.suppress(TypeError, ValueError):  # a record without a time (a gap) has no age
                at = datetime.fromisoformat(str(record.payload["at"])) if "at" in record.payload else None
                if at is None:
                    continue
                if backlog.oldest_pending_at is None or at < backlog.oldest_pending_at:
                    backlog.oldest_pending_at = at
        if stream_dir == self._writer.directory:
            backlog.local_watermark, backlog.committed_watermark = self._writer.stats().confirmed_sequence, acknowledged

    def _observe(self, report: DrainReport) -> None:
        backlog = report.backlog
        if report.failures:
            self._last_failure = report.failures[-1]
        backlog.last_failure = self._last_failure
        with contextlib.suppress(OSError):
            backlog.free_bytes = shutil.disk_usage(self._root).free
        crossed = set()
        if backlog.pending_bytes >= self._warn_bytes:
            crossed.add("pending_bytes")
        if backlog.oldest_pending_at is not None and self._clock() - backlog.oldest_pending_at >= self._warn_age:
            crossed.add("pending_age")
        backlog.warnings = tuple(sorted(crossed))
        if self._warn is not None:  # only a change is reported: newly crossed, then back below
            facts = (f"events={backlog.pending_events} bytes={backlog.pending_bytes} "
                     f"oldest={None if backlog.oldest_pending_at is None else backlog.oldest_pending_at.isoformat()} "
                     f"last_failure={backlog.last_failure}")
            for name in sorted(crossed - self._crossed):
                self._warn(f"{self._name}: capture backlog above its {name} threshold ({facts}); nothing pending is deleted.")
            for name in sorted(self._crossed - crossed):
                self._warn(f"{self._name}: capture backlog back below its {name} threshold ({facts}).")
        self._crossed = crossed

    @contextlib.contextmanager
    def _readable(self, stream_dir: Path) -> Iterator[tuple[ob.StreamScan, int, str | None] | None]:
        if stream_dir == self._writer.directory:
            yield ob.scan_stream(stream_dir), self._writer.stats().confirmed_sequence, self._writer.active_segment
            return
        handle = ob.claim(stream_dir)
        if handle is None:
            yield None
            return
        try:
            scan = ob.scan_stream(stream_dir, orphan=True)
            yield scan, scan.verified_sequence, None
        finally:
            ob.release(handle)

    def _deliver(self, stream_dir: Path, scan: ob.StreamScan, bound: int, active: str | None, report: DrainReport) -> None:
        ack = ob.read_ack(stream_dir)
        after = (ack.sequence, ack.digest) if ack is not None else (0, ob.GENESIS)
        ledger = ack.ledger_instance if ack is not None else None
        pending = [r for r in scan.records if after[0] < r.sequence <= bound]
        if not pending and ledger is not None:
            report.compacted += len(ob.compact(stream_dir, scan, ledger_instance=ledger, active_segment=active))
            return
        for batch in batches(pending):
            committed = self._committed(stream_dir.name, ledger, after, batch, scan.unverified_tail)
            if ob.write_ack(stream_dir, scan, ledger_instance=committed.ledger_instance, sequence=committed.sequence, digest=committed.digest):
                report.committed += committed.sequence - after[0]
            after, ledger = (committed.sequence, committed.digest), committed.ledger_instance
            report.compacted += len(ob.compact(stream_dir, scan, ledger_instance=ledger, active_segment=active))

    def _committed(self, stream_id: str, ledger: str | None, after: tuple[int, str], batch: list[ob.Record],
                   withheld: ob.Record | None) -> uc.CaptureAck:
        """The ledger's acknowledgement of ``batch``. It may instead name the withheld tail of a dead writer's stream with
        that record's exact digest: the writer died after the ledger committed it, so the ledger already holds those bytes."""
        last = "unsent"
        named = {(batch[-1].sequence, batch[-1].digest)} | ({(withheld.sequence, withheld.digest)} if withheld is not None else set())
        for _ in range(MAX_ATTEMPTS):
            try:
                committed = self._send(stream_id, ledger, after, batch)
            except DrainStop as stop:
                if not stop.transient:
                    raise
                last = stop.reason
                continue
            if committed.stream_id != stream_id or (committed.sequence, committed.digest) not in named:
                raise DrainStop("ack_mismatch")
            return committed
        raise DrainStop(last)

    def start(self) -> None:
        """Start the owned background thread: a pass now, then every `pass_seconds` or when nudged."""
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name=self._name, daemon=True)
            self._thread.start()

    def nudge(self) -> None:
        self._wake.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            with contextlib.suppress(Exception):  # a pass never takes the process down; its report keeps the cause
                self.drain_once()
            self._wake.wait(self._pass_seconds)
            self._wake.clear()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)


def batches(records: list[ob.Record]) -> Iterator[list[ob.Record]]:
    batch: list[ob.Record] = []
    size = 0
    for record in records:
        cost = len(json.dumps(record.line.decode("ascii"))) + 2  # the line as an escaped JSON string, plus ", "
        if batch and (len(batch) >= uc.MAX_RECORDS or size + cost > _BATCH_BUDGET):
            yield batch
            batch, size = [], 0
        batch.append(record)
        size += cost
    if batch:
        yield batch
