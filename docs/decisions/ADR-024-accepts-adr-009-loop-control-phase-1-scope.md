# ADR-024: Accepts ADR-009 as scoped for loop control Phase 1: a detector, one nudge, a check-in

**Status:** Accepted. **Decision date:** 2026-10-23. **Decider:** the operator (verbatim below, source S10). The
mechanism details are Claude's, reviewed by Codex through four rounds of the Plan 12.3 plan. **Publication:**
editable in pre-merge review, frozen byte for byte on first merge to `main`.

**Relationship:** Accepts [ADR-009](ADR-009-loop-control-without-stopping-the-user.md)'s Option D **as scoped
here**: its rung 2 (escalation to a stronger model) and its Jev secondary signal are not accepted now. ADR-009
stays frozen and unchanged. This record ends the interim that
[ADR-015](ADR-015-cost-stop-removal-sequencing.md) accepted, in which the existing loop limits "can still stop a
turn until the loop-control design (ADR-009) replaces them", for interactive sessions only.

## Provenance

Source **S10**, indexed in the [decision log](README.md#rules-for-every-record): the app's export of the Claude
session for the Plan 12 next-item thread, session `817f38ae-e1fb-432b-a2e9-d7827bd97aa3`, at
`optimus-handoff\decisions-sources\2026-10-23-claude-session-plan12-export.zip`; SHA-256
`B3B52E66E3E3AFA99034125AD690914B7F03610C41F5BDC63F27331EA1FAC2E1`. The archive is external raw provenance, never
an operating, test or release dependency.

**The options shown** were Claude's reconciled scope, `optimus-handoff\plan-12-discovery\2026-10-23-loop-control-reconciled-scope.md`
(SHA-256 `2f57775fefd2989048cd0f39c5d08a3e489c450bd977b83e31023257a5d2f505`), section "Decisions for the operator".

**Operator, verbatim (2026-10-23):**

> "Approved: D1 accept ADR-009 as scoped (detector, one nudge, check-in; escalation after Auto), D2 thresholds 3 / one nudge / Continue +3, D3 retire the legacy goal-loop path if no supported client uses it. Draft the Phase 1 plan (no number) for Codex CLI review."

**Priority, verbatim (2026-10-23):** "P1(a), A1, A2, A3, A5 are approved". P1(a) makes loop control Plan 12.3 (#394).

## Options and trade-offs

| Decision | Options weighed | Chosen, and why |
|---|---|---|
| D1, the mechanism | ADR-009's Options A–E; within D, all three rungs now, or the detector, nudge and check-in now with escalation later | **Detector, one nudge, check-in; escalation after Auto (Plan 12.4).** Escalation needs Auto's routing and an eligible-implementer graph (ADR-004, ADR-007), which do not exist yet. The check-in alone already removes the interactive hard stops |
| D2, the thresholds | Keep today's limit of 2; move to the surveyed norm of 3; set them by measurement first | **3 for repeats, cycles, no progress and repeated errors; one nudge per episode; Continue grants +3 planning steps.** All are configurable. 3 is the industry norm in ADR-009's survey; measurement against escaped loops and interrupted work stays owed (#396) |
| D3, the legacy goal loop (`optimus.agent.run` with `completion_condition`, #270) | Fix its cancellation and accounting gaps; retire it | **Retire it if no supported client uses it.** Zed does not, and the framed transport that reaches it is refused at startup under the enforced registry. Retiring is less work than fixing a second loop |
| D4, provider 429/5xx | A hard stop now; a "retry later?" check-in | **Not decided by the operator.** It was recommended but not part of the approval, so today's hard stop stays by default (#396) |

## Decision, paraphrased

In an interactive ACP session, a repetition, cycle, no-progress or repeated-error detection, or the end of the
planning allowance (3 steps or 30 minutes), no longer ends the turn. The model first gets one corrective nudge,
then the user gets a Continue/Stop check-in. Continue grants only a fresh planning allowance (+3 steps, a fresh 30
minutes), never a WRITE or TEST approval. Headless callers (golden, evaluation, Stage C and other non-ACP callers)
keep today's hard caps. First-occurrence typed failures (Gateway or provider faults, read errors, guard blocks)
stay stops. The mechanism and its tests are specified in the Plan 12.3 plan,
`docs/superpowers/plans/2026-10-23-plan-12-3-loop-control-phase-1_v5.md`.

## Authority boundary

- **Accepted by the operator:** D1–D3 as quoted, and the priority P1(a).
- **Agent detail, reviewed by Codex:** the transition table, the reason codes, the TEST deadline and containment,
  and the defaults beyond D2 (the 15-minute TEST deadline and the 10-second teardown bound).
- **Not decided here:** D4, escalation (#397), cross-turn fingerprints, alert thresholds and persisted episode
  accounting (#396).
- **Implementation** was released separately by the operator on 2026-10-23 for Plan 12.3. This record grants no
  merge, paid call or GitHub write.
