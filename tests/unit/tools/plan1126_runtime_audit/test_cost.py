"""Discovered-multiplier cost-model tests."""

from __future__ import annotations

from tools.plan1126_runtime_audit.cost import compute_cost


def test_computed_cost_includes_cancellation_queue_sink_and_close_multipliers() -> None:
    cost = compute_cost(
        cancellation_points=2,
        queues=3,
        sinks=4,
        close_paths=5,
        seed_count=256,
        admission_probe_count=10_000,
        sink_failure_count=100,
        scenario_durations_ms={"delivery": [10.0, 20.0, 30.0, 40.0]},
    )
    assert cost.cancellation_concurrency_levels == (2, 4, 8)
    assert cost.cancellation_schedules == 1536
    assert cost.cancellation_control_schedules == 512
    assert cost.queue_admissions == 30_000
    assert cost.sink_failure_runs == 400
    assert cost.idempotent_close_invocations == 75
    assert cost.scenario_p50_ms == {"delivery": 25.0}
    assert cost.scenario_p95_ms == {"delivery": 40.0}
