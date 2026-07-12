"""Fake-based integration evidence for Plan 9.85 multi-turn planning.

Uses scripted Gateway responses and local workspace fixtures only. This tier
proves deterministic AgentRunner branches end-to-end; it is not sufficient for
live Redis, Gateway, or ACP sign-off.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

from optimus.agent.models import AgentApproval, AgentRunRequest, AgentRunStatus
from optimus.agent.planning_loop import (
    PLANNING_NEW_READ_MAX_BYTES,
    PlanningReadRequest,
    max_planning_observation_text_bytes,
)
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import InMemoryAgentStateStore
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.guardrails.pre_tool import PreToolGuard
from optimus.runtime.modes import ExecutionMode
from optimus.usage.accounting import UsageAccountingService

_FINAL_PLAN = "READ large.py\nWRITE large.py\nupdated header\n"
_READ_MORE = "OBSERVE: need header\nREAD: large.py#bytes=0:5\n"


class ScriptingGateway:
    def __init__(self, scripts: list[tuple[str, Decimal, str]]) -> None:
        self._scripts = list(scripts)
        self.calls: list[dict[str, object]] = []

    def create_response(
        self,
        *,
        model: str,
        input_text: str,
        metadata: dict[str, object] | None = None,
    ) -> GatewayResponse:
        if not self._scripts:
            raise RuntimeError("scripted gateway exhausted")
        output_text, cost_usd, gateway_request_id = self._scripts.pop(0)
        self.calls.append(
            {
                "model": model,
                "input_text": input_text,
                "metadata": metadata,
                "gateway_request_id": gateway_request_id,
            }
        )
        return GatewayResponse(
            response_id=gateway_request_id,
            output_text=output_text,
            gateway_usage=GatewayUsage(
                gateway_request_id=gateway_request_id,
                provider="glm",
                billing_units=1,
                cost_usd=cost_usd,
            ),
            raw={"id": gateway_request_id},
        )


def _write_oversized_required_file(workspace: Path) -> None:
    (workspace / "large.py").write_text("alpha" + ("x" * (17 * 1024)), encoding="utf-8")


def _integration_runner(
    workspace: Path,
    *,
    gateway: ScriptingGateway,
    store: InMemoryAgentStateStore | None = None,
    usage_accounting: UsageAccountingService | None = None,
) -> AgentRunner:
    guard = PreToolGuard.for_workspace(workspace_root=workspace.resolve(), allowed_network_hosts=())
    return AgentRunner(
        gateway_client=gateway,
        model="glm-5.2",
        guard=guard,
        state_store=store or InMemoryAgentStateStore(),
        usage_accounting=usage_accounting,
    )


def _planning_request(
    workspace: Path,
    *,
    run_id: str = "run-integration",
    max_planning_turns: int = 3,
    max_cost_usd: Decimal = Decimal("0.05"),
) -> AgentRunRequest:
    return AgentRunRequest(
        run_id=run_id,
        task="Edit large.py",
        execution_mode=ExecutionMode.AGENT,
        workspace_root=workspace.resolve(),
        max_planning_turns=max_planning_turns,
        max_cost_usd=max_cost_usd,
    )


def test_fake_integration_two_turn_read_more_then_final_settles(tmp_path: Path) -> None:
    _write_oversized_required_file(tmp_path)
    gateway = ScriptingGateway(
        [
            (_READ_MORE, Decimal("0.002"), "gw-1"),
            (_FINAL_PLAN, Decimal("0.003"), "gw-2"),
        ]
    )
    store = InMemoryAgentStateStore()
    runner = _integration_runner(tmp_path, gateway=gateway, store=store)

    result = runner.run(_planning_request(tmp_path, max_planning_turns=2))

    assert len(gateway.calls) == 2
    assert all(call["metadata"]["purpose"] == "planning_turn" for call in gateway.calls)
    assert result.status is AgentRunStatus.AWAITING_APPROVAL
    assert result.stop_reason is None
    assert result.plan_hash == hashlib.sha256(_FINAL_PLAN.encode("utf-8")).hexdigest()
    stored = store.load_plan(run_id="run-integration", plan_hash=result.plan_hash or "")
    assert stored.planning_turns == 2
    assert stored.gateway_request_ids == ("gw-1", "gw-2")
    assert stored.cost_usd == Decimal("0.005")


def test_fake_integration_repeated_range_failure(tmp_path: Path) -> None:
    _write_oversized_required_file(tmp_path)
    gateway = ScriptingGateway(
        [
            (_READ_MORE, Decimal("0.001"), "gw-1"),
            (_READ_MORE, Decimal("0.001"), "gw-2"),
        ]
    )
    store = InMemoryAgentStateStore()
    runner = _integration_runner(tmp_path, gateway=gateway, store=store)

    result = runner.run(_planning_request(tmp_path, max_planning_turns=3))

    assert result.status is AgentRunStatus.TERMINATED
    assert result.stop_reason == "PLANNING_REPEATED_READ_REQUEST"
    assert result.plan_hash is None
    assert store.latest_plan_for_run(run_id="run-integration") is None


def test_fake_integration_observation_carryover_overflow_fails_closed(tmp_path: Path) -> None:
    _write_oversized_required_file(tmp_path)
    scripts: list[tuple[str, Decimal, str]] = []
    for index in range(6):
        start = index * 5
        end = start + 5
        read_request = (PlanningReadRequest(path="large.py", start_byte=start, end_byte=end),)
        observation = "o" * max_planning_observation_text_bytes(read_request)
        scripts.append(
            (
                f"OBSERVE: {observation}\nREAD: large.py#bytes={start}:{end}\n",
                Decimal("0.001"),
                f"gw-{index + 1}",
            )
        )
    scripts.append((_FINAL_PLAN, Decimal("0.001"), "gw-final"))
    gateway = ScriptingGateway(scripts)
    runner = _integration_runner(tmp_path, gateway=gateway)

    result = runner.run(_planning_request(tmp_path, max_planning_turns=8))

    assert result.status is AgentRunStatus.TERMINATED
    assert result.stop_reason == "PLANNING_OBSERVATION_BUDGET_EXHAUSTED"
    assert result.plan_hash is None
    assert "observation evidence exceeds" in result.output_text


def test_fake_integration_current_read_overflow_fails_closed(tmp_path: Path) -> None:
    _write_oversized_required_file(tmp_path)
    oversized_read = PLANNING_NEW_READ_MAX_BYTES + 500
    read_more = f"OBSERVE: need large chunk\nREAD: large.py#bytes=0:{oversized_read}\n"
    gateway = ScriptingGateway(
        [
            (read_more, Decimal("0.001"), "gw-1"),
            (_FINAL_PLAN, Decimal("0.001"), "gw-2"),
        ]
    )
    runner = _integration_runner(tmp_path, gateway=gateway)

    result = runner.run(_planning_request(tmp_path, max_planning_turns=2))

    assert result.status is AgentRunStatus.TERMINATED
    assert result.stop_reason == "PLANNING_READ_BUDGET_EXHAUSTED"
    assert result.plan_hash is None
    assert "read evidence exceeds" in result.output_text


def test_fake_integration_max_planning_turns_one(tmp_path: Path) -> None:
    _write_oversized_required_file(tmp_path)
    gateway = ScriptingGateway([(_READ_MORE, Decimal("0.002"), "gw-1")])
    store = InMemoryAgentStateStore()
    runner = _integration_runner(tmp_path, gateway=gateway, store=store)

    result = runner.run(_planning_request(tmp_path, max_planning_turns=1))

    assert len(gateway.calls) == 1
    assert result.status is AgentRunStatus.TERMINATED
    assert result.stop_reason == "PLANNING_TURN_LIMIT_EXHAUSTED"
    assert store.latest_plan_for_run(run_id="run-integration") is None


def test_fake_integration_max_planning_turns_two_allows_read_more_then_final(tmp_path: Path) -> None:
    _write_oversized_required_file(tmp_path)
    gateway = ScriptingGateway(
        [
            (_READ_MORE, Decimal("0.002"), "gw-1"),
            (_FINAL_PLAN, Decimal("0.003"), "gw-2"),
        ]
    )
    runner = _integration_runner(tmp_path, gateway=gateway)

    result = runner.run(_planning_request(tmp_path, max_planning_turns=2))

    assert len(gateway.calls) == 2
    assert result.status is AgentRunStatus.AWAITING_APPROVAL
    assert result.stop_reason is None


def test_fake_integration_budget_collides_with_max_turn_boundary(tmp_path: Path) -> None:
    _write_oversized_required_file(tmp_path)
    gateway = ScriptingGateway(
        [
            (_READ_MORE, Decimal("0.03"), "gw-1"),
            (_FINAL_PLAN, Decimal("0.03"), "gw-2"),
        ]
    )
    runner = _integration_runner(tmp_path, gateway=gateway)

    result = runner.run(_planning_request(tmp_path, max_planning_turns=2, max_cost_usd=Decimal("0.05")))

    assert len(gateway.calls) == 2
    assert result.status is AgentRunStatus.TERMINATED
    assert result.stop_reason == "PLANNING_BUDGET_EXHAUSTED"
    assert result.plan_hash is None


def test_fake_integration_no_pre_settlement_mutation(tmp_path: Path) -> None:
    _write_oversized_required_file(tmp_path)
    original = (tmp_path / "large.py").read_text(encoding="utf-8")
    gateway = ScriptingGateway(
        [
            (_READ_MORE, Decimal("0.002"), "gw-1"),
            (_FINAL_PLAN, Decimal("0.003"), "gw-2"),
        ]
    )
    runner = _integration_runner(tmp_path, gateway=gateway)

    result = runner.run(_planning_request(tmp_path, max_planning_turns=2))

    assert result.status is AgentRunStatus.AWAITING_APPROVAL
    assert result.mutation_count == 0
    assert (tmp_path / "large.py").read_text(encoding="utf-8") == original


def test_fake_integration_exact_approval_replay_without_replanning(tmp_path: Path) -> None:
    _write_oversized_required_file(tmp_path)
    gateway = ScriptingGateway(
        [
            (_READ_MORE, Decimal("0.002"), "gw-1"),
            (_FINAL_PLAN, Decimal("0.003"), "gw-2"),
        ]
    )
    store = InMemoryAgentStateStore()
    runner = _integration_runner(tmp_path, gateway=gateway, store=store)

    plan_result = runner.run(_planning_request(tmp_path, max_planning_turns=2, run_id="run-replay"))
    assert plan_result.status is AgentRunStatus.AWAITING_APPROVAL
    assert plan_result.plan_hash is not None
    assert len(gateway.calls) == 2

    replay_gateway = ScriptingGateway([("WRITE large.py\nshould not run\n", Decimal("0.01"), "gw-replay")])
    replay_runner = _integration_runner(tmp_path, gateway=replay_gateway, store=store)
    approved = replay_runner.run(
        AgentRunRequest(
            run_id="run-replay",
            task="Edit large.py",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path.resolve(),
            approval=AgentApproval(
                approved=True,
                approval_id="approval-integration",
                plan_hash=plan_result.plan_hash,
            ),
        )
    )

    assert approved.status is AgentRunStatus.COMPLETED
    assert replay_gateway.calls == []
    assert "updated header" in (tmp_path / "large.py").read_text(encoding="utf-8")
    assert "should not run" not in (tmp_path / "large.py").read_text(encoding="utf-8")
