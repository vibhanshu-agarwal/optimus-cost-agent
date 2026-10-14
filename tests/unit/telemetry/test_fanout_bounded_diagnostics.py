from datetime import UTC, datetime
from decimal import Decimal

import pytest

from optimus.telemetry.events import TelemetryEvent
from optimus.telemetry.fanout import TelemetryFanout


class RecordingWriter:
    def __init__(self) -> None:
        self.events: list[TelemetryEvent] = []

    def append(self, event: TelemetryEvent) -> None:
        self.events.append(event)


class RecordingExporter:
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


def _event(index: int) -> TelemetryEvent:
    return TelemetryEvent.model_call(
        run_id="run-1",
        session_id="session-1",
        request_id=f"req-{index}",
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


def test_fanout_retains_recent_delivery_results_and_accounts_for_evictions():
    writer = RecordingWriter()
    exporter = RecordingExporter()
    fanout = TelemetryFanout(
        jsonl_writer=writer,
        redis_sink=lambda event: None,
        gateway_exporter=exporter,
        batch_size=1,
    )
    original_list = fanout.delivery_results
    for index in range(20):
        fanout(_event(index))

    assert fanout.delivery_results is original_list
    assert len(fanout.delivery_results) == 16
    assert fanout.delivery_result_limit == 16
    assert fanout.delivery_results[0].trace_batch_id == "batch-5"
    assert fanout.delivery_results[-1].trace_batch_id == "batch-20"
    assert fanout.delivery_results_dropped == 4
    assert len(writer.events) == len(exporter.batches) == 20


def test_fanout_retains_recent_local_failures_and_accounts_for_evictions():
    class FailingWriter:
        def append(self, event):
            raise RuntimeError("synthetic sink failure")

    redis_attempts = []
    exporter = RecordingExporter()
    fanout = TelemetryFanout(
        jsonl_writer=FailingWriter(),
        redis_sink=redis_attempts.append,
        gateway_exporter=exporter,
        batch_size=1,
    )
    for index in range(20):
        fanout(_event(index))

    assert len(fanout.local_sink_failures) == fanout.local_sink_failure_limit == 16
    assert fanout.local_sink_failures_dropped == 4
    assert len(redis_attempts) == len(exporter.batches) == 20
    assert all(failure.sink == "jsonl" for failure in fanout.local_sink_failures)


def test_fanout_rejects_nonpositive_diagnostic_limits():
    for option in ("delivery_result_limit", "local_sink_failure_limit"):
        for invalid in (0, -1):
            with pytest.raises(ValueError, match=option):
                TelemetryFanout(
                    jsonl_writer=RecordingWriter(),
                    redis_sink=lambda event: None,
                    gateway_exporter=RecordingExporter(),
                    **{option: invalid},
                )


def test_custom_diagnostic_limits_keep_recent_results_and_log_evicted_failures(caplog):
    import logging

    class FailingWriter:
        def append(self, event):
            raise RuntimeError("synthetic-private-sink-message")

    def fail_redis(event):
        raise OSError("synthetic-private-sink-message")

    exporter = RecordingExporter()
    fanout = TelemetryFanout(jsonl_writer=FailingWriter(), redis_sink=fail_redis, gateway_exporter=exporter,
                             batch_size=1, delivery_result_limit=2, local_sink_failure_limit=3)
    original_list = fanout.delivery_results
    with caplog.at_level(logging.WARNING, logger="optimus.telemetry.fanout"):
        for index in range(4):
            fanout(_event(index))
    assert fanout.delivery_results is original_list
    assert [result.trace_batch_id for result in fanout.delivery_results] == ["batch-3", "batch-4"]
    assert fanout.delivery_results_dropped == 2
    assert [(failure.sink, failure.exception_type) for failure in fanout.local_sink_failures] == [
        ("redis", "OSError"), ("jsonl", "RuntimeError"), ("redis", "OSError"),
    ]
    assert fanout.local_sink_failures_dropped == 5
    assert len(exporter.batches) == 4
    warnings = [record for record in caplog.records if record.name == "optimus.telemetry.fanout"]
    assert len(warnings) == 8  # Evicting a memory record does not erase its visible warning.
    assert "synthetic-private-sink-message" not in caplog.text
