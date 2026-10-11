"""Plan 12.2 closure (release supplement V2): source-owned test profiles.

A fixed name selects packaged, reviewed data with a pinned effective hash. Unknown names, an
unavailable profile, a changed override and a fixture policy refuse. Production stays inactive.

Profile B (``attached``) is the qualification policy plus the one accepted summary-quality receipt
(operator approval of the offline preparation batch, 2026-10-11): its own pinned hash, the qualification
profile unchanged, and the filed receipt byte for byte the accepted candidate's.
"""

from __future__ import annotations

import hashlib
import json
from importlib import resources
from pathlib import Path

import pytest

from optimus_model_policy import Role, select_eligible_models, validate_registry
from optimus_model_policy import binding as binding_module
from optimus_model_policy import test_profiles as profiles
from optimus_model_policy.binding import BindingError, packaged_defaults, trusted_snapshot
from optimus_model_policy.registry import SUMMARY_FIXTURE_DIGEST, SUMMARY_FORMAT, SUMMARY_PROMPT_DIGEST, SUMMARY_VALIDATOR, load_registry

QUALIFICATION_HASH = "048c1a2b3e7d3436d371e8964200064bb30f0a1a865c945f92a2fc09d3ba5cba"  # pragma: allowlist secret - registry identity, not a credential
ATTACHED_HASH = "06e637845f5f7cea2b4a22d23407c59efc9741d7848b06ee5f4c3d2284f3f07d"  # pragma: allowlist secret - registry identity, not a credential
HAIKU = "anthropic/claude-haiku-5.5"
# The accepted Stage 2 artifacts (Codex acceptance, 2026-10-11): the receipt candidate's exact bytes and the
# assessment it names. The candidate is rebuilt below from the filed receipt, so the filed copy is proven equal.
CANDIDATE_SHA256 = "3bac81899ae317c547daf94e98c19511ed434131d93578fe650ba10fde58045a"  # pragma: allowlist secret - public evidence digest
ASSESSMENT_SHA256 = "29631c0c9c69394649b713a14f7f9e42265a177580b20d6f46222c6c7371ccaf"  # pragma: allowlist secret - public evidence digest
CANDIDATE_NOTE = "a candidate for review: it qualifies nothing and enables no attached engine by itself"


def test_production_composition_is_untouched() -> None:
    assert binding_module.ENFORCEMENT_ACTIVE is False
    assert trusted_snapshot() is None
    assert profiles.registry_for_launch(None) is None


def test_no_shipped_default_carries_a_receipt() -> None:
    """The receipt is test data only: no packaged default carries a summary receipt."""
    defaults = load_registry(packaged_defaults(), None)
    assert all(entry.summary_receipts == () for entry in defaults.policy.models.values())


@pytest.mark.parametrize(("name", "code"), [("bogus", "TEST_PROFILE_UNKNOWN"), ("", "TEST_PROFILE_UNKNOWN")])
def test_only_a_reviewed_name_composes(name: str, code: str) -> None:
    with pytest.raises(BindingError) as caught:
        profiles.compose_test_profile_snapshot(name)
    assert caught.value.code == code


def test_an_unavailable_profile_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both reviewed profiles are available now; the refusal stays covered with a stand-in."""
    stand_in = profiles.TestProfile(name="attached", override=None, effective_hash=None, model_id=None, role=None, output_cap=None, unavailable_reason="a stand-in")
    monkeypatch.setitem(profiles.TEST_PROFILES, "attached", stand_in)
    with pytest.raises(BindingError) as caught:
        profiles.compose_test_profile_snapshot("attached")
    assert (caught.value.code, str(caught.value)) == ("TEST_PROFILE_UNAVAILABLE", "TEST_PROFILE_UNAVAILABLE: a stand-in")


def test_the_attached_profile_composes_its_own_pinned_reviewed_snapshot() -> None:
    snapshot = profiles.compose_test_profile_snapshot("attached")
    attached, qualification = profiles.TEST_PROFILES["attached"], profiles.TEST_PROFILES["qualification"]

    assert snapshot.effective_hash == ATTACHED_HASH == attached.effective_hash != QUALIFICATION_HASH
    assert snapshot.policy.fixture is False
    assert profiles.registry_for_launch("attached").effective_hash == ATTACHED_HASH
    assert (attached.override, attached.unavailable_reason) == ("test_profile_attached.yaml", None)
    # The same model, test-agent role and output cap as the qualification profile.
    assert (attached.model_id, attached.role, attached.output_cap) == (qualification.model_id, qualification.role, qualification.output_cap) == (HAIKU, "easy", 32_768)


def test_the_attached_policy_is_the_qualification_policy_plus_one_receipt() -> None:
    attached = profiles.compose_test_profile_snapshot("attached").policy.model_dump(mode="json")
    qualification = profiles.compose_test_profile_snapshot("qualification").policy.model_dump(mode="json")

    assert qualification["models"][HAIKU]["summary_receipts"] == []
    assert len(attached["models"][HAIKU].pop("summary_receipts")) == 1
    qualification["models"][HAIKU].pop("summary_receipts")
    assert attached == qualification


def test_the_filed_receipt_is_the_accepted_candidate_byte_for_byte() -> None:
    [receipt] = profiles.compose_test_profile_snapshot("attached").policy.models[HAIKU].summary_receipts
    # The candidate as `assess` wrote it (_write_json: indent 2, one trailing newline), rebuilt from the filed receipt.
    candidate = json.dumps({"receipt": receipt.model_dump(mode="json"), "assessment_sha256": ASSESSMENT_SHA256, "note": CANDIDATE_NOTE}, indent=2) + "\n"

    assert hashlib.sha256(candidate.encode("utf-8")).hexdigest() == CANDIDATE_SHA256
    assert (receipt.format, receipt.fixture_digest, receipt.prompt_digest, receipt.validator) == (SUMMARY_FORMAT, SUMMARY_FIXTURE_DIGEST, SUMMARY_PROMPT_DIGEST, SUMMARY_VALIDATOR)
    # The genuine v6 run's two requests and run date (the original v6 FAIL record is separate and unchanged).
    assert (receipt.request_ids, receipt.recorded_on, receipt.result) == (("gw-142d038d8be1423bba3a4c286f813726", "gw-52fac698887f4b69b98f33ad60e0650b"), "2026-10-10", "pass")


def test_the_receipt_qualifies_the_summarizer_only_in_the_attached_profile() -> None:
    attached = profiles.compose_test_profile_snapshot("attached")

    assert select_eligible_models(attached, Role.SUMMARIZER) == (HAIKU,)
    assert select_eligible_models(attached, Role.EASY) == (HAIKU,)
    assert [issue for issue in validate_registry(attached) if issue.model_id == HAIKU] == []
    assert select_eligible_models(profiles.compose_test_profile_snapshot("qualification"), Role.SUMMARIZER) == ()


def test_the_attached_override_is_package_data() -> None:
    override = resources.files("optimus_model_policy").joinpath("test_profile_attached.yaml")
    assert override.is_file() and "summary_receipts" in override.read_text(encoding="utf-8")


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
