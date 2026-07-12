from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from optimus.agent.directives import AgentDirectiveParseError, AgentPlanDirectives, parse_agent_plan
from optimus.agent.prompts import build_multi_turn_planner_input
from optimus.agent.workspace_context import DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.guardrails.pre_tool import PreToolGuard
from optimus.loops.completion import DeterministicCompletionEvaluator
from optimus.loops.controller import GoalLoopController
from optimus.loops.ledger import InMemoryProgressLedger
from optimus.loops.models import IterationOutcome, IterationState, LoopBudgetPolicy, LoopStopReason, LoopToolExecutorProtocol
from optimus.retry.policy import RetryController, RetryPolicy
from optimus.runtime.modes import ExecutionMode
from optimus.telemetry.subjects import sanitize_workspace_text

PlanningGatewayUsageCallback = Callable[[GatewayUsage, int, int], None]

PLANNING_OBSERVATION_MAX_BYTES = 4 * 1024
PLANNING_NEW_READ_MAX_BYTES = 12 * 1024
_PLACEHOLDER_SOURCE_SHA256 = "0" * 64

_OBSERVE_DIRECTIVE = re.compile(r"^OBSERVE:\s*(.*)$", re.DOTALL)
_READ_RANGE_DIRECTIVE = re.compile(r"^READ:\s+(\S+)#bytes=(\d+):(\d+)\s*$")
_REFUSE_DIRECTIVE = re.compile(r"^REFUSE:\s*(.+)$")
_WRITE_DIRECTIVE = re.compile(r"^WRITE\s+(\S+)\s*$")
_DIRECTIVE_PREFIXES = ("OBSERVE:", "READ:", "WRITE", "TEST", "REFUSE:", "PLAN:")
_REFUSE_REASON_DIRECTIVE_PREFIX = re.compile(
    r"^(?:OBSERVE:|READ:|WRITE(?:\s|$)|TEST\s|PLAN:|CONTENT:|END_CONTENT)"
)
_BULLET_PREFIXES = ("- ", "* ", "+ ")


class PlanningTurnKind(StrEnum):
    READ_MORE = "READ_MORE"
    FINAL_PLAN = "FINAL_PLAN"
    REFUSE = "REFUSE"


class PlanningTurnParseError(ValueError):
    pass


class PlanningReadError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class PlanningEvidenceBudgetError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class PlanningLoopPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_planning_turns: int = Field(default=3, ge=1)
    max_wall_clock_minutes: int = Field(default=30, ge=1)

    def to_loop_budget_policy(self, *, max_cost_usd: Decimal) -> LoopBudgetPolicy:
        if max_cost_usd <= Decimal("0"):
            raise ValueError("max_cost_usd must be positive before constructing a planning loop")
        return LoopBudgetPolicy(
            max_iterations=self.max_planning_turns,
            max_budget_credits=max_cost_usd,
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


class PlanningLoopResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    stop_reason: str | None = None
    settled_turns: int = Field(default=0, ge=0)
    total_cost_usd: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    gateway_request_ids: tuple[str, ...] = ()
    plan_text: str | None = None
    plan_hash: str | None = None
    provider: str | None = None
    directives: AgentPlanDirectives | None = None
    corrective_text: str = ""
    refusal_reason: str | None = None
    evidence_metadata: dict[str, str] = Field(default_factory=dict)


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
    remaining_budget_usd: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    gateway_request_ids: tuple[str, ...] = ()
    wire_retry_count: int = Field(default=0, ge=0)
    stop_reason: str | None = None
    """Set only on the final, settling event for a run; None on intermediate
    READ_MORE progress events."""


PlanningProgressObserver = Callable[[PlanningProgressEvent], None]


def run_planning_with_budget(max_cost_usd: Decimal) -> PlanningLoopResult:
    if max_cost_usd <= Decimal("0"):
        return PlanningLoopResult(stop_reason="PLANNING_BUDGET_EXHAUSTED", settled_turns=0)
    raise NotImplementedError("planning loop runner is implemented in a later task")


def pack_planning_evidence(
    *,
    observations: tuple[PlanningObservation, ...],
    current_reads: tuple[PlanningReadEvidence, ...],
) -> PlanningEvidenceEnvelope:
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
        raise PlanningTurnParseError("no recognized planning-turn grammar")

    refuse_decision = _try_parse_refuse(stripped)
    if refuse_decision is not None:
        return refuse_decision
    if stripped.startswith("REFUSE:"):
        raise PlanningTurnParseError("REFUSE reason must be one non-empty line")

    surface_lines = _directive_surface_lines(stripped)
    if _surface_has_observe(surface_lines):
        return _parse_intermediate_turn(stripped)

    final_decision = _try_parse_final_plan(text)
    if final_decision is not None:
        return final_decision

    if _surface_has_ranged_read(surface_lines):
        return _parse_intermediate_turn(stripped)

    raise PlanningTurnParseError("no recognized planning-turn grammar")


def _directive_surface_lines(text: str) -> tuple[str, ...]:
    lines = text.splitlines()
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
    )


def _surface_has_observe(surface_lines: tuple[str, ...]) -> bool:
    return any(line.startswith("OBSERVE:") for line in surface_lines)


def _surface_has_ranged_read(surface_lines: tuple[str, ...]) -> bool:
    return any(_RANGED_READ_LINE.match(line) is not None for line in surface_lines)


def _parse_intermediate_turn(text: str) -> PlanningTurnDecision:
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
                raise PlanningTurnParseError("multiple OBSERVE directives are not supported")
            observation_text = observe_match.group(1).strip()
            continue

        read_match = _READ_RANGE_DIRECTIVE.match(line)
        if read_match is not None:
            path = _normalize_workspace_relative_path(read_match.group(1))
            start_byte = int(read_match.group(2))
            end_byte = int(read_match.group(3))
            if end_byte <= start_byte:
                raise PlanningTurnParseError("READ range end must be greater than start")
            read_requests.append(
                PlanningReadRequest(path=path, start_byte=start_byte, end_byte=end_byte)
            )
            continue

        if line.startswith(_DIRECTIVE_PREFIXES):
            raise PlanningTurnParseError("intermediate planning turn contains unsupported directive")

        raise PlanningTurnParseError("intermediate planning turn contains unrecognized content")

    if observation_text is None:
        raise PlanningTurnParseError("intermediate planning turn requires OBSERVE")

    if not read_requests:
        raise PlanningTurnParseError("intermediate planning turn requires at least one ranged READ")

    read_request_tuple = tuple(read_requests)
    if (
        planning_observation_carryover_bytes(
            observation_text=observation_text,
            read_requests=read_request_tuple,
        )
        > PLANNING_OBSERVATION_MAX_BYTES
    ):
        raise PlanningTurnParseError("observation exceeds planning observation budget")

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
        raise PlanningTurnParseError("REFUSE reason must be one non-empty line")

    refuse_match = _REFUSE_DIRECTIVE.match(lines[0])
    if refuse_match is None:
        raise PlanningTurnParseError("REFUSE reason must be one non-empty line")

    reason = refuse_match.group(1).strip()
    if not reason:
        raise PlanningTurnParseError("REFUSE reason must be one non-empty line")
    if len(reason.encode("utf-8")) > 512:
        raise PlanningTurnParseError("REFUSE reason exceeds 512 UTF-8 bytes")
    if _REFUSE_REASON_DIRECTIVE_PREFIX.match(reason):
        raise PlanningTurnParseError("REFUSE reason must not contain directive prefixes")

    return PlanningTurnDecision(kind=PlanningTurnKind.REFUSE, reason=reason)


def _try_parse_final_plan(text: str) -> PlanningTurnDecision | None:
    try:
        directives = parse_agent_plan(text)
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
        raise PlanningTurnParseError("READ path must be workspace-relative")
    path = Path(path_text)
    if path.is_absolute() or ".." in path.parts:
        raise PlanningTurnParseError("READ path must be workspace-relative")
    if re.match(r"^[A-Za-z]:[\\/]|^/", path_text):
        raise PlanningTurnParseError("READ path must be workspace-relative")
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
                    raise PlanningTurnParseError(f"duplicate READ ranges for {path}")
                if current.start_byte < other.end_byte and other.start_byte < current.end_byte:
                    raise PlanningTurnParseError(f"overlapping READ ranges for {path}")


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


def planning_corrective_text(
    stop_reason: str | None,
    *,
    refusal_reason: str | None = None,
    workspace_root: Path | None = None,
) -> str:
    if stop_reason == "PLANNING_MODEL_REFUSED" and refusal_reason is not None:
        return sanitize_workspace_text(refusal_reason, workspace_root=workspace_root)
    templates = {
        "PLANNING_REPEATED_READ_REQUEST": "Planning stopped after repeated non-progress read requests.",
        "PLANNING_UNPARSEABLE_RESPONSE": (
            "Planning stopped after repeated responses that did not match the required directive grammar."
        ),
        "PLANNING_BUDGET_EXHAUSTED": "Planning stopped because the run budget was exhausted.",
        "PLANNING_WALL_CLOCK_EXHAUSTED": "Planning stopped because the wall-clock limit was reached.",
        "PLANNING_TURN_LIMIT_EXHAUSTED": "Planning stopped before a final plan could be settled.",
        "PLANNING_HALTED": "Planning was halted before settlement.",
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
        max_cost_usd: Decimal,
        guard: PreToolGuard | None = None,
        now: Callable[[], datetime] | None = None,
        halt_requested: Callable[[], bool] | None = None,
        usage_callback: PlanningGatewayUsageCallback | None = None,
        retry_controller: RetryController | None = None,
        progress_observer: PlanningProgressObserver | None = None,
    ) -> None:
        self._gateway_client = gateway_client
        self._model = model
        self._policy = policy
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

    def run(
        self,
        *,
        run_id: str,
        session_id: str | None,
        task: str,
        initial_workspace_context: str = "",
    ) -> PlanningLoopResult:
        if self._max_cost_usd <= Decimal("0"):
            return PlanningLoopResult(stop_reason="PLANNING_BUDGET_EXHAUSTED", settled_turns=0)

        from optimus.loops.tools import GuardedLoopToolExecutor

        iteration_runner = _PlanningIterationRunner(
            gateway_client=self._gateway_client,
            model=self._model,
            task=task,
            initial_workspace_context=initial_workspace_context,
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
        )
        controller = GoalLoopController(
            policy=iteration_runner.loop_budget_policy,
            runner=iteration_runner,
            tools=GuardedLoopToolExecutor(guard=self._guard),
            evaluator=DeterministicCompletionEvaluator(
                completed=False,
                reason="planning loop uses per-turn settlement",
            ),
            ledger=InMemoryProgressLedger(),
            halt_requested=self._halt_requested,
            now=self._now,
        )
        loop_result = controller.run(
            IterationState(
                run_id=run_id,
                session_id=session_id,
                goal=task,
                completion_condition=task,
                started_at=self._now(),
            )
        )
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
        workspace_root: Path,
        run_id: str,
        session_id: str | None,
        execution_mode: ExecutionMode,
        policy: PlanningLoopPolicy,
        loop_budget_policy: LoopBudgetPolicy,
        max_cost_usd: Decimal,
        now: Callable[[], datetime],
        usage_callback: PlanningGatewayUsageCallback | None,
        retry_controller: RetryController,
        progress_observer: PlanningProgressObserver | None,
        halt_requested: Callable[[], bool] | None = None,
    ) -> None:
        self._gateway_client = gateway_client
        self._model = model
        self._task = task
        self._initial_workspace_context = initial_workspace_context
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
        self._observations: list[PlanningObservation] = []
        self._current_reads: tuple[PlanningReadEvidence, ...] = ()
        self._gateway_request_ids: list[str] = []
        self._total_cost_usd = Decimal("0")
        self._last_decision: PlanningTurnDecision | None = None
        self._last_provider: str | None = None
        self._last_wire_retry_count = 0
        self._typed_planning_stop_reason: str | None = None
        self._last_non_progress_kind: Literal["READ_MORE", "UNPARSEABLE"] | None = None
        self._halt_requested = halt_requested or (lambda: False)

    def _typed_planning_failure(
        self,
        *,
        stop_reason: str,
        summary: str,
        cost_credits: Decimal,
    ) -> IterationOutcome:
        self._typed_planning_stop_reason = stop_reason
        return IterationOutcome(
            summary=summary,
            deterministic_completion=True,
            failure_signature=None,
            cost_credits=cost_credits,
        )

    def _invoke_planning_gateway(
        self,
        *,
        planning_turn: int,
        prompt: str,
    ) -> tuple[GatewayResponse, Decimal]:
        attempt_cost = Decimal("0")
        wire_attempt = 0

        def operation() -> GatewayResponse:
            nonlocal attempt_cost, wire_attempt
            wire_attempt += 1
            response = self._gateway_client.create_response(
                model=self._model,
                input_text=prompt,
                metadata={
                    "run_id": self._run_id,
                    "session_id": self._session_id,
                    "purpose": "planning_turn",
                    "planning_turn": planning_turn,
                },
            )
            attempt_cost = response.gateway_usage.cost_usd
            self._last_provider = response.gateway_usage.provider
            if self._usage_callback is not None:
                self._usage_callback(response.gateway_usage, planning_turn, wire_attempt)
            return response

        retry_result = self._retry_controller.run(operation)
        if retry_result.value is None:
            raise RuntimeError("planning gateway request failed after retries")
        self._last_wire_retry_count = retry_result.retry_count
        return retry_result.value, attempt_cost

    def run_iteration(self, state: IterationState, tools: LoopToolExecutorProtocol) -> IterationOutcome:
        planning_turn = state.iteration + 1
        remaining_budget = max(Decimal("0"), self._max_cost_usd - state.credits_spent)
        remaining_wall_clock = max(
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
                cost_credits=Decimal("0"),
            )
        prompt = build_multi_turn_planner_input(
            self._task,
            planning_turn=planning_turn,
            max_planning_turns=self._policy.max_planning_turns,
            remaining_budget_usd=remaining_budget,
            remaining_wall_clock_minutes=remaining_wall_clock,
            carried_observations_envelope=carried_envelope,
            current_read_evidence_envelope=current_envelope,
            initial_workspace_context=self._initial_workspace_context if planning_turn == 1 else "",
        )
        try:
            response, attempt_cost = self._invoke_planning_gateway(planning_turn=planning_turn, prompt=prompt)
        except RuntimeError:
            return IterationOutcome(
                summary="planning gateway request failed after retries",
                deterministic_completion=False,
                failure_signature="GATEWAY_FAILURE",
                cost_credits=Decimal("0"),
            )
        self._gateway_request_ids.append(response.gateway_usage.gateway_request_id)
        self._total_cost_usd += attempt_cost

        try:
            decision = parse_planning_turn(response.output_text)
        except PlanningTurnParseError:
            self._last_non_progress_kind = "UNPARSEABLE"
            return IterationOutcome(
                summary="planning response was unparseable",
                deterministic_completion=False,
                failure_signature="UNPARSEABLE",
                cost_credits=attempt_cost,
            )

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
                    cost_credits=attempt_cost,
                )
            except PlanningReadError as exc:
                return self._typed_planning_failure(
                    stop_reason=exc.code,
                    summary=str(exc),
                    cost_credits=attempt_cost,
                )
            except LoopToolBlocked as exc:
                return self._typed_planning_failure(
                    stop_reason="PLANNING_READ_GUARD_BLOCKED",
                    summary=str(exc),
                    cost_credits=attempt_cost,
                )
            self._observations.extend(
                observations_from_read_evidence(
                    observation_text=decision.observation_text or "",
                    read_evidence=tuple(read_evidence),
                )
            )
            self._current_reads = tuple(read_evidence)
            if self._progress_observer is not None:
                self._progress_observer(
                    PlanningProgressEvent(
                        run_id=self._run_id,
                        session_id=self._session_id,
                        settled_turn=planning_turn,
                        max_planning_turns=self._policy.max_planning_turns,
                        read_request_count=len(read_evidence),
                        read_identities=tuple(
                            sorted(
                                f"{item.path}#bytes={item.start_byte}:{item.end_byte}"
                                for item in read_evidence
                            )
                        ),
                        source_sha256s=tuple(item.source_sha256 for item in read_evidence),
                        read_byte_counts=tuple(item.end_byte - item.start_byte for item in read_evidence),
                        total_cost_usd=self._total_cost_usd,
                        remaining_budget_usd=max(
                            Decimal("0"),
                            self._max_cost_usd - state.credits_spent - attempt_cost,
                        ),
                        gateway_request_ids=tuple(self._gateway_request_ids),
                        wire_retry_count=self._last_wire_retry_count,
                    )
                )
            return IterationOutcome(
                summary="planning requested guarded read evidence",
                deterministic_completion=False,
                failure_signature=decision.failure_signature,
                cost_credits=attempt_cost,
            )

        if decision.kind is PlanningTurnKind.FINAL_PLAN:
            return IterationOutcome(
                summary="planning settled with a final directive plan",
                deterministic_completion=True,
                failure_signature=None,
                cost_credits=attempt_cost,
                evidence={"planning_turn": str(planning_turn)},
            )

        if decision.kind is PlanningTurnKind.REFUSE:
            return IterationOutcome(
                summary="planning settled with a typed refusal",
                deterministic_completion=True,
                failure_signature=None,
                cost_credits=attempt_cost,
            )

        raise AssertionError(f"unsupported planning decision: {decision.kind}")

    def _planning_resource_stop_after_final_plan(self, *, state: IterationState) -> str | None:
        if state.credits_spent >= self.loop_budget_policy.max_budget_credits:
            return "PLANNING_BUDGET_EXHAUSTED"
        if state.elapsed_minutes(now=self._now()) >= self.loop_budget_policy.max_wall_clock_minutes:
            return "PLANNING_WALL_CLOCK_EXHAUSTED"
        return None

    def _planning_failure_result(
        self,
        *,
        stop_reason: str,
        settled_turns: int,
        refusal_reason: str | None = None,
    ) -> PlanningLoopResult:
        return PlanningLoopResult(
            stop_reason=stop_reason,
            settled_turns=settled_turns,
            total_cost_usd=self._total_cost_usd,
            gateway_request_ids=tuple(self._gateway_request_ids),
            corrective_text=planning_corrective_text(
                stop_reason,
                refusal_reason=refusal_reason,
                workspace_root=self._workspace_root,
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
        settled_turns = loop_result.state.iteration
        if loop_result.stop_reason is LoopStopReason.COMPLETED:
            decision = self._last_decision

            if loop_result.state.human_halt_requested or self._halt_requested():
                return self._planning_failure_result(
                    stop_reason="PLANNING_HALTED",
                    settled_turns=settled_turns,
                )

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
                    gateway_request_ids=tuple(self._gateway_request_ids),
                    plan_text=plan_text,
                    plan_hash=plan_hash,
                    provider=self._last_provider,
                    directives=decision.directives,
                    evidence_metadata={"settled_turns": str(settled_turns)},
                )

            raise AssertionError("planning loop completed without a settled decision")

        if loop_result.stop_reason is LoopStopReason.REPEATED_FAILURE:
            mapped_stop = (
                "PLANNING_UNPARSEABLE_RESPONSE"
                if self._last_non_progress_kind == "UNPARSEABLE"
                else "PLANNING_REPEATED_READ_REQUEST"
            )
            return self._planning_failure_result(
                stop_reason=mapped_stop,
                settled_turns=settled_turns,
            )

        mapped_stop = _PLANNING_STOP_REASONS.get(loop_result.stop_reason)
        return PlanningLoopResult(
            stop_reason=mapped_stop,
            settled_turns=settled_turns,
            total_cost_usd=self._total_cost_usd,
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
                max_planning_turns=self._policy.max_planning_turns,
                total_cost_usd=self._total_cost_usd,
                remaining_budget_usd=max(Decimal("0"), self._max_cost_usd - self._total_cost_usd),
                gateway_request_ids=tuple(self._gateway_request_ids),
                wire_retry_count=self._last_wire_retry_count,
                stop_reason=result.stop_reason,
            )
        )
