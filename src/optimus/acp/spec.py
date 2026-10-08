from __future__ import annotations

import asyncio
import contextlib
import inspect
import itertools
import sys
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from context_engine import SummaryCheckpoint
from optimus.acp.conversation import (
    AttachedConversationState,
    ConversationDisposition,
    ConversationOutcome,
    ConversationSanitizer,
    ConversationSanitizerInputs,
    ConversationState,
)
from optimus.acp.debug_trace import acp_debug_log, debug_trace_enabled
from optimus.acp.errors import (
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    REQUEST_CANCELLED,
    AcpOutboundError,
    JsonRpcError,
    error_response,
    success_response,
)
from optimus.acp.lifecycle import (
    NonTurnResponseEnvelope,
    NoticeControl,
    ResponseEnvelope,
    ResponseOwnershipSlot,
    SendKind,
    TurnControl,
    TurnResponseEnvelope,
)
from optimus.acp.session_config import (
    SLIDING_ACTIVE_TEXT,
    STRATEGY_CONFIG_ID,
    STRATEGY_IDS,
    ConfigPublication,
    SessionConfigSnapshot,
    build_session_config_options,
)
from optimus.acp.settlement import (
    ConversationCommit,
    EffectState,
    FinalDelivery,
    RpcResponseDelivery,
    Settlement,
    TurnSettlementSnapshot,
)
from optimus.acp.shapes import (
    AGENT_MODE_ID,
    CHAT_MODE_ID,
    MODE_CONFIG_ID,
    build_agent_message_chunk_notification,
    build_config_option_update_notification,
    build_current_mode_update_notification,
    build_plan_session_update,
    build_planning_progress_notification,
    build_request_permission_params,
    build_session_mode_state,
    build_tool_call_notification,
    build_usage_update,
    new_approval_id,
    new_tool_call_id,
    tool_kind_for_name,
)
from optimus.agent.models import AgentApproval, AgentRunRequest, AgentRunResult, AgentRunStatus
from optimus.agent.planning_loop import PlanningProgressEvent
from optimus.context.adapter import ApprovalFact, approval_fact_from_permission
from optimus.context.assembly import AttachedTurn, ContextAttachment
from optimus.mcp.client_catalog import ClientMcpOneCallApproval
from optimus.mcp.client_config import ClientMcpConfigError
from optimus.mcp.client_disposition import AcpMcpPermissionBroker, ClientMcpRuntime, ClientMcpSessionState
from optimus.runtime.modes import ExecutionMode
from optimus.usage.cost_alerts import AlertPolicy, AlertTracker, CostScopeSummary
from optimus.usage.turn_settlement import TurnCostSummary, TurnSettlement, receipt_from_maintenance

if TYPE_CHECKING:
    from optimus.gateway.route_binding import RoutePolicy, TurnRouteBinder

ACP_PROTOCOL_VERSION = 1

# Plan 12.1: ACP mode IDs <-> the canonical per-session ExecutionMode. Internal
# ExecutionMode.PLAN is deliberately not selectable from ACP.
_MODE_BY_ID: dict[str, ExecutionMode] = {AGENT_MODE_ID: ExecutionMode.AGENT, CHAT_MODE_ID: ExecutionMode.CHAT}
_ID_BY_MODE: dict[ExecutionMode, str] = {mode: mode_id for mode_id, mode in _MODE_BY_ID.items()}
_CONFIG_SETTER_METHODS = frozenset({"session/set_mode", "session/set_config_option"})
_CHAT_CANCELLED_TEXT = "Chat answer cancelled before it was shown."
_CHAT_FAILURE_FALLBACK_TEXT = "Chat could not answer this prompt. Please try again."

CAPACITY_WARNING_TEXT = (
    "Heads-up: this conversation has used about 80% of its context budget. "
    "Please start a new thread soon; once it is full, new prompts in this thread will be refused."
)
"""Sent once, when an admitted prompt or a committed reply first projects the conversation
past 80% of `CONVERSATION_MAX_BYTES` (operator ruling 2026-08-20; Plan 12.2 Task 3)."""

CAPACITY_REFUSAL_TEXT = (
    "This conversation has reached its context limit, so this prompt was refused. "
    "Please start a new thread to continue."
)

CAPACITY_REACHED_TEXT = (
    "This conversation has now reached its context limit. "
    "Please start a new thread to continue; new prompts in this thread will be refused."
)
"""Sent when a committed reply itself fills the conversation, so the user learns of it
before their next prompt is refused."""

# Plan 12.2 Task 9: attached Context Engine notices. Each names its limiting condition and whether the
# thread can continue; none is a content-policy refusal (design spec 8.2, 10).
CONTEXT_FALLBACK_TEXT = (
    "The {strategy} context strategy is unavailable for this prompt. The full conversation history will be "
    "used if it fits the model's request limit."
)
# One fixed message per known engine reason, naming the limit and the recovery that can actually help;
# an unknown reason is never shown verbatim (Codex's final corrections C1, 2026-10-04). The common ending
# speaks only of answer/planning dispatch: summarization attempts may already have run and been charged.
CONTEXT_UNAVAILABLE_ENDING = "This thread stays open. No answer or plan was requested for this prompt."
CONTEXT_UNAVAILABLE_TEXTS: dict[str, str] = {
    "turn exceeds maintenance input": (
        "An earlier turn is too large for {strategy} to summarize with the current limits. Choose Sliding window "
        "to continue with less ordinary conversation history, or start a new thread. Sliding window may omit all "
        "ordinary history if even the newest turn does not fit."
    ),
    "exact authority exceeds history capacity": (
        "The recorded execution outcomes and approval facts exceed this thread's context allowance. Start a new "
        "thread; changing context strategy will not make those required facts smaller."
    ),
    "history capacity too small for a summary": (
        "The {strategy} summary and required history do not fit this thread's context allowance. Choose Sliding "
        "window to continue with less ordinary conversation history, or start a new thread."
    ),
    "maintenance input exceeded": (
        "The {strategy} strategy cannot summarize this history within its input or call limits. Choose Sliding "
        "window to continue with less ordinary conversation history, or start a new thread."
    ),
    "maintenance allowance exceeded": (
        "The {strategy} strategy cannot summarize this history within its input or call limits. Choose Sliding "
        "window to continue with less ordinary conversation history, or start a new thread."
    ),
    "maintenance failed": (
        "The {strategy} summary could not be completed or accepted. Retrying may help and may incur another "
        "summarization charge. You can also choose Sliding window to continue with less ordinary conversation "
        "history."
    ),
    "summary malformed": (
        "The {strategy} summary could not be completed or accepted. Retrying may help and may incur another "
        "summarization charge. You can also choose Sliding window to continue with less ordinary conversation "
        "history."
    ),
    "summary exceeds bound": (
        "The {strategy} summary could not be completed or accepted. Retrying may help and may incur another "
        "summarization charge. You can also choose Sliding window to continue with less ordinary conversation "
        "history."
    ),
    "maintenance unavailable": (
        "Summarization is unavailable with this thread's current model and settings. Choose Sliding window to "
        "continue with less ordinary conversation history, or retry after summarization becomes available."
    ),
    "source exceeds limit": "The stored conversation exceeds the context engine's source limit. Start a new thread.",
}
CONTEXT_UNAVAILABLE_UNKNOWN_TEXT = (
    "The {strategy} context strategy could not prepare this conversation. You can try Sliding window with less "
    "ordinary conversation history, or start a new thread."
)
CONTEXT_RESERVATION_TEXT = (
    "This prompt would not leave enough room in this conversation's storage for a reply, so nothing was "
    "sent to the model. This thread stays open: a shorter prompt may fit."
)
CONTEXT_PLAN_TOO_LARGE_TEXT = (
    "The plan is too large to keep in this conversation's history, so it was not offered for approval "
    "and nothing was changed. Ask for a smaller change."
)
_CONTEXT_CANCELLED_TEXT = "Cancelled before the model was asked."
# An attached session's storage limit is not the model's context, so its notices name storage
# (design spec 8.4, 10). Engine-absent sessions keep the texts above.
ATTACHED_STORAGE_WARNING_TEXT = (
    "Heads-up: this conversation has used about 80% of its storage limit. "
    "Please start a new thread soon; once its storage is full, new prompts in this thread will be refused."
)
ATTACHED_STORAGE_REFUSAL_TEXT = (
    "This conversation's storage is full, so this prompt was refused. Please start a new thread to continue."
)
ATTACHED_STORAGE_REACHED_TEXT = (
    "This conversation's storage is now full. "
    "Please start a new thread to continue; new prompts in this thread will be refused."
)
# Release supplement V1 (D7 request-capacity exception): with a trusted route policy and no engine, the
# 80% storage notice names storage and says a model request can be refused sooner; the request meter and
# its separate 80% warning read the complete request the Gateway's final guard admits. Neither promises a
# number of future turns. Without a route policy (today's inactive enforcement) the texts above are kept.
ABSENT_STORAGE_WARNING_TEXT = (
    "Heads-up: this conversation has used about 80% of its storage limit. Please start a new thread soon; "
    "once its storage is full, new prompts in this thread will be refused. A model request can be refused "
    "sooner, when it exceeds the model's input capacity."
)
REQUEST_CAPACITY_WARNING_TEXT = (
    "Heads-up: this prompt's model request used 80% or more of the model's input capacity. A later request "
    "that exceeds that capacity will be refused. A shorter prompt or a narrower request involving fewer "
    "workspace files may help; if earlier conversation history is the cause, start a new thread."
)
REQUEST_WARNING_FRACTION = 0.8
_NOTICE_FLUSH_TIMEOUT_SECONDS = 30.0
_STRATEGY_LABELS = {"compaction": "compaction", "hybrid": "hybrid", "sliding_window": "sliding window"}


def context_unavailable_text(reason: str | None, strategy: str) -> str:
    """The refusal for an attached view that could not be built and a full history over the floor:
    the fixed message for a known engine reason, the generic one otherwise, then the common ending."""
    message = CONTEXT_UNAVAILABLE_TEXTS.get(reason or "", CONTEXT_UNAVAILABLE_UNKNOWN_TEXT)
    return f"{message.format(strategy=strategy)} {CONTEXT_UNAVAILABLE_ENDING}"


def resolve_max_planning_turns(environ: Mapping[str, str]) -> int | None:
    """Operator-only testing override for AgentRunRequest.max_planning_turns.

    Not part of the ACP wire contract: session/prompt has no client-facing field
    for this, so live evidence gathering (Plan 9.85 Task 8) sets this env var on
    the agent process itself to force turn-limit scenarios.

    Plan 9.96, Task 5 Step 2: takes an explicit ``environ`` mapping rather than
    reading ``os.environ`` implicitly. Callers resolve this exactly once
    (typically alongside launch authorization, before the ACP server starts
    serving requests) and thread the typed result through
    AcpDuplexAdapter/JsonRpcDispatcher/AcpStreamServer — no per-request or
    per-call-site ambient environment read.
    """
    raw = environ.get("OPTIMUS_MAX_PLANNING_TURNS")
    if raw is None or raw.strip() == "":
        return None
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ValueError("OPTIMUS_MAX_PLANNING_TURNS must be an integer >= 1") from exc
    if value < 1:
        raise ValueError("OPTIMUS_MAX_PLANNING_TURNS must be an integer >= 1")
    return value


class AcpOutboundChannel(Protocol):
    async def notify(self, method: str, params: dict[str, Any], *, require_flushed: bool = False) -> None:
        """Send a notification. With ``require_flushed``, anything short of a confirmed flush raises."""
        ...

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        ...

    def cancel_request(self, request_id: str | int, result: dict[str, Any]) -> None:
        ...


@dataclass
class AcpSpecSession:
    session_id: str
    cwd: Path
    execution_mode: ExecutionMode = ExecutionMode.AGENT
    client_mcp_state: ClientMcpSessionState | None = None
    conversation: ConversationState | None = None
    # Plan 12.1 / 12.2 Task 10: serializes every config setter for this session; prompts never take it.
    config_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)
    # The one publication state every setter shares: what is committed but not yet confirmed.
    config_publication: ConfigPublication = field(default_factory=ConfigPublication, repr=False, compare=False)
    # Plan 12.2 Task 10: set by a committed switch to sliding, cleared by its confirmed notice or a switch away.
    sliding_notice_pending: bool = False
    # Release supplement V1: set once the 80% request-capacity warning is confirmed delivered.
    request_warning_sent: bool = False
    # Plan 12.2 Task 9, attached sessions only: the strategy the next turn captures, the published
    # summary checkpoint and the host's exact approval facts per turn. None/empty when absent.
    context_strategy: str | None = None
    context_checkpoint: SummaryCheckpoint | None = None
    context_approvals: dict[int, tuple[ApprovalFact, ...]] = field(default_factory=dict, repr=False, compare=False)
    # Plan 12.2 Task 11: every model attempt of this session, settled exactly once, and the cost
    # alert crossings already reported.
    cost_settlement: TurnSettlement = field(default_factory=TurnSettlement, repr=False, compare=False)
    alert_tracker: AlertTracker = field(default_factory=AlertTracker, repr=False, compare=False)

    def __post_init__(self) -> None:
        # The conversation's cost is one projection over this session's receipts, updated whenever a
        # receipt arrives - including after a turn's terminal finalization (Codex CP3 ruling R2).
        self.cost_settlement.subscribe(self._project_turn_cost)

    def _project_turn_cost(self, turn_id: str, summary: TurnCostSummary) -> None:
        if self.conversation is not None:
            self.conversation.project_turn_cost(turn_id, known_usd=summary.known_subtotal_usd, complete=summary.complete)


@dataclass
class AcpPromptTurn:
    session_id: str
    turn_seq: int
    turn_control: TurnControl
    # Captured at admission; the turn never re-reads the session's mode (Plan 12.1).
    execution_mode: ExecutionMode = ExecutionMode.AGENT
    pending_permission_request_id: str | int | None = None
    permission_tool_call_id: str | None = None
    permission_handle: Any | None = None
    # Plan 12.2: an attached turn's captured context, its packer and its dispatch readings.
    attached: AttachedTurn | None = None
    # Codex CP3 ruling R4: the turn's request binder for the trusted planning/answer route, captured
    # before any await. None while no route policy is configured (registry enforcement inactive).
    route_binder: TurnRouteBinder | None = None

    @property
    def run_id(self) -> str:
        return f"{self.session_id}:{self.turn_seq}"


class InMemoryAcpSpecSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, AcpSpecSession] = {}
        self._closed_state_ids: set[str] = set()

    def create(self, *, cwd: Path, conversation: ConversationState | None = None) -> AcpSpecSession:
        session = AcpSpecSession(
            session_id=f"session-{uuid.uuid4().hex}",
            cwd=cwd.resolve(),
            conversation=conversation,
        )
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> AcpSpecSession | None:
        return self._sessions.get(session_id)

    def remove(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session is not None and session.client_mcp_state is not None:
            self._close_state_once(session)

    def close_all(self) -> None:
        for session in list(self._sessions.values()):
            self._close_state_once(session)

    def _close_state_once(self, session: AcpSpecSession) -> None:
        state = session.client_mcp_state
        if state is None:
            return
        if session.session_id in self._closed_state_ids:
            return
        self._closed_state_ids.add(session.session_id)
        state.close()


class RecordingOutboundChannel:
    """
    Represents an outbound channel used for recording JSON-RPC notifications and
    requests, as well as handling responses and cancellations.

    This class facilitates the sending and recording of JSON-RPC notifications and
    requests, the retrieval of specific requests based on their method, and the
    management of responses and cancellations for active requests. Its purpose is
    to provide a structured mechanism to log, retrieve, and handle JSON-RPC
    communications in an asynchronous context.

    :ivar notifications: List of recorded JSON-RPC notification messages.
    :type notifications: list[dict[str, Any]]
    :ivar requests: List of recorded JSON-RPC request messages.
    :type requests: list[dict[str, Any]]
    """
    def __init__(self) -> None:
        self.notifications: list[dict[str, Any]] = []
        self.requests: list[dict[str, Any]] = []
        self._request_ids = itertools.count(1)
        self._request_event = asyncio.Event()
        self._futures: dict[str | int, asyncio.Future[dict[str, Any]]] = {}

    async def notify(self, method: str, params: dict[str, Any], *, require_flushed: bool = False) -> None:
        del require_flushed  # a recorded notification is always delivered
        self.notifications.append({"jsonrpc": "2.0", "method": method, "params": params})

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = f"agent-{next(self._request_ids)}"
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._futures[request_id] = future
        self.requests.append({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        self._request_event.set()
        return await future

    async def wait_for_request(self, method: str) -> dict[str, Any]:
        while True:
            for request in self.requests:
                if request["method"] == method:
                    return request
            self._request_event.clear()
            await self._request_event.wait()

    def respond(self, request_id: str | int, result: dict[str, Any]) -> None:
        future = self._futures.get(request_id)
        if future is not None and not future.done():
            future.set_result(result)

    def cancel_request(self, request_id: str | int, result: dict[str, Any]) -> None:
        self.respond(request_id, result)


class AcpDuplexAdapter:
    """
    Handles duplex communication and request-response mechanism for the ACP framework.

    The AcpDuplexAdapter class is responsible for managing requests and notifications
    from clients and coordinating sessions within the ACP framework. It provides
    mechanisms for handling various JSON-RPC 2.0 methods such as initializing the
    agent, creating new sessions, and managing session prompts. Additionally, it
    supports asynchronous processing and error handling for robust communication.

    :ivar runner: Executes tasks and runs planning processes.
    :type runner: Any
    :ivar workspace_root: Path to the root directory for workspace-related operations.
    :type workspace_root: str or Path
    :ivar sessions: In-memory storage for session specifications.
    :type sessions: InMemoryAcpSpecSessionStore
    :ivar outbound: Channel for managing outbound requests and notifications.
    :type outbound: AcpOutboundChannel
    """
    def __init__(
        self,
        *,
        runner: Any,
        workspace_root: str | Path,
        sessions: InMemoryAcpSpecSessionStore,
        outbound: AcpOutboundChannel,
        max_planning_turns: int | None = None,
        client_mcp_runtime: ClientMcpRuntime | None = None,
        sanitizer_inputs: ConversationSanitizerInputs | None = None,
        notice_control: NoticeControl | None = None,
        settlement_sink: Any | None = None,
        context_attachment: ContextAttachment | None = None,
        alert_policies: tuple[AlertPolicy, ...] = (),
        route_policy: RoutePolicy | None = None,
    ) -> None:
        self._runner = runner
        self._workspace_root = Path(workspace_root).resolve()
        self._sessions = sessions
        self._outbound = outbound
        self._active_turns: dict[str, AcpPromptTurn] = {}
        # Plan 9.96, Task 5 Step 2: resolved once by the caller (typically via
        # resolve_max_planning_turns(authorized_launch.candidate.agent_environ))
        # and threaded in here, rather than read from os.environ per prompt.
        self._max_planning_turns = max_planning_turns
        self._client_mcp_runtime = client_mcp_runtime
        self._sanitizer_inputs = sanitizer_inputs or ConversationSanitizerInputs(
            known_secrets=(),
            path_aliases=(),
            known_pii=(),
        )
        self._notice_control = notice_control
        self._settlement_sink = settlement_sink
        # Plan 12.2 Task 9: fixes every new session's storage class. None keeps the engine-absent floor.
        self._context_attachment = context_attachment
        # Plan 12.2 Task 11: operator-configured cost alerts (turn and session scopes); none by default,
        # and no amount is invented. A daily scope needs a reconciled durable ledger, which this host
        # does not have: such a policy is refused here, never counted per process or silently dropped.
        if any(policy.scope == "day" for policy in alert_policies):
            raise ValueError("daily cost alerts need a reconciled durable ledger (P9.85-FU-3); this host has none")
        self._alert_policies = tuple(alert_policies)
        # Codex CP3 ruling R4: the injected trusted planning/answer route policy. None keeps today's
        # unbound requests; nothing attaches one at startup (activation hold).
        self._route_policy = route_policy
        self._closed = False

    def _remove_active_turn(self, session_id: str, turn_seq: int, control: TurnControl) -> bool:
        current = self._active_turns.get(session_id)
        if current is None:
            return False
        if current.turn_seq != turn_seq or current.turn_control is not control:
            return False
        del self._active_turns[session_id]
        return True

    def _non_turn(
        self,
        response: dict[str, Any],
        ownership_slot: ResponseOwnershipSlot | None = None,
    ) -> NonTurnResponseEnvelope:
        return NonTurnResponseEnvelope(response=response, ownership_slot=ownership_slot)

    def _turn(
        self,
        response: dict[str, Any],
        turn_control: TurnControl,
        ownership_slot: ResponseOwnershipSlot | None = None,
    ) -> TurnResponseEnvelope:
        return TurnResponseEnvelope(
            response=response,
            turn_control=turn_control,
            ownership_slot=ownership_slot,
        )

    def _new_conversation(self) -> ConversationState:
        sanitizer = ConversationSanitizer(self._sanitizer_inputs)
        attachment = self._context_attachment
        if attachment is None:
            return ConversationState(sanitizer)
        return AttachedConversationState(
            sanitizer,
            source_max_bytes=attachment.source_max_bytes,
            record_reservation_bytes=attachment.record_reservation_bytes,
        )

    def _planner_inputs(
        self,
        conversation: ConversationState,
        sanitized_prompt: str,
        mode: ExecutionMode,
    ) -> tuple[str, str]:
        """The single history source for both ACP modes: returns ``(task, conversation_envelope)``.

        Agent keeps receiving the envelope inside ``task``. Chat (Plan 12.1 /
        P11.25-FU-1) receives the same envelope separately, with ``task`` holding
        only the current prompt.
        """
        envelope = conversation.planner_envelope() if conversation.records else ""
        if mode is ExecutionMode.CHAT:
            return sanitized_prompt, envelope
        return (f"{envelope}\n{sanitized_prompt}" if envelope else sanitized_prompt), ""

    def _placeholder_settlement(self, turn: AcpPromptTurn) -> TurnSettlementSnapshot:
        fields = turn.turn_control.current_settlement_fields()
        settlement = (
            Settlement.TRANSPORT_ABANDONED
            if fields["post_teardown"]
            else Settlement.COMPLETED
        )
        return TurnSettlementSnapshot(
            settlement=settlement,
            final_delivery=FinalDelivery(fields["final_delivery"]),
            rpc_response_delivery=RpcResponseDelivery(fields["rpc_response_delivery"]),
            conversation_commit=ConversationCommit.NOT_COMMITTED,
            effect_state=EffectState(fields["effect_state"]),
            cost_complete=bool(fields["cost_complete"]),
        )

    def _settlement_evidence_callback(self, turn: AcpPromptTurn):
        def _callback(outcome: TurnSettlementSnapshot) -> None:
            from datetime import UTC, datetime

            from optimus.telemetry.events import TelemetryEvent
            from optimus.telemetry.fanout import emit_acp_turn_settlement_contained

            fields = turn.turn_control.current_settlement_fields()
            phase = (
                "transport_abandoned"
                if fields["post_teardown"]
                else "completed"
            )
            event = TelemetryEvent.acp_turn_settlement(
                run_id=turn.run_id,
                session_id=turn.session_id,
                request_id=f"{turn.run_id}:settlement",
                occurred_at=datetime.now(tz=UTC),
                turn_seq=turn.turn_seq,
                interruption_phase=phase,
                settlement=outcome.settlement.value,
                final_delivery=outcome.final_delivery.value,
                rpc_response_delivery=outcome.rpc_response_delivery.value,
                conversation_commit=outcome.conversation_commit.value,
                effect_state=outcome.effect_state.value,
                provider_attempt_started=bool(fields["provider_attempt_started"]),
                cost_complete=outcome.cost_complete,
                prior_history_flush=bool(fields["prior_history_flush"]),
                post_teardown=bool(fields["post_teardown"]),
            )
            emit_acp_turn_settlement_contained(self._settlement_sink, event)

        return _callback

    async def handle_client_request(
        self,
        request: dict[str, Any],
        ownership_slot: ResponseOwnershipSlot | None = None,
    ) -> ResponseEnvelope:
        request_id = request.get("id")
        if request.get("jsonrpc") != "2.0" or "method" not in request:
            return self._non_turn(
                error_response(request_id, JsonRpcError(code=INVALID_REQUEST, message="invalid request")),
                ownership_slot,
            )

        method = request["method"]
        if method == "initialize":
            return self._non_turn(self._handle_initialize(request), ownership_slot)
        if method == "session/new":
            return self._non_turn(await self._handle_session_new(request), ownership_slot)
        if method == "session/prompt":
            return await self._handle_session_prompt(request, ownership_slot=ownership_slot)
        if method in _CONFIG_SETTER_METHODS:
            return self._non_turn(await self._handle_config_change(request, method=method), ownership_slot)
        if method in {"session/update", "session/request_permission"}:
            return self._non_turn(
                error_response(request_id, JsonRpcError(code=METHOD_NOT_FOUND, message=f"method not found: {method}")),
                ownership_slot,
            )
        return self._non_turn(
            error_response(request_id, JsonRpcError(code=METHOD_NOT_FOUND, message=f"method not found: {method}")),
            ownership_slot,
        )

    def close_all(self) -> None:
        """Cancel outstanding ACP permission work, then close session states exactly once."""
        if self._closed:
            return
        self._closed = True
        for turn in list(self._active_turns.values()):
            turn.turn_control.request_session_cancel()
            if turn.permission_handle is not None:
                turn.permission_handle.cancel()
            elif turn.pending_permission_request_id is not None:
                self._outbound.cancel_request(
                    turn.pending_permission_request_id,
                    {"outcome": {"outcome": "cancelled"}},
                )
                turn.pending_permission_request_id = None
        self._sessions.close_all()

    async def handle_client_notification(self, notification: dict[str, Any]) -> None:
        if notification.get("method") != "session/cancel":
            return
        # region agent log
        acp_debug_log(
            location="spec.py:handle_client_notification:session_cancel",
            message="session/cancel notification received",
            data=lambda: {"session_id": notification.get("params", {}).get("sessionId") if isinstance(notification.get("params"), dict) else None},
            hypothesis_id="H1",
        )
        # endregion
        params = notification.get("params")
        if not isinstance(params, dict):
            return
        session_id = params.get("sessionId")
        if not isinstance(session_id, str):
            return
        turn = self._active_turns.get(session_id)
        if turn is None:
            return
        turn.turn_control.request_session_cancel()
        if turn.permission_handle is not None:
            turn.permission_handle.cancel()
        elif turn.pending_permission_request_id is not None:
            self._outbound.cancel_request(turn.pending_permission_request_id, {"outcome": {"outcome": "cancelled"}})

    def _handle_initialize(self, request: dict[str, Any]) -> dict[str, Any]:
        params = request.get("params")
        if not isinstance(params, dict) or not isinstance(params.get("protocolVersion"), int):
            return error_response(request.get("id"), JsonRpcError(code=INVALID_REQUEST, message="invalid request"))
        agent_capabilities: dict[str, Any] = {
            "promptCapabilities": {
                "image": False,
                "audio": False,
                "embeddedContext": False,
            },
            # session/load remains P11-FEAT-ZED-RESUME; do not advertise loadSession.
            "sessionCapabilities": {},
        }
        # Advertise HTTP/SSE only after adapters + gates are proven (Task 8).
        http_enabled = bool(self._client_mcp_runtime and self._client_mcp_runtime.mcp_http_enabled)
        sse_enabled = bool(self._client_mcp_runtime and self._client_mcp_runtime.mcp_sse_enabled)
        agent_capabilities["mcpCapabilities"] = {"http": http_enabled, "sse": sse_enabled}
        return success_response(
            request_id=request.get("id"),
            result={
                "protocolVersion": ACP_PROTOCOL_VERSION,
                "agentCapabilities": agent_capabilities,
                "agentInfo": {"name": "optimus", "version": "0.1.0"},
                "authMethods": [],
            },
        )

    def _session_new_result(self, session: AcpSpecSession) -> dict[str, Any]:
        mode_id = _ID_BY_MODE[session.execution_mode]
        return {
            "sessionId": session.session_id,
            "modes": build_session_mode_state(current_mode_id=mode_id),
            "configOptions": build_session_config_options(self._config_snapshot(session)),
        }

    @staticmethod
    def _config_snapshot(session: AcpSpecSession) -> SessionConfigSnapshot:
        """Every advertised selector's current value (Plan 12.2 Task 10)."""
        return SessionConfigSnapshot(mode_id=_ID_BY_MODE[session.execution_mode], strategy=session.context_strategy)

    async def _handle_config_change(self, request: dict[str, Any], *, method: str) -> dict[str, Any]:
        """One validation-and-update path for ``session/set_mode`` and ``session/set_config_option``.

        Answered without waiting for an in-flight turn: an admitted turn keeps the settings it
        captured, so a change only affects the next prompt. The context strategy is settable only on
        an attached session; elsewhere it is an unknown option and can never attach the engine.
        Invalid requests leave every value and every projection untouched.
        """
        request_id = request.get("id")

        def invalid(message: str) -> dict[str, Any]:
            return error_response(request_id, JsonRpcError(code=INVALID_REQUEST, message=message))

        params = request.get("params")
        if not isinstance(params, dict) or not isinstance(params.get("sessionId"), str):
            return invalid("invalid request")
        mode: ExecutionMode | None = None
        strategy: str | None = None
        if method == "session/set_mode":
            mode_id = params.get("modeId")
            if not isinstance(mode_id, str) or mode_id not in _MODE_BY_ID:
                return invalid("unsupported mode")
            mode = _MODE_BY_ID[mode_id]
        else:
            config_id = params.get("configId")
            if not isinstance(config_id, str):
                return invalid("invalid request")
            if config_id == MODE_CONFIG_ID:
                if params.get("type") == "boolean":
                    return invalid("config option value type mismatch")
                mode_id = params.get("value")
                if not isinstance(mode_id, str) or mode_id not in _MODE_BY_ID:
                    return invalid("unsupported mode")
                mode = _MODE_BY_ID[mode_id]
            elif config_id == STRATEGY_CONFIG_ID and self._context_attachment is not None:
                if params.get("type") == "boolean":
                    return invalid("config option value type mismatch")
                strategy = params.get("value")
                if not isinstance(strategy, str) or strategy not in STRATEGY_IDS:
                    return invalid("unsupported context strategy")
            else:
                return invalid("unknown config option")
        session = self._sessions.get(params["sessionId"])
        if session is None:
            return invalid("unknown session")

        # Serialized per session: the state change, its updates and the response value belong to
        # this request alone. The prompt path never takes this lock, so no turn is held up, and no
        # setter ever waits for a model call or a permission answer.
        async with session.config_lock:
            await self._apply_session_config(session, mode=mode, strategy=strategy)
            if method == "session/set_mode":
                return success_response(request_id=request_id, result={})
            return success_response(
                request_id=request_id,
                result={"configOptions": build_session_config_options(self._config_snapshot(session))},
            )

    async def _apply_session_config(
        self, session: AcpSpecSession, *, mode: ExecutionMode | None, strategy: str | None
    ) -> None:
        """Commit any change once, then publish what is pending. Caller holds ``session.config_lock``.

        A mode change pends ``current_mode_update`` and the full set; a strategy-only change pends only
        the full set, so it never announces a mode change. Each update must be confirmed as flushed.
        If one fails, is ambiguous or is suppressed, the change stays committed and pending, and the
        next setter republishes the whole current set even when it repeats a value.
        """
        publication = session.config_publication
        mode_changed = mode is not None and session.execution_mode is not mode
        strategy_changed = strategy is not None and session.context_strategy != strategy
        if mode_changed:
            assert mode is not None
            session.execution_mode = mode
        if strategy_changed:
            session.context_strategy = strategy
            # A switch to sliding owes the next admitted turn its notice; switching away cancels it.
            session.sliding_notice_pending = strategy == "sliding_window"
        if mode_changed or strategy_changed:
            publication.commit(mode_changed=mode_changed)
        pending = publication.pending_updates()
        if not pending:
            return
        revision = publication.revision
        snapshot = self._config_snapshot(session)
        if "current_mode_update" in pending:
            await self._outbound.notify(
                "session/update",
                build_current_mode_update_notification(session_id=session.session_id, current_mode_id=snapshot.mode_id),
                require_flushed=True,
            )
        await self._outbound.notify(
            "session/update",
            build_config_option_update_notification(
                session_id=session.session_id, config_options=build_session_config_options(snapshot)
            ),
            require_flushed=True,
        )
        publication.confirmed(revision)

    async def _handle_session_new(self, request: dict[str, Any]) -> dict[str, Any]:
        params = request.get("params")
        if not isinstance(params, dict) or not isinstance(params.get("cwd"), str):
            return error_response(request.get("id"), JsonRpcError(code=INVALID_REQUEST, message="invalid request"))
        cwd = Path(params["cwd"]).resolve()
        if not cwd.is_relative_to(self._workspace_root):
            return error_response(
                request.get("id"),
                JsonRpcError(code=INVALID_REQUEST, message="session cwd outside configured workspace"),
            )
        mcp_servers = params.get("mcpServers", [])
        if mcp_servers is None:
            mcp_servers = []
        if not isinstance(mcp_servers, list):
            return error_response(request.get("id"), JsonRpcError(code=INVALID_REQUEST, message="invalid request"))

        # Provisional in-memory session after input-shape validation.
        session = self._sessions.create(cwd=cwd, conversation=self._new_conversation())
        if self._context_attachment is not None:
            session.context_strategy = self._context_attachment.initial_strategy
            session.sliding_notice_pending = session.context_strategy == "sliding_window"
        empty_state = ClientMcpSessionState(session_id=session.session_id)
        session.client_mcp_state = empty_state

        if len(mcp_servers) == 0:
            return success_response(request_id=request.get("id"), result=self._session_new_result(session))

        runtime = self._client_mcp_runtime
        if runtime is None:
            self._sessions.remove(session.session_id)
            return error_response(
                request.get("id"),
                JsonRpcError(code=INVALID_REQUEST, message="client MCP runtime not configured"),
            )

        state: ClientMcpSessionState | None = None
        try:
            async def request_permission(permission_params: dict[str, Any]) -> dict[str, Any]:
                return await self._outbound.request("session/request_permission", permission_params)

            state = await runtime.disposition.disposition_for_new_session(
                session.session_id,
                cwd,
                mcp_servers,
                request_permission,
            )
            runtime.disposition.attach_runtime_resolver(
                state,
                sdk_adapter=runtime.sdk_adapter,
            )
        except ClientMcpConfigError:
            if state is not None:
                state.close()
            self._sessions.remove(session.session_id)
            return error_response(request.get("id"), JsonRpcError(code=INVALID_REQUEST, message="invalid request"))
        except Exception:
            if state is not None:
                state.close()
            self._sessions.remove(session.session_id)
            return error_response(request.get("id"), JsonRpcError(code=INVALID_REQUEST, message="invalid request"))

        assert state is not None
        session.client_mcp_state = state
        return success_response(request_id=request.get("id"), result=self._session_new_result(session))

    async def _handle_session_prompt(
        self,
        request: dict[str, Any],
        *,
        ownership_slot: ResponseOwnershipSlot | None = None,
    ) -> ResponseEnvelope:
        params = request.get("params")
        if not isinstance(params, dict):
            return self._non_turn(
                error_response(request.get("id"), JsonRpcError(code=INVALID_REQUEST, message="invalid request")),
                ownership_slot,
            )
        session_id = params.get("sessionId")
        prompt = params.get("prompt")
        if not isinstance(session_id, str) or not isinstance(prompt, list):
            return self._non_turn(
                error_response(request.get("id"), JsonRpcError(code=INVALID_REQUEST, message="invalid request")),
                ownership_slot,
            )
        session = self._sessions.get(session_id)
        if session is None:
            return self._non_turn(
                error_response(request.get("id"), JsonRpcError(code=INVALID_REQUEST, message="unknown session")),
                ownership_slot,
            )
        task = _text_from_content_blocks(prompt)
        if not task:
            return self._non_turn(
                error_response(request.get("id"), JsonRpcError(code=INVALID_REQUEST, message="empty prompt")),
                ownership_slot,
            )

        if session_id in self._active_turns:
            return self._non_turn(
                error_response(
                    request.get("id"),
                    JsonRpcError(code=REQUEST_CANCELLED, message="a turn is already in progress"),
                ),
                ownership_slot,
            )

        conversation = session.conversation
        if conversation is None:
            conversation = self._new_conversation()
            session.conversation = conversation

        admission = conversation.prepare_admission(task)
        if not admission.admitted:
            return await self._refuse_prompt(
                request_id=request.get("id"),
                session_id=session_id,
                conversation=conversation,
                reason=admission.refuse_reason or "refused",
                ownership_slot=ownership_slot,
            )

        assert admission.turn_seq is not None
        turn_seq = conversation.allocate_turn_seq()
        if turn_seq != admission.turn_seq:
            # allocate must match the admission probe; invariant otherwise.
            turn_seq = admission.turn_seq
            conversation._next_turn_seq = turn_seq + 1  # noqa: SLF001

        turn_control = TurnControl(session_id=session_id, turn_seq=turn_seq)
        turn = AcpPromptTurn(
            session_id=session_id,
            turn_seq=turn_seq,
            turn_control=turn_control,
            execution_mode=session.execution_mode,
        )
        turn_control.set_finalization_hooks(
            active_map_remover=self._remove_active_turn,
            settlement_callback=self._settlement_evidence_callback(turn),
        )
        if ownership_slot is not None:
            ownership_slot.bind_turn(turn_control)
        self._active_turns[session_id] = turn
        run_id = turn.run_id
        # region agent log
        acp_debug_log(
            location="spec.py:_handle_session_prompt:entry",
            message="session/prompt started",
            data=lambda: {"session_id": session_id, "request_id": request.get("id"), "run_id": run_id, "turn_seq": turn_seq},
            hypothesis_id="H1",
        )
        # endregion
        # Plan 12.2 Task 9: an attached turn captures its history, strategy and checkpoint now,
        # before any await a setter could interleave with.
        attached_turn = (
            AttachedTurn.capture(
                attachment=self._context_attachment,
                session_key=session_id,
                records=conversation.records,
                approvals=session.context_approvals,
                generation=conversation.generation,
                sanitizer=conversation.sanitizer,
                strategy=session.context_strategy or self._context_attachment.initial_strategy,
                mode=turn.execution_mode,
                checkpoint=session.context_checkpoint,
                current_prompt=admission.sanitized_user_prompt,
                turn_seq=turn_seq,
                cancelled=turn.turn_control.halt_requested,
                deliver_notice=self._blocking_notice(session_id, asyncio.get_running_loop()),
                record_receipt=lambda receipt: session.cost_settlement.record_attempt(receipt_from_maintenance(receipt)),
                record_integrity_failure=lambda receipt: session.cost_settlement.record_integrity_failure(
                    receipt_from_maintenance(receipt).turn_id
                ),
            )
            if self._context_attachment is not None
            else None
        )
        turn.attached = attached_turn
        if self._route_policy is not None:
            turn.route_binder = self._route_policy.capture(
                session_id=session_id, turn_seq=turn_seq, deliver_notice=self._blocking_notice(session_id, asyncio.get_running_loop())
            )
        try:
            if admission.crosses_warning and conversation.note_warning_threshold_for_attempt(
                admission.projected_bytes
            ):
                await self._emit_capacity_notice(
                    session_id=session_id, conversation=conversation, text=self._warning_text(), is_warning=True
                )
            if attached_turn is not None and attached_turn.strategy == "sliding_window" and session.sliding_notice_pending:
                await self._emit_sliding_notice(session)

            if attached_turn is None:
                planner_task, conversation_envelope = self._planner_inputs(
                    conversation, admission.sanitized_user_prompt, turn.execution_mode
                )
                planning_fields: dict[str, object] = {
                    "run_id": run_id,
                    "session_id": session_id,
                    "task": planner_task,
                    "execution_mode": turn.execution_mode,
                    "workspace_root": session.cwd,
                    "conversation_envelope": conversation_envelope,
                }
            else:
                stopped = await self._prepare_attached_context(
                    request_id=request.get("id"),
                    session=session,
                    conversation=conversation,
                    turn=turn,
                    attached_turn=attached_turn,
                    sanitized_user_prompt=admission.sanitized_user_prompt,
                    ownership_slot=ownership_slot,
                )
                if stopped is not None:
                    return stopped
                admitted = attached_turn.admitted
                assert admitted is not None
                planning_fields = {
                    "run_id": run_id,
                    "session_id": session_id,
                    "task": admitted.current_prompt,
                    "execution_mode": turn.execution_mode,
                    "workspace_root": session.cwd,
                    "conversation_envelope": admitted.conversation_envelope,
                    "selection_text": admitted.selection_text,
                    "context_digest": admitted.digest,
                }
            if self._max_planning_turns is not None:
                planning_fields["max_planning_turns"] = self._max_planning_turns
            planning_request = AgentRunRequest(**planning_fields)
            loop = asyncio.get_running_loop()
            default_observer = (
                self._runner._planning_progress_observer
                if hasattr(self._runner, "_planning_progress_observer")
                else None
            )

            def _session_progress_observer(event: PlanningProgressEvent) -> None:
                if default_observer is not None:
                    default_observer(event)
                asyncio.run_coroutine_threadsafe(
                    self._emit_planning_progress(session_id=session_id, event=event, turn=turn),
                    loop,
                )

            planning_result = await self._in_worker(
                session,
                turn,
                self._runner.run,
                planning_request,
                **self._runner_runtime_kwargs(
                    planning_progress_observer=_session_progress_observer,
                    session=session,
                    halt_requested=turn.turn_control.halt_requested,
                    operation_control=turn.turn_control,
                    context_packer=attached_turn,
                    stage_receipts=session.cost_settlement.record_attempt,
                    route_binder=turn.route_binder,
                    integrity_failure=session.cost_settlement.record_integrity_failure,
                ),
            )
            self._apply_turn_cost(
                session,
                turn,
                planning_cost=planning_result.total_cost_usd,
                planning_complete=planning_result.cost_complete,
            )
            # region agent log
            acp_debug_log(
                location="spec.py:_handle_session_prompt:planning_done",
                message="planning completed",
                data=lambda: {
                    "run_id": run_id,
                    "status": planning_result.status.value,
                    "plan_hash": planning_result.plan_hash,
                    "read_tool_calls": sum(1 for call in planning_result.tool_calls if call.tool_name == "file_reader"),
                },
                hypothesis_id="H3",
            )
            # endregion
            if turn.execution_mode is ExecutionMode.CHAT:
                return await self._finish_chat_turn(
                    request_id=request.get("id"),
                    session_id=session_id,
                    conversation=conversation,
                    turn=turn,
                    sanitized_user_prompt=admission.sanitized_user_prompt,
                    result=planning_result,
                    ownership_slot=ownership_slot,
                )
            if (
                attached_turn is not None
                and planning_result.status is AgentRunStatus.AWAITING_APPROVAL
                and not self._plan_record_fits(
                    conversation, turn_seq, admission.sanitized_user_prompt, planning_result.candidate_plan_text or ""
                )
            ):
                # Design spec 4.2: a plan the attached record cannot keep fails before approval or any
                # effect, and its exact failed outcome is kept instead of the plan.
                await self._emit_final_text(session_id=session_id, text=CONTEXT_PLAN_TOO_LARGE_TEXT, turn=turn)
                await self._commit_turn(
                    conversation=conversation,
                    turn=turn,
                    sanitized_user_prompt=admission.sanitized_user_prompt,
                    result=planning_result.model_copy(update={"candidate_plan_text": None}),
                    outcome=ConversationOutcome.FAILED,
                    completion_text=CONTEXT_PLAN_TOO_LARGE_TEXT,
                )
                return self._turn(
                    success_response(request_id=request.get("id"), result={"stopReason": "end_turn"}),
                    turn_control,
                    ownership_slot,
                )
            await self._emit_result_updates(session_id=session_id, result=planning_result, planning=True, turn=turn)
            if turn.turn_control.halt_requested():
                await self._commit_turn(
                    conversation=conversation,
                    turn=turn,
                    sanitized_user_prompt=admission.sanitized_user_prompt,
                    result=planning_result,
                    outcome=ConversationOutcome.CANCELLED,
                )
                return self._turn(
                    success_response(request_id=request.get("id"), result={"stopReason": "cancelled"}),
                    turn_control,
                    ownership_slot,
                )
            if planning_result.status is not AgentRunStatus.AWAITING_APPROVAL:
                await self._emit_completion_message(session_id=session_id, result=planning_result, turn=turn)
                await self._commit_turn(
                    conversation=conversation,
                    turn=turn,
                    sanitized_user_prompt=admission.sanitized_user_prompt,
                    result=planning_result,
                    outcome=_conversation_outcome(planning_result),
                )
                return self._turn(
                    success_response(request_id=request.get("id"), result={"stopReason": _stop_reason(planning_result)}),
                    turn_control,
                    ownership_slot,
                )

            if not planning_result.plan_hash:
                await self._emit_completion_message(session_id=session_id, result=planning_result, turn=turn)
                await self._commit_turn(
                    conversation=conversation,
                    turn=turn,
                    sanitized_user_prompt=admission.sanitized_user_prompt,
                    result=planning_result,
                    outcome=_conversation_outcome(planning_result),
                )
                return self._turn(
                    success_response(request_id=request.get("id"), result={"stopReason": _stop_reason(planning_result)}),
                    turn_control,
                    ownership_slot,
                )

            permission_result = await self._request_permission(turn=turn, result=planning_result)
            # region agent log
            acp_debug_log(
                location="spec.py:_handle_session_prompt:permission_done",
                message="permission response received",
                data=lambda: {
                    "run_id": run_id,
                    "outcome": permission_result.get("outcome"),
                    "has_metadata": isinstance(permission_result.get("metadata"), dict),
                    "metadata_keys": sorted(permission_result["metadata"].keys())
                    if isinstance(permission_result.get("metadata"), dict)
                    else [],
                    "top_level_keys": sorted(permission_result.keys()),
                },
                hypothesis_id="GAP1",
            )
            # endregion
            if attached_turn is not None:
                # The host's exact decision for this artifact, decided as the application below is.
                session.context_approvals[turn_seq] = (
                    approval_fact_from_permission(
                        turn_seq=turn_seq,
                        artifact_hash=planning_result.plan_hash,
                        permission_result=permission_result,
                        halted=turn.turn_control.halt_requested(),
                    ),
                )
            if turn.turn_control.halt_requested() or not _permission_approved(permission_result):
                await self._commit_turn(
                    conversation=conversation,
                    turn=turn,
                    sanitized_user_prompt=admission.sanitized_user_prompt,
                    result=planning_result,
                    outcome=ConversationOutcome.CANCELLED
                    if turn.turn_control.halt_requested()
                    else ConversationOutcome.REJECTED,
                )
                return self._turn(
                    success_response(request_id=request.get("id"), result={"stopReason": "cancelled"}),
                    turn_control,
                    ownership_slot,
                )

            approved_request = planning_request.model_copy(
                update={
                    "approval": AgentApproval(
                        approved=True,
                        approval_id=new_approval_id(),
                        plan_hash=planning_result.plan_hash or "",
                    )
                }
            )
            approved_result = await self._in_worker(
                session,
                turn,
                self._runner.run,
                approved_request,
                **self._runner_runtime_kwargs(
                    session=session,
                    operation_control=turn.turn_control,
                    stage_receipts=session.cost_settlement.record_attempt,
                    route_binder=turn.route_binder,
                    integrity_failure=session.cost_settlement.record_integrity_failure,
                ),
            )
            # region agent log
            acp_debug_log(
                location="spec.py:_handle_session_prompt:approved_done",
                message="approved execution completed",
                data=lambda: {
                    "run_id": run_id,
                    "status": approved_result.status.value,
                    "mutation_count": approved_result.mutation_count,
                    "tool_call_count": len(approved_result.tool_calls),
                    "tool_names": [call.tool_name for call in approved_result.tool_calls],
                },
                hypothesis_id="H7",
                run_id="post-fix",
            )
            # endregion
            await self._emit_result_updates(session_id=session_id, result=approved_result, planning=False, turn=turn)
            await self._emit_completion_message(session_id=session_id, result=approved_result, turn=turn)
            await self._commit_turn(
                conversation=conversation,
                turn=turn,
                sanitized_user_prompt=admission.sanitized_user_prompt,
                result=approved_result,
                outcome=_conversation_outcome(approved_result),
            )
            return self._turn(
                success_response(request_id=request.get("id"), result={"stopReason": _stop_reason(approved_result)}),
                turn_control,
                ownership_slot,
            )
        except AcpOutboundError as exc:
            # region agent log
            acp_debug_log(
                location="spec.py:_handle_session_prompt:outbound_error",
                message="client rejected outbound ACP request",
                data=lambda exc=exc: {"run_id": run_id, "code": exc.code, "message": exc.message},
                hypothesis_id="H1",
            )
            # endregion
            # A live exit still reports any threshold this turn crossed (Codex CP3 ruling R2).
            await self._emit_exit_cost_alerts(turn)
            return self._turn(
                error_response(
                    request_id=request.get("id"),
                    error=JsonRpcError(code=exc.code, message=exc.message, data=exc.data),
                ),
                turn_control,
                ownership_slot,
            )
        except Exception:
            # An exception after a paid attempt is still a live exit: its crossings are reported
            # once, in this turn, before the failure propagates as it always has (Codex CP3 ruling R2).
            await self._emit_exit_cost_alerts(turn)
            raise
        finally:
            # Every exit projects what this turn's receipts settled; the projection is idempotent and
            # later receipts keep updating it (Plan 12.2 Task 11; Codex CP3 ruling R2).
            self._apply_settled_cost(session, turn)
            self._report_context_faults(turn)
            # Recompute after any cancellation so settlement telemetry is exact even for a turn that
            # ends without a commit (Plan 12.2 Task 2). After transport teardown this is a no-op.
            turn.turn_control.refresh_effect_state()
            turn.turn_control.finalize_once(self._placeholder_settlement(turn))

    async def _refuse_prompt(
        self,
        *,
        request_id: str | int | None,
        session_id: str,
        conversation: ConversationState,
        reason: str,
        ownership_slot: ResponseOwnershipSlot | None,
    ) -> NonTurnResponseEnvelope:
        del conversation
        full = reason in {"cap", "cap_closed", "reservation"}
        message = (
            CONTEXT_RESERVATION_TEXT
            if reason == "reservation"
            else ATTACHED_STORAGE_REFUSAL_TEXT
            if full and self._storage_labelled
            else CAPACITY_REFUSAL_TEXT
            if full
            else "Conversation delivery is indeterminate; this prompt was refused."
            if reason == "delivery_indeterminate"
            else "This prompt was refused."
        )
        # Best-effort explanatory notice; refusal RPC response still returns on notify failure.
        with contextlib.suppress(Exception):
            await self._outbound.notify(
                "session/update",
                build_agent_message_chunk_notification(session_id=session_id, text=message),
            )
        # A full conversation ends the turn normally rather than as a "refusal": Zed hides a refused
        # turn's text behind a generic content-policy banner, and the user must see "start a new
        # thread" (sandbox Zed live check, 2026-09-29). The conversation disposition, not the stop
        # reason, records that capacity refused it.
        return self._non_turn(
            success_response(request_id=request_id, result={"stopReason": "end_turn" if full else "refusal"}),
            ownership_slot,
        )

    async def _prepare_attached_context(
        self,
        *,
        request_id: str | int | None,
        session: AcpSpecSession,
        conversation: ConversationState,
        turn: AcpPromptTurn,
        attached_turn: AttachedTurn,
        sanitized_user_prompt: str,
        ownership_slot: ResponseOwnershipSlot | None,
    ) -> TurnResponseEnvelope | None:
        """Prepare an attached turn's view off the event loop (Plan 12.2 Task 9; design spec 8).

        Returns the turn's response when it stops here, or None to dispatch. A cancelled turn sends
        and publishes nothing and is committed as cancelled. An unavailable engine whose full history
        is over the floor is refused with zero planning/answer calls and no commit: the thread stays
        OPEN and the next turn tries again. Every maintenance attempt was already recorded.
        """
        outcome = await self._in_worker(session, turn, attached_turn.prepare)
        self._report_context_faults(turn, outcome=outcome.kind)
        halted = turn.turn_control.halt_requested()
        if outcome.kind in {"cancelled", "unavailable"} or halted:
            # No planning or answer call follows; any summaries already paid for still count.
            self._apply_settled_cost(session, turn)
        strategy = _STRATEGY_LABELS[attached_turn.strategy]  # captured; a setter during maintenance never changes it
        if outcome.kind == "cancelled" or halted:
            await self._commit_turn(
                conversation=conversation,
                turn=turn,
                sanitized_user_prompt=sanitized_user_prompt,
                result=_context_stop_result(turn, _CONTEXT_CANCELLED_TEXT),
                outcome=ConversationOutcome.CANCELLED,
                completion_text=_CONTEXT_CANCELLED_TEXT,
            )
            return self._turn(success_response(request_id=request_id, result={"stopReason": "cancelled"}), turn.turn_control, ownership_slot)
        if outcome.kind == "unavailable":
            await self._emit_final_text(
                session_id=turn.session_id, text=context_unavailable_text(outcome.reason, strategy), turn=turn
            )
            await self._emit_cost_alerts(turn)
            return self._turn(success_response(request_id=request_id, result={"stopReason": "end_turn"}), turn.turn_control, ownership_slot)
        checkpoint = attached_turn.checkpoint_to_publish(current_generation=conversation.generation, cancelled=halted)
        if checkpoint is not None:
            session.context_checkpoint = checkpoint
        if outcome.kind == "fallback":
            # Live-only and best-effort, before any dispatch; never stored in the canonical history.
            with contextlib.suppress(Exception):
                await self._outbound.notify(
                    "session/update",
                    build_agent_message_chunk_notification(
                        session_id=turn.session_id, text=CONTEXT_FALLBACK_TEXT.format(strategy=strategy)
                    ),
                )
        return None

    @property
    def _storage_labelled(self) -> bool:
        """Whether this adapter's conversation limit is storage, not the model's context: attached, or
        absent under a trusted route policy whose requests the Gateway guards (release supplement V1)."""
        return self._context_attachment is not None or self._route_policy is not None

    def _warning_text(self) -> str:
        if self._context_attachment is not None:
            return ATTACHED_STORAGE_WARNING_TEXT
        return ABSENT_STORAGE_WARNING_TEXT if self._route_policy is not None else CAPACITY_WARNING_TEXT

    async def _emit_sliding_notice(self, session: AcpSpecSession) -> None:
        """The first admitted turn after a switch to sliding says so, once (design spec 10).

        Live-only and best-effort: only a confirmed flush clears the obligation, so a failed or
        ambiguous send is tried again on the next admitted sliding turn; it never fails this turn."""
        payload = build_agent_message_chunk_notification(session_id=session.session_id, text=SLIDING_ACTIVE_TEXT)
        try:
            await self._outbound.notify("session/update", payload, require_flushed=True)
        except Exception:  # noqa: BLE001 - a notice failure never fails the turn
            return
        session.sliding_notice_pending = False

    def _blocking_notice(self, session_id: str, loop: asyncio.AbstractEventLoop) -> Any:
        """A notice channel for work off the event loop: delivers `text` to this session and returns
        True only once the send is confirmed as flushed, within a finite wait."""

        def deliver(text: str) -> bool:
            payload = build_agent_message_chunk_notification(session_id=session_id, text=text)
            future = asyncio.run_coroutine_threadsafe(
                self._outbound.notify("session/update", payload, require_flushed=True), loop
            )
            try:
                future.result(timeout=_NOTICE_FLUSH_TIMEOUT_SECONDS)
            except Exception:  # noqa: BLE001 - unconfirmed: nothing that needs the notice is sent
                future.cancel()
                return False
            return True

        return deliver

    @staticmethod
    def _plan_record_fits(conversation: ConversationState, turn_seq: int, sanitized_user_prompt: str, plan_text: str) -> bool:
        """Whether this turn's record can keep its plan and still commit a result within the attached
        source limit: the reply is bounded at commit, the plan and facts never are."""
        assert isinstance(conversation, AttachedConversationState)
        return conversation.plan_fits(
            turn_seq,
            sanitized_user_prompt=sanitized_user_prompt,
            sanitized_plan_text=conversation.sanitize_text(plan_text) if plan_text else "",
        )

    async def _finish_chat_turn(
        self,
        *,
        request_id: str | int | None,
        session_id: str,
        conversation: ConversationState,
        turn: AcpPromptTurn,
        sanitized_user_prompt: str,
        result: AgentRunResult,
        ownership_slot: ResponseOwnershipSlot | None,
    ) -> TurnResponseEnvelope:
        """Plan 12.1: settle a Chat turn. It never sends a plan card or asks for permission.

        A nonblank completed answer is the turn's final text. Any terminal
        failure shows the runner's corrective text, records a non-success
        outcome and ends the turn normally (``end_turn``) rather than with
        ``refusal``; a cancelled turn returns ``cancelled``.
        """
        if turn.turn_control.halt_requested():
            await self._commit_turn(
                conversation=conversation,
                turn=turn,
                sanitized_user_prompt=sanitized_user_prompt,
                result=result,
                outcome=ConversationOutcome.CANCELLED,
                completion_text=_CHAT_CANCELLED_TEXT,
            )
            return self._turn(
                success_response(request_id=request_id, result={"stopReason": "cancelled"}),
                turn.turn_control,
                ownership_slot,
            )
        answer = _chat_answer_text(result)
        if answer:
            text, outcome = answer, ConversationOutcome.COMPLETED
        else:
            text = result.output_text.strip() or _CHAT_FAILURE_FALLBACK_TEXT
            outcome = _conversation_outcome(result)
            if outcome is ConversationOutcome.COMPLETED:
                outcome = ConversationOutcome.FAILED
        await self._emit_final_text(session_id=session_id, text=text, turn=turn)
        await self._commit_turn(
            conversation=conversation,
            turn=turn,
            sanitized_user_prompt=sanitized_user_prompt,
            result=result,
            outcome=outcome,
            completion_text=text,
        )
        return self._turn(
            success_response(request_id=request_id, result={"stopReason": "end_turn"}),
            turn.turn_control,
            ownership_slot,
        )

    async def _emit_final_text(self, *, session_id: str, text: str, turn: AcpPromptTurn) -> None:
        turn.turn_control.seal_final_delivery()
        lease = turn.turn_control.start_terminal_message("final_text")
        if not lease.granted:
            return
        await self._outbound.notify(
            "session/update",
            build_agent_message_chunk_notification(session_id=session_id, text=text),
        )

    async def _commit_turn(
        self,
        *,
        conversation: ConversationState,
        turn: AcpPromptTurn,
        sanitized_user_prompt: str,
        result: AgentRunResult,
        outcome: ConversationOutcome,
        completion_text: str | None = None,
    ) -> None:
        raw_plan = result.candidate_plan_text or ""
        plan_text = conversation.sanitize_text(raw_plan) if raw_plan else ""
        completion = conversation.sanitize_text(
            completion_text if completion_text is not None else _completion_message(result)
        )
        decision = conversation.prepare_commit(
            turn.turn_seq,
            sanitized_user_prompt=sanitized_user_prompt,
            sanitized_plan_text=plan_text,
            sanitized_completion_text=completion,
            outcome=outcome,
            # The effect the turn's operations actually settled, recomputed after any cancellation
            # (Plan 12.2 Task 2). A turn that started no WRITE or TEST, including every Chat turn,
            # settles NONE.
            effect_state=turn.turn_control.refresh_effect_state(),
        )
        conversation.commit_after_final_flush(decision)
        # A long reply can cross 80% (or fill the conversation outright) after an admission that
        # was well below it; tell the user now, not at the refusal. A reply past the cap never
        # gets the "soon" warning, even when an earlier disposition kept it from closing.
        if decision.closes_cap and conversation.disposition is ConversationDisposition.CAP_CLOSED:
            await self._emit_capacity_notice(
                session_id=turn.session_id,
                conversation=conversation,
                text=ATTACHED_STORAGE_REACHED_TEXT if self._storage_labelled else CAPACITY_REACHED_TEXT,
                is_warning=False,
            )
        elif (
            not decision.closes_cap
            and decision.crosses_warning
            and conversation.note_warning_threshold_for_attempt(decision.projected_bytes)
        ):
            await self._emit_capacity_notice(
                session_id=turn.session_id, conversation=conversation, text=self._warning_text(), is_warning=True
            )
        await self._emit_usage_update(session_id=turn.session_id, conversation=conversation, turn=turn)
        await self._emit_request_capacity_warning(turn)
        await self._emit_cost_alerts(turn)

    def _apply_turn_cost(
        self, session: AcpSpecSession, turn: AcpPromptTurn, *, planning_cost: Decimal, planning_complete: bool
    ) -> None:
        """A runner's own reported total, kept only for a runner that reports no planning or answer
        receipt for the turn (one that does not report its attempts). Receipts, when present, are the
        turn's cost and its projection never adds this claim: no second debit (Codex CP3 ruling R2)."""
        self._apply_settled_cost(session, turn)
        if any(r.stage in {"planning", "answer"} for r in session.cost_settlement.receipts(turn.run_id)):
            return
        session.conversation.apply_planning_cost_once(turn.turn_seq, cost_usd=planning_cost, cost_complete=planning_complete)

    @staticmethod
    def _apply_settled_cost(session: AcpSpecSession, turn: AcpPromptTurn) -> None:
        """Project the turn's settled receipts (every stage) into the conversation, ordered with every
        other projection of this session. Idempotent: the turn's entry is replaced, never added to."""
        conversation = session.conversation
        session.cost_settlement.project(
            turn.run_id,
            lambda turn_id, summary: conversation.project_turn_cost(
                turn_id, known_usd=summary.known_subtotal_usd, complete=summary.complete
            ),
        )

    async def _in_worker(self, session: AcpSpecSession, turn: AcpPromptTurn, function: Any, *args: Any, **kwargs: Any) -> Any:
        """Run `function` off the event loop as one invocation of this turn: the turn's cost stays
        incomplete while the worker runs, even after this coroutine stops waiting for it (transport
        teardown), and a worker that never started can never start later (Codex CP3 ruling R2)."""
        invocation = session.cost_settlement.open_invocation(turn.run_id)

        def call() -> Any:
            if not invocation.start():
                return None  # its turn already stopped waiting; nothing may run now
            try:
                return function(*args, **kwargs)
            finally:
                invocation.end()

        try:
            return await asyncio.to_thread(call)
        finally:
            invocation.abandon_unstarted()

    async def _emit_exit_cost_alerts(self, turn: AcpPromptTurn) -> None:
        """Alerts for a live exit that did not commit. Never after transport teardown: the facts stay
        in the settlement, and no live send is attempted (Codex CP3 ruling R2)."""
        if turn.turn_control.transport_abandoned():
            return
        with contextlib.suppress(Exception):
            await self._emit_cost_alerts(turn)

    def _report_context_faults(self, turn: AcpPromptTurn, *, outcome: str | None = None) -> None:
        """One content-free operator line per attached-view fault (Codex CP3 ruling M2): the turn's
        run id, the phase and a bounded category, never exception text, history, summary, credential or
        engine reason. Best-effort: it never fails the turn."""
        attached = turn.attached
        if attached is None:
            return
        try:
            for fault in attached.take_faults():
                print(
                    f"optimus.acp: context fault run_id={turn.run_id} phase={fault.phase} "
                    f"category={fault.category} outcome={outcome or 'repack_refused'}",
                    file=sys.stderr,
                )
        except Exception:  # noqa: BLE001 - a diagnostic never fails the turn
            return

    async def _emit_cost_alerts(self, turn: AcpPromptTurn) -> None:
        """Report each configured cost threshold this turn or session has newly reached, once, as a
        live notice. Alerts never refuse, stop or delay anything; a failed send is dropped."""
        session = self._sessions.get(turn.session_id)
        if session is None or not self._alert_policies:
            return
        settlement = session.cost_settlement
        turn_summary = settlement.settle_turn(turn.run_id)
        session_summary = settlement.settle_all()
        summaries = {
            "turn": CostScopeSummary(
                scope="turn", scope_id=turn.run_id, known_subtotal_usd=turn_summary.known_subtotal_usd, complete=turn_summary.complete
            ),
            "session": CostScopeSummary(
                scope="session",
                scope_id=turn.session_id,
                known_subtotal_usd=session_summary.known_subtotal_usd,
                complete=session_summary.complete,
            ),
        }
        for policy in self._alert_policies:
            for notice in session.alert_tracker.new_notices(summaries[policy.scope], policy):
                with contextlib.suppress(Exception):
                    await self._outbound.notify(
                        "session/update", build_agent_message_chunk_notification(session_id=turn.session_id, text=notice.text)
                    )

    async def _emit_capacity_notice(
        self,
        *,
        session_id: str,
        conversation: ConversationState,
        text: str,
        is_warning: bool,
    ) -> None:
        """Deliver a capacity notice: the one-time 80% warning or the "limit reached" notice.

        Best-effort: a failed send never fails the turn. The send demands a confirmed flush, and
        the warning is confirmed only then. A failed or ambiguous write re-arms it, so the next
        opportunity (this turn's commit, or the next admission) sends it again: a possible
        duplicate warning is preferred to a lost one. The `NoticeControl` warning sequence, when
        present, is bookkeeping retired as soon as the attempt settles. Main has no
        `session/load`, so the notice is live-only: nothing stores or replays it.
        """
        handle = (
            self._notice_control.allocate_warning_sequence()
            if is_warning and self._notice_control is not None
            else None
        )
        payload = build_agent_message_chunk_notification(session_id=session_id, text=text)
        try:
            await self._outbound.notify("session/update", payload, require_flushed=True)
        except Exception:
            if is_warning:
                conversation.rearm_warning_attempt()
        else:
            if is_warning:
                conversation.confirm_warning_flushed()
        finally:
            if handle is not None and self._notice_control is not None:
                self._notice_control.abort_warning_sequence(handle)

    async def _emit_usage_update(
        self, *, session_id: str, conversation: ConversationState, turn: AcpPromptTurn | None = None
    ) -> None:
        """Send the ACP `usage_update` meter after a committed turn, with the session's cost only
        when it is complete.

        Engine-absent without a route policy (inactive enforcement): estimated context used/size
        (storage bytes // 4). Attached (Plan 12.2 Task 10; design spec 8.4), and engine-absent under a
        trusted route policy (release supplement V1): the largest complete planning/answer input actually
        sent during the turn against that request's usable capacity; summarizer calls are excluded, and
        a turn that sent nothing, or whose request the Gateway refused, gets no reading.

        Live-only and best-effort: it is never stored or replayed, and a failed send never fails
        the turn. A refusal commits nothing, so it sends no new reading.
        """
        gauge = conversation.usage_gauge()
        used, size = gauge.used, gauge.size
        if turn is not None and (turn.attached is not None or turn.route_binder is not None):
            reading = turn.attached.largest_dispatch() if turn.attached is not None else turn.route_binder.largest_dispatch()
            if reading is None:
                return
            used, size = reading.tokens, reading.capacity
        payload = build_usage_update(session_id=session_id, used=used, size=size, cost=gauge.cost)
        with contextlib.suppress(Exception):
            await self._outbound.notify("session/update", payload)

    async def _emit_request_capacity_warning(self, turn: AcpPromptTurn) -> None:
        """Release supplement V1: once a session's engine-absent request reaches 80% of its usable input
        capacity under a trusted route policy, say so, once. It reads the same reading as the meter, so a
        refused request (no reading) gets its capacity refusal instead. Separate from the storage notice;
        live-only and best-effort: only a confirmed flush retires it, and a failed send never fails the
        turn."""
        session = self._sessions.get(turn.session_id)
        if session is None or session.request_warning_sent or turn.attached is not None or turn.route_binder is None:
            return
        reading = turn.route_binder.largest_dispatch()
        if reading is None or reading.tokens < REQUEST_WARNING_FRACTION * reading.capacity:
            return
        payload = build_agent_message_chunk_notification(session_id=turn.session_id, text=REQUEST_CAPACITY_WARNING_TEXT)
        try:
            await self._outbound.notify("session/update", payload, require_flushed=True)
        except Exception:  # noqa: BLE001 - a notice failure never fails the turn
            return
        session.request_warning_sent = True

    async def _request_permission(self, *, turn: AcpPromptTurn, result: AgentRunResult) -> dict[str, Any]:
        tool_call_id = new_tool_call_id()
        turn.permission_tool_call_id = tool_call_id
        params = build_request_permission_params(
            session_id=turn.session_id,
            tool_call_id=tool_call_id,
            plan_text=result.output_text,
            plan_hash=result.plan_hash or "",
            run_id=result.run_id,
        )
        # region agent log
        acp_debug_log(
            location="spec.py:_request_permission:pre_send",
            message="sending session/request_permission",
            data=lambda: {
                "session_id": turn.session_id,
                "run_id": result.run_id,
                "param_keys": sorted(params.keys()),
                "has_toolCall": "toolCall" in params,
            },
            hypothesis_id="H2",
        )
        # endregion
        request_task = asyncio.create_task(self._outbound.request("session/request_permission", params))
        await asyncio.sleep(0)
        if self._active_turns.get(turn.session_id) is turn:
            if hasattr(self._outbound, "requests") and self._outbound.requests:
                turn.pending_permission_request_id = self._outbound.requests[-1]["id"]
            elif getattr(self._outbound, "last_outbound_request_id", None) is not None:
                turn.pending_permission_request_id = self._outbound.last_outbound_request_id
        return await request_task

    def _runner_runtime_kwargs(
        self,
        *,
        session: AcpSpecSession,
        planning_progress_observer: Any | None = None,
        halt_requested: Any | None = None,
        operation_control: Any | None = None,
        context_packer: Any | None = None,
        stage_receipts: Any | None = None,
        route_binder: Any | None = None,
        integrity_failure: Any | None = None,
    ) -> dict[str, Any]:
        """Pass client-MCP runtime kwargs only when the runner accepts them."""
        kwargs: dict[str, Any] = {}
        try:
            parameters = inspect.signature(self._runner.run).parameters
        except (TypeError, ValueError):
            parameters = {}
        accepts_var_kw = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values())

        def _maybe(name: str, value: object) -> None:
            if accepts_var_kw or name in parameters:
                kwargs[name] = value

        if planning_progress_observer is not None:
            _maybe("planning_progress_observer", planning_progress_observer)
        if halt_requested is not None:
            _maybe("halt_requested", halt_requested)
        if operation_control is not None:
            _maybe("operation_control", operation_control)
        if context_packer is not None:
            _maybe("context_packer", context_packer)
        if stage_receipts is not None:
            _maybe("stage_receipts", stage_receipts)
        if route_binder is not None:
            _maybe("route_binder", route_binder)
        if integrity_failure is not None:
            _maybe("integrity_failure", integrity_failure)
        _maybe("client_mcp_service", _client_mcp_service(session))
        _maybe("mcp_permission_broker", self._mcp_permission_broker_for(session))
        return kwargs

    def _mcp_permission_broker_for(self, session: AcpSpecSession) -> AcpMcpPermissionBroker | None:
        if session.client_mcp_state is None:
            return None
        loop = asyncio.get_running_loop()

        async def _request(params: dict[str, Any]) -> dict[str, Any]:
            return await self._outbound.request("session/request_permission", params)

        def _issue(request: Any) -> ClientMcpOneCallApproval | None:
            state = session.client_mcp_state
            if state is None:
                return None
            return state.tool_service.issue_one_call_approval(request)

        return AcpMcpPermissionBroker(
            session_id=session.session_id,
            request_permission=_request,
            issue_approval=_issue,
            timeout_seconds=30.0,
            loop=loop,
        )

    async def _emit_result_updates(
        self,
        *,
        session_id: str,
        result: AgentRunResult,
        planning: bool,
        turn: AcpPromptTurn | None = None,
    ) -> None:
        if planning:
            if turn is not None:
                lease = turn.turn_control.try_start(SendKind.PROVISIONAL_PLAN, "plan")
                if not lease.granted:
                    return
            update_payload = build_plan_session_update(session_id=session_id, plan_text=result.output_text)
            # region agent log
            acp_debug_log(
                location="spec.py:_emit_result_updates:plan",
                message="emitting plan session/update",
                data=lambda: {
                    "session_id": session_id,
                    "update_keys": sorted(update_payload["update"].keys()),
                    "has_entries": "entries" in update_payload["update"],
                },
                hypothesis_id="GAP2",
            )
            # endregion
            await self._outbound.notify("session/update", update_payload)
            return
        for tool_call in result.tool_calls:
            tool_call_id = new_tool_call_id()
            payload = build_tool_call_notification(
                session_id=session_id,
                tool_call_id=tool_call_id,
                title=tool_call.tool_name,
                summary=tool_call.summary,
                kind=tool_kind_for_name(tool_call.tool_name),
            )
            # region agent log
            if debug_trace_enabled():
                acp_debug_log(
                    location="spec.py:_emit_result_updates:tool_call",
                    message="emitting tool_call session/update",
                    data=lambda tool_call=tool_call, tool_call_id=tool_call_id, payload=payload: {
                        "session_id": session_id,
                        "tool_call_id": tool_call_id,
                        "session_update": payload["update"]["sessionUpdate"],
                        "tool_name": tool_call.tool_name,
                        "status": payload["update"]["status"],
                    },
                    hypothesis_id="H5",
                    run_id="post-fix",
                )
            # endregion
            await self._outbound.notify("session/update", payload)

    async def _emit_completion_message(
        self,
        *,
        session_id: str,
        result: AgentRunResult,
        turn: AcpPromptTurn | None = None,
    ) -> None:
        if turn is not None:
            turn.turn_control.seal_final_delivery()
            lease = turn.turn_control.start_terminal_message("completed_plan")
            if not lease.granted:
                return
        completed_plan = build_plan_session_update(
            session_id=session_id,
            plan_text=result.output_text,
            entry_status="completed",
        )
        await self._outbound.notify("session/update", completed_plan)
        if turn is not None:
            lease = turn.turn_control.start_terminal_message("final_text")
            if not lease.granted:
                return
        message = _completion_message(result)
        message_payload = build_agent_message_chunk_notification(session_id=session_id, text=message)
        # region agent log
        acp_debug_log(
            location="spec.py:_emit_completion_message",
            message="emitting completion updates",
            data=lambda: {
                "session_id": session_id,
                "plan_entry_count": len(completed_plan["update"]["entries"]),
                "message_preview": message[:120],
                "has_agent_message_chunk": message_payload["update"]["sessionUpdate"] == "agent_message_chunk",
            },
            hypothesis_id="H7",
            run_id="post-fix",
        )
        # endregion
        await self._outbound.notify("session/update", message_payload)

    async def _emit_planning_progress(
        self,
        *,
        session_id: str,
        event: PlanningProgressEvent,
        turn: AcpPromptTurn | None = None,
    ) -> None:
        if turn is not None:
            lease = turn.turn_control.try_start(
                SendKind.PROGRESS,
                f"progress-{event.settled_turn}",
            )
            if not lease.granted:
                return
        payload = build_planning_progress_notification(
            session_id=session_id,
            settled_turn=event.settled_turn,
            max_planning_turns=event.max_planning_turns,
            read_request_count=event.read_request_count,
        )
        await self._outbound.notify("session/update", payload)


_VISIBLE_WORKSPACE_CONTEXT_FAILURES = frozenset(
    {
        "AMBIGUOUS_WORKSPACE_REFERENCE",
        "REQUIRED_WORKSPACE_FILE_TOO_LARGE",
        "WORKSPACE_REFERENCE_NOT_READABLE",
    }
)

_PLANNING_TERMINAL_STOP_REASONS = frozenset(
    {
        "PLANNING_GATEWAY_FAILURE",
        "PLANNING_GATEWAY_COST_UNKNOWN",
        "PLANNING_GATEWAY_REFUSED",
        "PLANNING_INPUT_CAPACITY_EXCEEDED",
        "PLANNING_NOTICE_UNDELIVERED",
        "PLANNING_REPEATED_READ_REQUEST",
        "PLANNING_UNPARSEABLE_RESPONSE",
        "PLANNING_OUTPUT_TRUNCATED",
        "PLANNING_OUTPUT_UNFINISHED",
        "PLANNING_WALL_CLOCK_EXHAUSTED",
        "PLANNING_TURN_LIMIT_EXHAUSTED",
        "PLANNING_HALTED",
        "PLANNING_MODEL_REFUSED",
        "CONTEXT_CAPACITY_EXCEEDED",
        "PLANNING_OBSERVATION_BUDGET_EXHAUSTED",
        "PLANNING_READ_BUDGET_EXHAUSTED",
        "PLANNING_READ_INVALID_RANGE",
        "PLANNING_READ_INVALID_PATH",
        "PLANNING_READ_FILE_NOT_FOUND",
        "PLANNING_READ_NOT_UTF8_ALIGNED",
        "PLANNING_READ_SOURCE_CHANGED",
        "PLANNING_READ_GUARD_BLOCKED",
    }
)


def _completion_message(result: AgentRunResult) -> str:
    if result.mutation_count > 0:
        writes = [call.summary for call in result.tool_calls if call.tool_name == "write_file"]
        if writes:
            return "Completed:\n" + "\n".join(f"- {summary}" for summary in writes)
        return f"Completed {result.mutation_count} file change(s)."
    if result.tool_calls:
        return "Executed:\n" + "\n".join(f"- {call.summary}" for call in result.tool_calls)
    if result.stop_reason in _VISIBLE_WORKSPACE_CONTEXT_FAILURES:
        return result.output_text
    if result.stop_reason in _PLANNING_TERMINAL_STOP_REASONS:
        return result.output_text
    return "Turn completed."


def _chat_answer_text(result: AgentRunResult) -> str:
    """The answer a Chat turn may show: a completed, nonblank model response."""
    if result.status is not AgentRunStatus.COMPLETED:
        return ""
    return result.output_text.strip()


def _client_mcp_service(session: AcpSpecSession) -> object | None:
    state = session.client_mcp_state
    if state is None:
        return None
    return state.tool_service


def _permission_approved(permission_result: dict[str, Any]) -> bool:
    outcome = permission_result.get("outcome")
    if not isinstance(outcome, dict):
        return False
    if outcome.get("outcome") != "selected":
        return False
    return outcome.get("optionId") == "approve"


def _text_from_content_blocks(blocks: list[Any]) -> str:
    texts: list[str] = []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
            texts.append(block["text"])
    return "\n".join(texts).strip()


def _context_stop_result(turn: AcpPromptTurn, text: str) -> AgentRunResult:
    """The result a turn records when it stopped before any planning or answer call."""
    return AgentRunResult(
        run_id=turn.run_id,
        session_id=turn.session_id,
        execution_mode=turn.execution_mode,
        status=AgentRunStatus.TERMINATED,
        final_state="TERMINATED",
        output_text=text,
        tool_calls=(),
        total_cost_usd=Decimal("0"),
        mutation_count=0,
        provider_keys_resolvable=(),
        stop_reason="cancelled",
    )


def _conversation_outcome(result: AgentRunResult) -> ConversationOutcome:
    if result.status is AgentRunStatus.COMPLETED:
        return ConversationOutcome.COMPLETED
    if result.status is AgentRunStatus.TERMINATED and result.stop_reason == "cancelled":
        return ConversationOutcome.CANCELLED
    if result.status is AgentRunStatus.AWAITING_APPROVAL:
        return ConversationOutcome.REJECTED
    return ConversationOutcome.FAILED


def _stop_reason(result: AgentRunResult) -> str:
    if result.status is AgentRunStatus.COMPLETED:
        return "end_turn"
    if result.status is AgentRunStatus.TERMINATED and result.stop_reason == "cancelled":
        return "cancelled"
    if result.stop_reason in _PLANNING_TERMINAL_STOP_REASONS:
        return "end_turn"
    if result.stop_reason == "PLAN_NOT_FOUND_OR_EXPIRED":
        return "end_turn"
    return "refusal"
