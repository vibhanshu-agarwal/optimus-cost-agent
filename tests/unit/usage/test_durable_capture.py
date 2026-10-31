"""Plan 12.8 Task 1: durable coverage epochs and the host's capture records, on a real outbox under a temporary root.
Every record a test reads back is also validated against its kind's contract schema."""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from optimus.gateway.models import GatewayUsage
from optimus.usage import capture_events as ev
from optimus.usage.durable_capture import DurableCapture, host_outbox_root
from optimus.usage.turn_settlement import StageReceipt, TurnCostSummary
from optimus_security import durable_outbox as ob
from optimus_security import usage_capture_contract as uc
from tools.testing import run_context_guard

_AT = datetime(2026, 10, 31, tzinfo=UTC)


def _capture(tmp_path, **kwargs) -> DurableCapture:
    ack_wait = kwargs.pop("ack_wait", 5.0)
    return DurableCapture(ob.OutboxWriter(host_outbox_root(tmp_path / "config"), **kwargs), ack_wait=ack_wait, clock=lambda: _AT)


def _records(capture: DurableCapture) -> list[dict]:
    payloads = [dict(r.payload) for r in ob.scan_stream(capture.writer.directory).records]
    for payload in payloads:
        uc.validate_payload(payload, writer="host")
    return payloads


def _kinds(capture: DurableCapture) -> list[str]:
    return [r["kind"] for r in _records(capture)]


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


def _drain(capture: DurableCapture) -> None:
    deadline = time.monotonic() + 5.0
    while capture.writer.stats().pending and time.monotonic() < deadline:
        time.sleep(0.01)


def _gate(capture: DurableCapture, kind: str) -> tuple[threading.Event, threading.Event]:
    """Block the writer inside the first record of ``kind`` until the returned gate is set."""
    gate, entered = threading.Event(), threading.Event()
    original = capture.writer._writer.append

    def slow(payload, *, event_id=None):
        if payload.get("kind") == kind and not entered.is_set():
            entered.set()
            gate.wait(5.0)
        return original(payload, event_id=event_id)

    capture.writer._writer.append = slow  # type: ignore[method-assign]
    return gate, entered


def test_a_clean_turn_records_begin_intent_receipt_and_a_complete_close_in_order(tmp_path):
    capture = _capture(tmp_path)
    invocation = capture.invocation_opened("s:1", "s")
    assert capture.intent("s:1", "s:1:planning:1:1", stage="planning", requested_model="m")
    receipt = _receipt()
    capture.receipt(receipt)
    capture.invocation_ended("s:1", invocation, "ended")
    assert capture.close(_summary("s:1", (receipt,)))
    capture.stop()

    records = _records(capture)

    assert [r["kind"] for r in records] == [
        uc.STREAM_START, uc.EPOCH_BEGIN, uc.INVOCATION_OPEN, uc.ATTEMPT_INTENT, uc.ATTEMPT_RECEIPT, uc.INVOCATION_END,
        uc.EPOCH_IDENTITIES, uc.EPOCH_CLOSE, uc.STREAM_END,
    ]
    assert len({r["epoch_id"] for r in records if r.get("epoch_id")}) == 1
    identities, close = records[6], records[7]
    assert identities["settled_attempt_ids"] == [receipt.attempt_id] and identities["parts"] == 1
    assert close["host_complete"] is True and close["begin_confirmed"] is True and close["identity_parts"] == 1
    assert close["settled_count"] == 1 and close["known_subtotal_usd"] == "0.25"
    assert records[3]["purpose"] == "agent.plan"


def test_the_receipt_record_is_allowlisted_and_keeps_unknowns_and_presence(tmp_path):
    capture = _capture(tmp_path)
    capture.receipt(_receipt(attempt="a:1"))
    capture.receipt(_receipt(attempt="a:2", cache_hit=False, reasoning_tokens=None))
    capture.receipt(_receipt(attempt="a:3", cost=None))
    capture.receipt(_receipt(attempt="a:4", cost="0.0000001"))
    capture.stop()

    first, second, unknown, tiny = [r for r in _records(capture) if r["kind"] == uc.ATTEMPT_RECEIPT]

    assert "cache_hit" not in first["usage"], "an absent cache fact is not persisted as an observed miss"
    assert second["usage"]["cache_hit"] is False
    assert first["usage"]["cost_usd"] == "0.25" and first["usage"]["reasoning_tokens"] is None
    assert unknown["reported_cost_usd"] is None and unknown["usage"] is None and unknown["outcome"] == "uncertain"
    assert tiny["reported_cost_usd"] == "0.0000001", "never exponent notation"
    assert first["facts_digest"].startswith("hex:") and "gateway_usage" not in first


def test_equal_receipts_digest_equally_under_both_replay_contracts():
    a = _receipt(cost="0.25")
    b = _receipt(cost="0.250")

    assert a.facts() == b.facts() and a.settled_facts() == b.settled_facts()
    assert ev.digest(a.facts()) == ev.digest(b.facts())
    assert ev.digest(a.settled_facts()) == ev.digest(b.settled_facts())
    assert ev.digest(a.facts()) != ev.digest(_receipt(cost="0.26").facts())


def test_a_terminal_state_with_a_running_worker_snapshots_and_closes_after_settlement(tmp_path):
    capture = _capture(tmp_path)
    worker = capture.invocation_opened("s:1")
    assert not capture.close(_summary("s:1", (), pending_invocations=1)), "teardown with a worker still running"
    assert not capture.close(_summary("s:1", (), pending_invocations=1)), "one snapshot only"
    receipt = _receipt()
    capture.receipt(receipt)  # the worker's attempt, still inside the epoch
    capture.invocation_ended("s:1", worker, "ended")
    assert capture.close(_summary("s:1", (receipt,)))
    capture.stop()

    records = _records(capture)
    kinds = [r["kind"] for r in records]
    assert kinds.count(uc.EPOCH_TERMINAL) == 1 and kinds.count(uc.EPOCH_CLOSE) == 1
    assert kinds.index(uc.EPOCH_TERMINAL) < kinds.index(uc.ATTEMPT_RECEIPT) < kinds.index(uc.EPOCH_CLOSE)
    receipt_record = next(r for r in records if r["kind"] == uc.ATTEMPT_RECEIPT)
    assert receipt_record["late"] is False
    assert next(r for r in records if r["kind"] == uc.EPOCH_CLOSE)["host_complete"] is True


def test_large_identity_sets_continue_in_ordered_parts_bound_by_the_close(tmp_path):
    capture = _capture(tmp_path)
    capture.invocation_opened("s:1")
    receipts = tuple(_receipt(attempt=f"s:1:planning:1:{n}:1") for n in range(uc.MAX_LIST * 2 + 5))
    capture.close(_summary("s:1", receipts))
    capture.stop()

    records = _records(capture)
    parts = [r for r in records if r["kind"] == uc.EPOCH_IDENTITIES]
    close = next(r for r in records if r["kind"] == uc.EPOCH_CLOSE)

    assert [p["part"] for p in parts] == [1, 2, 3] and {p["parts"] for p in parts} == {3}
    assert sum((p["settled_attempt_ids"] for p in parts), []) == [r.attempt_id for r in receipts]
    assert close["identity_parts"] == 3 and close["settled_count"] == len(receipts)
    assert close["identities_digest"] == ev.identity_parts(close["epoch_id"], _summary("s:1", receipts))[1]


def test_a_late_receipt_after_a_written_close_is_appended_and_the_close_is_not_rewritten(tmp_path):
    capture = _capture(tmp_path)
    capture.invocation_opened("s:1")
    assert capture.close(_summary("s:1", ()))
    _drain(capture)
    capture.receipt(_receipt())
    assert not capture.close(_summary("s:1", (_receipt(),))), "a written close is final"
    capture.stop()

    records = _records(capture)
    assert [r["kind"] for r in records].count(uc.EPOCH_CLOSE) == 1
    late = next(r for r in records if r["kind"] == uc.ATTEMPT_RECEIPT)
    assert late["late"] is True and late["epoch_id"] == next(r["epoch_id"] for r in records if r["kind"] == uc.EPOCH_BEGIN)


def test_an_incomplete_settlement_summary_never_closes_complete(tmp_path):
    capture = _capture(tmp_path)
    capture.invocation_opened("s:1")
    unknown = _receipt(cost=None)
    capture.receipt(unknown)
    capture.close(_summary("s:1", (unknown,)))
    capture.stop()

    records = _records(capture)
    close = next(r for r in records if r["kind"] == uc.EPOCH_CLOSE)
    assert close["host_complete"] is False and close["unknown_count"] == 1
    assert next(r for r in records if r["kind"] == uc.EPOCH_IDENTITIES)["unknown_attempt_ids"] == [unknown.attempt_id]


def test_a_refused_record_keeps_the_epoch_incomplete_and_model_work_proceeds(tmp_path):
    capture = _capture(tmp_path, queue_records=3)
    capture.invocation_opened("s:1")
    _drain(capture)
    gate, entered = _gate(capture, uc.ATTEMPT_RECEIPT)
    capture.receipt(_receipt(attempt="a:1"))
    assert entered.wait(5.0)  # the writer is inside a:1; the queue is empty
    for n in (2, 3, 4):
        capture.receipt(_receipt(attempt=f"a:{n}"))  # fill the queue
    capture.receipt(_receipt(attempt="a:5"))  # refused
    gate.set()
    _drain(capture)
    assert capture.close(_summary("s:1", ()))
    capture.stop()

    close = next(r for r in _records(capture) if r["kind"] == uc.EPOCH_CLOSE)
    assert close["rejected_records"] == 1 and close["host_complete"] is False


def test_a_refused_close_leaves_the_epoch_open_for_a_later_close(tmp_path):
    capture = _capture(tmp_path, queue_records=3)
    capture.invocation_opened("s:1")
    _drain(capture)
    gate, entered = _gate(capture, uc.ATTEMPT_RECEIPT)
    capture.receipt(_receipt())
    assert entered.wait(5.0)
    capture.integrity_failure("s:1", "receipt_conflict")
    capture.integrity_failure("s:1", "receipt_conflict")
    assert not capture.close(_summary("s:1", ())), "its identity part takes the last slot; the close is refused"
    gate.set()
    _drain(capture)
    capture.receipt(_receipt(attempt="s:1:planning:1:2:1"))
    assert capture.close(_summary("s:1", ()))
    capture.stop()

    records = _records(capture)
    assert [r["kind"] for r in records].count(uc.EPOCH_CLOSE) == 1
    assert all(r["late"] is False for r in records if r["kind"] == uc.ATTEMPT_RECEIPT), "the epoch stayed open"
    assert next(r for r in records if r["kind"] == uc.EPOCH_CLOSE)["host_complete"] is False


def test_a_queued_close_whose_write_fails_reopens_the_epoch(tmp_path, monkeypatch):
    capture = _capture(tmp_path)
    capture.invocation_opened("s:1")
    _drain(capture)
    original = capture.writer._writer.append

    def failing_close(payload, *, event_id=None):
        if payload.get("kind") == uc.EPOCH_CLOSE:
            raise ob.OutboxError("WRITE_FAILED", "simulated")
        return original(payload, event_id=event_id)

    capture.writer._writer.append = failing_close  # type: ignore[method-assign]
    assert capture.close(_summary("s:1", ()))
    _drain(capture)
    capture.writer._writer.append = original  # type: ignore[method-assign]
    capture.receipt(_receipt())
    assert capture.close(_summary("s:1", (_receipt(),)))
    capture.stop()

    records = _records(capture)
    assert next(r for r in records if r["kind"] == uc.ATTEMPT_RECEIPT)["late"] is False
    assert [r["kind"] for r in records].count(uc.EPOCH_CLOSE) == 1


def test_an_intent_not_durable_within_the_wait_is_unconfirmed_even_if_written_later(tmp_path):
    capture = _capture(tmp_path, ack_wait=0.05)
    gate, _ = _gate(capture, uc.ATTEMPT_INTENT)
    capture.invocation_opened("s:1")
    confirmed = capture.intent("s:1", "s:1:planning:1:1", stage="planning")
    gate.set()
    _drain(capture)
    capture.close(_summary("s:1", ()))
    capture.stop()

    records = _records(capture)
    assert confirmed is False
    assert any(r["kind"] == uc.ATTEMPT_INTENT for r in records), "the record itself still lands"
    close = next(r for r in records if r["kind"] == uc.EPOCH_CLOSE)
    assert close["unconfirmed_intents"] == 1 and close["host_complete"] is False


def test_a_begin_that_never_persisted_cannot_close_complete(tmp_path):
    capture = _capture(tmp_path)
    original = capture.writer._writer.append

    def failing_begin(payload, *, event_id=None):
        if payload.get("kind") in {uc.STREAM_START, uc.EPOCH_BEGIN}:
            raise ob.OutboxError("WRITE_FAILED", "simulated disk full")
        return original(payload, event_id=event_id)

    capture.writer._writer.append = failing_begin  # type: ignore[method-assign]
    capture.invocation_opened("s:1")
    _drain(capture)
    capture.close(_summary("s:1", ()))
    capture.stop()

    records = _records(capture)
    close = next(r for r in records if r["kind"] == uc.EPOCH_CLOSE)
    assert close["begin_confirmed"] is False and close["host_complete"] is False
    assert uc.EPOCH_BEGIN not in [r["kind"] for r in records]


def test_stop_records_the_open_epochs_without_closing_them(tmp_path):
    capture = _capture(tmp_path)
    capture.invocation_opened("s:1")
    assert capture.stop()

    records = _records(capture)
    assert records[-1]["kind"] == uc.STREAM_END and records[-1]["open_epochs"] == [records[1]["epoch_id"]]
    assert uc.EPOCH_CLOSE not in [r["kind"] for r in records]


@pytest.mark.parametrize(("stage", "purpose", "expected"), [("summarization", "memory.extract", "memory.extract"), ("answer", None, "agent.answer")])
def test_purposes_default_by_stage_and_memory_is_summarization_only(stage, purpose, expected):
    assert ev.purpose_for(stage, purpose) == expected
    with pytest.raises(ValueError):
        ev.purpose_for("planning", "memory.extract")
    with pytest.raises(ValueError):
        ev.purpose_for("summarization", "Memory Extract")


def test_capture_aimed_at_the_real_config_root_is_refused_visibly_and_creates_nothing():
    """The accounting-root control: in the guarded pytest process, a capture writer pointed at the real per-user config
    root fails its writes, model work proceeds, and the refusal stays visible although production code swallowed it."""
    if run_context_guard.mode() != "pytest_process_guard":
        pytest.skip("the pytest-process guard is not installed in this run")
    config_root = next(Path(root) for root in run_context_guard.protected_roots() if root.endswith("\\roaming\\optimus-cost-agent"))
    accounting = config_root / "accounting"
    existed = accounting.exists()
    before = run_context_guard.denials()
    capture = DurableCapture.at(config_root)

    confirmed = capture.intent("s:1", "s:1:planning:1:1", stage="planning")
    capture.stop()

    assert confirmed is False
    assert capture.writer.stats().last_failure == "WRITE_FAILED"
    assert run_context_guard.denials() > before, "the guard refused the write"
    assert accounting.exists() == existed and not capture.writer.directory.exists()
    assert json.dumps(capture.writer.stats().__dict__)  # stats stay reportable


def test_decimals_persist_exactly_beyond_the_context_precision_and_digest_distinctly():
    from decimal import localcontext

    first, second = "0.12345678901234567890123456781", "0.12345678901234567890123456782"
    with localcontext() as context:
        context.prec = 5
        texts = [ev.decimal_text(Decimal(v)) for v in (first, second, "0.250", "1E+1", "0E-8")]
        digests = {ev.digest(_receipt(cost=v).facts()) for v in (first, second)}

    assert texts == [first, second, "0.25", "10", "0"]
    assert len(digests) == 2, "a contradictory replay can never look identical"


def test_maximal_identities_split_into_parts_that_each_fit_the_record_cap(tmp_path):
    capture = _capture(tmp_path)
    capture.invocation_opened("s:1")
    settled = tuple(f"s:{n:04d}:" + "x" * (uc.MAX_STRING - 7) for n in range(50))
    unknown = settled[:20] + tuple(f"u{n:03d}" + "é" * (uc.MAX_STRING - 4) for n in range(100))  # under MAX_LIST, over the byte cap
    summary = TurnCostSummary(turn_id="s:1", known_subtotal_usd=Decimal("0"), unknown_attempt_ids=unknown, receipt_ids=settled)
    assert capture.close(summary)
    capture.stop()

    lines = {r.digest: r.line for r in ob.scan_stream(capture.writer.directory).records}
    records = _records(capture)
    parts = [r for r in records if r["kind"] == uc.EPOCH_IDENTITIES]
    close = next(r for r in records if r["kind"] == uc.EPOCH_CLOSE)

    assert all(len(line) <= ob.MAX_RECORD_BYTES for line in lines.values())
    assert [p["part"] for p in parts] == list(range(1, len(parts) + 1)) and close["identity_parts"] == len(parts) >= 2
    assert tuple(sum((p["settled_attempt_ids"] for p in parts), [])) == settled
    assert tuple(sum((p["unknown_attempt_ids"] for p in parts), [])) == unknown
    assert close["identities_digest"] == ev.identity_parts(close["epoch_id"], summary)[1]
