"""Plan 12.9: deterministic accounting fixtures for the usage report's arithmetic (B1, one subtraction; Task 1), and its
response pages and bounded route handler (Task 2)."""

from __future__ import annotations

import threading
import time
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from optimus_gateway import usage_price_snapshots
from optimus_gateway import usage_report as report
from optimus_gateway.usage_report import AttemptFact, TurnFact, auto_scope, compare, price_attempt, totals
from optimus_gateway.usage_store import ReportFacts, StoreError
from optimus_model_policy.savings_references import CategoryPrices, Reference, ReferenceSet, RuleSource, Source, Tier
from optimus_security import usage_report_contract as urc

D = Decimal


def _reference(ref_id="ref-a", *, input="1", output="4", cached="0.1", reasoning=True, as_of=date(2026, 11, 1), tiers=()):
    return Reference(
        id=ref_id, display=ref_id, unit="usd_per_million_tokens",
        prices=CategoryPrices(input=input, output=output, cached_input=cached), tiers=tiers,
        reasoning_billed_as_output=reasoning, reasoning_source=None if reasoning is None else RuleSource(url="https://example.test/billing", quote="Reasoning is output.", fetched_on=date(2026, 11, 1)),
        source=Source(url="https://example.test/p", price_as_of=as_of),
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


# --- Plan 12.9 Task 2: the response pages and the route's bounded handler --------------------------------------------

_KEY = b"k" * 32
_LEDGER = "a" * 32


def _references(count=2):
    return ReferenceSet(version=1, references=tuple(_reference(f"ref-{i}") for i in range(count)))


def _payload(attempt_id, turn, *, cost="0.002", inp=1000, out=200, cached=0, reasoning=0, stage="planning", outcome="completed"):
    return {"attempt_id": attempt_id, "turn_id": turn, "epoch_id": "e" * 32, "stage": stage, "purpose": "turn.planning",
            "outcome": outcome, "reported_cost_usd": cost, "input_tokens": inp, "output_tokens": out, "cached_tokens": cached,
            "usage": {"reasoning_tokens": reasoning}, "requested_model": "m-1", "resolved_model": "m-1", "provider": "p-1"}


def _facts(receipts=None, *, epochs=None, selections=None, ledger=_LEDGER, too_large=False, uncommitted=0, uncovered=0, gaps=0,
           unallocated=()):
    receipts = receipts if receipts is not None else [
        (_payload("a1", "t1"), False, False),
        (_payload("c1", "t1", cost="0.0001", stage="classification", inp=100, out=0), False, False),
        (_payload("f1", "t2", cost="0.5"), False, False),
    ]
    return ReportFacts(ledger, datetime(2026, 11, 1, 12, tzinfo=UTC), tuple(receipts),
                       epochs if epochs is not None else {"t1": ("complete",), "t2": ("complete",)},
                       selections if selections is not None else {"t1": ("auto",), "t2": ("fixed",)}, too_large,
                       uncommitted_streams=uncommitted, uncovered_streams=uncovered, stream_gaps=gaps,
                       unallocated_costs=tuple(unallocated))


def _request(**changes):
    fields = {"session_id": "s", "turn_id": None, "reference_ids": None, "page_size": 100, "cursor": None, "expected_turns": 2,
              "frontier": (("f" * 32, 9),)}
    return urc.ReportRequest(**{**fields, **changes})


def _page(facts, request, references, principal="p"):
    position = report.open_position(request, references, key=_KEY, principal=principal)
    return urc.validate_report(report.report_body(facts, request, references, key=_KEY, principal=principal, position=position))


def test_a_page_counts_each_canonical_receipt_once_and_compares_the_auto_scope_only():
    body = _page(_facts(), _request(), _references())

    assert body["session"] == {"known_usd": "0.5021", "attempts": 3, "unknown_attempts": 0, "conflicts": 0, "late": 0,
                               "turns": 2, "definitive": True, "reasons": []}
    assert body["auto"]["known_usd"] == "0.0021" and body["auto"]["attempts"] == 2  # the fixed turn is not compared
    assert body["attribution"] == {"auto_turns": 1, "fixed_turns": 1, "unattributed_turns": 0}
    # a1: 1000 x 1/M + 200 x 4/M = 0.0018; c1: 100 x 1/M = 0.0001; savings 0.0019 - 0.0021
    assert [c["savings_usd"] for c in body["comparisons"]["columns"]] == ["-0.0002", "-0.0002"]
    assert [r["attempt_id"] for r in body["detail"]] == ["a1", "c1", "f1"] and body["next_cursor"] is None
    assert body["b2"] == body["b3"] == {"state": "unavailable"}


def test_pages_walk_the_reference_groups_then_the_detail_rows_with_whole_scope_totals():
    references = _references(5)
    receipts = [(_payload(f"a{n}", "t1"), False, False) for n in reversed(range(5))]  # the database collation's order
    facts = _facts(receipts, epochs={"t1": ("complete",)}, selections={"t1": ("auto",)})
    pages, cursor = [], None
    while True:
        pages.append(_page(facts, _request(page_size=2, cursor=cursor, expected_turns=1), references))
        cursor = pages[-1]["next_cursor"]
        if cursor is None:
            break

    assert [[c["reference_id"] for c in p["comparisons"]["columns"]] for p in pages] == [
        ["ref-0", "ref-1", "ref-2"], ["ref-3", "ref-4"], [], []]
    assert [[r["attempt_id"] for r in p["detail"]] for p in pages] == [[], ["a0", "a1"], ["a2", "a3"], ["a4"]]
    assert len({p["revision"] for p in pages}) == 1 and all(p["session"] == pages[0]["session"] for p in pages)


@pytest.mark.parametrize("change", [
    lambda: (_facts([(_payload("late", "t1"), True, False), *_facts().receipts]), {}),  # a receipt arrived
    lambda: (_facts(epochs={"t1": ("incomplete",), "t2": ("complete",)}), {}),  # coverage was downgraded
    lambda: (_facts(ledger="b" * 32), {}),  # another ledger answers
    lambda: (_facts(), {"session_id": "other"}),  # the cursor is not this request's
    lambda: (_facts(), {"reference_ids": ("ref-0",)}),
    lambda: (_facts(), {"page_size": 1}),
])
def test_a_cursor_answers_changed_for_different_facts_ledger_or_request(change):
    references = _references(5)
    first = _page(_facts(), _request(), references)
    facts, request_changes = change()

    with pytest.raises(report.Changed):
        _page(facts, _request(cursor=first["next_cursor"], **request_changes), references)


@pytest.mark.parametrize("tamper", [
    lambda cursor: cursor[:-1] + ("0" if cursor[-1] != "0" else "1"),
    lambda cursor: urc.seal_cursor(b"x" * 32, {"scope": {}}),  # sealed under another key
])
def test_an_altered_cursor_answers_changed(tamper):
    references = _references(5)
    cursor = _page(_facts(), _request(), references)["next_cursor"]

    with pytest.raises(report.Changed):
        _page(_facts(), _request(cursor=tamper(cursor)), references)


def test_another_principal_cannot_continue_a_cursor():
    references = _references(5)
    cursor = _page(_facts(), _request(), references)["next_cursor"]

    with pytest.raises(report.Changed):
        _page(_facts(), _request(cursor=cursor), references, principal="someone-else")


def test_a_scope_over_the_bounds_reports_unavailable_totals_and_nothing_truncated():
    body = _page(_facts((), epochs={}, selections={}, too_large=True), _request(), _references())

    assert body["session"]["known_usd"] is None and body["session"]["reasons"] == ["scope_too_large"]
    assert body["comparisons"]["columns"] == [] and body["detail"] == []


def test_unattributed_or_uncaptured_turns_keep_the_auto_comparison_incomplete():
    unattributed = _page(_facts(selections={"t1": ("auto",), "t2": ("auto", "fixed")}), _request(), _references())
    uncaptured = _page(_facts(), _request(expected_turns=3), _references())

    assert unattributed["attribution"]["unattributed_turns"] == 1  # contradictory contexts are not evidence
    for body in (unattributed, uncaptured):
        assert "attribution_unavailable" in body["auto"]["reasons"]
        assert all(c["savings_usd"] is None and "actual_incomplete" in c["reasons"] for c in body["comparisons"]["columns"])
    assert "turn_not_captured" in uncaptured["session"]["reasons"]


def test_without_the_hosts_turn_count_no_scope_is_definitive():
    body = _page(_facts(), _request(expected_turns=None), _references())

    assert body["session"]["reasons"] == body["auto"]["reasons"] == ["expected_turns_unknown"]  # nothing else is missing
    assert all(c["savings_usd"] is None for c in body["comparisons"]["columns"])


def test_an_unknown_reference_is_refused():
    with pytest.raises(urc.ContractError):
        report.report_body(_facts(), _request(reference_ids=("ref-9",)), _references(), key=_KEY, principal="p")


class _Store:
    def __init__(self, result=None, *, gate=None):
        self.result, self.gate, self.calls = result, gate, 0

    def report_facts(self, session_id, turn_id, *, frontier, deadline, max_attempts, max_turns):
        self.calls += 1
        if self.gate is not None:
            self.gate.wait(10)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _handle(store, body=None):
    raw = urc.build_request(_request()) if body is None else body
    return report.handle_usage_report_request(raw_body=raw, config=SimpleNamespace(usage_store=store, shared_secret="s3"))


@pytest.fixture
def synthetic_references(monkeypatch):
    monkeypatch.setattr(usage_price_snapshots, "configured_references", lambda: _references())


def test_capabilities_are_answered_without_any_ledger():
    status, body = _handle(None, urc.build_request(None))

    assert status == 200 and urc.FEATURE_REPORT_CONTEXT in urc.validate_capabilities(body)


@pytest.mark.parametrize(("store", "code"), [
    (None, "ACCOUNTING_NOT_CONFIGURED"),
    (_Store(StoreError("unavailable")), "LEDGER_UNAVAILABLE"),
    (_Store(StoreError("timeout")), "REPORT_TIMEOUT"),
])
def test_ledger_states_answer_stable_codes(synthetic_references, store, code):
    assert _handle(store) == urc.error_body(code)


@pytest.mark.parametrize(("body", "code"), [
    (b"{", "REQUEST_INVALID"),
    (b'{"schema_version": 1, "operation": "report", "session_id": "s", "sql": "SELECT 1"}', "REQUEST_INVALID"),
    (b" " * (urc.MAX_REQUEST_BYTES + 1), "REQUEST_TOO_LARGE"),
])
def test_requests_outside_the_contract_never_reach_the_ledger(synthetic_references, body, code):
    store = _Store(_facts())

    assert _handle(store, body) == urc.error_body(code) and store.calls == 0


def test_a_page_is_served_and_an_altered_cursor_never_reaches_the_ledger(synthetic_references):
    store = _Store(_facts())
    status, body = _handle(store)
    altered = urc.build_request(_request(cursor=urc.seal_cursor(b"x" * 32, {"scope": {}})))

    assert status == 200 and urc.validate_report(body)["session"]["attempts"] == 3
    assert _handle(store, altered) == urc.error_body("REPORT_CHANGED") and store.calls == 1


def test_an_expired_worker_keeps_its_slot_until_it_exits_and_further_requests_are_busy(synthetic_references, monkeypatch):
    monkeypatch.setattr(report, "REPORT_SECONDS", 0.05)
    gate = threading.Event()
    slow = _Store(_facts(), gate=gate)
    try:
        assert _handle(slow) == urc.error_body("REPORT_TIMEOUT")
        assert _handle(slow) == urc.error_body("REPORT_TIMEOUT")
        assert _handle(_Store(_facts())) == urc.error_body("REPORT_BUSY")  # both slots are held by workers still running
    finally:
        gate.set()
    deadline = time.monotonic() + 5
    while (served := _handle(_Store(_facts())))[0] != 200 and time.monotonic() < deadline:
        time.sleep(0.01)  # the released workers exit and return their slots
    assert served[0] == 200


# --- Plan 12.9 Checkpoint A (round 93) ---------------------------------------------------------------------------


@pytest.mark.parametrize(("outcome", "expected"), [
    ("completed", "tokens_unreported"),  # free, but its reference-token cost is unknown
    ("unattributed", "tokens_unreported"),
    ("not_sent", D(0)),  # never executed
    ("rejected", D(0)),
])
def test_only_a_request_never_executed_reprices_to_zero_without_tokens(outcome, expected):
    attempt = _attempt(cost="0", outcome=outcome, inp=None, out=None, cached=None, reasoning=None)

    assert price_attempt(attempt, _reference()) == expected


def test_a_reference_without_a_source_is_unavailable_and_its_neighbour_is_not():
    bare = Reference(id="ref-bare", display="bare", unit="usd_per_million_tokens",
                     prices=CategoryPrices(input="1", output="4", cached_input="0.1"), reasoning_billed_as_output=None,
                     source=Source(price_as_of=date(2026, 11, 1)))
    attempts = [_attempt()]
    actual = totals(attempts, _COMPLETE)

    assert compare(attempts, actual, bare).reasons == ("source_missing",)
    assert compare(attempts, actual, _reference()).complete
    body = _page(_facts(), _request(), ReferenceSet(version=1, references=(_reference(), bare)))
    assert [c["source"] for c in body["comparisons"]["columns"]] == ["https://example.test/p", None]


@pytest.mark.parametrize(("facts", "request_changes", "reason"), [
    (lambda: _facts(uncommitted=None), {"frontier": None}, "frontier_unknown"),
    (lambda: _facts(uncommitted=1), {}, "delivery_pending"),  # a receipt of a recorded turn has not arrived
    (lambda: _facts(gaps=1), {}, "stream_gap"),
    (lambda: _facts(uncovered=1), {}, "frontier_unknown"),  # a host stream behind the facts has no frontier
])
def test_delivery_that_is_not_proven_withholds_every_definitive_total(facts, request_changes, reason):
    body = _page(facts(), _request(**request_changes), _references())

    assert reason in body["session"]["reasons"] and reason in body["auto"]["reasons"]
    assert all(c["savings_usd"] is None for c in body["comparisons"]["columns"])


def test_a_committed_frontier_changes_the_revision():
    pending = _page(_facts(uncommitted=1), _request(), _references(5))

    with pytest.raises(report.Changed):
        _page(_facts(uncommitted=0), _request(cursor=pending["next_cursor"]), _references(5))


def test_any_number_of_maximum_length_references_continues_by_cursor():
    references = ReferenceSet(version=1, references=tuple(_reference(f"r{n:02d}" + "x" * 61) for n in range(urc.MAX_REFERENCE_IDS)))
    pages, cursor = [], None
    while True:
        pages.append(_page(_facts(), _request(cursor=cursor), references))
        cursor = pages[-1]["next_cursor"]
        if cursor is None:
            break

    assert sum(len(p["comparisons"]["columns"]) for p in pages) == urc.MAX_REFERENCE_IDS
    assert max(len(p["next_cursor"] or "") for p in pages) < 1024


def test_detail_pages_by_serialized_bytes_and_every_page_fits_the_response_bound():
    wide = "\u2603" * 512  # six bytes a character once escaped; five such fields per row, as the capture contract allows
    turn = "t" + wide[1:]
    ids = [f"a{n:03d}" + wide[4:] for n in range(100)]
    receipts = [({**_payload(attempt_id, turn), "requested_model": wide, "resolved_model": wide, "provider": wide}, False, False)
                for attempt_id in ids]
    facts = _facts(receipts, epochs={turn: ("complete",)}, selections={turn: ("auto",)})
    pages, cursor = [], None
    while True:
        pages.append(_page(facts, _request(cursor=cursor, expected_turns=1, reference_ids=("ref-0",)), _references()))
        cursor = pages[-1]["next_cursor"]
        if cursor is None:
            break

    assert len(pages) > 1 and all(report.wire_size(p) <= urc.MAX_RESPONSE_BYTES for p in pages)
    assert [row["attempt_id"] for p in pages for row in p["detail"]] == ids


def test_the_deadline_bounds_the_arithmetic_too(synthetic_references, monkeypatch):
    monkeypatch.setattr(report, "REPORT_SECONDS", 0.2)
    real = report.report_body
    monkeypatch.setattr(report, "report_body", lambda *a, **k: (time.sleep(0.5), real(*a, **k))[1])

    assert _handle(_Store(_facts())) == urc.error_body("REPORT_TIMEOUT")


def test_a_benchmark_without_provenance_is_omitted_and_the_report_stays_valid():
    unsourced = ReferenceSet(version=1, references=(_reference(),),
                             benchmark={"text": "t", "limitations": "l", "source": {"price_as_of": None}})

    body = _page(_facts(), _request(), unsourced)  # _page validates the whole response

    assert body["benchmark"] is None and body["comparisons"]["columns"][0]["complete"]


# --- Plan 12.9 Task 3: unallocated overhead -------------------------------------------------------------------------


def test_session_less_overhead_is_shown_apart_and_never_added_to_the_session():
    plain = _page(_facts(), _request(), _references())
    with_overhead = _page(_facts(unallocated=("0.01", None)), _request(), _references())

    assert with_overhead["unallocated"] == {"known_usd": "0.01", "attempts": 2, "unknown_attempts": 1}
    assert plain["unallocated"] == {"known_usd": "0", "attempts": 0, "unknown_attempts": 0}
    assert with_overhead["session"] == plain["session"] and with_overhead["auto"] == plain["auto"]
    assert with_overhead["revision"] != plain["revision"]
