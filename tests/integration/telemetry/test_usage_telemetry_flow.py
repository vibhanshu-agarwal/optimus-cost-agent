from datetime import UTC, datetime
from decimal import Decimal

from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES
from optimus.gateway.client import GatewayRequest
from optimus.gateway.models import GatewayUsage
from optimus.telemetry.events import TelemetryEvent
from optimus.telemetry.jsonl import JsonlTelemetryWriter
from optimus.telemetry.observability import GatewayObservabilityExporter
from optimus.telemetry.redis_adapter import RedisTelemetryAdapter
from optimus.telemetry.redis_sink import RedisTelemetryEventSink
from optimus.usage.accounting import UsageAccountingService
from tests.support.gateway_settings import gateway_settings


class FakeTransport:
    def __init__(self) -> None:
        self.requests: list[GatewayRequest] = []

    def post_json(self, request: GatewayRequest):
        self.requests.append(request)
        return {"accepted": True}


class FakeRedis:
    def __init__(self) -> None:
        self.commands: list[tuple[object, ...]] = []
        self._series: set[str] = set()
        self._hashes: dict[str, dict[str, str]] = {}

    async def execute_command(self, *args: object):
        self.commands.append(args)
        if args[0] == "TS.CREATE":
            key = args[1]
            if key in self._series:
                raise RuntimeError("TSDB: key already exists")
            self._series.add(key)
        return "OK"

    async def hset(self, key: str, mapping: dict[str, str]):
        self.commands.append(("HSET", key, mapping))
        return len(mapping)

    async def hsetnx(self, key: str, field: str, value: str):
        bucket = self._hashes.setdefault(key, {})
        if field in bucket:
            return 0
        bucket[field] = value
        return 1

    async def hget(self, key: str, field: str):
        return self._hashes.get(key, {}).get(field)

    async def hdel(self, key: str, *fields: str):
        bucket = self._hashes.get(key, {})
        return sum(1 for field in fields if bucket.pop(field, None) is not None)

    async def expire(self, key: str, ttl_seconds: int):
        self.commands.append(("EXPIRE", key, ttl_seconds))
        return True


def test_usage_event_is_written_to_jsonl_and_exported_to_gateway(tmp_path, monkeypatch):
    for key in LOCAL_PROVIDER_KEY_NAMES:
        monkeypatch.delenv(key, raising=False)
    event = TelemetryEvent.model_call(
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        model="glm-5.2",
        model_version="2026-06-01",
        provider="glm",
        cache_hit=True,
        billing_units=10,
        cost_usd=Decimal("0.001"),
        latency_ms=30,
        prompt="hello",
        response="done",
        input_tokens=3,
        output_tokens=2,
    )
    writer = JsonlTelemetryWriter(tmp_path / "telemetry.jsonl")
    writer.append(event)
    transport = FakeTransport()
    exporter = GatewayObservabilityExporter(
        settings=gateway_settings(),
        transport=transport,
    )

    response = exporter.export((event,))

    assert response == {"accepted": True}
    assert (tmp_path / "telemetry.jsonl").read_text(encoding="utf-8").count("\n") == 1
    assert transport.requests[0].payload["events"][0]["cost_usd"] == "0.001"


def test_gateway_usage_event_flows_to_jsonl_redis_and_gateway_export(tmp_path, monkeypatch):
    for key in LOCAL_PROVIDER_KEY_NAMES:
        monkeypatch.delenv(key, raising=False)
    writer = JsonlTelemetryWriter(tmp_path / "telemetry.jsonl")
    fake_redis = FakeRedis()
    redis_sink = RedisTelemetryEventSink(RedisTelemetryAdapter(client=fake_redis))
    captured: list[TelemetryEvent] = []

    def fan_out(event: TelemetryEvent) -> None:
        captured.append(event)
        writer.append(event)
        redis_sink(event)

    accounting = UsageAccountingService(event_sink=fan_out)

    accounting.record_gateway_usage(
        GatewayUsage(
            gateway_request_id="gw-1",
            provider="tavily",
            cache_hit=False,
            billing_units=10,
            cost_usd=Decimal("0.002"),
        ),
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 28, tzinfo=UTC),
        service="web.search",
        native_unit="tavily_credits",
    )

    jsonl_lines = (tmp_path / "telemetry.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(jsonl_lines) == 1
    assert '"kind":"gateway_usage"' in jsonl_lines[0]

    assert ("TS.ADD", "optimus:usage:run-1:cost_usd", "*", "0.002") in fake_redis.commands
    assert ("TS.ADD", "optimus:usage:run-1:billing_units", "*", "10") in fake_redis.commands

    transport = FakeTransport()
    exporter = GatewayObservabilityExporter(settings=gateway_settings(), transport=transport)
    response = exporter.export(tuple(captured))

    assert response == {"accepted": True}
    assert transport.requests[0].payload["events"][0]["kind"] == "gateway_usage"
    assert transport.requests[0].payload["events"][0]["cost_usd"] == "0.002"
