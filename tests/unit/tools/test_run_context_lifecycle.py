"""Ownership, lifecycle, per-test records and overlap for the pytest run context.

Nested runs are real pytest processes on the synthetic targets in `test_run_context_targets.py`.
The planted-run proofs use an outside observer that holds validated process handles and never a
job handle; the only process it ends is the planted root it started.
"""

from __future__ import annotations

import ctypes
import json
import os
import re
import secrets
import subprocess
import sys
import sysconfig
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.support import run_context_observer as observer
from tools.testing import run_context, run_context_guard, run_context_records, run_context_windows

_ROOT = Path(__file__).resolve().parents[3]
_TARGETS = "tests/unit/tools/test_run_context_targets.py"
_RUN = re.compile(r"run=(\d{8}T\d{6}-\d{1,10}-[0-9a-f]{6})")
_windows = pytest.mark.skipif(sys.platform != "win32", reason="native job ownership is Windows-only")


def _context() -> run_context.RunContext:
    context = run_context.current()
    assert context is not None, "the root conftest did not start a run context"
    return context


def _record(run_id: str) -> dict[str, object]:
    record = run_context_records.read_record(_ROOT / "tmp" / "test-runs" / run_id / "run.json")
    assert record is not None, run_id
    return record


def _stream(run_id: str, name: str) -> list[dict[str, object]]:
    entries, refused = run_context_records.read_entries(_ROOT / "tmp" / "test-runs" / run_id / f"{name}.jsonl", name)
    assert refused == 0
    return entries


def _nested(target: str, *arguments: str, behaviour: str = "") -> tuple[int, str, str]:
    environment = {name: value for name, value in os.environ.items() if not name.startswith("OPTIMUS_TEST_RUN_CONTEXT_")}
    if behaviour:
        environment["OPTIMUS_TEST_RUN_CONTEXT_BEHAVIOUR"] = behaviour
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", target, *arguments],
        cwd=_ROOT, env=environment, capture_output=True, text=True, timeout=300, check=False,
    )
    output = completed.stdout + completed.stderr
    found = _RUN.search(output)
    assert found is not None, output
    return completed.returncode, found.group(1), output


# --- Task 3: per-test records, collection identity, completeness.


def test_this_session_keeps_node_identities_phases_and_samples() -> None:
    context = _context()
    nodes = _stream(context.run_id, "nodes")
    assert context.counts["selected"] >= 1 and len(nodes) == context.counts["nodes"]
    assert all(len(str(entry["node"])) == 64 for entry in nodes)
    own = run_context._node(f"{_TARGETS.replace('targets', 'lifecycle')}::test_this_session_keeps_node_identities_phases_and_samples")  # noqa: SLF001
    assert own in {entry["node"] for entry in nodes if entry["state"] == "selected"}
    samples = _stream(context.run_id, "samples")
    assert samples and samples[0]["checkpoint"] == "start"
    # Nothing in this session has stopped a stream or failed to record so far.
    assert context.truncated is False and context.counts["recording_errors"] == 0, context.counts
    record = _record(context.run_id)
    assert record["python"] == ".".join(str(part) for part in sys.version_info[:3]) and record["config_sha256"]


def test_two_tests_that_share_a_label_keep_distinct_identities() -> None:
    first, second = 'tests/a.py::test_x[one two]', 'tests/a.py::test_x[one_two]'
    assert run_context._label(first) == run_context._label(second) == "tests/a.py::test_x[one_two]"  # noqa: SLF001
    assert run_context._node(first) != run_context._node(second)  # noqa: SLF001
    secret_shaped = "tests/a.py::test_x[" + "token" + "=" + "hunter2" * 2 + "]"
    assert run_context._label(secret_shaped) is None  # noqa: SLF001 - withheld; the digest still identifies it


@pytest.mark.parametrize(
    ("behaviour", "exit_code", "expected"),
    [
        ("", 0, [("setup", "passed"), ("call", "passed"), ("teardown", "passed")]),
        ("setup_skip", 0, [("setup", "skipped"), ("teardown", "passed")]),
        ("teardown_failure", 1, [("setup", "passed"), ("call", "passed"), ("teardown", "failed")]),
    ],
    ids=["passing", "setup-skip", "teardown-failure"],
)
def test_each_phase_outcome_is_kept_as_pytest_reported_it(behaviour: str, exit_code: int, expected: list[tuple[str, str]]) -> None:
    code, run_id, output = _nested(f"{_TARGETS}::test_behaviour_target", behaviour=behaviour)
    assert code == exit_code, output
    record, phases = _record(run_id), _stream(run_id, "phases")
    assert [(entry["when"], entry["outcome"]) for entry in phases] == expected
    assert (record["exit_status"], record["completeness"], record["selected"]) == (exit_code, "COMPLETE", 1)
    assert f"records=COMPLETE phases={len(expected)} exit={exit_code}" in output
    # A finished run has withdrawn its own announcement; its record stays in the worktree.
    assert not (run_context_records.registry_root() / f"{run_id}.json").exists()
    if behaviour == "setup_skip":
        reason = str(phases[0]["reason"])
        assert "synthetic setup skip" in reason and "hunter2" not in reason
        assert "hunter2" not in (_ROOT / "tmp" / "test-runs" / run_id / "phases.jsonl").read_text(encoding="utf-8")


def test_an_interrupted_run_is_never_recorded_as_a_clean_pass() -> None:
    code, run_id, output = _nested(f"{_TARGETS}::test_behaviour_target", behaviour="interrupt")
    record = _record(run_id)
    assert code == 2 and record["exit_status"] == 2 and "exit=2" in output, output
    assert ("call", "passed") not in [(entry["when"], entry["outcome"]) for entry in _stream(run_id, "phases")]


def test_a_collection_error_is_counted_and_never_recorded_as_a_clean_pass() -> None:
    code, run_id, output = _nested(_TARGETS, behaviour="collection_error")
    record = _record(run_id)
    assert code == 2 and record["exit_status"] == 2 and "exit=2" in output, output
    assert record["collection_errors"] == 1 and record["selected"] == 0 and _stream(run_id, "phases") == []


def test_deselected_tests_keep_their_identity() -> None:
    code, run_id, output = _nested(_TARGETS, "-k", "behaviour_target")
    assert code == 0, output
    record, nodes = _record(run_id), _stream(run_id, "nodes")
    assert (record["selected"], record["deselected"]) == (1, 2)
    states = sorted(str(entry["state"]) for entry in nodes)
    assert states == ["deselected", "deselected", "selected"]
    assert run_context._node(f"{_TARGETS}::test_planted_run_target") in {entry["node"] for entry in nodes if entry["state"] == "deselected"}  # noqa: SLF001


def _scratch_context(tmp_path: Path) -> run_context.RunContext:
    real = _context()
    scratch = run_context.RunContext(
        run_id=real.run_id, mode=real.mode, reason=real.reason, record_dir=tmp_path, started_utc=real.started_utc,
        worktree=real.worktree, started_monotonic=time.monotonic(), started_wall=time.time(),
    )
    scratch.last_sample = time.monotonic()  # no sample is due inside these unit checks
    return scratch


def _report(outcome: str = "passed", when: str = "call") -> SimpleNamespace:
    return SimpleNamespace(nodeid="tests/a.py::test_x", when=when, outcome=outcome, start=time.time(), duration=0.01, longrepr=None)


def test_a_stream_stops_at_its_ceiling_and_says_so(tmp_path: Path) -> None:
    assert run_context.MAX_STREAM_RECORDS == {"nodes": 40_000, "phases": 60_000, "samples": 5_000}
    assert run_context_records.MAX_STREAM_BYTES == 32 * 1024 * 1024 and run_context_records.MAX_RUN_FOLDERS == 2000
    scratch = _scratch_context(tmp_path)
    scratch.ceilings = {"nodes": 2, "phases": 2, "samples": 2}
    for _ in range(4):
        run_context.record_phase(scratch, _report())
    assert scratch.counts["phases"] == 2 and scratch.truncated is True
    assert run_context.completeness(scratch) == "TRUNCATED"
    assert len(run_context_records.read_entries(tmp_path / "phases.jsonl", "phases")[0]) == 2
    size = (tmp_path / "phases.jsonl").stat().st_size
    with pytest.raises(run_context_records.RecordTooLarge, match=run_context_records.TOO_LARGE):
        run_context_records.append_entries(tmp_path / "phases.jsonl", "phases", [
            {"node": "0" * 64, "when": "call", "outcome": "passed", "at": 0, "seconds": 0}], max_bytes=size + 10)
    assert (tmp_path / "phases.jsonl").stat().st_size == size


def test_a_recording_failure_is_counted_and_never_raised(tmp_path: Path) -> None:
    scratch = _scratch_context(tmp_path)
    run_context.record_phase(scratch, _report(outcome="not-an-outcome"))
    run_context.record_phase(scratch, SimpleNamespace())
    assert scratch.counts["recording_errors"] == 2 and scratch.counts["phases"] == 0
    assert run_context.completeness(scratch) == "INVALID" and not (tmp_path / "phases.jsonl").exists()


def test_a_damaged_stream_yields_only_its_whole_conforming_lines(tmp_path: Path) -> None:
    good = {"node": "a" * 64, "when": "call", "outcome": "passed", "at": 1.0, "seconds": 0.5}
    lines = [json.dumps(good), json.dumps({**good, "extra": "x"}), json.dumps({"node": "short"}), json.dumps(good)[:25]]
    (tmp_path / "phases.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert run_context_records.read_entries(tmp_path / "phases.jsonl", "phases") == ([good], 3)
    assert run_context_records.read_entries(tmp_path / "missing.jsonl", "phases") == ([], 0)
    shaped_like_an_assignment = "token" + "=" + "hunter2" * 2
    for bad in ({**good, "reason": "line\nbreak"}, {**good, "note": "x"}, {"node": "a" * 64}, {**good, "reason": shaped_like_an_assignment}):
        with pytest.raises(ValueError, match=run_context_records.REJECTED):
            run_context_records.append_entries(tmp_path / "refused.jsonl", "phases", [good, bad])
    assert not (tmp_path / "refused.jsonl").exists()


def test_old_finished_run_folders_are_pruned_and_unfinished_ones_kept(tmp_path: Path) -> None:
    start = run_context_records.read_record(_context().record_dir / "run.json")
    assert start is not None
    start.pop("schema")
    names = [f"2000010{day}T000000-{os.getpid()}-00000{day}" for day in range(1, 7)]
    for index, name in enumerate(names):
        checkpoint = "start" if index == 0 else "terminal"
        run_context_records.write_record(tmp_path / name / "run.json", {**start, "run_id": name, "checkpoint": checkpoint})
    (tmp_path / "not-a-run").mkdir()
    assert run_context_records.prune_run_folders(tmp_path, names[1], ceiling=3) == 1
    # Oldest three were candidates: the unfinished one and the current one stay; one is removed.
    assert sorted(entry.name for entry in tmp_path.iterdir()) == sorted([names[0], names[1], *names[3:], "not-a-run"])


# --- Task 4: what the guard protects is stated in the record.


@_windows
def test_the_record_states_how_many_folders_are_protected(monkeypatch: pytest.MonkeyPatch) -> None:
    context = _context()
    if context.guard_mode != "pytest_process_guard":
        pytest.skip("the MAIN-5 guard is in force; this guard installed nothing")
    record = _record(context.run_id)
    assert (record["protected_roots"], record["protection"]) == (4, "full")
    assert sorted(root.rsplit("\\", 1)[-1] for root in run_context_guard.protected_roots()) == [
        "optimus-cost-agent", "optimus-cost-agent", "python keyring", "python keyring"]
    monkeypatch.setattr(run_context_guard, "_protected_names", run_context_guard.protected_roots()[:3])
    assert run_context_guard.protection() == "reduced"
    monkeypatch.setattr(run_context_guard, "_mode", "not_installed")
    assert run_context_guard.protection() == "none"


# --- Task 2: enrolment failure, PID reuse, hop limit, repeated sessions.


class _Faulty:
    def __init__(self, real: object, **replaced: object) -> None:
        self._real, self._replaced = real, replaced

    def __getattr__(self, name: str) -> object:
        return self._replaced[name] if name in self._replaced else getattr(self._real, name)


def _fail(code: int):  # noqa: ANN202
    def call(*_arguments: object) -> int:
        ctypes.set_last_error(code)
        return 0

    return call


@_windows
@pytest.mark.parametrize(
    ("call", "expected"),
    [
        ("AssignProcessToJobObject", {"limits_set": True, "assigned": False, "assign_error": 5}),
        ("SetInformationJobObject", {"limits_set": False, "limits_error": 5}),
    ],
)
def test_an_enrolment_that_fails_claims_no_job(monkeypatch: pytest.MonkeyPatch, call: str, expected: dict[str, object]) -> None:
    real_owner = run_context_windows.owner()
    monkeypatch.setattr(run_context_windows, "_owner", None)
    monkeypatch.setattr(run_context_windows, "_api", _Faulty(run_context_windows._kernel32(), **{call: _fail(5)}))  # noqa: SLF001
    failed = run_context_windows.enroll(f"20000101T000000-{os.getpid()}-{secrets.token_hex(3)}")
    assert (failed.valid, failed.handle, failed.facts["enrolled"], failed.facts["created"]) == (False, None, False, True)
    assert {name: failed.facts.get(name) for name in expected} == expected
    assert ("assigned" in failed.facts) == (call == "AssignProcessToJobObject")
    monkeypatch.undo()
    assert run_context_windows.owner() is real_owner and run_context_windows.is_member(run_context_windows.current_identity()) is True


@_windows
def test_a_reused_pid_is_never_taken_for_the_process_it_replaced(monkeypatch: pytest.MonkeyPatch) -> None:
    own = run_context_windows.current_identity()
    impostor = run_context_windows.ProcessIdentity(pid=own.pid, creation_time=(own.creation_time or 0) + 1)
    assert run_context_windows.is_member(impostor) is None
    real = run_context_windows._kernel32()  # noqa: SLF001
    pseudo = real.GetCurrentProcess()

    def later(handle: object, created: object, *rest: object) -> int:
        read = real.GetProcessTimes(handle, created, *rest)
        if handle != pseudo:
            created._obj.dwHighDateTime = 0x7FFFFFFF  # noqa: SLF001 - a parent "created" after its child
        return read

    monkeypatch.setattr(run_context_windows, "_api", _Faulty(real, GetProcessTimes=later))
    assert run_context_windows.ancestors() == ([], "ancestor_exited")


@_windows
def test_a_walk_cut_off_by_the_hop_limit_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    chain, stopped = run_context_windows.ancestors(max_hops=1)
    assert len(chain) == 1 and stopped == "hop_limit"
    monkeypatch.setattr(run_context_windows, "ancestors", lambda: (chain, stopped))
    assert run_context._discover_parent_run("20000101T000000-1-000000") == {  # noqa: SLF001
        "status": "UNKNOWN", "reason": "hop_limit", "method": "validated_process_ancestry"}


_REPEATED_SESSIONS = '''
import pytest
target = "tests/unit/tools/test_run_context.py::test_probe_noop"
common = ["-p", "no:cacheprovider", "-q", target]
codes = [int(pytest.main(common)), int(pytest.main(common)), int(pytest.main([*common, "-m", "e2e"]))]
print("CODES=" + ",".join(str(code) for code in codes))
'''


@_windows
def test_a_second_default_session_reuses_the_job_and_a_passive_one_is_refused() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", _REPEATED_SESSIONS], cwd=_ROOT, capture_output=True, text=True, timeout=300, check=False,
    )
    output = completed.stdout + completed.stderr
    assert "CODES=0,0,4" in output and "separate interpreter" in output, output
    first, second = (_record(run_id) for run_id in _RUN.findall(output)[:2])
    assert (first["session_index"], second["session_index"]) == (1, 2)
    assert first["native"]["job_name"] == second["native"]["job_name"]
    assert first["native"]["reused_from_earlier_session"] is False and second["native"]["reused_from_earlier_session"] is True
    assert second["parent_run"] == {"status": "same_interpreter"} and second["native"]["valid"] is True
    assert "accounting_baseline" not in first and second["accounting_baseline"]["ok"] is True
    assert second["accounting"]["total_processes"] >= second["accounting_baseline"]["total_processes"]


# --- Tasks 2 and 3: a planted run takes its own processes with it and leaves another run alone.


def _plant(folder: Path, started_by: str) -> subprocess.Popen[bytes]:
    """Start a planted run through the venv launcher, or directly with the base interpreter.

    The venv launcher keeps its interpreter in a job of its own and that job already ends the
    tree when the interpreter exits. Started directly, with the environment's packages on
    PYTHONPATH, there is no such job: the run context's own job is then the only thing that can
    end the planted run's children, and every process it starts is a plain interpreter too.
    """
    folder.mkdir()
    environment = {**os.environ, "OPTIMUS_TEST_RUN_CONTEXT_PLANT": str(folder)}
    executable = sys.executable
    if started_by == "base_interpreter":
        executable = sys._base_executable  # noqa: SLF001 - the interpreter behind the venv launcher
        environment["PYTHONPATH"] = os.pathsep.join([sysconfig.get_paths()["purelib"], str(_ROOT / "src"), str(_ROOT)])
    with open(folder / "output.txt", "wb") as output:
        return subprocess.Popen(
            [executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", f"{_TARGETS}::test_planted_run_target"],
            cwd=_ROOT, env=environment, stdout=output, stderr=subprocess.STDOUT,
        )


def _planted(folder: Path) -> dict[str, object]:
    deadline = time.monotonic() + 180
    while not (folder / "plant.json").exists():
        assert time.monotonic() < deadline, (folder / "output.txt").read_text(encoding="utf-8", errors="replace")
        time.sleep(0.1)
    time.sleep(0.2)
    return json.loads((folder / "plant.json").read_text(encoding="utf-8"))


@_windows
@pytest.mark.parametrize("started_by", ["venv_launcher", "base_interpreter"])
@pytest.mark.parametrize("how", ["normal_exit", "abrupt_exit"])
def test_a_planted_run_takes_its_own_processes_with_it_and_leaves_another_run_alone(tmp_path: Path, how: str, started_by: str) -> None:
    if started_by == "base_interpreter" and getattr(sys, "_main5_guard_activated", False):
        pytest.skip("MAIN-5 requires every Python child to start through its attempt environment")
    survivor_process, planted_process = _plant(tmp_path / "survivor", started_by), _plant(tmp_path / "planted", started_by)
    fewest = 5 if started_by == "venv_launcher" else 3
    watched: list[observer.Watched] = []
    try:
        survivor, planted = _planted(tmp_path / "survivor"), _planted(tmp_path / "planted")
        root_pid = planted["root"]["pid"]
        own = observer.watch(planted["members"], may_end_pid=root_pid if how == "abrupt_exit" else None)
        others = observer.watch(survivor["members"])
        watched = [*own, *others]
        root = next(process for process in own if process.pid == root_pid)
        # Root, a sleeping child and a nested pytest; behind the venv launcher each is two processes.
        assert len(own) >= fewest and len(others) >= fewest
        assert all(process.handle is not None for process in watched), "every reported identity must validate"
        assert all(observer.is_gone(process) is False for process in watched)

        # Before anything ends: seen from this test's job, both planted runs are its own members.
        seen = {entry["run_id"]: entry["relation"] for entry in run_context.other_runs("none")[0]}
        assert seen.get(planted["run_id"]) == "own_job" and seen.get(survivor["run_id"]) == "own_job"

        if how == "normal_exit":
            (tmp_path / "planted" / "release").write_text("go", encoding="utf-8")
        else:
            assert observer.end(root) is True
            assert all(observer.end(process) is False for process in others), "the observer can end only the planted root"
        assert observer.wait_until_gone(root, 60) is not None, "the planted root never exited"
        waits = [observer.wait_until_gone(process, 5.0) for process in own]
        assert all(wait is not None for wait in waits), f"members still running five seconds after the root exited: {waits}"

        assert all(observer.is_gone(process) is False for process in others), "the independent run must be untouched"
        still = {entry["run_id"] for entry in run_context.other_runs("none")[0]}
        assert survivor["run_id"] in still and planted["run_id"] not in still and planted["nested"]["run_id"] not in still

        record = _record(planted["run_id"])
        if how == "normal_exit":
            assert planted_process.wait(timeout=30) == 0
            assert (record["checkpoint"], record["exit_status"], record["completeness"]) == ("terminal", 0, "COMPLETE")
            assert record["accounting"]["total_processes"] > 1
            last = _stream(planted["run_id"], "samples")[-1]
            relations = {entry["run_id"]: entry["relation"] for entry in last["others"]}
            assert last["checkpoint"] == "terminal"
            assert relations.get(survivor["run_id"]) == "outside" and relations.get(planted["nested"]["run_id"]) == "own_job"
        else:
            # No terminal record could be written: the record stays partial and the observer supplies the rest.
            assert record["checkpoint"] == "start" and "exit_status" not in record

        (tmp_path / "survivor" / "release").write_text("go", encoding="utf-8")
        assert survivor_process.wait(timeout=120) == 0
        assert all(observer.wait_until_gone(process, 5.0) is not None for process in others)
    finally:
        observer.close(watched)
        for process in (survivor_process, planted_process):
            if process.poll() is None:
                process.kill()
                process.wait(timeout=60)


def test_the_context_and_the_observer_never_open_a_job_or_start_a_thread() -> None:
    for module in (run_context, run_context_guard, run_context_records, run_context_windows, observer):
        source = Path(module.__file__).read_text(encoding="utf-8")
        found = [name for name in ("OpenJobObject", "import threading", "from threading", "Timer(") if name in source]
        assert found == [], f"{module.__name__} must not use {found}"
