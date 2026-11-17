"""Continuation lookup (Plan 12.11 Task 1; design spec v4 §5): which settled checkpoint a new session continues from.

Pure. A project-level lookup finds the latest eligible predecessor, preferring the same branch and worktree, then the same
branch, then any in the project. Another project's checkpoint is never eligible. Historical plans, approvals and tests in a
checkpoint never become current authority; the host renders them as history.
"""

from __future__ import annotations

from collections.abc import Iterable

from context_engine.memory_contracts import ContinuationCheckpoint


def predecessor(checkpoints: Iterable[ContinuationCheckpoint], *, project: str, branch: str, worktree: str) -> ContinuationCheckpoint | None:
    eligible = [checkpoint for checkpoint in checkpoints if checkpoint.project == project]

    def latest(candidates: list[ContinuationCheckpoint]) -> ContinuationCheckpoint | None:
        # settled time first; a tie between sessions breaks on session then sequence, so the answer never depends on input order
        return max(candidates, key=lambda c: (c.settled_at_ms, c.session, c.sequence), default=None)

    same_place = [c for c in eligible if c.branch == branch and c.worktree == worktree]
    same_branch = [c for c in eligible if c.branch == branch]
    return latest(same_place) or latest(same_branch) or latest(eligible)
