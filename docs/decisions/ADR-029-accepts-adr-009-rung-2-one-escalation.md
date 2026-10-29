# ADR-029: Accepts ADR-009's rung 2: an Auto turn moves once to the escalation model before its check-in

**Status:** Accepted. **Decision date:** 2026-10-27. **Decider:** the operator (verbatim below, source S16). The
mechanism is Claude's; the review is Codex's (CLI round 75 and its follow-ups, posted on #397). **Publication:**
editable in pre-merge review, frozen byte for byte on first merge to `main`.

**Relationship:**
- **Accepts** [ADR-009](ADR-009-loop-control-without-stopping-the-user.md)'s rung 2, "escalate one step on an explicit
  escalation graph", **as scoped here**, and settles its open item 4: whether rung 2 is on by default.
  [ADR-024](ADR-024-accepts-adr-009-loop-control-phase-1-scope.md) left rung 2 out of Phase 1 ("escalation after
  Auto"). ADR-009 and ADR-024 stay frozen and unchanged.
- **Uses the exception [ADR-007](ADR-007-auto-mode-tier-routing.md) anticipates.** Under "Frozen per turn", ADR-007
  says "The chosen model and route are fixed for the turn" (line 70) and "A misroute is recovered by ADR-009's bounded
  escalation" (line 72). An escalated turn changes model once, mid-turn. Implementation, not ADR-007's wording: Plan
  12.4 binds a turn's approved application to the turn's model, so an escalated turn's application runs on the model it
  moved to.
- **Fulfils** [ADR-028](ADR-028-accepts-adr-007-auto-judge-h.md)'s note that ADR-007's "misroute recovered by
  ADR-009's bounded escalation" was not a present safeguard. It now is, in the bounded form below.
- **Unchanged:** the tiers stay fixed and the models stay configuration
  ([ADR-025](ADR-025-models-are-configuration-per-model-admission.md)); cost stays alerts, not limits
  ([ADR-005](ADR-005-cost-alerts-not-limits.md)).

## The operator's decision (2026-10-27, verbatim, source S16)

Asked through AskUserQuestion (2026-10-27 18:39 UTC): "ADR-009 leaves one decision to you: when an Auto turn is
still looping after its nudge, should Optimus move it to the stronger model automatically?" The operator chose:

> "(a) Automatic (Recommended)"

**Priority, verbatim (2026-10-27, source S16):** "#397 - can we get this done first? Then test auto live inside Zed".

## Options for ADR-009 open item 4

| Option | What happens | Trade-off | Recommendation |
|---|---|---|---|
| (a) Automatic in Auto mode | It escalates without asking, at most once per turn, with a live notice and price line; the check-in follows | Up to Continue's allowance (3 steps) runs on the dearer model without a prompt. The cost is bounded by one move per turn and signalled by the notice's price line, an alert, not a limit (ADR-005) | Claude, and Codex (round 75, finding 12) |
| (b) Ask first | The check-in gains a third option, "Use a stronger model" | No dearer step without the user's consent, at the cost of one more prompt for each struggling turn | Not recommended |
| (c) Automatic, plus a setting to turn it off | (a) plus an environment switch | (a)'s cost, but automatic escalation can be disabled; adds one setting to document and test | Not recommended by Claude or Codex: a setting nobody asked for, and Auto itself is opt-in |

The operator was shown each option with a description in the same question (S16, the `2026-10-27T18:38:35.950Z`
turn). For (b) it read "nothing escalates without that click. One more prompt for each struggling turn."

## Decision, paraphrased

In an interactive Auto session, once a recovery episode's nudge has not helped, the rest of the turn moves **once**
to a stronger eligible model. The episode still ends at the user's Continue/Stop check-in.

"Not helped" means any of:
- a second detection;
- the allowance ending with no plan and no refusal;
- a REFUSE settled after the nudge, as the weak model gives up while it loops.

On a grant, that refusal is set aside for the stronger model. With no grant, it waits at the check-in as before. A
first-occurrence refusal outside an episode stays a refusal, and a final plan after the nudge goes straight to the
check-in.

**The graph rule (agent detail, reviewed by Codex):**
- An Auto implementer may move once to the configured escalation target: the `escalation` role's first routable model
  in the trusted registry.
- ADR-009 requires the target to be eligible for the implementer role. `escalation` is one of `IMPLEMENTER_ROLES`
  (`src/optimus_model_policy/registry.py`), so registry validation holds each of its models to the implementer checks,
  native tools and the planning grammar (`src/optimus_model_policy/validation.py`).
- The role's later entries only substitute for stopped earlier ones; they are never further steps.
- A turn already running the target, or one whose target has less usable input, has no step and goes straight to
  the check-in, which says so.
- No model is named in code.

**Bounds:**
- at most one move per episode and per turn;
- the stronger model gets Continue's allowance (3 steps, a fresh 30 minutes);
- a halt wins at every point;
- nothing runs while the user is asked.

Fixed-model launches, headless callers and `OPTIMUS_LOOP_RECOVERY=headless` keep Phase 1 unchanged.

**The notice:** the move is announced with a live line that gives the price change from the registry. It is
informational (ADR-005): its delivery is recorded, and it never gates the move. A Contributor disclosure stays
mandatory for each request. The mechanism, its tests and its live and Zed evidence are specified in the #397 plan (r7,
`optimus-handoff/sandbox-review-kit/p397-escalation/plan.md`) and the PR that implements it.

## Evidence at acceptance, and what is still owed

The runs, their heads, results and log hashes, and the reviews are in the
[#397 validation record](../sources/p397-escalation/validation-record.md).

- **Tests:**
  - unit and end-to-end tests of the trigger, the graph rule, the bounds, Continue, the approved application and
    the records;
  - Windows full suite with coverage on `ca66625` (2026-10-28): 10,417 passed, 0 failed;
  - Windows full suite with coverage on `07e7ed2` (2026-10-29): 10,462 passed and 2 failed, both inventory checks
    (a platform tag and the logging-surface manifest);
  - after it, with no further full suite: the retry-report fixes `bfee317` and `5630fe9` (852 Gateway and inventory
    tests; a five-part revert check) and the inventory fix `6ca4bee` (195 tests; no product change);
  - **owed by the PR's gates:** Linux CI on the PR's final head.
- **Scripted live evidence,** on a scripted provider under plan r6's evidence exception S1, which the operator
  accepted by running its approval:
  - acpx slice A1′ on `ca66625` (2026-10-28): the easy model was stuck, moved once to the escalation model, and the
    check-in was answered Stop;
  - the Zed UI scenarios on `ca66625` (2026-10-29), all passing in real Zed against the records. U2 was Stop at the
    check-in; U5 a cancel while the check-in was pending; U4 no stronger model; and U3 Continue, then the separate
    plan approval.
- **Real-model Zed evidence (2026-10-29),** each case with its Auto line and matching routing records:
  - U1 and Z1 (easy) on `3272ce0`: completed.
  - Z2 on `3272ce0`: routed one tier up from medium for low confidence, as the case requires. The turn then lost a
    reply the provider had billed (USD 0.0401) to the agent's 30 s Gateway timeout, and stopped as
    `PLANNING_GATEWAY_COST_UNKNOWN`. Fixed in `07e7ed2`; Z2 was not re-run.
  - Z3 (complex) on `07e7ed2`: a 51 s planning reply arrived with its cost known, which the 30 s timeout would have
    lost. The model then refused the task, which is model behaviour.
- **Still owed in #397:** a real model getting stuck enough to escalate (plan r6, S3). The scripted evidence stands in
  until then.

## Authority boundary

- **Accepted by the operator:** option (a), as quoted, and the priority.
- **Agent detail, reviewed by Codex:** the trigger, the graph rule, the bounds, the attachment contract, the notice
  text and the records.
- **Not decided here:**
  - cross-turn fingerprints, persisted episode accounting and alert thresholds (#396);
  - the ACP model picker and selection filters (#398);
  - D4, provider 429/5xx (#396).
- This record grants no merge, paid call or GitHub write.
