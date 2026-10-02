"""Capture what a thread, asyncio task, child or descendant process is doing, for failure diagnostics.

The ONE owner of concurrency capture (P11-FU-33 batch; operator directive 2026-10-02: tests
must never lose context). Callers format the snapshots for their own medium: the shared test
helpers (``tests/support/concurrency.py``) render multi-line reports, and the H5 shutdown
schedule (``tools/plan1126_runtime_audit/shutdown.py``) renders single-line, content-free
entries for its frozen schema.

Snapshots carry names, ids, flags, qualified names and frame locations (file, line, function)
only -- never local-variable values, source text, credentials or process command lines.
"""

from __future__ import annotations

import asyncio
import gc
import os
import sys
import threading
import traceback
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import FrameType
from typing import Any

DEFAULT_FRAME_LIMIT = 15


@dataclass(frozen=True)
class FrameLocation:
    filename: str
    lineno: int | None
    function: str


@dataclass(frozen=True)
class ThreadSnapshot:
    name: str
    ident: int | None
    native_id: int | None
    daemon: bool
    alive: bool
    target: str
    frames: tuple[FrameLocation, ...]  # innermost first; empty when no live frame


@dataclass(frozen=True)
class TaskSnapshot:
    name: str
    coroutine: str
    state: str  # "pending", "done" or "cancelled"
    frames: tuple[FrameLocation, ...]  # innermost first


@dataclass(frozen=True)
class ProcessSnapshot:
    pid: int | None
    running: bool
    returncode: int | None


def qualified_name(obj: object) -> str:
    if obj is None:
        return "-"
    name = getattr(obj, "__qualname__", None) or type(obj).__qualname__
    module = getattr(obj, "__module__", None)
    return f"{module}.{name}" if module else str(name)


def coroutine_name(coro: object) -> str:
    if coro is None:
        return "-"
    frame = getattr(coro, "cr_frame", None)
    module = frame.f_globals.get("__name__") if frame is not None else None
    name = getattr(coro, "__qualname__", None) or type(coro).__qualname__
    return f"{module}.{name}" if module else str(name)


def frame_locations(frame: FrameType | None, *, limit: int = DEFAULT_FRAME_LIMIT) -> tuple[FrameLocation, ...]:
    """Innermost-first locations of ``frame``'s stack; no source text, no locals."""
    if frame is None:
        return ()
    summaries = traceback.StackSummary.extract(traceback.walk_stack(frame), limit=limit, lookup_lines=False)
    return tuple(FrameLocation(item.filename, item.lineno, item.name) for item in summaries)


def snapshot_thread(
    thread: threading.Thread,
    frames: Mapping[int, FrameType] | None = None,
    *,
    limit: int = DEFAULT_FRAME_LIMIT,
) -> ThreadSnapshot:
    frames = sys._current_frames() if frames is None else frames
    return ThreadSnapshot(
        name=thread.name,
        ident=thread.ident,
        native_id=thread.native_id,
        daemon=thread.daemon,
        alive=thread.is_alive(),
        target=qualified_name(getattr(thread, "_target", None)),
        frames=frame_locations(frames.get(thread.ident), limit=limit) if thread.ident is not None else (),
    )


def snapshot_threads(threads: Iterable[threading.Thread], *, limit: int = DEFAULT_FRAME_LIMIT) -> tuple[ThreadSnapshot, ...]:
    """All snapshots from ONE frames capture, so they describe the same instant."""
    frames = sys._current_frames()
    return tuple(snapshot_thread(thread, frames, limit=limit) for thread in threads)


def alive_after_bounded_join(thread: threading.Thread, seconds: float) -> bool:
    """Annotation only: whether ``thread`` is still alive after a bounded join. Never a verdict."""
    if thread is not threading.current_thread() and thread.ident is not None:
        thread.join(seconds)
    return thread.is_alive()


def snapshot_task(task: asyncio.Future[Any], *, limit: int = DEFAULT_FRAME_LIMIT) -> TaskSnapshot:
    is_task = isinstance(task, asyncio.Task)
    stack = task.get_stack(limit=limit) if is_task else []
    return TaskSnapshot(
        name=task.get_name() if is_task else "-",
        coroutine=coroutine_name(task.get_coro()) if is_task else "-",
        state="cancelled" if task.cancelled() else "done" if task.done() else "pending",
        frames=tuple(
            FrameLocation(frame.f_code.co_filename, frame.f_lineno, frame.f_code.co_name)
            for frame in reversed(stack)
        ),
    )


def pending_tasks() -> list[asyncio.Task[Any]]:
    """Every not-done asyncio task in this interpreter, on any loop -- running, idle or closed."""
    return [obj for obj in gc.get_objects() if isinstance(obj, asyncio.Task) and not obj.done()]


def snapshot_process(process: Any) -> ProcessSnapshot:
    """A child process by pid and exit state only -- never its command line."""
    if isinstance(process, ProcessWatch):
        return process.snapshot()
    returncode = process.poll() if hasattr(process, "poll") else getattr(process, "returncode", None)
    return ProcessSnapshot(pid=getattr(process, "pid", None), running=returncode is None, returncode=returncode)


_SYNCHRONIZE = 0x00100000
_QUERY_LIMITED_INFORMATION = 0x1000
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 0x102


class ProcessWatch:
    """A process observed from outside by pid -- a descendant, not our own child.

    It is pinned while it runs, so a recycled pid is never mistaken for it: Windows holds a
    SYNCHRONIZE | QUERY_LIMITED_INFORMATION handle, Linux a pidfd. Elsewhere it falls back to an
    unpinned signal-0 probe. (On Windows `os.kill(pid, 0)` is not a probe at all.) Watch a
    process while it is known to be running; `ProcessLookupError` means it could not be opened.
    The exit code is reported where the platform exposes it for a non-child (Windows), else None.
    """

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self._handle: int | None = None
        self._pidfd: int | None = None
        self._closed = False
        if sys.platform == "win32":
            handle = _kernel32().OpenProcess(_SYNCHRONIZE | _QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                raise ProcessLookupError(pid)
            self._handle = handle
        elif hasattr(os, "pidfd_open"):
            self._pidfd = os.pidfd_open(pid)  # raises ProcessLookupError when the pid is gone

    def snapshot(self) -> ProcessSnapshot:
        if self._closed:
            raise ValueError(f"the watch on pid {self.pid} is closed")
        if self._handle is not None:
            import ctypes

            api = _kernel32()
            waited = api.WaitForSingleObject(self._handle, 0)
            if waited == _WAIT_TIMEOUT:
                return ProcessSnapshot(pid=self.pid, running=True, returncode=None)
            if waited != _WAIT_OBJECT_0:
                raise ctypes.WinError(ctypes.get_last_error())
            code = ctypes.c_ulong()
            known = bool(api.GetExitCodeProcess(self._handle, ctypes.byref(code)))
            return ProcessSnapshot(pid=self.pid, running=False, returncode=code.value if known else None)
        if self._pidfd is not None:
            import select

            readable, _, _ = select.select([self._pidfd], [], [], 0)
            return ProcessSnapshot(pid=self.pid, running=not readable, returncode=None)
        try:
            os.kill(self.pid, 0)
        except ProcessLookupError:
            return ProcessSnapshot(pid=self.pid, running=False, returncode=None)
        except PermissionError:
            pass
        return ProcessSnapshot(pid=self.pid, running=True, returncode=None)

    def close(self) -> None:
        self._closed = True
        if self._handle is not None:
            _kernel32().CloseHandle(self._handle)
            self._handle = None
        if self._pidfd is not None:
            os.close(self._pidfd)
            self._pidfd = None


_api: Any = None


def _kernel32() -> Any:
    """kernel32 bound lazily: importing this module must not load ctypes (the H5 child imports it)."""
    global _api
    if _api is None:
        import ctypes
        from ctypes import wintypes

        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.restype = ctypes.c_void_p
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.WaitForSingleObject.restype = wintypes.DWORD
        api.WaitForSingleObject.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        api.GetExitCodeProcess.restype = wintypes.BOOL
        api.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        api.CloseHandle.restype = wintypes.BOOL
        api.CloseHandle.argtypes = [ctypes.c_void_p]
        _api = api
    return _api
