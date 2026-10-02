"""The host's maintenance callback: injected summarizer calls with receipts (Plan 12.2 Task 8).

Design spec 5, 6.2 and 11; Task 1 contracts 2-3 and 6. The engine's `MaintenanceCallback` is
synchronous and runs off the ACP event loop. This host side:

- makes no call for a cancelled turn, or for a prompt or format version it does not hold;
- sends the fixed `context-summary-v1` prompt with the engine's sanitized source after it;
- records a receipt for every provider attempt the call reports, on arrival, whatever the result.
  An unknown cost stays unknown (`None`), never zero. A failed, cancelled, stale or discarded summary
  still costs what it cost;
- re-sanitizes the model's output before it is ever used;
- never sends host authority: the engine's maintenance input carries only ordinary history.

The injected call reports provider failures as attempts. An exception it raises is a defect and
propagates, rather than silently losing attempts. Settling receipts into turn totals and alerts is
Task 11's projection over the existing ledger.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from context_engine import MaintenanceRequest, MaintenanceResult
from context_engine.summary import PROMPT_VERSION, SUMMARY_FORMAT, build_summary_prompt
from optimus.acp.conversation import ConversationSanitizer

ATTEMPT_OUTCOMES = frozenset({"completed", "not_sent", "rejected", "uncertain"})


@dataclass(frozen=True, slots=True)
class SummarizerAttempt:
    """One provider attempt, as the injected call reports it. `cost_usd` is `None` when unknown."""

    attempt_id: str
    gateway_request_id: str | None
    outcome: str
    cost_usd: Decimal | None

    def __post_init__(self) -> None:
        if not self.attempt_id or self.outcome not in ATTEMPT_OUTCOMES:
            raise ValueError("a summarizer attempt needs an id and a known outcome")
        if self.cost_usd is not None and (not self.cost_usd.is_finite() or self.cost_usd < 0):
            raise ValueError("a reported cost must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class SummarizerResponse:
    """What one summarizer request produced: text if any, its true finish status, every attempt."""

    text: str | None
    finish_status: str | None
    attempts: tuple[SummarizerAttempt, ...]


class SummarizerCall(Protocol):
    """The injected model call (the host's Gateway path in CP3; fakes in CP2)."""

    def __call__(self, *, prompt: str, max_output_tokens: int) -> SummarizerResponse: ...


@dataclass(frozen=True, slots=True)
class MaintenanceIdentity:
    """Who and what a maintenance call serves, captured with the turn's settings."""

    session_id: str
    turn_seq: int
    model_id: str
    route: tuple[str, ...]
    reasoning: str | None
    strategy: str
    revision_digest: str


@dataclass(frozen=True, slots=True)
class MaintenanceReceipt:
    """One summarization-stage provider attempt, recorded on arrival."""

    identity: MaintenanceIdentity
    stage: str
    attempt_id: str
    gateway_request_id: str | None
    outcome: str
    cost_usd: Decimal | None
    finish_status: str | None
    covered_turn_ids: tuple[int, ...]


class HostMaintenance:
    """The engine's `MaintenanceCallback`, bound to one turn's captured identity."""

    def __init__(
        self,
        *,
        call: SummarizerCall,
        sanitizer: ConversationSanitizer,
        identity: MaintenanceIdentity,
        record_receipt: Callable[[MaintenanceReceipt], None],
        cancelled: Callable[[], bool],
    ) -> None:
        self._call = call
        self._sanitizer = sanitizer
        self._identity = identity
        self._record = record_receipt
        self._cancelled = cancelled

    def __call__(self, request: MaintenanceRequest) -> MaintenanceResult:
        if request.prompt_version != PROMPT_VERSION or request.format_version != SUMMARY_FORMAT:
            return MaintenanceResult(summary_text=None, attempt_ids=(), status="unsupported", finish_status=None)
        if self._cancelled():
            return MaintenanceResult(summary_text=None, attempt_ids=(), status="cancelled", finish_status=None)
        response = self._call(prompt=build_summary_prompt(request.input_text), max_output_tokens=request.max_output_tokens)
        for attempt in response.attempts:
            self._record(
                MaintenanceReceipt(
                    identity=self._identity,
                    stage="summarization",
                    attempt_id=attempt.attempt_id,
                    gateway_request_id=attempt.gateway_request_id,
                    outcome=attempt.outcome,
                    cost_usd=attempt.cost_usd,
                    finish_status=response.finish_status if attempt.outcome == "completed" else None,
                    covered_turn_ids=request.covered_turn_ids,
                )
            )
        attempt_ids = tuple(attempt.attempt_id for attempt in response.attempts)
        if self._cancelled():
            return MaintenanceResult(summary_text=None, attempt_ids=attempt_ids, status="cancelled", finish_status=response.finish_status)
        completed = any(attempt.outcome == "completed" for attempt in response.attempts)
        if response.text is None or not completed:
            return MaintenanceResult(summary_text=None, attempt_ids=attempt_ids, status="failed", finish_status=response.finish_status)
        return MaintenanceResult(
            summary_text=self._sanitizer.sanitize(response.text),
            attempt_ids=attempt_ids,
            status="completed",
            finish_status=response.finish_status,
        )
