from decimal import Decimal

from optimus_gateway.pricing import billing_units, compute_cost_usd


def test_billing_units_is_input_plus_output_tokens():
    assert billing_units(input_tokens=12, output_tokens=8) == 20


def test_compute_cost_usd_uses_published_haiku_rates():
    cost = compute_cost_usd(input_tokens=1_000_000, output_tokens=0)
    assert cost == Decimal("1.00")

    cost = compute_cost_usd(input_tokens=0, output_tokens=1_000_000)
    assert cost == Decimal("5.00")

    cost = compute_cost_usd(input_tokens=1000, output_tokens=500)
    expected = (Decimal("1000") * Decimal("1.00") / Decimal(1_000_000)) + (
        Decimal("500") * Decimal("5.00") / Decimal(1_000_000)
    )
    assert cost == expected
