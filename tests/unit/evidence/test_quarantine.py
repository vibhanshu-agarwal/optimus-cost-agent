"""RED/GREEN unit tests for hash-only process-dump quarantine."""

from __future__ import annotations

import hashlib
import struct
from datetime import datetime
from pathlib import Path

import pytest

from evidence_handoff.redaction.models import Disposition


def _quarantine():
    from evidence_handoff.redaction import quarantine as quarantine_mod

    return quarantine_mod


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    capture = tmp_path / "cap"
    quarantine = tmp_path / "quarantine"
    capture.mkdir()
    quarantine.mkdir()
    return capture, quarantine


def _elf_core(*, big_endian: bool) -> bytes:
    # Minimal ELF header with ET_CORE (4).
    ident = bytearray(16)
    ident[0:4] = b"\x7fELF"
    ident[4] = 1  # ELFCLASS32
    ident[5] = 2 if big_endian else 1  # EI_DATA
    ident[6] = 1  # EV_CURRENT
    header = bytearray(ident)
    # e_type at offset 16
    if big_endian:
        header += struct.pack(">H", 4)  # ET_CORE
        header += struct.pack(">H", 0)  # e_machine
        header += struct.pack(">I", 1)  # e_version
    else:
        header += struct.pack("<H", 4)
        header += struct.pack("<H", 0)
        header += struct.pack("<I", 1)
    header += b"\x00" * (64 - len(header))
    return bytes(header)


def test_recognizes_windows_minidump(tmp_path: Path) -> None:
    q = _quarantine()
    capture, quarantine = _setup(tmp_path)
    source = capture / "crash.dmp"
    body = b"MDMP" + b"\x00" * 128
    source.write_bytes(body)
    result = q.quarantine_process_dump(source_path=source, quarantine_root=quarantine)
    assert result.disposition is Disposition.QUARANTINED
    assert result.dump_kind == "windows_minidump"
    assert result.sha256 == hashlib.sha256(body).hexdigest()
    assert result.byte_size == len(body)
    assert result.quarantine_path is not None
    assert result.quarantine_path.exists()
    assert not source.exists()
    assert isinstance(result.discovered_at, datetime)
    assert result.discovered_at.tzinfo is not None


def test_recognizes_elf_core_both_endians(tmp_path: Path) -> None:
    q = _quarantine()
    capture, quarantine = _setup(tmp_path)
    for big, name in ((False, "le"), (True, "be")):
        source = capture / f"core-{name}"
        body = _elf_core(big_endian=big) + b"\x00" * 32
        source.write_bytes(body)
        result = q.quarantine_process_dump(source_path=source, quarantine_root=quarantine)
        assert result.dump_kind == "elf_core"
        assert result.sha256 == hashlib.sha256(body).hexdigest()
        assert not source.exists()


def test_unknown_magic_still_hash_quarantines(tmp_path: Path) -> None:
    q = _quarantine()
    capture, quarantine = _setup(tmp_path)
    source = capture / "mystery.bin"
    body = b"NOTA" + b"\x01" * 64
    source.write_bytes(body)
    result = q.quarantine_process_dump(source_path=source, quarantine_root=quarantine)
    assert result.disposition is Disposition.QUARANTINED
    assert result.dump_kind == "unknown"
    assert result.reason_code == "unrecognized_dump_magic"
    assert result.sha256 == hashlib.sha256(body).hexdigest()


def test_already_quarantined_retained(tmp_path: Path) -> None:
    q = _quarantine()
    _, quarantine = _setup(tmp_path)
    source = quarantine / "already.dmp"
    body = b"MDMP" + b"\x02" * 40
    source.write_bytes(body)
    result = q.quarantine_process_dump(source_path=source, quarantine_root=quarantine)
    assert result.quarantine_path == source.resolve()
    assert source.exists()
    assert result.sha256 == hashlib.sha256(body).hexdigest()


def test_cross_filesystem_refuses_without_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    q = _quarantine()
    capture, quarantine = _setup(tmp_path)
    source = capture / "crash.dmp"
    source.write_bytes(b"MDMP" + b"\x00" * 20)
    monkeypatch.setattr(q, "_filesystem_device_id", lambda path: 1 if "cap" in str(path) else 2)
    result = q.quarantine_process_dump(source_path=source, quarantine_root=quarantine)
    assert result.disposition is Disposition.QUARANTINED
    assert result.reason_code == "cross_filesystem_rename_rejected"
    assert source.exists()  # must not copy-away on failure
    assert result.quarantine_path is None


def test_restrictive_permissions_on_quarantined_file(tmp_path: Path) -> None:
    q = _quarantine()
    capture, quarantine = _setup(tmp_path)
    source = capture / "crash.dmp"
    source.write_bytes(b"MDMP" + b"\x00" * 20)
    result = q.quarantine_process_dump(source_path=source, quarantine_root=quarantine)
    assert result.quarantine_path is not None
    from evidence_handoff.redaction.private_files import verify_restrictive_permissions

    verify_restrictive_permissions(result.quarantine_path)


def test_hash_only_record_has_no_body_fields(tmp_path: Path) -> None:
    q = _quarantine()
    capture, quarantine = _setup(tmp_path)
    source = capture / "crash.dmp"
    body = b"MDMP" + b"secret-should-not-appear-in-repr"
    source.write_bytes(body)
    result = q.quarantine_process_dump(source_path=source, quarantine_root=quarantine)
    rendered = repr(result) + str(result)
    assert b"secret-should-not-appear-in-repr".decode() not in rendered
    assert not hasattr(result, "body")
    assert not hasattr(result, "contents")


def test_no_promotion_api_for_dumps() -> None:
    q = _quarantine()
    assert not hasattr(q, "promote_process_dump")
    assert not hasattr(q, "promote_dump")
    assert not any(name.startswith("promote") for name in dir(q) if not name.startswith("_"))
