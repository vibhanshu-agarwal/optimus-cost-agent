"""Plan 12.2 Haiku 5.5 experimental test profile (operator release and Codex disposition, 2026-10-09).

The qualification profile is Claude Haiku 5.5 on OpenRouter's first-party Anthropic endpoint. Two
test-only exceptions apply, and only to the reviewed profile's exact pinned snapshot hash:

- an EMPIRICAL size estimate (``utf8-bytes-ratio-empirical``): one token per UTF-8 byte plus a framing
  allowance, recorded as an engineering estimate rather than a publisher-proven bound (``verified``
  stays false and keeps its meaning);
- provider-family routing: the generic ``anthropic`` slug, which OpenRouter documents can reach every
  variant or region of that provider.

Neither exception is a YAML flag: any other snapshot, including a copy of the same override with any
policy value changed, gets the ordinary refusals.
"""

from __future__ import annotations

from decimal import Decimal
from importlib import resources
from pathlib import Path

import pytest

from optimus_model_policy import Message, PackedModelRequest, Role, guard_request, select_eligible_models, validate_registry
from optimus_model_policy import test_profiles as profiles
from optimus_model_policy.binding import packaged_defaults, trusted_snapshot
from optimus_model_policy.experimental import (
    EXPERIMENTAL_ROUTES,
    HAIKU_ATTACHED_HASH,
    HAIKU_QUALIFICATION_HASH,
    SHIPPED_DEFAULTS_HASH,
    experimental_route,
)
from optimus_model_policy.registry import RegistrySnapshot, load_registry

HAIKU = "anthropic/claude-haiku-5.5"


def _profile() -> RegistrySnapshot:
    return profiles.compose_test_profile_snapshot("qualification")


def _tampered(tmp_path: Path) -> RegistrySnapshot:
    """The reviewed override with one policy value changed (the framing allowance, 256 -> 255): the same
    model and route under a different composed snapshot."""
    original = resources.files("optimus_model_policy").joinpath("test_profile_qualification.yaml").read_text(encoding="utf-8")
    assert original.count("fixed_tokens: 256") == 1
    copy = tmp_path / "copy.yaml"
    copy.write_text(original.replace("fixed_tokens: 256", "fixed_tokens: 255"), encoding="utf-8")
    return load_registry(packaged_defaults(), copy)


def test_a_comment_only_edit_keeps_the_composed_snapshot(tmp_path: Path) -> None:
    """The pin identifies the composed policy, not the file's bytes: comments do not change it."""
    original = resources.files("optimus_model_policy").joinpath("test_profile_qualification.yaml").read_text(encoding="utf-8")
    copy = tmp_path / "comment.yaml"
    copy.write_text(original + "# a reviewer's note\n", encoding="utf-8")
    assert load_registry(packaged_defaults(), copy).effective_hash == _profile().effective_hash


def _request(content: str, *, output_cap: int = 32_768) -> PackedModelRequest:
    return PackedModelRequest(model_id=HAIKU, messages=(Message(role="user", content=content),), tools_json="", output_cap=output_cap)


def test_the_qualification_profile_is_the_haiku_route_with_its_inspected_facts() -> None:
    snapshot = _profile()
    haiku = snapshot.policy.models[HAIKU]
    [endpoint] = haiku.route.endpoints

    assert (endpoint.provider, endpoint.quantization, endpoint.context_window_tokens, endpoint.max_output_tokens, endpoint.verified) == (
        "anthropic", "unknown", 1_000_000, 128_000, True
    )  # fmt: skip
    # Reservation prices are the higher published tier (prompts over 100,000 tokens).
    assert (haiku.prices.input_usd_per_million, haiku.prices.output_usd_per_million) == (Decimal("0.50"), Decimal("2.50"))
    assert haiku.default_reasoning == "low" and "low" in haiku.capabilities.reasoning_levels
    assert haiku.route.allow_fallbacks is False and haiku.route.require_parameters is True

    estimator = snapshot.policy.estimators[haiku.route.estimator]
    assert (estimator.method, estimator.tokens_per_byte, estimator.verified) == ("utf8-bytes-ratio-empirical", Decimal(1), False)
    assert snapshot.policy.roles[Role.EASY] == (HAIKU,)
    assert profiles.TEST_PROFILES["qualification"].model_id == HAIKU


def test_the_pinned_profile_makes_haiku_eligible_for_the_test_agent_role() -> None:
    snapshot = _profile()
    assert select_eligible_models(snapshot, Role.EASY) == (HAIKU,)
    codes = {issue.code for issue in validate_registry(snapshot) if issue.model_id == HAIKU and issue.role is Role.EASY}
    assert codes == set()


def test_the_exceptions_belong_to_the_pinned_hash_not_to_the_yaml(tmp_path: Path) -> None:
    tampered = _tampered(tmp_path)
    assert tampered.effective_hash != _profile().effective_hash

    assert experimental_route(tampered, HAIKU) is None
    assert select_eligible_models(tampered, Role.EASY) == ()
    codes = {issue.code for issue in validate_registry(tampered) if issue.model_id == HAIKU and issue.role is Role.EASY}
    assert {"ESTIMATOR_UNVERIFIED", "ROUTE_TARGET_NOT_EXACT"} <= codes


def test_the_experimental_route_names_its_profile_model_family_and_provider() -> None:
    snapshot = _profile()
    route = experimental_route(snapshot, HAIKU)

    assert route is not None and EXPERIMENTAL_ROUTES[snapshot.effective_hash] == route
    assert (route.profile, route.model_id, route.provider_family, route.provider_name) == ("qualification", HAIKU, "anthropic", "Anthropic")
    assert experimental_route(snapshot, "openai/gpt-6-luna") is None


def test_the_empirical_estimate_counts_bytes_plus_the_framing_allowance() -> None:
    snapshot = _profile()
    estimator = snapshot.policy.estimators[snapshot.policy.models[HAIKU].route.estimator]
    content = "é" * 1_000  # 2,000 UTF-8 bytes

    decision = guard_request(_request(content), snapshot, snapshot.effective_hash)

    assert decision.allowed and decision.reason is None
    assert decision.input_tokens == 2_000 + estimator.per_message_tokens + estimator.fixed_tokens
    assert estimator.per_message_tokens + estimator.fixed_tokens > 0


def test_the_empirical_estimate_still_refuses_one_byte_over_capacity() -> None:
    snapshot = _profile()
    estimator = snapshot.policy.estimators[snapshot.policy.models[HAIKU].route.estimator]
    usable = 262_144 - 32_768
    fits = usable - estimator.per_message_tokens - estimator.fixed_tokens

    assert guard_request(_request("a" * fits), snapshot, snapshot.effective_hash).allowed
    refused = guard_request(_request("a" * (fits + 1)), snapshot, snapshot.effective_hash)
    assert (refused.allowed, refused.reason, refused.input_tokens) == (False, "INPUT_EXCEEDS_CAPACITY", usable + 1)


def test_outside_the_pinned_profile_the_empirical_estimate_is_unverified(tmp_path: Path) -> None:
    tampered = _tampered(tmp_path)
    decision = guard_request(_request("hello"), tampered, tampered.effective_hash)
    assert (decision.allowed, decision.reason) == (False, "ESTIMATOR_UNVERIFIED")


@pytest.mark.parametrize("pin", list(EXPERIMENTAL_ROUTES))
def test_every_experimental_pin_is_a_reviewed_test_profile_hash(pin: str) -> None:
    assert pin in {profile.effective_hash for profile in profiles.TEST_PROFILES.values()}


def test_the_shipped_exception_is_the_attached_pin_and_nothing_else() -> None:
    """Closure plan v3: the one shipped empirical exception is bound to the exact reviewed snapshot, which is the
    attached profile's. No other production snapshot is listed, and verified stays false."""
    shipped = trusted_snapshot()
    assert shipped is not None and shipped.effective_hash == SHIPPED_DEFAULTS_HASH == HAIKU_ATTACHED_HASH
    route = experimental_route(shipped, HAIKU)
    assert route is not None and route == EXPERIMENTAL_ROUTES[HAIKU_ATTACHED_HASH]
    assert shipped.policy.estimators[shipped.policy.models[HAIKU].route.estimator].verified is False
    assert set(EXPERIMENTAL_ROUTES) == {HAIKU_QUALIFICATION_HASH, HAIKU_ATTACHED_HASH}


def test_the_attached_profile_has_the_same_experimental_route_under_its_own_hash() -> None:
    """Profile B admits the same two exceptions, bound to its own pin (offline preparation batch, 2026-10-11)."""
    attached = profiles.compose_test_profile_snapshot("attached")
    route = experimental_route(attached, HAIKU)

    assert route is not None and EXPERIMENTAL_ROUTES[attached.effective_hash] == route
    assert (route.profile, route.model_id, route.provider_family, route.provider_name) == ("attached", HAIKU, "anthropic", "Anthropic")
    assert {r.profile for r in EXPERIMENTAL_ROUTES.values()} == {"qualification", "attached"}
    assert {pin for pin, r in EXPERIMENTAL_ROUTES.items()} == {profiles.TEST_PROFILES[r.profile].effective_hash for r in EXPERIMENTAL_ROUTES.values()}
