"""#465 on the real Gateway HTTP surface: the identity route, and a bound request refused before any upstream use."""

from __future__ import annotations

import http.client
import json
import threading
from collections.abc import Iterator
from dataclasses import replace
from decimal import Decimal

import pytest

from optimus.acp import launch_policy
from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import GatewayClient
from optimus.gateway.errors import GatewayHttpError
from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.server import serve_gateway
from optimus_gateway.upstream_client import ProviderMessageResult
from optimus_security import gateway_identity as gi

_MODEL = "claude-haiku"
SHARED_SECRET = "identity-test-secret"  # pragma: allowlist secret - synthetic test fixture
_HMAC_KEY = b"k" * 32


def _identity(**overrides: object) -> gi.GatewayIdentity:
    values: dict[str, object] = {
        "provider": "openrouter",
        "base_url": "http://127.0.0.1:9/api/v1",
        "provider_api_key": "sk-or-test",  # pragma: allowlist secret - synthetic test fixture
        "shared_secret": SHARED_SECRET,
        "composition": gi.COMPOSITION_STANDARD,
        "model_registry": "registry-literal",
        "stage_c_envelope": None,
        "accounting": "accounting-literal",
        "tool_environ": {},
        "hmac_key": _HMAC_KEY,
    }
    values.update(overrides)
    return gi.compose_identity(**values)  # type: ignore[arg-type]


class _Upstream:
    def __init__(self) -> None:
        self.calls = 0

    def create_message(self, *, model: str, input_text: str) -> ProviderMessageResult:
        self.calls += 1
        return ProviderMessageResult(message_id="m", output_text=input_text, input_tokens=1, output_tokens=1, total_tokens=2,
                                     billing_units=2, cost_usd=Decimal("0.00001"), provider="openrouter", resolved_provider=None, requested_model=model,
                                     resolved_model=model, model_version=None, cache_hit=False)


@pytest.fixture
def gateway() -> Iterator[tuple[int, _Upstream]]:
    upstream = _Upstream()
    config = GatewayServiceConfig(
        bind_host="127.0.0.1", bind_port=0, shared_secret=SHARED_SECRET, provider="openrouter",
        provider_api_key="sk-or-test",  # pragma: allowlist secret - synthetic test fixture
        base_url="http://127.0.0.1:9/api/v1",
    )
    config = replace(config, local_identity=gi.ServedIdentity(_identity(), gi.proof_key(_HMAC_KEY)))
    server = serve_gateway(config=config, upstream_client=upstream)  # type: ignore[arg-type]
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], upstream
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def _post(port: int, path: str, body: bytes, headers: dict[str, str] | None = None) -> tuple[int, dict[str, object]]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("POST", path, body=body, headers={"Content-Type": "application/json", **(headers or {})})
        reply = connection.getresponse()
        return reply.status, json.loads(reply.read())
    finally:
        connection.close()


_AUTH = {"Authorization": f"Bearer {SHARED_SECRET}"}


def test_the_route_proves_the_served_identity_for_this_nonce(gateway) -> None:
    port, upstream = gateway
    nonce = gi.new_nonce()
    status, reply = _post(port, gi.PATH, gi.build_request(nonce), _AUTH)
    assert status == 200
    assert gi.read_reply(reply, nonce=nonce, hmac_key=_HMAC_KEY).digest == _identity().digest
    assert upstream.calls == 0


def test_a_replayed_reply_fails_for_a_new_nonce(gateway) -> None:
    port, _ = gateway
    nonce = gi.new_nonce()
    _, reply = _post(port, gi.PATH, gi.build_request(nonce), _AUTH)
    with pytest.raises(gi.IdentityReplyError):
        gi.read_reply(reply, nonce=gi.new_nonce(), hmac_key=_HMAC_KEY)


def test_the_route_refuses_a_wrong_key_before_reading_anything(gateway) -> None:
    port, _ = gateway
    status, reply = _post(port, gi.PATH, gi.build_request(gi.new_nonce()), {"Authorization": "Bearer wrong"})
    assert status == 401
    assert "fields" not in reply


@pytest.mark.parametrize("body", [b"{}", b"not json", b'{"nonce":"short"}', b'{"nonce":"' + b"a" * 32 + b'","x":1}'])
def test_the_route_refuses_anything_but_its_request(gateway, body: bytes) -> None:
    port, _ = gateway
    status, _reply = _post(port, gi.PATH, body, _AUTH)
    assert status == 400


def test_the_reply_carries_no_url_or_secret_in_the_clear(gateway) -> None:
    port, _ = gateway
    _, reply = _post(port, gi.PATH, gi.build_request(gi.new_nonce()), _AUTH)
    text = json.dumps(reply)
    for value in ("127.0.0.1:9", "sk-or-test", SHARED_SECRET, "registry-literal", "accounting-literal"):
        assert value not in text


@pytest.mark.parametrize("path", ["/v1/responses", "/v1/chat/completions", "/v1/decisions", "/v1/observability/usage-capture"])
def test_a_request_bound_to_another_identity_is_refused_before_dispatch(gateway, path: str) -> None:
    port, upstream = gateway
    body = json.dumps({"model": "m", "input": "x", "messages": [{"role": "user", "content": "x"}]}).encode()
    status, reply = _post(port, path, body, {**_AUTH, gi.HEADER: "0" * 64})
    assert status == 409
    assert reply == {"error": "gateway_identity_mismatch"}
    assert upstream.calls == 0


def test_a_refusal_answers_even_a_body_past_its_reading_limit(gateway) -> None:
    port, upstream = gateway
    status, reply = _post(port, "/v1/responses", b"x" * 200_000, {**_AUTH, gi.HEADER: "0" * 64})
    assert (status, reply) == (409, {"error": "gateway_identity_mismatch"})
    assert upstream.calls == 0


def test_the_real_gateway_client_stops_on_a_replaced_gateway_with_no_upstream_use(gateway) -> None:
    """The port-replacement race: the check passed against one Gateway, and another now holds the port."""
    port, upstream = gateway
    settings = OptimusGatewaySettings(gateway_url=f"http://127.0.0.1:{port}", optimus_api_key=SHARED_SECRET,
                                      gateway_identity="0" * 64)
    with pytest.raises(GatewayHttpError) as raised:
        GatewayClient(settings=settings).create_response(model="m", input_text="x")
    assert raised.value.status_code == 409
    assert upstream.calls == 0


def test_the_real_gateway_client_bound_to_this_identity_reaches_the_upstream(gateway) -> None:
    port, upstream = gateway
    settings = OptimusGatewaySettings(gateway_url=f"http://127.0.0.1:{port}", optimus_api_key=SHARED_SECRET,
                                      gateway_identity=_identity().digest)
    GatewayClient(settings=settings).create_response(model=_MODEL, input_text="x")
    assert upstream.calls == 1


def test_a_request_with_no_binding_is_not_refused(gateway) -> None:
    """A caller with no expectation has nothing to be bound to; it still needs the key."""
    port, upstream = gateway
    body = json.dumps({"model": _MODEL, "input": "x"}).encode()
    status, _reply = _post(port, "/v1/responses", body, _AUTH)
    assert status == 200
    assert upstream.calls == 1


def test_a_gateway_with_no_identity_ignores_binding_and_has_no_route() -> None:
    upstream = _Upstream()
    config = GatewayServiceConfig(
        bind_host="127.0.0.1", bind_port=0, shared_secret=SHARED_SECRET, provider="openrouter",
        provider_api_key="sk-or-test",  # pragma: allowlist secret - synthetic test fixture
        base_url="http://127.0.0.1:9/api/v1",
    )
    server = serve_gateway(config=config, upstream_client=upstream)  # type: ignore[arg-type]
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        status, _reply = _post(server.server_address[1], gi.PATH, gi.build_request(gi.new_nonce()), _AUTH)
        assert status == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


@pytest.mark.parametrize(
    ("field", "overrides"),
    [
        ("upstream", {"base_url": "http://127.0.0.1:10/api/v1"}),
        ("upstream_credential", {"provider_api_key": "sk-or-other"}),  # pragma: allowlist secret - synthetic test fixture
        ("gateway_key", {"shared_secret": "other"}),  # pragma: allowlist secret - synthetic test fixture
        ("registry", {"model_registry": "other-registry"}),
        ("composition", {"composition": gi.COMPOSITION_AUTO}),
        ("stage_c", {"stage_c_envelope": "envelope"}),
        ("accounting", {"accounting": None}),
        ("tool_policy", {"tool_environ": {"OPTIMUS_GATEWAY_TOOL_ALLOWED_DOMAINS": "example.com"}}),
    ],
)
def test_every_compatibility_field_changes_only_its_own_fingerprint(field: str, overrides: dict[str, object]) -> None:
    expected, other = _identity(), _identity(**overrides)
    assert gi.differing_fields(expected, other) == (field,)
    assert expected.digest != other.digest


def test_nothing_about_the_workspace_or_the_session_can_enter_the_identity() -> None:
    assert not {"workspace", "branch", "security_snapshot", "session", "nonce", "expiry"} & set(gi.FIELD_LABELS)


def test_the_same_configuration_has_the_same_identity_in_every_session() -> None:
    assert _identity() == _identity()


def test_a_url_spelled_differently_is_the_same_destination() -> None:
    assert _identity(base_url="HTTP://127.0.0.1:9/api/v1/").digest == _identity().digest


def test_a_tool_setting_absent_equals_a_blank_one() -> None:
    assert _identity(tool_environ={"TAVILY_API_KEY": "  "}).digest == _identity().digest


def test_the_tool_names_are_the_ones_the_launch_projects_to_the_gateway() -> None:
    assert set(gi.TOOL_POLICY_NAMES) == set(launch_policy.GATEWAY_TOOL_CHILD_ENV_NAMES)


def test_a_reply_under_another_key_fails_even_with_its_own_proof() -> None:
    other = b"o" * 32
    nonce = gi.new_nonce()
    served = gi.ServedIdentity(_identity(hmac_key=other), gi.proof_key(other))
    with pytest.raises(gi.IdentityReplyError):
        gi.read_reply(served.reply(nonce), nonce=nonce, hmac_key=_HMAC_KEY)


def test_a_replay_with_its_nonce_rewritten_fails_on_its_proof() -> None:
    """No key is needed to rewrite a field of an old reply, so the proof is what stops this one."""
    served = gi.ServedIdentity(_identity(), gi.proof_key(_HMAC_KEY))
    nonce = gi.new_nonce()
    replayed = {**served.reply(gi.new_nonce()), "nonce": nonce}
    with pytest.raises(gi.IdentityReplyError, match="proof"):
        gi.read_reply(replayed, nonce=nonce, hmac_key=_HMAC_KEY)


def test_a_reply_naming_another_nonce_fails_even_with_a_good_proof() -> None:
    served = gi.ServedIdentity(_identity(), gi.proof_key(_HMAC_KEY))
    nonce = gi.new_nonce()
    with pytest.raises(gi.IdentityReplyError, match="nonce"):
        gi.read_reply({**served.reply(nonce), "nonce": gi.new_nonce()}, nonce=nonce, hmac_key=_HMAC_KEY)


def test_a_served_identity_never_shows_its_key() -> None:
    served = gi.ServedIdentity(_identity(), gi.proof_key(_HMAC_KEY))
    assert gi.proof_key(_HMAC_KEY).hex() not in repr(served)
    assert str(gi.proof_key(_HMAC_KEY)) not in repr(served)
