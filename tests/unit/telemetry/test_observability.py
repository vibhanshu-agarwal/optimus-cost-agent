from datetime import UTC, datetime
from decimal import Decimal

from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES, OptimusGatewaySettings
from optimus.gateway.client import GatewayRequest
from optimus.telemetry.events import TelemetryEvent
from optimus.telemetry.observability import GatewayObservabilityExporter


class FakeTransport:
    def __init__(self) -> None:
        self.requests: list[GatewayRequest] = []

    def post_json(self, request: GatewayRequest):
        self.requests.append(request)
        return {"accepted": True, "trace_batch_id": "trace-batch-1"}


def test_observability_export_posts_to_gateway_trace_endpoint(monkeypatch):
    for key in LOCAL_PROVIDER_KEY_NAMES:
        monkeypatch.delenv(key, raising=False)
    transport = FakeTransport()
    settings = OptimusGatewaySettings(gateway_url="https://gateway.optimus.ai", optimus_api_key="opt-test")
    exporter = GatewayObservabilityExporter(settings=settings, transport=transport)
    event = TelemetryEvent.model_call(
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        model="glm-5.2",
        model_version="2026-06-01",
        provider="glm",
        cache_hit=False,
        billing_units=10,
        cost_usd=Decimal("0.001"),
        latency_ms=20,
        prompt="hello",
        response_summary="done",
    )

    response = exporter.export((event,))

    assert response == {"accepted": True, "trace_batch_id": "trace-batch-1"}
    assert transport.requests[0].url == "https://gateway.optimus.ai/v1/observability/traces"
    assert transport.requests[0].payload["events"][0]["run_id"] == "run-1"


def test_observability_export_does_not_require_local_provider_keys(monkeypatch):
    for key in LOCAL_PROVIDER_KEY_NAMES:
        monkeypatch.delenv(key, raising=False)
    transport = FakeTransport()
    settings = OptimusGatewaySettings(gateway_url="https://gateway.optimus.ai", optimus_api_key="opt-test")
    exporter = GatewayObservabilityExporter(settings=settings, transport=transport)

    response = exporter.export(())

    assert response == {"accepted": True, "trace_batch_id": "trace-batch-1"}
