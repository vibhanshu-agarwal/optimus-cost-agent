"""Live Zed 1.13.1 crash-log collection proof.

Requires a real supported Zed instance and its real
``%LOCALAPPDATA%\\Zed\\logs\\`` tree. Crash claims need an operator-approved
crash exercise that produces a new dump/panic artifact; ordinary log appends
are recorded but never asserted as crashes.

Important process model: one ``Zed.exe`` editor process owns *all* open windows
and tabs on this machine. Those ``zed-live-probe.txt`` tabs from the test are
not separate processes — they share the same editor PID. Crashing that PID
closes every Zed window, not just the probe tabs. Confirm nothing with unsaved
work is open under that process before enabling the crash exercise.

When ``OPTIMUS_EVIDENCE_ZED_CRASH_EXERCISE=1``, after log-watch proof the test
snapshots again, induces an in-process ``ACCESS_VIOLATION`` in the correlated
editor PID via ``CreateRemoteThread`` starting at an invalid address (so Zed's
crash-handler can write a real ``.dmp`` / panic ``.json``), then watches the
log root. Do not use Task Manager End Task / ``taskkill`` — those bypass
crashpad and produce no dump.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import subprocess
import time
from pathlib import Path

import pytest

from tools.evidence_gather_support import zed_logs as zed_mod
from tools.evidence_gather_support.common import HostError

REPO_ROOT = Path(__file__).resolve().parents[3]

pytestmark = [pytest.mark.requires_zed]

# OpenProcess rights needed to create a remote faulting thread.
_PROCESS_CREATE_THREAD = 0x0002
_PROCESS_QUERY_INFORMATION = 0x0400
_PROCESS_VM_OPERATION = 0x0008
_PROCESS_VM_WRITE = 0x0020
_PROCESS_VM_READ = 0x0010
_INDUCE_ACCESS = (
    _PROCESS_CREATE_THREAD
    | _PROCESS_QUERY_INFORMATION
    | _PROCESS_VM_OPERATION
    | _PROCESS_VM_WRITE
    | _PROCESS_VM_READ
)


def _zed_executable() -> Path:
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if not local:
        pytest.fail("LOCALAPPDATA_missing")
    candidate = Path(local) / "Programs" / "Zed" / "bin" / "Zed.exe"
    if candidate.is_file():
        return candidate.resolve()
    pytest.fail("zed_executable_missing")


def _require_zed_version(exe: Path) -> str:
    completed = subprocess.run(
        [str(exe), "--version"],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        timeout=30,
    )
    version = (completed.stdout or completed.stderr or "").strip()
    if completed.returncode != 0 or not version:
        pytest.fail("zed_version_failed")
    try:
        zed_mod.require_supported_client_identity("zed-1.13.1", reported_version=version)
    except HostError as exc:
        pytest.fail(f"zed_version_unsupported:{exc.code}:{version}")
    return version


def _resolve_expected_pid(observed: tuple[int, ...]) -> int:
    override = os.environ.get("OPTIMUS_EVIDENCE_ZED_PID", "").strip()
    if override:
        pid = int(override)
        zed_mod.correlate_zed_processes(expected_pids=(pid,), observed_pids=observed)
        return pid
    if not observed:
        raise HostError("zed_process_lookup_failed")
    if len(observed) != 1:
        raise HostError("zed_multi_instance_ambiguous")
    return observed[0]


def _ensure_zed_running(exe: Path, open_path: Path) -> tuple[int, tuple[int, ...]]:
    try:
        observed = zed_mod.discover_zed_editor_pids()
        pid = _resolve_expected_pid(observed)
        return pid, observed
    except HostError as exc:
        if exc.code == "zed_multi_instance_ambiguous":
            raise
        if exc.code not in {"zed_process_lookup_failed", "zed_unrelated_process"}:
            raise
    subprocess.Popen(  # noqa: S603 — absolute Zed path, shell=False
        [str(exe), str(open_path)],
        cwd=str(REPO_ROOT),
        shell=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            observed = zed_mod.discover_zed_editor_pids()
            pid = _resolve_expected_pid(observed)
            return pid, observed
        except HostError as exc:
            if exc.code == "zed_multi_instance_ambiguous":
                raise
        time.sleep(0.5)
    pytest.fail("zed_process_not_started")


def _provoke_zed_log_activity(exe: Path, path: Path) -> None:
    subprocess.run(
        [str(exe), str(path)],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        timeout=60,
    )


def _induce_zed_crashpad_fault(pid: int) -> None:
    """Fault the editor so Zed's crash-handler can emit dump/panic under logs/.

    Starts a remote thread at address ``1`` inside the target process. That
    immediately raises ``ACCESS_VIOLATION``, which is the class of fault Zed's
    crashpad path is built to observe. This is intentionally *not*
    ``DebugBreakProcess`` (waits for a debugger) and *not* ``taskkill``
    (terminates without a fault, so no dump).
    """
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(_INDUCE_ACCESS, False, int(pid))
    if not handle:
        pytest.fail(f"zed_crash_open_process_failed:{ctypes.get_last_error()}")
    thread = None
    try:
        thread_id = ctypes.c_ulong(0)
        # lpStartAddress=1 → fetch/execute at unmapped address → ACCESS_VIOLATION.
        thread = kernel32.CreateRemoteThread(
            handle,
            None,
            0,
            ctypes.c_void_p(1),
            None,
            0,
            ctypes.byref(thread_id),
        )
        if not thread:
            pytest.fail(f"zed_crash_remote_thread_failed:{ctypes.get_last_error()}")
        # Brief wait; dump writing is asynchronous in the crash-handler sidecar.
        kernel32.WaitForSingleObject(thread, 5_000)
    finally:
        if thread:
            kernel32.CloseHandle(thread)
        kernel32.CloseHandle(handle)


def _watch_for_crash_artifacts(
    pid: int, snapshot: zed_mod.ZedLogSnapshot
) -> tuple[zed_mod.ZedFileRecord, ...]:
    print(
        {
            "crash_induction": "CreateRemoteThread_invalid_address",
            "pid": pid,
            "log_root": str(snapshot.root),
            "poll_seconds": 90,
        }
    )
    _induce_zed_crashpad_fault(pid)
    try:
        return zed_mod.watch_log_root(
            snapshot,
            watch_seconds=90.0,
            poll_interval_seconds=0.5,
        )
    except HostError as exc:
        if exc.code == "zed_watch_timeout":
            pytest.fail("zed_crash_exercise_missing_artifact")
        raise


def _crash_roles_for(candidates: tuple[zed_mod.ZedFileRecord, ...], log_root: Path) -> list[str]:
    names: list[str] = []
    for item in candidates:
        header = (log_root / item.name).read_bytes()[:4]
        role = zed_mod.classify_artifact_role(item.name, header)
        if role in {"zed_process_dump", "zed_panic_json"}:
            names.append(item.name)
    return names


def test_live_zed_crash_log_pre_run_exclusion_and_bounded_watch(tmp_path: Path) -> None:
    exe = _zed_executable()
    version = _require_zed_version(exe)
    expected_root = zed_mod.default_live_zed_log_root()
    log_root = zed_mod.require_zed_log_root(expected_root, expected_live_root=expected_root)

    probe = (tmp_path / "zed-live-probe.txt").resolve()
    probe.write_text("optimus-evidence-zed-live-probe\n", encoding="utf-8")
    try:
        pid, observed = _ensure_zed_running(exe, probe)
    except HostError as exc:
        pytest.fail(exc.code)
    # Independent discovery must agree with the correlated expected PID.
    zed_mod.correlate_zed_processes(expected_pids=(pid,), observed_pids=observed)

    pre_names = {path.name for path in log_root.iterdir() if path.is_file()}
    watch_started_ns = time.monotonic_ns()
    wall_started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    snapshot = zed_mod.snapshot_log_root(
        log_root,
        monotonic_ns=watch_started_ns,
        wall_clock=wall_started,
    )
    assert {record.name for record in snapshot.records} == pre_names

    _provoke_zed_log_activity(exe, probe)
    try:
        candidates = zed_mod.watch_log_root(snapshot, watch_seconds=20.0, poll_interval_seconds=0.25)
    except HostError as exc:
        if exc.code == "zed_watch_timeout":
            pytest.fail("zed_post_start_log_change_missing")
        raise

    candidate_names = {item.name for item in candidates}
    for record in snapshot.records:
        if record.name not in candidate_names:
            current = zed_mod.file_record_for(log_root / record.name)
            assert current == record

    digests = {
        item.name: zed_mod.digest_stable(log_root / item.name, expected=item) for item in candidates
    }
    watch_ended_ns = time.monotonic_ns()
    wall_ended = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    batch = zed_mod.build_collection_batch(
        scenario_id="zed-session",
        run_id="live-zed-watch",
        monotonic_origin_ns=watch_started_ns,
        snapshot=snapshot,
        candidates=candidates,
        digests=digests,
        process_pids=(pid,),
        watch_started_ns=watch_started_ns,
        watch_ended_ns=watch_ended_ns,
        wall_started=wall_started,
        wall_ended=wall_ended,
    )
    assert batch.collector_id == "zed_crash_collector"
    assert batch.artifacts
    assert all(obs.observation_kind == "zed_log_candidate" for obs in batch.observations)
    assert all(obs.observation_kind != "client_crash_observed" for obs in batch.observations)

    evidence = {
        "zed_version": version,
        "zed_exe": str(exe),
        "zed_exe_path_digest": hashlib.sha256(str(exe).encode("utf-8")).hexdigest(),
        "zed_pid": pid,
        "observed_pids": list(observed),
        "log_root": str(log_root),
        "pre_run_count": len(snapshot.records),
        "pre_run_names": sorted(pre_names),
        "candidate_names": [item.name for item in candidates],
        "candidate_roles": [artifact.role for artifact in batch.artifacts],
        "digests": digests,
        "watch_started_ns": watch_started_ns,
        "watch_ended_ns": watch_ended_ns,
        "wall_started": wall_started,
        "wall_ended": wall_ended,
    }
    print(evidence)

    exercise = os.environ.get("OPTIMUS_EVIDENCE_ZED_CRASH_EXERCISE", "").strip()
    if exercise != "1":
        pytest.fail(
            "zed_crash_exercise_incomplete: log-watch evidence recorded above; set "
            "OPTIMUS_EVIDENCE_ZED_CRASH_EXERCISE=1 after confirming no unsaved work in "
            "any Zed window (one editor PID owns all tabs), then re-run so the test "
            "can induce CreateRemoteThread ACCESS_VIOLATION and capture dump/panic"
        )

    crash_started_ns = time.monotonic_ns()
    crash_wall_started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    crash_snapshot = zed_mod.snapshot_log_root(
        log_root,
        monotonic_ns=crash_started_ns,
        wall_clock=crash_wall_started,
    )
    crash_candidates = _watch_for_crash_artifacts(pid, crash_snapshot)
    crash_names = _crash_roles_for(crash_candidates, log_root)
    if not crash_names:
        pytest.fail(
            "zed_crash_exercise_missing_artifact: post-crash candidates lacked "
            "zed_process_dump/zed_panic_json roles"
        )
    crash_digests = {
        item.name: zed_mod.digest_stable(log_root / item.name, expected=item)
        for item in crash_candidates
        if item.name in crash_names
    }
    print(
        {
            "crash_candidate_names": crash_names,
            "crash_digests": crash_digests,
            "crash_all_candidates": [item.name for item in crash_candidates],
        }
    )
