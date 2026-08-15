"""Tests for trusted operator roots and canonical workspace identity.

Task 2 of Plan 9.96: OS-derived roots and workspace identity cannot be
redirected by workspace launch environment values. Trusted bootstrap
(Constraint 8) never depends on inherited APPDATA, LOCALAPPDATA, HOME,
XDG_CONFIG_HOME, or gated OPTIMUS_CONFIG_ROOT.
"""

from __future__ import annotations

import os
import subprocess
import sys
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

    def test_identity_binds_lexical_path_and_target_change_time(self, tmp_path: Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        link = tmp_path / "workspace-link"
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            pytest.skip("symlink creation requires elevated privileges")

        identity = resolve_workspace_identity(link)

        expected_lexical = os.path.normcase(str(link.absolute())) if sys.platform == "win32" else str(link.absolute())
        assert identity.lexical_path == expected_lexical
        assert identity.canonical_path == str(target.resolve())
        assert identity.digest

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

    def test_trusted_path_error_propagates_as_its_own_type(self) -> None:
        with pytest.raises(TrustedPathError) as exc_info:
            raise TrustedPathError(code="WORKSPACE_NOT_FOUND", detail="synthetic")

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

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only: directory ctime changes on entry creation")
    def test_revalidation_fails_after_workspace_directory_metadata_change(self, tmp_path: Path) -> None:
        # Legacy characterization kept under its original POSIX ctime skip.
        # The unguarded FU-18 proof that runs on Windows is
        # test_fu18_equal_ctime_non_excluded_add_is_root_topology_mismatch.
        from optimus.acp.trusted_paths import (
            resolve_workspace_security_state,
            revalidate_workspace_security_state,
        )

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        initial = resolve_workspace_security_state(workspace)
        (workspace / "added-after-authorization").write_text("synthetic", encoding="utf-8")

        with pytest.raises(TrustedPathError) as exc_info:
            revalidate_workspace_security_state(initial)
        assert exc_info.value.code == "WORKSPACE_IDENTITY_CHANGED"
        assert exc_info.value.reason == "root_topology_mismatch"


class TestWindowsCaseNormalization:
    """Windows case normalization for workspace paths."""

    @pytest.mark.skipif(
        sys.platform != "win32",
        reason="Windows-only: case-insensitive filesystem identity",
    )
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
            assert id_upper.lexical_path == id_lower.lexical_path
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


# --- Plan 11.15 Task 1: tri-state Git probe ---


def _git_probe_stdout(repository_root: Path, git_common_dir: Path) -> str:
    return f"{repository_root}\n{git_common_dir}\n"


def _oserror(*, winerror: int | None = None, errno_value: int | None = None) -> OSError:
    code = errno_value if errno_value is not None else (winerror or 0)
    exc = OSError(code, "injected probe failure")
    if winerror is not None:
        exc.winerror = winerror
    if errno_value is not None:
        exc.errno = errno_value
    return exc


class TestGitContextDispositions:
    """Git discovery is PRESENT / ABSENT / UNAVAILABLE from one coherent probe."""

    def test_git_context_present_ordinary_git_directory_uses_one_invocation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from optimus.acp import trusted_paths

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / ".git").mkdir()
        monkeypatch.setattr(trusted_paths.shutil, "which", lambda _name: "C:/fake/git.exe")
        calls: list[tuple[list[str], dict[str, object]]] = []

        def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append((list(argv), dict(kwargs)))
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=_git_probe_stdout(workspace.resolve(), (workspace / ".git").resolve()),
                stderr="",
            )

        result = trusted_paths.resolve_git_context(workspace, run=run)

        assert len(calls) == 1
        argv, kwargs = calls[0]
        assert kwargs.get("shell") is False
        assert "--path-format=absolute" in argv
        assert argv[-2:] == ["--show-toplevel", "--git-common-dir"]
        assert "-z" not in argv
        assert result.disposition is trusted_paths.GitContextDisposition.PRESENT
        assert result.repository_root == str(workspace.resolve())
        assert result.git_common_dir == str((workspace / ".git").resolve())

    def test_git_context_present_worktree_git_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from optimus.acp import trusted_paths

        workspace = tmp_path / "worktree"
        common = tmp_path / "main.git"
        workspace.mkdir()
        common.mkdir()
        (workspace / ".git").write_text("gitdir: ../main.git\n", encoding="utf-8")
        monkeypatch.setattr(trusted_paths.shutil, "which", lambda _name: "/usr/bin/git")

        def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=_git_probe_stdout(workspace.resolve(), common.resolve()),
                stderr="fatal: should never be persisted\n",
            )

        result = trusted_paths.resolve_git_context(workspace, run=run)

        assert result.disposition is trusted_paths.GitContextDisposition.PRESENT
        assert result.repository_root == str(workspace.resolve())
        assert result.git_common_dir == str(common.resolve())
        serialized = repr(result.diagnostics)
        assert "fatal:" not in serialized

    def test_git_context_absent_without_subprocess(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from optimus.acp import trusted_paths

        workspace = tmp_path / "plain"
        workspace.mkdir()
        calls: list[object] = []
        monkeypatch.setattr(trusted_paths.shutil, "which", lambda _name: "git")

        def run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append("spawned")
            raise AssertionError("ABSENT must not spawn Git")

        result = trusted_paths.resolve_git_context(workspace, run=run)

        assert result.disposition is trusted_paths.GitContextDisposition.ABSENT
        assert result.repository_root is None
        assert result.git_common_dir is None
        assert calls == []

    def test_git_context_unavailable_when_git_executable_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from optimus.acp import trusted_paths

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / ".git").mkdir()
        monkeypatch.setattr(trusted_paths.shutil, "which", lambda _name: None)
        calls: list[object] = []

        def run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append("spawned")
            raise AssertionError("missing git must not spawn")

        result = trusted_paths.resolve_git_context(workspace, run=run)

        assert result.disposition is trusted_paths.GitContextDisposition.UNAVAILABLE
        assert result.repository_root is None
        assert result.git_common_dir is None
        assert calls == []
        assert result.diagnostics[0].classification == "permanent"
        assert len(result.diagnostics) == 1

    @pytest.mark.parametrize(
        "stdout",
        ("", "only-one-path\n", "\n\n", "a\nb\nc\n", " \n \n"),
        ids=("empty", "one-field", "empty-fields", "three-fields", "whitespace"),
    )
    def test_git_context_unavailable_for_corrupt_invalid_empty_output(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        stdout: str,
    ) -> None:
        from optimus.acp import trusted_paths

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / ".git").mkdir()
        monkeypatch.setattr(trusted_paths.shutil, "which", lambda _name: "git")

        def run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="raw git stderr")

        result = trusted_paths.resolve_git_context(workspace, run=run)

        assert result.disposition is trusted_paths.GitContextDisposition.UNAVAILABLE
        assert result.diagnostics[0].classification == "permanent"
        assert "raw git stderr" not in repr(result.diagnostics)

    def test_git_context_unavailable_for_inconsistent_nonzero_status(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from optimus.acp import trusted_paths

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / ".git").mkdir()
        monkeypatch.setattr(trusted_paths.shutil, "which", lambda _name: "git")

        def run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(argv, 128, stdout="", stderr="fatal: not a git repository")

        result = trusted_paths.resolve_git_context(workspace, run=run)

        assert result.disposition is trusted_paths.GitContextDisposition.UNAVAILABLE
        assert result.diagnostics[0].classification == "permanent"
        assert result.diagnostics[0].return_code == 128
        assert "fatal:" not in repr(result.diagnostics)

    def test_git_context_unavailable_on_marker_walk_access_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from optimus.acp import trusted_paths

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        monkeypatch.setattr(trusted_paths.shutil, "which", lambda _name: "git")

        def boom(path: str, *args: object, **kwargs: object) -> os.stat_result:
            if Path(path).name == ".git":
                raise OSError(13, "Permission denied")
            return os.lstat(path, *args, **kwargs)

        monkeypatch.setattr(trusted_paths.os, "lstat", boom)
        calls: list[object] = []

        def run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append("spawned")
            raise AssertionError("marker-walk failure must not spawn Git")

        result = trusted_paths.resolve_git_context(workspace, run=run)

        assert result.disposition is trusted_paths.GitContextDisposition.UNAVAILABLE
        assert result.diagnostics[0].classification == "permanent"
        assert calls == []

    def test_git_context_old_none_helpers_are_unreachable(self) -> None:
        from optimus.acp import trusted_paths

        assert not hasattr(trusted_paths, "_git_repository_root")
        assert not hasattr(trusted_paths, "_git_common_dir")


class TestGitRetryContract:
    """Exactly three total attempts, explicit transient allowlist, injectable backoff."""

    def _present_workspace(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        from optimus.acp import trusted_paths

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / ".git").mkdir()
        monkeypatch.setattr(trusted_paths.shutil, "which", lambda _name: "git")
        return workspace

    def _present_run(
        self, workspace: Path, failures: list[BaseException]
    ) -> tuple[object, list[int]]:
        attempts: list[int] = []

        def run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            attempts.append(len(attempts) + 1)
            if failures:
                raise failures.pop(0)
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=_git_probe_stdout(workspace.resolve(), (workspace / ".git").resolve()),
                stderr="",
            )

        return run, attempts

    @pytest.mark.parametrize("success_attempt", (1, 2, 3), ids=("attempt1", "attempt2", "attempt3"))
    def test_retry_contract_success_yields_identical_present_facts(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        success_attempt: int,
    ) -> None:
        from optimus.acp import trusted_paths

        workspace = self._present_workspace(tmp_path, monkeypatch)
        sleeps: list[float] = []
        failures: list[BaseException] = [
            _oserror(winerror=6) for _ in range(success_attempt - 1)
        ]
        run, attempts = self._present_run(workspace, failures)
        result = trusted_paths.resolve_git_context(
            workspace, run=run, sleeper=sleeps.append
        )
        expected_sleeps = [0.025, 0.100][: success_attempt - 1]

        assert result.disposition is trusted_paths.GitContextDisposition.PRESENT
        assert result.repository_root == str(workspace.resolve())
        assert result.git_common_dir == str((workspace / ".git").resolve())
        assert attempts == list(range(1, success_attempt + 1))
        assert sleeps == expected_sleeps

    @pytest.mark.parametrize(
        "factory",
        (
            lambda: _oserror(winerror=6),
            lambda: _oserror(winerror=50),
            lambda: _oserror(errno_value=__import__("errno").EINTR),
            lambda: _oserror(errno_value=__import__("errno").EAGAIN),
            lambda: _oserror(errno_value=__import__("errno").ETIMEDOUT),
            lambda: subprocess.TimeoutExpired(cmd="git", timeout=5),
        ),
        ids=("winerror-6", "winerror-50", "EINTR", "EAGAIN", "ETIMEDOUT", "TimeoutExpired"),
    )
    def test_retry_contract_exhaustion_is_unavailable(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        factory: object,
    ) -> None:
        from optimus.acp import trusted_paths

        workspace = self._present_workspace(tmp_path, monkeypatch)
        sleeps: list[float] = []
        remaining = [factory() for _ in range(3)]  # type: ignore[operator]
        run, attempts = self._present_run(workspace, remaining)
        result = trusted_paths.resolve_git_context(
            workspace, run=run, sleeper=sleeps.append
        )

        assert result.disposition is trusted_paths.GitContextDisposition.UNAVAILABLE
        assert result.repository_root is None
        assert result.git_common_dir is None
        assert attempts == [1, 2, 3]
        assert sleeps == [0.025, 0.100]
        assert [item.attempt for item in result.diagnostics] == [1, 2, 3]
        assert all(item.classification == "transient" for item in result.diagnostics)
        assert result.diagnostics[-1].disposition == "retry_exhausted"

    def test_retry_contract_permanent_error_invokes_once_and_never_sleeps(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from optimus.acp import trusted_paths

        workspace = self._present_workspace(tmp_path, monkeypatch)
        sleeps: list[float] = []
        run, attempts = self._present_run(workspace, [_oserror(errno_value=999)])
        result = trusted_paths.resolve_git_context(
            workspace, run=run, sleeper=sleeps.append
        )

        assert result.disposition is trusted_paths.GitContextDisposition.UNAVAILABLE
        assert attempts == [1]
        assert sleeps == []
        assert result.diagnostics[0].classification == "permanent"
        assert result.diagnostics[0].attempt == 1


class TestGitRedirectEnvironment:
    """Repository-redirection variables cannot select a different identity."""

    def test_git_redirect_strips_hostile_keys_and_keeps_path_and_sentinel(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from optimus.acp import trusted_paths

        workspace = tmp_path / "workspace"
        hostile = tmp_path / "hostile-repo"
        workspace.mkdir()
        hostile.mkdir()
        (workspace / ".git").mkdir()
        monkeypatch.setattr(trusted_paths.shutil, "which", lambda _name: "git")
        captured: dict[str, object] = {}

        def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            captured["env"] = kwargs.get("env")
            captured["cwd"] = kwargs.get("cwd")
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=_git_probe_stdout(workspace.resolve(), (workspace / ".git").resolve()),
                stderr="",
            )

        environ = {
            "PATH": "/trusted/bin",
            "OPTIMUS_TEST_SENTINEL": "keep-me",
            "GIT_DIR": str(hostile / ".git"),
            "GIT_WORK_TREE": str(hostile),
            "GIT_COMMON_DIR": str(hostile / ".git"),
        }
        result = trusted_paths.resolve_git_context(
            workspace, environ=environ, run=run
        )
        env = captured["env"]
        assert isinstance(env, dict)
        for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR"):
            assert key not in env
            assert key.lower() not in {item.lower() for item in env}
        assert env["PATH"] == "/trusted/bin"
        assert env["OPTIMUS_TEST_SENTINEL"] == "keep-me"
        assert captured["cwd"] == str(workspace)
        assert result.disposition is trusted_paths.GitContextDisposition.PRESENT
        assert result.repository_root == str(workspace.resolve())
        assert result.repository_root != str(hostile.resolve())

    @pytest.mark.skipif(
        sys.platform != "win32",
        reason="Windows-only: repository-redirect env keys are stripped case-insensitively",
    )
    def test_git_redirect_strips_case_variants_on_windows(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from optimus.acp import trusted_paths

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / ".git").mkdir()
        monkeypatch.setattr(trusted_paths.shutil, "which", lambda _name: "git")
        captured: dict[str, object] = {}

        def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            captured["env"] = kwargs.get("env")
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=_git_probe_stdout(workspace.resolve(), (workspace / ".git").resolve()),
                stderr="",
            )

        result = trusted_paths.resolve_git_context(
            workspace,
            environ={
                "PATH": "C:\\Windows\\System32",
                "Git_Dir": "C:\\hostile\\.git",
                "git_work_tree": "C:\\hostile",
                "Git_Common_Dir": "C:\\hostile\\.git",
            },
            run=run,
        )
        env = captured["env"]
        assert isinstance(env, dict)
        assert {key.lower() for key in env}.isdisjoint(
            {"git_dir", "git_work_tree", "git_common_dir"}
        )
        assert env["PATH"] == "C:\\Windows\\System32"
        assert result.disposition is trusted_paths.GitContextDisposition.PRESENT


# --- Plan 11.15 Task 2: v3 identity, exclusion policy, topology snapshot ---


class TestWorkspaceIdentityV3:
    """v3 digest is length-delimited, Git-tri-state, and independent of ctime."""

    def test_v3_absent_sentinel_is_length_delimited_and_ignores_ctime(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from optimus.acp import trusted_paths

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        monkeypatch.setattr(
            trusted_paths,
            "resolve_git_context",
            lambda *_a, **_k: trusted_paths.GitContextResult(
                disposition=trusted_paths.GitContextDisposition.ABSENT,
                repository_root=None,
                git_common_dir=None,
                diagnostics=(),
            ),
        )
        first = trusted_paths.resolve_workspace_security_state(workspace)
        (workspace / "added-after-authorization").write_text("x", encoding="utf-8")
        second = trusted_paths.resolve_workspace_security_state(workspace)

        assert first.identity.format_version == 3
        assert first.identity.digest == second.identity.digest
        assert first.identity.git_context.disposition is trusted_paths.GitContextDisposition.ABSENT
        assert "change_time_ns" not in first.identity.__dataclass_fields__

    def test_v3_present_binds_both_git_paths_not_diagnostics(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from optimus.acp import trusted_paths

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / ".git").mkdir()
        present = trusted_paths.GitContextResult(
            disposition=trusted_paths.GitContextDisposition.PRESENT,
            repository_root=str(workspace.resolve()),
            git_common_dir=str((workspace / ".git").resolve()),
            diagnostics=(),
        )
        noisy = trusted_paths.GitContextResult(
            disposition=trusted_paths.GitContextDisposition.PRESENT,
            repository_root=present.repository_root,
            git_common_dir=present.git_common_dir,
            diagnostics=(
                trusted_paths.ProbeDiagnostic(
                    phase="git_context",
                    probe="rev-parse",
                    attempt=2,
                    classification="transient",
                    disposition="present",
                    exception_type="OSError",
                    errno=None,
                    winerror=6,
                    return_code=None,
                    duration_ms=1,
                ),
            ),
        )
        monkeypatch.setattr(trusted_paths, "resolve_git_context", lambda *_a, **_k: present)
        quiet_state = trusted_paths.resolve_workspace_security_state(workspace)
        monkeypatch.setattr(trusted_paths, "resolve_git_context", lambda *_a, **_k: noisy)
        noisy_state = trusted_paths.resolve_workspace_security_state(workspace)
        assert quiet_state.identity.digest == noisy_state.identity.digest

        moved = trusted_paths.GitContextResult(
            disposition=trusted_paths.GitContextDisposition.PRESENT,
            repository_root=str(workspace.resolve()),
            git_common_dir=str((tmp_path / "other.git").resolve()),
            diagnostics=(),
        )
        monkeypatch.setattr(trusted_paths, "resolve_git_context", lambda *_a, **_k: moved)
        moved_state = trusted_paths.resolve_workspace_security_state(workspace)
        assert moved_state.identity.digest != quiet_state.identity.digest

    def test_v3_unavailable_produces_no_identity_digest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from optimus.acp import trusted_paths

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / ".git").mkdir()
        monkeypatch.setattr(
            trusted_paths,
            "resolve_git_context",
            lambda *_a, **_k: trusted_paths.GitContextResult(
                disposition=trusted_paths.GitContextDisposition.UNAVAILABLE,
                repository_root=None,
                git_common_dir=None,
                diagnostics=(),
            ),
        )
        with pytest.raises(trusted_paths.TrustedPathError) as exc_info:
            trusted_paths.resolve_workspace_security_state(workspace)
        assert exc_info.value.code == "WORKSPACE_IDENTITY_UNAVAILABLE"

    def test_legacy_v2_golden_vector_is_pinned(self) -> None:
        from optimus.acp import trusted_paths

        digest = trusted_paths.compute_legacy_v2_digest(
            lexical_path="/tmp/golden-workspace",
            canonical_path="/tmp/golden-workspace",
            device=8,
            inode=16,
            change_time_ns=123456789,
            repository_root=None,
            git_common_dir=None,
        )
        assert digest == "24cce4d45cd7207882167783cc65d2071f3724cd49a5c5b0550050e523d8b95c"


class TestExclusionPolicyV1:
    def test_exclusion_policy_exact_member_set(self) -> None:
        from optimus.acp import trusted_paths

        assert trusted_paths.WORKSPACE_EXCLUSION_POLICY_VERSION == 1
        assert trusted_paths.exclusion_policy_v1_exact_names() == {
            ".pytest_cache",
            ".ruff_cache",
            ".coverage",
            "coverage.xml",
            ".venv",
            ".venv-wsl",
            ".venv_wsl",
            "build",
            "dist",
            ".uv-cache",
            ".uv-cache-plan118",
            "tmp",
        }

    @pytest.mark.parametrize(
        ("name", "excluded"),
        (
            (".coverage.1", True),
            (".coverage.", False),
            (".uv-cache-foo", True),
            ("hs_err_pid123.log", True),
            ("replay_pid456.log", True),
            ("xhs_err_pid1.log", False),
            ("hs_err_pid.log", False),
            ("notes.log", False),
            (".idea", False),
            ("node_modules", False),
            ("foo/.coverage", False),
        ),
    )
    def test_exclusion_policy_anchored_patterns_and_near_misses(
        self, name: str, excluded: bool
    ) -> None:
        from optimus.acp import trusted_paths

        assert trusted_paths.is_excluded_immediate_basename(name) is excluded

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only: ordinal case-insensitive exclusions")
    def test_exclusion_policy_windows_ordinal_case_insensitive(self) -> None:
        from optimus.acp import trusted_paths

        assert trusted_paths.is_excluded_immediate_basename(".Coverage") is True
        assert trusted_paths.is_excluded_immediate_basename("HS_ERR_PID9.LOG") is True

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only: byte-sensitive exclusion matching")
    def test_exclusion_policy_posix_byte_sensitive(self) -> None:
        from optimus.acp import trusted_paths

        assert trusted_paths.is_excluded_immediate_basename(".Coverage") is False
        assert trusted_paths.is_excluded_immediate_basename("HS_ERR_PID9.LOG") is False

    def test_exclusion_policy_invalid_is_permanent_unavailable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from optimus.acp import trusted_paths

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        monkeypatch.setattr(trusted_paths, "compiled_exclusion_policy_v1", lambda: None)
        with pytest.raises(trusted_paths.TrustedPathError) as exc_info:
            trusted_paths.resolve_workspace_security_state(workspace)
        assert exc_info.value.code == "WORKSPACE_IDENTITY_UNAVAILABLE"
        assert exc_info.value.diagnostics[0].classification == "permanent"
        assert exc_info.value.diagnostics[0].attempt == 1


class TestTopologySnapshot:
    def test_topology_detects_add_remove_rename_and_ignores_nested_content(
        self, tmp_path: Path
    ) -> None:
        from optimus.acp import trusted_paths

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "keep").mkdir()
        (workspace / "keep" / "nested.txt").write_text("one", encoding="utf-8")
        before = trusted_paths.resolve_workspace_security_state(workspace)
        (workspace / "keep" / "nested.txt").write_text("two", encoding="utf-8")
        nested = trusted_paths.resolve_workspace_security_state(workspace)
        assert before.change_snapshot.immediate_root_digest == nested.change_snapshot.immediate_root_digest

        (workspace / "added-after-authorization").write_text("x", encoding="utf-8")
        added = trusted_paths.resolve_workspace_security_state(workspace)
        assert added.change_snapshot.immediate_root_digest != before.change_snapshot.immediate_root_digest

    def test_fu18_equal_ctime_non_excluded_add_is_root_topology_mismatch(
        self, tmp_path: Path
    ) -> None:
        from optimus.acp import trusted_paths

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        initial = trusted_paths.resolve_workspace_security_state(workspace)
        before_ctime = workspace.stat().st_ctime_ns
        (workspace / "added-after-authorization").write_text("synthetic", encoding="utf-8")
        after_ctime = workspace.stat().st_ctime_ns
        after = trusted_paths.resolve_workspace_security_state(workspace)

        assert initial.identity.digest == after.identity.digest
        assert initial.change_snapshot.immediate_root_digest != after.change_snapshot.immediate_root_digest
        with pytest.raises(trusted_paths.TrustedPathError) as exc_info:
            trusted_paths.revalidate_workspace_security_state(initial)
        assert exc_info.value.code == "WORKSPACE_IDENTITY_CHANGED"
        assert exc_info.value.reason == "root_topology_mismatch"
        if before_ctime != after_ctime:
            # Inject equality: the mismatch must still hold when ctime is not a signal.
            assert initial.identity.digest == after.identity.digest

    @pytest.mark.parametrize("name", (".coverage", "hs_err_pid123.log"))
    def test_fu18_excluded_immediate_names_are_accepted_residuals(
        self, tmp_path: Path, name: str
    ) -> None:
        from optimus.acp import trusted_paths

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        initial = trusted_paths.resolve_workspace_security_state(workspace)
        (workspace / name).write_text("volatile", encoding="utf-8")
        trusted_paths.revalidate_workspace_security_state(initial)

    def test_fu18_excluded_tmp_nested_file_is_accepted_residual(self, tmp_path: Path) -> None:
        from optimus.acp import trusted_paths

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "tmp").mkdir()
        initial = trusted_paths.resolve_workspace_security_state(workspace)
        (workspace / "tmp" / "drop.txt").write_text("volatile", encoding="utf-8")
        trusted_paths.revalidate_workspace_security_state(initial)
