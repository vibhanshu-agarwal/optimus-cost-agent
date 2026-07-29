"""End-to-end unit coverage of the settled-usage persistence pipeline.

Wires ``UsageAccountingService`` (Task 3's ``event_sink``) directly to a
``RedisTelemetryEventSink`` backed by a real ``RedisTelemetryAdapter`` and an
in-memory Redis fake, and asserts the exact TimeSeries command sequence the
Task 3 brief specifies -- without any live Redis server.
"""

from datetime import UTC, datetime

import pytest

from optimus.telemetry.redis_adapter import RedisTelemetryAdapter
from optimus.telemetry.redis_sink import RedisTelemetryEventSink
from optimus.usage.accounting import UsageAccountingService
from optimus.usage.errors import DuplicateGatewayRequestError
from tests.unit.usage.test_accounting import gateway_usage


class FakeRedis:
    def __init__(self) -> None:
        self.commands: list[tuple[object, ...]] = []
        self._series: set[str] = set()
        self._hashes: dict[str, dict[str, str]] = {}

    async def execute_command(self, *args: object):
        self.commands.append(args)
        name = args[0]
        if name == "TS.CREATE":
            key = args[1]
            if key in self._series:
                raise RuntimeError("TSDB: key already exists")
            self._series.add(key)
            return "OK"
        if name == "TS.ALTER":
            return "OK"
        if name == "TS.ADD":
            return 0
        raise AssertionError(f"unexpected command: {args}")

    async def hset(self, key: str, mapping: dict[str, str]):
        self.commands.append(("HSET", key, mapping))
        self._hashes.setdefault(key, {}).update(mapping)
        return len(mapping)

    async def hsetnx(self, key: str, field: str, value: str):
        self.commands.append(("HSETNX", key, field, value))
        bucket = self._hashes.setdefault(key, {})
        if field in bucket:
            return 0
        bucket[field] = value
        return 1

    async def hget(self, key: str, field: str):
        self.commands.append(("HGET", key, field))
        return self._hashes.get(key, {}).get(field)

    async def hdel(self, key: str, *fields: str):
        self.commands.append(("HDEL", key, *fields))
        bucket = self._hashes.get(key, {})
        removed = 0
        for field in fields:
            if bucket.pop(field, None) is not None:
                removed += 1
        return removed

    async def expire(self, key: str, ttl_seconds: int):
        self.commands.append(("EXPIRE", key, ttl_seconds))
        return True


def _sink() -> tuple[FakeRedis, UsageAccountingService]:
    redis = FakeRedis()
    adapter = RedisTelemetryAdapter(client=redis)
    accounting = UsageAccountingService(event_sink=RedisTelemetryEventSink(adapter))
    return redis, accounting


def test_first_settled_usage_writes_exact_ts_create_and_ts_add_sequence():
    redis, accounting = _sink()

    accounting.record_gateway_usage(
        gateway_usage("gw-1", "0.002", 10),
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 28, tzinfo=UTC),
        service="web.search",
        native_unit="tavily_credits",
    )

    assert (
        "TS.CREATE",
        "optimus:usage:run-1:cost_usd",
        "RETENTION",
        2_592_000_000,
        "LABELS",
        "run_id",
        "run-1",
        "metric",
        "cost_usd",
    ) in redis.commands
    assert (
        "TS.CREATE",
        "optimus:usage:run-1:billing_units",
        "RETENTION",
        2_592_000_000,
        "LABELS",
        "run_id",
        "run-1",
        "metric",
        "billing_units",
    ) in redis.commands
    assert ("TS.ADD", "optimus:usage:run-1:cost_usd", "*", "0.002") in redis.commands
    assert ("TS.ADD", "optimus:usage:run-1:billing_units", "*", "10") in redis.commands


def test_identical_replay_writes_no_second_ts_add():
    redis, accounting = _sink()
    usage = gateway_usage("gw-1", "0.002", 10)
    common = dict(
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 28, tzinfo=UTC),
        service="web.search",
        native_unit="tavily_credits",
    )

    accounting.record_gateway_usage(usage, **common)
    ts_add_count_after_first = sum(1 for command in redis.commands if command[0] == "TS.ADD")

    accounting.record_gateway_usage(usage, **common)
    ts_add_count_after_second = sum(1 for command in redis.commands if command[0] == "TS.ADD")

    assert ts_add_count_after_first == 2
    assert ts_add_count_after_second == 2


def test_divergent_duplicate_raises_and_writes_no_second_point():
    redis, accounting = _sink()
    common = dict(
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 28, tzinfo=UTC),
        service="web.search",
        native_unit="tavily_credits",
    )
    accounting.record_gateway_usage(gateway_usage("gw-1", "0.002", 10), **common)

    with pytest.raises(DuplicateGatewayRequestError):
        accounting.record_gateway_usage(gateway_usage("gw-1", "0.004", 10), **common)

    assert sum(1 for command in redis.commands if command[0] == "TS.ADD") == 2
