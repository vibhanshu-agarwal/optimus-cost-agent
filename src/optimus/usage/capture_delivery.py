"""Delivery of the host's outbox streams to the Gateway-owned ledger (Plan 12.8; ADR-032).

Each pass reads every stream under the host outbox root. This process's own live stream is sent only up to its
writer's confirmed sequence; a stream whose writer has ended or died is claimed by its lock and scanned as an orphan,
so its unverified tail is withheld. Records after the stored acknowledgement go up in batches bounded by the contract's
count and byte limits, through the existing Gateway URL and key. Only a committed acknowledgement is stored, and only a
stored acknowledgement of the same ledger instance compacts closed segments. A refused or failed batch leaves every
record in place; the next pass resends. Passes run on one owned background thread, at most three transient attempts
per trigger, never inside settlement and never on a model call's path.
"""

from __future__ import annotations

import contextlib
import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from optimus.gateway.errors import GatewayError, GatewayHttpError
from optimus_security import durable_outbox as ob
from optimus_security import usage_capture_contract as uc

if TYPE_CHECKING:
    from optimus.gateway.client import GatewayClient
    from optimus.usage.durable_capture import DurableCapture

PASS_SECONDS = 15.0  # agent-selected
MAX_ATTEMPTS = 3
_BATCH_BUDGET = uc.MAX_BODY_BYTES - 4096


@dataclass
class DeliveryReport:
    committed: int = 0
    compacted: int = 0
    pending_streams: int = 0
    failures: list[str] = field(default_factory=list)


class CaptureDelivery:
    def __init__(self, capture: DurableCapture, client: GatewayClient, *, pass_seconds: float = PASS_SECONDS) -> None:
        self._capture = capture
        self._client = client
        self._root = capture.writer.directory.parent
        self._pass_seconds = pass_seconds
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_report = DeliveryReport()

    def drain_once(self) -> DeliveryReport:
        """One pass over every stream; never raises for a delivery failure, which is reported and retried later."""
        report = DeliveryReport()
        for stream_dir in ob.stream_dirs(self._root):
            with self._readable(stream_dir) as reading:
                if reading is None:
                    continue  # another live process's stream
                scan, bound, active = reading
                try:
                    self._deliver(stream_dir, scan, bound, active, report)
                except _Stop as stop:
                    report.failures.append(stop.reason)
                    report.pending_streams += 1
        self.last_report = report
        return report

    @contextlib.contextmanager
    def _readable(self, stream_dir: Path) -> Iterator[tuple[ob.StreamScan, int, str | None] | None]:
        writer = self._capture.writer
        if stream_dir == writer.directory:
            yield ob.scan_stream(stream_dir), writer.stats().confirmed_sequence, writer.active_segment
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

    def _deliver(self, stream_dir: Path, scan: ob.StreamScan, bound: int, active: str | None, report: DeliveryReport) -> None:
        ack = ob.read_ack(stream_dir)
        after = (ack.sequence, ack.digest) if ack is not None else (0, ob.GENESIS)
        ledger = ack.ledger_instance if ack is not None else None
        pending = [r for r in scan.records if after[0] < r.sequence <= bound]
        if not pending and ledger is not None:
            report.compacted += len(ob.compact(stream_dir, scan, ledger_instance=ledger, active_segment=active))
            return
        for batch in _batches(pending):
            committed = self._send(stream_dir.name, ledger, after, batch)
            if ob.write_ack(stream_dir, scan, ledger_instance=committed.ledger_instance, sequence=committed.sequence, digest=committed.digest):
                report.committed += committed.sequence - after[0]
            after, ledger = (committed.sequence, committed.digest), committed.ledger_instance
            report.compacted += len(ob.compact(stream_dir, scan, ledger_instance=ledger, active_segment=active))

    def _send(self, stream_id: str, ledger: str | None, after: tuple[int, str], batch: list[ob.Record]) -> uc.CaptureAck:
        body = json.loads(uc.build_batch("host", stream_id, ledger, after[0], after[1], batch))
        last: str = "unsent"
        for _ in range(MAX_ATTEMPTS):
            try:
                reply = self._client.post_observability_json(path=uc.PATH, payload=body)
            except GatewayHttpError as exc:
                if exc.status_code == 503:
                    last = "ledger_unavailable"
                    continue
                raise _Stop(f"refused:{exc.status_code}") from None
            except GatewayError:
                last = "gateway_unreachable"
                continue
            try:
                committed = uc.parse_ack(reply, stream_id=stream_id)
            except uc.ContractError:
                raise _Stop("malformed_ack") from None
            if committed.sequence != batch[-1].sequence or committed.digest != batch[-1].digest:
                raise _Stop("ack_mismatch")
            return committed
        raise _Stop(last)

    def start(self) -> None:
        """Start the owned background thread: a pass now, then every `pass_seconds` or when nudged."""
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="capture-delivery", daemon=True)
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


class _Stop(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _batches(records: list[ob.Record]) -> Iterator[list[ob.Record]]:
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
