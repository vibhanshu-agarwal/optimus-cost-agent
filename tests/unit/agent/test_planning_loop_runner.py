from __future__ import annotations

import hashlib
import itertools
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from optimus.agent.planning_loop import (
    PlanningLoopPolicy,
    PlanningLoopRunner,
)
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.guardrails.pre_tool import PreToolGuard
from optimus.runtime.modes import ExecutionMode


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


def _runner(
    tmp_path: Path,
    *,
    gateway: ScriptingGateway,
    policy: PlanningLoopPolicy | None = None,
    max_cost_usd: Decimal = Decimal("0.05"),
    now: callable | None = None,
    halt_requested: callable | None = None,
) -> PlanningLoopRunner:
    return PlanningLoopRunner(
        gateway_client=gateway,
        model="glm-5.2",
        policy=policy or PlanningLoopPolicy(),
        workspace_root=tmp_path,
        execution_mode=ExecutionMode.AGENT,
        guard=PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=()),
        max_cost_usd=max_cost_usd,
        now=now,
        halt_requested=halt_requested,
    )


def _write_file(tmp_path: Path, relative_path: str, content: str) -> None:
    target = tmp_path / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


FINAL_PLAN = "READ src/a.py\nWRITE src/a.py\nupdated\nTEST pytest tests/unit -q\n"
READ_MORE_A = "OBSERVE: need header\nREAD: src/a.py#bytes=0:5\n"
REFUSE_TEXT = "REFUSE: Current raw evidence is insufficient for a safe write.\n"


def test_planning_loop_succeeds_on_first_turn_final_plan(tmp_path):
    gateway = ScriptingGateway([(FINAL_PLAN, Decimal("0.002"), "gw-1")])
    result = _runner(tmp_path, gateway=gateway, policy=PlanningLoopPolicy(max_planning_turns=1)).run(
        run_id="run-1",
        session_id="session-1",
        task="Update src/a.py",
        initial_workspace_context="seed context",
    )

    assert result.stop_reason is None
    assert result.settled_turns == 1
    assert result.plan_text == FINAL_PLAN
    assert result.plan_hash == hashlib.sha256(FINAL_PLAN.encode("utf-8")).hexdigest()
    assert result.refusal_reason is None
    assert result.total_cost_usd == Decimal("0.002")
    assert result.gateway_request_ids == ("gw-1",)


def test_planning_loop_maps_single_turn_read_more_to_turn_limit(tmp_path):
    _write_file(tmp_path, "src/a.py", "alpha")
    gateway = ScriptingGateway([(READ_MORE_A, Decimal("0.002"), "gw-1")])
    result = _runner(tmp_path, gateway=gateway, policy=PlanningLoopPolicy(max_planning_turns=1)).run(
        run_id="run-1",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="",
    )

    assert result.stop_reason == "PLANNING_TURN_LIMIT_EXHAUSTED"
    assert result.settled_turns == 1
    assert result.plan_hash is None
    assert result.plan_text is None


def test_planning_loop_succeeds_after_read_more_then_final(tmp_path):
    _write_file(tmp_path, "src/a.py", "alpha content")
    gateway = ScriptingGateway(
        [
            (READ_MORE_A, Decimal("0.002"), "gw-1"),
            (FINAL_PLAN, Decimal("0.002"), "gw-2"),
        ]
    )
    result = _runner(tmp_path, gateway=gateway, policy=PlanningLoopPolicy(max_planning_turns=2)).run(
        run_id="run-1",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="seed",
    )

    assert result.stop_reason is None
    assert result.settled_turns == 2
    assert result.plan_text == FINAL_PLAN
    assert result.total_cost_usd == Decimal("0.004")
    assert result.gateway_request_ids == ("gw-1", "gw-2")


def test_planning_loop_maps_repeated_read_request_to_typed_stop(tmp_path):
    _write_file(tmp_path, "src/a.py", "alpha")
    gateway = ScriptingGateway(
        [
            (READ_MORE_A, Decimal("0.001"), "gw-1"),
            (READ_MORE_A, Decimal("0.001"), "gw-2"),
        ]
    )
    result = _runner(tmp_path, gateway=gateway, policy=PlanningLoopPolicy(max_planning_turns=3)).run(
        run_id="run-1",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="",
    )

    assert result.stop_reason == "PLANNING_REPEATED_READ_REQUEST"
    assert result.settled_turns == 2
    assert result.plan_hash is None


def test_planning_loop_maps_budget_exhaustion_before_turn_limit(tmp_path):
    gateway = ScriptingGateway(
        [
            (READ_MORE_A.replace("src/a.py", "src/b.py"), Decimal("0.03"), "gw-1"),
            (FINAL_PLAN, Decimal("0.03"), "gw-2"),
        ]
    )
    _write_file(tmp_path, "src/b.py", "beta")
    result = _runner(
        tmp_path,
        gateway=gateway,
        policy=PlanningLoopPolicy(max_planning_turns=2),
        max_cost_usd=Decimal("0.05"),
    ).run(
        run_id="run-1",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="",
    )

    assert result.stop_reason == "PLANNING_BUDGET_EXHAUSTED"
    assert result.settled_turns == 2
    assert result.plan_hash is None


def test_planning_loop_maps_wall_clock_before_turn_limit(tmp_path):
    start = datetime(2026, 7, 6, tzinfo=UTC)
    gateway = ScriptingGateway([(READ_MORE_A, Decimal("0.001"), "gw-1")])
    _write_file(tmp_path, "src/a.py", "alpha")
    clock = itertools.chain(
        [start, start],
        itertools.repeat(start + timedelta(minutes=31)),
    )
    result = _runner(
        tmp_path,
        gateway=gateway,
        policy=PlanningLoopPolicy(max_planning_turns=3, max_wall_clock_minutes=30),
        now=lambda: next(clock),
    ).run(
        run_id="run-1",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="",
    )

    assert result.stop_reason == "PLANNING_WALL_CLOCK_EXHAUSTED"
    assert result.plan_hash is None


def test_planning_loop_maps_human_halt(tmp_path):
    gateway = ScriptingGateway([(FINAL_PLAN, Decimal("0.002"), "gw-1")])
    result = _runner(
        tmp_path,
        gateway=gateway,
        halt_requested=lambda: True,
    ).run(
        run_id="run-1",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="",
    )

    assert result.stop_reason == "PLANNING_HALTED"
    assert result.settled_turns == 0
    assert gateway.calls == []


def test_planning_loop_maps_refuse_to_model_refused(tmp_path):
    gateway = ScriptingGateway([(REFUSE_TEXT, Decimal("0.002"), "gw-1")])
    result = _runner(tmp_path, gateway=gateway).run(
        run_id="run-1",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="",
    )

    assert result.stop_reason == "PLANNING_MODEL_REFUSED"
    assert result.plan_hash is None
    assert result.plan_text is None
    assert "insufficient for a safe write" in result.corrective_text
    assert result.refusal_reason is not None


def test_planning_loop_stops_on_consecutive_unparseable_responses(tmp_path):
    gateway = ScriptingGateway(
        [
            ("Here is prose only.", Decimal("0.001"), "gw-1"),
            ("Still just prose.", Decimal("0.001"), "gw-2"),
        ]
    )
    result = _runner(tmp_path, gateway=gateway, policy=PlanningLoopPolicy(max_planning_turns=3)).run(
        run_id="run-1",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="",
    )

    assert result.stop_reason == "PLANNING_REPEATED_READ_REQUEST"
    assert result.settled_turns == 2


def test_planning_loop_recovers_after_one_unparseable_response(tmp_path):
    gateway = ScriptingGateway(
        [
            ("Here is prose only.", Decimal("0.001"), "gw-1"),
            (FINAL_PLAN, Decimal("0.002"), "gw-2"),
        ]
    )
    result = _runner(tmp_path, gateway=gateway, policy=PlanningLoopPolicy(max_planning_turns=3)).run(
        run_id="run-1",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="",
    )

    assert result.stop_reason is None
    assert result.settled_turns == 2
    assert result.plan_text == FINAL_PLAN


def test_planning_loop_stop_precedence_favors_repeated_failure(tmp_path):
    start = datetime(2026, 7, 6, tzinfo=UTC)
    gateway = ScriptingGateway(
        [
            (READ_MORE_A, Decimal("0.01"), "gw-1"),
            (READ_MORE_A, Decimal("0.01"), "gw-2"),
        ]
    )
    _write_file(tmp_path, "src/a.py", "alpha")
    result = _runner(
        tmp_path,
        gateway=gateway,
        policy=PlanningLoopPolicy(max_planning_turns=3, max_wall_clock_minutes=1),
        max_cost_usd=Decimal("0.05"),
        now=lambda: start + timedelta(minutes=5),
    ).run(
        run_id="run-1",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="",
    )

    assert result.stop_reason == "PLANNING_REPEATED_READ_REQUEST"
