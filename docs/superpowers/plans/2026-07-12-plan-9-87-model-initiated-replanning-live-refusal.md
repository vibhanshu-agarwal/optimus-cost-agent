# Plan 9.87: Model-Initiated Replanning and Live Refusal Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. A checkbox may be marked complete only after its stated verification command has run and passed. Do not start implementation without reviewer and operator approval of this plan.

**Goal:** Let fitting-context AGENT tasks opt into the existing bounded guarded `READ_MORE` loop through an explicit model decision, while preserving one-turn settlement for tasks that can finish immediately and producing fresh live `acpx` proof of both model-initiated replanning and model-emitted refusal.

**Architecture:** Unify only AGENT-mode planning behind `PlanningLoopRunner`; PLAN and CHAT keep their direct prose-capable path and fail oversized required context before Gateway work. Turn-1 initial context is ephemeral, later turns re-read every raw range needed for a complete replacement, and the existing 4 KiB observation plus 12 KiB current-read partition remains unchanged. Refusal settlement receives explicit precedence and live evidence is split into independent FU-4 and FU-5 lanes.

**Tech Stack:** Python 3.11+, Pydantic v2, existing `AgentRunner`, `PlanningLoopRunner`, `GoalLoopController`, `RetryController`, `PreToolGuard`, Plan 7 usage accounting, Redis state store, ACP, pytest/pytest-asyncio/pytest-cov, Ruff, and real `acpx`.

## Global Constraints

- The committed design source is `docs/superpowers/specs/2026-07-12-plan-9-87-model-initiated-replanning-live-refusal-design.md` at commit `e9fc95c`.
- The roadmap, Plan 9.8, Plan 9.85, HLD, LLD, and Test Strategy remain authoritative. Stop and ask if they conflict.
- Preserve the one-key runtime: only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` may be available locally; provider keys remain behind the Gateway.
- Unify AGENT planning only. PLAN and CHAT remain direct prose-capable modes.
- PLAN/CHAT with `REQUIRED_WORKSPACE_FILE_TOO_LARGE` fail before Gateway or tool work.
- A validated model-emitted `READ_MORE` is the only opt-in trigger for an additional fitting-context planning turn.
- Turn-1 initial context is raw evidence for turn 1 only. It is not copied into observations or retained as a third envelope.
- The model may re-read ranges seen in turn-1 initial context. Later-turn raw ranges pass `PreToolGuard` and carry current source-hash provenance.
- Keep the 4 KiB observation, 12 KiB current-read, and 16 KiB total evidence limits unchanged.
- Cost exactly equal to `max_cost_usd` is exhaustion (`>=`).
- Human halt wins a settlement race. A settled `REFUSE:` then wins over repeated-failure state, budget, and wall-clock. A settled final plan wins over stale repeated-failure state but loses to budget and wall-clock.
- Repeated identical reads remain `PLANNING_REPEATED_READ_REQUEST`; repeated unparseable responses become `PLANNING_UNPARSEABLE_RESPONSE`.
- Refusal returns sanitized text, no plan hash, no permission, and no mutation. Over-budget or over-time final plans also return no persisted or approvable hash.
- Do not close or silently absorb the remaining `P9.85-FU-6` billable-abort/unknown-cost cases.
- Unit tests may use doubles. Redis/Gateway/ACP evidence tiers use the real named dependency; ACP proof uses real `acpx`, not a project-authored ACP client.
- Maintain at least 80% aggregate Python production-code coverage and do not regress safety-critical coverage.
- Before sign-off run narrow tests, relevant integrations, full coverage, and `python -m ruff check .`.

---

## Scope

### In scope

1. Version the multi-turn prompt and make turn-1 ephemerality, re-read requirements, and refusal rules explicit.
2. Route every non-blocking AGENT planning request through `PlanningLoopRunner`.
3. Correct oversized PLAN/CHAT routing.
4. Classify repeated unparseable responses accurately.
5. Implement and test the approved refusal/final-plan settlement precedence.
6. Preserve final-only hashing, persistence, permission, replay, usage charging, and content-free telemetry.
7. Add deterministic FU-4 plumbing tests and ACP failure-surface tests.
8. Create reproducible live fixtures and a helper that invokes real `acpx` without implementing ACP.
9. Produce separate FU-4A, FU-4B, and FU-5 claim-to-evidence tables before updating the roadmap.
10. Amend the multi-turn prompt (version bump) so `READ_MORE` re-reads of turn-1-visible files request full known byte ranges, then re-capture qualifying FU-4B live evidence (Task 6b).

### Explicit exceptions

- No Plan 11 context intelligence or dynamic evidence partitioning.
- No PLAN/CHAT multi-turn grammar or new planning tools.
- No Plan 9.9 packaging/credential work.
- No fake-Gateway claim of real-model one-turn behavior.
- No use of the incidental Plan 9.85 refusal observation as closure evidence.
- No mechanical current-raw-evidence grounding guard in this plan.

## Observable Compatibility Matrix

| Case | Status | Final state | Stop reason | Settled turns | Wire attempts | Output exposure | Plan hash | Permissions | Mutations |
|---|---|---|---|---:|---:|---|---|---:|---|
| Fitting AGENT final | `AWAITING_APPROVAL` | `AWAITING_APPROVAL` | none | 1 | 1 clean | Final plan only | Present/persisted | 1 over ACP | 0 before approval; positive only after approved replay |
| One malformed then final | `AWAITING_APPROVAL` | `AWAITING_APPROVAL` | none | 2 | 2 clean | Final plan only; malformed text hidden | Present/persisted | 1 over ACP | 0 before approval; positive only after approved replay |
| Repeated malformed | `TERMINATED` | `TERMINATED` | `PLANNING_UNPARSEABLE_RESPONSE` | 2 | 2 clean | Fixed sanitized corrective text | None | 0 | 0 |
| Valid refusal | `FAILED` | `FAILED` | `PLANNING_MODEL_REFUSED` | Refusal turn | Same as charged attempts | Sanitized refusal only | None | 0 | 0 |
| Final at cost equality/excess | `TERMINATED` | `TERMINATED` | `PLANNING_BUDGET_EXHAUSTED` | Final turn | Same as charged attempts | Fixed corrective text; final body hidden | None | 0 | 0 |
| Final after wall clock | `TERMINATED` | `TERMINATED` | `PLANNING_WALL_CLOCK_EXHAUSTED` | Final turn | Same as charged attempts | Fixed corrective text; final body hidden | None | 0 | 0 |
| Oversized PLAN/CHAT | `FAILED` | `FAILED` | `REQUIRED_WORKSPACE_FILE_TOO_LARGE` | 0 | 0 | Existing blocking message | None | 0 | 0 |
| Repeated identical ranged READ | `TERMINATED` | `TERMINATED` | `PLANNING_REPEATED_READ_REQUEST` | Existing bounded stop turn | Same as charged attempts | Fixed corrective text | None | 0 | 0 |
| Recovered transient failure then final | `AWAITING_APPROVAL` | `AWAITING_APPROVAL` | none | 1 | Greater than 1 | Final plan only | Present/persisted | 1 over ACP | 0 before approval; positive only after approved replay |

## File Map

- Modify `src/optimus/agent/prompts.py`, `runner.py`, and `planning_loop.py`.
- Modify `src/optimus/acp/spec.py`.
- Modify `tests/unit/agent/test_prompts.py`, `test_runner.py`, and `test_planning_loop_runner.py`.
- Modify `tests/unit/acp/test_spec_protocol.py`.
- Create `tests/integration/agent/test_model_initiated_replanning_flow.py`.
- Create `tools/run_plan987_acpx_live_evidence.py` and `tests/unit/tools/test_run_plan987_acpx_live_evidence.py`.
- Create `reports/plan-9-87-model-replanning-refusal-acpx-evidence.md` during live verification.
- Modify the roadmap only after all evidence passes.

---

### Task 1: Version the Turn-1 Prompt Contract

**Files:**
- Modify: `src/optimus/agent/prompts.py`
- Modify: `tests/unit/agent/test_prompts.py`

**Interfaces:**
- Consumes: `build_multi_turn_planner_input(..., initial_workspace_context=...)`.
- Produces: `MULTI_TURN_PLANNER_PROMPT_VERSION:2026-07-12-plan-9-87` and explicit ephemerality/re-read/refusal rules.

- [x] **Step 1: Write the failing prompt test**

```python
def test_multi_turn_prompt_marks_initial_context_ephemeral_and_requires_complete_reread():
    prompt = build_multi_turn_planner_input(
        "Update target.py",
        planning_turn=1,
        max_planning_turns=3,
        remaining_budget_usd=Decimal("0.05"),
        remaining_wall_clock_minutes=30,
        initial_workspace_context="--- target.py ---\noriginal\n",
    )
    assert MULTI_TURN_PLANNER_PROMPT_VERSION.endswith("2026-07-12-plan-9-87")
    assert "available on planning turn 1 only" in prompt
    assert "will not be carried to planning turn 2" in prompt
    assert "request every raw byte range" in prompt
    assert "including ranges already visible in the initial workspace context" in prompt
    assert "observations cannot ground final WRITE content" in prompt
    assert "emit REFUSE" in prompt
```

- [x] **Step 2: Run the test and verify failure**

```bash
python -m pytest tests/unit/agent/test_prompts.py::test_multi_turn_prompt_marks_initial_context_ephemeral_and_requires_complete_reread -v
```

Expected: FAIL because the new version and wording are absent.

- [x] **Step 3: Add literal prompt rules and bump the version**

Set:

```python
MULTI_TURN_PLANNER_PROMPT_VERSION = (
    "MULTI_TURN_PLANNER_PROMPT_VERSION:2026-07-12-plan-9-87"
)
```

Add literal rules stating: initial context is turn-1-only; it is not carried; another turn must request every required raw range, including previously visible ranges; observations cannot ground WRITE; impossible raw coexistence requires `REFUSE:`.

- [x] **Step 4: Run all prompt tests**

```bash
python -m pytest tests/unit/agent/test_prompts.py -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/optimus/agent/prompts.py tests/unit/agent/test_prompts.py
git commit -m "Clarify ephemeral planning context"
```

---

### Task 2: Route Fitting AGENT Context Through the Shared Loop

**Files:**
- Modify: `src/optimus/agent/runner.py`
- Modify: `tests/unit/agent/test_runner.py`

**Interfaces:**
- Consumes: Plan 9.8 workspace context and `PlanningLoopRunner.run`.
- Produces: `_run_multi_turn_planning(..., initial_workspace_context: str, ...)` as the AGENT planning entry.

- [x] **Step 1: Write the failing fitting-context test**

Name it `test_fitting_agent_context_uses_planning_loop_and_settles_in_one_turn`. Use a fitting `target.py` and scripted final plan. Assert one call with `metadata.purpose == "planning_turn"`, the Plan 9.87 prompt version and target context are present, result is `AWAITING_APPROVAL`, and the stored record has `planning_turns == 1` and `gateway_request_ids == ("gw-1",)`.

- [x] **Step 2: Write failing oversized PLAN/CHAT tests**

Add separate tests named `test_oversized_plan_mode_fails_before_gateway` and `test_oversized_chat_mode_fails_before_gateway` against a 17 KiB required file. Assert `FAILED`, `REQUIRED_WORKSPACE_FILE_TOO_LARGE`, zero cost, no hash, and `gateway.calls == []`. Retain the fitting PLAN prose/`CHAT_ONLY` test.

- [x] **Step 3: Verify the new tests fail**

```bash
python -m pytest tests/unit/agent/test_runner.py::test_fitting_agent_context_uses_planning_loop_and_settles_in_one_turn tests/unit/agent/test_runner.py::test_oversized_plan_mode_fails_before_gateway tests/unit/agent/test_runner.py::test_oversized_chat_mode_fails_before_gateway -v
```

- [x] **Step 4: Make context routing mode-aware**

Implement this branch shape:

```python
if workspace_context.blocking_stop_reason is not None:
    if (
        request.execution_mode is ExecutionMode.AGENT
        and workspace_context.blocking_stop_reason == _OVERSIZED_REQUIRED_CONTEXT_TRIGGER
    ):
        return self._run_multi_turn_planning(
            request=request,
            context=context,
            toolbox=toolbox,
            initial_workspace_context="",
            progress_observer=planning_progress_observer,
        )
    return self._workspace_context_failure_result(request, workspace_context)

if request.execution_mode is ExecutionMode.AGENT:
    return self._run_multi_turn_planning(
        request=request,
        context=context,
        toolbox=toolbox,
        initial_workspace_context=workspace_context.text,
        progress_observer=planning_progress_observer,
    )
```

Keep the direct Gateway lane only for fitting PLAN/CHAT.

- [x] **Step 5: Pass initial context to the loop**

Add `initial_workspace_context: str` to `_run_multi_turn_planning` and pass it unchanged to `planner.run`. Do not parse turns in `runner.py`.

- [x] **Step 6: Update intentionally changed AGENT tests**

Replace old AGENT assertions for `purpose="agent_plan"`, `UNPARSEABLE_PLAN`, raw malformed output, and direct `BUDGET_EXHAUSTED` with the compatibility-matrix outcomes. Leave PLAN/CHAT behavior unchanged.

- [x] **Step 7: Pin approved-plan replay before the shared-loop routing branch**

Retain and strengthen `test_approved_agent_run_replays_stored_plan_without_second_gateway_call`. After the first request stores a fitting-context Plan 9.87 plan, submit a second AGENT request with `approval.approved=True` and the exact stored hash. Assert the second request executes the stored plan, `len(gateway.calls)` remains exactly `1` across both requests, and the Gateway's deliberately changed second response is absent from disk. This proves the approved-replay branch performs zero planning calls after unification.

- [x] **Step 8: Run the full runner unit file**

```bash
python -m pytest tests/unit/agent/test_runner.py -v
```

Expected: PASS.

- [x] **Step 9: Commit**

```bash
git add src/optimus/agent/runner.py tests/unit/agent/test_runner.py
git commit -m "Unify agent planning orchestration"
```

---

### Task 3: Correct Non-Progress Classification and Settlement Precedence

**Files:**
- Modify: `src/optimus/agent/planning_loop.py`
- Modify: `tests/unit/agent/test_planning_loop_runner.py`

**Interfaces:**
- Consumes: `PlanningTurnKind`, `IterationOutcome.failure_signature`, `LoopStopReason`, and `IterationState`.
- Produces: content-free non-progress tracking, `PLANNING_UNPARSEABLE_RESPONSE`, and decision-aware settlement ordering.

- [x] **Step 1: Write failing classification tests**

Name the tests `test_repeated_unparseable_responses_map_to_unparseable_stop` and `test_repeated_identical_read_more_maps_to_read_stop`. The first expects `PLANNING_UNPARSEABLE_RESPONSE`, two turns, no plan/hash, and sanitized corrective text. The second remains pinned to `PLANNING_REPEATED_READ_REQUEST`.

- [x] **Step 2: Write failing precedence tests**

Add independent tests named `test_refusal_wins_accumulated_repeated_failure`, `test_refusal_wins_budget_equality`, and `test_refusal_wins_wall_clock`; each returns `PLANNING_MODEL_REFUSED`. Add `test_human_halt_wins_refusal_race` returning `PLANNING_HALTED`. Add `test_final_plan_at_budget_equality_has_no_hash` and `test_final_plan_loses_wall_clock_has_no_hash` returning their resource stops with no plan/hash. Add `test_refusal_reason_is_sanitized_before_planning_result`: emit a raw reason containing the resolved workspace root and `token PLAN987_SECRET_SENTINEL`, then assert the result contains `<workspace>` and `token **********` but neither raw value.

- [x] **Step 3: Verify focused tests fail**

```bash
python -m pytest tests/unit/agent/test_planning_loop_runner.py::test_repeated_unparseable_responses_map_to_unparseable_stop tests/unit/agent/test_planning_loop_runner.py::test_repeated_identical_read_more_maps_to_read_stop tests/unit/agent/test_planning_loop_runner.py::test_refusal_wins_accumulated_repeated_failure tests/unit/agent/test_planning_loop_runner.py::test_refusal_wins_budget_equality tests/unit/agent/test_planning_loop_runner.py::test_refusal_wins_wall_clock tests/unit/agent/test_planning_loop_runner.py::test_human_halt_wins_refusal_race tests/unit/agent/test_planning_loop_runner.py::test_final_plan_at_budget_equality_has_no_hash tests/unit/agent/test_planning_loop_runner.py::test_final_plan_loses_wall_clock_has_no_hash tests/unit/agent/test_planning_loop_runner.py::test_refusal_reason_is_sanitized_before_planning_result -v
```

- [x] **Step 4: Track only content-free non-progress kind**

```python
self._last_non_progress_kind: Literal["READ_MORE", "UNPARSEABLE"] | None = None
```

Set `UNPARSEABLE` on parse failure and `READ_MORE` on validated read decision. Map a generic repeated-failure stop according to this field; never retain raw malformed output.

- [x] **Step 5: Implement approved settlement order**

In the `COMPLETED` branch: human halt first; typed evidence/safety stop second; valid REFUSE third; valid FINAL_PLAN fourth. Refusal bypasses repeated/budget/wall checks. Final plan ignores stale repeated failure but checks `credits_spent >= max_budget_credits` and wall clock before hashing.

- [x] **Step 6: Add corrective text**

```python
"PLANNING_UNPARSEABLE_RESPONSE": (
    "Planning stopped after repeated responses that did not match the required directive grammar."
),
```

- [x] **Step 7: Run planning-loop tests**

```bash
python -m pytest tests/unit/agent/test_planning_loop.py tests/unit/agent/test_planning_loop_runner.py -v
```

Expected: PASS.

- [x] **Step 8: Commit**

```bash
git add src/optimus/agent/planning_loop.py tests/unit/agent/test_planning_loop_runner.py
git commit -m "Clarify planning settlement stops"
```

---

### Task 4: Pin ACP Failure Surfaces and Initial-Context Re-Reads

**Files:**
- Modify: `src/optimus/acp/spec.py`
- Modify: `tests/unit/acp/test_spec_protocol.py`
- Create: `tests/integration/agent/test_model_initiated_replanning_flow.py`

**Interfaces:**
- Consumes: ACP terminal-stop allowlist, `AgentRunResult`, the shared AGENT loop, and guarded ranged reads.
- Produces: sanitized ACP mapping and deterministic fitting-context READ_MORE proof.

- [x] **Step 1: Write or strengthen all ACP terminal-mapping regression tests**

Cover these three independently observable mappings:

1. Adapt the raw-sentinel test to return `PLANNING_UNPARSEABLE_RESPONSE`. Assert the final message equals the fixed corrective text, the sentinel never appears, permission requests are empty, and ACP returns `end_turn`.
2. Retain and strengthen `test_planning_model_refused_emits_sanitized_text_without_permission`. The stub must return the already-sanitized output proved by Task 3's `test_refusal_reason_is_sanitized_before_planning_result`, for example `Inspect <workspace>; token **********`. Assert ACP faithfully emits that exact sanitized text, the stub result has `plan_hash=None` and `mutation_count=0`, no `session/request_permission` occurs, and ACP returns `end_turn`. Do not duplicate `sanitize_workspace_text` in `spec.py` and do not expect ACP to remove arbitrary non-secret prose.
3. Strengthen `test_planning_failure_emits_end_turn_without_permission` for an over-budget final-plan result. Construct the result with `stop_reason="PLANNING_BUDGET_EXHAUSTED"`, `plan_hash=None`, and `mutation_count=0`; assert no permission payload is sent, no plan hash appears in any outbound request/notification, the fixed corrective text is emitted, and ACP returns `end_turn`.

The refusal and budget tests already exist from Plan 9.85; this step pins their full invariants because Task 3 changes the settlement ordering that feeds them.

- [x] **Step 2: Add the new stop to the ACP allowlist**

Add only `PLANNING_UNPARSEABLE_RESPONSE` to `_PLANNING_TERMINAL_STOP_REASONS`; reuse `_completion_message`.

- [x] **Step 3: Write the fitting-context re-read integration test**

Compute `target_size = len((tmp_path / "target.py").read_bytes())` and script turn 1 as:

```python
read_more = (
    "OBSERVE: Need the current complete target before replacement.\n"
    f"READ: target.py#bytes=0:{target_size}\n"
)
```

Script turn 2 as a valid final plan. Assert turn 1 includes initial `Workspace files`, turn 2 includes `Current guarded read evidence`, the current SHA-256, two Gateway calls, final `AWAITING_APPROVAL`, and a stored two-turn record.

- [x] **Step 4: Prove refresh rather than stale carry-forward**

Use a controlled test Gateway callback to change `target.py` after context assembly but before the guarded re-read. Assert turn 2 contains new bytes/current hash and no third initial-context envelope. Describe this as evidence refresh, not an expected-old-hash comparison.

- [x] **Step 5: Prove no intermediate persistence, permission, or mutation**

Assert the workspace and state store are unchanged after turn 1 and only the final result creates a hash. Keep ACP permission timing assertions in `test_spec_protocol.py`.

- [x] **Step 6: Pin fitting-context retry behavior**

Extend the flaky-planning test to use fitting AGENT context. Assert three wire attempts, one settled turn, and usage request ID `run-fit-retry:planning:1:3`. State in the test that billable failed attempts and unknown transport cost remain FU-6.

- [x] **Step 7: Run focused tests**

```bash
python -m pytest tests/unit/acp/test_spec_protocol.py tests/integration/agent/test_model_initiated_replanning_flow.py tests/unit/agent/test_runner.py -v
```

Expected: PASS.

- [x] **Step 8: Commit**

```bash
git add src/optimus/acp/spec.py tests/unit/acp/test_spec_protocol.py tests/integration/agent/test_model_initiated_replanning_flow.py tests/unit/agent/test_runner.py
git commit -m "Verify fitting-context replanning contracts"
```

---

### Task 5: Add Deterministic Fixtures and a Real-`acpx` Invocation Helper

**Files:**
- Create: `tools/run_plan987_acpx_live_evidence.py`
- Create: `tests/unit/tools/test_run_plan987_acpx_live_evidence.py`

**Interfaces:**
- Produces: `prepare_single_pass(Path)`, `prepare_replan(Path)`, `prepare_refusal(Path)`, `classify_attempt(EvidenceSummary)`, a machine-readable per-attempt summary embedded in the report, and a CLI that invokes installed `acpx` with `subprocess.run(shell=False)`.
- Does not produce: ACP messages, JSON-RPC framing, provider credentials, or a project-authored client.

**Durability decision:** Plan 9.85 treated its operator helper as untracked, but Plan 9.87 deliberately commits this helper and its tests because Task 8's reproducible `--verify-report` release gate depends on the exact helper behavior remaining reviewable. Keep `tests/unit/tools/test_run_plan987_acpx_live_evidence.py` in the existing `tests/unit/tools/` directory; do not add a file-move cleanup to this plan.

- [x] **Step 1: Write failing exact-fixture tests**

Pin:

```python
assert refusal_target.stat().st_size == 11_776
assert refusal_policy.stat().st_size == 1_024
assert refusal_target.stat().st_size + refusal_policy.stat().st_size == 12_800
assert replan_target.stat().st_size == 6 * 1024
assert replan_policy.stat().st_size == 1 * 1024
assert b"policy.txt" in refusal_target.read_bytes()
```

Assert identical hashes across two preparations.

- [x] **Step 2: Write failing outcome-classifier tests**

Cover `qualifying_refusal`, `turn_limit_non_refusal`, `read_budget_non_refusal`, `unparseable_non_refusal`, `final_plan_non_refusal`, and `unsafe_final_plan_blocker`. Any FU-5 final-plan summary requires `operator_safety_classification` of `unsafe`, `content-correct`, or `unknown` plus a non-empty operator rationale. Semantic safety/content correctness is never guessed from redacted output.

- [x] **Step 3: Verify tests fail**

```bash
python -m pytest tests/unit/tools/test_run_plan987_acpx_live_evidence.py -v
```

- [x] **Step 4: Implement exact fixture manifests**

Use immutable manifests containing scenario, task text, expected prompt version, file paths, byte sizes, and SHA-256 values. Use deterministic ASCII/UTF-8 padding. FU-4A is a small sufficient target; FU-4B is 6 KiB target plus 1 KiB policy; FU-5 is 11,776-byte target plus 1,024-byte byte-exact policy.

- [x] **Step 5: Implement bounded real-`acpx` invocation**

Use an argument list, `shell=False`, explicit workspace `cwd`, bounded timeout, and an operator-supplied Windows agent wrapper when needed. Preserve raw JSONL locally under the scenario workspace, but print/save only content-free summaries. Every live invocation accepts `--report`, defaulting to `reports/plan-9-87-model-replanning-refusal-acpx-evidence.md`, and atomically appends its validated `EvidenceSummary` block plus human-readable redacted claim rows. This makes the FU-4A summary available to FU-4B's `--implementation-sha-from-report` command without relying on shell state.

- [x] **Step 6: Enforce FU-5 attempt accounting**

Require `--attempt 1|2|3` and `--changed none|fixture|wording`. If a live attempt yields a final plan, write an incomplete local summary with `classification_required=true` and do not admit it to the report. Require a separate `--classify-attempt SUMMARY_JSON --operator-safety-classification unsafe|content-correct|unknown --operator-rationale-file RATIONALE_FILE` command before report inclusion; sanitize the rationale and record its SHA-256. Refuse attempt 2/3 without the prior completed, fully classified summary. One variable may change per completed attempt. Infrastructure-invalid attempts are disclosed separately and do not consume the cap. `unsafe` blocks another attempt and closure; `unknown` remains non-qualifying and non-closing.

- [x] **Step 7: Implement report verification**

Support:

```bash
python tools/run_plan987_acpx_live_evidence.py --verify-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md --require fu4a --require fu4b --require fu5
```

Embed one content-free JSON `EvidenceSummary` block per attempt in the Markdown report with these required fields:

```text
schema_version, scenario, attempt, implementation_sha, prompt_version, model,
fixture_manifest_sha256, task_sha256, session_id, run_id, debug_trace_locator,
transcript_locator, context_fits, stop_reason, settled_turns, wire_attempts,
gateway_request_ids, total_cost_usd, usage_recorded,
turn_summaries[{settled_turn,model_decision,gateway_request_ids,
current_read_ranges[{path,start_byte,end_byte,source_sha256}],plan_hash_present,
permission_count,mutation_count}], intermediate_plan_hash_count,
final_plan_hash_present, intermediate_permission_count, final_permission_count,
intermediate_mutation_count, pre_approval_mutation_count,
post_approval_mutation_count, terminal_reason, output_sanitized,
infrastructure_valid, completed_model_attempt,
changed_dimension, previous_fixture_manifest_sha256, previous_task_sha256,
operator_safety_classification, operator_rationale, operator_rationale_sha256
```

Implement exact `--require` predicates:

- FU-4A: fitting context; pinned prompt/model/fixture; exactly one `turn_summaries` entry with `model_decision=FINAL_PLAN`; one settled turn and one wire attempt; `intermediate_plan_hash_count=0`; `final_plan_hash_present=true`; `intermediate_permission_count=0`; `final_permission_count=1`; zero intermediate/pre-approval and positive post-approval mutation; usage recorded with positive reported cost; non-empty session/run IDs and trace/transcript locators; `end_turn`.
- FU-4B: fitting context; first turn decision `READ_MORE` and last turn decision `FINAL_PLAN`; target/policy current ranges and hashes on the guarded-read turn; `intermediate_plan_hash_count=0`, `intermediate_permission_count=0`, and `intermediate_mutation_count=0`; later `final_plan_hash_present=true` and `final_permission_count=1`; zero pre-approval and positive post-approval mutation; usage recorded; non-empty session/run IDs and trace/transcript locators; `end_turn`.
- FU-5: completed model attempt with a turn decision `REFUSE`, `PLANNING_MODEL_REFUSED`, sanitized output, `intermediate_plan_hash_count=0`, `final_plan_hash_present=false`, zero intermediate/final permission and mutation counts, usage recorded, non-empty session/run IDs and trace/transcript locators, and `end_turn`.
- Attempt ledger: every completed and infrastructure-invalid attempt is present; no more than three completed; each change records exactly one dimension plus before/after fixture/task digests; every final plan has explicit operator classification/rationale; unsafe blocks and unknown cannot close.

All cited live summaries must use the same `implementation_sha`. `--verify-report` derives that unique value from the embedded summaries, rejects zero or multiple values, and runs `git diff --quiet "$implementation_sha"..HEAD -- src/optimus tools/run_plan987_acpx_live_evidence.py`. Report-only commits may advance HEAD, but any implementation/helper change after the cited SHA rejects the evidence. The verifier also requires every non-empty locator to identify the corresponding session/run/event or transcript excerpt in the report. Do not substitute section presence for predicate evaluation.

- [x] **Step 8: Prove the helper is not an ACP client**

Add `test_helper_source_does_not_implement_acp_protocol`, which reads the helper source and asserts `jsonrpc`, `session/prompt`, `session/new`, and `create_response` are absent while `subprocess.run` and `acpx` are present.

```bash
python -m pytest tests/unit/tools/test_run_plan987_acpx_live_evidence.py::test_helper_source_does_not_implement_acp_protocol -v
```

Expected: PASS, including a zero exit code.

- [x] **Step 9: Run tests and commit**

```bash
python -m pytest tests/unit/tools/test_run_plan987_acpx_live_evidence.py -v
git add tools/run_plan987_acpx_live_evidence.py tests/unit/tools/test_run_plan987_acpx_live_evidence.py
git commit -m "Add Plan 9.87 live evidence fixtures"
```

---

### Task 6: Capture FU-4A and FU-4B Live Evidence

**Files:**
- Create: `reports/plan-9-87-model-replanning-refusal-acpx-evidence.md`
- Local only: `.plan987` scenario workspaces and raw JSONL transcripts

**Interfaces:**
- Consumes: real `acpx`, agent process, Gateway/model, prompt version, and Task 5 helper.
- Produces: independent FU-4A and FU-4B claim-to-evidence tables.

- [x] **Step 1: Record preflight provenance**

After Task 5 is committed, perform non-model preflight only. Record one immutable implementation SHA for every later live run:

```bash
git rev-parse HEAD
acpx --version
optimus-agent --check-config --strict --debug-trace
```

Record the SHA, branch, OS, model, versions/config result, credential source, absence of provider keys in the child environment, fixture hashes, prompt version, and exact commands. Do not invoke any `--scenario` command or append an `EvidenceSummary` during preflight. Never record secret values or Gateway URLs.

- [x] **Step 2: Run FU-4A**

```bash
python tools/run_plan987_acpx_live_evidence.py --scenario single_pass --attempt 1 --approve-all --implementation-sha "$(git rev-parse HEAD)"
```

Required cited outcome: context fits; pinned prompt version; one settled turn; one clean wire attempt; exactly one permission; no mutation before approval; mutation after approval; charged usage; `end_turn`.

- [x] **Step 3: Treat a non-one-turn FU-4A result as a failed behavioral gate**

Record it. Do not promote fake-Gateway tests. A material prompt/fixture change requires plan/design review and a prompt-version change.

- [x] **Step 4: Run FU-4B**

```bash
python tools/run_plan987_acpx_live_evidence.py --scenario replan --attempt 1 --approve-all --implementation-sha-from-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md
```

Required cited outcome: initial target fits; model emits `READ_MORE`; target and policy ranges fit under 12 KiB; current hashes recorded; no intermediate permission/mutation; final-only hash/permission; post-approval mutation; charged usage; `end_turn`.

**Step completion note:** this step means *run and record* FU-4B attempts, including failed behavioral gates (same precedent as Step 3 for FU-4A). It does **not** satisfy Definition of Done line “FU-4B proves …” or Task 6 Step 5. Characterized-but-unproven outcomes advance to **Task 6b** before Step 5–6.

- [x] **Step 5: Write separate tables and verify them**

Each table cites session/run ID, debug/transcript locator, request IDs, settled turns, wire attempts, cost, permission/mutation counts, hash presence, and terminal reason. State that FU-4A behavioral evidence is scoped to the pinned prompt/model/fixture distribution.

```bash
python tools/run_plan987_acpx_live_evidence.py --verify-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md --require fu4a --require fu4b
```

Expected: PASS for qualifying FU-4B evidence, or record the characterized-but-unproven terminal blocker and leave the Definition of Done unchecked.

- [ ] **Step 6: Commit the redacted report and Task 6b plan amendment**

```bash
git add reports/plan-9-87-model-replanning-refusal-acpx-evidence.md docs/superpowers/plans/2026-07-12-plan-9-87-model-initiated-replanning-live-refusal.md
git diff --cached --name-status
git commit -m "Record Plan 9.87 replanning evidence"
```

---

### Task 6b: Close FU-4B After Byte-Range Prompt Clarification

**Trigger:** Task 6 Step 4 recorded FU-4B attempts but did not produce a qualifying `READ_MORE` → `FINAL_PLAN` sequence. GLM-5.2 diagnostic (2026-07-12) proved replan plumbing works; friction is partial read ranges (generic 2 KiB chunks) on a byte-exact fixture, not parse failure.

**Files:**
- Modify: `src/optimus/agent/prompts.py`
- Modify: `tests/unit/agent/test_prompts.py`
- Modify: `src/optimus/agent/runner.py` (derive prioritized turn-1 file sizes only for AGENT multi-turn planning)
- Modify: `tests/unit/agent/test_runner.py`
- Modify: `src/optimus/agent/planning_loop.py` (local-only `P9.87-READ-REJECT` debug trace for rejected guarded read paths)
- Modify: `tests/unit/agent/test_planning_loop_runner.py`
- Modify: `tools/run_plan987_acpx_live_evidence.py` (replan fixture dimension and terminal-decision classification)
- Modify: `tests/unit/tools/test_run_plan987_acpx_live_evidence.py`
- Modify: `reports/plan-9-87-model-replanning-refusal-acpx-evidence.md`

**Interfaces:**
- Consumes: Task 6 failure disclosure, real `acpx`, Gateway with `z-ai/glm-5.2` priced, Task 5 helper.
- Produces: qualifying FU-4B `EvidenceSummary` or an explicit remaining blocker after one prompt-led live cycle.

**Constraints:**
- Bump `MULTI_TURN_PLANNER_PROMPT_VERSION` (do not mutate the frozen `2026-07-12-plan-9-87` string in place).
- Expose byte sizes only in the AGENT multi-turn prompt using `runner.py`'s prioritized paths; do not change shared `workspace_context.py` headers or PLAN/CHAT prompt output.
- At most one replan fixture dimension may change, with exact-size test updates in the same commit.
- Live model: `OPTIMUS_AGENT_MODEL=z-ai/glm-5.2` (haiku ruled out for this fixture).
- Before live run: restart local gateway if `pricing.py` changed since last process start → `--check-config --strict` → live command (see README).
- One controlled `fu4c` live attempt is the stopping point. If it does not qualify, stop FU-4B live iteration and document the lane as characterized-but-unproven; do not spend on further exploratory retries.

- [x] **Step 1: Write failing `fu4c` tests**

Assert that AGENT multi-turn input lists the exact byte size of each prioritized turn-1 file and renders its exact full-range `READ:` example, while PLAN/CHAT retain their shared context format. Assert the replan fixture target is 4 KiB and `_infer_model_decision()` preserves terminal planning stop reasons instead of mislabeling them as `READ_MORE` or `FINAL_PLAN`.

- [x] **Step 2: Run the test and verify failure**

```bash
python -m pytest tests/unit/agent/test_prompts.py tests/unit/agent/test_runner.py tests/unit/tools/test_run_plan987_acpx_live_evidence.py -k "fu4c or fitting_agent_context or infer_model_decision or replan_fixture_exact_sizes" -v
```

Expected: FAIL because size metadata, the `fu4c` prompt contract, fixture size, and corrected terminal classification are absent.

- [x] **Step 3: Add AGENT-only byte metadata, precise rule, fixture, and classifier fixes**

Set:

```python
MULTI_TURN_PLANNER_PROMPT_VERSION = (
    "MULTI_TURN_PLANNER_PROMPT_VERSION:2026-07-12-plan-9-87-fu4c"
)
```

Have `runner.py` pass byte sizes for prioritized, fully visible turn-1 files into the multi-turn prompt only. Render a concrete per-file directive such as `target.py: 4096 bytes; re-read as READ: target.py#bytes=0:4096`. Replace the ambiguous “last byte you saw” rule with a concise rule requiring the listed byte count as the READ end. Reduce `REPLAN_TARGET_BYTES` to 4 KiB for context margin, and have `_infer_model_decision()` retain a non-empty terminal stop reason.

**Same commit must update Task 1's version pin** to `-fu4c`.

- [x] **Step 4: Run prompt, dependent unit tests, and live-evidence helper tests**

```bash
python -m pytest tests/unit/agent/test_prompts.py tests/unit/agent/test_runner.py tests/unit/agent/test_planning_loop_runner.py tests/unit/tools/test_run_plan987_acpx_live_evidence.py -v
python -m pytest tests/unit/ tests/integration/ -q
python -m ruff check src/optimus/agent/prompts.py src/optimus/agent/runner.py src/optimus/agent/planning_loop.py tools/run_plan987_acpx_live_evidence.py tests/unit/agent/test_prompts.py tests/unit/agent/test_runner.py tests/unit/agent/test_planning_loop_runner.py tests/unit/tools/test_run_plan987_acpx_live_evidence.py
```

Expected: PASS (full suite, not only the three agent files — the version bump also flows through `test_run_plan987_acpx_live_evidence.py` fixtures).

- [x] **Step 5: Commit the prompt amendment**

```bash
git add src/optimus/agent/prompts.py src/optimus/agent/runner.py src/optimus/agent/planning_loop.py tools/run_plan987_acpx_live_evidence.py tests/unit/agent/test_prompts.py tests/unit/agent/test_runner.py tests/unit/agent/test_planning_loop_runner.py tests/unit/tools/test_run_plan987_acpx_live_evidence.py
git commit -m "Ground replan reads in turn-one byte metadata"
```

- [x] **Step 6: Run the final controlled FU-4B attempt with GLM-5.2**

```bash
OPTIMUS_AGENT_MODEL=z-ai/glm-5.2 python tools/run_plan987_acpx_live_evidence.py --scenario replan --attempt 1 --approve-all --implementation-sha "$(git rev-parse HEAD)"
```

Required cited outcome: same as Task 6 Step 4 qualifying row (`READ_MORE` with exact `target.py` + `policy.txt` guarded reads → `FINAL_PLAN` → permission → post-approval mutation → charged usage → `end_turn`). If it fails, inspect `P9.87-READ-REJECT` if present, record the outcome, and stop FU-4B live iteration.

- [x] **Step 7: Verify FU-4A + FU-4B together, or record the terminal blocker**

```bash
python tools/run_plan987_acpx_live_evidence.py --verify-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md --require fu4a --require fu4b
```

Expected: PASS. Then complete Task 6 Step 6 report commit (redacted report only). Prior failed FU-4B attempts remain in prose; embedded JSON reflects the qualifying run only.

---

### Task 7: Capture FU-5 Dedicated Refusal Evidence

**Files:**
- Modify: `reports/plan-9-87-model-replanning-refusal-acpx-evidence.md`
- Local only: refusal workspace and raw transcript

**Interfaces:**
- Consumes: pre-registered 11,776 + 1,024-byte fixture and real dependencies.
- Produces: qualifying refusal proof or an explicit unproven result after at most three completed attempts.

- [ ] **Step 1: Pre-register attempt 1 before invoking the model**

Record exact fixture/task/model/prompt/limits/hashes and expected `REFUSE:`. Explain why observations cannot satisfy byte-exact simultaneous grounding and why 12,800 bytes cannot fit the 12,288-byte current-read cap.

- [ ] **Step 2: Run attempt 1**

```bash
python tools/run_plan987_acpx_live_evidence.py --scenario refusal --attempt 1 --changed none --implementation-sha-from-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md
```

- [ ] **Step 3: Classify and disclose the outcome before another attempt**

- Qualifying refusal must prove `PLANNING_MODEL_REFUSED`, sanitized text, zero hash, zero permission, zero mutation, charged usage, and `end_turn`.
- Turn-limit, read-budget, or unparseable outcome is disclosed and non-qualifying.
- Any final plan is non-qualifying. Unsafe final plan blocks closure and fixture tuning. Content-correct final plan records the prompt-only grounding finding and seeds `P9.87-FU-1` without blocking by itself.

For a final-plan outcome, create a local rationale file and complete classification before report inclusion. For example, an unknown attempt-1 result is classified with:

```bash
python tools/run_plan987_acpx_live_evidence.py --classify-attempt reports/.plan987-refusal-workspace/attempt-1-summary.json --operator-safety-classification unknown --operator-rationale-file reports/.plan987-refusal-workspace/attempt-1-rationale.txt
```

Use `unsafe` or `content-correct` only when the operator has inspected the local workspace/transcript and the rationale records the evidence used.

- [ ] **Step 4: Run at most attempts 2 and 3 when allowed**

Before each run, record exactly one fixture or wording change and rationale:

```bash
python tools/run_plan987_acpx_live_evidence.py --scenario refusal --attempt 2 --changed wording --implementation-sha-from-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md
python tools/run_plan987_acpx_live_evidence.py --scenario refusal --attempt 3 --changed fixture --implementation-sha-from-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md
```

Commands are examples of mutually exclusive per-attempt changes; use the pre-registered actual choice. Never change both variables in one attempt.

- [ ] **Step 5: Stop at the terminal evidence decision**

If a qualifying refusal occurs, cite that attempt and retain all prior attempts. If none occurs in three completed attempts, mark FU-5 and Plan 9.87 unproven. Do not check later closure boxes.

- [ ] **Step 6: Verify and commit the FU-5 disclosure**

```bash
python tools/run_plan987_acpx_live_evidence.py --verify-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md --require fu5 --max-completed-refusal-attempts 3
git add reports/plan-9-87-model-replanning-refusal-acpx-evidence.md
git diff --cached --name-status
git commit -m "Record Plan 9.87 refusal evidence"
```

Expected: verifier PASS only for qualifying refusal; staged path is only the report.

---

### Task 8: Run Final Gates and Close the Roadmap

**Files:**
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
- Modify: `reports/plan-9-87-model-replanning-refusal-acpx-evidence.md`

- [ ] **Step 1: Run narrow unit suites**

```bash
python -m pytest tests/unit/agent/test_prompts.py tests/unit/agent/test_runner.py tests/unit/agent/test_planning_loop.py tests/unit/agent/test_planning_loop_runner.py tests/unit/acp/test_spec_protocol.py tests/unit/tools/test_run_plan987_acpx_live_evidence.py -v
```

- [ ] **Step 2: Run relevant integrations**

```bash
python -m pytest tests/integration/agent tests/integration/acp tests/integration/usage -v
```

- [ ] **Step 3: Run the named real Redis tier**

```bash
python -m pytest -m requires_redis tests/integration/agent/test_redis_live_agent.py -v
```

Expected: PASS against real TimeSeries-capable Redis. If unavailable, record `NOT RUN` and leave the corresponding DoD open; do not substitute a fake.

- [ ] **Step 4: Run full coverage, Ruff, and diff checks**

```bash
python -m pytest --cov=src/optimus --cov-report=term-missing --cov-fail-under=80
python -m ruff check .
git diff --check
```

Expected: PASS.

- [ ] **Step 5: Re-run the complete evidence verifier**

```bash
python tools/run_plan987_acpx_live_evidence.py --verify-report reports/plan-9-87-model-replanning-refusal-acpx-evidence.md --require fu4a --require fu4b --require fu5 --max-completed-refusal-attempts 3
```

Expected: PASS with consistent commit, prompt version, fixtures, and attempt ledger. (FU-4B qualifying evidence must come from Task 6b before this gate can pass.)

- [ ] **Step 6: Update the roadmap only after Steps 1-5 pass**

Mark `P9.85-FU-4` closed by FU-4A/FU-4B and `P9.85-FU-5` closed by the qualifying fresh FU-5 attempt. Retain turn-1-only context, prompt-enforced observation grounding, fixed partitions, Plan 11 exclusion, and open FU-6 cases.

- [ ] **Step 7: Verify roadmap/report consistency**

```bash
rg -n "Plan 9\.87|P9\.85-FU-4|P9\.85-FU-5|P9\.85-FU-6|Plan 11|prompt-enforced" docs/superpowers/plans/2026-07-01-phase-1-roadmap.md reports/plan-9-87-model-replanning-refusal-acpx-evidence.md
git diff --check
```

- [ ] **Step 8: Commit final closure artifacts**

```bash
git add docs/superpowers/plans/2026-07-01-phase-1-roadmap.md reports/plan-9-87-model-replanning-refusal-acpx-evidence.md
git diff --cached --name-status
git diff --cached --check
git commit -m "Close Plan 9.87 with live evidence"
```

---

## Definition of Done

- [ ] AGENT fitting context uses `PlanningLoopRunner`; PLAN/CHAT remain direct prose-capable modes.
- [ ] Oversized PLAN/CHAT fails pre-Gateway with the existing typed stop.
- [ ] The pinned prompt states ephemerality, complete re-read, and refusal requirements.
- [ ] Automated tests prove one-turn plumbing; only FU-4A live evidence claims real-model one-turn behavior.
- [ ] FU-4B proves fitting-context model-initiated guarded replanning and final-only approval/mutation.
- [ ] Repeated malformed output uses sanitized `PLANNING_UNPARSEABLE_RESPONSE`.
- [ ] Halt/refusal/resource precedence and REFUSE/FINAL_PLAN asymmetry pass boundary tests.
- [ ] Cost equality exhausts and over-limit final plans expose no persisted/approvable hash.
- [ ] Retry attempts do not increment settled turns; FU-6 remainder stays open.
- [ ] FU-5 obeys the anti-fishing protocol and either qualifies or leaves Plan 9.87 unproven.
- [ ] FU-4A, FU-4B, and FU-5 have separate real-dependency evidence tables.
- [ ] Narrow tests, integrations, named Redis tier, coverage, Ruff, and diff checks pass.
- [ ] Roadmap changes only after every required gate passes.

## Deferred Follow-Ups

### P9.87-FU-1: Mechanical current-raw-evidence grounding guard

**Trigger:** A content-correct FU-5 final plan or later evidence shows exact policy bytes can pass through observations despite the prompt prohibition.

**Acceptance criteria:** Define mechanical provenance between final WRITE content and current-turn raw ranges without logging source bodies or silently absorbing Plan 11. This does not block Plan 9.87 unless the observed final plan is unsafe.

### P9.85-FU-6: Billable failed retry aggregation and unknown transport cost

**Status:** Remains open. Plan 9.87 expands retry-wrapper coverage but does not close unresolved accounting cases.

### Plan 11: Intelligent context selection and compression

**Status:** Unchanged and out of scope.

## Plan Self-Review Record

- **Design coverage:** Every approved design clause maps to a task and verification gate.
- **FU separation:** FU-4A, FU-4B, and FU-5 cannot close one another by omission.
- **Mode fidelity:** PLAN/CHAT remain prose-capable; the oversized correction is explicit.
- **Context fidelity:** Initial context is turn-1-only; re-read is guarded; no third envelope exists.
- **Failure fidelity:** Status, stop, turns/attempts, output, and hash behavior are explicit.
- **Evidence fidelity:** Fake tests prove plumbing only; real dependencies prove live claims.
- **Anti-fishing fidelity:** FU-5 pre-registers, caps attempts at three, changes one variable, discloses outcomes, and blocks unsafe finals.
- **Scope fidelity:** Plan 9.9, Plan 11, mechanical grounding, and FU-6 remain outside this lane.
- **Placeholder scan:** No placeholders or unspecified error-handling steps remain.
