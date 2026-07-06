from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class GoldenTask(BaseModel):
    model_config = ConfigDict(frozen=True)

    task_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    expected_mode: str = Field(min_length=1)
    expected_tools: tuple[str, ...]
    max_cost_usd: Decimal = Field(ge=Decimal("0"))
    expected_final_state: str = Field(min_length=1)
    mutation_expected: bool
    release_gate: bool = False


@dataclass(frozen=True)
class GoldenTaskResult:
    task_id: str
    actual_mode: str
    actual_tools: tuple[str, ...]
    actual_cost_usd: Decimal
    actual_final_state: str
    mutation_count: int
    provider_keys_resolvable: tuple[str, ...]


@dataclass(frozen=True)
class GoldenTaskEvaluation:
    task: GoldenTask
    result: GoldenTaskResult
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


def load_golden_tasks(path: str | Path) -> tuple[GoldenTask, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"), parse_float=Decimal)
    return tuple(GoldenTask.model_validate(task) for task in payload["tasks"])


def evaluate_golden_task(task: GoldenTask, result: GoldenTaskResult) -> GoldenTaskEvaluation:
    failures: list[str] = []
    if result.task_id != task.task_id:
        failures.append(f"expected task_id {task.task_id}, got {result.task_id}")
    if result.actual_mode != task.expected_mode:
        failures.append(f"expected mode {task.expected_mode}, got {result.actual_mode}")
    failures.extend(_tool_failures(task.expected_tools, result.actual_tools))
    if result.actual_cost_usd > task.max_cost_usd:
        failures.append(f"actual cost {result.actual_cost_usd} exceeds max {task.max_cost_usd}")
    if result.actual_final_state != task.expected_final_state:
        failures.append(f"expected final state {task.expected_final_state}, got {result.actual_final_state}")
    if task.mutation_expected and result.mutation_count <= 0:
        failures.append("expected at least one mutation")
    if not task.mutation_expected and result.mutation_count != 0:
        failures.append(f"expected zero mutations, got {result.mutation_count}")
    if task.release_gate and result.provider_keys_resolvable:
        failures.append(f"provider keys resolvable: {', '.join(sorted(result.provider_keys_resolvable))}")
    return GoldenTaskEvaluation(task=task, result=result, failures=tuple(failures))


def _tool_failures(expected: tuple[str, ...], actual: tuple[str, ...]) -> tuple[str, ...]:
    failures: list[str] = []
    for index, expected_tool in enumerate(expected):
        if index >= len(actual):
            failures.append(f"missing expected tool {expected_tool} at position {index + 1}")
            continue
        actual_tool = actual[index]
        if actual_tool != expected_tool:
            failures.append(f"expected tool {expected_tool} at position {index + 1}, got {actual_tool}")
    if len(actual) > len(expected):
        extra = ", ".join(actual[len(expected) :])
        failures.append(f"unexpected extra tools: {extra}")
    return tuple(failures)
