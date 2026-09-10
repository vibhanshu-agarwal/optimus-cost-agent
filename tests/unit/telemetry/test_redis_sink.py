import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

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


class _Submissions:
    """An injected submission seam that runs each operation factory itself."""

    def __init__(self) -> None:
        self.count = 0

    def __call__(self, operation):
        self.count += 1
        return asyncio.run(operation())


def _sink(adapter: FakeRedisTelemetryAdapter) -> tuple[RedisTelemetryEventSink, _Submissions]:
    submissions = _Submissions()
    return RedisTelemetryEventSink(adapter, submit=submissions), submissions


def _agent_run_event(run_id: str) -> TelemetryEvent:
    return TelemetryEvent.agent_run(
        run_id=run_id,
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


def test_redis_telemetry_sink_requires_an_injected_submission_seam():
    """MUTATION: a serving sink that silently falls back to the shared tool owner."""
    with pytest.raises(TypeError, match="submit"):
        RedisTelemetryEventSink(FakeRedisTelemetryAdapter())


def test_redis_telemetry_sink_records_agent_run_cost_and_metadata():
    adapter = FakeRedisTelemetryAdapter()
    sink, submissions = _sink(adapter)
    sink(_agent_run_event("run-1"))

    assert ("run-1", "cost_usd", "0.003") in adapter.metrics
    assert len(adapter.metadata) == 1
    assert adapter.metadata[0].run_id == "run-1"
    assert adapter.metadata[0].execution_mode == "AGENT"
    assert submissions.count == 1


def test_redis_telemetry_sink_persists_gateway_usage_as_settled_usage():
    adapter = FakeRedisTelemetryAdapter()
    sink, submissions = _sink(adapter)
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
    assert submissions.count == 1


def test_a_runtime_bound_sink_runs_on_the_runtime_owner_and_never_the_shared_one():
    """MUTATION: a second loop owner touching the runtime's client."""
    import threading

    from optimus.redis import async_bridge
    from optimus.redis.async_bridge import RedisLoopOwner
    from optimus.redis.runtime import RedisRuntime

    threads: list[int] = []

    class _Client:
        async def execute_command(self, *args):
            threads.append(threading.get_ident())
            return 1

        async def hset(self, key, mapping):
            threads.append(threading.get_ident())
            return 1

        async def expire(self, key, ttl):
            return True

        async def aclose(self):
            return None

    class _Pool:
        async def aclose(self):
            return None

    owner = RedisLoopOwner(name="seam2b-sink-owner")
    runtime = RedisRuntime(pool=_Pool(), client=_Client(), owner=owner)
    try:
        sink = runtime.telemetry_sink()
        sink(_agent_run_event("run-2"))
    finally:
        runtime.close(timeout=5.0)
    assert threads and set(threads) == {owner.thread.ident}
    assert async_bridge._shared_tool_owner is None, "a serving sink reached the shared tool owner"


def test_a_late_event_after_close_receives_a_stable_closed_error():
    from optimus.redis.async_bridge import RedisLoopOwner, RedisLoopOwnerClosed
    from optimus.redis.runtime import RedisRuntime

    class _Client:
        async def execute_command(self, *args):  # pragma: no cover - must never run
            raise AssertionError("a closed runtime accepted telemetry")

        async def aclose(self):
            return None

    class _Pool:
        async def aclose(self):
            return None

    owner = RedisLoopOwner(name="seam2b-late-sink-owner")
    runtime = RedisRuntime(pool=_Pool(), client=_Client(), owner=owner)
    sink = runtime.telemetry_sink()
    runtime.close(timeout=5.0)
    with pytest.raises(RedisLoopOwnerClosed):
        sink(_agent_run_event("run-3"))
    assert runtime.owner is owner and owner.is_terminated
