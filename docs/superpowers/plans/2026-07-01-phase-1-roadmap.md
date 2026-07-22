# Phase 1 Implementation Roadmap

This roadmap preserves the current decomposition derived from the authoritative PDF docs so future work can continue even if this chat context is unavailable.

The PDFs under `docs/*.pdf` remain authoritative. This file is a planning companion, not a replacement for the HLD, LLD, Guardrails Strategy, Roadmap, or Test Strategy.

## Roadmap Rules

- Keep each implementation plan sized to roughly 2-3 weeks of human development effort.
- Use Spec-Driven Development for architectural changes.
- Use TDD for implementation: write the failing test, watch it fail, implement the minimum code, then refactor.
- Keep local runtime credentials limited to `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`.
- Do not introduce local Tavily, OpenAI, OpenRouter, GLM, LangSmith, or provider keys.
- If HLD, LLD, and Test Strategy conflict, stop and resolve the conflict before coding.

## Cross-Cutting: Context Window Optimization & Intelligent Selection

Context Window Optimization - with Intelligent Selection as the primary control plane and Intelligent Pruning as one named strategy inside it - is core Phase 1 architecture, not an optional later-phase optimization. It governs how evidence, tool output, and conversation state get selected, packed, compacted, and evicted across the plans below, and it is tracked here so it stays visible even though it is not yet scheduled as its own plan.

**Canonical source:** `docs/context-window-optimization-strategy.md` is the standalone, senior-architect-approved canonical design note for this initiative. It stays standalone - intentionally separate from the HLD, LLD, and Test Strategy PDFs - until gates, traces, and ablations are defined and calibrated. See "PDF fold-in" below.

**Placeholder targets stay placeholders.** Values such as the >= 15% fully-loaded cost savings target, the "no material regression" threshold, latency/cache-hit baselines, and cooldown windows are calibration items, not release gates. Do not wire them into Test Strategy or the release-gate runner as pass/fail thresholds until they are calibrated on Optimus eval runs.

**How the existing plans carry this initiative:**
- Plan 7 owns the cost-attribution prerequisite: every prompt block, retrieval/compression/summarization/reranking step, and model call must be attributable by strategy, stage, `run_id`/`session_id`, token count, `cost_usd`, `cache_hit`, model, and provider. Without this, the selection layer's cost gates are not measurable.
- Plan 8 (extended by Plan 8.5) owns leaving room in the fitness-gate and release-gate machinery for the offline promotion gates, the baseline/ablation plan, and context-regret checks defined in the design note - without binding them in as enforced gates yet.
- Plans 4, 5, 6, 6.5, and 9 supply the context-selection inputs this initiative packs and scores, but do not implement selection themselves: Plan 4 provides evidence-ledger and tool-output-trust signals, Plans 5, 6, and 6.5 provide the guardrail, MCP, runtime-trust, and config-trust signals that feed freshness/trust gating, and Plan 9 provides loop state and skill-selection signals for on-demand procedural context.

**PDF fold-in:** the HLD, LLD, and Test Strategy PDFs remain authoritative and untouched by this initiative for now. Only the accepted policy folds into those PDFs, and only after calibration baselines, trace fields, ablation criteria, and promotion gates are accepted.

## Plan 1: Core Runtime, ACP Transport, and Test Harness

**Plan file:** `docs/superpowers/plans/2026-07-01-core-runtime-acp-transport.md`

**User story:** As a local ACP client, I can send framed JSON-RPC requests and receive deterministic responses.

**Source anchors:**
- LLD sections covering ACP framing, stream transport, task lifecycle, and Sprint 1 Transport & Protocol gates.
- Test Strategy Schema Validation Tests and Phase 1 Release Gates.

**Notes:** Do not cite Test Strategy section 5 for transport/framing ownership. Section 5 is Mode and State Transition Tests. The real transport/framing ownership appears in the schema validation and release-gate transport material.

**Known follow-up:** Plan 1 is a transport foundation slice, not the full Sprint 1 transport sign-off. Continuous stdio serving, the 50-burst fragmented-header simulation, Task Manager semantics beyond dispatcher-level duplicate tracking, max declared body-size enforcement that maps oversized bodies to `-32600 Invalid Request`, and any buffered-reader treatment for zero-length frames with trailing bytes should be handled in a transport hardening task before the final release gate.

## Plan 2: Mode, State Machine, and Mutation Guard

**User story:** As a user, I can trust Plan/Chat mode to be advisory-only and Agent mode to mutate only after approval.

**Source anchors:**
- Architecture section 7.
- LLD section 4A.
- Test Strategy section 5.

**Expected deliverables:**
- `ExecutionMode`, generation scope classification, lifecycle states, transition validator, `AwaitingApproval`, `MutationGuard`, and `assert_mutation_allowed()`.
- Tests proving Plan/Chat cannot mutate, Agent mode must pass through approval, invalid transitions fail closed, and mutation tools check the primitive before I/O.

## Plan 3: Gateway-Only Configuration and Gateway Client

**User story:** As a developer, I run locally with only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; all provider credentials stay gateway-side.

**Source anchors:**
- Architecture sections 5A and 11.
- LLD section 0A.
- Test Strategy section 7.

**Expected deliverables:**
- Gateway settings model, trusted origin validation, production-mode rules, authorization header construction, provider-key rejection, `/v1/responses` request shape, and typed gateway error handling.
- Tests proving local provider keys are rejected or ignored according to mode, gateway origins are validated, and no local provider key is needed for a mocked full run.

## Plan 4: Tool Policy and Evidence Acquisition

**User story:** As the agent runtime, I authorize tool calls deterministically and record external evidence with gateway usage.

**Source anchors:**
- Architecture section 8.
- LLD section 9 and Evidence Ledger material.
- Test Strategy section 6.

**Expected deliverables:**
- `ToolInvocationPolicy`, reason codes, local-first evidence policy, web search/extract request wrappers, URL provenance checks, per-run call caps, and `EvidenceLedgerEntry`.
- Tests proving web search requires a trigger, extract URLs must come from approved search results, call caps are atomic, and gateway usage propagates into evidence records.

## Plan 5: Permission Engine, Pre-Tool Guard, and Shell Safety

**User story:** As a project owner, I can enforce deny-before-allow permissions and block unsafe shell/file/network operations before execution.

**Source anchors:**
- Guardrails Strategy sections 2-4.
- LLD section 12A.
- Test Strategy sections 14.1-14.3.

**Expected deliverables:**
- `PermissionPolicy`, `PermissionDecision`, `PreToolGuard`, impact classification, and local deterministic `CommandSafetyValidator`.
- Tests for deny precedence, mode short-circuiting, human approval holds, destructive commands, pipe-to-shell patterns, env/credential reads, ANSI controls, insecure transport, network egress, and Unicode/homoglyph confusion.

## Plan 6: Prompt-Injection, MCP Trust, and CI Guardrail Parity

**User story:** As a maintainer, I can prevent poisoned repo/MCP metadata from widening trust and verify guardrails locally and in CI.

**Source anchors:**
- Guardrails Strategy sections 5-6.
- LLD section 12B.
- Test Strategy sections 14.4-14.7.

**Expected deliverables:**
- Prompt-injection fixture handling, MCP autoload denial, trusted MCP registration flow, pre-commit rule parity, CI clean-environment re-checks, and bypass tests.
- Tests proving poisoned config cannot escalate permissions, cloned repo MCP servers do not auto-load, `--no-verify`/unsafe env/network patterns are caught by gates, and local/CI checks exercise the same rule set.

## Plan 6.5: Guardrail Hardening and MCP Runtime Trust Wiring

**Plan file:** `docs/superpowers/plans/2026-07-04-plan-6-5-guardrail-hardening-mcp-runtime-trust.md`

**User story:** As a maintainer, I can close Plan 6 review/CI gaps before usage accounting depends on stable guardrail and MCP trust events.

**Source anchors:**
- Plan 6 review follow-ups and CI findings.
- Guardrails Strategy sections 5-6.
- LLD sections 12A and 12B.
- Test Strategy sections 14.1-14.7.

**Expected deliverables:**
- Missing-path fail-closed handling for MCP manifest scans, env-aware git bypass hardening, maintained Unicode confusable detection, and runtime MCP trust wiring.
- Tests proving unreadable MCP manifests block cleanly, `GIT_CONFIG_*` and alias/hook bypasses are caught at the shell/pre-tool boundary, Unicode spoofing detection is shared by config and command scanners, and MCP runtime calls cannot bypass the trust registry.

## Plan 7: Usage Accounting, Evidence Ledger, and Observability

**Plan file:** `docs/superpowers/plans/2026-07-04-usage-accounting-evidence-ledger-observability.md`

**User story:** As a FinOps reviewer, I can reconcile every billable call from gateway response to persisted usage and evidence records.

**Source anchors:**
- Architecture sections 4, 5, and 12.
- LLD sections 9E, 10, 10A, and 11A.
- Test Strategy section 8.

**Expected deliverables:**
- `GatewayUsage`, `ProviderUsage`, usage accounting service, Redis HASH/TimeSeries adapter boundaries, JSONL telemetry event schema, and reconciliation methods.
- Tests proving `gateway_request_id`, provider, cache_hit, billing_units, cost_usd, native_unit, optimus_credits_debited, model/version, run_id, and session_id are recorded from gateway response fields and not estimated post-hoc.

## Plan 8: Retry, Fitness Gates, Golden Tasks, and Release Gate

**Plan file:** `docs/superpowers/plans/2026-07-05-retry-fitness-gates-golden-tasks-release-gate.md`

**User story:** As a release owner, I can prove the system fails closed, retries boundedly, passes coverage, and completes one-key release gates.

**Source anchors:**
- Architecture sections 3, 6, 9, and 12.
- LLD section 11.
- Test Strategy sections 9, 12, and 13.

**Expected deliverables:**
- Failure classification, retry/backoff policy, max 3 transient retries, composite gate results, golden task fixtures, and release-gate runner.
- Tests proving permanent failures do not retry, transient failures cap at 3 attempts, gate failures leave no partial writes, golden tasks validate expected mode/tools/cost band/final state, and full release gate runs with only Optimus credentials.

## Plan 8.5: Release-Gate Hardening and Golden-Harness Wiring

**Plan file:** `docs/superpowers/plans/2026-07-06-plan-8-5-release-gate-hardening.md`

**User story:** As a release owner, I can trust that shadow-workspace promotion matches exactly what the fitness gates evaluated, that the one-key scanner covers every local artifact that could leak a provider key, and that the Phase 1 release-gate CLI can actually reach a real PASS end-to-end.

**Source anchors:**
- PR #21 code review (2026-07-06).
- Plan 8 plan file "Notes for reviewers" and Deferred Follow-Ups (P8-FU-1 deletion propagation, unchecked golden-harness CLI and staging Gateway E2E items).
- Test Strategy sections 9, 12, and 13 (same anchors as Plan 8 — this closes gaps against existing requirements, it does not add new ones).

**Expected deliverables** (each maps to a review finding; keep traceability during implementation):

1. **Shadow-workspace deletion propagation** — `changed_paths()` / `promote_shadow_changes()` must detect and promote file deletions (present in `workspace_root`, absent from `shadow_root`), preserving rollback-on-partial-promotion-failure. Closes P8-FU-1 and Critical Issue #1: gates can evaluate a shadow tree missing a file while promotion never removes it from the real workspace, so promoted state can diverge from what passed.
2. **One-key scanner default wiring** — the one-key gate in `build_phase1_release_gates()` currently scans only `.env`, `.env.local`, and `pyproject.toml`, while `scan_local_credentials()` supports arbitrary `config_paths`. Either extend the default scan surface to every local artifact the release runner produces or reads, or explicitly document and test the accepted scan boundary so the gap is a reviewed decision, not an implicit one.
3. **Golden-harness wiring for the default CLI** — `tools/run_phase1_release_gate.py` fails by default (`golden task harness not configured`) because no harness is injected. Provide either a deterministic local harness that runs `phase1_golden_tasks.json` against the real runtime with only Optimus credentials, or a documented CLI flag/config path to supply one, plus an explicit decision on whether staging Gateway E2E is required for Sprint 1 sign-off or stays a documented manual step. Closes Plan 8 PR unchecked test-plan items.
4. **Release-gate command timeout** — `CommandGate` / `_run_command` has no `subprocess` timeout; a hung test run would hang the release gate indefinitely. Add a bounded timeout with a failed-gate result on expiry.
5. **Shadow-workspace copy cost** — `ShadowWorkspace` recreates a full `copytree` on every gated-retry attempt, ignoring only `.git`, `__pycache__`, `.pytest_cache`. Add a broader/configurable ignore list (`.venv`, `node_modules`, build/dist output, etc.) and/or reuse one shadow copy across retry attempts instead of recopying from scratch each time.
6. **Fitness-gate telemetry cost accuracy** — `GatedRetryRunner._emit_fitness_gate` hardcodes `cost_usd=Decimal("0")` instead of the candidate's actual cost, misreporting gate-attempt cost in telemetry used for Plan 7 reconciliation.
7. **Promotion failure test-hook removal** — `fail_after_promoted_paths` on `ShadowWorkspaceMutationRunner` is a test-only fault-injection parameter on a production-callable signature. Remove it from the runtime API and retain deterministic mid-promotion rollback coverage through a test-only seam (injected copier, promotion strategy, or private test helper). Closes P8-FU-3.
8. **(Optional, lower priority)** Refactor `classify_failure`'s in-function deferred import of `CompositeGateError` into a shared low-level exceptions module, removing the `retry`↔`gates` circular-import workaround.

**Tests proving:**
- A shadow candidate that deletes a file promotes the deletion and still rolls back cleanly on a later promotion failure.
- The one-key gate fails when a provider key is resolvable from any in-scope local artifact, not only the three hardcoded paths.
- The default `tools/run_phase1_release_gate.py` run reaches a real PASS/FAIL against golden-task fixtures without manual harness injection.
- A release-gate command exceeding its timeout is reported as a failed gate rather than hanging.
- Fitness-gate telemetry events carry non-placeholder cost figures.
- Rollback-on-partial-promotion-failure tests remain equivalent or stronger without `fail_after_promoted_paths` on production APIs.

## Plan 9: Bounded Goal Loops and Curated Workflow Skills

**User story:** As an agent operator, I can bound long-running goal loops and load only trusted workflow skills without widening permissions.

**Source anchors:**
- Guardrails Strategy sections 7-8 and 10-11.
- LLD sections 12C and 12D.
- Test Strategy sections 14.8-14.9.

**Priority note:** This is explicit Phase 1 architectural support but appears lower priority than the release-gate foundation because the LLD Sprint 1 checklist and Test Strategy release gates do not foreground it. Keep it explicit so it is not silently dropped.

**Expected deliverables:**
- `GoalLoopController`, `IterationState`, `CompletionEvaluator`, `ProgressLedger`, `LoopBudgetPolicy`, `SkillRegistry`, `SkillManifest`, `SkillTrustPolicy`, and `SkillInvocationPolicy`.
- Tests proving loop stops on completion, max iterations, budget exhaustion, wall-clock limit, repeated failure, and human halt; skill loading only occurs for matched trusted skills and cannot widen the tool surface or override deny rules.

## Plan 9.5: Agent Orchestration and End-to-End Coding Workflow

**Plan file:** `docs/superpowers/plans/2026-07-07-agent-orchestration-end-to-end-coding-workflow.md`

**User story:** As an operator, I can give the local Optimus Agent a normal coding task and receive a planned, approved, guarded, validated, and cost-attributed outcome.

**Expected deliverables:**
- `AgentRunner`, `AgentRunRequest`, `AgentRunResult`, guarded tool adapters, `optimus.agent.run`, and `AgentGoldenTaskHarness`.
- Tests proving Plan/Chat advisory-only behavior, Agent-mode approval before mutation, guarded tool use, bounded-loop stop integration, skill selection, real golden harness execution, and one-key release evidence.

**Completion plan:** `docs/superpowers/plans/2026-07-07-plan-9-5-working-acp-agent-completion.md`

**Mandatory completion deliverables:**
- Spawnable Agent Client Protocol stdio process for IDE integration through `python -m optimus.acp` and `optimus-agent`.
- Agent Client Protocol conformance for newline-delimited JSON-RPC: client-to-agent requests `initialize`, `session/new`, and `session/prompt`; client-to-agent notification `session/cancel`; plus agent-to-client `session/update` and `session/request_permission`.
- Production `AcpStreamServer` wiring with real `GatewayClient`, `AgentRunner`, Redis-backed agent state, configured `workspace_root`, and shared `PreToolGuard`.
- Framed `optimus.agent.run` integration tests through `AcpStreamServer.handle_one()`, including the two-call approval flow.
- Redis-backed persisted plan replay so approved Agent-mode execution uses the exact stored plan text instead of re-planning through a live Gateway.
- Versioned directive prompt contract, typed unparseable-plan failure, and checked-in redacted smoke transcript for real Gateway evidence.
- Operator-friendly startup messages for missing Optimus credentials or missing, unsafe, or unreachable Redis configuration.
- README launch instructions and smoke checks that prove a running agent deliverable, not only importable code.

**Status:** Plan 9.5 is the build plan and is complete when the completion plan's Tasks 0-8 land with their own DoD tests green. Plan 9.5 completion does NOT constitute working-agent sign-off; that gate is owned by Plan 9.6. The smoke-transcript and live-evidence expectations formerly attached to Plan 9.5 have transferred to Plan 9.6.

## Plan 9.6: Live Verification and LLD Alignment

**Plan file:** `docs/superpowers/plans/2026-07-07-plan-9-6-live-verification-and-lld-alignment.md`

**User story:** As the operator, I can verify on my own machine — against a real TimeSeries-capable Redis, real Optimus Gateway credentials, and a real spawned ACP stdio process — that the agent Plan 9.5 built actually works, before anything is signed off.

**Expected deliverables:**
- Pre-flight checks (`preflight.py`) shared by `--check-config [--strict]`, pytest fixtures, `tools/verify_live_agent.py`, and the release gate: credential presence, Redis PING, RedisTimeSeries capability probe, gateway auth probe, workspace writability — all failing closed with operator action messages.
- Live test tiers with registered markers: `requires_redis` (live state-store, telemetry, bootstrap, and server-stream tests — no Redis fakes), `requires_gateway` (real model calls, cost-capped), and `e2e` (spawned `python -m optimus.acp` subprocess over real ndjson pipes).
- LLD v2.38 §10 conformance: live TS.CREATE/TS.ALTER retention tests, `run:{run_id}:metadata` hash contract tests, `redis.asyncio` shared-pool migration, and `RedisTelemetryAdapter` wired into production bootstrap.
- Committed evidence: `reports/plan-9-6-e2e-acp-transcript.json`, the `verify_live_agent` transcript, the Zed HITL session artifact, and the recorded Task L10 plan-text governance decision.

**Status:** Complete (2026-07-11). The active execution checklist records all 8/8 claim-to-evidence
rows and Phases A-F complete. Phase D alignment/evidence merged through PR #40
(`8aa9776411e6f433463c1493b118435520fc6f3c`); final Phase F sign-off merged through PR #42
(`3ac2f914e14dcf62045375faae5c85908e73c075`). The Phase 1 working-agent gate passed, so this
Plan 11 prerequisite is no longer open.

### Plan 9.6 closure — complete

The real-IDE HITL row closed through Plan 9.75's conformant ACP approval/completion flow and
`reports/plan-9-75-zed-hitl-runtime-evidence.md`. Subprocess, live Redis/Gateway, operator-only,
manual PATH/keychain, and post-merge Zed evidence are recorded in
`docs/superpowers/plans/2026-07-10-plan-9-6-live-signoff-execution.md` and its linked reports. The
operator/IDE launch path remains standardized on `uv tool install --editable .`.

## Plan 9.7: Local Dev Infra Auto-Start and Keychain-Based Setup

**Plan file:** `docs/superpowers/plans/2026-07-08-plan-9-7-local-dev-infra-autostart-and-setup.md`

**User story:** As an operator, I run `optimus-agent` and it ensures its own local dependencies
(Redis via Docker, the local Optimus Gateway process) are up, instead of me hand-editing two
`.env` files and starting each dependency manually in separate shells first.

**Expected deliverables:**
- `local_gateway_secrets.py`: precedence-chain secret resolution (env var → `.env.gateway` →
  Windows keychain via `keyring`) and an `optimus-agent --setup` one-time interactive wizard.
- `local_infra.py`: `apply_local_defaults()`, `ensure_local_redis()` (Docker auto-start/reuse),
  `ensure_local_gateway()` (spawn/track the gateway child process, torn down when `optimus-agent`
  exits, never left as an orphaned secret-holding background process).
- `--no-auto-start` opt-out flag; `.env`/`.env.gateway` retained as a transitional fallback.

**Status:** Merged to `main` (2026-07-09, PR #32). The complete Windows operator walkthrough
(global PATH install, keychain-only `--setup`, zero `OPTIMUS_*` shell variables, auto-start, and a
real planning call) is recorded in `reports/plan-9-7-manual-e2e-evidence.md`. The formerly deferred
IDE turn completed through Plan 9.75. Windows-only scope remains; Linux/WSL keyring-backend support
is deferred. This lane stays orthogonal to Plan 9.6 live-verification scope.

## Plan 9.75 (Complete)

**Plan:** Zed HITL ACP conformance — plan `entries`, permission `toolCall`, approval handling, and
visible completion.

**Plan file:**
`docs/superpowers/plans/2026-07-09-plan-9-75-zed-hitl-acp-toolcall-permission.md`.
Its **Verified defects** section is the authoritative protocol-shape record.

**Status:** Complete (2026-07-10). PR #36 merged at
`4fe353bb21ff3a39914e5cf84979a4494c54e25b`. Runtime and post-fix Zed evidence is in
`reports/plan-9-75-zed-hitl-runtime-evidence.md`; the original diagnosis is retained in
`reports/plan-9-75-zed-hitl-defect-notes.md`. PR #40 later aligned Phase D operator verification to
the post-#36 shapes, and PR #42 closed the parent Plan 9.6 sign-off gate.

**Separate client-stability custody:** Plan 9.8 later raised `P9.8-FU-5` for a Zed 1.10.2 panic
after correctly rendering the ambiguous-refusal text. That is not a regression or reopened item in
this completed lane; it is owned by the standalone tracked backlog entry below and must not be
folded into Plan 11.

## Plan 9.8: Task-Aware Workspace Context for Planning

**Plan file:** `docs/superpowers/plans/2026-07-10-plan-9-8-task-aware-workspace-context.md`

**User story:** As an operator, when I ask the agent to change an explicitly referenced file, the
planner receives that file's content even when task-blind workspace filler would otherwise exhaust
the context budget.

**Status:** Implemented and live-verified 2026-07-11. Evidence:
[`reports/plan-9-8-task-aware-context-evidence.md`](../../../reports/plan-9-8-task-aware-context-evidence.md).

Plan 9.8 guarantees context inclusion for exact relative paths and unique basenames and visibly
rejects ambiguous/oversized required references. It does not provide multi-turn replanning or
Plan 11 intelligent selection and does not prove mutation tasks generally.

**Known limitation (P9.8-FU-5):** On Zed 1.10.2, the ambiguous-refusal corrective text can flash and
then panic the client (`range end index 3 out of range for slice of length 2`). Agent-side refusal
contract and independent `acpx` durable UI remain proven; durable Zed stay-up on that path is
deferred, not claimed. Sole custody is the standalone tracked backlog entry below; this work must
not be folded into Plan 11 or the completed Plan 9.75 lane.

**P9.8-FU-6 (substantively resolved, no discrete closing commit):** the acceptance criteria —
a documented operator/pre-GUI evidence path uses independently authored `acpx` exclusively, and
hand-rolled Plan 9.8 harnesses are removed or clearly marked non-evidence — are met in practice.
`tools/run_plan98_live_evidence.py`, the hand-rolled harness named in this follow-up's original
trigger, no longer exists in the repository; every live-evidence tool added since
(`tools/run_plan987_acpx_live_evidence.py`, `tools/run_plan988_fu4b_live_evidence.py`, and Plan
9.96/9.98's real-`acpx` capture tooling) drives real `acpx` exclusively, and "use real `acpx`, never
a hand-rolled ACP client fake" has been the enforced integration-evidence policy across every plan
since. Unlike other closed follow-ups in this document, this resolution happened gradually as
adopted practice across Plans 9.87, 9.88, 9.96, and 9.98 rather than through one dedicated PR, so
there is no single commit to cite; recorded here as the closure this roadmap was missing.

## Plan 9.85: Multi-Turn Read-Observe-Replan Workflow

**Raised:** Deferred from Plan 9.8 as `P9.8-FU-1` (2026-07-10 draft); formalized as its own
tracked roadmap entry 2026-07-11 during Plan 9.8 evidence review, closing a gap where the plan
document named a candidate plan number that was never added to the roadmap.

**User story:** As the agent runtime, when a required task spans files whose complete priority
blocks exceed the workspace-context budget, or the model needs READ evidence before it can safely
form a WRITE, I run bounded READ -> observe -> replan iterations instead of either silently
truncating required context or failing closed on every multi-file task.

**Status:** Implemented and live-verified 2026-07-12 for the oversized-required-context trigger.
Evidence: [`reports/plan-9-85-multi-turn-acpx-evidence.md`](../../../reports/plan-9-85-multi-turn-acpx-evidence.md).

Plan 9.85 adapts the existing `GoalLoopController` with a bounded, turn-capped READ -> observe ->
replan iteration; enforces the 4 KiB/12 KiB observation/current-read evidence partition fail-closed
with no silent truncation; charges and records every Gateway wire attempt (including retries)
against `max_cost_usd`; and exposes only the final settled plan for ACP approval, hashing, and
persistence. Real `acpx` 0.12.0 evidence proves a live multi-turn success path (settled turns
progressing to a final plan, exactly one permission request, post-approval mutation gated on that
approval, `end_turn`) and a live turn-limit terminal failure (`PLANNING_TURN_LIMIT_EXHAUSTED`, zero
permission requests, zero mutation, sanitized corrective text, `end_turn`).

**Deferred (`P9.85-FU-4`, `P9.85-FU-5`) -> Plan 9.87:** model-initiated replanning when Plan 9.8's
single-pass context already fits, and a live model-emitted `REFUSE:` demonstration as dedicated
Plan 9.85 closure evidence, are closed with recorded deferrals rather than silently claimed. See
Plan 9.87 below. (A live `REFUSE:` was independently observed during Plan 9.85 evidence-gathering
as a supplementary artifact and is credited to Plan 9.87's scope, not claimed as Plan 9.85 proof.)

**Known limitations (retained, not claimed live-proven beyond this scope):**

- Fixed 4 KiB/12 KiB observation-vs-current-read partition; no intelligent compression (Plan 11).
- Raw evidence is visible for one turn only; earlier evidence carries forward as untrusted
  observations with path/range/hash provenance, never silently re-read as if complete.
- Superseded/wrong plan-hash rejection (`PLAN_NOT_FOUND_OR_EXPIRED`) is proven by unit and ACP
  tests, not live `acpx` hash injection: the ACP wire protocol never accepts a client-supplied plan
  hash for approval replay (`spec.py` always re-uses the server's own just-settled hash), so there
  is no live wire-level surface to inject a stale hash against.
- `P9.85-FU-6`: `RetryController` wraps every settled-turn Gateway call; aggregating usage from a
  billable failure that aborts a retry sequence (as opposed to a cost-free transient failure)
  remains open.
- `P9.85-FU-7`: ACP debug-trace redaction (`redact_for_telemetry` applied in `acp_debug_log`) is a
  brute-force, unconditional fix landed ahead of this closure; a deliberate-access design
  (session/time-scoped opt-out for legitimate raw-trace debugging, plus a broader logging-surface
  audit) is owned by Plan 9.95, scheduled after Plan 9.9.

## Plan 9.87 (Closed): Model-Initiated Replanning and Live Refusal Evidence

**Raised:** Deferred from Plan 9.85 as `P9.85-FU-4` and `P9.85-FU-5` when closing the
oversized-required-context workflow.

**Initial scope:**
- Let a model enter the bounded guarded READ_MORE workflow when Plan 9.8 context fits but is
  insufficient for a safe WRITE, without imposing multi-turn cost on tasks that settle single-pass.
- Produce real `acpx` evidence that the live model emits `REFUSE:` and that ACP surfaces
  `PLANNING_MODEL_REFUSED` with sanitized text, zero plan hash, zero permission requests, zero
  mutation, and `end_turn`.

**Status:** Closed. FU-4A and FU-5 are proven with verified real-dependency evidence. FU-4B is
**accepted-open** (exhausted, not qualifying) under Plan 9.88 Task 8 Outcome B — ceremony HEAD
`fec114b7fc79da35ea399f4d66e22e776e6b76a3`, operator `vibhanshu-agarwal`, timestamp
`2026-07-14T08:13:56Z`; pair-plus-exhaustion gate PASS; `--require fu4b` correctly FAIL.
Accepted-open is not qualifying FU-4B evidence. This planning-loop lane remains separate from
Plan 9.9 packaging/credential diagnostics and from Plan 11 intelligent selection/compression —
do not fold this scope into either.

## Plan 9.88 (Closed): FU-4B Evidence Remediation and Plan 9.87 Closure

**Raised:** 2026-07-13 from Plan 9.87's documented FU-4B characterization. This is a dedicated
follow-up lane, not a reopening of the frozen Plan 9.87 capture driver.

**Initial scope:**
- Use a new FU-4B `acpx` capture helper with task wording that explicitly names `policy.txt`,
  reusing only safe, read-only machinery from the frozen Plan 9.87 helper.
- Pre-register a maximum of three completed model attempts. Each later attempt changes exactly one
  dimension (`wording`, `fixture`, or `model`); a model change retains fixture/task digests, records
  the prior model, uses the normal model-resolution path rather than a hardcoded model, and requires
  a priced model plus a Gateway restart and strict preflight. Disclose infrastructure-invalid runs
  without counting them.
- Extend only the post-capture verifier so the selected FU-4B claim watches `src/optimus` and the
  new helper; retain the existing FU-4A/FU-5 verifier semantics and watched paths unchanged.
- If a qualifying FU-4B capture succeeds, run the full FU-4A/FU-4B/FU-5 closure gate. If the cap
  exhausts, require contemporaneous operator sign-off before an honest Plan 9.87 amendment changes
  the closure command to FU-4A/FU-5 and records FU-4B as an accepted-open limitation; never make
  the FU-4B verifier pass vacuously.

**Sequencing guard-rail:** `main` must stay frozen on `src/optimus/**` and
`tools/run_plan987_acpx_live_evidence.py` until Plan 9.88 records the Plan 9.87 closure gate.
Doc-only merges are safe; any change to either watched path before that ceremony would permanently
invalidate the spent FU-5 evidence. Plan 9.88 must complete this closure decision before Plan 9.9
starts.

**Status:** Closed under Outcome B (exhausted ledger + contemporaneous accepted-open). Ceremony
HEAD `fec114b7fc79da35ea399f4d66e22e776e6b76a3`; disposition recorded in
`reports/plan-9-87-model-replanning-refusal-acpx-evidence.md`. Plan 9.88 carries forward
`P9.87-FU-1` (raw-evidence grounding guard, unresolved) and `P9.85-FU-6` (billable retry
accounting, unresolved) from Plan 9.87, and adds `P9.88-FU-2` (ledger digest specification)
and `P9.88-FU-3` (frozen-code read-range telemetry misattribution) — see Plan 9.88's Deferred
Follow-Ups. No `P9.88-FU-1` (unsafe-final follow-up) was created — terminal disposition was
exhaustion, not unsafe.

## Plan 9.9 (Implemented and Live-Verified): Operator Packaging and Credential Diagnostics

**Raised:** 2026-07-11 while closing Plan 9.7 review follow-ups during Plan 9.8 review.

**User story:** As a Windows operator, I get an actionable diagnostic when provider identity and
provider key resolve from incompatible configuration layers, and `optimus-agent` finds its project
resources correctly from both editable and non-editable tool installations.

**Initial scope (exactly these two deferred Plan 9.7 seeds):**

- Cross-layer provider/key mismatch diagnostics: `resolve_provider_secrets` currently resolves the
  provider name and provider API key independently through env -> `.env.gateway` -> keyring. An
  env-overridden provider can therefore be paired with a keyring key for a different provider,
  spawning the local gateway and surfacing only a confusing upstream 401 in
  `reports/local-gateway.log`. Plan 9.9 must warn or fail closed at the `ensure_local_gateway`
  call site without logging either key.
- Non-editable-install project-root discovery: `Path(__file__).parents[3]` in
  `src/optimus/acp/__main__.py` and the same pattern in `src/optimus/acp/debug_trace.py` can resolve
  the installed package tree rather than the repository/project root. That can skip
  `.env.gateway` discovery and place gateway/debug logs under the wrong tree. Plan 9.9 must define
  and test an explicit resource/config/log-root contract for editable and non-editable installs.

**Status:** Implemented and live-verified. Implementation plan approved by the reviewer agent and
operator on 2026-07-14
(`docs/superpowers/plans/2026-07-14-plan-9-9-operator-packaging-and-credential-diagnostics.md`);
implementation SHA `f120a5afde39e3b3a8a405211ae71653b6e75665`, evidence report SHA
`cde9cb9d22c32d0d0fe05b019543d6b1b5ba78a5`. Real `acpx` packaging evidence:
`reports/plan-9-9-operator-packaging-evidence.md`.

Plan 9.9 established and live-verified the non-editable install contract. Future operator and
Plan 9.8 regression runs use `uv tool install . --reinstall`; the historical Plan 9.8 evidence
remains unchanged.

`P9.9-FU-1` (workspace-influenced agent launch environment) is deliberately deferred, not
implemented here. Its sole current custody line is under Plan 9.96 below.

## Plan 9.95 (Implemented): Usage, Telemetry, and Evidence-Tooling Correctness

**Raised:** 2026-07-14 as the custody entry for open deferred follow-ups. The operator approved
the three-lane split on 2026-07-14; the detailed Plan 9.95 implementation plan is
`docs/superpowers/plans/2026-07-14-plan-9-95-usage-telemetry-evidence-tooling-correctness.md`
was approved by the reviewer-agent and operator on 2026-07-14. Implemented 2026-07-15 on branch
`agent/kiro/plan-9-95-usage-telemetry-evidence`; implementation SHA
`41a9cddddbacad766d8a432b7129a18d8976b54a`; evidence in
`reports/plan-9-95-usage-telemetry-evidence.md`.

- `P9.85-FU-6` — billable failed-retry aggregation / unknown transport cost — **closed**.
- `P9.88-FU-2` — ledger digest specification and verifier helper — **closed**.
- `P9.88-FU-3` — read-range telemetry misattribution in `planning_loop.py` — **closed**.

**Custody transfer record (trace only, not ownership):**

- `P9.85-FU-7` moved from Plan 9.95 to Plan 9.96.
- `P9.9-FU-1` moved from Plan 9.95 to Plan 9.96.
- `P9.87-FU-1` moved from Plan 9.95 to Plan 9.97.

FU-4B accepted-open is deliberately not in this entry: it is a closed disposition under the Plan
9.88 ceremony, not a TODO. **Status:** Implemented; `P9.85-FU-6`, `P9.88-FU-2`, and `P9.88-FU-3`
closed with evidence. Remaining deferred follow-ups owned by Plans 9.96 and 9.97.

## Plan 9.96 (Planning Approved; Implementation Not Started): Operator-Controlled Debug and Launch Trust

**Raised:** 2026-07-14 by the approved Plan 9.95 lane split.

**Foundation:** This lane builds on the landed Plan 9.9 implementation commit
`f120a5afde39e3b3a8a405211ae71653b6e75665` and its verified evidence artifact
`reports/plan-9-9-operator-packaging-evidence.md`. Those proven code and evidence anchors, not a
prior plan document, are the dependency contract for this lane.

**Design-entry gate:** Satisfied on 2026-07-15. The dedicated security review froze
`docs/superpowers/specs/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md`
at SHA-256 `8B67FC187B92F0B66A9932AAAD9A013C476C19C165A1044F57F338245A01786C`; its adjacent approval record
is `docs/superpowers/reviews/2026-07-15-plan-9-96-security-contract-approval.md` at SHA-256
`63F2200FE3A4540A4455CF737B42E042D9613648454736B543846A6CB4BD211D`. The review fixed the
authorization, scope, expiry, audit, storage, transcript, workspace-origin, and launch-setting
trust boundaries before implementation planning began.

**Owned follow-ups (sole custody):**

- `P9.85-FU-7` — deliberate-access design for session- or time-scoped access to unredacted debug
  traces, a broader audit of every logging/telemetry surface for the same class of gap, and an
  explicit decision on whether real `acpx` client transcripts can or should be brought under the
  same redaction guarantee rather than relying on human review before committed excerpts.
- **Sole custody — `P9.9-FU-1`: Workspace-influenced agent launch environment.** Scope wording is
  retained from the landed follow-up's Deferred Follow-Ups section; that is scope provenance, not
  this lane's dependency anchor.

  **Risk:** The config-root containment guard prevents implicit or explicitly redirected config
  files from resolving inside the workspace. It cannot prove that top-precedence environment values
  are operator-authored when an IDE merges project-local settings into the external agent launch
  environment. A malicious workspace could therefore influence provider, base-URL, or credential
  environment fields even though `.env.gateway` discovery is safe.

  **Acceptance criteria:** Define and implement a trust boundary that distinguishes
  operator-approved agent environment overrides from workspace-provided launch settings; fail
  closed or require an explicit approval ceremony before workspace-originated settings can affect
  local-Gateway provider, base URL, or credentials. Preserve legitimate shell/admin deployment
  flows and do not log values.

**Status:** Planning approved on 2026-07-15; implementation has not started. The reviewer-agent and
operator approved
`docs/superpowers/plans/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust.md` at
SHA-256 `E47701358596D0D31E6CD7FDF21438D529C65F0190889058C936FB9A0B00E721`. The authoritative adjacent
plan-approval record is
`docs/superpowers/reviews/2026-07-15-plan-9-96-implementation-plan-approval.md` at SHA-256
`A7DD28190FAC6859B6FED451E4CC89F64035EA0581CE3AB9A5D3BA1C89E8C6DB`. Implementation must wait for
this docs-only planning branch to merge, then begin from a fresh branch/worktree based on the latest
`origin/main`.

Plan 9.96 Task 9 Steps 2, 3, and 5 depend on Plan 9.98's implementation commit
`74d4ff21173a597c3b274cf6e6cbdf8a7eb43697` and its real-dependency evidence report at
`reports/plan-9-98-real-acpx-session-evidence.md`.

## Plan 9.97 (Tracked, Not Yet Scheduled): Mechanical Current-Raw-Evidence Grounding

**Raised:** 2026-07-14 by the approved Plan 9.95 lane split.

**Owned follow-up:** `P9.87-FU-1` — define a mechanical provenance guard between final WRITE
content and current-turn raw ranges without logging source bodies.

This lane must not absorb or be absorbed by Plan 11.

**Status:** Tracked, not yet scheduled; no implementation plan exists on this branch. Its future
design must preserve the current-raw-evidence boundary independently of Plan 11's intelligent
selection and compression work.

## Plan 9.98 (Implemented): Real ACPX Session Evidence for Plan 9.96 Task 9

**Raised:** 2026-07-18 when Plan 9.96 Task 9's committed `acpx --version` capture helper proved
structurally unable to drive the real sessions required by Steps 2, 3, and 5.

**Foundation:** Plan 9.96 Tasks 0-8 at
`d0c467041015b5f3630c7d4b984c0a2b396a8bb8`.

**Implementation and evidence:** Implemented at
`74d4ff21173a597c3b274cf6e6cbdf8a7eb43697`. The independently verified ordinary and elevated
real-ACPX evidence, immutable artifact SHA-256 values, bounded completion rule, Redis-derived cost,
and exact environment-role audit are recorded in
`reports/plan-9-98-real-acpx-session-evidence.md`.

**Dependency:** Plan 9.96 Task 9 may now run its Step 2 capture commands with `--drive-session`.
Plan 9.98 is necessary but not sufficient for Plan 9.96 closure because Plan 9.99 remains open.

**Status:** Implemented and real-dependency verified on 2026-07-19.

### P9.98-FU-1 (Implemented): Workspace Identity TOCTOU Repair and Linux CI Isolation

**Raised:** 2026-07-19, by Linux CI failures on PR #60 discovered before that PR merged. Two
defects: (1) workspace revalidation remembered only the resolved target path, so a symlink
retargeted after authorization, or a delete-and-recreate that happened to reuse an inode, could
evade detection; (2) the default Linux CI suite implicitly depended on host keyring availability,
POSIX file-creation defaults, and Python locale coercion that do not hold in a clean CI environment.

**Root cause and fix:** `WorkspaceIdentity` (`src/optimus/acp/trusted_paths.py`) now binds the
original absolute lexical input path alongside the resolved canonical path, device, inode, and a
`st_ctime_ns` change-time token. Revalidation reconstructs a fresh identity from the stored lexical
path -- not the previously-resolved target -- and compares the complete digest, so a retargeted
symlink or a same-path replacement fails closed with `WORKSPACE_IDENTITY_CHANGED` before spawn.
`optimus-trust inspect` now resolves workspace identity before opening the keyring-backed approval
store, so a nonexistent workspace fails before any keyring access. Default-suite tests were made
host-independent (fake keyring at every boundary, permission checks recorded rather than exercised
against the real filesystem, explicit Popen-environment assertions) without adding a Redis, Gateway,
ACPX, or keyring dependency to CI.

**Design and plan:**
`docs/superpowers/specs/2026-07-19-plan-9-98-fu-1-workspace-identity-ci-design.md`; implementation
plan `docs/superpowers/plans/2026-07-19-plan-9-98-fu-1-workspace-identity-linux-ci.md`, approved and
amended twice (v2 widened Task 1's identity-test scope, v3 corrected the verifier invocation) via
`docs/superpowers/reviews/2026-07-19-plan-9-98-fu-1-implementation-plan-approval.md` and its
`-v2`/`-v3` amendment records.

**Implementation:** Commits `e77904257e647bdbdf4df85fc64155426df07a8e` ("fix: harden workspace
identity revalidation"), `3079de205c1509599b36518f60fe97844406a7b6` ("fix: validate inspect
workspace before keyring"), and `4818533c43202441152de42364b66f54aa5cdd31` ("test: make launch
trust checks portable in CI") -- all merged as part of PR #60 (`agent/kiro/plan-9-96`, 2026-07-19),
the same documented operator exception that bundled Plan 9.96 Tasks 0-8 and all of Plan 9.98 into
one PR ahead of a weekly usage-limit reset. This plan's own Task 5 (an independent push, reviewer
sign-off, and GitHub Actions verification cycle written assuming its own dedicated PR) was
superseded by that bundling decision rather than skipped; the code and tests it specifies are the
same code and tests live on `main` today.

**Status:** Implemented. Re-verified 2026-07-23: `tests/unit/acp/test_trusted_paths.py` and the
related launch-trust suites pass on current `main` (aside from the separately tracked Windows
subprocess handle-duplication flake below, which is unrelated). This plan's own Task 5 and
Definition-of-Done checkboxes remain unticked because that closure ceremony never ran as its own PR;
this entry is the closure record this roadmap was missing.

### P9.98-FU-2 (Implemented): Approval-Time Runtime Bootstrap

**Raised:** 2026-07-19, as an immediate follow-up to Plan 9.98-FU-1, on the same pre-merge PR #60.
FU-1's own `st_ctime_ns` workspace-identity binding introduced a self-invalidation defect: the first
time a `.optimus` runtime-root directory was created inside the resolved workspace -- whether by an
agent launch or the evidence tooling -- that creation itself changed the *parent* workspace
directory's own change-time on POSIX, immediately invalidating the identity FU-1 had captured at
approval time. A durable approval could pass authoring and then never actually be reusable.

**Root cause and fix:** The TTY-gated `optimus-trust approve` ceremony
(`src/optimus/acp/launch_approval_cli.py`) now creates and validates the empty resolved-workspace
`.optimus` directory itself, before it captures the identity bound into the approval, so the
directory's own creation can no longer retroactively change a stored identity's change-time.
`append_launch_audit_event()` (`src/optimus/acp/launch_audit.py`) became a strict read-only consumer
of that directory: it never creates it, and treats a missing, non-directory, or symlinked runtime
root as fatal instead of silently bootstrapping one. Only the approve path, after `_require_tty()`,
may create `.optimus`; `optimus-agent`, `optimus-trust run`, the evidence tool, `inspect`, `revoke`,
and verification commands must never initialize it, preserving the no-launch-side-runtime-root-
creation boundary the design set.

**Design and plan:** `docs/superpowers/specs/2026-07-19-workspace-runtime-bootstrap-ci-design.md`;
implementation plan
`docs/superpowers/plans/2026-07-19-plan-9-98-fu-2-approval-time-runtime-bootstrap.md`, approved via
`docs/superpowers/reviews/2026-07-19-plan-9-98-fu-2-implementation-plan-approval.md`.

**Implementation:** Commits `16cc68c7b3233945cbb17654b4d91a9b42dc9c01` ("fix: require initialized
workspace runtime root"), `d31f93e4d46175e882cf0d5cc5fb2bf9e7c60610` ("fix: bootstrap runtime root
during approval"), `cbe7b1d17291475ec286cf7e984a847d18286a78` ("test: cover approved runtime root
lifecycle"), and `900edfe159429b19b05449efae4382bddb72f21d` ("test: preserve missing runtime root
regression") -- all merged as part of the same bundled PR #60. As with FU-1, this plan's own
checkboxes were never ticked in-file because progress tracking did not go back through the plan
document during the bundled push; the underlying work is real, live, and tested.

**Downstream connection:** Discovering and fixing this exact class of POSIX change-time mutation is
what led directly to a later CI run surfacing a related but distinct test-alignment gap -- five
runtime-root failure-path tests whose fixtures did not yet account for the new fail-closed
behavior this FU introduced -- tracked and separately closed as **Plan 9.98-FU-3** immediately below.
That is why FU-3 already existed in this roadmap while FU-1 and FU-2, the causal work, did not.

**Status:** Implemented. Re-verified 2026-07-23: `tests/unit/acp/test_launch_approval_cli.py` and
`tests/unit/acp/test_launch_audit.py` pass on current `main` (aside from the separately tracked
Windows subprocess handle-duplication flake below, which is unrelated). This entry is the closure
record this roadmap was missing.

### P9.98-FU-3 (Complete): POSIX Runtime-Root Failure-Path Test Alignment

**Raised:** 2026-07-19 by GitHub Actions `clean-environment-recheck` on PR #60
([run 29690328862](https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/29690328862)).

**Known CI status:** The Windows-local full suite passed, but the clean Linux run failed five
runtime-root tests.  On POSIX, removing or replacing the direct child `.optimus` after a durable
approval changes the workspace directory's bound `st_ctime_ns`.  The durable-approval lookup then
correctly fails closed as `NO_APPROVAL` before the audit consumer can emit
`AUDIT_DIR_UNAVAILABLE`.  Windows does not expose this test setup because its `st_ctime` has
creation-time semantics.

**Owned follow-up:** Reconcile the test contracts without weakening FU-1's lexical-path,
device/inode, or change-time identity binding.  Launch and evidence flows that mutate `.optimus`
before reauthorization must prove the earlier `NO_APPROVAL` failure, no runtime-root recreation,
and no child/infra side effect.  Direct audit-consumer tests must independently prove
`AUDIT_DIR_UNAVAILABLE` for a missing or unsafe already-authorized runtime root.  Do not skip,
deselect, or platform-xfail the Linux tests.

**Acceptance boundary:** A fresh, separately reviewed plan must name all five failures from run
29690328862, keep the direct audit-root failure coverage, preserve the POSIX mutation-detection
proof, and finish with an unskipped clean Linux CI run.  No production-code defect is assumed by
this entry; the next plan must re-establish that conclusion from current source and CI evidence.

**Status:** Complete.  Resolved by a fresh, separately reviewed design spec and implementation plan
(`docs/superpowers/specs/2026-07-22-plan-9-98-fu-3-posix-runtime-root-tests-design.md`,
`docs/superpowers/plans/2026-07-22-plan-9-98-fu-3-posix-runtime-root-tests.md`), implemented and
merged via [PR #61](https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/61)
(`06937d334b6fbc614ca3054d5da793c7290d6f32`) on 2026-07-22.  All five named failures from run
29690328862 are resolved: the two full-entrypoint tests now assert POSIX `NO_APPROVAL` at durable
lookup, and the three evidence-tool tests mutate the runtime root only after a real authorization
succeeds, proving `AUDIT_DIR_UNAVAILABLE` from the real audit consumer.  FU-1's lexical-path,
device/inode, and `st_ctime_ns` identity binding is unchanged; no file under `src/` or `tools/`
was modified.  The final clean Ubuntu `clean-environment-recheck` run
([29921106279](https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/29921106279))
passed with `1452 passed, 0 failed, 9 skipped, 25 deselected` and 85.57% coverage, unskipped and
unmodified with respect to the five named tests.  PR #60 merged 2026-07-19 under a documented
operator exception because this follow-up was still outstanding; that exception is now resolved.

## Plan 9.99 (Planning Approved; Implementation Not Started): Credential URI Security-Snapshot Canonicalization

**Raised:** 2026-07-18 by the Plan 9.98 v6 security audit.

**Owned finding:** SECURITY-tier URI values currently enter the launch security snapshot only after
URI-userinfo masking, so changing only userinfo can leave the digest unchanged despite Plan 9.96's
URI-userinfo-HMAC requirement. Literal display of `OPTIMUS_GATEWAY_URL` can also expose URI userinfo
during approval.

**Acceptance boundary:** Produce a separately reviewed security contract and implementation plan;
bind URI userinfo into the security snapshot without logging or displaying it; make approval display
userinfo-safe; and add fail-closed tests for digest sensitivity, display redaction, and unchanged
non-credential URI behavior.

**Dependency:** Plan 9.99 must land before Plan 9.96 closes. Plan 9.98 v6 does not implement,
reinterpret, or waive this finding.

**Design-entry gate:** Reviewer-agent and operator approved on 2026-07-22. The review
broadened the finding to every SECURITY-tier URI-bearing value (`OPTIMUS_GATEWAY_URL`,
`OPTIMUS_REDIS_URL`, `OPTIMUS_LOCAL_GATEWAY_BASE_URL`, and the resolved `_resolved_base_url`),
required original-text userinfo slicing to preserve IPv6 bracket and host-case fidelity, and required
a registry-wide invariant so a future `_URL`/`_URI` SECURITY-tier name cannot omit URI
classification. The frozen contract is
`docs/superpowers/specs/2026-07-22-plan-9-99-credential-uri-security-snapshot-canonicalization-design.md`
at SHA-256 `B2B236EEF191EC74046A9FF32EA63F91A08E6519BA30ADF8FA3599F4DBC77CF8`; its adjacent approval
record is `docs/superpowers/reviews/2026-07-22-plan-9-99-security-design-approval.md`.

**Status:** Reviewer-agent and operator approved the implementation plan on 2026-07-22; implementation
has not started.
`docs/superpowers/plans/2026-07-22-plan-9-99-credential-uri-security-snapshot-canonicalization.md` is
frozen at SHA-256 `BEDF2340F8473F2FDCB2E582255E4A09C42B0B9017AFAC5847FD962C2FD6AFA1`; its adjacent
approval record is `docs/superpowers/reviews/2026-07-22-plan-9-99-implementation-plan-approval.md`.
Docs merged in PR #63 (commit `b6ab9b6`). Implementation must begin from a fresh branch/worktree based
on the latest `origin/main`, not the Plan 9.98 branch.

## Backlog: P9.85-FU-3 Cross-Run/Session Spend Policy (Tracked, Not Yet Scheduled)

**Raised:** 2026-07-11, in Plan 9.85's own Deferred Follow-Ups section
(`docs/superpowers/plans/2026-07-11-plan-9-85-multi-turn-read-observe-replan.md`), disclosed as
owned by an unnamed future budget-governance plan rather than silently dropped.

**Owned follow-up:** Define an operator-configurable cumulative session/project spend ceiling above
the existing per-run `max_cost_usd` monotonic limit and the Plan 7 usage ledger. Plan 9.85 records
all usage completely and accurately but does not itself invent any cross-run denial policy.

**Acceptance criteria:** A new cross-run/session ceiling must not weaken or duplicate the existing
per-run monotonic-tighten-or-exact approval contract (Plan 9.96), must be enforced from the same
reconciled Plan 7 usage ledger rather than a new parallel accounting path, and must fail closed
rather than silently permit overspend when ledger data is unavailable.

**Status:** Tracked, not yet scheduled. No implementation plan exists.

## Backlog: Re-pin FU-4A/FU-5 Live Evidence (Tracked, Not Yet Scheduled)

**Raised:** 2026-07-15 by Plan 9.95 Task 5 Implementation Amendment. The Plan 9.87 evidence
report's `--require fu4a` and `--require fu5` gates fail with `implementation drift` because
34 files in `src/optimus` changed between the pinned implementation SHAs (`4bf20fff` for fu4a,
`bfcea0da` for fu5) and `origin/main` at the time of Plan 9.95's branch-cut — caused by Plan 9.9
and other unrelated prior work. Re-establishing freshness requires re-capturing live `acpx`
evidence against the current codebase. This is not a correctness defect (the underlying
implementations remain functionally correct) but a watched-path-drift gap in the evidence chain.

Plan 9.96 will materially modify `src/optimus/**`, increasing watched-path drift, and freezes the
Plan 9.87/9.88 raw-capture helpers as non-qualifying while introducing a sanitized capture path.
The future re-pin must be prioritized with that change in mind and explicitly choose its capture
path (expected to be the reviewed Plan 9.96 tool if that implementation has landed); it must not
assume the frozen helpers remain an acceptable current-evidence path.

**Status:** Tracked, not yet scheduled. No implementation plan exists.

## Backlog: P9.8-FU-5 Zed Refusal-Rendering Stability (Tracked, Not Yet Scheduled)

**Raised:** 2026-07-11 during Plan 9.8 live evidence. Zed 1.10.2 correctly received and briefly
rendered the ambiguous-refusal corrective text, then panicked in native client code with
`range end index 3 out of range for slice of length 2`. The agent wire contract and independent
`acpx` durable refusal UI remain proven.

**Sole custody:** This backlog entry. Plan 9.75 was already complete when the client-stability issue
was discovered, and its evidence report classifies the panic as separate from the ACP conformance
fix. Do not reopen Plan 9.75 and do not silently fold this work into Plan 11.

**Acceptance boundary:** Reproduce against a supported current Zed build, separate agent payload
correctness from client rendering behavior, preserve the existing fail-closed refusal contract,
and produce durable operator-visible refusal evidence or an explicit externally owned Zed defect
disposition. Any agent-side workaround requires its own reviewed plan and must not weaken ACP
conformance.

**Evidence anchors:** `reports/plan-9-8-task-aware-context-evidence.md`,
`reports/plan-9-75-zed-hitl-runtime-evidence.md`, and the Plan 9.8 `P9.8-FU-5` acceptance criteria.

**Status:** Tracked, not yet scheduled. No implementation plan exists.

## Backlog: NDJSON Session Initial-Send Broken-Pipe Race (Resolved)

**Raised:** 2026-07-22, after `test_run_operator_live_session_surfaces_no_approval_remediation`
failed with `BrokenPipeError: [Errno 32] Broken pipe` on three separate `main`-branch CI runs within
four days: the Plan 9.98-FU-3 closure commit (`40d5fa2`, resolved by rerun), the Plan 9.98-FU-3
implementation merge (`06937d3`, PR #61), and the Plan 9.99 docs merge (`efabbbe`, PR #63). The same
test passed clean on the intervening PR #62 merge, confirming genuine intermittency rather than a
commit-specific regression.

**Root cause:** `NdjsonSubprocessSession.send()`
(`src/optimus/acp/ndjson_subprocess_session.py:74-80`) writes to `process.stdin` with no exception
handling. `_fail_subprocess_exited()` (same file, lines 159-181) is the code that detects an
early-exited child and translates its stderr into the clean, value-free gate-rejection message via
`_extract_gate_rejection_message()` — but it is only reached from `read_next()`, which runs strictly
after `send()` returns. When a spawned agent child exits and closes stdin before the parent's first
`send()` call completes (as happens whenever `__main__.py`'s launch gate rejects before the ACP
handshake begins), the raw `BrokenPipeError` propagates instead of ever reaching that remediation
path. This is not test-only flakiness: any real operator hitting this exact timing would see a bare
traceback instead of the intended "run `optimus-trust ... approve --mode durable`" guidance.

**Second race found during implementation:** Fixing the above exposed a related, pre-existing race:
`_fail_subprocess_exited()` (shared by `send()`, `wait_for()`, and `read_next()`) read
`stderr_text()` with no guarantee the background `_read_stderr` thread had drained the child's
already-printed gate-rejection line yet. `wait_for()`'s `poll()` check fires on its very first loop
iteration with zero delay, so it could call `_fail_subprocess_exited()` before the reader thread had
appended anything, falling through to the generic "exited early, empty stderr" message instead of the
real remediation text — confirmed on real CI (run `29933994440`) immediately after the first fix
landed. The synchronization was centralized inside `_fail_subprocess_exited()` itself rather than
duplicated per caller.

**Scope clarity:** This is a Plan 9.96 follow-up, not a Plan 9.8 or Plan 9.98 one. The affected code
(`NdjsonSubprocessSession`, `operator_verify.py`) is Plan 9.96 Task 5 Batch 3's own work — every
attribution comment in the affected files says so (`ndjson_subprocess_session.py:163`,
`operator_verify.py:3`, `test_verify_live_agent_cli.py:39,225,323`). Plan 9.98 and Plan 9.99 never
touched this file; they are only the contexts where this pre-existing flake happened to surface in
CI, since the full suite runs on every commit regardless of what changed. Plan 9.96 itself remains
open — only Task 9 (real launch-trust evidence, gated behind Plan 9.99) is outstanding — so this
flake is a real risk to Plan 9.96's own eventual Task 9 closure-evidence run, which will need a clean
full-suite pass. It does not block or reopen Plan 9.98 (already closed) or Plan 9.99 (docs-only,
unaffected by this test).

**Acceptance boundary:** Wrap the initial `send()` write/flush against `BrokenPipeError`/`OSError`;
on that failure, route through the same `_fail_subprocess_exited()` / gate-rejection-message
detection already used for read-time exits, so a send-time pipe closure produces the identical clean
`LiveSessionError` an operator gets today from a read-time exit. Preserve the test's real (non-mocked)
subprocess design. Demonstrate the fix with repeated runs showing zero flakes before closing.

**Resolution:** Fixed in PR #65 (commits `aef45e9`, `a806c06`), merged to `main` at `39c7992` on
2026-07-22. `send()`/`close_stdin()` now convert an already-exited child's broken pipe into the same
clean `LiveSessionError` a read-time exit produces, and `_fail_subprocess_exited()` waits for the
process and drains the stderr reader before building its message, closing both races. Five new
deterministic unit tests in `tests/unit/acp/test_ndjson_subprocess_session.py` reproduce each race
without relying on OS-scheduling timing; the previously-flaky integration test passed 25/25 local
repeated runs and green on real `clean-environment-recheck` CI (run `29934807930`) before merge.

**Evidence anchors:** `docs/superpowers/reviews/plan-9-98-fu-3-review-checkpoints.md:245-279`
(first documented occurrence); CI runs `29921106279`, `29922900606`, `29930887488` (failures) and
`29923341465` (clean pass, same test, same day); CI run `29933994440` (the second race, exposed after
the first fix); CI run `29934807930` and post-merge `main` run `29935529847` (clean, both fixes
applied).

**Status:** Resolved 2026-07-22.

## Backlog: Windows Subprocess Handle-Duplication Flake, WinError 6/50 (Tracked, Not Yet Scheduled)

**Raised:** 2026-07-22, during Plan 9.99 Task 7 repository-wide verification. Independently reproduced
by both the implementing agent (Cursor) and the reviewing agent (Claude) on the same Windows
development host, in two separate full-suite runs taken minutes apart.

**Signature:** `uv run pytest -q` intermittently fails with `OSError: [WinError 6] The handle is
invalid` or `[WinError 50] The request is not supported`. Every occurrence raises inside CPython's own
`subprocess.py`, at `Popen.__init__` -> `_get_handles` -> `_make_inheritable` ->
`_winapi.DuplicateHandle`, for a THIRD-PARTY child process spawned directly via stdlib
`subprocess.run`/`Popen` (`git.exe`, `icacls.exe`, or the real subprocess launched by
`tests/integration/release/test_verify_live_agent_cli.py`, which exercises the real
`NdjsonSubprocessSession`/`operator_verify.ensure_verify_workspace` machinery). The failure occurs
before any Optimus-authored code gets control of the child process. Two independent full-suite runs on
the same host produced: one completely clean pass (1469 passed, 0 failed) and one run failing an
identical set of 11 tests (see Evidence anchors).

**Explicitly distinct from the just-resolved NDJSON broken-pipe race above:** that bug was a genuine
logic defect inside `NdjsonSubprocessSession` itself -- two real races in Optimus's own code, confirmed
on real Linux CI, fixed in PR #65. This entry must NOT be assumed to be the same kind of problem merely
because it is also subprocess-related and also intermittent. Treating a reproducible failure as "just
flaky" without root-causing it is exactly the mistake the broken-pipe entry above shows this project
has made before real evidence corrected it; this entry exists so the same mistake is not repeated here
by default.

**Root cause: not yet established.** Plausible causes, none yet confirmed:
- Windows handle-table growth/exhaustion within a single long-lived `uv run pytest` process across
  roughly 1500 tests, many of which spawn subprocesses -- potentially aggravated by
  `NdjsonSubprocessSession`'s background reader threads holding pipe handles alive longer than
  strictly necessary across unrelated later tests.
- A known class of CPython-on-Windows `subprocess` race between one call's handle duplication and
  concurrent garbage collection of a previously-exited `Popen` object under load.
- Restrictions specific to the sandboxed Bash-tool shell this evidence was collected through (job
  objects / handle-inheritance limits) that may not reproduce in a native terminal, in WSL2, or in
  real CI.

**Acceptance boundary:** This may only be closed as environment-only noise after:
1. Reproducing (or failing to reproduce) the identical failure set on a plain native Windows terminal,
   outside any sandboxed tool shell, with the result recorded.
2. Reproducing (or failing to reproduce) on the project's WSL2 Ubuntu-24.04 substitute (see the
   "WSL2 = local Linux CI substitute" operating note) and checking real GitHub Actions CI history, to
   establish whether this is Windows-general, sandbox-specific, or already absent on the Linux runners
   CI actually uses.
3. Auditing whether any Optimus-owned code -- in particular `NdjsonSubprocessSession`'s reader threads,
   and any other call site constructing `subprocess.Popen`/`subprocess.run` without promptly closing
   pipes or joining reader threads -- leaves handles alive longer than necessary in a way that could
   contribute to handle-table pressure, even though the failure itself surfaces inside stdlib rather
   than in Optimus's own code.
4. Only classifying this as a pure OS/sandbox environment limitation once (1) and (2) point away from
   an Optimus code defect. If (3) turns up a real resource-lifecycle issue, it must be fixed with a real
   PR, the same way the NDJSON broken-pipe race was, not suppressed or skip-marked away.

**Evidence anchors:** Plan 9.99 Task 7 handoff checkpoint log
(`docs/superpowers/reviews/plan-9-99-review-checkpoints.md` -- gitignored, cite by content since it is
not in git history). Two full-suite runs on the same host: one clean (1469 passed, 0 failed, 20
skipped, 25 deselected) and one reproducing exactly this set --
`tests/integration/release/test_verify_live_agent_cli.py` (`test_verify_live_agent_defaults_to_scratch_workspace`,
`test_verify_live_agent_preflight_failure_exits_2`, `test_verify_live_agent_success_exits_0`,
`test_verify_live_agent_runtime_failure_exits_3`),
`tests/unit/acp/test_launch_gate.py::TestRealWindowsDaclEnumeration` (all 3 cases),
`tests/unit/acp/test_trusted_paths.py::TestWorkspaceIdentity::test_identity_includes_git_root_when_present`,
`tests/unit/tools/test_run_plan996_acpx_security_evidence.py::test_capture_timeout_terminates_parent_and_descendant_in_an_isolated_probe`,
`tests/unit/tools/test_verify_plan987_acpx_evidence.py::test_post_capture_verifier_is_directly_executable`,
`tests/unit/tools/test_verify_plan987_acpx_evidence.py::test_cli_digest_gate_rejects_non_lowercase_or_non_sha256_value`.

**Scope clarity:** None of the affected tests overlap with any file Plan 9.99 changed
(`src/optimus_security/sanitization.py`, `src/optimus/acp/launch_policy.py`,
`src/optimus/acp/launch_gate.py`, `src/optimus/acp/launch_approvals.py`,
`src/optimus/acp/launch_approval_cli.py`, and their test files); the failure set and signature are
identical whether or not Plan 9.99's changes are present in the working tree. This does not block
Plan 9.99 completion, commit, or PR -- it is an unrelated, pre-existing, environment-surfaced flake,
tracked here rather than inside the Plan 9.99 plan file.

**Status:** Tracked, not yet scheduled. No implementation plan exists.

## Plan 10 (Tracked, Not Yet Scheduled): Unified Gateway Capabilities Broker

**Raised:** 2026-07-08, during Plan 9.7 review. The client-side one-key contract is already
shaped for this: `src/optimus/evidence/acquisition.py` posts to `/v1/tools/web/search` and
`src/optimus/telemetry/observability.py` posts to `/v1/observability/traces` through
`GatewayClient`, the same gateway-only seam model calls already use — but the local gateway
(`src/optimus_gateway/server.py`) only implements `/v1/responses`. Those calls would 404 against
the local gateway today. The gap is not in the agent-side contract; it's that the local gateway
stub hasn't grown routes/upstream adapters for web search or observability export yet. Any real
web-search or observability provider key (e.g. Tavily, LangSmith) would need to live gateway-side
once those routes exist, per the same one-key model already enforced for model calls.

**User story:** As an operator, I hold exactly one local credential set, and the local gateway
brokers web search, web extract, and observability export the same way it already brokers model
calls — vendor keys for those capabilities live gateway-side only, never in the agent's own
environment.

**Status:** Tracked, not yet scheduled; no design work done yet. Explicitly out of scope for Plan
9.7 (a local-startup-ergonomics plan, not a gateway-capability-surface redesign) and for Plan 9.6
(live-verification proof of the existing model-call path). The one confirmed decision so far:
this is its own plan, not folded into 9.7. Design questions to resolve when scheduled: whether to
implement web search and observability together as one gateway-capability slice (same
secret-boundary and route pattern serves both) versus web search first with observability staying
a no-op/local-JSONL sink until a later slice; the gateway-side secret resolution shape (own
env/`.env.gateway`/keyring precedence, independent of Plan 9.7's agent-side equivalent); and
normalized `gateway_usage`/cost fields for non-model calls, matching the existing model-call
pattern.

## Plan 11 (Tracked, Not Yet Scheduled): Context Window Optimization and Intelligent Selection

**Design source:** `docs/context-window-optimization-strategy.md` (standalone canonical design note; no HLD/LLD/Test Strategy anchors yet - see the Cross-Cutting section above)

**Future implementation plan:** create `docs/superpowers/plans/YYYY-MM-DD-context-window-optimization-intelligent-selection.md` after Plan 9.8 and the prerequisite plans (7, 8, 8.5, and the input-supplying Plans 4, 5, 6, 6.5, 9) are stable.

**User story:** As the agent runtime, I select, pack, summarize, invalidate, evict, and measure context under a cost- and freshness-aware policy, so the agent gets smarter while fully-loaded cost goes down, without ever silently dropping required evidence to fit a budget.

**Status:** Tracked, not yet scheduled. This plan comes after Plan 9.8, Plan 9.5 task-level agent orchestration, and the real golden harness are stable, since selection policy depends on the cost-attribution, evidence, trust, freshness, loop/skill, and agent-run signals those plans establish. Do not start this plan early just because it is architecturally core - its inputs need to exist first.

**Source anchors:**
- `docs/context-window-optimization-strategy.md` - Context Type x Mechanism Matrix, Selection Pipeline, Selection Model, Freshness and Dependency Precedence, Prompt Packing and Cost Controls, Compaction, Offline Promotion Gates, Online Guardrails, Context Regret, Baseline and Ablation Plan, Calibration Items.
- Depends on: Plan 7's cost-attribution ledger, Plan 4's evidence/tool-output trust, Plans 5/6/6.5's guardrail and MCP/config/runtime trust signals, Plan 9's loop/skill state.

**Owned deferred follow-ups (sole custody):**
- `P9.8-FU-2` — intelligent ambiguous-reference ranking with measured wrong-target regret and a
  fail-closed threshold.
- `P9.8-FU-3` — dynamic, model-aware context budgets and injection-safe required-file
  summarization with measured quality/cost trade-offs.

`P9.8-FU-5` is explicitly excluded; its Zed client-stability custody remains in the standalone
backlog entry above.

**Expected deliverables:**
- Selection/scoring engine implementing the utility function (weighted relevance, dependency-coverage gain, authority, recency, user pin, failure recurrence, evidence-diversity gain, minus redundancy penalty), dependency-closure resolution, and budget-constrained packing.
- Two-phase trust/freshness gating, cache-stable prompt packing, and compaction triggered by the defined high-water marks (context usage threshold, iteration boundary, tool-output budget, repeated-failure pollution, model-tier downgrade, scope/approval change).
- Offline promotion-gate harness (patch correctness, fully-loaded cost, stale-context rejection, context regret, coverage@line-budget, injection safety) and the null-baseline / single-mechanism / combination ablation suite.
- Online guardrail circuit breakers (missing attribution, budget overshoot, incomplete dependency closure, low freshness confidence, cache-hit degradation) with anti-thrash cooldown.

**Explicit non-goal for this plan's initial scope:** promoting any calibration placeholder (15% savings target, regression thresholds, latency/cache baselines) to a binding release gate, and folding this content into the HLD/LLD/Test Strategy PDFs. Both happen later, and only after Optimus eval runs calibrate the placeholders and the promotion gates are accepted.

## Recommended Sequence

1. Plan 1: Core runtime and ACP transport.
2. Plan 2: Mode/state/mutation boundary.
3. Plan 3: Gateway-only configuration and gateway client.
4. Plan 4: Tool policy and evidence acquisition.
5. Plan 5: Permission/pre-tool/shell guardrails.
6. Plan 6: Prompt-injection/MCP/CI parity.
7. Plan 6.5: Guardrail hardening and MCP runtime trust wiring.
8. Plan 7: Usage accounting and observability.
9. Plan 8: Retry, fitness gates, and release gates.
10. Plan 8.5: Release-gate hardening and golden-harness wiring.
11. Plan 9: Bounded loops and curated workflow skills.
12. Plan 9.5: Agent orchestration and end-to-end coding workflow.
13. Plan 9.7: Local dev infra auto-start and keychain-based setup — **merged (PR #32,
    2026-07-09); complete operator walkthrough recorded 2026-07-11.** IDE `session/prompt`
    completion was subsequently closed by Plan 9.75.
14. Plan 9.75: Zed HITL ACP conformance and real Zed completion — **complete (2026-07-10),**
    merged through PR #36 at `4fe353bb21ff3a39914e5cf84979a4494c54e25b`; evidence in
    `reports/plan-9-75-zed-hitl-runtime-evidence.md`.
15. Plan 9.8: Task-aware workspace context for planning — implemented and live-verified 2026-07-11;
    exact-path Zed mutation under filler pressure proven; ambiguous refusal on-wire with Zed stay-up
    deferred as P9.8-FU-5; evidence in `reports/plan-9-8-task-aware-context-evidence.md`.
16. Plan 9.85: Multi-turn read-observe-replan workflow — implemented and live-verified
    2026-07-12 for the oversized-required-context trigger; deferred from Plan 9.8 as P9.8-FU-1;
    closes the gap where required context exceeds the single-pass budget; evidence in
    `reports/plan-9-85-multi-turn-acpx-evidence.md`.
17. Plan 9.87: Model-initiated replanning and live refusal evidence — **closed**; FU-4A/FU-5
    proven, FU-4B accepted-open (exhausted) via Plan 9.88 ceremony
    `fec114b7fc79da35ea399f4d66e22e776e6b76a3`.
18. Plan 9.88: FU-4B evidence remediation and Plan 9.87 closure — **closed** (Outcome B
    accepted-open); completed before Plan 9.9 began.
19. Plan 9.9: Operator packaging and credential diagnostics — **implemented and live-verified**;
    implementation SHA `f120a5afde39e3b3a8a405211ae71653b6e75665`, evidence report SHA
    `cde9cb9d22c32d0d0fe05b019543d6b1b5ba78a5`; owns cross-layer provider/key mismatch diagnostics
    and non-editable-install root discovery; evidence in
    `reports/plan-9-9-operator-packaging-evidence.md`.
20. Plan 9.95: Usage, telemetry, and evidence-tooling correctness — implemented;
    `P9.85-FU-6`, `P9.88-FU-2`, and `P9.88-FU-3` closed; evidence in
    `reports/plan-9-95-usage-telemetry-evidence.md`.
21. Plan 9.96: Operator-controlled debug and launch trust — **planning approved 2026-07-15;
    implementation not started.** Frozen security contract SHA-256
    `8B67FC187B92F0B66A9932AAAD9A013C476C19C165A1044F57F338245A01786C`, security-contract approval
    record SHA-256 `63F2200FE3A4540A4455CF737B42E042D9613648454736B543846A6CB4BD211D`, and approved implementation
    plan SHA-256 `E47701358596D0D31E6CD7FDF21438D529C65F0190889058C936FB9A0B00E721`; adjacent plan-approval
    record SHA-256 `A7DD28190FAC6859B6FED451E4CC89F64035EA0581CE3AB9A5D3BA1C89E8C6DB`.
22. Plan 9.97: Mechanical current-raw-evidence grounding — tracked, not yet scheduled; remains
    isolated from Plan 11; no implementation plan exists.
23. Plan 9.98: Real ACPX session evidence for Plan 9.96 Task 9 — **implemented and
    real-dependency verified** at `74d4ff21173a597c3b274cf6e6cbdf8a7eb43697`; evidence in
    `reports/plan-9-98-real-acpx-session-evidence.md`.
24. Plan 9.99: Credential URI security-snapshot canonicalization — planning approved 2026-07-22,
    implementation not started; must land before Plan 9.96 closes.
25. Plan 10: Unified Gateway Capabilities Broker — tracked, not yet scheduled.
26. Plan 11: Context window optimization and intelligent selection — tracked, not yet scheduled;
    starts only after Plan 9.8, Plan 9.5 task-level agent orchestration, and the real golden
    harness are stable.

The recommended sequence builds the executable release skeleton while ensuring the higher-risk guardrail surface is stable before Plan 7 starts recording guardrail and MCP audit events. Plan 8.5 closes PR #21 review gaps in shadow promotion fidelity, one-key scan coverage, golden-harness CLI wiring, command timeouts, shadow copy cost, and fitness-gate telemetry cost before Sprint 1 sign-off is treated as complete. Plan 9.5 composes the Phase 1 primitives into a working local-first coding agent; Plan 9.8 establishes the specific task-aware context correctness floor before Plan 11 adds context-window intelligence. Plan 11 stays last regardless: it depends on Plan 9.8 and inputs from Plans 4, 5, 6, 6.5, 7, 9, and 9.5, and its PDF fold-in is explicitly deferred until calibration is accepted.

Plan 9.9 follows Plan 9.8 as a separate operator-runtime hardening lane. It owns the two deferred
Plan 9.7 packaging/credential diagnostics and does not expand Plan 9.8's context-selection scope.
Plan 9.9 established and live-verified the non-editable install contract. Future operator and
Plan 9.8 regression runs use `uv tool install . --reinstall`; the historical Plan 9.8 evidence
remains unchanged.
Plan 9.85 is a separate lane from both Plan 9.8 and Plan 9.9: it extends Plan 9.8's single-pass
correctness floor to bounded multi-turn planning when required context cannot fit one pass, and it
neither depends on nor blocks Plan 9.9. Plan 9.85 is implemented and live-verified for the
oversized-required-context trigger; `P9.85-FU-4` (model-initiated replanning when Plan 9.8 context
already fits) and `P9.85-FU-5` (live model-emitted `REFUSE:` demonstration) are explicitly deferred
to the newly tracked **Plan 9.87**, which follows Plan 9.85; **Plan 9.88** remediated FU-4B
and closed Plan 9.87 (Outcome B accepted-open) before Plan 9.9 in the sequence above. Plan 9.87
and Plan 9.88 are closed; Plan 9.9 is now itself implemented and live-verified (implementation SHA
`f120a5afde39e3b3a8a405211ae71653b6e75665`).

Plans 9.6 and 9.7 sit alongside each other, not in a strict dependency order: Plan 9.6 owns the Phase 1 working-agent sign-off gate (live Redis/Gateway/e2e proof plus the real-IDE HITL artifact) and Plan 11 does not start until it passes; Plan 9.7 only changes how an operator's local Redis/Gateway dependencies get started before a session and does not touch what Plan 9.6 proves or gate. Plan 9.7 merged independently of Plan 9.6's remaining open HITL item. **Plan 9.75** follows Plan 9.7 in the recommended sequence: it fixes the open Zed HITL / `toolCall` permission payload and closes Plan 9.7's deferred planning-bar DoD using the Plan 9.7 operator PATH install for manual verification. Plan 10 is tracked separately and not yet scheduled or designed; do not fold its gateway-capability-broker scope into 9.6, 9.7, or 9.75 when picking up either.
