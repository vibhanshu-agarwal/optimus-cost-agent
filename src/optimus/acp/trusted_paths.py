"""OS-derived trusted operator roots and canonical workspace identity.

Plan 9.96, Task 2: Approval/key/lock locations never depend on inherited
APPDATA, LOCALAPPDATA, HOME, XDG_CONFIG_HOME, or gated OPTIMUS_CONFIG_ROOT
(Global Constraint 8). Workspace identity binds approvals to a specific
filesystem path and inode, detecting relocation and symlink changes.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

_CONFIG_DIR_NAME = "optimus-cost-agent"


# --- Error type ---


class TrustedPathError(ValueError):
    """Raised when trusted path resolution or workspace identity fails."""

    def __init__(self, *, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}" if self.detail else self.code


# --- Dataclasses ---


@dataclass(frozen=True)
class TrustedOperatorRoots:
    """OS-derived roots independent of inherited environment variables.

    default_config_root: where .env.gateway and persistent config live
        (RoamingAppData on Windows, ~/.config on POSIX).
    approval_runtime_root: where approval locks and ephemeral runtime state live
        (LocalAppData on Windows, ~/.local/state on POSIX).
    """

    default_config_root: Path
    approval_runtime_root: Path


@dataclass(frozen=True)
class WorkspaceIdentity:
    """Canonical identity of a workspace directory bound to filesystem metadata.

    Used to bind approval records to a specific workspace location. Changes to
    the path, inode, device, or git state invalidate existing approvals.
    """

    lexical_path: str
    canonical_path: str
    device: int
    inode: int
    change_time_ns: int
    repository_root: str | None
    git_common_dir: str | None
    digest: str


# --- Injectable platform adapters ---


class WindowsKnownFoldersAdapter(Protocol):
    """Protocol for resolving Windows Known Folder paths."""

    roaming_appdata: Path | None
    local_appdata: Path | None


class PosixHomeAdapter(Protocol):
    """Protocol for resolving POSIX authenticated user home."""

    home_dir: Path | None


# --- Root resolution ---


def resolve_trusted_operator_roots(
    *,
    platform_name: str,
    windows_known_folders: Any | None = None,
    posix_home: Any | None = None,
) -> TrustedOperatorRoots:
    """Resolve OS-derived config and runtime roots.

    On Windows: uses Known Folder paths (FOLDERID_RoamingAppData, FOLDERID_LocalAppData)
    through the injectable adapter. NEVER reads APPDATA/LOCALAPPDATA env vars.

    On POSIX/macOS: uses the authenticated user's home directory through the
    injectable adapter. NEVER reads HOME/XDG_CONFIG_HOME env vars.

    Raises TrustedPathError with code TRUSTED_OPERATOR_ROOT_UNAVAILABLE if the
    OS cannot provide the required paths.
    """
    if platform_name == "win32":
        return _resolve_windows_roots(windows_known_folders)
    return _resolve_posix_roots(posix_home)


def _resolve_windows_roots(folders: Any | None) -> TrustedOperatorRoots:
    """Resolve Windows roots from Known Folder adapter."""
    if folders is None:
        folders = _real_windows_known_folders()

    roaming = getattr(folders, "roaming_appdata", None)
    local = getattr(folders, "local_appdata", None)

    if roaming is None or local is None:
        raise TrustedPathError(
            code="TRUSTED_OPERATOR_ROOT_UNAVAILABLE",
            detail="Windows Known Folders (RoamingAppData/LocalAppData) could not be resolved",
        )

    return TrustedOperatorRoots(
        default_config_root=Path(roaming) / _CONFIG_DIR_NAME,
        approval_runtime_root=Path(local) / _CONFIG_DIR_NAME,
    )


def _resolve_posix_roots(posix_home: Any | None) -> TrustedOperatorRoots:
    """Resolve POSIX roots from home directory adapter."""
    if posix_home is None:
        posix_home = _real_posix_home()

    home_dir = getattr(posix_home, "home_dir", None)

    if home_dir is None:
        raise TrustedPathError(
            code="TRUSTED_OPERATOR_ROOT_UNAVAILABLE",
            detail="POSIX authenticated home directory could not be resolved",
        )

    home = Path(home_dir)
    return TrustedOperatorRoots(
        default_config_root=home / ".config" / _CONFIG_DIR_NAME,
        approval_runtime_root=home / ".local" / "state" / _CONFIG_DIR_NAME,
    )


# --- Real OS adapters (used when no injectable adapter is provided) ---


@dataclass
class _RealWindowsKnownFolders:
    """Resolve Windows Known Folders via ctypes SHGetKnownFolderPath.

    Uses proper binary GUID structs as required by the Windows API.
    """

    roaming_appdata: Path | None = None
    local_appdata: Path | None = None

    def __post_init__(self) -> None:
        try:
            import ctypes
            from ctypes import wintypes

            class _GUID(ctypes.Structure):
                _fields_ = [
                    ("Data1", wintypes.DWORD),
                    ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8),
                ]

            # FOLDERID_RoamingAppData = {3EB685DB-65F9-4CF6-A03A-E3EF65729F3D}
            folderid_roaming = _GUID(
                0x3EB685DB, 0x65F9, 0x4CF6,
                (ctypes.c_ubyte * 8)(0xA0, 0x3A, 0xE3, 0xEF, 0x65, 0x72, 0x9F, 0x3D),
            )
            # FOLDERID_LocalAppData = {F1B32785-6FBA-4FCF-9D55-7B8E7F157091}
            folderid_local = _GUID(
                0xF1B32785, 0x6FBA, 0x4FCF,
                (ctypes.c_ubyte * 8)(0x9D, 0x55, 0x7B, 0x8E, 0x7F, 0x15, 0x70, 0x91),
            )

            shell32 = ctypes.windll.shell32  # type: ignore[attr-defined]
            ole32 = ctypes.windll.ole32  # type: ignore[attr-defined]

            shell32.SHGetKnownFolderPath.argtypes = [
                ctypes.POINTER(_GUID),
                wintypes.DWORD,
                wintypes.HANDLE,
                ctypes.POINTER(ctypes.c_wchar_p),
            ]
            shell32.SHGetKnownFolderPath.restype = ctypes.c_long

            # Resolve RoamingAppData
            path_ptr = ctypes.c_wchar_p()
            hr = shell32.SHGetKnownFolderPath(
                ctypes.byref(folderid_roaming), 0, None, ctypes.byref(path_ptr)
            )
            if hr == 0 and path_ptr.value:
                self.roaming_appdata = Path(path_ptr.value)
                ole32.CoTaskMemFree(path_ptr)

            # Resolve LocalAppData
            path_ptr = ctypes.c_wchar_p()
            hr = shell32.SHGetKnownFolderPath(
                ctypes.byref(folderid_local), 0, None, ctypes.byref(path_ptr)
            )
            if hr == 0 and path_ptr.value:
                self.local_appdata = Path(path_ptr.value)
                ole32.CoTaskMemFree(path_ptr)

        except (OSError, AttributeError, ImportError):
            pass


@dataclass
class _RealPosixHome:
    """Resolve POSIX home via pwd.getpwuid(os.getuid()).pw_dir."""

    home_dir: Path | None = None

    def __post_init__(self) -> None:
        try:
            import os
            import pwd

            pw_entry = pwd.getpwuid(os.getuid())
            if pw_entry.pw_dir:
                self.home_dir = Path(pw_entry.pw_dir)
        except (ImportError, KeyError, OSError):
            pass


def _real_windows_known_folders() -> _RealWindowsKnownFolders:
    """Create a real Windows Known Folders adapter."""
    return _RealWindowsKnownFolders()


def _real_posix_home() -> _RealPosixHome:
    """Create a real POSIX home adapter."""
    return _RealPosixHome()


# --- Workspace identity ---


def resolve_workspace_identity(workspace_root: Path) -> WorkspaceIdentity:
    """Resolve canonical workspace identity from filesystem.

    Captures:
    - Canonical (resolved) path
    - Filesystem device and inode (st_dev, st_ino)
    - Git repository root and common dir (if present)
    - SHA-256 digest binding all identity fields

    Uses shell=False subprocess calls for git. Does not create any directories.

    Raises TrustedPathError with code WORKSPACE_NOT_FOUND if the path doesn't exist.
    """
    lexical_path = str(workspace_root.absolute())
    if sys.platform == "win32":
        lexical_path = os.path.normcase(lexical_path)
    resolved = Path(lexical_path).resolve()

    if not resolved.exists():
        raise TrustedPathError(
            code="WORKSPACE_NOT_FOUND",
            detail="workspace directory does not exist",
        )

    try:
        stat = resolved.stat()
    except OSError as exc:
        raise TrustedPathError(
            code="WORKSPACE_NOT_FOUND",
            detail="cannot stat workspace directory",
        ) from exc

    device = stat.st_dev
    inode = stat.st_ino

    repository_root = _git_repository_root(resolved)
    git_common_dir = _git_common_dir(resolved) if repository_root else None

    # Compute identity digest from all binding fields.
    digest = _compute_identity_digest(
        lexical_path=lexical_path,
        canonical_path=str(resolved),
        device=device,
        inode=inode,
        change_time_ns=stat.st_ctime_ns,
        repository_root=repository_root,
        git_common_dir=git_common_dir,
    )

    return WorkspaceIdentity(
        lexical_path=lexical_path,
        canonical_path=str(resolved),
        device=device,
        inode=inode,
        change_time_ns=stat.st_ctime_ns,
        repository_root=repository_root,
        git_common_dir=git_common_dir,
        digest=digest,
    )


def revalidate_workspace_identity(identity: WorkspaceIdentity) -> None:
    """Revalidate a previously captured workspace identity.

    Reconstructs identity from the original lexical path and compares the
    full digest. Raises TrustedPathError with code WORKSPACE_IDENTITY_CHANGED
    if the path no longer resolves to the authorized target or any bound
    identity field differs.
    """
    try:
        current = resolve_workspace_identity(Path(identity.lexical_path))
    except TrustedPathError as exc:
        raise TrustedPathError(
            code="WORKSPACE_IDENTITY_CHANGED",
            detail="workspace directory no longer resolves to the authorized identity",
        ) from exc

    if current.digest != identity.digest:
        raise TrustedPathError(
            code="WORKSPACE_IDENTITY_CHANGED",
            detail="workspace identity digest mismatch",
        )


# --- Git helpers ---


def _git_repository_root(workspace: Path) -> str | None:
    """Resolve git repository root using argument-list subprocess (shell=False)."""
    git_executable = shutil.which("git")
    if git_executable is None:
        return None

    try:
        result = subprocess.run(
            [git_executable, "rev-parse", "--show-toplevel"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return str(Path(result.stdout.strip()).resolve())
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _git_common_dir(workspace: Path) -> str | None:
    """Resolve git common dir (relevant for worktrees)."""
    git_executable = shutil.which("git")
    if git_executable is None:
        return None

    try:
        result = subprocess.run(
            [git_executable, "rev-parse", "--git-common-dir"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            raw = result.stdout.strip()
            # --git-common-dir returns a relative path; resolve from workspace.
            return str((workspace / raw).resolve())
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


# --- Digest computation ---


def _compute_identity_digest(
    *,
    lexical_path: str,
    canonical_path: str,
    device: int,
    inode: int,
    change_time_ns: int,
    repository_root: str | None,
    git_common_dir: str | None,
) -> str:
    """Compute a SHA-256 digest binding all workspace identity fields.

    The digest changes when any bound field changes, ensuring that approval
    records are invalidated on workspace relocation, symlink retargeting,
    or git common-dir changes.
    """
    hasher = hashlib.sha256()
    hasher.update(b"workspace-identity-v2\x00")
    hasher.update(lexical_path.encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update(canonical_path.encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update(str(device).encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update(str(inode).encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update(str(change_time_ns).encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update((repository_root or "").encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update((git_common_dir or "").encode("utf-8"))
    return hasher.hexdigest()
