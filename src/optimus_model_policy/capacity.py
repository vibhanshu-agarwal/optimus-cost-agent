"""Complete-request capacity (spec 9.4; Task 1 contracts §4). Pure functions; no money.

    effective_total = min(context_ceiling, smallest verified window in the route allow-set)
    usable_input    = effective_total - output_reserve      # the reserve is counted once
    complete_input_estimate <= usable_input                 # equality admitted
    0 < output_reserve <= smallest verified max output

The estimate is computed from the final packed request: every message's UTF-8 bytes (after all host
transformations), its framing, and the final serialized tool material. A caller-declared token count
is never trusted. Unknown models, aliases, estimators and unverified routes are refused before any
upstream call; the request is never exempted to make it fit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from optimus_model_policy.registry import EstimatorProfile, RegistrySnapshot

__all__ = ["CapacityDecision", "InputEstimate", "Message", "PackedModelRequest", "estimate_complete_input", "guard_request"]


@dataclass(frozen=True, slots=True)
class Message:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class PackedModelRequest:
    """The final request as it will be sent: messages after every host transformation, the final
    serialized tool material (escaping included) and the actual upstream output cap."""

    model_id: str
    messages: tuple[Message, ...]
    tools_json: str
    output_cap: int


@dataclass(frozen=True, slots=True)
class InputEstimate:
    tokens: int
    utf8_bytes: int
    message_count: int
    method: str


@dataclass(frozen=True, slots=True)
class CapacityDecision:
    allowed: bool
    reason: str | None
    input_tokens: int
    output_reserve: int
    usable_input: int
    effective_total: int


def estimate_complete_input(request: PackedModelRequest, profile: EstimatorProfile) -> InputEstimate:
    utf8_bytes = sum(len(message.content.encode("utf-8")) for message in request.messages)
    utf8_bytes += len(request.tools_json.encode("utf-8"))
    content_tokens = math.ceil(profile.tokens_per_byte * utf8_bytes)
    tokens = content_tokens + profile.per_message_tokens * len(request.messages) + profile.fixed_tokens
    return InputEstimate(tokens=tokens, utf8_bytes=utf8_bytes, message_count=len(request.messages), method=profile.method)


def _refuse(reason: str, *, reserve: int = 0, usable: int = 0, total: int = 0, tokens: int = 0) -> CapacityDecision:
    return CapacityDecision(
        allowed=False, reason=reason, input_tokens=tokens, output_reserve=reserve, usable_input=usable, effective_total=total
    )


def guard_request(request: PackedModelRequest, snapshot: RegistrySnapshot, approved_hash: str) -> CapacityDecision:
    """Admit the request only if it fits the approved snapshot's verified route for that model."""
    if approved_hash != snapshot.effective_hash:
        return _refuse("SNAPSHOT_NOT_APPROVED")
    policy = snapshot.policy
    entry = policy.models.get(request.model_id)
    if entry is None:
        return _refuse("UNKNOWN_MODEL")
    profile = policy.estimators.get(entry.route.estimator)
    if profile is None:
        return _refuse("ESTIMATOR_UNKNOWN")
    if not profile.verified:
        return _refuse("ESTIMATOR_UNVERIFIED")
    endpoints = entry.route.endpoints
    windows = [endpoint.context_window_tokens for endpoint in endpoints]
    outputs = [endpoint.max_output_tokens for endpoint in endpoints]
    if any(not endpoint.verified for endpoint in endpoints) or any(v is None for v in windows + outputs):
        return _refuse("ROUTE_UNVERIFIED")
    effective_total = min(policy.context_ceiling_tokens, min(windows))  # type: ignore[type-var]
    reserve = request.output_cap
    if reserve <= 0:
        return _refuse("OUTPUT_RESERVE_INVALID", reserve=reserve, total=effective_total)
    if reserve > min(outputs):  # type: ignore[type-var]
        return _refuse("OUTPUT_RESERVE_EXCEEDS_ROUTE", reserve=reserve, total=effective_total)
    usable = effective_total - reserve
    estimate = estimate_complete_input(request, profile)
    if estimate.tokens > usable:
        return _refuse("INPUT_EXCEEDS_CAPACITY", reserve=reserve, usable=usable, total=effective_total, tokens=estimate.tokens)
    return CapacityDecision(
        allowed=True,
        reason=None,
        input_tokens=estimate.tokens,
        output_reserve=reserve,
        usable_input=usable,
        effective_total=effective_total,
    )
