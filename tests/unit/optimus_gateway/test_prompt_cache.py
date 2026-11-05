"""Plan 12.10 Task 4: a route's optional prompt caching. Saying nothing keeps every approved hash and wire byte; opting in enters the
identities; only `top_level` changes what is sent. The wire tests read the real client's bytes, not a fake's keywords."""

from __future__ import annotations

from pathlib import Path

import pytest

import optimus_gateway.responses as responses_module
from optimus.gateway.disclosure import ContributorDisclosure
from optimus.gateway.route_binding import RoutePolicy
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


def test_the_hosts_own_disclosure_is_accepted_for_a_cached_route(monkeypatch, tmp_path):
    """Not a binding built for the test: the one the host really signs must cover the control the Gateway will send."""
    snapshot = verified_snapshot(tmp_path, _with_cache("top_level", count=2))
    wire = Wire(reply=http_reply(200, ok_completion_body())).install(monkeypatch)
    client = UrllibOpenAICompatibleClient(api_key=PROVIDER_KEY, base_url="https://openrouter.ai/api/v1")
    disclosure = ContributorDisclosure(snapshot=snapshot, key=disclosure_key(SHARED_SECRET), deliver_notice=lambda _notice: True)
    made = disclosure.binding(model_id="us/contrib", request_id="req-1", input_text="hi", output_cap=CAP)
    assert made is not None
    status, _ = _send("responses", gateway_config(model_policy(snapshot)), client, model="us/contrib", route_binding=made.to_wire())
    assert status == 200 and wire.request_body(0)["cache_control"] == {"type": "ephemeral"}


@pytest.mark.parametrize("mode", [None, "none", "implicit"])
def test_the_client_itself_adds_nothing_for_any_other_setting(monkeypatch, mode):
    wire = Wire(reply=http_reply(200, ok_completion_body())).install(monkeypatch)
    client = UrllibOpenAICompatibleClient(api_key=PROVIDER_KEY, base_url="https://openrouter.ai/api/v1")
    client.create_message_once(model="cn/alpha", input_text="hi", max_tokens=CAP, provider_controls={}, reasoning=None, prompt_cache=mode)
    assert "cache_control" not in wire.request_body(0)


# --- ADR-039: the prefix mode caches only the stable start of a request ---------------------------------

PREFIX_TEXT = "fixed text and map \U0001f600 end\n"
QUESTION = "\nCurrent question: one\n"


def _prefix_binding(snapshot, *, chars: int | None = len(PREFIX_TEXT)) -> dict:
    return RouteBinding(registry_hash=snapshot.effective_hash, request_id="req-1", output_cap=CAP, cache_prefix_chars=chars).to_wire()


def _real_client() -> UrllibOpenAICompatibleClient:
    return UrllibOpenAICompatibleClient(api_key=PROVIDER_KEY, base_url="https://openrouter.ai/api/v1")


def _binder(snapshot):
    policy = RoutePolicy(snapshot=snapshot, disclosure_key=disclosure_key(SHARED_SECRET), model_id="cn/alpha", role="medium", output_cap=CAP)
    return policy.capture(session_id="s", turn_seq=1, deliver_notice=lambda _notice: True)


def test_a_named_prefix_changes_the_payload_identity_and_no_prefix_does_not():
    messages = (Message("user", "hi"),)
    base = payload_digest("cn/alpha", messages, CAP, reasoning="high")
    assert payload_digest("cn/alpha", messages, CAP, reasoning="high", prompt_cache="prefix") == base
    named = payload_digest("cn/alpha", messages, CAP, reasoning="high", prompt_cache="prefix", cache_prefix_chars=1)
    assert named != base
    assert named != payload_digest("cn/alpha", messages, CAP, reasoning="high", prompt_cache="prefix", cache_prefix_chars=2)
    assert named != payload_digest("cn/alpha", messages, CAP, reasoning="high", prompt_cache="top_level")


def test_the_prefix_setting_enters_the_registry_and_route_identities(tmp_path):
    plain = verified_snapshot(tmp_path)
    chosen = verified_snapshot(tmp_path, _with_cache("prefix"))
    assert chosen.effective_hash != plain.effective_hash
    assert route_digest("cn/alpha", chosen.policy.models["cn/alpha"]) != route_digest("cn/alpha", plain.policy.models["cn/alpha"])


@pytest.mark.parametrize("route", ["responses", "chat"])
def test_a_prefix_route_with_nothing_named_sends_the_baseline_wire(monkeypatch, tmp_path, route):
    assert _wire_body(monkeypatch, tmp_path, _with_cache("prefix"), route) == BASELINE_WIRE


@pytest.mark.parametrize("route", ["responses", "chat"])
def test_a_named_prefix_is_two_blocks_with_only_the_first_marked(monkeypatch, tmp_path, route):
    snapshot = verified_snapshot(tmp_path, _with_cache("prefix"))
    wire = Wire(reply=http_reply(200, ok_completion_body())).install(monkeypatch)
    tail = QUESTION.rstrip()  # the chat route strips, so this text survives flattening unchanged
    status, _ = _send(route, gateway_config(model_policy(snapshot)), _real_client(), text=PREFIX_TEXT + tail, route_binding=_prefix_binding(snapshot))
    assert status == 200
    sent = wire.request_body(0)
    assert "cache_control" not in sent  # no root control: that would write the whole prompt again
    assert sent["messages"] == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": PREFIX_TEXT, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": tail},
            ],
        }
    ]
    assert sent["provider"] == BASELINE_WIRE["provider"] and sent["max_tokens"] == CAP and sent["reasoning"] == {"effort": "high"}


def test_on_the_chat_route_the_offset_counts_the_flattened_text(monkeypatch, tmp_path):
    """Flattening strips the ends, so an offset computed before it would cut in the wrong place."""
    from optimus_gateway.models import flatten_messages_to_input_text, validate_chat_completions_envelope

    snapshot = verified_snapshot(tmp_path, _with_cache("prefix"))
    wire = Wire(reply=http_reply(200, ok_completion_body())).install(monkeypatch)
    messages = [{"role": "user", "content": f"   {PREFIX_TEXT}{QUESTION}   "}]
    _model, validated, _metadata = validate_chat_completions_envelope({"model": "cn/alpha", "messages": messages})
    flattened = flatten_messages_to_input_text(validated)
    assert flattened != messages[0]["content"]
    status, _ = handle_chat_completions_request(
        authorization_header=AUTH,
        request_body={"model": "cn/alpha", "messages": messages, "route_binding": _prefix_binding(snapshot, chars=flattened.index("\n") + 1)},
        config=gateway_config(model_policy(snapshot)),
        upstream_client=_real_client(),
    )
    assert status == 200
    blocks = wire.request_body(0)["messages"][0]["content"]
    assert blocks[0]["text"] + blocks[1]["text"] == flattened and blocks[0]["text"] == PREFIX_TEXT


def test_two_questions_send_byte_identical_first_blocks_through_the_real_binder(monkeypatch, tmp_path):
    snapshot = verified_snapshot(tmp_path, _with_cache("prefix"))
    wire = Wire(reply=http_reply(200, ok_completion_body())).install(monkeypatch)
    binder = _binder(snapshot)
    config = gateway_config(model_policy(snapshot))
    for question in ("\nCurrent question: one\n", "\nCurrent question: a different one\n"):
        text = PREFIX_TEXT + question
        bound = binder.bind(stage="answer", input_text=text, stable_prefix=PREFIX_TEXT)
        assert bound is not None
        status, _ = _send("responses", config, _real_client(), text=text, route_binding=bound.binding.to_wire())
        assert status == 200
    first, second = (wire.request_body(index)["messages"][0]["content"] for index in (0, 1))
    assert first[0] == second[0] and first[0]["text"] == PREFIX_TEXT and first[1] != second[1]


@pytest.mark.parametrize("mode", [None, "none", "implicit", "top_level"])
def test_the_host_names_no_prefix_on_a_route_not_approved_for_one(tmp_path, mode):
    snapshot = verified_snapshot(tmp_path, VERIFIED_POLICY if mode is None else _with_cache(mode))
    bound = _binder(snapshot).bind(stage="answer", input_text=PREFIX_TEXT + QUESTION, stable_prefix=PREFIX_TEXT)
    assert bound is not None and "cache_prefix_chars" not in bound.binding.to_wire()


def test_text_that_does_not_begin_with_the_prefix_names_none(tmp_path):
    binder = _binder(verified_snapshot(tmp_path, _with_cache("prefix")))
    assert binder.bind(stage="answer", input_text="something else", stable_prefix=PREFIX_TEXT).binding.cache_prefix_chars is None
    assert binder.bind(stage="answer", input_text="anything").binding.cache_prefix_chars is None


@pytest.mark.parametrize("bad", [0, -1, True, False, 1.5, "5", [1], {}])
def test_a_malformed_offset_is_refused_when_the_binding_is_parsed(tmp_path, monkeypatch, bad):
    snapshot = verified_snapshot(tmp_path, _with_cache("prefix"))
    wire = Wire(reply=http_reply(200, ok_completion_body())).install(monkeypatch)
    raw = {**_prefix_binding(snapshot, chars=None), "cache_prefix_chars": bad}
    status, reply = _send("responses", gateway_config(model_policy(snapshot)), _real_client(), route_binding=raw)
    assert (status, reply["code"]) == (400, "BINDING_MALFORMED") and wire.sent == []


@pytest.mark.parametrize(
    "text, chars",
    [
        ("hi", 2),  # at the end: the second block would be empty
        ("hi", 3),  # past the end
        ("hi   ", 2),  # the second block would be blank
        ("   hi", 3),  # the first block would be blank
    ],
)
def test_an_offset_that_cannot_split_the_input_reaches_no_provider(monkeypatch, tmp_path, text, chars):
    snapshot = verified_snapshot(tmp_path, _with_cache("prefix"))
    wire = Wire(reply=http_reply(200, ok_completion_body())).install(monkeypatch)
    status, reply = _send("responses", gateway_config(model_policy(snapshot)), _real_client(), text=text, route_binding=_prefix_binding(snapshot, chars=chars))
    assert (status, reply["code"]) == (400, "CACHE_PREFIX_INVALID") and wire.sent == []


@pytest.mark.parametrize("mode", [None, "none", "implicit", "top_level"])
def test_a_route_not_approved_for_a_prefix_refuses_one(monkeypatch, tmp_path, mode):
    snapshot = verified_snapshot(tmp_path, VERIFIED_POLICY if mode is None else _with_cache(mode))
    wire = Wire(reply=http_reply(200, ok_completion_body())).install(monkeypatch)
    status, reply = _send("responses", gateway_config(model_policy(snapshot)), _real_client(), text=PREFIX_TEXT + QUESTION, route_binding=_prefix_binding(snapshot))
    assert (status, reply["code"]) == (400, "CACHE_PREFIX_INVALID") and wire.sent == []


def test_a_contributor_disclosure_covers_the_prefix_it_was_issued_for(monkeypatch, tmp_path):
    """The host's real disclosure is accepted; moving or dropping the boundary afterwards is not the payload it covers."""
    snapshot = verified_snapshot(tmp_path, _with_cache("prefix", count=2))
    wire = Wire(reply=http_reply(200, ok_completion_body())).install(monkeypatch)
    disclosure = ContributorDisclosure(snapshot=snapshot, key=disclosure_key(SHARED_SECRET), deliver_notice=lambda _notice: True)
    text = PREFIX_TEXT + QUESTION
    made = disclosure.binding(model_id="us/contrib", request_id="req-1", input_text=text, output_cap=CAP, cache_prefix_chars=len(PREFIX_TEXT))
    assert made is not None
    config = gateway_config(model_policy(snapshot))
    moved = {**made.to_wire(), "cache_prefix_chars": len(PREFIX_TEXT) - 1}
    status, reply = _send("responses", config, _real_client(), model="us/contrib", text=text, route_binding=moved)
    assert (status, reply["code"]) == (400, "DISCLOSURE_INVALID") and wire.sent == []
    removed = {key: value for key, value in made.to_wire().items() if key != "cache_prefix_chars"}
    status, reply = _send("responses", config, _real_client(), model="us/contrib", text=text, route_binding=removed)
    assert (status, reply["code"]) == (400, "DISCLOSURE_INVALID") and wire.sent == []
    status, _ = _send("responses", config, _real_client(), model="us/contrib", text=text, route_binding=made.to_wire())
    assert status == 200 and wire.request_body(0)["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}


def test_a_recovery_attempt_resends_the_identical_two_blocks(monkeypatch, tmp_path):
    monkeypatch.setattr(responses_module, "_sleep", lambda _seconds: None)
    snapshot = verified_snapshot(tmp_path, _with_cache("prefix"))
    wire = Wire(replies=[http_reply(429), http_reply(200, ok_completion_body())]).install(monkeypatch)
    status, _ = _send("responses", gateway_config(model_policy(snapshot)), _real_client(), text=PREFIX_TEXT + QUESTION, route_binding=_prefix_binding(snapshot))
    assert status == 200 and len(wire.sent) == 2
    assert wire.request_body(0) == wire.request_body(1)
    assert wire.request_body(0)["messages"][0]["content"][0]["text"] == PREFIX_TEXT
