"""Real PostgreSQL induced-failure, restart latch, and linked recovery evidence."""

from __future__ import annotations

import secrets
import socket
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest

pytestmark = pytest.mark.requires_evidence_handoff_postgres


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _abs(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class _Harness:
    store: object
    manager: object
    monitor: object
    recovery: object
    conninfo: str
    control_root: Path
    password: str
    port: int
    config: object
    bootstrap: object


@pytest.fixture()
def integrity_harness(tmp_path: Path):
    from evidence_handoff_runtime.config import FeatureConfig, LifecycleBootstrapContext
    from evidence_handoff_runtime.lifecycle import LifecycleError, LifecycleManager
    from evidence_handoff_runtime.migrations import apply_migrations
    from evidence_handoff_runtime.store import PostgresLedgerStore
    from optimus_security.sanitization import PathAliasRule

    port = _free_port()
    suffix = uuid.uuid4().hex[:8]
    password = f"integrity-{secrets.token_hex(8)}"
    capture = _abs(tmp_path, "capture")
    control_root = _abs(tmp_path, "control")
    config = FeatureConfig.from_mapping(
        {
            "enabled": "true",
            "backend_id": "docker",
            "bind_host": "127.0.0.1",
            "postgres_port": str(port),
            "container_name": f"evidence-handoff-integrity-{suffix}",
            "image": "postgres:16-alpine",
            "volume_name": f"evidence-handoff-integrity-data-{suffix}",
        }
    )
    bootstrap = LifecycleBootstrapContext(
        service_secrets=("svc-secret-alpha",),
        identity_values=("operator@example.test",),
        path_aliases=(PathAliasRule(source_root=str(capture), alias="<temp>"),),
        temporary_capture_root=capture,
        staging_root=_abs(tmp_path, "staging"),
        quarantine_root=_abs(tmp_path, "quarantine"),
        forbidden_persistence_roots=(_abs(tmp_path, "forbidden"),),
        allowed_origins=("http://127.0.0.1:8765",),
        enrollment_principal_ids=("reviewer-1",),
        capabilities=("review-ruling",),
        lock_path=tmp_path / "lifecycle.lock",
        control_root=control_root,
        store_admin_user="handoff",
        store_admin_password=password,
    )
    manager = LifecycleManager(config, bootstrap)
    try:
        started = manager.start()
        if not started.running:
            # Transient Docker/Postgres readiness flakes under sequential container churn.
            try:
                manager.stop()
            except Exception:
                pass
            try:
                manager.destroy_for_test_cleanup()
            except LifecycleError:
                pass
            manager = LifecycleManager(config, bootstrap)
            started = manager.start()
        assert started.running is True, started.summary_code
        assert started.backend_id == "docker"
        instance_id = started.ledger_instance_id
        assert instance_id
        conninfo = (
            f"host=127.0.0.1 port={port} user=handoff password={password} "
            "dbname=postgres connect_timeout=5"
        )
        apply_migrations(conninfo)
        store = PostgresLedgerStore(conninfo=conninfo, ledger_instance_id=instance_id)
        store.ensure_instance_metadata()
        # Monitor/recovery are constructed inside each test so RED fails on the missing
        # production modules before optional wiring, matching Task 4 Step 1 scope.
        yield _Harness(
            store=store,
            manager=manager,
            monitor=None,
            recovery=None,
            conninfo=conninfo,
            control_root=control_root,
            password=password,
            port=port,
            config=config,
            bootstrap=bootstrap,
        )
    finally:
        try:
            manager.stop()
        except Exception:
            pass
        try:
            manager.destroy_for_test_cleanup()
        except LifecycleError:
            pass


def _bind_monitor(h: _Harness):
    from evidence_handoff_runtime.integrity import IntegrityMonitor
    from evidence_handoff_runtime.recovery import RecoveryManager

    h.monitor = IntegrityMonitor(store=h.store, control_root=h.control_root, lifecycle=h.manager)
    h.recovery = RecoveryManager(control_root=h.control_root, store=h.store, lifecycle=h.manager)
    return h


def _sanitized(*, text: str = "ruling body"):
    from evidence_handoff.ledger.models import (
        EntryKind,
        EntryMessage,
        MessagePart,
        SanitizedDraft,
        SchemaId,
    )

    return SanitizedDraft(
        kind=EntryKind.REVIEW_RULING,
        schema_id=SchemaId.REVIEW_RULING.value,
        context_id="ctx-1",
        recipient_agent_ids=("implementer-1",),
        message=EntryMessage(parts=(MessagePart(kind="text", text=text),)),
        artifacts=(),
        task_id=None,
        in_reply_to=None,
        rule_counts={"exact_secret_replacement": 0},
    )


def _identity():
    from evidence_handoff.ledger.models import ServerIdentity

    return ServerIdentity(
        principal_id="principal-reviewer",
        agent_id="reviewer-1",
        caller_role="reviewer",
        authority="review-ruling",
    )


def _seed_entries(store, count: int = 3) -> list:
    results = []
    for index in range(count):
        results.append(
            store.append(
                _sanitized(text=f"ruling-{index}"),
                _identity(),
                idempotency_key=f"idem-{index}",
            )
        )
    return results


def _assert_latched(monitor, *, cause, instance_id: str, safe_boundary: int) -> object:
    from evidence_handoff_runtime.integrity import LedgerIntegrityError

    status = monitor.status()
    assert status.failure_class == "ledger_integrity_failed"
    assert status.normal_operations_allowed is False
    assert status.may_auto_relay is False
    assert status.incident is not None
    assert status.incident.cause == cause
    assert status.incident.ledger_instance_id == instance_id
    assert status.incident.safe_boundary_sequence == safe_boundary
    assert status.incident.retryable is False
    with pytest.raises(LedgerIntegrityError) as blocked:
        monitor.refuse_if_latched()
    assert blocked.value.code == "ledger_integrity_failed"
    return status.incident


def test_chain_break_latches_survives_restart_and_blocks_append(integrity_harness) -> None:
    import psycopg

    from evidence_handoff_runtime.integrity import IntegrityCause, LedgerIntegrityError
    from evidence_handoff_runtime.lifecycle import LifecycleManager

    h = _bind_monitor(integrity_harness)
    seeded = _seed_entries(h.store, 3)
    with psycopg.connect(h.conninfo) as conn:
        conn.execute(
            """
            UPDATE evidence_handoff_entries
            SET content_sha256 = %s
            WHERE ledger_instance_id = %s AND sequence = 2
            """,
            ("0" * 64, h.store._ledger_instance_id),
        )
        conn.commit()

    with pytest.raises(LedgerIntegrityError) as raised:
        h.monitor.verify_full()
    assert raised.value.cause is IntegrityCause.CHAIN_BREAK
    incident = _assert_latched(
        h.monitor,
        cause=IntegrityCause.CHAIN_BREAK,
        instance_id=h.store._ledger_instance_id,
        safe_boundary=1,
    )

    with pytest.raises(LedgerIntegrityError):
        h.store.append(_sanitized(text="after-latch"), _identity(), idempotency_key="idem-after")

    # Real process restart: new LifecycleManager + IntegrityMonitor on same control_root.
    restarted_manager = LifecycleManager(h.config, h.bootstrap)
    from evidence_handoff_runtime.integrity import IntegrityMonitor
    from evidence_handoff_runtime.store import PostgresLedgerStore

    restarted_store = PostgresLedgerStore(
        conninfo=h.conninfo, ledger_instance_id=h.store._ledger_instance_id
    )
    restarted_monitor = IntegrityMonitor(
        store=restarted_store, control_root=h.control_root, lifecycle=restarted_manager
    )
    status = restarted_manager.status()
    assert status.summary_code == "ledger_integrity_failed"
    assert status.integrity_incident is not None
    assert status.integrity_incident.incident_id == incident.incident_id
    assert status.integrity_incident.cause is IntegrityCause.CHAIN_BREAK
    assert status.integrity_incident.safe_boundary_sequence == 1
    assert restarted_monitor.status().incident.incident_id == incident.incident_id
    assert seeded[0].sequence == 1


@pytest.mark.parametrize(
    ("corrupt", "cause", "safe_boundary"),
    [
        ("sequence_duplicate", "sequence_duplicate", 1),
        ("sequence_gap", "sequence_gap", 1),
        ("counter_head_mismatch", "counter_head_mismatch", 2),
        ("ledger_instance_mismatch", "ledger_instance_mismatch", 0),
        ("rollback_divergence", "rollback_divergence", 2),
    ],
)
def test_induced_failure_classes_latch(
    integrity_harness, corrupt: str, cause: str, safe_boundary: int
) -> None:
    import psycopg

    from evidence_handoff_runtime.integrity import IntegrityCause, LedgerIntegrityError

    h = _bind_monitor(integrity_harness)
    _seed_entries(h.store, 3)
    instance_id = h.store._ledger_instance_id
    expected = IntegrityCause(cause)

    with psycopg.connect(h.conninfo) as conn:
        if corrupt == "sequence_duplicate":
            conn.execute("ALTER TABLE evidence_handoff_entries DROP CONSTRAINT IF EXISTS evidence_handoff_entries_sequence_key")
            conn.execute(
                "ALTER TABLE evidence_handoff_entries DROP CONSTRAINT IF EXISTS evidence_handoff_entries_pkey"
            )
            row = conn.execute(
                "SELECT * FROM evidence_handoff_entries WHERE ledger_instance_id = %s AND sequence = 2",
                (instance_id,),
            ).fetchone()
            assert row is not None
            conn.execute(
                """
                INSERT INTO evidence_handoff_entries (
                    sequence, ledger_instance_id, entry_id, schema_id, kind, context_id, task_id,
                    in_reply_to, recipient_agent_ids, message_json, artifacts_json, principal_id,
                    agent_id, caller_role, authority, attestation, created_at, idempotency_key,
                    prev_content_sha256, content_sha256
                )
                SELECT sequence, ledger_instance_id, %s, schema_id, kind, context_id, task_id,
                    in_reply_to, recipient_agent_ids, message_json, artifacts_json, principal_id,
                    agent_id, caller_role, authority, attestation, created_at, %s,
                    prev_content_sha256, content_sha256
                FROM evidence_handoff_entries
                WHERE ledger_instance_id = %s AND sequence = 2
                """,
                (str(uuid.uuid4()), f"dup-{uuid.uuid4().hex}", instance_id),
            )
        elif corrupt == "sequence_gap":
            conn.execute(
                "DELETE FROM evidence_handoff_entries WHERE ledger_instance_id = %s AND sequence = 2",
                (instance_id,),
            )
        elif corrupt == "counter_head_mismatch":
            conn.execute(
                """
                UPDATE evidence_handoff_counter
                SET last_content_sha256 = %s
                WHERE ledger_instance_id = %s
                """,
                ("c" * 64, instance_id),
            )
        elif corrupt == "ledger_instance_mismatch":
            conn.execute(
                """
                INSERT INTO evidence_handoff_ledger_instance(ledger_instance_id, genesis_sequence)
                VALUES (%s, 0)
                """,
                ("foreign-instance",),
            )
            conn.execute(
                """
                UPDATE evidence_handoff_entries
                SET ledger_instance_id = %s
                WHERE ledger_instance_id = %s AND sequence = 2
                """,
                ("foreign-instance", instance_id),
            )
        elif corrupt == "rollback_divergence":
            # Client/external witness claims a head ahead of the restored counter.
            conn.execute(
                """
                UPDATE evidence_handoff_counter
                SET last_committed = 2, last_content_sha256 = (
                    SELECT content_sha256 FROM evidence_handoff_entries
                    WHERE ledger_instance_id = %s AND sequence = 2
                )
                WHERE ledger_instance_id = %s
                """,
                (instance_id, instance_id),
            )
            conn.execute(
                "DELETE FROM evidence_handoff_entries WHERE ledger_instance_id = %s AND sequence = 3",
                (instance_id,),
            )
        conn.commit()

    if corrupt == "rollback_divergence":
        witness = {
            "ledger_instance_id": instance_id,
            "last_committed": 3,
            "last_content_sha256": "d" * 64,
        }
        with pytest.raises(LedgerIntegrityError) as raised:
            h.monitor.verify_full(external_witnesses=(witness,))
    else:
        with pytest.raises(LedgerIntegrityError) as raised:
            h.monitor.verify_full()
    assert raised.value.cause is expected
    _assert_latched(
        h.monitor,
        cause=expected,
        instance_id=instance_id,
        safe_boundary=safe_boundary,
    )


def test_latch_precedes_feature_disable_and_postgres_unavailable(integrity_harness) -> None:
    import psycopg

    from evidence_handoff_runtime.config import FeatureConfig
    from evidence_handoff_runtime.integrity import IntegrityCause, LedgerIntegrityError
    from evidence_handoff_runtime.lifecycle import LifecycleManager

    h = _bind_monitor(integrity_harness)
    _seed_entries(h.store, 2)
    with psycopg.connect(h.conninfo) as conn:
        conn.execute(
            """
            UPDATE evidence_handoff_entries
            SET prev_content_sha256 = %s
            WHERE ledger_instance_id = %s AND sequence = 2
            """,
            ("e" * 64, h.store._ledger_instance_id),
        )
        conn.commit()

    with pytest.raises(LedgerIntegrityError):
        h.monitor.verify_full()
    incident = h.monitor.status().incident
    assert incident is not None
    incident_id = incident.incident_id
    cause = incident.cause
    boundary = incident.safe_boundary_sequence

    # Explicitly disable the feature in a separate LifecycleManager run.
    disabled_config = FeatureConfig.from_mapping(
        {
            "enabled": "false",
            "backend_id": "docker",
            "bind_host": "127.0.0.1",
            "postgres_port": str(h.port),
            "container_name": h.config.container_name,
            "image": h.config.image,
            "volume_name": h.config.volume_name,
        }
    )
    disabled_manager = LifecycleManager(disabled_config, h.bootstrap)
    disabled_status = disabled_manager.status()
    assert disabled_status.summary_code == "ledger_integrity_failed"
    assert disabled_status.integrity_incident is not None
    assert disabled_status.integrity_incident.incident_id == incident_id
    assert disabled_status.integrity_incident.cause is cause
    assert disabled_status.integrity_incident.safe_boundary_sequence == boundary
    assert disabled_status.integrity_incident.cause is IntegrityCause.CHAIN_BREAK

    # Make PostgreSQL unavailable; latch must still dominate status.
    h.manager.stop()
    unavailable_manager = LifecycleManager(h.config, h.bootstrap)
    unavailable_status = unavailable_manager.status()
    assert unavailable_status.summary_code == "ledger_integrity_failed"
    assert unavailable_status.integrity_incident.incident_id == incident_id
    assert unavailable_status.integrity_incident.cause is cause
    assert unavailable_status.integrity_incident.safe_boundary_sequence == boundary


def test_linked_replacement_recovery_lineage(integrity_harness) -> None:
    import psycopg

    from evidence_handoff_runtime.integrity import IntegrityCause, IntegrityLatch, LedgerIntegrityError
    from evidence_handoff_runtime.recovery import RecoveryError

    h = _bind_monitor(integrity_harness)
    seeded = _seed_entries(h.store, 3)
    with psycopg.connect(h.conninfo) as conn:
        conn.execute(
            """
            UPDATE evidence_handoff_entries
            SET content_sha256 = %s
            WHERE ledger_instance_id = %s AND sequence = 3
            """,
            ("f" * 64, h.store._ledger_instance_id),
        )
        conn.commit()

    with pytest.raises(LedgerIntegrityError):
        h.monitor.verify_full()
    incident = h.monitor.status().incident
    assert incident is not None
    assert incident.cause is IntegrityCause.CHAIN_BREAK

    quarantine = h.recovery.quarantine(h.store._ledger_instance_id, incident=incident)
    assert quarantine.read_only is True
    with pytest.raises(RecoveryError) as auto:
        h.recovery.clear_latch_automatically(incident)
    assert auto.value.code == "automatic_clear_forbidden"
    with pytest.raises(RecoveryError):
        h.recovery.repair_in_place(incident)

    anchor = h.recovery.find_last_verified_anchor(h.store._ledger_instance_id)
    assert anchor.sequence == 2
    assert anchor.content_sha256 == seeded[1].content_sha256
    assert anchor.verified is True

    replacement = h.recovery.activate_linked_replacement(incident, anchor)
    assert replacement.predecessor_instance_id == h.store._ledger_instance_id
    assert replacement.recovery_anchor_sequence == 2
    assert replacement.recovery_anchor_digest == seeded[1].content_sha256
    assert replacement.incident_id == incident.incident_id
    # Untrusted tail (seq 3) remains in predecessor; never copied as repaired content.
    assert "repaired" not in repr(replacement).lower()
    predecessor_latch = IntegrityLatch(control_root=h.control_root).load()
    assert predecessor_latch is not None
    assert predecessor_latch.incident_id == incident.incident_id

    # First append on the linked replacement must continue the lineage.
    from evidence_handoff_runtime.store import PostgresLedgerStore

    replacement_store = PostgresLedgerStore(
        conninfo=h.conninfo,
        ledger_instance_id=replacement.ledger_instance_id,
        control_root=h.control_root,
    )
    first = replacement_store.append(
        _sanitized(text="first-on-replacement"),
        _identity(),
        idempotency_key="idem-replacement-1",
    )
    assert first.sequence == anchor.sequence + 1
    assert first.content_sha256
    # Predecessor untrusted tail at sequence 3 must still exist and must not block replacement seq 3.
    with psycopg.connect(h.conninfo) as conn:
        pred_tail = conn.execute(
            """
            SELECT sequence, content_sha256 FROM evidence_handoff_entries
            WHERE ledger_instance_id = %s AND sequence = 3
            """,
            (h.store._ledger_instance_id,),
        ).fetchone()
        assert pred_tail is not None
        repl_row = conn.execute(
            """
            SELECT sequence, prev_content_sha256, ledger_instance_id
            FROM evidence_handoff_entries
            WHERE ledger_instance_id = %s AND sequence = %s
            """,
            (replacement.ledger_instance_id, first.sequence),
        ).fetchone()
        assert repl_row is not None
        assert int(repl_row[0]) == 3
        assert repl_row[1] == seeded[1].content_sha256
        assert repl_row[2] == replacement.ledger_instance_id
