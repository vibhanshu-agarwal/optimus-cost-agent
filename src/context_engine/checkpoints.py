"""Checkpoint reuse and compare-and-publish (Plan 12.2 Task 6; design spec 5; Task 1 contracts 2).

A checkpoint is reused by append-only prefix validation: the same session, no future revision, the
same strategy, parameters and format, every covered turn still present with an unchanged source
digest, and a covered range that is the snapshot's summarizable prefix. That means a contiguous run
from the first turn, or from the second for hybrid, whose first turn may be pinned exactly. A valid
checkpoint is then re-keyed to the captured current revision. Session identity alone never makes a
checkpoint fresh.

Publication is a pure compare: the candidate's revision and parameter digest must equal the current
ones and the turn must not be cancelled. The host performs the store under its own lock; the engine
stores nothing.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from .contracts import HistoryRevision, HistorySnapshot, StrategyParameters, SummaryCheckpoint, turn_source_digest


@dataclass(frozen=True, slots=True)
class ReuseResult:
    """A re-keyed checkpoint, or `None` with the reason it cannot be reused."""

    checkpoint: SummaryCheckpoint | None
    reason: str | None


def _rejected(reason: str) -> ReuseResult:
    return ReuseResult(checkpoint=None, reason=reason)


def reuse_checkpoint(
    checkpoint: SummaryCheckpoint,
    snapshot: HistorySnapshot,
    *,
    strategy: str,
    parameters: StrategyParameters,
) -> ReuseResult:
    """Validate `checkpoint` against `snapshot` and re-key it to the snapshot's revision."""
    earlier, current = checkpoint.revision, snapshot.revision
    if earlier.session_key != current.session_key:
        return _rejected("other session")
    if earlier.generation > current.generation or earlier.last_committed_seq > current.last_committed_seq:
        return _rejected("future revision")
    if checkpoint.strategy != strategy:
        return _rejected("strategy mismatch")
    if checkpoint.parameters_digest != parameters.digest:
        return _rejected("parameters mismatch")
    if checkpoint.format_version != parameters.format_version:
        return _rejected("format mismatch")
    position = {seq: index for index, seq in enumerate(snapshot.ids)}
    if any(seq not in position for seq in checkpoint.covered_turn_ids):
        return _rejected("covered source missing")
    start = position[checkpoint.covered_turn_ids[0]]
    allowed_starts = (0, 1) if strategy == "hybrid" else (0,)
    expected = snapshot.ids[start : start + len(checkpoint.covered_turn_ids)]
    if start not in allowed_starts or expected != checkpoint.covered_turn_ids:
        return _rejected("coverage is not a prefix")
    for seq, digest in zip(checkpoint.covered_turn_ids, checkpoint.source_digests, strict=True):
        if turn_source_digest(snapshot.turns[position[seq]]) != digest:
            return _rejected("covered source changed")
    return ReuseResult(checkpoint=dataclasses.replace(checkpoint, revision=current), reason=None)


def publish_checkpoint(
    candidate: SummaryCheckpoint,
    *,
    current_revision: HistoryRevision,
    current_parameters_digest: str,
    cancelled: bool,
) -> bool:
    """Whether `candidate` may be published now. A cancelled or stale candidate is discarded by the
    caller; any calls it cost are still settled by the host."""
    if cancelled:
        return False
    return candidate.revision == current_revision and candidate.parameters_digest == current_parameters_digest
