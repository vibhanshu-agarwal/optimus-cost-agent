"""A result-aware loop detector for interactive planning (Plan 12.3, Design 2; ADR-024).

Every trigger compares results, not only actions: polling that returns changing results never
fires. Defaults are the operator's D2 thresholds (3).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from optimus.loops.signals import ActionKind, LoopStep


class LoopSignalKind(StrEnum):
    REPEATED_READ = "REPEATED_READ"
    REPEATED_MCP = "REPEATED_MCP"
    CYCLE = "CYCLE"
    NO_PROGRESS = "NO_PROGRESS"
    REPEATED_PARSE_ERROR = "REPEATED_PARSE_ERROR"


class LoopThresholds(BaseModel):
    model_config = ConfigDict(frozen=True)

    repeat: int = Field(default=3, ge=2)
    cycles: int = Field(default=3, ge=2)
    no_progress: int = Field(default=3, ge=2)
    repeated_error: int = Field(default=3, ge=2)


@dataclass(frozen=True)
class LoopDetection:
    kind: LoopSignalKind
    step: LoopStep
    """The step that completed the pattern."""


_REPEAT_KINDS = {
    ActionKind.READ: LoopSignalKind.REPEATED_READ,
    ActionKind.MCP: LoopSignalKind.REPEATED_MCP,
    ActionKind.PARSE_FAILURE: LoopSignalKind.REPEATED_PARSE_ERROR,
}


class LoopDetector:
    def __init__(self, thresholds: LoopThresholds | None = None) -> None:
        self._thresholds = thresholds or LoopThresholds()
        t = self._thresholds
        self._steps: deque[LoopStep] = deque(maxlen=max(t.repeat, 2 * t.cycles, t.no_progress, t.repeated_error))

    def reset(self) -> None:
        """Forget the streaks; a new episode needs a fresh pattern. Read coverage is kept by its owner."""
        self._steps.clear()

    def observe(self, step: LoopStep) -> LoopDetection | None:
        """Record `step`; the most specific pattern it completes, if any."""
        self._steps.append(step)
        t = self._thresholds
        last = self._last(t.repeated_error)
        if last and last[0].error_class is not None and all(s.error_class == last[0].error_class for s in last):
            return LoopDetection(LoopSignalKind.REPEATED_PARSE_ERROR, step)
        last = self._last(t.repeat)
        if last and all(_identity(s) == _identity(step) for s in last):
            return LoopDetection(_REPEAT_KINDS[step.kind], step)
        last = self._last(2 * t.cycles)
        if (
            last
            and _identity(last[0]) != _identity(last[1])
            and all(_identity(s) == _identity(last[i % 2]) for i, s in enumerate(last))
        ):
            return LoopDetection(LoopSignalKind.CYCLE, step)
        last = self._last(t.no_progress)
        if last and not any(s.novel for s in last):
            return LoopDetection(LoopSignalKind.NO_PROGRESS, step)
        return None

    def _last(self, count: int) -> list[LoopStep]:
        return list(self._steps)[-count:] if len(self._steps) >= count else []


def _identity(step: LoopStep) -> tuple[str, str]:
    return step.fingerprint, step.result_digest
