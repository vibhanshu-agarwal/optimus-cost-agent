# Plan 12.1: Plan/Chat advisory-answer implementation

**Date/base:** 2026-09-29; `origin/main` `81ec05f`.

**Goal:** Deliver a selectable, read-only ACP Chat mode with reliable prose answers and full unsummarised conversation history, while preserving Agent as the default and reusing Plan 2's enforcement.

**Architecture:** One per-session `ExecutionMode` is exposed through synchronized ACP `modes` and a mode-category select `configOptions` entry; the existing non-AGENT runner gets a mode-specific prompt and canonical conversation envelope; Chat completion is an answer update, not a plan. The same admission/commit record and cost contract apply to both modes.

**Design:** [Plan 12.1 design spec](../specs/2026-09-29-plan-12-1-plan-chat-advisory-answer-design.md).

**Backlog owners:** `P12-FU-1` owns advisory answers; `P11.25-FU-1` alone owns non-AGENT conversation carriage. Both are promoted to this plan upon its publication on `main`.

**Roles:** Claude reviews these documents, implements on a separate branch from `main`, and obtains an independent Codex implementation review. The operator decides PR and merge. No implementation is authorized merely by this draft.

## Global constraints

- Build core Optimus behavior with Context Engine absent. Do not import sandbox context-floor code or work in the Optimus sandbox. The later floor port must reconcile `src/optimus/acp/spec.py` admission/commit and the `ConversationState` record against this slice.
- Reuse Plan 2's `ExecutionMode`, permission denials, `MutationGuard`, and `assert_mutation_allowed()` unchanged. Agent remains the default. No new side-effect path, approval bypass, or alternate Chat guard.
- Use the pinned ACP v1 schema in `tests/fixtures/acp/acp-v1-schema.json`. Do not advertise `session/load`, add Context Engine options, or close `P11.25-FU-2` or `P9.8-FU-5`.
- Implement by red-then-green focused tests, then independent `acpx` and live Zed proof. Every finished checkbox requires its named evidence. Before **any** local pytest run (focused or full) or commit with hooks, verify both lane predicates: no `run_main5_guarded_suite` process is active, and the newest `main5-*` guarded-run folder containing `before.json` also contains `result.json`. If either fails, wait; do not start local tests or a normal hook run. Under the standing operator rule dated 2026-09-29, docs-only commits skip only `optimus-pytest-coverage`, run every other hook, disclose the skip in the commit message, and rely on PR CI for the full suite. That standing rule does not authorize a hook skip on implementation commits. Because `main` lacks Known Folders isolation, a local full suite also requires an uncontended lane and isolation of the real `%LOCALAPPDATA%\optimus-cost-agent\locks` path; otherwise use PR CI.
- Preserve the golden harness's internal `ExecutionMode.PLAN` directive prompt and read behavior. Only `CHAT` gets the new advisory prompt and read-directive bypass. Do not advertise `PLAN` in ACP.
- Do not modify frozen/archived records. Before sign-off, audit the pool, roadmap, README and any other live current-state claim that this change affects. Review and delivery remain separate from operator PR/merge approval.

## Review focus

Claude should challenge the one-state/two-projection ACP contract, schema shapes and paired-update ordering; the mode snapshot under concurrent prompts; the boundary between Chat answers and internal `PLAN` directives/reads; whether the existing `ConversationState` can commit an answer without a plan; Chat single-call failure paths; and all paths that could execute a model-produced directive in Chat. A safety-path mismatch or failure of the revised contract in installed Zed requires a reviewed successor design before implementation proceeds.

## Prerequisites

| Category and prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|
| Code/state: Plan 2 enforcement, ACP sessions, non-AGENT runner, and canonical conversation record exist at `81ec05f` | yes | Implementer verifies base | N/A; extending the missing advisory path is the work of this plan |
| Code/state: installed Zed displays the mode-category config option usefully | yes | Operator observation; Claude accepted and requested this revision | Zed 1.21.0 rendered the reference agent's mode config option; classic-modes-only rendering remains unverified, so Plan 12.1 mirrors both surfaces |
| Services: a reachable Optimus Gateway and model for live answer proof | unknown | Operator owns local service state | Merely unauthorized if available but not started; genuinely hard if external service unavailable. Task 0 distinguishes |
| Services: Redis or other live dependency required by the selected real ACP launch configuration | unknown | Operator owns local service state; Claude checks launch path | Merely unauthorized if available but not started; genuinely hard if unavailable. Task 0 identifies the exact dependency |
| Tooling: installed Zed version and independently authored `acpx` binary are usable | yes for inventory; live Optimus use remains unproved | Operator owns machine state; Claude inventories | Zed 1.21.0 and `acpx` 0.12.0 were inventoried. The earlier Optimus `Loading...` state was traced to `session/load` waiting on MCP permission requests; Task 4 uses a new thread |
| Credentials/authority: only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` available for live proof | unknown | Operator | Merely unauthorized if credentials exist but are not released; external dependency if none exist. No provider key is placed in Optimus |
| Human interaction: trusted Zed workspace, agent selection, and visible Chat answer | unknown | Operator owns GUI action; Claude records outcome | Merely unauthorized when a manual click/trust ceremony is needed; Task 0 records the exact action |
| Cost: one or more paid Gateway calls for `acpx`/Zed live proof under the existing `$0.05` per-prompt contract | unknown | Operator | Merely unauthorized until paid-call authority and budget are known; Task 0 establishes this before a call |
| Validation lane: every local pytest run/commit hook can be scheduled after the two guarded-lane predicates pass; full suite also needs lock-path isolation, or PR CI | unknown | Operator owns lane schedule; Claude checks | Merely unauthorized if a lane is busy; wait for focused runs and hooks, use PR CI for the full suite where appropriate, and do not interrupt the sandbox run |

## Task 0 — Establish external proof and picker behavior

**Files:** evidence report under `reports/` chosen with the reviewer; no product code. The 2026-09-29 operator-owned Zed observation settled the picker mechanism: Zed 1.21.0 rendered the independently authored `claude-acp` agent's separate Mode, Model, Effort and Fast controls, and the probe showed that the agent advertised both classic `modes` and `configOptions`. Zed's single Mode picker came from the mode-category config option; classic-modes-only rendering was not established. The Optimus `Loading...` trace was a separate `session/load`/MCP-permission wait, so later proof uses a new thread. This plan therefore mirrors Agent/Chat through both protocol surfaces as specified in the design.

**Remaining before paid live proof:** record the repository-safe evidence summary, Gateway/Redis readiness, credentials and paid-call authority, trusted-workspace action, and the two guarded-lane predicates. Do not copy private paths, credentials, or raw operator artifacts into the repository. Typing into Zed and selecting its controls remain operator-only. Task 4 still requires the implemented Optimus agent and independent `acpx`; the reference-agent picker observation alone is not Definition-of-Done evidence. If the revised dual-surface contract is unusable in installed Zed, stop and ask Codex to revise the design rather than silently reducing it to one mechanism.

**Acceptance:** A dated repository-safe evidence artifact records the exact Zed build and Optimus trace finding, observed controls, reference-agent response shape, live-proof prerequisites, paid-call disposition, and the accepted dual-surface decision. Unknown live prerequisites become yes/no with an owner and next action.

- [ ] Task 0 records the accepted picker finding and settles the remaining live-proof prerequisites without secrets.

## Task 1 — ACP session mode contract

**Files:** `src/optimus/acp/spec.py`, ACP session/update builders as needed, `tests/unit/acp/test_spec_protocol.py`, `tests/unit/acp/test_shapes.py`, and focused mode tests near them.

1. **Red:** tests assert `session/new` advertises synchronized classic `modes` and exactly one select config option with `id: mode`, `category: mode`, `currentValue: agent`, and Agent/Chat values. Parameterize changes through `session/set_mode` and `session/set_config_option`: each sets Chat, emits `current_mode_update` then `config_option_update` with the full synchronized option set before its response, and changes canonical state once. Repeating the current value succeeds without duplicate updates; the classic method returns its empty success object and the config method returns the full current `configOptions`. Reject bad mode values, unknown config IDs, boolean/type mismatch, malformed parameters and unknown sessions without mutation or either update. Block a Chat turn inside the runner, change to Agent through one setter, and assert both updates and the response arrive while the turn remains blocked. Release it: the turn ends as Chat with an answer chunk and no plan update; the next prompt is Agent. Mirror this with the other setter during an Agent turn and prove that its pending permission request is neither cancelled nor bypassed. Schema-shape tests validate `session/new`, both method responses, `current_mode_update`, and `config_option_update` against the pinned fixture. Confirm the tests fail on `81ec05f` for the expected missing behavior.
2. **Green:** add one canonical mode field and project it through both ACP surfaces using existing error/dispatch/writer conventions. Implement both setters through one validation-and-update path. On a real change, commit the state once, send `current_mode_update`, send full-set `config_option_update`, then return the method-specific response. Snapshot mode at prompt admission; the runner request, update/completion branch, permission path and conversation commit use that value without re-reading `session.execution_mode`. Answer either setter without awaiting an active turn. Keep `session/load` absent from capabilities and method dispatch.
3. **Verify:** run `uv run pytest tests/unit/acp/test_spec_protocol.py tests/unit/acp/test_shapes.py -q` and any new focused mode test file; record command, exit status, and selected JSON wire examples. Review that Agent's default and existing permission/approval behavior remain unchanged.

**Acceptance:** An ACP client can select and observe Chat through either protocol surface without waiting for or changing an already admitted turn; both advertised projections remain synchronized; paired updates precede either setter response in the specified order; invalid requests are atomic.

- [ ] Task 1 red and green commands, schema examples, and mode-snapshot proof are recorded.

## Task 2 — Non-AGENT history and advisory prompt

**Files:** `src/optimus/agent/models.py`, `src/optimus/agent/prompts.py`, `src/optimus/agent/runner.py`, `src/optimus/acp/spec.py`; `tests/unit/agent/test_prompts.py`, `tests/unit/agent/test_runner.py`, `tests/unit/agent/test_golden.py`, `tests/unit/acp/test_conversation.py`.

1. **Red:** demonstrate that Chat currently receives directive grammar and no prior-turn envelope. Tests require `build_agent_planner_input` to accept/render the existing canonical envelope as prior untrusted conversation, omit directive grammar for `CHAT` only, preserve it and `READ` behavior for internal `PLAN`, and include the current prompt once. Add hostile workspace/history text cases. Include a multi-turn Agent→Chat→Chat→Agent test showing chronological turns and the same 512 KiB admission/bytes/4 estimate with no strategy engine. A follow-up reference to an earlier file must drive Chat workspace selection using the same history-plus-current-prompt text as Agent, while the model input contains the current prompt only once.
2. **Green:** compute `conversation.planner_envelope()` once at the ACP `_planner_task` seam. Agent retains its current envelope-inside-task form; Chat gets the same string in an optional frozen `AgentRunRequest.conversation_envelope` field and the current prompt in `task`. Extend the existing builder and Chat call site; use the shared history plus current prompt for Chat workspace-file selection. Select advisory instructions by `ExecutionMode.CHAT` only. Keep workspace framing as untrusted data. Chat bypasses `_execute_read_directives`; `PLAN` retains it. Use Gateway metadata `purpose: advisory_answer` for Chat, preserving the run/session/request ID, usage/cost attribution, and one-call `$0.05` budget handling. Preserve `agent_plan` purpose for existing Agent/Plan calls.
3. **Verify:** after the lane check, run `uv run pytest tests/unit/agent/test_prompts.py tests/unit/agent/test_runner.py tests/unit/acp/test_conversation.py tests/unit/agent/test_golden.py -q`. Inspect the exact constructed Chat input to confirm the current user turn is not duplicated and no directive grammar appears. Assert the golden `PLAN` tasks still use required `file_reader`/`web_search` behavior and the versioned directive prompt. Verify a partial workspace context yields a qualified answer contract, not an asserted complete inventory.

**Acceptance:** The Chat prompt can answer ordinary questions and greetings in prose based on available workspace context; its history is the same canonical bounded history as Agent; it cannot turn a model-produced `READ`/write/shell string into an executed tool call. Internal `PLAN` remains directive/read compatible.

- [ ] Task 2 red and green commands and the exact prompt/history assertions are recorded.

## Task 3 — Answer delivery, settlement, and safety

**Files:** `src/optimus/acp/spec.py`, `src/optimus/acp/server.py`, `src/optimus/agent/runner.py`, `tests/unit/acp/test_spec_protocol.py`, `tests/unit/acp/test_conversation.py`, `tests/unit/agent/test_runner.py`, existing guardrail tests.

1. **Red:** assert a successful Chat turn yields an actual prose `agent_message_chunk` under the existing `final_text` terminal lease after `seal_final_delivery`, `stopReason: end_turn`, no `PROVISIONAL_PLAN` or `completed_plan` send, no approval request, zero mutation/tool side-effect calls, and one committed record with empty plan, answer completion, and `EffectState.NONE`. On the **single-call Chat path specifically**, inject a Gateway exception, unknown cost, `BUDGET_EXHAUSTED`, and blank output; each must produce a visible corrective message, a non-success record and ACP `end_turn`, not `Turn completed.` or content-policy `refusal`. Actual cancellation returns `cancelled`. Cover over-cap admission under its existing refusal contract, both in-flight mode-switch directions through the two setters, and mutation attempts in user prompt, workspace text, and model output. Assert Chat Gateway metadata purpose and bounded telemetry method labels for both `session/set_mode` and `session/set_config_option`.
2. **Green:** branch ACP result and completion updates by the admitted turn's mode. Preserve final-delivery leases and settlement order. For Chat, emit the answer as `final_text` on success and no plan messages; store the answer rather than `Turn completed.`. Map Chat terminal failures to visible corrective text and `end_turn`; handle the single-call Gateway exception and unknown-cost cases explicitly. Do not apply that Chat mapping to Agent/Plan or claim to fix Zed refusal rendering generally. Suppress read-directive execution for Chat only, preserve it for `PLAN`, and keep the guard and Agent approval path unchanged. Add both mode-setting methods to `src/optimus/acp/server.py`'s bounded method labels; leave structured `_meta` to `P11.25-FU-2`.
3. **Verify:** run `uv run pytest tests/unit/acp/test_spec_protocol.py tests/unit/acp/test_conversation.py tests/unit/agent/test_runner.py tests/unit/agent/test_planning_loop_runner.py -q` after focused red/green runs, then inspect the wire transcript and conversation record. Run the existing guardrail subset identified by `rg --files tests/unit | rg 'guardrail|permission|mutation'` to detect regression; record exact commands/results. A failed or cancelled turn must not acquire a success-shaped Chat record.

**Acceptance:** The user sees the model's answer in Chat and never a plan card for that turn; a hostile Chat request cannot mutate; Agent remains default and guarded.

- [ ] Task 3 red and green commands, wire transcript, record assertion, and guardrail regression results are recorded.

## Task 4 — Independent ACP and live Zed evidence

**Files:** a dated evidence report in `reports/`, ACP transcript/log artifacts under the repository's evidence policy, and any focused E2E/golden test updates. Use an independently authored `acpx` client for ACP-protocol evidence; a project-authored client/fixture cannot replace it.

1. Run `acpx` against the real Optimus process with only the Gateway URL/key locally available. Capture initialize; new-session `modes`, `configOptions` and Agent default; a change to Chat through `session/set_config_option`; both ordered updates; Chat question/answer/update/stop; a change back to Agent through `session/set_mode`; and absence of Chat mutation. Validate schema, projection synchronization and cost fields without logging secrets. Record the exact `acpx` version, invocation, exit status, and artifact paths.
2. With the operator typing and selecting controls in installed Zed, choose Chat in an actual Optimus thread and ask a greeting and one read-only workspace question whose answer the supplied context can support. Observe the rendered answer, no plan card or mutation, then switch to Agent and confirm the selected state. Record Zed version, workspace trust state, screenshot/log or operator-witnessed observation, Gateway request IDs/cost, and any limitations. Do not claim success from the Task 0 fixture alone.
3. Run narrow E2E/golden checks using real dependencies for their named tier. Require real Gateway for `requires_gateway` and real process plus `acpx` for ACP live proof; fakes stay in unit tests.

**Acceptance:** The real independent client and Zed both demonstrate selectable Chat and a useful read-only answer. If a prerequisite is unavailable, mark this task unrun/blocked with its named owner; do not substitute a fake or claim Definition of Done.

- [ ] Task 4 includes independently authored `acpx` and installed-Zed artifacts tied to the same implementation commit.

## Task 5 — Validation, document freshness, and review

**Files:** this plan's checkboxes/evidence links, the consolidated pool, the Phase 1 roadmap, and any README/current-state statement affected by delivery; no frozen or archived files.

1. Check both guarded-lane predicates before every local pytest run and commit with hooks, including the focused runs in Tasks 1–3. Run focused tests, coverage for affected safety modules, and Ruff only in an idle lane; record exact result and any unrun tier. For a local full suite, additionally establish isolation of the real Known Folders lock path, or use PR CI. A busy-lane hook skip requires the operator authority described under Global constraints. Do not start a competing `main` suite. A CI full-suite result is evidence for that run only; a platform-shaped failure requires the specified alternate-OS reproduction.
2. Audit the live docs for statements now made stale by implementation. Keep pool `P12-FU-1` and `P11.25-FU-1` promoted but **not closed** until independent evidence and acceptance warrant closure. Preserve the separate statuses of `P11.25-FU-2`, `P9.8-FU-5`, and `P11-FU-1`.
3. Claude presents the exact diff, tests, `acpx` transcript, Zed observation, cost and remaining risks to Codex. Codex independently reviews against this design, Plan 2 enforcement, and the sandbox floor integration seam. Operator approval is required for PR/merge.

**Acceptance:** Each Definition-of-Done claim below maps to a real named artifact and reviewer finding. No test is described as passed if skipped or unrun.

- [ ] Task 5 records focused validation, Ruff, full-suite lane/CI result, doc freshness audit, and Codex review before any delivery claim.

## Definition of Done and evidence map

| Claim | Required evidence |
|---|---|
| ACP mode has one canonical value, both protocol projections stay synchronized, Agent is default, and turns are snapshot-safe under concurrency | Pinned-schema tests for both setters/responses/updates plus `acpx` transcript and Task 0/Task 4 Zed observations |
| Chat gives grounded prose without directive grammar or plan updates | Prompt-input focused tests, wire update tests, and real Zed answer |
| Internal `PLAN` retains its directive prompt and read behavior | Existing runner/golden test results and focused regression assertions |
| Non-AGENT history uses the existing cap and record | Multi-turn focused tests showing canonical order, admission, commit, and no duplicate current turn |
| Chat cannot mutate; Agent guard is unchanged | Adversarial unit/golden cases, guardrail regression tests, and independent ACP observation |
| `$0.05` per-prompt cost and terminal results remain truthful and attributable to Chat | Gateway usage assertions, Chat `purpose`/method-label tests, single-call budget/unknown-cost/Gateway-failure/blank-output tests, and live request-ID/cost report |
| Delivery is reviewable without disturbing sandbox tests | Focused test/coverage/Ruff results, independent review, and idle-lane proof or PR CI for full suite |

## Explicit exceptions

| Outside this plan | Sole owner / destination |
|---|---|
| Context Engine compaction, hybrid, sliding window and picker | Broader Plan 12 context lane; `P9.8-FU-3` and strategy design |
| Persisted mode on `session/load` or any resume implementation | `P11-FU-1` |
| Structured ACP stop-reason metadata | `P11.25-FU-2` |
| Zed refusal-rendering correction | `P9.8-FU-5` |
| Chat read-on-request | Optional under `P12-FU-1`; no deferred obligation is created. Register a new Plan 12 pool item before scheduling it if requested later |
| Sandbox context-floor port | Separate port from sandbox tag with explicit seam reconciliation |

**Estimate:** The original 3–4 working-day estimate is optimistic after identifying the in-flight mode-switch and single-call failure paths. Allow 4–6 working days for implementation if Task 0 confirms Zed/`acpx`/Gateway readiness, then 1–2 working days for live evidence and review; prerequisite recovery may add time. Read-on-request is deferred; adding it later is estimated at 1–2 days and requires a revised plan. These are planning estimates, not a completion claim.
