"""Deterministic golden-task fixtures and evaluation for Phase 1 regression checks.

A GoldenTask is a versioned, deterministic regression scenario for the Optimus Cost
Agent. It encodes what a correct end-to-end run should look like — not a live user
prompt, but a fixture with expected behavior used to catch regressions before release.

The name follows the usual "golden file / golden test" pattern: a known-good reference
compared against actual runs.

Workflow:
    1. ``load_golden_tasks()`` reads versioned JSON (e.g.
       ``tests/fixtures/golden_tasks/phase1_golden_tasks.json``) into ``GoldenTask``
       models.
    2. A ``GoldenTaskHarness`` (see ``optimus.golden.runner``) runs each task and
       returns a ``GoldenTaskResult`` with observed mode, tools, cost, state, mutation
       count, and resolvable provider keys.
    3. ``evaluate_golden_task()`` compares expected vs actual and returns pass/fail with
       specific failure messages (wrong tool at position N, cost over budget, etc.).
    4. ``evaluate_golden_task_suite()`` runs the full suite; the Phase 1 release runner
       includes this as the ``golden-task-suite`` gate.

This is E2E regression testing with deterministic scoring — not LLM-judged eval (that
remains a Gateway-routed extension). ``GoldenTask`` is the spec; the harness executes
the agent and produces ``GoldenTaskResult``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class GoldenTask(BaseModel):
    """Frozen expected behavior for one scripted agent scenario.

    Each field defines part of the "correct run" contract:

    - ``task_id`` / ``description``: stable ID and human-readable scenario name.
    - ``expected_mode``: runtime mode (e.g. ``plan_chat`` vs ``agent``).
    - ``expected_tools``: ordered tool trajectory; sequence and position matter.
    - ``max_cost_usd``: cost ceiling; actual cost must stay at or below this value.
    - ``expected_final_state``: terminal state (``chat_only``, ``completed``,
      ``terminated``, etc.).
    - ``mutation_expected``: whether the run should mutate the workspace.
    - ``release_gate``: when true, also enforces the one-key model — no local provider
      keys may be resolvable in the run environment.

    Examples: "explain a small function" (plan-only, no mutation) or "add a docstring"
    (agent mode, ``write_file``, mutation expected). See ``phase1_golden_tasks.json``.
    """

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
    """Observed outcome from a harness run of a single ``GoldenTask``.

    Produced by ``GoldenTaskHarness.run()``; consumed by ``evaluate_golden_task()``.
    """

    task_id: str
    actual_mode: str
    actual_tools: tuple[str, ...]
    actual_cost_usd: Decimal
    actual_final_state: str
    mutation_count: int
    provider_keys_resolvable: tuple[str, ...]


@dataclass(frozen=True)
class GoldenTaskEvaluation:
    """Pass/fail verdict with human-readable failure reasons."""

    task: GoldenTask
    result: GoldenTaskResult
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


def load_golden_tasks(path: str | Path) -> tuple[GoldenTask, ...]:
    """Load versioned golden-task fixtures from JSON into frozen ``GoldenTask`` models."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"), parse_float=Decimal)
    return tuple(GoldenTask.model_validate(task) for task in payload["tasks"])


def evaluate_golden_task(task: GoldenTask, result: GoldenTaskResult) -> GoldenTaskEvaluation:
    """Compare a harness result against the golden-task spec.

    Checks mode, ordered tool trajectory, cost band, final state, mutation policy,
    and (for release-gate tasks) that no provider keys were resolvable locally.
    """
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
