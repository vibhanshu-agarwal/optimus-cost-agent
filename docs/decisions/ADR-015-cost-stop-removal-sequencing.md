# ADR-015: Remove the product dollar stop after accounting and unknown-cost policy, without waiting for ADR-009

**Status:** Accepted-with-open-items. **Decision date:** 2026-10-01. **Decider:** operator, evidenced by the verbatim selected option and cross-checked question-tool answer. **Publication:** Repository-form record; editable in pre-merge review, frozen byte for byte on first merge to `main`.

**Relationship:** Completes [ADR-005](ADR-005-cost-alerts-not-limits.md)'s cost-stop-removal sequencing and clarifies the interim dependency on [ADR-009](ADR-009-loop-control-without-stopping-the-user.md). It does not accept ADR-009's Proposed detection/check-in/escalation mechanism or resolve the unknown-cost successor.

## Provenance

Source **S2**, indexed in the [decision log](README.md#rules-for-every-record): the operator's Claude Code session "PYTHON - [PLAN 12] Context Engine compaction", session `4162c45b-36f9-4cec-adb6-722ec3b28cb2`, exported on 2026-10-01 to `optimus-handoff\decisions-sources\2026-10-01-claude-session-context-engine-decisions-export.zip`; SHA-256 `8769D433CB869362305E91525273E8CA7A19EBC2807B1CA726F5DC9D4A81F5C2`. The archive is external raw provenance, never an operating, test or release dependency. The verbatim questions, options, selected labels and typed response reproduced below are the repository-visible decision evidence. Codex verified the archive checksum and the exact Q1–Q3 selections against the original question-tool records; Claude checked the export. Question/option wording is Claude's; selected labels and typed responses are the operator's. Agent relay summaries are context only.

**Question shown, verbatim:**

> Q3: When should the $0.05 per-turn cost stop be removed?

**Operator selected, verbatim:**

> After accounting (Recommended)

**Selected description shown, verbatim:**

> Remove it once cost accounting and the unknown-cost policy are ready. The existing loop limits (3 planning rounds, 30 minutes, 2 repeated failures) stay in place and can still stop a turn until the loop-control design (ADR-009) replaces them.

## Context and options

ADR-005 already accepts alerts rather than Optimus product cost stops. On the pinned source, the product still checks dollars in runner/planning/controller paths and prompts the model with remaining dollars. Independent bounds also exist: Agent planning defaults to 3 rounds, 30 minutes and repeated-failure limit 2; Chat has one call; the goal loop is not an ACP path.

| Exact option shown | Exact description shown |
|---|---|
| After accounting (Recommended) | Remove it once cost accounting and the unknown-cost policy are ready. The existing loop limits (3 planning rounds, 30 minutes, 2 repeated failures) stay in place and can still stop a turn until the loop-control design (ADR-009) replaces them. |
| Wait for loop control | Keep the $0.05 stop until ADR-009's check-in design is accepted and built. This is later, and the cost stop stays in place longer. |

The chosen sequencing removes the cost stop sooner than waiting for ADR-009 while retaining finite loop bounds and accounting/unknown-cost prerequisites. Existing loop-based stops remain an accepted interim trade-off. This does not select any new loop mechanism.

**Decision, paraphrased:** remove the $0.05 product stop and every equivalent monetary stop once exactly-once accounting and the accepted D6 unknown-cost/governed-document successor are ready. Do not wait for ADR-009's Proposed mechanism. Keep existing count/time/repeated-failure controls until the independently accepted future mechanism changes them. The current values are retained interim behavior, not new permanent loop defaults designed here.

Remove stop predicates, positive-dollar construction requirements and remaining-dollar planner prompts, not merely the visible $0.05 constant. A huge/infinite sentinel, hidden maintenance dollar reserve or subtraction is not removal. Retain actual spend accounting, alerts under accepted threshold policy, authorization, cancellation, safety and capacity/output protections. Independent test/golden/evaluation dollar and call caps remain separate authorization contracts.

## Consequences and unresolved work

Users can still reach the existing finite loop stop before task completion; the operator accepts that interim trade-off. ADR-009's desired bounded recovery/check-in behavior remains owed and Proposed, with its own scope/review. Do not claim its requirement fully delivered by retaining the old limits.

D6 still requires a concrete successor for unknown receipts, bounded retry/continuation behavior, alert values/day boundaries and governed budget-document succession. Unknown cost is not zero; retain known subtotals before and after unknown attempts and mark completeness truthfully. This record chooses no automatic retry or session-long maintenance suspension. Daily/cross-run reconciliation remains `P9.85-FU-3`; telemetry contract remains `P11.26-CAND-2-TELEMETRY-CONTRACT`.

The full [Plan 12.2 (reviewed source revision 5)](../superpowers/plans/2026-10-01-plan-12-2-context-engine-implementation.md) Task 11 implements this sequence only after separate execution acceptance. Codex drafts governed successors; Claude reviews/implements authorized scope; the operator controls filing, PR and merge. This record commissions no implementation, paid calls or delivery. The separate S2 docs-first selection authorizes filing; Package A does not release Task 11. First merge freezes it.
