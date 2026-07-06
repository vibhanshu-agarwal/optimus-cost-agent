from __future__ import annotations

from optimus.release.runner import CallableGate, ReleaseGateRunner


def test_injected_phase1_release_runner_reports_golden_and_one_key_results():
    report = ReleaseGateRunner(
        gates=(
            CallableGate(name="golden-task-suite", run=lambda: (True, "10 golden tasks evaluated")),
            CallableGate(name="one-key-credential-scan", run=lambda: (True, "allowed Optimus credentials present")),
        )
    ).run()

    assert report.passed is True
    assert [result.name for result in report.results] == ["golden-task-suite", "one-key-credential-scan"]
