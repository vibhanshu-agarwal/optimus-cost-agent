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
    src = sorted(real_root.glob("*.sql"))[0]
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
