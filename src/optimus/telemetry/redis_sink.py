from __future__ import annotations

from optimus.redis.async_bridge import sync_await
from optimus.telemetry.events import TelemetryEvent, TelemetryEventKind
from optimus.telemetry.redis_adapter import RedisTelemetryAdapter, RunMetadata


class RedisTelemetryEventSink:
    """Sync event sink that persists agent telemetry through RedisTelemetryAdapter."""

    def __init__(self, adapter: RedisTelemetryAdapter) -> None:
        self._adapter = adapter

    def __call__(self, event: TelemetryEvent) -> None:
        if event.kind is TelemetryEventKind.MODEL_CALL:
            sync_await(self._handle_model_call(event))
            return
        if event.kind is TelemetryEventKind.AGENT_RUN:
            sync_await(self._handle_agent_run(event))

    async def _handle_model_call(self, event: TelemetryEvent) -> None:
        payload = event.payload
        await self._adapter.record_metric(
            run_id=event.run_id,
            metric_name="cost_usd",
            value=str(payload["cost_usd"]),
        )
        await self._adapter.record_metric(
            run_id=event.run_id,
            metric_name="tokens_input",
            value=str(payload.get("input_tokens", 0)),
        )
        await self._adapter.record_metric(
            run_id=event.run_id,
            metric_name="tokens_output",
            value=str(payload.get("output_tokens", 0)),
        )

    async def _handle_agent_run(self, event: TelemetryEvent) -> None:
        payload = event.payload
        await self._adapter.record_metric(
            run_id=event.run_id,
            metric_name="cost_usd",
            value=str(payload["total_cost_usd"]),
        )
        await self._adapter.write_run_metadata(
            RunMetadata(
                run_id=event.run_id,
                execution_mode=str(payload.get("execution_mode", "AGENT")),
                generation_scope=str(payload.get("generation_scope", "FILE_MUTATION")),
                rigor_level=str(payload.get("rigor_level", "MEDIUM")),
                user_approval_id=str(payload.get("user_approval_id", "unauthorized_direct_run")),
                assumption_count=int(payload.get("assumption_count", 0)),
            )
        )
