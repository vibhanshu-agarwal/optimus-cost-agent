"""Streaming text artifact sanitization for evidence redaction."""

from __future__ import annotations

import codecs
import os
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from optimus_security.sanitization import (
    EVIDENCE_REDACTION_POLICY,
    PathAliasRule,
    StreamingTextSanitizer,
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
    """Stream-sanitize a text artifact into private staging. Never writes raw interim text."""
    try:
        size = source_path.stat().st_size
    except OSError:
        return _quarantine("text_source_unreadable")
    if size > MAX_ARTIFACT_BYTES:
        return _quarantine("input_too_large")

    sanitizer = StreamingTextSanitizer(
        known_secrets=known_secrets,
        known_pii=known_pii,
        path_aliases=path_aliases,
        policy=EVIDENCE_REDACTION_POLICY,
    )
    decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
    handle = None
    staging_path: Path | None = None
    byte_size = 0
    try:
        handle = create_private_staging_file(staging_root=staging_root, artifact_role=artifact_role)
        staging_path = handle.path
        with source_path.open("rb") as source:
            while True:
                chunk = source.read(read_size)
                if not chunk:
                    break
                try:
                    text_chunk = decoder.decode(chunk, final=False)
                except UnicodeDecodeError:
                    raise _Utf8Error from None
                released = sanitizer.feed(text_chunk)
                if released:
                    data = released.encode("utf-8")
                    os.write(handle.fileno(), data)
                    byte_size += len(data)
            try:
                text_chunk = decoder.decode(b"", final=True)
            except UnicodeDecodeError:
                raise _Utf8Error from None
            if text_chunk:
                released = sanitizer.feed(text_chunk)
                if released:
                    data = released.encode("utf-8")
                    os.write(handle.fileno(), data)
                    byte_size += len(data)
            final = sanitizer.finalize()
            if final:
                data = final.encode("utf-8")
                os.write(handle.fileno(), data)
                byte_size += len(data)
        handle.flush()
        handle.close()
        handle = None
        return TextSanitizeResult(
            disposition=Disposition.PROMOTED,
            staging_path=staging_path,
            rule_counts=dict(sanitizer.rule_counts),
            reason_code=None,
            byte_size=byte_size,
        )
    except _Utf8Error:
        _abort_staging(handle, staging_path)
        return _quarantine("invalid_utf8", rule_counts=sanitizer.rule_counts)
    except PrivateFileError:
        _abort_staging(handle, staging_path)
        return _quarantine("private_staging_failed", rule_counts=sanitizer.rule_counts)
    except OSError:
        _abort_staging(handle, staging_path)
        return _quarantine("text_io_failed", rule_counts=sanitizer.rule_counts)


class _Utf8Error(Exception):
    pass


def _abort_staging(handle: object | None, staging_path: Path | None) -> None:
    if handle is not None:
        close = getattr(handle, "close", None)
        if close is not None:
            with suppress(Exception):
                close()
    if staging_path is not None:
        with suppress(Exception):
            cleanup_private_path(staging_path)
