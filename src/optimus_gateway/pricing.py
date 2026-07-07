from __future__ import annotations

from decimal import Decimal

# Anthropic Claude Haiku 4.5 published list pricing snapshot (USD per 1M tokens).
PRICE_SNAPSHOT_ID = "anthropic-claude-haiku-4-5-20251001-2026-07-08"
INPUT_USD_PER_MILLION_TOKENS = Decimal("1.00")
OUTPUT_USD_PER_MILLION_TOKENS = Decimal("5.00")


def billing_units(*, input_tokens: int, output_tokens: int) -> int:
    return input_tokens + output_tokens


def compute_cost_usd(*, input_tokens: int, output_tokens: int) -> Decimal:
    input_cost = Decimal(input_tokens) * INPUT_USD_PER_MILLION_TOKENS / Decimal(1_000_000)
    output_cost = Decimal(output_tokens) * OUTPUT_USD_PER_MILLION_TOKENS / Decimal(1_000_000)
    return input_cost + output_cost
