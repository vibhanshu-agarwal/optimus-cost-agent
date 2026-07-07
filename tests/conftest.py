from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from decimal import Decimal

import pytest

from optimus.acp.preflight import PreflightFailure, run_preflight
from optimus.agent.state_store import RedisAgentStateStore
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.telemetry.redis_adapter import RedisTelemetryAdapter


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
    store = RedisAgentStateStore.from_url(redis_url)
    yield store, redis_key_namespace
    client = store._client
    for key in client.scan_iter(match=f"agent:plan:{redis_key_namespace}*"):
        client.delete(key)


@pytest.fixture
async def live_redis_telemetry(redis_key_namespace: str):
    try:
        redis_url = run_preflight(os.environ, require_timeseries=True)
    except PreflightFailure as exc:
        pytest.fail(exc.user_message)

    import redis.asyncio as aioredis

    client = aioredis.from_url(redis_url, decode_responses=True)
    adapter = RedisTelemetryAdapter(client=client)
    run_id = redis_key_namespace
    yield adapter, run_id, client
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
