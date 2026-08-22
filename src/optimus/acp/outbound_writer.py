"""Dedicated process-lifetime NDJSON outbound writer (Plan 11.25 Task 4)."""

from __future__ import annotations

import concurrent.futures
import json
import queue
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from optimus.acp.lifecycle import SendCompletion, SendKey, TurnSendKey, WriterToken
from optimus.acp.settlement import SendOutcome, SendState


class PhysicalNdjsonTransport(Protocol):
    def write_bytes(self, data: bytes) -> None: ...

    def flush(self) -> None: ...


class SendOwner(Protocol):
    def claim_write_started(self, send_key: Any) -> SendState: ...

    def publish_authoritative(self, send_key: Any, outcome: SendOutcome) -> None: ...

    def publish_diagnostic(self, send_key: Any, outcome: SendOutcome) -> None: ...


@dataclass(slots=True)
class _EphemeralSlot:
    authoritative: SendState
    diagnostic: SendOutcome | None = None


class EphemeralSendOwner:
    """Minimal send-owner for channel emits before turn leases are wired (Task 7)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._slots: dict[SendKey, _EphemeralSlot] = {}

    def create_queued(self, send_key: SendKey) -> None:
        with self._lock:
            self._slots[send_key] = _EphemeralSlot(authoritative=SendState.QUEUED)

    def suppress(self, send_key: SendKey) -> None:
        with self._lock:
            slot = self._slots.get(send_key)
            if slot is not None and slot.authoritative is SendState.QUEUED:
                slot.authoritative = SendState.SUPPRESSED

    def claim_write_started(self, send_key: SendKey) -> SendState:
        with self._lock:
            slot = self._slots[send_key]
            if slot.authoritative is SendState.QUEUED:
                slot.authoritative = SendState.WRITE_STARTED
            return slot.authoritative

    def publish_authoritative(self, send_key: SendKey, outcome: SendOutcome) -> None:
        with self._lock:
            slot = self._slots[send_key]
            if slot.authoritative in {
                SendState.FLUSHED,
                SendState.CONCLUSIVE_FAILURE,
                SendState.AMBIGUOUS,
                SendState.SUPPRESSED,
            }:
                return
            slot.authoritative = SendState(outcome.value)

    def publish_diagnostic(self, send_key: SendKey, outcome: SendOutcome) -> None:
        with self._lock:
            self._slots[send_key].diagnostic = outcome


@dataclass(slots=True)
class OutboundQueueItem:
    payload: Mapping[str, Any]
    send_key: SendKey
    owner: SendOwner
    source_future: concurrent.futures.Future[SendCompletion]
    writer_token: WriterToken | None = None
    handle: Any | None = None
    prepare_error: BaseException | None = None


_SENTINEL = object()


def classify_physical_outcome(
    *,
    preparation_error: BaseException | None,
    write_started: bool,
    write_error: BaseException | None,
    flush_error: BaseException | None,
) -> SendOutcome:
    if preparation_error is not None and not write_started:
        return SendOutcome.CONCLUSIVE_FAILURE
    if write_error is not None or flush_error is not None:
        return SendOutcome.AMBIGUOUS
    return SendOutcome.FLUSHED


class DedicatedOutboundWriter:
    """Single non-daemon FIFO thread owning every physical NDJSON write+flush."""

    def __init__(self, transport: PhysicalNdjsonTransport) -> None:
        self._transport = transport
        self._queue: queue.Queue[OutboundQueueItem | object] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._started = False
        self._closed = False
        self._join_lock = threading.Lock()
        self._joined = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread = threading.Thread(
            target=self._run,
            name="optimus-acp-ndjson-writer",
            daemon=False,
        )
        self._thread.start()

    def submit(self, item: OutboundQueueItem) -> concurrent.futures.Future[SendCompletion]:
        if self._closed:
            raise RuntimeError("dedicated outbound writer is closed")
        if not self._started:
            raise RuntimeError("dedicated outbound writer not started")
        self._queue.put(item)
        return item.source_future

    def close_and_join(self) -> None:
        with self._join_lock:
            if self._joined:
                return
            self._closed = True
            self._queue.put(_SENTINEL)
            if self._thread is not None:
                self._thread.join()
            self._joined = True

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is _SENTINEL:
                return
            assert isinstance(item, OutboundQueueItem)
            try:
                self._process_item(item)
            except BaseException:
                try:
                    self._fail_closed(item, SendOutcome.AMBIGUOUS)
                except BaseException:
                    pass

    def _process_item(self, item: OutboundQueueItem) -> None:
        if not item.source_future.set_running_or_notify_cancel():
            state = item.owner.claim_write_started(item.send_key)
            if state is SendState.QUEUED:
                item.owner.publish_authoritative(item.send_key, SendOutcome.SUPPRESSED)
            if not item.source_future.done():
                item.source_future.set_result(
                    SendCompletion(send_key=item.send_key, outcome=SendOutcome.SUPPRESSED)
                )
            if item.writer_token is not None:
                item.writer_token.release()
            return

        payload_bytes: bytes | None = None
        preparation_error: BaseException | None = item.prepare_error
        if preparation_error is None:
            try:
                payload_bytes = (
                    json.dumps(dict(item.payload), separators=(",", ":")) + "\n"
                ).encode("utf-8")
            except BaseException as exc:
                preparation_error = exc

        state = item.owner.claim_write_started(item.send_key)
        if state is SendState.SUPPRESSED:
            item.source_future.set_result(
                SendCompletion(send_key=item.send_key, outcome=SendOutcome.SUPPRESSED)
            )
            if item.writer_token is not None:
                item.writer_token.release()
            return

        write_error: BaseException | None = None
        flush_error: BaseException | None = None
        write_entered = False
        if preparation_error is not None:
            outcome = SendOutcome.CONCLUSIVE_FAILURE
        else:
            assert payload_bytes is not None
            try:
                write_entered = True
                self._transport.write_bytes(payload_bytes)
            except BaseException as exc:
                write_error = exc
            if write_error is None:
                try:
                    self._transport.flush()
                except BaseException as exc:
                    flush_error = exc
            outcome = classify_physical_outcome(
                preparation_error=None,
                write_started=write_entered,
                write_error=write_error,
                flush_error=flush_error,
            )

        try:
            current = item.owner.claim_write_started(item.send_key)
            if current is SendState.AMBIGUOUS:
                if outcome is not SendOutcome.AMBIGUOUS:
                    item.owner.publish_diagnostic(item.send_key, outcome)
                authoritative = SendOutcome.AMBIGUOUS
            elif current is SendState.SUPPRESSED:
                authoritative = SendOutcome.SUPPRESSED
            elif current in {SendState.FLUSHED, SendState.CONCLUSIVE_FAILURE}:
                authoritative = SendOutcome(current.value)
            else:
                item.owner.publish_authoritative(item.send_key, outcome)
                authoritative = outcome
        except BaseException:
            authoritative = SendOutcome.AMBIGUOUS
            try:
                item.owner.publish_authoritative(item.send_key, authoritative)
            except BaseException:
                pass

        item.source_future.set_result(
            SendCompletion(send_key=item.send_key, outcome=authoritative)
        )
        if item.writer_token is not None:
            item.writer_token.release()

    def _fail_closed(self, item: OutboundQueueItem, outcome: SendOutcome) -> None:
        if not item.source_future.done():
            item.source_future.set_result(SendCompletion(send_key=item.send_key, outcome=outcome))
        if item.writer_token is not None:
            item.writer_token.release()


_ephemeral_counter = 0
_ephemeral_counter_lock = threading.Lock()


def next_ephemeral_send_key(kind: str = "channel") -> TurnSendKey:
    global _ephemeral_counter
    with _ephemeral_counter_lock:
        _ephemeral_counter += 1
        value = _ephemeral_counter
    return TurnSendKey(kind=kind, message_id=str(value))
