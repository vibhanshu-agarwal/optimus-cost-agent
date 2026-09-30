# Plan 12.1 — implementation and live evidence (Tasks 1–4)

**Date:** 2026-09-30.
**Plan:** [Plan 12.1 implementation plan](../docs/superpowers/plans/2026-09-29-plan-12-1-plan-chat-advisory-answer-implementation.md). Task 0: [Task 0 report](plan-12-1-task0-picker-and-live-proof-prerequisites.md).
**Branch / PR:** `claude/plan12.1/plan-chat-mode`, draft PR #212, base `08ec2ee`.
**Final implementation head for all Task 4 evidence:** `8b7d51e`. Its product code equals `13f7c15`; the two later commits change only the pool.
**Raw artifacts:** operator handoff kit, folders `plan12-1-impl-claude-20260930` (Tasks 1–3 and review-fix logs) and `plan12-1-task4-20260930` (Task 4). They are kept outside the repository because they contain private paths. Paths below are redacted to `<scratch-workspace>`.

## 1. Commits and CI

| Commit | Content | CI full suite (`guardrails`) |
|---|---|---|
| `1eeb8d3` | Task 0 report (docs only) | — |
| `8e936fc` | Tasks 1–3 | [success](https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/36626662420) |
| `59f3698` | Review fix: serialize mode setters per session | [success](https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/36628431287) |
| `0eeabc4` | Review fix: mode updates require a confirmed flush | [success](https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/36652675140) |
| `13f7c15` | Task 4 finding fix: Chat Gateway call under the turn directive lifecycle | [success](https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/36683277342) |
| `b563bb6` | Pool: file `P12.1-FU-1` (docs only) | cancelled, superseded by `8b7d51e` |
| `8b7d51e` | Pool: correct `P12.1-FU-1` (docs only) | [success](https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/36686844641) |
| `d846b5d` | This report, checkboxes, plan wording and README (docs only) | [success](https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/36692001280) |
| `1cc1cbd` | Final-review fix: refuse Chat with a `completion_condition` before any call | pushed with `1c797b9`; covered by that run |
| `1c797b9` | Report update for `1cc1cbd` (docs only); last head with product-code changes | [success](https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/36695370522): 4516 passed, 60 skipped, 111 deselected |

**Coverage from the `1c797b9` CI full suite** (statement coverage per changed module; the run uses `--cov=optimus --cov-branch`):

| Module | Coverage |
|---|---|
| `acp/spec.py` | 84% |
| `acp/server.py` | 90% |
| `acp/shapes.py` | 95% |
| `agent/runner.py` | 83% |
| `agent/prompts.py` | 96% |
| `agent/models.py` | 90% |
| Whole package | 87% |

In the same run, all Plan 12.1 test nodes passed with none skipped, and the golden-harness real-runner tests passed, including the internal `PLAN` "explain small function" scenario.

**Applicability of the live evidence to `1cc1cbd`.**
- **What the fix changes:** `1cc1cbd` changes only `AgentRunner.run`'s handling of a Chat request that carries a `completion_condition`. Before the fix, such a request entered the goal loop, which bypassed the Chat halt and directive gates.
- **Why the ACP evidence still stands:** standard ACP `session/prompt` never supplies `completion_condition`; only the legacy `optimus.agent.run` method can reach the goal loop. The Task 4 live evidence on `8b7d51e` therefore covers the `session/prompt` path unchanged, and no further paid calls were made.
- **How the corrected route is verified:** by regression tests (section 2) and the PR CI full suite.

**Hook disclosure:**
- Every commit skipped only `optimus-pytest-coverage` and ran every other hook.
- Docs-only commits used the standing operator rule of 2026-09-29.
- Implementation commits used an operator approval scoped to Plan 12.1, while `main` lacks child-process Known Folders test isolation.
- A local full suite was not run for that reason. The PR CI full suite on each head is the full-suite evidence.

## 2. Tasks 1–3: red, then green

All local runs followed a clear guarded-lane check. Commands used the worktree's `.venv` Python (`python -m pytest ... -q -p no:cacheprovider`).

| Step | Result |
|---|---|
| Red, Tasks 1–3 contract tests on the base | 18 failed, 1 passed |
| Red, Task 2 runner tests | 9 failed, 2 passed |
| Red, Tasks 2–3 ACP tests | 6 failed, 20 passed |
| Green, new Plan 12.1 test files | 37 passed |
| Green, `tests/unit/acp` and `tests/unit/agent` directories | 1343 passed, 20 skipped |
| Red, concurrent setters (`59f3698`) | 7 failed, 1 passed; the e2e wire-order test failed on the old code |
| Red, ambiguous send (`0eeabc4`) | 4 failed, 1 passed |
| Red, Chat directive lifecycle (`13f7c15`) | 4 failed, 5 passed |
| Green, focused set at `13f7c15` | 549 passed |
| Red, Chat with a completion condition (`1cc1cbd`) | 2 failed: 5 Gateway calls on unknown cost; a call despite a pre-cancelled turn |
| Green, focused set plus `tests/unit/loops` and the goal-loop integration test at `1cc1cbd` | 591 passed, 1 skipped |
| Ruff | clean at every commit |

**Focused set at `13f7c15`:**
- ACP units: `test_spec_protocol`, `test_shapes`, `test_plan121_chat_mode`, `test_conversation`, `test_lifecycle`, `test_stdio_ndjson`, `test_outbound_writer`, `test_outbound_errors` and `test_debug_trace_call_sites`;
- the whole `tests/unit/agent` directory;
- e2e: `test_plan121_mode_wire_order` and `test_multi_turn_conversation`.

It left out the six ACP modules that write launch-approval lock files into the real operator root. Before-and-after snapshots of the real roots showed no writes for those runs.

### Checkbox evidence map (Tasks 1–3)

Test names below are in `tests/unit/acp/test_plan121_chat_mode.py` (ACP), `tests/unit/agent/test_plan121_chat_runner.py` (runner) and `tests/e2e/acp/test_plan121_mode_wire_order.py` (e2e).

- **Task 1: schema examples and mode-snapshot proof.**
  - `test_session_new_advertises_synchronized_modes_and_mode_config_option` and `test_setter_changes_mode_once_and_sends_paired_updates_before_response` validate `NewSessionResponse`, both setter responses and every `SessionNotification` against the pinned ACP v1 schema.
  - Idempotence and atomicity: `test_repeating_the_current_mode_is_idempotent` and `test_invalid_mode_changes_are_atomic` (11 cases, `INVALID_REQUEST`).
  - Mode snapshot at admission: `test_mode_change_during_a_chat_turn_applies_to_the_next_prompt_only` and `test_mode_change_during_an_agent_turn_keeps_its_permission_request`.
  - Concurrency: `test_concurrent_setters_are_serialized_per_session`, `test_a_prompt_is_not_blocked_by_a_setter_mid_update` and the e2e `test_concurrent_setters_keep_each_response_after_its_own_paired_updates`.
  - Delivery failure: `test_a_retry_resynchronizes_the_client_after_a_failed_mode_update` and `test_an_ambiguous_mode_update_is_not_success_and_a_same_mode_retry_resends_both`.
  - `session/load` stays unadvertised: `test_initialize_still_does_not_advertise_session_load`.
  - Wire example: section 3.1.
- **Task 2: exact prompt and history assertions.**
  - Prompt and history: `test_chat_prompt_is_advisory_prose_without_directive_grammar` (no directive grammar, read-only, untrusted-data instruction) and `test_chat_prompt_renders_prior_history_once_before_the_current_question`.
  - Envelope and workspace selection: `test_chat_request_carries_the_envelope_separately_from_the_task`, `test_chat_workspace_selection_uses_history_plus_current_prompt` and `test_chat_gateway_call_is_attributed_as_an_advisory_answer` (one call, purpose `advisory_answer`).
  - Internal `PLAN` unchanged: `test_plan_mode_keeps_directive_prompt_and_read_behaviour`.
- **Task 3: wire transcript, record assertion and guardrail regression.**
  - Wire transcript: section 3.1.
  - Records: `test_chat_turns_share_the_canonical_history_with_agent_turns` (Agent → Chat → Chat → Agent carriage and records), `test_chat_failures_are_visible_non_success_turns_that_end_normally` (four failure kinds; `end_turn`, visible text, no plan, non-completed record) and `test_cancelled_chat_turn_returns_cancelled_without_a_plan_card`.
  - No mutation: `test_chat_never_executes_model_produced_directives` and `test_chat_cannot_mutate_from_hostile_prompt_workspace_or_model_text`.
  - Single-call failures: `test_chat_blank_answer_is_a_visible_failure_not_a_success`, `test_chat_gateway_error_with_reported_usage_is_a_known_cost_failure`, `test_chat_gateway_error_without_usage_is_an_unknown_cost_failure` and `test_chat_over_budget_answer_is_terminated_as_budget_exhausted`.
  - Turn directive lifecycle: the four `TurnControl` tests added in `13f7c15`.
  - No goal loop for Chat: `test_chat_with_a_completion_condition_is_rejected_without_a_gateway_call` and `test_cancelled_chat_with_a_completion_condition_makes_no_gateway_call` (`1cc1cbd`).
  - Guardrail regression: Plan 2's existing enforcement and guardrail suites are unchanged and pass in the CI full suite on every head in section 1.

**Disclosure:** the one directory-wide run (1343 passed) wrote four empty lock files to the real root. Four more came from an isolation probe. All eight are left untouched, pending a separate cleanup decision.

## 3. Task 4: live evidence on `8b7d51e`

**Install and trust state:**
- **Installed build:** the `optimus-agent` uv tool, built from `8b7d51e` with a clean tree. All 135 `optimus` `.py` files are byte-identical to the source.
- **Rollback path:** the prior install (`c69fd48`) is backed up with SHA-256 manifests, and a rollback script is recorded.
- **Workspace approval:** durable and current. Every launch in this section was `AUTHORIZED`, with `OPTIMUS_AGENT_MODEL` propagated.
- **Readiness:** a no-cost check (TCP connect to `127.0.0.1:8765`, and no "did not become ready" line) passed before calls 4–6.

**Clients:** `acpx` 0.12.0, independently authored. Zed 1.21.0 (`33c95853ed2b6956f339733c63a8220964ecbeb6`).

### 3.1 `acpx` (plan Task 4, step 1)

**Invocation:** `acpx --agent "optimus-agent --workspace-root . --debug-trace" --cwd <scratch-workspace> --deny-all --format json`, followed by `sessions new`, `set`/`set-mode` and `prompt`. Every command exited 0.

**How `acpx` runs these commands:**
- Each command starts a fresh agent process, because Optimus does not advertise `session/load`.
- Before a prompt, `acpx` replays its saved mode on the new session.

| Plan item | Evidence |
|---|---|
| `initialize`; new-session `modes`, `configOptions`, Agent default | Call-6 transcript. `session/new` returns `currentModeId: "agent"` and one `mode` select option with `currentValue: "agent"`. |
| Change to Chat through `session/set_config_option` | `acpx set mode chat`. The agent trace shows `session/set_config_option`, two `session/update`, then the response. The response `configOptions` has `currentValue: "chat"`. |
| Both ordered updates | Call-6 transcript: `current_mode_update` (`chat`), then `config_option_update` (`currentValue: "chat"`), then `{}`. Order is also pinned by the unit and e2e wire-order tests. |
| Chat question, answer, update, stop | Call 6: "What does calc.py do?" returns one `agent_message_chunk` ("`calc.py` defines one function, `add(a, b)`, which returns the result of adding `a` and `b`.") and `stopReason: "end_turn"`. No plan update. |
| Change back to Agent through `session/set_mode` | `acpx set-mode agent`. The agent trace shows `session/set_mode` (`acpx`'s replay of Chat), then `session/set_mode` to Agent, each with two `session/update` before its response. No model call. |
| No Chat mutation | Telemetry for every Chat turn: `mutation_count: 0`, `tool_names: []`. |
| Cost fields | Call 6: `total_cost_usd` `0.000681675`, settlement `cost_complete: true`, `provider_attempt_started: true`. |

**Wire example** (call 6; descriptions shortened, cwd redacted):

```json
{"jsonrpc":"2.0","id":1,"method":"session/new","params":{"cwd":"<scratch-workspace>","mcpServers":[]}}
{"jsonrpc":"2.0","id":1,"result":{"sessionId":"session-564f8c70ce4242bd8c73625cd0822fee","modes":{"currentModeId":"agent","availableModes":[{"id":"agent","name":"Agent","description":"…"},{"id":"chat","name":"Chat","description":"…"}]},"configOptions":[{"id":"mode","name":"Mode","category":"mode","type":"select","currentValue":"agent","options":[{"value":"agent","name":"Agent","description":"…"},{"value":"chat","name":"Chat","description":"…"}]}]}}
{"jsonrpc":"2.0","id":2,"method":"session/set_mode","params":{"sessionId":"session-564f8c70ce4242bd8c73625cd0822fee","modeId":"chat"}}
{"jsonrpc":"2.0","method":"session/update","params":{"sessionId":"session-564f8c70ce4242bd8c73625cd0822fee","update":{"sessionUpdate":"current_mode_update","currentModeId":"chat"}}}
{"jsonrpc":"2.0","method":"session/update","params":{"sessionId":"session-564f8c70ce4242bd8c73625cd0822fee","update":{"sessionUpdate":"config_option_update","configOptions":[{"id":"mode","name":"Mode","category":"mode","type":"select","currentValue":"chat","options":["…"]}]}}}
{"jsonrpc":"2.0","id":2,"result":{}}
{"jsonrpc":"2.0","id":3,"method":"session/prompt","params":{"sessionId":"session-564f8c70ce4242bd8c73625cd0822fee","prompt":[{"type":"text","text":"What does calc.py do?"}]}}
{"jsonrpc":"2.0","method":"session/update","params":{"sessionId":"session-564f8c70ce4242bd8c73625cd0822fee","update":{"sessionUpdate":"agent_message_chunk","content":{"type":"text","text":"`calc.py` defines one function, `add(a, b)`, which returns the result of adding `a` and `b`."}}}}
{"jsonrpc":"2.0","id":3,"result":{"stopReason":"end_turn"}}
```

### 3.2 Zed (plan Task 4, step 2)

The operator typed the prompts and selected controls. Claude verified each step from the Optimus debug trace and telemetry before the next paid call.

| Plan item | Evidence |
|---|---|
| Chat chosen in an actual Optimus thread | New Optimus thread. The trace shows `session/new`, then `session/set_config_option` (two updates, then the response). The picker shows Chat. |
| Greeting | "Hello" → "Hello! How can I help?" (call 4, `CHAT_ONLY`, $0.00067155). |
| Read-only workspace question | "What is README.md for?" → "README.md identifies this as a scratch workspace and says it was used for the Plan 12 context-floor Zed check on 2026-09-29. It doesn't give further setup or usage instructions." This matches the file (call 5, `CHAT_ONLY`, $0.000720425). |
| No plan card, no mutation | Operator screenshot shows prose answers only. Telemetry: `mutation_count: 0`, no tools. |
| Switch to Agent and confirm the selected state | New thread (unpaid): `session/set_config_option` to Chat, then `session/set_config_option` back to Agent, each with two updates before the response. The operator screenshot shows the picker on Agent. |
| Zed version, trust state | Zed 1.21.0. The workspace approval was current, and every launch was `AUTHORIZED`. |
| Gateway request IDs and cost | Cost: as above. `gateway_request_id` is `None` on the ACP path (see section 4). |

### 3.3 Paid-call ledger

Authority: operator, 2026-09-29. Luna (`openai/gpt-6-luna`) through the Gateway, at most $0.05 per prompt, at most six calls.

| # | Client | Build | Outcome | Gateway-reported cost |
|---|---|---|---|---|
| 1 | `acpx` | `0eeabc4` | answered | $0.000679675 |
| 2–3 | Zed | `0eeabc4` | the local Gateway missed its readiness deadline; no provider reached; `CHAT_GATEWAY_COST_UNKNOWN` (`P12.1-FU-1`) | $0 each |
| 4–5 | Zed | `8b7d51e` | answered | $0.00067155; $0.000720425 |
| 6 | `acpx` | `8b7d51e` | answered | $0.000681675 |

Six of six calls were used, for $0.002753325 in total. No paid Agent prompt was sent. Calls 1–3 are supplemental evidence from a superseded build. The Task 4 acceptance evidence is calls 4–6 plus the unpaid mode switches, all on `8b7d51e`.

### 3.4 Narrow checks (plan Task 4, step 3)

- **Ran:** the e2e checks for this slice (`test_plan121_mode_wire_order`, `test_multi_turn_conversation`) use the real `serve_ndjson` process path.
- **Not run separately:** no `requires_gateway` pytest tier. The live `acpx` and Zed calls through the real local Gateway are the real-Gateway evidence, and the paid-call allowance is exhausted.

## 4. Findings and limitations

- **`P12.1-FU-1` (filed, Open).** On one Zed launch, the agent's TCP readiness probe for the local Gateway did not succeed within 10 seconds. The agent stopped the child and kept serving without a Gateway. The cause is not diagnosed.
- **Fixed in this PR (`13f7c15`).** The Chat Gateway call ran outside the turn's GATEWAY directive lifecycle. This misreported settlement cost and let a cancelled turn still make the call.
- **`gateway_request_id` is `None` on the ACP path.** Request IDs cannot be recorded. The closest existing owner is `P11.26-CAND-2-TELEMETRY-CONTRACT`.
- **MCP permission requests at `session/new`.** Zed passes its configured MCP servers, and Optimus sent five `session/request_permission` requests during `session/new`. Zed answered them with errors, and the session proceeded. This is the known Zed live-check finding #6, outside Plan 12.1.
- **Zed saves the picked mode.** Zed persists the last picked mode as `agent_servers.optimus.default_config_options` in its settings and applies it to new threads. The temporary settings were restored byte-identical after the evidence runs.
- **Fixed in this PR (`1cc1cbd`).** A Chat request with a `completion_condition` entered the goal loop. That repeated an unknown-cost failure five times and bypassed cancellation. It is now refused before any call.
- **Goal loop and turn control (observation outside Plan 12.1).** The goal loop's iteration runner calls `_run_once` without the turn's halt check or directive control, for Agent and internal `PLAN` requests too. This predates Plan 12.1. Standard ACP `session/prompt` never supplies `completion_condition`; the legacy `optimus.agent.run` method can reach the goal loop. Filed as `P12.1-FU-2`.
- **Settlement `conversation_commit`.** It reports `not_committed` for every turn, Agent and Chat alike. This predates Plan 12.1 and is not changed here.
- **Screenshot capture.** After a Windows update on 2026-09-30, computer-use screenshots show the Zed window blank. The Zed screenshots are the operator's own.
- **Plan wording.** Computer use holds Zed at click-only access, so typing in Zed stays operator-only.

## 5. Codex review record

Codex reviewed read-only. For the final P1 it also ran its own fake-Gateway probe; it made no paid calls and no edits.

| Reviewed head | Finding | Resolution |
|---|---|---|
| `8e936fc` | Changes requested: two concurrent mode setters could interleave between notification awaits | `59f3698` per-session setter lock and retry resynchronization |
| `59f3698` | An `AMBIGUOUS` send was treated as delivered, so a same-mode retry could not resynchronize | `0eeabc4` confirmed-flush requirement for mode updates |
| `0eeabc4` | Interim review approved; full-suite CI green on the exact head | Install hold lifted for Task 4 |
| `13f7c15` | Code review approved (Chat call under the turn directive lifecycle) | — |
| `P12.1-FU-1` draft | Wording corrected to the failed TCP readiness probe and the agent's `stop()` call | `8b7d51e` |
| Task 4 evidence | Successful answers accepted; unpaid mode-switch evidence requested | Provided on `8b7d51e` (section 3) |
| `d846b5d` | P1: Chat with a `completion_condition` entered the goal loop | `1cc1cbd` refusal before any call |
| `1c797b9` | Implementation review passes. Zero-call rejection independently verified, including a pre-cancelled turn; ordinary Chat still makes one attempt and keeps the unknown-cost result. Reachability wording corrected; `P12.1-FU-2` requested | This report and the pool |

**Codex's other final-review conclusions:**
- Plan 2 enforcement and internal `PLAN` behaviour are preserved.
- The evidence supports the ACP capability.
- The sandbox context floor remains a separate port. That port must reconcile final-text delivery and conversation commit with this slice.

## 6. Definition of Done: claim → evidence → review

| Claim (plan) | Evidence | Review |
|---|---|---|
| One canonical ACP mode, both projections synchronized, Agent default, snapshot-safe under concurrency | Section 2 Task 1 tests (pinned-schema validation of both setters, responses and updates; admission snapshot; serialized setters; retry resynchronization); section 3.1 `acpx` transcript and unpaid switches; section 3.2 Zed; Task 0 report | Codex: `0eeabc4` approved, `1c797b9` passes |
| Chat gives grounded prose without directive grammar or plan updates | Section 2 Task 2 prompt tests; ACP tests asserting no `plan` update; section 3.2 Zed README answer matching the file; section 3.1 `calc.py` answer | Codex: live evidence accepted |
| Internal `PLAN` keeps its directive prompt and read behaviour | `test_plan_mode_keeps_directive_prompt_and_read_behaviour`; golden-harness real-runner tests in the `1c797b9` CI run | Codex: preserved |
| Non-AGENT history uses the existing cap and record | `test_chat_turns_share_the_canonical_history_with_agent_turns` (canonical order and records); `test_chat_prompt_renders_prior_history_once_before_the_current_question` (no duplicate current turn); `test_multi_turn_conversation` e2e. Admission and commit use the shared path that precedes the mode branch. No Chat-specific cap-refusal test was added; the existing cap tests cover that shared path. | Codex: `1c797b9` passes |
| Chat cannot mutate; Agent guard unchanged | `test_chat_never_executes_model_produced_directives`, `test_chat_cannot_mutate_from_hostile_prompt_workspace_or_model_text`; Plan 2 and guardrail suites in CI; live telemetry `mutation_count: 0` on every Chat turn | Codex: Plan 2 enforcement preserved |
| `$0.05` per-prompt cost and terminal results truthful and attributable to Chat | `test_chat_gateway_call_is_attributed_as_an_advisory_answer` (purpose, cost); budget, unknown-cost, Gateway-failure and blank-answer tests; directive-lifecycle and goal-loop refusal tests; `test_mode_setters_are_approved_diagnostic_method_categories`; section 3.3 ledger. Limitation: `gateway_request_id` is `None` on the ACP path, so live request IDs cannot be reported. | Codex: ledger verified |
| Delivery reviewable without disturbing sandbox tests | Guarded-lane check before every local run and hook commit; focused runs with before/after real-root snapshots; Ruff; PR CI full suite on each head (section 1); Codex reviews (section 5) | Codex: `1c797b9` passes |
