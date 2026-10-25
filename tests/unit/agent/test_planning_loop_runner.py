from __future__ import annotations

import hashlib
import itertools
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import create_autospec

import pytest

from optimus.acp.debug_trace import configure_debug_trace, resolve_debug_log_path
from optimus.agent.planning_loop import (
    PlanningLoopPolicy,
    PlanningLoopRunner,
    PlanningProgressEvent,
    _PlanningIterationRunner,
)
from optimus.gateway.client import GatewayClient
from optimus.gateway.errors import GatewayHttpError
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.guardrails.pre_tool import PreToolGuard
from optimus.loops.controller import GoalLoopResult
from optimus.loops.models import IterationState, LoopStopReason
from optimus.retry.policy import RetryController, RetryPolicy
from optimus.runtime.modes import ExecutionMode


class ScriptingGateway:
    def __init__(self, scripts: list[tuple[str, Decimal, str]]) -> None:
        self._scripts = list(scripts)
        self.calls: list[dict[str, object]] = []
        self.checked = create_autospec(GatewayClient, instance=True, spec_set=True)
        self.checked.create_response.side_effect = self.create_response
        self.create_response = self.checked.create_response

    def create_response(self, *, model: str, input_text: str, metadata=None, route_binding=None) -> GatewayResponse:
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
    progress_observer: callable | None = None,
    usage_callback: callable | None = None,
) -> PlanningLoopRunner:
    return PlanningLoopRunner(
        gateway_client=getattr(gateway, "checked", gateway),
        model="glm-5.2",
        policy=policy or PlanningLoopPolicy(),
        workspace_root=tmp_path,
        execution_mode=ExecutionMode.AGENT,
        guard=PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=()),
        max_cost_usd=max_cost_usd,
        now=now,
        halt_requested=halt_requested,
        progress_observer=progress_observer,
        usage_callback=usage_callback,
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


def test_repeated_unparseable_responses_map_to_unparseable_stop(tmp_path):
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

    assert result.stop_reason == "PLANNING_UNPARSEABLE_RESPONSE"
    assert result.settled_turns == 2
    assert result.plan_hash is None
    assert result.plan_text is None
    assert "did not match the required directive grammar" in result.corrective_text
    assert "Here is prose only." not in result.corrective_text
    assert "Still just prose." not in result.corrective_text


def test_repeated_gateway_failures_map_to_gateway_failure_stop(tmp_path):
    class FailingGateway(ScriptingGateway):
        def create_response(
            self,
            *,
            model: str,
            input_text: str,
            metadata: dict[str, object] | None = None,
        ) -> GatewayResponse:
            raise RuntimeError("gateway unavailable")

    result = _runner(
        tmp_path,
        gateway=FailingGateway([]),
        policy=PlanningLoopPolicy(max_planning_turns=3),
    ).run(
        run_id="run-1",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="",
    )

    # RuntimeError is not a typed GatewayError — unknown transport cost.
    assert result.stop_reason == "PLANNING_GATEWAY_COST_UNKNOWN"
    assert result.gateway_request_ids == ()
    assert result.total_cost_usd == Decimal("0")
    assert result.cost_complete is False
    assert result.unknown_cost_attempt_count == 1


def test_repeated_identical_read_more_maps_to_read_stop(tmp_path):
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


def test_refusal_wins_accumulated_repeated_failure(tmp_path):
    gateway = ScriptingGateway(
        [
            ("Here is prose only.", Decimal("0.001"), "gw-1"),
            (REFUSE_TEXT, Decimal("0.001"), "gw-2"),
        ]
    )
    result = _runner(
        tmp_path,
        gateway=gateway,
        policy=PlanningLoopPolicy(max_planning_turns=3),
        max_cost_usd=Decimal("0.002"),
    ).run(
        run_id="run-1",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="",
    )

    assert result.stop_reason == "PLANNING_MODEL_REFUSED"
    assert result.settled_turns == 2
    assert result.plan_hash is None


def test_refusal_wins_budget_equality(tmp_path):
    gateway = ScriptingGateway([(REFUSE_TEXT, Decimal("0.002"), "gw-1")])
    result = _runner(tmp_path, gateway=gateway, max_cost_usd=Decimal("0.002")).run(
        run_id="run-1",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="",
    )

    assert result.stop_reason == "PLANNING_MODEL_REFUSED"
    assert result.plan_hash is None


def test_refusal_wins_wall_clock(tmp_path):
    start = datetime(2026, 7, 6, tzinfo=UTC)
    late = start + timedelta(minutes=31)
    now_value = {"current": start}

    class WallClockAfterFirstTurnGateway(ScriptingGateway):
        def create_response(self, *, model: str, input_text: str, metadata: dict[str, object] | None = None):
            response = super().create_response(model=model, input_text=input_text, metadata=metadata)
            if len(self.calls) >= 2:
                now_value["current"] = late
            return response

    gateway = WallClockAfterFirstTurnGateway(
        [
            (READ_MORE_A, Decimal("0.001"), "gw-1"),
            (REFUSE_TEXT, Decimal("0.001"), "gw-2"),
        ]
    )
    _write_file(tmp_path, "src/a.py", "alpha")
    result = _runner(
        tmp_path,
        gateway=gateway,
        policy=PlanningLoopPolicy(max_planning_turns=3, max_wall_clock_minutes=30),
        now=lambda: now_value["current"],
    ).run(
        run_id="run-1",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="",
    )

    assert result.stop_reason == "PLANNING_MODEL_REFUSED"
    assert result.settled_turns == 2
    assert result.plan_hash is None


def test_human_halt_wins_refusal_race(tmp_path):
    halt_after_response = {"active": False}

    class HaltAfterResponseGateway(ScriptingGateway):
        def create_response(self, *, model: str, input_text: str, metadata: dict[str, object] | None = None):
            response = super().create_response(model=model, input_text=input_text, metadata=metadata)
            halt_after_response["active"] = True
            return response

    gateway = HaltAfterResponseGateway([(REFUSE_TEXT, Decimal("0.002"), "gw-1")])
    result = _runner(
        tmp_path,
        gateway=gateway,
        halt_requested=lambda: halt_after_response["active"],
    ).run(
        run_id="run-1",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="",
    )

    assert result.stop_reason == "PLANNING_HALTED"
    assert result.plan_hash is None


def _preselected_non_completed_loop_result(stop_reason: LoopStopReason, *, iteration: int = 2) -> GoalLoopResult:
    """Fabricate a controller result after stop selection and before conversion."""
    return GoalLoopResult(
        state=IterationState(
            run_id="run-1",
            session_id=None,
            goal="Update src/a.py",
            completion_condition="final plan",
            started_at=datetime(2026, 7, 6, tzinfo=UTC),
            iteration=iteration,
            cost_usd_spent=Decimal("0.004"),
        ),
        stop_reason=stop_reason,
        summary="controller stopped",
    )


def _iteration_runner_for_conversion(
    tmp_path: Path,
    *,
    halt_requested,
) -> _PlanningIterationRunner:
    policy = PlanningLoopPolicy()
    max_cost_usd = Decimal("0.05")
    return _PlanningIterationRunner(
        gateway_client=ScriptingGateway([]).checked,
        model="glm-5.2",
        task="Update src/a.py",
        initial_workspace_context="",
        initial_workspace_file_sizes={},
        workspace_root=tmp_path,
        run_id="run-1",
        session_id=None,
        execution_mode=ExecutionMode.AGENT,
        policy=policy,
        loop_budget_policy=policy.to_loop_budget_policy(max_cost_usd=max_cost_usd),
        max_cost_usd=max_cost_usd,
        now=lambda: datetime(2026, 7, 6, tzinfo=UTC),
        usage_callback=None,
        retry_controller=RetryController(
            policy=RetryPolicy(base_delay_ms=0, jitter_ms=(0,)),
            sleep_ms=lambda _delay_ms: None,
        ),
        progress_observer=None,
        halt_requested=halt_requested,
        guard=PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=()),
    )


@pytest.mark.parametrize(
    ("stop_reason", "mapped_without_halt"),
    [
        (LoopStopReason.REPEATED_FAILURE, "PLANNING_REPEATED_READ_REQUEST"),
        (LoopStopReason.BUDGET_EXHAUSTED, "PLANNING_BUDGET_EXHAUSTED"),
        (LoopStopReason.WALL_CLOCK, "PLANNING_WALL_CLOCK_EXHAUSTED"),
        (LoopStopReason.MAX_ITERATIONS, "PLANNING_TURN_LIMIT_EXHAUSTED"),
    ],
)
def test_halt_wins_over_preselected_non_completed_stop(
    tmp_path: Path,
    stop_reason: LoopStopReason,
    mapped_without_halt: str,
) -> None:
    """DoD 5.21 sixth family: late halt after non-COMPLETED stop selection.

    Halt becomes true after the controller already selected REPEATED_FAILURE /
    BUDGET_EXHAUSTED / WALL_CLOCK / MAX_ITERATIONS, before to_planning_result()
    dispatches that stop. The preselected mapped stop must not be reported.
    """
    loop_result = _preselected_non_completed_loop_result(stop_reason)

    without_halt = _iteration_runner_for_conversion(tmp_path, halt_requested=lambda: False)
    assert without_halt.to_planning_result(loop_result).stop_reason == mapped_without_halt

    halt_armed = {"active": False}

    def halt_after_stop_selection() -> bool:
        return halt_armed["active"]

    with_halt = _iteration_runner_for_conversion(tmp_path, halt_requested=halt_after_stop_selection)
    # Simulate the race window: stop already selected; halt flips before conversion.
    halt_armed["active"] = True
    halted = with_halt.to_planning_result(loop_result)
    assert halted.stop_reason == "PLANNING_HALTED"
    assert halted.settled_turns == loop_result.state.iteration
    assert halted.plan_hash is None
    assert halted.plan_text is None


def test_final_plan_at_budget_equality_has_no_hash(tmp_path):
    gateway = ScriptingGateway([(FINAL_PLAN, Decimal("0.002"), "gw-1")])
    result = _runner(tmp_path, gateway=gateway, max_cost_usd=Decimal("0.002")).run(
        run_id="run-1",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="",
    )

    assert result.stop_reason == "PLANNING_BUDGET_EXHAUSTED"
    assert result.settled_turns == 1
    assert result.plan_hash is None
    assert result.plan_text is None


def test_final_plan_loses_wall_clock_has_no_hash(tmp_path):
    start = datetime(2026, 7, 6, tzinfo=UTC)
    late = start + timedelta(minutes=31)
    gateway = ScriptingGateway([(FINAL_PLAN, Decimal("0.002"), "gw-1")])
    clock = itertools.chain([start, start], itertools.repeat(late))
    result = _runner(
        tmp_path,
        gateway=gateway,
        policy=PlanningLoopPolicy(max_wall_clock_minutes=30),
        now=lambda: next(clock),
    ).run(
        run_id="run-1",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="",
    )

    assert result.stop_reason == "PLANNING_WALL_CLOCK_EXHAUSTED"
    assert result.settled_turns == 1
    assert result.plan_hash is None
    assert result.plan_text is None


def test_refusal_reason_is_sanitized_before_planning_result(tmp_path):
    workspace_path = str(tmp_path.resolve())
    raw_reason = f"Inspect {workspace_path}; token PLAN987_SECRET_SENTINEL"
    gateway = ScriptingGateway([(f"REFUSE: {raw_reason}\n", Decimal("0.002"), "gw-1")])
    result = _runner(tmp_path, gateway=gateway).run(
        run_id="run-1",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="",
    )

    assert result.stop_reason == "PLANNING_MODEL_REFUSED"
    assert "<workspace>" in result.corrective_text
    assert "token **********" in result.corrective_text
    assert workspace_path not in result.corrective_text
    assert "PLAN987_SECRET_SENTINEL" not in result.corrective_text
    assert result.refusal_reason is not None
    assert workspace_path not in result.refusal_reason
    assert "PLAN987_SECRET_SENTINEL" not in result.refusal_reason


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


def test_planning_loop_emits_final_progress_event_with_stop_reason_on_typed_failure(tmp_path):
    _write_file(tmp_path, "src/a.py", "alpha")
    gateway = ScriptingGateway(
        [
            (READ_MORE_A, Decimal("0.001"), "gw-1"),
            (READ_MORE_A, Decimal("0.001"), "gw-2"),
        ]
    )
    events: list[PlanningProgressEvent] = []
    result = _runner(
        tmp_path,
        gateway=gateway,
        policy=PlanningLoopPolicy(max_planning_turns=3),
        progress_observer=events.append,
    ).run(
        run_id="run-1",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="",
    )

    assert result.stop_reason == "PLANNING_REPEATED_READ_REQUEST"
    # Two READ_MORE progress events (one per turn) plus one final settlement event.
    assert len(events) == 3
    assert events[0].stop_reason is None
    assert events[1].stop_reason is None
    assert events[-1].stop_reason == "PLANNING_REPEATED_READ_REQUEST"
    assert events[-1].settled_turn == result.settled_turns
    assert events[-1].gateway_request_ids == result.gateway_request_ids


def test_planning_loop_emits_final_progress_event_on_success(tmp_path):
    _write_file(tmp_path, "src/a.py", "alpha content")
    gateway = ScriptingGateway(
        [
            (READ_MORE_A, Decimal("0.002"), "gw-1"),
            (FINAL_PLAN, Decimal("0.002"), "gw-2"),
        ]
    )
    events: list[PlanningProgressEvent] = []
    result = _runner(
        tmp_path,
        gateway=gateway,
        policy=PlanningLoopPolicy(max_planning_turns=2),
        progress_observer=events.append,
    ).run(
        run_id="run-1",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="seed",
    )

    assert result.stop_reason is None
    assert result.plan_text == FINAL_PLAN
    # One READ_MORE progress event plus one final settlement event.
    assert len(events) == 2
    assert events[0].stop_reason is None
    assert events[-1].stop_reason is None
    assert events[-1].settled_turn == result.settled_turns


def test_planning_loop_skips_final_progress_event_when_nothing_settled(tmp_path):
    gateway = ScriptingGateway([(FINAL_PLAN, Decimal("0.002"), "gw-1")])
    events: list[PlanningProgressEvent] = []
    result = _runner(
        tmp_path,
        gateway=gateway,
        halt_requested=lambda: True,
        progress_observer=events.append,
    ).run(
        run_id="run-1",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="",
    )

    assert result.stop_reason == "PLANNING_HALTED"
    assert result.settled_turns == 0
    assert events == []


def test_planning_loop_maps_observation_carryover_overflow_to_typed_stop(tmp_path):
    _write_file(tmp_path, "large.py", "x" * (17 * 1024))
    from optimus.agent.planning_loop import PlanningReadRequest, max_planning_observation_text_bytes

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
    gateway = ScriptingGateway(scripts)
    result = _runner(tmp_path, gateway=gateway, policy=PlanningLoopPolicy(max_planning_turns=8)).run(
        run_id="run-1",
        session_id=None,
        task="Update large.py",
        initial_workspace_context="",
    )

    assert result.stop_reason == "PLANNING_OBSERVATION_BUDGET_EXHAUSTED"
    assert result.plan_hash is None
    assert "observation evidence exceeds" in result.corrective_text


def test_planning_loop_maps_current_read_overflow_to_typed_stop(tmp_path):
    from optimus.agent.planning_loop import PLANNING_NEW_READ_MAX_BYTES

    _write_file(tmp_path, "large.py", "x" * (17 * 1024))
    oversized_read = PLANNING_NEW_READ_MAX_BYTES + 500
    read_more = f"OBSERVE: need large chunk\nREAD: large.py#bytes=0:{oversized_read}\n"
    gateway = ScriptingGateway(
        [
            (read_more, Decimal("0.001"), "gw-1"),
            (FINAL_PLAN.replace("src/a.py", "large.py"), Decimal("0.001"), "gw-2"),
        ]
    )
    result = _runner(tmp_path, gateway=gateway, policy=PlanningLoopPolicy(max_planning_turns=2)).run(
        run_id="run-1",
        session_id=None,
        task="Update large.py",
        initial_workspace_context="",
    )

    assert result.stop_reason == "PLANNING_READ_BUDGET_EXHAUSTED"
    assert result.plan_hash is None
    assert "read evidence exceeds" in result.corrective_text


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


def test_planning_loop_logs_rejected_read_path_to_debug_trace(tmp_path):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)

    read_missing = "OBSERVE: need policy\nREAD: policy.txt#bytes=0:1024\n"
    gateway = ScriptingGateway([(read_missing, Decimal("0.001"), "gw-1")])
    result = _runner(tmp_path, gateway=gateway).run(
        run_id="run-read-reject",
        session_id="session-read-reject",
        task="Update target.py",
        initial_workspace_context="",
    )

    assert result.stop_reason == "PLANNING_READ_FILE_NOT_FOUND"
    assert "policy.txt" not in result.corrective_text

    lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").strip().splitlines()]
    reject_lines = [line for line in lines if line.get("hypothesisId") == "P9.87-READ-REJECT"]
    assert len(reject_lines) == 1
    data = reject_lines[0]["data"]
    assert data["rejected_path"] == "policy.txt"
    assert data["stop_reason"] == "PLANNING_READ_FILE_NOT_FOUND"
    assert data["start_byte"] == 0
    assert data["end_byte"] == 1024
    assert data["run_id"] == "run-read-reject"


# --- Plan 9.95 Task 2 Step 1: failing aggregation and terminal-state tests ---


class FailThenSucceedGateway:
    """First call raises GatewayHttpError 503 with valid usage, second returns success."""

    def __init__(self) -> None:
        self.attempts = 0

    def create_response(
        self,
        *,
        model: str,
        input_text: str,
        metadata: dict[str, object] | None = None,
    ) -> GatewayResponse:
        self.attempts += 1
        if self.attempts == 1:
            raise GatewayHttpError(
                503,
                "temporary overload",
                gateway_usage=GatewayUsage(
                    gateway_request_id="gw-failed-1",
                    provider="glm",
                    billing_units=5,
                    cost_usd=Decimal("0.001"),
                ),
            )
        return GatewayResponse(
            response_id="resp-success-2",
            output_text=FINAL_PLAN,
            gateway_usage=GatewayUsage(
                gateway_request_id="gw-success-2",
                provider="glm",
                billing_units=10,
                cost_usd=Decimal("0.002"),
            ),
            raw={"id": "resp-success-2"},
        )


class PermanentFailWithUsageGateway:
    """Raises GatewayHttpError 400 (permanent) with valid usage."""

    def __init__(self) -> None:
        self.attempts = 0

    def create_response(
        self,
        *,
        model: str,
        input_text: str,
        metadata: dict[str, object] | None = None,
    ) -> GatewayResponse:
        self.attempts += 1
        raise GatewayHttpError(
            400,
            "bad request",
            gateway_usage=GatewayUsage(
                gateway_request_id="gw-perm-1",
                provider="glm",
                billing_units=3,
                cost_usd=Decimal("0.001"),
            ),
        )


class UnknownCostGateway:
    """Raises GatewayHttpError 503 without valid usage (unknown cost)."""

    def __init__(self) -> None:
        self.attempts = 0

    def create_response(
        self,
        *,
        model: str,
        input_text: str,
        metadata: dict[str, object] | None = None,
    ) -> GatewayResponse:
        self.attempts += 1
        raise GatewayHttpError(503, "temporary outage")


class ReportedThenUnknownGateway:
    """First call has valid usage (503), second has no usage (503)."""

    def __init__(self) -> None:
        self.attempts = 0

    def create_response(
        self,
        *,
        model: str,
        input_text: str,
        metadata: dict[str, object] | None = None,
    ) -> GatewayResponse:
        self.attempts += 1
        if self.attempts == 1:
            raise GatewayHttpError(
                503,
                "first failure with usage",
                gateway_usage=GatewayUsage(
                    gateway_request_id="gw-reported-1",
                    provider="glm",
                    billing_units=5,
                    cost_usd=Decimal("0.001"),
                ),
            )
        raise GatewayHttpError(503, "second failure no usage")


class BudgetCapGateway:
    """503 with valid usage that exactly hits the budget cap."""

    def __init__(self) -> None:
        self.attempts = 0

    def create_response(
        self,
        *,
        model: str,
        input_text: str,
        metadata: dict[str, object] | None = None,
    ) -> GatewayResponse:
        self.attempts += 1
        raise GatewayHttpError(
            503,
            "overloaded",
            gateway_usage=GatewayUsage(
                gateway_request_id="gw-cap-1",
                provider="glm",
                billing_units=50,
                cost_usd=Decimal("0.005"),
            ),
        )


class UnexpectedExceptionGateway:
    """Raises TypeError (unexpected non-Gateway exception)."""

    def __init__(self) -> None:
        self.attempts = 0
        self.checked = create_autospec(GatewayClient, instance=True, spec_set=True)
        self.checked.create_response.side_effect = self.create_response
        self.create_response = self.checked.create_response

    def create_response(self, *, model: str, input_text: str, metadata=None, route_binding=None) -> GatewayResponse:
        self.attempts += 1
        raise TypeError("SENTINEL-PAYLOAD-BUG")


def test_reported_transient_failure_then_success_aggregates_both_wire_attempts(tmp_path):
    gateway = FailThenSucceedGateway()
    callback_attempts: list[tuple[int, int, str]] = []

    def usage_cb(usage: GatewayUsage, planning_turn: int, wire_attempt: int) -> None:
        callback_attempts.append((planning_turn, wire_attempt, usage.gateway_request_id))

    result = _runner(tmp_path, gateway=gateway, usage_callback=usage_cb).run(
        run_id="run-retry-agg",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="",
    )

    assert result.total_cost_usd == Decimal("0.003")
    assert result.gateway_request_ids == ("gw-failed-1", "gw-success-2")
    assert result.cost_complete is True
    assert result.unknown_cost_attempt_count == 0
    assert callback_attempts == [(1, 1, "gw-failed-1"), (1, 2, "gw-success-2")]


def test_reported_permanent_failure_is_charged_before_gateway_stop(tmp_path):
    gateway = PermanentFailWithUsageGateway()
    callback_attempts: list[tuple[int, int, str]] = []

    def usage_cb(usage: GatewayUsage, planning_turn: int, wire_attempt: int) -> None:
        callback_attempts.append((planning_turn, wire_attempt, usage.gateway_request_id))

    result = _runner(tmp_path, gateway=gateway, usage_callback=usage_cb).run(
        run_id="run-perm-fail",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="",
    )

    assert gateway.attempts == 1
    assert result.stop_reason == "PLANNING_GATEWAY_FAILURE"
    assert result.total_cost_usd == Decimal("0.001")
    assert result.gateway_request_ids == ("gw-perm-1",)
    assert result.cost_complete is True
    assert result.unknown_cost_attempt_count == 0
    assert callback_attempts == [(1, 1, "gw-perm-1")]
    assert result.plan_hash is None


def test_unknown_transport_cost_stops_before_retry(tmp_path):
    gateway = UnknownCostGateway()

    result = _runner(tmp_path, gateway=gateway).run(
        run_id="run-unknown",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="",
    )

    assert gateway.attempts == 1
    assert result.stop_reason == "PLANNING_GATEWAY_COST_UNKNOWN"
    assert result.total_cost_usd == Decimal("0")
    assert result.cost_complete is False
    assert result.unknown_cost_attempt_count == 1
    assert result.plan_hash is None


def test_unknown_after_reported_failure_retains_known_cost_lower_bound(tmp_path):
    gateway = ReportedThenUnknownGateway()

    result = _runner(tmp_path, gateway=gateway).run(
        run_id="run-partial-unknown",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="",
    )

    # First attempt has reported cost, second is unknown → stops
    assert gateway.attempts == 2
    assert result.stop_reason == "PLANNING_GATEWAY_COST_UNKNOWN"
    assert result.total_cost_usd == Decimal("0.001")  # known lower bound
    assert result.cost_complete is False
    assert result.unknown_cost_attempt_count == 1
    assert result.gateway_request_ids == ("gw-reported-1",)
    assert result.plan_hash is None


def test_reported_failed_attempt_at_budget_cap_stops_before_retry(tmp_path):
    gateway = BudgetCapGateway()

    # max_cost_usd = 0.005 and the first failure costs exactly 0.005
    result = _runner(tmp_path, gateway=gateway, max_cost_usd=Decimal("0.005")).run(
        run_id="run-cap",
        session_id=None,
        task="Update src/a.py",
        initial_workspace_context="",
    )

    assert gateway.attempts == 1
    assert result.stop_reason == "PLANNING_BUDGET_EXHAUSTED"
    assert result.total_cost_usd == Decimal("0.005")
    assert result.cost_complete is True
    assert result.unknown_cost_attempt_count == 0
    assert result.gateway_request_ids == ("gw-cap-1",)
    assert result.plan_hash is None


def test_unexpected_attempt_exception_logs_type_only_and_stops_cost_unknown(tmp_path):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)

    gateway = UnexpectedExceptionGateway()

    result = _runner(tmp_path, gateway=gateway).run(
        run_id="run-unexpected",
        session_id="session-unexpected",
        task="Update src/a.py",
        initial_workspace_context="",
    )

    assert gateway.attempts == 1
    assert result.stop_reason == "PLANNING_GATEWAY_COST_UNKNOWN"
    assert result.total_cost_usd == Decimal("0")
    assert result.cost_complete is False
    assert result.unknown_cost_attempt_count == 1
    assert result.plan_hash is None

    # Verify the debug record
    lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").strip().splitlines()]
    usage_unknown_lines = [line for line in lines if line.get("hypothesisId") == "P9.95-USAGE-UNKNOWN"]
    assert len(usage_unknown_lines) == 1
    record = usage_unknown_lines[0]
    assert record["data"]["error_type"] == "TypeError"
    assert record["data"]["run_id"] == "run-unexpected"
    assert record["data"]["session_id"] == "session-unexpected"
    assert record["data"]["planning_turn"] == 1
    assert record["data"]["wire_attempt"] == 1
    # Must NOT contain the exception message or traceback
    record_str = json.dumps(record)
    assert "SENTINEL-PAYLOAD-BUG" not in record_str

    # Corrective text must not contain the exception message
    assert "SENTINEL-PAYLOAD-BUG" not in result.corrective_text


# --- Plan 9.95 Task 4 Step 1: non-alphabetical multi-file read regression ---


def test_non_alphabetical_multi_file_read_telemetry_preserves_association(tmp_path):
    """Read execution order zeta.py then alpha.py must not misattribute hashes or byte counts."""
    import hashlib as _hashlib

    _write_file(tmp_path, "zeta.py", "ZZZ")              # read bytes=0:3 → 3 bytes
    _write_file(tmp_path, "alpha.py", "xxAAAAAxx")       # read bytes=2:9 → 7 bytes

    zeta_content = "ZZZ"
    alpha_content = "xxAAAAAxx"
    zeta_sha = _hashlib.sha256(zeta_content.encode("utf-8")).hexdigest()
    alpha_sha = _hashlib.sha256(alpha_content.encode("utf-8")).hexdigest()

    # The gateway response reads zeta.py first, then alpha.py (non-alphabetical execution order).
    read_both = "OBSERVE: need both files\nREAD: zeta.py#bytes=0:3\nREAD: alpha.py#bytes=2:9\n"
    gateway = ScriptingGateway(
        [
            (read_both, Decimal("0.001"), "gw-1"),
            (FINAL_PLAN, Decimal("0.001"), "gw-2"),
        ]
    )
    events: list[PlanningProgressEvent] = []
    result = _runner(
        tmp_path,
        gateway=gateway,
        policy=PlanningLoopPolicy(max_planning_turns=2),
        progress_observer=events.append,
    ).run(
        run_id="run-assoc",
        session_id=None,
        task="Update zeta.py and alpha.py",
        initial_workspace_context="",
    )

    assert result.stop_reason is None
    # The first progress event is the READ_MORE turn.
    event = events[0]
    # Canonical order is alphabetical by (path, start_byte, end_byte, sha256).
    # alpha.py comes before zeta.py.
    assert event.read_identities == (
        "alpha.py#bytes=2:9",
        "zeta.py#bytes=0:3",
    )
    assert event.source_sha256s == (alpha_sha, zeta_sha)
    assert event.read_byte_counts == (7, 3)


def test_planning_loop_runner_accepts_keyword_only_client_mcp_service(tmp_path):
    from optimus.agent.models import AgentMcpToolOutput, AgentToolCall

    class _Svc:
        def list_tools(self, server: str):
            return (
                AgentMcpToolOutput(server_name=server, tool_name="mcp_list_tools", text='{"tools":["t"]}'),
                AgentToolCall(tool_name="mcp_list_tools", summary="listed", authorization_outcome="ALLOW"),
            )

    (tmp_path / "a.py").write_text("x\n", encoding="utf-8")
    gateway = ScriptingGateway(
        [
            ("MCP_LIST tools\n", Decimal("0.001"), "gw-1"),
            ("WRITE a.py\ny\n", Decimal("0.001"), "gw-2"),
        ]
    )
    result = PlanningLoopRunner(
        gateway_client=getattr(gateway, "checked", gateway),
        model="glm-5.2",
        policy=PlanningLoopPolicy(max_planning_turns=3),
        workspace_root=tmp_path,
        execution_mode=ExecutionMode.AGENT,
        guard=PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=()),
        max_cost_usd=Decimal("0.05"),
        client_mcp_service=_Svc(),
    ).run(run_id="run-mcp", session_id=None, task="mcp then write")
    assert result.stop_reason is None
    assert "client_mcp_service" not in result.model_dump()
    assert len(gateway.calls) == 2
    assert "untrusted" in str(gateway.calls[1]["input_text"]).lower()


def test_contract_gateway_boundary_rejects_unknown_attributes():
    script = ScriptingGateway([])
    boundary = getattr(script, "checked", script)
    with pytest.raises(AttributeError):
        boundary.unknown_gateway_operation = True
    with pytest.raises(TypeError):
        boundary.create_response(model="model", input_text="input", obsolete_route=True)


# --- #388: recovery and diagnosability after a turn that makes no progress ---

SIZES_HEADER = "Known byte sizes for fully visible turn-1 files:"
_SIZE_LIST_LINE = re.compile(r"^- (\S+): (\d+) bytes; re-read as READ: ", re.MULTILINE)
TARGET_SOURCE = "def target():\n    return 1\n"
TARGET_FINAL_PLAN = "READ target.py\nWRITE target.py\ndef target():\n    return 2\n"
PROSE = "Here is prose only."


class SizeListReadGateway(ScriptingGateway):
    """Turn 2 re-reads only what the size list in the input it actually receives names, and refuses
    without one, as the prompt's re-read rule requires. A fixed script would pass on the unfixed loop,
    because guarded reads never check that their size was shown (Codex round 34)."""

    def create_response(self, *, model, input_text, metadata=None):
        if len(self.calls) == 1:
            sizes = _SIZE_LIST_LINE.findall(input_text)
            reply = (
                "OBSERVE: re-read the listed files\n" + "".join(f"READ: {path}#bytes=0:{size}\n" for path, size in sizes)
                if sizes
                else "REFUSE: no listed byte size to ground the re-read.\n"
            )
            self._scripts[0] = (reply, *self._scripts[0][1:])
        return super().create_response(model=model, input_text=input_text, metadata=metadata)


def _scripts(*replies: str) -> list[tuple[str, Decimal, str]]:
    return [(reply, Decimal("0.001"), f"gw-{index}") for index, reply in enumerate(replies, start=1)]


def _run_target(tmp_path: Path, gateway: ScriptingGateway, **kwargs):
    _write_file(tmp_path, "target.py", TARGET_SOURCE)
    return _runner(tmp_path, gateway=gateway, **kwargs).run(
        run_id="run-388",
        session_id="session-388",
        task="Update target.py",
        initial_workspace_context="SEED-CONTEXT-388\n" + TARGET_SOURCE,
        initial_workspace_file_sizes={"target.py": (tmp_path / "target.py").stat().st_size},
    )


def _size_line(tmp_path: Path) -> str:
    size = (tmp_path / "target.py").stat().st_size
    return f"- target.py: {size} bytes; re-read as READ: target.py#bytes=0:{size}"


def _nonprogress_records(log_path: Path) -> list[dict]:
    lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    return [line for line in lines if line.get("hypothesisId") == "P12.2-NONPROGRESS"]


def test_size_list_survives_an_unparseable_first_turn(tmp_path):
    gateway = ScriptingGateway(_scripts(PROSE, REFUSE_TEXT))
    _run_target(tmp_path, gateway)

    second = gateway.calls[1]["input_text"]
    assert _size_line(tmp_path) in second
    assert "SEED-CONTEXT-388" not in second, "the raw context stays turn-1-only (Plan 9.87)"


def test_size_list_survives_an_mcp_first_turn(tmp_path):
    gateway = ScriptingGateway(_scripts("MCP_LIST tools\n", REFUSE_TEXT))
    _run_target(tmp_path, gateway)

    second = gateway.calls[1]["input_text"]
    assert _size_line(tmp_path) in second
    assert "SEED-CONTEXT-388" not in second


def test_size_list_is_not_sent_after_a_read_turn(tmp_path):
    gateway = ScriptingGateway(_scripts("OBSERVE: need the header\nREAD: target.py#bytes=0:5\n", REFUSE_TEXT))
    _run_target(tmp_path, gateway)

    assert SIZES_HEADER in gateway.calls[0]["input_text"]
    assert SIZES_HEADER not in gateway.calls[1]["input_text"]


def test_unparseable_first_turn_recovers_through_a_listed_size_read(tmp_path):
    gateway = SizeListReadGateway(_scripts(PROSE, "", TARGET_FINAL_PLAN))
    result = _run_target(tmp_path, gateway)

    assert result.stop_reason is None, result.corrective_text
    assert result.settled_turns == 3
    assert result.plan_hash is not None
    assert len(gateway.calls) == 3
    third = gateway.calls[2]["input_text"]
    assert "Current guarded read evidence" in third
    assert SIZES_HEADER not in third


def test_unparseable_turn_writes_one_content_free_nonprogress_record(tmp_path):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)
    reply = "Prose only — no directives."
    _run_target(tmp_path, ScriptingGateway(_scripts(reply, REFUSE_TEXT)))

    [record] = _nonprogress_records(log_path)
    assert record["location"] == "planning_loop.py:execute_iteration:unparseable"
    assert record["data"] == {
        "run_id": "run-388",
        "session_id": "session-388",
        "planning_turn": 1,
        "kind": "UNPARSEABLE",
        "reason_code": "GRAMMAR_UNRECOGNIZED",
        "output_bytes": len(reply.encode("utf-8")),
    }


def test_mcp_turn_writes_one_nonprogress_record_with_bounded_outcome(tmp_path):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)
    reply = "MCP_LIST canary388server\n"
    # No client MCP service: the real toolbox answers BLOCK.
    _run_target(tmp_path, ScriptingGateway(_scripts(reply, REFUSE_TEXT)))

    [record] = _nonprogress_records(log_path)
    assert record["location"] == "planning_loop.py:execute_iteration:mcp_tool"
    assert record["data"] == {
        "run_id": "run-388",
        "session_id": "session-388",
        "planning_turn": 1,
        "kind": "MCP_TOOL",
        "output_bytes": len(reply.encode("utf-8")),
        "mcp_operation": "list",
        "authorization_outcome": "BLOCK",
    }
    assert "canary388server" not in json.dumps(record)


def test_two_unparseable_turns_write_two_records_and_keep_the_unparseable_stop(tmp_path):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)
    result = _run_target(tmp_path, ScriptingGateway(_scripts(PROSE, "Still just prose.")))

    assert result.stop_reason == "PLANNING_UNPARSEABLE_RESPONSE"
    assert result.settled_turns == 2
    assert [record["data"]["planning_turn"] for record in _nonprogress_records(log_path)] == [1, 2]


@pytest.mark.parametrize(
    ("template", "reason_code"),
    [
        ("OBSERVE: need it\nREAD: {canary}#bytes=0:10\nREAD: {canary}#bytes=0:10\n", "READ_RANGES_DUPLICATE"),
        ("OBSERVE: need it\nREAD: {canary}#bytes=0:10\nREAD: {canary}#bytes=5:15\n", "READ_RANGES_OVERLAP"),
        ("{canary} is all I will say.", "GRAMMAR_UNRECOGNIZED"),
    ],
    ids=["duplicate-ranges", "overlapping-ranges", "free-text"],
)
def test_nonprogress_trace_never_carries_reply_content(tmp_path, template, reason_code):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log_path)
    canary = f"CANARY-PATH-{uuid.uuid4().hex}"
    _run_target(
        tmp_path,
        ScriptingGateway(_scripts(template.format(canary=canary))),
        policy=PlanningLoopPolicy(max_planning_turns=1),
    )

    [record] = _nonprogress_records(log_path)
    assert record["data"]["reason_code"] == reason_code
    assert canary not in log_path.read_text(encoding="utf-8")


# --- #403 (option B, Codex round 44): bounded corrective feedback after an unparseable turn ----------------------

MISSING_OBSERVE = "READ: target.py#bytes=0:10\n"  # run 3's observed omission: a ranged READ without OBSERVE


def _notice(code: str) -> str:
    from optimus.agent.planning_loop import PLANNING_PARSE_FEEDBACK

    return PLANNING_PARSE_FEEDBACK[code]


class NoticeFollowingGateway(ScriptingGateway):
    """Turn 2 recovers only when its input carries the OBSERVE notice; without it, it repeats run 3's omission, so the
    unfixed loop stops at the repeat limit (Codex round 44: a double that cannot recover without the notice)."""

    def create_response(self, *, model, input_text, metadata=None):
        if len(self.calls) == 1:
            size = (self.workspace / "target.py").stat().st_size
            reply = f"OBSERVE: re-read target.py\nREAD: target.py#bytes=0:{size}\n" if _notice("INTERMEDIATE_REQUIRES_OBSERVE") in input_text else MISSING_OBSERVE
            self._scripts[0] = (reply, *self._scripts[0][1:])
        return super().create_response(model=model, input_text=input_text, metadata=metadata)


def test_the_feedback_table_covers_exactly_the_closed_codes_with_fixed_text():
    from optimus.agent.planning_loop import PLANNING_PARSE_FEEDBACK, PLANNING_TURN_PARSE_CODES

    assert set(PLANNING_PARSE_FEEDBACK) == PLANNING_TURN_PARSE_CODES
    for code, text in PLANNING_PARSE_FEEDBACK.items():
        assert text and "{" not in text and "}" not in text, code  # fixed text: nothing is ever interpolated
        assert text == text.strip() and "\n" not in text, code


def test_a_malformed_turn_recovers_through_the_notice_to_a_grounded_plan(tmp_path):
    gateway = NoticeFollowingGateway(_scripts(MISSING_OBSERVE, "", TARGET_FINAL_PLAN))
    gateway.workspace = tmp_path
    result = _run_target(tmp_path, gateway)

    assert result.stop_reason is None, result.corrective_text
    assert (result.settled_turns, len(gateway.calls)) == (3, 3)
    assert result.plan_hash is not None
    assert _notice("INTERMEDIATE_REQUIRES_OBSERVE") in gateway.calls[1]["input_text"]
    assert _notice("INTERMEDIATE_REQUIRES_OBSERVE") not in gateway.calls[0]["input_text"]
    assert "Current guarded read evidence" in gateway.calls[2]["input_text"]


def test_without_the_notice_the_same_double_cannot_recover(tmp_path, monkeypatch):
    """The control's dependency (Codex round 44): suppress the notice and the same scenario stops at the repeat limit."""
    from optimus.agent import planning_loop

    monkeypatch.setattr(planning_loop, "_correction_notice", lambda code: "")
    gateway = NoticeFollowingGateway(_scripts(MISSING_OBSERVE, "", TARGET_FINAL_PLAN))
    gateway.workspace = tmp_path
    result = _run_target(tmp_path, gateway)

    assert (result.stop_reason, result.settled_turns, result.plan_hash) == ("PLANNING_UNPARSEABLE_RESPONSE", 2, None)


def test_the_notice_is_cleared_after_a_validly_parsed_turn(tmp_path):
    gateway = ScriptingGateway(_scripts(MISSING_OBSERVE, "OBSERVE: need it\nREAD: target.py#bytes=0:5\n", REFUSE_TEXT))
    _run_target(tmp_path, gateway)

    notice = _notice("INTERMEDIATE_REQUIRES_OBSERVE")
    assert [notice in call["input_text"] for call in gateway.calls] == [False, True, False]


def test_each_code_has_its_own_notice():
    from optimus.agent.planning_loop import PLANNING_PARSE_FEEDBACK

    assert len(set(PLANNING_PARSE_FEEDBACK.values())) == len(PLANNING_PARSE_FEEDBACK)


def test_a_later_failure_carries_only_its_own_notice(tmp_path):
    """Four turns, since two consecutive unparseable turns end the run: malformed (A), valid, malformed (B), then the
    prompt that must name B alone."""
    replies = (MISSING_OBSERVE, "OBSERVE: need it\nREAD: target.py#bytes=0:5\n", "OBSERVE: only a note\n", REFUSE_TEXT)
    gateway = ScriptingGateway(_scripts(*replies))
    _run_target(tmp_path, gateway, policy=PlanningLoopPolicy(max_planning_turns=4))

    first, second = _notice("INTERMEDIATE_REQUIRES_OBSERVE"), _notice("INTERMEDIATE_REQUIRES_READ")
    assert [(first in call["input_text"], second in call["input_text"]) for call in gateway.calls] == [
        (False, False), (True, False), (False, False), (False, True),
    ]  # fmt: skip


def test_ignored_feedback_keeps_the_unchanged_repeat_stop(tmp_path):
    result = _run_target(tmp_path, ScriptingGateway(_scripts(MISSING_OBSERVE, MISSING_OBSERVE)))

    assert result.stop_reason == "PLANNING_UNPARSEABLE_RESPONSE"
    assert result.settled_turns == 2


def test_the_notice_never_carries_reply_content(tmp_path):
    canary = f"CANARY-{uuid.uuid4().hex}"
    gateway = ScriptingGateway(_scripts(f"{canary} is all I will say.", REFUSE_TEXT))
    _run_target(tmp_path, gateway)

    second = gateway.calls[1]["input_text"]
    assert _notice("GRAMMAR_UNRECOGNIZED") in second and canary not in second


class _FailsOnceAfterTurnOne(ScriptingGateway):
    """Turn 1 is malformed; turn 2's first wire attempt fails transiently and its retry answers."""

    def create_response(self, *, model, input_text, metadata=None):
        if len(self.calls) == 1 and not getattr(self, "failed", False):
            self.failed = True
            self.failed_input = input_text
            raise GatewayHttpError(503, "temporary overload", gateway_usage=GatewayUsage(gateway_request_id="gw-503", provider="glm", billing_units=1, cost_usd=Decimal("0.001")))
        return super().create_response(model=model, input_text=input_text, metadata=metadata)


def test_the_notice_is_stable_across_a_turns_wire_retry(tmp_path):
    gateway = _FailsOnceAfterTurnOne(_scripts(MISSING_OBSERVE, REFUSE_TEXT))
    _run_target(tmp_path, gateway)

    notice = _notice("INTERMEDIATE_REQUIRES_OBSERVE")
    assert notice in gateway.failed_input and notice in gateway.calls[1]["input_text"]
    assert gateway.failed_input == gateway.calls[1]["input_text"]  # the retried request is the same request


def test_two_runs_never_share_a_notice(tmp_path):
    first = ScriptingGateway(_scripts(MISSING_OBSERVE, REFUSE_TEXT))
    _run_target(tmp_path / "a", first)
    second = ScriptingGateway(_scripts(REFUSE_TEXT))
    _run_target(tmp_path / "b", second)

    assert _notice("INTERMEDIATE_REQUIRES_OBSERVE") not in second.calls[0]["input_text"]
