from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from optimus.telemetry.redaction import redact_for_telemetry
from optimus.telemetry.serialization import json_safe


class TelemetryEventKind(StrEnum):
    MODEL_CALL = "model_call"
    TOOL_CALL = "tool_call"
    GATEWAY_USAGE = "gateway_usage"
    GUARDRAIL_AUDIT = "guardrail_audit"
    RECONCILIATION = "reconciliation"
    ERROR = "error"
    PRICING_FALLBACK = "pricing_fallback"
    RETRY_DECISION = "retry_decision"
    FITNESS_GATE = "fitness_gate"
    GOLDEN_TASK = "golden_task"
    RELEASE_GATE = "release_gate"


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
        response: str,
        input_tokens: int,
        output_tokens: int,
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
                "response": response,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
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

    @classmethod
    def retry_decision(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        attempt: int,
        retry_count: int,
        failure_kind: str,
        action: str,
        delay_ms: int,
        disposition: str,
    ) -> TelemetryEvent:
        return cls(
            kind=TelemetryEventKind.RETRY_DECISION,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={
                "attempt": attempt,
                "retry_count": retry_count,
                "failure_kind": failure_kind,
                "action": action,
                "delay_ms": delay_ms,
                "disposition": disposition,
            },
        )

    @classmethod
    def fitness_gate(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        passed: bool,
        required_gate_names: tuple[str, ...],
        failed_gate_names: tuple[str, ...],
        duration_ms: int,
        cost_usd: Decimal,
    ) -> TelemetryEvent:
        return cls(
            kind=TelemetryEventKind.FITNESS_GATE,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={
                "passed": passed,
                "required_gate_names": required_gate_names,
                "failed_gate_names": failed_gate_names,
                "duration_ms": duration_ms,
                "cost_usd": cost_usd,
            },
        )

    @classmethod
    def golden_task(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        task_id: str,
        passed: bool,
        expected_mode: str,
        actual_mode: str,
        expected_tools: tuple[str, ...],
        actual_tools: tuple[str, ...],
        max_cost_usd: Decimal,
        actual_cost_usd: Decimal,
        expected_final_state: str,
        actual_final_state: str,
    ) -> TelemetryEvent:
        return cls(
            kind=TelemetryEventKind.GOLDEN_TASK,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={
                "task_id": task_id,
                "passed": passed,
                "expected_mode": expected_mode,
                "actual_mode": actual_mode,
                "expected_tools": expected_tools,
                "actual_tools": actual_tools,
                "max_cost_usd": max_cost_usd,
                "actual_cost_usd": actual_cost_usd,
                "expected_final_state": expected_final_state,
                "actual_final_state": actual_final_state,
            },
        )

    @classmethod
    def release_gate(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        gate_name: str,
        passed: bool,
        duration_ms: int,
        output_summary: str,
    ) -> TelemetryEvent:
        return cls(
            kind=TelemetryEventKind.RELEASE_GATE,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={
                "gate_name": gate_name,
                "passed": passed,
                "duration_ms": duration_ms,
                "output_summary": output_summary,
            },
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
        return json_safe(redact_for_telemetry(encoded))

    def to_json_line(self) -> str:
        return json.dumps(self.to_json_dict(), sort_keys=True, separators=(",", ":"), default=_json_default)


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")
