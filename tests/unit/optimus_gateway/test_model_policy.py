"""Plan 12.2 Task 5: the Gateway enforces the trusted model registry before any upstream call.

Enforcement is built but inactive (operator decision 2026-10-02): with no policy configured the
Gateway keeps today's routing and refuses a ``route_binding`` it cannot honour. With a policy, every
refusal below makes zero upstream calls, on ``/v1/responses`` and on ``/v1/chat/completions`` after
its flattening. Contributor routes need a disclosure bound to request, route and payload.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from optimus.gateway.errors import GatewayHttpError
from optimus.gateway.models import parse_gateway_response, parse_gateway_usage
from optimus.retry.policy import FailureKind, classify_failure
from optimus_gateway.chat_completions import handle_chat_completions_request
from optimus_gateway.model_policy import GatewayModelPolicy
from optimus_gateway.responses import handle_responses_request
from optimus_gateway.upstream_client import UrllibOpenAICompatibleClient
from tests.unit.optimus_gateway.model_policy_support import (
    AUTH,
    CAP,
    SHARED_SECRET,
    VERIFIED_POLICY,
    RecordingUpstream,
    binding,
    gateway_config,
    model_policy,
    verified_snapshot,
)

ROUTES = ("responses", "chat")


def _send(route: str, config, upstream, *, model: str, text: str, route_binding: Any = None, omit: bool = False):
    body: dict[str, Any] = {"model": model}
    if route == "responses":
        body["input"] = text
        handler = handle_responses_request
    else:
        body["messages"] = [{"role": "user", "content": text}]
        handler = handle_chat_completions_request
    if not omit:
        body["route_binding"] = route_binding
    return handler(authorization_header=AUTH, request_body=body, config=config, upstream_client=upstream)


@pytest.fixture
def snapshot(tmp_path: Path):
    return verified_snapshot(tmp_path)


# --- Inactive: today's routing ----------------------------------------------------------------------


@pytest.mark.parametrize("route", ROUTES)
def test_inactive_gateway_keeps_todays_alias_routing_without_new_wire_fields(route: str) -> None:
    upstream = RecordingUpstream()
    status, _ = _send(route, gateway_config(), upstream, model="claude-haiku", text="hi", omit=True)
    assert status == 200
    assert upstream.calls == [
        {"model": "anthropic/claude-haiku-4.5", "input_text": "hi", "max_tokens": None, "provider_controls": None}
    ]


@pytest.mark.parametrize("route", ROUTES)
def test_inactive_gateway_rejects_a_binding_it_cannot_enforce(route: str, snapshot) -> None:
    upstream = RecordingUpstream()
    status, body = _send(route, gateway_config(), upstream, model="cn/alpha", text="hi", route_binding=binding(snapshot))
    assert (status, body["code"]) == (400, "BINDING_UNSUPPORTED")
    assert upstream.calls == []


# --- Active: refusals make zero upstream calls ------------------------------------------------------


@pytest.mark.parametrize("route", ROUTES)
def test_missing_binding_is_refused(route: str, snapshot) -> None:
    upstream = RecordingUpstream()
    for omit, value in ((True, None), (False, None)):
        status, body = _send(route, gateway_config(model_policy(snapshot)), upstream, model="cn/alpha", text="hi", route_binding=value, omit=omit)
        assert (status, body["code"]) == (400, "BINDING_REQUIRED")
    assert upstream.calls == []


@pytest.mark.parametrize("route", ROUTES)
def test_forged_registry_hash_is_refused(route: str, snapshot) -> None:
    upstream = RecordingUpstream()
    forged = dict(binding(snapshot), registry_hash="f" * 64)
    status, body = _send(route, gateway_config(model_policy(snapshot)), upstream, model="cn/alpha", text="hi", route_binding=forged)
    assert (status, body["code"]) == (400, "REGISTRY_HASH_MISMATCH")
    assert upstream.calls == []


@pytest.mark.parametrize("route", ROUTES)
def test_stale_launch_snapshot_is_refused(route: str, snapshot) -> None:
    """The Gateway's snapshot is not the one launch approved (stale approval or changed file)."""
    upstream = RecordingUpstream()
    policy = model_policy(snapshot, approved_hash="0" * 64)
    status, body = _send(route, gateway_config(policy), upstream, model="cn/alpha", text="hi", route_binding=binding(snapshot))
    assert (status, body["code"]) == (503, "SNAPSHOT_NOT_APPROVED")
    assert upstream.calls == []


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("model", ["anthropic/claude-haiku-4.5", "claude-haiku", "vendor/anything", "CN/ALPHA", " cn/alpha2"])
def test_arbitrary_models_and_aliases_are_never_routed(route: str, model: str, snapshot) -> None:
    upstream = RecordingUpstream()
    status, body = _send(route, gateway_config(model_policy(snapshot)), upstream, model=model, text="hi", route_binding=binding(snapshot))
    assert (status, body["code"]) == (400, "UNKNOWN_MODEL")
    assert upstream.calls == []


@pytest.mark.parametrize("route", ROUTES)
def test_registry_model_without_an_eligible_role_is_refused(route: str, snapshot) -> None:
    upstream = RecordingUpstream()
    status, body = _send(
        route, gateway_config(model_policy(snapshot)), upstream, model="us/idle", text="hi", route_binding=binding(snapshot, model="us/idle")
    )
    assert (status, body["code"]) == (400, "MODEL_NOT_ELIGIBLE")
    assert upstream.calls == []


@pytest.mark.parametrize("route", ROUTES)
def test_unrecorded_quantization_is_not_eligible_so_it_is_refused(route: str, snapshot) -> None:
    """Host eligibility and Gateway admission agree: a route the Gateway cannot constrain to an
    approved quantization is not eligible, so it is never the host's default either (Fable M1)."""
    upstream = RecordingUpstream()
    status, body = _send(
        route,
        gateway_config(model_policy(snapshot)),
        upstream,
        model="cn/nullquant",
        text="hi",
        route_binding=binding(snapshot, model="cn/nullquant"),
    )
    assert (status, body["code"]) == (400, "MODEL_NOT_ELIGIBLE")
    assert upstream.calls == []


def _malformed_bindings(snapshot) -> list[tuple[Any, str]]:
    good = binding(snapshot)
    return [
        ("not-an-object", "BINDING_MALFORMED"),
        (dict(good, extra=1), "BINDING_MALFORMED"),
        ({k: v for k, v in good.items() if k != "request_id"}, "BINDING_MALFORMED"),
        (dict(good, version=2), "BINDING_VERSION_UNSUPPORTED"),
        (dict(good, version=True), "BINDING_MALFORMED"),
        (dict(good, version=1.0), "BINDING_MALFORMED"),
        (dict(good, output_cap=True), "BINDING_MALFORMED"),
        (dict(good, output_cap="16384"), "BINDING_MALFORMED"),
        (dict(good, request_id="  "), "BINDING_MALFORMED"),
        (dict(good, registry_hash=good["registry_hash"].upper()), "BINDING_MALFORMED"),
        (dict(good, registry_hash="abc"), "BINDING_MALFORMED"),
        (dict(good, disclosure={"route_digest": "a" * 64, "payload_digest": "b" * 64}), "BINDING_MALFORMED"),
        (dict(good, disclosure={"route_digest": "a" * 64, "payload_digest": "b" * 64, "mac": "c" * 64, "x": 1}), "BINDING_MALFORMED"),
    ]


@pytest.mark.parametrize("route", ROUTES)
def test_unsupported_binding_shapes_are_rejected_not_ignored(route: str, snapshot) -> None:
    upstream = RecordingUpstream()
    for value, code in _malformed_bindings(snapshot):
        status, body = _send(route, gateway_config(model_policy(snapshot)), upstream, model="cn/alpha", text="hi", route_binding=value)
        assert (status, body["code"]) == (400, code), value
    assert upstream.calls == []


def test_a_fixture_registry_cannot_be_enforced(tmp_path: Path) -> None:
    fixture = verified_snapshot(tmp_path, VERIFIED_POLICY.replace("fixture: false", "fixture: true"))
    with pytest.raises(ValueError, match="fixture"):
        GatewayModelPolicy.for_launch(snapshot=fixture, approved_hash=fixture.effective_hash, shared_secret=SHARED_SECRET)


# --- Active: an admitted request ------------------------------------------------------------------


@pytest.mark.parametrize("route", ROUTES)
def test_admitted_request_carries_route_controls_and_output_cap(route: str, snapshot) -> None:
    upstream = RecordingUpstream()
    status, body = _send(route, gateway_config(model_policy(snapshot)), upstream, model="cn/alpha", text="plan the change", route_binding=binding(snapshot))
    assert status == 200, body
    [call] = upstream.calls
    assert call["model"] == "cn/alpha"
    assert call["max_tokens"] == CAP
    assert dict(call["provider_controls"]) == {
        "only": ["alpha-cloud/fp8", "alpha-backup"],
        "quantizations": ["bf16", "fp8"],
        "allow_fallbacks": False,
        "require_parameters": True,
    }


def test_route_controls_and_cap_reach_the_provider_wire_payload(monkeypatch: pytest.MonkeyPatch, snapshot) -> None:
    """The real client's JSON, not a fake's kwargs: wire mapping v1 is OpenRouter ``max_tokens`` and
    ``provider``; today's routing sends neither."""
    sent: list[dict[str, Any]] = []

    class _Response:
        headers: dict[str, str] = {}

        def read(self) -> bytes:
            return json.dumps(
                {
                    "id": "gen-1",
                    "model": "cn/alpha",
                    "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": "0.00001"},
                }
            ).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def fake_urlopen(request, timeout: float = 0):
        sent.append(json.loads(request.data.decode("utf-8")))
        return _Response()

    monkeypatch.setattr("optimus_gateway.upstream_client.urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(api_key="or-test", base_url="https://openrouter.ai/api/v1")

    status, _ = _send("chat", gateway_config(model_policy(snapshot)), client, model="cn/alpha", text="hi", route_binding=binding(snapshot, input_text="hi"))
    assert status == 200
    status, _ = _send("responses", gateway_config(), client, model="claude-haiku", text="hi", omit=True)
    assert status == 200

    enforced, today = sent
    assert enforced == {
        "model": "cn/alpha",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": CAP,
        "provider": {
            "only": ["alpha-cloud/fp8", "alpha-backup"],
            "quantizations": ["bf16", "fp8"],
            "allow_fallbacks": False,
            "require_parameters": True,
        },
    }
    assert set(today) == {"model", "messages"}


# --- Contributor disclosure -----------------------------------------------------------------------


@pytest.mark.parametrize("route", ROUTES)
def test_contributor_route_without_disclosure_is_refused(route: str, snapshot) -> None:
    upstream = RecordingUpstream()
    status, body = _send(
        route, gateway_config(model_policy(snapshot)), upstream, model="us/contrib", text="hi", route_binding=binding(snapshot, model="us/contrib")
    )
    assert (status, body["code"]) == (400, "DISCLOSURE_REQUIRED")
    assert upstream.calls == []


@pytest.mark.parametrize("route", ROUTES)
def test_one_notice_covers_identical_payload_retries_on_the_same_route(route: str, snapshot) -> None:
    upstream = RecordingUpstream()
    config = gateway_config(model_policy(snapshot))
    authorized = binding(snapshot, model="us/contrib", input_text="hi", disclose=True)
    for _ in range(2):
        status, _ = _send(route, config, upstream, model="us/contrib", text="hi", route_binding=authorized)
        assert status == 200
    assert len(upstream.calls) == 2, "each retry is its own upstream attempt"


@pytest.mark.parametrize("route", ROUTES)
def test_a_disclosure_never_covers_another_payload_request_route_or_launch(route: str, snapshot) -> None:
    upstream = RecordingUpstream()
    config = gateway_config(model_policy(snapshot))
    issued = binding(snapshot, model="us/contrib", input_text="hi", disclose=True)
    other_model = binding(snapshot, model="cn/alpha", input_text="hi", disclose=True)  # notice for another route
    cases = [
        ("hi, changed", issued),  # changed payload, e.g. maintenance or a re-packed request
        ("hi", dict(issued, request_id="req-2")),  # another request
        ("hi", dict(issued, output_cap=CAP - 1)),  # another output cap changes the payload
        ("hi", dict(issued, disclosure=dict(issued["disclosure"], route_digest=other_model["disclosure"]["route_digest"]))),
        ("hi", dict(issued, disclosure=dict(issued["disclosure"], mac="0" * 64))),  # forged
        ("hi", binding(snapshot, model="us/contrib", input_text="hi", disclose=True, secret="another-launch")),  # pragma: allowlist secret - synthetic test fixture
    ]
    for text, value in cases:
        status, body = _send(route, config, upstream, model="us/contrib", text=text, route_binding=value)
        assert (status, body["code"]) == (400, "DISCLOSURE_INVALID"), value
    assert upstream.calls == []


def test_chat_disclosure_binds_the_flattened_payload(snapshot) -> None:
    """The digest covers what is actually sent upstream: the flattened text, not the message list."""
    upstream = RecordingUpstream()
    config = gateway_config(model_policy(snapshot))
    request = {
        "model": "us/contrib",
        "messages": [{"role": "system", "content": " rules "}, {"role": "user", "content": "task"}],
        "route_binding": binding(snapshot, model="us/contrib", input_text="rules\ntask", disclose=True),
    }
    status, _ = handle_chat_completions_request(authorization_header=AUTH, request_body=request, config=config, upstream_client=upstream)
    assert status == 200
    assert upstream.calls[0]["input_text"] == "rules\ntask"


# --- Finish status under the verified route contract ----------------------------------------------


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("finish", ["stop", "length"])
def test_complete_and_length_limited_replies_reach_the_host(route: str, finish: str, snapshot) -> None:
    upstream = RecordingUpstream(finish_reason=finish)
    status, body = _send(route, gateway_config(model_policy(snapshot)), upstream, model="cn/alpha", text="hi", route_binding=binding(snapshot, input_text="hi"))
    assert status == 200
    if route == "responses":
        assert parse_gateway_response(body).finish_reason == finish
    else:
        assert body["choices"][0]["finish_reason"] == finish


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("finish", [None, "content_filter", "tool_calls", "error"])
def test_missing_or_unknown_finish_status_fails_and_keeps_its_usage(route: str, finish, snapshot) -> None:
    upstream = RecordingUpstream(finish_reason=finish)
    status, body = _send(route, gateway_config(model_policy(snapshot)), upstream, model="cn/alpha", text="hi", route_binding=binding(snapshot, input_text="hi"))
    assert (status, body["code"]) == (422, "FINISH_STATUS_UNVERIFIED")
    assert len(upstream.calls) == 1
    usage = parse_gateway_usage(body["gateway_usage"])  # the host keeps the billed receipt
    assert usage.cost_usd == Decimal("0.0002")
    assert "output_text" not in body and "choices" not in body


def test_the_host_never_retries_a_billed_finish_refusal(snapshot) -> None:
    """The refusal follows a made, billed call; the host's retry policy treats it as terminal, so
    the planning loop does not re-dispatch the prompt (Fable M2)."""
    upstream = RecordingUpstream(finish_reason="content_filter")
    status, body = _send("responses", gateway_config(model_policy(snapshot)), upstream, model="cn/alpha", text="hi", route_binding=binding(snapshot, input_text="hi"))
    error = GatewayHttpError(status, body["error"], gateway_usage=parse_gateway_usage(body["gateway_usage"]))
    classification = classify_failure(error)
    assert classification.retryable is False
    assert classification.kind is FailureKind.PERMANENT


def test_inactive_gateway_passes_any_finish_status_through() -> None:
    """Before activation only ``length`` is acted on, by the host; nothing else changes."""
    upstream = RecordingUpstream(finish_reason=None)
    status, _ = _send("responses", gateway_config(), upstream, model="claude-haiku", text="hi", omit=True)
    assert status == 200
