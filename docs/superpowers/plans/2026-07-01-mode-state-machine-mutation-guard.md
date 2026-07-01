# Mode, State Machine, and Mutation Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 1 mode boundary, deterministic lifecycle state machine, AwaitingApproval gate, and mutation primitive that prevents repository or shell mutation outside approved Agent mode.

**Architecture:** Add a focused `optimus.runtime` package that owns execution modes, generation-scope classification, lifecycle states, transition validation, approval records, and `MutationGuard`. Add a small `optimus.tools` mutation-wrapper package so file writes, shell execution, and shadow-apply paths must call `assert_mutation_allowed()` before any I/O. Integrate the runtime exception with the existing ACP JSON-RPC error helpers so forbidden mutations return code `-32002`.

**Tech Stack:** Python >=3.14, pytest, pytest-asyncio, coverage.py, pytest-cov, stdlib `dataclasses`, stdlib `enum`, stdlib `pathlib`, stdlib `subprocess`.

---

## Source Anchors

- `docs/Optimus-Cost-Agent-Architecture-v2.15.pdf`, section 7: Plan/Chat is advisory-only; Agent mode is write-authorized only within approved workspace boundaries and after gates.
- `docs/Optimus-Cost-Agent-LLD-v2.38.pdf`, section 4A: lifecycle states, valid/invalid transition table, mode-specific permission matrix, and `MutationGuard` as the mutation-boundary validator.
- `docs/Optimus-Cost-Agent-Test-Strategy-v1.4.pdf`, section 5: `assert_mutation_allowed()` tests, invalid transition tests, AwaitingApproval bypass tests, and mode-boundary integration tests.
- `docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.0.pdf`, sections 0, 10, and 11: guardrail inventory, representative contract shapes, and traceability requirement that every control has executable tests.
- `docs/superpowers/plans/2026-07-01-core-runtime-acp-transport.md`: Plan 1 package, ACP, JSON-RPC, dispatcher, and stream-handler foundation.
- `AGENTS.md`: TDD required, safety-critical coverage must not regress, and mutation paths must pass through `MutationGuard` / `assert_mutation_allowed()` and AwaitingApproval.

## Scope

### In Scope

- `ExecutionMode` with `PLAN`, `CHAT`, and `AGENT`.
- `GenerationScope` and deterministic scope classification.
- Lifecycle states from LLD section 4A: `IDLE`, `PLANNING`, `PLAN_READY`, `CHAT_ONLY`, `AWAITING_APPROVAL`, `EXECUTING`, `TOOL_CALLING`, `VALIDATING`, `FAILED`, `COMPLETED`, and `TERMINATED`.
- Transition validator with fail-closed `-32002` rejection for invalid or bypass transitions.
- `AwaitingApproval` record with approval, denial, and timeout behavior.
- `MutationGuard`, `MutationKind`, `MutationForbidden`, and top-level `assert_mutation_allowed()`.
- Mutation tool wrappers for `write_file`, `shell_exec`, and `shadow_apply` that invoke the guard before side effects.
- ACP/JSON-RPC mapping for `MutationForbidden` to `-32002`.
- Unit and integration tests proving Plan/Chat cannot mutate, Agent mode must pass through approval, invalid transitions fail closed, and mutation wrappers check the primitive before I/O.

### Out of Scope

- Gateway client, Optimus auth, provider key rejection, or gateway usage parsing.
- Full `PermissionPolicy`, `PreToolGuard`, shell command sanitizer, MCP trust, prompt-injection scanning, and CI parity. Those belong to later roadmap plans.
- Real patch application semantics beyond a guardable `shadow_apply()` boundary.
- Workspace path canonicalization and cross-drive/traversal rejection. The approved `write_file()` wrapper in this plan is deliberately mode/approval-only until the later PreToolGuard/path-safety plan adds workspace-bound checks.
- Composite fitness-gate retry integration. This plan covers `FAILED -> PLANNING` retry state changes, but the Test Strategy's "fails twice, passes third, final patch applied" scenario depends on the later composite gate runner.
- Full golden task suite and one-key release gate. This plan creates the runtime primitive those gates will exercise later.
- Redis telemetry persistence and mutation-call telemetry counters. This plan proves no side effect occurs; durable telemetry lands in a later observability slice.

## File Structure

- Modify: `src/optimus/acp/errors.py` - add JSON-RPC code `MUTATION_FORBIDDEN = -32002`.
- Modify: `src/optimus/acp/dispatcher.py` - map runtime methods and mutation exceptions to JSON-RPC responses.
- Create: `src/optimus/runtime/__init__.py` - public runtime exports.
- Create: `src/optimus/runtime/modes.py` - execution mode and generation-scope classification.
- Create: `src/optimus/runtime/state.py` - lifecycle states, approval record, runtime context, transition validator.
- Create: `src/optimus/runtime/mutation.py` - `MutationGuard`, exception type, and top-level primitive.
- Create: `src/optimus/tools/__init__.py` - mutation tool exports.
- Create: `src/optimus/tools/mutation_tools.py` - guard-first file, shell, and shadow-apply wrappers.
- Create: `tests/unit/runtime/test_modes.py` - mode and generation-scope tests.
- Create: `tests/unit/runtime/test_state_machine.py` - valid/invalid transition and approval tests.
- Create: `tests/unit/runtime/test_mutation_guard.py` - `assert_mutation_allowed()` tests.
- Create: `tests/unit/tools/test_mutation_tools.py` - before-I/O guard tests.
- Modify: `tests/unit/acp/test_dispatcher.py` - JSON-RPC `-32002` mapping tests.
- Create: `tests/integration/runtime/test_mode_boundary.py` - end-to-end no-mutation boundary tests with fakes.

## Human Agile Sizing

This plan is sized for roughly 2 weeks of human development effort:

- Days 1-2: modes and generation-scope classification.
- Days 3-5: lifecycle state model and transition validation.
- Days 6-7: approval records and timeout/denial fallback.
- Days 8-9: mutation guard and tool wrappers.
- Days 10-11: ACP error mapping and integration tests.
- Days 12-13: coverage, refactor, docs, and sign-off checks.

## Task 1: Execution Modes and Generation Scope

**Files:**
- Create: `src/optimus/runtime/__init__.py`
- Create: `src/optimus/runtime/modes.py`
- Test: `tests/unit/runtime/test_modes.py`

- [ ] **Step 1: Write failing mode and classification tests**

Create `tests/unit/runtime/test_modes.py`:

```python
from optimus.runtime.modes import (
    ExecutionMode,
    GenerationScope,
    classify_generation_scope,
)


def test_execution_mode_values_match_public_contract():
    assert ExecutionMode.PLAN.value == "PLAN"
    assert ExecutionMode.CHAT.value == "CHAT"
    assert ExecutionMode.AGENT.value == "AGENT"


def test_inline_snippet_scope_for_short_advisory_text():
    scope = classify_generation_scope(
        generated_line_count=14,
        modified_paths=[],
        created_paths=[],
        deleted_paths=[],
        touches_core_package=False,
    )

    assert scope is GenerationScope.INLINE_SNIPPET


def test_patch_proposal_scope_for_existing_file_patch_text():
    scope = classify_generation_scope(
        generated_line_count=30,
        modified_paths=["src/optimus/acp/dispatcher.py"],
        created_paths=[],
        deleted_paths=[],
        touches_core_package=False,
    )

    assert scope is GenerationScope.PATCH_PROPOSAL


def test_file_mutation_scope_for_single_file_create_or_delete():
    create_scope = classify_generation_scope(
        generated_line_count=5,
        modified_paths=[],
        created_paths=["src/optimus/runtime/state.py"],
        deleted_paths=[],
        touches_core_package=False,
    )
    delete_scope = classify_generation_scope(
        generated_line_count=5,
        modified_paths=[],
        created_paths=[],
        deleted_paths=["src/optimus/runtime/state.py"],
        touches_core_package=False,
    )

    assert create_scope is GenerationScope.FILE_MUTATION
    assert delete_scope is GenerationScope.FILE_MUTATION


def test_multi_file_changeset_scope_for_core_or_multiple_roots():
    core_scope = classify_generation_scope(
        generated_line_count=5,
        modified_paths=["src/optimus/runtime/state.py"],
        created_paths=[],
        deleted_paths=[],
        touches_core_package=True,
    )
    roots_scope = classify_generation_scope(
        generated_line_count=5,
        modified_paths=["src/optimus/runtime/state.py", "tests/unit/runtime/test_state.py"],
        created_paths=[],
        deleted_paths=[],
        touches_core_package=False,
    )

    assert core_scope is GenerationScope.MULTI_FILE_CHANGESET
    assert roots_scope is GenerationScope.MULTI_FILE_CHANGESET
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
pytest tests/unit/runtime/test_modes.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'optimus.runtime'`.

- [ ] **Step 3: Implement modes and scope classification**

Create `src/optimus/runtime/__init__.py`:

```python
"""Runtime governance primitives for Optimus Cost Agent."""
```

Create `src/optimus/runtime/modes.py`:

```python
from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath


class ExecutionMode(StrEnum):
    PLAN = "PLAN"
    CHAT = "CHAT"
    AGENT = "AGENT"


class GenerationScope(StrEnum):
    INLINE_SNIPPET = "INLINE_SNIPPET"
    PATCH_PROPOSAL = "PATCH_PROPOSAL"
    FILE_MUTATION = "FILE_MUTATION"
    MULTI_FILE_CHANGESET = "MULTI_FILE_CHANGESET"


def classify_generation_scope(
    *,
    generated_line_count: int,
    modified_paths: list[str],
    created_paths: list[str],
    deleted_paths: list[str],
    touches_core_package: bool,
) -> GenerationScope:
    # Scope names are specified by the architecture. The line-count and root
    # heuristics are conservative Phase 1 implementation decisions.
    changed_paths = [*modified_paths, *created_paths, *deleted_paths]
    if touches_core_package or _distinct_roots(changed_paths) > 1:
        return GenerationScope.MULTI_FILE_CHANGESET
    if created_paths or deleted_paths:
        return GenerationScope.FILE_MUTATION
    if modified_paths:
        return GenerationScope.PATCH_PROPOSAL
    if generated_line_count < 15:
        return GenerationScope.INLINE_SNIPPET
    return GenerationScope.PATCH_PROPOSAL


def _distinct_roots(paths: list[str]) -> int:
    roots: set[str] = set()
    for path in paths:
        parts = PurePosixPath(path.replace("\\", "/")).parts
        if parts:
            roots.add(parts[0])
    return len(roots)
```

- [ ] **Step 4: Export public runtime types**

Update `src/optimus/runtime/__init__.py`:

```python
"""Runtime governance primitives for Optimus Cost Agent."""

from optimus.runtime.modes import (
    ExecutionMode,
    GenerationScope,
    classify_generation_scope,
)

__all__ = [
    "ExecutionMode",
    "GenerationScope",
    "classify_generation_scope",
]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run:

```bash
pytest tests/unit/runtime/test_modes.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/optimus/runtime/__init__.py src/optimus/runtime/modes.py tests/unit/runtime/test_modes.py
git commit -m "Add execution mode and generation scope primitives."
```

## Task 2: Lifecycle State Machine

**Files:**
- Create: `src/optimus/runtime/state.py`
- Modify: `src/optimus/runtime/__init__.py`
- Test: `tests/unit/runtime/test_state_machine.py`

- [ ] **Step 1: Write failing transition tests**

Create `tests/unit/runtime/test_state_machine.py`:

```python
import pytest

from optimus.runtime.modes import ExecutionMode
from optimus.runtime.mutation import MutationForbidden
from optimus.runtime.state import (
    AgentState,
    RuntimeContext,
    StateTransition,
    TransitionValidator,
)


def test_idle_to_planning_valid_on_user_request():
    context = RuntimeContext(execution_mode=ExecutionMode.PLAN)

    updated = TransitionValidator().transition(
        context,
        StateTransition(target=AgentState.PLANNING, reason="user request"),
    )

    assert updated.state is AgentState.PLANNING


def test_plan_ready_to_chat_only_valid_for_plan_mode():
    context = RuntimeContext(
        execution_mode=ExecutionMode.PLAN,
        state=AgentState.PLAN_READY,
    )

    updated = TransitionValidator().transition(
        context,
        StateTransition(target=AgentState.CHAT_ONLY, reason="advisory response"),
    )

    assert updated.state is AgentState.CHAT_ONLY


def test_plan_ready_direct_to_executing_rejected_with_code_32002():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.PLAN_READY,
    )

    with pytest.raises(MutationForbidden) as exc_info:
        TransitionValidator().transition(
            context,
            StateTransition(target=AgentState.EXECUTING, reason="bypass approval"),
        )

    assert exc_info.value.code == -32002
    assert "must pass through AwaitingApproval" in str(exc_info.value)


def test_any_bypass_to_executing_rejected():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.IDLE,
    )

    with pytest.raises(MutationForbidden, match="No path bypasses AwaitingApproval"):
        TransitionValidator().transition(
            context,
            StateTransition(target=AgentState.EXECUTING, reason="bypass"),
        )


def test_failed_to_planning_increments_retry_count():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.FAILED,
        retry_count=1,
        failure_context="gate failed",
    )

    updated = TransitionValidator().transition(
        context,
        StateTransition(target=AgentState.PLANNING, reason="retry"),
    )

    assert updated.state is AgentState.PLANNING
    assert updated.retry_count == 2
    assert updated.failure_context == "gate failed"


def test_failed_to_terminated_after_max_retries():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.FAILED,
        retry_count=3,
        max_retries=3,
    )

    updated = TransitionValidator().transition(
        context,
        StateTransition(target=AgentState.TERMINATED, reason="retry budget exhausted"),
    )

    assert updated.state is AgentState.TERMINATED
    assert updated.user_escalation is True


def test_approved_execution_enters_tool_calling_then_validating():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.EXECUTING,
        approval_granted=True,
        user_approval_id="approval-123",
    )
    validator = TransitionValidator()

    tool_calling = validator.transition(
        context,
        StateTransition(target=AgentState.TOOL_CALLING, reason="authorized tool call"),
    )
    validating = validator.transition(
        tool_calling,
        StateTransition(target=AgentState.VALIDATING, reason="tool response received"),
    )

    assert tool_calling.state is AgentState.TOOL_CALLING
    assert validating.state is AgentState.VALIDATING


def test_validation_pass_returns_to_executing_before_completion():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.VALIDATING,
        approval_granted=True,
        user_approval_id="approval-123",
    )
    validator = TransitionValidator()

    executing = validator.transition(
        context,
        StateTransition(target=AgentState.EXECUTING, reason="all gates passed"),
    )
    completed = validator.transition(
        executing,
        StateTransition(target=AgentState.COMPLETED, reason="planned work done"),
    )

    assert executing.state is AgentState.EXECUTING
    assert completed.state is AgentState.COMPLETED


def test_validation_failure_enters_failed_state():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.VALIDATING,
        approval_granted=True,
        user_approval_id="approval-123",
    )

    updated = TransitionValidator().transition(
        context,
        StateTransition(target=AgentState.FAILED, reason="fitness gate failed"),
    )

    assert updated.state is AgentState.FAILED


def test_validation_pass_requires_existing_approval():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.VALIDATING,
        approval_granted=False,
        user_approval_id=None,
    )

    with pytest.raises(MutationForbidden, match="approval required before Executing"):
        TransitionValidator().transition(
            context,
            StateTransition(target=AgentState.EXECUTING, reason="all gates passed"),
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
pytest tests/unit/runtime/test_state_machine.py -v
```

Expected: FAIL with missing `optimus.runtime.state` and `optimus.runtime.mutation`.

- [ ] **Step 3: Add the mutation exception used by the validator**

Create `src/optimus/runtime/mutation.py` with the exception only:

```python
from __future__ import annotations

from dataclasses import dataclass

MUTATION_FORBIDDEN_CODE = -32002


@dataclass(frozen=True)
class MutationForbidden(Exception):
    message: str
    code: int = MUTATION_FORBIDDEN_CODE

    def __str__(self) -> str:
        return self.message
```

- [ ] **Step 4: Implement lifecycle state and transition validation**

Create `src/optimus/runtime/state.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from optimus.runtime.modes import ExecutionMode
from optimus.runtime.mutation import MutationForbidden


class AgentState(StrEnum):
    IDLE = "IDLE"
    PLANNING = "PLANNING"
    PLAN_READY = "PLAN_READY"
    CHAT_ONLY = "CHAT_ONLY"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    TOOL_CALLING = "TOOL_CALLING"
    VALIDATING = "VALIDATING"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    TERMINATED = "TERMINATED"


@dataclass(frozen=True)
class RuntimeContext:
    execution_mode: ExecutionMode
    state: AgentState = AgentState.IDLE
    approval_granted: bool = False
    user_approval_id: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    failure_context: str | None = None
    user_escalation: bool = False


@dataclass(frozen=True)
class StateTransition:
    target: AgentState
    reason: str


class TransitionValidator:
    def transition(
        self,
        context: RuntimeContext,
        transition: StateTransition,
    ) -> RuntimeContext:
        source = context.state
        target = transition.target

        if target is AgentState.EXECUTING and source not in {
            AgentState.AWAITING_APPROVAL,
            AgentState.VALIDATING,
        }:
            if source is AgentState.PLAN_READY:
                raise MutationForbidden("PlanReady -> Executing rejected: must pass through AwaitingApproval")
            raise MutationForbidden("No path bypasses AwaitingApproval")

        if source is AgentState.IDLE and target is AgentState.PLANNING:
            return replace(context, state=target)
        if source is AgentState.PLANNING and target is AgentState.PLAN_READY:
            return replace(context, state=target)
        if source is AgentState.PLAN_READY and target is AgentState.CHAT_ONLY:
            if context.execution_mode is ExecutionMode.AGENT:
                raise MutationForbidden("Agent mode cannot fall through to ChatOnly without denial or timeout")
            return replace(context, state=target)
        if source is AgentState.PLAN_READY and target is AgentState.AWAITING_APPROVAL:
            if context.execution_mode is not ExecutionMode.AGENT:
                raise MutationForbidden("AwaitingApproval is valid only in Agent mode")
            return replace(context, state=target)
        if source is AgentState.AWAITING_APPROVAL and target is AgentState.EXECUTING:
            if not context.approval_granted:
                raise MutationForbidden("approval required before Executing")
            return replace(context, state=target)
        if source is AgentState.AWAITING_APPROVAL and target is AgentState.CHAT_ONLY:
            return replace(context, state=target, approval_granted=False)
        if source is AgentState.EXECUTING and target in {AgentState.TOOL_CALLING, AgentState.COMPLETED}:
            return replace(context, state=target)
        if source is AgentState.TOOL_CALLING and target is AgentState.VALIDATING:
            return replace(context, state=target)
        if source is AgentState.VALIDATING and target in {AgentState.EXECUTING, AgentState.FAILED}:
            if target is AgentState.EXECUTING and not context.approval_granted:
                raise MutationForbidden("approval required before Executing")
            return replace(context, state=target)
        if source is AgentState.FAILED and target is AgentState.PLANNING:
            if context.retry_count >= context.max_retries:
                raise MutationForbidden("retry budget exhausted")
            return replace(context, state=target, retry_count=context.retry_count + 1)
        if source is AgentState.FAILED and target is AgentState.TERMINATED:
            return replace(context, state=target, user_escalation=True)

        raise MutationForbidden(f"invalid transition: {source.value} -> {target.value}")
```

- [ ] **Step 5: Export lifecycle types**

Update `src/optimus/runtime/__init__.py`:

```python
"""Runtime governance primitives for Optimus Cost Agent."""

from optimus.runtime.modes import (
    ExecutionMode,
    GenerationScope,
    classify_generation_scope,
)
from optimus.runtime.mutation import MUTATION_FORBIDDEN_CODE, MutationForbidden
from optimus.runtime.state import (
    AgentState,
    RuntimeContext,
    StateTransition,
    TransitionValidator,
)

__all__ = [
    "AgentState",
    "ExecutionMode",
    "GenerationScope",
    "MUTATION_FORBIDDEN_CODE",
    "MutationForbidden",
    "RuntimeContext",
    "StateTransition",
    "TransitionValidator",
    "classify_generation_scope",
]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run:

```bash
pytest tests/unit/runtime/test_state_machine.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/optimus/runtime tests/unit/runtime/test_state_machine.py
git commit -m "Add lifecycle state transition validation."
```

## Task 3: AwaitingApproval Record, Denial, and Timeout

**Files:**
- Modify: `src/optimus/runtime/state.py`
- Test: `tests/unit/runtime/test_state_machine.py`

- [ ] **Step 1: Add failing AwaitingApproval tests**

Update the existing import block in `tests/unit/runtime/test_state_machine.py` to include `AwaitingApproval`:

```python
from optimus.runtime.state import (
    AgentState,
    AwaitingApproval,
    RuntimeContext,
    StateTransition,
    TransitionValidator,
)
```

Append these tests to `tests/unit/runtime/test_state_machine.py`:

```python

def test_awaiting_approval_grants_context_with_approval_id():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.AWAITING_APPROVAL,
    )
    approval = AwaitingApproval(approval_id="approval-123", requested_at_ms=1000, timeout_ms=5000)

    updated = approval.grant(context)

    assert updated.approval_granted is True
    assert updated.user_approval_id == "approval-123"


def test_awaiting_approval_denial_falls_back_to_chat_only():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.AWAITING_APPROVAL,
    )
    approval = AwaitingApproval(approval_id="approval-123", requested_at_ms=1000, timeout_ms=5000)

    updated = approval.deny(context)

    assert updated.state is AgentState.CHAT_ONLY
    assert updated.approval_granted is False


def test_awaiting_approval_timeout_falls_back_to_chat_only():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.AWAITING_APPROVAL,
    )
    approval = AwaitingApproval(approval_id="approval-123", requested_at_ms=1000, timeout_ms=5000)

    updated = approval.timeout_if_expired(context, now_ms=6001)

    assert updated.state is AgentState.CHAT_ONLY
    assert updated.approval_granted is False


def test_awaiting_approval_before_timeout_keeps_context_unchanged():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.AWAITING_APPROVAL,
    )
    approval = AwaitingApproval(approval_id="approval-123", requested_at_ms=1000, timeout_ms=5000)

    updated = approval.timeout_if_expired(context, now_ms=5999)

    assert updated == context
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
pytest tests/unit/runtime/test_state_machine.py -v
```

Expected: FAIL with missing `AwaitingApproval`.

- [ ] **Step 3: Implement `AwaitingApproval`**

Add to `src/optimus/runtime/state.py` below `StateTransition`:

```python
@dataclass(frozen=True)
class AwaitingApproval:
    approval_id: str
    requested_at_ms: int
    timeout_ms: int

    def grant(self, context: RuntimeContext) -> RuntimeContext:
        self._require_awaiting(context)
        return replace(
            context,
            approval_granted=True,
            user_approval_id=self.approval_id,
        )

    def deny(self, context: RuntimeContext) -> RuntimeContext:
        self._require_awaiting(context)
        # Denial and timeout are the sanctioned Agent-mode fallback to advisory output.
        return replace(
            context,
            state=AgentState.CHAT_ONLY,
            approval_granted=False,
            user_approval_id=self.approval_id,
        )

    def timeout_if_expired(self, context: RuntimeContext, *, now_ms: int) -> RuntimeContext:
        self._require_awaiting(context)
        if now_ms - self.requested_at_ms <= self.timeout_ms:
            return context
        # Timeout follows the same sanctioned fallback path as explicit denial.
        return replace(
            context,
            state=AgentState.CHAT_ONLY,
            approval_granted=False,
            user_approval_id=self.approval_id,
        )

    def _require_awaiting(self, context: RuntimeContext) -> None:
        if context.state is not AgentState.AWAITING_APPROVAL:
            raise MutationForbidden("approval record can be used only in AwaitingApproval state")
```

- [ ] **Step 4: Export `AwaitingApproval`**

Update `src/optimus/runtime/__init__.py` imports and `__all__`:

```python
from optimus.runtime.state import (
    AgentState,
    AwaitingApproval,
    RuntimeContext,
    StateTransition,
    TransitionValidator,
)
```

Add `"AwaitingApproval"` to `__all__`.

- [ ] **Step 5: Run the tests to verify they pass**

Run:

```bash
pytest tests/unit/runtime/test_state_machine.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/optimus/runtime tests/unit/runtime/test_state_machine.py
git commit -m "Add AwaitingApproval approval and timeout handling."
```

## Task 4: MutationGuard and `assert_mutation_allowed()`

**Files:**
- Modify: `src/optimus/runtime/mutation.py`
- Modify: `src/optimus/runtime/__init__.py`
- Test: `tests/unit/runtime/test_mutation_guard.py`

- [ ] **Step 1: Write failing mutation guard tests**

Create `tests/unit/runtime/test_mutation_guard.py`:

```python
import pytest

from optimus.runtime.modes import ExecutionMode
from optimus.runtime.mutation import (
    MutationForbidden,
    MutationGuard,
    MutationKind,
    assert_mutation_allowed,
)
from optimus.runtime.state import AgentState, RuntimeContext


def test_plan_mode_mutation_forbidden_with_required_message():
    context = RuntimeContext(execution_mode=ExecutionMode.PLAN, state=AgentState.CHAT_ONLY)

    with pytest.raises(MutationForbidden) as exc_info:
        assert_mutation_allowed(context, MutationKind.WRITE_FILE)

    assert exc_info.value.code == -32002
    assert str(exc_info.value) == "mutation forbidden in Plan/Chat mode"


def test_chat_mode_mutation_forbidden_with_required_message():
    context = RuntimeContext(execution_mode=ExecutionMode.CHAT, state=AgentState.CHAT_ONLY)

    with pytest.raises(MutationForbidden, match="mutation forbidden in Plan/Chat mode"):
        assert_mutation_allowed(context, MutationKind.SHELL_EXEC)


def test_agent_mode_before_approval_forbidden():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.AWAITING_APPROVAL,
        approval_granted=False,
    )

    with pytest.raises(MutationForbidden, match="approval required before mutation"):
        assert_mutation_allowed(context, MutationKind.WRITE_FILE)


def test_agent_mode_after_approval_allowed_in_executing_state():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.EXECUTING,
        approval_granted=True,
        user_approval_id="approval-123",
    )

    assert assert_mutation_allowed(context, MutationKind.WRITE_FILE) is None


def test_agent_mode_mutation_rejected_from_terminal_state():
    context = RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.TERMINATED,
        approval_granted=True,
        user_approval_id="approval-123",
    )

    with pytest.raises(MutationForbidden, match="mutation not allowed from state TERMINATED"):
        MutationGuard().assert_allowed(context, MutationKind.SHADOW_APPLY)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
pytest tests/unit/runtime/test_mutation_guard.py -v
```

Expected: FAIL with missing `MutationGuard`, `MutationKind`, or `assert_mutation_allowed`.

- [ ] **Step 3: Implement the guard primitive**

Replace `src/optimus/runtime/mutation.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from optimus.runtime.modes import ExecutionMode

if TYPE_CHECKING:
    from optimus.runtime.state import RuntimeContext

MUTATION_FORBIDDEN_CODE = -32002


class MutationKind(StrEnum):
    WRITE_FILE = "write_file"
    SHELL_EXEC = "shell_exec"
    SHADOW_APPLY = "shadow_apply"


@dataclass(frozen=True)
class MutationForbidden(Exception):
    message: str
    code: int = MUTATION_FORBIDDEN_CODE

    def __str__(self) -> str:
        return self.message


class MutationGuard:
    def assert_allowed(self, context: RuntimeContext, kind: MutationKind) -> None:
        from optimus.runtime.state import AgentState

        if context.execution_mode in {ExecutionMode.PLAN, ExecutionMode.CHAT}:
            raise MutationForbidden("mutation forbidden in Plan/Chat mode")
        if context.execution_mode is not ExecutionMode.AGENT:
            raise MutationForbidden(f"unknown execution mode: {context.execution_mode}")
        if not context.approval_granted or context.user_approval_id is None:
            raise MutationForbidden("approval required before mutation")
        if context.state not in {AgentState.EXECUTING, AgentState.TOOL_CALLING, AgentState.VALIDATING}:
            raise MutationForbidden(f"mutation not allowed from state {context.state.value}")


def assert_mutation_allowed(context: RuntimeContext, kind: MutationKind) -> None:
    MutationGuard().assert_allowed(context, kind)
```

- [ ] **Step 4: Export guard types**

Update `src/optimus/runtime/__init__.py` mutation imports:

```python
from optimus.runtime.mutation import (
    MUTATION_FORBIDDEN_CODE,
    MutationForbidden,
    MutationGuard,
    MutationKind,
    assert_mutation_allowed,
)
```

Add these names to `__all__`:

```python
"MutationGuard",
"MutationKind",
"assert_mutation_allowed",
```

- [ ] **Step 5: Run the tests to verify they pass**

Run:

```bash
pytest tests/unit/runtime/test_mutation_guard.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/optimus/runtime tests/unit/runtime/test_mutation_guard.py
git commit -m "Add mutation guard primitive."
```

## Task 5: Guard-First Mutation Tool Wrappers

**Files:**
- Create: `src/optimus/tools/__init__.py`
- Create: `src/optimus/tools/mutation_tools.py`
- Test: `tests/unit/tools/test_mutation_tools.py`

- [ ] **Step 1: Write failing before-I/O mutation wrapper tests**

Create `tests/unit/tools/test_mutation_tools.py`:

```python
import pytest

from optimus.runtime.modes import ExecutionMode
from optimus.runtime.mutation import MutationForbidden
from optimus.runtime.state import AgentState, RuntimeContext
from optimus.tools.mutation_tools import shell_exec, shadow_apply, write_file


class ProbeRunner:
    def __init__(self) -> None:
        self.called = False

    def __call__(self, command: list[str]) -> object:
        self.called = True
        return {"returncode": 0, "command": command}


class ProbeApplier:
    def __init__(self) -> None:
        self.called = False

    def __call__(self, patch_text: str) -> object:
        self.called = True
        return {"applied": True, "patch_text": patch_text}


def plan_context() -> RuntimeContext:
    return RuntimeContext(execution_mode=ExecutionMode.PLAN, state=AgentState.CHAT_ONLY)


def approved_agent_context() -> RuntimeContext:
    return RuntimeContext(
        execution_mode=ExecutionMode.AGENT,
        state=AgentState.EXECUTING,
        approval_granted=True,
        user_approval_id="approval-123",
    )


def test_write_file_checks_guard_before_writing(tmp_path):
    target = tmp_path / "blocked.txt"

    with pytest.raises(MutationForbidden):
        write_file(target, "blocked", context=plan_context())

    assert not target.exists()


def test_shell_exec_checks_guard_before_runner_call():
    runner = ProbeRunner()

    with pytest.raises(MutationForbidden):
        shell_exec(["pytest", "-q"], context=plan_context(), runner=runner)

    assert runner.called is False


def test_shadow_apply_checks_guard_before_applier_call():
    applier = ProbeApplier()

    with pytest.raises(MutationForbidden):
        shadow_apply("diff --git a/x b/x", context=plan_context(), applier=applier)

    assert applier.called is False


def test_write_file_allowed_after_agent_approval(tmp_path):
    target = tmp_path / "allowed.txt"

    write_file(target, "allowed", context=approved_agent_context())

    assert target.read_text(encoding="utf-8") == "allowed"


def test_shell_exec_allowed_after_agent_approval():
    runner = ProbeRunner()

    result = shell_exec(["pytest", "-q"], context=approved_agent_context(), runner=runner)

    assert runner.called is True
    assert result == {"returncode": 0, "command": ["pytest", "-q"]}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
pytest tests/unit/tools/test_mutation_tools.py -v
```

Expected: FAIL with missing `optimus.tools`.

- [ ] **Step 3: Implement mutation wrappers**

Create `src/optimus/tools/__init__.py`:

```python
"""Tool wrappers that enforce runtime guardrails before side effects."""
```

Create `src/optimus/tools/mutation_tools.py`:

```python
from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TypeVar

from optimus.runtime.mutation import MutationKind, assert_mutation_allowed
from optimus.runtime.state import RuntimeContext

ShellResult = TypeVar("ShellResult")
PatchResult = TypeVar("PatchResult")


def write_file(path: str | Path, content: str, *, context: RuntimeContext) -> None:
    assert_mutation_allowed(context, MutationKind.WRITE_FILE)
    Path(path).write_text(content, encoding="utf-8")


def shell_exec(
    command: Sequence[str],
    *,
    context: RuntimeContext,
    runner: Callable[[list[str]], ShellResult] | None = None,
) -> ShellResult | subprocess.CompletedProcess[str]:
    assert_mutation_allowed(context, MutationKind.SHELL_EXEC)
    if runner is not None:
        return runner(list(command))
    return subprocess.run(list(command), check=False, text=True, capture_output=True)


def shadow_apply(
    patch_text: str,
    *,
    context: RuntimeContext,
    applier: Callable[[str], PatchResult],
) -> PatchResult:
    assert_mutation_allowed(context, MutationKind.SHADOW_APPLY)
    return applier(patch_text)
```

- [ ] **Step 4: Export mutation wrappers**

Update `src/optimus/tools/__init__.py`:

```python
"""Tool wrappers that enforce runtime guardrails before side effects."""

from optimus.tools.mutation_tools import shell_exec, shadow_apply, write_file

__all__ = ["shell_exec", "shadow_apply", "write_file"]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run:

```bash
pytest tests/unit/tools/test_mutation_tools.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/optimus/tools tests/unit/tools/test_mutation_tools.py
git commit -m "Guard mutation tool wrappers before side effects."
```

## Task 6: ACP Error Code and Dispatcher Mapping

**Files:**
- Modify: `src/optimus/acp/errors.py`
- Modify: `src/optimus/acp/dispatcher.py`
- Test: `tests/unit/acp/test_dispatcher.py`

- [ ] **Step 1: Add failing dispatcher mapping tests**

Append to `tests/unit/acp/test_dispatcher.py`:

```python
from optimus.acp.errors import MUTATION_FORBIDDEN
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.state import AgentState, RuntimeContext


def test_dispatcher_maps_forbidden_runtime_mutation_to_32002():
    dispatcher = JsonRpcDispatcher(
        runtime_context=RuntimeContext(
            execution_mode=ExecutionMode.PLAN,
            state=AgentState.CHAT_ONLY,
        )
    )

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "write-1",
            "method": "optimus.mutation.writeFile",
            "params": {"path": "blocked.txt", "content": "blocked"},
        }
    )

    assert response["id"] == "write-1"
    assert response["error"]["code"] == MUTATION_FORBIDDEN
    assert response["error"]["message"] == "mutation forbidden in Plan/Chat mode"
```

- [ ] **Step 2: Run the dispatcher tests to verify they fail**

Run:

```bash
pytest tests/unit/acp/test_dispatcher.py -v
```

Expected: FAIL with missing `MUTATION_FORBIDDEN` or unexpected `runtime_context` argument.

- [ ] **Step 3: Add the JSON-RPC error code**

Update `src/optimus/acp/errors.py`:

```python
MUTATION_FORBIDDEN = -32002
```

Keep the existing `DUPLICATE_REQUEST_ID = -32001` constant unchanged.

- [ ] **Step 4: Map runtime mutation errors in the dispatcher**

Update `src/optimus/acp/dispatcher.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from optimus.acp.errors import (
    DUPLICATE_REQUEST_ID,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    MUTATION_FORBIDDEN,
    JsonRpcError,
    error_response,
    success_response,
)
from optimus.acp.request_ids import DuplicateRequestId, RequestIdTracker
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.mutation import MutationForbidden
from optimus.runtime.state import AgentState, RuntimeContext
from optimus.tools.mutation_tools import write_file


class JsonRpcDispatcher:
    def __init__(
        self,
        request_ids: RequestIdTracker | None = None,
        runtime_context: RuntimeContext | None = None,
    ) -> None:
        self._request_ids = request_ids or RequestIdTracker()
        self._runtime_context = runtime_context or RuntimeContext(
            execution_mode=ExecutionMode.PLAN,
            state=AgentState.CHAT_ONLY,
        )

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = request.get("id")
        try:
            self._request_ids.remember(request_id)
        except DuplicateRequestId:
            return error_response(
                request_id=request_id,
                error=JsonRpcError(
                    code=DUPLICATE_REQUEST_ID,
                    message="duplicate request id",
                    data={"id": request_id},
                ),
            )

        if request.get("jsonrpc") != "2.0" or "method" not in request:
            return error_response(
                request_id=request_id,
                error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
            )

        method = request["method"]
        try:
            if method == "optimus.ping":
                return success_response(request_id=request_id, result={"message": "pong"})
            if method == "optimus.mutation.writeFile":
                params = request.get("params")
                if not isinstance(params, dict) or not isinstance(params.get("path"), str):
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
                    )
                write_file(
                    Path(params["path"]),
                    str(params.get("content", "")),
                    context=self._runtime_context,
                )
                return success_response(request_id=request_id, result={"written": params["path"]})
        except MutationForbidden as exc:
            return error_response(
                request_id=request_id,
                error=JsonRpcError(code=MUTATION_FORBIDDEN, message=str(exc)),
            )

        return error_response(
            request_id=request_id,
            error=JsonRpcError(code=METHOD_NOT_FOUND, message=f"method not found: {method}"),
        )
```

- [ ] **Step 5: Run dispatcher and existing ACP tests**

Run:

```bash
pytest tests/unit/acp/test_dispatcher.py tests/integration/acp/test_server_stream.py -v
```

Expected: PASS, including existing `optimus.ping`, duplicate ID, and stream-handler tests.

- [ ] **Step 6: Commit**

```bash
git add src/optimus/acp/errors.py src/optimus/acp/dispatcher.py tests/unit/acp/test_dispatcher.py
git commit -m "Map mutation guard failures to JSON-RPC errors."
```

## Task 7: Mode Boundary Integration Tests

**Files:**
- Create: `tests/integration/runtime/test_mode_boundary.py`
- Verify: `src/optimus/runtime/*`, `src/optimus/tools/*`, `src/optimus/acp/*`

- [ ] **Step 1: Write integration tests for no mutation and approval path**

Create `tests/integration/runtime/test_mode_boundary.py`:

```python
import pytest

from optimus.runtime.modes import ExecutionMode
from optimus.runtime.mutation import MutationForbidden
from optimus.runtime.state import (
    AgentState,
    AwaitingApproval,
    RuntimeContext,
    StateTransition,
    TransitionValidator,
)
from optimus.tools.mutation_tools import write_file


def test_full_plan_chat_boundary_returns_plan_text_and_does_not_mutate(tmp_path):
    context = RuntimeContext(execution_mode=ExecutionMode.PLAN)
    validator = TransitionValidator()
    context = validator.transition(context, StateTransition(AgentState.PLANNING, "user request"))
    context = validator.transition(context, StateTransition(AgentState.PLAN_READY, "plan ready"))
    context = validator.transition(context, StateTransition(AgentState.CHAT_ONLY, "advisory response"))

    plan_text = "Plan text returned for review."
    target = tmp_path / "blocked.txt"
    with pytest.raises(MutationForbidden):
        write_file(target, "blocked", context=context)

    assert plan_text == "Plan text returned for review."
    assert target.exists() is False


def test_agent_mode_approval_denied_falls_back_to_chat_only_and_no_mutation(tmp_path):
    context = RuntimeContext(execution_mode=ExecutionMode.AGENT)
    validator = TransitionValidator()
    context = validator.transition(context, StateTransition(AgentState.PLANNING, "user request"))
    context = validator.transition(context, StateTransition(AgentState.PLAN_READY, "plan ready"))
    context = validator.transition(context, StateTransition(AgentState.AWAITING_APPROVAL, "needs approval"))
    context = AwaitingApproval("approval-1", requested_at_ms=1000, timeout_ms=5000).deny(context)

    target = tmp_path / "denied.txt"
    with pytest.raises(MutationForbidden):
        write_file(target, "blocked", context=context)

    assert context.state is AgentState.CHAT_ONLY
    assert target.exists() is False


def test_agent_mode_after_approval_can_write_file(tmp_path):
    context = RuntimeContext(execution_mode=ExecutionMode.AGENT)
    validator = TransitionValidator()
    context = validator.transition(context, StateTransition(AgentState.PLANNING, "user request"))
    context = validator.transition(context, StateTransition(AgentState.PLAN_READY, "plan ready"))
    context = validator.transition(context, StateTransition(AgentState.AWAITING_APPROVAL, "needs approval"))
    context = AwaitingApproval("approval-1", requested_at_ms=1000, timeout_ms=5000).grant(context)
    context = validator.transition(context, StateTransition(AgentState.EXECUTING, "approval granted"))

    target = tmp_path / "allowed.txt"
    write_file(target, "allowed", context=context)

    assert target.read_text(encoding="utf-8") == "allowed"
```

- [ ] **Step 2: Run integration tests to verify they pass**

Run:

```bash
pytest tests/integration/runtime/test_mode_boundary.py -v
```

Expected: PASS.

- [ ] **Step 3: Run focused runtime, tools, and ACP suites**

Run:

```bash
pytest tests/unit/runtime tests/unit/tools tests/unit/acp/test_dispatcher.py tests/integration/runtime tests/integration/acp -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/runtime/test_mode_boundary.py
git commit -m "Verify mode boundary integration behavior."
```

## Task 8: Coverage, Release-Gate Notes, and Working Tree Check

**Files:**
- Modify: `README.md`
- Verify: all files from Tasks 1-7

- [ ] **Step 1: Run narrow test suite with coverage**

Run:

```bash
pytest tests/unit/runtime tests/unit/tools tests/unit/acp/test_dispatcher.py tests/integration/runtime tests/integration/acp --cov=optimus --cov-branch --cov-report=term-missing
```

Expected: PASS with aggregate production-code coverage at or above 80%. Safety-critical `optimus.runtime.mutation` and `optimus.runtime.state` should have no unreviewed coverage holes on guard branches.

- [ ] **Step 2: Run full test suite**

Run:

```bash
pytest -v
```

Expected: PASS.

- [ ] **Step 3: Add README mode boundary note**

Append under the existing Phase 1 Transport Foundation section in `README.md`:

```markdown
### Phase 1 Mode Boundary Foundation

The runtime governance foundation implements execution modes, generation-scope
classification, lifecycle transition validation, AwaitingApproval handling, and
the `assert_mutation_allowed()` primitive. Mutation wrappers for file writes,
shell execution, and shadow patch application call the primitive before any
side effect, and ACP callers receive JSON-RPC code `-32002` when the boundary is
violated.
```

- [ ] **Step 4: Re-run focused documentation-adjacent smoke test**

Run:

```bash
pytest tests/unit/runtime tests/unit/tools -v
```

Expected: PASS.

- [ ] **Step 5: Check working tree**

Run:

```bash
git status --short
```

Expected: only intentional Plan 2 implementation files are modified or added. Pre-existing unrelated IDE, extracted-doc, or generated cache artifacts must not be staged.

- [ ] **Step 6: Commit**

```bash
git add README.md src/optimus/runtime src/optimus/tools src/optimus/acp/errors.py src/optimus/acp/dispatcher.py tests/unit/runtime tests/unit/tools tests/unit/acp/test_dispatcher.py tests/integration/runtime
git commit -m "Add mode state machine and mutation guard."
```

## Self-Review

- Spec coverage: The plan implements Architecture section 7 mode separation, LLD section 4A lifecycle state names and transition rules, the mode-specific permission matrix's guard requirement for mutation operations, and Test Strategy section 5 assertions for `assert_mutation_allowed()`, direct execution bypass rejection, AwaitingApproval denial/timeout fallback, executing/tool-calling/validating transitions, and no mutation before I/O. Composite fitness-gate retry integration and workspace path canonicalization are explicitly deferred to later roadmap plans.
- Placeholder scan: This plan avoids open placeholders. Later roadmap work is named only in Out of Scope where the Phase 1 roadmap already assigns it to other plans.
- Type consistency: `ExecutionMode`, `GenerationScope`, `AgentState`, `RuntimeContext`, `AwaitingApproval`, `MutationKind`, `MutationGuard`, and `MutationForbidden` are defined before use. JSON-RPC error code `MUTATION_FORBIDDEN` maps to runtime `MUTATION_FORBIDDEN_CODE`, both `-32002`.
- TDD compliance: Each production change has a failing-test step first, followed by minimal implementation, then a focused verification command.
- Evidence boundary: The plan is based on inspected roadmap, Plan 1 implementation files, PDF source anchors, extracted Test Strategy text, and rendered LLD state-machine pages. Generation-scope names are spec-derived; the concrete line-count and path-root classifier thresholds are conservative Phase 1 implementation assumptions.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-01-mode-state-machine-mutation-guard.md`. Two execution options:

**1. Subagent-Driven (recommended when available)** - dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - execute tasks in this session task-by-task with checkpoints. Use `superpowers:executing-plans` if available; otherwise follow this plan directly with the same red/green/refactor discipline.

Before implementation, create or switch to a dedicated branch from latest `main`, for example `agent/codex/mode-state-mutation-guard`, or create a separate worktree if this Plan 1 branch must remain untouched. Do not run `git commit`, push, or create/delete branches unless the user explicitly approves those actions.
