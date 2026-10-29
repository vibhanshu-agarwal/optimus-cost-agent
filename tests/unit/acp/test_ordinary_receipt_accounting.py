"""Plan 12.2 closure (Codex 6249427656): the ordinary attachment's receipt-first accounting.

The ordinary attachment's attachment-level ledger callback is a no-op (``no_attachment_ledger``); every
summarization receipt must still reach the turn's session settlement, through the per-turn sink the adapter
captures. These tests drive the real ordinary composition (the shipped registry, the plain engine, Haiku 5.5's
summarizer route through the real ``GatewayClient``) on a scripted transport, with a fake answer runner:

- a charged failure keeps its known cost and the turn stays complete;
- a transport loss keeps the attempt with an unknown cost and the turn never reads complete;
- a cancel during maintenance still settles the attempt, publishes nothing and dispatches no answer.

The shared route stop: Haiku 5.5 is both the default planner and the summarizer on the one shipped experimental
route, so a refused reply on either stops the other in that Gateway process, before the provider, at no cost.
"""

from __future__ import annotations

import asyncio
import threading
from decimal import Decimal
from typing import Any

import pytest

import optimus_gateway.responses as gateway_responses
from optimus.acp.context_attachment import ordinary_attachment, ordinary_route_policy
from optimus.acp.spec import CONTEXT_FALLBACK_TEXT
from optimus.agent.runner import CHAT_ROUTE_STOPPED_MESSAGES, AgentRunner
from optimus.context.maintenance import MaintenanceIdentity
from optimus.gateway.errors import GatewayHttpError
from optimus.gateway.models import GatewayUsage
from optimus.runtime.modes import ExecutionMode
from optimus.usage.turn_settlement import StageReceipt
from optimus_model_policy.binding import trusted_snapshot
from tests.unit.acp.test_context_engine_admission import SUMMARY, make_adapter, new_session, prompt, prompt_request, rpc, session_of, texts
from tests.unit.acp.test_ordinary_compaction_flow import HAIKU, SECRET, _client, synthetic_notes
from tests.unit.agent.test_route_binding import InProcessGateway, _request
from tests.unit.agent.test_route_binding import _client as _gateway_client
from tests.unit.optimus_gateway.model_policy_support import SHARED_SECRET, RecordingUpstream

COST = Decimal("0.0035")


class ScriptedTransport:
    """A fake Gateway transport for summary requests: each request takes the next scripted behaviour."""

    def __init__(self, behaviours: list[str], *, entered: threading.Event | None = None, release: threading.Event | None = None) -> None:
        self.behaviours = list(behaviours)
        self.requests: list[Any] = []
        self.entered, self.release = entered, release

    def post_json(self, request: Any) -> dict[str, Any]:
        self.requests.append(request)
        n = len(self.requests)
        behaviour = self.behaviours.pop(0) if self.behaviours else "ok"
        if behaviour == "block":
            assert self.entered is not None and self.release is not None
            self.entered.set()
            assert self.release.wait(5)
            behaviour = "ok"
        usage = {"gateway_request_id": f"gw-s{n}", "provider": "openrouter", "billing_units": 1, "cost_usd": str(COST)}
        if behaviour == "charged-failure":
            raise GatewayHttpError(
                502, "failed", gateway_usage=GatewayUsage(gateway_request_id=f"gw-s{n}", provider="openrouter", billing_units=1, cost_usd=COST)
            )
        if behaviour == "lost":
            raise ConnectionResetError("reset after send")
        return {"output_text": SUMMARY, "finish_reason": "stop", "gateway_usage": usage}


async def _two_notes_then(tmp_path, transport: ScriptedTransport):
    snapshot = trusted_snapshot()
    assert snapshot is not None
    attachment = ordinary_attachment(snapshot=snapshot, model_id=HAIKU, gateway_client=_client(transport), shared_secret=SECRET)
    assert attachment is not None
    adapter, outbound, runner = make_adapter(tmp_path, attachment)
    session_id = await new_session(adapter, tmp_path, mode="chat")
    for n in (1, 2):
        await prompt(adapter, outbound, session_id, synthetic_notes(n) + "\n\nReply with OK only.", f"notes-{n}")
    assert transport.requests == [], "the first two turns need no maintenance"
    return adapter, outbound, runner, session_id


def _summary_receipts(adapter, session_id: str) -> tuple[list[StageReceipt], str]:
    session = session_of(adapter, session_id)
    turn_id = f"{session_id}:{max(session.conversation.records)}"
    return [r for r in session.cost_settlement.receipts(turn_id) if r.stage == "summarization"], turn_id


async def test_a_charged_maintenance_failure_keeps_its_cost_in_the_turns_settlement(tmp_path) -> None:
    transport = ScriptedTransport(["charged-failure"])
    adapter, outbound, runner, session_id = await _two_notes_then(tmp_path, transport)
    outbound.notifications.clear()

    response = await prompt(adapter, outbound, session_id, "What release code name was chosen in the first planning notes?", "question")

    receipts, turn_id = _summary_receipts(adapter, session_id)
    assert len(receipts) == len(transport.requests) >= 1, "every attempt reached the session settlement"
    assert [(r.outcome, r.reported_cost_usd) for r in receipts][0] == ("completed", COST)
    summary = session_of(adapter, session_id).cost_settlement.settle_turn(turn_id)
    assert summary.known_subtotal_usd == sum((r.reported_cost_usd for r in receipts), Decimal("0")) and summary.complete
    # The engine was unavailable, so the stated fallback answered from the full history (within the floor).
    assert response["result"]["stopReason"] == "end_turn"
    assert CONTEXT_FALLBACK_TEXT.format(strategy="compaction") in texts(outbound)


async def test_a_lost_maintenance_attempt_is_unknown_and_the_turn_never_reads_complete(tmp_path) -> None:
    transport = ScriptedTransport(["lost"])
    adapter, outbound, runner, session_id = await _two_notes_then(tmp_path, transport)

    await prompt(adapter, outbound, session_id, "What release code name was chosen in the first planning notes?", "question")

    receipts, turn_id = _summary_receipts(adapter, session_id)
    assert len(receipts) == len(transport.requests) >= 1
    assert (receipts[0].outcome, receipts[0].reported_cost_usd) == ("uncertain", None)
    summary = session_of(adapter, session_id).cost_settlement.settle_turn(turn_id)
    assert receipts[0].attempt_id in summary.unknown_attempt_ids and not summary.complete


async def test_a_cancel_during_ordinary_maintenance_still_settles_the_attempt(tmp_path) -> None:
    entered, release = threading.Event(), threading.Event()
    transport = ScriptedTransport(["block"], entered=entered, release=release)
    adapter, outbound, runner, session_id = await _two_notes_then(tmp_path, transport)
    session = session_of(adapter, session_id)
    checkpoint_before, answers_before = session.context_checkpoint, len(runner.requests)
    records_before = dict(session.conversation.records)
    turn_id = f"{session_id}:{session.conversation.next_turn_seq}"

    task = asyncio.create_task(rpc(adapter, prompt_request(session_id, "What release code name was chosen?", "c1")))
    assert await asyncio.to_thread(entered.wait, 5)
    await adapter.handle_client_notification({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": session_id}})
    release.set()
    response = await asyncio.wait_for(task, timeout=5)

    assert response["result"]["stopReason"] == "cancelled"
    assert len(runner.requests) == answers_before, "no answer is dispatched"
    assert session.context_checkpoint is checkpoint_before, "nothing is published"
    receipts = [r for r in session.cost_settlement.receipts(turn_id) if r.stage == "summarization"]
    assert [(r.outcome, r.reported_cost_usd) for r in receipts] == [("completed", COST)], "the attempt still settles"
    assert session.cost_settlement.settle_turn(turn_id).known_subtotal_usd == COST
    assert session.conversation.records == records_before, "the paid attempt settles independently of history"


# --- The shared route stop ------------------------------------------------------------------------------------


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gateway_responses, "_sleep", lambda _seconds: None)


class HaikuReplies(RecordingUpstream):
    """Completed replies with router evidence: the expected provider, or another one (a failed check)."""

    def __init__(self, providers: list[str]) -> None:
        super().__init__()
        self.providers = list(providers)

    def _result(self, model: str):
        from optimus_gateway.upstream_client import ProviderMessageResult

        base = super()._result(model)
        provider = self.providers.pop(0) if len(self.providers) > 1 else self.providers[0]
        evidence = {"resolved_provider": provider, "router_attempt": 1, "router_pipeline": (), "input_tokens": 1}
        return ProviderMessageResult(**{**base.__dict__, **evidence})


def _shipped_gateway(providers: list[str]) -> InProcessGateway:
    shipped = trusted_snapshot()
    assert shipped is not None
    gateway = InProcessGateway(shipped, HaikuReplies(providers))  # type: ignore[arg-type]
    return gateway


def _summarize(gateway: InProcessGateway):
    shipped = trusted_snapshot()
    assert shipped is not None
    attachment = ordinary_attachment(snapshot=shipped, model_id=HAIKU, gateway_client=_gateway_client(gateway), shared_secret=SHARED_SECRET)
    assert attachment is not None
    route = attachment.summarizer_route
    identity = MaintenanceIdentity(
        session_id="s", turn_seq=3, model_id=route.model_id, role=route.role, route=route.route, reasoning=route.reasoning,
        quantizations=route.quantizations, strategy="compaction", revision_digest="r", registry_hash=shipped.effective_hash,
    )  # fmt: skip
    return attachment.summarizer(identity, lambda text: True)(prompt="Summarize the notes.", max_output_tokens=8_192)


def _answer(gateway: InProcessGateway, tmp_path):
    shipped = trusted_snapshot()
    assert shipped is not None
    binder = ordinary_route_policy(snapshot=shipped, model_id=HAIKU, shared_secret=SHARED_SECRET).capture(session_id="s", turn_seq=3, deliver_notice=lambda text: True)
    receipts: list[StageReceipt] = []
    result = AgentRunner(gateway_client=_gateway_client(gateway), model=HAIKU).run(
        _request(tmp_path, ExecutionMode.CHAT, task="A question?"), stage_receipts=receipts.append, route_binder=binder
    )
    return result, receipts


@pytest.mark.usefixtures("no_sleep")
def test_a_refused_summary_reply_stops_the_answer_on_the_shared_route(tmp_path) -> None:
    gateway = _shipped_gateway(["Google"])  # the summary's reply names another provider: a failed check

    summary = _summarize(gateway)
    assert summary.text is None and [(a.outcome, a.cost_usd is not None) for a in summary.attempts] == [("completed", True)], "billed, kept"

    result, receipts = _answer(gateway, tmp_path)

    assert len(gateway.upstream.calls) == 1, "the answer never reached the provider"
    assert gateway.replies[-1][1]["code"] == "EMPIRICAL_ROUTE_STOPPED"
    assert [(r.outcome, r.reported_cost_usd) for r in receipts] == [("rejected", Decimal("0"))]
    assert (result.stop_reason, result.output_text) == ("CHAT_GATEWAY_REFUSED", CHAT_ROUTE_STOPPED_MESSAGES["CHAT_GATEWAY_REFUSED"])


@pytest.mark.usefixtures("no_sleep")
def test_a_refused_answer_reply_stops_every_later_summary_on_the_shared_route(tmp_path) -> None:
    gateway = _shipped_gateway(["Google"])

    result, _ = _answer(gateway, tmp_path)
    assert (result.stop_reason, result.output_text) == ("CHAT_GATEWAY_FAILURE", CHAT_ROUTE_STOPPED_MESSAGES["CHAT_GATEWAY_FAILURE"])

    summary = _summarize(gateway)

    assert len(gateway.upstream.calls) == 1, "the summary never reached the provider"
    assert gateway.replies[-1][1]["code"] == "EMPIRICAL_ROUTE_STOPPED"
    assert summary.text is None and [(a.outcome, a.cost_usd) for a in summary.attempts] == [("rejected", Decimal("0"))]
