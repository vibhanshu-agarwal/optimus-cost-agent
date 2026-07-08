from decimal import Decimal

import pytest

from optimus_gateway.pricing import billing_units, compute_cost_usd, lookup_model_rate


def test_billing_units_is_input_plus_output_tokens():
    assert billing_units(input_tokens=12, output_tokens=8) == 20


def test_compute_cost_usd_uses_anthropic_haiku_rates():
    cost, snapshot = compute_cost_usd(
        provider="anthropic",
        resolved_model="claude-haiku-4-5-20251001",
        input_tokens=1_000_000,
        output_tokens=0,
    )
    assert cost == Decimal("1.00")
    assert snapshot.startswith("anthropic-")


def test_compute_cost_usd_uses_openrouter_haiku_rates():
    cost, _snapshot = compute_cost_usd(
        provider="openrouter",
        resolved_model="anthropic/claude-haiku-4.5",
        input_tokens=1_000_000,
        output_tokens=0,
    )
    assert cost == Decimal("1.00")


def test_lookup_model_rate_fails_loudly_for_unknown_model():
    with pytest.raises(ValueError, match="no pricing snapshot"):
        lookup_model_rate(provider="openrouter", resolved_model="unknown/model")
