from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from optimus.gateway.models import GatewayUsage


class ProviderUsage(BaseModel):
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
    optimus_credits_debited: Decimal = Field(ge=Decimal("0"))
    model: str | None = None
    model_version: str | None = None
    price_snapshot_id: str = Field(min_length=1)

    @classmethod
    def from_gateway_usage(
        cls,
        gateway_usage: GatewayUsage,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
    ) -> ProviderUsage:
        missing = [
            name
            for name in ("service", "native_unit", "optimus_credits_debited", "price_snapshot_id")
            if getattr(gateway_usage, name) is None
        ]
        if missing:
            raise ValueError(f"gateway usage missing normalized fields: {','.join(missing)}")
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
            service=gateway_usage.service or "",
            native_unit=gateway_usage.native_unit or "",
            optimus_credits_debited=gateway_usage.optimus_credits_debited or Decimal("0"),
            model=gateway_usage.model,
            model_version=gateway_usage.model_version,
            price_snapshot_id=gateway_usage.price_snapshot_id or "",
        )
