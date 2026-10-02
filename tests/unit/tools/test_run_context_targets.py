"""Synthetic targets for nested run-context probes.

Every test here does nothing in an ordinary run. A probe in `test_run_context_lifecycle.py` starts a
real nested pytest on one of them and selects a behaviour through the environment, so no failing,
skipping or long-running test is ever part of the default selection.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from tools.testing import run_context, run_context_windows

BEHAVIOUR_VARIABLE = "OPTIMUS_TEST_RUN_CONTEXT_BEHAVIOUR"
PLANT_VARIABLE = "OPTIMUS_TEST_RUN_CONTEXT_PLANT"
HOLD_VARIABLE = "OPTIMUS_TEST_RUN_CONTEXT_HOLD"
_BEHAVIOUR = os.environ.get(BEHAVIOUR_VARIABLE, "")
_ROOT = Path(__file__).resolve().parents[3]
_THIS = "tests/unit/tools/test_run_context_targets.py"

if _BEHAVIOUR == "collection_error":
    raise RuntimeError("synthetic collection error")


def _wait_for(path: Path, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def _behaviour() -> Iterator[None]:
    if _BEHAVIOUR == "setup_skip":
        # The reason carries a secret-shaped assignment, built here so no such literal is in the file.
        pytest.skip("synthetic setup skip " + "token" + "=" + "hunter2" * 2)
    yield
    if _BEHAVIOUR == "teardown_failure":
        raise RuntimeError("synthetic teardown failure")


def test_behaviour_target(_behaviour: None) -> None:
    if _BEHAVIOUR == "interrupt":
        raise KeyboardInterrupt


def test_held_nested_target() -> None:
    """The nested child of a planted run: reports its own run, then waits until it is ended."""
    folder = os.environ.get(HOLD_VARIABLE)
    if not folder:
        return
    context = run_context.current()
    assert context is not None
    Path(folder, "nested.json").write_text(json.dumps({"run_id": context.run_id, "root": context.root}), encoding="utf-8")
    _wait_for(Path(folder, "release-nested"), 300)


def test_planted_run_target() -> None:
    """A planted run: starts a sleeping child and a nested pytest, reports every member, then waits."""
    folder = os.environ.get(PLANT_VARIABLE)
    if not folder:
        return
    context = run_context.current()
    assert context is not None and context.native.get("enrolled"), "a planted run must own its job"
    subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])  # noqa: S603 - this interpreter
    environment = {name: value for name, value in os.environ.items() if name != PLANT_VARIABLE}
    environment[HOLD_VARIABLE] = folder
    subprocess.Popen(  # noqa: S603 - this interpreter running this file's own nested target
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", f"{_THIS}::test_held_nested_target"],
        cwd=_ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    assert _wait_for(Path(folder, "nested.json"), 120), "the nested pytest never reported"
    members, error = run_context_windows.members()
    assert members is not None, error
    Path(folder, "plant.json").write_text(json.dumps({
        "run_id": context.run_id, "root": context.root, "job_name": context.native.get("job_name"),
        "members": [{"pid": member.pid, "creation_time": member.creation_time} for member in members],
        "nested": json.loads(Path(folder, "nested.json").read_text(encoding="utf-8")),
    }), encoding="utf-8")
    # Released: return normally, leaving the sleeper and the nested pytest running. Not released:
    # the observer ends this process abruptly while it waits here.
    _wait_for(Path(folder, "release"), 300)
