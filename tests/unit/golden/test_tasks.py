from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from optimus.golden.tasks import GoldenTaskResult, evaluate_golden_task, load_golden_tasks


FIXTURE_PATH = Path("tests/fixtures/golden_tasks/phase1_golden_tasks.json")


def test_phase1_golden_tasks_fixture_loads_expected_release_gate_case():
    tasks = load_golden_tasks(FIXTURE_PATH)

    assert len(tasks) == 10
    assert tasks[-1].task_id == "one-key-release-gate"
    assert tasks[-1].release_gate is True
    assert tasks[-1].max_cost_usd == Decimal("0.050")


def test_golden_task_evaluator_passes_expected_agent_outcome():
    task = next(task for task in load_golden_tasks(FIXTURE_PATH) if task.task_id == "docstring-single-function")
    result = GoldenTaskResult(
        task_id=task.task_id,
        actual_mode="agent",
        actual_tools=("file_reader", "write_file"),
        actual_cost_usd=Decimal("0.009"),
        actual_final_state="completed",
        mutation_count=1,
        provider_keys_resolvable=(),
    )

    evaluation = evaluate_golden_task(task, result)

    assert evaluation.passed is True
    assert evaluation.failures == ()


def test_golden_task_evaluator_fails_on_extra_cost_and_wrong_tool():
    task = next(task for task in load_golden_tasks(FIXTURE_PATH) if task.task_id == "dependency-version-lookup")
    result = GoldenTaskResult(
        task_id=task.task_id,
        actual_mode="plan_chat",
        actual_tools=("file_reader", "web_extract"),
        actual_cost_usd=Decimal("0.020"),
        actual_final_state="chat_only",
        mutation_count=0,
        provider_keys_resolvable=(),
    )

    evaluation = evaluate_golden_task(task, result)

    assert evaluation.passed is False
    assert "expected tool web_search at position 2, got web_extract" in evaluation.failures
    assert "actual cost 0.020 exceeds max 0.008" in evaluation.failures


def test_release_gate_task_fails_when_provider_key_is_resolvable():
    task = next(task for task in load_golden_tasks(FIXTURE_PATH) if task.task_id == "one-key-release-gate")
    result = GoldenTaskResult(
        task_id=task.task_id,
        actual_mode="agent",
        actual_tools=tuple(task.expected_tools),
        actual_cost_usd=Decimal("0.020"),
        actual_final_state="completed",
        mutation_count=1,
        provider_keys_resolvable=("OPENAI_API_KEY",),
    )

    evaluation = evaluate_golden_task(task, result)

    assert evaluation.passed is False
    assert "provider keys resolvable: OPENAI_API_KEY" in evaluation.failures
