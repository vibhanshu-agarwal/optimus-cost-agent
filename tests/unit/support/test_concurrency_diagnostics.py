"""The shared diagnostics helpers name what failed (operator directive 2026-10-02).

Each test injects a real failure of one kind -- a stuck thread, a pending task, a running process,
an offending row -- and proves the report names it, its target and where it is. A helper whose
report would not have named the cause is not done.
"""

from __future__ import annotations

import asyncio
import dataclasses
import enum
import subprocess
import sys
import threading
import time

import pytest

from tests.support.concurrency import (
    DescendantRecorder,
    announce_pid_code,
    assert_descendants_killed,
    assert_no_new_threads,
    assert_no_offending_rows,
    assert_processes_exited,
    assert_some_row,
    assert_tasks_done,
    assert_threads_alive,
    assert_threads_stopped,
    describe_process,
    thread_baseline,
)
from tools.concurrency_capture import ProcessWatch


class Classification(enum.Enum):
    CANONICAL = "canonical"


def test_a_stuck_thread_is_named_with_its_target_and_stack():
    release = threading.Event()

    def _stuck_in_teardown() -> None:
        release.wait(10)

    thread = threading.Thread(target=_stuck_in_teardown, name="diag-stuck", daemon=True)
    thread.start()
    try:
        with pytest.raises(AssertionError) as caught:
            assert_threads_stopped([thread], "teardown left a thread")
    finally:
        release.set()
        thread.join(5)
    report = str(caught.value)
    assert report.startswith("teardown left a thread: 1 thread(s) still alive at detection")
    assert "thread 'diag-stuck'" in report and "daemon=True" in report
    assert "_stuck_in_teardown" in report.splitlines()[1]  # the target
    assert "in _stuck_in_teardown" in report  # the live frame
    assert "still alive after a 0.2s diagnostic join: yes" in report


def test_the_verdict_is_taken_at_detection_even_if_the_thread_then_exits():
    release = threading.Event()
    thread = threading.Thread(target=release.wait, args=(10,), name="diag-exiting", daemon=True)
    thread.start()
    threading.Timer(0.05, release.set).start()
    with pytest.raises(AssertionError) as caught:
        assert_threads_stopped([thread], "detection")
    thread.join(5)
    assert "still alive after a 0.2s diagnostic join: no" in str(caught.value)


def test_a_dead_thread_fails_an_aliveness_precondition_with_its_identity():
    thread = threading.Thread(target=lambda: None, name="diag-dead")
    thread.start()
    thread.join(5)
    with pytest.raises(AssertionError, match=r"precondition: 1 thread\(s\) not alive at detection\nthread 'diag-dead'"):
        assert_threads_alive([thread], "precondition")


def test_a_new_thread_outside_the_baseline_is_reported():
    baseline = thread_baseline()
    release = threading.Event()
    thread = threading.Thread(target=release.wait, args=(10,), name="diag-new", daemon=True)
    thread.start()
    try:
        with pytest.raises(AssertionError, match="thread 'diag-new'"):
            assert_no_new_threads(baseline, "leak")
    finally:
        release.set()
        thread.join(5)


def test_a_pending_task_is_named_with_its_coroutine_and_suspended_frame():
    async def _never_finishes(gate: asyncio.Event) -> None:
        await gate.wait()

    async def _scenario() -> str:
        gate = asyncio.Event()
        task = asyncio.create_task(_never_finishes(gate), name="diag-task")
        await asyncio.sleep(0)
        try:
            with pytest.raises(AssertionError) as caught:
                assert_tasks_done([task], "tasks left")
        finally:
            gate.set()
            await task
        return str(caught.value)

    report = asyncio.run(_scenario())
    assert report.startswith("tasks left: 1 task(s) pending at detection\ntask 'diag-task'")
    assert "_never_finishes" in report.splitlines()[1]
    assert "in _never_finishes" in report


def test_a_running_process_is_reported_by_pid_without_its_command_line():
    marker = "diag-command-line-must-not-appear"
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)", marker], stdin=subprocess.DEVNULL
    )
    try:
        with pytest.raises(AssertionError) as caught:
            assert_processes_exited([process], "children left")
    finally:
        process.kill()
        process.wait(10)
    report = str(caught.value)
    assert f"pid={process.pid} state=running" in report
    assert marker not in report and sys.executable not in report


def _announcing_child(directory, role: str, then: str) -> subprocess.Popen[bytes]:
    code = announce_pid_code(directory, role) + "; " + then
    return subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.DEVNULL)


def test_a_descendant_left_running_is_named_by_role_and_pid(tmp_path):
    with DescendantRecorder(tmp_path, ["grandchild"]) as recorder:
        process = _announcing_child(tmp_path, "grandchild", "import time; time.sleep(30)")
        try:
            assert recorder.wait_for(["grandchild"], timeout=30), "the control descendant never announced itself"
            with pytest.raises(AssertionError) as caught:
                assert_descendants_killed(recorder, ["grandchild"], deadline=time.monotonic(), what="timeout cleanup")
        finally:
            process.kill()
            process.wait(10)
    report = str(caught.value)
    announced = recorder.outcome("grandchild")[0]  # the interpreter; process.pid may be a venv launcher
    assert report.startswith("timeout cleanup: 1 of 1 descendant(s) not killed by the deadline\n")
    assert f"grandchild pid={announced} state=running" in report


def test_a_descendant_that_exits_only_after_the_deadline_is_named_with_how_late(tmp_path):
    with DescendantRecorder(tmp_path, ["grandchild"]) as recorder:
        deadline = time.monotonic()
        process = _announcing_child(tmp_path, "grandchild", "import time; time.sleep(0.5)")
        process.wait(30)
        assert recorder.wait_for_exit(["grandchild"], timeout=30)
        with pytest.raises(AssertionError) as caught:
            assert_descendants_killed(recorder, ["grandchild"], deadline=deadline, what="timeout cleanup")
    report = str(caught.value)
    assert f"grandchild pid={recorder.outcome('grandchild')[0]} exited " in report
    assert "s after the deadline (it was waited for, not killed)" in report


def test_a_descendant_that_never_started_is_named_so_the_control_cannot_pass_vacuously(tmp_path):
    with DescendantRecorder(tmp_path, ["grandchild"]) as recorder:
        with pytest.raises(AssertionError) as caught:
            assert_descendants_killed(recorder, ["grandchild"], deadline=time.monotonic(), what="timeout cleanup")
    assert "grandchild never announced a pid, so the run proves nothing about it" in str(caught.value)


def test_a_descendant_killed_before_the_deadline_passes(tmp_path):
    with DescendantRecorder(tmp_path, ["grandchild"]) as recorder:
        process = _announcing_child(tmp_path, "grandchild", "import time; time.sleep(30)")
        assert recorder.wait_for(["grandchild"], timeout=30)
        process.kill()
        process.wait(10)
        assert recorder.wait_for_exit(["grandchild"], timeout=30)
        assert_descendants_killed(recorder, ["grandchild"], deadline=time.monotonic(), what="timeout cleanup")
    with pytest.raises(RuntimeError, match="open recorder"):
        assert_descendants_killed(recorder, ["grandchild"], deadline=time.monotonic(), what="after close")


def test_a_recorder_that_stopped_watching_is_named_not_read_as_a_verdict(tmp_path, monkeypatch):
    import tests.support.concurrency as support

    def broken_watch(pid):
        raise OSError(f"injected: cannot watch {pid}")

    monkeypatch.setattr(support, "ProcessWatch", broken_watch)
    with DescendantRecorder(tmp_path, ["grandchild"]) as recorder:
        process = _announcing_child(tmp_path, "grandchild", "import time; time.sleep(30)")
        try:
            deadline = time.monotonic() + 30
            while recorder.error is None and time.monotonic() < deadline:
                time.sleep(0.01)
            with pytest.raises(AssertionError) as caught:
                assert_descendants_killed(recorder, ["grandchild"], deadline=time.monotonic(), what="timeout cleanup")
        finally:
            process.kill()
            process.wait(10)
    assert "timeout cleanup: the descendant recorder stopped watching: OSError('injected: cannot watch" in str(caught.value)


def _refusing_kernel32(error: int):
    """A stand-in kernel32 whose OpenProcess fails with `error` (5 = access denied, 87 = no such pid)."""
    import ctypes

    class _Refusing:
        def OpenProcess(self, *_args):  # noqa: N802 - mirrors the Win32 name
            ctypes.set_last_error(error)
            return None

    return _Refusing()


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows OpenProcess path")
def test_a_process_the_watch_may_not_open_is_an_error_not_a_missing_process(monkeypatch):
    """Codex review R1: access denied says nothing about whether the process exists."""
    import tools.concurrency_capture as capture

    monkeypatch.setattr(capture, "_kernel32", lambda: _refusing_kernel32(5))
    with pytest.raises(PermissionError) as caught:
        ProcessWatch(4242)
    assert caught.value.winerror == 5
    monkeypatch.setattr(capture, "_kernel32", lambda: _refusing_kernel32(87))
    with pytest.raises(ProcessLookupError):
        ProcessWatch(4242)


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows OpenProcess path")
def test_an_access_denied_descendant_is_a_recorder_failure_never_an_exit(tmp_path, monkeypatch):
    """Codex review R1, through the recorder: the role is never recorded as gone, and the verdict
    names the access-denied error instead of passing."""
    import tools.concurrency_capture as capture

    monkeypatch.setattr(capture, "_kernel32", lambda: _refusing_kernel32(5))
    with DescendantRecorder(tmp_path, ["grandchild"]) as recorder:
        process = _announcing_child(tmp_path, "grandchild", "import time; time.sleep(30)")
        try:
            deadline = time.monotonic() + 30
            while recorder.error is None and time.monotonic() < deadline:
                time.sleep(0.01)
            with pytest.raises(AssertionError) as caught:
                assert_descendants_killed(recorder, ["grandchild"], deadline=time.monotonic(), what="timeout cleanup")
        finally:
            process.kill()
            process.wait(10)
    assert recorder.outcome("grandchild")[2] is None, "an unobservable descendant was recorded as gone"
    assert "timeout cleanup: the descendant recorder stopped watching: PermissionError(" in str(caught.value)


def test_a_watched_process_is_pinned_and_reports_its_exit(tmp_path):
    process = subprocess.Popen([sys.executable, "-c", "import sys, time; time.sleep(0.3); sys.exit(3)"])
    watch = ProcessWatch(process.pid)
    try:
        assert watch.snapshot().running
        process.wait(30)
        snapshot = watch.snapshot()
        description = describe_process(watch)
    finally:
        watch.close()
    assert not snapshot.running
    # Windows reads a non-child's exit code through its handle; a Linux pidfd only signals the exit.
    expected = 3 if sys.platform == "win32" else None
    assert snapshot.returncode == expected
    assert description == (
        f"process pid={process.pid} state=exited(3)" if expected == 3 else f"process pid={process.pid} state=exited"
    )
    with pytest.raises(ValueError, match="closed"):
        watch.snapshot()


def test_offending_rows_are_printed_with_their_index_and_chosen_fields():
    rows = [
        {"close_path_id": "h5-a", "terminal_cause": "orderly_eof", "unexpected_persistent_threads": []},
        {"close_path_id": "h5-b", "terminal_cause": "transport_failure", "unexpected_persistent_threads": ["t | daemon=True"]},
    ]
    with pytest.raises(AssertionError) as caught:
        assert_no_offending_rows(
            rows,
            lambda row: row["unexpected_persistent_threads"],
            "persistent threads",
            fields=("close_path_id", "terminal_cause", "unexpected_persistent_threads"),
        )
    report = str(caught.value)
    assert report.startswith("persistent threads: 1 of 2 row(s) offend; first 1:")
    assert "[1] {'close_path_id': 'h5-b', 'terminal_cause': 'transport_failure'" in report
    assert "h5-a" not in report


_SENTINEL = "REVIEW_FAKE_SECRET_VALUE"  # pragma: allowlist secret - a fake sentinel; it must never be printed


class _Opaque:
    """An arbitrary object whose repr would leak the sentinel."""

    def __repr__(self) -> str:
        return f"Opaque(secret={_SENTINEL})"


@dataclasses.dataclass
class _Record:
    close_path_id: str
    terminal_cause: str
    password: str
    context: object


def _leaky_rows() -> list[object]:
    return [
        {"close_path_id": "h5-a", "terminal_cause": "orderly_eof", "api_key": _SENTINEL},
        {"close_path_id": "h5-b", "nested": {"inner": [{"access_token": _SENTINEL}]}, "argv": ["tool", _SENTINEL]},
        {"close_path_id": "h5-c", "note": f"Authorization: Bearer {_SENTINEL}abcdef0123456789abcdef"},
        {"close_path_id": "h5-d", "locals": {"x": _SENTINEL}, "object": _Opaque()},
        _Record("h5-e", "transport_failure", _SENTINEL, _Opaque()),
    ]


@pytest.mark.parametrize("fields", [None, ("close_path_id", "api_key", "nested", "argv", "note", "locals", "object",
                                           "terminal_cause", "password", "context")])
def test_offending_rows_never_print_credential_values_payloads_or_object_reprs(fields):
    """Codex review R4: the row report names each row by index and safe identity only."""
    with pytest.raises(AssertionError) as caught:
        assert_no_offending_rows(_leaky_rows(), lambda _row: True, "rows", fields=fields)
    report = str(caught.value)
    assert _SENTINEL not in report, report
    assert "Opaque(" not in report, report
    for index, identity in enumerate(("h5-a", "h5-b", "h5-c", "h5-d", "h5-e")):
        assert f"[{index}]" in report and identity in report, report
    assert "'api_key': '<redacted>'" in report
    assert "'password': '<redacted>'" in report or "password='<redacted>'" in report
    assert "<_Opaque>" in report


def test_a_missing_row_report_never_prints_credential_values_payloads_or_object_reprs():
    with pytest.raises(AssertionError) as caught:
        assert_some_row(_leaky_rows(), lambda _row: False, "a matching row")
    report = str(caught.value)
    assert _SENTINEL not in report, report
    assert "Opaque(" not in report, report
    assert "h5-a" in report and "h5-e" in report, report


def test_safe_values_keep_their_identity_in_the_row_report():
    with pytest.raises(AssertionError) as caught:
        assert_no_offending_rows(
            [("RecordA", 3, None, True, Classification.CANONICAL, "src/x.py:12 in close")],
            lambda _row: True,
            "rows",
        )
    report = str(caught.value)
    assert "('RecordA', 3, None, True, Classification.CANONICAL, 'src/x.py:12 in close')" in report, report


def test_a_missing_row_lists_the_candidates_that_did_not_match():
    with pytest.raises(AssertionError, match=r"must end with .put: none of 2 row\(s\) matched; first 2:\n  \[0\] 'a.get'\n  \[1\] 'b.pop'"):
        assert_some_row(["a.get", "b.pop"], lambda reference: reference.endswith(".put"), "must end with .put")
