"""Content-free feature control state for default-off degradation."""

from __future__ import annotations

from dataclasses import dataclass

from evidence_handoff_runtime.config import Availability, FeatureConfig


@dataclass(frozen=True)
class FeatureControlState:
    availability: Availability
    active_route: str
    summary_code: str
    may_start_infrastructure: bool
    projected_credential: str | None


def build_control_state(config: FeatureConfig) -> FeatureControlState:
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
