"""OS-derived trusted operator roots and canonical workspace identity.

Plan 9.96, Task 2: Approval/key/lock locations never depend on inherited
APPDATA, LOCALAPPDATA, HOME, XDG_CONFIG_HOME, or gated OPTIMUS_CONFIG_ROOT
(Global Constraint 8). Workspace identity binds approvals to a specific
filesystem path and inode, detecting relocation and symlink changes.
"""

from __future__ import annotations

import errno
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Protocol

_CONFIG_DIR_NAME = "optimus-cost-agent"


# --- Error type ---


class TrustedPathError(ValueError):
    """Raised when trusted path resolution or workspace identity fails."""

    def __init__(self, *, code: str, detail: str = "", reason: str | None = None,
                 diagnostics: tuple[ProbeDiagnostic, ...] = ()) -> None:
        self.code = code
        self.detail = detail
        self.reason = reason
        self.diagnostics = diagnostics
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


class GitContextDisposition(str, Enum):
    """Confirmed Git topology, confirmed absence, or unavailable evidence."""

    PRESENT = "present"
    ABSENT = "absent"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ProbeDiagnostic:
    """Sanitized structured evidence for one Git or filesystem probe attempt."""

    phase: str
    probe: str
    attempt: int
    classification: Literal["transient", "permanent"]
    disposition: str
    exception_type: str | None
    errno: int | None
    winerror: int | None
    return_code: int | None
    duration_ms: int


@dataclass(frozen=True)
class GitContextResult:
    """One coherent Git discovery result. UNAVAILABLE cannot feed a digest."""

    disposition: GitContextDisposition
    repository_root: str | None
    git_common_dir: str | None
    diagnostics: tuple[ProbeDiagnostic, ...]


@dataclass(frozen=True)
class WorkspaceChangeSnapshot:
    """Ephemeral immediate-root topology snapshot. Never stored in approvals."""

    canonical_path: str
    device: int
    inode: int
    exclusion_policy_version: int
    immediate_root_digest: str
    diagnostics: tuple[ProbeDiagnostic, ...]


@dataclass(frozen=True)
class WorkspaceSecurityState:
    """One successful resolution of stable identity, topology, and legacy v2 address."""

    identity: WorkspaceIdentity
    change_snapshot: WorkspaceChangeSnapshot
    legacy_v2_digest: str


@dataclass(frozen=True)
class WorkspaceIdentity:
    """Stable v3 workspace identity. Does not bind timestamps or snapshots."""

    format_version: int
    lexical_path: str
    canonical_path: str
    device: int
    inode: int
    git_context: GitContextResult
    digest: str

    @property
    def repository_root(self) -> str | None:
        return self.git_context.repository_root

    @property
    def git_common_dir(self) -> str | None:
        return self.git_context.git_common_dir


_GIT_REDIRECT_KEYS = frozenset(
    {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_INDEX_FILE",
        "GIT_NAMESPACE",
    }
)
_TRANSIENT_WINERRORS = frozenset({6, 50})
_TRANSIENT_ERRNOS = frozenset({errno.EINTR, errno.EAGAIN, errno.ETIMEDOUT})
_GIT_PROBE_ATTEMPTS = 3
_GIT_PROBE_BACKOFFS = (0.025, 0.100)
_GIT_PROBE_TIMEOUT_SECONDS = 5.0


_SNAPSHOT_PROBES = frozenset({"scandir", "lstat"})


def format_trusted_path_operator_message(
    exc: TrustedPathError,
    *,
    prefix: str,
    workspace_root: Path,
    when: Literal["initial", "revalidate"],
) -> str:
    """Operator-facing trusted-path stderr: typed code, phase, and remediation."""
    snapshot = any(item.probe in _SNAPSHOT_PROBES for item in exc.diagnostics)
    phase = f"{when}_snapshot" if snapshot else f"{when}_identity"
    if exc.code == "WORKSPACE_NOT_FOUND":
        if exc.detail:
            return f"{prefix}: WORKSPACE_NOT_FOUND: {exc.detail}"
        return f"{prefix}: WORKSPACE_NOT_FOUND"
    if exc.code == "WORKSPACE_IDENTITY_UNAVAILABLE":
        exhausted = any(item.disposition == "retry_exhausted" for item in exc.diagnostics)
        action = (
            "Retry the launch after the probe condition clears."
            if exhausted
            else "Repair Git or filesystem access, then retry."
        )
        return (
            f"{prefix}: WORKSPACE_IDENTITY_UNAVAILABLE: workspace identity could not be confirmed "
            f"(phase={phase}). {action}"
        )
    if exc.code == "WORKSPACE_IDENTITY_CHANGED":
        reason = exc.reason or "stable_identity_mismatch"
        return (
            f"{prefix}: WORKSPACE_IDENTITY_CHANGED: workspace identity changed "
            f"(reason={reason}). Review the workspace and re-approve with:\n"
            f"  optimus-trust --workspace-root {workspace_root} approve --mode durable"
        )
    detail = f": {exc.detail}" if exc.detail else ""
    return f"{prefix}: {exc.code}{detail}"


def absent_git_context() -> GitContextResult:
    return GitContextResult(
        disposition=GitContextDisposition.ABSENT,
        repository_root=None,
        git_common_dir=None,
        diagnostics=(),
    )


def present_git_context(repository_root: str, git_common_dir: str) -> GitContextResult:
    return GitContextResult(
        disposition=GitContextDisposition.PRESENT,
        repository_root=repository_root,
        git_common_dir=git_common_dir,
        diagnostics=(),
    )
WORKSPACE_IDENTITY_FORMAT_VERSION = 3
WORKSPACE_EXCLUSION_POLICY_VERSION = 1
_EXCLUSION_EXACT_NAMES = frozenset(
    {
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
)
_EXCLUSION_PATTERNS = (
    re.compile(r"^\.coverage\..+$"),
    re.compile(r"^\.uv-cache-.+$"),
    re.compile(r"^hs_err_pid\d+\.log$"),
    re.compile(r"^replay_pid\d+\.log$"),
)


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
    """Resolve the stable v3 identity. Topology lives on WorkspaceSecurityState."""
    return resolve_workspace_security_state(workspace_root).identity


def revalidate_workspace_identity(identity: WorkspaceIdentity) -> None:
    """Revalidate stable v3 identity only. Topology uses revalidate_workspace_security_state."""
    try:
        current = resolve_workspace_identity(Path(identity.lexical_path))
    except TrustedPathError as exc:
        if exc.code == "WORKSPACE_IDENTITY_UNAVAILABLE":
            raise
        raise TrustedPathError(
            code="WORKSPACE_IDENTITY_CHANGED",
            detail="workspace directory no longer resolves to the authorized identity",
            reason="stable_identity_mismatch",
        ) from exc

    if current.digest != identity.digest:
        raise TrustedPathError(
            code="WORKSPACE_IDENTITY_CHANGED",
            detail="workspace identity digest mismatch",
            reason="stable_identity_mismatch",
        )


# --- Git helpers ---


def resolve_git_context(
    workspace: Path,
    *,
    environ: Mapping[str, str] | None = None,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    sleeper: Callable[[float], None] = time.sleep,
) -> GitContextResult:
    """Discover Git topology as PRESENT, ABSENT, or UNAVAILABLE.

    Marker inspection uses non-following lstat. A missing marker is ABSENT
    without spawning Git. A present marker issues one argument-list command
    that returns both repository root and common directory. Unavailable
    evidence is never converted to absence or hashed.
    """
    marker = _git_marker_disposition(workspace)
    if marker.disposition is GitContextDisposition.ABSENT:
        return marker
    if marker.disposition is GitContextDisposition.UNAVAILABLE:
        return marker

    git_executable = shutil.which("git")
    if git_executable is None:
        return GitContextResult(
            disposition=GitContextDisposition.UNAVAILABLE,
            repository_root=None,
            git_common_dir=None,
            diagnostics=(
                _probe_diagnostic(
                    probe="git_executable",
                    attempt=1,
                    classification="permanent",
                    disposition=GitContextDisposition.UNAVAILABLE.value,
                    exception_type=None,
                    errno_value=None,
                    winerror=None,
                    return_code=None,
                    duration_ms=0,
                ),
            ),
        )

    env = _sanitize_git_environ(os.environ if environ is None else environ)
    argv = [
        git_executable,
        "rev-parse",
        "--path-format=absolute",
        "--show-toplevel",
        "--git-common-dir",
    ]
    diagnostics: list[ProbeDiagnostic] = []
    for attempt in range(1, _GIT_PROBE_ATTEMPTS + 1):
        started = time.monotonic()
        try:
            completed = run(
                argv,
                cwd=str(workspace),
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=_GIT_PROBE_TIMEOUT_SECONDS,
                shell=False,
            )
        except Exception as exc:
            duration_ms = _duration_ms(started)
            transient = _is_transient_git_error(exc)
            diagnostic = _diagnostic_from_exception(
                probe="rev-parse",
                attempt=attempt,
                exc=exc,
                transient=transient,
                duration_ms=duration_ms,
            )
            if transient and attempt < _GIT_PROBE_ATTEMPTS:
                diagnostics.append(diagnostic)
                sleeper(_GIT_PROBE_BACKOFFS[attempt - 1])
                continue
            if transient:
                diagnostics.append(replace(diagnostic, disposition="retry_exhausted"))
            else:
                diagnostics.append(diagnostic)
            return GitContextResult(
                disposition=GitContextDisposition.UNAVAILABLE,
                repository_root=None,
                git_common_dir=None,
                diagnostics=tuple(diagnostics),
            )

        duration_ms = _duration_ms(started)
        parsed = _parse_git_rev_parse_paths(completed, workspace=workspace)
        if parsed is not None:
            diagnostics.append(
                _probe_diagnostic(
                    probe="rev-parse",
                    attempt=attempt,
                    classification="transient" if diagnostics else "permanent",
                    disposition=GitContextDisposition.PRESENT.value,
                    exception_type=None,
                    errno_value=None,
                    winerror=None,
                    return_code=completed.returncode,
                    duration_ms=duration_ms,
                )
            )
            repository_root, git_common_dir = parsed
            return GitContextResult(
                disposition=GitContextDisposition.PRESENT,
                repository_root=repository_root,
                git_common_dir=git_common_dir,
                diagnostics=tuple(diagnostics),
            )
        diagnostics.append(
            _probe_diagnostic(
                probe="rev-parse",
                attempt=attempt,
                classification="permanent",
                disposition=GitContextDisposition.UNAVAILABLE.value,
                exception_type=None,
                errno_value=None,
                winerror=None,
                return_code=completed.returncode,
                duration_ms=duration_ms,
            )
        )
        return GitContextResult(
            disposition=GitContextDisposition.UNAVAILABLE,
            repository_root=None,
            git_common_dir=None,
            diagnostics=tuple(diagnostics),
        )

    return GitContextResult(
        disposition=GitContextDisposition.UNAVAILABLE,
        repository_root=None,
        git_common_dir=None,
        diagnostics=tuple(diagnostics),
    )


def _git_marker_disposition(workspace: Path) -> GitContextResult:
    """Walk toward the filesystem root looking for a non-followed `.git` marker."""
    current = Path(workspace)
    while True:
        marker = current / ".git"
        try:
            os.lstat(marker)
        except FileNotFoundError:
            parent = current.parent
            if parent == current:
                return GitContextResult(
                    disposition=GitContextDisposition.ABSENT,
                    repository_root=None,
                    git_common_dir=None,
                    diagnostics=(),
                )
            current = parent
            continue
        except OSError as exc:
            return GitContextResult(
                disposition=GitContextDisposition.UNAVAILABLE,
                repository_root=None,
                git_common_dir=None,
                diagnostics=(
                    _diagnostic_from_exception(
                        probe="git_marker",
                        attempt=1,
                        exc=exc,
                        transient=False,
                        duration_ms=0,
                    ),
                ),
            )
        return GitContextResult(
            disposition=GitContextDisposition.PRESENT,
            repository_root=None,
            git_common_dir=None,
            diagnostics=(),
        )


def _sanitize_git_environ(environ: Mapping[str, str]) -> dict[str, str]:
    if sys.platform == "win32":
        blocked = {key.casefold() for key in _GIT_REDIRECT_KEYS}
        return {key: value for key, value in environ.items() if key.casefold() not in blocked}
    return {key: value for key, value in environ.items() if key not in _GIT_REDIRECT_KEYS}


def _is_transient_git_error(exc: BaseException) -> bool:
    if isinstance(exc, subprocess.TimeoutExpired):
        return True
    if isinstance(exc, OSError):
        winerror = getattr(exc, "winerror", None)
        if winerror in _TRANSIENT_WINERRORS:
            return True
        if getattr(exc, "errno", None) in _TRANSIENT_ERRNOS:
            return True
    return False


def _parse_git_rev_parse_paths(
    completed: subprocess.CompletedProcess[str],
    *,
    workspace: Path,
) -> tuple[str, str] | None:
    if completed.returncode != 0:
        return None
    stdout = (completed.stdout or "").replace("\r\n", "\n")
    fields = stdout.split("\n")
    while fields and fields[-1] == "":
        fields.pop()
    if len(fields) != 2 or any(not field.strip() for field in fields):
        return None
    try:
        repository_root = str(Path(fields[0]).resolve())
        common = Path(fields[1])
        git_common_dir = str(
            common.resolve() if common.is_absolute() else (workspace / common).resolve()
        )
    except (OSError, ValueError):
        return None
    if not repository_root or not git_common_dir:
        return None
    return repository_root, git_common_dir


def _diagnostic_from_exception(
    *,
    probe: str,
    attempt: int,
    exc: BaseException,
    transient: bool,
    duration_ms: int,
) -> ProbeDiagnostic:
    winerror = getattr(exc, "winerror", None)
    errno_value = getattr(exc, "errno", None) if isinstance(exc, OSError) else None
    return_code = getattr(exc, "returncode", None)
    return _probe_diagnostic(
        probe=probe,
        attempt=attempt,
        classification="transient" if transient else "permanent",
        disposition=GitContextDisposition.UNAVAILABLE.value,
        exception_type=type(exc).__name__,
        errno_value=errno_value if isinstance(errno_value, int) else None,
        winerror=winerror if isinstance(winerror, int) else None,
        return_code=return_code if isinstance(return_code, int) else None,
        duration_ms=duration_ms,
    )


def _probe_diagnostic(
    *,
    probe: str,
    attempt: int,
    classification: Literal["transient", "permanent"],
    disposition: str,
    exception_type: str | None,
    errno_value: int | None,
    winerror: int | None,
    return_code: int | None,
    duration_ms: int,
) -> ProbeDiagnostic:
    return ProbeDiagnostic(
        phase="git_context",
        probe=probe,
        attempt=attempt,
        classification=classification,
        disposition=disposition,
        exception_type=exception_type,
        errno=errno_value,
        winerror=winerror,
        return_code=return_code,
        duration_ms=duration_ms,
    )


def _duration_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


# --- Digest computation ---


def compute_legacy_v2_digest(
    *,
    lexical_path: str,
    canonical_path: str,
    device: int,
    inode: int,
    change_time_ns: int,
    repository_root: str | None,
    git_common_dir: str | None,
) -> str:
    """Exact pre-change v2 digest. Used only as a migration address."""
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


def compute_workspace_identity_v3_digest(
    *,
    lexical_path: str,
    canonical_path: str,
    device: int,
    inode: int,
    git_context: GitContextResult,
) -> str:
    if git_context.disposition is GitContextDisposition.UNAVAILABLE:
        raise TrustedPathError(
            code="WORKSPACE_IDENTITY_UNAVAILABLE",
            detail="unavailable git context cannot be hashed",
            diagnostics=git_context.diagnostics,
        )
    hasher = hashlib.sha256()
    _put_bytes(hasher, b"workspace-identity-v3")
    _put_bytes(hasher, str(WORKSPACE_IDENTITY_FORMAT_VERSION).encode("ascii"))
    _put_bytes(hasher, lexical_path.encode("utf-8"))
    _put_bytes(hasher, canonical_path.encode("utf-8"))
    _put_bytes(hasher, str(device).encode("ascii"))
    _put_bytes(hasher, str(inode).encode("ascii"))
    if git_context.disposition is GitContextDisposition.ABSENT:
        _put_bytes(hasher, b"git:absent")
    else:
        _put_bytes(hasher, b"git:present")
        _put_bytes(hasher, (git_context.repository_root or "").encode("utf-8"))
        _put_bytes(hasher, (git_context.git_common_dir or "").encode("utf-8"))
    return hasher.hexdigest()


def _put_bytes(hasher: Any, data: bytes) -> None:
    hasher.update(len(data).to_bytes(8, "big"))
    hasher.update(data)


@dataclass(frozen=True)
class ExclusionPolicyV1:
    version: int
    exact_names: frozenset[str]
    patterns: tuple[re.Pattern[str], ...]


def compiled_exclusion_policy_v1() -> ExclusionPolicyV1 | None:
    if WORKSPACE_EXCLUSION_POLICY_VERSION != 1:
        return None
    return ExclusionPolicyV1(
        version=1,
        exact_names=_EXCLUSION_EXACT_NAMES,
        patterns=_EXCLUSION_PATTERNS,
    )


def exclusion_policy_v1_exact_names() -> set[str]:
    policy = compiled_exclusion_policy_v1()
    if policy is None:
        raise TrustedPathError(
            code="WORKSPACE_IDENTITY_UNAVAILABLE",
            detail="exclusion policy is missing or invalid",
        )
    return set(policy.exact_names)


def is_excluded_immediate_basename(name: str) -> bool:
    policy = compiled_exclusion_policy_v1()
    if policy is None:
        raise TrustedPathError(
            code="WORKSPACE_IDENTITY_UNAVAILABLE",
            detail="exclusion policy is missing or invalid",
        )
    candidate = name.casefold() if sys.platform == "win32" else name
    exact = (
        {item.casefold() for item in policy.exact_names}
        if sys.platform == "win32"
        else policy.exact_names
    )
    if candidate in exact:
        return True
    return any(pattern.fullmatch(candidate) is not None for pattern in policy.patterns)


def resolve_workspace_security_state(
    workspace_root: Path,
    *,
    git_probe: Callable[..., GitContextResult] | None = None,
    scandir: Callable[[str], AbstractContextManager[Iterator[os.DirEntry[str]]]] = os.scandir,
    sleeper: Callable[[float], None] = time.sleep,
) -> WorkspaceSecurityState:
    probe = git_probe if git_probe is not None else resolve_git_context
    lexical_path, resolved, root_stat = _stat_workspace_root(workspace_root)
    policy = compiled_exclusion_policy_v1()
    if policy is None:
        raise TrustedPathError(
            code="WORKSPACE_IDENTITY_UNAVAILABLE",
            detail="exclusion policy is missing or invalid",
            diagnostics=(
                _probe_diagnostic(
                    probe="exclusion_policy",
                    attempt=1,
                    classification="permanent",
                    disposition="unavailable",
                    exception_type=None,
                    errno_value=None,
                    winerror=None,
                    return_code=None,
                    duration_ms=0,
                ),
            ),
        )

    git_context = probe(resolved)
    if git_context.disposition is GitContextDisposition.UNAVAILABLE:
        raise TrustedPathError(
            code="WORKSPACE_IDENTITY_UNAVAILABLE",
            detail="git context is unavailable",
            diagnostics=git_context.diagnostics,
        )

    identity = WorkspaceIdentity(
        format_version=WORKSPACE_IDENTITY_FORMAT_VERSION,
        lexical_path=lexical_path,
        canonical_path=str(resolved),
        device=root_stat.st_dev,
        inode=root_stat.st_ino,
        git_context=git_context,
        digest=compute_workspace_identity_v3_digest(
            lexical_path=lexical_path,
            canonical_path=str(resolved),
            device=root_stat.st_dev,
            inode=root_stat.st_ino,
            git_context=git_context,
        ),
    )
    snapshot = _capture_change_snapshot(
        resolved,
        root_stat=root_stat,
        policy=policy,
        scandir=scandir,
        sleeper=sleeper,
    )
    present = git_context.disposition is GitContextDisposition.PRESENT
    return WorkspaceSecurityState(
        identity=identity,
        change_snapshot=snapshot,
        legacy_v2_digest=compute_legacy_v2_digest(
            lexical_path=lexical_path,
            canonical_path=str(resolved),
            device=root_stat.st_dev,
            inode=root_stat.st_ino,
            change_time_ns=root_stat.st_ctime_ns,
            repository_root=git_context.repository_root if present else None,
            git_common_dir=git_context.git_common_dir if present else None,
        ),
    )


def revalidate_workspace_security_state(expected: WorkspaceSecurityState) -> None:
    try:
        current = resolve_workspace_security_state(Path(expected.identity.lexical_path))
    except TrustedPathError as exc:
        if exc.code == "WORKSPACE_IDENTITY_UNAVAILABLE":
            raise
        raise TrustedPathError(
            code="WORKSPACE_IDENTITY_CHANGED",
            detail="workspace directory no longer resolves to the authorized identity",
            reason="stable_identity_mismatch",
        ) from exc

    if current.identity.digest != expected.identity.digest:
        raise TrustedPathError(
            code="WORKSPACE_IDENTITY_CHANGED",
            detail="stable workspace identity mismatch",
            reason="stable_identity_mismatch",
        )
    if current.change_snapshot.immediate_root_digest != expected.change_snapshot.immediate_root_digest:
        raise TrustedPathError(
            code="WORKSPACE_IDENTITY_CHANGED",
            detail="immediate-root topology mismatch",
            reason="root_topology_mismatch",
        )


def _stat_workspace_root(workspace_root: Path) -> tuple[str, Path, os.stat_result]:
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
        root_stat = resolved.stat()
    except OSError as exc:
        raise TrustedPathError(
            code="WORKSPACE_NOT_FOUND",
            detail="cannot stat workspace directory",
        ) from exc
    return lexical_path, resolved, root_stat


def _capture_change_snapshot(
    resolved: Path,
    *,
    root_stat: os.stat_result,
    policy: ExclusionPolicyV1,
    scandir: Callable[[str], AbstractContextManager[Iterator[os.DirEntry[str]]]],
    sleeper: Callable[[float], None],
) -> WorkspaceChangeSnapshot:
    entries: list[bytes] = []
    try:
        with scandir(str(resolved)) as listing:
            children = list(listing)
    except OSError as exc:
        raise TrustedPathError(
            code="WORKSPACE_IDENTITY_UNAVAILABLE",
            detail="cannot scan workspace root",
            diagnostics=(
                _diagnostic_from_exception(
                    probe="scandir",
                    attempt=1,
                    exc=exc,
                    transient=_is_transient_git_error(exc),
                    duration_ms=0,
                ),
            ),
        ) from exc

    seen: set[bytes] = set()
    for child in children:
        name = child.name
        if is_excluded_immediate_basename(name):
            continue
        try:
            info = child.stat(follow_symlinks=False)
        except OSError as exc:
            raise TrustedPathError(
                code="WORKSPACE_IDENTITY_UNAVAILABLE",
                detail="cannot lstat immediate-root entry",
                diagnostics=(
                    _diagnostic_from_exception(
                        probe="lstat",
                        attempt=1,
                        exc=exc,
                        transient=_is_transient_git_error(exc),
                        duration_ms=0,
                    ),
                ),
            ) from exc
        encoded = _encode_topology_entry(name, info, resolved / name)
        if encoded in seen:
            raise TrustedPathError(
                code="WORKSPACE_IDENTITY_UNAVAILABLE",
                detail="duplicate topology encoding",
            )
        seen.add(encoded)
        entries.append(encoded)

    entries.sort()
    hasher = hashlib.sha256()
    _put_bytes(hasher, b"workspace-topology-v1")
    _put_bytes(hasher, str(policy.version).encode("ascii"))
    for encoded in entries:
        _put_bytes(hasher, encoded)
    return WorkspaceChangeSnapshot(
        canonical_path=str(resolved),
        device=root_stat.st_dev,
        inode=root_stat.st_ino,
        exclusion_policy_version=policy.version,
        immediate_root_digest=hasher.hexdigest(),
        diagnostics=(),
    )


def _encode_topology_entry(name: str, info: os.stat_result, path: Path) -> bytes:
    try:
        name_bytes = os.fsencode(name)
    except (TypeError, ValueError, OSError) as exc:
        raise TrustedPathError(
            code="WORKSPACE_IDENTITY_UNAVAILABLE",
            detail="unencodable topology name",
        ) from exc
    mode = info.st_mode
    if stat.S_ISLNK(mode):
        kind = b"symlink"
        try:
            target = os.fsencode(os.readlink(path))
        except OSError as exc:
            raise TrustedPathError(
                code="WORKSPACE_IDENTITY_UNAVAILABLE",
                detail="cannot read symlink target",
            ) from exc
    elif stat.S_ISDIR(mode):
        kind = b"dir"
        target = b""
    elif stat.S_ISREG(mode):
        kind = b"file"
        target = b""
    else:
        kind = f"mode:{mode}".encode("ascii")
        target = b""
    hasher = hashlib.sha256()
    _put_bytes(hasher, name_bytes)
    _put_bytes(hasher, kind)
    _put_bytes(hasher, str(info.st_dev).encode("ascii"))
    _put_bytes(hasher, str(info.st_ino).encode("ascii"))
    _put_bytes(hasher, target)
    return hasher.digest()
