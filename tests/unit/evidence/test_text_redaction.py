"""RED/GREEN unit tests for streaming text evidence sanitization."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_handoff.redaction.bounds import STREAM_READ_BYTES
from evidence_handoff.redaction.models import Disposition

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "evidence"


def _canaries() -> dict[str, str]:
    return json.loads((FIXTURES / "redaction_canaries.json").read_text(encoding="utf-8"))


def _text():
    from evidence_handoff.redaction import text as text_mod

    return text_mod


def test_exact_secret_split_across_every_stream_boundary(tmp_path: Path) -> None:
    text = _text()
    canaries = _canaries()
    secret = canaries["unlabeled_api_key"]
    body = ("prefix-" + secret + "-suffix\n").encode("utf-8")
    source = tmp_path / "cap" / "note.txt"
    source.parent.mkdir(parents=True)
    source.write_bytes(body)
    staging = tmp_path / "staging"
    staging.mkdir()

    for split in range(1, len(secret)):
        result = text.sanitize_text_artifact(
            source_path=source,
            staging_root=staging,
            artifact_role="session_note",
            known_secrets=(secret,),
            known_pii=(),
            path_aliases=(),
            read_size=max(1, split),
        )
        assert result.disposition is Disposition.PROMOTED
        assert result.staging_path is not None
        out = result.staging_path.read_text(encoding="utf-8")
        assert secret not in out
        assert "**********" in out
        result.staging_path.unlink(missing_ok=True)


def test_candidates_split_across_64kib_reads(tmp_path: Path) -> None:
    text = _text()
    canaries = _canaries()
    secret = canaries["unlabeled_api_key"]
    # Place secret across the default 64 KiB boundary.
    left = b"x" * (STREAM_READ_BYTES - len(secret) // 2)
    payload = left + secret.encode("utf-8") + b"\n"
    assert len(left) < STREAM_READ_BYTES < len(payload)
    source = tmp_path / "cap" / "big.txt"
    source.parent.mkdir()
    source.write_bytes(payload)
    staging = tmp_path / "staging"
    staging.mkdir()
    result = text.sanitize_text_artifact(
        source_path=source,
        staging_root=staging,
        artifact_role="session_note",
        known_secrets=(secret,),
        known_pii=(),
        path_aliases=(),
    )
    assert result.disposition is Disposition.PROMOTED
    assert secret not in result.staging_path.read_text(encoding="utf-8")


def test_preserves_original_newlines(tmp_path: Path) -> None:
    text = _text()
    source = tmp_path / "cap" / "lines.txt"
    source.parent.mkdir()
    source.write_bytes(b"a\r\nb\nc\r\n")
    staging = tmp_path / "staging"
    staging.mkdir()
    result = text.sanitize_text_artifact(
        source_path=source,
        staging_root=staging,
        artifact_role="session_note",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
    )
    assert result.disposition is Disposition.PROMOTED
    assert result.staging_path.read_bytes() == b"a\r\nb\nc\r\n"


def test_strict_utf8_no_raw_fallback(tmp_path: Path) -> None:
    text = _text()
    source = tmp_path / "cap" / "bad.txt"
    source.parent.mkdir()
    source.write_bytes(b"ok\xffnot-utf8")
    staging = tmp_path / "staging"
    staging.mkdir()
    result = text.sanitize_text_artifact(
        source_path=source,
        staging_root=staging,
        artifact_role="session_note",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
    )
    assert result.disposition is Disposition.QUARANTINED
    assert result.reason_code == "invalid_utf8"
    assert result.staging_path is None
    # No raw interim transcript under staging.
    assert list(staging.iterdir()) == [] or all(
        p.suffix != ".txt" or "ok" not in p.read_bytes() for p in staging.iterdir() if p.is_file()
    )


def test_input_too_large_quarantines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    text = _text()
    monkeypatch.setattr(text, "MAX_ARTIFACT_BYTES", 16)
    source = tmp_path / "cap" / "big.txt"
    source.parent.mkdir()
    source.write_bytes(b"0123456789abcdef!")
    staging = tmp_path / "staging"
    staging.mkdir()
    result = text.sanitize_text_artifact(
        source_path=source,
        staging_root=staging,
        artifact_role="session_note",
        known_secrets=(),
        known_pii=(),
        path_aliases=(),
    )
    assert result.disposition is Disposition.QUARANTINED
    assert result.reason_code == "input_too_large"
