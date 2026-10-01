"""Gateway enforcement of the trusted model registry (Plan 12.2 Task 5; Task 1 contracts §4).

Inactive unless launch composed a trusted snapshot (see ``optimus_model_policy.binding``). When a
:class:`GatewayModelPolicy` is configured, every model request must carry a ``route_binding`` and is
admitted only if, before any upstream call:

* the snapshot is the approved one and the caller bound that same snapshot;
* the model is an exact registry ID eligible for an active role (no alias, no pass-through);
* the final upstream request fits the verified route with the bound output cap counted once;
* a Contributor route carries a disclosure authorization for this request, route and payload.

The admitted request goes upstream with the route's provider allow-set, its routing controls and
the output cap. Its reply counts as complete only on a verified ``stop``; ``length`` passes through
so the host can mark it incomplete, and any other or missing finish status fails with its usage
kept, as a permanent (non-retryable) failure. Without a policy the Gateway keeps today's routing
and rejects any ``route_binding``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final

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

__all__ = [
    "AdmittedRequest",
    "GatewayModelPolicy",
    "ModelPolicyRefusal",
    "admit_request",
    "check_finish_status",
    "parse_route_binding",
]

COMPLETE_FINISH: Final = "stop"
LENGTH_FINISH: Final = "length"
_PASSED_FINISH: Final = frozenset({COMPLETE_FINISH, LENGTH_FINISH})


class ModelPolicyRefusal(Exception):
    """A request refused by the model policy. ``status`` is the HTTP status the Gateway returns."""

    def __init__(self, code: str, detail: str = "", *, status: int = 400) -> None:
        self.code = code
        self.detail = detail
        self.status = status
        super().__init__(f"model policy refused the request ({code}){': ' + detail if detail else ''}")


@dataclass(frozen=True)
class GatewayModelPolicy:
    """The trusted snapshot, the hash launch approved and the per-launch disclosure key."""

    snapshot: RegistrySnapshot
    approved_hash: str
    disclosure_key: bytes = field(repr=False)
    eligible_models: frozenset[str] = field(init=False)

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
            payload=payload_digest(model, messages, binding.output_cap),
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
    )


def check_finish_status(finish_reason: str | None) -> None:
    """Under the verified route contract only ``stop`` and ``length`` are passed to the host.

    The refusal is a permanent status (422): the call was made and billed, so the host must not
    re-dispatch it as a transient failure (an unknown or unusable result is never retried).
    """
    if finish_reason not in _PASSED_FINISH:
        raise ModelPolicyRefusal("FINISH_STATUS_UNVERIFIED", f"provider finish status {finish_reason!r}", status=422)
