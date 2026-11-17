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
