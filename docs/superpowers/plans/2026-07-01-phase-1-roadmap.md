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

## Plan 7: Usage Accounting, Evidence Ledger, and Observability

**User story:** As a FinOps reviewer, I can reconcile every billable call from gateway response to persisted usage and evidence records.

**Source anchors:**
- Architecture sections 4, 5, and 12.
- LLD sections 9E, 10, 10A, and 11A.
- Test Strategy section 8.

**Expected deliverables:**
- `GatewayUsage`, `ProviderUsage`, usage accounting service, Redis HASH/TimeSeries adapter boundaries, JSONL telemetry event schema, and reconciliation methods.
- Tests proving `gateway_request_id`, provider, cache_hit, billing_units, cost_usd, native_unit, optimus_credits_debited, model/version, run_id, and session_id are recorded from gateway response fields and not estimated post-hoc.

## Plan 8: Retry, Fitness Gates, Golden Tasks, and Release Gate

**User story:** As a release owner, I can prove the system fails closed, retries boundedly, passes coverage, and completes one-key release gates.

**Source anchors:**
- Architecture sections 3, 6, 9, and 12.
- LLD section 11.
- Test Strategy sections 9, 12, and 13.

**Expected deliverables:**
- Failure classification, retry/backoff policy, max 3 transient retries, composite gate results, golden task fixtures, and release-gate runner.
- Tests proving permanent failures do not retry, transient failures cap at 3 attempts, gate failures leave no partial writes, golden tasks validate expected mode/tools/cost band/final state, and full release gate runs with only Optimus credentials.

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

## Recommended Sequence

1. Plan 1: Core runtime and ACP transport.
2. Plan 2: Mode/state/mutation boundary.
3. Plan 3: Gateway-only configuration and gateway client.
4. Plan 4: Tool policy and evidence acquisition.
5. Plan 7: Usage accounting and observability.
6. Plan 8: Retry, fitness gates, and release gates.
7. Plan 5: Permission/pre-tool/shell guardrails.
8. Plan 6: Prompt-injection/MCP/CI parity.
9. Plan 9: Bounded loops and curated workflow skills.

The recommended sequence builds the executable release skeleton before expanding the higher-risk guardrail surface. If the project goal shifts toward safety certification before gateway functionality, move Plans 5 and 6 immediately after Plan 2.
