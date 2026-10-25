"""Per-model admission exceptions as registry data (Plan 12.4 v7 Design 1; ADR-025), on the Haiku 5.5 profiles.

The qualification profile is Claude Haiku 5.5 on OpenRouter's first-party Anthropic endpoint. Its entry's
``admission`` block carries two independent exceptions, each with its evidence and limitations:

- ``empirical_estimate``: a ``utf8-bytes-ratio-empirical`` estimate, one token per UTF-8 byte plus a framing
  allowance, recorded as an engineering estimate rather than a publisher-proven bound (``verified`` stays false);
- ``provider_family``: the generic ``anthropic`` slug, which OpenRouter documents can reach every variant or region
  of that provider.

The block is part of the canonical policy, so any change to it composes another effective hash, which the operator
approves before it is enforced. Without the block, the ordinary refusals apply.
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
    HAIKU_ATTACHED_HASH,
    HAIKU_QUALIFICATION_HASH,
    SHIPPED_DEFAULTS_HASH,
    ExperimentalRoute,
    experimental_route,
)
from optimus_model_policy.registry import RegistryError, RegistrySnapshot, load_registry

HAIKU = "anthropic/claude-haiku-5.5"
LUNA = "openai/gpt-6-luna"


def _profile() -> RegistrySnapshot:
    return profiles.compose_test_profile_snapshot("qualification")


def _profile_text() -> str:
    return resources.files("optimus_model_policy").joinpath("test_profile_qualification.yaml").read_text(encoding="utf-8")


def _edited(tmp_path: Path, old: str, new: str) -> RegistrySnapshot:
    text = _profile_text()
    assert text.count(old) == 1, old
    copy = tmp_path / "copy.yaml"
    copy.write_text(text.replace(old, new), encoding="utf-8")
    return load_registry(packaged_defaults(), copy)


def _without(tmp_path: Path, *parts: str) -> RegistrySnapshot:
    """The qualification profile with the named admission parts removed (the defaults carry none for this copy)."""
    text = _profile_text()
    start = text.index("    admission:\n")
    end = text.index("    # The shipped defaults carry")
    block = text[start:end]
    kept = {"empirical_estimate", "provider_family"} - set(parts)
    lines = ["    admission:\n"]
    for part in ("empirical_estimate", "provider_family"):
        if part in kept:
            body = block[block.index(f"      {part}:\n") :]
            following = [index for name in ("empirical_estimate", "provider_family") if name != part and (index := body.find(f"      {name}:\n", 1)) > 0]
            lines.append(body[: min(following)] if following else body)
        else:
            # Maps combine, so a part left out would come back from the defaults: removing one takes an explicit null.
            lines.append(f"      {part}: null\n")
    replacement = "".join(lines) if kept else "    admission: null\n"
    copy = tmp_path / "without.yaml"
    copy.write_text(text.replace(block, replacement), encoding="utf-8")
    # The packaged defaults carry Haiku's block too; replacing it with null (or one part) removes the rest.
    snapshot = load_registry(packaged_defaults(), copy)
    admission = snapshot.policy.models[HAIKU].admission
    assert (admission is None) == (not kept)
    return snapshot


def _request(content: str, *, output_cap: int = 32_768, model: str = HAIKU) -> PackedModelRequest:
    return PackedModelRequest(model_id=model, messages=(Message(role="user", content=content),), tools_json="", output_cap=output_cap)


def _haiku_codes(snapshot: RegistrySnapshot) -> set[str]:
    return {issue.code for issue in validate_registry(snapshot) if issue.model_id == HAIKU and issue.role is Role.EASY}


def test_a_comment_only_edit_keeps_the_composed_snapshot(tmp_path: Path) -> None:
    """The pin identifies the composed policy, not the file's bytes: comments do not change it."""
    copy = tmp_path / "comment.yaml"
    copy.write_text(_profile_text() + "# a reviewer's note\n", encoding="utf-8")
    assert load_registry(packaged_defaults(), copy).effective_hash == _profile().effective_hash


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


def test_the_admission_block_records_evidence_assumptions_and_limitations() -> None:
    admission = _profile().policy.models[HAIKU].admission
    assert admission is not None and admission.empirical_estimate is not None and admission.provider_family is not None
    assert admission.empirical_estimate.evidence and admission.empirical_estimate.assumptions and admission.empirical_estimate.limitations
    assert (admission.provider_family.provider, admission.provider_family.provider_name) == ("anthropic", "Anthropic")
    assert admission.provider_family.evidence and admission.provider_family.limitations


def test_the_profile_makes_haiku_eligible_for_the_test_agent_role() -> None:
    snapshot = _profile()
    assert select_eligible_models(snapshot, Role.EASY) == (HAIKU,)
    assert _haiku_codes(snapshot) == set()


def test_admission_is_data_so_a_changed_policy_value_keeps_it_under_another_hash(tmp_path: Path) -> None:
    """A copy with the framing allowance changed (256 -> 255) composes another snapshot, which the operator must
    approve before it is enforced; the model's own admission still applies within it."""
    tampered = _edited(tmp_path, "fixed_tokens: 256", "fixed_tokens: 255")
    assert tampered.effective_hash != _profile().effective_hash
    assert experimental_route(tampered, HAIKU) == experimental_route(_profile(), HAIKU)
    assert select_eligible_models(tampered, Role.EASY) == (HAIKU,)


def test_without_its_admission_block_haiku_gets_the_ordinary_refusals(tmp_path: Path) -> None:
    bare = _without(tmp_path, "empirical_estimate", "provider_family")

    assert experimental_route(bare, HAIKU) is None
    assert select_eligible_models(bare, Role.EASY) == ()
    assert {"ESTIMATOR_UNVERIFIED", "ROUTE_TARGET_NOT_EXACT"} <= _haiku_codes(bare)
    decision = guard_request(_request("hello"), bare, bare.effective_hash)
    assert (decision.allowed, decision.reason) == (False, "ESTIMATOR_UNVERIFIED")


@pytest.mark.parametrize(
    ("removed", "remaining_refusal"),
    [("provider_family", "ROUTE_TARGET_NOT_EXACT"), ("empirical_estimate", "ESTIMATOR_UNVERIFIED")],
)
def test_each_admission_part_relaxes_only_its_own_rule(tmp_path: Path, removed: str, remaining_refusal: str) -> None:
    snapshot = _without(tmp_path, removed)
    codes = _haiku_codes(snapshot)

    assert remaining_refusal in codes
    assert {"ESTIMATOR_UNVERIFIED", "ROUTE_TARGET_NOT_EXACT"} - {remaining_refusal} & codes == set()
    route = experimental_route(snapshot, HAIKU)
    assert route is not None and route.empirical_estimate is (removed != "empirical_estimate")
    assert (route.provider_name is None) is (removed == "provider_family")


def test_a_provider_family_admission_must_name_a_slug_the_route_uses(tmp_path: Path) -> None:
    snapshot = _edited(tmp_path, "        provider: anthropic\n", "        provider: anthropic-elsewhere\n")
    assert "ADMISSION_SCOPE_UNUSED" in _haiku_codes(snapshot)
    assert select_eligible_models(snapshot, Role.EASY) == ()


def test_an_admission_part_without_evidence_is_rejected(tmp_path: Path) -> None:
    text = _profile_text()
    start = text.index("        limitations:\n          - \"the base slug")
    end = text.index("    # The shipped defaults carry")
    copy = tmp_path / "empty.yaml"
    copy.write_text(text[:start] + "        limitations: []\n" + text[end:], encoding="utf-8")
    with pytest.raises(RegistryError) as caught:
        load_registry(packaged_defaults(), copy)
    assert caught.value.code == "SCHEMA_INVALID"


def test_the_admission_route_names_its_model_parts_and_provider() -> None:
    route = experimental_route(_profile(), HAIKU)

    assert route == ExperimentalRoute(model_id=HAIKU, empirical_estimate=True, provider_family="anthropic", provider_name="Anthropic")
    assert experimental_route(_profile(), LUNA) is None
    assert experimental_route(_profile(), "no/such-model") is None


def test_a_model_added_in_yaml_alone_becomes_eligible_and_leads_its_role_on_price(tmp_path: Path) -> None:
    """Models are configuration (Plan 12.4 v7 Acceptance): an override adds Luna's route facts, the conservative
    estimator and its admission evidence, and assigns it to easy. No code changes; Luna's lower prices order it
    first. Its new snapshot still needs the operator's approval before it is enforced."""
    override = tmp_path / "luna.yaml"
    override.write_text(
        """
models:
  openai/gpt-6-luna:
    route:
      estimator: conservative-utf8
      endpoints:
        - {provider: openai, quantization: unknown, context_window_tokens: 1050000, max_output_tokens: 128000, verified: true, observed_on: "2026-10-25"}
    admission:
      empirical_estimate:
        evidence: ["a test fixture: OpenAI publishes no Luna tokenizer"]
        assumptions: ["text-only input"]
        limitations: ["a first call can exceed its estimate before the per-reply check stops later calls"]
      provider_family:
        provider: openai
        provider_name: OpenAI
        evidence: ["a test fixture"]
        limitations: ["the base slug can reach any OpenAI variant"]
roles:
  easy: [anthropic/claude-haiku-5.5, openai/gpt-6-luna]
""",
        encoding="utf-8",
    )
    snapshot = load_registry(packaged_defaults(), override)

    assert select_eligible_models(snapshot, Role.EASY) == (LUNA, HAIKU)
    assert snapshot.effective_hash != trusted_snapshot().effective_hash  # type: ignore[union-attr]
    decision = guard_request(_request("é" * 1_000, model=LUNA), snapshot, snapshot.effective_hash)
    assert decision.allowed and decision.input_tokens == 2_000 + 16 + 256


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


def test_the_conservative_default_estimator_ships_with_haikus_values() -> None:
    shipped = trusted_snapshot()
    assert shipped is not None
    default, haiku = shipped.policy.estimators["conservative-utf8"], shipped.policy.estimators["haiku-5-5-empirical"]
    assert default == haiku and default.verified is False


def test_the_review_pins_are_the_reviewed_profile_hashes() -> None:
    assert {HAIKU_QUALIFICATION_HASH, HAIKU_ATTACHED_HASH} == {profile.effective_hash for profile in profiles.TEST_PROFILES.values()}


def test_the_shipped_defaults_are_the_attached_pin_with_haikus_own_admission() -> None:
    """Closure plan v3: the shipped defaults compose to the attached profile's snapshot. Haiku's admission is its
    own entry's block, and verified stays false."""
    shipped = trusted_snapshot()
    assert shipped is not None and shipped.effective_hash == SHIPPED_DEFAULTS_HASH == HAIKU_ATTACHED_HASH
    assert experimental_route(shipped, HAIKU) == experimental_route(_profile(), HAIKU)
    assert shipped.policy.estimators[shipped.policy.models[HAIKU].route.estimator].verified is False
    assert [model for model in shipped.policy.models if experimental_route(shipped, model) is not None] == [HAIKU]


def test_the_attached_profile_has_the_same_admission_under_its_own_hash() -> None:
    attached = profiles.compose_test_profile_snapshot("attached")

    assert attached.effective_hash != _profile().effective_hash
    assert attached.policy.models[HAIKU].admission == _profile().policy.models[HAIKU].admission
