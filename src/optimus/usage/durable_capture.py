"""Durable coverage epochs on the host's outbox (Plan 12.8; memory design v4 section 7; ADR-032).

One epoch per turn. `TurnSettlement` drives it: the turn's first worker invocation begins it, before any dispatch;
each host request appends a sequenced intent before it is sent; every receipt settlement accepts is appended as it
was accepted; the close follows the turn's terminal finalization once no invocation is still running, and carries
the expected and settled identities. Records are queued in order on one owned writer, so a confirmed later record
proves every earlier one was processed.

Capture never stops model work. A record the queue refused, an intent not durable within the wait, or a begin that
never persisted leaves the epoch's `host_complete` false; a write failure leaves a gap record in the stream. Nothing
here infers a clean close: a turn whose close never persisted stays open, and a later clean epoch says nothing about
it. A receipt that arrives after its epoch closed is appended with `late=True`; the close is never rewritten.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from optimus.usage import capture_events as ev
from optimus.usage.turn_settlement import StageReceipt, TurnCostSummary
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
    invocations: dict[str, str] = field(default_factory=dict)


class DurableCapture:
    """The host's capture writer, one per process; thread-safe. Calls are cheap and never block, except `intent`,
    which waits at most `ack_wait` seconds for its record to be durable."""

    def __init__(self, writer: OutboxWriter, *, ack_wait: float = ACK_WAIT_SECONDS,
                 clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC)) -> None:
        self._writer = writer
        self._ack_wait = ack_wait
        self._clock = clock
        self._lock = threading.Lock()
        self._open: dict[str, _Epoch] = {}
        self._closed: dict[str, str] = {}  # shortcut: kept for the process lifetime; bound it if sessions grow huge
        self._started = False

    @classmethod
    def at(cls, config_root: Path) -> DurableCapture:
        return cls(OutboxWriter(host_outbox_root(config_root)))

    @property
    def writer(self) -> OutboxWriter:
        return self._writer

    def _submit(self, kind: str, epoch: _Epoch | None = None, **facts: Any) -> Ticket:
        if not self._started:
            self._started = True
            self._writer.submit({"kind": ev.STREAM_START, "at": self._clock().isoformat()})
        ticket = self._writer.submit({"kind": kind, "at": self._clock().isoformat(), **facts})
        if ticket.failure is not None and epoch is not None:
            epoch.rejected += 1
        return ticket

    def _epoch(self, turn_id: str, session_id: str | None) -> _Epoch:
        epoch = self._open.get(turn_id)
        if epoch is None:
            epoch_id = uuid.uuid4().hex
            ticket = self._submit(ev.EPOCH_BEGIN, epoch_id=epoch_id, turn_id=turn_id, session_id=session_id)
            epoch = _Epoch(epoch_id, turn_id, ticket)
            if ticket.failure is not None:
                epoch.rejected += 1
            self._open[turn_id] = epoch
        return epoch

    def invocation_opened(self, turn_id: str, session_id: str | None = None) -> str:
        """Begin the turn's epoch if this is its first invocation, then record the invocation; returns its ID."""
        with self._lock:
            epoch = self._epoch(turn_id, session_id)
            invocation_id = uuid.uuid4().hex
            epoch.invocations[invocation_id] = "open"
            self._submit(ev.INVOCATION_OPEN, epoch, epoch_id=epoch.epoch_id, invocation_id=invocation_id)
            return invocation_id

    def invocation_ended(self, turn_id: str, invocation_id: str, state: str) -> None:
        with self._lock:
            epoch = self._open.get(turn_id)
            epoch_id = epoch.epoch_id if epoch is not None else self._closed.get(turn_id)
            if epoch is not None:
                epoch.invocations[invocation_id] = state
            self._submit(ev.INVOCATION_END, epoch, epoch_id=epoch_id, invocation_id=invocation_id, state=state)

    def intent(self, turn_id: str, host_request_id: str, *, stage: str, session_id: str | None = None,
               requested_model: str | None = None, purpose: str | None = None) -> bool:
        """Append the pre-dispatch intent for one host request; True only if it is durable within the wait. A record
        confirmed after the wait never counts as a pre-dispatch intent."""
        with self._lock:
            epoch = self._epoch(turn_id, session_id)
            epoch.intents += 1
            ticket = self._submit(
                ev.ATTEMPT_INTENT,
                epoch,
                epoch_id=epoch.epoch_id,
                host_request_id=host_request_id,
                stage=stage,
                purpose=ev.purpose_for(stage, purpose),
                requested_model=requested_model,
            )
        confirmed = ticket.wait(self._ack_wait)
        if not confirmed:
            with self._lock:
                epoch.unconfirmed_intents += 1
        return confirmed

    def receipt(self, receipt: StageReceipt, *, purpose: str | None = None) -> None:
        with self._lock:
            epoch = self._open.get(receipt.turn_id)
            if epoch is None and receipt.turn_id not in self._closed:
                epoch = self._epoch(receipt.turn_id, receipt.session_id)  # a receipt with no worker invocation
            epoch_id = epoch.epoch_id if epoch is not None else self._closed[receipt.turn_id]
            self._submit(ev.ATTEMPT_RECEIPT, epoch, **_without_kind(ev.receipt_payload(receipt, epoch_id=epoch_id, late=epoch is None, purpose=purpose)))

    def integrity_failure(self, turn_id: str, reason: str) -> None:
        with self._lock:
            epoch = self._open.get(turn_id)
            epoch_id = epoch.epoch_id if epoch is not None else self._closed.get(turn_id)
            self._submit(ev.INTEGRITY_FAILURE, epoch, epoch_id=epoch_id, turn_id=turn_id, reason=reason, late=epoch is None)

    def close(self, summary: TurnCostSummary) -> None:
        """Close the turn's epoch from its settled summary; a no-op if it never began or already closed."""
        with self._lock:
            epoch = self._open.pop(summary.turn_id, None)
            if epoch is None:
                return
            self._closed[summary.turn_id] = epoch.epoch_id
            begin_confirmed = epoch.begin.wait(0) and epoch.begin.record is not None
            pending = sorted(name for name, state in epoch.invocations.items() if state == "open" or state == "started")
            host_complete = (
                summary.complete and begin_confirmed and not pending and epoch.rejected == 0 and epoch.unconfirmed_intents == 0
            )
            self._submit(
                ev.EPOCH_CLOSE,
                None,
                epoch_id=epoch.epoch_id,
                turn_id=summary.turn_id,
                settled_attempt_ids=list(summary.receipt_ids),
                unknown_attempt_ids=list(summary.unknown_attempt_ids),
                pending_invocations=summary.pending_invocations,
                integrity_failures=summary.integrity_failures,
                known_subtotal_usd=str(summary.known_subtotal_usd),
                intents=epoch.intents,
                unconfirmed_intents=epoch.unconfirmed_intents,
                rejected_records=epoch.rejected,
                begin_confirmed=begin_confirmed,
                host_complete=host_complete,
            )

    def stop(self, timeout: float = 5.0) -> None:
        """Orderly shutdown: record the stream's end, then flush and release it. Open epochs stay open."""
        with self._lock:
            if self._started:
                self._writer.submit({"kind": ev.STREAM_END, "at": self._clock().isoformat(), "open_epochs": sorted(e.epoch_id for e in self._open.values())})
        self._writer.close(timeout)


def _without_kind(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "kind"}
