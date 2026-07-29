from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from optimus.telemetry.events import TelemetryEvent
from optimus.telemetry.fanout import TelemetryFanout
from optimus.telemetry.jsonl import JsonlTelemetryWriter
from optimus.telemetry.observability import TraceDeliveryState
from optimus.telemetry.redis_adapter import RedisTelemetryAdapter
from optimus.telemetry.redis_sink import RedisTelemetryEventSink


class FakeRedisTelemetryClient:
    """Minimal async double satisfying `RedisTelemetryClient` for wiring tests."""

    def __init__(self) -> None:
        self.commands: list[tuple[object, ...]] = []

    async def execute_command(self, *args: object):
        self.commands.append(args)
        return "OK"

    async def hset(self, key: str, mapping: dict[str, str]):
        self.commands.append(("HSET", key, mapping))
        return len(mapping)

    async def hsetnx(self, key: str, field: str, value: str):
        return 1

    async def hget(self, key: str, field: str):
        return None

    async def hdel(self, key: str, *fields: str):
        return 0

    async def expire(self, key: str, ttl_seconds: int):
        return True


class RecordingExporter:
    """Test double for the Gateway export seam: records every batch it is given."""

    def __init__(self) -> None:
        self.batches: list[tuple[TelemetryEvent, ...]] = []

    def export(self, events: tuple[TelemetryEvent, ...]) -> dict[str, object]:
        self.batches.append(events)
        return {
            "trace_batch_id": f"batch-{len(self.batches)}",
            "trace_ids": [],
            "delivery_state": "delivered",
            "retry_count": 0,
            "final_disposition": "delivered",
        }


class RecordingRedisSinkSpy:
    """Wraps a real event sink, recording every event forwarded to it exactly once.

    Delegates to the wrapped sink so the spy also exercises the real
    ``RedisTelemetryEventSink`` dispatch/no-op behavior per event kind -- it only
    adds an independent, order-preserving record of what ``TelemetryFanout``
    actually forwarded to the Redis-sink slot.
    """

    def __init__(self, wrapped: Callable[[TelemetryEvent], None]) -> None:
        self._wrapped = wrapped
        self.events: list[TelemetryEvent] = []

    def __call__(self, event: TelemetryEvent) -> None:
        self.events.append(event)
        self._wrapped(event)


class RaisingExporter:
    """Test double simulating a Gateway export transport/timeout failure."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.batches: list[tuple[TelemetryEvent, ...]] = []

    def export(self, events: tuple[TelemetryEvent, ...]) -> dict[str, object]:
        self.batches.append(events)
        raise self._exc


def _model_call_event(*, run_id: str = "run-1", request_id: str = "req-1") -> TelemetryEvent:
    return TelemetryEvent.model_call(
        run_id=run_id,
        session_id="session-1",
        request_id=request_id,
        occurred_at=datetime(2026, 7, 29, tzinfo=UTC),
        model="glm-5.2",
        model_version=None,
        provider="glm",
        cache_hit=False,
        billing_units=1,
        cost_usd=Decimal("0.001"),
        latency_ms=10,
        prompt="hi",
        response="there",
        input_tokens=1,
        output_tokens=1,
    )


def _tool_call_event(*, run_id: str = "run-1") -> TelemetryEvent:
    return TelemetryEvent.tool_call(
        run_id=run_id,
        session_id="session-1",
        request_id="req-tool",
        occurred_at=datetime(2026, 7, 29, tzinfo=UTC),
        tool_name="write_file",
        parameters={"path": "a.py"},
        result_summary="wrote 1 file",
        latency_ms=5,
        policy_reason="allowed",
        authorization_outcome="ALLOW",
    )


def _error_event(*, run_id: str = "run-1") -> TelemetryEvent:
    return TelemetryEvent.error(
        run_id=run_id,
        session_id="session-1",
        request_id="req-error",
        occurred_at=datetime(2026, 7, 29, tzinfo=UTC),
        error_type="GatewayHttpError",
        message="temporary outage",
        disposition="retried",
    )


def _retry_decision_event(*, run_id: str = "run-1") -> TelemetryEvent:
    return TelemetryEvent.retry_decision(
        run_id=run_id,
        session_id="session-1",
        request_id="req-retry",
        occurred_at=datetime(2026, 7, 29, tzinfo=UTC),
        attempt=2,
        retry_count=1,
        failure_kind="transient",
        action="retry",
        delay_ms=100,
        disposition="retrying",
    )


def _guardrail_audit_event(*, run_id: str = "run-1") -> TelemetryEvent:
    return TelemetryEvent.guardrail_audit(
        run_id=run_id,
        session_id="session-1",
        request_id="req-policy",
        occurred_at=datetime(2026, 7, 29, tzinfo=UTC),
        tool_surface="write_file",
        verdict="ALLOW",
        rule_id="rule-1",
        failed_checks=(),
        requires_human_approval=False,
    )


def _agent_run_event(*, run_id: str = "run-1") -> TelemetryEvent:
    return TelemetryEvent.agent_run(
        run_id=run_id,
        session_id="session-1",
        request_id="req-final",
        occurred_at=datetime(2026, 7, 29, tzinfo=UTC),
        status="completed",
        final_state="COMPLETED",
        tool_names=("write_file",),
        total_cost_usd=Decimal("0.003"),
        mutation_count=1,
        stop_reason=None,
    )


def _fanout(tmp_path, exporter, *, batch_size: int = 10) -> tuple[TelemetryFanout, JsonlTelemetryWriter, RedisTelemetryEventSink]:
    writer = JsonlTelemetryWriter(tmp_path / "telemetry.jsonl")
    redis_sink = RedisTelemetryEventSink(RedisTelemetryAdapter(client=FakeRedisTelemetryClient()))
    fanout = TelemetryFanout(
        jsonl_writer=writer,
        redis_sink=redis_sink,
        gateway_exporter=exporter,
        batch_size=batch_size,
    )
    return fanout, writer, redis_sink


def test_fanout_batches_gateway_export_at_configured_size(tmp_path):
    writer = JsonlTelemetryWriter(tmp_path / "telemetry.jsonl")
    redis_sink = RedisTelemetryEventSink(RedisTelemetryAdapter(client=FakeRedisTelemetryClient()))
    recording_exporter = RecordingExporter()
    event_one = _model_call_event(request_id="req-1")
    event_two = _model_call_event(request_id="req-2")

    fanout = TelemetryFanout(
        jsonl_writer=writer,
        redis_sink=redis_sink,
        gateway_exporter=recording_exporter,
        batch_size=2,
    )
    fanout(event_one)
    assert recording_exporter.batches == []
    fanout(event_two)
    assert len(recording_exporter.batches) == 1
    fanout.flush()
    assert all(event.run_id == "run-1" for event in recording_exporter.batches[0])
    # flush() is a no-op once the buffer has already been drained by the auto-flush above.
    assert len(recording_exporter.batches) == 1


def test_fanout_flush_is_a_noop_when_no_events_are_buffered(tmp_path):
    fanout, _writer, _redis_sink = _fanout(tmp_path, RecordingExporter())

    fanout.flush()

    assert fanout.delivery_results == []


def test_fanout_writes_every_event_kind_to_local_sinks_exactly_once(tmp_path):
    writer = JsonlTelemetryWriter(tmp_path / "telemetry.jsonl")
    real_redis_sink = RedisTelemetryEventSink(RedisTelemetryAdapter(client=FakeRedisTelemetryClient()))
    redis_spy = RecordingRedisSinkSpy(real_redis_sink)
    fanout = TelemetryFanout(
        jsonl_writer=writer,
        redis_sink=redis_spy,
        gateway_exporter=RecordingExporter(),
        batch_size=10,
    )

    events = (
        _model_call_event(),
        _tool_call_event(),
        _error_event(),
        _retry_decision_event(),
        _guardrail_audit_event(),
        _agent_run_event(),
    )
    for event in events:
        fanout(event)

    jsonl_lines = writer.path.read_text(encoding="utf-8").splitlines()
    assert len(jsonl_lines) == len(events)
    written_kinds = [event.kind.value for event in events]
    assert [f'"kind":"{kind}"' in line for kind, line in zip(written_kinds, jsonl_lines, strict=True)] == [True] * len(events)

    # Step-1 binding constraint: the Redis sink receives every model/tool/error/
    # retry/policy/final event exactly once, matching the same set and order as
    # the JSONL writer above -- not just the subset (MODEL_CALL/AGENT_RUN/
    # GATEWAY_USAGE) that RedisTelemetryEventSink itself acts on internally.
    assert redis_spy.events == list(events)
    assert [event.kind for event in redis_spy.events] == [event.kind for event in events]


def test_fanout_isolates_gateway_export_failure_and_records_failed_delivery_result(tmp_path):
    exporter = RaisingExporter(TimeoutError("gateway unreachable"))
    fanout, writer, _redis_sink = _fanout(tmp_path, exporter, batch_size=10)
    event_one = _model_call_event()

    fanout(event_one)
    assert fanout.delivery_results == []
    fanout.flush()

    assert len(fanout.delivery_results) == 1
    assert fanout.delivery_results[0].delivery_state is TraceDeliveryState.FAILED
    # Local sinks already have the event; the export failure never unwinds that.
    assert writer.path.read_text(encoding="utf-8").count("\n") == 1


def test_fanout_export_failure_never_raises_out_of_call_or_flush(tmp_path):
    exporter = RaisingExporter(TimeoutError("gateway unreachable"))
    fanout, _writer, _redis_sink = _fanout(tmp_path, exporter, batch_size=1)

    # batch_size=1 triggers the auto-flush synchronously inside __call__; it must not raise.
    fanout(_model_call_event())

    assert len(fanout.delivery_results) == 1
    assert fanout.delivery_results[0].delivery_state is TraceDeliveryState.FAILED


class MalformedResponseExporter:
    """Test double simulating a Gateway response that does not parse as a `TraceExportResult`."""

    def export(self, events: tuple[TelemetryEvent, ...]) -> dict[str, object]:
        return {"accepted": True}


def test_fanout_treats_a_malformed_gateway_response_as_a_failed_delivery(tmp_path):
    fanout, _writer, _redis_sink = _fanout(tmp_path, MalformedResponseExporter(), batch_size=1)

    fanout(_model_call_event())

    assert len(fanout.delivery_results) == 1
    assert fanout.delivery_results[0].delivery_state is TraceDeliveryState.FAILED
    assert "gateway_export_response_invalid" in fanout.delivery_results[0].final_disposition


def test_fanout_rejects_non_positive_batch_size(tmp_path):
    writer = JsonlTelemetryWriter(tmp_path / "telemetry.jsonl")
    redis_sink = RedisTelemetryEventSink(RedisTelemetryAdapter(client=FakeRedisTelemetryClient()))

    with pytest.raises(ValueError):
        TelemetryFanout(
            jsonl_writer=writer,
            redis_sink=redis_sink,
            gateway_exporter=RecordingExporter(),
            batch_size=0,
        )
