"""Plan 12.2 Task 5: trusted registry composition and the per-request route binding.

Enforcement is built but inactive (operator decision 2026-10-02): nothing composes a trusted snapshot
until ``ENFORCEMENT_ACTIVE`` is flipped in a reviewed change. These tests prove the inactive default,
what activation would compose, and that the binding and disclosure primitives bind exactly the
request, route and payload they name.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from optimus_model_policy import Message, load_registry
from optimus_model_policy import binding as binding_module
from optimus_model_policy.binding import (
    ENFORCEMENT_ACTIVE,
    BindingError,
    DisclosureAuthorization,
    RouteBinding,
    approval_literal,
    compose_trusted_snapshot,
    disclosure_key,
    issue_disclosure,
    packaged_defaults,
    payload_digest,
    route_digest,
    trusted_approval_literal,
    trusted_snapshot,
    verify_disclosure,
)

_FIXTURE = """\
schema_version: 1
policy_version: "binding-fixture"
fixture: true
context_ceiling_tokens: 262144
output_reserve_tokens: {}
estimators: {}
role_price_blends: {}
alerts: {thresholds_usd: []}
models: {}
roles: {}
"""


def test_enforcement_ships_inactive() -> None:
    assert ENFORCEMENT_ACTIVE is False
    assert trusted_snapshot() is None
    assert trusted_approval_literal() is None


def test_activation_composes_the_packaged_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(binding_module, "ENFORCEMENT_ACTIVE", True)
    snapshot = trusted_snapshot()
    assert snapshot is not None
    assert snapshot.effective_hash == load_registry(packaged_defaults(), None).effective_hash
    literal = trusted_approval_literal()
    assert literal is not None and re.fullmatch(r"optimus-model-registry-v1:[0-9a-f]{64}", literal)
    assert literal == approval_literal(snapshot)
    assert len(literal.encode()) < 100, "bounded: the approval record stores the hash, not the registry"


def test_a_fixture_registry_is_never_trusted(tmp_path: Path) -> None:
    path = tmp_path / "fixture.yaml"
    path.write_text(_FIXTURE, encoding="utf-8")
    with pytest.raises(BindingError) as caught:
        compose_trusted_snapshot(path)
    assert caught.value.code == "FIXTURE_POLICY"


# --- Route binding wire ---------------------------------------------------------------------------

_HASH = "a" * 64


def test_route_binding_round_trips_through_its_wire_form() -> None:
    disclosure = DisclosureAuthorization(route_digest="b" * 64, payload_digest="c" * 64, mac="d" * 64)
    for value in (
        RouteBinding(registry_hash=_HASH, request_id="req-1", output_cap=4096),
        RouteBinding(registry_hash=_HASH, request_id="req-1", output_cap=4096, disclosure=disclosure),
    ):
        wire = value.to_wire()
        assert wire["version"] == 1
        assert RouteBinding.from_wire(wire) == value
    assert "disclosure" not in RouteBinding(registry_hash=_HASH, request_id="r", output_cap=1).to_wire()


def test_a_null_disclosure_reads_as_absent() -> None:
    wire = {"version": 1, "registry_hash": _HASH, "request_id": "r", "output_cap": 1, "disclosure": None}
    assert RouteBinding.from_wire(wire).disclosure is None


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda w: w.pop("version"), "BINDING_MALFORMED"),
        (lambda w: w.update(version=0), "BINDING_VERSION_UNSUPPORTED"),
        (lambda w: w.update(version=1.0), "BINDING_MALFORMED"),
        (lambda w: w.update(surprise=True), "BINDING_MALFORMED"),
        (lambda w: w.update(output_cap=1.5), "BINDING_MALFORMED"),
        (lambda w: w.update(request_id=7), "BINDING_MALFORMED"),
        (lambda w: w.update(registry_hash="g" * 64), "BINDING_MALFORMED"),
        (lambda w: w.update(registry_hash="a" * 63), "BINDING_MALFORMED"),
        (lambda w: w.update(disclosure="yes"), "BINDING_MALFORMED"),
        (lambda w: w.update(disclosure={"route_digest": "b" * 64, "payload_digest": "c" * 64, "mac": "D" * 64}), "BINDING_MALFORMED"),
    ],
)
def test_route_binding_parsing_is_strict(mutation, code: str) -> None:
    wire = {"version": 1, "registry_hash": _HASH, "request_id": "r", "output_cap": 1}
    mutation(wire)
    with pytest.raises(BindingError) as caught:
        RouteBinding.from_wire(wire)
    assert caught.value.code == code


# --- Digests and disclosure -----------------------------------------------------------------------


def _alpha(tmp_path: Path):
    from tests.unit.optimus_gateway.model_policy_support import verified_snapshot

    snapshot = verified_snapshot(tmp_path)
    return snapshot, snapshot.policy.models["cn/alpha"]


def test_payload_digest_covers_model_roles_content_and_cap() -> None:
    base = payload_digest("m", (Message("user", "hi"),), 10)
    assert payload_digest("m", (Message("user", "hi"),), 10) == base
    for changed in (
        payload_digest("n", (Message("user", "hi"),), 10),
        payload_digest("m", (Message("system", "hi"),), 10),
        payload_digest("m", (Message("user", "hi "),), 10),
        payload_digest("m", (Message("user", "hi"), Message("user", "")), 10),
        payload_digest("m", (Message("user", "hi"),), 11),
    ):
        assert changed != base


def test_route_digest_changes_with_the_endpoint_allow_set(tmp_path: Path) -> None:
    snapshot, entry = _alpha(tmp_path)
    base = route_digest("cn/alpha", entry)
    assert route_digest("cn/other", entry) != base
    narrowed = entry.model_copy(update={"route": entry.route.model_copy(update={"endpoints": entry.route.endpoints[:1]})})
    assert route_digest("cn/alpha", narrowed) != base


def test_disclosure_verifies_only_for_its_request_route_payload_and_launch(tmp_path: Path) -> None:
    _, entry = _alpha(tmp_path)
    key = disclosure_key("launch-secret")
    route = route_digest("cn/alpha", entry)
    payload = payload_digest("cn/alpha", (Message("user", "hi"),), 10)
    authorization = issue_disclosure(key, request_id="req-1", model_id="cn/alpha", route=route, payload=payload)
    assert verify_disclosure(key, authorization, request_id="req-1", model_id="cn/alpha", route=route, payload=payload)

    other_payload = payload_digest("cn/alpha", (Message("user", "hi!"),), 10)
    other_route = route_digest("cn/beta", entry)
    for kwargs in (
        {"request_id": "req-2", "model_id": "cn/alpha", "route": route, "payload": payload},
        {"request_id": "req-1", "model_id": "cn/beta", "route": route, "payload": payload},
        {"request_id": "req-1", "model_id": "cn/alpha", "route": other_route, "payload": payload},
        {"request_id": "req-1", "model_id": "cn/alpha", "route": route, "payload": other_payload},
    ):
        assert not verify_disclosure(key, authorization, **kwargs), kwargs
    assert not verify_disclosure(
        disclosure_key("another-launch"), authorization, request_id="req-1", model_id="cn/alpha", route=route, payload=payload
    )


def test_an_authorization_must_state_exactly_what_it_covers(tmp_path: Path) -> None:
    """A valid MAC with a misstated digest is still refused, so a recorded authorization never
    claims a payload or route it was not issued for."""
    from dataclasses import replace

    _, entry = _alpha(tmp_path)
    key = disclosure_key("launch-secret")
    route = route_digest("cn/alpha", entry)
    payload = payload_digest("cn/alpha", (Message("user", "hi"),), 10)
    authorization = issue_disclosure(key, request_id="req-1", model_id="cn/alpha", route=route, payload=payload)
    for misstated in (replace(authorization, payload_digest="0" * 64), replace(authorization, route_digest="0" * 64)):
        assert not verify_disclosure(key, misstated, request_id="req-1", model_id="cn/alpha", route=route, payload=payload)


def test_moving_text_between_request_and_model_never_reuses_a_mac() -> None:
    """Fields are length-prefixed: ("ab", "c/d") and ("a", "bc/d") are different authorizations."""
    key = disclosure_key("launch-secret")
    route, payload = "a" * 64, "b" * 64
    first = issue_disclosure(key, request_id="ab", model_id="c/d", route=route, payload=payload)
    shifted = issue_disclosure(key, request_id="a", model_id="bc/d", route=route, payload=payload)
    assert first.mac != shifted.mac
    assert not verify_disclosure(key, first, request_id="a", model_id="bc/d", route=route, payload=payload)


def test_disclosure_key_is_domain_separated_from_the_shared_secret() -> None:
    key = disclosure_key("launch-secret")
    assert len(key) == 32
    assert key != b"launch-secret" and key != disclosure_key("launch-secret2")
