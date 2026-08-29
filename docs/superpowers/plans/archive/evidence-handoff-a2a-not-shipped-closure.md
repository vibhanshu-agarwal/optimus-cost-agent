# A2A Ledger — Not-Shipped Closure Plan (preserved record)

Preserved from gitignored `.superpowers/sdd/a2a-not-shipped-closure-plan-DRAFT.md` on 2026-08-12.
Audited commit `e5f7e339`. Author: Claude (drafter/implementer). Reviewer: Codex.

**Current authority: historical.** v1 was the approved Revision 3 plan; superseded by `_v2`
(`evidence-handoff-a2a-not-shipped-closure_v2.md`), itself now superseded by live `_v3`
(`evidence-handoff-a2a-not-shipped-closure_v3.md`). Current execution state lives only in `_v3`.

The region between the PRESERVED-BODY markers below is byte-identical to the source and
must not be edited. Any later material (for example a custody manifest) goes **outside** it.

<!-- PRESERVED-BODY-START -->
# A2A Ledger — Declare Not-Shipped, Preserve Audit, Log Findings (REVISION 3, for Codex review)

**Author:** Claude (drafter/implementer this session, per the operator's 2026-08-12 lane assignment)
**Reviewer:** Codex
**Operator ruling:** declare not-shipped, fix M17, defer; *"Ensure none of the audit docs are lost.
The issues should be logged in the backlog pool for evidence handoff and must have an entry in the
table."*
**Prior reviews:** `.superpowers/sdd/a2a-not-shipped-closure-plan-review.md` — R1 CHANGES REQUIRED (11 items, all adopted); R2 CHANGES REQUIRED (4 narrow items, all adopted here).
**Status:** Revision 3, for review. Authorizes nothing. No remediation, no scheduling of A-F.

All eleven checklist items addressed. Task order follows the review's essential sequence: tracked
custody baseline → atomic pool/ownership changes → obligation/priority projection → cross-document
freshness → full gates and closure.

## 0. Disposition of the review

| Finding | Disposition |
|---|---|
| P0-1 preservation set incomplete; audit misclassified as a spec | **Accepted.** Sealed findings added; audits move to `reviews/`. |
| P0-2 committed-blob digests impossible in task order | **Accepted.** Two custody phases with a named custody commit. |
| P0-3 link/ownership/allowlist split across broken checkpoints | **Accepted.** Each link is one atomic mutation. |
| P0-4 "safe deferral" overstates the evidence | **Accepted, and it corrects a claim I made.** Verified: `evidence-handoff-lifecycle` and `evidence-handoff-service` are declared `[project.scripts]`. Bounded language adopted verbatim. |
| P1-5 adjacent custody not explicit; stale Optimus Redis reference | **Accepted.** Verified pool line 1397 says "the A2A ledger's hardened-Redis fallback path"; no such path exists. |
| P1-6 docs-test contract incomplete | **Accepted.** Concrete constants and mappings below. |
| P1-7 "full CI-equivalent" omits CI commands | **Accepted.** Install/build/noneditable stages added. |
| Q1 Priority on both tables | **Yes**, per ruling. |
| Q2 no design spec | **Approved**, and the closure plan is itself tracked. |

## Constraints — verified by inspection, do not re-derive

1. `test_new_pool_links_only_to_explicitly_product_owned_documents` asserts
   `listed_docs == PRODUCT_OWNED_DOCS` **and** `linked_docs <= PRODUCT_OWNED_DOCS`. The
   ownership-section regex matches only `docs/superpowers/{plans,specs}/*.md`.
2. Therefore **only** the scoping contract (spec) and this closure plan (plan) may be markdown-linked
   from the pool. Audits and review chronologies are referenced by **backticked tracked path**.
3. `docs/superpowers/reviews/` is gitignored only for `*-review-checkpoints.md` (`.gitignore:97`).
4. `test_new_pool_has_no_scheduling_plan_numbers`: the product pool may contain no `Plan N` token.
5. Product-pool tests are **in scope now**; their Plan 11.10 protection was scoped to a plan that
   excluded product documents. State this in the commit message.
6. Verified `[project.scripts]`: `evidence-handoff-lifecycle` and `evidence-handoff-service` exist.

## Task 1 — Preserve the audit record; establish the custody baseline

Six records. Classification follows document taxonomy, not link convenience.

| Source (gitignored) | Tracked destination | Linkable? |
|---|---|---|
| `a2a-audit-independent-findings.md` | `docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md` | no — backticked |
| `a2a-audit-SEALED-reviewer-findings.md` | `docs/superpowers/reviews/evidence-handoff-a2a-ledger-sealed-reviewer-findings.md` | no — backticked |
| `a2a-remediation-scoping-proposal-DRAFT.md` (approved Rev 3) | `docs/superpowers/specs/evidence-handoff-a2a-ledger-remediation-scoping.md` | **yes** |
| `a2a-remediation-scoping-review.md` | `docs/superpowers/reviews/evidence-handoff-a2a-remediation-scoping-review.md` | no — backticked |
| this closure plan (approved) | `docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure.md` | **yes** |
| this plan's review chronology | `docs/superpowers/reviews/evidence-handoff-a2a-not-shipped-closure-review.md` | no — backticked |

Each destination is: provenance header → **`<!-- PRESERVED-BODY-START -->`** → byte-identical source
body → **`<!-- PRESERVED-BODY-END -->`** → optional appended material. Task 1 diffs **only the
delimited region**; anything appended later (the Task 5 custody manifest) goes **outside** it. Without
these delimiters "byte-identical body" and "append a manifest" cannot both be true.

**Approval-precedence headers.** Every preserved record whose body carries historical status text
needs its current authority stated in the header, so no two status declarations look coequal:

- **scoping contract** — header states approval at **Revision 3** supersedes the body's
  "DRAFT / for review" text;
- **closure plan** — header identifies the approved revision and review disposition and states that
  this supersedes the body's `Revision N, for review` / `Authorizes nothing` text;
- **both review chronologies** — header states the **latest** disposition, so an opening
  `CHANGES REQUIRED` line from an earlier round cannot be mistaken for the current ruling.

- [ ] **Step 1:** Create all six tracked files with headers.
- [ ] **Step 2:** Verify each body matches its source below the header (`diff` on header-stripped
      copies). Record the per-file line counts.
- [ ] **Step 3:** Run `uv run pytest tests/unit/docs/test_open_work_pool_hygiene.py -q`. Expect green
      — no pool text changed yet.
- [ ] **Step 4:** **Stop. Request operator authorization for the artifact custody commit.** If not
      granted, stop here; do **not** substitute working-tree hashes while claiming committed-blob
      custody.
- [ ] **Step 5:** On authorization, create the custody commit containing exactly these six files.
      Record its SHA as `<custody-commit>`; every later digest uses
      `git show <custody-commit>:<path>`, never a moving `HEAD`.

## Task 2 — Atomic link, ownership, and allowlist for the two linkable documents

One atomic mutation; the repository is never left red at a checkpoint.

- [ ] **Step 1 (RED):** Add both paths to `PRODUCT_OWNED_DOCS` in
      `tests/unit/docs/test_open_work_pool_hygiene.py`:
      `docs/superpowers/specs/evidence-handoff-a2a-ledger-remediation-scoping.md` and
      `docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure.md`.
      Run the narrow docs test; expect FAIL on `listed_docs == PRODUCT_OWNED_DOCS`.
- [ ] **Step 2 (GREEN):** In the same cycle, add both to the pool's
      `## Product-owned documents temporarily hosted in Optimus` section **and** add the pool
      markdown links that reference them. Re-run the narrow docs test to green.
- [ ] **Step 3:** Assert no reviews-directory artifact appears as a markdown link anywhere in the
      pool. Stop for review.

## Task 3 — Rewrite the A2A row, add six slice rows, add Priority to Feature slices

New Feature slices header: `Identity | State | Priority | Scope detail`.

**Priority seeding.** Every row `MEDIUM` **except** `EVIDENCE-HANDOFF-FEAT-CREDENTIAL-LIFECYCLE`,
whose authored **HIGH** moves out of State prose into the Priority cell. Remove the inline
`**HIGH** priority` label so no duplicate remains. The six deferred slices are `MEDIUM` — Severity
expresses security impact, Priority expresses the operator's current scheduling decision.

**A2A row — required content.** Replace `**Closed**`:

- **not shipped / not supported / not trusted**; independent audit at `e5f7e339` returned NOT SOUND,
  17 findings, 3 Critical;
- corrected Git facts: tip **`658042d`** (not `72c3b82`), **25** commits from `8735885`, PR **#128**
  merged `7b5865f` and PR **#129** merged `74f7104` — the row's "no PR opened" is false;
- **code remains merged and the console scripts remain present**;
- the bounded deferral rationale, adopted verbatim from the review:

  > The feature is not on the ordinary Optimus runtime path and lifecycle activation is opt-in by
  > default. However, merged code and installed console entry points remain manually callable. They
  > are unsupported and untrusted and must not be enabled or used for trusted workflows.

- links to the tracked scoping contract and closure plan; backticked paths for the audit records;
- remediation is **scoped but not scheduled**, owned by the six new rows.

**Six new rows**, all `Tracked, Not Yet Scheduled` 2026-08-12, `MEDIUM`, naming obligations and the
order `Pre-A → A → {B, C, D} → E → F`:
`LEDGER-COMPOSITION` (C1,C3,H7,H9,M15) · `LEDGER-INTEGRITY-BOUNDARY` (C2,H13,M16c) ·
`LEDGER-DATAPATH` (H4,H5,H6) · `LEDGER-RUNTIME-BOUNDARY` (H8,M14,M16b) ·
`LEDGER-AUDIT-WIRING` (M16a) · `LEDGER-EVIDENCE-DOD` (H10,H11,H12b).

- [ ] **Step 1 (RED):** Add the six IDs to `PRODUCT_FEATURE_IDS`; replace
      `test_a2a_ledger_reachability_blocker_is_resolved_and_design_is_owned` with
      `test_a2a_ledger_row_records_not_shipped_state`, asserting: not-shipped/not-trusted wording;
      `658042d`; `25`; `PR #128`; `PR #129`; default-off activation; no ordinary Optimus
      ledger/runtime import; the installed-entry-point warning; and **absence** of `**Closed**` and
      of `72c3b82`. Add the Feature-slices Priority contract (exactly one Priority column; every cell
      in `HIGH|MEDIUM|LOW`; Credential Lifecycle the sole non-MEDIUM; no residual body priority
      label). Run narrow docs test; expect FAIL.
- [ ] **Step 2 (GREEN):** Make the edits. Re-run to green.
- [ ] **Step 3:** Verify no `Plan N` token entered the pool. Stop for review.

## Task 4 — Obligations table

Add `## A2A ledger audit obligations` —
`| Obligation | Severity | Owning slice | Status | Priority |`, **20 rows**.

Severity inherits the parent finding: `C*` = CRITICAL; `H*` (including H12a, H12b) = HIGH;
`M*` (including M16a, M16b, M16c) = MEDIUM. Priority `MEDIUM` throughout. Status `Open` for all
except **M17**, which is `Closed` by this plan.

`EXPECTED_OBLIGATIONS` — the exact constant to encode, one row per obligation, no grouping:

| Obligation | Severity | Owning slice | Status |
|---|---|---|---|
| C1 | CRITICAL | `EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION` | Open |
| C2 | CRITICAL | `EVIDENCE-HANDOFF-FEAT-LEDGER-INTEGRITY-BOUNDARY` | Open |
| C3 | CRITICAL | `EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION` | Open |
| H4 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-DATAPATH` | Open |
| H5 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-DATAPATH` | Open |
| H6 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-DATAPATH` | Open |
| H7 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION` | Open |
| H8 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-RUNTIME-BOUNDARY` | Open |
| H9 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION` | Open |
| H10 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-EVIDENCE-DOD` | Open |
| H11 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-EVIDENCE-DOD` | Open |
| H12a | HIGH | program gate contract (pre-work, unscheduled) | Open |
| H12b | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-EVIDENCE-DOD` | Open |
| H13 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-INTEGRITY-BOUNDARY` | Open |
| M14 | MEDIUM | `EVIDENCE-HANDOFF-FEAT-LEDGER-RUNTIME-BOUNDARY` | Open |
| M15 | MEDIUM | `EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION` | Open |
| M16a | MEDIUM | `EVIDENCE-HANDOFF-FEAT-LEDGER-AUDIT-WIRING` | Open |
| M16b | MEDIUM | `EVIDENCE-HANDOFF-FEAT-LEDGER-RUNTIME-BOUNDARY` | Open |
| M16c | MEDIUM | `EVIDENCE-HANDOFF-FEAT-LEDGER-INTEGRITY-BOUNDARY` | Open |
| M17 | MEDIUM | this closure plan | **Closed** |

Counts to assert: 20 rows; 3 CRITICAL, 11 HIGH, 6 MEDIUM; owners distribute
COMPOSITION 5, INTEGRITY-BOUNDARY 3, DATAPATH 3, RUNTIME-BOUNDARY 3, EVIDENCE-DOD 3,
AUDIT-WIRING 1, gate contract 1, closure plan 1.

This table is an **index projecting slice state**, not a second owner.

- [ ] **Step 1 (RED):** Add `EXPECTED_OBLIGATIONS` as an exact `{obligation: (severity, owner)}`
      mapping of all 20; assert the table's rows equal it, that Status is `Open|Closed` with M17 the
      sole `Closed`, that all six slice states are `Tracked, Not Yet Scheduled`, that the parent A2A
      row is not `Closed`, and the Priority contract for this table. Expect FAIL.
- [ ] **Step 2 (GREEN):** Add the table. Re-run to green.
- [ ] **Step 3:** Stop for review.

## Task 5 — Adjacent custody, cross-document freshness, gates, closure

**Pool custody edits — all four rows, explicitly:**

- `A2A-LEDGER-DESIGN-REFRESH`: remove operation-entry guard custody (now `LEDGER-INTEGRITY-BOUNDARY`);
  retain design v2 restatement, Docker/wslc, session Option A.
- `AT-REST-INTEGRITY`: retain periodic/scheduled post-readiness verification; remove
  operator-triggered/on-demand full-audit wording.
- `CREDENTIAL-LIFECYCLE`: retain OAuth/rotation and Cursor discovery interoperability; state the
  Evidence/DoD slice dependency or its obligation to narrow the future native-client claim.
- `PEER-LIVENESS-SIGNAL`: remove stale "in-flight Task 6/Task 10/Task 11" phrasing.

**Optimus-pool correction (verified):** line ~1397 states *"as the A2A ledger's hardened-Redis
fallback path"*. No such path exists; the A2A runtime is PostgreSQL. Narrow the reference to generic
future consolidated-startup work. This is the **only** Optimus-pool edit authorized here. No README
current-state A2A claim exists; historical references to the unchanged frozen v1/v2 pair are not
rewritten.

- [ ] **Step 1 (RED):** Pin each adjacent-custody clause so future wording cannot restore dual
      ownership; pin the corrected Optimus Redis wording. Expect FAIL.
- [ ] **Step 2 (GREEN):** Make the edits. Re-run narrow docs test to green.
- [ ] **Step 3:** Full gate set (below). A known flake is diagnostic context, **not** permission to
      check a failed gate: isolate, then **rerun the original full command to exit 0** before marking
      any checkbox. A deselected-or-failed command never becomes `[x]`.
- [ ] **Step 4:** Compute custody digests **without a masking pipeline**. `git show … | sha256sum`
      is unsafe: `sha256sum` exits 0 on empty input after a failed `git show`, yielding
      `e3b0c442…` — a plausible digest for a file that does not exist. Demonstrated live during
      review. For each of the six records:

      ```bash
      git show "<custody-commit>:<path>" > /tmp/blob.bin 2>/tmp/blob.err; rc=$?
      test "$rc" -eq 0 || { echo "git show FAILED: $path"; exit 1; }
      sha256sum /tmp/blob.bin
      wc -l < /tmp/blob.bin
      ```

      Record path, custody-commit SHA, digest, and verified line count in the custody manifest,
      appended **outside** the `PRESERVED-BODY` delimiters of
      `docs/superpowers/reviews/evidence-handoff-a2a-not-shipped-closure-review.md`.
      Do not use a pipeline unless both `pipefail` and the producer's status are explicitly checked.
- [ ] **Step 5:** Documentation-freshness audit across the product pool, Optimus pool, README and
      `AGENTS.md` for A2A current-state claims. Stop for final review.
- [ ] **Step 6:** **Stop. Request explicit operator authorization for the final closure commit.**
      On authorization, run `git status --short` immediately beforehand and **reject any extra
      path**; the commit contains exactly:

      - `docs/superpowers/plans/evidence-handoff-open-work-pool.md`
      - `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`
      - `tests/unit/docs/test_open_work_pool_hygiene.py`
      - `docs/superpowers/reviews/evidence-handoff-a2a-not-shipped-closure-review.md`
      - `docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure.md` — its checkboxes are
        the required on-disk progress record

      Without this second commit M17 is not durably closed and the two-phase custody disposition is
      incomplete. Neither commit is authorized by any review; both need the operator.

## Verification gates — actual Guardrails inventory plus repository gates

```bash
uv sync --all-extras
# noneditable-package gate — the verifier declares --wheel-dir and --scratch-root as
# required=True (tools/verify_plan99_noneditable_install.py:409-412); omitting them exits at
# argument parsing. This mirrors .github/workflows/guardrails.yml:34-39.
uv build --wheel --out-dir dist/plan99
test "$(ls -1 dist/plan99/*.whl | wc -l)" -eq 1   # verifier requires exactly one wheel
plan99_scratch="$(mktemp -d)"
uv run python tools/verify_plan99_noneditable_install.py \
  --wheel-dir dist/plan99 \
  --scratch-root "$plan99_scratch"
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
uv lock --check
git diff --check
```

Narrow cycle after every red/green: `uv run pytest tests/unit/docs/test_open_work_pool_hygiene.py -q`.
Coverage floor `fail_under = 80`. Capture return codes directly — **never read `$?` after a pipe**.
Known tracked flakes: `P11-FU-7`, `P11-FU-6`.

## Definition of Done

- [ ] All six audit/plan records preserved in tracked storage with provenance headers; the scoping
      header states its Revision-3 approval supersedes the preserved DRAFT status text.
- [ ] Custody commit exists and is operator-authorized; all six digests computed from it and recorded
      in the named tracked manifest.
- [ ] The A2A row states not-shipped/not-supported/not-trusted, carries the three corrected Git
      facts, says code and console scripts remain present, and uses the bounded deferral rationale
      without "latent, not live".
- [ ] Six slice rows `Tracked, Not Yet Scheduled`; nothing scheduled or numbered.
- [ ] Obligations table: 20 rows matching `EXPECTED_OBLIGATIONS` exactly; M17 the sole `Closed`.
- [ ] Both product tables carry exactly one Priority column; Credential Lifecycle is the sole
      non-MEDIUM seed; no residual body priority label.
- [ ] `PRODUCT_FEATURE_IDS` and `PRODUCT_OWNED_DOCS` updated; only the scoping contract and closure
      plan are linked; every reviews artifact referenced by backticked path.
- [ ] All four adjacent custody rows corrected; the Optimus Redis reference narrowed.
- [ ] Pool contains no plan-number token; no `src/` change; no digest-pinned artifact modified.
- [ ] The noneditable gate ran with `--wheel-dir` and `--scratch-root` and exactly one wheel present.
- [ ] Custody digests computed without a pipeline; each `git show` return code checked; line counts recorded.
- [ ] Preserved bodies delimited; the custody manifest sits outside the delimiters.
- [ ] Approval-precedence headers present on the scoping contract, the closure plan, and both review chronologies.
- [ ] The final closure commit is operator-authorized and contains exactly the five named paths, verified by `git status --short` immediately beforehand.
- [ ] Every gate above exits 0, with any isolated flake followed by a clean rerun of the full command.

<!-- PRESERVED-BODY-END -->
