# Review Chronology — A2A Not-Shipped Closure Plan (preserved record)

Preserved from gitignored `.superpowers/sdd/a2a-not-shipped-closure-plan-review.md` on 2026-08-12.
Audited commit `e5f7e339`. Author: Codex (reviewer). Reviewer: n/a — this is the review record.

**Body pinned at the H1 custody cutoff, 2026-08-12T12:24:30Z: 71,285 bytes, SHA-256
`601142B974898ECEAB9F2750A84C572FE51637FEDCC33069DA89177AC9333EA0`.** The live source is
append-only and keeps growing past this point; this record intentionally does not track it further.
Later review rounds live only in the ignored chronology and in the append-only Review Chronology
narrative itself, never in this pinned body.

**Latest disposition: see live `_v3`** (`docs/superpowers/plans/archive/evidence-handoff-a2a-not-shipped-closure_v3.md`)
for current authorization status and execution state. This file is the append-only chronology of
every review ruling that produced it, superseding no earlier round; earlier rounds open with
CHANGES REQUIRED and are historical, not the current ruling.

The region between the PRESERVED-BODY markers below is byte-identical to the pinned cutoff source
and must not be edited. Any later material (for example a custody manifest) goes **outside** it.

<!-- PRESERVED-BODY-START -->
# Review — A2A Not-Shipped Closure Plan

## Current State

**Live artifact:** `.superpowers/sdd/a2a-not-shipped-closure-plan_v3-DRAFT.md`  
**Artifact SHA-256:** `0A14921BB2E7F9534668726BA4D00B1D49BFE9117F112028E835D04D308943A8`  
**Decision:** **TASK 1C BYTE RECONSTRUCTION VERIFIED, BUT THREE CUSTODY/DOCUMENT CORRECTIONS ARE
REQUIRED; TASK 1D REMAINS BLOCKED.**

PR #131 is merged into `main` as `e2496ced8580ff0318bf263c5c43eb446bea10e0`.
Records 1-6 were independently verified byte-for-byte against their authoritative sources at the
observed cutoff; `_v2` has one intended logical status-line change after LF normalization; and
`_v3` exactly matches the LF-normalized live plan. Before staging, apply the three corrections in
the checkpoint below, rerun Task 1C's final verification, and return. Do not execute Task 1D.

## 2026-08-12T12:24:30Z — Task 1C reconstruction verified; custody cutoff correction required

Fresh direct-byte verification found exactly one structural START/END marker pair for each of
records 1-6 and exact source-body equality. The observed body digests include independent audit
`FFE80EA3…`, sealed findings `510E1107…`, scoping review `464EBEAF…`, closure review
`B8D78979…`, scoping contract `30BC62B6…`, and v1 closure plan `C993B3A6…`. Records 5-6 retain
their 297/295 CR bytes. Record 7 is LF-clean and `git diff --no-index` reports only its intended
status-line change. Record 8's raw blob equals the live `_v3` after path-aware LF normalization.
The custody worktree has exactly eight expected untracked paths, no staged or tracked diff, and is
`0 0` against `origin/main`. All eight Bash fences pass `bash -n`; the ledger has 53 boxes
(19 checked / 34 open), 20 obligation rows, and zero lone CR bytes.

### H1. [P0] Record 4 needs an immutable custody cutoff before Task 1D

Record 4's body matched the live reviewer chronology at the instant of inspection (67,481 bytes,
SHA-256 `B8D78979BA4E476EF9254BA0CD0CAA44449529BD94A6DA4C745EA8A47CEB90A0`). Recording this required
review checkpoint necessarily advances that source. Task 1D currently compares record 4 against
the ever-growing live file, so the correct reconstruction becomes stale merely because the
reviewer performs the mandatory checkpoint update.

Freeze record 4 at the exact reviewer-chronology bytes **through this checkpoint**. The reviewer
will report that post-checkpoint SHA-256 and byte count externally. Reopen Task 1C Steps 1, 4, and
5; refresh record 4's body once from that cutoff; and record the cutoff digest/size in `_v3`.
Amend Task 1D Step 2 so records 1-3 and 5-6 remain exact-current-source comparisons, while record 4
is extracted from the staged blob and verified against the pinned cutoff SHA-256 and byte count,
not the subsequently advancing live source. Update the Step 2 checkbox wording to match. Later
review checkpoints remain in the ignored chronology unless a later plan step explicitly refreshes
the tracked body; they do not invalidate the pinned custody baseline.

### H2. [P1] Historical `_v2` still calls itself the live execution target

Record 7 line 8 says `This is the live execution target; v1 is history`, immediately before its
new line 9 says `_v2` is historical and `_v3` is live. Remove the stale live-target clause from
line 8, retaining only v1's immutability statement. Reopen Task 1C Step 3 and update its evidence:
the normalized `_v2` diff must contain exactly the two permitted header edits (line 8's stale
clause removal and line 9's historical disposition), with all substantive plan content unchanged.

### H3. [P1] The live byte-count table is false for record 8

The table records 49,173 bytes, while the reconstructed record 8 is 50,557 bytes at the inspected
state (834 LF, zero CR). Because the H1/H2 plan corrections will change live `_v3` again, do not
hard-code 50,557 prematurely. After every required plan/evidence edit is final, regenerate record
8 from LF-normalized `_v3`, recompute all eight target sizes, update the table, regenerate record 8
again, and confirm its self-reported size equals its actual size (repeat if digit-width changes).
Reopen Task 1C Steps 4-5 for that final copy and exact-eight-untracked stop proof.

**Authorization boundary:** only the H1-H3 Task 1C/plan corrections above are authorized. Keep all
eight records untracked. Do not stage, commit, push, execute Task 1D or later, edit pools/tests,
close M17, or schedule remediation. Return the corrected `_v3` and eight-record state for review.

## 2026-08-12T11:56:37Z — Live header corrected; Task 1C released

The live header now truthfully states Task 1A and Task 1B are complete and Task 1C awaits reviewer
authorization. Searches find no remaining claim that Task 1B is blocked or pending G1. The edit is
header-only: the checkbox ledger remains 53 boxes (14 checked / 39 open), all 20 obligation rows
remain, and direct byte inspection finds 797 CRLF pairs with zero lone CR bytes.

The custody worktree remains at `e2496ced…`, `0 0` against `origin/main`, with exactly the six
expected untracked candidate records and no staged or tracked diff. This is the approved Task 1C
input state.

**Authorization boundary:** execute Task 1C Steps 1-5 and stop. Task 1C may create/finalize the
eight untracked records named by the source map, but must not stage them. Task 1D index verification,
Task 1E custody commit/PR, Tasks 2-5, M17 closure, and remediation scheduling remain blocked.

## 2026-08-12T11:48:00Z — Task 1B accepted; stale live header blocks Task 1C

Fresh custody-worktree verification reports `HEAD`, merge-base, and `origin/main` all at
`e2496ced8580ff0318bf263c5c43eb446bea10e0`; `origin/main...HEAD` is `0 0`; exactly the six expected
candidate records remain untracked; and there is no staged or tracked diff. The eight-path
attribute check reports `text: unset` for records 1-6 and `text: auto` / `eol: lf` for both `_v2`
and `_v3`.

The checkbox ledger is truthful at 53 boxes (14 checked / 39 open), all 20 obligation rows remain,
the file contains 796 CRLF pairs and zero lone CR bytes, and all eight Bash fences pass `bash -n`.
Task 1B execution is therefore accepted.

One current-state defect remains: the live header still says **“Task 1B remains blocked pending
review of the G1 correction”**, although G1 was approved and Task 1B is complete. This directly
contradicts the checked Task 1B section and can mislead a fresh worker reading the plan from the
top. Correct that header in place and return for the bounded Task 1C release.

**Authorization boundary:** no Task 1C reconstruction or later work is authorized by this
checkpoint. Tasks 1C-1E and 2-5, the custody commit/PR, M17 closure, and remediation scheduling
remain blocked.

## 2026-08-12T11:41:27Z — G1 approved; Task 1B released

The G1 correction closes the future Task 1D cleanup defect. Both `pwd -P` producers are checked;
the resolved scratch directory must equal exactly `$ROOT/.custody_scratch`; recursive deletion
targets only that validated absolute path; deletion is checked; and both absolute and relative
absence proofs are required. The header, Task 1E scope statement, and historical Task 1A Steps 7-8
now accurately record the merged tooling PR.

Fresh independent verification found 785 lines, 53 checkboxes (11 checked / 42 open), eight Bash
fences passing `bash -n`, 784 CRLF pairs and zero lone CR bytes. The 20-row obligation table remains
present. Merge commit `e2496ced…` is an ancestor of `origin/main`.

The custody worktree remains on `agent/claude/a2a-audit-docs-preservation` at `e5f7e339…`, two
commits behind `origin/main`, with exactly the six expected untracked candidate records and no
staged or tracked diff. This is the expected Task 1B input state.

**Authorization boundary:** execute Task 1B Steps 1-3 and stop. Do not reconstruct or stage the
eight-record custody set, create the custody commit/PR, edit pools or tests, close M17, execute
Tasks 2-5, or schedule remediation.

**Reviewer:** Codex  
**Date:** 2026-08-12  
**Artifact reviewed:** `.superpowers/sdd/a2a-not-shipped-closure-plan-DRAFT.md`  
**Authorities:** independent A2A audit, approved remediation scoping contract, operator ruling to
declare not-shipped / correct M17 / defer  
**Decision:** **CHANGES REQUIRED — do not execute the draft yet**

The proposed outcome is correct: preserve the audit, make the product pool state truthful, give all
20 obligations durable deferred custody, and schedule no remediation. A separate design is not
needed. The draft is not yet executable as a plan because it omits one of the audit records, places
an audit under `specs/` to make it linkable, asks for committed-blob hashes before any commit exists,
and spreads one test-pinned link/ownership mutation across tasks that would leave intermediate
review checkpoints knowingly broken.

## Direct rulings on the open questions

### 1. Add Priority to both product-pool tables: yes

Do it in this closure. The product-pool pass was deliberately deferred by the earlier Optimus-only
work, and product documents/tests are now explicitly in scope. Leaving the new tables inconsistent
would create another known freshness item during the very change intended to make the pool durable.

Required convention:

- `Feature slices`: `Identity | State | Priority | Scope detail`.
- `A2A ledger audit obligations`: `Obligation | Severity | Owning slice | Status | Priority`.
- Every row starts `MEDIUM` except the existing
  `EVIDENCE-HANDOFF-FEAT-CREDENTIAL-LIFECYCLE`, whose authored **HIGH** priority must move from State
  prose into the Priority cell. Do not preserve a duplicate inline `Priority:`/`HIGH priority` label.
- The six deferred remediation slices remain `MEDIUM`; Severity in the obligation table expresses
  security impact, while Priority expresses the operator's current scheduling decision.
- Add product-pool tests proving both tables have exactly one Priority column, every cell is one of
  `HIGH|MEDIUM|LOW`, Credential Lifecycle is the sole non-MEDIUM seed, and no body priority label
  remains.

### 2. No preceding design spec: approved

This is a bounded documentation/custody correction with docs-contract tests. The operator decision
and approved Revision 3 scoping contract already settle the architectural and deferral boundaries.
A new design would add no decision surface.

The **closure plan itself must still be finalized into tracked product storage before execution**,
with its approval review preserved. “No design needed” does not mean the executable plan may remain
only in gitignored `.superpowers/sdd/`.

## Blocking plan findings

### 1. [P0] The preservation set is incomplete, and the audit is misclassified as a spec

Task 1 says three artifacts are the complete gitignored set, but
`.superpowers/sdd/a2a-audit-SEALED-reviewer-findings.md` is a fourth audit record. The independent
report's differential explicitly relies on it and pins its digest. Omitting it violates the
operator's “none of the audit docs are lost” instruction.

The independent audit is also a review/evidence record, not a product specification. Putting it
under `docs/superpowers/specs/` solely to satisfy the markdown-link allowlist corrupts document
taxonomy. A test constraint is not a reason to relabel an audit as a spec.

**Required correction:** preserve at least these records:

| Source | Tracked classification |
|---|---|
| `a2a-audit-independent-findings.md` | `docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md` |
| `a2a-audit-SEALED-reviewer-findings.md` | `docs/superpowers/reviews/evidence-handoff-a2a-ledger-sealed-reviewer-findings.md` |
| approved Revision 3 scoping proposal | `docs/superpowers/specs/evidence-handoff-a2a-ledger-remediation-scoping.md` |
| scoping review chronology | `docs/superpowers/reviews/evidence-handoff-a2a-remediation-scoping-review.md` |
| approved closure plan | a tracked `docs/superpowers/plans/evidence-handoff-*.md` path |
| this plan review/approval chronology | a tracked non-checkpoint file under `docs/superpowers/reviews/` |

Only the scoping contract and closure plan are plans/specs eligible for pool markdown links and
`PRODUCT_OWNED_DOCS`. Reference the independent audit, sealed review, and both review chronologies by
backticked tracked path. This follows the constraint already recognized for the scoping review.

If source bodies remain byte-identical below provenance headers, the scoping header must explicitly
state that its approval-at-Revision-3 authority supersedes the preserved body's historical
“DRAFT/for review” status text. Do not leave two apparently coequal status declarations.

### 2. [P0] The committed-blob digest step is impossible in the stated task order

Task 1 creates new files and immediately requires `git show HEAD:<path>`. Until those files are
committed, that command fails. The plan contains no commit boundary and does not say where the
digests are recorded. A digest cannot be inserted into the file it hashes without changing the
digest.

**Required correction:** define two explicit custody phases:

1. After byte/body verification and reviewer approval, create an **operator-authorized artifact
   custody commit** containing the finalized tracked plan and preserved records.
2. In the later pool/docs commit, compute hashes from that exact custody commit using
   `git show <custody-commit>:<path>` and record them in a named tracked custody location (for example
   the corrected A2A row or a tracked review manifest). Never use a moving `HEAD` implicitly.

The plan must name the recording file and commit sequence. If commit authorization has not been
granted, stop before the custody commit; do not substitute working-tree hashes while claiming
committed-blob custody.

### 3. [P0] Link creation, ownership listing, and the test allowlist are split across broken checkpoints

Task 2 adds markdown links, Task 4 later adds pool ownership entries, and Task 5 later updates
`PRODUCT_OWNED_DOCS`. The pinned equality/link test must fail between those steps, yet every task says
“Stop for review.” That violates the plan rule that each reviewed task ends with a coherent,
testable deliverable.

**Required correction:** treat each new markdown link as one atomic mutation:

- create the linked tracked plan/spec;
- add it to the pool's product-owned-document list;
- add it to `PRODUCT_OWNED_DOCS`; and
- add the pool link;

within the same task/test cycle. Review records use backticked paths and need none of those link
allowlist changes. Do not deliberately leave the repository red at a task checkpoint.

### 4. [P0] “Safe deferral” / “latent, not live” overstates the evidence

The inspected facts are narrower:

- lifecycle `--enabled` defaults false; and
- `src/optimus`/`src/optimus_gateway` do not import the A2A ledger/runtime path (the Optimus adapter
  imports only the separately closed redaction model).

But the installed distribution still exposes `evidence-handoff-lifecycle` and
`evidence-handoff-service`. Manual invocation can reach known defective paths; the service CLI can
select the false-success stub without an auth bundle. Therefore the defects are not globally
unreachable or proven safe.

**Required correction:** state this as a **bounded deferral rationale**, not a safety proof:

> The feature is not on the ordinary Optimus runtime path and lifecycle activation is opt-in by
> default. However, merged code and installed console entry points remain manually callable. They
> are unsupported and untrusted and must not be enabled or used for trusted workflows.

Tests may pin the two bounded facts. Do not assert “latent, not live” without the manual-entry-point
qualification, and do not imply that a documentation declaration disables code.

### 5. [P1] M17/adjacent custody edits are not explicit enough

Adding six rows while leaving the existing adjacency prose unchanged creates ambiguous ownership.
The approved scoping contract requires exact custody boundaries. The plan must name the edits, not
say only that the main row “reconciles” them.

Required pool updates:

- `A2A-LEDGER-DESIGN-REFRESH`: remove operation-entry guard custody in favor of
  `LEDGER-INTEGRITY-BOUNDARY`; retain design v2 restatement, Docker/wslc, and session Option A.
- `AT-REST-INTEGRITY`: retain periodic/scheduled post-readiness historical verification; remove
  operator-triggered/on-demand full-audit wording now owned by the Integrity Boundary slice.
- `CREDENTIAL-LIFECYCLE`: retain OAuth/rotation and Cursor discovery interoperability; state the
  Evidence/DoD slice dependency or its obligation to narrow the future native-client claim.
- `PEER-LIVENESS-SIGNAL`: remove stale “in-flight Task 6/Task 10/Task 11” phrasing and retain the
  independent non-goal owner.
- Main A2A row: say code remains merged and console scripts remain present, while the capability is
  not shipped/supported/trusted.

The required documentation-freshness audit also found one Optimus-pool statement that must be
corrected or explicitly dispositioned: the accepted Redis-risk entry currently names “the A2A
ledger's hardened-Redis fallback path” as though such a path exists
(`2026-07-23-consolidated-deferred-followups-backlog.md:1396-1399`). The A2A runtime is PostgreSQL,
not a hardened Redis fallback. A narrow correction to generic future consolidated-startup work is
within M17 freshness scope; retaining the current false product reference is not.

No README current-state A2A claim was found. Historical references to the unchanged frozen v1/v2
pair need not be rewritten merely because the supported product state changes.

### 6. [P1] The docs-test contract misses existing and newly introduced invariants

Task 5 must be expanded. At minimum:

- Add all six new feature IDs to `PRODUCT_FEATURE_IDS`; otherwise the exact-one-product-owner test
  does not protect them.
- Replace/rename `test_a2a_ledger_reachability_blocker_is_resolved_and_design_is_owned`, whose
  current assertions pin the old “resolved/Closed” narrative. Assert not-shipped/not-trusted,
  `658042d`, 25 commits, both merged PRs, default-off activation, no ordinary Optimus ledger/runtime
  import, and the installed-entry-point warning.
- Test the exact 20-row obligation→owner→severity mapping, not only the obligation set and owner
  vocabulary. H12a/H12b must both be HIGH; M16a/b/c remain MEDIUM.
- Add the two-table Priority contract ruled above.
- Assert each reviews artifact is referenced by a backticked path and does not appear as a markdown
  link; assert only the actual linked plan/spec additions enter `PRODUCT_OWNED_DOCS`.
- Assert all six slice states are `Tracked, Not Yet Scheduled` and M17 alone is Closed in the
  obligations projection; the parent A2A row is not `Closed`.
- Pin the adjacent-custody clauses so future wording cannot silently restore dual ownership.
- Run the narrow docs file after each red/green cycle:
  `uv run pytest tests/unit/docs/test_open_work_pool_hygiene.py -q`.

The plan should include the concrete constants, parser/helper reuse, and expected mappings rather
than “add a test” prose. This is a plan contract for an agent unfamiliar with the context.

### 7. [P1] The advertised “full CI-equivalent” gate list omits CI commands

The current list starts after Guardrails' install/package stages. It omits:

- `uv sync --all-extras`;
- wheel build; and
- `tools/verify_plan99_noneditable_install.py`.

Either include those exact workflow commands or rename the list honestly. Given H12's history, use
the actual local-executable Guardrails command inventory, plus the narrow docs test. Also run
`uv lock --check` and `git diff --check` as repository release gates even though they are not current
Guardrails workflow steps.

A known flake is diagnostic context, not permission to check a failed gate. If a full command exits
nonzero, isolate the known test, then rerun the original full command to exit 0 before marking the
checkbox. Preserve the rule that a selected-but-deselected or failed command never becomes `[x]`.

## Required revision checklist

- [ ] Preserve the sealed reviewer findings and the finalized plan/review chronology as tracked
  records.
- [ ] Put audits under `reviews/`, not `specs/`; use backticked paths for review/audit records.
- [ ] Specify provenance-header precedence over preserved historical Draft status text.
- [ ] Add an authorized custody-commit boundary before committed-blob hash computation; name where
  hashes are recorded.
- [ ] Make new link + ownership list + `PRODUCT_OWNED_DOCS` changes atomic.
- [ ] Replace “safe/latent” language with bounded default-off/no-Optimus-path facts plus the manual
  console-entry-point warning.
- [ ] Spell out updates to all four adjacent custody rows and the stale Optimus Redis reference.
- [ ] Add Priority to both product tables, using MEDIUM default and preserving Credential Lifecycle
  HIGH as the sole exception.
- [ ] Update `PRODUCT_FEATURE_IDS`, replace the stale A2A test, and pin exact severity, priority,
  state, link, and custody mappings.
- [ ] Add the narrow docs-test cycle and the missing install/noneditable package gates; require a
  clean rerun after any isolated flake.
- [ ] Track the approved closure plan itself; keep designs/runtime/pinned A2A artifacts untouched.

## Final ruling

**Return a revised closure plan; no design spec is required.** The plan may remain a five-task plan
if Claude regroups the work so every task closes a complete red/green or custody cycle. The
essential order is: tracked custody baseline and authorized artifact commit; TDD-protected atomic
pool/ownership changes; obligation/priority projection; cross-document freshness; then full gates,
committed-blob evidence, and closure. Nothing in this review authorizes remediation code, scheduling
of A–F, commits, or execution.

---

## Revision 2 re-review — 2026-08-12

**Artifact:** `.superpowers/sdd/a2a-not-shipped-closure-plan-DRAFT.md`, Revision 2  
**Decision:** **CHANGES REQUIRED — one narrow Revision 3; do not execute Revision 2**

Revision 2 substantively adopts all eleven items from the first review. The preservation set,
document taxonomy, 20-obligation projection, six slice owners, severity/priority policy, bounded
not-shipped wording, M17 custody split, product/Optimus freshness scope, and the no-design ruling are
now correct. The plan is not executable yet because four mechanical custody and gate defects remain.

### R2-1. [P0] The noneditable-package gate is guaranteed to fail

The plan runs:

```bash
uv build
uv run python tools/verify_plan99_noneditable_install.py
```

That is not the Guardrails command. The verifier declares both `--wheel-dir` and `--scratch-root`
as required arguments (`tools/verify_plan99_noneditable_install.py:409-412`), so Revision 2 exits at
argument parsing. Guardrails also builds a wheel into the directory passed to the verifier
(`.github/workflows/guardrails.yml:34-39`).

**Required correction:** use the local-executable equivalent of the actual workflow:

```bash
uv build --wheel --out-dir dist/plan99
plan99_scratch="$(mktemp -d)"
uv run python tools/verify_plan99_noneditable_install.py \
  --wheel-dir dist/plan99 \
  --scratch-root "$plan99_scratch"
```

The plan must also require exactly one wheel in `dist/plan99`, because the verifier enforces that
precondition. This is a gate correction, not an A2A implementation change.

### R2-2. [P0] The required second commit and its authorization boundary are still missing

The first review required two custody phases: an authorized six-record custody commit, then a later
pool/docs commit containing the projection and custody manifest. Revision 2 defines the first commit
but stops at Task 5 Step 5 with the later changes only in the working tree. It neither requests
operator authorization for the closure commit nor creates it. Therefore its claimed two-phase
disposition is incomplete, and M17 is not durably closed.

**Required correction:** after final reviewer approval, stop and request explicit operator
authorization for a second, final closure commit. On authorization, that commit must contain exactly
the intended post-custody files:

- `docs/superpowers/plans/archive/evidence-handoff-open-work-pool.md`;
- `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`;
- `tests/unit/docs/test_open_work_pool_hygiene.py`;
- `docs/superpowers/reviews/evidence-handoff-a2a-not-shipped-closure-review.md`; and
- `docs/superpowers/plans/archive/evidence-handoff-a2a-not-shipped-closure.md`, whose checkboxes are the
  required on-disk progress record.

Re-run `git status --short` immediately before that commit and reject any extra path. Nothing in this
review grants either commit authorization; the planned Task 1 Step 4 stop remains mandatory.

### R2-3. [P0] The manifest step contradicts byte preservation and masks `git show` failure

Task 1 promises that every destination body remains byte-identical below its provenance header.
Task 5 then appends a custody manifest to one of those six destinations. Without an explicit
preserved-body boundary, both statements cannot remain true.

The proposed `git show <custody-commit>:<path> | sha256sum` also violates the plan's own evidence
rule. In a normal shell pipeline, `sha256sum` can exit zero after a failed `git show`, producing the
hash of empty input. The later instruction not to read `$?` after a pipe does not make that pipeline
safe.

**Required correction:** add explicit start/end delimiters around each immutable preserved source
body, diff only that delimited region in Task 1, and place the later manifest outside the preserved
region. For each blob, first redirect `git show` to a temporary file, capture and require the
`git show` return code, and only then hash the temporary file. Record path, custody commit SHA, digest,
and verified line count. Do not use a pipeline unless `pipefail` and the producer status are both
explicitly verified.

### R2-4. [P1] Approval precedence must cover the closure plan too

The scoping destination correctly gets a header saying Revision 3 approval supersedes the preserved
body's historical DRAFT status. The closure-plan source itself says `Revision 2, for review` and
`Authorizes nothing`; preserving that below a generic provenance header recreates the same competing
status problem.

**Required correction:** the tracked closure-plan header must identify the approved revision and
review disposition and explicitly state that this current authority supersedes the preserved
body's historical review-only status. Apply the same latest-disposition rule to the preserved plan
review chronology so its opening Revision 1 `CHANGES REQUIRED` line cannot be mistaken for the
current ruling.

## Revision 2 ruling

Return Revision 3 with only these four corrections. The five-task structure, no-design ruling,
Priority policy, six-slice deferral, and all substantive obligation/custody assignments are approved
and should not be reopened. Once Revision 3 is approved, Claude may execute only through Task 1
Step 3, then must stop at Step 4 for the operator's custody-commit authorization as already planned.

---

## Revision 3 re-review — 2026-08-12

**Artifact:** `.superpowers/sdd/a2a-not-shipped-closure-plan-DRAFT.md`, Revision 3  
**Decision:** **APPROVED FOR BOUNDED EXECUTION — mandatory stop at Task 1 Step 4**

Revision 3 makes only the four authorized mechanical corrections. No substantive scope, priority,
severity, ownership, custody, design, or scheduling decision was reopened.

### Disposition of the Revision 2 findings

| Finding | Revision 3 disposition |
|---|---|
| R2-1 noneditable-package command could not run | **Resolved.** The plan builds one wheel in `dist/plan99`, asserts the verifier's exactly-one-wheel precondition, creates a temporary scratch root, and passes both repository-required arguments. This matches `.github/workflows/guardrails.yml:34-39` and `tools/verify_plan99_noneditable_install.py:409-412`. |
| R2-2 second commit/authorization boundary missing | **Resolved.** Task 5 Step 6 requires final review, a separate operator authorization, immediate `git status --short`, rejection of extra paths, and the exact five-path closure-commit allowlist. The tracked closure plan is included as the checkbox record. |
| R2-3 manifest contradicted preservation and hashing masked failure | **Resolved.** All preserved bodies have explicit start/end delimiters; the manifest is outside them. Each `git show` writes to a temporary file, its return code is required before hashing, and the manifest records path, custody SHA, digest, and line count. No custody hash uses a pipeline. |
| R2-4 approval precedence incomplete | **Resolved.** Current-authority headers are required for the scoping contract, closure plan, and both review chronologies, expressly superseding historical review-only dispositions in their preserved bodies. |

For Task 1 Step 2, the operative instruction is the explicit rule at Revision 3 lines 55-58:
extract and diff only the bytes between `PRESERVED-BODY-START` and `PRESERVED-BODY-END`. The later
`header-stripped copies` shorthand does not include the delimiters or any appended manifest material.

### Execution authority and stops

Claude is approved to execute **Task 1 Steps 1-3 only**:

1. create the six tracked preservation records with the specified provenance/authority headers and
   preserved-body delimiters;
2. verify the six extracted bodies byte-for-byte and record their line counts; and
3. run the narrow docs test and require a green result.

At **Task 1 Step 4**, stop and request the operator's explicit authorization for the six-file
artifact custody commit. This approval does **not** authorize either commit, remediation work, or
scheduling of slices A-F. After the custody commit is separately authorized and landed, plan
execution may resume with Tasks 2-5 under their stated review checkpoints; Task 5 Step 5 and Step 6
remain mandatory final-review and operator-authorization stops.

## Final ruling

**Revision 3 is the approved closure plan. No further plan revision or design spec is required.**
The implementation lane may begin within the bounded authority above. All checkboxes remain evidence
gated by their stated verification commands and the repository's checkbox protocol.

---

## `_v2` forward-amendment review — 2026-08-12

**Artifact:** `.superpowers/sdd/a2a-not-shipped-closure-plan_v2-DRAFT.md`  
**Artifact SHA-256 reviewed:** `ffcdce4b83358cb2f5ce4b29a097a0488e92f62db2c2a31ab1654d4df961a066`  
**Decision:** **CHANGES REQUIRED — do not execute the tooling or custody PR yet**

The amendment's technical direction is accepted:

- use a separate two-file prerequisite tooling PR;
- apply exact-path `-text` only to the six immutable preserved records;
- keep the living `_v2` plan under normal LF normalization;
- configure the hook with `--markdown-linebreak-ext=md`, subject to execution proof;
- stage real blobs, never `git add -N`, and hash only after checked `git cat-file` retrieval;
- do not run `git diff --cached --check` against the six records whose intentional Markdown hard
  breaks make that Git builtin intrinsically incompatible; and
- carry six preserved records plus one live `_v2` plan in the custody PR.

Those decisions should not be reopened. The draft still is not an executable live plan.

### A1. [P0] `_v2` contains no checkbox ledger or executable tasks

Repository search finds **zero** `- [ ]` or `- [x]` entries in the proposed live successor. Lines
97-104 say to add an authoritative ledger, but do not add one. Lines 118-126 are a narrative
sequence without commands, expected results, gates, commit allowlists, or review stops. This repeats
the exact `AGENTS.md:76` defect the amendment exists to cure.

**Required correction:** make `_v2` the consolidated executable successor, following the existing
`archive/evidence-handoff-risk-bearing-slice-implementation_v2.md` precedent. It must contain:

- an authoritative checkbox ledger for the historical Task 1 Steps 1-3. A historical box may be
  `[x]` only if its text records the limited evidence actually obtained (working-tree body equality
  or the 43-test result) and expressly does **not** call that committed custody;
- unchecked, command-level tasks for the tooling prerequisite, merge/update checkpoint, seven-file
  reconstruction, staging/index verification, custody authorization, commit/push/PR, and later
  committed-blob manifest work;
- the unchanged Tasks 2-5 copied into the live plan with their boxes open, updated only where paths,
  gates, or the live plan version necessarily changed; and
- a Definition of Done that distinguishes the initial custody PR from eventual M17 closure.

Do not create `_v3`: this `_v2` draft is not approved or pinned and may be revised in place.

### A2. [P0] The prerequisite tooling PR is a proposal, not an executable task

The draft says execution must prove the hook flag, but names no probe, command, expected result,
branch, gate set, status allowlist, or authorization boundary. It also says only to append attributes,
while the existing `.gitattributes:1-7` comment would become false: normalization would no longer
cover *all* text files and the repository would contain intentional CRLF exceptions.

**Required correction:** define the prerequisite task completely:

1. Use a dedicated Claude worktree and `agent/claude/a2a-audit-custody-tooling`, created from freshly
   fetched `origin/main`.
2. Modify exactly `.gitattributes` and `.pre-commit-config.yaml`. Update the `.gitattributes`
   explanatory comment as well as adding the six exact `-text` paths.
3. Use an uncommitted scratch/fixture probe to prove both properties: an exact-path CRLF blob remains
   CRLF in the index, and a `.md` file with intentional two-space breaks is unchanged by the configured
   hook. Check command return codes before hashing; remove the probe and prove it is absent from the
   final status.
4. Require `git check-attr` to report `text: unset` for all six paths while `_v2` remains normal text
   with LF normalization.
5. Run the relevant hygiene/config gates, the narrow docs test, Ruff, and a non-vacuous whitespace
   check over the two tracked config edits. State every command and expected exit code.
6. Stop for explicit operator authorization before commit/push/PR; require an exact two-path status
   and wait for the PR to merge before touching the custody branch.

### A3. [P0] The index-blob gate does not yet prove its stated invariant

Lines 80-91 show safe blob retrieval, but omit the exact source-to-destination map, exact staged path
allowlist, delimiter-count check, byte-for-byte extraction procedure, and proof that the hook left the
working tree unchanged. Rehashing the index after a hook is insufficient by itself: a hook can modify
the working file while the old staged blob remains unchanged.

**Required correction:** the custody task must require, in order:

- freshly merged tooling `main`, then `git check-attr` results for six preserved files and `_v2`;
- exact reconstruction of six preserved records plus the approved live `_v2`;
- actual staging and equality of `git diff --cached --name-only` to the seven-path allowlist;
- exactly one real start-marker line and one real end-marker line in each preserved index blob;
- byte-for-byte comparison of each extracted index region to its named ignored source, recording full
  SHA-256, byte count, and `wc -l` count;
- a pre-hook status and working/index hash snapshot, the configured all-files hook with exit 0, an
  identical post-hook status, no unstaged diff for the seven paths, and the same index hashes;
- `git diff --cached --check` scoped to the normal-text `_v2` only (not the six immutable records),
  with the ordinary repository whitespace gate retained for later non-preserved Tasks 2-5; and
- final exact seven-path status/diffstat followed by the operator-authorization stop.

No source comparison may depend on a hash-producing pipeline or an unchecked producer. The plan must
name where the ignored authoritative sources are read from; they are not present automatically in a
fresh worktree.

### A4. [P1] The uncommitted v1 wrapper needs a static historical header before it freezes

The approved v1 **body** is immutable, but its proposed tracked wrapper has never been committed. Its
current header says Revision 3 is the current authority and contains mutable execution-state prose;
both become stale as soon as `_v2` is approved or Tasks 2-5 later run.

Before the custody commit, finalize the outside-the-delimiters v1 header as static history: v1 was the
approved Revision 3 plan, is superseded by live `_v2`, and current execution state lives only in
`_v2`. Do not alter a byte inside v1's preserved region. After the custody commit, the entire tracked
v1 record is frozen. The tracked `_v2` header must carry the final approval disposition, and the
closure-review wrapper must identify `_v2` as the latest disposition.

### A5. [P1] Future ownership must retain both plan versions

Line 116 says `PRODUCT_OWNED_DOCS` gains `_v2` “not v1.” That conflicts with the plan-versioning
precedent and with v1's classification as a product-owned plan. The existing risk-slice v1/v2 pair is
listed in `PRODUCT_OWNED_DOCS` and in the pool's product-owned-document section
(`test_open_work_pool_hygiene.py:226-227`; product pool lines 81-82).

When Tasks 2-5 eventually run:

- the current-state A2A row must point to live `_v2`;
- both historical v1 and live `_v2` belong in the product-owned-document list and
  `PRODUCT_OWNED_DOCS`;
- the scoping contract remains the linked spec addition; and
- adding v1, v2, ownership entries, allowlist entries, and any chosen links remains one atomic green
  docs-test cycle.

The row may label v1 historical or reference it without making it the current execution target, but
v1 must not be reclassified as non-product-owned merely because `_v2` exists.

## `_v2` draft ruling

Return a revised `_v2` draft addressing A1-A5. The prerequisite tooling PR split, exact six-file
`-text` list, normal-LF `_v2`, Markdown-aware hook direction, incompatibility of Git's whitespace
checker with the six preserved records, and seven-document custody shape are approved. Nothing in
this review authorizes file staging, either commit, either push/PR, Tasks 2-5, M17 closure, or A-F
scheduling.

---

## `_v2` revised-draft re-review — 2026-08-12

**Artifact:** `.superpowers/sdd/a2a-not-shipped-closure-plan_v2-DRAFT.md`  
**Artifact SHA-256 reviewed:** `65eb8f7422023d1b742069e42ab3d572434bf129708873d8e518714114aa9c64`  
**Decision:** **CHANGES REQUIRED — one more in-place `_v2` revision; do not execute**

Mechanical verification confirms 4 checked and 37 open boxes. A4 is resolved: v1's preserved body
is immutable while its not-yet-committed wrapper is finalized as static history, and `_v2` becomes
the live status/ledger. A5 is resolved: both v1 and `_v2` remain product-owned, while only `_v2` is
the live execution target. The explicit authoritative ignored-source directory also resolves the
fresh-worktree source ambiguity.

### B1. [P0] A1 remains open: Tasks 2-5 were summarized, not carried forward

Lines 178-194 contain one checkbox per original task and say the tasks were copied. They were not.
The Revision 3 plan's RED/GREEN steps, exact 20-obligation mapping, adjacent-custody clauses, gate
commands, review stops, final authorization boundary, and detailed Definition of Done are absent.
An implementer cannot execute Tasks 2-5 from the live `_v2` contract without reopening frozen v1,
and four summary bullets cannot authoritatively track the many original steps.

**Required correction:** copy the full executable Tasks 2-5 and their Definition of Done into `_v2`,
keeping every step open and changing only the version-dependent paths/ownership and the amended
custody/whitespace gates. Preserve the exact obligation table and all commands already approved in
Revision 3. The current-state row links live `_v2`; the ownership list and `PRODUCT_OWNED_DOCS`
contain scoping, historical v1, and live `_v2` atomically.

Also correct the historical ledger:

- line 37 calls the six candidates “tracked records,” but `git status` reports all six as `??`. The
  checked claim must say **untracked candidate records created at tracked destinations**;
- VOID Step 3c and superseded Step 4 must be non-checkbox historical dispositions. Leaving them as
  permanently uncheckable `[ ]` items makes the live ledger look incomplete forever.

### B2. [P0] A2 remains open: the scratch probe is not runnable and can false-pass

The purported exact probe creates `...independent-audit.md.probe`, which does **not** match the exact
`...independent-audit.md -text` attribute. It then uses unresolved placeholders
`<probe-at-an-exact--text-path>` and `<md-with-hard-breaks>`. The Python command merely prints
`False` but still exits zero, and `echo "rc=$?"` records a failing hook without requiring success.
The broad `git reset` cleanup is also not an exact-path cleanup contract.

**Required correction:** use one temporary file at an actual future preserved `.md` path, containing
CRLF plus intentional two-space Markdown breaks. Stage that exact path; retrieve its index blob with
a checked producer return code; make the Python assertion exit nonzero unless CRLF is present; run
the hook and explicitly require exit 0; compare pre/post working bytes; then remove only that exact
path from index and working tree. The final two-path status must prove cleanup.

Replace every placeholder with literal commands/paths. `git check-attr` must query both `text` and
`eol`, expecting `text: unset` for the six exceptions and `text: auto`, `eol: lf` for `_v2`.

### B3. [P0] A3 remains open: the custody verification lacks the executable map and commands

Task 1D states the right assertions but still omits:

- the six exact ignored-source → tracked-destination mappings;
- the literal seven-path staging/allowlist command;
- the delimiter extraction/comparison command;
- literal full-digest/byte/line evidence commands;
- the pre/post status and working/index hash comparison commands; and
- the scoped `_v2`-only cached whitespace command.

Add the exact map and commands. After each verified checkbox edit to tracked `_v2`, restage `_v2`
before taking the pre-hook snapshot; otherwise the ledger update itself creates the unstaged change
that Task 1D Step 5 forbids. Post-hook proof must explicitly compare **working-file hashes as well as
index hashes**, plus require no unstaged diff for all seven paths.

Task 1B must also name the non-interactive update command and require the custody branch's merge base
and behind count to equal fresh `origin/main` before reconstruction.

### B4. [P0] The post-custody manifest has no valid commit topology

Task 1E commits/pushes seven records. Task 1F then modifies the tracked closure-review wrapper by
appending the manifest, but specifies no second commit, path allowlist, authorization, push, or PR
state for that modification. Part 1's DoD nevertheless requires the digests to be recorded. The
manifest cannot be present in the custody commit whose SHA it records, and appending it also changes
one of the seven files after that baseline.

Choose and encode one non-circular topology:

1. **Recommended for this preservation-only PR:** the first commit is the seven-record custody
   baseline; report its SHA externally and defer the tracked manifest to the already-open Task 5
   closure commit. Part 1 DoD then requires verified committed blobs but not an already tracked
   manifest; or
2. define a separately reviewed and operator-authorized follow-up commit with an exact allowlist for
   the manifest/ledger changes, explicitly labeling all hashes as hashes of the first custody commit.

Do not put commit/push/PR into a checkbox that would have to be checked before the command ran in
order to appear in that same commit. Track only evidence that can truthfully exist before the commit;
record the resulting commit/PR as external evidence or in a later authorized ledger update.

## Revised-draft ruling

Return the same `_v2-DRAFT` with B1-B4 corrected. A4/A5 are closed. The source directory, tooling-PR
split, six exact `-text` exceptions, LF-normalized live `_v2`, Markdown-aware hook, seven-document
custody shape, and v1/v2 ownership ruling are settled. No staging, commit, push, PR, Tasks 2-5, M17
closure, or remediation scheduling is authorized.

---

## `_v2` 52-checkbox re-review — 2026-08-12

**Artifact:** `.superpowers/sdd/a2a-not-shipped-closure-plan_v2-DRAFT.md`  
**Artifact SHA-256 reviewed:** `4fce87473bb41e07c11ddab9df9e738e1e739254db9d9f117ac64615d3c4d39f`  
**Decision:** **CHANGES REQUIRED — mechanical correction only; do not execute**

Verified counts: 404 lines, 10 task headings, 20 obligation rows, 4 checked historical boxes, and
48 open boxes. B4 is resolved: the seven-record commit is the non-circular custody baseline, its SHA
and PR are external evidence, and the tracked manifest is deferred to Task 5. The historical ledger
now describes the six files truthfully as untracked candidates and removes VOID/superseded items
from checkbox state.

The remaining defects are executable-command and exact-fidelity defects; no custody or product
decision is reopened.

### C1. [P0] Task 1D still cannot execute: its shell map and variables do not exist

The Markdown table defines a conceptual map, but no shell command assigns `SDD`, `SRC`, or `DST`.
Task 1D Step 2 therefore runs `git cat-file blob ":$DST"` and opens `"$SDD/$SRC"` with undefined
variables. Step 3 still contains the literal placeholder `git add -- <_v2>`. Its later `$P` index
hash command also has no loop that assigns `P`.

`SEVEN` is said to be reused by later steps, but shell arrays do not survive separate shell/tool
invocations. The staged-set proof additionally uses process substitution around
`git diff --cached --name-only | sort`; the producer's failure is not captured, contradicting the
plan's checked-producer rule.

**Required correction:** provide one literal, self-contained verification script (or repeat complete
definitions in every command block) that:

- assigns the absolute `SDD` path;
- defines parallel six-entry `SOURCES`/`DESTINATIONS` arrays and the seven-entry `SEVEN` array;
- checks array lengths before looping;
- stages literal paths, writes actual/expected path lists to temporary files with each producer's
  return code checked, sorts those files, then compares them;
- loops by index to assign `SRC` and `DST` before checked blob retrieval and extraction;
- uses the literal `_v2` destination instead of `<_v2>`;
- computes and saves working/index hashes for every `P` with checked commands; and
- repeats or sources the definitions wherever a later step runs in a fresh shell.

The existing extraction envelope was independently tested against five current candidate records
and succeeds when the wrapper is constructed with the required separator newline. State the exact
envelope bytes so reconstruction cannot omit that separator.

### C2. [P0] Task 5's manifest command has an undefined path and incomplete evidence contract

Task 5 Step 4 runs `git show "<custody-commit>:$P"`, but never defines or loops over `P`; it also does
not say explicitly whether the manifest covers six preserved records or the full seven-path custody
baseline. The Part 2 DoD says only that a manifest is present.

**Required correction:** define the exact custody-commit SHA input and the same literal seven-path
array, loop over all seven baseline paths, check `git show`, hash, and line-count command return
codes, and record path + custody SHA + full SHA-256 + byte count + line count for each. State that
record 7's digest is its custody-baseline digest even though live `_v2` is later updated.

### C3. [P1] The prerequisite branch command does not create the required worktree

Task 1A says “dedicated Claude worktree” but executes only `git checkout -B`, which switches/resets a
branch in whichever worktree is current. It neither creates nor identifies the required separate
tooling worktree and can overwrite an existing local branch pointer.

Use an explicit sibling path and `git worktree add -b agent/claude/a2a-audit-custody-tooling ...
origin/main` after fetch, with preflight checks that neither path nor branch is already occupied.
In Task 1B, the known zero-commit custody branch must fast-forward to merged `origin/main`; remove the
open-ended rebase fallback. If `--ff-only` fails, stop for review rather than changing topology.

### C4. [P1] The carried-forward contract still contains abbreviations and one self-referential commit box

Task 2 uses `…/specs` and `…/plans` rather than the three literal repository paths, despite the claim
that the plan has no placeholders. Task 3 also dropped the approved requirement to link the scoping
contract and reference every review/audit record by backticked path, and its Priority-test shorthand
does not restate the exact one-column/value/sole-HIGH/no-inline-label assertions.

Replace those abbreviations and restore those explicit assertions. Task 5 Step 6 must mirror Task
1E: make the operator-authorization stop the checkbox, then place the resulting closure commit as
external evidence/non-checkbox action. A commit/push action cannot truthfully be checked inside the
same commit that is supposed to carry that checkbox.

## 52-checkbox draft ruling

Return the same `_v2-DRAFT` with C1-C4 corrected. B4 and the prior A4/A5 rulings are closed. All
architecture, custody topology, six-file `-text` scope, seven-record baseline, ownership, priority,
severity, and deferral decisions remain approved and must not be revisited. Nothing here authorizes
the tooling worktree, staging, either commit, either push/PR, Tasks 2-5, M17 closure, or remediation
scheduling.

---

## `_v2` command-fidelity re-review — 2026-08-12

**Artifact:** `.superpowers/sdd/a2a-not-shipped-closure-plan_v2-DRAFT.md`  
**Artifact SHA-256 reviewed:** `cb8e041e7a8b3a47c435b0fa46b3c604b90a4b7be7350c7f8ef006a048a58f43`  
**Decision:** **CHANGES REQUIRED — two command-level corrections; do not execute**

Mechanical verification confirms 598 lines, 10 task headings, 20 obligation rows, 4 checked
historical boxes, and 48 open boxes. All eight Bash fences pass `bash -n` under Git Bash. Direct byte
inspection finds 598 CRLF pairs and **zero** lone CR, NUL, or other control bytes. The only runtime
substitution is the custody-commit SHA that cannot exist until Task 1E; it is not an unresolved
design placeholder.

C3 is resolved: Task 1A now creates an explicit sibling worktree from fetched `origin/main`, and
Task 1B permits only `git merge --ff-only`, with a mandatory review stop on failure. C4 is resolved:
Tasks 2-5 use literal product paths, restore the scoping/backticked-review/Priority contracts, and
move the closure commit outside checkbox state. C1's source/destination arrays, seven-path staging
set, literal `_v2` path, envelope, and fresh-shell rule are present. C2's seven-path manifest scope
and custody-baseline `_v2` semantics are present.

Two execution defects remain. They are mechanical and do not reopen any settled architecture,
custody, ownership, severity, priority, or deferral decision.

### D1. [P0] Task 1D still permits false evidence from unchecked producers

The block declares that no comparison may use an unchecked producer, but several producers used by
the comparisons still have no return-code gate:

- both `sort ... -o ...` commands and the expected-list `printf` feeding the staged-set `diff`;
- the pre-hook and post-hook **index** `sha256sum` commands; and
- the post-hook `git status --short` snapshot.

The fixed `/tmp` filenames make this material: a failed producer can leave or compare incomplete or
stale evidence. Add and require the return code immediately after every one of those commands. The
working-file hash commands and `git cat-file` retrievals already do this correctly. A scratch
directory created for the run is preferable, but checked producers plus deliberate truncation and
exact cleanup are sufficient; do not widen this into a topology change.

### D2. [P0] Task 5's manifest loop is syntactically valid but cannot terminate

The final `printf` and `i=$((i + 1))` were silently joined onto one physical line. Bash parses that
line, which is why `bash -n` passes, but the assignment becomes an extra argument to `printf`; `i`
remains zero and the loop repeats forever while emitting malformed rows. Put the increment on its
own line.

The same block reintroduces the prohibited hash pipeline:

```bash
h=$(sha256sum "/tmp/manifest_blob_$i.bin" | cut -d' ' -f1); rc=$?
```

That checks `cut`, not `sha256sum`. Write `sha256sum` output to a temporary file, require its return
code, then parse and validate the full digest without a hash-producing pipeline. Also capture and
require the return code of `wc -c`; the `git show` and `wc -l` checks are already correct.

## Command-fidelity ruling

Return the same `_v2-DRAFT` with D1-D2 corrected and rerun both `bash -n` **and** a semantic scan of
each loop body for a standalone increment and checked evidence producers. C3/C4 and the substantive
parts of C1/C2 are closed. Nothing in this review authorizes worktree creation, staging, either
commit, either push/PR, Tasks 2-5, M17 closure, or remediation scheduling.

---

## `_v2` digest-parse re-review — 2026-08-12

**Artifact:** `.superpowers/sdd/a2a-not-shipped-closure-plan_v2-DRAFT.md`  
**Artifact SHA-256 reviewed:** `94fafdf81b5e8b6db5cddc30ca0d9dc94a4ed8a68c22cf006c03aabb62a9bd60`  
**Decision:** **CHANGES REQUIRED — one final digest-parse correction; do not execute**

Mechanical verification confirms 607 lines, 10 task headings, 20 obligation rows, 4 checked
historical boxes, and 48 open boxes. All eight Bash fences pass `bash -n` under Git Bash. All four
loop increments are standalone. Direct byte inspection finds 607 CRLF pairs and zero lone CR, NUL,
or other control bytes. Repository search finds no `sha256sum | ...` pipeline.

D1 is resolved completely: both staged-set `sort` calls, the expected-list `printf`, both index-hash
producers, and the post-hook status producer now capture and require distinct return codes. D2's
standalone increment, checked `sha256sum`, checked `wc -l`, and checked `wc -c` are also correct.

### E1. [P0] The replacement digest parser is still unchecked and unvalidated

Task 5 now writes checked `sha256sum` output to a file, but the next command is:

```bash
h=$(cut -d' ' -f1 "/tmp/manifest_hash_$i.txt")
```

The `cut` return code is discarded, and the plan never proves that `h` is a full SHA-256. If `cut`
fails, the loop still records an empty digest in the custody manifest. This is the one clause from
D2's required "parse and validate the full digest" correction that remains open.

Use a no-pipeline parse with an immediate return-code check, then require exactly 64 hexadecimal
characters before writing the manifest row. For example:

```bash
read -r h _ < "/tmp/manifest_hash_$i.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: parse hash $P"; exit 1; }
[[ "$h" =~ ^[0-9a-fA-F]{64}$ ]] || { echo "FAIL: invalid SHA-256 $P"; exit 1; }
```

## Digest-parse ruling

Return the same `_v2-DRAFT` with E1 corrected. No other plan content needs to change. D1 and every
other part of D2 are closed, as are C3/C4 and the substantive C1/C2 decisions. Nothing in this
review authorizes worktree creation, staging, either commit, either push/PR, Tasks 2-5, M17 closure,
or remediation scheduling.

---

## `_v2` final approval — 2026-08-12

**Artifact:** `.superpowers/sdd/a2a-not-shipped-closure-plan_v2-DRAFT.md`  
**Approved artifact SHA-256:** `8daeb1dd340280bf80903e48db52352a8cea6fa6abf6fe3e982690ea339116f0`  
**Decision:** **APPROVED FOR BOUNDED EXECUTION — Task 1A Steps 1-7 only**

E1 is resolved exactly as ruled. Task 5 parses the checked `sha256sum` output with Bash `read`,
requires the `read` return code, and validates the result against `^[0-9a-fA-F]{64}$` before the
digest can enter the manifest.

Fresh reviewer verification on the approved bytes produced:

- 609 lines, 10 task headings, 20 obligation rows;
- 52 checkboxes: 4 checked historical facts and 48 open steps;
- eight Bash fences, all passing `bash -n` under Git Bash;
- four standalone loop increments and no `cut` or hash-producing pipeline;
- 609 CRLF pairs with zero lone CR, NUL, or other control bytes; and
- a functional parser probe where a short digest was rejected, a real 64-hex digest was accepted,
  and an empty digest file failed at `read` before regex validation (`11 / 0 / 10`, overall exit 0).

All A1-A5, B1-B4, C1-C4, D1-D2, and E1 findings are closed. The approved prerequisite-tooling split,
six exact `-text` records, normal-LF live `_v2`, seven-record custody baseline, non-circular manifest
topology, ownership, priority, severity, deferral, and no-remediation/no-scheduling rulings remain
the contract.

### Execution boundary

Claude may execute **Task 1A Steps 1-7 only**: create the named dedicated tooling worktree, modify
exactly `.gitattributes` and `.pre-commit-config.yaml`, run the literal probe and gates, and stop with
the exact two-path status evidence required by Step 7.

This approval does **not** authorize Task 1A Step 8, any commit, push, PR, Task 1B or later work,
Tasks 2-5, M17 closure, or remediation scheduling. At the Step 7 stop, explicit operator
authorization is required before the tooling commit/push/PR.

---

## Remote-publication readiness check — 2026-08-12

**Decision:** **NOT READY TO PUSH THE DOCUMENTS YET — prerequisite tooling is still unexecuted**

Fresh read-only inspection found no local `agent/claude/a2a-audit-custody-tooling` branch or tooling
worktree. The locally fetched `origin/main` still has the pre-amendment `.gitattributes` policy and
no `--markdown-linebreak-ext=md` hook argument. The custody worktree remains at `e5f7e33`, `0 0`
against its locally fetched `origin/main`, with exactly six untracked candidate records and no staged
content. The approved live `_v2` record has not yet been reconstructed there.

Therefore the repository is ready only for the already-approved Task 1A Steps 1-7 preparation. The
publication sequence remains: prepare and review the two-file tooling change; obtain operator
authorization for its commit/push/PR; wait for that PR to merge; execute Task 1B through Task 1D;
then obtain a separate operator authorization for the seven-record custody commit/push/docs PR.

---

## Task 1A Step 7 implementation review — 2026-08-12

**Worktree:** `D:/Projects/Development/Python/optimus-cost-agent-wt-claude-tooling`  
**Branch:** `agent/claude/a2a-audit-custody-tooling`  
**Decision:** **TECHNICAL DIFF APPROVED; COMMIT/PUSH/PR NOT YET AUTHORIZED — forward amendment and
ledger correction required**

Fresh reviewer inspection confirms the two-file implementation is correct:

- branch and `origin/main` are both `e5f7e339`, with `0 0` divergence and the same merge base;
- the index contains exactly `.gitattributes` and `.pre-commit-config.yaml`;
- there are no unstaged or untracked paths;
- staged blob IDs are `b381b75eaf169b13a2b7b69b9c8b91d1210a2ef5` and
  `0b1005e01b4beb1f00c1aa9674506988e668951b`;
- all six exact preserved paths report `text: unset`, while live `_v2` reports `text: auto` and
  `eol: lf`;
- `git diff --cached --check` passes; and
- independent reruns pass: check-yaml, check-toml, trailing-whitespace, the narrow docs contract
  (`43 passed`), and Ruff (`All checks passed`). The hooks leave the staged hashes/status unchanged.

No change to the staged two-file diff is required.

### Blocking process findings

1. **[P0] The authoritative execution ledger still has all seven Task 1A boxes open.** Under
   `AGENTS.md`'s checkbox protocol, the prose report cannot establish completion. Evidence supports
   carrying Steps 1-3 and 5-7 forward as checked historical facts, but the on-disk plan currently
   records none of them.
2. **[P0] Step 4 did not run the approved command.** The literal `/tmp`/native-Python boundary failed,
   and execution substituted a repo-relative scratch directory without stopping for amendment.
   The substitute appears technically equivalent and its reported result is consistent with the
   final attributes/hook behavior, but plan fidelity forbids retroactive completion of the stated
   checkbox from a different command.

Because approved `_v2` is pinned, correct this forward-only in
`.superpowers/sdd/a2a-not-shipped-closure-plan_v3-DRAFT.md`; do not edit `_v2` command text. The
amendment is mechanical only:

- carry the settled plan unchanged;
- record Steps 1-3 and 5-7 as checked historical evidence, with Step 4 still open;
- replace cross-runtime `/tmp` paths in Task 1A Step 4 and Task 1D with one explicit repo-relative
  scratch directory, including preflight non-existence, checked creation, exact cleanup, and final
  absence proof;
- add the observed `uv sync --extra dev` prerequisite before the first pre-commit invocation in a
  fresh worktree, and ensure the custody worktree has the same prerequisite before Task 1D; and
- rerun amended Step 4 literally, then check Step 4 only after it passes.

The report's claim that Task 5 has the same native-Python boundary is incorrect. Task 5's `/tmp`
files are consumed by Git Bash tools (`sha256sum`, `read`, and `wc`), not native Python; do not widen
the amendment to Task 5 absent new evidence.

After `_v3` is reviewed and amended Step 4 passes, return to the Step 7 authorization stop. Nothing
in this review grants the tooling commit, push, or PR; nor does it authorize Task 1B or later work.

---

## `_v3` forward-amendment review — 2026-08-12

**Artifact:** `.superpowers/sdd/a2a-not-shipped-closure-plan_v3-DRAFT.md`  
**Artifact SHA-256 reviewed:** `5f9fe3ea73f96d9bf98602e9fb056f80e2c6bf578f66a8fcf4ac29b6effbd825`  
**Decision:** **CHANGES REQUIRED — revise `_v3` in place; tooling commit/push/PR remains withheld**

Fresh verification confirms 677 lines, 10 task headings, 20 obligation rows, and 52 checkboxes
(11 checked / 41 open). All eight Bash fences pass `bash -n` under Git Bash. Direct byte inspection
finds 677 CRLF pairs and zero lone CR, NUL, or other control bytes. The tooling worktree still has
exactly the same two staged paths, no unstaged/untracked content, no scratch leftovers, and a clean
cached whitespace check. The two-file tooling diff remains technically approved and needs no edit.

The amendment correctly establishes the `/tmp`/native-Python defect and correctly leaves Task 5's
pure-Bash `/tmp` use unchanged. It does not yet satisfy the forward-version or scratch-safety
contract.

### F1. [P0] A live `_v3` makes the custody baseline eight records, but the plan still ships `_v2`

The draft calls itself the live successor while every downstream path remains byte-identical to
`_v2`. Its source map writes “this document” to the `_v2.md` destination; Task 1C still declares
`_v2` live; Task 1D stages `V2_PATH` as record 7; Tasks 2-3 link/own `_v2` as live; Task 5 hashes
seven records and later edits `_v2`; and the Definition of Done still names `_v2` live.

That violates the forward-only version rule. Once `_v3` exists, `_v2` is immutable history and
must not be silently overwritten or dropped. The custody baseline becomes:

1. the six existing preserved records;
2. historical, normal-text `_v2`; and
3. live, normal-text `_v3`.

Revise all version-dependent plumbing consistently:

- map record 7 to the ignored `_v2-DRAFT` source and tracked `_v2.md` historical destination;
- map record 8 to this `_v3-DRAFT` source and tracked `_v3.md` live destination;
- state v1 and `_v2` are history and `_v3` is the live execution ledger;
- query `check-attr` for both normal-text plan versions; reopen Task 1A Step 5 until that literal
  eight-path check is rerun;
- reconstruct, stage, hash, and custody **eight** records in Tasks 1C-1E; Task 1D must name literal
  `V2_PATH` and `V3_PATH`, use an eight-path allowlist, and scope the cached whitespace check to both
  normal-text plans;
- atomically add scoping + v1 + `_v2` + `_v3` to product ownership/`PRODUCT_OWNED_DOCS`, while the
  current A2A row links live `_v3`;
- make Task 5's manifest cover all eight custody-baseline blobs, treating record 8 as `_v3`'s
  baseline digest; the later closure commit edits `_v3`, not frozen `_v2`; and
- update the Definition of Done and every remaining “record 7/live `_v2`” statement accordingly.

These are version-plumbing changes only. Do not alter the settled obligations, severity, priority,
slice ownership, deferral, or no-remediation rulings.

### F2. [P0] The amended scratch commands omit the explicitly required safety contract

The prior ruling required preflight non-existence, checked creation, exact cleanup, and final absence
proof. Task 1A Step 4 instead uses unchecked `mkdir -p .probe_scratch` and unchecked
`rm -rf -- "$P" .probe_scratch`; Task 1D similarly uses unchecked `mkdir -p "$SCRATCH"` and unchecked
`rm -rf -- "$SCRATCH"`. Both accept or delete a pre-existing directory, and neither command proves
cleanup succeeded. This contradicts the prose that every failure exits nonzero.

Reopen Task 1A Steps 4 and 7. For Step 4, require absence before creation, check creation, check each
cleanup operation, avoid recursive deletion where the three exact scratch files can be removed
explicitly, and prove both the probe path and scratch directory are absent afterward. For Task 1D,
require the same preflight and checked creation; before recursive cleanup, resolve and verify the
exact scratch directory is the intended repo-relative directory, then check deletion and final
absence. A failure must stop without claiming the corresponding checkbox.

After revising `_v3`, rerun literal Steps 4, 5, and 7 and update only those boxes on passing evidence.
The previously verified Steps 1-3 and 6 may remain checked. Return for review at Step 7. Nothing in
this ruling authorizes the tooling commit, push, PR, Task 1B or later execution, M17 closure, or any
remediation scheduling.

---

## `_v3` F1/F2 re-review and Task 1A authorization — 2026-08-12

**Artifact:** `.superpowers/sdd/a2a-not-shipped-closure-plan_v3-DRAFT.md`  
**Artifact SHA-256 reviewed:** `86523c4bb6382c758a165b5122e71cc027c9d64874369b2adacac5ee34bd49dd`  
**Decision:** **TASK 1A APPROVED; EXACT TWO-FILE TOOLING COMMIT/PUSH/PR AUTHORIZED BY THE USER'S
CONDITIONAL REQUEST. TASK 1B REMAINS BLOCKED.**

F1 is closed. The plan now consistently defines eight custody records: six preserved records,
historical normal-text `_v2`, and live normal-text `_v3`. The source map, reconstruction, `EIGHT`
allowlists and loops, ownership set, live pool link, manifest, closure-commit ledger, and Definition
of Done all use that topology.

The executed portion of F2 is closed. The reviewer independently reran the literal Task 1A Step 4
block in the tooling worktree: hook passed, cleanup printed `CLEANUP VERIFIED ABSENT`, and the block
exited 0. A fresh eight-path attribute check reports `text: unset` for the six preserved records and
`text: auto` / `eol: lf` for both `_v2` and `_v3`. Final status remains exactly:

```text
M  .gitattributes
M  .pre-commit-config.yaml
```

There are no unstaged, untracked, probe, or scratch paths. The staged blob IDs remain
`b381b75eaf169b13a2b7b69b9c8b91d1210a2ef5` and
`0b1005e01b4beb1f00c1aa9674506988e668951b`; `git diff --cached --check` passes. All eight plan Bash
fences pass `bash -n`. The ledger contains 53 boxes (11 checked / 42 open) because Task 1C now has a
separate historical `_v2` reconstruction step; the obligation count remains 20.

### Authorized Task 1A Step 8 scope

Claude may now, on `agent/claude/a2a-audit-custody-tooling`:

1. re-run `git status --short` and reject any path other than the two above;
2. commit exactly `.gitattributes` and `.pre-commit-config.yaml`;
3. push that branch;
4. open the prerequisite tooling PR against `main`; and
5. report the commit SHA and PR URL, then wait for merge.

No document-custody files, pools, tests, source files, or `_v3` draft belong in this tooling commit.
This authorization does not extend to Task 1B.

### G1. [P1] One future Task 1D cleanup guard still needs correction before Task 1B

Task 1D says it verifies the *exact* intended scratch directory, but its command only checks that the
resolved path matches `*/.custody_scratch`. That suffix accepts the same directory name under any
unexpected working directory. The `cd/pwd` substitution's return code is also unchecked, and the
delete uses unresolved relative `$SCRATCH` rather than the validated absolute path.

Revise `_v3` in place before Task 1B: capture and check the repository root via `pwd -P`; capture and
check the scratch directory via `cd "$SCRATCH" && pwd -P`; require exact equality to
`$ROOT/.custody_scratch`; delete the validated absolute path; check deletion; and prove both the
validated absolute path and repo-relative scratch path are absent. Also correct the stale header
phrase saying review still awaits Step 4's rerun, and the scope sentence saying Task 1E was untouched
even though its record count changed from seven to eight.

These are unexecuted future-command/current-state prose corrections. They do not invalidate Task 1A
or the authorized two-file tooling PR. Do not begin Task 1B until the corrected `_v3` is reviewed and
the tooling PR has merged. Nothing here authorizes document custody, Tasks 2-5, M17 closure, or
remediation scheduling.

---

## Prerequisite tooling PR merged — 2026-08-12

**PR:** `https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/131`  
**Head commit:** `b370765fc85516fff0652313fbd221f568a9d3db`  
**Merge commit on `main`:** `e2496ced8580ff0318bf263c5c43eb446bea10e0`  
**Decision:** **TASK 1A COMPLETE; G1 PLAN CORRECTION MAY PROCEED; TASK 1B STILL BLOCKED**

Before merge, GitHub reported exactly two changed files, one commit, base `main`, expected head
`b370765f…`, and `mergeStateStatus: CLEAN`. Required check `clean-environment-recheck` completed
successfully in 1m39s. The GitHub app's merge endpoint lacked permission (403), so the authenticated
GitHub CLI fallback merged with `--match-head-commit b370765f…` and merge-commit method. No branch or
worktree deletion was requested or performed.

Fresh post-merge verification reports PR state `MERGED` at `2026-08-12T11:25:09Z`; remote `main`
points to `e2496ced…`, whose message is `Merge pull request #131 ... tooling: protect A2A audit
records from normalization`.

Claude may now revise `_v3` in place for G1 only: exact resolved scratch-directory equality,
checked resolution, deletion through the validated absolute path, dual absence proof, and the two
stale prose corrections already specified. Return the corrected `_v3` for review. **Do not execute
Task 1B yet.** No document reconstruction, staging, custody commit, Tasks 2-5, M17 closure, or
remediation scheduling is authorized by this checkpoint.

<!-- PRESERVED-BODY-END -->

## Task 5 Step 4 — tracked custody manifest (outside the preserved region)

Every digest below is a hash **of the custody commit** `ec73ba48628c051d07db06f10fa816fac681616c`
(Task 1E's custody commit, later merged to `main` as `cdc0df309b436d6b93dcb3423e82ae4aee1b0d14`),
not of any later working-tree state. Record 7 (`_v2`) is not touched again after Task 1D, and its
digest below matches its current tracked bytes exactly (independently reverified via fresh
`git show HEAD:...`). Record 8 (`_v3`) is the closure plan's own custody-baseline digest as committed;
it legitimately differs from `_v3`'s current working-tree bytes (Tasks 2-5 have since edited `_v3`'s
checkboxes and current-state prose) — that difference is expected, not a mismatch to reconcile.

| # | Path | SHA-256 (of the custody commit) | Bytes | Lines |
|---|---|---|---|---|
| 1 | `docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md` | `af3ccb0f306b7902ac0e7de1aa79c2cd1725b5263d73a110163947ab2c06cf06` | 41108 | 692 |
| 2 | `docs/superpowers/reviews/evidence-handoff-a2a-ledger-sealed-reviewer-findings.md` | `196dc171cf130eae96c3265fc3a26b36c9550389762cd314b1232094e189bb72` | 5107 | 85 |
| 3 | `docs/superpowers/reviews/evidence-handoff-a2a-remediation-scoping-review.md` | `aa89bf21c583f40ecfb0b44c822b1a2d2aa80f2d019e30c103da6f5961559cf9` | 26218 | 468 |
| 4 | `docs/superpowers/reviews/evidence-handoff-a2a-not-shipped-closure-review.md` | `06bafea8f91d86646656a997da34688e12fd6b729c978d72efa9a8f74dc90d8a` | 72592 | 1213 |
| 5 | `docs/superpowers/specs/evidence-handoff-a2a-ledger-remediation-scoping.md` | `c6e62f06a658956b986ca77b697177458da848e0d33984f8ba4d60de8ed4fad9` | 18379 | 313 |
| 6 | `docs/superpowers/plans/archive/evidence-handoff-a2a-not-shipped-closure.md` | `c9724c618338a331121e84b16e59b81e672079b882e236308dab6eea192d8e06` | 20309 | 310 |
| 7 | `docs/superpowers/plans/archive/evidence-handoff-a2a-not-shipped-closure_v2.md` | `6d6c0e6a82dba0317260ba077ccb0874f2dcea5994dfaa220a3f764c77fc3aa2` | 33501 | 609 |
| 8 | `docs/superpowers/plans/archive/evidence-handoff-a2a-not-shipped-closure_v3.md` | `c93c178bf00da99d002e2273bb004f8535f2f1d219375d24f4b2e6bac39f8063` | 105574 | 1657 |

Row 4 is this record's own custody-commit digest (`docs/superpowers/reviews/evidence-handoff-a2a-not-shipped-closure-review.md`
at commit `ec73ba48628c051d07db06f10fa816fac681616c`) — it does not and cannot include this
Step 4 section itself, which is later, non-preserved material appended after that commit.
