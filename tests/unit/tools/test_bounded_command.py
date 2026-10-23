"""Plan 12.3 Design 8: a TEST command runs contained, with a deadline and the turn's cancellation, and its
stop is bounded. Real child processes: a timeout and a cancellation leave no surviving descendants."""

from __future__ import annotations

import sys
import threading
import time

import pytest

from optimus.runtime import process_tree
from optimus.runtime.process_tree import CommandStopped, run_bounded
from tests.support.concurrency import DescendantRecorder, assert_descendants_killed
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
