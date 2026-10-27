from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import inspect
import itertools
import sys
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from functools import partial
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Any, Literal, NotRequired, Protocol, TypedDict

from context_engine import SummaryCheckpoint
from optimus.acp.conversation import (
    AttachedConversationState,
    ConversationDisposition,
    ConversationOutcome,
    ConversationSanitizer,
    ConversationSanitizerInputs,
    ConversationState,
)
from optimus.acp.debug_trace import (
    PRE_RUN_REFUSAL_REASONS,
    PROMPT_REFUSAL_REASONS,
    acp_debug_log,
    debug_trace_enabled,
    log_auto_route,
    log_context_fault,
    log_pre_run_refusal,
    log_prompt_refusal,
)
from optimus.acp.errors import (
    INVALID_REQUEST,
    MCP_REOPEN_REFUSED,
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
    LOOP_CONTINUE_OPTION_ID,
    LOOP_STOP_OPTION_ID,
    MODE_CONFIG_ID,
    build_agent_message_chunk_notification,
    build_config_option_update_notification,
    build_current_mode_update_notification,
    build_loop_checkin_params,
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
from optimus.agent.models import TEST_STOP_REASONS, AgentApproval, AgentRunRequest, AgentRunResult, AgentRunStatus, AgentToolCall
from optimus.agent.planning_loop import (
    CheckInDecision,
    EscalationGrant,
    EscalationRefusal,
    PlanningCheckIn,
    PlanningCheckInCallback,
    PlanningEscalation,
    PlanningEscalationCallback,
    PlanningProgressEvent,
)
from optimus.context.adapter import ApprovalFact, approval_fact_from_permission
from optimus.context.assembly import AttachedTurn, ContextAttachment
from optimus.gateway.attempts import ROUTE_STOPPED_NO_RETRY
from optimus.mcp.client_catalog import ClientMcpOneCallApproval
from optimus.mcp.client_config import ClientMcpConfigError
from optimus.mcp.client_disposition import (
    AcpMcpPermissionBroker,
    ClientMcpDisposition,
    ClientMcpRuntime,
    ClientMcpSessionState,
    run_close_hooks,
)
from optimus.runtime.modes import ExecutionMode
from optimus.tools.line_endings import WRITE_LINE_ENDINGS_MIXED
from optimus.usage.cost_alerts import AlertPolicy, AlertTracker, CostScopeSummary
from optimus.usage.turn_settlement import TurnCostSummary, TurnSettlement, receipt_from_maintenance
from optimus_security.failure_facts import host_session_id

if TYPE_CHECKING:
    from optimus.acp.auto_composition import AutoDecision, AutoRouter
    from optimus.context.assembly import DispatchReading
    from optimus.gateway.route_binding import RequestReading, RoutePolicy, TurnRouteBinder
    from optimus.telemetry.jsonl import JsonlTelemetryWriter


def _operator_line(line: str) -> None:
    """One content-free operator line on stderr. A failed write never suppresses the trace or telemetry record
    beside it (correction plan v4, C7)."""
    with contextlib.suppress(Exception):
        print(line, file=sys.stderr)

class _PlanningRequestFields(TypedDict):
    run_id: str
    session_id: str
    task: str
    execution_mode: ExecutionMode
    workspace_root: Path
    conversation_envelope: str
    selection_text: NotRequired[str]
    context_digest: NotRequired[str]
    max_planning_turns: NotRequired[int]


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
# Plan 12.4 Task 4: an Auto turn refused before any answer call; the thread stays open.
_AUTO_REFUSAL_TEXT = {
    "AUTO_NO_ROUTABLE_MODEL": (
        "Auto has no model left to route this turn to: every eligible model has stopped for this launch. Nothing was "
        "sent. Restart Optimus, or choose a model with OPTIMUS_AGENT_MODEL."
    ),
    "ACCOUNTING_INTEGRITY": "Auto could not account for this turn's classification cost, so no answer was requested.",
}
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


# #400 (Codex round 40, finding 2): the summarizer shares the planner's experimental route, so after a summary
# failure that proved it stopped, neither a retry nor Sliding window can help; the engine reason is kept unshown.
CONTEXT_ROUTE_STOPPED_TEXT = (
    "The {strategy} summary could not be completed, and the model gateway has stopped this experimental route. "
    f"{ROUTE_STOPPED_NO_RETRY}"
)


def context_unavailable_text(reason: str | None, strategy: str, *, route_stopped: bool = False) -> str:
    """The refusal for an attached view that could not be built and a full history over the floor:
    the fixed message for a known engine reason, the generic one otherwise, then the common ending.
    `route_stopped`: a summary call's failure proved the shared experimental route stopped (#400)."""
    if route_stopped:
        return f"{CONTEXT_ROUTE_STOPPED_TEXT.format(strategy=strategy)} {CONTEXT_UNAVAILABLE_ENDING}"
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


def resolve_interactive_recovery(environ: Mapping[str, str], *, caller_default: bool) -> bool:
    """Plan 12.3, Design 6: `OPTIMUS_LOOP_RECOVERY` (`interactive` or `headless`), else the caller's default.
    An ACP prompt defaults to interactive; a test composition, like every non-ACP caller, to headless.
    A client that answers every permission request on its own (acpx `--approve-all`) sets headless.
    Resolved once, like resolve_max_planning_turns."""
    raw = environ.get("OPTIMUS_LOOP_RECOVERY")
    if raw is None or raw.strip() == "":
        return caller_default
    value = raw.strip().lower()
    if value not in {"interactive", "headless"}:
        raise ValueError("OPTIMUS_LOOP_RECOVERY must be interactive or headless")
    return value == "interactive"


class AcpOutboundChannel(Protocol):
    async def notify(self, method: str, params: dict[str, Any], *, require_flushed: bool = False) -> None:
        """Send a notification. With ``require_flushed``, anything short of a confirmed flush raises."""
        ...

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        ...

    def cancel_request(self, request_id: str | int, result: dict[str, Any]) -> None:
        ...


@dataclass
class _IdleMcpState:
    phase: str = "ACTIVE"
    idle_epoch: int = 0
    deadline: float | None = None
    turn_seq: int | None = None
    turn_epoch: int = 0
    marker_seen: bool = False
    committed: bool | None = None


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
    # Plan 12.4 Task 4, Auto launches only: each committed turn's routing, keyed by its turn sequence and published only
    # when that turn commits as completed or rejected. Kept apart from the canonical five-field turn records.
    auto_routes: dict[int, AutoDecision] = field(default_factory=dict, repr=False, compare=False)

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
    # Plan 12.4 Task 4: an Auto turn's routing, bound once after classification; its model is the turn's for every
    # call (planning, the approved application and the answer). None on every other launch.
    auto_decision: AutoDecision | None = None
    # Plan 12.4 Task 5: set once the turn's one routing record is written, so a later cancel cannot add a second.
    auto_recorded: bool = False
    # #397: the model a recovery escalation moved the turn to, once; `auto_decision` stays the classifier's routing.
    escalated_model: str | None = None

    @property
    def run_id(self) -> str:
        return f"{self.session_id}:{self.turn_seq}"

    @property
    def turn_model(self) -> str | None:
        """The model the turn's calls send now: the escalation's once moved, else the routed one; None off Auto."""
        return self.escalated_model or (None if self.auto_decision is None else self.auto_decision.model_id)


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
        try:
            if session is not None and session.client_mcp_state is not None:
                self._close_state_once(session)
        finally:
            self._closed_state_ids.discard(session_id)

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
        session_seeder: Callable[[Any], str | None] | None = None,
        failure_telemetry: JsonlTelemetryWriter | None = None,
        interactive_recovery: bool = True,
        auto_router: AutoRouter | None = None,
        mcp_idle_seconds: int | None = None,
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        if mcp_idle_seconds is not None and (type(mcp_idle_seconds) is not int or not 1 <= mcp_idle_seconds <= 2592000):
            raise ValueError("invalid MCP idle seconds")
        self._mcp_idle_seconds = mcp_idle_seconds
        self._monotonic_clock = monotonic_clock
        self._idle_mcp: dict[str, _IdleMcpState] = {}
        self._idle_sweeper: asyncio.Task[None] | None = None
        self._idle_sweep_lock = asyncio.Lock()
        self._mcp_close_tasks: set[asyncio.Task[Any]] = set()
        self._reopen_reservations: dict[str, asyncio.Task[Any]] = {}
        self._reopen_cancelled: set[str] = set()
        # Plan 12.4 Task 4: an Auto launch binds each turn's route and attachment from its router; new sessions take the
        # router's base attachment (the default planner's) for their storage class and initial strategy.
        if auto_router is not None:
            if route_policy is not None or context_attachment is not None:
                raise ValueError("an Auto launch binds each turn's route and attachment itself")
            context_attachment = auto_router.base_attachment
        self._auto_router = auto_router
        # The launch's stop set, told of each model a planning or answer call proves stopped (Plan 12.4 Task 4).
        self._model_stops = None if auto_router is None else auto_router.stops.add
        self._runner = runner
        # Plan 12.3: resolved once by the caller (resolve_interactive_recovery); headless passes no check-in.
        self._interactive_recovery = interactive_recovery
        # Correction plan v4, C4: this harness's workspace writer for the always-on refusal and fault records. Bound
        # here, never configured globally, so a later composition can neither redirect nor clear it.
        self._failure_telemetry = failure_telemetry
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
        # Codex CP3 ruling R4: the injected trusted planning/answer route policy (an ordinary launch's from the
        # shipped registry, Plan 12.2 closure). None sends unbound requests (registry enforcement inactive).
        self._route_policy = route_policy
        # Plan 12.2 Task 13 (Stage C): the approved scenario's one-time seeding of the launch's first new
        # attached session; a returned reason refuses the session instead. None (every other composition)
        # seeds nothing.
        self._session_seeder = session_seeder if context_attachment is not None else None
        self._closed = False

    def record_turn_commit(self, session_id: str, turn_seq: int, *, committed: bool | None) -> None:
        idle = self._idle_mcp.get(session_id)
        if idle is not None and idle.turn_seq == turn_seq:
            idle.marker_seen = True
            idle.committed = committed

    def note_turn_delivered(self, control: TurnControl, *, cancelled: bool = False) -> None:
        idle = self._idle_mcp.get(control.session_id)
        session = self._sessions.get(control.session_id)
        if idle is None or idle.turn_seq != control.turn_seq:
            return
        known = idle.marker_seen and idle.committed is not None
        idle.marker_seen = False
        state = session.client_mcp_state if session is not None else None
        if (self._closed or cancelled or control.halt_requested() or not known
                or idle.turn_epoch != idle.idle_epoch or control.rpc_response_delivery is not RpcResponseDelivery.FLUSHED
                or state is None or state._closed or state.suspended or not state.has_open_peer()
                or idle.phase not in {"ACTIVE", "IDLE_CANDIDATE"}):
            return
        assert self._mcp_idle_seconds is not None
        idle.phase = "IDLE_CANDIDATE"
        idle.deadline = self._monotonic_clock() + self._mcp_idle_seconds

    def start_idle_mcp_sweeper(self) -> None:
        if self._mcp_idle_seconds is None or self._closed or self._idle_sweeper is not None:
            return
        async def sweep() -> None:
            assert self._mcp_idle_seconds is not None
            while True:
                await asyncio.sleep(min(60, self._mcp_idle_seconds))
                await self.sweep_idle_mcp_once()
        self._idle_sweeper = asyncio.create_task(sweep(), name="optimus-idle-mcp-sweeper")

    async def stop_idle_mcp_sweeper(self) -> None:
        task = self._idle_sweeper
        if task is not None:
            task.cancel()
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
            with contextlib.suppress(asyncio.CancelledError):
                task.result()
            self._idle_sweeper = None

    async def sweep_idle_mcp_once(self) -> None:
        runtime = self._client_mcp_runtime
        if self._mcp_idle_seconds is None or runtime is None or self._closed:
            return
        async with self._idle_sweep_lock:
            for session_id, idle in tuple(self._idle_mcp.items()):
                session = self._sessions.get(session_id)
                if session is None:
                    self._idle_mcp.pop(session_id, None)
                    continue
                if (idle.phase != "IDLE_CANDIDATE" or idle.deadline is None or self._monotonic_clock() < idle.deadline
                        or session_id in self._active_turns or session_id in self._reopen_reservations):
                    continue
                state = session.client_mcp_state
                if state is None:
                    continue
                idle.deadline = None
                if state.has_leased_stdio_server() and not runtime.sdk_adapter.stdio_warning_channel_observable():
                    runtime.sdk_adapter.record_diagnostic("WARNING_UNOBSERVABLE")
                    idle.phase = "ACTIVE"
                    continue
                hooks = state.prepare_suspend()
                if hooks is None:
                    idle.phase = "ACTIVE"
                    continue
                idle.phase = "MCP_CLOSING"
                async def close_peer(
                    state: ClientMcpSessionState = state, hooks: tuple[Callable[[], None], ...] = hooks,
                    idle: _IdleMcpState = idle, session_id: str = session_id,
                ) -> None:
                    try:
                        def work() -> tuple[str, ...]:
                            failures = run_close_hooks(hooks)
                            if runtime.sdk_adapter.has_pending_connections_for_session(session_id):
                                failures += ("CLEANUP_UNCERTAIN",)
                            return failures
                        failures = await runtime.disposition.run_blocking(work)
                    except BaseException:
                        state.complete_suspend(("CLEANUP_UNCERTAIN",))
                        idle.phase = "QUARANTINED"
                        raise
                    if idle.phase == "QUARANTINED":
                        failures += ("CLEANUP_UNCERTAIN",)
                    clean = state.complete_suspend(failures)
                    idle.phase = "MCP_SUSPENDED" if clean else "QUARANTINED"
                job = asyncio.create_task(close_peer(), name="optimus-idle-mcp-close")
                self._mcp_close_tasks.add(job)
                budget = max(1, len(state.server_names())) * runtime.sdk_adapter._operation_timeout_seconds
                try:
                    await asyncio.wait_for(asyncio.shield(job), timeout=budget)
                except TimeoutError:
                    idle.phase = "QUARANTINED"
                    runtime.disposition.record_session_close_failure()
                except Exception:
                    idle.phase = "QUARANTINED"
                finally:
                    if job.done():
                        self._mcp_close_tasks.discard(job)

    def _cancel_loop_work(self) -> None:
        self._closed = True
        for reservation in self._reopen_reservations.values():
            reservation.cancel()
        for turn in list(self._active_turns.values()):
            turn.turn_control.request_session_cancel()
            if turn.permission_handle is not None:
                turn.permission_handle.cancel()
            elif turn.pending_permission_request_id is not None:
                self._outbound.cancel_request(turn.pending_permission_request_id, {"outcome": {"outcome": "cancelled"}})
                turn.pending_permission_request_id = None

    async def aclose(self) -> None:
        self._cancel_loop_work()
        prior_failure: BaseException | None = None
        try:
            await self.stop_idle_mcp_sweeper()
        except BaseException as exc:
            prior_failure = exc
        current = asyncio.current_task()
        cancelled = current is not None and current.cancelling() > 0
        reservations = tuple(self._reopen_reservations.values())
        for task in reservations + tuple(self._mcp_close_tasks):
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    current = asyncio.current_task()
                    if current is not None and current.cancelling():
                        cancelled = True
                except BaseException:
                    break
            try:
                task.result()
            except BaseException as exc:
                expected_cancel = task in reservations and isinstance(exc, asyncio.CancelledError)
                if not expected_cancel and prior_failure is None:
                    prior_failure = exc
        self._mcp_close_tasks.clear()
        runtime = self._client_mcp_runtime
        disposition = runtime.disposition if isinstance(runtime, ClientMcpRuntime) else None
        cleanup_lane = disposition if isinstance(disposition, ClientMcpDisposition) else None
        if prior_failure is not None and cleanup_lane is not None:
            cleanup_lane.record_session_close_failure()
        prepared = [(session.client_mcp_state, session.client_mcp_state.prepare_close())
                    for session in self._sessions._sessions.values() if session.client_mcp_state is not None]
        async def close_states() -> None:
            primary: BaseException | None = None
            for state, hooks in prepared:
                try:
                    failures = (await cleanup_lane.run_blocking(partial(run_close_hooks, hooks))
                                if cleanup_lane is not None else await asyncio.to_thread(run_close_hooks, hooks))
                except BaseException as exc:
                    state.complete_close(("SESSION_CLOSE_FAILED",))
                    if primary is None:
                        primary = exc
                else:
                    state.complete_close(failures)
            if cleanup_lane is not None:
                await cleanup_lane.drain()
            if primary is not None:
                raise primary
        job = asyncio.create_task(close_states(), name="optimus-mcp-session-shutdown")
        self._mcp_close_tasks.add(job)
        try:
            while not job.done():
                try:
                    await asyncio.shield(job)
                except asyncio.CancelledError:
                    cancelled = True
            try:
                job.result()
            except BaseException as exc:
                if prior_failure is None:
                    prior_failure = exc
        finally:
            if job.done():
                self._mcp_close_tasks.discard(job)
        self._idle_mcp.clear()
        if prior_failure is not None:
            raise prior_failure
        if cancelled:
            raise asyncio.CancelledError

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
        self._cancel_loop_work()
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
        reservation = self._reopen_reservations.get(session_id)
        if reservation is not None:
            self._reopen_cancelled.add(session_id)
            reservation.cancel()
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
            refusal = self._session_seeder(session) if self._session_seeder is not None else None
            if refusal is not None:
                self._sessions.remove(session.session_id)
                return error_response(request.get("id"), JsonRpcError(code=INVALID_REQUEST, message=refusal))
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
        except BaseException:
            if state is not None:
                hooks = state.prepare_close()
                try:
                    failures = await runtime.disposition.run_blocking(partial(run_close_hooks, hooks))
                except BaseException:
                    state.complete_close(("SESSION_CLOSE_FAILED",))
                else:
                    state.complete_close(failures)
            self._sessions.remove(session.session_id)
            raise

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
            self._pre_run_refused(request, None, "invalid_params")
            return self._non_turn(
                error_response(request.get("id"), JsonRpcError(code=INVALID_REQUEST, message="invalid request")),
                ownership_slot,
            )
        session_id = params.get("sessionId")
        prompt = params.get("prompt")
        if not isinstance(session_id, str) or not isinstance(prompt, list):
            self._pre_run_refused(request, session_id, "invalid_prompt_shape")
            return self._non_turn(
                error_response(request.get("id"), JsonRpcError(code=INVALID_REQUEST, message="invalid request")),
                ownership_slot,
            )
        session = self._sessions.get(session_id)
        if session is None:
            self._pre_run_refused(request, session_id, "unknown_session")
            return self._non_turn(
                error_response(request.get("id"), JsonRpcError(code=INVALID_REQUEST, message="unknown session")),
                ownership_slot,
            )
        task = _text_from_content_blocks(prompt)
        if not task:
            self._pre_run_refused(request, session_id, "empty_prompt")
            return self._non_turn(
                error_response(request.get("id"), JsonRpcError(code=INVALID_REQUEST, message="empty prompt")),
                ownership_slot,
            )

        if session_id in self._active_turns:
            self._pre_run_refused(request, session_id, "turn_in_progress")
            return self._non_turn(
                error_response(
                    request.get("id"),
                    JsonRpcError(code=REQUEST_CANCELLED, message="a turn is already in progress"),
                ),
                ownership_slot,
            )

        idle = self._idle_mcp.get(session_id)
        if self._closed or (idle is not None and idle.phase == "MCP_CLOSING"):
            return self._mcp_refusal(request, session_id, "mcp_closing", ownership_slot)
        if idle is not None and idle.phase == "QUARANTINED":
            return self._mcp_refusal(request, session_id, "mcp_cleanup_uncertain", ownership_slot)
        if session_id in self._reopen_reservations:
            return self._mcp_refusal(request, session_id, "mcp_reopen_in_progress", ownership_slot)

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

        captured_mode = session.execution_mode
        captured_strategy = session.context_strategy
        captured_checkpoint = session.context_checkpoint
        captured_approvals = dict(session.context_approvals)
        captured_notice = session.sliding_notice_pending
        captured_revision = session.config_publication.revision
        if self._mcp_idle_seconds is not None:
            idle = self._idle_mcp.setdefault(session_id, _IdleMcpState())
            idle.idle_epoch += 1
            idle.deadline = None
            idle.marker_seen = False
            if idle.phase == "IDLE_CANDIDATE":
                idle.phase = "ACTIVE"
        state = session.client_mcp_state
        if state is not None and state.suspended and captured_mode is not ExecutionMode.CHAT:
            runtime = self._client_mcp_runtime
            if runtime is None:
                return self._mcp_refusal(request, session_id, "mcp_reopen_refused", ownership_slot)
            async def request_permission(params):
                return await self._outbound.request("session/request_permission", params)
            reservation = asyncio.create_task(runtime.disposition.reopen_suspended(state, request_permission),
                                               name="optimus-mcp-renewal")
            self._reopen_reservations[session_id] = reservation
            try:
                try:
                    outcome = await reservation
                except asyncio.CancelledError:
                    state.restore_suspended()
                    current = asyncio.current_task()
                    if current is not None and current.cancelling():
                        raise
                    return self._non_turn(success_response(request.get("id"), {"stopReason": "cancelled"}), ownership_slot)
                except Exception:
                    outcome = "outbound_failure"
                if session_id in self._reopen_cancelled:
                    state.restore_suspended()
                    return self._non_turn(success_response(request.get("id"), {"stopReason": "cancelled"}), ownership_slot)
                if outcome != "allow":
                    return self._mcp_refusal(request, session_id, "mcp_reopen_refused", ownership_slot)
            finally:
                self._reopen_reservations.pop(session_id, None)
                self._reopen_cancelled.discard(session_id)
            admission = conversation.prepare_admission(task)
            if self._closed or state._closed or not admission.admitted:
                state.restore_suspended()
                if not admission.admitted:
                    return await self._refuse_prompt(request_id=request.get("id"), session_id=session_id,
                        conversation=conversation, reason=admission.refuse_reason or "refused", ownership_slot=ownership_slot)
                return self._mcp_refusal(request, session_id, "mcp_closing", ownership_slot)
            if idle is not None:
                idle.phase = "ACTIVE"

        assert admission.turn_seq is not None
        turn_seq = conversation.allocate_turn_seq()
        if turn_seq != admission.turn_seq:
            # allocate must match the admission probe; invariant otherwise.
            turn_seq = admission.turn_seq
            conversation._next_turn_seq = turn_seq + 1  # noqa: SLF001

        if idle is not None:
            idle.turn_seq = turn_seq
            idle.turn_epoch = idle.idle_epoch

        turn_control = TurnControl(session_id=session_id, turn_seq=turn_seq)
        turn = AcpPromptTurn(
            session_id=session_id,
            turn_seq=turn_seq,
            turn_control=turn_control,
            execution_mode=captured_mode,
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
                approvals=captured_approvals,
                generation=conversation.generation,
                sanitizer=conversation.sanitizer,
                strategy=captured_strategy or self._context_attachment.initial_strategy,
                mode=turn.execution_mode,
                checkpoint=captured_checkpoint,
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
            if self._auto_router is not None:
                try:
                    routed = await self._route_auto_turn(
                        request_id=request.get("id"),
                        session=session,
                        conversation=conversation,
                        turn=turn,
                        prompt_blocks=prompt,
                        sanitized_user_prompt=admission.sanitized_user_prompt,
                        ownership_slot=ownership_slot,
                    )
                except asyncio.CancelledError:
                    # Codex round 68: the server's teardown cancels this task mid-routing; the turn keeps its one record.
                    self._record_auto_turn(
                        session,
                        turn,
                        "abandoned" if turn.turn_control.transport_abandoned() else "cancelled",
                        outcome=None,
                        decision=turn.auto_decision,
                    )
                    raise
                if routed is not None:
                    return routed
            if admission.crosses_warning and conversation.note_warning_threshold_for_attempt(
                admission.projected_bytes
            ):
                await self._emit_capacity_notice(
                    session_id=session_id, conversation=conversation, text=self._warning_text(), is_warning=True
                )
            if attached_turn is not None and attached_turn.strategy == "sliding_window" and captured_notice:
                await self._emit_sliding_notice(session, expected_revision=captured_revision)

            if attached_turn is None:
                planner_task, conversation_envelope = self._planner_inputs(
                    conversation, admission.sanitized_user_prompt, turn.execution_mode
                )
                planning_fields: _PlanningRequestFields = {
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
                    execution_mode=turn.execution_mode,
                    planning_progress_observer=_session_progress_observer,
                    session=session,
                    halt_requested=turn.turn_control.halt_requested,
                    operation_control=turn.turn_control,
                    context_packer=attached_turn,
                    stage_receipts=session.cost_settlement.record_attempt,
                    route_binder=turn.route_binder,
                    integrity_failure=session.cost_settlement.record_integrity_failure,
                    recovery_checkin=self._recovery_checkin_for(turn, loop) if self._interactive_recovery else None,
                    turn_model=turn.turn_model,
                    model_stops=self._model_stops,
                    recovery_escalation=(
                        self._recovery_escalation_for(turn, loop)
                        if self._interactive_recovery and turn.auto_decision is not None
                        else None
                    ),
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
                    execution_mode=turn.execution_mode,
                    session=session,
                    operation_control=turn.turn_control,
                    stage_receipts=session.cost_settlement.record_attempt,
                    route_binder=turn.route_binder,
                    integrity_failure=session.cost_settlement.record_integrity_failure,
                    # An escalated turn's application runs on the model and binder it moved to (#397).
                    turn_model=turn.turn_model,
                    model_stops=self._model_stops,
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
                data=_outbound_error_payload(run_id, exc),
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
            if idle is not None and not idle.marker_seen:
                self.record_turn_commit(session_id, turn_seq, committed=False)
            # Every exit projects what this turn's receipts settled; the projection is idempotent and
            # later receipts keep updating it (Plan 12.2 Task 11; Codex CP3 ruling R2).
            self._apply_settled_cost(session, turn)
            self._report_context_faults(turn)
            # Recompute after any cancellation so settlement telemetry is exact even for a turn that
            # ends without a commit (Plan 12.2 Task 2). After transport teardown this is a no-op.
            turn.turn_control.refresh_effect_state()
            turn.turn_control.finalize_once(self._placeholder_settlement(turn))

    def _mcp_refusal(
        self, request: dict[str, Any], session_id: str, reason: str,
        ownership_slot: ResponseOwnershipSlot | None,
    ) -> ResponseEnvelope:
        self._pre_run_refused(request, session_id, reason)
        code = MCP_REOPEN_REFUSED if reason == "mcp_reopen_refused" else REQUEST_CANCELLED
        return self._non_turn(error_response(request.get("id"), JsonRpcError(
            code=code, message="client MCP unavailable" if code == MCP_REOPEN_REFUSED else "session unavailable",
            data={"reason": reason})), ownership_slot)

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
        # The fixed refusal reason persists (Codex round 13 finding 2): the operator line, the trace and the always-on
        # telemetry record, each contained on its own (correction plan v4, C7); never the prompt.
        known = reason if reason in PROMPT_REFUSAL_REASONS else "unrecognized"
        _operator_line(f"optimus.acp: prompt refused session_id={host_session_id(session_id) or 'none'} reason={known}")
        log_prompt_refusal(session_id=session_id, request_id=request_id, reason=reason, telemetry=self._failure_telemetry)
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

    async def _route_auto_turn(
        self,
        *,
        request_id: str | int | None,
        session: AcpSpecSession,
        conversation: ConversationState,
        turn: AcpPromptTurn,
        prompt_blocks: list[Any],
        sanitized_user_prompt: str,
        ownership_slot: ResponseOwnershipSlot | None,
    ) -> TurnResponseEnvelope | None:
        """Plan 12.4 Tasks 4-5: classify this Auto turn with H in its worker, resolve its model, bind that model's route
        and context limits for the whole turn, then show its notice. Every admitted Auto turn leaves exactly one routing
        record. Returns the turn's response when it stops here, or None to dispatch."""
        from optimus.acp.auto_composition import (
            AutoTurnRefused,
            ClassificationAccountingError,
            ClassifierCall,
            ClassifierHalted,
            ClassifierOutcome,
        )
        from optimus.agent.auto_contract import build_classifier_input
        from optimus.gateway.attempts import AttemptIntegrityError

        router = self._auto_router
        assert router is not None
        # Frozen before the first await: the prompt, the turn's captured mode, the last committed routed tier, and the
        # turn's own receipt sink and control for the classifier's call.
        contract = build_classifier_input(
            sanitized_user_prompt,
            mode=turn.execution_mode.value,
            attachments=_attachments_from_content_blocks(prompt_blocks),
            previous_tier=session.auto_routes[max(session.auto_routes)].tier if session.auto_routes else None,
        )
        call = ClassifierCall(
            session_id=turn.session_id,
            turn_seq=turn.turn_seq,
            run_id=turn.run_id,
            record_receipt=session.cost_settlement.record_attempt,
            integrity_failure=session.cost_settlement.record_integrity_failure,
            operation_control=turn.turn_control,
        )
        outcome: ClassifierOutcome | None
        try:
            outcome = await self._in_worker(session, turn, router.classify, contract, call)
        except ClassifierHalted:
            outcome = None  # the dispatch lease was refused: a cancel or teardown, handled below
        except (ClassificationAccountingError, AttemptIntegrityError):
            # Accounting failures never enter the classifier-failure rule (Codex round 67).
            return await self._refuse_auto_turn(
                request_id=request_id, session=session, turn=turn, reason="ACCOUNTING_INTEGRITY", outcome=None, ownership_slot=ownership_slot
            )
        except AutoTurnRefused as exc:
            return await self._refuse_auto_turn(
                request_id=request_id, session=session, turn=turn, reason=exc.code, outcome=None, ownership_slot=ownership_slot
            )
        except Exception:  # noqa: BLE001 - a failure the backend did not map takes the failure rule (v9 Design 4)
            outcome = ClassifierOutcome(tier=None, confidence_band="none", failure_kind="error")
        if turn.turn_control.transport_abandoned():
            # Finalization and late-cost handling run as for any turn; no answer call and no new notice start.
            self._record_auto_turn(session, turn, "abandoned", outcome=outcome)
            return self._turn(success_response(request_id=request_id, result={"stopReason": "cancelled"}), turn.turn_control, ownership_slot)
        if outcome is None or turn.turn_control.halt_requested():
            self._record_auto_turn(session, turn, "cancelled", outcome=outcome)
            await self._commit_turn(
                conversation=conversation,
                turn=turn,
                sanitized_user_prompt=sanitized_user_prompt,
                result=_context_stop_result(turn, _CONTEXT_CANCELLED_TEXT),
                outcome=ConversationOutcome.CANCELLED,
                completion_text=_CONTEXT_CANCELLED_TEXT,
            )
            return self._turn(success_response(request_id=request_id, result={"stopReason": "cancelled"}), turn.turn_control, ownership_slot)
        try:
            decision = router.resolve(outcome)
        except AutoTurnRefused as exc:
            return await self._refuse_auto_turn(
                request_id=request_id, session=session, turn=turn, reason=exc.code, outcome=outcome, ownership_slot=ownership_slot
            )
        if decision.failure_kind is not None:
            log_auto_route(run_id=turn.run_id, outcome="failure_rule", reason=decision.failure_kind, telemetry=self._failure_telemetry)
        turn.route_binder = router.route_policy(decision).capture(
            session_id=turn.session_id, turn_seq=turn.turn_seq, deliver_notice=self._blocking_notice(turn.session_id, asyncio.get_running_loop())
        )
        if turn.attached is not None:
            turn.attached.bind_attachment(router.attachments[decision.model_id])
        turn.auto_decision = decision
        delivered = await self._emit_auto_notice(turn, decision)
        self._record_auto_turn(session, turn, "routed", outcome=outcome, decision=decision, notice_delivered=delivered)
        return None

    async def _refuse_auto_turn(
        self,
        *,
        request_id: str | int | None,
        session: AcpSpecSession,
        turn: AcpPromptTurn,
        reason: str,
        outcome: Any,
        ownership_slot: ResponseOwnershipSlot | None,
    ) -> TurnResponseEnvelope:
        """An Auto turn refused recoverably before any answer call. Nothing is committed, so the thread stays open; any
        classifier cost already recorded still counts."""
        log_auto_route(run_id=turn.run_id, outcome="refused", reason=reason, telemetry=self._failure_telemetry)
        self._record_auto_turn(session, turn, "refused", outcome=outcome, reason=reason)
        _operator_line(
            f"optimus.acp: auto turn refused session_id={host_session_id(turn.session_id) or 'none'} turn_seq={turn.turn_seq} reason={reason}"
        )
        if not turn.turn_control.transport_abandoned():
            await self._emit_final_text(session_id=turn.session_id, text=_AUTO_REFUSAL_TEXT[reason], turn=turn)
            await self._emit_cost_alerts(turn)
        return self._turn(success_response(request_id=request_id, result={"stopReason": "end_turn"}), turn.turn_control, ownership_slot)

    async def _emit_auto_notice(self, turn: AcpPromptTurn, decision: AutoDecision) -> bool:
        """The turn's one Auto line (Plan 12.4 Task 5): live-only, never stored in the canonical history. True only once
        its send is confirmed flushed. It is informational, so an unconfirmed notice never stops the turn."""
        from optimus.acp.auto_composition import notice_text

        if turn.turn_control.transport_abandoned():
            return False
        payload = build_agent_message_chunk_notification(session_id=turn.session_id, text=notice_text(decision))
        try:
            await self._outbound.notify("session/update", payload, require_flushed=True)
        except Exception:  # noqa: BLE001 - recorded as undelivered; never fails the turn
            return False
        return True

    def _record_auto_turn(
        self,
        session: AcpSpecSession,
        turn: AcpPromptTurn,
        disposition: Literal["routed", "refused", "cancelled", "abandoned"],
        *,
        outcome: Any,
        decision: AutoDecision | None = None,
        reason: str | None = None,
        notice_delivered: bool = False,
    ) -> None:
        """The admitted Auto turn's one routing record (Plan 12.4 Task 5), through the harness's event sink. Contained: a
        telemetry failure never fails the turn. The classifier attempt's outcome is read from the turn's own receipts."""
        from datetime import UTC, datetime

        from optimus.acp.auto_composition import routing_record
        from optimus.telemetry.events import TelemetryEvent

        if turn.auto_recorded:
            return
        turn.auto_recorded = True
        sink = self._settlement_sink
        if sink is None:
            return
        attempts = [r.outcome for r in session.cost_settlement.receipts(turn.run_id) if r.stage == "classification"]
        record = routing_record(
            disposition,
            outcome=outcome,
            decision=decision,
            reason=reason,
            classifier_attempt=attempts[-1] if attempts else None,
            notice_delivered=notice_delivered,
        )
        with contextlib.suppress(Exception):
            sink(
                TelemetryEvent.auto_routing(
                    run_id=turn.run_id,
                    session_id=turn.session_id,
                    request_id=f"{turn.run_id}:auto-routing",
                    occurred_at=datetime.now(tz=UTC),
                    record=record,
                )
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
                session_id=turn.session_id,
                text=context_unavailable_text(outcome.reason, strategy, route_stopped=outcome.route_stopped),
                turn=turn,
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
        return self._context_attachment is not None or self._bound_routes

    @property
    def _bound_routes(self) -> bool:
        """Whether every planning/answer request is bound to a trusted route: one policy, or Auto's per-turn ones."""
        return self._route_policy is not None or self._auto_router is not None

    def _warning_text(self) -> str:
        if self._context_attachment is not None:
            return ATTACHED_STORAGE_WARNING_TEXT
        return ABSENT_STORAGE_WARNING_TEXT if self._bound_routes else CAPACITY_WARNING_TEXT

    async def _emit_sliding_notice(self, session: AcpSpecSession, *, expected_revision: int | None = None) -> None:
        """The first admitted turn after a switch to sliding says so, once (design spec 10).

        Live-only and best-effort: only a confirmed flush clears the obligation, so a failed or
        ambiguous send is tried again on the next admitted sliding turn; it never fails this turn."""
        revision = session.config_publication.revision if expected_revision is None else expected_revision
        payload = build_agent_message_chunk_notification(session_id=session.session_id, text=SLIDING_ACTIVE_TEXT)
        try:
            await self._outbound.notify("session/update", payload, require_flushed=True)
        except Exception:  # noqa: BLE001 - a notice failure never fails the turn
            return
        if session.config_publication.revision == revision:
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
        self.record_turn_commit(turn.session_id, turn.turn_seq, committed=None)
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
        self.record_turn_commit(turn.session_id, turn.turn_seq, committed=decision.commit)
        if turn.auto_decision is not None and outcome in (ConversationOutcome.COMPLETED, ConversationOutcome.REJECTED):
            # Plan 12.4 Task 4: only a committed, uncancelled, unfailed turn sets the next turn's previous tier.
            session = self._sessions.get(turn.session_id)
            if session is not None:
                session.auto_routes[turn.turn_seq] = turn.auto_decision
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
        conversation = session.conversation
        if conversation is None:
            raise RuntimeError("conversation is not initialized")
        self._apply_settled_cost(session, turn)
        if any(r.stage in {"planning", "answer"} for r in session.cost_settlement.receipts(turn.run_id)):
            return
        conversation.apply_planning_cost_once(turn.turn_seq, cost_usd=planning_cost, cost_complete=planning_complete)

    @staticmethod
    def _apply_settled_cost(session: AcpSpecSession, turn: AcpPromptTurn) -> None:
        """Project the turn's settled receipts (every stage) into the conversation, ordered with every
        other projection of this session. Idempotent: the turn's entry is replaced, never added to."""
        conversation = session.conversation
        if conversation is None:
            raise RuntimeError("conversation is not initialized")
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
        engine reason; the same facts in the trace and the always-on telemetry record (correction plan v4, C4).
        Best-effort: it never fails the turn, and each record is contained on its own (C7)."""
        attached = turn.attached
        if attached is None:
            return
        try:
            faults = attached.take_faults()
        except Exception:  # noqa: BLE001 - a diagnostic never fails the turn
            return
        for fault in faults:
            ended = outcome or "repack_refused"
            _operator_line(
                f"optimus.acp: context fault run_id={turn.run_id} phase={fault.phase} "
                f"category={fault.category} detail={fault.detail or 'none'} outcome={ended}"
            )
            log_context_fault(
                run_id=turn.run_id, phase=fault.phase, category=fault.category, detail=fault.detail, outcome=ended, telemetry=self._failure_telemetry
            )

    def _pre_run_refused(self, request: dict[str, Any], session_id: object, reason: str) -> None:
        """A prompt request refused before any turn (correction plan v4, C5): its fixed reason, with the session and the
        client's request id each in its own shape, in the operator line, the trace and the always-on telemetry
        record. Never the prompt or the invalid values; each record is contained on its own."""
        known = reason if reason in PRE_RUN_REFUSAL_REASONS else "unrecognized"
        _operator_line(f"optimus.acp: prompt refused session_id={host_session_id(session_id) or 'none'} reason={known}")
        log_pre_run_refusal(session_id=session_id, request_id=request.get("id"), reason=reason, telemetry=self._failure_telemetry)

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
            reading: DispatchReading | RequestReading | None
            if turn.attached is not None:
                reading = turn.attached.largest_dispatch()
            elif turn.route_binder is not None:
                reading = turn.route_binder.largest_dispatch()
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
        return await self._send_permission_request(turn, params)

    async def _send_permission_request(self, turn: AcpPromptTurn, params: dict[str, Any]) -> dict[str, Any]:
        """Send one session/request_permission, tracked so that session/cancel can end it."""
        request_task = asyncio.create_task(self._outbound.request("session/request_permission", params))
        await asyncio.sleep(0)
        if self._active_turns.get(turn.session_id) is turn:
            if hasattr(self._outbound, "requests") and self._outbound.requests:
                turn.pending_permission_request_id = self._outbound.requests[-1]["id"]
            else:
                last_outbound_request_id = getattr(self._outbound, "last_outbound_request_id", None)
                if last_outbound_request_id is not None:
                    turn.pending_permission_request_id = last_outbound_request_id
            if turn.turn_control.halt_requested() and turn.pending_permission_request_id is not None:
                # A session/cancel that ran before the id was recorded could not end this request.
                self._outbound.cancel_request(turn.pending_permission_request_id, {"outcome": {"outcome": "cancelled"}})
        return await request_task

    def _recovery_checkin_for(self, turn: AcpPromptTurn, loop: asyncio.AbstractEventLoop) -> PlanningCheckInCallback:
        """The planning worker's thread-safe bridge to a recovery check-in (Plan 12.3, Design 5). It blocks
        that worker, not the event loop; session/cancel and teardown end the pending request."""

        async def ask(checkin: PlanningCheckIn) -> CheckInDecision:
            params = build_loop_checkin_params(
                session_id=turn.session_id, tool_call_id=new_tool_call_id(), text=checkin.text, run_id=turn.run_id
            )
            try:
                response = await self._send_permission_request(turn, params)
            except Exception:  # noqa: BLE001 - a client that cannot answer ends the turn recoverably
                return CheckInDecision.UNAVAILABLE
            finally:
                turn.pending_permission_request_id = None
            return checkin_decision(response)

        def recovery_checkin(checkin: PlanningCheckIn) -> CheckInDecision:
            control = turn.turn_control
            if control.halt_requested():
                return CheckInDecision.STOP
            pending = asyncio.run_coroutine_threadsafe(ask(checkin), loop)
            # Transport teardown cancels the turn's permission handle; by session close the turn may have
            # left the active map, so only this releases a pending check-in (Codex Checkpoint A, 1).
            control.set_permission_handle(pending)
            try:
                if control.halt_requested():
                    pending.cancel()  # teardown ran before the handle was registered
                return pending.result()
            except concurrent.futures.CancelledError:
                return CheckInDecision.STOP
            finally:
                control.set_permission_handle(None)

        return recovery_checkin

    def _recovery_escalation_for(self, turn: AcpPromptTurn, loop: asyncio.AbstractEventLoop) -> PlanningEscalationCallback:
        """The planning worker's bridge to an Auto turn's one escalation (#397, ADR-009 rung 2): the target from
        configuration, a best-effort notice, then the switch of the turn's binder, meter and context limits. It blocks
        that worker, never the event loop, and a halt wins before the target, after the notice and before the switch."""
        from optimus.acp.auto_composition import escalation_notice_text

        router = self._auto_router
        assert router is not None
        control = turn.turn_control

        def notify(text: str) -> bool:
            # Informational (ADR-005): bounded by the notice flush timeout and cancelled by teardown like a pending
            # check-in; a timeout, failure or cancel is only recorded as undelivered.
            payload = build_agent_message_chunk_notification(session_id=turn.session_id, text=text)
            pending = asyncio.run_coroutine_threadsafe(self._outbound.notify("session/update", payload, require_flushed=True), loop)
            # Teardown cancels the control's handle and session/cancel the turn's, as for a pending check-in.
            control.set_permission_handle(pending)
            turn.permission_handle = pending
            try:
                if control.halt_requested():
                    pending.cancel()
                pending.result(timeout=_NOTICE_FLUSH_TIMEOUT_SECONDS)
            except (Exception, concurrent.futures.CancelledError):  # noqa: BLE001
                pending.cancel()
                return False
            finally:
                control.set_permission_handle(None)
                turn.permission_handle = None
            return True

        def recovery_escalation(move: PlanningEscalation) -> EscalationGrant | EscalationRefusal:
            current = turn.turn_model
            if control.halt_requested():
                return EscalationRefusal.HALTED
            # Every fallible part is prepared before anything is published, so a failure leaves the turn as it was and
            # goes to the check-in with its cause recorded.
            try:
                target = None if current is None else router.escalation_target(current)
                if current is None or target is None:
                    return EscalationRefusal.NO_TARGET
                binder = router.escalation_route(target).capture(
                    session_id=turn.session_id, turn_seq=turn.turn_seq, deliver_notice=self._blocking_notice(turn.session_id, loop)
                )
                attachment = None if turn.attached is None else router.attachments[target]
                text = escalation_notice_text(router.snapshot, from_model=current, to_model=target, what=move.what)
            except Exception as exc:  # noqa: BLE001 - recorded with its class facts, never its text
                log_auto_route(run_id=turn.run_id, outcome="escalation_failed", reason="error", telemetry=self._failure_telemetry, failure=exc)
                _operator_line(
                    f"optimus.acp: auto escalation failed session_id={host_session_id(turn.session_id) or 'none'} "
                    f"turn_seq={turn.turn_seq} error={type(exc).__name__}"
                )
                return EscalationRefusal.FAILED
            delivered = not control.transport_abandoned() and notify(text)
            if control.halt_requested():
                return EscalationRefusal.HALTED
            if turn.route_binder is not None:
                binder.adopt_readings(turn.route_binder)
            if turn.attached is not None and attachment is not None:
                turn.attached.escalate_attachment(attachment)
            turn.route_binder, turn.escalated_model = binder, target
            return EscalationGrant(model_id=target, route_binder=binder, notice_delivered=delivered)

        return recovery_escalation

    def _runner_runtime_kwargs(
        self,
        *,
        session: AcpSpecSession,
        execution_mode: ExecutionMode | None = None,
        planning_progress_observer: Any | None = None,
        halt_requested: Any | None = None,
        operation_control: Any | None = None,
        context_packer: Any | None = None,
        stage_receipts: Any | None = None,
        route_binder: Any | None = None,
        integrity_failure: Any | None = None,
        recovery_checkin: Any | None = None,
        turn_model: str | None = None,
        model_stops: Any | None = None,
        recovery_escalation: Any | None = None,
    ) -> dict[str, Any]:
        """Pass client-MCP runtime kwargs only when the runner accepts them."""
        kwargs: dict[str, Any] = {}
        try:
            parameters: Mapping[str, inspect.Parameter] = inspect.signature(self._runner.run).parameters
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
        if recovery_checkin is not None:
            _maybe("recovery_checkin", recovery_checkin)
        if turn_model is not None:
            # A runner that cannot take it still sends its launch model, which its bound-route check then refuses.
            _maybe("turn_model", turn_model)
        if model_stops is not None:
            _maybe("model_stops", model_stops)
        if recovery_escalation is not None:
            _maybe("recovery_escalation", recovery_escalation)
        chat = (execution_mode or session.execution_mode) is ExecutionMode.CHAT
        _maybe("client_mcp_service", None if chat else _client_mcp_service(session))
        _maybe("mcp_permission_broker", None if chat else self._mcp_permission_broker_for(session))
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
                    data=_tool_call_payload(session_id, tool_call, tool_call_id, payload),
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
        "PLANNING_GATEWAY_REGISTRY_MISMATCH",
        "PLANNING_INPUT_CAPACITY_EXCEEDED",
        "PLANNING_NOTICE_UNDELIVERED",
        "PLANNING_REPEATED_READ_REQUEST",
        "PLANNING_REPEATED_MCP_REQUEST",
        "PLANNING_ACTION_CYCLE",
        "PLANNING_NO_PROGRESS",
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
    if result.stop_reason in TEST_STOP_REASONS.values():
        return result.output_text  # it names the stopped TEST and any change already applied (Plan 12.3)
    if result.stop_reason == "EDIT_NOT_APPLICABLE":
        return result.output_text  # the closed code and that nothing was written (#407)
    if result.stop_reason == WRITE_LINE_ENDINGS_MIXED:
        return result.output_text  # the refused WRITE and the TESTs that did not run (#410)
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


def checkin_decision(response: Any) -> CheckInDecision:
    """A check-in answer: only its own options count. A cancelled request is Stop (the turn's halt then
    wins); anything else is unrecognised and ends the turn recoverably (Plan 12.3, Design 5)."""
    outcome = response.get("outcome") if isinstance(response, dict) else None
    if isinstance(outcome, dict) and outcome.get("outcome") == "cancelled":
        return CheckInDecision.STOP
    if isinstance(outcome, dict) and outcome.get("outcome") == "selected":
        option = outcome.get("optionId")
        if option == LOOP_CONTINUE_OPTION_ID:
            return CheckInDecision.CONTINUE
        if option == LOOP_STOP_OPTION_ID:
            return CheckInDecision.STOP
    return CheckInDecision.INVALID


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


def _attachments_from_content_blocks(blocks: list[Any]) -> list[tuple[str, int]]:
    """The Auto classifier contract's attachment summary (Plan 12.4 Design 3): each resource or resource link's URI and
    size in bytes. Only sizes are taken, never contents; a link without a stated size counts as zero."""
    items: list[tuple[str, int]] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "resource_link" and isinstance(block.get("uri"), str):
            size = block.get("size")
            items.append((block["uri"], size if type(size) is int and size >= 0 else 0))
        elif block.get("type") == "resource" and isinstance(block.get("resource"), dict):
            resource = block["resource"]
            if isinstance(resource.get("uri"), str):
                text, blob = resource.get("text"), resource.get("blob")
                size = len(text.encode("utf-8")) if isinstance(text, str) else len(blob) * 3 // 4 if isinstance(blob, str) else 0
                items.append((resource["uri"], size))
    return items


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
    if result.stop_reason in _PLANNING_TERMINAL_STOP_REASONS or result.stop_reason in TEST_STOP_REASONS.values():
        return "end_turn"
    if result.stop_reason in ("PLAN_NOT_FOUND_OR_EXPIRED", WRITE_LINE_ENDINGS_MIXED):
        return "end_turn"
    return "refusal"


def _outbound_error_payload(run_id: str, exc: AcpOutboundError) -> Callable[[], dict[str, object]]:
    def payload() -> dict[str, object]:
        return {"run_id": run_id, "code": exc.code, "message": exc.message}

    return payload


def _tool_call_payload(session_id: str, tool_call: AgentToolCall, tool_call_id: str, payload: Mapping[str, Mapping[str, object]]) -> Callable[[], dict[str, object]]:
    def supply() -> dict[str, object]:
        return {
        "session_id": session_id,
        "tool_call_id": tool_call_id,
        "session_update": payload["update"]["sessionUpdate"],
        "tool_name": tool_call.tool_name,
        "status": payload["update"]["status"],
        }

    return supply
