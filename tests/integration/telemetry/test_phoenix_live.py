"""E6: real Phoenix trace evidence for the Gateway OTel/OTLP export path.

Sends a real trace batch through the production Gateway trace-ingress
handler (``optimus_gateway.observability.handle_observability_traces_request``)
with a real ``OpenTelemetryTraceExporter`` whose OTLP target is the
Gateway-only ``OTEL_EXPORTER_OTLP_ENDPOINT`` (fail-closed if unset/blank).
Test-only ``PHOENIX_TEST_BASE_URL`` / ``PHOENIX_TEST_PROJECT`` are used only
for Phoenix health checks and the spans REST query
(``GET /v1/projects/{project}/spans``, the endpoint whose response schema
actually carries ``context``/``attributes``/``events`` -- the sibling
``/traces?include_spans=true`` endpoint only returns bare span identity
fields, confirmed by probing the live OpenAPI schema). OTLP and REST hosts
may intentionally differ (for example when the collector's OTLP port is
mapped separately from the UI/REST port).

No test fake stands in for Phoenix (Plan 11.5 Task 8 binding constraint).
Production code never imports a Phoenix SDK: this test only ever speaks
OTLP HTTP/protobuf (via the real, unmodified Gateway exporter class) and
Phoenix's plain REST API over ``urllib``. If ``OTEL_EXPORTER_OTLP_ENDPOINT``
or ``PHOENIX_TEST_BASE_URL`` is unset, or Phoenix is unreachable, the
fixture fails closed with an explicit missing-dependency message.

Task 8 watch item (multi-root OTel grouping): ``_emit_spans`` starts every
root event (no ``parent_span_id``) with a fresh, empty ``Context()``. This
test sends two root events that share one WIRE ``trace_id`` and asserts,
against the real Phoenix REST response, whether they land in one OTel/
Phoenix trace or two -- resolving the carry-in watch with live evidence
instead of narration.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime

import pytest

from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.observability import OpenTelemetryTraceExporter, handle_observability_traces_request

pytestmark = pytest.mark.requires_phoenix

_HEALTH_TIMEOUT_SECONDS = 30.0
_HEALTH_POLL_SECONDS = 0.5
_SPAN_QUERY_TIMEOUT_SECONDS = 30.0
_SPAN_QUERY_POLL_SECONDS = 1.0


def _http_get_json(url: str, *, timeout: float = 10.0) -> tuple[int, dict[str, object]]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, {}


def _wait_for_phoenix_health(base_url: str) -> None:
    deadline = time.monotonic() + _HEALTH_TIMEOUT_SECONDS
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/healthz", timeout=5) as response:
                if response.status == 200:
                    return
        except OSError as exc:
            last_error = exc
        time.sleep(_HEALTH_POLL_SECONDS)
    pytest.fail(
        f"Phoenix health endpoint at {base_url}/healthz did not become ready "
        f"within {_HEALTH_TIMEOUT_SECONDS}s ({last_error})."
    )


@pytest.fixture
def phoenix_otlp_endpoint() -> str:
    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not otlp_endpoint:
        pytest.fail(
            "Set Gateway-only OTEL_EXPORTER_OTLP_ENDPOINT to the real Phoenix OTLP "
            "HTTP traces URL (e.g. http://127.0.0.1:6006/v1/traces or a separately "
            "mapped OTLP port) before running requires_phoenix tests."
        )
    return otlp_endpoint


@pytest.fixture
def phoenix_project() -> tuple[str, str]:
    base_url = os.environ.get("PHOENIX_TEST_BASE_URL", "").strip()
    if not base_url:
        pytest.fail(
            "Set PHOENIX_TEST_BASE_URL (e.g. http://127.0.0.1:6006) to a running Phoenix "
            "collector's UI/REST base URL before running requires_phoenix tests "
            "(see docs/superpowers/plans/2026-07-29-plan-11-6-local-live-dependencies-operator-runbook.md "
            "for named Phoenix dependency startup)."
        )
    project = os.environ.get("PHOENIX_TEST_PROJECT", "default").strip() or "default"
    _wait_for_phoenix_health(base_url)
    return base_url, project


def _wire_event(
    *,
    event_id: str,
    trace_id: str,
    kind: str,
    run_id: str,
    request_id: str,
    session_id: str,
    parent_span_id: str | None = None,
    gateway_request_id: str | None = None,
    **attributes: object,
) -> dict[str, object]:
    event: dict[str, object] = {
        "schema_version": "1",
        "event_id": event_id,
        "trace_id": trace_id,
        "kind": kind,
        "run_id": run_id,
        "request_id": request_id,
        "occurred_at": datetime.now(UTC).isoformat(),
        "session_id": session_id,
    }
    if parent_span_id is not None:
        event["parent_span_id"] = parent_span_id
    if gateway_request_id is not None:
        event["gateway_request_id"] = gateway_request_id
    event.update(attributes)
    return event


def _span_by_event_id(spans: list[dict[str, object]], event_id: str) -> dict[str, object]:
    for span in spans:
        if (span.get("attributes", {}) or {}).get("event_id") == event_id:
            return span
    raise AssertionError(f"no span found with event_id={event_id!r}")


def test_live_phoenix_receives_real_otlp_batch_with_required_fields(
    phoenix_project: tuple[str, str],
    phoenix_otlp_endpoint: str,
) -> None:
    base_url, project = phoenix_project
    run_id = f"run-phoenix-{uuid.uuid4().hex[:12]}"
    session_id = f"session-phoenix-{uuid.uuid4().hex[:12]}"
    wire_trace_id = f"trace-{uuid.uuid4().hex}"
    root_a_id = f"evt-root-a-{uuid.uuid4().hex[:8]}"
    root_b_id = f"evt-root-b-{uuid.uuid4().hex[:8]}"
    child_id = f"evt-child-{uuid.uuid4().hex[:8]}"
    batch_id = f"batch-{uuid.uuid4().hex}"

    events = [
        _wire_event(
            event_id=root_a_id,
            trace_id=wire_trace_id,
            kind="model_call",
            run_id=run_id,
            request_id="req-phoenix-1",
            session_id=session_id,
            gateway_request_id="gw-phoenix-1",
            provider="glm",
            model="glm-5.2",
            cache_hit=False,
            billing_units=10,
            cost_usd="0.0015",
            api_key="should-never-reach-phoenix",
            prompt="live phoenix evidence prompt",
        ),
        _wire_event(
            event_id=root_b_id,
            trace_id=wire_trace_id,
            kind="tool_call",
            run_id=run_id,
            request_id="req-phoenix-2",
            session_id=session_id,
            policy_signal="USER_REQUESTED_EXTERNAL_FACT",
            validation_status="passed",
            final_disposition="delivered",
        ),
        _wire_event(
            event_id=child_id,
            trace_id=wire_trace_id,
            kind="model_call_retry",
            run_id=run_id,
            request_id="req-phoenix-1",
            session_id=session_id,
            parent_span_id=root_a_id,
            retry_count=1,
            cache_hit=False,
        ),
    ]
    request_body = {"schema_version": "1", "batch_id": batch_id, "events": events}

    config = GatewayServiceConfig(
        bind_host="127.0.0.1",
        bind_port=0,
        shared_secret="phoenix-live-evidence-secret",
        provider="openrouter",
        provider_api_key="phoenix-live-evidence-dummy-provider-key",
        base_url="https://openrouter.ai/api/v1",
        otlp_endpoint=phoenix_otlp_endpoint,
    )
    trace_exporter = OpenTelemetryTraceExporter(otlp_endpoint=config.otlp_endpoint)

    status, body = handle_observability_traces_request(
        authorization_header=f"Bearer {config.shared_secret}",
        request_body=request_body,
        config=config,
        upstream_client=None,
        trace_exporter=trace_exporter,
    )

    assert status == 200
    assert body["status"] == "accepted"
    assert body["delivery_state"] == "delivered"
    assert "gateway_usage" not in body
    assert "billing_units" not in body
    assert "cost_usd" not in body

    spans = _poll_for_spans(base_url, project, event_ids=(root_a_id, root_b_id, child_id))

    root_a_span = _span_by_event_id(spans, root_a_id)
    root_b_span = _span_by_event_id(spans, root_b_id)
    child_span = _span_by_event_id(spans, child_id)

    root_a_attrs = root_a_span["attributes"]
    root_b_attrs = root_b_span["attributes"]
    child_attrs = child_span["attributes"]

    # Required identity/correlation attributes.
    for attrs, expected_request_id in ((root_a_attrs, "req-phoenix-1"), (root_b_attrs, "req-phoenix-2")):
        assert attrs["run_id"] == run_id
        assert attrs["session_id"] == session_id
        assert attrs["request_id"] == expected_request_id
        assert attrs["trace_id"] == wire_trace_id

    # Provider/model/cache/billing/USD attribution on the model_call root.
    assert root_a_attrs["provider"] == "glm"
    assert root_a_attrs["model"] == "glm-5.2"
    assert root_a_attrs["cache_hit"] is False
    assert root_a_attrs["billing_units"] == 10
    assert root_a_attrs["cost_usd"] == "0.0015"
    assert root_a_attrs["gateway_request_id"] == "gw-phoenix-1"

    # Redaction: the secret-named "api_key" field must never reach Phoenix,
    # either as a raw attribute or inside its redaction event.
    for span in (root_a_span,):
        assert "api_key" not in span["attributes"]
        redaction_events = [event for event in span.get("events", []) if event.get("name") == "redaction"]
        assert any(event["attributes"].get("field") == "api_key" for event in redaction_events)
        for event in redaction_events:
            assert "should-never-reach-phoenix" not in json.dumps(event)
        assert "should-never-reach-phoenix" not in json.dumps(span)

    # Validation/policy/final-disposition attribution on the tool_call root.
    assert root_b_attrs["policy_signal"] == "USER_REQUESTED_EXTERNAL_FACT"
    assert root_b_attrs["validation_status"] == "passed"
    assert root_b_attrs["final_disposition"] == "delivered"

    # Retry attribution on the child.
    assert child_attrs["retry_count"] == 1
    assert child_attrs["parent_span_id"] == root_a_id

    # Parent/child relationship: the child's real OTel parent span id must
    # equal root A's real OTel span id (not the wire event_id).
    assert child_span["parent_id"] == root_a_span["context"]["span_id"]

    # Task 8 watch (multi-root OTel grouping): _emit_spans starts every root
    # (no parent_span_id) with a fresh, empty Context(), so the OTel SDK
    # assigns each root its own new real trace id. Two roots sharing one
    # WIRE trace_id therefore land in two DIFFERENT real OTel/Phoenix
    # traces -- proven here against a real collector, not asserted from
    # source reading alone.
    root_a_real_trace_id = root_a_span["context"]["trace_id"]
    root_b_real_trace_id = root_b_span["context"]["trace_id"]
    assert root_a_real_trace_id != root_b_real_trace_id, (
        "Watch item resolved differently than expected: two root events sharing one "
        "wire trace_id landed in the SAME real OTel/Phoenix trace. Update the Task 8 "
        "report disposition if this assertion ever legitimately flips."
    )
    # The child (parented to root A) shares root A's real trace id.
    assert child_span["context"]["trace_id"] == root_a_real_trace_id


def _poll_for_spans(base_url: str, project: str, *, event_ids: tuple[str, ...]) -> list[dict[str, object]]:
    deadline = time.monotonic() + _SPAN_QUERY_TIMEOUT_SECONDS
    last_spans: list[dict[str, object]] = []
    while time.monotonic() < deadline:
        status, body = _http_get_json(f"{base_url}/v1/projects/{project}/spans?limit=200")
        if status == 200:
            spans = list(body.get("data", []))
            last_spans = spans
            found_ids = {(span.get("attributes", {}) or {}).get("event_id") for span in spans}
            if set(event_ids).issubset(found_ids):
                return spans
        time.sleep(_SPAN_QUERY_POLL_SECONDS)
    pytest.fail(
        f"Phoenix project {project!r} at {base_url} did not surface all expected spans "
        f"{event_ids} within {_SPAN_QUERY_TIMEOUT_SECONDS}s (last saw {len(last_spans)} spans)."
    )
