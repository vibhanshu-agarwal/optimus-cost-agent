# ADR-033: Accepts ADR-032, durable usage capture with a host outbox and a Gateway-owned Postgres drain

**Status:** Accepted. **Decision date:** 2026-11-01. **Decider:** the operator (verbatim below, source S17), through
Codex's acceptance under the operator's standing rule. The mechanisms are Claude's; the review is Codex's (CLI rounds
88–91, posted on [#454](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/454)). **Publication:** editable
in pre-merge review, frozen byte for byte on first merge to `main`.

**Relationship:**
- **Accepts** [ADR-032](ADR-032-durable-usage-capture-and-gateway-drain.md) as merged in `f1e3bac` (PR
  [#456](https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/456)): its decision, its options and its
  consequences and limits, with no change. ADR-032 stays frozen and unchanged; its own status line still reads
  Proposed, and the index records the effective status.
- **Unchanged:** the credential boundary the operator accepted on 2026-10-31 with the Plan 12.8 plan-hash approval
  (ADR-032, Decider and provenance), and the two-credential rule for the ACP host.

## The operator's decision (2026-11-01, verbatim, source S17)

> "If the reviewer is happy to change it, then please change the status of ADR-032"

The operator's standing rule (2026-10-03) is that Codex's acceptance is the operator's. Codex's round-91 verdict on
this acceptance was "ACCEPT WITH CHANGES", with "No substantive decision text needs changing"; its one change was to
record the acceptance in this new record instead of editing ADR-032.

## Context

ADR-032 merged with Plan 12.8 as Proposed. Its mechanisms were reviewed and accepted by Codex at Checkpoint A (round
88), Checkpoint B (round 89) and final Checkpoint C (round 90, pass 5, at `b12cac3`). PR #456 merged after green CI,
#454 is closed, and the plan is archived. Under the publication-freeze rule (`docs/decisions/README.md`, rule 5), the
acceptance of a merged record is a new record.

## Options considered

| | (a) Accept ADR-032 as merged | (b) Accept with open items | (c) Keep Proposed |
|---|---|---|---|
| What it says | The decision and its disclosed limits are accepted policy | The decision is accepted; named limits stay open | No acceptance yet |
| Fit with the evidence | Codex accepted every checkpoint and found no decision text to change | No limit has an owner or an agreed fix; each is a disclosed trade-off, not owed work | Leaves a delivered, reviewed design looking unsettled |
| Recommendation | **Codex (round 91); chosen** | Not recommended | Not recommended |

## Consequences and limits

- ADR-032's consequences and limits are accepted as written, including: no hardware power-loss guarantee; local
  accumulation during a Postgres outage, with warnings and no deletion; capture is prospective only; a dead writer's
  committed tail can stay local, counted as pending; and the diagnostic copy is best effort, flushed and not
  fsynced.
- Not claimed: provider billing correctness or a generally working Phase 1 agent.
- No implementation, paid call or new work is commissioned by this record.

## Decider and provenance

- **Acceptance:** the operator, 2026-11-01, in Claude's Plan 12.8 session (source S17), conditional on the reviewer's
  agreement. Codex agreed in round 91 (#454 comment 6554829492).
- **Codex review of ADR-032's mechanisms:** rounds 88–90; every review is posted verbatim on #454.
- **This record:** drafted by Claude; reviewed by Codex before delivery.
