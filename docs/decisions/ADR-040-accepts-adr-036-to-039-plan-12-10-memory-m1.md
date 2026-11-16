# ADR-040: Accepts ADR-036 to ADR-039, the Plan 12.10 memory M1 decisions

**Status:** Accepted, effective on the operator-approved merge of this record. **Decision date:** 2026-11-16.
**Decider:** the operator (verbatim below, source S20). Claude implemented the mechanisms. Codex's checkpoint reviews
are posted verbatim for CP1 on [#465](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/465) and for
CP2–CP4 on [#469](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/469).
Codex CLI round 100 is the separate review of this acceptance record; Claude posts each round-100 review verbatim
on [#482](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/482) before publication.
**Publication:** editable in pre-merge review, frozen byte for byte on first merge to `main`.

**Relationship:**
- **Accepts**, as merged in `4ae7389` (PR [#478](https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/478)), each
  with its decision, its options and its consequences and limits, and with no change:
  - [ADR-036](ADR-036-local-gateway-attach-identity.md), local Gateway attach identity;
  - [ADR-037](ADR-037-context-index-storage-setup-and-worker.md), context index storage, setup and worker;
  - [ADR-038](ADR-038-context-index-retrieval-tools-and-caching.md), retrieval, tools and caching;
  - [ADR-039](ADR-039-provider-cache-breakpoint-after-the-map.md), the provider cache breakpoint after the map.
- The four records stay frozen and unchanged. Their own status lines still read Proposed, and the index records the
  effective status.
- **Unchanged:** alerts, not limits ([ADR-005](ADR-005-cost-alerts-not-limits.md)); models are configuration
  ([ADR-025](ADR-025-models-are-configuration-per-model-admission.md)); and the host's credential boundary of
  [ADR-032](ADR-032-durable-usage-capture-and-gateway-drain.md), which ADR-036 and ADR-037 keep.

## The operator's decision (2026-11-16, verbatim, source S20)

> "I accept ADR-036 to ADR-039."

It names all four records, so no interpretation is needed. It was also posted on #482 (comment 6914076353).

## Context

Plan 12.10 (#469) delivered under these four Proposed records. Each said that operator acceptance was separate, and
#482 tracked it. PR #478 merged at `4ae7389`; the closure PR #483 merged at `5715ff1`, and #469 is closed. Under the
publication-freeze rule (`docs/decisions/README.md`, rule 5), the acceptance of a merged record is a new record. One
record covers all four because the operator accepted them in one sentence, as ADR-033 and ADR-035 each accepted one.

## Options considered

| | (a) Accept all four as merged | (b) Accepted-with-open-items | (c) Keep Proposed, or decide each separately |
|---|---|---|---|
| What it says | The decisions and their disclosed limits are accepted policy | The decisions are accepted; named items stay open against the records | No acceptance yet, or four separate records |
| Fit with the evidence | The operator accepted all four in one sentence. Nothing in the decision text needs changing. The residuals below already have their own issues | Would make #477, #480 and #481 read as unfinished parts of these decisions. They are owned work outside the decisions | Contradicts the operator's decision; separate records would repeat one source four times |
| Recommendation | **Claude; chosen** | Not recommended | Not recommended |

## Consequences and limits

- The four records' consequences and limits are accepted as written. Among them:
  - **ADR-036.** An older Gateway taking the port after the check is not closed. Mixed configurations on one port refuse.
  - **ADR-037.** Two workspaces on one Gateway key are not isolated from each other by the index. A branch's first build
    is a cold build.
  - **ADR-038.** Grounding often says nothing about a symbol in a language the parser cannot see. A failed worker stops
    indexing for that session and does not restart by itself.
  - **ADR-039.** The `prefix` mode stays off by default. One paid pair proved reuse is possible. It says nothing about
    production hit rates or savings.
- **The index notes stay.** ADR-038's row keeps its note that Task 5's delivery evidence supersedes the record's
  implementation and "not yet proved" notes. Those bytes stay as merged.
- **Delivery evidence stays as recorded.** `reports/plan12-memory-m1/qualification.json` records the Windows full-suite
  disposition as "ACCEPTED WITH EXCEPTION (not a passing full run)" under Codex review 45. In `targets.json`, the
  `assembly` block is scoped to the 52-file pilot; `assembly_corpus_b` separately records the approved corpus-B
  ceilings. `qualify-6.json` records those ceilings as met. This record changes none of that evidence.
- **Owned elsewhere:**
  - the unauthenticated local Redis attach is [#480](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/480);
  - the Phoenix attach's identity check is [#481](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/481);
  - the test-run recorder's Windows terminal-record failure is [#477](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/477).
- **Not decided here:** turning on ADR-039's `prefix` mode for real use. ADR-039 says that follows an operator decision,
  and accepting the record is not that decision.
- Not claimed: production cache hit rates, realized savings, provider billing correctness or large-corpus
  qualification.
- No implementation, paid call or new work is commissioned by this record.

## Decider and provenance

- **Acceptance:** the operator, 2026-11-16, in Claude's Plan 12.10 session (source S20).
- **Codex review of the mechanisms:** Plan 12.10's checkpoint reviews, posted verbatim for CP1 on #465 and CP2–CP4 on #469.
- **This record:** drafted by Claude; reviewed by Codex in CLI round 100.
