"""Arm H, Auto mode's production classifier: its rules first, its classifier model only when they are unsure (Plan 12.4
v9 Design 4; ADR-027; the Task 5 implementation note r3, accepted by Codex round 67).

Every number and text below is frozen from the pilot's ``frozen-1`` (review kit ``task3/runs/frozen-1/frozen.json``,
SHA-256 ``0a16c2ef0ddd4448...``) and the pilot's ``arms.py``: the rules, their cut points 0.5 and 4.5, the rules'
answering confidence 0.8, the classifier's ``choice`` question, and the route-up threshold 0.95 on the final answer.
A new value is a new judge and needs its own decision (v9 Design 5; #426); the model itself is configuration.

One production correction to the pilot, approved in Codex round 62: the classifier's confidence must be a finite
number in [0, 1]; a missing or malformed one is an abstention, not a confident answer.
"""

from __future__ import annotations

import json
import math
import re
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from optimus.acp.auto_composition import (
    AnsweredBy,
    ClassificationAccountingError,
    ClassifierCall,
    ClassifierHalted,
    ClassifierOutcome,
    FailureKind,
    StopSet,
)
from optimus.agent.auto_contract import PROMPT_EXCERPT_MAX_BYTES, ClassifierInput, Tier
from optimus.gateway.attempts import (
    AttemptIntegrityError,
    ProviderAttempt,
    attempts_from_decision,
    attempts_from_failure,
    stops_experimental_route,
)
from optimus.gateway.errors import GatewayHttpError, GatewayResponseError
from optimus.gateway.models import GatewayDecision
from optimus.gateway.route_binding import registry_route_identity
from optimus.usage.turn_settlement import StageReceipt
from optimus_model_policy import RegistrySnapshot, decision_payload_text, estimate_decision
from optimus_model_policy.binding import RouteBinding
from optimus_model_policy.experimental import experimental_route
from optimus_model_policy.registry import CLASSIFIER_REQUEST_BOUND_TOKENS

__all__ = ["QUESTIONS", "HybridClassifier", "predict_rules", "route_up", "rule_score"]

TIERS: tuple[Tier, ...] = ("easy", "medium", "complex")
CUT_MEDIUM = 0.5
CUT_COMPLEX = 4.5
RULE_CONFIDENCE = 0.8
ROUTE_UP_THRESHOLD = 0.95

_CRITERIA = {
    "easy": "One file, explicit and mechanical.",
    "medium": "Two to five files or one module, or a bounded investigation.",
    "complex": "Crosses modules, open-ended debugging, or touches security, data or concurrency.",
}
_INSTRUCTIONS = "Which tier of coding model does this request to a coding agent need?"
QUESTIONS: dict[str, Any] = {"tier": {"type": "choice", "instructions": _INSTRUCTIONS, "criteria": _CRITERIA}}
"""The classifier's frozen question: the pilot's ``choice`` variant."""

# --- The rules, verbatim from the pilot's arms.py (generic signals written before the split; only the cuts were tuned).

_COMPLEX = re.compile(
    r"\b(secur\w*|auth\w*|credential\w*|secret\w*|password\w*|token\w*|encrypt\w*|permission\w*|vulnerab\w*|inject\w*|"
    r"migrat\w*|schema|database|drop|delete\w* (?:all|the|every)|data loss|concurren\w*|thread\w*|race|deadlock\w*|async\w*|"
    r"lock\w*|flak\w*|intermittent\w*|leak\w*|architect\w*|redesign\w*|across (?:the )?(?:codebase|modules|services)|"
    r"whole (?:codebase|repo\w*|project)|production|deploy\w*|rotate|rollback|corrupt\w*)\b",
    re.IGNORECASE,
)
_MEDIUM = re.compile(
    r"\b(debug\w*|investigat\w*|why|error\w*|exception\w*|traceback|fail\w*|crash\w*|bug\w*|regress\w*|implement\w*|"
    r"add (?:a |an )?(?:feature|support|option)|integrat\w*|refactor\w*|module|tests?|review\w*|wrong|unexpected\w*|broken)\b",
    re.IGNORECASE,
)
_EASY = re.compile(
    r"\b(rename|typo\w*|comment\w*|docstring\w*|format\w*|lint\w*|bump|spelling|one[- ]line|what does|explain|readme|"
    r"print|log message|whitespace)\b",
    re.IGNORECASE,
)
_PATH = re.compile(r"[\w./\\-]+\.(?:py|js|ts|tsx|jsx|java|go|rs|rb|cs|cpp|c|h|kt|swift|md|yaml|yml|json|toml|sql|sh)\b")


def rule_score(state: dict[str, Any]) -> float:
    text = state["prompt"]
    score = 2.0 * min(len(set(m.lower() for m in _COMPLEX.findall(text))), 2)
    score += 1.0 * min(len(set(m.lower() for m in _MEDIUM.findall(text))), 2)
    score -= 1.0 * min(len(set(m.lower() for m in _EASY.findall(text))), 2)
    paths = {m.lower() for m in _PATH.findall(text)}
    files = len(paths) + state["attachments"]["count"]
    score += 1.0 if files >= 3 else 0.0
    score += 1.0 if files >= 6 else 0.0
    score += 0.5 if state["truncated"] else 0.0
    if state["previous_tier"] is not None and len(text) < 80:
        score = {"easy": 0.0, "medium": 2.0, "complex": 4.0}[state["previous_tier"]]  # a short continuation keeps its tier
    return score


def predict_rules(state: dict[str, Any]) -> tuple[Tier, float]:
    """Tier by the two frozen cut points; confidence is the distance to the nearest cut, capped at 1."""
    score = rule_score(state)
    tier: Tier = "easy" if score < CUT_MEDIUM else "medium" if score < CUT_COMPLEX else "complex"
    margin = min(abs(score - CUT_MEDIUM), abs(score - CUT_COMPLEX))
    return tier, min(1.0, margin / 2.0)


def route_up(tier: Tier, confidence: float) -> tuple[Tier, bool]:
    """The pilot's route-up (``metrics.route``) on a valid answer: below the threshold, one tier up. Complex stays
    complex and is not counted as routed up."""
    rank = TIERS.index(tier)
    if confidence < ROUTE_UP_THRESHOLD:
        return TIERS[min(rank + 1, 2)], rank < 2
    return tier, False


def _answer(tier: Tier, confidence: float, answered_by: AnsweredBy) -> ClassifierOutcome:
    final, routed_up = route_up(tier, confidence)
    band = "high" if confidence >= ROUTE_UP_THRESHOLD else "low"
    return ClassifierOutcome(
        tier=final, confidence_band=band, routed_up_for_confidence=routed_up, predicted_tier=tier, answered_by=answered_by
    )


def _failure(kind: FailureKind) -> ClassifierOutcome:
    return ClassifierOutcome(tier=None, confidence_band="none", failure_kind=kind)


def _cut(text: str, budget: int) -> str:
    """The contract's own excerpt rule: a UTF-8 prefix cut on a character boundary."""
    return text.encode("utf-8")[:budget].decode("utf-8", errors="ignore")


_NOT_SENT = ProviderAttempt(number=1, outcome="not_sent", cost_usd=Decimal("0"))
_OPERATION = "classification:1:1"


class HybridClassifier:
    """H's backend for one launch: the frozen rules, then one decision from the classifier model through the Gateway."""

    def __init__(self, *, snapshot: RegistrySnapshot, gateway_client: Any, model_id: str) -> None:
        entry = snapshot.policy.models[model_id]
        windows = [endpoint.context_window_tokens for endpoint in entry.route.endpoints if endpoint.context_window_tokens is not None]
        self._snapshot = snapshot
        self._client = gateway_client
        self._model = model_id
        self._identity = registry_route_identity(snapshot, model_id=model_id, role="classifier")
        self._experimental = experimental_route(snapshot, model_id) is not None
        self._profile = snapshot.policy.estimators[entry.route.estimator]
        # The Gateway's own bound for this request (``admit_decision``): the classifier bound or the route's window.
        self._bound = min(CLASSIFIER_REQUEST_BOUND_TOKENS, *windows)

    def __call__(self, contract: ClassifierInput, stops: StopSet, call: ClassifierCall) -> ClassifierOutcome:
        tier, confidence = predict_rules(json.loads(contract.to_json()))
        if confidence >= RULE_CONFIDENCE:
            return _answer(tier, confidence, "rules")
        if self._model in stops:
            return _failure("stopped_classifier")
        state = self._fit(contract)
        if state is None:
            return _failure("error")  # no excerpt fits the bound: refused here, before any call
        decision, failure = self._decide(state, stops, call)
        if failure is not None:
            stopped = self._model in stops
            if stopped:
                return _failure("stopped_classifier")
            # A transport loss (the client's own `transport` failure, or an exception outside the Gateway's types) is a
            # timeout; a Gateway refusal or a reply the client could not read is an error.
            transport = not isinstance(failure, (GatewayHttpError, GatewayResponseError)) or (
                isinstance(failure, GatewayHttpError) and (failure.failure or {}).get("kind") == "transport"
            )
            return _failure("timeout" if transport else "error")
        assert decision is not None
        answer = (decision.answers or {}).get("tier")
        choice = answer.get("choice") if isinstance(answer, dict) else None
        if choice not in TIERS:
            return _failure("invalid_answer")  # defensive: the Gateway's upstream parser already refuses a bad choice
        value = answer.get("confidence") if isinstance(answer, dict) else None
        # The host's client decodes JSON numbers with a fraction as Decimal; an integer 0 or 1 arrives as int.
        if not isinstance(value, (int, float, Decimal)) or isinstance(value, bool) or not math.isfinite(value) or not 0 <= value <= 1:
            return _failure("abstention")  # Codex round 62: a missing or malformed confidence is an abstention
        return _answer(choice, float(value), "classifier")

    def _fit(self, contract: ClassifierInput) -> dict[str, Any] | None:
        """The contract's state, its excerpt shrunk by the overflow until the complete typed request fits the Gateway's
        bound by the route's own estimator (the pilot's fit rule); None when nothing fits."""
        budget = PROMPT_EXCERPT_MAX_BYTES
        excerpt = contract.prompt
        while True:
            state = json.loads(contract.to_json())
            overflow = estimate_decision(self._model, decision_payload_text(state, QUESTIONS), self._profile).tokens - self._bound
            if overflow <= 0:
                return state
            budget -= overflow  # one estimated token per byte at most: shrinking by the overflow is enough or more
            if budget <= 0:
                return None
            # Cutting the 4 KB excerpt equals cutting the original prompt at any budget up to 4 KB; the flag follows the
            # pilot's rule (the original was longer than the budget).
            contract = replace(contract, prompt=_cut(excerpt, budget), truncated=contract.truncated or len(excerpt.encode("utf-8")) > budget)

    def _decide(self, state: dict[str, Any], stops: StopSet, call: ClassifierCall) -> tuple[GatewayDecision | None, BaseException | None]:
        """One decision, under the turn's dispatch lease; its attempts accounted, and a proven stop recorded, whatever
        happens. Raises :class:`ClassifierHalted` when the lease is refused and :class:`ClassificationAccountingError`
        when an attempt cannot be accounted for (which takes precedence)."""
        from optimus.acp.lifecycle import DirectiveKind

        control = call.operation_control
        base = f"{call.run_id}:classification:1:1"
        control.register_operations([(DirectiveKind.GATEWAY, _OPERATION)])
        if not control.try_start(DirectiveKind.GATEWAY, _OPERATION).granted:
            self._account(call, base, (_NOT_SENT,))
            raise ClassifierHalted()
        request_id = f"{call.session_id}:{call.turn_seq}:classification:1:{uuid.uuid4().hex}"
        binding = RouteBinding(registry_hash=self._snapshot.effective_hash, request_id=request_id, output_cap=0)
        decision: GatewayDecision | None = None
        failure: BaseException | None = None
        attempts: tuple[ProviderAttempt, ...] | None = None
        try:
            try:
                decision = self._client.create_decision(model=self._model, state=state, questions=QUESTIONS, route_binding=binding)
            except Exception as exc:  # noqa: BLE001 - every failure is classified; transport loss stays unknown
                failure = exc
            attempts = self._account(call, base, None, decision=decision, failure=failure)
        finally:
            if failure is not None and stops_experimental_route(failure, experimental=self._experimental):
                stops.add(self._model)
            unknown = attempts is None or any(attempt.cost_usd is None for attempt in attempts)
            control.complete_directive(DirectiveKind.GATEWAY, _OPERATION, "succeeded" if decision is not None else "cost_unknown" if unknown else "failed")
        return decision, failure

    def _account(
        self,
        call: ClassifierCall,
        base: str,
        attempts: tuple[ProviderAttempt, ...] | None,
        *,
        decision: GatewayDecision | None = None,
        failure: BaseException | None = None,
    ) -> tuple[ProviderAttempt, ...]:
        """Offer every attempt's receipt; on any failure tell the turn and raise :class:`ClassificationAccountingError`."""
        errors: list[BaseException] = []
        if attempts is None:
            try:
                attempts = attempts_from_decision(decision) if decision is not None else attempts_from_failure(failure or RuntimeError())
            except AttemptIntegrityError as error:
                errors.append(error)
                attempts = error.attempts
        post_teardown = bool(call.operation_control.transport_abandoned())
        for attempt in attempts:
            try:
                call.record_receipt(self._receipt(call, base, attempt, post_teardown=post_teardown))
            except Exception as error:  # noqa: BLE001 - every receipt is offered first
                errors.append(error)
        if errors:
            call.integrity_failure(call.run_id)
            raise ClassificationAccountingError("a classifier attempt could not be accounted for") from errors[0]
        return attempts

    def _receipt(self, call: ClassifierCall, base: str, attempt: ProviderAttempt, *, post_teardown: bool) -> StageReceipt:
        identity = self._identity
        return StageReceipt(
            session_id=call.session_id,
            turn_id=call.run_id,
            stage="classification",
            # As the runner numbers them: a routed attempt within its request; unattributed usage keyed `usage`.
            attempt_id=f"{base}:{attempt.key}" if attempt.routed or attempt.outcome == "unattributed" else base,
            gateway_request_id=attempt.gateway_request_id,
            outcome=attempt.outcome,
            reported_cost_usd=attempt.cost_usd,
            recorded_at=datetime.now(tz=UTC),
            requested_model=identity.model_id,
            role=identity.role,
            route=identity.route,
            reasoning=identity.reasoning,
            quantizations=identity.quantizations,
            registry_hash=identity.registry_hash,
            provider_request_id=attempt.provider_request_id,
            http_status=attempt.http_status,
            gateway_usage=attempt.gateway_usage,
            post_teardown=post_teardown,
        )
