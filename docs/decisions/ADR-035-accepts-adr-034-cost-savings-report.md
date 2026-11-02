# ADR-035: Accepts ADR-034, the cost-savings report

**Status:** Accepted, effective on the operator-approved merge of this record. **Decision date:** 2026-11-02.
**Decider:** the operator, with source S19 interpreted below and confirmed by approval to merge this record. Codex
authored Plan 12.9 in round 92; Claude implemented it; Codex reviewed Checkpoints A–C in rounds 93–95. All 13 checkpoint
reviews are posted verbatim on [#248](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/248). Round 96
produced the design-document successors; round 97 reviews this acceptance record. **Publication:** editable in
pre-merge review, frozen byte for byte on first merge to `main`.

**Relationship:**
- **Accepts** [ADR-034](ADR-034-cost-savings-report-read-and-presentation.md) as merged in `a88fde8` (PR
  [#462](https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/462)): its decision, its options and its
  consequences and limits, with no change. ADR-034 stays frozen and unchanged; its own status line still reads
  Proposed, and the index records the effective status.
- **Unchanged:** [ADR-012](ADR-012-cost-savings-report.md)'s open item 3, paid B3 authority, which stays closed here and
  is now owned by [#463](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/463); and the credential boundary
  of [ADR-032](ADR-032-durable-usage-capture-and-gateway-drain.md).

## The operator's decision (2026-11-02, verbatim, source S19)

> "please make necessary corrections and update the ADR abd any changes for closure"

**How this was read (Claude's interpretation, not the operator's words).** S19 followed Claude's closing report, which
listed "Accepting ADR-034, which stays Proposed until you do." among the remaining operator decisions. Claude reads the
closure request as proposing acceptance of ADR-034 as merged. Rule 5 of `docs/decisions/README.md` requires a new record
for a change to a merged ADR; it does not itself establish acceptance. The operator's approval to merge this exact
record confirms that interpretation.

## Context

ADR-034 merged with Plan 12.9 as Proposed, and said that operator acceptance was separate. Its mechanisms were reviewed
by Codex at the plan's Checkpoints A, B and C. PR #462 merged after green CI, main's push CI passed at `a88fde8` and
again at `24ceaf3` with the archive and design documents, and #248 is closed.

## Options considered

| | (a) Accept ADR-034 as merged | (b) Accepted-with-open-items | (c) Keep Proposed |
|---|---|---|---|
| What it says | The decision and its disclosed limits are accepted policy | The decision is accepted; named items stay open against the record | No acceptance yet |
| Fit with the evidence | Nothing in the decision text needs changing. B2, B3 and the Gateway-attach gap are outside ADR-034's decision and have their own issues | Would make those issues read as unfinished parts of this decision. It would suit the `/savings next` verification gap, which is inside the decision, but the operator has already dispositioned the qualification | Leaves a delivered, reviewed design looking unsettled, against the operator's request to update it for closure |
| Recommendation | **Claude and Codex (round 97); chosen** | Not recommended | Not recommended |

## Consequences and limits

- ADR-034's consequences and limits are accepted as written, including: the Auto table reprices the same reported tokens
  and does not predict Auto-off results; a classification receipt without a cached split leaves an Auto column
  incomplete; reference prices are dated evidence, not current prices; and cache-write tokens are in no column.
- **Delivery evidence stays qualified.** The status in `reports/plan12-cost-savings/qualification.json` remains
  "QUALIFIED under the operator's disposition". The one Windows full suite failed on a test double, and the operator
  accepted that without a rerun. The fix behind `/savings next` has not run in Zed or in a Windows full suite. These
  are dispositioned verification limits, not deferred tasks. This record does not establish that verification or waive
  real-Zed testing generally.
- **Owned elsewhere:** B2, B3, the unresolved paid-authority decision (not permission to spend) and the OC-4 items are
  [#463](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/463); a launch attaching to a Gateway it did not
  start is [#465](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/465).
- **Pinned records stay as filed:** HLD v2.24, LLD v2.47 and Test Strategy v1.10 state ADR-034 as Proposed at `a88fde8`,
  and `docs/README.md` notes the later acceptance. `reports/plan12-cost-savings/manifest.json` keeps the Task 0 plan path;
  the plan with that digest is now at
  `docs/superpowers/plans/archive/2026-11-01-plan-12-9-cost-savings-report-implementation_v2.md`.
- Not claimed: provider billing correctness, realized savings, or a B2 or B3 result.
- No implementation, paid call or new work is commissioned by this record.

## Decider and provenance

- **Acceptance:** the operator, 2026-11-02, in Claude's Plan 12.9 session (source S19), as interpreted above and
  confirmed by approval to merge this record.
- **Codex review of ADR-034's mechanisms:** rounds 93–95, as stated in the status line.
- **This record:** drafted by Claude; reviewed by Codex in round 97. Claude posts the round-97 reviews verbatim on #248
  before publication.
