from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ModelRate:
    price_snapshot_id: str
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal


MODEL_RATES: dict[tuple[str, str], ModelRate] = {
    ("anthropic", "claude-haiku-4-5-20251001"): ModelRate(
        "anthropic-claude-haiku-4-5-20251001-2026-07-08",
        Decimal("1.00"),
        Decimal("5.00"),
    ),
    ("openrouter", "anthropic/claude-3.5-haiku"): ModelRate(
        "openrouter-anthropic-claude-3.5-haiku-2026-07-08",
        Decimal("0.80"),
        Decimal("4.00"),
    ),
    ("openai", "gpt-4o-mini"): ModelRate(
        "openai-gpt-4o-mini-2026-07-08",
        Decimal("0.15"),
        Decimal("0.60"),
    ),
}


def billing_units(*, input_tokens: int, output_tokens: int) -> int:
    return input_tokens + output_tokens


def lookup_model_rate(*, provider: str, resolved_model: str) -> ModelRate:
    rate = MODEL_RATES.get((provider, resolved_model))
    if rate is None:
        raise ValueError(f"no pricing snapshot for provider={provider!r} model={resolved_model!r}")
    return rate


def compute_cost_usd(
    *,
    provider: str,
    resolved_model: str,
    input_tokens: int,
    output_tokens: int,
) -> tuple[Decimal, str]:
    rate = lookup_model_rate(provider=provider, resolved_model=resolved_model)
    input_cost = Decimal(input_tokens) * rate.input_usd_per_million / Decimal(1_000_000)
    output_cost = Decimal(output_tokens) * rate.output_usd_per_million / Decimal(1_000_000)
    return input_cost + output_cost, rate.price_snapshot_id
