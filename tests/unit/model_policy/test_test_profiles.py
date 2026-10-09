"""Plan 12.2 closure (release supplement V2): source-owned test profiles.

A fixed name selects packaged, reviewed data with a pinned effective hash. Unknown names, an
unavailable profile, a changed override and a fixture policy refuse. Production stays inactive.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import pytest

from optimus_model_policy import Role, select_eligible_models, validate_registry
from optimus_model_policy import binding as binding_module
from optimus_model_policy import test_profiles as profiles
from optimus_model_policy.binding import BindingError, packaged_defaults, trusted_snapshot
from optimus_model_policy.registry import load_registry

QUALIFICATION_HASH = "048c1a2b3e7d3436d371e8964200064bb30f0a1a865c945f92a2fc09d3ba5cba"  # pragma: allowlist secret - registry identity, not a credential


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


def test_the_qualification_profile_keeps_luna_ineligible_and_the_summarizer_unqualified() -> None:
    """Haiku replaces Luna in the profile's roles (defaults unchanged). The summarizer role still needs a
    genuine passing receipt: none is fabricated in advance."""
    snapshot = profiles.compose_test_profile_snapshot("qualification")
    assert "openai/gpt-6-luna" not in snapshot.policy.roles[Role.EASY] + snapshot.policy.roles[Role.SUMMARIZER]
    assert select_eligible_models(snapshot, Role.SUMMARIZER) == ()
    codes = {issue.code for issue in validate_registry(snapshot) if issue.model_id == "anthropic/claude-haiku-5.5" and issue.role is Role.SUMMARIZER}
    assert codes == {"SUMMARIZER_UNQUALIFIED"}
    assert snapshot.policy.output_reserve_tokens == {"implementer": 32_768, "summarizer": 8_192}


def test_the_override_is_package_data() -> None:
    override = resources.files("optimus_model_policy").joinpath("test_profile_qualification.yaml")
    assert override.is_file() and "anthropic/claude-haiku-5.5" in override.read_text(encoding="utf-8")


def _swap_override(monkeypatch: pytest.MonkeyPatch, path: Path, *, pinned: str) -> None:
    profile = profiles.TEST_PROFILES["qualification"]
    monkeypatch.setitem(profiles.TEST_PROFILES, "qualification", profiles.TestProfile(**{**profile.__dict__, "effective_hash": pinned}))
    monkeypatch.setattr(profiles, "_override_path", lambda _profile: path)


def test_a_changed_override_no_longer_matches_its_pin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    original = resources.files("optimus_model_policy").joinpath("test_profile_qualification.yaml").read_text(encoding="utf-8")
    changed = tmp_path / "changed.yaml"
    changed.write_text(original.replace('input_usd_per_million: "0.50"', 'input_usd_per_million: "0.01"'), encoding="utf-8")
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
