from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from optimus_gateway.model_mapping import resolve_model_id
from optimus_gateway.models import (
    GatewayServiceConfig,
    ModelRequestValidationError,
    authorize_bearer,
    validate_responses_envelope,
)
from optimus_gateway.upstream_client import ProviderMessageResult, UpstreamClient
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

    try:
        model, input_text, _metadata = validate_responses_envelope(request_body)
    except ModelRequestValidationError as exc:
        return 400, {"error": sanitize_error_message(str(exc))}

    return run_model_completion(
        model=model,
        input_text=input_text,
        config=config,
        upstream_client=upstream_client,
        build_success=_build_responses_success,
    )


def run_model_completion(
    *,
    model: str,
    input_text: str,
    config: GatewayServiceConfig,
    upstream_client: UpstreamClient,
    build_success,
) -> tuple[int, dict[str, Any]]:
    """Shared auth-complete provider path for Responses and Chat Completions."""
    try:
        provider_model = resolve_model_id(provider=config.provider, model=model)
    except ValueError as exc:
        return 400, {"error": sanitize_error_message(str(exc))}

    try:
        provider_result = upstream_client.create_message(model=provider_model, input_text=input_text)
    except RuntimeError as exc:
        return 502, {"error": sanitize_error_message(str(exc))}

    gateway_usage = {
        "gateway_request_id": f"gw-{uuid.uuid4().hex}",
        "provider": config.provider,
        "provider_request_id": provider_result.message_id,
        "billing_units": provider_result.billing_units,
        "cost_usd": provider_result.cost_usd,
        "cache_hit": provider_result.cache_hit,
        "model": model,
        "resolved_provider": provider_result.resolved_provider,
        "resolved_model": provider_result.resolved_model,
        "model_version": provider_result.model_version,
        "input_tokens": provider_result.input_tokens,
        "output_tokens": provider_result.output_tokens,
        "total_tokens": provider_result.total_tokens,
        "reasoning_tokens": provider_result.reasoning_tokens,
        "cached_tokens": provider_result.cached_tokens,
        "cache_age_seconds": provider_result.cache_age_seconds,
    }
    try:
        assert_gateway_usage_contract(gateway_usage)
    except ValueError as exc:
        return 502, {"error": sanitize_error_message(str(exc))}
    gateway_usage["cost_usd"] = format_cost_usd(provider_result.cost_usd)
    return 200, build_success(provider_result=provider_result, gateway_usage=gateway_usage)


def assert_gateway_usage_contract(gateway_usage: dict[str, Any]) -> None:
    """Fail closed before emitting a model success envelope with incomplete usage."""
    required = ("gateway_request_id", "provider", "cache_hit", "billing_units", "cost_usd")
    for field in required:
        if field not in gateway_usage:
            raise ValueError(f"gateway_usage missing required field: {field}")
    request_id = gateway_usage["gateway_request_id"]
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("gateway_request_id must be a non-empty string")
    if not isinstance(gateway_usage["provider"], str) or not gateway_usage["provider"].strip():
        raise ValueError("provider must be a non-empty string")
    if gateway_usage["cost_usd"] is None:
        raise ValueError("cost_usd must be non-null")
    try:
        cost = Decimal(str(gateway_usage["cost_usd"]))
    except Exception as exc:
        raise ValueError("cost_usd must be decimal-parseable") from exc
    if not cost.is_finite() or cost < Decimal("0"):
        raise ValueError("cost_usd must be non-negative")
    billing = gateway_usage["billing_units"]
    if not isinstance(billing, int) or isinstance(billing, bool) or billing < 0:
        raise ValueError("billing_units must be a non-negative integer")


def _build_responses_success(
    *,
    provider_result: ProviderMessageResult,
    gateway_usage: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": f"resp-{uuid.uuid4().hex}",
        "output_text": provider_result.output_text,
        "gateway_usage": gateway_usage,
    }


def sanitize_error_message(message: str) -> str:
    """Return a sanitized Gateway error message without a raw fallback."""
    try:
        sanitized = sanitize_for_persistence(message).value
    except Exception:
        return "internal gateway error"
    return sanitized if isinstance(sanitized, str) and sanitized else "internal gateway error"


def format_cost_usd(cost_usd: Decimal) -> str:
    normalized = cost_usd.normalize()
    return format(normalized, "f")
