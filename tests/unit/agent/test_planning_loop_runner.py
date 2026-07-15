from __future__ import annotations

import hashlib
import itertools
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from optimus.acp.debug_trace import resolve_debug_log_path
from optimus.agent.planning_loop import (
    PlanningLoopPolicy,
    PlanningLoopRunner,
    PlanningProgressEvent,
)
from optimus.gateway.errors import GatewayHttpError
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
    progress_observer: callable | None = None,
    usage_callback: callable | None = None,
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


def test_planning_loop_logs_rejected_read_path_to_debug_trace(tmp_path, monkeypatch):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    monkeypatch.setenv("OPTIMUS_ACP_DEBUG_TRACE", "1")
    monkeypatch.setenv("OPTIMUS_ACP_DEBUG_LOG", str(log_path))

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

    def create_response(
        self,
        *,
        model: str,
        input_text: str,
        metadata: dict[str, object] | None = None,
    ) -> GatewayResponse:
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


def test_unexpected_attempt_exception_logs_type_only_and_stops_cost_unknown(tmp_path, monkeypatch):
    log_path = resolve_debug_log_path(workspace_root=tmp_path)
    monkeypatch.setenv("OPTIMUS_ACP_DEBUG_TRACE", "1")
    monkeypatch.setenv("OPTIMUS_ACP_DEBUG_LOG", str(log_path))

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
