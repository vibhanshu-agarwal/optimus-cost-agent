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

**Status:** Approved for implementation. Owns the Phase 1 working-agent sign-off gate; Plan 10 does not start before this gate passes.

### Immediate post-PR #30 follow-up (Plan 9.6 closure)

**Reason:** PR #30 provides subprocess/operator proof, but the real-IDE HITL claim remains open.

**Must land next:**
- ACP `session/request_permission` payload conformance update in `src/optimus/acp/spec.py`: include the ACP v1-required `toolCall` object in addition to the existing approval options/metadata.
- Update/add protocol tests and transcript assertions so the permission request shape is locked by tests (not only by manual review).
- Re-run the Zed HITL flow and commit an artifact under `reports/` proving approval UI rendering + successful end-turn completion.
- Close the Plan 9.6 claim-table row "A real IDE can drive it" only after the artifact is on disk and reviewed.

**Gate reminder:** Until the follow-up above is complete, treat Plan 9.6 as "subprocess/operator proof green, real IDE HITL open."

## Plan 10 (Tracked, Not Yet Scheduled): Context Window Optimization and Intelligent Selection

**Design source:** `docs/context-window-optimization-strategy.md` (standalone canonical design note; no HLD/LLD/Test Strategy anchors yet - see the Cross-Cutting section above)

**Future implementation plan:** create `docs/superpowers/plans/YYYY-MM-DD-context-window-optimization-intelligent-selection.md` after the prerequisite plans (7, 8, 8.5, and the input-supplying Plans 4, 5, 6, 6.5, 9) are stable.

**User story:** As the agent runtime, I select, pack, summarize, invalidate, evict, and measure context under a cost- and freshness-aware policy, so the agent gets smarter while fully-loaded cost goes down, without ever silently dropping required evidence to fit a budget.

**Status:** Tracked, not yet scheduled. This plan comes after Plan 9.5 task-level agent orchestration and the real golden harness are stable, since selection policy depends on the cost-attribution, evidence, trust, freshness, loop/skill, and agent-run signals those plans establish. Do not start this plan early just because it is architecturally core - its inputs need to exist first.

**Source anchors:**
- `docs/context-window-optimization-strategy.md` - Context Type x Mechanism Matrix, Selection Pipeline, Selection Model, Freshness and Dependency Precedence, Prompt Packing and Cost Controls, Compaction, Offline Promotion Gates, Online Guardrails, Context Regret, Baseline and Ablation Plan, Calibration Items.
- Depends on: Plan 7's cost-attribution ledger, Plan 4's evidence/tool-output trust, Plans 5/6/6.5's guardrail and MCP/config/runtime trust signals, Plan 9's loop/skill state.

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
13. Plan 9.6 closure follow-up: ACP `toolCall` permission conformance + real Zed HITL artifact.
14. Plan 10: Context window optimization and intelligent selection - tracked, not yet scheduled; starts only once Plan 9.5 task-level agent orchestration and the real golden harness are stable.

The recommended sequence builds the executable release skeleton while ensuring the higher-risk guardrail surface is stable before Plan 7 starts recording guardrail and MCP audit events. Plan 8.5 closes PR #21 review gaps in shadow promotion fidelity, one-key scan coverage, golden-harness CLI wiring, command timeouts, shadow copy cost, and fitness-gate telemetry cost before Sprint 1 sign-off is treated as complete. Plan 9.5 composes the Phase 1 primitives into a working local-first coding agent before Plan 10 adds context-window intelligence. Plan 10 stays last regardless: it depends on inputs from Plans 4, 5, 6, 6.5, 7, 9, and 9.5, and its PDF fold-in is explicitly deferred until calibration is accepted.
