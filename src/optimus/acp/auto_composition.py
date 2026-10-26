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
    "ClassificationAccountingError",
    "ClassifierCall",
    "ClassifierHalted",
    "ClassifierOutcome",
    "Escalation",
    "StopSet",
    "auto_router",
    "compose_auto_composition",
    "notice_text",
    "routing_record",
]

TIERS: tuple[Tier, ...] = ("easy", "medium", "complex")
"""The classifier's tiers, lowest first; each maps to the implementer role of the same name. Routing up never leaves
them: past complex comes the default planner (v9 Design 4)."""

FailureKind = Literal["timeout", "invalid_answer", "abstention", "stopped_classifier", "error"]
"""Why the classifier gave no tier. ``error`` is the host's own label for an exception the backend did not map."""

AnsweredBy = Literal["rules", "classifier"]
"""Which part of H answered: its rules, or its classifier model (Plan 12.4 Task 5)."""


class AutoTurnRefused(Exception):
    """An Auto turn refused recoverably before any answer call: the thread stays open and nothing is dispatched."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ClassifierHalted(Exception):
    """The classifier's dispatch lease was refused: the turn was cancelled or torn down before its classifier call was
    sent (Plan 12.4 Task 5). The host ends the turn as for any cancel during classification."""


class ClassificationAccountingError(Exception):
    """A classifier attempt could not be accounted for: its report could not be attributed, or the turn's receipt sink
    refused a receipt (Plan 12.4 Task 5). The turn is refused with ACCOUNTING_INTEGRITY, never routed by the failure
    rule. The first original error is chained."""


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
    predicted_tier: Tier | None = None
    """The answer's tier before the confidence route-up; None on a failure."""
    answered_by: AnsweredBy | None = None


@dataclass(frozen=True, slots=True)
class ClassifierCall:
    """One turn's context for its classifier call (Plan 12.4 Task 5), captured before the turn's first await: where its
    receipts go, how an integrity failure is reported, and the turn's control for the dispatch lease."""

    session_id: str
    turn_seq: int
    run_id: str
    record_receipt: Callable[[Any], None]
    integrity_failure: Callable[[str], None]
    operation_control: Any


Classifier = Callable[[ClassifierInput, StopSet, ClassifierCall], ClassifierOutcome]


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
    predicted_tier: Tier | None = None
    answered_by: AnsweredBy | None = None


_FAILURE_WORDS: dict[str, str] = {
    "timeout": "timeout",
    "invalid_answer": "invalid answer",
    "abstention": "no confident answer",
    "stopped_classifier": "it has stopped for this launch",
    "error": "error",
}
_ESCALATION_WORDS: dict[str, str] = {"stopped": "stopped", "empty": "none configured"}


def notice_text(decision: AutoDecision) -> str:
    """The turn's one Auto line (Plan 12.4 Task 5), for example ``Auto: medium → google/gemini-3.8-flash``, with why it
    is not simply the classifier's tier when it is not."""
    reasons: list[str] = []
    if decision.failure_kind is not None:
        reasons.append(f"the classifier failed: {_FAILURE_WORDS[decision.failure_kind]}")
    elif decision.routed_up_for_confidence and decision.predicted_tier is not None:
        reasons.append(f"unsure, so one tier up from {decision.predicted_tier}")
    reasons += [f"no {e.from_tier} model available: {_ESCALATION_WORDS[e.reason]}" for e in decision.escalations]
    if decision.default_fallback:
        reasons.append("the default model: no tier was available")
    return f"Auto: {decision.tier} → {decision.model_id}" + (f" ({'; '.join(reasons)})" if reasons else "")


def routing_record(
    disposition: Literal["routed", "refused", "cancelled", "abandoned"],
    *,
    outcome: ClassifierOutcome | None,
    decision: AutoDecision | None = None,
    reason: str | None = None,
    classifier_attempt: str | None = None,
    notice_delivered: bool = False,
) -> dict[str, Any]:
    """One admitted Auto turn's content-free routing record (Plan 12.4 Task 5): the classifier facts it obtained and,
    once bound, its route; null where unknown. Never a prompt, contract, answer text or confidence value."""
    facts: AutoDecision | ClassifierOutcome | None = decision if decision is not None else outcome
    return {
        "arm": "H",
        "disposition": disposition,
        "reason": reason,
        "answered_by": None if facts is None else facts.answered_by,
        "predicted_tier": None if facts is None else facts.predicted_tier,
        "classifier_tier": decision.classifier_tier if decision is not None else None if outcome is None else outcome.tier,
        "confidence_band": None if facts is None else facts.confidence_band,
        "routed_up_for_confidence": None if facts is None else facts.routed_up_for_confidence,
        "failure_kind": None if facts is None else facts.failure_kind,
        "classifier_attempt": classifier_attempt,
        "escalations": None if decision is None else [{"from_tier": e.from_tier, "reason": e.reason} for e in decision.escalations],
        "default_fallback": None if decision is None else decision.default_fallback,
        "tier": None if decision is None else decision.tier,
        "role": None if decision is None else decision.role,
        "model_id": None if decision is None else decision.model_id,
        "notice_delivered": notice_delivered,
    }


@dataclass(frozen=True)
class AutoComposition:
    """The approved Auto registry for this launch."""

    snapshot: RegistrySnapshot

    def default_model(self) -> str:
        """ADR-023's default planner computed in the Auto registry: the strict auth probe's model, and the last fallback
        when no tier at or above a turn's is routable. Computed from configuration, never pinned."""
        return default_agent_model(self.snapshot)

    def classifier_model(self) -> str:
        """The classifier role's first eligible model: configuration, never pinned (Plan 12.4 Task 5). Refused when the role
        is empty, or when the model needs a Contributor disclosure, which the decision route cannot verify."""
        eligible = select_eligible_models(self.snapshot, Role.CLASSIFIER)
        if not eligible:
            raise BindingError("AUTO_CLASSIFIER_MISSING", "the Auto composition assigns no eligible classifier")
        if self.snapshot.policy.models[eligible[0]].data_use.disclosure == "contributor":
            raise BindingError("AUTO_CLASSIFIER_DISCLOSURE_UNSUPPORTED", "the classifier needs a disclosure the decision route cannot verify")
        return eligible[0]


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

    def classify(self, contract: ClassifierInput, call: ClassifierCall) -> ClassifierOutcome:
        """Synchronous: the host calls it in the turn's worker, never on the event loop."""
        return self.classifier(contract, self.stops, call)

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
                predicted_tier=outcome.predicted_tier,
                answered_by=outcome.answered_by,
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
    classifier: Classifier | None = None,
) -> AutoRouter:
    """Build the launch's Auto state once, from the approved snapshot: every route policy and attachment a turn can
    select is constructed (and so validated) here, before the server starts. ``classifier`` None installs H's backend
    (``auto_hybrid``) for the composition's classifier model; tests inject their own."""
    snapshot = composition.snapshot
    classifier_model = composition.classifier_model()
    if classifier is None:
        from optimus.acp.auto_hybrid import HybridClassifier  # its seam types are defined here

        classifier = HybridClassifier(snapshot=snapshot, gateway_client=gateway_client, model_id=classifier_model)
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
    # One stop set for the launch: the resolver, the runner and the summarizer share it (one model, one stop).
    stops = StopSet()
    base = ordinary_attachment(
        snapshot=snapshot,
        model_id=default_model,
        gateway_client=gateway_client,
        shared_secret=shared_secret,
        attempt_observer=attempt_observer,
        model_stops=stops,
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
        stops=stops,
        classifier=classifier,
    )
