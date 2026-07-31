"""RED/GREEN unit tests for private staging filesystem primitives."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest


def _pf():
    from evidence_handoff.redaction import private_files

    return private_files


def test_create_private_staging_file_uses_role_based_name(tmp_path: Path) -> None:
    pf = _pf()
    staging = tmp_path / "staging"
    staging.mkdir()
    handle = pf.create_private_staging_file(staging_root=staging.resolve(), artifact_role="acp_debug_trace")
    assert handle.path.parent == staging.resolve()
    assert "acp_debug_trace" in handle.path.name
    assert ".." not in handle.path.name
    assert handle.path.exists()
    handle.close()


def test_rejects_symlink_parent_escape(tmp_path: Path) -> None:
    pf = _pf()
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    # Pass the unresolved symlink path — resolve() would follow and hide the escape.
    with pytest.raises(pf.PrivateFileError, match="symlink_component_rejected"):
        pf.create_private_staging_file(staging_root=link, artifact_role="session_note")


@pytest.mark.skipif(sys.platform != "win32", reason="NTFS junctions are Windows-specific")
def test_rejects_junction_parent_escape(tmp_path: Path) -> None:
    """Junctions are not Path.is_symlink(); reparse-aware rejection is mandatory."""
    pf = _pf()
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    _create_ntfs_junction(link, real)
    # Empirically pin the host gap this test exists to close.
    assert link.is_symlink() is False
    assert link.is_dir() is True
    st = os.lstat(link)
    assert int(getattr(st, "st_file_attributes", 0)) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    with pytest.raises(pf.PrivateFileError, match="symlink_component_rejected"):
        pf.create_private_staging_file(staging_root=link, artifact_role="session_note")


def _create_ntfs_junction(link: Path, target: Path) -> None:
    """Create a real NTFS junction (not a symlink) at link → target."""
    try:
        import _winapi

        create = getattr(_winapi, "CreateJunction", None)
        if create is not None:
            create(str(target), str(link))
            if link.exists():
                return
    except (ImportError, OSError):
        pass
    import subprocess

    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not link.exists():
        pytest.skip(f"junction unavailable: rc={result.returncode} {result.stdout} {result.stderr}")


def test_rejects_source_destination_overlap(tmp_path: Path) -> None:
    pf = _pf()
    dest = (tmp_path / "dest").resolve()
    dest.mkdir()
    nested = dest / "staging"
    nested.mkdir()
    with pytest.raises(pf.PrivateFileError, match="staging_under_destination"):
        pf.validate_root_placement(
            nested,
            role="staging",
            destination_root=dest,
            forbidden_roots=(),
        )


def test_rejects_path_under_forbidden_root(tmp_path: Path) -> None:
    pf = _pf()
    forbidden = (tmp_path / "cloud").resolve()
    forbidden.mkdir()
    staging = forbidden / "staging"
    staging.mkdir()
    with pytest.raises(pf.PrivateFileError, match="path_under_forbidden_root"):
        pf.validate_root_placement(
            staging,
            role="staging",
            destination_root=(tmp_path / "dest").resolve(),
            forbidden_roots=(forbidden,),
        )


def test_same_filesystem_atomic_replace(tmp_path: Path) -> None:
    pf = _pf()
    staging = tmp_path / "staging"
    dest_root = tmp_path / "dest"
    staging.mkdir()
    dest_root.mkdir()
    handle = pf.create_private_staging_file(staging_root=staging.resolve(), artifact_role="screenshot_v1")
    handle.path.write_text("sanitized", encoding="utf-8")
    handle.close()
    destination = dest_root / "screenshot_v1.png"
    pf.atomic_replace_same_filesystem(handle.path, destination)
    assert destination.read_text(encoding="utf-8") == "sanitized"
    assert not handle.path.exists()


def test_cross_filesystem_rename_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pf = _pf()
    src = tmp_path / "a.txt"
    dst = tmp_path / "b.txt"
    src.write_text("x", encoding="utf-8")
    monkeypatch.setattr(pf, "_filesystem_device_id", lambda path: 1 if path == src else 2)
    with pytest.raises(pf.PrivateFileError, match="cross_filesystem_rename_rejected"):
        pf.atomic_replace_same_filesystem(src, dst)


def test_cleanup_removes_partial_staging(tmp_path: Path) -> None:
    pf = _pf()
    staging = tmp_path / "staging"
    staging.mkdir()
    handle = pf.create_private_staging_file(staging_root=staging.resolve(), artifact_role="session_note")
    path = handle.path
    handle.close()
    pf.cleanup_private_path(path)
    assert not path.exists()


def test_quarantine_partial_staging_moves_file(tmp_path: Path) -> None:
    pf = _pf()
    staging = tmp_path / "staging"
    quarantine = tmp_path / "quarantine"
    staging.mkdir()
    quarantine.mkdir()
    handle = pf.create_private_staging_file(staging_root=staging.resolve(), artifact_role="session_note")
    handle.path.write_text("partial", encoding="utf-8")
    handle.close()
    moved = pf.quarantine_partial_staging(handle.path, quarantine_root=quarantine.resolve())
    assert moved.parent == quarantine.resolve()
    assert moved.exists()
    assert not handle.path.exists()


def test_generated_filename_rejects_unsafe_role(tmp_path: Path) -> None:
    pf = _pf()
    staging = (tmp_path / "staging").resolve()
    staging.mkdir()
    with pytest.raises(pf.PrivateFileError, match="unsafe_artifact_role"):
        pf.create_private_staging_file(staging_root=staging, artifact_role="../etc/passwd")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits checked on POSIX hosts")
def test_posix_modes_after_create(tmp_path: Path) -> None:
    pf = _pf()
    staging = (tmp_path / "staging").resolve()
    staging.mkdir()
    directory = pf.create_private_directory(staging / "locked")
    mode = stat.S_IMODE(directory.stat().st_mode)
    assert mode == 0o700
    handle = pf.create_private_staging_file(staging_root=staging, artifact_role="session_note")
    file_mode = stat.S_IMODE(handle.path.stat().st_mode)
    assert file_mode == 0o600
    handle.close()
