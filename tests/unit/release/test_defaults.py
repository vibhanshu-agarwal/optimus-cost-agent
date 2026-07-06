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
