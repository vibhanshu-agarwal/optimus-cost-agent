"""Canonical screenshot decode/re-encode and digest-bound approval binding."""

from __future__ import annotations

import hashlib
import io
import os
import warnings
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageFile, UnidentifiedImageError

from optimus_security.sanitization import (
    EVIDENCE_REDACTION_POLICY,
    PathAliasRule,
    sanitize_for_persistence,
)

from .bounds import (
    MAX_IMAGE_AXIS_PIXELS,
    MAX_IMAGE_BYTES,
    MAX_IMAGE_DECODED_PIXELS,
)
from .models import Disposition, ScreenshotApproval
from .private_files import (
    PrivateFileError,
    cleanup_private_path,
    create_private_staging_file,
    quarantine_partial_staging,
    verify_restrictive_permissions,
)

# Re-export for monkeypatchable bounds.
__all__ = [
    "MAX_IMAGE_AXIS_PIXELS",
    "MAX_IMAGE_BYTES",
    "MAX_IMAGE_DECODED_PIXELS",
    "ImageSanitizeResult",
    "apply_screenshot_approval",
    "sanitize_screenshot_artifact",
]

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"


@dataclass(frozen=True)
class ImageSanitizeResult:
    disposition: Disposition
    staging_path: Path | None
    quarantine_path: Path | None
    staged_sha256: str | None
    reason_code: str | None
    byte_size: int | None
    sanitized_approver_id: str | None = None
    sanitized_rationale: str | None = None
    rule_counts: Mapping[str, int] | None = None


def _quarantine_result(
    reason: str,
    *,
    quarantine_path: Path | None = None,
) -> ImageSanitizeResult:
    return ImageSanitizeResult(
        disposition=Disposition.QUARANTINED,
        staging_path=None,
        quarantine_path=quarantine_path,
        staged_sha256=None,
        reason_code=reason,
        byte_size=None,
        sanitized_approver_id=None,
        sanitized_rationale=None,
        rule_counts=None,
    )


def _detect_image_magic(header: bytes) -> str | None:
    if header.startswith(_PNG_MAGIC):
        return "PNG"
    if header.startswith(_JPEG_MAGIC):
        return "JPEG"
    return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _abort_staging(handle: object | None, staging_path: Path | None) -> None:
    if handle is not None:
        close = getattr(handle, "close", None)
        if close is not None:
            with suppress(Exception):
                close()
    if staging_path is not None:
        with suppress(Exception):
            cleanup_private_path(staging_path)

def sanitize_screenshot_artifact(
    *,
    source_path: Path,
    staging_root: Path,
    quarantine_root: Path,
    artifact_role: str,
    known_secrets: Sequence[str],
    known_pii: Sequence[str],
    path_aliases: Sequence[PathAliasRule],
) -> ImageSanitizeResult:
    """Decode a PNG/JPEG screenshot into a metadata-free staged PNG.

    Moves the raw source into quarantine before returning awaiting-approval state.
    """
    del known_secrets, known_pii, path_aliases  # reserved for approval-path sanitization
    try:
        size = source_path.stat().st_size
    except OSError:
        return _quarantine_result("image_source_unreadable")
    if size > MAX_IMAGE_BYTES:
        return _quarantine_result("image_too_large")
    try:
        with source_path.open("rb") as handle:
            header = handle.read(16)
    except OSError:
        return _quarantine_result("image_source_unreadable")
    kind = _detect_image_magic(header)
    if kind is None:
        return _quarantine_result("unsupported_image_format")

    handle = None
    staging_path: Path | None = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            try:
                with Image.open(source_path) as img:
                    frames = int(getattr(img, "n_frames", 1) or 1)
                    if frames != 1:
                        return _quarantine_result("multiframe_image_rejected")
                    # Bounds use header/metadata size — must run before full decode.
                    width, height = img.size
                    if width > MAX_IMAGE_AXIS_PIXELS or height > MAX_IMAGE_AXIS_PIXELS:
                        return _quarantine_result("image_dimensions_too_large")
                    if width * height > MAX_IMAGE_DECODED_PIXELS:
                        return _quarantine_result("image_pixels_too_large")
                    img.load()
                    mode = "RGBA" if img.mode in {"RGBA", "LA", "PA"} or "A" in img.getbands() else "RGB"
                    if mode == "RGBA":
                        pixels = img.convert("RGBA")
                    else:
                        pixels = img.convert("RGB")
                    clean = Image.new(mode, pixels.size)
                    clean.paste(pixels, (0, 0))
            except UnidentifiedImageError:
                return _quarantine_result("image_decode_failed")
            except Image.DecompressionBombError:
                return _quarantine_result("image_decompression_failed")
            except OSError:
                return _quarantine_result("image_decode_failed")
            except Warning:
                return _quarantine_result("image_decompression_failed")

        buf = io.BytesIO()
        save_kwargs: dict[str, object] = {
            "format": "PNG",
            "optimize": False,
            "compress_level": 9,
        }
        clean.save(buf, **save_kwargs)
        payload = buf.getvalue()
        if not payload.startswith(_PNG_MAGIC):
            return _quarantine_result("image_encode_failed")

        handle = create_private_staging_file(staging_root=staging_root, artifact_role=artifact_role)
        staging_path = handle.path
        os.write(handle.fileno(), payload)
        handle.flush()
        handle.close()
        handle = None
        verify_restrictive_permissions(staging_path)
        digest = _sha256_file(staging_path)

        try:
            quarantined = quarantine_partial_staging(source_path, quarantine_root=quarantine_root)
            verify_restrictive_permissions(quarantined)
        except PrivateFileError:
            _abort_staging(None, staging_path)
            return _quarantine_result("raw_source_quarantine_failed")

        return ImageSanitizeResult(
            disposition=Disposition.AWAITING_HUMAN_APPROVAL,
            staging_path=staging_path,
            quarantine_path=quarantined,
            staged_sha256=digest,
            reason_code=None,
            byte_size=len(payload),
        )
    except PrivateFileError:
        _abort_staging(handle, staging_path)
        return _quarantine_result("private_staging_failed")
    except OSError:
        _abort_staging(handle, staging_path)
        return _quarantine_result("image_io_failed")


def apply_screenshot_approval(
    *,
    staging_path: Path,
    approval: ScreenshotApproval,
    known_secrets: Sequence[str],
    known_pii: Sequence[str],
    path_aliases: Sequence[PathAliasRule],
) -> ImageSanitizeResult:
    """Recompute staged digest and bind an independent human approval record."""
    try:
        digest = _sha256_file(staging_path)
    except OSError:
        return _quarantine_result("staged_image_unreadable")
    if digest != approval.staged_sha256:
        return _quarantine_result("approval_digest_mismatch")

    approver = sanitize_for_persistence(
        approval.approver_id,
        known_secrets=known_secrets,
        known_pii=known_pii,
        path_aliases=path_aliases,
        policy=EVIDENCE_REDACTION_POLICY,
    )
    rationale = sanitize_for_persistence(
        approval.rationale,
        known_secrets=known_secrets,
        known_pii=known_pii,
        path_aliases=path_aliases,
        policy=EVIDENCE_REDACTION_POLICY,
    )
    return ImageSanitizeResult(
        disposition=Disposition.PROMOTED,
        staging_path=staging_path,
        quarantine_path=None,
        staged_sha256=digest,
        reason_code=None,
        byte_size=staging_path.stat().st_size,
        sanitized_approver_id=str(approver.value),
        sanitized_rationale=str(rationale.value),
        rule_counts={
            key: approver.rule_counts.get(key, 0) + rationale.rule_counts.get(key, 0)
            for key in set(approver.rule_counts) | set(rationale.rule_counts)
        },
    )


# Harden decoder against truncated streams failing open.
ImageFile.LOAD_TRUNCATED_IMAGES = False
