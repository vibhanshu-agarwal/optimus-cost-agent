"""Portable evidence collector package.

Public exports are deliberate and limited to the frozen scenario surface.
"""

from .models import (
    AdapterParameter,
    AdapterSpec,
    BindingKind,
    CapturedArtifact,
    ClaimKind,
    ClassificationResult,
    CollectionBatch,
    EvidenceClaim,
    Observation,
    Outcome,
    RequiredBinding,
    RunContext,
    Scenario,
    scenario_to_canonical_dict,
)
from .scenarios import (
    load_scenario,
    resolve_bindings,
    scenario_sha256,
)

__all__ = [
    "AdapterParameter",
    "AdapterSpec",
    "BindingKind",
    "CapturedArtifact",
    "ClaimKind",
    "ClassificationResult",
    "CollectionBatch",
    "EvidenceClaim",
    "Observation",
    "Outcome",
    "RequiredBinding",
    "RunContext",
    "Scenario",
    "load_scenario",
    "resolve_bindings",
    "scenario_sha256",
    "scenario_to_canonical_dict",
]
