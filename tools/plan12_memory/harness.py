"""Arm D's narrow Gateway adapter for the pinned generic harness (Plan 12.5 Task 3).

It turns the harness's message list into one Optimus Gateway chat request, and the Gateway's
reply into per-attempt receipts. It holds no credential and never re-sends: the Gateway makes
every safe resend itself and marks each failure non-retryable. It imports neither the harness
nor the Gateway; the mini-SWE-agent model class that calls it is a #248 setup item recorded in
reports/plan12-memory-evaluation/harness-choice.json.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from tools.plan12_memory.contracts import AttemptReceipt, GatewayReply, GatewayRoute

ROUTE_BINDING_VERSION = 1  # optimus_model_policy.binding; the tests parse the output with its real from_wire
_ROLES = frozenset({"system", "user", "assistant"})
_UNBILLED = frozenset({"not_sent", "rejected"})  # no model ran (optimus_model_policy.binding.ATTEMPT_OUTCOMES)
_POSSIBLY_BILLED = frozenset({"completed", "uncertain"})
_TOKENS = {"input_tokens": "input_tokens", "output_tokens": "output_tokens", "cache_tokens": "cached_tokens",
           "reasoning_tokens": "reasoning_tokens"}


def encode_transcript(messages: Sequence[Mapping[str, Any]]) -> str:
    """The Gateway joins message texts without their roles, so each role is written into the text."""
    blocks = []
    for message in messages:
        role, content = message.get("role"), message.get("content")
        if role not in _ROLES or not isinstance(content, str):
            raise ValueError(f"unsupported message: role {role!r} with {type(content).__name__} content")
        blocks.append(f"<{role}>\n{content.strip()}\n</{role}>")
    if not blocks:
        raise ValueError("no messages to send")
    return "\n\n".join(blocks)


def build_request(route: GatewayRoute, messages: Sequence[Mapping[str, Any]], *, request_id: str) -> dict[str, Any]:
    """The request body. The caller adds the Gateway's bearer header; no provider key is involved."""
    return {
        "model": route.model_id,
        "messages": [{"role": "user", "content": encode_transcript(messages)}],
        "route_binding": {
            "version": ROUTE_BINDING_VERSION,
            "registry_hash": route.registry_hash,
            "request_id": request_id,
            "output_cap": route.output_cap,
        },
    }


def parse_reply(status: int, body: Mapping[str, Any], *, route: GatewayRoute) -> GatewayReply:
    """The reply's text and one receipt per attempt that may have reached a model.

    A completed attempt is settled from ``gateway_usage``. An uncertain one, or a completed one
    without matching usage, stays intent-only with every token and cost unknown. Unbilled
    attempts carry no charge and no receipt. A malformed body raises ValueError.
    """
    attempts = body.get("route_attempts")
    if attempts is None and status != 200:
        attempts = []  # rejected before routing (authorization or envelope)
    if not isinstance(attempts, list):
        raise ValueError("route_attempts must be a list")
    usage = body.get("gateway_usage")
    receipts = [receipt for record in attempts if (receipt := _receipt(record, usage, route)) is not None]
    if status != 200:
        code = body.get("code")
        return GatewayReply(status=status, content=None, finish_reason=None, attempts=tuple(receipts),
                            error_code=code if isinstance(code, str) else f"HTTP_{status}")
    try:
        choice = body["choices"][0]
        content, finish_reason = choice["message"]["content"], choice["finish_reason"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("a successful reply needs choices[0] with message.content and finish_reason") from exc
    if not isinstance(content, str) or not (finish_reason is None or isinstance(finish_reason, str)):
        raise ValueError("message.content must be text and finish_reason text or null")
    return GatewayReply(status=status, content=content, finish_reason=finish_reason, error_code=None,
                        attempts=tuple(receipts))


def _receipt(record: object, usage: object, route: GatewayRoute) -> AttemptReceipt | None:
    if not isinstance(record, Mapping) or not isinstance(attempt_id := record.get("gateway_request_id"), str):
        raise ValueError("each route attempt needs a gateway_request_id")
    outcome = record.get("outcome")
    if outcome in _UNBILLED:
        return None
    if outcome not in _POSSIBLY_BILLED:
        raise ValueError(f"unknown attempt outcome {outcome!r}")
    fields: dict[str, Any] = {"attempt_id": attempt_id, "gateway_request_id": attempt_id, "state": "intent_only",
                              "price_snapshot_id": None, "cost_usd": None} | dict.fromkeys(_TOKENS)
    if outcome == "completed" and isinstance(usage, Mapping) and usage.get("gateway_request_id") == attempt_id:
        fields |= {key: usage.get(name) for key, name in _TOKENS.items()}
        fields |= {"state": "settled", "price_snapshot_id": f"registry:{route.registry_hash}",
                   "cost_usd": _decimal(usage.get("cost_usd"))}
    # strict: a token count given as text or a boolean is malformed, never coerced
    return AttemptReceipt.model_validate(fields, strict=True)


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("cost_usd must be a decimal string")
    try:
        return Decimal(value)  # AttemptReceipt rejects NaN and infinity
    except InvalidOperation as exc:
        raise ValueError(f"cost_usd {value!r} is not a decimal") from exc
