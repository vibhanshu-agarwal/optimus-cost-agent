from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from decimal import Decimal

import pytest

from optimus.acp.debug_trace import reset_debug_trace_context
from optimus.acp.preflight import PreflightFailure, run_preflight
from optimus.agent.state_store import RedisAgentStateStore
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.redis.async_bridge import shutdown_background_loop
from optimus.redis.runtime import RedisRuntime
from optimus.telemetry.redis_adapter import RedisTelemetryAdapter


@pytest.fixture(scope="session", autouse=True)
def _shutdown_redis_bridge_after_session() -> None:
    yield
    shutdown_background_loop()


@pytest.fixture(autouse=True)
def _reset_debug_trace_context_between_tests() -> Iterator[None]:
    """Plan 9.96, Task 5: DebugTraceContext is process-local module state (it
    replaced os.environ mutation, which pytest's monkeypatch used to undo
    automatically). Without this reset, a context set by one test would leak
    into every subsequent test in the same process."""
    reset_debug_trace_context()
    yield
    reset_debug_trace_context()


@pytest.fixture
def redis_key_namespace() -> Iterator[str]:
    run_id = f"live-{uuid.uuid4().hex}"
    yield run_id


@pytest.fixture
def live_redis_store(redis_key_namespace: str) -> Iterator[tuple[RedisAgentStateStore, str]]:
    try:
        redis_url = run_preflight(os.environ, require_timeseries=True)
    except PreflightFailure as exc:
        pytest.fail(exc.user_message)
    runtime = RedisRuntime.from_url(redis_url)
    store = runtime.sync_state_store()
    try:
        yield store, redis_key_namespace
    finally:
        runtime.close()


@pytest.fixture
async def live_redis_telemetry(redis_key_namespace: str):
    try:
        redis_url = run_preflight(os.environ, require_timeseries=True)
    except PreflightFailure as exc:
        pytest.fail(exc.user_message)

    import redis.asyncio as aioredis

    client = aioredis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
    adapter = RedisTelemetryAdapter(client=client)
    run_id = redis_key_namespace
    try:
        yield adapter, run_id, client
    finally:
        for pattern in (f"telemetry:run:{run_id}*", f"run:{run_id}:*"):
            async for key in client.scan_iter(match=pattern):
                await client.delete(key)
        await client.aclose()


class FakeGatewayClient:
    def __init__(self, output_text: str = "Plan text") -> None:
        self.calls: list[dict[str, object]] = []
        self.output_text = output_text

    def create_response(self, *, model: str, input_text: str, metadata=None) -> GatewayResponse:
        self.calls.append({"model": model, "input_text": input_text, "metadata": metadata})
        return GatewayResponse(
            response_id="resp-1",
            output_text=self.output_text,
            gateway_usage=GatewayUsage(
                gateway_request_id="gw-1",
                provider="glm",
                billing_units=5,
                cost_usd=Decimal("0.002"),
            ),
            raw={"id": "resp-1"},
        )
