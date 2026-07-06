from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from optimus.golden.runner import GoldenTaskHarness, evaluate_golden_task_suite
from optimus.golden.tasks import GoldenTask, GoldenTaskResult, load_golden_tasks

FIXTURE_PATH = Path("tests/fixtures/golden_tasks/phase1_golden_tasks.json")


class FakeHarness:
    def run(self, task: GoldenTask) -> GoldenTaskResult:
        return GoldenTaskResult(
            task_id=task.task_id,
            actual_mode=task.expected_mode,
            actual_tools=tuple(task.expected_tools),
            actual_cost_usd=task.max_cost_usd,
            actual_final_state=task.expected_final_state,
            mutation_count=1 if task.mutation_expected else 0,
            provider_keys_resolvable=(),
        )


class LeakyHarness:
    def run(self, task: GoldenTask) -> GoldenTaskResult:
        return GoldenTaskResult(
            task_id=task.task_id,
            actual_mode=task.expected_mode,
            actual_tools=tuple(task.expected_tools),
            actual_cost_usd=Decimal("0"),
            actual_final_state=task.expected_final_state,
            mutation_count=1 if task.mutation_expected else 0,
            provider_keys_resolvable=("OPENAI_API_KEY",) if task.release_gate else (),
        )


def test_fake_harness_satisfies_golden_task_protocol():
    harness: GoldenTaskHarness = FakeHarness()
    task = load_golden_tasks(FIXTURE_PATH)[0]

    assert harness.run(task).task_id == task.task_id


def test_evaluate_golden_task_suite_passes_when_harness_matches_expectations():
    report = evaluate_golden_task_suite(load_golden_tasks(FIXTURE_PATH), harness=FakeHarness())

    assert report.passed is True
    assert len(report.evaluations) == 10


def test_evaluate_golden_task_suite_fails_when_release_gate_result_leaks_provider_key():
    report = evaluate_golden_task_suite(load_golden_tasks(FIXTURE_PATH), harness=LeakyHarness())

    assert report.passed is False
    assert any("provider keys resolvable" in failure for evaluation in report.evaluations for failure in evaluation.failures)
