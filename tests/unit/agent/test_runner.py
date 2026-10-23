import hashlib
import os
import sys
from decimal import Decimal
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from optimus.agent.models import AgentApproval, AgentRunRequest, AgentRunStatus
from optimus.agent.prompts import MULTI_TURN_PLANNER_PROMPT_VERSION
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import InMemoryAgentStateStore
from optimus.agent.workspace_context import WorkspaceContextResult
from optimus.gateway.errors import GatewayHttpError
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.guardrails.pre_tool import PreToolGuard
from optimus.loops.models import IterationOutcome, IterationState
from optimus.runtime.modes import ExecutionMode
from optimus.telemetry.events import TelemetryEventKind
from optimus.usage.accounting import UsageAccountingService


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


class FlakyPlanningGateway:
    def __init__(self, *, final_text: str, cost_usd: Decimal, gateway_request_id: str) -> None:
        self._final_text = final_text
        self._cost_usd = cost_usd
        self._gateway_request_id = gateway_request_id
        self.attempts = 0
        self.calls: list[dict[str, object]] = []

    def create_response(self, *, model: str, input_text: str, metadata=None) -> GatewayResponse:
        self.attempts += 1
        self.calls.append({"model": model, "metadata": metadata, "attempt": self.attempts})
        if self.attempts < 3:
            raise GatewayHttpError(
                503,
                "temporary outage",
                gateway_usage=GatewayUsage(
                    gateway_request_id=f"gw-failed-{self.attempts}",
                    provider="glm",
                    billing_units=1,
                    cost_usd=Decimal("0.0005"),
                    service="responses",
                    native_unit="tokens",
                    price_snapshot_id="prices-test",
                ),
            )
        return GatewayResponse(
            response_id=self._gateway_request_id,
            output_text=self._final_text,
            gateway_usage=GatewayUsage(
                gateway_request_id=self._gateway_request_id,
                provider="glm",
                billing_units=1,
                cost_usd=self._cost_usd,
                service="responses",
                native_unit="tokens",
                price_snapshot_id="prices-test",
            ),
            raw={"id": self._gateway_request_id},
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


def test_plan_model_request_carries_workspace_source_but_never_the_runtime_tree(tmp_path):
    """Plan 12.2 runtime-context exclusion: the launch's own .optimus files never reach the model."""
    gateway = FakeGatewayClient("READ src/example.py\nExplain the function.")
    target = tmp_path / "src" / "example.py"
    target.parent.mkdir()
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    runtime = tmp_path / ".optimus"
    runtime.mkdir()
    for name in ("debug-acp.ndjson", "launch-audit.ndjson", "local-gateway.log", "telemetry.jsonl"):
        (runtime / name).write_text('{"event": "RUNTIME_SENTINEL_7F3A"}\n', encoding="utf-8")

    AgentRunner(gateway_client=gateway, model="glm-5.2").run(
        AgentRunRequest(run_id="run-1", task="Explain", execution_mode=ExecutionMode.PLAN, workspace_root=tmp_path)
    )

    input_text = gateway.calls[0]["input_text"]
    assert "--- src/example.py ---" in input_text and "def f():" in input_text
    assert "RUNTIME_SENTINEL_7F3A" not in input_text and ".optimus" not in input_text


def test_unparseable_agent_plan_fails_typed_without_silent_success(tmp_path):
    gateway = ScriptingGateway(
        [
            ("Here is prose, not directives.", Decimal("0.001"), "gw-1"),
            ("Here is prose, not directives.", Decimal("0.001"), "gw-2"),
        ]
    )
    runner = AgentRunner(gateway_client=gateway, model="glm-5.2")

    result = runner.run(AgentRunRequest(run_id="run-1", task="Do work", execution_mode=ExecutionMode.AGENT, workspace_root=tmp_path))

    assert result.status is AgentRunStatus.TERMINATED
    assert result.stop_reason == "PLANNING_UNPARSEABLE_RESPONSE"
    assert result.mutation_count == 0
    assert result.plan_hash is None
    assert "did not match the required directive grammar" in result.output_text
    assert "Here is prose, not directives." not in result.output_text


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


def test_agent_mode_recovers_from_an_unparseable_first_turn_through_a_listed_size_read(tmp_path):
    """#388 through the real runner: the turn-1 size list comes from the workspace context it builds."""
    from tests.unit.agent.test_planning_loop_runner import (
        PROSE,
        SIZES_HEADER,
        TARGET_FINAL_PLAN,
        TARGET_SOURCE,
        SizeListReadGateway,
        _scripts,
    )

    (tmp_path / "target.py").write_text(TARGET_SOURCE, encoding="utf-8")
    gateway = SizeListReadGateway(_scripts(PROSE, "", TARGET_FINAL_PLAN))
    result = AgentRunner(gateway_client=gateway, model="glm-5.2").run(
        AgentRunRequest(run_id="run-388", task="Update target.py", execution_mode=ExecutionMode.AGENT, workspace_root=tmp_path)
    )

    assert f"{SIZES_HEADER}\n- target.py: " in gateway.calls[0]["input_text"], "precondition: turn 1 lists the size"
    assert result.status is AgentRunStatus.AWAITING_APPROVAL, result.stop_reason
    assert len(gateway.calls) == 3


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
        AgentRunRequest(
            run_id="run-1",
            task="Add a docstring to example.py",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
        )
    )
    first_input = gateway.calls[0]["input_text"]
    assert gateway.calls[0]["metadata"]["purpose"] == "planning_turn"
    assert MULTI_TURN_PLANNER_PROMPT_VERSION in first_input
    assert "--- example.py ---" in first_input
    gateway.output_text = "WRITE example.py\nBROKEN SECOND PLAN\n"
    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Add a docstring to example.py",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
            approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash=plan_result.plan_hash),
        )
    )

    assert len(gateway.calls) == 1
    assert result.status is AgentRunStatus.COMPLETED
    assert "Return one" in target.read_text(encoding="utf-8")
    assert "BROKEN SECOND PLAN" not in target.read_text(encoding="utf-8")


def test_approved_agent_run_with_wrong_hash_returns_plan_not_found_or_expired(tmp_path):
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

    assert result.status is AgentRunStatus.FAILED
    assert result.stop_reason == "PLAN_NOT_FOUND_OR_EXPIRED"
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
    assert result.stop_reason == "PLANNING_BUDGET_EXHAUSTED"
    assert result.mutation_count == 0
    assert result.plan_hash is None
    assert tuple(call.tool_name for call in result.tool_calls) == ()


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


def test_fitting_agent_context_uses_planning_loop_and_settles_in_one_turn(tmp_path):
    (tmp_path / "target.py").write_bytes(b"original\n")
    final_plan = "READ target.py\nWRITE target.py\nupdated\n"
    gateway = ScriptingGateway([(final_plan, Decimal("0.002"), "gw-1")])
    store = InMemoryAgentStateStore()
    runner = AgentRunner(gateway_client=gateway, model="glm-5.2", state_store=store)

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Update target.py",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
        )
    )

    assert len(gateway.calls) == 1
    assert gateway.calls[0]["metadata"]["purpose"] == "planning_turn"
    input_text = gateway.calls[0]["input_text"]
    assert MULTI_TURN_PLANNER_PROMPT_VERSION in input_text
    assert "--- target.py ---" in input_text
    assert "- target.py: 9 bytes" in input_text
    assert "original" in input_text
    assert result.status is AgentRunStatus.AWAITING_APPROVAL
    assert result.total_cost_usd == Decimal("0.002")
    assert result.plan_hash == hashlib.sha256(final_plan.encode("utf-8")).hexdigest()
    stored = store.load_plan(run_id="run-1", plan_hash=result.plan_hash or "")
    assert stored.planning_turns == 1
    assert stored.gateway_request_ids == ("gw-1",)
    assert stored.cost_usd == Decimal("0.002")


def test_oversized_plan_mode_fails_before_gateway(tmp_path):
    (tmp_path / "large.py").write_text("x" * (17 * 1024), encoding="utf-8")
    gateway = FakeGatewayClient("READ large.py\nExplain")
    runner = AgentRunner(gateway_client=gateway, model="glm-5.2")

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Explain large.py",
            execution_mode=ExecutionMode.PLAN,
            workspace_root=tmp_path,
        )
    )

    assert result.status is AgentRunStatus.FAILED
    assert result.stop_reason == "REQUIRED_WORKSPACE_FILE_TOO_LARGE"
    assert result.total_cost_usd == Decimal("0")
    assert result.plan_hash is None
    assert result.mutation_count == 0
    assert gateway.calls == []


def test_oversized_chat_mode_fails_before_gateway(tmp_path):
    (tmp_path / "large.py").write_text("x" * (17 * 1024), encoding="utf-8")
    gateway = FakeGatewayClient("READ large.py\nExplain")
    runner = AgentRunner(gateway_client=gateway, model="glm-5.2")

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Explain large.py",
            execution_mode=ExecutionMode.CHAT,
            workspace_root=tmp_path,
        )
    )

    assert result.status is AgentRunStatus.FAILED
    assert result.stop_reason == "REQUIRED_WORKSPACE_FILE_TOO_LARGE"
    assert result.total_cost_usd == Decimal("0")
    assert result.plan_hash is None
    assert result.mutation_count == 0
    assert gateway.calls == []


def test_oversized_required_file_triggers_multi_turn_planning(tmp_path):
    (tmp_path / "large.py").write_text("x" * (17 * 1024), encoding="utf-8")
    final_plan = "READ large.py\nWRITE large.py\nupdated header\n"
    gateway = ScriptingGateway([(final_plan, Decimal("0.002"), "gw-1")])
    store = InMemoryAgentStateStore()
    runner = AgentRunner(gateway_client=gateway, model="glm-5.2", state_store=store)

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Edit large.py",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
        )
    )

    assert len(gateway.calls) == 1
    assert gateway.calls[0]["metadata"]["purpose"] == "planning_turn"
    assert result.status is AgentRunStatus.AWAITING_APPROVAL
    assert result.total_cost_usd == Decimal("0.002")
    assert result.plan_hash == hashlib.sha256(final_plan.encode("utf-8")).hexdigest()
    stored = store.load_plan(run_id="run-1", plan_hash=result.plan_hash or "")
    assert stored.planning_turns == 1
    assert stored.gateway_request_ids == ("gw-1",)
    assert stored.cost_usd == Decimal("0.002")


def test_oversized_required_file_settles_after_read_more_then_final(tmp_path):
    (tmp_path / "large.py").write_text("alpha" + ("x" * (17 * 1024)), encoding="utf-8")
    read_more = "OBSERVE: need header\nREAD: large.py#bytes=0:5\n"
    final_plan = "READ large.py\nWRITE large.py\nupdated header\n"
    gateway = ScriptingGateway(
        [
            (read_more, Decimal("0.002"), "gw-1"),
            (final_plan, Decimal("0.003"), "gw-2"),
        ]
    )
    store = InMemoryAgentStateStore()
    accounting = UsageAccountingService()
    runner = AgentRunner(
        gateway_client=gateway,
        model="glm-5.2",
        state_store=store,
        usage_accounting=accounting,
    )

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Edit large.py",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
            max_planning_turns=2,
        )
    )

    assert len(gateway.calls) == 2
    assert result.status is AgentRunStatus.AWAITING_APPROVAL
    assert result.total_cost_usd == Decimal("0.005")
    stored = store.load_plan(run_id="run-1", plan_hash=result.plan_hash or "")
    assert stored.planning_turns == 2
    assert stored.gateway_request_ids == ("gw-1", "gw-2")
    assert stored.cost_usd == Decimal("0.005")
    assert stored.plan_text == final_plan
    # ScriptingGateway's usage envelopes carry no wire `service`/`native_unit`; every
    # accepted envelope is still recorded with the caller-owned persistence context.
    assert [entry.gateway_request_id for entry in accounting.provider_ledger.entries] == ["gw-1", "gw-2"]
    assert all(entry.service == "agent.model" for entry in accounting.provider_ledger.entries)
    assert all(entry.native_unit == "tokens" for entry in accounting.provider_ledger.entries)


def test_oversized_required_file_honors_max_planning_turns_override(tmp_path):
    (tmp_path / "large.py").write_text("x" * (17 * 1024), encoding="utf-8")
    read_more = "OBSERVE: need header\nREAD: large.py#bytes=0:5\n"
    gateway = ScriptingGateway([(read_more, Decimal("0.002"), "gw-1")])
    store = InMemoryAgentStateStore()
    runner = AgentRunner(gateway_client=gateway, model="glm-5.2", state_store=store)

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Edit large.py",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
            max_planning_turns=1,
        )
    )

    assert len(gateway.calls) == 1
    assert result.status is AgentRunStatus.TERMINATED
    assert result.stop_reason == "PLANNING_TURN_LIMIT_EXHAUSTED"
    assert store.latest_plan_for_run(run_id="run-1") is None


def test_oversized_planning_retries_gateway_without_extra_settled_turn(tmp_path):
    (tmp_path / "large.py").write_text("x" * (17 * 1024), encoding="utf-8")
    final_plan = "READ large.py\nWRITE large.py\nupdated header\n"
    gateway = FlakyPlanningGateway(
        final_text=final_plan,
        cost_usd=Decimal("0.002"),
        gateway_request_id="gw-1",
    )
    accounting = UsageAccountingService()
    runner = AgentRunner(
        gateway_client=gateway,
        model="glm-5.2",
        usage_accounting=accounting,
    )

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Edit large.py",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
        )
    )

    assert gateway.attempts == 3
    assert result.status is AgentRunStatus.AWAITING_APPROVAL
    # All three attempts are persisted: two failed + one success.
    assert [entry.request_id for entry in accounting.provider_ledger.entries] == [
        "run-1:planning:1:1",
        "run-1:planning:1:2",
        "run-1:planning:1:3",
    ]
    assert accounting.provider_ledger.total_cost_usd() == Decimal("0.003")
    assert all(entry.service == "agent.model" for entry in accounting.provider_ledger.entries)
    assert all(entry.native_unit == "tokens" for entry in accounting.provider_ledger.entries)
    # Plan 11.5 Task 2 review fix: the wire `price_snapshot_id` must be forwarded to
    # UsageAccountingService, not dropped.
    assert all(entry.price_snapshot_id == "prices-test" for entry in accounting.provider_ledger.entries)


def test_fitting_context_planning_retries_gateway_without_extra_settled_turn(tmp_path):
    # Plan 9.95 Task 3: billable failed attempts are now aggregated (FU-6 closure).
    (tmp_path / "target.py").write_text("original\n", encoding="utf-8")
    final_plan = "READ target.py\nWRITE target.py\nupdated header\n"
    gateway = FlakyPlanningGateway(
        final_text=final_plan,
        cost_usd=Decimal("0.002"),
        gateway_request_id="gw-1",
    )
    accounting = UsageAccountingService()
    runner = AgentRunner(
        gateway_client=gateway,
        model="glm-5.2",
        usage_accounting=accounting,
    )

    result = runner.run(
        AgentRunRequest(
            run_id="run-fit-retry",
            task="Update target.py",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
        )
    )

    assert gateway.attempts == 3
    assert result.status is AgentRunStatus.AWAITING_APPROVAL
    # All three attempts are persisted: two failed + one success.
    assert [entry.request_id for entry in accounting.provider_ledger.entries] == [
        "run-fit-retry:planning:1:1",
        "run-fit-retry:planning:1:2",
        "run-fit-retry:planning:1:3",
    ]
    assert accounting.provider_ledger.gateway_request_ids(run_id="run-fit-retry") == {
        "gw-failed-1",
        "gw-failed-2",
        "gw-1",
    }
    assert accounting.provider_ledger.total_cost_usd(run_id="run-fit-retry") == Decimal("0.003")
    assert result.total_cost_usd == Decimal("0.003")
    assert result.cost_complete is True
    assert result.unknown_cost_attempt_count == 0
    assert all(entry.service == "agent.model" for entry in accounting.provider_ledger.entries)
    assert all(entry.native_unit == "tokens" for entry in accounting.provider_ledger.entries)


def test_unknown_planning_cost_terminates_without_plan_or_usage_row(tmp_path):
    """A gateway error with no valid usage terminates immediately with no persisted rows."""
    (tmp_path / "target.py").write_text("original\n", encoding="utf-8")

    class UnknownCostPlanningGateway:
        def __init__(self) -> None:
            self.attempts = 0

        def create_response(self, *, model: str, input_text: str, metadata=None) -> GatewayResponse:
            self.attempts += 1
            raise GatewayHttpError(503, "temporary outage")

    gateway = UnknownCostPlanningGateway()
    accounting = UsageAccountingService()
    runner = AgentRunner(
        gateway_client=gateway,
        model="glm-5.2",
        usage_accounting=accounting,
    )

    result = runner.run(
        AgentRunRequest(
            run_id="run-unknown",
            task="Update target.py",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
        )
    )

    assert gateway.attempts == 1
    assert result.status is AgentRunStatus.TERMINATED
    assert result.stop_reason == "PLANNING_GATEWAY_COST_UNKNOWN"
    assert result.total_cost_usd == Decimal("0")
    assert result.cost_complete is False
    assert result.unknown_cost_attempt_count == 1
    assert result.plan_hash is None
    assert result.mutation_count == 0
    assert accounting.provider_ledger.entries == ()


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


class _CompleteAtRunBudget:
    def run_iteration(self, state: IterationState, tools) -> IterationOutcome:
        del state, tools
        return IterationOutcome(
            summary="pytest tests green",
            cost_usd=Decimal("0.05"),
            deterministic_completion=True,
        )


def test_bounded_auto_fix_loop_still_completes_when_finishing_turn_cost_equals_budget(tmp_path):
    runner = AgentRunner(
        gateway_client=FakeGatewayClient(),
        model="glm-5.2",
        loop_iteration_runner=_CompleteAtRunBudget(),
    )

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Debug the failing pytest test",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
            completion_condition="pytest tests pass",
        )
    )

    assert result.stop_reason == "COMPLETED"
    assert result.status is AgentRunStatus.COMPLETED


class _FlushCountingEventSink:
    """Narrow event-sink double exposing only the `flush()` protocol `AgentRunner.run` checks for."""

    def __init__(self) -> None:
        self.events: list[object] = []
        self.flush_calls = 0

    def __call__(self, event: object) -> None:
        self.events.append(event)

    def flush(self) -> None:
        self.flush_calls += 1


def test_run_flushes_event_sink_after_the_final_agent_run_event(tmp_path):
    sink = _FlushCountingEventSink()
    runner = AgentRunner(gateway_client=FakeGatewayClient(), model="glm-5.2", event_sink=sink)

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Plan only",
            execution_mode=ExecutionMode.PLAN,
            workspace_root=tmp_path,
        )
    )

    assert result.status is AgentRunStatus.COMPLETED
    assert sink.flush_calls == 1
    assert [event.kind for event in sink.events] == [TelemetryEventKind.AGENT_RUN]
    # flush() happens strictly after the final agent_run event is emitted.
    assert sink.events[-1].kind is TelemetryEventKind.AGENT_RUN


def test_run_flushes_event_sink_even_when_an_inner_run_raises_a_controlled_failure(tmp_path):
    class _RaisingRunner(AgentRunner):
        def _run_once(self, request, *, planning_progress_observer=None, **_kwargs):
            raise RuntimeError("controlled failure injected by test")

    sink = _FlushCountingEventSink()
    runner = _RaisingRunner(gateway_client=FakeGatewayClient(), model="glm-5.2", event_sink=sink)

    with pytest.raises(RuntimeError, match="controlled failure injected by test"):
        runner.run(
            AgentRunRequest(
                run_id="run-1",
                task="Plan only",
                execution_mode=ExecutionMode.PLAN,
                workspace_root=tmp_path,
            )
        )

    assert sink.flush_calls == 1
    # The raise happened before the final agent_run event could be emitted.
    assert sink.events == []


def test_run_with_callable_only_event_sink_never_errors_on_missing_flush(tmp_path):
    """Plain `Callable[[TelemetryEvent], None]` sinks (the pre-Task-5 contract) have no `flush`."""
    events: list[object] = []
    runner = AgentRunner(gateway_client=FakeGatewayClient(), model="glm-5.2", event_sink=events.append)

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Plan only",
            execution_mode=ExecutionMode.PLAN,
            workspace_root=tmp_path,
        )
    )

    assert result.status is AgentRunStatus.COMPLETED
    assert len(events) == 1


def test_run_with_telemetry_fanout_isolates_gateway_trace_failure_from_agent_result(tmp_path):
    """Full Task 5 isolation: a permanently-failing Gateway trace exporter must never change
    the agent's completed status, USD total, or mutation count, and `flush()` must still run.
    """
    from optimus.telemetry.fanout import TelemetryFanout
    from optimus.telemetry.jsonl import JsonlTelemetryWriter
    from optimus.telemetry.observability import TraceDeliveryState

    class _AlwaysTimingOutExporter:
        def __init__(self) -> None:
            self.calls = 0

        def export(self, events):
            self.calls += 1
            raise TimeoutError("gateway trace ingress unreachable")

    class _RecordingRedisSink:
        def __init__(self) -> None:
            self.events: list[object] = []

        def __call__(self, event: object) -> None:
            self.events.append(event)

    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    jsonl_writer = JsonlTelemetryWriter(tmp_path / ".optimus" / "telemetry.jsonl")
    redis_sink = _RecordingRedisSink()
    gateway_exporter = _AlwaysTimingOutExporter()
    fanout = TelemetryFanout(
        jsonl_writer=jsonl_writer,
        redis_sink=redis_sink,
        gateway_exporter=gateway_exporter,
        batch_size=100,
    )
    runner = AgentRunner(
        gateway_client=FakeGatewayClient("WRITE example.py\ndef f():\n    \"\"\"Return one.\"\"\"\n    return 1\n"),
        model="glm-5.2",
        event_sink=fanout,
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
    assert result.total_cost_usd == Decimal("0.002")
    assert "Return one" in target.read_text(encoding="utf-8")

    # `run()` called flush() after each of the two runs above, and every flush hit the
    # permanently-failing exporter, so every recorded delivery result is FAILED -- the
    # trace failure never changed the agent result asserted above.
    assert gateway_exporter.calls == 2
    assert len(fanout.delivery_results) == 2
    assert all(result.delivery_state is TraceDeliveryState.FAILED for result in fanout.delivery_results)

    # Local sinks received every event exactly once regardless of the trace failure.
    assert jsonl_writer.path.read_text(encoding="utf-8").count("\n") == 2
    assert [event.kind for event in redis_sink.events] == [TelemetryEventKind.AGENT_RUN, TelemetryEventKind.AGENT_RUN]


def test_agent_runner_run_accepts_keyword_only_mcp_runtime_without_request_fields(tmp_path):
    from optimus.agent.models import AgentMcpToolOutput, AgentToolCall

    class _Svc:
        list_calls: list[str]

        def __init__(self) -> None:
            self.list_calls = []

        def list_tools(self, server: str):
            self.list_calls.append(server)
            return (
                AgentMcpToolOutput(server_name=server, tool_name="mcp_list_tools", text='{"tools":[]}'),
                AgentToolCall(tool_name="mcp_list_tools", summary="listed", authorization_outcome="ALLOW"),
            )

    (tmp_path / "a.py").write_text("x\n", encoding="utf-8")
    service = _Svc()
    gateway = ScriptingGateway(
        [
            ("MCP_LIST tools\n", Decimal("0.001"), "gw-1"),
            ("WRITE a.py\ny\n", Decimal("0.001"), "gw-2"),
        ]
    )
    request = AgentRunRequest(
        run_id="run-kw-mcp",
        session_id="s1",
        task="mcp",
        execution_mode=ExecutionMode.AGENT,
        workspace_root=tmp_path,
        max_planning_turns=3,
    )
    assert "client_mcp_service" not in request.model_dump()
    result = AgentRunner(gateway_client=gateway, model="glm-5.2").run(
        request,
        client_mcp_service=service,
    )
    assert "client_mcp_service" not in result.model_dump()
    assert service.list_calls == ["tools"]
    assert all(call.tool_name != "lookup" for call in result.tool_calls)


def test_run_with_telemetry_fanout_preserves_completed_result_when_jsonl_fails(tmp_path, monkeypatch, caplog, capsys):
    import logging

    from optimus.telemetry.fanout import TelemetryFanout
    from optimus.telemetry.jsonl import JsonlTelemetryWriter

    class RecordingExporter:
        def __init__(self):
            self.batches = []

        def export(self, events):
            self.batches.append(events)
            return {"trace_batch_id": f"batch-{len(self.batches)}", "trace_ids": [],
                    "delivery_state": "delivered", "retry_count": 0, "final_disposition": "delivered"}

    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    writer = JsonlTelemetryWriter(tmp_path / ".optimus" / "telemetry.jsonl")
    redis_events = []
    exporter = RecordingExporter()
    fanout = TelemetryFanout(jsonl_writer=writer, redis_sink=redis_events.append, gateway_exporter=exporter, batch_size=1)
    runner = AgentRunner(
        gateway_client=FakeGatewayClient('WRITE example.py\ndef f():\n    """Return one."""\n    return 1\n'),
        model="glm-5.2", event_sink=fanout,
    )
    common = dict(run_id="run-1", task="Add a docstring to example.py", execution_mode=ExecutionMode.AGENT, workspace_root=tmp_path)
    plan_result = runner.run(AgentRunRequest(**common))
    before_redis, before_gateway = len(redis_events), len(exporter.batches)
    healthy_append = writer.append
    failed_events = []

    def fail_completed_event(event):
        if event.kind is not TelemetryEventKind.AGENT_RUN:
            return healthy_append(event)
        assert '"""Return one."""' in target.read_text(encoding="utf-8")
        payload = event.to_json_dict()
        assert payload["status"] == "completed"
        assert payload["mutation_count"] == 1
        assert payload["total_cost_usd"] == "0.002"
        failed_events.append(event)
        raise OSError("synthetic-private-sink-message")

    monkeypatch.setattr(writer, "append", fail_completed_event)
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="optimus.telemetry.fanout"):
        result = runner.run(AgentRunRequest(
            **common, approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash=plan_result.plan_hash),
        ))

    assert result.status is AgentRunStatus.COMPLETED
    assert result.mutation_count == 1
    assert result.total_cost_usd == Decimal("0.002")
    assert '"""Return one."""' in target.read_text(encoding="utf-8")
    assert len(failed_events) == 1
    assert redis_events[before_redis:] == failed_events
    assert exporter.batches[before_gateway:] == [tuple(failed_events)]
    fanout.flush()
    assert len(exporter.batches) == before_gateway + 1
    assert len(fanout.local_sink_failures) == 1
    failure = fanout.local_sink_failures[0]
    assert (failure.sink, failure.event_kind, failure.reason_code, failure.exception_type) == (
        "jsonl", "agent_run", "telemetry_sink_raised", "OSError",
    )
    warnings = [record for record in caplog.records if record.name == "optimus.telemetry.fanout"]
    assert len(warnings) == 1
    assert warnings[0].levelno == logging.WARNING
    assert warnings[0].exc_info is None
    assert "synthetic-private-sink-message" not in caplog.text + repr(failure)
    assert capsys.readouterr().out == ""


# --- Plan 12.2 READ + W: model-issued access to the reserved runtime tree `.optimus/` --------------------------

RUNTIME_SENTINEL = "RUNTIME-SENTINEL-7f3a"
SOURCE_TEXT = "print('ordinary source')\n"


def _runtime_workspace(root: Path) -> Path:
    """An ordinary source file beside a runtime tree holding a sentinel that must never be read."""
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "a.py").write_text(SOURCE_TEXT, encoding="utf-8")
    (root / ".optimus").mkdir(exist_ok=True)
    (root / ".optimus" / "telemetry.ndjson").write_text(RUNTIME_SENTINEL, encoding="utf-8")
    return root


@pytest.fixture
def directory_alias():
    """Directory aliases: a Windows junction where `_winapi` exists, else a directory symlink. Each alias itself is
    removed at teardown, never anything through it."""
    made: list[tuple[Path, bool]] = []

    def make(link: Path, target: Path) -> None:
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            import _winapi
        except ImportError:
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError as exc:
                pytest.skip(f"directory alias unavailable: {exc}")
            made.append((link, False))
            return
        _winapi.CreateJunction(str(target), str(link))
        made.append((link, True))

    yield make
    for link, junction in reversed(made):
        os.rmdir(link) if junction else link.unlink()


def _guarded_runner(workspace: Path, gateway, **kwargs) -> tuple[AgentRunner, PreToolGuard]:
    guard = PreToolGuard.for_workspace(workspace_root=workspace, allowed_network_hosts=())
    return AgentRunner(gateway_client=gateway, model="glm-5.2", guard=guard, **kwargs), guard


def _reads(result) -> tuple[str, ...]:
    return tuple(call.summary for call in result.tool_calls if call.tool_name == "file_reader")


def _blocked(guard: PreToolGuard) -> list[str]:
    return [event.failed_checks[0] for event in guard.audit_events() if event.verdict == "BLOCK"]


def _captures(gateway, guard: PreToolGuard, *results) -> list[str]:
    """Everything a run exposed: each Gateway request, each run result (its output, plan text, tool calls and their
    summaries) and each guard audit event."""
    captures = [repr(call) for call in gateway.calls]
    captures += [repr(result) for result in results if result is not None]
    captures += [repr(event) for event in guard.audit_events()]
    return captures


def _assert_runtime_bytes_never_surface(gateway, guard: PreToolGuard, *results) -> None:
    """READ v3 §6: the sentinel's bytes appear in no request, tool call, summary or audit capture. The runner keeps
    only a plan READ's summary, so on R1-R3 and R5 this pins absence at both versions; where a route forwards read
    bytes (R4, the next planning turn), it is what fails at baseline."""
    assert gateway.calls  # the capture is not vacuous
    assert [text for text in _captures(gateway, guard, *results) if RUNTIME_SENTINEL in text] == []


def _plan_and_approve(runner: AgentRunner, workspace: Path, task: str = "Update src/a.py"):
    plan = runner.run(AgentRunRequest(run_id="run-1", task=task, execution_mode=ExecutionMode.AGENT, workspace_root=workspace))
    approved = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task=task,
            execution_mode=ExecutionMode.AGENT,
            workspace_root=workspace,
            approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash=plan.plan_hash),
        )
    )
    return plan, approved


def _agent(task: str, workspace: Path, **kwargs) -> AgentRunRequest:
    return AgentRunRequest(run_id="run-1", task=task, execution_mode=ExecutionMode.AGENT, workspace_root=workspace, **kwargs)


def test_plan_read_directives_never_read_the_runtime_tree_while_planning_or_after_approval(tmp_path):
    workspace = _runtime_workspace(tmp_path)
    (workspace / "a" / ".optimus").mkdir(parents=True)
    (workspace / "a" / ".optimus" / "state.json").write_text(RUNTIME_SENTINEL, encoding="utf-8")
    plan_text = "READ .optimus/telemetry.ndjson\nREAD a/.optimus/state.json\nREAD src/a.py\nWRITE src/a.py\nprint('updated')\n"
    gateway = FakeGatewayClient(plan_text)
    runner, guard = _guarded_runner(workspace, gateway, state_store=InMemoryAgentStateStore())

    plan, approved = _plan_and_approve(runner, workspace)

    _assert_runtime_bytes_never_surface(gateway, guard, plan, approved)
    assert _reads(plan) == ("read src/a.py",)
    assert _reads(approved) == ("read src/a.py", "read src/a.py")  # the READ, then the read-before-write
    assert _blocked(guard).count("path.runtime.read") == 4  # two reserved READs, while planning and after approval


def test_a_reserved_alias_into_ordinary_source_is_denied_by_its_requested_name(tmp_path, directory_alias):
    workspace = _runtime_workspace(tmp_path)
    directory_alias(workspace / "a" / ".optimus", workspace / "src")
    gateway = FakeGatewayClient("READ a/.optimus/a.py\nREAD src/a.py\nWRITE src/a.py\nx = 1\n")
    runner, guard = _guarded_runner(workspace, gateway)

    result = runner.run(_agent("Read", workspace))

    _assert_runtime_bytes_never_surface(gateway, guard, result)
    assert _reads(result) == ("read src/a.py",)
    assert "path.runtime.read" in _blocked(guard)


def test_an_ordinary_alias_into_the_runtime_tree_is_denied_by_its_resolved_target(tmp_path, directory_alias):
    workspace = _runtime_workspace(tmp_path)
    directory_alias(workspace / "src" / "rt", workspace / ".optimus")
    gateway = FakeGatewayClient("READ src/rt/telemetry.ndjson\nREAD src/a.py\nWRITE src/a.py\nx = 1\n")
    runner, guard = _guarded_runner(workspace, gateway)

    result = runner.run(_agent("Read", workspace))

    _assert_runtime_bytes_never_surface(gateway, guard, result)
    assert _reads(result) == ("read src/a.py",)
    assert "path.runtime.read" in _blocked(guard)


@pytest.mark.skipif(sys.platform != "win32", reason="NTFS names are case-insensitive; a POSIX `.OPTIMUS` is another directory")
def test_a_case_variant_of_the_runtime_tree_is_denied_on_windows(tmp_path):
    workspace = _runtime_workspace(tmp_path)
    gateway = FakeGatewayClient("READ .OPTIMUS/telemetry.ndjson\nREAD src/a.py\nWRITE src/a.py\nx = 1\n")
    runner, guard = _guarded_runner(workspace, gateway)

    result = runner.run(_agent("Read", workspace))

    _assert_runtime_bytes_never_surface(gateway, guard, result)
    assert _reads(result) == ("read src/a.py",)
    assert "path.runtime.read" in _blocked(guard)


def _without_final_path_support(monkeypatch) -> None:
    import ntpath

    def unsupported(path):
        raise OSError(22, "Incorrect function", str(path), 1)  # winerror 1: ERROR_INVALID_FUNCTION

    monkeypatch.setattr(ntpath, "_getfinalpathname", unsupported)


@pytest.mark.skipif(sys.platform != "win32", reason="final-path resolution (GetFinalPathNameByHandle) is the Windows mechanism")
def test_without_final_path_support_ordinary_source_is_still_read(tmp_path, monkeypatch):
    workspace = _runtime_workspace(tmp_path)
    _without_final_path_support(monkeypatch)
    runner, guard = _guarded_runner(workspace, FakeGatewayClient("READ src/a.py\nWRITE src/a.py\nx = 1\n"))

    result = runner.run(_agent("Read", workspace))

    assert _reads(result) == ("read src/a.py",)
    assert _blocked(guard) == []


@pytest.mark.skipif(sys.platform != "win32", reason="final-path resolution (GetFinalPathNameByHandle) is the Windows mechanism")
def test_without_final_path_support_the_runtime_name_is_still_denied(tmp_path, monkeypatch):
    workspace = _runtime_workspace(tmp_path)
    _without_final_path_support(monkeypatch)
    gateway = FakeGatewayClient("READ .optimus/telemetry.ndjson\nWRITE src/a.py\nx = 1\n")
    runner, guard = _guarded_runner(workspace, gateway)

    result = runner.run(_agent("Read", workspace))

    _assert_runtime_bytes_never_surface(gateway, guard, result)
    assert _reads(result) == ()
    assert "path.runtime.read" in _blocked(guard)


def _failing_resolve(monkeypatch, error: BaseException) -> None:
    """Fault the resolution both versions perform, for the named target only."""
    original_resolve = Path.resolve

    def resolve(self, strict=False):
        if self.name == "unresolvable.py":
            raise error
        return original_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolve)


@pytest.mark.parametrize("error", [OSError("simulated resolution failure"), RuntimeError("simulated symlink loop")], ids=["oserror", "runtimeerror"])
def test_an_unresolvable_plan_read_target_is_denied_through_the_audited_guard(tmp_path, monkeypatch, error):
    workspace = _runtime_workspace(tmp_path)
    (workspace / "src" / "unresolvable.py").write_text(RUNTIME_SENTINEL, encoding="utf-8")
    _failing_resolve(monkeypatch, error)
    gateway = FakeGatewayClient("READ src/unresolvable.py\nREAD src/a.py\nWRITE src/a.py\nx = 1\n")
    runner, guard = _guarded_runner(workspace, gateway)

    result = runner.run(_agent("Read", workspace))

    _assert_runtime_bytes_never_surface(gateway, guard, result)
    assert _reads(result) == ("read src/a.py",)
    assert "path.unresolved.read" in _blocked(guard)


@pytest.mark.parametrize("error", [OSError("simulated resolution failure"), RuntimeError("simulated symlink loop")], ids=["oserror", "runtimeerror"])
def test_an_unresolvable_plan_read_target_is_denied_after_approval_too(tmp_path, monkeypatch, error):
    workspace = _runtime_workspace(tmp_path)
    (workspace / "src" / "unresolvable.py").write_text(RUNTIME_SENTINEL, encoding="utf-8")
    _failing_resolve(monkeypatch, error)
    gateway = FakeGatewayClient("READ src/unresolvable.py\nWRITE src/a.py\nx = 1\n")
    runner, guard = _guarded_runner(workspace, gateway, state_store=InMemoryAgentStateStore())

    plan, approved = _plan_and_approve(runner, workspace)

    _assert_runtime_bytes_never_surface(gateway, guard, plan, approved)
    assert _reads(approved) == ("read src/a.py",)  # only the read-before-write of the WRITE target
    assert _blocked(guard).count("path.unresolved.read") == 2  # while planning and after approval


def test_a_denied_plan_read_publishes_a_no_effect_terminal_and_never_succeeds(tmp_path):
    from optimus.acp.lifecycle import TurnControl

    class RecordingControl(TurnControl):
        def __init__(self) -> None:
            super().__init__(session_id="sess-1", turn_seq=1)
            self.terminals: list[tuple[str, str]] = []

        def complete_directive(self, kind, operation_id, terminal):
            self.terminals.append((kind.value, terminal))
            super().complete_directive(kind, operation_id, terminal)

    workspace = _runtime_workspace(tmp_path)
    control = RecordingControl()
    gateway = FakeGatewayClient("READ .optimus/telemetry.ndjson\nWRITE src/a.py\nx = 1\n")
    runner, guard = _guarded_runner(workspace, gateway)

    result = runner.run(_agent("Read", workspace), operation_control=control)

    _assert_runtime_bytes_never_surface(gateway, guard, result)
    assert [entry for entry in control.terminals if entry[0] == "planning_read"] == [("planning_read", "failed_no_effect")]


def test_a_write_to_an_existing_runtime_file_fails_before_any_write(tmp_path):
    workspace = _runtime_workspace(tmp_path)
    runtime_file = workspace / ".optimus" / "telemetry.ndjson"
    gateway = FakeGatewayClient('WRITE .optimus/telemetry.ndjson\n{"forged": true}\n')
    runner, guard = _guarded_runner(workspace, gateway, state_store=InMemoryAgentStateStore())

    plan = runner.run(_agent("Update src/a.py", workspace))
    try:
        approved = runner.run(
            _agent("Update src/a.py", workspace, approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash=plan.plan_hash))
        )
    except PermissionError:
        approved = None

    _assert_runtime_bytes_never_surface(gateway, guard, plan, approved)
    assert runtime_file.read_text(encoding="utf-8") == RUNTIME_SENTINEL
    assert approved is None or approved.status is not AgentRunStatus.COMPLETED
    assert "path.runtime.read" in _blocked(guard)  # the read-before-write is denied first


def test_a_write_never_creates_a_file_in_the_runtime_tree(tmp_path):
    workspace = _runtime_workspace(tmp_path)
    forged = workspace / ".optimus" / "plan12-stage-c" / "forged.jsonl"
    forged.parent.mkdir()
    plan_text = 'WRITE .optimus/plan12-stage-c/forged.jsonl\n{"kind": "init"}\n'
    gateway = FakeGatewayClient(plan_text)
    runner, guard = _guarded_runner(workspace, gateway, state_store=InMemoryAgentStateStore())

    plan = runner.run(_agent("Update src/a.py", workspace))
    try:
        approved = runner.run(
            _agent("Update src/a.py", workspace, approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash=plan.plan_hash))
        )
    except PermissionError:
        approved = None

    _assert_runtime_bytes_never_surface(gateway, guard, plan, approved)
    assert not forged.exists()
    assert approved is None or approved.status is not AgentRunStatus.COMPLETED
    assert "path.runtime.write" in _blocked(guard)


def test_a_planner_ranged_read_of_the_runtime_tree_stops_and_never_reaches_the_model(tmp_path):
    workspace = _runtime_workspace(tmp_path)
    gateway = ScriptingGateway(
        [
            ("OBSERVE: need runtime state\nREAD: .optimus/telemetry.ndjson#bytes=0:21\n", Decimal("0.002"), "gw-1"),
            ("READ src/a.py\nWRITE src/a.py\nx = 1\n", Decimal("0.003"), "gw-2"),
        ]
    )
    runner, guard = _guarded_runner(workspace, gateway)

    result = runner.run(_agent("Edit src/a.py", workspace, max_planning_turns=2))

    _assert_runtime_bytes_never_surface(gateway, guard, result)  # at baseline the sentinel reaches the next turn
    assert result.stop_reason == "PLANNING_READ_GUARD_BLOCKED"
    assert all(RUNTIME_SENTINEL not in str(call["input_text"]) for call in gateway.calls)
    assert "path.runtime.read" in _blocked(guard)


@pytest.mark.parametrize("error", [OSError("simulated resolution failure"), RuntimeError("simulated symlink loop")], ids=["oserror", "runtimeerror"])
def test_an_unresolvable_planner_ranged_read_stops_through_the_audited_guard(tmp_path, monkeypatch, error):
    workspace = _runtime_workspace(tmp_path)
    (workspace / "src" / "unresolvable.py").write_text(RUNTIME_SENTINEL, encoding="utf-8")
    _failing_resolve(monkeypatch, error)
    gateway = ScriptingGateway(
        [
            ("OBSERVE: need it\nREAD: src/unresolvable.py#bytes=0:21\n", Decimal("0.002"), "gw-1"),
            ("READ src/a.py\nWRITE src/a.py\nx = 1\n", Decimal("0.003"), "gw-2"),
        ]
    )
    runner, guard = _guarded_runner(workspace, gateway)

    result = runner.run(_agent("Edit src/a.py", workspace, max_planning_turns=2))

    assert result.stop_reason == "PLANNING_READ_GUARD_BLOCKED"
    _assert_runtime_bytes_never_surface(gateway, guard, result)
    assert "path.unresolved.read" in _blocked(guard)


def test_ordinary_source_is_still_read_by_plan_and_planner_reads_and_through_a_normal_alias(tmp_path, directory_alias):
    workspace = _runtime_workspace(tmp_path)
    directory_alias(workspace / "lib", workspace / "src")
    gateway = ScriptingGateway(
        [
            ("OBSERVE: need the header\nREAD: src/a.py#bytes=0:5\n", Decimal("0.002"), "gw-1"),
            ("READ lib/a.py\nREAD src/a.py\nWRITE src/a.py\nx = 1\n", Decimal("0.003"), "gw-2"),
        ]
    )
    runner, guard = _guarded_runner(workspace, gateway)

    result = runner.run(_agent("Edit src/a.py", workspace, max_planning_turns=2))

    assert result.status is AgentRunStatus.AWAITING_APPROVAL
    assert _reads(result) == ("read src/a.py", "read src/a.py")  # the alias read is summarised by its resolved target
    assert "print" in str(gateway.calls[1]["input_text"])  # the ranged read's bytes reached the next turn
    assert all(RUNTIME_SENTINEL not in str(call["input_text"]) for call in gateway.calls)
    captures = _captures(gateway, guard, result)
    assert any("print" in text for text in captures)  # the capture sees the bytes a run does read
    assert [text for text in captures if RUNTIME_SENTINEL in text] == []
    assert _blocked(guard) == []


def test_a_workspace_under_an_ancestor_named_optimus_still_reads_its_source(tmp_path):
    workspace = _runtime_workspace(tmp_path / ".optimus" / "ws")
    runner, guard = _guarded_runner(workspace, FakeGatewayClient("READ src/a.py\nWRITE src/a.py\nx = 1\n"))

    result = runner.run(_agent("Read", workspace))

    assert _reads(result) == ("read src/a.py",)
    assert _blocked(guard) == []


def test_a_missing_reserved_plan_read_is_denied_through_the_audited_guard_while_planning_and_after_approval(tmp_path):
    workspace = _runtime_workspace(tmp_path)
    plan_text = "READ .optimus/missing.json\nREAD a/.optimus/missing.json\nREAD src/a.py\nWRITE src/a.py\nprint('updated')\n"
    gateway = FakeGatewayClient(plan_text)
    runner, guard = _guarded_runner(workspace, gateway, state_store=InMemoryAgentStateStore())

    plan, approved = _plan_and_approve(runner, workspace)

    _assert_runtime_bytes_never_surface(gateway, guard, plan, approved)
    assert _blocked(guard).count("path.runtime.read") == 4  # two missing reserved READs, while planning and after approval
    assert _reads(plan) == ("read src/a.py",)
    assert not (workspace / ".optimus" / "missing.json").exists()


def test_a_missing_target_through_an_alias_into_the_runtime_tree_is_denied_by_its_resolved_target(tmp_path, directory_alias):
    workspace = _runtime_workspace(tmp_path)
    directory_alias(workspace / "src" / "rt", workspace / ".optimus")
    gateway = FakeGatewayClient("READ src/rt/missing.json\nREAD src/a.py\nWRITE src/a.py\nx = 1\n")
    runner, guard = _guarded_runner(workspace, gateway)

    result = runner.run(_agent("Read", workspace))

    _assert_runtime_bytes_never_surface(gateway, guard, result)
    assert "path.runtime.read" in _blocked(guard)
    assert _reads(result) == ("read src/a.py",)


def test_a_missing_reserved_plan_read_publishes_a_no_effect_terminal(tmp_path):
    from optimus.acp.lifecycle import TurnControl

    class RecordingControl(TurnControl):
        def __init__(self) -> None:
            super().__init__(session_id="sess-1", turn_seq=1)
            self.terminals: list[tuple[str, str]] = []

        def complete_directive(self, kind, operation_id, terminal):
            self.terminals.append((kind.value, terminal))
            super().complete_directive(kind, operation_id, terminal)

    workspace = _runtime_workspace(tmp_path)
    control = RecordingControl()
    runner, _ = _guarded_runner(workspace, FakeGatewayClient("READ .optimus/missing.json\nWRITE src/a.py\nx = 1\n"))

    runner.run(_agent("Read", workspace), operation_control=control)

    assert [entry for entry in control.terminals if entry[0] == "planning_read"] == [("planning_read", "failed_no_effect")]


def test_an_ordinary_missing_plan_read_is_still_skipped_without_a_denial(tmp_path):
    workspace = _runtime_workspace(tmp_path)
    gateway = FakeGatewayClient("READ src/missing.py\nREAD src/a.py\nWRITE src/a.py\nx = 1\n")
    runner, guard = _guarded_runner(workspace, gateway)

    result = runner.run(_agent("Read", workspace))

    assert result.status is AgentRunStatus.AWAITING_APPROVAL
    assert _reads(result) == ("read src/a.py",)
    assert _blocked(guard) == []


def _file_symlink_or_skip(link: Path, target: Path) -> None:
    """A file symlink: POSIX, or Windows with the symlink privilege; skipped otherwise (READ v3 §6 A5)."""
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"file symlink unavailable: {exc}")


def test_an_ordinary_file_symlink_into_the_runtime_tree_is_denied_by_its_resolved_target(tmp_path):
    workspace = _runtime_workspace(tmp_path)
    _file_symlink_or_skip(workspace / "src" / "link.ndjson", workspace / ".optimus" / "telemetry.ndjson")
    gateway = FakeGatewayClient("READ src/link.ndjson\nREAD src/a.py\nWRITE src/a.py\nx = 1\n")
    runner, guard = _guarded_runner(workspace, gateway)

    result = runner.run(_agent("Read", workspace))

    _assert_runtime_bytes_never_surface(gateway, guard, result)
    assert _reads(result) == ("read src/a.py",)
    assert "path.runtime.read" in _blocked(guard)
