from decimal import Decimal

import pytest
from pydantic import ValidationError

from optimus.agent.models import AgentApproval, AgentRunRequest, AgentRunResult, AgentRunStatus, AgentToolCall
from optimus.runtime.modes import ExecutionMode


def test_agent_run_request_requires_run_id_task_and_workspace(tmp_path):
    request = AgentRunRequest(
        run_id="run-1",
        session_id="session-1",
        task="Add a docstring to src/example.py",
        execution_mode=ExecutionMode.AGENT,
        workspace_root=tmp_path,
        approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash="hash-1"),
        max_cost_usd=Decimal("0.05"),
        completion_condition="example.py contains a docstring",
    )

    assert request.workspace_root == tmp_path.resolve()
    assert request.approval.approved is True
    assert request.max_cost_usd == Decimal("0.05")


def test_agent_run_request_rejects_relative_workspace():
    with pytest.raises(ValidationError, match="workspace_root must be absolute"):
        AgentRunRequest(run_id="run-1", task="Explain code", execution_mode=ExecutionMode.PLAN, workspace_root=".")


def test_agent_run_request_normalizes_lower_case_wire_mode(tmp_path):
    request = AgentRunRequest(run_id="run-1", task="Explain code", execution_mode="plan", workspace_root=tmp_path)

    assert request.execution_mode is ExecutionMode.PLAN


def test_agent_approval_requires_id_and_plan_hash_when_approved():
    with pytest.raises(ValidationError, match="approved requests require approval_id and plan_hash"):
        AgentApproval(approved=True, approval_id="approval-1")


def test_agent_run_request_defaults_planning_turn_policy(tmp_path):
    request = AgentRunRequest(
        run_id="run-1",
        task="Explain code",
        execution_mode=ExecutionMode.PLAN,
        workspace_root=tmp_path,
    )
    assert request.max_planning_turns == 3
    assert request.planning_wall_clock_minutes == 30


def test_agent_run_request_accepts_boundary_planning_turn_cap(tmp_path):
    request = AgentRunRequest(
        run_id="run-1",
        task="Explain code",
        execution_mode=ExecutionMode.PLAN,
        workspace_root=tmp_path,
        max_planning_turns=1,
    )
    assert request.max_planning_turns == 1


@pytest.mark.parametrize("turns", [0, -1])
def test_agent_run_request_rejects_non_positive_planning_turn_caps(turns: int, tmp_path):
    with pytest.raises(ValidationError):
        AgentRunRequest(
            run_id="run-1",
            task="Explain code",
            execution_mode=ExecutionMode.PLAN,
            workspace_root=tmp_path,
            max_planning_turns=turns,
        )


@pytest.mark.parametrize("minutes", [0, -1])
def test_agent_run_request_rejects_non_positive_planning_wall_clock(minutes: int, tmp_path):
    with pytest.raises(ValidationError):
        AgentRunRequest(
            run_id="run-1",
            task="Explain code",
            execution_mode=ExecutionMode.PLAN,
            workspace_root=tmp_path,
            planning_wall_clock_minutes=minutes,
        )


def test_agent_run_result_records_tool_trajectory_and_final_state():
    result = AgentRunResult(
        run_id="run-1",
        session_id=None,
        execution_mode=ExecutionMode.AGENT,
        status=AgentRunStatus.COMPLETED,
        final_state="COMPLETED",
        output_text="Added the docstring.",
        tool_calls=(
            AgentToolCall(tool_name="file_reader", summary="read src/example.py", cost_usd=Decimal("0")),
            AgentToolCall(tool_name="write_file", summary="wrote src/example.py", cost_usd=Decimal("0")),
        ),
        total_cost_usd=Decimal("0.012"),
        mutation_count=1,
        provider_keys_resolvable=(),
        stop_reason=None,
    )

    assert tuple(call.tool_name for call in result.tool_calls) == ("file_reader", "write_file")
    assert result.mutation_count == 1
