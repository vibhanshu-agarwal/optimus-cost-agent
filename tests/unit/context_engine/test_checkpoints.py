"""Plan 12.2 Task 6: immutable contracts, checkpoint reuse and compare-and-publish.

Design spec 5 and Task 1 contracts 2. A snapshot's revision digest must match its content. A summary
checkpoint is reused only by append-only prefix validation: every covered source digest, the same
strategy, parameters and format, and a covered range that is the snapshot's oldest turns. It is then
re-keyed to the current revision. Publication compares against the current revision and parameter
digest, so a stale or cancelled paid result can never publish.
"""

from __future__ import annotations

import dataclasses

import pytest

from context_engine import (
    ContractError,
    HistoryRevision,
    HistorySnapshot,
    OrdinaryTurn,
    PreparedView,
    ProtectedTurnState,
    StrategyParameters,
    SummaryCheckpoint,
    history_digest,
    publish_checkpoint,
    reuse_checkpoint,
    turn_source_digest,
)

PARAMS = StrategyParameters(
    anchor_input_tokens=100,
    compaction_tail_input_tokens=200,
    hybrid_tail_input_tokens=400,
    summary_output_tokens=50,
    max_maintenance_calls=2,
    prompt_version="summary-prompt-v1",
    format_version="context-summary-v1",
)


def _turn(seq: int, text: str = "") -> OrdinaryTurn:
    return OrdinaryTurn(seq=seq, user_prompt=f"ask {seq}{text}", plan_text="", completion_text=f"done {seq}")


def _state(seq: int, *, outcome: str = "completed", effect: str = "none", facts: tuple[str, ...] = ()) -> ProtectedTurnState:
    return ProtectedTurnState(seq=seq, outcome=outcome, effect_state=effect, approval_facts=facts)


def snapshot(seqs: tuple[int, ...] | int, *, session: str = "s-1", generation: int | None = None, edits: dict[int, str] | None = None) -> HistorySnapshot:
    ids = tuple(range(1, seqs + 1)) if isinstance(seqs, int) else seqs
    turns = tuple(_turn(i, (edits or {}).get(i, "")) for i in ids)
    protected = tuple(_state(i) for i in ids)
    revision = HistoryRevision(
        session_key=session,
        generation=len(ids) if generation is None else generation,
        last_committed_seq=ids[-1] if ids else 0,
        digest=history_digest(turns, protected),
    )
    return HistorySnapshot(revision=revision, turns=turns, protected=protected)


def checkpoint(snap: HistorySnapshot, covered: tuple[int, ...], **changes: object) -> SummaryCheckpoint:
    by_seq = {turn.seq: turn for turn in snap.turns}
    fields: dict[str, object] = {
        "revision": snap.revision,
        "covered_turn_ids": covered,
        "source_digests": tuple(turn_source_digest(by_seq[seq]) for seq in covered),
        "strategy": "compaction",
        "parameters_digest": PARAMS.digest,
        "format_version": PARAMS.format_version,
        "summary_text": "Task context: build a calculator.",
    }
    fields.update(changes)
    return SummaryCheckpoint(**fields)  # type: ignore[arg-type]


# --- Snapshot integrity ------------------------------------------------------------------------------


def test_a_well_formed_snapshot_is_accepted() -> None:
    snap = snapshot(3)
    assert snap.ids == (1, 2, 3)
    assert snap.revision.last_committed_seq == 3


def test_an_empty_history_is_a_valid_snapshot() -> None:
    snap = snapshot(())
    assert (snap.ids, snap.revision.last_committed_seq) == ((), 0)


def test_a_revision_digest_that_does_not_match_the_content_is_rejected() -> None:
    snap = snapshot(3)
    with pytest.raises(ContractError, match="digest"):
        HistorySnapshot(revision=dataclasses.replace(snap.revision, digest="0" * 64), turns=snap.turns, protected=snap.protected)


@pytest.mark.parametrize(
    "turns, protected, last, error",
    [
        ((2, 1), (2, 1), 1, "strictly increasing"),
        ((1, 1), (1, 1), 1, "strictly increasing"),
        ((1, 2), (1,), 2, "one protected record"),
        ((1, 2), (1, 3), 2, "one protected record"),
        ((1, 2), (1, 2), 3, "last_committed_seq"),
    ],
    ids=["unordered", "duplicate", "missing-protected", "foreign-protected", "wrong-last-seq"],
)
def test_malformed_snapshots_are_validation_failures(turns, protected, last, error) -> None:
    """Each case carries the digest of its own content, so only the targeted check can reject it."""
    ordinary = tuple(_turn(i) for i in turns)
    states = tuple(_state(i) for i in protected)
    digest = history_digest(ordinary, states) if len(ordinary) == len(states) else "a" * 64
    with pytest.raises(ContractError, match=error):
        HistorySnapshot(
            revision=HistoryRevision(session_key="s", generation=2, last_committed_seq=last, digest=digest),
            turns=ordinary,
            protected=states,
        )


def test_host_enums_cannot_cross_the_boundary() -> None:
    """A host `StrEnum` is a `str` subclass; the contract accepts exact `str` only."""
    from enum import StrEnum

    class HostOutcome(StrEnum):
        COMPLETED = "completed"

    with pytest.raises(ContractError, match="outcome"):
        ProtectedTurnState(seq=1, outcome=HostOutcome.COMPLETED, effect_state="none", approval_facts=())


@pytest.mark.parametrize(
    "build",
    [
        lambda: OrdinaryTurn(seq=True, user_prompt="a", plan_text="", completion_text=""),
        lambda: OrdinaryTurn(seq=0, user_prompt="a", plan_text="", completion_text=""),
        lambda: OrdinaryTurn(seq=1, user_prompt="\ud800", plan_text="", completion_text=""),
        lambda: ProtectedTurnState(seq=1, outcome="completed", effect_state="none", approval_facts=["granted"]),
        lambda: ProtectedTurnState(seq=1, outcome="", effect_state="none", approval_facts=()),
        lambda: HistoryRevision(session_key="", generation=0, last_committed_seq=0, digest="a" * 64),
        lambda: HistoryRevision(session_key="s", generation=-1, last_committed_seq=0, digest="a" * 64),
        lambda: HistoryRevision(session_key="s", generation=0, last_committed_seq=0, digest="A" * 64),
    ],
    ids=["bool-seq", "zero-seq", "lone-surrogate", "list-not-tuple", "empty-outcome", "empty-session", "negative-generation", "uppercase-digest"],
)
def test_records_reject_values_outside_the_contract(build) -> None:
    with pytest.raises(ContractError):
        build()


def test_every_protected_fact_is_part_of_the_history_digest() -> None:
    turns = (_turn(1),)
    base = history_digest(turns, (_state(1),))
    variants = {
        history_digest(turns, (_state(1, outcome="rejected"),)),
        history_digest(turns, (_state(1, effect="complete"),)),
        history_digest(turns, (_state(1, facts=("denied:abc",)),)),
        history_digest((_turn(1, "!"),), (_state(1),)),
    }
    assert base not in variants and len(variants) == 4


@pytest.mark.parametrize("field", ["user_prompt", "plan_text", "completion_text", "seq"])
def test_every_ordinary_field_is_part_of_the_source_digest(field) -> None:
    """A checkpoint's coverage is bound to every field of its source turns, including the plan."""
    turn = OrdinaryTurn(seq=1, user_prompt="ask", plan_text="WRITE a.py", completion_text="done")
    changed = dataclasses.replace(turn, **{field: 2 if field == "seq" else getattr(turn, field) + "!"})
    assert turn_source_digest(changed) != turn_source_digest(turn)


def test_fact_boundaries_are_unambiguous() -> None:
    """Length-prefixed fields: moving text between adjacent fields changes the digest."""
    a = OrdinaryTurn(seq=1, user_prompt="ab", plan_text="c", completion_text="")
    b = OrdinaryTurn(seq=1, user_prompt="a", plan_text="bc", completion_text="")
    assert turn_source_digest(a) != turn_source_digest(b)
    one, two = _state(1, facts=("ab", "c")), _state(1, facts=("a", "bc"))
    assert history_digest((_turn(1),), (one,)) != history_digest((_turn(1),), (two,))


# --- Parameters -------------------------------------------------------------------------------------


def test_the_parameter_digest_is_deterministic_and_covers_every_field() -> None:
    assert PARAMS.digest == dataclasses.replace(PARAMS).digest
    for field in dataclasses.fields(StrategyParameters):
        value = getattr(PARAMS, field.name)
        changed = value + "-x" if isinstance(value, str) else value + 1
        assert dataclasses.replace(PARAMS, **{field.name: changed}).digest != PARAMS.digest, field.name


def test_maintenance_parameters_need_a_positive_output_and_call_budget() -> None:
    with pytest.raises(ContractError):
        dataclasses.replace(PARAMS, summary_output_tokens=0)
    with pytest.raises(ContractError):
        dataclasses.replace(PARAMS, max_maintenance_calls=-1)
    # Sliding window makes no maintenance calls: zero calls is a valid parameter set.
    assert dataclasses.replace(PARAMS, max_maintenance_calls=0).max_maintenance_calls == 0


# --- Checkpoint construction --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "covered, digests",
    [((2, 1), 2), ((1, 1), 2), ((1, 2), 1), ((), 0)],
    ids=["unordered", "overlapping", "digest-count", "empty"],
)
def test_a_checkpoint_with_malformed_coverage_is_rejected(covered, digests) -> None:
    snap = snapshot(3)
    with pytest.raises(ContractError):
        SummaryCheckpoint(
            revision=snap.revision,
            covered_turn_ids=covered,
            source_digests=tuple(turn_source_digest(snap.turns[0]) for _ in range(digests)),
            strategy="compaction",
            parameters_digest=PARAMS.digest,
            format_version=PARAMS.format_version,
            summary_text="x",
        )


def test_a_sliding_window_never_has_a_checkpoint() -> None:
    snap = snapshot(3)
    with pytest.raises(ContractError, match="strategy"):
        checkpoint(snap, (1,), strategy="sliding_window")


# --- Append-only prefix reuse -------------------------------------------------------------------------


def test_an_append_only_prefix_is_reused_and_rekeyed_to_the_current_revision() -> None:
    earlier, current = snapshot(3), snapshot(5)
    result = reuse_checkpoint(checkpoint(earlier, (1, 2)), current, strategy="compaction", parameters=PARAMS)
    assert result.reason is None
    assert result.checkpoint is not None
    assert result.checkpoint.revision == current.revision
    assert result.checkpoint.covered_turn_ids == (1, 2)
    assert result.checkpoint.summary_text == "Task context: build a calculator."


def test_a_changed_covered_source_is_not_reused() -> None:
    earlier = snapshot(3)
    current = snapshot(5, edits={2: " (edited)"})
    result = reuse_checkpoint(checkpoint(earlier, (1, 2)), current, strategy="compaction", parameters=PARAMS)
    assert (result.checkpoint, result.reason) == (None, "covered source changed")


@pytest.mark.parametrize(
    "changes, strategy, reason",
    [
        ({}, "hybrid", "strategy mismatch"),
        ({"parameters_digest": "f" * 64}, "compaction", "parameters mismatch"),
        ({"format_version": "context-summary-v0"}, "compaction", "format mismatch"),
    ],
    ids=["strategy", "parameters", "format"],
)
def test_identity_mismatches_are_not_reused(changes, strategy, reason) -> None:
    earlier, current = snapshot(3), snapshot(4)
    result = reuse_checkpoint(checkpoint(earlier, (1, 2), **changes), current, strategy=strategy, parameters=PARAMS)
    assert (result.checkpoint, result.reason) == (None, reason)


def test_a_missing_covered_source_is_not_reused() -> None:
    earlier = snapshot(3)
    current = snapshot((1, 2, 4, 5), generation=5)
    result = reuse_checkpoint(checkpoint(earlier, (1, 2, 3)), current, strategy="compaction", parameters=PARAMS)
    assert (result.checkpoint, result.reason) == (None, "covered source missing")


def test_a_future_revision_is_not_reused() -> None:
    later, current = snapshot(5), snapshot(4)
    result = reuse_checkpoint(checkpoint(later, (1, 2)), current, strategy="compaction", parameters=PARAMS)
    assert (result.checkpoint, result.reason) == (None, "future revision")


@pytest.mark.parametrize(
    "strategy, covered",
    [("compaction", (2, 3)), ("compaction", (1, 3)), ("hybrid", (3, 4)), ("hybrid", (2, 4))],
    ids=["compaction-late-start", "compaction-gap", "hybrid-late-start", "hybrid-gap"],
)
def test_coverage_that_is_not_the_summarizable_prefix_is_not_reused(strategy, covered) -> None:
    """Compaction summarizes from the first turn; hybrid may pin the first turn exactly and summarize
    from the second. Either way the covered range is contiguous: no gap, no late start."""
    earlier, current = snapshot(4), snapshot(5)
    result = reuse_checkpoint(checkpoint(earlier, covered, strategy=strategy), current, strategy=strategy, parameters=PARAMS)
    assert (result.checkpoint, result.reason) == (None, "coverage is not a prefix")


def test_a_hybrid_checkpoint_after_the_pinned_first_turn_is_reused() -> None:
    earlier, current = snapshot(4), snapshot(5)
    result = reuse_checkpoint(checkpoint(earlier, (2, 3), strategy="hybrid"), current, strategy="hybrid", parameters=PARAMS)
    assert result.reason is None and result.checkpoint is not None


def test_another_sessions_checkpoint_is_never_reused() -> None:
    """Session identity alone never makes a checkpoint fresh, and another session's never applies."""
    earlier, current = snapshot(3, session="s-other"), snapshot(4)
    result = reuse_checkpoint(checkpoint(earlier, (1, 2)), current, strategy="compaction", parameters=PARAMS)
    assert (result.checkpoint, result.reason) == (None, "other session")


# --- Compare-and-publish ------------------------------------------------------------------------------


def test_a_current_uncancelled_candidate_publishes() -> None:
    snap = snapshot(4)
    candidate = checkpoint(snap, (1, 2))
    assert publish_checkpoint(candidate, current_revision=snap.revision, current_parameters_digest=PARAMS.digest, cancelled=False)


@pytest.mark.parametrize("cancelled, revision_turns, params_digest", [(True, 4, None), (False, 5, None), (False, 4, "e" * 64)], ids=["cancelled", "stale-revision", "changed-parameters"])
def test_a_stale_or_cancelled_candidate_never_publishes(cancelled, revision_turns, params_digest) -> None:
    snap = snapshot(4)
    candidate = checkpoint(snap, (1, 2))
    current = snapshot(revision_turns)
    assert not publish_checkpoint(
        candidate,
        current_revision=current.revision,
        current_parameters_digest=params_digest or PARAMS.digest,
        cancelled=cancelled,
    )


def test_a_stale_paid_result_publishes_only_after_a_validated_rekey() -> None:
    """A summary paid for at revision 4 is stale once turn 5 commits; it may publish only if its
    covered prefix still validates against the new snapshot."""
    at_four, at_five = snapshot(4), snapshot(5)
    paid = checkpoint(at_four, (1, 2))
    assert not publish_checkpoint(paid, current_revision=at_five.revision, current_parameters_digest=PARAMS.digest, cancelled=False)
    rekeyed = reuse_checkpoint(paid, at_five, strategy="compaction", parameters=PARAMS).checkpoint
    assert rekeyed is not None
    assert publish_checkpoint(rekeyed, current_revision=at_five.revision, current_parameters_digest=PARAMS.digest, cancelled=False)


# --- Prepared view partitions -------------------------------------------------------------------------


def _view(**changes: object) -> PreparedView:
    snap = snapshot(4)
    fields: dict[str, object] = {
        "head_turn_ids": (1,),
        "tail_turn_ids": (4,),
        "checkpoint": checkpoint(snap, (2, 3), strategy="hybrid"),
        "protected": snap.protected,
        "covered_turn_ids": (2, 3),
        "omitted_turn_ids": (),
        "available": True,
        "reason": None,
    }
    fields.update(changes)
    return PreparedView(**fields)  # type: ignore[arg-type]


def test_a_view_with_disjoint_partitions_is_accepted() -> None:
    assert _view().available


@pytest.mark.parametrize(
    "changes",
    [{"tail_turn_ids": (3, 4)}, {"head_turn_ids": (1, 4)}, {"omitted_turn_ids": (2,)}],
    ids=["tail-overlaps-summary", "head-overlaps-tail", "omitted-overlaps-summary"],
)
def test_overlapping_partitions_are_rejected(changes) -> None:
    with pytest.raises(ContractError, match="overlap"):
        _view(**changes)


@pytest.mark.parametrize(
    "changes",
    [{"covered_turn_ids": (2,)}, {"checkpoint": None}, {"checkpoint": None, "covered_turn_ids": (), "omitted_turn_ids": (2, 3)}],
    ids=["covered-differs", "covered-without-checkpoint", "no-summary-is-fine"],
)
def test_a_views_covered_turns_are_exactly_its_checkpoints(changes) -> None:
    if changes.get("omitted_turn_ids"):
        assert _view(**changes).covered_turn_ids == ()
        return
    with pytest.raises(ContractError, match="coverage"):
        _view(**changes)


def test_an_unavailable_view_states_its_reason() -> None:
    with pytest.raises(ContractError, match="reason"):
        _view(available=False, reason=None)
    assert _view(available=False, reason="maintenance unavailable").reason == "maintenance unavailable"
