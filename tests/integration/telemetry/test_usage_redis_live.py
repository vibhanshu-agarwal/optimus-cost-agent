"""E4: real TimeSeries-capable Redis evidence for provider usage persistence.

Writes two identical provider-usage attempts (same ``gateway_request_id``,
identical accounting facts) plus one divergent attempt (same
``gateway_request_id``, different facts) through the real
``UsageAccountingService`` -> ``RedisTelemetryEventSink`` ->
``RedisTelemetryAdapter`` path, against a live TimeSeries-capable Redis
server, then reads both ``optimus:usage:{run_id}:cost_usd`` and
``optimus:usage:{run_id}:billing_units`` back via ``TS.RANGE``/``TS.INFO``.

No unit fake stands in for Redis here (Plan 11.5 Task 8 binding constraint).
If a live TimeSeries-capable Redis is not reachable, the fixture fails
closed with an explicit missing-dependency message via ``run_preflight``.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from optimus.acp.preflight import PreflightFailure, run_preflight
from optimus.evidence.ledger import EvidenceLedger, EvidenceLedgerEntry
from optimus.gateway.models import GatewayUsage
from optimus.redis.async_bridge import sync_await
from optimus.telemetry.redis_adapter import RETENTION_MS_30_DAYS, RedisTelemetryAdapter
from optimus.telemetry.redis_sink import RedisTelemetryEventSink
from optimus.tools.policy import EvidenceReasonCode, ToolClass, ToolPolicySignal
from optimus.usage.accounting import UsageAccountingService
from optimus.usage.errors import DuplicateGatewayRequestError

pytestmark = pytest.mark.requires_redis

_RUN_ID_PREFIX = "live-usage"


def _gateway_usage(gateway_request_id: str, cost_usd: str, billing_units: int) -> GatewayUsage:
    return GatewayUsage(
        gateway_request_id=gateway_request_id,
        provider="tavily",
        cache_hit=False,
        billing_units=billing_units,
        cost_usd=Decimal(cost_usd),
        service="web.search",
        native_unit="tavily_credits",
    )


def _ts_info_mapping(info: object) -> dict[object, object]:
    if isinstance(info, dict):
        return info
    return {info[index]: info[index + 1] for index in range(0, len(info), 2)}


def _labels_mapping(info: dict[object, object]) -> dict[str, str]:
    raw = info.get("labels", [])
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items()}
    return {str(raw[index]): str(raw[index + 1]) for index in range(0, len(raw), 2)}


@pytest.fixture
def live_usage_redis(redis_key_namespace: str):
    try:
        redis_url = run_preflight(os.environ, require_timeseries=True)
    except PreflightFailure as exc:
        pytest.fail(exc.user_message)

    import redis.asyncio as aioredis

    client = aioredis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
    run_id = f"{_RUN_ID_PREFIX}-{redis_key_namespace}"
    try:
        yield client, run_id
    finally:

        async def _cleanup() -> None:
            async for key in client.scan_iter(match=f"optimus:usage:{run_id}:*"):
                await client.delete(key)
            await client.aclose()

        sync_await(_cleanup())


def test_live_redis_provider_usage_persistence_matches_response_and_ledger(
    live_usage_redis: tuple[object, str],
) -> None:
    client, run_id = live_usage_redis
    adapter = RedisTelemetryAdapter(client=client)
    accounting = UsageAccountingService(event_sink=RedisTelemetryEventSink(adapter))
    occurred_at = datetime(2026, 7, 28, tzinfo=UTC)

    response = _gateway_usage("gw-live-1", "0.0025", 10)
    identical_replay = _gateway_usage("gw-live-1", "0.0025", 10)
    divergent = _gateway_usage("gw-live-1", "0.0099", 999)

    accounting.record_gateway_usage(
        response,
        run_id=run_id,
        session_id="session-live",
        request_id="req-live-1",
        occurred_at=occurred_at,
        service="web.search",
        native_unit="tavily_credits",
    )
    accounting.record_gateway_usage(
        identical_replay,
        run_id=run_id,
        session_id="session-live",
        request_id="req-live-1-replay",
        occurred_at=occurred_at,
        service="web.search",
        native_unit="tavily_credits",
    )
    with pytest.raises(DuplicateGatewayRequestError):
        accounting.record_gateway_usage(
            divergent,
            run_id=run_id,
            session_id="session-live",
            request_id="req-live-1-divergent",
            occurred_at=occurred_at,
            service="web.search",
            native_unit="tavily_credits",
        )

    evidence = EvidenceLedger().record(
        EvidenceLedgerEntry.from_gateway_usage(
            run_id=run_id,
            session_id="session-live",
            reason=EvidenceReasonCode.USER_REQUESTED,
            policy_signal=ToolPolicySignal.USER_REQUESTED_EXTERNAL_FACT.value,
            tool_class=ToolClass.WEB_SEARCH,
            sources=("https://docs.example.com",),
            gateway_usage=response,
            queried_at=occurred_at,
        )
    )

    provider_entry = accounting.provider_ledger.entries_for_run(run_id)[-1]
    evidence_entry = evidence.entries_for_run(run_id)[-1]

    cost_key = f"optimus:usage:{run_id}:cost_usd"
    units_key = f"optimus:usage:{run_id}:billing_units"

    async def _read_back() -> tuple[list[object], list[object], object, object]:
        cost_samples = await client.execute_command("TS.RANGE", cost_key, "-", "+")
        unit_samples = await client.execute_command("TS.RANGE", units_key, "-", "+")
        cost_info = await client.execute_command("TS.INFO", cost_key)
        unit_info = await client.execute_command("TS.INFO", units_key)
        return cost_samples, unit_samples, cost_info, unit_info

    cost_samples, unit_samples, cost_info_raw, unit_info_raw = sync_await(_read_back())

    # Exactly one point per accepted (deduplicated) request: the identical
    # replay is idempotent (no second TS.ADD); the divergent attempt is
    # rejected before any write.
    assert len(cost_samples) == 1
    assert len(unit_samples) == 1

    cost_value = Decimal(str(cost_samples[0][1]))
    unit_value = Decimal(str(unit_samples[0][1]))

    # response / ProviderUsage / EvidenceLedger / TimeSeries USD equality.
    assert response.cost_usd == provider_entry.cost_usd == evidence_entry.cost_usd == cost_value
    # response / ProviderUsage / EvidenceLedger / TimeSeries billing-unit equality.
    assert response.billing_units == provider_entry.billing_units == evidence_entry.billing_units == int(unit_value)

    cost_info = _ts_info_mapping(cost_info_raw)
    unit_info = _ts_info_mapping(unit_info_raw)
    assert int(cost_info["retentionTime"]) == RETENTION_MS_30_DAYS
    assert int(unit_info["retentionTime"]) == RETENTION_MS_30_DAYS

    cost_labels = _labels_mapping(cost_info)
    unit_labels = _labels_mapping(unit_info)
    assert cost_labels == {"run_id": run_id, "metric": "cost_usd"}
    assert unit_labels == {"run_id": run_id, "metric": "billing_units"}
