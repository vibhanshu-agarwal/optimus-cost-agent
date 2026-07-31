"""Private staging filesystem primitives for evidence redaction.

Portable stdlib-only module: no Optimus host imports, no shelling out to icacls.
Errors expose stable snake_case codes only (never raw paths or secret material).
"""

from __future__ import annotations

import os
import re
import stat
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

_ROLE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

# Windows well-known SIDs (stable across locales).
_SID_SYSTEM = "S-1-5-18"
_SID_ADMINISTRATORS = "S-1-5-32-544"
_SID_OWNER_RIGHTS = "S-1-3-4"

_ACCESS_ALLOWED_ACE_TYPE = 0x00
_TOKEN_QUERY = 0x0008
_TOKEN_USER = 1
_DACL_SECURITY_INFORMATION = 0x00000004
_PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000
_ACL_SIZE_INFORMATION_CLASS = 2
_SE_FILE_OBJECT = 1
_GENERIC_ALL = 0x10000000
_SET_ACCESS = 2
_TRUSTEE_IS_SID = 0
_TRUSTEE_IS_USER = 1
_TRUSTEE_IS_GROUP = 2
_NO_INHERITANCE = 0
_CONTAINER_INHERIT_ACE = 0x1
_OBJECT_INHERIT_ACE = 0x2
_NO_MULTIPLE_TRUSTEE = 0


class PrivateFileError(Exception):
    """Fail-closed private-file failure with a stable code only."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass
class PrivateFileHandle:
    """Exclusive staging file opened with restrictive permissions."""

    path: Path
    _fd: int

    def fileno(self) -> int:
        return self._fd

    def flush(self) -> None:
        if self._fd < 0:
            raise PrivateFileError("staging_handle_closed")
        os.fsync(self._fd)

    def close(self) -> None:
        if self._fd >= 0:
            try:
                os.fsync(self._fd)
            except OSError:
                pass
            os.close(self._fd)
            self._fd = -1


def _filesystem_device_id(path: Path) -> int:
    return path.stat().st_dev


def _raise(code: str) -> None:
    raise PrivateFileError(code)


def _validate_artifact_role(artifact_role: str) -> None:
    if not _ROLE_PATTERN.fullmatch(artifact_role):
        _raise("unsafe_artifact_role")


def _absolute_without_follow(path: Path) -> Path:
    return path if path.is_absolute() else Path.cwd() / path


def _is_redirecting_component(path: Path) -> bool:
    """True when path is a symlink or (on Windows) any reparse point including junctions.

    ``Path.is_symlink()`` is false for NTFS junctions (``IO_REPARSE_TAG_MOUNT_POINT``),
    so Windows must also inspect ``st_file_attributes`` / ``st_reparse_tag`` from
    ``os.lstat``. Missing paths are not redirecting; unexpected ``lstat`` errors
    fail closed.
    """
    try:
        if path.is_symlink():
            return True
    except OSError:
        return True
    if sys.platform != "win32":
        return False
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    attrs = int(getattr(st, "st_file_attributes", 0) or 0)
    if attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        return True
    return bool(getattr(st, "st_reparse_tag", 0) or 0)


def _assert_no_symlink_components(path: Path) -> Path:
    """Reject any symlink/junction/reparse component; return absolute non-followed path."""
    absolute = _absolute_without_follow(path)
    built = Path(absolute.anchor)
    parts = absolute.parts[1:] if absolute.anchor else absolute.parts
    for part in parts:
        built = built / part
        if _is_redirecting_component(built):
            _raise("symlink_component_rejected")
    return built


def _is_path_under(child: Path, parent: Path) -> bool:
    try:
        child_resolved = child.resolve()
        parent_resolved = parent.resolve()
    except OSError:
        return False
    if child_resolved == parent_resolved:
        return True
    try:
        child_resolved.relative_to(parent_resolved)
        return True
    except ValueError:
        return False


def validate_root_placement(
    path: Path,
    *,
    role: str,
    destination_root: Path,
    forbidden_roots: Sequence[Path],
) -> None:
    """Reject unsafe staging/quarantine placement relative to destination and forbidden roots."""
    del role  # Role retained for call-site clarity / future policy; codes stay value-free.
    candidate = _assert_no_symlink_components(path)
    dest = _absolute_without_follow(destination_root)
    if _is_path_under(candidate, dest):
        _raise("staging_under_destination")
    for forbidden in forbidden_roots:
        if _is_path_under(candidate, _absolute_without_follow(forbidden)):
            _raise("path_under_forbidden_root")


def _apply_posix_mode(path: Path, mode: int) -> None:
    os.chmod(path, mode)


def create_private_directory(path: Path) -> Path:
    """Create a new directory with restrictive same-user permissions."""
    target = _assert_no_symlink_components(path)
    if target.exists():
        _raise("private_directory_exists")
    parent = target.parent
    if not parent.exists() or not parent.is_dir():
        _raise("private_directory_parent_missing")
    _assert_no_symlink_components(parent)
    try:
        if sys.platform == "win32":
            target.mkdir(mode=0o700)
            _apply_windows_restrictive_dacl(target, is_directory=True)
        else:
            old_umask = os.umask(0o077)
            try:
                target.mkdir(mode=0o700)
            finally:
                os.umask(old_umask)
            _apply_posix_mode(target, 0o700)
    except PrivateFileError:
        raise
    except OSError:
        _raise("private_directory_create_failed")
    verify_restrictive_permissions(target)
    return target


def create_private_staging_file(*, staging_root: Path, artifact_role: str) -> PrivateFileHandle:
    """Create an exclusive private staging file under staging_root."""
    _validate_artifact_role(artifact_role)
    root = _assert_no_symlink_components(staging_root)
    if not root.exists() or not root.is_dir():
        _raise("staging_root_missing")
    name = f"{artifact_role}-{uuid.uuid4().hex}.partial"
    path = root / name
    flags = os.O_CREAT | os.O_EXCL | os.O_RDWR
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        if sys.platform == "win32":
            fd = os.open(path, flags, 0o600)
            try:
                _apply_windows_restrictive_dacl(path, is_directory=False)
            except Exception:
                os.close(fd)
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
                raise
        else:
            old_umask = os.umask(0o077)
            try:
                fd = os.open(path, flags, 0o600)
            finally:
                os.umask(old_umask)
            try:
                os.fchmod(fd, 0o600)
            except OSError:
                os.close(fd)
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
                _raise("private_file_permission_failed")
    except PrivateFileError:
        raise
    except OSError:
        _raise("private_file_create_failed")
    handle = PrivateFileHandle(path=path, _fd=fd)
    try:
        verify_restrictive_permissions(path)
    except PrivateFileError:
        handle.close()
        cleanup_private_path(path)
        raise
    return handle


def atomic_replace_same_filesystem(source: Path, destination: Path) -> None:
    """Atomically replace destination with source on the same filesystem only."""
    src = _assert_no_symlink_components(source)
    dest = _absolute_without_follow(destination)
    _assert_no_symlink_components(dest.parent)
    if not src.exists() or not src.is_file():
        _raise("atomic_replace_source_missing")
    if not dest.parent.exists() or not dest.parent.is_dir():
        _raise("atomic_replace_destination_parent_missing")
    device_target = dest if dest.exists() else dest.parent
    if _filesystem_device_id(src) != _filesystem_device_id(device_target):
        _raise("cross_filesystem_rename_rejected")
    try:
        # Ensure content durability before rename.
        with open(src, "rb+", buffering=0) as handle:
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(src, dest)
        # Best-effort directory fsync of destination parent.
        try:
            dir_fd = os.open(dest.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except PrivateFileError:
        raise
    except OSError:
        _raise("atomic_replace_failed")


def cleanup_private_path(path: Path) -> None:
    """Remove a private staging path if present."""
    target = _absolute_without_follow(path)
    try:
        if target.is_symlink():
            target.unlink(missing_ok=True)
            return
        if target.is_file():
            target.unlink(missing_ok=True)
            return
        if target.is_dir():
            target.rmdir()
    except OSError:
        _raise("private_cleanup_failed")


def quarantine_partial_staging(path: Path, *, quarantine_root: Path) -> Path:
    """Move a partial staging file into quarantine with a generated name."""
    src = _assert_no_symlink_components(path)
    root = _assert_no_symlink_components(quarantine_root)
    if not src.exists() or not src.is_file():
        _raise("quarantine_source_missing")
    if not root.exists() or not root.is_dir():
        _raise("quarantine_root_missing")
    dest = root / f"quarantine-{uuid.uuid4().hex}.partial"
    if _filesystem_device_id(src) != _filesystem_device_id(root):
        _raise("cross_filesystem_rename_rejected")
    try:
        os.replace(src, dest)
    except OSError:
        _raise("quarantine_move_failed")
    return dest


def verify_restrictive_permissions(path: Path) -> None:
    """Verify path permissions match the platform private-file contract."""
    target = _absolute_without_follow(path)
    if not target.exists():
        _raise("permission_target_missing")
    if sys.platform == "win32":
        _verify_windows_dacl(target)
        return
    mode = stat.S_IMODE(target.stat().st_mode)
    expected = 0o700 if target.is_dir() else 0o600
    if mode != expected:
        _raise("posix_permissions_too_open")


def enumerate_allowed_windows_sids(path: Path) -> tuple[str, ...]:
    """Return allow-ACE SID strings for evidence (Windows only)."""
    if sys.platform != "win32":
        _raise("windows_dacl_unsupported")
    return _enumerate_windows_allow_sids(_absolute_without_follow(path))


# --- Windows DACL helpers (ctypes only; no host package import) ---


def _apply_windows_restrictive_dacl(path: Path, *, is_directory: bool) -> None:
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.windll.advapi32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    class TRUSTEE(ctypes.Structure):
        _fields_ = [
            ("pMultipleTrustee", ctypes.c_void_p),
            ("MultipleTrusteeOperation", wintypes.DWORD),
            ("TrusteeForm", wintypes.DWORD),
            ("TrusteeType", wintypes.DWORD),
            ("ptstrName", ctypes.c_void_p),
        ]

    class EXPLICIT_ACCESS(ctypes.Structure):
        _fields_ = [
            ("grfAccessPermissions", wintypes.DWORD),
            ("grfAccessMode", wintypes.DWORD),
            ("grfInheritance", wintypes.DWORD),
            ("Trustee", TRUSTEE),
        ]

    advapi32.ConvertStringSidToSidW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
    advapi32.ConvertStringSidToSidW.restype = wintypes.BOOL
    advapi32.SetEntriesInAclW.argtypes = [
        wintypes.ULONG,
        ctypes.POINTER(EXPLICIT_ACCESS),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.SetEntriesInAclW.restype = wintypes.DWORD
    advapi32.SetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    advapi32.SetNamedSecurityInfoW.restype = wintypes.DWORD
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    user_sid = _current_user_sid_pointer()
    system_sid = ctypes.c_void_p()
    admin_sid = ctypes.c_void_p()
    if not advapi32.ConvertStringSidToSidW(_SID_SYSTEM, ctypes.byref(system_sid)):
        _raise("windows_dacl_apply_failed")
    if not advapi32.ConvertStringSidToSidW(_SID_ADMINISTRATORS, ctypes.byref(admin_sid)):
        kernel32.LocalFree(system_sid)
        _raise("windows_dacl_apply_failed")

    inheritance = (
        _CONTAINER_INHERIT_ACE | _OBJECT_INHERIT_ACE if is_directory else _NO_INHERITANCE
    )
    entries = (EXPLICIT_ACCESS * 3)()
    sid_ptrs = (
        (user_sid, _TRUSTEE_IS_USER),
        (system_sid, _TRUSTEE_IS_USER),
        (admin_sid, _TRUSTEE_IS_GROUP),
    )
    try:
        for index, (sid_ptr, trustee_type) in enumerate(sid_ptrs):
            entries[index].grfAccessPermissions = _GENERIC_ALL
            entries[index].grfAccessMode = _SET_ACCESS
            entries[index].grfInheritance = inheritance
            entries[index].Trustee.pMultipleTrustee = None
            entries[index].Trustee.MultipleTrusteeOperation = _NO_MULTIPLE_TRUSTEE
            entries[index].Trustee.TrusteeForm = _TRUSTEE_IS_SID
            entries[index].Trustee.TrusteeType = trustee_type
            entries[index].Trustee.ptstrName = sid_ptr

        new_acl = ctypes.c_void_p()
        status = advapi32.SetEntriesInAclW(3, entries, None, ctypes.byref(new_acl))
        if status != 0 or not new_acl:
            _raise("windows_dacl_apply_failed")
        try:
            security_info = _DACL_SECURITY_INFORMATION | _PROTECTED_DACL_SECURITY_INFORMATION
            status = advapi32.SetNamedSecurityInfoW(
                str(path),
                _SE_FILE_OBJECT,
                security_info,
                None,
                None,
                new_acl,
                None,
            )
            if status != 0:
                _raise("windows_dacl_apply_failed")
        finally:
            kernel32.LocalFree(new_acl)
    finally:
        kernel32.LocalFree(system_sid)
        kernel32.LocalFree(admin_sid)
        # user_sid comes from token buffer lifetime below — freed with token buffer holder.


def _current_user_sid_pointer() -> int:
    """Return a PSID pointer into a process-lifetime buffer for the current user.

    The returned pointer remains valid for the duration of the calling process's
    temporary buffer kept on the function's stack via a module-level cache entry
    refreshed per call.
    """
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.windll.advapi32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)):
        _raise("windows_dacl_apply_failed")
    try:
        needed = wintypes.DWORD(0)
        advapi32.GetTokenInformation(token, _TOKEN_USER, None, 0, ctypes.byref(needed))
        if needed.value == 0:
            _raise("windows_dacl_apply_failed")
        buf = ctypes.create_string_buffer(needed.value)
        if not advapi32.GetTokenInformation(token, _TOKEN_USER, buf, needed.value, ctypes.byref(needed)):
            _raise("windows_dacl_apply_failed")
        # Keep buffer alive for the subsequent SetEntriesInAcl call by stashing it.
        global _USER_SID_BUFFER
        _USER_SID_BUFFER = buf
        return int(ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0])
    finally:
        kernel32.CloseHandle(token)


_USER_SID_BUFFER: object | None = None


def _verify_windows_dacl(path: Path) -> None:
    allowed = {_current_user_sid_string(), _SID_SYSTEM, _SID_ADMINISTRATORS, _SID_OWNER_RIGHTS}
    for sid in _enumerate_windows_allow_sids(path):
        if sid not in allowed:
            _raise("windows_permissions_too_open")


def _enumerate_windows_allow_sids(path: Path) -> tuple[str, ...]:
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.windll.advapi32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    advapi32.GetFileSecurityW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetFileSecurityW.restype = wintypes.BOOL
    advapi32.GetSecurityDescriptorDacl.argtypes = [
        wintypes.LPVOID,
        ctypes.POINTER(wintypes.BOOL),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.BOOL),
    ]
    advapi32.GetSecurityDescriptorDacl.restype = wintypes.BOOL
    advapi32.GetAclInformation.argtypes = [
        ctypes.c_void_p,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.c_int,
    ]
    advapi32.GetAclInformation.restype = wintypes.BOOL
    advapi32.GetAce.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
    advapi32.GetAce.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p)]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    file_str = str(path)
    needed = wintypes.DWORD(0)
    advapi32.GetFileSecurityW(file_str, _DACL_SECURITY_INFORMATION, None, 0, ctypes.byref(needed))
    if needed.value == 0:
        _raise("windows_dacl_unreadable")
    sd_buffer = ctypes.create_string_buffer(needed.value)
    if not advapi32.GetFileSecurityW(
        file_str, _DACL_SECURITY_INFORMATION, sd_buffer, needed.value, ctypes.byref(needed)
    ):
        _raise("windows_dacl_unreadable")

    dacl_present = wintypes.BOOL()
    dacl_ptr = ctypes.c_void_p()
    dacl_defaulted = wintypes.BOOL()
    if not advapi32.GetSecurityDescriptorDacl(
        sd_buffer, ctypes.byref(dacl_present), ctypes.byref(dacl_ptr), ctypes.byref(dacl_defaulted)
    ):
        _raise("windows_dacl_unreadable")
    if not dacl_present.value or not dacl_ptr:
        _raise("windows_dacl_unreadable")

    class _AclSizeInformation(ctypes.Structure):
        _fields_ = [
            ("AceCount", wintypes.DWORD),
            ("AclBytesInUse", wintypes.DWORD),
            ("AclBytesFree", wintypes.DWORD),
        ]

    size_info = _AclSizeInformation()
    if not advapi32.GetAclInformation(
        dacl_ptr, ctypes.byref(size_info), ctypes.sizeof(size_info), _ACL_SIZE_INFORMATION_CLASS
    ):
        _raise("windows_dacl_unreadable")

    found: list[str] = []
    for index in range(size_info.AceCount):
        ace_ptr = ctypes.c_void_p()
        if not advapi32.GetAce(dacl_ptr, index, ctypes.byref(ace_ptr)):
            _raise("windows_dacl_unreadable")
        ace_type = ctypes.cast(ace_ptr, ctypes.POINTER(ctypes.c_ubyte))[0]
        if ace_type != _ACCESS_ALLOWED_ACE_TYPE:
            continue
        sid_ptr = ctypes.c_void_p(ace_ptr.value + 8)
        sid_str_ptr = ctypes.c_wchar_p()
        if not advapi32.ConvertSidToStringSidW(sid_ptr, ctypes.byref(sid_str_ptr)):
            _raise("windows_dacl_unreadable")
        try:
            sid_str = sid_str_ptr.value or ""
        finally:
            kernel32.LocalFree(sid_str_ptr)
        found.append(sid_str)
    # Preserve encounter order while dropping inheritance duplicates.
    return tuple(dict.fromkeys(found))


def _current_user_sid_string() -> str:
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.windll.advapi32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p)]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)):
        _raise("windows_dacl_unreadable")
    try:
        needed = wintypes.DWORD(0)
        advapi32.GetTokenInformation(token, _TOKEN_USER, None, 0, ctypes.byref(needed))
        if needed.value == 0:
            _raise("windows_dacl_unreadable")
        buf = ctypes.create_string_buffer(needed.value)
        if not advapi32.GetTokenInformation(token, _TOKEN_USER, buf, needed.value, ctypes.byref(needed)):
            _raise("windows_dacl_unreadable")
        sid_ptr_value = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
        sid_str_ptr = ctypes.c_wchar_p()
        if not advapi32.ConvertSidToStringSidW(ctypes.c_void_p(sid_ptr_value), ctypes.byref(sid_str_ptr)):
            _raise("windows_dacl_unreadable")
        try:
            return sid_str_ptr.value or ""
        finally:
            kernel32.LocalFree(sid_str_ptr)
    finally:
        kernel32.CloseHandle(token)
