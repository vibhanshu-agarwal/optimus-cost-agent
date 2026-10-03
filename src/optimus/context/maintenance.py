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

import itertools
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from context_engine import MaintenanceRequest, MaintenanceResult
from context_engine.summary import PROMPT_VERSION, SUMMARY_FORMAT, build_summary_prompt
from optimus.acp.conversation import ConversationSanitizer
from optimus.gateway.attempts import PREFLIGHT_REFUSAL_CODES, ProviderAttempt, attempts_from_failure, attempts_from_response
from optimus.gateway.models import GatewayUsage
from optimus_model_policy.binding import RouteBinding

# Re-exported: the one preflight classifier every stage uses lives in optimus.gateway.attempts.
__all__ = ["PREFLIGHT_REFUSAL_CODES"]

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
    provider: str | None = None
    resolved_provider: str | None = None
    resolved_model: str | None = None
    gateway_usage: GatewayUsage | None = None
    """The Gateway's original normalized usage, on the attempt that settled the request only."""

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


class SummarizerFactory(Protocol):
    """Binds a summarizer call to one turn: its identity, and the turn's way to deliver a required
    notice (such as the Contributor disclosure) to the user before anything is sent."""

    def __call__(self, identity: MaintenanceIdentity, deliver_notice: Callable[[str], bool]) -> SummarizerCall: ...


@dataclass(frozen=True, slots=True)
class MaintenanceIdentity:
    """Who and what a maintenance call serves, captured with the turn's settings: the exact role,
    model, route, reasoning setting and quantizations it was approved for (CP3 carried obligation),
    and the trusted registry snapshot they come from (Codex CP3 ruling R5)."""

    session_id: str
    turn_seq: int
    model_id: str
    role: str
    route: tuple[str, ...]
    reasoning: str | None
    quantizations: tuple[str | None, ...]
    strategy: str
    revision_digest: str
    registry_hash: str | None = None


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
    provider: str | None = None
    resolved_provider: str | None = None
    resolved_model: str | None = None
    gateway_usage: GatewayUsage | None = None


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
                    provider=attempt.provider,
                    resolved_provider=attempt.resolved_provider,
                    resolved_model=attempt.resolved_model,
                    gateway_usage=attempt.gateway_usage,
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

    It never raises. Every attempt the Gateway reports becomes a `SummarizerAttempt`, classified by
    the one host classifier every stage uses (`optimus.gateway.attempts`): the cost the Gateway settled
    goes to the completed attempt, with its original usage; a proven unsent or refused attempt costs
    nothing; an `uncertain` one stays unknown. Nothing is retried here.

    `bind(request_id, input_text, output_cap)` returns the request's route binding (with its
    Contributor disclosure, noticed first, where required) or None when a required notice was not
    delivered: then nothing is sent. Without `bind` no binding is sent (registry enforcement inactive).
    """

    def __init__(
        self,
        *,
        gateway_client: Any,
        model_id: str,
        session_id: str,
        request_ids: Callable[[], str],
        bind: Callable[[str, str, int], RouteBinding | None] | None = None,
    ) -> None:
        self._client = gateway_client
        self._model_id = model_id
        self._session_id = session_id
        self._request_ids = request_ids
        self._bind = bind

    def __call__(self, *, prompt: str, max_output_tokens: int) -> SummarizerResponse:
        request_id = self._request_ids()
        binding = None
        if self._bind is not None:
            binding = self._bind(request_id, prompt, max_output_tokens)
            if binding is None:
                unsent = SummarizerAttempt(attempt_id=f"{request_id}:1", gateway_request_id=None, outcome="not_sent", cost_usd=Decimal("0"))
                return SummarizerResponse(text=None, finish_status=None, attempts=(unsent,))
        metadata = {"session_id": self._session_id, "purpose": "context_summary", "request_id": request_id}
        try:
            response = self._client.create_response(
                model=self._model_id, input_text=prompt, metadata=metadata, route_binding=binding
            )
        except Exception as exc:  # noqa: BLE001 - every failure is classified; transport loss stays unknown
            return SummarizerResponse(text=None, finish_status=None, attempts=_attempts(request_id, attempts_from_failure(exc)))
        attempts = _attempts(request_id, attempts_from_response(response))
        return SummarizerResponse(text=response.output_text, finish_status=response.finish_reason, attempts=attempts)


def _attempts(request_id: str, attempts: tuple[ProviderAttempt, ...]) -> tuple[SummarizerAttempt, ...]:
    return tuple(
        SummarizerAttempt(
            attempt_id=f"{request_id}:{attempt.number}",
            gateway_request_id=attempt.gateway_request_id,
            outcome=attempt.outcome,
            cost_usd=attempt.cost_usd,
            provider_request_id=attempt.provider_request_id,
            http_status=attempt.http_status,
            provider=attempt.gateway_usage.provider if attempt.gateway_usage else None,
            resolved_provider=attempt.gateway_usage.resolved_provider if attempt.gateway_usage else None,
            resolved_model=attempt.gateway_usage.resolved_model if attempt.gateway_usage else None,
            gateway_usage=attempt.gateway_usage,
        )
        for attempt in attempts
    )


def gateway_summarizer_factory(
    *,
    gateway_client: Any,
    route: SummarizerRoute,
    snapshot: Any | None,
    disclosure_key: bytes | None,
) -> SummarizerFactory:
    """The production summarizer for an attachment: one `GatewaySummarizerCall` per turn.

    With a trusted registry `snapshot` and launch `disclosure_key`, each request is route-bound and,
    for a Contributor route, the turn's notice is delivered before its disclosure is issued; without
    them (registry enforcement inactive) no binding is sent. Request identities, and so attempt
    identities, are minted here per turn and call: session, turn, call ordinal and a random part, so
    two turns can never claim one attempt (Fable CP3 review MAJOR-3).

    The identity a turn captured must be the route actually bound (Codex CP3 ruling R5): its model,
    role, endpoints, reasoning and quantizations must equal `route`, and with a snapshot, `route` must
    be what the snapshot gives that model and the identity's registry hash the snapshot's. Anything
    else raises `RouteIdentityError` before a request exists, so no attempt is ever relabelled."""
    from optimus.gateway.disclosure import ContributorDisclosure
    from optimus.gateway.route_binding import RouteIdentityError, registry_route_identity

    configured = (route.model_id, route.role, route.route, route.reasoning, route.quantizations)
    if snapshot is not None:
        trusted = registry_route_identity(snapshot, model_id=route.model_id, role=route.role)
        if configured != (trusted.model_id, trusted.role, trusted.route, trusted.reasoning, trusted.quantizations):
            raise RouteIdentityError("the summarizer route does not match the trusted registry")

    def bind_turn(identity: MaintenanceIdentity, deliver_notice: Callable[[str], bool]) -> SummarizerCall:
        captured = (identity.model_id, identity.role, identity.route, identity.reasoning, identity.quantizations)
        if captured != configured:
            raise RouteIdentityError("the turn's summarizer identity is not the route this summarizer binds")
        if snapshot is not None and identity.registry_hash != snapshot.effective_hash:
            raise RouteIdentityError("the turn's registry identity is not the trusted snapshot")
        ordinal = itertools.count(1)

        def request_ids() -> str:
            return f"{identity.session_id}:{identity.turn_seq}:summary:{next(ordinal)}:{uuid.uuid4().hex}"

        bind = None
        if snapshot is not None and disclosure_key is not None:
            disclosure = ContributorDisclosure(snapshot=snapshot, key=disclosure_key, deliver_notice=deliver_notice)

            def bind(request_id: str, input_text: str, output_cap: int) -> RouteBinding | None:
                return disclosure.binding(model_id=route.model_id, request_id=request_id, input_text=input_text, output_cap=output_cap)

        return GatewaySummarizerCall(
            gateway_client=gateway_client,
            model_id=route.model_id,
            session_id=identity.session_id,
            request_ids=request_ids,
            bind=bind,
        )

    return bind_turn
