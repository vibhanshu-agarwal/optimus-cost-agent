"""Plan 12.3 Design 8: a TEST command runs contained, with a deadline and the turn's cancellation, and its
stop is bounded. Real child processes: a timeout and a cancellation leave no surviving descendants."""

from __future__ import annotations

import sys
import threading
import time

import pytest

from optimus.runtime import process_tree
from optimus.runtime.process_tree import CommandStopped, run_bounded
from tests.support.concurrency import DescendantRecorder, announce_pid_code, assert_descendants_killed
from tests.support.fault_injection import descendant_tree


def _never() -> bool:
    return False


def test_a_command_that_exits_returns_its_output_even_when_it_fills_the_pipe():
    code = "import sys; sys.stdout.write('x' * 1_000_000); sys.exit(3)"
    result = run_bounded([sys.executable, "-c", code], deadline=time.monotonic() + 60, cancelled=_never)
    assert (result.returncode, len(result.stdout)) == (3, 1_000_000)


def test_a_hung_command_and_its_descendants_are_stopped_at_the_deadline(tmp_path):
    code, roles = descendant_tree(tmp_path, "middle-exited")
    with DescendantRecorder(tmp_path, roles) as recorder:
        started = time.monotonic()
        with pytest.raises(CommandStopped) as stopped:
            run_bounded([sys.executable, "-c", code], deadline=started + 3, cancelled=_never)
        assert stopped.value.outcome == "timed_out"
        assert str(stopped.value) == "timed out after 3 s"
        assert_descendants_killed(recorder, roles, deadline=time.monotonic() + 5.0, what="a timed-out TEST")
    assert time.monotonic() - started < 3 + process_tree._CLEANUP_SECONDS


def test_a_cancelled_command_and_its_descendants_are_stopped(tmp_path):
    code, roles = descendant_tree(tmp_path, "parent-alive")
    cancel = threading.Event()
    with DescendantRecorder(tmp_path, roles) as recorder:
        threading.Thread(target=lambda: (recorder.wait_for(roles, timeout=30), cancel.set()), daemon=True).start()
        with pytest.raises(CommandStopped) as stopped:
            run_bounded([sys.executable, "-c", code], deadline=time.monotonic() + 60, cancelled=cancel.is_set)
        assert stopped.value.outcome == "cancelled"
        assert_descendants_killed(recorder, roles, deadline=time.monotonic() + 5.0, what="a cancelled TEST")


def test_a_stop_that_cannot_be_confirmed_is_reported_within_the_bound(monkeypatch):
    monkeypatch.setattr(process_tree, "_CLEANUP_SECONDS", 1.0)
    real_kill = process_tree.kill_tree
    survivors = []
    monkeypatch.setattr(process_tree, "kill_tree", survivors.append)  # the kill silently does nothing
    started = time.monotonic()
    with pytest.raises(CommandStopped) as stopped:
        run_bounded([sys.executable, "-c", "import time; time.sleep(60)"], deadline=started + 1, cancelled=_never)
    try:
        assert stopped.value.outcome == "stop_unconfirmed"
        assert time.monotonic() - started < 1 + 1.0 + 1.0
    finally:
        for process in survivors:
            real_kill(process)
            process.wait(10)


def test_a_command_that_cannot_be_contained_is_refused(monkeypatch, tmp_path):
    marker = tmp_path / "ran"

    def refuse(args, **kwargs):
        raise process_tree.ContainmentError("injected: the job refused the process")

    monkeypatch.setattr(process_tree, "popen", refuse)
    with pytest.raises(CommandStopped) as stopped:
        run_bounded([sys.executable, "-c", f"open({str(marker)!r}, 'w').close()"], deadline=time.monotonic() + 60, cancelled=_never)
    assert stopped.value.outcome == "containment_failed"
    assert not marker.exists()


def test_a_descendant_that_outlives_its_root_makes_the_stop_unconfirmed(monkeypatch):
    """Codex Checkpoint B, 2: the root exits and its pipes close while a descendant that redirected them runs on."""
    monkeypatch.setattr(process_tree, "_CLEANUP_SECONDS", 3.0)
    real_kill = process_tree.kill_tree
    survivors: list = []
    monkeypatch.setattr(process_tree, "kill_tree", survivors.append)  # injected: the kill does nothing
    code = (
        "import subprocess, sys, time; "
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], "
        "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
        "time.sleep(2)"
    )
    started = time.monotonic()
    with pytest.raises(CommandStopped) as stopped:
        run_bounded([sys.executable, "-c", code], deadline=started + 1, cancelled=_never)
    try:
        assert stopped.value.outcome == "stop_unconfirmed"
        assert time.monotonic() - started < 1 + 3.0 + 1.0
    finally:
        for process in survivors:
            real_kill(process)


def test_a_missing_executable_is_an_ordinary_launch_failure_not_a_containment_failure():
    with pytest.raises(OSError) as raised:
        run_bounded(["optimus-no-such-test-runner-12-3"], deadline=time.monotonic() + 60, cancelled=_never)
    assert not isinstance(raised.value, process_tree.ContainmentError)


@pytest.mark.skipif(sys.platform != "win32", reason="job containment is the Windows path")
def test_a_containment_failure_after_the_child_started_never_claims_it_did_not_run(monkeypatch):
    """Codex Checkpoint B, 1: a resume can let the child run before setup fails; it is stopped, not "not run"."""
    real_resume = process_tree._resume

    def resume_then_fail(pid):
        real_resume(pid)
        raise OSError("injected: setup failed after the child ran")

    monkeypatch.setattr(process_tree, "_resume", resume_then_fail)
    with pytest.raises(CommandStopped) as stopped:
        run_bounded([sys.executable, "-c", "import time; time.sleep(30)"], deadline=time.monotonic() + 60, cancelled=_never)
    assert stopped.value.outcome == "containment_failed"
    assert "after the command started" in str(stopped.value)


@pytest.mark.skipif(sys.platform != "win32", reason="job containment is the Windows path")
def test_a_containment_cleanup_that_fails_is_an_unconfirmed_stop(monkeypatch):
    def fail_resume(_pid):
        raise OSError("injected: resume failed")

    def fail_terminate(_job):
        raise OSError("injected: terminate failed")

    monkeypatch.setattr(process_tree, "_resume", fail_resume)
    monkeypatch.setattr(process_tree, "_terminate_job", fail_terminate)
    with pytest.raises(CommandStopped) as stopped:
        run_bounded([sys.executable, "-c", "pass"], deadline=time.monotonic() + 60, cancelled=_never)
    assert stopped.value.outcome == "stop_unconfirmed"


def test_a_cancellation_that_arrives_as_the_root_exits_still_stops_its_descendants(tmp_path):
    """Codex Checkpoint B re-review: the cancel lands during communicate(), the root exits and closes its pipes,
    and a descendant that redirected them runs on. The tree is still stopped, and the TEST reports a cancellation."""
    marker = tmp_path / "root-exited"
    grandchild = announce_pid_code(tmp_path, "grandchild") + "; import time; time.sleep(60)"
    code = (
        "import pathlib, subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {grandchild!r}], "
        "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
        "time.sleep(1); "
        f"pathlib.Path({str(marker)!r}).touch()"
    )
    with DescendantRecorder(tmp_path, ("grandchild",)) as recorder:
        with pytest.raises(CommandStopped) as stopped:
            run_bounded([sys.executable, "-c", code], deadline=time.monotonic() + 60, cancelled=marker.exists)
        assert stopped.value.outcome == "cancelled"
        assert_descendants_killed(recorder, ("grandchild",), deadline=time.monotonic() + 5.0, what="a TEST cancelled as its root exited")
