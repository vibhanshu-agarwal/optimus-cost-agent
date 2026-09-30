# ADR-008: A final review step, with Standard and Thorough modes

**Status:** Proposed. **Date:** 2026-09-30. **Decider:** the operator's idea. The design is Claude's
proposal, awaiting Codex and then the operator.

## Context

**Claude asked:** "Is 'review' something Auto picks when the user asks for a review, or an automatic step
where a stronger model checks a cheaper model's plan before you approve it?"

**Operator, verbatim (2026-09-30):**

> "2. No. keep it simple [Here I wanted to explore Jev' capabilities - can it detect that the code needs
> review - Given any task there should be a final review step but there may be certain exceptions if the
> task is trivial or cost is too much of an issue - perhaps we can have a mode for this - Standard vs
> Thorough or something such?]"

**Claude's interpretation, for the operator to confirm:**

- "Review" is not a routing class for Auto.
- It is a **final review step on every task.**
  - In one mode (**Thorough**) it always runs.
  - In the other (**Standard**) it is skipped when the task is trivial.
- Jev might decide "is this trivial?".

**Evidence on Jev for review triage** (evidence file, section F):

- **What exists:**
  - OpenRouter's cookbooks gate *commands*, not diffs. They approve at ≥0.9, block at ≤0.1, and send
    anything in between to a human.
  - A "verified cascade" uses Jev to check a cheaper model's answers.
- **What does not:** an official evaluation of Jev on diffs. Community "PR risk" tools exist, but they
  are unvalidated and score one file at a time because of the 32K limit.
- **Implication:** Jev is plausible for triage on bounded input, but its thresholds must be fitted on
  labelled Optimus changes.

## Where the step sits in Optimus's flow

Today the flow is: plan, then the user approves (`session/request_permission`), then apply.

- **P1: review before approval (proposed).**
  - It is a **plan and patch safety step.** The reviewer's findings are shown with the approval prompt,
    so the user decides with them in view.
  - Nothing is applied yet, so there is no rollback.
  - It does **not** validate how the change behaves once applied.
- **P2: review after applying.** It can run tests, but the change is already applied. It is better once
  test execution is part of the flow.
- **Chat answers.** Answers that change nothing (Chat mode) are reviewed before final delivery, where a
  review applies.

## Options considered

| | A: no review | B: always review | C: Standard (triage) and Thorough (always), user-selectable (proposed) | D: review only on request |
|---|---|---|---|---|
| Quality | Lowest | Highest | High, with a small triage-miss risk | User-dependent |
| Cost per task | None | Review-tier price on every task | Review only on non-trivial tasks in Standard | Low |
| Matches "a final review step, with exceptions" | No | Partly | **Yes** | No |
| Complexity | None | Low | Medium: triage plus a picker | Low |

## Decision (proposed)

- **Option C at placement P1.** Two review **depths**, chosen with an ACP config option in the IDE (for
  example `_review_depth`).
  - Review depth is separate from the Agent/Chat execution mode.
  - It follows the same full-set update rule as the other pickers (ADR-002).
- **Thorough:** always review.
- **Standard:** review unless the change is *confidently* low-impact.
  - **Small or docs-only does not mean trivial.** For example, changes to AGENTS.md, approval rules or
    security policy are high impact.
  - Only work that a stated rule classes as low-impact is exempt. Deterministic rules come first; Jev
    (`noul`: "does this change need review?") comes second, with thresholds fitted on labelled data.
  - Uncertain cases are reviewed.
- **The review is bound to the exact artifact.**
  - It records the hash of the plan or patch it reviewed.
  - **Reviewer findings never grant approval.**
  - If the plan is revised, the revision is re-hashed and must be approved as the exact revised artifact.
    A review of the earlier artifact is stale and invalid for the new one.
- **The reviewer comes from the review tier,** chosen among reviewer-eligible models, as the operator
  configured them (ADR-004).
  - Sonnet 5.5 is the default under the per-token rule, ahead of Kimi K3.
  - Proposed and not adopted: prefer a reviewer from a **different model family** than the author, so the
    two do not share blind spots. This remains subject to eligible-role pricing.
- **Review cost** is labelled as its own stage and alerted per ADR-005, never capped.

**Authority boundary:**

- **The operator's idea:** a final review step, with Standard and Thorough.
- **Proposed:** this mechanism.
- **Not commissioned:** implementation.

## Open items

1. The operator confirms the interpretation above, and which mode is the default.
2. The triviality rules and Jev's thresholds, on labelled data. A paid evaluation needs authority.
3. Whether the cross-family reviewer preference is adopted.

## Consequences

- **Easier:** cheap models become safer to rely on, because a stronger model checks their work.
- **Harder:**
  - one more model call and more latency on reviewed tasks;
  - a picker to maintain;
  - triage mistakes in Standard mode.
