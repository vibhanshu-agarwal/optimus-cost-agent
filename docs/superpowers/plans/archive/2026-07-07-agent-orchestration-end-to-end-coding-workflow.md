# Agent Orchestration and End-to-End Coding Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Implemented (Phase 1). See README.md's "Phase 1 Agent Orchestration" feature section and
this plan's entry under Plan 9.5 in `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` for
current build status. This plan predates this project's per-step checkbox-tracking convention, so
its steps below were never intended to be individually ticked.

**Goal:** Compose the existing Phase 1 primitives into a working local-first coding agent that can plan, request approval, execute guarded mutations, validate outcomes, and produce real golden-task evidence before Plan 11 adds context-window intelligence.

**Architecture:** Add a small `optimus.agent` package that owns task-level orchestration above the existing ACP, gateway, evidence, guardrail, mutation, retry, loop, skill, telemetry, and golden-task primitives. The agent runner exposes a typed run contract, drives the Plan/Approval/Execute/Validate lifecycle through `RuntimeContext` and `TransitionValidator`, and delegates all side effects to existing guarded tool wrappers with the dispatcher's guard/audit sink injected when available. ACP gains one task-level method, `optimus.agent.run`, while the existing primitive methods remain available for focused tests and lower-level clients.

**Tech Stack:** Python >=3.14, pydantic >=2.8, pytest, pytest-asyncio, coverage.py, pytest-cov, existing `optimus.acp`, `optimus.gateway`, `optimus.evidence`, `optimus.runtime`, `optimus.tools`, `optimus.guardrails`, `optimus.gates`, `optimus.retry`, `optimus.loops`, `optimus.skills`, `optimus.telemetry`, `optimus.golden`, and `optimus.release`. No new runtime dependency is required.

## Global Constraints

- Keep local runtime credentials limited to `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`.
- Do not introduce local Tavily, OpenAI, OpenRouter, GLM, LangSmith, Anthropic, Azure OpenAI, or provider keys.
- Plan/Chat mode remains advisory-only and must not mutate files, run shell commands, call MCP side-effect tools, or perform web side effects.
- Agent mode mutation must pass through `AwaitingApproval`, `MutationGuard` / `assert_mutation_allowed()`, `PreToolGuard`, and `PermissionPolicy`.
- Agent-mode approval must be bound to the exact plan text through a deterministic `plan_hash`; approved requests without both `approval_id` and `plan_hash` are invalid.
- ACP callers may pass lower-case wire modes (`"plan"`, `"chat"`, `"agent"`), but the server model normalizes them to `ExecutionMode` before orchestration.
- The dispatcher owns the configured workspace root; request `workspace_root` values must resolve inside that configured root.
- All Gateway/model-touching calls must use `GatewayClient`; usage and cost must come from gateway response fields, not local estimates.
- Budget checks use gateway `cost_usd` values accumulated per run; the runner terminates with `stop_reason="BUDGET_EXHAUSTED"` when the configured dollar budget is exceeded.
- Every task uses TDD: write or update the failing test first, run it to observe failure, implement minimum code, then refactor with tests green.
- Plan 11 context-window optimization, intelligent selection, intelligent pruning, context-regret scoring, ablation suites, and calibrated cost-savings gates are out of scope.

---

## Source Anchors

- `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
  - Plans 1-9 provide the runtime, guardrail, evidence, usage, release, loop, and skill primitives.
  - Plan 11 starts only once the release skeleton and guardrail/input surface are stable.
- `docs/superpowers/plans/2026-07-06-bounded-goal-loops-curated-workflow-skills.md`
  - Plan 9 provides `GoalLoopController`, completion evaluation, progress ledger, guarded loop tools, `SkillRegistry`, and skill invocation policy.
- `tests/fixtures/golden_tasks/phase1_golden_tasks.json`
  - Existing golden scenarios already describe expected task-level coding-agent behavior.
- Current implementation anchors:
  - `src/optimus/acp/dispatcher.py`
  - `src/optimus/runtime/state.py`
  - `src/optimus/runtime/mutation.py`
  - `src/optimus/tools/mutation_tools.py`
  - `src/optimus/guardrails/pre_tool.py`
  - `src/optimus/loops/controller.py`
  - `src/optimus/skills/registry.py`
  - `src/optimus/golden/tasks.py`
  - `src/optimus/golden/runner.py`
  - `src/optimus/release/defaults.py`

## Current Gap

Plan 9 is implemented and validated, but the repository still mostly exposes primitives:

- ACP supports `optimus.gateway.responses`, `optimus.evidence.search`, `optimus.evidence.extract`, and `optimus.mutation.writeFile`.
- Golden tasks describe full coding-agent trajectories, but the current release gate consumes externally supplied `GoldenTaskResult` JSON.
- There is no task-level runner that can receive a coding task and produce an observed trajectory by composing planning, approval, tool use, mutation, validation, loop stop reasons, skill selection, telemetry, and golden-task evidence.
- There is no first-party harness evidence for the Phase 1 subset that Plan 9.5 should own: `explain-small-function`, `docstring-single-function`, `plan-then-approve-agent`, and `budget-exhausted`.

Plan 9.5 closes that gap. It should leave the project with a working Phase 1 Agent before Plan 11 makes the Agent smarter.

## File Structure

- Create: `src/optimus/agent/__init__.py` - public exports for the task-level agent contracts.
- Create: `src/optimus/agent/models.py` - `AgentRunRequest`, `AgentRunResult`, `AgentToolCall`, `AgentRunStatus`, `AgentApproval`.
- Create: `src/optimus/agent/tools.py` - tool adapter protocol and guarded adapters for file read, file write, shell/test runner, shadow apply, evidence, release gate, and skill preflight.
- Create: `src/optimus/agent/runner.py` - `AgentRunner`, lifecycle orchestration, prompt construction, approval gating, validation, bounded-loop integration.
- Create: `src/optimus/agent/golden.py` - `AgentGoldenTaskHarness` that runs golden tasks through `AgentRunner`.
- Modify: `src/optimus/acp/dispatcher.py` - add `optimus.agent.run` method.
- Modify: `src/optimus/golden/__init__.py` - export `AgentGoldenTaskHarness` only if it lives under `optimus.golden`; otherwise keep export under `optimus.agent`.
- Modify: `src/optimus/release/defaults.py` - support a real agent harness for the Plan 9.5 subset when configured, while preserving JSON harness support for external staging evidence.
- Modify: `tools/run_phase1_release_gate.py` - add real-agent harness CLI wiring and task-id filtering for the Plan 9.5 subset.
- Modify: `src/optimus/telemetry/events.py` - add `AGENT_RUN` event kind and factory.
- Modify: `README.md` - document the task-level agent run path.
- Create: `tests/unit/agent/test_models.py`
- Create: `tests/unit/agent/test_tools.py`
- Create: `tests/unit/agent/test_runner.py`
- Create: `tests/unit/agent/test_golden.py`
- Create: `tests/integration/agent/test_plan_chat_agent_run.py`
- Create: `tests/integration/agent/test_approved_mutation_run.py`
- Create: `tests/integration/agent/test_golden_harness_real_runner.py`
- Modify: `tests/unit/acp/test_dispatcher.py`
- Modify: `tests/unit/telemetry/test_events.py`
- Modify: `tests/unit/release/test_defaults.py`

## Human Agile Sizing

This is about 1-2 weeks of human development effort:

- Day 1: agent run models and typed result trajectory.
- Day 2: tool adapters and guarded tool-call recording.
- Day 3: Plan/Chat runner flow and Gateway planning call.
- Day 4: Agent-mode approval and mutation flow.
- Day 5: validation runner and bounded-loop stop integration.
- Day 6: skill selection and invocation wiring.
- Day 7: ACP `optimus.agent.run` endpoint.
- Day 8: real golden harness and release-gate wiring.
- Day 9: telemetry and README.
- Day 10: focused verification, coverage, and review hardening.

---

## Task 1: Agent Run Models

**Traceability:** Phase 1 roadmap Plans 2, 7, 8, 9; golden task contract

**Files:**
- Create: `src/optimus/agent/__init__.py`
- Create: `src/optimus/agent/models.py`
- Create: `tests/unit/agent/test_models.py`

**Interfaces:**
- Produces: `AgentRunRequest`, `AgentRunResult`, `AgentRunStatus`, `AgentToolCall`, `AgentApproval`.
- Consumes later: `AgentRunner.run(request: AgentRunRequest) -> AgentRunResult`.

- [ ] **Step 1: Write failing model tests**

Create `tests/unit/agent/test_models.py`:

```python
from decimal import Decimal

import pytest
from pydantic import ValidationError

from optimus.agent.models import AgentApproval, AgentRunRequest, AgentRunResult, AgentRunStatus, AgentToolCall
from optimus.runtime.modes import ExecutionMode


def test_agent_run_request_requires_run_id_task_and_workspace(tmp_path):
    request = AgentRunRequest(
        run_id="run-1",
        session_id="session-1",
        task="Add a docstring to src/example.py",
        execution_mode=ExecutionMode.AGENT,
        workspace_root=tmp_path,
        approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash="hash-1"),
        max_cost_usd=Decimal("0.05"),
        completion_condition="example.py contains a docstring",
    )

    assert request.workspace_root == tmp_path.resolve()
    assert request.approval.approved is True
    assert request.max_cost_usd == Decimal("0.05")


def test_agent_run_request_rejects_relative_workspace():
    with pytest.raises(ValidationError, match="workspace_root must be absolute"):
        AgentRunRequest(run_id="run-1", task="Explain code", execution_mode=ExecutionMode.PLAN, workspace_root=".")


def test_agent_run_request_normalizes_lower_case_wire_mode(tmp_path):
    request = AgentRunRequest(run_id="run-1", task="Explain code", execution_mode="plan", workspace_root=tmp_path)

    assert request.execution_mode is ExecutionMode.PLAN


def test_agent_approval_requires_id_and_plan_hash_when_approved():
    with pytest.raises(ValidationError, match="approved requests require approval_id and plan_hash"):
        AgentApproval(approved=True, approval_id="approval-1")


def test_agent_run_result_records_tool_trajectory_and_final_state():
    result = AgentRunResult(
        run_id="run-1",
        session_id=None,
        execution_mode=ExecutionMode.AGENT,
        status=AgentRunStatus.COMPLETED,
        final_state="COMPLETED",
        output_text="Added the docstring.",
        tool_calls=(
            AgentToolCall(tool_name="file_reader", summary="read src/example.py", cost_usd=Decimal("0")),
            AgentToolCall(tool_name="write_file", summary="wrote src/example.py", cost_usd=Decimal("0")),
        ),
        total_cost_usd=Decimal("0.012"),
        mutation_count=1,
        provider_keys_resolvable=(),
        stop_reason=None,
    )

    assert tuple(call.tool_name for call in result.tool_calls) == ("file_reader", "write_file")
    assert result.mutation_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/agent/test_models.py -v
```

Expected: FAIL because `optimus.agent` does not exist.

- [ ] **Step 3: Implement models**

Create `src/optimus/agent/models.py` with frozen pydantic models:

```python
from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from optimus.runtime.modes import ExecutionMode


class AgentRunStatus(StrEnum):
    PLAN_READY = "plan_ready"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    TERMINATED = "terminated"
    FAILED = "failed"


class AgentApproval(BaseModel):
    model_config = ConfigDict(frozen=True)

    approved: bool = False
    approval_id: str | None = None
    plan_hash: str | None = None

    @model_validator(mode="after")
    def require_bound_approval(self) -> "AgentApproval":
        if self.approved and (not self.approval_id or not self.plan_hash):
            raise ValueError("approved requests require approval_id and plan_hash")
        return self


class AgentToolCall(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool_name: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    cost_usd: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    authorization_outcome: str = "ALLOW"


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    session_id: str | None = None
    task: str = Field(min_length=1)
    execution_mode: ExecutionMode
    workspace_root: Path
    approval: AgentApproval = Field(default_factory=AgentApproval)
    max_cost_usd: Decimal = Field(default=Decimal("0.05"), ge=Decimal("0"))
    skill_paths: tuple[Path, ...] = ()
    completion_condition: str | None = None

    @field_validator("execution_mode", mode="before")
    @classmethod
    def normalize_execution_mode(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.upper()
        return value

    @field_validator("workspace_root")
    @classmethod
    def require_absolute_workspace(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("workspace_root must be absolute")
        return value.resolve()


class AgentRunResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    session_id: str | None
    execution_mode: ExecutionMode
    status: AgentRunStatus
    final_state: str = Field(min_length=1)
    output_text: str = Field(min_length=1)
    tool_calls: tuple[AgentToolCall, ...] = ()
    total_cost_usd: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    mutation_count: int = Field(default=0, ge=0)
    provider_keys_resolvable: tuple[str, ...] = ()
    plan_hash: str | None = None
    stop_reason: str | None = None
```

Create `src/optimus/agent/__init__.py`:

```python
from optimus.agent.models import AgentApproval, AgentRunRequest, AgentRunResult, AgentRunStatus, AgentToolCall

__all__ = [
    "AgentApproval",
    "AgentRunRequest",
    "AgentRunResult",
    "AgentRunStatus",
    "AgentToolCall",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/unit/agent/test_models.py -v
```

Expected: PASS.

---

## Task 2: Guarded Agent Tool Adapters

**Traceability:** Plans 4, 5, 6.5, 8.5, 9

**Files:**
- Create: `src/optimus/agent/tools.py`
- Create: `tests/unit/agent/test_tools.py`

**Interfaces:**
- Consumes: `AgentRunRequest`, `RuntimeContext`, `PreToolGuard`, mutation wrappers.
- Produces: `AgentToolAdapter` protocol and `AgentToolbox` methods:
  - `read_file(path: Path) -> tuple[str, AgentToolCall]`
  - `write_file(path: Path, content: str) -> AgentToolCall`
  - `run_tests(command: tuple[str, ...]) -> AgentToolCall`
  - `AgentToolbox.for_workspace(workspace_root: str | Path, context: RuntimeContext, run_id: str, session_id: str | None = None, guard: PreToolGuard | None = None) -> AgentToolbox`

- [ ] **Step 1: Write failing tool adapter tests**

Create `tests/unit/agent/test_tools.py`:

```python
from pathlib import Path

import pytest

from optimus.agent.tools import AgentToolbox
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.state import AgentState, RuntimeContext


def approved_context() -> RuntimeContext:
    return RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.EXECUTING,
        approval_granted=True,
        user_approval_id="approval-1",
    )


def test_toolbox_reads_workspace_file_and_records_tool_call(tmp_path):
    target = tmp_path / "src" / "example.py"
    target.parent.mkdir()
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    toolbox = AgentToolbox.for_workspace(workspace_root=tmp_path, context=approved_context(), run_id="run-1")

    text, call = toolbox.read_file(target)

    assert "return 1" in text
    assert call.tool_name == "file_reader"
    assert call.authorization_outcome == "ALLOW"


def test_toolbox_blocks_secret_file_write(tmp_path):
    toolbox = AgentToolbox.for_workspace(workspace_root=tmp_path, context=approved_context(), run_id="run-1")

    with pytest.raises(PermissionError, match="secret or credential path access is denied"):
        toolbox.write_file(tmp_path / ".env", "OPENAI_API_KEY=local")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/agent/test_tools.py -v
```

Expected: FAIL because `optimus.agent.tools` does not exist.

- [ ] **Step 3: Implement minimal guarded toolbox**

Create `src/optimus/agent/tools.py`:

```python
from __future__ import annotations

from pathlib import Path

from optimus.agent.models import AgentToolCall
from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard, PreToolRequest, PreToolVerdict
from optimus.runtime.modes import GenerationScope
from optimus.runtime.mutation import MutationForbidden
from optimus.runtime.state import RuntimeContext
from optimus.tools.mutation_tools import write_file as guarded_write_file


class AgentToolbox:
    def __init__(
        self,
        *,
        workspace_root: Path,
        context: RuntimeContext,
        run_id: str,
        session_id: str | None,
        guard: PreToolGuard,
    ) -> None:
        self._workspace_root = workspace_root.resolve()
        self._context = context
        self._run_id = run_id
        self._session_id = session_id
        self._guard = guard

    @classmethod
    def for_workspace(
        cls,
        *,
        workspace_root: str | Path,
        context: RuntimeContext,
        run_id: str,
        session_id: str | None = None,
        guard: PreToolGuard | None = None,
    ) -> "AgentToolbox":
        root = Path(workspace_root).resolve()
        return cls(
            workspace_root=root,
            context=context,
            run_id=run_id,
            session_id=session_id,
            guard=guard or PreToolGuard.for_workspace(workspace_root=root, allowed_network_hosts=()),
        )

    def read_file(self, path: str | Path) -> tuple[str, AgentToolCall]:
        target = Path(path).resolve()
        result = self._guard.check(
            PreToolRequest(
                run_id=self._run_id,
                session_id=self._session_id,
                execution_mode=self._context.execution_mode,
                tool_surface=ToolSurface.FILE_READ,
                action="read_file",
                target_path=str(target),
                generation_scope=GenerationScope.INLINE_SNIPPET,
                approval_granted=self._context.approval_granted,
                approver=self._context.user_approval_id,
            )
        )
        if result.verdict is not PreToolVerdict.ALLOW:
            raise PermissionError(result.reason)
        return target.read_text(encoding="utf-8"), AgentToolCall(
            tool_name="file_reader",
            summary=f"read {target.relative_to(self._workspace_root).as_posix()}",
            authorization_outcome=result.verdict.value,
        )

    def write_file(self, path: str | Path, content: str) -> AgentToolCall:
        target = Path(path).resolve()
        try:
            guarded_write_file(target, content, context=self._context, guard=self._guard)
        except MutationForbidden as exc:
            raise PermissionError(str(exc)) from exc
        return AgentToolCall(
            tool_name="write_file",
            summary=f"wrote {target.relative_to(self._workspace_root).as_posix()}",
            authorization_outcome="ALLOW",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/unit/agent/test_tools.py -v
```

Expected: PASS.

---

## Task 3: Task-Level Agent Runner Lifecycle

**Traceability:** Plans 2, 3, 5, 7, 8, 9

**Files:**
- Create: `src/optimus/agent/runner.py`
- Modify: `src/optimus/agent/__init__.py`
- Create: `tests/unit/agent/test_runner.py`
- Create: `tests/integration/agent/test_plan_chat_agent_run.py`
- Create: `tests/integration/agent/test_approved_mutation_run.py`

**Interfaces:**
- Consumes: `GatewayClient`, `AgentToolbox`, `RuntimeContext`, `TransitionValidator`, optional `PreToolGuard`, `GoalLoopController`, optional `SkillRegistry`.
- Produces: `AgentRunner.run(request: AgentRunRequest) -> AgentRunResult`.

- [ ] **Step 1: Write failing lifecycle tests**

Create `tests/unit/agent/test_runner.py`:

```python
from decimal import Decimal

from optimus.agent.models import AgentApproval, AgentRunRequest, AgentRunStatus
from optimus.agent.runner import AgentRunner
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.runtime.modes import ExecutionMode


class FakeGatewayClient:
    def __init__(self, output_text: str = "Plan text") -> None:
        self.calls = []
        self.output_text = output_text

    def create_response(self, *, model: str, input_text: str, metadata=None):
        self.calls.append({"model": model, "input_text": input_text, "metadata": metadata})
        return GatewayResponse(
            response_id="resp-1",
            output_text=self.output_text,
            gateway_usage=GatewayUsage(
                gateway_request_id="gw-1",
                provider="glm",
                billing_units=5,
                cost_usd=Decimal("0.002"),
            ),
            raw={"id": "resp-1"},
        )


def test_plan_mode_returns_plan_without_mutation(tmp_path):
    target = tmp_path / "src" / "example.py"
    target.parent.mkdir()
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    gateway = FakeGatewayClient("READ src/example.py\nExplain the function.")
    runner = AgentRunner(gateway_client=gateway, model="glm-5.2")

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Explain a small function",
            execution_mode=ExecutionMode.PLAN,
            workspace_root=tmp_path,
        )
    )

    assert result.status is AgentRunStatus.COMPLETED
    assert result.final_state == "CHAT_ONLY"
    assert result.mutation_count == 0
    assert result.total_cost_usd == Decimal("0.002")
    assert tuple(call.tool_name for call in result.tool_calls) == ("file_reader",)
    assert gateway.calls[0]["metadata"]["run_id"] == "run-1"


def test_agent_mode_without_approval_returns_awaiting_approval(tmp_path):
    runner = AgentRunner(gateway_client=FakeGatewayClient("Plan: write the file."), model="glm-5.2")

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Add a docstring",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
        )
    )

    assert result.status is AgentRunStatus.AWAITING_APPROVAL
    assert result.final_state == "AWAITING_APPROVAL"
    assert result.mutation_count == 0
    assert result.plan_hash is not None


def test_agent_mode_with_approval_can_write_single_file(tmp_path):
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    runner = AgentRunner(
        gateway_client=FakeGatewayClient("WRITE example.py\ndef f():\n    \"\"\"Return one.\"\"\"\n    return 1\n"),
        model="glm-5.2",
    )

    plan_result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Add a docstring to example.py",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
        )
    )

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Add a docstring to example.py",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
            approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash=plan_result.plan_hash),
        )
    )

    assert result.status is AgentRunStatus.COMPLETED
    assert result.mutation_count == 1
    assert "Return one" in target.read_text(encoding="utf-8")
    assert tuple(call.tool_name for call in result.tool_calls) == ("file_reader", "write_file")


def test_agent_mode_rejects_approval_for_different_plan(tmp_path):
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    runner = AgentRunner(
        gateway_client=FakeGatewayClient("WRITE example.py\ndef f():\n    \"\"\"Return one.\"\"\"\n    return 1\n"),
        model="glm-5.2",
    )

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Add a docstring to example.py",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
            approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash="different-plan"),
        )
    )

    assert result.status is AgentRunStatus.AWAITING_APPROVAL
    assert result.mutation_count == 0
    assert "Return one" not in target.read_text(encoding="utf-8")


def test_agent_mode_terminates_when_gateway_cost_exceeds_budget(tmp_path):
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    runner = AgentRunner(gateway_client=FakeGatewayClient("READ example.py\nExplain before stopping."), model="glm-5.2")

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Explain code",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
            max_cost_usd=Decimal("0.001"),
        )
    )

    assert result.status is AgentRunStatus.TERMINATED
    assert result.stop_reason == "BUDGET_EXHAUSTED"
    assert result.mutation_count == 0
    assert tuple(call.tool_name for call in result.tool_calls) == ("file_reader",)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/agent/test_runner.py -v
```

Expected: FAIL because `AgentRunner` does not exist.

- [ ] **Step 3: Implement first runner slice**

Implement `src/optimus/agent/runner.py` with:

- `AgentRunner.__init__(gateway_client: GatewayClient, model: str, guard: PreToolGuard | None = None)`.
- Plan-mode and Chat-mode calls to `gateway_client.create_response()` with metadata `{"run_id": request.run_id, "session_id": request.session_id, "purpose": "agent_plan"}`. Treat `ExecutionMode.CHAT` as the same advisory-only path as `ExecutionMode.PLAN`.
- Lifecycle transitions through `TransitionValidator`: `IDLE -> PLANNING -> PLAN_READY`; Agent mode without approval then enters `AWAITING_APPROVAL`; approved Agent mode uses `AwaitingApproval.grant()` before `EXECUTING`.
- Pass the runner's optional `guard` into every `AgentToolbox.for_workspace(...)` call so ACP-created runners preserve the dispatcher's audit sink instead of creating an isolated guard.
- A deterministic `plan_hash = sha256(response.output_text.encode("utf-8")).hexdigest()` returned with `PLAN_READY` / `AWAITING_APPROVAL`; approved Agent requests must carry the matching hash before execution.
- Runner-level budget accounting from `GatewayUsage.cost_usd`. If accumulated cost exceeds `request.max_cost_usd`, allow already-authorized advisory reads to be recorded, then return `AgentRunStatus.TERMINATED`, `final_state="TERMINATED"`, and `stop_reason="BUDGET_EXHAUSTED"` before any mutation.
- Agent-mode no-approval result with `AgentRunStatus.AWAITING_APPROVAL`.
- A deterministic `READ <relative-path>` directive parser that calls `AgentToolbox.read_file()` in Plan/Chat and Agent modes so golden explain/docstring tasks can observe `file_reader`.
- Approved Agent-mode minimal deterministic write parser for test scaffolding:
  - Only accept output beginning with `WRITE <relative-path>\n<content>`.
  - Reject absolute paths and `..`.
  - Before every write, call `AgentToolbox.read_file()` for the target when it exists and record the read in the same trajectory.
  - Use `AgentToolbox.write_file()`.
  - Later tasks can replace the parser with structured Gateway output without changing the runner contract.

- [ ] **Step 4: Run lifecycle tests**

Run:

```bash
pytest tests/unit/agent/test_runner.py tests/integration/runtime/test_mode_boundary.py tests/unit/tools/test_mutation_tools.py -v
```

Expected: PASS.

---

## Task 4: ACP Task-Level Method

**Traceability:** ACP server and dispatcher, Plan 2 state boundary

**Files:**
- Modify: `src/optimus/acp/dispatcher.py`
- Modify: `tests/unit/acp/test_dispatcher.py`

**Interfaces:**
- Adds JSON-RPC method: `optimus.agent.run`.
- Params shape:
  - `run_id: str`
  - `session_id: str | null`
  - `task: str`
  - `execution_mode: "plan" | "chat" | "agent"`
  - `workspace_root: str`
  - `approval: {"approved": bool, "approval_id": str | null, "plan_hash": str | null}`
- Dispatcher owns `configured_workspace_root`; request `workspace_root` must resolve inside it.

- [ ] **Step 1: Write failing dispatcher test**

Add to `tests/unit/acp/test_dispatcher.py`:

```python
from optimus.runtime.modes import ExecutionMode


class FakeAgentRunner:
    def __init__(self):
        self.requests = []

    def run(self, request):
        from optimus.agent.models import AgentRunResult, AgentRunStatus
        from decimal import Decimal

        self.requests.append(request)
        return AgentRunResult(
            run_id=request.run_id,
            session_id=request.session_id,
            execution_mode=request.execution_mode,
            status=AgentRunStatus.COMPLETED,
            final_state="CHAT_ONLY",
            output_text="Plan text",
            total_cost_usd=Decimal("0.002"),
        )


def test_dispatcher_routes_agent_run_to_runner(tmp_path):
    agent_runner = FakeAgentRunner()
    dispatcher = JsonRpcDispatcher(agent_runner=agent_runner, workspace_root=tmp_path)

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "agent-run-1",
            "method": "optimus.agent.run",
            "params": {
                "run_id": "run-1",
                "task": "Explain code",
                "execution_mode": "plan",
                "workspace_root": str(tmp_path),
            },
        }
    )

    assert response["result"]["status"] == "completed"
    assert response["result"]["output_text"] == "Plan text"
    assert agent_runner.requests[0].run_id == "run-1"
    assert agent_runner.requests[0].execution_mode is ExecutionMode.PLAN


def test_dispatcher_rejects_agent_run_outside_configured_workspace(tmp_path):
    agent_runner = FakeAgentRunner()
    dispatcher = JsonRpcDispatcher(agent_runner=agent_runner, workspace_root=tmp_path)
    outside = tmp_path.parent / "outside"
    outside.mkdir(exist_ok=True)

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "agent-run-1",
            "method": "optimus.agent.run",
            "params": {
                "run_id": "run-1",
                "task": "Explain code",
                "execution_mode": "plan",
                "workspace_root": str(outside),
            },
        }
    )

    assert response["error"]["message"] == "workspace_root outside configured workspace"
    assert agent_runner.requests == []
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/unit/acp/test_dispatcher.py::test_dispatcher_routes_agent_run_to_runner -v
```

Expected: FAIL because dispatcher has no `agent_runner` argument or method handler.

- [ ] **Step 3: Implement dispatcher method**

Update `JsonRpcDispatcher.__init__()` to accept `agent_runner: AgentRunner | None = None` and `workspace_root: Path | str | None = None`. Store the resolved configured workspace root on the dispatcher. When constructing an `AgentRunner` inside dispatcher/server setup instead of injecting one, pass the dispatcher's `PreToolGuard` into `AgentRunner(..., guard=self._pre_tool_guard)`.

Add method handling before primitive mutation handling:

```python
if method == "optimus.agent.run":
    if self._agent_runner is None:
        return error_response(
            request_id=request_id,
            error=JsonRpcError(code=METHOD_NOT_FOUND, message="agent runner not configured"),
        )
    try:
        agent_request = AgentRunRequest.model_validate(request.get("params"))
    except ValidationError:
        return error_response(
            request_id=request_id,
            error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
        )
    if self._workspace_root is not None and not agent_request.workspace_root.is_relative_to(self._workspace_root):
        return error_response(
            request_id=request_id,
            error=JsonRpcError(code=INVALID_REQUEST, message="workspace_root outside configured workspace"),
        )
    result = self._agent_runner.run(agent_request)
    return success_response(request_id=request_id, result=result.model_dump(mode="json"))
```

- [ ] **Step 4: Run dispatcher regression tests**

Run:

```bash
pytest tests/unit/acp/test_dispatcher.py tests/integration/acp/test_server_stream.py -v
```

Expected: PASS.

---

## Task 5: Real Agent Golden Harness

**Traceability:** Plan 8/8.5 golden tasks and release gate, user expectation that the Agent performs Phase 1 coding tasks

**Files:**
- Create: `src/optimus/agent/golden.py`
- Modify: `src/optimus/agent/__init__.py`
- Create: `tests/unit/agent/test_golden.py`
- Create: `tests/integration/agent/test_golden_harness_real_runner.py`
- Modify: `src/optimus/release/defaults.py`
- Modify: `tests/unit/release/test_defaults.py`
- Modify: `tools/run_phase1_release_gate.py`
- Modify: `tests/integration/release/test_phase1_release_gate_cli.py`

**Interfaces:**
- Produces: `AgentGoldenTaskHarness(GoldenTaskHarness)` with `run(task: GoldenTask) -> GoldenTaskResult`.
- Produces: release-default wiring that accepts an explicit golden task filter for the Plan 9.5 subset.
- Produces: golden `actual_cost_usd` as total scenario cost; approved two-call Agent scenarios sum planning cost plus approved execution cost.
- Cost boundary note: `AgentRunner` enforces `max_cost_usd` per individual `AgentRunRequest`; `AgentGoldenTaskHarness` reports and evaluates summed scenario cost across the plan and approved execution calls. A future fixture can therefore pass individual runner budgets but fail golden evaluation if its total scenario cost exceeds the fixture cap; that is expected golden-gate behavior, not a runner bug.
- Consumes: `AgentRunner`, `GoldenTask`, workspace fixture factory.

- [ ] **Step 1: Write failing golden harness tests**

Create `tests/unit/agent/test_golden.py`:

```python
from decimal import Decimal

from optimus.agent.golden import AgentGoldenTaskHarness
from optimus.agent.models import AgentRunResult, AgentRunStatus, AgentToolCall
from optimus.golden.tasks import GoldenTask
from optimus.runtime.modes import ExecutionMode


class FakeRunner:
    def run(self, request):
        return AgentRunResult(
            run_id=request.run_id,
            session_id=request.session_id,
            execution_mode=request.execution_mode,
            status=AgentRunStatus.COMPLETED,
            final_state="completed",
            output_text="done",
            tool_calls=(AgentToolCall(tool_name="file_reader", summary="read", cost_usd=Decimal("0")),),
            total_cost_usd=Decimal("0.004"),
            mutation_count=0,
            provider_keys_resolvable=(),
        )


class SequenceRunner:
    def __init__(self, *results: AgentRunResult) -> None:
        self.results = list(results)
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        return self.results.pop(0)


def agent_task(task_id: str, max_cost_usd: Decimal = Decimal("0.020")) -> GoldenTask:
    return GoldenTask(
        task_id=task_id,
        description="Produce plan text, receive approval, then mutate.",
        expected_mode="agent",
        expected_tools=("file_reader", "write_file"),
        max_cost_usd=max_cost_usd,
        expected_final_state="completed",
        mutation_expected=True,
        release_gate=False,
    )


def run_result(
    *,
    execution_mode: ExecutionMode,
    status: AgentRunStatus,
    final_state: str,
    cost_usd: str,
    plan_hash: str | None = None,
    mutation_count: int = 0,
) -> AgentRunResult:
    return AgentRunResult(
        run_id="run-1",
        session_id=None,
        execution_mode=execution_mode,
        status=status,
        final_state=final_state,
        output_text="done",
        tool_calls=(AgentToolCall(tool_name="file_reader", summary="read", cost_usd=Decimal("0")),),
        total_cost_usd=Decimal(cost_usd),
        mutation_count=mutation_count,
        provider_keys_resolvable=(),
        plan_hash=plan_hash,
        stop_reason="BUDGET_EXHAUSTED" if status is AgentRunStatus.TERMINATED else None,
    )


def test_agent_golden_harness_converts_runner_result(tmp_path):
    task = GoldenTask(
        task_id="explain-small-function",
        description="Explain a function under 15 lines.",
        expected_mode="plan_chat",
        expected_tools=("file_reader",),
        max_cost_usd=Decimal("0.005"),
        expected_final_state="chat_only",
        mutation_expected=False,
        release_gate=False,
    )
    harness = AgentGoldenTaskHarness(runner=FakeRunner(), workspace_root=tmp_path)

    result = harness.run(task)

    assert result.task_id == "explain-small-function"
    assert result.actual_tools == ("file_reader",)
    assert result.actual_cost_usd == Decimal("0.004")


def test_agent_golden_harness_short_circuits_terminated_plan(tmp_path):
    runner = SequenceRunner(
        run_result(
            execution_mode=ExecutionMode.AGENT,
            status=AgentRunStatus.TERMINATED,
            final_state="terminated",
            cost_usd="0.002",
            plan_hash=None,
        )
    )
    harness = AgentGoldenTaskHarness(runner=runner, workspace_root=tmp_path)

    result = harness.run(agent_task("budget-exhausted", max_cost_usd=Decimal("0.001")))

    assert len(runner.requests) == 1
    assert result.actual_final_state == "terminated"
    assert result.actual_cost_usd == Decimal("0.002")


def test_agent_golden_harness_sums_plan_and_execution_cost(tmp_path):
    runner = SequenceRunner(
        run_result(
            execution_mode=ExecutionMode.AGENT,
            status=AgentRunStatus.AWAITING_APPROVAL,
            final_state="AWAITING_APPROVAL",
            cost_usd="0.003",
            plan_hash="plan-1",
        ),
        run_result(
            execution_mode=ExecutionMode.AGENT,
            status=AgentRunStatus.COMPLETED,
            final_state="completed",
            cost_usd="0.004",
            mutation_count=1,
        ),
    )
    harness = AgentGoldenTaskHarness(runner=runner, workspace_root=tmp_path)

    result = harness.run(agent_task("plan-then-approve-agent"))

    assert len(runner.requests) == 2
    assert runner.requests[1].approval.plan_hash == "plan-1"
    assert result.actual_cost_usd == Decimal("0.007")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/unit/agent/test_golden.py -v
```

Expected: FAIL because `AgentGoldenTaskHarness` does not exist.

- [ ] **Step 3: Implement harness**

Create `src/optimus/agent/golden.py`:

```python
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from optimus.agent.models import AgentApproval, AgentRunRequest, AgentRunResult, AgentRunStatus
from optimus.agent.runner import AgentRunner
from optimus.golden.runner import GoldenTaskHarness
from optimus.golden.tasks import GoldenTask, GoldenTaskResult
from optimus.release.credentials import scan_local_credentials
from optimus.runtime.modes import ExecutionMode


class AgentGoldenTaskHarness(GoldenTaskHarness):
    def __init__(self, *, runner: AgentRunner, workspace_root: str | Path) -> None:
        self._runner = runner
        self._workspace_root = Path(workspace_root).resolve()

    def run(self, task: GoldenTask) -> GoldenTaskResult:
        mode = ExecutionMode.AGENT if task.expected_mode == "agent" else ExecutionMode.PLAN
        approval = AgentApproval()
        plan_cost = Decimal("0")
        if mode is ExecutionMode.AGENT:
            plan_result = self._runner.run(
                AgentRunRequest(
                    run_id=f"golden:{task.task_id}:plan",
                    session_id=None,
                    task=task.description,
                    execution_mode=mode,
                    workspace_root=self._workspace_root,
                    max_cost_usd=task.max_cost_usd,
                )
            )
            plan_cost = plan_result.total_cost_usd
            if plan_result.status is AgentRunStatus.TERMINATED:
                return self._to_golden_result(task=task, result=plan_result, total_cost_usd=plan_cost)
            approval = AgentApproval(
                approved=True,
                approval_id=f"golden:{task.task_id}:approval",
                plan_hash=plan_result.plan_hash,
            )
        request = AgentRunRequest(
            run_id=f"golden:{task.task_id}",
            session_id=None,
            task=task.description,
            execution_mode=mode,
            workspace_root=self._workspace_root,
            approval=approval,
            max_cost_usd=task.max_cost_usd,
        )
        result = self._runner.run(request)
        return self._to_golden_result(task=task, result=result, total_cost_usd=plan_cost + result.total_cost_usd)

    def _to_golden_result(
        self,
        *,
        task: GoldenTask,
        result: AgentRunResult,
        total_cost_usd: Decimal,
    ) -> GoldenTaskResult:
        actual_mode = "agent" if result.execution_mode is ExecutionMode.AGENT else "plan_chat"
        credential_scan = scan_local_credentials()
        return GoldenTaskResult(
            task_id=task.task_id,
            actual_mode=actual_mode,
            actual_tools=tuple(call.tool_name for call in result.tool_calls),
            actual_cost_usd=total_cost_usd,
            actual_final_state=result.final_state.lower(),
            mutation_count=result.mutation_count,
            provider_keys_resolvable=credential_scan.provider_keys_resolvable,
        )
```

- [ ] **Step 4: Add integration coverage for real scenarios**

Create `tests/integration/agent/test_golden_harness_real_runner.py` with at least:

- `explain-small-function` plan-only scenario.
- `docstring-single-function` approved Agent-mode mutation scenario.
- `plan-then-approve-agent` two-call approval scenario that verifies the approved run carries the first call's `plan_hash`.
- `budget-exhausted` termination scenario.

Use fake Gateway responses with deterministic output and assert `evaluate_golden_task()` passes for each selected fixture.
The unit tests above cover the terminated-plan short-circuit and the two-call scenario cost sum.

Update `src/optimus/release/defaults.py` so the real agent harness path accepts a task-id filter:

```python
PLAN_9_5_REAL_AGENT_TASK_IDS = (
    "explain-small-function",
    "docstring-single-function",
    "plan-then-approve-agent",
    "budget-exhausted",
)
```

Add `golden_task_ids: tuple[str, ...] | None = None` to `build_phase1_release_gates(...)` immediately after `golden_harness`.

Update `_golden_task_suite_gate(golden_harness, golden_task_ids)`:

```python
def _golden_task_suite_gate(
    golden_harness: GoldenTaskHarness | None,
    golden_task_ids: tuple[str, ...] | None,
) -> tuple[bool, str]:
    if golden_harness is None:
        return False, "golden task harness not configured"
    tasks = load_golden_tasks(Path("tests/fixtures/golden_tasks/phase1_golden_tasks.json"))
    if golden_task_ids is not None:
        requested = set(golden_task_ids)
        tasks = tuple(task for task in tasks if task.task_id in requested)
    report = evaluate_golden_task_suite(tasks, harness=golden_harness)
    return report.passed, report.failure_summary
```

Keep the existing JSON harness path for the broader fixture file. Add a regression test proving unsupported fixture IDs are skipped by the Plan 9.5 real harness rather than converted into passing synthetic results.

Update `tools/run_phase1_release_gate.py` to add:

```python
parser.add_argument("--agent-harness", action="store_true", help="Run the Plan 9.5 golden subset through AgentGoldenTaskHarness.")
parser.add_argument("--task-id", action="append", default=None, help="Golden task id to include; may be supplied more than once.")
parser.add_argument("--agent-model", default="glm-5.2", help="Gateway model used by the real agent harness.")
```

Add these imports:

```python
from optimus.agent.golden import AgentGoldenTaskHarness
from optimus.agent.runner import AgentRunner
from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import GatewayClient
from optimus.release.defaults import PLAN_9_5_REAL_AGENT_TASK_IDS, build_phase1_release_gates
```

When `--agent-harness` is set, build the real harness and task filter:

```python
golden_task_ids = None
if args.agent_harness:
    settings = OptimusGatewaySettings.from_env()
    gateway_client = GatewayClient(settings=settings)
    agent_runner = AgentRunner(gateway_client=gateway_client, model=args.agent_model)
    golden_harness = AgentGoldenTaskHarness(runner=agent_runner, workspace_root=Path("."))
    golden_task_ids = tuple(args.task_id or PLAN_9_5_REAL_AGENT_TASK_IDS)
```

Pass `golden_task_ids=golden_task_ids` to `build_phase1_release_gates(...)`. Keep `--golden-results` mutually exclusive with `--agent-harness`.

Add to `tests/integration/release/test_phase1_release_gate_cli.py`:

```python
def test_release_cli_accepts_agent_harness_task_filter_text():
    text = RELEASE_CLI.read_text(encoding="utf-8")

    assert "--agent-harness" in text
    assert "--task-id" in text
    assert "AgentGoldenTaskHarness" in text
    assert "golden_task_ids=golden_task_ids" in text
```

- [ ] **Step 5: Run golden harness tests**

Run:

```bash
pytest tests/unit/agent/test_golden.py tests/integration/agent/test_golden_harness_real_runner.py tests/unit/golden tests/unit/release/test_defaults.py tests/integration/release/test_phase1_release_gate_cli.py -v
```

Expected: PASS.

---

## Task 6: Skills, Loops, Telemetry, and Stop Reasons in Agent Runs

**Traceability:** Plan 7 telemetry, Plan 9 loops and skills, Plan 11 input-signal prerequisite

**Files:**
- Modify: `src/optimus/agent/runner.py`
- Modify: `src/optimus/telemetry/events.py`
- Modify: `tests/unit/agent/test_runner.py`
- Modify: `tests/unit/telemetry/test_events.py`
- Create: `tests/integration/agent/test_loop_skill_agent_flow.py`

**Interfaces:**
- Consumes: `SkillRegistry`, `SkillInvocationPolicy`, `GoalLoopController`, `ProgressLedger`.
- Produces: `TelemetryEvent.agent_run(...)` and `AgentRunResult.stop_reason`.

- [ ] **Step 1: Write failing telemetry and integration tests**

Add to `tests/unit/telemetry/test_events.py`:

```python
def test_agent_run_event_serializes_status_and_tool_trajectory():
    event = TelemetryEvent.agent_run(
        run_id="run-1",
        session_id=None,
        request_id="run-1:agent-run",
        occurred_at=datetime(2026, 7, 7, tzinfo=UTC),
        status="completed",
        final_state="COMPLETED",
        tool_names=("file_reader", "write_file"),
        total_cost_usd=Decimal("0.012"),
        mutation_count=1,
        stop_reason=None,
    )

    encoded = event.to_json_dict()

    assert encoded["kind"] == "agent_run"
    assert encoded["tool_names"] == ["file_reader", "write_file"]
    assert encoded["total_cost_usd"] == "0.012"
```

Create `tests/integration/agent/test_loop_skill_agent_flow.py` with:

- A trusted skill fixture matching a pytest-related task.
- A fake runner/evaluator that stops with `LoopStopReason.COMPLETED`.
- An assertion that selected skill telemetry and final `AgentRunResult.stop_reason == "COMPLETED"` are present.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/telemetry/test_events.py::test_agent_run_event_serializes_status_and_tool_trajectory tests/integration/agent/test_loop_skill_agent_flow.py -v
```

Expected: FAIL because agent-run telemetry and loop/skill runner wiring do not exist.

- [ ] **Step 3: Implement telemetry and runner wiring**

Add `TelemetryEventKind.AGENT_RUN = "agent_run"` and a `TelemetryEvent.agent_run(...)` factory.

Update `AgentRunner` to:

- Load `SkillRegistry.from_paths(tuple(request.skill_paths))` when skill paths are supplied.
- Record matched skill names in telemetry fields only; do not add a `skill_selection` pseudo-tool to `AgentRunResult.tool_calls` or golden `actual_tools`.
- Use `GoalLoopController` only when the request includes a measurable completion condition. For this first slice, derive a loop only for tests that pass the optional `AgentRunRequest.completion_condition` defined in Task 1.
- Emit one `agent_run` telemetry event at the final boundary.

- [ ] **Step 4: Run loop/skill/telemetry tests**

Run:

```bash
pytest tests/unit/agent tests/unit/loops tests/unit/skills tests/unit/telemetry/test_events.py tests/integration/agent tests/integration/loops tests/integration/skills -v
```

Expected: PASS.

---

## Task 7: README, Release Visibility, and Verification

**Traceability:** Phase 1 release sign-off and Plan 11 readiness

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`

**Interfaces:**
- Updates roadmap sequence to include Plan 9.5 before Plan 11.
- Documents that Plan 11 starts after task-level Agent run and real golden harness are stable.

- [ ] **Step 1: Update README**

Add a concise section after Plan 9 documentation:

```markdown
### Phase 1 Agent Orchestration

Plan 9.5 composes the Phase 1 primitives into a task-level coding agent. The
agent runner accepts a typed task request, plans through the Optimus Gateway,
pauses for approval before Agent-mode mutation, executes side-effecting tools
only through guardrails, validates the result, and records the observed tool
trajectory for golden-task evaluation.

Plan 11 context-window optimization builds on this runner. It does not create
the task lifecycle, approval boundary, tool adapters, or golden harness.
```

- [ ] **Step 2: Update roadmap**

In `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, insert:

```markdown
## Plan 9.5: Agent Orchestration and End-to-End Coding Workflow

**Plan file:** `docs/superpowers/plans/2026-07-07-agent-orchestration-end-to-end-coding-workflow.md`

**User story:** As an operator, I can give the local Optimus Agent a normal coding task and receive a planned, approved, guarded, validated, and cost-attributed outcome.

**Expected deliverables:**
- `AgentRunner`, `AgentRunRequest`, `AgentRunResult`, guarded tool adapters, `optimus.agent.run`, and `AgentGoldenTaskHarness`.
- Tests proving Plan/Chat advisory-only behavior, Agent-mode approval before mutation, guarded tool use, bounded-loop stop integration, skill selection, real golden harness execution, and one-key release evidence.

**Status:** Approved for implementation. This is the bridge between Plan 9 primitives and Plan 11 intelligence.
```

Update the recommended sequence so Plan 9.5 appears between Plan 9 and Plan 11.

- [ ] **Step 3: Run verification**

Run:

```bash
pytest tests/unit/agent tests/integration/agent tests/unit/acp tests/integration/acp tests/unit/golden tests/unit/release tests/unit/loops tests/unit/skills tests/integration/loops tests/integration/skills -v
pytest --cov=optimus --cov-branch --cov-report=term-missing
git diff --check
```

Expected:

- All listed tests PASS.
- Aggregate production-code coverage remains >= 80%.
- `git diff --check` reports no whitespace errors.

- [ ] **Step 4: Release-gate evidence**

Run the Plan 9.5 real-agent golden subset with only Optimus credentials available locally:

```bash
python tools/run_phase1_release_gate.py --agent-harness --task-id explain-small-function --task-id docstring-single-function --task-id plan-then-approve-agent --task-id budget-exhausted
```

Expected:

- PASS only if those four fixture results are produced by the real `AgentGoldenTaskHarness` or staging-equivalent Optimus-only task runs.
- The remaining golden fixtures may still be consumed from JSON/staging evidence until their required tools exist; do not require the Plan 9.5 runner to fake unsupported tool surfaces.
- If staging Gateway E2E is not available, report it as release evidence not run; do not claim Sprint 1 sign-off.

## Mandatory Completion Plan

Tasks 1-7 delivered orchestration primitives, but they do not satisfy the operator user story by themselves. The mandatory completion plan is:

`docs/superpowers/plans/2026-07-07-plan-9-5-working-acp-agent-completion.md`

Plan 9.5 is not complete until that plan delivers:

- A spawnable Agent Client Protocol stdio process for IDE integration through `python -m optimus.acp` and `optimus-agent`.
- Agent Client Protocol conformance for newline-delimited JSON-RPC: client-to-agent requests `initialize`, `session/new`, and `session/prompt`; client-to-agent notification `session/cancel`; plus agent-to-client `session/update` and `session/request_permission`.
- Production `AcpStreamServer` wiring with real `GatewayClient`, `AgentRunner`, Redis-backed agent state, configured `workspace_root`, and shared `PreToolGuard`.
- Framed `optimus.agent.run` integration tests through `AcpStreamServer.handle_one()`, including the two-call approval flow.
- Redis-backed persisted plan replay so approved Agent-mode execution uses the exact stored plan text instead of re-planning through a live Gateway.
- Versioned directive prompt contract, typed unparseable-plan failure, and checked-in redacted smoke transcript for real Gateway evidence.
- Operator-friendly startup messages for missing Optimus credentials or missing, unsafe, or unreachable Redis configuration.
- Guarded pytest execution in the runnable coding-agent path.
- README launch instructions and smoke checks that prove a running agent deliverable, not only importable code.

The completion plan contains the only explicit exceptions for the working-agent deliverable. Anything not listed as an exception there is part of the required Plan 9.5 completion scope.

## Self-Review

- Spec coverage: this plan closes the task-level Agent gap between Plan 9 primitives and Plan 11 context intelligence.
- Scope control: Plan 11 context optimization remains out of scope.
- One-key model: all model calls route through `GatewayClient`; local provider keys remain forbidden.
- Guardrail boundary: every side effect routes through existing guarded tool wrappers, configured workspace containment, approval state, and plan-hash verification.
- Golden evidence: this plan replaces JSON-only result consumption with a real agent harness path for `explain-small-function`, `docstring-single-function`, `plan-then-approve-agent`, and `budget-exhausted`, while preserving JSON/staging evidence for unsupported fixtures.
- Cost accounting: per-run budget enforcement and summed golden scenario cost are intentionally different gates.
- Review fixes: absolute workspace validation checks before resolve; lower-case ACP modes normalize; approved mutations require `approval_id` plus `plan_hash`; Plan/Chat reads and read-before-write are explicit; budget exhaustion terminates before mutation; terminated golden plan runs short-circuit without approval construction; release CLI flags are included in implementation scope; two-call scenario cost sums planning plus execution; runner guard injection preserves dispatcher audit sinks.
- Placeholder scan: no unresolved placeholders remain in this draft.
- Planning gap acknowledged and converted into the mandatory completion plan at `docs/superpowers/plans/2026-07-07-plan-9-5-working-acp-agent-completion.md`.
