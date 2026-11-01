"""The usage report's arithmetic (Plan 12.9; ADR-034): measured totals with coverage, and B1 comparison columns.

Pure functions over canonical ledger facts: one fact per canonical attempt (aliases and replays are the reader's to
fold, so a repeated attempt ID here is a defect and refused). Money is `Decimal`; an unknown cost or token count is
None and is never read as zero.

B1 reprices each attempt's reported tokens at a reference's own dated list prices and subtracts the actual fully
loaded total once. Optimus's overhead (classification, summarization, retries, escalation) is already in that total,
so nothing is deducted twice. A column's savings and percentage appear only when everything it compares is known.

Token categories nest as the provider reports them (OpenRouter usage accounting, fetched 2026-11-01, Plan 12.9
Task 0): ``cached_tokens`` is a breakdown of ``input_tokens`` and ``reasoning_tokens`` of ``output_tokens``, so
``total_tokens`` is input plus output. `test_upstream_client` pins that the adapter keeps this nesting.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from optimus_model_policy.savings_references import TOKENS_PER_PRICE_UNIT, CategoryPrices, Reference

_PERCENT_STEP = Decimal("0.1")


@dataclass(frozen=True)
class AttemptFact:
    attempt_id: str
    turn_id: str
    stage: str
    outcome: str
    cost_usd: Decimal | None
    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    reasoning_tokens: int | None
    late: bool = False
    conflict: bool = False


@dataclass(frozen=True)
class TurnFact:
    turn_id: str
    epoch_state: str | None  # "complete", "open", "incomplete", or None when no epoch was captured
    selection: str | None  # "auto" or "fixed" from turn.report_context; None when the turn is unattributed


@dataclass(frozen=True)
class Totals:
    known_usd: Decimal
    attempts: int
    unknown_attempts: int
    conflicts: int
    late: int
    turns: int
    reasons: tuple[str, ...]

    @property
    def definitive(self) -> bool:
        return not self.reasons


@dataclass(frozen=True)
class Column:
    reference_id: str
    snapshot_id: str
    price_as_of: str | None
    baseline_known_usd: Decimal
    priced_attempts: int
    unpriced: tuple[tuple[str, int, int | None], ...]  # (reason, attempts, tokens)
    reasons: tuple[str, ...]
    savings_usd: Decimal | None
    savings_percent: Decimal | None

    @property
    def complete(self) -> bool:
        return not self.reasons


def _unique(attempts: Sequence[AttemptFact]) -> None:
    repeated = [key for key, count in Counter(a.attempt_id for a in attempts).items() if count > 1]
    if repeated:
        raise ValueError(f"attempt {repeated[0]!r} appears more than once; the reader must fold aliases and replays")


def totals(attempts: Sequence[AttemptFact], turns: Sequence[TurnFact], *, expected_turns: int | None = None,
           delivery_pending: bool = False, unattributed_turns: int = 0) -> Totals:
    """Measured known cost for one scope, and every reason it is not definitive (empty when it is).
    ``unattributed_turns`` counts session turns of unknown selection: any of them might belong to an Auto scope."""
    _unique(attempts)
    reasons: set[str] = set()
    states = Counter(turn.epoch_state for turn in turns)
    if states[None]:
        reasons.add("epoch_missing")
    if states["open"]:
        reasons.add("epoch_open")
    if states["incomplete"]:
        reasons.add("epoch_incomplete")
    if expected_turns is not None and expected_turns > len(turns):
        reasons.add("turn_not_captured")
    if delivery_pending:
        reasons.add("delivery_pending")
    if unattributed_turns:
        reasons.add("attribution_unavailable")
    unknown = sum(a.cost_usd is None for a in attempts)
    conflicts = sum(a.conflict for a in attempts)
    late = sum(a.late for a in attempts)
    if unknown:
        reasons.add("unknown_cost")
    if conflicts:
        reasons.add("receipt_conflict")
    if late:
        reasons.add("late_receipt")
    known = sum((a.cost_usd for a in attempts if a.cost_usd is not None), Decimal(0))
    return Totals(known, len(attempts), unknown, conflicts, late, len(turns), tuple(sorted(reasons)))


def _rate(price: Decimal | None) -> Decimal:
    """USD per token. Callers refuse a None price wherever it would multiply a positive count first."""
    return Decimal(0) if price is None else price / TOKENS_PER_PRICE_UNIT


def _input_cost(attempt: AttemptFact, prices: CategoryPrices) -> Decimal | str:
    total, cached = attempt.input_tokens, attempt.cached_tokens
    assert total is not None
    if cached is None:  # the split is unknown; it matters only when the two prices differ
        if prices.input is not None and prices.input == prices.cached_input:
            return total * _rate(prices.input)
        return "cached_split_unreported"
    if cached > total:
        return "categories_inconsistent"
    uncached = total - cached
    if uncached and prices.input is None:
        return "price_missing_input"
    if cached and prices.cached_input is None:
        return "price_missing_cached_input"
    return uncached * _rate(prices.input) + cached * _rate(prices.cached_input)


def _output_cost(attempt: AttemptFact, prices: CategoryPrices, reasoning_billed_as_output: bool | None) -> Decimal | str:
    total, reasoning = attempt.output_tokens, attempt.reasoning_tokens
    assert total is not None
    if reasoning is not None and reasoning > total:
        return "categories_inconsistent"
    if not reasoning_billed_as_output and reasoning != 0:  # reasoning is unpriced, so any of it leaves the cost open
        return "reasoning_split_unreported"
    if total and prices.output is None:
        return "price_missing_output"
    return total * _rate(prices.output)


def price_attempt(attempt: AttemptFact, reference: Reference) -> Decimal | str:
    """The attempt's reported tokens at ``reference``'s prices, or the reason it cannot be priced."""
    if attempt.input_tokens is None or attempt.output_tokens is None:
        # Nothing reported and nothing billed (a request never sent or refused before dispatch) reprices to zero.
        return Decimal(0) if attempt.cost_usd == 0 and attempt.input_tokens is None and attempt.output_tokens is None \
            else "tokens_unreported"
    prices = reference.prices_for(attempt.input_tokens)
    input_cost = _input_cost(attempt, prices)
    if isinstance(input_cost, str):
        return input_cost
    output_cost = _output_cost(attempt, prices, reference.reasoning_billed_as_output)
    return output_cost if isinstance(output_cost, str) else input_cost + output_cost


def compare(attempts: Sequence[AttemptFact], actual: Totals, reference: Reference) -> Column:
    """One B1 column: baseline minus actual fully loaded cost, once, for the same scope as ``actual``."""
    _unique(attempts)
    baseline = Decimal(0)
    priced = 0
    unpriced: Counter[str] = Counter()
    unpriced_tokens: dict[str, int | None] = {}
    for attempt in attempts:
        result = price_attempt(attempt, reference)
        if isinstance(result, str):
            unpriced[result] += 1
            tokens = None if attempt.input_tokens is None or attempt.output_tokens is None \
                else attempt.input_tokens + attempt.output_tokens
            previous = unpriced_tokens.get(result, 0)
            unpriced_tokens[result] = None if previous is None or tokens is None else previous + tokens
        else:
            baseline += result
            priced += 1
    reasons = set()
    if reference.source.price_as_of is None:
        reasons.add("source_date_missing")
    if unpriced:
        reasons.add("unpriced_attempts")
    if not actual.definitive:
        reasons.add("actual_incomplete")
    if not attempts:
        reasons.add("no_attempts")
    savings = percent = None
    if not reasons:
        savings = baseline - actual.known_usd
        if baseline > 0:
            percent = (savings * 100 / baseline).quantize(_PERCENT_STEP)
    as_of = reference.source.price_as_of
    return Column(
        reference.id, reference.snapshot_id, None if as_of is None else as_of.isoformat(), baseline, priced,
        tuple((reason, unpriced[reason], unpriced_tokens[reason]) for reason in sorted(unpriced)),
        tuple(sorted(reasons)), savings, percent,
    )


def auto_scope(attempts: Iterable[AttemptFact], turns: Sequence[TurnFact]) -> tuple[list[AttemptFact], list[TurnFact]]:
    """The attempts and turns explicitly attributed to Auto; never inferred from a model or role."""
    auto_turns = [turn for turn in turns if turn.selection == "auto"]
    ids = {turn.turn_id for turn in auto_turns}
    return [a for a in attempts if a.turn_id in ids], auto_turns
