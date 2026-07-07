from decimal import Decimal

from optimus.agent.golden import AgentGoldenTaskHarness
from optimus.agent.models import AgentRunResult, AgentRunStatus, AgentToolCall
from optimus.golden.tasks import GoldenTask
from optimus.runtime.modes import ExecutionMode


class FakeRunner:
    def run(self, request):
        return AgentRunResult(
            run_id=request.run_id,
            session_id=request.session_id,
            execution_mode=request.execution_mode,
            status=AgentRunStatus.COMPLETED,
            final_state="completed",
            output_text="done",
            tool_calls=(AgentToolCall(tool_name="file_reader", summary="read", cost_usd=Decimal("0")),),
            total_cost_usd=Decimal("0.004"),
            mutation_count=0,
            provider_keys_resolvable=(),
        )


class SequenceRunner:
    def __init__(self, *results: AgentRunResult) -> None:
        self.results = list(results)
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        return self.results.pop(0)


def agent_task(task_id: str, max_cost_usd: Decimal = Decimal("0.020")) -> GoldenTask:
    return GoldenTask(
        task_id=task_id,
        description="Produce plan text, receive approval, then mutate.",
        expected_mode="agent",
        expected_tools=("file_reader", "write_file"),
        max_cost_usd=max_cost_usd,
        expected_final_state="completed",
        mutation_expected=True,
        release_gate=False,
    )


def run_result(
    *,
    execution_mode: ExecutionMode,
    status: AgentRunStatus,
    final_state: str,
    cost_usd: str,
    plan_hash: str | None = None,
    mutation_count: int = 0,
) -> AgentRunResult:
    return AgentRunResult(
        run_id="run-1",
        session_id=None,
        execution_mode=execution_mode,
        status=status,
        final_state=final_state,
        output_text="done",
        tool_calls=(AgentToolCall(tool_name="file_reader", summary="read", cost_usd=Decimal("0")),),
        total_cost_usd=Decimal(cost_usd),
        mutation_count=mutation_count,
        provider_keys_resolvable=(),
        plan_hash=plan_hash,
        stop_reason="BUDGET_EXHAUSTED" if status is AgentRunStatus.TERMINATED else None,
    )


def test_agent_golden_harness_converts_runner_result(tmp_path):
    task = GoldenTask(
        task_id="explain-small-function",
        description="Explain a function under 15 lines.",
        expected_mode="plan_chat",
        expected_tools=("file_reader",),
        max_cost_usd=Decimal("0.005"),
        expected_final_state="chat_only",
        mutation_expected=False,
        release_gate=False,
    )
    harness = AgentGoldenTaskHarness(runner=FakeRunner(), workspace_root=tmp_path)

    result = harness.run(task)

    assert result.task_id == "explain-small-function"
    assert result.actual_tools == ("file_reader",)
    assert result.actual_cost_usd == Decimal("0.004")


def test_agent_golden_harness_short_circuits_terminated_plan(tmp_path):
    runner = SequenceRunner(
        run_result(
            execution_mode=ExecutionMode.AGENT,
            status=AgentRunStatus.TERMINATED,
            final_state="terminated",
            cost_usd="0.002",
            plan_hash=None,
        )
    )
    harness = AgentGoldenTaskHarness(runner=runner, workspace_root=tmp_path)

    result = harness.run(agent_task("budget-exhausted", max_cost_usd=Decimal("0.001")))

    assert len(runner.requests) == 1
    assert result.actual_final_state == "terminated"
    assert result.actual_cost_usd == Decimal("0.002")


def test_agent_golden_harness_sums_plan_and_execution_cost(tmp_path):
    runner = SequenceRunner(
        run_result(
            execution_mode=ExecutionMode.AGENT,
            status=AgentRunStatus.AWAITING_APPROVAL,
            final_state="AWAITING_APPROVAL",
            cost_usd="0.003",
            plan_hash="plan-1",
        ),
        run_result(
            execution_mode=ExecutionMode.AGENT,
            status=AgentRunStatus.COMPLETED,
            final_state="completed",
            cost_usd="0.004",
            mutation_count=1,
        ),
    )
    harness = AgentGoldenTaskHarness(runner=runner, workspace_root=tmp_path)

    result = harness.run(agent_task("plan-then-approve-agent"))

    assert len(runner.requests) == 2
    assert runner.requests[1].approval.plan_hash == "plan-1"
    assert result.actual_cost_usd == Decimal("0.007")
