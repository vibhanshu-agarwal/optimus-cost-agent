from decimal import Decimal

import pytest

from optimus.telemetry.redis_adapter import RedisTelemetryAdapter, RunMetadata
from optimus.usage.errors import DuplicateGatewayRequestError


class FakeRedis:
    def __init__(self, fail_create_existing: bool = False) -> None:
        self.fail_create_existing = fail_create_existing
        self.commands: list[tuple[object, ...]] = []
        self._created_series: set[str] = set()
        self._hashes: dict[str, dict[str, str]] = {}

    async def execute_command(self, *args: object):
        self.commands.append(args)
        if args[0] == "TS.CREATE":
            key = args[1]
            if self.fail_create_existing or key in self._created_series:
                raise RuntimeError("TSDB: key already exists")
            self._created_series.add(key)
        return "OK"

    async def hset(self, key: str, mapping: dict[str, str]):
        self.commands.append(("HSET", key, mapping))
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


async def test_ensure_series_alters_existing_key():
    client = FakeRedis(fail_create_existing=True)
    adapter = RedisTelemetryAdapter(client=client)

    await adapter.ensure_series("telemetry:run:run-1:metrics:cost_usd")

    assert ("TS.CREATE", "telemetry:run:run-1:metrics:cost_usd", "RETENTION", 2_592_000_000) in client.commands
    assert ("TS.ALTER", "telemetry:run:run-1:metrics:cost_usd", "RETENTION", 2_592_000_000) in client.commands


async def test_record_metric_writes_timeseries_value():
    client = FakeRedis()
    adapter = RedisTelemetryAdapter(client=client)

    await adapter.record_metric(run_id="run-1", metric_name="cost_usd", value="0.003")

    assert ("TS.ADD", "telemetry:run:run-1:metrics:cost_usd", "*", "0.003") in client.commands


async def test_write_run_metadata_sets_hash_and_ttl():
    client = FakeRedis()
    adapter = RedisTelemetryAdapter(client=client)

    await adapter.write_run_metadata(
        RunMetadata(
            run_id="run-1",
            execution_mode="PLAN",
            generation_scope="INLINE_SNIPPET",
            rigor_level="LOW",
            user_approval_id="unauthorized_direct_run",
            assumption_count=2,
        )
    )

    assert (
        "HSET",
        "run:run-1:metadata",
        {
            "execution_mode": "PLAN",
            "generation_scope": "INLINE_SNIPPET",
            "rigor_level": "LOW",
            "user_approval_id": "unauthorized_direct_run",
            "assumption_count": "2",
        },
    ) in client.commands
    assert ("EXPIRE", "run:run-1:metadata", 2_592_000) in client.commands


async def test_record_settled_usage_writes_exact_ts_create_and_ts_add_sequence():
    client = FakeRedis()
    adapter = RedisTelemetryAdapter(client=client)

    await adapter.record_settled_usage(
        run_id="run-1",
        gateway_request_id="gw-1",
        provider="tavily",
        provider_request_id="provider-1",
        billing_units=10,
        cost_usd=Decimal("0.002"),
    )

    assert client.commands == [
        ("HSETNX", "optimus:usage:run-1:claims", "gw-1", client.commands[0][3]),
        (
            "TS.CREATE",
            "optimus:usage:run-1:cost_usd",
            "RETENTION",
            2_592_000_000,
            "LABELS",
            "run_id",
            "run-1",
            "metric",
            "cost_usd",
        ),
        (
            "TS.CREATE",
            "optimus:usage:run-1:billing_units",
            "RETENTION",
            2_592_000_000,
            "LABELS",
            "run_id",
            "run-1",
            "metric",
            "billing_units",
        ),
        ("TS.ADD", "optimus:usage:run-1:cost_usd", "*", "0.002"),
        ("TS.ADD", "optimus:usage:run-1:billing_units", "*", "10"),
    ]


async def test_record_settled_usage_identical_replay_is_a_noop():
    client = FakeRedis()
    adapter = RedisTelemetryAdapter(client=client)
    kwargs = dict(
        run_id="run-1",
        gateway_request_id="gw-1",
        provider="tavily",
        provider_request_id="provider-1",
        billing_units=10,
        cost_usd=Decimal("0.002"),
    )

    await adapter.record_settled_usage(**kwargs)
    await adapter.record_settled_usage(**kwargs)

    assert sum(1 for command in client.commands if command[0] == "TS.ADD") == 2


async def test_record_settled_usage_divergent_duplicate_raises_and_writes_no_second_point():
    client = FakeRedis()
    adapter = RedisTelemetryAdapter(client=client)
    await adapter.record_settled_usage(
        run_id="run-1",
        gateway_request_id="gw-1",
        provider="tavily",
        provider_request_id="provider-1",
        billing_units=10,
        cost_usd=Decimal("0.002"),
    )

    with pytest.raises(DuplicateGatewayRequestError, match="gw-1"):
        await adapter.record_settled_usage(
            run_id="run-1",
            gateway_request_id="gw-1",
            provider="tavily",
            provider_request_id="provider-1",
            billing_units=10,
            cost_usd=Decimal("0.004"),
        )

    assert sum(1 for command in client.commands if command[0] == "TS.ADD") == 2


async def test_record_settled_usage_removes_claim_when_timeseries_write_fails():
    client = FakeRedis()

    class FailingTsAddRedis(FakeRedis):
        async def execute_command(self, *args: object):
            if args[0] == "TS.ADD":
                self.commands.append(args)
                raise RuntimeError("connection reset")
            return await super().execute_command(*args)

    client = FailingTsAddRedis()
    adapter = RedisTelemetryAdapter(client=client)

    with pytest.raises(RuntimeError, match="connection reset"):
        await adapter.record_settled_usage(
            run_id="run-1",
            gateway_request_id="gw-1",
            provider="tavily",
            provider_request_id="provider-1",
            billing_units=10,
            cost_usd=Decimal("0.002"),
        )

    assert ("HDEL", "optimus:usage:run-1:claims", "gw-1") in client.commands
    # A retried attempt after the claim is released must succeed cleanly.
    client2 = FakeRedis()
    adapter2 = RedisTelemetryAdapter(client=client2)
    await adapter2.record_settled_usage(
        run_id="run-1",
        gateway_request_id="gw-1",
        provider="tavily",
        provider_request_id="provider-1",
        billing_units=10,
        cost_usd=Decimal("0.002"),
    )
    assert sum(1 for command in client2.commands if command[0] == "TS.ADD") == 2


async def test_record_settled_usage_reuses_existing_series_for_second_request_in_same_run():
    client = FakeRedis()
    adapter = RedisTelemetryAdapter(client=client)

    await adapter.record_settled_usage(
        run_id="run-1",
        gateway_request_id="gw-1",
        provider="tavily",
        provider_request_id="provider-1",
        billing_units=10,
        cost_usd=Decimal("0.002"),
    )
    await adapter.record_settled_usage(
        run_id="run-1",
        gateway_request_id="gw-2",
        provider="tavily",
        provider_request_id="provider-2",
        billing_units=5,
        cost_usd=Decimal("0.001"),
    )

    assert ("TS.ALTER", "optimus:usage:run-1:cost_usd", "RETENTION", 2_592_000_000) in client.commands
    assert ("TS.ALTER", "optimus:usage:run-1:billing_units", "RETENTION", 2_592_000_000) in client.commands
    assert sum(1 for command in client.commands if command[0] == "TS.ADD") == 4


async def test_record_settled_usage_rejects_missing_run_id():
    client = FakeRedis()
    adapter = RedisTelemetryAdapter(client=client)

    with pytest.raises(ValueError, match="run_id"):
        await adapter.record_settled_usage(
            run_id="",
            gateway_request_id="gw-1",
            provider="tavily",
            provider_request_id="provider-1",
            billing_units=10,
            cost_usd=Decimal("0.002"),
        )
