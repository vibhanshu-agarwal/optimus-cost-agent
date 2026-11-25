"""Plan 12.14 (D3): ModelEntry.context_budget.input_target_usd. Omitted when absent, so a composition without it keeps its hash; staged on the shipped Haiku 5.5 entry by Task 2."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from optimus_model_policy.binding import packaged_defaults, trusted_snapshot
from optimus_model_policy.experimental import SHIPPED_DEFAULTS_HASH
from optimus_model_policy.registry import RegistryError, load_registry

HAIKU = "anthropic/claude-haiku-5.5"


def _override(tmp_path: Path, value: str) -> Path:
    path = tmp_path / "override.yaml"
    path.write_text(f"models:\n  {HAIKU}:\n    context_budget: {{input_target_usd: {value}}}\n", encoding="utf-8")
    return path


PRE_FIELD_HASH = "4d2f637e822841c23ae617d352c81a6472d11771fd7cd7011b3052c12b506338"  # pragma: allowlist secret - registry identity, not a credential
FIELD_LINE = '    context_budget: {input_target_usd: "0.008192"}\n'


def defaults_without_field(tmp_path: Path) -> Path:
    """The packaged defaults with only the D3 field line removed: the composition before Plan 12.14 Task 2."""
    text = packaged_defaults().read_text(encoding="utf-8")
    assert text.count(FIELD_LINE) == 1
    path = tmp_path / "defaults-without-field.yaml"
    path.write_text(text.replace(FIELD_LINE, ""), encoding="utf-8")
    return path


def test_the_shipped_entry_carries_the_approved_d3_target_and_removing_it_restores_the_pre_change_hash(tmp_path):
    """Plan 12.14 Task 2 (operator hash approval 2026-11-25): the field is staged in the defaults themselves. Removing it gives back
    the pre-change composition exactly, so a gate failure can revert to a proven hash, and an entry without it keeps its canonical form."""
    snapshot = trusted_snapshot()
    entry = snapshot.policy.models[HAIKU]
    assert entry.context_budget is not None and entry.context_budget.input_target_usd == Decimal("0.008192")
    assert snapshot.effective_hash == SHIPPED_DEFAULTS_HASH == "b7fca195e22c4884109540c8c0d8acf2f23ec70534994d4136445a7408906e3a"  # pragma: allowlist secret - registry identity
    before = load_registry(defaults_without_field(tmp_path))
    assert before.policy.models[HAIKU].context_budget is None and "context_budget" not in before.policy.models[HAIKU].model_dump(mode="json")
    assert before.effective_hash == PRE_FIELD_HASH


def test_the_field_is_a_positive_decimal_and_changes_the_hash(tmp_path):
    snapshot = trusted_snapshot()
    assert snapshot.policy.models[HAIKU].model_dump(mode="json")["context_budget"] == {"input_target_usd": "0.008192"}
    other = load_registry(packaged_defaults(), _override(tmp_path, '"0.004096"'))
    assert other.policy.models[HAIKU].context_budget.input_target_usd == Decimal("0.004096") and other.effective_hash != SHIPPED_DEFAULTS_HASH
    same = load_registry(packaged_defaults(), _override(tmp_path, '"0.0081920"'))
    assert same.effective_hash == SHIPPED_DEFAULTS_HASH  # one canonical text per value


@pytest.mark.parametrize("value", ['"0"', '"-0.01"', "0.008192", '"NaN"', '"Infinity"'])
def test_zero_negative_float_and_non_finite_targets_are_refused(tmp_path, value):
    with pytest.raises(RegistryError) as caught:
        load_registry(packaged_defaults(), _override(tmp_path, value))
    assert caught.value.code == "SCHEMA_INVALID"
