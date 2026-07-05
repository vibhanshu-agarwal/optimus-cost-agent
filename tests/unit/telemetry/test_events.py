from datetime import UTC, datetime
from decimal import Decimal

from optimus.telemetry.events import TelemetryEvent, TelemetryEventKind


def test_model_call_event_contains_required_usage_fields():
    event = TelemetryEvent.model_call(
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        model="glm-5.2",
        model_version="2026-06-01",
        provider="glm",
        cache_hit=True,
        billing_units=123,
        cost_usd=Decimal("0.0123"),
        latency_ms=250,
        prompt="hello",
        response_summary="done",
    )

    payload = event.to_json_dict()

    assert payload["kind"] == TelemetryEventKind.MODEL_CALL.value
    assert payload["run_id"] == "run-1"
    assert payload["session_id"] == "session-1"
    assert payload["model"] == "glm-5.2"
    assert payload["model_version"] == "2026-06-01"
    assert payload["provider"] == "glm"
    assert payload["cache_hit"] is True
    assert payload["billing_units"] == 123
    assert payload["cost_usd"] == "0.0123"
    assert payload["prompt"] == "hello"


def test_gateway_reconciliation_and_pricing_fallback_events_have_json_payloads():
    gateway_event = TelemetryEvent.gateway_usage(
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        gateway_request_id="gw-1",
        provider="glm",
        cache_hit=False,
        billing_units=123,
        cost_usd=Decimal("0.0123"),
        service="responses",
        native_unit="tokens",
        optimus_credits_debited=Decimal("1.23"),
        model="glm-5.2",
        model_version="2026-06-01",
        price_snapshot_id="prices-2026-07-04",
    )
    reconciliation_event = TelemetryEvent.reconciliation(
        run_id="run-1",
        session_id="session-1",
        request_id="req-2",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        matched_gateway_request_ids=frozenset({"gw-1"}),
        missing_provider_usage_ids=frozenset(),
        missing_evidence_ids=frozenset(),
        evidence_cost_usd=Decimal("0.0123"),
        provider_cost_usd=Decimal("0.0123"),
        cost_delta_usd=Decimal("0"),
        reconciled=True,
    )
    fallback_event = TelemetryEvent.pricing_fallback(
        run_id="run-1",
        session_id="session-1",
        request_id="req-3",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        provider="glm",
        service="responses",
        native_unit="tokens",
        price_snapshot_id="prices-local-2026-07-04",
        reason="gateway_price_snapshot_unavailable",
    )

    assert gateway_event.to_json_dict()["kind"] == TelemetryEventKind.GATEWAY_USAGE.value
    assert gateway_event.to_json_dict()["cost_usd"] == "0.0123"
    assert reconciliation_event.to_json_dict()["matched_gateway_request_ids"] == ["gw-1"]
    assert reconciliation_event.to_json_dict()["reconciled"] is True
    assert fallback_event.to_json_dict()["kind"] == TelemetryEventKind.PRICING_FALLBACK.value
    assert "cost_usd" not in fallback_event.to_json_dict()


def test_secret_values_are_redacted_from_event_payload():
    event = TelemetryEvent.tool_call(
        run_id="run-1",
        session_id=None,
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        tool_name="web.search",
        parameters={
            "query": "pytest",
            "api_key": "secret-token",
            "nested": {"Authorization": "Bearer nested-token"},
        },
        result_summary="Authorization: Bearer result-token",
        latency_ms=10,
        policy_reason="USER_REQUESTED",
        authorization_outcome="ALLOW",
    )

    assert "secret-token" not in event.to_json_line()
    assert "nested-token" not in event.to_json_line()
    assert "result-token" not in event.to_json_line()
    assert "**********" in event.to_json_line()
    assert event.to_json_dict()["authorization_outcome"] == "ALLOW"
