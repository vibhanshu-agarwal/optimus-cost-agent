from __future__ import annotations

import hashlib
from decimal import Decimal

from optimus.agent.golden import AgentGoldenTaskHarness
from optimus.agent.runner import AgentRunner
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.golden.tasks import evaluate_golden_task, load_golden_tasks


class ScenarioGatewayClient:
    def __init__(self, output_text: str, *, cost_usd: str = "0.002") -> None:
        self.output_text = output_text
        self.cost_usd = Decimal(cost_usd)

    def create_response(self, *, model: str, input_text: str, metadata=None) -> GatewayResponse:
        return GatewayResponse(
            response_id="resp-1",
            output_text=self.output_text,
            gateway_usage=GatewayUsage(
                gateway_request_id="gw-1",
                provider="glm",
                billing_units=5,
                cost_usd=self.cost_usd,
            ),
            raw={"id": "resp-1"},
        )


class RecordingRunner:
    def __init__(self, runner: AgentRunner) -> None:
        self._runner = runner
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        return self._runner.run(request)


FIXTURE_PATH = "tests/fixtures/golden_tasks/phase1_golden_tasks.json"


def task_by_id(task_id: str):
    return next(task for task in load_golden_tasks(FIXTURE_PATH) if task.task_id == task_id)


def test_explain_small_function_plan_only_scenario(tmp_path):
    target = tmp_path / "src" / "example.py"
    target.parent.mkdir()
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    harness = AgentGoldenTaskHarness(
        runner=AgentRunner(
            gateway_client=ScenarioGatewayClient("READ src/example.py\nExplain the function."),
            model="glm-5.2",
        ),
        workspace_root=tmp_path,
    )

    result = harness.run(task_by_id("explain-small-function"))

    assert evaluate_golden_task(task_by_id("explain-small-function"), result).passed is True


def test_docstring_single_function_approved_agent_mutation(tmp_path):
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    harness = AgentGoldenTaskHarness(
        runner=AgentRunner(
            gateway_client=ScenarioGatewayClient(
                "WRITE example.py\ndef f():\n    \"\"\"Return one.\"\"\"\n    return 1\n"
            ),
            model="glm-5.2",
        ),
        workspace_root=tmp_path,
    )

    result = harness.run(task_by_id("docstring-single-function"))

    assert evaluate_golden_task(task_by_id("docstring-single-function"), result).passed is True
    assert "Return one" in target.read_text(encoding="utf-8")


def test_plan_then_approve_agent_carries_plan_hash(tmp_path):
    target = tmp_path / "src" / "example.py"
    target.parent.mkdir()
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    output_text = "WRITE src/example.py\ndef f():\n    \"\"\"Planned.\"\"\"\n    return 1\n"
    runner = RecordingRunner(
        AgentRunner(
            gateway_client=ScenarioGatewayClient(output_text),
            model="glm-5.2",
        )
    )
    harness = AgentGoldenTaskHarness(runner=runner, workspace_root=tmp_path)

    result = harness.run(task_by_id("plan-then-approve-agent"))

    expected_plan_hash = hashlib.sha256(output_text.encode("utf-8")).hexdigest()
    assert len(runner.requests) == 2
    assert runner.requests[1].approval.plan_hash == expected_plan_hash
    assert evaluate_golden_task(task_by_id("plan-then-approve-agent"), result).passed is True
    assert "Planned" in target.read_text(encoding="utf-8")


def test_budget_exhausted_termination_scenario(tmp_path):
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    harness = AgentGoldenTaskHarness(
        runner=AgentRunner(
            gateway_client=ScenarioGatewayClient("READ example.py\nExplain before stopping."),
            model="glm-5.2",
        ),
        workspace_root=tmp_path,
    )
    task = task_by_id("budget-exhausted")

    result = harness.run(task)

    assert result.actual_mode == "agent"
    assert result.actual_tools == ()
    assert result.actual_final_state == "terminated"
    assert result.mutation_count == 0
    assert result.actual_cost_usd == Decimal("0.002")
