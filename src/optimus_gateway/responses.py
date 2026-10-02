from __future__ import annotations

import time
import uuid
from decimal import Decimal
from typing import Any

from optimus_gateway.model_mapping import resolve_model_id
from optimus_gateway.model_policy import ModelPolicyRefusal, admit_request, check_finish_status, parse_route_binding
from optimus_gateway.models import (
    GatewayServiceConfig,
    ModelRequestValidationError,
    authorize_bearer,
    validate_responses_envelope,
)
from optimus_gateway.upstream_client import ProviderMessageResult, UpstreamAttemptFailure, UpstreamClient
from optimus_model_policy.binding import (
    ATTEMPT_COMPLETED,
    ATTEMPT_UNCERTAIN,
    MAX_ROUTE_ATTEMPTS,
    RouteBinding,
)
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
    try:
        route_binding = parse_route_binding(request_body, config.model_policy)
    except ModelPolicyRefusal as exc:
        return policy_refusal(exc)

    return run_model_completion(
        model=model,
        input_text=input_text,
        config=config,
        upstream_client=upstream_client,
        build_success=_build_responses_success,
        route_binding=route_binding,
    )


def run_model_completion(
    *,
    model: str,
    input_text: str,
    config: GatewayServiceConfig,
    upstream_client: UpstreamClient,
    build_success,
    route_binding: RouteBinding | None = None,
) -> tuple[int, dict[str, Any]]:
    """Shared auth-complete provider path for Responses and Chat Completions.

    With a model policy configured (Plan 12.2 Task 5) the request is admitted against the trusted
    registry before any upstream call and runs under the enforced attempt contract; without one,
    today's alias/pass-through routing and retry loop apply unchanged.
    """
    if config.model_policy is not None:
        return _run_enforced_completion(
            model=model,
            input_text=input_text,
            config=config,
            upstream_client=upstream_client,
            build_success=build_success,
            route_binding=route_binding,
        )
    try:
        provider_model = resolve_model_id(provider=config.provider, model=model)
    except ValueError as exc:
        return 400, {"error": sanitize_error_message(str(exc))}

    try:
        provider_result = upstream_client.create_message(model=provider_model, input_text=input_text)
    except RuntimeError as exc:
        return 502, {"error": sanitize_error_message(str(exc))}

    gateway_usage = _gateway_usage(config=config, model=model, provider_result=provider_result, gateway_request_id=f"gw-{uuid.uuid4().hex}")
    try:
        assert_gateway_usage_contract(gateway_usage)
    except ValueError as exc:
        return 502, {"error": sanitize_error_message(str(exc))}
    gateway_usage["cost_usd"] = format_cost_usd(provider_result.cost_usd)
    return 200, build_success(provider_result=provider_result, gateway_usage=gateway_usage)


def _run_enforced_completion(
    *,
    model: str,
    input_text: str,
    config: GatewayServiceConfig,
    upstream_client: UpstreamClient,
    build_success,
    route_binding: RouteBinding | None,
) -> tuple[int, dict[str, Any]]:
    """The enforced attempt contract (Task 1 contracts §4 and §6).

    One host model request makes at most ``MAX_ROUTE_ATTEMPTS`` provider attempts of the identical
    admitted payload on the same approved route. A further attempt follows only an attempt that
    certainly reached no model (never sent, or rate-limited); an uncertain, possibly billed attempt is
    never re-sent. Every attempt has its own receipt identity and is reported, in order, in
    ``route_attempts``; every failure is marked non-retryable, so the host does not re-send either.
    """
    policy = config.model_policy
    assert policy is not None
    if route_binding is None:
        return policy_refusal(ModelPolicyRefusal("BINDING_REQUIRED"))
    try:
        admitted = admit_request(policy, model=model, input_text=input_text, binding=route_binding)
    except ModelPolicyRefusal as exc:
        return policy_refusal(exc)

    attempts: list[dict[str, Any]] = []
    correlation = {"route_request_id": admitted.request_id, "route_attempts": attempts, "retryable": False}
    provider_result: ProviderMessageResult | None = None
    number = 0
    while provider_result is None:
        # Bounded by the recovery rule below: only ``number < MAX_ROUTE_ATTEMPTS`` sends another.
        number += 1
        attempt_id = f"gw-{uuid.uuid4().hex}"
        try:
            provider_result = upstream_client.create_message_once(
                model=admitted.model_id,
                input_text=admitted.input_text,
                max_tokens=admitted.output_cap,
                provider_controls=admitted.provider_controls,
                reasoning=admitted.reasoning,
            )
        except UpstreamAttemptFailure as failure:
            attempts.append(_attempt_record(number, attempt_id, failure.outcome, http_status=failure.http_status))
            if failure.recoverable and number < MAX_ROUTE_ATTEMPTS:
                _sleep(_RECOVERY_DELAY_SECONDS)
                continue
            code = f"UPSTREAM_ATTEMPT_{failure.outcome.upper()}"
            return 502, {"error": sanitize_error_message(f"upstream attempt failed ({code})"), "code": code, **correlation}

    gateway_usage = _gateway_usage(config=config, model=model, provider_result=provider_result, gateway_request_id=attempt_id)
    gateway_usage.update(route_request_id=admitted.request_id, attempt=number)
    try:
        assert_gateway_usage_contract(gateway_usage)
    except ValueError:
        attempts.append(_attempt_record(number, attempt_id, ATTEMPT_UNCERTAIN))
        return 502, {"error": "upstream usage could not be verified", "code": "UPSTREAM_ATTEMPT_UNCERTAIN", **correlation}
    gateway_usage["cost_usd"] = format_cost_usd(provider_result.cost_usd)
    attempts.append(_attempt_record(number, attempt_id, ATTEMPT_COMPLETED, provider_request_id=provider_result.message_id))
    try:
        check_finish_status(getattr(provider_result, "finish_reason", None))
    except ModelPolicyRefusal as exc:
        # The call happened and was billed: the error keeps its usage so the host records it.
        status, body = policy_refusal(exc)
        return status, {**body, **correlation, "gateway_usage": gateway_usage}
    return 200, {**build_success(provider_result=provider_result, gateway_usage=gateway_usage), "route_attempts": attempts}


_RECOVERY_DELAY_SECONDS = 0.5
_sleep = time.sleep


def _attempt_record(
    number: int, attempt_id: str, outcome: str, *, http_status: int | None = None, provider_request_id: str | None = None
) -> dict[str, Any]:
    return {
        "attempt": number,
        "gateway_request_id": attempt_id,
        "outcome": outcome,
        "http_status": http_status,
        "provider_request_id": provider_request_id,
    }


def _gateway_usage(
    *, config: GatewayServiceConfig, model: str, provider_result: ProviderMessageResult, gateway_request_id: str
) -> dict[str, Any]:
    return {
        "gateway_request_id": gateway_request_id,
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


def policy_refusal(exc: ModelPolicyRefusal) -> tuple[int, dict[str, Any]]:
    """A model-policy refusal: a stable code, never retryable by the host. ``route_attempts`` is empty
    for a refusal before any attempt; the finish-status refusal after a completed attempt replaces it
    with that attempt's record."""
    return exc.status, {"error": sanitize_error_message(str(exc)), "code": exc.code, "retryable": False, "route_attempts": []}


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
        # The provider's true finish status, or None when it reported none (Plan 12.2 Task 5).
        "finish_reason": getattr(provider_result, "finish_reason", None),
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
