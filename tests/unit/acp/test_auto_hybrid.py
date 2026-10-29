"""Plan 12.4 Task 5: H's production backend (ADR-028; the Task 5 implementation note r3, accepted by Codex round 67).

H's rules answer when they are confident; otherwise the classifier model answers through the real Gateway decision
route (``handle_decision_request``) behind a ``GatewayClient`` transport. The System One provider is scripted, but its
replies pass the real upstream parser, so a reply the Gateway refuses is refused here exactly as in production. The
registry is the real approved Auto composition. No network or paid call is made.
"""

from __future__ import annotations

import json
import math
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from optimus.acp import auto_hybrid
from optimus.acp.auto_composition import AutoComposition, ClassificationAccountingError, ClassifierCall, ClassifierHalted, StopSet
from optimus.acp.auto_hybrid import QUESTIONS, HybridClassifier, predict_rules, route_up
from optimus.acp.lifecycle import TurnControl
from optimus.agent.auto_contract import build_classifier_input
from optimus.gateway.attempts import attempts_from_failure, is_preflight_refusal, stops_experimental_route
from optimus.gateway.client import _route_attempts_dropped, _try_parse_error_correlation, _try_parse_error_usage
from optimus.gateway.errors import GatewayHttpError, GatewayResponseError
from optimus.gateway.models import GatewayDecision, GatewayRouteAttempt, GatewayUsage, parse_decision_response
from optimus.usage.turn_settlement import ReceiptConflictError, StageReceipt, TurnSettlement
from optimus_gateway.decisions import handle_decision_request
from optimus_gateway.upstream_client import UpstreamAttemptFailure
from optimus_gateway.upstream_client import parse_decision_response as parse_system_one
from optimus_model_policy import decision_payload_text, estimate_decision
from optimus_model_policy.binding import ATTEMPT_UNCERTAIN, BindingError, auto_snapshot, packaged_defaults
from optimus_model_policy.registry import CLASSIFIER_REQUEST_BOUND_TOKENS, load_registry
from tests.unit.agent.test_route_binding import _client
from tests.unit.optimus_gateway.model_policy_support import gateway_config, model_policy
from tests.unit.optimus_gateway.test_decisions import CLASSIFIER_OVERRIDE

JEV = "typesafe/jev-1.14"
SURE = "Fix the typo in the README."  # the rules: easy, confidence 1.0
UNSURE = "Debug the failing test."  # the rules: medium, confidence 0.75, so the classifier answers


@pytest.fixture
def snapshot():
    approved = auto_snapshot()
    assert approved is not None
    return approved


def system_one(choice: Any = "medium", confidence: Any = 0.97, *, drop_confidence: bool = False) -> dict[str, Any]:
    """A raw System One reply, as the provider sends it."""
    answer: dict[str, Any] = {"type": "choice", "choice": choice}
    if not drop_confidence:
        answer["confidence"] = confidence
    return {
        "id": "gen-dec-1",
        "model": JEV + "-20261014",
        "provider": "TypeSafe",
        "answers": {"tier": answer},
        "usage": {"cost": "0.0000042", "input_tokens": 100, "output_tokens": 0},
    }


class SystemOne:
    """The provider behind the real Gateway: each reply passes the real upstream parser, which refuses what it cannot
    verify as an uncertain attempt, exactly as ``create_decision_once`` does."""

    def __init__(self, *replies: dict[str, Any] | BaseException) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def create_decision_once(self, *, model: str, state: Any, questions: Any, provider_controls: Any) -> Any:
        self.calls.append({"model": model, "state": state, "questions": questions})
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        try:
            return parse_system_one(json.loads(json.dumps(reply)), questions=questions)
        except (UnicodeError, ValueError, RuntimeError) as exc:
            raise UpstreamAttemptFailure(ATTEMPT_UNCERTAIN, failure={"kind": "unreadable"}) from exc


class DecisionGateway:
    """A `GatewayTransport` that hands each decision request to the real Gateway handler and turns its error replies
    into the same `GatewayHttpError` the urllib transport raises."""

    def __init__(self, snapshot: Any, upstream: SystemOne) -> None:
        self.config = gateway_config(model_policy(snapshot))
        self.upstream = upstream
        self.payloads: list[dict[str, Any]] = []

    def post_json(self, request: Any) -> dict[str, Any]:
        assert request.url.endswith("/v1/decisions")
        self.payloads.append(request.payload)
        status, body = handle_decision_request(
            authorization_header=request.headers.get("Authorization"), request_body=request.payload, config=self.config, upstream_client=self.upstream
        )
        detail = json.dumps(body, default=str)
        if status != 200:
            code, retryable, attempts = _try_parse_error_correlation(detail)
            raise GatewayHttpError(
                status, detail, gateway_usage=_try_parse_error_usage(detail), gateway_code=code, retryable=retryable,
                route_attempts=attempts, route_attempts_malformed=_route_attempts_dropped(detail, attempts),
            )  # fmt: skip
        return json.loads(detail, parse_float=Decimal)


class Turn:
    """One turn's real control and settlement, and the call H receives."""

    def __init__(self, *, receipts: Any = None) -> None:
        self.control = TurnControl(session_id="s", turn_seq=1)
        self.settlement = TurnSettlement()
        self.integrity: list[str] = []
        self.call = ClassifierCall(
            session_id="s",
            turn_seq=1,
            run_id="s:1",
            record_receipt=receipts or self.settlement.record_attempt,
            integrity_failure=self.integrity.append,
            operation_control=self.control,
        )

    def receipts(self) -> list[StageReceipt]:
        return list(self.settlement.receipts("s:1"))


def _h(snapshot: Any, *replies: Any) -> tuple[HybridClassifier, SystemOne, DecisionGateway]:
    upstream = SystemOne(*replies)
    gateway = DecisionGateway(snapshot, upstream)
    return HybridClassifier(snapshot=snapshot, gateway_client=_client(gateway), model_id=JEV), upstream, gateway


def _contract(prompt: str, **extra: Any) -> Any:
    return build_classifier_input(prompt, mode="AGENT", **extra)


# --- The frozen settings ---------------------------------------------------------------------------------------------


def test_the_frozen_settings_are_h_as_accepted() -> None:
    assert (auto_hybrid.CUT_MEDIUM, auto_hybrid.CUT_COMPLEX, auto_hybrid.RULE_CONFIDENCE, auto_hybrid.ROUTE_UP_THRESHOLD) == (0.5, 4.5, 0.8, 0.95)
    assert QUESTIONS["tier"]["type"] == "choice" and list(QUESTIONS["tier"]["criteria"]) == ["easy", "medium", "complex"]
    assert predict_rules(json.loads(_contract(SURE).to_json())) == ("easy", 1.0)
    assert predict_rules(json.loads(_contract(UNSURE).to_json())) == ("medium", 0.75)
    # Under the frozen cuts a short continuation of a complex turn scores 4.0: medium at confidence 0.25, so the
    # classifier decides it (the pilot's own self-check used other cuts).
    assert predict_rules(json.loads(_contract("ok go ahead", previous_tier="complex").to_json())) == ("medium", 0.25)


def test_the_route_up_is_the_pilots_including_its_boundaries() -> None:
    assert route_up("easy", 0.95) == ("easy", False)
    assert route_up("easy", 0.9499) == ("medium", True)
    assert route_up("medium", 0.5) == ("complex", True)
    assert route_up("complex", 0.1) == ("complex", False), "complex stays complex and is not counted as routed up"


# --- The decision path -----------------------------------------------------------------------------------------------


def test_a_rules_confident_turn_makes_no_call(snapshot) -> None:
    h, upstream, _ = _h(snapshot)
    turn = Turn()
    outcome = h(_contract(SURE), StopSet(), turn.call)
    assert (outcome.tier, outcome.answered_by, outcome.confidence_band, outcome.predicted_tier) == ("easy", "rules", "high", "easy")
    assert upstream.calls == [] and turn.receipts() == []


def test_an_unsure_turn_asks_the_classifier_once_with_the_frozen_question_and_binding(snapshot) -> None:
    h, upstream, gateway = _h(snapshot, system_one("medium", 0.97))
    turn = Turn()
    contract = _contract(UNSURE)
    outcome = h(contract, StopSet(), turn.call)

    assert (outcome.tier, outcome.answered_by, outcome.confidence_band, outcome.routed_up_for_confidence) == ("medium", "classifier", "high", False)
    [payload] = gateway.payloads
    assert payload["model"] == JEV and payload["questions"] == QUESTIONS and payload["state"] == json.loads(contract.to_json())
    binding = payload["route_binding"]
    assert binding["output_cap"] == 0 and binding["registry_hash"] == snapshot.effective_hash
    assert binding["request_id"].startswith("s:1:classification:1:")
    [receipt] = turn.receipts()
    assert (receipt.stage, receipt.outcome, receipt.requested_model, receipt.role) == ("classification", "completed", JEV, "classifier")
    assert receipt.reported_cost_usd == Decimal("0.0000042")
    assert len(upstream.calls) == 1


@pytest.mark.parametrize(
    ("choice", "confidence", "expected"),
    [("medium", 0.9, ("complex", True, "low")), ("complex", 0.2, ("complex", False, "low")), ("easy", 0.95, ("easy", False, "high"))],
    ids=["low-routes-up", "low-complex-stays", "boundary-holds"],
)
def test_the_classifiers_confidence_routes_up_once(snapshot, choice: str, confidence: float, expected: tuple[str, bool, str]) -> None:
    h, _, _ = _h(snapshot, system_one(choice, confidence))
    outcome = h(_contract(UNSURE), StopSet(), Turn().call)
    assert (outcome.tier, outcome.routed_up_for_confidence, outcome.confidence_band) == expected
    assert outcome.predicted_tier == choice


@pytest.mark.parametrize(("rules", "calls"), [(0.8, 0), (0.7999, 1)], ids=["at-0.8-the-rules-answer", "below-0.8-the-classifier-answers"])
def test_the_rules_answer_from_exactly_their_threshold(snapshot, monkeypatch, rules: float, calls: int) -> None:
    monkeypatch.setattr(auto_hybrid, "predict_rules", lambda state: ("medium", rules))
    h, upstream, _ = _h(snapshot, system_one("medium", 0.99))
    h(_contract(UNSURE), StopSet(), Turn().call)
    assert len(upstream.calls) == calls


@pytest.mark.parametrize(
    "confidence",
    [None, True, 1.5, -0.1, "0.9", math.nan, "missing"],
    ids=["null", "bool", "above-1", "below-0", "string", "nan", "missing"],
)
def test_a_missing_or_malformed_confidence_is_an_abstention_that_keeps_its_cost(snapshot, confidence: Any) -> None:
    reply = system_one("easy", drop_confidence=True) if confidence == "missing" else system_one("easy", confidence)
    h, _, _ = _h(snapshot, reply)
    turn = Turn()
    outcome = h(_contract(UNSURE), StopSet(), turn.call)
    assert (outcome.tier, outcome.failure_kind, outcome.confidence_band) == (None, "abstention", "none")
    [receipt] = turn.receipts()
    assert (receipt.outcome, receipt.reported_cost_usd) == ("completed", Decimal("0.0000042")), "the known cost is kept"


def test_a_choice_the_gateway_refuses_stops_the_classifier_for_the_launch(snapshot) -> None:
    h, _, _ = _h(snapshot, system_one("hard"))
    turn, stops = Turn(), StopSet()
    outcome = h(_contract(UNSURE), stops, turn.call)
    assert outcome.failure_kind == "stopped_classifier" and JEV in stops
    [receipt] = turn.receipts()
    assert (receipt.outcome, receipt.reported_cost_usd) == ("uncertain", None)


def test_a_stopped_classifier_is_never_called(snapshot) -> None:
    h, upstream, _ = _h(snapshot)
    stops = StopSet()
    stops.add(JEV)
    assert h(_contract(UNSURE), stops, Turn().call).failure_kind == "stopped_classifier"
    assert h(_contract(SURE), stops, Turn().call).answered_by == "rules", "a rules-confident turn still routes"
    assert upstream.calls == []


def test_a_transport_loss_is_a_timeout_with_an_unknown_cost(snapshot) -> None:
    class Lost:
        def post_json(self, request: Any) -> dict[str, Any]:
            raise GatewayHttpError(0, "reset", failure={"kind": "transport"})

    turn = Turn()
    outcome = HybridClassifier(snapshot=snapshot, gateway_client=_client(Lost()), model_id=JEV)(_contract(UNSURE), StopSet(), turn.call)
    assert outcome.failure_kind == "timeout"
    [receipt] = turn.receipts()
    assert (receipt.outcome, receipt.reported_cost_usd) == ("uncertain", None)


def test_an_unreadable_gateway_reply_is_an_error_not_a_timeout(snapshot) -> None:
    class Garbled:
        def post_json(self, request: Any) -> dict[str, Any]:
            raise GatewayHttpError(0, "gateway returned invalid JSON", failure={"kind": "gateway_invalid_json"})

    outcome = HybridClassifier(snapshot=snapshot, gateway_client=_client(Garbled()), model_id=JEV)(_contract(UNSURE), StopSet(), Turn().call)
    assert outcome.failure_kind == "error"


def test_a_refused_lease_sends_nothing_and_halts(snapshot) -> None:
    h, upstream, _ = _h(snapshot, system_one())
    turn = Turn()
    turn.control.request_session_cancel()
    with pytest.raises(ClassifierHalted):
        h(_contract(UNSURE), StopSet(), turn.call)
    assert upstream.calls == []
    assert [(r.outcome, r.reported_cost_usd) for r in turn.receipts()] == [("not_sent", Decimal("0"))]


def test_a_refused_receipt_is_an_accounting_failure_and_a_proven_stop_is_still_kept(snapshot) -> None:
    def refusing(receipt: Any) -> None:
        raise ReceiptConflictError("already recorded differently")

    h, _, _ = _h(snapshot, system_one("hard"))
    turn, stops = Turn(receipts=refusing), StopSet()
    with pytest.raises(ClassificationAccountingError) as raised:
        h(_contract(UNSURE), stops, turn.call)
    assert isinstance(raised.value.__cause__, ReceiptConflictError)
    assert turn.integrity == ["s:1"] and JEV in stops


def test_an_unattributable_report_is_an_accounting_failure_after_its_records_are_offered(snapshot) -> None:
    usage = GatewayUsage(gateway_request_id="gw-reported", provider="openrouter", billing_units=1, cost_usd=Decimal("0.0000042"))

    class Unattributable:
        def create_decision(self, **kwargs: Any) -> GatewayDecision:
            attempts = (GatewayRouteAttempt(attempt=1, gateway_request_id="gw-other", outcome="completed"),)
            return GatewayDecision(answers={"tier": {"choice": "easy", "confidence": 1.0}}, gateway_usage=usage, route_attempts=attempts)

    turn = Turn()
    with pytest.raises(ClassificationAccountingError):
        HybridClassifier(snapshot=snapshot, gateway_client=Unattributable(), model_id=JEV)(_contract(UNSURE), StopSet(), turn.call)
    assert turn.integrity == ["s:1"]
    assert "unattributed" in [r.outcome for r in turn.receipts()], "the reported charge is still recorded"


def test_an_oversized_excerpt_is_cut_until_the_gateway_admits_it(snapshot) -> None:
    h, _, gateway = _h(snapshot, system_one())
    contract = _contract('"' * 5000)  # each quote doubles in JSON, so the 4 KB excerpt overflows the bound
    h(contract, StopSet(), Turn().call)
    [payload] = gateway.payloads
    state = payload["state"]
    profile = snapshot.policy.estimators[snapshot.policy.models[JEV].route.estimator]
    assert estimate_decision(JEV, decision_payload_text(state, QUESTIONS), profile).tokens <= CLASSIFIER_REQUEST_BOUND_TOKENS
    assert state["truncated"] is True and len(state["prompt"].encode()) < len(contract.prompt.encode())


def test_a_request_with_no_room_is_refused_before_any_call(snapshot) -> None:
    h, upstream, _ = _h(snapshot, system_one())
    h._bound = 100  # noqa: SLF001 - below the fixed parts alone
    assert h(_contract(UNSURE), StopSet(), Turn().call).failure_kind == "error"
    assert upstream.calls == []


# --- The Gateway, the client and the launch check --------------------------------------------------------------------


def _contributor_snapshot(tmp_path: Path) -> Any:
    override = tmp_path / "contributor.yaml"
    override.write_text(CLASSIFIER_OVERRIDE.replace("disclosure: none", "disclosure: contributor"), encoding="utf-8")
    return load_registry(packaged_defaults(), override)


def test_the_gateway_refuses_a_disclosure_needing_classifier_as_a_proven_zero_cost_rejection(tmp_path) -> None:
    contributor = _contributor_snapshot(tmp_path)
    upstream = SystemOne(system_one())
    h = HybridClassifier(snapshot=contributor, gateway_client=_client(DecisionGateway(contributor, upstream)), model_id=JEV)
    turn, stops = Turn(), StopSet()
    outcome = h(_contract(UNSURE), stops, turn.call)
    assert upstream.calls == [] and outcome.failure_kind == "error" and JEV not in stops
    assert [(r.outcome, r.reported_cost_usd) for r in turn.receipts()] == [("rejected", Decimal("0"))]
    refusal = GatewayHttpError(400, "refused", gateway_code="DECISION_DISCLOSURE_UNSUPPORTED", retryable=False)
    assert is_preflight_refusal(refusal) and not stops_experimental_route(refusal, experimental=True)
    assert [(a.outcome, a.cost_usd) for a in attempts_from_failure(refusal)] == [("rejected", Decimal("0"))]


def test_the_launch_check_refuses_a_missing_or_disclosure_needing_classifier(tmp_path) -> None:
    with pytest.raises(BindingError) as contributor:
        AutoComposition(_contributor_snapshot(tmp_path)).classifier_model()
    assert contributor.value.code == "AUTO_CLASSIFIER_DISCLOSURE_UNSUPPORTED"
    empty = tmp_path / "no-classifier.yaml"
    empty.write_text("roles:\n  classifier: []\n", encoding="utf-8")
    with pytest.raises(BindingError) as missing:
        AutoComposition(load_registry(packaged_defaults(), empty)).classifier_model()
    assert missing.value.code == "AUTO_CLASSIFIER_MISSING"


def _usage_body() -> dict[str, Any]:
    return {"gateway_request_id": "gw-1", "provider": "openrouter", "billing_units": 1, "cost_usd": "0.0000042"}


@pytest.mark.parametrize(
    "defect", [{"answers": "no"}, {"id": 42}, {"model": {}}], ids=["answers", "id", "model"]
)
def test_a_malformed_decision_is_unusable_but_keeps_its_usage_and_attempts(defect: dict[str, Any]) -> None:
    body = {"id": "gen-1", "model": JEV, "answers": {"tier": {}}, "gateway_usage": _usage_body(),
            "route_attempts": [{"attempt": 1, "gateway_request_id": "gw-1", "outcome": "completed"}], **defect}  # fmt: skip
    decision = parse_decision_response(body)
    assert decision.answers is None
    assert decision.gateway_usage.gateway_request_id == "gw-1" and len(decision.route_attempts) == 1


def test_malformed_route_attempts_raise_but_keep_the_usage() -> None:
    with pytest.raises(GatewayResponseError) as raised:
        parse_decision_response({"answers": {}, "gateway_usage": _usage_body(), "route_attempts": "no"})
    assert raised.value.gateway_usage is not None
