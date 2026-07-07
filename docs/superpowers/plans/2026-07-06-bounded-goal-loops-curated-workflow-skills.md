# Bounded Goal Loops and Curated Workflow Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Phase 1 architectural support for bounded goal-driven loops and trusted workflow skills without making autonomous loops the default execution mode or widening the existing permission surface.

**Architecture:** Build a small `optimus.loops` package for loop budgets, iteration state, progress ledger entries, completion evaluation, stop-reason decisions, and controller-owned guarded iteration execution. The controller owns the `GuardedLoopToolExecutor` and passes it into every runner, so loop tool use is guarded by construction rather than by convention. Build a separate `optimus.skills` package for curated Markdown skills with lazy body loading, full-content hashing, deterministic match/trust checks, and invocation policy that narrows tool use before delegating to the existing `PreToolGuard`, `PermissionPolicy`, `ToolRegistry`, and MCP trust controls. Deterministic completion predicates are primary; the optional Gateway completion evaluator can confirm but cannot override failing structured evidence. Model-touching completion evaluation routes through the Optimus Gateway and records usage/cost; deterministic stop checks and skill resolution remain zero-token.

**Tech Stack:** Python >=3.14, pydantic >=2.8, pytest, pytest-asyncio, coverage.py, pytest-cov, stdlib `datetime`, `decimal`, `hashlib`, `json`, `pathlib`, `time`, `typing.Protocol`, existing `optimus.gateway`, `optimus.guardrails`, `optimus.runtime`, `optimus.telemetry`, `optimus.tools`, and `optimus.usage`. No new runtime dependency is required.

---

## Source Anchors

- `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, Plan 9: `GoalLoopController`, `IterationState`, `CompletionEvaluator`, `ProgressLedger`, `LoopBudgetPolicy`, `SkillRegistry`, `SkillManifest`, `SkillTrustPolicy`, and `SkillInvocationPolicy`.
- `docs/superpowers/plans/2026-07-06-plan-8-5-release-gate-hardening.md`: Plan 9 starts after the release-gate hardening layer exists; it does not reopen shadow promotion, one-key scanning, golden harness wiring, or command timeout work.
- `docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.0.pdf`, sections 7, 8, 10, and 11:
  - Bounded loops are Phase 1 architectural support, not the default execution mode.
  - Loops require measurable completion criteria, `max_iterations`, `max_budget_credits`, `max_wall_clock_minutes`, per-iteration evidence, clean diff checks, pre-tool guard enforcement, human approval for escalation, and repeated-failure termination.
  - Skills are curated, reviewed, versioned Markdown artifacts with YAML frontmatter, loaded only on match, and blocked when draft/untrusted in Agent mode.
  - A skill's `allowed_tools` can narrow tool use but can never widen the agent's tool surface or override project/user deny rules.
- `docs/Optimus-Cost-Agent-LLD-v2.38.pdf`, sections 12C and 12D:
  - Loop contracts: `GoalLoopController`, `IterationState`, `CompletionEvaluator`, `ProgressLedger`, `LoopBudgetPolicy`, `LoopStopReason`.
  - Persistent state lives in files, git history, task manifests, traces, and the evidence ledger, not an ever-growing chat context.
  - Completion evaluator is a cheap Gateway-routed model, not the main reasoning model.
  - Skill contracts: `SkillRegistry`, `SkillManifest`, `SkillTrustPolicy`, and `SkillInvocationPolicy`.
- `docs/Optimus-Cost-Agent-Test-Strategy-v1.4.pdf`, sections 14.8 and 14.9:
  - Loop tests must stop on completion, max iterations, budget exhaustion, and repeated failure, and must never bypass permission or shell enforcement.
  - Skill tests must load only on match, block draft/untrusted skills, enforce declared `allowed_tools`, and prove skills cannot override project/user deny rules.
- Existing implementation anchors:
  - `src/optimus/guardrails/pre_tool.py`
  - `src/optimus/guardrails/permissions.py`
  - `src/optimus/guardrails/audit.py`
  - `src/optimus/tools/registry.py`
  - `src/optimus/tools/policy.py`
  - `src/optimus/gateway/client.py`
  - `src/optimus/gateway/models.py`
  - `src/optimus/telemetry/events.py`
  - `src/optimus/runtime/state.py`

## Plan 8.5 Follow-Up Classification

These items were reviewed before writing Plan 9. Recommended disposition:

| Follow-up | Blocking before Plan 9? | Plan 9 scope? | Recommendation |
| --- | --- | --- | --- |
| Staging Gateway E2E evidence | No for Plan 9 coding; yes before Sprint 1 sign-off is claimed | No | Treat as release evidence after Plan 8.5 and after Plan 9 verification. Plan 9 tests should not depend on a live staging gateway. |
| Shadow reuse across retries | No | No | Keep after Plan 9 as a performance optimization. Plan 9 does not use shadow workspace retry copies directly. |
| Optional exception import cleanup | No | No | The live tree already contains `src/optimus/gates/exceptions.py`. If a reviewer finds residual lazy imports, fix as a small Plan 8.5 cleanup PR, not inside Plan 9. |

**Decision:** Do not create an in-between implementation plan by default. Plan 9 should proceed next. Create a small Plan 8.6 only if reviewers require an automated staging Gateway result producer before any further Phase 1 feature work; otherwise the staging evidence item belongs in release sign-off notes.

## Scope

### In Scope

- Loop domain models, stop reasons, budget policy, and append-only progress records.
- A JSONL progress ledger suitable for files under a workspace-local reports/state directory, with typed fields, telemetry redaction, and workspace-bound path validation.
- A goal-loop controller that executes one iteration at a time, owns and passes guarded tools into the runner, checks deterministic stop reasons before and after each iteration, and records all stop decisions.
- Explicit stop precedence: `HUMAN_HALT > REPEATED_FAILURE > BUDGET_EXHAUSTED > WALL_CLOCK > MAX_ITERATIONS`. This preserves the most actionable stop reason when multiple deterministic limits become true at the same boundary.
- A Gateway-routed completion evaluator with strict JSON parsing, fake-transport unit tests proving one-key Gateway usage and returned `GatewayUsage` cost propagation, and deterministic evidence gating so model output cannot override a failed predicate.
- A guarded loop tool executor that requires `PreToolGuard` before shell/file/web/MCP actions inside loop iterations.
- Curated skill manifests parsed from Markdown frontmatter using stdlib-only parsing.
- Skill matching by description keywords and file globs, trust blocking in Agent mode, full-content hashing, lazy body loading, and draft-only model-authored skills.
- Skill invocation policy that intersects skill-declared tools with the requested action and still delegates to `PreToolGuard` and `PermissionPolicy`.
- Telemetry events for goal-loop stop decisions and skill match/selection/invocation outcomes.
- Focused unit and integration tests for Test Strategy 14.8 and 14.9.

### Out of Scope

- Making bounded loops the default execution mode.
- Building a full autonomous planner, multi-agent scheduler, or long-running background service.
- Adding local OpenAI, Tavily, OpenRouter, GLM, LangSmith, Anthropic, Azure OpenAI, or provider keys.
- Adding PyYAML or any new runtime dependency for frontmatter parsing.
- Plan 10 context-window optimization or enforcing uncalibrated context/cost savings gates.
- Reopening Plan 8.5 shadow promotion, one-key scan, golden harness, command timeout, or release runner work.

### Dependency Notes

- Start implementation only after the Plan 8.5 branch is accepted or merged to `main`.
- Branch from latest `main` using the repo convention, for example `agent/cursor/bounded-goal-loops-skills`.
- Keep local runtime credentials limited to `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`.
- Commit steps below are implementation checkpoints. Do not run `git commit`, push, delete branches, or rewrite history unless the user explicitly approves.

## File Structure

- Create: `src/optimus/loops/__init__.py` - public exports for loop contracts.
- Create: `src/optimus/loops/models.py` - `LoopStopReason`, `LoopBudgetPolicy`, `IterationState`, `IterationOutcome`, `CompletionEvaluation`, controller-facing protocols.
- Create: `src/optimus/loops/ledger.py` - `ProgressLedgerEntry`, in-memory ledger, JSONL ledger.
- Create: `src/optimus/loops/completion.py` - deterministic evidence predicate and Gateway evaluator implementing the `CompletionEvaluatorProtocol` from `models.py`.
- Create: `src/optimus/loops/controller.py` - `GoalLoopController`, `IterationRunner` protocol, stop-reason evaluation, mid-loop halt/deadline/budget context.
- Create: `src/optimus/loops/tools.py` - guarded loop tool executor that delegates to `PreToolGuard`.
- Create: `src/optimus/telemetry/subjects.py` - shared workspace-path masking for audit, telemetry, and ledger payloads.
- Create: `src/optimus/telemetry/serialization.py` - shared JSON-safe serializer for Decimal-bearing telemetry and loop ledger payloads.
- Modify: `src/optimus/telemetry/redaction.py` - add generic token/password/secret assignment redaction.
- Modify: `src/optimus/guardrails/pre_tool.py` - reuse shared subject sanitization instead of owning a duplicate private helper.
- Create: `src/optimus/skills/__init__.py` - public exports for skill contracts.
- Create: `src/optimus/skills/models.py` - `SkillManifest`, `SkillTrustLevel`, `SkillMatch`.
- Create: `src/optimus/skills/registry.py` - Markdown frontmatter parser, manifest loader, deterministic matcher, lazy skill body loader.
- Create: `src/optimus/skills/invocation.py` - `SkillTrustPolicy`, `SkillInvocationPolicy`, invocation decisions.
- Modify: `src/optimus/telemetry/events.py` - add `GOAL_LOOP`, `SKILL_SELECTION`, and `SKILL_INVOCATION` events.
- Modify: `tests/fixtures/golden_tasks/phase1_golden_tasks.json` - add a Plan 9 golden task only if the existing schema supports a non-invasive fixture entry; otherwise keep Plan 9 verification in unit/integration tests.
- Create: `tests/unit/loops/test_models.py`
- Create: `tests/unit/loops/test_ledger.py`
- Create: `tests/unit/loops/test_completion.py`
- Create: `tests/unit/loops/test_controller.py`
- Create: `tests/unit/loops/test_tools.py`
- Create: `tests/unit/skills/test_registry.py`
- Create: `tests/unit/skills/test_invocation.py`
- Create: `tests/integration/loops/test_goal_loop_guardrail_flow.py`
- Create: `tests/integration/skills/test_skill_guardrail_flow.py`
- Modify: `tests/unit/telemetry/test_events.py`
- Create: `tests/unit/telemetry/test_serialization.py`
- Modify: `README.md` - document bounded loops and curated skills behavior.

## Human Agile Sizing

This is about 1-2 weeks of human development effort:

- Day 1: loop models and progress ledger.
- Day 2: stop-reason controller and deterministic iteration runner tests.
- Day 3: Gateway completion evaluator and cost propagation.
- Day 4: guarded loop tool executor and integration tests.
- Day 5: skill manifest parsing and registry matching.
- Day 6: skill trust and invocation policy.
- Day 7: telemetry events and cross-package integration.
- Day 8: README and focused verification.
- Day 9-10: reviewer feedback and release-gate/golden fixture adjustments if needed.

## Commit Policy for Execution

Each task includes a commit step because the Superpowers workflow favors small reviewable checkpoints. In this repo, commit steps are approval-gated: do not run `git commit`, push, delete branches, or rewrite history unless the user explicitly approves that action. If commit approval has not been granted, treat each commit step as a local checkpoint: run the narrow tests, run `git diff --check`, and leave the working tree ready for review.

---

## Task 1: Loop Models and Progress Ledger

**Traceability:** LLD 12C, Guardrails Strategy 7.2, Test Strategy 14.8 prerequisite

**Files:**
- Create: `src/optimus/loops/__init__.py`
- Create: `src/optimus/loops/models.py`
- Create: `src/optimus/loops/ledger.py`
- Create: `src/optimus/telemetry/serialization.py`
- Create: `src/optimus/telemetry/subjects.py`
- Modify: `src/optimus/telemetry/redaction.py`
- Modify: `src/optimus/telemetry/events.py`
- Modify: `src/optimus/guardrails/pre_tool.py`
- Create: `tests/unit/loops/test_models.py`
- Create: `tests/unit/loops/test_ledger.py`
- Create: `tests/unit/telemetry/test_serialization.py`
- Modify: `tests/unit/telemetry/test_events.py`
- Modify: `tests/unit/guardrails/test_pre_tool_guard.py`

- [x] **Step 1: Write failing model and ledger tests**

Create `tests/unit/loops/test_models.py`:

```python
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from optimus.loops.models import IterationOutcome, IterationState, LoopBudgetPolicy, LoopStopReason


def test_loop_budget_policy_requires_positive_bounds():
    with pytest.raises(ValidationError):
        LoopBudgetPolicy(max_iterations=0, max_budget_credits=Decimal("1"), max_wall_clock_minutes=5)

    with pytest.raises(ValidationError):
        LoopBudgetPolicy(max_iterations=1, max_budget_credits=Decimal("0"), max_wall_clock_minutes=5)

    with pytest.raises(ValidationError):
        LoopBudgetPolicy(max_iterations=1, max_budget_credits=Decimal("1"), max_wall_clock_minutes=0)


def test_iteration_state_requires_timezone_aware_start_time():
    with pytest.raises(ValidationError, match="started_at must be timezone-aware"):
        IterationState(
            run_id="run-1",
            session_id=None,
            goal="Migrate auth call sites",
            completion_condition="tests/unit/auth pass",
            started_at=datetime(2026, 7, 6),
        )


def test_iteration_state_tracks_budget_and_repeated_failures():
    started = datetime.now(tz=UTC)
    state = IterationState(
        run_id="run-1",
        session_id="session-1",
        goal="Migrate auth call sites",
        completion_condition="tests/unit/auth pass",
        started_at=started,
    )

    failed_once = state.record_outcome(
        IterationOutcome(
            summary="pytest failed",
            cost_credits=Decimal("0.25"),
            failure_signature="tests/unit/auth/test_login.py::test_login",
        )
    )
    failed_twice = failed_once.record_outcome(
        IterationOutcome(
            summary="same pytest failed",
            cost_credits=Decimal("0.10"),
            failure_signature="tests/unit/auth/test_login.py::test_login",
        )
    )

    assert failed_twice.iteration == 2
    assert failed_twice.credits_spent == Decimal("0.35")
    assert failed_twice.repeated_failure_count == 2
    assert failed_twice.last_failure_signature == "tests/unit/auth/test_login.py::test_login"
    assert failed_twice.elapsed_minutes(now=started + timedelta(minutes=3)) == 3


def test_loop_stop_reason_values_are_stable_for_traces():
    assert {reason.value for reason in LoopStopReason} == {
        "COMPLETED",
        "MAX_ITERATIONS",
        "BUDGET_EXHAUSTED",
        "WALL_CLOCK",
        "REPEATED_FAILURE",
        "HUMAN_HALT",
    }
```

Create `tests/unit/loops/test_ledger.py`:

```python
import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from optimus.loops.ledger import InMemoryProgressLedger, JsonlProgressLedger, ProgressLedgerEntry
from optimus.loops.models import LoopStopReason


def entry(iteration: int = 1) -> ProgressLedgerEntry:
    return ProgressLedgerEntry(
        run_id="run-1",
        session_id="session-1",
        iteration=iteration,
        goal="Migrate auth call sites",
        summary="updated one file",
        cost_credits=Decimal("0.125"),
        stop_reason=None,
        failure_signature=None,
        occurred_at=datetime(2026, 7, 6, tzinfo=UTC),
    )


def test_in_memory_progress_ledger_is_append_only():
    ledger = InMemoryProgressLedger()

    ledger.append(entry(1))
    ledger.append(entry(2))

    assert tuple(item.iteration for item in ledger.entries(run_id="run-1")) == (1, 2)
    assert ledger.entries(run_id="other") == ()


def test_jsonl_progress_ledger_writes_redacted_json_lines(tmp_path):
    path = tmp_path / "reports" / "loop-progress.jsonl"
    ledger = JsonlProgressLedger(path, workspace_root=tmp_path)

    ledger.append(entry(1))
    ledger.append(
        ProgressLedgerEntry(
            run_id="run-1",
            session_id=None,
            iteration=2,
            goal="Migrate auth call sites",
            summary=f"stopped after token=secret-token in {tmp_path / 'src' / 'optimus' / 'x.py'}",
            cost_credits=Decimal("0"),
            stop_reason=LoopStopReason.MAX_ITERATIONS,
            failure_signature="Authorization: Bearer secret-token",
            occurred_at=datetime(2026, 7, 6, tzinfo=UTC),
        )
    )

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    decoded = [json.loads(line) for line in lines]
    assert decoded[0]["cost_credits"] == "0.125"
    assert decoded[1]["stop_reason"] == "MAX_ITERATIONS"
    assert "secret-token" not in lines[1]
    assert "<workspace>/src/optimus/x.py" in lines[1]


def test_jsonl_progress_ledger_rejects_path_outside_workspace(tmp_path):
    outside = tmp_path.parent / "outside.jsonl"

    with pytest.raises(ValueError, match="progress ledger path must stay under workspace_root"):
        JsonlProgressLedger(outside, workspace_root=tmp_path)
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/loops/test_models.py tests/unit/loops/test_ledger.py -v
```

Expected: FAIL because `optimus.loops` does not exist.

- [x] **Step 3: Add loop models**

Create `src/optimus/loops/models.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoopStopReason(StrEnum):
    COMPLETED = "COMPLETED"
    MAX_ITERATIONS = "MAX_ITERATIONS"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    WALL_CLOCK = "WALL_CLOCK"
    REPEATED_FAILURE = "REPEATED_FAILURE"
    HUMAN_HALT = "HUMAN_HALT"


class LoopBudgetPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_iterations: int = Field(ge=1)
    max_budget_credits: Decimal = Field(gt=Decimal("0"))
    max_wall_clock_minutes: int = Field(ge=1)
    repeated_failure_limit: int = Field(default=3, ge=2)


class CompletionEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True)

    completed: bool
    reason: str = Field(min_length=1)
    confidence: Decimal = Field(default=Decimal("1"), ge=Decimal("0"), le=Decimal("1"))
    cost_credits: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    gateway_request_id: str | None = None


class IterationOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    summary: str = Field(min_length=1)
    cost_credits: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    failure_signature: str | None = None
    deterministic_completion: bool = False
    evidence: dict[str, str] = Field(default_factory=dict)


class CompletionEvaluatorProtocol(Protocol):
    def evaluate(self, state: "IterationState", ledger: Any) -> CompletionEvaluation:
        raise NotImplementedError


class LoopToolExecutorProtocol(Protocol):
    """Marker protocol for guarded loop tool bundles passed through the controller."""


class IterationState(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    session_id: str | None
    goal: str = Field(min_length=1)
    completion_condition: str = Field(min_length=1)
    started_at: datetime
    deadline_at: datetime | None = None
    remaining_budget_credits: Decimal | None = None
    iteration: int = Field(default=0, ge=0)
    credits_spent: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    last_failure_signature: str | None = None
    repeated_failure_count: int = Field(default=0, ge=0)
    human_halt_requested: bool = False

    @field_validator("started_at")
    @classmethod
    def require_timezone_aware_started_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("started_at must be timezone-aware")
        return value

    def record_outcome(self, outcome: IterationOutcome) -> "IterationState":
        repeated = 0
        if outcome.failure_signature is not None:
            repeated = self.repeated_failure_count + 1 if outcome.failure_signature == self.last_failure_signature else 1
        return self.model_copy(
            update={
                "iteration": self.iteration + 1,
                "credits_spent": self.credits_spent + outcome.cost_credits,
                "last_failure_signature": outcome.failure_signature,
                "repeated_failure_count": repeated,
            }
        )

    def record_completion_evaluation(self, evaluation: CompletionEvaluation) -> "IterationState":
        return self.model_copy(update={"credits_spent": self.credits_spent + evaluation.cost_credits})

    def request_halt(self) -> "IterationState":
        return self.model_copy(update={"human_halt_requested": True})

    def with_runtime_limits(self, *, policy: LoopBudgetPolicy) -> "IterationState":
        deadline_at = self.started_at + timedelta(minutes=policy.max_wall_clock_minutes)
        remaining = max(Decimal("0"), policy.max_budget_credits - self.credits_spent)
        return self.model_copy(update={"deadline_at": deadline_at, "remaining_budget_credits": remaining})

    def elapsed_minutes(self, *, now: datetime) -> int:
        elapsed = now - self.started_at
        return max(0, int(elapsed.total_seconds() // 60))
```

Create `src/optimus/loops/__init__.py`:

```python
from optimus.loops.models import (
    CompletionEvaluation,
    CompletionEvaluatorProtocol,
    IterationOutcome,
    IterationState,
    LoopBudgetPolicy,
    LoopStopReason,
    LoopToolExecutorProtocol,
)

__all__ = [
    "CompletionEvaluation",
    "CompletionEvaluatorProtocol",
    "IterationOutcome",
    "IterationState",
    "LoopBudgetPolicy",
    "LoopStopReason",
    "LoopToolExecutorProtocol",
]
```

- [x] **Step 4: Add progress ledgers**

Create `src/optimus/loops/ledger.py`:

```python
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from threading import Lock
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from optimus.loops.models import LoopStopReason
from optimus.telemetry.redaction import redact_for_telemetry
from optimus.telemetry.serialization import json_safe
from optimus.telemetry.subjects import sanitize_workspace_text


class ProgressLedgerEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    session_id: str | None
    iteration: int = Field(ge=0)
    goal: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    cost_credits: Decimal = Field(ge=Decimal("0"))
    stop_reason: LoopStopReason | None
    failure_signature: str | None
    evidence: dict[str, str] = Field(default_factory=dict)
    occurred_at: datetime

    def to_json_dict(self) -> dict[str, object]:
        data = self.model_dump(mode="json")
        return json_safe(redact_for_telemetry(data))


class ProgressLedger(Protocol):
    def append(self, entry: ProgressLedgerEntry) -> None:
        raise NotImplementedError

    def entries(self, *, run_id: str) -> tuple[ProgressLedgerEntry, ...]:
        raise NotImplementedError


class InMemoryProgressLedger:
    def __init__(self) -> None:
        self._lock = Lock()
        self._entries: list[ProgressLedgerEntry] = []

    def append(self, entry: ProgressLedgerEntry) -> None:
        with self._lock:
            self._entries.append(entry)

    def entries(self, *, run_id: str) -> tuple[ProgressLedgerEntry, ...]:
        with self._lock:
            return tuple(entry for entry in self._entries if entry.run_id == run_id)


class JsonlProgressLedger:
    def __init__(self, path: str | Path, *, workspace_root: str | Path) -> None:
        root = Path(workspace_root).resolve()
        candidate = Path(path).resolve(strict=False)
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("progress ledger path must stay under workspace_root") from exc
        self._path = candidate
        self._workspace_root = root
        self._lock = Lock()

    def append(self, entry: ProgressLedgerEntry) -> None:
        # Redaction is idempotent; append-time sanitization adds the workspace-root context.
        payload = _sanitize_workspace_paths(entry.to_json_dict(), workspace_root=self._workspace_root)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.write("\n")

    def entries(self, *, run_id: str) -> tuple[ProgressLedgerEntry, ...]:
        if not self._path.exists():
            return ()
        decoded: list[ProgressLedgerEntry] = []
        with self._path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                entry = ProgressLedgerEntry.model_validate_json(line)
                if entry.run_id == run_id:
                    decoded.append(entry)
        return tuple(decoded)


def _sanitize_workspace_paths(value: object, *, workspace_root: Path) -> object:
    if isinstance(value, dict):
        return {key: _sanitize_workspace_paths(child, workspace_root=workspace_root) for key, child in value.items()}
    if isinstance(value, list):
        return [_sanitize_workspace_paths(child, workspace_root=workspace_root) for child in value]
    if isinstance(value, str):
        return sanitize_workspace_text(value, workspace_root=workspace_root)
    return value
```

Create `src/optimus/telemetry/serialization.py` in this task and move the current private JSON-safe helper there:

```python
from __future__ import annotations

from decimal import Decimal
from typing import Any


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: json_safe(child) for key, child in value.items()}
    if isinstance(value, list):
        return [json_safe(child) for child in value]
    if isinstance(value, Decimal):
        return str(value)
    return value
```

Create `src/optimus/telemetry/subjects.py` and move the workspace replacement and secret-subject behavior out of `src/optimus/guardrails/pre_tool.py`:

```python
from __future__ import annotations

import re
from pathlib import Path

from optimus.telemetry.redaction import redact_for_telemetry

_SUBJECT_SECRET_VALUE_PATTERN = re.compile(r"(?i)\b(token|password|secret|credential|api[_-]?key)(\s+)\S+")


def sanitize_workspace_text(text: str, *, workspace_root: str | Path | None) -> str:
    subject = text.replace("\\", "/")
    if workspace_root is not None:
        workspace_text = Path(workspace_root).resolve().as_posix().rstrip("/")
        subject = subject.replace(workspace_text, "<workspace>")
    subject = str(redact_for_telemetry(subject))
    return _SUBJECT_SECRET_VALUE_PATTERN.sub(r"\1\2**********", subject)
```

Update `src/optimus/telemetry/redaction.py` to cover URL userinfo and generic free-text assignments used by shell commands, summaries, and ledger entries. Keep whitespace-separated redaction out of this shared redactor so ordinary prompt/response telemetry such as "token refresh logic" and "password reset flow" remains intact:

```python
_URL_USERINFO_PATTERN = re.compile(r"(?i)(https?://)[^/\s:@]+:[^@\s/]+@")
_GENERIC_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(token|password|secret|credential|api[_-]?key)((?:=|:)\s*)\S+"
)


def _redact_free_text(text: str) -> str:
    redacted = _URL_USERINFO_PATTERN.sub(r"\1**********@", text)
    redacted = _BEARER_TOKEN_PATTERN.sub(r"\1**********", redacted)
    redacted = _ENV_ASSIGNMENT_PATTERN.sub(r"\1=**********", redacted)
    redacted = _GENERIC_SECRET_ASSIGNMENT_PATTERN.sub(r"\1\2**********", redacted)
    redacted = _API_KEY_HEADER_PATTERN.sub(r"\1: **********", redacted)
    redacted = _X_API_KEY_HEADER_PATTERN.sub("x-api-key: **********", redacted)
    return redacted
```

Then update `src/optimus/guardrails/pre_tool.py` to import `sanitize_workspace_text` and implement `_sanitize_subject()` as:

```python
def _sanitize_subject(request: PreToolRequest, *, workspace_root: Path | None) -> str:
    subject = " ".join(request.command) if request.command else request.target_path or request.action
    if subject is None:
        return ""
    return sanitize_workspace_text(subject, workspace_root=workspace_root)
```

Remove the old private `_redact_secret_values()` helper from `pre_tool.py` after this change; the redaction logic now belongs in `optimus.telemetry.redaction`.

Update `TelemetryEvent.to_json_dict()` in `src/optimus/telemetry/events.py` to import `json_safe` from `optimus.telemetry.serialization` and call `json_safe(redact_for_telemetry(encoded))`. Remove the private `_json_safe()` helper from `events.py` after updating its tests.

Create `tests/unit/telemetry/test_serialization.py`:

```python
from decimal import Decimal

from optimus.telemetry.redaction import redact_for_telemetry
from optimus.telemetry.serialization import json_safe
from optimus.telemetry.subjects import sanitize_workspace_text


def test_json_safe_converts_decimal_without_float_rounding():
    assert json_safe({"cost": Decimal("0.125")}) == {"cost": "0.125"}


def test_sanitize_workspace_text_masks_workspace_and_generic_token(tmp_path):
    text = f"token=secret-token {tmp_path / 'src' / 'optimus' / 'x.py'}"

    sanitized = sanitize_workspace_text(text, workspace_root=tmp_path)

    assert "secret-token" not in sanitized
    assert sanitized == "token=********** <workspace>/src/optimus/x.py"


def test_shared_redaction_preserves_non_secret_prose():
    assert redact_for_telemetry("token refresh logic and password reset flow") == "token refresh logic and password reset flow"


def test_sanitize_workspace_text_preserves_audit_subject_secret_masking():
    sanitized = sanitize_workspace_text("token secret-token https://user:pass@example.com/repo.git", workspace_root=None)

    assert sanitized == "token ********** https://**********@example.com/repo.git"
```

Run:

```bash
pytest tests/unit/telemetry/test_serialization.py tests/unit/telemetry/test_events.py tests/unit/guardrails/test_pre_tool_guard.py tests/unit/guardrails/test_prompt_injection.py -v
```

Expected: PASS after the serialization, subject-sanitization, redaction, guardrail audit-subject, and `TelemetryEvent` updates are complete.

- [x] **Step 5: Export ledger types and run tests**

Update `src/optimus/loops/__init__.py`:

```python
from optimus.loops.ledger import InMemoryProgressLedger, JsonlProgressLedger, ProgressLedger, ProgressLedgerEntry
from optimus.loops.models import (
    CompletionEvaluation,
    CompletionEvaluatorProtocol,
    IterationOutcome,
    IterationState,
    LoopBudgetPolicy,
    LoopStopReason,
    LoopToolExecutorProtocol,
)

__all__ = [
    "CompletionEvaluation",
    "CompletionEvaluatorProtocol",
    "InMemoryProgressLedger",
    "IterationOutcome",
    "IterationState",
    "JsonlProgressLedger",
    "LoopBudgetPolicy",
    "LoopStopReason",
    "LoopToolExecutorProtocol",
    "ProgressLedger",
    "ProgressLedgerEntry",
]
```

Run:

```bash
pytest tests/unit/loops/test_models.py tests/unit/loops/test_ledger.py tests/unit/telemetry/test_serialization.py tests/unit/telemetry/test_events.py tests/unit/guardrails/test_pre_tool_guard.py tests/unit/guardrails/test_prompt_injection.py -v
```

Expected: PASS.

- [x] **Step 6: Local checkpoint**

Run:

```bash
git diff --check
git status --short
```

Expected: only loop files/tests are new, plus any pre-existing unrelated workspace noise remains untouched.

Commit only if explicitly approved:

```bash
git add src/optimus/loops src/optimus/telemetry/serialization.py src/optimus/telemetry/subjects.py src/optimus/telemetry/redaction.py src/optimus/telemetry/events.py src/optimus/guardrails/pre_tool.py tests/unit/loops/test_models.py tests/unit/loops/test_ledger.py tests/unit/telemetry/test_serialization.py tests/unit/telemetry/test_events.py tests/unit/guardrails/test_pre_tool_guard.py tests/unit/guardrails/test_prompt_injection.py
git commit -m "Add bounded loop state and progress ledger."
```

---

## Task 2: Goal Loop Controller and Stop Reasons

**Traceability:** Guardrails Strategy 7.1-7.2, LLD 12C, Test Strategy 14.8

**Ordering note:** This task intentionally depends only on `CompletionEvaluatorProtocol` and `LoopToolExecutorProtocol` from `src/optimus/loops/models.py`. It must not import `optimus.loops.completion` or `optimus.loops.tools`; Tasks 3 and 4 add the concrete Gateway evaluator and guarded tool executor later.

**Deterministic completion precedence:** `IterationOutcome.deterministic_completion=True` deliberately wins at the end of that same iteration, even if the iteration also consumes the last budget or reaches the wall-clock boundary. The runner is reporting direct completion evidence for work just performed; budget and wall-clock stops are checked before the next iteration would begin.

**Files:**
- Create: `src/optimus/loops/controller.py`
- Modify: `src/optimus/loops/__init__.py`
- Create: `tests/unit/loops/test_controller.py`

- [x] **Step 1: Write failing controller tests**

Create `tests/unit/loops/test_controller.py`:

```python
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from optimus.loops.controller import GoalLoopController
from optimus.loops.ledger import InMemoryProgressLedger
from optimus.loops.models import (
    CompletionEvaluation,
    IterationOutcome,
    IterationState,
    LoopBudgetPolicy,
    LoopStopReason,
    LoopToolExecutorProtocol,
)


class StaticRunner:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def run_iteration(self, state: IterationState, tools: LoopToolExecutorProtocol) -> IterationOutcome:
        self.calls += 1
        return self.outcomes.pop(0)


class StaticEvaluator:
    def __init__(self, evaluations):
        self.evaluations = list(evaluations)

    def evaluate(self, state: IterationState, ledger: InMemoryProgressLedger) -> CompletionEvaluation:
        return self.evaluations.pop(0)


def state(started_at: datetime | None = None) -> IterationState:
    return IterationState(
        run_id="run-1",
        session_id="session-1",
        goal="Migrate auth call sites",
        completion_condition="tests/unit/auth pass",
        started_at=started_at or datetime(2026, 7, 6, tzinfo=UTC),
    )


def policy() -> LoopBudgetPolicy:
    return LoopBudgetPolicy(max_iterations=3, max_budget_credits=Decimal("1.0"), max_wall_clock_minutes=10)


class FakeLoopTools:
    pass


def loop_tools(tmp_path) -> LoopToolExecutorProtocol:
    _ = tmp_path
    return FakeLoopTools()


def test_loop_stops_on_completion(tmp_path):
    ledger = InMemoryProgressLedger()
    runner = StaticRunner([IterationOutcome(summary="updated", cost_credits=Decimal("0.1"))])
    evaluator = StaticEvaluator([CompletionEvaluation(completed=True, reason="tests pass", cost_credits=Decimal("0.01"))])
    controller = GoalLoopController(policy=policy(), runner=runner, tools=loop_tools(tmp_path), evaluator=evaluator, ledger=ledger, now=lambda: datetime(2026, 7, 6, tzinfo=UTC))

    result = controller.run(state())

    assert result.stop_reason is LoopStopReason.COMPLETED
    assert result.state.iteration == 1
    assert result.state.credits_spent == Decimal("0.11")
    assert ledger.entries(run_id="run-1")[-1].stop_reason is LoopStopReason.COMPLETED


def test_loop_stops_on_max_iterations(tmp_path):
    ledger = InMemoryProgressLedger()
    runner = StaticRunner([IterationOutcome(summary="not done"), IterationOutcome(summary="not done"), IterationOutcome(summary="not done")])
    evaluator = StaticEvaluator([CompletionEvaluation(completed=False, reason="not done")] * 3)
    controller = GoalLoopController(policy=policy(), runner=runner, tools=loop_tools(tmp_path), evaluator=evaluator, ledger=ledger, now=lambda: datetime(2026, 7, 6, tzinfo=UTC))

    result = controller.run(state())

    assert result.stop_reason is LoopStopReason.MAX_ITERATIONS
    assert runner.calls == 3


def test_loop_stops_on_budget_exhaustion(tmp_path):
    ledger = InMemoryProgressLedger()
    runner = StaticRunner([IterationOutcome(summary="expensive", cost_credits=Decimal("1.25"))])
    evaluator = StaticEvaluator([])
    controller = GoalLoopController(policy=policy(), runner=runner, tools=loop_tools(tmp_path), evaluator=evaluator, ledger=ledger, now=lambda: datetime(2026, 7, 6, tzinfo=UTC))

    result = controller.run(state())

    assert result.stop_reason is LoopStopReason.BUDGET_EXHAUSTED
    assert evaluator.evaluations == []


def test_loop_stops_on_deterministic_completion_without_evaluator(tmp_path):
    ledger = InMemoryProgressLedger()
    runner = StaticRunner([IterationOutcome(summary="tests pass", deterministic_completion=True, evidence={"pytest": "passed"})])
    evaluator = StaticEvaluator([])
    controller = GoalLoopController(policy=policy(), runner=runner, tools=loop_tools(tmp_path), evaluator=evaluator, ledger=ledger, now=lambda: datetime(2026, 7, 6, tzinfo=UTC))

    result = controller.run(state())

    assert result.stop_reason is LoopStopReason.COMPLETED
    assert evaluator.evaluations == []
    assert ledger.entries(run_id="run-1")[-1].evidence == {"pytest": "passed"}


def test_loop_stops_on_wall_clock_before_next_iteration(tmp_path):
    start = datetime(2026, 7, 6, tzinfo=UTC)
    ledger = InMemoryProgressLedger()
    runner = StaticRunner([IterationOutcome(summary="should not run")])
    evaluator = StaticEvaluator([])
    controller = GoalLoopController(
        policy=policy(),
        runner=runner,
        tools=loop_tools(tmp_path),
        evaluator=evaluator,
        ledger=ledger,
        now=lambda: start + timedelta(minutes=11),
    )

    result = controller.run(state(started_at=start))

    assert result.stop_reason is LoopStopReason.WALL_CLOCK
    assert runner.calls == 0


def test_loop_stops_on_repeated_failure(tmp_path):
    ledger = InMemoryProgressLedger()
    runner = StaticRunner(
        [
            IterationOutcome(summary="failed", failure_signature="same"),
            IterationOutcome(summary="failed", failure_signature="same"),
            IterationOutcome(summary="failed", failure_signature="same"),
        ]
    )
    evaluator = StaticEvaluator([CompletionEvaluation(completed=False, reason="not done")] * 2)
    controller = GoalLoopController(policy=policy(), runner=runner, tools=loop_tools(tmp_path), evaluator=evaluator, ledger=ledger, now=lambda: datetime(2026, 7, 6, tzinfo=UTC))

    result = controller.run(state())

    assert result.stop_reason is LoopStopReason.REPEATED_FAILURE
    assert result.state.repeated_failure_count == 3
    assert len(evaluator.evaluations) == 0


def test_loop_stops_on_human_halt(tmp_path):
    ledger = InMemoryProgressLedger()
    runner = StaticRunner([])
    evaluator = StaticEvaluator([])
    controller = GoalLoopController(policy=policy(), runner=runner, tools=loop_tools(tmp_path), evaluator=evaluator, ledger=ledger, now=lambda: datetime(2026, 7, 6, tzinfo=UTC))

    result = controller.run(state().request_halt())

    assert result.stop_reason is LoopStopReason.HUMAN_HALT
    assert runner.calls == 0


def test_stop_reason_precedence_when_multiple_limits_hold(tmp_path):
    start = datetime(2026, 7, 6, tzinfo=UTC)
    state_with_all_limits = IterationState(
        run_id="run-1",
        session_id="session-1",
        goal="Migrate auth call sites",
        completion_condition="tests/unit/auth pass",
        started_at=start,
        iteration=3,
        credits_spent=Decimal("1.25"),
        repeated_failure_count=3,
    )
    controller = GoalLoopController(
        policy=policy(),
        runner=StaticRunner([]),
        tools=loop_tools(tmp_path),
        evaluator=StaticEvaluator([]),
        ledger=InMemoryProgressLedger(),
        now=lambda: start + timedelta(minutes=11),
    )

    result = controller.run(state_with_all_limits)

    assert result.stop_reason is LoopStopReason.REPEATED_FAILURE


def test_mid_loop_human_halt_is_checked_between_iterations(tmp_path):
    ledger = InMemoryProgressLedger()
    runner = StaticRunner([IterationOutcome(summary="first"), IterationOutcome(summary="should not run")])
    evaluator = StaticEvaluator([CompletionEvaluation(completed=False, reason="not done")])
    checks = iter((False, False, True))
    controller = GoalLoopController(
        policy=policy(),
        runner=runner,
        tools=loop_tools(tmp_path),
        evaluator=evaluator,
        ledger=ledger,
        halt_requested=lambda: next(checks),
        now=lambda: datetime(2026, 7, 6, tzinfo=UTC),
    )

    result = controller.run(state())

    assert result.stop_reason is LoopStopReason.HUMAN_HALT
    assert runner.calls == 1
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/loops/test_controller.py -v
```

Expected: FAIL because `optimus.loops.controller` does not exist.

- [x] **Step 3: Add controller**

Create `src/optimus/loops/controller.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from optimus.loops.ledger import ProgressLedger, ProgressLedgerEntry
from optimus.loops.models import (
    CompletionEvaluatorProtocol,
    IterationOutcome,
    IterationState,
    LoopBudgetPolicy,
    LoopStopReason,
    LoopToolExecutorProtocol,
)


class IterationRunner(Protocol):
    def run_iteration(self, state: IterationState, tools: LoopToolExecutorProtocol) -> IterationOutcome:
        raise NotImplementedError


class GoalLoopResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    state: IterationState
    stop_reason: LoopStopReason
    summary: str


class GoalLoopController:
    def __init__(
        self,
        *,
        policy: LoopBudgetPolicy,
        runner: IterationRunner,
        tools: LoopToolExecutorProtocol,
        evaluator: CompletionEvaluatorProtocol,
        ledger: ProgressLedger,
        halt_requested: Callable[[], bool] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._policy = policy
        self._runner = runner
        self._tools = tools
        self._evaluator = evaluator
        self._ledger = ledger
        self._halt_requested = halt_requested or (lambda: False)
        self._now = now or (lambda: datetime.now(tz=UTC))

    def run(self, initial_state: IterationState) -> GoalLoopResult:
        state = initial_state
        while True:
            pre_stop = self._stop_reason(state)
            if pre_stop is not None:
                self._record(state=state, summary=f"stopped before iteration: {pre_stop.value}", stop_reason=pre_stop)
                return GoalLoopResult(state=state, stop_reason=pre_stop, summary=pre_stop.value)

            outcome = self._runner.run_iteration(state.with_runtime_limits(policy=self._policy), self._tools)
            state = state.record_outcome(outcome)
            self._record(
                state=state,
                summary=outcome.summary,
                stop_reason=None,
                failure_signature=outcome.failure_signature,
                cost_credits=outcome.cost_credits,
                evidence=outcome.evidence,
            )

            if outcome.deterministic_completion:
                self._record(
                    state=state,
                    summary=outcome.summary,
                    stop_reason=LoopStopReason.COMPLETED,
                    evidence=outcome.evidence,
                )
                return GoalLoopResult(state=state, stop_reason=LoopStopReason.COMPLETED, summary=outcome.summary)

            post_stop = self._stop_reason(state)
            if post_stop is not None:
                self._record(state=state, summary=f"stopped after iteration: {post_stop.value}", stop_reason=post_stop)
                return GoalLoopResult(state=state, stop_reason=post_stop, summary=post_stop.value)

            evaluation = self._evaluator.evaluate(state, self._ledger)
            state = state.record_completion_evaluation(evaluation)
            self._record(
                state=state,
                summary=f"completion evaluation: {evaluation.reason}",
                stop_reason=None,
                cost_credits=evaluation.cost_credits,
            )
            if evaluation.completed:
                self._record(state=state, summary=evaluation.reason, stop_reason=LoopStopReason.COMPLETED)
                return GoalLoopResult(state=state, stop_reason=LoopStopReason.COMPLETED, summary=evaluation.reason)

    def _stop_reason(self, state: IterationState) -> LoopStopReason | None:
        if state.human_halt_requested or self._halt_requested():
            return LoopStopReason.HUMAN_HALT
        if state.repeated_failure_count >= self._policy.repeated_failure_limit:
            return LoopStopReason.REPEATED_FAILURE
        if state.credits_spent >= self._policy.max_budget_credits:
            return LoopStopReason.BUDGET_EXHAUSTED
        if state.elapsed_minutes(now=self._now()) >= self._policy.max_wall_clock_minutes:
            return LoopStopReason.WALL_CLOCK
        if state.iteration >= self._policy.max_iterations:
            return LoopStopReason.MAX_ITERATIONS
        return None

    def _record(
        self,
        *,
        state: IterationState,
        summary: str,
        stop_reason: LoopStopReason | None,
        failure_signature: str | None = None,
        cost_credits: Decimal = Decimal("0"),
        evidence: dict[str, str] | None = None,
    ) -> None:
        self._ledger.append(
            ProgressLedgerEntry(
                run_id=state.run_id,
                session_id=state.session_id,
                iteration=state.iteration,
                goal=state.goal,
                summary=summary,
                cost_credits=cost_credits,
                stop_reason=stop_reason,
                failure_signature=failure_signature,
                evidence=evidence or {},
                occurred_at=self._now(),
            )
        )
```

- [x] **Step 4: Export controller and run tests**

Update `src/optimus/loops/__init__.py`:

```python
from optimus.loops.controller import GoalLoopController, GoalLoopResult, IterationRunner
from optimus.loops.ledger import InMemoryProgressLedger, JsonlProgressLedger, ProgressLedger, ProgressLedgerEntry
from optimus.loops.models import (
    CompletionEvaluation,
    CompletionEvaluatorProtocol,
    IterationOutcome,
    IterationState,
    LoopBudgetPolicy,
    LoopStopReason,
    LoopToolExecutorProtocol,
)

__all__ = [
    "CompletionEvaluation",
    "CompletionEvaluatorProtocol",
    "GoalLoopController",
    "GoalLoopResult",
    "InMemoryProgressLedger",
    "IterationOutcome",
    "IterationRunner",
    "IterationState",
    "JsonlProgressLedger",
    "LoopBudgetPolicy",
    "LoopStopReason",
    "LoopToolExecutorProtocol",
    "ProgressLedger",
    "ProgressLedgerEntry",
]
```

Run:

```bash
pytest tests/unit/loops/test_controller.py tests/unit/loops/test_models.py tests/unit/loops/test_ledger.py -v
```

Expected: PASS.

- [x] **Step 5: Local checkpoint**

Run:

```bash
git diff --check
```

Commit only if explicitly approved:

```bash
git add src/optimus/loops tests/unit/loops
git commit -m "Add bounded goal loop controller."
```

---

## Task 3: Gateway-Routed Completion Evaluator

**Traceability:** Guardrails Strategy 7 cost note, LLD 12C, one-key model

**Files:**
- Create: `src/optimus/loops/completion.py`
- Modify: `src/optimus/loops/__init__.py`
- Create: `tests/unit/loops/test_completion.py`

- [x] **Step 1: Write failing completion evaluator tests**

Create `tests/unit/loops/test_completion.py`:

```python
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import GatewayClient
from optimus.loops.completion import DeterministicCompletionEvaluator, GatewayCompletionEvaluator
from optimus.loops.ledger import InMemoryProgressLedger
from optimus.loops.models import CompletionEvaluation, IterationState


class FakeTransport:
    def __init__(self, body):
        self.body = body
        self.requests = []

    def post_json(self, request):
        self.requests.append(request)
        return self.body


def state() -> IterationState:
    return IterationState(
        run_id="run-1",
        session_id="session-1",
        goal="Migrate auth call sites",
        completion_condition="tests/unit/auth pass",
        started_at=datetime(2026, 7, 6, tzinfo=UTC),
    )


def settings() -> OptimusGatewaySettings:
    return OptimusGatewaySettings(
        gateway_url="https://gateway.optimus.ai",
        optimus_api_key="optimus-key",
        production_mode=True,
    )


def test_deterministic_completion_evaluator_is_zero_cost():
    evaluator = DeterministicCompletionEvaluator(completed=True, reason="predicate passed")

    result = evaluator.evaluate(state(), InMemoryProgressLedger())

    assert result == CompletionEvaluation(completed=True, reason="predicate passed")


def test_gateway_completion_evaluator_routes_through_gateway_and_returns_usage():
    transport = FakeTransport(
        {
            "id": "resp-1",
            "output_text": '{"completed": true, "reason": "tests pass", "confidence": "0.98"}',
            "gateway_usage": {
                "gateway_request_id": "gw-1",
                "provider": "openai",
                "billing_units": 7,
                "cost_usd": "0.002",
                "optimus_credits_debited": "0.03",
                "service": "responses",
                "native_unit": "tokens",
                "price_snapshot_id": "prices-1",
            },
        }
    )
    evaluator = GatewayCompletionEvaluator(
        client=GatewayClient(settings=settings(), transport=transport),
        model="cheap-evaluator",
    )

    result = evaluator.evaluate(state(), InMemoryProgressLedger())

    assert result.completed is True
    assert result.reason == "tests pass"
    assert result.cost_credits == Decimal("0.03")
    assert result.gateway_request_id == "gw-1"
    assert transport.requests[0].headers["Authorization"] == "Bearer optimus-key"
    assert transport.requests[0].payload["metadata"]["purpose"] == "goal_loop_completion_evaluation"


def test_gateway_completion_evaluator_rejects_string_boolean():
    transport = FakeTransport(
        {
            "id": "resp-1",
            "output_text": '{"completed": "false", "reason": "string boolean", "confidence": "0.98"}',
            "gateway_usage": {
                "gateway_request_id": "gw-1",
                "provider": "openai",
                "billing_units": 7,
                "cost_usd": "0.002",
            },
        }
    )
    evaluator = GatewayCompletionEvaluator(
        client=GatewayClient(settings=settings(), transport=transport),
        model="cheap-evaluator",
    )

    with pytest.raises(ValueError, match="completed must be a JSON boolean"):
        evaluator.evaluate(state(), InMemoryProgressLedger())


def test_gateway_completion_evaluator_rejects_invalid_confidence():
    transport = FakeTransport(
        {
            "id": "resp-1",
            "output_text": '{"completed": false, "reason": "not done", "confidence": "high"}',
            "gateway_usage": {
                "gateway_request_id": "gw-1",
                "provider": "openai",
                "billing_units": 7,
                "cost_usd": "0.002",
            },
        }
    )
    evaluator = GatewayCompletionEvaluator(
        client=GatewayClient(settings=settings(), transport=transport),
        model="cheap-evaluator",
    )

    with pytest.raises(ValueError, match="confidence must be a decimal"):
        evaluator.evaluate(state(), InMemoryProgressLedger())


def test_gateway_completion_evaluator_cannot_override_failed_deterministic_evidence():
    transport = FakeTransport(
        {
            "id": "resp-1",
            "output_text": '{"completed": true, "reason": "model says done", "confidence": "0.99"}',
            "gateway_usage": {
                "gateway_request_id": "gw-1",
                "provider": "openai",
                "billing_units": 7,
                "cost_usd": "0.002",
            },
        }
    )
    evaluator = GatewayCompletionEvaluator(
        client=GatewayClient(settings=settings(), transport=transport),
        model="cheap-evaluator",
        deterministic_predicate=lambda state, ledger: CompletionEvaluation(completed=False, reason="pytest failed"),
    )

    result = evaluator.evaluate(state(), InMemoryProgressLedger())

    assert result.completed is False
    assert result.reason == "pytest failed"
    assert transport.requests == []


def test_gateway_completion_evaluator_fails_closed_on_non_json_output():
    transport = FakeTransport(
        {
            "id": "resp-1",
            "output_text": "yes, done",
            "gateway_usage": {
                "gateway_request_id": "gw-1",
                "provider": "openai",
                "billing_units": 7,
                "cost_usd": "0.002",
            },
        }
    )
    evaluator = GatewayCompletionEvaluator(
        client=GatewayClient(settings=settings(), transport=transport),
        model="cheap-evaluator",
    )

    with pytest.raises(ValueError, match="completion evaluator returned invalid JSON"):
        evaluator.evaluate(state(), InMemoryProgressLedger())
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/loops/test_completion.py -v
```

Expected: FAIL because `optimus.loops.completion` does not exist.

- [x] **Step 3: Add completion evaluators**

Create `src/optimus/loops/completion.py`:

```python
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Protocol

from optimus.gateway.client import GatewayClient
from optimus.loops.ledger import ProgressLedger
from optimus.loops.models import CompletionEvaluation, CompletionEvaluatorProtocol, IterationState


class DeterministicCompletionPredicate(Protocol):
    def __call__(self, state: IterationState, ledger: ProgressLedger) -> CompletionEvaluation:
        raise NotImplementedError


class DeterministicCompletionEvaluator:
    def __init__(self, *, completed: bool, reason: str) -> None:
        self._completed = completed
        self._reason = reason

    def evaluate(self, state: IterationState, ledger: ProgressLedger) -> CompletionEvaluation:
        return CompletionEvaluation(completed=self._completed, reason=self._reason)


class GatewayCompletionEvaluator:
    def __init__(
        self,
        *,
        client: GatewayClient,
        model: str,
        deterministic_predicate: DeterministicCompletionPredicate | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._deterministic_predicate = deterministic_predicate

    def evaluate(self, state: IterationState, ledger: ProgressLedger) -> CompletionEvaluation:
        if self._deterministic_predicate is not None:
            deterministic = self._deterministic_predicate(state, ledger)
            if not deterministic.completed:
                return deterministic
        response = self._client.create_response(
            model=self._model,
            input_text=_completion_prompt(state, ledger),
            metadata={
                "purpose": "goal_loop_completion_evaluation",
                "run_id": state.run_id,
                "session_id": state.session_id,
            },
        )
        try:
            payload = json.loads(response.output_text, parse_float=Decimal)
        except json.JSONDecodeError as exc:
            raise ValueError("completion evaluator returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("completion evaluator returned non-object JSON")
        completed = payload.get("completed")
        if not isinstance(completed, bool):
            raise ValueError("completed must be a JSON boolean")
        try:
            confidence = Decimal(str(payload.get("confidence", "1")))
        except InvalidOperation as exc:
            raise ValueError("confidence must be a decimal") from exc
        usage = response.gateway_usage
        credits = usage.optimus_credits_debited if usage.optimus_credits_debited is not None else Decimal("0")
        return CompletionEvaluation(
            completed=completed,
            reason=str(payload.get("reason") or "completion evaluator did not provide a reason"),
            confidence=confidence,
            cost_credits=credits,
            gateway_request_id=usage.gateway_request_id,
        )


def _completion_prompt(state: IterationState, ledger: ProgressLedger) -> str:
    recent = ledger.entries(run_id=state.run_id)[-5:]
    summaries = "\n".join(
        f"- iteration {entry.iteration}: summary={entry.summary}; failure_signature={entry.failure_signature}; stop_reason={entry.stop_reason}; evidence={entry.evidence}"
        for entry in recent
    )
    return (
        "Evaluate whether the bounded goal loop is complete.\n"
        "Return strict JSON with keys completed, reason, and confidence.\n"
        f"Goal: {state.goal}\n"
        f"Completion condition: {state.completion_condition}\n"
        f"Iterations: {state.iteration}\n"
        f"Recent progress:\n{summaries}\n"
    )
```

- [x] **Step 4: Export evaluator and run tests**

Update `src/optimus/loops/__init__.py` to export the concrete evaluators while keeping `CompletionEvaluatorProtocol` imported from `optimus.loops.models`:

```python
from optimus.loops.completion import DeterministicCompletionEvaluator, GatewayCompletionEvaluator
from optimus.loops.models import CompletionEvaluatorProtocol
```

Add `"CompletionEvaluatorProtocol"`, `"DeterministicCompletionEvaluator"`, and `"GatewayCompletionEvaluator"` to `__all__`.

Run:

```bash
pytest tests/unit/loops/test_completion.py tests/unit/gateway/test_client.py tests/unit/gateway/test_models.py -v
```

Expected: PASS.

- [x] **Step 5: Local checkpoint**

Run:

```bash
git diff --check
```

Commit only if explicitly approved:

```bash
git add src/optimus/loops tests/unit/loops/test_completion.py
git commit -m "Route loop completion evaluation through the gateway."
```

---

## Task 4: Guarded Loop Tool Execution

**Traceability:** Guardrails Strategy 7.2, LLD 12A/12C, Test Strategy 14.8

**Files:**
- Create: `src/optimus/loops/tools.py`
- Modify: `src/optimus/loops/__init__.py`
- Create: `tests/unit/loops/test_tools.py`
- Create: `tests/integration/loops/test_goal_loop_guardrail_flow.py`

- [x] **Step 1: Write failing guarded tool tests**

Create `tests/unit/loops/test_tools.py`:

```python
import pytest

from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard, PreToolVerdict
from optimus.loops.tools import GuardedLoopToolExecutor, LoopToolBlocked
from optimus.runtime.modes import ExecutionMode, GenerationScope


def executor(tmp_path) -> GuardedLoopToolExecutor:
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=("gateway.optimus.ai",))
    return GuardedLoopToolExecutor(guard=guard)


def test_loop_tool_executor_blocks_plan_mode_shell(tmp_path):
    tools = executor(tmp_path)

    with pytest.raises(LoopToolBlocked) as exc:
        tools.preflight(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.PLAN,
            tool_surface=ToolSurface.SHELL,
            action="pytest tests/unit -q",
            command=("pytest", "tests/unit", "-q"),
            approval_granted=True,
        )

    assert exc.value.result.verdict is PreToolVerdict.BLOCK
    assert exc.value.result.rule_id == "mode.plan_chat.no_shell"


def test_loop_tool_executor_allows_agent_mode_safe_pytest(tmp_path):
    tools = executor(tmp_path)

    result = tools.preflight(
        run_id="run-1",
        session_id="session-1",
        execution_mode=ExecutionMode.AGENT,
        tool_surface=ToolSurface.SHELL,
        action="pytest tests/unit -q",
        command=("pytest", "tests/unit", "-q"),
        approval_granted=True,
    )

    assert result.verdict is PreToolVerdict.ALLOW


def test_loop_tool_executor_preserves_multi_file_approval_hold(tmp_path):
    tools = executor(tmp_path)

    with pytest.raises(LoopToolBlocked) as exc:
        tools.preflight(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.FILE_WRITE,
            action="write",
            target_path=str(tmp_path / "src" / "optimus" / "x.py"),
            generation_scope=GenerationScope.MULTI_FILE_CHANGESET,
            approval_granted=False,
        )

    assert exc.value.result.verdict is PreToolVerdict.HOLD
    assert exc.value.result.requires_human_approval is True
```

Create `tests/integration/loops/test_goal_loop_guardrail_flow.py`:

```python
from datetime import UTC, datetime
from decimal import Decimal

from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard
from optimus.loops.controller import GoalLoopController
from optimus.loops.ledger import InMemoryProgressLedger
from optimus.loops.models import CompletionEvaluation, IterationOutcome, IterationState, LoopBudgetPolicy, LoopStopReason
from optimus.loops.tools import GuardedLoopToolExecutor, LoopToolBlocked
from optimus.runtime.modes import ExecutionMode


class UnsafeRunner:
    def run_iteration(self, state: IterationState, tools: GuardedLoopToolExecutor) -> IterationOutcome:
        try:
            tools.preflight(
                run_id=state.run_id,
                session_id=state.session_id,
                execution_mode=ExecutionMode.AGENT,
                tool_surface=ToolSurface.SHELL,
                action="rm -rf src",
                command=("rm", "-rf", "src"),
                approval_granted=True,
            )
        except LoopToolBlocked as exc:
            return IterationOutcome(summary=exc.result.reason, failure_signature=exc.result.rule_id)
        return IterationOutcome(summary="unexpected allow")


class NeverComplete:
    def evaluate(self, state, ledger):
        return CompletionEvaluation(completed=False, reason="not done")


def test_goal_loop_never_bypasses_pre_tool_guard(tmp_path):
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=())
    tools = GuardedLoopToolExecutor(guard=guard)
    ledger = InMemoryProgressLedger()
    controller = GoalLoopController(
        policy=LoopBudgetPolicy(max_iterations=5, max_budget_credits=Decimal("1"), max_wall_clock_minutes=5, repeated_failure_limit=2),
        runner=UnsafeRunner(),
        tools=tools,
        evaluator=NeverComplete(),
        ledger=ledger,
        now=lambda: datetime(2026, 7, 6, tzinfo=UTC),
    )

    result = controller.run(
        IterationState(
            run_id="run-1",
            session_id="session-1",
            goal="Try unsafe loop action",
            completion_condition="must not run unsafe command",
            started_at=datetime(2026, 7, 6, tzinfo=UTC),
        )
    )

    assert result.stop_reason is LoopStopReason.REPEATED_FAILURE
    assert guard.audit_events()
    assert guard.audit_events()[0].rule_id == "shell.destructive.rm_rf"
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/loops/test_tools.py tests/integration/loops/test_goal_loop_guardrail_flow.py -v
```

Expected: FAIL because `optimus.loops.tools` does not exist.

- [x] **Step 3: Add guarded loop tool executor**

Create `src/optimus/loops/tools.py`:

```python
from __future__ import annotations

from collections.abc import Mapping

from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard, PreToolRequest, PreToolResult
from optimus.runtime.modes import ExecutionMode, GenerationScope


class LoopToolBlocked(RuntimeError):
    def __init__(self, result: PreToolResult) -> None:
        self.result = result
        super().__init__(result.reason)


class GuardedLoopToolExecutor:
    def __init__(self, *, guard: PreToolGuard) -> None:
        self._guard = guard

    def preflight(
        self,
        *,
        run_id: str,
        session_id: str | None,
        execution_mode: ExecutionMode,
        tool_surface: ToolSurface,
        action: str,
        command: tuple[str, ...] = (),
        target_path: str | None = None,
        generation_scope: GenerationScope = GenerationScope.INLINE_SNIPPET,
        approval_granted: bool = False,
        environment: Mapping[str, str] | None = None,
    ) -> PreToolResult:
        result = self._guard.check(
            PreToolRequest(
                run_id=run_id,
                session_id=session_id,
                execution_mode=execution_mode,
                tool_surface=tool_surface,
                action=action,
                command=command,
                target_path=target_path,
                generation_scope=generation_scope,
                approval_granted=approval_granted,
                environment=environment or {},
            )
        )
        if not result.allowed:
            raise LoopToolBlocked(result)
        return result
```

- [x] **Step 4: Export executor and run tests**

Update `src/optimus/loops/__init__.py`:

```python
from optimus.loops.tools import GuardedLoopToolExecutor, LoopToolBlocked
```

Add `"GuardedLoopToolExecutor"` and `"LoopToolBlocked"` to `__all__`.

Run:

```bash
pytest tests/unit/loops/test_tools.py tests/integration/loops/test_goal_loop_guardrail_flow.py tests/unit/guardrails/test_pre_tool_guard.py -v
```

Expected: PASS.

- [x] **Step 5: Local checkpoint**

Run:

```bash
git diff --check
```

Commit only if explicitly approved:

```bash
git add src/optimus/loops tests/unit/loops/test_tools.py tests/integration/loops/test_goal_loop_guardrail_flow.py
git commit -m "Enforce pre-tool guard inside goal loops."
```

---

## Task 5: Skill Manifest Registry

**Traceability:** Guardrails Strategy 8.1-8.2, LLD 12D, Test Strategy 14.9

**Files:**
- Create: `src/optimus/skills/__init__.py`
- Create: `src/optimus/skills/models.py`
- Create: `src/optimus/skills/registry.py`
- Create: `tests/unit/skills/test_registry.py`

- [x] **Step 1: Write failing registry tests**

Create `tests/unit/skills/test_registry.py`:

```python
from pathlib import Path

import pytest

from optimus.runtime.modes import ExecutionMode
from optimus.skills.models import SkillTrustLevel
from optimus.skills.registry import SkillManifestError, SkillRegistry, parse_skill_markdown


SKILL_TEXT = """---
name: pytest-debugging
description: Debug failing pytest tests with a red-green loop.
keywords:
  - pytest
  - debug
  - failing
globs:
  - tests/**/*.py
allowed_tools:
  - shell
  - file_read
owner: maintainer
version: 1.0.0
trust_level: trusted
---

# Pytest Debugging

Run the narrow failing test first, inspect the failure, then patch the smallest code path.
"""


def test_parse_skill_markdown_manifest():
    manifest = parse_skill_markdown(SKILL_TEXT, source_path=Path("skills/pytest/SKILL.md"))

    assert manifest.name == "pytest-debugging"
    assert manifest.description == "Debug failing pytest tests with a red-green loop."
    assert manifest.globs == ("tests/**/*.py",)
    assert manifest.allowed_tools == ("shell", "file_read")
    assert manifest.owner == "maintainer"
    assert manifest.version == "1.0.0"
    assert manifest.trust_level is SkillTrustLevel.TRUSTED
    assert len(manifest.manifest_hash) == 64
    assert manifest.manifest_hash == manifest.content_hash
    assert "Run the narrow failing test first" not in manifest.model_dump_json()


def test_skill_registry_matches_by_description_and_globs(tmp_path):
    path = tmp_path / "skills" / "pytest" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(SKILL_TEXT, encoding="utf-8")
    registry = SkillRegistry.from_paths((path,))

    matches = registry.match(
        run_id="run-1",
        session_id="session-1",
        task_text="Please debug the failing pytest test",
        changed_paths=("tests/unit/test_example.py",),
        execution_mode=ExecutionMode.AGENT,
    )

    assert tuple(match.manifest.name for match in matches) == ("pytest-debugging",)
    assert matches[0].matched_reasons == ("description", "glob:tests/**/*.py")


def test_skill_registry_does_not_match_unrelated_task(tmp_path):
    path = tmp_path / "skills" / "pytest" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(SKILL_TEXT, encoding="utf-8")
    registry = SkillRegistry.from_paths((path,))

    matches = registry.match(
        run_id="run-1",
        session_id="session-1",
        task_text="Write architecture notes",
        changed_paths=("docs/design.md",),
        execution_mode=ExecutionMode.AGENT,
    )

    assert matches == ()


def test_skill_registry_matches_double_star_zero_directory_path(tmp_path):
    path = tmp_path / "skills" / "pytest" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(SKILL_TEXT, encoding="utf-8")
    registry = SkillRegistry.from_paths((path,))

    matches = registry.match(
        run_id="run-1",
        session_id="session-1",
        task_text="Please debug the failing pytest test",
        changed_paths=("tests/test_example.py",),
        execution_mode=ExecutionMode.AGENT,
    )

    assert tuple(match.manifest.name for match in matches) == ("pytest-debugging",)


def test_skill_registry_does_not_read_unmatched_skill_body(tmp_path):
    path = tmp_path / "skills" / "pytest" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(SKILL_TEXT, encoding="utf-8")
    registry = SkillRegistry.from_paths((path,))

    matches = registry.match(
        run_id="run-1",
        session_id="session-1",
        task_text="Write architecture notes",
        changed_paths=("docs/design.md",),
        execution_mode=ExecutionMode.AGENT,
    )

    assert matches == ()
    # `from_paths()` reads the full file to hash it; this assertion verifies the body was never surfaced to runtime context.
    assert registry.loaded_body_paths() == ()


def test_skill_registry_loads_body_only_after_match(tmp_path):
    path = tmp_path / "skills" / "pytest" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(SKILL_TEXT, encoding="utf-8")
    registry = SkillRegistry.from_paths((path,))
    match = registry.match(
        run_id="run-1",
        session_id="session-1",
        task_text="Please debug the failing pytest test",
        changed_paths=("tests/unit/test_example.py",),
        execution_mode=ExecutionMode.AGENT,
    )[0]

    body = registry.load_body(match.manifest)

    assert "Run the narrow failing test first" in body
    assert registry.loaded_body_paths() == (path.resolve().as_posix(),)


def test_skill_manifest_rejects_unknown_allowed_tool():
    text = SKILL_TEXT.replace("  - shell", "  - Shell")

    with pytest.raises(SkillManifestError, match="unknown allowed_tools"):
        parse_skill_markdown(text, source_path=Path("skills/pytest/SKILL.md"))
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/skills/test_registry.py -v
```

Expected: FAIL because `optimus.skills` does not exist.

- [x] **Step 3: Add skill models**

Create `src/optimus/skills/models.py`:

```python
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SkillTrustLevel(StrEnum):
    TRUSTED = "trusted"
    DRAFT = "draft"


class SkillManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    keywords: tuple[str, ...] = ()
    globs: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    owner: str = Field(min_length=1)
    version: str = Field(min_length=1)
    trust_level: SkillTrustLevel = SkillTrustLevel.DRAFT
    source_path: str = Field(min_length=1)
    manifest_hash: str = Field(min_length=64, max_length=64)
    content_hash: str = Field(min_length=64, max_length=64)


class SkillMatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    manifest: SkillManifest
    matched_reasons: tuple[str, ...]
```

- [x] **Step 4: Add stdlib frontmatter parser and registry**

Create `src/optimus/skills/registry.py`:

```python
from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath

from optimus.guardrails.permissions import ToolSurface
from optimus.runtime.modes import ExecutionMode
from optimus.skills.models import SkillManifest, SkillMatch, SkillTrustLevel


class SkillManifestError(ValueError):
    pass


class SkillRegistry:
    def __init__(self, manifests: tuple[SkillManifest, ...]) -> None:
        self._manifests = manifests
        self._loaded_body_paths: list[str] = []

    @classmethod
    def from_paths(cls, paths: tuple[Path, ...]) -> "SkillRegistry":
        return cls(tuple(parse_skill_markdown(path.read_text(encoding="utf-8"), source_path=path) for path in paths))

    def match(
        self,
        *,
        run_id: str,
        session_id: str | None,
        task_text: str,
        changed_paths: tuple[str, ...],
        execution_mode: ExecutionMode,
    ) -> tuple[SkillMatch, ...]:
        # Task 7 attaches telemetry to these identifiers; keep the public API stable from the start.
        _ = (run_id, session_id)
        matches: list[SkillMatch] = []
        for manifest in self._manifests:
            if execution_mode is ExecutionMode.AGENT and manifest.trust_level is SkillTrustLevel.DRAFT:
                continue
            reasons = _match_reasons(manifest, task_text=task_text, changed_paths=changed_paths)
            if reasons:
                matches.append(SkillMatch(manifest=manifest, matched_reasons=reasons))
        return tuple(matches)

    def load_body(self, manifest: SkillManifest) -> str:
        path = Path(manifest.source_path).resolve()
        text = path.read_text(encoding="utf-8")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != manifest.content_hash:
            raise SkillManifestError("skill content hash changed")
        self._loaded_body_paths.append(path.as_posix())
        return _body_without_frontmatter(text)

    def loaded_body_paths(self) -> tuple[str, ...]:
        return tuple(self._loaded_body_paths)


def parse_skill_markdown(text: str, *, source_path: Path) -> SkillManifest:
    metadata = _frontmatter(text)
    required = ("name", "description", "owner", "version")
    missing = [key for key in required if not metadata.get(key)]
    if missing:
        raise SkillManifestError(f"skill manifest missing required fields: {missing}")
    allowed_tools = tuple(metadata.get("allowed_tools", ()))
    unknown_tools = sorted(set(allowed_tools) - {surface.value for surface in ToolSurface})
    if unknown_tools:
        raise SkillManifestError(f"unknown allowed_tools: {unknown_tools}")
    try:
        trust_level = SkillTrustLevel(str(metadata.get("trust_level", "draft")))
    except ValueError as exc:
        raise SkillManifestError(f"unknown trust_level: {metadata.get('trust_level')}") from exc
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return SkillManifest(
        name=str(metadata["name"]),
        description=str(metadata["description"]),
        keywords=tuple(metadata.get("keywords", ())),
        globs=tuple(metadata.get("globs", ())),
        allowed_tools=allowed_tools,
        owner=str(metadata["owner"]),
        version=str(metadata["version"]),
        trust_level=trust_level,
        source_path=source_path.as_posix(),
        manifest_hash=content_hash,
        content_hash=content_hash,
    )


def _frontmatter(text: str) -> dict[str, object]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillManifestError("skill markdown must start with YAML frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise SkillManifestError("skill markdown frontmatter must end with ---") from exc
    data: dict[str, object] = {}
    current_list_key: str | None = None
    for raw in lines[1:end]:
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("  - "):
            if current_list_key is None:
                raise SkillManifestError("list item without key")
            data.setdefault(current_list_key, [])
            if not isinstance(data[current_list_key], list):
                raise SkillManifestError(f"frontmatter key is not a list: {current_list_key}")
            data[current_list_key].append(line[4:].strip())
            continue
        current_list_key = None
        if ":" not in line:
            raise SkillManifestError(f"invalid frontmatter line: {line}")
        key, value = line.split(":", 1)
        key = key.strip()
        if key in data:
            raise SkillManifestError(f"duplicate frontmatter key: {key}")
        value = value.strip()
        if value == "":
            data[key] = []
            current_list_key = key
        else:
            data[key] = value
    return data


def _match_reasons(manifest: SkillManifest, *, task_text: str, changed_paths: tuple[str, ...]) -> tuple[str, ...]:
    reasons: list[str] = []
    task_lower = task_text.lower()
    description_terms = [term for term in (*manifest.keywords, *manifest.description.lower().replace("-", " ").split()) if len(term) >= 5]
    if sum(1 for term in set(description_terms) if term in task_lower) >= 2:
        reasons.append("description")
    for pattern in manifest.globs:
        if any(PurePosixPath(path.replace("\\", "/")).full_match(pattern) for path in changed_paths):
            reasons.append(f"glob:{pattern}")
    return tuple(reasons)


def _body_without_frontmatter(text: str) -> str:
    lines = text.splitlines()
    end = lines.index("---", 1)
    return "\n".join(lines[end + 1 :]).lstrip()
```

Create `src/optimus/skills/__init__.py`:

```python
from optimus.skills.models import SkillManifest, SkillMatch, SkillTrustLevel
from optimus.skills.registry import SkillManifestError, SkillRegistry, parse_skill_markdown

__all__ = [
    "SkillManifest",
    "SkillManifestError",
    "SkillMatch",
    "SkillRegistry",
    "SkillTrustLevel",
    "parse_skill_markdown",
]
```

- [x] **Step 5: Run registry tests**

Run:

```bash
pytest tests/unit/skills/test_registry.py -v
```

Expected: PASS.

- [x] **Step 6: Local checkpoint**

Run:

```bash
git diff --check
```

Commit only if explicitly approved:

```bash
git add src/optimus/skills tests/unit/skills/test_registry.py
git commit -m "Add curated workflow skill registry."
```

---

## Task 6: Skill Trust and Invocation Policy

**Traceability:** Guardrails Strategy 8.2, LLD 12D, Test Strategy 14.9

**Files:**
- Create: `src/optimus/skills/invocation.py`
- Modify: `src/optimus/skills/__init__.py`
- Create: `tests/unit/skills/test_invocation.py`
- Create: `tests/integration/skills/test_skill_guardrail_flow.py`

- [ ] **Step 1: Write failing invocation tests**

Create `tests/unit/skills/test_invocation.py`:

```python
from optimus.guardrails.permissions import ToolSurface
from optimus.runtime.modes import ExecutionMode
from optimus.skills.invocation import SkillInvocationPolicy, SkillInvocationVerdict, SkillTrustPolicy
from optimus.skills.models import SkillManifest, SkillTrustLevel


def manifest(*, trust_level: SkillTrustLevel, allowed_tools=("shell",)) -> SkillManifest:
    return SkillManifest(
        name="pytest-debugging",
        description="Debug pytest failures",
        globs=("tests/**/*.py",),
        allowed_tools=allowed_tools,
        owner="maintainer",
        version="1.0.0",
        trust_level=trust_level,
        source_path="skills/pytest/SKILL.md",
        manifest_hash="a" * 64,
        content_hash="a" * 64,
    )


def test_draft_skill_is_blocked_in_agent_mode():
    decision = SkillTrustPolicy().check(manifest=manifest(trust_level=SkillTrustLevel.DRAFT), execution_mode=ExecutionMode.AGENT)

    assert decision.verdict is SkillInvocationVerdict.BLOCK
    assert decision.rule_id == "skill.draft_blocked_agent_mode"


def test_draft_skill_can_be_suggested_in_plan_mode():
    decision = SkillTrustPolicy().check(manifest=manifest(trust_level=SkillTrustLevel.DRAFT), execution_mode=ExecutionMode.PLAN)

    assert decision.verdict is SkillInvocationVerdict.HOLD
    assert decision.requires_human_approval is True


def test_skill_invocation_policy_blocks_tool_not_declared_by_skill():
    decision = SkillInvocationPolicy().authorize_tool(
        manifest=manifest(trust_level=SkillTrustLevel.TRUSTED, allowed_tools=("file_read",)),
        requested_tool=ToolSurface.SHELL,
        execution_mode=ExecutionMode.AGENT,
    )

    assert decision.verdict is SkillInvocationVerdict.BLOCK
    assert decision.rule_id == "skill.tool_not_declared"


def test_skill_invocation_policy_allows_declared_tool_to_continue_to_pre_tool_guard():
    decision = SkillInvocationPolicy().authorize_tool(
        manifest=manifest(trust_level=SkillTrustLevel.TRUSTED, allowed_tools=("shell",)),
        requested_tool=ToolSurface.SHELL,
        execution_mode=ExecutionMode.AGENT,
    )

    assert decision.verdict is SkillInvocationVerdict.ALLOW
    assert decision.rule_id == "skill.declared_tool_allowed"
```

Create `tests/integration/skills/test_skill_guardrail_flow.py`:

```python
import pytest

from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard
from optimus.runtime.modes import ExecutionMode
from optimus.skills.invocation import SkillInvocationPolicy, SkillInvocationVerdict
from optimus.skills.models import SkillManifest, SkillTrustLevel


def trusted_shell_skill() -> SkillManifest:
    return SkillManifest(
        name="unsafe-shell-example",
        description="Example shell skill",
        globs=(),
        allowed_tools=("shell",),
        owner="maintainer",
        version="1.0.0",
        trust_level=SkillTrustLevel.TRUSTED,
        source_path="skills/shell/SKILL.md",
        manifest_hash="b" * 64,
        content_hash="b" * 64,
    )


def test_skill_cannot_override_user_deny_rules(tmp_path):
    policy = SkillInvocationPolicy()
    skill_decision = policy.authorize_tool(
        manifest=trusted_shell_skill(),
        requested_tool=ToolSurface.SHELL,
        execution_mode=ExecutionMode.AGENT,
    )
    assert skill_decision.verdict is SkillInvocationVerdict.ALLOW

    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=())
    result = policy.preflight_with_guard(
        guard=guard,
        manifest=trusted_shell_skill(),
        run_id="run-1",
        session_id=None,
        execution_mode=ExecutionMode.AGENT,
        requested_tool=ToolSurface.SHELL,
        action="rm -rf src",
        command=("rm", "-rf", "src"),
        approval_granted=True,
    )

    assert result.verdict.name == "BLOCK"
    assert result.rule_id == "shell.destructive.rm_rf"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/skills/test_invocation.py tests/integration/skills/test_skill_guardrail_flow.py -v
```

Expected: FAIL because `optimus.skills.invocation` does not exist.

- [ ] **Step 3: Add skill invocation policy**

Create `src/optimus/skills/invocation.py`:

```python
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard, PreToolRequest, PreToolResult, PreToolVerdict
from optimus.runtime.modes import ExecutionMode, GenerationScope
from optimus.skills.models import SkillManifest, SkillTrustLevel


class SkillInvocationVerdict(StrEnum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    HOLD = "HOLD"


class SkillInvocationDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    verdict: SkillInvocationVerdict
    rule_id: str
    reason: str
    requires_human_approval: bool = False

    @property
    def allowed(self) -> bool:
        return self.verdict is SkillInvocationVerdict.ALLOW


class SkillTrustPolicy:
    def check(self, *, manifest: SkillManifest, execution_mode: ExecutionMode) -> SkillInvocationDecision:
        if manifest.trust_level is SkillTrustLevel.TRUSTED:
            return SkillInvocationDecision(
                verdict=SkillInvocationVerdict.ALLOW,
                rule_id="skill.trusted",
                reason="trusted skill may be considered for invocation",
            )
        if execution_mode is ExecutionMode.AGENT:
            return SkillInvocationDecision(
                verdict=SkillInvocationVerdict.BLOCK,
                rule_id="skill.draft_blocked_agent_mode",
                reason="draft skills cannot load in Agent mode",
            )
        return SkillInvocationDecision(
            verdict=SkillInvocationVerdict.HOLD,
            rule_id="skill.draft_requires_review",
            reason="draft skill requires review before use",
            requires_human_approval=True,
        )


class SkillInvocationPolicy:
    def __init__(self, *, trust_policy: SkillTrustPolicy | None = None) -> None:
        self._trust_policy = trust_policy or SkillTrustPolicy()

    def authorize_tool(
        self,
        *,
        manifest: SkillManifest,
        requested_tool: ToolSurface,
        execution_mode: ExecutionMode,
    ) -> SkillInvocationDecision:
        trust = self._trust_policy.check(manifest=manifest, execution_mode=execution_mode)
        if not trust.allowed:
            return trust
        if requested_tool.value not in manifest.allowed_tools:
            return SkillInvocationDecision(
                verdict=SkillInvocationVerdict.BLOCK,
                rule_id="skill.tool_not_declared",
                reason="skill did not declare the requested tool surface",
            )
        return SkillInvocationDecision(
            verdict=SkillInvocationVerdict.ALLOW,
            rule_id="skill.declared_tool_allowed",
            reason="skill declared the requested tool surface; pre-tool guard must still authorize it",
        )

    def preflight_with_guard(
        self,
        *,
        guard: PreToolGuard,
        manifest: SkillManifest,
        run_id: str,
        session_id: str | None,
        execution_mode: ExecutionMode,
        requested_tool: ToolSurface,
        action: str,
        command: tuple[str, ...] = (),
        target_path: str | None = None,
        generation_scope: GenerationScope = GenerationScope.INLINE_SNIPPET,
        approval_granted: bool = False,
    ) -> PreToolResult:
        decision = self.authorize_tool(manifest=manifest, requested_tool=requested_tool, execution_mode=execution_mode)
        if not decision.allowed:
            return PreToolResult(
                verdict=PreToolVerdict.BLOCK if decision.verdict is SkillInvocationVerdict.BLOCK else PreToolVerdict.HOLD,
                rule_id=decision.rule_id,
                reason=decision.reason,
                requires_human_approval=decision.requires_human_approval,
            )
        return guard.check(
            PreToolRequest(
                run_id=run_id,
                session_id=session_id,
                execution_mode=execution_mode,
                tool_surface=requested_tool,
                action=action,
                command=command,
                target_path=target_path,
                generation_scope=generation_scope,
                approval_granted=approval_granted,
            )
        )
```

- [ ] **Step 4: Export invocation types and run tests**

Update `src/optimus/skills/__init__.py`:

```python
from optimus.skills.invocation import SkillInvocationDecision, SkillInvocationPolicy, SkillInvocationVerdict, SkillTrustPolicy
from optimus.skills.models import SkillManifest, SkillMatch, SkillTrustLevel
from optimus.skills.registry import SkillManifestError, SkillRegistry, parse_skill_markdown

__all__ = [
    "SkillInvocationDecision",
    "SkillInvocationPolicy",
    "SkillInvocationVerdict",
    "SkillManifest",
    "SkillManifestError",
    "SkillMatch",
    "SkillRegistry",
    "SkillTrustLevel",
    "SkillTrustPolicy",
    "parse_skill_markdown",
]
```

Run:

```bash
pytest tests/unit/skills/test_invocation.py tests/integration/skills/test_skill_guardrail_flow.py tests/unit/guardrails/test_permissions.py tests/unit/guardrails/test_pre_tool_guard.py -v
```

Expected: PASS.

- [ ] **Step 5: Local checkpoint**

Run:

```bash
git diff --check
```

Commit only if explicitly approved:

```bash
git add src/optimus/skills tests/unit/skills tests/integration/skills
git commit -m "Enforce skill trust and tool invocation policy."
```

---

## Task 7: Loop and Skill Telemetry

**Traceability:** Guardrails Strategy 7.2, 8.2, 9; LLD 10A/12C/12D; Plan 10 input signals

**Files:**
- Modify: `src/optimus/telemetry/events.py`
- Modify: `tests/unit/telemetry/test_events.py`
- Modify: `src/optimus/loops/controller.py`
- Modify: `src/optimus/skills/registry.py`
- Modify: `src/optimus/skills/invocation.py`
- Modify: `tests/unit/loops/test_controller.py`
- Modify: `tests/unit/skills/test_invocation.py`

- [ ] **Step 1: Write failing telemetry tests**

Append to `tests/unit/telemetry/test_events.py`:

```python
from datetime import UTC, datetime
from decimal import Decimal


def test_goal_loop_event_serializes_stop_reason_and_budget():
    event = TelemetryEvent.goal_loop(
        run_id="run-1",
        session_id="session-1",
        request_id="loop-1",
        occurred_at=datetime(2026, 7, 6, tzinfo=UTC),
        iteration=3,
        stop_reason="REPEATED_FAILURE",
        credits_spent=Decimal("0.25"),
        max_budget_credits=Decimal("1.00"),
        summary="same failure repeated",
    )

    encoded = event.to_json_dict()

    assert encoded["kind"] == "goal_loop"
    assert encoded["stop_reason"] == "REPEATED_FAILURE"
    assert encoded["credits_spent"] == "0.25"


def test_skill_invocation_event_serializes_manifest_hash_without_body():
    event = TelemetryEvent.skill_invocation(
        run_id="run-1",
        session_id=None,
        request_id="skill-1",
        occurred_at=datetime(2026, 7, 6, tzinfo=UTC),
        skill_name="pytest-debugging",
        manifest_hash="a" * 64,
        verdict="ALLOW",
        rule_id="skill.declared_tool_allowed",
        requested_tool="shell",
    )

    encoded = event.to_json_dict()

    assert encoded["kind"] == "skill_invocation"
    assert encoded["manifest_hash"] == "a" * 64
    assert "Run the narrow failing test" not in str(encoded)


def test_skill_selection_event_serializes_match_reasons():
    event = TelemetryEvent.skill_selection(
        run_id="run-1",
        session_id=None,
        request_id="run-1:skill-selection:pytest-debugging",
        occurred_at=datetime(2026, 7, 6, tzinfo=UTC),
        skill_name="pytest-debugging",
        manifest_hash="a" * 64,
        matched_reasons=("description", "glob:tests/**/*.py"),
    )

    encoded = event.to_json_dict()

    assert encoded["kind"] == "skill_selection"
    assert encoded["matched_reasons"] == ["description", "glob:tests/**/*.py"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/telemetry/test_events.py::test_goal_loop_event_serializes_stop_reason_and_budget tests/unit/telemetry/test_events.py::test_skill_invocation_event_serializes_manifest_hash_without_body tests/unit/telemetry/test_events.py::test_skill_selection_event_serializes_match_reasons -v
```

Expected: FAIL because telemetry event kinds/factories do not exist.

- [ ] **Step 3: Add telemetry event factories**

In `src/optimus/telemetry/events.py`, update `TelemetryEventKind`:

```python
    GOAL_LOOP = "goal_loop"
    SKILL_SELECTION = "skill_selection"
    SKILL_INVOCATION = "skill_invocation"
```

Add factories to `TelemetryEvent`:

```python
    @classmethod
    def goal_loop(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        iteration: int,
        stop_reason: str,
        credits_spent: Decimal,
        max_budget_credits: Decimal,
        summary: str,
    ) -> TelemetryEvent:
        return cls(
            kind=TelemetryEventKind.GOAL_LOOP,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={
                "iteration": iteration,
                "stop_reason": stop_reason,
                "credits_spent": credits_spent,
                "max_budget_credits": max_budget_credits,
                "summary": summary,
            },
        )

    @classmethod
    def skill_invocation(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        skill_name: str,
        manifest_hash: str,
        verdict: str,
        rule_id: str,
        requested_tool: str,
    ) -> TelemetryEvent:
        return cls(
            kind=TelemetryEventKind.SKILL_INVOCATION,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={
                "skill_name": skill_name,
                "manifest_hash": manifest_hash,
                "verdict": verdict,
                "rule_id": rule_id,
                "requested_tool": requested_tool,
            },
        )

    @classmethod
    def skill_selection(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        request_id: str,
        occurred_at: datetime,
        skill_name: str,
        manifest_hash: str,
        matched_reasons: tuple[str, ...],
    ) -> TelemetryEvent:
        return cls(
            kind=TelemetryEventKind.SKILL_SELECTION,
            run_id=run_id,
            session_id=session_id,
            request_id=request_id,
            occurred_at=occurred_at,
            payload={
                "skill_name": skill_name,
                "manifest_hash": manifest_hash,
                "matched_reasons": matched_reasons,
            },
        )
```

- [ ] **Step 4: Thread optional event sinks**

Update `GoalLoopController.__init__()` in `src/optimus/loops/controller.py`:

```python
from collections.abc import Callable
from optimus.telemetry.events import TelemetryEvent

...
        event_sink: Callable[[TelemetryEvent], None] | None = None,
...
        self._event_sink = event_sink
```

When returning a stop result, emit:

```python
    def _emit_stop(self, *, state: IterationState, stop_reason: LoopStopReason, summary: str) -> None:
        if self._event_sink is None:
            return
        self._event_sink(
            TelemetryEvent.goal_loop(
                run_id=state.run_id,
                session_id=state.session_id,
                request_id=f"{state.run_id}:loop:{state.iteration}",
                occurred_at=self._now(),
                iteration=state.iteration,
                stop_reason=stop_reason.value,
                credits_spent=state.credits_spent,
                max_budget_credits=self._policy.max_budget_credits,
                summary=summary,
            )
        )
```

Call `_emit_stop()` immediately before each `return GoalLoopResult(...)`.

Update `SkillInvocationPolicy.__init__()` in `src/optimus/skills/invocation.py`:

```python
from collections.abc import Callable
from datetime import UTC, datetime
from optimus.telemetry.events import TelemetryEvent

...
    def __init__(
        self,
        *,
        trust_policy: SkillTrustPolicy | None = None,
        event_sink: Callable[[TelemetryEvent], None] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._trust_policy = trust_policy or SkillTrustPolicy()
        self._event_sink = event_sink
        self._now = now or (lambda: datetime.now(tz=UTC))
```

Add:

```python
    def _emit(
        self,
        *,
        manifest: SkillManifest,
        run_id: str,
        session_id: str | None,
        requested_tool: ToolSurface,
        decision: SkillInvocationDecision,
    ) -> None:
        if self._event_sink is None:
            return
        self._event_sink(
            TelemetryEvent.skill_invocation(
                run_id=run_id,
                session_id=session_id,
                request_id=f"{run_id}:skill-invocation:{manifest.name}",
                occurred_at=self._now(),
                skill_name=manifest.name,
                manifest_hash=manifest.manifest_hash,
                verdict=decision.verdict.value,
                rule_id=decision.rule_id,
                requested_tool=requested_tool.value,
            )
        )
```

Call `_emit()` from `preflight_with_guard()` after `authorize_tool()` returns a decision. If the skill decision allows and `PreToolGuard` later blocks, emit a second skill event with the guard rule only if reviewers want both signals; the minimal required signal is the skill policy outcome.

Also update `SkillRegistry` in `src/optimus/skills/registry.py` to accept optional telemetry:

```python
from collections.abc import Callable
from datetime import UTC, datetime

from optimus.telemetry.events import TelemetryEvent


class SkillRegistry:
    def __init__(
        self,
        manifests: tuple[SkillManifest, ...],
        *,
        event_sink: Callable[[TelemetryEvent], None] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._manifests = manifests
        self._loaded_body_paths: list[str] = []
        self._event_sink = event_sink
        self._now = now or (lambda: datetime.now(tz=UTC))
```

When `match()` appends a `SkillMatch`, emit immediately after appending. If `from_paths()` needs telemetry in production wiring, extend it to accept the same optional `event_sink` and `now` parameters and pass them through to `cls(...)`:

```python
    def _emit_selection(self, *, run_id: str, session_id: str | None, match: SkillMatch) -> None:
        if self._event_sink is None:
            return
        self._event_sink(
            TelemetryEvent.skill_selection(
                run_id=run_id,
                session_id=session_id,
                request_id=f"{run_id}:skill-selection:{match.manifest.name}",
                occurred_at=self._now(),
                skill_name=match.manifest.name,
                manifest_hash=match.manifest.manifest_hash,
                matched_reasons=match.matched_reasons,
            )
        )
```

Use the existing `run_id` and `session_id` parameters on `match()` to emit the selection event, and keep the tests in `tests/unit/skills/test_registry.py` on that signature:

```python
matches = registry.match(
    run_id="run-1",
    session_id="session-1",
    task_text="Please debug the failing pytest test",
    changed_paths=("tests/unit/test_example.py",),
    execution_mode=ExecutionMode.AGENT,
)
```

- [ ] **Step 5: Run telemetry and integration tests**

Run:

```bash
pytest tests/unit/telemetry/test_events.py tests/unit/loops/test_controller.py tests/unit/skills/test_registry.py tests/unit/skills/test_invocation.py tests/integration/loops/test_goal_loop_guardrail_flow.py tests/integration/skills/test_skill_guardrail_flow.py -v
```

Expected: PASS.

- [ ] **Step 6: Local checkpoint**

Run:

```bash
git diff --check
```

Commit only if explicitly approved:

```bash
git add src/optimus/telemetry/events.py src/optimus/loops src/optimus/skills tests/unit/telemetry/test_events.py tests/unit/loops tests/unit/skills tests/integration/loops tests/integration/skills
git commit -m "Record loop and skill workflow telemetry."
```

---

## Task 8: Documentation and Golden/Release Visibility

**Traceability:** Roadmap Plan 9, Test Strategy 14.8-14.9, Plan 10 input-signal dependency

**Files:**
- Modify: `README.md`
- Optional modify: `tests/fixtures/golden_tasks/phase1_golden_tasks.json`
- Optional modify: `tests/unit/golden/test_tasks.py`

- [ ] **Step 1: Update README with Plan 9 operator contract**

Add a concise section to `README.md`:

```markdown
### Bounded Goal Loops and Curated Workflow Skills

Plan 9 adds architectural support for bounded goal-driven loops and curated
workflow skills. Loops are not the default execution mode. They are enabled only
when a task has a machine-checkable completion condition and explicit
`LoopBudgetPolicy` bounds for iterations, Optimus credits, wall-clock time, and
repeated failures.

Loop iterations persist progress to an append-only ledger and must use the same
`PreToolGuard` and permission policy as ordinary Agent-mode tool calls. A loop
that reaches completion, budget exhaustion, max iterations, wall-clock timeout,
repeated failure, or human halt records a stable `LoopStopReason`.

Skills are reviewed Markdown artifacts with frontmatter metadata. Trusted skills
may be loaded only when their description or globs match the task. Draft skills
are blocked in Agent mode, and a skill's `allowed_tools` list can only narrow
tool use. It cannot override project or user deny rules.
```

- [ ] **Step 2: Decide whether to add a golden fixture**

Inspect the existing golden task schema in `tests/fixtures/golden_tasks/phase1_golden_tasks.json` and `src/optimus/golden/tasks.py`. The current golden runner validates an ordered `expected_tools` trajectory and consumes harness results; a schema-valid fixture without a matching harness scenario/result will fail golden tests and release-gate evaluation.

Default to the README fallback below. Add a fixture only if the implementation also adds the corresponding harness scenario/result producer and uses real tool names from the harness trajectory. If that support exists, the fixture shape must look like:

```json
{
  "task_id": "plan9-bounded-loop-skill-policy",
  "description": "Use a bounded loop to process a small test queue and load only a trusted pytest skill.",
  "expected_mode": "agent",
  "expected_tools": ["file_reader", "test_runner"],
  "max_cost_usd": "0.05",
  "expected_final_state": "completed",
  "mutation_expected": false,
  "release_gate": false
}
```

If there is no matching harness scenario/result producer, or if loop stop reasons and skill trust decisions cannot be asserted directly, do not force Plan 9 into `phase1_golden_tasks.json`. Record the decision in README instead:

```markdown
Plan 9 loop and skill behavior is covered by `tests/unit/loops`,
`tests/unit/skills`, `tests/integration/loops`, and `tests/integration/skills`.
It is not added to `phase1_golden_tasks.json` until the golden schema can assert
loop stop reasons and skill trust decisions directly.
```

- [ ] **Step 3: Run docs and golden-adjacent tests**

Run:

```bash
pytest tests/unit/golden tests/unit/loops tests/unit/skills tests/integration/loops tests/integration/skills -v
```

Expected: PASS.

- [ ] **Step 4: Local checkpoint**

Run:

```bash
git diff --check
```

Commit only if explicitly approved:

```bash
git add README.md tests/fixtures/golden_tasks/phase1_golden_tasks.json tests/unit/golden/test_tasks.py
git commit -m "Document bounded loops and workflow skills."
```

---

## Task 9: Focused Verification and Sign-Off

**Files:**
- Verify: `src/optimus/loops`
- Verify: `src/optimus/skills`
- Verify: `src/optimus/guardrails`
- Verify: `src/optimus/tools`
- Verify: `src/optimus/telemetry/events.py`

- [ ] **Step 1: Run Plan 9 unit tests**

Run:

```bash
pytest tests/unit/loops tests/unit/skills -v
```

Expected: PASS.

- [ ] **Step 2: Run guardrail and tool regression tests**

Run:

```bash
pytest tests/unit/guardrails tests/unit/tools tests/integration/guardrails -v
```

Expected: PASS.

- [ ] **Step 3: Run Plan 9 integration tests**

Run:

```bash
pytest tests/integration/loops tests/integration/skills -v
```

Expected: PASS.

- [ ] **Step 4: Run telemetry regression tests**

Run:

```bash
pytest tests/unit/telemetry tests/integration/telemetry -v
```

Expected: PASS.

- [ ] **Step 5: Run focused coverage gate**

Run:

```bash
pytest tests/unit/loops tests/unit/skills tests/unit/guardrails tests/unit/tools tests/unit/telemetry tests/integration/loops tests/integration/skills tests/integration/guardrails --cov=optimus.loops --cov=optimus.skills --cov=optimus.guardrails --cov=optimus.tools --cov=optimus.telemetry --cov-branch --cov-report=term-missing --cov-fail-under=80
```

Expected: PASS with coverage >= 80 for affected production packages.

- [ ] **Step 6: Run full package gate if the environment has all dev dependencies**

Run:

```bash
pytest --cov=optimus --cov-branch --cov-report=term-missing -v
```

Expected: PASS with aggregate Python production-code coverage >= 80. If the local environment lacks a dependency such as `confusable_homoglyphs`, report the exact import error and the narrower passing gates instead of claiming full-suite success.

- [ ] **Step 7: Run release gate as non-blocking evidence if Plan 8.5 is merged**

Run with provider keys cleared and only Optimus credentials present:

```bash
python tools/run_phase1_release_gate.py --golden-results reports/phase1-golden-results.json
```

Expected: PASS only when Plan 8.5 release gates, golden task results, one-key scan, unit/integration, coverage, and diff checks all pass. If no real Optimus-only golden result JSON exists yet, report this as "not run - staging Gateway E2E evidence still deferred" rather than failing Plan 9 implementation verification.

- [ ] **Step 8: Check diff hygiene**

Run:

```bash
git status --short
git diff --check
```

Expected: only intentional Plan 9 files are modified or added. Pre-existing `.idea`, `.claude`, `.cursor`, or other unrelated noise remains unstaged and untouched.

- [ ] **Step 9: Commit**

Only if explicitly approved:

```bash
git add src/optimus/loops src/optimus/skills src/optimus/telemetry/events.py src/optimus/telemetry/serialization.py src/optimus/telemetry/subjects.py src/optimus/telemetry/redaction.py src/optimus/guardrails/pre_tool.py tests/unit/loops tests/unit/skills tests/integration/loops tests/integration/skills tests/unit/telemetry/test_events.py tests/unit/telemetry/test_serialization.py README.md
git commit -m "Add bounded goal loops and curated workflow skills."
```

## Deferred Decisions and Follow-Ups

- **Plan 8.5 staging Gateway E2E evidence:** remains a release sign-off evidence task, not a Plan 9 implementation prerequisite. Plan 9 verification must state whether the real Optimus-only golden results JSON was available.
- **Shadow reuse across retries:** remains after Plan 9. Do not mix shadow workspace performance work into loop/skill contracts.
- **Loop persistence backend:** this plan starts with in-memory and JSONL ledgers. Redis-backed loop progress can be added later only after retention, key schema, and high-cardinality policy are specified.
- **Skill repository location:** this plan supports loading from explicit paths. A repo-wide default location such as `.optimus/skills` or `docs/skills` should be decided after the first trusted skills are authored and reviewed.
- **Golden schema for loop/skill assertions:** if the current golden task schema cannot assert stop reasons and skill trust decisions directly, defer fixture-level golden coverage until the schema can represent those outcomes honestly.

## Self-Review

- Spec coverage: loop stop conditions are covered by Tasks 1-4 and 7; skill match/trust/tool enforcement by Tasks 5-7; documentation and verification by Tasks 8-9.
- Plan 8.5 follow-ups: classified explicitly and not silently absorbed into Plan 9.
- One-key model: the only model-touching loop component is `GatewayCompletionEvaluator`, which uses `GatewayClient` and `OPTIMUS_GATEWAY_URL` / `OPTIMUS_API_KEY` configuration.
- Guardrail boundary: loops and skills call into existing `PreToolGuard` / `PermissionPolicy`; neither can bypass mode rules, deny rules, or shell validation.
- Reviewer hardening: stop precedence is explicit, the controller owns guarded tools, Task 2 avoids circular imports through model-level protocols, skill hashes cover full file contents, deterministic completion evidence is persisted and actionable, post-iteration deterministic stops skip paid evaluator calls, and mid-run halt checks are reachable.
- Revision 2 fixes: controller tests use `tmp_path`, ledger tests import `pytest`, JSONL output masks workspace paths and generic `token=` values, skill-selection telemetry asserts list serialization, evaluator completion cost is not double-counted, and the golden fixture path defaults to README fallback unless a real harness scenario exists.
- Cost boundary: deterministic loop/skill resolution is zero-token; Gateway evaluator cost comes from gateway usage fields and never estimates provider cost locally.
- TDD compliance: each production task starts with failing tests and exact commands.
- Placeholder scan: no task contains unresolved implementation placeholders; optional golden fixture work has an explicit branch based on existing schema capability.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-06-bounded-goal-loops-curated-workflow-skills.md`.

Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - execute tasks in this session using `superpowers:executing-plans`, with checkpoints.

Plan 9 should be implemented only after Plan 8.5 is accepted or merged to `main`. Branch from latest `main` with the repo convention, for example `agent/cursor/bounded-goal-loops-skills`, and keep implementation commits limited to the files named in this plan unless review feedback expands scope.
