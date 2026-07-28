from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import GatewayClient, GatewayTransport
from optimus.telemetry.events import TELEMETRY_EVENT_SCHEMA_VERSION, TelemetryEvent


class TraceEvent(BaseModel):
    """Wire-level trace event envelope validated inside a `TraceBatch`.

    This is deliberately narrower than `TelemetryEvent`: it validates the
    correlation identity fields required for Gateway trace ingress while
    permitting additional flattened payload keys (e.g. `cost_usd`, `provider`)
    to pass through untouched via `extra="allow"` for Gateway-side mapping.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    schema_version: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    parent_span_id: str | None = None
    kind: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    session_id: str | None = None
    request_id: str = Field(min_length=1)
    occurred_at: datetime
    gateway_request_id: str | None = None


class TraceBatch(BaseModel):
    """Agent-side typed batch of trace events sent to the Gateway trace ingress."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    schema_version: str = Field(min_length=1)
    batch_id: str = Field(min_length=1)
    events: tuple[TraceEvent, ...] = Field(min_length=1)


class TraceDeliveryState(StrEnum):
    DELIVERED = "delivered"
    QUEUED = "queued"
    FAILED = "failed"
    NOT_CONFIGURED = "not_configured"


class TraceExportResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    trace_batch_id: str = Field(min_length=1)
    trace_ids: tuple[str, ...] = ()
    delivery_state: TraceDeliveryState
    retry_count: int = Field(ge=0)
    final_disposition: str = Field(min_length=1)


class GatewayObservabilityExporter:
    def __init__(
        self,
        *,
        settings: OptimusGatewaySettings,
        transport: GatewayTransport | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._client = GatewayClient(settings=settings, transport=transport, timeout_seconds=timeout_seconds)

    def export(self, events: tuple[TelemetryEvent, ...]) -> dict[str, object]:
        """Send a typed `TraceBatch`-shaped envelope to the Gateway trace ingress.

        `schema_version`/`batch_id` are wire-required by the Gateway's typed
        `GatewayTraceBatch` validation (Task 4); a fresh `batch_id` is
        generated per export call so repeated flushes are independently
        correlatable even when they carry the same (or zero) events.
        """
        return self._client.post_observability_json(
            path="/v1/observability/traces",
            payload={
                "schema_version": TELEMETRY_EVENT_SCHEMA_VERSION,
                "batch_id": f"batch-{uuid4().hex}",
                "events": [event.to_json_dict() for event in events],
            },
        )
