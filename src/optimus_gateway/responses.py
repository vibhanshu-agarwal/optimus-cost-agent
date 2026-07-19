from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from optimus_gateway.model_mapping import resolve_model_id
from optimus_gateway.models import GatewayServiceConfig, authorize_bearer
from optimus_gateway.pricing import billing_units, compute_cost_usd, lookup_model_rate
from optimus_gateway.upstream_client import UpstreamClient
from optimus_security.sanitization import sanitize_for_persistence


def handle_responses_request(
    *,
    authorization_header: str | None,
    request_body: dict[str, Any],
    config: GatewayServiceConfig,
    upstream_client: UpstreamClient,
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
        provider_model = resolve_model_id(provider=config.provider, model=model)
    except ValueError as exc:
        return 400, {"error": _sanitize_error_message(str(exc))}

    try:
        lookup_model_rate(provider=config.provider, resolved_model=provider_model)
    except ValueError as exc:
        return 500, {"error": _sanitize_error_message(str(exc))}

    try:
        provider_result = upstream_client.create_message(model=provider_model, input_text=input_text)
    except RuntimeError as exc:
        return 502, {"error": _sanitize_error_message(str(exc))}

    cost_usd, price_snapshot_id = compute_cost_usd(
        provider=config.provider,
        resolved_model=provider_model,
        input_tokens=provider_result.input_tokens,
        output_tokens=provider_result.output_tokens,
    )

    gateway_request_id = f"gw-{uuid.uuid4().hex}"
    response_id = f"resp-{uuid.uuid4().hex}"
    total_billing_units = billing_units(
        input_tokens=provider_result.input_tokens,
        output_tokens=provider_result.output_tokens,
    )

    return 200, {
        "id": response_id,
        "output_text": provider_result.output_text,
        "gateway_usage": {
            "gateway_request_id": gateway_request_id,
            "provider": config.provider,
            "provider_request_id": provider_result.message_id,
            "billing_units": total_billing_units,
            "cost_usd": _format_cost_usd(cost_usd),
            "cache_hit": False,
            "model": model,
            "model_version": provider_model,
            "price_snapshot_id": price_snapshot_id,
        },
    }


def _sanitize_error_message(message: str) -> str:
    """Return a sanitized Gateway error message without a raw fallback."""
    try:
        sanitized = sanitize_for_persistence(message).value
    except Exception:
        return "internal gateway error"
    return sanitized if isinstance(sanitized, str) and sanitized else "internal gateway error"


def _format_cost_usd(cost_usd: Decimal) -> str:
    normalized = cost_usd.normalize()
    return format(normalized, "f")
