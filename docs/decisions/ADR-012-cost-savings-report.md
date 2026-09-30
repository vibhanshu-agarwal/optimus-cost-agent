# ADR-012: A cost-savings report is a Plan 12 feature

**Status:** Accepted-with-open-items. The requirement is accepted; the design is proposed; nothing is
commissioned.
**Date:** 2026-09-30.
**Decider:** the operator set the requirement. The design options are Claude's proposal, awaiting Codex.

## Context

**Operator, verbatim (2026-09-30):**

> "One of my initial requirements was to build some kind of table that shows how much Optimus saved on
> cost - so there benchmarks and our own tests will come in handy- let us add it as one of the features of
> Plan 12 (need to record it so it is not lost again)"

**The original product description** (in the brainstorm diary, outside the repository) says Optimus
"reduces spend using DSPy-based request-type classifiers, Redis-backed smart memory management, and
intelligent context management algorithms, further cutting cost by reducing hallucinations, curbing
unnecessary agent loops, and applying smart caching strategies". A savings report is how that claim gets
measured and shown.

**What exists (checked on `main` at `e41b66d`):**

- **No backlog item or plan owns a user-facing savings report.**
- **Related, but not the same thing:**
  - `docs/context-window-optimization-strategy.md` has a "fully-loaded cost savings target, currently
    placeholder >= 15%" and "offline promotion gates";
  - the Phase 1 roadmap rules that "placeholder targets stay placeholders" until they are calibrated on
    Optimus evaluation runs;
  - Plan 8 reserved golden-report fields for future promotion gates.

  Those are internal quality gates. This feature is a report the user sees.
- **Inputs it would use:**
  - per-call usage and cost, including which model actually answered. The known gap is owned by
    `P11.26-CAND-2-TELEMETRY-CONTRACT`;
  - registry prices (ADR-004);
  - golden tasks (Plan 8);
  - public benchmarks (evidence file, section D).

## Options considered: what "saved" is measured against

| Baseline | How | For | Against |
|---|---|---|---|
| B1: premium-model counterfactual | Price the same tokens at a reference model's list price, for example Sonnet 5.5 | Live, cheap to compute | Assumes the same token counts across models; overstates savings when the premium model was not needed; the reference is a choice |
| B2: no-optimization counterfactual | Price the same model as if it had received full verbatim history, no caching and no routing | Isolates Optimus's own techniques | Estimated, not observed; ignores quality |
| B3: measured A/B on golden tasks | Run the same tasks with and without Optimus's features, or against a baseline agent, and compare **cost per successful task** | Real, and includes quality | Paid and periodic, not live |
| B4: external benchmarks | Artificial Analysis cost per task and similar | Free, third-party, credible | Different tasks and harnesses from Optimus's workload |

## Decision

**Authority boundary:**

- **Accepted by the operator:** the requirement, that a cost-savings report is a Plan 12 feature. Claude
  and Codex also accept the four baselines as the design options.
- **Proposed:**
  - the design;
  - the delivery surface and storage;
  - the reference baseline.
- **Not commissioned:** implementation and paid comparisons.

**Proposed design:**

- **Net savings is one subtraction:** *comparable baseline total* minus *actual fully loaded total*.
  - The actual total already includes summarizing, classification, review, retries, fallbacks and
    escalations, so they are **not deducted a second time**.
- **Label each estimate for what it is:**
  - **B1** is token-price substitution. It is not evidence of realized savings.
  - **B2** is a counterfactual that depends on the workload, not an observed alternative.
  - **B1 and B2 overlap, so they are never added together.**
- **Show everything, including bad news:**
  - negative savings;
  - incomplete coverage, abstaining from a definitive total or percentage when accounting or the baseline
    is incomplete;
  - provenance: model, route, pricing date, strategy, stage, request, run and session.
- **Measured comparisons.** B3 compares matched outcomes and quality on the golden tasks. B4 is labelled
  context only.
- **No fixed saving percentage is accepted.** The ≥15% figure in the context strategy document stays an
  uncalibrated placeholder.
- **The report never claims savings it cannot show the basis for.**
- **Backlog entry:** `P12-FU-2` in the consolidated backlog, drafted by Codex on 2026-09-30.

## Open items

1. **Where the table appears.** Options:
   - an ACP slash command in the IDE (for example `/savings`, advertised through ACP's available-commands
     update);
   - a Markdown report in the workspace;
   - the observability dashboard.
2. **The reference model for B1,** and how results are grouped (per session, per day).
3. **Paid-call authority for the B3 runs.**

## Consequences

- **Easier:** the product claim becomes demonstrable, and model or strategy choices can be judged on
  measured net savings.
- **Harder:** it depends on complete per-call attribution. Until that exists, the report must mark itself
  incomplete rather than guess.
