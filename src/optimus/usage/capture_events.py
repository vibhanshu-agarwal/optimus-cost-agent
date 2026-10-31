"""Host-side builders for the durable-capture records (Plan 12.8 Task 1; memory design v4 section 7; ADR-032). The kinds
and each kind's exact schema live in the neutral `optimus_security.usage_capture_contract`; this module turns host
facts into those payloads.

Only allowlisted fields persist: identity and correlation, stage and purpose, outcome, requested and resolved route,
reported usage and cost, model and version, price snapshot, arrival bookkeeping and coverage references. A field the
Gateway did not report stays null: a missing cost is unknown, never zero, and `cache_hit` is recorded only when the
wire carried it, so an absent cache fact is never persisted as an observed miss. Costs are plain decimal strings.

The receipt keeps both replay contracts' digests, `facts_digest` over `StageReceipt.facts()` and `settled_digest` over
`StageReceipt.settled_facts()`, through a versioned canonical serialization that preserves their equality: equal
decimals (``0.25`` and ``0.250``) digest equally, and models are serialized field by field, never through ``repr``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from optimus.gateway.models import GatewayUsage
from optimus.usage.turn_settlement import StageReceipt, TurnCostSummary
from optimus_security.durable_outbox import MAX_RECORD_BYTES
from optimus_security.usage_capture_contract import (
    ATTEMPT_RECEIPT,
    EPOCH_IDENTITIES,
    MAX_LIST,
    PURPOSE,
)

# The purpose each stage's ordinary call serves; a memory call names its own `memory.*` purpose (design v4 section 7).
DEFAULT_PURPOSES = {
    "planning": "agent.plan",
    "answer": "agent.answer",
    "summarization": "context.summary",
    "classification": "auto.classify",
    "operation": "operation.call",
}
DIGEST_VERSION = "capture-facts-v1"
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
    if not PURPOSE.fullmatch(purpose) or (stage != "summarization" and purpose.startswith("memory.")):
        raise ValueError("a purpose is a dotted lowercase name, and only summarization serves memory")
    return purpose


def decimal_text(value: Decimal) -> str:
    """The exact plain decimal string (never exponent notation, never rounded by the active context); only
    insignificant trailing zeros are dropped, so equal decimals give equal text and unequal ones never collide."""
    if not value.is_finite():
        raise ValueError("a persisted decimal is finite")
    text = format(value, "f")  # exact: formatting without a precision applies no context
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return {"decimal": decimal_text(value)}
    if isinstance(value, datetime):
        return {"datetime": value.isoformat()}
    if isinstance(value, BaseModel):
        return {"model": type(value).__name__, "fields": {name: _canonical_value(getattr(value, name)) for name in sorted(type(value).model_fields)}}
    if isinstance(value, tuple | list):
        return [_canonical_value(item) for item in value]
    if value is None or isinstance(value, bool | int | str):
        return value
    raise TypeError(f"no canonical form for {type(value).__name__}")


def digest(values: tuple[object, ...]) -> str:
    """A versioned digest of a replay fingerprint, rendered `hex:` so evidence never looks like a bare secret."""
    body = json.dumps([DIGEST_VERSION, _canonical_value(values)], sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "hex:" + hashlib.sha256(body.encode("ascii")).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return decimal_text(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value


def usage_payload(usage: GatewayUsage) -> dict[str, Any]:
    payload = {name: _jsonable(getattr(usage, name)) for name in _USAGE_FIELDS}
    if "cache_hit" in usage.model_fields_set:
        payload["cache_hit"] = usage.cache_hit
    return payload


def receipt_payload(receipt: StageReceipt, *, epoch_id: str, late: bool, purpose: str | None = None) -> dict[str, Any]:
    """One accepted receipt, exactly as settlement accepted it; never enriched later. The writer adds `at`."""
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


# Room left in each continuation record for its frame and fixed fields.
_PART_BUDGET = MAX_RECORD_BYTES - 4096


def identity_parts(epoch_id: str, summary: TurnCostSummary) -> tuple[list[dict[str, Any]], str]:
    """The close's ordered continuation records and the digest binding all of them, so no identity is silently
    omitted. Each part holds at most `MAX_LIST` IDs per list and fits the per-record cap by its encoded (escaped)
    size; there is always at least one part. Settled IDs fill parts first, then unknown IDs, in order."""
    settled, unknown = list(summary.receipt_ids), list(summary.unknown_attempt_ids)
    chunks: list[tuple[list[str], list[str]]] = [([], [])]
    size = 0
    for which, identity in [(0, item) for item in settled] + [(1, item) for item in unknown]:
        cost = len(json.dumps(identity, ensure_ascii=True)) + 1
        current = chunks[-1]
        if len(current[which]) >= MAX_LIST or size + cost > _PART_BUDGET:
            chunks.append(([], []))
            current, size = chunks[-1], 0
        current[which].append(identity)
        size += cost
    parts = [
        {
            "kind": EPOCH_IDENTITIES,
            "epoch_id": epoch_id,
            "part": index + 1,
            "parts": len(chunks),
            "settled_attempt_ids": settled_ids,
            "unknown_attempt_ids": unknown_ids,
        }
        for index, (settled_ids, unknown_ids) in enumerate(chunks)
    ]
    return parts, digest((epoch_id, tuple(settled), tuple(unknown)))
