"""Plan 12.8 K3 on a real, released, disposable Postgres (`requires_plan12_capture_postgres`): the Gateway-owned
ledger's migrations, atomic commit, idempotent replay, receipt conflicts and aliases, database-enforced immutability,
unavailable spans, concurrent drains, an outage and restart, and host delivery through the real capture route.

The resource comes only from the file named by P128_CAPTURE_K3_CONFIG (host, port, container, image_id, volume, user,
database) and the password from P128_CAPTURE_K3_PASSWORD; it is admitted by inspecting the container (loopback port,
its own volume, the released image) before any connection. Without them every case skips as UNRUN."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import pytest

from optimus.gateway.models import GatewayUsage
from optimus.usage.durable_capture import DurableCapture, host_outbox_root
from optimus.usage.turn_settlement import StageReceipt, TurnSettlement
from optimus_gateway.usage_store import StoreError, UsageStore
from optimus_security import durable_outbox as ob
from optimus_security import usage_capture_contract as uc

pytestmark = [pytest.mark.requires_plan12_capture_postgres]

CONFIG_ENV = "P128_CAPTURE_K3_CONFIG"
PASSWORD_ENV = "P128_CAPTURE_K3_PASSWORD"  # pragma: allowlist secret - an environment variable name, not a credential
_AT = datetime(2026, 10, 31, tzinfo=UTC)


@pytest.fixture(scope="module")
def released() -> dict[str, Any]:
    path, password = os.environ.get(CONFIG_ENV, ""), os.environ.get(PASSWORD_ENV, "")
    if not path or not password:
        pytest.skip(f"UNRUN: {CONFIG_ENV} or {PASSWORD_ENV} names no released K3 resource; no connection was made")
    from tools.plan12_memory import probes

    section = json.loads(Path(path).read_text(encoding="utf-8"))
    identity = probes.admit_postgres_resource(section, probes.docker_inspect)
    conninfo = f"host={section['host']} port={section['port']} dbname={section['database']} user={section['user']} password={password}"
    return {"section": section, "identity": identity, "conninfo": conninfo}


@pytest.fixture
def store(released) -> UsageStore:
    usage_store = UsageStore(released["conninfo"])
    usage_store.migrate()
    return usage_store


def _capture(tmp_path: Path) -> DurableCapture:
    return DurableCapture(ob.OutboxWriter(host_outbox_root(tmp_path / "config")), ack_wait=5.0, clock=lambda: _AT)


def _receipt(turn: str, attempt: str, *, cost: str = "0.25", gw: str | None = None) -> StageReceipt:
    gw = gw or f"gw-{uuid.uuid4().hex}"
    usage = GatewayUsage(gateway_request_id=gw, provider="openrouter", billing_units=3, cost_usd=Decimal(cost))
    return StageReceipt(session_id="s", turn_id=turn, stage="planning", attempt_id=attempt, gateway_request_id=gw, outcome="completed",
                        reported_cost_usd=Decimal(cost), recorded_at=_AT, gateway_usage=usage)


def _turn(capture: DurableCapture, turn: str, receipts: list[StageReceipt]) -> None:
    settlement = TurnSettlement(capture=capture, session_id="s")
    invocation = settlement.open_invocation(turn)
    invocation.start()
    for receipt in receipts:
        try:
            settlement.record_attempt(receipt)
        except Exception:  # noqa: BLE001 - a conflicting receipt is the case under test
            pass
    invocation.end()
    settlement.finalize_turn(turn)


def _batch(capture: DurableCapture, after: tuple[int, str] = (0, ob.GENESIS), ledger: str | None = None) -> uc.CaptureBatch:
    capture.stop()
    scan = ob.scan_stream(capture.writer.directory)
    records = [r for r in scan.records if r.sequence > after[0]]
    return uc.parse_batch(uc.build_batch("host", scan.stream_id, ledger, after[0], after[1], records))


def _rows(released, sql: str, *args: Any) -> list[tuple[Any, ...]]:
    with psycopg.connect(released["conninfo"]) as conn:  # a new connection: durable readback only
        return conn.execute(sql, args).fetchall()


def test_migrations_are_pinned_and_the_ledger_instance_is_stable(released, store):
    again = UsageStore(released["conninfo"]).migrate()

    assert again == store.ledger_instance
    assert _rows(released, "SELECT filename FROM optimus_usage_schema_migrations") == [("001_durable_capture.sql",)]


def test_a_batch_commits_atomically_and_reads_back_from_a_new_connection(released, store, tmp_path):
    capture = _capture(tmp_path)
    _turn(capture, "s:1", [_receipt("s:1", "s:1:planning:1:1")])
    batch = _batch(capture)

    result = store.ingest(batch)

    assert result.ack.sequence == batch.records[-1].sequence and result.ack.digest == batch.records[-1].digest
    events = _rows(released, "SELECT count(*) FROM optimus_usage.capture_event WHERE stream_id = %s", batch.stream_id)
    assert events == [(len(batch.records),)]
    assert _rows(released, "SELECT reported_cost_usd FROM optimus_usage.attempt_receipt WHERE attempt_id = %s", "s:1:planning:1:1") == [(Decimal("0.25"),)]
    epoch = _rows(released, "SELECT state, reasons FROM optimus_usage.coverage_epoch WHERE stream_id = %s AND turn_id = %s", batch.stream_id, "s:1")
    assert epoch == [("complete", [])]
    cursor = _rows(released, "SELECT sequence, record_digest FROM optimus_usage.drain_cursor WHERE stream_id = %s", batch.stream_id)
    assert cursor == [(result.ack.sequence, result.ack.digest)]


def test_a_lost_acknowledgement_replays_idempotently(released, store, tmp_path):
    capture = _capture(tmp_path)
    _turn(capture, "s:1", [_receipt("s:1", f"{uuid.uuid4().hex}:planning:1:1")])
    batch = _batch(capture)

    first, second = store.ingest(batch), store.ingest(batch)

    assert first.ack == second.ack and second.inserted == 0 and second.replayed == len(batch.records)
    assert _rows(released, "SELECT count(*) FROM optimus_usage.capture_event WHERE stream_id = %s", batch.stream_id) == [(len(batch.records),)]


def test_a_contradictory_duplicate_is_evidence_and_an_identical_alias_is_linked(released, store, tmp_path):
    attempt = f"{uuid.uuid4().hex}:planning:1:1"
    gw = f"gw-{uuid.uuid4().hex}"
    first = _capture(tmp_path / "a")
    _turn(first, "s:1", [_receipt("s:1", attempt, gw=gw)])
    store.ingest(_batch(first))
    second = _capture(tmp_path / "b")  # another process replays the same Gateway request, and a contradiction
    _turn(second, "s:2", [_receipt("s:1", attempt + "x", gw=gw), _receipt("s:1", attempt, cost="0.99", gw=f"gw-{uuid.uuid4().hex}")])

    result = store.ingest(_batch(second))

    assert result.ack.conflicts >= 1
    assert _rows(released, "SELECT reported_cost_usd FROM optimus_usage.attempt_receipt WHERE attempt_id = %s", attempt) == [(Decimal("0.25"),)]
    assert _rows(released, "SELECT canonical_attempt_id FROM optimus_usage.receipt_alias WHERE attempt_id = %s", attempt + "x") == [(attempt,)]
    assert _rows(released, "SELECT reason FROM optimus_usage.receipt_conflict WHERE attempt_id = %s", attempt) == [("attempt_facts_differ",)]


@pytest.mark.parametrize("statement", [
    "UPDATE optimus_usage.capture_event SET kind = 'x' WHERE stream_id = %s",
    "DELETE FROM optimus_usage.capture_event WHERE stream_id = %s",
    "TRUNCATE optimus_usage.capture_event CASCADE",  # a plain TRUNCATE is refused by the foreign keys already
])
def test_facts_are_immutable_in_the_database(released, store, tmp_path, statement):
    capture = _capture(tmp_path)
    _turn(capture, "s:1", [])
    batch = _batch(capture)
    store.ingest(batch)

    with psycopg.connect(released["conninfo"]) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(statement, () if "TRUNCATE" in statement else (batch.stream_id,))


def test_a_sender_ahead_of_the_ledger_starts_with_an_unavailable_span_and_a_different_overlap_is_refused(released, store, tmp_path):
    capture = _capture(tmp_path)
    _turn(capture, "s:1", [])
    capture.stop()
    scan = ob.scan_stream(capture.writer.directory)
    head, tail = scan.records[:2], scan.records[2:]
    after = (head[-1].sequence, head[-1].digest)

    store.ingest(uc.parse_batch(uc.build_batch("host", scan.stream_id, "f" * 32, after[0], after[1], tail)))
    span = _rows(released, "SELECT reasons FROM optimus_usage.coverage_epoch WHERE epoch_id LIKE %s", f"unavailable:{scan.stream_id}:%")
    forged = ob.frame(scan.stream_id, tail[0].sequence, after[1], {"kind": uc.STREAM_START, "at": _AT.isoformat()})
    with pytest.raises(StoreError) as refused:
        store.ingest(uc.parse_batch(uc.build_batch("host", scan.stream_id, store.ledger_instance, after[0], after[1], [forged])))

    assert span and span[0][0][0] == f"stream_span_unavailable:1-{after[0]}"
    assert refused.value.code == "cursor_mismatch"


def test_concurrent_drains_of_one_batch_commit_it_once(released, store, tmp_path):
    capture = _capture(tmp_path)
    _turn(capture, "s:1", [_receipt("s:1", f"{uuid.uuid4().hex}:planning:1:1")])
    batch = _batch(capture)
    acks: list[Any] = []
    barrier = threading.Barrier(4)

    def drain() -> None:
        barrier.wait(10)
        acks.append(UsageStore(released["conninfo"]).ingest(batch).ack)

    workers = [threading.Thread(target=drain) for _ in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(60)

    assert len(acks) == 4 and len({(a.sequence, a.digest) for a in acks}) == 1
    assert _rows(released, "SELECT count(*) FROM optimus_usage.capture_event WHERE stream_id = %s", batch.stream_id) == [(len(batch.records),)]


def test_an_outage_is_retryable_and_committed_rows_survive_a_restart(released, store, tmp_path):
    container = released["section"]["container"]
    capture = _capture(tmp_path)
    _turn(capture, "s:1", [_receipt("s:1", f"{uuid.uuid4().hex}:planning:1:1")])
    batch = _batch(capture)
    committed = store.ingest(batch)

    subprocess.run(["docker", "stop", "--time", "10", container], check=True, capture_output=True, timeout=120)
    try:
        with pytest.raises(StoreError) as down:
            UsageStore(released["conninfo"], connect_timeout=2).ingest(batch)
    finally:
        subprocess.run(["docker", "start", container], check=True, capture_output=True, timeout=120)
    deadline = time.monotonic() + 60
    while True:
        try:
            replay = UsageStore(released["conninfo"]).ingest(batch)
            break
        except StoreError:
            if time.monotonic() > deadline:
                raise
            time.sleep(1)

    assert down.value.code == "unavailable"
    assert replay.ack == committed.ack and replay.inserted == 0
    assert _rows(released, "SELECT count(*) FROM optimus_usage.capture_event WHERE stream_id = %s", batch.stream_id) == [(len(batch.records),)]


def test_host_delivery_through_the_real_route_commits_acknowledges_and_compacts(released, store, tmp_path):
    from optimus.config.gateway import OptimusGatewaySettings
    from optimus.gateway.client import GatewayClient, GatewayRequest
    from optimus.gateway.errors import GatewayHttpError
    from optimus.usage.capture_delivery import CaptureDelivery
    from optimus_gateway.models import GatewayServiceConfig
    from optimus_gateway.usage_capture import handle_usage_capture_request

    secret = "k3-route-secret"  # pragma: allowlist secret
    config = GatewayServiceConfig(bind_host="127.0.0.1", bind_port=0, shared_secret=secret, provider="openrouter",
                                  provider_api_key="or-test", base_url="https://openrouter.ai/api/v1", usage_store=store)  # pragma: allowlist secret

    class Route:
        def post_json(self, request: GatewayRequest) -> dict[str, Any]:
            status, body = handle_usage_capture_request(
                authorization_header=request.headers.get("Authorization"), raw_body=json.dumps(request.payload).encode(), config=config
            )
            if status != 200:
                raise GatewayHttpError(status, json.dumps(body))
            return body

    capture = DurableCapture(ob.OutboxWriter(host_outbox_root(tmp_path / "config"), segment_bytes=700), ack_wait=5.0, clock=lambda: _AT)
    for n in range(4):
        _turn(capture, f"s:{n}", [_receipt(f"s:{n}", f"{uuid.uuid4().hex}:planning:1:1")])
    deadline = time.monotonic() + 10
    while capture.writer.stats().pending and time.monotonic() < deadline:
        time.sleep(0.01)  # delivery sends only what the writer has confirmed
    delivery = CaptureDelivery(capture, GatewayClient(settings=OptimusGatewaySettings(gateway_url="http://127.0.0.1:1", optimus_api_key=secret), transport=Route()))

    report = delivery.drain_once()

    ack = ob.read_ack(capture.writer.directory)
    assert report.failures == [] and ack is not None and ack.ledger_instance == store.ledger_instance
    assert report.compacted >= 1
    assert _rows(released, "SELECT count(*) FROM optimus_usage.coverage_epoch WHERE stream_id = %s AND state = 'complete'", capture.writer.stream_id) == [(4,)]
    capture.stop()


@pytest.mark.requires_os_keyring_write
def test_the_gateway_reads_its_ledger_credential_only_from_its_keyring_namespace_and_drains(released, store, tmp_path):
    """The K3 credential path: a run-specific entry in the real OS keyring under the Gateway's own namespace, read by the
    production `start_accounting`; the host never sees it. The entry is deleted afterwards."""
    import keyring

    from optimus_gateway import usage_capture
    from optimus_security import accounting_config as ac

    section = released["section"]
    name = f"k3-{uuid.uuid4().hex}"
    root = tmp_path / "accounting"
    root.mkdir()
    (root / ac.CONFIG_NAME).write_bytes(json.dumps({
        "schema_version": 1, "host": section["host"], "port": section["port"], "database": section["database"],
        "user": section["user"], "credential_name": name, "connect_timeout_seconds": 5,
    }).encode())
    keyring.set_password(ac.KEYRING_SERVICE, name, os.environ[PASSWORD_ENV])
    accounting = None
    try:
        accounting = usage_capture.start_accounting(root, keyring_backend=keyring, log=lambda _line: None)
        assert accounting.store is not None and accounting.drain is not None
        usage_capture.begin("s:1:planning:1:1")
        usage_capture.set_request("gw-k3-credential")
        with usage_capture.physical_attempt():
            pass
        deadline = time.monotonic() + 10
        while accounting.writer.stats().pending and time.monotonic() < deadline:
            time.sleep(0.01)
        report = accounting.drain.drain_once()
    finally:
        usage_capture.end()
        if accounting is not None:
            accounting.stop()
        keyring.delete_password(ac.KEYRING_SERVICE, name)

    assert report.failures == [] and report.committed == 2
    rows = _rows(released, "SELECT writer, sequence FROM optimus_usage.drain_cursor WHERE stream_id = %s", accounting.writer.stream_id)
    assert rows == [("gateway", 2)]
    assert keyring.get_password(ac.KEYRING_SERVICE, name) is None, "the run-specific entry is gone"
