"""Plan 12.8 K3 helpers shared by the live tier and its killed-writer child processes: receipts and turns as the
production call sites produce them, and a transport that hands host delivery to the real Gateway capture route."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from optimus.gateway.client import GatewayRequest
from optimus.gateway.errors import GatewayHttpError
from optimus.gateway.models import GatewayUsage
from optimus.usage.durable_capture import DurableCapture
from optimus.usage.turn_settlement import StageReceipt, TurnSettlement

AT = datetime(2026, 10, 31, tzinfo=UTC)
ROUTE_SECRET = "k3-route-secret"  # pragma: allowlist secret - a synthetic Gateway key for an in-process route


def receipt(turn: str, attempt: str, *, cost: str = "0.25", gw: str | None = None) -> StageReceipt:
    gw = gw or f"gw-{uuid.uuid4().hex}"
    usage = GatewayUsage(gateway_request_id=gw, provider="openrouter", billing_units=3, cost_usd=Decimal(cost))
    return StageReceipt(session_id="s", turn_id=turn, stage="planning", attempt_id=attempt, gateway_request_id=gw, outcome="completed",
                        reported_cost_usd=Decimal(cost), recorded_at=AT, gateway_usage=usage)


def turn(capture: DurableCapture, turn_id: str, receipts: list[StageReceipt]) -> None:
    """A turn as the production call sites produce it: each receipt follows its host request's pre-dispatch intent."""
    settlement = TurnSettlement(capture=capture, session_id="s")
    invocation = settlement.open_invocation(turn_id)
    invocation.start()
    for item in receipts:
        capture.intent(turn_id, item.attempt_id, stage="planning")
        try:
            settlement.record_attempt(item)
        except Exception:  # noqa: BLE001, S110 - a conflicting receipt is the case under test
            pass
    invocation.end()
    settlement.finalize_turn(turn_id)


class RouteTransport:
    """Hands each host delivery request to the real Gateway capture handler and raises as the urllib transport would."""

    def __init__(self, store: Any) -> None:
        from optimus_gateway.models import GatewayServiceConfig

        self.config = GatewayServiceConfig(bind_host="127.0.0.1", bind_port=0, shared_secret=ROUTE_SECRET, provider="openrouter",
                                           provider_api_key="or-test", base_url="https://openrouter.ai/api/v1", usage_store=store)  # pragma: allowlist secret

    def post_json(self, request: GatewayRequest) -> dict[str, Any]:
        from optimus_gateway.usage_capture import handle_usage_capture_request

        status, body = handle_usage_capture_request(
            authorization_header=request.headers.get("Authorization"), raw_body=json.dumps(request.payload).encode(), config=self.config
        )
        if status != 200:
            raise GatewayHttpError(status, json.dumps(body))
        return body


def route_client(store: Any) -> Any:
    from optimus.config.gateway import OptimusGatewaySettings
    from optimus.gateway.client import GatewayClient

    settings = OptimusGatewaySettings(gateway_url="http://127.0.0.1:1", optimus_api_key=ROUTE_SECRET)
    return GatewayClient(settings=settings, transport=RouteTransport(store))
