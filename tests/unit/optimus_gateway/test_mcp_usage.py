from __future__ import annotations

from decimal import Decimal

import pytest
import redis

from optimus_gateway.mcp_usage import (
    InMemoryMCPUsageWriter,
    MCPUsageConflictError,
    MCPUsagePersistenceError,
    MCPUsageRecord,
    MCPUsageUnavailableError,
    RedisMCPUsageWriter,
)


def _record(**overrides: object) -> MCPUsageRecord:
    values: dict[str, object] = {
        "gateway_request_id": "gw-mcp-1",
        "run_id": "run-1",
        "session_id": "session-1",
        "request_id": "request-1",
        "profile_id": "context7",
        "profile_revision": "rev-1",
        "namespaced_tool_name": "context7.search",
        "upstream_tool_name": "search",
        "transport": "http",
        "disposition": "mcp.call.complete",
        "attribution": "settled",
        "duration_ms": 12,
        "request_bytes": 128,
        "response_bytes": 256,
        "provider_request_id": "upstream-1",
        "billing_units": 4,
        "cost_usd": Decimal("0.02"),
    }
    values.update(overrides)
    return MCPUsageRecord(**values)


@pytest.mark.parametrize(
    "attribution,fields",
    (
        ("settled", {"billing_units": 4, "cost_usd": Decimal("0.02")}),
        ("explicit_zero", {"billing_units": 0, "cost_usd": Decimal("0")}),
        ("unavailable", {"billing_units": None, "cost_usd": None}),
    ),
)
def test_usage_record_preserves_each_attribution_state(attribution: str, fields: dict[str, object]):
    record = _record(attribution=attribution, **fields)

    assert record.attribution == attribution
    assert record.model_dump(mode="json")["cost_usd"] == (
        None if fields["cost_usd"] is None else str(fields["cost_usd"])
    )


@pytest.mark.parametrize(
    "overrides",
    (
        {"attribution": "settled", "billing_units": None, "cost_usd": Decimal("0.02")},
        {"attribution": "explicit_zero", "billing_units": 1, "cost_usd": Decimal("0.01")},
        {"attribution": "unavailable", "billing_units": 0, "cost_usd": Decimal("0")},
        {"duration_ms": -1},
        {"request_bytes": -1},
        {"response_bytes": -1},
    ),
)
def test_usage_record_rejects_invalid_attribution_or_measurement(overrides: dict[str, object]):
    with pytest.raises(ValueError):
        _record(**overrides)


def test_in_memory_writer_accepts_identical_replay_and_rejects_divergent_same_id():
    writer = InMemoryMCPUsageWriter()
    record = _record()

    writer.persist(record)
    writer.persist(record.model_copy())

    with pytest.raises(MCPUsageConflictError):
        writer.persist(record.model_copy(update={"cost_usd": Decimal("0.03")}))

    assert writer.record_for(record.gateway_request_id) == record


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    def set(self, key: str, value: str, *, nx: bool, ex: int) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        self.expirations[key] = ex
        return True

    def get(self, key: str) -> str | None:
        return self.values.get(key)


def test_redis_writer_uses_direct_ttl_bound_idempotent_key_value_storage():
    client = _FakeRedis()
    writer = RedisMCPUsageWriter(client=client, retention_seconds=86400)
    record = _record()

    writer.persist(record)
    writer.persist(record.model_copy())

    key = "gateway:mcp:usage:gw-mcp-1"
    assert client.expirations[key] == 86400
    assert writer.record_for("gw-mcp-1") == record


class _FailingRedis:
    def set(self, *args: object, **kwargs: object) -> bool:
        raise redis.exceptions.ConnectionError("redis unavailable")

    def get(self, *args: object, **kwargs: object) -> None:
        raise redis.exceptions.ConnectionError("redis unavailable")


def test_redis_writer_exposes_typed_unavailable_failure_without_memory_fallback():
    writer = RedisMCPUsageWriter(client=_FailingRedis())

    with pytest.raises(MCPUsageUnavailableError):
        writer.persist(_record())
    assert not hasattr(writer, "_records")


def test_persistence_error_is_distinct_from_record_validation():
    assert issubclass(MCPUsageUnavailableError, MCPUsagePersistenceError)
