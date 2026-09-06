"""Stable public facade for the H4 delivery-settlement characterization."""

from .delivery_characterization import (
    H4_SOURCE_PATHS,
    build_h4_audit_artifact,
    delivery_schedule_observations,
    derive_delivery_vocabulary,
    derive_transition_authority,
)
from .delivery_characterization import (
    DeliveryObservation as DeliveryScheduleObservation,
)

__all__ = (
    "H4_SOURCE_PATHS",
    "DeliveryScheduleObservation",
    "build_h4_audit_artifact",
    "delivery_schedule_observations",
    "derive_delivery_vocabulary",
    "derive_transition_authority",
)
