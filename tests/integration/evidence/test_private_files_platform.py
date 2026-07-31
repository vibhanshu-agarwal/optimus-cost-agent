"""Real-host permission evidence for private staging primitives."""

from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest


def _pf():
    from evidence_handoff.redaction import private_files

    return private_files


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits are host-specific")
def test_posix_private_modes_are_restrictive(tmp_path: Path) -> None:
    pf = _pf()
    staging = tmp_path / "staging"
    staging.mkdir()
    directory = pf.create_private_directory(staging / "locked")
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    handle = pf.create_private_staging_file(staging_root=staging.resolve(), artifact_role="session_note")
    try:
        assert stat.S_IMODE(handle.path.stat().st_mode) == 0o600
        pf.verify_restrictive_permissions(handle.path)
        pf.verify_restrictive_permissions(directory)
    finally:
        handle.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DACL evidence is host-specific")
def test_windows_private_dacl_is_restrictive(tmp_path: Path) -> None:
    pf = _pf()
    staging = tmp_path / "staging"
    quarantine = tmp_path / "quarantine"
    staging.mkdir()
    quarantine.mkdir()
    directory = pf.create_private_directory(staging / "locked")
    handle = pf.create_private_staging_file(staging_root=staging.resolve(), artifact_role="acp_debug_trace")
    try:
        pf.verify_restrictive_permissions(handle.path)
        pf.verify_restrictive_permissions(directory)
        allowed = pf.enumerate_allowed_windows_sids(handle.path)
        # Content-free: only well-known / current-user principals, never raw path bodies.
        assert allowed
        assert all(isinstance(sid, str) and sid.startswith("S-1-") for sid in allowed)
    finally:
        handle.close()
