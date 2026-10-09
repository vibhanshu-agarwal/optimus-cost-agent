"""Plan 12.2 closure: the product coverage gate checks separate floors on one full-suite dataset.

Datasets here are written with coverage's own data API (line data), never by tracing inside this
test process, and run mode's pytest launch is an injected stand-in: no nested suite runs. Each stand-in
repository is a real Git checkout because the gate inventories `src/` from the Git index.
"""

from __future__ import annotations

import json
import platform
import shlex
import subprocess
import textwrap
from pathlib import Path

import coverage
import pytest
import yaml
from coverage import CoverageData

from tools import check_product_coverage as gate
from tools.check_product_coverage import CoverageGateError

REPO_ROOT = Path(__file__).resolve().parents[3]

GROUPS = {
    "schema_version": 1,
    "groups": [
        {"name": "product", "packages": ["alpha", "alpha_extra"], "floor": 80, "enforced": True},
        {"name": "engine", "packages": ["beta"], "floor": 80, "enforced": True},
        {"name": "evidence", "packages": ["gamma"], "floor": 80, "enforced": False},
    ],
    "package_floors": [{"package": "alpha_extra", "floor": 80, "enforced": True}],
    "aggregate": {"floor": 80, "enforced": False},
}


def _module(path: Path, statements: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"value_{i} = {i}\n" for i in range(statements)), encoding="utf-8")
    return path


def track(repo: Path) -> None:
    """Record the stand-in repository's current files in its Git index (the gate's inventory)."""
    if not (repo / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)


def make_repo(tmp_path: Path, groups: dict | None = None) -> Path:
    repo = tmp_path / "repo"
    src = repo / "src"
    (src / "alpha").mkdir(parents=True)
    (src / "alpha" / "__init__.py").write_text("", encoding="utf-8")
    _module(src / "alpha" / "big.py", 90)
    _module(src / "alpha_extra" / "__init__.py", 0)
    _module(src / "alpha_extra" / "small.py", 10)
    _module(src / "beta" / "ns_module.py", 10)  # a namespace package: no __init__.py
    _module(src / "gamma" / "__init__.py", 0)
    _module(src / "gamma" / "handoff.py", 10)
    sources = ", ".join(f'"src/{name}"' for name in ("alpha", "alpha_extra", "beta", "gamma"))
    (repo / "pyproject.toml").write_text(
        textwrap.dedent(
            f"""\
            [tool.coverage.run]
            branch = false
            source = [{sources}]

            [tool.coverage.report]
            fail_under = 80
            """
        ),
        encoding="utf-8",
    )
    (repo / "groups.json").write_text(json.dumps(groups or GROUPS), encoding="utf-8")
    track(repo)
    return repo


def write_data(repo: Path, executed: dict[str, int], *, touched: tuple[str, ...] = ()) -> Path:
    """`executed` maps a src-relative file to how many of its first lines ran; `touched` files are in
    the dataset as unexecuted, as coverage records never-imported files under configured sources."""
    data = CoverageData(basename=str(repo / ".coverage"))
    src = repo / "src"
    data.add_lines({str((src / name).resolve()): range(1, count + 1) for name, count in executed.items()})
    data.touch_files([str((src / name).resolve()) for name in touched])
    data.write()
    return repo / ".coverage"


ALL_FILES = ("alpha/__init__.py", "alpha/big.py", "alpha_extra/__init__.py", "alpha_extra/small.py", "beta/ns_module.py", "gamma/__init__.py", "gamma/handoff.py")


def floors(report: dict) -> dict[str, tuple[float, bool]]:
    return {row["name"]: (row["percent"], row["passed"]) for row in report["floors"]}


def test_a_low_required_package_fails_despite_a_high_aggregate(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    data = write_data(repo, {"alpha/big.py": 90, "alpha_extra/small.py": 10, "beta/ns_module.py": 2, "gamma/handoff.py": 10}, touched=ALL_FILES)

    report = gate.report_dataset(data, gate.load_groups(repo / "groups.json"), repo=repo)

    rows = floors(report)
    assert rows["aggregate"][0] > 80 and rows["aggregate"][1]
    assert rows["engine"] == (20.0, False)
    assert gate.verdict({"pytest_exit": 0}, report, None)["failures"] == ["engine 20.0% < 80.0%"]


def test_an_include_pattern_selects_its_package_only(tmp_path: Path) -> None:
    """`alpha` must not swallow `alpha_extra` (as `optimus` must not swallow `optimus_gateway`)."""
    repo = make_repo(tmp_path)
    data = write_data(repo, {"alpha/big.py": 90, "alpha_extra/small.py": 0, "beta/ns_module.py": 10, "gamma/handoff.py": 10}, touched=ALL_FILES)

    rows = floors(gate.report_dataset(data, gate.load_groups(repo / "groups.json"), repo=repo))

    assert rows["product"] == (90.0, True) and rows["alpha_extra"] == (0.0, False)


def test_a_never_imported_file_counts_and_one_missing_from_the_data_is_refused(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    config = gate.load_groups(repo / "groups.json")
    data = write_data(repo, {"alpha/big.py": 90, "alpha_extra/small.py": 10, "beta/ns_module.py": 10}, touched=ALL_FILES)
    assert floors(gate.report_dataset(data, config, repo=repo))["evidence"] == (0.0, False)  # unexecuted, still measured

    data = write_data(repo, {"alpha/big.py": 90, "alpha_extra/small.py": 10, "beta/ns_module.py": 10})
    with pytest.raises(CoverageGateError, match="missing from the dataset"):
        gate.report_dataset(data, config, repo=repo)


def test_an_informational_group_below_its_floor_never_fails_the_gate(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    data = write_data(repo, {"alpha/big.py": 90, "alpha_extra/small.py": 10, "beta/ns_module.py": 10, "gamma/handoff.py": 3}, touched=ALL_FILES)

    report = gate.report_dataset(data, gate.load_groups(repo / "groups.json"), repo=repo)

    assert floors(report)["evidence"] == (30.0, False)  # recorded as below its floor, never as a pass
    assert gate.verdict({"pytest_exit": 0}, report, None) == {"passed": True, "failures": []}


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda g: g["groups"][2]["packages"].remove("gamma"), "in no product group"),
        (lambda g: g["groups"][1]["packages"].append("alpha"), "more than one group"),
        (lambda g: g["groups"][2]["packages"].append("delta"), "not in src"),
        (lambda g: g["package_floors"].append({"package": "delta", "floor": 80, "enforced": True}), "belongs to a group"),
        (lambda g: g["groups"][0].update(floor=101), "floor"),
        (lambda g: g["groups"][0].update(enforced="yes"), "enforced"),
    ],
    ids=["unmapped", "duplicate", "stale", "unknown-package-floor", "bad-floor", "bad-enforced"],
)
def test_every_src_package_maps_to_exactly_one_group(tmp_path: Path, change, message: str) -> None:
    groups = json.loads(json.dumps(GROUPS))
    change(groups)
    repo = make_repo(tmp_path, groups)

    with pytest.raises(CoverageGateError, match=message):
        config = gate.load_groups(repo / "groups.json")
        gate.validate_inventory(config, gate.discover_packages(gate.tracked_sources(repo)), gate.configured_sources(repo / "pyproject.toml"))


def test_namespace_packages_are_discovered_from_the_git_index_only(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "src" / "notes").mkdir()
    (repo / "src" / "notes" / "README.md").write_text("no Python here", encoding="utf-8")
    track(repo)
    _module(repo / "src" / "scratch" / "wip.py", 1)  # untracked: never a package of the repository

    assert gate.discover_packages(gate.tracked_sources(repo)) == ("alpha", "alpha_extra", "beta", "gamma")


def test_the_inventory_fails_closed_outside_a_git_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    plain = tmp_path / "plain"
    _module(plain / "src" / "alpha" / "a.py", 1)

    with pytest.raises(CoverageGateError, match="cannot list the tracked src files"):
        gate.tracked_sources(plain)


def test_a_top_level_src_module_is_refused(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    _module(repo / "src" / "stray.py", 1)
    track(repo)

    with pytest.raises(CoverageGateError, match="stray.py"):
        gate.discover_packages(gate.tracked_sources(repo))


@pytest.mark.parametrize(
    ("statements", "executed", "compared", "passed"),
    [(10000, 7949, "79", False), (200, 159, "80", True), (200, 158, "79", False), (200, 160, "80", True)],
    ids=["79.49", "79.5-compares-as-80", "79.0", "80"],
)
def test_the_floor_comparison_is_coverages_own_fail_under_rule(tmp_path: Path, statements: int, executed: int, compared: str, passed: bool) -> None:
    """The rule pytest-cov's `--cov-fail-under`, pyproject's `fail_under` and `coverage report
    --fail-under` apply: the total rounded to the configured precision (0 here; Python's `round`, ties
    to even) against the floor. The measured value is kept beside the compared one."""
    repo = make_repo(tmp_path)
    (repo / "src" / "beta" / "ns_module.py").unlink()
    _module(repo / "src" / "beta" / "wide.py", statements)
    track(repo)
    files = (*(name for name in ALL_FILES if name != "beta/ns_module.py"), "beta/wide.py")
    executed_lines = {**{name: count for name, count in FULL.items() if name != "beta/ns_module.py"}, "beta/wide.py": executed}

    report = gate.report_dataset(write_data(repo, executed_lines, touched=files), gate.load_groups(repo / "groups.json"), repo=repo)

    [row] = [row for row in report["floors"] if row["name"] == "engine"]
    assert (row["percent"], row["compared"], row["passed"]) == (pytest.approx(100 * executed / statements), compared, passed)
    assert report["precision"] == 0
    failures = gate.verdict({"pytest_exit": 0}, report, None)["failures"]
    assert failures == ([] if passed else [f"engine {row['percent']}% < 80.0%"])


def test_the_repository_coverage_configuration_resolves_to_precision_zero() -> None:
    """The canonical comparison is at precision 0 because the repository sets none (coverage's default);
    a precision setting added later would change every floor decision and must fail here first."""
    assert coverage.Coverage(config_file=str(REPO_ROOT / "pyproject.toml")).config.precision == 0


def test_configured_sources_must_be_exactly_the_src_packages(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    config = gate.load_groups(repo / "groups.json")

    with pytest.raises(CoverageGateError, match="missing .*src/gamma"):
        gate.validate_inventory(config, gate.discover_packages(gate.tracked_sources(repo)), ("src/alpha", "src/alpha_extra", "src/beta"))


def _stand_in(repo: Path, exit_code: int, executed: dict[str, int]):
    calls: list[list[str]] = []

    def runner(command, cwd):
        calls.append(list(command))
        assert cwd == repo
        write_data(repo, executed, touched=ALL_FILES)
        return exit_code

    return runner, calls


FULL = {"alpha/big.py": 90, "alpha_extra/small.py": 10, "beta/ns_module.py": 10, "gamma/handoff.py": 10}


def test_run_mode_launches_the_one_fixed_selection_and_keeps_its_true_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))  # the stand-in repo is no git checkout
    repo = make_repo(tmp_path)
    (repo / ".coverage.stale").write_text("old", encoding="utf-8")
    (repo / ".coveragerc").write_text("[run]\n", encoding="utf-8")
    runner, calls = _stand_in(repo, 1, FULL)
    report_path = tmp_path / "out" / "report.json"

    exit_code = gate.main(["--run-full-suite", "--groups", str(repo / "groups.json"), "--report-json", str(report_path)], runner=runner, repo=repo)

    assert exit_code == 1
    [command] = calls
    assert tuple(command[1:]) == gate.FULL_SUITE_ARGS
    assert not (repo / ".coverage.stale").exists() and (repo / ".coveragerc").exists()
    result = json.loads(report_path.read_text(encoding="utf-8"))
    assert result["run"]["pytest_exit"] == 1 and result["verdict"]["failures"] == ["full suite exit 1"]
    assert (result["run"]["git_head"], result["run"]["worktree_dirty"]) == (None, None)
    assert all(row["passed"] for row in result["coverage"]["floors"])  # floors met, the failed suite still fails


def test_report_mode_needs_the_identified_dataset(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runner, _ = _stand_in(repo, 0, FULL)
    report_path = tmp_path / "out" / "report.json"
    assert gate.main(["--run-full-suite", "--groups", str(repo / "groups.json"), "--report-json", str(report_path)], runner=runner, repo=repo) == 0
    record = report_path.with_suffix(".run.json")

    args = ["--data-file", str(repo / ".coverage"), "--run-record", str(record), "--groups", str(repo / "groups.json"), "--report-json", str(tmp_path / "again.json")]
    assert gate.main(args, repo=repo) == 0

    write_data(repo, {"alpha/big.py": 1}, touched=ALL_FILES)  # a different dataset than the run recorded
    assert gate.main(args, repo=repo) == 1
    assert "stale or foreign" in json.loads((tmp_path / "again.json").read_text(encoding="utf-8"))["verdict"]["failures"][0]

    (repo / ".coverage").unlink()
    assert gate.main(args, repo=repo) == 1


@pytest.mark.parametrize(
    "argv",
    [
        ["--run-full-suite", "--data-file", "x"],
        ["--run-full-suite", "--run-record", "x"],
        ["--data-file", "x"],
        [],
    ],
    ids=["both-modes", "record-with-run", "data-without-record", "no-mode"],
)
def test_contradictory_or_incomplete_modes_are_rejected(tmp_path: Path, argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        gate.main([*argv, "--groups", "g.json", "--report-json", str(tmp_path / "r.json")], repo=tmp_path)
    assert exit_info.value.code == 2


def test_a_run_record_names_the_checkout_it_measured() -> None:
    identity = gate.candidate_identity(REPO_ROOT)
    assert len(str(identity["git_head"])) == 40 and isinstance(identity["worktree_dirty"], bool)
    assert len(str(identity["git_tree"])) == 40


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def committed_repo(tmp_path: Path) -> Path:
    """A stand-in repository with one commit, whose gate outputs are ignored as the real repository's are."""
    repo = make_repo(tmp_path)
    (repo / ".gitignore").write_text(".coverage\n.coverage.*\n", encoding="utf-8")
    (repo / "notes.txt").write_text("tracked, outside src\n", encoding="utf-8")
    track(repo)
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "base")
    return repo


def test_the_same_dataset_is_exported_as_repository_relative_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path)
    monkeypatch.chdir(repo)  # the gate runs from the repository root, as CI does
    out = tmp_path / "out" / "coverage.json"

    report = gate.report_dataset(write_data(repo, FULL, touched=ALL_FILES), gate.load_groups(repo / "groups.json"), repo=repo, json_out=out)

    exported = json.loads(out.read_text(encoding="utf-8"))
    assert sorted(name.replace("\\", "/") for name in exported["files"]) == sorted(f"src/{name}" for name in ALL_FILES)
    big = next(row for name, row in exported["files"].items() if name.replace("\\", "/") == "src/alpha/big.py")["summary"]
    assert (big["num_statements"], big["covered_lines"], big["missing_lines"]) == (90, 90, 0)
    assert report["coverage_json_sha256"] == gate._sha256(out) and floors(report)["engine"] == (100.0, True)


def test_json_rows_that_are_not_repository_relative_fail_the_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path)
    monkeypatch.chdir(tmp_path)  # outside the repository root: rows would be keyed "repo/src/..."

    with pytest.raises(CoverageGateError, match="repository-relative"):
        gate.report_dataset(write_data(repo, FULL, touched=ALL_FILES), gate.load_groups(repo / "groups.json"), repo=repo, json_out=tmp_path / "c.json")


def test_a_dataset_that_cannot_be_exported_fails_the_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path)
    monkeypatch.chdir(repo)
    runner, _ = _stand_in(repo, 0, FULL)
    blocked = tmp_path / "blocked"
    blocked.mkdir()  # a folder where the JSON file should be: the export cannot write it
    report_path = tmp_path / "out" / "report.json"

    exit_code = gate.main(["--run-full-suite", "--groups", str(repo / "groups.json"), "--report-json", str(report_path), "--coverage-json", str(blocked)], runner=runner, repo=repo)

    assert exit_code == 1
    [failure] = json.loads(report_path.read_text(encoding="utf-8"))["verdict"]["failures"]
    assert failure.startswith("cannot export the coverage JSON report: ")  # the OSError subclass differs by platform


def test_an_older_json_is_removed_before_the_gate_measures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    groups = {**GROUPS, "groups": GROUPS["groups"][:2]}  # gamma unmapped: the gate fails before any run
    repo = make_repo(tmp_path, groups)
    monkeypatch.chdir(repo)
    runner, calls = _stand_in(repo, 0, FULL)
    out = tmp_path / "out" / "coverage.json"
    out.parent.mkdir()
    out.write_text("{}", encoding="utf-8")  # an earlier run's export

    exit_code = gate.main(["--run-full-suite", "--groups", str(repo / "groups.json"), "--report-json", str(tmp_path / "out" / "r.json"), "--coverage-json", str(out)], runner=runner, repo=repo)

    assert (exit_code, calls, out.exists()) == (1, [], False)  # no older export can pass as this run's


def test_a_failed_suite_still_exports_its_data_and_receipts_and_keeps_its_verdict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path)  # git-initialised but never committed: HEAD is unborn, so identity is unknown
    monkeypatch.chdir(repo)
    runner, _ = _stand_in(repo, 1, FULL)
    report_path = tmp_path / "out" / "report.json"
    out = tmp_path / "out" / "coverage.json"

    exit_code = gate.main(["--run-full-suite", "--groups", str(repo / "groups.json"), "--report-json", str(report_path), "--coverage-json", str(out)], runner=runner, repo=repo)

    assert exit_code == 1
    result = json.loads(report_path.read_text(encoding="utf-8"))
    assert result["verdict"] == {"passed": False, "failures": ["full suite exit 1"]}
    assert result["coverage"]["coverage_json_sha256"] == gate._sha256(out)
    record = json.loads(report_path.with_suffix(".run.json").read_text(encoding="utf-8"))
    assert record == result["run"] and record["schema"] == gate.RUN_RECORD_SCHEMA
    assert record["coverage_version"] == coverage.__version__ and record["uv_lock_sha256"] is None
    assert record["pyproject_sha256"] == gate._sha256(repo / "pyproject.toml")
    assert record["coverage_config"]["run"]["source"] == ["src/alpha", "src/alpha_extra", "src/beta", "src/gamma"]
    assert record["python_version"] and record["platform"]
    assert record["python_implementation"] == platform.python_implementation()
    assert (record["groups_path"], record["groups_sha256"]) == ("groups.json", gate._sha256(repo / "groups.json"))
    unknown = ("git_head", "git_tree", "worktree_dirty", "git_head_after", "git_tree_after", "worktree_dirty_after")
    assert {key: record[key] for key in unknown} == dict.fromkeys(unknown)


def test_a_run_record_names_the_clean_checkout_before_and_after_the_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = committed_repo(tmp_path)
    monkeypatch.chdir(repo)
    runner, _ = _stand_in(repo, 0, FULL)
    report_path = tmp_path / "out" / "report.json"

    assert gate.main(["--run-full-suite", "--groups", str(repo / "groups.json"), "--report-json", str(report_path)], runner=runner, repo=repo) == 0

    record = json.loads(report_path.with_suffix(".run.json").read_text(encoding="utf-8"))
    head, tree = _git(repo, "rev-parse", "HEAD"), _git(repo, "rev-parse", "HEAD^{tree}")
    assert (record["git_head"], record["git_tree"], record["worktree_dirty"]) == (head, tree, False)
    assert (record["git_head_after"], record["git_tree_after"], record["worktree_dirty_after"]) == (head, tree, False)
    assert record["started"] <= record["finished"]


@pytest.mark.parametrize("written", ["notes.txt", "scratch.txt"], ids=["tracked-edit", "untracked-file"])
def test_a_change_to_the_checkout_during_the_run_is_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, written: str) -> None:
    repo = committed_repo(tmp_path)
    monkeypatch.chdir(repo)
    runner, _ = _stand_in(repo, 0, FULL)

    def editing(command, cwd):
        (repo / written).write_text("written while the suite ran\n", encoding="utf-8")  # outside src, not ignored
        return runner(command, cwd)

    report_path = tmp_path / "out" / "report.json"
    gate.main(["--run-full-suite", "--groups", str(repo / "groups.json"), "--report-json", str(report_path)], runner=editing, repo=repo)

    record = json.loads(report_path.with_suffix(".run.json").read_text(encoding="utf-8"))
    assert (record["worktree_dirty"], record["worktree_dirty_after"]) == (False, True)
    assert record["git_head_after"] == record["git_head"]


def test_a_commit_during_the_run_is_recorded_even_when_the_tree_is_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = committed_repo(tmp_path)
    monkeypatch.chdir(repo)
    runner, _ = _stand_in(repo, 0, FULL)

    def committing(command, cwd):
        _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "--allow-empty", "-m", "moved")
        return runner(command, cwd)

    report_path = tmp_path / "out" / "report.json"
    gate.main(["--run-full-suite", "--groups", str(repo / "groups.json"), "--report-json", str(report_path)], runner=committing, repo=repo)

    record = json.loads(report_path.with_suffix(".run.json").read_text(encoding="utf-8"))
    assert record["git_head_after"] != record["git_head"] and record["git_tree_after"] == record["git_tree"]


def test_a_groups_policy_outside_the_repository_is_named_by_its_absolute_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = committed_repo(tmp_path)
    monkeypatch.chdir(repo)
    outside = tmp_path / "elsewhere" / "groups.json"
    outside.parent.mkdir()
    outside.write_bytes((repo / "groups.json").read_bytes())
    runner, _ = _stand_in(repo, 0, FULL)
    report_path = tmp_path / "out" / "report.json"

    gate.main(["--run-full-suite", "--groups", str(outside), "--report-json", str(report_path)], runner=runner, repo=repo)

    record = json.loads(report_path.with_suffix(".run.json").read_text(encoding="utf-8"))
    assert (record["groups_path"], record["groups_sha256"]) == (outside.resolve().as_posix(), gate._sha256(outside))


def test_ci_keeps_the_one_full_run_and_uploads_its_evidence_even_when_it_fails() -> None:
    steps = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "guardrails.yml").read_text(encoding="utf-8"))["jobs"]["clean-environment-recheck"]["steps"]
    names = [step.get("name") for step in steps]
    position = names.index("optimus-check: pytest-coverage")
    gate_step, copy, upload = steps[position : position + 3]
    assert (copy["name"], upload["name"]) == ("Keep the full run's run-context records", "Upload product coverage evidence")
    assert shlex.split(gate_step["run"]) == [
        "uv", "run", "python", "tools/check_product_coverage.py", "--run-full-suite", "--groups", "tools/product-coverage-groups.json",
        "--report-json", "${RUNNER_TEMP}/product-coverage/product-coverage-report.json",
        "--coverage-json", "${RUNNER_TEMP}/product-coverage/coverage.json",
    ]
    assert [step for step in steps if "pytest" in str(step.get("run", ""))] == []  # no second suite exports the JSON
    assert copy["if"] == upload["if"] == "${{ !cancelled() }}"
    assert copy["run"] == 'mkdir -p "${RUNNER_TEMP}/product-coverage/test-runs" && cp --parents tmp/test-runs/*/run.json "${RUNNER_TEMP}/product-coverage/test-runs/"'
    assert upload["uses"].startswith("actions/upload-artifact@")
    assert upload["with"] == {
        "name": "product-coverage-${{ github.sha }}-${{ github.run_attempt }}",
        "path": "${{ runner.temp }}/product-coverage/",
        "if-no-files-found": "error",
    }


def test_the_repository_groups_cover_the_real_src_packages_exactly() -> None:
    config = gate.load_groups(REPO_ROOT / "tools" / "product-coverage-groups.json")
    gate.validate_inventory(config, gate.discover_packages(gate.tracked_sources(REPO_ROOT)), gate.configured_sources(REPO_ROOT / "pyproject.toml"))
    required = {row.name: (row.packages, row.floor, row.enforced) for row in (*config.groups, *config.package_floors)}
    assert required["optimus"] == (("optimus", "optimus_gateway", "optimus_security", "optimus_model_policy"), 80.0, True)
    assert required["context_engine"] == (("context_engine",), 80.0, True)
    assert required["optimus_model_policy"] == (("optimus_model_policy",), 80.0, True)
    assert required["evidence_handoff"][2] is False and config.aggregate.enforced is False
