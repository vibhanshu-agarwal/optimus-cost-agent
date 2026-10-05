"""Product coverage gates: every production package belongs to exactly one product, each enforced product is
measured unrounded against its floor over complete, current, full-run data, and anything else fails closed."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tools.testing import coverage_products as cp
from tools.testing import run_context

_ROOT = Path(__file__).resolve().parents[3]
_CURRENT = ("optimus", "optimus_gateway", "optimus_security", "evidence_handoff", "evidence_handoff_runtime")


# --- Classification ------------------------------------------------------------------------------------------

def test_every_current_source_package_belongs_to_exactly_one_product() -> None:
    packages = cp.discover_packages(_ROOT)
    assert packages == tuple(sorted(_CURRENT))  # distribution metadata such as *.egg-info is not a package
    members = [package for group in cp.PRODUCTS.values() for package in group]
    assert len(members) == len(set(members))
    assert cp.classify_packages(packages) == {
        "optimus": "Optimus", "optimus_gateway": "Optimus", "optimus_security": "Optimus",
        "evidence_handoff": "A2A", "evidence_handoff_runtime": "A2A",
    }


def test_an_unknown_or_new_package_fails_closed_until_it_is_reviewed() -> None:
    with pytest.raises(cp.CoverageInputError, match="unreviewed package new_product"):
        cp.classify_packages(("optimus", "new_product"))


def test_a_package_claimed_by_two_products_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cp, "PRODUCTS", {**cp.PRODUCTS, "A2A": ("evidence_handoff", "optimus_security")})
    with pytest.raises(cp.CoverageInputError, match="optimus_security belongs to more than one product"):
        cp.classify_packages(("optimus_security",))


def test_the_coverage_data_source_lists_exactly_the_source_packages() -> None:
    """Bare `--cov` measures the configured source list; a package missing from it would vanish from every report."""
    configured = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["coverage"]["run"]["source"]
    assert sorted(path.removeprefix("src/") for path in configured) == list(cp.discover_packages(_ROOT))


# --- Product floors over complete data (pure) ----------------------------------------------------------------

def _row(statements: int, covered: int, branches: int = 0, covered_branches: int = 0) -> dict[str, object]:
    return {"summary": {"num_statements": statements, "covered_lines": covered, "num_branches": branches,
                        "covered_branches": covered_branches, "missing_lines": statements - covered,
                        "missing_branches": branches - covered_branches}}


def _data(rows: dict[str, dict[str, object]], *, branch: bool = True) -> dict[str, object]:
    return {"meta": {"format": 3, "version": "7.14.3", "timestamp": "2026-10-05T01:00:00", "branch_coverage": branch}, "files": rows}


def _evaluate(rows: dict[str, tuple[int, ...]], *, branch: bool = True) -> cp.CoverageVerdict:
    """Rows keyed `package/module.py` as (statements, covered[, branches, covered branches]); the current source
    holds exactly those files with those counts."""
    full = {path: (*values, 0, 0)[:4] for path, values in rows.items()}
    report = _data({f"src/{path}": _row(*values) for path, values in full.items()}, branch=branch)
    counts = {f"src/{path}": (values[0], values[2]) for path, values in full.items()}
    packages = sorted({path.split("/", 1)[0] for path in rows})
    files = {package: tuple(f"src/{path}" for path in rows if path.startswith(package + "/")) for package in packages}
    return cp.evaluate(report, counts, files)


def _status(verdict: cp.CoverageVerdict) -> dict[str, str]:
    return {product.name: product.status for product in verdict.products}


_A2A_LOW = {"evidence_handoff/a.py": (10, 1, 0, 0)}


def test_exactly_eighty_passes_and_just_below_fails_although_it_displays_as_eighty() -> None:
    exact = _evaluate({"optimus/a.py": (8000, 6400, 2000, 1600), **_A2A_LOW})
    assert exact.passed and _status(exact)["Optimus"] == "pass"
    below = _evaluate({"optimus/a.py": (8000, 6400, 2000, 1599), **_A2A_LOW})  # 79.99 %, shown as 80 % when rounded
    assert not below.passed and _status(below)["Optimus"] == "fail"
    assert f"{below.products[0].percent:.0f}" == "80" and below.products[0].percent < 80


def test_the_optimus_floor_is_over_all_its_packages_together() -> None:
    verdict = _evaluate({"optimus/a.py": (100, 100), "optimus_gateway/b.py": (100, 61), **_A2A_LOW})
    assert verdict.passed and verdict.products[0].percent == pytest.approx(80.5)


def test_model_policy_below_eighty_fails_even_when_the_optimus_aggregate_passes() -> None:
    verdict = _evaluate({"optimus/a.py": (1000, 1000), "optimus_model_policy/p.py": (100, 79), **_A2A_LOW})
    assert _status(verdict) == {"Optimus": "pass", "Model policy": "fail", "Context Engine": "n/a", "A2A": "informational"}
    assert not verdict.passed


def test_context_engine_below_eighty_fails_and_absent_future_products_are_not_applicable() -> None:
    absent = _evaluate({"optimus/a.py": (10, 9), **_A2A_LOW})
    assert absent.passed and _status(absent)["Context Engine"] == "n/a" and _status(absent)["Model policy"] == "n/a"
    present = _evaluate({"optimus/a.py": (10, 9), "context_engine/c.py": (100, 79), **_A2A_LOW})
    assert not present.passed and _status(present)["Context Engine"] == "fail"


def test_a2a_below_eighty_is_reported_but_never_changes_the_verdict() -> None:
    verdict = _evaluate({"optimus/a.py": (10, 9), "evidence_handoff/a.py": (100, 3), "evidence_handoff_runtime/b.py": (100, 0)})
    a2a = next(product for product in verdict.products if product.name == "A2A")
    assert verdict.passed and a2a.status == "informational" and not a2a.enforced and a2a.percent == pytest.approx(1.5)


def test_a_present_product_with_nothing_to_measure_fails() -> None:
    verdict = _evaluate({"optimus/a.py": (0, 0), **_A2A_LOW})
    assert not verdict.passed and "Optimus has no statements or branches to measure" in verdict.problems
    assert _status(verdict)["Optimus"] == "fail" and verdict.products[0].percent is None  # never shown as passing


# --- Complete, current data ----------------------------------------------------------------------------------

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
    verdict = _evaluate({"optimus/a.py": (10, 10)}, branch=False)
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


# --- Full-run binding (pure) ---------------------------------------------------------------------------------

_HEAD = "a" * 40
_UNIVERSE = ("tests/unit/test_a.py::test_one", "tests/unit/test_b.py::test_two[1]")


def _digest(nodes: tuple[str, ...]) -> str:
    found = hashlib.sha256()
    for node in sorted(nodes):
        found.update(run_context._node(node).encode("ascii"))  # noqa: SLF001
    return found.hexdigest()


def _identity(**changes: object) -> cp.SourceIdentity:
    values: dict[str, object] = {"head": _HEAD, "config_sha256": "c" * 64, "lock_sha256": "d" * 64, "universe": _UNIVERSE, "clean": True,
                                 "latest_change": ("src/optimus/a.py", "2026-10-05T00:40:00+00:00")}
    values.update(changes)
    return cp.SourceIdentity(**values)  # type: ignore[arg-type]


def _full_run(**changes: object) -> dict[str, object]:
    record: dict[str, object] = {
        "schema": "test-run-context-v1", "root": {"pid": 522, "creation_time": None},
        "checkpoint": "terminal", "run_id": "20261005T010000-522-b5f07d", "mode": "active", "reason": "default_selection",
        "platform": "linux", "head": _HEAD, "config_sha256": "c" * 64, "lock_sha256": "d" * 64,
        "started_utc": "2026-10-05T00:50:00+00:00", "finished_utc": "2026-10-05T01:10:00+00:00",
        "completeness": "COMPLETE", "exit_status": 0, "collection_errors": 0,
        "selected": len(_UNIVERSE), "selection_sha256": _digest(_UNIVERSE),
        "native": {"supported": False, "attempted": False, "enrolled": False}, "guard_mode": "unsupported_platform",
        "protection": "none", "parent_run": {"status": "unsupported"},
    }
    record.update(changes)
    return record


def _meta(at: datetime) -> dict[str, object]:
    return {"branch_coverage": True, "timestamp": at.astimezone().replace(tzinfo=None).isoformat()}


_DURING = datetime(2026, 10, 5, 1, 9, tzinfo=timezone.utc)


def test_coverage_from_the_full_default_run_of_this_source_is_accepted() -> None:
    assert cp.full_run_problems(_full_run(), _meta(_DURING), _identity()) == []


@pytest.mark.parametrize(("changes", "identity", "problem"), [
    ({"completeness": "INVALID"}, {}, "the run's own record cannot support a result: records_INVALID"),
    ({"reason": "explicit_targets"}, {}, "the run was not the default selection (explicit_targets)"),
    ({"selected": 1, "selection_sha256": _digest(_UNIVERSE[:1])}, {}, "the run did not select the current default universe (1 of 2 tests)"),
    ({"selection_sha256": _digest(("tests/unit/test_c.py::test_other", _UNIVERSE[1]))}, {}, "the run did not select the current default universe (2 of 2 tests)"),
    ({"exit_status": 1}, {}, "the run's own record cannot support a result: exit_status_differs"),
    ({}, {"head": "b" * 40}, f"the run measured commit {_HEAD}, not the current HEAD {'b' * 40}"),
    ({}, {"config_sha256": "e" * 64}, "the run used a different pyproject.toml"),
    ({}, {"lock_sha256": "e" * 64}, "the run used a different uv.lock"),
    ({}, {"clean": False}, "the source, tests or configuration have uncommitted changes, so the run's commit does not identify them"),
    # A dirty run, then `git stash` / `checkout` / `restore`: the tree is clean again, but the files were rewritten.
    ({}, {"latest_change": ("src/optimus/a.py", "2026-10-05T00:55:00+00:00")},
     "src/optimus/a.py changed at 2026-10-05 00:55:00+00:00, after the run started, so the run may have measured other bytes"),
])
def test_partial_failed_or_source_mismatched_runs_are_rejected(changes: dict[str, object], identity: dict[str, object], problem: str) -> None:
    assert problem in cp.full_run_problems(_full_run(**changes), _meta(_DURING), _identity(**identity))


@pytest.mark.parametrize("at", [datetime(2026, 10, 5, 0, 49, tzinfo=timezone.utc), datetime(2026, 10, 5, 1, 20, tzinfo=timezone.utc)])
def test_coverage_written_outside_the_run_is_not_that_run_s_data(at: datetime) -> None:
    problems = cp.full_run_problems(_full_run(), _meta(at), _identity())
    assert any(problem.startswith("the coverage data was written at") for problem in problems)


def test_the_report_is_bound_to_the_one_full_run_that_wrote_it(tmp_path: Path) -> None:
    """Nested sessions run inside the full run's window, and other days' full runs remain on disk; only the largest
    default-selection run containing the report's write time is its run, and a tie is no answer."""
    def plant(name: str, **changes: object) -> Path:
        folder = tmp_path / "tmp" / "test-runs" / name
        folder.mkdir(parents=True)
        (folder / "run.json").write_text(json.dumps(_full_run(**changes)), encoding="utf-8")
        return folder / "run.json"

    full = plant("full", selected=5000)
    plant("nested", selected=1)
    plant("yesterday", selected=6000, started_utc="2026-10-04T00:50:00+00:00", finished_utc="2026-10-04T01:10:00+00:00")
    plant("collection", selected=5000, reason="collection_only")
    report = tmp_path / "coverage.json"
    report.write_text(json.dumps({"meta": _meta(_DURING), "files": {}}), encoding="utf-8")
    assert cp.find_full_run(tmp_path, report) == full
    plant("twin", selected=5000)
    assert cp.find_full_run(tmp_path, report) is None


# --- Full evaluation over a real repository ------------------------------------------------------------------

def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def test_a_real_repository_s_current_full_run_data_is_evaluated_end_to_end(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    for package in ("optimus", "evidence_handoff"):
        (root / "src" / package).mkdir(parents=True)
        (root / "src" / package / "__init__.py").write_text("", encoding="utf-8")
        (root / "src" / package / "core.py").write_text("def one(flag):\n    if flag:\n        return 1\n    return 0\n", encoding="utf-8")
    (root / "src" / "optimus_cost_agent.egg-info").mkdir()
    (root / "pyproject.toml").write_text('[tool.coverage.run]\nbranch = true\nsource = ["src/optimus", "src/evidence_handoff"]\n', encoding="utf-8")
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    _git(root.parent, "init", "-q", str(root))
    _git(root, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "add", ".")
    _git(root, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-q", "-m", "seed")
    files = {}
    for package in ("optimus", "evidence_handoff"):
        for name in ("__init__.py", "core.py"):
            statements, branches = cp.source_counts(root / "src" / package / name, root / "pyproject.toml")
            files[f"src/{package}/{name}"] = _row(statements, statements, branches, branches)
    started = datetime.now(timezone.utc) + timedelta(seconds=1)  # the run starts after the source was written
    report_path = tmp_path / "coverage.json"
    report_path.write_text(json.dumps({"meta": _meta(started + timedelta(minutes=10)), "files": files}), encoding="utf-8")
    record = _full_run(head=_git(root, "rev-parse", "HEAD"), config_sha256=hashlib.sha256((root / "pyproject.toml").read_bytes()).hexdigest(),
                       lock_sha256=hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest(),
                       started_utc=started.isoformat(), finished_utc=(started + timedelta(minutes=20)).isoformat())
    record_path = tmp_path / "run.json"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    verdict = cp.evaluate_products(report_path, cp.discover_packages(root), record_path, root=root, universe=_UNIVERSE)
    assert verdict.problems == () and verdict.passed and _status(verdict)["Optimus"] == "pass"
    core = root / "src" / "optimus" / "core.py"
    core.write_text("def one(flag):\n    return 1 if flag else 0\n", encoding="utf-8")
    os.utime(core, (started.timestamp() + 60, started.timestamp() + 60))  # edited during the run
    drifted = cp.evaluate_products(report_path, cp.discover_packages(root), record_path, root=root, universe=_UNIVERSE)
    assert not drifted.passed and any("the current source has" in problem for problem in drifted.problems)
    assert any("uncommitted changes" in problem for problem in drifted.problems)
    # The edit is reverted (`git checkout`, `git stash`): clean again, same counts, but rewritten after the run began.
    _git(root, "checkout", "--", "src/optimus/core.py")
    os.utime(core, (started.timestamp() + 120, started.timestamp() + 120))
    reverted = cp.evaluate_products(report_path, cp.discover_packages(root), record_path, root=root, universe=_UNIVERSE)
    assert reverted.problems == (
        f"src/optimus/core.py changed at {datetime.fromtimestamp(started.timestamp() + 120, timezone.utc)}, after the run started, "
        "so the run may have measured other bytes",)


# --- What the tool prints ------------------------------------------------------------------------------------

def test_printed_problems_pass_the_shared_sanitizer(capsys: pytest.CaptureFixture[str]) -> None:
    cp._print_verdict(cp.CoverageVerdict((), ("src/optimus/x.py: from http://user:hunter2@example.invalid",)))  # noqa: SLF001  # pragma: allowlist secret - synthetic credential-shaped text the sanitizer must mask
    printed = capsys.readouterr().out
    assert printed.startswith("coverage-products: problem: src/optimus/x.py") and "hunter2" not in printed


def test_an_input_failure_line_passes_the_shared_sanitizer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def unreadable(*args: object, **kwargs: object) -> cp.CoverageVerdict:
        raise ValueError("unreadable http://user:hunter2@example.invalid")  # pragma: allowlist secret - synthetic credential-shaped text the sanitizer must mask

    monkeypatch.setattr(cp, "evaluate_products", unreadable)
    assert cp.main(["report", "--coverage-json", str(tmp_path / "coverage.json"), "--run-record", str(tmp_path / "run.json")]) == cp.EXIT_INPUT
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
    missing = _safety()
    del missing["files"][cp.SAFETY_MODULES[2]]  # type: ignore[union-attr]
    assert cp.compare_safety_rows(_safety(), missing) == [f"{cp.SAFETY_MODULES[2]}: no row in the candidate report"]
    other_tool = _safety()
    other_tool["meta"] = {**other_tool["meta"], "version": "7.0.0"}  # type: ignore[dict-item]
    assert cp.compare_safety_rows(_safety(), other_tool) == ["the reports were made by different coverage versions (7.14.3, 7.0.0)"]


def test_the_safety_comparison_names_the_two_reports_it_compared(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The comparison cannot see platform, interpreter or source SHA, so its output binds the exact report files for
    the evidence that names their CI runs."""
    base, candidate = tmp_path / "base.json", tmp_path / "candidate.json"
    base.write_text(json.dumps(_safety()), encoding="utf-8")
    candidate.write_text(json.dumps(_safety(**{cp.SAFETY_MODULES[0]: (100, 99, 20, 20)})), encoding="utf-8")
    assert cp.main(["compare", "--base", str(base), "--candidate", str(candidate)]) == cp.EXIT_PASS
    printed = capsys.readouterr().out
    assert all(hashlib.sha256(path.read_bytes()).hexdigest() in printed for path in (base, candidate))


def test_the_safety_modules_are_the_seven_named_optimus_files() -> None:
    assert cp.SAFETY_MODULES == (
        "src/optimus/tools/registry.py", "src/optimus/runtime/mutation.py", "src/optimus/gateway/models.py",
        "src/optimus/evidence/ledger.py", "src/optimus/acp/framing.py", "src/optimus/retry/policy.py", "src/optimus/tools/policy.py",
    )
    assert all((_ROOT / path).is_file() for path in cp.SAFETY_MODULES)
