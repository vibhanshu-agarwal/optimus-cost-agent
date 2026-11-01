"""The usage report (Plan 12.9; ADR-034): measured totals with coverage, B1 comparison columns, the paginated
response and the Gateway route's bounded handler.

The arithmetic is pure functions over canonical ledger facts: one fact per canonical attempt (aliases and replays are the reader's to
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

import dataclasses
import hashlib
import hmac
import json
import secrets
import threading
import time
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from optimus_model_policy.savings_references import TOKENS_PER_PRICE_UNIT, CategoryPrices, Reference, ReferenceSet
from optimus_security import usage_report_contract as urc

if TYPE_CHECKING:
    from optimus_gateway.models import GatewayServiceConfig
    from optimus_gateway.usage_store import ReportFacts

_PERCENT_STEP = Decimal("0.1")
_NOT_EXECUTED = frozenset({"not_sent", "rejected"})  # the capture contract requires their cost to be exactly 0


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
        raise ValueError("an attempt appears more than once; the reader must fold aliases and replays")


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
        # Only a request that was never executed (not sent, or refused before dispatch) reprices to zero; a completed
        # call that reported no tokens is unpriced even when it was free.
        return Decimal(0) if attempt.outcome in _NOT_EXECUTED else "tokens_unreported"
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
    if reference.source.locator is None:
        reasons.add("source_missing")
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


# --- The response ----------------------------------------------------------------------------------
# Pages walk the reference columns in groups of `REFERENCE_GROUP`, then the detail rows; every page carries the whole
# scope's totals. A cursor seals the request it continues and the revision it read; anything different is CHANGED.


class Changed(Exception):
    """The cursor is not one this Gateway sealed for this request, or the facts it read have changed."""


_STATE_ORDER = ("incomplete", None, "open", "complete")  # a turn with several epochs takes its least complete state


def _turn(turn_id: str, states: Sequence[str | None], selections: Sequence[str]) -> TurnFact:
    state = next(s for s in _STATE_ORDER if s in states) if states else None
    return TurnFact(turn_id, state, selections[0] if len(selections) == 1 else None)  # contradictory contexts: unknown


def _attempt(payload: Mapping[str, Any], late: bool, conflict: bool) -> AttemptFact:
    cost, usage = payload["reported_cost_usd"], payload["usage"] or {}
    return AttemptFact(payload["attempt_id"], payload["turn_id"], payload["stage"], payload["outcome"],
                       None if cost is None else Decimal(cost), payload["input_tokens"], payload["output_tokens"],
                       payload["cached_tokens"], usage.get("reasoning_tokens"), late=late, conflict=conflict)


def _money(value: Decimal | None) -> str | None:
    return None if value is None else format(value.normalize(), "f")


def _with(t: Totals, reasons: Sequence[str]) -> Totals:
    return dataclasses.replace(t, reasons=tuple(sorted({*t.reasons, *reasons})))


def _totals_body(t: Totals) -> dict[str, Any]:
    return {"known_usd": _money(t.known_usd), "attempts": t.attempts, "unknown_attempts": t.unknown_attempts,
            "conflicts": t.conflicts, "late": t.late, "turns": t.turns, "definitive": t.definitive, "reasons": list(t.reasons)}


def _column_body(column: Column, reference: Reference) -> dict[str, Any]:
    return {
        "reference_id": column.reference_id, "display": reference.display, "snapshot_id": column.snapshot_id,
        "source": reference.source.locator, "price_as_of": column.price_as_of,
        "baseline_known_usd": _money(column.baseline_known_usd), "priced_attempts": column.priced_attempts,
        "unpriced": [{"reason": r, "attempts": n, "tokens": tokens} for r, n, tokens in column.unpriced],
        "complete": column.complete, "reasons": list(column.reasons), "savings_usd": _money(column.savings_usd),
        "savings_percent": _money(column.savings_percent),
    }


def _row(payload: Mapping[str, Any], fact: AttemptFact, selection: str | None) -> dict[str, Any]:
    return {
        "turn_id": fact.turn_id, "attempt_id": fact.attempt_id, "stage": fact.stage, "purpose": payload["purpose"],
        "outcome": fact.outcome, "cost_usd": _money(fact.cost_usd), "selection": selection,
        "requested_model": payload["requested_model"], "resolved_model": payload["resolved_model"],
        "provider": payload["provider"], "input_tokens": fact.input_tokens, "output_tokens": fact.output_tokens,
        "cached_tokens": fact.cached_tokens, "reasoning_tokens": fact.reasoning_tokens, "late": fact.late,
        "conflict": fact.conflict,
    }


def _selected(references: ReferenceSet, ids: Sequence[str] | None) -> list[Reference]:
    by_id = {reference.id: reference for reference in references.references}
    if ids is None:
        return list(references.references)
    if any(i not in by_id for i in ids):
        raise urc.ContractError("reference")
    return [by_id[i] for i in ids]


def _digest(value: object) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return "hex:" + hashlib.sha256(text.encode("ascii")).hexdigest()


def cursor_scope(request: urc.ReportRequest, selected: Sequence[Reference], principal: str) -> str:
    """A bounded digest of everything a continuation must repeat: any number of references fits in a cursor."""
    return _digest([principal, request.session_id, request.turn_id, [r.id for r in selected], request.page_size,
                    request.expected_turns, None if request.frontier is None else [list(f) for f in request.frontier]])


def open_position(request: urc.ReportRequest, references: ReferenceSet, *, key: bytes, principal: str) -> dict[str, Any] | None:
    """The sealed position a cursor continues (None for a first page), checked against this request before any read."""
    if request.cursor is None:
        return None
    try:
        sealed = urc.open_cursor(key, request.cursor)
    except urc.ContractError:
        raise Changed from None
    if sealed.get("scope") != cursor_scope(request, _selected(references, request.reference_ids), principal):
        raise Changed
    return sealed


def report_body(facts: ReportFacts, request: urc.ReportRequest, references: ReferenceSet, *, key: bytes, principal: str,
                position: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """One response page for ``facts``; `Changed` when ``position`` was sealed for another ledger or revision."""
    selected = _selected(references, request.reference_ids)
    scope = cursor_scope(request, selected, principal)
    body: dict[str, Any] = {
        "schema_version": urc.SCHEMA_VERSION, "status": "ok", "ledger_instance": facts.ledger_instance,
        "as_of": facts.as_of.isoformat(), "scope": {"session_id": request.session_id, "turn_id": request.turn_id},
        "b2": {"state": "unavailable"}, "b3": {"state": "unavailable"},
        # B4 needs its provenance: a benchmark without a source locator is not shown at all.
        "benchmark": None if references.benchmark is None or references.benchmark.source.locator is None else {
            "text": references.benchmark.text, "limitations": references.benchmark.limitations,
            "source": references.benchmark.source.locator,
            "as_of": None if references.benchmark.source.price_as_of is None else references.benchmark.source.price_as_of.isoformat(),
        },
    }
    if facts.too_large:
        unavailable = {"known_usd": None, "attempts": 0, "unknown_attempts": 0, "conflicts": 0, "late": 0, "turns": 0,
                       "definitive": False, "reasons": ["scope_too_large"]}
        revision = _digest([facts.ledger_instance, "scope_too_large", scope, references.digest])
        if position is not None and position.get("revision") != revision:
            raise Changed
        return {**body, "revision": revision, "session": unavailable, "auto": unavailable,
                "attribution": {"auto_turns": 0, "fixed_turns": 0, "unattributed_turns": 0},
                "comparisons": {"offset": 0, "total": len(selected), "columns": []}, "detail": [], "next_cursor": None}
    attempts = [_attempt(*receipt) for receipt in facts.receipts]
    turns = [_turn(turn_id, facts.epochs[turn_id], facts.selections.get(turn_id, ())) for turn_id in sorted(facts.epochs)]
    revision = _digest([facts.ledger_instance, scope, references.digest, [dataclasses.astuple(a) for a in attempts],
                        [dataclasses.astuple(t) for t in turns], facts.uncommitted_streams, facts.uncovered_streams,
                        facts.stream_gaps])
    if position is not None and (position.get("ledger_instance"), position.get("revision")) != (facts.ledger_instance, revision):
        raise Changed
    unattributed = sum(turn.selection is None for turn in turns)
    uncaptured = max(0, (request.expected_turns or 0) - len(turns))  # a turn the ledger never received may be Auto
    # Delivery: without the host's turn count and capture frontier no scope is shown complete, since a turn or a receipt
    # may not have reached the ledger; nor while a frontier is uncommitted or a stream of the scope has a gap.
    delivery = ["expected_turns_unknown"] if request.expected_turns is None else []
    delivery += ["frontier_unknown"] if facts.uncommitted_streams is None or facts.uncovered_streams else []
    delivery += ["delivery_pending"] if facts.uncommitted_streams else []
    delivery += ["stream_gap"] if facts.stream_gaps else []
    session = _with(totals(attempts, turns, expected_turns=request.expected_turns), delivery)
    auto_attempts, auto_turns = auto_scope(attempts, turns)
    auto = _with(totals(auto_attempts, auto_turns, unattributed_turns=unattributed + uncaptured), delivery)

    offset, after = (0, None) if position is None else (position["offset"], position["after"])
    group = selected[offset:offset + urc.REFERENCE_GROUP]
    selection = {turn.turn_id: turn.selection for turn in turns}
    page: dict[str, Any] = {
        **body, "revision": revision, "session": _totals_body(session), "auto": _totals_body(auto),
        "attribution": {"auto_turns": len(auto_turns), "fixed_turns": sum(t.selection == "fixed" for t in turns),
                        "unattributed_turns": unattributed},
        "comparisons": {"offset": offset, "total": len(selected),
                        "columns": [_column_body(compare(auto_attempts, auto, r), r) for r in group]},
        "detail": [], "next_cursor": _LONGEST_CURSOR,
    }
    detail: list[dict[str, Any]] = page["detail"]
    following: tuple[int, int | None] | None = None
    if offset + urc.REFERENCE_GROUP < len(selected):
        following = (offset + urc.REFERENCE_GROUP, None)
    else:
        ordered = sorted(zip((receipt[0] for receipt in facts.receipts), attempts, strict=True),
                         key=lambda pair: (pair[1].turn_id, pair[1].attempt_id))  # Python's order, not the database collation's
        # ``after`` counts the rows already shown: the revision binds exactly these facts in this order, so an offset is
        # as safe as a key and stays bounded however long the identifiers are.
        rows = ordered[after or 0:]
        # Rows are bounded by count and by the page's own serialized size, measured with the longest cursor (escaped
        # text can take six bytes a character); a page always carries at least one row.
        room = urc.MAX_RESPONSE_BYTES - wire_size(page)
        for payload, fact in rows[:request.page_size]:
            row = _row(payload, fact, selection.get(fact.turn_id))
            room -= wire_size(row) + 1
            if detail and room < 0:
                break
            detail.append(row)
        if len(detail) < len(rows):
            following = (len(selected), (after or 0) + len(detail))
    page["next_cursor"] = None if following is None else urc.seal_cursor(key, {
        "scope": scope, "ledger_instance": facts.ledger_instance, "revision": revision, "offset": following[0], "after": following[1],
    })
    return page


_LONGEST_CURSOR = "x" * (2048 + 1 + 64)  # `usage_report_contract._CURSOR`'s bound, held in place while a page is measured


def wire_size(value: object) -> int:
    """Bytes as `server._send_json` writes them."""
    return len(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))


# --- The Gateway route (`server.py` authenticates and frames before calling it) ---------------------

_CURSOR_KEY = secrets.token_bytes(32)  # per process: a restarted Gateway answers every earlier cursor REPORT_CHANGED
_WORKERS = threading.BoundedSemaphore(2)  # outstanding database reads (agent-selected)
REPORT_SECONDS = 5.0  # one report's whole deadline: its database read, the arithmetic and serialization


def _principal(shared_secret: str) -> str:
    return hmac.new(_CURSOR_KEY, shared_secret.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def handle_usage_report_request(*, raw_body: bytes, config: GatewayServiceConfig) -> tuple[int, dict[str, Any]]:
    """`POST /v1/observability/usage-report` after authentication: capabilities without the database, or one report
    page read by a bounded worker. An expired worker keeps its slot until it exits and its late result is dropped."""
    from optimus_gateway.usage_price_snapshots import configured_references
    from optimus_gateway.usage_store import StoreError

    try:
        request = urc.parse_request(raw_body)
    except urc.ContractError as exc:
        return urc.error_body("REQUEST_TOO_LARGE" if exc.code == "too_large" else "REQUEST_INVALID")
    if request is None:
        return 200, urc.capabilities_body()
    store = config.usage_store
    if store is None:
        return urc.error_body("ACCOUNTING_NOT_CONFIGURED")
    references, principal = configured_references(), _principal(config.shared_secret)
    try:
        position = open_position(request, references, key=_CURSOR_KEY, principal=principal)
    except Changed:
        return urc.error_body("REPORT_CHANGED")
    except urc.ContractError:
        return urc.error_body("REQUEST_INVALID")
    if not _WORKERS.acquire(blocking=False):
        return urc.error_body("REPORT_BUSY")
    deadline = time.monotonic() + REPORT_SECONDS
    outcome: list[tuple[int, dict[str, Any]]] = []

    def report() -> None:
        try:
            facts = store.report_facts(request.session_id, request.turn_id, frontier=request.frontier, deadline=deadline,
                                       max_attempts=urc.MAX_ATTEMPTS, max_turns=urc.MAX_TURNS)
            outcome.append((200, report_body(facts, request, references, key=_CURSOR_KEY, principal=principal,
                                             position=position)))
        except StoreError as exc:
            outcome.append(urc.error_body("REPORT_TIMEOUT" if exc.code == "timeout" else "LEDGER_UNAVAILABLE"))
        except Changed:
            outcome.append(urc.error_body("REPORT_CHANGED"))
        except urc.ContractError:
            outcome.append(urc.error_body("REQUEST_INVALID"))
        finally:
            _WORKERS.release()

    worker = threading.Thread(target=report, name="usage-report", daemon=True)
    worker.start()
    worker.join(max(0.0, deadline - time.monotonic()))
    return outcome[0] if outcome and time.monotonic() <= deadline else urc.error_body("REPORT_TIMEOUT")
