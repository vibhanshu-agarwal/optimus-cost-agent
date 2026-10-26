# Exception routes accept one unflagged guardrail stage (#400, option b1)

**Status:** Accepted. **Date:** 2026-10-26 (Asia/Calcutta). **Deciders:** the operator (the policy and its residual
risk, by the direct approval quoted below); recommended by Codex (CLI review round 58); drafted and filed by Claude.
Identifier: the decisions index ended at ADR-024 on main `eb5e371`, and 025 is held by the unmerged Plan 12.4
branch's ADR-025, so this record takes 026. No frozen predecessor is edited.

## Direct authority

In the Claude session for the Plan 12.4 Auto thread (source S12 in the [decisions index](README.md)), the operator
answered the question "How should #400's guardrail stage be handled?" with:

> Approved: #400 option b1 with Codex round 58's conditions, accepting the residual risk (an unflagged stage does not
> prove unchanged content or data handling). Deliver main-first as a #400 PR with the Plan 12.4 successor and decision
> record; post the round-58 review to #400.

Codex's round-58 review is posted verbatim on #400 (comment 6408119815).

## Context

- **#400 (R-15):** OpenRouter's router sometimes reports a `guardrail` pipeline stage on Haiku 5.5 replies. The
  experimental (exception) route refused every pipeline stage with a billed 422 `EMPIRICAL_ROUTER_PIPELINE`, and
  stopped its route for the launch.
- **#400's option D (PR #402)** started persisting each guardrail stage's closed facts and changed no policy.
- **The first live capture with facts** was the Plan 12.4 pilot's smoke test on 2026-10-26:
  - `router_pipeline: ["guardrail"]`;
  - facts `{flagged: false, detected: missing, decision: missing, action: missing, guardrail_scope: missing,
    verdict_conflict: false}`;
  - one completed attempt, provider Anthropic.
  - The stop then refused 28 later Haiku calls unsent.
- **The account side is ruled out:** the operator's OpenRouter account has no guardrails configured.
- **OpenRouter's router-metadata guide:** a blocked request is a 403 with `action: "blocked"`.

## Options considered

| Option | For | Against |
|---|---|---|
| **(b1) Accept exactly one unflagged stage with no reported verdict.** Chosen | Keeps every other reply check, and refuses any reported flag, detection, decision, action, conflict or scope. One shared predicate over the existing closed facts, with no new configuration | It is a relaxation, not proof: an unflagged stage does not show the content unchanged, or how the guardrail handled the data |
| (b1+) b1, plus the stage's name kept as a closed literal | Would help establish the stage's origin over time | Widens the change, and the rule does not depend on the name. Optional diagnostics only |
| (b2) Accept any unflagged stage, whatever its decision or action | Fewer refusals | Would pass a stage that reports an action |
| (c) Keep refusing every stage | No new risk | Haiku's route stops at the first such stage. The Plan 12.4 pilot cannot measure its Haiku arms, and Auto's exception routes stay exposed |

## Decision

On an exception route, a reply whose router pipeline is **exactly one `guardrail` stage** passes the pipeline check
only when **every** one of these holds. Facts are compared by identity, so an explicit null, a wrong type or an
unknown string is never a pass:
- there is exactly one closed-facts record for that stage;
- `flagged` is `false`;
- `detected` is `false` or `missing`;
- `decision` and `action` are both `missing`;
- `verdict_conflict` is `false`;
- `guardrail_scope` is `missing`.

Any other stage type, more than one stage, a mismatched facts count, or any other guardrail fact still refuses, as
before. The code is `optimus_gateway.model_policy.unflagged_guardrail_only`, which reads
`optimus_security.failure_facts.guardrail_stage_facts`.

## Controls and consequences

- **Unchanged:** every other reply check (one router attempt, the provider, the estimate bound, the finish status, the
  usage contract), receipt-first settlement, and the permanent route stop. A stop is never cleared by a later accepted
  stage. An accepted stage does not trip a stop.
- **The residual risk, accepted by the operator:** an accepted stage does not prove that the request or reply was
  unchanged, or how the guardrail handled the data.
- **On main** the exception route is pinned in code (`optimus_model_policy/experimental.py`), whose residuals now
  include this one. No effective registry hash changes, so no approval is renewed.
- **On the Plan 12.4 branch** admission is entry data (its ADR-025). The branch records this residual in each exception
  route's admission limitations, so those effective hashes change and the operator re-approves them.
- **Plan 12.4 v8** (decision N3) is the plan's complete successor for this change.
- **Not superseded:** ADR-023's shipped empirical admission stands. This record adds one accepted router-pipeline shape
  to the checks that admission runs under.
