"""Gateway enforcement of the trusted model registry (Plan 12.2 Task 5; Task 1 contracts §4).

Inactive unless launch composed a trusted snapshot (see ``optimus_model_policy.binding``). When a
:class:`GatewayModelPolicy` is configured, every model request must carry a ``route_binding`` and is
admitted only if, before any upstream call:

* the snapshot is the approved one and the caller bound that same snapshot;
* the model is an exact registry ID eligible for an active role (no alias, no pass-through);
* the final upstream request fits the verified route with the bound output cap counted once;
* a Contributor route carries a disclosure authorization for this request, route and payload
  (the payload identity includes the approved reasoning setting).

The admitted request goes upstream with the route's exact endpoint slugs, its routing controls, the
output cap and the approved reasoning level, under the bounded attempt contract (see
``responses``). Its reply counts as complete only on a verified ``stop``; ``length`` passes through
so the host can mark it incomplete, and any other or missing finish status fails with its usage
kept, as a permanent (non-retryable) failure. Without a policy (an unenforced Gateway) it keeps the
pre-registry routing and rejects any ``route_binding`` with ``BINDING_UNSUPPORTED``.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final

from optimus_gateway.request_diagnostics import RECOGNIZED_FINISH, recognized_provider
from optimus_model_policy import (
    DORMANT_ROLES,
    CapacityDecision,
    Message,
    PackedModelRequest,
    RegistrySnapshot,
    Role,
    guard_request,
    select_eligible_models,
)
from optimus_model_policy.binding import (
    BindingError,
    RouteBinding,
    disclosure_key,
    payload_digest,
    route_digest,
    verify_disclosure,
)
from optimus_model_policy.capacity import estimate_complete_input
from optimus_model_policy.experimental import EMPIRICAL_ESTIMATOR_METHOD, ExperimentalRoute, experimental_route
from optimus_model_policy.registry import CLASSIFIER_REQUEST_BOUND_TOKENS
from optimus_security.failure_facts import bounded

__all__ = [
    "AdmittedRequest",
    "GatewayModelPolicy",
    "ModelPolicyRefusal",
    "RouteStops",
    "admit_decision",
    "admit_request",
    "check_decision_reply",
    "check_experimental_reply",
    "check_finish_status",
    "parse_route_binding",
]

COMPLETE_FINISH: Final = "stop"
LENGTH_FINISH: Final = "length"
_PASSED_FINISH: Final = frozenset({COMPLETE_FINISH, LENGTH_FINISH})


class ModelPolicyRefusal(Exception):
    """A request refused by the model policy. ``status`` is the HTTP status the Gateway returns.

    ``log_detail`` replaces ``detail`` in the Gateway's log only, where the detail would interpolate a reply's own
    value (correction plan v4, C1); the response keeps ``detail``. ``log_message`` is the text the log records."""

    def __init__(self, code: str, detail: str = "", *, status: int = 400, log_detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        self.status = status
        logged = detail if log_detail is None else log_detail
        self.log_message = f"model policy refused the request ({code}){': ' + logged if logged else ''}"
        super().__init__(f"model policy refused the request ({code}){': ' + detail if detail else ''}")


class RouteStops:
    """One stop per model (Plan 12.4 v7 Design 1). A failed exception-route check stops that model's route, and
    only that model's, for the rest of this Gateway's life. A tripped stop cannot be cleared."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._codes: dict[str, str] = {}

    def code(self, model_id: str) -> str | None:
        with self._lock:
            return self._codes.get(model_id)

    def trip(self, model_id: str, code: str) -> None:
        with self._lock:
            self._codes.setdefault(model_id, code)


@dataclass(frozen=True)
class GatewayModelPolicy:
    """The trusted snapshot, the hash launch approved and the per-launch disclosure key."""

    snapshot: RegistrySnapshot
    approved_hash: str
    disclosure_key: bytes = field(repr=False)
    eligible_models: frozenset[str] = field(init=False)
    route_stops: RouteStops = field(default_factory=RouteStops, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.snapshot.policy.fixture:
            raise ValueError("a fixture registry cannot be enforced")
        eligible = {
            model_id
            for role in Role
            if role not in DORMANT_ROLES
            for model_id in select_eligible_models(self.snapshot, role)
        }
        object.__setattr__(self, "eligible_models", frozenset(eligible))

    @classmethod
    def for_launch(cls, *, snapshot: RegistrySnapshot, approved_hash: str, shared_secret: str) -> GatewayModelPolicy:
        return cls(snapshot=snapshot, approved_hash=approved_hash, disclosure_key=disclosure_key(shared_secret))


@dataclass(frozen=True)
class AdmittedRequest:
    """A request cleared for one upstream call: what to send and the capacity decision behind it."""

    model_id: str
    input_text: str
    output_cap: int
    provider_controls: Mapping[str, Any]
    decision: CapacityDecision
    request_id: str
    reasoning: str | None
    """The route's approved reasoning level, sent as ``reasoning.effort`` (None: the route has none)."""
    experimental: ExperimentalRoute | None = None
    """The reviewed experimental test route this request was admitted under, if any: every reply is
    then checked with :func:`check_experimental_reply`."""


def parse_route_binding(request_body: Mapping[str, Any], policy: GatewayModelPolicy | None) -> RouteBinding | None:
    """The request's binding, or None on the inactive path. Unsupported combinations are refused."""
    raw = request_body.get("route_binding")
    if policy is None:
        if "route_binding" in request_body:
            raise ModelPolicyRefusal("BINDING_UNSUPPORTED", "this Gateway enforces no model registry")
        return None
    if raw is None:
        raise ModelPolicyRefusal("BINDING_REQUIRED", "requests must bind the trusted model registry")
    try:
        return RouteBinding.from_wire(raw)
    except BindingError as exc:
        raise ModelPolicyRefusal(exc.code, exc.detail) from exc


def admit_request(policy: GatewayModelPolicy, *, model: str, input_text: str, binding: RouteBinding) -> AdmittedRequest:
    """Admit one final upstream request or raise :class:`ModelPolicyRefusal`. Makes no calls."""
    snapshot = policy.snapshot
    if snapshot.effective_hash != policy.approved_hash:
        raise ModelPolicyRefusal("SNAPSHOT_NOT_APPROVED", status=503)
    if binding.registry_hash != snapshot.effective_hash:
        raise ModelPolicyRefusal("REGISTRY_HASH_MISMATCH", "the request bound a different registry snapshot")
    entry = snapshot.policy.models.get(model)
    if entry is None:
        raise ModelPolicyRefusal("UNKNOWN_MODEL", "only exact registry model IDs are routed")
    if model not in policy.eligible_models:
        raise ModelPolicyRefusal("MODEL_NOT_ELIGIBLE", "the model holds no eligible role in this snapshot")
    experimental = experimental_route(snapshot, model)
    stopped = None if experimental is None else policy.route_stops.code(model)
    if stopped is not None:
        raise ModelPolicyRefusal("EMPIRICAL_ROUTE_STOPPED", f"an earlier reply failed {stopped}", status=503)

    # The Gateway's upstream request is one user message holding the final flattened input.
    messages = (Message(role="user", content=input_text),)
    decision = guard_request(
        PackedModelRequest(model_id=model, messages=messages, tools_json="", output_cap=binding.output_cap),
        snapshot,
        policy.approved_hash,
    )
    if not decision.allowed:
        raise ModelPolicyRefusal(decision.reason or "CAPACITY_REFUSED")

    # Eligibility already requires a verified window, max output and quantization on every endpoint.
    endpoints = entry.route.endpoints

    if entry.data_use.disclosure == "contributor":
        authorization = binding.disclosure
        if authorization is None:
            raise ModelPolicyRefusal("DISCLOSURE_REQUIRED", "a Contributor route needs the disclosure notice first")
        if not verify_disclosure(
            policy.disclosure_key,
            authorization,
            request_id=binding.request_id,
            model_id=model,
            route=route_digest(model, entry),
            payload=payload_digest(model, messages, binding.output_cap, reasoning=entry.default_reasoning),
        ):
            raise ModelPolicyRefusal("DISCLOSURE_INVALID", "the disclosure does not cover this request, route and payload")

    controls = {
        "only": list(dict.fromkeys(endpoint.provider for endpoint in endpoints)),
        "quantizations": sorted({endpoint.quantization for endpoint in endpoints if endpoint.quantization is not None}),
        "allow_fallbacks": entry.route.allow_fallbacks,
        "require_parameters": entry.route.require_parameters,
    }
    return AdmittedRequest(
        model_id=model,
        input_text=input_text,
        output_cap=binding.output_cap,
        provider_controls=MappingProxyType(controls),
        decision=decision,
        request_id=binding.request_id,
        reasoning=entry.default_reasoning,
        experimental=experimental,
    )


def check_experimental_reply(admitted: AdmittedRequest, result: Any, policy: GatewayModelPolicy | None = None) -> None:
    """Check one completed reply against what the model's admission exceptions assumed (Codex disposition,
    2026-10-09; Plan 12.4 v7 Design 1). Every exception route's router metadata must be readable and report one
    attempt and no pipeline stage. A ``provider_family`` route's metadata must also name the recorded provider
    (identity, not an exact variant), whatever its estimator; an ``empirical_estimate`` route's reported prompt
    tokens must not exceed the estimate the request was admitted under. No provider is guessed. A failure is a
    permanent (422) billed result. A pass shows only that this request fitted. ``policy`` only lets the log's
    projection of a mismatched provider recognize the trusted registry's slugs (correction plan v4, C1); the check
    itself compares the original value."""
    route = admitted.experimental
    if route is None:
        return
    unreadable = getattr(result, "router_metadata_error", None)
    if unreadable is not None:
        raise ModelPolicyRefusal("EMPIRICAL_ROUTER_METADATA_MALFORMED", unreadable, status=422)
    provider = getattr(result, "resolved_provider", None)
    attempt = getattr(result, "router_attempt", None)
    pipeline = getattr(result, "router_pipeline", None)
    if route.provider_name is not None:
        if provider is None:
            raise ModelPolicyRefusal("EMPIRICAL_PROVIDER_MISSING", "the reply carries no selected router provider", status=422)
        if provider != route.provider_name:
            raise ModelPolicyRefusal(
                "EMPIRICAL_PROVIDER_MISMATCH",
                f"router provider {provider!r}, expected {route.provider_name!r}",
                log_detail=f"router provider {recognized_provider(provider, policy)!r}, expected {route.provider_name!r}",
                status=422,
            )
    if attempt is None or pipeline is None:
        raise ModelPolicyRefusal("EMPIRICAL_ROUTER_METADATA_MISSING", "the reply carries no router attempt or pipeline record", status=422)
    if attempt != 1:
        raise ModelPolicyRefusal("EMPIRICAL_ROUTER_FALLBACK", f"the router reports attempt {attempt}", status=422)
    if pipeline:
        raise ModelPolicyRefusal("EMPIRICAL_ROUTER_PIPELINE", f"the router ran {', '.join(pipeline)}", status=422)
    if route.empirical_estimate and result.input_tokens > admitted.decision.input_tokens:
        raise ModelPolicyRefusal(
            "EMPIRICAL_ESTIMATE_EXCEEDED",
            f"reported {result.input_tokens} prompt tokens, estimated at most {admitted.decision.input_tokens}",
            status=422,
        )


def admit_decision(policy: GatewayModelPolicy, *, model: str, payload_text: str, binding: RouteBinding) -> AdmittedRequest:
    """Admit one decision request (Plan 12.4 v7 Design 1: the Jev adapter) or raise :class:`ModelPolicyRefusal`.

    The model must be eligible for the classifier role in the approved snapshot, its route must not be stopped, and
    the typed request (its canonical state and questions) must fit the classifier's complete-request bound and the
    route's window by the route's own estimator. A decision model writes no free text, so no output is reserved."""
    snapshot = policy.snapshot
    if snapshot.effective_hash != policy.approved_hash:
        raise ModelPolicyRefusal("SNAPSHOT_NOT_APPROVED", status=503)
    if binding.registry_hash != snapshot.effective_hash:
        raise ModelPolicyRefusal("REGISTRY_HASH_MISMATCH", "the request bound a different registry snapshot")
    entry = snapshot.policy.models.get(model)
    if entry is None:
        raise ModelPolicyRefusal("UNKNOWN_MODEL", "only exact registry model IDs are routed")
    if model not in select_eligible_models(snapshot, Role.CLASSIFIER):
        raise ModelPolicyRefusal("MODEL_NOT_ELIGIBLE", "the model holds no eligible classifier role in this snapshot")
    experimental = experimental_route(snapshot, model)
    stopped = None if experimental is None else policy.route_stops.code(model)
    if stopped is not None:
        raise ModelPolicyRefusal("EMPIRICAL_ROUTE_STOPPED", f"an earlier reply failed {stopped}", status=503)
    profile = snapshot.policy.estimators[entry.route.estimator]
    if not profile.verified and not (experimental is not None and experimental.empirical_estimate and profile.method == EMPIRICAL_ESTIMATOR_METHOD):
        raise ModelPolicyRefusal("ESTIMATOR_UNVERIFIED")
    # Eligibility already requires a verified window on every endpoint.
    windows = [endpoint.context_window_tokens for endpoint in entry.route.endpoints if endpoint.context_window_tokens is not None]
    total = min(CLASSIFIER_REQUEST_BOUND_TOKENS, *windows)
    packed = PackedModelRequest(model_id=model, messages=(Message(role="user", content=payload_text),), tools_json="", output_cap=1)
    estimate = estimate_complete_input(packed, profile)
    decision = CapacityDecision(
        allowed=estimate.tokens <= total,
        reason=None if estimate.tokens <= total else "INPUT_EXCEEDS_CAPACITY",
        input_tokens=estimate.tokens,
        output_reserve=0,
        usable_input=total,
        effective_total=total,
    )
    if not decision.allowed:
        raise ModelPolicyRefusal("INPUT_EXCEEDS_CAPACITY")
    controls = {"only": list(dict.fromkeys(endpoint.provider for endpoint in entry.route.endpoints)), "allow_fallbacks": entry.route.allow_fallbacks}
    return AdmittedRequest(
        model_id=model,
        input_text=payload_text,
        output_cap=0,
        provider_controls=MappingProxyType(controls),
        decision=decision,
        request_id=binding.request_id,
        reasoning=None,
        experimental=experimental,
    )


def check_decision_reply(admitted: AdmittedRequest, result: Any, policy: GatewayModelPolicy | None = None) -> None:
    """Check one decision reply (Plan 12.4 v7; the System One endpoint carries no router metadata or finish status).

    Always: the reply names the requested model, or a dated snapshot of it. A ``provider_family`` route's reply must
    name the recorded provider; an ``empirical_estimate`` route's reported input tokens must not exceed the estimate.
    The router attempt and pipeline cannot be checked on this endpoint; the request sends ``allow_fallbacks: false``.
    A failure is a permanent (422) billed result."""
    resolved = getattr(result, "resolved_model", None)
    if not isinstance(resolved, str) or not (resolved == admitted.model_id or resolved.startswith(admitted.model_id + "-")):
        raise ModelPolicyRefusal("DECISION_MODEL_MISMATCH", "the reply names another model", status=422)
    route = admitted.experimental
    if route is None:
        return
    provider = getattr(result, "resolved_provider", None)
    if route.provider_name is not None:
        if provider is None:
            raise ModelPolicyRefusal("EMPIRICAL_PROVIDER_MISSING", "the reply carries no provider", status=422)
        if provider != route.provider_name:
            raise ModelPolicyRefusal(
                "EMPIRICAL_PROVIDER_MISMATCH",
                f"reply provider {provider!r}, expected {route.provider_name!r}",
                log_detail=f"reply provider {recognized_provider(provider, policy)!r}, expected {route.provider_name!r}",
                status=422,
            )
    if route.empirical_estimate and result.input_tokens > admitted.decision.input_tokens:
        raise ModelPolicyRefusal(
            "EMPIRICAL_ESTIMATE_EXCEEDED",
            f"reported {result.input_tokens} input tokens, estimated at most {admitted.decision.input_tokens}",
            status=422,
        )


def check_finish_status(finish_reason: str | None) -> None:
    """Under the verified route contract only ``stop`` and ``length`` are passed to the host.

    The refusal is a permanent status (422): the call was made and billed, so the host must not
    re-dispatch it as a transient failure (an unknown or unusable result is never retried).
    """
    if finish_reason not in _PASSED_FINISH:
        raise ModelPolicyRefusal(
            "FINISH_STATUS_UNVERIFIED",
            f"provider finish status {finish_reason!r}",
            log_detail=f"provider finish status {bounded(finish_reason, RECOGNIZED_FINISH)!r}",
            status=422,
        )
