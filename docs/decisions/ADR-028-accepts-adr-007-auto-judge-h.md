# ADR-028: Accepts ADR-007, with arm H as Auto mode's per-turn judge

**Number:** filed as ADR-027 on the Plan 12.4 branch and in its reviews (#395); renumbered to ADR-028 at merge, because
main's [ADR-027](ADR-027-idle-client-mcp-lifetime-contract.md) (#427) merged first. The approved `auto` overlay's
classifier evidence still names it ADR-027: that text is registry data inside the approved hash `f11dc3ab…`.

**Status:** Accepted. **Decision date:** 2026-10-26. **Decider:** the operator (verbatim below, source S13). The
evidence and the mechanism are Claude's; the review is Codex's (CLI round 62, posted on #395). **Publication:**
editable in pre-merge review, frozen byte for byte on first merge to `main`.

**Relationship:** Accepts [ADR-007](ADR-007-auto-mode-tier-routing.md)'s evaluation-led decision, **with the judge
that the Plan 12.4 pilot's pre-registered rule selected**. ADR-007 stays frozen and unchanged. Its proposed routing
behaviour is accepted as below.
- **Not a present safeguard:** ADR-007's "misroute recovered by ADR-009's bounded escalation". ADR-009's rung 2 is
  deferred to #397 and was not accepted by [ADR-024](ADR-024-accepts-adr-009-loop-control-phase-1-scope.md).
- **Unchanged:** the tiers stay fixed and the models stay configuration
  ([ADR-025](ADR-025-models-are-configuration-per-model-admission.md)).

## The operator's decision (2026-10-26, verbatim, source S13)

> "Approved: accept arm H (the hybrid: rules, then Jev) as Auto mode's judge per the pre-registered rule and Codex
> round 62, with its limitations. Draft round 2 (a steadier DSPy, the Jev + DSPy combinations, GPT-6 Luna Decisions, a
> fresh sealed test set) for Codex review; no paid calls yet."

## Context

ADR-007 proposed comparing rules, Jev, a cheap-tier model and a DSPy-optimised classifier on labelled data, then
routing each turn to a tier. Plan 12.4 v8 Design 3 ran that pilot under a decision rule fixed before any run. The
[evidence bundle](../sources/plan-12-4-auto-pilot/) holds the full results.

## Options considered

| | (a) Accept H, as the rule selects | (b) Accept B, Jev alone | (c) No winner yet: a larger test first |
|---|---|---|---|
| Follows the pre-registered rule | Yes | No: overrides the tie-break after seeing results | No: adds a precondition the rule does not have |
| Evidence | Passes both gates; beats A | Passes both gates; beats A; tied with H; the 2× winner | — |
| Host complexity | A rule score plus Jev | Jev only | — |
| Time to Phase B | Now | Now | After new labels and a fresh test split |
| Recommendation | **Claude and Codex (round 62); chosen** | Not recommended by Claude | Not recommended by Claude or Codex as a precondition; kept as the re-evaluation trigger (round 2) |

## Decision

**Auto mode's per-turn judge is arm H:**

1. The rules score the turn's frozen input contract. If they are confident (confidence ≥ 0.8; cut points 0.5 and
   4.5), their tier is the answer.
2. Otherwise Jev decides, through the Gateway's System One adapter, with the frozen `choice` question.
3. Any answer below confidence 0.95, and any abstention, failure, or missing or malformed confidence, routes one tier
   up.

The thresholds and the question are frozen in the pilot's `frozen.json`, filed in the evidence bundle with its
hashes.

## Evidence (the pilot's test split: 150 held-out requests × 3 repeats)

- **H:** penalty 0.547, under-route 4.7%, flip 4.7%, accuracy 56%, $0.022 per 1,000 classifications, p95 0.83 s.
  Against A: −0.207 [−0.387, −0.027].
- **Tied with B (Jev alone):** +0.013 [−0.020, +0.060]. H wins the tie on classifier cost. The rules decide 4 of 150
  turns, so H behaves as Jev with a free pre-filter.
- **Not selected:**
  - A, rules: under-route 12%;
  - C, Haiku prompt: flip 14.7%;
  - D, DSPy on Haiku: under-route 10% and flip 8.7%, despite 77% accuracy.
- **Codex round 62** recomputed every metric, winner and interval independently.

## Limitations accepted with this decision

- **A bounded pilot result:** H's rates are 4.7% against a 5% gate (Wilson upper bound 9.3%). The evidence does not
  establish population rates below 5%. At an under-route weight of 2×, the rule selects B instead.
- **No subset has a winner,** except the hand-written cases (C).
- **Author exposure:** the rule author saw the archived prompts, and wrote the hand-written cases, before writing the
  rules (A, and H's rule component). Test items were excluded from optimisation and threshold selection; they were
  not unseen by the author.
- **Labels:** kappa 0.513, with the higher label on disagreement.
- **The previous-tier signal** was almost untested (295 of 300 items had none).
- **Savings depend on the model list:** with today's `auto` list, Auto routes at $10.64 per 1,000 nominal turns,
  against $11.25 for always-complex and $9.71 for perfect routing.

## Consequences

- **Before the `auto` hash is approved,** `auto_overlay.yaml` gains:
  - Jev's complete reviewed entry, with its admission limitations: no finish status, router-attempt count or pipeline
    stages on the System One endpoint;
  - `classifier: [typesafe/jev-1.14]`;
  - a positive classifier reserve, which the validator requires and Jev does not use;
  - the 8,192 estimated-token bound.

  The full effective composition is then validated, and its new exact hash is approved.
- **Phase B (Tasks 4–5) builds H exactly:**
  - the rule score in the host;
  - the Jev adapter on the production path, with confidence validated to a finite value in [0, 1];
  - the route-up;
  - classifier-failure handling;
  - a per-turn routing record.

  Its live slices check one turn per routable tier. This acceptance does not show that production Auto works.
- **Re-evaluation (round 2, the operator's instruction above):** a new judge candidate re-runs the harness on a
  fresh, sealed test split under the same rule, never on this one. Candidates include a steadier DSPy, a Jev + DSPy
  combination, or GPT-6 Luna Decisions. Swapping one decision model for another of the same kind is then
  configuration plus that evidence.
