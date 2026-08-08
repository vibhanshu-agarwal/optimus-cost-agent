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
