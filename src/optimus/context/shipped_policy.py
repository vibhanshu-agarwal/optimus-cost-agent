"""The accepted numeric context policy, shared by the shipped ordinary attachment and the Stage C test composition
(Plan 12.2 closure plan v3: one shipped numeric policy; Stage C imports it rather than production importing Stage C).

The values are the accepted closure numeric set (closure proposal section 1; Codex scope agreement section 1),
unchanged from the ones Stage C's attached cases ran with. ``attachment_limits`` derives the per-route limits from
the trusted snapshot: usable input is the request ceiling (the smaller of the policy ceiling and the route window)
less the implementer reserve; history gets ``min(131072, floor(0.8 * usable))``; the summary byte bound is
``floor(S / r)`` for the route's estimator ratio ``r``.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from context_engine import StrategyParameters, ViewLimits
from context_engine.summary import PROMPT_VERSION, SUMMARY_FORMAT
from optimus.context.maintenance import MaintenanceReceipt
from optimus_model_policy import Message, PackedModelRequest, RegistrySnapshot
from optimus_model_policy.capacity import estimate_complete_input

__all__ = [
    "ANCHOR_INPUT_TOKENS",
    "COMPACTION_TAIL_INPUT_TOKENS",
    "HISTORY_ALLOWANCE_CAP_TOKENS",
    "HYBRID_TAIL_INPUT_TOKENS",
    "INITIAL_STRATEGY",
    "MAINTENANCE_INPUT_TOKENS",
    "MAX_MAINTENANCE_CALLS",
    "MAX_REPACKS",
    "RECORD_RESERVATION_BYTES",
    "SOURCE_MAX_BYTES",
    "SUMMARY_OUTPUT_TOKENS",
    "TRANSIENT_MAX_BYTES",
    "AttachmentLimits",
    "attachment_limits",
    "no_attachment_ledger",
]

SOURCE_MAX_BYTES = 1_048_576
RECORD_RESERVATION_BYTES = 131_072
TRANSIENT_MAX_BYTES = 524_288
MAINTENANCE_INPUT_TOKENS = 131_072
SUMMARY_OUTPUT_TOKENS = 8_192
ANCHOR_INPUT_TOKENS = 16_384
COMPACTION_TAIL_INPUT_TOKENS = 32_768
HYBRID_TAIL_INPUT_TOKENS = 65_536
MAX_MAINTENANCE_CALLS = 18
MAX_REPACKS = 1
HISTORY_ALLOWANCE_CAP_TOKENS = 131_072
INITIAL_STRATEGY = "compaction"


@dataclass(frozen=True)
class AttachmentLimits:
    parameters: StrategyParameters
    limits: ViewLimits
    usable_input_tokens: int
    estimate_request: Callable[[str], int]


def attachment_limits(snapshot: RegistrySnapshot, model_id: str) -> AttachmentLimits:
    """The accepted limits on ``model_id``'s own route and estimator in the trusted snapshot. Raises KeyError when
    the snapshot does not state the model, its estimator, a route window or the output reserves."""
    policy = snapshot.policy
    entry = policy.models[model_id]
    estimator = policy.estimators[entry.route.estimator]
    windows: list[int] = []
    for endpoint in entry.route.endpoints:
        if endpoint.context_window_tokens is None:  # a guarded route always states its window
            raise KeyError(f"{model_id}: route window not stated")
        windows.append(endpoint.context_window_tokens)
    window = min(windows)
    output_reserve = policy.output_reserve_tokens["implementer"]
    usable = min(policy.context_ceiling_tokens, window) - output_reserve
    summary_tokens = min(SUMMARY_OUTPUT_TOKENS, policy.output_reserve_tokens["summarizer"])
    ratio = estimator.tokens_per_byte

    def estimate_history(text: str) -> int:
        return math.ceil(ratio * len(text.encode("utf-8")))

    def estimate_request(text: str) -> int:
        request = PackedModelRequest(model_id=model_id, messages=(Message(role="user", content=text),), tools_json="", output_cap=output_reserve)
        return estimate_complete_input(request, estimator).tokens

    parameters = StrategyParameters(
        anchor_input_tokens=ANCHOR_INPUT_TOKENS,
        compaction_tail_input_tokens=COMPACTION_TAIL_INPUT_TOKENS,
        hybrid_tail_input_tokens=HYBRID_TAIL_INPUT_TOKENS,
        summary_output_tokens=summary_tokens,
        max_maintenance_calls=MAX_MAINTENANCE_CALLS,
        prompt_version=PROMPT_VERSION,
        format_version=SUMMARY_FORMAT,
    )
    limits = ViewLimits(
        history_input_tokens=min(HISTORY_ALLOWANCE_CAP_TOKENS, math.floor(usable * 0.8)),
        source_max_bytes=SOURCE_MAX_BYTES,
        transient_max_bytes=TRANSIENT_MAX_BYTES,
        maintenance_input_tokens=MAINTENANCE_INPUT_TOKENS,
        maintenance_output_tokens=summary_tokens,
        summary_max_bytes=math.floor(summary_tokens / ratio),
        estimate_history=estimate_history,
        estimator_id=entry.route.estimator,
    )
    return AttachmentLimits(parameters=parameters, limits=limits, usable_input_tokens=usable, estimate_request=estimate_request)


def no_attachment_ledger(_receipt: MaintenanceReceipt) -> None:
    """The attachment-level usage ledger sink. The host runner has no usage ledger to receive it; every receipt
    still reaches the turn's session settlement (receipt-first accounting), and the Gateway records every
    physical attempt."""
