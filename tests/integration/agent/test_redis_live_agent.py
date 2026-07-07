from __future__ import annotations

import os
import uuid

import pytest

from optimus.agent.models import AgentApproval, AgentRunRequest, AgentRunStatus
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import AgentPlanRecord, RedisAgentStateStore
from optimus.guardrails.pre_tool import PreToolGuard
from optimus.runtime.modes import ExecutionMode
from tests.conftest import FakeGatewayClient

pytestmark = pytest.mark.requires_redis


def test_live_redis_store_roundtrips_plan_record(live_redis_store):
    store, run_id = live_redis_store
    from decimal import Decimal

    record = AgentPlanRecord(
        run_id=run_id,
        session_id="session-1",
        task="Add a docstring",
        execution_mode=ExecutionMode.AGENT,
        workspace_root="/repo",
        plan_hash="hash-live-1",
        plan_text="WRITE example.py\ncontent",
        gateway_request_id="gw-live-1",
        model="glm-5.2",
        provider="glm",
        cost_usd=Decimal("0.002"),
        created_at_ms=1_000,
        expires_at_ms=3_601_000,
    )

    store.save_plan(record)

    assert store.load_plan(run_id=run_id, plan_hash="hash-live-1") == record
    assert store.latest_plan_for_run(run_id=run_id) == record


def test_live_agent_runner_replays_plan_from_redis_with_fresh_runner(tmp_path, live_redis_store):
    store, run_id = live_redis_store
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    plan_text = 'WRITE example.py\ndef f():\n    """Return one."""\n    return 1\n'
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path.resolve(), allowed_network_hosts=())
    redis_url = os.environ["OPTIMUS_REDIS_URL"]

    planner_gateway = FakeGatewayClient(plan_text)
    planner = AgentRunner(
        gateway_client=planner_gateway,
        model="glm-5.2",
        guard=guard,
        state_store=store,
    )
    plan_result = planner.run(
        AgentRunRequest(
            run_id=run_id,
            task="Add a docstring",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path.resolve(),
        )
    )

    assert plan_result.status is AgentRunStatus.AWAITING_APPROVAL
    assert plan_result.plan_hash
    assert len(planner_gateway.calls) == 1
    assert store.latest_plan_for_run(run_id=run_id) is not None

    replay_gateway = FakeGatewayClient("WRITE example.py\nBROKEN SECOND PLAN\n")
    replay_runner = AgentRunner(
        gateway_client=replay_gateway,
        model="glm-5.2",
        guard=guard,
        state_store=RedisAgentStateStore.from_url(redis_url),
    )
    approved = replay_runner.run(
        AgentRunRequest(
            run_id=run_id,
            task="Add a docstring",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path.resolve(),
            approval=AgentApproval(
                approved=True,
                approval_id="approval-live-1",
                plan_hash=plan_result.plan_hash,
            ),
        )
    )

    assert approved.status is AgentRunStatus.COMPLETED
    assert replay_gateway.calls == []
    assert "Return one" in target.read_text(encoding="utf-8")
    assert "BROKEN SECOND PLAN" not in target.read_text(encoding="utf-8")


def test_live_agent_runner_rejects_approval_when_redis_plan_missing(tmp_path, live_redis_store):
    store, run_id = live_redis_store
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path.resolve(), allowed_network_hosts=())
    runner = AgentRunner(
        gateway_client=FakeGatewayClient("WRITE example.py\ncontent"),
        model="glm-5.2",
        guard=guard,
        state_store=store,
    )

    result = runner.run(
        AgentRunRequest(
            run_id=run_id,
            task="Add a docstring",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path.resolve(),
            approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash="missing-hash"),
        )
    )

    assert result.status is AgentRunStatus.FAILED
    assert result.stop_reason == "PLAN_NOT_FOUND_OR_EXPIRED"


def test_live_two_run_ids_do_not_collide_in_redis(tmp_path, live_redis_store):
    store, run_id = live_redis_store
    other_run_id = f"live-{uuid.uuid4().hex}"
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path.resolve(), allowed_network_hosts=())
    runner = AgentRunner(
        gateway_client=FakeGatewayClient("WRITE example.py\ncontent"),
        model="glm-5.2",
        guard=guard,
        state_store=store,
    )

    try:
        first = runner.run(
            AgentRunRequest(
                run_id=run_id,
                task="Task A",
                execution_mode=ExecutionMode.AGENT,
                workspace_root=tmp_path.resolve(),
            )
        )
        runner_b = AgentRunner(
            gateway_client=FakeGatewayClient("WRITE other.py\nother content"),
            model="glm-5.2",
            guard=guard,
            state_store=store,
        )
        second = runner_b.run(
            AgentRunRequest(
                run_id=other_run_id,
                task="Task B",
                execution_mode=ExecutionMode.AGENT,
                workspace_root=tmp_path.resolve(),
            )
        )

        assert first.plan_hash != second.plan_hash
        assert store.latest_plan_for_run(run_id=run_id).task == "Task A"
        assert store.latest_plan_for_run(run_id=other_run_id).task == "Task B"
    finally:
        client = store._client
        for key in client.scan_iter(match=f"agent:plan:{other_run_id}*"):
            client.delete(key)
