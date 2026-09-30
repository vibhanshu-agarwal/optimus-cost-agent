# ADR-009: Loop control that is never open-ended and never silently stops the user

**Status:** Proposed. **Date:** 2026-09-30. **Decider:** the operator set the requirement. The
architecture is Claude's proposal, awaiting Codex and then the operator.

## Context

**Operator, verbatim (2026-09-30):**

> "2. Option A. We need anti-hallucination controls such as loop detection and budget- this was one of
> the requirements I had laid down early on but seems to be lost? I don't want the user to not be able to
> complete a task because of our cost controls.No limit from our end - our job is alerts and warnings
> based on decided thresholds"

> "4. This too was determined by the agents - I don't want any cost control strategy to actually stop a
> user from completing his work. Can Jev or any other techniques help ? Some models go into aggressive
> loop mode when they are struggling, this should not be open-ended - your architect perspective needed
> here"

**The original requirement** is the operator's product description: "...further cutting cost by reducing
hallucinations, curbing unnecessary agent loops...". It survived only as a "cost lever" in the Plan 12
brainstorm diary, which is outside the repository.

**What exists on `main`.** Every control is a count, and every one stops the turn:

- **`max_planning_turns = 3`** (`agent/models.py:99`, `agent/planning_loop.py:89`).
  - Added by commit `7b572f8` on 2026-07-12 (Plan 9.85), which calls it "a chosen Phase 1 default
    consistent with bounded-loop principles".
  - **Agents chose it**, not the operator.
- **`repeated_failure_limit = 2`** in the planning loop (`agent/planning_loop.py:99`), with signatures for:
  - repeated read requests;
  - `UNPARSEABLE` responses;
  - repeated MCP operations.

  Two identical failures in a row end the turn, for example with `PLANNING_REPEATED_READ_REQUEST`. The
  *detection* is useful; the *response* conflicts with the operator's rule.
- **The goal loop** (5 iterations, 30 minutes) is unreachable from ACP, which never sets
  `completion_condition`.
- **The $0.05 per-turn stop**, which ADR-005 removes from the product path.

**Why this matters now.** ADR-005 removes cost stops, so an unproductive loop is bounded only by loop
control. Among the listed models, the survey found the most independent loop reports for the cheap-tier
candidate GLM 5.3 Flash, for example 220+ identical tool calls over about 25 minutes (evidence file,
section D). These are anecdotal incident reports, not failure rates.

**Industry practice among the ten surveyed agents.** Evidence file section E has the full table and
sources.

- **Main signal:** an identical consecutive tool call, at 3–5 repetitions. Error streaks are counted
  separately, usually at 3.
- **Two stages:** first inject a corrective message ("try a different approach"), then pause.
  - **Interactive tools ask the user** with explicit options: Cline ("Try a different approach / Stop
    this run"), Copilot ("Continue to iterate?", which raises the limit 1.5×), Goose ("Would you like me
    to continue?"), and opencode (once / always / reject).
  - Headless modes stop.
- **Coverage gaps:** among the surveyed agents, only OpenHands documents A–B alternation detection.
  Gemini CLI adds an LLM judge, confirmed by a second model at ≥0.9 confidence.
- **Research:**
  - Combining structural and semantic cycle detection reached F1 0.72, against 0.08 and 0.28 for each
    alone.
  - Cheap per-step monitors caught 71% of failures at a 5% false-alarm rate.
  - Rolling back and re-running flagged runs raised task success from 52% to 73%.
- **Escalation helped on one published workload.** Together's cascade, Flash first then GLM 5.3 when
  tests fail, solved 80.9% of DeepSWE tasks at $1.70 per task (section D). That is evidence for trying
  it, not a guarantee for Optimus.

## Requirements, as executable properties

1. **Never open-ended.** Unproductive work always reaches a decision point within a bounded number of
   iterations.
2. **Never a silent stop for cost reasons.** In an interactive session, only the user ends a task on cost
   or loop grounds. Optimus may pause and ask, but it does not decide alone.
   - This does **not** forbid a turn from safely refusing or failing for safety, context-capacity or
     provider reasons. The task stays recoverable (ADR-005).
3. **Pausing costs nothing.** No model call runs while Optimus waits for the user.
4. **A struggling model gets help before the user is asked:** a corrective hint, then a stronger
   *eligible* model.

## Options considered

| | A: count caps with a hard stop (today) | B: higher caps with a hard stop | C: detect, nudge, then ask the user | D: detect, nudge, escalate a tier, then ask (proposed) | E: model-judged progress only (Jev or an LLM judge) |
|---|---|---|---|---|---|
| Stops the user's task | Yes | Yes, later | No, the user decides | No, the user decides | Depends |
| Bounded | Yes | Yes | Yes | Yes | Only if thresholds are trusted |
| Catches a struggling cheap model's loop | Stops it | Stops it later | Asks the user | **Often fixes it** by escalating | Maybe |
| Semantic loops (not identical calls) | No | No | Partly | Partly, plus Jev as a secondary check | Yes, with false positives |
| Cost | Lowest | Low | Low | Higher per escalated step; alerts per ADR-005 | Small (Jev) to medium (LLM judge) |
| Complexity | Exists | Trivial | Medium | Medium-high: needs ADR-004/007 | Medium; needs labelled data |
| Evidence | Agent-chosen default | none | Cline, OpenHands, Gemini, Copilot, Goose, opencode | Together cascade; industry nudge-then-ask | Gemini judge; Copilot Advanced Autopilot; disputed Jev calibration |

## Decision (proposed): Option D

Deterministic signals are primary; Jev is a secondary check.

**1. Signals** (per turn; thresholds start at the industry norm and are tuned by measurement):

- the same normalized action (directive or tool call with the same arguments) 3 times in a row;
- the same failure signature 3 times, reusing today's signatures;
- A–B alternation over 3 cycles;
- no progress across N iterations;
- repeated unparseable responses.

**What counts as progress.** Progress includes new evidence and read-only analysis, not only workspace
changes. Legitimate repetition is not a cycle: polling a long-running process, or re-reading a file that
has changed. Each signal needs negative tests proving that normal progress never triggers it.

**2. Secondary signal: Jev.** A yes/no question, "Is the agent making progress?", asked over a compact
JSON progress summary (under 32K tokens), only after N iterations with no deterministic progress marker.

- It is never the sole reason to pause, until thresholds have been fitted on Optimus's own labelled
  trajectories. Its calibration is disputed (evidence file, section F).
- **A Jev judgement never grants tool, mutation or route permission.**

**3. A bounded recovery episode.** One episode starts at the first detection. It **always ends at a user
check-in** (rung 3) and does not silently reset when the model changes. Each rung is taken at most once
per episode.

1. **Nudge.** Tell the model what repeated and what the last error was, and ask it to try a different
   approach. There is no separate classifier call, but the next model request and its added tokens are
   billable.
2. **Escalate one step on an explicit escalation graph**, in Auto mode only, with a live notice and a
   cost alert (ADR-005).
   - The graph is declared in the registry (ADR-004). Under the operator's configuration of
     2026-09-30, the example edge is the medium-task default to the complex-task and escalation model:
     Muse Spark 1.3 Contributor to Gemini 3.8 Flash, with GLM 5.3 as Gemini's fallback.
   - Every target must be **eligible for the implementer role**. Review-tier models are not automatically
     qualified implementers.
   - If there is no eligible next step, or the user fixed a model, skip to rung 3 and offer the choice
     there.
3. **Pause and ask** through ACP `session/request_permission`, with a summary of what was tried. The
   options are Continue, Use a stronger eligible model (when one exists) and Stop.
   - **"Continue" grants only one more bounded planning allowance.** It is not mutation or tool approval,
     not route approval, and not unlimited retries. Every mutation still needs its own approval.
   - Nothing runs while Optimus waits.

**Cancellation.** It is honoured at every rung and while a permission request is pending, so any new loop
path must avoid the gap recorded in `P12.1-FU-2`.

**No interactive client.** If the client cannot present the check-in, the turn ends with a recoverable
explanation rather than spinning.

**4. Count caps become check-ins, not stops.** When the iteration allowance runs out, the agent asks to
continue, as Copilot and Goose do. The default allowance is set from measurement. Today's
`repeated_failure_limit` hard stop is replaced by the recovery episode.

**5. Headless runs keep explicit hard limits.** Tests, golden runs and any non-interactive caller have no
one to ask.

**Authority boundary:**

- **Accepted by the operator:** the requirement. Loops are never open-ended, and a cost control never
  stops the user's work.
- **Proposed:** this mechanism.
- **Not commissioned:** implementation.

## Consequences

- **Easier:** tasks finish more often; the user stays in control. As the operator put it, loop control is
  a safety net for exceptional situations, "should not be needed as an everyday occurrence". Defaults are
  chosen for everyday reliability (ADR-004), not rescued by this mechanism.
- **Harder:**
  - escalation needs the registry (ADR-004) and Auto routing (ADR-007);
  - each signal needs tests, including negative tests that normal progress never triggers a pause;
  - turns can last longer, bounded by user consent.
- **Existing owners to check before filing anything:**
  - `P12.1-FU-2`, "goal-loop iterations bypass turn cancellation". Any new loop path must honour turn
    cancellation.
  - `P11.25-FU-2`, structured stop reasons.

## Open items

1. **Thresholds and the default iteration allowance**, to be measured.
2. **How Zed renders custom permission option names** for the three choices. This is a free check.
3. **Jev evaluation on Optimus trajectories.** Paid calls need operator authority.
4. **Whether rung 2 (automatic escalation) is on by default,** or needs the user's consent each time. It
   costs more per step, so the operator decides.
