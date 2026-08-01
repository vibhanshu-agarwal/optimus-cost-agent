"""Portable evidence collector contracts.

Stdlib-only. No optimus, optimus_gateway, optimus_security, or tools imports.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class BindingKind(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ABSOLUTE_PATH = "absolute_path"


class Outcome(StrEnum):
    RENDERED_STABLE = "rendered_stable"
    RENDERED_THEN_CRASHED = "rendered_then_crashed"
    CLIENT_CRASHED = "client_crashed"
    INDETERMINATE = "indeterminate"


class ClaimKind(StrEnum):
    COMPLETION_OBSERVED = "completion_observed"
    RENDER_OBSERVED = "render_observed"
    CLIENT_ALIVE = "client_alive"
    OBSERVATION_WINDOW_COMPLETE = "observation_window_complete"
    CLIENT_CRASH_OBSERVED = "client_crash_observed"
    INTEGRITY_VALID = "integrity_valid"


@dataclass(frozen=True, slots=True)
class RequiredBinding:
    name: str
    kind: BindingKind
    required: bool
    min_length: int | None = None
    max_length: int | None = None


@dataclass(frozen=True, slots=True)
class AdapterParameter:
    name: str
    kind: BindingKind
    value: str | int | bool


@dataclass(frozen=True, slots=True)
class AdapterSpec:
    adapter_id: str
    contract_version: str
    parameters: tuple[AdapterParameter, ...]


@dataclass(frozen=True, slots=True)
class Scenario:
    schema: str
    scenario_id: str
    required_bindings: tuple[RequiredBinding, ...]
    client: AdapterSpec
    fixture: AdapterSpec
    preconditions: tuple[AdapterSpec, ...]
    collection: tuple[AdapterSpec, ...]
    detection: tuple[AdapterSpec, ...]
    required_evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RunContext:
    schema: str
    scenario_id: str
    run_id: str
    scenario_sha256: str
    capture_root: Path
    monotonic_origin_ns: int


@dataclass(frozen=True, slots=True)
class CapturedArtifact:
    role: str
    media_type: str
    relative_locator: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class Observation:
    schema: str
    scenario_id: str
    run_id: str
    collector_id: str
    sequence: int
    monotonic_offset_ns: int
    observed_at: str
    observation_kind: str
    correlation: tuple[tuple[str, str], ...]
    artifact_role: str | None
    artifact_sha256: str | None
    reason_code: str | None


@dataclass(frozen=True, slots=True)
class CollectionBatch:
    collector_id: str
    contract_version: str
    observations: tuple[Observation, ...]
    artifacts: tuple[CapturedArtifact, ...]


@dataclass(frozen=True, slots=True)
class EvidenceClaim:
    claim_kind: ClaimKind
    scenario_id: str
    run_id: str
    detector_id: str
    contract_version: str
    evidence_sha256: tuple[str, ...]
    starts_at_ns: int
    ends_at_ns: int
    reason_code: str


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    schema: str
    scenario_id: str
    run_id: str
    outcome: Outcome
    claims: tuple[EvidenceClaim, ...]
    reason_codes: tuple[str, ...]
    raw_bundle_sha256: str


def _canonicalize(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_canonicalize(item) for item in value]
    if isinstance(value, dict):
        return {key: _canonicalize(item) for key, item in value.items()}
    return value


def scenario_to_canonical_dict(scenario: Scenario) -> dict[str, Any]:
    """Serialize a scenario with enum values and tuples as JSON arrays."""
    return _canonicalize(asdict(scenario))


def adapter_parameter_to_canonical_dict(parameter: AdapterParameter) -> dict[str, Any]:
    return _canonicalize(asdict(parameter))
