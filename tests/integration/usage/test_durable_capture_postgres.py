"""Plan 12.8 K3 on a real, released, disposable Postgres (`requires_plan12_capture_postgres`): the Gateway-owned
ledger's migrations, atomic commit, idempotent replay, receipt conflicts and aliases, database-enforced immutability,
unavailable spans, concurrent drains, an outage and restart, and host delivery through the real capture route.

The resource comes only from the file named by P128_CAPTURE_K3_CONFIG (host, port, container, image_id, volume, user,
database) and the password from P128_CAPTURE_K3_PASSWORD; it is admitted by inspecting the container (loopback port,
its own volume, the released image) before any connection. Without them every case skips as UNRUN."""

from __future__ import annotations

import dataclasses
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
from optimus.usage.turn_settlement import ReceiptConflictError, StageReceipt, TurnSettlement
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
    """A turn as the production call sites produce it: each receipt follows its host request's pre-dispatch intent."""
    settlement = TurnSettlement(capture=capture, session_id="s")
    invocation = settlement.open_invocation(turn)
    invocation.start()
    for receipt in receipts:
        capture.intent(turn, receipt.attempt_id, stage="planning")
        try:
            settlement.record_attempt(receipt)
        except Exception:  # noqa: BLE001 - a conflicting receipt is the case under test
            pass
    invocation.end()
    settlement.finalize_turn(turn)


def _gateway_evidence(store: UsageStore, tmp_path: Path, receipts: list[StageReceipt], *, outcomes: tuple[str, ...] = ("completed",),
                      gateway_request_id: str | None = None) -> None:
    """The Gateway's physical-attempt records (attempts 1..n with these outcomes) for each receipt's host request, under the
    receipt's own Gateway request unless another is named, committed to the ledger as its drain would."""
    writer = ob.OutboxWriter(tmp_path / "gateway-outbox")
    for receipt in receipts:
        gw = gateway_request_id or receipt.gateway_request_id
        for number, outcome in enumerate(outcomes, start=1):
            writer.submit({"kind": uc.GATEWAY_ATTEMPT_INTENT, "at": _AT.isoformat(), "gateway_request_id": gw,
                           "host_request_id": receipt.attempt_id, "attempt": number, "route": None})
            writer.submit({"kind": uc.GATEWAY_ATTEMPT_OUTCOME, "at": _AT.isoformat(), "gateway_request_id": gw, "attempt": number,
                           "outcome": outcome, "http_status": 503 if outcome == "failed" else None, "cost_usd": None,
                           "billing_units": None, "intent_confirmed": True})
    writer.close()
    scan = ob.scan_stream(writer.directory)
    store.ingest(uc.parse_batch(uc.build_batch("gateway", scan.stream_id, None, 0, ob.GENESIS, list(scan.records))))


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
    attempt = f"{uuid.uuid4().hex}:planning:1:1"
    receipt = _receipt("s:1", attempt)
    capture = _capture(tmp_path)
    _turn(capture, "s:1", [receipt])
    batch = _batch(capture)

    result = store.ingest(batch)

    assert result.ack.sequence == batch.records[-1].sequence and result.ack.digest == batch.records[-1].digest
    events = _rows(released, "SELECT count(*) FROM optimus_usage.capture_event WHERE stream_id = %s", batch.stream_id)
    assert events == [(len(batch.records),)]
    assert _rows(released, "SELECT reported_cost_usd FROM optimus_usage.attempt_receipt WHERE attempt_id = %s", attempt) == [(Decimal("0.25"),)]
    epoch = _rows(released, "SELECT state, reasons FROM optimus_usage.coverage_epoch WHERE stream_id = %s AND turn_id = %s", batch.stream_id, "s:1")
    assert epoch == [("incomplete", ["physical_evidence_missing", "receipt_without_physical"])], "a host request alone cannot prove its physical attempts"
    _gateway_evidence(store, tmp_path, [receipt])
    epoch = _rows(released, "SELECT state, reasons FROM optimus_usage.coverage_epoch WHERE stream_id = %s AND turn_id = %s", batch.stream_id, "s:1")
    assert epoch == [("complete", [])], "the Gateway's evidence arriving later certifies it"
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
    epochs = _rows(released, "SELECT state, reasons FROM optimus_usage.coverage_epoch WHERE stream_id = %s AND close_sequence IS NOT NULL", capture.writer.stream_id)
    assert epochs == [("incomplete", ["physical_evidence_missing", "receipt_without_physical"])] * 4, "all four closed; only the Gateway's evidence is missing"
    capture.stop()


BOUNDARY_ENV = "P128_CAPTURE_K3_ACCOUNTING_ROOT"
RUN_ENV = "P128_CAPTURE_K3_RUN_ID"
_READY_SECONDS = 60
_GATEWAY_CHILD = """
import json, sys
from pathlib import Path
import keyring
from optimus_gateway import usage_capture
from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.server import serve_gateway
from tests.support.plan12_capture_provisioner import bound_accounting
section, root, run_id, approved = json.loads(sys.argv[3]), Path(sys.argv[1]), sys.argv[4], sys.argv[5]
literal, config = bound_accounting(section, root, run_id)  # verified again here, before the keyring read
if literal != approved:
    raise SystemExit("accounting_config_changed_after_admission")
accounting = usage_capture.start_accounting(root, config, keyring_backend=keyring, log=lambda line: print(line, file=sys.stderr, flush=True))
service = GatewayServiceConfig(bind_host="127.0.0.1", bind_port=0, shared_secret=sys.argv[2], provider="openrouter",
                               provider_api_key="unused-in-this-case", base_url="https://openrouter.ai/api/v1", usage_store=accounting.store)  # pragma: allowlist secret - a placeholder key for a provider never called here
server = serve_gateway(config=service)
print(json.dumps({"port": server.server_address[1], "store": accounting.store is not None}), flush=True)
try:
    server.serve_forever()
finally:
    accounting.stop()
"""


@pytest.fixture(scope="module")
def boundary() -> tuple[dict[str, Any], Path, str, str]:
    """Admission before any child launch or secret access: the released container, then the provisioned root bound to it
    and to this run's role and keyring entry. A provisioned root that names anything else fails the case."""
    if os.environ.get(PASSWORD_ENV):
        pytest.skip("UNRUN: the credential-boundary case runs only without the ledger password in the pytest environment")
    path, root, run_id = os.environ.get(CONFIG_ENV, ""), os.environ.get(BOUNDARY_ENV, ""), os.environ.get(RUN_ENV, "")
    if not path or not root or not run_id:
        pytest.skip(f"UNRUN: {CONFIG_ENV}, {BOUNDARY_ENV} or {RUN_ENV} names no provisioned run; no process was started")
    from tests.support.plan12_capture_provisioner import bound_accounting
    from tools.plan12_memory import probes

    section = json.loads(Path(path).read_text(encoding="utf-8"))
    probes.admit_postgres_resource(section, probes.docker_inspect)
    literal, _ = bound_accounting(section, Path(root), run_id)
    return section, Path(root), run_id, literal


def _ready_line(child: subprocess.Popen[str]) -> str:
    """The child's readiness line within a deadline; on timeout the child is terminated and reaped and the case fails
    with its sanitized stderr."""
    from tools.plan12_memory import probes

    lines: list[str] = []
    reader = threading.Thread(target=lambda: lines.append(child.stdout.readline()), daemon=True)  # type: ignore[union-attr]
    reader.start()
    reader.join(_READY_SECONDS)
    if lines and lines[0]:
        return lines[0]
    child.kill()
    _, stderr = child.communicate(timeout=30)
    pytest.fail(f"the Gateway child was not ready within {_READY_SECONDS}s: {probes.sanitize(stderr[-2000:])[0]}")


def _psql(section: dict[str, Any], sql: str) -> list[str]:
    """Readback inside the container's own local socket: the pytest process never holds the ledger password."""
    completed = subprocess.run(
        ["docker", "exec", section["container"], "psql", "-U", section["user"], "-d", section["database"], "-tAc", sql],
        check=True, capture_output=True, text=True, timeout=60,
    )
    return [line for line in completed.stdout.splitlines() if line]


@pytest.mark.requires_os_keyring
def test_the_host_delivers_over_http_to_a_gateway_process_that_alone_holds_the_ledger_credential(boundary, tmp_path):
    """Checkpoint B finding 7: the provisioner placed the credential in the Gateway's keyring namespace outside pytest; a
    separate Gateway process resolves it through the production `start_accounting`; the host side holds only the Gateway
    URL and key and delivers through the production urllib transport."""
    import secrets as secrets_module
    import sys

    from optimus.config.gateway import OptimusGatewaySettings
    from optimus.gateway.client import GatewayClient
    from optimus.usage.capture_delivery import CaptureDelivery

    section, root, run_id, literal = boundary
    key = secrets_module.token_hex(16)
    environ = {k: v for k, v in os.environ.items() if k != PASSWORD_ENV}
    child = subprocess.Popen([sys.executable, "-c", _GATEWAY_CHILD, str(root), key, json.dumps(section), run_id, literal],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environ)
    try:
        ready = json.loads(_ready_line(child))
        assert ready["store"] is True, "the Gateway process resolved its own credential"
        capture = _capture(tmp_path)
        for n in range(3):
            _turn(capture, f"s:{n}", [_receipt(f"s:{n}", f"{uuid.uuid4().hex}:planning:1:1")])
        deadline = time.monotonic() + 10
        while capture.writer.stats().pending and time.monotonic() < deadline:
            time.sleep(0.01)
        client = GatewayClient(settings=OptimusGatewaySettings(gateway_url=f"http://127.0.0.1:{ready['port']}", optimus_api_key=key))
        report = CaptureDelivery(capture, client).drain_once()
        stream, confirmed = capture.writer.stream_id, capture.writer.stats().confirmed_sequence
        capture.stop()
    finally:
        child.terminate()
        try:
            child.wait(30)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(30)

    assert os.environ.get(PASSWORD_ENV) is None
    assert report.failures == [] and report.committed == confirmed
    assert _psql(section, f"SELECT count(*) FROM optimus_usage.capture_event WHERE stream_id = '{stream}'") == [str(confirmed)]
    assert _psql(section, f"SELECT writer, sequence FROM optimus_usage.drain_cursor WHERE stream_id = '{stream}'") == [f"host|{confirmed}"]


def _epoch_state(released, stream_id: str) -> list[tuple[Any, ...]]:
    return _rows(released, "SELECT state, reasons FROM optimus_usage.coverage_epoch WHERE stream_id = %s AND close_sequence IS NOT NULL", stream_id)


@pytest.mark.parametrize(
    ("outcomes", "other_request", "reasons"),
    [
        (("completed",), False, []),
        (("uncertain",), False, ["physical_attempt_uncertain"]),
        (("completed",), True, ["physical_receipt_unmatched", "receipt_without_physical"]),  # unrelated Gateway IDs prove nothing
        (("failed", "failed", "completed"), False, ["physical_cost_unresolved"]),  # legacy 503 retries: earlier costs unknown
        (("not_sent", "completed"), False, []),  # a refused dispatch reached no model
        (("failed",), False, ["physical_attempt_missing"]),  # a completed receipt, but no completed attempt recorded
    ],
)
def test_physical_evidence_decides_certification(released, store, tmp_path, outcomes, other_request, reasons):
    attempt = f"{uuid.uuid4().hex}:planning:1:1"
    receipt = _receipt("s:1", attempt)
    capture = _capture(tmp_path)
    _turn(capture, "s:1", [receipt])
    batch = _batch(capture)
    store.ingest(batch)

    _gateway_evidence(store, tmp_path, [receipt], outcomes=outcomes, gateway_request_id=f"gw-{uuid.uuid4().hex}" if other_request else None)

    expected = [("incomplete", reasons)] if reasons else [("complete", [])]
    assert _epoch_state(released, batch.stream_id) == expected


def test_a_late_integrity_failure_from_production_settlement_downgrades_a_certified_epoch(released, store, tmp_path):
    attempt = f"{uuid.uuid4().hex}:planning:1:1"
    receipt = _receipt("s:1", attempt)
    capture = _capture(tmp_path)
    settlement = TurnSettlement(capture=capture, session_id="s")
    invocation = settlement.open_invocation("s:1")
    invocation.start()
    capture.intent("s:1", attempt, stage="planning")
    settlement.record_attempt(receipt)
    invocation.end()
    settlement.finalize_turn("s:1")
    deadline = time.monotonic() + 10
    while capture.writer.stats().pending and time.monotonic() < deadline:
        time.sleep(0.01)
    first = ob.scan_stream(capture.writer.directory)
    store.ingest(uc.parse_batch(uc.build_batch("host", first.stream_id, None, 0, ob.GENESIS, list(first.records))))
    _gateway_evidence(store, tmp_path, [receipt])
    assert _epoch_state(released, first.stream_id) == [("complete", [])]

    with pytest.raises(ReceiptConflictError):  # the same attempt reported again with other facts, after the close
        settlement.record_attempt(_receipt("s:1", attempt, cost="0.99", gw=receipt.gateway_request_id))
    last = first.records[-1]
    store.ingest(_batch(capture, after=(last.sequence, last.digest), ledger=store.ledger_instance))

    assert _epoch_state(released, first.stream_id) == [("incomplete", ["integrity_failure"])]


def test_a_stale_certification_waits_for_the_epoch_and_never_erases_a_downgrade(released, store, tmp_path, monkeypatch):
    """Two connections, deterministically interleaved: the Gateway drain's certification has read its evidence and is
    held there; a late receipt on the host stream must wait for the epoch rather than commit a downgrade the held
    certification would then overwrite."""
    attempt = f"{uuid.uuid4().hex}:planning:1:1"
    receipt = _receipt("s:1", attempt)
    capture = _capture(tmp_path)
    _turn(capture, "s:1", [receipt])
    capture.receipt(_receipt("s:1", f"{attempt}:late"))  # appended after the close, delivered in a second batch
    batch = _batch(capture)
    split = next(n for n, r in enumerate(batch.records) if r.payload["kind"] == uc.ATTEMPT_RECEIPT and r.payload["late"])
    store.ingest(dataclasses.replace(batch, records=batch.records[:split]))
    held, release = threading.Event(), threading.Event()
    gateway_store = UsageStore(released["conninfo"])
    original = UsageStore._physical

    def paused(self, conn, intents, answered):
        reasons = original(self, conn, intents, answered)
        if self is gateway_store:
            held.set()
            release.wait(30)
        return reasons

    monkeypatch.setattr(UsageStore, "_physical", paused)
    gateway = threading.Thread(target=_gateway_evidence, args=(gateway_store, tmp_path, [receipt]))
    gateway.start()
    assert held.wait(30), "the Gateway's certification read its evidence"
    prior = batch.records[split - 1]
    results: list[Any] = []
    rest = dataclasses.replace(batch, after_sequence=prior.sequence, after_digest=prior.digest, ledger_instance=store.ledger_instance,
                               records=batch.records[split:])
    late = threading.Thread(target=lambda: results.append(UsageStore(released["conninfo"]).ingest(rest)))
    late.start()
    late.join(2)
    waiting = late.is_alive()
    release.set()
    gateway.join(30)
    late.join(30)

    assert waiting, "the late receipt's certification waited for the epoch"
    assert len(results) == 1 and results[0].inserted == len(rest.records)
    assert "late_receipt" in _epoch_state(released, batch.stream_id)[0][1]


def test_a_late_receipt_or_a_ledger_conflict_downgrades_a_certified_epoch(released, store, tmp_path):
    attempt = f"{uuid.uuid4().hex}:planning:1:1"
    receipt, late = _receipt("s:1", attempt), _receipt("s:1", f"{attempt}:late")
    capture = _capture(tmp_path / "a")
    _turn(capture, "s:1", [receipt])
    capture.receipt(late)  # after the close: appended late
    batch = _batch(capture)
    store.ingest(batch)
    _gateway_evidence(store, tmp_path / "g", [receipt, late])

    assert ("late_receipt" in _epoch_state(released, batch.stream_id)[0][1])

    other = f"{uuid.uuid4().hex}:planning:1:1"
    clean_receipt = _receipt("s:2", other, gw="gw-shared-" + other)
    clean = _capture(tmp_path / "b")
    _turn(clean, "s:2", [clean_receipt])
    clean_batch = _batch(clean)
    store.ingest(clean_batch)
    _gateway_evidence(store, tmp_path / "h", [clean_receipt])
    assert _epoch_state(released, clean_batch.stream_id) == [("complete", [])]
    rival = _capture(tmp_path / "c")  # another stream settles the same Gateway request differently
    _turn(rival, "s:3", [_receipt("s:3", other, cost="0.99", gw="gw-shared-" + other)])
    store.ingest(_batch(rival))

    assert "receipt_conflict" in _epoch_state(released, clean_batch.stream_id)[0][1]


def test_an_alias_reserves_its_attempt_identity_sequentially_and_concurrently(released, store, tmp_path):
    attempt, gw = f"{uuid.uuid4().hex}:planning:1:1", f"gw-{uuid.uuid4().hex}"
    first = _capture(tmp_path / "a")
    _turn(first, "s:1", [_receipt("s:1", attempt, gw=gw)])
    store.ingest(_batch(first))
    alias = _capture(tmp_path / "b")
    _turn(alias, "s:2", [_receipt("s:1", attempt + "-alias", gw=gw)])
    store.ingest(_batch(alias))
    reuse = _capture(tmp_path / "c")  # the alias's ID reused for a different Gateway request
    _turn(reuse, "s:3", [_receipt("s:1", attempt + "-alias", gw=f"gw-{uuid.uuid4().hex}")])

    result = store.ingest(_batch(reuse))

    assert result.ack.conflicts == 1
    assert _rows(released, "SELECT count(*) FROM optimus_usage.attempt_receipt WHERE attempt_id = %s", attempt + "-alias") == [(0,)]

    shared_attempt, shared_gw = f"{uuid.uuid4().hex}:planning:1:1", f"gw-{uuid.uuid4().hex}"
    batches = []
    for n in range(4):  # four streams race to settle one attempt under different requests
        racer = _capture(tmp_path / f"r{n}")
        _turn(racer, f"s:{n}", [_receipt("s:1", shared_attempt, gw=shared_gw if n == 0 else f"gw-{uuid.uuid4().hex}")])
        batches.append(_batch(racer))
    barrier = threading.Barrier(4)

    def drain(batch: uc.CaptureBatch) -> None:
        barrier.wait(10)
        UsageStore(released["conninfo"]).ingest(batch)

    workers = [threading.Thread(target=drain, args=(b,)) for b in batches]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(60)

    canonical = _rows(released, "SELECT count(*) FROM optimus_usage.attempt_receipt WHERE attempt_id = %s", shared_attempt)
    conflicts = _rows(released, "SELECT count(*) FROM optimus_usage.receipt_conflict WHERE attempt_id = %s", shared_attempt)
    assert canonical == [(1,)] and conflicts == [(3,)]


def test_a_held_stream_lock_makes_ingest_retryable_within_its_bound(released, store, tmp_path):
    capture = _capture(tmp_path)
    _turn(capture, "s:1", [])
    batch = _batch(capture)
    with psycopg.connect(released["conninfo"]) as holder:
        holder.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (batch.stream_id,))  # held until rollback
        bounded = UsageStore(released["conninfo"], lock_timeout_ms=500)
        started = time.monotonic()
        with pytest.raises(StoreError) as waited:
            bounded.ingest(batch)
        elapsed = time.monotonic() - started
        holder.rollback()

    assert waited.value.code == "unavailable" and elapsed < 5
    assert _rows(released, "SELECT count(*) FROM optimus_usage.capture_event WHERE stream_id = %s", batch.stream_id) == [(0,)]
    assert store.ingest(batch).inserted == len(batch.records), "after the holder lets go, the same batch commits"


def test_a_receipt_with_no_recorded_intent_is_never_certified(released, store, tmp_path):
    capture = _capture(tmp_path)
    settlement = TurnSettlement(capture=capture, session_id="s")
    invocation = settlement.open_invocation("s:1")
    invocation.start()
    settlement.record_attempt(_receipt("s:1", f"{uuid.uuid4().hex}:planning:1:1"))  # sent without a pre-dispatch intent
    invocation.end()
    settlement.finalize_turn("s:1")
    batch = _batch(capture)

    store.ingest(batch)

    assert _epoch_state(released, batch.stream_id) == [("incomplete", ["receipt_without_intent", "receipt_without_physical"])]
