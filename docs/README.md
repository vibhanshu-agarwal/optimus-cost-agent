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
| [Architecture (HLD) v2.18](Optimus-Cost-Agent-Architecture-v2.18.pdf) | High-level design |
| [LLD v2.41](Optimus-Cost-Agent-LLD-v2.41.pdf) | Low-level design |
| [Test Strategy v1.7](Optimus-Cost-Agent-Test-Strategy-v1.7.pdf) | Testing approach |
| [Agent Execution Guardrails and Workflow Strategy v1.3](Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.3.pdf) | Execution guardrails |
| [Architecture Roadmap v10](Optimus-Architecture-Roadmap-v10.pdf) | Long-range roadmap |
| [Publication sources for the current PDFs](sources/gateway-mcp-authoritative-document-reversal/) | Sources the HLD v2.18, LLD v2.41, Guardrails v1.3 and Test Strategy v1.7 were built from |

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
| [Evidence and local artifact policy](governance/evidence-and-local-artifact-policy.md) | What counts as repository evidence |

## Planning

Status, priority and ownership live only in the backlog; plans do not declare their own status.

| Document | What it is |
|---|---|
| [Plans folder guide](superpowers/plans/README.md) | How plans are added, revised and archived |
| [Consolidated backlog](superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md) | The one live registry of work, status and next gates |
| [Phase 1 roadmap](superpowers/plans/2026-07-01-phase-1-roadmap.md) | Historical sequencing of Phase 1 |
| [Plan 11 v1.0 milestone charter](superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md) | What v1.0 must contain |
| [Hardening masterplan](superpowers/plans/hardening-runtime-quality-masterplan.md) | The 15 hardening tracks and their status |
| [Hardening: CI guardrail truthfulness](superpowers/plans/hardening-ci-guardrail-truthfulness-implementation.md) | The active hardening track |

Live plans (each listed in the backlog's live plan registry):

| Plan | What it is |
|---|---|
| [Plan 11.7 v3: Zed resume](superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation_v3.md) | Resume an ACP session in Zed |
| [Plan 11.23: client-MCP runtime composition](superpowers/plans/2026-08-18-plan-11-23-p11-fu-20-client-mcp-runtime-composition.md) | Client-supplied MCP servers at runtime |
| [Plan 11.24 v6: guided session-load probe](superpowers/plans/2026-08-18-plan-11-24-zed-guided-session-load-probe_v6.md) | Probe of Zed's `session/load` |
| [Plan 11.27 v12: Git test immunity and CI secret scan](superpowers/plans/2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v12.md) | Latest version; v2 to v10 are in `archive/` |
| [P11-FU-6 v2: bounded early POST rejection](superpowers/plans/2026-09-05-p11-fu6-bounded-early-post-rejection_v2.md) | Gateway early-rejection correction |
| [Local-hook UTF-8 repair](superpowers/plans/2026-09-06-local-hook-utf8-repair.md) | Pre-commit hook decoding fix |
| [Evidence collector](superpowers/plans/evidence-handoff-evidence-collector-implementation.md) | Evidence-handoff collector |

## Current designs

| Document | What it is |
|---|---|
| [ACP runtime hardening audit design](superpowers/specs/2026-08-29-plan-11-26-acp-runtime-hardening-audit-design.md) | Governing audit for ACP runtime hardening |
| [A2A ledger design v2](superpowers/specs/evidence-handoff-a2a-ledger-design_v2.md) | Agent-to-agent ledger and channel |
| [A2A ledger remediation scoping](superpowers/specs/evidence-handoff-a2a-ledger-remediation-scoping.md) | Scope of the open ledger remediation slices |
| [Evidence collector design](superpowers/specs/evidence-handoff-evidence-collector-design.md) | Evidence-handoff collector |
| [Zed render-observation design](superpowers/specs/evidence-handoff-zed-render-observation-design.md) | Observing what Zed actually renders |

## Current reviews and references

| Document | What it is |
|---|---|
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
