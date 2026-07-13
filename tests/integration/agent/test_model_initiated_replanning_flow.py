"""Fake-based integration evidence for Plan 9.87 fitting-context replanning.

Uses scripted Gateway responses and local workspace fixtures only. This tier
proves deterministic AgentRunner branches end-to-end; it is not sufficient for
live Redis, Gateway, or ACP sign-off.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

from optimus.agent.models import AgentRunRequest, AgentRunStatus
from optimus.agent.planning_loop import PlanningProgressEvent
from optimus.agent.prompts import MULTI_TURN_PLANNER_PROMPT_VERSION, WORKSPACE_FILES_HEADER
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import InMemoryAgentStateStore
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.guardrails.pre_tool import PreToolGuard
from optimus.runtime.modes import ExecutionMode
from optimus.usage.accounting import UsageAccountingService

_ORIGINAL_TARGET_BYTES = b"original\n"
_REFRESHED_TARGET_BYTES = b"updated!\n"
assert len(_ORIGINAL_TARGET_BYTES) == len(_REFRESHED_TARGET_BYTES)


class ScriptingGateway:
    def __init__(
        self,
        scripts: list[tuple[str, Decimal, str]],
        *,
        on_planning_turn: dict[int, callable] | None = None,
    ) -> None:
        self._scripts = list(scripts)
        self._on_planning_turn = on_planning_turn or {}
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
        metadata = metadata or {}
        planning_turn = metadata.get("planning_turn")
        if isinstance(planning_turn, int):
            callback = self._on_planning_turn.get(planning_turn)
            if callback is not None:
                callback()
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


def _runner(
    workspace: Path,
    *,
    gateway: ScriptingGateway,
    store: InMemoryAgentStateStore | None = None,
    usage_accounting: UsageAccountingService | None = None,
    progress_observer: callable | None = None,
) -> AgentRunner:
    guard = PreToolGuard.for_workspace(workspace_root=workspace.resolve(), allowed_network_hosts=())
    return AgentRunner(
        gateway_client=gateway,
        model="glm-5.2",
        guard=guard,
        state_store=store or InMemoryAgentStateStore(),
        usage_accounting=usage_accounting,
        planning_progress_observer=progress_observer,
    )


def test_fitting_context_model_initiated_replanning_refreshes_guarded_reads(tmp_path: Path) -> None:
    target = tmp_path / "target.py"
    target.write_bytes(_ORIGINAL_TARGET_BYTES)
    target_size = len(target.read_bytes())
    read_more = (
        "OBSERVE: Need the current complete target before replacement.\n"
        f"READ: target.py#bytes=0:{target_size}\n"
    )
    final_plan = "READ target.py\nWRITE target.py\nupdated header\n"

    def refresh_target_before_guarded_read() -> None:
        target.write_bytes(_REFRESHED_TARGET_BYTES)

    gateway = ScriptingGateway(
        [
            (read_more, Decimal("0.002"), "gw-1"),
            (final_plan, Decimal("0.003"), "gw-2"),
        ],
        on_planning_turn={1: refresh_target_before_guarded_read},
    )
    store = InMemoryAgentStateStore()
    intermediate_checks: list[str] = []

    def progress_observer(event: PlanningProgressEvent) -> None:
        if event.settled_turn == 1 and event.stop_reason is None:
            assert store.latest_plan_for_run(run_id="run-replan") is None
            intermediate_checks.append("checked")

    runner = _runner(tmp_path, gateway=gateway, store=store, progress_observer=progress_observer)

    result = runner.run(
        AgentRunRequest(
            run_id="run-replan",
            task="Update target.py",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path.resolve(),
            max_planning_turns=2,
        )
    )

    assert len(gateway.calls) == 2
    assert all(call["metadata"]["purpose"] == "planning_turn" for call in gateway.calls)
    turn_1_input = gateway.calls[0]["input_text"]
    turn_2_input = gateway.calls[1]["input_text"]
    assert MULTI_TURN_PLANNER_PROMPT_VERSION in turn_1_input
    assert WORKSPACE_FILES_HEADER in turn_1_input
    assert b"original" in turn_1_input.encode("utf-8")
    assert "Current guarded read evidence" in turn_2_input
    assert b"updated!" in turn_2_input.encode("utf-8")
    assert WORKSPACE_FILES_HEADER not in turn_2_input
    refreshed_sha256 = hashlib.sha256(_REFRESHED_TARGET_BYTES).hexdigest()
    assert refreshed_sha256 in turn_2_input
    assert b"original" not in turn_2_input.encode("utf-8").split(b"Current guarded read evidence", 1)[1]
    assert intermediate_checks == ["checked"]
    assert result.status is AgentRunStatus.AWAITING_APPROVAL
    assert result.stop_reason is None
    assert result.mutation_count == 0
    assert result.plan_hash == hashlib.sha256(final_plan.encode("utf-8")).hexdigest()
    stored = store.load_plan(run_id="run-replan", plan_hash=result.plan_hash or "")
    assert stored.planning_turns == 2
    assert stored.gateway_request_ids == ("gw-1", "gw-2")
    assert target.read_bytes() == _REFRESHED_TARGET_BYTES
