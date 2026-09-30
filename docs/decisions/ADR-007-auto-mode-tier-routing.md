# ADR-007: Auto mode: classify each request into a tier

**Status:** Proposed. **Date:** 2026-09-30. **Decider:** the operator set the direction. The design is
Claude's proposal, awaiting Codex and an evaluation.

## Context

**Operator, verbatim (2026-09-30):**

> "So the "Auto" mode should classify into one of these three and assign from them, it is here I was
> thinking of Jev"

**Earlier decisions:**

- 2026-09-28, operator, a paraphrase recorded in the brainstorm diary: the user picks **Auto** (Optimus
  routes) or a model from the curated list.
- 2026-09-28: Claude runs a "Jev vs DSPy" routing experiment.
- The operator's original product description mentions "DSPy-based request-type classifiers".

**Evidence on Jev** (evidence file, section F):

- **Question types.** A `choice` question accepts up to 255 options and returns per-option probabilities
  and a confidence.
- **Cost and speed.** $0.042 per million input tokens, output free. Median latency about 175–217 ms.
- **Input.** Text only, 32K context on OpenRouter.
- **Calibration is disputed.**
  - TypeSafe says the probabilities are calibrated.
  - OpenRouter's own benchmark says confidence is "not a calibrated probability", though it ranks well:
    96.3% accuracy at confidence ≥0.99, and 29.6% below 0.5.
  - Answers vary by up to 0.08 across repeated calls.
- **Accuracy.** 81.0% on Banking77, against 84.4% for Opus 5.
- **`typesafe/jev-router`** is a complete router. It chooses among undocumented candidate models, and its
  price is variable.

## Options considered

| | A: rules and heuristics | B: Jev `choice` classifier | C: an ultra-cheap-tier model as classifier | D: DSPy-optimized classifier | E: `jev-router` |
|---|---|---|---|---|---|
| Cost per request | Free | About $0.00004 | About $0.0001 | Depends on the base model | The routed model's price |
| Latency | About 0 | About 0.2 s | About 1 s | Model-dependent | Built in |
| Confidence signal | No | Yes (ranks well; calibration disputed) | Weak | Depends | Opaque |
| Respects the curated registry (ADR-004) | Yes | Yes | Yes | Yes | **No**: its own candidates |
| Needs labelled data | To write the rules | To fit thresholds | To validate | To train and optimize | No |
| Fit with the original vision | | | | "DSPy request-type classifiers" | |

- **E fails ADR-004,** because it would route to models outside the curated list.
- **D is the operator's original idea.** It needs a training set, which is the same labelled data B and C
  need.

## Decision (proposed)

**The evaluation:**

- **Evaluate A (rules), B (Jev) and C (a cheap-tier classifier) on the same task distribution.** Add D if
  the labelled set supports training.
- **Keep tuning data and test data apart.** Training and threshold tuning use one split; accuracy is
  reported on a held-out split.
- **The classifier may abstain** on ambiguous input.

**Routing behaviour:**

- **Confidence bands:**
  - high confidence: route to the tier;
  - low confidence or abstention: route one tier *up*.

  This is proposed behaviour, not a calibrated safety claim. Jev's calibration is disputed (evidence
  file, section F).
- **Routes only to eligible models.** The router selects among role-eligible models on their pinned
  routes (ADR-004). A tier with no eligible model for the role is not routable.
- **Frozen per turn.** The chosen model and route are fixed for the turn. A user override from the IDE
  model picker (ADR-004) applies at the next turn boundary.
- **A misroute is recovered** by ADR-009's bounded escalation.
- **Input:** the current prompt plus a compact state (mode, the size of the recent change, file types),
  not the full history, because of the 32K limit.
- **Placement.** Routing is host-side (core Optimus), not part of the Context Engine.
  - The Jev call needs a Gateway adapter for `/api/v1/systemone`.
  - Its cost is recorded and attributed as its own stage.
- **No evaluation is authorized by this record.**

## Open items

1. The labelled prompt set: who builds it, how big, and which categories.
2. **Paid-call authority for the evaluation:** model, per-call cap and call count.
3. Whether "review" is a routing class at all. The operator said "keep it simple"; ADR-008 treats review
   as a review-depth setting instead.

## Consequences

- **Easier:** cost stays low without the user choosing a model each time.
- **Harder:**
  - classifier errors cost either quality (routed too low) or money (routed too high);
  - ADR-009 escalation and the evaluation keep those errors bounded and measured.
