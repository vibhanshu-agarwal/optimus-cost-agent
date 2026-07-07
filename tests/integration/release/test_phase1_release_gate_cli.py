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


def test_release_cli_accepts_agent_harness_task_filter_text():
    text = RELEASE_CLI.read_text(encoding="utf-8")

    assert "--agent-harness" in text
    assert "--task-id" in text
    assert "AgentGoldenTaskHarness" in text
    assert "golden_task_ids=golden_task_ids" in text


def test_readme_documents_spawnable_acp_agent_contract():
    text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "python -m optimus.acp --workspace-root" in text
    assert "optimus-agent --workspace-root" in text
    assert "OPTIMUS_REDIS_URL=redis://localhost:6379/0" in text
    assert "initialize" in text
    assert "session/new" in text
    assert "session/prompt" in text
    assert "session/request_permission" in text
    assert "agent_servers" in text
    assert "session/cancel" in text
    assert "approval_id" in text
    assert "plan_hash" in text
    assert "plan approval expires after 3600 seconds" in text


def test_release_cli_wires_redis_backed_agent_harness():
    text = RELEASE_CLI.read_text(encoding="utf-8")

    assert "OPTIMUS_REDIS_URL" in text
    assert "RedisAgentStateStore" in text
    assert ".ping()" in text
    assert "build_agent_runner_for_harness" in text
    assert "PLAN_9_5_REAL_AGENT_TASK_IDS" in text
    assert "reports/plan-9-5-working-agent-smoke-transcript.json" in text


def test_release_cli_agent_harness_pings_redis_before_golden_tasks(tmp_path, monkeypatch):
    ping_calls: list[bool] = []

    class FakeStore:
        def ping(self):
            ping_calls.append(True)

    class FakeRuntime:
        def ping(self):
            ping_calls.append(True)

        def sync_state_store(self):
            return FakeStore()

        def telemetry_adapter(self):
            return object()

    monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "https://gateway.optimus.ai")
    monkeypatch.setenv("OPTIMUS_API_KEY", "opt-test")
    monkeypatch.setenv("OPTIMUS_REDIS_URL", "redis://127.0.0.1:6379/0")
    monkeypatch.setattr("optimus.acp.bootstrap.RedisRuntime.from_url", lambda url: FakeRuntime())

    class FakeGatewayClient:
        def create_response(self, *, model: str, input_text: str, metadata=None):
            from decimal import Decimal

            from optimus.gateway.models import GatewayResponse, GatewayUsage

            return GatewayResponse(
                response_id="resp-1",
                output_text="READ src/example.py\nExplain the function.",
                gateway_usage=GatewayUsage(
                    gateway_request_id="gw-1",
                    provider="glm",
                    billing_units=1,
                    cost_usd=Decimal("0.001"),
                ),
                raw={"id": "resp-1"},
            )

    monkeypatch.setattr("optimus.gateway.client.GatewayClient", lambda settings: FakeGatewayClient())
    monkeypatch.setattr(
        "optimus.release.defaults.evaluate_golden_task_suite",
        lambda tasks, harness: type("Report", (), {"passed": True, "failure_summary": ""})(),
    )
    transcript_path = tmp_path / "plan-9-5-working-agent-smoke-transcript.json"
    monkeypatch.setattr(
        "optimus.release.agent_smoke_transcript.PLAN_9_5_SMOKE_TRANSCRIPT_PATH",
        transcript_path,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_phase1_release_gate.py",
            "--agent-harness",
            "--task-id",
            "explain-small-function",
            "--credential-scan-root",
            str(tmp_path),
            "--skip-command-gates-for-test",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(RELEASE_CLI), run_name="__main__")

    assert exc.value.code in {0, 1}
    assert ping_calls == [True]
    assert transcript_path.is_file()
