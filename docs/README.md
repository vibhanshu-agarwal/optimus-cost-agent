# Documentation index

Every folder under `docs/` works the same way:

- **The folder root holds only current documents**, in their latest version.
- **Everything else is in that folder's `archive/`**: superseded versions and records of finished
  work. Archived files are kept byte-for-byte and are never edited.

Documents are found by file name, so moving one into `archive/` needs no test or tool change
(see `tools/doc_paths.py`). When a document stops being current, move it to the `archive/` beside
it and remove its line below. A test checks that this index lists every current document.

## Design documents (authoritative)

| Document | What it is |
|---|---|
| [Architecture (HLD) v2.22](Optimus-Cost-Agent-Architecture-v2.22.pdf) | High-level design; opt-in Auto mode and its enforced-registry prerequisites at `bf440cb` (2026-10-27). Carried baseline and EDIT statements retain their earlier pins. The [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) still controls unrefreshed Plan 12.2 material; ADR-024 governs interactive loop control |
| [LLD v2.45](Optimus-Cost-Agent-LLD-v2.45.pdf) | Low-level design; Auto composition, H, decisions, routing/binding, stops, settlement and visibility (§13.10), with registry/construction corrections at `bf440cb` (2026-10-27). Prior baseline/EDIT pins remain. The [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) controls unrefreshed material; ADR-024 governs interactive loop control |
| [Test Strategy v1.9](Optimus-Cost-Agent-Test-Strategy-v1.9.pdf) | Testing approach; v1.9 is the capability and evidence correction of 2026-10-15 (reviewed local filing candidate); current Plan 12.2 evidence status is in the [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) |
| [Agent Execution Guardrails and Workflow Strategy v1.5](Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.5.pdf) | Execution guardrails; v1.5 replaces only the v1.4 cover, recording the filed D7 provenance (ADR-018), the merge of the v2.19/v2.42/v1.8 companions (PR #276) and their corrected successors v2.20/v2.43/v1.9 and Roadmap v11, which are local filing candidates like v1.5 itself (2026-10-15); the body is unchanged; its cover and inherited Context Engine activation statements are amended by the [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) |
| [Architecture Roadmap v11](Optimus-Architecture-Roadmap-v11.pdf) | Long-range roadmap; v11 classifies each phase as implemented, approved requirement or proposed (correction of 2026-10-15; reviewed local filing candidate); current Plan 12.2 status is in the [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) |
| [Plan 12.2 ordinary shipping amendment](sources/plan-12-2-ordinary-shipping/) | Filed 2026-10-18 Plan 12.2 statements and historical evidence. HLD v2.22 / LLD v2.45 refresh registry, production-construction and Auto statements; this amendment remains controlling for their unrefreshed Plan 12.2 material and retains its Guardrails/evidence/roadmap scope. The frozen amendment and 2026-10-15 correction sources stay unchanged |
| [Plan 12.4 Auto-mode successor sources](sources/plan-12-4-auto-mode/) | Codex's replacement text, assembled baseline-keyed sources and filing validation for HLD v2.22 and LLD v2.45; scoped to Auto and its registry prerequisites at `bf440cb` |
| [Agent-mode localized EDIT successor sources](sources/agent-localized-edit/) | Preserved predecessor sources and validation for HLD v2.21 and LLD v2.44; their baseline-keyed page bodies are the inputs to the Auto successor |
| [Capability and evidence correction sources](sources/capability-evidence-correction/) | Sources, authoring tools, correction map and validation record for HLD v2.20, LLD v2.43, Roadmap v11 and Test Strategy v1.9, and the Guardrails v1.5 cover |
| [Plan 12.2 closure publication sources](sources/plan-12-2-context-engine-closure/) | Sources the HLD v2.19, LLD v2.42, Guardrails v1.4 and Test Strategy v1.8 were built from (Plan 12.2 Context Engine closure). Still the source of the Guardrails v1.5 body (unchanged from v1.4), and historical provenance for the archived v2.19, v2.42, v1.4 and v1.8 |
| [Plan 12.4 Auto-mode pilot evidence](sources/plan-12-4-auto-pilot/) | Content-free evidence for the Auto judge: the evidence report, every view's tables, the frozen settings and the exploratory combinations; the digest-bearing manifest stays in the review kit, pinned by SHA-256 |
| [Plan 12.4 round 2 evidence](sources/plan-12-4-auto-round2/) | Content-free evidence for round 2, the challenger round on a fresh sealed split: the evidence report, every view's tables, the frozen settings, the manifest and a tool that recomputes every view; H stays (Checkpoint R2, 2026-10-27; Plan 12.4 v10, the closing record, is in the plans archive) |

## Decision records (ADRs)

Operator decisions with their verbatim context, the options considered and the trade-offs. Read the
relevant records before proposing a change in their area.

| Document | What it is |
|---|---|
| [Decision log guide and index](decisions/README.md) | Rules for recording decisions, and the index of records |
| [ADR-001: Context Engine as a separate product](decisions/ADR-001-context-engine-separate-product.md) | Loose coupling; the Optimus floor stays |
| [ADR-002: History strategies and picker](decisions/ADR-002-history-strategies-and-picker.md) | Compaction (default), hybrid, sliding window; IDE picker |
| [ADR-003: Context ceiling and history limits](decisions/ADR-003-context-ceiling-and-history-limits.md) | About 256K for all models; history past 512 KiB while the engine is attached; Haiku removed |
| [ADR-004: Curated model registry](decisions/ADR-004-curated-model-registry.md) | YAML tiers, origin rule, per-token selection among eligible models |
| [ADR-005: Cost alerts, not limits](decisions/ADR-005-cost-alerts-not-limits.md) | No Optimus cost stops; alerts at thresholds |
| [ADR-006: Summarizer model](decisions/ADR-006-summarizer-model.md) | From the ultra-cheap tier, behind a quality gate |
| [ADR-007: Auto mode tier routing](decisions/ADR-007-auto-mode-tier-routing.md) | Classifying each request into a tier |
| [ADR-008: Final review step and modes](decisions/ADR-008-final-review-step-and-modes.md) | Standard and Thorough |
| [ADR-009: Loop control](decisions/ADR-009-loop-control-without-stopping-the-user.md) | Never open-ended, never a silent stop |
| [ADR-010: Data handling on Chinese-model routes](decisions/ADR-010-data-handling-for-chinese-model-routes.md) | No restriction now (deferred) |
| [ADR-011: How decisions are recorded](decisions/ADR-011-how-decisions-are-recorded.md) | This log, in the repository |
| [ADR-012: Cost-savings report](decisions/ADR-012-cost-savings-report.md) | A Plan 12 feature: net savings, with a stated baseline |
| [ADR-013: Plan 12 effect repair](decisions/ADR-013-plan12-effect-producer-repair.md) | First code step; real WRITE/TEST boundaries and cancellation; later Package A authority |
| [ADR-014: Request guard and source floor](decisions/ADR-014-all-session-request-guard-floor-clarification.md) | ADR-003 clarification with full-floor route evidence required |
| [ADR-015: Cost-stop removal sequencing](decisions/ADR-015-cost-stop-removal-sequencing.md) | After accounting/D6, without waiting for ADR-009 |
| [ADR-016: Checkpoint cadence](decisions/ADR-016-checkpoint-review-cadence.md) | Fable then Codex at at most four checkpoints; local task commits; Package A publication |
| [ADR-017: Package A coverage residual](decisions/ADR-017-package-a-coverage-exception.md) | Exact one-time four-statement exception at 38a465f; result remains NOT MET |
| [ADR-018: Plan 12 CP4 numeric policy](decisions/ADR-018-plan12-cp4-numeric-policy.md) | Measured numeric set, whole-turn availability limitation and the D7 request-capacity exception; the operator's acceptance is quoted verbatim (source S4) |
| [ADR-019: Plan 12 Task 1 policy integration](decisions/ADR-019-plan12-task1-policy-integration.md) | Accepted Task 1 mechanisms and the proposed governed integration of ADR-003 to 006 |
| [ADR-020: Test cadence and staged delivery](decisions/ADR-020-test-cadence-product-coverage-and-staged-delivery.md) | Accepted policy/mechanisms and Plan 11.30 progress exception; Tasks 0–3 locally accepted/delivered; local Task 6 accepted with approved checkout exception; report/docs delivered at 1c7be2d; Stage B Task 4/C/G accepted and local delivery verified at `43eb190`; Task 5/D accepted and local delivery verified at `66ddabf`; Stage B governance and local Task 6 accepted at measured `3cece0a`; results delivered at `26bd667`; corrected integration contract and revised-v5 wording accepted; Claude/Codex responsibility clarified; v5 approved; I1 bootstrap local delivery verified at `6f1935d`; PR279 main-push baseline accepted at `4ed9b25`; current (2026-10-11): I1 merged on main via PR #279 (`4ed9b25`) and its main-push baseline accepted; I2/I3 integration merge committed locally at `ea88814e` (tree `9048bc8d`) and accepted, with I3 evidence including the WSL platform discharge; I4 exact-source finals accepted at `ea88814e` (Windows/WSL canonical gates and validation pass); S1 reader correction delivered at `343b233a` and accepted, with corrected-source I4 finals accepted at that pin (Windows/WSL canonical gates and validation pass; WSL platform obligation discharged at that pin only); documentary delivery `281f8ce7` accepted and its forward WSL platform obligation discharged; PR #280 published at `281f8ce7`, with its candidate Linux CI and seven-module safety comparison (no regression) accepted at merge ref `1946713e`; D3 documentary delivery `228b5f6f` accepted and its WSL platform obligation discharged; D3 pushed to PR #280 without force and its new-head CI accepted at merge ref `789586d7`; PR #280 merged to main at `3dc85529` and its actual main-push CI and seven-module safety comparison accepted; the record was first merged by PR #280 and is now byte-frozen, so its dated draft and status wording is historical; current (2026-10-11, after Codex's 17:11:44 UTC acceptance): the terminal-docs PR #281 merged to main at `d5b4bec3` and its main-push CI accepted, with the record's bytes unchanged; Plan 11.30 v5 completed and archived (operator grant "YES", a direct operator reply in Codex chat on client date 2026-10-12, recorded by Codex at 2026-10-11 19:05:47 UTC, answering the exact question that approved closing Plan 11.30, archiving v5 and the kickoff, Checkpoint A, Checkpoint B dated 2026-10-05 and Task 3 records byte-for-byte, and one normal-hook closing commit); cleanup held |
| [ADR-021: Bounded GitHub authority switch](decisions/ADR-021-bounded-github-authority-switch.md) | Mechanism for moving the status authority of 49 Optimus work records to their GitHub issues, accepted by the operator on 2026-10-12 (sources S6 and S7) and activated by the merge of PR #285 (`f4f0e2f8`, 2026-10-12) |
| [ADR-022: GitHub Issues as the work register](decisions/ADR-022-github-issues-as-the-work-register.md) | Corrects only ADR-021's pool-first intake: new plans, defects and follow-ups are created as issues, the unfinished remainder of the open work migrates in dependency-bounded groups, the backlog is transitional and documents keep scope, design, history and pointers; operator requirement accepted (source S8), mechanism proposed by Claude and reviewed by Codex |
| [ADR-023: Plan 12.2 shipped admission and default planner](decisions/ADR-023-plan12-shipped-empirical-admission-and-default-planner.md) | Historical exact-snapshot Haiku 5.5 empirical admission (`verified: false`) and the medium-then-easy default planner. ADR-025 supersedes the one-hash/one-model admission mechanism with per-entry evidence and the trusted operator override; ADR-023's other decisions and residuals remain |
| [ADR-024: Accepts ADR-009 as scoped](decisions/ADR-024-accepts-adr-009-loop-control-phase-1-scope.md) | Loop control Phase 1: a detector, one nudge and a Continue/Stop check-in, escalation after Auto; operator D1–D3 (source S10) |
| [ADR-025: Models are configuration](decisions/ADR-025-models-are-configuration-per-model-admission.md) | Per-model admission evidence in each registry entry, a conservative default estimator, per-model stops and the operator override; operator N1(a) and N2(a) (source S11) |
| [ADR-026: Exception routes accept one unflagged guardrail stage](decisions/ADR-026-exception-routes-accept-one-unflagged-guardrail-stage.md) | #400 option b1: one `guardrail` stage reporting `flagged` false and no detection, decision, action, conflict or scope passes the exception-route pipeline check; every other stage still refuses; residual risk accepted by the operator |
| [ADR-027: Idle client-MCP lifetime](decisions/ADR-027-idle-client-mcp-lifetime-contract.md) | Retain in-memory continuity; positive idle delay and fresh atomic permission renewal |
| [ADR-028: Accepts ADR-007 with arm H](decisions/ADR-028-accepts-adr-007-auto-judge-h.md) | Auto mode's per-turn judge: the rules when confident, otherwise Jev, routing up when unsure; chosen by the Plan 12.4 pilot's pre-registered rule; operator acceptance (source S13) |
| [Evidence, 2026-09-30](decisions/2026-09-30-industry-context-cost-and-model-evidence.md) | Industry practice, OpenRouter controls, model catalog snapshot |

## Research (input for Plan 12)

| Document | What it is |
|---|---|
| [Context window optimization strategy](context-window-optimization-strategy.md) | Context selection, packing, compaction and cost gates |
| [GraphRAG research](graphrag-research.md) | Graph-based retrieval options |
| [Agent evaluation tooling research](agent-evaluation-tooling-research.md) | Options for measuring agent output quality |

## Operations and policy

| Document | What it is |
|---|---|
| [Local live dependencies runbook](runbooks/local-live-dependencies.md) | Starting Redis, the Gateway and Phoenix locally |
| [Plan 12.2 Stage C live run runbook](runbooks/plan-12-2-stage-c-live-run.md) | The bounded Stage C test release (r9): its guard, launches, custody checks and stop and continuation rules |
| [Evidence and local artifact policy](governance/evidence-and-local-artifact-policy.md) | What counts as repository evidence |

## Planning

Status, priority and ownership live in the record's GitHub issue; the transitional backlog holds them only for records not yet marked `Moved` and takes no new work entries (a new plan's issue-only registry pointer row excepted). Plans do not declare their own status.

| Document | What it is |
|---|---|
| [Plans folder guide](superpowers/plans/README.md) | How plans are added, revised and archived |
| [Consolidated backlog](superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md) | Transitional register: work, status and next gates only for records not yet moved to GitHub issues (`Moved` rows link theirs); it takes no new work entries (a new plan's issue-only registry pointer row excepted) |
| [Work status table][work-status-hosted] | Live table of the repository's GitHub issues, the work register, hosted on GitHub Pages (no checkout needed); the issues are authoritative. Source: [`work-status.html`](work-status.html). Fallback: the repository's open issues on GitHub, linked from the page and from the backlog |
| [Phase 1 roadmap](superpowers/plans/2026-07-01-phase-1-roadmap.md) | Historical sequencing of Phase 1 |
| [Plan 11 v1.0 milestone charter](superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md) | What v1.0 must contain |
| [Hardening masterplan](superpowers/plans/hardening-runtime-quality-masterplan.md) | The 15 hardening tracks and their status |
| [Hardening: CI guardrail truthfulness](superpowers/plans/hardening-ci-guardrail-truthfulness-implementation.md) | CI guardrail enforcement contract |

Live plans (each listed in the backlog's live plan registry):

| Plan | What it is |
|---|---|
| [Idle client-MCP lifetime v3](superpowers/plans/2026-10-26-idle-mcp-suspension-main-port_v3.md) | #427; A-derived lifetime owner and idle renewal on main |
| [Plan 11.7 v3: Zed resume](superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation_v3.md) | Resume an ACP session in Zed |
| [Plan 11.23: client-MCP runtime composition](superpowers/plans/2026-08-18-plan-11-23-p11-fu-20-client-mcp-runtime-composition.md) | Client-supplied MCP servers at runtime |
| [Plan 11.24 v6: guided session-load probe](superpowers/plans/2026-08-18-plan-11-24-zed-guided-session-load-probe_v6.md) | Probe of Zed's `session/load` |
| [Plan 11.27 v12: Git test immunity and CI secret scan](superpowers/plans/2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v12.md) | Latest version; v2 to v10 are in `archive/` |
| [Plan 11.28: Parallel local test context](superpowers/plans/2026-10-02-plan-11-28-parallel-local-test-context-implementation.md) | Default-run attribution, application-folder isolation and parallel acceptance in separate worktrees |
| [P11-FU-6 v2: bounded early POST rejection](superpowers/plans/2026-09-05-p11-fu6-bounded-early-post-rejection_v2.md) | Gateway early-rejection correction |
| [Local-hook UTF-8 repair](superpowers/plans/2026-09-06-local-hook-utf8-repair.md) | Pre-commit hook decoding fix |
| [Evidence collector](superpowers/plans/evidence-handoff-evidence-collector-implementation.md) | Evidence-handoff collector |

## Current designs

| Document | What it is |
|---|---|
| [Idle client-MCP lifetime design](superpowers/specs/2026-10-26-idle-mcp-suspension-main-port-design.md) | Self-contained #427 contract; [intake receipt](superpowers/reports/2026-10-26-idle-mcp-suspension-main-port-receipt.md) |
| [Plan 12.2 Context Engine design (v3)](superpowers/specs/2026-10-01-plan-12-2-context-engine-design_v3.md) | Three history strategies, exact host facts, floor, registry and cost integration; v3 adds the CP4 measured adoption and D7 disposition |
| [Plan 12.2 ordinary compaction shipping contract](superpowers/specs/2026-10-18-plan-12-2-ordinary-compaction-shipping-contract.md) | Scoped successor for the shipping candidate: the ordinary composition, the shipped empirical exception, the shared numeric policy, approval migration and the closure gates; filed 2026-10-18; its acceptance and closure gate are tracked in #237 |
| [Plan 12.2 Task 1 contracts (v3)](superpowers/specs/2026-10-02-plan-12-2-task1-contracts_v3.md) | Engine data, summary format, registry/trust/capacity, host integration, D6; v3 adds the CP4 numeric adoption and the trusted test composition. The 2026-10-02 acceptance belongs to the archived first edition |
| [Plan 12.1 advisory-answer design](superpowers/specs/2026-09-29-plan-12-1-plan-chat-advisory-answer-design.md) | ACP Agent/Chat mode, prose-answer and history contract |
| [ACP runtime hardening audit design](superpowers/specs/2026-08-29-plan-11-26-acp-runtime-hardening-audit-design.md) | Governing audit for ACP runtime hardening |
| [Plan 11.28 parallel local test context design](superpowers/specs/2026-10-02-plan-11-28-parallel-local-test-context-design.md) | Selection boundary, native ownership, validated ancestry and proof-based child isolation |
| [A2A ledger design v2](superpowers/specs/evidence-handoff-a2a-ledger-design_v2.md) | Agent-to-agent ledger and channel |
| [A2A ledger remediation scoping](superpowers/specs/evidence-handoff-a2a-ledger-remediation-scoping.md) | Scope of the open ledger remediation slices |
| [Evidence collector design](superpowers/specs/evidence-handoff-evidence-collector-design.md) | Evidence-handoff collector |
| [Zed render-observation design](superpowers/specs/evidence-handoff-zed-render-observation-design.md) | Observing what Zed actually renders |

## Current reviews and references

| Document | What it is |
|---|---|
| [Plan 12.2 offline delivery merge record](superpowers/reviews/2026-10-08-plan-12-2-offline-merge-record.md) | PR #276 merged as c509fc8 on 2026-10-08, with Package A (#216 marked merged); offline merge gate complete, not a full CP4 pass; three live obligations remain deferred |
| [Plan 12.2 CP4 offline delivery disposition](superpowers/reviews/2026-10-08-plan-12-2-cp4-offline-delivery-disposition.md) | Operator decision, 2026-10-08: offline delivery through 2068366 is complete; Luna qualification, the summary-quality receipt and real-editor Task 13 are deferred as UNRUN obligations; not a full CP4 pass |
| [Plan 12.2 CP4 offline review disposition](superpowers/reviews/2026-10-04-plan-12-2-cp4-offline-review-disposition.md) | Codex accepts the offline batch at cf9bb9d with declared scope; five rulings; full CP4 remains open |
| [Plan 11.25 producer-instrumentation correction](superpowers/reviews/2026-10-01-plan-11-25-effect-instrumentation-correction.md) | Checked historical steps do not establish current runner instrumentation; Plan 12 owns the repair |
| [A2A ledger independent audit](superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md) | Findings the open ledger slices fix |
| [CI baseline report exceptions](superpowers/reviews/2026-09-06-baseline-report-exceptions.json) | Live exception set for the CI guardrail track |
| [Plan 9.96 logging-surface audit](superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json) | Historical, but stays here: Plan 11.7's custody tooling binds this exact path |
| [MCP security best practices](superpowers/reports/2026-08-05-mcp-gateway-security-best-practices-reference.md) | Reference for the open client-MCP items |

## Archives

- [Older design document versions](archive/)
- [Finished and superseded plans](superpowers/plans/archive/)
- [Superseded designs](superpowers/specs/archive/)
- [Past reviews and approvals](superpowers/reviews/archive/)
- [Past reports](superpowers/reports/archive/)
- [Past runbooks](runbooks/archive/)
- [Older publication sources](sources/archive/)

- [Plan 12.2 Package A delivery record](superpowers/reviews/2026-10-02-plan-12-2-package-a-delivery.md) — local commits, offline acceptance, residual and evidence custody.

[work-status-hosted]: https://vibhanshu-agarwal.github.io/optimus-cost-agent/work-status.html
