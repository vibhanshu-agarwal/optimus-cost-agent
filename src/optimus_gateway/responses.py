from __future__ import annotations

import json
import time
import uuid
from decimal import Decimal
from typing import Any

from optimus_gateway import request_diagnostics, usage_capture
from optimus_gateway.model_mapping import resolve_model_id
from optimus_gateway.model_policy import (
    AdmittedRequest,
    GatewayModelPolicy,
    ModelPolicyRefusal,
    admit_request,
    check_experimental_reply,
    check_finish_status,
    parse_route_binding,
)
from optimus_gateway.models import (
    GatewayServiceConfig,
    ModelRequestValidationError,
    authorize_bearer,
    validate_responses_envelope,
)
from optimus_gateway.request_diagnostics import recognized_model, recognized_provider
from optimus_gateway.upstream_client import (
    KNOWN_ROUTER_STAGES,
    ProviderMessageResult,
    UpstreamAttemptFailure,
    UpstreamClient,
    request_budget_admits,
)
from optimus_model_policy.binding import (
    ATTEMPT_COMPLETED,
    ATTEMPT_NOT_SENT,
    ATTEMPT_UNCERTAIN,
    MAX_ROUTE_ATTEMPTS,
    UPSTREAM_ATTEMPT_TIMEOUT_SECONDS,
    RouteBinding,
)
from optimus_model_policy.stage_c import Admission, StageCRefusal, reservation_usd
from optimus_security.failure_facts import (
    bounded,
    bounded_failure,
    bounded_guardrail_list,
    final_sanitize,
    gateway_request_id,
    host_route_id,
    provider_request_id,
    slug,
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
        try:
            return _run_enforced_completion(
                model=model,
                input_text=input_text,
                config=config,
                upstream_client=upstream_client,
                build_success=build_success,
                route_binding=route_binding,
            )
        finally:
            # Correction plan v4, C2: a Stage C ledger write failure reaches this request's log line (and, since the
            # guard then halts, every later refusal's), never its response.
            write_failure = getattr(config.stage_c_guard, "last_write_failure", None)
            if isinstance(write_failure, dict):
                request_diagnostics.note(ledger_write_failure=dict(write_failure))
    try:
        provider_model = resolve_model_id(provider=config.provider, model=model)
    except ValueError as exc:
        # The caller's model name is never logged (C1): the log keeps the fixed text, the response is unchanged.
        request_diagnostics.note(error="unsupported gateway model")
        return 400, {"error": sanitize_error_message(str(exc))}

    # Minted before the upstream call so every attempt line and the outcome line share it (C9).
    gateway_request_id = f"gw-{uuid.uuid4().hex}"
    request_diagnostics.note(gateway_request_id=gateway_request_id)
    usage_capture.set_request(gateway_request_id)  # its internal retries are physical attempts of this one request
    try:
        provider_result = upstream_client.create_message(model=provider_model, input_text=input_text)
    except RuntimeError as exc:
        return 502, {"error": sanitize_error_message(str(exc))}

    gateway_usage = _gateway_usage(config=config, model=model, provider_result=provider_result, gateway_request_id=gateway_request_id)
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

    Under a Stage C guard (Plan 12.2 Task 13) each physical attempt, a safe resend included, is first
    admitted by the guard, which persists its full reservation before dispatch; a refusal reaches no
    provider. The attempt is settled once: a proven unbilled failure releases its dollars, an uncertain
    one stops every later dispatch, and a completed reply's reported charge is settled before any reply
    check can fail the call.
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
    guard = config.stage_c_guard
    admission: Admission | None = None
    number = 0
    while provider_result is None:
        # Bounded by the recovery rule below: only ``number < MAX_ROUTE_ATTEMPTS`` sends another.
        number += 1
        attempt_id = f"gw-{uuid.uuid4().hex}"
        usage_capture.set_request(attempt_id)
        if guard is not None:
            try:
                admission = guard.admit(attempt_id=attempt_id, request_id=admitted.request_id, reserve_usd=_attempt_reservation(policy, admitted))
            except StageCRefusal as exc:
                status, body = policy_refusal(ModelPolicyRefusal(exc.code, exc.detail, status=503))
                return status, {**body, **correlation}
        usage_capture.prepare_attempt()  # Plan 12.8: the capture intent, before the dispatch-time budget check
        if not request_budget_admits(UPSTREAM_ATTEMPT_TIMEOUT_SECONDS):
            # Checked at dispatch, after any admission and recovery delay: nothing is sent that could still be running
            # once the host stops waiting, so this attempt certainly reached no model.
            usage_capture.abandon_attempt()
            if admission is not None and guard is not None:
                guard.settle_unbilled(admission, ATTEMPT_NOT_SENT)
            attempts.append(_attempt_record(number, attempt_id, ATTEMPT_NOT_SENT, failure=dict(_REQUEST_BUDGET_FAILURE)))
            return 502, {"error": sanitize_error_message("upstream attempt failed (UPSTREAM_ATTEMPT_NOT_SENT)"), "code": "UPSTREAM_ATTEMPT_NOT_SENT", **correlation}
        try:
            provider_result = upstream_client.create_message_once(
                model=admitted.model_id,
                input_text=admitted.input_text,
                max_tokens=admitted.output_cap,
                provider_controls=admitted.provider_controls,
                reasoning=admitted.reasoning,
            )
        except UpstreamAttemptFailure as failure:
            if admission is not None and guard is not None:  # an admission exists only from a guard
                guard.settle_unbilled(admission, failure.outcome)  # an outcome not proven unbilled is unknown
            attempts.append(_attempt_record(number, attempt_id, failure.outcome, http_status=failure.http_status, failure=failure.failure))
            # A recovery attempt also has to end while the host is still waiting for this reply.
            if (
                failure.recoverable
                and number < MAX_ROUTE_ATTEMPTS
                and request_budget_admits(_RECOVERY_DELAY_SECONDS + UPSTREAM_ATTEMPT_TIMEOUT_SECONDS)
            ):
                _sleep(_RECOVERY_DELAY_SECONDS)
                continue
            code = f"UPSTREAM_ATTEMPT_{failure.outcome.upper()}"
            if failure.outcome == ATTEMPT_UNCERTAIN:
                _stop_experimental_route(policy, admitted, code)  # possibly billed, usage unknown
            return 502, {"error": sanitize_error_message(f"upstream attempt failed ({code})"), "code": code, **correlation}
        except BaseException:
            if admission is not None and guard is not None:
                guard.settle_unknown(admission, "attempt raised")
            raise

    gateway_usage = _gateway_usage(config=config, model=model, provider_result=provider_result, gateway_request_id=attempt_id)
    gateway_usage.update(route_request_id=admitted.request_id, attempt=number)
    try:
        assert_gateway_usage_contract(gateway_usage)
    except ValueError as exc:
        if admission is not None and guard is not None:
            guard.settle_unknown(admission, "usage unverifiable")
        attempts.append(
            _attempt_record(
                number,
                attempt_id,
                ATTEMPT_UNCERTAIN,
                provider_request_id=provider_result.message_id,
                router_pipeline=provider_result.router_pipeline,
                router_guardrails=provider_result.router_guardrails,
                failure={"kind": "usage_contract", "reason": slug(str(exc))},
            )
        )
        _stop_experimental_route(policy, admitted, "UPSTREAM_ATTEMPT_UNCERTAIN")
        return 502, {"error": "upstream usage could not be verified", "code": "UPSTREAM_ATTEMPT_UNCERTAIN", **correlation}
    if admission is not None and guard is not None:
        guard.settle_charged(admission, provider_result.cost_usd)  # settled before any reply check can fail
    gateway_usage["cost_usd"] = format_cost_usd(provider_result.cost_usd)
    attempts.append(
        _attempt_record(
            number,
            attempt_id,
            ATTEMPT_COMPLETED,
            provider_request_id=provider_result.message_id,
            router_pipeline=provider_result.router_pipeline,
            router_guardrails=provider_result.router_guardrails,
        )
    )
    try:
        check_finish_status(getattr(provider_result, "finish_reason", None))
        check_experimental_reply(admitted, provider_result, policy)
    except ModelPolicyRefusal as exc:
        # The call happened and was billed: the error keeps its usage so the host records it.
        _stop_experimental_route(policy, admitted, exc.code)
        status, body = policy_refusal(exc)
        return status, {**body, **correlation, "gateway_usage": gateway_usage}
    return 200, {**build_success(provider_result=provider_result, gateway_usage=gateway_usage), "route_attempts": attempts}


def _attempt_reservation(policy: GatewayModelPolicy, admitted: AdmittedRequest) -> Decimal:
    """One attempt's full Stage C reservation: the final admitted input estimate and the bound output cap
    (which also bounds reasoning output) at the registry's conservative prices."""
    prices = policy.snapshot.policy.models[admitted.model_id].prices
    return reservation_usd(
        input_tokens=admitted.decision.input_tokens,
        output_tokens=admitted.output_cap,
        input_usd_per_million=prices.input_usd_per_million,
        output_usd_per_million=prices.output_usd_per_million,
    )


def _stop_experimental_route(policy: GatewayModelPolicy, admitted: AdmittedRequest, code: str) -> None:
    """On an exception route a failed or unverifiable reply stops every later call to that model (Codex
    disposition, 2026-10-09; Plan 12.4 v7: per model); ordinary routes keep their per-request failure handling."""
    if admitted.experimental is not None:
        policy.route_stops.trip(admitted.model_id, code)


_RECOVERY_DELAY_SECONDS = 0.5
_sleep = time.sleep
_REQUEST_BUDGET_FAILURE = {"kind": "request_budget"}
"""An attempt never dispatched: it could not have ended before the host stops waiting (#397 live Z2)."""


def _attempt_record(
    number: int,
    attempt_id: str,
    outcome: str,
    *,
    http_status: int | None = None,
    provider_request_id: str | None = None,
    router_pipeline: tuple[str, ...] | None = None,
    router_guardrails: tuple[dict[str, Any], ...] | None = None,
    failure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """``router_pipeline``: the stage types the router reported for a completed attempt (empty when none ran,
    None without router metadata). ``router_guardrails``: each guardrail stage's closed facts (#400), added only
    when one ran, so every other record is unchanged. ``failure``: a failed attempt's bounded, content-free cause.
    Each keeps a failure diagnosable."""
    record = {
        "attempt": number,
        "gateway_request_id": attempt_id,
        "outcome": outcome,
        "http_status": http_status,
        "provider_request_id": provider_request_id,
        "router_pipeline": None if router_pipeline is None else list(router_pipeline),
        "failure": failure,
    }
    if router_guardrails:
        record["router_guardrails"] = list(router_guardrails)
    return record


_LOGGED_USAGE_FIELDS = ("gateway_request_id", "provider_request_id", "resolved_provider", "resolved_model", "input_tokens", "output_tokens", "cost_usd")


def model_request_log_line(path: str, status: int, body: dict[str, Any], *, policy: GatewayModelPolicy | None = None) -> str:
    """One JSON line per model request for the Gateway's log (its stderr, persisted as ``local-gateway.log``):
    the outcome, the Gateway's own refusal text, every attempt's ids and router stages, the settled usage, and the
    request's log-only facts (its legacy Gateway id, a Stage C ledger write failure). Selected fields only, each id
    in its generated shape and each upstream value recognized against trusted data (correction plan v4, C1), then
    a final redaction pass: never the prompt, the reply, a caller's free text or a credential. The response body
    itself is unchanged."""
    usage = body.get("gateway_usage")
    attempts = body.get("route_attempts")
    facts = request_diagnostics.noted()
    record = {
        "event": "model_request",
        "path": path,
        "status": status,
        "code": body.get("code"),
        "error": facts.get("error", body.get("error")),
        "gateway_request_id": gateway_request_id(facts.get("gateway_request_id")),
        "route_request_id": host_route_id(body.get("route_request_id") or (usage.get("route_request_id") if isinstance(usage, dict) else None)),
        "route_attempts": [_logged_attempt(item) for item in attempts or () if isinstance(item, dict)],
        "usage": _logged_usage(usage, policy) if isinstance(usage, dict) else None,
    }
    if "ledger_write_failure" in facts:
        record["ledger_write_failure"] = facts["ledger_write_failure"]
    return json.dumps(final_sanitize(record), separators=(",", ":"), sort_keys=True, default=str)


def _logged_attempt(item: dict[str, Any]) -> dict[str, Any]:
    stages = item.get("router_pipeline")
    logged = {
        "attempt": item.get("attempt") if type(item.get("attempt")) is int else None,
        "gateway_request_id": gateway_request_id(item.get("gateway_request_id")),
        "outcome": item.get("outcome"),
        "http_status": item.get("http_status") if type(item.get("http_status")) is int else None,
        "provider_request_id": provider_request_id(item.get("provider_request_id")),
        "router_pipeline": [bounded(stage, KNOWN_ROUTER_STAGES) for stage in stages] if isinstance(stages, list) else None,
        "failure": bounded_failure(item.get("failure")),
    }
    if "router_guardrails" in item:
        logged["router_guardrails"] = bounded_guardrail_list(item["router_guardrails"])
    return logged


def _logged_usage(usage: dict[str, Any], policy: GatewayModelPolicy | None) -> dict[str, Any]:
    logged = {key: usage.get(key) for key in _LOGGED_USAGE_FIELDS}
    logged["gateway_request_id"] = gateway_request_id(usage.get("gateway_request_id"))
    logged["provider_request_id"] = provider_request_id(usage.get("provider_request_id"))
    logged["resolved_provider"] = recognized_provider(usage.get("resolved_provider"), policy)
    logged["resolved_model"] = recognized_model(usage.get("resolved_model"), policy)
    return logged


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
    with that attempt's record. The log records the refusal's log-safe text (correction plan v4, C1)."""
    request_diagnostics.note(error=sanitize_error_message(exc.log_message))
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
