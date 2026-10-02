"""Boundary proofs for the pytest run context: selection, native failures and the record policy.

Selection probes run real nested pytest sessions against a synthetic target in
`test_run_context.py`. The target carries a marker only when a probe asks for one through the
environment, so no live service is involved and an operator's own marker runs never select it.
Native failures are injected over the real kernel32 binding, one call at a time. The collision
proof runs in its own interpreter against a job that the proof itself creates.
"""

from __future__ import annotations

import ctypes
import json
import os
import secrets
import subprocess
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.testing import run_context, run_context_records, run_context_windows

_ROOT = Path(__file__).resolve().parents[3]
_TARGET = "tests/unit/tools/test_run_context.py::test_probe_sentinel"
_APPROVED = run_context.APPROVED_DEFAULT_MARKER_EXPRESSION
_windows = pytest.mark.skipif(sys.platform != "win32", reason="native job ownership is Windows-only")


def _context(request: pytest.FixtureRequest) -> run_context.RunContext:
    for value in request.config.stash._storage.values():  # noqa: SLF001 - the stash key is private to conftest
        if isinstance(value, run_context.RunContext):
            return value
    raise AssertionError("the root conftest did not start a run context")


def _probe(tmp_path: Path, arguments: tuple[str, ...], mark: str) -> tuple[int, dict[str, object] | None, str]:
    """Run the synthetic target in a real nested pytest; return exit code, what it reported, and output."""
    sentinel = tmp_path / "sentinel.json"
    environment = {**os.environ, "OPTIMUS_TEST_RUN_CONTEXT_PROBE_SENTINEL": str(sentinel)}
    environment.pop("OPTIMUS_TEST_RUN_CONTEXT_PROBE_MARK", None)
    if mark:
        environment["OPTIMUS_TEST_RUN_CONTEXT_PROBE_MARK"] = mark
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", _TARGET, *arguments],
        cwd=_ROOT, env=environment, capture_output=True, text=True, timeout=300, check=False,
    )
    reported = json.loads(sentinel.read_text(encoding="utf-8")) if sentinel.is_file() else None
    return completed.returncode, reported, completed.stdout + completed.stderr


def _alternate_config(tmp_path: Path, expression: str) -> tuple[str, ...]:
    config = tmp_path / "alternate.ini"
    config.write_text(
        f'[pytest]\npythonpath = src .\nasyncio_mode = auto\naddopts = --import-mode=importlib -m "{expression}"\n',
        encoding="utf-8",
    )
    return ("-c", str(config), "--rootdir", str(_ROOT))


def test_the_frozen_default_expression_equals_the_repository_configuration() -> None:
    addopts = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]["addopts"]
    assert addopts[addopts.index("-m") + 1] == _APPROVED
    assert addopts.count("-m") == 1


# --- A1: only the approved default selection, under the repository's own configuration, is ACTIVE.

_PASSIVE_PROBES = [
    pytest.param(("-o", "addopts=-m e2e"), "e2e", "overridden_addopts", id="overridden-addopts-selects-e2e"),
    pytest.param(("-o", "addopts=-m e2e", "-m", _APPROVED), "", "overridden_addopts", id="mixed-override-then-default"),
    pytest.param(("-m", "e2e"), "e2e", "non_default_selection", id="explicit-non-default"),
    pytest.param(("-m", "not e2e"), "", "non_default_selection", id="unknown-partial-expression"),
    pytest.param(("--test-run-context=passive",), "", "requested", id="requested-passive"),
]


@pytest.mark.parametrize(("arguments", "mark", "reason"), _PASSIVE_PROBES)
def test_a_selection_that_is_not_the_approved_default_runs_passive(
    tmp_path: Path, arguments: tuple[str, ...], mark: str, reason: str
) -> None:
    code, reported, output = _probe(tmp_path, arguments, mark)
    assert code == 0 and reported is not None, output
    assert (reported["mode"], reported["reason"]) == ("passive", reason), output
    assert reported["guard"] == "not_installed" and reported["owns_job"] is False, reported
    assert reported["real_adapter_replaced"] is False and reported["protected_roots"] == 0, reported
    assert f"mode=passive reason={reason}" in output and "guard=not_installed" in output, output


@pytest.mark.parametrize(("expression", "mark"), [(_APPROVED, ""), ("e2e", "e2e")], ids=["same-default", "selects-e2e"])
def test_another_config_file_runs_passive_whatever_it_selects(tmp_path: Path, expression: str, mark: str) -> None:
    code, reported, output = _probe(tmp_path, _alternate_config(tmp_path, expression), mark)
    assert code == 0 and reported is not None, output
    assert (reported["mode"], reported["reason"]) == ("passive", "foreign_configuration"), output
    assert reported["guard"] == "not_installed" and reported["owns_job"] is False, reported
    assert reported["real_adapter_replaced"] is False, reported


def test_the_default_written_out_explicitly_stays_active(tmp_path: Path) -> None:
    code, reported, output = _probe(tmp_path, ("-m", _APPROVED), "")
    assert code == 0 and reported is not None, output
    assert (reported["mode"], reported["reason"]) == ("active", "default_selection"), output
    if sys.platform == "win32":
        assert reported["owns_job"] is True and reported["guard"] in {"pytest_process_guard", "main5_guard_present"}


def test_a_collection_only_run_is_passive_and_executes_nothing(tmp_path: Path) -> None:
    code, reported, output = _probe(tmp_path, ("--collect-only",), "")
    assert code == 0 and reported is None, output
    assert "mode=passive reason=collection_only" in output and "guard=not_installed" in output, output


def _config(**changes: object) -> SimpleNamespace:
    option = {"markexpr": _APPROVED, "collectonly": False, "test_run_context": "auto", "override_ini": None}
    paths = {"inipath": _ROOT / "pyproject.toml", "rootpath": _ROOT}
    for name, value in changes.items():
        (paths if name in paths else option)[name] = value
    return SimpleNamespace(option=SimpleNamespace(**option), **paths)


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        (_config(), ("active", "default_selection")),
        (_config(markexpr="e2e"), ("passive", "non_default_selection")),
        (_config(markexpr=""), ("passive", "non_default_selection")),
        (_config(markexpr=_APPROVED + " and not slow"), ("passive", "non_default_selection")),
        (_config(markexpr="e2e", override_ini=["addopts=-m e2e"]), ("passive", "overridden_addopts")),
        (_config(override_ini=["addopts=-m e2e"]), ("passive", "overridden_addopts")),
        (_config(override_ini=["log_level=INFO"]), ("active", "default_selection")),
        (_config(inipath=_ROOT / "tests" / "pytest.ini"), ("passive", "foreign_configuration")),
        (_config(inipath=None), ("passive", "foreign_configuration")),
        (_config(rootpath=_ROOT / "tests"), ("passive", "foreign_configuration")),
        (_config(collectonly=True), ("passive", "collection_only")),
        (_config(test_run_context="passive"), ("passive", "requested")),
    ],
)
def test_the_classifier_never_compares_a_session_with_its_own_configuration(
    config: SimpleNamespace, expected: tuple[str, str]
) -> None:
    assert run_context.classify(config) == expected


@_windows
def test_an_active_interpreter_refuses_a_later_passive_session(request: pytest.FixtureRequest) -> None:
    context = _context(request)
    assert context.mode == "active" and run_context_windows.owner() is not None
    before = run_context._sessions_started  # noqa: SLF001
    with pytest.raises(pytest.UsageError, match="separate interpreter"):
        run_context.start_run(_config(markexpr="e2e"))
    assert run_context._sessions_started == before  # noqa: SLF001 - refused before anything was recorded


# --- A2: a failed native query is UNKNOWN, never "no parent"; a name collision changes nothing.


class _Faulty:
    """The real kernel32 binding with one or more calls replaced."""

    def __init__(self, real: object, **replaced: object) -> None:
        self._real, self._replaced = real, replaced

    def __getattr__(self, name: str) -> object:
        return self._replaced[name] if name in self._replaced else getattr(self._real, name)


def _fail(code: int, result: int = 0):  # noqa: ANN202
    def call(*_arguments: object) -> int:
        ctypes.set_last_error(code)
        return result

    return call


def _inject(monkeypatch: pytest.MonkeyPatch, **replaced: object) -> None:
    monkeypatch.setattr(run_context_windows, "_api", _Faulty(run_context_windows._kernel32(), **replaced))  # noqa: SLF001


def _parent_status() -> dict[str, object]:
    return run_context._discover_parent_run("20000101T000000-1-000000")  # noqa: SLF001


@_windows
def test_real_ancestry_lists_only_running_processes_created_before_their_child() -> None:
    chain, stopped = run_context_windows.ancestors()
    assert chain, stopped
    younger = run_context_windows.current_identity()
    for ancestor in chain:
        assert ancestor.live is True and ancestor.creation_time is not None and ancestor.error is None
        assert ancestor.creation_time <= younger.creation_time
        younger = ancestor
    assert stopped in {"root_reached", "ancestor_exited", "access_denied"}, stopped


@_windows
@pytest.mark.parametrize(
    ("replaced", "stopped"),
    [
        ({"CreateToolhelp32Snapshot": _fail(8, ctypes.c_void_p(-1).value)}, "snapshot_failed"),
        ({"Process32FirstW": _fail(5)}, "snapshot_incomplete"),
        ({"Process32NextW": _fail(5)}, "snapshot_incomplete"),
        ({"OpenProcess": _fail(5)}, "access_denied"),
        ({"OpenProcess": _fail(31)}, "identity_failed"),
        ({"GetExitCodeProcess": _fail(31)}, "identity_failed"),
    ],
    ids=["snapshot", "first-entry", "iteration", "open-denied", "open-error", "liveness"],
)
def test_a_failed_native_query_makes_the_parent_unknown(
    monkeypatch: pytest.MonkeyPatch, replaced: dict[str, object], stopped: str
) -> None:
    _inject(monkeypatch, **replaced)
    assert run_context_windows.ancestors() == ([], stopped)
    assert _parent_status() == {"status": "UNKNOWN", "reason": stopped, "method": "validated_process_ancestry"}


@_windows
def test_a_listing_cut_short_after_this_process_was_listed_is_still_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """The partial list holds this process and its parent, so only the error code shows it is partial."""
    real = run_context_windows._kernel32()  # noqa: SLF001
    listed_own = []

    def next_entry(snapshot: object, entry: object) -> int:
        if listed_own:
            ctypes.set_last_error(5)
            return 0
        more = real.Process32NextW(snapshot, entry)
        if more and entry._obj.th32ProcessID == os.getpid():  # noqa: SLF001 - the entry behind ctypes.byref
            listed_own.append(True)
        return more

    _inject(monkeypatch, Process32NextW=next_entry)
    assert run_context_windows.ancestors() == ([], "snapshot_incomplete")
    assert listed_own == [True]
    assert _parent_status()["status"] == "UNKNOWN"


@_windows
def test_a_failed_creation_time_read_is_not_taken_for_an_exited_parent(monkeypatch: pytest.MonkeyPatch) -> None:
    real = run_context_windows._kernel32()  # noqa: SLF001
    own = real.GetCurrentProcess()

    def times(handle: object, *rest: object) -> int:
        if handle == own:
            return real.GetProcessTimes(handle, *rest)
        ctypes.set_last_error(31)
        return 0

    _inject(monkeypatch, GetProcessTimes=times)
    assert run_context_windows.ancestors() == ([], "identity_failed")
    assert _parent_status()["status"] == "UNKNOWN"


@_windows
@pytest.mark.parametrize("how", ["no_such_process", "exit_code_read"])
def test_an_exited_ancestor_ends_the_chain_without_proving_absence(monkeypatch: pytest.MonkeyPatch, how: str) -> None:
    if how == "no_such_process":
        _inject(monkeypatch, OpenProcess=_fail(87))
    else:
        def exited(_handle: object, code: object) -> int:
            code._obj.value = 0  # noqa: SLF001 - the DWORD behind ctypes.byref
            return 1

        _inject(monkeypatch, GetExitCodeProcess=exited)
    assert run_context_windows.ancestors() == ([], "ancestor_exited")
    assert _parent_status() == {"status": "not_found", "reason": "ancestor_exited", "method": "validated_process_ancestry"}


_COLLISION_SCRIPT = '''
import ctypes, json, sys
from ctypes import wintypes
from tools.testing import run_context_windows as native

run_id = sys.argv[1]
api = native._kernel32()
existing = api.CreateJobObjectW(None, "optimus-test-run-" + run_id)
owner = native.enroll(run_id)
member = wintypes.BOOL()
asked = api.IsProcessInJob(api.GetCurrentProcess(), existing, ctypes.byref(member))
extended, _, _ = native._structures()
limits, returned = extended(), wintypes.DWORD()
read = api.QueryInformationJobObject(existing, 9, ctypes.byref(limits), ctypes.sizeof(limits), ctypes.byref(returned))
print(json.dumps({
    "existing_created": bool(existing), "valid": owner.valid, "handle": owner.handle, "facts": owner.facts,
    "membership_read": bool(asked), "member_of_existing": bool(member.value),
    "limits_read": bool(read), "existing_limit_flags": int(limits.Basic.LimitFlags),
    "second_call_same_owner": native.enroll(run_id) is owner,
}))
'''


@_windows
def test_a_job_name_that_already_exists_is_rejected_without_changing_that_job(tmp_path: Path) -> None:
    script = tmp_path / "collision.py"
    script.write_text(_COLLISION_SCRIPT, encoding="utf-8")
    run_id = f"20000101T000000-{os.getpid()}-{secrets.token_hex(3)}"
    completed = subprocess.run(
        [sys.executable, str(script), run_id], cwd=_ROOT, env={**os.environ, "PYTHONPATH": str(_ROOT)},
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    seen = json.loads(completed.stdout)
    assert seen["existing_created"] is True
    assert (seen["valid"], seen["handle"]) == (False, None)
    assert seen["facts"] == {"enrolled": False, "name_already_existed": True, "created": False, "create_error": 183}
    assert seen["membership_read"] is True and seen["member_of_existing"] is False
    assert seen["limits_read"] is True and seen["existing_limit_flags"] == 0
    assert seen["second_call_same_owner"] is True


def test_a_failed_enrolment_is_never_summarised_as_a_job(request: pytest.FixtureRequest) -> None:
    real = _context(request)
    failed = run_context.RunContext(
        run_id=real.run_id, mode="active", reason="default_selection", record_dir=real.record_dir,
        started_utc=real.started_utc, worktree=real.worktree, parent_run={"status": "UNKNOWN", "reason": "snapshot_failed"},
        native={"supported": True, "attempted": True, "valid": False, "enrolled": False, "name_already_existed": True},
    )
    line = run_context.summary_line(failed, None)
    assert "native=INVALID" in line and "job=" not in line and "processes=" not in line
    assert "parent=UNKNOWN" in line


# --- A3: the writer, the reader and the summary enforce one bounded, typed field table.


def _valid(request: pytest.FixtureRequest) -> dict[str, object]:
    record = run_context_records.read_record(_context(request).record_dir / "run.json")
    assert record is not None
    record.pop("schema")
    return record


def _sensitive(kind: str) -> str:
    # Built at run time so that no secret-shaped literal sits in this file.
    return {"assignment": "token" + "=" + "hunter2" * 2, "labelled": "password" + ": " + "hunter2" * 2}[kind]


_BREAKERS = {
    "extra-top-level-field": lambda record: record.update(note="anything"),
    "extra-nested-field": lambda record: record["root"].update(command_line="python -m pytest"),
    "extra-deep-field": lambda record: record["native"].update(detail={"argv": ["x"]}),
    "schema-supplied": lambda record: record.update(schema="test-run-context-v1"),
    "schema-replaced": lambda record: record.update(schema="something-else"),
    "run-id-control-characters": lambda record: record.update(run_id="20000101T000000-1-00000\x1b"),
    "run-id-free-text": lambda record: record.update(run_id="run with spaces"),
    "run-id-names-another-process": lambda record: record.update(run_id="20000101T000000-1-000000"),
    "parent-run-id-free-text": lambda record: record.update(parent_run={"status": "parent", "run_id": "x\ny"}),
    "branch-control-characters": lambda record: record.update(branch="agent/a/b\x00c"),
    "branch-sensitive": lambda record: record.update(branch=_sensitive("assignment")),
    "worktree-sensitive": lambda record: record.update(worktree="C:\\w\\" + _sensitive("labelled")),
    "worktree-control-characters": lambda record: record.update(worktree="C:\\w\nrun=forged"),
    "image-path": lambda record: record["root"].update(image="C:\\Users\\someone\\python.exe"),
    "number-as-text": lambda record: record["root"].update(pid="1234"),
    "flag-as-number": lambda record: record["native"].update(supported=1),
    "list-for-a-table": lambda record: record.update(native=["enrolled"]),
    "unknown-mode": lambda record: record.update(mode="observer"),
}


@pytest.mark.parametrize("name", sorted(_BREAKERS))
def test_the_writer_refuses_a_record_outside_the_field_table(request: pytest.FixtureRequest, tmp_path: Path, name: str) -> None:
    record = _valid(request)
    run_context_records.write_record(tmp_path / "control.json", record)
    assert run_context_records.read_record(tmp_path / "control.json") is not None
    _BREAKERS[name](record)
    with pytest.raises(ValueError, match=run_context_records.REJECTED) as refusal:
        run_context_records.write_record(tmp_path / "refused.json", record)
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["control.json"]
    assert "hunter2" not in str(refusal.value) and "forged" not in str(refusal.value)


@pytest.mark.parametrize("name", sorted(set(_BREAKERS) - {"schema-supplied", "branch-sensitive", "worktree-sensitive"}))
def test_the_reader_refuses_a_stored_record_outside_the_field_table(request: pytest.FixtureRequest, tmp_path: Path, name: str) -> None:
    record = _valid(request)
    _BREAKERS[name](record)
    stored = tmp_path / "stored.json"
    stored.write_text(json.dumps({"schema": run_context_records.SCHEMA, **record}), encoding="utf-8")
    assert run_context_records.read_record(stored) is None


def test_checkout_text_that_is_not_fit_to_persist_is_withheld_by_name(request: pytest.FixtureRequest, tmp_path: Path) -> None:
    real = _context(request)
    odd = run_context.RunContext(
        run_id=real.run_id, mode=real.mode, reason=real.reason, record_dir=tmp_path, started_utc=real.started_utc,
        worktree="C:\\w\\" + _sensitive("labelled"), branch="agent/" + _sensitive("assignment") + "/x", head="not-a-commit",
        declared_agent=_sensitive("assignment"), root=real.root, parent_run=real.parent_run, native=real.native,
        guard_mode=real.guard_mode,
    )
    payload = run_context._payload(odd, checkpoint="start")  # noqa: SLF001
    assert [payload[name] for name in ("worktree", "branch", "head", "declared_agent")] == [None] * 4
    assert payload["withheld"] == ["branch", "declared_agent", "head", "worktree"]
    run_context_records.write_record(tmp_path / "run.json", payload)
    text = (tmp_path / "run.json").read_text(encoding="utf-8")
    assert "hunter2" not in text and "not-a-commit" not in text
    assert "hunter2" not in run_context.summary_line(odd, None)


def test_a_forged_registry_entry_never_reaches_a_record_or_the_terminal(request: pytest.FixtureRequest) -> None:
    """Two planted entries claim this process as their root: one malformed, one filed under another name."""
    context = _context(request)
    own = run_context_records.read_record(run_context_records.registry_root() / f"{context.run_id}.json")
    assert own is not None
    registry = run_context_records.registry_root()
    marker = secrets.token_hex(4)
    malformed = {**own, "run_id": f"forged-{marker} token=hunter2hunter2\x1b[31m parent=forged"}
    misfiled = {**own, "run_id": f"20000101T000000-{os.getpid()}-{marker[:6]}"}
    planted = [registry / f"zzz-{marker}-malformed.json", registry / f"zzz-{marker}-misfiled.json"]
    try:
        planted[0].write_text(json.dumps(malformed), encoding="utf-8")
        planted[1].write_text(json.dumps(misfiled), encoding="utf-8")
        accepted = [entry["run_id"] for entry in run_context_records.registry_entries("none")]
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", "tests/unit/tools/test_run_context.py::test_probe_noop"],
            cwd=_ROOT, capture_output=True, text=True, timeout=300, check=False,
        )
    finally:
        for path in planted:
            path.unlink(missing_ok=True)
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, output
    assert malformed["run_id"] not in accepted and misfiled["run_id"] not in accepted and context.run_id in accepted
    assert "hunter2" not in output and "forged" not in output and misfiled["run_id"] not in output
    child_run = output.split("run=", 1)[1].split(" ", 1)[0]
    child = run_context_records.read_record(_ROOT / "tmp" / "test-runs" / child_run / "run.json")
    assert child is not None
    if sys.platform == "win32":
        assert child["parent_run"] == {"status": "parent", "run_id": context.run_id, "method": "validated_process_ancestry"}
        assert f"parent={context.run_id}" in output
