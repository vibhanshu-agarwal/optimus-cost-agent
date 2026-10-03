"""Codex CP3 ruling R2, M2 and N1, at the ACP host.

R2: a turn's conversation cost is one receipt-derived projection. It is idempotent, never debits twice,
keeps updating after the turn's terminal finalization (a worker left behind by transport teardown can
still report), and is incomplete while such a worker still runs. A live exception exit reports its
cost alerts once, in that turn; after teardown nothing live is sent, and the facts stay settled.

M2: an attached view that was not built leaves one content-free operator line: run id, phase and a
bounded category - never exception text, history, summary, credential or the engine's reason.

N1: a Contributor notice that is not confirmed within the finite wait sends nothing, its pending send
is cancelled, and a late completion is never counted.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import re
import threading
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

import optimus.acp.spec as spec_module
from context_engine import PreparedView
from context_engine.engine import ContextEngine
from optimus.acp.conversation import ConversationSanitizer, ConversationSanitizerInputs, ConversationState
from optimus.acp.errors import AcpOutboundError
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.agent.models import AgentRunResult, AgentRunStatus
from optimus.agent.runner import AgentRunner
from optimus.gateway.disclosure import CONTRIBUTOR_NOTICE
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.runtime.modes import ExecutionMode
from optimus.usage.cost_alerts import AlertPolicy
from optimus.usage.turn_settlement import StageReceipt, TurnSettlement
from tests.unit.acp.test_context_engine_admission import (
    SummarizerCall,
    make_adapter,
    make_attachment,
    new_session,
    prompt,
    prompt_request,
    rpc,
    session_of,
    texts,
)
from tests.unit.acp.test_context_notices import DispatchingRunner, _contributor_attachment, _ObservingClient

AT = datetime(2026, 10, 3, tzinfo=UTC)


def receipt(attempt: str, cost: str | None, *, turn: str = "s:1", stage: str = "answer", gateway: str | None = None) -> StageReceipt:
    known = cost is not None
    return StageReceipt(
        session_id="s", turn_id=turn, stage=stage, attempt_id=attempt, gateway_request_id=gateway or (f"gw-{attempt}" if known else None),
        outcome="completed" if known else "uncertain", reported_cost_usd=Decimal(cost) if known else None, recorded_at=AT,
    )  # fmt: skip


def conversation() -> ConversationState:
    return ConversationState(ConversationSanitizer(ConversationSanitizerInputs((), ())))


def bound_session() -> SimpleNamespace:
    """A session whose conversation follows its settlement, as `AcpSpecSession` wires it."""
    session = SimpleNamespace(conversation=conversation(), cost_settlement=TurnSettlement())
    session.cost_settlement.subscribe(
        lambda turn_id, summary: session.conversation.project_turn_cost(turn_id, known_usd=summary.known_subtotal_usd, complete=summary.complete)
    )
    return session


TURN = SimpleNamespace(run_id="s:1", turn_seq=1)


# --- The projection ------------------------------------------------------------------------------------


def test_receipts_after_an_empty_finalization_still_reach_the_projection() -> None:
    session = SimpleNamespace(conversation=conversation(), cost_settlement=TurnSettlement())
    AcpDuplexAdapter._apply_settled_cost(session, TURN)

    session.cost_settlement.record_attempt(receipt("late", "0.004"))
    AcpDuplexAdapter._apply_settled_cost(session, TURN)

    assert (session.conversation.known_cost_usd, session.conversation.cost_complete) == (Decimal("0.004"), True)


@pytest.mark.parametrize("cost", ["0.004", None], ids=["known", "unknown"])
def test_a_subscribed_projection_follows_each_late_receipt_on_its_own(cost) -> None:
    session = bound_session()
    AcpDuplexAdapter._apply_settled_cost(session, TURN)  # the turn's terminal finalization: nothing yet

    session.cost_settlement.record_attempt(receipt("late", cost))

    expected = (Decimal(cost), True) if cost else (Decimal("0"), False)
    assert (session.conversation.known_cost_usd, session.conversation.cost_complete) == expected


def test_known_costs_before_and_after_an_unknown_all_count() -> None:
    session = bound_session()
    for attempt, cost in (("a", "0.001"), ("b", None), ("c", "0.002")):
        session.cost_settlement.record_attempt(receipt(attempt, cost))

    assert (session.conversation.known_cost_usd, session.conversation.cost_complete) == (Decimal("0.003"), False)
    assert session.conversation.usage_gauge().cost is None  # an incomplete total is never shown as the total


def test_a_replayed_receipt_and_a_repeated_projection_never_debit_twice() -> None:
    session = bound_session()
    first = receipt("a", "0.002")
    session.cost_settlement.record_attempt(first)
    session.cost_settlement.record_attempt(first)
    session.cost_settlement.record_attempt(dataclasses.replace(first, recorded_at=datetime(2026, 10, 4, tzinfo=UTC)))
    for _ in range(3):
        AcpDuplexAdapter._apply_settled_cost(session, TURN)

    assert session.conversation.known_cost_usd == Decimal("0.002")


def test_a_running_worker_keeps_its_turn_incomplete_until_it_ends() -> None:
    session = bound_session()
    invocation = session.cost_settlement.open_invocation("s:1")
    assert session.conversation.cost_complete is False  # it may still be billed

    assert invocation.start() is True
    session.cost_settlement.record_attempt(receipt("a", "0.002"))
    assert (session.conversation.known_cost_usd, session.conversation.cost_complete) == (Decimal("0.002"), False)

    invocation.end()
    assert session.conversation.cost_complete is True


def test_a_worker_that_never_started_can_never_start_later() -> None:
    session = bound_session()
    invocation = session.cost_settlement.open_invocation("s:1")

    invocation.abandon_unstarted()

    assert session.conversation.cost_complete is True
    assert invocation.start() is False
    invocation.end()  # a no-op: it never started
    assert session.cost_settlement.settle_turn("s:1").pending_invocations == 0


def test_concurrent_receipts_leave_the_projection_equal_to_the_settlement() -> None:
    session = bound_session()
    barrier = threading.Barrier(8)

    def record(n: int) -> None:
        barrier.wait(5)
        for k in range(25):
            session.cost_settlement.record_attempt(receipt(f"{n}-{k}", "0.001"))
            AcpDuplexAdapter._apply_settled_cost(session, TURN)

    threads = [threading.Thread(target=record, args=(n,), name=f"recorder-{n}") for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
        assert not thread.is_alive(), thread.name

    assert session.conversation.known_cost_usd == session.cost_settlement.settle_turn("s:1").known_subtotal_usd == Decimal("0.200")


# --- The real ACP cancellation and worker boundary ------------------------------------------------------


class _Lost(Exception):
    pass


@pytest.mark.parametrize("late", ["known", "unknown"])
async def test_a_worker_left_behind_by_teardown_still_settles_and_nothing_live_is_sent(tmp_path, late) -> None:
    entered, release = threading.Event(), threading.Event()

    class Gateway:
        def create_response(self, **kwargs):
            entered.set()
            if not release.wait(5):
                raise AssertionError("never released")
            if late == "unknown":
                raise _Lost("connection reset after send")
            usage = GatewayUsage(gateway_request_id="late-gw", provider="fake", billing_units=1, cost_usd=Decimal("0.004"))
            return GatewayResponse(output_text="A late answer.", gateway_usage=usage, raw={}, finish_reason="stop")

    store, outbound = InMemoryAcpSpecSessionStore(), RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(
        runner=AgentRunner(gateway_client=Gateway(), model="fake/model"), workspace_root=tmp_path, sessions=store, outbound=outbound,
        alert_policies=(AlertPolicy(scope="turn", thresholds_usd=(Decimal("0.001"),)),),
    )  # fmt: skip
    session_id = await new_session(adapter, tmp_path, mode="chat")
    session = store.get(session_id)
    ended = threading.Event()
    session.cost_settlement.subscribe(lambda turn_id, summary: ended.set() if summary.receipt_ids and not summary.pending_invocations else None)

    task = asyncio.create_task(rpc(adapter, prompt_request(session_id, "A question?", "p1")))
    assert await asyncio.to_thread(entered.wait, 5)
    active = adapter._active_turns[session_id]  # noqa: SLF001
    active.turn_control.request_transport_teardown()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    sent = len(outbound.notifications)

    # The prompt has finalized, but its worker is still in the Gateway: not "complete at $0".
    assert (session.conversation.known_cost_usd, session.conversation.cost_complete) == (Decimal("0"), False)

    release.set()
    assert await asyncio.to_thread(ended.wait, 5)

    [settled] = session.cost_settlement.receipts(active.run_id)
    assert settled.post_teardown is True
    if late == "known":
        assert (session.conversation.known_cost_usd, session.conversation.cost_complete) == (Decimal("0.004"), True)
    else:
        assert (settled.outcome, session.conversation.known_cost_usd, session.conversation.cost_complete) == ("uncertain", Decimal("0"), False)
    assert len(outbound.notifications) == sent  # no alert, meter or text after teardown


class _PaidThenBroken:
    """Reports one paid attempt through the turn's sink, then fails."""

    def run(self, request, **kwargs):
        kwargs["stage_receipts"](receipt(f"{request.run_id}:answer:1:1", "0.003", turn=request.run_id))
        raise RuntimeError("runner defect after a paid attempt")


async def test_an_exception_after_a_paid_attempt_alerts_once_and_keeps_the_cost(tmp_path) -> None:
    store, outbound = InMemoryAcpSpecSessionStore(), RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(
        runner=_PaidThenBroken(), workspace_root=tmp_path, sessions=store, outbound=outbound,
        alert_policies=(AlertPolicy(scope="turn", thresholds_usd=(Decimal("0.002"),)),),
    )  # fmt: skip
    session_id = await new_session(adapter, tmp_path, mode="chat")

    with pytest.raises(RuntimeError, match="runner defect"):
        await rpc(adapter, prompt_request(session_id, "A question?", "p1"))

    alerts = [text for text in texts(outbound) if text.startswith("Cost alert")]
    assert alerts == ["Cost alert: this turn's model costs have reached $0.002 (now $0.003)."]
    session = store.get(session_id)
    assert (session.conversation.known_cost_usd, session.conversation.cost_complete) == (Decimal("0.003"), True)


async def test_an_outbound_failure_exit_still_alerts_in_its_turn(tmp_path) -> None:
    class Runner:
        def run(self, request, **kwargs):
            kwargs["stage_receipts"](receipt(f"{request.run_id}:planning:1:1", "0.003", turn=request.run_id, stage="planning"))
            return AgentRunResult(
                run_id=request.run_id, session_id=request.session_id, execution_mode=ExecutionMode.AGENT,
                status=AgentRunStatus.AWAITING_APPROVAL, final_state="AWAITING_APPROVAL", output_text="WRITE a.py\nx",
                tool_calls=(), total_cost_usd=Decimal("0.003"), mutation_count=0, provider_keys_resolvable=(),
                plan_hash="hash-1", candidate_plan_text="WRITE a.py\nx",
            )  # fmt: skip

    store, outbound = InMemoryAcpSpecSessionStore(), RecordingOutboundChannel()

    async def refuse(method, params):
        raise AcpOutboundError(code=-32603, message="client refused the permission request")

    outbound.request = refuse  # type: ignore[method-assign]
    adapter = AcpDuplexAdapter(
        runner=Runner(), workspace_root=tmp_path, sessions=store, outbound=outbound,
        alert_policies=(AlertPolicy(scope="session", thresholds_usd=(Decimal("0.002"),)),),
    )  # fmt: skip
    session_id = await new_session(adapter, tmp_path)

    response = await rpc(adapter, prompt_request(session_id, "Change it.", "p1"))

    assert "error" in response
    assert [text for text in texts(outbound) if text.startswith("Cost alert")] == [
        "Cost alert: this session's model costs have reached $0.002 (now $0.003)."
    ]


class _ReceiptingAgent:
    """Plans with one paid receipt; applying the stored plan sends nothing and carries the plan cost."""

    def run(self, request, **kwargs):
        common = dict(run_id=request.run_id, session_id=request.session_id, tool_calls=(), mutation_count=0, provider_keys_resolvable=())
        if not request.approval.approved:
            kwargs["stage_receipts"](receipt(f"{request.run_id}:planning:1:1", "0.002", turn=request.run_id, stage="planning"))
            return AgentRunResult(
                execution_mode=ExecutionMode.AGENT, status=AgentRunStatus.AWAITING_APPROVAL, final_state="AWAITING_APPROVAL",
                output_text="WRITE a.py\nx", total_cost_usd=Decimal("0.002"), plan_hash="hash-1", candidate_plan_text="WRITE a.py\nx", **common,
            )  # fmt: skip
        return AgentRunResult(
            execution_mode=ExecutionMode.AGENT, status=AgentRunStatus.COMPLETED, final_state="COMPLETED",
            output_text="done", total_cost_usd=Decimal("0.002"), plan_hash="hash-1", **common,
        )  # fmt: skip


async def test_approval_and_application_never_debit_the_plan_twice(tmp_path) -> None:
    adapter, outbound, _ = make_adapter(tmp_path, None, _ReceiptingAgent())
    session_id = await new_session(adapter, tmp_path)

    await prompt(adapter, outbound, session_id, "Change it.", "p1", approve=True)

    session = session_of(adapter, session_id)
    assert session.cost_settlement.settle_all().known_subtotal_usd == Decimal("0.002")
    assert (session.conversation.known_cost_usd, session.conversation.cost_complete) == (Decimal("0.002"), True)


async def test_a_runner_that_reports_no_receipts_keeps_its_reported_total(tmp_path) -> None:
    adapter, outbound, _ = make_adapter(tmp_path, None, DispatchingRunner())
    session_id = await new_session(adapter, tmp_path, mode="chat")

    await prompt(adapter, outbound, session_id, "A question?", "p1")

    assert session_of(adapter, session_id).conversation.known_cost_usd == Decimal("0.001")


# --- M2: content-free context fault diagnostics ----------------------------------------------------------

FAULT_LINE = re.compile(
    r"^optimus\.acp: context fault run_id=session-[0-9a-f]{32}:\d+ phase=(prepare|repack) category=[a-z_]+ outcome=[a-z_]+$"
)
PRIVATE_TEXT = "PRIVATE-MARKER-0123 and some private history text"


def _fault_lines(capsys) -> list[str]:
    return [line for line in capsys.readouterr().err.splitlines() if line.startswith("optimus.acp: context fault")]


class _RaisingEngine:
    def prepare_view(self, snapshot, **kwargs):
        raise RuntimeError(PRIVATE_TEXT)


class _StrangeReasonEngine:
    def prepare_view(self, snapshot, **kwargs):
        return PreparedView((), (), None, snapshot.protected, (), (), False, PRIVATE_TEXT)


def _raising_summarizer():
    def call(*, prompt, max_output_tokens):
        raise RuntimeError(PRIVATE_TEXT)

    return call


@pytest.mark.parametrize(
    ("attachment", "category"),
    [
        (lambda: make_attachment(engine=_RaisingEngine()), "engine_error"),
        (lambda: make_attachment(engine=_StrangeReasonEngine()), "other"),
        (lambda: dataclasses.replace(make_attachment(tail=10), summarizer=lambda identity, deliver: _raising_summarizer()), "maintenance_error"),
        (lambda: dataclasses.replace(make_attachment(tail=10), summarizer=_refusing_factory), "config_error"),
    ],
    ids=["engine-raises", "unlisted-reason", "maintenance-raises", "summarizer-identity-refused"],
)
async def test_a_view_fault_leaves_one_content_free_operator_line(tmp_path, capsys, attachment, category) -> None:
    adapter, outbound, _ = make_adapter(tmp_path, attachment(), DispatchingRunner())
    session_id = await new_session(adapter, tmp_path, mode="chat")
    for n in range(3):
        await prompt(adapter, outbound, session_id, f"Prompt {n} " + "words " * 40, f"p{n}")

    from optimus.context.assembly import FAULT_CATEGORIES

    lines = _fault_lines(capsys)
    assert lines and all(FAULT_LINE.match(line) for line in lines), lines
    categories = {re.search(r"category=(\S+)", line).group(1) for line in lines}
    assert category in categories and categories <= FAULT_CATEGORIES
    assert all("PRIVATE-MARKER" not in line and "private history" not in line for line in lines)


def _refusing_factory(identity, deliver_notice):
    from optimus.gateway.route_binding import RouteIdentityError

    raise RouteIdentityError(PRIVATE_TEXT)


async def test_a_healthy_turn_leaves_no_fault_line(tmp_path, capsys) -> None:
    adapter, outbound, _ = make_adapter(tmp_path, make_attachment(summarizer=SummarizerCall()), DispatchingRunner())
    session_id = await new_session(adapter, tmp_path, mode="chat")

    await prompt(adapter, outbound, session_id, "A question?", "p1")

    assert _fault_lines(capsys) == []


def test_a_repack_fault_is_recorded_with_its_phase_and_category() -> None:
    from optimus.acp.conversation import ConversationOutcome, ConversationTurn
    from optimus.acp.settlement import EffectState
    from optimus.context.assembly import AttachedTurn

    class ShrinkingEngine:
        def __init__(self) -> None:
            self.calls = 0

        def prepare_view(self, snapshot, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return ContextEngine().prepare_view(snapshot, **kwargs)
            return PreparedView((), (), None, snapshot.protected, (), (), False, "history capacity too small for a summary")

    records = {
        seq: ConversationTurn(user_prompt=f"q{seq}", plan_text="", completion_text="a" * 6000, outcome=ConversationOutcome.COMPLETED, effect_state=EffectState.NONE)
        for seq in (1, 2)
    }
    attachment = dataclasses.replace(make_attachment(engine=ShrinkingEngine()), usable_input_tokens=2500)
    turn = AttachedTurn.capture(
        attachment=attachment, session_key="s", records=records, approvals={}, generation=2,
        sanitizer=ConversationSanitizer(ConversationSanitizerInputs((), ())), strategy="sliding_window", mode=ExecutionMode.CHAT,
        checkpoint=None, current_prompt="now", turn_seq=3, cancelled=lambda: False,
    )  # fmt: skip
    assert turn.prepare().kind == "view" and turn.take_faults() == ()

    assert turn.fit(lambda envelope: f"Q\n{envelope}") is None

    assert [(fault.phase, fault.category) for fault in turn.take_faults()] == [("repack", "capacity")]


def test_a_fault_only_ever_carries_its_bounded_vocabulary() -> None:
    from optimus.context.assembly import FAULT_CATEGORIES, ContextFault

    with pytest.raises(ValueError):
        ContextFault("prepare", "RuntimeError: " + PRIVATE_TEXT)
    with pytest.raises(ValueError):
        ContextFault("elsewhere", "engine_error")
    assert all(re.fullmatch(r"[a-z_]+", category) for category in FAULT_CATEGORIES)


# --- N1: the notice wait is finite and never counts a late success ----------------------------------------


async def test_an_unconfirmed_notice_times_out_sends_nothing_and_is_never_counted_late(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(spec_module, "_NOTICE_FLUSH_TIMEOUT_SECONDS", 0.05)
    outbound = RecordingOutboundChannel()
    original = outbound.notify
    gate = asyncio.Event()
    cancelled: list[str] = []

    async def notify(method, params, *, require_flushed=False):
        if CONTRIBUTOR_NOTICE in str(params.get("update", {}).get("content", {}).get("text", "")):
            try:
                await gate.wait()  # never confirmed in time
            except asyncio.CancelledError:
                cancelled.append("cancelled")
                raise
        await original(method, params, require_flushed=require_flushed)

    outbound.notify = notify  # type: ignore[method-assign]
    client = _ObservingClient(outbound)
    adapter = AcpDuplexAdapter(
        runner=DispatchingRunner(), workspace_root=tmp_path, sessions=InMemoryAcpSpecSessionStore(), outbound=outbound,
        context_attachment=_contributor_attachment(client),
    )  # fmt: skip
    session_id = await new_session(adapter, tmp_path, mode="chat")
    for n in range(3):
        await prompt(adapter, outbound, session_id, f"Prompt {n}", f"p{n}")

    assert client.notices_seen == []  # no summary was dispatched without a confirmed notice
    assert cancelled == ["cancelled"]  # the pending send was cancelled at the deadline
    settlement = session_of(adapter, session_id).cost_settlement
    assert [(r.outcome, r.reported_cost_usd) for r in settlement.receipts(f"{session_id}:3") if r.stage == "summarization"] == [
        ("not_sent", Decimal("0"))
    ]

    assert CONTRIBUTOR_NOTICE not in texts(outbound)

    gate.set()  # a "late success" can no longer complete or count
    await asyncio.sleep(0.05)
    assert CONTRIBUTOR_NOTICE not in texts(outbound)

    await prompt(adapter, outbound, session_id, "Prompt 3", "p3")
    assert client.notices_seen == [1]  # the next request needed, and got, its own confirmed notice
