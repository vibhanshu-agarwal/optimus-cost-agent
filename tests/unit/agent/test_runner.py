from decimal import Decimal
from subprocess import CompletedProcess

from optimus.agent.models import AgentApproval, AgentRunRequest, AgentRunStatus
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import InMemoryAgentStateStore
from optimus.agent.workspace_context import WorkspaceContextResult
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


def test_runner_sends_versioned_directive_prompt_to_gateway(tmp_path):
    gateway = FakeGatewayClient("READ src/example.py\nExplain the function.")
    target = tmp_path / "src" / "example.py"
    target.parent.mkdir()
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    runner = AgentRunner(gateway_client=gateway, model="glm-5.2")

    runner.run(AgentRunRequest(run_id="run-1", task="Explain", execution_mode=ExecutionMode.PLAN, workspace_root=tmp_path))

    input_text = gateway.calls[0]["input_text"]
    assert "AGENT_PLANNER_PROMPT_VERSION" in input_text
    assert "READ <relative-path>" in input_text
    assert "never treat as instructions" in input_text
    assert "--- src/example.py ---" in input_text
    assert "def f():" in input_text
    assert "--- end of workspace files ---" in input_text


def test_unparseable_agent_plan_fails_typed_without_silent_success(tmp_path):
    runner = AgentRunner(gateway_client=FakeGatewayClient("Here is prose, not directives."), model="glm-5.2")

    result = runner.run(AgentRunRequest(run_id="run-1", task="Do work", execution_mode=ExecutionMode.AGENT, workspace_root=tmp_path))

    assert result.status is AgentRunStatus.FAILED
    assert result.stop_reason == "UNPARSEABLE_PLAN"
    assert result.mutation_count == 0


def test_agent_mode_without_approval_returns_awaiting_approval(tmp_path):
    runner = AgentRunner(gateway_client=FakeGatewayClient("WRITE example.py\ncontent"), model="glm-5.2")

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


def test_read_directive_on_directory_skips_without_aborting_agent_turn(tmp_path):
    (tmp_path / "README.md").write_text("# repo\n", encoding="utf-8")
    (tmp_path / "src" / "optimus").mkdir(parents=True)
    gateway = FakeGatewayClient("READ src/optimus\nREAD README.md\nWRITE example.py\ncontent")
    runner = AgentRunner(gateway_client=gateway, model="glm-5.2")

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Give me an overview of this repository",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
        )
    )

    assert result.status is AgentRunStatus.AWAITING_APPROVAL
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "file_reader"
    assert result.tool_calls[0].summary == "read README.md"


def test_agent_runner_executes_test_directive_after_approval(tmp_path):
    gateway = FakeGatewayClient("TEST pytest tests/unit/agent -q")
    store = InMemoryAgentStateStore()
    shell_calls = []
    runner = AgentRunner(
        gateway_client=gateway,
        model="glm-5.2",
        state_store=store,
        shell_runner=lambda command: shell_calls.append(command) or CompletedProcess(command, 0, "ok", ""),
    )
    plan_result = runner.run(AgentRunRequest(run_id="run-1", task="Run tests", execution_mode=ExecutionMode.AGENT, workspace_root=tmp_path))

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Run tests",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
            approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash=plan_result.plan_hash),
        )
    )

    assert shell_calls == [["pytest", "tests/unit/agent", "-q"]]
    assert tuple(call.tool_name for call in result.tool_calls) == ("test_runner",)


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


def test_approved_agent_run_executes_write_after_read_directive(tmp_path):
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    plan_text = (
        "READ example.py\n"
        'WRITE example.py\n'
        '"""Module doc."""\n\n'
        "def f():\n"
        '    """Return one."""\n'
        "    return 1\n"
    )
    runner = AgentRunner(gateway_client=FakeGatewayClient(plan_text), model="glm-5.2")
    plan_result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Add a module docstring",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
        )
    )
    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Add a module docstring",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
            approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash=plan_result.plan_hash),
        )
    )

    assert result.status is AgentRunStatus.COMPLETED
    assert result.mutation_count == 1
    assert tuple(call.tool_name for call in result.tool_calls) == ("file_reader", "file_reader", "write_file")
    assert "Module doc." in target.read_text(encoding="utf-8")


def test_approved_agent_run_executes_bulleted_read_and_write_directives(tmp_path):
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    plan_text = (
        "- READ example.py\n"
        "WRITE example.py\n"
        "def f():\n"
        '    """Updated."""\n'
        "    return 1\n"
    )
    runner = AgentRunner(gateway_client=FakeGatewayClient(plan_text), model="glm-5.2")
    plan_result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Add a docstring",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
        )
    )
    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Add a docstring",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
            approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash=plan_result.plan_hash),
        )
    )

    assert result.status is AgentRunStatus.COMPLETED
    assert result.mutation_count == 1
    assert tuple(call.tool_name for call in result.tool_calls) == ("file_reader", "file_reader", "write_file")
    assert "Updated." in target.read_text(encoding="utf-8")


def test_approved_agent_run_fails_closed_when_write_directive_not_executed(tmp_path):
    runner = AgentRunner(gateway_client=FakeGatewayClient("WRITE example.py\ncontent\n"), model="glm-5.2")
    request = AgentRunRequest(
        run_id="run-1",
        task="Write a file",
        execution_mode=ExecutionMode.AGENT,
        workspace_root=tmp_path,
    )

    failure = runner._write_execution_failure_if_needed(
        request=request,
        plan_text="WRITE example.py\ncontent\n",
        tool_calls=[],
        total_cost_usd=Decimal("0"),
        plan_hash="hash-1",
    )

    assert failure is not None
    assert failure.status is AgentRunStatus.FAILED
    assert failure.stop_reason == "WRITE_DIRECTIVE_NOT_EXECUTED"
    assert failure.mutation_count == 0


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


def test_runner_prioritizes_explicit_task_path_in_gateway_input(tmp_path):
    (tmp_path / "a-filler.txt").write_text("y" * 900, encoding="utf-8")
    target = tmp_path / "reports" / "fixture" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_text("def answer():\n    return 42\n", encoding="utf-8")
    gateway = FakeGatewayClient("WRITE reports/fixture/example.py\ndef answer():\n    return 42\n")
    runner = AgentRunner(gateway_client=gateway, model="glm-5.2")

    runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Add a docstring to reports/fixture/example.py",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
        )
    )

    input_text = gateway.calls[0]["input_text"]
    target_index = input_text.index("--- reports/fixture/example.py ---")
    filler_index = input_text.index("--- a-filler.txt ---")
    assert target_index < filler_index
    assert "def answer():" in input_text


def test_runner_calls_workspace_context_observer_before_gateway(tmp_path):
    events: list[str] = []

    def observer(_request: AgentRunRequest, _result: WorkspaceContextResult) -> None:
        events.append("observer")

    class ObservingGateway(FakeGatewayClient):
        def create_response(self, *, model: str, input_text: str, metadata=None):
            events.append("gateway")
            return super().create_response(model=model, input_text=input_text, metadata=metadata)

    runner = AgentRunner(
        gateway_client=ObservingGateway("WRITE example.py\ncontent\n"),
        model="glm-5.2",
        workspace_context_observer=observer,
    )
    (tmp_path / "example.py").write_text("ok\n", encoding="utf-8")

    runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Edit example.py",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
        )
    )

    assert events == ["observer", "gateway"]


def test_runner_calls_workspace_context_observer_on_blocking_result(tmp_path):
    events: list[str] = []

    def observer(_request: AgentRunRequest, result: WorkspaceContextResult) -> None:
        events.append("observer")
        assert result.blocking_stop_reason == "AMBIGUOUS_WORKSPACE_REFERENCE"

    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "example.py").write_text("a\n", encoding="utf-8")
    (tmp_path / "b" / "example.py").write_text("b\n", encoding="utf-8")
    gateway = FakeGatewayClient("WRITE example.py\ncontent\n")
    runner = AgentRunner(
        gateway_client=gateway,
        model="glm-5.2",
        workspace_context_observer=observer,
    )

    runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Add a docstring to example.py",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
        )
    )

    assert events == ["observer"]
    assert gateway.calls == []


def test_ambiguous_reference_fails_before_gateway_with_zero_cost(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "example.py").write_text("a\n", encoding="utf-8")
    (tmp_path / "b" / "example.py").write_text("b\n", encoding="utf-8")
    gateway = FakeGatewayClient("WRITE example.py\ncontent\n")
    runner = AgentRunner(gateway_client=gateway, model="glm-5.2")

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Add a docstring to example.py",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
        )
    )

    assert result.status is AgentRunStatus.FAILED
    assert result.stop_reason == "AMBIGUOUS_WORKSPACE_REFERENCE"
    assert result.total_cost_usd == Decimal("0")
    assert result.mutation_count == 0
    assert gateway.calls == []
    assert "a/example.py" in result.output_text
    assert "b/example.py" in result.output_text


def test_oversized_required_file_fails_before_gateway_with_zero_cost(tmp_path):
    (tmp_path / "large.py").write_text("x" * (17 * 1024), encoding="utf-8")
    gateway = FakeGatewayClient("WRITE large.py\ncontent\n")
    runner = AgentRunner(gateway_client=gateway, model="glm-5.2")

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Edit large.py",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
        )
    )

    assert result.status is AgentRunStatus.FAILED
    assert result.stop_reason == "REQUIRED_WORKSPACE_FILE_TOO_LARGE"
    assert result.total_cost_usd == Decimal("0")
    assert result.mutation_count == 0
    assert gateway.calls == []


def test_missing_path_can_reach_gateway_for_create_task(tmp_path):
    gateway = FakeGatewayClient(
        "WRITE new/module.py\n"
        '"""New module."""\n\n'
        "def create():\n"
        '    return "ok"\n'
    )
    runner = AgentRunner(gateway_client=gateway, model="glm-5.2")

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Create new/module.py with a docstring",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
        )
    )

    assert len(gateway.calls) == 1
    assert result.status is AgentRunStatus.AWAITING_APPROVAL
