"""Text artifact sanitization for evidence redaction: one one-shot pass over the whole decoded artifact."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from optimus_security.sanitization import (
    EVIDENCE_REDACTION_POLICY,
    PathAliasRule,
    sanitize_for_persistence,
)

from .bounds import MAX_ARTIFACT_BYTES, STREAM_READ_BYTES
from .models import Disposition
from .private_files import (
    PrivateFileError,
    cleanup_private_path,
    create_private_staging_file,
)

# Re-export for tests that monkeypatch handler-local bounds.
__all__ = [
    "MAX_ARTIFACT_BYTES",
    "STREAM_READ_BYTES",
    "TextSanitizeResult",
    "sanitize_text_artifact",
]


@dataclass(frozen=True)
class TextSanitizeResult:
    disposition: Disposition
    staging_path: Path | None
    rule_counts: Mapping[str, int]
    reason_code: str | None
    byte_size: int | None


def _quarantine(reason: str, *, rule_counts: Mapping[str, int] | None = None) -> TextSanitizeResult:
    return TextSanitizeResult(
        disposition=Disposition.QUARANTINED,
        staging_path=None,
        rule_counts=dict(rule_counts or {}),
        reason_code=reason,
        byte_size=None,
    )


def sanitize_text_artifact(
    *,
    source_path: Path,
    staging_root: Path,
    artifact_role: str,
    known_secrets: Sequence[str],
    known_pii: Sequence[str],
    path_aliases: Sequence[PathAliasRule],
    read_size: int = STREAM_READ_BYTES,
) -> TextSanitizeResult:
    """Sanitize a text artifact into private staging in one pass. Never writes raw interim text.

    The whole artifact (at most ``MAX_ARTIFACT_BYTES``) is decoded and sanitized at once, so the output is exactly
    one-shot ``sanitize_for_persistence``: a streaming cut can separate a label from its value or change how ordered
    rules interact, at any distance (#622). ``read_size`` only sets the read chunk.
    """
    try:
        size = source_path.stat().st_size
    except OSError:
        return _quarantine("text_source_unreadable")
    if size > MAX_ARTIFACT_BYTES:
        return _quarantine("input_too_large")

    handle = None
    staging_path: Path | None = None
    try:
        chunks: list[bytes] = []
        total = 0
        with source_path.open("rb") as source:
            while chunk := source.read(read_size):
                total += len(chunk)
                if total > MAX_ARTIFACT_BYTES:
                    # The file grew after the size check.
                    return _quarantine("input_too_large")
                chunks.append(chunk)
        try:
            raw_text = b"".join(chunks).decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return _quarantine("invalid_utf8")
        del chunks
        result = sanitize_for_persistence(
            raw_text,
            known_secrets=known_secrets,
            known_pii=known_pii,
            path_aliases=path_aliases,
            policy=EVIDENCE_REDACTION_POLICY,
        )
        del raw_text
        data = str(result.value).encode("utf-8")
        handle = create_private_staging_file(staging_root=staging_root, artifact_role=artifact_role)
        staging_path = handle.path
        view = memoryview(data)
        while view:
            view = view[os.write(handle.fileno(), view) :]
        handle.flush()
        handle.close()
        handle = None
        return TextSanitizeResult(
            disposition=Disposition.PROMOTED,
            staging_path=staging_path,
            rule_counts=dict(result.rule_counts),
            reason_code=None,
            byte_size=len(data),
        )
    except PrivateFileError:
        _abort_staging(handle, staging_path)
        return _quarantine("private_staging_failed")
    except OSError:
        _abort_staging(handle, staging_path)
        return _quarantine("text_io_failed")


def _abort_staging(handle: object | None, staging_path: Path | None) -> None:
    if handle is not None:
        close = getattr(handle, "close", None)
        if close is not None:
            with suppress(Exception):
                close()
    if staging_path is not None:
        with suppress(Exception):
            cleanup_private_path(staging_path)
