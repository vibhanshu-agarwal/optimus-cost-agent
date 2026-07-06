from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from optimus.golden.tasks import GoldenTask, GoldenTaskResult


def load_golden_results(path: str | Path) -> dict[str, GoldenTaskResult]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"), parse_float=Decimal)
    results: dict[str, GoldenTaskResult] = {}
    for item in payload.get("results", ()):
        result = GoldenTaskResult(
            task_id=str(item["task_id"]),
            actual_mode=str(item["actual_mode"]),
            actual_tools=tuple(str(tool) for tool in item["actual_tools"]),
            actual_cost_usd=Decimal(str(item["actual_cost_usd"])),
            actual_final_state=str(item["actual_final_state"]),
            mutation_count=int(item["mutation_count"]),
            provider_keys_resolvable=tuple(str(key) for key in item.get("provider_keys_resolvable", ())),
        )
        results[result.task_id] = result
    return results


class JsonGoldenTaskHarness:
    def __init__(self, *, results: dict[str, GoldenTaskResult]) -> None:
        self._results = dict(results)

    @classmethod
    def from_path(cls, path: str | Path) -> JsonGoldenTaskHarness:
        return cls(results=load_golden_results(path))

    def run(self, task: GoldenTask) -> GoldenTaskResult:
        try:
            return self._results[task.task_id]
        except KeyError as exc:
            raise KeyError(f"missing golden result for {task.task_id}") from exc
