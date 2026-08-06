"""Plan 11.8 live MCP accounting evidence against real Redis + RedisTimeSeries."""

from __future__ import annotations

import os
import uuid
from decimal import Decimal
from typing import Iterator

import pytest
import redis

from optimus_gateway.mcp_usage import (
    MCPUsageConflictError,
    MCPUsageRecord,
    RedisMCPUsageWriter,
)

pytestmark = pytest.mark.requires_redis


def _live_redis_url() -> str:
    value = os.environ.get("OPTIMUS_REDIS_URL", "").strip()
    if not value:
        pytest.fail("OPTIMUS_REDIS_URL is required for the real Redis MCP accounting tier")
    return value


@pytest.fixture
def live_mcp_usage_store() -> Iterator[tuple[RedisMCPUsageWriter, redis.Redis, list[str]]]:
    client = redis.Redis.from_url(
        _live_redis_url(),
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    try:
        client.ping()
        probe_key = f"optimus:plan118:mcp:timeseries:{uuid.uuid4().hex}"
        client.execute_command("TS.ADD", probe_key, "*", 1)
        client.delete(probe_key)
    except Exception as exc:  # noqa: BLE001 - live tier must fail loudly with dependency detail
        client.close()
        pytest.fail(f"real Redis must provide connectivity and TimeSeries support: {type(exc).__name__}")

    writer = RedisMCPUsageWriter(client=client, retention_seconds=3600)
    keys: list[str] = []
    try:
        yield writer, client, keys
    finally:
        if keys:
            client.delete(*keys)
        client.close()


def _record(*, gateway_request_id: str, attribution: str = "settled") -> MCPUsageRecord:
    monetary = {
        "billing_units": 3,
        "cost_usd": Decimal("0.0125"),
    }
    if attribution == "explicit_zero":
        monetary = {"billing_units": 0, "cost_usd": Decimal("0")}
    elif attribution == "unavailable":
        monetary = {"billing_units": None, "cost_usd": None}
    return MCPUsageRecord(
        gateway_request_id=gateway_request_id,
        run_id="plan118-redis-run",
        session_id="plan118-redis-session",
        request_id=f"request-{gateway_request_id}",
        profile_id="plan118-http",
        profile_revision="rev-http-live-1",
        namespaced_tool_name="plan118-http.echo",
        upstream_tool_name="echo",
        transport="http",
        disposition="mcp.call.complete",
        attribution=attribution,  # type: ignore[arg-type]
        duration_ms=12,
        request_bytes=128,
        response_bytes=256,
        provider_request_id=None,
        **monetary,
    )


def test_live_redis_mcp_usage_is_idempotent_and_retained(live_mcp_usage_store) -> None:
    writer, client, keys = live_mcp_usage_store
    gateway_request_id = f"gw-plan118-redis-{uuid.uuid4().hex}"
    record = _record(gateway_request_id=gateway_request_id)
    keys.append(f"gateway:mcp:usage:{gateway_request_id}")

    writer.persist(record)
    writer.persist(record.model_copy())

    assert writer.record_for(gateway_request_id) == record
    assert client.ttl(keys[0]) > 0
    with pytest.raises(MCPUsageConflictError):
        writer.persist(record.model_copy(update={"cost_usd": Decimal("0.99")}))


@pytest.mark.parametrize("attribution", ["explicit_zero", "unavailable"])
def test_live_redis_preserves_non_settled_attribution_without_zero_coercion(
    live_mcp_usage_store, attribution: str
) -> None:
    writer, _client, keys = live_mcp_usage_store
    gateway_request_id = f"gw-plan118-{attribution}-{uuid.uuid4().hex}"
    keys.append(f"gateway:mcp:usage:{gateway_request_id}")
    record = _record(gateway_request_id=gateway_request_id, attribution=attribution)

    writer.persist(record)
    loaded = writer.record_for(gateway_request_id)

    assert loaded == record
    if attribution == "unavailable":
        assert loaded is not None
        assert loaded.billing_units is None
        assert loaded.cost_usd is None
    else:
        assert loaded is not None
        assert loaded.billing_units == 0
        assert loaded.cost_usd == Decimal("0")
