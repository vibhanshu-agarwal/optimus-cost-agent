from decimal import Decimal

from optimus.agent.models import AgentApproval, AgentRunRequest, AgentRunStatus
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import InMemoryAgentStateStore
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.runtime.modes import ExecutionMode
from optimus.telemetry.events import TelemetryEventKind


class FakeGatewayClient:
    def __init__(self, output_text: str = "Plan text") -> None:
        self.calls = []
        self.output_text = output_text

    def create_response(self, *, model: str, input_text: str, metadata=None):
        self.calls.append({"model": model, "input_text": input_text, "metadata": metadata})
        return GatewayResponse(
            response_id="resp-1",
            output_text=self.output_text,
            gateway_usage=GatewayUsage(
                gateway_request_id="gw-1",
                provider="glm",
                billing_units=5,
                cost_usd=Decimal("0.002"),
            ),
            raw={"id": "resp-1"},
        )


def test_plan_mode_returns_plan_without_mutation(tmp_path):
    target = tmp_path / "src" / "example.py"
    target.parent.mkdir()
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    gateway = FakeGatewayClient("READ src/example.py\nExplain the function.")
    runner = AgentRunner(gateway_client=gateway, model="glm-5.2")

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Explain a small function",
            execution_mode=ExecutionMode.PLAN,
            workspace_root=tmp_path,
        )
    )

    assert result.status is AgentRunStatus.COMPLETED
    assert result.final_state == "CHAT_ONLY"
    assert result.mutation_count == 0
    assert result.total_cost_usd == Decimal("0.002")
    assert tuple(call.tool_name for call in result.tool_calls) == ("file_reader",)
    assert gateway.calls[0]["metadata"]["run_id"] == "run-1"


def test_agent_mode_without_approval_returns_awaiting_approval(tmp_path):
    runner = AgentRunner(gateway_client=FakeGatewayClient("Plan: write the file."), model="glm-5.2")

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Add a docstring",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
        )
    )

    assert result.status is AgentRunStatus.AWAITING_APPROVAL
    assert result.final_state == "AWAITING_APPROVAL"
    assert result.mutation_count == 0
    assert result.plan_hash is not None


def test_agent_mode_with_approval_can_write_single_file(tmp_path):
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    runner = AgentRunner(
        gateway_client=FakeGatewayClient("WRITE example.py\ndef f():\n    \"\"\"Return one.\"\"\"\n    return 1\n"),
        model="glm-5.2",
    )

    plan_result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Add a docstring to example.py",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
        )
    )

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Add a docstring to example.py",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
            approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash=plan_result.plan_hash),
        )
    )

    assert result.status is AgentRunStatus.COMPLETED
    assert result.mutation_count == 1
    assert "Return one" in target.read_text(encoding="utf-8")
    assert tuple(call.tool_name for call in result.tool_calls) == ("file_reader", "write_file")


def test_approved_agent_run_replays_stored_plan_without_second_gateway_call(tmp_path):
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    gateway = FakeGatewayClient('WRITE example.py\ndef f():\n    """Return one."""\n    return 1\n')
    store = InMemoryAgentStateStore()
    runner = AgentRunner(gateway_client=gateway, model="glm-5.2", state_store=store)

    plan_result = runner.run(
        AgentRunRequest(run_id="run-1", task="Add a docstring", execution_mode=ExecutionMode.AGENT, workspace_root=tmp_path)
    )
    gateway.output_text = "WRITE example.py\nBROKEN SECOND PLAN\n"
    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Add a docstring",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
            approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash=plan_result.plan_hash),
        )
    )

    assert len(gateway.calls) == 1
    assert result.status is AgentRunStatus.COMPLETED
    assert "Return one" in target.read_text(encoding="utf-8")
    assert "BROKEN SECOND PLAN" not in target.read_text(encoding="utf-8")


def test_approved_agent_run_with_wrong_hash_returns_awaiting_approval_without_mutation(tmp_path):
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    gateway = FakeGatewayClient('WRITE example.py\ndef f():\n    """Return one."""\n    return 1\n')
    store = InMemoryAgentStateStore()
    runner = AgentRunner(gateway_client=gateway, model="glm-5.2", state_store=store)
    runner.run(AgentRunRequest(run_id="run-1", task="Add a docstring", execution_mode=ExecutionMode.AGENT, workspace_root=tmp_path))

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Add a docstring",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
            approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash="wrong-hash"),
        )
    )

    assert result.status is AgentRunStatus.AWAITING_APPROVAL
    assert result.mutation_count == 0
    assert "Return one" not in target.read_text(encoding="utf-8")


def test_approved_agent_run_replays_plan_from_fresh_runner_with_shared_store(tmp_path):
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    shared_store = InMemoryAgentStateStore()
    runner_a_gateway = FakeGatewayClient('WRITE example.py\ndef f():\n    """Return one."""\n    return 1\n')
    runner_a = AgentRunner(gateway_client=runner_a_gateway, model="glm-5.2", state_store=shared_store)
    plan_result = runner_a.run(
        AgentRunRequest(run_id="run-1", task="Add a docstring", execution_mode=ExecutionMode.AGENT, workspace_root=tmp_path)
    )
    runner_b_gateway = FakeGatewayClient("WRITE example.py\nBROKEN SECOND PLAN\n")
    runner_b = AgentRunner(gateway_client=runner_b_gateway, model="glm-5.2", state_store=shared_store)

    result = runner_b.run(
        AgentRunRequest(
            run_id="run-1",
            task="Add a docstring",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
            approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash=plan_result.plan_hash),
        )
    )

    assert runner_b_gateway.calls == []
    assert result.status is AgentRunStatus.COMPLETED
    assert "Return one" in target.read_text(encoding="utf-8")


def test_approved_agent_run_reports_expired_or_unknown_plan_without_replanning(tmp_path):
    gateway = FakeGatewayClient("WRITE example.py\nBROKEN SECOND PLAN\n")
    runner = AgentRunner(gateway_client=gateway, model="glm-5.2", state_store=InMemoryAgentStateStore())

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Add a docstring",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
            approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash="expired-plan"),
        )
    )

    assert gateway.calls == []
    assert result.status is AgentRunStatus.FAILED
    assert result.stop_reason == "PLAN_NOT_FOUND_OR_EXPIRED"
    assert "plan approval expired or was not found" in result.output_text.lower()


def test_agent_mode_rejects_approval_for_different_plan(tmp_path):
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    gateway = FakeGatewayClient("WRITE example.py\ndef f():\n    \"\"\"Return one.\"\"\"\n    return 1\n")
    runner = AgentRunner(
        gateway_client=gateway,
        model="glm-5.2",
    )

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Add a docstring to example.py",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
            approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash="different-plan"),
        )
    )

    assert result.status is AgentRunStatus.FAILED
    assert result.stop_reason == "PLAN_NOT_FOUND_OR_EXPIRED"
    assert result.mutation_count == 0
    assert "Return one" not in target.read_text(encoding="utf-8")
    assert gateway.calls == []


def test_agent_mode_terminates_when_gateway_cost_exceeds_budget(tmp_path):
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    runner = AgentRunner(gateway_client=FakeGatewayClient("READ example.py\nExplain before stopping."), model="glm-5.2")

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Explain code",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
            max_cost_usd=Decimal("0.001"),
        )
    )

    assert result.status is AgentRunStatus.TERMINATED
    assert result.stop_reason == "BUDGET_EXHAUSTED"
    assert result.mutation_count == 0
    assert tuple(call.tool_name for call in result.tool_calls) == ("file_reader",)


def test_agent_run_emits_telemetry_at_final_boundary(tmp_path):
    target = tmp_path / "src" / "example.py"
    target.parent.mkdir()
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    events: list = []
    runner = AgentRunner(
        gateway_client=FakeGatewayClient("READ src/example.py\nExplain the function."),
        model="glm-5.2",
        event_sink=events.append,
    )

    runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Explain a small function",
            execution_mode=ExecutionMode.PLAN,
            workspace_root=tmp_path,
        )
    )

    assert events[-1].kind is TelemetryEventKind.AGENT_RUN
    assert events[-1].payload["status"] == "completed"
    assert events[-1].payload["tool_names"] == ("file_reader",)
