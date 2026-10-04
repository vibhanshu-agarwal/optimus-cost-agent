"""Plan 12.2 Task 7: deterministic complete-turn strategies (design spec 6.1-6.4; Task 1 contracts 3).

Fixture allocations below are explicit test policy, never deployment defaults. The estimator counts
characters so allocations are exact. Every view keeps every turn whole and keeps exact protected state
for every committed turn. A view that cannot be built honestly is unavailable with a reason; it is
never approximated, truncated or summarized from authority.
"""

from __future__ import annotations

import dataclasses
import inspect
import math
import random
from fractions import Fraction

import pytest

from context_engine import (
    ContractError,
    HistoryRevision,
    HistorySnapshot,
    MaintenanceRequest,
    MaintenanceResult,
    OrdinaryTurn,
    ProtectedTurnState,
    StrategyParameters,
    SummaryCheckpoint,
    ViewLimits,
    history_digest,
    turn_source_digest,
)
from context_engine.engine import PRIOR_SUMMARY_HEADER, ContextEngine
from context_engine.selection import render_ordinary_turn, render_protected_state
from context_engine.summary import SECTIONS


def summary_text(label: str, *, length: int | None = None) -> str:
    """A valid `context-summary-v1` summary, optionally padded to exactly `length` characters."""
    bodies = [label, "-", "-", "-", "-", "-"]
    text = "\n".join(f"## {name}\n{body}" for name, body in zip(SECTIONS, bodies, strict=True))
    if length is not None:
        assert len(text) <= length
        text += "x" * (length - len(text))
    return text


def chars(text: str) -> int:
    return len(text)


def make_snapshot(sizes: list[int], *, facts: dict[int, tuple[str, ...]] | None = None, session: str = "s-1") -> HistorySnapshot:
    turns = tuple(OrdinaryTurn(seq=i, user_prompt="u" * size, plan_text="", completion_text=f"c{i}") for i, size in enumerate(sizes, start=1))
    protected = tuple(ProtectedTurnState(seq=t.seq, outcome="completed", effect_state="none", approval_facts=(facts or {}).get(t.seq, ())) for t in turns)
    revision = HistoryRevision(session_key=session, generation=len(turns), last_committed_seq=len(turns), digest=history_digest(turns, protected))
    return HistorySnapshot(revision=revision, turns=turns, protected=protected)


def cost(snapshot: HistorySnapshot, *seqs: int) -> int:
    by_seq = {turn.seq: turn for turn in snapshot.turns}
    return sum(len(render_ordinary_turn(by_seq[seq])) for seq in seqs)


def authority(snapshot: HistorySnapshot) -> int:
    return sum(len(render_protected_state(state)) for state in snapshot.protected)


def params(**changes: object) -> StrategyParameters:
    base = StrategyParameters(
        anchor_input_tokens=0,
        compaction_tail_input_tokens=0,
        hybrid_tail_input_tokens=0,
        summary_output_tokens=200,
        max_maintenance_calls=3,
        prompt_version="summary-prompt-v1",
        format_version="context-summary-v1",
    )
    return dataclasses.replace(base, **changes)  # type: ignore[arg-type]


def limits(history: int = 100_000, **changes: object) -> ViewLimits:
    base = ViewLimits(
        history_input_tokens=history,
        source_max_bytes=10_000_000,
        transient_max_bytes=10_000_000,
        maintenance_input_tokens=100_000,
        maintenance_output_tokens=200,
        summary_max_bytes=800,  # a character is at most 4 UTF-8 bytes
        estimate_history=chars,
        estimator_id="chars-v1",
    )
    return dataclasses.replace(base, **changes)  # type: ignore[arg-type]


class FakeMaintenance:
    """Returns a short summary naming its coverage; records every request."""

    def __init__(self, *, status: str = "completed", finish: str | None = "stop", text: str | None = "SUMMARY") -> None:
        self.requests: list[MaintenanceRequest] = []
        self._status, self._finish, self._text = status, finish, text

    def __call__(self, request: MaintenanceRequest) -> MaintenanceResult:
        self.requests.append(request)
        text = None if self._text is None else summary_text(f"{self._text} {request.covered_turn_ids}")
        return MaintenanceResult(summary_text=text, attempt_ids=(f"attempt-{len(self.requests)}",), status=self._status, finish_status=self._finish)


ENGINE = ContextEngine()


def view(snapshot, strategy, parameters, *, lim=None, checkpoint=None, maintenance=None, cancelled=lambda: False):
    return ENGINE.prepare_view(
        snapshot,
        strategy=strategy,
        parameters=parameters,
        limits=lim or limits(),
        checkpoint=checkpoint,
        maintenance=maintenance if maintenance is not None else FakeMaintenance(),
        cancelled=cancelled,
    )


def partitions(v) -> tuple[int, ...]:
    return tuple(sorted(v.head_turn_ids + v.tail_turn_ids + v.covered_turn_ids + v.omitted_turn_ids))


# --- Compaction and hybrid ----------------------------------------------------------------------------


def test_hybrid_keeps_a_fitting_first_turn_exact_and_compaction_does_not() -> None:
    """The required discriminator (spec 6.3): turn 1 fits the anchor and lies outside both tails."""
    snap = make_snapshot([20, 30, 30, 30, 30, 30])
    p = params(anchor_input_tokens=cost(snap, 1), compaction_tail_input_tokens=cost(snap, 6), hybrid_tail_input_tokens=cost(snap, 5, 6))
    compaction, hybrid = view(snap, "compaction", p), view(snap, "hybrid", p)
    assert hybrid.head_turn_ids == (1,) and compaction.head_turn_ids == ()
    assert 1 in compaction.covered_turn_ids and 1 not in hybrid.covered_turn_ids
    assert p.hybrid_tail_input_tokens > p.compaction_tail_input_tokens
    assert (compaction.tail_turn_ids, hybrid.tail_turn_ids) == ((6,), (5, 6))
    assert compaction.protected == hybrid.protected == snap.protected
    assert partitions(compaction) == partitions(hybrid) == snap.ids


def test_an_oversized_first_turn_enters_the_hybrid_summary_with_its_facts_exact() -> None:
    snap = make_snapshot([200, 30, 30, 30], facts={1: ('{"decision":"denied"}',)})
    p = params(anchor_input_tokens=cost(snap, 1) - 1, hybrid_tail_input_tokens=cost(snap, 4))
    v = view(snap, "hybrid", p)
    assert v.head_turn_ids == () and v.covered_turn_ids[0] == 1
    assert v.protected[0].approval_facts == ('{"decision":"denied"}',)


def test_the_head_is_not_repeated_when_the_first_turn_is_in_the_tail() -> None:
    snap = make_snapshot([20, 20])
    maintenance = FakeMaintenance()
    v = view(snap, "hybrid", params(anchor_input_tokens=1000, hybrid_tail_input_tokens=1000), maintenance=maintenance)
    assert (v.head_turn_ids, v.tail_turn_ids, v.covered_turn_ids) == ((), (1, 2), ())
    assert maintenance.requests == []


def test_compaction_summarizes_every_turn_older_than_its_tail() -> None:
    snap = make_snapshot([30, 30, 30, 30])
    maintenance = FakeMaintenance()
    v = view(snap, "compaction", params(compaction_tail_input_tokens=cost(snap, 3, 4)), maintenance=maintenance)
    assert (v.tail_turn_ids, v.covered_turn_ids, v.omitted_turn_ids) == ((3, 4), (1, 2), ())
    assert v.checkpoint is not None and v.checkpoint.covered_turn_ids == (1, 2)
    assert v.checkpoint.revision == snap.revision
    assert v.checkpoint.source_digests == tuple(turn_source_digest(t) for t in snap.turns[:2])
    assert [r.covered_turn_ids for r in maintenance.requests] == [(1, 2)]


def test_a_tail_that_fits_everything_needs_no_summary() -> None:
    snap = make_snapshot([10, 10, 10])
    maintenance = FakeMaintenance()
    v = view(snap, "compaction", params(compaction_tail_input_tokens=10_000), maintenance=maintenance)
    assert (v.tail_turn_ids, v.checkpoint, maintenance.requests) == ((1, 2, 3), None, [])


def test_the_tail_never_cuts_a_turn_and_stops_at_the_first_that_does_not_fit() -> None:
    snap = make_snapshot([10, 10, 200, 10])
    v = view(snap, "compaction", params(compaction_tail_input_tokens=cost(snap, 4) + 50))
    assert v.tail_turn_ids == (4,) and v.covered_turn_ids == (1, 2, 3)


def test_the_tail_shrinks_to_leave_room_for_the_summary() -> None:
    snap = make_snapshot([30, 30, 30])
    p = params(compaction_tail_input_tokens=cost(snap, 2, 3), summary_output_tokens=160)
    budget = authority(snap) + cost(snap, 2, 3) + 159  # one token short of tail + summary
    v = view(snap, "compaction", p, lim=limits(history=budget))
    assert v.available and v.tail_turn_ids == (3,) and v.covered_turn_ids == (1, 2)


# --- Sliding window -----------------------------------------------------------------------------------


def test_sliding_keeps_the_newest_complete_suffix_and_omits_the_rest() -> None:
    snap = make_snapshot([30, 30, 30, 30])
    budget = authority(snap) + cost(snap, 3, 4)
    v = view(snap, "sliding_window", params(), lim=limits(history=budget))
    assert (v.head_turn_ids, v.tail_turn_ids, v.covered_turn_ids, v.omitted_turn_ids) == ((), (3, 4), (), (1, 2))
    assert v.checkpoint is None and v.available


def test_sliding_never_skips_an_oversized_newest_turn_to_keep_older_ones() -> None:
    snap = make_snapshot([10, 10, 500])
    budget = authority(snap) + cost(snap, 1, 2)
    v = view(snap, "sliding_window", params(), lim=limits(history=budget))
    assert (v.tail_turn_ids, v.omitted_turn_ids) == ((), (1, 2, 3))
    assert v.protected == snap.protected


def test_sliding_makes_zero_maintenance_calls_even_with_a_checkpoint_after_a_switch() -> None:
    snap = make_snapshot([30, 30, 30, 30])
    compaction = view(snap, "compaction", params(compaction_tail_input_tokens=cost(snap, 4)))
    assert compaction.checkpoint is not None
    maintenance = FakeMaintenance()
    v = view(snap, "sliding_window", params(), lim=limits(history=authority(snap) + cost(snap, 4)), checkpoint=compaction.checkpoint, maintenance=maintenance)
    assert maintenance.requests == []
    assert v.checkpoint is None and v.omitted_turn_ids == (1, 2, 3)


def test_the_canonical_snapshot_is_never_changed() -> None:
    snap = make_snapshot([30, 30, 30])
    before = (snap.revision, snap.turns, snap.protected)
    for strategy in ("compaction", "hybrid", "sliding_window"):
        view(snap, strategy, params(compaction_tail_input_tokens=cost(snap, 3), hybrid_tail_input_tokens=cost(snap, 3)))
    assert (snap.revision, snap.turns, snap.protected) == before


# --- Exact authority and the empty history -------------------------------------------------------------


@pytest.mark.parametrize("strategy", ["compaction", "hybrid", "sliding_window"])
def test_authority_that_cannot_fit_makes_the_view_unavailable_without_any_call(strategy) -> None:
    snap = make_snapshot([10, 10], facts={1: ("x" * 300,)})
    maintenance = FakeMaintenance()
    v = view(snap, strategy, params(), lim=limits(history=authority(snap) - 1), maintenance=maintenance)
    assert (v.available, v.reason) == (False, "exact authority exceeds history capacity")
    assert v.protected == snap.protected and maintenance.requests == []


def test_authority_is_never_sent_to_maintenance() -> None:
    fact = '{"artifact_hash":"plan-7","decision":"granted"}'
    snap = make_snapshot([30, 30, 30, 30], facts={1: (fact,), 2: (fact,)})
    maintenance = FakeMaintenance()
    view(snap, "compaction", params(compaction_tail_input_tokens=cost(snap, 4)), maintenance=maintenance)
    assert maintenance.requests and all(fact not in r.input_text and "plan-7" not in r.input_text for r in maintenance.requests)


@pytest.mark.parametrize("strategy", ["compaction", "hybrid", "sliding_window"])
def test_an_empty_history_needs_no_maintenance(strategy) -> None:
    maintenance = FakeMaintenance()
    v = view(make_snapshot([]), strategy, params(), maintenance=maintenance)
    assert v.available and partitions(v) == () and maintenance.requests == []


@pytest.mark.parametrize("strategy", ["compaction", "hybrid", "sliding_window"])
def test_every_turn_lands_in_exactly_one_partition(strategy) -> None:
    snap = make_snapshot([25, 70, 15, 40, 90, 5, 33])
    v = view(snap, strategy, params(anchor_input_tokens=200, compaction_tail_input_tokens=150, hybrid_tail_input_tokens=300), lim=limits(history=authority(snap) + 600))
    assert v.available and partitions(v) == snap.ids


# --- Maintenance planning: whole turns, finite calls ---------------------------------------------------


def test_maintenance_input_holds_whole_turns() -> None:
    snap = make_snapshot([30, 30, 30, 30])
    maintenance = FakeMaintenance()
    view(snap, "compaction", params(compaction_tail_input_tokens=cost(snap, 4)), maintenance=maintenance)
    text = "".join(r.input_text for r in maintenance.requests)
    for turn in snap.turns[:3]:
        assert render_ordinary_turn(turn) in text


RESERVE = 160  # room for a short valid six-section summary


def two_turn_chunks(snap: HistorySnapshot) -> int:
    """A maintenance input that holds two whole turns, or one with a prior summary at full length."""
    assert cost(snap, 1) > len(PRIOR_SUMMARY_HEADER) + RESERVE + 2, "a third turn must not fit"
    return cost(snap, 1, 2) + len(PRIOR_SUMMARY_HEADER) + RESERVE + 2


def test_older_history_is_chunked_within_maintenance_input() -> None:
    snap = make_snapshot([200, 200, 200, 200, 200])
    maintenance = FakeMaintenance()
    lim = limits(maintenance_input_tokens=two_turn_chunks(snap))
    v = view(snap, "compaction", params(compaction_tail_input_tokens=cost(snap, 5), summary_output_tokens=RESERVE), lim=lim, maintenance=maintenance)
    assert v.available and v.covered_turn_ids == (1, 2, 3, 4)
    assert [r.covered_turn_ids for r in maintenance.requests] == [(1, 2), (1, 2, 3, 4)]
    assert all(chars(r.input_text) <= lim.maintenance_input_tokens for r in maintenance.requests)


def test_chunks_are_planned_for_the_longest_allowed_prior_summary() -> None:
    """A later chunk carries the previous summary. Planning counts it at its maximum length, so a
    summary that uses its whole allowance still leaves every input within bounds. Planning by a
    shorter guess would overfill a chunk, and the call-time check would refuse it."""
    snap = make_snapshot([37] * 19)

    class LongSummary(FakeMaintenance):
        def __call__(self, request: MaintenanceRequest) -> MaintenanceResult:
            self.requests.append(request)
            return MaintenanceResult(summary_text=summary_text("L", length=request.max_output_tokens), attempt_ids=("a",), status="completed", finish_status="stop")

    maintenance = LongSummary()
    lim = limits(maintenance_input_tokens=9 * cost(snap, 1) + 8, maintenance_output_tokens=300)
    p = params(compaction_tail_input_tokens=cost(snap, 19), summary_output_tokens=400, max_maintenance_calls=3)
    v = view(snap, "compaction", p, lim=lim, maintenance=maintenance)
    assert v.available, v.reason
    assert len(maintenance.requests) == 3
    assert all(chars(r.input_text) <= lim.maintenance_input_tokens for r in maintenance.requests)
    assert {r.max_output_tokens for r in maintenance.requests} == {300}, "the smaller of the summary and route output bounds"


def test_an_input_the_estimator_prices_above_its_plan_is_refused_before_the_call() -> None:
    """Planning adds per-turn estimates; the actual input is estimated again before the call. An
    estimator that charges more for combined text cannot push an oversized request out."""
    snap = make_snapshot([40, 40, 40, 40])

    def superadditive(text: str) -> int:
        return len(text) + (500 if text.count('"seq"') > 1 else 0)

    maintenance = FakeMaintenance()
    planned = cost(snap, 1, 2, 3) + 2  # three whole turns and two separators, as planning adds them
    lim = limits(maintenance_input_tokens=planned + 100, estimate_history=superadditive)
    v = view(snap, "compaction", params(compaction_tail_input_tokens=superadditive(render_ordinary_turn(snap.turns[3]))), lim=lim, maintenance=maintenance)
    assert (v.available, v.reason, maintenance.requests) == (False, "maintenance input exceeded", [])


def test_source_beyond_its_limit_is_unavailable() -> None:
    snap = make_snapshot([30, 30])
    source = sum(len(render_ordinary_turn(t).encode("utf-8")) for t in snap.turns)
    assert view(snap, "sliding_window", params(), lim=limits(source_max_bytes=source)).available
    v = view(snap, "sliding_window", params(), lim=limits(source_max_bytes=source - 1))
    assert (v.available, v.reason) == (False, "source exceeds limit")


def test_maintenance_input_beyond_the_transient_bound_is_refused_before_the_call() -> None:
    # The planner counts bytes as well as tokens (Codex's final corrections C2), so a turn that cannot
    # fit the transient bound is refused at planning, before any call; the check of each assembled
    # input stays as the backstop (see the non-subadditive estimator test).
    snap = make_snapshot([30, 30, 30])
    maintenance = FakeMaintenance()
    lim = limits(transient_max_bytes=50, summary_max_bytes=40)
    v = view(snap, "compaction", params(compaction_tail_input_tokens=cost(snap, 3)), lim=lim, maintenance=maintenance)
    assert (v.available, v.reason, maintenance.requests) == (False, "turn exceeds maintenance input", [])


def test_a_summary_over_its_bound_makes_the_view_unavailable() -> None:
    snap = make_snapshot([30, 30, 30])
    v = view(snap, "compaction", params(compaction_tail_input_tokens=cost(snap, 3), summary_output_tokens=5), maintenance=FakeMaintenance())
    assert (v.available, v.reason) == (False, "summary exceeds bound")


def test_needing_more_calls_than_allowed_is_unavailable_before_any_call() -> None:
    snap = make_snapshot([200, 200, 200, 200, 200])
    maintenance = FakeMaintenance()
    lim = limits(maintenance_input_tokens=cost(snap, 1) + len(PRIOR_SUMMARY_HEADER) + RESERVE + 6)
    p = params(compaction_tail_input_tokens=cost(snap, 5), max_maintenance_calls=2, summary_output_tokens=RESERVE)
    v = view(snap, "compaction", p, lim=lim, maintenance=maintenance)
    assert (v.available, v.reason, maintenance.requests) == (False, "maintenance allowance exceeded", [])


# --- Remaining turn-wide allowance (release supplement V3) --------------------------------------------


def _four_chunk_case() -> tuple[HistorySnapshot, StrategyParameters, ViewLimits]:
    """Turns 1-4 are summarized one per call; turn 5 is the exact tail."""
    snap = make_snapshot([200, 200, 200, 200, 200])
    lim = limits(maintenance_input_tokens=cost(snap, 1) + len(PRIOR_SUMMARY_HEADER) + RESERVE + 6)
    return snap, params(compaction_tail_input_tokens=cost(snap, 5), max_maintenance_calls=18, summary_output_tokens=RESERVE), lim


@pytest.mark.parametrize("bad", [-1, True, 1.0, "2"])
def test_the_remaining_allowance_must_be_a_non_negative_int_or_none(bad: object) -> None:
    assert limits().maintenance_calls_remaining is None
    assert limits(maintenance_calls_remaining=0).maintenance_calls_remaining == 0
    with pytest.raises(ContractError, match="maintenance_calls_remaining"):
        limits(maintenance_calls_remaining=bad)


def test_the_remaining_allowance_bounds_the_whole_plan_before_any_call() -> None:
    snap, p, lim = _four_chunk_case()
    refused = FakeMaintenance()
    v = view(snap, "compaction", p, lim=dataclasses.replace(lim, maintenance_calls_remaining=3), maintenance=refused)
    assert (v.available, v.reason, refused.requests) == (False, "maintenance allowance exceeded", [])

    fitting = FakeMaintenance()
    v = view(snap, "compaction", p, lim=dataclasses.replace(lim, maintenance_calls_remaining=4), maintenance=fitting)
    assert v.available and len(fitting.requests) == 4


def test_a_larger_remaining_allowance_never_lifts_the_parameters_bound() -> None:
    snap, p, lim = _four_chunk_case()
    maintenance = FakeMaintenance()
    v = view(snap, "compaction", dataclasses.replace(p, max_maintenance_calls=3), lim=dataclasses.replace(lim, maintenance_calls_remaining=18), maintenance=maintenance)
    assert (v.available, v.reason, maintenance.requests) == (False, "maintenance allowance exceeded", [])


def test_zero_remaining_allows_only_a_view_that_needs_no_call() -> None:
    snap, p, lim = _four_chunk_case()
    exhausted = dataclasses.replace(lim, maintenance_calls_remaining=0)
    first = FakeMaintenance()
    full = view(snap, "compaction", p, lim=lim, maintenance=first)
    assert full.available and full.checkpoint is not None

    # A checkpoint that already covers the range is reused with no call.
    again = FakeMaintenance()
    reused = view(snap, "compaction", p, lim=exhausted, checkpoint=full.checkpoint, maintenance=again)
    assert reused.available and again.requests == [] and reused.checkpoint == full.checkpoint
    # Sliding and an all-tail view need no call either.
    assert view(snap, "sliding_window", p, lim=exhausted, maintenance=again).available
    assert view(snap, "compaction", dataclasses.replace(p, compaction_tail_input_tokens=100_000), lim=exhausted, maintenance=again).available
    assert again.requests == []
    # A cold plan needing calls refuses before its first callback.
    cold = view(snap, "compaction", p, lim=exhausted, maintenance=again)
    assert (cold.available, cold.reason, again.requests) == (False, "maintenance allowance exceeded", [])


def test_the_remaining_allowance_is_outside_checkpoint_identity() -> None:
    """A smaller allowance leaves the parameters digest alone, so a prefix checkpoint is still reused
    and only the uncovered turns are summarized."""
    snap, p, lim = _four_chunk_case()
    prefix_snap = make_snapshot([200, 200, 200])  # turns 1-2 summarized, turn 3 the tail
    prefix = view(prefix_snap, "compaction", dataclasses.replace(p, compaction_tail_input_tokens=cost(prefix_snap, 3)), lim=lim)
    assert prefix.available and prefix.checkpoint is not None and prefix.checkpoint.covered_turn_ids == (1, 2)

    maintenance = FakeMaintenance()
    v = view(snap, "compaction", p, lim=dataclasses.replace(lim, maintenance_calls_remaining=2), checkpoint=prefix.checkpoint, maintenance=maintenance)
    assert v.available and v.checkpoint is not None
    assert v.checkpoint.parameters_digest == p.digest == prefix.checkpoint.parameters_digest
    assert [request.covered_turn_ids for request in maintenance.requests] == [(1, 2, 3), (1, 2, 3, 4)]
    assert all(PRIOR_SUMMARY_HEADER in request.input_text for request in maintenance.requests)


def test_a_turn_larger_than_the_maintenance_input_is_unavailable_and_never_cut() -> None:
    snap = make_snapshot([500, 10, 10])
    maintenance = FakeMaintenance()
    v = view(snap, "compaction", params(compaction_tail_input_tokens=cost(snap, 3)), lim=limits(maintenance_input_tokens=100), maintenance=maintenance)
    assert (v.available, v.reason, maintenance.requests) == (False, "turn exceeds maintenance input", [])


class ExactText(FakeMaintenance):
    """Returns exactly the given text, whatever the coverage."""

    def __init__(self, text: str, *, status: str = "completed") -> None:
        super().__init__(status=status)
        self._exact = text

    def __call__(self, request: MaintenanceRequest) -> MaintenanceResult:
        self.requests.append(request)
        return MaintenanceResult(summary_text=self._exact, attempt_ids=("a",), status=self._status, finish_status="stop")


@pytest.mark.parametrize(
    "fake, reason",
    [
        (FakeMaintenance(status="failed", text=None), "maintenance failed"),
        (ExactText("a usable-looking summary", status="failed"), "maintenance failed"),
        (FakeMaintenance(finish="length"), "maintenance failed"),
        (FakeMaintenance(text=None), "maintenance failed"),
        (ExactText(""), "maintenance failed"),
        # No summarizer configured, or one that does not support this prompt/format version: not a
        # provider failure, so retrying cannot help (Codex's final corrections C1).
        (FakeMaintenance(status="unavailable", text=None, finish=None), "maintenance unavailable"),
        (FakeMaintenance(status="unsupported", text=None, finish=None), "maintenance unavailable"),
        (ExactText("a usable-looking summary", status="unsupported"), "maintenance unavailable"),
        # A host's defensive refusal past its turn-wide allowance is the allowance reason, never a paid
        # failure that "retrying may help" (closure V2 section 2.2).
        (FakeMaintenance(status="allowance_exhausted", text=None, finish=None), "maintenance allowance exceeded"),
    ],
    ids=[
        "failed",
        "failed-with-text",
        "length-limited",
        "none",
        "empty-string",
        "no-summarizer",
        "unsupported",
        "unsupported-with-text",
        "allowance-exhausted",
    ],
)
def test_an_unusable_maintenance_result_makes_the_view_unavailable(fake, reason) -> None:
    snap = make_snapshot([30, 30, 30])
    v = view(snap, "compaction", params(compaction_tail_input_tokens=cost(snap, 3)), maintenance=fake)
    assert (v.available, v.reason, v.checkpoint) == (False, reason, None)
    assert v.protected == snap.protected


def test_history_too_small_for_any_summary_is_unavailable() -> None:
    snap = make_snapshot([30, 30, 30])
    p = params(compaction_tail_input_tokens=cost(snap, 3), summary_output_tokens=100)
    maintenance = FakeMaintenance()
    v = view(snap, "compaction", p, lim=limits(history=authority(snap) + 99), maintenance=maintenance)
    assert (v.available, v.reason, maintenance.requests) == (False, "history capacity too small for a summary", [])


def test_a_result_that_arrives_after_cancellation_is_discarded() -> None:
    """The call ran and is settled by the host, but a cancelled turn's summary is never offered."""
    snap = make_snapshot([30, 30, 30])
    maintenance = FakeMaintenance()
    v = view(snap, "compaction", params(compaction_tail_input_tokens=cost(snap, 3)), maintenance=maintenance, cancelled=lambda: bool(maintenance.requests))
    assert (v.available, v.reason, v.checkpoint, len(maintenance.requests)) == (False, "cancelled", None, 1)


def test_cancellation_before_maintenance_makes_no_call() -> None:
    snap = make_snapshot([30, 30, 30])
    maintenance = FakeMaintenance()
    v = view(snap, "compaction", params(compaction_tail_input_tokens=cost(snap, 3)), maintenance=maintenance, cancelled=lambda: True)
    assert (v.available, v.reason, maintenance.requests) == (False, "cancelled", [])


def test_cancellation_between_chunks_stops_further_calls() -> None:
    snap = make_snapshot([200, 200, 200, 200, 200])
    maintenance = FakeMaintenance()
    v = view(
        snap,
        "compaction",
        params(compaction_tail_input_tokens=cost(snap, 5), summary_output_tokens=RESERVE),
        lim=limits(maintenance_input_tokens=two_turn_chunks(snap)),
        maintenance=maintenance,
        cancelled=lambda: len(maintenance.requests) >= 1,
    )
    assert (v.available, v.reason, len(maintenance.requests)) == (False, "cancelled", 1)


# --- Checkpoint reuse ---------------------------------------------------------------------------------


class FixedSummary(FakeMaintenance):
    """Returns the same valid summary text for every request."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self._fixed = text

    def __call__(self, request: MaintenanceRequest) -> MaintenanceResult:
        self.requests.append(request)
        return MaintenanceResult(summary_text=self._fixed, attempt_ids=(f"attempt-{len(self.requests)}",), status="completed", finish_status="stop")


def history_used(v, snapshot: HistorySnapshot, estimate=chars) -> int:
    """What the view puts in the history budget: exact authority, exact turns and the summary."""
    exact = v.head_turn_ids + v.tail_turn_ids
    summary = estimate(v.checkpoint.summary_text) if v.checkpoint is not None else 0
    return sum(estimate(render_protected_state(s)) for s in snapshot.protected) + sum(estimate(render_ordinary_turn(t)) for t in snapshot.turns if t.seq in exact) + summary


def test_a_valid_checkpoint_covering_the_whole_range_is_reused_without_a_call() -> None:
    snap = make_snapshot([30, 30, 30, 30])
    p = params(compaction_tail_input_tokens=cost(snap, 4))
    first = view(snap, "compaction", p)
    maintenance = FakeMaintenance()
    again = view(snap, "compaction", p, checkpoint=first.checkpoint, maintenance=maintenance)
    assert again.checkpoint == first.checkpoint and maintenance.requests == []
    assert history_used(again, snap) <= limits().history_input_tokens


def test_a_reused_summary_over_the_current_output_bound_is_rebuilt_from_source() -> None:
    """Codex CP2 R1: a 400-token checkpoint reused under a 200-token cap overfilled history."""
    snap = make_snapshot([30, 30, 30, 30])
    p = params(compaction_tail_input_tokens=cost(snap, 4), summary_output_tokens=400)
    first = view(snap, "compaction", p, lim=limits(maintenance_output_tokens=400), maintenance=FixedSummary(summary_text("L", length=400)))
    assert first.checkpoint is not None and len(first.checkpoint.summary_text) == 400
    reduced = limits(history=authority(snap) + cost(snap, 4) + 200, maintenance_output_tokens=200)
    maintenance = FakeMaintenance()
    v = view(snap, "compaction", p, lim=reduced, checkpoint=first.checkpoint, maintenance=maintenance)
    assert v.available, v.reason
    assert [r.covered_turn_ids for r in maintenance.requests] == [(1, 2, 3)]
    assert first.checkpoint.summary_text not in maintenance.requests[0].input_text
    assert history_used(v, snap) <= reduced.history_input_tokens


def test_a_hybrid_reused_summary_over_the_current_output_bound_is_rebuilt_from_source() -> None:
    snap = make_snapshot([30, 30, 30, 30, 30])
    p = params(anchor_input_tokens=cost(snap, 1), hybrid_tail_input_tokens=cost(snap, 5), summary_output_tokens=400)
    first = view(snap, "hybrid", p, lim=limits(maintenance_output_tokens=400), maintenance=FixedSummary(summary_text("L", length=400)))
    assert first.head_turn_ids == (1,) and first.checkpoint is not None and first.checkpoint.covered_turn_ids == (2, 3, 4)
    reduced = limits(history=authority(snap) + cost(snap, 1, 5) + 200, maintenance_output_tokens=200)
    maintenance = FakeMaintenance()
    v = view(snap, "hybrid", p, lim=reduced, checkpoint=first.checkpoint, maintenance=maintenance)
    assert v.available and v.head_turn_ids == (1,) and v.tail_turn_ids == (5,)
    assert [r.covered_turn_ids for r in maintenance.requests] == [(2, 3, 4)]
    assert first.checkpoint.summary_text not in maintenance.requests[0].input_text
    assert history_used(v, snap) <= reduced.history_input_tokens


def test_a_reused_summary_is_measured_with_the_current_estimator() -> None:
    """The checkpoint's parameter digest does not cover the estimator: the same partitions under a
    heavier estimator must re-measure the cached text, not trust it."""
    snap = make_snapshot([30, 30, 30, 30])
    p = params(compaction_tail_input_tokens=cost(snap, 4), summary_output_tokens=400)
    cached = summary_text("Z")
    cached += "z" * (300 - len(cached))
    first = view(snap, "compaction", p, lim=limits(maintenance_output_tokens=400), maintenance=FixedSummary(cached))
    assert first.checkpoint is not None and first.checkpoint.summary_text == cached

    def heavier(text: str) -> int:
        return len(text) + 3 * text.count("z")

    assert all(heavier(render_ordinary_turn(t)) == len(render_ordinary_turn(t)) for t in snap.turns), "turn costs unchanged"
    lim = limits(maintenance_output_tokens=400, estimate_history=heavier, estimator_id="chars-plus-z")
    maintenance = FakeMaintenance()
    v = view(snap, "compaction", p, lim=lim, checkpoint=first.checkpoint, maintenance=maintenance)
    assert v.available and v.covered_turn_ids == first.covered_turn_ids
    assert [r.covered_turn_ids for r in maintenance.requests] == [(1, 2, 3)] and cached not in maintenance.requests[0].input_text
    assert heavier(v.checkpoint.summary_text) <= 400


def test_a_cached_summary_that_no_longer_parses_is_rebuilt_from_source() -> None:
    snap = make_snapshot([30, 30, 30, 30])
    p = params(compaction_tail_input_tokens=cost(snap, 4))
    first = view(snap, "compaction", p)
    corrupt = dataclasses.replace(first.checkpoint, summary_text="## Task context\nonly one section")
    maintenance = FakeMaintenance()
    v = view(snap, "compaction", p, checkpoint=corrupt, maintenance=maintenance)
    assert v.available and [r.covered_turn_ids for r in maintenance.requests] == [(1, 2, 3)]
    assert v.checkpoint is not None and v.checkpoint.summary_text != corrupt.summary_text


def test_a_rebuild_that_needs_more_calls_than_allowed_is_unavailable_with_zero_calls() -> None:
    snap = make_snapshot([300, 300, 300, 300])
    p = params(compaction_tail_input_tokens=cost(snap, 4), summary_output_tokens=400, max_maintenance_calls=1)
    first = view(snap, "compaction", p, lim=limits(maintenance_output_tokens=400), maintenance=FixedSummary(summary_text("L", length=400)))
    assert first.checkpoint is not None
    # The input holds one turn beside a maximal prior summary, never two turns: rebuilding turns 1-3
    # from source needs three calls, and one is allowed.
    reduced = limits(maintenance_output_tokens=200, maintenance_input_tokens=len(PRIOR_SUMMARY_HEADER) + 200 + 1 + cost(snap, 1))
    assert cost(snap, 1, 2) + 1 > reduced.maintenance_input_tokens
    maintenance = FakeMaintenance()
    v = view(snap, "compaction", p, lim=reduced, checkpoint=first.checkpoint, maintenance=maintenance)
    assert (v.available, v.reason, maintenance.requests) == (False, "maintenance allowance exceeded", [])


def test_a_prefix_checkpoint_over_the_current_bound_is_not_merged() -> None:
    small, grown = make_snapshot([30, 30, 30, 30]), make_snapshot([30, 30, 30, 30, 30])
    p = params(compaction_tail_input_tokens=cost(small, 4), summary_output_tokens=400)
    prior = view(small, "compaction", p, lim=limits(maintenance_output_tokens=400), maintenance=FixedSummary(summary_text("L", length=400))).checkpoint
    assert prior is not None and prior.covered_turn_ids == (1, 2, 3)
    maintenance = FakeMaintenance()
    v = view(grown, "compaction", p, lim=limits(maintenance_output_tokens=200), checkpoint=prior, maintenance=maintenance)
    assert v.available and [r.covered_turn_ids for r in maintenance.requests] == [(1, 2, 3, 4)]
    assert prior.summary_text not in maintenance.requests[0].input_text


def test_an_appended_turn_merges_only_the_new_range_into_the_prior_summary() -> None:
    small = make_snapshot([30, 30, 30, 30])
    grown = make_snapshot([30, 30, 30, 30, 30])
    p = params(compaction_tail_input_tokens=cost(small, 4))
    prior = view(small, "compaction", p).checkpoint
    assert prior is not None and prior.covered_turn_ids == (1, 2, 3)
    maintenance = FakeMaintenance()
    v = view(grown, "compaction", p, checkpoint=prior, maintenance=maintenance)
    assert v.covered_turn_ids == (1, 2, 3, 4)
    [request] = maintenance.requests
    assert request.covered_turn_ids == (1, 2, 3, 4)
    assert prior.summary_text in request.input_text
    assert render_ordinary_turn(grown.turns[3]) in request.input_text
    assert render_ordinary_turn(grown.turns[0]) not in request.input_text, "already summarized source is not re-sent"
    assert v.checkpoint is not None and v.checkpoint.revision == grown.revision


def test_no_summarizer_output_capacity_is_unavailable_not_an_error() -> None:
    v = view(make_snapshot([30, 30, 30]), "compaction", params(compaction_tail_input_tokens=cost(make_snapshot([30, 30, 30]), 3)), lim=limits(maintenance_output_tokens=0))
    assert (v.available, v.reason) == (False, "maintenance unavailable")


def test_a_reused_summary_too_long_to_sit_beside_the_next_turn_falls_back_to_source() -> None:
    small, grown = make_snapshot([30, 30, 30, 30]), make_snapshot([30, 30, 30, 30, 30])
    p = params(compaction_tail_input_tokens=cost(small, 4), summary_output_tokens=400)
    prior = view(small, "compaction", p, lim=limits(maintenance_output_tokens=400), maintenance=FixedSummary(summary_text("L", length=400))).checkpoint
    assert prior is not None and prior.covered_turn_ids == (1, 2, 3)
    # Four whole turns fit the input; the long prior summary plus turn 4 does not.
    lim = limits(maintenance_input_tokens=cost(grown, 1, 2, 3, 4) + 3, maintenance_output_tokens=400)
    assert len(PRIOR_SUMMARY_HEADER) + 400 + 1 + cost(grown, 4) > lim.maintenance_input_tokens
    maintenance = FakeMaintenance()
    v = view(grown, "compaction", p, lim=lim, checkpoint=prior, maintenance=maintenance)
    assert v.available, v.reason
    [request] = maintenance.requests
    assert request.covered_turn_ids == (1, 2, 3, 4) and prior.summary_text not in request.input_text
    assert render_ordinary_turn(grown.turns[0]) in request.input_text


def test_a_checkpoint_covering_more_than_the_summarized_range_is_resummarized() -> None:
    """A larger history budget can widen the exact tail, so an earlier checkpoint may cover turns
    that are now exact. It is not a prefix of the range and is not reused."""
    snap = make_snapshot([30, 30, 30, 30])
    p = params(compaction_tail_input_tokens=cost(snap, 3, 4))
    tight = view(snap, "compaction", p, lim=limits(history=authority(snap) + cost(snap, 4) + 200))
    assert tight.checkpoint is not None and tight.checkpoint.covered_turn_ids == (1, 2, 3)
    maintenance = FakeMaintenance()
    v = view(snap, "compaction", p, checkpoint=tight.checkpoint, maintenance=maintenance)
    assert v.covered_turn_ids == (1, 2) and [r.covered_turn_ids for r in maintenance.requests] == [(1, 2)]
    assert tight.checkpoint.summary_text not in maintenance.requests[0].input_text


def test_a_hybrid_checkpoint_made_while_the_first_turn_was_pinned_is_resummarized_when_it_is_not() -> None:
    snap = make_snapshot([400, 30, 30, 30])
    p = params(anchor_input_tokens=cost(snap, 1), hybrid_tail_input_tokens=cost(snap, 4))
    pinned = view(snap, "hybrid", p)
    assert pinned.head_turn_ids == (1,) and pinned.checkpoint is not None and pinned.checkpoint.covered_turn_ids == (2, 3)
    maintenance = FakeMaintenance()
    unpinned = view(snap, "hybrid", p, lim=limits(history=authority(snap) + cost(snap, 1) - 1), checkpoint=pinned.checkpoint, maintenance=maintenance)
    assert unpinned.available and unpinned.head_turn_ids == () and unpinned.covered_turn_ids == (1, 2, 3)
    [request] = maintenance.requests
    assert render_ordinary_turn(snap.turns[0]) in request.input_text and pinned.checkpoint.summary_text not in request.input_text


def test_a_stale_or_mismatched_checkpoint_is_resummarized_from_source() -> None:
    snap = make_snapshot([30, 30, 30, 30])
    other = make_snapshot([30, 30, 30, 30], session="s-other")
    p = params(compaction_tail_input_tokens=cost(snap, 4))
    foreign = view(other, "compaction", p).checkpoint
    maintenance = FakeMaintenance()
    v = view(snap, "compaction", p, checkpoint=foreign, maintenance=maintenance)
    assert v.available and [r.covered_turn_ids for r in maintenance.requests] == [(1, 2, 3)]
    assert foreign is not None and foreign.summary_text not in maintenance.requests[0].input_text


# --- Contract ------------------------------------------------------------------------------------------


def test_an_unknown_strategy_is_a_contract_error() -> None:
    with pytest.raises(ContractError, match="strategy"):
        view(make_snapshot([10]), "random", params())


def test_the_same_inputs_give_the_same_view() -> None:
    snap = make_snapshot([25, 70, 15, 40, 90, 5, 33])
    p = params(anchor_input_tokens=200, compaction_tail_input_tokens=150, hybrid_tail_input_tokens=300)
    for strategy in ("compaction", "hybrid", "sliding_window"):
        assert view(snap, strategy, p) == view(snap, strategy, p)


def test_the_engine_ships_no_default_policy() -> None:
    """Allocations come only from reviewed policy or tests (D1/D2); prepare_view has no defaults."""
    signature = inspect.signature(ContextEngine.prepare_view)
    assert all(p.default is inspect.Parameter.empty for name, p in signature.parameters.items() if name != "self")


def test_a_checkpoint_passed_to_prepare_view_must_be_a_checkpoint() -> None:
    with pytest.raises(ContractError):
        view(make_snapshot([10]), "compaction", params(), checkpoint="not a checkpoint")  # type: ignore[arg-type]
    assert SummaryCheckpoint  # imported for the type


# --- Dual-budget packing (CP4 correction C2) -----------------------------------------------------------
#
# Codex's final corrections (2026-10-04): every maintenance input must fit both its token limit and the
# transient UTF-8 byte limit, with a later chunk's prior summary counted at its maximum token estimate
# and byte length. Estimators below are `ceil(r * UTF-8 bytes)`, the supported profile.

_UNITS = {"ascii": "abcde ", "latin": "éàüöñ ", "cjk": "漢字仮名文 ", "emoji": "🙂🚀🧪🔧🎯 "}


def ratio_estimator(ratio: Fraction):
    return lambda text: math.ceil(len(text.encode("utf-8")) * ratio)


def byte_limits(ratio: Fraction, *, maintenance_input: int, transient: int, summary_tokens: int, history: int = 10_000_000) -> ViewLimits:
    return ViewLimits(
        history_input_tokens=history,
        source_max_bytes=10**9,
        transient_max_bytes=transient,
        maintenance_input_tokens=maintenance_input,
        maintenance_output_tokens=summary_tokens,
        summary_max_bytes=math.floor(summary_tokens / ratio),  # floor(S / r): never rejects what S admits
        estimate_history=ratio_estimator(ratio),
        estimator_id=f"utf8-bytes-ratio:{ratio}",
    )


def text_of(alphabet: str, size: int) -> str:
    """About `size` UTF-8 bytes of space-separated words, never more."""
    unit = _UNITS[alphabet]
    text = unit * (size // len(unit.encode("utf-8")))
    while len(text.encode("utf-8")) > size:
        text = text[:-1]
    return text


def turns_of(sizes: list[int], alphabet: str = "ascii", *, start: int = 1) -> list[OrdinaryTurn]:
    return [OrdinaryTurn(seq=seq, user_prompt=text_of(alphabet, size), plan_text="", completion_text=f"c{seq}") for seq, size in enumerate(sizes, start=start)]


def snapshot_of(turns: list[OrdinaryTurn], *, session: str = "s-c2") -> HistorySnapshot:
    turns_tuple = tuple(turns)
    protected = tuple(ProtectedTurnState(seq=t.seq, outcome="completed", effect_state="none", approval_facts=()) for t in turns_tuple)
    revision = HistoryRevision(session_key=session, generation=len(turns_tuple), last_committed_seq=turns_tuple[-1].seq, digest=history_digest(turns_tuple, protected))
    return HistorySnapshot(revision=revision, turns=turns_tuple, protected=protected)


def rendered_bytes(turn: OrdinaryTurn) -> int:
    return len(render_ordinary_turn(turn).encode("utf-8"))


class MaximalSummary:
    """A valid summary exactly `summary_max_bytes` long (ASCII, so its estimate stays within the token
    cap), or `fixed` text when given; records every request."""

    def __init__(self, lim: ViewLimits, *, fixed: str | None = None) -> None:
        self.requests: list[MaintenanceRequest] = []
        self._lim, self._fixed = lim, fixed

    def __call__(self, request: MaintenanceRequest) -> MaintenanceResult:
        self.requests.append(request)
        text = self._fixed if self._fixed is not None else summary_text(f"c{len(self.requests)}", length=self._lim.summary_max_bytes)
        return MaintenanceResult(summary_text=text, attempt_ids=(f"a{len(self.requests)}",), status="completed", finish_status="stop")


def assert_within(lim: ViewLimits, requests: list[MaintenanceRequest]) -> None:
    for request in requests:
        assert lim.estimate_history(request.input_text) <= lim.maintenance_input_tokens
        assert len(request.input_text.encode("utf-8")) <= lim.transient_max_bytes


def compaction(summary_tokens: int, calls: int) -> StrategyParameters:
    return params(compaction_tail_input_tokens=0, summary_output_tokens=summary_tokens, max_maintenance_calls=calls)


def test_a_low_ratio_cold_rebuild_of_about_900_kib_is_available_within_the_allowance() -> None:
    """Claude's simplicity-review probe B as a regression: at 0.2 tokens per byte the token-only planner
    packed a chunk over the 524288-byte transient bound, so every cold rebuild was refused, zero calls."""
    ratio = Fraction(1, 5)
    lim = byte_limits(ratio, maintenance_input=131_072, transient=524_288, summary_tokens=8_192)
    rng = random.Random(12)
    snap = snapshot_of(turns_of([rng.randrange(4_000, 13_000) for _ in range(110)]))
    assert sum(rendered_bytes(turn) for turn in snap.turns) > 900 * 1024
    maintenance = MaximalSummary(lim)

    v = view(snap, "compaction", compaction(8_192, 18), lim=lim, maintenance=maintenance)

    assert (v.available, v.reason) == (True, None)
    assert 1 < len(maintenance.requests) <= 18
    assert_within(lim, maintenance.requests)
    assert v.covered_turn_ids == tuple(turn.seq for turn in snap.turns)


@pytest.mark.parametrize("ratio", [Fraction(1), Fraction(1, 2), Fraction(1, 4), Fraction(1, 5)], ids=["1", "0.5", "0.25", "0.2"])
@pytest.mark.parametrize("alphabet", sorted(_UNITS))
def test_every_planned_input_fits_both_budgets_fresh_and_reused(ratio, alphabet) -> None:
    lim = byte_limits(ratio, maintenance_input=4_096, transient=16_384, summary_tokens=512)
    # The largest turn a non-first chunk can take in each budget: the tokens left beside a maximal prior
    # summary, as bytes, and the bytes left beside it.
    token_room = lim.maintenance_input_tokens - lim.estimate_history(PRIOR_SUMMARY_HEADER) - 512 - lim.estimate_history("\n")
    capacity = min(math.floor(token_room / ratio), lim.transient_max_bytes - len(PRIOR_SUMMARY_HEADER) - lim.summary_max_bytes - 1)
    rng = random.Random(f"{ratio}-{alphabet}")
    sizes = [rng.choice([capacity // 40, capacity // 7, capacity // 2 - 60, int(capacity * 0.8)]) for _ in range(45)]
    turns = turns_of(sizes, alphabet)
    assert max(rendered_bytes(turn) for turn in turns) <= capacity  # every turn fits: no false refusal
    first, later = turns[:40], turns[40:]

    fresh = MaximalSummary(lim)
    v1 = view(snapshot_of(first), "compaction", compaction(512, 100), lim=lim, maintenance=fresh)
    assert (v1.available, v1.reason) == (True, None)
    assert len(fresh.requests) > 1
    assert_within(lim, fresh.requests)

    reused = MaximalSummary(lim)
    v2 = view(snapshot_of(first + later), "compaction", compaction(512, 100), lim=lim, checkpoint=v1.checkpoint, maintenance=reused)
    assert (v2.available, v2.reason) == (True, None)
    assert reused.requests and reused.requests[0].input_text.startswith(PRIOR_SUMMARY_HEADER)  # merged, not rebuilt
    assert_within(lim, reused.requests)


def test_an_assembled_input_exactly_at_the_byte_limit_is_sent_and_one_byte_more_splits() -> None:
    ratio = Fraction(1, 100)  # tokens never bind here
    turns = turns_of([900, 1_100])
    exact = rendered_bytes(turns[0]) + 1 + rendered_bytes(turns[1])

    at_limit = byte_limits(ratio, maintenance_input=10**6, transient=exact, summary_tokens=5)
    maintenance = MaximalSummary(at_limit)
    v = view(snapshot_of(turns), "compaction", compaction(5, 3), lim=at_limit, maintenance=maintenance)
    assert v.available and [len(r.input_text.encode("utf-8")) for r in maintenance.requests] == [exact]

    over = byte_limits(ratio, maintenance_input=10**6, transient=exact - 1, summary_tokens=5)
    maintenance = MaximalSummary(over)
    v = view(snapshot_of(turns), "compaction", compaction(5, 3), lim=over, maintenance=maintenance)
    assert v.available and len(maintenance.requests) == 2
    assert_within(over, maintenance.requests)


def test_a_single_turn_one_byte_over_the_transient_bound_is_refused_before_any_call() -> None:
    ratio = Fraction(1, 100)
    turns = turns_of([3_000])
    size = rendered_bytes(turns[0])

    lim = byte_limits(ratio, maintenance_input=10**6, transient=size, summary_tokens=5)
    fits = MaximalSummary(lim)
    assert view(snapshot_of(turns), "compaction", compaction(5, 3), lim=lim, maintenance=fits).available
    assert len(fits.requests) == 1

    lim = byte_limits(ratio, maintenance_input=10**6, transient=size - 1, summary_tokens=5)
    refused = MaximalSummary(lim)
    v = view(snapshot_of(turns), "compaction", compaction(5, 3), lim=lim, maintenance=refused)
    assert (v.available, v.reason, refused.requests) == (False, "turn exceeds maintenance input", [])


def test_a_plan_over_the_call_allowance_by_bytes_is_refused_before_any_call() -> None:
    ratio = Fraction(1, 100)
    turns = turns_of([2_000, 2_000])
    lim = byte_limits(ratio, maintenance_input=10**6, transient=rendered_bytes(turns[0]) + 1_000, summary_tokens=5)
    maintenance = MaximalSummary(lim)

    v = view(snapshot_of(turns), "compaction", compaction(5, 1), lim=lim, maintenance=maintenance)

    assert (v.available, v.reason, maintenance.requests) == (False, "maintenance allowance exceeded", [])


def test_a_summary_exactly_at_the_byte_bound_is_accepted_and_one_byte_more_is_not() -> None:
    # A token cap of 100 at 0.01 tokens per byte allows 10,000 bytes, so only the byte bound decides.
    lim = dataclasses.replace(byte_limits(Fraction(1, 100), maintenance_input=10**6, transient=100_000, summary_tokens=100), summary_max_bytes=2_000)
    snap = snapshot_of(turns_of([500, 500]))

    exact = view(snap, "compaction", compaction(100, 3), lim=lim, maintenance=MaximalSummary(lim, fixed=summary_text("s", length=2_000)))
    over = view(snap, "compaction", compaction(100, 3), lim=lim, maintenance=MaximalSummary(lim, fixed=summary_text("s", length=2_001)))

    assert (exact.available, exact.reason) == (True, None)
    assert (over.available, over.reason) == (False, "summary exceeds bound")


def test_a_reused_summary_over_todays_byte_bound_is_rebuilt_from_source() -> None:
    # The same token cap and parameters, so only the byte bound differs between the two turns.
    roomy = dataclasses.replace(byte_limits(Fraction(1, 100), maintenance_input=10**6, transient=100_000, summary_tokens=100), summary_max_bytes=4_000)
    tight = dataclasses.replace(roomy, summary_max_bytes=2_000)
    turns = turns_of([500, 500, 500, 500])
    old = view(snapshot_of(turns[:3]), "compaction", compaction(100, 3), lim=roomy, maintenance=MaximalSummary(roomy))
    assert old.checkpoint is not None and len(old.checkpoint.summary_text.encode("utf-8")) == 4_000

    maintenance = MaximalSummary(tight)
    v = view(snapshot_of(turns), "compaction", compaction(100, 3), lim=tight, checkpoint=old.checkpoint, maintenance=maintenance)

    assert (v.available, v.reason) == (True, None)
    assert not maintenance.requests[0].input_text.startswith(PRIOR_SUMMARY_HEADER)  # from source, not the old summary
    assert maintenance.requests[0].covered_turn_ids[0] == 1


def test_a_non_subadditive_estimator_never_sends_an_oversized_input() -> None:
    """The planner sums per-piece estimates, which `ViewLimits` allows only for a subadditive
    estimator. A deliberately non-conforming one under-counts the joined input; the check of each
    assembled input before its call still refuses it."""

    def superadditive(text: str) -> int:
        n = len(text.encode("utf-8"))
        return n + n * n // 1_000_000

    turns = turns_of([1_000] * 10)
    pieces = sum(superadditive(render_ordinary_turn(turn)) for turn in turns) + 9 * superadditive("\n")
    lim = dataclasses.replace(
        byte_limits(Fraction(1), maintenance_input=pieces, transient=10**6, summary_tokens=5), estimate_history=superadditive, estimator_id="superadditive-test"
    )
    assert superadditive("\n".join(render_ordinary_turn(turn) for turn in turns)) > lim.maintenance_input_tokens
    maintenance = MaximalSummary(lim)

    v = view(snapshot_of(turns), "compaction", compaction(5, 3), lim=lim, maintenance=maintenance)

    assert (v.available, v.reason, maintenance.requests) == (False, "maintenance input exceeded", [])


@pytest.mark.parametrize("summary_max_bytes", [0, 10_000_000])
def test_the_summary_byte_bound_is_positive_and_below_the_transient_bound(summary_max_bytes) -> None:
    with pytest.raises(ContractError, match="summary_max_bytes"):
        limits(summary_max_bytes=summary_max_bytes)


def test_the_summary_byte_bound_has_no_default() -> None:
    with pytest.raises(TypeError):
        ViewLimits(100, 1_000, 1_000, 100, 10, estimate_history=chars, estimator_id="chars-v1")  # type: ignore[call-arg]
