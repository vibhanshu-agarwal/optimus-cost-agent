"""Plan 12.2 Task 11: exactly-once stage receipts and turn settlement (design spec 11; Task 1 contracts 6).

Every actual provider attempt counts once: an identical replay adds nothing, a conflicting duplicate
is an integrity error. A failed, cancelled, stale or discarded summary still costs what it cost. An
unknown cost stays unknown, never zero, and known costs before and after it stay in the subtotal.
Settlement is a projection over receipts, independent of the conversation commit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from optimus.usage.turn_settlement import (
    ReceiptConflictError,
    StageReceipt,
    TurnSettlement,
    receipt_from_maintenance,
)

AT = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def receipt(attempt: str, cost: str | None, *, stage: str = "planning", turn: str = "s:1", outcome: str = "completed", gateway: str | None = None, at=AT) -> StageReceipt:
    return StageReceipt(
        session_id="s",
        turn_id=turn,
        stage=stage,
        attempt_id=attempt,
        gateway_request_id=gateway if gateway is not None else f"gw-{attempt}",
        outcome=outcome,
        reported_cost_usd=None if cost is None else Decimal(cost),
        requested_model="m",
        recorded_at=at,
    )


def test_an_identical_replay_counts_once_even_when_it_arrives_later():
    settlement = TurnSettlement()
    settlement.record_attempt(receipt("a1", "0.002"))
    settlement.record_attempt(receipt("a1", "0.002", at=datetime(2026, 10, 3, 12, 5, tzinfo=UTC)))

    summary = settlement.settle_turn("s:1")

    assert summary.known_subtotal_usd == Decimal("0.002")
    assert summary.receipt_ids == ("a1",) and summary.complete


@pytest.mark.parametrize(
    "conflict",
    [
        receipt("a1", "0.003"),  # same attempt, different cost
        receipt("a1", None, outcome="uncertain"),  # the same attempt, now claimed unknown
        receipt("a1", "0.002", stage="answer"),
        receipt("a2", "0.003", gateway="gw-a1"),  # another attempt settling the same Gateway request differently
    ],
)
def test_a_conflicting_duplicate_is_an_integrity_error(conflict):
    settlement = TurnSettlement()
    settlement.record_attempt(receipt("a1", "0.002"))

    with pytest.raises(ReceiptConflictError):
        settlement.record_attempt(conflict)
    assert settlement.settle_turn("s:1").known_subtotal_usd == Decimal("0.002")


def test_known_costs_before_and_after_an_unknown_attempt_stay_in_the_subtotal():
    settlement = TurnSettlement()
    settlement.record_attempt(receipt("a1", "0.002"))
    settlement.record_attempt(receipt("a2", None, outcome="uncertain"))
    settlement.record_attempt(receipt("a3", "0.005"))

    summary = settlement.settle_turn("s:1")

    assert summary.known_subtotal_usd == Decimal("0.007")
    assert summary.unknown_attempt_ids == ("a2",)
    assert not summary.complete
    assert summary.receipt_ids == ("a1", "a2", "a3")


def test_an_unknown_cost_is_never_zero():
    with pytest.raises(ValueError):
        StageReceipt(
            session_id="s", turn_id="s:1", stage="planning", attempt_id="a", gateway_request_id=None,
            outcome="uncertain", reported_cost_usd=Decimal("0"), recorded_at=AT,
        )  # fmt: skip


@pytest.mark.parametrize(("outcome", "cost"), [("not_sent", "0.001"), ("completed", "-1"), ("completed", "NaN")])
def test_a_receipt_outside_the_contract_is_refused(outcome, cost):
    with pytest.raises(ValueError):
        receipt("a1", cost, outcome=outcome)


def test_turns_settle_independently_and_an_unrecorded_turn_is_empty():
    settlement = TurnSettlement()
    settlement.record_attempt(receipt("a1", "0.002", turn="s:1"))
    settlement.record_attempt(receipt("b1", "0.004", turn="s:2"))

    assert settlement.settle_turn("s:2").known_subtotal_usd == Decimal("0.004")
    empty = settlement.settle_turn("s:9")
    assert (empty.known_subtotal_usd, empty.receipt_ids, empty.complete) == (Decimal("0"), (), True)


def _maintenance_receipt(attempt: str, cost: Decimal | None, outcome: str = "completed"):
    from optimus.context.maintenance import MaintenanceIdentity, MaintenanceReceipt

    identity = MaintenanceIdentity(
        session_id="s", turn_seq=1, model_id="qwen/qwen3.7-flash", role="summarizer", route=("alibaba",),
        reasoning=None, quantizations=("fp8",), strategy="compaction", revision_digest="d" * 64,
    )  # fmt: skip
    return MaintenanceReceipt(
        identity=identity, stage="summarization", attempt_id=attempt, gateway_request_id=f"gw-{attempt}", outcome=outcome,
        cost_usd=cost, finish_status="stop" if outcome == "completed" else None, covered_turn_ids=(1, 2), recorded_at=AT,
        provider_request_id=None, http_status=None,
    )  # fmt: skip


def test_a_discarded_or_failed_summary_still_costs_what_it_cost():
    settlement = TurnSettlement()
    settlement.record_attempt(receipt_from_maintenance(_maintenance_receipt("m1", Decimal("0.0003"))))
    settlement.record_attempt(receipt_from_maintenance(_maintenance_receipt("m2", None, outcome="uncertain")))
    settlement.record_attempt(receipt("a1", "0.002"))

    summary = settlement.settle_turn("s:1")

    assert summary.known_subtotal_usd == Decimal("0.0023")
    assert summary.unknown_attempt_ids == ("m2",)
    converted = receipt_from_maintenance(_maintenance_receipt("m1", Decimal("0.0003")))
    assert (converted.stage, converted.strategy, converted.revision_digest, converted.requested_model) == (
        "summarization", "compaction", "d" * 64, "qwen/qwen3.7-flash",
    )  # fmt: skip


def test_receipts_from_other_threads_are_recorded_once(tmp_path):
    import threading

    settlement = TurnSettlement()
    barrier = threading.Barrier(8)

    def record() -> None:
        barrier.wait()
        settlement.record_attempt(receipt("a1", "0.002"))

    threads = [threading.Thread(target=record) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)

    assert settlement.settle_turn("s:1").receipt_ids == ("a1",)


# --- The runner reports every planning and answer attempt -----------------------------------------


class _Gateway:
    """Scripted replies: a string is answered with a known cost; an exception is raised (unknown cost)."""

    def __init__(self, *replies) -> None:
        self.replies = list(replies)
        self.calls = 0

    def create_response(self, *, model, input_text, metadata=None):
        from optimus.gateway.models import GatewayResponse, GatewayUsage

        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        usage = GatewayUsage(gateway_request_id=f"gw-{self.calls}", provider="p", billing_units=1, cost_usd=Decimal("0.002"))
        return GatewayResponse(output_text=reply, gateway_usage=usage, raw={}, finish_reason="stop")


def _run(tmp_path, mode, gateway):
    from optimus.agent.models import AgentRunRequest
    from optimus.agent.runner import AgentRunner
    from optimus.runtime.modes import ExecutionMode

    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    receipts: list[StageReceipt] = []
    request = AgentRunRequest(run_id="s:1", session_id="s", task="Q", execution_mode=getattr(ExecutionMode, mode), workspace_root=tmp_path)
    result = AgentRunner(gateway_client=gateway, model="m").run(request, stage_receipts=receipts.append)
    return result, receipts


def test_planning_reports_a_known_attempt_then_an_unknown_one(tmp_path):
    gateway = _Gateway("OBSERVE: need it\nREAD: a.py#bytes=0:5\n", ConnectionResetError("lost"))

    result, receipts = _run(tmp_path, "AGENT", gateway)

    assert [(r.stage, r.outcome, r.reported_cost_usd) for r in receipts] == [
        ("planning", "completed", Decimal("0.002")),
        ("planning", "uncertain", None),
    ]
    assert [r.attempt_id for r in receipts] == ["s:1:planning:1:1", "s:1:planning:2:1"]
    assert receipts[0].gateway_request_id == "gw-1" and receipts[1].gateway_request_id is None
    assert not result.cost_complete


def test_a_chat_answer_reports_its_attempt(tmp_path):
    result, receipts = _run(tmp_path, "CHAT", _Gateway("An answer."))

    [receipt] = receipts
    assert (receipt.stage, receipt.outcome, receipt.reported_cost_usd, receipt.attempt_id) == (
        "answer", "completed", Decimal("0.002"), "s:1:answer:1:1",
    )  # fmt: skip
    assert result.total_cost_usd == receipt.reported_cost_usd  # the runner's total and its receipts agree


def test_an_unknown_chat_attempt_is_reported_unknown(tmp_path):
    _, receipts = _run(tmp_path, "CHAT", _Gateway(TimeoutError("read timed out")))

    [receipt] = receipts
    assert (receipt.stage, receipt.outcome, receipt.reported_cost_usd) == ("answer", "uncertain", None)


def test_applying_a_stored_plan_reports_no_planning_attempt(tmp_path):
    from optimus.agent.models import AgentApproval, AgentRunRequest
    from optimus.agent.runner import AgentRunner
    from optimus.agent.state_store import InMemoryAgentStateStore
    from optimus.runtime.modes import ExecutionMode

    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    runner = AgentRunner(gateway_client=_Gateway("WRITE a.py\nx = 2\n"), model="m", state_store=InMemoryAgentStateStore())
    receipts: list[StageReceipt] = []
    request = AgentRunRequest(run_id="s:1", session_id="s", task="Q", execution_mode=ExecutionMode.AGENT, workspace_root=tmp_path)
    planned = runner.run(request, stage_receipts=receipts.append)
    approved = request.model_copy(update={"approval": AgentApproval(approved=True, approval_id="a", plan_hash=planned.plan_hash)})
    runner.run(approved, stage_receipts=receipts.append)

    assert len(receipts) == 1  # application makes no model call, so planning is charged once


# --- The ACP session settles every stage once ----------------------------------------------------


class _ReceiptRunner:
    """Reports one attempt per planning/answer run through `stage_receipts`, as the real runner does;
    `unknown_on` makes those turns' attempts unknown."""

    def __init__(self, *, unknown_on: tuple[int, ...] = ()) -> None:
        self.unknown_on = unknown_on

    def run(self, request, **kwargs):
        from optimus.agent.models import AgentRunResult, AgentRunStatus
        from optimus.runtime.modes import ExecutionMode

        turn = int(request.run_id.rsplit(":", 1)[1])
        chat = request.execution_mode is ExecutionMode.CHAT
        unknown = turn in self.unknown_on
        cost = Decimal("0.001") if chat else Decimal("0.002")
        if not request.approval.approved:
            stage = "answer" if chat else "planning"
            kwargs["stage_receipts"](
                StageReceipt(
                    session_id=request.session_id, turn_id=request.run_id, stage=stage, attempt_id=f"{request.run_id}:{stage}:1:1",
                    gateway_request_id=None if unknown else f"gw-{request.run_id}", outcome="uncertain" if unknown else "completed",
                    reported_cost_usd=None if unknown else cost, recorded_at=AT,
                )
            )  # fmt: skip
        common = dict(run_id=request.run_id, session_id=request.session_id, tool_calls=(), mutation_count=0, provider_keys_resolvable=())
        if chat:
            return AgentRunResult(
                execution_mode=ExecutionMode.CHAT, status=AgentRunStatus.COMPLETED, final_state="CHAT_ONLY", output_text="An answer.",
                total_cost_usd=Decimal("0") if unknown else cost, cost_complete=not unknown, **common,
            )  # fmt: skip
        if not request.approval.approved:
            return AgentRunResult(
                execution_mode=ExecutionMode.AGENT, status=AgentRunStatus.AWAITING_APPROVAL, final_state="AWAITING_APPROVAL",
                output_text="WRITE a.py\nx", total_cost_usd=cost, plan_hash="hash-1", candidate_plan_text="WRITE a.py\nx", **common,
            )  # fmt: skip
        return AgentRunResult(
            execution_mode=ExecutionMode.AGENT, status=AgentRunStatus.COMPLETED, final_state="COMPLETED", output_text="done",
            total_cost_usd=cost, plan_hash="hash-1", **common,
        )  # fmt: skip


async def test_a_session_settles_summarization_and_planning_once(tmp_path):
    from tests.unit.acp.test_context_engine_admission import SummarizerCall, make_adapter, make_attachment, new_session, prompt, session_of

    adapter, outbound, _ = make_adapter(tmp_path, make_attachment(summarizer=SummarizerCall()), _ReceiptRunner())
    session_id = await new_session(adapter, tmp_path, mode="chat")
    for n in range(4):
        await prompt(adapter, outbound, session_id, f"Prompt {n}", f"p{n}")

    session = session_of(adapter, session_id)
    summary = session.cost_settlement.settle_turn(f"{session_id}:4")
    stages = sorted(r.stage for r in session.cost_settlement.receipts(f"{session_id}:4"))
    assert stages == ["answer", "summarization"]
    assert summary.known_subtotal_usd == Decimal("0.0011") and summary.complete
    # The conversation's cost carries summarization as well as the answers, each once: four answers
    # and the summaries of turns 3 and 4.
    assert session.conversation.usage_gauge().cost == Decimal("0.0042")


async def test_known_session_cost_keeps_accumulating_after_an_unknown_turn(tmp_path):
    from tests.unit.acp.test_context_engine_admission import make_adapter, new_session, prompt, session_of

    adapter, outbound, _ = make_adapter(tmp_path, None, _ReceiptRunner(unknown_on=(2,)))
    session_id = await new_session(adapter, tmp_path, mode="chat")
    for n in range(3):
        await prompt(adapter, outbound, session_id, f"Prompt {n}", f"p{n}")

    conversation = session_of(adapter, session_id).conversation
    assert conversation.usage_gauge().cost is None  # never a definitive total once incomplete
    assert conversation.known_cost_usd == Decimal("0.002")  # turns 1 and 3, before and after the unknown


async def test_a_configured_alert_is_shown_once_and_refuses_nothing(tmp_path):
    from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
    from optimus.usage.cost_alerts import AlertPolicy
    from tests.unit.acp.test_context_engine_admission import new_session, prompt, texts

    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(
        runner=_ReceiptRunner(),
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=outbound,
        alert_policies=(AlertPolicy(scope="session", thresholds_usd=(Decimal("0.002"),)),),
    )
    session_id = await new_session(adapter, tmp_path, mode="chat")

    responses, shown = [], []
    for n in range(3):
        outbound.notifications.clear()
        responses.append(await prompt(adapter, outbound, session_id, f"Prompt {n}", f"p{n}"))
        shown.append(sum("Cost alert" in text for text in texts(outbound)))

    assert [r["result"]["stopReason"] for r in responses] == ["end_turn"] * 3
    assert shown == [0, 1, 0]  # below at $0.001, crossed at $0.002, then never repeated


async def test_an_approval_denial_still_settles_its_planning_cost(tmp_path):
    import asyncio

    from tests.unit.acp.test_context_engine_admission import make_adapter, new_session, prompt_request, rpc, session_of

    adapter, outbound, _ = make_adapter(tmp_path, None, _ReceiptRunner())
    session_id = await new_session(adapter, tmp_path)
    task = asyncio.create_task(rpc(adapter, prompt_request(session_id, "Change it", "p1")))
    permission = await asyncio.wait_for(outbound.wait_for_request("session/request_permission"), timeout=5)
    outbound.respond(permission["id"], {"outcome": {"outcome": "selected", "optionId": "reject"}})
    await asyncio.wait_for(task, timeout=5)

    summary = session_of(adapter, session_id).cost_settlement.settle_turn(f"{session_id}:1")
    assert summary.known_subtotal_usd == Decimal("0.002")
    assert summary.receipt_ids == (f"{session_id}:1:planning:1:1",)


@pytest.mark.parametrize("exit_kind", ["refused_above_floor", "cancelled"])
async def test_summaries_paid_for_on_a_turn_that_sends_nothing_still_settle(tmp_path, exit_kind):
    import asyncio
    import threading

    from tests.unit.acp.test_context_engine_admission import (
        SummarizerCall,
        commit_record,
        make_adapter,
        make_attachment,
        new_session,
        prompt,
        prompt_request,
        rpc,
        session_of,
    )  # fmt: skip

    entered, release = threading.Event(), threading.Event()
    summarizer = SummarizerCall(text="not a valid summary" if exit_kind == "refused_above_floor" else SummarizerCall().text)
    adapter, outbound, runner = make_adapter(tmp_path, make_attachment(summarizer=summarizer), _ReceiptRunner())
    session_id = await new_session(adapter, tmp_path, mode="chat")
    session = session_of(adapter, session_id)
    if exit_kind == "refused_above_floor":
        # Malformed summaries make the view unavailable after paid maintenance; the floor is exceeded.
        for n in range(3):
            commit_record(session.conversation, ("history " * 22_000)[:176_000] + str(n))
        response = await prompt(adapter, outbound, session_id, "Now", "now")
        assert response["result"]["stopReason"] == "end_turn"
        assert len(session.conversation.records) == 3  # nothing committed: the refusal is recoverable
        turn_id = f"{session_id}:4"
    else:
        for n in range(3):
            await prompt(adapter, outbound, session_id, f"Prompt {n}", f"p{n}")

        def block() -> None:
            entered.set()
            assert release.wait(5)

        summarizer._during = block  # noqa: SLF001
        task = asyncio.create_task(rpc(adapter, prompt_request(session_id, "Cancel me", "c1")))
        assert await asyncio.to_thread(entered.wait, 5)
        await adapter.handle_client_notification({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": session_id}})
        release.set()
        assert (await asyncio.wait_for(task, timeout=5))["result"]["stopReason"] == "cancelled"
        turn_id = f"{session_id}:4"

    receipts = session.cost_settlement.receipts(turn_id)
    assert receipts and all(r.stage == "summarization" for r in receipts)
    assert session.cost_settlement.settle_turn(turn_id).known_subtotal_usd == Decimal("0.0001") * len(receipts)


# --- Fable CP3 review fixes -------------------------------------------------------------------------


def test_an_identical_gateway_replay_on_another_host_attempt_is_charged_once():
    settlement = TurnSettlement()
    settlement.record_attempt(receipt("a1", "0.002", gateway="gw-shared"))
    settlement.record_attempt(receipt("a2", "0.002", gateway="gw-shared"))  # the Gateway replayed its settled request

    summary = settlement.settle_turn("s:1")

    assert summary.known_subtotal_usd == Decimal("0.002") and summary.receipt_ids == ("a1",)


def test_a_summarization_receipt_keeps_the_exact_route_and_resolved_provider():
    import dataclasses

    raw = dataclasses.replace(_maintenance_receipt("m1", Decimal("0.0003")), provider="alibaba", resolved_provider="alibaba", resolved_model="qwen/qwen3.7-flash-0901")

    converted = receipt_from_maintenance(raw)

    assert (converted.role, converted.route) == ("summarizer", ("alibaba",))
    assert (converted.provider, converted.resolved_provider, converted.resolved_model) == ("alibaba", "alibaba", "qwen/qwen3.7-flash-0901")


def test_an_unknown_attempt_settled_after_teardown_is_flagged(tmp_path):
    from optimus.acp.lifecycle import TurnControl
    from optimus.agent.models import AgentRunRequest
    from optimus.agent.runner import AgentRunner
    from optimus.runtime.modes import ExecutionMode

    control = TurnControl(session_id="s", turn_seq=1)

    class Gateway:
        def create_response(self, *, model, input_text, metadata=None):
            control.request_transport_teardown()  # the client went away while the attempt was in flight
            raise ConnectionResetError("lost")

    receipts: list[StageReceipt] = []
    request = AgentRunRequest(run_id="s:1", session_id="s", task="Q", execution_mode=ExecutionMode.CHAT, workspace_root=tmp_path)
    AgentRunner(gateway_client=Gateway(), model="m").run(request, stage_receipts=receipts.append, operation_control=control)

    [unknown] = receipts
    assert (unknown.outcome, unknown.reported_cost_usd, unknown.post_teardown) == ("uncertain", None, True)


async def test_a_runner_exception_still_applies_what_the_turn_settled(tmp_path):
    from tests.unit.acp.test_context_engine_admission import make_adapter, new_session, prompt_request, rpc, session_of

    class RaisingRunner:
        def run(self, request, **kwargs):
            kwargs["stage_receipts"](
                StageReceipt(
                    session_id=request.session_id, turn_id=request.run_id, stage="answer", attempt_id=f"{request.run_id}:answer:1:1",
                    gateway_request_id="gw-x", outcome="completed", reported_cost_usd=Decimal("0.004"), recorded_at=AT,
                )
            )  # fmt: skip
            raise RuntimeError("runner defect after a paid call")

    adapter, _, _ = make_adapter(tmp_path, None, RaisingRunner())
    session_id = await new_session(adapter, tmp_path, mode="chat")

    with pytest.raises(RuntimeError, match="runner defect"):
        await rpc(adapter, prompt_request(session_id, "Q", "p1"))

    conversation = session_of(adapter, session_id).conversation
    assert conversation.known_cost_usd == Decimal("0.004") and conversation.usage_gauge().cost == Decimal("0.004")


def test_a_daily_alert_policy_is_refused_by_a_host_without_a_reconciled_ledger(tmp_path):
    from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
    from optimus.usage.cost_alerts import AlertPolicy

    with pytest.raises(ValueError, match="reconciled durable ledger"):
        AcpDuplexAdapter(
            runner=_ReceiptRunner(),
            workspace_root=tmp_path,
            sessions=InMemoryAcpSpecSessionStore(),
            outbound=RecordingOutboundChannel(),
            alert_policies=(AlertPolicy(scope="day", thresholds_usd=(Decimal("1"),), day_timezone="Asia/Kolkata"),),
        )
