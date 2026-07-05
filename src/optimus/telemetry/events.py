from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TelemetryEventKind(StrEnum):
    PRICING_FALLBACK = "pricing_fallback"


class TelemetryEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: TelemetryEventKind
    run_id: str = Field(min_length=1)
    session_id: str | None
    request_id: str = Field(min_length=1)
    occurred_at: datetime
    payload: dict[str, Any]

    @classmethod
    def pricing_fallback(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        provider: str,
        service: str,
        native_unit: str,
        price_snapshot_id: str,
        reason: str,
    ) -> TelemetryEvent:
        return cls(
            kind=TelemetryEventKind.PRICING_FALLBACK,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={
                "provider": provider,
                "service": service,
                "native_unit": native_unit,
                "price_snapshot_id": price_snapshot_id,
                "reason": reason,
            },
        )

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "occurred_at": self.occurred_at.isoformat(),
            **self.payload,
        }
