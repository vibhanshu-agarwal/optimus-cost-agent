"""Dedicated outbound writer FIFO / phase / shutdown tests (Plan 11.25 Task 4)."""

from __future__ import annotations

import asyncio
import concurrent.futures
import io
import threading
from pathlib import Path

import pytest

from optimus.acp.lifecycle import TurnSendKey, WriterToken
from optimus.acp.outbound_writer import (
    DedicatedOutboundWriter,
    EphemeralSendOwner,
    OutboundQueueItem,
    classify_physical_outcome,
)
from optimus.acp.server import StdioNdjsonLineReader, StdioNdjsonLineWriter
from optimus.acp.settlement import SendOutcome, SendState
from tests.integration.acp.test_server_stream import configured_test_agent_server


class ControllableTransport:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.flushes = 0
        self.write_entered = threading.Event()
        self.allow_write = threading.Event()
        self.allow_write.set()
        self.write_error: BaseException | None = None
        self.flush_error: BaseException | None = None
        self._lock = threading.Lock()

    def write_bytes(self, data: bytes) -> None:
        self.write_entered.set()
        self.allow_write.wait(timeout=5)
        if self.write_error is not None:
            raise self.write_error
        with self._lock:
            self.writes.append(data)

    def flush(self) -> None:
        if self.flush_error is not None:
            raise self.flush_error
        self.flushes += 1


def _item(
    owner: EphemeralSendOwner,
    *,
    payload: dict,
    key: TurnSendKey | None = None,
    token: WriterToken | None = None,
) -> OutboundQueueItem:
    send_key = key or TurnSendKey(kind="test", message_id=str(id(payload)))
    owner.create_queued(send_key)
    return OutboundQueueItem(
        payload=payload,
        send_key=send_key,
        owner=owner,
        source_future=concurrent.futures.Future(),
        writer_token=token,
    )


def test_fifo_serialization_blocks_second_write_until_first_completes() -> None:
    transport = ControllableTransport()
    transport.allow_write.clear()
    writer = DedicatedOutboundWriter(transport)
    writer.start()
    owner = EphemeralSendOwner()

    first = _item(owner, payload={"id": 1})
    second = _item(owner, payload={"id": 2})
    writer.submit(first)
    assert transport.write_entered.wait(timeout=2)
    writer.submit(second)
    assert len(transport.writes) == 0

    unrelated_started = threading.Event()

    def unrelated() -> None:
        unrelated_started.set()

    threading.Thread(target=unrelated).start()
    assert unrelated_started.wait(timeout=1)

    transport.allow_write.set()
    assert first.source_future.result(timeout=2).outcome is SendOutcome.FLUSHED
    assert second.source_future.result(timeout=2).outcome is SendOutcome.FLUSHED
    assert len(transport.writes) == 2
    writer.close_and_join()


def test_phase_classification_helpers() -> None:
    assert (
        classify_physical_outcome(
            preparation_error=RuntimeError("prep"),
            write_started=False,
            write_error=None,
            flush_error=None,
        )
        is SendOutcome.CONCLUSIVE_FAILURE
    )
    assert (
        classify_physical_outcome(
            preparation_error=None,
            write_started=True,
            write_error=OSError("write"),
            flush_error=None,
        )
        is SendOutcome.AMBIGUOUS
    )
    assert (
        classify_physical_outcome(
            preparation_error=None,
            write_started=True,
            write_error=None,
            flush_error=OSError("flush"),
        )
        is SendOutcome.AMBIGUOUS
    )
    assert (
        classify_physical_outcome(
            preparation_error=None,
            write_started=True,
            write_error=None,
            flush_error=None,
        )
        is SendOutcome.FLUSHED
    )


def test_token_released_after_flush() -> None:
    transport = ControllableTransport()
    writer = DedicatedOutboundWriter(transport)
    writer.start()
    owner = EphemeralSendOwner()
    released: list[str] = []

    def on_release() -> None:
        released.append("token")

    token = WriterToken(on_release)
    item = _item(owner, payload={"ok": True}, token=token)
    writer.submit(item)
    completion = item.source_future.result(timeout=2)
    assert completion.outcome is SendOutcome.FLUSHED
    assert released == ["token"]
    writer.close_and_join()


def test_queued_suppression_resolves_without_write() -> None:
    transport = ControllableTransport()
    writer = DedicatedOutboundWriter(transport)
    writer.start()
    owner = EphemeralSendOwner()
    key = TurnSendKey(kind="test", message_id="sup")
    item = _item(owner, payload={"x": 1}, key=key)
    owner.suppress(key)
    writer.submit(item)
    completion = item.source_future.result(timeout=2)
    assert completion.outcome is SendOutcome.SUPPRESSED
    assert transport.writes == []
    writer.close_and_join()


def test_write_started_freeze_plus_late_diagnostic() -> None:
    transport = ControllableTransport()
    transport.allow_write.clear()
    writer = DedicatedOutboundWriter(transport)
    writer.start()
    owner = EphemeralSendOwner()
    key = TurnSendKey(kind="test", message_id="freeze")
    item = _item(owner, payload={"x": 1}, key=key)
    writer.submit(item)
    assert transport.write_entered.wait(timeout=2)
    with owner._lock:  # noqa: SLF001
        owner._slots[key].authoritative = SendState.AMBIGUOUS  # noqa: SLF001
    transport.allow_write.set()
    completion = item.source_future.result(timeout=2)
    assert completion.outcome is SendOutcome.AMBIGUOUS
    with owner._lock:  # noqa: SLF001
        assert owner._slots[key].diagnostic is SendOutcome.FLUSHED  # noqa: SLF001
    writer.close_and_join()


def test_flush_failure_is_ambiguous() -> None:
    transport = ControllableTransport()
    transport.flush_error = OSError("flush boom")
    writer = DedicatedOutboundWriter(transport)
    writer.start()
    owner = EphemeralSendOwner()
    item = _item(owner, payload={"x": 1})
    writer.submit(item)
    assert item.source_future.result(timeout=2).outcome is SendOutcome.AMBIGUOUS
    writer.close_and_join()


def test_close_and_join_is_idempotent_and_non_daemon() -> None:
    transport = ControllableTransport()
    writer = DedicatedOutboundWriter(transport)
    writer.start()
    assert writer._thread is not None  # noqa: SLF001
    assert writer._thread.daemon is False  # noqa: SLF001
    owner = EphemeralSendOwner()
    item = _item(owner, payload={"x": 1})
    writer.submit(item)
    item.source_future.result(timeout=2)
    writer.close_and_join()
    writer.close_and_join()


def test_no_direct_ndjson_physical_write_outside_writer_and_adapter() -> None:
    root = Path("src/optimus/acp")
    allowed_names = {"outbound_writer.py", "server.py"}
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        if path.name in allowed_names:
            continue
        text = path.read_text(encoding="utf-8")
        if "write_bytes(" in text:
            offenders.append(str(path))
    assert offenders == []


@pytest.mark.asyncio
async def test_serve_ndjson_eof_with_dedicated_writer(tmp_path) -> None:
    configured = configured_test_agent_server(tmp_path, output_text="READ example.py\n")
    stream_in = io.BytesIO(b"")
    stream_out = io.BytesIO()
    reader = StdioNdjsonLineReader(stream_in)
    writer = StdioNdjsonLineWriter(stream_out)
    await asyncio.wait_for(configured.server.serve_ndjson(reader, writer), timeout=2)
