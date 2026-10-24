from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from optimus.agent.directives import (
    EDIT_END_MARKER,
    EDIT_OLD_MARKER,
    AgentDirectiveParseError,
    AgentPlanDirectives,
    parse_agent_plan,
    parse_mcp_call_line,
    parse_mcp_list_line,
)
from optimus.agent.models import AgentMcpToolOutput, AgentToolCall, ContextPacker
from optimus.agent.operation_control import TurnOperationControl
from optimus.agent.prompts import build_multi_turn_planner_input, format_mcp_evidence_envelope
from optimus.agent.tools import AgentToolbox
from optimus.agent.workspace_context import DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES
from optimus.gateway.attempts import (
    ROUTE_STOPPED_NO_RETRY,
    AttemptIntegrityError,
    ProviderAttempt,
    attempts_from_failure,
    attempts_from_response,
    first_error,
    gateway_registry_mismatch_text,
    is_gateway_registry_mismatch,
    is_input_capacity_refusal,
    is_preflight_refusal,
    stops_experimental_route,
)
from optimus.gateway.errors import GatewayError
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.guardrails.pre_tool import PreToolGuard
from optimus.loops.completion import DeterministicCompletionEvaluator
from optimus.loops.controller import GoalLoopController, GoalLoopResult
from optimus.loops.detector import LoopDetection, LoopDetector, LoopSignalKind, LoopThresholds
from optimus.loops.ledger import InMemoryProgressLedger
from optimus.loops.models import IterationOutcome, IterationState, LoopBudgetPolicy, LoopStopReason, LoopToolExecutorProtocol
from optimus.loops.signals import LoopStep, McpResults, ReadCoverage, ReadResult, mcp_step, parse_failure_step, read_step
from optimus.retry.policy import RetryController, RetryPolicy
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.state import RuntimeContext
from optimus.telemetry.events import TelemetryEvent
from optimus.telemetry.subjects import sanitize_workspace_text
from optimus_security.failure_facts import bounded

if TYPE_CHECKING:
    from optimus.gateway.route_binding import BoundRequest, TurnRouteBinder


PlanningGatewayUsageCallback = Callable[[GatewayUsage, int, int], None]
# (planning turn, wire attempt, every provider attempt of that request, the route identity it was
# bound to or None when unbound): one call per host request, known or unknown (Codex CP3 ruling R3/R4).
# (planning turn, wire attempt, attempts, route identity, the request's error if it failed: diagnostic only)
PlanningAttemptCallback = Callable[[int, int, tuple[ProviderAttempt, ...], Any, BaseException | None], None]
# A request whose required notice was not delivered: never sent, so it certainly cost nothing.
_NOT_SENT = ProviderAttempt(number=1, outcome="not_sent", cost_usd=Decimal("0"))

PLANNING_OBSERVATION_MAX_BYTES = 4 * 1024
PLANNING_NEW_READ_MAX_BYTES = 12 * 1024
_PLACEHOLDER_SOURCE_SHA256 = "0" * 64

_OBSERVE_DIRECTIVE = re.compile(r"^OBSERVE:\s*(.*)$", re.DOTALL)
_READ_RANGE_DIRECTIVE = re.compile(r"^READ:\s+(\S+)#bytes=(\d+):(\d+)\s*$")
_REFUSE_DIRECTIVE = re.compile(r"^REFUSE:\s*(.+)$")
_WRITE_DIRECTIVE = re.compile(r"^WRITE\s+(\S+)\s*$")
_DIRECTIVE_PREFIXES = ("OBSERVE:", "READ:", "WRITE", "TEST", "REFUSE:", "PLAN:", "MCP_LIST", "MCP_CALL")
_REFUSE_REASON_DIRECTIVE_PREFIX = re.compile(
    r"^(?:OBSERVE:|READ:|WRITE(?:\s|$)|TEST\s|PLAN:|CONTENT:|END_CONTENT|MCP_LIST\s|MCP_CALL\s)"
)
_BULLET_PREFIXES = ("- ", "* ", "+ ")


class PlanningTurnKind(StrEnum):
    READ_MORE = "READ_MORE"
    MCP_TOOL = "MCP_TOOL"
    FINAL_PLAN = "FINAL_PLAN"
    REFUSE = "REFUSE"


class PlanningTurnParseError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


# Every reason a planning turn fails to parse (#388). Trace records carry only the code, never the
# message, which may quote the reply.
PLANNING_TURN_PARSE_CODES = frozenset(
    {
        "GRAMMAR_UNRECOGNIZED",
        "REFUSE_NOT_ONE_LINE",
        "REFUSE_TOO_LONG",
        "REFUSE_HAS_DIRECTIVE_PREFIX",
        "MCP_MIXED_DIRECTIVES",
        "MCP_NOT_EXACTLY_ONE",
        "MCP_LIST_INVALID",
        "MCP_CALL_INVALID",
        "MCP_DIRECTIVE_MALFORMED",
        "OBSERVE_MULTIPLE",
        "READ_RANGE_EMPTY",
        "INTERMEDIATE_UNSUPPORTED_DIRECTIVE",
        "INTERMEDIATE_UNRECOGNIZED_CONTENT",
        "INTERMEDIATE_REQUIRES_OBSERVE",
        "INTERMEDIATE_REQUIRES_READ",
        "OBSERVATION_TOO_LARGE",
        "READ_PATH_NOT_RELATIVE",
        "READ_RANGES_DUPLICATE",
        "READ_RANGES_OVERLAP",
    }
)
_MCP_AUTHORIZATION_OUTCOMES = frozenset({"ALLOW", "BLOCK", "HOLD"})

# #403 (option B, Codex round 44): the fixed notice the next turn carries after an unparseable one, one per closed
# code. Fixed text only: never the reply, the parse message, a path or exception text. Strict parsing is unchanged.
PLANNING_PARSE_FEEDBACK: dict[str, str] = {
    "GRAMMAR_UNRECOGNIZED": (
        "it matched no planning-turn form. Reply with exactly one form: an intermediate turn (one OBSERVE: line, "
        "then ranged READ: lines), one MCP_LIST or MCP_CALL line, a final plan, or a one-line REFUSE:."
    ),
    "REFUSE_NOT_ONE_LINE": "a REFUSE: reply must be a single non-empty line.",
    "REFUSE_TOO_LONG": "a REFUSE: reason must be at most 512 UTF-8 bytes.",
    "REFUSE_HAS_DIRECTIVE_PREFIX": "a REFUSE: reason must not contain directive prefixes.",
    "MCP_MIXED_DIRECTIVES": "an MCP_LIST or MCP_CALL line must be the whole reply, never mixed with other directives.",
    "MCP_NOT_EXACTLY_ONE": "an MCP turn must contain exactly one MCP_LIST or MCP_CALL line.",
    "MCP_LIST_INVALID": "the MCP_LIST line was malformed; use MCP_LIST <server>.",
    "MCP_CALL_INVALID": "the MCP_CALL line was malformed; use MCP_CALL <server> <tool> <canonical-json-object>.",
    "MCP_DIRECTIVE_MALFORMED": "the MCP directive was malformed; use MCP_LIST <server> or MCP_CALL <server> <tool> <json>.",
    "OBSERVE_MULTIPLE": "an intermediate turn must contain exactly one OBSERVE: line.",
    "READ_RANGE_EMPTY": "each READ: range must end after it starts.",
    "INTERMEDIATE_UNSUPPORTED_DIRECTIVE": "an intermediate turn may contain only one OBSERVE: line and ranged READ: lines.",
    "INTERMEDIATE_UNRECOGNIZED_CONTENT": (
        "an intermediate turn may contain only one OBSERVE: line and ranged READ: lines, with no other text."
    ),
    "INTERMEDIATE_REQUIRES_OBSERVE": "an intermediate turn needs an OBSERVE: line before its READ: lines.",
    "INTERMEDIATE_REQUIRES_READ": "an intermediate turn needs at least one ranged READ: line after its OBSERVE: line.",
    "OBSERVATION_TOO_LARGE": "the OBSERVE: note and its READ: requests exceeded the observation budget; keep the note shorter.",
    "READ_PATH_NOT_RELATIVE": "each READ: path must be workspace-relative.",
    "READ_RANGES_DUPLICATE": "the READ: ranges must not repeat.",
    "READ_RANGES_OVERLAP": "the READ: ranges must not overlap.",
}


def _correction_notice(code: str | None) -> str:
    """The next turn's notice for the previous turn's parse-failure code, or "" when that turn parsed (#403)."""
    return PLANNING_PARSE_FEEDBACK[code] if code is not None else ""


class PlanningReadError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class PlanningEvidenceBudgetError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class _PlanningGatewayInvocationError(RuntimeError):
    """Internal: typed planning stop raised from _invoke_planning_gateway."""

    def __init__(self, stop_reason: str, *, reported_cost_usd: Decimal) -> None:
        self.stop_reason = stop_reason
        self.reported_cost_usd = reported_cost_usd
        super().__init__(stop_reason)


class PlanningLoopPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_planning_turns: int = Field(default=3, ge=1)
    max_wall_clock_minutes: int = Field(default=30, ge=1)
    # Plan 12.3 (ADR-024, D2): interactive recovery only. Continue grants these steps and a fresh
    # max_wall_clock_minutes; headless runs keep the hard caps above.
    loop_thresholds: LoopThresholds = Field(default_factory=LoopThresholds)
    continue_grant_steps: int = Field(default=3, ge=1)

    def to_loop_budget_policy(self, *, max_cost_usd: Decimal | None = None) -> LoopBudgetPolicy:
        """The loop's finite work controls; a dollar bound only for an evaluation caller's explicit cap
        (Plan 12.2 Task 11). A product planning loop has none."""
        if max_cost_usd is not None and max_cost_usd <= Decimal("0"):
            raise ValueError("an evaluation cap must be positive before constructing a planning loop")
        return LoopBudgetPolicy(
            max_iterations=self.max_planning_turns,
            max_budget_usd=max_cost_usd,
            max_wall_clock_minutes=self.max_wall_clock_minutes,
            repeated_failure_limit=2,
        )


class PlanningObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    start_byte: int = Field(ge=0)
    end_byte: int = Field(ge=1)
    source_sha256: str = Field(min_length=1)
    observation_text: str


class PlanningReadRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    start_byte: int = Field(ge=0)
    end_byte: int = Field(ge=1)


class PlanningReadEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    start_byte: int = Field(ge=0)
    end_byte: int = Field(ge=1)
    source_sha256: str = Field(min_length=1)
    range_text: str


class PlanningEvidenceEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    byte_size: int = Field(ge=0)


class PlanningTurnDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: PlanningTurnKind
    observation_text: str | None = None
    read_requests: tuple[PlanningReadRequest, ...] = ()
    failure_signature: str | None = None
    plan_text: str | None = None
    directives: AgentPlanDirectives | None = None
    reason: str | None = None
    mcp_operation: str | None = None
    mcp_server: str | None = None
    mcp_tool: str | None = None
    mcp_arguments: dict[str, object] | None = None


class PlanningLoopResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    stop_reason: str | None = None
    settled_turns: int = Field(default=0, ge=0)
    total_cost_usd: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    cost_complete: bool = True
    unknown_cost_attempt_count: int = Field(default=0, ge=0)
    gateway_request_ids: tuple[str, ...] = ()
    plan_text: str | None = None
    plan_hash: str | None = None
    provider: str | None = None
    directives: AgentPlanDirectives | None = None
    corrective_text: str = ""
    refusal_reason: str | None = None
    evidence_metadata: dict[str, str] = Field(default_factory=dict)
    # Path -> sha256 of the raw evidence visible on the final plan's turn; an EDIT is bound to it (#407).
    evidence_sha256s: dict[str, str] = Field(default_factory=dict)


class PlanningProgressEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    session_id: str | None = None
    settled_turn: int = Field(ge=1)
    max_planning_turns: int = Field(ge=1)
    read_request_count: int = Field(default=0, ge=0)
    read_identities: tuple[str, ...] = ()
    source_sha256s: tuple[str, ...] = ()
    read_byte_counts: tuple[int, ...] = ()
    total_cost_usd: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    cost_complete: bool = True
    unknown_cost_attempt_count: int = Field(default=0, ge=0)
    # An evaluation caller's remaining explicit cap; None on every product run, which has no dollar bound
    # (Plan 12.2 Task 11).
    remaining_budget_usd: Decimal | None = Field(default=None, ge=Decimal("0"))
    gateway_request_ids: tuple[str, ...] = ()
    wire_retry_count: int = Field(default=0, ge=0)
    stop_reason: str | None = None
    """Set only on the final, settling event for a run; None on intermediate
    READ_MORE progress events."""

    @model_validator(mode="after")
    def check_read_telemetry_alignment(self) -> "PlanningProgressEvent":
        n = self.read_request_count
        if len(self.read_identities) != n:
            raise ValueError(
                f"read_identities length {len(self.read_identities)} "
                f"does not match read_request_count {n}"
            )
        if len(self.source_sha256s) != n:
            raise ValueError(
                f"source_sha256s length {len(self.source_sha256s)} "
                f"does not match read_request_count {n}"
            )
        if len(self.read_byte_counts) != n:
            raise ValueError(
                f"read_byte_counts length {len(self.read_byte_counts)} "
                f"does not match read_request_count {n}"
            )
        return self


def planning_read_telemetry_fields(
    read_evidence: tuple[PlanningReadEvidence, ...],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[int, ...]]:
    """Derive aligned telemetry tuples from a canonical ordering of read evidence.

    Returns (read_identities, source_sha256s, read_byte_counts) where each
    position corresponds to the same read operation. The ordering is canonical
    (path, start_byte, end_byte, source_sha256) so that telemetry is
    deterministic regardless of read execution order.
    """
    ordered = tuple(
        sorted(
            read_evidence,
            key=lambda item: (item.path, item.start_byte, item.end_byte, item.source_sha256),
        )
    )
    return (
        tuple(f"{item.path}#bytes={item.start_byte}:{item.end_byte}" for item in ordered),
        tuple(item.source_sha256 for item in ordered),
        tuple(item.end_byte - item.start_byte for item in ordered),
    )


PlanningProgressObserver = Callable[[PlanningProgressEvent], None]


class CheckInDecision(StrEnum):
    CONTINUE = "continue"
    STOP = "stop"
    UNAVAILABLE = "unavailable"  # the client could not be asked
    INVALID = "invalid"  # an unrecognised answer: treated as Stop, with a recoverable explanation


class PlanningCheckIn(BaseModel):
    """What the user is asked at a recovery check-in (Plan 12.3, Design 5). Continue grants only a
    fresh planning allowance: never a WRITE or TEST approval, which keeps its own request."""

    model_config = ConfigDict(frozen=True)

    cause: str
    planning_steps: int = Field(ge=1)
    text: str
    plan_waiting: bool = False
    refusal_waiting: bool = False


# Blocks the planning worker until the user answers; nothing runs meanwhile (ADR-009 requirement 3).
PlanningCheckInCallback = Callable[[PlanningCheckIn], CheckInDecision]
_TURN_LIMIT, _WALL_CLOCK = "TURN_LIMIT", "WALL_CLOCK"
_NUDGE_STEP = object()  # the next recovery move is one budgeted nudge step, not a check-in


def pack_planning_evidence(
    *,
    observations: tuple[PlanningObservation, ...],
    current_reads: tuple[PlanningReadEvidence, ...],
) -> PlanningEvidenceEnvelope:
    """
    Packs planning evidence, including observations and current read evidence, into an envelope while ensuring
    that size constraints for serialized data are not exceeded.

    This function validates that the serialized forms of observations, current reads, and their combination
    do not surpass the predefined byte budgets. If any validation fails, an appropriate
    PlanningEvidenceBudgetError is raised.

    :param observations: A tuple containing instances of PlanningObservation, representing
                         planning-related observations to be serialized and included in
                         the evidence envelope.
    :param current_reads: A tuple containing instances of PlanningReadEvidence, representing
                          current read-based evidence to be serialized and included in
                          the evidence envelope.
    :return: A PlanningEvidenceEnvelope object holding the serialized and validated planning
             evidence, including its combined text and computed byte size.
    :rtype: PlanningEvidenceEnvelope
    :raises PlanningEvidenceBudgetError: Raised under the following conditions:
        - Serialized planning observations exceed the carryover budget.
        - Serialized planning read evidence exceeds the current-turn budget.
        - Combined serialized evidence exceeds the workspace context budget.
    """
    observation_text = "".join(_serialize_planning_observation(observation) for observation in observations)
    observation_bytes = len(observation_text.encode("utf-8"))
    if observation_bytes > PLANNING_OBSERVATION_MAX_BYTES:
        raise PlanningEvidenceBudgetError(
            "PLANNING_OBSERVATION_BUDGET_EXHAUSTED",
            "serialized planning observations exceed the carryover budget",
        )

    current_read_text = "".join(_serialize_planning_read_evidence(evidence) for evidence in current_reads)
    current_read_bytes = len(current_read_text.encode("utf-8"))
    if current_read_bytes > PLANNING_NEW_READ_MAX_BYTES:
        raise PlanningEvidenceBudgetError(
            "PLANNING_READ_BUDGET_EXHAUSTED",
            "serialized planning read evidence exceeds the current-turn budget",
        )

    combined_text = observation_text + current_read_text
    combined_bytes = len(combined_text.encode("utf-8"))
    if combined_bytes > DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES:
        raise PlanningEvidenceBudgetError(
            "PLANNING_READ_BUDGET_EXHAUSTED",
            "combined planning evidence exceeds the workspace context budget",
        )

    return PlanningEvidenceEnvelope(text=combined_text, byte_size=combined_bytes)


def verify_planning_source_hash(*, workspace_root: Path, path: str, expected_sha256: str) -> None:
    target = _resolve_workspace_file(workspace_root=workspace_root, relative_path=path)
    if not target.is_file():
        raise PlanningReadError("PLANNING_READ_FILE_NOT_FOUND", f"file not found: {path}")
    actual_sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual_sha256 != expected_sha256:
        raise PlanningReadError(
            "PLANNING_READ_SOURCE_CHANGED",
            f"source hash changed for {path}",
        )


def max_planning_observation_text_bytes(read_requests: tuple[PlanningReadRequest, ...]) -> int:
    if not read_requests:
        return PLANNING_OBSERVATION_MAX_BYTES
    header_sum = planning_observation_carryover_bytes(
        observation_text="",
        read_requests=read_requests,
    )
    remaining = PLANNING_OBSERVATION_MAX_BYTES - header_sum
    if remaining <= 0:
        return 0
    return remaining // len(read_requests)


def planning_observation_carryover_bytes(
    *,
    observation_text: str,
    read_requests: tuple[PlanningReadRequest, ...],
    source_sha256: str = _PLACEHOLDER_SOURCE_SHA256,
) -> int:
    return sum(
        planning_observation_serialized_bytes(
            PlanningObservation(
                path=request.path,
                start_byte=request.start_byte,
                end_byte=request.end_byte,
                source_sha256=source_sha256,
                observation_text=observation_text,
            )
        )
        for request in read_requests
    )


def observations_for_intermediate_turn(
    *,
    observation_text: str,
    read_requests: tuple[PlanningReadRequest, ...],
    source_sha256s: tuple[str, ...] | None = None,
) -> tuple[PlanningObservation, ...]:
    if source_sha256s is None:
        hashes = (_PLACEHOLDER_SOURCE_SHA256,) * len(read_requests)
    elif len(source_sha256s) != len(read_requests):
        raise ValueError("source_sha256s must align with read_requests")
    else:
        hashes = source_sha256s
    return tuple(
        PlanningObservation(
            path=request.path,
            start_byte=request.start_byte,
            end_byte=request.end_byte,
            source_sha256=source_hash,
            observation_text=observation_text,
        )
        for request, source_hash in zip(read_requests, hashes, strict=True)
    )


def observations_from_read_evidence(
    *,
    observation_text: str,
    read_evidence: tuple[PlanningReadEvidence, ...],
) -> tuple[PlanningObservation, ...]:
    return tuple(
        PlanningObservation(
            path=evidence.path,
            start_byte=evidence.start_byte,
            end_byte=evidence.end_byte,
            source_sha256=evidence.source_sha256,
            observation_text=observation_text,
        )
        for evidence in read_evidence
    )


def planning_observation_serialized_bytes(observation: PlanningObservation) -> int:
    return len(_serialize_planning_observation(observation).encode("utf-8"))


def _serialize_planning_observation(observation: PlanningObservation) -> str:
    return (
        "OBS_RECORD "
        f"path={observation.path} "
        f"bytes={observation.start_byte}:{observation.end_byte} "
        f"sha256={observation.source_sha256}\n"
        f"{observation.observation_text}\n"
        "END_OBS_RECORD\n"
    )


def _serialize_planning_read_evidence(evidence: PlanningReadEvidence) -> str:
    return (
        "READ_BLOCK "
        f"path={evidence.path} "
        f"bytes={evidence.start_byte}:{evidence.end_byte} "
        f"sha256={evidence.source_sha256}\n"
        f"{evidence.range_text}\n"
        "END_READ_BLOCK\n"
    )


def _resolve_workspace_file(*, workspace_root: Path, relative_path: str) -> Path:
    root = workspace_root.resolve()
    candidate = Path(relative_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise PlanningReadError("PLANNING_READ_INVALID_PATH", "READ path must be workspace-relative")
    return (root / candidate).resolve()


_RANGED_READ_LINE = re.compile(r"^READ:\s+\S+#bytes=\d+:\d+\s*$")
_FINAL_READ_DIRECTIVE = re.compile(r"^READ\s+(\S+)\s*$")
_FINAL_TEST_DIRECTIVE = re.compile(r"^TEST\s+(.+)$")


def parse_planning_turn(text: str) -> PlanningTurnDecision:
    stripped = text.strip()
    if not stripped:
        raise PlanningTurnParseError("GRAMMAR_UNRECOGNIZED", "no recognized planning-turn grammar")

    refuse_decision = _try_parse_refuse(stripped)
    if refuse_decision is not None:
        return refuse_decision
    if stripped.startswith("REFUSE:"):
        raise PlanningTurnParseError("REFUSE_NOT_ONE_LINE", "REFUSE reason must be one non-empty line")

    mcp_decision = _try_parse_mcp_turn(stripped)
    if mcp_decision is not None:
        return mcp_decision

    surface_lines = _directive_surface_lines(stripped)
    if _surface_has_observe(surface_lines):
        return _parse_intermediate_turn(stripped)

    final_decision = _try_parse_final_plan(text)
    if final_decision is not None:
        return final_decision

    if _surface_has_ranged_read(surface_lines):
        return _parse_intermediate_turn(stripped)

    raise PlanningTurnParseError("GRAMMAR_UNRECOGNIZED", "no recognized planning-turn grammar")


def _try_parse_mcp_turn(text: str) -> PlanningTurnDecision | None:
    lines = [line.strip() for line in _outside_edit_blocks(text.splitlines()) if line.strip()]
    if not lines:
        return None
    if not (lines[0].startswith("MCP_LIST") or lines[0].startswith("MCP_CALL")):
        # If MCP appears mixed later with other content, reject below when surface has MCP.
        if any(line.startswith("MCP_LIST") or line.startswith("MCP_CALL") for line in lines):
            raise PlanningTurnParseError(
                "MCP_MIXED_DIRECTIVES", "MCP directives must be a single intermediate tool request"
            )
        return None
    if len(lines) != 1:
        raise PlanningTurnParseError(
            "MCP_NOT_EXACTLY_ONE", "MCP turn must contain exactly one MCP_LIST or MCP_CALL directive"
        )

    try:
        list_directive = parse_mcp_list_line(lines[0])
    except AgentDirectiveParseError as exc:
        raise PlanningTurnParseError("MCP_LIST_INVALID", str(exc)) from exc
    if list_directive is not None:
        return PlanningTurnDecision(
            kind=PlanningTurnKind.MCP_TOOL,
            mcp_operation="list",
            mcp_server=list_directive.server,
        )

    try:
        call_directive = parse_mcp_call_line(lines[0])
    except AgentDirectiveParseError as exc:
        raise PlanningTurnParseError("MCP_CALL_INVALID", str(exc)) from exc
    if call_directive is not None:
        return PlanningTurnDecision(
            kind=PlanningTurnKind.MCP_TOOL,
            mcp_operation="call",
            mcp_server=call_directive.server,
            mcp_tool=call_directive.tool,
            mcp_arguments=call_directive.arguments,
        )

    if lines[0].startswith("MCP_LIST") or lines[0].startswith("MCP_CALL"):
        raise PlanningTurnParseError("MCP_DIRECTIVE_MALFORMED", "malformed MCP directive")
    return None


def _outside_edit_blocks(lines: list[str]) -> list[str]:
    """The lines outside EDIT blocks: OLD/NEW bodies are opaque content, never directives (#407)."""
    outside: list[str] = []
    inside = False
    for line in lines:
        marker = line.strip()
        if inside:
            inside = marker != EDIT_END_MARKER
        elif marker == EDIT_OLD_MARKER:
            inside = True
        else:
            outside.append(line)
    return outside


def _directive_surface_lines(text: str) -> tuple[str, ...]:
    lines = _outside_edit_blocks(text.splitlines())
    surface_lines: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        normalized = _normalize_directive_surface_line(line)
        if _WRITE_DIRECTIVE.match(normalized) is not None:
            index += 1
            while index < len(lines) and not _is_final_directive_line(lines[index]):
                index += 1
            continue
        stripped = line.strip()
        if stripped:
            surface_lines.append(stripped)
        index += 1
    return tuple(surface_lines)


def _normalize_directive_surface_line(line: str) -> str:
    normalized = line.strip()
    while True:
        for prefix in _BULLET_PREFIXES:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :].lstrip()
                break
        else:
            return normalized


def _is_final_directive_line(line: str) -> bool:
    normalized = _normalize_directive_surface_line(line)
    return (
        _FINAL_READ_DIRECTIVE.match(normalized) is not None
        or _WRITE_DIRECTIVE.match(normalized) is not None
        or _FINAL_TEST_DIRECTIVE.match(normalized) is not None
        or normalized.startswith("MCP_LIST ")
        or normalized.startswith("MCP_CALL ")
        or normalized == "MCP_LIST"
        or normalized == "MCP_CALL"
    )


def _surface_has_observe(surface_lines: tuple[str, ...]) -> bool:
    return any(line.startswith("OBSERVE:") for line in surface_lines)


def _surface_has_ranged_read(surface_lines: tuple[str, ...]) -> bool:
    return any(_RANGED_READ_LINE.match(line) is not None for line in surface_lines)


def _parse_intermediate_turn(text: str) -> PlanningTurnDecision:
    """
    Parses an intermediate planning turn from the provided text and extracts directives for
    observation and read requests. Each directive is validated for correctness and supported format.
    The function ensures that there is exactly one OBSERVE directive, at least one ranged READ directive,
    and validates that their combined size does not exceed the observation byte budget. Additionally,
    it ensures that read ranges do not overlap.

    :param text: The input text representing the intermediate planning turn, containing directives
        for observation and read requests.
    :type text: str

    :raises PlanningTurnParseError: Raised if:
        - Multiple OBSERVE directives are present in the input.
        - No OBSERVE directive is found.
        - No ranged READ directive is present.
        - READ range end byte is less than or equal to the start byte.
        - Any unsupported or unrecognized directive is found in the input.
        - The observation size exceeds the allowed planning observation byte budget.
        - Overlapping reads are detected in the read requests.

    :return: A decision object representing the parsed planning turn, including the observation text,
        a tuple of read requests, and additional metadata. The decision is of type `PlanningTurnDecision`
        and indicates that more reads are required.
    :rtype: PlanningTurnDecision
    """
    lines = text.splitlines()
    observation_text: str | None = None
    read_requests: list[PlanningReadRequest] = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        observe_match = _OBSERVE_DIRECTIVE.match(line)
        if observe_match is not None:
            if observation_text is not None:
                raise PlanningTurnParseError("OBSERVE_MULTIPLE", "multiple OBSERVE directives are not supported")
            observation_text = observe_match.group(1).strip()
            continue

        read_match = _READ_RANGE_DIRECTIVE.match(line)
        if read_match is not None:
            path = _normalize_workspace_relative_path(read_match.group(1))
            start_byte = int(read_match.group(2))
            end_byte = int(read_match.group(3))
            if end_byte <= start_byte:
                raise PlanningTurnParseError("READ_RANGE_EMPTY", "READ range end must be greater than start")
            read_requests.append(
                PlanningReadRequest(path=path, start_byte=start_byte, end_byte=end_byte)
            )
            continue

        if line.startswith(_DIRECTIVE_PREFIXES):
            raise PlanningTurnParseError(
                "INTERMEDIATE_UNSUPPORTED_DIRECTIVE", "intermediate planning turn contains unsupported directive"
            )

        raise PlanningTurnParseError(
            "INTERMEDIATE_UNRECOGNIZED_CONTENT", "intermediate planning turn contains unrecognized content"
        )

    if observation_text is None:
        raise PlanningTurnParseError("INTERMEDIATE_REQUIRES_OBSERVE", "intermediate planning turn requires OBSERVE")

    if not read_requests:
        raise PlanningTurnParseError(
            "INTERMEDIATE_REQUIRES_READ", "intermediate planning turn requires at least one ranged READ"
        )

    read_request_tuple = tuple(read_requests)
    if (
        planning_observation_carryover_bytes(
            observation_text=observation_text,
            read_requests=read_request_tuple,
        )
        > PLANNING_OBSERVATION_MAX_BYTES
    ):
        raise PlanningTurnParseError("OBSERVATION_TOO_LARGE", "observation exceeds planning observation budget")

    _validate_non_overlapping_reads(read_requests)

    return PlanningTurnDecision(
        kind=PlanningTurnKind.READ_MORE,
        observation_text=observation_text,
        read_requests=read_request_tuple,
        failure_signature=_normalized_read_failure_signature(read_requests),
    )


def _try_parse_refuse(text: str) -> PlanningTurnDecision | None:
    if not text.startswith("REFUSE:"):
        return None

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 1:
        raise PlanningTurnParseError("REFUSE_NOT_ONE_LINE", "REFUSE reason must be one non-empty line")

    refuse_match = _REFUSE_DIRECTIVE.match(lines[0])
    if refuse_match is None:
        raise PlanningTurnParseError("REFUSE_NOT_ONE_LINE", "REFUSE reason must be one non-empty line")

    reason = refuse_match.group(1).strip()
    if not reason:
        raise PlanningTurnParseError("REFUSE_NOT_ONE_LINE", "REFUSE reason must be one non-empty line")
    if len(reason.encode("utf-8")) > 512:
        raise PlanningTurnParseError("REFUSE_TOO_LONG", "REFUSE reason exceeds 512 UTF-8 bytes")
    if _REFUSE_REASON_DIRECTIVE_PREFIX.match(reason):
        raise PlanningTurnParseError("REFUSE_HAS_DIRECTIVE_PREFIX", "REFUSE reason must not contain directive prefixes")

    return PlanningTurnDecision(kind=PlanningTurnKind.REFUSE, reason=reason)


def _try_parse_final_plan(text: str) -> PlanningTurnDecision | None:
    try:
        # A model's EDIT never carries a base: the harness binds it before approval (#407).
        directives = parse_agent_plan(text, edit_base="forbidden")
    except AgentDirectiveParseError:
        return None

    return PlanningTurnDecision(
        kind=PlanningTurnKind.FINAL_PLAN,
        plan_text=text,
        directives=directives,
    )


def _normalize_workspace_relative_path(path_text: str) -> str:
    from pathlib import Path

    if not path_text:
        raise PlanningTurnParseError("READ_PATH_NOT_RELATIVE", "READ path must be workspace-relative")
    path = Path(path_text)
    if path.is_absolute() or ".." in path.parts:
        raise PlanningTurnParseError("READ_PATH_NOT_RELATIVE", "READ path must be workspace-relative")
    if re.match(r"^[A-Za-z]:[\\/]|^/", path_text):
        raise PlanningTurnParseError("READ_PATH_NOT_RELATIVE", "READ path must be workspace-relative")
    return path.as_posix()


def _validate_non_overlapping_reads(read_requests: list[PlanningReadRequest]) -> None:
    by_path: dict[str, list[PlanningReadRequest]] = {}
    for request in read_requests:
        by_path.setdefault(request.path, []).append(request)

    for path, ranges in by_path.items():
        sorted_ranges = sorted(ranges, key=lambda item: (item.start_byte, item.end_byte))
        for index, current in enumerate(sorted_ranges):
            for other in sorted_ranges[index + 1 :]:
                if current.start_byte == other.start_byte and current.end_byte == other.end_byte:
                    raise PlanningTurnParseError("READ_RANGES_DUPLICATE", f"duplicate READ ranges for {path}")
                if current.start_byte < other.end_byte and other.start_byte < current.end_byte:
                    raise PlanningTurnParseError("READ_RANGES_OVERLAP", f"overlapping READ ranges for {path}")


def _normalized_read_failure_signature(read_requests: list[PlanningReadRequest]) -> str:
    identities = sorted(f"{request.path}#bytes={request.start_byte}:{request.end_byte}" for request in read_requests)
    return "|".join(identities)


assert PLANNING_OBSERVATION_MAX_BYTES + PLANNING_NEW_READ_MAX_BYTES == DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES

_PLANNING_STOP_REASONS = {
    LoopStopReason.REPEATED_FAILURE: "PLANNING_REPEATED_READ_REQUEST",
    LoopStopReason.BUDGET_EXHAUSTED: "PLANNING_BUDGET_EXHAUSTED",
    LoopStopReason.WALL_CLOCK: "PLANNING_WALL_CLOCK_EXHAUSTED",
    LoopStopReason.MAX_ITERATIONS: "PLANNING_TURN_LIMIT_EXHAUSTED",
    LoopStopReason.HUMAN_HALT: "PLANNING_HALTED",
}
# The actual cause of a recovery stop, per detection or allowance (Plan 12.3, Design 7).
_RECOVERY_STOP_REASONS: dict[str, str] = {
    LoopSignalKind.REPEATED_READ: "PLANNING_REPEATED_READ_REQUEST",
    LoopSignalKind.REPEATED_MCP: "PLANNING_REPEATED_MCP_REQUEST",
    LoopSignalKind.CYCLE: "PLANNING_ACTION_CYCLE",
    LoopSignalKind.NO_PROGRESS: "PLANNING_NO_PROGRESS",
    LoopSignalKind.REPEATED_PARSE_ERROR: "PLANNING_UNPARSEABLE_RESPONSE",
    _TURN_LIMIT: "PLANNING_TURN_LIMIT_EXHAUSTED",
    _WALL_CLOCK: "PLANNING_WALL_CLOCK_EXHAUSTED",
}
_SIGNAL_TEXT = {
    LoopSignalKind.REPEATED_READ: "repeated {subject} with unchanged results",
    LoopSignalKind.REPEATED_MCP: "repeated {subject} with unchanged results",
    LoopSignalKind.CYCLE: "alternated between the same two requests with unchanged results, ending with {subject}",
    LoopSignalKind.NO_PROGRESS: "made several steps without new evidence, ending with {subject}",
    LoopSignalKind.REPEATED_PARSE_ERROR: "repeated {subject}",
}
_RECOVERY_NOTE_MAX_BYTES = 1024
_CHECKIN_ENDINGS = {
    CheckInDecision.UNAVAILABLE: (
        " The check-in to continue could not be shown, so the turn ended. Nothing was changed; send the request again to retry."
    ),
    CheckInDecision.INVALID: (
        " The answer to the check-in was not recognised, so the turn ended as if you chose Stop. Nothing was changed; "
        "send the request again to retry."
    ),
}


# #400: the same failures when they prove the experimental route stopped, as Chat says them (r8). The Gateway then
# admits no further request on that route while it runs, so these never suggest a retry. Same stop reasons.
# Each speaks only for the failed request and the absent plan: an earlier turn of the same run may already have run
# an approved MCP call (Codex round 40, finding 3).
PLANNING_ROUTE_STOPPED_MESSAGES: dict[str, str] = {
    "PLANNING_GATEWAY_FAILURE": (
        "Planning stopped because the model gateway refused the model's reply after the call was charged, and this "
        f"experimental route is now stopped. That reply was not used, and no plan was offered for approval. {ROUTE_STOPPED_NO_RETRY}"
    ),
    "PLANNING_GATEWAY_COST_UNKNOWN": (
        "Planning stopped because the model gateway failed without reporting the call's cost, and this experimental "
        f"route is now stopped. No plan was offered for approval. {ROUTE_STOPPED_NO_RETRY}"
    ),
    # A later refusal proves only the stop and this request's free refusal, never the stop's cause (Codex review P2).
    "PLANNING_GATEWAY_REFUSED": (
        "Planning stopped because the model gateway has stopped this experimental route, so it refused this request "
        f"before it reached any model and nothing was charged for it. No plan was offered for approval. {ROUTE_STOPPED_NO_RETRY}"
    ),
    # A summary this turn stopped the route, and the request then did not fit (Codex round 41): no capacity
    # recovery can help while the route is stopped.
    "CONTEXT_CAPACITY_EXCEEDED": (
        "Planning stopped because its next request would not fit the model's input capacity, and the model gateway "
        f"has stopped this experimental route. That request was not sent, and no plan was offered for approval. {ROUTE_STOPPED_NO_RETRY}"
    ),
}


def planning_corrective_text(
    stop_reason: str | None,
    *,
    refusal_reason: str | None = None,
    workspace_root: Path | None = None,
    route_stopped: bool = False,
    detail: str | None = None,
) -> str:
    """The user's text for `stop_reason`. ``route_stopped``: the request's failure proved its experimental route
    stopped (#400). `detail` names what repeated (Plan 12.3, Design 7)."""
    text = _corrective_template(
        stop_reason, refusal_reason=refusal_reason, workspace_root=workspace_root, route_stopped=route_stopped
    )
    return text + sanitize_workspace_text(detail, workspace_root=workspace_root) if detail and text else text


def _corrective_template(
    stop_reason: str | None, *, refusal_reason: str | None, workspace_root: Path | None, route_stopped: bool
) -> str:
    if stop_reason == "PLANNING_MODEL_REFUSED" and refusal_reason is not None:
        return sanitize_workspace_text(refusal_reason, workspace_root=workspace_root)
    if route_stopped and stop_reason in PLANNING_ROUTE_STOPPED_MESSAGES:
        return PLANNING_ROUTE_STOPPED_MESSAGES[stop_reason]
    templates = {
        "PLANNING_REPEATED_READ_REQUEST": "Planning stopped after repeated non-progress read requests.",
        "PLANNING_REPEATED_MCP_REQUEST": "Planning stopped after repeated MCP requests that returned the same result.",
        "PLANNING_ACTION_CYCLE": (
            "Planning stopped after the model alternated between the same requests with unchanged results."
        ),
        "PLANNING_NO_PROGRESS": "Planning stopped after several steps that produced no new evidence.",
        "PLANNING_GATEWAY_FAILURE": "Planning stopped because the model gateway request failed.",
        "PLANNING_GATEWAY_COST_UNKNOWN": (
            "Planning stopped because a gateway attempt cost could not be verified; "
            "no further retry was dispatched."
        ),
        "PLANNING_GATEWAY_REFUSED": (
            "Planning stopped because the model gateway refused the request before sending it to any "
            "model. Nothing was charged, stored or changed."
        ),
        # Plan 12.2 closure: the adopted Gateway enforces no registry or another one (Codex 6249427656).
        "PLANNING_GATEWAY_REGISTRY_MISMATCH": gateway_registry_mismatch_text("PLANNING_GATEWAY_REGISTRY_MISMATCH", workspace_root),
        "PLANNING_NOTICE_UNDELIVERED": (
            "Planning stopped because the required notice for this model could not be shown, so the "
            "request was not sent. Nothing was stored or changed."
        ),
        "PLANNING_UNPARSEABLE_RESPONSE": (
            "Planning stopped after repeated responses that did not match the required directive grammar."
        ),
        "PLANNING_OUTPUT_TRUNCATED": (
            "Planning stopped because the model's reply reached its output limit before the plan was "
            "complete. Nothing was stored, offered for approval or changed."
        ),
        "PLANNING_OUTPUT_UNFINISHED": (
            "Planning stopped because a content filter or a provider error ended the model's reply before "
            "it finished. Nothing was stored, offered for approval or changed."
        ),
        "PLANNING_BUDGET_EXHAUSTED": "Planning stopped because the run budget was exhausted.",
        "PLANNING_WALL_CLOCK_EXHAUSTED": "Planning stopped because the wall-clock limit was reached.",
        "PLANNING_TURN_LIMIT_EXHAUSTED": "Planning stopped before a final plan could be settled.",
        "PLANNING_HALTED": "Planning was halted before settlement.",
        "CONTEXT_CAPACITY_EXCEEDED": (
            "Planning stopped because its next request would not fit the model's input capacity, even "
            "with a smaller view of the conversation. That request was not sent, and nothing was stored "
            "or changed. A shorter prompt or a narrower request that involves fewer workspace files may "
            "help. If earlier conversation history is the cause, start a new thread."
        ),
        # The Gateway's final guard refused the complete request as over the route's input capacity, with
        # no smaller view tried (release supplement V1; Codex's exact text, 2026-10-04).
        "PLANNING_INPUT_CAPACITY_EXCEEDED": (
            "Planning stopped because its next request exceeds the model's input capacity. That request was "
            "not sent to a model. A shorter prompt or a narrower request involving fewer workspace files may "
            "help. If earlier conversation history is the cause, start a new thread. This thread stays open."
        ),
        "PLANNING_OBSERVATION_BUDGET_EXHAUSTED": (
            "Planning stopped because carried observation evidence exceeds the allowed budget."
        ),
        "PLANNING_READ_BUDGET_EXHAUSTED": (
            "Planning stopped because requested read evidence exceeds the allowed budget."
        ),
        "PLANNING_READ_INVALID_RANGE": "Planning stopped because a guarded read range was invalid.",
        "PLANNING_READ_INVALID_PATH": "Planning stopped because a guarded read path was invalid.",
        "PLANNING_READ_FILE_NOT_FOUND": "Planning stopped because a guarded read target was not found.",
        "PLANNING_READ_NOT_UTF8_ALIGNED": (
            "Planning stopped because a guarded read range was not valid UTF-8."
        ),
        "PLANNING_READ_SOURCE_CHANGED": "Planning stopped because source content changed during planning.",
        "PLANNING_READ_GUARD_BLOCKED": "Planning stopped because a guarded read was blocked by policy.",
    }
    if stop_reason is None:
        return ""
    return templates.get(
        stop_reason,
        sanitize_workspace_text(stop_reason, workspace_root=workspace_root),
    )


class PlanningLoopRunner:
    def __init__(
        self,
        *,
        gateway_client,
        model: str,
        policy: PlanningLoopPolicy,
        workspace_root: Path,
        execution_mode: ExecutionMode,
        max_cost_usd: Decimal | None = None,
        guard: PreToolGuard | None = None,
        now: Callable[[], datetime] | None = None,
        halt_requested: Callable[[], bool] | None = None,
        usage_callback: PlanningGatewayUsageCallback | None = None,
        retry_controller: RetryController | None = None,
        progress_observer: PlanningProgressObserver | None = None,
        client_mcp_service: object | None = None,
        mcp_permission_broker: object | None = None,
        operation_control: TurnOperationControl | None = None,
        context_packer: ContextPacker | None = None,
        attempt_callback: PlanningAttemptCallback | None = None,
        route_binder: TurnRouteBinder | None = None,
        recovery_checkin: PlanningCheckInCallback | None = None,
        loop_event_sink: Callable[[TelemetryEvent], None] | None = None,
    ) -> None:
        """`recovery_checkin` makes the run interactive (Plan 12.3, Design 6): repetition and the end of
        the allowance get a nudge, then a check-in, instead of a stop. Without it the run is headless
        and keeps today's hard caps."""
        self._gateway_client = gateway_client
        self._model = model
        self._policy = policy
        self._recovery_checkin = recovery_checkin
        self._loop_event_sink = loop_event_sink
        self._workspace_root = workspace_root.resolve()
        self._execution_mode = execution_mode
        self._max_cost_usd = max_cost_usd
        self._guard = guard or PreToolGuard.for_workspace(
            workspace_root=self._workspace_root,
            allowed_network_hosts=(),
        )
        self._now = now or (lambda: datetime.now(tz=UTC))
        self._halt_requested = halt_requested or (lambda: False)
        self._usage_callback = usage_callback
        self._retry_controller = retry_controller or RetryController(
            policy=RetryPolicy(base_delay_ms=0, jitter_ms=(0,)),
            sleep_ms=lambda _delay_ms: None,
        )
        self._progress_observer = progress_observer
        self._client_mcp_service = client_mcp_service
        self._mcp_permission_broker = mcp_permission_broker
        self._operation_control = operation_control
        self._context_packer = context_packer
        self._attempt_callback = attempt_callback
        self._route_binder = route_binder

    def run(
        self,
        *,
        run_id: str,
        session_id: str | None,
        task: str,
        initial_workspace_context: str = "",
        initial_workspace_file_sizes: dict[str, int] | None = None,
        client_mcp_service: object | None = None,
        mcp_permission_broker: object | None = None,
        conversation_envelope: str = "",
        required_file_sizes: dict[str, int] | None = None,
        initial_workspace_sha256s: dict[str, str] | None = None,
    ) -> PlanningLoopResult:
        # Only an evaluation caller's explicit cap can stop planning on money (Plan 12.2 Task 11).
        if self._max_cost_usd is not None and self._max_cost_usd <= Decimal("0"):
            return PlanningLoopResult(stop_reason="PLANNING_BUDGET_EXHAUSTED", settled_turns=0)

        from optimus.loops.tools import GuardedLoopToolExecutor

        service = client_mcp_service if client_mcp_service is not None else self._client_mcp_service
        broker = mcp_permission_broker if mcp_permission_broker is not None else self._mcp_permission_broker

        iteration_runner = _PlanningIterationRunner(
            gateway_client=self._gateway_client,
            model=self._model,
            task=task,
            initial_workspace_context=initial_workspace_context,
            initial_workspace_file_sizes=initial_workspace_file_sizes or {},
            required_file_sizes=required_file_sizes,
            initial_workspace_sha256s=initial_workspace_sha256s,
            workspace_root=self._workspace_root,
            run_id=run_id,
            session_id=session_id,
            execution_mode=self._execution_mode,
            policy=self._policy,
            loop_budget_policy=self._policy.to_loop_budget_policy(max_cost_usd=self._max_cost_usd),
            max_cost_usd=self._max_cost_usd,
            now=self._now,
            usage_callback=self._usage_callback,
            retry_controller=self._retry_controller,
            progress_observer=self._progress_observer,
            halt_requested=self._halt_requested,
            guard=self._guard,
            client_mcp_service=service,
            mcp_permission_broker=broker,
            operation_control=self._operation_control,
            conversation_envelope=conversation_envelope,
            context_packer=self._context_packer,
            attempt_callback=self._attempt_callback,
            route_binder=self._route_binder,
            interactive=self._recovery_checkin is not None,
            loop_event_sink=self._loop_event_sink,
        )
        tools = GuardedLoopToolExecutor(guard=self._guard)

        def run_allowance(steps: int, *, budgeted: bool = False, spent: Decimal = Decimal("0")) -> GoalLoopResult:
            # One allowance: `steps` planning steps and a fresh wall clock. A headless run has exactly one.
            # It starts from the turn's spend, so an evaluation caller's cap covers the whole turn.
            iteration_runner.start_allowance(steps, budgeted=budgeted)
            controller = GoalLoopController(
                policy=iteration_runner.loop_budget_policy.model_copy(update={"max_iterations": steps}),
                runner=iteration_runner,
                tools=tools,
                evaluator=DeterministicCompletionEvaluator(
                    completed=False,
                    reason="planning loop uses per-turn settlement",
                ),
                ledger=InMemoryProgressLedger(),
                halt_requested=self._halt_requested,
                now=self._now,
            )
            return controller.run(
                IterationState(
                    run_id=run_id,
                    session_id=session_id,
                    goal=task,
                    completion_condition=task,
                    started_at=self._now(),
                    cost_usd_spent=spent,
                )
            )

        loop_result = run_allowance(self._policy.max_planning_turns)
        checkin = self._recovery_checkin
        while checkin is not None and not self._halt_requested():
            move = iteration_runner.next_recovery_move(loop_result)
            if move is None:
                break
            if move is _NUDGE_STEP:
                # A detection on the allowance's last step, or after the clock: its nudge still comes
                # before the check-in, in exactly one more step (Plan 12.3, Design 4).
                loop_result = run_allowance(1, budgeted=True, spent=loop_result.state.cost_usd_spent)
                continue
            assert isinstance(move, PlanningCheckIn)
            try:
                decision = checkin(move)
            except Exception:  # noqa: BLE001 - a check-in that cannot be shown ends the turn recoverably
                decision = CheckInDecision.UNAVAILABLE
            if not isinstance(decision, CheckInDecision):
                decision = CheckInDecision.INVALID
            iteration_runner.record_checkin(move, decision)
            if self._halt_requested() or decision is not CheckInDecision.CONTINUE:
                break
            iteration_runner.end_episode()
            if move.plan_waiting:
                break  # the kept final plan goes on to the normal plan approval
            loop_result = run_allowance(self._policy.continue_grant_steps, spent=loop_result.state.cost_usd_spent)
        result = iteration_runner.to_planning_result(loop_result)
        iteration_runner.emit_final_progress(result)
        return result


class _PlanningIterationRunner:
    def __init__(
        self,
        *,
        gateway_client,
        model: str,
        task: str,
        initial_workspace_context: str,
        initial_workspace_file_sizes: dict[str, int],
        required_file_sizes: dict[str, int] | None = None,
        initial_workspace_sha256s: dict[str, str] | None = None,
        workspace_root: Path,
        run_id: str,
        session_id: str | None,
        execution_mode: ExecutionMode,
        policy: PlanningLoopPolicy,
        loop_budget_policy: LoopBudgetPolicy,
        max_cost_usd: Decimal | None,
        now: Callable[[], datetime],
        usage_callback: PlanningGatewayUsageCallback | None,
        retry_controller: RetryController,
        progress_observer: PlanningProgressObserver | None,
        halt_requested: Callable[[], bool] | None = None,
        guard: PreToolGuard | None = None,
        client_mcp_service: object | None = None,
        mcp_permission_broker: object | None = None,
        operation_control: TurnOperationControl | None = None,
        conversation_envelope: str = "",
        context_packer: ContextPacker | None = None,
        attempt_callback: PlanningAttemptCallback | None = None,
        route_binder: TurnRouteBinder | None = None,
        interactive: bool = False,
        loop_event_sink: Callable[[TelemetryEvent], None] | None = None,
    ) -> None:
        self._gateway_client = gateway_client
        self._model = model
        self._task = task
        # Plan 12.3 interactive recovery. Steps are numbered across allowances, so each request keeps
        # its own operation id; costs, evidence and receipts simply carry on.
        self._interactive = interactive
        self._loop_event_sink = loop_event_sink
        self._detector = LoopDetector(policy.loop_thresholds)
        self._coverage = ReadCoverage()
        self._mcp_results = McpResults()
        self._steps_run = 0
        self._turn_offset = 0
        self._allowance_end = policy.max_planning_turns
        self._budgeted_step = False
        self._episode: LoopDetection | None = None  # the first detection of the open episode
        self._nudge: str | None = None  # the open episode's note, until a request carries it
        self._nudged = False
        self._checkin_requested = False
        self._last_error_step: LoopStep | None = None
        self._recovery_stop: tuple[str, str] | None = None  # (stop reason, the user's detail)
        self._refusal_detail = ""
        self._attempt_callback = attempt_callback
        self._route_binder = route_binder
        # Sticky: a Gateway failure proved this route stopped, and a stopped route never restarts (#400).
        self._route_stopped = False
        # The previous turn's closed parse-failure code, for the next turn's notice; None once a turn parses (#403).
        self._parse_failure_code: str | None = None
        self._conversation_envelope = conversation_envelope
        self._context_packer = context_packer
        self._initial_workspace_context = initial_workspace_context
        self._initial_workspace_file_sizes = initial_workspace_file_sizes
        self._required_file_sizes = required_file_sizes or {}
        self._initial_workspace_sha256s = initial_workspace_sha256s or {}
        # The raw evidence the final plan's turn showed, by path; set when a final plan settles (#407).
        self._final_evidence_sha256s: dict[str, str] = {}
        self._workspace_root = workspace_root
        self._run_id = run_id
        self._session_id = session_id
        self._execution_mode = execution_mode
        self._policy = policy
        self.loop_budget_policy = loop_budget_policy
        self._max_cost_usd = max_cost_usd
        self._now = now
        self._usage_callback = usage_callback
        self._retry_controller = retry_controller
        self._progress_observer = progress_observer
        self._operation_control = operation_control
        self._observations: list[PlanningObservation] = []
        self._current_reads: tuple[PlanningReadEvidence, ...] = ()
        self._mcp_evidence_envelope: str = ""
        self._mcp_tool_calls: list[AgentToolCall] = []
        self._gateway_request_ids: list[str] = []
        self._total_cost_usd = Decimal("0")
        self._cost_complete = True
        self._unknown_cost_attempt_count = 0
        self._last_decision: PlanningTurnDecision | None = None
        self._last_provider: str | None = None
        self._last_wire_retry_count = 0
        self._typed_planning_stop_reason: str | None = None
        self._last_non_progress_kind: Literal["GATEWAY_FAILURE", "READ_MORE", "MCP_TOOL", "UNPARSEABLE"] | None = None
        self._halt_requested = halt_requested or (lambda: False)
        self._guard = guard or PreToolGuard.for_workspace(
            workspace_root=workspace_root,
            allowed_network_hosts=(),
        )
        self._client_mcp_service = client_mcp_service
        self._mcp_permission_broker = mcp_permission_broker
        self._mcp_toolbox = AgentToolbox.for_workspace(
            workspace_root=workspace_root,
            context=RuntimeContext(execution_mode=execution_mode),
            run_id=run_id,
            session_id=session_id,
            guard=self._guard,
            client_mcp_service=client_mcp_service,
            mcp_permission_broker=mcp_permission_broker,
        )

    def _cap_reached(self, spent: Decimal) -> bool:
        """Whether an evaluation caller's explicit cap is spent; a product run has no cap (Plan 12.2 Task 11)."""
        return self._max_cost_usd is not None and spent >= self._max_cost_usd

    def _remaining_cap(self, spent: Decimal) -> Decimal | None:
        """The evaluation cap left, for telemetry only; None on a product run, which has no dollar bound."""
        return None if self._max_cost_usd is None else max(Decimal("0"), self._max_cost_usd - spent)

    def _typed_planning_failure(
        self,
        *,
        stop_reason: str,
        summary: str,
        cost_usd: Decimal,
    ) -> IterationOutcome:
        self._typed_planning_stop_reason = stop_reason
        return IterationOutcome(
            summary=summary,
            deterministic_completion=True,
            failure_signature=None,
            cost_usd=cost_usd,
        )

    # Plan 12.3 interactive recovery (Design 4). The order after each step: the outcome is recorded
    # (the controller), then the detector runs (here), then the controller applies the allowance.
    def _observed(self, outcome: IterationOutcome, step: LoopStep, planning_turn: int) -> IterationOutcome:
        if not self._interactive:
            return outcome  # headless keeps today's consecutive counter and its hard stop
        if step.error_class is not None:
            self._last_error_step = step
        detection = self._detector.observe(step)
        if detection is not None:
            self._emit_loop_record("detection", detection.kind, planning_turn)
            if self._episode is None:
                self._episode = detection
                self._nudge = self._recovery_note(detection)  # help comes before asking
            elif self._nudged:
                self._checkin_requested = True
        return outcome.model_copy(update={"failure_signature": None, "deterministic_completion": self._checkin_requested})

    def start_allowance(self, steps: int, *, budgeted: bool) -> None:
        self._turn_offset = self._steps_run
        self._allowance_end = self._steps_run + steps
        self._budgeted_step = budgeted

    def next_recovery_move(self, loop_result: GoalLoopResult) -> PlanningCheckIn | object | None:
        """After an allowance: the budgeted nudge step, a check-in, or None when the result stands.
        First-occurrence typed failures, refusals and halts stay stops."""
        if self._typed_planning_stop_reason is not None:
            return None
        stop = loop_result.stop_reason
        kind = None if self._last_decision is None else self._last_decision.kind
        plan_waiting, refusal_waiting = kind is PlanningTurnKind.FINAL_PLAN, kind is PlanningTurnKind.REFUSE
        if stop is LoopStopReason.COMPLETED:
            # An open episode always ends at a check-in, even when its nudge produced a plan or a refusal.
            if not (self._checkin_requested or ((plan_waiting or refusal_waiting) and self._episode is not None)):
                return None
        elif stop in (LoopStopReason.MAX_ITERATIONS, LoopStopReason.WALL_CLOCK):
            if self._nudge is not None:
                return _NUDGE_STEP
            plan_waiting = refusal_waiting = False
        else:
            return None
        if self._episode is not None:
            cause: str = self._episode.kind
        else:
            cause = _WALL_CLOCK if stop is LoopStopReason.WALL_CLOCK else _TURN_LIMIT
        return PlanningCheckIn(
            cause=cause,
            planning_steps=self._steps_run,
            text=self._checkin_text(cause, plan_waiting, refusal_waiting),
            plan_waiting=plan_waiting,
            refusal_waiting=refusal_waiting,
        )

    def record_checkin(self, checkin: PlanningCheckIn, decision: CheckInDecision) -> None:
        self._emit_loop_record("check_in", checkin.cause, self._steps_run, decision=decision)
        if decision is CheckInDecision.CONTINUE:
            return
        if checkin.refusal_waiting:
            # A refusal that is not continued stands, with the model's reason and any check-in explanation.
            self._refusal_detail = _CHECKIN_ENDINGS.get(decision, "")
            return
        detail = "" if self._episode is None else f" Last repeated step: {self._episode.step.subject}."
        detail += _CHECKIN_ENDINGS.get(decision, "")
        self._recovery_stop = (_RECOVERY_STOP_REASONS[checkin.cause], detail)

    def end_episode(self) -> None:
        """Continue ends the episode: a later detection starts a new one, with its own nudge."""
        self._episode, self._nudge, self._nudged, self._checkin_requested = None, None, False, False
        self._detector.reset()
        if self._last_decision is not None and self._last_decision.kind is PlanningTurnKind.REFUSE:
            self._last_decision = None  # Continue sets the refusal aside for more planning steps

    def _recovery_note(self, detection: LoopDetection) -> str:
        lines = [
            "Your recent planning steps "
            + _SIGNAL_TEXT[detection.kind].format(subject=detection.step.subject)
            + ". Do not repeat that request."
        ]
        error = self._last_error_step
        if error is not None:
            lines.append(f"Last error: the reply did not parse (parser reason {error.error_class}): {error.error_message}")
        lines.append(
            "Try a different approach: request different evidence, or settle a final plan or a REFUSE: line "
            "with the evidence you already have."
        )
        note = sanitize_workspace_text("\n".join(lines), workspace_root=self._workspace_root)
        return note.encode("utf-8")[:_RECOVERY_NOTE_MAX_BYTES].decode("utf-8", errors="ignore")

    def _checkin_text(self, cause: str, plan_waiting: bool, refusal_waiting: bool) -> str:
        minutes = self._policy.max_wall_clock_minutes
        if self._episode is not None:
            what = (
                "the model " + _SIGNAL_TEXT[self._episode.kind].format(subject=self._episode.step.subject)
                + ", and was asked once to try a different approach"
            )
        elif cause == _WALL_CLOCK:
            what = f"the {minutes}-minute planning time ran out without a final plan"
        else:
            what = "the planning steps ran out without a final plan"
        text = f"Planning paused after step {self._steps_run}: {what}."
        if plan_waiting:
            text += " A final plan is ready: Continue shows it for your approval."
        elif refusal_waiting:
            assert self._last_decision is not None
            text += (
                f" The model then refused: {self._last_decision.reason} Continue sets the refusal aside and grants "
                f"{self._policy.continue_grant_steps} more planning steps and {minutes} minutes; Stop keeps the refusal."
            )
        else:
            text += f" Continue grants {self._policy.continue_grant_steps} more planning steps and {minutes} minutes."
        text += " Continue never approves a change; every change still needs its own approval. Stop ends this turn."
        return sanitize_workspace_text(text, workspace_root=self._workspace_root)

    def _emit_loop_record(self, record: str, signal: str, planning_step: int, *, decision: CheckInDecision | None = None) -> None:
        """Content-free: no path, tool, argument or reply text (Plan 12.3, Design 7)."""
        if self._loop_event_sink is None:
            return
        self._loop_event_sink(
            TelemetryEvent.loop_recovery(
                run_id=self._run_id,
                session_id=self._session_id,
                request_id=f"{self._run_id}:loop-recovery:{planning_step}:{record}",
                occurred_at=self._now(),
                record=record,
                signal=str(signal),
                planning_step=planning_step,
                decision=None if decision is None else decision.value,
            )
        )

    def _record_reported_gateway_usage(
        self,
        usage: GatewayUsage,
        planning_turn: int,
        wire_attempt: int,
    ) -> None:
        """Record one reported usage envelope exactly once.

        Appends the Gateway request ID, adds cost, captures provider, and
        invokes the usage callback. Called from both the success path and the
        typed-Gateway-exception path when gateway_usage is not None.
        """
        self._gateway_request_ids.append(usage.gateway_request_id)
        self._total_cost_usd += usage.cost_usd
        self._last_provider = usage.provider
        if self._usage_callback is not None:
            self._usage_callback(usage, planning_turn, wire_attempt)

    def _report_attempts(
        self, planning_turn: int, wire_attempt: int, attempts: tuple[ProviderAttempt, ...], identity: Any, failure: BaseException | None = None
    ) -> None:
        if self._attempt_callback is not None:
            self._attempt_callback(planning_turn, wire_attempt, attempts, identity, failure)

    def _invoke_planning_gateway(
        self,
        *,
        planning_turn: int,
        prompt: str,
    ) -> tuple[GatewayResponse, Decimal]:
        from optimus.retry.policy import PermanentGatewayError as _PermanentStop

        cost_before = self._total_cost_usd
        wire_attempt = 0
        bound: BoundRequest | None = None
        # How this request's sequence ended, for its stop reason (sequence-local, not loop-wide).
        ended = {"unsent": False, "unknown": False, "refused": False, "over_capacity": False, "registry_mismatch": False}
        # An attempt that cannot be attributed or recorded truthfully (a Gateway report that names no
        # attempt, a conflicting receipt, a divergent ledger record) is an integrity error. Everything
        # that can still be recorded is recorded first; then it fails the turn loudly after the retry
        # funnel, never as a gateway failure (Fable CP3 correction review MINOR-1; Codex CP3 correction
        # ruling C1).
        integrity: list[Exception] = []

        def capture(action: Callable[[], Any]) -> None:
            try:
                action()
            except Exception as error:  # noqa: BLE001 - held for after the retry funnel
                integrity.append(error)

        def operation() -> GatewayResponse:
            nonlocal wire_attempt, bound
            wire_attempt += 1
            control = self._operation_control
            op_id = f"gateway:{planning_turn}:{wire_attempt}"

            def complete(terminal: str) -> None:
                if control is not None:
                    from optimus.acp.lifecycle import DirectiveKind

                    control.complete_directive(DirectiveKind.GATEWAY, op_id, terminal)

            if self._route_binder is not None and bound is None:
                # One binding per payload, after the halt check and before the lease, so a request
                # whose notice was not delivered is never a started provider attempt. An identical
                # transport retry reuses it with its own attempt identity (Codex CP3 ruling R4).
                if self._halt_requested():
                    raise _PermanentStop("gateway attempt suppressed by turn control")
                bound = self._route_binder.bind(stage="planning", input_text=prompt)
                if bound is None:
                    ended["unsent"] = True
                    binder = self._route_binder
                    capture(lambda: self._report_attempts(planning_turn, wire_attempt, (_NOT_SENT,), binder.identity))
                    raise _PermanentStop("required notice not delivered; nothing was sent")
            identity = bound.identity if bound is not None else None

            def account(
                usage: GatewayUsage | None, classify: Callable[[], tuple[ProviderAttempt, ...]], failure: BaseException | None = None
            ) -> tuple[ProviderAttempt, ...] | None:
                """Settled usage to the totals and the ledger, then every attempt to the receipt sink,
                or, for a report that cannot be attributed, the records its integrity error carries,
                with the request's `failure` for the diagnostic only. No failure stops the next step.
                Returns None when anything failed."""
                held = len(integrity)
                if usage is not None:
                    capture(lambda: self._record_reported_gateway_usage(usage, planning_turn, wire_attempt))
                try:
                    attempts = classify()
                except AttemptIntegrityError as error:
                    integrity.append(error)
                    attempts = error.attempts
                capture(lambda: self._report_attempts(planning_turn, wire_attempt, attempts, identity, failure))
                return attempts if len(integrity) == held else None

            if control is not None:
                from optimus.acp.lifecycle import DirectiveKind

                control.register_operations([(DirectiveKind.GATEWAY, op_id)])
                lease = control.try_start(DirectiveKind.GATEWAY, op_id)
                if not lease.granted:
                    raise _PermanentStop("gateway attempt suppressed by turn control")
            if self._context_packer is not None:
                # Plan 12.2 Task 10: the attached meter reads only inputs actually sent.
                self._context_packer.record_dispatch(prompt)
            elif self._route_binder is not None:
                # Release supplement V1: without an engine, the request meter reads the bound route's capacity.
                self._route_binder.record_dispatch(prompt)
            metadata: dict[str, Any] = {
                "run_id": self._run_id,
                "session_id": self._session_id,
                "purpose": "planning_turn",
                "planning_turn": planning_turn,
            }
            binding: dict[str, Any] = {}
            if bound is not None:
                metadata["request_id"] = bound.request_id
                binding["route_binding"] = bound.binding
            try:
                response = self._gateway_client.create_response(
                    model=self._model, input_text=prompt, metadata=metadata, **binding
                )
            except GatewayError as exc:
                # One classifier for every stage (Codex CP3 ruling R3): each provider attempt is
                # reported, a proven preflight refusal costs nothing, and anything without settled
                # usage stays unknown. Settled usage is recorded first, so a paid attempt reaches the
                # totals and the ledger even if its report then fails.
                if stops_experimental_route(exc, experimental=self._route_binder is not None and self._route_binder.experimental):
                    self._route_stopped = True
                usage = getattr(exc, "gateway_usage", None)
                attempts = account(usage, _failure_classifier(exc), exc)
                if attempts is None:
                    complete("cost_unknown")
                    raise _PermanentStop("attempt accounting integrity error") from exc
                unknown = sum(1 for attempt in attempts if attempt.cost_usd is None)
                complete("cost_unknown" if unknown else "failed")
                if unknown:
                    # Unknown cost: terminal regardless of retryability.
                    self._cost_complete = False
                    self._unknown_cost_attempt_count += unknown
                    ended["unknown"] = True
                    raise _PermanentStop("unknown transport cost") from exc
                if is_preflight_refusal(exc):
                    ended["refused"] = True
                    ended["over_capacity"] = is_input_capacity_refusal(exc)
                    ended["registry_mismatch"] = is_gateway_registry_mismatch(exc)
                    raise _PermanentStop("refused before any upstream attempt") from exc
                # An evaluation caller's explicit cap: at/above it, stop immediately (Plan 12.2 Task 11).
                if usage is not None and self._cap_reached(self._total_cost_usd):
                    raise _PermanentStop("budget exhausted after reported failed attempt") from exc
                # Re-raise for normal RetryController classification.
                raise
            except Exception as exc:
                complete("cost_unknown")
                # Unexpected non-Gateway exception — treat as unknown cost.
                self._cost_complete = False
                self._unknown_cost_attempt_count += 1
                ended["unknown"] = True
                account(None, _failure_classifier(exc), exc)
                from optimus.acp.debug_trace import acp_debug_log, debug_trace_enabled

                if debug_trace_enabled():
                    acp_debug_log(
                        location="planning_loop.py:_invoke_planning_gateway",
                        message="planning attempt cost unknown",
                        data=_unknown_cost_payload(self, exc, planning_turn, wire_attempt),
                        hypothesis_id="P9.95-USAGE-UNKNOWN",
                        run_id=self._run_id,
                    )
                raise _PermanentStop("unknown transport cost") from exc

            complete("succeeded")
            # Success path — record usage exactly once, before the attempts are classified.
            attempts = account(response.gateway_usage, lambda: attempts_from_response(response))
            if attempts is None:
                raise _PermanentStop("attempt accounting integrity error")
            # A routed success can follow an earlier attempt whose cost is unknown; it stays unknown.
            unknown = sum(1 for attempt in attempts if attempt.cost_usd is None)
            if unknown:
                self._cost_complete = False
                self._unknown_cost_attempt_count += unknown
            return response

        retry_result = self._retry_controller.run(operation)
        if integrity:
            raise first_error(integrity)

        # Map RetryResult to planning outcomes.
        sequence_cost = self._total_cost_usd - cost_before

        if retry_result.value is not None:
            # Success after zero or more reported retries.
            self._last_wire_retry_count = retry_result.retry_count
            return retry_result.value, sequence_cost

        # Terminal failure — determine stop reason.
        if ended["unsent"]:
            raise _PlanningGatewayInvocationError("PLANNING_NOTICE_UNDELIVERED", reported_cost_usd=sequence_cost)
        if ended["unknown"]:
            raise _PlanningGatewayInvocationError(
                "PLANNING_GATEWAY_COST_UNKNOWN", reported_cost_usd=sequence_cost
            )
        if ended["over_capacity"]:
            raise _PlanningGatewayInvocationError("PLANNING_INPUT_CAPACITY_EXCEEDED", reported_cost_usd=sequence_cost)
        if ended["registry_mismatch"]:
            raise _PlanningGatewayInvocationError("PLANNING_GATEWAY_REGISTRY_MISMATCH", reported_cost_usd=sequence_cost)
        if ended["refused"]:
            raise _PlanningGatewayInvocationError("PLANNING_GATEWAY_REFUSED", reported_cost_usd=sequence_cost)
        if self._cap_reached(self._total_cost_usd):
            raise _PlanningGatewayInvocationError(
                "PLANNING_BUDGET_EXHAUSTED", reported_cost_usd=sequence_cost
            )
        raise _PlanningGatewayInvocationError(
            "PLANNING_GATEWAY_FAILURE", reported_cost_usd=sequence_cost
        )

    def run_iteration(self, state: IterationState, tools: LoopToolExecutorProtocol) -> IterationOutcome:
        self._steps_run += 1
        planning_turn = self._turn_offset + state.iteration + 1
        remaining_wall_clock = 0 if self._budgeted_step else max(
            0,
            self._policy.max_wall_clock_minutes - state.elapsed_minutes(now=self._now()),
        )
        carried_envelope = ""
        current_envelope = ""
        try:
            if self._observations:
                carried_envelope = pack_planning_evidence(
                    observations=tuple(self._observations),
                    current_reads=(),
                ).text
            if self._current_reads:
                current_envelope = pack_planning_evidence(
                    observations=(),
                    current_reads=self._current_reads,
                ).text
        except PlanningEvidenceBudgetError as exc:
            return self._typed_planning_failure(
                stop_reason=exc.code,
                summary=str(exc),
                cost_usd=Decimal("0"),
            )
        mcp_evidence_envelope = self._mcp_evidence_envelope
        recovery_note = self._nudge or ""
        # Captured once per turn, so every repack and wire retry of this turn carries the same notice (#403).
        correction_notice = _correction_notice(self._parse_failure_code)

        def build(conversation_envelope: str) -> str:
            return build_multi_turn_planner_input(
                self._task,
                planning_turn=planning_turn,
                max_planning_turns=self._allowance_end,
                remaining_wall_clock_minutes=remaining_wall_clock,
                recovery_note=recovery_note,
                carried_observations_envelope=carried_envelope,
                current_read_evidence_envelope=current_envelope,
                mcp_evidence_envelope=mcp_evidence_envelope,
                initial_workspace_context=self._initial_workspace_context if planning_turn == 1 else "",
                # The sizes stay until the first guarded read: a turn that read nothing still needs
                # them to size its re-read (#388). The raw context stays turn-1-only (Plan 9.87).
                initial_workspace_file_sizes=(
                    self._initial_workspace_file_sizes if planning_turn == 1 or not self._observations else {}
                ),
                # Metadata of files no turn showed in full: every ranged read is sized from it.
                required_file_sizes=self._required_file_sizes,
                evidence_limits=(
                    PLANNING_OBSERVATION_MAX_BYTES,
                    PLANNING_NEW_READ_MAX_BYTES,
                    DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES,
                ),
                conversation_envelope=conversation_envelope,
                correction_notice=correction_notice,
            )

        if self._context_packer is None:
            prompt = build(self._conversation_envelope)
        else:
            # An attached turn: files and evidence grow every round, so each complete request is
            # fitted to the route's usable input, repacking the history view when needed (Plan 12.2
            # Task 9). Nothing that does not fit is sent.
            fitted = self._context_packer.fit(build)
            if fitted is None and self._halt_requested():
                return self._typed_planning_failure(
                    stop_reason="PLANNING_HALTED",
                    summary="planning was halted while its request was being fitted",
                    cost_usd=Decimal("0"),
                )
            if fitted is None:
                # A summary this turn may have stopped the shared route (#400; Codex round 41). Packers that
                # predate the fact (test doubles) have none.
                if getattr(self._context_packer, "route_stopped", False) is True:
                    self._route_stopped = True
                return self._typed_planning_failure(
                    stop_reason="CONTEXT_CAPACITY_EXCEEDED",
                    summary="the planning request does not fit the model's usable input",
                    cost_usd=Decimal("0"),
                )
            prompt = fitted
        # MCP evidence is one-shot for the turn that just received it.
        self._mcp_evidence_envelope = ""
        if self._nudge is not None:
            self._nudge, self._nudged = None, True  # one nudge per episode, carried by this request
        try:
            response, attempt_cost = self._invoke_planning_gateway(planning_turn=planning_turn, prompt=prompt)
        except _PlanningGatewayInvocationError as exc:
            self._last_non_progress_kind = "GATEWAY_FAILURE"
            return self._typed_planning_failure(
                stop_reason=exc.stop_reason,
                summary=f"planning gateway invocation stopped: {exc.stop_reason}",
                cost_usd=exc.reported_cost_usd,
            )
        # Success path — cost already recorded inside _invoke_planning_gateway via
        # _record_reported_gateway_usage; do NOT append/add again here.

        # A reply cut off at its output limit is never a candidate, even if its prefix parses as a
        # valid plan: stop before parsing, storing, approval or execution (Plan 12.2 Task 5).
        if getattr(response, "length_limited", False):
            return self._typed_planning_failure(
                stop_reason="PLANNING_OUTPUT_TRUNCATED",
                summary="planning response was cut off at the model's output limit",
                cost_usd=attempt_cost,
            )
        # Likewise a reply a content filter or provider error ended (operator decision 2026-10-02).
        if getattr(response, "stopped_unfinished", False):
            return self._typed_planning_failure(
                stop_reason="PLANNING_OUTPUT_UNFINISHED",
                summary="planning response was ended by a content filter or provider error",
                cost_usd=attempt_cost,
            )

        try:
            decision = parse_planning_turn(response.output_text)
        except PlanningTurnParseError as exc:
            self._last_non_progress_kind = "UNPARSEABLE"
            self._parse_failure_code = exc.code  # the next turn's notice; the repeat signature is unchanged (#403)
            from optimus.acp.debug_trace import acp_debug_log, debug_trace_enabled

            if debug_trace_enabled():
                acp_debug_log(
                    location="planning_loop.py:execute_iteration:unparseable",
                    message="planning turn made no progress",
                    data=_non_progress_payload(self, "UNPARSEABLE", planning_turn, response, exc=exc),
                    hypothesis_id="P12.2-NONPROGRESS",
                    run_id=self._run_id,
                )
            return self._observed(
                IterationOutcome(
                    summary="planning response was unparseable",
                    deterministic_completion=False,
                    failure_signature="UNPARSEABLE",
                    cost_usd=attempt_cost,
                ),
                parse_failure_step(code=exc.code, message=str(exc)),
                planning_turn,
            )

        self._parse_failure_code = None  # this turn parsed: no notice follows it (#403)
        self._last_decision = decision
        if decision.kind is PlanningTurnKind.READ_MORE:
            self._last_non_progress_kind = "READ_MORE"
            from optimus.loops.tools import GuardedLoopToolExecutor, LoopToolBlocked

            if not isinstance(tools, GuardedLoopToolExecutor):
                raise TypeError("planning loop requires GuardedLoopToolExecutor")
            read_evidence: list[PlanningReadEvidence] = []
            try:
                for request in decision.read_requests:
                    read_evidence.append(
                        tools.read_file_range(
                            workspace_root=self._workspace_root,
                            run_id=self._run_id,
                            session_id=self._session_id,
                            execution_mode=self._execution_mode,
                            request=request,
                        )
                    )
            except PlanningEvidenceBudgetError as exc:
                return self._typed_planning_failure(
                    stop_reason=exc.code,
                    summary=str(exc),
                    cost_usd=attempt_cost,
                )
            except PlanningReadError as exc:
                from optimus.acp.debug_trace import acp_debug_log, debug_trace_enabled

                if debug_trace_enabled():
                    acp_debug_log(
                        location="planning_loop.py:execute_iteration",
                        message="planning read rejected",
                        data=_read_rejection_payload(self, exc, request),
                        hypothesis_id="P9.87-READ-REJECT",
                        run_id=self._run_id,
                    )
                return self._typed_planning_failure(
                    stop_reason=exc.code,
                    summary=str(exc),
                    cost_usd=attempt_cost,
                )
            except LoopToolBlocked as exc:
                return self._typed_planning_failure(
                    stop_reason="PLANNING_READ_GUARD_BLOCKED",
                    summary=str(exc),
                    cost_usd=attempt_cost,
                )
            self._observations.extend(
                observations_from_read_evidence(
                    observation_text=decision.observation_text or "",
                    read_evidence=tuple(read_evidence),
                )
            )
            self._current_reads = tuple(read_evidence)
            if self._progress_observer is not None:
                identities, sha256s, byte_counts = planning_read_telemetry_fields(
                    tuple(read_evidence)
                )
                self._progress_observer(
                    PlanningProgressEvent(
                        run_id=self._run_id,
                        session_id=self._session_id,
                        settled_turn=planning_turn,
                        max_planning_turns=self._allowance_end,
                        read_request_count=len(read_evidence),
                        read_identities=identities,
                        source_sha256s=sha256s,
                        read_byte_counts=byte_counts,
                        total_cost_usd=self._total_cost_usd,
                        remaining_budget_usd=self._remaining_cap(state.cost_usd_spent + attempt_cost),
                        gateway_request_ids=tuple(self._gateway_request_ids),
                        wire_retry_count=self._last_wire_retry_count,
                    )
                )
            return self._observed(
                IterationOutcome(
                    summary="planning requested guarded read evidence",
                    deterministic_completion=False,
                    failure_signature=decision.failure_signature,
                    cost_usd=attempt_cost,
                ),
                read_step(
                    (ReadResult(e.path, e.start_byte, e.end_byte, e.source_sha256) for e in read_evidence),
                    self._coverage,
                ),
                planning_turn,
            )

        if decision.kind is PlanningTurnKind.MCP_TOOL:
            self._last_non_progress_kind = "MCP_TOOL"
            # MCP evidence is single-turn: clear prior envelope before attaching the new one.
            self._mcp_evidence_envelope = ""
            output: AgentMcpToolOutput
            call: AgentToolCall
            if decision.mcp_operation == "list":
                output, call = self._mcp_toolbox.mcp_list_tools(decision.mcp_server or "")
            elif decision.mcp_operation == "call":
                output, call = self._mcp_toolbox.mcp_call(
                    decision.mcp_server or "",
                    decision.mcp_tool or "",
                    decision.mcp_arguments or {},
                )
            else:
                return self._typed_planning_failure(
                    stop_reason="PLANNING_UNPARSEABLE_RESPONSE",
                    summary="unsupported MCP operation",
                    cost_usd=attempt_cost,
                )
            self._mcp_tool_calls.append(call)
            self._mcp_evidence_envelope = format_mcp_evidence_envelope(output)
            self._current_reads = ()
            from optimus.acp.debug_trace import acp_debug_log, debug_trace_enabled

            if debug_trace_enabled():
                acp_debug_log(
                    location="planning_loop.py:execute_iteration:mcp_tool",
                    message="planning turn made no progress",
                    data=_non_progress_payload(self, "MCP_TOOL", planning_turn, response, decision=decision, call=call),
                    hypothesis_id="P12.2-NONPROGRESS",
                    run_id=self._run_id,
                )
            return self._observed(
                IterationOutcome(
                    summary="planning requested generic MCP tool evidence",
                    deterministic_completion=False,
                    failure_signature=f"MCP:{decision.mcp_operation}:{decision.mcp_server}",
                    cost_usd=attempt_cost,
                ),
                mcp_step(
                    operation=decision.mcp_operation or "",
                    server=decision.mcp_server or "",
                    tool=decision.mcp_tool or "",
                    arguments=decision.mcp_arguments or {},
                    evidence_envelope=self._mcp_evidence_envelope,
                    results=self._mcp_results,
                ),
                planning_turn,
            )

        if decision.kind is PlanningTurnKind.FINAL_PLAN:
            # The same turn-1-only rule as the initial context the prompt showed, plus this turn's current reads.
            self._final_evidence_sha256s = {
                **(self._initial_workspace_sha256s if planning_turn == 1 else {}),
                **{read.path: read.source_sha256 for read in self._current_reads},
            }
            return IterationOutcome(
                summary="planning settled with a final directive plan",
                deterministic_completion=True,
                failure_signature=None,
                cost_usd=attempt_cost,
                evidence={"planning_turn": str(planning_turn)},
            )

        if decision.kind is PlanningTurnKind.REFUSE:
            return IterationOutcome(
                summary="planning settled with a typed refusal",
                deterministic_completion=True,
                failure_signature=None,
                cost_usd=attempt_cost,
            )

        raise AssertionError(f"unsupported planning decision: {decision.kind}")

    def _planning_resource_stop_after_final_plan(self, *, state: IterationState) -> str | None:
        cap = self.loop_budget_policy.max_budget_usd
        if cap is not None and state.cost_usd_spent >= cap:  # an evaluation cap only (Plan 12.2 Task 11)
            return "PLANNING_BUDGET_EXHAUSTED"
        # Interactive: a final plan that arrives in the step where the clock expired is kept (Design 4).
        if not self._interactive and state.elapsed_minutes(now=self._now()) >= self.loop_budget_policy.max_wall_clock_minutes:
            return "PLANNING_WALL_CLOCK_EXHAUSTED"
        return None

    def _planning_failure_result(
        self,
        *,
        stop_reason: str,
        settled_turns: int,
        refusal_reason: str | None = None,
        detail: str | None = None,
    ) -> PlanningLoopResult:
        return PlanningLoopResult(
            stop_reason=stop_reason,
            settled_turns=settled_turns,
            total_cost_usd=self._total_cost_usd,
            cost_complete=self._cost_complete,
            unknown_cost_attempt_count=self._unknown_cost_attempt_count,
            gateway_request_ids=tuple(self._gateway_request_ids),
            corrective_text=planning_corrective_text(
                stop_reason,
                refusal_reason=refusal_reason,
                workspace_root=self._workspace_root,
                route_stopped=self._route_stopped,
                detail=detail,
            ),
            refusal_reason=(
                planning_corrective_text(
                    "PLANNING_MODEL_REFUSED",
                    refusal_reason=refusal_reason,
                    workspace_root=self._workspace_root,
                )
                if stop_reason == "PLANNING_MODEL_REFUSED" and refusal_reason is not None
                else None
            ),
            evidence_metadata={"settled_turns": str(settled_turns)},
        )

    def to_planning_result(self, loop_result) -> PlanningLoopResult:
        settled_turns = self._turn_offset + loop_result.state.iteration
        # Unconditional halt recheck before any stop-reason conversion (Plan 11.25 Task 6).
        if loop_result.state.human_halt_requested or self._halt_requested():
            return self._planning_failure_result(
                stop_reason="PLANNING_HALTED",
                settled_turns=settled_turns,
            )
        if self._recovery_stop is not None:
            # Stop at a check-in, or one that could not be shown: the actual cause (Design 7).
            stop_reason, detail = self._recovery_stop
            return self._planning_failure_result(stop_reason=stop_reason, settled_turns=settled_turns, detail=detail)

        if loop_result.stop_reason is LoopStopReason.COMPLETED:
            decision = self._last_decision

            if self._typed_planning_stop_reason is not None:
                return self._planning_failure_result(
                    stop_reason=self._typed_planning_stop_reason,
                    settled_turns=settled_turns,
                )

            if decision is not None and decision.kind is PlanningTurnKind.REFUSE:
                return self._planning_failure_result(
                    stop_reason="PLANNING_MODEL_REFUSED",
                    settled_turns=settled_turns,
                    refusal_reason=decision.reason,
                    detail=self._refusal_detail,
                )

            if decision is not None and decision.kind is PlanningTurnKind.FINAL_PLAN:
                resource_stop = self._planning_resource_stop_after_final_plan(state=loop_result.state)
                if resource_stop is not None:
                    return self._planning_failure_result(
                        stop_reason=resource_stop,
                        settled_turns=settled_turns,
                    )
                plan_text = decision.plan_text
                plan_hash = (
                    hashlib.sha256(plan_text.encode("utf-8")).hexdigest()
                    if plan_text is not None
                    else None
                )
                return PlanningLoopResult(
                    stop_reason=None,
                    settled_turns=settled_turns,
                    total_cost_usd=self._total_cost_usd,
                    cost_complete=self._cost_complete,
                    unknown_cost_attempt_count=self._unknown_cost_attempt_count,
                    gateway_request_ids=tuple(self._gateway_request_ids),
                    plan_text=plan_text,
                    plan_hash=plan_hash,
                    provider=self._last_provider,
                    directives=decision.directives,
                    evidence_metadata={"settled_turns": str(settled_turns)},
                    evidence_sha256s=dict(self._final_evidence_sha256s),
                )

            raise AssertionError("planning loop completed without a settled decision")

        if loop_result.stop_reason is LoopStopReason.REPEATED_FAILURE:
            repeated_stops: dict[str | None, str] = {
                "GATEWAY_FAILURE": "PLANNING_GATEWAY_FAILURE",
                "UNPARSEABLE": "PLANNING_UNPARSEABLE_RESPONSE",
                "MCP_TOOL": "PLANNING_REPEATED_MCP_REQUEST",  # not a read (Plan 12.3, Design 7)
            }
            repeated_stop = repeated_stops.get(self._last_non_progress_kind, "PLANNING_REPEATED_READ_REQUEST")
            return self._planning_failure_result(
                stop_reason=repeated_stop,
                settled_turns=settled_turns,
            )

        mapped_stop = _PLANNING_STOP_REASONS.get(loop_result.stop_reason)
        return PlanningLoopResult(
            stop_reason=mapped_stop,
            settled_turns=settled_turns,
            total_cost_usd=self._total_cost_usd,
            cost_complete=self._cost_complete,
            unknown_cost_attempt_count=self._unknown_cost_attempt_count,
            gateway_request_ids=tuple(self._gateway_request_ids),
            corrective_text=planning_corrective_text(
                mapped_stop,
                workspace_root=self._workspace_root,
            ),
            evidence_metadata={"settled_turns": str(settled_turns)},
        )

    def emit_final_progress(self, result: PlanningLoopResult) -> None:
        """Record one content-free telemetry event for the settled/stopped run.

        Per-turn PlanningProgressEvents (emitted from run_iteration's READ_MORE
        branch) never carry a stop reason; this is the only place the final
        outcome (success or any typed stop) gets recorded for evidence/telemetry.
        Skipped when nothing settled (e.g. an immediate halt before any turn ran).
        """
        if self._progress_observer is None or result.settled_turns == 0:
            return
        self._progress_observer(
            PlanningProgressEvent(
                run_id=self._run_id,
                session_id=self._session_id,
                settled_turn=result.settled_turns,
                max_planning_turns=self._allowance_end,
                total_cost_usd=self._total_cost_usd,
                remaining_budget_usd=self._remaining_cap(self._total_cost_usd),
                gateway_request_ids=tuple(self._gateway_request_ids),
                wire_retry_count=self._last_wire_retry_count,
                stop_reason=result.stop_reason,
            )
        )


def _failure_classifier(exc: BaseException) -> Callable[[], tuple[ProviderAttempt, ...]]:
    def classify() -> tuple[ProviderAttempt, ...]:
        return attempts_from_failure(exc)

    return classify


def _unknown_cost_payload(self: _PlanningIterationRunner, exc: Exception, planning_turn: int, wire_attempt: int) -> Callable[[], dict[str, object]]:
    def payload() -> dict[str, object]:
        return {
        "run_id": self._run_id,
        "session_id": self._session_id,
        "planning_turn": planning_turn,
        "wire_attempt": wire_attempt,
        "error_type": type(exc).__name__,
        }

    return payload


def _read_rejection_payload(self: _PlanningIterationRunner, exc: PlanningReadError, request: PlanningReadRequest) -> Callable[[], dict[str, object]]:
    def payload() -> dict[str, object]:
        return {
        "run_id": self._run_id,
        "session_id": self._session_id,
        "stop_reason": exc.code,
        "rejected_path": request.path,
        "start_byte": request.start_byte,
        "end_byte": request.end_byte,
        }

    return payload


def _non_progress_payload(
    self: _PlanningIterationRunner,
    kind: str,
    planning_turn: int,
    response: GatewayResponse,
    *,
    exc: PlanningTurnParseError | None = None,
    decision: PlanningTurnDecision | None = None,
    call: AgentToolCall | None = None,
) -> Callable[[], dict[str, object]]:
    """A turn that made no progress, without its content: never the reply, the parse message (it may
    quote the reply), an MCP server or tool name, or a path (#388)."""

    def payload() -> dict[str, object]:
        data: dict[str, object] = {
            "run_id": self._run_id,
            "session_id": self._session_id,
            "planning_turn": planning_turn,
            "kind": kind,
            "output_bytes": len(response.output_text.encode("utf-8")),
        }
        if exc is not None:
            data["reason_code"] = exc.code
        if decision is not None and call is not None:
            data["mcp_operation"] = decision.mcp_operation
            data["authorization_outcome"] = bounded(call.authorization_outcome, _MCP_AUTHORIZATION_OUTCOMES)
        return data

    return payload
