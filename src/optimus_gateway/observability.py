from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any, Mapping, Protocol

from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace import Tracer, set_span_in_context

from optimus_gateway.models import GatewayServiceConfig, authorize_bearer
from optimus_gateway.responses import sanitize_error_message
from optimus_gateway.upstream_client import UpstreamClient
from optimus_security.sanitization import sanitize_for_persistence

# Plan 11.5, Task 4: Gateway-local mirror of the agent-side
# `optimus.telemetry.observability` trace contract. Duplicated (not imported)
# because `optimus_gateway` must remain independently importable with zero
# `optimus.*` imports; field names and string values are kept identical so
# the wire envelope stays compatible with the agent-side client.

_TRACER_NAME = "optimus-gateway"
_DEFAULT_MAX_TRANSIENT_RETRIES = 1

_REQUIRED_IDENTITY_FIELDS = ("schema_version", "event_id", "trace_id", "kind", "run_id", "request_id", "occurred_at")
_OPTIONAL_IDENTITY_FIELDS = ("parent_span_id", "session_id", "gateway_request_id")

# Free-text content fields (mirroring TelemetryEvent payload shapes for
# model/tool/error events) are attached as a redacted span EVENT rather than
# a flat attribute, keeping short attribution values easy to query while
# quarantining larger untrusted text.
_CONTENT_EVENT_FIELD_NAMES = frozenset({"prompt", "response", "result_summary", "message", "output_summary", "summary"})

# Maps a `sanitize_for_persistence` rule name to a short, stable redaction
# reason string recorded on the span (never the raw rule-count metadata).
_REASON_BY_RULE: dict[str, str] = {
    "dict_key_redaction": "secret",
    "exact_secret_replacement": "secret",
    "bearer_token_redaction": "bearer_token",
    "env_assignment_redaction": "env_assignment",
    "generic_secret_redaction": "generic_secret",
    "api_key_header_redaction": "api_key_header",
    "x_api_key_header_redaction": "api_key_header",
    "uri_userinfo_masking": "uri_userinfo",
    "unsupported_object_type_metadata": "unsupported_type",
}

# Rules that indicate the FIELD ITSELF (not merely its text content) is
# secret-named; these fields are dropped entirely from span attributes
# rather than kept with a masked value.
_FIELD_DROP_REASONS = frozenset({"secret"})


class ObservabilityIngressError(ValueError):
    """Raised when a trace ingress envelope is structurally invalid."""


class TransientTraceExportError(Exception):
    """Raised by a `SpanExporter` to signal a retryable delivery fault.

    Distinguishes an exporter that could not currently reach the collector
    (network/connection-level) from a definite permanent rejection, so the
    bounded-retry exporter can report `QUEUED` (retryable later) instead of
    `FAILED` (a definite rejection) once its retry budget is exhausted.
    """


class TraceDeliveryState(StrEnum):
    DELIVERED = "delivered"
    QUEUED = "queued"
    FAILED = "failed"
    NOT_CONFIGURED = "not_configured"


@dataclass(frozen=True)
class GatewayTraceEvent:
    """Gateway-local mirror of the agent-side `TraceEvent`.

    Only structural identity fields are typed. Every other wire key is
    untrusted payload data preserved verbatim in `attributes` for span
    mapping/redaction — never executed, fetched, or promoted to policy.
    """

    schema_version: str
    event_id: str
    trace_id: str
    kind: str
    run_id: str
    request_id: str
    occurred_at: str
    parent_span_id: str | None = None
    session_id: str | None = None
    gateway_request_id: str | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GatewayTraceBatch:
    """Gateway-local mirror of the agent-side `TraceBatch`.

    Unlike the agent-side Pydantic model, `events` may be empty here: an
    empty, structurally valid batch is accepted (a legitimate no-op flush),
    not treated as malformed.
    """

    schema_version: str
    batch_id: str
    events: tuple[GatewayTraceEvent, ...]


@dataclass(frozen=True)
class GatewayTraceExportResult:
    """Gateway-local mirror of the agent-side `TraceExportResult`."""

    trace_batch_id: str
    trace_ids: tuple[str, ...] = ()
    delivery_state: TraceDeliveryState = TraceDeliveryState.NOT_CONFIGURED
    retry_count: int = 0
    final_disposition: str = ""


class TraceExporter(Protocol):
    def export(self, batch: GatewayTraceBatch) -> GatewayTraceExportResult:
        """Export a validated trace batch and return its explicit delivery state."""


def validate_trace_batch(request_body: dict[str, Any]) -> GatewayTraceBatch:
    """Validate the typed trace ingress envelope, tolerating unknown top-level keys.

    Event contents are treated as untrusted data: only structural shape is
    checked here, and no field is executed, dereferenced, or promoted to
    policy. Redaction happens later, at export/span-mapping time.
    """
    if not isinstance(request_body, dict):
        raise ObservabilityIngressError("request body must be a JSON object")
    schema_version = request_body.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version.strip():
        raise ObservabilityIngressError("schema_version is required and must be a non-empty string")
    batch_id = request_body.get("batch_id")
    if not isinstance(batch_id, str) or not batch_id.strip():
        raise ObservabilityIngressError("batch_id is required and must be a non-empty string")
    if "events" not in request_body:
        raise ObservabilityIngressError("events is required and must be an array")
    raw_events = request_body["events"]
    if not isinstance(raw_events, list):
        raise ObservabilityIngressError("events is required and must be an array")
    events = tuple(_validate_trace_event(raw_event, index) for index, raw_event in enumerate(raw_events))
    return GatewayTraceBatch(schema_version=schema_version, batch_id=batch_id, events=events)


def _validate_trace_event(raw_event: Any, index: int) -> GatewayTraceEvent:
    if not isinstance(raw_event, dict):
        raise ObservabilityIngressError(f"event at index {index} must be a JSON object")
    values: dict[str, Any] = {}
    for field_name in _REQUIRED_IDENTITY_FIELDS:
        value = raw_event.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ObservabilityIngressError(f"event at index {index} is missing required field: {field_name}")
        values[field_name] = value
    for field_name in _OPTIONAL_IDENTITY_FIELDS:
        value = raw_event.get(field_name)
        if value is not None and not isinstance(value, str):
            raise ObservabilityIngressError(
                f"event at index {index} field {field_name} must be a string when present"
            )
        values[field_name] = value
    identity_keys = frozenset(_REQUIRED_IDENTITY_FIELDS) | frozenset(_OPTIONAL_IDENTITY_FIELDS)
    attributes = {key: raw_value for key, raw_value in raw_event.items() if key not in identity_keys}
    return GatewayTraceEvent(**values, attributes=attributes)


class _RetryTrackingSpanExporter(SpanExporter):
    """Wraps the underlying `SpanExporter` to surface retry/outcome state.

    `BatchSpanProcessor.force_flush()` returns `True` on any non-shutdown
    call regardless of the delegate's actual export outcome — it never
    surfaces success/failure or retry counts. This wrapper is the only way
    to observe the delegate's real outcome from outside the processor after
    `force_flush()` returns.
    """

    def __init__(self, delegate: SpanExporter, *, max_retries: int) -> None:
        self._delegate = delegate
        self._max_retries = max_retries
        self.retry_count = 0
        self.succeeded = False
        self.exhausted_transient = False

    def export(self, spans: Any) -> SpanExportResult:
        attempt = 0
        while True:
            transient = False
            try:
                result = self._delegate.export(spans)
                if result is SpanExportResult.FAILURE and isinstance(self._delegate, OTLPSpanExporter):
                    transient = True
            except TransientTraceExportError:
                result = SpanExportResult.FAILURE
                transient = True
            except Exception:  # noqa: BLE001 — any other delegate fault is a permanent export failure
                result = SpanExportResult.FAILURE
            if result == SpanExportResult.SUCCESS:
                self.succeeded = True
                return SpanExportResult.SUCCESS
            if attempt >= self._max_retries:
                self.succeeded = False
                self.exhausted_transient = transient
                return SpanExportResult.FAILURE
            attempt += 1
            self.retry_count += 1

    def shutdown(self) -> None:
        self._delegate.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._delegate.force_flush(timeout_millis)


class OpenTelemetryTraceExporter:
    """Maps a validated `GatewayTraceBatch` to redacted OTLP spans.

    The production path builds `OTLPSpanExporter` from `otlp_endpoint`
    (HTTP/protobuf); tests inject `span_exporter` directly, bypassing the
    network entirely. A missing endpoint with no injected exporter is
    `NOT_CONFIGURED` — never a silent successful no-op.
    """

    def __init__(
        self,
        *,
        otlp_endpoint: str | None,
        span_exporter: SpanExporter | None = None,
        max_transient_retries: int = _DEFAULT_MAX_TRANSIENT_RETRIES,
    ) -> None:
        self._otlp_endpoint = otlp_endpoint
        self._span_exporter = span_exporter
        self._max_transient_retries = max_transient_retries

    def export(self, batch: GatewayTraceBatch) -> GatewayTraceExportResult:
        trace_ids = _distinct_trace_ids(batch)

        if not batch.events:
            return GatewayTraceExportResult(
                trace_batch_id=batch.batch_id,
                trace_ids=trace_ids,
                delivery_state=TraceDeliveryState.DELIVERED,
                retry_count=0,
                final_disposition="empty_batch_no_spans_exported",
            )

        delegate = self._span_exporter
        if delegate is None:
            if not self._otlp_endpoint:
                return GatewayTraceExportResult(
                    trace_batch_id=batch.batch_id,
                    trace_ids=trace_ids,
                    delivery_state=TraceDeliveryState.NOT_CONFIGURED,
                    retry_count=0,
                    final_disposition="otlp_endpoint_not_configured",
                )
            delegate = OTLPSpanExporter(endpoint=self._otlp_endpoint)

        tracker = _RetryTrackingSpanExporter(delegate, max_retries=self._max_transient_retries)
        provider = TracerProvider()
        processor = BatchSpanProcessor(tracker)
        provider.add_span_processor(processor)
        tracer = provider.get_tracer(_TRACER_NAME)

        _emit_spans(tracer, batch)
        processor.force_flush()
        provider.shutdown()

        if tracker.succeeded:
            delivery_state = TraceDeliveryState.DELIVERED
            final_disposition = "exported_to_otlp_collector"
        elif tracker.exhausted_transient:
            delivery_state = TraceDeliveryState.QUEUED
            final_disposition = "transient_export_failure_retry_budget_exhausted"
        else:
            delivery_state = TraceDeliveryState.FAILED
            final_disposition = "permanent_export_failure"

        return GatewayTraceExportResult(
            trace_batch_id=batch.batch_id,
            trace_ids=trace_ids,
            delivery_state=delivery_state,
            retry_count=tracker.retry_count,
            final_disposition=final_disposition,
        )


def _distinct_trace_ids(batch: GatewayTraceBatch) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for event in batch.events:
        seen.setdefault(event.trace_id, None)
    return tuple(seen.keys())


def _emit_spans(tracer: Tracer, batch: GatewayTraceBatch) -> None:
    """Map each event to a span, preserving parent/child structure by event_id.

    `parent_span_id` on the wire event carries the logical PARENT EVENT's
    `event_id` (not a raw OTel span id); children are nested under the real
    OTel context of the span already created for that parent event, so OTel
    natively assigns the correct shared trace id and parent/child span ids.
    """
    context_by_event_id: dict[str, Context] = {}
    for event in batch.events:
        parent_context = context_by_event_id.get(event.parent_span_id) if event.parent_span_id else None
        span = tracer.start_span(f"optimus.{event.kind}", context=parent_context if parent_context is not None else Context())
        try:
            _apply_identity_attributes(span, event)
            _apply_redacted_attributes(span, event)
        finally:
            span.end()
        context_by_event_id[event.event_id] = set_span_in_context(span)


def _apply_identity_attributes(span: Any, event: GatewayTraceEvent) -> None:
    span.set_attribute("schema_version", event.schema_version)
    span.set_attribute("event_id", event.event_id)
    span.set_attribute("trace_id", event.trace_id)
    span.set_attribute("run_id", event.run_id)
    span.set_attribute("request_id", event.request_id)
    span.set_attribute("occurred_at", event.occurred_at)
    if event.parent_span_id is not None:
        span.set_attribute("parent_span_id", event.parent_span_id)
    if event.session_id is not None:
        span.set_attribute("session_id", event.session_id)
    if event.gateway_request_id is not None:
        span.set_attribute("gateway_request_id", event.gateway_request_id)


def _apply_redacted_attributes(span: Any, event: GatewayTraceEvent) -> None:
    content_fields: dict[str, tuple[Any, str | None]] = {}
    for key, raw_value in event.attributes.items():
        sanitized_value, reason = _redact_field(key, raw_value)
        if reason in _FIELD_DROP_REASONS:
            span.add_event("redaction", attributes={"field": key, "reason": reason})
            continue
        if key in _CONTENT_EVENT_FIELD_NAMES:
            content_fields[key] = (sanitized_value, reason)
            continue
        coerced = _coerce_attribute_value(sanitized_value)
        if coerced is not None:
            span.set_attribute(key, coerced)
        if reason is not None:
            span.add_event("redaction", attributes={"field": key, "reason": reason})

    if content_fields:
        content_event_attributes: dict[str, Any] = {}
        for key, (value, reason) in content_fields.items():
            coerced = _coerce_attribute_value(value)
            content_event_attributes[key] = coerced if coerced is not None else ""
            if reason is not None:
                span.add_event("redaction", attributes={"field": key, "reason": reason})
        span.add_event("content", attributes=content_event_attributes)


def _redact_field(key: str, value: Any) -> tuple[Any, str | None]:
    """Sanitize a single untrusted attribute field via the shared sanitizer.

    Returns `(sanitized_value, reason)`; `reason` is `None` when no rule
    fired. Calling `sanitize_for_persistence` on a single-key dict isolates
    exactly which rule(s) fired for THIS field, which the shared sanitizer's
    aggregate `rule_counts` alone would not distinguish per field.
    """
    result = sanitize_for_persistence({key: value})
    sanitized = result.value
    sanitized_value = sanitized[key] if isinstance(sanitized, dict) and key in sanitized else value
    if not result.rule_counts:
        return sanitized_value, None
    for rule_name, reason in _REASON_BY_RULE.items():
        if rule_name in result.rule_counts:
            return sanitized_value, reason
    return sanitized_value, "redacted"


def _coerce_attribute_value(value: Any) -> str | bool | int | float | None:
    """Coerce a sanitized field value into an OTel-safe attribute primitive."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (str, int, float)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except TypeError:
        return str(value)


def handle_observability_traces_request(
    *,
    authorization_header: str | None,
    request_body: dict[str, Any],
    config: GatewayServiceConfig,
    upstream_client: UpstreamClient,
    trace_exporter: TraceExporter,
) -> tuple[int, dict[str, Any]]:
    """Authenticate, validate, redact, and export a typed trace batch.

    Acceptance means the Gateway accepted and attempted to export the
    structured trace batch, not that the underlying collector confirmed
    receipt — `delivery_state` carries that explicit outcome. This route
    never emits `gateway_usage`, `billing_units`, or `cost_usd`: trace
    delivery failure never fabricates model failure, reverses a mutation, or
    adds a model charge.
    """
    del upstream_client
    if not authorize_bearer(authorization_header=authorization_header, shared_secret=config.shared_secret):
        return 401, {"error": "unauthorized"}
    try:
        batch = validate_trace_batch(request_body)
    except ObservabilityIngressError as exc:
        return 400, {"error": sanitize_error_message(str(exc))}

    gateway_request_id = f"gw-{uuid.uuid4().hex}"
    result = trace_exporter.export(batch)
    return 200, {
        "status": "accepted",
        "gateway_request_id": gateway_request_id,
        "trace_batch_id": result.trace_batch_id,
        "trace_ids": list(result.trace_ids),
        "delivery_state": result.delivery_state.value,
        "retry_count": result.retry_count,
        "final_disposition": result.final_disposition,
    }
