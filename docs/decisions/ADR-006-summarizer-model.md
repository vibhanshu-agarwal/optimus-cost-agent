# ADR-006: The summarizer comes from the ultra-cheap tier

**Status:** Accepted-with-open-items. **Date:** 2026-09-30. **Decider:** the operator.

## Context

**Operator, verbatim (2026-09-30):**

> "3. Previously, the choice was Claude Haiku - but now there are many options. I am thinking GPT-6-Luna
> but open to other models if they provide same capability at a lower price + Jev is also under
> consideration - that means 0 cost if that works. I am expecting more architectural input from you and
> Codex as Senior Architects"

> "Ultra - Cheap tier - Summarizer + Easy tasks (GPT-6-Luna + Qwen 3.7 flash)"; "3. Already mentioned
> above"

**Facts:**

- **Jev cannot summarize.** Jev (TypeSafe System One) returns only typed answers: yes/no, a choice or a
  score.
  - It is cheap, about $0.042 per million input tokens with output free (diary, 2026-09-28), but not
    zero.
  - `typesafe/jev-router` charges the price of whichever model it picks.
- **Cost of one compaction** (50K tokens in, 2K out; OpenRouter prices, 2026-09-30):

  | Model | Cost |
  |---|---|
  | Qwen 3.7 Flash | about $0.002 |
  | Luna | about $0.006 |
  | Haiku 4.5 | about $0.06 |

- **Payback.** Compacting 50K tokens to about 3K saves about 47K tokens on every later call, so a
  compaction pays for itself within one or two calls (ignoring cache discounts).
- **Industry** (research sweep, 2026-09-30; see the
  [evidence file](2026-09-30-industry-context-cost-and-model-evidence.md)):
  - Most agents summarize with the session's own model.
  - Aider tries a cheaper "weak model" first.
  - Cline and OpenHands allow a configured summarizer; OpenHands tags its cost separately.

## Options considered

| | A: same model as the agent | B: a dedicated ultra-cheap tier (chosen) | C: Jev |
|---|---|---|---|
| Cost | As expensive as the agent model | Fractions of a cent per compaction | n/a |
| Quality | Consistent with the agent | Must be proven by a gate | **Cannot produce text** |
| Cache reuse | Yes (shared prefix) | No | n/a |
| Operational | One model | One more model | n/a |

**Reasoning.** Between cheap models the price difference per compaction is a fraction of a cent. The real
cost of a bad summary is a failed or wrong later turn.

- **Eligibility is set by operator configuration** (ADR-004, decision 3). The operator decided "tests are
  not needed just to check tasks".
- **Among eligible models, the operator's accepted rule applies:** the cheapest per token (ADR-004,
  "per token among eligible models").

Jev's architectural role is selection rather than rewriting (ADR-007 and ADR-009).

## Decision

**Authority boundary:**

- **Accepted by the operator:**
  - the tier;
  - eligibility by configuration;
  - **the summary quality check is kept.** The operator said on 2026-09-30: "keep the summarizer check".
- **Proposed:** the check's exact fixture and pass criterion.
- **Not commissioned:** implementation and the paid runs.

**The decision:**

- **Tier.** The summarizer role is taken from the ultra-cheap tier of the registry (ADR-004).
- **Eligibility: operator configuration plus one required check.**
  - The structural validator bars any model lacking a capability that the summary format requires, such
    as structured output.
  - **A model must also pass the summary quality check** before it can be marked eligible for the
    summarizer role. The check is a coding conversation with an early constraint and a late correction
    (the calculator scenario), and the summary must keep both.
  - The pass is recorded in the registry with model, route, reasoning setting, fixture version and date.
  - **This is the one deliberate exception** to ADR-004's "tests are not needed just to check tasks". The
    operator chose it because a summary that silently drops a constraint is harder to notice than a
    coding failure, and no coding benchmark measures it.
- **Selection.** The cheapest per token among eligible models.
  - In price order, these are Qwen 3.7 Flash, then Luna.
  - Qwen 3.7 Flash lists no structured-output support. If the summary format needs a strict schema, the
    validator bars Qwen from this role, and Luna is used.
- **No unqualified fallback.** If no eligible summarizer is available, the engine uses the non-latching
  fallback agreed in the Context Engine direction: full history if it fits the floor, otherwise refuse
  the turn in a way the user can recover from. It never silently uses an unqualified model.
- **Muse Spark 1.3 Contributor** is in the cheap tier, not the summarizer's tier. If the operator ever
  makes it eligible to summarize, its warning applies to summarizer requests too (ADR-004, decision 7).
- **Configuration.** The summarizer is a registry setting, never hard-coded.

## Open items

1. **The check's exact fixture and pass criterion,** to be specified in the design spec. It is small:
   one scenario per candidate model.
2. **Paid-call authority** for running the check on each candidate (Qwen 3.7 Flash, Luna): model,
   per-call cap and call count.
3. **The operator's question was answered,** verbatim (2026-09-30): "keep the summarizer check".

## Consequences

- **Summarizer cost** is accounted exactly once and labelled separately (ADR-005), with alerts only.
- **Revisit** if the check shows the ultra-cheap tier loses facts. Then evaluate the same-model option for
  the summarizer role.
