# Consolidated Deferred Follow-Ups Backlog

## Purpose

This document is the single source of truth for every currently open, unscheduled `P#-FU-#`
follow-up raised across the Plan 9-series (Plan 9 through Plan 9.99). Before this document existed,
each follow-up lived only inside the "Deferred Follow-Ups" section of whichever plan originally
raised it, cross-referenced (if at all) by a one-line mention in the roadmap. Two of them
(Plan 9.98-FU-1 and FU-2) were fully implemented and merged without ever getting a roadmap entry at
all, discovered only by manual audit. This document exists so that stops happening: everything
still open lives in exactly one place, and nothing gets promoted into a real plan without being
removed from here first.

This document does not itself implement anything. Every entry below either becomes its own
numbered plan (following [[plan-numbering-convention]]-style sequential allocation) or gets folded
into an already-designated future plan (e.g. Plan 11, Plan 9.97) when that plan is actually
scheduled. The roadmap's `## Backlog: Consolidated Deferred Follow-Ups` section links here; it does
not duplicate this content.

## How to use this document

- **Adding a new item:** When a plan's implementation or review surfaces a new deferred follow-up
  (including ones emerging from Plan 9.96 Task 9 or Plan 9.97, once either actually lands), add it
  here with the same fields every other entry uses (Raised / Origin / Designated future plan /
  Trigger or acceptance criteria / Status), rather than leaving it only inside that plan's own
  Deferred Follow-Ups section or a scattered roadmap backlog entry.
- **Promoting an item:** When an item is scheduled into a real numbered plan, mark its Status as
  `Promoted -> Plan N` with the date and a link to the new plan file, and leave the entry in place
  (do not delete history) rather than removing the row.
- **Closing an item:** When an item is fully implemented, mark Status as `Closed` with the
  implementation commit/PR and evidence citation, the same way other closed follow-ups are recorded
  elsewhere in this project's roadmap.

## Open items

### P9.8-FU-2: Intelligent ambiguous-reference ranking

**Raised:** 2026-07-10, in Plan 9.8's own Deferred Follow-Ups
(`docs/superpowers/plans/2026-07-10-plan-9-8-task-aware-workspace-context.md`).

**Designated future plan:** Plan 11 (Context Window Optimization and Intelligent Selection).

**Acceptance criteria:** Candidate ranking uses the accepted relevance/trust/freshness/dependency
policy, measures wrong-target regret, and retains a fail-closed threshold. Until this lands,
ambiguity stays visible and deterministic (Plan 9.8's current behavior).

**Status:** Open, not yet scheduled.

### P9.8-FU-3: Dynamic context budgets and required-file summarization

**Raised:** 2026-07-10, in Plan 9.8's own Deferred Follow-Ups
(`docs/superpowers/plans/2026-07-10-plan-9-8-task-aware-workspace-context.md`).

**Designated future plan:** Plan 11 (Context Window Optimization and Intelligent Selection).

**Acceptance criteria:** Budget changes are model-aware, cost-attributed, injection-safe, measured
against the null baseline, and never silently omit required evidence.

**Status:** Open, not yet scheduled.

### P9.8-FU-5: Zed Refusal-Rendering Stability

**Raised:** 2026-07-11 during Plan 9.8 live evidence. Zed 1.10.2 correctly received and briefly
rendered the ambiguous-refusal corrective text, then panicked in native client code with
`range end index 3 out of range for slice of length 2`. The agent wire contract and independent
`acpx` durable refusal UI remain proven.

**Designated future plan:** None yet — sole custody is this entry. Plan 9.75 was already complete
when the client-stability issue was discovered, and its evidence report classifies the panic as
separate from the ACP conformance fix. Do not reopen Plan 9.75 and do not silently fold this work
into Plan 11.

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

**Designated future plan:** Plan 11 (Context Window Optimization and Intelligent Selection).

**Acceptance criteria:** An approved design may replace fixed fail-closed carryover with
provenance-preserving compression, regret measurement, and calibration gates. Until then, overflow
remains terminal (Plan 9.85's current behavior).

**Status:** Open, not yet scheduled.

### P9.85-FU-2: Dynamic planning-evidence partition

**Raised:** 2026-07-11, in Plan 9.85's own Deferred Follow-Ups
(`docs/superpowers/plans/2026-07-11-plan-9-85-multi-turn-read-observe-replan.md`).

**Designated future plan:** Plan 11 (Context Window Optimization and Intelligent Selection).

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

**Status:** Open, not yet scheduled.

### P9.87-FU-1: Mechanical Current-Raw-Evidence Grounding Guard

**Raised:** 2026-07-12, in Plan 9.87's own Deferred Follow-Ups
(`docs/superpowers/plans/2026-07-12-plan-9-87-model-initiated-replanning-live-refusal.md`). Carried
forward, unresolved, through Plan 9.88's closure ceremony and Plan 9.95's custody-transfer record.

**Designated future plan:** Plan 9.97 (Mechanical Current-Raw-Evidence Grounding), already named in
the roadmap as Tracked, Not Yet Scheduled — this is that plan's sole owned follow-up.

**Trigger:** A content-correct FU-5 final plan or later evidence shows exact policy bytes can pass
through observations despite the prompt prohibition.

**Acceptance criteria:** Define mechanical provenance between final WRITE content and current-turn
raw ranges without logging source bodies or silently absorbing Plan 11's intelligent-selection
scope. This lane must not absorb or be absorbed by Plan 11.

**Status:** Open, not yet scheduled. Plan 9.97 already holds this plan's numbered slot in the
roadmap; this entry exists so the underlying acceptance criteria live in the same consolidated place
as every other open item rather than only inside the originating Plan 9.87 document.

## Explicitly out of scope for this document

Plan 9.96's two "sole custody" owned follow-ups (`P9.85-FU-7`, `P9.9-FU-1`) and the future
`P9.96-FU-1` through `FU-7` disclosures are deliberately **not** listed here. They already have an
active, imminent closure path — Plan 9.96 Task 9 Step 6 closes the first two directly, and a
standing scope-conflict ruling requires the remaining seven to be added as new roadmap entries only
after Task 9's evidence report lands. Add them here instead only if Task 9 closes without resolving
them and they become genuinely deferred, unscheduled work.
