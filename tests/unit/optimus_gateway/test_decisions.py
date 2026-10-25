"""Plan 12.4 v7 Design 1: the Gateway's decision route for classifier models such as Jev.

``POST /v1/decisions`` is served only under an enforced registry, to a model eligible for the classifier role, for a
typed request that fits the classifier's complete-request bound. One provider attempt is made and never re-sent. A
completed reply's usage is kept; its reply checks then run, and a failed check on an exception route stops that
model's route. The System One endpoint carries no router metadata, so only the model, provider and estimate are
checked (design notes, 2026-10-25).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from optimus_gateway.decisions import handle_decision_request
from optimus_gateway.upstream_client import DecisionResult, UpstreamAttemptFailure, UrllibOpenAICompatibleClient, parse_decision_response
from optimus_model_policy.binding import packaged_defaults
from optimus_model_policy.registry import RegistrySnapshot, load_registry
from tests.unit.optimus_gateway.model_policy_support import AUTH, PROVIDER_KEY, Wire, binding, gateway_config, http_reply, model_policy

JEV = "typesafe/jev-1.14"
HAIKU = "anthropic/claude-haiku-5.5"
QUESTIONS = {
    "tier": {"type": "choice", "instructions": "Which tier?", "criteria": {"easy": "one file", "medium": "a module", "complex": "crosses modules"}},
}
STATE = {"contract": "auto-input-v1", "prompt": "rename foo"}
# Jev in the classifier role, as the evaluation composition admits it: the catalogue's facts (2026-10-25), the
# conservative estimator, and both admission parts.
CLASSIFIER_OVERRIDE = """
output_reserve_tokens: {implementer: 32768, summarizer: 8192, classifier: 256}
models:
  typesafe/jev-1.14:
    origin: non-china
    tier: ultra-cheap
    prices: {input_usd_per_million: "0.042", output_usd_per_million: "0"}
    data_use: {provider_may_train_on_inputs: "no", disclosure: none}
    capabilities: {native_tools: false, text_planning_grammar: false, structured_output: true, reasoning_levels: []}
    default_reasoning: null
    route:
      estimator: conservative-utf8
      endpoints:
        - {provider: typesafe, quantization: unknown, context_window_tokens: 262144, max_output_tokens: 235929, verified: true, observed_on: "2026-10-25"}
    admission:
      empirical_estimate:
        evidence: ["a test fixture"]
        assumptions: ["text-only input"]
        limitations: ["a first call can exceed its estimate"]
      provider_family:
        provider: typesafe
        provider_name: TypeSafe
        evidence: ["a test fixture"]
        limitations: ["the System One endpoint reports no router attempt or pipeline"]
roles:
  classifier: [typesafe/jev-1.14]
"""


def _snapshot(tmp_path: Path) -> RegistrySnapshot:
    override = tmp_path / "classifier.yaml"
    override.write_text(CLASSIFIER_OVERRIDE, encoding="utf-8")
    return load_registry(packaged_defaults(), override)


def _payload_tokens() -> int:
    text = json.dumps({"state": STATE, "questions": QUESTIONS}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return len(text.encode("utf-8")) + 16 + 256


def _result(**changes: Any) -> DecisionResult:
    base = {
        "decision_id": "gen-dec-1",
        "resolved_model": JEV + "-20261014",
        "resolved_provider": "TypeSafe",
        "answers": {"tier": {"type": "choice", "choice": "easy", "confidence": 0.9, "probabilities": {"easy": 0.95, "medium": 0.05, "complex": 0}}},
        "input_tokens": 100,
        "output_tokens": 10,
        "cost_usd": Decimal("0.0000042"),
    }
    return DecisionResult(**{**base, **changes})


class Deciding:
    def __init__(self, *outcomes: DecisionResult | BaseException) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    def create_decision_once(self, **kwargs: Any) -> DecisionResult:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _post(policy, upstream, snapshot: RegistrySnapshot, *, model: str = JEV, questions: dict | None = None, state: dict | None = None, bind: bool = True):
    body: dict[str, Any] = {"model": model, "state": STATE if state is None else state, "questions": QUESTIONS if questions is None else questions}
    if bind:
        body["route_binding"] = binding(snapshot, model=model, output_cap=1)
    return handle_decision_request(authorization_header=AUTH, request_body=body, config=gateway_config(policy), upstream_client=upstream)


def test_a_decision_is_admitted_sent_once_and_settled(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    upstream = Deciding(_result())

    status, body = _post(model_policy(snapshot), upstream, snapshot)

    assert status == 200
    assert body["answers"]["tier"]["choice"] == "easy" and body["model"] == JEV + "-20261014"
    assert (body["gateway_usage"]["cost_usd"], body["gateway_usage"]["input_tokens"]) == ("0.0000042", 100)
    assert [attempt["outcome"] for attempt in body["route_attempts"]] == ["completed"]
    [call] = upstream.calls
    assert call["model"] == JEV and call["provider_controls"] == {"only": ["typesafe"], "allow_fallbacks": False}


def test_decisions_need_an_enforced_registry_and_a_binding(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    upstream = Deciding()

    status, body = _post(None, upstream, snapshot)
    assert (status, body["code"]) == (400, "DECISIONS_NEED_REGISTRY")
    status, body = _post(model_policy(snapshot), upstream, snapshot, bind=False)
    assert body["code"] == "BINDING_REQUIRED"
    assert upstream.calls == []


def test_only_a_classifier_eligible_model_is_served(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    upstream = Deciding()
    status, body = _post(model_policy(snapshot), upstream, snapshot, model=HAIKU)
    assert (status, body["code"]) == (400, "MODEL_NOT_ELIGIBLE") and upstream.calls == []


def test_a_typed_request_over_the_classifier_bound_is_refused_before_any_call(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    upstream = Deciding()
    big = {"contract": "auto-input-v1", "prompt": "x" * 9000}
    status, body = _post(model_policy(snapshot), upstream, snapshot, state=big)
    assert body["code"] == "INPUT_EXCEEDS_CAPACITY" and upstream.calls == []


@pytest.mark.parametrize(
    ("result", "code"),
    [
        (_result(resolved_provider="Elsewhere"), "EMPIRICAL_PROVIDER_MISMATCH"),
        (_result(resolved_provider=None), "EMPIRICAL_PROVIDER_MISSING"),
        (_result(resolved_model="other/model"), "DECISION_MODEL_MISMATCH"),
        (_result(input_tokens=10**6), "EMPIRICAL_ESTIMATE_EXCEEDED"),
    ],
)
def test_a_failed_reply_check_keeps_its_usage_and_stops_the_route(tmp_path: Path, result: DecisionResult, code: str) -> None:
    snapshot = _snapshot(tmp_path)
    policy = model_policy(snapshot)
    upstream = Deciding(result)

    status, body = _post(policy, upstream, snapshot)
    assert (status, body["code"]) == (422, code) and body["gateway_usage"]["cost_usd"] == "0.0000042"

    later_status, later = _post(policy, upstream, snapshot)
    assert (later_status, later["code"]) == (503, "EMPIRICAL_ROUTE_STOPPED")
    assert len(upstream.calls) == 1


def test_the_estimate_check_uses_the_admitted_estimate(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    status, _ = _post(model_policy(snapshot), Deciding(_result(input_tokens=_payload_tokens())), snapshot)
    assert status == 200


def test_an_uncertain_attempt_stops_the_route_and_a_refused_one_does_not(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    policy = model_policy(snapshot)

    status, body = _post(policy, Deciding(UpstreamAttemptFailure("rejected", http_status=400, failure={"kind": "http"})), snapshot)
    assert (status, body["code"]) == (502, "UPSTREAM_ATTEMPT_REJECTED")
    assert _post(policy, Deciding(_result()), snapshot)[0] == 200

    status, body = _post(policy, Deciding(UpstreamAttemptFailure("uncertain", failure={"kind": "transport"})), snapshot)
    assert (status, body["code"]) == (502, "UPSTREAM_ATTEMPT_UNCERTAIN")
    assert _post(policy, Deciding(_result()), snapshot)[1]["code"] == "EMPIRICAL_ROUTE_STOPPED"


@pytest.mark.parametrize(
    "questions",
    [
        {},
        {"q": {"type": "essay"}},
        {"q": {"type": "score", "criteria": ["only one"]}},
        {"q": {"type": "choice", "criteria": {}}},
    ],
)
def test_a_malformed_envelope_is_refused(tmp_path: Path, questions: dict) -> None:
    snapshot = _snapshot(tmp_path)
    status, _ = _post(model_policy(snapshot), Deciding(), snapshot, questions=questions)
    assert status == 400


def _reply(**changes: Any) -> dict[str, Any]:
    reply = {
        "id": "gen-dec-1",
        "model": JEV + "-20261014",
        "provider": "TypeSafe",
        "answers": {"tier": {"type": "choice", "choice": "easy", "confidence": 0.9, "probabilities": {}}},
        "usage": {"input_tokens": 100, "output_tokens": 10, "cost": 0.0000042},
    }
    reply.update(changes)
    return reply


@pytest.mark.parametrize(
    "reply",
    [
        _reply(answers={}),
        _reply(answers={"tier": {"type": "noul", "noul": 0.5}}),
        _reply(answers={"tier": {"type": "choice", "choice": "huge"}}),
        _reply(usage={"input_tokens": 100, "output_tokens": 10}),
        _reply(usage={"input_tokens": 100, "output_tokens": 10, "cost": -1}),
        _reply(usage={"input_tokens": -1, "output_tokens": 10, "cost": 0}),
        _reply(id=""),
    ],
)
def test_an_unverifiable_decision_reply_is_refused(reply: dict[str, Any]) -> None:
    with pytest.raises(RuntimeError):
        parse_decision_response(reply, questions=QUESTIONS)


def test_noul_and_score_answers_are_range_checked() -> None:
    questions = {"bug": {"type": "noul", "criteria": {"true": "a", "false": "b"}}, "size": {"type": "score", "criteria": ["s", "m", "l"]}}
    ok = _reply(answers={"bug": {"type": "noul", "noul": 0.2}, "size": {"type": "score", "score": 1.5}})
    assert parse_decision_response(ok, questions=questions).answers["size"]["score"] == 1.5
    for bad in ({"bug": {"type": "noul", "noul": 1.5}, "size": {"type": "score", "score": 1}}, {"bug": {"type": "noul", "noul": 0}, "size": {"type": "score", "score": 3}}):
        with pytest.raises(RuntimeError):
            parse_decision_response(_reply(answers=bad), questions=questions)


def test_the_real_client_posts_to_system_one_with_the_route_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    wire = Wire(reply=http_reply(200, json.dumps(_reply()).encode("utf-8"))).install(monkeypatch)
    client = UrllibOpenAICompatibleClient(api_key=PROVIDER_KEY, base_url="https://openrouter.ai/api/v1", sleep=lambda _s: None)

    result = client.create_decision_once(model=JEV, state=STATE, questions=QUESTIONS, provider_controls={"only": ["typesafe"], "allow_fallbacks": False})

    assert (result.decision_id, result.resolved_provider, result.cost_usd) == ("gen-dec-1", "TypeSafe", Decimal("0.0000042"))
    head, _, sent_body = bytes(wire.sent[-1]).partition(b"\r\n\r\n")
    assert head.startswith(b"POST /api/v1/systemone HTTP/1.1\r\n")
    assert json.loads(sent_body) == {"model": JEV, "state": STATE, "questions": QUESTIONS, "provider": {"only": ["typesafe"], "allow_fallbacks": False}}
