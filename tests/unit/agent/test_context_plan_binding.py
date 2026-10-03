"""Plan 12.2 Task 9: a stored plan is bound to the context it was planned on (design spec 7; Task 1
contracts 5).

The plan record keeps the admitted context digest. Applying it requires the same digest, so a changed
context needs fresh planning and approval. Application reuses the admitted request: a mode or strategy
change while the permission dialog is open cannot alter it, no summary is regenerated, and planning
cost already charged is not charged again.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.agent.models import AgentApproval, AgentRunRequest, AgentRunStatus
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import AgentPlanRecord, InMemoryAgentStateStore, _record_from_mapping, _record_to_mapping
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.runtime.modes import ExecutionMode

PLAN = 'WRITE example.py\ndef f():\n    """Return one."""\n    return 1\n'


class _Gateway:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text
        self.calls: list[dict[str, object]] = []

    def create_response(self, *, model: str, input_text: str, metadata=None) -> GatewayResponse:
        self.calls.append({"input_text": input_text, "metadata": metadata})
        usage = GatewayUsage(gateway_request_id=f"gw-{len(self.calls)}", provider="openrouter", billing_units=10, cost_usd=Decimal("0.002"))
        return GatewayResponse(response_id=f"r{len(self.calls)}", output_text=self.output_text, gateway_usage=usage, raw={})


class _Usage:
    def __init__(self) -> None:
        self.records: list[object] = []

    def record_gateway_usage(self, *args, **kwargs) -> None:
        self.records.append((args, kwargs))


def _request(tmp_path: Path, *, digest: str | None, approval: AgentApproval | None = None) -> AgentRunRequest:
    fields: dict[str, object] = dict(
        run_id="session-1:3",
        session_id="session-1",
        task="Add a docstring to example.py",
        execution_mode=ExecutionMode.AGENT,
        workspace_root=tmp_path,
        conversation_envelope="HISTORY-VIEW",
        selection_text="Add a docstring to example.py",
        context_digest=digest,
    )
    if approval is not None:
        fields["approval"] = approval
    return AgentRunRequest(**fields)


def _plan(tmp_path: Path, digest: str | None = "a" * 64):
    (tmp_path / "example.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    gateway = _Gateway(PLAN)
    store = InMemoryAgentStateStore()
    usage = _Usage()
    runner = AgentRunner(gateway_client=gateway, model="m", state_store=store, usage_accounting=usage)
    planned = runner.run(_request(tmp_path, digest=digest))
    assert planned.status is AgentRunStatus.AWAITING_APPROVAL
    return runner, gateway, store, usage, planned


def _approval(planned) -> AgentApproval:
    return AgentApproval(approved=True, approval_id="approval-1", plan_hash=planned.plan_hash)


def test_the_stored_plan_records_the_admitted_context_digest(tmp_path):
    _, _, store, _, planned = _plan(tmp_path)

    record = store.load_plan(run_id="session-1:3", plan_hash=planned.plan_hash)

    assert record.context_digest == "a" * 64
    assert record.task == "Add a docstring to example.py"


def test_a_changed_context_digest_invalidates_the_stored_authorization(tmp_path):
    runner, gateway, _, _, planned = _plan(tmp_path)

    result = runner.run(_request(tmp_path, digest="b" * 64, approval=_approval(planned)))

    assert result.stop_reason == "PLAN_NOT_FOUND_OR_EXPIRED"
    assert result.mutation_count == 0
    assert "Return one" not in (tmp_path / "example.py").read_text(encoding="utf-8")
    assert len(gateway.calls) == 1


def test_a_missing_digest_never_matches_a_bound_plan(tmp_path):
    runner, _, _, _, planned = _plan(tmp_path)

    result = runner.run(_request(tmp_path, digest=None, approval=_approval(planned)))

    assert result.stop_reason == "PLAN_NOT_FOUND_OR_EXPIRED"


def test_an_unbound_plan_never_matches_a_bound_request(tmp_path):
    runner, _, _, _, planned = _plan(tmp_path, digest=None)

    result = runner.run(_request(tmp_path, digest="a" * 64, approval=_approval(planned)))

    assert result.stop_reason == "PLAN_NOT_FOUND_OR_EXPIRED"


def test_applying_the_stored_plan_charges_no_new_planning_receipt(tmp_path):
    runner, gateway, _, usage, planned = _plan(tmp_path)
    receipts_after_planning = len(usage.records)

    result = runner.run(_request(tmp_path, digest="a" * 64, approval=_approval(planned)))

    assert result.status is AgentRunStatus.COMPLETED
    assert "Return one" in (tmp_path / "example.py").read_text(encoding="utf-8")
    assert len(gateway.calls) == 1
    assert len(usage.records) == receipts_after_planning


def test_the_digest_survives_the_redis_mapping_and_legacy_records_load_unbound():
    record = AgentPlanRecord(
        run_id="r",
        task="t",
        execution_mode=ExecutionMode.AGENT,
        workspace_root="/w",
        plan_hash="h",
        plan_text="WRITE a.py\nx",
        gateway_request_id="gw",
        model="m",
        provider="p",
        cost_usd=Decimal("0.002"),
        created_at_ms=1,
        expires_at_ms=2,
        context_digest="a" * 64,
    )

    assert _record_from_mapping(_record_to_mapping(record)).context_digest == "a" * 64
    legacy = _record_to_mapping(record.model_copy(update={"context_digest": None}))
    assert "context_digest" not in legacy
    assert _record_from_mapping(legacy).context_digest is None


# --- ACP: application reuses the admitted request ------------------------------------------------


async def test_a_mode_or_strategy_change_while_waiting_cannot_alter_application(tmp_path):
    from tests.unit.acp.test_context_engine_admission import (
        Runner,
        SummarizerCall,
        make_attachment,
        new_session,
        prompt_request,
        rpc,
        session_of,
    )

    summarizer = SummarizerCall()
    runner = Runner()
    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(
        runner=runner,
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=outbound,
        context_attachment=make_attachment(summarizer=summarizer),
    )
    session_id = await new_session(adapter, tmp_path)
    for n in range(3):
        task = asyncio.create_task(rpc(adapter, prompt_request(session_id, f"Earlier {n}", f"p{n}")))
        permission = await asyncio.wait_for(outbound.wait_for_request("session/request_permission"), timeout=5)
        outbound.respond(permission["id"], {"outcome": {"outcome": "selected", "optionId": "approve"}})
        outbound.requests.clear()
        await asyncio.wait_for(task, timeout=5)
    session = session_of(adapter, session_id)
    conversation = session.conversation

    task = asyncio.create_task(rpc(adapter, prompt_request(session_id, "Apply it", "now")))
    permission = await asyncio.wait_for(outbound.wait_for_request("session/request_permission"), timeout=5)
    summaries_at_permission = len(summarizer.prompts)
    set_mode = {"jsonrpc": "2.0", "id": "m", "method": "session/set_mode", "params": {"sessionId": session_id, "modeId": "chat"}}
    assert "result" in await rpc(adapter, set_mode)
    session.context_strategy = "sliding_window"
    outbound.respond(permission["id"], {"outcome": {"outcome": "selected", "optionId": "approve"}})
    response = await asyncio.wait_for(task, timeout=5)

    assert response["result"]["stopReason"] == "end_turn"
    planning, applied = runner.requests[-2], runner.requests[-1]
    assert applied.approval.approved and not planning.approval.approved
    assert applied.model_dump(exclude={"approval"}) == planning.model_dump(exclude={"approval"})
    assert applied.execution_mode is ExecutionMode.AGENT
    assert len(summarizer.prompts) == summaries_at_permission  # no summary regenerated
    # Four planning charges, none repeated, plus every summary paid for (Plan 12.2 Task 11).
    assert conversation.usage_gauge().cost == Decimal("0.008") + Decimal("0.0001") * len(summarizer.prompts)
    facts = session.context_approvals[max(conversation.records)]
    assert [fact.decision.value for fact in facts] == ["granted"]
    assert facts[0].artifact_hash == "hash-1"
