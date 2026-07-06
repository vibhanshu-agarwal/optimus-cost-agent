from __future__ import annotations

from optimus.release.runner import CallableGate, CommandGate, ReleaseGateRunner


def test_release_runner_executes_gates_in_order_and_reports_pass():
    seen: list[str] = []
    gates = (
        CallableGate(name="first", run=lambda: seen.append("first") or (True, "ok")),
        CallableGate(name="second", run=lambda: seen.append("second") or (True, "ok")),
    )

    report = ReleaseGateRunner(gates=gates).run()

    assert report.passed is True
    assert seen == ["first", "second"]
    assert [result.name for result in report.results] == ["first", "second"]


def test_release_runner_continues_after_failure_to_collect_full_report():
    gates = (
        CallableGate(name="first", run=lambda: (False, "failed")),
        CallableGate(name="second", run=lambda: (True, "ok")),
    )

    report = ReleaseGateRunner(gates=gates).run()

    assert report.passed is False
    assert [(result.name, result.passed) for result in report.results] == [("first", False), ("second", True)]


def test_command_gate_uses_injected_executor_and_redacts_output():
    commands: list[tuple[str, ...]] = []

    def executor(command: tuple[str, ...], timeout_seconds: float | None) -> tuple[int, str, str]:
        commands.append(command)
        return (1, "OPENAI_API_KEY=sk-test", "")

    gate = CommandGate(name="provider-key-check", command=("python", "-c", "print('x')"), executor=executor)

    result = gate.run()

    assert result.passed is False
    assert commands == [("python", "-c", "print('x')")]
    assert "sk-test" not in result.output_summary
    assert "**********" in result.output_summary


def test_release_report_serializes_to_json_dict():
    report = ReleaseGateRunner(gates=(CallableGate(name="gate", run=lambda: (True, "ok")),)).run()

    assert report.to_json_dict()["passed"] is True
    assert report.to_json_dict()["results"][0]["name"] == "gate"


def test_command_gate_reports_timeout_as_failed_gate():
    def executor(command: tuple[str, ...], timeout_seconds: float | None) -> tuple[int, str, str]:
        raise TimeoutError(f"command timed out after {timeout_seconds} seconds")

    gate = CommandGate(
        name="slow-tests",
        command=("python", "-m", "pytest"),
        timeout_seconds=0.01,
        executor=executor,
    )

    result = gate.run()

    assert result.passed is False
    assert "timed out after 0.01 seconds" in result.output_summary


def test_release_runner_continues_after_command_timeout():
    def timeout_executor(command: tuple[str, ...], timeout_seconds: float | None) -> tuple[int, str, str]:
        raise TimeoutError("command timed out after 1.0 seconds")

    report = ReleaseGateRunner(
        gates=(
            CommandGate(name="slow", command=("slow",), timeout_seconds=1.0, executor=timeout_executor),
            CallableGate(name="after", run=lambda: (True, "ok")),
        )
    ).run()

    assert report.passed is False
    assert [(result.name, result.passed) for result in report.results] == [("slow", False), ("after", True)]


def test_release_runner_continues_after_gate_raises():
    class RaisingGate:
        name = "broken"

        def run(self) -> None:
            raise FileNotFoundError("no such executable")

    report = ReleaseGateRunner(
        gates=(
            RaisingGate(),
            CallableGate(name="after", run=lambda: (True, "ok")),
        )
    ).run()

    assert report.passed is False
    assert [(result.name, result.passed) for result in report.results] == [("broken", False), ("after", True)]
    assert "FileNotFoundError" in report.results[0].output_summary
