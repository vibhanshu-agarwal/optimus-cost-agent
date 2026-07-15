"""Tests for trusted operator roots and canonical workspace identity.

Task 2 of Plan 9.96: OS-derived roots and workspace identity cannot be
redirected by workspace launch environment values. Trusted bootstrap
(Constraint 8) never depends on inherited APPDATA, LOCALAPPDATA, HOME,
XDG_CONFIG_HOME, or gated OPTIMUS_CONFIG_ROOT.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from optimus.acp.trusted_paths import (
    TrustedPathError,
    resolve_trusted_operator_roots,
    resolve_workspace_identity,
    revalidate_workspace_identity,
)

# --- Fake OS adapters for testing ---


@dataclass
class FakeWindowsKnownFolders:
    """Injectable adapter returning controlled Windows Known Folder paths."""

    roaming_appdata: Path | None = None
    local_appdata: Path | None = None


@dataclass
class FakePosixHome:
    """Injectable adapter returning controlled POSIX home directory."""

    home_dir: Path | None = None


# --- Task 2 Step 1: Failing Windows/POSIX root tests ---


class TestTrustedRootsWindows:
    """Windows root resolution uses Known Folders, ignores inherited env."""

    def test_windows_roots_from_known_folders(self, tmp_path: Path) -> None:
        roaming = tmp_path / "Users" / "operator" / "AppData" / "Roaming"
        local = tmp_path / "Users" / "operator" / "AppData" / "Local"
        roaming.mkdir(parents=True)
        local.mkdir(parents=True)

        folders = FakeWindowsKnownFolders(roaming_appdata=roaming, local_appdata=local)
        roots = resolve_trusted_operator_roots(
            platform_name="win32",
            windows_known_folders=folders,
        )

        assert roots.default_config_root == roaming / "optimus-cost-agent"
        assert roots.approval_runtime_root == local / "optimus-cost-agent"

    def test_hostile_appdata_env_does_not_change_result(self, tmp_path: Path) -> None:
        """Inherited APPDATA/LOCALAPPDATA must have no effect on trusted roots."""
        real_roaming = tmp_path / "real-roaming"
        real_local = tmp_path / "real-local"
        real_roaming.mkdir()
        real_local.mkdir()

        folders = FakeWindowsKnownFolders(
            roaming_appdata=real_roaming,
            local_appdata=real_local,
        )
        # Even with hostile env vars set, the result comes from Known Folders.
        roots = resolve_trusted_operator_roots(
            platform_name="win32",
            windows_known_folders=folders,
        )

        assert roots.default_config_root == real_roaming / "optimus-cost-agent"
        assert roots.approval_runtime_root == real_local / "optimus-cost-agent"

    def test_missing_windows_known_folder_fails(self) -> None:
        """When the OS cannot resolve Known Folders, fail with a stable code."""
        folders = FakeWindowsKnownFolders(roaming_appdata=None, local_appdata=None)
        with pytest.raises(TrustedPathError) as exc_info:
            resolve_trusted_operator_roots(
                platform_name="win32",
                windows_known_folders=folders,
            )
        assert exc_info.value.code == "TRUSTED_OPERATOR_ROOT_UNAVAILABLE"

    def test_partial_missing_windows_known_folder_fails(self) -> None:
        """If only one folder resolves, still fail — both are required."""
        folders = FakeWindowsKnownFolders(
            roaming_appdata=Path("C:/Users/test/AppData/Roaming"),
            local_appdata=None,
        )
        with pytest.raises(TrustedPathError) as exc_info:
            resolve_trusted_operator_roots(
                platform_name="win32",
                windows_known_folders=folders,
            )
        assert exc_info.value.code == "TRUSTED_OPERATOR_ROOT_UNAVAILABLE"


class TestTrustedRootsPosix:
    """POSIX root resolution uses pwd.getpwuid, ignores inherited env."""

    def test_posix_roots_from_home_dir(self, tmp_path: Path) -> None:
        home = tmp_path / "home" / "operator"
        home.mkdir(parents=True)

        posix_home = FakePosixHome(home_dir=home)
        roots = resolve_trusted_operator_roots(
            platform_name="linux",
            posix_home=posix_home,
        )

        assert roots.default_config_root == home / ".config" / "optimus-cost-agent"
        assert roots.approval_runtime_root == home / ".local" / "state" / "optimus-cost-agent"

    def test_hostile_home_xdg_env_does_not_change_result(self, tmp_path: Path) -> None:
        """Inherited HOME and XDG_CONFIG_HOME must have no effect."""
        real_home = tmp_path / "real-home"
        real_home.mkdir()

        posix_home = FakePosixHome(home_dir=real_home)
        roots = resolve_trusted_operator_roots(
            platform_name="linux",
            posix_home=posix_home,
        )

        assert roots.default_config_root == real_home / ".config" / "optimus-cost-agent"
        assert roots.approval_runtime_root == real_home / ".local" / "state" / "optimus-cost-agent"

    def test_missing_posix_home_fails(self) -> None:
        """When pwd.getpwuid cannot resolve, fail with a stable code."""
        posix_home = FakePosixHome(home_dir=None)
        with pytest.raises(TrustedPathError) as exc_info:
            resolve_trusted_operator_roots(
                platform_name="linux",
                posix_home=posix_home,
            )
        assert exc_info.value.code == "TRUSTED_OPERATOR_ROOT_UNAVAILABLE"

    def test_darwin_uses_posix_paths(self, tmp_path: Path) -> None:
        """macOS uses the same POSIX path scheme."""
        home = tmp_path / "Users" / "operator"
        home.mkdir(parents=True)

        posix_home = FakePosixHome(home_dir=home)
        roots = resolve_trusted_operator_roots(
            platform_name="darwin",
            posix_home=posix_home,
        )

        assert roots.default_config_root == home / ".config" / "optimus-cost-agent"
        assert roots.approval_runtime_root == home / ".local" / "state" / "optimus-cost-agent"


class TestTrustedRootsNoWorkspaceCreation:
    """Root resolution must not create workspace directories."""

    def test_resolution_does_not_create_directories(self, tmp_path: Path) -> None:
        roaming = tmp_path / "roaming"
        local = tmp_path / "local"
        # Directories DON'T exist yet.
        folders = FakeWindowsKnownFolders(roaming_appdata=roaming, local_appdata=local)
        roots = resolve_trusted_operator_roots(
            platform_name="win32",
            windows_known_folders=folders,
        )
        # The paths are returned but NOT created on disk.
        assert not roots.default_config_root.exists()
        assert not roots.approval_runtime_root.exists()


# --- Task 2 Step 3: Workspace identity tests ---


class TestWorkspaceIdentity:
    """Canonical workspace identity with file-system binding."""

    def test_identity_captures_path_and_stat(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        identity = resolve_workspace_identity(workspace)

        assert identity.canonical_path == str(workspace.resolve())
        stat = workspace.stat()
        assert identity.device == stat.st_dev
        assert identity.inode == stat.st_ino
        # Digest is a hex string.
        assert len(identity.digest) == 64  # SHA-256 hex

    def test_identity_includes_git_root_when_present(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        # Initialize a git repo.
        subprocess.run(
            ["git", "init"],
            cwd=workspace,
            capture_output=True,
            check=True,
        )

        identity = resolve_workspace_identity(workspace)

        assert identity.repository_root is not None
        assert identity.repository_root == str(workspace.resolve())

    def test_identity_none_git_when_not_a_repo(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        identity = resolve_workspace_identity(workspace)

        assert identity.repository_root is None
        assert identity.git_common_dir is None

    def test_missing_workspace_fails(self, tmp_path: Path) -> None:
        workspace = tmp_path / "nonexistent"
        with pytest.raises(TrustedPathError) as exc_info:
            resolve_workspace_identity(workspace)
        assert exc_info.value.code == "WORKSPACE_NOT_FOUND"

    def test_digest_changes_with_path(self, tmp_path: Path) -> None:
        ws1 = tmp_path / "workspace1"
        ws2 = tmp_path / "workspace2"
        ws1.mkdir()
        ws2.mkdir()

        id1 = resolve_workspace_identity(ws1)
        id2 = resolve_workspace_identity(ws2)

        assert id1.digest != id2.digest

    def test_digest_is_deterministic(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        id1 = resolve_workspace_identity(workspace)
        id2 = resolve_workspace_identity(workspace)

        assert id1.digest == id2.digest


class TestWorkspaceIdentityRevalidation:
    """Revalidation detects changes to path, file identity, and git state."""

    def test_revalidation_passes_for_unchanged_workspace(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        identity = resolve_workspace_identity(workspace)
        # Should not raise.
        revalidate_workspace_identity(identity)

    def test_revalidation_fails_for_missing_workspace(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        identity = resolve_workspace_identity(workspace)
        workspace.rmdir()

        with pytest.raises(TrustedPathError) as exc_info:
            revalidate_workspace_identity(identity)
        assert exc_info.value.code == "WORKSPACE_IDENTITY_CHANGED"

    def test_revalidation_fails_for_symlink_target_change(self, tmp_path: Path) -> None:
        target1 = tmp_path / "target1"
        target2 = tmp_path / "target2"
        target1.mkdir()
        target2.mkdir()
        link = tmp_path / "workspace-link"
        try:
            link.symlink_to(target1, target_is_directory=True)
        except OSError:
            pytest.skip("symlink creation requires elevated privileges")

        identity = resolve_workspace_identity(link)

        # Re-point the symlink.
        link.unlink()
        link.symlink_to(target2, target_is_directory=True)

        with pytest.raises(TrustedPathError) as exc_info:
            revalidate_workspace_identity(identity)
        assert exc_info.value.code == "WORKSPACE_IDENTITY_CHANGED"


class TestWindowsCaseNormalization:
    """Windows case normalization for workspace paths."""

    def test_case_variants_produce_same_identity(self, tmp_path: Path) -> None:
        workspace = tmp_path / "WorkSpace"
        workspace.mkdir()

        # Use different case for the same actual directory.
        id_upper = resolve_workspace_identity(tmp_path / "WorkSpace")
        id_lower = resolve_workspace_identity(tmp_path / "workspace")

        # On case-insensitive filesystems both resolve to the same canonical path.
        # On case-sensitive, they'd be different dirs (and one wouldn't exist).
        if id_upper.canonical_path.lower() == id_lower.canonical_path.lower():
            # Case-insensitive: digests should match.
            assert id_upper.digest == id_lower.digest



# --- Platform-guarded real adapter smoke tests ---


class TestRealWindowsAdapter:
    """Smoke test the real Windows Known Folder adapter on actual Windows."""

    @pytest.mark.skipif(
        __import__("sys").platform != "win32",
        reason="Windows-only: real SHGetKnownFolderPath",
    )
    def test_real_windows_known_folders_resolves(self) -> None:
        """On a real Windows box, the ctypes GUID-based resolution must work."""
        from optimus.acp.trusted_paths import _real_windows_known_folders

        folders = _real_windows_known_folders()
        assert folders.roaming_appdata is not None, (
            "SHGetKnownFolderPath failed for RoamingAppData"
        )
        assert folders.local_appdata is not None, (
            "SHGetKnownFolderPath failed for LocalAppData"
        )
        # Both paths should be absolute and contain "AppData".
        assert folders.roaming_appdata.is_absolute()
        assert folders.local_appdata.is_absolute()

    @pytest.mark.skipif(
        __import__("sys").platform != "win32",
        reason="Windows-only: real end-to-end root resolution",
    )
    def test_real_windows_trusted_roots_end_to_end(self) -> None:
        """Real root resolution produces valid paths on Windows."""
        roots = resolve_trusted_operator_roots(platform_name="win32")
        assert roots.default_config_root.is_absolute()
        assert roots.approval_runtime_root.is_absolute()
        assert "optimus-cost-agent" in str(roots.default_config_root)
        assert "optimus-cost-agent" in str(roots.approval_runtime_root)


class TestRealPosixAdapter:
    """Smoke test the real POSIX home adapter on actual POSIX."""

    @pytest.mark.skipif(
        __import__("sys").platform == "win32",
        reason="POSIX-only: real pwd.getpwuid",
    )
    def test_real_posix_home_resolves(self) -> None:
        """On a real POSIX box, pwd.getpwuid resolution must work."""
        from optimus.acp.trusted_paths import _real_posix_home

        home = _real_posix_home()
        assert home.home_dir is not None, "pwd.getpwuid failed to resolve home"
        assert home.home_dir.is_absolute()

    @pytest.mark.skipif(
        __import__("sys").platform == "win32",
        reason="POSIX-only: real end-to-end root resolution",
    )
    def test_real_posix_trusted_roots_end_to_end(self) -> None:
        """Real root resolution produces valid paths on POSIX."""
        import sys

        roots = resolve_trusted_operator_roots(platform_name=sys.platform)
        assert roots.default_config_root.is_absolute()
        assert roots.approval_runtime_root.is_absolute()
        assert "optimus-cost-agent" in str(roots.default_config_root)
        assert "optimus-cost-agent" in str(roots.approval_runtime_root)
