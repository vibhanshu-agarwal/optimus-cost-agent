"""Child census hook: which Python children of an ordinary pytest run ask for the real known folders?

Test support only, and inert unless a census asks for it: it does nothing without
`OPTIMUS_TEST_CHILD_CENSUS_DIR`. A census run puts this folder on PYTHONPATH for one ordinary
pytest invocation; nothing is installed in the environment and no launcher is changed.

In each Python child that inherits that environment it records a start line carrying the child's
own process identity (PID and creation time) and its parent's identity, arms the same refusal as
`tests.support.child_tripwire` on the product's real Windows known-folder adapter, and records an
end line. A child that asks for the real folders is refused and recorded; the real folders are
never resolved. In every hooked process it also records each `subprocess.Popen`: the test frame it
came from, whether the child's environment still carries this hook, and, once the child exists,
the child's identity read from the launch handle. A site is therefore attributed only to its own
launches, and each launch only by the child it started. Where the MAIN-5 guard is active the hook
stands aside. A failure here never changes the observed process.
"""

import os
import sys

_directory = os.environ.get("OPTIMUS_TEST_CHILD_CENSUS_DIR")
_TARGET = "optimus.acp.trusted_paths"
REFUSAL = "TEST_CHILD_CENSUS_REAL_ADAPTER"

if _directory and not getattr(sys, "_main5_guard_activated", False):
    try:
        import atexit
        import functools
        import importlib.util
        import json
        import subprocess

        _file = os.path.join(_directory, f"{os.getpid()}-{os.urandom(3).hex()}.jsonl")
        _test = os.environ.get("PYTEST_CURRENT_TEST", "")[:300]
        _calls = [0]
        _launches = [0]

        def _note(event, **fields):
            try:
                with open(_file, "a", encoding="utf-8") as stream:
                    stream.write(json.dumps({"event": event, "pid": os.getpid(), "test": _test, **fields}) + "\n")
            except OSError:
                pass

        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            # Explicit signatures: handles are pointer-sized and must never pass through a default c_int.
            _kernel32.GetCurrentProcess.argtypes = ()
            _kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            _kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
            _kernel32.OpenProcess.restype = wintypes.HANDLE
            _kernel32.GetProcessTimes.argtypes = (wintypes.HANDLE, *(ctypes.POINTER(wintypes.FILETIME),) * 4)
            _kernel32.GetProcessTimes.restype = wintypes.BOOL
            _kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
            _kernel32.CloseHandle.restype = wintypes.BOOL

            def _creation_time(handle):
                """A process's creation time from its handle (FILETIME as one integer), or None when the query fails."""
                try:
                    times = [wintypes.FILETIME() for _ in range(4)]
                    if not _kernel32.GetProcessTimes(wintypes.HANDLE(int(handle)), *(ctypes.byref(each) for each in times)):
                        return None
                    return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
                except Exception:  # noqa: BLE001
                    return None

            _ntdll = ctypes.WinDLL("ntdll", use_last_error=True)

            class _BasicInformation(ctypes.Structure):
                _fields_ = [("ExitStatus", ctypes.c_long), ("PebBaseAddress", ctypes.c_void_p), ("AffinityMask", ctypes.c_size_t),
                            ("BasePriority", ctypes.c_long), ("UniqueProcessId", ctypes.c_size_t), ("InheritedFromUniqueProcessId", ctypes.c_size_t)]

            _ntdll.NtQueryInformationProcess.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.ULONG, ctypes.POINTER(wintypes.ULONG))
            _ntdll.NtQueryInformationProcess.restype = ctypes.c_long

            def _own_creation_time():
                return _creation_time(_kernel32.GetCurrentProcess())

            def _parent_of(pid):
                """A process's creation time and its parent's PID, read through one handle, or (None, None)."""
                handle = _kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
                if not handle:
                    return None, None
                try:
                    created = _creation_time(handle)
                    information, returned = _BasicInformation(), wintypes.ULONG(0)
                    status = _ntdll.NtQueryInformationProcess(handle, 0, ctypes.byref(information), ctypes.sizeof(information), ctypes.byref(returned))
                    return created, (int(information.InheritedFromUniqueProcessId) if status == 0 else None)
                finally:
                    _kernel32.CloseHandle(handle)

            def _launched_creation_time(process):
                return _creation_time(process._handle)  # noqa: SLF001 - the handle Popen holds on the child
        else:
            def _stat_fields(pid):
                try:
                    with open(f"/proc/{pid}/stat", encoding="utf-8") as stream:
                        return stream.read().rsplit(")", 1)[1].split()
                except (OSError, IndexError):
                    return None

            def _start_ticks(pid):
                """A process's start time in clock ticks since boot, from procfs, or None."""
                fields = _stat_fields(pid)
                try:
                    return int(fields[19]) if fields else None
                except (ValueError, IndexError):
                    return None

            def _own_creation_time():
                return _start_ticks(os.getpid())

            def _parent_of(pid):
                fields = _stat_fields(pid)
                try:
                    return (int(fields[19]), int(fields[1])) if fields else (None, None)
                except (ValueError, IndexError):
                    return None, None

            def _launched_creation_time(process):
                return _start_ticks(process.pid)

        def _ancestors(limit=6):
            """This process's ancestors, nearest first, as (pid, creation time) pairs read through handles.

            The chain stops at the first ancestor whose identity cannot be read or whose creation time
            is later than its descendant's (a reused PID): a launch binds to a child only on an exact
            identity somewhere in this chain, so a broken link ends it rather than guessing.
            """

            chain, pid, younger = [], os.getppid(), _own_creation_time()
            for _ in range(limit):
                if not pid or younger is None:
                    break
                created, above = _parent_of(pid)
                if created is None or created > younger:
                    chain.append({"pid": pid, "creation_time": None})
                    break
                chain.append({"pid": pid, "creation_time": created})
                pid, younger = above, created
            return chain

        def _refuse():
            _calls[0] += 1
            _note("real_adapter_call", count=_calls[0])
            raise RuntimeError(REFUSAL)

        class _Finder:
            busy = False

            def find_spec(self, name, path=None, target=None):
                if name != _TARGET or self.busy:
                    return None
                self.busy = True
                try:
                    spec = importlib.util.find_spec(name)
                finally:
                    self.busy = False
                if spec is None or spec.loader is None:
                    return None
                execute = spec.loader.exec_module

                def exec_module(module):
                    execute(module)
                    # A pytest session installs its own guard on this adapter (its conftest imports the
                    # guard module first); leave that one alone. Any other process is armed, whether
                    # or not it happens to import pytest.
                    armed = "tools.testing.run_context_guard" not in sys.modules
                    if armed:
                        module._real_windows_known_folders = _refuse
                    _note("trusted_paths_imported", armed=armed)

                spec.loader.exec_module = exec_module
                return spec

        def _launch_site():
            frame = sys._getframe(2)
            while frame is not None:
                name = frame.f_code.co_filename.replace("\\", "/")
                marker = name.find("/tests/")
                if marker >= 0 and "/tests/support/child_census/" not in name:
                    return name[marker + 1:], frame.f_code.co_name, frame.f_lineno
                frame = frame.f_back
            return None, None, None

        _real_init = subprocess.Popen.__init__

        @functools.wraps(_real_init)
        def _init(self, args, *positional, **options):
            # The launching side: which test frame started a child, whether the child's environment
            # still carries this hook, and, once the child exists, which process it is. The launch
            # itself is untouched; a failed launch is recorded without a child.
            env = options.get("env", positional[9] if len(positional) > 9 else None)
            effective = os.environ if env is None else env
            fields = {}
            try:
                _launches[0] += 1
                file, function, line = _launch_site()
                program = args[0] if isinstance(args, (list, tuple)) and args else args
                fields = dict(
                    launch=_launches[0], site_file=file, site_function=function, site_line=line,
                    hook_env=bool(effective.get("OPTIMUS_TEST_CHILD_CENSUS_DIR")) and "child_census" in str(effective.get("PYTHONPATH", "")),
                    program=os.path.basename(str(program))[:80], launching_test=os.environ.get("PYTEST_CURRENT_TEST", "")[:300],
                )
            except Exception:  # noqa: BLE001 - never change the launch
                pass
            try:
                _real_init(self, args, *positional, **options)
            except BaseException:
                _note("launch", **fields, child=None)
                raise
            try:
                child = {"pid": self.pid, "creation_time": _launched_creation_time(self)}
            except Exception:  # noqa: BLE001
                child = {"pid": getattr(self, "pid", None), "creation_time": None}
            _note("launch", **fields, child=child)

        subprocess.Popen.__init__ = _init
        sys.meta_path.insert(0, _Finder())
        _chain = _ancestors()
        _note("start", base_interpreter=sys.prefix == sys.base_prefix, armed=True, creation_time=_own_creation_time(),
              ppid=os.getppid(), parent_creation_time=_chain[0]["creation_time"] if _chain else None, ancestors=_chain)
        atexit.register(lambda: _note(
            "end", is_pytest="pytest" in sys.modules, trusted_paths_imported=_TARGET in sys.modules,
            real_adapter_calls=_calls[0], script=os.path.basename(sys.argv[0]) if sys.argv and sys.argv[0] not in ("-c", "-m") else (sys.argv[0] if sys.argv else ""),
        ))
    except Exception:  # noqa: BLE001 - an observer must never change the observed process
        pass
