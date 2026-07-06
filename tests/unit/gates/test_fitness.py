from __future__ import annotations

from optimus.gates.fitness import (
    CompositeGateError,
    FitnessCheck,
    FitnessGateRunner,
    GateResult,
    GateStatus,
)


class PassingCheck:
    name = "unit-tests"
    required = True

    def run(self) -> GateResult:
        return GateResult.pass_(name=self.name, summary="tests passed", duration_ms=12)


class FailingCheck:
    name = "coverage"
    required = True

    def run(self) -> GateResult:
        return GateResult.fail(name=self.name, summary="coverage below threshold", duration_ms=8)


class OptionalFailingCheck:
    name = "future-context-regret"
    required = False

    def run(self) -> GateResult:
        return GateResult.fail(name=self.name, summary="future Plan 10 signal", duration_ms=1)


class RaisingCheck:
    name = "architecture"
    required = True

    def run(self) -> GateResult:
        raise RuntimeError("tool crashed")


def test_composite_gate_passes_when_required_checks_pass():
    result = FitnessGateRunner(checks=(PassingCheck(),)).run()

    assert result.passed is True
    assert result.required_gate_names == ("unit-tests",)
    assert result.failed_gate_names == ()
    assert result.results[0].status is GateStatus.PASS


def test_required_gate_failure_fails_composite_result():
    result = FitnessGateRunner(checks=(PassingCheck(), FailingCheck())).run()

    assert result.passed is False
    assert result.failed_gate_names == ("coverage",)


def test_optional_gate_failure_does_not_block_composite_result():
    result = FitnessGateRunner(checks=(PassingCheck(), OptionalFailingCheck())).run()

    assert result.passed is True
    assert result.failed_gate_names == ()
    assert result.warning_gate_names == ("future-context-regret",)


def test_gate_exception_fails_closed():
    result = FitnessGateRunner(checks=(RaisingCheck(),)).run()

    assert result.passed is False
    assert result.failed_gate_names == ("architecture",)
    assert result.results[0].status is GateStatus.ERROR
    assert "RuntimeError" in result.results[0].summary


def test_raise_for_failure_uses_tight_failure_summary():
    result = FitnessGateRunner(checks=(FailingCheck(),)).run()

    try:
        result.raise_for_failure()
    except CompositeGateError as exc:
        assert exc.result == result
        assert str(exc) == "required fitness gates failed: coverage"
    else:
        raise AssertionError("expected CompositeGateError")


def test_protocol_accepts_fitness_check_instances():
    check: FitnessCheck = PassingCheck()

    assert check.name == "unit-tests"
    assert check.required is True
