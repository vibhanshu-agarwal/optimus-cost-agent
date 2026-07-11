# Plan 9.85: Multi-Turn Read-Observe-Replan Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. A checkbox may be marked complete only after its stated verification command has run and passed. Do not start implementation without reviewer and operator approval of this plan.

**Goal:** Extend Plan 9.8's fail-closed, task-aware planning floor with a bounded READ -> observe -> replan workflow that can gather required evidence across settled planning turns and expose only the final plan for approval.

**Architecture:** Adapt the existing `GoalLoopController` rather than create a second loop engine. A planning-specific iteration runner emits either a validated final directive plan or a guarded READ request plus a bounded observation; `LoopBudgetPolicy` supplies turn, cost, wall-clock, repeated-failure, and stop-precedence behavior. The complete 16 KiB planning-evidence envelope is partitioned deterministically between carried observations and new guarded READ evidence, and overflow fails closed without truncation.

**Tech Stack:** Python 3.11+, Pydantic v2, existing Optimus `GoalLoopController` / `LoopBudgetPolicy`, `AgentRunner`, `GatewayClient`, `RetryController`, `PreToolGuard`, Plan 7 usage accounting, Redis plan state, pytest/pytest-asyncio/pytest-cov, Ruff, real `acpx` for ACP-tier evidence.

## Global Constraints

- The roadmap entry in `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` and Plan 9.8 implementation contract in `docs/superpowers/plans/2026-07-10-plan-9-8-task-aware-workspace-context.md` are the immediate scope anchors.
- HLD, LLD, and Test Strategy remain authoritative. Stop and ask if they conflict with this plan.
- Preserve the one-key runtime: only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` are available to the agent; provider keys remain behind the Gateway.
- Plan 9.8 remains the prerequisite correctness floor: exact paths and unique basenames resolve deterministically, ambiguous paths fail before Gateway/tool work, and no required evidence is silently truncated.
- Plan 9.85 is separate from Plan 9.9 packaging/credential diagnostics and Plan 11 intelligent context selection, ranking, summarization, or dynamic budget tuning.
- `max_planning_turns` defaults to 3 and validates `ge=1`. This is a chosen Phase 1 default consistent with bounded-loop principles; it is not derived from `RetryPolicy.max_retries=3` or the existing goal-loop runtime default of 5 iterations.
- A planning turn is a settled model decision. Transient wire retries within that turn remain governed by `RetryPolicy`; they do not consume additional planning turns.
- Every Gateway wire attempt, including a failed or retried attempt when the Gateway reports usage, must be recorded through Plan 7 accounting and charged to the same run-level `max_cost_usd` ceiling.
- Map `AgentRunRequest.max_cost_usd` directly to `LoopBudgetPolicy.max_budget_credits`; do not introduce a third cost-budget name.
- Because `AgentRunRequest.max_cost_usd` permits zero while `LoopBudgetPolicy.max_budget_credits` requires a positive value, a zero budget returns typed `PLANNING_BUDGET_EXHAUSTED` before controller construction; it is never raised to an artificial minimum.
- Planning stop precedence remains exactly `HUMAN_HALT > REPEATED_FAILURE > BUDGET_EXHAUSTED > WALL_CLOCK > MAX_ITERATIONS`.
- The planning adapter sets `repeated_failure_limit=2`. Its failure signature is the normalized, sorted set of requested READ path/range identities; requesting the same evidence on consecutive settled turns is non-progress.
- A final-cap turn that requests more READ evidence is a typed failure, never an approvable intermediate state.
- Only the final validated directive plan is hashed, persisted, or exposed through `session/request_permission`. Any replan supersedes candidate text from earlier turns.
- Approval carrying a non-final or superseded hash fails closed with `PLAN_NOT_FOUND_OR_EXPIRED`. Approval replay loads the exact stored final plan and makes no new planning Gateway call.
- All loop READs execute through `GuardedLoopToolExecutor` and `PreToolGuard`; the planning adapter must not read the filesystem directly.
- Maintain at least 80% aggregate Python production-code coverage and do not regress safety-critical coverage.
- Unit tests may use doubles. Redis/Gateway/ACP evidence tiers must use the real dependency named by the tier. ACP-protocol proof must use real `acpx`, not a project-authored ACP harness.
- Before sign-off run narrow tests, the affected integration suites, full pytest with coverage, and `python -m ruff check .`.

---

## Scope and Non-Goals

### In scope

1. A validated planning-loop policy with configurable turn and wall-clock limits and the existing run cost ceiling.
2. A strict intermediate-turn grammar for READ requests and bounded observation carryover.
3. Guarded ranged READ evidence so large required files can be observed across turns without pretending a partial range is a complete file.
4. A `GoalLoopController` adapter with deterministic settlement and existing stop precedence.
5. Cost/usage aggregation across planning turns and retry attempts.
6. Final-plan-only hashing, persistence, ACP permission emission, and approval replay.
7. Content-free planning-loop telemetry and real `acpx` evidence.

### Explicit exceptions

- No semantic ranking, automatic summarization, embeddings, contextual compression, dynamic context-window calibration, or provider-specific token budgeting; those remain Plan 11.
- No arbitrary tool expansion during planning. Plan 9.85 adds only guarded file READ ranges.
- No WRITE or TEST execution before final-plan approval.
- No changes to local Gateway packaging, credential-layer diagnostics, or non-editable install discovery; those remain Plan 9.9.
- No change to `DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES = 16 * 1024`.
- No claim that three turns can handle arbitrarily large files. If bounded ranges and carryover cannot settle within policy, return a typed failure.
- No model-initiated READ_MORE path when Plan 9.8 context already fits. Single-pass behavior remains stable; `P9.85-FU-4` tracks that unimplemented half of the roadmap user story.

## Settled-Turn Contract

Each Gateway response must parse as exactly one of:

```text
OBSERVE: <bounded observation text>
READ: <workspace-relative-path>#bytes=<start>:<end>
[READ: ...]
```

or the existing final directive grammar:

```text
PLAN: <summary>
READ: <workspace-relative-path>
WRITE: <workspace-relative-path>
CONTENT:
<replacement content>
END_CONTENT
[TEST: <safe pytest command>]
```

or an explicit refusal:

```text
REFUSE: <one-line sanitized reason>
```

An intermediate response must contain at least one ranged `READ`, must contain no `WRITE` or `TEST`, and must fit the observation cap. A final response must parse through `parse_agent_plan`, may contain ordinary final-plan READ directives, and must not contain the intermediate `OBSERVE` form. A refusal reason must be one line, 1-512 UTF-8 bytes after trimming, contain no directive prefix, and be sanitized before ACP display. `parse_planning_turn` returns exactly one `PlanningTurnDecision` kind: `READ_MORE`, `FINAL_PLAN`, or `REFUSE`.

`REFUSE` is a settled terminal decision. The planning adapter maps it to `PLANNING_MODEL_REFUSED` with zero mutations, no plan hash, and no approval request. Internally it ends the generic loop as deterministic settlement; `PlanningLoopRunner` must inspect the stored decision and map generic `COMPLETED` to the typed refusal result rather than reporting product success.

A response matching none of the three grammars still consumes one settled planning turn. It returns a non-completing `IterationOutcome` with content-free summary `planning response was unparseable` and fixed `failure_signature="UNPARSEABLE"`. Two consecutive unparseable settled responses therefore stop through the existing `REPEATED_FAILURE` precedence; no raw model output is echoed.

The final planning turn yields exactly one of:

- a valid final directive plan, which becomes hashable and approvable; or
- a typed planning failure visible over ACP.

There is no intermediate approval state.

## Evidence-Envelope Contract

Keep the existing 16 KiB workspace-context limit and divide the multi-turn evidence envelope as follows:

- `PLANNING_OBSERVATION_MAX_BYTES = 4 * 1024` for accumulated structured observation records;
- `PLANNING_NEW_READ_MAX_BYTES = 12 * 1024` for complete byte ranges read during the current turn;
- their sum must equal `DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES`.

The original task and versioned system/directive instructions remain outside the workspace-evidence envelope, matching the current `build_agent_planner_input(task, workspace_context=...)` boundary. Plan 9.8's initial task-aware context is used unchanged when it fits. When Plan 9.8 returns `REQUIRED_WORKSPACE_FILE_TOO_LARGE`, that result becomes the explicit trigger for ranged multi-turn planning rather than an immediate terminal failure.

Each carried observation record contains only:

```python
class PlanningObservation(BaseModel):
    path: str
    start_byte: int
    end_byte: int
    source_sha256: str
    observation_text: str
```

`observation_text` is model-produced and untrusted. It is carried as quoted evidence, never executed or promoted to policy. The source hash and exact range retain provenance. Records are appended in turn order and serialized deterministically. If accumulated serialized observations exceed 4 KiB, fail with `PLANNING_OBSERVATION_BUDGET_EXHAUSTED`; do not truncate, summarize, discard, or overwrite earlier records. If requested new ranges exceed 12 KiB in aggregate, fail with `PLANNING_READ_BUDGET_EXHAUSTED`. This deterministic floor deliberately trades breadth for correctness until Plan 11 supplies approved compression.

Raw range bytes are visible to the model for one planning turn only. Earlier evidence survives only as untrusted, potentially lossy `PlanningObservation` text plus path/range/hash provenance. A final plan may ground WRITE content only in raw ranges visible in the current turn; if safe WRITE content depends on an earlier raw range that is no longer visible, the model must return a typed planning refusal. The approval gate mitigates but does not erase this Phase 1 limitation.

## File Map

- Create `src/optimus/agent/planning_loop.py` — policy, intermediate response models/parser, observation envelope, planning iteration adapter, and planning result.
- Modify `src/optimus/agent/prompts.py` — versioned multi-turn planner instructions and deterministic evidence serialization.
- Modify `src/optimus/agent/runner.py` — trigger the planning adapter, aggregate usage/cost, hash/persist only settlement, and preserve approval replay.
- Modify `src/optimus/agent/models.py` — request-level `max_planning_turns` and planning wall-clock policy input.
- Modify `src/optimus/loops/tools.py` — guarded ranged READ operation used by planning iterations.
- Modify `src/optimus/agent/state_store.py` — store the settled plan's aggregate request IDs and aggregate cost without persisting intermediate source text.
- Modify `src/optimus/usage/accounting.py` and `src/optimus/usage/models.py` only as needed to record retry-attempt usage with stable per-attempt request IDs.
- Modify `src/optimus/acp/spec.py` — emit no permission request until settlement and map typed planning stops to visible completion text.
- Modify `src/optimus/acp/debug_trace.py` and `src/optimus/acp/bootstrap.py` — content-free planning-loop observer wiring.
- Create `tests/unit/agent/test_planning_loop.py`.
- Modify `tests/unit/agent/test_models.py`, `tests/unit/agent/test_prompts.py`, `tests/unit/agent/test_runner.py`, `tests/unit/agent/test_state_store.py`, `tests/unit/loops/test_tools.py`, `tests/unit/usage/test_accounting.py`, `tests/unit/acp/test_spec_protocol.py`, and `tests/unit/acp/test_bootstrap.py`; create `tests/unit/acp/test_debug_trace.py`.
- Create `tests/integration/agent/test_multi_turn_planning_flow.py`.
- Modify `tests/e2e/acp/test_spawned_agent_live.py` only for non-ACP process assertions; do not use it as ACP-tier sign-off evidence.
- Create `reports/plan-9-85-multi-turn-acpx-evidence.md` during live verification.
- Modify `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` only after all stated evidence passes.

---

### Task 1: Define the Planning Policy and Intermediate-Turn Grammar

**Deliverable:** Validated policy inputs and an unambiguous parser distinguish intermediate observation/READ requests from final plans.

**Files:**
- Create: `src/optimus/agent/planning_loop.py`
- Modify: `src/optimus/agent/models.py`
- Test: `tests/unit/agent/test_planning_loop.py`
- Test: `tests/unit/agent/test_models.py`

**Interfaces:**
- Consumes: `LoopBudgetPolicy`, `DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES`, `AgentRunRequest.max_cost_usd`.
- Produces: `PlanningLoopPolicy.to_loop_budget_policy(max_cost_usd)`, `PlanningObservation`, `PlanningReadRequest`, `PlanningTurnDecision`, and `parse_planning_turn(text)`.

- [x] **Step 1: Write failing policy validation and boundary tests**

Add tests proving:

```python
def test_planning_policy_defaults_to_three_turns_and_two_repeated_failures():
    policy = PlanningLoopPolicy()
    assert policy.max_planning_turns == 3
    assert policy.max_wall_clock_minutes == 30
    loop_policy = policy.to_loop_budget_policy(max_cost_usd=Decimal("0.05"))
    assert loop_policy.max_iterations == 3
    assert loop_policy.max_budget_credits == Decimal("0.05")
    assert loop_policy.repeated_failure_limit == 2


def test_zero_run_budget_fails_before_loop_policy_construction():
    result = run_planning_with_budget(Decimal("0"))
    assert result.stop_reason == "PLANNING_BUDGET_EXHAUSTED"
    assert result.settled_turns == 0


@pytest.mark.parametrize("turns", [0, -1])
def test_planning_policy_rejects_non_positive_turn_caps(turns: int):
    with pytest.raises(ValidationError):
        PlanningLoopPolicy(max_planning_turns=turns)


@pytest.mark.parametrize("turns", [1, 2])
def test_planning_policy_accepts_deterministic_boundary_caps(turns: int):
    assert PlanningLoopPolicy(max_planning_turns=turns).max_planning_turns == turns
```

Add `AgentRunRequest` round-trip coverage for `max_planning_turns=1` and rejection of zero.

- [x] **Step 2: Run the tests and verify the intended failures**

Run:

```bash
python -m pytest tests/unit/agent/test_planning_loop.py tests/unit/agent/test_models.py -v
```

Expected: FAIL because the planning-loop types and request field do not exist.

- [x] **Step 3: Add the validated policy and request field**

Implement:

```python
PLANNING_OBSERVATION_MAX_BYTES = 4 * 1024
PLANNING_NEW_READ_MAX_BYTES = 12 * 1024


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
```

Add to `AgentRunRequest`:

```python
max_planning_turns: int = Field(default=3, ge=1)
planning_wall_clock_minutes: int = Field(default=30, ge=1)
```

Do not add another request cost field.

- [x] **Step 4: Write failing parser tests**

Cover one READ, multiple sorted READ identities, malformed/absolute/traversal paths, overlapping ranges, `end <= start`, missing observation, oversized observation, intermediate `WRITE`/`TEST`, mixed intermediate/final grammar, a valid existing final plan, a valid one-line `REFUSE`, empty/multiline/oversized refusal reasons, and text matching none of the three grammars.

The normalized failure signature assertion is exact:

```python
decision = parse_planning_turn(
    "OBSERVE: Need both definitions.\n"
    "READ: src/b.py#bytes=0:128\n"
    "READ: src/a.py#bytes=128:256\n"
)
assert decision.failure_signature == (
    "src/a.py#bytes=128:256|src/b.py#bytes=0:128"
)
```

- [x] **Step 5: Implement strict intermediate models and parser**

Use frozen Pydantic models. Normalize paths to POSIX workspace-relative form, sort identities only for the failure signature, preserve declared order for execution, and reject duplicate or overlapping ranges for the same file. `parse_planning_turn` must return a discriminated result whose kind is `READ_MORE`, `FINAL_PLAN`, or `REFUSE`; it must never guess based on parse failure. Represent no-match text with an explicit parse error that the iteration adapter converts to the fixed `UNPARSEABLE` non-progress outcome.

- [x] **Step 6: Run narrow tests**

Run:

```bash
python -m pytest tests/unit/agent/test_planning_loop.py tests/unit/agent/test_models.py -v
```

Expected: PASS.

- [x] **Step 7: Commit**

```bash
git add src/optimus/agent/planning_loop.py src/optimus/agent/models.py tests/unit/agent/test_planning_loop.py tests/unit/agent/test_models.py
git commit -m "Define bounded planning-turn contracts"
```

---

### Task 2: Add Guarded Ranged READ Evidence and Fail-Closed Envelope Packing

**Deliverable:** Planning turns can read exact byte ranges through the existing guard, retain provenance, and fail rather than truncate either current evidence or accumulated observations.

**Files:**
- Modify: `src/optimus/loops/tools.py`
- Modify: `src/optimus/agent/planning_loop.py`
- Test: `tests/unit/loops/test_tools.py`
- Test: `tests/unit/agent/test_planning_loop.py`

**Interfaces:**
- Consumes: `GuardedLoopToolExecutor`, `PreToolGuard`, `PlanningReadRequest`.
- Produces: `GuardedLoopToolExecutor.read_file_range(...) -> PlanningReadEvidence` and `pack_planning_evidence(...) -> PlanningEvidenceEnvelope`.

- [x] **Step 1: Write failing guarded-range tests**

Cover exact bytes, UTF-8 boundary rejection, path traversal, symlink escape, missing file, changed-file hash, aggregate range budget overflow, and proof that `PreToolGuard.evaluate(...)` runs before opening the file. Do not repair a split UTF-8 code point silently; return `PLANNING_READ_NOT_UTF8_ALIGNED`.

- [x] **Step 2: Run the focused tests and verify failure**

```bash
python -m pytest tests/unit/loops/test_tools.py tests/unit/agent/test_planning_loop.py -v
```

Expected: FAIL because ranged READ and envelope packing are absent.

- [x] **Step 3: Implement the guarded ranged READ**

Add a read-only method that:

1. validates the relative path/range;
2. asks `PreToolGuard` to authorize the READ surface;
3. resolves and rechecks the path under the workspace root;
4. reads only `[start_byte:end_byte]`;
5. validates complete UTF-8 decoding;
6. returns path, range, `sha256` of the complete source file, and exact decoded range text.

The planning adapter must receive evidence only through this method. It must not accept `Path`, `open`, `read_text`, or `read_bytes` callbacks.

- [x] **Step 4: Implement deterministic envelope packing**

`pack_planning_evidence` must:

- serialize prior `PlanningObservation` records in turn order;
- reject serialized carryover above 4 KiB with `PLANNING_OBSERVATION_BUDGET_EXHAUSTED`;
- serialize complete current range blocks with path/range/hash headers;
- reject aggregate current blocks above 12 KiB with `PLANNING_READ_BUDGET_EXHAUSTED`;
- assert the combined encoded size is at most 16 KiB;
- never call a truncation helper.

Add an invariant test:

```python
assert PLANNING_OBSERVATION_MAX_BYTES + PLANNING_NEW_READ_MAX_BYTES == DEFAULT_WORKSPACE_CONTEXT_MAX_BYTES
```

- [x] **Step 5: Run the focused tests**

```bash
python -m pytest tests/unit/loops/test_tools.py tests/unit/agent/test_planning_loop.py -v
```

Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add src/optimus/loops/tools.py src/optimus/agent/planning_loop.py tests/unit/loops/test_tools.py tests/unit/agent/test_planning_loop.py
git commit -m "Add guarded ranged planning evidence"
```

---

### Task 3: Build the `GoalLoopController` Planning Adapter

**Deliverable:** A settled planning attempt reuses existing loop stop semantics and returns either one final plan or one typed failure.

**Files:**
- Modify: `src/optimus/agent/planning_loop.py`
- Modify: `src/optimus/agent/prompts.py`
- Test: `tests/unit/agent/test_planning_loop.py`
- Test: `tests/unit/agent/test_prompts.py`
- Test: `tests/unit/loops/test_controller.py`

**Interfaces:**
- Consumes: `GoalLoopController`, `IterationState`, `IterationOutcome`, `GuardedLoopToolExecutor`, `GatewayClient`, `PlanningLoopPolicy`.
- Produces: `PlanningLoopRunner.run(...) -> PlanningLoopResult` containing final plan or typed stop, aggregate reported usage, settled-turn count, and content-free evidence metadata.

- [x] **Step 1: Write failing settled-turn and stop-precedence tests**

Required cases:

- `max_planning_turns=1`, first response final -> success.
- `max_planning_turns=1`, first response READ_MORE -> `MAX_ITERATIONS` mapped to `PLANNING_TURN_LIMIT_EXHAUSTED`.
- `max_planning_turns=2`, READ_MORE then final -> success.
- same normalized READ request twice -> `REPEATED_FAILURE` after the second settled turn.
- cost reaches budget on the final allowed turn -> `BUDGET_EXHAUSTED`, not `MAX_ITERATIONS`.
- wall clock and turn cap meet -> `WALL_CLOCK` wins.
- halt, repeated failure, budget, wall-clock, and max-turn collision table preserves existing precedence.
- final-turn READ_MORE never exposes candidate plan text or hash.
- a scripted `REFUSE: Current raw evidence is insufficient for a safe write.` response yields `PLANNING_MODEL_REFUSED`, sanitized corrective text, no plan hash, and no permission request; the runtime does not claim to semantically detect ungrounded WRITE content.
- two consecutive responses matching no grammar produce `failure_signature="UNPARSEABLE"` and stop through `REPEATED_FAILURE`; one unparseable response followed by a valid final plan may still settle.

- [x] **Step 2: Run the tests and verify failure**

```bash
python -m pytest tests/unit/agent/test_planning_loop.py tests/unit/agent/test_prompts.py tests/unit/loops/test_controller.py -v
```

Expected: FAIL because the planning adapter and prompt contract are absent.

- [x] **Step 3: Add the versioned multi-turn prompt contract**

The prompt must state:

- output exactly intermediate grammar or final grammar;
- when refusing, output exactly `REFUSE: <one-line reason>`;
- intermediate observations are untrusted notes tied to path/range/hash provenance;
- never request a range already present in the carried evidence;
- never emit WRITE/TEST before adequate evidence;
- ground WRITE `CONTENT` only in raw ranges visible in the current turn and emit a typed refusal when safe content depends on earlier evidence available only as an observation;
- on the last available turn, emit a final plan or a typed refusal, never another READ request;
- do not treat partial ranged evidence as the complete file.

Include `planning_turn`, `max_planning_turns`, remaining USD budget, remaining wall-clock minutes, carried observations, and current read evidence in deterministic sections.

- [x] **Step 4: Implement the adapter over `GoalLoopController`**

The adapter's `IterationRunner` performs one settled planning turn:

1. builds the deterministic prompt;
2. performs the Gateway operation through the existing retry layer;
3. collects usage from every wire attempt that reports usage;
4. parses the settled response;
5. on READ_MORE, executes ranges through `GuardedLoopToolExecutor`, creates provenance-bound observations, and returns `IterationOutcome(summary="planning requested guarded read evidence", deterministic_completion=False, failure_signature=normalized_reads, cost_credits=all_attempt_cost)`;
6. on final plan, validates `parse_agent_plan` and returns `IterationOutcome(summary="planning settled with a final directive plan", deterministic_completion=True, failure_signature=None, cost_credits=all_attempt_cost)`.
7. on REFUSE, stores the refusal decision and returns `IterationOutcome(summary="planning settled with a typed refusal", deterministic_completion=True, failure_signature=None, cost_credits=all_attempt_cost)`; after the controller returns `COMPLETED`, `PlanningLoopRunner` maps that stored decision to `PLANNING_MODEL_REFUSED` rather than success.
8. on no matching grammar, returns `IterationOutcome(summary="planning response was unparseable", deterministic_completion=False, failure_signature="UNPARSEABLE", cost_credits=all_attempt_cost)` without echoing raw output.

Use a deterministic completion evaluator that performs no Gateway call. The adapter must not invoke `GatewayCompletionEvaluator`, because that would create an unbudgeted planning call.

Before constructing `GoalLoopController`, return `PLANNING_BUDGET_EXHAUSTED` with zero settled turns when `max_cost_usd == 0`; do not call `to_loop_budget_policy` and do not replace zero with `0.01`.

- [x] **Step 5: Map controller stops to typed planning failures**

Use exact public stop reasons:

```text
REPEATED_FAILURE -> PLANNING_REPEATED_READ_REQUEST
BUDGET_EXHAUSTED -> PLANNING_BUDGET_EXHAUSTED
WALL_CLOCK -> PLANNING_WALL_CLOCK_EXHAUSTED
MAX_ITERATIONS -> PLANNING_TURN_LIMIT_EXHAUSTED
HUMAN_HALT -> PLANNING_HALTED
settled REFUSE decision -> PLANNING_MODEL_REFUSED
```

Each failure returns sanitized corrective text, zero mutations, no plan hash, and no approval request.

- [x] **Step 6: Run focused tests**

```bash
python -m pytest tests/unit/agent/test_planning_loop.py tests/unit/agent/test_prompts.py tests/unit/loops/test_controller.py -v
```

Expected: PASS.

- [x] **Step 7: Commit**

```bash
git add src/optimus/agent/planning_loop.py src/optimus/agent/prompts.py tests/unit/agent/test_planning_loop.py tests/unit/agent/test_prompts.py tests/unit/loops/test_controller.py
git commit -m "Adapt bounded goal loops for replanning"
```

---

### Task 4: Integrate Settlement, Aggregate Cost, and Final-Only Approval Into `AgentRunner`

**Deliverable:** `AgentRunner` triggers multi-turn planning only when needed, charges the entire attempt, and persists/hashes only the final plan.

**Files:**
- Modify: `src/optimus/agent/runner.py`
- Modify: `src/optimus/agent/state_store.py`
- Modify: `src/optimus/usage/accounting.py`
- Modify: `src/optimus/usage/models.py`
- Test: `tests/unit/agent/test_runner.py`
- Test: `tests/unit/agent/test_state_store.py`
- Test: `tests/unit/usage/test_accounting.py`

**Interfaces:**
- Consumes: `PlanningLoopRunner`, existing Plan 9.8 `WorkspaceContextResult`, Plan 7 `UsageAccountingService`.
- Produces: final-only `AgentPlanRecord`, aggregate `total_cost_usd`, all Gateway request IDs, and unchanged approval replay.

- [x] **Step 1: Write failing integration-at-runner tests**

Cover:

- Plan 9.8 context fits -> exactly one planning call and unchanged behavior.
- oversized required context -> multi-turn adapter runs.
- ambiguous basename -> still fails before Gateway and never enters planning loop.
- intermediate responses never call `save_plan`, never compute/expose `plan_hash`, and never execute WRITE/TEST.
- final plan hash equals SHA-256 of final text only.
- stored `cost_usd` equals sum of all reported attempt costs.
- stored Gateway request IDs preserve every successful/reported attempt in order.
- retry wire attempts add usage but only one settled turn.
- approval with a superseded candidate hash returns `PLAN_NOT_FOUND_OR_EXPIRED`; it never executes or courtesy re-prompts with the latest plan.
- approval with the final hash replays without a Gateway call.
- a new operator prompt/run gets a fresh three-turn attempt, while Plan 7 retains cumulative per-run/session usage entries and each request still obeys `max_cost_usd`.

- [x] **Step 2: Run focused tests and verify failure**

```bash
python -m pytest tests/unit/agent/test_runner.py tests/unit/agent/test_state_store.py tests/unit/usage/test_accounting.py -v
```

Expected: FAIL on missing planning integration and aggregate record fields.

- [x] **Step 3: Trigger the loop only for the Plan 9.8 oversized-required-context condition**

Preserve terminal handling for ambiguity and other blocking reasons. Do not silently broaden the trigger. If normal context fits, retain the single-pass path for cost and behavior stability.

Construct `PlanningLoopPolicy(max_planning_turns=request.max_planning_turns, max_wall_clock_minutes=request.planning_wall_clock_minutes)` at this integration boundary, then map `request.max_cost_usd` through `to_loop_budget_policy(...)`. Add runner tests that override each request field so defaults cannot mask missing wiring.

- [x] **Step 4: Aggregate and record all reported Gateway usage**

The retry wrapper must expose per-attempt usage when present. For each item, call `UsageAccountingService.record_gateway_usage(...)` with a stable request ID derived from `run_id`, settled turn, and wire attempt. Sum `cost_usd` before loop stop evaluation. Missing usage on a transport failure is recorded as an error/unknown-cost condition; it must not be estimated locally.

- [x] **Step 5: Persist only settlement**

Extend `AgentPlanRecord` with:

```python
gateway_request_ids: tuple[str, ...] = ()
planning_turns: int = Field(default=1, ge=1)
```

Keep `gateway_request_id` as the final settled response ID for compatibility. Set `cost_usd` to aggregate reported planning cost. Do not persist intermediate source ranges or model observations in the approval store.

- [x] **Step 6: Preserve exact final-hash replay**

Hash only after final grammar validation. On approval, load by `run_id + final plan_hash`, compare task/mode/workspace as today, and execute the stored final text without planning or Gateway calls. A missing/superseded hash remains fail-closed.

- [x] **Step 7: Run focused tests**

```bash
python -m pytest tests/unit/agent/test_runner.py tests/unit/agent/test_state_store.py tests/unit/usage/test_accounting.py -v
```

Expected: PASS.

- [x] **Step 8: Commit**

```bash
git add src/optimus/agent/runner.py src/optimus/agent/state_store.py src/optimus/usage/accounting.py src/optimus/usage/models.py tests/unit/agent/test_runner.py tests/unit/agent/test_state_store.py tests/unit/usage/test_accounting.py
git commit -m "Settle multi-turn plans before approval"
```

---

### Task 5: Wire ACP Settlement Visibility and Content-Free Telemetry

**Deliverable:** ACP clients see progress without receiving a permission request until final settlement, and typed failures remain visible without leaking source.

**Files:**
- Modify: `src/optimus/acp/spec.py`
- Modify: `src/optimus/acp/debug_trace.py`
- Modify: `src/optimus/acp/bootstrap.py`
- Test: `tests/unit/acp/test_spec_protocol.py`
- Create: `tests/unit/acp/test_debug_trace.py`
- Test: `tests/unit/acp/test_bootstrap.py`

**Interfaces:**
- Consumes: settled/failure `AgentRunResult` and content-free planning observer events.
- Produces: ACP `session/update`, final-only `session/request_permission`, sanitized terminal completion, and JSONL trace evidence.

- [x] **Step 1: Write failing ACP protocol tests**

Use a scripted runner to prove:

- intermediate turns emit optional progress updates only;
- zero `session/request_permission` messages occur before final settlement;
- settlement emits exactly one permission request carrying the final hash;
- typed planning failures emit no permission request and end with `stopReason: end_turn`;
- `PLANNING_MODEL_REFUSED` emits sanitized refusal text, no plan hash, and no permission request;
- a superseded hash cannot reach execution;
- trace fields contain turn number, requested path/range identities, byte counts, hashes, costs, stop reason, and request IDs but no source or observation text.

- [x] **Step 2: Run focused ACP tests and verify failure**

```bash
python -m pytest tests/unit/acp/test_spec_protocol.py tests/unit/acp/test_debug_trace.py tests/unit/acp/test_bootstrap.py -v
```

Expected: FAIL on missing settlement-aware protocol behavior and observer wiring.

- [x] **Step 3: Implement final-only permission emission**

Keep the `session/prompt` request pending across internal settled planning turns. Emit sanitized `session/update` progress such as `Planning turn 2 of 3: reading 2 guarded ranges.` Do not include paths if the existing ACP redaction policy classifies them as sensitive. Send `session/request_permission` only when `AgentRunStatus.AWAITING_APPROVAL` includes the final hash.

- [x] **Step 4: Implement content-free trace events**

Use hypothesis ID `P9.85-REPLAN`. Include `run_id`, `session_id`, settled turn, max turns, reported aggregate cost, remaining budget, range identities/hashes/byte counts, retry count, and loop stop. Exclude prompts, source bytes, observation text, credentials, and raw model output.

- [x] **Step 5: Run focused ACP tests**

```bash
python -m pytest tests/unit/acp/test_spec_protocol.py tests/unit/acp/test_debug_trace.py tests/unit/acp/test_bootstrap.py -v
```

Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add src/optimus/acp/spec.py src/optimus/acp/debug_trace.py src/optimus/acp/bootstrap.py tests/unit/acp/test_spec_protocol.py tests/unit/acp/test_debug_trace.py tests/unit/acp/test_bootstrap.py
git commit -m "Expose settled replanning over ACP"
```

---

### Task 6: Add Cross-Layer Integration and Regression Gates

**Deliverable:** Fake-based tests prove deterministic branches; real dependency tiers prove their named contracts without mislabeling harness evidence.

**Files:**
- Create: `tests/integration/agent/test_multi_turn_planning_flow.py`
- Modify: `tests/integration/agent/test_redis_live_agent.py`
- Modify: `tests/integration/gateway/test_gateway_live.py`
- Modify: `tests/e2e/acp/test_spawned_agent_live.py`

**Interfaces:**
- Consumes: production bootstrap, real Redis state store, real Gateway fixture, spawned agent process.
- Produces: integration evidence for settlement, aggregate usage, persistence, and regression safety.

- [ ] **Step 1: Add deterministic fake-based integration cases**

Prove a two-turn READ_MORE -> final flow, a repeated-range failure, observation overflow, current-read overflow, cap=1, cap=2, budget/max-turn collision, no pre-settlement mutation, and exact approval replay.

- [ ] **Step 2: Run deterministic integration tests**

```bash
python -m pytest tests/integration/agent/test_multi_turn_planning_flow.py -v
```

Expected: PASS. Label this evidence fake-based and not sufficient for live sign-off.

- [ ] **Step 3: Add real Redis persistence coverage**

With `requires_redis`, persist only the final plan and aggregate metadata, recreate the runner/store, approve the final hash, and prove no new Gateway call. Assert no intermediate source or observation text exists in the persisted plan record.

- [ ] **Step 4: Run the real Redis tier**

```bash
python -m pytest -m requires_redis tests/integration/agent/test_redis_live_agent.py -v
```

Expected: PASS against a real TimeSeries-capable Redis. If unavailable, report NOT RUN; do not substitute a fake.

- [ ] **Step 5: Add real Gateway accounting coverage**

With `requires_gateway`, run a bounded two-turn prompt using real Optimus credentials, assert distinct `gateway_request_id` values, aggregate reported costs, one-key environment, and no locally resolvable provider key.

- [ ] **Step 6: Run the real Gateway tier**

```bash
python -m pytest -m requires_gateway tests/integration/gateway/test_gateway_live.py -v
```

Expected: PASS against the real Gateway. If credentials are unavailable, report NOT RUN; do not substitute a fake.

- [ ] **Step 7: Run spawned-process regression tests**

```bash
python -m pytest tests/e2e/acp/test_spawned_agent_live.py -v
```

Expected: PASS. This proves process behavior only and is not the ACP-tier live artifact.

- [ ] **Step 8: Commit**

```bash
git add tests/integration/agent/test_multi_turn_planning_flow.py tests/integration/agent/test_redis_live_agent.py tests/integration/gateway/test_gateway_live.py tests/e2e/acp/test_spawned_agent_live.py
git commit -m "Verify multi-turn planning across runtime layers"
```

---

### Task 7: Produce Real `acpx` Evidence, Close Plan 9.85, and Track Plan 9.87

**Deliverable:** A redacted artifact proves Plan 9.85's real ACP protocol path; the roadmap then marks Plan 9.85 implemented/live-verified with explicit deferrals and creates Plan 9.87 as their durable owner.

**Files:**
- Create: `reports/plan-9-85-multi-turn-acpx-evidence.md`
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`

**Interfaces:**
- Consumes: installed `optimus-agent`, real local Optimus Gateway, real TimeSeries-capable Redis, real `acpx`, only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` in the agent environment.
- Produces: claim-to-evidence mapping for multi-turn ACP behavior.

- [ ] **Step 1: Verify live prerequisites without exposing secrets**

Confirm `acpx --version`, `optimus-agent --check-config`, Redis TimeSeries capability, Gateway health, and the absence of local provider keys. Record versions and sanitized outcomes only.

- [ ] **Step 2: Run a real `acpx` multi-turn scenario**

Use a temporary workspace whose required evidence cannot fit Plan 9.8's single-pass complete-file block but can settle through two guarded ranges. Capture the ACP transcript and content-free trace proving:

- at least two settled planning turns;
- no permission request after the intermediate READ_MORE turn;
- guarded range identities and hashes without source text;
- distinct Gateway request IDs and aggregate reported cost;
- one final plan hash and one permission request;
- explicit approval of that exact hash;
- mutation only after approval;
- `stopReason: end_turn`.

Do not use `tests/e2e/acp`, `operator_verify.py`, or another project-authored client as the ACP evidence source.

- [ ] **Step 3: Run a real `acpx` terminal-boundary scenario**

Set `max_planning_turns=1` for a task that requests more READ evidence. Prove typed `PLANNING_TURN_LIMIT_EXHAUSTED`, zero permission requests, zero mutation, visible corrective text, and `end_turn`.

Live model-emitted `REFUSE:` evidence is owned by Plan 9.87 (`P9.85-FU-5`). This turn-limit scenario proves the shared typed-failure ACP surface live with real `acpx`: sanitized corrective text, zero permission requests, zero mutation, and `end_turn`.

- [ ] **Step 4: Run a real `acpx` superseded-hash rejection scenario**

Attempt approval with a non-final hash captured only inside the controlled test fixture, not exposed by the agent protocol. Prove no execution and exact `PLAN_NOT_FOUND_OR_EXPIRED`. Then approve the final hash and prove exact replay.

- [ ] **Step 5: Write the redacted evidence report**

Include commands, versions, timestamps, run/session IDs, request IDs, turn counts, byte budgets, reported costs, approval IDs/hashes, mutation outcome, and explicit redaction notes. For every Definition of Done claim, name the real artifact line or transcript section that proves it.

- [ ] **Step 6: Run full verification**

```bash
python -m pytest tests/unit/agent tests/unit/loops tests/unit/acp tests/unit/usage -v
python -m pytest tests/integration/agent tests/integration/acp tests/integration/usage -v
python -m pytest --cov=src/optimus --cov-report=term-missing --cov-fail-under=80
python -m ruff check .
git diff --check
```

Expected: all available tests PASS, coverage is at least 80%, Ruff is clean, and `git diff --check` emits no output. Report any live tier not run; do not check its DoD item.

- [ ] **Step 7: Update the roadmap only after evidence passes**

Mark Plan 9.85 **implemented and live-verified for the oversized-required-context trigger**, link `reports/plan-9-85-multi-turn-acpx-evidence.md`, and state that it is closed with recorded deferrals rather than silently claiming those deferrals. The Plan 9.85 status line must name `P9.85-FU-4` (model-initiated evidence requests when Plan 9.8 context fits) and `P9.85-FU-5` (live model-emitted refusal demonstration) as deferred to Plan 9.87. Retain the shipped limitations: fixed 4/12 KiB partition; raw evidence is visible for one turn and earlier evidence is carried only as untrusted observations; no intelligent compression; typed failure when safe WRITE content is not grounded in currently visible raw evidence or evidence cannot settle within policy.

In the same roadmap edit, add this separate lane between Plan 9.85 and Plan 9.9:

```markdown
## Plan 9.87 (Tracked, Not Yet Scheduled): Model-Initiated Replanning and Live Refusal Evidence

**Raised:** Deferred from Plan 9.85 as `P9.85-FU-4` and `P9.85-FU-5` when closing the oversized-required-context workflow.

**Initial scope:**
- Let a model enter the bounded guarded READ_MORE workflow when Plan 9.8 context fits but is insufficient for a safe WRITE, without imposing multi-turn cost on tasks that settle single-pass.
- Produce real `acpx` evidence that the live model emits `REFUSE:` and that ACP surfaces `PLANNING_MODEL_REFUSED` with sanitized text, zero plan hash, zero permission requests, zero mutation, and `end_turn`.

**Status:** Tracked, not yet scheduled. This planning-loop lane is separate from Plan 9.9 packaging/credential diagnostics and from Plan 11 intelligent selection/compression.
```

Add a Recommended Sequence entry for Plan 9.87 immediately after Plan 9.85 and before Plan 9.9. Renumber later sequence entries if the roadmap uses ordinal numbering. The status prose must make clear that Plan 9.85 is closed with these recorded deferrals, while Plan 9.87 is not implemented.

- [ ] **Step 8: Commit the live evidence and roadmap closure**

```bash
git add reports/plan-9-85-multi-turn-acpx-evidence.md docs/superpowers/plans/2026-07-01-phase-1-roadmap.md
git commit -m "Record live Plan 9.85 ACP evidence"
```

---

## Definition of Done

- [ ] `max_planning_turns` defaults to 3, validates `ge=1`, and boundary tests cover 1 and 2.
- [ ] Planning uses `GoalLoopController` and existing stop precedence with `repeated_failure_limit=2`.
- [ ] A settled planning turn is distinct from retry wire attempts; all reported attempt usage is charged and recorded.
- [ ] `max_cost_usd` maps directly to `LoopBudgetPolicy.max_budget_credits`.
- [ ] Repeating the same normalized path/range set on consecutive settled turns stops with `PLANNING_REPEATED_READ_REQUEST`.
- [ ] The 16 KiB envelope is exactly partitioned into 4 KiB carryover and 12 KiB current READ evidence.
- [ ] Neither accumulated observations nor current ranges are silently truncated, summarized, or discarded.
- [ ] Final WRITE content is grounded only in raw ranges visible in the current turn; dependence on earlier observation-only evidence produces a typed refusal.
- [ ] Scripted unit/ACP tests prove `REFUSE: <one-line reason>` parses and maps to terminal `PLANNING_MODEL_REFUSED` with sanitized text, no plan hash, and no approval request; the shared typed-failure ACP surface is proven live by the real `acpx` turn-limit scenario.
- [ ] Responses matching no settled-turn grammar consume a turn with fixed `UNPARSEABLE` failure signature, and two consecutive occurrences stop through `REPEATED_FAILURE` without echoing raw output.
- [ ] Every ranged READ is authorized through `GuardedLoopToolExecutor` and `PreToolGuard`.
- [ ] No intermediate candidate is hashed, persisted, or exposed for approval.
- [ ] A final-turn READ_MORE response becomes a typed failure with no WRITE and no approval request.
- [ ] Only the final plan hash is accepted; superseded/missing hashes fail closed.
- [ ] Approval replay executes the exact stored final text without another planning Gateway call.
- [ ] Budget exhaustion beats max iterations at the same boundary.
- [ ] Plan 9.8 ambiguity failures still occur before Gateway/tool work and single-pass tasks retain their one-call behavior.
- [ ] Content-free telemetry proves turns, ranges, hashes, costs, retry counts, and stops without source/observation text or secrets.
- [ ] Real Redis evidence proves final-only persistence and replay.
- [ ] Real Gateway evidence proves distinct request IDs, aggregate reported cost, and the one-key environment.
- [ ] Real `acpx` evidence proves intermediate non-approval, final approval, post-approval mutation, terminal failure, and explicit turn completion.
- [ ] Aggregate Python production coverage remains at least 80%.
- [ ] `python -m ruff check .` passes before sign-off.

## Deferred Follow-Ups

### P9.85-FU-1: Intelligent observation compression

**Owner:** Plan 11.

**Acceptance criteria:** An approved design may replace fixed fail-closed carryover with provenance-preserving compression, regret measurement, and calibration gates. Until then, overflow remains terminal.

### P9.85-FU-2: Dynamic planning-evidence partition

**Owner:** Plan 11.

**Acceptance criteria:** Calibrated evidence justifies changing the fixed 4 KiB/12 KiB split without weakening Plan 9.8 completeness and ambiguity guarantees.

### P9.85-FU-3: Cross-run/session spend policy

**Owner:** Future budget-governance plan.

**Acceptance criteria:** Define operator-configurable cumulative session/project ceilings above the existing per-run `max_cost_usd` and Plan 7 ledger. Plan 9.85 records all usage but does not invent a new cross-run denial policy.

### P9.85-FU-4: Model-initiated evidence requests when Plan 9.8 context fits

**Owner:** Plan 9.87; coordinate with Plan 11 if intelligent selection or compression becomes necessary.

**Acceptance criteria:** When the initial Plan 9.8 context fits but the model cannot safely form a WRITE, the settled response may enter the same bounded guarded READ_MORE workflow without imposing multi-turn cost on tasks that can finish single-pass. The design must define an explicit opt-in trigger, preserve final-only approval, charge all reported usage, and provide real `acpx` evidence for both unchanged single-pass behavior and model-initiated replanning.

### P9.85-FU-5: Live model-emitted refusal demonstration

**Owner:** Plan 9.87.

**Acceptance criteria:** With a real Gateway/model and real `acpx`, produce a task where the live model emits `REFUSE:` because safe WRITE content cannot be grounded in currently visible raw evidence. Prove ACP returns `PLANNING_MODEL_REFUSED` with sanitized visible text, zero plan hash, zero permission requests, zero mutation, and `end_turn`. Scripted unit/ACP evidence remains necessary for deterministic grammar and mapping coverage but cannot satisfy this live model-behavior claim.

### P9.85-FU-6: Planning gateway calls through `RetryController`

**Owner:** Task 4 integration (Plan 9.85).

**Status:** `PlanningLoopRunner` wraps each settled-turn Gateway call in `RetryController` with per-attempt usage callbacks. Runner-level accounting records stable `run_id:planning:{turn}:{wire_attempt}` request IDs when normalized usage fields are present.

**Remaining acceptance criteria:** prove multi-attempt usage aggregation when transient failures report billable usage before aborting; integration tests for transport failures with unknown cost.

## Plan Self-Review Record

- **Roadmap coverage:** turn cap, multi-call budget/cost, final approval hash, and real `acpx` evidence map to named tasks and DoD checks for the oversized-required-context trigger. Plan 9.85 closes as implemented/live-verified with `P9.85-FU-4` and `P9.85-FU-5` explicitly deferred to the separately tracked Plan 9.87; closure means closed with recorded deferrals, not silent omission or overclaim.
- **Plan 9.8 fidelity:** exact/unique path behavior and ambiguity refusal remain unchanged; only oversized required context triggers ranged multi-turn planning.
- **Loop-contract fidelity:** planning reuses `GoalLoopController`, existing precedence, `max_budget_credits`, and a deterministic non-Gateway evaluator.
- **Retry distinction:** settled turns and transient retries are separately counted, while every reported wire cost accrues to the run.
- **Envelope ambiguity:** fixed byte allocations, serialization order, provenance fields, and fail-closed overflow are explicit.
- **Approval race:** no intermediate protocol approval surface exists, and only stored final hashes replay.
- **Evidence-tier fidelity:** unit doubles are not presented as live proof; Redis, Gateway, and ACP sign-off use real named dependencies.
- **Placeholder scan:** no `TBD`, `TODO`, “similar to,” or unspecified error-handling steps remain.
