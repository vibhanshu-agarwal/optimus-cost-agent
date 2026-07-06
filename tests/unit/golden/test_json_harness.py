from __future__ import annotations

from decimal import Decimal

import pytest

from optimus.golden.json_harness import JsonGoldenTaskHarness, load_golden_results
from optimus.golden.tasks import GoldenTask, GoldenTaskResult


def task(task_id: str = "explain-small-function") -> GoldenTask:
    return GoldenTask(
        task_id=task_id,
        description="Explain a function.",
        expected_mode="plan_chat",
        expected_tools=("file_reader",),
        max_cost_usd=Decimal("0.005"),
        expected_final_state="chat_only",
        mutation_expected=False,
        release_gate=False,
    )


def test_load_golden_results_maps_results_by_task_id(tmp_path):
    path = tmp_path / "phase1-golden-results.json"
    path.write_text(
        """
        {
          "results": [
            {
              "task_id": "explain-small-function",
              "actual_mode": "plan_chat",
              "actual_tools": ["file_reader"],
              "actual_cost_usd": "0.004",
              "actual_final_state": "chat_only",
              "mutation_count": 0,
              "provider_keys_resolvable": []
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    results = load_golden_results(path)

    assert results["explain-small-function"] == GoldenTaskResult(
        task_id="explain-small-function",
        actual_mode="plan_chat",
        actual_tools=("file_reader",),
        actual_cost_usd=Decimal("0.004"),
        actual_final_state="chat_only",
        mutation_count=0,
        provider_keys_resolvable=(),
    )


def test_json_harness_returns_result_for_requested_task(tmp_path):
    path = tmp_path / "phase1-golden-results.json"
    path.write_text(
        '{"results":[{"task_id":"explain-small-function","actual_mode":"plan_chat","actual_tools":["file_reader"],"actual_cost_usd":"0.004","actual_final_state":"chat_only","mutation_count":0,"provider_keys_resolvable":[]}]}',
        encoding="utf-8",
    )

    harness = JsonGoldenTaskHarness.from_path(path)

    assert harness.run(task()).task_id == "explain-small-function"


def test_json_harness_fails_closed_for_missing_task_result(tmp_path):
    path = tmp_path / "phase1-golden-results.json"
    path.write_text('{"results":[]}', encoding="utf-8")

    harness = JsonGoldenTaskHarness.from_path(path)

    with pytest.raises(KeyError, match="missing golden result for explain-small-function"):
        harness.run(task())
