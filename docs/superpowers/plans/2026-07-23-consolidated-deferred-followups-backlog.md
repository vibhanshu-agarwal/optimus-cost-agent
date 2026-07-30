# Consolidated Open Work Pool

## Purpose

This document is the single source of truth for all currently open work: charter-ratified feature
slices, deferred follow-ups, parked items, and tracked defects. It owns each item's existence and
state; the relevant charter or source document owns scope, sequencing, and detailed acceptance
criteria. Anything not listed here is not tracked.

Before this document existed, each follow-up lived only inside the "Deferred Follow-Ups" section of
whichever plan originally raised it, cross-referenced (if at all) by a one-line mention in the
roadmap. Two of them (Plan 9.98-FU-1 and FU-2) were fully implemented and merged without ever
getting a roadmap entry at all, discovered only by manual audit. This document exists so that stops
happening: everything still open lives in exactly one place, and nothing gets promoted into a real
plan without being removed from the open pool first.

This document does not itself implement anything. Every open entry below either becomes its own
numbered plan (following [[plan-numbering-convention]]-style sequential allocation) or gets folded
into an already-designated future plan (e.g. Plan 12 or a reviewed Plan 11 feature slice) when that plan is actually
scheduled. The roadmap's Plan 11 v1.0 milestone section links here; it does
not duplicate this content.

## How to use this document

- **Adding a new item:** When a plan's implementation or review surfaces a new deferred follow-up
  (including ones emerging from Plan 9.96 Task 9 or Plan 11 feature work), record it here first
  with the same fields every other entry uses (Raised / Origin / Designated future plan /
  Trigger or acceptance criteria / Status). Other documents may link to the entry, but must not
  carry its live open-item status or become a second pool.
- **Promoting an item:** When an item is scheduled into a real numbered plan, mark its Status as
  `Promoted -> Plan N` with the date and a link to the new plan file, and leave the entry in place
  (do not delete history) rather than removing the row.
- **Closing an item:** When an item is fully implemented, mark Status as `Closed` with the
  implementation commit/PR and evidence citation, the same way other closed follow-ups are recorded
  elsewhere in this project's roadmap.

## Feature slices

The pool owns each feature's existence and state; the [Plan 11 v1.0 milestone charter](2026-07-25-plan-11-v1-milestone-charter.md)
owns feature scope and sequencing. Plan 12 is listed so its post-v1.0 custody cannot fall off the
open-work inventory.

| Identity | State | Scope detail |
|---|---|---|
| `P11-FEAT-GATEWAY-CORE` | Plan 11.1 — closed; merged to `main` as PR #85 (`6ae6997`, tip `6c39599`). Migration closed by **Plan 11.4**, merged to `main` as PR #91 (`d80e112`), 2026-07-28; no migration follow-ups remain open under this identity | [Charter](2026-07-25-plan-11-v1-milestone-charter.md#p11-feat-gateway-core---gateway-core-and-observability-route); migration custody: strict-loopback completion, OpenRouter-default OpenAI-compatible aggregator transport, provider-reported accounting, and direct-adapter retirement — all implemented and independently re-verified task-by-task. The bounded Vercel Python transport check is complete as a design decision: Vercel is backlogged under this identity (its public OpenAI-compatible transport doesn't document the mandatory per-response provider-cost fields the settled `GatewayUsage` contract requires; no comparison matrix, no second endpoint added). Closure evidence: [design spec](../specs/2026-07-28-plan-11-4-p11-feat-gateway-core-migration-design.md), [implementation plan](2026-07-28-plan-11-4-gateway-core-migration.md) (all 36 checkboxes checked against their named verification commands) |
| `P11-FEAT-GATEWAY-TOOLS` | Plan 11.2 — closed by PR #88 (merge `4590dbf`); migration follow-ups remain assigned here and receive a new Plan 11.x number only at pickup | [Charter](2026-07-25-plan-11-v1-milestone-charter.md#p11-feat-gateway-tools-and-p11-feat-gateway-cost-obs); migration custody: deterministic search/direct extract, route-specific dependency availability, replacement acceptance, and Tavily rollback-reviewed retirement; closure evidence: [Plan 11.2 approval](../reviews/2026-07-27-plan-11-2-implementation-plan-approval-v2.md), [local-process evidence](../../../reports/plan-11-2-gateway-tools-local-process-evidence.md), [staging evidence](../../../reports/plan-11-2-gateway-tools-staging-evidence.md), and [fitness report](../../../reports/plan-11-2-gateway-tools-task7-fitness.md) |
| `P11-FEAT-GATEWAY-COST-OBS` | Plan 11.5 — closed by PR #95 (merge `e388258`), 2026-07-29; migration follow-ups remain assigned here (`P11.5-FU-1` open; `P11.5-FU-2` closed via Plan 11.6) and receive a new Plan 11.x number only at pickup | [Charter](2026-07-25-plan-11-v1-milestone-charter.md#p11-feat-gateway-tools-and-p11-feat-gateway-cost-obs); [implementation plan](2026-07-28-plan-11-5-p11-feat-gateway-cost-obs-implementation.md); migration custody: OTel/OTLP-to-Phoenix and the separately reviewed USD field migration |
| `P11-FEAT-GATEWAY-MCP` | Ratified; operator confirmed MCP support on 2026-07-29 (`P11-FU-3` decision half closed). Still blocked on the route/typed-contract design and fresh requirement extraction—no MCP endpoint is shown or implied yet; plan number assigned at pickup | [Charter](2026-07-25-plan-11-v1-milestone-charter.md#p11-feat-gateway-mcp---gateway-mcp-tool-call-brokering) |
| `P11-FEAT-ZED-RESUME` | **Plan 11.7 picked up 2026-07-29; implementation plan drafting/review in progress.** Carries owned `P11-FU-1` and `P9.8-FU-5`; coordinates, but does not own, `P11-FU-4` | [Charter](2026-07-25-plan-11-v1-milestone-charter.md#p11-feat-zed-resume---zed-integration-fixes-and-session-resume) |
| `P11-FEAT-REGISTRY` | Ratified, unscheduled; blocked on its research gate — no authoritative source exists in any of the four pinned documents. Also owns the v1.0 release-version contract | [Charter](2026-07-25-plan-11-v1-milestone-charter.md#p11-feat-registry---acp-registry-registration-and-v10-cut) |
| `P11-FEAT-IDE` | Conditional — opens only by explicit amendment if REGISTRY surfaces an unmet multi-IDE expectation | [Charter](2026-07-25-plan-11-v1-milestone-charter.md#p11-feat-ide---conditional-ide-specific-testing) |
| `P11-FEAT-REDACTION-GATE` | **HIGH; ratified, unscheduled.** First slice in the future independent handoff/evidence train because it unblocks sanitized Plan 11.7 Task 0 evidence. The eventual plan number is assigned at pickup; no number is reserved by this row. | Type-dispatched, fail-closed artifact gate: parse/sanitize/reserialize JSON and NDJSON; stream-sanitize logs and notes; strip screenshot metadata and require human approval; quarantine dumps and retain hashes only. Redact API keys and PII using exact runtime-known-secret matching plus pattern/entropy detection and path canonicalization. Preserve session/run IDs, model/provider names, and git SHAs. [Design draft](../specs/2026-07-30-p11-feat-redaction-gate-design.md). |
| `P11-FEAT-EVIDENCE-COLLECTOR` | Ratified, unscheduled; sequenced after `P11-FEAT-REDACTION-GATE`. The eventual plan number is assigned at pickup; no number is reserved by this row. | One `tools/evidence_gather.py` entry point with subcommands, declarative scenarios, composable collectors/detectors, and the redaction gate as a separately invocable final stage. Outcomes are `rendered_stable`, `rendered_then_crashed`, `client_crashed`, or `indeterminate`; no hardcoded model literals or default report targets. Its Zed prompt-injection gate remains investigation-only until UIA/SendInput on Zed 1.13.1, the `zed://` scheme, and hermetic `--user-data-dir` instances produce evidence. |
| `P11-FEAT-A2A-LEDGER` | Ratified, unscheduled; sequenced after the redaction gate and evidence collector. **Blocked on the cross-agent localhost-TCP reachability investigation** for Claude Code, Cursor, and Codex. The eventual plan number is assigned at pickup; no number is reserved by this row. | Default-off, opt-in append-only handoff protocol—not a transcript archive—with question, answer, evidence-notice, review-ruling, handoff, and separate acknowledgement entries; large payloads use SHA-256 references. PostgreSQL in Docker is primary only if the reachability spike passes; otherwise use global SQLite under a non-cloud-synced `%LOCALAPPDATA%`-class path. Keep the store independent of Redis/general memory, preserve reviewer/implementer role separation, apply ingress redaction before every write, and place any eventual container configuration in Plan 11.6's consolidated startup source of truth. |
| `P11-FEAT-APPROVAL-RECORD` | Design-needed, investigation only; ratified and unscheduled. Independent of the approved redaction-gate design and implementation plan, and blocks neither. The eventual plan number is assigned at pickup; no number is reserved by this row. | Generalize the redaction gate's digest-bound screenshot approval record into an operator Approval/Denial Record for exact artifacts. This is a convenience audit trail, explicitly **not** a security control, authorization mechanism, or cryptographic proof: it records the artifact digest, decision, timestamp, and asserted identity, including denials as well as approvals. The implementing agent never produces the record and only references one by digest; impose no interactive unlock or key management in its path. Voice is out of scope. The record may reserve an optional, unused signature field so future asymmetric signing is additive, but the artifact itself must not be called a signature. `authority=operator-relay` in the A2A ledger remains asserted, not cryptographically proven. |
| `Plan 12` | Post-v1.0 context-window and intelligent-selection lane; outside the v1.0 cut | [Charter boundary](2026-07-25-plan-11-v1-milestone-charter.md#explicit-exclusions-and-unresolved-inputs) |

## Open items

### P9.8-FU-2: Intelligent ambiguous-reference ranking

**Raised:** 2026-07-10, in Plan 9.8's own Deferred Follow-Ups
(`docs/superpowers/plans/2026-07-10-plan-9-8-task-aware-workspace-context.md`).

**Designated future plan:** Plan 12 (Context Window Optimization and Intelligent Selection).

**Acceptance criteria:** Candidate ranking uses the accepted relevance/trust/freshness/dependency
policy, measures wrong-target regret, and retains a fail-closed threshold. Until this lands,
ambiguity stays visible and deterministic (Plan 9.8's current behavior).

**Status:** Scheduled in Plan 11.7 (`P11-FEAT-ZED-RESUME`); open pending the current-Zed
pre/post refusal-rendering evidence and reviewed disposition.

### P9.8-FU-3: Dynamic context budgets and required-file summarization

**Raised:** 2026-07-10, in Plan 9.8's own Deferred Follow-Ups
(`docs/superpowers/plans/2026-07-10-plan-9-8-task-aware-workspace-context.md`).

**Designated future plan:** Plan 12 (Context Window Optimization and Intelligent Selection).

**Acceptance criteria:** Budget changes are model-aware, cost-attributed, injection-safe, measured
against the null baseline, and never silently omit required evidence.

**Status:** Open, not yet scheduled.

### P9.8-FU-5: Zed Refusal-Rendering Stability

**Raised:** 2026-07-11 during Plan 9.8 live evidence. Zed 1.10.2 correctly received and briefly
rendered the ambiguous-refusal corrective text, then panicked in native client code with
`range end index 3 out of range for slice of length 2`. The agent wire contract and independent
`acpx` durable refusal UI remain proven.

**Designated slice:** `P11-FEAT-ZED-RESUME` (plan number assigned at pickup). Plan 9.75 was already complete
when the client-stability issue was discovered, and its evidence report classifies the panic as
separate from the ACP conformance fix. Do not reopen Plan 9.75 and do not fold this work into Plan 12.

**Acceptance criteria:** Reproduce against a supported current Zed build, separate agent payload
correctness from client rendering behavior, preserve the existing fail-closed refusal contract, and
produce durable operator-visible refusal evidence or an explicit externally owned Zed defect
disposition. Any agent-side workaround requires its own reviewed plan and must not weaken ACP
conformance.

**Evidence anchors:** `reports/plan-9-8-task-aware-context-evidence.md`,
`reports/plan-9-75-zed-hitl-runtime-evidence.md`, and the Plan 9.8 `P9.8-FU-5` acceptance criteria.

**Status:** Open, not yet scheduled.

### P9.85-FU-1: Intelligent observation compression

**Raised:** 2026-07-11, in Plan 9.85's own Deferred Follow-Ups
(`docs/superpowers/plans/2026-07-11-plan-9-85-multi-turn-read-observe-replan.md`).

**Designated future plan:** Plan 12 (Context Window Optimization and Intelligent Selection).

**Acceptance criteria:** An approved design may replace fixed fail-closed carryover with
provenance-preserving compression, regret measurement, and calibration gates. Until then, overflow
remains terminal (Plan 9.85's current behavior).

**Status:** Open, not yet scheduled.

### P9.85-FU-2: Dynamic planning-evidence partition

**Raised:** 2026-07-11, in Plan 9.85's own Deferred Follow-Ups
(`docs/superpowers/plans/2026-07-11-plan-9-85-multi-turn-read-observe-replan.md`).

**Designated future plan:** Plan 12 (Context Window Optimization and Intelligent Selection).

**Acceptance criteria:** Calibrated evidence justifies changing the fixed 4 KiB/12 KiB
observation/current-read split without weakening Plan 9.8's completeness and ambiguity guarantees.

**Status:** Open, not yet scheduled.

### P9.85-FU-3: Cross-Run/Session Spend Policy

**Raised:** 2026-07-11, in Plan 9.85's own Deferred Follow-Ups
(`docs/superpowers/plans/2026-07-11-plan-9-85-multi-turn-read-observe-replan.md`), disclosed as
owned by an unnamed future budget-governance plan rather than silently dropped.

**Designated future plan:** None yet named — a future budget-governance plan.

**Acceptance criteria:** Define an operator-configurable cumulative session/project spend ceiling
above the existing per-run `max_cost_usd` monotonic limit and the Plan 7 usage ledger. Any new
cross-run/session ceiling must not weaken or duplicate the existing per-run
monotonic-tighten-or-exact approval contract (Plan 9.96), must be enforced from the same reconciled
Plan 7 usage ledger rather than a new parallel accounting path, and must fail closed rather than
silently permit overspend when ledger data is unavailable. Plan 9.85 records all usage completely
and accurately but does not itself invent any cross-run denial policy.

**Architecture resolution (2026-07-28):** The repaired HLD v2.16 §§5A and 11, LLD v2.39 §§0A,
9D, and 10A, Guardrails v1.1 §§7.2 and 9, and the refreshed requirement inventory settle the
local Gateway as the authority for current-run budget caps, provider-reported usage/cost, and the
reconciled cost ledger. The prior architecture conflict about a hosted budget service is resolved.
This entry does not define a cumulative session/project ceiling: that policy remains open,
undesigned, and unscheduled under a future budget-governance plan.

**Plan 11 disposition:** Architecture-unblocked; no implementation or cumulative cross-run policy
design is included in Plan 11. Revisit only under the future budget-governance plan.

**Status:** Open, not yet scheduled.

### P9.87-FU-1: Mechanical Current-Raw-Evidence Grounding Guard

**Raised:** 2026-07-12, in Plan 9.87's own Deferred Follow-Ups
(`docs/superpowers/plans/2026-07-12-plan-9-87-model-initiated-replanning-live-refusal.md`). Carried
forward, unresolved, through Plan 9.88's closure ceremony and Plan 9.95's custody-transfer record.

**Designated future plan:** Plan 11 feature work; no feature slice or plan number is assigned yet.
This item was formerly the sole follow-up in the retired Plan 9.97 lane and is now carried by this
pool without a Plan 10.x slot.

**Trigger:** A content-correct FU-5 final plan or later evidence shows exact policy bytes can pass
through observations despite the prompt prohibition.

**Acceptance criteria:** Define mechanical provenance between final WRITE content and current-turn
raw ranges without logging source bodies or silently absorbing Plan 12's intelligent-selection
scope. This lane must not absorb or be absorbed by Plan 12.

**Status:** Open, not yet scheduled. This pool records promotion and disposition when this item is
picked up; no Plan 10.x slot is reserved.

### P11-FU-1: ACP Session Resume Capability

**Raised:** 2026-07-25 during Plan 11 scoping. The current ACP adapter dispatches `initialize`,
`session/new`, and `session/prompt`, but has no `session/load` handler. Its initialization response
advertises an empty `sessionCapabilities` object, so the client correctly concludes that resume is
unsupported and starts a new session on every connection.

**Origin:** `src/optimus/acp/spec.py` (`AcpDuplexAdapter.handle_client_request` and
`_handle_initialize`), with the live server wiring `InMemoryAcpSpecSessionStore` in
`src/optimus/acp/server.py`.

**Designated slice:** `P11-FEAT-ZED-RESUME` (plan number assigned at pickup). This item is
owned by `P11-FEAT-ZED-RESUME`, not parked or deferred to a later milestone.

**Acceptance criteria:** The reviewed `P11-FEAT-ZED-RESUME` design and implementation must:

- implement ACP `session/load` and advertise `loadSession` only when its semantics are supported;
- define the session identity, workspace binding, conversation/history, and relevant run metadata
  that persist across client/process boundaries;
- select and document a durable storage mechanism, TTL/expiry, deletion, migration/versioning,
  retention, and storage-failure behavior as a first-class design decision;
- restore the session in the protocol-required shape, including conversation replay or the exact
  supported load semantics, without silently substituting `session/new`; and
- cover successful load, unknown/expired sessions, workspace mismatch, malformed or unavailable
  storage, capability negotiation, and history replay with unit/integration/live ACP evidence.

`InMemoryAcpSpecSessionStore` is process-local. `RedisAgentStateStore` stores expiring agent plans
(`AgentPlanRecord`), not ACP session or conversation state, and cannot be treated as an existing
resume store without an explicit design and migration decision.

**Status:** Scheduled in Plan 11.7 (`P11-FEAT-ZED-RESUME`); open pending implementation and
real-`acpx`/Zed evidence. This is an unimplemented protocol capability, not a flaky regression or
a parked architecture blocker.

### P11-FU-2: Package Lookup and Security Advisory Gateway Capability

**Raised:** 2026-07-25 during the Plan 11 Gateway requirement review. At intake, the pinned LLD named
`POST /v1/tools/package/lookup` and `POST /v1/tools/security/advisory` as Gateway-facing typed
endpoints, and §9A/§9B define their package/advisory tool class and routing signals. At intake, the
local repository did not yet implement these Gateway routes as dedicated endpoints. Existing policy
behavior is not absent: `src/optimus/tools/policy.py:85-93` routes `DEPENDENCY_VERSION_CHECK` and
`SECURITY_OR_CVE_CHECK` into `WEB_SEARCH_TRIGGERS`, while LLD §9B's `DEFAULT_POLICY_MATRIX`
(p.26) maps both signals to `ToolClass.PACKAGE_AND_ADVISORY_METADATA`. At intake, dependency and
CVE evidence was therefore served via generic web search, against a different tool class than the
LLD specified. Picking up FU-2 changed existing, tested policy behavior, not merely adding routes.

**Origin:** `docs/Optimus-Cost-Agent-LLD-v2.39.pdf`, §0.D (p.3), §9A (p.24), and §9B (p.25).

**Designated slice:** `P11-FEAT-GATEWAY-TOOLS` (Plan 11.2 at pickup). This capability was
implemented and closed in PR #88 / merge `4590dbf`; future search-independence and migration work
remains owned by the same feature identity. It is not part of the `P9.85-FU-3` cumulative
cross-run policy. The reviewed artifacts are the [design specification](../specs/2026-07-26-plan-11-2-p11-feat-gateway-tools-design.md)
and [implementation plan](2026-07-26-plan-11-2-p11-feat-gateway-tools-implementation.md).

**Acceptance criteria:** The reviewed `P11-FEAT-GATEWAY-TOOLS` design and implementation must:

- define and serve the package-registry lookup and security-advisory request/response contracts;
- route `PACKAGE_AND_ADVISORY_METADATA` using `PACKAGE_VERSION` and `SECURITY_ADVISORY` signals;
- preserve the one-key boundary, Gateway-side provider secrets, policy revalidation, usage/cost
  envelope, and evidence/provenance contracts; and
- provide named unit, integration, and real-Gateway evidence for both endpoint families.

**Closure evidence:** The checked Plan 11.2 Definition of Done and closing approval are recorded
in the [v2 approval record](../reviews/2026-07-27-plan-11-2-implementation-plan-approval-v2.md).
Named evidence reports are the [real local-process HTTP artifact](../../../reports/plan-11-2-gateway-tools-local-process-evidence.md),
[real staging-Gateway artifact](../../../reports/plan-11-2-gateway-tools-staging-evidence.md), and
[fitness/release-gate report](../../../reports/plan-11-2-gateway-tools-task7-fitness.md).

**Status:** Closed by PR #88 / merge `4590dbf`; the dedicated package/advisory routes and their
evidence are complete. Remaining migration work stays with `P11-FEAT-GATEWAY-TOOLS` and is not a
reopening of this closed item.

### P11-FU-3: MCP Support Decision After LLD §0.B Source Repair

**Raised:** 2026-07-25 during the Plan 11 Gateway requirement review. The original LLD §0.B was
clipped at the rendered page boundary around `/v1/tools/web/extract`, and §0.C named MCP tool
brokering without an MCP endpoint or Gateway request/response shape in §0.D.

**Origin:** `docs/Optimus-Cost-Agent-LLD-v2.39.pdf`, §0.B (rendered p.2), §0.C (p.3), and §0.D
(p.3), final SHA-256 `82513729FD1A6E87FAD310DD90A18C996981B68024204E56CCA65377495585DE`.

**Completed source repair:** The v2.39 §0.B clip and hosted-content repair are complete. The
published source is extractable, its component flow is complete, and the §0.B diagram states that
no MCP endpoint is shown or implied. The repair is documentation-complete; it does not authorize
MCP implementation or endpoint inference.

**Operator decision (2026-07-29):** Affirmative—MCP brokering is supported. Operator's stated
rationale: non-negotiable for any agent, especially a coding agent.

**Remaining acceptance criteria:**

- ~~The operator must explicitly decide whether MCP brokering is supported.~~ Decided 2026-07-29:
  yes.
- A separately reviewed Gateway route and typed request/response contract must still be authored,
  source-pinned, and followed by fresh requirement extraction before any implementation plan is
  promoted. This design/contract work has not started.

**Status:** Decision half closed (2026-07-29: MCP brokering is supported).
`P11-FEAT-GATEWAY-MCP` remains blocked pending the route/contract design and requirement
extraction—not yet ready for an implementation plan. `P11-FEAT-ZED-RESUME` was picked up instead
as Plan 11.7; this entry stays open and unscheduled.

### P11-FU-4: Re-pin FU-4A/FU-5 Live Evidence

**Raised:** 2026-07-15 by the Plan 9.95 Task 5 implementation amendment.

**Origin:** `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, historical backlog section §776.
The Plan 9.87 `fu4a` and `fu5` evidence gates fail with implementation drift against the current
codebase, so fresh live evidence must be captured and re-pinned.

**Designated slice:** Coordinate with `P11-FEAT-ZED-RESUME` where the Zed live-evidence
capture path overlaps; no Plan 11.x plan number is allocated by this entry.

**Acceptance criteria:** Re-capture fresh real-`acpx` FU-4A and FU-5 evidence against the current
codebase, select the reviewed sanitized capture path, record the exact evidence and implementation
SHAs, and close or explicitly disposition the freshness gap before the v1.0 cut.

**Status:** Tracked, not yet scheduled; no implementation plan exists. Evidence-freshness class.

### P11-FU-5: Windows Subprocess Handle-Duplication Flake (WinError 6/50)

**Raised:** 2026-07-22 during Plan 9.99 Task 7 repository-wide verification.

**Origin:** `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, historical backlog section §861.
The feasibility findings, including the no-reproduction result and the separately identified
durable-approval identity concern, remain in that roadmap entry.

**Designated slice:** Future Windows investigation; no plan number is allocated.

**Acceptance criteria:** A future pickup must preserve the distinction between the unreproduced
Windows flake and the actionable durable-approval identity concern, establish the applicable
reproduction or non-reproduction disposition, and receive a reviewed custody decision before any
fix or exclusion is claimed.

**Status:** Tracked, not yet scheduled; root cause is not established. The feasibility findings
live in the roadmap entry, and no plan number was allocated. Deliberately not picked up after the
feasibility pass.

### P11-FU-6: Gateway `test_server` Full-Suite Port/Teardown Flake

**Raised:** 2026-07-26 during Plan 11.1 Task 7 final sign-off (PR #85 / `P11-FEAT-GATEWAY-CORE`).

**Origin:** Intermittent failure of
`tests/unit/optimus_gateway/test_server.py::test_tools_routes_remain_not_found` observed once in
five consecutive full-suite runs (`uv run --frozen pytest -q` and the same suite under `--cov`).
The same test passed every isolation run (single node and the full 24-test `test_server.py` file).
Not connected to Plan 11.1 CORE-route feature correctness — focused and live CORE evidence stayed
green throughout review.

**Suspected cause:** Shared `_start_server()` / `_stop_server()` helpers spin a real
`ThreadingHTTPServer` on an OS-assigned loopback port (`socket.bind(("127.0.0.1", 0))`) per test
(~20 siblings in the file). Likely a Windows-specific port-reuse or thread-teardown race
(`server.shutdown()` / `thread.join(timeout=5)` racing the next test's bind), not an assertion
defect in the failing test.

**Related prior art:** Same Windows test-infra flake class as `P11-FU-5` (WinError 6/50) and the
`agent/cursor/windows-subprocess-handle-flake-backlog` branch. Before scoping a numbered plan,
check whether this shares that root cause; do a feasibility pass before any scoped plan, not
before.

**Designated slice:** Future Windows / gateway unit-harness investigation; no plan number is
allocated (lazy numbering — assign only if/when picked up for scoping).

**Acceptance criteria:** Reproduce or disposition under full-suite load on Windows; determine
whether this is the same root cause as `P11-FU-5` or a distinct bind/teardown race; harden
`_start_server`/`_stop_server` (or equivalent) only after a reviewed feasibility pass; preserve
the CORE-route unit coverage that already passes in isolation.

**Status:** Tracked, not yet scheduled; no implementation plan exists. Feasibility pass required
before promotion.

### P11-FU-7: Windows Coverage/`sys.settrace` Timing Flake in ACP NDJSON Sanitization Test

**Raised:** 2026-07-27 during the Plan 11.3 Task 1 independent review (operator Vibhanshu).
The failure was observed once in a full-suite run for
`tests/unit/acp/test_stdio_ndjson.py::test_serve_ndjson_sanitizes_request_processing_response_and_stderr`;
the same test passed 2/2 when run in isolation. The same failure pattern has previously
recurred during Plan 10.1 and Plan 11.1 verification.

**Origin:** Repeated diagnosis identifies coverage instrumentation / `sys.settrace` timing
sensitivity racing with the test's `asyncio.wait_for(..., timeout=1)`. This is a test-harness
timing flake, not an identified defect in ACP stdio or NDJSON production behavior. The
failure concerns the test's scheduling deadline under instrumentation and must not be
re-diagnosed as an ACP protocol or sanitization regression at each plan pickup.

**Designated slice:** Future Windows / test-infrastructure reliability work; no plan number is
allocated (lazy numbering — assign only if/when picked up for scoping).

**Acceptance criteria:** A future pickup must:

- reproduce or disposition the failure under the relevant Windows full-suite and coverage
  configurations, including a clean isolation comparison;
- verify the diagnosis against the test's `asyncio.wait_for(..., timeout=1)` deadline and
  coverage / `sys.settrace` instrumentation timing, distinguishing it from a production
  stdio/NDJSON failure;
- apply a reviewed, narrowly scoped test-infrastructure remedy (or document a durable
  non-reproduction/disposition) without weakening the assertions that request-processing,
  response, and stderr sanitization remain correct;
- demonstrate that the remedy does not hide genuine ACP stdio/NDJSON regressions and record
  the exact Windows, pytest, coverage, and test-suite conditions used; and
- preserve the existing independent test evidence, with no production-code change claimed
  unless new evidence establishes a separate production defect.

**Related prior art:** Follow the Windows/test-infrastructure flake custody pattern used by
`P11-FU-5` (WinError 6/50 subprocess handle-duplication) and `P11-FU-6` (gateway `test_server`
port/teardown race). This item is distinct: its established mechanism is coverage
instrumentation / `sys.settrace` scheduling pressure around an `asyncio.wait_for` deadline
in a unit test, with no current evidence of a subprocess-handle or port-teardown defect.

**Status:** Tracked, not yet scheduled; no implementation plan exists. Root cause is already
diagnosed as coverage/trace instrumentation timing sensitivity; do not reopen ACP production
debugging from scratch when this entry is picked up.

### P11.5-FU-1: Map live OTLPSpanExporter FAILURE into Gateway QUEUED/retry semantics

**Raised:** 2026-07-29 during Plan 11.5 Task 4 independent operator verification (and matching
linked task review). Confirmed by reading installed
`opentelemetry-exporter-otlp-proto-http` 1.44.0 `OTLPSpanExporter.export()`: every failure path,
including the exporter's internal retry-with-backoff loop, ends in
`return SpanExportResult.FAILURE` and never raises.

**Origin:** Plan 11.5 Gateway `OpenTelemetryTraceExporter` / `_RetryTrackingSpanExporter` only
classifies `exhausted_transient=True` (→ delivery state `queued`) when the delegate *raises*
`TransientTraceExportError`. Against the real SDK exporter that path is unreachable; unit tests
reach `QUEUED` only via an injected `_AlwaysTransientSpanExporter` double. Live collector
outages therefore surface as `failed` rather than `queued`.

**Severity / non-blocking rationale:** Does not crash the agent, does not mask failure as
success, and does not invent cost/accounting. A genuinely transient network hiccup loses
retry-worthiness signal but remains honest (`failed`). Accepted as non-blocking for Task 4
sign-off; must retain named pool custody before Plan 11.5 close.

**Designated slice:** `P11-FEAT-GATEWAY-COST-OBS` (follow-up plan number assigned at pickup —
do not silently fold into an unfinished Task 4/5/8 checkpoint without a reviewed amendment).

**Acceptance criteria:** A future pickup must:

- preserve the four explicit delivery states (`delivered` / `queued` / `failed` /
  `not_configured`) and the rule that a missing endpoint is never reported as successful
  delivery;
- map real `OTLPSpanExporter` / `SpanExportResult.FAILURE` (and any bounded transient class
  the design chooses) into Gateway delivery results without requiring the SDK to raise;
- keep agent-side code free of OTLP/Phoenix endpoints and credentials;
- prove the path with focused unit evidence against a double that returns `FAILURE` (not only
  a raising double), plus at least one live/Phoenix-tier check or an explicit documented
  disposition if live evidence remains Task 8-owned;
- never invent model failure, reverse a completed mutation, or add a model charge when export
  fails.

**Evidence anchors:** Plan 11.5 Task 4 brief/report/review
(`.superpowers/sdd/task-4-*.md` on the Plan 11.5 branch),
`src/optimus_gateway/observability.py`, and `opentelemetry.exporter.otlp.proto.http.trace_exporter`
1.44.0 source for `OTLPSpanExporter.export`.

**Related Task 8 watch (not this FU's scope):** `_emit_spans` starts a fresh empty `Context()`
for every event with no `parent_span_id`, so multiple independent root-level events that share
a wire `trace_id` may land as separate real OTel traces. Task 4 tests only exercise single-root
batches; Plan 11.5 Task 8 real Phoenix evidence must prove or disposition this.

**Status:** Tracked, not yet scheduled; no implementation plan exists. Drafted 2026-07-29 for
operator review of pool custody wording.

### P11-FU-8: Align `OPTIMUS_LOCAL_GATEWAY_BASE_URL` with `OPTIMUS_GATEWAY_<THING>_BASE_URL` naming

**Raised:** 2026-07-29 by operator ([Vibhanshu]) during backlog triage. Priority: **Low**.
Status for pickup: **Needs deeper investigation before scoping — not ready to implement.**

**Origin / substance:** The name is functionally correct but inconsistent with sibling Gateway
env naming (`OPTIMUS_GATEWAY_TAVILY_BASE_URL`, `OPTIMUS_GATEWAY_OSV_BASE_URL`, and similar all use
`OPTIMUS_GATEWAY_<THING>_BASE_URL`). This identifier breaks the pattern as
`OPTIMUS_LOCAL_GATEWAY_BASE_URL`. Candidate rename: `OPTIMUS_GATEWAY_PROVIDER_BASE_URL`.

**Why this is not a quick rename (confirmed by direct investigation):**

- Blast radius: ~20 files / ~65 occurrences across three source packages (`optimus.acp`,
  `optimus_gateway`, `optimus_security`) and at least six test files
  (`tests/unit/acp/test_launch_gate.py` alone has ~15 occurrences; a dedicated
  `tests/unit/security/test_gateway_base_url_resolution.py` exists for this surface).
- The variable **name** feeds the HMAC security-snapshot fingerprint via
  `compute_secret_fingerprint(value, field_name=name, ...)` in `launch_gate.py`. Renaming
  invalidates existing operators' durable launch approvals and requires an explicit migration
  story — not a silent swap.
- `resolve_launch_candidate` fails closed on any unrecognized `OPTIMUS_*` name. An operator's
  existing `.env.gateway` that still carries the old name would hard-break post-rename unless a
  compatibility alias (or dual-accept window) is designed first.
- At least one referencing design
  (`docs/superpowers/specs/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md`)
  is frozen/digest-pinned; its header requires a matching frozen digest for approval, so any
  edit needs a full reviewed amendment rather than an in-place tweak.
- Historical doc surface: nine plan/spec references across six plan/spec identities (the original pre-9.x local-Gateway-service plan, 9.7, 9.96, 9.99, 10.2, 11.4). Frozen/historical docs must be allowlisted by exact path if touched only for census, or
  amended under their own review rules.

**Designated slice / plan shape:** Future small dedicated naming/canonicalization plan
(precedent: Plan 9.99 existed for this class of security-snapshot naming concern). Do **not**
fold a silent rename into an unfinished Plan 11.5 checkpoint or any unrelated feature slice.
Plan number assigned at pickup after the compat-alias + migration design is reviewed.

**Next step before implementation:** Scope a compatibility-alias + durable-approval migration
design (old name accept window, fingerprint transition, fail-closed behavior for mixed/unknown
names, operator docs, and frozen-spec amendment path). Only then commit to the rename target
(`OPTIMUS_GATEWAY_PROVIDER_BASE_URL` or a reviewed alternative).

**Acceptance criteria (draft — refine at pickup):**

- Reviewed design covers alias window, HMAC fingerprint migration, and fail-closed launch-gate
  behavior for stale vs dual names.
- Implementation (when scheduled) updates all live `src` / `tests` / runtime examples /
  `.env*.example` surfaces; does not silently break existing durable approvals.
- Frozen digest-pinned specs are amended under their own approval path or left untouched with
  exact-path historical custody — no broad `docs/**` rewrite.
- Focused regression coverage extends
  `tests/unit/security/test_gateway_base_url_resolution.py` and launch-gate fingerprint tests for
  the chosen migration semantics.

**Evidence anchors:** operator investigation notes (2026-07-29); `src/optimus_security` launch-gate
fingerprint path; sibling env names `OPTIMUS_GATEWAY_TAVILY_BASE_URL` /
`OPTIMUS_GATEWAY_OSV_BASE_URL`; Plan 9.99
(`docs/superpowers/plans/2026-07-22-plan-9-99-credential-uri-security-snapshot-canonicalization.md`)
as process precedent.

**Status:** Tracked, not yet scheduled; **needs deeper investigation / migration design before
scoping**. No implementation plan exists. Filed 2026-07-29 for pool custody.

### P11-FU-9: Client-Supplied ACP `mcpServers` Disposition

**Raised:** 2026-07-29 during Plan 11.7 design review after validating the vendored ACP v1 schema.
Priority: **Protocol-honesty / trust-boundary follow-up; not a Plan 11.7 prerequisite.**

**Origin / current behavior:** ACP requires `mcpServers` on both `NewSessionRequest` and
`LoadSessionRequest`. Optimus has long accepted `session/new` while ignoring that field; existing
tests and live payloads send `[]`. This is not the same system as `P11-FEAT-GATEWAY-MCP`:
ACP `mcpServers` asks the agent to connect outward to client-nominated servers, while Gateway MCP
brokering routes Optimus-owned tool calls through the Gateway. Sequencing Gateway-MCP first would
not resolve the current ACP behavior.

**Designated custody:** This entry owns the cross-lifecycle ACP-input decision for current
`session/new` and future methods, including `session/load`. Plan 11.7 preserves the shipped
posture and records the field without creating a client-nominated connection; it does not claim
that Gateway-MCP implements this capability.

**Acceptance criteria:**

- Decide explicitly whether non-empty client-supplied MCP server arrays are rejected, accepted but
  deliberately unsupported, or honored through a separately reviewed agent-side MCP client.
- Apply the decision consistently to every ACP lifecycle method that carries `mcpServers`; do not
  fix only `session/load` while leaving `session/new` semantically different.
- Preserve the one-key/Gateway trust boundary, reject arbitrary side-effecting connectivity unless
  explicitly authorized, and distinguish client-nominated MCP from Gateway-brokered tools in docs
  and telemetry.
- Add schema-pinned unit tests plus real-client evidence for empty and non-empty arrays, with no
  raw server credentials or untrusted configuration persisted or logged.

**Status:** Tracked, not yet scheduled. Explicitly not a hard prerequisite for Plan 11.7 and not
owned by `P11-FEAT-GATEWAY-MCP`.

### P11-FU-10: Complete ACP Error-Code Registry Audit

**Raised:** 2026-07-29 during Plan 11.7 design review after the vendored ACP schema exposed the
current `MUTATION_FORBIDDEN = -32002` collision with ACP `RESOURCE_NOT_FOUND`.
Priority: **Conformance hardening; partially forced into Plan 11.7.**

**Forced Plan 11.7 subset:** Plan 11.7 must reserve ACP `-32002` for
`RESOURCE_NOT_FOUND`, relocate ACP-adapter mutation refusal to Optimus code `-32910`, and remove
the duplicate raw wire-code constant from `src/optimus/runtime/mutation.py`. That required subset
belongs to Plan 11.7 and does not block on this follow-up.

**This entry retains only the general audit:**

- audit `DUPLICATE_REQUEST_ID = -32001` against ACP/JSON-RPC allocations and actual client
  behavior;
- eliminate remaining production raw error-code literals outside the central ACP registry;
- reduce the Plan 11.7 exact path-and-symbol legacy allowlist to zero; and
- retain frozen historical plan references as expected evidence rather than rewriting history.

**Acceptance criteria:**

- A schema-derived oracle proves registry uniqueness, disjointness from ACP allocations, and
  exclusion from JSON-RPC's complete `-32768…-32000` reserved band for Optimus application codes.
- An AST-based source audit rejects raw JSON-RPC/application code literals outside the central
  registry. Any temporary baseline allowlist is exact by path and symbol and cannot grow.
- Runtime exceptions remain semantic; the ACP adapter alone maps them to wire codes.
- Current user-facing documentation is updated when codes move, while frozen historical plans
  remain byte-for-byte historical records with explicit audit disposition.

**Status:** Tracked, not yet scheduled. It does not gate Plan 11.7 closure; Plan 11.7 owns only the
forced `-32002`/mutation-refusal correction and a no-new-bypasses baseline gate.

### P11.5-FU-2: Consistent local env / Redis / Phoenix / Gateway startup for live runs

**Raised:** 2026-07-29 during Plan 11.5 Task 8 (real Redis / Phoenix / ACP release-evidence
capture), by operator ([Vibhanshu]). Priority: **HIGH**. Surfaced while attempting live E7
`acpx` capture and `requires_gateway` evidence and hitting four inconsistent mechanisms for
getting local dependencies running before landing on a workaround.

**Origin / core problem:** `optimus-agent` startup (`__main__.py`) already resolves runtime
configuration from the OS keychain + sensible defaults with **zero required env vars** — the
documented Plan 9.7 / Plan 9.6 Phase C "no `.env` files required" path, confirmed still working.
But `src/optimus/acp/subprocess_env.py`'s `build_acp_subprocess_env` (used by both the Plan 11.5
Task 8 `acpx` evidence tool and the older Plan 9.87 one) imposes a separate, stricter gate that
`OPTIMUS_GATEWAY_URL` / `OPTIMUS_API_KEY` / `OPTIMUS_REDIS_URL` be **explicitly present in the
shell**. That stricter gate is not technically required by the agent contract and is what forced
a manual workaround during Task 8.

**Four divergent mechanisms found this session (do not add a fifth):**

1. **`optimus-agent` auto-start** (`ensure_local_gateway` / `ensure_local_redis`) — zero env vars,
   keychain-based, non-interactive.
2. **`optimus-trust run-gateway`** — interactive ceremony, TTY-required, displays a config
   snapshot.
3. **`tools/run_local_gateway.sh` / `.ps1`** — look like standalone non-interactive launchers
   (names/docstrings still describe old direct-source behavior) but now just delegate to #2.
4. **`build_acp_subprocess_env`** — a stricter, explicit-env-var gate layered on top of #1 for
   evidence tooling specifically.

**Explicit requirement — consolidate, don't bolt on another option:** The fix must reduce this
to **one clear path**. Preferred direction: make #4 honor #1's proven keychain-only contract. If
evidence-capture truly needs stricter/explicit config, that divergence must be deliberate and
documented — and #3 must be deleted or clearly repointed so it is not a false lead. Whichever
direction, there must be exactly one documented answer to "how do I get local deps running for a
live run," not several scripts that look interchangeable but aren't.

**Also found:** No launcher exists for **Phoenix** at all — only an inline `docker run` hint
buried in a test docstring. Bring Phoenix into the **same** single consistent mechanism rather
than adding another ad-hoc path.

**Deliverable:** One short operator runbook (matching the existing Plan 9.6 Phase C runbook
precedent at
`docs/runbooks/plan-9-6-phase-c-operator-path.md`) that is the **single
source of truth**, backed by code that actually matches what the runbook says — not a doc layered
on top of still-divergent scripts.

**Designated slice / plan shape:** Future small dedicated startup/runbook consolidation plan
(Plan number assigned at pickup). Do **not** silently fold into an unfinished Plan 11.5 Task 8
checkpoint without a reviewed amendment; retain named pool custody before Plan 11.5 close.

**Acceptance criteria (draft — refine at pickup):**

- Exactly one documented, operator-usable path for local Redis + Gateway (+ Phoenix where needed)
  for live/evidence runs.
- `build_acp_subprocess_env` either honors the keychain-only agent contract (#1) or documents and
  tests a deliberate, reviewed divergence — no implicit stricter shell-env gate.
- `tools/run_local_gateway.sh` / `.ps1` either match that single path (names + behavior) or are
  removed/repointed so they cannot mislead.
- Phoenix local startup is part of the same mechanism/runbook (not a fifth ad-hoc docker hint).
- Runbook text and code paths are verified against each other (presence tests and/or a focused
  live smoke that follows the runbook steps).
- Does not invent a fifth launcher family; does not weaken launch-trust / one-key / Gateway-only
  OTLP contracts.

**Evidence anchors:** Plan 11.5 Task 8 review conversation and evidence attempt (E7 /
`requires_gateway` capture that surfaced all four mechanisms); `.superpowers/sdd/task-8-report.md`
incomplete live E7 / `requires_gateway` dispositions; `src/optimus/acp/subprocess_env.py`;
`tools/run_plan115_acpx_cost_obs_evidence.py`; `tools/run_local_gateway.sh` / `.ps1`;
`optimus-trust run-gateway`; Plan 9.6 Phase C runbook
(`docs/runbooks/plan-9-6-phase-c-operator-path.md`).

**New finding (2026-07-29, discovered while attempting live `requires_gateway`/E7 evidence):** the
established `optimus-redis` (`redis:8`, port 6379) container had stopped — likely from a
machine/Docker Desktop restart since its last use, not a code or process regression. In its
absence, an unrelated project's container (`optimus-plan112-redis`, `redis:7-alpine`, no
TimeSeries module) took over the same default host port. `optimus-agent`'s preflight correctly
detected and rejected the TimeSeries-less Redis — the fail-closed check itself worked as
designed — but there is no protection against an unrelated project's container colliding on the
same default port, and no documented recovery path. This also reconfirms the divergent-mechanism
finding above at the Docker/port layer: separately-named, non-default-port containers
(`optimus-task8-redis` on 16379, `optimus-task8-phoenix` on 16006) were found running alongside
the default-port containers, consistent with different sessions standing up isolated instances
instead of one shared, documented one. The eventual design must nail this down explicitly (e.g. a
project-specific non-default port, or an explicit identity check) rather than depend on ambient
port availability.

**Status:** **Closed** (2026-07-29): Plan 11.6 implemented on
`agent/cursor/plan-11-6-local-startup-consolidation` with commits
`d123779`, `01f7849`, `24158ce`, `1618591`, `ef3dbd8` (Tasks 1–5) and Task 6 live evidence in
[`reports/plan-11-6-local-startup-live-evidence.md`](../../reports/plan-11-6-local-startup-live-evidence.md)
(plus [`reports/plan-11-6-local-startup-acpx-evidence.md`](../../reports/plan-11-6-local-startup-acpx-evidence.md)
and WSL residual
[`reports/plan-11-6-local-startup-acpx-wsl-evidence.md`](../../reports/plan-11-6-local-startup-acpx-wsl-evidence.md)).
Operator runbook:
[`docs/runbooks/local-live-dependencies.md`](../../runbooks/local-live-dependencies.md).
Retain this entry for history; do not reopen without a new deferred-follow-up ID.

## Accepted risks and warnings

Entries in this section record operator-accepted limitations. They are not open work and do not
reserve a future plan number.

### Plan 11.7 accepted risk: `optimus-redis` ACP-session durability boundary

**RISK (accepted by operator 2026-07-30):** `optimus-redis` provides no real durability for
[Plan 11.7](2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md)'s "durable Redis ACP
sessions." Live-inspected container state has no volume mounts, `appendonly no` (periodic RDB
snapshots only), and a default user configured as `nopass ~* &* +@all`; strict loopback binding
mitigates the unauthenticated default-user exposure.

**Consequence:** Container removal loses all ACP session state. Container restart recovers only to
the latest RDB snapshot. The accepted Plan 11.7 meaning of "durable" is survival across
process/agent restarts, not container lifecycle events.

**Revisit trigger:** Revisit only if session-state loss occurs in practice or a future plan—such
as the A2A ledger's hardened-Redis fallback path—already changes Redis persistence configuration.
In that case, fix persistence once in the consolidated startup mechanism under the single-config
rule.

**Status:** Accepted as-is by the operator on 2026-07-30; recorded warning, not open work.

## P9.96 Task 9 Disclosed Follow-Ups (Closed; historical Plan 10 custody)

**Raised:** Disclosed by Plan 9.96 Task 9 on 2026-07-23 under the 2026-07-18 scope-conflict ruling.
Plan 9.96 closes only `P9.85-FU-7` and `P9.9-FU-1`; these seven disclosures are named custody, not
silent drops.

**Origin:** `reports/plan-9-96-operator-debug-launch-trust-evidence.md`, limitations table.

**Historical designated future plan:** Plan 10 (retired). These seven distinct stable-ID catalog
entries are now closed; no Plan 10.x slot or new Plan 10 work remains.

| ID | Summary |
|---|---|
| `P9.96-FU-1` | `StartupConfigurationError` missing `optimus-agent:` prefix in `acp/__main__.py` |
| `P9.96-FU-2` | Duplicated TOCTOU comment block in `acp/__main__.py` |
| `P9.96-FU-3` | `append_launch_audit_event` docstring says trusted external runtime root but uses `workspace/.optimus` |
| `P9.96-FU-4` | Latent unroutable `DEFAULT_AGENT_MODEL = "glm-5.2"` in `agent/defaults.py` (ACP path injects `claude-haiku`) |
| `P9.96-FU-5` | Frozen dataclass exceptions mask real codes via `@contextmanager` (`FrozenInstanceError`) |
| `P9.96-FU-6` | Frozen plan Task 9 CLI arg-order / PATH assumptions; execution uses `uv run` plus `--workspace-root` before the subcommand (applied; not a code defect) |
| `P9.96-FU-7` | Approve ceremony writes durable approval with no y/N confirm; bare-shell display rows may be empty when settings are keyring/default-sourced |

**Acceptance / disposition:** The rows were open until a reviewed implementation or explicit closure
record resolved each one with evidence. `P9.96-FU-6` is an applied execution correction, not a code
defect, and closed through the explicit reviewed disposition below.

**Plan 10.1 dispositions (updated 2026-07-23; the pool's first allocated slot):**

| ID | Disposition |
|---|---|
| `P9.96-FU-1` | **Closed** by Plan 10.1, commit `daccb0d7469814930922eae67a86552435258cf6` ("fix(acp): prefix PreflightFailure and StartupConfigurationError stderr"). Named tests: `tests/unit/acp/test_main_check_config.py::test_check_config_prints_preflight_failure`, `tests/unit/acp/test_main_wiring.py::test_startup_configuration_error_has_agent_prefix`. |
| `P9.96-FU-2` | **Closed** by Plan 10.1, same commit `daccb0d7469814930922eae67a86552435258cf6` (duplicate TOCTOU comment block removed; one copy retained, verified via `rg -n -F "Plan 9.96, Task 5 Step 7 (TOCTOU matrix): workspace identity is a" src/optimus/acp/__main__.py` returning a single hit). |
| `P9.96-FU-3` | **Closed** by Plan 10.1, commit `d83953880a15419097e91da262678f736905cccd` ("docs(acp): align launch-audit docstrings with workspace-local runtime root"). Named test: `tests/unit/acp/test_launch_audit.py::test_launch_audit_docs_describe_workspace_local_runtime_root`. |
| `P9.96-FU-4` | **Closed** by Plan 10.1, commit `cc66d660cd8580eb3b821d0eb25ed04b27605dc0` ("fix(agent): use routable shared default"). Named tests: `tests/unit/agent/test_defaults.py::test_resolve_agent_model_falls_back_to_routable_shared_default`, `tests/unit/optimus_gateway/test_models.py::test_resolve_model_id_accepts_shared_agent_default_for_every_provider`. |
| `P9.96-FU-5` | **Closed** by Plan 10.1 evidence; no source or test change. Static inventory found zero `@contextmanager`/`FrozenInstanceError` occurrences in `src`/`tests`; the two candidate frozen exceptions (`StartupConfigurationError`, `AcpOutboundError`) only ever construct once via `raise ... from` / `future.set_exception(...)` and never reassign a field post-construction on any real call path. Behavior selector (`tests/unit/acp/test_bootstrap.py`, `test_outbound_errors.py`, `test_trusted_paths.py`, `test_preflight.py`) passed 36 passed, 5 skipped (environment-legitimate skips). Full record: `docs/superpowers/reviews/plan-10-1-review-checkpoints.md`, 2026-07-23T13:20:00Z entry. |
| `P9.96-FU-6` | **Closed** by reviewed Plan 10.1 disposition; execution correction only, no code change — see the disposition paragraph below. |
| `P9.96-FU-7` | **Closed** by Plan 10.2 for the remaining effective-row display provenance gap, while Plan 10.1's confirmation-gate half remains part of the same stable finding (commit `278d95bec4e9a62c55c5de1237a61af1ca661309`). Plan 10.2 implementation commit `4350ae6f455c83f6d8a79c2a0bbdfe149755a4ef` ("feat(acp): display effective credential provenance in optimus-trust approve"). Named tests: `tests/unit/acp/test_local_gateway_secrets.py` (shared-secret provenance / wrapper / base-URL keyring ignore), `tests/unit/acp/test_launch_gate.py::TestEffectiveCredentialDisplayRows`, `TestMissingKeyNonDisclosureAndGoldenDigest`, `tests/unit/acp/test_launch_approval_cli.py::test_display_candidate_prints_source_class`. Frozen plan: `docs/superpowers/plans/2026-07-23-plan-10-2-p9-96-fu7-effective-row-display-provenance.md` (SHA-256 `4303D6AD5C44ED62A85A0509C8C87366505D4D470DD7BC4E0B4309BBE6E3C771`). Approval: `docs/superpowers/reviews/2026-07-23-plan-10-2-implementation-plan-approval.md`. Evidence: gitignored `docs/superpowers/reviews/plan-10-2-review-checkpoints.md`. Plan 10.2 does **not** change the approval digest contract; golden digest `f7af89af0acce664b27825e5af9823c25b11579490bccc73e8f82d4ec316f248` remains byte-identical. |

**`P9.96-FU-6` disposition paragraph:** `P9.96-FU-6` named the frozen Plan 9.96 Task 9 plan's own CLI
arg-order assumption against `optimus-trust`'s `argparse` contract. `--workspace-root`
(`src/optimus/acp/launch_approval_cli.py:78-82`) is declared on the top-level `ArgumentParser`
*before* `subparsers = parser.add_subparsers(dest="command")` (line 84), so under normal `argparse`
semantics it must be supplied before the subcommand token — e.g.
`optimus-trust --workspace-root <path> approve --mode durable`, not after. The corrected command
shape (`uv run` plus global options such as `--workspace-root` preceding the subcommand) was already
applied during Plan 9.96 Task 9's own real-`acpx` evidence capture
(`reports/plan-9-96-operator-debug-launch-trust-evidence.md`), not by Plan 10.1. Plan 10.1 (Task 6,
2026-07-23) re-verified this reviewed disposition by re-reading the current `argparse` source and
confirming the contract is unchanged. `P9.96-FU-6` was never a source-code defect and required no
production or test change under Plan 10.1 or any prior plan; no commit is recorded for this
disposition.

**Also disclosed (Plan 9.98 custody handoff):** inner `optimus-agent` launch-audit `agent_child`
may omit keyring-resolved `OPTIMUS_API_KEY` because audit precedes `apply_local_defaults`; outer
post-default audit remains the authoritative child-key evidence source. This is a custody note, not
an additional Plan 10 item.

**Status:** `P9.96-FU-1` through `P9.96-FU-4` and `P9.96-FU-6` are closed by Plan 10.1 (see the
dispositions table above); `P9.96-FU-5` is closed by Plan 10.1 evidence with no source/test change;
`P9.96-FU-7` is **closed** under its original stable ID: Plan 10.1 closed the confirmation-gate half
and Plan 10.2 (commit `4350ae6f455c83f6d8a79c2a0bbdfe149755a4ef`) closed the effective-row display
provenance half. No new catalog ID or Plan 10.x plan document was created by either pickup. The
remaining open items are now carried by this pool, except for the parked, undecided
`P9.85-FU-3` entry above.

## Closed Historical Follow-Ups (formerly tracked lightweight notes)

### Plan 10.3 frozen-plan status correction (historical)

The frozen Plan 10.3 implementation plan retains its pre-approval draft status because its
approval record pins the plan bytes. The digest-pinned approval record and the roadmap's closed
Plan 10.3 entry are authoritative for the lane's closed state; this pool records the closure
without editing the historical frozen plan.

### `uv.lock` missing direct dependencies: `keyring`, `redis`, and their transitive chain (disclosed 2026-07-23 during Plan 10.1 Task 1)

The committed `uv.lock` is out of sync with `pyproject.toml`, not just stale: `uv lock --dry-run`
shows 13 packages a regeneration would add, including `keyring` and `redis` (both **direct**
dependencies declared in `pyproject.toml`, not stray transitives) and the Linux SecretStorage
keyring-backend chain (`cryptography`, `jeepney`, `secretstorage`, `cffi`, `pycparser`, `jaraco-*`).
`uv run --locked` and `uv lock --check` both fail on current `main`. Confirmed `cryptography` is
genuinely unimportable in a `--frozen`-synced venv on both Windows and a fresh WSL2 environment
(`ModuleNotFoundError`); `keyring`/`redis` only appear to work locally because of packages left over
from an older install, not because the lock is sound — a fresh clone or Linux CI doing
`uv sync --frozen` gets exactly the lock's packages and nothing else, so `keyring`'s SecretStorage
backend would fail to import there. Traced via `git log`: the lock was last regenerated at `9c1206d`
(2026-07-04) while `pyproject.toml` changed again at `1f7116b` (2026-07-15, Plan 9.9's approval-
ceremony work) — the drift predates Plan 10.1 and passed through several already-merged,
already-reviewed plans undetected.

**Fix:** regenerate the lock (`uv lock`), review the diff for anything beyond the expected
keyring/redis/dotenv chain, then re-run the default test suite and a WSL2 cross-check to confirm
`keyring`/`redis`/`cryptography` all import cleanly from a fresh sync. Not a Plan 10.1 blocker —
Plan 10.1 used `uv run --frozen` as a standing substitute for the plan's literal `--locked` command
text rather than regenerate the lock mid-plan, since that would have been its own scope change; not
scheduled.

**Promoted -> Plan 10.3** (2026-07-24): Closed by
[`2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md`](2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md).
Lock commit `1b152a8` ("chore: refresh uv lock for declared gateway dependencies") adds exactly the
reviewed 13-package chain (`cffi`, `cryptography`, `jaraco-classes`, `jaraco-context`,
`jaraco-functools`, `jeepney`, `keyring`, `more-itertools`, `pycparser`, `python-dotenv`,
`pywin32-ctypes`, `redis`, `secretstorage`); `pyproject.toml` unchanged; `uv lock --check` exits 0.
Windows acceptance: `uv run --frozen pytest -q` → 1495 passed, 20 skipped, 27 deselected.
WSL2 Ubuntu-24.04 disposable fresh-sync import printed `keyring redis cryptography`. No new catalog
ID; this note is closed by Plan 10.3.

### Tools: `SurfaceAuditError` frozen-dataclass CI wart (disclosed 2026-07-23 during Plan 10.1 Task 7)

`tools/verify_plan996_logging_surfaces.py` raises a `@dataclass(frozen=True)` `SurfaceAuditError`.
When that exception is raised under pytest's generator-based failure capture, pytest teardown can
attempt to attach `.__traceback__` and surface a secondary `FrozenInstanceError` in the CI log.
Standalone `main()` outside pytest raises `SurfaceAuditError` cleanly with no crash — this is a
pytest-harness wart, not a production or `src`/`tests` FU-5 recurrence. Trivial later fix: drop
`frozen=True` on that tools-only exception class (nothing in that type needs immutability). Not a
Plan 10.1 blocker; not scheduled.

**Promoted -> Plan 10.3** (2026-07-24): Closed by
[`2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md`](2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md).
Tools commit `4d1f086` ("fix(tools): allow surface audit errors to carry tracebacks") drops only
`frozen=True` from `SurfaceAuditError`. Named regression:
`tests/unit/tools/test_verify_plan996_logging_surfaces.py::test_surface_audit_error_allows_pytest_traceback_attachment`
(RED `FrozenInstanceError` → GREEN); full tools unit file 13 passed; standalone `main()` still exits
0 with `Plan 9.96 logging-surface audit passed`. No new catalog ID; this note is closed by Plan 10.3.

## Closed custody excluded from the open pool

Plan 9.96's two sole-custody follow-ups (`P9.85-FU-7`, `P9.9-FU-1`) are closed with the Plan 9.96
Task 9 evidence report and are intentionally not listed as open backlog entries.
