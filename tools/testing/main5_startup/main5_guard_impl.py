"""MAIN-5 test startup: compose the established port guard with root guards."""

from __future__ import annotations

import _winapi
import ctypes
import importlib.abc
import importlib.machinery
import json
import msvcrt
import ntpath
import os
import re
import runpy
import sys
import uuid
from ctypes import wintypes
from json import dumps as _dumps
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

_config_path = Path(__file__).with_name("main5-config.json")
_attempt_mode = _config_path.is_file()
_config = json.loads(_config_path.read_text(encoding="utf-8")) if _attempt_mode else {}
_env_override_ignored = _attempt_mode and any(
    os.environ.get(name) and os.environ[name] != _config.get(config_name)
    for name, config_name in (
        ("MAIN5_GUARD_LOG_DIR", "log_dir"),
        ("MAIN5_CONTROL_PROTECTED_ROOT", "control_protected_root"),
        ("MAIN5_PORT_GUARD", "port_guard"),
        ("X1_GUARD_LOG", "X1_GUARD_LOG"),
        ("KEYRING_AUDIT_LOG", "KEYRING_AUDIT_LOG"),
    )
)
for _key in ("X1_GUARD_LOG", "KEYRING_AUDIT_LOG"):
    if _key in _config and (_attempt_mode or not os.environ.get(_key)):
        os.environ[_key] = _config[_key]

_log_dir_text = _config.get("log_dir") if _attempt_mode else os.environ.get("MAIN5_GUARD_LOG_DIR")
if not _log_dir_text:
    raise RuntimeError("MAIN5_GUARD_LOG_DIR is required")
_log_dir = Path(_log_dir_text)
if not _log_dir.is_dir():
    raise RuntimeError("MAIN5_GUARD_LOG_DIR must already exist")
_log_file = _log_dir / f"{os.getpid()}-{uuid.uuid4().hex}.jsonl"
_log_file.touch(exist_ok=False)
_census_file = _log_file.with_suffix(".census")
_census_fd = os.open(_census_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
_spawn_file = _log_file.with_suffix(".spawn")
_spawn_fd = os.open(_spawn_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND, 0o600)
_seen_events: set[str] = set()


class _FILETIME(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.GetProcessTimes.argtypes = [
    wintypes.HANDLE, ctypes.POINTER(_FILETIME), ctypes.POINTER(_FILETIME),
    ctypes.POINTER(_FILETIME), ctypes.POINTER(_FILETIME),
]
_kernel32.GetProcessTimes.restype = wintypes.BOOL
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL
_kernel32.GetCurrentProcess.restype = wintypes.HANDLE


def _creation_time(handle: object) -> tuple[int | None, int | None]:
    created, exited, kernel, user = (_FILETIME() for _ in range(4))
    if not _kernel32.GetProcessTimes(
        int(handle), ctypes.byref(created), ctypes.byref(exited),
        ctypes.byref(kernel), ctypes.byref(user),
    ):
        return None, ctypes.get_last_error()
    return (int(created.high) << 32) | int(created.low), None


def _parent_creation_time(pid: int) -> tuple[int | None, int | None]:
    handle = _kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None, ctypes.get_last_error()
    try:
        return _creation_time(handle)
    finally:
        _kernel32.CloseHandle(handle)


def _refuse(code: str, error_type: str | None = None) -> None:
    row = {
        "kind": "guard_refusal", "pid": os.getpid(),
        "creation_time": globals().get("_own_creation"), "code": code,
    }
    if error_type is not None:
        row["error_type"] = error_type
    try:
        with _log_file.open("a", encoding="utf-8") as stream:
            stream.write(_dumps(row, separators=(",", ":")) + "\n")
    except BaseException:
        os.write(2, b"MAIN5_REFUSAL_LEDGER_FAILED\n")
        os._exit(87)
    os._exit(86)


def _write_spawn(row: dict[str, object]) -> None:
    try:
        os.write(_spawn_fd, (_dumps(row, separators=(",", ":")) + "\n").encode("utf-8"))
    except BaseException:
        _refuse("spawn_ledger_failed")


_own_creation, _own_creation_error = _creation_time(_kernel32.GetCurrentProcess())
_parent_creation, _parent_creation_error = _parent_creation_time(os.getppid())
_begin = {
    "pid": os.getpid(),
    "parent_pid": os.getppid(),
    "creation_time": _own_creation,
    "creation_error": _own_creation_error,
    "parent_creation_time": _parent_creation,
    "parent_creation_error": _parent_creation_error,
    "image": sys._base_executable,
    "runner_direct_role": os.environ.pop("MAIN5_DIRECT_LAUNCH", None),
    "flags": {
        "no_site": bool(sys.flags.no_site),
        "isolated": bool(sys.flags.isolated),
        "ignore_environment": bool(sys.flags.ignore_environment),
    },
}
_write_spawn({"kind": "guard_begin", **_begin})
_port_guard_text = _config.get("port_guard") if _attempt_mode else os.environ.get("MAIN5_PORT_GUARD")
if not _port_guard_text:
    _refuse("port_guard_missing")
_PORT_GUARD = Path(_port_guard_text)
if not _PORT_GUARD.is_file():
    _refuse("port_guard_missing")
try:
    runpy.run_path(str(_PORT_GUARD), run_name="_main5_port_guard")
except BaseException as exc:
    _refuse("port_guard_start_failed", type(exc).__name__)
_write_spawn({"kind": "guard_start", **_begin, "env_override_ignored": bool(_env_override_ignored)})


def _created_image(process_handle: object) -> str:
    size = wintypes.DWORD(32768)
    buffer = ctypes.create_unicode_buffer(size.value)
    query = ctypes.windll.kernel32.QueryFullProcessImageNameW
    query.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    query.restype = wintypes.BOOL
    if not query(int(process_handle), 0, buffer, ctypes.byref(size)):
        return "<unavailable>"
    return buffer.value


def _interpreter_shape(command_line: object) -> tuple[dict[str, bool], str]:
    result = {"no_site": False, "isolated": False, "ignore_environment": False}
    if not isinstance(command_line, str):
        return result, "unknown"
    count = ctypes.c_int()
    parse = ctypes.windll.shell32.CommandLineToArgvW
    parse.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    parse.restype = ctypes.POINTER(ctypes.c_wchar_p)
    arguments = parse(command_line, ctypes.byref(count))
    if not arguments:
        return result, "unknown"
    try:
        shape = "unknown"
        index = 1
        while index < count.value:
            option = arguments[index]
            if option in {"-V", "-VV", "--version"}:
                shape = "version_probe"
                break
            if option in {"-h", "--help"}:
                shape = "help_probe"
                break
            if option == "--":
                shape = "script" if index + 1 < count.value else "unknown"
                break
            if not option.startswith("-") or option == "-":
                shape = "script"
                break
            if option.startswith("--"):
                index += 1
                continue
            letters = option[1:]
            result["no_site"] |= "S" in letters
            result["isolated"] |= "I" in letters
            result["ignore_environment"] |= "E" in letters
            if "c" in letters:
                shape = "code"
                break
            if "m" in letters:
                shape = "module"
                break
            if letters in {"W", "X"}:
                # The next argument is an option value, not a script path.
                index += 2
                continue
            index += 1
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(arguments, ctypes.c_void_p))
    return result, shape


_original_create_process = _winapi.CreateProcess
_original_get_exit_code = _winapi.GetExitCodeProcess
_handles: dict[int, tuple[int, int | None]] = {}


def _recorded_create_process(*args, **kwargs):
    created = _original_create_process(*args, **kwargs)
    process_handle, _thread_handle, child_pid, _thread_id = created
    image = _created_image(process_handle)
    created_at, creation_error = _creation_time(process_handle)
    flags, shape = _interpreter_shape(args[1] if len(args) > 1 else kwargs.get("command_line"))
    _handles[int(process_handle)] = (child_pid, created_at)
    _write_spawn({
        "kind": "create_process", "parent_pid": os.getpid(),
        "parent_creation_time": _own_creation,
        "child_pid": child_pid, "creation_time": created_at,
        "creation_error": creation_error, "image": image, "flags": flags,
        "shape": shape,
    })
    return created


def _recorded_get_exit_code(process_handle: object) -> int:
    result = _original_get_exit_code(process_handle)
    identity = _handles.get(int(process_handle))
    if identity is not None and result != _winapi.STILL_ACTIVE:
        _write_spawn({
            "kind": "exit_code", "child_pid": identity[0],
            "creation_time": identity[1], "exit_code": result,
        })
    return result


_winapi.CreateProcess = _recorded_create_process
_winapi.GetExitCodeProcess = _recorded_get_exit_code


def _record(code: str, event: str | None = None) -> None:
    test_id = os.environ.get("MAIN5_TEST_ID") or os.environ.get("PYTEST_CURRENT_TEST") or "<not-propagated>"
    row = {"pid": os.getpid(), "creation_time": _own_creation, "code": code, "test": test_id}
    if event is not None:
        row["event"] = event
    try:
        with _log_file.open("a", encoding="utf-8") as stream:
            stream.write(_dumps(row, separators=(",", ":")) + "\n")
    except BaseException:
        _refuse("guard_log_failed")


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _known_folder(folder_id: _GUID) -> Path:
    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32
    shell32.SHGetKnownFolderPath.argtypes = [
        ctypes.POINTER(_GUID), wintypes.DWORD, wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    shell32.SHGetKnownFolderPath.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    path_ptr = ctypes.c_wchar_p()
    result = shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(path_ptr))
    try:
        if result != 0 or not path_ptr.value:
            raise RuntimeError("MAIN5_KNOWN_FOLDERS_UNAVAILABLE")
        return Path(path_ptr.value)
    finally:
        if path_ptr:
            ole32.CoTaskMemFree(path_ptr)


_roaming_appdata = _known_folder(_GUID(
    0x3EB685DB, 0x65F9, 0x4CF6,
    (ctypes.c_ubyte * 8)(0xA0, 0x3A, 0xE3, 0xEF, 0x65, 0x72, 0x9F, 0x3D),
))
_local_appdata = _known_folder(_GUID(
    0xF1B32785, 0x6FBA, 0x4FCF,
    (ctypes.c_ubyte * 8)(0x9D, 0x55, 0x7B, 0x8E, 0x7F, 0x15, 0x70, 0x91),
))
_program_data = os.environ.get("ProgramData") or _config.get("program_data")
if not _program_data:
    raise RuntimeError("MAIN5_PROGRAM_DATA_UNAVAILABLE")
_protected = [
    _roaming_appdata / "optimus-cost-agent",
    _local_appdata / "optimus-cost-agent",
    _local_appdata / "Python Keyring",
    Path(_program_data) / "Python Keyring",
]
_control_root = _config.get("control_protected_root") if _attempt_mode else os.environ.get("MAIN5_CONTROL_PROTECTED_ROOT")
if _control_root:
    _protected.append(Path(_control_root))


def _local_path_name(value: str) -> str:
    # Windows accepts slash aliases; classify them before any resolution or I/O.
    value = value.replace("/", "\\")
    if value.casefold().startswith("\\\\?\\"):
        value = value[4:]
        # Extended DOS disk paths are required for disk-handle classification.
        if not (ntpath.isabs(value) and ntpath.splitdrive(value)[0].endswith(":")):
            raise ValueError("MAIN5_UNCLASSIFIABLE_EXTENDED_PATH")
    if value.startswith("\\\\") or value.casefold().startswith(
        ("\\??\\", "\\device\\", "\\dosdevices\\", "\\global??\\")
    ):
        raise ValueError("MAIN5_NETWORK_OR_DEVICE_PATH")
    if ntpath.splitdrive(value)[0] and not ntpath.isabs(value):
        raise ValueError("MAIN5_DRIVE_RELATIVE_PATH")
    return value


def _normalized(path: object) -> str:
    value = os.fspath(path)
    if not isinstance(value, str):
        raise TypeError("MAIN5_UNCLASSIFIABLE_PATH")
    value = _local_path_name(value)
    # A mapped drive or reparse point can resolve from a local spelling to UNC.
    resolved = _local_path_name(str(Path(value).resolve(strict=False)))
    return ntpath.normcase(resolved)


_protected_names = tuple(_normalized(root) for root in _protected)
if any(ntpath.commonpath((_normalized(_log_dir), root)) == root for root in _protected_names):
    raise RuntimeError("MAIN5_LOG_WITHIN_PROTECTED_ROOT")


def _is_protected(path: object) -> bool:
    if not isinstance(path, int):
        raw = os.fspath(path)
        if isinstance(raw, str) and raw.casefold().startswith("\\\\.\\pipe\\"):
            # CreateFile opens named-pipe IPC with write access; it is not a file.
            return False
        if isinstance(raw, str) and ntpath.normcase(raw) in {"nul", "\\\\.\\nul"}:
            # logging.FileHandler resolves os.devnull to the Windows NUL device.
            return False
    if isinstance(path, int):
        handle = wintypes.HANDLE(msvcrt.get_osfhandle(path))
        kernel = ctypes.windll.kernel32
        kernel.GetFileType.argtypes = [wintypes.HANDLE]
        kernel.GetFileType.restype = wintypes.DWORD
        kind = kernel.GetFileType(handle)
        if kind in (2, 3):  # console/character device or pipe: no filesystem path
            return False
        if kind != 1:
            raise TypeError("MAIN5_UNCLASSIFIABLE_HANDLE")
        kernel.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
        kernel.GetFinalPathNameByHandleW.restype = wintypes.DWORD
        buffer = ctypes.create_unicode_buffer(32768)
        length = kernel.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
        if not length or length >= len(buffer):
            raise OSError("MAIN5_HANDLE_PATH_UNAVAILABLE")
        path = buffer.value
        if path.startswith("\\\\?\\UNC\\"):
            path = "\\\\" + path[8:]
        elif path.startswith("\\\\?\\"):
            path = path[4:]
    name = _normalized(path)
    for root in _protected_names:
        try:
            if ntpath.commonpath((name, root)) == root:
                return True
        except ValueError:
            continue
    return False


def _sqlite_target(database: object) -> object | None:
    if database == ":memory:":
        return None
    if not isinstance(database, str) or not database.casefold().startswith("file:"):
        return database
    parts = urlsplit(database)
    if parts.scheme.casefold() != "file" or "#" in database:
        raise ValueError("MAIN5_SQLITE_URI_MALFORMED")
    if parts.netloc not in ("", "localhost"):
        raise ValueError("MAIN5_SQLITE_URI_REMOTE_AUTHORITY")
    query = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True, errors="strict")
    keys = [key for key, _ in query]
    if len(keys) != len(set(keys)) or not set(keys) <= {"mode", "cache"}:
        raise ValueError("MAIN5_SQLITE_URI_PARAMS")
    if dict(query).get("mode") == "memory":
        return None
    path = unquote(parts.path, errors="strict")
    if re.match(r"^/[A-Za-z]:", path):
        path = path[1:]
    if not path:
        raise ValueError("MAIN5_SQLITE_URI_EMPTY_PATH")
    return path


def _audit(event: str, args: tuple[object, ...]) -> None:
    if event in {"subprocess.Popen", "os.system", "os.startfile"} or event.startswith(("os.spawn", "os.exec")):
        _write_spawn({"kind": "audit_spawn", "parent_pid": os.getpid(), "event": event})
    if event not in _seen_events:
        _seen_events.add(event)
        if not re.fullmatch(r"[A-Za-z0-9_./]+", event):
            event = "UNCLASSIFIED_EVENT_NAME"
        try:
            os.write(_census_fd, (event + "\n").encode("ascii"))
        except OSError:
            _refuse("census_log_failed")
    paths: tuple[object, ...] = ()
    ambiguous = False
    if event == "open":
        if len(args) < 3:
            ambiguous = True
        else:
            mode, flags = args[1], args[2]
            writing = isinstance(mode, str) and any(char in mode for char in "wax+")
            if isinstance(flags, int):
                writing = writing or bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if writing:
                paths = (args[0],)
    elif event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.utime", "os.truncate"}:
        paths = args[:1]
        dir_fd_index = {"os.mkdir": 2, "os.remove": 1, "os.rmdir": 1, "os.chmod": 2, "os.utime": 3}.get(event)
        if not paths or (dir_fd_index is not None and (len(args) <= dir_fd_index or args[dir_fd_index] not in (-1, None))):
            ambiguous = True
    elif event == "os.rename":
        paths = args[:2]
        if len(args) < 4 or args[2] not in (-1, None) or args[3] not in (-1, None):
            ambiguous = True
    elif event == "_winapi.CopyFile2":
        paths = args[1:2]
        ambiguous = len(args) < 2
    elif event == "_winapi.CreateFile":
        if len(args) < 5 or not isinstance(args[1], int) or not isinstance(args[3], int) or not isinstance(args[4], int):
            ambiguous = True
        else:
            write_access = 0x40000000 | 0x10000000 | 0x02000000 | 0x00010000 | 0x000C0116
            creates_or_truncates = args[3] in {1, 2, 4, 5}
            deletes_on_close = bool(args[4] & 0x04000000)
            if args[1] & write_access or creates_or_truncates or deletes_on_close:
                paths = args[:1]
    elif event == "_winapi.CreateJunction":
        paths = args[1:2]
        ambiguous = len(args) < 2
    elif event in {"os.link", "os.symlink"}:
        paths = args[1:2]
        if len(args) < 2:
            ambiguous = True
        elif event == "os.link" and (len(args) < 4 or args[2] not in (-1, None) or args[3] not in (-1, None)):
            ambiguous = True
        elif event == "os.symlink" and len(args) >= 3 and args[2] not in (-1, None):
            ambiguous = True
    elif event == "sqlite3.connect":
        if not args:
            ambiguous = True
        else:
            try:
                target = _sqlite_target(args[0])
            except (TypeError, ValueError, OSError):
                ambiguous = True
            else:
                if target is not None:
                    paths = (target,)
    if not paths and not ambiguous:
        return
    try:
        blocked = ambiguous or any(_is_protected(path) for path in paths)
    except (TypeError, ValueError, OSError):
        blocked = True
    if blocked:
        _record("MAIN5_WRITE", event)
        raise PermissionError("MAIN5_WRITE")


sys.addaudithook(_audit)


def _refuse_real_known_folders() -> None:
    _record("MAIN5_REAL_ADAPTER")
    raise RuntimeError("MAIN5_REAL_ADAPTER")


class _TrustedPathsLoader(importlib.abc.Loader):
    def __init__(self, original: importlib.abc.Loader) -> None:
        self._original = original

    def __getattr__(self, name: str):
        return getattr(self._original, name)

    def create_module(self, spec):
        create = getattr(self._original, "create_module", None)
        return create(spec) if create is not None else None

    def exec_module(self, module) -> None:
        try:
            self._original.exec_module(module)
            module._real_windows_known_folders = _refuse_real_known_folders
            patched = module._real_windows_known_folders is _refuse_real_known_folders
        except BaseException:
            _refuse("trusted_paths_patch_failed")
        if not patched:
            _refuse("trusted_paths_patch_failed")


class _TrustedPathsFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != "optimus.acp.trusted_paths":
            return None
        try:
            spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        except BaseException:
            _refuse("trusted_paths_patch_failed")
        if spec is None or spec.loader is None or not hasattr(spec.loader, "exec_module"):
            _refuse("trusted_paths_patch_failed")
        spec.loader = _TrustedPathsLoader(spec.loader)
        return spec


if "optimus.acp.trusted_paths" in sys.modules:
    _refuse("trusted_paths_preloaded")
sys.meta_path.insert(0, _TrustedPathsFinder())
