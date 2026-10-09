"""Product coverage gate: one full-suite dataset, separate floors (Plan 12.2 closure, CP4).

The settled floors (operator decision; Test Strategy section 8A successor) are checked independently
on one dataset: the Optimus product group, `context_engine` and `optimus_model_policy` each at 80%.
Evidence Handoff is reported against its 80% threshold for information only, and so is the all-source
aggregate. Every top-level `src/` package, namespace packages included, belongs to exactly one group.

Run mode (final CP4 verification and CI): ``--run-full-suite`` starts exactly one approved full pytest
selection with the configured coverage sources, keeps its true exit, then reports that dataset. It
takes no pytest arguments, so it cannot narrow the selection; the root conftest and test-run context
apply unchanged. Report mode: ``--data-file`` with the ``--run-record`` that run mode wrote reports an
already identified full-suite dataset without rerunning tests; a dataset whose hash no longer matches
its record is stale and refused.

``--coverage-json`` (either mode) also writes coverage.py's own JSON report of the same loaded dataset:
per-file statement/branch totals and misses keyed by repository-relative ``src/`` paths, for the base
and candidate safety-module comparison (Plan 11.30 v5 I1). It is never a second test run; a dataset that
cannot be exported, or rows that are not repository-relative, fail the gate. The run record also carries
the commit and tree before and after the run, whether the checkout was clean before and after, the
groups policy loaded, and the configuration, lock, coverage engine and interpreter identities: receipts
for a later validity check, which this gate's own verdict neither uses nor replaces.

The commit-profile hook is not this gate: until the profiles lane lands it keeps its existing entry and
pyproject's interim Optimus-only floor (release supplement, 2026-10-04).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import platform
import subprocess
import sys
import time
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # run as a script (CI): make the repository's `tools` importable
    sys.path.insert(0, str(REPO_ROOT))

from tools.tracked_repository_files import TrackedFileInventoryError, tracked_repository_files  # noqa: E402

GROUPS_SCHEMA_VERSION = 1
RUN_RECORD_SCHEMA = "plan12-product-coverage-run-v1"
# The one approved full selection: the repository's own addopts and markers, the configured coverage
# sources (so files never imported are measured as unexecuted), and no fail-under of pytest-cov's own:
# the aggregate is informational and the floors are checked below.
FULL_SUITE_ARGS = ("-m", "pytest", "--cov", "--cov-branch", "--cov-fail-under=0", "--cov-report=term-missing", "-q")


class CoverageGateError(Exception):
    """A configuration, inventory or dataset problem: the gate fails, never reports a pass."""


@dataclass(frozen=True)
class Floor:
    name: str
    packages: tuple[str, ...]
    floor: float
    enforced: bool


@dataclass(frozen=True)
class GroupsConfig:
    groups: tuple[Floor, ...]
    package_floors: tuple[Floor, ...]
    aggregate: Floor


def _floor(raw: object, *, where: str) -> Floor:
    if not isinstance(raw, dict) or set(raw) - {"name", "packages", "package", "floor", "enforced"}:
        raise CoverageGateError(f"{where}: unknown or malformed entry")
    packages = raw.get("packages", [raw["package"]] if "package" in raw else [])
    name = raw.get("name", raw.get("package"))
    floor, enforced = raw.get("floor"), raw.get("enforced")
    if not isinstance(name, str) or not name:
        raise CoverageGateError(f"{where}: an entry needs a name")
    if not isinstance(packages, list) or not all(isinstance(p, str) and p for p in packages):
        raise CoverageGateError(f"{where} {name}: packages must be non-empty strings")
    if isinstance(floor, bool) or not isinstance(floor, int | float) or not 0 <= floor <= 100:
        raise CoverageGateError(f"{where} {name}: floor must be a number from 0 to 100")
    if not isinstance(enforced, bool):
        raise CoverageGateError(f"{where} {name}: enforced must be true or false")
    return Floor(name=name, packages=tuple(packages), floor=float(floor), enforced=enforced)


def load_groups(path: Path) -> GroupsConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CoverageGateError(f"cannot read groups file {path.name}: {type(exc).__name__}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != GROUPS_SCHEMA_VERSION or set(raw) - {"schema_version", "groups", "package_floors", "aggregate"}:
        raise CoverageGateError("groups file: unsupported schema")
    groups = tuple(_floor(entry, where="group") for entry in raw.get("groups", []))
    package_floors = tuple(_floor(entry, where="package floor") for entry in raw.get("package_floors", []))
    aggregate = _floor({**raw.get("aggregate", {}), "name": "aggregate", "packages": []}, where="aggregate") if "aggregate" in raw else None
    if not groups or aggregate is None:
        raise CoverageGateError("groups file: groups and aggregate are required")
    names = [group.name for group in groups]
    if len(set(names)) != len(names):
        raise CoverageGateError("groups file: duplicate group name")
    members = [package for group in groups for package in group.packages]
    duplicates = sorted({package for package in members if members.count(package) > 1})
    if duplicates:
        raise CoverageGateError(f"groups file: packages in more than one group: {duplicates}")
    for entry in package_floors:
        if len(entry.packages) != 1 or entry.packages[0] not in members:
            raise CoverageGateError(f"package floor {entry.name}: must name one package that belongs to a group")
    return GroupsConfig(groups=groups, package_floors=package_floors, aggregate=aggregate)


def tracked_sources(repo: Path) -> tuple[PurePosixPath, ...]:
    """Every tracked Python file under `src/`, relative to it: the repository-truth inventory (the Git
    index), never a disk walk, so untracked or generated files can neither add nor hide a package."""
    try:
        files = tracked_repository_files(repo, pathspecs=("src",))
    except TrackedFileInventoryError as exc:
        raise CoverageGateError(f"cannot list the tracked src files: {exc}") from exc
    src = (repo / "src").resolve()
    return tuple(PurePosixPath(path.relative_to(src).as_posix()) for path in files if path.suffix == ".py")


def discover_packages(sources: Sequence[PurePosixPath]) -> tuple[str, ...]:
    """Every top-level package with tracked Python source, `__init__.py` or not (namespace packages). A
    top-level module would belong to no group, so it is refused rather than left unmeasured."""
    stray = sorted(str(path) for path in sources if len(path.parts) == 1)
    if stray:
        raise CoverageGateError(f"top-level src modules belong to no package group: {stray}")
    return tuple(sorted({path.parts[0] for path in sources if not path.parts[0].startswith((".", "_"))}))


def configured_sources(pyproject: Path) -> tuple[str, ...]:
    config = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    source = config.get("tool", {}).get("coverage", {}).get("run", {}).get("source")
    if not isinstance(source, list) or not all(isinstance(item, str) for item in source):
        raise CoverageGateError("pyproject [tool.coverage.run] source must list the src packages")
    return tuple(source)


def validate_inventory(config: GroupsConfig, discovered: Sequence[str], sources: Sequence[str]) -> None:
    members = {package for group in config.groups for package in group.packages}
    unmapped = sorted(set(discovered) - members)
    stale = sorted(members - set(discovered))
    if unmapped:
        raise CoverageGateError(f"src packages in no product group: {unmapped}")
    if stale:
        raise CoverageGateError(f"product groups name packages not in src: {stale}")
    expected = {f"src/{package}" for package in discovered}
    configured = {source.replace("\\", "/").rstrip("/") for source in sources}
    if configured != expected:
        raise CoverageGateError(
            f"configured coverage sources differ from the src packages: missing {sorted(expected - configured)}, extra {sorted(configured - expected)}"
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def report_dataset(data_file: Path, config: GroupsConfig, *, repo: Path, json_out: Path | None = None) -> dict[str, object]:
    """Each floor's percentage from one dataset, with the configured precision and comparison: coverage's
    own fail-under rule, as pytest-cov and `coverage report --fail-under` apply it (the total rounded to
    the configured precision is compared with the floor). With `json_out`, the same loaded dataset is
    also exported as coverage's JSON report."""
    import coverage
    from coverage.exceptions import NoDataError
    from coverage.results import display_covered, should_fail_under

    if not data_file.is_file() or data_file.stat().st_size == 0:
        raise CoverageGateError("coverage data is missing or empty")
    cov = coverage.Coverage(data_file=str(data_file), config_file=str(repo / "pyproject.toml"))
    cov.load()
    measured = {Path(name).resolve() for name in cov.get_data().measured_files()}
    src = (repo / "src").resolve()
    # Every tracked source file must be in the dataset, executed or not; a run without the configured
    # sources would silently drop never-imported files from the denominator.
    sources = tracked_sources(repo)
    packages = set(discover_packages(sources))
    absent = sorted(str(path) for path in sources if path.parts[0] in packages and (src / path).resolve() not in measured)
    if absent:
        raise CoverageGateError(f"source files missing from the dataset (not measured even as unexecuted): {absent[:10]}")
    precision = cov.config.precision

    def percent(packages: Sequence[str]) -> float:
        include = [f"{(src / package).as_posix()}/*" for package in packages] if packages else None
        try:
            return cov.report(include=include, file=io.StringIO(), precision=precision)
        except NoDataError as exc:
            raise CoverageGateError(f"no measured files for {list(packages) or 'aggregate'}") from exc

    rows = []
    for entry in (*config.groups, *config.package_floors, config.aggregate):
        value = percent(entry.packages)
        passed = not should_fail_under(value, entry.floor, precision)
        rows.append(
            {
                "name": entry.name,
                "packages": list(entry.packages),
                "percent": value,
                "compared": display_covered(value, precision),
                "floor": entry.floor,
                "enforced": entry.enforced,
                "passed": passed,
            }
        )
    result: dict[str, object] = {"data_file_sha256": _sha256(data_file), "precision": precision, "floors": rows}
    if json_out is not None:
        result["coverage_json_sha256"] = export_json(cov, json_out, measured=len(measured))
    return result


def export_json(cov: object, json_out: Path, *, measured: int) -> str:
    """Coverage's own JSON report of the dataset already loaded in `cov`: never another test run. Every
    measured file must appear once, keyed by its repository-relative `src/` path (the gate runs from the
    repository root, as CI does), so a base and a candidate report compare row by row."""
    from coverage.exceptions import CoverageException

    try:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        cov.json_report(outfile=str(json_out))  # type: ignore[attr-defined]
        rows = json.loads(json_out.read_text(encoding="utf-8")).get("files", {})
    except (CoverageException, OSError, ValueError) as exc:
        raise CoverageGateError(f"cannot export the coverage JSON report: {type(exc).__name__}") from exc
    names = [name.replace("\\", "/") for name in rows]
    if len(names) != measured or not all(name.startswith("src/") for name in names):
        raise CoverageGateError("coverage JSON rows are not the measured files keyed by repository-relative src/ paths")
    return _sha256(json_out)


Runner = Callable[[Sequence[str], Path], int]


def _run_pytest(command: Sequence[str], cwd: Path) -> int:
    # One child: the repository's own interpreter running its default selection. No shell, no nested
    # uv; output streams to this process's terminal so CI keeps the full pytest log.
    return subprocess.run(list(command), cwd=cwd, check=False).returncode  # noqa: S603 - fixed argv


def candidate_identity(repo: Path) -> dict[str, object]:
    """The commit this run measures, its tree (a pull-request run measures GitHub's merge commit, whose
    tree is what a branch head is compared by) and whether the checkout differed from it: complete
    `git status --porcelain`, so an edited tool, groups file or untracked file counts, ignored outputs do
    not (Fable CP4 release review m7). Unknown outside a git checkout."""
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
        tree = subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
        status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return {"git_head": None, "git_tree": None, "worktree_dirty": None}
    return {"git_head": head, "git_tree": tree, "worktree_dirty": bool(status.strip())}


def run_receipts(repo: Path, groups: Path) -> dict[str, object]:
    """What the run measured with besides its commit: the groups policy file it loaded, configuration and
    lock bytes, the coverage engine and its configuration, and the interpreter. A safety comparison needs
    the same coverage version, configuration and policy on both sides; these are its receipts, not an
    authenticated snapshot."""
    import coverage

    def digest(name: str) -> str | None:
        path = repo / name
        return _sha256(path) if path.is_file() else None

    policy = groups.resolve()
    try:
        policy_path = policy.relative_to(repo.resolve()).as_posix()
    except ValueError:  # a policy file outside the repository is named by its absolute path
        policy_path = policy.as_posix()
    config = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))
    return {
        "groups_path": policy_path,
        "groups_sha256": _sha256(policy),
        "pyproject_sha256": digest("pyproject.toml"),
        "uv_lock_sha256": digest("uv.lock"),
        "coverage_version": coverage.__version__,
        "coverage_config": config.get("tool", {}).get("coverage"),
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "platform": sys.platform,
    }


def run_full_suite(repo: Path, *, groups: Path, runner: Runner = _run_pytest, python: str = sys.executable) -> dict[str, object]:
    data_file = repo / ".coverage"
    # Only coverage data files (`.coverage`, `.coverage.<suffix>`), never `.coveragerc`: a stale dataset
    # must never be reported as this run's.
    for stale in repo.glob(".coverage*"):
        if stale.is_file() and (stale.name == ".coverage" or stale.name.startswith(".coverage.")):
            stale.unlink()
    command = [python, *FULL_SUITE_ARGS]
    identity = {**candidate_identity(repo), **run_receipts(repo, groups)}
    started = time.time()
    exit_code = runner(command, repo)
    finished = time.time()
    after = candidate_identity(repo)  # the checkout once the child exited: a change during the run shows
    record: dict[str, object] = {
        "schema": RUN_RECORD_SCHEMA,
        **identity,
        "git_head_after": after["git_head"],
        "git_tree_after": after["git_tree"],
        "worktree_dirty_after": after["worktree_dirty"],
        "command": [Path(command[0]).name, *command[1:]],
        "pytest_exit": exit_code,
        "started": started,
        "finished": finished,
        "data_file": data_file.name,
    }
    if data_file.is_file():
        record["data_file_sha256"] = _sha256(data_file)
    return record


def verdict(run: dict[str, object], measured: dict[str, object] | None, error: str | None) -> dict[str, object]:
    failures = []
    if run.get("pytest_exit") != 0:
        failures.append(f"full suite exit {run.get('pytest_exit')}")
    if error is not None:
        failures.append(error)
    if measured is not None:
        failures += [f"{row['name']} {row['percent']}% < {row['floor']}%" for row in measured["floors"] if row["enforced"] and not row["passed"]]
    return {"passed": not failures, "failures": failures}


def main(argv: Sequence[str] | None = None, *, runner: Runner = _run_pytest, repo: Path = REPO_ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run-full-suite", action="store_true", help="run the one approved full selection, then report it")
    mode.add_argument("--data-file", type=Path, help="report an identified full-suite dataset (needs --run-record)")
    parser.add_argument("--run-record", type=Path, help="the run record --run-full-suite wrote for --data-file")
    parser.add_argument("--groups", type=Path, required=True)
    parser.add_argument("--report-json", type=Path, required=True)
    parser.add_argument("--coverage-json", type=Path, help="also export coverage's JSON report of the same dataset")
    args = parser.parse_args(argv)
    if args.run_full_suite and args.run_record is not None:
        parser.error("--run-record belongs to --data-file")
    if args.data_file is not None and args.run_record is None:
        parser.error("--data-file needs the --run-record that identifies it as a full-suite dataset")

    error: str | None = None
    if args.coverage_json is not None and args.coverage_json.is_file():
        args.coverage_json.unlink()  # an earlier export must never pass as this run's
    measured: dict[str, object] | None = None
    try:
        config = load_groups(args.groups)
        validate_inventory(config, discover_packages(tracked_sources(repo)), configured_sources(repo / "pyproject.toml"))
    except CoverageGateError as exc:
        config, error = None, str(exc)

    if args.run_full_suite:
        run = run_full_suite(repo, groups=args.groups, runner=runner) if config is not None else {"schema": RUN_RECORD_SCHEMA, "pytest_exit": None}
        data_file = repo / ".coverage"
    else:
        data_file = args.data_file
        try:
            run = json.loads(args.run_record.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            run, error = {"pytest_exit": None}, error or "run record missing or unreadable"
        else:
            if run.get("schema") != RUN_RECORD_SCHEMA or not data_file.is_file() or run.get("data_file_sha256") != _sha256(data_file):
                error = error or "dataset is not the one its run record identifies (stale or foreign data)"
    if config is not None and error is None:
        try:
            measured = report_dataset(data_file, config, repo=repo, json_out=args.coverage_json)
        except CoverageGateError as exc:
            error = str(exc)

    result = {"run": run, "coverage": measured, "verdict": verdict(run, measured, error)}
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.run_full_suite and "data_file_sha256" in run:
        (args.report_json.with_suffix(".run.json")).write_text(json.dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if "git_head" in run:
        print(f"coverage dataset: git_head {run['git_head']} worktree_dirty {run['worktree_dirty']}")
    if "git_head_after" in run:
        print(f"coverage dataset after the run: git_head {run['git_head_after']} worktree_dirty {run['worktree_dirty_after']}")
    if measured is not None and "coverage_json_sha256" in measured:
        print(f"coverage json: {args.coverage_json} sha256 {measured['coverage_json_sha256']}")
    for row in (measured or {}).get("floors", []):
        label = "required" if row["enforced"] else "informational"
        verdict_text = "PASS" if row["passed"] else "BELOW"
        print(f"coverage {row['name']}: {row['compared']}% compared, {row['percent']:.4f}% measured (floor {row['floor']}%, {label}) {verdict_text}")
    for failure in result["verdict"]["failures"]:
        print(f"coverage gate failure: {failure}", file=sys.stderr)
    return 0 if result["verdict"]["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
