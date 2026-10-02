"""Default protection of the real application folders inside a pytest process.

Test tooling only. In an active default-selection session on Windows this module:

- learns the real protected folders from the operating system, through the product's own adapter;
- makes that real adapter refuse, so nothing in the pytest process resolves the real folders;
- denies writes under the protected folders through a Python audit hook; and
- gives each test its own synthetic folders when a test passes none.

It protects the pytest process only. A child process is a separate interpreter and is not covered
by this module. When the MAIN-5 guard is already active it is left in force and nothing here is
installed: its refusal is stricter and must not be replaced by a permissive default.

Limits, stated so no claim exceeds them: paths are compared after lexical normalisation, so a
junction that points into a protected folder is not detected, and writes made through an already
open descriptor are not classified.
"""

from __future__ import annotations

import hashlib
import ntpath
import os
import sys
from pathlib import Path
from types import SimpleNamespace

REAL_ADAPTER_REFUSAL = "TEST_RUN_CONTEXT_REAL_ADAPTER"
WRITE_REFUSAL = "TEST_RUN_CONTEXT_WRITE"
_CONFIG_DIR_NAME = "optimus-cost-agent"
_KEYRING_DIR_NAME = "Python Keyring"
_FIRST_PATH_EVENTS = frozenset({"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.utime", "os.truncate"})
_SECOND_PATH_EVENTS = frozenset({"os.link", "os.symlink", "_winapi.CopyFile2", "_winapi.CreateJunction"})
_EVENTS = _FIRST_PATH_EVENTS | _SECOND_PATH_EVENTS | {"open", "os.rename", "sqlite3.connect", "_winapi.CreateFile"}
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
_WINAPI_WRITE_ACCESS = 0x40000000 | 0x10000000 | 0x02000000 | 0x00010000 | 0x000C0116

_mode = "not_installed"
_enabled = False
_hook_added = False
_protected_names: tuple[str, ...] = ()
_redirected_modules: tuple[object, ...] = ()


def mode() -> str:
    """`pytest_process_guard`, `main5_guard_present`, `unsupported_platform` or `not_installed`."""
    return _mode


def protected_roots() -> tuple[str, ...]:
    """The normalised real folders this guard denies writes to. Empty unless installed."""
    return _protected_names


def _refuse_real_adapter() -> object:
    raise RuntimeError(REAL_ADAPTER_REFUSAL)


def _normalized(path: object) -> str | None:
    try:
        value = os.fsdecode(os.fspath(path))  # type: ignore[arg-type]
    except TypeError:
        return None
    value = value.replace("/", "\\")
    if value.casefold().startswith("\\\\.\\pipe\\"):
        return None
    if value.startswith("\\\\?\\"):
        value = value[4:]
    return ntpath.normcase(ntpath.abspath(value))


def _is_protected(path: object) -> bool:
    name = _normalized(path)
    if name is None:
        return False
    return any(name == root or name.startswith(root + "\\") for root in _protected_names)


def _audit(event: str, args: tuple[object, ...]) -> None:
    if not _enabled or event not in _EVENTS:
        return
    paths: tuple[object, ...] = ()
    if event == "open":
        if len(args) >= 3 and not isinstance(args[0], int):
            mode_text, flags = args[1], args[2]
            writing = isinstance(mode_text, str) and any(char in mode_text for char in "wax+")
            if isinstance(flags, int):
                writing = writing or bool(flags & _WRITE_FLAGS)
            if writing:
                paths = (args[0],)
    elif event in _FIRST_PATH_EVENTS:
        paths = args[:1]
    elif event == "os.rename":
        paths = args[:2]
    elif event in _SECOND_PATH_EVENTS:
        paths = args[1:2]
    elif event == "sqlite3.connect":
        if args and args[0] != ":memory:":
            paths = args[:1]
    elif event == "_winapi.CreateFile":
        if len(args) >= 4 and isinstance(args[1], int) and isinstance(args[3], int):
            if args[1] & _WINAPI_WRITE_ACCESS or args[3] in {1, 2, 4, 5}:
                paths = args[:1]
    if any(_is_protected(path) for path in paths):
        raise PermissionError(WRITE_REFUSAL)


def install() -> str:
    """Install the pytest-process guard for an active default-selection session. Idempotent."""
    global _mode, _enabled, _hook_added, _protected_names, _redirected_modules
    if _mode != "not_installed":
        return _mode
    if sys.platform != "win32":
        _mode = "unsupported_platform"
        return _mode
    if getattr(sys, "_main5_guard_activated", False):
        _mode = "main5_guard_present"
        return _mode

    from optimus.acp import __main__ as acp_main
    from optimus.acp import launch_approval_cli, operator_paths, trusted_paths

    folders = trusted_paths._real_windows_known_folders()
    roaming, local = getattr(folders, "roaming_appdata", None), getattr(folders, "local_appdata", None)
    if roaming is None or local is None:
        raise RuntimeError("TEST_RUN_CONTEXT_REAL_ROOTS_UNAVAILABLE")
    roots = [Path(roaming) / _CONFIG_DIR_NAME, Path(local) / _CONFIG_DIR_NAME, Path(local) / _KEYRING_DIR_NAME]
    program_data = os.environ.get("ProgramData")
    if program_data:
        roots.append(Path(program_data) / _KEYRING_DIR_NAME)
    _protected_names = tuple(name for name in (_normalized(root) for root in roots) if name)

    trusted_paths._real_windows_known_folders = _refuse_real_adapter
    _redirected_modules = (trusted_paths, operator_paths, acp_main, launch_approval_cli)
    if not _hook_added:
        sys.addaudithook(_audit)
        _hook_added = True
    _enabled = True
    _mode = "pytest_process_guard"
    return _mode


def redirect_for_test(monkeypatch: object, session_root: Path, nodeid: str) -> None:
    """Give one test its own synthetic folders whenever it resolves the roots without passing any.

    A test that supplies its own adapter, or replaces the real adapter with a fake, keeps exactly
    the behaviour it asked for.
    """
    if _mode != "pytest_process_guard":
        return
    from optimus.acp import trusted_paths

    known_root = session_root / hashlib.sha256(nodeid.encode("utf-8")).hexdigest()[:16]
    original = trusted_paths.resolve_trusted_operator_roots

    def resolve_with_default_folders(*, platform_name: str, windows_known_folders=None, posix_home=None):  # noqa: ANN001, ANN202
        selected = windows_known_folders
        if platform_name == "win32" and selected is None and trusted_paths._real_windows_known_folders is _refuse_real_adapter:
            roaming, local = known_root / "Roaming", known_root / "Local"
            roaming.mkdir(parents=True, exist_ok=True)
            local.mkdir(parents=True, exist_ok=True)
            selected = SimpleNamespace(roaming_appdata=roaming, local_appdata=local)
        return original(platform_name=platform_name, windows_known_folders=selected, posix_home=posix_home)

    modules = list(_redirected_modules)
    capture_tool = sys.modules.get("tools.run_plan996_acpx_security_evidence")
    if capture_tool is not None:
        modules.append(capture_tool)
    for module in modules:
        monkeypatch.setattr(module, "resolve_trusted_operator_roots", resolve_with_default_folders)  # type: ignore[attr-defined]
