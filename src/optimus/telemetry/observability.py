from __future__ import annotations

from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import GatewayClient, GatewayTransport
from optimus.telemetry.events import TelemetryEvent


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
        return self._client.post_observability_json(
            path="/v1/observability/traces",
            payload={"events": [event.to_json_dict() for event in events]},
        )
