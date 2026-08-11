"""Unit tests for content-free integrity classification, latching, and status."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_integrity_causes_match_design_stable_set() -> None:
    from evidence_handoff_runtime.integrity import IntegrityCause

    assert {cause.value for cause in IntegrityCause} == {
        "sequence_duplicate",
        "sequence_gap",
        "chain_break",
        "counter_head_mismatch",
        "rollback_divergence",
        "ledger_instance_mismatch",
    }


def test_integrity_incident_is_content_free_and_non_retryable(tmp_path: Path) -> None:
    from evidence_handoff_runtime.integrity import IntegrityCause, IntegrityIncident

    incident = IntegrityIncident(
        incident_id="inc-1",
        cause=IntegrityCause.CHAIN_BREAK,
        ledger_instance_id="inst-1",
        safe_boundary_sequence=3,
        detected_at="2026-08-08T12:00:00+00:00",
        disposition="latched",
    )
    rendered = repr(incident)
    assert "ruling" not in rendered
    assert "message" not in rendered
    assert incident.failure_class == "ledger_integrity_failed"
    assert incident.retryable is False
    mapping = incident.to_public_mapping()
    assert set(mapping) <= {
        "incident_id",
        "cause",
        "ledger_instance_id",
        "safe_boundary_sequence",
        "detected_at",
        "disposition",
        "failure_class",
        "retryable",
    }
    assert "entry_body" not in mapping
    assert "content_sha256" not in mapping


def test_integrity_latch_persists_atomically_and_reloads(tmp_path: Path) -> None:
    from evidence_handoff_runtime.integrity import IntegrityCause, IntegrityIncident, IntegrityLatch

    control_root = tmp_path / "control"
    control_root.mkdir()
    incident = IntegrityIncident(
        incident_id="inc-persist",
        cause=IntegrityCause.SEQUENCE_GAP,
        ledger_instance_id="inst-a",
        safe_boundary_sequence=2,
        detected_at="2026-08-08T12:01:00+00:00",
        disposition="latched",
    )
    latch = IntegrityLatch(control_root=control_root)
    latch.persist(incident)
    reloaded = IntegrityLatch(control_root=control_root).load()
    assert reloaded is not None
    assert reloaded.incident_id == "inc-persist"
    assert reloaded.cause is IntegrityCause.SEQUENCE_GAP
    assert reloaded.safe_boundary_sequence == 2
    # Latch file must not embed entry bodies or digests beyond the safe boundary integer.
    payload = json.loads((control_root / "integrity_latch.json").read_text(encoding="utf-8"))
    assert "message" not in json.dumps(payload)
    assert "prev_content_sha256" not in json.dumps(payload)


def test_integrity_latch_fail_closed_when_persist_impossible(tmp_path: Path) -> None:
    from evidence_handoff_runtime.integrity import (
        IntegrityCause,
        IntegrityIncident,
        IntegrityLatch,
        IntegrityLatchError,
    )

    blocked = tmp_path / "missing-parent" / "control"
    latch = IntegrityLatch(control_root=blocked)
    incident = IntegrityIncident(
        incident_id="inc-fail",
        cause=IntegrityCause.COUNTER_HEAD_MISMATCH,
        ledger_instance_id="inst-b",
        safe_boundary_sequence=0,
        detected_at="2026-08-08T12:02:00+00:00",
        disposition="latched",
    )
    with pytest.raises(IntegrityLatchError) as raised:
        latch.persist(incident)
    assert raised.value.code == "integrity_latch_persist_failed"


def test_monitor_latches_on_verify_full_and_blocks_normal_ops(tmp_path: Path) -> None:
    from evidence_handoff_runtime.integrity import (
        IntegrityCause,
        IntegrityMonitor,
        LedgerIntegrityError,
    )

    class _BrokenStore:
        ledger_instance_id = "inst-broken"

        def verify_full(self):  # noqa: ANN202 - double
            raise LedgerIntegrityError(
                cause=IntegrityCause.CHAIN_BREAK,
                ledger_instance_id=self.ledger_instance_id,
                safe_boundary_sequence=1,
            )

        def mirror_integrity_incident(self, incident: object) -> None:
            return None

        def append(self, *_args, **_kwargs):  # noqa: ANN002,ANN003
            raise AssertionError("append must be refused while latched")

    control_root = tmp_path / "control"
    control_root.mkdir()
    monitor = IntegrityMonitor(store=_BrokenStore(), control_root=control_root)
    with pytest.raises(LedgerIntegrityError) as raised:
        monitor.verify_full()
    assert raised.value.code == "ledger_integrity_failed"
    assert raised.value.cause is IntegrityCause.CHAIN_BREAK
    assert raised.value.retryable is False

    status = monitor.status()
    assert status.failure_class == "ledger_integrity_failed"
    assert status.incident is not None
    assert status.incident.cause is IntegrityCause.CHAIN_BREAK
    assert status.normal_operations_allowed is False
    assert status.active_route != "operator_relay" or status.may_auto_relay is False

    # Restart simulation: new monitor, same control root, no store call required.
    restarted = IntegrityMonitor(store=_BrokenStore(), control_root=control_root)
    assert restarted.status().incident is not None
    assert restarted.status().incident.incident_id == status.incident.incident_id
    with pytest.raises(LedgerIntegrityError):
        restarted.refuse_if_latched()


def test_monitor_verify_unfiltered_range_latches_on_gap(tmp_path: Path) -> None:
    from evidence_handoff_runtime.integrity import (
        IntegrityCause,
        IntegrityMonitor,
        LedgerIntegrityError,
    )

    class _GapStore:
        ledger_instance_id = "inst-gap"

        def verify_unfiltered_range(self, *, reader_cursor: int, watermark: int, anchor: object):  # noqa: ANN001
            raise LedgerIntegrityError(
                cause=IntegrityCause.SEQUENCE_GAP,
                ledger_instance_id=self.ledger_instance_id,
                safe_boundary_sequence=reader_cursor,
            )

        def mirror_integrity_incident(self, incident: object) -> None:
            return None

    control_root = tmp_path / "control"
    control_root.mkdir()
    monitor = IntegrityMonitor(store=_GapStore(), control_root=control_root)
    with pytest.raises(LedgerIntegrityError) as raised:
        monitor.verify_unfiltered_range(reader_cursor=1, watermark=5, anchor=None)
    assert raised.value.cause is IntegrityCause.SEQUENCE_GAP
    assert monitor.status().incident is not None


def test_integrity_latch_fail_closed_on_corrupt_file(tmp_path: Path) -> None:
    from evidence_handoff_runtime.integrity import IntegrityLatch, IntegrityLatchError

    control_root = tmp_path / "control"
    control_root.mkdir()
    (control_root / "integrity_latch.json").write_text("{not-json", encoding="utf-8")
    latch = IntegrityLatch(control_root=control_root)
    with pytest.raises(IntegrityLatchError) as raised:
        latch.load()
    assert raised.value.code == "integrity_latch_corrupt"


def test_clear_false_positive_rejected_without_repeated_verification(tmp_path: Path) -> None:
    from evidence_handoff_runtime.integrity import (
        IntegrityCause,
        IntegrityIncident,
        IntegrityLatch,
        IntegrityMonitor,
        IntegrityRecoveryError,
    )

    control_root = tmp_path / "control"
    control_root.mkdir()
    incident = IntegrityIncident(
        incident_id="inc-fp",
        cause=IntegrityCause.CHAIN_BREAK,
        ledger_instance_id="inst-fp",
        safe_boundary_sequence=4,
        detected_at="2026-08-08T12:03:00+00:00",
        disposition="latched",
    )
    IntegrityLatch(control_root=control_root).persist(incident)

    class _Store:
        ledger_instance_id = "inst-fp"

        def verify_full(self):  # noqa: ANN202
            raise AssertionError("clear path must not auto-verify away genuine breaks")

    monitor = IntegrityMonitor(store=_Store(), control_root=control_root)
    with pytest.raises(IntegrityRecoveryError) as raised:
        monitor.clear_false_positive(witnesses=())
    assert raised.value.code in {"false_positive_clear_refused", "genuine_corruption_uncleared"}
    assert monitor.status().incident is not None


def _mirrored_latch_payload(
    *,
    incident_id: str = "ca00677d-133d-4ec0-9934-4563d54db2ed",
    ledger_instance_id: str = "inst-live",
) -> dict:
    return {
        "incident_id": incident_id,
        "cause": "chain_break",
        "ledger_instance_id": ledger_instance_id,
        "safe_boundary_sequence": 0,
        "detected_at": "2026-08-10T17:00:00+00:00",
        "disposition": "latched",
        "failure_class": "ledger_integrity_failed",
        "retryable": False,
    }


def _patch_control_state_latch(monkeypatch: pytest.MonkeyPatch, payload: dict | None) -> None:
    """Stub psycopg.connect so control_state SELECT returns ``payload`` (or no row)."""
    import evidence_handoff_runtime.store as store_mod

    class _Result:
        def fetchone(self):
            if payload is None:
                return None
            return {"value_json": payload}

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def execute(self, query: str, params: object = None):  # noqa: ANN001
            assert "evidence_handoff_control_state" in str(query)
            assert params == ("integrity_latch",)
            return _Result()

        def commit(self) -> None:
            return None

    monkeypatch.setattr(store_mod.psycopg, "connect", lambda *a, **k: _Conn())


def test_store_without_control_root_reports_db_mirrored_latch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Production shape: service builds PostgresLedgerStore with control_root=None."""
    from evidence_handoff_runtime.store import PostgresLedgerStore

    payload = _mirrored_latch_payload()
    _patch_control_state_latch(monkeypatch, payload)
    store = PostgresLedgerStore(
        conninfo="host=unused dbname=postgres",
        ledger_instance_id="inst-live",
        control_root=None,
    )
    fact = store.global_integrity_fact()
    assert fact["latched"] is True
    assert fact["incident_id"] == payload["incident_id"]
    assert fact["cause"] == "chain_break"
    assert fact["safe_boundary_sequence"] == 0


def test_store_without_control_root_refuses_when_db_latch_matches_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from evidence_handoff_runtime.integrity import LedgerIntegrityError
    from evidence_handoff_runtime.store import PostgresLedgerStore

    _patch_control_state_latch(monkeypatch, _mirrored_latch_payload(ledger_instance_id="inst-live"))
    store = PostgresLedgerStore(
        conninfo="host=unused dbname=postgres",
        ledger_instance_id="inst-live",
        control_root=None,
    )
    with pytest.raises(LedgerIntegrityError) as raised:
        store._refuse_if_integrity_latched()
    assert raised.value.cause.value == "chain_break"
    assert raised.value.ledger_instance_id == "inst-live"


def test_store_without_control_root_permits_when_db_latch_is_predecessor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task 4: predecessor latch must not block a linked replacement instance."""
    from evidence_handoff_runtime.store import PostgresLedgerStore

    _patch_control_state_latch(
        monkeypatch,
        _mirrored_latch_payload(ledger_instance_id="inst-predecessor"),
    )
    replacement = PostgresLedgerStore(
        conninfo="host=unused dbname=postgres",
        ledger_instance_id="inst-replacement",
        control_root=None,
    )
    replacement._refuse_if_integrity_latched()  # must not raise
    fact = replacement.global_integrity_fact()
    # Fact remains content-free and global; refuse path is what scopes by instance.
    assert fact["latched"] is True
    assert fact["incident_id"] == "ca00677d-133d-4ec0-9934-4563d54db2ed"


def test_persist_latch_propagates_mirror_failure_after_file_persist(tmp_path: Path) -> None:
    """DB mirror is production's only latch source; swallow would fail open."""
    from evidence_handoff_runtime.integrity import (
        IntegrityCause,
        IntegrityMonitor,
        LedgerIntegrityError,
    )

    class _MirrorBoomStore:
        ledger_instance_id = "inst-mirror-boom"

        def verify_full(self):  # noqa: ANN202
            raise LedgerIntegrityError(
                cause=IntegrityCause.CHAIN_BREAK,
                ledger_instance_id=self.ledger_instance_id,
                safe_boundary_sequence=1,
            )

        def mirror_integrity_incident(self, incident: object) -> None:
            raise RuntimeError("mirror_write_failed")

    control_root = tmp_path / "control"
    control_root.mkdir()
    monitor = IntegrityMonitor(store=_MirrorBoomStore(), control_root=control_root)

    with pytest.raises(RuntimeError, match="mirror_write_failed"):
        monitor.verify_full()

    # File latch must still have been written before the mirror failure.
    assert (control_root / "integrity_latch.json").is_file()


def test_persist_latch_requires_mirror_method_on_store(tmp_path: Path) -> None:
    """A store without mirror_integrity_incident must not silently skip mirroring."""
    from evidence_handoff_runtime.integrity import (
        IntegrityCause,
        IntegrityMonitor,
        LedgerIntegrityError,
    )

    class _NoMirrorStore:
        ledger_instance_id = "inst-no-mirror"

        def verify_full(self):  # noqa: ANN202
            raise LedgerIntegrityError(
                cause=IntegrityCause.CHAIN_BREAK,
                ledger_instance_id=self.ledger_instance_id,
                safe_boundary_sequence=2,
            )

    control_root = tmp_path / "control"
    control_root.mkdir()
    monitor = IntegrityMonitor(store=_NoMirrorStore(), control_root=control_root)

    with pytest.raises(AttributeError):
        monitor.verify_full()
