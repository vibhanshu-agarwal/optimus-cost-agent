"""Plan 12.8 Task 1: durable coverage epochs and the capture contract, on a real outbox under a temporary root."""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from optimus.gateway.models import GatewayUsage
from optimus.usage import capture_events as ev
from optimus.usage.durable_capture import DurableCapture, host_outbox_root
from optimus.usage.turn_settlement import StageReceipt, TurnCostSummary
from optimus_security import durable_outbox as ob

_AT = datetime(2026, 10, 31, tzinfo=UTC)


def _capture(tmp_path, **kwargs) -> DurableCapture:
    return DurableCapture(ob.OutboxWriter(host_outbox_root(tmp_path / "config"), **kwargs), clock=lambda: _AT)


def _records(capture: DurableCapture) -> list[dict]:
    return [dict(r.payload) for r in ob.scan_stream(capture.writer.directory).records]


def _receipt(turn: str = "s:1", attempt: str = "s:1:planning:1:1:1", cost: str | None = "0.25", **usage_kwargs) -> StageReceipt:
    usage = None
    if cost is not None:
        usage = GatewayUsage(
            gateway_request_id=f"gw-{attempt}", provider="openrouter", billing_units=10, cost_usd=Decimal(cost), **usage_kwargs
        )
    return StageReceipt(
        session_id="s",
        turn_id=turn,
        stage="planning",
        attempt_id=attempt,
        gateway_request_id=f"gw-{attempt}" if cost is not None else None,
        outcome="completed" if cost is not None else "uncertain",
        reported_cost_usd=Decimal(cost) if cost is not None else None,
        recorded_at=_AT,
        gateway_usage=usage,
    )


def _summary(turn: str, receipts: tuple[StageReceipt, ...], **kwargs) -> TurnCostSummary:
    known = sum((r.reported_cost_usd for r in receipts if r.reported_cost_usd is not None), Decimal("0"))
    return TurnCostSummary(
        turn_id=turn,
        known_subtotal_usd=known,
        unknown_attempt_ids=tuple(r.attempt_id for r in receipts if r.reported_cost_usd is None),
        receipt_ids=tuple(r.attempt_id for r in receipts),
        **kwargs,
    )


def test_a_clean_turn_records_begin_intent_receipt_and_a_complete_close_in_order(tmp_path):
    capture = _capture(tmp_path)
    invocation = capture.invocation_opened("s:1", "s")
    assert capture.intent("s:1", "s:1:planning:1:1", stage="planning", requested_model="m")
    receipt = _receipt()
    capture.receipt(receipt)
    capture.invocation_ended("s:1", invocation, "ended")
    capture.close(_summary("s:1", (receipt,)))
    capture.stop()

    records = _records(capture)
    kinds = [r["kind"] for r in records]

    assert kinds == [ev.STREAM_START, ev.EPOCH_BEGIN, ev.INVOCATION_OPEN, ev.ATTEMPT_INTENT, ev.ATTEMPT_RECEIPT, ev.INVOCATION_END, ev.EPOCH_CLOSE, ev.STREAM_END]
    epoch_ids = {r["epoch_id"] for r in records if "epoch_id" in r}
    assert len(epoch_ids) == 1
    close = records[6]
    assert close["host_complete"] is True and close["begin_confirmed"] is True
    assert close["settled_attempt_ids"] == [receipt.attempt_id] and close["known_subtotal_usd"] == "0.25"
    assert records[3]["purpose"] == "agent.plan"


def test_the_receipt_record_is_allowlisted_and_keeps_unknowns_and_presence(tmp_path):
    capture = _capture(tmp_path)
    capture.receipt(_receipt(attempt="a:1"))
    capture.receipt(_receipt(attempt="a:2", cache_hit=False, reasoning_tokens=None))
    capture.receipt(_receipt(attempt="a:3", cost=None))
    capture.stop()

    receipts = [r for r in _records(capture) if r["kind"] == ev.ATTEMPT_RECEIPT]
    first, second, unknown = receipts

    assert "cache_hit" not in first["usage"], "an absent cache fact is not persisted as an observed miss"
    assert second["usage"]["cache_hit"] is False
    assert first["usage"]["cost_usd"] == "0.25" and first["usage"]["reasoning_tokens"] is None
    assert unknown["reported_cost_usd"] is None and unknown["usage"] is None and unknown["outcome"] == "uncertain"
    assert set(first) >= {"facts_digest", "settled_digest"} and first["facts_digest"].startswith("hex:")
    assert "gateway_usage" not in first and "prompt" not in json.dumps(receipts)


def test_a_late_receipt_after_close_is_appended_and_the_close_is_not_rewritten(tmp_path):
    capture = _capture(tmp_path)
    capture.invocation_opened("s:1")
    capture.close(_summary("s:1", ()))
    capture.receipt(_receipt())
    capture.close(_summary("s:1", (_receipt(),)))  # a second close is a no-op
    capture.stop()

    records = _records(capture)
    assert [r["kind"] for r in records].count(ev.EPOCH_CLOSE) == 1
    late = next(r for r in records if r["kind"] == ev.ATTEMPT_RECEIPT)
    assert late["late"] is True and late["epoch_id"] == next(r["epoch_id"] for r in records if r["kind"] == ev.EPOCH_BEGIN)


def test_an_incomplete_settlement_summary_never_closes_complete(tmp_path):
    capture = _capture(tmp_path)
    capture.invocation_opened("s:1")
    unknown = _receipt(cost=None)
    capture.receipt(unknown)
    capture.close(_summary("s:1", (unknown,)))
    capture.stop()

    close = next(r for r in _records(capture) if r["kind"] == ev.EPOCH_CLOSE)
    assert close["host_complete"] is False and close["unknown_attempt_ids"] == [unknown.attempt_id]


def test_a_refused_record_keeps_the_epoch_incomplete_and_model_work_proceeds(tmp_path):
    capture = _capture(tmp_path, queue_records=1)
    gate = threading.Event()
    original = capture.writer._writer.append

    def slow(payload, *, event_id=None):
        gate.wait(5.0)
        return original(payload, event_id=event_id)

    capture.writer._writer.append = slow  # type: ignore[method-assign]
    capture.invocation_opened("s:1")  # stream.start in flight, begin queued, invocation refused
    capture.receipt(_receipt())  # refused: the queue is full
    gate.set()
    _drain(capture)
    capture.close(_summary("s:1", (_receipt(),)))
    capture.stop()

    close = next(r for r in _records(capture) if r["kind"] == ev.EPOCH_CLOSE)
    assert close["rejected_records"] >= 1 and close["host_complete"] is False


def test_a_refused_close_leaves_the_epoch_open_rather_than_inferring_one(tmp_path):
    capture = _capture(tmp_path, queue_records=1)
    gate, entered = threading.Event(), threading.Event()
    original = capture.writer._writer.append

    def slow(payload, *, event_id=None):
        if payload.get("kind") == ev.ATTEMPT_RECEIPT:
            entered.set()
            gate.wait(5.0)
        return original(payload, event_id=event_id)

    capture.writer._writer.append = slow  # type: ignore[method-assign]
    for step in (lambda: capture.invocation_opened("s:1"), lambda: capture.receipt(_receipt())):
        _drain(capture)
        step()
    assert entered.wait(5.0)  # the writer is inside the receipt; the queue is empty
    capture.integrity_failure("s:1", "receipt_conflict")  # fills the queue
    capture.close(_summary("s:1", ()))  # refused: the queue is full
    gate.set()
    _drain(capture)
    capture.stop()

    kinds = [r["kind"] for r in _records(capture)]
    assert ev.INTEGRITY_FAILURE in kinds
    assert ev.EPOCH_CLOSE not in kinds and kinds[-1] == ev.STREAM_END


def _drain(capture: DurableCapture) -> None:
    deadline = time.monotonic() + 5.0
    while capture.writer.stats().pending and time.monotonic() < deadline:
        time.sleep(0.01)


def test_an_intent_not_durable_within_the_wait_is_unconfirmed_even_if_written_later(tmp_path):
    capture = DurableCapture(ob.OutboxWriter(host_outbox_root(tmp_path / "config")), ack_wait=0.05, clock=lambda: _AT)
    gate = threading.Event()
    original = capture.writer._writer.append

    def slow(payload, *, event_id=None):
        if payload.get("kind") == ev.ATTEMPT_INTENT:
            gate.wait(5.0)
        return original(payload, event_id=event_id)

    capture.writer._writer.append = slow  # type: ignore[method-assign]
    capture.invocation_opened("s:1")
    confirmed = capture.intent("s:1", "s:1:planning:1:1", stage="planning")
    gate.set()
    capture.close(_summary("s:1", ()))
    capture.stop()

    records = _records(capture)
    assert confirmed is False
    assert any(r["kind"] == ev.ATTEMPT_INTENT for r in records), "the record itself still lands"
    close = next(r for r in records if r["kind"] == ev.EPOCH_CLOSE)
    assert close["unconfirmed_intents"] == 1 and close["host_complete"] is False


def test_a_begin_that_never_persisted_cannot_close_complete(tmp_path, monkeypatch):
    capture = _capture(tmp_path)
    real_fsync = ob.os.fsync
    failures = iter([True, True])  # stream.start and epoch.begin fail; later records succeed

    def flaky(fd):
        if next(failures, False):
            raise OSError(28, "simulated disk full")
        return real_fsync(fd)

    monkeypatch.setattr(ob.os, "fsync", flaky)
    capture.invocation_opened("s:1")
    capture.close(_summary("s:1", ()))
    capture.stop()

    records = _records(capture)
    close = next(r for r in records if r["kind"] == ev.EPOCH_CLOSE)
    assert close["begin_confirmed"] is False and close["host_complete"] is False
    assert records[0]["kind"] == ob.GAP_KIND and records[0]["unconfirmed_from"] == 1


def test_stop_records_the_open_epochs_without_closing_them(tmp_path):
    capture = _capture(tmp_path)
    capture.invocation_opened("s:1")
    capture.stop()

    records = _records(capture)
    assert [r["kind"] for r in records][-1] == ev.STREAM_END
    assert records[-1]["open_epochs"] == [records[1]["epoch_id"]]
    assert ev.EPOCH_CLOSE not in [r["kind"] for r in records]


@pytest.mark.parametrize(("stage", "purpose", "expected"), [("summarization", "memory.extract", "memory.extract"), ("answer", None, "agent.answer")])
def test_purposes_default_by_stage_and_memory_is_summarization_only(stage, purpose, expected):
    assert ev.purpose_for(stage, purpose) == expected
    with pytest.raises(ValueError):
        ev.purpose_for("planning", "memory.extract")
    with pytest.raises(ValueError):
        ev.purpose_for("summarization", "Memory Extract")
