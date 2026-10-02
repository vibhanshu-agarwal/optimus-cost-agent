"""Run context for pytest: which run this is, what it owns, and what else was running.

Test tooling only, loaded from `tests/conftest.py`. Importing it has no side effects. A session
that uses the unchanged default marker selection (including a focused subset of it) is ACTIVE: on
Windows it owns a new job object and the pytest process is guarded against the real application
folders. Every other session is PASSIVE: it is recorded, and nothing else about it changes.

The context creates no thread, timer or helper process. It never reads a command line and never
opens another run's job.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from tools.testing import run_context_guard as guard
from tools.testing import run_context_records as records
from tools.testing import run_context_windows as native

OPTION_DEST = "test_run_context"
ACTIVE = "active"
PASSIVE = "passive"
UNKNOWN = "UNKNOWN"

# The approved default selection, frozen here on purpose. A session's own configuration can be
# replaced from the command line, the environment or another config file, so it is never the
# comparator. A guardrail test keeps this list equal to the repository's pyproject.toml.
EXCLUDED_BY_DEFAULT = (
    "requires_redis", "requires_gateway", "requires_mcp_http", "requires_mcp_stdio", "e2e", "requires_live_gateway",
    "requires_phoenix", "requires_os_keyring", "requires_os_keyring_write", "requires_acpx", "requires_zed",
    "requires_windows_desktop", "evidence_investigation", "requires_evidence_handoff_postgres",
    "requires_evidence_handoff_service", "requires_real_agents",
)
APPROVED_DEFAULT_MARKER_EXPRESSION = " and ".join(f"not {name}" for name in EXCLUDED_BY_DEFAULT)
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


# Frozen ceilings on one run's streams. A stream that reaches its ceiling stops and the record says so.
MAX_STREAM_RECORDS = {"nodes": 40_000, "phases": 60_000, "samples": 5_000}
# Entries whose append failed for a reason outside the entry itself wait here for the next append.
MAX_PENDING_ENTRIES = 2_000


@dataclass
class RunContext:
    run_id: str
    mode: str
    reason: str
    record_dir: Path
    started_utc: str
    worktree: str
    branch: str | None = None
    head: str | None = None
    declared_agent: str | None = None
    root: dict[str, object] = field(default_factory=dict)
    root_parent: dict[str, object] = field(default_factory=dict)
    parent_run: dict[str, object] = field(default_factory=dict)
    native: dict[str, object] = field(default_factory=dict)
    guard_mode: str = "not_installed"
    session_index: int = 1
    started_monotonic: float = 0.0
    started_wall: float = 0.0
    facts: dict[str, object] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=lambda: {
        "nodes": 0, "phases": 0, "samples": 0, "selected": 0, "deselected": 0, "collection_errors": 0,
        "recording_errors": 0, "deferred_appends": 0,
    })
    truncated: bool = False
    last_sample: float = 0.0
    ceilings: dict[str, int] = field(default_factory=lambda: dict(MAX_STREAM_RECORDS))
    pending: dict[str, list[dict[str, object]]] = field(default_factory=lambda: {"nodes": [], "phases": [], "samples": []})
    selection: object = field(default_factory=hashlib.sha256)


_sessions_started = 0
_current: RunContext | None = None
SAMPLE_INTERVAL_SECONDS = 5.0


def current() -> RunContext | None:
    """The context of the pytest session now running in this interpreter, if any."""
    return _current


def _uses_repository_configuration(config: object) -> bool:
    """Whether the session was configured by this checkout's own pyproject.toml and nothing else."""
    try:
        inipath, rootpath = getattr(config, "inipath", None), getattr(config, "rootpath", None)
        if inipath is None or rootpath is None:
            return False
        return (
            Path(str(inipath)).resolve() == (_REPOSITORY_ROOT / "pyproject.toml").resolve()
            and Path(str(rootpath)).resolve() == _REPOSITORY_ROOT
        )
    except OSError:
        return False


def classify(config: object) -> tuple[str, str]:
    """ACTIVE only for the approved default selection under the repository's own configuration.

    The effective `-m` expression is compared with the frozen approved expression, as text. A file
    or `-k` subset of the default selection stays ACTIVE. Anything else is PASSIVE: another
    expression (even an equivalent one written differently), an overridden `addopts`, another
    config file or root, a collection-only run, or an explicit request.
    """
    option = config.option  # type: ignore[attr-defined]
    if getattr(option, OPTION_DEST, "auto") == "passive":
        return PASSIVE, "requested"
    if getattr(option, "collectonly", False):
        return PASSIVE, "collection_only"
    if not _uses_repository_configuration(config):
        return PASSIVE, "foreign_configuration"
    overrides = getattr(option, "override_ini", None) or ()
    if any(str(entry).split("=", 1)[0].strip() == "addopts" for entry in overrides):
        return PASSIVE, "overridden_addopts"
    if (getattr(option, "markexpr", "") or "") != APPROVED_DEFAULT_MARKER_EXPRESSION:
        return PASSIVE, "non_default_selection"
    return ACTIVE, "default_selection"


def _identity(identity: native.ProcessIdentity) -> dict[str, object]:
    image = identity.image if identity.image is not None and records.IMAGE.fullmatch(identity.image) else None
    return {"pid": identity.pid, "creation_time": identity.creation_time, "image": image, "error": identity.error,
            "live": identity.live}


def _bounded(value: str | None, pattern: object) -> str | None:
    """A value fit to persist, or None when it breaks its pattern or the shared sanitizer would change it."""
    if value is None or pattern.fullmatch(value) is None:  # type: ignore[attr-defined]
        return None
    return value if records.unchanged_by_shared_sanitizer(value) else None


def _git_identity(worktree: Path) -> tuple[str | None, str | None]:
    """Branch and commit read from the checkout's own files, without starting a process."""
    try:
        marker = worktree / ".git"
        git_dir = marker
        if marker.is_file():
            text = marker.read_text(encoding="utf-8").strip()
            if not text.startswith("gitdir:"):
                return None, None
            git_dir = Path(text.split(":", 1)[1].strip())
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref:"):
            return None, head
        reference = head.split(":", 1)[1].strip()
        branch = reference.removeprefix("refs/heads/")
        common = git_dir
        common_marker = git_dir / "commondir"
        if common_marker.is_file():
            common = (git_dir / common_marker.read_text(encoding="utf-8").strip()).resolve()
        for base in (git_dir, common):
            candidate = base / reference
            if candidate.is_file():
                return branch, candidate.read_text(encoding="utf-8").strip()
        packed = common / "packed-refs"
        if packed.is_file():
            for line in packed.read_text(encoding="utf-8").splitlines():
                if line.endswith(" " + reference):
                    return branch, line.split(" ", 1)[0]
        return branch, None
    except OSError:
        return None, None


def _declared_agent(branch: str | None) -> str | None:
    """The agent named in an `agent/<name>/...` branch. Provenance the branch supplies, not proof."""
    parts = (branch or "").split("/")
    return parts[1] if len(parts) >= 3 and parts[0] == "agent" else None


def _whole_number(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _discover_parent_run(run_id: str) -> dict[str, object]:
    """Which registered active run, if any, this process descends from.

    A child cannot see its parent run's job: the Python venv launcher puts every interpreter it
    starts into a job of its own, so a process's immediate job holds only itself. The parent is
    therefore found by ancestry: the nearest running ancestor whose PID and creation time match a
    registered active root. This names a relationship only; ownership and cleanup stay with each
    run's own job. No job is opened and no command line is read.

    The answer is `parent` when a match is found, `none` only when the whole chain was followed to
    its end without one, `not_found` when the visible chain ended at an exited ancestor (earlier
    ancestors cannot be seen, so absence is not established), and UNKNOWN when any query failed.
    """
    method = "validated_process_ancestry"
    chain, stopped = native.ancestors()
    roots: dict[tuple[int, int], str] = {}
    for entry in records.registry_entries(run_id):
        # The reader guarantees a complete root identity. An entry that still lacks one, or whose
        # creation time was never read, names no ancestor and is passed over, never raised on.
        root = entry.get("root")
        pid, created = (root.get("pid"), root.get("creation_time")) if isinstance(root, dict) else (None, None)
        named = entry.get("run_id")
        if entry.get("mode") == ACTIVE and _whole_number(pid) and _whole_number(created) and isinstance(named, str):
            roots[(pid, created)] = named
    for ancestor in chain:
        found = roots.get((ancestor.pid, ancestor.creation_time or -1)) if ancestor.live is True else None
        if found is not None:
            return {"status": "parent", "run_id": found, "method": method}
    if stopped == "root_reached":
        return {"status": "none", "method": method}
    if stopped == "ancestor_exited":
        return {"status": "not_found", "reason": stopped, "method": method}
    return {"status": UNKNOWN, "reason": stopped, "method": method}


def start_run(config: object) -> RunContext:
    """Classify the session, enrol and guard an active one, and write its first record."""
    global _sessions_started
    mode, reason = classify(config)
    enrolled_before = native.supported() and native.owner() is not None
    if enrolled_before and mode == PASSIVE:
        import pytest

        raise pytest.UsageError(
            "test-run-context: this interpreter already started an active default run; "
            "start this selection in a separate interpreter"
        )
    _sessions_started += 1
    worktree = Path(str(config.rootpath))  # type: ignore[attr-defined]
    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{os.getpid()}-{secrets.token_hex(3)}"
    branch, head = _git_identity(worktree)
    context = RunContext(
        run_id=run_id, mode=mode, reason=reason, record_dir=worktree / "tmp" / "test-runs" / run_id,
        started_utc=datetime.now(timezone.utc).isoformat(), worktree=str(worktree), branch=branch, head=head,
        declared_agent=_declared_agent(branch), session_index=_sessions_started,
    )
    if native.supported():
        context.root = _identity(native.current_identity())
        context.root_parent = _identity(native.parent_identity())
        context.parent_run = {"status": "same_interpreter"} if enrolled_before else _discover_parent_run(run_id)
        if mode == ACTIVE:
            owner = native.enroll(run_id)
            context.native = {"supported": True, "attempted": True, "valid": owner.valid, "job_name": owner.name,
                              "reused_from_earlier_session": enrolled_before, **owner.facts}
        else:
            context.native = {"supported": True, "attempted": False, "enrolled": False}
    else:
        context.root = {"pid": os.getpid(), "creation_time": None, "image": None, "error": None, "live": True}
        context.native = {"supported": False, "attempted": False, "enrolled": False}
        context.parent_run = {"status": "unsupported"}
    if mode == ACTIVE:
        context.guard_mode = guard.install()
    context.started_monotonic, context.started_wall = time.monotonic(), time.time()
    context.facts = _session_facts(worktree)
    if context.native.get("enrolled") and enrolled_before:
        # A later session in the same interpreter shares the job: its own activity is the
        # difference between the terminal totals and this baseline.
        context.facts["accounting_baseline"] = native.accounting()
    payload = _payload(context, checkpoint="start")
    records.write_record(context.record_dir / "run.json", payload)
    records.write_record(records.registry_root() / f"{run_id}.json", payload)
    global _current
    _current = context
    if context.parent_run.get("status") not in {"parent", "same_interpreter"}:
        records.prune_run_folders(context.record_dir.parent, run_id)
    sample_run(context, "start")
    return context


def _file_digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _session_facts(worktree: Path) -> dict[str, object]:
    import pytest

    return {
        "python": ".".join(str(part) for part in sys.version_info[:3]), "pytest": _bounded_version(pytest.__version__),
        "lock_sha256": _file_digest(worktree / "uv.lock"), "config_sha256": _file_digest(worktree / "pyproject.toml"),
        "protected_roots": len(guard.protected_roots()), "protection": guard.protection(),
    }


def _bounded_version(value: str) -> str:
    return "".join(char for char in value if char.isalnum() or char in ".+-")[:40] or "unknown"


def _node(nodeid: str) -> str:
    """The exact identity of a test: a digest of its raw node ID, so two tests never collapse into one."""
    return hashlib.sha256(nodeid.encode("utf-8")).hexdigest()


def _label(nodeid: str) -> str | None:
    """A bounded display label for a node ID, or None when the shared sanitizer would change the ID.

    The raw ID is checked first, before any character is replaced, so replacing characters can
    never turn text the sanitizer recognises into text it does not.
    """
    if not records.unchanged_by_shared_sanitizer(nodeid):
        return None
    label = "".join(char if records.LABEL.fullmatch(char) else "_" for char in nodeid)[:200]
    return label if label and records.unchanged_by_shared_sanitizer(label) else None


def _reason(text: object) -> str:
    """A skip reason as the shared sanitizer leaves it, printable and bounded."""
    cleaned = "".join(char if " " <= char <= "~" else " " for char in str(text))[:200]
    return "".join(char if " " <= char <= "~" else " " for char in records.sanitized_text(cleaned))[:200]


def _append(context: RunContext, stream: str, entries: list[dict[str, object]]) -> None:
    """Append to a stream within its ceiling. Nothing here raises.

    An entry the table refuses is a recording error. An append that fails for a reason outside the
    entries (a test has patched the serializer, the file is briefly locked) is deferred: the batch
    waits, in order, for the next append of that stream, and `finish_run` makes a last attempt.
    """
    pending = context.pending[stream]
    batch = [*pending, *entries]
    pending.clear()
    if not batch:
        return
    if context.counts[stream] + len(batch) > context.ceilings[stream]:
        context.truncated = True
        return
    try:
        records.append_entries(context.record_dir / f"{stream}.jsonl", stream, batch)
        context.counts[stream] += len(batch)
    except records.RecordTooLarge:
        context.truncated = True
    except ValueError:
        context.counts["recording_errors"] += 1
    except Exception:  # noqa: BLE001 - the cause is outside the entries; keep them for the next attempt
        if len(batch) > MAX_PENDING_ENTRIES:
            context.counts["recording_errors"] += 1
        else:
            pending.extend(batch)
            context.counts["deferred_appends"] += 1


def record_collection(context: RunContext, selected: list[str], deselected: list[str]) -> None:
    """Keep the identity of every collected test, selected or deselected, independently of its outcome."""
    entries = []
    for state, nodeids in (("selected", selected), ("deselected", deselected)):
        for nodeid in nodeids:
            entries.append({"node": _node(nodeid), "label": _label(nodeid), "state": state})
        context.counts[state] += len(nodeids)
    for nodeid in sorted(selected):
        context.selection.update(_node(nodeid).encode("ascii"))  # type: ignore[attr-defined]
    for start in range(0, len(entries), 2000):
        _append(context, "nodes", entries[start:start + 2000])


def record_collection_error(context: RunContext) -> None:
    context.counts["collection_errors"] += 1


def record_phase(context: RunContext, report: object) -> None:
    """Keep one test phase, then take a sample if one is due. Runs synchronously; never raises."""
    try:
        entry: dict[str, object] = {
            "node": _node(str(report.nodeid)), "when": str(report.when), "outcome": str(report.outcome),  # type: ignore[attr-defined]
            "at": round(max(0.0, float(getattr(report, "start", context.started_wall)) - context.started_wall), 3),
            "seconds": round(max(0.0, float(getattr(report, "duration", 0.0))), 3),
        }
        if entry["outcome"] == "skipped":
            longrepr = getattr(report, "longrepr", None)
            detail = longrepr[2] if isinstance(longrepr, tuple) and len(longrepr) == 3 else getattr(report, "wasxfail", "")
            entry["reason"] = _reason(detail)
        _append(context, "phases", [entry])
        if time.monotonic() - context.last_sample >= SAMPLE_INTERVAL_SECONDS:
            sample_run(context, "phase")
    except Exception:  # noqa: BLE001 - recording must never change a test's outcome
        context.counts["recording_errors"] += 1


def other_runs(run_id: str) -> tuple[list[dict[str, object]], int, bool]:
    """Other registered runs that are running now, how many more were not listed, and whether reading failed.

    On Windows each is checked through a process handle (PID, creation time and live state) and
    then against this run's own job: `own_job` or `outside`. Nothing is inferred from a registry
    entry alone, and no other run's job is opened. Elsewhere the relation is `unverified`.
    """
    try:
        entries = records.registry_entries(run_id)
    except OSError:
        return [], 0, True
    listed: list[dict[str, object]] = []
    extra = 0
    for entry in entries:
        root = entry.get("root")
        pid, created = (root.get("pid"), root.get("creation_time")) if isinstance(root, dict) else (None, None)
        if not _whole_number(pid):
            continue
        if native.supported():
            if not _whole_number(created):
                continue
            identity = native.process_identity(pid)
            if identity.creation_time != created or identity.live is not True:
                continue
            member = native.is_member(identity)
            relation = "own_job" if member is True else "outside" if member is False else "unverified"
        else:
            if not Path(f"/proc/{pid}").exists():
                continue
            relation = "unverified"
        if len(listed) >= records.MAX_OTHER_RUNS:
            extra += 1
            continue
        listed.append({
            "run_id": entry["run_id"], "relation": relation, "declared_agent": entry.get("declared_agent"),
            "worktree": entry.get("worktree"),
        })
    return listed, extra, False


def sample_run(context: RunContext, checkpoint: str) -> None:
    """One synchronous observation: this run's job totals and the other runs alive right now.

    Called at the start, at test-phase boundaries when the interval has passed, and at the end.
    There is no timer or thread, so a long phase has no sample inside it; `gap` shows that.
    """
    try:
        now = time.monotonic()
        others, extra, failed = other_runs(context.run_id)
        entry: dict[str, object] = {
            "at": round(now - context.started_monotonic, 3),
            "gap": round(now - (context.last_sample or context.started_monotonic), 3),
            "checkpoint": checkpoint, "others": others, "others_not_listed": extra, "registry_error": failed,
        }
        if context.native.get("enrolled"):
            entry["accounting"] = native.accounting()
        context.last_sample = now
        _append(context, "samples", [entry])
    except Exception:  # noqa: BLE001 - recording must never change a test's outcome
        context.counts["recording_errors"] += 1


def _payload(context: RunContext, *, checkpoint: str) -> dict[str, object]:
    """The record for one checkpoint. Checkout-derived text that is not fit to persist is withheld by name."""
    text = {
        "worktree": _bounded(context.worktree, records.WORKTREE), "branch": _bounded(context.branch, records.BRANCH),
        "head": _bounded(context.head, records.COMMIT), "declared_agent": _bounded(context.declared_agent, records.AGENT),
    }
    supplied = {"worktree": context.worktree, "branch": context.branch, "head": context.head,
                "declared_agent": context.declared_agent}
    payload: dict[str, object] = {
        "checkpoint": checkpoint, "run_id": context.run_id, "mode": context.mode, "reason": context.reason,
        "session_index": context.session_index, "started_utc": context.started_utc, **text,
        "withheld": sorted(name for name, value in text.items() if value is None and supplied[name] is not None),
        "platform": sys.platform, "root": context.root, "parent_run": context.parent_run, "native": context.native,
        "guard_mode": context.guard_mode, **context.facts,
    }
    if context.root_parent:
        payload["root_parent"] = context.root_parent
    return payload


def completeness(context: RunContext) -> str:
    """INVALID after any recording failure, TRUNCATED when a ceiling stopped a stream, else COMPLETE."""
    if context.counts["recording_errors"]:
        return "INVALID"
    return "TRUNCATED" if context.truncated else "COMPLETE"


def finish_run(context: RunContext, exit_status: int) -> dict[str, object]:
    """Write the terminal record. The job handle is deliberately kept until the interpreter exits.

    A recording failure never replaces pytest's own exit status: it makes the record INVALID,
    and the summary line says so.
    """
    global _current
    sample_run(context, "terminal")
    for stream in ("nodes", "phases", "samples"):
        if context.pending[stream]:
            _append(context, stream, [])
        if context.pending[stream]:
            # Still not written after the last attempt: the record is incomplete and says so.
            context.counts["recording_errors"] += 1
            context.pending[stream].clear()
    final: dict[str, object] = {"exit_status": int(exit_status), "finished_utc": datetime.now(timezone.utc).isoformat()}
    if context.native.get("enrolled"):
        final["accounting"] = native.accounting()
        identities, error = native.members()
        # `complete` is True only when every listed member's identity was actually read.
        final["members"] = (
            {"ok": True, "complete": all(identity.creation_time is not None for identity in identities),
             "identities": [_identity(identity) for identity in identities]}
            if identities is not None else {"ok": False, "complete": False, "error": error}
        )
    counts = context.counts
    final.update({
        "selected": counts["selected"], "deselected": counts["deselected"], "collection_errors": counts["collection_errors"],
        "selection_sha256": context.selection.hexdigest(),  # type: ignore[attr-defined]
        "streams": {"nodes": counts["nodes"], "phases": counts["phases"], "samples": counts["samples"],
                    "truncated": context.truncated},
        "recording_errors": counts["recording_errors"], "deferred_appends": counts["deferred_appends"],
        "last_sample_at": round(max(0.0, context.last_sample - context.started_monotonic), 3),
        "completeness": completeness(context),
    })
    payload = {**_payload(context, checkpoint="terminal"), **final}
    try:
        records.write_record(context.record_dir / "run.json", payload)
    except (OSError, ValueError):
        final["completeness"] = "INVALID"
    records.remove_own_registry_entry(context.run_id)
    _current = None
    return final


def summary_line(context: RunContext, final: dict[str, object] | None) -> str:
    """One compact line for pytest's terminal summary."""
    parts = [f"test-run-context: mode={context.mode}", f"reason={context.reason}", f"run={context.run_id}"]
    if context.native.get("enrolled"):
        accounting = (final or {}).get("accounting") or {}
        processes = accounting.get("total_processes") if isinstance(accounting, dict) and accounting.get("ok") else "QUERY_FAILED"
        parts += [f"native={'valid' if context.native.get('valid') else 'INVALID'}", f"job={context.native.get('job_name')}",
                  f"processes={processes}"]
    elif context.native.get("attempted"):
        # Enrolment was tried and did not hold: no job and no process count are claimed.
        parts.append("native=INVALID")
    else:
        parts.append(f"native={'not_enrolled' if context.native.get('supported') else 'unsupported'}")
    status = context.parent_run.get("status")
    parts.append(f"parent={context.parent_run.get('run_id') if status == 'parent' else status}")
    parts.append(f"guard={context.guard_mode}")
    if context.guard_mode == "pytest_process_guard":
        parts.append(f"protection={context.facts.get('protection')}")
    if final is not None:
        streams = final.get("streams") or {}
        parts += [f"records={final.get('completeness')}", f"phases={streams.get('phases') if isinstance(streams, dict) else 0}",
                  f"exit={final.get('exit_status')}"]
    return " ".join(str(part) for part in parts)
