"""Discovered-multiplier audit cost calculation."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True, slots=True)
class AuditCost:
    cancellation_concurrency_levels: tuple[int, int, int]
    cancellation_schedules: int
    cancellation_control_schedules: int
    queue_admissions: int
    sink_failure_runs: int
    idempotent_close_invocations: int
    scenario_p50_ms: Mapping[str, float]
    scenario_p95_ms: Mapping[str, float]

    def to_dict(self) -> dict[str, object]:
        return {
            "cancellation_concurrency_levels": list(self.cancellation_concurrency_levels),
            "cancellation_schedules": self.cancellation_schedules,
            "cancellation_control_schedules": self.cancellation_control_schedules,
            "queue_admissions": self.queue_admissions,
            "sink_failure_runs": self.sink_failure_runs,
            "idempotent_close_invocations": self.idempotent_close_invocations,
            "scenario_p50_ms": dict(self.scenario_p50_ms),
            "scenario_p95_ms": dict(self.scenario_p95_ms),
        }


def _p95(values: Sequence[float]) -> float:
    ordered = sorted(values)
    return float(ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)])


def compute_cost(
    *,
    cancellation_points: int,
    queues: int,
    sinks: int,
    close_paths: int,
    seed_count: int,
    admission_probe_count: int,
    sink_failure_count: int,
    scenario_durations_ms: Mapping[str, Sequence[float]],
) -> AuditCost:
    counts = (cancellation_points, queues, sinks, close_paths, seed_count, admission_probe_count, sink_failure_count)
    if any(value < 0 for value in counts):
        raise ValueError("cost multipliers must be non-negative")
    if any(not durations for durations in scenario_durations_ms.values()):
        raise ValueError("measured scenario duration series must be non-empty")
    levels = (2, 4, 8)
    p50 = {name: float(statistics.median(durations)) for name, durations in sorted(scenario_durations_ms.items())}
    p95 = {name: _p95(durations) for name, durations in sorted(scenario_durations_ms.items())}
    return AuditCost(
        cancellation_concurrency_levels=levels,
        cancellation_schedules=cancellation_points * len(levels) * seed_count,
        cancellation_control_schedules=cancellation_points * seed_count,
        queue_admissions=queues * admission_probe_count,
        sink_failure_runs=sinks * sink_failure_count,
        idempotent_close_invocations=close_paths * 3 * 5,
        scenario_p50_ms=p50,
        scenario_p95_ms=p95,
    )
