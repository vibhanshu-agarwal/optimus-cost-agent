from datetime import UTC, datetime
from decimal import Decimal

from optimus.telemetry.events import TelemetryEvent, TelemetryEventKind
from optimus.telemetry.redaction import redact_for_telemetry


def test_model_call_event_contains_required_audit_fields():
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
        response="done with full model output",
        input_tokens=10,
        output_tokens=5,
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
    assert payload["latency_ms"] == 250
    assert payload["prompt"] == "hello"
    assert payload["response"] == "done with full model output"
    assert payload["input_tokens"] == 10
    assert payload["output_tokens"] == 5
    assert "response_summary" not in payload


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


def test_error_event_redacts_secrets_embedded_in_message_text():
    event = TelemetryEvent.error(
        run_id="run-1",
        session_id=None,
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        error_type="GatewayHttpError",
        message="OPTIMUS_API_KEY=opt-secret OPENAI_API_KEY=sk-secret api-key: abc123",
        disposition="fail_closed",
    )

    line = event.to_json_line()

    assert "opt-secret" not in line
    assert "sk-secret" not in line
    assert "abc123" not in line
    assert "OPTIMUS_API_KEY=**********" in line
    assert "OPENAI_API_KEY=**********" in line
    assert "api-key: **********" in line


def test_structured_provider_env_key_names_are_redacted_from_payload():
    event = TelemetryEvent.tool_call(
        run_id="run-1",
        session_id=None,
        request_id="req-1",
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        tool_name="web.search",
        parameters={
            "OPENAI_API_KEY": "sk-structured",
            "OPTIMUS_API_KEY": "opt-structured",
            "api_key": "plain-secret",
            "input_tokens": 12,
        },
        result_summary="ok",
        latency_ms=10,
        policy_reason="USER_REQUESTED",
        authorization_outcome="ALLOW",
    )

    parameters = event.to_json_dict()["parameters"]

    assert parameters["OPENAI_API_KEY"] == "**********"
    assert parameters["OPTIMUS_API_KEY"] == "**********"
    assert parameters["api_key"] == "**********"
    assert parameters["input_tokens"] == 12
    assert "sk-structured" not in event.to_json_line()
    assert "opt-structured" not in event.to_json_line()
    assert "plain-secret" not in event.to_json_line()


def test_retry_decision_event_serializes_failure_classification():
    event = TelemetryEvent.retry_decision(
        run_id="run-1",
        session_id="session-1",
        request_id="req-1",
        occurred_at=datetime(2026, 7, 5, tzinfo=UTC),
        attempt=2,
        retry_count=1,
        failure_kind="transient",
        action="retry",
        delay_ms=1000,
        disposition="retrying",
    )

    payload = event.to_json_dict()

    assert event.kind is TelemetryEventKind.RETRY_DECISION
    assert payload["attempt"] == 2
    assert payload["failure_kind"] == "transient"
    assert payload["action"] == "retry"


def test_fitness_gate_event_serializes_gate_names_and_cost():
    event = TelemetryEvent.fitness_gate(
        run_id="run-1",
        session_id=None,
        request_id="req-1",
        occurred_at=datetime(2026, 7, 5, tzinfo=UTC),
        passed=False,
        required_gate_names=("tests", "coverage"),
        failed_gate_names=("coverage",),
        duration_ms=125,
        cost_usd=Decimal("0.000"),
    )

    payload = event.to_json_dict()

    assert event.kind is TelemetryEventKind.FITNESS_GATE
    assert payload["passed"] is False
    assert payload["failed_gate_names"] == ["coverage"]
    assert payload["cost_usd"] == "0.000"


def test_golden_task_event_serializes_expected_and_actual_outcome():
    event = TelemetryEvent.golden_task(
        run_id="run-1",
        session_id=None,
        request_id="golden-docstring",
        occurred_at=datetime(2026, 7, 5, tzinfo=UTC),
        task_id="docstring-single-function",
        passed=True,
        expected_mode="agent",
        actual_mode="agent",
        expected_tools=("file_reader", "write_file"),
        actual_tools=("file_reader", "write_file"),
        max_cost_usd=Decimal("0.012"),
        actual_cost_usd=Decimal("0.009"),
        expected_final_state="completed",
        actual_final_state="completed",
    )

    payload = event.to_json_dict()

    assert event.kind is TelemetryEventKind.GOLDEN_TASK
    assert payload["task_id"] == "docstring-single-function"
    assert payload["passed"] is True


def test_release_gate_event_redacts_secret_environment_details():
    event = TelemetryEvent.release_gate(
        run_id="run-1",
        session_id=None,
        request_id="release",
        occurred_at=datetime(2026, 7, 5, tzinfo=UTC),
        gate_name="one-key",
        passed=False,
        duration_ms=10,
        output_summary="OPENAI_API_KEY=sk-live leaked",
    )

    payload = event.to_json_dict()

    assert event.kind is TelemetryEventKind.RELEASE_GATE
    assert payload["gate_name"] == "one-key"
    assert "sk-live" not in payload["output_summary"]
    assert "**********" in payload["output_summary"]


def test_public_redaction_helper_masks_provider_key_assignments():
    payload = redact_for_telemetry({"stdout": "OPENAI_API_KEY=sk-live"})

    assert payload == {"stdout": "OPENAI_API_KEY=**********"}
