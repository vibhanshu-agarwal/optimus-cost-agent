"""Native Windows job ownership for a pytest run: enrolment, identity and accounting.

Test tooling only. Importing this module has no side effects and is safe on every platform; the
native calls run only when a function is called on Windows. Every query returns its outcome
explicitly: a failed query is reported as failed, never as an empty or zero result.

A process is identified by PID plus creation time, never by PID alone and never by its command
line. This module opens no job other than the one it creates: other runs are inspected through
process handles and through this run's own job.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

_KILL_ON_JOB_CLOSE = 0x2000
_BREAKAWAY_OK = 0x0800
_SILENT_BREAKAWAY_OK = 0x1000
_QUERY_LIMITED_INFORMATION = 0x1000
_ERROR_ALREADY_EXISTS = 183
_EXTENDED_LIMIT_CLASS = 9
_ACCOUNTING_AND_IO_CLASS = 8
_PROCESS_ID_LIST_CLASS = 3
_PID_CAPACITY = 4096
_IO_FIELDS = ("read_operations", "write_operations", "other_operations", "read_bytes", "write_bytes", "other_bytes")


@dataclass(frozen=True)
class ProcessIdentity:
    """One process: PID plus creation time. `error` is the native error when it could not be read."""

    pid: int
    creation_time: int | None
    image: str | None = None
    error: int | None = None


@dataclass
class JobOwner:
    """The job this interpreter created and enrolled itself in. The handle is kept until exit."""

    name: str
    handle: int | None
    valid: bool
    facts: dict[str, object] = field(default_factory=dict)


_owner: JobOwner | None = None
_api: object | None = None


def supported() -> bool:
    return sys.platform == "win32"


def _kernel32():  # noqa: ANN202 - ctypes library object, Windows only
    global _api
    if _api is not None:
        return _api
    import ctypes
    from ctypes import wintypes

    handle = ctypes.c_void_p
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.GetCurrentProcess.restype = handle
    api.CreateJobObjectW.restype = handle
    api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    api.AssignProcessToJobObject.argtypes = [handle, handle]
    api.AssignProcessToJobObject.restype = wintypes.BOOL
    api.IsProcessInJob.argtypes = [handle, handle, ctypes.POINTER(wintypes.BOOL)]
    api.IsProcessInJob.restype = wintypes.BOOL
    api.SetInformationJobObject.argtypes = [handle, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    api.SetInformationJobObject.restype = wintypes.BOOL
    api.QueryInformationJobObject.argtypes = [handle, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    api.QueryInformationJobObject.restype = wintypes.BOOL
    api.OpenProcess.restype = handle
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.CloseHandle.argtypes = [handle]
    api.GetProcessTimes.argtypes = [handle] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    api.GetProcessTimes.restype = wintypes.BOOL
    api.GetHandleInformation.argtypes = [handle, ctypes.POINTER(wintypes.DWORD)]
    api.GetHandleInformation.restype = wintypes.BOOL
    api.QueryFullProcessImageNameW.argtypes = [handle, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    api.QueryFullProcessImageNameW.restype = wintypes.BOOL
    _api = api
    return api


def _structures():  # noqa: ANN202 - ctypes structure classes, Windows only
    import ctypes
    from ctypes import wintypes

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in _IO_FIELDS]

    class BasicLimit(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD),
        ]

    class ExtendedLimit(ctypes.Structure):
        _fields_ = [
            ("Basic", BasicLimit), ("IoInfo", IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    class BasicAccounting(ctypes.Structure):
        _fields_ = [
            ("TotalUserTime", ctypes.c_longlong), ("TotalKernelTime", ctypes.c_longlong),
            ("ThisPeriodTotalUserTime", ctypes.c_longlong), ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
            ("TotalPageFaultCount", wintypes.DWORD), ("TotalProcesses", wintypes.DWORD),
            ("ActiveProcesses", wintypes.DWORD), ("TotalTerminatedProcesses", wintypes.DWORD),
        ]

    class AccountingAndIo(ctypes.Structure):
        _fields_ = [("Basic", BasicAccounting), ("Io", IoCounters)]

    class ProcessIdList(ctypes.Structure):
        _fields_ = [("Assigned", wintypes.DWORD), ("InList", wintypes.DWORD), ("Pids", ctypes.c_size_t * _PID_CAPACITY)]

    return ExtendedLimit, AccountingAndIo, ProcessIdList


def _creation_time(api: object, handle: object) -> tuple[int | None, int | None]:
    import ctypes
    from ctypes import wintypes

    created, exited, kernel, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
    if not api.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)):
        return None, ctypes.get_last_error()
    return (created.dwHighDateTime << 32) | created.dwLowDateTime, None


def process_identity(pid: int) -> ProcessIdentity:
    """PID, creation time and image name of a live process, read through a short-lived handle."""
    import ctypes
    from ctypes import wintypes

    api = _kernel32()
    handle = api.OpenProcess(_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ProcessIdentity(pid=pid, creation_time=None, error=ctypes.get_last_error())
    try:
        created, error = _creation_time(api, handle)
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        image = os.path.basename(buffer.value) if api.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)) else None
        return ProcessIdentity(pid=pid, creation_time=created, image=image, error=error)
    finally:
        api.CloseHandle(handle)


def current_identity() -> ProcessIdentity:
    api = _kernel32()
    created, error = _creation_time(api, api.GetCurrentProcess())
    return ProcessIdentity(pid=os.getpid(), creation_time=created, image=os.path.basename(sys.executable), error=error)


def parent_identity() -> ProcessIdentity:
    """The process that started this one, accepted only if it was created before this process."""
    parent = process_identity(os.getppid())
    own = current_identity()
    if parent.creation_time is None or own.creation_time is None or parent.creation_time > own.creation_time:
        return ProcessIdentity(pid=parent.pid, creation_time=None, error=parent.error)
    return parent


def _member_pids(api: object, job: object) -> tuple[list[int] | None, int | None]:
    import ctypes
    from ctypes import wintypes

    _, _, process_id_list = _structures()
    listing = process_id_list()
    returned = wintypes.DWORD()
    if not api.QueryInformationJobObject(job, _PROCESS_ID_LIST_CLASS, ctypes.byref(listing), ctypes.sizeof(listing), ctypes.byref(returned)):
        return None, ctypes.get_last_error()
    return [int(listing.Pids[index]) for index in range(listing.InList)], None


def ancestors(max_hops: int = 32) -> tuple[list[ProcessIdentity], str]:
    """This process's live ancestors, nearest first, each validated by PID plus creation time.

    A hop is accepted only when the parent can be opened and was created no later than its child,
    which rules out a reused PID. The walk stops at the first hop that cannot be validated. The
    second value says why: `ended` (the parent is gone or its PID was reused), `access_denied`,
    `hop_limit` or `snapshot_failed`. This is process ancestry, not job membership.
    """
    import ctypes
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    api = _kernel32()
    api.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    api.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    api.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessEntry)]
    api.Process32FirstW.restype = wintypes.BOOL
    api.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessEntry)]
    api.Process32NextW.restype = wintypes.BOOL
    snapshot = api.CreateToolhelp32Snapshot(0x00000002, 0)
    if not snapshot or snapshot == ctypes.c_void_p(-1).value:
        return [], "snapshot_failed"
    parents: dict[int, int] = {}
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(ProcessEntry)
        more = api.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            more = api.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        api.CloseHandle(snapshot)

    chain: list[ProcessIdentity] = []
    current = current_identity()
    for _ in range(max_hops):
        parent_pid = parents.get(current.pid)
        if not parent_pid or current.creation_time is None:
            return chain, "ended"
        parent = process_identity(parent_pid)
        if parent.creation_time is None:
            return chain, "access_denied" if parent.error == 5 else "ended"
        if parent.creation_time > current.creation_time:
            return chain, "ended"
        chain.append(parent)
        current = parent
    return chain, "hop_limit"


def enroll(run_id: str) -> JobOwner:
    """Create a new kill-on-close job and put this process in it. Idempotent per interpreter."""
    global _owner
    if _owner is not None:
        return _owner
    import ctypes
    from ctypes import wintypes

    api = _kernel32()
    extended_limit, _, _ = _structures()
    me = api.GetCurrentProcess()
    name = f"optimus-test-run-{run_id}"
    facts: dict[str, object] = {}
    ctypes.set_last_error(0)
    job = api.CreateJobObjectW(None, name)
    created_error = ctypes.get_last_error()
    facts["created"] = bool(job)
    facts["create_error"] = created_error if not job else None
    facts["name_already_existed"] = created_error == _ERROR_ALREADY_EXISTS
    if not job:
        _owner = JobOwner(name=name, handle=None, valid=False, facts=facts)
        return _owner

    inherit = wintypes.DWORD()
    facts["handle_inheritable"] = bool(inherit.value & 1) if api.GetHandleInformation(job, ctypes.byref(inherit)) else None

    limits = extended_limit()
    limits.Basic.LimitFlags = _KILL_ON_JOB_CLOSE
    facts["limits_set"] = bool(api.SetInformationJobObject(job, _EXTENDED_LIMIT_CLASS, ctypes.byref(limits), ctypes.sizeof(limits)))
    facts["limits_error"] = None if facts["limits_set"] else ctypes.get_last_error()

    facts["assigned"] = bool(api.AssignProcessToJobObject(job, me))
    facts["assign_error"] = None if facts["assigned"] else ctypes.get_last_error()

    member = wintypes.BOOL()
    facts["self_is_member"] = bool(member.value) if api.IsProcessInJob(me, job, ctypes.byref(member)) else None

    readback = extended_limit()
    returned = wintypes.DWORD()
    if api.QueryInformationJobObject(job, _EXTENDED_LIMIT_CLASS, ctypes.byref(readback), ctypes.sizeof(readback), ctypes.byref(returned)):
        flags = int(readback.Basic.LimitFlags)
        facts["kill_on_close"] = bool(flags & _KILL_ON_JOB_CLOSE)
        facts["breakaway_ok"] = bool(flags & _BREAKAWAY_OK)
        facts["silent_breakaway_ok"] = bool(flags & _SILENT_BREAKAWAY_OK)
    else:
        facts["flags_error"] = ctypes.get_last_error()

    valid = (
        not facts["name_already_existed"] and facts["handle_inheritable"] is False and facts["limits_set"]
        and facts["assigned"] and facts["self_is_member"] is True and facts.get("kill_on_close") is True
        and facts.get("breakaway_ok") is False and facts.get("silent_breakaway_ok") is False
    )
    _owner = JobOwner(name=name, handle=job, valid=bool(valid), facts=facts)
    return _owner


def owner() -> JobOwner | None:
    return _owner


def is_member(identity: ProcessIdentity) -> bool | None:
    """Whether a process belongs to this run's own job. None when it cannot be determined."""
    import ctypes
    from ctypes import wintypes

    if _owner is None or _owner.handle is None or identity.creation_time is None:
        return None
    api = _kernel32()
    handle = api.OpenProcess(_QUERY_LIMITED_INFORMATION, False, identity.pid)
    if not handle:
        return None
    try:
        created, _ = _creation_time(api, handle)
        if created != identity.creation_time:
            return None
        member = wintypes.BOOL()
        if not api.IsProcessInJob(handle, _owner.handle, ctypes.byref(member)):
            return None
        return bool(member.value)
    finally:
        api.CloseHandle(handle)


def accounting() -> dict[str, object]:
    """Totals for this run's job. `ok` is False, with the native error, when the query failed."""
    import ctypes
    from ctypes import wintypes

    if _owner is None or _owner.handle is None:
        return {"ok": False, "error": "no_job"}
    api = _kernel32()
    _, accounting_and_io, _ = _structures()
    totals = accounting_and_io()
    returned = wintypes.DWORD()
    if not api.QueryInformationJobObject(_owner.handle, _ACCOUNTING_AND_IO_CLASS, ctypes.byref(totals), ctypes.sizeof(totals), ctypes.byref(returned)):
        return {"ok": False, "error": ctypes.get_last_error()}
    return {
        "ok": True,
        "total_processes": int(totals.Basic.TotalProcesses),
        "active_processes": int(totals.Basic.ActiveProcesses),
        "user_seconds": totals.Basic.TotalUserTime / 1e7,
        "kernel_seconds": totals.Basic.TotalKernelTime / 1e7,
        "io": {name: int(getattr(totals.Io, name)) for name in _IO_FIELDS},
    }


def members() -> tuple[list[ProcessIdentity] | None, int | None]:
    """Identities of the processes currently in this run's job."""
    if _owner is None or _owner.handle is None:
        return None, None
    pids, error = _member_pids(_kernel32(), _owner.handle)
    if pids is None:
        return None, error
    return [process_identity(pid) for pid in pids], None
