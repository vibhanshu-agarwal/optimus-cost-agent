"""Run a change-selected test profile: `python -m tools.testing.run_profile --profile NAME [--base SHA]`.

Test tooling only (Plan 11.30). The runner reads Git and the tracked sources, selects with
`tools/testing/test_profiles.py`, writes one selection record and one evidence manifest, and runs the
selection as ordinary pytest subprocesses of this checkout under the unchanged default `-m`, so each
subrun is an ACTIVE run-context run with its own records. Nothing here changes the index or HEAD.

Git is read with the caller's environment on purpose: inside a pre-commit hook, Git points
`GIT_INDEX_FILE` at the index being committed, and the commit profile must select from that index.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools import process_tree
from tools.testing import run_context
from tools.testing import run_context_records as records
from tools.testing import test_profiles as profiles


def _git(root: Path, *arguments: str) -> bytes:
    completed = subprocess.run(["git", *arguments], cwd=root, capture_output=True, check=False)  # noqa: S603, S607
    if completed.returncode != 0:
        raise profiles.SelectionError(f"git {arguments[0]} failed with exit {completed.returncode}")
    return completed.stdout


def _has_commit(root: Path, revision: str) -> bool:
    completed = subprocess.run(  # noqa: S603, S607
        ["git", "cat-file", "-e", f"{revision}^{{commit}}"], cwd=root, capture_output=True, check=False,
    )
    return completed.returncode == 0


def _untracked(root: Path) -> tuple[profiles.Change, ...]:
    names = _git(root, "ls-files", "--others", "--exclude-standard", "-z").decode("utf-8").split("\0")
    return tuple(profiles.Change("A", name) for name in names if name)


def _working_digest(root: Path, path: str) -> str | None:
    try:
        return hashlib.sha256((root / path).read_bytes()).hexdigest()
    except OSError:
        return None


def _provisional(root: Path, changes: tuple[profiles.Change, ...]) -> tuple[tuple[str, str | None], ...]:
    paths = {path for change in changes for path in (change.path, change.old_path) if path}
    return tuple((path, _working_digest(root, path)) for path in sorted(paths))


def _merged(*groups: tuple[profiles.Change, ...]) -> tuple[profiles.Change, ...]:
    seen: dict[tuple[str, str | None], profiles.Change] = {}
    for group in groups:
        for change in group:
            seen.setdefault((change.path, change.old_path), change)
    return tuple(sorted(seen.values(), key=lambda change: (change.path, change.old_path or "")))


def change_set(root: Path, profile: str, base: str | None, *, exact: bool = False) -> profiles.ChangeSet:
    """The changes a profile selects from.

    commit: the index against HEAD, plus unstaged divergence (tests run working bytes) as provisional.
    quick: the working tree against HEAD, plus untracked files, all provisional.
    checkpoint: the working tree against the recorded base, plus untracked files; whatever is not yet
    committed is provisional. An unreadable base is an unavailable old view (the broad path).
    `exact` refuses any provisional divergence: exact-source acceptance runs committed bytes only.
    """
    if profile == "checkpoint":
        if not base:
            raise profiles.SelectionError("a checkpoint needs --base <recorded checkpoint SHA>")
    elif base:
        raise profiles.SelectionError("--base applies to a checkpoint only; a commit is the index against HEAD")
    diff = ("diff", "--name-status", "-z", "-M")
    if profile == "commit":
        staged = profiles.parse_name_status(_git(root, *diff, "--cached"))
        unstaged = profiles.parse_name_status(_git(root, *diff))
        changes, provisional = _merged(staged, unstaged), _provisional(root, unstaged)
        old_graph = True
    elif profile == "quick":
        working = profiles.parse_name_status(_git(root, *diff, "HEAD")) if _has_commit(root, "HEAD") else ()
        changes = _merged(working, _untracked(root))
        provisional, old_graph = _provisional(root, changes), True
    elif profile == "checkpoint":
        if not _has_commit(root, base or ""):
            return profiles.ChangeSet("checkpoint", (), (), old_graph=False)
        untracked = _untracked(root)
        changes = _merged(profiles.parse_name_status(_git(root, *diff, base or "")), untracked)
        uncommitted = _merged(profiles.parse_name_status(_git(root, *diff, "HEAD")), untracked)
        provisional, old_graph = _provisional(root, uncommitted), True
    else:
        raise profiles.SelectionError(f"profile {profile!r} is not change-selected; change-selected profiles are {list(profiles.CHANGE_SELECTED)}")
    if exact and provisional:
        raise profiles.SelectionError("exact-source acceptance refuses uncommitted divergence: " + ", ".join(path for path, _ in provisional))
    return profiles.ChangeSet("checkpoint" if profile == "checkpoint" else "commit", changes, provisional, old_graph)


# --- Supervised subruns ---------------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
SELECTION_SCHEMA = "test-profile-selection-v1"
RUN_SCHEMA = "test-profile-run-v1"
_OWNED: dict[int, subprocess.Popen[bytes]] = {}  # every subrun process this runner started and has not reaped
_POLL_SECONDS = 0.2
_START_TIMEOUT_SECONDS = 300.0


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _record_time(text: object) -> str | None:
    try:
        return _iso(datetime.fromisoformat(str(text)))
    except ValueError:
        return None


@dataclass
class SubrunResult:
    name: str
    nodes: tuple[str, ...]
    command: tuple[str, ...]
    argfile: Path
    pid: int = 0
    launched: float = 0.0  # time.time() at launch: a run record older than this is another process's
    exit_code: int | None = None
    run_id: str | None = None
    mode: str | None = None
    reason: str | None = None
    started_utc: str | None = None
    executing_utc: str | None = None  # when its first test phase began
    executing_until_utc: str | None = None  # when its last recorded test phase ended
    finished_utc: str | None = None
    terminated: bool = False  # stopped by this runner, not finished on its own
    process_alive: bool = False
    load_run_id: str | None = None  # a repeat: the one load run that ran for the whole of it
    problem: str | None = "not_validated"  # why its own run record cannot support a pass; None when it can
    qualifications: tuple[str, ...] = ()  # the weaker, legitimate labels a supporting record still carries
    audit_depth: str | None = None  # the effective --audit-depth its own terminal record states


_WINDOWS_GUARDS = ("pytest_process_guard", "main5_guard_present")


def record_validity(record: dict[str, object] | None, exit_code: int | None) -> tuple[str | None, tuple[str, ...]]:
    """Whether a finished subrun's own run record supports a pass: its first problem (None when there is none) and
    the qualifications a supporting record still carries. Records arrive through `records.read_record`, so they
    already conform to the run-context field table; this reads their terminal facts as the run's summary line does.
    A capability the platform claims (Windows: a valid native job and a guard) must hold; POSIX's unsupported
    labels and an UNKNOWN parent are qualifications, never failures."""
    if record is None:
        return "no_run_record", ()
    if record.get("checkpoint") != "terminal" or not record.get("finished_utc"):
        return "no_terminal_record", ()
    if record.get("mode") != "active":
        return f"mode_{record.get('mode')}", ()
    if "terminal_failure" in record:
        return "terminal_failure", ()
    if record.get("completeness") != "COMPLETE":
        return f"records_{record.get('completeness')}", ()
    if record.get("exit_status") != exit_code:
        return "exit_status_differs", ()
    # Until quick/full parity (G) is accepted, only a full-depth run counts; a record that does not say is not one.
    if record.get("audit_depth") != "full":
        return f"audit_depth_{record.get('audit_depth') or 'missing'}", ()
    windows = record.get("platform") == "win32"
    native = record.get("native") if isinstance(record.get("native"), dict) else {}
    qualifications: list[str] = []
    if native.get("enrolled") or native.get("attempted"):
        if not (native.get("enrolled") and native.get("valid")):
            return "native_invalid", ()
    elif native.get("supported"):
        return "native_not_enrolled", ()
    elif windows:
        return "native_unsupported", ()
    else:
        qualifications.append("native=unsupported")
    guard = record.get("guard_mode")
    if guard not in (_WINDOWS_GUARDS if windows else ("unsupported_platform",)):
        return f"guard_{guard}", ()
    if guard != "pytest_process_guard":
        qualifications.append(f"guard={guard}")
    elif record.get("protection") != "full":
        qualifications.append(f"protection={record.get('protection')}")
    parent = record.get("parent_run") if isinstance(record.get("parent_run"), dict) else {}
    if parent.get("status") in ("UNKNOWN", "not_found"):
        qualifications.append(f"parent={parent.get('status')}" + (f":{parent.get('reason')}" if parent.get("reason") else ""))
    elif parent.get("status") == "unsupported":
        qualifications.append("parent=unsupported")
    if native.get("enrolled"):
        accounting, members = record.get("accounting"), record.get("members")
        if not (isinstance(accounting, dict) and accounting.get("ok")):
            qualifications.append("processes=QUERY_FAILED")  # as the run's own summary line says
        if not (isinstance(members, dict) and members.get("ok") and members.get("complete")):
            qualifications.append("members=incomplete")
    return None, tuple(qualifications)


def owned_processes_alive() -> int:
    """How many subrun processes this runner started are still running."""
    return sum(1 for process in _OWNED.values() if process.poll() is None)


def _stop(process: subprocess.Popen[bytes]) -> None:
    """Stop one owned subrun tree. Never touches a process this runner did not start."""
    if process.poll() is None:
        process_tree.kill_tree(process)
        process.wait(timeout=60)


def _stop_all_owned() -> None:
    for process in list(_OWNED.values()):
        _stop(process)
    _OWNED.clear()


def start_subrun(root: Path, out_dir: Path, name: str, nodes: tuple[str, ...], *, env: dict[str, str] | None = None) -> tuple[SubrunResult, subprocess.Popen[bytes]]:
    """Start one pytest session of exactly `nodes` under the unchanged default selection (so ACTIVE)."""
    folder = out_dir / name
    folder.mkdir(parents=True, exist_ok=True)
    argfile = folder / "nodes.txt"
    argfile.write_bytes("".join(f"{node}\n" for node in nodes).encode("utf-8"))
    command = (sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "--no-cov", "-q", "--audit-depth=full", f"@{argfile}")
    launched = time.time()
    # Like any pytest run, the session writes to the console; its identity, mode and times come from its
    # own run records, so no raw test output is kept here.
    process = process_tree.popen(list(command), cwd=root, env=env)
    _OWNED[process.pid] = process
    return SubrunResult(name, nodes, command, argfile, pid=process.pid, launched=launched, process_alive=True), process


def _run_record(root: Path, pid: int, launched: float) -> tuple[Path, dict[str, object]] | None:
    """The run record of the session this subrun process started: same pid, started after its launch."""
    runs = root / "tmp" / "test-runs"
    try:
        folders = [folder for folder in runs.iterdir() if folder.is_dir()]
    except OSError:
        return None
    for folder in folders:
        record = records.read_record(folder / "run.json")
        if record is None:
            continue
        # On Windows a venv's python.exe is a launcher: the session's root is its child, so the
        # process this runner started appears as the root's parent.
        pids = {identity.get("pid") for identity in (record.get("root"), record.get("root_parent")) if isinstance(identity, dict)}
        started = _record_time(record.get("started_utc"))
        recent = started is not None and datetime.fromisoformat(started).timestamp() >= launched - 1.0
        if pid in pids and recent:
            return folder, record
    return None


def _first_phase_at(folder: Path) -> float | None:
    entries, _, _ = records.read_entries(folder / "phases.jsonl", "phases")
    return float(entries[0]["at"]) if entries else None  # type: ignore[arg-type]


def wait_until_executing(root: Path, result: SubrunResult, process: subprocess.Popen[bytes]) -> bool:
    """Block until the subrun has begun its first test phase (True) or has ended without one (False)."""
    deadline = time.monotonic() + _START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        found = _run_record(root, result.pid, result.launched)
        if found is not None and _first_phase_at(found[0]) is not None:
            return True
        if process.poll() is not None:
            return False
        time.sleep(_POLL_SECONDS)
    raise profiles.SelectionError(f"subrun {result.name} did not begin a test phase within {_START_TIMEOUT_SECONDS:.0f} s")


def finish_subrun(root: Path, result: SubrunResult, process: subprocess.Popen[bytes], *, terminate: bool = False) -> SubrunResult:
    """Reap a subrun (stopping it first when asked) and read its identity and times from its records."""
    if terminate and process.poll() is None:
        _stop(process)
        result.terminated = True
        result.finished_utc = _iso(datetime.now(timezone.utc))
    result.exit_code = process.wait()
    _OWNED.pop(process.pid, None)
    result.process_alive = False
    located = _run_record(root, result.pid, result.launched)
    result.problem, result.qualifications = record_validity(None if located is None else located[1], result.exit_code)
    if located is not None:
        folder, record = located
        result.run_id, result.mode, result.reason = str(record.get("run_id")), str(record.get("mode")), str(record.get("reason"))
        result.audit_depth = None if record.get("audit_depth") is None else str(record.get("audit_depth"))
        result.started_utc = _record_time(record.get("started_utc"))
        if not result.terminated:
            result.finished_utc = _record_time(record.get("finished_utc"))
        entries, _, _ = records.read_entries(folder / "phases.jsonl", "phases")
        if entries and result.started_utc:
            began = datetime.fromisoformat(result.started_utc)
            result.executing_utc = _iso(began + timedelta(seconds=float(entries[0]["at"])))  # type: ignore[arg-type]
            last = max(float(entry["at"]) + float(entry["seconds"]) for entry in entries)  # type: ignore[arg-type]
            result.executing_until_utc = _iso(began + timedelta(seconds=last))
    return result


def run_subrun(root: Path, out_dir: Path, name: str, nodes: tuple[str, ...], *, env: dict[str, str] | None = None) -> SubrunResult:
    result, process = start_subrun(root, out_dir, name, nodes, env=env)
    try:
        return finish_subrun(root, result, process)
    finally:
        _stop(process)
        _OWNED.pop(process.pid, None)


def covers(load: SubrunResult, attempt: SubrunResult) -> bool:
    """Whether a repeat ran wholly inside its load's recorded test phases: it began after the load's first phase
    began and ended before the load's last recorded phase ended (not merely before the load's session ended).
    The repeat's own record must support a pass; so must the load's, unless this runner stopped the load, whose
    recorded phases still bound when it was executing."""
    if attempt.problem is not None or (load.problem is not None and not load.terminated) or load.mode != "active":
        return False
    begun, until = load.executing_utc, load.executing_until_utc
    started, ended = attempt.started_utc, attempt.finished_utc
    return begun is not None and until is not None and started is not None and ended is not None and begun <= started and ended <= until


@dataclass(frozen=True)
class OverlapOutcome:
    verdict: str  # "complete", "failed", "unrun" or "invalid" (a load never began its tests)
    required: SubrunResult  # the checkpoint-required full-depth load run
    loads: tuple[SubrunResult, ...]  # every load iteration, the required one first
    attempts: tuple[SubrunResult, ...]  # every repeat that ran, in order
    counted: tuple[SubrunResult, ...]  # the repeats one load run covered completely
    detail: str


def overlap(
    root: Path, out_dir: Path, load_nodes: tuple[str, ...], repeat_nodes: tuple[str, ...], *, repeats: int = 3,
    max_attempts: int | None = None, env: dict[str, str] | None = None, progress: Callable[[str], None] | None = None,
) -> OverlapOutcome:
    """Windows checkpoint stability: run `repeat_nodes` `repeats` times, each completely inside one running
    load run of `load_nodes` (the required full-depth current audit; repeated only as needed to keep
    the overlap). A repeat counts only when its load had begun executing before it started and was
    still running when it ended. Failures stop the lane and are kept; nothing is retried to green."""
    notify = progress or (lambda event: None)
    limit = max_attempts or repeats * 3
    loads: list[SubrunResult] = []
    attempts: list[SubrunResult] = []
    counted: list[SubrunResult] = []
    covering: dict[int, SubrunResult] = {}  # attempt index -> the load that covered it
    processes: dict[str, subprocess.Popen[bytes]] = {}
    reaped: set[str] = set()
    verdict, detail = "unrun", ""
    try:
        required, process = start_subrun(root, out_dir, "load-1", load_nodes, env=env)
        loads.append(required)
        processes[required.name] = process
        notify("load-1 started")
        current = required
        while len(covering) < repeats and len(attempts) < limit and len(loads) <= limit:
            try:
                executing = wait_until_executing(root, current, processes[current.name])
            except profiles.SelectionError as error:  # a load that never began its tests: stop, keep what ran
                verdict, detail = "invalid", records.sanitized_text(str(error))[:300]
                break
            if not executing or processes[current.name].poll() is not None:
                finish_subrun(root, current, processes[current.name])
                reaped.add(current.name)
                notify(f"{current.name} finished exit={current.exit_code}")
                if current.exit_code != 0:
                    verdict, detail = "failed", f"load run {current.name} exited {current.exit_code}"
                    break
                current, process = start_subrun(root, out_dir, f"load-{len(loads) + 1}", load_nodes, env=env)
                loads.append(current)
                processes[current.name] = process
                notify(f"{current.name} started")
                continue
            name = f"repeat-{len(attempts) + 1}"
            notify(f"{name} started")
            attempt = run_subrun(root, out_dir, name, repeat_nodes, env=env)
            attempts.append(attempt)
            still_running = processes[current.name].poll() is None
            notify(f"{name} finished exit={attempt.exit_code}")
            if attempt.exit_code != 0:
                verdict, detail = "failed", f"{name} exited {attempt.exit_code}"
                break
            if still_running:
                covering[len(attempts) - 1] = current
        for load in [load for load in loads if load.name not in reaped]:
            alive = processes[load.name].poll() is None
            # The required load always runs to its end; an extra load iteration is load only.
            finish_subrun(root, load, processes[load.name], terminate=verdict in ("failed", "invalid") or (load is not required and alive))
        for index, load in covering.items():
            attempt = attempts[index]
            if covers(load, attempt):
                attempt.load_run_id = load.run_id
                counted.append(attempt)
        if verdict not in ("failed", "invalid"):
            if required.exit_code != 0:
                verdict, detail = "failed", f"required load run exited {required.exit_code}"
            elif len(counted) >= repeats:
                verdict, detail = "complete", f"{len(counted)} repeats each inside one load run's recorded test phases"
            else:
                verdict, detail = "unrun", f"only {len(counted)} of {repeats} repeats were completely overlapped in {len(attempts)} attempts"
    finally:
        _stop_all_owned()
    return OverlapOutcome(verdict, loads[0], tuple(loads), tuple(attempts), tuple(counted), detail)


# --- Selection record, execution and the command line ---------------------------------------------------

EXIT_PASS, EXIT_TESTS_FAILED, EXIT_INPUT, EXIT_INVALID = 0, 1, 2, 3


def _tracked(root: Path) -> tuple[str, ...]:
    return tuple(name for name in _git(root, "ls-files", "-z").decode("utf-8").split("\0") if name)


def repository_inputs(root: Path, changes: profiles.ChangeSet) -> tuple[dict[str, str], tuple[str, ...]]:
    """Tracked files (plus new files the change set adds) and the working text of every Python source."""
    added = tuple(change.path for change in changes.changes if change.status == "A")
    tracked = tuple(sorted({*_tracked(root), *added}))
    sources: dict[str, str] = {}
    for path in tracked:
        if path.endswith(".py"):
            try:
                sources[path] = (root / path).read_bytes().decode("utf-8")
            except (OSError, UnicodeDecodeError):
                continue  # deleted in the working tree, or not text: its edges are unknown
    return sources, tracked


def collect_universe(root: Path, env: dict[str, str] | None = None) -> tuple[str, ...]:
    """The node IDs of the unchanged default selection, collected by pytest itself."""
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=root, env=env, capture_output=True, check=False,
    )
    if completed.returncode != 0:
        raise profiles.SelectionError(f"collecting the default selection failed with exit {completed.returncode}")
    lines = completed.stdout.decode("utf-8", errors="replace").splitlines()
    return tuple(line.strip() for line in lines if line.startswith("tests/") and "::" in line)


def _digest(text: str | bytes) -> str:
    return hashlib.sha256(text.encode("utf-8") if isinstance(text, str) else text).hexdigest()


def classification_digest(classification: profiles.Classification) -> str:
    return _digest("".join(f"{node}\t{classification.tiers[node]}\n" for node in sorted(classification.tiers)))


def selection_record(
    root: Path, changes: profiles.ChangeSet, selection: profiles.Selection, classification: profiles.Classification,
    manifest: profiles.ProfileManifest, base: str | None,
) -> dict[str, object]:
    """The additive, versioned selection record: what was selected from what, and why."""
    head = _git(root, "rev-parse", "--verify", "-q", "HEAD").decode().strip() if _has_commit(root, "HEAD") else None
    grouped: dict[str, list[str]] = {}
    for node in selection.nodes:
        grouped.setdefault(selection.reasons[node], []).append(run_context._node(node))  # noqa: SLF001
    record: dict[str, object] = {
        "schema": SELECTION_SCHEMA, "profile": selection.profile, "label": selection.label, "view": changes.view,
        "platform": sys.platform, "base": base, "head": head,
        "index_sha256": _digest(_git(root, "diff", "--cached", "--binary")),
        "working_sha256": _digest(_git(root, "diff", "--binary")),
        "manifest_sha256": manifest.digest, "classification_sha256": classification_digest(classification),
        "changes": [[change.status, change.path, change.old_path] for change in changes.changes],
        "old_view_available": changes.old_graph,
        "provisional": [[path, digest] for path, digest in selection.provisional],
        "collected": len(classification.tiers), "selected": len(selection.nodes),
        "deselected": len(classification.tiers) - len(selection.nodes),
        # Node IDs are filesystem text (some carry credential-shaped test parameters): like the run-context
        # node stream, the record keeps each node's digest and a label only where the sanitizer leaves it.
        "nodes": [{"node": run_context._node(node), "label": run_context._label(node)} for node in selection.nodes],  # noqa: SLF001
        "reasons": grouped,
        "fallback": list(selection.fallback), "domains": selection.domains,
        "platform_triggers": list(selection.platform_triggers), "obligations": list(selection.obligations),
        "concurrency": list(selection.concurrency), "audit_depth": selection.audit_depth,
    }
    if not records.unchanged_by_shared_sanitizer(record):
        raise profiles.SelectionError("the selection record would be changed by the shared sanitizer; nothing was run")
    return record


def _write_json(path: Path, value: dict[str, object]) -> str:
    data = (json.dumps(value, indent=1, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(data)
    return _digest(data)


def _subrun_entry(result: SubrunResult) -> dict[str, object]:
    return {
        "name": result.name, "run_id": result.run_id, "mode": result.mode, "reason": result.reason, "exit": result.exit_code,
        "nodes": len(result.nodes), "nodes_sha256": _digest(result.argfile.read_bytes()), "started_utc": result.started_utc,
        "executing_utc": result.executing_utc, "executing_until_utc": result.executing_until_utc,
        "finished_utc": result.finished_utc, "terminated": result.terminated, "load_run_id": result.load_run_id,
        "audit_depth": result.audit_depth,
        "record_problem": result.problem, "qualifications": list(result.qualifications),
    }


def execute(
    root: Path, out_dir: Path, selection: profiles.Selection, classification: profiles.Classification,
    *, env: dict[str, str] | None = None, progress: Callable[[str], None] | None = None,
) -> tuple[str, int, list[SubrunResult], OverlapOutcome | None, str]:
    """Run the selection: one serial subrun; at a checkpoint, then the full-depth current audit, under which
    Windows repeats the selected concurrency nodes three times (POSIX runs them once, serially, without load).
    Returns the verdict, its exit code, the subruns, the overlap outcome and a detail line. A failure stays a
    failure; a pass needs every finished subrun's own terminal record to support it."""
    if selection.label != "selected":
        return selection.label, EXIT_PASS, [], None, ""
    audits = tuple(node for node in selection.nodes if classification.tiers[node] == "audit-current")
    main = tuple(node for node in selection.nodes if node not in set(audits))
    if not main and not audits:
        return "empty-selection", EXIT_PASS, [], None, ""
    subruns: list[SubrunResult] = []
    outcome: OverlapOutcome | None = None
    stopped: str | None = None
    try:
        if main:
            subruns.append(run_subrun(root, out_dir / "subruns", "selected", main, env=env))
        if audits and sys.platform == "win32" and selection.concurrency:
            outcome = overlap(root, out_dir / "subruns", audits, selection.concurrency, env=env, progress=progress)
            subruns += [*outcome.loads, *outcome.attempts]
        elif audits:
            subruns.append(run_subrun(root, out_dir / "subruns", "audit-current", audits, env=env))
    except profiles.SelectionError as error:  # a subrun that never began its tests: the run itself failed
        _stop_all_owned()
        stopped = records.sanitized_text(str(error))[:300]
    finished = [result for result in subruns if not result.terminated]
    failed = [f"{result.name} exited {result.exit_code}" for result in finished if result.exit_code not in (0, None)]
    if outcome is not None and outcome.verdict == "failed":
        failed.append(outcome.detail)
    if failed:
        return "failed", EXIT_TESTS_FAILED, subruns, outcome, "; ".join(failed)
    if outcome is not None and outcome.verdict == "invalid":
        stopped = outcome.detail
    if stopped is not None:
        return "invalid", EXIT_INVALID, subruns, outcome, stopped
    # A subrun whose own record cannot support a pass is named, even when it is also why repeats went uncounted.
    problems = [f"{result.name}: {result.problem}" for result in finished if result.problem is not None]
    if problems:
        return "invalid", EXIT_INVALID, subruns, outcome, "; ".join(problems)
    if outcome is not None and outcome.verdict == "unrun":
        return "stability-unrun", EXIT_INVALID, subruns, outcome, outcome.detail
    if outcome is not None and outcome.verdict != "complete":
        return "invalid", EXIT_INVALID, subruns, outcome, f"unknown stability verdict {outcome.verdict}"
    return "pass", EXIT_PASS, subruns, outcome, ""


def failure_line(profile: str, error: Exception) -> str:
    """The one line an input failure prints. Its detail names repository paths, so it passes the shared sanitizer."""
    return f"test-profile: profile={profile} verdict=input-failure detail={records.sanitized_text(str(error))[:300]}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.testing.run_profile", description="Run a change-selected test profile.")
    parser.add_argument("--profile", required=True, choices=profiles.CHANGE_SELECTED)
    parser.add_argument("--base", default=None, help="checkpoint: the recorded immutable checkpoint base SHA")
    parser.add_argument("--exact", action="store_true", help="refuse uncommitted divergence (exact-source acceptance)")
    parser.add_argument("--dry-run", action="store_true", help="select and write the selection record; run nothing")
    parser.add_argument("--output", type=Path, default=None, help="evidence folder (default: tmp/test-profiles)")
    arguments = parser.parse_args(argv)
    invocation = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{os.getpid()}-{secrets.token_hex(3)}"
    out_dir = (arguments.output or ROOT / "tmp" / "test-profiles") / invocation
    try:
        manifest = profiles.load_manifest((ROOT / "tests" / "profiles.toml").read_text(encoding="utf-8"))
        changes = change_set(ROOT, arguments.profile, arguments.base, exact=arguments.exact)
        sources, tracked = repository_inputs(ROOT, changes)
        classification = profiles.classify_nodes(collect_universe(ROOT), manifest)
        dependencies = profiles.build_dependency_map(sources, tracked, manifest)
        selection = profiles.select_tests(changes, classification, dependencies, profiles.ProfileRequest(arguments.profile))
        record = selection_record(ROOT, changes, selection, classification, manifest, arguments.base)
    except (OSError, profiles.ManifestError, profiles.ClassificationError, profiles.SelectionError) as error:
        print(failure_line(arguments.profile, error))
        return EXIT_INPUT
    out_dir.mkdir(parents=True, exist_ok=True)
    record_sha = _write_json(out_dir / "selection.json", record)
    fallback = "broad" if selection.fallback else "none"
    summary = (
        f"test-profile: profile={arguments.profile} label={selection.label} selected={len(selection.nodes)} "
        f"deselected={len(classification.tiers) - len(selection.nodes)} fallback={fallback} "
        f"platform={'triggered' if selection.platform_triggers else 'none'} obligations={','.join(selection.obligations) or 'none'}"
    )
    if arguments.dry_run:
        print(f"{summary} verdict=dry-run record={out_dir / 'selection.json'}")
        return EXIT_PASS
    verdict, code, subruns, outcome, detail = execute(
        ROOT, out_dir, selection, classification, progress=lambda event: print(f"test-profile: {event}", flush=True))
    run_manifest: dict[str, object] = {
        "schema": RUN_SCHEMA, "invocation": invocation, "profile": arguments.profile, "platform": sys.platform,
        "verdict": verdict, "exit": code, "detail": detail, "selection_sha256": record_sha,
        "subruns": [_subrun_entry(result) for result in subruns],
        "stability": None if outcome is None else {
            "verdict": outcome.verdict, "detail": outcome.detail, "required_load_run_id": outcome.required.run_id,
            "counted_repeat_run_ids": [result.run_id for result in outcome.counted],
        },
        "obligations": list(selection.obligations),
    }
    if not records.unchanged_by_shared_sanitizer(run_manifest):
        print(f"{summary} verdict=invalid detail=evidence manifest refused by the shared sanitizer")
        return EXIT_INVALID
    _write_json(out_dir / "manifest.json", run_manifest)
    print(f"{summary} verdict={verdict}{f' detail={detail}' if detail else ''} manifest={out_dir / 'manifest.json'}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
