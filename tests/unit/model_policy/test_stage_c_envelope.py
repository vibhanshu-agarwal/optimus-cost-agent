"""Plan 12.2 Task 13 (Stage C): the source-owned test envelope (scope agreement, 2026-10-11).

One reviewed release shares one envelope across both test-profile launches. Release r2 (the operator's release
of 2026-10-12): $8 of known charges plus outstanding reservations, 138 physical upstream attempts and one
60-minute window. It supersedes the reviewed r1 ($0.50, 24 attempts), whose ledger it never opens or resets. Its literal binds the
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
        "plan12-2-stage-c-r2", Decimal("8"), 138, 3600
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
        {"release_id": "plan12-2-stage-c-r1"},
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


def test_a_relative_ledger_or_an_unavailable_profile_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(BindingError) as caught:
        stage_c.compose_stage_c_envelope(ledger=Path("relative/ledger.jsonl"))
    assert caught.value.code == "STAGE_C_LEDGER_NOT_ABSOLUTE"

    stand_in = profiles.TestProfile(name="attached", override=None, effective_hash=None, model_id=None, role=None, output_cap=None, unavailable_reason="a stand-in")
    monkeypatch.setitem(profiles.TEST_PROFILES, "attached", stand_in)
    with pytest.raises(BindingError) as caught:
        stage_c.compose_stage_c_envelope(ledger=stage_c.stage_c_ledger_path(tmp_path))
    assert caught.value.code == "STAGE_C_PROFILE_UNAVAILABLE"


def test_a_reservation_is_the_input_estimate_and_output_cap_at_registry_prices() -> None:
    reserve = stage_c.reservation_usd(input_tokens=78_883, output_tokens=32_768, input_usd_per_million=Decimal("0.50"), output_usd_per_million=Decimal("2.50"))
    assert reserve == Decimal("0.1213615")


def test_the_r2_release_never_opens_or_resets_an_r1_ledger(tmp_path: Path) -> None:
    """r2 has its own ledger file and literal; an r1 ledger, if one was ever created, stays history: never
    reopened, reset or overwritten by r2."""
    r2_path = stage_c.stage_c_ledger_path(tmp_path)
    r2 = stage_c.compose_stage_c_envelope(ledger=r2_path)
    r1_path = tmp_path / "plan12-stage-c" / "plan12-2-stage-c-r1.jsonl"
    r1 = stage_c.StageCEnvelope(**{**r2.__dict__, "release_id": "plan12-2-stage-c-r1", "limit_usd": Decimal("0.50"), "max_attempts": 24, "ledger": str(r1_path)})
    stage_c.initialize_stage_c_ledger(r1_path, r1)
    before = r1_path.read_bytes()

    assert r2_path == tmp_path / "plan12-stage-c" / "plan12-2-stage-c-r2.jsonl" and r2.literal != r1.literal
    stage_c.initialize_stage_c_ledger(r2_path, r2)
    stage_c.StageCGuard.open(r2_path, r2).close()
    with pytest.raises(stage_c.StageCLedgerError) as caught:
        stage_c.StageCGuard.open(r1_path, r2)
    assert caught.value.code == "STAGE_C_LEDGER_NOT_BOUND"
    assert r1_path.read_bytes() == before
