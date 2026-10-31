"""Plan 12.8 Task 3: host delivery of outbox streams through the real Gateway capture route and contract. The ledger
here is a unit-tier double that acknowledges what it is given; the real Postgres ledger is the live tier's
(`requires_plan12_capture_postgres`)."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
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
