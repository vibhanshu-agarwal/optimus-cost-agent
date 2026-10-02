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
    payload = _payload(context, checkpoint="start")
    records.write_record(context.record_dir / "run.json", payload)
    records.write_record(records.registry_root() / f"{run_id}.json", payload)
    return context


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
        "guard_mode": context.guard_mode,
    }
    if context.root_parent:
        payload["root_parent"] = context.root_parent
    return payload


def finish_run(context: RunContext, exit_status: int) -> dict[str, object]:
    """Write the terminal record. The job handle is deliberately kept until the interpreter exits."""
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
    elif context.native.get("attempted"):
        # Enrolment was tried and did not hold: no job and no process count are claimed.
        parts.append("native=INVALID")
    else:
        parts.append(f"native={'not_enrolled' if context.native.get('supported') else 'unsupported'}")
    status = context.parent_run.get("status")
    parts.append(f"parent={context.parent_run.get('run_id') if status == 'parent' else status}")
    parts.append(f"guard={context.guard_mode}")
    return " ".join(str(part) for part in parts)
