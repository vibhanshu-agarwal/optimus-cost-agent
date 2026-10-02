"""Run context for pytest: which run this is, what it owns, and what else was running.

Test tooling only, loaded from `tests/conftest.py`. Importing it has no side effects. A session
that uses the unchanged default marker selection (including a focused subset of it) is ACTIVE: on
Windows it owns a new job object and the pytest process is guarded against the real application
folders. Every other session is PASSIVE: it is recorded, and nothing else about it changes.

The context creates no thread, timer or helper process. It never reads a command line and never
opens another run's job.
"""

from __future__ import annotations

import os
import secrets
import sys
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


_sessions_started = 0


def default_marker_expression(config: object) -> str | None:
    """The `-m` expression the project's own configuration supplies, or None when there is none."""
    try:
        addopts = list(config.getini("addopts"))  # type: ignore[attr-defined]
    except (ValueError, KeyError):
        return None
    for index, value in enumerate(addopts[:-1]):
        if value == "-m":
            return str(addopts[index + 1])
    return None


def classify(config: object) -> tuple[str, str]:
    """ACTIVE only for the unchanged default selection; everything unrecognised is PASSIVE."""
    option = config.option  # type: ignore[attr-defined]
    if getattr(option, OPTION_DEST, "auto") == "passive":
        return PASSIVE, "requested"
    if getattr(option, "collectonly", False):
        return PASSIVE, "collection_only"
    default = default_marker_expression(config)
    if default is None:
        return PASSIVE, "no_default_expression"
    if (getattr(option, "markexpr", "") or "") != default:
        return PASSIVE, "non_default_selection"
    return ACTIVE, "default_selection"


def _identity(identity: native.ProcessIdentity) -> dict[str, object]:
    return {"pid": identity.pid, "creation_time": identity.creation_time, "image": identity.image, "error": identity.error}


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


def _discover_parent_run(run_id: str) -> dict[str, object]:
    """Which registered active run, if any, this process descends from.

    A child cannot see its parent run's job: the Python venv launcher puts every interpreter it
    starts into a job of its own, so a process's immediate job holds only itself. The parent is
    therefore found by ancestry: the nearest live ancestor whose PID and creation time match a
    registered active root. Every hop is validated; a hop that cannot be opened makes the answer
    UNKNOWN, never a guess. No job is opened and no command line is read.
    """
    chain, stopped = native.ancestors()
    if stopped == "snapshot_failed":
        return {"status": UNKNOWN, "reason": stopped}
    roots: dict[tuple[int, int], str] = {}
    for entry in records.registry_entries(run_id):
        root = entry.get("root")
        if entry.get("mode") != ACTIVE or not isinstance(root, dict) or not isinstance(entry.get("run_id"), str):
            continue
        if isinstance(root.get("pid"), int) and isinstance(root.get("creation_time"), int):
            roots[(root["pid"], root["creation_time"])] = str(entry["run_id"])
    for ancestor in chain:
        found = roots.get((ancestor.pid, ancestor.creation_time or -1))
        if found is not None:
            return {"status": "parent", "run_id": found, "method": "validated_process_ancestry"}
    if stopped in {"access_denied", "hop_limit"}:
        return {"status": UNKNOWN, "reason": stopped}
    return {"status": "none"}


def start_run(config: object) -> RunContext:
    """Classify the session, enrol and guard an active one, and write its first record."""
    global _sessions_started
    mode, reason = classify(config)
    enrolled_before = native.supported() and native.owner() is not None
    if enrolled_before and mode == PASSIVE:
        import pytest

        raise pytest.UsageError(
            "test-run-context: this interpreter already owns a default-run job; "
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
            context.native = {"supported": True, "enrolled": True, "valid": owner.valid, "job_name": owner.name,
                              "reused_from_earlier_session": enrolled_before, **owner.facts}
        else:
            context.native = {"supported": True, "enrolled": False}
    else:
        context.root = {"pid": os.getpid(), "creation_time": None, "image": os.path.basename(sys.executable), "error": None}
        context.native = {"supported": False, "enrolled": False}
        context.parent_run = {"status": "unsupported"}
    if mode == ACTIVE:
        context.guard_mode = guard.install()
    payload = _payload(context, checkpoint="start")
    records.write_record(context.record_dir / "run.json", payload)
    records.write_record(records.registry_root() / f"{run_id}.json", payload)
    return context


def _payload(context: RunContext, *, checkpoint: str) -> dict[str, object]:
    return {
        "checkpoint": checkpoint, "run_id": context.run_id, "mode": context.mode, "reason": context.reason,
        "session_index": context.session_index, "started_utc": context.started_utc, "worktree": context.worktree,
        "branch": context.branch, "head": context.head, "declared_agent": context.declared_agent,
        "platform": sys.platform, "root": context.root, "root_parent": context.root_parent,
        "parent_run": context.parent_run, "native": context.native, "guard_mode": context.guard_mode,
    }


def finish_run(context: RunContext, exit_status: int) -> dict[str, object]:
    """Write the terminal record. The job handle is deliberately kept until the interpreter exits."""
    final: dict[str, object] = {"exit_status": int(exit_status), "finished_utc": datetime.now(timezone.utc).isoformat()}
    if context.native.get("enrolled"):
        final["accounting"] = native.accounting()
        identities, error = native.members()
        final["members"] = (
            {"ok": True, "identities": [_identity(identity) for identity in identities]}
            if identities is not None else {"ok": False, "error": error}
        )
    payload = {**_payload(context, checkpoint="terminal"), **final}
    records.write_record(context.record_dir / "run.json", payload)
    return final


def summary_line(context: RunContext, final: dict[str, object] | None) -> str:
    """One compact line for pytest's terminal summary."""
    parts = [f"test-run-context: mode={context.mode}", f"reason={context.reason}", f"run={context.run_id}"]
    if context.native.get("enrolled"):
        accounting = (final or {}).get("accounting") or {}
        processes = accounting.get("total_processes") if isinstance(accounting, dict) and accounting.get("ok") else "QUERY_FAILED"
        parts += [f"native={'valid' if context.native.get('valid') else 'INVALID'}", f"job={context.native.get('job_name')}",
                  f"processes={processes}"]
    else:
        parts.append(f"native={'not_enrolled' if context.native.get('supported') else 'unsupported'}")
    status = context.parent_run.get("status")
    parts.append(f"parent={context.parent_run.get('run_id') if status == 'parent' else status}")
    parts.append(f"guard={context.guard_mode}")
    return " ".join(str(part) for part in parts)
