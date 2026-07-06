from __future__ import annotations

import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

from optimus.golden.tasks import load_golden_tasks

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def write_matching_results(path: Path) -> None:
    tasks = load_golden_tasks("tests/fixtures/golden_tasks/phase1_golden_tasks.json")
    payload = {
        "results": [
            {
                "task_id": task.task_id,
                "actual_mode": task.expected_mode,
                "actual_tools": list(task.expected_tools),
                "actual_cost_usd": str(min(task.max_cost_usd, Decimal("0.001"))),
                "actual_final_state": task.expected_final_state,
                "mutation_count": 1 if task.mutation_expected else 0,
                "provider_keys_resolvable": [],
            }
            for task in tasks
        ]
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_release_cli_accepts_golden_results_path(tmp_path, monkeypatch):
    results_path = tmp_path / "phase1-golden-results.json"
    write_matching_results(results_path)
    monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "https://gateway.example")
    monkeypatch.setenv("OPTIMUS_API_KEY", "opt-test")
    for provider_key in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "TAVILY_API_KEY", "GLM_API_KEY", "LANGSMITH_API_KEY"):
        monkeypatch.delenv(provider_key, raising=False)

    completed = subprocess.run(
        [
            sys.executable,
            "tools/run_phase1_release_gate.py",
            "--golden-results",
            str(results_path),
            "--credential-scan-root",
            str(tmp_path),
            "--skip-command-gates-for-test",
        ],
        check=False,
        text=True,
        capture_output=True,
        cwd=PROJECT_ROOT,
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")},
    )

    assert completed.returncode == 0
    report = json.loads(completed.stdout)
    assert report["passed"] is True
    assert any(result["name"] == "golden-task-suite" and result["passed"] for result in report["results"])
