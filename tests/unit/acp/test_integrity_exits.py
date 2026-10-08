"""Codex CP3 correction ruling C1 and C2: accounting-integrity exits keep the reported charge.

When the Gateway reports valid usage that names no single completed route attempt (a contract
violation), or a sink refuses a receipt, the run still fails loudly and is never retried, but the
reported charge is kept: in the existing ledger once, and in the session settlement as an
`unattributed` record whose cost counts while its turn stays incomplete. The route attempts are kept as
reported, unsettled; nothing is relabelled or invented. A crossed live threshold alerts once with the
retained facts; after transport teardown nothing live is sent. A replay never charges twice. A charge
only the existing ledger refuses keeps its turn incomplete too, and one raised error keeps the others
noted (Fable CP3 correction-2 review MINOR-1, NIT-1).

C1 is proved through the real ACP prompt, worker and finalization boundary with the real runner; C2
through the real GatewaySummarizerCall -> HostMaintenance -> attachment and ledger sinks, and through
an attached ACP turn. Each has a matched, attributable control.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import threading
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from context_engine import MaintenanceRequest
from context_engine.summary import PROMPT_VERSION, SECTIONS, SUMMARY_FORMAT
from optimus.acp.conversation import ConversationSanitizer, ConversationSanitizerInputs
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.agent.models import AgentRunRequest
from optimus.agent.runner import AgentRunner
from optimus.context.maintenance import (
    GatewaySummarizerCall,
    HostMaintenance,
    MaintenanceIdentity,
    SummarizerRoute,
    gateway_summarizer_factory,
)
from optimus.gateway.attempts import AttemptIntegrityError
from optimus.gateway.errors import GatewayHttpError
from optimus.gateway.models import GatewayResponse, GatewayRouteAttempt, GatewayUsage
from optimus.runtime.modes import ExecutionMode
from optimus.usage.accounting import UsageAccountingService
from optimus.usage.cost_alerts import AlertPolicy
from optimus.usage.errors import DuplicateGatewayRequestError
from optimus.usage.turn_settlement import ReceiptConflictError, StageReceipt, TurnSettlement, UsageLedgerAdapter, receipt_from_maintenance
from tests.unit.acp.test_context_engine_admission import make_attachment, new_session, prompt_request, rpc, texts

SUMMARY = "\n".join(f"## {name}\nNone." for name in SECTIONS)


def _usage(gateway_id: str = "gw-reported", cost: str = "0.004", **changes) -> GatewayUsage:
    return GatewayUsage(
        gateway_request_id=gateway_id, provider="fake", billing_units=3, input_tokens=2, output_tokens=1, cost_usd=Decimal(cost), **changes
    )


def _report(*, broken: bool, text: str = "A synthetic answer.", usage: GatewayUsage | None = None) -> GatewayResponse:
    usage = usage or _usage()
    named = "gw-other" if broken else usage.gateway_request_id
    attempts = (GatewayRouteAttempt(attempt=1, gateway_request_id=named, outcome="completed"),)
    return GatewayResponse(output_text=text, finish_reason="stop", raw={}, gateway_usage=usage, route_attempts=attempts)


class Gateway:
    """Synthetic replies in order (the last repeats); an exception in the list is raised."""

    def __init__(self, *replies) -> None:
        self.replies = list(replies)
        self.calls = 0

    def create_response(self, **kwargs):
        self.calls += 1
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, BaseException):
            raise reply
        return reply


def _adapter(tmp_path: Path, gateway, *, service: UsageAccountingService | None = None, scope: str = "turn", attachment=None):
    store, outbound = InMemoryAcpSpecSessionStore(), RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(
        runner=AgentRunner(gateway_client=gateway, model="fake/model", usage_accounting=service), workspace_root=tmp_path, sessions=store,
        outbound=outbound, alert_policies=(AlertPolicy(scope=scope, thresholds_usd=(Decimal("0.001"),)),), context_attachment=attachment,
    )  # fmt: skip
    return adapter, store, outbound


def _alerts(outbound) -> list[str]:
    return [text for text in texts(outbound) if text.startswith("Cost alert")]


def _state(session, run_id: str) -> dict:
    turn = session.cost_settlement.settle_turn(run_id)
    return {
        "settlement": (turn.known_subtotal_usd, turn.complete),
        "conversation": (session.conversation.known_cost_usd, session.conversation.cost_complete),
        "outcomes": sorted((r.outcome, r.gateway_request_id) for r in session.cost_settlement.receipts(run_id)),
    }


# --- C1: planning and Chat through the real ACP worker and finalization boundary --------------------------


@pytest.mark.parametrize("mode", ["agent", "chat"])
async def test_an_unattributable_report_keeps_its_charge_incomplete_and_alerts_once(tmp_path, mode) -> None:
    service, gateway = UsageAccountingService(), Gateway(_report(broken=True))
    adapter, store, outbound = _adapter(tmp_path, gateway, service=service)
    session_id = await new_session(adapter, tmp_path, mode=mode)

    with pytest.raises(AttemptIntegrityError):
        await rpc(adapter, prompt_request(session_id, "A question?", "p1"))

    session = store.get(session_id)
    assert gateway.calls == 1  # loud and terminal: never retried, nothing further dispatched
    assert _state(session, f"{session_id}:1") == {
        "settlement": (Decimal("0.004"), False),
        "conversation": (Decimal("0.004"), False),
        # The reported charge, unattributed; the route attempt as reported, unsettled. Nothing relabelled.
        "outcomes": [("unattributed", "gw-reported"), ("uncertain", "gw-other")],
    }
    assert [entry.gateway_request_id for entry in service.provider_ledger.entries] == ["gw-reported"]
    assert _alerts(outbound) == [
        "Cost alert: this turn's model costs have reached $0.001 (at least $0.004; some costs are unknown, so the total is incomplete)."
    ]
    assert session.cost_settlement.settle_turn(f"{session_id}:1").pending_invocations == 0


@pytest.mark.parametrize("mode", ["agent", "chat"])
async def test_the_matched_report_settles_complete_with_one_alert(tmp_path, mode) -> None:
    service, gateway = UsageAccountingService(), Gateway(_report(broken=False, text="WRITE a.py\nx" if mode == "agent" else "An answer."))
    adapter, store, outbound = _adapter(tmp_path, gateway, service=service)
    session_id = await new_session(adapter, tmp_path, mode=mode)

    task = asyncio.create_task(rpc(adapter, prompt_request(session_id, "A question?", "p1")))
    if mode == "agent":
        permission = await asyncio.wait_for(outbound.wait_for_request("session/request_permission"), timeout=5)
        outbound.respond(permission["id"], {"outcome": {"outcome": "cancelled"}})
    await asyncio.wait_for(task, timeout=5)

    session = store.get(session_id)
    assert _state(session, f"{session_id}:1") == {
        "settlement": (Decimal("0.004"), True),
        "conversation": (Decimal("0.004"), True),
        "outcomes": [("completed", "gw-reported")],
    }
    assert service.provider_ledger.total_cost_usd() == Decimal("0.004")
    assert len(_alerts(outbound)) == 1


@pytest.mark.parametrize("ledger", [False, True], ids=["settlement-refuses", "ledger-and-settlement-refuse"])
async def test_a_receipt_the_store_refuses_fails_loudly_and_never_reads_complete(tmp_path, ledger) -> None:
    """A real below-sink failure: the Gateway answers turn 2 with turn 1's request id and different
    settled facts. The settlement (and the ledger, when present) refuses it; the turn fails loudly, its
    accounting stays incomplete and the first charge is never doubled."""
    service = UsageAccountingService() if ledger else None
    gateway = Gateway(_report(broken=False), _report(broken=False, usage=_usage(cost="0.005")))
    adapter, store, _ = _adapter(tmp_path, gateway, service=service, scope="session")
    session_id = await new_session(adapter, tmp_path, mode="chat")
    await rpc(adapter, prompt_request(session_id, "First?", "p1"))

    with pytest.raises((ReceiptConflictError, DuplicateGatewayRequestError)):
        await rpc(adapter, prompt_request(session_id, "Second?", "p2"))

    session = store.get(session_id)
    turn = session.cost_settlement.settle_turn(f"{session_id}:2")
    assert (turn.known_subtotal_usd, turn.complete) == (Decimal("0"), False)
    assert turn.integrity_failures == (2 if ledger else 1)  # the settlement's refusal, and the ledger's
    assert (session.conversation.known_cost_usd, session.conversation.cost_complete) == (Decimal("0.004"), False)
    if service is not None:
        assert service.provider_ledger.total_cost_usd() == Decimal("0.004")


async def test_an_unattributable_report_after_teardown_is_kept_and_nothing_live_is_sent(tmp_path) -> None:
    entered, release = threading.Event(), threading.Event()

    class BlockedGateway:
        def create_response(self, **kwargs):
            entered.set()
            if not release.wait(5):
                raise AssertionError("never released")
            return _report(broken=True)

    adapter, store, outbound = _adapter(tmp_path, BlockedGateway())
    session_id = await new_session(adapter, tmp_path, mode="chat")
    session = store.get(session_id)
    ended = threading.Event()
    session.cost_settlement.subscribe(lambda turn_id, summary: ended.set() if summary.receipt_ids and not summary.pending_invocations else None)

    task = asyncio.create_task(rpc(adapter, prompt_request(session_id, "A question?", "p1")))
    assert await asyncio.to_thread(entered.wait, 5)
    adapter._active_turns[session_id].turn_control.request_transport_teardown()  # noqa: SLF001
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    sent = len(outbound.notifications)
    release.set()
    assert await asyncio.to_thread(ended.wait, 5)

    assert _state(session, f"{session_id}:1")["settlement"] == (Decimal("0.004"), False)
    assert all(r.post_teardown for r in session.cost_settlement.receipts(f"{session_id}:1"))
    assert len(outbound.notifications) == sent


def _ledger_holding_other_facts() -> UsageAccountingService:
    """An existing ledger that already holds `gw-reported` with other facts (another run's record)."""
    service = UsageAccountingService()
    service.record_gateway_usage(
        _usage(cost="0.009"), run_id="other:1", session_id="other", request_id="other:1:planning:1:1",
        occurred_at=datetime(2026, 10, 3, tzinfo=UTC), service="agent.model", native_unit="tokens",
    )  # fmt: skip
    return service


@pytest.mark.parametrize("mode", ["agent", "chat"])
async def test_a_charge_only_the_ledger_refuses_keeps_the_turn_incomplete(tmp_path, mode) -> None:
    """Fable CP3 correction-2 review MINOR-1: the ledger refuses the charge (its Gateway request id is
    already recorded with other facts) while the session's settlement, which has no conflicting owner,
    accepts it. The turn fails loudly and never reads complete; the ledger's own record stands."""
    service = _ledger_holding_other_facts()
    gateway = Gateway(_report(broken=False, text="WRITE a.py\nx" if mode == "agent" else "An answer."))
    adapter, store, outbound = _adapter(tmp_path, gateway, service=service)
    session_id = await new_session(adapter, tmp_path, mode=mode)

    with pytest.raises(DuplicateGatewayRequestError):
        await rpc(adapter, prompt_request(session_id, "A question?", "p1"))

    session = store.get(session_id)
    turn = session.cost_settlement.settle_turn(f"{session_id}:1")
    assert gateway.calls == 1
    assert (turn.known_subtotal_usd, turn.complete, turn.integrity_failures) == (Decimal("0.004"), False, 1)
    assert (session.conversation.known_cost_usd, session.conversation.cost_complete) == (Decimal("0.004"), False)
    assert service.provider_ledger.total_cost_usd() == Decimal("0.009")
    [alert] = _alerts(outbound)
    assert "at least $0.004" in alert  # incomplete wording, never "(now $0.004)"


@pytest.mark.parametrize("mode", [ExecutionMode.AGENT, ExecutionMode.CHAT, ExecutionMode.PLAN], ids=["planning", "chat", "plan"])
def test_every_runner_path_reports_a_ledger_refusal_to_its_turn(tmp_path, mode) -> None:
    """The multi-turn planning loop, Chat and the single-shot PLAN path all record through the runner's
    one ledger entry point, which tells the run's settlement of a refusal."""
    settlement = TurnSettlement()
    request = AgentRunRequest(run_id="s:1", session_id="s", task="Change it.", workspace_root=tmp_path, execution_mode=mode)
    runner = AgentRunner(gateway_client=Gateway(_report(broken=False, text="WRITE a.py\nx")), model="fake/model", usage_accounting=_ledger_holding_other_facts())

    with pytest.raises(DuplicateGatewayRequestError):
        runner.run(request, stage_receipts=settlement.record_attempt, integrity_failure=settlement.record_integrity_failure)

    turn = settlement.settle_turn("s:1")
    assert (turn.known_subtotal_usd, turn.complete, turn.integrity_failures) == (Decimal("0.004"), False, 1)


def test_one_raised_accounting_error_keeps_the_others_noted(tmp_path) -> None:
    """Fable CP3 correction-2 review NIT-1: every held accounting error is noted (by type) on the one
    raised, on the runner and on the summary path."""
    settlement = TurnSettlement()
    request = AgentRunRequest(run_id="s:1", session_id="s", task="A question?", workspace_root=tmp_path, execution_mode=ExecutionMode.CHAT)
    runner = AgentRunner(gateway_client=Gateway(_report(broken=True)), model="fake/model", usage_accounting=_ledger_holding_other_facts())

    with pytest.raises(DuplicateGatewayRequestError) as raised:
        runner.run(request, stage_receipts=settlement.record_attempt, integrity_failure=settlement.record_integrity_failure)

    assert raised.value.__notes__ == ["accounting also failed: AttemptIntegrityError"]
    turn = settlement.settle_turn("s:1")
    assert (turn.known_subtotal_usd, turn.complete, turn.integrity_failures) == (Decimal("0.004"), False, 2)

    def refusing(receipt) -> None:
        raise ReceiptConflictError("already settled differently")

    host = HostMaintenance(
        call=GatewaySummarizerCall(gateway_client=Gateway(_report(broken=True, text=SUMMARY)), model_id="fake", session_id="s", request_ids=lambda: "r"),
        sanitizer=ConversationSanitizer(ConversationSanitizerInputs((), ())), identity=IDENTITY, record_receipt=refusing, cancelled=lambda: False,
    )  # fmt: skip
    with pytest.raises(ReceiptConflictError) as refused:
        host(REQUEST)
    assert "accounting also failed: AttemptIntegrityError" in refused.value.__notes__


def test_a_replay_or_later_reconciliation_never_charges_twice() -> None:
    settlement = TurnSettlement()
    unattributed = StageReceipt(
        session_id="s", turn_id="s:1", stage="answer", attempt_id="s:1:answer:1:1:usage", gateway_request_id="gw-reported",
        outcome="unattributed", reported_cost_usd=Decimal("0.004"), recorded_at=datetime(2026, 10, 3, tzinfo=UTC), gateway_usage=_usage(),
    )  # fmt: skip
    settlement.record_attempt(unattributed)
    settlement.record_attempt(unattributed)  # replay: identical, nothing added

    reconciled = dataclasses.replace(unattributed, attempt_id="s:1:answer:2:1:1", outcome="completed")
    with pytest.raises(ReceiptConflictError):
        settlement.record_attempt(reconciled)  # a later "reconciliation" of the same request

    turn = settlement.settle_turn("s:1")
    assert (turn.known_subtotal_usd, turn.complete) == (Decimal("0.004"), False)


# --- C2: summaries through GatewaySummarizerCall -> HostMaintenance -> attachment and ledger ----------------

IDENTITY = MaintenanceIdentity(
    session_id="s", turn_seq=1, model_id="fake", role="summarizer", route=("fake",), reasoning=None, quantizations=(None,),
    strategy="compaction", revision_digest="a" * 64,
)  # fmt: skip
REQUEST = MaintenanceRequest(
    input_text="ordinary synthetic history", covered_turn_ids=(1,), max_output_tokens=100, prompt_version=PROMPT_VERSION, format_version=SUMMARY_FORMAT
)
TYPED_FAILURE = GatewayHttpError(
    422, "x", gateway_code="FINISH_STATUS_UNVERIFIED", retryable=False, gateway_usage=_usage(),
    route_attempts=(GatewayRouteAttempt(attempt=1, gateway_request_id="gw-other", outcome="completed"),),
)  # fmt: skip


def _summarize(gateway, *, cancelled_after: bool = False, settlement: TurnSettlement | None = None, service: UsageAccountingService | None = None):
    settlement = settlement if settlement is not None else TurnSettlement()
    service = service if service is not None else UsageAccountingService()
    ledger, rows, calls = UsageLedgerAdapter(service), [], {"n": 0}

    def record(receipt) -> None:
        rows.append(receipt)
        ledger.record_maintenance(receipt)
        settlement.record_attempt(receipt_from_maintenance(receipt))

    def cancelled() -> bool:
        calls["n"] += 1
        return cancelled_after and calls["n"] > 1

    host = HostMaintenance(
        call=GatewaySummarizerCall(gateway_client=gateway, model_id="fake", session_id="s", request_ids=lambda: "summary-r"),
        sanitizer=ConversationSanitizer(ConversationSanitizerInputs((), ())), identity=IDENTITY, record_receipt=record, cancelled=cancelled,
    )  # fmt: skip
    error = None
    try:
        result = host(REQUEST)
    except AttemptIntegrityError as exc:
        error, result = exc, None
    return error, result, rows, settlement, service


@pytest.mark.parametrize(
    ("reply", "cancelled_after"),
    [(_report(broken=True, text=SUMMARY), False), (TYPED_FAILURE, False), (_report(broken=True, text=SUMMARY), True)],
    ids=["success-response", "typed-failure-with-usage", "cancelled-after-the-call"],
)
def test_an_unattributable_summary_report_keeps_its_charge_once_and_publishes_nothing(reply, cancelled_after) -> None:
    gateway = Gateway(reply)

    error, result, rows, settlement, service = _summarize(gateway, cancelled_after=cancelled_after)

    assert isinstance(error, AttemptIntegrityError) and result is None  # loud; no summary to publish or reuse
    assert gateway.calls == 1
    assert sorted((r.outcome, r.gateway_request_id) for r in rows) == [("unattributed", "gw-reported"), ("uncertain", "gw-other")]
    assert [e.gateway_request_id for e in service.provider_ledger.entries] == ["gw-reported"]
    summary = settlement.settle_turn("s:1")
    assert (summary.known_subtotal_usd, summary.complete) == (Decimal("0.004"), False)
    unattributed = next(r for r in rows if r.outcome == "unattributed")
    assert unattributed.gateway_usage == _usage() and unattributed.identity == IDENTITY


def test_a_replayed_unattributable_summary_report_is_recorded_once() -> None:
    settlement, service = TurnSettlement(), UsageAccountingService()

    for _ in range(2):
        error, *_ = _summarize(Gateway(_report(broken=True, text=SUMMARY)), settlement=settlement, service=service)
        assert isinstance(error, AttemptIntegrityError)

    assert len(service.provider_ledger.entries) == 1
    assert settlement.settle_turn("s:1").known_subtotal_usd == Decimal("0.004")


def test_the_matched_summary_report_settles_complete() -> None:
    error, result, rows, settlement, service = _summarize(Gateway(_report(broken=False, text=SUMMARY)))

    assert error is None and result.status == "completed"
    assert [(r.outcome, r.cost_usd) for r in rows] == [("completed", Decimal("0.004"))]
    assert settlement.settle_turn("s:1").complete and service.provider_ledger.total_cost_usd() == Decimal("0.004")


def test_a_ledger_refusal_never_keeps_the_charge_out_of_the_settlement() -> None:
    """The attached turn offers each summary receipt to both sinks; a refusing ledger is raised after the
    settlement has recorded the charge."""
    from optimus.acp.conversation import ConversationOutcome, ConversationTurn
    from optimus.acp.settlement import EffectState
    from optimus.context.assembly import AttachedTurn

    def refusing_ledger(receipt) -> None:
        raise DuplicateGatewayRequestError("gw-reported")

    settlement = TurnSettlement()
    call = GatewaySummarizerCall(gateway_client=Gateway(_report(broken=False, text=SUMMARY)), model_id="m", session_id="s", request_ids=lambda: "r")
    attachment = dataclasses.replace(make_attachment(tail=10), summarizer=lambda identity, deliver: call, record_receipt=refusing_ledger)
    records = {seq: ConversationTurn(f"q{seq} " + "w " * 200, "", "a " * 200, ConversationOutcome.COMPLETED, EffectState.NONE) for seq in (1, 2, 3)}
    turn = AttachedTurn.capture(
        attachment=attachment, session_key="s", records=records, approvals={}, generation=3,
        sanitizer=ConversationSanitizer(ConversationSanitizerInputs((), ())), strategy="compaction", mode=ExecutionMode.CHAT, checkpoint=None,
        current_prompt="now", turn_seq=4, cancelled=lambda: False,
        record_receipt=lambda receipt: settlement.record_attempt(receipt_from_maintenance(receipt)),
        record_integrity_failure=lambda receipt: settlement.record_integrity_failure(receipt_from_maintenance(receipt).turn_id),
    )  # fmt: skip

    with pytest.raises(DuplicateGatewayRequestError):
        turn.prepare()

    summary = settlement.settle_turn("s:4")
    assert (summary.known_subtotal_usd, summary.complete, summary.integrity_failures) == (Decimal("0.004"), False, 1)


async def test_an_attached_turns_unattributable_summary_is_kept_and_alerted_through_the_acp_host(tmp_path) -> None:
    service = UsageAccountingService()

    class Summarizing(Gateway):
        def create_response(self, *, model, input_text, metadata=None, **kwargs):
            self.calls += 1
            if metadata.get("purpose") == "context_summary":
                return _report(broken=True, text=SUMMARY, usage=_usage("gw-summary"))
            return _report(broken=False, usage=_usage(f"gw-answer-{self.calls}", cost="0.0001"))

    gateway = Summarizing(None)
    route = SummarizerRoute(model_id="test/summarizer", role="summarizer", route=("provider-a",), reasoning=None, quantizations=("fp8",))
    attachment = dataclasses.replace(
        make_attachment(tail=10), summarizer=gateway_summarizer_factory(gateway_client=gateway, route=route, snapshot=None, disclosure_key=None),
        summarizer_route=route, record_receipt=UsageLedgerAdapter(service).record_maintenance,
    )  # fmt: skip
    adapter, store, outbound = _adapter(tmp_path, gateway, service=service, attachment=attachment)
    session_id = await new_session(adapter, tmp_path, mode="chat")

    raised = None
    for n in range(6):
        try:
            await rpc(adapter, prompt_request(session_id, f"Question {n}: " + "words " * 30, f"p{n}"))
        except AttemptIntegrityError:
            raised = n + 1
            break

    assert raised is not None  # the turn that needed a summary failed loudly
    session = store.get(session_id)
    run_id = f"{session_id}:{raised}"
    assert sorted(r.outcome for r in session.cost_settlement.receipts(run_id)) == ["unattributed", "uncertain"]  # no answer was dispatched
    assert session.cost_settlement.settle_turn(run_id).known_subtotal_usd == Decimal("0.004")
    assert session.conversation.cost_complete is False
    assert "gw-summary" in service.provider_ledger.gateway_request_ids()
    assert any("at least $0.004" in alert for alert in _alerts(outbound))


async def test_an_attached_turns_summary_charge_the_ledger_refuses_is_kept_incomplete_through_the_acp_host(tmp_path) -> None:
    class Summarizing(Gateway):
        def create_response(self, *, model, input_text, metadata=None, **kwargs):
            self.calls += 1
            if metadata.get("purpose") == "context_summary":
                return _report(broken=False, text=SUMMARY, usage=_usage("gw-summary"))
            return _report(broken=False, usage=_usage(f"gw-answer-{self.calls}", cost="0.0001"))

    def refusing_ledger(receipt) -> None:
        raise DuplicateGatewayRequestError(receipt.gateway_request_id)

    gateway = Summarizing(None)
    route = SummarizerRoute(model_id="test/summarizer", role="summarizer", route=("provider-a",), reasoning=None, quantizations=("fp8",))
    attachment = dataclasses.replace(
        make_attachment(tail=10), summarizer=gateway_summarizer_factory(gateway_client=gateway, route=route, snapshot=None, disclosure_key=None),
        summarizer_route=route, record_receipt=refusing_ledger,
    )  # fmt: skip
    adapter, store, outbound = _adapter(tmp_path, gateway, attachment=attachment)
    session_id = await new_session(adapter, tmp_path, mode="chat")

    raised = None
    for n in range(6):
        try:
            await rpc(adapter, prompt_request(session_id, f"Question {n}: " + "words " * 30, f"p{n}"))
        except DuplicateGatewayRequestError:
            raised = n + 1
            break

    assert raised is not None  # the turn that needed a summary failed loudly
    session = store.get(session_id)
    run_id = f"{session_id}:{raised}"
    assert [r.gateway_request_id for r in session.cost_settlement.receipts(run_id)] == ["gw-summary"]  # no answer was dispatched
    turn = session.cost_settlement.settle_turn(run_id)
    assert (turn.known_subtotal_usd, turn.complete, turn.integrity_failures) == (Decimal("0.004"), False, 1)
    assert session.conversation.cost_complete is False
    assert any("at least $0.004" in alert for alert in _alerts(outbound))
