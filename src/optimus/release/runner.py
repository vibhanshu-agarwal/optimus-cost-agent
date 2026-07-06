from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from optimus.telemetry.events import TelemetryEvent
from optimus.telemetry.redaction import redact_for_telemetry


@dataclass(frozen=True)
class ReleaseGateResult:
    name: str
    passed: bool
    output_summary: str
    duration_ms: int

    def to_json_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "passed": self.passed,
            "output_summary": self.output_summary,
            "duration_ms": self.duration_ms,
        }


class ReleaseGate(Protocol):
    name: str

    def run(self) -> ReleaseGateResult:
        raise NotImplementedError


class CallableGate:
    def __init__(self, *, name: str, run: Callable[[], tuple[bool, str]]) -> None:
        self.name = name
        self._run = run

    def run(self) -> ReleaseGateResult:
        started = datetime.now(tz=UTC)
        passed, summary = self._run()
        return ReleaseGateResult(
            name=self.name,
            passed=passed,
            output_summary=_safe_summary(summary),
            duration_ms=_duration_ms(started),
        )


CommandExecutor = Callable[[tuple[str, ...], float | None], tuple[int, str, str]]


@dataclass(frozen=True)
class CommandGate:
    name: str
    command: tuple[str, ...]
    timeout_seconds: float | None = 600.0
    executor: CommandExecutor | None = None

    def run(self) -> ReleaseGateResult:
        started = datetime.now(tz=UTC)
        try:
            exit_code, stdout, stderr = (self.executor or _run_command)(self.command, self.timeout_seconds)
            output = "\n".join(part for part in (stdout.strip(), stderr.strip()) if part)
            passed = exit_code == 0
            summary = output or f"exit_code={exit_code}"
        except TimeoutError as exc:
            passed = False
            summary = str(exc)
        return ReleaseGateResult(
            name=self.name,
            passed=passed,
            output_summary=_safe_summary(summary),
            duration_ms=_duration_ms(started),
        )


@dataclass(frozen=True)
class ReleaseGateReport:
    results: tuple[ReleaseGateResult, ...]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    def to_json_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "results": [result.to_json_dict() for result in self.results],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_json_dict(), sort_keys=True, indent=2)


class ReleaseGateRunner:
    def __init__(
        self,
        *,
        gates: tuple[ReleaseGate, ...],
        event_sink: Callable[[TelemetryEvent], None] | None = None,
        run_id: str = "release-gate",
        session_id: str | None = None,
    ) -> None:
        self._gates = gates
        self._event_sink = event_sink
        self._run_id = run_id
        self._session_id = session_id

    def run(self) -> ReleaseGateReport:
        results: list[ReleaseGateResult] = []
        for gate in self._gates:
            started = datetime.now(tz=UTC)
            try:
                result = gate.run()
            except Exception as exc:
                result = ReleaseGateResult(
                    name=gate.name,
                    passed=False,
                    output_summary=_safe_summary(f"{type(exc).__name__}: {exc}"),
                    duration_ms=_duration_ms(started),
                )
            results.append(result)
            if self._event_sink is not None:
                self._event_sink(
                    TelemetryEvent.release_gate(
                        run_id=self._run_id,
                        session_id=self._session_id,
                        request_id=gate.name,
                        occurred_at=datetime.now(tz=UTC),
                        gate_name=gate.name,
                        passed=result.passed,
                        duration_ms=result.duration_ms,
                        output_summary=result.output_summary,
                    )
                )
        return ReleaseGateReport(results=tuple(results))


def _run_command(command: tuple[str, ...], timeout_seconds: float | None) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"command {' '.join(command)} timed out after {timeout_seconds} seconds") from exc
    return completed.returncode, completed.stdout, completed.stderr


def _duration_ms(started: datetime) -> int:
    return max(int((datetime.now(tz=UTC) - started).total_seconds() * 1000), 0)


def _safe_summary(summary: str) -> str:
    redacted = redact_for_telemetry(summary)
    return str(redacted)
