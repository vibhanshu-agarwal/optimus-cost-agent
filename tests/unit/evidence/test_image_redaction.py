"""RED/GREEN unit tests for canonical screenshot sanitization."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin

from evidence_handoff.redaction.bounds import MAX_IMAGE_BYTES
from evidence_handoff.redaction.models import Disposition, ScreenshotApproval

CANARY_TEXT = "PNG_TEXT_CANARY_SECRET_VALUE"
CANARY_XMP = "XMP_CANARY_SECRET_VALUE"
CANARY_ICC = b"ICC_CANARY_SECRET_VALUE_PROFILE"
CANARY_COMMENT = b"COMMENT_CANARY_SECRET_VALUE"


def _images():
    from evidence_handoff.redaction import images as images_mod

    return images_mod


def _setup(tmp_path: Path) -> tuple[Path, Path, Path]:
    capture = tmp_path / "cap"
    staging = tmp_path / "staging"
    quarantine = tmp_path / "quarantine"
    capture.mkdir()
    staging.mkdir()
    quarantine.mkdir()
    return capture, staging, quarantine


def _write_metadata_png(path: Path) -> None:
    img = Image.new("RGB", (32, 24), color=(12, 34, 56))
    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_text("Author", CANARY_TEXT)
    pnginfo.add_text("XML:com.adobe.xmp", CANARY_XMP)
    buf = io.BytesIO()
    img.save(buf, format="PNG", pnginfo=pnginfo, icc_profile=CANARY_ICC)
    path.write_bytes(buf.getvalue())


def _write_metadata_jpeg(path: Path) -> None:
    img = Image.new("RGB", (40, 30), color=(1, 2, 3))
    exif = img.getexif()
    exif[0x010E] = CANARY_COMMENT.decode("ascii")  # ImageDescription
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90, exif=exif.tobytes())
    path.write_bytes(buf.getvalue())


def test_png_and_jpeg_magic_accepted(tmp_path: Path) -> None:
    images = _images()
    capture, staging, quarantine = _setup(tmp_path)
    png = capture / "shot.png"
    jpg = capture / "shot.jpg"
    Image.new("RGB", (8, 8), color=(0, 0, 0)).save(png)
    Image.new("RGB", (8, 8), color=(0, 0, 0)).save(jpg, format="JPEG")
    for source in (png, jpg):
        result = images.sanitize_screenshot_artifact(
            source_path=source,
            staging_root=staging,
            quarantine_root=quarantine,
            artifact_role="screenshot_v1",
            known_secrets=(),
            known_pii=(),
            path_aliases=(),
        )
        assert result.disposition is Disposition.AWAITING_HUMAN_APPROVAL
        assert result.staging_path is not None
        assert result.staging_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_unsupported_format_quarantines(tmp_path: Path) -> None:
    images = _images()
    capture, staging, quarantine = _setup(tmp_path)
    source = capture / "x.gif"
    Image.new("RGB", (8, 8), color=(0, 0, 0)).save(source, format="GIF")
    result = images.sanitize_screenshot_artifact(
        source_path=source,
        staging_root=staging,
        quarantine_root=quarantine,
        artifact_role="screenshot_v1",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
    )
    assert result.disposition is Disposition.QUARANTINED
    assert result.reason_code == "unsupported_image_format"


def test_multiframe_rejected(tmp_path: Path) -> None:
    images = _images()
    capture, staging, quarantine = _setup(tmp_path)
    source = capture / "anim.gif"
    frames = [Image.new("RGB", (8, 8), color=(i, 0, 0)) for i in range(3)]
    frames[0].save(source, format="GIF", save_all=True, append_images=frames[1:])
    result = images.sanitize_screenshot_artifact(
        source_path=source,
        staging_root=staging,
        quarantine_root=quarantine,
        artifact_role="screenshot_v1",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
    )
    assert result.disposition is Disposition.QUARANTINED
    assert result.reason_code in {"unsupported_image_format", "multiframe_image_rejected"}


def test_byte_and_dimension_bounds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    images = _images()
    capture, staging, quarantine = _setup(tmp_path)
    source = capture / "big.png"
    Image.new("RGB", (16, 16), color=(0, 0, 0)).save(source)
    monkeypatch.setattr(images, "MAX_IMAGE_BYTES", 10)
    result = images.sanitize_screenshot_artifact(
        source_path=source,
        staging_root=staging,
        quarantine_root=quarantine,
        artifact_role="screenshot_v1",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
    )
    assert result.disposition is Disposition.QUARANTINED
    assert result.reason_code == "image_too_large"

    monkeypatch.setattr(images, "MAX_IMAGE_BYTES", MAX_IMAGE_BYTES)
    monkeypatch.setattr(images, "MAX_IMAGE_AXIS_PIXELS", 4)
    source2 = capture / "wide.png"
    Image.new("RGB", (8, 2), color=(0, 0, 0)).save(source2)
    result2 = images.sanitize_screenshot_artifact(
        source_path=source2,
        staging_root=staging,
        quarantine_root=quarantine,
        artifact_role="screenshot_v1",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
    )
    assert result2.disposition is Disposition.QUARANTINED
    assert result2.reason_code == "image_dimensions_too_large"


def _png_with_declared_dimensions(path: Path, width: int, height: int) -> None:
    """Write a small PNG whose IHDR declares a large raster (open sees size; no full raster)."""
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    # Single filtered zero scanline — enough for IHDR/open; incomplete for a full decode.
    raw = b"\x00" + (b"\x00\x00\x00" * width)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def test_pixel_bounds_reject_before_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Real 40M+ declared pixels must fail closed without calling Image.load()."""
    images = _images()
    capture, staging, quarantine = _setup(tmp_path)
    source = capture / "huge-declared.png"
    # 8000 x 5001 = 40_008_000 > MAX_IMAGE_DECODED_PIXELS (40_000_000), under Pillow's ~89M bomb default.
    width, height = 8000, 5001
    assert width * height > images.MAX_IMAGE_DECODED_PIXELS
    assert width <= images.MAX_IMAGE_AXIS_PIXELS
    assert height <= images.MAX_IMAGE_AXIS_PIXELS
    _png_with_declared_dimensions(source, width, height)
    assert source.stat().st_size < images.MAX_IMAGE_BYTES

    load_calls: list[str] = []
    real_load = Image.Image.load

    def _tracking_load(self: Image.Image, *args: object, **kwargs: object) -> Image.Image:
        load_calls.append("load")
        return real_load(self, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "load", _tracking_load)
    result = images.sanitize_screenshot_artifact(
        source_path=source,
        staging_root=staging,
        quarantine_root=quarantine,
        artifact_role="screenshot_v1",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
    )
    assert result.disposition is Disposition.QUARANTINED
    assert result.reason_code == "image_pixels_too_large"
    assert load_calls == []


def test_malformed_decoder_input(tmp_path: Path) -> None:
    images = _images()
    capture, staging, quarantine = _setup(tmp_path)
    source = capture / "bad.jpg"
    source.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)
    result = images.sanitize_screenshot_artifact(
        source_path=source,
        staging_root=staging,
        quarantine_root=quarantine,
        artifact_role="screenshot_v1",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
    )
    assert result.disposition is Disposition.QUARANTINED
    assert result.reason_code == "image_decode_failed"


def test_canonical_png_strips_metadata_and_uses_role_name(tmp_path: Path) -> None:
    images = _images()
    capture, staging, quarantine = _setup(tmp_path)
    source = capture / "unsafe name with spaces & secrets.png"
    _write_metadata_png(source)
    # Also write a JPEG with EXIF canaries for a second pass.
    jpeg = capture / "with-exif.jpg"
    _write_metadata_jpeg(jpeg)

    for path in (source, jpeg):
        result = images.sanitize_screenshot_artifact(
            source_path=path,
            staging_root=staging,
            quarantine_root=quarantine,
            artifact_role="screenshot_v1",
            known_secrets=(),
            known_pii=(),
            path_aliases=(),
        )
        assert result.disposition is Disposition.AWAITING_HUMAN_APPROVAL
        assert result.staging_path is not None
        assert "screenshot_v1" in result.staging_path.name
        assert "unsafe" not in result.staging_path.name
        staged = result.staging_path.read_bytes()
        for canary in (CANARY_TEXT, CANARY_XMP, CANARY_COMMENT.decode("ascii")):
            assert canary.encode("utf-8") not in staged
            assert canary.lower().encode("utf-8") not in staged.lower()
        assert CANARY_ICC not in staged
        # Raw source moved to quarantine; not left in capture.
        assert not path.exists()
        assert result.quarantine_path is not None
        assert result.quarantine_path.exists()
        # Re-open staged image: no text/exif bags.
        with Image.open(result.staging_path) as out:
            assert out.format == "PNG"
            assert not out.info.get("exif")
            assert "Author" not in out.info
            assert out.n_frames == 1


def test_deterministic_png_bytes(tmp_path: Path) -> None:
    images = _images()
    capture, staging, quarantine = _setup(tmp_path)
    src_a = capture / "a.png"
    src_b = capture / "b.png"
    Image.new("RGB", (11, 7), color=(9, 8, 7)).save(src_a)
    Image.new("RGB", (11, 7), color=(9, 8, 7)).save(src_b)
    ra = images.sanitize_screenshot_artifact(
        source_path=src_a,
        staging_root=staging,
        quarantine_root=quarantine,
        artifact_role="screenshot_v1",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
    )
    rb = images.sanitize_screenshot_artifact(
        source_path=src_b,
        staging_root=staging,
        quarantine_root=quarantine,
        artifact_role="screenshot_v1",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
    )
    assert ra.staging_path.read_bytes() == rb.staging_path.read_bytes()
    assert ra.staged_sha256 == rb.staged_sha256


def test_exact_digest_approval_promotes(tmp_path: Path) -> None:
    images = _images()
    capture, staging, quarantine = _setup(tmp_path)
    source = capture / "ok.png"
    Image.new("RGB", (5, 5), color=(1, 1, 1)).save(source)
    pending = images.sanitize_screenshot_artifact(
        source_path=source,
        staging_root=staging,
        quarantine_root=quarantine,
        artifact_role="screenshot_v1",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
    )
    assert pending.disposition is Disposition.AWAITING_HUMAN_APPROVAL
    assert pending.staged_sha256 is not None
    # Re-open staged file as if operator approved the exact digest.
    # Source already quarantined; approve path takes staging path as source?
    # Handler API: pass approval on a second call against already-staged? Plan says
    # recompute digest before promotion. Use evaluate_screenshot_approval helper.
    approval = ScreenshotApproval(
        staged_sha256=pending.staged_sha256,
        approver_id="operator-a",
        collector_id="collector-b",
        approved_at=datetime(2026, 7, 31, 12, 0, tzinfo=UTC),
        rationale="looks clear of secrets",
    )
    decided = images.apply_screenshot_approval(
        staging_path=pending.staging_path,
        approval=approval,
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
    )
    assert decided.disposition is Disposition.PROMOTED
    assert decided.staged_sha256 == pending.staged_sha256
    assert decided.sanitized_approver_id == "operator-a"


def test_stale_approval_rejects(tmp_path: Path) -> None:
    images = _images()
    capture, staging, quarantine = _setup(tmp_path)
    source = capture / "ok.png"
    Image.new("RGB", (5, 5), color=(2, 2, 2)).save(source)
    pending = images.sanitize_screenshot_artifact(
        source_path=source,
        staging_root=staging,
        quarantine_root=quarantine,
        artifact_role="screenshot_v1",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
    )
    approval = ScreenshotApproval(
        staged_sha256="0" * 64,
        approver_id="operator-a",
        collector_id="collector-b",
        approved_at=datetime(2026, 7, 31, 12, 0, tzinfo=UTC),
        rationale="stale",
    )
    decided = images.apply_screenshot_approval(
        staging_path=pending.staging_path,
        approval=approval,
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
    )
    assert decided.disposition is Disposition.QUARANTINED
    assert decided.reason_code == "approval_digest_mismatch"


def test_self_approval_rejected_by_contract() -> None:
    with pytest.raises(ValueError, match="approver_equals_collector"):
        ScreenshotApproval(
            staged_sha256="a" * 64,
            approver_id="same",
            collector_id="same",
            approved_at=datetime(2026, 7, 31, 12, 0, tzinfo=UTC),
            rationale="nope",
        )


def test_approval_identity_and_rationale_sanitized(tmp_path: Path) -> None:
    images = _images()
    capture, staging, quarantine = _setup(tmp_path)
    source = capture / "ok.png"
    Image.new("RGB", (4, 4), color=(3, 3, 3)).save(source)
    pending = images.sanitize_screenshot_artifact(
        source_path=source,
        staging_root=staging,
        quarantine_root=quarantine,
        artifact_role="screenshot_v1",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
    )
    secret = "Q7mV2xN9pR4tY8kL3cD6wF1hJ5sB0zUa"
    approval = ScreenshotApproval(
        staged_sha256=pending.staged_sha256 or ("b" * 64),
        approver_id=f"ops-{secret}",
        collector_id="collector-b",
        approved_at=datetime(2026, 7, 31, 12, 0, tzinfo=UTC),
        rationale=f"reviewed {secret}",
    )
    decided = images.apply_screenshot_approval(
        staging_path=pending.staging_path,
        approval=approval,
        known_secrets=(secret,),
        known_pii=(),
        path_aliases=(),
    )
    assert decided.disposition is Disposition.PROMOTED
    assert secret not in (decided.sanitized_approver_id or "")
    assert secret not in (decided.sanitized_rationale or "")
    assert "**********" in (decided.sanitized_rationale or "")
