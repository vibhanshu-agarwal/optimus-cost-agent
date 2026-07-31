"""Typed model validation for evidence_handoff.redaction.models.

Named test_redaction_models.py because tests/unit/evidence/test_models.py already
owns optimus.evidence.models coverage. Flagged for reviewer confirmation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest


def _models():
    from evidence_handoff.redaction import models

    return models


def _inventory():
    from optimus_security.sensitive_values import SensitiveValueInventory

    return SensitiveValueInventory


def _abs(tmp_path: Path, *parts: str) -> Path:
    path = tmp_path.joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _runtime(tmp_path: Path):
    models = _models()
    SensitiveValueInventory = _inventory()
    capture = _abs(tmp_path, "capture")
    staging = _abs(tmp_path, "staging")
    quarantine = _abs(tmp_path, "quarantine")
    forbidden = _abs(tmp_path, "forbidden")
    return models.RedactionRuntimeInputs(
        sensitive_values=SensitiveValueInventory(),
        path_aliases=(models.PathAliasRule(source_root=str(capture), alias="<temp>"),),
        temporary_capture_root=capture,
        staging_root=staging,
        quarantine_root=quarantine,
        forbidden_persistence_roots=(forbidden,),
    )


def _valid_request(tmp_path: Path, *, role: str = "acp_debug_trace"):
    models = _models()
    runtime = _runtime(tmp_path)
    destination = _abs(tmp_path, "destination")
    source = runtime.temporary_capture_root / "artifact.ndjson"
    source.write_text("{}\n", encoding="utf-8")
    return models.RedactionRequest(
        source_path=source.resolve(),
        destination_root=destination,
        artifact_kind=models.ArtifactKind.NDJSON,
        artifact_role=role,
        runtime=runtime,
    )


def test_enums_match_frozen_contract() -> None:
    models = _models()
    assert set(models.ArtifactKind) == {
        models.ArtifactKind.JSON,
        models.ArtifactKind.NDJSON,
        models.ArtifactKind.ACP_DEBUG_TRACE,
        models.ArtifactKind.TEXT,
        models.ArtifactKind.SCREENSHOT,
        models.ArtifactKind.PROCESS_DUMP,
    }
    assert set(models.Disposition) == {
        models.Disposition.PROMOTED,
        models.Disposition.AWAITING_HUMAN_APPROVAL,
        models.Disposition.QUARANTINED,
        models.Disposition.REJECTED,
    }


def test_path_alias_rule_reexported_from_sanitizer() -> None:
    models = _models()
    from optimus_security.sanitization import PathAliasRule as SanitizerPathAliasRule

    assert models.PathAliasRule is SanitizerPathAliasRule


def test_rejects_relative_source_path(tmp_path: Path) -> None:
    models = _models()
    runtime = _runtime(tmp_path)
    with pytest.raises(ValueError, match="relative_path_rejected"):
        models.RedactionRequest(
            source_path=Path("relative/source.txt"),
            destination_root=_abs(tmp_path, "destination"),
            artifact_kind=models.ArtifactKind.TEXT,
            artifact_role="session_note",
            runtime=runtime,
        )


def test_rejects_relative_destination_root(tmp_path: Path) -> None:
    models = _models()
    runtime = _runtime(tmp_path)
    source = runtime.temporary_capture_root / "note.txt"
    source.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="relative_path_rejected"):
        models.RedactionRequest(
            source_path=source.resolve(),
            destination_root=Path("relative/dest"),
            artifact_kind=models.ArtifactKind.TEXT,
            artifact_role="session_note",
            runtime=runtime,
        )


def test_rejects_relative_runtime_roots(tmp_path: Path) -> None:
    models = _models()
    SensitiveValueInventory = _inventory()
    with pytest.raises(ValueError, match="relative_path_rejected"):
        models.RedactionRuntimeInputs(
            sensitive_values=SensitiveValueInventory(),
            path_aliases=(),
            temporary_capture_root=Path("capture"),
            staging_root=_abs(tmp_path, "staging"),
            quarantine_root=_abs(tmp_path, "quarantine"),
            forbidden_persistence_roots=(),
        )


def test_rejects_source_outside_capture_and_quarantine(tmp_path: Path) -> None:
    models = _models()
    runtime = _runtime(tmp_path)
    outside = _abs(tmp_path, "outside") / "leak.txt"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="source_not_under_approved_root"):
        models.RedactionRequest(
            source_path=outside.resolve(),
            destination_root=_abs(tmp_path, "destination"),
            artifact_kind=models.ArtifactKind.TEXT,
            artifact_role="session_note",
            runtime=runtime,
        )


def test_rejects_source_under_destination(tmp_path: Path) -> None:
    models = _models()
    SensitiveValueInventory = _inventory()
    destination = _abs(tmp_path, "destination")
    nested_capture = destination / "capture"
    nested_capture.mkdir(parents=True, exist_ok=True)
    source = nested_capture / "artifact.txt"
    source.write_text("x", encoding="utf-8")
    bad_runtime = models.RedactionRuntimeInputs(
        sensitive_values=SensitiveValueInventory(),
        path_aliases=(),
        temporary_capture_root=nested_capture.resolve(),
        staging_root=_abs(tmp_path, "staging"),
        quarantine_root=_abs(tmp_path, "quarantine"),
        forbidden_persistence_roots=(),
    )
    with pytest.raises(ValueError, match="source_under_destination"):
        models.RedactionRequest(
            source_path=source.resolve(),
            destination_root=destination,
            artifact_kind=models.ArtifactKind.TEXT,
            artifact_role="session_note",
            runtime=bad_runtime,
        )


def test_rejects_staging_under_destination(tmp_path: Path) -> None:
    models = _models()
    SensitiveValueInventory = _inventory()
    destination = _abs(tmp_path, "destination")
    staging = destination / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    capture = _abs(tmp_path, "capture")
    quarantine = _abs(tmp_path, "quarantine")
    source = capture / "a.txt"
    source.write_text("x", encoding="utf-8")
    runtime = models.RedactionRuntimeInputs(
        sensitive_values=SensitiveValueInventory(),
        path_aliases=(),
        temporary_capture_root=capture,
        staging_root=staging.resolve(),
        quarantine_root=quarantine,
        forbidden_persistence_roots=(),
    )
    with pytest.raises(ValueError, match="staging_under_destination"):
        models.RedactionRequest(
            source_path=source.resolve(),
            destination_root=destination,
            artifact_kind=models.ArtifactKind.TEXT,
            artifact_role="session_note",
            runtime=runtime,
        )


def test_rejects_quarantine_under_destination(tmp_path: Path) -> None:
    models = _models()
    SensitiveValueInventory = _inventory()
    destination = _abs(tmp_path, "destination")
    quarantine = destination / "quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)
    capture = _abs(tmp_path, "capture")
    staging = _abs(tmp_path, "staging")
    source = capture / "a.txt"
    source.write_text("x", encoding="utf-8")
    runtime = models.RedactionRuntimeInputs(
        sensitive_values=SensitiveValueInventory(),
        path_aliases=(),
        temporary_capture_root=capture,
        staging_root=staging,
        quarantine_root=quarantine.resolve(),
        forbidden_persistence_roots=(),
    )
    with pytest.raises(ValueError, match="quarantine_under_destination"):
        models.RedactionRequest(
            source_path=source.resolve(),
            destination_root=destination,
            artifact_kind=models.ArtifactKind.TEXT,
            artifact_role="session_note",
            runtime=runtime,
        )


def test_rejects_paths_under_forbidden_persistence_root(tmp_path: Path) -> None:
    models = _models()
    SensitiveValueInventory = _inventory()
    forbidden = _abs(tmp_path, "cloud-sync")
    capture = forbidden / "capture"
    capture.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError, match="path_under_forbidden_root"):
        models.RedactionRuntimeInputs(
            sensitive_values=SensitiveValueInventory(),
            path_aliases=(),
            temporary_capture_root=capture.resolve(),
            staging_root=_abs(tmp_path, "staging"),
            quarantine_root=_abs(tmp_path, "quarantine"),
            forbidden_persistence_roots=(forbidden,),
        )


def test_rejects_unsafe_artifact_roles(tmp_path: Path) -> None:
    unsafe_roles = (
        "",
        "../etc/passwd",
        "C:/Windows",
        "plan-" + "11-7-trace",
        "EVIDENCE-HANDOFF-" + "FEAT" + "-X",
    )
    for role in unsafe_roles:
        with pytest.raises(ValueError, match="unsafe_artifact_role"):
            _valid_request(tmp_path, role=role)


def test_allows_version_suffix_artifact_role(tmp_path: Path) -> None:
    request = _valid_request(tmp_path, role="screenshot_v1")
    assert request.artifact_role == "screenshot_v1"


def test_rejects_invalid_staged_sha256() -> None:
    models = _models()
    with pytest.raises(ValueError, match="invalid_approval_digest"):
        models.ScreenshotApproval(
            staged_sha256="abc",
            approver_id="approver-a",
            collector_id="collector-b",
            approved_at=datetime.now(tz=UTC),
            rationale="looks clean",
        )


def test_rejects_timezone_naive_approval_timestamp() -> None:
    models = _models()
    digest = "a" * 64
    with pytest.raises(ValueError, match="approval_timestamp_not_timezone_aware"):
        models.ScreenshotApproval(
            staged_sha256=digest,
            approver_id="approver-a",
            collector_id="collector-b",
            approved_at=datetime(2020, 1, 1, 12, 0, 0),  # intentional naive timestamp
            rationale="looks clean",
        )


def test_rejects_approver_equal_to_collector() -> None:
    models = _models()
    digest = "b" * 64
    with pytest.raises(ValueError, match="approver_equals_collector"):
        models.ScreenshotApproval(
            staged_sha256=digest,
            approver_id="same-actor",
            collector_id="same-actor",
            approved_at=datetime.now(tz=UTC),
            rationale="looks clean",
        )


def test_valid_minimal_request_passes(tmp_path: Path) -> None:
    models = _models()
    request = _valid_request(tmp_path)
    assert request.artifact_kind is models.ArtifactKind.NDJSON
    assert request.source_path.is_absolute()


def test_redaction_gate_result_frozen_shape() -> None:
    models = _models()
    result = models.RedactionGateResult(
        disposition=models.Disposition.REJECTED,
        artifact_locator=None,
        manifest_locator=None,
        reason_code="relative_path_rejected",
    )
    assert result.disposition is models.Disposition.REJECTED
    assert result.reason_code == "relative_path_rejected"
