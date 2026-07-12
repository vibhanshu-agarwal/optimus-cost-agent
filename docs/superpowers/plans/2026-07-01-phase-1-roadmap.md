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

**Status:** Approved for implementation. Owns the Phase 1 working-agent sign-off gate; Plan 11 does not start before this gate passes.

### Plan 9.6 closure — remaining work (see Plan 9.75)

Subprocess and operator proof tiers are green. The real-IDE HITL claim, ACP
`toolCall` on `session/request_permission`, and committed Zed artifact remain
open — **all tracked in Plan 9.75**
(`docs/superpowers/plans/2026-07-09-plan-9-75-zed-hitl-acp-toolcall-permission.md`).
Do not maintain a separate checklist here; use Plan 9.75 tasks and DoD.

**Already landed from the original closure list:** operator/IDE launch path
standardized on `uv tool install --editable .` (README + Plan 9.6 workarounds).

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

**Status:** Merged to `main` (2026-07-09, PR #32). Operator infra path manually verified on
Windows (global PATH install, `--setup`, `--check-config --strict`, auto-start). IDE turn
completion deferred to Plan 9.75. Windows-only scope for now (Linux/WSL keyring-backend support
deferred). Orthogonal to Plan 9.6 live-verification scope — changes how local dependencies get
started, not whether the agent's behavior against them is proven.

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
deferred, not claimed.

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
  audit) is deferred to a future plan scheduled after Plan 9.9.

## Plan 9.87 (Tracked, Not Yet Scheduled): Model-Initiated Replanning and Live Refusal Evidence

**Raised:** Deferred from Plan 9.85 as `P9.85-FU-4` and `P9.85-FU-5` when closing the
oversized-required-context workflow.

**Initial scope:**
- Let a model enter the bounded guarded READ_MORE workflow when Plan 9.8 context fits but is
  insufficient for a safe WRITE, without imposing multi-turn cost on tasks that settle single-pass.
- Produce real `acpx` evidence that the live model emits `REFUSE:` and that ACP surfaces
  `PLANNING_MODEL_REFUSED` with sanitized text, zero plan hash, zero permission requests, zero
  mutation, and `end_turn`.

**Status:** Tracked, not yet scheduled; no implementation plan exists. This planning-loop lane is
separate from Plan 9.9 packaging/credential diagnostics and from Plan 11 intelligent
selection/compression — do not fold this scope into either.

## Plan 9.9 (Tracked, Not Yet Scheduled): Operator Packaging and Credential Diagnostics

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

**Status:** Tracked, not yet scheduled; no implementation plan exists. Until Plan 9.9 lands, Plan
9.8's live operator gate must use `uv tool install --editable . --reinstall`. Do not silently
change that gate to a non-editable install or fold these packaging/credential concerns into Plan
9.8's context-selection implementation.

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
    2026-07-09).** Operator infra path verified; IDE `session/prompt` completion deferred to
    Plan 9.75.
14. Plan 9.75: Zed HITL — ACP `toolCall` on `session/request_permission` + real Zed turn
    completion (P0, drafted — depends on Plan 9.7 operator PATH install for verification; see
    `docs/superpowers/plans/2026-07-09-plan-9-75-zed-hitl-acp-toolcall-permission.md`).
15. Plan 9.8: Task-aware workspace context for planning — implemented and live-verified 2026-07-11;
    exact-path Zed mutation under filler pressure proven; ambiguous refusal on-wire with Zed stay-up
    deferred as P9.8-FU-5; evidence in `reports/plan-9-8-task-aware-context-evidence.md`.
16. Plan 9.85: Multi-turn read-observe-replan workflow — implemented and live-verified
    2026-07-12 for the oversized-required-context trigger; deferred from Plan 9.8 as P9.8-FU-1;
    closes the gap where required context exceeds the single-pass budget; evidence in
    `reports/plan-9-85-multi-turn-acpx-evidence.md`.
17. Plan 9.87: Model-initiated replanning and live refusal evidence — tracked, not yet scheduled;
    deferred from Plan 9.85 as P9.85-FU-4 and P9.85-FU-5.
18. Plan 9.9: Operator packaging and credential diagnostics — tracked, not yet scheduled; owns
    cross-layer provider/key mismatch diagnostics and non-editable-install root discovery.
19. Plan 10: Unified Gateway Capabilities Broker — tracked, not yet scheduled.
20. Plan 11: Context window optimization and intelligent selection — tracked, not yet scheduled;
    starts only after Plan 9.8, Plan 9.5 task-level agent orchestration, and the real golden
    harness are stable.

The recommended sequence builds the executable release skeleton while ensuring the higher-risk guardrail surface is stable before Plan 7 starts recording guardrail and MCP audit events. Plan 8.5 closes PR #21 review gaps in shadow promotion fidelity, one-key scan coverage, golden-harness CLI wiring, command timeouts, shadow copy cost, and fitness-gate telemetry cost before Sprint 1 sign-off is treated as complete. Plan 9.5 composes the Phase 1 primitives into a working local-first coding agent; Plan 9.8 establishes the specific task-aware context correctness floor before Plan 11 adds context-window intelligence. Plan 11 stays last regardless: it depends on Plan 9.8 and inputs from Plans 4, 5, 6, 6.5, 7, 9, and 9.5, and its PDF fold-in is explicitly deferred until calibration is accepted.

Plan 9.9 follows Plan 9.8 as a separate operator-runtime hardening lane. It owns the two deferred
Plan 9.7 packaging/credential diagnostics and does not expand Plan 9.8's context-selection scope.
Plan 9.8 continues to use an editable operator install for live proof until Plan 9.9 establishes
and verifies the non-editable-install root contract.
Plan 9.85 is a separate lane from both Plan 9.8 and Plan 9.9: it extends Plan 9.8's single-pass
correctness floor to bounded multi-turn planning when required context cannot fit one pass, and it
neither depends on nor blocks Plan 9.9. Plan 9.85 is implemented and live-verified for the
oversized-required-context trigger; `P9.85-FU-4` (model-initiated replanning when Plan 9.8 context
already fits) and `P9.85-FU-5` (live model-emitted `REFUSE:` demonstration) are explicitly deferred
to the newly tracked **Plan 9.87**, which follows Plan 9.85 and precedes Plan 9.9 in the sequence
above and is not itself implemented.

Plans 9.6 and 9.7 sit alongside each other, not in a strict dependency order: Plan 9.6 owns the Phase 1 working-agent sign-off gate (live Redis/Gateway/e2e proof plus the real-IDE HITL artifact) and Plan 11 does not start until it passes; Plan 9.7 only changes how an operator's local Redis/Gateway dependencies get started before a session and does not touch what Plan 9.6 proves or gate. Plan 9.7 merged independently of Plan 9.6's remaining open HITL item. **Plan 9.75** follows Plan 9.7 in the recommended sequence: it fixes the open Zed HITL / `toolCall` permission payload and closes Plan 9.7's deferred planning-bar DoD using the Plan 9.7 operator PATH install for manual verification. Plan 10 is tracked separately and not yet scheduled or designed; do not fold its gateway-capability-broker scope into 9.6, 9.7, or 9.75 when picking up either.
