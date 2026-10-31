"""Plan 12.8 Task 3: host delivery of outbox streams through the real Gateway capture route and contract. The ledger
here is a unit-tier double that acknowledges what it is given; the real Postgres ledger is the live tier's
(`requires_plan12_capture_postgres`)."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import GatewayClient, GatewayRequest
from optimus.gateway.errors import GatewayHttpError
from optimus.usage.capture_delivery import CaptureDelivery
from optimus.usage.durable_capture import DurableCapture, host_outbox_root
from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.usage_capture import handle_usage_capture_request
from optimus_security import durable_outbox as ob
from optimus_security import usage_capture_contract as uc

_AT = datetime(2026, 10, 31, tzinfo=UTC)
_SECRET = "capture-test-secret"  # pragma: allowlist secret
_LEDGER = "1" * 32


class _AckingStore:
    """Acknowledges each batch's last record, as a committing ledger would; refuses while `down`."""

    def __init__(self) -> None:
        self.ledger_instance = _LEDGER
        self.batches: list[uc.CaptureBatch] = []
        self.down = False

    def ingest(self, batch: uc.CaptureBatch) -> Any:
        from optimus_gateway.usage_store import IngestResult, StoreError

        if self.down:
            raise StoreError("unavailable")
        self.batches.append(batch)
        last = batch.records[-1]
        return IngestResult(uc.CaptureAck(_LEDGER, batch.stream_id, last.sequence, last.digest), len(batch.records), 0)


class _RouteTransport:
    """Hands each host request to the real Gateway capture handler and raises as the urllib transport would."""

    def __init__(self, store: _AckingStore | None) -> None:
        self.config = GatewayServiceConfig(bind_host="127.0.0.1", bind_port=0, shared_secret=_SECRET, provider="openrouter",
                                           provider_api_key="or-test", base_url="https://openrouter.ai/api/v1", usage_store=store)  # pragma: allowlist secret
        self.bodies: list[bytes] = []

    def post_json(self, request: GatewayRequest) -> dict[str, Any]:
        raw = json.dumps(request.payload).encode("utf-8")
        self.bodies.append(raw)
        status, body = handle_usage_capture_request(authorization_header=request.headers.get("Authorization"), raw_body=raw, config=self.config)
        if status != 200:
            raise GatewayHttpError(status, json.dumps(body))
        return body


def _client(transport: _RouteTransport) -> GatewayClient:
    return GatewayClient(settings=OptimusGatewaySettings(gateway_url="http://127.0.0.1:8765", optimus_api_key=_SECRET), transport=transport)


def _capture(tmp_path: Path, **kwargs: Any) -> DurableCapture:
    return DurableCapture(ob.OutboxWriter(host_outbox_root(tmp_path / "config"), **kwargs), ack_wait=5.0, clock=lambda: _AT)


def _fill(capture: DurableCapture, turns: int) -> None:
    for n in range(turns):
        capture.invocation_opened(f"s:{n}", "s")
    deadline = time.monotonic() + 5.0
    while capture.writer.stats().pending and time.monotonic() < deadline:
        time.sleep(0.01)


def test_the_live_stream_is_delivered_to_its_confirmed_sequence_and_acknowledged(tmp_path):
    capture = _capture(tmp_path, segment_bytes=600)
    _fill(capture, 6)
    store = _AckingStore()
    delivery = CaptureDelivery(capture, _client(_RouteTransport(store)))

    report = delivery.drain_once()

    confirmed = capture.writer.stats().confirmed_sequence
    ack = ob.read_ack(capture.writer.directory)
    assert report.failures == [] and ack is not None and ack.sequence == confirmed and ack.ledger_instance == _LEDGER
    assert [r.sequence for b in store.batches for r in b.records] == list(range(1, confirmed + 1))
    assert report.compacted >= 1 and (capture.writer.directory / capture.writer.active_segment).exists()  # type: ignore[operator]
    assert delivery.drain_once().committed == 0, "nothing new: nothing resent"
    capture.stop()


def test_an_unavailable_ledger_keeps_every_record_and_the_next_pass_delivers(tmp_path):
    capture = _capture(tmp_path)
    _fill(capture, 2)
    store = _AckingStore()
    store.down = True
    delivery = CaptureDelivery(capture, _client(_RouteTransport(store)))

    first = delivery.drain_once()
    store.down = False
    second = delivery.drain_once()

    assert first.failures == ["ledger_unavailable"] and first.committed == 0
    assert second.failures == [] and second.committed == capture.writer.stats().confirmed_sequence
    capture.stop()


def test_backlog_age_is_warned_once_at_its_boundary_during_an_outage_and_clears_after_catch_up(tmp_path):
    capture = _capture(tmp_path)
    _fill(capture, 3)
    confirmed = capture.writer.stats().confirmed_sequence
    on_disk = sum(len(r.line) + 1 for r in ob.scan_stream(capture.writer.directory).records)
    store = _AckingStore()
    store.down = True
    clock = [_AT + timedelta(hours=24) - timedelta(microseconds=1)]
    warnings: list[str] = []
    delivery = CaptureDelivery(capture, _client(_RouteTransport(store)), warn=warnings.append, clock=lambda: clock[0], warn_bytes=10**9)

    below = delivery.drain_once().backlog
    clock[0] += timedelta(microseconds=1)
    crossed = delivery.drain_once().backlog
    again = delivery.drain_once().backlog
    store.down = False
    caught_up = delivery.drain_once().backlog

    assert (below.pending_events, below.pending_bytes, below.oldest_pending_at) == (confirmed, on_disk, _AT)
    assert (below.local_watermark, below.committed_watermark, below.last_failure) == (confirmed, 0, "ledger_unavailable")
    assert below.warnings == () and crossed.warnings == again.warnings == ("pending_age",)
    assert crossed.pending_events == again.pending_events == confirmed, "nothing pending is deleted during the outage"
    assert (caught_up.pending_events, caught_up.pending_bytes, caught_up.warnings) == (0, 0, ())
    assert caught_up.committed_watermark == confirmed and caught_up.last_failure == "ledger_unavailable"
    assert len(warnings) == 2 and "above its pending_age threshold" in warnings[0] and "back below its pending_age" in warnings[1]
    capture.stop()


def test_backlog_bytes_are_warned_from_exactly_their_threshold(tmp_path):
    capture = _capture(tmp_path)
    _fill(capture, 2)
    on_disk = sum(len(r.line) + 1 for r in ob.scan_stream(capture.writer.directory).records)
    store = _AckingStore()
    store.down = True
    at = lambda: _AT  # noqa: E731

    under = CaptureDelivery(capture, _client(_RouteTransport(store)), clock=at, warn_bytes=on_disk + 1).drain_once().backlog
    exact = CaptureDelivery(capture, _client(_RouteTransport(store)), clock=at, warn_bytes=on_disk).drain_once().backlog

    assert under.warnings == () and exact.warnings == ("pending_bytes",)
    assert exact.free_bytes is not None and exact.free_bytes > 0
    capture.stop()


def test_without_an_accounting_ledger_the_route_refuses_retryably_and_nothing_is_lost(tmp_path):
    capture = _capture(tmp_path)
    _fill(capture, 1)
    delivery = CaptureDelivery(capture, _client(_RouteTransport(None)))

    report = delivery.drain_once()

    assert report.failures == ["ledger_unavailable"] and ob.read_ack(capture.writer.directory) is None
    assert len(ob.scan_stream(capture.writer.directory).records) == capture.writer.stats().confirmed_sequence
    capture.stop()


def test_orphan_streams_are_claimed_and_their_unverified_tail_is_withheld(tmp_path):
    root = host_outbox_root(tmp_path / "config")
    dead = ob.StreamWriter(root)
    for _ in range(3):
        dead.append({"kind": uc.STREAM_START, "at": _AT.isoformat()})
    dead._abandon_segment()
    dead._lock_handle.close()  # type: ignore[union-attr]
    orderly = ob.StreamWriter(root)
    orderly.append({"kind": uc.STREAM_START, "at": _AT.isoformat()})
    orderly.append({"kind": uc.STREAM_END, "at": _AT.isoformat(), "open_epochs": []})
    orderly.close()
    capture = DurableCapture(ob.OutboxWriter(root), clock=lambda: _AT)
    store = _AckingStore()

    CaptureDelivery(capture, _client(_RouteTransport(store))).drain_once()

    delivered = {b.stream_id: [r.sequence for r in b.records] for b in store.batches}
    assert delivered[dead.stream_id] == [1, 2], "the last record of a dead writer is withheld"
    assert delivered[orderly.stream_id] == [1, 2], "an orderly end is delivered whole"
    capture.stop()


def test_a_dead_writers_tail_is_settled_only_by_an_acknowledgement_naming_its_exact_bytes(tmp_path):
    """The writer died after the ledger committed its last record but before storing the acknowledgement: the replayed
    prefix is answered with that record, which settles the withheld tail. An acknowledgement ahead with any other digest
    is refused and stores nothing."""
    from optimus_gateway.usage_store import IngestResult

    root = host_outbox_root(tmp_path / "config")
    dead = ob.StreamWriter(root)
    records = [dead.append({"kind": uc.STREAM_START, "at": _AT.isoformat()}) for _ in range(3)]
    dead._abandon_segment()
    dead._lock_handle.close()  # type: ignore[union-attr]
    reports = []
    for named in ("f" * 64, records[2].digest):

        class LedgerAhead(_AckingStore):
            digest = named

            def ingest(self, batch: uc.CaptureBatch) -> Any:
                super().ingest(batch)
                return IngestResult(uc.CaptureAck(_LEDGER, batch.stream_id, 3, self.digest), 0, len(batch.records))

        capture = DurableCapture(ob.OutboxWriter(root), clock=lambda: _AT)
        reports.append(CaptureDelivery(capture, _client(_RouteTransport(LedgerAhead()))).drain_once())
        capture.stop()
        if named != records[2].digest:
            assert reports[-1].failures == ["ack_mismatch"] and ob.read_ack(dead.directory) is None

    ack = ob.read_ack(dead.directory)
    assert reports[-1].failures == [] and ack is not None and (ack.sequence, ack.digest) == (3, records[2].digest)
    assert ob.scan_stream(dead.directory, orphan=True).unverified_tail is None, "an acknowledged tail is settled"


def test_a_dead_writers_withheld_tail_and_its_damaged_bytes_stay_visible_in_the_backlog(tmp_path):
    """Codex Checkpoint C finding 3: once the verified prefix is acknowledged, the withheld tail is still pending (its
    age warns; nothing reads as caught up) and the torn bytes after it are reported apart, on every pass."""
    root = host_outbox_root(tmp_path / "config")
    dead = ob.StreamWriter(root)
    records = [dead.append({"kind": uc.STREAM_START, "at": _AT.isoformat()}) for _ in range(3)]
    dead._abandon_segment()
    dead._lock_handle.close()  # type: ignore[union-attr]
    (segment,) = [p for p in dead.directory.iterdir() if p.name.startswith(ob._SEGMENT_PREFIX)]
    torn = b"f" * 64 + b' {"stream"'
    with open(segment, "ab") as handle:
        handle.write(torn)
    capture = DurableCapture(ob.OutboxWriter(root), clock=lambda: _AT)
    warnings: list[str] = []
    delivery = CaptureDelivery(capture, _client(_RouteTransport(_AckingStore())), warn=warnings.append, clock=lambda: _AT + timedelta(hours=24))

    passes = [delivery.drain_once().backlog for _ in range(2)]
    capture.stop()

    ack = ob.read_ack(dead.directory)
    assert ack is not None and ack.sequence == 2, "the verified prefix is acknowledged; the tail is withheld"
    for backlog in passes:
        assert (backlog.pending_events, backlog.pending_bytes, backlog.oldest_pending_at) == (1, len(records[2].line) + 1, _AT)
        assert backlog.damaged_bytes == len(torn) and backlog.warnings == ("pending_age",)
    assert len(warnings) == 1 and "damaged=" in warnings[0]


def test_a_live_foreign_stream_is_left_to_its_own_process(tmp_path):
    root = host_outbox_root(tmp_path / "config")
    foreign = ob.StreamWriter(root)
    foreign.append({"kind": uc.STREAM_START, "at": _AT.isoformat()})
    capture = DurableCapture(ob.OutboxWriter(root), clock=lambda: _AT)
    store = _AckingStore()

    CaptureDelivery(capture, _client(_RouteTransport(store))).drain_once()

    assert foreign.stream_id not in {b.stream_id for b in store.batches}
    foreign.close()
    capture.stop()


def test_batches_respect_the_record_count_and_body_limits(tmp_path):
    capture = _capture(tmp_path)
    for _ in range(uc.MAX_RECORDS + 40):
        capture.writer.submit({"kind": uc.STREAM_START, "at": _AT.isoformat()})
    _fill(capture, 0)
    store = _AckingStore()
    transport = _RouteTransport(store)

    CaptureDelivery(capture, _client(transport)).drain_once()

    assert len(store.batches) >= 2 and all(len(b.records) <= uc.MAX_RECORDS for b in store.batches)
    assert all(len(body) <= uc.MAX_BODY_BYTES for body in transport.bodies)
    capture.stop()


def test_an_acknowledgement_that_names_another_record_is_never_stored(tmp_path):
    capture = _capture(tmp_path)
    _fill(capture, 1)

    class _Lying(_AckingStore):
        def ingest(self, batch: uc.CaptureBatch) -> Any:
            from optimus_gateway.usage_store import IngestResult

            first = batch.records[0]
            return IngestResult(uc.CaptureAck(_LEDGER, batch.stream_id, first.sequence, first.digest), 1, 0)

    report = CaptureDelivery(capture, _client(_RouteTransport(_Lying()))).drain_once()

    assert report.failures == ["ack_mismatch"] and ob.read_ack(capture.writer.directory) is None
    capture.stop()


def test_the_route_refuses_bad_credentials_and_malformed_batches_before_the_ledger():
    store = _AckingStore()
    config = _RouteTransport(store).config

    assert handle_usage_capture_request(authorization_header="Bearer wrong", raw_body=b"{}", config=config)[0] == 401
    status, body = handle_usage_capture_request(authorization_header=f"Bearer {_SECRET}", raw_body=b'{"x":1}', config=config)
    assert (status, body["code"]) == (400, "CAPTURE_UNKNOWN_FIELD") and store.batches == []


def test_the_ledger_recomputes_the_hosts_identity_digest_exactly():
    from decimal import Decimal

    from optimus.usage.capture_events import identity_parts
    from optimus.usage.turn_settlement import TurnCostSummary
    from optimus_gateway.usage_store import _identities_digest

    summary = TurnCostSummary(turn_id="s:1", known_subtotal_usd=Decimal("0"), unknown_attempt_ids=("u:1", "café"), receipt_ids=("s:1:planning:1:1", "u:1"))
    parts, host_digest = identity_parts("e" * 32, summary)

    settled = sum((p["settled_attempt_ids"] for p in parts), [])
    unknown = sum((p["unknown_attempt_ids"] for p in parts), [])
    assert _identities_digest("e" * 32, settled, unknown) == host_digest
    assert _identities_digest("e" * 32, settled[::-1], unknown) != host_digest
