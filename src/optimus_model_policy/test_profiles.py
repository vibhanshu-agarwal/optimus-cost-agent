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
``attached`` profile needs a genuine passing summary-quality receipt and its own reviewed hash and
approval, so it is declared unavailable until then: no hash or receipt is fabricated in advance.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from optimus_model_policy.binding import BindingError, packaged_defaults, trusted_snapshot
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
    # Profile A: qualification and absent-engine behaviour. It records the 2026-10-04 free inspection's
    # observed public facts for the baseline candidate, unverified: its tokenizer is not established by
    # publisher configuration, every endpoint's quantization is unknown and the registry-priced endpoint
    # is a base slug. It therefore admits no model, and a launch with it refuses before any call.
    "qualification": TestProfile(
        name="qualification",
        override="test_profile_qualification.yaml",
        effective_hash="0539d26660457618add2de9266c541975cb30f3927860e9c68da01152f3551a0",  # pragma: allowlist secret - registry identity, not a credential
        model_id="openai/gpt-6-luna",
        role="easy",
        output_cap=32768,
    ),
    # Profile B: attached maintenance. Needs profile A's genuine passing receipt first.
    "attached": TestProfile(
        name="attached",
        override=None,
        effective_hash=None,
        model_id=None,
        role=None,
        output_cap=None,
        unavailable_reason="needs a genuine passing summary-quality receipt and its own reviewed hash and approval",
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
