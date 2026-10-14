from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from optimus.telemetry.events import TelemetryEvent, TelemetryEventKind
from optimus.telemetry.observability import TraceDeliveryState, TraceExportResult

LOCAL_SINK_RAISED_REASON_CODE = "telemetry_sink_raised"
_LOGGER = logging.getLogger("optimus.telemetry.fanout")


@dataclass(frozen=True, slots=True)
class LocalTelemetrySinkFailure:
    """A contained delivery failure with no exception message or private payload."""

    sink: str
    event_kind: str
    reason_code: str
    exception_type: str


class JsonlWriterProtocol(Protocol):
    def append(self, event: TelemetryEvent) -> None: ...


class GatewayExporterProtocol(Protocol):
    def export(self, events: tuple[TelemetryEvent, ...]) -> dict[str, object]: ...


class TelemetryFanout:
    """Synchronous fan-out of one telemetry event to local sinks plus a batched Gateway export.

    Every event is attempted against JSONL and Redis independently. Ordinary local
    delivery failures are logged as four sanitized fields and retained in the
    bounded recent ``local_sink_failures`` window; ``local_sink_failures_dropped``
    counts evictions. Exception messages and tracebacks are never logged here.
    Standard logging keeps diagnostics visible on stderr with debug tracing off.
    Control-flow exceptions still propagate. Mandatory audit, ledger and session
    writes are separate responsibilities and are not contained at this boundary.

    Neither local sink is skipped because of an ordinary delivery failure. Gateway export is
    batched (flushed once ``batch_size`` events have accumulated, or explicitly via
    :meth:`flush`) and isolated at this boundary: a Gateway export failure -- whether
    the exporter raises or returns a response that does not parse as a
    ``TraceExportResult`` -- is recorded in the bounded recent
    :attr:`delivery_results` list and never re-raised. Evictions are counted by
    :attr:`delivery_results_dropped`. This is a binding constraint (Plan 11.5 Task 5):
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
        delivery_result_limit: int = 16,
        local_sink_failure_limit: int = 16,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        if delivery_result_limit < 1:
            raise ValueError("delivery_result_limit must be >= 1")
        if local_sink_failure_limit < 1:
            raise ValueError("local_sink_failure_limit must be >= 1")
        self.delivery_result_limit = delivery_result_limit
        self.local_sink_failure_limit = local_sink_failure_limit
        self.jsonl_writer = jsonl_writer
        self.redis_sink = redis_sink
        self.gateway_exporter = gateway_exporter
        self.batch_size = batch_size
        self.delivery_results: list[TraceExportResult] = []
        self.delivery_results_dropped = 0
        self._buffer: list[TelemetryEvent] = []
        self._local_sink_failures: list[LocalTelemetrySinkFailure] = []
        self.local_sink_failures_dropped = 0

    @property
    def local_sink_failures(self) -> tuple[LocalTelemetrySinkFailure, ...]:
        """Recent sanitized failures; every failure is also logged independently."""
        return tuple(self._local_sink_failures)

    def _record_delivery_result(self, result: TraceExportResult) -> None:
        self.delivery_results.append(result)
        if len(self.delivery_results) > self.delivery_result_limit:
            del self.delivery_results[0]
            self.delivery_results_dropped += 1

    def _record_local_sink_failure(self, failure: LocalTelemetrySinkFailure) -> None:
        self._local_sink_failures.append(failure)
        if len(self._local_sink_failures) > self.local_sink_failure_limit:
            del self._local_sink_failures[0]
            self.local_sink_failures_dropped += 1

    def _attempt_local_sink(self, sink: str, event: TelemetryEvent, deliver: Callable[[TelemetryEvent], None]) -> None:
        try:
            deliver(event)
        except Exception as exc:
            failure = LocalTelemetrySinkFailure(
                sink=sink,
                event_kind=event.kind.value,
                reason_code=LOCAL_SINK_RAISED_REASON_CODE,
                exception_type=type(exc).__name__,
            )
            self._record_local_sink_failure(failure)
            _report_local_sink_failure(failure)

    def __call__(self, event: TelemetryEvent) -> None:
        self._attempt_local_sink("jsonl", event, self.jsonl_writer.append)
        self._attempt_local_sink("redis", event, self.redis_sink)
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
            self._record_delivery_result(_failed_delivery_result(reason=f"gateway_export_raised:{type(exc).__name__}"))
            return
        self._record_delivery_result(_parse_delivery_result(response))


def emit_acp_turn_settlement_contained(
    sink: Callable[[TelemetryEvent], None] | None,
    event: TelemetryEvent,
) -> None:
    """Best-effort settlement evidence: catch ``Exception`` only, never ``BaseException``.

    Ordinary ``TelemetryFanout.__call__`` semantics are unchanged. This narrow helper
    wraps the settlement evidence attempt so JSONL/Redis/Gateway failures cannot
    replace or swallow a surrounding ``CancelledError``.
    """
    if sink is None:
        return
    if event.kind is not TelemetryEventKind.ACP_TURN_SETTLEMENT:
        raise ValueError("emit_acp_turn_settlement_contained accepts only ACP_TURN_SETTLEMENT")
    try:
        sink(event)
    except Exception:
        return


def _report_local_sink_failure(failure: LocalTelemetrySinkFailure) -> None:
    _LOGGER.warning(
        "telemetry local sink failure: sink=%s event_kind=%s reason_code=%s exception_type=%s",
        failure.sink,
        failure.event_kind,
        failure.reason_code,
        failure.exception_type,
    )


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
