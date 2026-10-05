"""Product coverage gates over one full default-selection run (Plan 11.30 Task 3).

Every importable production package under ``src/`` belongs to exactly one product. Each enforced product is
measured unrounded with coverage.py's own formula, (covered lines + covered branches) / (statements + branches),
against its floor; the deferred A2A product is printed and never enforced. The data must be complete (a row for
every current source file), current (each row's statement and branch counts equal coverage.py's analysis of the
current file) and the full default selection of this source (its run-context terminal record supports a result,
selected exactly the current collected universe, and names this commit, configuration and lock). Anything else
fails closed.

    python -m tools.testing.coverage_products report --coverage-json PATH [--run-record PATH]
    python -m tools.testing.coverage_products compare --base PATH --candidate PATH
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.testing import run_context
from tools.testing import run_context_records as records
from tools.tracked_repository_files import tracked_repository_files

ROOT = Path(__file__).resolve().parents[2]
FLOOR = 80.0
PRODUCTS: dict[str, tuple[str, ...]] = {
    "Optimus": ("optimus", "optimus_gateway", "optimus_security", "optimus_model_policy"),
    "Context Engine": ("context_engine",),
    "A2A": ("evidence_handoff", "evidence_handoff_runtime"),
}
INFORMATIONAL = frozenset({"A2A"})  # deferred product: reported, never enforced
MODEL_POLICY = "optimus_model_policy"  # its own floor, over the same rows it adds to Optimus
SAFETY_MODULES = (
    "src/optimus/tools/registry.py", "src/optimus/runtime/mutation.py", "src/optimus/gateway/models.py",
    "src/optimus/evidence/ledger.py", "src/optimus/acp/framing.py", "src/optimus/retry/policy.py", "src/optimus/tools/policy.py",
)
EXIT_PASS, EXIT_BELOW_FLOOR, EXIT_INPUT, EXIT_INVALID = 0, 1, 2, 3
# pytest-cov writes its reports as the session ends, just after the run-context terminal record.
_LATE_REPORT = timedelta(minutes=5)


class CoverageInputError(ValueError):
    """The packages cannot be classified, or an input cannot be read."""


@dataclass(frozen=True)
class ProductResult:
    name: str
    packages: tuple[str, ...]  # the present packages measured
    statements: int
    covered_statements: int
    branches: int
    covered_branches: int
    percent: float | None  # unrounded; None when no package of the product is present
    enforced: bool
    status: str  # "pass", "fail", "informational" or "n/a"


@dataclass(frozen=True)
class CoverageVerdict:
    products: tuple[ProductResult, ...]
    problems: tuple[str, ...]  # data that cannot support a verdict; any problem fails it

    @property
    def passed(self) -> bool:
        return not self.problems and all(product.status != "fail" for product in self.products)


@dataclass(frozen=True)
class SourceIdentity:
    """What the coverage must have been measured on: this commit, configuration, lock and collected universe."""

    head: str | None
    config_sha256: str | None
    lock_sha256: str | None
    universe: tuple[str, ...]
    clean: bool  # no uncommitted change under src/, tests/, pyproject.toml or uv.lock
    # The most recently modified of those tracked files and its UTC modification time: a dirty run followed by
    # `git stash`, `checkout` or `restore` leaves a clean tree, but rewrites the files after the run began.
    latest_change: tuple[str, str] | None


def _tracked_python(root: Path) -> tuple[str, ...]:
    """Every tracked Python file under src/, as a repository-relative POSIX path."""
    resolved = root.resolve()
    return tuple(sorted(
        path.relative_to(resolved).as_posix() for path in tracked_repository_files(root, pathspecs=("src",)) if path.suffix == ".py"
    ))


def discover_packages(root: Path) -> tuple[str, ...]:
    """Importable top-level packages under src/: tracked Python directories, never distribution metadata (`*.egg-info`)."""
    return tuple(sorted({
        parts[1] for parts in (path.split("/") for path in _tracked_python(root))
        if len(parts) > 2 and parts[1].isidentifier() and not parts[1].startswith("__")
    }))


def classify_packages(packages: tuple[str, ...]) -> dict[str, str]:
    """Each package's one product. A package claimed twice, or not yet reviewed into a product, fails closed."""
    product_of: dict[str, str] = {}
    for product, members in PRODUCTS.items():
        for member in members:
            if member in product_of:
                raise CoverageInputError(f"{member} belongs to more than one product")
            product_of[member] = product
    unknown = [package for package in packages if package not in product_of]
    if unknown:
        raise CoverageInputError(f"unreviewed package {unknown[0]}: classify it into a product before measuring")
    return {package: product_of[package] for package in packages}


@functools.lru_cache(maxsize=4)
def _coverage(config: str) -> object:
    import coverage  # noqa: PLC0415 - only the report tool needs coverage.py's analysis

    return coverage.Coverage(config_file=config, data_file=None)


def source_counts(path: Path, config: Path) -> tuple[int, int]:
    """The statements and branches coverage.py counts for this file under this configuration (its exclusions)."""
    from coverage.python import PythonFileReporter  # noqa: PLC0415

    reporter = PythonFileReporter(str(path), coverage=_coverage(str(config)))  # type: ignore[arg-type]
    return len(reporter.lines()), sum(count for count in reporter.exit_counts().values() if count > 1)


def _measure(name: str, packages: tuple[str, ...], files: Mapping[str, tuple[str, ...]], rows: Mapping[str, dict],
             enforced: bool, problems: list[str]) -> ProductResult:
    present = tuple(package for package in packages if package in files)
    if not present:
        return ProductResult(name, (), 0, 0, 0, 0, None, enforced, "n/a")
    totals = [0, 0, 0, 0]
    for package in present:
        for path in files[package]:
            summary = rows.get(path, {}).get("summary", {})
            for index, key in enumerate(("num_statements", "covered_lines", "num_branches", "covered_branches")):
                totals[index] += int(summary.get(key, 0))
    statements, covered, branches, covered_branches = totals
    if statements + branches == 0:
        if enforced:
            problems.append(f"{name} has no statements or branches to measure")
        return ProductResult(name, present, 0, 0, 0, 0, None, enforced, "fail" if enforced else "informational")
    percent = 100.0 * (covered + covered_branches) / (statements + branches)
    status = ("pass" if percent >= FLOOR else "fail") if enforced else "informational"
    return ProductResult(name, present, statements, covered, branches, covered_branches, percent, enforced, status)


def evaluate(report: Mapping[str, object], counts: Mapping[str, tuple[int, int]], files: Mapping[str, tuple[str, ...]]) -> CoverageVerdict:
    """The verdict over complete, current data: `files` is every current source file per present package, and
    `counts` their statements and branches as coverage.py analyses the current source."""
    problems: list[str] = []
    try:
        classify_packages(tuple(files))
    except CoverageInputError as error:
        return CoverageVerdict((), (str(error),))
    meta = report.get("meta") if isinstance(report.get("meta"), dict) else {}
    if not meta.get("branch_coverage"):  # type: ignore[union-attr]
        problems.append("the coverage data was not measured with branch coverage")
    raw = report.get("files") if isinstance(report.get("files"), dict) else {}
    rows = {str(path).replace("\\", "/"): row for path, row in raw.items()}  # type: ignore[union-attr]
    expected = {path for paths in files.values() for path in paths}
    problems += [f"{path}: no coverage row" for path in sorted(expected - rows.keys())]
    problems += [f"{path}: row for a file that is not in the current source" for path in sorted(rows.keys() - expected)]
    for path in sorted(expected & rows.keys()):
        summary = rows[path].get("summary", {})
        found = (summary.get("num_statements"), summary.get("num_branches"))
        if found != counts[path]:
            problems.append(f"{path}: report counts {found[0]} statements and {found[1]} branches; "
                            f"the current source has {counts[path][0]} and {counts[path][1]}")
    products = (
        _measure("Optimus", PRODUCTS["Optimus"], files, rows, True, problems),
        _measure("Model policy", (MODEL_POLICY,), files, rows, True, problems),
        _measure("Context Engine", PRODUCTS["Context Engine"], files, rows, True, problems),
        _measure("A2A", PRODUCTS["A2A"], files, rows, "A2A" not in INFORMATIONAL, problems),
    )
    return CoverageVerdict(products, tuple(problems))


def universe_digest(universe: tuple[str, ...]) -> str:
    """The run-context selection digest of a set of node IDs (sorted node digests), as a run records it."""
    found = hashlib.sha256()
    for node in sorted(universe):
        found.update(run_context._node(node).encode("ascii"))  # noqa: SLF001 - the run context's own node digest
    return found.hexdigest()


def _utc(text: object) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(text))
    except ValueError:
        return None
    return (moment.astimezone() if moment.tzinfo is None else moment).astimezone(timezone.utc)  # naive = this host's local time


def full_run_problems(run: Mapping[str, object], meta: Mapping[str, object], identity: SourceIdentity) -> list[str]:
    """Why this run's coverage cannot be the full default selection of this source; empty when it can."""
    from tools.testing import run_profile  # noqa: PLC0415 - the runner's terminal-record validity rule

    problems: list[str] = []
    problem, _ = run_profile.record_validity(dict(run), 0)  # a passing full run: its recorded exit is 0
    if problem is not None:
        problems.append(f"the run's own record cannot support a result: {problem}")
    if run.get("reason") != "default_selection":
        problems.append(f"the run was not the default selection ({run.get('reason')})")
    if run.get("collection_errors"):
        problems.append(f"the run had {run.get('collection_errors')} collection errors")
    if run.get("selected") != len(identity.universe) or run.get("selection_sha256") != universe_digest(identity.universe):
        problems.append(f"the run did not select the current default universe ({run.get('selected')} of {len(identity.universe)} tests)")
    if run.get("head") != identity.head:
        problems.append(f"the run measured commit {run.get('head')}, not the current HEAD {identity.head}")
    if run.get("config_sha256") != identity.config_sha256:
        problems.append("the run used a different pyproject.toml")
    if run.get("lock_sha256") != identity.lock_sha256:
        problems.append("the run used a different uv.lock")
    if not identity.clean:
        problems.append("the source, tests or configuration have uncommitted changes, so the run's commit does not identify them")
    if identity.latest_change is not None:
        path, when = identity.latest_change
        changed, began = _utc(when), _utc(run.get("started_utc"))
        if changed is not None and began is not None and changed > began:
            problems.append(f"{path} changed at {changed}, after the run started, so the run may have measured other bytes")
    written, started, finished = _utc(meta.get("timestamp")), _utc(run.get("started_utc")), _utc(run.get("finished_utc"))
    if written is None or started is None or finished is None or not started <= written <= finished + _LATE_REPORT:
        problems.append(f"the coverage data was written at {written}, outside the run ({started} to {finished})")
    return problems


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def _digest_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def source_identity(root: Path, universe: tuple[str, ...]) -> SourceIdentity:
    scope = ("src", "tests", "pyproject.toml", "uv.lock")
    changed = _git(root, "status", "--porcelain", "--", *scope)
    resolved = root.resolve()
    newest = max(((path.stat().st_mtime, path) for path in tracked_repository_files(root, pathspecs=scope)), default=None)
    latest = None if newest is None else (
        newest[1].relative_to(resolved).as_posix(), datetime.fromtimestamp(newest[0], timezone.utc).isoformat())
    return SourceIdentity(_git(root, "rev-parse", "HEAD"), _digest_file(root / "pyproject.toml"), _digest_file(root / "uv.lock"),
                          universe, clean=not changed, latest_change=latest)


def evaluate_products(coverage_json: Path, package_roots: tuple[str, ...], full_run_manifest: Path, *,
                      root: Path = ROOT, universe: tuple[str, ...] | None = None) -> CoverageVerdict:
    """The product verdict for one full run's coverage JSON, bound to that run's run-context record and to this
    source. `universe` defaults to the default selection collected from this source now."""
    report = json.loads(coverage_json.read_bytes())
    config = root / "pyproject.toml"
    tracked = _tracked_python(root)
    files = {package: tuple(path for path in tracked if path.startswith(f"src/{package}/")) for package in package_roots}
    counts = {path: source_counts(root / path, config) for paths in files.values() for path in paths}
    verdict = evaluate(report, counts, files)
    run = records.read_record(full_run_manifest)
    if run is None:
        return CoverageVerdict(verdict.products, (*verdict.problems, f"{full_run_manifest}: not a readable run-context record"))
    if universe is None:
        from tools.testing import run_profile  # noqa: PLC0415

        universe = run_profile.collect_universe(root)
    identity = source_identity(root, universe)
    meta = report.get("meta") if isinstance(report.get("meta"), dict) else {}
    return CoverageVerdict(verdict.products, (*verdict.problems, *full_run_problems(run, meta, identity)))


def find_full_run(root: Path, coverage_json: Path) -> Path | None:
    """The one terminal default-selection record whose run contains the report's write time; None unless exactly one."""
    meta = json.loads(coverage_json.read_bytes()).get("meta") or {}
    written = _utc(meta.get("timestamp"))
    found = []
    for path in sorted((root / "tmp" / "test-runs").glob("*/run.json")):
        record = records.read_record(path)
        if record is None or record.get("checkpoint") != "terminal" or record.get("reason") != "default_selection":
            continue
        started, finished = _utc(record.get("started_utc")), _utc(record.get("finished_utc"))
        if written and started and finished and started <= written <= finished + _LATE_REPORT:
            found.append((int(record.get("selected", 0)), path))  # type: ignore[call-overload]
    if not found:
        return None
    most = max(selected for selected, _ in found)
    largest = [path for selected, path in found if selected == most]  # nested sessions select far fewer tests
    return largest[0] if len(largest) == 1 else None


def compare_safety_rows(base: Mapping[str, object], candidate: Mapping[str, object]) -> list[str]:
    """Regressions of the named safety-critical modules between comparable reports (same coverage version and
    branch measurement); totals and misses are compared, never rounded percentages."""
    base_meta, candidate_meta = base.get("meta") or {}, candidate.get("meta") or {}  # type: ignore[var-annotated]
    if base_meta.get("version") != candidate_meta.get("version"):  # type: ignore[union-attr]
        return [f"the reports were made by different coverage versions ({base_meta.get('version')}, {candidate_meta.get('version')})"]  # type: ignore[union-attr]
    if not (base_meta.get("branch_coverage") and candidate_meta.get("branch_coverage")):  # type: ignore[union-attr]
        return ["both reports must measure branch coverage"]
    problems = []
    for path in SAFETY_MODULES:
        rows = []
        for label, report in (("base", base), ("candidate", candidate)):
            row = (report.get("files") or {}).get(path)  # type: ignore[union-attr]
            if row is None:
                problems.append(f"{path}: no row in the {label} report")
            rows.append(row)
        if None in rows:
            continue
        old, new = (row["summary"] for row in rows)  # type: ignore[index]

        def shown(summary: Mapping[str, int]) -> str:
            return (f"{summary['covered_lines']}/{summary['num_statements']} statements and "
                    f"{summary['covered_branches']}/{summary['num_branches']} branches")

        def percent(summary: Mapping[str, int]) -> float:
            total = summary["num_statements"] + summary["num_branches"]
            return 100.0 if total == 0 else 100.0 * (summary["covered_lines"] + summary["covered_branches"]) / total

        if (new["missing_lines"] > old["missing_lines"] or new["missing_branches"] > old["missing_branches"]
                or percent(new) < percent(old)):
            problems.append(f"{path}: regressed from {shown(old)} to {shown(new)}")
    return problems


def _print_verdict(verdict: CoverageVerdict) -> None:
    for product in verdict.products:
        if product.percent is None:
            print(f"coverage-products: {product.name}: {product.status}")
            continue
        floor = f"floor {FLOOR:g}" if product.enforced else "not enforced"
        print(f"coverage-products: {product.name}: {product.percent:.4f}% ({product.covered_statements}/{product.statements} "
              f"statements, {product.covered_branches}/{product.branches} branches; {floor}) {product.status} "
              f"[{', '.join(product.packages)}]")
    for problem in verdict.problems:
        print(f"coverage-products: problem: {records.sanitized_text(problem)[:300]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.testing.coverage_products", description="Product coverage gates.")
    commands = parser.add_subparsers(dest="command", required=True)
    reported = commands.add_parser("report", help="gate one full run's coverage JSON per product")
    reported.add_argument("--coverage-json", type=Path, required=True)
    reported.add_argument("--run-record", type=Path, default=None, help="its run-context run.json (default: found by time)")
    compared = commands.add_parser("compare", help="compare the safety-critical module rows of two comparable reports")
    compared.add_argument("--base", type=Path, required=True)
    compared.add_argument("--candidate", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "compare":
            base, candidate = arguments.base.read_bytes(), arguments.candidate.read_bytes()
            # The reports carry no platform, interpreter or source SHA: name the exact files compared, for the
            # evidence that binds them to their CI runs.
            print(f"coverage-products: compared base sha256 {hashlib.sha256(base).hexdigest()} "
                  f"with candidate sha256 {hashlib.sha256(candidate).hexdigest()}")
            problems = compare_safety_rows(json.loads(base), json.loads(candidate))
            for problem in problems:
                print(f"coverage-products: safety: {records.sanitized_text(problem)[:300]}")
            print(f"coverage-products: safety rows {'regressed or incomparable' if problems else 'comparable, no regression'}")
            return EXIT_BELOW_FLOOR if problems else EXIT_PASS
        record = arguments.run_record or find_full_run(ROOT, arguments.coverage_json)
        if record is None:
            print("coverage-products: problem: no single full default-selection run record contains this report")
            return EXIT_INVALID
        verdict = evaluate_products(arguments.coverage_json, discover_packages(ROOT), record)
    except (OSError, ValueError) as error:
        print(f"coverage-products: input failure: {records.sanitized_text(str(error))[:300]}")
        return EXIT_INPUT
    _print_verdict(verdict)
    if verdict.problems:
        return EXIT_INVALID
    return EXIT_PASS if verdict.passed else EXIT_BELOW_FLOOR


if __name__ == "__main__":
    sys.exit(main())
