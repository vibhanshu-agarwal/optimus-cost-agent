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
propagates out of this callback, rather than silently losing attempts; the attached turn's engine
boundary then reports an unavailable view (Task 9). The Gateway adapter, `GatewaySummarizerCall`,
never raises: any failure after the request may have left becomes an `uncertain` attempt carrying what
it knows. A receipt keeps what the ledger cannot hold for an attempt that never completed: its time,
provider request ID and HTTP status. Settling receipts into turn totals and alerts is Task 11's
projection over the existing ledger.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from context_engine import MaintenanceRequest, MaintenanceResult
from context_engine.summary import PROMPT_VERSION, SUMMARY_FORMAT, build_summary_prompt
from optimus.acp.conversation import ConversationSanitizer
from optimus.gateway.errors import GatewayHttpError, GatewayResponseError
from optimus.gateway.models import GatewayRouteAttempt, GatewayUsage
from optimus_model_policy.binding import RouteBinding

ATTEMPT_OUTCOMES = frozenset({"completed", "not_sent", "rejected", "uncertain"})


@dataclass(frozen=True, slots=True)
class SummarizerAttempt:
    """One provider attempt, as the injected call reports it. `cost_usd` is `None` when unknown."""

    attempt_id: str
    gateway_request_id: str | None
    outcome: str
    cost_usd: Decimal | None
    provider_request_id: str | None = None
    http_status: int | None = None

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
    """Who and what a maintenance call serves, captured with the turn's settings: the exact role,
    model, route, reasoning setting and quantizations it was approved for (CP3 carried obligation)."""

    session_id: str
    turn_seq: int
    model_id: str
    role: str
    route: tuple[str, ...]
    reasoning: str | None
    quantizations: tuple[str | None, ...]
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
    recorded_at: datetime
    provider_request_id: str | None
    http_status: int | None


def _utc_now() -> datetime:
    return datetime.now(UTC)


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
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._call = call
        self._sanitizer = sanitizer
        self._identity = identity
        self._record = record_receipt
        self._cancelled = cancelled
        self._clock = clock

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
                    recorded_at=self._clock(),
                    provider_request_id=attempt.provider_request_id,
                    http_status=attempt.http_status,
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


@dataclass(frozen=True, slots=True)
class SummarizerRoute:
    """The exact approved summarizer a turn's maintenance calls use: model, role, route, reasoning
    setting and quantizations. It becomes each call's `MaintenanceIdentity`."""

    model_id: str
    role: str
    route: tuple[str, ...]
    reasoning: str | None
    quantizations: tuple[str | None, ...]


class GatewaySummarizerCall:
    """The production `SummarizerCall`: one summarizer request through the Optimus Gateway.

    It never raises. Every attempt the Gateway reports becomes a `SummarizerAttempt`; the cost the
    Gateway settled goes to the completed attempt, a proven unsent or refused attempt costs nothing,
    and an `uncertain` one stays unknown. A failure with no attempt list is one attempt: completed with
    its reported cost when the Gateway reported usage, otherwise `uncertain` with an unknown cost,
    since the request may have run and been billed. Nothing is retried here.
    """

    def __init__(
        self,
        *,
        gateway_client: Any,
        model_id: str,
        registry_hash: str | None,
        session_id: str,
        request_ids: Callable[[], str],
    ) -> None:
        self._client = gateway_client
        self._model_id = model_id
        self._registry_hash = registry_hash
        self._session_id = session_id
        self._request_ids = request_ids

    def __call__(self, *, prompt: str, max_output_tokens: int) -> SummarizerResponse:
        request_id = self._request_ids()
        binding = (
            RouteBinding(registry_hash=self._registry_hash, request_id=request_id, output_cap=max_output_tokens)
            if self._registry_hash is not None
            else None
        )
        metadata = {"session_id": self._session_id, "purpose": "context_summary", "request_id": request_id}
        try:
            response = self._client.create_response(
                model=self._model_id, input_text=prompt, metadata=metadata, route_binding=binding
            )
        except GatewayHttpError as exc:
            attempts = _attempts(request_id, exc.route_attempts, exc.gateway_usage, http_status=exc.status_code)
            return SummarizerResponse(text=None, finish_status=None, attempts=attempts)
        except GatewayResponseError as exc:
            return SummarizerResponse(text=None, finish_status=None, attempts=_attempts(request_id, (), exc.gateway_usage))
        except Exception:  # noqa: BLE001 - transport loss after dispatch: may have run and been billed
            return SummarizerResponse(text=None, finish_status=None, attempts=_attempts(request_id, (), None))
        attempts = _attempts(request_id, response.route_attempts, response.gateway_usage)
        return SummarizerResponse(text=response.output_text, finish_status=response.finish_reason, attempts=attempts)


def _attempts(
    request_id: str,
    route_attempts: tuple[GatewayRouteAttempt, ...],
    usage: GatewayUsage | None,
    *,
    http_status: int | None = None,
) -> tuple[SummarizerAttempt, ...]:
    if route_attempts:
        # The settled usage belongs to the final completed attempt only; never counted twice.
        settled = max((item.attempt for item in route_attempts if item.outcome == "completed"), default=None)
        return tuple(
            SummarizerAttempt(
                attempt_id=f"{request_id}:{item.attempt}",
                gateway_request_id=item.gateway_request_id,
                outcome=item.outcome,
                cost_usd=_attempt_cost(item.outcome, usage if item.attempt == settled else None),
                provider_request_id=item.provider_request_id,
                http_status=item.http_status,
            )
            for item in route_attempts
        )
    if usage is not None:
        return (
            SummarizerAttempt(
                attempt_id=f"{request_id}:1",
                gateway_request_id=usage.gateway_request_id,
                outcome="completed",
                cost_usd=usage.cost_usd,
                provider_request_id=usage.provider_request_id,
                http_status=http_status,
            ),
        )
    return (
        SummarizerAttempt(
            attempt_id=f"{request_id}:1", gateway_request_id=None, outcome="uncertain", cost_usd=None, http_status=http_status
        ),
    )


def _attempt_cost(outcome: str, usage: GatewayUsage | None) -> Decimal | None:
    if outcome in {"not_sent", "rejected"}:
        return Decimal("0")
    if outcome == "completed" and usage is not None:
        return usage.cost_usd
    return None
