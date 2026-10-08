"""Optimus model policy: the curated registry, structural role validation and request capacity.

A neutral package shared by the host and the Gateway (Plan 12.2 Task 4). It imports nothing from
``optimus``, ``optimus_gateway`` or ``optimus_security``.
"""

from optimus_model_policy.capacity import (
    CapacityDecision,
    InputEstimate,
    Message,
    PackedModelRequest,
    estimate_complete_input,
    guard_request,
)
from optimus_model_policy.registry import (
    DORMANT_ROLES,
    IMPLEMENTER_ROLES,
    MAX_CONTEXT_CEILING_TOKENS,
    SUMMARY_FORMAT,
    EstimatorProfile,
    ModelEntry,
    Origin,
    Policy,
    RegistryError,
    RegistrySnapshot,
    Role,
    Tier,
    load_registry,
)
from optimus_model_policy.validation import (
    ValidationIssue,
    ordered_assignments,
    select_eligible_models,
    validate_registry,
)

__all__ = [
    "DORMANT_ROLES",
    "IMPLEMENTER_ROLES",
    "MAX_CONTEXT_CEILING_TOKENS",
    "SUMMARY_FORMAT",
    "CapacityDecision",
    "EstimatorProfile",
    "InputEstimate",
    "Message",
    "ModelEntry",
    "Origin",
    "PackedModelRequest",
    "Policy",
    "RegistryError",
    "RegistrySnapshot",
    "Role",
    "Tier",
    "ValidationIssue",
    "estimate_complete_input",
    "guard_request",
    "load_registry",
    "ordered_assignments",
    "select_eligible_models",
    "validate_registry",
]
