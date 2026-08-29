# Plan 11.10: Documentation Status Consistency Design

**Status:** Draft for Claude and operator review. This design does not authorize the implementation
plan, documentation mutation beyond this draft, test mutation, commit, push, or pull request.

**Date:** 2026-08-11

**Scope:** Make the consolidated Optimus open-work pool the complete at-a-glance source for status
and priority, reconcile live status across its covered documents without changing pinned bytes,
repair the roadmap and charter, strengthen documentation-hygiene tests, and establish the
forward-only plan-versioning rule in `AGENTS.md`. This is documentation and documentation-test work
only. It makes no change under `src/`, to dependencies, authoritative PDFs, runtime behavior, or the
evidence-handoff product documents.

## Executive decision

Plan 11.10 uses a hybrid status-authority model because the approved edit boundary is intentionally
asymmetric:

- the pool is living and editable;
- 26 covered documents are split evenly between 13 immutable and 13 editable files; and
- six of the nine contradicted plan statuses are in immutable files.

Therefore pool-side frozen-document custody is the dominant Workstream 1 path. Editable plans with
missing or stale status receive accurate in-file status. Immutable plans and designs remain
byte-for-byte unchanged; the pool records one standardized frozen-authority marker and points to
the row that owns live status. The design does not manufacture `_v2` copies of historical plans to
avoid this boundary.

For the pool itself:

- all 42 `###` entries appear in exactly one entry index;
- all five currently ID-less open entries receive stable IDs;
- the four non-FU settled headings use a clearly labelled companion index;
- the existing five-token status grammar remains unchanged;
- the existing closure partition makes every `Promoted -> ...` row unambiguously unresolved;
- every row in every pool table receives one `Priority` cell, initially `MEDIUM`; and
- Priority exists nowhere else in the pool and is not a projection from entry bodies.

The success criterion is operational: a reader who reads only the pool tables and their adjacent
status legend can produce a complete and correct list of open items, resolved items, and initial
priorities without opening a detailed entry.

## Settled baseline and edit boundary

Gate 1 settled the boundary in
`docs/superpowers/reviews/plan-11-10-review-checkpoints.md`. It is not re-derived by this design.
The governing pool is editable and sits outside the 26-document covered-set count.

### Immutable covered documents

The following 13 current committed-blob digests match tracked approval or evidence records. No task
may change their bytes.

| Document | SHA-256 |
|---|---|
| Plan 10.2 implementation plan | `4303D6AD5C44ED62A85A0509C8C87366505D4D470DD7BC4E0B4309BBE6E3C771` |
| Plan 10.3 implementation plan | `E66ECA48C588E7DB618D4850FDF0CEE901B4966BC0AB405E21C857AE6BE24F32` |
| Plan 11.1 implementation plan | `254A6ACC56511BBCCEB8FC101B190F213FD65450327145C88979077D845D6D3E` |
| Plan 11.2 implementation plan | `8C96C9BFA67FB87F4A90FAE37169D27B437C5FD0CEE3AB2E6AB399E67B2874E5` |
| Plan 11.5 implementation plan | `0BAC146974984EA663B7A59802A1B5ED74F90EB682F855C0E05AAAB5B9A2C396` |
| Plan 11.7 parent implementation plan | `F52AD9A5A85DC50B0DFD3206B6BD09FD8FF0AE79B1A6049DF1017F978B1C462D` |
| Plan 11.7 feasibility amendment | `79F3C92A852CB7EAA6108D8F0757F6612A0C908FE032CE7CFAB58B46721C06E6` |
| Plan 11.7 origin-A amendment | `5BB327D88761AE329869B90866839D03F61EFF6AF0E5AE47F8D3D7551F849A4D` |
| Plan 11.7 retry-preflight amendment | `106FD92B8E43F44A7115D7EDB1F9CF1E3EE643E4B6F594FA656FB4119A969B82` |
| Plan 9.96 security design | `8B67FC187B92F0B66A9932AAAD9A013C476C19C165A1044F57F338245A01786C` |
| Plan 11.2 design | `2E679F105A250C7DF9F3757F72C43810B92810DD080EC6A4A985B778D163BFEC` |
| Plan 11.7 retry-preflight design | `EB34FA10148CE813A03E60E0770116ABA4AC9857E4DFBEE87E00C39BFDB0D392` |
| Plan 11.8 design | `AC48C0AEF1778D6EBE93005BC3993AE204F81A1C59CDC8DB17CFB7EDB6A040F8` |

### Editable covered documents

The editable set is the roadmap; Plans 9.8, 9.85, 9.87, 9.99, 10.1, 11.4, 11.6, 11.8, and
11.9; the Plan 11 charter; the Plan 11.4 design; and the P11-FU-9 design. Inclusion in the editable
set authorizes mutation only where this design names a required correction. It is not permission for
a general freshness rewrite.

Confirmed exclusions remain outside the work: Plan 9.6 live-signoff, Plan 9.98-FU-3, Plan 11.3,
narrative-only Plans 7, 9.7, 9.75, 9.88, 9.95, 9.96, and 9.97, and every evidence-handoff product
document named by `PRODUCT_OWNED_DOCS`.

## Alternatives considered

### Status-authority alternatives

1. **Recommended: hybrid authority.** Correct editable plan statuses in place; preserve every
   immutable byte; add one pool-side frozen-authority convention for pinned documents; keep live
   item status in the pool's feature, follow-up, and settled rows. This respects both the approval
   digests and the operator's pool-first workflow.
2. **Rejected: repair every status in place.** This would invalidate 13 recorded pins, including
   five approval records in the contradicting-status set and the Plan 11.7 evidence chain.
3. **Rejected: create retrospective `_v2` files for all stale pinned plans.** The new versioning rule
   is forward-only. Retrospective duplication would widen scope, obscure historical approval
   identity, and contradict the explicit preservation ruling for the three dated Plan 11.7
   amendments.

There is an unavoidable wording constraint: a marker cannot literally be inserted into an already
pinned file without destroying the pin. The implementable invariant is therefore:

- an editable plan tells the truth in its own `**Status:**` field; and
- an immutable artifact is identified by its approved digest, remains historical approval bytes,
  and has its live-status authority named in the pool.

The design records this explicitly rather than claiming that immutable bytes can be retrofitted.

### Promoted-resolution alternatives

1. **Recommended: use the existing closure partition.** Place a concise legend immediately beside
   the entry indexes: `Open`, `Promoted -> ...`, and `Partially implemented` are unresolved;
   `Closed` and `Reviewed disposition` are resolved. A promoted row is therefore visibly open until
   its own acceptance boundary changes its token to `Closed` or `Reviewed disposition`.
2. **Rejected: add a binary Open/Closed column.** The operator already declined a second binary
   status column, and it would duplicate information derivable from the canonical token.
3. **Rejected: extend the token to `Promoted -> ... (Open)`.** This would unilaterally change the
   five-token grammar and break exact status projection.

The recommended mechanism answers the Plan 11.7 case without following the target plan dynamically.
Both `P9.8-FU-5` and `P11-FU-1` remain unresolved because `Promoted -> ...` is itself an unresolved
token. If either item's acceptance criteria are later completed, its owning detail entry and table
row change to a closing token through the normal status workflow.

### Settled-entry alternatives

1. **Recommended: a companion settled index.** Keep every stable-ID FU heading in the main
   follow-up index, and put the accepted-risk heading plus the three closed-historical headings in a
   `Settled risks and historical entries` companion table. The union is the exact 42-heading
   projection.
2. **Rejected: mix title-keyed settled headings into the FU index.** Those four headings are not FU
   identities, and minting synthetic FU IDs for already-settled history would rewrite identity
   semantics. It would also make the active follow-up index harder to scan.

The companion table better serves the operator's question because settled non-FU material is
visible at a glance but cannot be mistaken for pickup-ready work.

## Workstream 1: status authority and frozen-document custody

### One frozen-authority marker

The pool gains a short, non-table section for immutable covered documents. A non-table list avoids
creating meaningless Priority values for document metadata. Each immutable path appears exactly
once with its approved digest and this exact semantic marker:

> Frozen approval bytes — live status is owned by the consolidated open-work pool.

Each list item links to the existing pool row or settled entry that owns current state. The marker
does not duplicate the owning row's full status prose. Tests enforce the exact 13-path/digest set,
unique occurrence, and the standardized marker wording.

The marker section is deliberately pool-side. The immutable files themselves remain untouched. The
pool's existing `How to use this document` section explains that approval-time status text inside a
pinned artifact is historical and that its referenced pool row is the live authority.

### Immutable contradicted statuses

Pool rows carry the correction for the dominant immutable group:

| Immutable plan | Historical text that cannot be changed | Live pool state |
|---|---|---|
| Plan 10.2 | Frozen/authorized, zero of 24 checked | Closed by PR #76 |
| Plan 10.3 | Draft/not authorized | Closed by PR #78 |
| Plan 11.1 | Pending approval/not authorized | Closed by PR #85 |
| Plan 11.2 | No status field | Closed by PR #88 |
| Plan 11.5 | Pending reviewer approval | Closed by PR #95 |
| Plan 11.7 parent | Draft/not authorized | Partially implemented and blocked |

The Plan 11.7 amendments remain unchanged and retain their approval-time draft text by design. Their
marker entries point to `P11-FEAT-ZED-RESUME` and `P11-FU-11`, which already carry the current
blocked/partial boundary. Immutable linked design specifications similarly remain approval artifacts;
their owning pool rows carry live work status.

### Editable status repairs

Only the following contradicted statuses are repaired in place:

- Plan 9.85 receives a plan-level live status that reflects its partially completed evidence gates
  rather than the nested "tracked, not yet scheduled" wording.
- Plan 9.87 records its reviewed closed disposition and names the closure authority despite its
  preserved historical unchecked evidence steps.
- Plan 11.9 records closure through PRs #123 and #124 instead of draft planning state.

Editable plans with no status receive a current field where required by the verified baseline:

- Plan 9.99 records `Partially implemented` because implementation Tasks 1-6 landed while three
  final verification steps remain unchecked.
- Plan 11.4 records closure through PR #91.

Plans 9.8, 10.1, 11.6, and 11.8 do not receive unrelated prose rewrites. The implementation plan
must inspect their current status fields and limit edits to a mechanically demonstrated violation of
this design. Design-spec status describes the approval state of the design artifact rather than the
live implementation lane; W1 does not rewrite linked specifications.

## Workstream 2: roadmap and charter freshness

The roadmap and charter remain summary/navigation documents, not competing status pools.

- The roadmap's Plan 11 milestone summary names Plans 11.1 through 11.9 explicitly enough that
  Plans 11.3 and 11.9 no longer disappear and the current closed/partial boundary is readable. It
  points to the consolidated pool for per-item live state rather than duplicating all detail.
- The charter replaces its false draft/no-subplan status with the ratified charter state and points
  to the pool for live feature status. Its feature summary acknowledges Plans 11.3 and 11.9 where
  their completed work belongs without converting the charter into a second backlog.
- README participates in the closing freshness audit. Its current Plan 11.6 references are not
  changed merely to increase plan-number coverage; it changes only if an audited current-state
  claim is false.

## Workstream 3: complete table-first pool

### Stable IDs and exact entry coverage

The current pool has 42 unique `###` headings, 33 stable-ID headings, and nine headings outside the
FU index. The five open ID-less headings receive the next unused linear FU identities:

| New ID | Existing title |
|---|---|
| `P11-FU-22` | Durable effect-aware MCP indeterminate-call custody |
| `P11-FU-23` | Durable client-MCP descriptor-surface pinning and named tool allowlists |
| `P11-FU-24` | Client-MCP durable HTTP/SSE trust relaxation |
| `P11-FU-25` | Authenticated client-owned MCP upstream evidence |
| `P11-FU-26` | Plan 11.8 Windows `WinError 10053` MCP test flake |

Repository search currently returns no use of `P11-FU-22` through `P11-FU-26`. Their assignment is
sequential and does not alter scope, status, or ownership.

After minting:

- the main follow-up index projects all 38 stable-ID `###` headings;
- the settled companion index projects the four remaining `###` headings; and
- the union is an exact title/row bijection for all 42 entries.

The Feature slices and P9.96 support tables are not part of the 42-entry bijection because their
rows represent feature identities and an aggregate historical view, respectively. They have their
own identity checks. This section-specific boundary is required to avoid pretending that the same
seven P9.96 IDs appearing in summary and disposition views are `###` headings.

### Table shapes

The pool ends with five Markdown tables:

1. Feature slices: `Identity | Status | Priority | Scope detail`.
2. Follow-up status index: `ID | Item | Status | Priority | Owning slice / designated plan | Evidence`.
3. Settled risks and historical entries: `Item | Status | Priority | Disposition / evidence`.
4. P9.96 historical summary: existing columns plus `Priority`.
5. P9.96 historical disposition: existing columns plus `Priority`.

Every body row in every table receives exactly one Priority cell. The initial value is `MEDIUM`
without exception. The allowed vocabulary is exactly `HIGH`, `MEDIUM`, or `LOW`.

Priority is authored only in table cells. Existing body prose such as `Priority: HIGH`,
`Priority: Low`, or descriptive `Priority:` labels is removed or rewritten to preserve any
non-priority fact such as "not a blocker." No `**Priority:**` field is introduced. The tests do not
compare Priority with entry bodies, do not create a Priority projection tuple, and do not enforce
cross-table equality for repeated P9.96 views. This deliberately follows the operator's one-copy,
table-only ruling.

### Canonical feature status

The Feature slices prose moves from `State` into `Scope detail`. The renamed `Status` cell contains
only a canonical token:

- `Closed`: Gateway Core, Gateway Tools, Gateway Cost/Observability;
- `Partially implemented`: Gateway MCP and Zed Resume; and
- `Open`: Registry, conditional IDE, and Plan 12.

The existing 27-of-46 Plan 11.8 boundary, PR #116/#118 evidence, and literal absence of
`next unused` remain in the Gateway MCP Scope detail cell. Tests enforce the same status vocabulary
for feature rows while leaving their detail prose unconstrained except for existing factual gates.

### Promoted rows and the closure partition

The table-adjacent legend defines:

- unresolved: `Open`, `Promoted -> ...`, `Partially implemented`;
- resolved: `Closed`, `Reviewed disposition`.

The Status cells for promoted entries remain exact projections of their detail-entry tokens. No
target-plan status is copied into the cell. This prevents a promoted item from appearing resolved
merely because it moved, and prevents target-plan drift from creating a second status source.

### Settled companion table

The companion table contains exactly:

- Plan 11.7 accepted risk: `optimus-redis` ACP-session durability boundary;
- Plan 10.3 frozen-plan status correction (historical);
- the historical `uv.lock` missing-direct-dependencies entry; and
- the historical `SurfaceAuditError` frozen-dataclass entry.

Its rows use the existing canonical `Reviewed disposition` or `Closed` token and `MEDIUM` Priority.
The detailed headings remain in place; the table is an index, not a migration of history.

## Workstream 4: forward-only plan versioning

`AGENTS.md` replaces the old generic "new plan file" amendment language with these rules:

- Going forward, amendment of an existing plan creates the next version of the same plan file:
  `XYZ.md` becomes `XYZ_v2.md`, then `XYZ_v3.md` as needed.
- The evidence-handoff risk-bearing-slice v1/v2 pair is cited as precedent but remains out of scope
  and unchanged.
- Existing dated amendment documents, including the three Plan 11.7 amendments, are not
  retroactively renamed because their approval digests are pinned.
- Once `_v2` exists, `_v1` is immutable; the consolidated pool points to the live version.
- Plan numbers extend linearly without limit: `11.9 -> 11.10 -> 11.11`.
- Interstitial allocations that sort between allocated numbers, such as the historical
  `9.8 -> 9.85 -> 9.975` pattern, are forbidden going forward.
- Nested sub-decimals such as `N.M.1` under a frozen plan are forbidden.

This rule separates plan identity from file version. A revised file keeps the same plan number;
new independently schedulable work takes the next linear plan number.

## Mechanical hygiene design

`tests/unit/docs/test_open_work_pool_hygiene.py` remains the only test file changed. The existing
product-owned assertions remain unchanged.

### Entry and table parsers

1. Replace the `len(entries) >= 41` floor with an exact bijection across the follow-up and settled
   indexes. Every `###` heading must map to exactly one designated entry-index row, and every such
   row must map back to one heading. A new ID-less or unindexed heading fails without changing a
   magic count.
2. Update `FU_INDEX_ROW_RE` for the six-column follow-up table. The exact projection remains
   `(title, status)`. Priority is parsed for independent validation but is not added to the
   projection tuple.
3. Add a settled-index parser keyed by exact heading title. Assert that main and settled row keys
   are disjoint and their union equals all entry headings.
4. Preserve `_entry_sections` duplicate-title rejection and `_status_token`'s exactly-one-Status
   rule.

### Priority validation

1. Parse every Markdown table in the Optimus pool by header.
2. Assert every table has exactly one `Priority` column.
3. Assert every body row has a cell in that column and its value is exactly `HIGH`, `MEDIUM`, or
   `LOW`.
4. Assert no non-table pool line contains a `Priority:` field or label.
5. Do not compare Priority against bodies or another table.

### Status validation

1. Preserve the five-token detail-entry grammar and exact Status projection.
2. Enforce canonical tokens in the Feature slices Status column.
3. Assert the documented closure partition and classify every `Promoted -> ...` token as
   unresolved without altering it.
4. Preserve promoted-target resolution beneath `docs/superpowers/plans/`.
5. Preserve `test_gateway_mcp_row_records_the_real_plan_118_boundary`, including `27 of 46`, PR
   #116/#118, and the `next unused` prohibition.

### Frozen and living document validation

1. Encode the approved 13 immutable paths and digests as a protected ledger in the documentation
   test or its local fixture.
2. Assert the pool's frozen-authority section lists the same paths and digests exactly once with the
   standardized marker.
3. During implementation, reject any Git diff touching an immutable path. Before sign-off,
   recompute hashes from committed `HEAD` blobs rather than trusting working-tree line endings.
4. Add targeted assertions for the editable status repairs and the roadmap/charter facts named in
   this design.
5. Add a documentation assertion for the forward-only `_v2` and linear-numbering language in
   `AGENTS.md`.

### Product boundary

These existing tests remain semantically and textually unchanged:

- `test_product_features_have_exactly_one_pool_owner`;
- all six `test_a2a_ledger_*` tests;
- `test_new_pool_has_no_scheduling_plan_numbers`;
- `test_new_pool_links_only_to_explicitly_product_owned_documents`; and
- `test_optimus_dependency_references_resolve_to_product_pool_without_status_custody`.

If one fails, implementation stops and reports a scope-boundary breach. Product Dependency clauses
remain free of status language.

## File responsibility map

| File | Designed responsibility |
|---|---|
| `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | Frozen-authority marker list; complete table-first status/priority index; five minted FU IDs; canonical Feature status; promoted closure legend; settled companion table. |
| `tests/unit/docs/test_open_work_pool_hygiene.py` | Exact entry-index bijection, all-table Priority validation, Feature status vocabulary, promoted unresolved partition, protected digest/marker checks, roadmap/charter and `AGENTS.md` regressions. |
| `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` | Current Plan 11.1-11.9 summary and pool pointer. |
| `docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md` | Ratified charter status and non-competing live-status pointer. |
| `docs/superpowers/plans/archive/2026-07-11-plan-9-85-multi-turn-read-observe-replan.md` | Accurate plan-level partial state. |
| `docs/superpowers/plans/archive/2026-07-12-plan-9-87-model-initiated-replanning-live-refusal.md` | Reviewed closed disposition. |
| `docs/superpowers/plans/archive/2026-07-22-plan-9-99-credential-uri-security-snapshot-canonicalization.md` | Missing partial-implementation status. |
| `docs/superpowers/plans/archive/2026-07-28-plan-11-4-gateway-core-migration.md` | Missing closed status. |
| `docs/superpowers/plans/archive/2026-08-08-plan-11-9-p11-7-fu-1-gateway-timeout-implementation.md` | Closed PR #123/#124 status. |
| `AGENTS.md` | Forward-only same-plan `_vN` file versioning and linear plan numbering. |

The design specification itself and the later implementation plan are additional Plan 11.10
artifacts. No other covered document is expected to change. In particular, Plan 11.8 implementation
and the two editable linked designs remain untouched unless Gate 2 review explicitly amends this
file map.

## TDD and verification strategy

Implementation is task-sequential and review-gated. Every documentation-hygiene behavior follows
RED-GREEN-REFACTOR:

1. Add the narrow failing test.
2. Run it and record the expected semantic failure.
3. Make the minimum documentation change.
4. Run the narrow test to green, then the complete pool hygiene file.
5. Stop for task review before the next task.

The later implementation plan must include these gates, with exact results recorded before any
completion checkbox is set:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/docs/test_open_work_pool_hygiene.py -v
.venv\Scripts\python.exe -m pytest tests/unit/docs -q
git diff --check
git diff --name-only origin/main...HEAD
```

It must also run the full CI-equivalent set before any task or Definition-of-Done claim:

```bash
uv run pre-commit run trailing-whitespace --all-files
uv run pre-commit run check-yaml --all-files
uv run pre-commit run check-toml --all-files
uv run pre-commit run check-added-large-files --all-files
uv run ruff check .
uv run bandit -q -r src -c pyproject.toml
uv run pre-commit run optimus-ast-grep --all-files
uv run python -m optimus.guardrails.prompt_injection
uv run detect-secrets-hook --baseline .secrets.baseline src
uv run pytest --cov=optimus --cov-branch --cov-report=term-missing -v
```

Immutable verification uses committed blobs:

```bash
git show HEAD:<immutable-path> | sha256sum
git diff --exit-code origin/main...HEAD -- <all-13-immutable-paths>
```

The expected SHA-256 values are the 13 values frozen in this design. The final documentation
freshness audit searches every current-state claim affected by Plan 11 status across the pool,
roadmap, charter, `README.md`, and `AGENTS.md`; it does not assume the implementer's named edits are
the complete set.

## Failure behavior

- An unindexed `###` heading, duplicate index row, row without Priority, invalid Priority token,
  non-table Priority field, or noncanonical Feature status fails the focused unit test.
- A promoted target outside the plan directory or a promoted row treated as resolved fails closed.
- Any immutable-file diff or digest mismatch stops the task before staging or commit.
- Any product-owned test failure stops work rather than widening the product-document scope.
- Any newly discovered current-state correction outside the file map requires a reviewed Plan 11.10
  design amendment; it is not silently folded into implementation.
- The implementation plan, commit, push, and PR remain unauthorized until their explicit gates.

## Definition of Done for the eventual implementation

- The governing pool plus 26-document boundary remains unchanged unless a reviewed amendment says
  otherwise.
- All 13 immutable committed blobs retain their approved SHA-256 values.
- Editable plan statuses named by this design are accurate and evidence-linked.
- The roadmap and charter no longer omit Plans 11.3 or 11.9 and do not compete with the pool for
  per-item live status.
- Every one of the 42 `###` entries appears in exactly one designated entry index, and every entry
  index row maps back to one heading.
- The five ID-less open entries own `P11-FU-22` through `P11-FU-26`.
- Feature status is canonical and its detailed prose remains in Scope detail.
- `Promoted -> ...` is visibly unresolved through the existing five-token closure partition.
- The four non-FU settled headings appear in the companion settled index.
- Every pool table row has one Priority cell; every initial value is `MEDIUM`; Priority appears only
  in table cells; no Priority projection or body field exists.
- The AGENTS plan-versioning rule is forward-only, preserves historical dated amendments, freezes
  v1 after v2, and allocates plan numbers linearly.
- Product-owned documents and their assertions are unchanged.
- Focused documentation tests, full CI-equivalent gates, Ruff, coverage, diff hygiene, immutable
  hashes, and the documentation freshness audit all pass with fresh evidence.
