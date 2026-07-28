from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES
from optimus.gateway.client import GatewayRequest
from optimus.telemetry.events import TelemetryEvent
from optimus.telemetry.observability import GatewayObservabilityExporter, TraceBatch
from tests.support.gateway_settings import LOOPBACK_GATEWAY_URL, gateway_settings


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
    settings = gateway_settings()
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
        response="done",
        input_tokens=3,
        output_tokens=2,
    )

    response = exporter.export((event,))

    assert response == {"accepted": True, "trace_batch_id": "trace-batch-1"}
    assert transport.requests[0].url == f"{LOOPBACK_GATEWAY_URL}/v1/observability/traces"
    assert transport.requests[0].payload["events"][0]["run_id"] == "run-1"


def test_observability_export_does_not_require_local_provider_keys(monkeypatch):
    for key in LOCAL_PROVIDER_KEY_NAMES:
        monkeypatch.delenv(key, raising=False)
    transport = FakeTransport()
    settings = gateway_settings()
    exporter = GatewayObservabilityExporter(settings=settings, transport=transport)

    response = exporter.export(())

    assert response == {"accepted": True, "trace_batch_id": "trace-batch-1"}


def _event_payload(*, event_id: str, trace_id: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "event_id": event_id,
        "trace_id": trace_id,
        "parent_span_id": None,
        "kind": "model_call",
        "run_id": "run-1",
        "session_id": "session-1",
        "request_id": "req-1",
        "occurred_at": "2026-07-28T00:00:00+00:00",
        "gateway_request_id": "gw-1",
        "provider": "openrouter",
        "model": "glm-5.2",
        "billing_units": 3,
        "cost_usd": "0.001",
    }


def test_trace_batch_rejects_missing_identity_and_accepts_unknown_top_level():
    event = _event_payload(event_id="event-1", trace_id="trace-1")
    batch = TraceBatch.model_validate({
        "schema_version": "1.0",
        "batch_id": "batch-1",
        "events": [event],
        "future_hint": {"enabled": True},
    })
    assert batch.batch_id == "batch-1"
    with pytest.raises(ValidationError, match="event_id"):
        TraceBatch.model_validate({"schema_version": "1.0", "batch_id": "batch-1", "events": [{"kind": "model_call"}]})
