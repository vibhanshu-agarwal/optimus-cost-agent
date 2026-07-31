"""Fail-closed redaction gate: dispatch, manifest, and atomic bundle promotion."""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from collections.abc import Mapping, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from optimus_security.sanitization import EVIDENCE_REDACTION_POLICY, PathAliasRule

from . import images, quarantine, structured, text
from .manifest import (
    MANIFEST_SCHEMA_VERSION,
    ManifestError,
    manifest_canary_scan,
    serialize_manifest,
)
from .models import (
    ArtifactKind,
    Disposition,
    RedactionGateResult,
    RedactionRuntimeInputs,
    ScreenshotApproval,
)
from .private_files import (
    PrivateFileError,
    _filesystem_device_id,
    apply_restrictive_permissions,
    atomic_replace_same_filesystem,
    cleanup_private_path,
    create_private_directory,
)

_PNG = b"\x89PNG\r\n\x1a\n"
_JPEG = b"\xff\xd8\xff"
_MDMP = b"MDMP"
_ELF = b"\x7fELF"


def _result(
    disposition: Disposition,
    *,
    artifact_locator: str | None = None,
    manifest_locator: str | None = None,
    reason_code: str | None = None,
) -> RedactionGateResult:
    return RedactionGateResult(
        disposition=disposition,
        artifact_locator=artifact_locator,
        manifest_locator=manifest_locator,
        reason_code=reason_code,
    )


def _alias_locator(path: Path, aliases: Sequence[PathAliasRule]) -> str:
    text_path = path.resolve().as_posix()
    ranked = sorted(
        (
            PathAliasRule(source_root=str(Path(rule.source_root).resolve()), alias=rule.alias)
            for rule in aliases
        ),
        key=lambda item: len(item.source_root),
        reverse=True,
    )
    for rule in ranked:
        root = Path(rule.source_root).resolve().as_posix().rstrip("/")
        if text_path == root or text_path.startswith(root + "/"):
            return rule.alias + text_path[len(root) :]
    # Never emit absolute paths in locators.
    return "<opaque>/" + path.name


def _read_magic(path: Path) -> bytes:
    with path.open("rb") as handle:
        return handle.read(16)


def _kind_mismatch(kind: ArtifactKind, magic: bytes) -> bool:
    if kind is ArtifactKind.SCREENSHOT:
        return not (magic.startswith(_PNG) or magic.startswith(_JPEG))
    if kind is ArtifactKind.PROCESS_DUMP:
        return False  # unknown magic still handled as dump quarantine
    if kind in {ArtifactKind.TEXT, ArtifactKind.JSON, ArtifactKind.NDJSON, ArtifactKind.ACP_DEBUG_TRACE}:
        if magic.startswith(_PNG) or magic.startswith(_JPEG) or magic.startswith(_MDMP) or magic.startswith(_ELF):
            return True
    return False


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _cleanup_tree(path: Path | None) -> None:
    if path is None:
        return
    with suppress(Exception):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            cleanup_private_path(path)


def _promote_bundle(*, bundle_dir: Path, destination_root: Path) -> Path:
    """Atomically rename a private bundle directory into the destination root."""
    dest = destination_root / bundle_dir.name
    if dest.exists():
        raise PrivateFileError("promotion_destination_exists")
    if not bundle_dir.is_dir():
        raise PrivateFileError("promotion_bundle_missing")
    if _filesystem_device_id(bundle_dir) != _filesystem_device_id(destination_root):
        raise PrivateFileError("cross_filesystem_rename_rejected")
    try:
        os.replace(bundle_dir, dest)
    except OSError:
        raise PrivateFileError("atomic_replace_failed") from None
    return dest


def _write_promoted_bundle(
    *,
    staging_root: Path,
    destination_root: Path,
    artifact_role: str,
    artifact_path: Path,
    manifest_fields: Mapping[str, object],
    known_secrets: Sequence[str],
    known_pii: Sequence[str],
    aliases: Sequence[PathAliasRule],
) -> tuple[str, str]:
    serialized = serialize_manifest(manifest_fields)
    if not manifest_canary_scan(serialized, known_secrets=known_secrets, known_pii=known_pii):
        raise ManifestError("manifest_canary_failed")

    bundle_name = f"{artifact_role}-{uuid.uuid4().hex}"
    bundle_dir = staging_root / f"bundle-{bundle_name}"
    create_private_directory(bundle_dir)
    artifact_dest = bundle_dir / "artifact"
    manifest_dest = bundle_dir / "manifest.json"
    try:
        # Same-filesystem move of staged artifact into the private bundle.
        atomic_replace_same_filesystem(artifact_path, artifact_dest)
        apply_restrictive_permissions(artifact_dest)
        data = serialized.encode("utf-8")
        with manifest_dest.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        apply_restrictive_permissions(manifest_dest)
        # Directory fsync best-effort.
        try:
            dir_fd = os.open(bundle_dir, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
        promoted = _promote_bundle(bundle_dir=bundle_dir, destination_root=destination_root)
    except Exception:
        _cleanup_tree(bundle_dir)
        raise

    artifact_locator = _alias_locator(promoted / "artifact", aliases)
    manifest_locator = _alias_locator(promoted / "manifest.json", aliases)
    return artifact_locator, manifest_locator


def run_redaction_gate(
    *,
    source_path: Path,
    destination_root: Path,
    artifact_kind: ArtifactKind,
    artifact_role: str,
    runtime: RedactionRuntimeInputs,
    screenshot_approval: ScreenshotApproval | None = None,
) -> RedactionGateResult:
    """Orchestrate sanitize → manifest canary → atomic destination promotion."""
    try:
        # Request validation without opening source body beyond existence/magic later.
        if not source_path.is_absolute() or not destination_root.is_absolute():
            return _result(Disposition.REJECTED, reason_code="relative_path_rejected")
        if not source_path.exists() or not source_path.is_file():
            return _result(Disposition.REJECTED, reason_code="source_missing")
    except OSError:
        return _result(Disposition.REJECTED, reason_code="source_unreadable")

    secrets = runtime.sensitive_values.secret_values_for_sanitizer()
    pii = runtime.sensitive_values.pii_values_for_sanitizer()
    aliases = runtime.path_aliases

    try:
        magic = _read_magic(source_path)
    except OSError:
        return _result(Disposition.QUARANTINED, reason_code="source_unreadable")
    if _kind_mismatch(artifact_kind, magic):
        return _result(Disposition.QUARANTINED, reason_code="artifact_kind_mismatch")

    created_at = datetime.now(tz=UTC).isoformat()

    try:
        if artifact_kind is ArtifactKind.TEXT:
            outcome = text.sanitize_text_artifact(
                source_path=source_path,
                staging_root=runtime.staging_root,
                artifact_role=artifact_role,
                known_secrets=secrets,
                known_pii=pii,
                path_aliases=aliases,
            )
            if outcome.disposition is not Disposition.PROMOTED or outcome.staging_path is None:
                return _result(
                    Disposition.QUARANTINED,
                    reason_code=outcome.reason_code or "text_sanitize_failed",
                )
            digest = _sha256_file(outcome.staging_path)
            fields = {
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "sanitizer_policy_version": EVIDENCE_REDACTION_POLICY.version,
                "artifact_kind": artifact_kind.value,
                "disposition": Disposition.PROMOTED.value,
                "artifact_sha256": digest,
                "artifact_byte_size": outcome.byte_size,
                "artifact_locator": "<destination>/" + artifact_role + "/artifact",
                "rule_counts": dict(outcome.rule_counts),
                "final_scan_passed": True,
                "reason_code": None,
                "created_at": created_at,
            }
            artifact_locator, manifest_locator = _write_promoted_bundle(
                staging_root=runtime.staging_root,
                destination_root=destination_root,
                artifact_role=artifact_role,
                artifact_path=outcome.staging_path,
                manifest_fields=fields,
                known_secrets=secrets,
                known_pii=pii,
                aliases=aliases,
            )
            return _result(
                Disposition.PROMOTED,
                artifact_locator=artifact_locator,
                manifest_locator=manifest_locator,
            )

        if artifact_kind is ArtifactKind.JSON:
            outcome = structured.sanitize_json_artifact(
                source_path=source_path,
                staging_root=runtime.staging_root,
                artifact_role=artifact_role,
                known_secrets=secrets,
                known_pii=pii,
                path_aliases=aliases,
            )
            return _promote_structured(
                outcome,
                artifact_kind=artifact_kind,
                artifact_role=artifact_role,
                runtime=runtime,
                destination_root=destination_root,
                secrets=secrets,
                pii=pii,
                created_at=created_at,
            )

        if artifact_kind in {ArtifactKind.NDJSON, ArtifactKind.ACP_DEBUG_TRACE}:
            outcome = structured.sanitize_ndjson_artifact(
                source_path=source_path,
                staging_root=runtime.staging_root,
                artifact_role=artifact_role,
                known_secrets=secrets,
                known_pii=pii,
                path_aliases=aliases,
                allow_acp_truncated_tail=artifact_kind is ArtifactKind.ACP_DEBUG_TRACE,
            )
            return _promote_structured(
                outcome,
                artifact_kind=artifact_kind,
                artifact_role=artifact_role,
                runtime=runtime,
                destination_root=destination_root,
                secrets=secrets,
                pii=pii,
                created_at=created_at,
            )

        if artifact_kind is ArtifactKind.SCREENSHOT:
            outcome = images.sanitize_screenshot_artifact(
                source_path=source_path,
                staging_root=runtime.staging_root,
                quarantine_root=runtime.quarantine_root,
                artifact_role=artifact_role,
                known_secrets=secrets,
                known_pii=pii,
                path_aliases=aliases,
            )
            if outcome.disposition is Disposition.QUARANTINED:
                return _result(
                    Disposition.QUARANTINED,
                    reason_code=outcome.reason_code or "image_sanitize_failed",
                )
            if screenshot_approval is not None and outcome.staging_path is not None:
                return promote_approved_screenshot(
                    staging_path=outcome.staging_path,
                    destination_root=destination_root,
                    artifact_role=artifact_role,
                    runtime=runtime,
                    approval=screenshot_approval,
                )
            locator = (
                _alias_locator(outcome.staging_path, aliases)
                if outcome.staging_path is not None
                else None
            )
            return _result(
                Disposition.AWAITING_HUMAN_APPROVAL,
                artifact_locator=locator,
                reason_code=None,
            )

        if artifact_kind is ArtifactKind.PROCESS_DUMP:
            dump = quarantine.quarantine_process_dump(
                source_path=source_path,
                quarantine_root=runtime.quarantine_root,
            )
            return _result(
                Disposition.QUARANTINED,
                reason_code=dump.reason_code,
                artifact_locator=(
                    _alias_locator(dump.quarantine_path, aliases) if dump.quarantine_path else None
                ),
            )

        return _result(Disposition.REJECTED, reason_code="unsupported_artifact_kind")
    except ManifestError as exc:
        return _result(Disposition.QUARANTINED, reason_code=exc.code)
    except PrivateFileError as exc:
        return _result(Disposition.QUARANTINED, reason_code=exc.code)
    except OSError:
        return _result(Disposition.QUARANTINED, reason_code="gate_io_failed")


def _promote_structured(
    outcome: structured.StructuredSanitizeResult,
    *,
    artifact_kind: ArtifactKind,
    artifact_role: str,
    runtime: RedactionRuntimeInputs,
    destination_root: Path,
    secrets: Sequence[str],
    pii: Sequence[str],
    created_at: str,
) -> RedactionGateResult:
    if outcome.disposition is not Disposition.PROMOTED or outcome.staging_path is None:
        return _result(
            Disposition.QUARANTINED,
            reason_code=outcome.reason_code or "structured_sanitize_failed",
        )
    digest = _sha256_file(outcome.staging_path)
    fields: dict[str, object] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "sanitizer_policy_version": EVIDENCE_REDACTION_POLICY.version,
        "artifact_kind": artifact_kind.value,
        "disposition": Disposition.PROMOTED.value,
        "artifact_sha256": digest,
        "artifact_byte_size": outcome.byte_size,
        "artifact_locator": "<destination>/" + artifact_role + "/artifact",
        "rule_counts": dict(outcome.rule_counts),
        "final_scan_passed": True,
        "reason_code": None,
        "created_at": created_at,
    }
    if outcome.truncated_tail_dropped:
        fields["truncated_tail_dropped"] = True
        fields["dropped_tail_bytes"] = outcome.dropped_tail_bytes
    artifact_locator, manifest_locator = _write_promoted_bundle(
        staging_root=runtime.staging_root,
        destination_root=destination_root,
        artifact_role=artifact_role,
        artifact_path=outcome.staging_path,
        manifest_fields=fields,
        known_secrets=secrets,
        known_pii=pii,
        aliases=runtime.path_aliases,
    )
    return _result(
        Disposition.PROMOTED,
        artifact_locator=artifact_locator,
        manifest_locator=manifest_locator,
    )


def promote_approved_screenshot(
    *,
    staging_path: Path,
    destination_root: Path,
    artifact_role: str,
    runtime: RedactionRuntimeInputs,
    approval: ScreenshotApproval,
) -> RedactionGateResult:
    """Recheck digest-bound approval and atomically promote a staged screenshot."""
    secrets = runtime.sensitive_values.secret_values_for_sanitizer()
    pii = runtime.sensitive_values.pii_values_for_sanitizer()
    decided = images.apply_screenshot_approval(
        staging_path=staging_path,
        approval=approval,
        known_secrets=secrets,
        known_pii=pii,
        path_aliases=runtime.path_aliases,
    )
    if decided.disposition is not Disposition.PROMOTED or decided.staging_path is None:
        return _result(
            Disposition.QUARANTINED,
            reason_code=decided.reason_code or "approval_failed",
        )
    created_at = datetime.now(tz=UTC).isoformat()
    fields = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "sanitizer_policy_version": EVIDENCE_REDACTION_POLICY.version,
        "artifact_kind": ArtifactKind.SCREENSHOT.value,
        "disposition": Disposition.PROMOTED.value,
        "artifact_sha256": decided.staged_sha256,
        "artifact_byte_size": decided.byte_size,
        "artifact_locator": "<destination>/" + artifact_role + "/artifact",
        "rule_counts": dict(decided.rule_counts or {}),
        "final_scan_passed": True,
        "reason_code": None,
        "approval_sha256": decided.staged_sha256,
        "approver_id": decided.sanitized_approver_id,
        "approved_at": approval.approved_at.isoformat(),
        "created_at": created_at,
    }
    try:
        artifact_locator, manifest_locator = _write_promoted_bundle(
            staging_root=runtime.staging_root,
            destination_root=destination_root,
            artifact_role=artifact_role,
            artifact_path=decided.staging_path,
            manifest_fields=fields,
            known_secrets=secrets,
            known_pii=pii,
            aliases=runtime.path_aliases,
        )
    except ManifestError as exc:
        return _result(Disposition.QUARANTINED, reason_code=exc.code)
    except PrivateFileError as exc:
        return _result(Disposition.QUARANTINED, reason_code=exc.code)
    return _result(
        Disposition.PROMOTED,
        artifact_locator=artifact_locator,
        manifest_locator=manifest_locator,
    )


# Re-export for monkeypatch in unit tests.
__all__ = [
    "promote_approved_screenshot",
    "run_redaction_gate",
    "_promote_bundle",
]
