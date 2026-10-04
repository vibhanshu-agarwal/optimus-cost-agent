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
    entries, refused, how = run_context_records.read_entries(_ROOT / "tmp" / "test-runs" / run_id / f"{name}.jsonl", name)
    assert (refused, how) in {(0, "ok"), (0, "missing")}
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
    """A context of this run's shape with its own run ID and folder, so nothing touches the real session's records."""
    real = _context()
    scratch = run_context.RunContext(
        run_id=f"20000101T000000-{os.getpid()}-{secrets.token_hex(3)}", mode=real.mode, reason=real.reason,
        record_dir=tmp_path, started_utc=real.started_utc, worktree=real.worktree,
        started_monotonic=time.monotonic(), started_wall=time.time(), root=dict(real.root), native=dict(real.native),
        parent_run=dict(real.parent_run),
        guard_mode=real.guard_mode, facts=dict(real.facts),
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


def test_an_append_that_fails_outside_the_entry_is_deferred_and_written_later(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Like tests/unit/acp/test_debug_trace.py: a test patches json.dumps to raise during its own call phase."""
    scratch = _scratch_context(tmp_path)

    def broken(*_arguments: object, **_options: object) -> str:
        raise TypeError("serialization blew up")

    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(json, "dumps", broken)
        run_context.record_phase(scratch, _report(when="call"))
    assert (scratch.counts["phases"], scratch.counts["deferred_appends"], scratch.counts["recording_errors"]) == (0, 1, 0)
    assert not (tmp_path / "phases.jsonl").exists()
    run_context.record_phase(scratch, _report(when="teardown"))
    entries, refused, how = run_context_records.read_entries(tmp_path / "phases.jsonl", "phases")
    assert [entry["when"] for entry in entries] == ["call", "teardown"] and (refused, how) == (0, "ok")
    assert (scratch.counts["phases"], scratch.pending["phases"]) == (2, [])
    assert run_context.completeness(scratch) == "COMPLETE"
    # Still failing at the end of the run: the actual terminal path makes a last attempt and fails.
    monkeypatch.setattr(json, "dumps", broken)
    run_context.record_phase(scratch, _report(when="setup"))
    assert scratch.pending["phases"] and scratch.counts["deferred_appends"] == 2
    monkeypatch.setattr(run_context, "_current", scratch)
    final = run_context.finish_run(scratch, 0)
    assert (final["exit_status"], final["completeness"]) == (0, "INVALID") and run_context.current() is None
    assert scratch.pending["phases"] == [] and scratch.counts["recording_errors"] >= 1


class _CloseFails:
    """A file whose bytes reach the disk and whose close then fails: the append's progress is unknown."""

    def __init__(self, inner: object) -> None:
        self._inner = inner

    def write(self, data: str) -> int:
        return self._inner.write(data)  # type: ignore[attr-defined]

    def __enter__(self) -> _CloseFails:
        return self

    def __exit__(self, *_arguments: object) -> None:
        self._inner.close()  # type: ignore[attr-defined]
        raise OSError("close blew up")


def _opening_phases_with_failing_close(real_open):  # noqa: ANN001, ANN202
    def opened(path: object, mode: str = "r", *arguments: object, **options: object) -> object:
        handle = real_open(path, mode, *arguments, **options)
        return _CloseFails(handle) if str(path).endswith("phases.jsonl") and "a" in mode else handle

    return opened


def test_an_append_with_unknown_progress_is_restored_then_retried_or_made_invalid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import builtins

    scratch = _scratch_context(tmp_path)
    run_context.record_phase(scratch, _report(when="setup"))
    size = (tmp_path / "phases.jsonl").stat().st_size
    real_open = builtins.open
    # Bytes reach the stream, then close fails: the stream is cut back to its earlier length and
    # the batch waits; the next append writes it once.
    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(builtins, "open", _opening_phases_with_failing_close(real_open))
        run_context.record_phase(scratch, _report(when="call"))
    assert (tmp_path / "phases.jsonl").stat().st_size == size
    assert (scratch.counts["phases"], scratch.counts["deferred_appends"], scratch.counts["recording_errors"]) == (1, 1, 0)
    run_context.record_phase(scratch, _report(when="teardown"))
    entries, refused, how = run_context_records.read_entries(tmp_path / "phases.jsonl", "phases")
    assert [entry["when"] for entry in entries] == ["setup", "call", "teardown"] and (refused, how) == (0, "ok")
    assert scratch.counts["phases"] == 3 and run_context.completeness(scratch) == "COMPLETE"
    # The same failure when the stream cannot be cut back: progress stays unknown, the record is INVALID.
    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(builtins, "open", _opening_phases_with_failing_close(real_open))
        patched.setattr(os, "truncate", lambda *_arguments: (_ for _ in ()).throw(OSError("truncate blew up")))
        run_context.record_phase(scratch, _report(when="setup"))
    assert (scratch.counts["phases"], scratch.counts["recording_errors"], scratch.pending["phases"]) == (3, 1, [])
    assert run_context.completeness(scratch) == "INVALID"
    # The terminal read-back sees the stray line that did reach the stream.
    monkeypatch.setattr(run_context, "_current", scratch)
    final = run_context.finish_run(scratch, 0)
    assert final["completeness"] == "INVALID" and final["streams"]["reconciled"] is False  # type: ignore[index]
    assert final["streams"]["read_back"]["phases"] == "differs"  # type: ignore[index]


def test_the_terminal_record_is_read_back_and_reconciled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    scratch = _scratch_context(tmp_path)
    for when in ("setup", "call", "teardown"):
        run_context.record_phase(scratch, _report(when=when))
    monkeypatch.setattr(run_context, "_current", scratch)
    final = run_context.finish_run(scratch, 0)
    assert final["completeness"] == "COMPLETE" and final["streams"]["reconciled"] is True, (final, scratch.counts)  # type: ignore[index]
    assert final["streams"]["read_back"] == {"nodes": "empty", "phases": "matches", "samples": "matches"}  # type: ignore[index]
    record = run_context_records.read_record(tmp_path / "run.json")
    assert record is not None and record["checkpoint"] == "terminal" and record["streams"]["reconciled"] is True
    assert run_context.current() is None


def test_a_terminal_failure_is_contained_and_still_cleans_up(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """json.dumps still patched when the session ends: no exception, exit status kept, entry withdrawn."""
    scratch = _scratch_context(tmp_path)
    run_context.record_phase(scratch, _report(when="call"))
    announcement = run_context_records.registry_root() / f"{scratch.run_id}.json"
    start = run_context_records.read_record(_context().record_dir / "run.json")
    assert start is not None
    start.pop("schema")
    run_context_records.write_record(announcement, {**start, "run_id": scratch.run_id})
    assert announcement.exists()

    def broken(*_arguments: object, **_options: object) -> str:
        raise TypeError("serialization blew up")

    monkeypatch.setattr(json, "dumps", broken)
    monkeypatch.setattr(run_context, "_current", scratch)
    final = run_context.finish_run(scratch, 3)
    assert (final["exit_status"], final["completeness"]) == (3, "INVALID")
    assert run_context.current() is None and not announcement.exists()
    monkeypatch.undo()
    record = run_context_records.read_record(tmp_path / "run.json")
    assert record is None or record["checkpoint"] == "start"
    # A failure anywhere else in the terminal work is contained the same way.
    another = _scratch_context(tmp_path / "another")
    run_context_records.write_record(run_context_records.registry_root() / f"{another.run_id}.json", {**start, "run_id": another.run_id})
    monkeypatch.setattr(run_context, "_read_back", lambda _context: (_ for _ in ()).throw(RuntimeError("read-back blew up")))
    monkeypatch.setattr(run_context, "_current", another)
    final = run_context.finish_run(another, 2)
    assert (final["exit_status"], final["completeness"]) == (2, "INVALID") and another.counts["recording_errors"] >= 1
    assert run_context.current() is None and not (run_context_records.registry_root() / f"{another.run_id}.json").exists()


def test_a_session_whose_terminal_write_fails_still_reports_its_exit_status() -> None:
    """The conftest path: a nested run whose target leaves json.dumps broken until the session ends."""
    code, run_id, output = _nested(f"{_TARGETS}::test_behaviour_target", behaviour="terminal_fault")
    assert code == 0, output
    assert "records=INVALID" in output and "exit=0" in output, output
    assert not (run_context_records.registry_root() / f"{run_id}.json").exists()
    record = run_context_records.read_record(_ROOT / "tmp" / "test-runs" / run_id / "run.json")
    assert record is not None and record["checkpoint"] == "start"


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
    assert run_context_records.read_entries(tmp_path / "phases.jsonl", "phases") == ([good], 3, "ok")
    assert run_context_records.read_entries(tmp_path / "missing.jsonl", "phases") == ([], 0, "missing")
    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(Path, "read_text", lambda *_arguments, **_options: (_ for _ in ()).throw(PermissionError("denied")))
        assert run_context_records.read_entries(tmp_path / "phases.jsonl", "phases") == ([], 0, "unreadable")
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
        # One deadline, five seconds from the detected root exit, shared by every member.
        gone = observer.wait_all_gone(own, 5.0)
        assert all(seconds is not None for seconds in gone.values()), f"members still running five seconds after the root exited: {gone}"

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
        assert all(seconds is not None for seconds in observer.wait_all_gone(others, 5.0).values())
    finally:
        observer.close(watched)
        for process in (survivor_process, planted_process):
            if process.poll() is None:
                process.kill()
                process.wait(timeout=60)


class _VirtualProcesses:
    """A kernel for the observer's waits: each handle is a process that exits at a known virtual second."""

    def __init__(self, exits_at: dict[int, float | None]) -> None:
        self.now, self.exits_at = 0.0, exits_at

    def clock(self) -> float:
        return self.now

    def WaitForSingleObject(self, handle: int, milliseconds: int) -> int:  # noqa: N802 - the native name
        exit_at = self.exits_at[handle]
        if exit_at is None:
            self.now += milliseconds / 1000
            return 0xFFFFFFFF
        if exit_at <= self.now:
            return 0
        if exit_at <= self.now + milliseconds / 1000:
            self.now = exit_at
            return 0
        self.now += milliseconds / 1000
        return 258


def test_the_cleanup_deadline_is_common_to_all_members() -> None:
    """Children exiting four and eight seconds after the root: the proof must fail, and it does."""
    kernel = _VirtualProcesses({1: 4.0, 2: 8.0, 3: None})
    first, second, unreadable = (observer.Watched(pid=pid, creation_time=1, handle=pid) for pid in (1, 2, 3))
    gone = observer.wait_all_gone([first, second], 5.0, api=kernel, clock=kernel.clock)
    assert gone == {1: 4.0, 2: None}, gone
    # Renewing five seconds per member would have accepted both; that reading is rejected.
    kernel = _VirtualProcesses({1: 4.0, 2: 8.0, 3: None})
    assert [observer.wait_until_gone(process, 5.0, api=kernel, clock=kernel.clock) for process in (first, second)] == [4.0, 4.0]
    # A wait that fails is never an exit, and a handle that could not be validated is never an exit.
    kernel = _VirtualProcesses({1: 1.0, 2: 1.0, 3: None})
    gone = observer.wait_all_gone([first, unreadable, observer.Watched(pid=4, creation_time=1, handle=None)], 5.0, api=kernel, clock=kernel.clock)
    assert gone == {1: 1.0, 3: None, 4: None}, gone


# --- R4: an overlap query that cannot observe a root says so.


@_windows
@pytest.mark.parametrize(
    ("identity", "listed_relation", "ended"),
    [
        (dict(opened=False, error=5), "unknown", 0),
        (dict(opened=True, creation_time=None, error=87), "unknown", 0),
        (dict(opened=True, creation_time=123456, live=None, error=5), "unknown", 0),
        (dict(opened=False, error=87), None, 1),
        (dict(opened=True, creation_time=999, live=True), None, 1),
        (dict(opened=True, creation_time=123456, live=False), None, 1),
    ],
    ids=["open-denied", "creation-query-failed", "liveness-denied", "no-such-process", "pid-reused", "terminated"],
)
def test_an_unobservable_root_is_unknown_and_an_ended_one_is_counted(
    monkeypatch: pytest.MonkeyPatch, identity: dict[str, object], listed_relation: str | None, ended: int
) -> None:
    entry = {"run_id": "20000101T000000-4242-abcdef", "mode": "active", "root": {"pid": 4242, "creation_time": 123456},
             "declared_agent": "claude", "worktree": "C:\\w"}
    monkeypatch.setattr(run_context_records, "registry_entries", lambda _exclude: ([entry], "ok"))
    fields = {"pid": 4242, "creation_time": None, "image": None, "error": None, "live": None, "opened": False, **identity}
    monkeypatch.setattr(run_context_windows, "process_identity", lambda _pid: run_context_windows.ProcessIdentity(**fields))
    listed, extra, registry, ended_count = run_context.other_runs("none")
    assert (extra, registry, ended_count) == (0, "ok", ended)
    assert [other["relation"] for other in listed] == ([listed_relation] if listed_relation else [])


def _start_record() -> dict[str, object]:
    """This session's own start record, as a shape for synthetic announcements. Read while the session is current."""
    start = run_context_records.read_record(_context().record_dir / "run.json")
    assert start is not None
    start.pop("schema")
    return start


def _announcement(run_id: str, start: dict[str, object]) -> dict[str, object]:
    pid = int(run_id.split("-")[1])
    return {**start, "run_id": run_id, "root": {**start["root"], "pid": pid}}  # type: ignore[dict-item]


class _ReadDenied:
    """Reading one existing file fails at the operating-system boundary; the reader itself is untouched.

    On Windows the file is held open with no sharing, so any other open is refused by the kernel.
    Elsewhere the process may be root, which no mode bit stops, so the open call is refused below
    `Path.read_text` for that one path.
    """

    def __init__(self, target: Path) -> None:
        self._target = target
        self._handle: int | None = None
        self._patch = pytest.MonkeyPatch()

    def __enter__(self) -> _ReadDenied:
        if sys.platform == "win32":
            import _winapi

            self._handle = _winapi.CreateFile(str(self._target), _winapi.GENERIC_READ, 0, 0, _winapi.OPEN_EXISTING, 0, 0)
        else:
            import io

            real_open, target = io.open, self._target

            def denied(file: object, *arguments: object, **options: object) -> object:
                if isinstance(file, (str, Path)) and Path(file) == target:
                    raise PermissionError(13, "synthetic read denial")
                return real_open(file, *arguments, **options)  # type: ignore[arg-type]

            self._patch.setattr(io, "open", denied)
        return self

    def __exit__(self, *_arguments: object) -> None:
        if self._handle is not None:
            import _winapi

            _winapi.CloseHandle(self._handle)
        self._patch.undo()


def _listing_denied(folder: Path) -> pytest.MonkeyPatch:
    """Listing one folder fails below the reader: `os.scandir` refuses that path and nothing else."""
    real_scandir = os.scandir

    def denied(path: object = ".", *arguments: object, **options: object) -> object:
        if isinstance(path, (str, Path)) and Path(path) == folder:
            raise PermissionError(13, "synthetic listing denial")
        return real_scandir(path, *arguments, **options)  # type: ignore[arg-type]

    patch = pytest.MonkeyPatch()
    patch.setattr(os, "scandir", denied)
    return patch


def test_a_registry_that_cannot_be_read_is_reported_not_hidden(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """R4: the actual reader, `other_runs`, the stored sample and parent discovery all carry the registry's state."""
    registry, start = tmp_path / "registry", _start_record()
    monkeypatch.setattr(run_context_records, "registry_root", lambda: registry)
    assert run_context_records.registry_entries("none") == ([], "absent")
    assert run_context.other_runs("none") == ([], 0, "absent", 0)
    registry.mkdir()
    assert run_context_records.registry_entries("none") == ([], "ok")
    first, second = "20000101T000000-4242-abcdef", "20000101T000000-4343-abcdef"
    for run_id in (first, second):
        run_context_records.write_record(registry / f"{run_id}.json", _announcement(run_id, start))
    assert sorted(entry["run_id"] for entry in run_context_records.registry_entries("none")[0]) == [first, second]
    # The folder itself cannot be listed: that is `unreadable`, never an empty registry.
    denied = _listing_denied(registry)
    try:
        assert run_context_records.registry_entries("none") == ([], "unreadable")
        assert run_context.other_runs("none") == ([], 0, "unreadable", 0)
        scratch = _scratch_context(tmp_path / "run")
        run_context.sample_run(scratch, "phase")
        samples, refused, how = run_context_records.read_entries(tmp_path / "run" / "samples.jsonl", "samples")
        assert (refused, how) == (0, "ok") and samples[-1]["registry"] == "unreadable" and samples[-1]["others"] == []
        monkeypatch.setattr(run_context_windows, "ancestors", lambda: ([], "root_reached"))
        assert run_context._discover_parent_run("none") == {  # noqa: SLF001
            "status": "UNKNOWN", "reason": "registry_unreadable", "method": "validated_process_ancestry"}
    finally:
        denied.undo()
    # One entry exists but cannot be read: the rest is listed and the answer is `partial`.
    with _ReadDenied(registry / f"{first}.json"):
        entries, state = run_context_records.registry_entries("none")
        assert state == "partial" and [entry["run_id"] for entry in entries] == [second]
        assert run_context.other_runs("none")[2] == "partial"
        assert run_context._discover_parent_run("none")["reason"] == "registry_partial"  # noqa: SLF001
    # An entry withdrawn between the listing and its read belongs to a run that just finished.
    real_load = run_context_records._load_record  # noqa: SLF001

    def withdrawn_meanwhile(source: Path) -> tuple[dict[str, object] | None, str]:
        if source.name == f"{first}.json":
            source.unlink()
        return real_load(source)

    monkeypatch.setattr(run_context_records, "_load_record", withdrawn_meanwhile)
    entries, state = run_context_records.registry_entries("none")
    assert state == "ok" and [entry["run_id"] for entry in entries] == [second]
    monkeypatch.setattr(run_context_records, "_load_record", real_load)
    # A malformed entry is refused and skipped, as before; it is not a read failure.
    (registry / "zzz-malformed.json").write_text("{not json", encoding="utf-8")
    entries, state = run_context_records.registry_entries("none")
    assert state == "ok" and [entry["run_id"] for entry in entries] == [second]


def test_a_registry_beyond_its_ceiling_is_partial_and_never_pruned(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Codex's registry-ceiling disposition: the cap stays, partial stays visible, absence is not guessed, nothing is deleted."""
    registry, start = tmp_path / "registry", _start_record()
    registry.mkdir()
    monkeypatch.setattr(run_context_records, "registry_root", lambda: registry)
    ceiling = run_context_records.MAX_REGISTRY_ENTRIES
    assert ceiling == 512
    ids = [f"20000101T{index:06d}-{index + 1}-abcdef" for index in range(ceiling + 1)]
    for run_id in ids:
        # A fixed creation time, so the parent match below works where the real root has none (no native support).
        announcement = _announcement(run_id, start)
        announcement["root"] = {**announcement["root"], "creation_time": 123456}  # type: ignore[dict-item]
        run_context_records.write_record(registry / f"{run_id}.json", announcement)
    before = sorted(path.name for path in registry.iterdir())
    entries, state = run_context_records.registry_entries("none")
    assert state == "partial" and len(entries) == ceiling and ids[0] not in {entry["run_id"] for entry in entries}
    assert run_context.other_runs("none")[2] == "partial"
    scratch = _scratch_context(tmp_path / "run")
    run_context.sample_run(scratch, "phase")
    samples = run_context_records.read_entries(tmp_path / "run" / "samples.jsonl", "samples")[0]
    assert samples[-1]["registry"] == "partial" and samples[-1]["others_not_listed"] >= 0
    # An unmatched parent is UNKNOWN; a positively validated parent among the observed entries is still found.
    monkeypatch.setattr(run_context_windows, "ancestors", lambda: ([], "root_reached"))
    assert run_context._discover_parent_run("none") == {  # noqa: SLF001
        "status": "UNKNOWN", "reason": "registry_partial", "method": "validated_process_ancestry"}
    newest = run_context_records.read_record(registry / f"{ids[-1]}.json")
    assert newest is not None
    live = run_context_windows.ProcessIdentity(pid=int(newest["root"]["pid"]), creation_time=123456,  # type: ignore[index]
                                               image=None, error=None, live=True, opened=True)
    monkeypatch.setattr(run_context_windows, "ancestors", lambda: ([live], "root_reached"))
    assert newest["mode"] == "active"
    assert run_context._discover_parent_run("none") == {  # noqa: SLF001
        "status": "parent", "run_id": ids[-1], "method": "validated_process_ancestry"}
    assert sorted(path.name for path in registry.iterdir()) == before, "no registry entry was deleted"


class _UnlinkDenied:
    """Removing one file fails at the operating-system boundary; the removal helper is untouched.

    On Windows a file that is open through the C runtime cannot be deleted, so holding it open is a
    genuine kernel refusal. Elsewhere an open file can be unlinked, so `os.unlink` is refused for
    that one path below `Path.unlink`.
    """

    def __init__(self, target: Path) -> None:
        self._target = target
        self._handle: object = None
        self._patch = pytest.MonkeyPatch()

    def __enter__(self) -> _UnlinkDenied:
        if sys.platform == "win32":
            self._handle = open(self._target, "rb")  # noqa: SIM115
        else:
            real_unlink, target = os.unlink, self._target

            def denied(path: object, *arguments: object, **options: object) -> None:
                if isinstance(path, (str, Path)) and Path(path) == target:
                    raise PermissionError(13, "synthetic unlink denial")
                real_unlink(path, *arguments, **options)  # type: ignore[arg-type]

            self._patch.setattr(os, "unlink", denied)
        return self

    def __exit__(self, *_arguments: object) -> None:
        if self._handle is not None:
            self._handle.close()  # type: ignore[attr-defined]
        self._patch.undo()


def test_the_stored_terminal_record_states_whether_the_announcement_was_withdrawn(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """R2: actual finish_run, writer, reader and removal helper; the stored and returned states agree."""
    registry, start = tmp_path / "registry", _start_record()
    registry.mkdir()
    monkeypatch.setattr(run_context_records, "registry_root", lambda: registry)
    scratch, denied = _scratch_context(tmp_path / "clean"), _scratch_context(tmp_path / "denied")
    # Positive: the announcement is withdrawn before the record is written, and the record says so.
    run_context_records.write_record(registry / f"{scratch.run_id}.json", _announcement(scratch.run_id, start))
    run_context.record_phase(scratch, _report(when="call"))
    monkeypatch.setattr(run_context, "_current", scratch)
    final = run_context.finish_run(scratch, 0)
    stored = run_context_records.read_record(tmp_path / "clean" / "run.json")
    assert stored is not None and stored["checkpoint"] == "terminal"
    for record in (final, stored):
        assert (record["exit_status"], record["completeness"], record["registry_withdrawal"], record["recording_errors"]) == (0, "COMPLETE", "done", 0)
    assert not (registry / f"{scratch.run_id}.json").exists() and run_context.current() is None
    # The unlink is denied by the operating system: the entry remains, and both the stored record and
    # the returned one say INVALID with the withdrawal failed; pytest's exit status is kept.
    announcement = registry / f"{denied.run_id}.json"
    run_context_records.write_record(announcement, _announcement(denied.run_id, start))
    run_context.record_phase(denied, _report(when="call"))
    monkeypatch.setattr(run_context, "_current", denied)
    with _UnlinkDenied(announcement):
        final = run_context.finish_run(denied, 7)
    assert announcement.exists()
    stored = run_context_records.read_record(tmp_path / "denied" / "run.json")
    assert stored is not None and stored["checkpoint"] == "terminal" and stored["streams"]["phases"] == 1
    for record in (final, stored):
        assert (record["exit_status"], record["completeness"], record["registry_withdrawal"]) == (7, "INVALID", "failed")
        assert record["recording_errors"] == 1
    assert run_context.current() is None
    # The removal is the ordinary helper: once the denial is lifted it withdraws the entry.
    run_context_records.remove_own_registry_entry(denied.run_id)
    assert not announcement.exists()


def test_a_refused_terminal_record_is_stored_as_invalid_when_any_record_can_be(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A full terminal record refused by the field table never leaves a COMPLETE claim behind."""
    registry, start = tmp_path / "registry", _start_record()
    registry.mkdir()
    monkeypatch.setattr(run_context_records, "registry_root", lambda: registry)
    scratch, another = _scratch_context(tmp_path / "run"), _scratch_context(tmp_path / "another")
    # The refused value sits in the terminal facts: the minimal INVALID record is stored instead.
    run_context_records.write_record(registry / f"{scratch.run_id}.json", _announcement(scratch.run_id, start))
    run_context.record_phase(scratch, _report(when="call"))
    scratch.native["enrolled"] = True
    monkeypatch.setattr(run_context_windows, "accounting", lambda: {"ok": True, "total_processes": "many"})
    monkeypatch.setattr(run_context_windows, "members", lambda: ([], None))
    monkeypatch.setattr(run_context, "_current", scratch)
    final = run_context.finish_run(scratch, 1)
    stored = run_context_records.read_record(tmp_path / "run" / "run.json")
    assert stored is not None and stored["checkpoint"] == "terminal" and "streams" not in stored
    for record in (final, stored):
        assert (record["completeness"], record["terminal_failure"], record["exit_status"], record["registry_withdrawal"]) == (
            "INVALID", "record.accounting.total_processes", 1, "done")
    assert not (registry / f"{scratch.run_id}.json").exists() and run_context.current() is None
    # The refused value sits in the run's own facts, shared by both attempts: nothing is stored, and
    # the returned result still says INVALID with the entry withdrawn.
    run_context_records.write_record(registry / f"{another.run_id}.json", _announcement(another.run_id, start))
    another.facts["protection"] = "not-a-level"
    monkeypatch.setattr(run_context, "_current", another)
    final = run_context.finish_run(another, 0)
    assert run_context_records.read_record(tmp_path / "another" / "run.json") is None
    assert (final["completeness"], final["terminal_failure"], final["registry_withdrawal"]) == ("INVALID", "record.protection", "done")
    assert not (registry / f"{another.run_id}.json").exists() and run_context.current() is None


def test_the_context_and_the_observer_never_open_a_job_or_start_a_thread() -> None:
    for module in (run_context, run_context_guard, run_context_records, run_context_windows, observer):
        source = Path(module.__file__).read_text(encoding="utf-8")
        found = [name for name in ("OpenJobObject", "import threading", "from threading", "Timer(") if name in source]
        assert found == [], f"{module.__name__} must not use {found}"
