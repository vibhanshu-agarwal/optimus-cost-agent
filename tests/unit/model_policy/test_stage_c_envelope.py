"""Plan 12.2 Task 13 (Stage C): the source-owned test envelope (scope agreement, 2026-10-11).

One reviewed release shares one envelope across both test-profile launches. Release r9 (the operator's approval
of proposal 235d7b7e on 2026-10-17, after r8 stopped at B7.6 on a charged reply refusal): $8 of known charges plus
outstanding reservations, 138 physical upstream attempts and one 60-minute window. It supersedes r8, r7, r6, r5, r4,
r3 and r2 ($8, 138 attempts each) and the reviewed r1 ($0.50, 24 attempts), whose ledgers it never opens or resets. Its literal binds the
release, the limits, both profiles' pinned hashes, the fixed scenario catalogue and the resolved ledger,
so changing any of them changes what a launch approves.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from optimus_model_policy import stage_c
from optimus_model_policy import test_profiles as profiles
from optimus_model_policy.binding import BindingError

QUALIFICATION_HASH = "048c1a2b3e7d3436d371e8964200064bb30f0a1a865c945f92a2fc09d3ba5cba"  # pragma: allowlist secret - registry identity, not a credential
ATTACHED_HASH = "06e637845f5f7cea2b4a22d23407c59efc9741d7848b06ee5f4c3d2284f3f07d"  # pragma: allowlist secret - registry identity, not a credential


def test_the_release_is_the_agreed_test_envelope() -> None:
    assert (stage_c.STAGE_C_RELEASE_ID, stage_c.STAGE_C_LIMIT_USD, stage_c.STAGE_C_MAX_ATTEMPTS, stage_c.STAGE_C_WINDOW_SECONDS) == (
        "plan12-2-stage-c-r9", Decimal("8"), 138, 3600
    )
    assert stage_c.STAGE_C_PROFILES == ("qualification", "attached")


def test_the_envelope_binds_the_release_limits_profiles_scenarios_and_ledger(tmp_path: Path) -> None:
    ledger = stage_c.stage_c_ledger_path(tmp_path)
    envelope = stage_c.compose_stage_c_envelope(ledger=ledger)

    assert ledger == tmp_path / "plan12-stage-c" / f"{stage_c.STAGE_C_RELEASE_ID}.jsonl"
    assert envelope.canonical() == {
        "release_id": stage_c.STAGE_C_RELEASE_ID,
        "limit_usd": "8",
        "max_attempts": 138,
        "window_seconds": 3600,
        "profiles": {"qualification": QUALIFICATION_HASH, "attached": ATTACHED_HASH},
        "scenarios": stage_c.scenario_catalogue_digest(),
        "ledger": str(ledger),
    }
    assert envelope.literal.startswith("optimus-stage-c-envelope-v1:") and len(envelope.literal.split(":")[-1]) == 64
    assert stage_c.compose_stage_c_envelope(ledger=ledger).literal == envelope.literal


@pytest.mark.parametrize(
    "change",
    [
        {"release_id": "plan12-2-stage-c-r7"},
        {"limit_usd": Decimal("8.000001")},
        {"max_attempts": 139},
        {"window_seconds": 3601},
        {"profiles": (("qualification", QUALIFICATION_HASH), ("attached", "0" * 64))},
        {"scenarios": "0" * 64},
        {"ledger": "C:/elsewhere/ledger.jsonl"},
    ],
    ids=["release", "dollars", "attempts", "window", "profile", "scenarios", "ledger"],
)
def test_every_bound_value_changes_the_literal(tmp_path: Path, change: dict) -> None:
    envelope = stage_c.compose_stage_c_envelope(ledger=stage_c.stage_c_ledger_path(tmp_path))
    changed = stage_c.StageCEnvelope(**{**envelope.__dict__, **change})
    assert changed.literal != envelope.literal


def test_the_scenario_catalogue_digest_covers_its_content() -> None:
    assert stage_c.scenario_catalogue_digest({"a": {"turns": 1}}) != stage_c.scenario_catalogue_digest({"a": {"turns": 2}})
    assert stage_c.scenario_catalogue_digest({"a": {"turns": 1}}) != stage_c.scenario_catalogue_digest({"b": {"turns": 1}})


def test_a_relative_ledger_is_refused() -> None:
    with pytest.raises(BindingError) as caught:
        stage_c.compose_stage_c_envelope(ledger=Path("relative/ledger.jsonl"))
    assert caught.value.code == "STAGE_C_LEDGER_NOT_ABSOLUTE"


def test_the_migration_keeps_the_historical_envelope_identity(tmp_path: Path) -> None:
    """Plan 12.4 v7 moved admission into the registry entries, which changed both profiles' composed hashes. Release r9
    keeps its own pins, so its envelope is the one recorded before the migration, byte for byte. The recorded envelope's
    ledger is the serialized Windows path, fixed here as a string so the identity holds on every platform (Codex round
    68)."""
    native = stage_c.stage_c_ledger_path(tmp_path)
    composed = stage_c.compose_stage_c_envelope(ledger=native)
    assert composed.ledger == str(native)
    envelope = stage_c.StageCEnvelope(**{**composed.__dict__, "ledger": r"C:\stage-c\ledger.jsonl"})

    assert dict(envelope.profiles) == {"qualification": QUALIFICATION_HASH, "attached": ATTACHED_HASH}
    assert envelope.literal == "optimus-stage-c-envelope-v1:3675df47fbf159ea488a745d9302aafae5ca9ea90dc77a8481aa0930f399be75"  # pragma: allowlist secret - envelope identity, not a credential


def test_the_release_refuses_the_migrated_profiles_and_gains_no_authority(tmp_path: Path) -> None:
    envelope = stage_c.compose_stage_c_envelope(ledger=stage_c.stage_c_ledger_path(tmp_path))

    for name in stage_c.STAGE_C_PROFILES:
        current = profiles.compose_test_profile_snapshot(name).effective_hash
        assert current != dict(envelope.profiles)[name]
        with pytest.raises(BindingError) as caught:
            stage_c.require_stage_c_profile(envelope, name, current)
        assert caught.value.code == "STAGE_C_PROFILE_MIGRATED"
        stage_c.require_stage_c_profile(envelope, name, dict(envelope.profiles)[name])  # its own pin still matches
    with pytest.raises(BindingError):
        stage_c.require_stage_c_profile(envelope, "", "")


def test_a_reservation_is_the_input_estimate_and_output_cap_at_registry_prices() -> None:
    reserve = stage_c.reservation_usd(input_tokens=78_883, output_tokens=32_768, input_usd_per_million=Decimal("0.50"), output_usd_per_million=Decimal("2.50"))
    assert reserve == Decimal("0.1213615")


EARLIER_RELEASES = {
    "r1": ("plan12-2-stage-c-r1", Decimal("0.50"), 24),
    "r2": ("plan12-2-stage-c-r2", Decimal("8"), 138),
    "r3": ("plan12-2-stage-c-r3", Decimal("8"), 138),
    "r4": ("plan12-2-stage-c-r4", Decimal("8"), 138),
    "r5": ("plan12-2-stage-c-r5", Decimal("8"), 138),
    "r6": ("plan12-2-stage-c-r6", Decimal("8"), 138),
    "r7": ("plan12-2-stage-c-r7", Decimal("8"), 138),
    "r8": ("plan12-2-stage-c-r8", Decimal("8"), 138),
}


@pytest.mark.parametrize("earlier", sorted(EARLIER_RELEASES))
def test_the_r9_release_never_opens_or_resets_an_earlier_ledger(tmp_path: Path, earlier: str) -> None:
    """r9 has its own ledger file and literal. An earlier release's ledger (r2 to r8 stopped with their windows open;
    r2, r3, r5, r6, r7 and r8 with settled charges) stays history: never reopened, reset or overwritten by r9, whose
    window and totals start afresh."""
    release_id, limit_usd, max_attempts = EARLIER_RELEASES[earlier]
    r8_path = stage_c.stage_c_ledger_path(tmp_path)
    r8 = stage_c.compose_stage_c_envelope(ledger=r8_path)
    old_path = tmp_path / "plan12-stage-c" / f"{release_id}.jsonl"
    old = stage_c.StageCEnvelope(**{**r8.__dict__, "release_id": release_id, "limit_usd": limit_usd, "max_attempts": max_attempts, "ledger": str(old_path)})
    stage_c.initialize_stage_c_ledger(old_path, old)
    used = stage_c.StageCGuard.open(old_path, old)
    used.settle_charged(used.admit(attempt_id="gw-" + "1" * 32, request_id="earlier-1", reserve_usd=Decimal("0.0837")), Decimal("0.0002471"))
    used.close()
    before = old_path.read_bytes()

    assert r8_path == tmp_path / "plan12-stage-c" / "plan12-2-stage-c-r9.jsonl" and r8.literal != old.literal
    stage_c.initialize_stage_c_ledger(r8_path, r8)
    guard = stage_c.StageCGuard.open(r8_path, r8)
    assert (guard.state.attempts, guard.state.charged_usd) == (0, Decimal(0))
    guard.close()
    with pytest.raises(stage_c.StageCLedgerError) as caught:
        stage_c.StageCGuard.open(old_path, r8)
    assert caught.value.code == "STAGE_C_LEDGER_NOT_BOUND"
    assert old_path.read_bytes() == before
