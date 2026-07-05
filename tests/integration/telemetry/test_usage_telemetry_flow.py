from datetime import UTC, datetime
from decimal import Decimal

from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES, OptimusGatewaySettings
from optimus.gateway.client import GatewayRequest
from optimus.telemetry.events import TelemetryEvent
from optimus.telemetry.jsonl import JsonlTelemetryWriter
from optimus.telemetry.observability import GatewayObservabilityExporter


class FakeTransport:
    def __init__(self) -> None:
        self.requests: list[GatewayRequest] = []

    def post_json(self, request: GatewayRequest):
        self.requests.append(request)
        return {"accepted": True}


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
        response_summary="done",
    )
    writer = JsonlTelemetryWriter(tmp_path / "telemetry.jsonl")
    writer.append(event)
    transport = FakeTransport()
    exporter = GatewayObservabilityExporter(
        settings=OptimusGatewaySettings(gateway_url="https://gateway.optimus.ai", optimus_api_key="opt-test"),
        transport=transport,
    )

    response = exporter.export((event,))

    assert response == {"accepted": True}
    assert (tmp_path / "telemetry.jsonl").read_text(encoding="utf-8").count("\n") == 1
    assert transport.requests[0].payload["events"][0]["cost_usd"] == "0.001"
