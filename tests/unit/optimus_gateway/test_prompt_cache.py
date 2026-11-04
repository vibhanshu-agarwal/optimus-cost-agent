"""Plan 12.10 Task 4: a route's optional prompt caching. Saying nothing keeps every approved hash and wire byte; opting in enters the
identities; only `top_level` changes what is sent. The wire tests read the real client's bytes, not a fake's keywords."""

from __future__ import annotations

from pathlib import Path

import pytest

from optimus_gateway.chat_completions import handle_chat_completions_request
from optimus_gateway.responses import handle_responses_request
from optimus_gateway.upstream_client import UrllibOpenAICompatibleClient
from optimus_model_policy.binding import Message, RouteBinding, disclosure_key, issue_disclosure, payload_digest, route_digest
from optimus_model_policy.registry import RegistryError, load_registry
from tests.unit.optimus_gateway.model_policy_support import (
    AUTH,
    CAP,
    PROVIDER_KEY,
    SHARED_SECRET,
    VERIFIED_POLICY,
    Wire,
    binding,
    gateway_config,
    http_reply,
    model_policy,
    ok_completion_body,
    verified_snapshot,
)

# What the code before this setting computed for VERIFIED_POLICY, exported from the commit before it and run there.
BEFORE_EFFECTIVE_HASH = "bac5079b156be4fa34566efb911683f9182c519d6898dc75faea73445a94e149"  # pragma: allowlist secret - public digest
BEFORE_ROUTE_DIGEST = "9c634337efd3d1bb955370b239c209d2406634b4b547969296afaa9f21ca43a7"  # pragma: allowlist secret - public digest
BEFORE_PAYLOAD_DIGEST = "7e48e3695c0298ba9724ecb8765cb6071cc81524d2a2e32e362450e0c149e583"  # pragma: allowlist secret - public digest
_ROUTE = "    route:\n      estimator: half\n"


def _with_cache(mode: str, *, count: int = 1) -> str:
    return VERIFIED_POLICY.replace(_ROUTE, f"    route:\n      prompt_cache: {mode}\n      estimator: half\n", count)


def _send(route: str, config, client, *, model: str = "cn/alpha", text: str = "hi", route_binding=None):
    body = {"model": model, "route_binding": route_binding}
    if route == "responses":
        return handle_responses_request(authorization_header=AUTH, request_body={**body, "input": text}, config=config, upstream_client=client)
    return handle_chat_completions_request(authorization_header=AUTH, request_body={**body, "messages": [{"role": "user", "content": text}]}, config=config, upstream_client=client)


def _wire_body(monkeypatch, tmp_path: Path, policy_text: str, route: str) -> dict:
    snapshot = verified_snapshot(tmp_path, policy_text)
    wire = Wire(reply=http_reply(200, ok_completion_body())).install(monkeypatch)
    client = UrllibOpenAICompatibleClient(api_key=PROVIDER_KEY, base_url="https://openrouter.ai/api/v1")
    status, _ = _send(route, gateway_config(model_policy(snapshot)), client, route_binding=binding(snapshot, input_text="hi"))
    assert status == 200
    return wire.request_body(0)


BASELINE_WIRE = {
    "model": "cn/alpha",
    "messages": [{"role": "user", "content": "hi"}],
    "max_tokens": CAP,
    "reasoning": {"effort": "high"},
    "provider": {"only": ["alpha-cloud/fp8", "alpha-backup/bf16"], "quantizations": ["bf16", "fp8"], "allow_fallbacks": False, "require_parameters": True},
}


def test_a_registry_that_says_nothing_keeps_every_approved_identity(tmp_path):
    snapshot = verified_snapshot(tmp_path)
    entry = snapshot.policy.models["cn/alpha"]
    assert "prompt_cache" not in entry.route.model_dump(mode="json")
    assert snapshot.effective_hash == BEFORE_EFFECTIVE_HASH
    assert route_digest("cn/alpha", entry) == BEFORE_ROUTE_DIGEST
    assert payload_digest("cn/alpha", (Message("user", "hi"),), CAP, reasoning="high") == BEFORE_PAYLOAD_DIGEST


@pytest.mark.parametrize("mode", ["none", "implicit", "top_level"])
def test_opting_in_enters_the_registry_and_route_identities(tmp_path, mode):
    plain = verified_snapshot(tmp_path)
    chosen = verified_snapshot(tmp_path, _with_cache(mode))
    assert chosen.effective_hash != plain.effective_hash
    assert route_digest("cn/alpha", chosen.policy.models["cn/alpha"]) != route_digest("cn/alpha", plain.policy.models["cn/alpha"])
    # Another model's route is not touched by this one's setting.
    assert route_digest("us/idle", chosen.policy.models["us/idle"]) == route_digest("us/idle", plain.policy.models["us/idle"])


def test_only_top_level_changes_the_payload_identity():
    messages = (Message("user", "hi"),)
    base = payload_digest("cn/alpha", messages, CAP, reasoning="high")
    assert payload_digest("cn/alpha", messages, CAP, reasoning="high", prompt_cache=None) == base
    assert payload_digest("cn/alpha", messages, CAP, reasoning="high", prompt_cache="none") == base
    assert payload_digest("cn/alpha", messages, CAP, reasoning="high", prompt_cache="implicit") == base
    assert payload_digest("cn/alpha", messages, CAP, reasoning="high", prompt_cache="top_level") != base


@pytest.mark.parametrize("route", ["responses", "chat"])
@pytest.mark.parametrize("mode", [None, "none", "implicit"])
def test_without_top_level_the_wire_is_exactly_what_it_was(monkeypatch, tmp_path, route, mode):
    assert _wire_body(monkeypatch, tmp_path, VERIFIED_POLICY if mode is None else _with_cache(mode), route) == BASELINE_WIRE


@pytest.mark.parametrize("route", ["responses", "chat"])
def test_top_level_adds_only_the_root_control_after_flattening(monkeypatch, tmp_path, route):
    # Pinning, fallback and parameter controls are unchanged, and the control is never inside `provider`.
    assert _wire_body(monkeypatch, tmp_path, _with_cache("top_level"), route) == {**BASELINE_WIRE, "cache_control": {"type": "ephemeral"}}


def test_chat_messages_are_flattened_to_one_user_message_before_the_control_is_added(monkeypatch, tmp_path):
    snapshot = verified_snapshot(tmp_path, _with_cache("top_level"))
    wire = Wire(reply=http_reply(200, ok_completion_body())).install(monkeypatch)
    client = UrllibOpenAICompatibleClient(api_key=PROVIDER_KEY, base_url="https://openrouter.ai/api/v1")
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    from optimus_gateway.models import flatten_messages_to_input_text, validate_chat_completions_envelope

    _model, validated, _metadata = validate_chat_completions_envelope({"model": "cn/alpha", "messages": messages})
    flattened = flatten_messages_to_input_text(validated)
    status, _ = handle_chat_completions_request(
        authorization_header=AUTH,
        request_body={"model": "cn/alpha", "messages": messages, "route_binding": binding(snapshot, input_text=flattened)},
        config=gateway_config(model_policy(snapshot)),
        upstream_client=client,
    )
    assert status == 200
    sent = wire.request_body(0)
    assert sent["messages"] == [{"role": "user", "content": flattened}]
    assert sent["cache_control"] == {"type": "ephemeral"}


@pytest.mark.parametrize("value", ["block", "per_block", "TOP_LEVEL", "true", "1", "{}"])
def test_an_unsupported_setting_is_refused_when_the_registry_loads(tmp_path, value):
    with pytest.raises(RegistryError) as refused:
        verified_snapshot(tmp_path, _with_cache(value))
    assert refused.value.code == "SCHEMA_INVALID"


def test_an_operator_override_sets_it_without_replacing_the_route(tmp_path):
    defaults = tmp_path / "defaults.yaml"
    defaults.write_text(VERIFIED_POLICY, encoding="utf-8")
    override = tmp_path / "override.yaml"
    override.write_text("models:\n  cn/alpha:\n    route:\n      prompt_cache: top_level\n", encoding="utf-8")
    plain = load_registry(defaults)
    chosen = load_registry(defaults, override)
    route = chosen.policy.models["cn/alpha"].route
    assert route.prompt_cache == "top_level"
    assert route.endpoints == plain.policy.models["cn/alpha"].route.endpoints
    assert chosen.effective_hash != plain.effective_hash


def _contributor_binding(snapshot, *, prompt_cache):
    entry = snapshot.policy.models["us/contrib"]
    authorization = issue_disclosure(
        disclosure_key(SHARED_SECRET),
        request_id="req-1",
        model_id="us/contrib",
        route=route_digest("us/contrib", entry),
        payload=payload_digest("us/contrib", (Message("user", "hi"),), CAP, reasoning=entry.default_reasoning, prompt_cache=prompt_cache),
    )
    return RouteBinding(registry_hash=snapshot.effective_hash, request_id="req-1", output_cap=CAP, disclosure=authorization).to_wire()


def test_a_contributor_disclosure_covers_the_cached_payload_it_was_issued_for(monkeypatch, tmp_path):
    snapshot = verified_snapshot(tmp_path, _with_cache("top_level", count=2))
    wire = Wire(reply=http_reply(200, ok_completion_body())).install(monkeypatch)
    client = UrllibOpenAICompatibleClient(api_key=PROVIDER_KEY, base_url="https://openrouter.ai/api/v1")
    config = gateway_config(model_policy(snapshot))
    status, reply = _send("responses", config, client, model="us/contrib", route_binding=_contributor_binding(snapshot, prompt_cache=None))
    assert (status, reply["code"]) == (400, "DISCLOSURE_INVALID")
    assert wire.sent == []
    status, _ = _send("responses", config, client, model="us/contrib", route_binding=_contributor_binding(snapshot, prompt_cache="top_level"))
    assert status == 200
    assert wire.request_body(0)["cache_control"] == {"type": "ephemeral"}
