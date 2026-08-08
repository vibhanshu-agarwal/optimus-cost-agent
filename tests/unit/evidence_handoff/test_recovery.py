"""Unit tests for quarantine and linked chain-break recovery."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_recovery_quarantines_predecessor_read_only(tmp_path: Path) -> None:
    from evidence_handoff_runtime.integrity import IntegrityCause, IntegrityIncident
    from evidence_handoff_runtime.recovery import RecoveryManager

    incident = IntegrityIncident(
        incident_id="inc-q",
        cause=IntegrityCause.CHAIN_BREAK,
        ledger_instance_id="inst-pred",
        safe_boundary_sequence=2,
        detected_at="2026-08-08T13:00:00+00:00",
        disposition="latched",
    )
    manager = RecoveryManager(control_root=tmp_path / "control", store=None)
    quarantine = manager.quarantine("inst-pred", incident=incident)
    assert quarantine.ledger_instance_id == "inst-pred"
    assert quarantine.read_only is True
    assert quarantine.incident_id == "inc-q"
    # Quarantine metadata never claims the tail was repaired.
    assert quarantine.disposition == "quarantined_read_only"
    assert "repaired" not in repr(quarantine).lower()
    assert "copied" not in repr(quarantine).lower()


def test_find_last_verified_anchor_stops_before_untrusted_tail(tmp_path: Path) -> None:
    from evidence_handoff_runtime.integrity import IntegrityCause, IntegrityIncident
    from evidence_handoff_runtime.recovery import RecoveryAnchor, RecoveryManager

    class _Store:
        def find_last_verified_anchor(self, instance_id: str) -> RecoveryAnchor:
            assert instance_id == "inst-pred"
            return RecoveryAnchor(
                ledger_instance_id="inst-pred",
                sequence=2,
                content_sha256="a" * 64,
                verified=True,
            )

    incident = IntegrityIncident(
        incident_id="inc-anchor",
        cause=IntegrityCause.SEQUENCE_GAP,
        ledger_instance_id="inst-pred",
        safe_boundary_sequence=2,
        detected_at="2026-08-08T13:01:00+00:00",
        disposition="latched",
    )
    manager = RecoveryManager(control_root=tmp_path / "control", store=_Store())
    manager.quarantine("inst-pred", incident=incident)
    anchor = manager.find_last_verified_anchor("inst-pred")
    assert anchor.sequence == 2
    assert anchor.verified is True
    assert len(anchor.content_sha256) == 64


def test_activate_linked_replacement_preserves_predecessor_latch(tmp_path: Path) -> None:
    from evidence_handoff_runtime.integrity import (
        IntegrityCause,
        IntegrityIncident,
        IntegrityLatch,
    )
    from evidence_handoff_runtime.recovery import RecoveryAnchor, RecoveryManager

    control_root = tmp_path / "control"
    control_root.mkdir()
    incident = IntegrityIncident(
        incident_id="inc-link",
        cause=IntegrityCause.CHAIN_BREAK,
        ledger_instance_id="inst-pred",
        safe_boundary_sequence=5,
        detected_at="2026-08-08T13:02:00+00:00",
        disposition="latched",
    )
    IntegrityLatch(control_root=control_root).persist(incident)
    anchor = RecoveryAnchor(
        ledger_instance_id="inst-pred",
        sequence=5,
        content_sha256="b" * 64,
        verified=True,
    )

    created: dict[str, object] = {}

    class _Store:
        def create_linked_replacement(self, *, incident, anchor):  # noqa: ANN001
            created["incident"] = incident
            created["anchor"] = anchor
            return {
                "ledger_instance_id": "inst-replacement",
                "predecessor_instance_id": "inst-pred",
                "recovery_anchor_sequence": anchor.sequence,
                "recovery_anchor_digest": anchor.content_sha256,
                "incident_id": incident.incident_id,
            }

    manager = RecoveryManager(control_root=control_root, store=_Store())
    manager.quarantine("inst-pred", incident=incident)
    replacement = manager.activate_linked_replacement(incident, anchor)
    assert replacement.ledger_instance_id == "inst-replacement"
    assert replacement.predecessor_instance_id == "inst-pred"
    assert replacement.recovery_anchor_sequence == 5
    assert replacement.recovery_anchor_digest == "b" * 64
    assert replacement.incident_id == "inc-link"
    # Predecessor latch remains permanent status after activation.
    predecessor = IntegrityLatch(control_root=control_root).load()
    assert predecessor is not None
    assert predecessor.incident_id == "inc-link"
    assert predecessor.disposition in {"latched", "quarantined_read_only", "replaced"}


def test_automatic_clear_and_in_place_repair_are_rejected(tmp_path: Path) -> None:
    from evidence_handoff_runtime.integrity import IntegrityCause, IntegrityIncident
    from evidence_handoff_runtime.recovery import RecoveryError, RecoveryManager

    incident = IntegrityIncident(
        incident_id="inc-no-clear",
        cause=IntegrityCause.ROLLBACK_DIVERGENCE,
        ledger_instance_id="inst-broken",
        safe_boundary_sequence=1,
        detected_at="2026-08-08T13:03:00+00:00",
        disposition="latched",
    )
    manager = RecoveryManager(control_root=tmp_path / "control", store=None)
    manager.quarantine("inst-broken", incident=incident)
    with pytest.raises(RecoveryError) as auto:
        manager.clear_latch_automatically(incident)
    assert auto.value.code == "automatic_clear_forbidden"

    with pytest.raises(RecoveryError) as repair:
        manager.repair_in_place(incident)
    assert repair.value.code == "in_place_repair_forbidden"

    with pytest.raises(RecoveryError) as copy_tail:
        manager.copy_untrusted_tail(incident, destination_instance_id="inst-new")
    assert copy_tail.value.code == "untrusted_tail_copy_forbidden"
