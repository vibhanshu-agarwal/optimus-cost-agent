from optimus.telemetry.redis_adapter import RedisTelemetryAdapter, RunMetadata


class FakeRedis:
    def __init__(self, fail_create_existing: bool = False) -> None:
        self.fail_create_existing = fail_create_existing
        self.commands: list[tuple[object, ...]] = []

    async def execute_command(self, *args: object):
        self.commands.append(args)
        if self.fail_create_existing and args[0] == "TS.CREATE":
            raise RuntimeError("TSDB: key already exists")
        return "OK"

    async def hset(self, key: str, mapping: dict[str, str]):
        self.commands.append(("HSET", key, mapping))
        return len(mapping)

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
