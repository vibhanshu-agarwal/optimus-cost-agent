from __future__ import annotations

from pathlib import Path

from optimus.golden.runner import GoldenTaskHarness, evaluate_golden_task_suite
from optimus.golden.tasks import load_golden_tasks
from optimus.release.credentials import scan_local_credentials
from optimus.release.runner import CallableGate, CommandGate, ReleaseGate


def build_phase1_release_gates(
    *,
    python_executable: str = "python",
    golden_harness: GoldenTaskHarness | None = None,
) -> tuple[ReleaseGate, ...]:
    return (
        CommandGate(
            name="unit-and-integration-tests",
            command=(python_executable, "-m", "pytest", "tests/unit", "tests/integration", "-q"),
        ),
        CommandGate(
            name="coverage-80",
            command=(
                python_executable,
                "-m",
                "pytest",
                "--cov=optimus",
                "--cov-branch",
                "--cov-report=term-missing",
                "--cov-fail-under=80",
                "-q",
            ),
        ),
        CommandGate(
            name="diff-whitespace-check",
            command=("git", "diff", "--check"),
        ),
        CallableGate(name="golden-task-suite", run=lambda: _golden_task_suite_gate(golden_harness)),
        CallableGate(name="one-key-credential-scan", run=_one_key_credential_gate),
    )


def _golden_task_suite_gate(golden_harness: GoldenTaskHarness | None) -> tuple[bool, str]:
    if golden_harness is None:
        return False, "golden task harness not configured"
    tasks = load_golden_tasks(Path("tests/fixtures/golden_tasks/phase1_golden_tasks.json"))
    report = evaluate_golden_task_suite(tasks, harness=golden_harness)
    return report.passed, report.failure_summary


def _one_key_credential_gate() -> tuple[bool, str]:
    result = scan_local_credentials(
        config_paths=(
            Path(".env"),
            Path(".env.local"),
            Path("pyproject.toml"),
        )
    )
    return result.passed, result.summary
