"""Plan 12.14 (D3): ModelEntry.context_budget.input_target_usd. Omitted when absent, so every existing composition keeps its hash."""

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


def test_an_entry_without_the_field_keeps_its_canonical_form_and_the_shipped_hash():
    snapshot = trusted_snapshot()
    entry = snapshot.policy.models[HAIKU]
    assert entry.context_budget is None and "context_budget" not in entry.model_dump(mode="json")
    assert snapshot.effective_hash == SHIPPED_DEFAULTS_HASH


def test_the_field_is_a_positive_decimal_and_changes_the_hash(tmp_path):
    snapshot = load_registry(packaged_defaults(), _override(tmp_path, '"0.008192"'))
    entry = snapshot.policy.models[HAIKU]
    assert entry.context_budget is not None and entry.context_budget.input_target_usd == Decimal("0.008192")
    assert entry.model_dump(mode="json")["context_budget"] == {"input_target_usd": "0.008192"}
    assert snapshot.effective_hash != SHIPPED_DEFAULTS_HASH
    same = load_registry(packaged_defaults(), _override(tmp_path, '"0.0081920"'))
    assert same.effective_hash == snapshot.effective_hash  # one canonical text per value


@pytest.mark.parametrize("value", ['"0"', '"-0.01"', "0.008192", '"NaN"', '"Infinity"'])
def test_zero_negative_float_and_non_finite_targets_are_refused(tmp_path, value):
    with pytest.raises(RegistryError) as caught:
        load_registry(packaged_defaults(), _override(tmp_path, value))
    assert caught.value.code == "SCHEMA_INVALID"
