"""Plan 12.9 Task 1: deterministic accounting fixtures for the usage report's arithmetic (B1, one subtraction)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from optimus_gateway.usage_report import AttemptFact, TurnFact, auto_scope, compare, price_attempt, totals
from optimus_model_policy.savings_references import CategoryPrices, Reference, Source, Tier

D = Decimal


def _reference(ref_id="ref-a", *, input="1", output="4", cached="0.1", reasoning=True, as_of=date(2026, 11, 1), tiers=()):
    return Reference(
        id=ref_id, display=ref_id, unit="usd_per_million_tokens",
        prices=CategoryPrices(input=input, output=output, cached_input=cached), tiers=tiers,
        reasoning_billed_as_output=reasoning, source=Source(url="https://example.test/p", price_as_of=as_of),
    )


def _attempt(attempt_id="a1", turn="t1", *, cost="0.002", stage="planning", outcome="completed", inp=1000, out=200,
             cached=0, reasoning=0, late=False, conflict=False):
    return AttemptFact(attempt_id, turn, stage, outcome, None if cost is None else D(cost), inp, out, cached, reasoning,
                       late, conflict)


_COMPLETE = [TurnFact("t1", "complete", "auto")]


def test_one_subtraction_includes_overhead_once():
    # A planning call and Auto's own classification call: both are in the actual total and both are repriced.
    attempts = [_attempt("a1", cost="0.0012", inp=1000, out=200, cached=400),
                _attempt("c1", cost="0.0001", stage="classification", inp=100, out=0)]
    actual = totals(attempts, _COMPLETE)

    column = compare(attempts, actual, _reference())

    # a1: 600 x 1/M + 400 x 0.1/M + 200 x 4/M = 0.00144; c1: 100 x 1/M = 0.0001
    assert column.baseline_known_usd == D("0.00154")
    assert actual.known_usd == D("0.0013")
    assert column.savings_usd == D("0.00024")
    assert column.savings_percent == D("15.6")
    assert column.complete and column.reasons == ()


def test_negative_savings_stay_signed_and_visible():
    attempts = [_attempt(cost="0.01", inp=1000, out=200)]

    column = compare(attempts, totals(attempts, _COMPLETE), _reference())

    assert column.savings_usd == D("0.0018") - D("0.01") < 0
    assert column.savings_percent == D("-455.6")


def test_a_zero_baseline_has_savings_but_no_percentage():
    attempts = [_attempt(cost="0", outcome="not_sent", inp=None, out=None, cached=None, reasoning=None)]

    column = compare(attempts, totals(attempts, _COMPLETE), _reference())

    assert column.baseline_known_usd == 0 and column.savings_usd == 0 and column.savings_percent is None


def test_unknown_cost_keeps_the_known_subtotal_and_withholds_savings():
    attempts = [_attempt("a1", cost="0.001"), _attempt("a2", cost=None, outcome="uncertain", inp=None, out=None)]
    actual = totals(attempts, _COMPLETE)

    column = compare(attempts, actual, _reference())

    assert actual.known_usd == D("0.001") and actual.unknown_attempts == 1 and "unknown_cost" in actual.reasons
    assert column.savings_usd is None and column.savings_percent is None
    assert set(column.reasons) == {"actual_incomplete", "unpriced_attempts"}


@pytest.mark.parametrize(
    ("attempt", "reference", "reason"),
    [
        (_attempt(cached=400), _reference(cached=None), "price_missing_cached_input"),
        (_attempt(cached=0), _reference(input=None), "price_missing_input"),
        (_attempt(), _reference(output=None), "price_missing_output"),
        (_attempt(cached=None), _reference(), "cached_split_unreported"),
        (_attempt(reasoning=None), _reference(reasoning=None), "reasoning_split_unreported"),
        (_attempt(reasoning=50), _reference(reasoning=None), "reasoning_split_unreported"),
        (_attempt(cached=1001), _reference(), "categories_inconsistent"),
        (_attempt(reasoning=201), _reference(), "categories_inconsistent"),
        (_attempt(inp=None), _reference(), "tokens_unreported"),
    ],
)
def test_a_null_category_is_never_priced_as_zero_or_at_another_price(attempt, reference, reason):
    assert price_attempt(attempt, reference) == reason


def test_a_split_that_cannot_change_the_price_is_not_needed():
    # Unknown cached share, but cached and uncached input cost the same; unknown reasoning share, billed as output.
    assert price_attempt(_attempt(cached=None), _reference(cached="1")) == D("0.0018")
    assert price_attempt(_attempt(reasoning=None), _reference()) == D("0.0018")
    assert price_attempt(_attempt(reasoning=0), _reference(reasoning=None)) == D("0.0018")


def test_a_long_context_tier_prices_the_whole_request_from_its_threshold():
    reference = _reference(tiers=(Tier(min_input_tokens=1000, prices=CategoryPrices(input="2", output="8", cached_input="0.2")),))

    assert price_attempt(_attempt(inp=999, out=0), reference) == D("0.000999")
    assert price_attempt(_attempt(inp=1000, out=0), reference) == D("0.002")


def test_each_reference_is_assessed_on_its_own():
    attempts = [_attempt(cached=400)]
    actual = totals(attempts, _COMPLETE)

    undated = compare(attempts, actual, _reference("ref-b", as_of=None))
    unpriced = compare(attempts, actual, _reference("ref-c", cached=None))
    complete = compare(attempts, actual, _reference("ref-a"))

    assert undated.reasons == ("source_date_missing",) and undated.savings_usd is None
    assert unpriced.reasons == ("unpriced_attempts",) and unpriced.unpriced == (("price_missing_cached_input", 1, 1200),)
    assert complete.complete and complete.savings_usd is not None


@pytest.mark.parametrize(
    ("turns", "kwargs", "reason"),
    [
        ([TurnFact("t1", "open", "auto")], {}, "epoch_open"),
        ([TurnFact("t1", "incomplete", "auto")], {}, "epoch_incomplete"),
        ([TurnFact("t1", None, "auto")], {}, "epoch_missing"),
        # A session that ran turns before durable capture (or whose turns never reached the ledger): qualified history.
        (_COMPLETE, {"expected_turns": 3}, "turn_not_captured"),
        (_COMPLETE, {"delivery_pending": True}, "delivery_pending"),
        (_COMPLETE, {"unattributed_turns": 1}, "attribution_unavailable"),
    ],
)
def test_coverage_is_not_definitive_for_each_stated_reason(turns, kwargs, reason):
    actual = totals([_attempt()], turns, **kwargs)

    assert actual.reasons == (reason,) and not actual.definitive
    assert compare([_attempt()], actual, _reference()).savings_usd is None


def test_late_and_conflicting_receipts_keep_their_known_charge_and_block_a_definitive_total():
    attempts = [_attempt("a1", late=True), _attempt("a2", conflict=True)]

    actual = totals(attempts, _COMPLETE)

    assert actual.known_usd == D("0.004") and actual.late == 1 and actual.conflicts == 1
    assert actual.reasons == ("late_receipt", "receipt_conflict")


def test_a_repeated_attempt_is_refused_so_nothing_is_charged_twice():
    with pytest.raises(ValueError, match="more than once"):
        totals([_attempt("a1"), _attempt("a1")], _COMPLETE)


def test_the_auto_scope_is_only_turns_explicitly_attributed_auto():
    turns = [TurnFact("t1", "complete", "auto"), TurnFact("t2", "complete", "fixed"), TurnFact("t3", "complete", None)]
    attempts = [_attempt("a1", "t1"), _attempt("a2", "t2"), _attempt("a3", "t3")]

    auto_attempts, auto_turns = auto_scope(attempts, turns)

    assert [a.attempt_id for a in auto_attempts] == ["a1"] and [t.turn_id for t in auto_turns] == ["t1"]


def test_no_attempts_is_not_a_saving():
    column = compare([], totals([], []), _reference())

    assert column.reasons == ("no_attempts",) and column.savings_usd is None
