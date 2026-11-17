"""Plan 12.11 Task 3: the per-session extractor with a scripted summarizer, the real settlement, and the store adapter on the
Gateway's handler over the in-memory stand-in. A controlled upstream proves plumbing, never extraction quality."""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from optimus.context import memory_extraction as mx
from optimus.context.maintenance import SummarizerAttempt, SummarizerResponse
from optimus.usage.turn_settlement import StageReceipt, TurnSettlement
from tests.unit.context.test_authored_memory import _adapter
from tests.unit.optimus_gateway.test_memory_store_commit import store

_AT = datetime(2026, 11, 17, tzinfo=UTC)
_TEXT = "From now on, new tests should use plain pytest asserts."
_GOOD = json.dumps({"candidates": [{"speech_act": "preference", "kind": "preference", "title": "test style",
                                    "statement": "New tests use plain pytest asserts.", "spans": [{"block": "b-1", "start": 0, "end": 54}]}]})
_LESSON = json.dumps({"candidates": [{"speech_act": "assertion", "kind": "lesson", "title": "fake clock",
                                      "statement": "The scheduler test needs a fake clock.", "evidence": ["ev-1"]}]})


class _Upstream:
    """A scripted summarizer: each call returns the next reply, after an optional pause, and records what it was asked."""

    def __init__(self, *replies: SummarizerResponse, pause: threading.Event | None = None) -> None:
        self.replies, self.pause, self.calls = list(replies), pause, []

    def bind(self, turn_id: str) -> Any:
        def call(*, prompt: str, max_output_tokens: int, purpose: str) -> SummarizerResponse:
            self.calls.append((turn_id, purpose, max_output_tokens, prompt))
            if self.pause is not None:
                self.pause.wait(5)
            return self.replies.pop(0)
        return call


def _completed(text: str, n: int = 1) -> SummarizerResponse:
    return SummarizerResponse(text=text, finish_status="stop", attempts=(SummarizerAttempt(f"a-{n}", f"gw-{n}", "completed", Decimal("0.001")),))


def _harness(upstream: _Upstream, **kwargs: Any) -> tuple[mx.MemoryExtractor, TurnSettlement, list[mx.Outcome], list[StageReceipt]]:
    service, _server, _ = store()
    settlement = TurnSettlement(session_id="s")
    outcomes: list[mx.Outcome] = []
    receipts: list[StageReceipt] = []

    def record(turn_id: str, purpose: str, attempt: SummarizerAttempt, _finish: str | None) -> None:
        receipt = StageReceipt(session_id="s", turn_id=turn_id, stage="summarization", attempt_id=attempt.attempt_id,
                               gateway_request_id=attempt.gateway_request_id, outcome=attempt.outcome, reported_cost_usd=attempt.cost_usd,
                               recorded_at=_AT, purpose=purpose)
        receipts.append(receipt)
        settlement.record_attempt(receipt)

    extractor = mx.MemoryExtractor(store=_adapter(service), settlement=settlement, bind=upstream.bind, record=record,
                                   sanitize=lambda value: value, report=outcomes.append, **kwargs)
    return extractor, settlement, outcomes, receipts


def _turn(n: int = 1, text: str = _TEXT, work: mx.CompletedWork | None = None) -> mx.TurnInput:
    return mx.TurnInput(f"s:{n}", "s-1", (mx.UserBlock("b-1", text),), work, (), True)


def _running(upstream: _Upstream) -> None:
    deadline = time.monotonic() + 5
    while not upstream.calls:
        assert time.monotonic() < deadline
        time.sleep(0.01)


def _until(outcomes: list[mx.Outcome], count: int) -> None:
    deadline = time.monotonic() + 5
    while len(outcomes) < count:
        assert time.monotonic() < deadline
        time.sleep(0.01)


def test_a_durable_statement_is_admitted_after_the_answer_and_its_turn_settles_once_the_job_has() -> None:
    gate = threading.Event()
    upstream = _Upstream(_completed(_GOOD), pause=gate)
    extractor, settlement, outcomes, receipts = _harness(upstream)
    user, agent = extractor.submit(_turn())
    assert (user.call, agent.call) == (True, False)
    settlement.finalize_turn("s:1")  # the answer was delivered; the job is still out
    assert settlement.settle_turn("s:1").pending_invocations == 1
    gate.set()
    _until(outcomes, 1)
    extractor.close()
    (outcome,) = outcomes
    assert outcome.incomplete is None and [notice.saved for notice in outcome.notices] == [True]
    assert [(r.purpose, r.outcome) for r in receipts] == [("memory.extract_user", "completed")]
    summary = settlement.settle_turn("s:1")
    assert summary.complete and summary.known_subtotal_usd == Decimal("0.001")
    (_turn_id, purpose, cap, prompt) = upstream.calls[0]
    assert (purpose, cap) == ("memory.extract_user", 512) and '<block id="b-1">' in prompt


def test_an_optional_agent_lesson_is_extracted_only_from_new_evidence() -> None:
    extractor, settlement, outcomes, _receipts = _harness(_Upstream(_completed(_LESSON)))
    work = mx.CompletedWork("fixed the timer", (mx.Evidence("ev-1", "verification"),))
    user, agent = extractor.submit(_turn(text="Fix the flaky timing assertion in test_scheduler.", work=work))
    assert (user.reason, agent.call) == ("task_request", True)
    _until(outcomes, 1)
    extractor.close()
    assert [notice.saved for notice in outcomes[0].notices] == [True] and settlement.settle_turn("s:1").complete


def test_a_failed_or_uncertain_attempt_settles_as_it_is_and_admits_nothing() -> None:
    uncertain = SummarizerResponse(text=None, finish_status=None, attempts=(SummarizerAttempt("a-1", None, "uncertain", None),))
    extractor, settlement, outcomes, receipts = _harness(_Upstream(uncertain, _completed("not json", 2)))
    extractor.submit(_turn(1))
    _until(outcomes, 1)
    extractor.submit(_turn(2, text="We always tag releases with a v prefix."))
    _until(outcomes, 2)
    extractor.close()
    assert [outcome.incomplete for outcome in outcomes] == ["empty_reply", "malformed_reply"]
    assert all(not outcome.notices for outcome in outcomes) and len(receipts) == 2
    assert settlement.settle_turn("s:1").unknown_attempt_ids == ("a-1",)  # unknown cost is not zero
    assert settlement.settle_turn("s:2").complete


def test_a_full_queue_skips_the_job_and_never_leaves_its_turn_pending() -> None:
    gate = threading.Event()
    upstream = _Upstream(*[_completed(_GOOD, n) for n in range(4)], pause=gate)
    extractor, settlement, outcomes, _receipts = _harness(upstream, workers=1, depth=1)
    extractor.submit(_turn(0, text="We always use tool number 0 here."))
    _running(upstream)  # the one worker is busy with it
    for n in (1, 2):
        extractor.submit(_turn(n, text=f"We always use tool number {n} here."))
    skipped = [outcome for outcome in outcomes if outcome.skipped]
    assert [outcome.skipped for outcome in skipped] == ["queue_full"] and settlement.settle_turn(skipped[0].turn_id).pending_invocations == 0
    gate.set()
    extractor.close()


def test_closing_abandons_queued_jobs_and_their_turns_settle() -> None:
    gate = threading.Event()
    upstream = _Upstream(*[_completed(_GOOD, n) for n in range(3)], pause=gate)
    extractor, settlement, outcomes, _receipts = _harness(upstream, workers=1, depth=2)
    extractor.submit(_turn(0, text="We always deploy region 0 first."))
    _running(upstream)
    for n in (1, 2):
        extractor.submit(_turn(n, text=f"We always deploy region {n} first."))
    closer = threading.Thread(target=extractor.close)
    closer.start()
    time.sleep(0.05)
    gate.set()
    closer.join(5)
    assert sorted(outcome.skipped or "ran" for outcome in outcomes) == ["closed", "closed", "ran"]
    assert all(settlement.settle_turn(f"s:{n}").pending_invocations == 0 for n in range(3))


def test_a_skipped_turn_takes_no_invocation_and_makes_no_call() -> None:
    upstream = _Upstream()
    extractor, settlement, outcomes, _receipts = _harness(upstream)
    assert extractor.submit(_turn(text="carry on")) == (mx.Decision(False, "acknowledgement_or_status"), mx.Decision(False, "no_completed_work"))
    extractor.close()
    assert upstream.calls == [] and outcomes == [] and settlement.settle_turn("s:1").pending_invocations == 0


def test_the_same_words_in_two_scopes_are_two_items_never_a_conflict() -> None:
    extractor, _settlement, outcomes, _receipts = _harness(_Upstream(_completed(_GOOD, 1), _completed(_GOOD, 2)))
    for n, scope in ((1, "s-1"), (2, "s-2")):  # queued directly: one session's own dedupe would skip the repeated text
        extractor._enqueue(mx.USER_PURPOSE, mx.TurnInput(f"s:{n}", scope, (mx.UserBlock("b-1", _TEXT),), None, (), True))
        _until(outcomes, n)
    extractor.close()
    assert [len(outcome.notices) for outcome in outcomes] == [1, 1] and not any(outcome.refusals for outcome in outcomes)
    assert outcomes[0].notices[0].item != outcomes[1].notices[0].item


class _SlowLease:
    """The adapter, with time spent inside each lease, so two jobs of one session overlap there."""

    def __init__(self, inner: Any) -> None:
        self.inner, self.project = inner, inner.project

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def lease(self) -> Any:
        import contextlib

        @contextlib.contextmanager
        def held() -> Any:
            with self.inner.lease() as token:
                time.sleep(0.2)
                yield token
        return held()


def test_two_jobs_of_one_session_never_fence_each_other_out() -> None:
    """Fable CP2 M4: one session commits under one lease at a time."""
    upstream = _Upstream(_completed(_GOOD, 1), _completed(_LESSON, 2))
    extractor, _settlement, outcomes, _receipts = _harness(upstream)
    extractor._store = _SlowLease(extractor._store)
    work = mx.CompletedWork("done", (mx.Evidence("ev-1", "verification"),))
    extractor.submit(_turn(text=_TEXT, work=work))
    _until(outcomes, 2)
    extractor.close()
    assert sorted(len(outcome.notices) for outcome in outcomes) == [1, 1] and not any(outcome.refusals for outcome in outcomes)


def test_a_write_the_store_refused_leaves_the_text_worth_trying_again() -> None:
    from optimus.context.authored_memory import MemoryStoreRefused

    extractor, _settlement, outcomes, _receipts = _harness(_Upstream(_completed(_GOOD, 1)))

    def refused(*_args: Any, **_kwargs: Any) -> Any:
        raise MemoryStoreRefused("LEASE_LOST")

    extractor._store.append = refused  # type: ignore[method-assign]
    extractor.submit(_turn())
    _until(outcomes, 1)
    assert outcomes[0].refusals == ("LEASE_LOST",)
    assert extractor._said == {}  # not marked extracted: the same words are tried again
    extractor.close()


def test_the_same_words_after_a_withdrawal_are_a_new_item() -> None:
    """Fable CP2 minor and Codex CP2 review 1, finding 8, through `submit`: words said again while their item stands make no
    call; once it is withdrawn they make a fresh item, never a replay of the withdrawn one."""
    upstream = _Upstream(_completed(_GOOD, 1), _completed(_GOOD, 2))
    extractor, _settlement, outcomes, _receipts = _harness(upstream)
    extractor.submit(_turn(1))
    _until(outcomes, 1)
    first = outcomes[0].notices[0]
    extractor.submit(_turn(3))
    _until(outcomes, 2)
    assert outcomes[1].skipped == "already_extracted" and len(upstream.calls) == 1
    del outcomes[1]
    with extractor._store.lease() as token:
        extractor._store.call("append", project="p-1", token=token, expected_version=1, idempotency_key="9" * 64,
                              event={"event_id": "e-withdraw", "item": first.item, "version": 2, "action": "withdraw", "trust": "user-authored",
                                     "status": "withdrawn", "kind": "preference", "scope": "s-1", "title": "", "statement": "", "anchors": [],
                                     "lineage": [], "valid_from_ms": 0, "valid_until_ms": 0})
    extractor.submit(_turn(2))
    _until(outcomes, 2)
    extractor.close()
    second = outcomes[1]
    assert not second.refusals and second.notices[0].item != first.item and second.notices[0].saved


def test_the_same_words_withdrawn_again_and_again_are_saved_each_time() -> None:
    """Codex CP2 review 2, finding 8, through `submit`: five withdrawals of the same words, and the sixth save still finds a
    free id; a bounded walk refused it as a version conflict for good."""
    import hashlib

    upstream = _Upstream(*(_completed(_GOOD, n) for n in range(1, 7)))
    extractor, _settlement, outcomes, _receipts = _harness(upstream)
    items: list[str] = []
    for n in range(1, 7):
        extractor.submit(_turn(n))
        _until(outcomes, n)
        (notice,) = outcomes[-1].notices
        assert not outcomes[-1].refusals and notice.saved and notice.item not in items, outcomes[-1]
        items.append(notice.item)
        with extractor._store.lease() as token:
            extractor._store.call("append", project="p-1", token=token, expected_version=1, idempotency_key=hashlib.sha256(str(n).encode()).hexdigest(),
                                  event={"event_id": f"e-withdraw-{n}", "item": notice.item, "version": 2, "action": "withdraw",
                                         "trust": "user-authored", "status": "withdrawn", "kind": "preference", "scope": "s-1", "title": "",
                                         "statement": "", "anchors": [], "lineage": [], "valid_from_ms": 0, "valid_until_ms": 0})
    extractor.close()


_RULE = json.dumps({"candidates": [{"speech_act": "decision", "kind": "constraint", "title": "deploy", "statement": "Never deploy.",
                                    "spans": [{"block": "b-1", "start": 0, "end": 13}]}]})
_AGAINST = json.dumps({"candidates": [{"speech_act": "assertion", "kind": "procedure", "title": "release",
                                       "statement": "Deploy after tests pass.", "evidence": ["ev-1"]}]})


def test_no_agent_call_is_made_in_a_scope_with_a_user_rule() -> None:
    """Codex CP2 review 1, finding 5, and review 2, finding 6, through the extractor: the lesson names no target and shares one
    word with the rule, and no check can show it leaves the rule standing; so in a scope holding a user item it could only go
    off, and the call is skipped (review 3's decision)."""
    control = _AGAINST.replace("Deploy after tests pass.", "Run the smoke tests before a deploy.")
    upstream = _Upstream(_completed(control, 1), _completed(_RULE, 2), _completed(_AGAINST, 3))
    extractor, settlement, outcomes, _receipts = _harness(upstream)
    work = mx.CompletedWork("released", (mx.Evidence("ev-1", "verification"),))
    extractor.submit(_turn(1, text="Release it.", work=work))
    _until(outcomes, 1)
    assert outcomes[0].reasons == ("ADMITTED",)  # control: no user item in the scope yet, so the optional lesson is kept
    extractor.submit(_turn(2, text="Never deploy."))
    _until(outcomes, 2)
    assert outcomes[1].reasons == ("ADMITTED",)
    work = mx.CompletedWork("released", (mx.Evidence("ev-1", "verification"), mx.Evidence("ev-2", "verification")))
    extractor.submit(_turn(3, text="Release it again.", work=work))
    _until(outcomes, 3)
    extractor.close()
    assert (outcomes[2].skipped, outcomes[2].notices) == ("user_items_in_scope", ())
    assert [purpose for _turn_id, purpose, _tokens, _prompt in upstream.calls] == [mx.AGENT_PURPOSE, mx.USER_PURPOSE]
    settlement.finalize_turn("s:3")
    assert settlement.settle_turn("s:3").pending_invocations == 0  # the skipped job still released its turn


def test_a_user_rule_saved_while_the_agent_call_is_out_sends_its_lesson_off() -> None:
    """The skip reads the scope before the call; the commit reads it again under the lease, so a rule saved meanwhile still
    sends the lesson off."""
    extractor, _settlement, outcomes, _receipts = _harness(_Upstream(_completed(_RULE, 1), _completed(_AGAINST, 2)))
    extractor.submit(_turn(1, text="Never deploy."))
    _until(outcomes, 1)
    store = extractor._store
    real, seen = store.user_items, []

    def first_empty(scope: str, *, limit: int) -> Any:  # the skip check ran just before the rule was saved
        seen.append(scope)
        return [] if len(seen) == 1 else real(scope, limit=limit)

    store.user_items = first_empty
    extractor.submit(_turn(2, text="Release it.", work=mx.CompletedWork("released", (mx.Evidence("ev-1", "verification"),))))
    _until(outcomes, 2)
    extractor.close()
    assert outcomes[1].reasons == ("USER_ITEMS_IN_SCOPE",) and len(seen) == 2
    (off,) = outcomes[1].notices
    assert store.read(off.item).event.trust == "off"  # appended as an off record, never as memory


def _retract(item: str) -> SummarizerResponse:
    text = "Cancel the rule about pushing to main."
    return _completed(json.dumps({"candidates": [{"speech_act": "retraction", "kind": "constraint", "title": "main", "statement": text,
                                                  "spans": [{"block": "b-1", "start": 0, "end": len(text)}], "target": item}]}), 2)


def test_a_target_the_words_no_longer_name_alone_under_the_lease_is_left_standing() -> None:
    """Codex CP2 review 5, finding 1: the host resolves the target again among every live user item under the lease, so a
    second rule the same words name, saved while the call was out, leaves both standing."""
    rule = json.dumps({"candidates": [{"speech_act": "decision", "kind": "constraint", "title": "main", "statement": "Never push to main.",
                                       "spans": [{"block": "b-1", "start": 0, "end": 19}]}]})
    upstream = _Upstream(_completed(rule, 1))
    extractor, _settlement, outcomes, _receipts = _harness(upstream)
    extractor.submit(_turn(1, text="Never push to main."))
    _until(outcomes, 1)
    (saved,) = outcomes[0].notices
    store = extractor._store
    real = store.user_items

    def another_too(scope: str, *, limit: int) -> Any:  # what the lease-time read sees: a second rule the words also name
        found = real(scope, limit=limit)
        return found if limit <= mx.MAX_EXISTING_ITEMS else [*found, mx.ExistingItem("m-" + "b" * 16, "Never push to main without review.")]

    store.user_items = another_too
    upstream.replies.append(_retract(saved.item))
    extractor.submit(_turn(2, text="Cancel the rule about pushing to main."))
    _until(outcomes, 2)
    extractor.close()
    assert outcomes[1].reasons == ("SPANS_UNVERIFIED",) and store.read(saved.item).event.status == "active"


def test_a_target_the_words_name_alone_is_withdrawn() -> None:
    """Control for the lease-time resolution: with the one rule live, the same words withdraw it."""
    rule = json.dumps({"candidates": [{"speech_act": "decision", "kind": "constraint", "title": "main", "statement": "Never push to main.",
                                       "spans": [{"block": "b-1", "start": 0, "end": 19}]}]})
    upstream = _Upstream(_completed(rule, 1))
    extractor, _settlement, outcomes, _receipts = _harness(upstream)
    extractor.submit(_turn(1, text="Never push to main."))
    _until(outcomes, 1)
    (saved,) = outcomes[0].notices
    upstream.replies.append(_retract(saved.item))
    extractor.submit(_turn(2, text="Cancel the rule about pushing to main."))
    _until(outcomes, 2)
    extractor.close()
    assert outcomes[1].reasons == ("RETRACTED",) and extractor._store.read(saved.item).event.status == "withdrawn"


def test_a_refused_receipt_never_drops_the_attempts_after_it() -> None:
    """Codex CP2 review 1, finding 6: every attempt is offered to settlement before the first refusal is reported."""
    two = SummarizerResponse(text=_GOOD, finish_status="stop", attempts=(SummarizerAttempt("a-1", "gw-1", "rejected", Decimal("0.001")),
                                                                         SummarizerAttempt("a-2", "gw-2", "completed", Decimal("0.002"))))
    extractor, _settlement, outcomes, receipts = _harness(_Upstream(two))
    offered: list[str] = []

    def record(turn_id: str, purpose: str, attempt: SummarizerAttempt, finish: str | None) -> None:
        offered.append(attempt.attempt_id)
        if attempt.attempt_id == "a-1":
            raise RuntimeError("ledger refused")

    extractor._record = record
    extractor.submit(_turn())
    _until(outcomes, 1)
    extractor.close()
    assert offered == ["a-1", "a-2"] and outcomes[0].incomplete == "extractor_fault" and not outcomes[0].notices
