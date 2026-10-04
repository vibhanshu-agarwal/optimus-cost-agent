"""Outside observer for planted test runs: watches processes through handles it validates itself.

Test support only. It opens process handles, never a job handle, so a watched run's cleanup is
never delayed or caused by the observer. A handle is kept only when the process behind it has the
creation time the planted run reported, which rules out a reused PID. The one process it can end is
the planted root a test names explicitly.
"""

from __future__ import annotations

import ctypes
import time
from collections.abc import Callable
from dataclasses import dataclass

_SYNCHRONIZE = 0x00100000
_QUERY_LIMITED_INFORMATION = 0x1000
_TERMINATE = 0x0001
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 258


@dataclass
class Watched:
    pid: int
    creation_time: int
    handle: int | None


def _kernel32():  # noqa: ANN202 - ctypes library object, Windows only
    from ctypes import wintypes

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.restype = ctypes.c_void_p
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.CloseHandle.argtypes = [ctypes.c_void_p]
    api.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    api.GetProcessTimes.restype = wintypes.BOOL
    api.WaitForSingleObject.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    api.WaitForSingleObject.restype = wintypes.DWORD
    api.TerminateProcess.argtypes = [ctypes.c_void_p, wintypes.UINT]
    api.TerminateProcess.restype = wintypes.BOOL
    return api


def watch(identities: list[dict[str, int]], *, may_end_pid: int | None = None) -> list[Watched]:
    """Open one validated handle per reported identity. An identity that cannot be validated has no handle."""
    from ctypes import wintypes

    api = _kernel32()
    watched: list[Watched] = []
    for identity in identities:
        pid, expected = int(identity["pid"]), int(identity["creation_time"])
        access = _SYNCHRONIZE | _QUERY_LIMITED_INFORMATION | (_TERMINATE if pid == may_end_pid else 0)
        handle = api.OpenProcess(access, False, pid)
        if handle:
            created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
            read = api.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user))
            if not read or ((created.dwHighDateTime << 32) | created.dwLowDateTime) != expected:
                api.CloseHandle(handle)
                handle = None
        watched.append(Watched(pid=pid, creation_time=expected, handle=handle or None))
    return watched


def is_gone(process: Watched) -> bool | None:
    """True once the process has terminated, False while it runs, None when that cannot be read."""
    if process.handle is None:
        return None
    result = _kernel32().WaitForSingleObject(process.handle, 0)
    return True if result == _WAIT_OBJECT_0 else False if result == _WAIT_TIMEOUT else None


def wait_until_gone(process: Watched, seconds: float, *, api: object = None, clock: Callable[[], float] = time.monotonic) -> float | None:
    """Seconds until the process terminated, or None when it was still running at the deadline
    or its state could not be read. An unknown state is never taken for an exit."""
    if process.handle is None:
        return None
    started = clock()
    result = (api or _kernel32()).WaitForSingleObject(process.handle, int(max(0.0, seconds) * 1000))
    return clock() - started if result == _WAIT_OBJECT_0 else None


def wait_all_gone(processes: list[Watched], seconds: float, *, api: object = None, clock: Callable[[], float] = time.monotonic) -> dict[int, float | None]:
    """One deadline for all: `seconds` from now, shared. Each process gets only what remains of it.

    The result maps PID to seconds-from-now at which the process was seen gone, or None when it
    was still running, or unreadable, when the common deadline passed.
    """
    started = clock()
    deadline = started + seconds
    gone: dict[int, float | None] = {}
    for process in processes:
        waited = wait_until_gone(process, deadline - clock(), api=api, clock=clock)
        gone[process.pid] = None if waited is None else round(clock() - started, 3)
    return gone


def end(process: Watched) -> bool:
    """End the one process the test asked to be able to end. Fails for every other handle."""
    return bool(process.handle is not None and _kernel32().TerminateProcess(process.handle, 1))


def close(processes: list[Watched]) -> None:
    api = _kernel32()
    for process in processes:
        if process.handle is not None:
            api.CloseHandle(process.handle)
            process.handle = None
