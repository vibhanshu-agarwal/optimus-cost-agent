"""The Gateway's decision route for classifier models such as Jev (Plan 12.4 v7 Design 1; ADR-007).

``POST /v1/decisions`` takes ``{model, state, questions, route_binding}`` and forwards it to the provider's System One
endpoint. It exists only under an enforced model registry: the model must be eligible for the classifier role in the
approved snapshot, the typed request must fit the classifier's complete-request bound, and exactly one provider
attempt is made, never re-sent. The reply's usage is settled like any model reply's, then its reply checks run; a
failed check on an exception route stops that model's route for the rest of the Gateway's life.
"""

from __future__ import annotations

import uuid
from typing import Any, Final

from optimus_gateway import request_diagnostics, usage_capture
from optimus_gateway.model_policy import ModelPolicyRefusal, admit_decision, check_decision_reply, parse_route_binding
from optimus_gateway.models import GatewayServiceConfig, authorize_bearer
from optimus_gateway.responses import (
    _REQUEST_BUDGET_FAILURE,
    _attempt_record,
    _stop_experimental_route,
    assert_gateway_usage_contract,
    format_cost_usd,
    policy_refusal,
    sanitize_error_message,
)
from optimus_gateway.upstream_client import DecisionResult, UpstreamAttemptFailure, UpstreamClient, request_budget_admits
from optimus_model_policy import decision_payload_text
from optimus_model_policy.binding import ATTEMPT_COMPLETED, ATTEMPT_NOT_SENT, ATTEMPT_UNCERTAIN, UPSTREAM_ATTEMPT_TIMEOUT_SECONDS

__all__ = ["DECISIONS_PATH", "handle_decision_request"]

DECISIONS_PATH: Final = "/v1/decisions"
_QUESTION_TYPES: Final = frozenset({"choice", "noul", "score"})


class _EnvelopeError(ValueError):
    pass


def _validate_envelope(body: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    model, state, questions = body.get("model"), body.get("state"), body.get("questions")
    if not isinstance(model, str) or not model.strip():
        raise _EnvelopeError("model must be a non-empty string")
    if not isinstance(state, dict):
        raise _EnvelopeError("state must be an object")
    if not isinstance(questions, dict) or not questions:
        raise _EnvelopeError("questions must be a non-empty object")
    for question in questions.values():
        if not isinstance(question, dict) or question.get("type") not in _QUESTION_TYPES:
            raise _EnvelopeError("each question must be an object with a choice, noul or score type")
        criteria = question.get("criteria")
        if question["type"] == "score" and not (isinstance(criteria, list) and len(criteria) >= 2):
            raise _EnvelopeError("a score question needs at least two ordered criteria")
        if question["type"] != "score" and not (isinstance(criteria, dict) and criteria):
            raise _EnvelopeError("a choice or noul question needs its criteria")
    return model, state, questions


def handle_decision_request(
    *,
    authorization_header: str | None,
    request_body: dict[str, Any],
    config: GatewayServiceConfig,
    upstream_client: UpstreamClient,
) -> tuple[int, dict[str, Any]]:
    if not authorize_bearer(authorization_header=authorization_header, shared_secret=config.shared_secret):
        return 401, {"error": "unauthorized"}
    policy = config.model_policy
    if policy is None:
        return policy_refusal(ModelPolicyRefusal("DECISIONS_NEED_REGISTRY", "decisions are served only under an enforced model registry"))
    try:
        model, state, questions = _validate_envelope(request_body)
    except _EnvelopeError as exc:
        return 400, {"error": sanitize_error_message(str(exc))}
    try:
        binding = parse_route_binding(request_body, policy)
        if binding is None:
            raise ModelPolicyRefusal("BINDING_REQUIRED")
        # The typed request the capacity check measures: its canonical state and questions (shared with the host).
        payload_text = decision_payload_text(state, questions)
        admitted = admit_decision(policy, model=model, payload_text=payload_text, binding=binding)
    except ModelPolicyRefusal as exc:
        return policy_refusal(exc)

    attempts: list[dict[str, Any]] = []
    correlation = {"route_request_id": admitted.request_id, "route_attempts": attempts, "retryable": False}
    attempt_id = f"gw-{uuid.uuid4().hex}"
    request_diagnostics.note(gateway_request_id=attempt_id)
    usage_capture.set_request(attempt_id)
    if not request_budget_admits(UPSTREAM_ATTEMPT_TIMEOUT_SECONDS):
        # As for a model attempt: nothing is dispatched that could still be running once the host stops waiting.
        attempts.append(_attempt_record(1, attempt_id, ATTEMPT_NOT_SENT, failure=dict(_REQUEST_BUDGET_FAILURE)))
        return 502, {"error": sanitize_error_message("upstream attempt failed (UPSTREAM_ATTEMPT_NOT_SENT)"), "code": "UPSTREAM_ATTEMPT_NOT_SENT", **correlation}
    try:
        result = upstream_client.create_decision_once(
            model=admitted.model_id, state=state, questions=questions, provider_controls=admitted.provider_controls
        )
    except UpstreamAttemptFailure as failure:
        attempts.append(_attempt_record(1, attempt_id, failure.outcome, http_status=failure.http_status, failure=failure.failure))
        code = f"UPSTREAM_ATTEMPT_{failure.outcome.upper()}"
        if failure.outcome == ATTEMPT_UNCERTAIN:
            _stop_experimental_route(policy, admitted, code)  # possibly billed, usage unknown
        return 502, {"error": sanitize_error_message(f"upstream attempt failed ({code})"), "code": code, **correlation}

    gateway_usage = _decision_usage(config=config, model=model, result=result, gateway_request_id=attempt_id)
    gateway_usage.update(route_request_id=admitted.request_id, attempt=1)
    try:
        assert_gateway_usage_contract(gateway_usage)
    except ValueError:
        attempts.append(_attempt_record(1, attempt_id, ATTEMPT_UNCERTAIN, provider_request_id=result.decision_id, failure={"kind": "usage_contract"}))
        _stop_experimental_route(policy, admitted, "UPSTREAM_ATTEMPT_UNCERTAIN")
        return 502, {"error": "upstream usage could not be verified", "code": "UPSTREAM_ATTEMPT_UNCERTAIN", **correlation}
    gateway_usage["cost_usd"] = format_cost_usd(result.cost_usd)
    attempts.append(_attempt_record(1, attempt_id, ATTEMPT_COMPLETED, provider_request_id=result.decision_id))
    try:
        check_decision_reply(admitted, result, policy)
    except ModelPolicyRefusal as exc:
        # The call happened and was billed: the error keeps its usage so the caller records it.
        _stop_experimental_route(policy, admitted, exc.code)
        status, body = policy_refusal(exc)
        return status, {**body, **correlation, "gateway_usage": gateway_usage}
    return 200, {"id": result.decision_id, "model": result.resolved_model, "answers": dict(result.answers), "gateway_usage": gateway_usage, "route_attempts": attempts}


def _decision_usage(*, config: GatewayServiceConfig, model: str, result: DecisionResult, gateway_request_id: str) -> dict[str, Any]:
    """The same usage fields a model reply carries; a decision has no cache, reasoning or finish facts."""
    return {
        "gateway_request_id": gateway_request_id,
        "provider": config.provider,
        "provider_request_id": result.decision_id,
        "billing_units": result.input_tokens + result.output_tokens,
        "cost_usd": result.cost_usd,
        "cache_hit": False,
        "model": model,
        "resolved_provider": result.resolved_provider,
        "resolved_model": result.resolved_model,
        "model_version": None,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "total_tokens": result.input_tokens + result.output_tokens,
        "reasoning_tokens": None,
        "cached_tokens": None,
        "cache_age_seconds": None,
    }
