from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from optimus.agent.directives import AgentDirectiveParseError, AgentPlanDirectives, parse_agent_plan
from optimus.agent.workspace_context import DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES
from optimus.loops.models import LoopBudgetPolicy

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
    largest_header_bytes = max(
        planning_observation_serialized_bytes(
            PlanningObservation(
                path=request.path,
                start_byte=request.start_byte,
                end_byte=request.end_byte,
                source_sha256=_PLACEHOLDER_SOURCE_SHA256,
                observation_text="",
            )
        )
        for request in read_requests
    )
    return PLANNING_OBSERVATION_MAX_BYTES - largest_header_bytes


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

    final_decision = _try_parse_final_plan(stripped)
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
    max_observation_text_bytes = max_planning_observation_text_bytes(read_request_tuple)
    observation_text_bytes = len(observation_text.encode("utf-8"))
    if observation_text_bytes > max_observation_text_bytes:
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
