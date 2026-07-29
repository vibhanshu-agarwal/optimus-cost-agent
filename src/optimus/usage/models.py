from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from optimus.gateway.models import GatewayUsage


class ProviderUsage(BaseModel):
    """Immutable, persisted superset of a settled ``GatewayUsage`` envelope.

    ``service`` and ``native_unit`` are caller-supplied persistence context,
    not sourced from the optional wire fields on ``GatewayUsage``.
    ``price_snapshot_id`` is optional diagnostic metadata. All other fields
    are copied verbatim from the provider-reported envelope; nothing here
    estimates a value the Gateway did not report.
    """

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    session_id: str | None = None
    request_id: str = Field(min_length=1)
    occurred_at: datetime
    gateway_request_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    provider_request_id: str | None = None
    cache_hit: bool = False
    billing_units: int = Field(ge=0)
    cost_usd: Decimal = Field(ge=Decimal("0"))
    service: str = Field(min_length=1)
    native_unit: str = Field(min_length=1)
    model: str | None = None
    model_version: str | None = None
    price_snapshot_id: str | None = None
    resolved_provider: str | None = None
    resolved_model: str | None = None
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    cached_tokens: int | None = Field(default=None, ge=0)
    cache_age_seconds: int | None = Field(default=None, ge=0)

    @field_validator("cost_usd")
    @classmethod
    def _cost_usd_must_be_finite(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("cost_usd must be finite")
        return value

    @classmethod
    def from_gateway_usage(
        cls,
        gateway_usage: GatewayUsage,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        service: str,
        native_unit: str,
        price_snapshot_id: str | None = None,
    ) -> ProviderUsage:
        return cls(
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            gateway_request_id=gateway_usage.gateway_request_id,
            provider=gateway_usage.provider,
            provider_request_id=gateway_usage.provider_request_id,
            cache_hit=gateway_usage.cache_hit,
            billing_units=gateway_usage.billing_units,
            cost_usd=gateway_usage.cost_usd,
            service=service,
            native_unit=native_unit,
            model=gateway_usage.model,
            model_version=gateway_usage.model_version,
            price_snapshot_id=price_snapshot_id,
            resolved_provider=gateway_usage.resolved_provider,
            resolved_model=gateway_usage.resolved_model,
            input_tokens=gateway_usage.input_tokens,
            output_tokens=gateway_usage.output_tokens,
            total_tokens=gateway_usage.total_tokens,
            reasoning_tokens=gateway_usage.reasoning_tokens,
            cached_tokens=gateway_usage.cached_tokens,
            cache_age_seconds=gateway_usage.cache_age_seconds,
        )
