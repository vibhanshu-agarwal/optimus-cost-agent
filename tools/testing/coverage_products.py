"""Full-run validity and safety-row comparison over the canonical product coverage gate (Plan 11.30 v5 I2).

The product floors are decided once, by `tools/check_product_coverage.py` (Plan 12.2, Test Strategy section 8A): its
groups file, coverage.py's fail-under comparison at precision 0 (79.5% compares as 80%, 79.0% fails) and its
namespace and unloaded-file inventory. This module decides no floor. Over the coverage JSON that gate exported from
the same dataset (`--coverage-json`) it adds what the gate does not bind, and anything else fails closed:

- the gate's run record identifies one clean canonical run of one exact checkout: schema, head and tree before and
  after, a clean complete checkout (tracked and untracked; ignored outputs aside) before and after, the canonical
  command and groups policy, configuration, lock, coverage engine, interpreter and platform (absent is unknown);
- the data is complete and current: a row for every tracked source file of every grouped package, no other row, and
  each row's statement and branch counts equal coverage.py's analysis of the current file;
- the dataset is the one full default session of this source: its run-context terminal record supports a result,
  selected exactly the current collected universe and names this commit, configuration and lock, inside the gate's
  own run, with the data written inside the session; the whole checkout is unchanged since it started.

`compare` checks the seven named safety-critical modules between a base and a candidate export by totals and misses,
never rounded percentages, only after both sides are proven the same way from their own uploaded records (never from
a passed flag) and are comparable: one coverage engine, configuration, groups policy, platform and Python
implementation and minor version. Naive coverage timestamps are read in each producer's stated UTC offset.

`validate` reads a naive coverage timestamp in this host's local zone, so it runs on the machine that produced the
data (in CI, the same job; locally, the measuring checkout). `compare` cannot recompute either side's collected
universe from its artifact or check the run-context record's platform against the gate's: per-SHA universe proof
(Plan 11.30 v5 Q-C3) and artifact origin are evidence-step receipts, never inferred from a passing comparison.

    python -m tools.testing.coverage_products validate --coverage-json PATH --gate-report PATH [--run-record PATH]
    python -m tools.testing.coverage_products compare --base PATH --base-report PATH --base-run-record PATH
        --base-producer-utc-offset +HH:MM --candidate PATH --candidate-report PATH --candidate-run-record PATH
        --candidate-producer-utc-offset +HH:MM [--base-audit-depth-proven-absent]
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools import check_product_coverage as gate
from tools.testing import run_context
from tools.testing import run_context_records as records
from tools.tracked_repository_files import TrackedFileInventoryError, tracked_repository_files

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_GROUPS = "tools/product-coverage-groups.json"
GROUPS = ROOT / CANONICAL_GROUPS
SAFETY_MODULES = (
    "src/optimus/tools/registry.py", "src/optimus/runtime/mutation.py", "src/optimus/gateway/models.py",
    "src/optimus/evidence/ledger.py", "src/optimus/acp/framing.py", "src/optimus/retry/policy.py", "src/optimus/tools/policy.py",
)
EXIT_PASS, EXIT_REGRESSED, EXIT_INPUT, EXIT_INVALID = 0, 1, 2, 3
# The gate exports the JSON as the session ends, just after the run-context terminal record. The margin applies to
# that export only, never to the session's or the gate's own bounds.
_LATE_REPORT = timedelta(minutes=5)
# Every receipt a new exact-source or comparison claim needs from the gate's run record (additive v1 keys).
REQUIRED_RECEIPT_KEYS = (
    "schema", "git_head", "git_tree", "git_head_after", "git_tree_after", "worktree_dirty", "worktree_dirty_after",
    "command", "groups_path", "groups_sha256", "pyproject_sha256", "uv_lock_sha256", "coverage_version", "coverage_config",
    "python_implementation", "python_version", "platform", "pytest_exit", "started", "finished", "data_file_sha256",
)
_HEX = re.compile(r"[0-9a-f]+")
_OFFSET = re.compile(r"([+-])(\d{2}):(\d{2})")


@dataclass(frozen=True)
class CoverageVerdict:
    problems: tuple[str, ...]  # data that cannot support the gate's verdict; any problem fails it

    @property
    def passed(self) -> bool:
        return not self.problems


@dataclass(frozen=True)
class SourceIdentity:
    """What the coverage must have been measured on: this exact clean checkout and its collected universe."""

    head: str | None
    tree: str | None
    config_sha256: str | None
    lock_sha256: str | None
    groups_sha256: str | None  # the canonical groups policy as checked out
    coverage_version: str  # the coverage.py that analyses the current source here
    universe: tuple[str, ...]
    clean: bool  # complete `git status --porcelain` empty: gate, tools, groups and untracked files included
    # The most recently modified tracked file of the whole checkout and its UTC modification time: a dirty run followed
    # by `git stash`, `checkout` or `restore` leaves a clean tree, but rewrites the files after the run began.
    latest_change: tuple[str, str] | None


@dataclass(frozen=True)
class Side:
    """One side of a safety comparison, as its CI run uploaded it."""

    label: str  # "base" or "candidate"
    report: Mapping[str, object]  # the gate's --report-json
    data: bytes  # the gate's --coverage-json export
    record: Mapping[str, object]  # the run-context terminal record of its full session
    producer_offset: str  # the producer's UTC offset (+HH:MM): coverage writes naive local timestamps
    depth_proof: bool = False  # base only: its exact SHA was proven to have no audit-depth option (v5 Q-C1)


def package_files(root: Path, groups: Path = GROUPS) -> dict[str, tuple[str, ...]]:
    """Every tracked source file of every package, as repository-relative POSIX paths, after the canonical gate's own
    inventory checks (each package in exactly one group, namespace packages included, no stray top-level module, the
    configured coverage sources equal to the packages). Raises `gate.CoverageGateError` otherwise."""
    config = gate.load_groups(groups)
    sources = gate.tracked_sources(root)
    packages = gate.discover_packages(sources)
    gate.validate_inventory(config, packages, gate.configured_sources(root / "pyproject.toml"))
    return {package: tuple(sorted(f"src/{path}" for path in sources if path.parts[0] == package)) for package in packages}


@functools.lru_cache(maxsize=4)
def _coverage(config: str) -> object:
    import coverage  # noqa: PLC0415 - only the validity check needs coverage.py's analysis

    return coverage.Coverage(config_file=config, data_file=None)


def source_counts(path: Path, config: Path) -> tuple[int, int]:
    """The statements and branches coverage.py counts for this file under this configuration (its exclusions)."""
    from coverage.python import PythonFileReporter  # noqa: PLC0415

    reporter = PythonFileReporter(str(path), coverage=_coverage(str(config)))  # type: ignore[arg-type]
    return len(reporter.lines()), sum(count for count in reporter.exit_counts().values() if count > 1)


def evaluate(report: Mapping[str, object], counts: Mapping[str, tuple[int, int]], files: Mapping[str, tuple[str, ...]]) -> CoverageVerdict:
    """Whether the data is complete and current: `files` is every current source file per package, and `counts` their
    statements and branches as coverage.py analyses the current source."""
    problems: list[str] = []
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
    return CoverageVerdict(tuple(problems))


def universe_digest(universe: tuple[str, ...]) -> str:
    """The run-context selection digest of a set of node IDs (sorted node digests), as a run records it."""
    found = hashlib.sha256()
    for node in sorted(universe):
        found.update(run_context._node(node).encode("ascii"))  # noqa: SLF001 - the run context's own node digest
    return found.hexdigest()


def _utc(text: object, producer: timezone | None = None) -> datetime | None:
    """An ISO timestamp in UTC. A naive one is the producer's local time: `producer` when stated, else this host's."""
    try:
        moment = datetime.fromisoformat(str(text))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=producer) if producer is not None else moment.astimezone()
    return moment.astimezone(timezone.utc)


def _epoch(value: object) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return datetime.fromtimestamp(value, timezone.utc)


def _offset(text: str) -> timezone | None:
    match = _OFFSET.fullmatch(text)
    if match is None:
        return None
    delta = timedelta(hours=int(match[2]), minutes=int(match[3]))
    return timezone(-delta if match[1] == "-" else delta)


def _hex(value: object, width: int) -> bool:
    return isinstance(value, str) and len(value) == width and _HEX.fullmatch(value) is not None


def receipt_problems(run: Mapping[str, object], label: str) -> list[str]:
    """Why a gate run record cannot identify one clean, canonical full run of one exact checkout. An absent key is
    unknown identity: retained historical evidence, unsupported for a new exact-source or comparison claim."""
    problems: list[str] = []
    if run.get("schema") != gate.RUN_RECORD_SCHEMA:
        problems.append(f"{label}: run record schema {run.get('schema')!r} is not {gate.RUN_RECORD_SCHEMA}")
    for key, width in (("git_head", 40), ("git_tree", 40), ("git_head_after", 40), ("git_tree_after", 40), ("groups_sha256", 64),
                       ("pyproject_sha256", 64), ("uv_lock_sha256", 64), ("data_file_sha256", 64)):
        if not _hex(run.get(key), width):
            problems.append(f"{label}: {key} unrecorded or malformed: identity unknown, unsupported for this claim")
    for key in ("worktree_dirty", "worktree_dirty_after"):
        if run.get(key) is not False:
            problems.append(f"{label}: {key} is {run.get(key, 'unrecorded')!r}: the checkout was not proven clean")
    if (run.get("git_head_after"), run.get("git_tree_after")) != (run.get("git_head"), run.get("git_tree")):
        problems.append(f"{label}: the checkout moved during the run")
    if run.get("groups_path") != CANONICAL_GROUPS:
        problems.append(f"{label}: floors came from groups_path {run.get('groups_path')!r}, not {CANONICAL_GROUPS}")
    command = run.get("command")
    if not (isinstance(command, list) and command and command[1:] == list(gate.FULL_SUITE_ARGS) and str(command[0]).startswith("python")):
        problems.append(f"{label}: command is not the canonical full selection")
    problems += [f"{label}: {key} unrecorded" for key in ("coverage_version", "python_implementation", "python_version", "platform")
                 if not (isinstance(run.get(key), str) and run.get(key))]
    config = run.get("coverage_config")
    measured = config.get("run") if isinstance(config, dict) else None
    if not (isinstance(measured, dict) and measured.get("branch") is True):
        problems.append(f"{label}: coverage_config unrecorded or without branch measurement")
    report = config.get("report") if isinstance(config, dict) and isinstance(config.get("report"), dict) else {}
    if report.get("precision", 0) != 0:
        problems.append(f"{label}: configured report precision {report.get('precision')} is not the canonical 0")
    if isinstance(run.get("pytest_exit"), bool) or not isinstance(run.get("pytest_exit"), int):
        problems.append(f"{label}: pytest_exit unrecorded")
    began, ended = _epoch(run.get("started")), _epoch(run.get("finished"))
    if began is None or ended is None or began > ended:
        problems.append(f"{label}: run window (started, finished) unrecorded or reversed")
    return problems


def full_run_problems(run: Mapping[str, object], meta: Mapping[str, object], identity: SourceIdentity) -> list[str]:
    """Why this run's coverage cannot be the full default selection of this source; empty when it can."""
    from tools.testing import run_profile  # noqa: PLC0415 - the runner's terminal-record validity rule

    problems: list[str] = []
    problem, _ = run_profile.record_validity(dict(run), 0)  # a passing full run at full audit depth: its exit is 0
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
        problems.append("the checkout has uncommitted or untracked changes, so the run's commit does not identify what it measured")
    started, finished = _utc(run.get("started_utc")), _utc(run.get("finished_utc"))
    if identity.latest_change is not None:
        path, when = identity.latest_change
        changed = _utc(when)
        if changed is not None and started is not None and changed > started:
            problems.append(f"{path} changed at {changed}, after the run started, so the run may have measured other bytes")
    written = _utc(meta.get("timestamp"))
    if written is None or started is None or finished is None or not started <= written <= finished + _LATE_REPORT:
        problems.append(f"the coverage data was written at {written}, outside the run ({started} to {finished})")
    return problems


def _inside(gate_run: Mapping[str, object], record: Mapping[str, object]) -> bool:
    """Whether a run-context session lies within the gate's own run window."""
    began, ended = _epoch(gate_run.get("started")), _epoch(gate_run.get("finished"))
    started, finished = _utc(record.get("started_utc")), _utc(record.get("finished_utc"))
    return None not in (began, ended, started, finished) and began <= started <= finished <= ended  # type: ignore[operator]


def gate_binding_problems(gate_report: Mapping[str, object], json_sha256: str, run: Mapping[str, object], identity: SourceIdentity) -> list[str]:
    """Why this coverage JSON is not the dataset the canonical gate reported, from one clean canonical run of this
    exact checkout and from this full session."""
    gate_run = gate_report.get("run") if isinstance(gate_report.get("run"), dict) else {}
    measured = gate_report.get("coverage") if isinstance(gate_report.get("coverage"), dict) else {}
    problems = receipt_problems(gate_run, "the gate run")  # type: ignore[arg-type]
    if measured.get("coverage_json_sha256") != json_sha256:  # type: ignore[union-attr]
        problems.append("the coverage JSON is not the export the gate reported")
    if not measured.get("data_file_sha256") or measured.get("data_file_sha256") != gate_run.get("data_file_sha256"):  # type: ignore[union-attr]
        problems.append("the gate report does not name the dataset its run recorded")
    if measured and measured.get("precision") != 0:  # type: ignore[union-attr]
        problems.append(f"the gate compared at precision {measured.get('precision')}, not the canonical 0")  # type: ignore[union-attr]
    if gate_run.get("git_head") != identity.head:  # type: ignore[union-attr]
        problems.append(f"the gate measured commit {gate_run.get('git_head')}, not the current HEAD {identity.head}")  # type: ignore[union-attr]
    if gate_run.get("git_tree") != identity.tree:  # type: ignore[union-attr]
        problems.append(f"the gate measured tree {gate_run.get('git_tree')}, not the current tree {identity.tree}")  # type: ignore[union-attr]
    if gate_run.get("groups_sha256") != identity.groups_sha256:  # type: ignore[union-attr]
        problems.append(f"the gate's groups policy is not the current {CANONICAL_GROUPS}")
    if gate_run.get("coverage_version") != identity.coverage_version:  # type: ignore[union-attr]
        problems.append(f"the gate ran coverage {gate_run.get('coverage_version')}; the current source is analysed with {identity.coverage_version}")  # type: ignore[union-attr]
    if gate_run.get("pyproject_sha256") != identity.config_sha256 or gate_run.get("uv_lock_sha256") != identity.lock_sha256:  # type: ignore[union-attr]
        problems.append("the gate ran with a different pyproject.toml or uv.lock")
    if not _inside(gate_run, run):  # type: ignore[arg-type]
        problems.append("the run-context record is not the gate's own full run")
    return problems


def eligible_full_runs(paths: Iterable[Path], gate_run: Mapping[str, object], universe: tuple[str, ...]) -> tuple[list[Path], int]:
    """The terminal ACTIVE default-selection sessions of the gate's own checkout, inside its run window, that selected
    exactly `universe` with no collection error; and how many records were considered. Nested, collection-only and
    probe sessions are never the full run, and two eligible sessions bind nothing: no "largest selected" choice."""
    digest, found, considered = universe_digest(universe), [], 0
    for path in paths:
        considered += 1
        record = records.read_record(path)
        if (record is not None and record.get("checkpoint") == "terminal" and record.get("mode") == "active"
                and record.get("reason") == "default_selection" and not record.get("collection_errors")
                and record.get("head") == gate_run.get("git_head") and record.get("config_sha256") == gate_run.get("pyproject_sha256")
                and record.get("lock_sha256") == gate_run.get("uv_lock_sha256")
                and record.get("selected") == len(universe) and record.get("selection_sha256") == digest and _inside(gate_run, record)):
            found.append(path)
    return found, considered


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def _digest_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def source_identity(root: Path, universe: tuple[str, ...]) -> SourceIdentity:
    """This checkout's identity: the complete status (tracked and untracked, ignored outputs aside) and the newest
    modification of any tracked file, not only source, tests, configuration and lock."""
    import coverage  # noqa: PLC0415

    changed = _git(root, "status", "--porcelain")
    resolved = root.resolve()
    try:
        tracked = tracked_repository_files(root, pathspecs=(".",))
    except TrackedFileInventoryError:  # e.g. a tracked file deleted from the checkout: the status above is already dirty
        tracked = ()
    newest = max(((path.stat().st_mtime, path) for path in tracked), default=None)
    latest = None if newest is None else (
        newest[1].relative_to(resolved).as_posix(), datetime.fromtimestamp(newest[0], timezone.utc).isoformat())
    return SourceIdentity(_git(root, "rev-parse", "HEAD"), _git(root, "rev-parse", "HEAD^{tree}"), _digest_file(root / "pyproject.toml"),
                          _digest_file(root / "uv.lock"), _digest_file(root / CANONICAL_GROUPS), coverage.__version__, universe,
                          clean=not changed, latest_change=latest)


def _default_universe(root: Path) -> tuple[str, ...]:
    from tools.testing import run_profile  # noqa: PLC0415

    return run_profile.collect_universe(root)


def validate_run(coverage_json: Path, gate_report: Path, full_run_manifest: Path, *, root: Path | None = None, groups: Path | None = None,
                 universe: tuple[str, ...] | None = None) -> CoverageVerdict:
    """The validity verdict for one gate run's coverage JSON, bound to the gate's report, to that run's full session
    and to this exact checkout. `universe` defaults to the default selection collected from this source now."""
    root = root or ROOT
    data = coverage_json.read_bytes()
    report = json.loads(data)
    config = root / "pyproject.toml"
    files = package_files(root, groups or root / CANONICAL_GROUPS)
    counts = {path: source_counts(root / path, config) for paths in files.values() for path in paths}
    verdict = evaluate(report, counts, files)
    run = records.read_record(full_run_manifest)
    if run is None:
        return CoverageVerdict((*verdict.problems, f"{full_run_manifest}: not a readable run-context record"))
    identity = source_identity(root, universe if universe is not None else _default_universe(root))
    meta = report.get("meta") if isinstance(report.get("meta"), dict) else {}
    binding = gate_binding_problems(json.loads(gate_report.read_bytes()), hashlib.sha256(data).hexdigest(), run, identity)
    return CoverageVerdict((*verdict.problems, *full_run_problems(run, meta, identity), *binding))


def _side_problems(side: Side, qualifications: list[str]) -> list[str]:
    """Why one side's export is not the proven full session of its own clean canonical run, and whether its gate passed."""
    from tools.testing import run_profile  # noqa: PLC0415

    label = side.label
    problems: list[str] = []
    producer = _offset(side.producer_offset)
    if producer is None:
        problems.append(f"{label}: producer UTC offset {side.producer_offset!r} is not a ±HH:MM offset: timezone unknown, unsupported")
    gate_run = side.report.get("run") if isinstance(side.report.get("run"), dict) else {}
    measured = side.report.get("coverage") if isinstance(side.report.get("coverage"), dict) else {}
    verdict = side.report.get("verdict") if isinstance(side.report.get("verdict"), dict) else {}
    problems += receipt_problems(gate_run, label)  # type: ignore[arg-type]
    if measured.get("coverage_json_sha256") != hashlib.sha256(side.data).hexdigest():  # type: ignore[union-attr]
        problems.append(f"{label}: the JSON is not the export its gate report names")
    if not measured.get("data_file_sha256") or measured.get("data_file_sha256") != gate_run.get("data_file_sha256"):  # type: ignore[union-attr]
        problems.append(f"{label}: the gate report does not name the dataset its run recorded")
    if measured.get("precision") != 0:  # type: ignore[union-attr]
        problems.append(f"{label}: the gate compared at precision {measured.get('precision')}, not the canonical 0")  # type: ignore[union-attr]
    record = side.record
    depth: str | None = "full"
    if label == "base" and "audit_depth" not in record:
        depth = None  # its producer had no audit-depth option: absence is checked, never an explicit stand-in
        if side.depth_proof:
            qualifications.append("base: audit_depth_unrecorded:no-option-at-base")
        else:
            problems.append("base: audit_depth unrecorded and no exact-SHA proof that the producer has no audit-depth option: UNKNOWN")
    problem, _ = run_profile.record_validity(dict(record), gate_run.get("pytest_exit"), audit_depth=depth)  # type: ignore[arg-type]
    if problem is not None:
        problems.append(f"{label}: the run's own record cannot support a result: {problem}")
    if record.get("reason") != "default_selection":
        problems.append(f"{label}: the run was not the default selection ({record.get('reason')})")
    if record.get("collection_errors"):
        problems.append(f"{label}: the run had {record.get('collection_errors')} collection errors")
    if not isinstance(record.get("selected"), int) or not _hex(record.get("selection_sha256"), 64):
        problems.append(f"{label}: the run recorded no selection count and digest")
    if record.get("head") != gate_run.get("git_head"):  # type: ignore[union-attr]
        problems.append(f"{label}: the run-context record measured {record.get('head')}, not the gate's {gate_run.get('git_head')}")  # type: ignore[union-attr]
    if record.get("config_sha256") != gate_run.get("pyproject_sha256") or record.get("lock_sha256") != gate_run.get("uv_lock_sha256"):  # type: ignore[union-attr]
        problems.append(f"{label}: the run-context record used another pyproject.toml or uv.lock than the gate")
    if not _inside(gate_run, record):  # type: ignore[arg-type]
        problems.append(f"{label}: the run-context record is not inside the gate's own run")
    if producer is not None:
        meta = json.loads(side.data).get("meta") or {}
        written, started, finished = _utc(meta.get("timestamp"), producer), _utc(record.get("started_utc")), _utc(record.get("finished_utc"))
        if written is None or started is None or finished is None or not started <= written <= finished + _LATE_REPORT:
            problems.append(f"{label}: the coverage data was written at {written}, outside the run ({started} to {finished})")
    if verdict.get("passed") is not True or gate_run.get("pytest_exit") != 0:  # type: ignore[union-attr]
        failures = "; ".join(str(item) for item in verdict.get("failures") or []) or "no passing verdict"  # type: ignore[union-attr]
        problems.append(f"{label}: the gate failed ({failures}), so its rows are not a passing full run's")
    return problems


def comparable_runs(base: Side, candidate: Side) -> tuple[list[str], list[str]]:
    """Why a base and a candidate export cannot be compared, and the qualifications a comparable pair carries. Each
    side must be the proven full session of its own clean canonical run, both gates passed, and both runs used one
    coverage engine, configuration, groups policy, platform and Python implementation and minor version. Each run's
    configuration and lock bind it to its own source; they need not match across commits."""
    qualifications: list[str] = []
    problems = [*_side_problems(base, qualifications), *_side_problems(candidate, qualifications)]
    runs = [side.report.get("run") if isinstance(side.report.get("run"), dict) else {} for side in (base, candidate)]
    for key in ("coverage_version", "coverage_config", "groups_sha256", "platform", "python_implementation"):
        if runs[0].get(key) != runs[1].get(key):  # type: ignore[union-attr]
            problems.append(f"the runs differ in {key} ({runs[0].get(key)!r}, {runs[1].get(key)!r})")  # type: ignore[union-attr]
    versions = [str(run.get("python_version") or "") for run in runs]  # type: ignore[union-attr]
    if [version.split(".")[:2] for version in versions] != [versions[0].split(".")[:2]] * 2:
        problems.append(f"the runs differ in Python major.minor ({versions[0]}, {versions[1]})")
    elif versions[0] != versions[1]:
        qualifications.append(f"python_patch_differs: base {versions[0]}, candidate {versions[1]}")
    return problems, qualifications


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
            files = {str(name).replace("\\", "/"): row for name, row in ((report.get("files") or {}).items())}  # type: ignore[union-attr]
            row = files.get(path)
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
    for problem in verdict.problems:
        print(f"coverage-products: problem: {records.sanitized_text(problem)[:300]}")
    print(f"coverage-products: full-run validity {'established' if verdict.passed else 'NOT established'}")


def _bound_record(gate_report: Path) -> tuple[Path | None, tuple[str, ...], str]:
    """CI binding: exactly one eligible full session of the gate's run, found under this checkout's run records."""
    gate_run = json.loads(gate_report.read_bytes()).get("run") or {}
    universe = _default_universe(ROOT)
    found, considered = eligible_full_runs(sorted((ROOT / "tmp" / "test-runs").glob("*/run.json")), gate_run, universe)
    if len(found) != 1:
        return None, universe, f"{len(found)} eligible full sessions in the gate's window; none is bound ({considered} records considered)"
    return found[0], universe, f"bound full session {found[0].parent.name} ({considered} records considered)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.testing.coverage_products", description="Product coverage full-run validity.")
    commands = parser.add_subparsers(dest="command", required=True)
    validated = commands.add_parser("validate", help="bind the gate's coverage JSON to its full default session of this source")
    validated.add_argument("--coverage-json", type=Path, required=True)
    validated.add_argument("--gate-report", type=Path, required=True, help="tools/check_product_coverage.py --report-json output")
    validated.add_argument("--run-record", type=Path, default=None, help="its verified run-context run.json (default: exactly one eligible); run on the producing host (its local zone)")
    compared = commands.add_parser("compare", help="compare the safety-critical module rows of two proven gate exports")
    for side in ("base", "candidate"):
        compared.add_argument(f"--{side}", type=Path, required=True)
        compared.add_argument(f"--{side}-report", type=Path, required=True)
        compared.add_argument(f"--{side}-run-record", type=Path, required=True)
        compared.add_argument(f"--{side}-producer-utc-offset", required=True, help="the producer's UTC offset, e.g. +00:00")
    compared.add_argument("--base-audit-depth-proven-absent", action="store_true",
                          help="the base SHA was inspected and has no audit-depth option (v5 Q-C1 receipt)")
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "compare":
            sides = []
            for name in ("base", "candidate"):
                data = getattr(arguments, name).read_bytes()
                # Name the exact files compared, for the evidence that binds them to their CI runs.
                print(f"coverage-products: compared {name} sha256 {hashlib.sha256(data).hexdigest()}")
                sides.append(Side(label=name, report=json.loads(getattr(arguments, f"{name}_report").read_bytes()), data=data,
                                  record=json.loads(getattr(arguments, f"{name}_run_record").read_bytes()),
                                  producer_offset=getattr(arguments, f"{name}_producer_utc_offset"),
                                  depth_proof=name == "base" and arguments.base_audit_depth_proven_absent))
            problems, qualifications = comparable_runs(*sides)
            problems = problems or compare_safety_rows(json.loads(sides[0].data), json.loads(sides[1].data))
            for qualification in qualifications:
                print(f"coverage-products: qualification: {records.sanitized_text(qualification)[:300]}")
            for problem in problems:
                print(f"coverage-products: safety: {records.sanitized_text(problem)[:300]}")
            print(f"coverage-products: safety rows {'regressed or incomparable' if problems else 'comparable, no regression'}")
            return EXIT_REGRESSED if problems else EXIT_PASS
        if arguments.run_record is not None:
            verdict = validate_run(arguments.coverage_json, arguments.gate_report, arguments.run_record, root=ROOT)
        else:
            record, universe, binding = _bound_record(arguments.gate_report)
            print(f"coverage-products: {'problem: ' if record is None else ''}{records.sanitized_text(binding)[:300]}")
            if record is None:
                return EXIT_INVALID
            verdict = validate_run(arguments.coverage_json, arguments.gate_report, record, root=ROOT, universe=universe)
    except gate.CoverageGateError as error:
        print(f"coverage-products: problem: {records.sanitized_text(str(error))[:300]}")
        return EXIT_INVALID
    except (OSError, ValueError) as error:
        print(f"coverage-products: input failure: {records.sanitized_text(str(error))[:300]}")
        return EXIT_INPUT
    _print_verdict(verdict)
    return EXIT_PASS if verdict.passed else EXIT_INVALID


if __name__ == "__main__":
    sys.exit(main())
