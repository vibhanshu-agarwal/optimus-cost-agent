"""Plan 12.4 Task 5: each routed Auto turn shows one confirmed notice before its planning or answer call, and every
admitted Auto turn leaves exactly one content-free routing record (the Task 5 implementation note r3, sections 4-5).
"""

from __future__ import annotations

import asyncio
import threading
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from optimus.acp.auto_composition import (
    AutoDecision,
    ClassifierHalted,
    ClassifierOutcome,
    Escalation,
    notice_text,
    routing_record,
)
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.telemetry.events import TelemetryEventKind
from optimus.usage.turn_settlement import StageReceipt
from tests.support.contract_doubles import checked_agent_runner
from tests.unit.acp.test_auto_turn_routing import GEMINI, LUNA, Classifier, _router
from tests.unit.acp.test_context_engine_admission import Runner, new_session, prompt, prompt_request, rpc, session_of, texts

RECORD_KEYS = {
    "arm", "disposition", "reason", "answered_by", "predicted_tier", "classifier_tier", "confidence_band",
    "routed_up_for_confidence", "failure_kind", "classifier_attempt", "escalations", "default_fallback", "tier", "role",
    "model_id", "notice_delivered",
}  # fmt: skip


def _decision(**changes: Any) -> AutoDecision:
    base: dict[str, Any] = dict(
        classifier_tier="medium", confidence_band="high", routed_up_for_confidence=False, failure_kind=None, escalations=(),
        default_fallback=False, tier="medium", role="medium", model_id=GEMINI, predicted_tier="medium", answered_by="classifier",
    )  # fmt: skip
    return AutoDecision(**{**base, **changes})


@pytest.mark.parametrize(
    ("changes", "text"),
    [
        ({}, "Auto: medium → google/gemini-3.8-flash"),
        ({"routed_up_for_confidence": True, "predicted_tier": "easy"}, "Auto: medium → google/gemini-3.8-flash (unsure, so one tier up from easy)"),
        ({"escalations": (Escalation(from_tier="easy", reason="stopped"),)}, "Auto: medium → google/gemini-3.8-flash (no easy model available: stopped)"),
        ({"tier": "complex", "failure_kind": "timeout"}, "Auto: complex → google/gemini-3.8-flash (the classifier failed: timeout)"),
        ({"default_fallback": True}, "Auto: medium → google/gemini-3.8-flash (the default model: no tier was available)"),
        (
            {"failure_kind": "abstention", "escalations": (Escalation(from_tier="complex", reason="empty"),), "default_fallback": True},
            "Auto: medium → google/gemini-3.8-flash (the classifier failed: no confident answer; no complex model available: "
            "none configured; the default model: no tier was available)",
        ),
    ],
    ids=["base", "routed-up", "escalation", "failure", "default", "joined"],
)
def test_the_notice_says_why_a_turn_is_not_simply_its_classifiers_tier(changes: dict[str, Any], text: str) -> None:
    assert notice_text(_decision(**changes)) == text


def test_the_record_is_content_free_and_null_where_unknown() -> None:
    outcome = ClassifierOutcome(tier="medium", confidence_band="high", predicted_tier="medium", answered_by="rules")
    record = routing_record("refused", outcome=outcome, reason="AUTO_NO_ROUTABLE_MODEL")
    assert set(record) == RECORD_KEYS
    assert (record["disposition"], record["reason"], record["answered_by"], record["classifier_tier"]) == ("refused", "AUTO_NO_ROUTABLE_MODEL", "rules", "medium")
    assert record["model_id"] is None and record["escalations"] is None and record["notice_delivered"] is False


class SeesNotices(Runner):
    """Records the notices already sent when each run starts."""

    def __init__(self, outbound: RecordingOutboundChannel) -> None:
        super().__init__()
        self.outbound = outbound
        self.seen: list[list[str]] = []

    def run(self, request, **kwargs):
        self.seen.append(texts(self.outbound))
        return super().run(request, **kwargs)


class Unconfirmed(RecordingOutboundChannel):
    async def notify(self, method: str, params: dict[str, Any], *, require_flushed: bool = False) -> None:
        update = params.get("update", {})
        if require_flushed and update.get("content", {}).get("text", "").startswith("Auto:"):
            raise TimeoutError("not confirmed")
        await super().notify(method, params, require_flushed=require_flushed)


def _adapter(tmp_path: Path, classifier: Any, *, outbound: RecordingOutboundChannel | None = None):
    outbound = outbound or RecordingOutboundChannel()
    runner = SeesNotices(outbound)
    events: list[Any] = []
    router = _router(classifier)
    adapter = AcpDuplexAdapter(
        runner=checked_agent_runner(runner), workspace_root=tmp_path, sessions=InMemoryAcpSpecSessionStore(), outbound=outbound,
        auto_router=router, settlement_sink=events.append,
    )  # fmt: skip
    return adapter, outbound, runner, events, router


def _records(events: list[Any]) -> list[dict[str, Any]]:
    return [event.payload for event in events if event.kind is TelemetryEventKind.AUTO_ROUTING]


async def test_a_routed_turn_shows_one_confirmed_notice_before_its_call_and_records_its_route(tmp_path) -> None:
    adapter, outbound, runner, events, _ = _adapter(tmp_path, Classifier(["easy"]))
    session_id = await new_session(adapter, tmp_path, mode="chat")

    await prompt(adapter, outbound, session_id, "Hello?", "q1")

    assert runner.seen == [[f"Auto: easy → {LUNA}"]], "the notice precedes the answer call"
    [record] = _records(events)
    assert set(record) == RECORD_KEYS
    assert (record["disposition"], record["tier"], record["model_id"], record["notice_delivered"]) == ("routed", "easy", LUNA, True)
    assert record["classifier_attempt"] is None, "the rules (here, a fake) made no classifier call"


async def test_an_unconfirmed_notice_still_runs_the_turn_and_is_recorded_undelivered(tmp_path) -> None:
    adapter, outbound, runner, events, _ = _adapter(tmp_path, Classifier(["easy"]), outbound=Unconfirmed())
    session_id = await new_session(adapter, tmp_path, mode="chat")

    await prompt(adapter, outbound, session_id, "Hello?", "q1")

    assert len(runner.requests) == 1
    [record] = _records(events)
    assert (record["disposition"], record["notice_delivered"]) == ("routed", False)


async def test_a_refused_turn_records_its_reason_and_shows_no_notice(tmp_path) -> None:
    adapter, outbound, runner, events, router = _adapter(tmp_path, Classifier(["complex"]))
    router.stops.add(GEMINI)
    session_id = await new_session(adapter, tmp_path, mode="chat")

    await prompt(adapter, outbound, session_id, "Hello?", "q1")

    assert runner.requests == [] and not any(text.startswith("Auto:") for text in texts(outbound))
    [record] = _records(events)
    assert (record["disposition"], record["reason"], record["classifier_tier"], record["model_id"]) == ("refused", "AUTO_NO_ROUTABLE_MODEL", "complex", None)


async def test_a_refused_lease_cancels_the_turn_and_records_it(tmp_path) -> None:
    adapter, outbound, runner, events, _ = _adapter(tmp_path, Classifier([ClassifierHalted()]))
    session_id = await new_session(adapter, tmp_path, mode="chat")

    response = await prompt(adapter, outbound, session_id, "Hello?", "q1")

    assert response["result"]["stopReason"] == "cancelled" and runner.requests == []
    [record] = _records(events)
    assert (record["disposition"], record["answered_by"], record["model_id"]) == ("cancelled", None, None)


async def test_teardown_during_classification_sends_nothing_more_and_records_abandoned(tmp_path) -> None:
    class TearsDown:
        def __call__(self, contract: Any, stops: Any, call: Any) -> ClassifierOutcome:
            call.operation_control.request_transport_teardown()
            # A late receipt still lands in the turn's settlement after teardown.
            call.record_receipt(_receipt(call, "uncertain", None))
            return ClassifierOutcome(tier="easy", confidence_band="high", predicted_tier="easy", answered_by="classifier")

    adapter, outbound, runner, events, _ = _adapter(tmp_path, TearsDown())
    session_id = await new_session(adapter, tmp_path, mode="chat")
    outbound.notifications.clear()

    await prompt(adapter, outbound, session_id, "Hello?", "q1")

    assert runner.requests == [] and not any(text.startswith("Auto:") for text in texts(outbound))
    [record] = _records(events)
    assert (record["disposition"], record["classifier_attempt"], record["answered_by"]) == ("abandoned", "uncertain", "classifier")


def _tear_down(adapter: AcpDuplexAdapter, task: asyncio.Task) -> None:
    """The server's transport-loss order (`server.py`): mark each active turn torn down, then cancel the request task."""
    for turn in list(adapter._active_turns.values()):  # noqa: SLF001
        turn.turn_control.request_transport_teardown()
    task.cancel()


async def test_a_request_task_cancelled_during_classification_records_once_and_keeps_its_late_receipt(tmp_path) -> None:
    # Codex round 68: the real teardown cancels the request task while the classifier is still outstanding.
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    class Outstanding:
        def __call__(self, contract: Any, stops: Any, call: Any) -> ClassifierOutcome:
            entered.set()
            release.wait(5)
            call.record_receipt(_receipt(call, "uncertain", None))
            finished.set()
            return ClassifierOutcome(tier="easy", confidence_band="high", predicted_tier="easy", answered_by="classifier")

    adapter, outbound, runner, events, _ = _adapter(tmp_path, Outstanding())
    session_id = await new_session(adapter, tmp_path, mode="chat")
    task = asyncio.create_task(rpc(adapter, prompt_request(session_id, "Hello?", "q1")))
    assert await asyncio.to_thread(entered.wait, 5)

    _tear_down(adapter, task)
    with pytest.raises(asyncio.CancelledError):
        await task
    release.set()
    assert await asyncio.to_thread(finished.wait, 5)

    assert runner.requests == [] and not any(text.startswith("Auto:") for text in texts(outbound))
    [record] = _records(events)
    assert (record["disposition"], record["model_id"]) == ("abandoned", None)
    receipts = session_of(adapter, session_id).cost_settlement.receipts(f"{session_id}:1")
    assert [(r.stage, r.outcome) for r in receipts] == [("classification", "uncertain")], "the late receipt still settles"


async def test_a_request_task_cancelled_while_the_notice_waits_records_once(tmp_path) -> None:
    class Stalls(RecordingOutboundChannel):
        async def notify(self, method: str, params: dict[str, Any], *, require_flushed: bool = False) -> None:
            if params.get("update", {}).get("content", {}).get("text", "").startswith("Auto:"):
                await asyncio.Event().wait()
            await super().notify(method, params, require_flushed=require_flushed)

    adapter, outbound, runner, events, _ = _adapter(tmp_path, Classifier(["easy"]), outbound=Stalls())
    session_id = await new_session(adapter, tmp_path, mode="chat")
    task = asyncio.create_task(rpc(adapter, prompt_request(session_id, "Hello?", "q1")))
    for _ in range(200):
        turns = list(adapter._active_turns.values())  # noqa: SLF001
        if turns and turns[0].auto_decision is not None:
            break
        await asyncio.sleep(0.01)

    _tear_down(adapter, task)
    with pytest.raises(asyncio.CancelledError):
        await task

    assert runner.requests == []
    [record] = _records(events)
    assert (record["disposition"], record["model_id"], record["notice_delivered"]) == ("abandoned", LUNA, False)


async def test_a_cancel_after_the_record_is_written_adds_no_second_record(tmp_path) -> None:
    class StallsText(RecordingOutboundChannel):
        async def notify(self, method: str, params: dict[str, Any], *, require_flushed: bool = False) -> None:
            if params.get("update", {}).get("sessionUpdate") == "agent_message_chunk":
                await asyncio.Event().wait()
            await super().notify(method, params, require_flushed=require_flushed)

    adapter, outbound, runner, events, router = _adapter(tmp_path, Classifier(["complex"]), outbound=StallsText())
    router.stops.add(GEMINI)
    session_id = await new_session(adapter, tmp_path, mode="chat")
    task = asyncio.create_task(rpc(adapter, prompt_request(session_id, "Hello?", "q1")))
    for _ in range(200):
        if _records(events):
            break
        await asyncio.sleep(0.01)

    _tear_down(adapter, task)
    with pytest.raises(asyncio.CancelledError):
        await task

    [record] = _records(events)
    assert (record["disposition"], record["reason"]) == ("refused", "AUTO_NO_ROUTABLE_MODEL")


def _receipt(call: Any, outcome: str, cost: Decimal | None) -> StageReceipt:
    from datetime import UTC, datetime

    return StageReceipt(
        session_id=call.session_id, turn_id=call.run_id, stage="classification", attempt_id=f"{call.run_id}:classification:1:1",
        gateway_request_id=None if outcome != "completed" else "gw-c1", outcome=outcome, reported_cost_usd=cost, recorded_at=datetime.now(tz=UTC),
    )  # fmt: skip


async def test_classification_receipts_land_in_the_turns_settlement(tmp_path) -> None:
    class Paid:
        def __call__(self, contract: Any, stops: Any, call: Any) -> ClassifierOutcome:
            call.record_receipt(_receipt(call, "completed", Decimal("0.0000042")))
            return ClassifierOutcome(tier="medium", confidence_band="high", predicted_tier="medium", answered_by="classifier")

    adapter, outbound, runner, events, _ = _adapter(tmp_path, Paid())
    session_id = await new_session(adapter, tmp_path, mode="chat")

    await prompt(adapter, outbound, session_id, "Hello?", "q1")

    session = session_of(adapter, session_id)
    receipts = [r for r in session.cost_settlement.receipts(f"{session_id}:1") if r.stage == "classification"]
    assert [(r.outcome, r.reported_cost_usd) for r in receipts] == [("completed", Decimal("0.0000042"))]
    assert session.cost_settlement.settle_turn(f"{session_id}:1").known_subtotal_usd >= Decimal("0.0000042")
    [record] = _records(events)
    assert record["classifier_attempt"] == "completed"


async def test_two_concurrent_turns_each_leave_their_own_record(tmp_path) -> None:
    adapter, outbound, runner, events, _ = _adapter(tmp_path, Classifier(["easy", "complex"]))
    first, second = await new_session(adapter, tmp_path, mode="chat"), await new_session(adapter, tmp_path, mode="chat")
    await asyncio.gather(prompt(adapter, outbound, first, "One?", "a"), prompt(adapter, outbound, second, "Two?", "b"))
    assert sorted(record["tier"] for record in _records(events)) == ["complex", "easy"]
