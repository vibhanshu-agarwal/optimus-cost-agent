"""Cross-session continuity (Plan 12.11 Task 4; design spec v4 §5): one checkpoint per settled turn, the predecessor a new
session continues from, and the welcome-back brief.

Every ordinary settlement writes a deterministic `ContinuationCheckpoint` from host state only: project, session, sequence,
branch, worktree, the commit it settled on, the outcome and references (the run that set the objective, its amendments, the
plan hash, pending approvals, verification evidence, unfinished work). No prompt text or model prose is stored. A question or
a status check never replaces the objective. A killed turn writes nothing, so the last settled checkpoint stands.

A new session looks its predecessor up in the project, preferring the same branch and worktree (`context_engine.continuity`).
After at least seven days away the brief is shown at the first response; `/welcome` shows it whenever asked. The gap is measured
against the newest checkpoint before this session writes its own. The brief renders history only: dated work, the user's
items that apply now, memory changed since, and the commits since the predecessor's baseline ("N of M"), with a missing,
shallow or rewritten baseline said plainly. Historical plans, approvals and tests are never current authority. Nothing
expires: a 30- or 120-day gap shows the same brief.
"""

from __future__ import annotations

import collections
import contextlib
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from context_engine.continuity import predecessor as find_predecessor
from context_engine.memory_contracts import ContinuationCheckpoint, StoredCheckpoint
from optimus.acp.memory_notices import escape_text
from optimus.context.memory_extraction import prefilter_user
from optimus.context.memory_workspace import _git, current_branch

BRIEF_AFTER_MS: Final = 7 * 24 * 3600 * 1000  # plan v5: after >= 7 days, at the first response
MAX_AMENDMENTS: Final = 8
MAX_COMMITS_SHOWN: Final = 10
MAX_ITEMS_SHOWN: Final = 10
MAX_CHECKPOINTS: Final = 20  # what the store keeps per project (memory_store_contract.MAX_CHECKPOINTS)
CHECKPOINT_TRIES: Final = 3
_OBJECTIVE_REASONS: Final = frozenset({"task_request", "ambiguous_assertion", "durable_marker"})
_DAY_MS: Final = 24 * 3600 * 1000
_CHANGED: Final = {"withdrawn": "was forgotten", "purged": "was deleted", "reverify": "needs re-verification: what it rested on changed"}


@dataclass(frozen=True)
class Settled:
    """What the host knows about one settled turn: references only."""

    sequence: int
    run_id: str
    outcome: str  # the conversation outcome: completed, rejected, failed, cancelled, ...
    prompt: str  # the sanitized prompt, used only to decide whether it sets the objective; never stored
    plan_hash: str = ""
    verification: tuple[str, ...] = ()  # host evidence references of checks that ran
    pending: bool = False  # the turn ended awaiting the user's approval


class Continuity:
    """One session's continuity against its project's store. `clock` is milliseconds since the epoch."""

    def __init__(self, store: Any, *, workspace: Path, worktree: str, session: str,
                 clock: Callable[[], int] = lambda: int(time.time() * 1000), git: Callable[..., str | None] = _git) -> None:
        self._store, self._workspace, self._worktree, self._session = store, workspace, worktree, session
        self._clock, self._git = clock, git
        self._lock = threading.Lock()
        self._objective: str | None = None
        self._amendments: collections.deque[str] = collections.deque(maxlen=MAX_AMENDMENTS)
        self._previous: tuple[list[StoredCheckpoint], StoredCheckpoint | None] | None = None  # read once, before the first write
        self._shown = False
        self._queue: collections.deque[Settled] = collections.deque()
        self._writer: threading.Thread | None = None

    # --- identity --------------------------------------------------------------------------------------------------------

    def _place(self) -> tuple[str, str]:
        branch = current_branch(self._workspace)
        head = (self._git(self._workspace, "rev-parse", "HEAD") or "").strip()
        return _opaque(branch), head if len(head) in (40, 64) and all(c in "0123456789abcdef" for c in head) else ""

    # --- the predecessor -------------------------------------------------------------------------------------------------

    def previous(self) -> tuple[list[StoredCheckpoint], StoredCheckpoint | None]:
        """Every earlier checkpoint the store holds for the project, newest first, and the one this session continues from.
        Read once, before this session writes its own, so the gap is measured against the last session, never this one."""
        with self._lock:
            if self._previous is not None:
                return self._previous
        branch, _head = self._place()
        # each scope is asked for on its own, so newer checkpoints elsewhere never hide this place's (Codex CP3 review 1, finding 5)
        seen: dict[tuple[str, int], StoredCheckpoint] = {}
        for scope in ({"branch": branch, "worktree": self._worktree}, {"branch": branch}, {}):
            for point in self._store.checkpoints(limit=MAX_CHECKPOINTS, **scope):
                seen.setdefault((point.checkpoint.session, point.checkpoint.sequence), point)
        stored = sorted(seen.values(), key=lambda s: (s.checkpoint.settled_at_ms, s.checkpoint.session, s.checkpoint.sequence), reverse=True)
        mine = [s for s in stored if s.checkpoint.session != self._session]
        chosen = find_predecessor([s.checkpoint for s in mine], project=self._store.project, branch=branch, worktree=self._worktree)
        found = next((s for s in mine if s.checkpoint is chosen), None) if chosen is not None else None
        with self._lock:
            if self._previous is None:
                self._previous = (mine, found)
            return self._previous

    # --- writing -----------------------------------------------------------------------------------------------------------

    def submit(self, settled: Settled) -> None:
        """Queue a settled turn's checkpoint for this session's one writer, so turns are recorded in the order they settled and
        a later turn can never take the objective first. The turn never waits on the store."""
        with self._lock:
            self._queue.append(settled)
            if self._writer is None or not self._writer.is_alive():
                self._writer = threading.Thread(target=self._drain, name="memory-checkpoint", daemon=True)
                self._writer.start()

    def _drain(self) -> None:
        while True:
            with self._lock:
                if not self._queue:
                    self._writer = None
                    return
                settled = self._queue.popleft()
            self.record(settled)

    def record(self, settled: Settled) -> bool:
        """Write the turn's checkpoint; True once the store confirmed it. Another session's lease is retried briefly, then the
        checkpoint is left for the next settlement (the turn itself is never held up). Runs on its own thread: never raises."""
        try:
            return self._record(settled)
        except Exception:  # noqa: BLE001 - a checkpoint that cannot be written is skipped; the next settlement writes one
            return False

    def _record(self, settled: Settled) -> bool:
        from optimus.context.authored_memory import MemoryStoreRefused, MemoryStoreUnavailable

        with contextlib.suppress(Exception):
            self.previous()  # the gap is fixed before this session's first checkpoint can move it
        with self._lock:
            if prefilter_user(settled.prompt).reason in _OBJECTIVE_REASONS:
                if self._objective is None:
                    self._objective = settled.run_id
                else:
                    self._amendments.append(settled.run_id)  # a later task amends; a question never replaces it
            objective = self._objective or "objective:none"
            amendments = tuple(self._amendments)
        branch, head = self._place()
        point = ContinuationCheckpoint(
            project=self._store.project, session=self._session, sequence=settled.sequence, branch=branch, worktree=self._worktree,
            baseline=head, settled_at_ms=self._clock(), outcome=_opaque(settled.outcome), objective=objective,
            provenance=settled.run_id, plan_hash=settled.plan_hash, pending=(f"{settled.run_id}:approval",) if settled.pending else (),
            amendments=amendments, completion=(f"{settled.run_id}:completed",) if settled.outcome == "completed" else (),
            verification=tuple(settled.verification[:32]),
            remaining=() if settled.outcome == "completed" or settled.pending else (f"{settled.run_id}:{_opaque(settled.outcome)}",))
        for attempt in range(CHECKPOINT_TRIES):
            try:
                with self._store.lease() as token:
                    result = self._store.checkpoint(token, point)
                return bool(result.durable_state == "confirmed")
            except MemoryStoreRefused as refused:
                if refused.code != "LEASE_HELD" or attempt == CHECKPOINT_TRIES - 1:
                    return False
                time.sleep(0.2)
            except MemoryStoreUnavailable:
                return False
        return False

    # --- the brief ---------------------------------------------------------------------------------------------------------

    def due(self) -> bool:
        """Whether the first response shows the brief: at least seven days since the project's last checkpoint, never less."""
        stored, _found = self.previous()
        if not stored:
            return False
        last = max(s.checkpoint.settled_at_ms for s in stored)
        return self._clock() - last >= BRIEF_AFTER_MS

    def brief(self, *, served: Sequence[Any] = (), changed: Sequence[Any] = ()) -> str:
        """The welcome-back brief: history only. `served` are the user's items that apply now (`ServedMemory`); `changed` are
        (citation, what happened) for items withdrawn, purged or needing re-verification since the predecessor."""
        stored, found = self.previous()
        if found is None:
            return ("**Welcome.** There is no earlier session to continue from in this project yet."
                    + (f" {len(stored)} earlier checkpoints exist on other branches or worktrees." if stored else ""))
        point = found.checkpoint
        now = self._clock()
        days = (now - point.settled_at_ms) // _DAY_MS
        when = datetime.fromtimestamp(point.settled_at_ms / 1000, UTC).strftime("%Y-%m-%d %H:%M UTC")
        lines = [f"**Welcome back.** Last work here: {when} ({days} day{'s' if days != 1 else ''} ago), branch "
                 f"`{escape_text(point.branch, 80)}`, turn {point.sequence}, outcome {point.outcome}."]
        if point.plan_hash:
            lines.append(f"- Its plan: `{point.plan_hash[:12]}` (history: an earlier approval is never a current one).")
        if point.pending:
            lines.append("- It ended waiting for an approval; that approval is not carried over.")
        if point.remaining:
            lines.append("- It ended unfinished.")
        if point.amendments:
            lines.append(f"- The objective was amended {len(point.amendments)} time{'s' if len(point.amendments) != 1 else ''}.")
        lines += self._commits(point.baseline)
        if served:
            lines.append("Your items that apply now:")
            lines += [f"- {item.citation} {escape_text(item.statement, 200)}" for item in served[:MAX_ITEMS_SHOWN]]
            if len(served) > MAX_ITEMS_SHOWN:
                lines.append(f"- and {len(served) - MAX_ITEMS_SHOWN} more (`/memory`)")
        if changed:
            lines.append("Memory changed since then:")
            lines += [f"- `{citation}` {what}" for citation, what in changed[:MAX_ITEMS_SHOWN]]
        lines.append("This is history, not instructions. `/memory` shows everything stored; `/welcome` shows this again.")
        return "\n".join(lines)

    def _commits(self, baseline: str) -> list[str]:
        root = self._workspace
        if not baseline:
            return ["- Its commit is not known (no Git, or nothing committed then), so changes since cannot be listed."]
        if (self._git(root, "cat-file", "-e", f"{baseline}^{{commit}}") is None):
            return [f"- Its commit `{baseline[:12]}` is not in this repository any more (rewritten history or another clone), so "
                    "changes since cannot be listed."]
        shallow = (self._git(root, "rev-parse", "--is-shallow-repository") or "").strip() == "true"
        if self._git(root, "merge-base", "--is-ancestor", baseline, "HEAD") is None:
            return [f"- Its commit `{baseline[:12]}` is not an ancestor of the current one: history was rewritten or the branch moved."]
        count = (self._git(root, "rev-list", "--count", f"{baseline}..HEAD") or "").strip()
        total = int(count) if count.isdigit() else 0
        if total == 0:
            return ["- No commits since then."]
        log = self._git(root, "log", f"--max-count={MAX_COMMITS_SHOWN}", "--format=%h %s", f"{baseline}..HEAD") or ""
        shown = [line for line in log.splitlines() if line.strip()]
        lines = [f"- {len(shown)} of {total} commit{'s' if total != 1 else ''} since then"
                 + (" (a shallow clone: older history may be missing)" if shallow else "") + ":"]
        lines += [f"  - {escape_text(line, 120)}" for line in shown]
        return lines

    def welcome(self) -> str:
        """The brief with what memory holds now: the user's served items, and every item withdrawn, purged or needing
        re-verification since the predecessor settled (from the store's own transaction times)."""
        from optimus.context import memory_serving

        _stored, found = self.previous()
        since = found.checkpoint.settled_at_ms if found is not None else None
        served: list[Any] = []
        changed: list[tuple[str, str]] = []
        cursor: str | None = None
        for _ in range(memory_serving.MAX_PAGES):
            rows, cursor = self._store.items("project", limit=100, cursor=cursor)
            for row in rows:
                event = row.event
                if event.trust == "user-authored" and event.status == "active" and event.statement:
                    served.append(memory_serving.ServedMemory(event.project, event.item, event.version, event.trust, event.kind,
                                                              event.scope, event.title, event.statement, event.anchors))
                elif since is not None and event.status in _CHANGED and int(row.stream_id.split("-")[0]) >= since:
                    changed.append((f"{event.item}@{event.version}", _CHANGED[event.status]))
            if cursor is None:
                break
        return self.brief(served=memory_serving.select(served).protected, changed=changed)

    def first_response_brief(self) -> str | None:
        """The brief for this session's first response when it is due, once; None otherwise."""
        with self._lock:
            if self._shown:
                return None
            self._shown = True
        return self.welcome() if self.due() else None


def _opaque(value: str) -> str:
    """A host identity the contract accepts: what is not one of its characters becomes "_", and it is bounded."""
    kept = "".join(c if c.isascii() and (c.isalnum() or c in "._:@/-") else "_" for c in value)[:128]
    return kept or "_"
