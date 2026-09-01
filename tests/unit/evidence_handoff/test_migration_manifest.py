"""Migration manifest digest immutability."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_migration_manifest_pins_digests_for_committed_sql() -> None:
    from evidence_handoff_runtime.migrations import MIGRATIONS_ROOT, MigrationManifest

    manifest = MigrationManifest.load()
    assert MIGRATIONS_ROOT.is_dir()
    assert manifest.entries, "at least one migration must be registered"
    for entry in manifest.entries:
        path = MIGRATIONS_ROOT / entry.filename
        assert path.is_file()
        assert entry.sha256 == MigrationManifest.digest_file(path)
        assert len(entry.sha256) == 64


def test_migration_manifest_detects_tampered_sql(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from evidence_handoff_runtime import migrations as migrations_mod
    from evidence_handoff_runtime.migrations import MigrationEntry, MigrationError, MigrationManifest

    real_root = migrations_mod.MIGRATIONS_ROOT
    assert real_root.is_dir()
    src = real_root / MigrationManifest.load().entries[0].filename
    dest_root = tmp_path / "migrations"
    dest_root.mkdir()
    dest = dest_root / src.name
    dest.write_text(src.read_text(encoding="utf-8") + "\n-- tampered\n", encoding="utf-8")
    monkeypatch.setattr(migrations_mod, "MIGRATIONS_ROOT", dest_root)
    original = MigrationManifest.digest_file(src)
    fake = MigrationManifest(entries=(MigrationEntry(filename=src.name, sha256=original),))
    with pytest.raises(MigrationError) as raised:
        fake.verify()
    assert raised.value.code == "migration_digest_mismatch"


def test_digest_file_stable_across_crlf_and_lf(tmp_path: Path) -> None:
    """Pinned digests must match git text=auto LF blobs, not local CRLF checkouts."""
    from evidence_handoff_runtime.migrations import MigrationManifest

    sql_lf = b"-- sample migration\nSELECT 1;\n"
    sql_crlf = sql_lf.replace(b"\n", b"\r\n")
    assert b"\r\n" in sql_crlf
    assert b"\r" not in sql_lf

    lf_path = tmp_path / "lf.sql"
    crlf_path = tmp_path / "crlf.sql"
    lf_path.write_bytes(sql_lf)
    crlf_path.write_bytes(sql_crlf)

    lf_digest = MigrationManifest.digest_file(lf_path)
    crlf_digest = MigrationManifest.digest_file(crlf_path)
    assert lf_digest == crlf_digest
    assert len(lf_digest) == 64

    changed = tmp_path / "changed.sql"
    changed.write_bytes(sql_lf + b"-- different\n")
    assert MigrationManifest.digest_file(changed) != lf_digest
