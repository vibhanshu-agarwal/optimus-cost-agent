"""Plan 12.2 closure (release supplement V2): source-owned test profiles.

A fixed name selects packaged, reviewed data with a pinned effective hash. Unknown names, an
unavailable profile, a changed override and a fixture policy refuse. Production stays inactive.
"""

from __future__ import annotations

from decimal import Decimal
from importlib import resources
from pathlib import Path

import pytest

from optimus_model_policy import Role, select_eligible_models, validate_registry
from optimus_model_policy import binding as binding_module
from optimus_model_policy import test_profiles as profiles
from optimus_model_policy.binding import BindingError, packaged_defaults, trusted_snapshot
from optimus_model_policy.registry import load_registry

QUALIFICATION_HASH = "0539d26660457618add2de9266c541975cb30f3927860e9c68da01152f3551a0"  # pragma: allowlist secret - registry identity, not a credential


def test_production_composition_is_untouched() -> None:
    assert binding_module.ENFORCEMENT_ACTIVE is False
    assert trusted_snapshot() is None
    assert profiles.registry_for_launch(None) is None


@pytest.mark.parametrize(("name", "code"), [("bogus", "TEST_PROFILE_UNKNOWN"), ("", "TEST_PROFILE_UNKNOWN"), ("attached", "TEST_PROFILE_UNAVAILABLE")])
def test_only_an_available_reviewed_name_composes(name: str, code: str) -> None:
    with pytest.raises(BindingError) as caught:
        profiles.compose_test_profile_snapshot(name)
    assert caught.value.code == code


def test_the_attached_profile_waits_for_a_genuine_receipt() -> None:
    attached = profiles.TEST_PROFILES["attached"]
    assert (attached.override, attached.effective_hash, attached.model_id) == (None, None, None)
    assert "receipt" in attached.unavailable_reason


def test_the_qualification_profile_composes_its_pinned_reviewed_snapshot() -> None:
    snapshot = profiles.compose_test_profile_snapshot("qualification")

    assert snapshot.effective_hash == QUALIFICATION_HASH == profiles.TEST_PROFILES["qualification"].effective_hash
    assert snapshot.policy.fixture is False
    assert profiles.registry_for_launch("qualification").effective_hash == QUALIFICATION_HASH


def test_the_qualification_profile_records_the_reviewed_route_and_admits_no_model_yet() -> None:
    """Codex's Luna disposition: exact openai/fast, the literal quantization filter "unknown", its own
    prices and an explicit "none" reasoning setting. The tokenizer, finish and reasoning facts are not
    established, so nothing is eligible and a launch with this profile refuses before any call."""
    snapshot = profiles.compose_test_profile_snapshot("qualification")
    luna = snapshot.policy.models["openai/gpt-6-luna"]
    [endpoint] = luna.route.endpoints

    assert (endpoint.provider, endpoint.quantization, endpoint.context_window_tokens, endpoint.max_output_tokens, endpoint.verified) == (
        "openai/fast", "unknown", 1_050_000, 128_000, False
    )  # fmt: skip
    assert (luna.prices.input_usd_per_million, luna.prices.output_usd_per_million) == (Decimal("0.20"), Decimal("1.00"))
    assert luna.default_reasoning == "none" and luna.route.allow_fallbacks is False
    assert snapshot.policy.output_reserve_tokens == {"implementer": 32_768, "summarizer": 8_192}

    assert select_eligible_models(snapshot, Role.EASY) == () and select_eligible_models(snapshot, Role.SUMMARIZER) == ()
    codes = {issue.code for issue in validate_registry(snapshot) if issue.model_id == "openai/gpt-6-luna"}
    assert codes == {"ESTIMATOR_UNKNOWN", "ROUTE_UNVERIFIED", "SUMMARIZER_UNQUALIFIED"}
    # The recorded literal "unknown" and the exact variant slug pass the existing rules unchanged.
    assert not codes & {"ROUTE_QUANTIZATION_UNKNOWN", "ROUTE_QUANTIZATION_NOT_EXPRESSIBLE", "ROUTE_TARGET_NOT_EXACT"}


def test_the_override_is_package_data() -> None:
    override = resources.files("optimus_model_policy").joinpath("test_profile_qualification.yaml")
    assert override.is_file() and "openai/fast" in override.read_text(encoding="utf-8")


def _swap_override(monkeypatch: pytest.MonkeyPatch, path: Path, *, pinned: str) -> None:
    profile = profiles.TEST_PROFILES["qualification"]
    monkeypatch.setitem(profiles.TEST_PROFILES, "qualification", profiles.TestProfile(**{**profile.__dict__, "effective_hash": pinned}))
    monkeypatch.setattr(profiles, "_override_path", lambda _profile: path)


def test_a_changed_override_no_longer_matches_its_pin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    original = resources.files("optimus_model_policy").joinpath("test_profile_qualification.yaml").read_text(encoding="utf-8")
    changed = tmp_path / "changed.yaml"
    changed.write_text(original.replace('input_usd_per_million: "0.20"', 'input_usd_per_million: "0.01"'), encoding="utf-8")
    _swap_override(monkeypatch, changed, pinned=QUALIFICATION_HASH)

    with pytest.raises(BindingError) as caught:
        profiles.compose_test_profile_snapshot("qualification")
    assert caught.value.code == "TEST_PROFILE_HASH_MISMATCH"


def test_a_fixture_override_never_composes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.yaml"
    fixture.write_text("fixture: true\n", encoding="utf-8")
    _swap_override(monkeypatch, fixture, pinned=load_registry(packaged_defaults(), fixture).effective_hash)

    with pytest.raises(BindingError) as caught:
        profiles.compose_test_profile_snapshot("qualification")
    assert caught.value.code == "FIXTURE_POLICY"


def test_a_malformed_override_is_refused_by_code(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("models: {a: &x 1, b: *x}\n", encoding="utf-8")
    _swap_override(monkeypatch, bad, pinned=QUALIFICATION_HASH)

    with pytest.raises(BindingError) as caught:
        profiles.compose_test_profile_snapshot("qualification")
    assert caught.value.code == "TEST_PROFILE_INVALID"
