"""Content-free feature control state for default-off degradation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evidence_handoff_runtime.config import Availability, FeatureConfig


@dataclass(frozen=True)
class FeatureControlState:
    availability: Availability
    active_route: str
    summary_code: str
    may_start_infrastructure: bool
    projected_credential: str | None
    integrity_incident: Any | None = None


def build_control_state(
    config: FeatureConfig,
    *,
    integrity_incident: Any | None = None,
) -> FeatureControlState:
    if integrity_incident is not None:
        return FeatureControlState(
            availability=Availability.UNAVAILABLE,
            active_route="integrity_hold",
            summary_code="ledger_integrity_failed",
            may_start_infrastructure=False,
            projected_credential=None,
            integrity_incident=integrity_incident,
        )
    if not config.enabled:
        return FeatureControlState(
            availability=Availability.DISABLED,
            active_route="operator_relay",
            summary_code="feature_disabled_operator_relay",
            may_start_infrastructure=False,
            projected_credential=None,
        )
    return FeatureControlState(
        availability=Availability.UNAVAILABLE,
        active_route="operator_relay",
        summary_code="feature_enabled_awaiting_lifecycle",
        may_start_infrastructure=False,
        projected_credential=None,
    )


__all__ = [
    "FeatureControlState",
    "build_control_state",
]
