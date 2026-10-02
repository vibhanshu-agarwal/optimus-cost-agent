"""Strategy orchestration: `ContextEngine.prepare_view` (Plan 12.2 Task 7; design spec 6; Task 1
contracts 2-3).

Allocation order: exact protected state for every committed turn comes first; if it cannot fit, the
view is unavailable and no maintenance runs. Then:

- compaction (default): the newest whole turns within its tail allocation stay exact, and every older
  turn is summarized;
- hybrid: the first turn is also pinned exactly when it fits the anchor allocation; the tail is larger;
  the middle is summarized; the head is never repeated in the tail;
- sliding window: the newest whole turns that fit stay exact and the rest are omitted from model
  context, never skipping an oversized newest turn, with zero maintenance calls.

Maintenance is planned in whole-turn chunks before any call. A later chunk's prior summary is
counted at its maximum length, so every planned input fits. A plan that needs more calls than allowed,
or a single turn larger than the maintenance input, is unavailable with zero calls. A valid checkpoint
is reused, or merged incrementally with only the turns it does not yet cover. The engine writes
nothing; it returns a candidate the host may publish.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from .checkpoints import reuse_checkpoint
from .contracts import (
    STRATEGIES,
    ContractError,
    HistorySnapshot,
    MaintenanceCallback,
    MaintenanceRequest,
    MaintenanceResult,
    OrdinaryTurn,
    PreparedView,
    StrategyParameters,
    SummaryCheckpoint,
    ViewLimits,
    turn_source_digest,
)
from .selection import newest_suffix_start, render_ordinary_turn, render_protected_state

PRIOR_SUMMARY_HEADER = "prior summary:\n"
_SEPARATOR = "\n"


class _Unavailable(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def maintenance_input(prior_summary: str | None, turns: Sequence[OrdinaryTurn]) -> str:
    """The source a maintenance call summarizes: an optional prior summary, then whole turns."""
    parts = [PRIOR_SUMMARY_HEADER + prior_summary] if prior_summary is not None else []
    parts.extend(render_ordinary_turn(turn) for turn in turns)
    return _SEPARATOR.join(parts)


class ContextEngine:
    """Pure strategy orchestration over an immutable snapshot."""

    def prepare_view(
        self,
        snapshot: HistorySnapshot,
        *,
        strategy: str,
        parameters: StrategyParameters,
        limits: ViewLimits,
        checkpoint: SummaryCheckpoint | None,
        maintenance: MaintenanceCallback,
        cancelled: Callable[[], bool],
    ) -> PreparedView:
        if not isinstance(snapshot, HistorySnapshot):
            raise ContractError("prepare_view needs a HistorySnapshot")
        if type(strategy) is not str or strategy not in STRATEGIES:
            raise ContractError(f"unknown strategy {strategy!r}")
        if not isinstance(parameters, StrategyParameters) or not isinstance(limits, ViewLimits):
            raise ContractError("prepare_view needs StrategyParameters and ViewLimits")
        if checkpoint is not None and not isinstance(checkpoint, SummaryCheckpoint):
            raise ContractError("checkpoint must be a SummaryCheckpoint or None")
        try:
            return self._prepare(snapshot, strategy, parameters, limits, checkpoint, maintenance, cancelled)
        except _Unavailable as unavailable:
            return PreparedView((), (), None, snapshot.protected, (), (), False, unavailable.reason)

    def _prepare(
        self,
        snapshot: HistorySnapshot,
        strategy: str,
        parameters: StrategyParameters,
        limits: ViewLimits,
        checkpoint: SummaryCheckpoint | None,
        maintenance: MaintenanceCallback,
        cancelled: Callable[[], bool],
    ) -> PreparedView:
        estimate = limits.estimate_history
        source_bytes = sum(len(render_ordinary_turn(turn).encode("utf-8")) for turn in snapshot.turns)
        if source_bytes > limits.source_max_bytes:
            raise _Unavailable("source exceeds limit")
        authority = sum(estimate(render_protected_state(state)) for state in snapshot.protected)
        if authority > limits.history_input_tokens:
            raise _Unavailable("exact authority exceeds history capacity")
        available = limits.history_input_tokens - authority
        ids = snapshot.ids
        costs = [estimate(render_ordinary_turn(turn)) for turn in snapshot.turns]

        if strategy == "sliding_window":
            start = newest_suffix_start(costs, available)
            return PreparedView((), ids[start:], None, snapshot.protected, (), ids[:start], True, None)

        tail_allocation = parameters.hybrid_tail_input_tokens if strategy == "hybrid" else parameters.compaction_tail_input_tokens
        if newest_suffix_start(costs, min(tail_allocation, available)) == 0:
            # Every turn fits the exact tail: nothing to summarize, and no head to repeat.
            return PreparedView((), ids, None, snapshot.protected, (), (), True, None)

        pinned = strategy == "hybrid" and bool(costs) and costs[0] <= parameters.anchor_input_tokens and costs[0] <= available
        head_end = 1 if pinned else 0
        room = available - (costs[0] if pinned else 0)
        start = max(newest_suffix_start(costs, min(tail_allocation, room)), head_end)
        reserve = min(parameters.summary_output_tokens, limits.maintenance_output_tokens)
        if start > head_end:
            tail_cost = sum(costs[start:])
            while room - tail_cost < reserve and start < len(ids):
                tail_cost -= costs[start]
                start += 1
            if room - tail_cost < reserve:
                raise _Unavailable("history capacity too small for a summary")

        covered = ids[head_end:start]
        summary = None
        if covered:
            summary = self._summarize(snapshot, covered, strategy, parameters, limits, checkpoint, maintenance, cancelled, reserve)
        return PreparedView(ids[:head_end], ids[start:], summary, snapshot.protected, covered, (), True, None)

    def _summarize(
        self,
        snapshot: HistorySnapshot,
        covered: tuple[int, ...],
        strategy: str,
        parameters: StrategyParameters,
        limits: ViewLimits,
        checkpoint: SummaryCheckpoint | None,
        maintenance: MaintenanceCallback,
        cancelled: Callable[[], bool],
        reserve: int,
    ) -> SummaryCheckpoint:
        estimate = limits.estimate_history
        prior: SummaryCheckpoint | None = None
        if checkpoint is not None:
            reused = reuse_checkpoint(checkpoint, snapshot, strategy=strategy, parameters=parameters).checkpoint
            # A checkpoint covering the whole range needs no call; one covering a prefix is merged
            # with only the turns it does not yet cover.
            if reused is not None and covered[: len(reused.covered_turn_ids)] == reused.covered_turn_ids:
                prior = reused

        by_seq = {turn.seq: turn for turn in snapshot.turns}
        remaining = [by_seq[seq] for seq in covered[len(prior.covered_turn_ids) if prior else 0 :]]
        chunks = self._plan(remaining, prior, limits, reserve)
        if len(chunks) > parameters.max_maintenance_calls:
            raise _Unavailable("maintenance allowance exceeded")

        summary_text = prior.summary_text if prior else None
        covered_so_far = prior.covered_turn_ids if prior else ()
        for chunk in chunks:
            if cancelled():
                raise _Unavailable("cancelled")
            text = maintenance_input(summary_text, chunk)
            if estimate(text) > limits.maintenance_input_tokens or len(text.encode("utf-8")) > limits.transient_max_bytes:
                raise _Unavailable("maintenance input exceeded")
            covered_so_far += tuple(turn.seq for turn in chunk)
            result = maintenance(
                MaintenanceRequest(
                    input_text=text,
                    covered_turn_ids=covered_so_far,
                    max_output_tokens=reserve,
                    prompt_version=parameters.prompt_version,
                    format_version=parameters.format_version,
                )
            )
            summary_text = self._accepted_summary(result, estimate, reserve)
        if cancelled():
            raise _Unavailable("cancelled")
        if summary_text is None or covered_so_far != covered:
            raise RuntimeError("maintenance plan did not cover the summarized range")
        return SummaryCheckpoint(
            revision=snapshot.revision,
            covered_turn_ids=covered,
            source_digests=tuple(turn_source_digest(by_seq[seq]) for seq in covered),
            strategy=strategy,
            parameters_digest=parameters.digest,
            format_version=parameters.format_version,
            summary_text=summary_text,
        )

    @staticmethod
    def _plan(remaining: list[OrdinaryTurn], prior: SummaryCheckpoint | None, limits: ViewLimits, reserve: int) -> list[list[OrdinaryTurn]]:
        """Whole-turn chunks, each fitting the maintenance input with its prior summary at its
        known length (a reused checkpoint) or its maximum length (an earlier chunk's output)."""
        estimate = limits.estimate_history
        header, separator = estimate(PRIOR_SUMMARY_HEADER), estimate(_SEPARATOR)
        prior_cost: int | None = estimate(PRIOR_SUMMARY_HEADER + prior.summary_text) if prior else None
        chunks: list[list[OrdinaryTurn]] = []
        index = 0
        while index < len(remaining):
            used = 0 if prior_cost is None else prior_cost + separator
            chunk: list[OrdinaryTurn] = []
            while index < len(remaining):
                turn_cost = estimate(render_ordinary_turn(remaining[index]))
                extra = turn_cost + (separator if chunk else 0)
                if used + extra > limits.maintenance_input_tokens:
                    break
                used += extra
                chunk.append(remaining[index])
                index += 1
            if not chunk:
                raise _Unavailable("turn exceeds maintenance input")
            chunks.append(chunk)
            prior_cost = header + reserve
        return chunks

    @staticmethod
    def _accepted_summary(result: object, estimate: Callable[[str], int], reserve: int) -> str:
        if (
            not isinstance(result, MaintenanceResult)
            or result.status != "completed"
            or result.finish_status != "stop"
            or not result.summary_text
        ):
            raise _Unavailable("maintenance failed")
        if estimate(result.summary_text) > reserve:
            raise _Unavailable("summary exceeds bound")
        return result.summary_text
