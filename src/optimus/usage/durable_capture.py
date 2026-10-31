"""Durable coverage epochs on the host's outbox (Plan 12.8; memory design v4 section 7; ADR-032).

One epoch per turn. `TurnSettlement` drives it: the turn's first worker invocation begins it, before any dispatch;
each host request appends a sequenced intent before it is sent; every receipt settlement accepts is appended as it
was accepted. When the turn reaches its terminal state while a worker still runs, a terminal snapshot records the
pending invocations and the epoch stays open; the close follows once every worker has settled. The close is preceded
by ordered `epoch.identities` parts holding the expected and settled identities, and binds them by count and digest.
Records are queued in order on one owned writer, so a confirmed later record proves every earlier one was processed.

Capture never stops model work. A record the queue refused, an intent not durable within the wait, or a begin that
never persisted leaves the epoch's `host_complete` false; a write failure leaves a gap record in the stream. Nothing
here infers a clean close: a close the queue refused leaves the epoch open for a later close, a queued close whose
write then failed reopens it, and only a close that was written settles it. A receipt that arrives after a written
close is appended with `late=True`; the close is never rewritten.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from optimus.usage import capture_events as ev
from optimus.usage.turn_settlement import StageReceipt, TurnCostSummary
from optimus_security import usage_capture_contract as uc
from optimus_security.durable_outbox import ACK_WAIT_SECONDS, OutboxWriter, Ticket


def host_outbox_root(config_root: Path) -> Path:
    """The host's outbox streams under the authorized per-user config root (never resolved here)."""
    return config_root / "accounting" / "outbox" / "host"


@dataclass
class _Epoch:
    epoch_id: str
    turn_id: str
    begin: Ticket
    rejected: int = 0
    intents: int = 0
    unconfirmed_intents: int = 0
    terminal_written: bool = False
    closing: Ticket | None = None


class DurableCapture:
    """The host's capture writer, one per process; thread-safe. Calls are cheap and never block, except `intent`,
    which waits at most `ack_wait` seconds for its record to be durable."""

    def __init__(self, writer: OutboxWriter, *, ack_wait: float = ACK_WAIT_SECONDS,
                 clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC)) -> None:
        self._writer = writer
        self._ack_wait = ack_wait
        self._clock = clock
        self._lock = threading.Lock()
        self._epochs: dict[str, _Epoch] = {}  # open or closing, by turn
        self._closed: dict[str, str] = {}  # shortcut: kept for the process lifetime; bound it if sessions grow huge
        self._started = False

    @classmethod
    def at(cls, config_root: Path) -> DurableCapture:
        return cls(OutboxWriter(host_outbox_root(config_root)))

    @property
    def writer(self) -> OutboxWriter:
        return self._writer

    def _submit(self, kind: str, epoch: _Epoch | None, **facts: Any) -> Ticket:
        if not self._started:
            self._started = True
            self._writer.submit({"kind": uc.STREAM_START, "at": self._clock().isoformat()})
        ticket = self._writer.submit({"kind": kind, "at": self._clock().isoformat(), **facts})
        if ticket.failure is not None and epoch is not None:
            epoch.rejected += 1
        return ticket

    def _settle_closing(self, turn_id: str) -> None:
        """Resolve a queued close: written, the epoch is closed; failed, it is open again."""
        epoch = self._epochs.get(turn_id)
        if epoch is None or epoch.closing is None or not epoch.closing.resolved:
            return
        if epoch.closing.record is not None:
            del self._epochs[turn_id]
            self._closed[turn_id] = epoch.epoch_id
        else:
            epoch.closing = None
            epoch.rejected += 1

    def _current(self, turn_id: str) -> tuple[_Epoch | None, str | None]:
        """The turn's open epoch, or None with its closed epoch's ID (None if it never began)."""
        self._settle_closing(turn_id)
        epoch = self._epochs.get(turn_id)
        if epoch is not None and epoch.closing is None:
            return epoch, epoch.epoch_id
        return None, epoch.epoch_id if epoch is not None else self._closed.get(turn_id)

    def _epoch(self, turn_id: str, session_id: str | None) -> _Epoch:
        epoch, closed_id = self._current(turn_id)
        if epoch is not None:
            return epoch
        if closed_id is not None:
            raise _Closed(closed_id)
        epoch_id = uuid.uuid4().hex
        ticket = self._submit(uc.EPOCH_BEGIN, None, epoch_id=epoch_id, turn_id=turn_id, session_id=session_id)
        epoch = _Epoch(epoch_id, turn_id, ticket, rejected=1 if ticket.failure is not None else 0)
        self._epochs[turn_id] = epoch
        return epoch

    def invocation_opened(self, turn_id: str, session_id: str | None = None) -> str:
        """Begin the turn's epoch if this is its first invocation, then record the invocation; returns its ID."""
        with self._lock:
            invocation_id = uuid.uuid4().hex
            try:
                epoch = self._epoch(turn_id, session_id)
            except _Closed as closed:  # a worker after the close: attributable, never reopening the epoch
                self._submit(uc.INVOCATION_OPEN, None, epoch_id=closed.epoch_id, invocation_id=invocation_id)
                return invocation_id
            self._submit(uc.INVOCATION_OPEN, epoch, epoch_id=epoch.epoch_id, invocation_id=invocation_id)
            return invocation_id

    def invocation_ended(self, turn_id: str, invocation_id: str, state: str) -> None:
        with self._lock:
            epoch, epoch_id = self._current(turn_id)
            self._submit(uc.INVOCATION_END, epoch, epoch_id=epoch_id, invocation_id=invocation_id, state=state)

    def intent(self, turn_id: str, host_request_id: str, *, stage: str, session_id: str | None = None,
               requested_model: str | None = None, purpose: str | None = None) -> bool:
        """Append the pre-dispatch intent for one host request; True only if it is durable within the wait. A record
        confirmed after the wait never counts as a pre-dispatch intent."""
        with self._lock:
            try:
                epoch = self._epoch(turn_id, session_id)
                epoch_id: str = epoch.epoch_id
            except _Closed as closed:
                epoch, epoch_id = None, closed.epoch_id
            if epoch is not None:
                epoch.intents += 1
            ticket = self._submit(
                uc.ATTEMPT_INTENT,
                epoch,
                epoch_id=epoch_id,
                host_request_id=host_request_id,
                stage=stage,
                purpose=ev.purpose_for(stage, purpose),
                requested_model=requested_model,
            )
        confirmed = ticket.wait(self._ack_wait)
        if not confirmed and epoch is not None:
            with self._lock:
                epoch.unconfirmed_intents += 1
        return confirmed

    def receipt(self, receipt: StageReceipt, *, purpose: str | None = None) -> None:
        with self._lock:
            try:
                epoch: _Epoch | None = self._epoch(receipt.turn_id, receipt.session_id)  # begins one if no invocation did
                epoch_id = epoch.epoch_id  # type: ignore[union-attr]
            except _Closed as closed:
                epoch, epoch_id = None, closed.epoch_id
            payload = ev.receipt_payload(receipt, epoch_id=epoch_id, late=epoch is None, purpose=purpose)
            del payload["kind"]
            self._submit(uc.ATTEMPT_RECEIPT, epoch, **payload)

    def integrity_failure(self, turn_id: str, reason: str) -> None:
        with self._lock:
            epoch, epoch_id = self._current(turn_id)
            self._submit(uc.INTEGRITY_FAILURE, epoch, epoch_id=epoch_id, turn_id=turn_id, reason=reason, late=epoch is None)

    def close(self, summary: TurnCostSummary) -> bool:
        """The turn's terminal state. With workers still pending, write one terminal snapshot and keep the epoch open;
        otherwise write the identity parts and the close. True once a close is queued; False if the epoch is not open,
        is still pending, or the queue refused the close (the epoch then stays open for a later close)."""
        with self._lock:
            epoch, _ = self._current(summary.turn_id)
            if epoch is None:
                return False
            if summary.pending_invocations:  # settlement is the authority on running workers
                if not epoch.terminal_written:
                    ticket = self._submit(
                        uc.EPOCH_TERMINAL,
                        epoch,
                        epoch_id=epoch.epoch_id,
                        turn_id=summary.turn_id,
                        pending_invocations=summary.pending_invocations,
                    )
                    epoch.terminal_written = ticket.failure is None
                return False
            parts, identities_digest = ev.identity_parts(epoch.epoch_id, summary)
            for part in parts:
                kind = part.pop("kind")
                self._submit(kind, epoch, **part)
            begin_confirmed = epoch.begin.wait(self._ack_wait)  # FIFO: normally resolved long before
            host_complete = (
                summary.complete and begin_confirmed and epoch.rejected == 0 and epoch.unconfirmed_intents == 0
            )
            ticket = self._submit(
                uc.EPOCH_CLOSE,
                epoch,
                epoch_id=epoch.epoch_id,
                turn_id=summary.turn_id,
                identity_parts=len(parts),
                settled_count=len(summary.receipt_ids),
                unknown_count=len(summary.unknown_attempt_ids),
                identities_digest=identities_digest,
                pending_invocations=summary.pending_invocations,
                integrity_failures=summary.integrity_failures,
                known_subtotal_usd=ev.decimal_text(summary.known_subtotal_usd),
                intents=epoch.intents,
                unconfirmed_intents=epoch.unconfirmed_intents,
                rejected_records=epoch.rejected,
                begin_confirmed=begin_confirmed,
                host_complete=host_complete,
            )
            if ticket.failure is not None:
                return False
            epoch.closing = ticket
            return True

    def stop(self, timeout: float = 5.0) -> bool:
        """Orderly shutdown: record the stream's end, then flush and release it. Open epochs stay open."""
        with self._lock:
            for turn_id in list(self._epochs):
                self._settle_closing(turn_id)
            if self._started:
                open_epochs = sorted(e.epoch_id for e in self._epochs.values())
                self._writer.submit({"kind": uc.STREAM_END, "at": self._clock().isoformat(), "open_epochs": open_epochs})
        return self._writer.close(timeout)


class _Closed(Exception):
    def __init__(self, epoch_id: str) -> None:
        super().__init__(epoch_id)
        self.epoch_id = epoch_id
