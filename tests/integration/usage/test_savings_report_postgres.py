"""Plan 12.9 Task 2 on a real, released, disposable Postgres (`requires_plan12_capture_postgres`): migration 002 upgrading
a 001 ledger in place, immutable price snapshots read back independently, the report's canonical arithmetic over
aliases, conflicts and late receipts, pagination against concurrent ingest, lock expiry within the report budget, an
outage, a replaced ledger, and real HTTP through the production host transport, including a Gateway process that alone
holds the ledger credential.

The resource is Plan 12.8's (P128_CAPTURE_K3_CONFIG and P128_CAPTURE_K3_PASSWORD), admitted by inspecting the container
before any connection. Run-specific databases are created inside that container and dropped afterwards. Without the
resource every case skips as UNRUN. References are synthetic; no model is named."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import psycopg
import pytest

from optimus.gateway.models import GatewayUsage
from optimus.usage.durable_capture import DurableCapture, host_outbox_root
from optimus.usage.turn_settlement import StageReceipt, TurnSettlement
from optimus_gateway import usage_price_snapshots, usage_store
from optimus_gateway.usage_report import handle_usage_report_request
from optimus_gateway.usage_store import StoreError, UsageStore
from optimus_model_policy.binding import compose_trusted_snapshot, packaged_defaults
from optimus_model_policy.savings_references import CategoryPrices, Reference, ReferenceSet, RuleSource, Source
from optimus_security import durable_outbox as ob
from optimus_security import usage_capture_contract as uc
from optimus_security import usage_report_contract as urc
from tests.integration.usage.test_durable_capture_postgres import _GATEWAY_CHILD, _ready_line
from tests.support.plan12_capture_k3 import AT

pytestmark = [pytest.mark.requires_plan12_capture_postgres]

CONFIG_ENV = "P128_CAPTURE_K3_CONFIG"
PASSWORD_ENV = "P128_CAPTURE_K3_PASSWORD"  # pragma: allowlist secret - an environment variable name, not a credential
BOUNDARY_ENV = "P128_CAPTURE_K3_ACCOUNTING_ROOT"
RUN_ENV = "P128_CAPTURE_K3_RUN_ID"
SECRET = "p129-report-secret"  # pragma: allowlist secret - a synthetic Gateway key for in-process routes
REFERENCES = ReferenceSet(version=1, references=tuple(
    Reference(id=f"ref-{n}", display=f"Reference {n}", unit="usd_per_million_tokens",
              prices=CategoryPrices(input="1", output="4", cached_input="0.1"), reasoning_billed_as_output=True,
              reasoning_source=RuleSource(url="https://example.test/billing", quote="Reasoning is output.", fetched_on=date(2026, 11, 1)),
              source=Source(url="https://example.test/prices", price_as_of=date(2026, 11, 1)))
    for n in range(5)
))


@pytest.fixture(scope="module")
def released() -> dict[str, Any]:
    path, password = os.environ.get(CONFIG_ENV, ""), os.environ.get(PASSWORD_ENV, "")
    if not path or not password:
        pytest.skip(f"UNRUN: {CONFIG_ENV} or {PASSWORD_ENV} names no released K3 resource; no connection was made")
    from tools.plan12_memory import probes

    section = json.loads(Path(path).read_text(encoding="utf-8"))
    identity = probes.admit_postgres_resource(section, probes.docker_inspect)
    conninfo = f"host={section['host']} port={section['port']} dbname={section['database']} user={section['user']} password={password}"
    return {"section": section, "identity": identity, "conninfo": conninfo, "password": password}


@pytest.fixture
def store(released) -> UsageStore:
    ledger = UsageStore(released["conninfo"])
    ledger.migrate()
    return ledger


@pytest.fixture
def scratch_database(released):
    """A run-specific database inside the released container, dropped afterwards: room for a second ledger."""
    section, name = released["section"], f"p129_{uuid.uuid4().hex[:16]}"
    with psycopg.connect(released["conninfo"], autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {name}")
    try:
        yield (f"host={section['host']} port={section['port']} dbname={name} user={section['user']} "
               f"password={released['password']}")
    finally:
        with psycopg.connect(released["conninfo"], autocommit=True) as admin:
            admin.execute(f"DROP DATABASE {name} WITH (FORCE)")


@pytest.fixture(autouse=True)
def synthetic_references(monkeypatch):
    monkeypatch.setattr(usage_price_snapshots, "configured_references", lambda: REFERENCES)


def _receipt(session: str, turn: str, attempt: str, *, cost: str = "0.0012", gw: str | None = None) -> StageReceipt:
    gw = gw or f"gw-{uuid.uuid4().hex}"
    usage = GatewayUsage(gateway_request_id=gw, provider="openrouter", billing_units=1200, cost_usd=Decimal(cost),
                         input_tokens=1000, output_tokens=200, cached_tokens=400, reasoning_tokens=0)
    return StageReceipt(session_id=session, turn_id=turn, stage="planning", attempt_id=attempt, gateway_request_id=gw,
                        outcome="completed", reported_cost_usd=Decimal(cost), recorded_at=AT, gateway_usage=usage,
                        provider="openrouter", input_tokens=1000, output_tokens=200, cached_tokens=400)


def _turn(capture: DurableCapture, session: str, turn: str, receipts: list[StageReceipt]) -> None:
    settlement = TurnSettlement(capture=capture, session_id=session)
    invocation = settlement.open_invocation(turn)
    invocation.start()
    for item in receipts:
        capture.intent(turn, item.attempt_id, stage="planning", session_id=session)
        try:
            settlement.record_attempt(item)
        except Exception:  # noqa: BLE001, S110 - a conflicting receipt is the case under test
            pass
    invocation.end()
    settlement.finalize_turn(turn)


def _capture(directory: Path) -> DurableCapture:
    return DurableCapture(ob.OutboxWriter(host_outbox_root(directory)), ack_wait=5.0, clock=lambda: AT)


Frontier = tuple[str, int]  # a host stream and the last record its writer confirmed


def _ingest(ledger: UsageStore, capture: DurableCapture) -> tuple[dict[str, str], Frontier]:
    """Commit the capture's stream; returns each turn's epoch ID and the stream's frontier."""
    capture.stop()
    scan = ob.scan_stream(capture.writer.directory)
    ledger.ingest(uc.parse_batch(uc.build_batch("host", scan.stream_id, None, 0, ob.GENESIS, list(scan.records))))
    epochs = {r.payload["turn_id"]: r.payload["epoch_id"] for r in scan.records if r.payload["kind"] == uc.EPOCH_BEGIN}
    return epochs, (scan.stream_id, scan.records[-1].sequence)


def _stream(ledger: UsageStore, directory: Path, writer: str, payloads: list[dict[str, Any]]) -> Frontier:
    """One more stream of ``writer`` records, committed as its drain would."""
    outbox = ob.OutboxWriter(directory)
    for payload in payloads:
        assert outbox.submit(payload).wait(5)
    outbox.close()
    scan = ob.scan_stream(outbox.directory)
    ledger.ingest(uc.parse_batch(uc.build_batch(writer, scan.stream_id, None, 0, ob.GENESIS, list(scan.records))))
    return scan.stream_id, scan.records[-1].sequence


def _contexts(ledger: UsageStore, directory: Path, session: str, selections: dict[str, tuple[str, str]]) -> Frontier:
    """Each turn's Auto/fixed context, as the host records it in the turn's own epoch: turn -> (epoch ID, selection)."""
    return _stream(ledger, directory, "host", [
        {"kind": uc.TURN_REPORT_CONTEXT, "at": AT.isoformat(), "epoch_id": epoch_id, "session_id": session,
         "turn_id": turn, "selection": selection, "registry_hash": None, "strategy": None}
        for turn, (epoch_id, selection) in selections.items()
    ])


def _gateway_evidence(ledger: UsageStore, directory: Path, receipts: list[StageReceipt]) -> None:
    _stream(ledger, directory, "gateway", [
        payload for r in receipts for payload in (
            {"kind": uc.GATEWAY_ATTEMPT_INTENT, "at": AT.isoformat(), "gateway_request_id": r.gateway_request_id,
             "host_request_id": r.attempt_id, "attempt": 1, "route": None},
            {"kind": uc.GATEWAY_ATTEMPT_OUTCOME, "at": AT.isoformat(), "gateway_request_id": r.gateway_request_id, "attempt": 1,
             "outcome": "completed", "http_status": None, "cost_usd": None, "billing_units": None, "intent_confirmed": True})
    ])


def _report(ledger: Any, session: str, **fields: Any) -> tuple[int, dict[str, Any]]:
    request = urc.ReportRequest(**{"session_id": session, "turn_id": None, "reference_ids": None, "page_size": 100,
                                   "cursor": None, "expected_turns": None, **fields})
    return handle_usage_report_request(raw_body=urc.build_request(request), config=SimpleNamespace(usage_store=ledger, shared_secret=SECRET))


def _session() -> str:
    return f"p129-{uuid.uuid4().hex}"


def _complete_turn(ledger: UsageStore, directory: Path, session: str, turn: str, *, selection: str = "auto",
                   cost: str = "0.0012") -> tuple[Frontier, ...]:
    """A certified turn; returns the host frontiers that delivered it (its turn stream and its context stream)."""
    receipt = _receipt(session, turn, f"{uuid.uuid4().hex}:planning:1:1", cost=cost)
    capture = _capture(directory / "host")
    _turn(capture, session, turn, [receipt])
    epochs, host = _ingest(ledger, capture)
    _gateway_evidence(ledger, directory / "gateway", [receipt])
    return host, _contexts(ledger, directory / "context", session, {turn: (epochs[turn], selection)})


def test_migration_002_upgrades_a_001_ledger_in_place_and_a_reader_never_migrates(scratch_database, tmp_path, monkeypatch):
    session = _session()
    old = UsageStore(scratch_database)
    with monkeypatch.context() as only_001:
        only_001.setattr(usage_store, "_PINNED", usage_store._PINNED[:1])
        old.migrate()
        capture = _capture(tmp_path)
        _turn(capture, session, "t1", [_receipt(session, "t1", f"{uuid.uuid4().hex}:planning:1:1")])
        _ingest(old, capture)

    with pytest.raises(StoreError) as before:
        UsageStore(scratch_database).report_facts(session, None, frontier=None, deadline=time.monotonic() + 5,
                                                  max_attempts=10, max_turns=10)
    upgraded = UsageStore(scratch_database)
    instance = upgraded.migrate()

    assert before.value.code == "unavailable"
    assert instance == old.ledger_instance
    with psycopg.connect(scratch_database) as conn:
        applied = [row[0] for row in conn.execute("SELECT filename FROM optimus_usage_schema_migrations ORDER BY filename")]
    assert applied == ["001_durable_capture.sql", "002_savings_report.sql"]
    status, body = _report(upgraded, session)
    assert status == 200 and body["session"]["attempts"] == 1 and body["session"]["known_usd"] == "0.0012"


@pytest.mark.parametrize("statement", [
    "UPDATE optimus_usage.price_snapshot SET body = '{}' WHERE snapshot_id = %s",
    "DELETE FROM optimus_usage.price_snapshot WHERE snapshot_id = %s",
    "TRUNCATE optimus_usage.price_snapshot",
])
def test_snapshots_read_back_independently_keep_their_first_capture_and_are_immutable(released, store, tmp_path, statement):
    policy = SimpleNamespace(snapshot=compose_trusted_snapshot(packaged_defaults()))
    ids = []
    for n in range(2):  # two Gateway processes capture the same configuration
        outbox = ob.OutboxWriter(tmp_path / f"gateway-{n}")
        usage_price_snapshots.configure(outbox)
        try:
            usage_price_snapshots.record_references(REFERENCES)
            ids.append(usage_price_snapshots.stamp({}, policy)["price_snapshot_id"])
        finally:
            usage_price_snapshots.configure(None)
        outbox.close()
        scan = ob.scan_stream(outbox.directory)
        store.ingest(uc.parse_batch(uc.build_batch("gateway", scan.stream_id, None, 0, ob.GENESIS, list(scan.records))))

    expected = {ids[0], *(r.snapshot_id for r in REFERENCES.references)}
    with psycopg.connect(released["conninfo"]) as conn:  # a new connection: durable readback only
        rows = conn.execute("SELECT snapshot_id, kind, body FROM optimus_usage.price_snapshot WHERE snapshot_id = ANY(%s)",
                            (sorted(expected),)).fetchall()
        assert ids[0] == ids[1] and {row[0] for row in rows} == expected and len(rows) == len(expected)
        registry = next(row[2] for row in rows if row[1] == uc.REGISTRY_SNAPSHOT)
        routes = {m: e.route for m, e in policy.snapshot.policy.models.items()}
        assert all(e["route"]["providers"] == list(routes[e["model"]].providers) for e in registry["entries"])
        assert {row[2]["reference"]["id"] for row in rows if row[1] == uc.REFERENCE_SNAPSHOT} == {r.id for r in REFERENCES.references}
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(statement, () if "TRUNCATE" in statement else (ids[0],))


def test_the_report_charges_each_canonical_receipt_once_and_shows_aliases_and_conflicts(store, tmp_path):
    session = _session()
    attempt, gw = f"{uuid.uuid4().hex}:planning:1:1", f"gw-{uuid.uuid4().hex}"
    original = _receipt(session, "t1", attempt, gw=gw)
    first = _capture(tmp_path / "a")
    _turn(first, session, "t1", [original])
    _ingest(store, first)
    second = _capture(tmp_path / "b")  # another process replays the same Gateway request, and a contradiction
    _turn(second, session, "t2", [_receipt(session, "t1", attempt + "x", gw=gw),
                                  _receipt(session, "t1", attempt, cost="0.99", gw=f"gw-{uuid.uuid4().hex}")])
    _ingest(store, second)

    status, body = _report(store, session, reference_ids=("ref-0",))  # one column group: the detail rows follow

    assert status == 200 and urc.validate_report(body)
    assert body["session"]["attempts"] == 1 and body["session"]["known_usd"] == "0.0012", "the alias and the contradiction add no charge"
    assert body["session"]["conflicts"] == 1 and "receipt_conflict" in body["session"]["reasons"]
    assert [row["conflict"] for row in body["detail"]] == [True]


def test_a_complete_auto_turn_is_definitive_and_a_late_receipt_downgrades_it(store, tmp_path):
    session = _session()
    frontier = _complete_turn(store, tmp_path / "t1", session, "t1")

    status, body = _report(store, session, expected_turns=1, frontier=frontier)
    # 600 x 1/M + 400 x 0.1/M + 200 x 4/M = 0.00144 against 0.0012 actual
    assert status == 200 and body["session"]["definitive"] and body["auto"]["definitive"]
    assert [c["savings_usd"] for c in body["comparisons"]["columns"]] == ["0.00024"] * 3
    assert _report(store, session)[1]["session"]["reasons"] == ["expected_turns_unknown", "frontier_unknown"]

    late_session = _session()
    receipt = _receipt(late_session, "t1", f"{uuid.uuid4().hex}:planning:1:1")
    late = _receipt(late_session, "t1", f"{receipt.attempt_id}:late")
    capture = _capture(tmp_path / "late")
    _turn(capture, late_session, "t1", [receipt])
    capture.receipt(late)  # after the close: appended late
    epochs, host = _ingest(store, capture)
    _gateway_evidence(store, tmp_path / "late-gateway", [receipt, late])
    context = _contexts(store, tmp_path / "late-context", late_session, {"t1": (epochs["t1"], "auto")})
    status, body = _report(store, late_session, expected_turns=1, frontier=(host, context))

    assert status == 200 and body["session"]["late"] == 1 and not body["session"]["definitive"]
    assert {"late_receipt", "epoch_incomplete"} <= set(body["session"]["reasons"])
    assert all(c["savings_usd"] is None for c in body["comparisons"]["columns"])


def test_ingest_between_pages_answers_report_changed(store, tmp_path):
    session = _session()
    _complete_turn(store, tmp_path / "t1", session, "t1")
    status, first = _report(store, session)
    assert status == 200 and first["next_cursor"] is not None  # five references: two column pages

    _complete_turn(store, tmp_path / "t2", session, "t2")

    assert _report(store, session, cursor=first["next_cursor"]) == urc.error_body("REPORT_CHANGED")


def test_a_turn_committed_in_the_middle_of_a_read_never_tears_the_page(store, tmp_path, monkeypatch):
    """One page reads one repeatable-read snapshot: a turn committed between its receipt and epoch statements is in
    neither, and the next report has both."""
    session = _session()
    _complete_turn(store, tmp_path / "t1", session, "t1")
    original = UsageStore._report_facts

    class Interleaved:
        def __init__(self, conn: Any) -> None:
            self.conn, self.done = conn, False

        def execute(self, sql: str, *args: Any) -> Any:
            result = self.conn.execute(sql, *args)
            if "attempt_receipt r" in sql and not self.done:
                self.done = True
                _complete_turn(store, tmp_path / "t2", session, "t2")  # another connection, committed
            return result

    with monkeypatch.context() as patched:
        patched.setattr(UsageStore, "_report_facts", lambda self, conn, *a: original(self, Interleaved(conn), *a))
        status, during = _report(store, session)
    status_after, after = _report(store, session)

    assert status == status_after == 200
    assert (during["session"]["turns"], during["session"]["attempts"]) == (1, 1)
    assert (after["session"]["turns"], after["session"]["attempts"]) == (2, 2)


def test_a_held_lock_expires_within_the_report_budget(released, store, tmp_path):
    session = _session()
    _complete_turn(store, tmp_path, session, "t1")
    store.report_budget_ms = 500
    with psycopg.connect(released["conninfo"]) as holder:
        holder.execute("LOCK TABLE optimus_usage.attempt_receipt IN ACCESS EXCLUSIVE MODE")
        started = time.monotonic()
        refused = _report(store, session)
        elapsed = time.monotonic() - started
        holder.rollback()

    assert refused == urc.error_body("REPORT_TIMEOUT") and elapsed < 3
    assert _report(store, session)[0] == 200


def test_an_outage_is_unavailable_and_the_report_returns_after_a_restart(released, store, tmp_path):
    session = _session()
    _complete_turn(store, tmp_path, session, "t1")
    container = released["section"]["container"]

    subprocess.run(["docker", "stop", "--time", "10", container], check=True, capture_output=True, timeout=120)
    try:
        down = _report(UsageStore(released["conninfo"], connect_timeout=2), session)
    finally:
        subprocess.run(["docker", "start", container], check=True, capture_output=True, timeout=120)
    deadline = time.monotonic() + 60
    while (up := _report(store, session))[0] != 200 and time.monotonic() < deadline:
        time.sleep(1)

    assert down == urc.error_body("LEDGER_UNAVAILABLE")
    assert up[0] == 200 and up[1]["session"]["attempts"] == 1


def test_a_replaced_ledger_answers_report_changed(store, scratch_database, tmp_path):
    session = _session()
    _complete_turn(store, tmp_path / "a", session, "t1")
    replacement = UsageStore(scratch_database)
    replacement.migrate()
    _complete_turn(replacement, tmp_path / "b", session, "t1")
    status, first = _report(store, session)

    assert status == 200 and first["next_cursor"] is not None
    assert _report(replacement, session, cursor=first["next_cursor"]) == urc.error_body("REPORT_CHANGED")


def test_the_host_reads_a_report_over_real_http_through_the_production_transport(store, tmp_path):
    from optimus.config.gateway import OptimusGatewaySettings
    from optimus.gateway.client import GatewayClient
    from optimus.gateway.errors import GatewayHttpError
    from optimus_gateway.models import GatewayServiceConfig
    from optimus_gateway.server import serve_gateway

    session = _session()
    frontier = _complete_turn(store, tmp_path, session, "t1")
    config = GatewayServiceConfig(bind_host="127.0.0.1", bind_port=0, shared_secret=SECRET, provider="openrouter",
                                  provider_api_key="or-test", base_url="https://openrouter.ai/api/v1", usage_store=store)  # pragma: allowlist secret
    server = serve_gateway(config=config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    payload = json.loads(urc.build_request(urc.ReportRequest(session, None, None, 100, None, 1, frontier)))
    try:
        body = GatewayClient(settings=OptimusGatewaySettings(gateway_url=url, optimus_api_key=SECRET)).post_observability_json(
            path=urc.PATH, payload=payload)
        with pytest.raises(GatewayHttpError) as refused:
            GatewayClient(settings=OptimusGatewaySettings(gateway_url=url, optimus_api_key="wrong")).post_observability_json(  # pragma: allowlist secret
                path=urc.PATH, payload=payload)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)

    assert urc.validate_report(body)["session"]["definitive"] and body["ledger_instance"] == store.ledger_instance
    assert refused.value.status_code == 401


@pytest.fixture(scope="module")
def boundary() -> tuple[dict[str, Any], Path, str, str]:
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


@pytest.mark.requires_os_keyring
def test_the_host_reads_a_report_from_a_gateway_process_that_alone_holds_the_ledger_credential(boundary, tmp_path):
    """The provisioner placed the credential in the Gateway's keyring namespace outside pytest; the Gateway child resolves
    it through the production `start_accounting`; the host holds only the Gateway URL and key."""
    import secrets as secrets_module

    from optimus.config.gateway import OptimusGatewaySettings
    from optimus.gateway.client import GatewayClient

    section, root, run_id, literal = boundary
    key = secrets_module.token_hex(16)
    environ = {k: v for k, v in os.environ.items() if k != PASSWORD_ENV}
    child = subprocess.Popen([sys.executable, "-c", _GATEWAY_CHILD, str(root), key, json.dumps(section), run_id, literal],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environ)
    try:
        ready = json.loads(_ready_line(child))
        client = GatewayClient(settings=OptimusGatewaySettings(gateway_url=f"http://127.0.0.1:{ready['port']}", optimus_api_key=key))
        capabilities = urc.validate_capabilities(client.post_observability_json(
            path=urc.PATH, payload=json.loads(urc.build_request(None))))
        body = client.post_observability_json(
            path=urc.PATH, payload=json.loads(urc.build_request(urc.ReportRequest(_session(), None, None, 10, None, None))))
    finally:
        child.terminate()
        try:
            child.wait(30)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(30)

    assert os.environ.get(PASSWORD_ENV) is None and ready["store"] is True
    assert urc.FEATURE_REPORT_CONTEXT in capabilities
    assert urc.validate_report(body)["session"]["attempts"] == 0


# --- Plan 12.9 Checkpoint A (round 93): delivery completeness and the cumulative deadline -------------------------------


def test_a_turn_count_alone_never_proves_a_receipt_was_delivered(store, tmp_path):
    session = _session()
    host, context = _complete_turn(store, tmp_path, session, "t1")
    ahead = (host[0], host[1] + 1)  # the host confirmed one more record than the ledger committed

    status, pending = _report(store, session, expected_turns=1, frontier=(ahead, context))
    unknown_stream = _report(store, session, expected_turns=1, frontier=(host, context, (uuid.uuid4().hex, 1)))[1]
    delivered = _report(store, session, expected_turns=1, frontier=(host, context))[1]

    assert status == 200 and not pending["session"]["definitive"] and "delivery_pending" in pending["session"]["reasons"]
    assert "delivery_pending" in unknown_stream["session"]["reasons"]
    assert delivered["session"]["definitive"] and pending["revision"] != delivered["revision"]


def test_a_gap_in_a_scope_stream_withholds_the_definitive_total(store, tmp_path):
    session = _session()
    receipt = _receipt(session, "t1", f"{uuid.uuid4().hex}:planning:1:1")
    capture = _capture(tmp_path / "host")
    _turn(capture, session, "t1", [receipt])
    capture.stop()
    scan = ob.scan_stream(capture.writer.directory)
    head, tail = scan.records[:1], scan.records[1:]  # this ledger never received the stream's first record
    store.ingest(uc.parse_batch(uc.build_batch("host", scan.stream_id, "f" * 32, head[-1].sequence, head[-1].digest, tail)))
    _gateway_evidence(store, tmp_path / "gateway", [receipt])
    epoch = next(r.payload["epoch_id"] for r in tail if r.payload["kind"] == uc.EPOCH_BEGIN)
    context = _contexts(store, tmp_path / "context", session, {"t1": (epoch, "auto")})

    status, body = _report(store, session, expected_turns=1, frontier=((scan.stream_id, tail[-1].sequence), context))

    assert status == 200 and "stream_gap" in body["session"]["reasons"] and not body["session"]["definitive"]


class _Slowed:
    """A report connection whose statements each wait ``pause`` seconds in the database first."""

    def __init__(self, conn: Any, pause: float, once: bool = False) -> None:
        self.conn, self.pause, self.once, self.used = conn, pause, once, False

    def execute(self, sql: Any, *args: Any) -> Any:
        if not (self.once and self.used):
            self.used = True
            self.conn.execute(f"SELECT pg_sleep({self.pause})")
        return self.conn.execute(sql, *args)


@pytest.mark.parametrize(("pause", "once"), [
    (0.9, False),  # every statement is shorter than the budget; together they outrun it
    (30, True),  # one statement would outrun it alone
])
def test_the_whole_read_ends_within_the_report_budget(store, tmp_path, monkeypatch, pause, once):
    session = _session()
    _complete_turn(store, tmp_path, session, "t1")
    store.report_budget_ms = 1000
    original = UsageStore._report_facts

    with monkeypatch.context() as slowed:
        slowed.setattr(UsageStore, "_report_facts", lambda self, conn, *a: original(self, _Slowed(conn, pause, once), *a))
        started = time.monotonic()
        refused = _report(store, session)
        elapsed = time.monotonic() - started

    assert refused == urc.error_body("REPORT_TIMEOUT") and elapsed < 1.5  # cancelled at the deadline, not after
    with psycopg.connect(store._conninfo) as conn:  # nothing of the expired read keeps running in the database
        deadline = time.monotonic() + 5
        while conn.execute("SELECT count(*) FROM pg_stat_activity WHERE query LIKE 'SELECT pg_sleep%%' AND pid <> pg_backend_pid()").fetchone()[0]:
            assert time.monotonic() < deadline, "an expired report statement is still running"
            time.sleep(0.1)


@pytest.mark.parametrize("frontier", [
    lambda host, context: (),  # empty: proves nothing
    lambda host, context: (context,),  # the receipt's own stream is not covered
    lambda host, context: (host, context, (uuid.uuid4().hex, 0)),  # a stream this ledger never saw, at sequence zero
])
def test_a_frontier_that_does_not_cover_the_scope_is_never_definitive(store, tmp_path, frontier):
    session = _session()
    host, context = _complete_turn(store, tmp_path, session, "t1")

    status, body = _report(store, session, expected_turns=1, frontier=frontier(host, context))

    assert status == 200 and not body["session"]["definitive"] and not body["auto"]["definitive"]
    assert {"frontier_unknown", "delivery_pending"} & set(body["session"]["reasons"])
    assert all(c["savings_usd"] is None and c["savings_percent"] is None for c in body["comparisons"]["columns"])


def test_an_empty_frontier_never_certifies_an_empty_scope(store):
    """With no facts there is nothing for coverage to miss, so only the frontier can say whether the host recorded any."""
    status, body = _report(store, _session(), expected_turns=0, frontier=())

    assert status == 200 and body["session"]["attempts"] == 0
    assert body["session"]["reasons"] == ["frontier_unknown"] and not body["session"]["definitive"]
