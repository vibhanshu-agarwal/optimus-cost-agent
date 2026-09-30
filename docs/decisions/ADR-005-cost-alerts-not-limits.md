# ADR-005: Cost policy: alerts and warnings, not limits

**Status:** Accepted. **Date:** 2026-09-30. **Decider:** the operator.

## Context

**Operator, verbatim (2026-09-30):**

> "2. I never asked for a per turn budget - it is agents (i suppose you and codex that decided it). As I
> understand that was meant for test runs"

> "2. Option A. We need anti-hallucination controls such as loop detection and budget- this was one of
> the requirements I had laid down early on but seems to be lost? I don't want the user to not be able to
> complete a task because of our cost controls.No limit from our end - our job is alerts and warnings
> based on decided thresholds"

> "4. This too was determined by the agents - I don't want any cost control strategy to actually stop a
> user from completing his work."

**Facts. Agents set both existing caps:**

- **$0.05** is the `AgentRunRequest.max_cost_usd` default (`agent/models.py:98`), added 2026-07-07 in
  commit `3eeb629` (Plan 9.5).
  - Every IDE prompt uses it; ACP passes no override.
  - It is checked **after** each call, so a call can overshoot.
  - The turn then ends `PLANNING_BUDGET_EXHAUSTED`.
  - On Haiku it stops long threads well before the history cap.
- **$0.25** is `OPTIMUS_LIVE_MAX_COST_USD`, the Plan 9.6 live-test cap. The launch gate displays and
  approves it, but nothing reads it at run time.

**Governance records that assume hard caps:**

- `P9.85-FU-3`: a session/project spend **ceiling** that fails closed;
- the Plan 9.96 per-run `max_cost_usd` contract;
- HLD v2.16 §§5A and 11, LLD v2.39 §§0A, 9D and 10A, and Guardrails v1.1 §§7.2 and 9. They make the local
  Gateway "the authority for current-run budget caps".

**Industry practice** (research sweep, 2026-09-30; see the
[evidence file](2026-09-30-industry-context-cost-and-model-evidence.md)): per-task dollar caps are rare
and off by default.

- Claude Code has one only in print mode; OpenHands V0's defaults to 0, meaning no limit.
- Most agents rely on account or billing budgets, request caps, or showing the cost.

**OpenRouter keys** can carry a USD spending limit (`limit`) with a daily, weekly or monthly
`limit_reset`.

## Options considered

| | A: no Optimus cost stop; alerts at thresholds (chosen) | B: a high "runaway" per-turn cap | C: only an OpenRouter key limit | D: a session/daily ceiling inside Optimus |
|---|---|---|---|---|
| Can stop the user's task | No | Yes, rarely | Only the user's own limit | Yes |
| Protects against runaway spend | Through alerts, loop control (ADR-009) and model choice (ADR-004) | Yes, after the money is billed | Yes, hard and coarse | Yes |
| Complexity | Low | Low | None | High: needs a persistent ledger |
| Matches the operator's intent | **Yes** | Partly | Partly | No |

## Decision

Option A.

**Authority boundary:**

- **Accepted by the operator:** the policy.
- **Proposed:** threshold values and delivery surfaces.
- **Not commissioned:** implementation. **Current code still enforces the $0.05 per-turn cap** until a
  separately approved implementation changes it.

**The policy:**

- **Remove Optimus-imposed hard cost stops from the product path.**
  - Do not keep the $0.05 subtraction, a cost reserve or stop-on-cost machinery under another name.
  - Test, golden and evaluation runs keep their own dollar and call-count limits. Those are separate
    authorization contracts, not product cost stops.
- **Alert and warn** at thresholds the operator sets in the registry policy (ADR-004): per turn, per
  session and per day.
  - Alerts are delivered as text notices in the IDE. In the 2026-09-29 check, Zed showed only the context
    part of the usage meter, not its cost field.
  - **Per-day alerts need reconciled ledger support.** In-memory conversation state alone cannot
    establish daily totals.
- **An optional OpenRouter key limit is the user's own backstop,** not an Optimus limit.
- **Alerts use the actual cost reported by the provider** for the model that actually answered,
  including fallbacks.

**What stays, for its own reasons:**

- output-token limits;
- whole-request and capacity protection (ADR-003);
- cancellation;
- authorization and approval;
- bounded loop recovery (ADR-009).

**The policy does not forbid safety, context or provider failures.** A turn may still safely refuse or
fail while the user's task stays recoverable.

**Accounting:**

- Record the actual provider-reported costs, attributed by stage and request.
- Settle exactly once on every exit.
- Report totals truthfully: **unknown cost is not zero**, and incomplete totals are shown as incomplete.

## Consequences

- **Correction A retires, confirmed by Codex on 2026-09-30.** Claude and Codex had agreed, in the
  Context Engine direction rounds, to prove a hard all-in dollar bound for each summarizer call. That
  requirement existed only because of the per-turn budget.
  - Provider price filters may still help select eligible routes (ADR-004).
  - They are no longer a prerequisite for a total-dollar guarantee.
- **To reconcile: what happens at run time when a cost is unknown.** The Context Engine rounds agreed
  that an unknown summarizer cost suspends paid maintenance for the session. That rule was tied to the
  old budget. Its successor must be decided explicitly under alerts-only, not inherited unnoticed.
- **Governance: record the successor policy; do not rewrite history.**
  - The frozen Plan 9.96 implementation plan and old approvals are not rewritten.
  - The live HLD, LLD, Guardrails and requirement inventory are amended through a governed documentation
    change, drafted by Codex.
  - **`P9.85-FU-3` keeps sole custody of cross-run and session spend policy.** Its revised future
    acceptance (alert thresholds instead of a ceiling that fails closed) is recorded there. No parallel
    alerts item is created.
- **Loops become the main runaway risk.** With no cost stop, an agent looping unproductively is bounded
  by loop control, so ADR-009 is essential.
- **Revisit** if users need an Optimus-side hard spend cap as an opt-in feature.
