"""Source-owned Plan 12.2 test profiles (closure release supplement V2, 2026-10-04).

A test profile is reviewed repository code and data, never caller input. A fixed name selects a
packaged registry override and its pinned effective hash; an unknown name, an unavailable profile, a
changed override or a fixture policy refuses. Selecting a profile grants nothing by itself:

- the launch gate binds the profile's effective hash into the HMAC-protected launch approval, so the
  operator approves that exact snapshot, and signs it into the Gateway child manifest;
- the Gateway composes the same named profile itself and refuses to start unless the signed manifest
  names the same hash;
- workspace, credential, permission and scope checks are unchanged.

Production is untouched: ``ENFORCEMENT_ACTIVE`` stays False, :func:`trusted_snapshot` keeps returning
None and the shipped defaults do not change. Activation remains a separate reviewed code release; this
module is the reviewed test-process composition the binding rule's "reviewed code change" names.

Verified facts enter a profile only through a reviewed change to its override and pinned hash. The
``attached`` profile (profile B) is the qualification policy plus the one genuine summary-quality
receipt Codex accepted (Stage 2, 2026-10-11), filed under the operator's approval of the offline
preparation batch: its own reviewed hash, which a launch approval binds like any other. It qualifies the
summarizer role for that test snapshot only. Composing it constructs no attached Context Engine: the
host builds none for any profile, so engine attachment remains a separate reviewed change.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from optimus_model_policy.binding import BindingError, packaged_defaults, trusted_snapshot
from optimus_model_policy.experimental import HAIKU_ATTACHED_HASH, HAIKU_QUALIFICATION_HASH
from optimus_model_policy.registry import RegistryError, RegistrySnapshot, load_registry

__all__ = ["TEST_PROFILE_NAMES", "TEST_PROFILES", "TestProfile", "compose_test_profile_snapshot", "registry_for_launch"]


@dataclass(frozen=True)
class TestProfile:
    """One reviewed test profile: its packaged override, pinned effective hash and the exact model,
    role and output cap the test process binds (or the reason it is not yet available)."""

    __test__ = False  # not a pytest test class

    name: str
    override: str | None
    effective_hash: str | None
    model_id: str | None
    role: str | None
    output_cap: int | None
    unavailable_reason: str | None = None


TEST_PROFILES: Final[dict[str, TestProfile]] = {
    # Profile A: qualification and absent-engine behaviour, on Claude Haiku 5.5 (operator release,
    # 2026-10-09). Its route facts come from the 2026-10-09 free inspection; its empirical estimator and
    # provider-family slug are admitted only through experimental.py, bound to this exact hash. Luna
    # stays ineligible: its 2026-10-04 facts never established a tokenizer.
    "qualification": TestProfile(
        name="qualification",
        override="test_profile_qualification.yaml",
        effective_hash=HAIKU_QUALIFICATION_HASH,
        model_id="anthropic/claude-haiku-5.5",
        role="easy",
        output_cap=32768,
    ),
    # Profile B: attached maintenance. Profile A's policy plus its accepted receipt (operator approval of the
    # offline preparation batch, 2026-10-11): the same model, test-agent role and output cap, its own hash.
    "attached": TestProfile(
        name="attached",
        override="test_profile_attached.yaml",
        effective_hash=HAIKU_ATTACHED_HASH,
        model_id="anthropic/claude-haiku-5.5",
        role="easy",
        output_cap=32768,
    ),
}
TEST_PROFILE_NAMES: Final = tuple(TEST_PROFILES)


def _override_path(profile: TestProfile) -> Path:
    assert profile.override is not None
    return Path(__file__).with_name(profile.override)


def compose_test_profile_snapshot(name: str) -> RegistrySnapshot:
    """The named profile's snapshot: packaged defaults plus its packaged override, exactly as reviewed."""
    profile = TEST_PROFILES.get(name)
    if profile is None:
        raise BindingError("TEST_PROFILE_UNKNOWN", "only the reviewed test profile names are accepted")
    if profile.override is None or profile.effective_hash is None:
        raise BindingError("TEST_PROFILE_UNAVAILABLE", profile.unavailable_reason or "not available")
    try:
        snapshot = load_registry(packaged_defaults(), _override_path(profile))
    except RegistryError as exc:
        raise BindingError("TEST_PROFILE_INVALID", type(exc).__name__) from exc
    if snapshot.policy.fixture:
        raise BindingError("FIXTURE_POLICY", "a fixture registry cannot be trusted at launch")
    if snapshot.effective_hash != profile.effective_hash:
        raise BindingError("TEST_PROFILE_HASH_MISMATCH", "the profile's composed hash is not its reviewed pin")
    return snapshot


def registry_for_launch(test_profile: str | None) -> RegistrySnapshot | None:
    """The snapshot a launch binds: the named test profile's, or the installed trusted snapshot
    (None while enforcement is inactive) when no profile is selected."""
    return compose_test_profile_snapshot(test_profile) if test_profile is not None else trusted_snapshot()
