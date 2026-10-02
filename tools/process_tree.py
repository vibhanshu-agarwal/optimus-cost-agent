"""Start a child process so that it and every descendant it ever creates can be killed together.

`taskkill /T` kills the tree it finds by walking parent pids at that moment. A descendant
created during the walk, or one whose parent has already exited, is not found: it survives and
keeps any inherited capture pipes open, so the caller blocks until it exits on its own (P11-FU-33
batch, 2026-10-02: a guarded full run's ledger showed a grandchild started 0.36 s into the kill).

Windows: the child is created suspended, assigned to a new job object and only then resumed, so
every descendant belongs to the job from its first instruction, and `kill_tree` terminates the
whole job in one call. Assigning after an unsuspended start would leave the same window open
whenever this process is descheduled between creating the child and assigning it. The job
neither kills on close nor allows breakaway: closing it leaves running processes alone, and a
descendant that asks to break away fails to start instead of escaping.

POSIX: the child leads a new session, and `kill_tree` signals its whole process group.

`popen` returns a plain `subprocess.Popen`, so callers keep their types; `kill_tree` refuses a
process this module did not start rather than falling back to a partial kill.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import weakref
from collections.abc import Sequence
from typing import Any

_CREATE_SUSPENDED = 0x00000004
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001
_THREAD_SUSPEND_RESUME = 0x0002
_SNAPSHOT_THREADS = 0x00000004
_RESUME_FAILED = 0xFFFFFFFF
_KILLED_EXIT_CODE = 1  # what `taskkill /F` reported, so callers see no change

_lock = threading.Lock()
_jobs: weakref.WeakKeyDictionary[subprocess.Popen[Any], int | None] = weakref.WeakKeyDictionary()
_api: Any = None
_entry: Any = None


def popen(args: Sequence[str], **kwargs: Any) -> subprocess.Popen[Any]:
    """`subprocess.Popen(args, **kwargs)` whose whole process tree `kill_tree` can end."""
    if sys.platform != "win32":
        if kwargs.get("start_new_session") is False:
            raise ValueError("a process tree needs its own session; do not pass start_new_session=False")
        kwargs["start_new_session"] = True
        process = subprocess.Popen(list(args), **kwargs)
        with _lock:
            _jobs[process] = None
        return process
    kwargs["creationflags"] = kwargs.get("creationflags", 0) | _CREATE_SUSPENDED
    process = subprocess.Popen(list(args), **kwargs)
    try:
        job = _contain(process.pid)
    except BaseException:
        process.kill()  # it never ran: it is still suspended
        process.wait()
        raise
    with _lock:
        _jobs[process] = job
    weakref.finalize(process, _close_handle, job)
    return process


def kill_tree(process: subprocess.Popen[Any]) -> None:
    """Kill `process` and every descendant it created, including ones whose parents have exited."""
    with _lock:
        if process not in _jobs:
            raise ValueError("kill_tree() needs a process started by tools.process_tree.popen()")
        job = _jobs[process]
    if job is not None:
        api = _kernel32()
        if not api.TerminateJobObject(job, _KILLED_EXIT_CODE):
            raise _win_error()
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass  # every member of the group has already exited


def _contain(pid: int) -> int:
    api = _kernel32()
    job = api.CreateJobObjectW(None, None)
    if not job:
        raise _win_error()
    try:
        _assign(job, pid)
        _resume(pid)
    except BaseException:
        _close_handle(job)
        raise
    return job


def _assign(job: int, pid: int) -> None:
    api = _kernel32()
    handle = api.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid)
    if not handle:
        raise _win_error()
    try:
        if not api.AssignProcessToJobObject(job, handle):
            raise _win_error()
    finally:
        api.CloseHandle(handle)


def _resume(pid: int) -> None:
    """Resume the suspended child's thread. Subprocess closes the thread handle, so find it by id."""
    import ctypes

    api = _kernel32()
    snapshot = api.CreateToolhelp32Snapshot(_SNAPSHOT_THREADS, 0)
    if snapshot in (None, ctypes.c_void_p(-1).value):
        raise _win_error()
    resumed = 0
    try:
        entry = _thread_entry()()
        entry.dwSize = ctypes.sizeof(entry)
        more = api.Thread32First(snapshot, ctypes.byref(entry))
        while more:
            if entry.th32OwnerProcessID == pid:
                thread = api.OpenThread(_THREAD_SUSPEND_RESUME, False, entry.th32ThreadID)
                if not thread:
                    raise _win_error()
                try:
                    if api.ResumeThread(thread) == _RESUME_FAILED:
                        raise _win_error()
                finally:
                    api.CloseHandle(thread)
                resumed += 1
            more = api.Thread32Next(snapshot, ctypes.byref(entry))
    finally:
        api.CloseHandle(snapshot)
    if not resumed:
        raise OSError(f"the suspended child {pid} has no thread to resume")


def _close_handle(handle: int) -> None:
    _kernel32().CloseHandle(handle)


def _win_error() -> OSError:
    import ctypes

    return ctypes.WinError(ctypes.get_last_error())


def _thread_entry() -> Any:
    """THREADENTRY32, defined once: ctypes matches pointer argument types by class identity."""
    global _entry
    if _entry is None:
        import ctypes
        from ctypes import wintypes

        class ThreadEntry32(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ThreadID", wintypes.DWORD),
                ("th32OwnerProcessID", wintypes.DWORD), ("tpBasePri", ctypes.c_long),
                ("tpDeltaPri", ctypes.c_long), ("dwFlags", wintypes.DWORD),
            ]

        _entry = ThreadEntry32
    return _entry


def _kernel32() -> Any:
    global _api
    if _api is None:
        import ctypes
        from ctypes import wintypes

        handle = ctypes.c_void_p
        entry = ctypes.POINTER(_thread_entry())
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.CreateJobObjectW.restype = handle
        api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        api.AssignProcessToJobObject.restype = wintypes.BOOL
        api.AssignProcessToJobObject.argtypes = [handle, handle]
        api.TerminateJobObject.restype = wintypes.BOOL
        api.TerminateJobObject.argtypes = [handle, wintypes.UINT]
        api.OpenProcess.restype = handle
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenThread.restype = handle
        api.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.ResumeThread.restype = wintypes.DWORD
        api.ResumeThread.argtypes = [handle]
        api.CreateToolhelp32Snapshot.restype = handle
        api.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        api.Thread32First.restype = wintypes.BOOL
        api.Thread32First.argtypes = [handle, entry]
        api.Thread32Next.restype = wintypes.BOOL
        api.Thread32Next.argtypes = [handle, entry]
        api.CloseHandle.restype = wintypes.BOOL
        api.CloseHandle.argtypes = [handle]
        _api = api
    return _api
