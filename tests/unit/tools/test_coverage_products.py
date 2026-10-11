"""Product coverage full-run validity (Plan 11.30 v5 I2): the canonical gate (tools/check_product_coverage.py) decides
every floor; this layer proves its coverage JSON is complete, current, from the one full default run of this exact
clean checkout and the export the gate reported, and compares safety-critical module rows only between two such
proven runs. Absent identity is unknown, never assumed; anything else fails closed."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

import pytest

from tools import check_product_coverage as gate
from tools.testing import coverage_products as cp
from tools.testing import run_context
from tools.testing import run_context_records as records

_ROOT = Path(__file__).resolve().parents[3]


# --- Inventory: the canonical gate's groups and checks ---------------------------------------------------------

def test_every_current_source_package_belongs_to_exactly_one_product() -> None:
    files = cp.package_files(_ROOT)
    config = gate.load_groups(cp.GROUPS)
    assert sorted(files) == sorted(package for group in config.groups for package in group.packages)
    tracked = [path for paths in files.values() for path in paths]
    assert len(tracked) == len(set(tracked)) and all(path.startswith("src/") and path.endswith(".py") for path in tracked)


def test_an_inventory_the_canonical_gate_refuses_is_never_validated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """An unmapped, doubly claimed or top-level source fails the gate's own inventory; the validity layer reports
    that failure as invalid and never measures (the gate's tests cover each inventory case)."""
    monkeypatch.setattr(gate, "tracked_sources", lambda root: (PurePosixPath("optimus/a.py"), PurePosixPath("new_product/b.py")))
    with pytest.raises(gate.CoverageGateError, match="src packages in no product group: \\['new_product'\\]"):
        cp.package_files(_ROOT)
    (tmp_path / "coverage.json").write_text("{}", encoding="utf-8")
    argv = ["validate", "--coverage-json", str(tmp_path / "coverage.json"), "--gate-report", str(tmp_path / "r.json"), "--run-record", str(tmp_path / "run.json")]
    assert cp.main(argv) == cp.EXIT_INVALID
    assert "coverage-products: problem: src packages in no product group" in capsys.readouterr().out


def test_the_coverage_data_source_lists_exactly_the_source_packages() -> None:
    """Bare `--cov` measures the configured source list; a package missing from it would vanish from every report."""
    configured = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["coverage"]["run"]["source"]
    assert sorted(path.removeprefix("src/") for path in configured) == sorted(cp.package_files(_ROOT))


def test_this_layer_decides_no_product_floor() -> None:
    """The lane's own unrounded floor gate is retired (v5 I2): the canonical gate is the only floor decision."""
    assert not any(hasattr(cp, name) for name in ("FLOOR", "evaluate_products", "ProductResult", "classify_packages"))


# --- Complete, current data (pure) --------------------------------------------------------------------------

def _row(statements: int, covered: int, branches: int = 0, covered_branches: int = 0) -> dict[str, object]:
    return {"summary": {"num_statements": statements, "covered_lines": covered, "num_branches": branches,
                        "covered_branches": covered_branches, "missing_lines": statements - covered,
                        "missing_branches": branches - covered_branches}}


def _data(rows: dict[str, dict[str, object]], *, branch: bool = True, stamp: str = "2026-10-05T01:09:00") -> dict[str, object]:
    return {"meta": {"format": 3, "version": "7.14.3", "timestamp": stamp, "branch_coverage": branch}, "files": rows}


def test_complete_current_branch_data_is_valid_whatever_its_percentages() -> None:
    """Floors are the gate's; a low row is still valid data."""
    report = _data({"src/optimus/a.py": _row(10, 1, 4, 0), "src\\optimus\\b.py": _row(5, 5)})  # Windows rows use backslashes
    verdict = cp.evaluate(report, {"src/optimus/a.py": (10, 4), "src/optimus/b.py": (5, 0)}, {"optimus": ("src/optimus/a.py", "src/optimus/b.py")})
    assert verdict.passed and verdict.problems == ()


def test_a_source_file_without_a_row_fails() -> None:
    report = _data({"src/optimus/a.py": _row(10, 9)})
    verdict = cp.evaluate(report, {"src/optimus/a.py": (10, 0), "src/optimus/b.py": (5, 0)}, {"optimus": ("src/optimus/a.py", "src/optimus/b.py")})
    assert not verdict.passed and "src/optimus/b.py: no coverage row" in verdict.problems


def test_a_row_for_a_file_not_in_the_current_source_fails() -> None:
    report = _data({"src/optimus/a.py": _row(10, 9), "src/optimus/gone.py": _row(5, 5)})
    verdict = cp.evaluate(report, {"src/optimus/a.py": (10, 0)}, {"optimus": ("src/optimus/a.py",)})
    assert not verdict.passed and "src/optimus/gone.py: row for a file that is not in the current source" in verdict.problems


@pytest.mark.parametrize("current", [(11, 0), (10, 2)])
def test_a_row_whose_denominator_differs_from_the_current_source_fails(current: tuple[int, int]) -> None:
    report = _data({"src/optimus/a.py": _row(10, 9)})
    verdict = cp.evaluate(report, {"src/optimus/a.py": current}, {"optimus": ("src/optimus/a.py",)})
    assert not verdict.passed
    assert f"src/optimus/a.py: report counts 10 statements and 0 branches; the current source has {current[0]} and {current[1]}" in verdict.problems


def test_line_only_data_cannot_satisfy_the_branch_coverage_floor() -> None:
    verdict = cp.evaluate(_data({"src/optimus/a.py": _row(10, 10)}, branch=False), {"src/optimus/a.py": (10, 0)}, {"optimus": ("src/optimus/a.py",)})
    assert not verdict.passed and "the coverage data was not measured with branch coverage" in verdict.problems


def test_the_report_counts_equal_coverage_py_s_own_analysis_of_the_source(tmp_path: Path) -> None:
    """The denominators this tool recomputes are the ones coverage.py itself reports, exclusions included."""
    package = tmp_path / "src" / "pkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "mod.py").write_text(
        "import sys\n\n\ndef pick(value):\n    if value:\n        return 1\n    for item in range(2):\n        if item:\n"
        "            break\n    return 0\n\n\ndef skipped():  # pragma: no cover\n    return 2\n\n\nprint(pick(len(sys.argv) > 5))\n",
        encoding="utf-8",
    )
    config = tmp_path / "pyproject.toml"
    config.write_text('[tool.coverage.run]\nbranch = true\nsource = ["src/pkg"]\n', encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(tmp_path / "src"), "COVERAGE_FILE": str(tmp_path / ".coverage")}
    for command in (["run", "-m", "pkg.mod"], ["json", "-o", str(tmp_path / "coverage.json")]):
        subprocess.run([sys.executable, "-m", "coverage", *command, f"--rcfile={config}"], cwd=tmp_path, env=env, check=True, capture_output=True)
    rows = json.loads((tmp_path / "coverage.json").read_text(encoding="utf-8"))["files"]
    summary = next(row["summary"] for name, row in rows.items() if name.replace("\\", "/").endswith("pkg/mod.py"))
    assert cp.source_counts(package / "mod.py", config) == (summary["num_statements"], summary["num_branches"])
    assert summary["num_branches"] > 0 and summary["excluded_lines"] > 0


# --- Fixtures: one complete, clean, identified canonical run ---------------------------------------------------

_GONE = object()
_HEAD, _TREE = "a" * 40, "7" * 40
_CONFIG, _LOCK, _GROUPS_SHA, _DATASET = "c" * 64, "d" * 64, "9" * 64, "1" * 64
_UNIVERSE = ("tests/unit/test_a.py::test_one", "tests/unit/test_b.py::test_two[1]")
_UTC = timezone.utc
_GATE_START, _GATE_END = datetime(2026, 10, 5, 0, 49, tzinfo=_UTC), datetime(2026, 10, 5, 1, 10, 30, tzinfo=_UTC)
_DURING = datetime(2026, 10, 5, 1, 9, tzinfo=_UTC)


def _changed(values: dict[str, object], changes: dict[str, object]) -> dict[str, object]:
    for key, value in changes.items():
        if value is _GONE:
            values.pop(key, None)
        else:
            values[key] = value
    return values


def _digest(nodes: tuple[str, ...]) -> str:
    found = hashlib.sha256()
    for node in sorted(nodes):
        found.update(run_context._node(node).encode("ascii"))  # noqa: SLF001
    return found.hexdigest()


def _identity(**changes: object) -> cp.SourceIdentity:
    values: dict[str, object] = {"head": _HEAD, "tree": _TREE, "config_sha256": _CONFIG, "lock_sha256": _LOCK,
                                 "groups_sha256": _GROUPS_SHA, "coverage_version": "7.14.3", "universe": _UNIVERSE, "clean": True,
                                 "latest_change": ("src/optimus/a.py", "2026-10-05T00:40:00+00:00")}
    return cp.SourceIdentity(**_changed(values, changes))  # type: ignore[arg-type]


def _full_run(**changes: object) -> dict[str, object]:
    record: dict[str, object] = {
        "schema": "test-run-context-v1", "root": {"pid": 522, "creation_time": None},
        "checkpoint": "terminal", "run_id": "20261005T010000-522-b5f07d", "mode": "active", "reason": "default_selection",
        "platform": "linux", "head": _HEAD, "config_sha256": _CONFIG, "lock_sha256": _LOCK,
        "started_utc": "2026-10-05T00:50:00+00:00", "finished_utc": "2026-10-05T01:10:00+00:00",
        "completeness": "COMPLETE", "exit_status": 0, "collection_errors": 0,
        "selected": len(_UNIVERSE), "selection_sha256": _digest(_UNIVERSE),
        "native": {"supported": False, "attempted": False, "enrolled": False}, "guard_mode": "unsupported_platform",
        "protection": "none", "parent_run": {"status": "unsupported"}, "audit_depth": "full",
    }
    return _changed(record, changes)


def _gate_run(**changes: object) -> dict[str, object]:
    run: dict[str, object] = {
        "schema": gate.RUN_RECORD_SCHEMA, "git_head": _HEAD, "git_tree": _TREE, "worktree_dirty": False,
        "git_head_after": _HEAD, "git_tree_after": _TREE, "worktree_dirty_after": False,
        "command": ["python", *gate.FULL_SUITE_ARGS], "groups_path": "tools/product-coverage-groups.json", "groups_sha256": _GROUPS_SHA,
        "pyproject_sha256": _CONFIG, "uv_lock_sha256": _LOCK, "coverage_version": "7.14.3",
        "coverage_config": {"run": {"branch": True, "source": ["src/optimus"]}, "report": {"fail_under": 80}},
        "python_implementation": "CPython", "python_version": "3.14.8", "platform": "linux",
        "pytest_exit": 0, "data_file": ".coverage", "data_file_sha256": _DATASET,
        "started": _GATE_START.timestamp(), "finished": _GATE_END.timestamp(),
    }
    return _changed(run, changes)


def _gate_report(json_sha: str = "f" * 64, *, passed: bool = True, coverage: dict[str, object] | None = None, **run: object) -> dict[str, object]:
    gate_run = _gate_run(**({"pytest_exit": 1} if not passed else {}), **run)
    measured: dict[str, object] = {"data_file_sha256": _DATASET, "coverage_json_sha256": json_sha, "precision": 0, "floors": []}
    measured.update(coverage or {})
    return {"run": gate_run, "coverage": measured, "verdict": {"passed": passed, "failures": [] if passed else ["full suite exit 1"]}}


def _meta(at: datetime) -> dict[str, object]:
    """A coverage JSON timestamp as coverage.py writes it: naive, in the producer's local time (this host here)."""
    return {"branch_coverage": True, "timestamp": at.astimezone().replace(tzinfo=None).isoformat()}


# --- Full-run binding to this source (pure) ---------------------------------------------------------------

def test_coverage_from_the_full_default_run_of_this_source_is_accepted() -> None:
    assert cp.full_run_problems(_full_run(), _meta(_DURING), _identity()) == []


def test_coverage_from_a_reduced_depth_or_unlabelled_run_is_refused() -> None:
    assert cp.full_run_problems(_full_run(audit_depth="quick"), _meta(_DURING), _identity()) == [
        "the run's own record cannot support a result: audit_depth_quick"]
    assert cp.full_run_problems(_full_run(audit_depth=_GONE), _meta(_DURING), _identity()) == [
        "the run's own record cannot support a result: audit_depth_missing"]


@pytest.mark.parametrize(("changes", "identity", "problem"), [
    ({"completeness": "INVALID"}, {}, "the run's own record cannot support a result: records_INVALID"),
    ({"mode": "passive"}, {}, "the run's own record cannot support a result: mode_passive"),
    ({"checkpoint": "start"}, {}, "the run's own record cannot support a result: no_terminal_record"),
    ({"reason": "explicit_targets"}, {}, "the run was not the default selection (explicit_targets)"),
    ({"collection_errors": 2}, {}, "the run had 2 collection errors"),
    ({"selected": 1, "selection_sha256": _digest(_UNIVERSE[:1])}, {}, "the run did not select the current default universe (1 of 2 tests)"),
    ({"selection_sha256": _digest(("tests/unit/test_c.py::test_other", _UNIVERSE[1]))}, {}, "the run did not select the current default universe (2 of 2 tests)"),
    ({"exit_status": 1}, {}, "the run's own record cannot support a result: exit_status_differs"),
    ({}, {"head": "b" * 40}, f"the run measured commit {_HEAD}, not the current HEAD {'b' * 40}"),
    ({}, {"config_sha256": "e" * 64}, "the run used a different pyproject.toml"),
    ({}, {"lock_sha256": "e" * 64}, "the run used a different uv.lock"),
    ({}, {"clean": False}, "the checkout has uncommitted or untracked changes, so the run's commit does not identify what it measured"),
    # A dirty run, then `git stash` / `checkout` / `restore`: the tree is clean again, but a file was rewritten.
    ({}, {"latest_change": ("tools/check_product_coverage.py", "2026-10-05T00:55:00+00:00")},
     "tools/check_product_coverage.py changed at 2026-10-05 00:55:00+00:00, after the run started, so the run may have measured other bytes"),
])
def test_partial_failed_or_source_mismatched_runs_are_rejected(changes: dict[str, object], identity: dict[str, object], problem: str) -> None:
    assert problem in cp.full_run_problems(_full_run(**changes), _meta(_DURING), _identity(**identity))


@pytest.mark.parametrize("at", [datetime(2026, 10, 5, 0, 49, tzinfo=_UTC), datetime(2026, 10, 5, 1, 16, tzinfo=_UTC)])
def test_coverage_written_outside_the_run_is_not_that_run_s_data(at: datetime) -> None:
    problems = cp.full_run_problems(_full_run(), _meta(at), _identity())
    assert any(problem.startswith("the coverage data was written at") for problem in problems)


# --- Receipts: one clean, canonical, identified gate run (I-M1) --------------------------------------------

def test_a_complete_clean_receipt_bound_to_this_source_has_no_problem() -> None:
    """Positive control: every negative below changes exactly one fact of this binding."""
    assert cp.gate_binding_problems(_gate_report(), "f" * 64, _full_run(), _identity()) == []


def test_codex_i_m1_counterexample_a_dirty_gate_checkout_is_refused() -> None:
    """Codex HOLD 2026-10-09 11:12:08 UTC, I-M1: matching hashes, window, head, config and lock with
    `worktree_dirty=True` returned no problem from the proposal's draft."""
    problems = cp.gate_binding_problems(_gate_report(worktree_dirty=True), "f" * 64, _full_run(), _identity())
    assert "the gate run: worktree_dirty is True: the checkout was not proven clean" in problems


@pytest.mark.parametrize("key", ["worktree_dirty", "worktree_dirty_after"])
@pytest.mark.parametrize("value", [True, None, "false", _GONE], ids=["dirty", "unknown", "string", "absent"])
def test_a_checkout_not_proven_clean_before_and_after_is_refused(key: str, value: object) -> None:
    problems = cp.receipt_problems(_gate_run(**{key: value}), "the gate run")
    assert any(problem.startswith(f"the gate run: {key} is ") for problem in problems), problems


@pytest.mark.parametrize("key", cp.REQUIRED_RECEIPT_KEYS)
def test_every_required_receipt_is_required_and_an_absent_one_is_unknown_identity(key: str) -> None:
    problems = cp.receipt_problems(_gate_run(**{key: _GONE}), "the gate run")
    assert any(key in problem for problem in problems), (key, problems)


@pytest.mark.parametrize(("changes", "problem"), [
    ({"git_head_after": "b" * 40}, "the gate run: the checkout moved during the run"),
    ({"git_tree_after": "8" * 40}, "the gate run: the checkout moved during the run"),
    ({"schema": "plan12-product-coverage-run-v0"}, "the gate run: run record schema 'plan12-product-coverage-run-v0' is not plan12-product-coverage-run-v1"),
    ({"groups_path": "elsewhere/groups.json"}, "the gate run: floors came from groups_path 'elsewhere/groups.json', not tools/product-coverage-groups.json"),
    ({"command": ["python", *gate.FULL_SUITE_ARGS, "-k", "x"]}, "the gate run: command is not the canonical full selection"),
    ({"command": ["python", *(arg for arg in gate.FULL_SUITE_ARGS if arg != "--cov-branch")]}, "the gate run: command is not the canonical full selection"),
    ({"git_tree": "short"}, "the gate run: git_tree unrecorded or malformed: identity unknown, unsupported for this claim"),
    ({"coverage_config": {"run": {"branch": False}}}, "the gate run: coverage_config unrecorded or without branch measurement"),
    ({"coverage_config": {"run": {"branch": True}, "report": {"precision": 2}}}, "the gate run: configured report precision 2 is not the canonical 0"),
    ({"python_implementation": ""}, "the gate run: python_implementation unrecorded"),
    ({"started": _GATE_END.timestamp(), "finished": _GATE_START.timestamp()}, "the gate run: run window (started, finished) unrecorded or reversed"),
])
def test_a_moved_unknown_or_non_canonical_gate_run_is_refused(changes: dict[str, object], problem: str) -> None:
    assert problem in cp.receipt_problems(_gate_run(**changes), "the gate run")


@pytest.mark.parametrize(("report", "identity", "problem"), [
    (_gate_report(coverage={"coverage_json_sha256": "0" * 64}), {}, "the coverage JSON is not the export the gate reported"),
    ({**_gate_report(), "coverage": None}, {}, "the coverage JSON is not the export the gate reported"),
    (_gate_report(coverage={"data_file_sha256": "2" * 64}), {}, "the gate report does not name the dataset its run recorded"),
    (_gate_report(coverage={"precision": 1}), {}, "the gate compared at precision 1, not the canonical 0"),
    (_gate_report(git_head="b" * 40, git_head_after="b" * 40), {}, f"the gate measured commit {'b' * 40}, not the current HEAD {_HEAD}"),
    (_gate_report(), {"tree": "8" * 40}, f"the gate measured tree {_TREE}, not the current tree {'8' * 40}"),
    (_gate_report(), {"groups_sha256": "8" * 64}, "the gate's groups policy is not the current tools/product-coverage-groups.json"),
    (_gate_report(), {"coverage_version": "7.0.0"}, "the gate ran coverage 7.14.3; the current source is analysed with 7.0.0"),
    (_gate_report(uv_lock_sha256="e" * 64), {}, "the gate ran with a different pyproject.toml or uv.lock"),
    # Another run-context record (a later full run, or one before the gate started) is not this gate's run.
    (_gate_report(started=datetime(2026, 10, 5, 0, 51, tzinfo=_UTC).timestamp()), {}, "the run-context record is not the gate's own full run"),
])
def test_a_json_or_run_the_gate_did_not_report_for_this_source_is_refused(report: dict[str, object], identity: dict[str, object], problem: str) -> None:
    assert problem in cp.gate_binding_problems(report, "f" * 64, _full_run(), _identity(**identity))


# --- Exactly one eligible full session (F1; no "largest selected" shortcut) --------------------------------

def _plant(root: Path, name: str, **changes: object) -> Path:
    folder = root / "tmp" / "test-runs" / name
    folder.mkdir(parents=True)
    (folder / "run.json").write_text(json.dumps(_full_run(**changes)), encoding="utf-8")
    return folder / "run.json"


def test_the_one_eligible_full_session_is_found_among_nested_collection_and_foreign_records(tmp_path: Path) -> None:
    full = _plant(tmp_path, "full")
    _plant(tmp_path, "nested", selected=1, selection_sha256=_digest(_UNIVERSE[:1]))  # a nested probe session inside the window
    _plant(tmp_path, "collection", mode="passive", reason="collection_only")
    _plant(tmp_path, "yesterday", started_utc="2026-10-04T00:50:00+00:00", finished_utc="2026-10-04T01:10:00+00:00")
    _plant(tmp_path, "other-commit", head="b" * 40)
    found, considered = cp.eligible_full_runs(sorted(tmp_path.glob("tmp/test-runs/*/run.json")), _gate_run(), _UNIVERSE)
    assert found == [full] and considered == 5


def test_two_eligible_sessions_or_none_bind_nothing(tmp_path: Path) -> None:
    _plant(tmp_path, "one")
    _plant(tmp_path, "twin")
    found, _ = cp.eligible_full_runs(sorted(tmp_path.glob("tmp/test-runs/*/run.json")), _gate_run(), _UNIVERSE)
    assert len(found) == 2  # ambiguous: the caller refuses it, never picks one
    assert cp.eligible_full_runs([], _gate_run(), _UNIVERSE) == ([], 0)


def test_validate_without_a_record_binds_only_exactly_one_eligible_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    for name in ("one", "twin"):
        _plant(tmp_path, name)
    (tmp_path / "coverage.json").write_text("{}", encoding="utf-8")
    (tmp_path / "r.json").write_text(json.dumps(_gate_report()), encoding="utf-8")
    monkeypatch.setattr(cp, "ROOT", tmp_path)
    monkeypatch.setattr(cp, "_default_universe", lambda root: _UNIVERSE)
    assert cp.main(["validate", "--coverage-json", str(tmp_path / "coverage.json"), "--gate-report", str(tmp_path / "r.json")]) == cp.EXIT_INVALID
    assert "coverage-products: problem: 2 eligible full sessions in the gate's window; none is bound" in capsys.readouterr().out


# --- Full validation over a real repository ------------------------------------------------------------------

def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def _real_repository(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    for package in ("optimus", "evidence_handoff"):
        (root / "src" / package).mkdir(parents=True)
        (root / "src" / package / "__init__.py").write_text("", encoding="utf-8")
        (root / "src" / package / "core.py").write_text("def one(flag):\n    if flag:\n        return 1\n    return 0\n", encoding="utf-8")
    (root / "tools").mkdir()
    (root / "tools" / "product-coverage-groups.json").write_text(json.dumps({"schema_version": 1, "groups": [
        {"name": "optimus", "packages": ["optimus"], "floor": 80, "enforced": True},
        {"name": "evidence_handoff", "packages": ["evidence_handoff"], "floor": 80, "enforced": False},
    ], "aggregate": {"floor": 80, "enforced": False}}), encoding="utf-8")
    (root / "tools" / "gate.py").write_text("GATE = 1\n", encoding="utf-8")
    (root / "pyproject.toml").write_text('[tool.coverage.run]\nbranch = true\nsource = ["src/optimus", "src/evidence_handoff"]\n', encoding="utf-8")
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (root / ".gitignore").write_text("tmp/\n", encoding="utf-8")
    _git(root.parent, "init", "-q", str(root))
    _git(root, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "add", ".")
    _git(root, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-q", "-m", "seed")
    return root, root / "tools" / "product-coverage-groups.json"


def test_the_whole_checkout_counts_for_cleanliness_tools_and_untracked_files_included(tmp_path: Path) -> None:
    root, groups = _real_repository(tmp_path)
    assert cp.source_identity(root, _UNIVERSE).clean
    (root / "tmp").mkdir()
    (root / "tmp" / "out.txt").write_text("an ignored output", encoding="utf-8")
    assert cp.source_identity(root, _UNIVERSE).clean  # ignored outputs never make it dirty
    (root / "scratch.txt").write_text("untracked", encoding="utf-8")
    assert not cp.source_identity(root, _UNIVERSE).clean
    (root / "scratch.txt").unlink()
    gate_file = root / "tools" / "gate.py"
    gate_file.write_text("GATE = 2\n", encoding="utf-8")  # outside src/, tests/, config and lock
    future = datetime.now(_UTC).timestamp() + 3600
    os.utime(gate_file, (future, future))
    identity = cp.source_identity(root, _UNIVERSE)
    assert not identity.clean and identity.latest_change is not None and identity.latest_change[0] == "tools/gate.py"
    assert identity.tree == _git(root, "rev-parse", "HEAD^{tree}")
    assert identity.groups_sha256 == hashlib.sha256(groups.read_bytes()).hexdigest()


def test_a_real_repository_s_current_full_run_data_is_evaluated_end_to_end(tmp_path: Path) -> None:
    import coverage  # noqa: PLC0415

    root, groups = _real_repository(tmp_path)
    files = {}
    for package in ("optimus", "evidence_handoff"):
        for name in ("__init__.py", "core.py"):
            statements, branches = cp.source_counts(root / "src" / package / name, root / "pyproject.toml")
            files[f"src/{package}/{name}"] = _row(statements, statements, branches, branches)
    started = datetime.now(_UTC) + timedelta(seconds=1)  # the run starts after the source was written
    report_path = tmp_path / "coverage.json"
    report_path.write_text(json.dumps({"meta": _meta(started + timedelta(minutes=10)), "files": files}), encoding="utf-8")
    head, tree = _git(root, "rev-parse", "HEAD"), _git(root, "rev-parse", "HEAD^{tree}")
    config_sha, lock_sha, groups_sha = (hashlib.sha256(path.read_bytes()).hexdigest() for path in (root / "pyproject.toml", root / "uv.lock", groups))
    record_path = tmp_path / "run.json"
    record_path.write_text(json.dumps(_full_run(head=head, config_sha256=config_sha, lock_sha256=lock_sha, started_utc=started.isoformat(),
                                                finished_utc=(started + timedelta(minutes=20)).isoformat())), encoding="utf-8")
    gate_path = tmp_path / "gate.json"
    gate_path.write_text(json.dumps(_gate_report(
        hashlib.sha256(report_path.read_bytes()).hexdigest(), git_head=head, git_head_after=head, git_tree=tree, git_tree_after=tree,
        pyproject_sha256=config_sha, uv_lock_sha256=lock_sha, groups_sha256=groups_sha, coverage_version=coverage.__version__,
        started=started.timestamp() - 5, finished=started.timestamp() + 21 * 60)), encoding="utf-8")

    def validate() -> cp.CoverageVerdict:
        return cp.validate_run(report_path, gate_path, record_path, root=root, groups=groups, universe=_UNIVERSE)

    verdict = validate()
    assert verdict.problems == () and verdict.passed
    core = root / "src" / "optimus" / "core.py"
    core.write_text("def one(flag):\n    return 1 if flag else 0\n", encoding="utf-8")
    os.utime(core, (started.timestamp() + 60, started.timestamp() + 60))  # edited during the run
    drifted = validate()
    assert not drifted.passed and any("the current source has" in problem for problem in drifted.problems)
    assert any("uncommitted or untracked changes" in problem for problem in drifted.problems)
    # The edit is reverted (`git checkout`, `git stash`): clean again, same counts, but rewritten after the run began.
    _git(root, "checkout", "--", "src/optimus/core.py")
    os.utime(core, (started.timestamp() + 120, started.timestamp() + 120))
    assert validate().problems == (
        f"src/optimus/core.py changed at {datetime.fromtimestamp(started.timestamp() + 120, _UTC)}, after the run started, "
        "so the run may have measured other bytes",)
    os.utime(core, (started.timestamp() - 60, started.timestamp() - 60))
    tool = root / "tools" / "gate.py"  # a gate or tool file rewritten during the run is caught as well
    os.utime(tool, (started.timestamp() + 90, started.timestamp() + 90))
    assert any(problem.startswith("tools/gate.py changed at") for problem in validate().problems)


# --- What the tool prints ------------------------------------------------------------------------------------

def test_printed_problems_pass_the_shared_sanitizer(capsys: pytest.CaptureFixture[str]) -> None:
    cp._print_verdict(cp.CoverageVerdict(("src/optimus/x.py: from http://user:hunter2@example.invalid",)))  # noqa: SLF001  # pragma: allowlist secret - synthetic credential-shaped text the sanitizer must mask
    printed = capsys.readouterr().out
    assert printed.startswith("coverage-products: problem: src/optimus/x.py") and "hunter2" not in printed
    assert printed.rstrip().endswith("full-run validity NOT established")


def test_an_input_failure_line_passes_the_shared_sanitizer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def unreadable(*args: object, **kwargs: object) -> cp.CoverageVerdict:
        raise ValueError("unreadable http://user:hunter2@example.invalid")  # pragma: allowlist secret - synthetic credential-shaped text the sanitizer must mask

    monkeypatch.setattr(cp, "validate_run", unreadable)
    argv = ["validate", "--coverage-json", str(tmp_path / "coverage.json"), "--gate-report", str(tmp_path / "r.json"), "--run-record", str(tmp_path / "run.json")]
    assert cp.main(argv) == cp.EXIT_INPUT
    printed = capsys.readouterr().out
    assert printed.startswith("coverage-products: input failure: unreadable") and "hunter2" not in printed


# --- Safety-critical module rows: base against candidate -----------------------------------------------------

def _safety(**overrides: tuple[int, int, int, int]) -> dict[str, object]:
    rows = {path: _row(100, 95, 20, 18) for path in cp.SAFETY_MODULES}
    rows.update({path: _row(*counts) for path, counts in overrides.items()})
    return _data(rows)


def test_comparable_safety_rows_without_regression_pass_and_improvements_are_fine() -> None:
    improved = _safety(**{cp.SAFETY_MODULES[0]: (100, 99, 20, 20)})
    assert cp.compare_safety_rows(_safety(), improved) == []


def test_a_safety_row_regression_or_a_missing_row_or_incomparable_data_is_reported() -> None:
    assert cp.compare_safety_rows(_safety(), _safety(**{cp.SAFETY_MODULES[1]: (100, 94, 20, 18)})) == [
        f"{cp.SAFETY_MODULES[1]}: regressed from 95/100 statements and 18/20 branches to 94/100 statements and 18/20 branches"]
    # More statements and more misses at a higher percentage is still a regression: misses are compared, not rounding.
    assert cp.compare_safety_rows(_safety(), _safety(**{cp.SAFETY_MODULES[3]: (200, 194, 20, 18)})) == [
        f"{cp.SAFETY_MODULES[3]}: regressed from 95/100 statements and 18/20 branches to 194/200 statements and 18/20 branches"]
    missing = _safety()
    del missing["files"][cp.SAFETY_MODULES[2]]  # type: ignore[union-attr]
    assert cp.compare_safety_rows(_safety(), missing) == [f"{cp.SAFETY_MODULES[2]}: no row in the candidate report"]
    other_tool = _safety()
    other_tool["meta"] = {**other_tool["meta"], "version": "7.0.0"}  # type: ignore[dict-item]
    assert cp.compare_safety_rows(_safety(), other_tool) == ["the reports were made by different coverage versions (7.14.3, 7.0.0)"]


def test_windows_row_keys_compare_as_the_same_modules() -> None:
    windows = _data({path.replace("/", "\\"): row for path, row in _safety()["files"].items()})  # type: ignore[union-attr]
    assert cp.compare_safety_rows(_safety(), windows) == []


# --- Comparable runs: both proven full sessions (I-M2, Q-C1, Q-C2, producer timezone) ----------------------

_BASE_HEAD, _BASE_TREE = "b" * 40, "6" * 40


def _side(label: str, *, data: dict[str, object] | None = None, record: dict[str, object] | None = None, offset: str = "+00:00",
          depth_proof: bool = False, report: dict[str, object] | None = None, **run: object) -> cp.Side:
    """A gate export, its report and its run-context record as one CI run uploads them (a UTC producer)."""
    body = json.dumps(data or _safety()).encode("utf-8")
    base = label == "base"
    identity = {"git_head": _BASE_HEAD, "git_head_after": _BASE_HEAD, "git_tree": _BASE_TREE, "git_tree_after": _BASE_TREE} if base else {}
    gate_report = report or _gate_report(hashlib.sha256(body).hexdigest(), **{**identity, **run})
    session = record or _full_run(**({"head": _BASE_HEAD, "audit_depth": _GONE} if base else {}))
    return cp.Side(label=label, report=gate_report, data=body, record=session, producer_offset=offset, depth_proof=depth_proof)


def _base(**changes: object) -> cp.Side:
    return _side("base", **{"depth_proof": True, **changes})


def _candidate(**changes: object) -> cp.Side:
    return _side("candidate", **changes)


def test_two_proven_full_sessions_with_one_engine_configuration_and_policy_are_comparable() -> None:
    """Positive control. The base lacks `audit_depth` and its exact-SHA proof is supplied: a qualification only."""
    problems, qualifications = cp.comparable_runs(_base(), _candidate())
    assert problems == [] and qualifications == ["base: audit_depth_unrecorded:no-option-at-base"]


def test_codex_i_m2_counterexample_an_unidentified_dirty_passed_export_is_refused() -> None:
    """Codex HOLD 2026-10-09 11:12:08 UTC, I-M2: matching JSON, configuration and version, pytest exit 0 and
    `passed=True`, but HEAD, tree, schema and command absent and dirty true, returned no problem from the draft."""
    body = json.dumps(_safety()).encode("utf-8")
    report = _gate_report(hashlib.sha256(body).hexdigest(), git_head=_GONE, git_tree=_GONE, schema=_GONE, command=_GONE, worktree_dirty=True)
    problems, _ = cp.comparable_runs(_base(), _candidate(report=report))
    for fact in ("git_head", "git_tree", "schema", "command", "worktree_dirty"):
        assert any(problem.startswith("candidate: ") and fact in problem for problem in problems), (fact, problems)


@pytest.mark.parametrize("label", ["base", "candidate"])
@pytest.mark.parametrize("key", cp.REQUIRED_RECEIPT_KEYS)
def test_a_missing_receipt_on_either_side_makes_the_runs_incomparable(label: str, key: str) -> None:
    sides = {"base": _base(), "candidate": _candidate()}
    sides[label] = (_base if label == "base" else _candidate)(**{key: _GONE})
    problems, _ = cp.comparable_runs(sides["base"], sides["candidate"])
    assert any(problem.startswith(f"{label}: ") and key in problem for problem in problems), (label, key, problems)


@pytest.mark.parametrize(("record", "problem"), [
    (_full_run(completeness="INVALID"), "candidate: the run's own record cannot support a result: records_INVALID"),
    (_full_run(mode="passive"), "candidate: the run's own record cannot support a result: mode_passive"),
    (_full_run(checkpoint="start"), "candidate: the run's own record cannot support a result: no_terminal_record"),
    (_full_run(exit_status=1), "candidate: the run's own record cannot support a result: exit_status_differs"),
    (_full_run(reason="non_default_selection"), "candidate: the run was not the default selection (non_default_selection)"),
    (_full_run(collection_errors=1), "candidate: the run had 1 collection errors"),
    (_full_run(selection_sha256=_GONE), "candidate: the run recorded no selection count and digest"),
    (_full_run(head="c" * 40), f"candidate: the run-context record measured {'c' * 40}, not the gate's {_HEAD}"),
    (_full_run(config_sha256="e" * 64), "candidate: the run-context record used another pyproject.toml or uv.lock than the gate"),
    (_full_run(started_utc="2026-10-05T00:48:00+00:00"), "candidate: the run-context record is not inside the gate's own run"),
])
def test_a_passed_flag_never_substitutes_for_a_proven_full_session(record: dict[str, object], problem: str) -> None:
    problems, _ = cp.comparable_runs(_base(), _candidate(record=record))
    assert problem in problems, problems


def test_a_valid_session_whose_gate_failed_is_reported_as_a_failed_gate_not_as_provenance() -> None:
    body = json.dumps(_safety()).encode("utf-8")
    failed = _candidate(report=_gate_report(hashlib.sha256(body).hexdigest(), passed=False), record=_full_run(exit_status=1))
    problems, _ = cp.comparable_runs(_base(), failed)
    assert problems == ["candidate: the gate failed (full suite exit 1), so its rows are not a passing full run's"]


def test_the_export_and_the_dataset_must_be_the_ones_the_gate_named() -> None:
    other = _candidate(data=_safety(**{cp.SAFETY_MODULES[0]: (100, 99, 20, 20)}), report=_gate_report("0" * 64))
    assert "candidate: the JSON is not the export its gate report names" in cp.comparable_runs(_base(), other)[0]
    body = json.dumps(_safety()).encode("utf-8")
    dataset = _candidate(report=_gate_report(hashlib.sha256(body).hexdigest(), coverage={"data_file_sha256": "2" * 64}))
    assert "candidate: the gate report does not name the dataset its run recorded" in cp.comparable_runs(_base(), dataset)[0]


@pytest.mark.parametrize(("change", "problem"), [
    ({"coverage_version": "7.0.0"}, "the runs differ in coverage_version ('7.14.3', '7.0.0')"),
    ({"coverage_config": {"run": {"branch": True, "source": ["src/optimus"]}, "report": {"exclude_lines": ["x"]}}}, "the runs differ in coverage_config"),
    ({"groups_sha256": "8" * 64}, "the runs differ in groups_sha256"),
    ({"platform": "win32"}, "the runs differ in platform ('linux', 'win32')"),
    ({"python_implementation": "PyPy"}, "the runs differ in python_implementation ('CPython', 'PyPy')"),
    ({"python_version": "3.13.9"}, "the runs differ in Python major.minor (3.14.8, 3.13.9)"),
])
def test_another_engine_configuration_policy_platform_or_interpreter_is_incomparable(change: dict[str, object], problem: str) -> None:
    problems, _ = cp.comparable_runs(_base(), _candidate(**change))
    assert any(found.startswith(problem) for found in problems), problems


def test_a_lock_or_configuration_hash_binds_each_run_to_its_own_source_and_need_not_match_across_commits() -> None:
    body = json.dumps(_safety()).encode("utf-8")
    candidate = _candidate(record=_full_run(lock_sha256="e" * 64), report=_gate_report(hashlib.sha256(body).hexdigest(), uv_lock_sha256="e" * 64))
    assert cp.comparable_runs(_base(), candidate)[0] == []


def test_a_python_patch_difference_is_a_disclosed_qualification_not_a_problem() -> None:
    problems, qualifications = cp.comparable_runs(_base(), _candidate(python_version="3.14.9"))
    assert problems == [] and "python_patch_differs: base 3.14.8, candidate 3.14.9" in qualifications


@pytest.mark.parametrize(("base", "candidate", "problem"), [
    ({"depth_proof": False}, {}, "base: audit_depth unrecorded and no exact-SHA proof that the producer has no audit-depth option: UNKNOWN"),
    ({"record": _full_run(head=_BASE_HEAD, audit_depth=None)}, {}, "base: the run's own record cannot support a result: audit_depth_None"),
    ({"record": _full_run(head=_BASE_HEAD, audit_depth="")}, {}, "base: the run's own record cannot support a result: audit_depth_"),
    ({"record": _full_run(head=_BASE_HEAD, audit_depth="quick")}, {}, "base: the run's own record cannot support a result: audit_depth_quick"),
    ({}, {"record": _full_run(audit_depth=_GONE)}, "candidate: the run's own record cannot support a result: audit_depth_missing"),
    ({}, {"record": _full_run(audit_depth="quick")}, "candidate: the run's own record cannot support a result: audit_depth_quick"),
], ids=["base-absent-unproven", "base-null", "base-empty", "base-quick", "candidate-absent", "candidate-quick"])
def test_only_the_proven_base_may_lack_an_audit_depth_and_never_record_a_reduced_one(base: dict[str, object], candidate: dict[str, object], problem: str) -> None:
    """Q-C1 (2026-10-09 11:43:37 UTC): key absence, proven by exact-SHA inspection, is the base's qualification; an
    explicit null, empty, quick or unknown value fails on either side, and the candidate must record full."""
    problems, _ = cp.comparable_runs(_base(**base), _candidate(**candidate))
    assert problem in problems, problems


@pytest.mark.parametrize(("offset", "fine"), [("+00:00", True), ("+05:30", False)])
def test_a_naive_coverage_timestamp_is_read_in_the_producer_timezone_never_the_analyst_s(offset: str, fine: bool) -> None:
    """coverage.py writes `meta.timestamp` naive in its producer's local time; a UTC CI artifact read as IST would move
    out of its own run. The producer offset is a receipt, never this host's zone."""
    data = _safety()
    data["meta"] = {**data["meta"], "timestamp": "2026-10-05T01:10:04"}  # 4 s after the session ended, in UTC
    problems, _ = cp.comparable_runs(_base(), _candidate(data=data, offset=offset))
    assert (problems == []) is fine, problems
    if not fine:
        assert any(problem.startswith("candidate: the coverage data was written at") for problem in problems)


def test_an_unparseable_producer_offset_is_unsupported() -> None:
    problems, _ = cp.comparable_runs(_base(), _candidate(offset="IST"))
    assert "candidate: producer UTC offset 'IST' is not a ±HH:MM offset: timezone unknown, unsupported" in problems


def _write_sides(tmp_path: Path, base: cp.Side, candidate: cp.Side) -> list[str]:
    argv = ["compare"]
    for side in (base, candidate):
        paths = {"": side.data, "-report": json.dumps(side.report).encode("utf-8"), "-run-record": json.dumps(side.record).encode("utf-8")}
        for suffix, body in paths.items():
            path = tmp_path / f"{side.label}{suffix}.json"
            path.write_bytes(body)
            argv += [f"--{side.label}{suffix}", str(path)]
        argv += [f"--{side.label}-producer-utc-offset", side.producer_offset]
    return [*argv, "--base-audit-depth-proven-absent"]


def test_the_safety_comparison_names_the_two_reports_it_compared(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    argv = _write_sides(tmp_path, _base(), _candidate(data=_safety(**{cp.SAFETY_MODULES[0]: (100, 99, 20, 20)})))
    assert cp.main(argv) == cp.EXIT_PASS
    printed = capsys.readouterr().out
    assert all(hashlib.sha256((tmp_path / f"{name}.json").read_bytes()).hexdigest() in printed for name in ("base", "candidate"))
    assert "coverage-products: qualification: base: audit_depth_unrecorded:no-option-at-base" in printed
    assert "safety rows comparable, no regression" in printed


def test_compare_reads_both_conforming_records_through_the_run_record_reader(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Positive control (Fable I4 S1): both sides' records conform to the run-context field table, so the shared reader
    returns them unchanged, and the base's proven absent audit depth stays a qualification."""
    argv = _write_sides(tmp_path, _base(), _candidate())
    for side in (_base(), _candidate()):
        assert records.read_record(tmp_path / f"{side.label}-run-record.json") == side.record
    assert cp.main(argv) == cp.EXIT_PASS
    printed = capsys.readouterr().out
    assert "coverage-products: qualification: base: audit_depth_unrecorded:no-option-at-base" in printed
    assert "safety rows comparable, no regression" in printed


def test_a_safety_regression_is_still_reported_through_the_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The reader change leaves safety outcomes unchanged: a regressed module is still reported and fails."""
    argv = _write_sides(tmp_path, _base(), _candidate(data=_safety(**{cp.SAFETY_MODULES[1]: (100, 94, 20, 18)})))
    assert cp.main(argv) == cp.EXIT_REGRESSED
    printed = capsys.readouterr().out
    assert f"coverage-products: safety: {cp.SAFETY_MODULES[1]}: regressed from" in printed
    assert "safety rows regressed or incomparable" in printed


def _unexpected_field(record: dict[str, object]) -> bytes:
    return json.dumps({**record, "unexpected_field": True}).encode("utf-8")


def _malformed(record: dict[str, object]) -> bytes:
    return json.dumps(record).encode("utf-8")[:-1]


def _oversized(record: dict[str, object]) -> bytes:
    body = json.dumps(record).encode("utf-8")
    return body[:-1] + b" " * records.MAX_RECORD_BYTES + b"}"  # still valid JSON, but larger than any record may be


@pytest.mark.parametrize("label", ["base", "candidate"])
@pytest.mark.parametrize("damage", [_unexpected_field, _malformed, _oversized], ids=["unexpected-field", "malformed", "oversized"])
def test_compare_refuses_a_record_the_run_record_reader_refuses(tmp_path: Path, capsys: pytest.CaptureFixture[str], label: str, damage: object) -> None:
    """Fable I4 S1, reproduced by Codex (2026-10-10): `compare` loaded both run records with plain JSON, so a record the
    run-context field table refuses (an out-of-table field, malformed, oversized) was compared as if valid. Each side's
    record now goes through `records.read_record`; one it refuses makes the runs incomparable, named by side."""
    base, candidate = _base(), _candidate()
    argv = _write_sides(tmp_path, base, candidate)
    side = base if label == "base" else candidate
    (tmp_path / f"{label}-run-record.json").write_bytes(damage(side.record))  # type: ignore[operator]
    assert records.read_record(tmp_path / f"{label}-run-record.json") is None
    assert cp.main(argv) == cp.EXIT_REGRESSED
    printed = capsys.readouterr().out
    assert (f"coverage-products: safety: {label}: the run-context record is missing, unreadable, oversized, malformed "
            "or outside the run-record field table, so the run cannot be identified") in printed
    assert "safety rows regressed or incomparable" in printed
    other = "candidate" if label == "base" else "base"
    assert f"coverage-products: safety: {other}:" not in printed


@pytest.mark.parametrize("missing", ["--base-run-record", "--candidate-run-record", "--base-producer-utc-offset", "--candidate-producer-utc-offset"])
def test_compare_requires_both_session_records_and_both_producer_offsets(tmp_path: Path, missing: str) -> None:
    argv = _write_sides(tmp_path, _base(), _candidate())
    index = argv.index(missing)
    with pytest.raises(SystemExit) as exit_info:
        cp.main(argv[:index] + argv[index + 2:])
    assert exit_info.value.code == 2


def test_the_safety_modules_are_the_seven_named_optimus_files() -> None:
    assert cp.SAFETY_MODULES == (
        "src/optimus/tools/registry.py", "src/optimus/runtime/mutation.py", "src/optimus/gateway/models.py",
        "src/optimus/evidence/ledger.py", "src/optimus/acp/framing.py", "src/optimus/retry/policy.py", "src/optimus/tools/policy.py",
    )
    assert all((_ROOT / path).is_file() for path in cp.SAFETY_MODULES)
