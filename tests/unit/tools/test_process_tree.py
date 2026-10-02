"""tools.process_tree: a started child and every descendant it creates are killed together."""

from __future__ import annotations

import subprocess
import sys
import time

import pytest

from tests.support.concurrency import DescendantRecorder, assert_descendants_killed
from tests.support.fault_injection import TREE_SHAPES, descendant_tree
from tools import process_tree


@pytest.mark.parametrize("shape", TREE_SHAPES)
def test_kill_tree_kills_every_descendant_including_ones_no_parent_walk_reaches(tmp_path, shape):
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
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(10)


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
    process.wait(30)
    process_tree.kill_tree(process)
    assert process.returncode == 0


def test_kill_tree_refuses_a_process_it_did_not_start():
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        with pytest.raises(ValueError, match="started by tools.process_tree.popen"):
            process_tree.kill_tree(process)
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


@pytest.mark.skipif(sys.platform == "win32", reason="process groups are the POSIX path")
def test_popen_refuses_to_share_the_callers_session():
    with pytest.raises(ValueError, match="start_new_session"):
        process_tree.popen([sys.executable, "-c", "pass"], start_new_session=False)
