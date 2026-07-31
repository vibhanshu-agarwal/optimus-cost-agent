"""RED/GREEN unit tests for redaction gate state machine."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from evidence_handoff.redaction.models import (
    ArtifactKind,
    Disposition,
    RedactionRequest,
    RedactionRuntimeInputs,
    ScreenshotApproval,
)
from optimus_security.sanitization import PathAliasRule
from optimus_security.sensitive_values import SensitiveValueInventory, SensitiveValueSourceClass


def _gate():
    from evidence_handoff.redaction import gate as gate_mod

    return gate_mod


def _runtime(tmp_path: Path) -> tuple[RedactionRuntimeInputs, Path]:
    capture = (tmp_path / "cap").resolve()
    staging = (tmp_path / "staging").resolve()
    quarantine = (tmp_path / "quarantine").resolve()
    dest = (tmp_path / "dest").resolve()
    for path in (capture, staging, quarantine, dest):
        path.mkdir(parents=True, exist_ok=True)
    inventory = SensitiveValueInventory()
    inventory.add_secret(
        "Q7mV2xN9pR4tY8kL3cD6wF1hJ5sB0zUa",
        source_class=SensitiveValueSourceClass.ENVIRONMENT,
    )
    return RedactionRuntimeInputs(
        sensitive_values=inventory,
        path_aliases=(
            PathAliasRule(source_root=str(dest), alias="<destination>"),
            PathAliasRule(source_root=str(staging), alias="<staging>"),
            PathAliasRule(source_root=str(quarantine), alias="<quarantine>"),
            PathAliasRule(source_root=str(capture), alias="<temp>"),
        ),
        temporary_capture_root=capture,
        staging_root=staging,
        quarantine_root=quarantine,
        forbidden_persistence_roots=(),
    ), dest


def test_reject_invalid_request_before_open(tmp_path: Path) -> None:
    gate = _gate()
    runtime, dest = _runtime(tmp_path)
    with pytest.raises(ValueError, match="relative_path_rejected"):
        RedactionRequest(
            source_path=Path("relative.txt"),
            destination_root=dest,
            artifact_kind=ArtifactKind.TEXT,
            artifact_role="session_note",
            runtime=runtime,
        )
    # Gate wrapper should map construction failures to REJECTED when given bad paths via run.
    result = gate.run_redaction_gate(
        source_path=runtime.temporary_capture_root / "missing.txt",
        destination_root=dest,
        artifact_kind=ArtifactKind.TEXT,
        artifact_role="session_note",
        runtime=runtime,
    )
    assert result.disposition is Disposition.REJECTED
    assert result.reason_code == "source_missing"
    assert result.manifest_locator is None
    assert result.artifact_locator is None


def test_promoted_text_writes_bundle_atomically(tmp_path: Path) -> None:
    gate = _gate()
    runtime, dest = _runtime(tmp_path)
    source = runtime.temporary_capture_root / "note.txt"
    source.write_text("hello safe text\n", encoding="utf-8")
    result = gate.run_redaction_gate(
        source_path=source,
        destination_root=dest,
        artifact_kind=ArtifactKind.TEXT,
        artifact_role="session_note",
        runtime=runtime,
    )
    assert result.disposition is Disposition.PROMOTED
    assert result.artifact_locator is not None
    assert result.manifest_locator is not None
    assert "<destination>" in result.artifact_locator
    # Destination exposes both files after rename.
    bundles = [p for p in dest.iterdir() if p.is_dir()]
    assert len(bundles) == 1
    assert (bundles[0] / "artifact").exists()
    assert (bundles[0] / "manifest.json").exists()
    manifest = json.loads((bundles[0] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["disposition"] == "promoted"
    assert manifest["final_scan_passed"] is True
    assert str(source.resolve()) not in (bundles[0] / "manifest.json").read_text(encoding="utf-8")


def test_type_mismatch_no_text_fallback(tmp_path: Path) -> None:
    gate = _gate()
    runtime, dest = _runtime(tmp_path)
    source = runtime.temporary_capture_root / "not-text.bin"
    source.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    result = gate.run_redaction_gate(
        source_path=source,
        destination_root=dest,
        artifact_kind=ArtifactKind.TEXT,
        artifact_role="session_note",
        runtime=runtime,
    )
    assert result.disposition is Disposition.QUARANTINED
    assert result.reason_code == "artifact_kind_mismatch"
    assert list(dest.iterdir()) == []


def test_screenshot_awaits_approval_without_promoting(tmp_path: Path) -> None:
    gate = _gate()
    runtime, dest = _runtime(tmp_path)
    source = runtime.temporary_capture_root / "shot.png"
    Image.new("RGB", (6, 6), color=(1, 2, 3)).save(source)
    result = gate.run_redaction_gate(
        source_path=source,
        destination_root=dest,
        artifact_kind=ArtifactKind.SCREENSHOT,
        artifact_role="screenshot_v1",
        runtime=runtime,
    )
    assert result.disposition is Disposition.AWAITING_HUMAN_APPROVAL
    assert list(dest.iterdir()) == []
    assert result.artifact_locator is not None
    assert "<staging>" in (result.artifact_locator or "")


def test_screenshot_with_matching_approval_promotes(tmp_path: Path) -> None:
    gate = _gate()
    runtime, dest = _runtime(tmp_path)
    source = runtime.temporary_capture_root / "shot.png"
    Image.new("RGB", (6, 6), color=(4, 5, 6)).save(source)
    pending = gate.run_redaction_gate(
        source_path=source,
        destination_root=dest,
        artifact_kind=ArtifactKind.SCREENSHOT,
        artifact_role="screenshot_v1",
        runtime=runtime,
    )
    assert pending.disposition is Disposition.AWAITING_HUMAN_APPROVAL
    # Recover staged digest from staging tree.
    staged = next(runtime.staging_root.rglob("*.partial"))
    digest = __import__("hashlib").sha256(staged.read_bytes()).hexdigest()
    # Move staged path aside is already there; promote with approval via second call helper.
    approval = ScreenshotApproval(
        staged_sha256=digest,
        approver_id="operator-a",
        collector_id="collector-b",
        approved_at=datetime(2026, 7, 31, 12, 0, tzinfo=UTC),
        rationale="clear",
    )
    # Source already quarantined; approve from staged file still under staging.
    result = gate.promote_approved_screenshot(
        staging_path=staged,
        destination_root=dest,
        artifact_role="screenshot_v1",
        runtime=runtime,
        approval=approval,
    )
    assert result.disposition is Disposition.PROMOTED
    assert any(dest.iterdir())


def test_dump_quarantines_without_destination_artifact(tmp_path: Path) -> None:
    gate = _gate()
    runtime, dest = _runtime(tmp_path)
    source = runtime.temporary_capture_root / "crash.dmp"
    source.write_bytes(b"MDMP" + b"\x00" * 64)
    result = gate.run_redaction_gate(
        source_path=source,
        destination_root=dest,
        artifact_kind=ArtifactKind.PROCESS_DUMP,
        artifact_role="process_dump",
        runtime=runtime,
    )
    assert result.disposition is Disposition.QUARANTINED
    assert list(dest.iterdir()) == []
    assert result.manifest_locator is None or "<destination>" not in (result.manifest_locator or "")


def test_atomic_rename_failure_leaves_destination_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = _gate()
    runtime, dest = _runtime(tmp_path)
    source = runtime.temporary_capture_root / "note.txt"
    source.write_text("ok\n", encoding="utf-8")

    def _boom(*_args: object, **_kwargs: object) -> None:
        from evidence_handoff.redaction.private_files import PrivateFileError

        raise PrivateFileError("atomic_replace_failed")

    monkeypatch.setattr(gate, "_promote_bundle", _boom)
    result = gate.run_redaction_gate(
        source_path=source,
        destination_root=dest,
        artifact_kind=ArtifactKind.TEXT,
        artifact_role="session_note",
        runtime=runtime,
    )
    assert result.disposition is Disposition.QUARANTINED
    assert result.reason_code == "atomic_replace_failed"
    assert list(dest.iterdir()) == []


def test_manifest_write_failure_does_not_claim_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = _gate()
    runtime, dest = _runtime(tmp_path)
    source = runtime.temporary_capture_root / "note.txt"
    source.write_text("ok\n", encoding="utf-8")

    def _fail_scan(*_args: object, **_kwargs: object) -> bool:
        return False

    monkeypatch.setattr(gate, "manifest_canary_scan", _fail_scan)
    result = gate.run_redaction_gate(
        source_path=source,
        destination_root=dest,
        artifact_kind=ArtifactKind.TEXT,
        artifact_role="session_note",
        runtime=runtime,
    )
    assert result.disposition is Disposition.QUARANTINED
    assert result.reason_code == "manifest_canary_failed"
    assert list(dest.iterdir()) == []


def test_quarantine_unavailable_stops_without_extra_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = _gate()
    runtime, dest = _runtime(tmp_path)
    source = runtime.temporary_capture_root / "shot.png"
    Image.new("RGB", (4, 4), color=(0, 0, 0)).save(source)

    def _q_fail(*_args: object, **_kwargs: object):
        from evidence_handoff.redaction.images import ImageSanitizeResult

        return ImageSanitizeResult(
            disposition=Disposition.QUARANTINED,
            staging_path=None,
            quarantine_path=None,
            staged_sha256=None,
            reason_code="raw_source_quarantine_failed",
            byte_size=None,
        )

    monkeypatch.setattr(
        "evidence_handoff.redaction.images.sanitize_screenshot_artifact",
        _q_fail,
    )
    result = gate.run_redaction_gate(
        source_path=source,
        destination_root=dest,
        artifact_kind=ArtifactKind.SCREENSHOT,
        artifact_role="screenshot_v1",
        runtime=runtime,
    )
    assert result.disposition is Disposition.QUARANTINED
    assert result.reason_code == "raw_source_quarantine_failed"
    assert source.exists()  # no silent second copy/promotion
    assert list(dest.iterdir()) == []
