"""The targets of the xdist controls (Plan 11.30 Task 5): core tests that do nothing outside those controls.

Kept apart from `test_run_context_xdist.py`, which reads the running platform and is therefore platform-tagged: a
tagged node always stays serial, and these must be admitted to core-parallel.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tools.testing import run_context
from tools.testing import run_context_xdist as xdist_context


@pytest.mark.parametrize("index", range(4))
def test_xdist_probe(index: int, pytestconfig: pytest.Config) -> None:
    """A core-parallel target for the nested xdist runs. Outside them it does nothing.

    `P1130_XDIST_PROBE_OUT` is a folder where each probe writes its own file of what it saw (never one shared file:
    two processes appending to one file can lose a line); `P1130_XDIST_PROBE` scripts one behaviour in worker gw0:
    `crash` ends the worker abruptly, `sleep` holds it, `grandchild` leaves a child process running.
    """
    out = os.environ.get("P1130_XDIST_PROBE_OUT")
    if not out:
        return
    worker = os.environ.get("PYTEST_XDIST_WORKER", "")
    action = os.environ.get("P1130_XDIST_PROBE", "")
    state = xdist_context.current_worker()
    facts: dict[str, object] = {"index": index, "worker": worker, "pid": os.getpid(),
                                "run_context": run_context.current() is not None,
                                "controller": None if state is None else state.controller_root["pid"],
                                "secret_visible": xdist_context.WORKER_INPUT in getattr(pytestconfig, "workerinput", {})}
    if action == "grandchild" and worker == "gw0":
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])  # noqa: S603 - fixed program
        facts["grandchild"] = child.pid
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / f"{index}.json").write_text(json.dumps(facts), encoding="utf-8")
    if worker != "gw0":
        return
    if action == "crash":
        os._exit(3)
    if action == "sleep":
        time.sleep(300)


def test_xdist_serial_probe() -> None:
    """A core target the reviewed [parallel] rule keeps serial: the runner's serial remainder in its core controls."""
