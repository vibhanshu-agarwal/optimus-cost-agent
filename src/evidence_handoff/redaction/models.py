"""Portable redaction request/result contracts.

Re-exports PathAliasRule from optimus_security without defining a competing type.
SensitiveValueInventory is imported from optimus_security; Task 2 provides a minimal
stub type so models can load before Task 3 expands inventory behavior.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from optimus_security.sanitization import PathAliasRule
from optimus_security.sensitive_values import SensitiveValueInventory

_ARTIFACT_ROLE_RE = re.compile(r"^[a-z][a-z0-9_]*(?:_v[0-9]+)?$")
_FEATURE_ID_RE = re.compile(r"(?<![A-Z0-9-])(?:[A-Z][A-Z0-9]*-)*FEAT-[A-Z0-9]+(?:-[A-Z0-9]+)*(?![A-Z0-9-])")
_PLAN_NUMBER_RE = re.compile(r"\bPlan [0-9]|\bplan-[0-9]", re.IGNORECASE)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ArtifactKind(StrEnum):
    JSON = "json"
    NDJSON = "ndjson"
    ACP_DEBUG_TRACE = "acp_debug_trace"
    TEXT = "text"
    SCREENSHOT = "screenshot"
    PROCESS_DUMP = "process_dump"


class Disposition(StrEnum):
    PROMOTED = "promoted"
    AWAITING_HUMAN_APPROVAL = "awaiting_human_approval"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"


def _require_absolute(path: Path, *, code: str = "relative_path_rejected") -> Path:
    if not path.is_absolute():
        raise ValueError(code)
    return path


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _validate_artifact_role(role: str) -> None:
    if not role or not _ARTIFACT_ROLE_RE.fullmatch(role):
        raise ValueError("unsafe_artifact_role")
    if _FEATURE_ID_RE.search(role) or _PLAN_NUMBER_RE.search(role):
        raise ValueError("unsafe_artifact_role")
    if "/" in role or "\\" in role or ".." in role:
        raise ValueError("unsafe_artifact_role")


@dataclass(frozen=True)
class RedactionRuntimeInputs:
    sensitive_values: SensitiveValueInventory
    path_aliases: tuple[PathAliasRule, ...]
    temporary_capture_root: Path
    staging_root: Path
    quarantine_root: Path
    forbidden_persistence_roots: tuple[Path, ...]

    def __post_init__(self) -> None:
        capture = _require_absolute(self.temporary_capture_root)
        staging = _require_absolute(self.staging_root)
        quarantine = _require_absolute(self.quarantine_root)
        forbidden = tuple(_require_absolute(path) for path in self.forbidden_persistence_roots)
        for root in (capture, staging, quarantine):
            for forbidden_root in forbidden:
                if _is_under(root, forbidden_root):
                    raise ValueError("path_under_forbidden_root")


@dataclass(frozen=True)
class ScreenshotApproval:
    staged_sha256: str
    approver_id: str
    collector_id: str
    approved_at: datetime
    rationale: str

    def __post_init__(self) -> None:
        if not _SHA256_RE.fullmatch(self.staged_sha256):
            raise ValueError("invalid_approval_digest")
        if not self.approver_id.strip():
            raise ValueError("invalid_approver_id")
        if not self.collector_id.strip():
            raise ValueError("invalid_collector_id")
        if self.approver_id == self.collector_id:
            raise ValueError("approver_equals_collector")
        if self.approved_at.tzinfo is None:
            raise ValueError("approval_timestamp_not_timezone_aware")
        if not self.rationale.strip():
            raise ValueError("empty_approval_rationale")


@dataclass(frozen=True)
class RedactionRequest:
    source_path: Path
    destination_root: Path
    artifact_kind: ArtifactKind
    artifact_role: str
    runtime: RedactionRuntimeInputs
    screenshot_approval: ScreenshotApproval | None = None

    def __post_init__(self) -> None:
        source = _require_absolute(self.source_path)
        destination = _require_absolute(self.destination_root)
        _validate_artifact_role(self.artifact_role)

        capture = self.runtime.temporary_capture_root
        quarantine = self.runtime.quarantine_root
        staging = self.runtime.staging_root

        if not (_is_under(source, capture) or _is_under(source, quarantine)):
            raise ValueError("source_not_under_approved_root")
        if _is_under(source, destination):
            raise ValueError("source_under_destination")
        if _is_under(staging, destination):
            raise ValueError("staging_under_destination")
        if _is_under(quarantine, destination):
            raise ValueError("quarantine_under_destination")

        for forbidden_root in self.runtime.forbidden_persistence_roots:
            for path in (source, destination, staging, quarantine, capture):
                if _is_under(path, forbidden_root):
                    raise ValueError("path_under_forbidden_root")

        if self.screenshot_approval is not None and self.artifact_kind is not ArtifactKind.SCREENSHOT:
            raise ValueError("approval_not_allowed_for_artifact_kind")


@dataclass(frozen=True)
class RedactionGateResult:
    disposition: Disposition
    artifact_locator: str | None
    manifest_locator: str | None
    reason_code: str | None


__all__ = [
    "ArtifactKind",
    "Disposition",
    "PathAliasRule",
    "RedactionGateResult",
    "RedactionRequest",
    "RedactionRuntimeInputs",
    "ScreenshotApproval",
    "SensitiveValueInventory",
]
