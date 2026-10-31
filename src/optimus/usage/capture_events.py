"""The durable-capture event contract, version 1 (Plan 12.8 Task 1; memory design v4 section 7; ADR-032).

Every record the host or the Gateway appends to its outbox stream is one of these payloads, framed by
`optimus_security.durable_outbox`. Only allowlisted fields persist: identity and correlation, stage and purpose,
outcome, requested and resolved route, reported usage and cost, model and version, price snapshot, arrival
bookkeeping and coverage references. No prompt, reply, router payload, exception text or credential is admitted.

A field the Gateway did not report stays absent or null: a missing cost is unknown, never zero, and `cache_hit` is
recorded only when the wire carried it, so an absent cache fact is never persisted as an observed miss. Costs are
decimal strings. The receipt keeps both replay contracts' digests: `facts_digest` over `StageReceipt.facts()` and
`settled_digest` over `StageReceipt.settled_facts()`.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from optimus.gateway.models import GatewayUsage
from optimus.usage.turn_settlement import StageReceipt
from optimus_security.usage_capture_contract import (
    ATTEMPT_INTENT,
    ATTEMPT_RECEIPT,
    EPOCH_BEGIN,
    EPOCH_CLOSE,
    GATEWAY_ATTEMPT_INTENT,
    GATEWAY_ATTEMPT_OUTCOME,
    INTEGRITY_FAILURE,
    INVOCATION_END,
    INVOCATION_OPEN,
    STREAM_END,
    STREAM_START,
)

__all__ = [
    "ATTEMPT_INTENT",
    "ATTEMPT_RECEIPT",
    "EPOCH_BEGIN",
    "EPOCH_CLOSE",
    "GATEWAY_ATTEMPT_INTENT",
    "GATEWAY_ATTEMPT_OUTCOME",
    "INTEGRITY_FAILURE",
    "INVOCATION_END",
    "INVOCATION_OPEN",
    "STREAM_END",
    "STREAM_START",
    "purpose_for",
    "receipt_payload",
    "usage_payload",
]

# The purpose each stage's ordinary call serves; a memory call names its own `memory.*` purpose (design v4 section 7).
DEFAULT_PURPOSES = {
    "planning": "agent.plan",
    "answer": "agent.answer",
    "summarization": "context.summary",
    "classification": "auto.classify",
}
_PURPOSE = re.compile(r"[a-z][a-z0-9_]*(\.[a-z0-9_]+)+")
_USAGE_FIELDS = (
    "gateway_request_id",
    "provider",
    "provider_request_id",
    "billing_units",
    "cost_usd",
    "service",
    "native_unit",
    "model",
    "model_version",
    "price_snapshot_id",
    "resolved_provider",
    "resolved_model",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "reasoning_tokens",
    "cached_tokens",
    "cache_age_seconds",
    "route_request_id",
    "attempt",
)
_RECEIPT_FIELDS = (
    "session_id",
    "turn_id",
    "stage",
    "attempt_id",
    "gateway_request_id",
    "outcome",
    "requested_model",
    "role",
    "reasoning",
    "resolved_model",
    "provider",
    "resolved_provider",
    "strategy",
    "revision_digest",
    "registry_hash",
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "provider_request_id",
    "http_status",
    "post_teardown",
)


def purpose_for(stage: str, purpose: str | None = None) -> str:
    """The persisted purpose: the stage's ordinary one, or an explicit well-formed one (a memory call's `memory.*`)."""
    if purpose is None:
        return DEFAULT_PURPOSES[stage]
    if not _PURPOSE.fullmatch(purpose) or (stage != "summarization" and purpose.startswith("memory.")):
        raise ValueError("a purpose is a dotted lowercase name, and only summarization serves memory")
    return purpose


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value


def digest(values: tuple[object, ...]) -> str:
    """A stable digest of a replay fingerprint, rendered `hex:` so evidence never looks like a bare secret."""
    return "hex:" + hashlib.sha256(repr(tuple(_jsonable(value) for value in values)).encode("utf-8")).hexdigest()


def usage_payload(usage: GatewayUsage) -> dict[str, Any]:
    payload = {name: _jsonable(getattr(usage, name)) for name in _USAGE_FIELDS}
    if "cache_hit" in usage.model_fields_set:
        payload["cache_hit"] = usage.cache_hit
    return payload


def receipt_payload(receipt: StageReceipt, *, epoch_id: str, late: bool, purpose: str | None = None) -> dict[str, Any]:
    """One accepted receipt, exactly as settlement accepted it; never enriched later."""
    payload: dict[str, Any] = {name: _jsonable(getattr(receipt, name)) for name in _RECEIPT_FIELDS}
    payload.update(
        kind=ATTEMPT_RECEIPT,
        epoch_id=epoch_id,
        purpose=purpose_for(receipt.stage, purpose),
        route=list(receipt.route),
        quantizations=list(receipt.quantizations),
        reported_cost_usd=_jsonable(receipt.reported_cost_usd),
        recorded_at=receipt.recorded_at.isoformat(),
        usage=usage_payload(receipt.gateway_usage) if receipt.gateway_usage is not None else None,
        facts_digest=digest(receipt.facts()),
        settled_digest=digest(receipt.settled_facts()),
        late=late,
    )
    return payload
