# Correction note: Plan 11.25 producer instrumentation was not established on the pinned production source

Date: 2026-10-01. Codex architecture/review. Repository-visible factual correction, not an executable amendment plan. The complete [Plan 12.2 implementation plan](../plans/2026-10-01-plan-12-2-context-engine-implementation.md) contains the repair contract. Archived Plan 11.25 and sealed evidence remain byte-identical. The sole backlog owns current repair state.

## Discrepancy

Archived [Plan 11.25](../plans/archive/2026-08-21-plan-11-25-multi-turn-conversation-implementation.md), Task 6, marks these steps complete:

- Step 3: directive lifecycle tests covering Planning READ, approved READ, implicit pre-WRITE read, WRITE and TEST, asserting lease denial prevents producer invocation and terminal states are published.
- Step 8: instrument producers at their real boundaries, registering known directives and publishing actual results/exceptions.

The source tree pinned to merged `83fafb9606fb81992508554aa302d3b62c603236` does not establish those claims for the three runner executors:

| Source boundary | Observed behavior |
|---|---|
| `agent/runner.py:822,849,875` | READ, WRITE and TEST executors discard operation_control; no producer lease/terminal instrumentation in these bodies |
| `agent/runner.py:706,723,727` | Approved READ/WRITE/TEST calls omit the control received by _run_approved_from_store |
| `acp/spec.py:1039` | Conversation commit hard-codes NONE regardless of actual WRITE/TEST effects |
| `acp/lifecycle.py:215–263,508–515` | Registry/start/completion and effect formula exist, but require actual producer facts |

Gateway and plan-persistence registrations do not fill the WRITE/TEST gap. Other agent records/tool-call summaries may indicate work happened; they do not supply the authoritative effect/cancellation protocol this claim requires. This note identifies a current-source versus checked-step discrepancy; it does not establish why it occurred or claim every unrelated Plan 11.25 component is missing. The separate ranged READ_MORE path is intentionally outside Q1 and contributes no effect. Archived Step 8 explicitly says “Planning iteration remains outside registered lifecycle and uses only the existing halt mechanism”, whereas the earlier checked test coverage lists Planning READ. Treat that tension as ambiguity in the archived plan, not a second demonstrated overclaim or a new orphan repair item. It does not weaken the concrete runner WRITE/TEST discrepancy above.

## Current disposition

The operator chose Q1 as recorded verbatim in [ADR-013](../../decisions/ADR-013-plan12-effect-producer-repair.md) with [S2 provenance](../../decisions/README.md#rules-for-every-record): Plan 12 owns this narrow repair as its first code task, not a separate runtime-hardening item. The host must block not-yet-started approved changes/tests on cancellation and commit actual effect state. lifecycle.py is required scope: cancellation and denied starts currently suppress without recalculating; completed WRITE plus suppressed TEST must be PARTIAL. Disconnect already recalculates and remains unchanged in that respect. The later S2 selections authorize Package A (Tasks 0, 2 and 3) after docs-first merge. Package-A delivery boundaries remain the operator’s later decision. Registration/start/terminal and consistent projection require executable proof; copying the current NONE placeholder is not completion.

Until that proof exists on the actual production base, do not describe these runner producer claims as implemented or technically cleared. The sandbox has the same reported gap and is not changed by this drafting work; it remains uncorrected until a separately authorized synchronization. Plan 12's PR description must disclose its runtime-hardening scope and sandbox status.

## Repository custody and authority

Mutable links from the decision index, docs index and sole backlog point to this note and Plan 12.2. The existing Plan 11.25 row remains a historical delivery record, with this discrepancy linked explicitly; its archived plan and sealed approvals/evidence are not edited or re-certified. Plan 12 owns the narrow repair under ADR-013; no separate runtime-hardening item or second pool is created. Separate goal-loop and planning READ_MORE owners/exclusions remain intact.

The operator selected docs-first filing and Package A execution, with no product code before that docs PR merges. No product-code change, repaired-producer proof, paid call, sandbox synchronization or package-A delivery is established by filing this factual note. Production behavior remains unrepaired until Task 2 lands with its real-boundary evidence.
