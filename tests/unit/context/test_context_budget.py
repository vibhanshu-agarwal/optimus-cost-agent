"""Plan 12.14 Task 1: the preparation-time budget. C, T and the chosen budget, field omission and the shared cache-write multiplier."""

from __future__ import annotations

from decimal import Decimal

import pytest

from context_engine.context_pack import chosen_budget
from optimus.context.context_budget import HARD_MAX_TOKENS, LEGACY_MAX_TOKENS, BudgetPolicy, legacy_budget, plan_budget, target_tokens
from optimus_model_policy.registry import CACHE_WRITE_INPUT_MULTIPLIER

D3_USABLE = min(1_000_000, 262_144) - 32_768  # Haiku 5.5's window, the 262,144 ceiling and the implementer reserve


def test_the_multiplier_is_shared_and_the_gateway_reserves_with_it():
    from optimus_gateway import responses

    assert CACHE_WRITE_INPUT_MULTIPLIER == Decimal("1.25")
    assert responses.CACHE_WRITE_INPUT_MULTIPLIER is CACHE_WRITE_INPUT_MULTIPLIER
    assert not hasattr(responses, "_CACHE_WRITE_INPUT_MULTIPLIER")


def test_the_plans_forecast_for_d3s_entry():
    assert D3_USABLE == 229_376
    policy = plan_budget(D3_USABLE, input_target_usd=Decimal("0.008192"), input_usd_per_million=Decimal("0.50"), cache_write=True)
    assert (policy.name, policy.ceiling, policy.target) == ("model-aware", 32_768, 13_107)
    assert plan_budget(D3_USABLE, input_target_usd=Decimal("0.008192"), input_usd_per_million=Decimal("0.50"), cache_write=False).target == 16_384
    assert legacy_budget(D3_USABLE) == 16_384


def test_an_entry_without_the_field_keeps_the_legacy_budget():
    policy = plan_budget(D3_USABLE, input_target_usd=None, input_usd_per_million=Decimal("0.50"), cache_write=True)
    assert policy == BudgetPolicy("legacy", LEGACY_MAX_TOKENS, None)
    assert plan_budget(20_000, input_target_usd=None, input_usd_per_million=Decimal("1"), cache_write=False).ceiling == 5_000


@pytest.mark.parametrize("usable, ceiling", [(229_376, HARD_MAX_TOKENS), (100_000, 25_000), (4, 1)])
def test_the_ceiling_is_a_quarter_of_usable_input_up_to_32768(usable, ceiling):
    assert plan_budget(usable, input_target_usd=Decimal("1"), input_usd_per_million=Decimal("1"), cache_write=False).ceiling == ceiling


def test_a_zero_price_targets_the_ceiling():
    policy = plan_budget(D3_USABLE, input_target_usd=Decimal("0.008192"), input_usd_per_million=Decimal("0"), cache_write=True)
    assert policy.target == policy.ceiling == 32_768


def test_the_target_is_estimator_tokens_floored():
    assert target_tokens(Decimal("0.008192"), Decimal("0.50"), cache_write=True) == 13_107  # 13,107.2
    assert target_tokens(Decimal("0.000001"), Decimal("3"), cache_write=False) == 0


@pytest.mark.parametrize("bad", [Decimal("0"), Decimal("-1"), Decimal("NaN")])
def test_a_target_must_be_a_positive_decimal(bad):
    with pytest.raises(ValueError):
        plan_budget(D3_USABLE, input_target_usd=bad, input_usd_per_million=Decimal("0.50"), cache_write=True)


@pytest.mark.parametrize(
    "ceiling, target, required, expected",
    [
        (32_768, 13_107, 0, 13_107),           # nothing required: the soft target
        (32_768, 13_107, 2_000, 13_107),       # ordinary fit: the target, the floor not binding
        (32_768, 13_107, 12_500, 13_524),      # the floor gives 1,024 of room above the required text
        (32_768, 13_107, 20_000, 21_024),      # required over the target: required wins, floor only
        (32_768, 13_107, 32_000, 32_768),      # the floor uses only the room there is
        (32_768, 13_107, 32_768, 32_768),      # equality: whole, no optional room
        (32_768, 40_000, 0, 32_768),           # a target above the ceiling is clipped
    ],
)
def test_chosen_budget(ceiling, target, required, expected):
    assert chosen_budget(ceiling, target, required) == expected
