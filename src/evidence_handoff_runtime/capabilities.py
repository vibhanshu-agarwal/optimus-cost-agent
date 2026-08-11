"""Reader capabilities, coordinated writer activation, and principal retirement."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

_ADMIN_SCOPE = "ledger.admin"
CAPABILITY_STALE_AFTER = timedelta(hours=24)
_DEFAULT_STALE_AFTER = CAPABILITY_STALE_AFTER


def capability_report_is_fresh(
    reported_at: datetime | None,
    *,
    now: datetime,
    stale_after: timedelta = CAPABILITY_STALE_AFTER,
    has_schemas: bool = True,
) -> bool:
    """True only when a non-empty schema report was recorded within stale_after."""
    if not has_schemas or reported_at is None:
        return False
    instant = reported_at
    if getattr(instant, "tzinfo", None) is None:
        instant = instant.replace(tzinfo=UTC)
    return instant >= (now - stale_after)


class ActivationError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __repr__(self) -> str:
        return f"ActivationError(code={self.code!r})"

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class ReaderCapability:
    agent_id: str
    principal_id: str
    supported_schemas: frozenset[str]
    reported_at: datetime
    retired: bool


@dataclass(frozen=True, slots=True)
class ActivationBlockers:
    stale_or_incompatible_principal_ids: frozenset[str]
    blocking: bool


@dataclass(frozen=True, slots=True)
class ActivationStatus:
    schema_id: str
    writer_active: bool
    activated_at: datetime


@dataclass(frozen=True, slots=True)
class AdministrativeAuditResult:
    principal_id: str
    agent_id: str
    retired: bool
    audit_event_id: str


def _caller_scopes(caller: Any) -> frozenset[str]:
    scopes = getattr(caller, "scopes", None)
    if scopes is None:
        scopes = getattr(caller, "scope", frozenset())
    return frozenset(str(item) for item in scopes or ())


def _require_admin(caller: Any) -> None:
    if _ADMIN_SCOPE not in _caller_scopes(caller):
        raise ActivationError("admin_required")


class CapabilityCoordinator:
    def __init__(
        self,
        *,
        store: Any,
        now: Callable[[], datetime] | None = None,
        stale_after: timedelta = CAPABILITY_STALE_AFTER,
        registered_readers: Mapping[str, str] | None = None,
    ) -> None:
        self._store = store
        self._now = now or (lambda: datetime.now(tz=UTC))
        self._stale_after = stale_after
        # principal_id -> agent_id for enrolled readers (optional; unit tests omit).
        self._registered_readers = dict(registered_readers or {})

    def record_capability(self, capability: ReaderCapability) -> None:
        self._store.upsert_reader_capability(capability)

    def get_capability(self, *, principal_id: str) -> ReaderCapability:
        return self._store.get_reader_capability(principal_id)

    def preflight_activation(self, schema_id: str) -> ActivationBlockers:
        blocked: set[str] = set()
        now = self._now()
        caps = {str(cap.principal_id): cap for cap in self._store.list_reader_capabilities()}
        principal_ids = (
            set(self._registered_readers) if self._registered_readers else set(caps)
        )
        for principal_id in principal_ids:
            cap = caps.get(str(principal_id))
            if cap is not None and cap.retired:
                continue
            if cap is None:
                blocked.add(str(principal_id))
                continue
            missing = str(schema_id) not in set(cap.supported_schemas)
            fresh = capability_report_is_fresh(
                cap.reported_at,
                now=now,
                stale_after=self._stale_after,
                has_schemas=bool(cap.supported_schemas),
            )
            if missing or not fresh:
                blocked.add(str(principal_id))
        return ActivationBlockers(
            stale_or_incompatible_principal_ids=frozenset(blocked),
            blocking=bool(blocked),
        )

    def activate_writer(self, schema_id: str, *, caller: Any) -> ActivationStatus:
        _require_admin(caller)
        blockers = self.preflight_activation(schema_id)
        if blockers.blocking:
            raise ActivationError("activation_blocked")
        return self._store.set_writer_active(schema_id, active=True)

    def retire_principal(
        self,
        principal_id: str,
        *,
        caller: Any,
        agent_id: str | None = None,
    ) -> AdministrativeAuditResult:
        _require_admin(caller)
        if agent_id is not None:
            return self._store.retire_principal(principal_id, agent_id=agent_id)
        return self._store.retire_principal(principal_id)


__all__ = [
    "ActivationBlockers",
    "ActivationError",
    "ActivationStatus",
    "AdministrativeAuditResult",
    "CapabilityCoordinator",
    "ReaderCapability",
    "CAPABILITY_STALE_AFTER",
    "capability_report_is_fresh",
]
