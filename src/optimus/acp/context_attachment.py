"""The ordinary launch's Context Engine composition (Plan 12.2 closure plan v3; the operator's approval of the
offline scope and policy, #237 6249169293).

An ordinary launch (no test profile) runs on the enforced shipped registry. It gets:

- an ordinary route policy binding every planning/answer request of the resolved agent model in that model's own
  implementer role, with the shipped implementer output reserve as its cap;
- an attached Context Engine: the existing :class:`ContextAttachment`, the plain engine, Gateway-backed maintenance
  through the registry's first eligible summarizer (Claude Haiku 5.5 with its accepted receipt), the one shared
  numeric policy (:mod:`optimus.context.shipped_policy`) and the per-turn receipt-first accounting.

It has none of Stage C's test controls: no scenario, seed, fault seam, pause or ledger. Without an eligible
summarizer the launch stays absent-engine (full history up to the floor, then a readable refusal); with the shipped
defaults that is an exceptional state, not the successful default.
"""

from __future__ import annotations

from typing import Any

from context_engine.engine import ContextEngine
from optimus.acp.debug_trace import log_provider_attempts
from optimus.context.assembly import ContextAttachment, SummarizerRoute
from optimus.context.maintenance import gateway_summarizer_factory
from optimus.context.shipped_policy import (
    INITIAL_STRATEGY,
    MAX_REPACKS,
    RECORD_RESERVATION_BYTES,
    SOURCE_MAX_BYTES,
    attachment_limits,
    no_attachment_ledger,
)
from optimus.gateway.route_binding import RouteIdentityError, RoutePolicy, registry_route_identity
from optimus_model_policy import IMPLEMENTER_ROLES, RegistrySnapshot, Role, select_eligible_models
from optimus_model_policy.binding import disclosure_key

__all__ = ["ordinary_attachment", "ordinary_route_policy"]

# The order in which an agent model's own implementer role is looked up: the default planner's (medium, then the
# easy fallback), then the higher tiers. A model keeps its own tier; nothing is reassigned.
_ROLE_ORDER = (Role.MEDIUM, Role.EASY, Role.COMPLEX, Role.ESCALATION)


def _implementer_role(snapshot: RegistrySnapshot, model_id: str) -> Role:
    for role in _ROLE_ORDER:
        if role in IMPLEMENTER_ROLES and model_id in select_eligible_models(snapshot, role):
            return role
    raise RouteIdentityError(f"model {model_id!r} is not an eligible implementer in the trusted registry")


def ordinary_route_policy(*, snapshot: RegistrySnapshot, model_id: str, shared_secret: str) -> RoutePolicy:
    """The ordinary launch's trusted planning/answer route policy for the resolved agent model."""
    role = _implementer_role(snapshot, model_id)
    output_cap = snapshot.policy.output_reserve_tokens.get("implementer")
    if output_cap is None:
        raise RouteIdentityError("the trusted registry states no implementer output reserve")
    return RoutePolicy(snapshot=snapshot, disclosure_key=disclosure_key(shared_secret), model_id=model_id, role=role.value, output_cap=output_cap)


def ordinary_attachment(*, snapshot: RegistrySnapshot, model_id: str, gateway_client: Any, shared_secret: str) -> ContextAttachment | None:
    """The ordinary launch's attachment, or None (absent engine) when the registry has no eligible summarizer."""
    summarizers = select_eligible_models(snapshot, Role.SUMMARIZER)
    if not summarizers:
        return None
    identity = registry_route_identity(snapshot, model_id=summarizers[0], role=Role.SUMMARIZER.value)
    route = SummarizerRoute(
        model_id=identity.model_id, role=identity.role, route=identity.route, reasoning=identity.reasoning, quantizations=identity.quantizations
    )
    limits = attachment_limits(snapshot, model_id)
    factory = gateway_summarizer_factory(
        gateway_client=gateway_client, route=route, snapshot=snapshot, disclosure_key=disclosure_key(shared_secret), attempt_observer=log_provider_attempts
    )
    return ContextAttachment(
        engine=ContextEngine(),
        parameters=limits.parameters,
        limits=limits.limits,
        source_max_bytes=SOURCE_MAX_BYTES,
        record_reservation_bytes=RECORD_RESERVATION_BYTES,
        usable_input_tokens=limits.usable_input_tokens,
        estimate_request=limits.estimate_request,
        registry_hash=snapshot.effective_hash,
        model_id=model_id,
        summarizer=factory,
        summarizer_route=route,
        record_receipt=no_attachment_ledger,
        max_repacks=MAX_REPACKS,
        initial_strategy=INITIAL_STRATEGY,
    )
