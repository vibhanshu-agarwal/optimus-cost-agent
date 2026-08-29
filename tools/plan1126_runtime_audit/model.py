"""Closed vocabularies and canonical models for the Plan 11.26 audit."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping


class BaselineScope(StrEnum):
    MERGED = "merged"
    OVERLAY = "overlay"
    BOTH_ALIGNED = "both-aligned"
    BOTH_DIVERGENT = "both-divergent"
    BINDING = "binding"


class Classification(StrEnum):
    CANONICAL = "CANONICAL"
    CANONICAL_BYPASSED = "CANONICAL_BYPASSED"
    DUPLICATED = "DUPLICATED"
    CONTRADICTORY = "CONTRADICTORY"
    MISSING = "MISSING"
    INTENTIONALLY_EXCEPTIONAL = "INTENTIONALLY_EXCEPTIONAL"
    PROVISIONAL_OVERLAY = "PROVISIONAL_OVERLAY"
    NOT_PRESENT = "NOT_PRESENT"
    SUPERSEDED = "SUPERSEDED"
    UNCLASSIFIED = "UNCLASSIFIED"


class LiveStatus(StrEnum):
    UNRUN = "UNRUN"
    PARTIAL = "PARTIAL"
    INVALID = "INVALID"
    COMPLETE = "COMPLETE"


class GateStatus(StrEnum):
    PASS = "PASS"
    PASS_WITH_FINDINGS = "PASS_WITH_FINDINGS"
    INCOMPLETE = "INCOMPLETE"


class PrerequisiteStatus(StrEnum):
    """Accepted Task 1 prerequisite states; near-synonyms are not interchangeable."""

    SATISFIED = "SATISFIED"
    SATISFIED_AT_PICKUP = "SATISFIED_AT_PICKUP"
    UNRESOLVED = "UNRESOLVED"
    DEFERRED_TASK_3 = "DEFERRED_TASK_3"
    UNAVAILABLE = "UNAVAILABLE"
    UNAUTHORIZED = "UNAUTHORIZED"
    UNAVAILABLE_AND_UNAUTHORIZED = "UNAVAILABLE_AND_UNAUTHORIZED"
    NOT_YET_IMPLEMENTED = "NOT_YET_IMPLEMENTED"


class InventoryKind(StrEnum):
    TASK_CREATE = "TASK_CREATE"
    CANCELLATION_POINT = "CANCELLATION_POINT"
    QUEUE = "QUEUE"
    RESOURCE_CONSTRUCT = "RESOURCE_CONSTRUCT"
    RESOURCE_TRANSFER = "RESOURCE_TRANSFER"
    RESOURCE_CLOSE = "RESOURCE_CLOSE"
    BROAD_CATCH = "BROAD_CATCH"
    SEMANTIC_WIRE_SELECTION = "SEMANTIC_WIRE_SELECTION"
    REDIS_CLIENT = "REDIS_CLIENT"
    REDIS_POOL = "REDIS_POOL"
    TELEMETRY = "TELEMETRY"
    DEBUG = "DEBUG"
    STDERR = "STDERR"
    REDACTION = "REDACTION"
    SINK = "SINK"
    DELIVERY_START = "DELIVERY_START"
    DELIVERY_PUBLICATION = "DELIVERY_PUBLICATION"
    DELIVERY_SETTLEMENT = "DELIVERY_SETTLEMENT"


def _closed_enum(enum_type: type[StrEnum], value: object, field: str) -> StrEnum:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must use the closed {enum_type.__name__} vocabulary") from exc


def _is_hex(value: object, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(character in "0123456789abcdef" for character in value)


def _nonnegative_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _required_string(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")


def _json_object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a JSON object")
    return value


def _json_array(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a JSON array")
    return value


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    evidence_id: str
    baseline_scope: BaselineScope
    digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "baseline_scope", _closed_enum(BaselineScope, self.baseline_scope, "evidence baseline_scope"))
        _required_string(self.evidence_id, "evidence_id")
        if not _is_hex(self.digest, 64):
            raise ValueError("evidence digest must be lowercase SHA-256")

    def to_dict(self) -> dict[str, str]:
        return {"evidence_id": self.evidence_id, "baseline_scope": self.baseline_scope.value, "digest": self.digest}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> EvidenceReference:
        payload = _json_object(payload, "evidence")
        if set(payload) != {"evidence_id", "baseline_scope", "digest"}:
            raise ValueError("evidence fields do not match the canonical schema")
        return cls(evidence_id=payload["evidence_id"], baseline_scope=payload["baseline_scope"], digest=payload["digest"])


@dataclass(frozen=True, slots=True)
class Finding:
    finding_id: str
    subject: str
    classification: Classification
    baseline_scope: BaselineScope
    symbols: tuple[str, ...]
    evidence: tuple[EvidenceReference, ...]
    owner: str
    ruling: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "classification", _closed_enum(Classification, self.classification, "classification"))
        object.__setattr__(self, "baseline_scope", _closed_enum(BaselineScope, self.baseline_scope, "baseline_scope"))
        for field in ("finding_id", "subject", "owner", "ruling"):
            _required_string(getattr(self, field), field)
        if not self.symbols:
            raise ValueError("symbols are required")
        if any(not isinstance(symbol, str) or not symbol.strip() for symbol in self.symbols):
            raise ValueError("symbols must be non-empty strings")
        object.__setattr__(self, "evidence", tuple(self.evidence))
        if not self.evidence:
            raise ValueError("evidence is required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "subject": self.subject,
            "classification": self.classification.value,
            "baseline_scope": self.baseline_scope.value,
            "symbols": sorted(self.symbols),
            "evidence": [item.to_dict() for item in sorted(self.evidence, key=lambda item: item.evidence_id)],
            "owner": self.owner,
            "ruling": self.ruling,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Finding:
        payload = _json_object(payload, "finding")
        expected = {"finding_id", "subject", "classification", "baseline_scope", "symbols", "evidence", "owner", "ruling"}
        if set(payload) != expected:
            raise ValueError("finding fields do not match the canonical schema")
        symbols = _json_array(payload["symbols"], "finding symbols")
        evidence = _json_array(payload["evidence"], "finding evidence")
        return cls(
            finding_id=payload["finding_id"],
            subject=payload["subject"],
            classification=payload["classification"],
            baseline_scope=payload["baseline_scope"],
            symbols=tuple(symbols),
            evidence=tuple(EvidenceReference.from_dict(item) for item in evidence),
            owner=payload["owner"],
            ruling=payload["ruling"],
        )


@dataclass(frozen=True, slots=True)
class DiscoveredSite:
    path: str
    symbol: str
    line: int
    kind: InventoryKind
    baseline_scope: BaselineScope
    evidence_digest: str
    classification: Classification = Classification.UNCLASSIFIED
    invariant: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _closed_enum(InventoryKind, self.kind, "kind"))
        object.__setattr__(self, "baseline_scope", _closed_enum(BaselineScope, self.baseline_scope, "baseline_scope"))
        object.__setattr__(self, "classification", _closed_enum(Classification, self.classification, "classification"))
        _required_string(self.path, "path")
        _required_string(self.symbol, "symbol")
        _required_string(self.evidence_digest, "evidence_digest")
        if self.invariant is not None:
            _required_string(self.invariant, "invariant")
        if not _nonnegative_integer(self.line) or self.line < 1:
            raise ValueError("line must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "symbol": self.symbol,
            "line": self.line,
            "kind": self.kind.value,
            "baseline_scope": self.baseline_scope.value,
            "evidence_digest": self.evidence_digest,
            "classification": self.classification.value,
            "invariant": self.invariant,
        }


_PROVENANCE_REQUIRED = {
    "binding_commit",
    "executable_path",
    "executable_sha256",
    "package_name",
    "package_version",
    "package_metadata_sha256",
    "build_manifest_sha256",
    "embedded_commit",
    "embedded_commit_sha256",
    "launcher_sha256",
    "client_provenance",
    "environment_fingerprint",
}
_MULTIPLIER_FIELDS = {"cancellation_points", "queues", "sinks", "close_paths"}
_COST_FIELDS = {
    "cancellation_concurrency_levels",
    "cancellation_schedules",
    "cancellation_control_schedules",
    "queue_admissions",
    "sink_failure_runs",
    "idempotent_close_invocations",
    "scenario_p50_ms",
    "scenario_p95_ms",
}


@dataclass(frozen=True, slots=True)
class AuditArtifact:
    schema_version: str
    merged_commit: str
    overlay_commit: str
    binding_commit: str | None
    baseline_reconciliation_status: str
    running_artifact_provenance: Mapping[str, Any] | None
    static_audit_status: LiveStatus
    runtime_characterization_status: LiveStatus
    live_redis_status: LiveStatus
    acpx_status: LiveStatus
    additional_client_status: LiveStatus
    zed_status: LiveStatus
    live_interoperability_status: LiveStatus
    findings: tuple[Finding, ...]
    discovered_multipliers: Mapping[str, int]
    computed_run_cost: Mapping[str, Any]
    gate_status: GateStatus

    def __post_init__(self) -> None:
        if self.schema_version != "plan-11-26-runtime-audit-v1":
            raise ValueError("schema_version is invalid")
        if not _is_hex(self.merged_commit, 40) or not _is_hex(self.overlay_commit, 40):
            raise ValueError("merged_commit and overlay_commit must be lowercase 40-hex commits")
        if self.binding_commit is not None and not _is_hex(self.binding_commit, 40):
            raise ValueError("binding_commit must be null or a lowercase 40-hex commit")
        if not isinstance(self.baseline_reconciliation_status, str) or not self.baseline_reconciliation_status:
            raise ValueError("baseline_reconciliation_status is required")
        for field in (
            "static_audit_status", "runtime_characterization_status", "live_redis_status", "acpx_status",
            "additional_client_status", "zed_status", "live_interoperability_status",
        ):
            object.__setattr__(self, field, _closed_enum(LiveStatus, getattr(self, field), field))
        live_evidence_statuses = (
            self.live_redis_status,
            self.acpx_status,
            self.additional_client_status,
            self.zed_status,
            self.live_interoperability_status,
        )
        if any(status in {LiveStatus.PARTIAL, LiveStatus.COMPLETE} for status in live_evidence_statuses) and (
            self.binding_commit is None or self.running_artifact_provenance is None
        ):
            raise ValueError("live evidence requires binding_commit and running_artifact_provenance")
        object.__setattr__(self, "gate_status", _closed_enum(GateStatus, self.gate_status, "gate_status"))
        object.__setattr__(self, "findings", tuple(self.findings))
        if not isinstance(self.discovered_multipliers, dict) or set(self.discovered_multipliers) != _MULTIPLIER_FIELDS:
            raise ValueError("discovered_multipliers fields do not match the canonical schema")
        if any(not _nonnegative_integer(value) for value in self.discovered_multipliers.values()):
            raise ValueError("discovered_multipliers must be nonnegative integers")
        if not isinstance(self.computed_run_cost, dict) or set(self.computed_run_cost) != _COST_FIELDS:
            raise ValueError("computed_run_cost fields do not match the canonical schema")
        if (
            not isinstance(self.computed_run_cost["cancellation_concurrency_levels"], list)
            or self.computed_run_cost["cancellation_concurrency_levels"] != [2, 4, 8]
        ):
            raise ValueError("cancellation_concurrency_levels must be exactly [2, 4, 8]")
        for field in (
            "cancellation_schedules", "cancellation_control_schedules", "queue_admissions",
            "sink_failure_runs", "idempotent_close_invocations",
        ):
            if not _nonnegative_integer(self.computed_run_cost[field]):
                raise ValueError(f"{field} must be a nonnegative integer")
        for field in ("scenario_p50_ms", "scenario_p95_ms"):
            durations = self.computed_run_cost[field]
            if not isinstance(durations, dict) or any(
                not isinstance(name, str) or not name or not isinstance(value, (int, float))
                or isinstance(value, bool) or value < 0 or not math.isfinite(value)
                for name, value in durations.items()
            ):
                raise ValueError(f"{field} must contain nonnegative finite durations")
        if self.running_artifact_provenance is not None and (
            not isinstance(self.running_artifact_provenance, dict)
            or set(self.running_artifact_provenance) != _PROVENANCE_REQUIRED
        ):
            raise ValueError("running_artifact_provenance must be external and complete; workspace git_sha is insufficient")
        if self.running_artifact_provenance is not None:
            provenance = self.running_artifact_provenance
            for field in ("executable_path", "package_name", "package_version"):
                if not isinstance(provenance[field], str) or not provenance[field]:
                    raise ValueError(f"running_artifact_provenance {field} is invalid")
            for field in (
                "executable_sha256", "package_metadata_sha256", "build_manifest_sha256",
                "embedded_commit_sha256", "launcher_sha256", "environment_fingerprint",
            ):
                if not _is_hex(provenance[field], 64):
                    raise ValueError(f"running_artifact_provenance {field} is invalid")
            if not _is_hex(provenance["binding_commit"], 40) or not _is_hex(provenance["embedded_commit"], 40):
                raise ValueError("running_artifact_provenance commit identity is invalid")
            if provenance["binding_commit"] != self.binding_commit or provenance["embedded_commit"] != self.binding_commit:
                raise ValueError("running_artifact_provenance does not match binding_commit")
            client = provenance["client_provenance"]
            if not isinstance(client, dict) or set(client) != {"name", "version", "path", "sha256", "metadata_sha256"}:
                raise ValueError("running_artifact_provenance client_provenance is invalid")
            if any(not isinstance(client[field], str) or not client[field] for field in ("name", "version", "path")):
                raise ValueError("running_artifact_provenance client identity is invalid")
            if not _is_hex(client["sha256"], 64) or not _is_hex(client["metadata_sha256"], 64):
                raise ValueError("running_artifact_provenance client digests are invalid")
        for finding in self.findings:
            if finding.baseline_scope is BaselineScope.BINDING and self.binding_commit is None:
                raise ValueError("binding_commit is required for a binding-scoped finding")
            if finding.baseline_scope is BaselineScope.BINDING and any(
                evidence.baseline_scope is not BaselineScope.BINDING for evidence in finding.evidence
            ):
                raise ValueError("binding evidence lineage must contain only binding-scoped evidence")
            if self.binding_commit is not None and finding.baseline_scope in {BaselineScope.OVERLAY, BaselineScope.BOTH_DIVERGENT} and finding.classification not in {Classification.PROVISIONAL_OVERLAY, Classification.NOT_PRESENT, Classification.SUPERSEDED}:
                raise ValueError("binding finding cannot be justified by overlay-only evidence")
        if self.gate_status is not GateStatus.INCOMPLETE and self.unclassified_finding_count:
            raise ValueError("UNCLASSIFIED findings must be zero at a passing gate")

    @property
    def finding_counts_by_classification(self) -> dict[str, int]:
        counts = Counter(finding.classification.value for finding in self.findings)
        return {classification.value: counts[classification.value] for classification in Classification}

    @property
    def unclassified_finding_count(self) -> int:
        return self.finding_counts_by_classification[Classification.UNCLASSIFIED.value]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "merged_commit": self.merged_commit,
            "overlay_commit": self.overlay_commit,
            "binding_commit": self.binding_commit,
            "baseline_reconciliation_status": self.baseline_reconciliation_status,
            "running_artifact_provenance": None if self.running_artifact_provenance is None else _canonical(self.running_artifact_provenance),
            "static_audit_status": self.static_audit_status.value,
            "runtime_characterization_status": self.runtime_characterization_status.value,
            "live_redis_status": self.live_redis_status.value,
            "acpx_status": self.acpx_status.value,
            "additional_client_status": self.additional_client_status.value,
            "zed_status": self.zed_status.value,
            "live_interoperability_status": self.live_interoperability_status.value,
            "unclassified_finding_count": self.unclassified_finding_count,
            "finding_counts_by_classification": self.finding_counts_by_classification,
            "findings": [finding.to_dict() for finding in sorted(self.findings, key=lambda item: item.finding_id)],
            "discovered_multipliers": _canonical(self.discovered_multipliers),
            "computed_run_cost": _canonical(self.computed_run_cost),
            "gate_status": self.gate_status.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AuditArtifact:
        payload = _json_object(payload, "artifact")
        expected = {
            "schema_version", "merged_commit", "overlay_commit", "binding_commit", "baseline_reconciliation_status",
            "running_artifact_provenance", "static_audit_status", "runtime_characterization_status", "live_redis_status",
            "acpx_status", "additional_client_status", "zed_status", "live_interoperability_status",
            "unclassified_finding_count", "finding_counts_by_classification", "findings", "discovered_multipliers",
            "computed_run_cost", "gate_status",
        }
        if set(payload) != expected:
            raise ValueError("artifact fields do not match the canonical schema")
        counts = payload["finding_counts_by_classification"]
        if (
            not _nonnegative_integer(payload["unclassified_finding_count"])
            or not isinstance(counts, dict)
            or set(counts) != {classification.value for classification in Classification}
            or any(not _nonnegative_integer(value) for value in counts.values())
        ):
            raise ValueError("finding counts must be closed nonnegative integer records")
        findings = _json_array(payload["findings"], "findings")
        _json_object(payload["discovered_multipliers"], "discovered_multipliers")
        _json_object(payload["computed_run_cost"], "computed_run_cost")
        if payload["running_artifact_provenance"] is not None:
            _json_object(payload["running_artifact_provenance"], "running_artifact_provenance")
        artifact = cls(
            schema_version=payload["schema_version"], merged_commit=payload["merged_commit"], overlay_commit=payload["overlay_commit"],
            binding_commit=payload["binding_commit"], baseline_reconciliation_status=payload["baseline_reconciliation_status"],
            running_artifact_provenance=payload["running_artifact_provenance"], static_audit_status=payload["static_audit_status"],
            runtime_characterization_status=payload["runtime_characterization_status"], live_redis_status=payload["live_redis_status"],
            acpx_status=payload["acpx_status"], additional_client_status=payload["additional_client_status"], zed_status=payload["zed_status"],
            live_interoperability_status=payload["live_interoperability_status"], findings=tuple(Finding.from_dict(item) for item in findings),
            discovered_multipliers=payload["discovered_multipliers"], computed_run_cost=payload["computed_run_cost"], gate_status=payload["gate_status"],
        )
        if payload["unclassified_finding_count"] != artifact.unclassified_finding_count:
            raise ValueError("unclassified_finding_count mismatch")
        if payload["finding_counts_by_classification"] != artifact.finding_counts_by_classification:
            raise ValueError("finding_counts_by_classification mismatch")
        return artifact
