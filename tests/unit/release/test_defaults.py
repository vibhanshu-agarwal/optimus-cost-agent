from __future__ import annotations

from optimus.release.defaults import build_phase1_release_gates


def test_default_phase1_release_gates_include_coverage_golden_and_one_key():
    gates = build_phase1_release_gates()
    names = [gate.name for gate in gates]

    assert "unit-and-integration-tests" in names
    assert "coverage-80" in names
    assert "golden-task-suite" in names
    assert "one-key-credential-scan" in names
    assert names[-1] == "one-key-credential-scan"


def test_default_golden_gate_fails_when_no_harness_is_configured():
    gates = build_phase1_release_gates()
    golden_gate = next(gate for gate in gates if gate.name == "golden-task-suite")

    result = golden_gate.run()

    assert result.passed is False
    assert "golden task harness not configured" in result.output_summary


from pathlib import Path


def test_phase1_release_gate_script_exists_and_uses_default_builder():
    script = Path("tools/run_phase1_release_gate.py")
    text = script.read_text(encoding="utf-8")

    assert "build_phase1_release_gates" in text
    assert "ReleaseGateRunner" in text
    assert "return 0 if report.passed else 1" in text
    assert "raise SystemExit(main())" in text


def test_default_one_key_gate_uses_release_scan_paths(monkeypatch, tmp_path):
    from optimus.release import defaults

    captured_paths: list[Path] = []

    class ScanResult:
        passed = True
        summary = "ok"

    def fake_scan_local_credentials(*, config_paths=(), environ=None):
        captured_paths.extend(Path(path) for path in config_paths)
        return ScanResult()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(defaults, "scan_local_credentials", fake_scan_local_credentials)

    gate = next(
        gate
        for gate in build_phase1_release_gates(credential_scan_root=tmp_path)
        if gate.name == "one-key-credential-scan"
    )
    result = gate.run()

    assert result.passed is True
    assert (tmp_path / "reports" / "phase1-golden-results.json").resolve() in captured_paths
    assert (tmp_path / "reports" / "process-state.json").resolve() in captured_paths


def test_phase1_release_gate_script_accepts_golden_results_argument():
    text = Path("tools/run_phase1_release_gate.py").read_text(encoding="utf-8")

    assert "--golden-results" in text
    assert "JsonGoldenTaskHarness.from_path" in text


def test_default_command_gates_receive_timeout():
    gates = build_phase1_release_gates(command_timeout_seconds=123.0)

    command_gates = [gate for gate in gates if getattr(gate, "command", None)]

    assert command_gates
    assert all(gate.timeout_seconds == 123.0 for gate in command_gates)


def test_phase1_release_gate_script_accepts_command_timeout_argument():
    text = Path("tools/run_phase1_release_gate.py").read_text(encoding="utf-8")

    assert "--command-timeout-seconds" in text
    assert "command_timeout_seconds=args.command_timeout_seconds" in text


def test_plan_9_5_golden_gate_filters_to_requested_task_ids():
    from decimal import Decimal

    from optimus.golden.tasks import GoldenTask, GoldenTaskResult
    from optimus.release.defaults import PLAN_9_5_REAL_AGENT_TASK_IDS, build_phase1_release_gates

    class StrictHarness:
        def run(self, task: GoldenTask) -> GoldenTaskResult:
            if task.task_id not in PLAN_9_5_REAL_AGENT_TASK_IDS:
                raise AssertionError(f"unexpected task {task.task_id}")
            return GoldenTaskResult(
                task_id=task.task_id,
                actual_mode=task.expected_mode,
                actual_tools=task.expected_tools,
                actual_cost_usd=Decimal("0"),
                actual_final_state=task.expected_final_state,
                mutation_count=1 if task.mutation_expected else 0,
                provider_keys_resolvable=(),
            )

    golden_gate = next(
        gate
        for gate in build_phase1_release_gates(
            golden_harness=StrictHarness(),
            golden_task_ids=PLAN_9_5_REAL_AGENT_TASK_IDS,
        )
        if gate.name == "golden-task-suite"
    )

    result = golden_gate.run()

    assert result.passed is True
