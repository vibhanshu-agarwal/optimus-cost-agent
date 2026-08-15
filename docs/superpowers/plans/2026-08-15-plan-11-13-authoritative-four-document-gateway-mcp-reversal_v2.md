# Plan 11.13: Authoritative Four-Document Gateway-MCP Reversal — v2

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. A checkbox may change only after its named verification command has passed and the reviewer checkpoint records the evidence.

**Goal:** Publish v2.18/v2.41/v1.3/v1.7 as the authoritative documents, removing the retired Gateway-brokered MCP contract while preserving the live client-supplied ACP `mcpServers` path and its real-dependency evidence boundary.

**Architecture:** This v2 is a narrow, forward-only successor to the approved v1 publication plan. It replaces v1 Task 0 Step 2 and v1 Task 1 in full so the workspace-identity/durable-approval audit covers all four base authoritative documents. Every other task, constraint, interface, required artifact, command, definition-of-done item, and explicit exception in v1 remains mandatory and unchanged.

**Tech Stack:** Markdown, SVG, JSON, Python publication helpers (`pypdf`, `reportlab`, Pillow), Pandoc 3.1.3, WeasyPrint 61.1, Poppler 24.02.0, WSL2 Ubuntu-24.04, the approved Windows Python assembly exception, `pytest`, Ruff, Git, and SHA-256.

## Status, authority, and frozen predecessor

This `_v2` file is the live Plan 11.13 execution contract. The v1 plan remains an immutable, approved historical artifact. An executor must read v1 followed by this v2; where they differ, this v2 controls. This revision does not authorize publication work before the v2 plan-review PR merges.

| Artifact | Path | `git hash-object` pin | Treatment |
|---|---|---:|---|
| Frozen v1 plan | `docs/superpowers/plans/2026-08-15-plan-11-13-authoritative-four-document-gateway-mcp-reversal.md` | `b54aa7bf33c9e8008f05ca348a37ee004112e329` | Immutable; do not edit, rename, or restage. |
| Live successor | `docs/superpowers/plans/2026-08-15-plan-11-13-authoritative-four-document-gateway-mcp-reversal_v2.md` | Compute at pickup | This document; supersedes only the v1 provisions stated below. |
| Plan 11.15 authority | `docs/superpowers/plans/2026-08-15-plan-11-15-p11-fu-18-29-durable-approval-identity.md` and its approved successor, if one exists at pickup | Record at pickup | Comparison authority only; Plan 11.13 must not implement or publish its identity mechanics. |

## Exact amendment and unchanged scope

### Superseded v1 provisions

1. **Task 0, Step 2** is replaced because two plan artifacts now exist: immutable v1 and live v2.
2. **Task 1 in full** is replaced. Its audit expands from base HLD v2.16 and LLD v2.39 to all four base authoritative documents: HLD v2.16, LLD v2.39, Guardrails v1.1, and Test Strategy v1.5. It still compares their current counterparts—v2.17, v2.40, v1.2, and v1.6—solely to locate amendment-era wording and page context.
3. Every reference in v1 to a single `NOT_REPRESENTED` / `CURRENT` / `STALE` result now means **one typed result per base document**, plus a summary result. A stale result in any document uses the already-reserved `P11-FU-30` custody path.

### Still unchanged from v1

- The only new authoritative PDF outputs are HLD v2.18, LLD v2.41, Guardrails v1.3, and Test Strategy v1.7; v2.17/v2.40/v1.2/v1.6 are immutable inputs, pinned by the four v1 SHA-256 values.
- The historical `docs/sources/mcp-gateway-architecture-amendment/` package remains immutable. Publication uses the sibling `docs/sources/gateway-mcp-authoritative-document-reversal/` package.
- The Task 3 bidirectional audit remains a hard gate: all retired Gateway-broker claims must be absent and all client-supplied ACP `mcpServers`/local-validation/pre-tool-guard/untrusted-output/independently-authored-client marker claims must remain present with client-owned wording.
- Rendered-page inspection remains a separately recorded gate. A source diff, successful build, fragment build, or validator exit code cannot substitute for visual inspection of the rendered pages.
- Plan 11.13 never corrects, adds, removes, or rephrases workspace-identity or durable-approval mechanics in any of the four new PDFs. Its sole identity outcome is a typed evidence finding and, only if required, an owned future pool entry.
- All v1 Tasks 2–7, their commands, their evidence requirements, their explicit exceptions, their definition of done, and the execution-handoff restriction remain in force.

## Replacement Task 0 Step 2: Confirm revision chain and deferred identifier

- [ ] **Step 2: Confirm the immutable v1/live-v2 chain and that `P11-FU-30` remains free.**

```powershell
git hash-object docs/superpowers/plans/2026-08-15-plan-11-13-authoritative-four-document-gateway-mcp-reversal.md
rg --files docs/superpowers/plans -g '*11-13*'
rg -n '^### P11-FU-30:|\| `P11-FU-30` \|' docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md docs/superpowers/plans/2026-07-01-phase-1-roadmap.md
```

Expected: the v1 hash equals `b54aa7bf33c9e8008f05ca348a37ee004112e329`; exactly the v1 and this v2 Plan 11.13 files exist; v2 is the only live execution contract; and `P11-FU-30` is absent unless a prior independently reviewed execution has already produced a documented `STALE` finding. A third plan revision, a v1 hash mismatch, or a conflicting follow-up requires a reviewed successor plan before sources are created.

## Replacement Task 1: Answer the all-four-base-document workspace-identity question without widening scope

**Files:** Read base/current HLD v2.16/v2.17, LLD v2.39/v2.40, Guardrails v1.1/v1.2, and Test Strategy v1.5/v1.6; amendment changed pages; Plan 11.15's approved identity contract; and current identity rows. Create page-level findings in the new reversal package `verification.md` and Plan 11.13 evidence report. Conditionally modify only the pool/roadmap for `P11-FU-30`.

**Interfaces:** Consumes all four base authoritative texts and the Plan 11.15 v3 workspace-identity/durable-approval contract. Produces a per-document `NOT_REPRESENTED`, `CURRENT`, or `STALE` result plus one summary. It never produces a Plan 11.13 identity change in the four new PDFs.

- [ ] **Step 1: Extract, search, and cite every base/current document at page level.**

```bash
mkdir -p tmp/pdfs/plan-11-13/extracted
pdftotext -layout docs/Optimus-Cost-Agent-Architecture-v2.16.pdf tmp/pdfs/plan-11-13/extracted/hld-v2.16.txt
pdftotext -layout docs/Optimus-Cost-Agent-Architecture-v2.17.pdf tmp/pdfs/plan-11-13/extracted/hld-v2.17.txt
pdftotext -layout docs/Optimus-Cost-Agent-LLD-v2.39.pdf tmp/pdfs/plan-11-13/extracted/lld-v2.39.txt
pdftotext -layout docs/Optimus-Cost-Agent-LLD-v2.40.pdf tmp/pdfs/plan-11-13/extracted/lld-v2.40.txt
pdftotext -layout docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.1.pdf tmp/pdfs/plan-11-13/extracted/guardrails-v1.1.txt
pdftotext -layout docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.2.pdf tmp/pdfs/plan-11-13/extracted/guardrails-v1.2.txt
pdftotext -layout docs/Optimus-Cost-Agent-Test-Strategy-v1.5.pdf tmp/pdfs/plan-11-13/extracted/test-strategy-v1.5.txt
pdftotext -layout docs/Optimus-Cost-Agent-Test-Strategy-v1.6.pdf tmp/pdfs/plan-11-13/extracted/test-strategy-v1.6.txt
rg -n -i 'workspace identity|durable approval|st_ctime|st_ino|workspace_digest|revalidate_workspace_identity|WorkspaceIdentity|approval lifecycle|re-?approval|manifest hash|identity' tmp/pdfs/plan-11-13/extracted
```

For every hit and every tested no-hit, record document/version, search term, extracted-text line, and 1-based PDF page. Confirm a cited page with `pdftotext -layout -f <page> -l <page> <pdf> -`; do not infer page number solely from a continuous extraction. Classify generic human approval, MCP descriptor/manifest identity, or test-tier wording separately from durable workspace identity. The established amendment fact remains: HLD changed pages have no workspace-identity terms; LLD revalidation concerns Gateway URLs, redirects, hosts, or MCP policy—not workspace identity. Guardrails and Test Strategy are now equally required evidence sources, not presumptively stale because they use approval or identity words.

- [ ] **Step 2: Compare each base-document finding to the Plan 11.15 v3 mechanics.**

For each of the four base documents, compare page-level evidence to the frozen Plan 11.15 contract: stable `workspace-identity-v3` encoding excludes `st_ctime_ns`; Git context is tri-state `PRESENT` / `ABSENT` / `UNAVAILABLE`; immediate-root topology is checked independently; transient probes are retried at most three times; unavailable evidence preserves approval rather than asserting a change; and v2-to-v3 durable-record promotion is authenticated, observable, and not applied to one-shots. Record exactly one typed result per base document:

1. `NOT_REPRESENTED` — the document has no durable workspace-identity/approval-lifecycle mechanism; generic approval or MCP manifest identity alone belongs here, with the cited reason.
2. `CURRENT` — the document contains a compatible mechanism, with exact page/text and corresponding Plan 11.15 property.
3. `STALE` — the document contains a superseded durable workspace-identity or approval-lifecycle mechanic, with exact page/text and mismatch.

Then record a deterministic summary: `NOT_REPRESENTED` only if all four are not represented; `CURRENT` if none is stale and at least one is current; otherwise `STALE`. A no-hit result is successful evidence, never a skipped audit. Do not treat a related MCP descriptor/manifest reapproval, Agent Mode human approval, or approval-test tier as workspace identity without the actual durable binding/lifecycle claim.

- [ ] **Step 3: Create `P11-FU-30` only if any base-document result is `STALE`.**

Add `P11-FU-30 — Authoritative Workspace-Identity Contract Alignment` to the tracked/not-yet-scheduled pool and roadmap. It must enumerate each stale base document, page, and exact wording; cite the conflicting Plan 11.15 property; name the future authoritative-document owner; and state that Plan 11.13 intentionally preserved the stale identity wording. If all results are `NOT_REPRESENTED` or `CURRENT`, create no row. In every result class, do not add workspace identity or durable-approval mechanics to HLD v2.18, LLD v2.41, Guardrails v1.3, or Test Strategy v1.7.

## Replaced Definition-of-Done and self-review rows

Replace the v1 identity definition-of-done row with:

- [ ] All four base documents have page-level typed identity findings; the deterministic summary is recorded; and any `STALE` result has the named `P11-FU-30` owner without widening this publication.

Replace the v1 Plan Self-Review identity row with:

| Requirement | Coverage |
|---|---|
| Plan 11.15 workspace-identity answer and custody across all four base documents | Replacement Task 1; v1 Task 6 |

## Execution handoff

After this v2 is independently reviewed and merged, execute v1 as amended by this v2 from a dedicated fresh worktree using `superpowers:subagent-driven-development` or `superpowers:executing-plans`. Do not start publication on this plan-PR branch. The executor reads the reviewer checkpoint log, verifies the frozen v1 pin and all four old-PDF pins from disk, then works the unchecked tasks in order with Replacement Task 0 Step 2 and Replacement Task 1 substituted for their v1 counterparts.
