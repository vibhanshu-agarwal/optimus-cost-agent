"""Savings-report reference prices (Plan 12.9; ADR-034): the configured comparison columns of the B1 table.

A reference is self-contained dated price evidence for one model, which need not be in the Optimus registry (operator,
2026-11-01, D3). Nothing here looks a reference up in the registry, checks its eligibility, routes to it or calls it,
and no reference price ever feeds registry price ordering, selection or settled cost.

Strict YAML (the registry's loader), a frozen schema with unknown fields refused, and one content-derived snapshot ID
per reference, so formatting alone (``0.10`` or ``0.1``) never changes it. An operator override replaces the packaged
file whole. A missing source date or category price is allowed here: it makes the affected comparison unavailable,
which is the report's job to say.

Neutral: imports nothing from ``optimus``, ``optimus_gateway`` or ``optimus_security``.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from optimus_model_policy.registry import (
    _FROZEN,
    NonNegativeDecimal,
    PositiveCount,
    RegistryError,
    StrictFlag,
    _decimal_text,
    _load_yaml,
)

__all__ = ["Benchmark", "CategoryPrices", "Reference", "ReferenceSet", "Source", "load_references", "packaged_references"]

SNAPSHOT_VERSION = "savings-reference-v1"
TOKENS_PER_PRICE_UNIT = Decimal(1_000_000)  # the one supported unit: USD per million tokens

# Anchored: pydantic's `pattern` searches rather than matching the whole string.
_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_PRINTABLE = re.compile(r"^[^\x00-\x1f\x7f]+$")
Display = Annotated[str, Field(min_length=1, max_length=120, pattern=_PRINTABLE.pattern)]
LongText = Annotated[str, Field(min_length=1, max_length=600, pattern=_PRINTABLE.pattern)]
Price = NonNegativeDecimal | None


class CategoryPrices(BaseModel):
    """USD per million tokens. ``input`` prices uncached input, ``cached_input`` cache reads; None is unknown, never 0."""

    model_config = _FROZEN

    input: Price
    output: Price
    cached_input: Price

    @field_validator("input", "output", "cached_input", mode="before")
    @classmethod
    def prices_from_text(cls, value: Any) -> Any:
        return _decimal_text(value)


class Tier(BaseModel):
    """Prices that replace the base prices for a request whose reported input tokens reach ``min_input_tokens``."""

    model_config = _FROZEN

    min_input_tokens: PositiveCount
    prices: CategoryPrices


class Source(BaseModel):
    model_config = _FROZEN

    url: Annotated[str, Field(max_length=300, pattern=r"^https://[^\s]+$")] | None = None
    evidence: Display | None = None
    revision: Display | None = None
    price_as_of: date | None

    @model_validator(mode="after")
    def one_locator(self) -> Source:
        if (self.url is None) == (self.evidence is None):
            raise ValueError("a source names exactly one of url or evidence")
        return self


class Reference(BaseModel):
    model_config = _FROZEN

    id: Annotated[str, Field(pattern=_ID.pattern)]
    display: Display
    provider: Display | None = None
    unit: Literal["usd_per_million_tokens"]
    prices: CategoryPrices
    tiers: tuple[Tier, ...] = ()
    # True: the schedule bills reasoning tokens as output. None: unknown, so reasoning tokens are unpriced.
    reasoning_billed_as_output: StrictFlag | None
    source: Source

    @field_validator("tiers")
    @classmethod
    def ascending_tiers(cls, tiers: tuple[Tier, ...]) -> tuple[Tier, ...]:
        thresholds = [tier.min_input_tokens for tier in tiers]
        if thresholds != sorted(set(thresholds)):
            raise ValueError("tiers must have strictly ascending min_input_tokens")
        return tiers

    @property
    def snapshot_id(self) -> str:
        body = json.dumps([SNAPSHOT_VERSION, self.model_dump(mode="json")], sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return "hex:" + hashlib.sha256(body.encode("ascii")).hexdigest()

    def prices_for(self, input_tokens: int) -> CategoryPrices:
        """The schedule that applies to a request with ``input_tokens`` reported input tokens (cached included)."""
        applicable = [tier.prices for tier in self.tiers if input_tokens >= tier.min_input_tokens]
        return applicable[-1] if applicable else self.prices


class Benchmark(BaseModel):
    """B4: dated external context for the report's footnote; never evidence of this user's savings."""

    model_config = _FROZEN

    text: LongText
    limitations: LongText
    source: Source


class ReferenceSet(BaseModel):
    model_config = _FROZEN

    version: Literal[1]
    references: tuple[Reference, ...]
    benchmark: Benchmark | None = None

    @field_validator("references")
    @classmethod
    def unique_ids(cls, references: tuple[Reference, ...]) -> tuple[Reference, ...]:
        ids = [reference.id for reference in references]
        if len(ids) != len(set(ids)):
            raise ValueError("reference ids must be unique")
        return references

    @property
    def digest(self) -> str:
        """Binds a report revision to exactly this configuration."""
        body = json.dumps([SNAPSHOT_VERSION, self.model_dump(mode="json")], sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return "hex:" + hashlib.sha256(body.encode("ascii")).hexdigest()


def packaged_references() -> Path:
    return Path(__file__).with_name("savings_references.yaml")


def load_references(path: Path) -> ReferenceSet:
    """The validated reference set in ``path``, or `RegistryError` (``YAML_REJECTED`` / ``REFERENCES_INVALID``)."""
    data, _raw = _load_yaml(path)
    try:
        return ReferenceSet.model_validate(data)
    except ValidationError as exc:
        raise RegistryError("REFERENCES_INVALID", f"{path.name}: {exc.error_count()} error(s)") from None
