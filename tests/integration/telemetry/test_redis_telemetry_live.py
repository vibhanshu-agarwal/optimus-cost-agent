from __future__ import annotations

from decimal import Decimal

import pytest

from optimus.telemetry.redis_adapter import RETENTION_MS_30_DAYS, RETENTION_SECONDS_30_DAYS, RunMetadata

pytestmark = pytest.mark.requires_redis

_METADATA_TTL_TOLERANCE_SECONDS = 5


def _ts_info_mapping(info: list[object]) -> dict[object, object]:
    return {info[index]: info[index + 1] for index in range(0, len(info), 2)}


def _retention_time_ms(info: list[object]) -> int:
    return int(_ts_info_mapping(info)["retentionTime"])


async def _telemetry_keys(client: object, run_id: str) -> set[str]:
    keys: set[str] = set()
    for pattern in (f"telemetry:run:{run_id}*", f"run:{run_id}:*"):
        async for key in client.scan_iter(match=pattern):
            keys.add(key)
    return keys


async def test_live_ensure_series_sets_retention_on_new_and_existing_keys(live_redis_telemetry):
    adapter, run_id, client = live_redis_telemetry
    new_key = f"telemetry:run:{run_id}:metrics:cost_usd"
    existing_key = f"telemetry:run:{run_id}:metrics:tokens_input"

    await client.execute_command("TS.CREATE", existing_key, "RETENTION", 1_000)

    await adapter.ensure_series(new_key)
    await adapter.ensure_series(existing_key)
    await adapter.ensure_series(new_key)

    assert _retention_time_ms(await client.execute_command("TS.INFO", new_key)) == RETENTION_MS_30_DAYS
    assert _retention_time_ms(await client.execute_command("TS.INFO", existing_key)) == RETENTION_MS_30_DAYS


async def test_live_record_metric_writes_samples_readable_via_ts_range(live_redis_telemetry):
    adapter, run_id, client = live_redis_telemetry
    metrics = {
        "cost_usd": "0.003",
        "tokens_input": "10",
        "tokens_output": "5",
    }

    for metric_name, value in metrics.items():
        await adapter.record_metric(run_id=run_id, metric_name=metric_name, value=value)

    for metric_name, expected in metrics.items():
        key = f"telemetry:run:{run_id}:metrics:{metric_name}"
        samples = await client.execute_command("TS.RANGE", key, "-", "+")
        assert samples
        assert Decimal(samples[-1][1]) == Decimal(expected)


async def test_live_write_run_metadata_sets_hash_fields_and_ttl(live_redis_telemetry):
    adapter, run_id, client = live_redis_telemetry
    metadata = RunMetadata(
        run_id=run_id,
        execution_mode="PLAN",
        generation_scope="INLINE_SNIPPET",
        rigor_level="LOW",
        user_approval_id="approval-live-telemetry",
        assumption_count=2,
    )

    await adapter.write_run_metadata(metadata)

    key = f"run:{run_id}:metadata"
    stored = await client.hgetall(key)
    assert stored == {
        "execution_mode": "PLAN",
        "generation_scope": "INLINE_SNIPPET",
        "rigor_level": "LOW",
        "user_approval_id": "approval-live-telemetry",
        "assumption_count": "2",
    }
    ttl = await client.ttl(key)
    assert RETENTION_SECONDS_30_DAYS - _METADATA_TTL_TOLERANCE_SECONDS <= ttl <= RETENTION_SECONDS_30_DAYS


async def test_live_telemetry_keys_are_namespaced_and_teardown_clears_them(live_redis_telemetry):
    adapter, run_id, client = live_redis_telemetry

    await adapter.record_metric(run_id=run_id, metric_name="cost_usd", value="0.001")
    await adapter.write_run_metadata(
        RunMetadata(
            run_id=run_id,
            execution_mode="AGENT",
            generation_scope="FILE_MUTATION",
            rigor_level="HIGH",
            user_approval_id="approval-keys",
            assumption_count=0,
        )
    )

    keys = await _telemetry_keys(client, run_id)
    assert keys
    assert all(key.startswith(f"telemetry:run:{run_id}") or key.startswith(f"run:{run_id}:") for key in keys)

    for pattern in (f"telemetry:run:{run_id}*", f"run:{run_id}:*"):
        async for key in client.scan_iter(match=pattern):
            await client.delete(key)

    assert await _telemetry_keys(client, run_id) == set()
