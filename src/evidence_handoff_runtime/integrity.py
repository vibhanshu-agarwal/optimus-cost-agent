"""Content-free ledger integrity classification, latching, and monitoring."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class IntegrityCause(StrEnum):
    SEQUENCE_DUPLICATE = "sequence_duplicate"
    SEQUENCE_GAP = "sequence_gap"
    CHAIN_BREAK = "chain_break"
    COUNTER_HEAD_MISMATCH = "counter_head_mismatch"
    ROLLBACK_DIVERGENCE = "rollback_divergence"
    LEDGER_INSTANCE_MISMATCH = "ledger_instance_mismatch"


class IntegrityLatchError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __repr__(self) -> str:
        return f"IntegrityLatchError(code={self.code!r})"

    def __str__(self) -> str:
        return self.code


class IntegrityRecoveryError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __repr__(self) -> str:
        return f"IntegrityRecoveryError(code={self.code!r})"

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class IntegrityIncident:
    incident_id: str
    cause: IntegrityCause
    ledger_instance_id: str
    safe_boundary_sequence: int
    detected_at: str
    disposition: str

    @property
    def failure_class(self) -> str:
        return "ledger_integrity_failed"

    @property
    def retryable(self) -> bool:
        return False

    def to_public_mapping(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "cause": self.cause.value,
            "ledger_instance_id": self.ledger_instance_id,
            "safe_boundary_sequence": self.safe_boundary_sequence,
            "detected_at": self.detected_at,
            "disposition": self.disposition,
            "failure_class": self.failure_class,
            "retryable": self.retryable,
        }

    def __repr__(self) -> str:
        return (
            "IntegrityIncident("
            f"incident_id={self.incident_id!r}, "
            f"cause={self.cause!r}, "
            f"ledger_instance_id={self.ledger_instance_id!r}, "
            f"safe_boundary_sequence={self.safe_boundary_sequence!r}, "
            f"detected_at={self.detected_at!r}, "
            f"disposition={self.disposition!r})"
        )


class LedgerIntegrityError(Exception):
    """Non-retryable ledger integrity failure."""

    def __init__(
        self,
        *,
        cause: IntegrityCause,
        ledger_instance_id: str,
        safe_boundary_sequence: int,
        incident_id: str | None = None,
        detected_at: str | None = None,
        disposition: str = "latched",
    ) -> None:
        self.code = "ledger_integrity_failed"
        self.cause = cause
        self.ledger_instance_id = ledger_instance_id
        self.safe_boundary_sequence = safe_boundary_sequence
        self.incident_id = incident_id or str(uuid.uuid4())
        self.detected_at = detected_at or datetime.now(UTC).isoformat()
        self.disposition = disposition
        self.retryable = False
        self.failure_class = "ledger_integrity_failed"
        super().__init__(self.code)

    def to_incident(self) -> IntegrityIncident:
        return IntegrityIncident(
            incident_id=self.incident_id,
            cause=self.cause,
            ledger_instance_id=self.ledger_instance_id,
            safe_boundary_sequence=self.safe_boundary_sequence,
            detected_at=self.detected_at,
            disposition=self.disposition,
        )

    def __repr__(self) -> str:
        return (
            "LedgerIntegrityError("
            f"code={self.code!r}, cause={self.cause!r}, "
            f"incident_id={self.incident_id!r}, "
            f"safe_boundary_sequence={self.safe_boundary_sequence!r})"
        )

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class IntegrityStatus:
    failure_class: str | None
    incident: IntegrityIncident | None
    normal_operations_allowed: bool
    may_auto_relay: bool
    active_route: str


_LATCH_FILENAME = "integrity_latch.json"


class IntegrityLatch:
    """Durable content-free integrity latch outside the ledger database."""

    def __init__(self, *, control_root: Path) -> None:
        self._control_root = control_root
        self._path = control_root / _LATCH_FILENAME

    def persist(self, incident: IntegrityIncident) -> None:
        if not self._control_root.is_dir():
            raise IntegrityLatchError("integrity_latch_persist_failed")
        durable = {
            "incident_id": incident.incident_id,
            "cause": incident.cause.value,
            "ledger_instance_id": incident.ledger_instance_id,
            "safe_boundary_sequence": incident.safe_boundary_sequence,
            "detected_at": incident.detected_at,
            "disposition": incident.disposition,
        }
        tmp_path = self._path.with_suffix(".tmp")
        try:
            tmp_path.write_text(json.dumps(durable, sort_keys=True) + "\n", encoding="utf-8")
            try:
                os.chmod(tmp_path, 0o600)
            except OSError:
                pass
            os.replace(tmp_path, self._path)
            try:
                os.chmod(self._path, 0o600)
            except OSError:
                pass
        except OSError as exc:
            tmp_path.unlink(missing_ok=True)
            raise IntegrityLatchError("integrity_latch_persist_failed") from exc

    def load(self) -> IntegrityIncident | None:
        if not self._path.is_file():
            return None
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise IntegrityLatchError("integrity_latch_corrupt") from exc
        try:
            return IntegrityIncident(
                incident_id=str(payload["incident_id"]),
                cause=IntegrityCause(str(payload["cause"])),
                ledger_instance_id=str(payload["ledger_instance_id"]),
                safe_boundary_sequence=int(payload["safe_boundary_sequence"]),
                detected_at=str(payload["detected_at"]),
                disposition=str(payload["disposition"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise IntegrityLatchError("integrity_latch_corrupt") from exc

    def update_disposition(self, disposition: str) -> IntegrityIncident | None:
        current = self.load()
        if current is None:
            return None
        updated = IntegrityIncident(
            incident_id=current.incident_id,
            cause=current.cause,
            ledger_instance_id=current.ledger_instance_id,
            safe_boundary_sequence=current.safe_boundary_sequence,
            detected_at=current.detected_at,
            disposition=disposition,
        )
        self.persist(updated)
        return updated


class IntegrityMonitor:
    """Continuous verification that latches non-retryable integrity failures."""

    def __init__(
        self,
        *,
        store: Any,
        control_root: Path,
        lifecycle: Any | None = None,
    ) -> None:
        self._store = store
        self._control_root = control_root
        self._lifecycle = lifecycle
        self._latch = IntegrityLatch(control_root=control_root)
        attach = getattr(store, "attach_integrity_control_root", None)
        if callable(attach):
            attach(control_root)

    def status(self) -> IntegrityStatus:
        incident = self._latch.load()
        if incident is None:
            return IntegrityStatus(
                failure_class=None,
                incident=None,
                normal_operations_allowed=True,
                may_auto_relay=False,
                active_route="ledger",
            )
        return IntegrityStatus(
            failure_class="ledger_integrity_failed",
            incident=incident,
            normal_operations_allowed=False,
            may_auto_relay=False,
            active_route="integrity_hold",
        )

    def refuse_if_latched(self) -> None:
        incident = self._latch.load()
        if incident is None:
            return
        raise LedgerIntegrityError(
            cause=incident.cause,
            ledger_instance_id=incident.ledger_instance_id,
            safe_boundary_sequence=incident.safe_boundary_sequence,
            incident_id=incident.incident_id,
            detected_at=incident.detected_at,
            disposition=incident.disposition,
        )

    def verify_readiness(self) -> Any:
        return self.verify_full()

    def verify_full(self, external_witnesses: tuple[dict[str, Any], ...] = ()) -> Any:
        self.refuse_if_latched()
        try:
            try:
                result = self._store.verify_full(external_witnesses=external_witnesses)
            except TypeError:
                if external_witnesses:
                    raise
                result = self._store.verify_full()
            return result
        except LedgerIntegrityError as exc:
            self._persist_latch(exc)
            raise

    def verify_unfiltered_range(
        self,
        *,
        reader_cursor: int,
        watermark: int,
        anchor: object,
    ) -> Any:
        self.refuse_if_latched()
        try:
            return self._store.verify_unfiltered_range(
                reader_cursor=reader_cursor,
                watermark=watermark,
                anchor=anchor,
            )
        except LedgerIntegrityError as exc:
            self._persist_latch(exc)
            raise

    def clear_false_positive(self, *, witnesses: tuple[object, ...] = ()) -> None:
        incident = self._latch.load()
        if incident is None:
            return
        if not witnesses:
            raise IntegrityRecoveryError("false_positive_clear_refused")
        raise IntegrityRecoveryError("genuine_corruption_uncleared")

    def _persist_latch(self, error: LedgerIntegrityError) -> None:
        incident = error.to_incident()
        self._latch.persist(incident)
        # Production (control_root=None on the store) reads only the DB mirror — never swallow.
        self._store.mirror_integrity_incident(incident)


__all__ = [
    "IntegrityCause",
    "IntegrityIncident",
    "IntegrityLatch",
    "IntegrityLatchError",
    "IntegrityMonitor",
    "IntegrityRecoveryError",
    "IntegrityStatus",
    "LedgerIntegrityError",
]
