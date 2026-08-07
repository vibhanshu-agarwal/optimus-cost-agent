# Consolidated Open-Work Pool Status Normalization Design

**Frozen design-body SHA-256:** `4ff6cc2591e2fe446d422847206769cfa96e20fad1356cb37947824a82525446`

The digest above is the SHA-256 of the committed UTF-8 LF-normalized file after removing only the
`**Frozen design-body SHA-256:**` line and its trailing line ending. The provisional zero value is
replaced from the committed blob after approval; the digest line is not part of the hashed body.

**Status:** Approved by the operator on 2026-08-07 for implementation planning. This specification
does not itself authorize production source, runtime, dependency, authoritative-PDF, or frozen-plan
mutation.

**Date:** 2026-08-07

**Scope:** Correct the consolidated open-work pool's verified stale claims, normalize its status
language, add a stable-ID follow-up index, and add mechanical anti-drift checks. This is a
documentation and documentation-hygiene-test change only; it does not change production source,
runtime behavior, dependencies, authoritative PDFs, or frozen plan bytes.

## Problem

The consolidated pool is the repository's living source of truth, but its status prose is not
mechanically constrained. The audit found:

- eleven status phrasings across 41 `###` entries;
- three entries without a `**Status:**` field;
- promoted work described without the pool's required `Promoted -> ...` form;
- a partially implemented lane described with activity-shaped wording;
- current-state negative-existence claims that remained after the denied artifact or behavior was
  implemented;
- four broken relative evidence links; and
- no follow-up index comparable to the feature-slice table.

The failure mode is silent aggregation drift: implementation, publication, or closure changes the
repository without forcing the pool's corresponding claim to change.

## Verified Baseline

The design is based on an independent sweep of the feature table, the historical disposition
table, all 41 `###` entries, local paths, relevant Git history, and cited GitHub pull requests.

- `P11-FEAT-GATEWAY-MCP` has a frozen design specification and a living Plan 11.8 implementation
  plan. PR #116 merged the implementation work; PR #118 repaired the resulting CI custody
  regressions.
- The Plan 11.8 plan has 27 checked and 19 unchecked boxes. Tasks 0-7 are complete, Task 8 Step 1
  is complete, Task 8 Steps 2-4 are incomplete, and Task 9 is incomplete.
- No repository document pins the Plan 11.8 implementation plan's current Git blob ID or SHA-256.
- Plan 11.6 / PR #97 added the local Phoenix launcher, port-identity checks, health probe, and
  operator runbook.
- PR #119 implemented and closed `P11-FU-9`.
- PR #111 implemented the `P11-FU-11` retry-preflight path through the reviewed Path A terminal
  stop, but the accepted same-session live retry remains unproved.
- The Plan 11.8 design, Plan 11.5 plan, Plan 11.7 parent plan and amendments, and Plan 10.3 plan are
  frozen/read-only and remain byte-for-byte unchanged.
- There are 32 stable-ID follow-up headings: 25 Plan 11.x-train IDs and seven legacy IDs. Nine
  additional `###` headings have no stable FU ID.
- Exactly four pool links incorrectly traverse two levels to `reports/`; the other report links
  use the correct three-level traversal.
- No open pull request owns any of the entries currently described as unscheduled.

## Canonical Status Contract

Every `###` entry must contain exactly one `**Status:**` field. The first text after the field must
match one of these forms and be terminated by `.` or `:` before explanatory prose:

1. `Open`
2. `Promoted -> [target](relative-plan-link.md)`
3. `Partially implemented`
4. `Closed`
5. `Reviewed disposition`

The tokens describe repository-verifiable artifact state:

- `Open` means the item is not scheduled into an implementation plan or amendment.
- `Promoted -> ...` means a plan or amendment owns the work and the entry has not reached its
  closure boundary. The target must be a Markdown link resolving to a file beneath
  `docs/superpowers/plans/`; a numeric Plan identifier is not required.
- `Partially implemented` means real implementation work is merged while the owning lane remains
  incomplete. The merged work must advance this entry's own acceptance criteria, not merely exist
  within its owning plan. Active-versus-paused human activity belongs only in the following prose.
- `Closed` means the acceptance boundary is fully implemented and has named implementation and
  evidence.
- `Reviewed disposition` means a reviewed, recorded decision closes the item without implementing
  it.

For the pool-closure gate, and therefore the v1.0 Definition of Done, an entry is resolved if and
only if its token is `Closed` or `Reviewed disposition`.

The expected 41-entry distribution after normalization is:

| Token | Count |
|---|---:|
| `Open` | 30 |
| `Promoted -> ...` | 2 |
| `Partially implemented` | 1 |
| `Closed` | 7 |
| `Reviewed disposition` | 1 |

The P9.96 aggregate section is not one of the 41 `###` entries, but its separate status field also
uses the canonical `Closed` token for document-wide consistency.

## Stable-ID Follow-Up Index

Add one table before the detailed entries with these columns:

| ID | Item | Status | Owning slice / designated plan | Evidence |
|---|---|---|---|---|

The table contains exactly the 32 headings whose form is `### <FU-ID>: <title>`:

- `P11-FU-1` through `P11-FU-20`;
- `P11.5-FU-1` and `P11.5-FU-2`;
- `P11.7-FU-1` through `P11.7-FU-3`; and
- `P9.8-FU-2`, `P9.8-FU-3`, `P9.8-FU-5`, `P9.85-FU-1` through `P9.85-FU-3`, and
  `P9.87-FU-1`.

The nine unnumbered/historical headings remain outside the index. Assigning synthetic IDs or using
editable titles as keys would make the index less stable. They remain fully covered by the
canonical-status and relative-link checks.

The table's Status cell is byte-identical to the entry's leading status token. For a promoted
entry, the token includes the same Markdown target link but excludes the terminating punctuation.
The detailed entry remains authoritative for explanatory prose.

## Factual Corrections

The pool and Plan 11.8 implementation plan receive these current-state corrections:

1. Replace the `P11-FEAT-GATEWAY-MCP` no-design/no-plan premise with links to the approved design
   and living Plan 11.8 plan, the 27/46 checkpoint, PR #116 implementation merge, PR #118 repair,
   and the 2026-08-06 pause/pivot. Do not state a concrete "next unused" Plan number; cite the
   numbering convention instead.
2. Set the living Plan 11.8 plan's status to `Partially implemented` and record the exact completed
   and incomplete task boundary. The frozen Plan 11.8 design remains untouched.
3. Update `P11-FU-3` so its closure prose records Plan 11.8 as the later implementation pickup
   rather than denying the plan's current existence.
4. Recast `P11-FU-9`'s ignored-`mcpServers` behavior as a dated intake finding resolved by PR #119.
5. Recast `P11-FU-11`'s unwired-preflight behavior as a dated pre-implementation finding and mark
   the item `Partially implemented` with the reviewed Path A non-claim preserved.
6. Recast `P11.5-FU-2`'s Phoenix and divergent-launcher descriptions as 2026-07-29 findings and
   point to Plan 11.6 / PR #97 and the living operator runbook.
7. Replace activity-shaped `P11-FEAT-ZED-RESUME` "active" wording with its verifiable partially
   implemented and blocked state.
8. Remove the `P11-FEAT-GATEWAY-CORE` contradiction between "no migration follow-ups" and the
   Vercel option remaining backlogged under the same stable identity.
9. Convert the two Plan 10.3 historical defects from present-tense findings into dated disclosures
   and give them canonical `Closed` statuses. Add `Closed` to the historical frozen-plan status
   correction entry without changing the frozen Plan 10.3 file.
10. Correct the P11-FU-11 terminal-seal link and three Plan 11.6 report links from `../../reports/`
    to `../../../reports/`.

All verified-current negative claims remain. In particular, ACP still does not implement or
advertise `session/load`; the named unscheduled FU entries have no implementation plan or open PR;
and the accepted local Redis container-durability limitation remains present in launcher code.

## Mechanical Hygiene Design

Extend `tests/unit/docs/test_open_work_pool_hygiene.py` using document parsers rather than
line-number assertions.

1. Parse all `###` sections and assert the document contains at least the 41-entry reviewed
   baseline. This protects the no-deletion history rule without forcing a magic-number edit for a
   legitimate addition.
2. Assert every entry contains exactly one `**Status:**` field whose leading token satisfies the
   canonical grammar.
3. Parse the 32 stable FU headings and the dedicated index table; assert unique IDs and an exact
   heading-to-row bijection.
4. Assert each table Status cell is byte-identical to the corresponding entry token.
5. For every promoted token, assert its Markdown link is relative, resolves to an existing file,
   and remains within `docs/superpowers/plans/` after path resolution.
6. Parse every relative Markdown link in the complete pool document, strip fragments, resolve it
   relative to the pool, and assert the target exists. External URLs and fragment-only links are
   excluded.
7. For `Closed`, `Partially implemented`, and `Reviewed disposition` entries, reject a historical
   defect section still labeled `Origin / current behavior`; settled entries must date the finding
   or label it as intake/pre-implementation behavior.

The tests intentionally do not force feature-table State cells into the five-token FU vocabulary.
Feature identities can span multiple implementation and follow-up plans. This leaves a known
residual: feature State prose can still drift semantically. The blanket relative-link test covers
feature-row links, while factual feature-state verification remains a documentation-freshness
review responsibility until a separately designed feature-state schema exists.

## TDD and Verification

Implementation follows documentation-focused TDD:

1. Add the new hygiene tests against the current pool and run the focused file to demonstrate the
   expected failures.
2. Update the pool and living Plan 11.8 status until the focused tests pass.
3. Run all documentation unit tests, then the complete default suite.
4. Run repository-wide Ruff, `git diff --check`, the negative-existence grep, the blanket link
   parser, and protected-file SHA checks before completion.

No frozen plan, authoritative PDF, production source file, dependency file, or runtime artifact is
modified.
