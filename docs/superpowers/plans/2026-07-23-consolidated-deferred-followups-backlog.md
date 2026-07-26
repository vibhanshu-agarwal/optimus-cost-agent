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
| `P11-FEAT-GATEWAY-CORE` | Plan 11.1 — closed; merged to `main` as PR #85 (`6ae6997`, tip `6c39599`) | [Charter](2026-07-25-plan-11-v1-milestone-charter.md#p11-feat-gateway-core---gateway-core-and-observability-route) |
| `P11-FEAT-GATEWAY-TOOLS` | Ratified, unscheduled; carries `P11-FU-2` | [Charter](2026-07-25-plan-11-v1-milestone-charter.md#p11-feat-gateway-tools-and-p11-feat-gateway-cost-obs) |
| `P11-FEAT-GATEWAY-COST-OBS` | Ratified, unscheduled | [Charter](2026-07-25-plan-11-v1-milestone-charter.md#p11-feat-gateway-tools-and-p11-feat-gateway-cost-obs) |
| `P11-FEAT-ZED-RESUME` | Ratified, unscheduled; carries `P11-FU-1` | [Charter](2026-07-25-plan-11-v1-milestone-charter.md#p11-feat-zed-resume---zed-integration-fixes-and-session-resume) |
| `P11-FEAT-REGISTRY` | Ratified, unscheduled; blocked on its research gate — no authoritative source exists in any of the four pinned documents. Also owns the v1.0 release-version contract | [Charter](2026-07-25-plan-11-v1-milestone-charter.md#p11-feat-registry---acp-registry-registration-and-v10-cut) |
| `P11-FEAT-IDE` | Conditional — opens only by explicit amendment if REGISTRY surfaces an unmet multi-IDE expectation | [Charter](2026-07-25-plan-11-v1-milestone-charter.md#p11-feat-ide---conditional-ide-specific-testing) |
| `Plan 12` | Post-v1.0 context-window and intelligent-selection lane; outside the v1.0 cut | [Charter boundary](2026-07-25-plan-11-v1-milestone-charter.md#explicit-exclusions-and-unresolved-inputs) |

## Open items

### P9.8-FU-2: Intelligent ambiguous-reference ranking

**Raised:** 2026-07-10, in Plan 9.8's own Deferred Follow-Ups
(`docs/superpowers/plans/2026-07-10-plan-9-8-task-aware-workspace-context.md`).

**Designated future plan:** Plan 12 (Context Window Optimization and Intelligent Selection).

**Acceptance criteria:** Candidate ranking uses the accepted relevance/trust/freshness/dependency
policy, measures wrong-target regret, and retains a fail-closed threshold. Until this lands,
ambiguity stays visible and deterministic (Plan 9.8's current behavior).

**Status:** Open, not yet scheduled.

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

**Verified blocker (2026-07-25):** Independent review confirms an unresolved architecture conflict.
HLD v2.15 §§5A and 11, LLD v2.38 §§0A, 9D, and 10A, and Guardrails v1.0 §§7.2 and 9 assign
budget enforcement to the Gateway and describe local budget state as informational. The current
`src/optimus_gateway/` implementation contains no budget, spend, cap, quota, or wallet-enforcement
logic. This item is therefore blocked on an operator decision about the Gateway budget-enforcement
roadmap and authority boundary; it is not a spec-readiness gap. The designated future plan remains
none/unassigned pending that decision.

**Plan 11 disposition:** Parked and undecided; not part of Plan 11's initial scope. Revisit only if
Plan 11 Gateway work organically reaches budget or cost policy.

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

**Status:** Owned by `P11-FEAT-ZED-RESUME`; open and not yet scheduled. This is an unimplemented protocol
capability, not a flaky regression or a parked architecture blocker.

### P11-FU-2: Package Lookup and Security Advisory Gateway Capability

**Raised:** 2026-07-25 during the Plan 11 Gateway requirement review. The pinned LLD names
`POST /v1/tools/package/lookup` and `POST /v1/tools/security/advisory` as Gateway-facing typed
endpoints, and §9A/§9B define their package/advisory tool class and routing signals. The local
repository does not yet implement these Gateway routes as dedicated endpoints. Existing policy
behavior is not absent: `src/optimus/tools/policy.py:85-93` routes `DEPENDENCY_VERSION_CHECK` and
`SECURITY_OR_CVE_CHECK` into `WEB_SEARCH_TRIGGERS`, while LLD §9B's `DEFAULT_POLICY_MATRIX`
(p.26) maps both signals to `ToolClass.PACKAGE_AND_ADVISORY_METADATA`. Dependency and CVE
evidence is therefore served today via generic web search, against a different tool class than
the LLD specifies. Picking up FU-2 changes existing, tested policy behavior, not merely adding
routes.

**Origin:** `docs/Optimus-Cost-Agent-LLD-v2.38.pdf`, §0.D (p.3), §9A (p.24), and §9B (p.25).

**Designated slice:** `P11-FEAT-GATEWAY-TOOLS` (plan number assigned at pickup). This is an
unimplemented capability owned by the Tools slice; it is not part of the parked `P9.85-FU-3`
budget-enforcement decision.

**Acceptance criteria:** The reviewed `P11-FEAT-GATEWAY-TOOLS` design and implementation must:

- define and serve the package-registry lookup and security-advisory request/response contracts;
- route `PACKAGE_AND_ADVISORY_METADATA` using `PACKAGE_VERSION` and `SECURITY_ADVISORY` signals;
- preserve the one-key boundary, Gateway-side provider secrets, policy revalidation, usage/cost
  envelope, and evidence/provenance contracts; and
- provide named unit, integration, and real-Gateway evidence for both endpoint families.

**Status:** Owned by `P11-FEAT-GATEWAY-TOOLS`; open and not yet scheduled. This is an unimplemented
capability, not a parked architecture blocker.

### P11-FU-3: LLD Source Repair — §0.B Component Flow and MCP Endpoint Shape

**Raised:** 2026-07-25 during the Plan 11 Gateway requirement review. LLD §0.B is clipped at the
rendered page boundary around `/v1/tools/web/extract`, and LLD §0.C names MCP tool brokering without
an MCP endpoint or Gateway request/response shape in §0.D.

**Origin:** `docs/Optimus-Cost-Agent-LLD-v2.38.pdf`, §0.B (rendered p.2), §0.C (p.3), and §0.D
(p.3); the source-contract gap was confirmed against the pinned SHA-256.

**Designated future plan:** `LLD source repair` (documentation-owner work; no Plan 11 feature or
plan number is assigned by this entry).

**Acceptance criteria:** The authoritative LLD source must be repaired or replaced by an explicitly
reviewed authoritative source that:

- restores the complete §0.B component-flow text without reconstructing the clipped continuation;
- defines whether MCP brokering is supported and, if so, supplies its Gateway route and typed
  request/response contract; and
- triggers fresh source digest verification and a new requirement extraction before any affected
  Gateway requirement is promoted into a specification.

**Status:** Open, not yet scheduled, and owned by `LLD source repair`. This is a documentation/source
contract repair item, not an inferred MCP implementation requirement.

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
