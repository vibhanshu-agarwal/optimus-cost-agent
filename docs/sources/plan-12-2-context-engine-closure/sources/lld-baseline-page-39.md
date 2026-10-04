Target contract after the named trusted-policy / Task 11 / coverage migration as applicable; the dated inactive production baseline is stated on the cover.

# 12. Guardrail and Workflow Component Contracts

All model-touching guardrails use the same loopback Gateway, developer aggregator account, actual accounting and explicit evaluation caps, provider-reported cost, and OTel trace path.

This section specifies the Phase 1 enforcement and workflow components introduced as a cross-cutting
concern in HLD §13. The authoritative policy rationale lives in the companion Agent Execution
Guardrails & Workflow Strategy v1.4 (§2-§9); the representative Pydantic type shapes are in its
§10.2. The contracts below are owned by this section. All model-touching elements (the borderline
classifier and the loop completion evaluator) route through the Optimus Gateway under the existing
developer aggregator account and normalized ledger (§0A, §10A); the guardrails introduce no second
cost path.

## 12A. Permission & Pre-Tool Enforcement

PermissionPolicy evaluates mode -> user_deny -> project_allow -> impact -> classifier and returns
a single PermissionDecision (ALLOW | DENY | HOLD); deny always precedes allow; the
classifier cannot overturn a deny.

PermissionDecision contains verdict, layer, rule_id, reason, and
requires_human_approval.

PreToolGuard fires after the agent assembles a tool call, before execution (cf. PreToolUse), for
every tool class (bash, file_edit, mcp_call, web); deterministic checks run before any classifier.
It returns PreToolResult.

CommandSafetyValidator is a local, in-process shell validator covering destructive commands,
pipe-to-shell, environment/credential access, Unicode homoglyph/confusable characters, ANSI/control
sequences, insecure transport, and unexpected network egress. Satisfiable by Tirith or an equivalent
validator; the design takes no hard dependency on any one implementation.

ToolInvocationAuditEvent is an append-only record of each decision (verdict, layer, failed checks,
approver) feeding the same trace sink as evidence and cost telemetry.

## 12B. Prompt-Injection & MCP Supply-Chain Trust

MCPTrustRegistry captures server_id, manifest_hash, allowed_tools, permission_scope, and
approved. MCP servers are never auto-loaded from cloned repositories; a manifest-hash change
forces re-approval; tool descriptors (name/description/schema) are inspected for injection before
being surfaced to the planner.

ConfigTrustScanner treats agent config and rule files as code, scanning on ingest for embedded
instructions, exfiltration endpoints, and homoglyph/ANSI content before they may influence behavior.

## 12C. Bounded Agent Loops

GoalLoopController, IterationState, CompletionEvaluator, ProgressLedger,
LoopBudgetPolicy (max_iterations, max_wall_clock_minutes, repeated_failure_limit; monetary policy only for explicitly capped evaluation callers), and
LoopStopReason (COMPLETED | MAX_ITERATIONS | WALL_CLOCK | REPEATED_FAILURE | HUMAN_HALT; BUDGET_EXHAUSTED only for independent evaluation) are the bounded-loop contracts.

Persistent state lives in files, git history, task manifests, traces, and the evidence ledger (§9E),
not in an ever-growing chat context. The pre-tool guard (§12A) is never bypassed inside a loop, and
the completion evaluator is a reserved cheap Gateway-routed capability. This section does not claim it is active; unknown costs do not latch a product goal loop. Task 11 removes the product monetary predicates on the reviewed cf9bb9d branch. Independent evaluation monetary policy remains explicit.