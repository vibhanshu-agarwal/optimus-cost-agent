"""Quarantine and linked chain-break recovery (no in-place history rewrite)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evidence_handoff_runtime.integrity import IntegrityIncident, IntegrityLatch


class RecoveryError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __repr__(self) -> str:
        return f"RecoveryError(code={self.code!r})"

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class QuarantineRecord:
    ledger_instance_id: str
    incident_id: str
    read_only: bool
    disposition: str

    def __repr__(self) -> str:
        return (
            "QuarantineRecord("
            f"ledger_instance_id={self.ledger_instance_id!r}, "
            f"incident_id={self.incident_id!r}, "
            f"read_only={self.read_only!r}, "
            f"disposition={self.disposition!r})"
        )


@dataclass(frozen=True, slots=True)
class RecoveryAnchor:
    ledger_instance_id: str
    sequence: int
    content_sha256: str
    verified: bool


@dataclass(frozen=True, slots=True)
class ReplacementInstance:
    ledger_instance_id: str
    predecessor_instance_id: str
    recovery_anchor_sequence: int
    recovery_anchor_digest: str
    incident_id: str

    def __repr__(self) -> str:
        return (
            "ReplacementInstance("
            f"ledger_instance_id={self.ledger_instance_id!r}, "
            f"predecessor_instance_id={self.predecessor_instance_id!r}, "
            f"recovery_anchor_sequence={self.recovery_anchor_sequence!r}, "
            f"recovery_anchor_digest={self.recovery_anchor_digest!r}, "
            f"incident_id={self.incident_id!r})"
        )


class RecoveryManager:
    """Explicit operator recovery path for latched integrity incidents."""

    def __init__(
        self,
        *,
        control_root: Path,
        store: Any | None = None,
        lifecycle: Any | None = None,
    ) -> None:
        self._control_root = control_root
        self._store = store
        self._lifecycle = lifecycle
        self._control_root.mkdir(parents=True, exist_ok=True)
        self._latch = IntegrityLatch(control_root=control_root)

    def quarantine(self, instance_id: str, *, incident: IntegrityIncident) -> QuarantineRecord:
        record = QuarantineRecord(
            ledger_instance_id=instance_id,
            incident_id=incident.incident_id,
            read_only=True,
            disposition="quarantined_read_only",
        )
        path = self._control_root / "quarantine.json"
        path.write_text(
            json.dumps(
                {
                    "ledger_instance_id": record.ledger_instance_id,
                    "incident_id": record.incident_id,
                    "read_only": True,
                    "disposition": record.disposition,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        if self._latch.load() is not None:
            self._latch.update_disposition("quarantined_read_only")
        return record

    def find_last_verified_anchor(self, instance_id: str) -> RecoveryAnchor:
        if self._store is None:
            raise RecoveryError("store_required_for_anchor")
        finder = getattr(self._store, "find_last_verified_anchor", None)
        if not callable(finder):
            raise RecoveryError("store_required_for_anchor")
        return finder(instance_id)

    def activate_linked_replacement(
        self,
        incident: IntegrityIncident,
        anchor: RecoveryAnchor,
    ) -> ReplacementInstance:
        if self._store is None:
            raise RecoveryError("store_required_for_replacement")
        creator = getattr(self._store, "create_linked_replacement", None)
        if not callable(creator):
            raise RecoveryError("store_required_for_replacement")
        payload = creator(incident=incident, anchor=anchor)
        replacement = ReplacementInstance(
            ledger_instance_id=str(payload["ledger_instance_id"]),
            predecessor_instance_id=str(payload["predecessor_instance_id"]),
            recovery_anchor_sequence=int(payload["recovery_anchor_sequence"]),
            recovery_anchor_digest=str(payload["recovery_anchor_digest"]),
            incident_id=str(payload["incident_id"]),
        )
        # Predecessor latch remains permanent; mark replaced without clearing.
        if self._latch.load() is not None:
            self._latch.update_disposition("replaced")
        return replacement

    def clear_latch_automatically(self, incident: IntegrityIncident) -> None:
        raise RecoveryError("automatic_clear_forbidden")

    def repair_in_place(self, incident: IntegrityIncident) -> None:
        raise RecoveryError("in_place_repair_forbidden")

    def copy_untrusted_tail(self, incident: IntegrityIncident, *, destination_instance_id: str) -> None:
        raise RecoveryError("untrusted_tail_copy_forbidden")


__all__ = [
    "QuarantineRecord",
    "RecoveryAnchor",
    "RecoveryError",
    "RecoveryManager",
    "ReplacementInstance",
]
