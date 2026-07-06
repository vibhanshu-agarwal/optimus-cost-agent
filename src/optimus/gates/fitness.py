from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class GateStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIP = "skip"


@dataclass(frozen=True)
class GateResult:
    name: str
    status: GateStatus
    summary: str
    duration_ms: int = 0
    required: bool = True

    @classmethod
    def pass_(cls, *, name: str, summary: str, duration_ms: int = 0, required: bool = True) -> GateResult:
        return cls(name=name, status=GateStatus.PASS, summary=summary, duration_ms=duration_ms, required=required)

    @classmethod
    def fail(cls, *, name: str, summary: str, duration_ms: int = 0, required: bool = True) -> GateResult:
        return cls(name=name, status=GateStatus.FAIL, summary=summary, duration_ms=duration_ms, required=required)

    @classmethod
    def error(cls, *, name: str, summary: str, duration_ms: int = 0, required: bool = True) -> GateResult:
        return cls(name=name, status=GateStatus.ERROR, summary=summary, duration_ms=duration_ms, required=required)


class FitnessCheck(Protocol):
    name: str
    required: bool

    def run(self) -> GateResult:
        raise NotImplementedError


@dataclass(frozen=True)
class CompositeGateResult:
    results: tuple[GateResult, ...]

    @property
    def passed(self) -> bool:
        return not self.failed_gate_names

    @property
    def required_gate_names(self) -> tuple[str, ...]:
        return tuple(result.name for result in self.results if result.required)

    @property
    def failed_gate_names(self) -> tuple[str, ...]:
        return tuple(
            result.name
            for result in self.results
            if result.required and result.status in {GateStatus.FAIL, GateStatus.ERROR}
        )

    @property
    def warning_gate_names(self) -> tuple[str, ...]:
        return tuple(
            result.name
            for result in self.results
            if not result.required and result.status in {GateStatus.FAIL, GateStatus.ERROR}
        )

    @property
    def duration_ms(self) -> int:
        return sum(result.duration_ms for result in self.results)

    def raise_for_failure(self) -> None:
        if not self.passed:
            raise CompositeGateError(self)


class CompositeGateError(Exception):
    def __init__(self, result: CompositeGateResult) -> None:
        self.result = result
        super().__init__(f"required fitness gates failed: {', '.join(result.failed_gate_names)}")


class FitnessGateRunner:
    def __init__(self, *, checks: tuple[FitnessCheck, ...]) -> None:
        self._checks = checks

    def run(self) -> CompositeGateResult:
        results: list[GateResult] = []
        for check in self._checks:
            try:
                result = check.run()
            except Exception as exc:
                result = GateResult.error(
                    name=check.name,
                    summary=f"{type(exc).__name__}: {exc}",
                    required=check.required,
                )
            if result.required != check.required:
                result = GateResult(
                    name=result.name,
                    status=result.status,
                    summary=result.summary,
                    duration_ms=result.duration_ms,
                    required=check.required,
                )
            results.append(result)
        return CompositeGateResult(results=tuple(results))
