"""The shared diagnostics helpers name what failed (operator directive 2026-10-02).

Each test injects a real failure of one kind -- a stuck thread, a pending task, a running process,
an offending row -- and proves the report names it, its target and where it is. A helper whose
report would not have named the cause is not done.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import threading

import pytest

from tests.support.concurrency import (
    assert_no_new_threads,
    assert_no_offending_rows,
    assert_processes_exited,
    assert_some_row,
    assert_tasks_done,
    assert_threads_alive,
    assert_threads_stopped,
    thread_baseline,
)


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


def test_a_missing_row_lists_the_candidates_that_did_not_match():
    with pytest.raises(AssertionError, match=r"must end with .put: none of 2 row\(s\) matched; first 2:\n  \[0\] 'a.get'\n  \[1\] 'b.pop'"):
        assert_some_row(["a.get", "b.pop"], lambda reference: reference.endswith(".put"), "must end with .put")
