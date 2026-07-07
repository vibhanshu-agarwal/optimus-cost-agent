from datetime import UTC, datetime
from decimal import Decimal

from optimus.telemetry.events import TelemetryEvent
from optimus.telemetry.redis_sink import RedisTelemetryEventSink


class FakeRedisTelemetryAdapter:
    def __init__(self) -> None:
        self.metrics: list[tuple[str, str, str]] = []
        self.metadata: list[object] = []

    async def record_metric(self, *, run_id: str, metric_name: str, value: str) -> None:
        self.metrics.append((run_id, metric_name, value))

    async def write_run_metadata(self, metadata: object) -> None:
        self.metadata.append(metadata)


def test_redis_telemetry_sink_records_agent_run_cost_and_metadata():
    adapter = FakeRedisTelemetryAdapter()
    sink = RedisTelemetryEventSink(adapter)
    sink(
        TelemetryEvent.agent_run(
            run_id="run-1",
            session_id="session-1",
            request_id="req-1",
            occurred_at=datetime(2026, 7, 7, tzinfo=UTC),
            status="completed",
            final_state="COMPLETED",
            tool_names=("file_writer",),
            total_cost_usd=Decimal("0.003"),
            mutation_count=1,
            stop_reason=None,
            execution_mode="AGENT",
            user_approval_id="approval-1",
        )
    )

    assert ("run-1", "cost_usd", "0.003") in adapter.metrics
    assert len(adapter.metadata) == 1
    assert adapter.metadata[0].run_id == "run-1"
    assert adapter.metadata[0].execution_mode == "AGENT"
