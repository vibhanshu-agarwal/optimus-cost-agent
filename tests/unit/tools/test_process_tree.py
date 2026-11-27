"""tools.process_tree: a started child and every descendant it creates are killed together."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time

import pytest

from tests.support.concurrency import DescendantRecorder, assert_descendants_killed
from tests.support.fault_injection import TREE_SHAPES, descendant_tree
from tools import process_tree


@pytest.mark.parametrize("shape", TREE_SHAPES)
@pytest.mark.parametrize(
    "force_fallback",
    [False, pytest.param(True, marks=pytest.mark.skipif(sys.platform != "linux", reason="Linux non-pidfd fallback"))],
)
def test_kill_tree_kills_every_descendant_including_ones_no_parent_walk_reaches(tmp_path, shape, monkeypatch, force_fallback):
    if force_fallback:
        monkeypatch.delattr(os, "pidfd_open", raising=False)
    code, roles = descendant_tree(tmp_path, shape)
    with DescendantRecorder(tmp_path, roles) as recorder:
        process = process_tree.popen([sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            assert recorder.wait_for(roles, timeout=30), f"the {shape} tree never formed"
            killed_at = time.monotonic()
            process_tree.kill_tree(process)
            # The named verdict comes first: a survivor would otherwise surface only as a pipe timeout.
            assert_descendants_killed(recorder, roles, deadline=killed_at + 5.0, what=f"kill_tree ({shape})")
            # Every holder of the pipes is gone, so collection ends without waiting out the sleeps.
            process.communicate(timeout=10)
            assert process_tree.wait_for_empty(process, deadline=time.monotonic() + 5)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(10)


@pytest.mark.skipif(sys.platform != "win32", reason="job objects are the Windows path")
def test_a_contained_tree_stays_in_the_runs_job_and_dies_without_ending_the_run(tmp_path):
    """The guarded test run's kill-on-close job still attributes and outlives a contained tree (#274)."""
    from tools.testing import run_context_windows

    owner = run_context_windows.owner()
    if owner is None or owner.handle is None:
        pytest.skip("this interpreter did not enrol in a run job (for example an xdist worker)")
    code, roles = descendant_tree(tmp_path, "parent-alive")
    seen: dict[str, run_context_windows.ProcessIdentity] = {}

    def announced() -> None:  # pin each member that has announced itself, by pid and creation time
        for role in roles:
            path = tmp_path / f"{role}.pid"
            if role not in seen and path.exists():
                seen[role] = run_context_windows.process_identity(int(path.read_text(encoding="utf-8")))

    with DescendantRecorder(tmp_path, roles) as recorder:
        launched_at = time.monotonic()  # every member starts its 30 s sleep after this
        process = process_tree.popen([sys.executable, "-c", code])
        try:
            formed = recorder.wait_for(roles, timeout=15)
            announced()
            assert formed, "the tree never formed"
            for role in roles:
                assert run_context_windows.is_member(seen[role]) is True, role
            killed_at = time.monotonic()
            # The verdict is taken by launched_at + 25 s, before any member could exit on its own.
            assert killed_at - launched_at < 20, "too slow to tell the kill from the members' natural exit"
            process_tree.kill_tree(process)
            assert_descendants_killed(recorder, roles, deadline=killed_at + 5.0, what="kill_tree inside the run job")
            assert process_tree.wait_for_empty(process, deadline=time.monotonic() + 5)
            assert process.wait(10) == 1, "the root was not ended by the job"  # a natural exit would be 0
        finally:
            with contextlib.suppress(OSError):
                process_tree.kill_tree(process)  # ends the whole job, also when an assertion above failed
            announced()
            for identity in seen.values():  # whatever is still running from this tree is stopped directly
                now = run_context_windows.process_identity(identity.pid)
                if now.live and identity.creation_time is not None and now.creation_time == identity.creation_time:
                    with contextlib.suppress(OSError):
                        os.kill(identity.pid, signal.SIGTERM)
            if process.poll() is None:
                process.kill()
            process.wait(10)
    assert run_context_windows.is_member(run_context_windows.current_identity()) is True
    assert run_context_windows.accounting()["ok"] is True


@pytest.mark.skipif(sys.platform != "win32", reason="kernel32 is the Windows path")
def test_the_run_context_and_the_process_tree_share_one_kernel32_binding():
    from tools.testing import run_context_windows

    assert run_context_windows._kernel32() is process_tree.kernel32()  # noqa: SLF001


class _NoSymbols:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass


def _load_refused(*_args: object, **_kwargs: object) -> object:
    raise OSError("kernel32 could not be loaded")


@pytest.mark.skipif(sys.platform != "win32", reason="kernel32 is the Windows path")
@pytest.mark.parametrize(("windll", "raised"), [(_load_refused, OSError), (_NoSymbols, AttributeError)])
def test_a_binding_that_cannot_load_raises_from_the_first_native_call_as_before(monkeypatch, windll, raised):
    """Unchanged by #274: a load or a missing-symbol failure raises from the first call, never at import."""
    import ctypes

    from tools.testing import run_context_windows

    monkeypatch.setattr(process_tree, "_api", None)
    monkeypatch.setattr(run_context_windows, "_api", None)
    monkeypatch.setattr(ctypes, "WinDLL", windll)
    with pytest.raises(raised):
        run_context_windows.current_identity()


def test_pipe_cleanup_reuses_one_budget_and_reports_all_unconfirmed_stages(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    clock = iter((0, 4, 5))
    monkeypatch.setattr(process_tree, "time", SimpleNamespace(monotonic=lambda: next(clock)))
    kill = Mock(side_effect=OSError("tree refusal"))
    monkeypatch.setattr(process_tree, "kill_tree", kill)
    process = Mock()
    process.wait.side_effect = subprocess.TimeoutExpired("child", 5)
    stdout_reader, stderr_reader = Mock(), Mock()
    stdout_reader.is_alive.return_value = True
    stderr_reader.is_alive.return_value = True

    with pytest.raises(process_tree.PipeCleanupError) as failure:
        process_tree.stop_piped_process(process, (stdout_reader, stderr_reader), deadline=5)
    assert str(failure.value) == (
        "process tree termination failed, root process reap unconfirmed, capture readers still running"
    )
    kill.assert_called_once_with(process)
    process.wait.assert_called_once_with(timeout=5)
    stdout_reader.join.assert_called_once_with(timeout=1)
    stderr_reader.join.assert_called_once_with(timeout=0)


def test_a_tree_child_runs_normally_and_keeps_the_callers_arguments(tmp_path):
    flags = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == "win32" else {}
    process = process_tree.popen(
        [sys.executable, "-c", "import os, sys; print(os.getcwd()); sys.exit(7)"],
        cwd=tmp_path, stdout=subprocess.PIPE, text=True, **flags,
    )
    out, _ = process.communicate(timeout=30)
    assert process.returncode == 7
    assert out.strip() == str(tmp_path)


def test_kill_tree_after_the_whole_tree_exited_is_harmless():
    process = process_tree.popen([sys.executable, "-c", "pass"])
    assert process_tree.wait_for_empty(process, deadline=time.monotonic() + 30)
    process_tree.kill_tree(process)
    assert process.returncode == 0


def test_kill_tree_refuses_a_process_it_did_not_start():
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        with pytest.raises(ValueError, match="started by tools.process_tree.popen"):
            process_tree.kill_tree(process)
        with pytest.raises(ValueError, match="tracked"):
            process_tree.wait_for_empty(process, deadline=time.monotonic())
    finally:
        process.kill()
        process.wait(10)


@pytest.mark.skipif(sys.platform != "win32", reason="job containment is the Windows path")
def test_a_child_that_cannot_be_contained_never_runs_and_the_error_is_raised(tmp_path, monkeypatch):
    started: list[subprocess.Popen[bytes]] = []
    real_popen = subprocess.Popen

    def recording_popen(*args, **kwargs):
        started.append(real_popen(*args, **kwargs))
        return started[-1]

    def refuse(_job, _pid):
        raise OSError("injected: the job refused the process")

    monkeypatch.setattr(subprocess, "Popen", recording_popen)
    monkeypatch.setattr(process_tree, "_assign", refuse)
    marker = tmp_path / "ran"
    with pytest.raises(OSError, match="injected"):
        process_tree.popen([sys.executable, "-c", f"open({str(marker)!r}, 'w').close()"])
    assert len(started) == 1
    assert started[0].returncode is not None, "the suspended child was left behind"
    assert not marker.exists(), "the child ran although it was never contained"


@pytest.mark.skipif(sys.platform != "win32", reason="job containment is the Windows path")
def test_a_failure_after_the_child_ran_kills_its_whole_tree_and_keeps_the_error(tmp_path, monkeypatch):
    """Codex review R2: setup can fail after the child has run and started descendants. The job is
    terminated (not just closed), so the whole tree dies, and the initiating error is raised."""
    code, roles = descendant_tree(tmp_path, "middle-exited")
    real_resume = process_tree._resume
    with DescendantRecorder(tmp_path, roles) as recorder:

        def resume_then_fail(pid):
            real_resume(pid)
            assert recorder.wait_for(roles, timeout=30), "the tree never formed"
            raise OSError("injected: setup failed after the child ran")

        monkeypatch.setattr(process_tree, "_resume", resume_then_fail)
        with pytest.raises(OSError, match="injected: setup failed after the child ran"):
            process_tree.popen([sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert_descendants_killed(recorder, roles, deadline=time.monotonic() + 5.0, what="post-resume failure cleanup")


@pytest.mark.skipif(sys.platform != "win32", reason="job containment is the Windows path")
def test_a_cleanup_failure_is_attached_to_the_initiating_error_and_the_root_is_still_reaped(monkeypatch):
    started: list[subprocess.Popen[bytes]] = []
    real_popen = subprocess.Popen

    def recording_popen(*args, **kwargs):
        started.append(real_popen(*args, **kwargs))
        return started[-1]

    def fail_resume(_pid):
        raise OSError("injected: resume failed")

    def fail_terminate(_job):
        raise OSError("injected: terminate failed")

    monkeypatch.setattr(subprocess, "Popen", recording_popen)
    monkeypatch.setattr(process_tree, "_resume", fail_resume)
    monkeypatch.setattr(process_tree, "_terminate_job", fail_terminate)
    with pytest.raises(OSError, match="injected: resume failed") as caught:
        process_tree.popen([sys.executable, "-c", "pass"])
    notes = getattr(caught.value, "__notes__", [])
    assert any("terminating the job failed" in note and "injected: terminate failed" in note for note in notes), notes
    assert started[0].returncode is not None, "the root was not reaped"


@pytest.mark.skipif(sys.platform == "win32", reason="process groups are the POSIX path")
def test_popen_refuses_to_share_the_callers_session():
    with pytest.raises(ValueError, match="start_new_session"):
        process_tree.popen([sys.executable, "-c", "pass"], start_new_session=False)
