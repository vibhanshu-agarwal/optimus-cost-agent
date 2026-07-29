from __future__ import annotations

from collections.abc import Callable
from typing import Protocol
from uuid import uuid4

from optimus.telemetry.events import TelemetryEvent
from optimus.telemetry.observability import TraceDeliveryState, TraceExportResult


class JsonlWriterProtocol(Protocol):
    def append(self, event: TelemetryEvent) -> None: ...


class GatewayExporterProtocol(Protocol):
    def export(self, events: tuple[TelemetryEvent, ...]) -> dict[str, object]: ...


class TelemetryFanout:
    """Synchronous fan-out of one telemetry event to local sinks plus a batched Gateway export.

    Every event is written to the local JSONL writer and forwarded to the Redis sink
    immediately and unconditionally -- both are cheap, local, in-process calls that
    must never be skipped because of a Gateway export outcome. Gateway export is
    batched (flushed once ``batch_size`` events have accumulated, or explicitly via
    :meth:`flush`) and isolated at this boundary: a Gateway export failure -- whether
    the exporter raises or returns a response that does not parse as a
    ``TraceExportResult`` -- is recorded in :attr:`delivery_results` for later
    evidence and never re-raised. This is a binding constraint (Plan 11.5 Task 5):
    a trace-delivery failure must never invent a model failure, reverse a mutation,
    or add a model charge, so it can never propagate out of :meth:`__call__` or
    :meth:`flush` into the agent's result.

    Instances are callable with the single-event ``Callable[[TelemetryEvent], None]``
    signature already used throughout the codebase as ``event_sink``, so a
    ``TelemetryFanout`` is a drop-in replacement wherever an ``event_sink`` is
    threaded through (``AgentRunner``, ``SkillRegistry``, ``GoalLoopController``,
    ``UsageAccountingService``, ``GatedRetryRunner``, ...).
    """

    def __init__(
        self,
        *,
        jsonl_writer: JsonlWriterProtocol,
        redis_sink: Callable[[TelemetryEvent], None],
        gateway_exporter: GatewayExporterProtocol,
        batch_size: int = 25,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        self.jsonl_writer = jsonl_writer
        self.redis_sink = redis_sink
        self.gateway_exporter = gateway_exporter
        self.batch_size = batch_size
        self.delivery_results: list[TraceExportResult] = []
        self._buffer: list[TelemetryEvent] = []

    def __call__(self, event: TelemetryEvent) -> None:
        self.jsonl_writer.append(event)
        self.redis_sink(event)
        self._buffer.append(event)
        if len(self._buffer) >= self.batch_size:
            self._export_buffered_batch()

    def flush(self) -> None:
        """Export any buffered events immediately; a no-op when the buffer is empty."""
        if self._buffer:
            self._export_buffered_batch()

    def _export_buffered_batch(self) -> None:
        events = tuple(self._buffer)
        self._buffer.clear()
        try:
            response = self.gateway_exporter.export(events)
        except Exception as exc:
            self.delivery_results.append(_failed_delivery_result(reason=f"gateway_export_raised:{type(exc).__name__}"))
            return
        self.delivery_results.append(_parse_delivery_result(response))


def _failed_delivery_result(*, reason: str) -> TraceExportResult:
    return TraceExportResult(
        trace_batch_id=f"batch-{uuid4().hex}",
        trace_ids=(),
        delivery_state=TraceDeliveryState.FAILED,
        retry_count=0,
        final_disposition=reason,
    )


def _parse_delivery_result(response: dict[str, object]) -> TraceExportResult:
    try:
        return TraceExportResult.model_validate(response)
    except Exception as exc:
        return _failed_delivery_result(reason=f"gateway_export_response_invalid:{type(exc).__name__}")
