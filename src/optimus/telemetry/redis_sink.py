from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from optimus.telemetry.events import TelemetryEvent, TelemetryEventKind
from optimus.telemetry.redis_adapter import RedisTelemetryAdapter, RunMetadata


class RedisTelemetryEventSink:
    """Sync event sink that persists agent telemetry through RedisTelemetryAdapter.

    Seam 2, checkpoint B: every Redis operation is submitted through ``submit`` -- the
    owner seam of the runtime whose client the adapter wraps (``RedisRuntime.run_sync``
    in production). The seam is required: a sink that fell back to the process-wide
    shared tool loop would drive that client from a second owner. Late events after
    the runtime closed its admission receive the runtime's stable closed error; nothing
    is reopened.
    """

    def __init__(
        self,
        adapter: RedisTelemetryAdapter,
        *,
        submit: Callable[[Callable[[], Awaitable[Any]]], Any],
    ) -> None:
        self._adapter = adapter
        self.submit = submit

    def __call__(self, event: TelemetryEvent) -> None:
        if event.kind is TelemetryEventKind.MODEL_CALL:
            self.submit(lambda: self._handle_model_call(event))
            return
        if event.kind is TelemetryEventKind.AGENT_RUN:
            self.submit(lambda: self._handle_agent_run(event))
            return
        if event.kind is TelemetryEventKind.GATEWAY_USAGE:
            self.submit(lambda: self._handle_gateway_usage(event))

    async def _handle_gateway_usage(self, event: TelemetryEvent) -> None:
        payload = event.payload
        await self._adapter.record_settled_usage(
            run_id=event.run_id,
            gateway_request_id=payload["gateway_request_id"],
            provider=payload["provider"],
            provider_request_id=payload.get("provider_request_id"),
            billing_units=payload["billing_units"],
            cost_usd=Decimal(str(payload["cost_usd"])),
        )

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
