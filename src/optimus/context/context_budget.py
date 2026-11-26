"""The context pack's preparation-time budget (Plan 12.14, one preparation-time budget; D3). Pure.

An entry without `context_budget.input_target_usd` keeps M1's legacy budget, min(floor(0.25 * usable input), 16,384). An entry with it
gets a hard ceiling C = min(floor(0.25 * usable input), 32,768) and a soft target T = floor(1,000,000 * target / effective input price),
in estimator tokens, never spend. A possible cache write prices input at CACHE_WRITE_INPUT_MULTIPLIER; there is no read discount. A zero
price targets C. The pack then chooses min(C, max(V + min(1024, C - V), T)) once it has measured its required text V
(context_engine.context_pack.chosen_budget), so required evidence wins over the soft target.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Literal

from optimus_model_policy.registry import CACHE_WRITE_INPUT_MULTIPLIER

PACK_SHARE: Final = Decimal("0.25")  # of the route's usable input, as M1
LEGACY_MAX_TOKENS: Final = 16_384
HARD_MAX_TOKENS: Final = 32_768
POLICY_VERSION: Final = "m2b-v1"


@dataclass(frozen=True)
class BudgetPolicy:
    name: Literal["legacy", "model-aware"]
    ceiling: int  # the pack's budget_tokens: legacy's whole budget, or C
    target: int | None  # T; None under legacy


def _share(usable_input: int) -> int:
    return int(usable_input * PACK_SHARE)


def legacy_budget(usable_input: int) -> int:
    return min(_share(usable_input), LEGACY_MAX_TOKENS)


def target_tokens(input_target_usd: Decimal, input_usd_per_million: Decimal, *, cache_write: bool) -> int:
    price = input_usd_per_million * (CACHE_WRITE_INPUT_MULTIPLIER if cache_write else 1)
    return int(Decimal(1_000_000) * input_target_usd / price)


def plan_budget(usable_input: int, *, input_target_usd: Decimal | None, input_usd_per_million: Decimal, cache_write: bool) -> BudgetPolicy:
    if input_target_usd is None:
        return BudgetPolicy("legacy", legacy_budget(usable_input), None)
    if not input_target_usd.is_finite() or input_target_usd <= 0:
        raise ValueError("context_budget.input_target_usd must be a positive decimal")
    ceiling = min(_share(usable_input), HARD_MAX_TOKENS)
    if input_usd_per_million == 0:
        return BudgetPolicy("model-aware", ceiling, ceiling)
    return BudgetPolicy("model-aware", ceiling, target_tokens(input_target_usd, input_usd_per_million, cache_write=cache_write))
