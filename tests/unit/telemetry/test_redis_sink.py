from datetime import UTC, datetime
from decimal import Decimal

from optimus.telemetry.events import TelemetryEvent
from optimus.telemetry.redis_sink import RedisTelemetryEventSink


class FakeRedisTelemetryAdapter:
    def __init__(self) -> None:
        self.metrics: list[tuple[str, str, str]] = []
        self.metadata: list[object] = []
        self.settled_usage: list[dict[str, object]] = []

    async def record_metric(self, *, run_id: str, metric_name: str, value: str) -> None:
        self.metrics.append((run_id, metric_name, value))

    async def write_run_metadata(self, metadata: object) -> None:
        self.metadata.append(metadata)

    async def record_settled_usage(
        self,
        *,
        run_id: str,
        gateway_request_id: str,
        provider: str,
        provider_request_id: str | None,
        billing_units: int,
        cost_usd: Decimal,
    ) -> None:
        self.settled_usage.append(
            {
                "run_id": run_id,
                "gateway_request_id": gateway_request_id,
                "provider": provider,
                "provider_request_id": provider_request_id,
                "billing_units": billing_units,
                "cost_usd": cost_usd,
            }
        )


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


def test_redis_telemetry_sink_persists_gateway_usage_as_settled_usage():
    adapter = FakeRedisTelemetryAdapter()
    sink = RedisTelemetryEventSink(adapter)
    sink(
        TelemetryEvent.gateway_usage(
            run_id="run-1",
            session_id="session-1",
            request_id="req-1",
            occurred_at=datetime(2026, 7, 28, tzinfo=UTC),
            gateway_request_id="gw-1",
            provider="tavily",
            provider_request_id="provider-1",
            cache_hit=False,
            billing_units=10,
            cost_usd=Decimal("0.002"),
            service="web.search",
            native_unit="tavily_credits",
            model=None,
            model_version=None,
        )
    )

    assert adapter.settled_usage == [
        {
            "run_id": "run-1",
            "gateway_request_id": "gw-1",
            "provider": "tavily",
            "provider_request_id": "provider-1",
            "billing_units": 10,
            "cost_usd": Decimal("0.002"),
        }
    ]
