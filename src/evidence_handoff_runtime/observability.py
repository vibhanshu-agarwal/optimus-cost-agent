"""Content-free delivery observability — facts only, no liveness guesses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class DeliveryView:
    agent_id: str
    principal_id: str
    principal_status: str
    confirmed_sequence: int
    last_confirmed_at: datetime | None
    visible_unread_count: int
    last_authenticated_request_at: datetime | None
    last_acknowledgement_sequence: int | None
    last_acknowledgement_at: datetime | None
    capability_reported_at: datetime | None
    capability_fresh: bool
    activation_blocked: bool
    warning_delivery: str
    integrity: dict[str, Any]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "principal_id": self.principal_id,
            "principal_status": self.principal_status,
            "confirmed_sequence": self.confirmed_sequence,
            "last_confirmed_at": self.last_confirmed_at.isoformat()
            if self.last_confirmed_at is not None
            else None,
            "visible_unread_count": self.visible_unread_count,
            "last_authenticated_request_at": self.last_authenticated_request_at.isoformat()
            if self.last_authenticated_request_at is not None
            else None,
            "last_acknowledgement_sequence": self.last_acknowledgement_sequence,
            "last_acknowledgement_at": self.last_acknowledgement_at.isoformat()
            if self.last_acknowledgement_at is not None
            else None,
            "capability_reported_at": self.capability_reported_at.isoformat()
            if self.capability_reported_at is not None
            else None,
            "capability_fresh": self.capability_fresh,
            "activation_blocked": self.activation_blocked,
            "warning_delivery": self.warning_delivery,
            "integrity": dict(self.integrity),
        }


def build_delivery_views(*, store: Any) -> tuple[DeliveryView, ...]:
    integrity = dict(store.global_integrity_fact() or {})
    views: list[DeliveryView] = []
    for row in store.list_delivery_facts() or ():
        views.append(
            DeliveryView(
                agent_id=str(row["agent_id"]),
                principal_id=str(row["principal_id"]),
                principal_status=str(row.get("principal_status") or "active"),
                confirmed_sequence=int(row.get("confirmed_sequence") or 0),
                last_confirmed_at=row.get("last_confirmed_at"),
                visible_unread_count=int(row.get("visible_unread_count") or 0),
                last_authenticated_request_at=row.get("last_authenticated_request_at"),
                last_acknowledgement_sequence=row.get("last_acknowledgement_sequence"),
                last_acknowledgement_at=row.get("last_acknowledgement_at"),
                capability_reported_at=row.get("capability_reported_at"),
                capability_fresh=bool(row.get("capability_fresh")),
                activation_blocked=bool(row.get("activation_blocked")),
                warning_delivery=str(row.get("warning_delivery") or "not_yet_requested"),
                integrity=integrity,
            )
        )
    return tuple(views)


def rebuild_delivery_projection(*, store: Any) -> dict[str, Any]:
    return dict(store.rebuild_delivery_projection())


__all__ = ["DeliveryView", "build_delivery_views", "rebuild_delivery_projection"]
