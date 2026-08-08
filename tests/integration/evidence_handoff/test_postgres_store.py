"""Real PostgreSQL store ordering, idempotency, concurrency, and rollback evidence."""

from __future__ import annotations

import secrets
import socket
import threading
import uuid
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


@pytest.fixture()
def postgres_store(tmp_path: Path):
    from evidence_handoff_runtime.config import FeatureConfig, LifecycleBootstrapContext
    from evidence_handoff_runtime.lifecycle import LifecycleError, LifecycleManager
    from evidence_handoff_runtime.migrations import apply_migrations
    from evidence_handoff_runtime.store import PostgresLedgerStore
    from optimus_security.sanitization import PathAliasRule

    port = _free_port()
    suffix = uuid.uuid4().hex[:8]
    password = f"store-{secrets.token_hex(8)}"
    capture = _abs(tmp_path, "capture")
    config = FeatureConfig.from_mapping(
        {
            "enabled": "true",
            "backend_id": "wslc",
            "bind_host": "127.0.0.1",
            "postgres_port": str(port),
            "container_name": f"evidence-handoff-store-{suffix}",
            "image": "postgres:16-alpine",
            "volume_name": f"evidence-handoff-store-data-{suffix}",
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
        control_root=_abs(tmp_path, "control"),
        store_admin_user="handoff",
        store_admin_password=password,
    )
    manager = LifecycleManager(config, bootstrap)
    try:
        started = manager.start()
        assert started.running is True
        instance_id = started.ledger_instance_id
        assert instance_id
        conninfo = (
            f"host=127.0.0.1 port={port} user=handoff password={password} "
            "dbname=postgres connect_timeout=5"
        )
        apply_migrations(conninfo)
        store = PostgresLedgerStore(conninfo=conninfo, ledger_instance_id=instance_id)
        store.ensure_instance_metadata()
        yield store
    finally:
        manager.stop()
        try:
            manager.destroy_for_test_cleanup()
        except LifecycleError:
            # Best-effort: start may have failed before the container existed.
            pass


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


def test_first_entry_null_predecessor_and_counter_head(postgres_store) -> None:
    store = postgres_store
    result = store.append(_sanitized(), _identity(), idempotency_key="idem-1")
    assert result.sequence == 1
    assert result.idempotent_replay is False
    status = store.current_status()
    assert status.last_committed == 1
    assert status.last_content_sha256 == result.content_sha256
    envelope = store.read_verified_global_range(start=1, watermark=1).entries[0]
    assert envelope.prev_content_sha256 is None
    assert envelope.sequence == 1


def test_same_key_idempotency_and_conflicting_retry(postgres_store) -> None:
    from evidence_handoff.ledger.errors import LedgerValidationError
    from evidence_handoff.ledger.models import (
        EntryKind,
        EntryMessage,
        MessagePart,
        SanitizedDraft,
        SchemaId,
    )

    store = postgres_store
    first = store.append(_sanitized(text="one"), _identity(), idempotency_key="idem-same")
    replay = store.append(_sanitized(text="one"), _identity(), idempotency_key="idem-same")
    assert replay.idempotent_replay is True
    assert replay.sequence == first.sequence
    assert replay.content_sha256 == first.content_sha256
    with pytest.raises(LedgerValidationError) as raised:
        store.append(_sanitized(text="different"), _identity(), idempotency_key="idem-same")
    assert raised.value.code == "idempotency_conflict"
    conflicting_recipients = SanitizedDraft(
        kind=EntryKind.REVIEW_RULING,
        schema_id=SchemaId.REVIEW_RULING.value,
        context_id="ctx-1",
        recipient_agent_ids=("other-agent",),
        message=EntryMessage(parts=(MessagePart(kind="text", text="one"),)),
        artifacts=(),
        task_id=None,
        in_reply_to=None,
        rule_counts={"exact_secret_replacement": 0},
    )
    with pytest.raises(LedgerValidationError) as recipients:
        store.append(conflicting_recipients, _identity(), idempotency_key="idem-same")
    assert recipients.value.code == "idempotency_conflict"
    assert store.current_status().last_committed == 1


def test_recipient_constraints_enforced_by_database(postgres_store) -> None:
    import psycopg

    store = postgres_store
    with psycopg.connect(store._conninfo) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                """
                INSERT INTO evidence_handoff_entries (
                    sequence, ledger_instance_id, entry_id, schema_id, kind, context_id, task_id,
                    in_reply_to, recipient_agent_ids, message_json, artifacts_json, principal_id,
                    agent_id, caller_role, authority, attestation, created_at, idempotency_key,
                    prev_content_sha256, content_sha256
                ) VALUES (
                    99, %s, 'entry-empty-recipients', 'review-ruling.v1', 'review-ruling', 'ctx',
                    NULL, NULL, '{}', '{"parts":[{"kind":"text","text":"x"}]}'::jsonb, '[]'::jsonb,
                    'p', 'a', 'reviewer', 'review-ruling', NULL, NOW(), 'idem-empty',
                    NULL, %s
                )
                """,
                (store._ledger_instance_id, "a" * 64),
            )
        conn.rollback()
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                """
                INSERT INTO evidence_handoff_entries (
                    sequence, ledger_instance_id, entry_id, schema_id, kind, context_id, task_id,
                    in_reply_to, recipient_agent_ids, message_json, artifacts_json, principal_id,
                    agent_id, caller_role, authority, attestation, created_at, idempotency_key,
                    prev_content_sha256, content_sha256
                ) VALUES (
                    99, %s, 'entry-dup-recipients', 'review-ruling.v1', 'review-ruling', 'ctx',
                    NULL, NULL, ARRAY['a1','a1'], '{"parts":[{"kind":"text","text":"x"}]}'::jsonb,
                    '[]'::jsonb, 'p', 'a', 'reviewer', 'review-ruling', NULL, NOW(), 'idem-dup',
                    NULL, %s
                )
                """,
                (store._ledger_instance_id, "b" * 64),
            )
        conn.rollback()


def test_concurrent_appends_are_gapless(postgres_store) -> None:
    store = postgres_store
    results = []
    errors = []

    def _worker(index: int) -> None:
        try:
            results.append(
                store.append(
                    _sanitized(text=f"ruling-{index}"),
                    _identity(),
                    idempotency_key=f"idem-{index}",
                )
            )
        except Exception as exc:  # noqa: BLE001 - collect for assertion
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert errors == []
    sequences = sorted(item.sequence for item in results)
    assert sequences == list(range(1, 9))
    assert store.current_status().last_committed == 8
    verified = store.verify_full()
    assert verified.verified is True
    assert verified.last_committed == 8


def test_rollback_leaves_counter_unchanged(postgres_store) -> None:
    from evidence_handoff.ledger.errors import LedgerStoreError

    store = postgres_store
    first = store.append(_sanitized(text="ok"), _identity(), idempotency_key="idem-ok")
    assert first.sequence == 1
    with pytest.raises(LedgerStoreError) as raised:
        store.append_with_forced_failure(_sanitized(text="boom"), _identity(), idempotency_key="idem-boom")
    assert raised.value.code == "forced_append_failure"
    status = store.current_status()
    assert status.last_committed == 1
    assert status.last_content_sha256 == first.content_sha256
    second = store.append(_sanitized(text="after"), _identity(), idempotency_key="idem-after")
    assert second.sequence == 2
