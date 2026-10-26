"""Process-scoped Auto composition for the ACP host (Plan 12.4 Designs 1 and 4; ADR-027).

``OPTIMUS_AGENT_MODEL=auto`` is the only way to choose Auto (``optimus.agent.defaults.auto_requested``). The launch
gate composes the Auto registry (the shipped defaults, the shipped Auto overlay and the operator override) and binds
its literal and its composition name in the operator's approval. After the launch is authorized, the host recomposes it
here and refuses anything other than what that authorized candidate digested. The Gateway composes the same registry
independently (``--auto-composition``) and refuses to start unless the signed manifest binds its hash. Nothing here
reads the environment, changes ``trusted_snapshot()`` or edits shipped data.

Each turn (Task 4 implementation note r3, sections 2-6): the injected classifier answers from the frozen input contract,
off the event loop; :meth:`AutoRouter.resolve` maps its tier to a role and picks the cheapest eligible model this launch
has not stopped, routing up a tier at a time, then to the default planner; the turn then binds that model's route and
context limits for its whole life. The launch's state below is immutable except the stop set, which only grows.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any, Literal

from optimus.acp.context_attachment import implementer_role, ordinary_attachment
from optimus.agent.auto_contract import ClassifierInput, Tier
from optimus.agent.defaults import default_agent_model
from optimus.context.assembly import ContextAttachment
from optimus.context.shipped_policy import attachment_limits
from optimus.gateway.route_binding import RouteIdentityError, RoutePolicy
from optimus_model_policy import RegistrySnapshot, Role, select_eligible_models
from optimus_model_policy.binding import AUTO_COMPOSITION, BindingError, approval_literal, auto_snapshot, disclosure_key

__all__ = [
    "AutoComposition",
    "AutoDecision",
    "AutoRouter",
    "AutoTurnRefused",
    "ClassifierOutcome",
    "Escalation",
    "StopSet",
    "auto_router",
    "classifier_not_installed",
    "compose_auto_composition",
]

TIERS: tuple[Tier, ...] = ("easy", "medium", "complex")
"""The classifier's tiers, lowest first; each maps to the implementer role of the same name. Routing up never leaves
them: past complex comes the default planner (v9 Design 4)."""

FailureKind = Literal["timeout", "invalid_answer", "abstention", "stopped_classifier", "error"]
"""Why the classifier gave no tier. ``error`` is the host's own label for an exception the backend did not map."""


class AutoTurnRefused(Exception):
    """An Auto turn refused recoverably before any answer call: the thread stays open and nothing is dispatched."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class StopSet:
    """The launch's models proven stopped (v9 Design 1), shared by every session: only added to, never cleared."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._models: set[str] = set()

    def add(self, model_id: str) -> None:
        with self._lock:
            self._models.add(model_id)

    def __contains__(self, model_id: object) -> bool:
        with self._lock:
            return model_id in self._models


@dataclass(frozen=True, slots=True)
class ClassifierOutcome:
    """The classifier's answer. ``tier`` is already confidence-adjusted by the backend, which routes a low-confidence
    answer up once; the resolver never adjusts it again. ``tier`` None is a failure (``failure_kind`` says which)."""

    tier: Tier | None
    confidence_band: str
    routed_up_for_confidence: bool = False
    failure_kind: FailureKind | None = None


Classifier = Callable[[ClassifierInput, StopSet], ClassifierOutcome]


def classifier_not_installed(contract: ClassifierInput, stops: StopSet) -> ClassifierOutcome:
    """The interim classifier, never shipped (Task 4 note r3): until H's backend (Task 5) is installed, every Auto turn
    is refused recoverably with no dispatch and no paid call. It never enters the classifier-failure fallback."""
    del contract, stops
    raise AutoTurnRefused("CLASSIFIER_NOT_INSTALLED")


@dataclass(frozen=True, slots=True)
class Escalation:
    """One availability route-up: the tier left, and whether its role had no eligible model or only stopped ones."""

    from_tier: Tier
    reason: Literal["empty", "stopped"]


@dataclass(frozen=True, slots=True)
class AutoDecision:
    """One turn's routing, frozen when it is bound and handed to Task 5's record and notice."""

    classifier_tier: Tier | None
    confidence_band: str
    routed_up_for_confidence: bool
    failure_kind: FailureKind | None
    escalations: tuple[Escalation, ...]
    default_fallback: bool
    tier: Tier
    role: str
    model_id: str


@dataclass(frozen=True)
class AutoComposition:
    """The approved Auto registry for this launch."""

    snapshot: RegistrySnapshot

    def default_model(self) -> str:
        """ADR-023's default planner computed in the Auto registry: the strict auth probe's model, and the last fallback
        when no tier at or above a turn's is routable. Computed from configuration, never pinned."""
        return default_agent_model(self.snapshot)


def compose_auto_composition(*, approved_literal: str | None, composition: str | None) -> AutoComposition:
    """The Auto composition. ``approved_literal`` and ``composition`` are what the authorized candidate digested; a
    launch whose approval did not bind the Auto composition, or whose recomposed literal differs, is refused."""
    if composition != AUTO_COMPOSITION:
        raise BindingError("AUTO_NOT_APPROVED", "the authorized launch did not bind the Auto composition")
    snapshot = auto_snapshot()
    if snapshot is None or approved_literal != approval_literal(snapshot):
        raise BindingError("AUTO_NOT_APPROVED", "the composed Auto registry is not the one the authorized launch digested")
    return AutoComposition(snapshot=snapshot)


@dataclass(frozen=True)
class AutoRouter:
    """The launch's immutable Auto state: the snapshot, one route policy per (model, role), one context attachment per
    model (none when the launch is absent-engine), the stop set and the classifier."""

    snapshot: RegistrySnapshot
    default_model: str
    default_role: str
    route_policies: Mapping[tuple[str, str], RoutePolicy]
    attachments: Mapping[str, ContextAttachment]
    stops: StopSet
    classifier: Classifier

    @property
    def base_attachment(self) -> ContextAttachment | None:
        """What new sessions take their storage class and initial strategy from: the default planner's attachment."""
        return self.attachments.get(self.default_model)

    def classify(self, contract: ClassifierInput) -> ClassifierOutcome:
        """Synchronous: the host calls it in the turn's worker, never on the event loop."""
        return self.classifier(contract, self.stops)

    def resolve(self, outcome: ClassifierOutcome) -> AutoDecision:
        """The turn's model (v9 Design 4). A failure counts as a medium abstention routed up, so it starts at complex.
        An empty or fully stopped role routes up a tier at a time; with none left, the default planner if it has not
        stopped; otherwise :class:`AutoTurnRefused`."""
        failure_kind = outcome.failure_kind or (None if outcome.tier is not None else "abstention")
        start: Tier = outcome.tier if outcome.tier is not None else "complex"
        escalations: list[Escalation] = []

        def decision(tier: Tier, model_id: str, *, role: str, default_fallback: bool) -> AutoDecision:
            return AutoDecision(
                classifier_tier=outcome.tier,
                confidence_band=outcome.confidence_band,
                routed_up_for_confidence=outcome.routed_up_for_confidence,
                failure_kind=failure_kind,
                escalations=tuple(escalations),
                default_fallback=default_fallback,
                tier=tier,
                role=role,
                model_id=model_id,
            )

        for tier in TIERS[TIERS.index(start) :]:
            eligible = select_eligible_models(self.snapshot, Role(tier))
            routable = [model_id for model_id in eligible if model_id not in self.stops]
            if routable:
                return decision(tier, routable[0], role=tier, default_fallback=False)
            escalations.append(Escalation(from_tier=tier, reason="stopped" if eligible else "empty"))
        if self.default_model not in self.stops:
            # The default planner is a medium or easy model (agent/defaults.py), so its role is also a tier.
            default_tier: Tier = "medium" if self.default_role == "medium" else "easy"
            return decision(default_tier, self.default_model, role=self.default_role, default_fallback=True)
        raise AutoTurnRefused("AUTO_NO_ROUTABLE_MODEL")

    def route_policy(self, decision: AutoDecision) -> RoutePolicy:
        return self.route_policies[(decision.model_id, decision.role)]

    def attachment_for(self, model_id: str) -> ContextAttachment | None:
        return self.attachments.get(model_id)


def auto_router(
    composition: AutoComposition,
    *,
    gateway_client: Any,
    shared_secret: str,
    attempt_observer: Any,
    classifier: Classifier = classifier_not_installed,
) -> AutoRouter:
    """Build the launch's Auto state once, from the approved snapshot: every route policy and attachment a turn can
    select is constructed (and so validated) here, before the server starts."""
    snapshot = composition.snapshot
    output_cap = snapshot.policy.output_reserve_tokens.get("implementer")
    if output_cap is None:
        raise RouteIdentityError("the trusted registry states no implementer output reserve")
    key = disclosure_key(shared_secret)
    default_model = composition.default_model()
    default_role = implementer_role(snapshot, default_model).value
    pairs: set[tuple[str, str]] = {(model_id, tier) for tier in TIERS for model_id in select_eligible_models(snapshot, Role(tier))}
    pairs.add((default_model, default_role))
    policies = {
        (model_id, role): RoutePolicy(snapshot=snapshot, disclosure_key=key, model_id=model_id, role=role, output_cap=output_cap)
        for model_id, role in pairs
    }
    base = ordinary_attachment(
        snapshot=snapshot, model_id=default_model, gateway_client=gateway_client, shared_secret=shared_secret, attempt_observer=attempt_observer
    )
    attachments: dict[str, ContextAttachment] = {}
    if base is not None:
        for model_id in {model_id for model_id, _ in pairs}:
            limits = attachment_limits(snapshot, model_id)
            attachments[model_id] = replace(
                base,
                model_id=model_id,
                parameters=limits.parameters,
                limits=limits.limits,
                usable_input_tokens=limits.usable_input_tokens,
                estimate_request=limits.estimate_request,
            )
    return AutoRouter(
        snapshot=snapshot,
        default_model=default_model,
        default_role=default_role,
        route_policies=policies,
        attachments=attachments,
        stops=StopSet(),
        classifier=classifier,
    )
