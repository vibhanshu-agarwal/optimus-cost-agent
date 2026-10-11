"""Plan 11.30 Task 4: reuse of an identical current measurement inside one test session.

The key is the exact measured source and identity files, entry, options, depth, platform, interpreter and
environment. A hit returns a copy of the named earlier data: never a new execution, an independent repeat
or a minted execution context. A failed measurement is never stored, and reuse never crosses a thread or a
session. Production paths never reuse: only test helpers opt in, and the run's terminal record names every hit.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from tools.plan1126_runtime_audit import measurement
from tools.plan1126_runtime_audit.current_envelope import MeasurementPlan, default_measurement_plan
from tools.plan1126_runtime_audit.source import ExecutingSourceMismatch, SourceTree, source_fingerprint

ROOT = Path(__file__).resolve().parents[4]
_ENTRY = "identity.echo_bound_modules"
_THIS = "tests/unit/tools/plan1126_runtime_audit/test_measurement_reuse.py"
_REUSE_PROBE = f"{_THIS}::test_measurement_reuse_probe"


def _plan(**options: object) -> MeasurementPlan:
    return default_measurement_plan(repository_root=ROOT, entries=(_ENTRY,), options=options)[0]


def _identity(plan: MeasurementPlan, **changes: object) -> str:
    arguments: dict[str, object] = {
        "source": plan.source, "spec": plan.spec, "entry": plan.entry, "options": plan.options,
        "repository_root": ROOT, "depth": "full",
    }
    arguments.update(changes)
    return measurement.measurement_identity(**arguments)  # type: ignore[arg-type]


def _measure(store: measurement.MeasurementReuse, plan: MeasurementPlan, requester: str, depth: str = "full"):
    return store.measure(
        source=plan.source, spec=plan.spec, entry=plan.entry, options=plan.options,
        repository_root=ROOT, depth=depth, requester=requester,
    )


def _counting(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    real = measurement.run_fresh_measurement
    calls: list[str] = []

    def counting(**kwargs):
        calls.append(kwargs["entry"])
        return real(**kwargs)

    monkeypatch.setattr(measurement, "run_fresh_measurement", counting)
    return calls


def test_the_reuse_key_is_the_exact_source_shape_options_depth_platform_and_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The key is computed without running anything, so the H5 entry (which measures a source tree) is free here.
    plan = default_measurement_plan(repository_root=ROOT, entries=("h5.shutdown_schedule",), options={"repeats": 1})[0]
    key = _identity(plan)
    assert _identity(plan) == key
    files = {path: plan.source.read_text(path) for path in plan.source.paths()}
    files[sorted(files)[0]] += "\n"
    edited = SourceTree(files)
    assert _identity(plan, source=edited, spec=replace(plan.spec, source_fingerprint=source_fingerprint(edited, edited.paths()))) != key
    assert _identity(plan, entry="h9.connection_health") != key
    assert _identity(plan, options={"repeats": 2}) != key
    assert _identity(plan, depth="quick") != key
    monkeypatch.setattr(measurement, "_execution_platform", lambda: ("another-platform", sys.executable, sys.version))
    assert _identity(plan) != key
    monkeypatch.undo()
    monkeypatch.setenv("OPTIMUS_P1130_REUSE_KEY_PROBE", "1")
    changed = _identity(plan)
    assert changed != key  # the environment the child inherits
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/another.py::test_other (call)")
    assert _identity(plan) == changed  # pytest's per-test name is not part of what is measured


def test_the_reuse_key_is_a_digest_that_writes_nothing_and_holds_no_environment_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plan 9.96: measurement_identity serializes its material (which includes the inherited environment) only to
    hash it. The result is the digest alone: no environment value survives in it, and nothing is written."""
    marker = "p1130-reuse-key-marker-value"
    monkeypatch.setenv("OPTIMUS_P1130_REUSE_KEY_SECRET", marker)
    monkeypatch.chdir(tmp_path)
    before = {path.name for path in tmp_path.iterdir()}
    key = _identity(_plan())
    assert re.fullmatch(r"[0-9a-f]{64}", key)
    assert marker not in key
    assert {path.name for path in tmp_path.iterdir()} == before, "the reuse key wrote something"


def test_an_identical_measurement_is_reused_as_a_copy_of_the_named_earlier_data(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _counting(monkeypatch)
    store = measurement.MeasurementReuse()
    plan = _plan()
    binding, result, earlier = _measure(store, plan, "tests/a.py::first")
    assert earlier is None and calls == [_ENTRY]
    result["planted"] = True  # the caller's own copy
    # From here a hit may neither execute nor mint an execution context: both refuse.
    refused: list[str] = []

    def refuse(*_args: object, _name: str = "", **_kwargs: object) -> None:
        refused.append(_name)
        raise AssertionError(f"a reuse executed {_name}")

    monkeypatch.setattr(measurement, "run_fresh_measurement", lambda **kwargs: refuse(_name="run_fresh_measurement"))
    monkeypatch.setattr(measurement, "establish_verified_execution", lambda **kwargs: refuse(_name="establish_verified_execution"))
    again_binding, again, earlier = _measure(store, plan, "tests/a.py::second")
    assert earlier == "tests/a.py::first" and refused == []
    assert again_binding.to_dict() == binding.to_dict()
    assert "planted" not in again
    again["planted"] = True  # nor can a hit's own copy reach the next hit
    _, third, earlier = _measure(store, plan, "tests/a.py::third")
    assert earlier == "tests/a.py::first" and "planted" not in third and refused == []
    monkeypatch.undo()  # the real measurement path again
    calls = _counting(monkeypatch)
    _, _, earlier = _measure(store, plan, "tests/a.py::fourth", depth="quick")
    assert earlier is None and calls == [_ENTRY]  # another depth is another measurement


def test_a_failed_measurement_is_never_stored(monkeypatch: pytest.MonkeyPatch) -> None:
    real = measurement.run_fresh_measurement
    attempts: list[str] = []

    def failing_once(**kwargs):
        attempts.append(kwargs["entry"])
        if len(attempts) == 1:
            raise ExecutingSourceMismatch("planted child failure")
        return real(**kwargs)

    monkeypatch.setattr(measurement, "run_fresh_measurement", failing_once)
    store = measurement.MeasurementReuse()
    plan = _plan()
    with pytest.raises(ExecutingSourceMismatch, match="planted child failure"):
        _measure(store, plan, "tests/a.py::first")
    _, _, earlier = _measure(store, plan, "tests/a.py::second")
    assert earlier is None and len(attempts) == 2


def test_reuse_never_crosses_a_thread_or_a_session(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _counting(monkeypatch)
    plan = _plan()
    # This control works on its own thread-local stores: the running session's store (which the test
    # helpers fill) must be left exactly as it is, never cleared by a control.
    running = measurement.session_measurement_reuse()
    kept = dict(running._taken)  # noqa: SLF001
    # A fresh store of the production object's own type: its thread-locality is what is under test.
    monkeypatch.setattr(measurement, "_reuse", type(measurement._reuse)())  # noqa: SLF001
    _measure(measurement.session_measurement_reuse(), plan, "tests/a.py::first")
    _, _, earlier = _measure(measurement.session_measurement_reuse(), plan, "tests/a.py::second")
    assert earlier == "tests/a.py::first" and len(calls) == 1
    seen: list[object] = []
    worker = threading.Thread(target=lambda: seen.append(_measure(measurement.session_measurement_reuse(), plan, "tests/a.py::thread")[2]))
    worker.start()
    worker.join()
    assert seen == [None] and len(calls) == 2
    measurement.clear_measurement_reuse()  # the session ended
    _, _, earlier = _measure(measurement.session_measurement_reuse(), plan, "tests/a.py::later")
    assert earlier is None and len(calls) == 3
    assert running._taken == kept  # noqa: SLF001


# --- Codex C-M2: a measurement is reused only against the same installed dependency files. A same-version edit of
# an installed file, a missing or corrupt installation, or an earlier binding that disagrees with what is installed
# never yields a hit. The H9 entry needs redis, so its plan exercises the real RECORD-validated integrity. ---


def _h9_plan() -> MeasurementPlan:
    return default_measurement_plan(repository_root=ROOT, entries=("h9.connection_health",))[0]


def _drifted(real, name: str = "redis"):
    return lambda dependency: "0" * 64 if dependency == name else real(dependency)


def test_the_reuse_key_binds_installed_dependency_integrity_including_the_entry_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _h9_plan()
    assert "redis" in plan.spec.dependencies
    real = measurement.verify_dependency_integrity
    key = _identity(plan)
    floor_only = replace(plan.spec, dependencies=())  # the caller names no dependency: the entry's own floor still binds
    floor_key = _identity(plan, spec=floor_only)
    monkeypatch.setattr(measurement, "verify_dependency_integrity", _drifted(real))  # same version, other installed bytes
    assert _identity(plan) != key
    assert _identity(plan, spec=floor_only) != floor_key


def test_a_missing_or_corrupt_dependency_refuses_reuse(monkeypatch: pytest.MonkeyPatch) -> None:
    def corrupt(name: str) -> str:
        raise ExecutingSourceMismatch(f"dependency {name!r} installed file does not match its RECORD hash")

    monkeypatch.setattr(measurement, "verify_dependency_integrity", corrupt)
    with pytest.raises(ExecutingSourceMismatch, match="RECORD"):
        _identity(_h9_plan())


def test_a_hit_whose_earlier_binding_disagrees_with_the_installed_files_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _h9_plan()
    installed = {name: measurement.verify_dependency_integrity(name) for name in sorted(plan.spec.dependencies)}

    def binding(redis: str) -> measurement.EnvironmentBinding:
        return measurement.EnvironmentBinding(
            interpreter_executable=str(Path(sys.executable).resolve()), interpreter_version=sys.version,
            prefix=str(Path(sys.prefix).resolve()), source_fingerprint=plan.spec.source_fingerprint,
            module_origins=(("src/stand_in.py", str(ROOT / "src" / "stand_in.py"), "b" * 64),),
            dependency_files=tuple((name, redis if name == "redis" else digest) for name, digest in installed.items()),
        )

    for redis, refused in ((installed["redis"], False), ("f" * 64, True)):
        monkeypatch.setattr(measurement, "run_fresh_measurement", lambda redis=redis, **kwargs: (binding(redis), {"observations": []}))
        store = measurement.MeasurementReuse()
        _measure(store, plan, "tests/a.py::first")
        if refused:
            with pytest.raises(ExecutingSourceMismatch, match="earlier binding"):
                _measure(store, plan, "tests/a.py::second")
        else:
            assert _measure(store, plan, "tests/a.py::second")[2] == "tests/a.py::first"


# --- Through the test helpers' route: the run's own terminal record names each reuse. ---


def test_measurement_reuse_probe() -> None:
    """A nested-run target that measures the same entry twice through the plugin. A no-op in an ordinary run."""
    if os.environ.get("OPTIMUS_MEASUREMENT_REUSE_PROBE") != "1":
        return
    from tests.support import profiles_plugin

    plan = _plan()
    for _ in (1, 2):
        profiles_plugin.measure_current_entry(
            source=plan.source, spec=plan.spec, entry=plan.entry, options=plan.options, repository_root=ROOT,
        )


def test_the_terminal_record_names_every_reuse(tmp_path: Path) -> None:
    from tools.testing import run_context, run_context_records

    scratch = tmp_path / "child-temp"
    scratch.mkdir()
    env = {**os.environ, "TMPDIR": str(scratch), "TEMP": str(scratch), "TMP": str(scratch), "OPTIMUS_MEASUREMENT_REUSE_PROBE": "1"}
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", _REUSE_PROBE],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=600, check=False,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, output
    found = re.search(r"test-run-context: .* run=(?P<run>\S+)", output)
    assert found is not None, output
    record = run_context_records.read_record(ROOT / "tmp" / "test-runs" / found["run"] / "run.json")
    assert record is not None and record["checkpoint"] == "terminal", output
    node, label = run_context._node(_REUSE_PROBE), run_context._label(_REUSE_PROBE)  # noqa: SLF001
    assert record["audit_reuse"] == [{"entry": _ENTRY, "node": node, "label": label, "from_node": node, "from_label": label}]
    assert "reused: 1" in output, output
