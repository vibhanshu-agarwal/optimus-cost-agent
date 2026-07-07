from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from optimus_gateway.anthropic_client import AnthropicClient
from optimus_gateway.models import GatewayServiceConfig, authorize_bearer, map_agent_model_id
from optimus_gateway.pricing import PRICE_SNAPSHOT_ID, billing_units, compute_cost_usd


def handle_responses_request(
    *,
    authorization_header: str | None,
    request_body: dict[str, Any],
    config: GatewayServiceConfig,
    anthropic_client: AnthropicClient,
) -> tuple[int, dict[str, Any]]:
    if not authorize_bearer(authorization_header=authorization_header, shared_secret=config.shared_secret):
        return 401, {"error": "unauthorized"}

    model = request_body.get("model")
    input_text = request_body.get("input")
    if not isinstance(model, str) or not model.strip():
        return 400, {"error": "model is required"}
    if not isinstance(input_text, str) or not input_text.strip():
        return 400, {"error": "input is required"}

    try:
        provider_model = map_agent_model_id(model)
    except ValueError as exc:
        return 400, {"error": str(exc)}

    try:
        provider_result = anthropic_client.create_message(model=provider_model, input_text=input_text)
    except RuntimeError as exc:
        return 502, {"error": str(exc)}

    gateway_request_id = f"gw-{uuid.uuid4().hex}"
    response_id = f"resp-{uuid.uuid4().hex}"
    total_billing_units = billing_units(
        input_tokens=provider_result.input_tokens,
        output_tokens=provider_result.output_tokens,
    )
    cost_usd = compute_cost_usd(
        input_tokens=provider_result.input_tokens,
        output_tokens=provider_result.output_tokens,
    )

    return 200, {
        "id": response_id,
        "output_text": provider_result.output_text,
        "gateway_usage": {
            "gateway_request_id": gateway_request_id,
            "provider": "anthropic",
            "provider_request_id": provider_result.message_id,
            "billing_units": total_billing_units,
            "cost_usd": _format_cost_usd(cost_usd),
            "cache_hit": False,
            "model": model,
            "model_version": provider_model,
            "price_snapshot_id": PRICE_SNAPSHOT_ID,
        },
    }


def _format_cost_usd(cost_usd: Decimal) -> str:
    normalized = cost_usd.normalize()
    return format(normalized, "f")
