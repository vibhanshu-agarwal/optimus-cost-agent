from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from optimus.golden.tasks import GoldenTask, GoldenTaskEvaluation, GoldenTaskResult, evaluate_golden_task
from optimus.telemetry.events import TelemetryEvent


class GoldenTaskHarness(Protocol):
    def run(self, task: GoldenTask) -> GoldenTaskResult:
        raise NotImplementedError


@dataclass(frozen=True)
class GoldenTaskSuiteReport:
    evaluations: tuple[GoldenTaskEvaluation, ...]

    @property
    def passed(self) -> bool:
        return all(evaluation.passed for evaluation in self.evaluations)

    @property
    def failure_summary(self) -> str:
        failures = [
            f"{evaluation.task.task_id}: {'; '.join(evaluation.failures)}"
            for evaluation in self.evaluations
            if not evaluation.passed
        ]
        return "all golden tasks passed" if not failures else " | ".join(failures)


def evaluate_golden_task_suite(
    tasks: tuple[GoldenTask, ...],
    *,
    harness: GoldenTaskHarness,
    event_sink: Callable[[TelemetryEvent], None] | None = None,
    run_id: str = "golden-task-suite",
    session_id: str | None = None,
) -> GoldenTaskSuiteReport:
    evaluations: list[GoldenTaskEvaluation] = []
    for task in tasks:
        evaluation = evaluate_golden_task(task, harness.run(task))
        evaluations.append(evaluation)
        if event_sink is not None:
            event_sink(
                TelemetryEvent.golden_task(
                    run_id=run_id,
                    session_id=session_id,
                    request_id=task.task_id,
                    occurred_at=datetime.now(tz=UTC),
                    task_id=task.task_id,
                    passed=evaluation.passed,
                    expected_mode=task.expected_mode,
                    actual_mode=evaluation.result.actual_mode,
                    expected_tools=tuple(task.expected_tools),
                    actual_tools=evaluation.result.actual_tools,
                    max_cost_usd=task.max_cost_usd,
                    actual_cost_usd=evaluation.result.actual_cost_usd,
                    expected_final_state=task.expected_final_state,
                    actual_final_state=evaluation.result.actual_final_state,
                )
            )
    return GoldenTaskSuiteReport(
        evaluations=tuple(evaluations)
    )
