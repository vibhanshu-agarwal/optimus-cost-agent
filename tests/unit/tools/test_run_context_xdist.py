"""Plan 11.30 Task 5: core-only xdist under one controller-owned run (v4 design contract 5).

The fast controls drive the controller's verdict on synthetic worker facts, one planted fault at a time. The real
controls run nested pytest-xdist sessions of this repository with two real worker processes, never fakes: the
ordinary run, a crash with no restart, absent or forged worker metadata, an absent guard, a worker on other
sources, a duplicated report, a collection disagreement, an interrupted controller, a stray grandchild, and every
refusal that must happen before a worker starts.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.testing import run_context_records
from tools.testing import run_context_xdist as xdist_context

_ROOT = Path(__file__).resolve().parents[3]
_PROBES = [f"tests/unit/tools/test_run_context_xdist_probes.py::test_xdist_probe[{index}]" for index in range(4)]
_RUN_ID = re.compile(r"test-run-context: .* run=(?P<run>\S+)")
_WINDOWS = sys.platform == "win32"
_PARALLEL = ("-n", "2", "--max-worker-restart=0", "--profile", "core-parallel", "--no-cov")


# --- fast controls: the verdict, one planted fault at a time ---------------------------------------------------


def _facts() -> dict[str, object]:
    return {"python": "3.14.4", "pytest": "9.0.1", "lock_sha256": "a" * 64, "config_sha256": "b" * 64, "head": "c" * 40}


def _controller(tmp_path: Path) -> xdist_context.Controller:
    return xdist_context.Controller(
        run_id="20261007T000000-100-abcdef", root={"pid": 100, "creation_time": 7}, guard_mode="pytest_process_guard",
        facts=_facts(), records=tmp_path / "workers", native=True,
    )


def _worker_record(controller: xdist_context.Controller, worker: str, number: int, **changes: object) -> dict[str, object]:
    record = {
        "run_id": controller.run_id, "worker": worker, "pid": number, "creation_time": number * 10,
        "ancestry": {"status": "controller", "method": "validated_process_ancestry"},
        "guard_mode": "pytest_process_guard", "facts": _facts(),
    }
    record.update(changes)
    return record


class _Report:
    def __init__(self, nodeid: str, when: str, worker: str, outcome: str = "passed", channel: str | None = None) -> None:
        self.nodeid, self.when, self.outcome, self.worker_id = nodeid, when, outcome, worker
        if channel is not None:  # xdist sets the worker channel a report arrived on as `report.node`
            self.node = SimpleNamespace(gateway=SimpleNamespace(id=channel))


def _valid_run(tmp_path: Path, **record_changes: dict[str, object]) -> xdist_context.Controller:
    """Two workers that each ran two of four tests, signed records written, every phase forwarded once."""
    controller = _controller(tmp_path)
    nodes = [f"tests/t.py::test_{index}" for index in range(4)]
    for worker, pid, mine in (("gw0", 201, nodes[:2]), ("gw1", 202, nodes[2:])):
        controller.node_input(worker)
        record = _worker_record(controller, worker, pid, **record_changes.get(worker, {}))
        xdist_context.write_worker_record(controller.records / f"{worker}.json", record, token=controller.token)
        controller.collection(worker, nodes)
        for nodeid in mine:
            for when in ("setup", "call", "teardown"):
                controller.phase(_Report(nodeid, when, worker))
        controller.workers[worker].member = True  # the controller confirmed it in the run's job while it ran
        controller.down(worker, {"p1130_worker": {"pid": pid, "creation_time": pid * 10, "phases": 6,
                                                   "deselected": [], "unrun": 0}}, None)
    return controller


def _problems(controller: xdist_context.Controller, **kwargs: object) -> list[str]:
    options = {"ended": dict.fromkeys(controller.expected, "ENDED"), "survivors": []}
    options.update(kwargs)
    return controller.verdict(**options)["problems"]


def test_a_worker_signature_is_a_digest_that_writes_nothing_and_holds_no_record_value(tmp_path: Path, monkeypatch) -> None:
    """The signature's canonical text exists only to be hashed: nothing is written, and no record value survives."""
    monkeypatch.chdir(tmp_path)
    record = {"run_id": "20261007T000000-100-abcdef", "worker": "gw0", "pid": 4242, "creation_time": 777,
              "facts": {"head": "c" * 40}}
    signature = xdist_context.sign("a" * 64, record)
    assert re.fullmatch(r"[0-9a-f]{64}", signature)
    assert list(tmp_path.iterdir()) == []
    assert not any(str(value) in signature for value in ("4242", "777", "gw0", "abcdef", "c" * 40))
    assert xdist_context.sign("b" * 64, record) != signature  # bound to the run's secret
    assert xdist_context.sign("a" * 64, {**record, "schema": "x", "signature": "y"}) == signature


def test_the_worker_record_writer_refuses_a_record_outside_its_field_table(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    good = _worker_record(controller, "gw0", 201)
    xdist_context.write_worker_record(tmp_path / "ok.json", good, token=controller.token)
    assert run_context_records.read_worker_record(tmp_path / "ok.json") is not None
    for bad in ({**good, "command": "python -c secret"}, {**good, "worker": "worker zero"}, {**good, "facts": {"head": "x"}}):
        with pytest.raises(run_context_records.RecordRejected):
            xdist_context.write_worker_record(tmp_path / "bad.json", bad, token=controller.token)
    assert not (tmp_path / "bad.json").exists()


def test_a_complete_two_worker_run_is_valid(tmp_path: Path) -> None:
    controller = _valid_run(tmp_path)
    verdict = controller.verdict(ended={"gw0": "ENDED", "gw1": "ENDED"}, survivors=[])
    assert verdict["verdict"] == "valid", verdict
    assert verdict["problems"] == [] and verdict["workers"] == 2 and verdict["capability"] == "native"
    assert sorted(item["worker"] for item in verdict["identities"]) == ["gw0", "gw1"]


def test_a_worker_record_signed_with_another_token_is_forged(tmp_path: Path) -> None:
    controller = _valid_run(tmp_path)
    record = _worker_record(controller, "gw1", 202)
    xdist_context.write_worker_record(controller.records / "gw1.json", record, token="0" * 64)
    assert "signature:gw1" in _problems(controller)


def test_a_record_from_another_run_or_worker_is_refused(tmp_path: Path) -> None:
    assert "run_mismatch:gw1" in _problems(_valid_run(tmp_path, gw1={"run_id": "20261007T000000-999-abcdef"}))
    controller = _valid_run(tmp_path / "second")
    xdist_context.write_worker_record(controller.records / "gw1.json", _worker_record(controller, "gw0", 201),
                                      token=controller.token)  # gw0's own record, reused as gw1's
    problems = _problems(controller)
    assert "worker_mismatch:gw1" in problems and "identity_mismatch:gw1" in problems


def test_two_workers_claiming_one_process_are_refused(tmp_path: Path) -> None:
    controller = _valid_run(tmp_path, gw1={"pid": 201, "creation_time": 2010})
    controller.workers["gw1"].output["p1130_worker"].update(pid=201, creation_time=2010)
    assert "identity_reused" in _problems(controller)


def test_a_missing_record_ancestry_guard_or_source_difference_is_invalid(tmp_path: Path) -> None:
    controller = _valid_run(tmp_path)
    (controller.records / "gw0.json").unlink()
    assert "record_missing:gw0" in _problems(controller)
    assert "ancestry:gw1" in _problems(_valid_run(tmp_path / "a", gw1={"ancestry": {"status": "not_found", "reason": "ancestor_exited"}}))
    assert "guard:gw1" in _problems(_valid_run(tmp_path / "g", gw1={"guard_mode": "not_installed"}))
    assert "source:gw1" in _problems(_valid_run(tmp_path / "s", gw1={"facts": {**_facts(), "lock_sha256": "0" * 64}}))


def test_a_crashed_missing_or_unended_worker_is_invalid(tmp_path: Path) -> None:
    controller = _valid_run(tmp_path)
    controller.workers["gw0"].error = "worker 'gw0' crashed while running 'tests/t.py::test_1'"
    assert "crashed:gw0" in _problems(controller)
    controller = _valid_run(tmp_path / "missing")
    del controller.workers["gw1"]
    assert "worker_missing:gw1" in _problems(controller)
    assert "survivor:gw1" in _problems(_valid_run(tmp_path / "live"), ended={"gw0": "ENDED", "gw1": "LIVE"})
    assert "escaped_descendants" in _problems(_valid_run(tmp_path / "esc"), survivors=[{"pid": 9, "creation_time": 1}])


def test_duplicate_unknown_and_missing_phases_are_invalid(tmp_path: Path) -> None:
    controller = _valid_run(tmp_path)
    controller.phase(_Report("tests/t.py::test_0", "call", "gw0"))
    assert "duplicate_phase" in _problems(controller)
    controller = _valid_run(tmp_path / "unknown")
    controller.phase(_Report("tests/t.py::test_9", "call", "gw7"))
    assert "unknown_worker" in _problems(controller)
    controller = _valid_run(tmp_path / "count")
    controller.workers["gw0"].output["p1130_worker"]["phases"] = 7  # the worker sent one the controller never got
    assert "phases_lost:gw0" in _problems(controller)
    controller = _valid_run(tmp_path / "teardown")
    controller.phases.pop((xdist_context.node_key("tests/t.py::test_3"), "teardown"))
    controller.workers["gw1"].received -= 1
    controller.workers["gw1"].output["p1130_worker"]["phases"] = 5
    assert "node_incomplete" in _problems(controller)


def _balanced(controller: xdist_context.Controller, worker: str, change: int) -> None:
    """Keep a worker's own count equal to what the controller received, so only the phase facts can tell."""
    controller.workers[worker].output["p1130_worker"]["phases"] += change


def test_a_passing_setup_without_its_call_is_invalid_even_when_counts_balance(tmp_path: Path) -> None:
    """Codex D-M1 (a): totals alone never prove a test ran. A passing setup must be followed by its call."""
    controller = _valid_run(tmp_path)
    controller.phases.pop((xdist_context.node_key("tests/t.py::test_0"), "call"))
    controller.workers["gw0"].received -= 1
    _balanced(controller, "gw0", -1)
    assert "call_missing" in _problems(controller)


def test_a_test_whose_phases_came_from_two_workers_is_invalid_even_when_counts_balance(tmp_path: Path) -> None:
    """Codex D-M1 (b): one worker runs every phase of a test. Swapping two call phases' workers balances every
    total, and is still refused."""
    controller = _valid_run(tmp_path)
    first, second = (xdist_context.node_key(f"tests/t.py::test_{index}") for index in (0, 2))
    controller.phases[(first, "call")], controller.phases[(second, "call")] = (
        controller.phases[(second, "call")], controller.phases[(first, "call")])
    assert "mixed_owner" in _problems(controller)


def test_a_phase_of_a_test_outside_the_agreed_selection_is_invalid_even_when_counts_balance(tmp_path: Path) -> None:
    """Codex D-M1 (c): a known worker reporting a test nobody selected is refused, not only an unknown worker."""
    controller = _valid_run(tmp_path)
    controller.phase(_Report("tests/t.py::test_foreign", "call", "gw0"))
    _balanced(controller, "gw0", 1)
    assert "unselected_phase" in _problems(controller)


def _run_of(tmp_path: Path, phases: dict[str, list[tuple[str, str, str]]]) -> xdist_context.Controller:
    """A two-worker run whose workers sent exactly `phases` (node, when, outcome), each worker's count balanced."""
    controller = _controller(tmp_path)
    nodes = sorted({node for sent in phases.values() for node, _, _ in sent})
    for worker, pid in (("gw0", 201), ("gw1", 202)):
        controller.node_input(worker)
        xdist_context.write_worker_record(controller.records / f"{worker}.json",
                                          _worker_record(controller, worker, pid), token=controller.token)
        controller.collection(worker, nodes)
        for node, when, outcome in phases.get(worker, []):
            controller.phase(_Report(node, when, worker, outcome, channel=worker))
        controller.workers[worker].member = True
        controller.down(worker, {"p1130_worker": {"pid": pid, "creation_time": pid * 10, "phases": len(phases.get(worker, [])),
                                                   "deselected": [], "unrun": 0}}, None)
    return controller


def test_a_setup_that_skipped_or_failed_legitimately_has_no_call(tmp_path: Path) -> None:
    """A genuine setup skip or failure ends the test without a call: valid, beside complete passing, failing and
    skipping tests."""
    controller = _run_of(tmp_path, {
        "gw0": [("tests/t.py::test_skip", "setup", "skipped"), ("tests/t.py::test_skip", "teardown", "passed"),
                ("tests/t.py::test_pass", "setup", "passed"), ("tests/t.py::test_pass", "call", "passed"),
                ("tests/t.py::test_pass", "teardown", "passed")],
        "gw1": [("tests/t.py::test_error", "setup", "failed"), ("tests/t.py::test_error", "teardown", "passed"),
                ("tests/t.py::test_fail", "setup", "passed"), ("tests/t.py::test_fail", "call", "failed"),
                ("tests/t.py::test_fail", "teardown", "passed"),
                ("tests/t.py::test_inner_skip", "setup", "passed"), ("tests/t.py::test_inner_skip", "call", "skipped"),
                ("tests/t.py::test_inner_skip", "teardown", "passed")],
    })
    verdict = controller.verdict(ended={"gw0": "ENDED", "gw1": "ENDED"}, survivors=[])
    assert verdict["verdict"] == "valid" and verdict["problems"] == [], verdict


def test_a_call_after_a_setup_that_did_not_pass_is_invalid(tmp_path: Path) -> None:
    """pytest never runs a call after a skipped or failed setup: one that arrives is not a valid phase sequence."""
    controller = _run_of(tmp_path, {"gw0": [("tests/t.py::test_0", "setup", "skipped"), ("tests/t.py::test_0", "call", "passed"),
                                            ("tests/t.py::test_0", "teardown", "passed")]})
    assert "call_unexpected" in _problems(controller)


def test_a_phase_is_attributed_to_the_channel_it_arrived_on_not_to_the_worker_it_names(tmp_path: Path) -> None:
    """A report's `worker_id` is the worker's own claim; the channel xdist received it on is the controller's
    knowledge. A report from gw1's channel naming gw0 is attributed to gw1, and the disagreement is refused."""
    controller = _run_of(tmp_path, {"gw1": [("tests/t.py::test_0", "setup", "passed"), ("tests/t.py::test_0", "call", "passed"),
                                            ("tests/t.py::test_0", "teardown", "passed")]})
    controller.phase(_Report("tests/t.py::test_1", "setup", "gw0", channel="gw1"))
    _balanced(controller, "gw1", 1)
    assert controller.phases[(xdist_context.node_key("tests/t.py::test_1"), "setup")][0] == "gw1"
    assert "attribution:gw1" in _problems(controller)


def test_a_worker_the_controller_could_not_confirm_in_its_job_is_invalid(tmp_path: Path) -> None:
    """Fable Task 5 finding 1: a worker's record and output are its own self-report. On a native platform the
    controller confirms each worker's identity in the run's job itself while the worker runs."""
    for member in (False, None):
        controller = _valid_run(tmp_path / str(member))
        controller.workers["gw1"].member = member
        assert "membership:gw1" in _problems(controller)


def test_a_failing_controller_verdict_is_an_invalid_verdict_never_an_escape(tmp_path: Path, monkeypatch) -> None:
    """Fable Task 5 finding 3: the terminal work never raises into pytest; a failure in it is INVALID."""
    controller = _valid_run(tmp_path)

    def broken(identities):  # noqa: ANN001, ANN202
        raise OSError("query failed")

    monkeypatch.setattr(xdist_context, "_wait_ended", broken)
    verdict = xdist_context.finish_controller(controller)
    assert verdict["verdict"] == "INVALID" and verdict["problems"] == ["controller_failure"], verdict
    assert verdict["workers"] == 2


def test_a_native_run_without_its_job_cannot_say_nothing_escaped(tmp_path: Path, monkeypatch) -> None:
    """Fable Task 5 finding 4: without the run's job the members are unknown, never an empty list."""
    monkeypatch.setattr(xdist_context.native, "supported", lambda: True)
    monkeypatch.setattr(xdist_context.native, "owner", lambda: None)
    assert xdist_context._survivors() is None  # noqa: SLF001
    assert "members_unknown" in _problems(_valid_run(tmp_path), survivors=None)  # and the verdict says so


def test_workers_that_collected_different_tests_disagree(tmp_path: Path) -> None:
    controller = _valid_run(tmp_path)
    controller.collection("gw1", ["tests/t.py::test_0"])
    assert "collection_disagreement" in _problems(controller)


def test_without_native_ancestry_the_capability_is_labelled_weaker(tmp_path: Path) -> None:
    controller = xdist_context.Controller(
        run_id="20261007T000000-100-abcdef", root={"pid": 100, "creation_time": None}, guard_mode="unsupported_platform",
        facts=_facts(), records=tmp_path / "workers", native=False,
    )
    for worker, pid in (("gw0", 201), ("gw1", 202)):
        controller.node_input(worker)
        record = _worker_record(controller, worker, pid, guard_mode="unsupported_platform",
                                ancestry={"status": "pid_ancestry", "method": "proc_parent_chain"})
        xdist_context.write_worker_record(controller.records / f"{worker}.json", record, token=controller.token)
        controller.collection(worker, [])
        controller.down(worker, {"p1130_worker": {"pid": pid, "creation_time": pid * 10, "phases": 0,
                                                   "deselected": [], "unrun": 0}}, None)
    verdict = controller.verdict(ended={"gw0": "ENDED", "gw1": "ENDED"}, survivors=[])
    assert verdict["verdict"] == "valid" and verdict["capability"] == "weaker", verdict


# --- real controls: nested two-worker runs of this repository ---------------------------------------------------


def _nested(tmp_path: Path, *arguments: str, extra_env: dict[str, str] | None = None, timeout: float = 600) -> tuple[int, str]:
    """A real nested pytest of this repository; its temporary folders are tmp_path's."""
    scratch = tmp_path / "child-temp"
    scratch.mkdir(exist_ok=True)
    env = {**os.environ, "TMPDIR": str(scratch), "TEMP": str(scratch), "TMP": str(scratch), **(extra_env or {})}
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", *arguments],
        cwd=_ROOT, env=env, capture_output=True, text=True, timeout=timeout, check=False,
    )
    return completed.returncode, completed.stdout + completed.stderr


def _terminal(output: str) -> dict[str, object]:
    found = _RUN_ID.search(output)
    assert found is not None, output
    record = run_context_records.read_record(_ROOT / "tmp" / "test-runs" / found["run"] / "run.json")
    assert record is not None and record["checkpoint"] == "terminal", output
    return record


def _probe_lines(path: Path) -> list[dict[str, object]]:
    """What every probe saw: each probe index writes its own file."""
    found = []
    for index in range(len(_PROBES)):
        try:
            found.append(json.loads((path / f"{index}.json").read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue  # a probe that has not run, or is still writing its file
    return found


def test_two_real_workers_run_under_one_controller_owned_run(tmp_path: Path) -> None:
    out = tmp_path / "probes"
    code, output = _nested(tmp_path, *_PARALLEL, *_PROBES, extra_env={"P1130_XDIST_PROBE_OUT": str(out)})
    assert code == 0, output
    record = _terminal(output)
    verdict = record["xdist"]
    assert verdict["verdict"] == "valid" and verdict["workers"] == 2 and verdict["problems"] == [], output
    assert verdict["capability"] == ("native" if _WINDOWS else "weaker"), output
    assert record["completeness"] == "COMPLETE" and record["mode"] == "active", output
    lines = _probe_lines(out)
    assert sorted(line["index"] for line in lines) == [0, 1, 2, 3], lines
    assert {line["worker"] for line in lines} == {"gw0", "gw1"}, lines  # both real workers ran tests
    assert not any(line["run_context"] for line in lines), lines  # no worker holds the run's streams
    assert not any(line["secret_visible"] for line in lines), lines  # nor can its tests read the run's secret
    controller_pid = record["root"]["pid"]
    assert all(line["pid"] != controller_pid for line in lines), lines
    identities = {item["worker"]: item for item in verdict["identities"]}
    assert {line["worker"]: line["pid"] for line in lines} == {worker: item["pid"] for worker, item in identities.items()}
    phases, _refused, how = run_context_records.read_entries(
        _ROOT / "tmp" / "test-runs" / record["run_id"] / "phases.jsonl", "phases")
    assert how == "ok" and len(phases) == 12, phases
    assert {entry["worker"] for entry in phases} == {"gw0", "gw1"}  # every phase names the worker that ran it
    assert record["selected"] == 4, record


def test_a_crashed_worker_is_not_restarted_and_the_run_is_invalid(tmp_path: Path) -> None:
    out = tmp_path / "probes"
    code, output = _nested(tmp_path, *_PARALLEL, *_PROBES,
                           extra_env={"P1130_XDIST_PROBE_OUT": str(out), "P1130_XDIST_PROBE": "crash"})
    assert code != 0, output
    record = _terminal(output)
    assert record["xdist"]["verdict"] == "INVALID" and "crashed:gw0" in record["xdist"]["problems"], output
    assert record["completeness"] == "INVALID", output
    assert "replacing crashed worker" not in output, output  # --max-worker-restart=0: never a replacement


@pytest.mark.parametrize(
    ("fault", "problem"),
    [
        ("forged_token", "signature:gw1"),
        ("absent_guard", "guard:gw1"),
        ("wrong_source", "source:gw1"),
        ("duplicate_report", "duplicate_phase"),
        ("missing_call", "call_missing"),  # Codex D-M1: gw1 really skips one test's call; every count balances
        ("foreign_node", "unselected_phase"),  # Codex D-M1: gw1 sends a report for a test nobody selected, counted
        pytest.param("foreign_identity", "membership:gw1", marks=pytest.mark.skipif(
            not _WINDOWS, reason="membership in the run's job is the native capability")),
    ],
)
def test_a_planted_worker_or_report_fault_makes_the_run_invalid(tmp_path: Path, fault: str, problem: str) -> None:
    code, output = _nested(tmp_path, "-p", "tests.support.xdist_faults", *_PARALLEL, *_PROBES,
                           extra_env={"P1130_XDIST_FAULT": fault})
    record = _terminal(output)
    assert record["xdist"]["verdict"] == "INVALID" and problem in record["xdist"]["problems"], output
    assert record["completeness"] == "INVALID", output
    # Every test may have passed, but an INVALID worker verdict never leaves a passing session (WSL showed xdist
    # exiting 0 after a worker failed to start and its tests never ran).
    assert code != 0 and record["exit_status"] == code, output


def test_a_worker_without_run_metadata_refuses_to_start(tmp_path: Path) -> None:
    code, output = _nested(tmp_path, "-p", "tests.support.xdist_faults", *_PARALLEL, *_PROBES,
                           extra_env={"P1130_XDIST_FAULT": "absent_metadata"})
    assert code != 0, output
    assert "TEST_RUN_CONTEXT_XDIST_WORKER_METADATA" in output, output
    record = _terminal(output)
    assert record["xdist"]["verdict"] == "INVALID", output


def test_workers_that_collect_different_tests_fail_the_run(tmp_path: Path) -> None:
    code, output = _nested(tmp_path, "-p", "tests.support.xdist_faults", *_PARALLEL, *_PROBES,
                           extra_env={"P1130_XDIST_FAULT": "collection_disagreement"})
    assert code != 0, output
    record = _terminal(output)
    assert record["xdist"]["verdict"] == "INVALID" and "collection_disagreement" in record["xdist"]["problems"], output


@pytest.mark.parametrize(
    "arguments",
    [
        ("-n", "2", "--max-worker-restart=0", "--no-cov"),  # no profile
        ("-n", "2", "--max-worker-restart=0", "--profile", "core", "--no-cov"),  # not the reviewed parallel set
        ("-n", "3", "--max-worker-restart=0", "--profile", "core-parallel", "--no-cov"),
        ("-n", "2", "--profile", "core-parallel", "--no-cov"),  # worker restarts left on
        ("-n", "2", "--max-worker-restart=0", "--profile", "core-parallel", "--cov=optimus"),  # a second coverage writer
        ("-n", "2", "--max-worker-restart=0", "--dist", "loadfile", "--profile", "core-parallel", "--no-cov"),
    ],
)
def test_an_unsupported_parallel_request_is_refused_before_any_worker_starts(tmp_path: Path, arguments: tuple[str, ...]) -> None:
    code, output = _nested(tmp_path, *arguments, *_PROBES)
    assert code == pytest.ExitCode.USAGE_ERROR, output
    assert "TEST_RUN_CONTEXT_XDIST_REFUSED" in output, output
    assert "created: " not in output and "[gw0]" not in output, output  # no worker was ever created


def _ended(pid: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _gone(pid):
            return True
        time.sleep(0.25)
    return _gone(pid)


def _gone(pid: int) -> bool:
    if not _WINDOWS:
        return not Path(f"/proc/{pid}").exists()
    from tools.testing import run_context_windows as native

    identity = native.process_identity(pid)
    return (not identity.opened and identity.error == native.ERROR_INVALID_PARAMETER) or identity.live is False


def _kill(pid: int) -> None:
    if _WINDOWS:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, check=False)  # noqa: S603, S607
    else:
        os.kill(pid, 9)


def test_an_interrupted_controller_leaves_no_worker_running(tmp_path: Path) -> None:
    out = tmp_path / "probes"
    scratch = tmp_path / "child-temp"
    scratch.mkdir()
    env = {**os.environ, "TMPDIR": str(scratch), "TEMP": str(scratch), "TMP": str(scratch),
           "P1130_XDIST_PROBE_OUT": str(out), "P1130_XDIST_PROBE": "sleep"}
    launched = subprocess.Popen(  # noqa: S603 - this repository's own pytest
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", *_PARALLEL, *_PROBES],
        cwd=_ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    workers: list[int] = []
    try:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline and not any(line["worker"] == "gw0" for line in _probe_lines(out)):
            time.sleep(0.5)
        lines = _probe_lines(out)
        workers = sorted({int(line["pid"]) for line in lines})
        assert any(line["worker"] == "gw0" for line in lines), lines
        controllers = {line["controller"] for line in lines}
        assert len(controllers) == 1 and None not in controllers, lines
        _kill(int(controllers.pop()))
        for pid in workers:
            assert _ended(pid, 30), f"worker {pid} survived its controller"
    finally:
        for pid in workers:
            if not _gone(pid):
                _kill(pid)
        launched.kill()
        launched.communicate(timeout=60)


def test_a_grandchild_left_running_by_a_worker_is_an_escaped_descendant(tmp_path: Path) -> None:
    out = tmp_path / "probes"
    code, output = _nested(tmp_path, *_PARALLEL, *_PROBES,
                           extra_env={"P1130_XDIST_PROBE_OUT": str(out), "P1130_XDIST_PROBE": "grandchild"})
    grandchildren = [int(line["grandchild"]) for line in _probe_lines(out) if "grandchild" in line]
    try:
        assert grandchildren, output
        record = _terminal(output)
        if _WINDOWS:
            assert "escaped_descendants" in record["xdist"]["problems"], output
            # Attributed: each escaped process names its parent, here the worker that started it (Fable finding 5).
            workers = {item["pid"] for item in record["xdist"]["identities"]}
            escaped = {item["pid"]: item["parent_pid"] for item in record["xdist"]["escaped"]}
            assert set(grandchildren) <= set(escaped) and all(escaped[pid] in workers for pid in grandchildren), record
            assert record["completeness"] == "INVALID", output
            assert all(_ended(pid, 30) for pid in grandchildren), "the controller's job did not end the grandchild"
        else:  # without a job there is no member list: the capability says so, and the test cleans up itself
            assert record["xdist"]["capability"] == "weaker", output
        del code
    finally:
        for pid in grandchildren:
            if not _gone(pid):
                _kill(pid)
