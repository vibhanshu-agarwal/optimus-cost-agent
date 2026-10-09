"""Plan 12.2 Haiku 5.5 experimental route: the Gateway's per-reply checks (Codex disposition, 2026-10-09).

On the reviewed experimental test route (``optimus_model_policy.experimental``) every completed reply
is checked against what the route assumed:

- the router metadata's selected provider is the expected one (provider identity, not an exact variant);
- the router made one attempt (no fallback) and ran no pipeline stage (no compression, guardrail, ...);
- the reported prompt tokens do not exceed the empirical estimate the request was admitted under.

A failed check fails that call as a permanent, billed result (its usage and attempt are kept, never
re-sent) and stops every later call on the route before it reaches the provider. A passing check shows
only that this request fitted. Ordinary verified routes are unaffected.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import optimus_gateway.responses as gateway_responses
from optimus_gateway.responses import handle_responses_request
from optimus_gateway.upstream_client import ProviderMessageResult
from optimus_model_policy import test_profiles as profiles
from tests.unit.optimus_gateway.model_policy_support import (
    AUTH,
    RecordingUpstream,
    binding,
    gateway_config,
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

    def __init__(self, *, provider: str | None = "Anthropic", attempt: int | None = 1, pipeline: tuple[str, ...] | None = (), input_tokens: int = ESTIMATE) -> None:
        super().__init__()
        self.evidence = {"resolved_provider": provider, "router_attempt": attempt, "router_pipeline": pipeline, "input_tokens": input_tokens}

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
    status, body = _post(policy, Replying(), request_id="host-req-later")
    return (status, body.get("code")) == (503, "EMPIRICAL_ROUTE_STOPPED")


def test_an_uncertain_possibly_billed_attempt_stops_the_route() -> None:
    from optimus_gateway.upstream_client import UpstreamAttemptFailure

    policy = _haiku_policy()
    upstream = Replying()
    upstream._attempts = [UpstreamAttemptFailure("uncertain")]

    status, body = _post(policy, upstream)

    assert (status, body["code"]) == (502, "UPSTREAM_ATTEMPT_UNCERTAIN")
    assert _stopped_after(policy)


def test_a_reply_whose_usage_cannot_be_verified_stops_the_route(monkeypatch: pytest.MonkeyPatch) -> None:
    def unverifiable(_usage: dict[str, Any]) -> None:
        raise ValueError("usage incomplete")

    monkeypatch.setattr(gateway_responses, "assert_gateway_usage_contract", unverifiable)
    policy = _haiku_policy()

    status, body = _post(policy, Replying())

    assert (status, body["code"]) == (502, "UPSTREAM_ATTEMPT_UNCERTAIN")
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
