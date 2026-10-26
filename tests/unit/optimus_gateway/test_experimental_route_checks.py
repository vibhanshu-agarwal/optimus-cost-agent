"""Plan 12.2 Haiku 5.5 experimental route: the Gateway's per-reply checks (Codex disposition, 2026-10-09).

On the reviewed experimental test route (``optimus_model_policy.experimental``) every completed reply
is checked against what the route assumed:

- the router metadata's selected provider is the expected one (provider identity, not an exact variant);
- the router made one attempt (no fallback) and ran no pipeline stage (no compression, guardrail, ...), except
  the one unflagged guardrail stage #400 option b1 accepts (ADR-026);
- the reported prompt tokens do not exceed the empirical estimate the request was admitted under.

A failed check fails that call as a permanent, billed result (its usage and attempt are kept, never
re-sent) and stops every later call on the route before it reaches the provider. A passing check shows
only that this request fitted. Ordinary verified routes are unaffected.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import optimus_gateway.responses as gateway_responses
from optimus_gateway.responses import handle_responses_request
from optimus_gateway.upstream_client import ProviderMessageResult, UrllibOpenAICompatibleClient
from optimus_model_policy import test_profiles as profiles
from tests.unit.optimus_gateway.model_policy_support import (
    AUTH,
    PROVIDER_KEY,
    RecordingUpstream,
    Wire,
    binding,
    gateway_config,
    http_reply,
    model_policy,
    verified_snapshot,
)

HAIKU = "anthropic/claude-haiku-5.5"
INPUT = "hi"
ESTIMATE = len(INPUT.encode("utf-8")) + 16 + 256  # one token per byte, one message, the framing allowance


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gateway_responses, "_sleep", lambda _seconds: None)


class Replying(RecordingUpstream):
    """Completed replies with scripted router evidence and reported prompt tokens."""

    def __init__(
        self,
        *,
        provider: str | None = "Anthropic",
        attempt: int | None = 1,
        pipeline: tuple[str, ...] | None = (),
        guardrails: object = None,
        input_tokens: int = ESTIMATE,
        metadata_error: str | None = None,
    ) -> None:
        super().__init__()
        self.evidence = {
            "resolved_provider": provider,
            "router_attempt": attempt,
            "router_pipeline": pipeline,
            "router_guardrails": guardrails,
            "input_tokens": input_tokens,
            "router_metadata_error": metadata_error,
        }

    def _result(self, model: str) -> ProviderMessageResult:
        base = super()._result(model)
        return ProviderMessageResult(**{**base.__dict__, **self.evidence})


def _haiku_policy():
    return model_policy(profiles.compose_test_profile_snapshot("qualification"))


def _post(policy, upstream, *, request_id: str = "host-req-1") -> tuple[int, dict[str, Any]]:
    return handle_responses_request(
        authorization_header=AUTH,
        request_body={"model": HAIKU, "input": INPUT, "route_binding": binding(policy.snapshot, model=HAIKU, input_text=INPUT, output_cap=32_768, request_id=request_id)},
        config=gateway_config(policy),
        upstream_client=upstream,
    )


def test_a_reply_that_matches_the_route_assumptions_passes_with_the_provider_family_filter() -> None:
    upstream = Replying()
    status, body = _post(_haiku_policy(), upstream)

    assert status == 200, body
    [call] = upstream.calls
    assert dict(call["provider_controls"]) == {"only": ["anthropic"], "quantizations": ["unknown"], "allow_fallbacks": False, "require_parameters": True}
    assert (call["reasoning"], call["max_tokens"]) == ("low", 32_768)


@pytest.mark.parametrize(
    ("evidence", "code"),
    [
        ({"input_tokens": ESTIMATE + 1}, "EMPIRICAL_ESTIMATE_EXCEEDED"),
        ({"provider": "Google"}, "EMPIRICAL_PROVIDER_MISMATCH"),
        ({"provider": None}, "EMPIRICAL_PROVIDER_MISSING"),
        ({"attempt": 2}, "EMPIRICAL_ROUTER_FALLBACK"),
        ({"attempt": None}, "EMPIRICAL_ROUTER_METADATA_MISSING"),
        ({"pipeline": ("context_compression",)}, "EMPIRICAL_ROUTER_PIPELINE"),
        ({"pipeline": None}, "EMPIRICAL_ROUTER_METADATA_MISSING"),
        ({"provider": None, "attempt": None, "pipeline": None, "metadata_error": "ambiguous"}, "EMPIRICAL_ROUTER_METADATA_MALFORMED"),
    ],
)
def test_a_failed_check_fails_the_billed_call_and_stops_the_route(evidence: dict[str, Any], code: str) -> None:
    policy = _haiku_policy()
    upstream = Replying(**evidence)

    status, body = _post(policy, upstream)

    assert (status, body["code"], body["retryable"]) == (422, code, False)
    assert body["gateway_usage"]["cost_usd"] and body["gateway_usage"]["input_tokens"] == upstream.evidence["input_tokens"]
    assert [attempt["outcome"] for attempt in body["route_attempts"]] == ["completed"]

    # Every later call on the route is refused before it reaches the provider.
    later_status, later = _post(policy, Replying(), request_id="host-req-2")
    assert (later_status, later["code"]) == (503, "EMPIRICAL_ROUTE_STOPPED")
    assert len(upstream.calls) == 1


def test_a_pipeline_refusal_keeps_the_stage_types_and_ids_in_the_attempt_and_the_gateway_log() -> None:
    """The 2026-10-20 D1(b) refusal named its stages only in an unpersisted message: the attempt record and
    the Gateway's log line must carry the stage types, the refusal detail and both request ids."""
    status, body = _post(_haiku_policy(), Replying(pipeline=("guardrail", "context_compression")))

    assert (status, body["code"]) == (422, "EMPIRICAL_ROUTER_PIPELINE")
    [attempt] = body["route_attempts"]
    assert attempt["router_pipeline"] == ["guardrail", "context_compression"]
    line = json.loads(gateway_responses.model_request_log_line("/v1/responses", status, body))
    assert (line["event"], line["status"], line["code"]) == ("model_request", 422, "EMPIRICAL_ROUTER_PIPELINE")
    assert "the router ran guardrail, context_compression" in line["error"]
    [logged] = line["route_attempts"]
    assert (logged["gateway_request_id"], logged["provider_request_id"]) == (attempt["gateway_request_id"], "gen-1")
    assert logged["router_pipeline"] == ["guardrail", "context_compression"]
    assert (line["usage"]["provider_request_id"], line["usage"]["resolved_provider"]) == ("gen-1", "Anthropic")


# --- #400 option b1 (Codex round 58; operator approval 2026-10-26): the one accepted guardrail stage -------------

_ACCEPTED = {"flagged": False, "detected": "missing", "decision": "missing", "action": "missing", "verdict_conflict": False, "guardrail_scope": "missing"}
_ONE = ("guardrail",)


@pytest.mark.parametrize("facts", [_ACCEPTED, {**_ACCEPTED, "detected": False}], ids=["captured-2026-10-26", "detected-false"])
def test_one_unflagged_guardrail_stage_passes_and_does_not_stop_the_route(facts: dict[str, Any]) -> None:
    policy = _haiku_policy()

    status, body = _post(policy, Replying(pipeline=_ONE, guardrails=(facts,)))

    assert status == 200, body
    assert not _stopped_after(policy)


@pytest.mark.parametrize(
    ("pipeline", "guardrails"),
    [
        (_ONE, ({**_ACCEPTED, "flagged": True},)),
        (_ONE, ({**_ACCEPTED, "flagged": "missing"},)),
        (_ONE, ({**_ACCEPTED, "flagged": "invalid"},)),
        (_ONE, ({**_ACCEPTED, "flagged": 0},)),
        (_ONE, ({**_ACCEPTED, "flagged": None},)),
        (_ONE, ({**_ACCEPTED, "detected": True},)),
        (_ONE, ({**_ACCEPTED, "detected": "invalid"},)),
        (_ONE, ({**_ACCEPTED, "decision": "unrecognized"},)),
        (_ONE, ({**_ACCEPTED, "decision": "invalid"},)),
        (_ONE, ({**_ACCEPTED, "action": "blocked"},)),
        (_ONE, ({**_ACCEPTED, "action": "unrecognized"},)),
        (_ONE, ({**_ACCEPTED, "action": "invalid"},)),
        (_ONE, ({**_ACCEPTED, "verdict_conflict": True},)),
        (_ONE, ({**_ACCEPTED, "verdict_conflict": "missing"},)),
        (_ONE, ({**_ACCEPTED, "guardrail_scope": "api-key"},)),
        (_ONE, ({**_ACCEPTED, "guardrail_scope": "unrecognized"},)),
        (_ONE, ({**_ACCEPTED, "guardrail_scope": "invalid"},)),
        (_ONE, None),
        (_ONE, ()),
        (_ONE, (_ACCEPTED, _ACCEPTED)),
        (_ONE, ("invalid",)),
        (_ONE, [_ACCEPTED]),
        (("guardrail", "guardrail"), (_ACCEPTED, _ACCEPTED)),
        (("guardrail", "context_compression"), (_ACCEPTED,)),
        (("context_compression", "guardrail"), (_ACCEPTED,)),
        (("unrecognized",), ()),
        (("plugin",), ()),
    ],
)
def test_any_other_pipeline_or_guardrail_fact_refuses_the_billed_reply_and_stops_the_route(pipeline: tuple[str, ...], guardrails: object) -> None:
    policy = _haiku_policy()
    upstream = Replying(pipeline=pipeline, guardrails=guardrails)

    status, body = _post(policy, upstream)

    assert (status, body["code"], body["retryable"]) == (422, "EMPIRICAL_ROUTER_PIPELINE", False)
    assert body["gateway_usage"]["cost_usd"] and [attempt["outcome"] for attempt in body["route_attempts"]] == ["completed"]
    assert len(upstream.calls) == 1
    # Neither a later reply with the accepted stage nor one with no stage clears the stop: each is refused before
    # it reaches the provider, so its own client is never called.
    for number, later_client in enumerate((Replying(pipeline=_ONE, guardrails=(_ACCEPTED,)), Replying()), 2):
        later_status, later = _post(policy, later_client, request_id=f"host-req-{number}")
        assert (later_status, later["code"]) == (503, "EMPIRICAL_ROUTE_STOPPED")
        assert later_client.calls == []


@pytest.mark.parametrize(
    ("evidence", "code"),
    [
        ({"input_tokens": ESTIMATE + 1}, "EMPIRICAL_ESTIMATE_EXCEEDED"),
        ({"provider": "Google"}, "EMPIRICAL_PROVIDER_MISMATCH"),
        ({"provider": None}, "EMPIRICAL_PROVIDER_MISSING"),
        ({"attempt": 2}, "EMPIRICAL_ROUTER_FALLBACK"),
        ({"attempt": None}, "EMPIRICAL_ROUTER_METADATA_MISSING"),
    ],
)
def test_an_accepted_guardrail_stage_keeps_every_other_reply_check(evidence: dict[str, Any], code: str) -> None:
    policy = _haiku_policy()

    status, body = _post(policy, Replying(pipeline=_ONE, guardrails=(_ACCEPTED,), **evidence))

    assert (status, body["code"]) == (422, code)
    assert _stopped_after(policy)


def test_an_accepted_guardrail_stage_keeps_the_finish_check_and_the_estimate_boundary() -> None:
    policy = _haiku_policy()
    assert _post(policy, Replying(pipeline=_ONE, guardrails=(_ACCEPTED,), input_tokens=ESTIMATE))[0] == 200

    upstream = Replying(pipeline=_ONE, guardrails=(_ACCEPTED,))
    upstream._finish_reason = "content_filter"
    status, body = _post(policy, upstream, request_id="host-req-2")

    assert (status, body["code"]) == (422, "FINISH_STATUS_UNVERIFIED")
    assert _stopped_after(policy)


def _routed(stages: list[Any]) -> dict[str, Any]:
    return {"requested": HAIKU, "strategy": "direct", "attempt": 1, "endpoints": {"total": 1, "available": [{"provider": "Anthropic", "model": HAIKU, "selected": True}]}, "pipeline": stages}


@pytest.mark.parametrize(
    ("stages", "status"),
    [
        ([{"type": "guardrail", "name": "moderation", "data": {"flagged": False}}], 200),
        ([{"type": "guardrail", "name": "content-filter", "data": {"flagged": False, "detected": False}}], 200),
        ([{"type": "guardrail", "name": "moderation", "data": {"flagged": False, "action": None}}], 422),
        ([{"type": "guardrail", "name": "moderation", "data": {"flagged": False, "decision": None}}], 422),
        ([{"type": "guardrail", "name": "moderation", "data": {"flagged": False, "decision": "missing"}}], 422),
        ([{"type": "guardrail", "name": "moderation", "data": {"flagged": False, "action": "missing"}}], 422),
        ([{"type": "guardrail", "name": "moderation", "data": {"flagged": "false"}}], 422),
        ([{"type": "guardrail", "name": "moderation", "data": {"flagged": None}}], 422),
        ([{"type": "guardrail", "name": "moderation", "data": {"flagged": 0}}], 422),
        ([{"type": "guardrail", "name": "moderation", "data": {"flagged": False, "detected": "no"}}], 422),
        ([{"type": "guardrail", "name": "moderation", "guardrail_scope": "api-key", "data": {"flagged": False}}], 422),
        ([{"type": "guardrail", "name": "moderation", "guardrail_scope": "missing", "data": {"flagged": False}}], 422),
        ([{"type": "guardrail", "name": "moderation"}], 422),
        ([{"type": "guardrail", "name": "moderation", "data": "flagged=false"}], 422),
        ([{"type": "guardrail", "data": {"flagged": False}}, {"type": "guardrail", "data": {"flagged": False}}], 422),
    ],
)
def test_the_rule_reads_the_real_clients_closed_facts(monkeypatch, stages: list[Any], status: int) -> None:
    """Raw OpenRouter metadata, through the real client and the Gateway handler: only the exact unflagged shape
    passes. An explicit null, a literal "missing" string, a wrong type or a reported scope is never a pass."""
    Wire(reply=_reply(HAIKU, _routed(stages))).install(monkeypatch)
    policy = _haiku_policy()

    got, body = _post(policy, _real_client())

    assert got == status, body
    assert body["gateway_usage"]["cost_usd"] == "0.0001"
    if status == 422:
        assert body["code"] == "EMPIRICAL_ROUTER_PIPELINE"
        assert _stopped_after(policy)


def test_the_gateway_log_line_never_carries_the_reply_text() -> None:
    status, body = _post(_haiku_policy(), Replying())

    line = gateway_responses.model_request_log_line("/v1/responses", status, body)
    assert json.loads(line)["status"] == 200
    assert "WRITE a.py" not in line and "output" not in json.loads(line)


def test_the_estimate_equality_boundary_is_admitted() -> None:
    status, body = _post(_haiku_policy(), Replying(input_tokens=ESTIMATE))
    assert status == 200, body


def test_ordinary_verified_routes_keep_their_existing_behaviour(tmp_path: Path) -> None:
    """A non-experimental snapshot is never checked: its replies pass on finish status alone."""
    snapshot = verified_snapshot(tmp_path)
    upstream = Replying(provider=None, attempt=None, pipeline=None, input_tokens=10**6)

    status, body = handle_responses_request(
        authorization_header=AUTH,
        request_body={"model": "cn/alpha", "input": "hi", "route_binding": binding(snapshot, input_text="hi")},
        config=gateway_config(model_policy(snapshot)),
        upstream_client=upstream,
    )

    assert status == 200, body


def _stopped_after(policy) -> bool:
    """True when a later request is refused as stopped without reaching its upstream client."""
    later = Replying()
    status, body = _post(policy, later, request_id="host-req-later")
    return (status, body.get("code")) == (503, "EMPIRICAL_ROUTE_STOPPED") and later.calls == []


def test_an_uncertain_possibly_billed_attempt_stops_the_route() -> None:
    from optimus_gateway.upstream_client import UpstreamAttemptFailure

    policy = _haiku_policy()
    upstream = Replying()
    upstream._attempts = [UpstreamAttemptFailure("uncertain")]

    status, body = _post(policy, upstream)

    assert (status, body["code"]) == (502, "UPSTREAM_ATTEMPT_UNCERTAIN")
    assert _stopped_after(policy)


@pytest.mark.parametrize(("pipeline", "guardrails"), [((), ()), (("guardrail",), ({"flagged": False, "detected": "missing", "decision": "missing", "action": "missing", "verdict_conflict": False, "guardrail_scope": "missing"},))], ids=["no-stage", "accepted-guardrail"])
def test_a_reply_whose_usage_cannot_be_verified_stops_the_route(monkeypatch: pytest.MonkeyPatch, pipeline: tuple[str, ...], guardrails: object) -> None:
    """Unverifiable usage stops the route whether or not the reply carries the one accepted guardrail stage (#400 b1)."""

    def unverifiable(_usage: dict[str, Any]) -> None:
        raise ValueError("usage incomplete")

    monkeypatch.setattr(gateway_responses, "assert_gateway_usage_contract", unverifiable)
    policy = _haiku_policy()
    upstream = Replying(pipeline=pipeline, guardrails=guardrails)

    status, body = _post(policy, upstream)

    assert (status, body["code"]) == (502, "UPSTREAM_ATTEMPT_UNCERTAIN")
    assert [attempt["outcome"] for attempt in body["route_attempts"]] == ["uncertain"] and len(upstream.calls) == 1
    monkeypatch.undo()
    assert _stopped_after(policy)


def test_an_unverified_finish_status_stops_the_route() -> None:
    policy = _haiku_policy()
    upstream = Replying()
    upstream._finish_reason = "content_filter"

    status, body = _post(policy, upstream)

    assert (status, body["code"]) == (422, "FINISH_STATUS_UNVERIFIED")
    assert _stopped_after(policy)


def test_a_failure_that_certainly_reached_no_model_does_not_stop_the_route() -> None:
    from optimus_gateway.upstream_client import UpstreamAttemptFailure

    policy = _haiku_policy()
    upstream = Replying()
    upstream._attempts = [UpstreamAttemptFailure("not_sent"), UpstreamAttemptFailure("not_sent")]

    status, body = _post(policy, upstream)

    assert (status, body["code"]) == (502, "UPSTREAM_ATTEMPT_NOT_SENT")
    status, body = _post(policy, Replying(), request_id="host-req-later")
    assert status == 200, body


# --- Unreadable router metadata, end to end (Codex Haiku Stage A review M1) ----------------------------------

_AMBIGUOUS = {
    "requested": HAIKU,
    "strategy": "direct",
    "attempt": 1,
    "endpoints": {"total": 2, "available": [{"provider": "Anthropic", "model": HAIKU, "selected": True}, {"provider": "Google", "model": HAIKU, "selected": True}]},
}
_STRING_PIPELINE = {**_AMBIGUOUS, "endpoints": {"total": 1, "available": [{"provider": "Anthropic", "model": HAIKU, "selected": True}]}, "pipeline": "context_compression"}


def _reply(model: str, metadata: dict[str, Any]) -> bytes:
    """A billed reply with valid usage (100 input, 20 output, $0.0001) and the given router metadata."""
    body = {
        "id": "gen-1",
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120, "cost": "0.0001"},
        "openrouter_metadata": metadata,
    }
    return http_reply(200, json.dumps(body).encode())


def _real_client() -> UrllibOpenAICompatibleClient:
    return UrllibOpenAICompatibleClient(api_key=PROVIDER_KEY, base_url="https://openrouter.ai/api/v1", sleep=lambda _s: None)


@pytest.mark.parametrize("metadata", [_AMBIGUOUS, _STRING_PIPELINE], ids=["two-selected-endpoints", "string-pipeline"])
def test_unreadable_router_metadata_keeps_the_billed_usage_and_stops_the_experimental_route(monkeypatch, metadata) -> None:
    """Through the real client and the Gateway handler: the billed reply fails as a completed attempt
    with its usage and cost, no provider is guessed, and the route stops."""
    Wire(reply=_reply(HAIKU, metadata)).install(monkeypatch)
    policy = _haiku_policy()

    status, body = _post(policy, _real_client())

    assert (status, body["code"], body["retryable"]) == (422, "EMPIRICAL_ROUTER_METADATA_MALFORMED", False)
    usage = body["gateway_usage"]
    assert (usage["input_tokens"], usage["output_tokens"], usage["cost_usd"], usage["resolved_provider"]) == (100, 20, "0.0001", None)
    assert [attempt["outcome"] for attempt in body["route_attempts"]] == ["completed"]
    assert _stopped_after(policy)


@pytest.mark.parametrize("metadata", [_AMBIGUOUS, _STRING_PIPELINE], ids=["two-selected-endpoints", "string-pipeline"])
def test_an_ordinary_route_keeps_its_accounting_when_router_metadata_is_unreadable(tmp_path: Path, monkeypatch, metadata) -> None:
    Wire(reply=_reply("cn/alpha", metadata)).install(monkeypatch)
    snapshot = verified_snapshot(tmp_path)

    status, body = handle_responses_request(
        authorization_header=AUTH,
        request_body={"model": "cn/alpha", "input": "hi", "route_binding": binding(snapshot, input_text="hi")},
        config=gateway_config(model_policy(snapshot)),
        upstream_client=_real_client(),
    )

    assert status == 200, body
    usage = body["gateway_usage"]
    assert (usage["input_tokens"], usage["output_tokens"], usage["cost_usd"], usage["resolved_provider"]) == (100, 20, "0.0001", None)
