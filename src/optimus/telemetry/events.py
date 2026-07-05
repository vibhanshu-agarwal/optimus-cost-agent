from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TelemetryEventKind(StrEnum):
    MODEL_CALL = "model_call"
    TOOL_CALL = "tool_call"
    GATEWAY_USAGE = "gateway_usage"
    GUARDRAIL_AUDIT = "guardrail_audit"
    RECONCILIATION = "reconciliation"
    ERROR = "error"
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
    def model_call(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        model: str,
        model_version: str | None,
        provider: str,
        cache_hit: bool,
        billing_units: int,
        cost_usd: Decimal,
        latency_ms: int,
        prompt: str,
        response_summary: str,
    ) -> TelemetryEvent:
        return cls(
            kind=TelemetryEventKind.MODEL_CALL,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={
                "model": model,
                "model_version": model_version,
                "provider": provider,
                "cache_hit": cache_hit,
                "billing_units": billing_units,
                "cost_usd": cost_usd,
                "latency_ms": latency_ms,
                "prompt": prompt,
                "response_summary": response_summary,
            },
        )

    @classmethod
    def gateway_usage(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        gateway_request_id: str,
        provider: str,
        cache_hit: bool,
        billing_units: int,
        cost_usd: Decimal,
        service: str,
        native_unit: str,
        optimus_credits_debited: Decimal,
        model: str | None,
        model_version: str | None,
        price_snapshot_id: str,
    ) -> TelemetryEvent:
        return cls(
            kind=TelemetryEventKind.GATEWAY_USAGE,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={
                "gateway_request_id": gateway_request_id,
                "provider": provider,
                "cache_hit": cache_hit,
                "billing_units": billing_units,
                "cost_usd": cost_usd,
                "service": service,
                "native_unit": native_unit,
                "optimus_credits_debited": optimus_credits_debited,
                "model": model,
                "model_version": model_version,
                "price_snapshot_id": price_snapshot_id,
            },
        )

    @classmethod
    def reconciliation(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        matched_gateway_request_ids: frozenset[str],
        missing_provider_usage_ids: frozenset[str],
        missing_evidence_ids: frozenset[str],
        evidence_cost_usd: Decimal,
        provider_cost_usd: Decimal,
        cost_delta_usd: Decimal,
        reconciled: bool,
    ) -> TelemetryEvent:
        return cls(
            kind=TelemetryEventKind.RECONCILIATION,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={
                "matched_gateway_request_ids": sorted(matched_gateway_request_ids),
                "missing_provider_usage_ids": sorted(missing_provider_usage_ids),
                "missing_evidence_ids": sorted(missing_evidence_ids),
                "evidence_cost_usd": evidence_cost_usd,
                "provider_cost_usd": provider_cost_usd,
                "cost_delta_usd": cost_delta_usd,
                "reconciled": reconciled,
            },
        )

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

    @classmethod
    def tool_call(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        tool_name: str,
        parameters: dict[str, Any],
        result_summary: str,
        latency_ms: int,
        policy_reason: str,
        authorization_outcome: str,
    ) -> TelemetryEvent:
        return cls(
            kind=TelemetryEventKind.TOOL_CALL,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={
                "tool_name": tool_name,
                "parameters": parameters,
                "result_summary": result_summary,
                "latency_ms": latency_ms,
                "policy_reason": policy_reason,
                "authorization_outcome": authorization_outcome,
            },
        )

    @classmethod
    def guardrail_audit(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        tool_surface: str,
        verdict: str,
        rule_id: str,
        failed_checks: tuple[str, ...],
        requires_human_approval: bool,
    ) -> TelemetryEvent:
        return cls(
            kind=TelemetryEventKind.GUARDRAIL_AUDIT,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={
                "tool_surface": tool_surface,
                "verdict": verdict,
                "rule_id": rule_id,
                "failed_checks": failed_checks,
                "requires_human_approval": requires_human_approval,
            },
        )

    @classmethod
    def error(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        error_type: str,
        message: str,
        disposition: str,
    ) -> TelemetryEvent:
        return cls(
            kind=TelemetryEventKind.ERROR,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={"error_type": error_type, "message": message, "disposition": disposition},
        )

    def to_json_dict(self) -> dict[str, Any]:
        encoded = {
            "kind": self.kind.value,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "occurred_at": self.occurred_at.isoformat(),
            **self.payload,
        }
        return _json_safe(_redact(encoded))

    def to_json_line(self) -> str:
        return json.dumps(self.to_json_dict(), sort_keys=True, separators=(",", ":"), default=_json_default)


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


_EXACT_SECRET_KEYS = {
    "authorization",
    "auth_header",
    "x-api-key",
}

_SECRET_KEY_PARTS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "credential",
    "optimus_api_key",
)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key).lower()
            if key_text in _EXACT_SECRET_KEYS or any(part in key_text for part in _SECRET_KEY_PARTS):
                redacted[key] = "**********"
            else:
                redacted[key] = _redact(child)
        return redacted
    if isinstance(value, (list, tuple)):
        return [_redact(child) for child in value]
    if isinstance(value, str):
        return re.sub(r"(?i)(authorization:\s*bearer\s+|bearer\s+)[^\s]+", r"\1**********", value)
    return value


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_json_safe(child) for child in value]
    if isinstance(value, Decimal):
        return str(value)
    return value
