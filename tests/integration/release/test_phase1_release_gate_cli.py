from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from optimus.golden.tasks import load_golden_tasks

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RELEASE_CLI = PROJECT_ROOT / "tools" / "run_phase1_release_gate.py"


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


def _release_cli_env(monkeypatch) -> dict[str, str]:
    monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "https://gateway.example")
    monkeypatch.setenv("OPTIMUS_API_KEY", "opt-test")
    for provider_key in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "TAVILY_API_KEY", "GLM_API_KEY", "LANGSMITH_API_KEY"):
        monkeypatch.delenv(provider_key, raising=False)
    return {**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")}


def _release_cli_argv(*, results_path: Path, scan_root: Path) -> list[str]:
    return [
        str(RELEASE_CLI),
        "--golden-results",
        str(results_path),
        "--credential-scan-root",
        str(scan_root),
        "--skip-command-gates-for-test",
    ]


def _run_release_cli_subprocess(
    *,
    argv: list[str],
    env: dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
) -> int:
    # File-backed pipes avoid WinError 6 when pytest captures stdio on Windows.
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        completed = subprocess.run(
            [sys.executable, *argv],
            check=False,
            cwd=PROJECT_ROOT,
            env=env,
            stdout=stdout,
            stderr=stderr,
            stdin=subprocess.DEVNULL,
            text=True,
        )
    return completed.returncode


def test_release_cli_accepts_golden_results_path(tmp_path, monkeypatch):
    results_path = tmp_path / "phase1-golden-results.json"
    write_matching_results(results_path)
    env = _release_cli_env(monkeypatch)
    stdout_path = tmp_path / "stdout.txt"
    stderr_path = tmp_path / "stderr.txt"

    exit_code = _run_release_cli_subprocess(
        argv=_release_cli_argv(results_path=results_path, scan_root=tmp_path),
        env=env,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )

    assert exit_code == 0, stderr_path.read_text(encoding="utf-8")
    report = json.loads(stdout_path.read_text(encoding="utf-8"))
    assert report["passed"] is True
    assert any(result["name"] == "golden-task-suite" and result["passed"] for result in report["results"])


def test_release_cli_main_in_process(tmp_path, monkeypatch):
    results_path = tmp_path / "phase1-golden-results.json"
    write_matching_results(results_path)
    _release_cli_env(monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_phase1_release_gate.py",
            "--golden-results",
            str(results_path),
            "--credential-scan-root",
            str(tmp_path),
            "--skip-command-gates-for-test",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(RELEASE_CLI), run_name="__main__")

    assert exc.value.code == 0
