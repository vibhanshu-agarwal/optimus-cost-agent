from __future__ import annotations

import os
import time
import uuid
from decimal import Decimal

import pytest

from optimus.agent.models import AgentApproval, AgentRunRequest, AgentRunStatus
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import AgentPlanRecord, RedisAgentStateStore
from optimus.guardrails.pre_tool import PreToolGuard
from optimus.redis.async_bridge import sync_await
from optimus.runtime.modes import ExecutionMode
from tests.conftest import FakeGatewayClient
from tests.integration.agent.test_multi_turn_planning_flow import (
    _FINAL_PLAN,
    _READ_MORE,
    ScriptingGateway,
    _write_oversized_required_file,
)

pytestmark = pytest.mark.requires_redis

_MULTILINE_PLAN_TEXT = (
    "WRITE example.py\n"
    "def f():\n"
    '    """Return one."""\n'
    "    return 1\n"
    "\n"
    "WRITE notes.md\n"
    "line two\n"
    "line three"
)


def _plan_keys_for_run(client: object, run_id: str) -> set[str]:
    async def _collect() -> set[str]:
        keys: set[str] = set()
        async for key in client.scan_iter(match=f"agent:plan:{run_id}*"):
            keys.add(key)
        return keys

    return sync_await(_collect())


def _delete_plan_keys(client: object, run_id: str) -> None:
    async def _delete() -> None:
        async for key in client.scan_iter(match=f"agent:plan:{run_id}*"):
            await client.delete(key)

    sync_await(_delete())


def test_live_redis_store_roundtrips_plan_record_with_full_fidelity(live_redis_store):
    store, run_id = live_redis_store
    record = AgentPlanRecord(
        run_id=run_id,
        session_id=None,
        task="Add a docstring with fidelity checks",
        execution_mode=ExecutionMode.PLAN,
        workspace_root="/repo",
        plan_hash="hash-live-fidelity",
        plan_text=_MULTILINE_PLAN_TEXT,
        gateway_request_id="gw-live-fidelity",
        model="glm-5.2",
        provider="glm",
        cost_usd=Decimal("1.23456789"),
        created_at_ms=1_000,
        expires_at_ms=3_601_000,
    )

    store.save_plan(record)

    loaded = store.load_plan(run_id=run_id, plan_hash="hash-live-fidelity")
    assert loaded == record
    assert loaded.session_id is None
    assert loaded.execution_mode is ExecutionMode.PLAN
    assert loaded.cost_usd == Decimal("1.23456789")
    assert loaded.plan_text == _MULTILINE_PLAN_TEXT
    assert store.latest_plan_for_run(run_id=run_id) == record


def test_live_redis_plan_expires_after_real_ttl(live_redis_store):
    _, run_id = live_redis_store
    redis_url = os.environ["OPTIMUS_REDIS_URL"]
    short_ttl_store = RedisAgentStateStore.from_url(redis_url, ttl_seconds=1)
    record = AgentPlanRecord(
        run_id=run_id,
        session_id="session-ttl",
        task="Expire quickly",
        execution_mode=ExecutionMode.AGENT,
        workspace_root="/repo",
        plan_hash="hash-live-ttl",
        plan_text="WRITE example.py\ncontent",
        gateway_request_id="gw-live-ttl",
        model="glm-5.2",
        provider="glm",
        cost_usd=Decimal("0.001"),
        created_at_ms=1_000,
        expires_at_ms=3_601_000,
    )

    short_ttl_store.save_plan(record)
    assert short_ttl_store.load_plan(run_id=run_id, plan_hash="hash-live-ttl") == record

    time.sleep(1.5)

    with pytest.raises(KeyError, match="stored plan not found"):
        short_ttl_store.load_plan(run_id=run_id, plan_hash="hash-live-ttl")
    assert short_ttl_store.latest_plan_for_run(run_id=run_id) is None


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


def test_live_redis_keys_are_namespaced_and_teardown_clears_them(live_redis_store):
    store, run_id = live_redis_store
    record = AgentPlanRecord(
        run_id=run_id,
        session_id="session-keys",
        task="Key hygiene",
        execution_mode=ExecutionMode.AGENT,
        workspace_root="/repo",
        plan_hash="hash-live-keys",
        plan_text="WRITE example.py\ncontent",
        gateway_request_id="gw-live-keys",
        model="glm-5.2",
        provider="glm",
        cost_usd=Decimal("0.002"),
        created_at_ms=1_000,
        expires_at_ms=3_601_000,
    )

    store.save_plan(record)
    keys = _plan_keys_for_run(store.redis_client, run_id)
    assert keys
    assert all(key.startswith(f"agent:plan:{run_id}") for key in keys)

    _delete_plan_keys(store.redis_client, run_id)

    assert _plan_keys_for_run(store.redis_client, run_id) == set()


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
        _delete_plan_keys(store.redis_client, other_run_id)


def test_live_multi_turn_planning_persists_final_plan_and_replays_without_gateway(
    tmp_path,
    live_redis_store,
) -> None:
    store, run_id = live_redis_store
    _write_oversized_required_file(tmp_path)
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path.resolve(), allowed_network_hosts=())
    redis_url = os.environ["OPTIMUS_REDIS_URL"]
    gateway = ScriptingGateway(
        [
            (_READ_MORE, Decimal("0.002"), "gw-live-mt-1"),
            (_FINAL_PLAN, Decimal("0.003"), "gw-live-mt-2"),
        ]
    )
    planner = AgentRunner(
        gateway_client=gateway,
        model="glm-5.2",
        guard=guard,
        state_store=store,
    )
    plan_result = planner.run(
        AgentRunRequest(
            run_id=run_id,
            task="Edit large.py",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path.resolve(),
            max_planning_turns=2,
        )
    )

    assert plan_result.status is AgentRunStatus.AWAITING_APPROVAL
    assert plan_result.plan_hash is not None
    assert len(gateway.calls) == 2

    stored = store.load_plan(run_id=run_id, plan_hash=plan_result.plan_hash)
    assert stored.planning_turns == 2
    assert stored.gateway_request_ids == ("gw-live-mt-1", "gw-live-mt-2")
    assert stored.cost_usd == Decimal("0.005")
    assert stored.plan_text == _FINAL_PLAN
    assert "OBSERVE:" not in stored.plan_text
    assert "need header" not in stored.plan_text

    replay_gateway = ScriptingGateway([("WRITE large.py\nstale replay\n", Decimal("0.01"), "gw-stale")])
    replay_runner = AgentRunner(
        gateway_client=replay_gateway,
        model="glm-5.2",
        guard=guard,
        state_store=RedisAgentStateStore.from_url(redis_url),
    )
    approved = replay_runner.run(
        AgentRunRequest(
            run_id=run_id,
            task="Edit large.py",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path.resolve(),
            approval=AgentApproval(
                approved=True,
                approval_id="approval-live-mt",
                plan_hash=plan_result.plan_hash,
            ),
        )
    )

    assert approved.status is AgentRunStatus.COMPLETED
    assert replay_gateway.calls == []
    assert "updated header" in (tmp_path / "large.py").read_text(encoding="utf-8")
    assert "stale replay" not in (tmp_path / "large.py").read_text(encoding="utf-8")
