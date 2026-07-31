"""Hash-only process-dump recognition and quarantine custody."""

from __future__ import annotations

import hashlib
import struct
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .bounds import STREAM_READ_BYTES
from .models import Disposition
from .private_files import (
    PrivateFileError,
    _filesystem_device_id,
    apply_restrictive_permissions,
    atomic_replace_same_filesystem,
    verify_restrictive_permissions,
)

__all__ = [
    "DumpQuarantineResult",
    "quarantine_process_dump",
    "recognize_dump_kind",
]

_MDMP = b"MDMP"
_ELF = b"\x7fELF"
_ET_CORE = 4


@dataclass(frozen=True)
class DumpQuarantineResult:
    disposition: Disposition
    dump_kind: str
    sha256: str | None
    byte_size: int | None
    quarantine_path: Path | None
    discovered_at: datetime | None
    reason_code: str | None

    def __repr__(self) -> str:
        return (
            "DumpQuarantineResult("
            f"disposition={self.disposition!r}, "
            f"dump_kind={self.dump_kind!r}, "
            f"sha256={self.sha256!r}, "
            f"byte_size={self.byte_size!r}, "
            f"reason_code={self.reason_code!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()


def recognize_dump_kind(header: bytes) -> str:
    """Classify a dump from a bounded header only."""
    if header.startswith(_MDMP):
        return "windows_minidump"
    if len(header) >= 18 and header.startswith(_ELF):
        ei_data = header[5]
        if ei_data == 1:
            e_type = struct.unpack_from("<H", header, 16)[0]
        elif ei_data == 2:
            e_type = struct.unpack_from(">H", header, 16)[0]
        else:
            return "unknown"
        if e_type == _ET_CORE:
            return "elf_core"
    return "unknown"


def _stream_sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(STREAM_READ_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
    return digest.hexdigest(), total


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def quarantine_process_dump(
    *,
    source_path: Path,
    quarantine_root: Path,
) -> DumpQuarantineResult:
    """Hash a process dump and move/retain it in quarantine. Never promotes."""
    discovered = datetime.now(tz=UTC)
    try:
        with source_path.open("rb") as handle:
            header = handle.read(64)
    except OSError:
        return DumpQuarantineResult(
            disposition=Disposition.QUARANTINED,
            dump_kind="unknown",
            sha256=None,
            byte_size=None,
            quarantine_path=None,
            discovered_at=discovered,
            reason_code="dump_source_unreadable",
        )

    kind = recognize_dump_kind(header)
    reason = "process_dump_quarantined" if kind != "unknown" else "unrecognized_dump_magic"

    try:
        digest, byte_size = _stream_sha256(source_path)
    except OSError:
        return DumpQuarantineResult(
            disposition=Disposition.QUARANTINED,
            dump_kind=kind,
            sha256=None,
            byte_size=None,
            quarantine_path=None,
            discovered_at=discovered,
            reason_code="dump_hash_failed",
        )

    source_resolved = source_path.resolve()
    quarantine_resolved = quarantine_root.resolve()
    if _is_under(source_resolved, quarantine_resolved):
        try:
            verify_restrictive_permissions(source_resolved)
        except PrivateFileError:
            # Already-quarantined retention still reports hash metadata.
            pass
        return DumpQuarantineResult(
            disposition=Disposition.QUARANTINED,
            dump_kind=kind,
            sha256=digest,
            byte_size=byte_size,
            quarantine_path=source_resolved,
            discovered_at=discovered,
            reason_code=reason,
        )

    try:
        if _filesystem_device_id(source_path) != _filesystem_device_id(quarantine_root):
            return DumpQuarantineResult(
                disposition=Disposition.QUARANTINED,
                dump_kind=kind,
                sha256=digest,
                byte_size=byte_size,
                quarantine_path=None,
                discovered_at=discovered,
                reason_code="cross_filesystem_rename_rejected",
            )
    except OSError:
        return DumpQuarantineResult(
            disposition=Disposition.QUARANTINED,
            dump_kind=kind,
            sha256=digest,
            byte_size=byte_size,
            quarantine_path=None,
            discovered_at=discovered,
            reason_code="cross_filesystem_rename_rejected",
        )

    dest = quarantine_resolved / f"process_dump-{uuid.uuid4().hex}.bin"
    try:
        atomic_replace_same_filesystem(source_path, dest)
        apply_restrictive_permissions(dest)
    except PrivateFileError as exc:
        code = getattr(exc, "code", "quarantine_move_failed")
        return DumpQuarantineResult(
            disposition=Disposition.QUARANTINED,
            dump_kind=kind,
            sha256=digest,
            byte_size=byte_size,
            quarantine_path=None,
            discovered_at=discovered,
            reason_code=code if code == "cross_filesystem_rename_rejected" else "quarantine_move_failed",
        )

    return DumpQuarantineResult(
        disposition=Disposition.QUARANTINED,
        dump_kind=kind,
        sha256=digest,
        byte_size=byte_size,
        quarantine_path=dest,
        discovered_at=discovered,
        reason_code=reason,
    )
