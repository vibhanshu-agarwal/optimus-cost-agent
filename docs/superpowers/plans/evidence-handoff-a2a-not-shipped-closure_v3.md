# A2A Not-Shipped Closure Plan — v3 (live successor)

> **For agentic workers:** stop for review after every task. A checkbox may be marked `[x]` only
> after its stated command ran and passed. Prose claims count for nothing (`AGENTS.md:76`).

**Author:** Claude (drafter/implementer) · **Reviewer:** Codex · **Date:** 2026-08-12
**Amends:** `a2a-not-shipped-closure-plan_v2-DRAFT.md` (D1/D2/E1-corrected). `_v2-DRAFT` is unchanged
and kept as the historical record of that review chronology.
**v1's preserved body is immutable.** This is the live execution target; v1 is history.
**Status: Task 1A COMPLETE. Task 1B COMPLETE. Task 1C COMPLETE.** The two-file tooling diff was
committed (`b370765`), pushed, opened as PR #131, and **merged to `main`** (merge commit `e2496ce`).
The custody branch fast-forwarded cleanly to that merge (`0	0` against `origin/main`) and the
eight-path `check-attr` rerun in the custody worktree matched exactly. All eight custody records
were reconstructed/finalized in `optimus-cost-agent-wt-claude` and verified against each record's
**live or pinned baseline as specified in Task 1C** (historical evidence — see the relabeled Task
1C byte table below, frozen at that cutoff and not reconverged since).

**Current state (post Task 1D rerun and H6):** Attempt 1 stopped correctly at Step 4 on a
**verified false negative** (index-hash aggregates differed only by filename, not by digest value;
no record drift occurred). H5 fixed the root cause, R1-R3 corrected the plan text and its snapshot
self-reference, and the authorized rerun executed Task 1D Steps 1-6 followed immediately by the
standalone H6 block. **All six Task 1D steps passed and are checked**; H6 then passed, proving
live-source, working, and staged record-8 object IDs identical to one another (the exact ID is
external evidence, recorded in the reviewer chronology — not embedded here, since embedding it in
this mutable document would itself change the document and invalidate the recorded ID). The custody
worktree proved all eight custody records staged and byte-verified (H6's own evidence). **Task 1E
was explicitly authorized by the operator; the custody commit was made, pushed, and opened as
PR #132 (preservation-only, per Task 1E Step 2's required framing), and PR #132 contains the
eight-record baseline.** A documentation-ledger defect in that commit (Task 1E's checkbox and
current-state prose) was found and **the selected amend topology has completed**: K3 passed;
after a fresh ref re-pin immediately beforehand, the operator-authorized `git commit --amend` and
exact-lease `git push --force-with-lease` updated PR #132 in place, preserving the
one-commit/eight-record baseline. **PR #132 remains unmerged; Tasks 2-5 remain separately gated.**
This document does not embed any transient index/status state or any mutable ref/object ID as a
self-identifier — those change by design as work proceeds and are **external review evidence**,
recorded in the reviewer chronology, never inside this mutable document (the same self-reference J1
and L1 both close). Task 1E authorized exactly the eight named document-custody files above — no
further pool, test, or source file mutation is authorized by this document; no Tasks 2-5
pool/test/source edit, M17 closure, or remediation scheduling is authorized until separately
granted.

## Why v3 exists

Real execution of Task 1A Steps 1-7 in a fresh worktree found two process/mechanical gaps the
Codex review then required as a narrow forward amendment, not a re-litigation of D1/D2/E1:

1. **Steps 1-3 and 5-7 genuinely ran and passed**, but the plan still recorded all seven as open
   `[ ]` — no completion was recorded on disk, contradicting `AGENTS.md:76`.
2. **Step 4's probe used `/tmp/*` scratch paths, which are invisible to native Windows
   `python`/`python3`** — Git Bash's `/tmp` is an MSYS-only virtual path; a file bash writes to
   `/tmp/foo.bin` does not exist from native Python's point of view, even in the same shell
   session. Confirmed directly: relative and `D:\`-style absolute paths resolve identically for
   both tools; only `/tmp/...` fails. Task 1D uses the identical pattern (`git cat-file`/`git show`
   output read by an embedded `python3` heredoc) and would hit the same wall on first execution.
   **Task 5 does not share this defect** — its digest parsing was already rewritten under the E1
   correction to use pure bash (`read` + regex), never Python, so it is unchanged here.
3. A fresh worktree also has no dev-dependency venv; `uv run pre-commit` fails until
   `uv sync --extra dev` has been run once. Added explicitly where first needed.

**Scope of this amendment: Task 1A's checkbox ledger and safety-checked scratch handling (Steps 4,
5, 7), and version-plumbing corrections in Tasks 1C, 1D, 2, 3, 5, and the DoD.** Task 1E's
*structure* (baseline-only commit, no manifest, SHA/PR reported externally) is unchanged, though
its *record count* changed 7→8 along with everything else under the F1 topology correction — it is
not "untouched" as an earlier revision of this sentence claimed. Task 1B, the obligation table, and
every substantive D1/D2/E1 scope/severity/priority/ownership ruling are
untouched — only the record count and which path is "live" change, per the F1 topology ruling.

**F1 topology correction — eight custody records, not seven.** Because `_v3` now exists as a real
file, the forward-only version rule applies one level up: `_v2` is no longer live. The custody
baseline is:

1. the six existing preserved (`-text`) records — unchanged;
2. **historical, normal-text `_v2`** (tracked `_v2.md`, sourced from `_v2-DRAFT.md`, frozen once
   `_v3` supersedes it) — **NOT `-text`**; its content has no deliberate CRLF or hard breaks, so
   normal `* text=auto eol=lf` handling is correct and no `.gitattributes` change is needed; and
3. **live, normal-text `_v3`** (tracked `_v3.md`, sourced from this document) — also not `-text`.

Both `_v2` and `_v3` stay under the default `.gitattributes` rule already staged — **the two-file
tooling diff needs no further change**, resolving the question this draft would otherwise have
raised.

**Authoritative ignored sources** — absent from a fresh worktree — live in
`D:\Projects\Development\Python\optimus-cost-agent-wt-codex\.superpowers\sdd\`.

**Source → destination map** (`$SDD` = the directory above). Used literally by Tasks 1A, 1C, 1D:

| # | `$SDD/` source | tracked destination (`$DST`) |
|---|---|---|
| 1 | `a2a-audit-independent-findings.md` | `docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md` |
| 2 | `a2a-audit-SEALED-reviewer-findings.md` | `docs/superpowers/reviews/evidence-handoff-a2a-ledger-sealed-reviewer-findings.md` |
| 3 | `a2a-remediation-scoping-review.md` | `docs/superpowers/reviews/evidence-handoff-a2a-remediation-scoping-review.md` |
| 4 | `a2a-not-shipped-closure-plan-review.md` | `docs/superpowers/reviews/evidence-handoff-a2a-not-shipped-closure-review.md` |
| 5 | `a2a-remediation-scoping-proposal-DRAFT.md` | `docs/superpowers/specs/evidence-handoff-a2a-ledger-remediation-scoping.md` |
| 6 | `a2a-not-shipped-closure-plan-DRAFT.md` | `docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure.md` |
| 7 | `a2a-not-shipped-closure-plan_v2-DRAFT.md` | `docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v2.md` — **historical, normal-text, frozen once `_v3` exists** |
| 8 | *(this document)* | `docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v3.md` — **live, normal-text** |

## Preservation envelope — exact bytes, used by Task 1C (reconstruction) and Task 1D (verification)

```
full_blob = header_bytes
          + b"<!-- PRESERVED-BODY-START -->
"
          + body_bytes
          + b"
<!-- PRESERVED-BODY-END -->
"
```

No separator between the START marker and `body_bytes` — the body begins on the very next byte
after the marker line. The `b"
"` immediately before the END marker is a **required separator**:
it guarantees the end marker sits on its own line even when `body_bytes` does not end with a
trailing newline. Reconstruction (Task 1C) must emit exactly this sequence; verification (Task 1D)
extracts `body_bytes` by locating the unique START/END marker lines and slicing between them.

## Why v2 exists

| # | Blocker | Proof |
|---|---|---|
| 1 | Git rewrites two preserved bodies on staging (CRLF→LF) | `30BC62B6`→`3765FFF5`; `C993B3A6`→`6630D6DF` |
| 2 | The all-files hook strips 18 intentional Markdown hard breaks | 6 each in records 1, 3, 4; `.pre-commit-config.yaml:5-7` excludes only `^reports/` |
| 3 | The tracked plan has no checked boxes while prose claims progress | `AGENTS.md:76` |

`git diff --cached --check` is a git builtin with no markdown-linebreak option; probed **exit 2** on
intentional hard breaks. It is unusable over the six preserved records.

---

## Task 1 — historical ledger (executed; recorded, not re-run)

- [x] **Step 1:** Six **untracked candidate records created at tracked destinations** in
      `optimus-cost-agent-wt-claude` on `agent/claude/a2a-audit-docs-preservation` (from `origin/main`
      `e5f7e33`, `0 0`). `git status` reports all six as `??`.
- [x] **Step 2:** **Working-tree** body equality verified for all six; delimiters unique.
      Bodies 40,410 / 4,350 / 17,567 / 25,537 / 19,547 / 22,461 bytes.
      **Working-tree evidence only — expressly NOT committed-blob custody.**
- [x] **Step 3a:** `uv run pytest tests/unit/docs/test_open_work_pool_hygiene.py -q` → **43 passed**.
- [x] **Step 3b:** `uv run ruff check .` → exit 0.

**Step 3c — VOID (historical disposition, not a task).** The reported `git diff --check` exit 0 was
vacuous: it inspects tracked/staged content and all six files were untracked. Superseded by Task 1D.

**Step 4 — SUPERSEDED (historical disposition, not a task).** Custody authorization was not granted;
replaced by Task 1E.

---

## Task 1A — prerequisite tooling PR (two files only)

- [x] **Step 1: VERIFIED HISTORICAL.** Dedicated sibling worktree created from freshly fetched
      `origin/main`: `git worktree add -b agent/claude/a2a-audit-custody-tooling
      D:/Projects/Development/Python/optimus-cost-agent-wt-claude-tooling origin/main`. Both
      preflight checks (path not occupied, branch not present) ran and passed before creation.
      `git rev-list --left-right --count origin/main...HEAD` returned `0	0` in the new worktree.

      ```bash
      git fetch origin; rc=$?
      test "$rc" -eq 0 || { echo "FAIL: git fetch"; exit 1; }

      WORKTREE_PATH="D:/Projects/Development/Python/optimus-cost-agent-wt-claude-tooling"
      test -e "$WORKTREE_PATH" && { echo "FAIL: worktree path already occupied: $WORKTREE_PATH"; exit 1; }
      if git show-ref --verify --quiet refs/heads/agent/claude/a2a-audit-custody-tooling; then
        echo "FAIL: branch agent/claude/a2a-audit-custody-tooling already exists locally"; exit 1
      fi

      git worktree add -b agent/claude/a2a-audit-custody-tooling "$WORKTREE_PATH" origin/main; rc=$?
      test "$rc" -eq 0 || { echo "FAIL: git worktree add"; exit 1; }

      cd "$WORKTREE_PATH"
      git rev-list --left-right --count origin/main...HEAD    # expect: 0	0
      ```
- [x] **Step 2: VERIFIED HISTORICAL.** `.gitattributes` amended: the false "every text file... is
      already stored LF-only" sentence corrected, and all six `-text` exceptions appended.
      Confirmed present via Step 5's `check-attr` run (below) and by direct read of the file.

      ```gitattributes
      docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md          -text
      docs/superpowers/reviews/evidence-handoff-a2a-ledger-sealed-reviewer-findings.md   -text
      docs/superpowers/reviews/evidence-handoff-a2a-remediation-scoping-review.md        -text
      docs/superpowers/reviews/evidence-handoff-a2a-not-shipped-closure-review.md        -text
      docs/superpowers/specs/evidence-handoff-a2a-ledger-remediation-scoping.md          -text
      docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure.md                 -text
      ```
- [x] **Step 3: VERIFIED HISTORICAL.** `args: [--markdown-linebreak-ext=md]` added to the
      `trailing-whitespace` hook in `.pre-commit-config.yaml`. Proved live by Step 4's rerun below
      (hook ran at exit 0 and left intentional hard breaks byte-identical).
- [x] **Step 4 — F2-CORRECTED AND RERUN.** Preflight confirmed both `$P` and `.probe_scratch/`
      absent before creation; `mkdir` checked; all four probe assertions passed (index retrieval;
      `-text` preserved CRLF; hook exit 0 — `optimus-check: hygiene trailing whitespace...Passed`;
      hard breaks byte-identical); cleanup removed the three known scratch files explicitly plus
      `rmdir` (no recursive delete), each checked; final proof confirmed both `$P` and
      `.probe_scratch/` genuinely absent (`CLEANUP VERIFIED ABSENT`). Corrected script, run for
      real:

      ```bash
      uv sync --extra dev; rc=$?
      test "$rc" -eq 0 || { echo "FAIL: uv sync --extra dev"; exit 1; }

      P=docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md
      SCRATCH=.probe_scratch

      test -e "$P" && { echo "FAIL: probe path already occupied: $P"; exit 1; }
      test -e "$SCRATCH" && { echo "FAIL: scratch directory already occupied: $SCRATCH"; exit 1; }

      mkdir "$SCRATCH"; rc=$?
      test "$rc" -eq 0 || { echo "FAIL: mkdir $SCRATCH"; exit 1; }

      printf 'alpha  \r\nbeta  \r\ngamma\r\n' > "$P"
      cp "$P" "$SCRATCH/probe_pre.bin"
      git add -- "$P"
      git cat-file blob ":$P" > "$SCRATCH/probe_idx.bin" 2>"$SCRATCH/probe_idx.err"; rc=$?
      test "$rc" -eq 0 || { echo "FAIL: index blob retrieval"; exit 1; }

      python -c "import sys;d=open('$SCRATCH/probe_idx.bin','rb').read();sys.exit(0 if b'\r\n' in d else 1)"; rc=$?
      test "$rc" -eq 0 || { echo "FAIL: -text did not preserve CRLF in the index"; exit 1; }

      uv run pre-commit run trailing-whitespace --files "$P"; rc=$?
      test "$rc" -eq 0 || { echo "FAIL: hook exit nonzero ($rc)"; exit 1; }

      cmp -s "$SCRATCH/probe_pre.bin" "$P" || { echo "FAIL: hook modified intentional hard breaks"; exit 1; }

      git restore --staged -- "$P"; rc=$?
      test "$rc" -eq 0 || { echo "FAIL: git restore --staged"; exit 1; }

      rm -- "$P"; rc=$?
      test "$rc" -eq 0 || { echo "FAIL: rm $P"; exit 1; }
      rm -- "$SCRATCH/probe_pre.bin"; rc=$?
      test "$rc" -eq 0 || { echo "FAIL: rm probe_pre.bin"; exit 1; }
      rm -- "$SCRATCH/probe_idx.bin"; rc=$?
      test "$rc" -eq 0 || { echo "FAIL: rm probe_idx.bin"; exit 1; }
      rm -- "$SCRATCH/probe_idx.err"; rc=$?
      test "$rc" -eq 0 || { echo "FAIL: rm probe_idx.err"; exit 1; }
      rmdir "$SCRATCH"; rc=$?
      test "$rc" -eq 0 || { echo "FAIL: rmdir $SCRATCH (not empty?)"; exit 1; }

      test ! -e "$P" || { echo "FAIL: $P still exists after cleanup"; exit 1; }
      test ! -e "$SCRATCH" || { echo "FAIL: $SCRATCH still exists after cleanup"; exit 1; }
      echo "CLEANUP VERIFIED ABSENT: $P and $SCRATCH"
      ```

      Every failure exits nonzero — no diagnostic that prints and passes. No recursive delete: the
      three known scratch files are removed explicitly, then the now-empty directory via `rmdir`
      (which itself fails loudly if anything unexpected remains inside it).
- [x] **Step 5 — F1-CORRECTED AND RERUN.** Literal eight-path check ran for real. Observed exactly
      as expected: `text: unset` for the six preserved records; `text: auto` / `eol: lf` for
      **both** `_v2` and `_v3` — confirming neither is `-text`-exempted, per F1:

      ```bash
      git check-attr text eol -- \
        docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md \
        docs/superpowers/reviews/evidence-handoff-a2a-ledger-sealed-reviewer-findings.md \
        docs/superpowers/reviews/evidence-handoff-a2a-remediation-scoping-review.md \
        docs/superpowers/reviews/evidence-handoff-a2a-not-shipped-closure-review.md \
        docs/superpowers/specs/evidence-handoff-a2a-ledger-remediation-scoping.md \
        docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure.md \
        docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v2.md \
        docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v3.md
      ```

      Expected: `text: unset` for the first six; for **both** `_v2` and `_v3`, `text: auto` and
      `eol: lf` — neither is `-text`-exempted, matching F1's ruling that both are normal-text.
      `git check-attr` is pattern-based and does not require the path to exist on disk, so this
      runs correctly even though records 7-8 have not been reconstructed in this worktree yet.
- [x] **Step 6: VERIFIED HISTORICAL.** All six gates run individually with real output, all exit 0:
      `check-yaml` passed; `check-toml` passed; `trailing-whitespace --all-files` passed;
      `pytest tests/unit/docs/test_open_work_pool_hygiene.py -q` → **43 passed**, exact match;
      `ruff check .` → **All checks passed!**; `git diff --cached --check` after staging both files
      → exit 0, non-vacuous (both files staged, neither is a preserved record).

      ```bash
      uv run pre-commit run check-yaml --all-files
      uv run pre-commit run check-toml --all-files
      uv run pre-commit run trailing-whitespace --all-files
      uv run pytest tests/unit/docs/test_open_work_pool_hygiene.py -q      # 43 passed
      uv run ruff check .
      git add -- .gitattributes .pre-commit-config.yaml
      git diff --cached --check                                            # non-vacuous: both staged, neither preserved
      ```
- [x] **Step 7 — RERUN FRESH after Steps 4/5; RESOLVED HISTORICAL.** `git status --short` after
      both corrected reruns showed **exactly** two staged paths — `M  .gitattributes` and
      `M  .pre-commit-config.yaml`, byte-identical to before the reruns (`+15/-3` and `+1`
      respectively) — no probe leftovers, no scratch directory, nothing else. **Stopped for
      explicit operator authorization**, as required. **That authorization was subsequently given**
      and Step 8 executed: committed as `b370765`, pushed, opened as PR #131, and merged to `main`
      as `e2496ce`. This step's own stop condition is satisfied; it does not extend to Task 1B,
      which requires its own separate authorization.

**Step 8 — external evidence, not a checkbox; RESOLVED HISTORICAL.** Committed `b370765`, pushed
`agent/claude/a2a-audit-custody-tooling`, opened PR #131, **merged to `main`** as `e2496ce`.
Reported as external evidence at the time, as required — a commit cannot contain its own
identifier, so these are recorded here only after the fact.

---

## Task 1B — merge checkpoint

- [x] **Step 1:** `git fetch origin` rc=0; confirmed the tooling merge commit `e2496ce` is a
      real ancestor of `origin/main` via `git merge-base --is-ancestor` (not just trusted from the
      operator's report). Custody branch was `2 0` (two behind) with exactly the six expected
      untracked records — matching the operator's independent finding exactly.
- [x] **Step 2:** Fast-forward succeeded: `Updating e5f7e33..e2496ce`, `Fast-forward`,
      diffstat `.gitattributes | 17 ++++++++++++++---` / `.pre-commit-config.yaml | 1 +`
      (`2 files changed, 15 insertions(+), 3 deletions(-)`) — exact match to the merged tooling PR.
      `git rev-list --left-right --count origin/main...HEAD` → `0	0`. Merge-base equality
      confirmed: `$MB` = `$OM` = `e2496ced8580ff0318bf263c5c43eb446bea10e0`. All six untracked
      records confirmed present and unaffected by the fast-forward (`git status --short`
      unchanged). Merged `.gitattributes` confirmed to carry all six `-text` lines.

      ```bash
      git merge --ff-only origin/main; rc=$?
      test "$rc" -eq 0 || { echo "FAIL: fast-forward failed — STOP, do not rebase, request review"; exit 1; }
      git rev-list --left-right --count origin/main...HEAD    # expect: behind = 0
      MB="$(git merge-base HEAD origin/main)"; OM="$(git rev-parse origin/main)"
      test "$MB" = "$OM" || { echo "FAIL: merge-base != origin/main"; exit 1; }
      ```

      If `--ff-only` fails, **stop for review** — do not change branch topology to force a merge.
- [x] **Step 3:** Task 1A Step 5's 8-path `check-attr` rerun in the **custody** worktree (not just
      the tooling worktree); identical result — six `text: unset`, both `_v2` and `_v3`
      `text: auto` / `eol: lf`. Stopped for review, as required. **Tasks 1C onward remain
      unauthorized** — this task's completion does not extend past its own three steps.

---

## Task 1C — reconstruct the eight records

- [x] **Step 1: VERIFIED, H1-corrected.** Records 1-6 rebuilt in `optimus-cost-agent-wt-claude`.
      Marker uniqueness confirmed for all six (exactly one anchored
      `^<!-- PRESERVED-BODY-START -->$` / `^<!-- PRESERVED-BODY-END -->$` line each — substring
      matching is unsafe here because record 6's own body *mentions* the marker syntax as prose).
      Records 1-3, 5-6 verified byte-exact against their current `$SDD` source, modulo exactly the
      required separator newline (records 1-3 sources lack a trailing newline; records 5-6 are
      **CRLF throughout** — `a2a-remediation-scoping-proposal-DRAFT.md`: 297 CR = 297 LF;
      `a2a-not-shipped-closure-plan-DRAFT.md`: 295 CR = 295 LF — verified via raw byte-offset
      extraction, not a line-oriented tool, and the dest files' CR counts (297, 295) confirm the
      CRLF survived the write byte-for-byte.
      **Record 4 (H1): pinned, not live.** The review chronology is append-only and the H1 finding
      itself necessarily advanced it while being written, so record 4 is pinned to the
      reviewer-reported **post-checkpoint cutoff: 71,285 bytes, SHA-256
      `601142B974898ECEAB9F2750A84C572FE51637FEDCC33069DA89177AC9333EA0`**. Before rebuilding,
      `.superpowers/sdd/a2a-not-shipped-closure-plan-review.md` (then exactly 71,285 bytes) was
      copied byte-for-byte to a stable sibling file,
      `a2a-not-shipped-closure-plan-review-H1-CUTOFF.md`, and `sha256sum` on that frozen copy was
      independently computed and matched `601142b9…` before use (checked producer: written to a
      file, `read -r` with a 64-hex-char regex validation, not a piped `cut`). Record 4's body was
      rebuilt from this frozen copy, not the live (still-growing) source, so later review rounds
      appended to the live chronology cannot silently invalidate this reconstruction. Byte-offset
      verification confirms record 4's body is exact against the frozen cutoff, modulo the same
      required-separator artifact as records 1-3 (cutoff lacks a trailing newline).
- [x] **Step 2: VERIFIED.** Record 6's wrapper (outside the delimiters) rewritten in the same
      write: replaced the mutable "EXECUTION STATE — READ BEFORE USING THIS PLAN" paragraph and
      "Revision 3 APPROVED" authority line with a static-history disposition — "v1 was the approved
      Revision 3 plan; superseded by `_v2`..., itself now superseded by live `_v3`... Current
      execution state lives only in `_v3`" — confirmed present via direct read of the written file;
      no mutable execution-state prose remains in the wrapper.
- [x] **Step 3: VERIFIED, H2-corrected.** Record 7 written to
      `evidence-handoff-a2a-not-shipped-closure_v2.md` from
      `$SDD/a2a-not-shipped-closure-plan_v2-DRAFT.md` (609 lines both sides). CR count on the write
      target: 0 (LF-clean). `diff` against the LF-normalized source shows **exactly two** changed
      lines, both header-only, no substantive plan content touched:
      line 8, `**v1's preserved body is immutable.** This is the live execution target; v1 is
      history.` → `**v1's preserved body is immutable.**` (H2: removes the stale live-target clause
      that contradicted line 9's own historical disposition, retaining only the immutability
      statement); and
      line 9, `Draft for review. Authorizes nothing.` → `Historical — superseded by live \`_v3\`...
      Current execution state lives only in \`_v3\`.` (unchanged from the prior round).
- [x] **Step 4: VERIFIED, H4-corrected.** Record 4's wrapper still reads "Latest disposition: see
      live `_v3`..." naming the live document by its tracked path (done in the H1-corrected Step 1
      pass; pinned record 4 itself is **not** refreshed here per H4's authorization boundary). The
      header's overgeneralized "verified byte-exact against their current sources" claim is
      replaced with an accurate per-record live-or-pinned-baseline summary, and Task 1D's F1
      preamble now states plainly that records 1-3/5-6 use live-source comparison while record 4
      uses pinned SHA-256/byte-count comparison. Record 8
      (`evidence-handoff-a2a-not-shipped-closure_v3.md`) is written **last**, only after every H1-H4
      plan-text edit in this document is final (per H3, to avoid hard-coding a size that later edits
      would immediately invalidate) — see the byte-count table immediately below, which records the
      converged, self-consistent final sizes and confirms record 8's actual size matches its own
      self-reported table entry.
- [x] **Step 5: VERIFIED, H4-corrected.** Stopped for review. `git status --short` in the custody
      worktree, run after H4's prose edits and record 8's re-converged final write, shows exactly
      the same eight tracked-destination paths as `??` (untracked) and nothing else changed; `git
      diff --cached --stat` is empty; `0	0` against `origin/main` (`e2496ce`) unchanged; no `git add`
      was run; pinned record 4 was not touched. See the byte-count table immediately below for the
      converged per-record evidence.

**HISTORICAL Task 1C/H4 cutoff evidence — frozen, not reconverged since.** The byte counts below are
a point-in-time record of the state at the Task 1C/H4 stop, before Task 1D Attempt 1 staged the
eight records and left record 8 `AM`. They are **not** a claim about current working-tree sizes and
must not be reconverged; record 8's live working bytes have since changed again (see the header's
"Current state" paragraph above for what is true now).

**Task 1C final byte counts, as of the H4 stop** (working tree, then-untracked; `wc -c` on each
write target at that time):

| # | Destination | Bytes |
|---|---|---|
| 1 | `evidence-handoff-a2a-ledger-independent-audit.md` | 41,108 |
| 2 | `evidence-handoff-a2a-ledger-sealed-reviewer-findings.md` | 5,107 |
| 3 | `evidence-handoff-a2a-remediation-scoping-review.md` | 26,218 |
| 4 | `evidence-handoff-a2a-not-shipped-closure-review.md` | 72,592 |
| 5 | `evidence-handoff-a2a-ledger-remediation-scoping.md` | 18,379 |
| 6 | `evidence-handoff-a2a-not-shipped-closure.md` | 20,309 |
| 7 | `evidence-handoff-a2a-not-shipped-closure_v2.md` | 33,501 |
| 8 | `evidence-handoff-a2a-not-shipped-closure_v3.md` | 54,197 |

At that time, `git status --short` in `optimus-cost-agent-wt-claude` (branch
`agent/claude/a2a-audit-docs-preservation`, `0	0` against `origin/main` at `e2496ce`) showed exactly
these eight paths as `??`, `git diff --cached --stat` was empty, and nothing else in the working
tree had changed. **Nothing was staged, committed, or pushed at that point.** Task 1D subsequently
ran Attempt 1 and staged all eight records — see the header above for the current staged/`AM`
state; this historical paragraph is not updated further.

---

## Task 1D — staging and index-blob verification

No comparison may use a hash-producing pipeline or an unchecked producer. Bash arrays and other
shell state do **not** survive separate shell/tool invocations, so the script below is **one
continuous session** — if execution must split it into fragments, re-paste the "Shared setup"
block verbatim at the top of every fragment.

**Scratch location amended (v3):** every `/tmp/*` path below is replaced with a repo-relative
`.custody_scratch/` directory. `/tmp` is an MSYS-only virtual path invisible to native Windows
`python`/`python3` — confirmed directly during Task 1A Step 4's first attempt, where a file bash
wrote to `/tmp/probe_idx.bin` did not exist from Python's point of view in the same shell session.
This script's Step 2 reads `/tmp/idx_$i.bin`-style files via an embedded `python3` heredoc and
would hit the identical wall. `.custody_scratch/` resolves identically for bash and native Python.
A `uv sync --extra dev` precondition is also added before Step 4, since a fresh or
not-yet-dev-synced worktree has no `pre-commit` executable until it runs once.

**F2 safety contract applied, corrected per G1:** absence required before creation; `mkdir` checked;
before recursive cleanup, the repository root is captured via checked `pwd -P` and the scratch
directory's absolute path via checked `cd "$SCRATCH" && pwd -P`, and the two are required to be
**exactly** `$ROOT/.custody_scratch` — not merely a `*/.custody_scratch` suffix match, which would
accept the same directory name under any unexpected parent. The earlier suffix-match version of
this guard is superseded. Deletion targets the **validated absolute path**, not the unresolved
relative `$SCRATCH`; `rm` is checked; the final proof confirms **both** the absolute and the
repo-relative paths are absent. This is documented here for when Task 1D actually executes (gated
behind Task 1B); it has not run yet — Task 1A's tooling PR has already merged.

**F1 topology applied, H4-aligned:** `_v2` is no longer the live path. Records 1-3 and 5-6 keep the
delimiter-based **live-source** body comparison. Record 4 uses the same delimiter extraction but is
verified against the **H1-pinned SHA-256/byte count** (`601142B9…`, 71,285 bytes), never the
subsequently-growing live chronology. `_v2` (record 7) is reconstructed once by Task 1C with two
deliberate header edits (H2) — like v1's own "finalize as static history" step — so it is **not**
verified against a source here; it joins `_v3` (record 8, live) in the eight-path staging,
hash-snapshot, and cached-whitespace-check surface instead.

**Attempt 1 (2026-08-12) stopped at Step 4 on a verifier false negative, not record drift.** Steps
1-3 passed; the hook exited 0; pre/post `git status`, working-file hashes, and index digest
**values** were all identical for every one of the eight records. The aggregate index-hash files
still differed line-for-line because `sha256sum "$SCRATCH/pre_idx_$i.bin"` and
`sha256sum "$SCRATCH/post_idx_$i.bin"` each embed their own (deliberately different) filename in
the output line, so a full-line `diff` could never pass even though the digests matched. No Task 1D
checkbox was marked; exactly the eight records were staged and `.custody_scratch/` held the full
attempt diagnostics; both were left untouched for review, then the scratch directory was removed
under the G1 exact-path contract once review confirmed no drift (see the Task 1D checklist below —
none of Steps 1-6 are checked).

**H5 fix applied:** both index-hash producers below now hash via **stdin redirection**
(`sha256sum < "$SCRATCH/..._idx_$i.bin"`), which makes `sha256sum` emit the stable `-` marker
instead of a filename, so the pre/post aggregate files are directly comparable by digest value
alone. This is still a checked producer, still no `awk`/hash-extraction pipeline, and matches the
fresh WSL reproduction cited in review.

```bash
# ---- Shared setup ----
SDD="D:/Projects/Development/Python/optimus-cost-agent-wt-codex/.superpowers/sdd"
SCRATCH=".custody_scratch"

test -e "$SCRATCH" && { echo "FAIL: scratch directory already occupied: $SCRATCH"; exit 1; }
mkdir "$SCRATCH"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: mkdir $SCRATCH"; exit 1; }

SOURCES=(
  "$SDD/a2a-audit-independent-findings.md"
  "$SDD/a2a-audit-SEALED-reviewer-findings.md"
  "$SDD/a2a-remediation-scoping-review.md"
  "$SDD/a2a-not-shipped-closure-plan-review.md"
  "$SDD/a2a-remediation-scoping-proposal-DRAFT.md"
  "$SDD/a2a-not-shipped-closure-plan-DRAFT.md"
)
DESTINATIONS=(
  "docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md"
  "docs/superpowers/reviews/evidence-handoff-a2a-ledger-sealed-reviewer-findings.md"
  "docs/superpowers/reviews/evidence-handoff-a2a-remediation-scoping-review.md"
  "docs/superpowers/reviews/evidence-handoff-a2a-not-shipped-closure-review.md"
  "docs/superpowers/specs/evidence-handoff-a2a-ledger-remediation-scoping.md"
  "docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure.md"
)
V2_PATH="docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v2.md"
V3_PATH="docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v3.md"

test "${#SOURCES[@]}" -eq 6 || { echo "FAIL: SOURCES length ${#SOURCES[@]}"; exit 1; }
test "${#DESTINATIONS[@]}" -eq 6 || { echo "FAIL: DESTINATIONS length ${#DESTINATIONS[@]}"; exit 1; }

EIGHT=("${DESTINATIONS[@]}" "$V2_PATH" "$V3_PATH")
test "${#EIGHT[@]}" -eq 8 || { echo "FAIL: EIGHT length ${#EIGHT[@]}"; exit 1; }

# ---- Step 1: stage exactly the eight-path allowlist ----
git add -- "${EIGHT[@]}"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: git add"; exit 1; }

git diff --cached --name-only > "$SCRATCH/staged_actual.txt" 2>"$SCRATCH/staged_actual.err"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: git diff --cached --name-only rc=$rc"; exit 1; }
sort "$SCRATCH/staged_actual.txt" -o "$SCRATCH/staged_actual.sorted.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: sort staged_actual"; exit 1; }

printf '%s\n' "${EIGHT[@]}" > "$SCRATCH/staged_expected.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: printf staged_expected"; exit 1; }
sort "$SCRATCH/staged_expected.txt" -o "$SCRATCH/staged_expected.sorted.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: sort staged_expected"; exit 1; }

diff "$SCRATCH/staged_actual.sorted.txt" "$SCRATCH/staged_expected.sorted.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: staged set != eight-path allowlist"; exit 1; }

# ---- Step 2 (H1-amended): records 1-3, 5, 6 verified against their live named source; record 4
# (index 3) verified against the H1-pinned cutoff SHA-256/byte-count instead, since the review
# chronology is append-only and would otherwise go stale merely from the mandatory review
# checkpoint that reported this cutoff ----
PINNED_R4_SHA256="601142B974898ECEAB9F2750A84C572FE51637FEDCC33069DA89177AC9333EA0"
PINNED_R4_BYTES="71285"
i=0
while [ "$i" -lt 6 ]; do
  DST="${DESTINATIONS[$i]}"
  git cat-file blob ":$DST" > "$SCRATCH/idx_$i.bin" 2>"$SCRATCH/idx_$i.err"; rc=$?
  test "$rc" -eq 0 || { echo "FAIL: retrieval $DST rc=$rc"; exit 1; }
  if [ "$i" -eq 3 ]; then
    python3 - "$SCRATCH/idx_$i.bin" "$PINNED_R4_SHA256" "$PINNED_R4_BYTES" <<'PY'
import sys, hashlib
blob = open(sys.argv[1], "rb").read()
pinned_sha = sys.argv[2]
pinned_bytes = int(sys.argv[3])
S = b"<!-- PRESERVED-BODY-START -->\n"
E = b"\n<!-- PRESERVED-BODY-END -->\n"
if blob.count(S) != 1 or blob.count(E) != 1:
    print("FAIL marker count"); sys.exit(1)
body = blob[blob.find(S) + len(S):blob.rfind(E)]
if len(body) != pinned_bytes:
    print("FAIL body byte count", len(body), "!= pinned", pinned_bytes); sys.exit(1)
digest = hashlib.sha256(body).hexdigest().upper()
if digest != pinned_sha:
    print("FAIL body SHA-256", digest, "!= pinned", pinned_sha); sys.exit(1)
print(digest, len(body), body.count(b"\n"))
PY
  else
    SRC="${SOURCES[$i]}"
    python3 - "$SRC" "$SCRATCH/idx_$i.bin" <<'PY'
import sys, hashlib
src = open(sys.argv[1], "rb").read()
blob = open(sys.argv[2], "rb").read()
S = b"<!-- PRESERVED-BODY-START -->\n"
E = b"\n<!-- PRESERVED-BODY-END -->\n"
if blob.count(S) != 1 or blob.count(E) != 1:
    print("FAIL marker count"); sys.exit(1)
body = blob[blob.find(S) + len(S):blob.rfind(E)]
if body != src:
    print("FAIL body mismatch"); sys.exit(1)
print(hashlib.sha256(body).hexdigest().upper(), len(body), body.count(b"\n"))
PY
  fi
  rc=$?
  test "$rc" -eq 0 || { echo "FAIL: extraction/comparison index $i ($DST)"; exit 1; }
  i=$((i + 1))
done
# Record the printed SHA-256 / byte-count / line-count triple for each of the six indices.
# Index 3 (record 4) is checked against the H1-pinned cutoff, never against
# $SDD/a2a-not-shipped-closure-plan-review.md directly -- that source keeps growing.

# ---- Step 3: restage _v2 and _v3 (literal paths), then snapshot pre-hook state for all eight ----
git add -- "$V2_PATH" "$V3_PATH"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: restage $V2_PATH $V3_PATH"; exit 1; }

git status --short > "$SCRATCH/pre_hook_status.txt" 2>&1; rc=$?
test "$rc" -eq 0 || { echo "FAIL: git status rc=$rc"; exit 1; }

: > "$SCRATCH/pre_working_hashes.txt"
: > "$SCRATCH/pre_index_hashes.txt"
i=0
while [ "$i" -lt 8 ]; do
  P="${EIGHT[$i]}"
  sha256sum "$P" >> "$SCRATCH/pre_working_hashes.txt"; rc=$?
  test "$rc" -eq 0 || { echo "FAIL: working hash $P"; exit 1; }
  git cat-file blob ":$P" > "$SCRATCH/pre_idx_$i.bin" 2>"$SCRATCH/pre_idx_$i.err"; rc=$?
  test "$rc" -eq 0 || { echo "FAIL: pre-hook index blob $P"; exit 1; }
  sha256sum < "$SCRATCH/pre_idx_$i.bin" >> "$SCRATCH/pre_index_hashes.txt"; rc=$?
  test "$rc" -eq 0 || { echo "FAIL: pre-hook index hash $P"; exit 1; }
  i=$((i + 1))
done

# ---- Step 4: run the configured hook; prove it changed nothing ----
# uv sync --extra dev is required before uv run pre-commit will find an executable in a fresh or
# not-yet-dev-synced worktree ("Failed to spawn: pre-commit / program not found" otherwise).
uv sync --extra dev; rc=$?
test "$rc" -eq 0 || { echo "FAIL: uv sync --extra dev"; exit 1; }

uv run pre-commit run trailing-whitespace --all-files; rc=$?
test "$rc" -eq 0 || { echo "FAIL: trailing-whitespace hook exit $rc"; exit 1; }

git status --short > "$SCRATCH/post_hook_status.txt" 2>&1; rc=$?
test "$rc" -eq 0 || { echo "FAIL: post-hook git status rc=$rc"; exit 1; }
diff "$SCRATCH/pre_hook_status.txt" "$SCRATCH/post_hook_status.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: git status changed after hook"; exit 1; }

: > "$SCRATCH/post_working_hashes.txt"
: > "$SCRATCH/post_index_hashes.txt"
i=0
while [ "$i" -lt 8 ]; do
  P="${EIGHT[$i]}"
  sha256sum "$P" >> "$SCRATCH/post_working_hashes.txt"; rc=$?
  test "$rc" -eq 0 || { echo "FAIL: post-hook working hash $P"; exit 1; }
  git cat-file blob ":$P" > "$SCRATCH/post_idx_$i.bin" 2>"$SCRATCH/post_idx_$i.err"; rc=$?
  test "$rc" -eq 0 || { echo "FAIL: post-hook index blob $P"; exit 1; }
  sha256sum < "$SCRATCH/post_idx_$i.bin" >> "$SCRATCH/post_index_hashes.txt"; rc=$?
  test "$rc" -eq 0 || { echo "FAIL: post-hook index hash $P"; exit 1; }
  i=$((i + 1))
done

diff "$SCRATCH/pre_working_hashes.txt" "$SCRATCH/post_working_hashes.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: working-file hashes changed"; exit 1; }
diff "$SCRATCH/pre_index_hashes.txt" "$SCRATCH/post_index_hashes.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: index hashes changed"; exit 1; }

git diff --name-only -- "${EIGHT[@]}" > "$SCRATCH/unstaged_after_hook.txt" 2>&1; rc=$?
test "$rc" -eq 0 || { echo "FAIL: git diff --name-only rc=$rc"; exit 1; }
test -s "$SCRATCH/unstaged_after_hook.txt" && { echo "FAIL: unstaged changes remain"; exit 1; }

# ---- Step 5: cached whitespace check, scoped to both normal-text plan versions ----
git diff --cached --check -- "$V2_PATH" "$V3_PATH"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: v2/v3 whitespace check rc=$rc"; exit 1; }

# ---- Step 6: final state, then verified cleanup of the scratch directory ----
git status --short
git diff --cached --stat

ROOT="$(pwd -P)"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: pwd -P (repo root)"; exit 1; }

SCRATCH_ABS="$(cd "$SCRATCH" && pwd -P)"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: pwd -P (scratch dir)"; exit 1; }

test "$SCRATCH_ABS" = "$ROOT/.custody_scratch" || {
  echo "FAIL: refusing recursive delete -- resolved $SCRATCH_ABS != $ROOT/.custody_scratch"; exit 1;
}

rm -rf -- "$SCRATCH_ABS"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: rm -rf $SCRATCH_ABS"; exit 1; }

test ! -e "$SCRATCH_ABS" || { echo "FAIL: $SCRATCH_ABS still exists after cleanup"; exit 1; }
test ! -e "$SCRATCH" || { echo "FAIL: $SCRATCH still exists after cleanup"; exit 1; }
echo "CLEANUP VERIFIED ABSENT: $SCRATCH_ABS and $SCRATCH"
```

- [x] **Step 1: VERIFIED (rerun).** Staged set equaled the eight-path allowlist exactly (script
      "Step 1" section, real `git add`/`diff --cached --name-only`/sorted-diff, rc=0 throughout).
- [x] **Step 2 (H1-amended): VERIFIED (rerun).** Records 1-3, 5, and 6 verified byte-identical to
      their named live `$SDD` source; record 4 verified against the H1-pinned cutoff (71,285 bytes,
      SHA-256 `601142B9…`), not the live chronology. Printed SHA-256/byte-count/line-count for all
      six indices, including index 3's exact match against the pin: `601142B974898ECEAB9F2750A84C572FE51637FEDCC33069DA89177AC9333EA0
      71285 1191`.
- [x] **Step 3: VERIFIED (rerun).** `_v2` and `_v3` restaged at their literal paths; pre-hook
      status, working-file hashes, and index hashes captured for all eight paths (script "Step 3"
      section, all producers rc=0).
- [x] **Step 4: VERIFIED (rerun).** `uv sync --extra dev` and `uv run pre-commit run
      trailing-whitespace --all-files` both exited 0 ("Passed"); post-hook status, working-file
      hashes, and index hashes were **all identical** to pre-hook (H5's stdin-hashing fix confirmed
      correct — no false negative this run); no unstaged diff remained for any of the eight paths.
- [x] **Step 5: VERIFIED (rerun).** `git diff --cached --check` scoped to `_v2` **and** `_v3`
      passed (rc=0); never run over records 1-6.
- [x] **Step 6: VERIFIED (rerun).** Final eight-path `git status --short` showed all eight paths as
      `A`; `git diff --cached --stat` showed 8 files changed, 4,745 insertions(+); repo root and
      scratch directory each resolved via checked `pwd -P`, exactly equal to
      `$ROOT/.custody_scratch`; deletion targeted that validated absolute path (rc=0), and both the
      absolute and repo-relative paths were proven absent afterward
      (`CLEANUP VERIFIED ABSENT: ...`). The reviewer's bounded release for this run covered Steps
      1-6 followed immediately by the standalone H6 block; execution continued through H6 (below)
      without a stop in between, then stopped before Task 1E as that release required.

**Ledger-sync step (H6) — external evidence, not a checkbox.** A checkbox here would recreate the
self-reference it exists to close: checking Steps 1-6 mutates ignored live `_v3`, so record 8's
*staged* blob must be resynchronized to that checked state before Task 1E commits anything. This is
a **complete, standalone** block — it redefines every path itself and does not rely on Task 1D's
shared-setup variables surviving the plan edits made between Step 6 and here. It hashes **ignored
live `_v3`** (`$LIVE_V3`), not working record 8, as the source of truth. On authorization, after
Steps 1-6 above pass for real, run this as one continuous session in the custody worktree:

```bash
# ---- H6 ledger-sync: standalone, self-contained; not part of Task 1D Steps 1-6 ----
SDD="D:/Projects/Development/Python/optimus-cost-agent-wt-codex/.superpowers/sdd"
LIVE_V3="$SDD/a2a-not-shipped-closure-plan_v3-DRAFT.md"
V2_PATH="docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v2.md"
V3_PATH="docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v3.md"
EIGHT=(
  "docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md"
  "docs/superpowers/reviews/evidence-handoff-a2a-ledger-sealed-reviewer-findings.md"
  "docs/superpowers/reviews/evidence-handoff-a2a-remediation-scoping-review.md"
  "docs/superpowers/reviews/evidence-handoff-a2a-not-shipped-closure-review.md"
  "docs/superpowers/specs/evidence-handoff-a2a-ledger-remediation-scoping.md"
  "docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure.md"
  "$V2_PATH"
  "$V3_PATH"
)
test "${#EIGHT[@]}" -eq 8 || { echo "FAIL: EIGHT length ${#EIGHT[@]}"; exit 1; }

SCRATCH=".custody_scratch"
test -e "$SCRATCH" && { echo "FAIL: scratch directory already occupied: $SCRATCH"; exit 1; }
mkdir "$SCRATCH"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: mkdir $SCRATCH"; exit 1; }

# ---- 1. LF-normalized copy of ignored live _v3 into tracked working record 8 ----
tr -d '\r' < "$LIVE_V3" > "$V3_PATH"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: LF-normalize copy to $V3_PATH"; exit 1; }

# ---- 2. checked staging of only V3_PATH ----
git add -- "$V3_PATH"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: git add $V3_PATH"; exit 1; }

# ---- 3. sorted exact staged-allowlist comparison ----
git diff --cached --name-only > "$SCRATCH/staged_actual.txt" 2>"$SCRATCH/staged_actual.err"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: git diff --cached --name-only rc=$rc"; exit 1; }
sort "$SCRATCH/staged_actual.txt" -o "$SCRATCH/staged_actual.sorted.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: sort staged_actual"; exit 1; }
printf '%s\n' "${EIGHT[@]}" > "$SCRATCH/staged_expected.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: printf staged_expected"; exit 1; }
sort "$SCRATCH/staged_expected.txt" -o "$SCRATCH/staged_expected.sorted.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: sort staged_expected"; exit 1; }
diff "$SCRATCH/staged_actual.sorted.txt" "$SCRATCH/staged_expected.sorted.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: staged set != eight-path allowlist"; exit 1; }

# ---- 4. checked live-source, working-file, and staged blob IDs; equality required before the hook
LIVE_ID="$(git hash-object --path="$V3_PATH" -- "$LIVE_V3")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: hash-object live source"; exit 1; }
WORK_ID_PRE="$(git hash-object -- "$V3_PATH")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: hash-object working record 8"; exit 1; }
STAGED_ID_PRE="$(git rev-parse ":$V3_PATH")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: rev-parse staged record 8"; exit 1; }
test -n "$LIVE_ID" || { echo "FAIL: empty live-source id"; exit 1; }
test "$LIVE_ID" = "$WORK_ID_PRE" || { echo "FAIL: live-source id != working-file id ($LIVE_ID != $WORK_ID_PRE)"; exit 1; }
test "$WORK_ID_PRE" = "$STAGED_ID_PRE" || { echo "FAIL: working-file id != staged id ($WORK_ID_PRE != $STAGED_ID_PRE)"; exit 1; }
echo "PRE-HOOK IDS EQUAL: $LIVE_ID"

# ---- 5. cached whitespace check, scoped to both normal-text plan versions ----
git diff --cached --check -- "$V2_PATH" "$V3_PATH"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: v2/v3 whitespace check rc=$rc"; exit 1; }

# ---- 6. configured hook; prove full-repository invariance, not just record-8/custody invariance
# (R2: the hook runs --all-files, so it could in principle touch a tracked path outside the eight-
# path custody set and still pass the narrower checks below -- this closes that gap) ----
# R3: $SCRATCH is unignored, so `git status --untracked-files=all` sees its own contents. Pre-create
# (truncate) BOTH snapshot files before the pre-hook snapshot, so neither file's own creation is a
# visible diff between the two snapshots -- otherwise the post snapshot always shows one extra
# untracked path (itself) that the pre snapshot could not have seen yet, guaranteeing a false FAIL.
: > "$SCRATCH/pre_hook_full_status.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: pre-create pre_hook_full_status.txt"; exit 1; }
: > "$SCRATCH/post_hook_full_status.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: pre-create post_hook_full_status.txt"; exit 1; }

git status --short --untracked-files=all > "$SCRATCH/pre_hook_full_status.txt" 2>&1; rc=$?
test "$rc" -eq 0 || { echo "FAIL: pre-hook full status rc=$rc"; exit 1; }

uv sync --extra dev; rc=$?
test "$rc" -eq 0 || { echo "FAIL: uv sync --extra dev"; exit 1; }
uv run pre-commit run trailing-whitespace --all-files; rc=$?
test "$rc" -eq 0 || { echo "FAIL: trailing-whitespace hook exit $rc"; exit 1; }

git status --short --untracked-files=all > "$SCRATCH/post_hook_full_status.txt" 2>&1; rc=$?
test "$rc" -eq 0 || { echo "FAIL: post-hook full status rc=$rc"; exit 1; }
diff "$SCRATCH/pre_hook_full_status.txt" "$SCRATCH/post_hook_full_status.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: repository-wide status changed after hook"; exit 1; }
echo "FULL-REPOSITORY STATUS UNCHANGED BY HOOK"

# ---- 7. post-hook working/index IDs equal to their pre-hook values and the live-source id
# (defense in depth, retained alongside the full-status check above) ----
WORK_ID_POST="$(git hash-object -- "$V3_PATH")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: post-hook hash-object working record 8"; exit 1; }
STAGED_ID_POST="$(git rev-parse ":$V3_PATH")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: post-hook rev-parse staged record 8"; exit 1; }
test "$WORK_ID_POST" = "$WORK_ID_PRE" || { echo "FAIL: working id changed after hook"; exit 1; }
test "$STAGED_ID_POST" = "$STAGED_ID_PRE" || { echo "FAIL: staged id changed after hook"; exit 1; }
test "$WORK_ID_POST" = "$LIVE_ID" || { echo "FAIL: post-hook working id != live-source id"; exit 1; }
test "$STAGED_ID_POST" = "$LIVE_ID" || { echo "FAIL: post-hook staged id != live-source id"; exit 1; }
echo "POST-HOOK IDS EQUAL: $WORK_ID_POST"

# ---- 8. no unstaged custody diff across all eight paths ----
git diff --name-only -- "${EIGHT[@]}" > "$SCRATCH/unstaged_after_hook.txt" 2>&1; rc=$?
test "$rc" -eq 0 || { echo "FAIL: git diff --name-only rc=$rc"; exit 1; }
test -s "$SCRATCH/unstaged_after_hook.txt" && { echo "FAIL: unstaged changes remain"; exit 1; }

# ---- 9. final status/diffstat and staged record-8 id, reported externally ----
git status --short
git diff --cached --stat
echo "FINAL STAGED RECORD 8 ID: $STAGED_ID_POST"

# ---- 10. exact-path checked cleanup of this block's own scratch directory ----
ROOT="$(pwd -P)"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: pwd -P (repo root)"; exit 1; }
SCRATCH_ABS="$(cd "$SCRATCH" && pwd -P)"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: pwd -P (scratch dir)"; exit 1; }
test "$SCRATCH_ABS" = "$ROOT/.custody_scratch" || {
  echo "FAIL: refusing recursive delete -- resolved $SCRATCH_ABS != $ROOT/.custody_scratch"; exit 1;
}
rm -rf -- "$SCRATCH_ABS"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: rm -rf $SCRATCH_ABS"; exit 1; }
test ! -e "$SCRATCH_ABS" || { echo "FAIL: $SCRATCH_ABS still exists after cleanup"; exit 1; }
test ! -e "$SCRATCH" || { echo "FAIL: $SCRATCH still exists after cleanup"; exit 1; }
echo "CLEANUP VERIFIED ABSENT: $SCRATCH_ABS and $SCRATCH"
```

Before running this block, Steps 1-6 above must have passed for real and been marked `[x]` in this
document. Task 1E's custody commit must contain this block's **post-sync** checked ledger, never
the pre-sync record-8 blob.

---

## Task 1E — custody commit (baseline only)

- [x] **Step 1: AUTHORIZED.** Vibhanshu explicitly authorized Task 1E directly in chat ("Approved"),
      after independent confirmation of the eight-record custody baseline (all `A`, identical
      live/working/staged record-8 IDs, no scratch paths, `0	0` against `origin/main`). No review
      grants this authorization; it came from the operator directly, as required.

**Step 2 — external evidence, not a checkbox.** On authorization: re-run `git status --short`
immediately beforehand, reject any extra path, commit exactly the eight records, push, open the PR
described as **artifact-custody preservation only** (Tasks 2-5 open, M17 not closed, DoD Part 2 not
satisfied, records not yet discoverable through the pool). The custody-commit SHA and PR number are
**reported externally**; a commit cannot contain its own identifier.

**Commit topology (chosen, non-circular).** The custody commit is the eight-record baseline. **No
tracked manifest is written into it** — a manifest recording that commit's SHA cannot exist inside
it, and appending one would alter a file after its own verified baseline. The tracked manifest is
therefore **deferred to the Task 5 closure commit**, which records all digests explicitly as *hashes
of the custody commit*.

**K3 — post-commit amend verifier (external evidence, not a checkbox).** H6 is a **pre-commit**
verifier: its Step 3 checks `git diff --cached --name-only` against the eight-path allowlist, which
is correct only when every custody path is a fresh staged addition relative to HEAD. After the
custody commit landed (`7e9928ec77bc41877db3179b707b3875d634ddc9`), seven of the eight paths became
byte-identical to HEAD and stopped appearing in that diff at all — H6 failed deterministically on a
model mismatch, not on data corruption. **H6's own text is left unchanged** (it remains correct for
its original pre-commit use); this is a **separate, standalone** verifier for the amend case. It is
one continuous session, self-contained like H6, and does not rely on any other block's shell state.

```bash
# ---- K3 amend-mode verifier (L1-L4 corrected): standalone; proves the index is safe to
# `git commit --amend`, then stops. Never runs the amend or the force-push itself. ----
SDD="D:/Projects/Development/Python/optimus-cost-agent-wt-codex/.superpowers/sdd"
LIVE_V3="$SDD/a2a-not-shipped-closure-plan_v3-DRAFT.md"
V2_PATH="docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v2.md"
V3_PATH="docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v3.md"
EIGHT=(
  "docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md"
  "docs/superpowers/reviews/evidence-handoff-a2a-ledger-sealed-reviewer-findings.md"
  "docs/superpowers/reviews/evidence-handoff-a2a-remediation-scoping-review.md"
  "docs/superpowers/reviews/evidence-handoff-a2a-not-shipped-closure-review.md"
  "docs/superpowers/specs/evidence-handoff-a2a-ledger-remediation-scoping.md"
  "docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure.md"
  "$V2_PATH"
  "$V3_PATH"
)
test "${#EIGHT[@]}" -eq 8 || { echo "FAIL: EIGHT length ${#EIGHT[@]}"; exit 1; }
SCRATCH=".custody_scratch"

EXPECTED_HEAD="7e9928ec77bc41877db3179b707b3875d634ddc9"
EXPECTED_PARENT="e2496ced8580ff0318bf263c5c43eb446bea10e0"
EXPECTED_BRANCH="agent/claude/a2a-audit-docs-preservation"

# ---- 1. HEAD, parent, branch, upstream checks; then one fetch of ALL refs (L3: a branch-scoped
# fetch never refreshes origin/main, so stale-cache drift on main goes undetected) ----
CURRENT_HEAD="$(git rev-parse HEAD)"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: rev-parse HEAD"; exit 1; }
test "$CURRENT_HEAD" = "$EXPECTED_HEAD" || { echo "FAIL: HEAD $CURRENT_HEAD != expected $EXPECTED_HEAD"; exit 1; }

CURRENT_PARENT="$(git rev-parse HEAD^)"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: rev-parse HEAD^"; exit 1; }
test "$CURRENT_PARENT" = "$EXPECTED_PARENT" || { echo "FAIL: HEAD^ $CURRENT_PARENT != expected $EXPECTED_PARENT"; exit 1; }

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: rev-parse --abbrev-ref HEAD"; exit 1; }
test "$CURRENT_BRANCH" = "$EXPECTED_BRANCH" || { echo "FAIL: branch $CURRENT_BRANCH != expected $EXPECTED_BRANCH"; exit 1; }

CURRENT_UPSTREAM="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}')"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: rev-parse upstream"; exit 1; }
test "$CURRENT_UPSTREAM" = "origin/$EXPECTED_BRANCH" || { echo "FAIL: upstream $CURRENT_UPSTREAM != expected origin/$EXPECTED_BRANCH"; exit 1; }

git fetch origin --quiet; rc=$?
test "$rc" -eq 0 || { echo "FAIL: git fetch origin (all refs)"; exit 1; }
REMOTE_BRANCH_HEAD="$(git rev-parse "refs/remotes/origin/$EXPECTED_BRANCH")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: rev-parse refs/remotes/origin/$EXPECTED_BRANCH"; exit 1; }
test "$REMOTE_BRANCH_HEAD" = "$EXPECTED_HEAD" || { echo "FAIL: freshly-fetched origin/$EXPECTED_BRANCH $REMOTE_BRANCH_HEAD != expected $EXPECTED_HEAD -- PR #132 state drifted, do not amend blind"; exit 1; }
REMOTE_MAIN_HEAD="$(git rev-parse "refs/remotes/origin/main")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: rev-parse refs/remotes/origin/main"; exit 1; }
test "$REMOTE_MAIN_HEAD" = "$EXPECTED_PARENT" || { echo "FAIL: freshly-fetched origin/main $REMOTE_MAIN_HEAD != expected parent $EXPECTED_PARENT -- main advanced, stop for topology review before amending a stale-parent baseline"; exit 1; }
echo "HEAD/PARENT/BRANCH/UPSTREAM/BOTH-REMOTE-REFS CHECKS OK: HEAD=$CURRENT_HEAD parent=$CURRENT_PARENT"

# ---- 2. recover a pre-existing .custody_scratch only if it is exactly the known five-file
# H6 pre-commit-model failure state; otherwise refuse rather than guess. Dotfile-safe (L4): uses a
# dotglob array, not `ls -1` (which silently omits dotfiles). M1: no pipeline anywhere in this
# validation (a `printf | sort` command substitution's `$?` only proves `sort` succeeded, masking a
# failed `printf`), no external `basename` producer, and `-L` is checked so a symlink to a regular
# file cannot satisfy the "regular known files" contract. Five directory entries in one directory
# are inherently distinct names; proving each of the five matches one of the five known literal
# names via `case` (no fallthrough) therefore proves exact set equality without sorting. ----
if [ -e "$SCRATCH" ]; then
  ROOT="$(pwd -P)"; rc=$?
  test "$rc" -eq 0 || { echo "FAIL: pwd -P (root, recovery)"; exit 1; }
  SCRATCH_ABS="$(cd "$SCRATCH" && pwd -P)"; rc=$?
  test "$rc" -eq 0 || { echo "FAIL: pwd -P (scratch, recovery)"; exit 1; }
  test "$SCRATCH_ABS" = "$ROOT/.custody_scratch" || { echo "FAIL: refusing recovery -- resolved $SCRATCH_ABS != $ROOT/.custody_scratch"; exit 1; }

  shopt -s dotglob nullglob
  RAW_ENTRIES=("$SCRATCH_ABS"/*)
  shopt -u dotglob nullglob
  test "${#RAW_ENTRIES[@]}" -eq 5 || { echo "FAIL: scratch contains ${#RAW_ENTRIES[@]} entries, expected exactly 5 -- refusing to auto-recover"; exit 1; }

  i=0
  while [ "$i" -lt 5 ]; do
    entry="${RAW_ENTRIES[$i]}"
    test -f "$entry" || { echo "FAIL: scratch entry '$entry' is not a regular file -- refusing to auto-recover"; exit 1; }
    test -L "$entry" && { echo "FAIL: scratch entry '$entry' is a symlink -- refusing to auto-recover"; exit 1; }
    entry_name="${entry##*/}"
    case "$entry_name" in
      staged_actual.err|staged_actual.sorted.txt|staged_actual.txt|staged_expected.sorted.txt|staged_expected.txt) : ;;
      *) echo "FAIL: scratch entry '$entry_name' is not one of the five known H6-failure files -- refusing to auto-recover"; exit 1 ;;
    esac
    i=$((i + 1))
  done
  echo "SCRATCH INVENTORY CONFIRMED: exactly five distinct known H6-failure files"

  rm -f -- "$SCRATCH_ABS/staged_actual.err" "$SCRATCH_ABS/staged_actual.sorted.txt" \
           "$SCRATCH_ABS/staged_actual.txt" "$SCRATCH_ABS/staged_expected.sorted.txt" \
           "$SCRATCH_ABS/staged_expected.txt"; rc=$?
  test "$rc" -eq 0 || { echo "FAIL: rm -f known five H6-failure scratch files"; exit 1; }
  rmdir "$SCRATCH_ABS"; rc=$?
  test "$rc" -eq 0 || { echo "FAIL: rmdir $SCRATCH_ABS"; exit 1; }
  test ! -e "$SCRATCH_ABS" || { echo "FAIL: $SCRATCH_ABS still exists after recovery"; exit 1; }
  test ! -e "$SCRATCH" || { echo "FAIL: $SCRATCH still exists after recovery"; exit 1; }
  echo "RECOVERED KNOWN FAILED SCRATCH: $SCRATCH_ABS and $SCRATCH"
else
  echo "NO PRE-EXISTING SCRATCH TO RECOVER"
fi

# ---- L2 preflight: require the exact initial global porcelain state -- one MM entry at V3_PATH
# and nothing else. Runs after recovery, before recreating scratch, so it cannot be satisfied by
# leftover scratch noise and cannot miss an unrelated staged/unstaged/untracked path. ----
INITIAL_STATUS="$(git status --short)"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: initial git status --short rc=$rc"; exit 1; }
EXPECTED_INITIAL_STATUS="MM $V3_PATH"
test "$INITIAL_STATUS" = "$EXPECTED_INITIAL_STATUS" || { echo "FAIL: initial porcelain state '$INITIAL_STATUS' != expected '$EXPECTED_INITIAL_STATUS' -- unrelated staged/unstaged/untracked path present"; exit 1; }
echo "INITIAL GLOBAL STATE CONFIRMED: $INITIAL_STATUS"

# ---- 3. recreate scratch safely, LF-copy live _v3, stage only V3_PATH ----
test -e "$SCRATCH" && { echo "FAIL: scratch directory already occupied after recovery: $SCRATCH"; exit 1; }
mkdir "$SCRATCH"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: mkdir $SCRATCH"; exit 1; }

tr -d '\r' < "$LIVE_V3" > "$V3_PATH"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: LF-normalize copy to $V3_PATH"; exit 1; }

git add -- "$V3_PATH"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: git add $V3_PATH"; exit 1; }

# ---- L2: after staging, the GLOBAL unstaged tracked diff (no pathspec) must be empty -- proves
# nothing outside the custody set is dirty either, not just the eight custody paths ----
git diff --name-only > "$SCRATCH/global_unstaged_pre.txt" 2>"$SCRATCH/global_unstaged_pre.err"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: pre-hook global git diff --name-only rc=$rc"; exit 1; }
test -s "$SCRATCH/global_unstaged_pre.txt" && { echo "FAIL: unrelated unstaged tracked path present before the hook"; exit 1; }
echo "GLOBAL UNSTAGED DIFF EMPTY BEFORE THE HOOK"

# ---- 4. staged delta against HEAD must be exactly one path: V3_PATH (catches unrelated staged
# changes -- this is the check H6 could not do post-commit) ----
git diff --cached --name-only > "$SCRATCH/delta_vs_head.txt" 2>"$SCRATCH/delta_vs_head.err"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: git diff --cached --name-only rc=$rc"; exit 1; }
DELTA_LINES="$(wc -l < "$SCRATCH/delta_vs_head.txt")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: wc -l delta"; exit 1; }
test "$DELTA_LINES" -eq 1 || { echo "FAIL: staged delta vs HEAD has $DELTA_LINES paths, expected exactly 1"; exit 1; }
DELTA_PATH="$(cat "$SCRATCH/delta_vs_head.txt")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: cat delta path"; exit 1; }
test "$DELTA_PATH" = "$V3_PATH" || { echo "FAIL: staged delta path '$DELTA_PATH' != '$V3_PATH'"; exit 1; }
echo "STAGED DELTA VS HEAD IS EXACTLY: $DELTA_PATH"

# ---- 5. all eight custody paths exist in the index (membership -- distinct from the delta check
# above; a scoped membership check alone would miss extra staged paths, and the delta check alone
# would not prove baseline completeness, so both are required) ----
git ls-files --error-unmatch -- "${EIGHT[@]}" > "$SCRATCH/index_membership.txt" 2>"$SCRATCH/index_membership.err"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: git ls-files --error-unmatch rc=$rc"; exit 1; }
sort "$SCRATCH/index_membership.txt" -o "$SCRATCH/index_membership.sorted.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: sort index_membership"; exit 1; }
printf '%s\n' "${EIGHT[@]}" > "$SCRATCH/eight_expected.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: printf eight_expected"; exit 1; }
sort "$SCRATCH/eight_expected.txt" -o "$SCRATCH/eight_expected.sorted.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: sort eight_expected"; exit 1; }
diff "$SCRATCH/index_membership.sorted.txt" "$SCRATCH/eight_expected.sorted.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: index membership != eight-path allowlist"; exit 1; }
echo "INDEX MEMBERSHIP CONFIRMED: all eight custody paths present"

# ---- 6. HEAD's own parent-relative changed-path set is exactly the eight-path allowlist (proves
# the one-commit/eight-record baseline is still intact before amendment) ----
git diff --name-only "HEAD^" HEAD > "$SCRATCH/head_vs_parent.txt" 2>"$SCRATCH/head_vs_parent.err"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: git diff HEAD^ HEAD rc=$rc"; exit 1; }
sort "$SCRATCH/head_vs_parent.txt" -o "$SCRATCH/head_vs_parent.sorted.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: sort head_vs_parent"; exit 1; }
diff "$SCRATCH/head_vs_parent.sorted.txt" "$SCRATCH/eight_expected.sorted.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: HEAD parent-relative change set != eight-path allowlist"; exit 1; }
echo "HEAD PARENT-RELATIVE CHANGE SET CONFIRMED: exactly the eight-path baseline"

# ---- 7. live/working/staged record-8 IDs equal; staged must differ from HEAD's old blob (else the
# amend would be a no-op); cached whitespace check on both normal-text plan versions ----
LIVE_ID="$(git hash-object --path="$V3_PATH" -- "$LIVE_V3")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: hash-object live source"; exit 1; }
WORK_ID_PRE="$(git hash-object -- "$V3_PATH")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: hash-object working record 8"; exit 1; }
STAGED_ID_PRE="$(git rev-parse ":$V3_PATH")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: rev-parse staged record 8"; exit 1; }
HEAD_OLD_ID="$(git rev-parse "HEAD:$V3_PATH")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: rev-parse HEAD record 8"; exit 1; }
test -n "$LIVE_ID" || { echo "FAIL: empty live-source id"; exit 1; }
test "$LIVE_ID" = "$WORK_ID_PRE" || { echo "FAIL: live-source id != working-file id ($LIVE_ID != $WORK_ID_PRE)"; exit 1; }
test "$WORK_ID_PRE" = "$STAGED_ID_PRE" || { echo "FAIL: working-file id != staged id ($WORK_ID_PRE != $STAGED_ID_PRE)"; exit 1; }
test "$STAGED_ID_PRE" != "$HEAD_OLD_ID" || { echo "FAIL: staged id equals HEAD's old blob -- amend would be a no-op"; exit 1; }
echo "PRE-HOOK IDS EQUAL AND DIFFER FROM HEAD: staged=$STAGED_ID_PRE head_old=$HEAD_OLD_ID"

git diff --cached --check -- "$V2_PATH" "$V3_PATH"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: v2/v3 whitespace check rc=$rc"; exit 1; }

# ---- 8. configured hook with R2/R3 full-repository-status invariance, then re-prove every
# assertion above post-hook ----
: > "$SCRATCH/pre_hook_full_status.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: pre-create pre_hook_full_status.txt"; exit 1; }
: > "$SCRATCH/post_hook_full_status.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: pre-create post_hook_full_status.txt"; exit 1; }

git status --short --untracked-files=all > "$SCRATCH/pre_hook_full_status.txt" 2>&1; rc=$?
test "$rc" -eq 0 || { echo "FAIL: pre-hook full status rc=$rc"; exit 1; }

uv sync --extra dev; rc=$?
test "$rc" -eq 0 || { echo "FAIL: uv sync --extra dev"; exit 1; }
uv run pre-commit run trailing-whitespace --all-files; rc=$?
test "$rc" -eq 0 || { echo "FAIL: trailing-whitespace hook exit $rc"; exit 1; }

git status --short --untracked-files=all > "$SCRATCH/post_hook_full_status.txt" 2>&1; rc=$?
test "$rc" -eq 0 || { echo "FAIL: post-hook full status rc=$rc"; exit 1; }
diff "$SCRATCH/pre_hook_full_status.txt" "$SCRATCH/post_hook_full_status.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: repository-wide status changed after hook"; exit 1; }
echo "FULL-REPOSITORY STATUS UNCHANGED BY HOOK"

WORK_ID_POST="$(git hash-object -- "$V3_PATH")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: post-hook hash-object working record 8"; exit 1; }
STAGED_ID_POST="$(git rev-parse ":$V3_PATH")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: post-hook rev-parse staged record 8"; exit 1; }
test "$WORK_ID_POST" = "$WORK_ID_PRE" || { echo "FAIL: working id changed after hook"; exit 1; }
test "$STAGED_ID_POST" = "$STAGED_ID_PRE" || { echo "FAIL: staged id changed after hook"; exit 1; }
test "$WORK_ID_POST" = "$LIVE_ID" || { echo "FAIL: post-hook working id != live-source id"; exit 1; }
test "$STAGED_ID_POST" = "$LIVE_ID" || { echo "FAIL: post-hook staged id != live-source id"; exit 1; }
echo "POST-HOOK IDS EQUAL: $WORK_ID_POST"

git diff --cached --name-only > "$SCRATCH/delta_vs_head_post.txt" 2>"$SCRATCH/delta_vs_head_post.err"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: post-hook git diff --cached --name-only rc=$rc"; exit 1; }
DELTA_LINES_POST="$(wc -l < "$SCRATCH/delta_vs_head_post.txt")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: wc -l post-hook delta"; exit 1; }
test "$DELTA_LINES_POST" -eq 1 || { echo "FAIL: post-hook staged delta vs HEAD has $DELTA_LINES_POST paths, expected exactly 1"; exit 1; }
DELTA_PATH_POST="$(cat "$SCRATCH/delta_vs_head_post.txt")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: cat post-hook delta path"; exit 1; }
test "$DELTA_PATH_POST" = "$V3_PATH" || { echo "FAIL: post-hook staged delta path '$DELTA_PATH_POST' != '$V3_PATH'"; exit 1; }

git ls-files --error-unmatch -- "${EIGHT[@]}" > "$SCRATCH/index_membership_post.txt" 2>"$SCRATCH/index_membership_post.err"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: post-hook git ls-files --error-unmatch rc=$rc"; exit 1; }
sort "$SCRATCH/index_membership_post.txt" -o "$SCRATCH/index_membership_post.sorted.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: sort post-hook index_membership"; exit 1; }
diff "$SCRATCH/index_membership_post.sorted.txt" "$SCRATCH/eight_expected.sorted.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: post-hook index membership != eight-path allowlist"; exit 1; }

# ---- L2: post-hook, the GLOBAL unstaged tracked diff (no EIGHT pathspec) must be empty -- a hook
# could alter an unrelated already-unstaged path without changing its status code, which a
# custody-scoped check would never catch ----
git diff --name-only > "$SCRATCH/global_unstaged_post.txt" 2>"$SCRATCH/global_unstaged_post.err"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: post-hook global git diff --name-only rc=$rc"; exit 1; }
test -s "$SCRATCH/global_unstaged_post.txt" && { echo "FAIL: unstaged changes remain somewhere in the repository after the hook"; exit 1; }
echo "POST-HOOK RE-VERIFICATION COMPLETE: one-path delta, eight-path membership, global unstaged diff empty"

# ---- 9 (L4-corrected). clean scratch through the exact-path guard FIRST, then authoritative final
# reporting -- the pre-cleanup git status/diff calls this block used to run had unchecked return
# codes and proved nothing about the state *after* cleanup, which is the state that actually gets
# amended. STOP -- never amend or force-push from inside this block. ----
ROOT="$(pwd -P)"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: pwd -P (repo root, final cleanup)"; exit 1; }
SCRATCH_ABS="$(cd "$SCRATCH" && pwd -P)"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: pwd -P (scratch dir, final cleanup)"; exit 1; }
test "$SCRATCH_ABS" = "$ROOT/.custody_scratch" || {
  echo "FAIL: refusing recursive delete -- resolved $SCRATCH_ABS != $ROOT/.custody_scratch"; exit 1;
}
rm -rf -- "$SCRATCH_ABS"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: rm -rf $SCRATCH_ABS"; exit 1; }
test ! -e "$SCRATCH_ABS" || { echo "FAIL: $SCRATCH_ABS still exists after cleanup"; exit 1; }
test ! -e "$SCRATCH" || { echo "FAIL: $SCRATCH still exists after cleanup"; exit 1; }
echo "CLEANUP VERIFIED ABSENT: $SCRATCH_ABS and $SCRATCH"

FINAL_STATUS="$(git status --short)"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: final git status --short rc=$rc"; exit 1; }
EXPECTED_FINAL_STATUS="M  $V3_PATH"
test "$FINAL_STATUS" = "$EXPECTED_FINAL_STATUS" || { echo "FAIL: final porcelain state '$FINAL_STATUS' != expected '$EXPECTED_FINAL_STATUS'"; exit 1; }
echo "$FINAL_STATUS"

FINAL_DIFFSTAT="$(git diff --cached --stat)"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: final git diff --cached --stat rc=$rc"; exit 1; }
test -n "$FINAL_DIFFSTAT" || { echo "FAIL: empty final cached diffstat"; exit 1; }
echo "$FINAL_DIFFSTAT"

echo "FINAL STAGED RECORD 8 ID: $STAGED_ID_POST"
echo "PRE-AMEND HEAD: $CURRENT_HEAD"
echo "K3 PASSED -- STOP HERE. Do not run 'git commit --amend' or 'git push --force-with-lease' from"
echo "this block. Report this output and stop for reviewer inspection before either command runs."
```

K3 never runs `git commit --amend` or `git push --force-with-lease` itself; those remain separate,
explicitly operator-authorized commands run only after K3's output is reviewed.

**K4 — pre-merge-freshness verifier for the second amend state (external evidence, not a
checkbox).** K3 verified the **first post-commit replacement** of an existing record 8 — HEAD
already contained a committed record 8 (blob `2a6f430e...`) when K3 ran; K3 verified that the
amend would replace it with `13e87ed4...`, not that no prior committed record 8 existed. That
first amend has since completed (`2bae3ed2645e5239c366b50e98bd45ed1dffcc2d`, parent
`e2496ced8580ff0318bf263c5c43eb446bea10e0`), and the pre-merge freshness audit then found this
document's own current-state prose stale (N1, corrected above). Refreshing tracked record 8 from
that correction creates a **second**, distinct amend state: a committed record 8 already exists at
a known old blob (`13e87ed4a854b63071f0ca9b1ab6eea6995f7fd7`) and must be replaced, not created.
**Historical K3 is untouched** — this is a separate, standalone, self-contained verifier for this
second state, one continuous session, relying on no other block's shell state.

```bash
# ---- K4 pre-merge-freshness verifier: standalone; proves the corrected record 8 is safe to
# `git commit --amend` a second time, then stops. Never runs the amend or the force-push itself. ----
SDD="D:/Projects/Development/Python/optimus-cost-agent-wt-codex/.superpowers/sdd"
LIVE_V3="$SDD/a2a-not-shipped-closure-plan_v3-DRAFT.md"
V2_PATH="docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v2.md"
V3_PATH="docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v3.md"
EIGHT=(
  "docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md"
  "docs/superpowers/reviews/evidence-handoff-a2a-ledger-sealed-reviewer-findings.md"
  "docs/superpowers/reviews/evidence-handoff-a2a-remediation-scoping-review.md"
  "docs/superpowers/reviews/evidence-handoff-a2a-not-shipped-closure-review.md"
  "docs/superpowers/specs/evidence-handoff-a2a-ledger-remediation-scoping.md"
  "docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure.md"
  "$V2_PATH"
  "$V3_PATH"
)
test "${#EIGHT[@]}" -eq 8 || { echo "FAIL: EIGHT length ${#EIGHT[@]}"; exit 1; }
SCRATCH=".custody_scratch"

EXPECTED_HEAD="2bae3ed2645e5239c366b50e98bd45ed1dffcc2d"
EXPECTED_PARENT="e2496ced8580ff0318bf263c5c43eb446bea10e0"
EXPECTED_BRANCH="agent/claude/a2a-audit-docs-preservation"
EXPECTED_OLD_RECORD8_BLOB="13e87ed4a854b63071f0ca9b1ab6eea6995f7fd7"

# ---- 1. HEAD, parent, branch, upstream, old committed record-8 blob; then one fetch of ALL refs
# and pin both remote-tracking refs (same discipline as K3's L3 fix) ----
CURRENT_HEAD="$(git rev-parse HEAD)"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: rev-parse HEAD"; exit 1; }
test "$CURRENT_HEAD" = "$EXPECTED_HEAD" || { echo "FAIL: HEAD $CURRENT_HEAD != expected $EXPECTED_HEAD"; exit 1; }

CURRENT_PARENT="$(git rev-parse HEAD^)"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: rev-parse HEAD^"; exit 1; }
test "$CURRENT_PARENT" = "$EXPECTED_PARENT" || { echo "FAIL: HEAD^ $CURRENT_PARENT != expected $EXPECTED_PARENT"; exit 1; }

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: rev-parse --abbrev-ref HEAD"; exit 1; }
test "$CURRENT_BRANCH" = "$EXPECTED_BRANCH" || { echo "FAIL: branch $CURRENT_BRANCH != expected $EXPECTED_BRANCH"; exit 1; }

CURRENT_UPSTREAM="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}')"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: rev-parse upstream"; exit 1; }
test "$CURRENT_UPSTREAM" = "origin/$EXPECTED_BRANCH" || { echo "FAIL: upstream $CURRENT_UPSTREAM != expected origin/$EXPECTED_BRANCH"; exit 1; }

OLD_RECORD8_BLOB="$(git rev-parse "HEAD:$V3_PATH")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: rev-parse HEAD record 8"; exit 1; }
test "$OLD_RECORD8_BLOB" = "$EXPECTED_OLD_RECORD8_BLOB" || { echo "FAIL: committed record 8 $OLD_RECORD8_BLOB != expected old blob $EXPECTED_OLD_RECORD8_BLOB"; exit 1; }

git fetch origin --quiet; rc=$?
test "$rc" -eq 0 || { echo "FAIL: git fetch origin (all refs)"; exit 1; }
REMOTE_BRANCH_HEAD="$(git rev-parse "refs/remotes/origin/$EXPECTED_BRANCH")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: rev-parse refs/remotes/origin/$EXPECTED_BRANCH"; exit 1; }
test "$REMOTE_BRANCH_HEAD" = "$EXPECTED_HEAD" || { echo "FAIL: freshly-fetched origin/$EXPECTED_BRANCH $REMOTE_BRANCH_HEAD != expected $EXPECTED_HEAD -- PR #132 state drifted, do not amend blind"; exit 1; }
REMOTE_MAIN_HEAD="$(git rev-parse "refs/remotes/origin/main")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: rev-parse refs/remotes/origin/main"; exit 1; }
test "$REMOTE_MAIN_HEAD" = "$EXPECTED_PARENT" || { echo "FAIL: freshly-fetched origin/main $REMOTE_MAIN_HEAD != expected parent $EXPECTED_PARENT -- main advanced, stop for topology review"; exit 1; }
echo "HEAD/PARENT/BRANCH/UPSTREAM/BOTH-REMOTE-REFS/OLD-RECORD8-BLOB CHECKS OK: HEAD=$CURRENT_HEAD old_record8=$OLD_RECORD8_BLOB"

# ---- 2. recover a pre-existing .custody_scratch only if every entry is a regular non-symlink file
# whose name is one of K4's own known scratch filenames (this block's full production surface, not
# K3's, since K3 remains historically unchanged); otherwise refuse rather than guess. Same
# no-pipeline, no-external-basename, case-based contract as K3's M1 fix -- accepts a zero-to-full-
# set contract: zero entries (K4 itself can leave an empty scratch directory if execution stops
# right after the checked `mkdir` but before the first file is written) through the full set,
# since a partial failure can stop at any of K4's own steps. Refusal of unknown, non-regular, or
# symlink entries is never weakened. ----
if [ -e "$SCRATCH" ]; then
  ROOT="$(pwd -P)"; rc=$?
  test "$rc" -eq 0 || { echo "FAIL: pwd -P (root, recovery)"; exit 1; }
  SCRATCH_ABS="$(cd "$SCRATCH" && pwd -P)"; rc=$?
  test "$rc" -eq 0 || { echo "FAIL: pwd -P (scratch, recovery)"; exit 1; }
  test "$SCRATCH_ABS" = "$ROOT/.custody_scratch" || { echo "FAIL: refusing recovery -- resolved $SCRATCH_ABS != $ROOT/.custody_scratch"; exit 1; }

  shopt -s dotglob nullglob
  RAW_ENTRIES=("$SCRATCH_ABS"/*)
  shopt -u dotglob nullglob

  if [ "${#RAW_ENTRIES[@]}" -eq 0 ]; then
    rmdir "$SCRATCH_ABS"; rc=$?
    test "$rc" -eq 0 || { echo "FAIL: rmdir empty $SCRATCH_ABS"; exit 1; }
    test ! -e "$SCRATCH_ABS" || { echo "FAIL: $SCRATCH_ABS still exists after empty-directory recovery"; exit 1; }
    test ! -e "$SCRATCH" || { echo "FAIL: $SCRATCH still exists after empty-directory recovery"; exit 1; }
    echo "RECOVERED EMPTY SCRATCH: $SCRATCH_ABS and $SCRATCH"
  else
    i=0
    while [ "$i" -lt "${#RAW_ENTRIES[@]}" ]; do
      entry="${RAW_ENTRIES[$i]}"
      test -f "$entry" || { echo "FAIL: scratch entry '$entry' is not a regular file -- refusing to auto-recover"; exit 1; }
      test -L "$entry" && { echo "FAIL: scratch entry '$entry' is a symlink -- refusing to auto-recover"; exit 1; }
      entry_name="${entry##*/}"
      case "$entry_name" in
        global_unstaged_pre.txt|global_unstaged_pre.err|delta_vs_head.txt|delta_vs_head.err|\
        index_membership.txt|index_membership.err|index_membership.sorted.txt|\
        eight_expected.txt|eight_expected.sorted.txt|\
        head_vs_parent.txt|head_vs_parent.err|head_vs_parent.sorted.txt|\
        pre_hook_full_status.txt|post_hook_full_status.txt|\
        delta_vs_head_post.txt|delta_vs_head_post.err|\
        index_membership_post.txt|index_membership_post.err|index_membership_post.sorted.txt|\
        global_unstaged_post.txt|global_unstaged_post.err) : ;;
        *) echo "FAIL: scratch entry '$entry_name' is not one of K4's known scratch files -- refusing to auto-recover"; exit 1 ;;
      esac
      i=$((i + 1))
    done
    echo "SCRATCH INVENTORY CONFIRMED: ${#RAW_ENTRIES[@]} entries, all known K4 scratch files"

    i=0
    while [ "$i" -lt "${#RAW_ENTRIES[@]}" ]; do
      rm -f -- "${RAW_ENTRIES[$i]}"; rc=$?
      test "$rc" -eq 0 || { echo "FAIL: rm -f ${RAW_ENTRIES[$i]}"; exit 1; }
      i=$((i + 1))
    done
    rmdir "$SCRATCH_ABS"; rc=$?
    test "$rc" -eq 0 || { echo "FAIL: rmdir $SCRATCH_ABS"; exit 1; }
    test ! -e "$SCRATCH_ABS" || { echo "FAIL: $SCRATCH_ABS still exists after recovery"; exit 1; }
    test ! -e "$SCRATCH" || { echo "FAIL: $SCRATCH still exists after recovery"; exit 1; }
    echo "RECOVERED KNOWN K4 SCRATCH: $SCRATCH_ABS and $SCRATCH"
  fi
else
  echo "NO PRE-EXISTING SCRATCH TO RECOVER"
fi

# ---- 3. exact pre-stage global state: one unstaged modified record 8, nothing else; LF-refresh
# from ignored live source; stage only that path ----
INITIAL_STATUS="$(git status --short)"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: initial git status --short rc=$rc"; exit 1; }
EXPECTED_INITIAL_STATUS=" M $V3_PATH"
test "$INITIAL_STATUS" = "$EXPECTED_INITIAL_STATUS" || { echo "FAIL: initial porcelain state '$INITIAL_STATUS' != expected '$EXPECTED_INITIAL_STATUS' -- unrelated staged/unstaged/untracked path present"; exit 1; }
echo "INITIAL GLOBAL STATE CONFIRMED: $INITIAL_STATUS"

test -e "$SCRATCH" && { echo "FAIL: scratch directory already occupied after recovery: $SCRATCH"; exit 1; }
mkdir "$SCRATCH"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: mkdir $SCRATCH"; exit 1; }

tr -d '\r' < "$LIVE_V3" > "$V3_PATH"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: LF-normalize copy to $V3_PATH"; exit 1; }

git diff --name-only > "$SCRATCH/global_unstaged_pre.txt" 2>"$SCRATCH/global_unstaged_pre.err"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: pre-stage global git diff --name-only rc=$rc"; exit 1; }
DELTA_LINES_PRESTAGE="$(wc -l < "$SCRATCH/global_unstaged_pre.txt")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: wc -l pre-stage global unstaged"; exit 1; }
test "$DELTA_LINES_PRESTAGE" -eq 1 || { echo "FAIL: pre-stage global unstaged diff has $DELTA_LINES_PRESTAGE paths, expected exactly 1"; exit 1; }
PRESTAGE_PATH="$(cat "$SCRATCH/global_unstaged_pre.txt")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: cat pre-stage global unstaged path"; exit 1; }
test "$PRESTAGE_PATH" = "$V3_PATH" || { echo "FAIL: pre-stage global unstaged path '$PRESTAGE_PATH' != '$V3_PATH'"; exit 1; }

git add -- "$V3_PATH"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: git add $V3_PATH"; exit 1; }
echo "STAGED ONLY: $V3_PATH"

# ---- 4. complete staged delta against HEAD is exactly record 8; all eight custody paths exist in
# the index; HEAD's own parent-relative changed-path set is exactly the eight-path allowlist ----
git diff --cached --name-only > "$SCRATCH/delta_vs_head.txt" 2>"$SCRATCH/delta_vs_head.err"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: git diff --cached --name-only rc=$rc"; exit 1; }
DELTA_LINES="$(wc -l < "$SCRATCH/delta_vs_head.txt")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: wc -l delta"; exit 1; }
test "$DELTA_LINES" -eq 1 || { echo "FAIL: staged delta vs HEAD has $DELTA_LINES paths, expected exactly 1"; exit 1; }
DELTA_PATH="$(cat "$SCRATCH/delta_vs_head.txt")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: cat delta path"; exit 1; }
test "$DELTA_PATH" = "$V3_PATH" || { echo "FAIL: staged delta path '$DELTA_PATH' != '$V3_PATH'"; exit 1; }
echo "STAGED DELTA VS HEAD IS EXACTLY: $DELTA_PATH"

git ls-files --error-unmatch -- "${EIGHT[@]}" > "$SCRATCH/index_membership.txt" 2>"$SCRATCH/index_membership.err"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: git ls-files --error-unmatch rc=$rc"; exit 1; }
sort "$SCRATCH/index_membership.txt" -o "$SCRATCH/index_membership.sorted.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: sort index_membership"; exit 1; }
printf '%s\n' "${EIGHT[@]}" > "$SCRATCH/eight_expected.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: printf eight_expected"; exit 1; }
sort "$SCRATCH/eight_expected.txt" -o "$SCRATCH/eight_expected.sorted.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: sort eight_expected"; exit 1; }
diff "$SCRATCH/index_membership.sorted.txt" "$SCRATCH/eight_expected.sorted.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: index membership != eight-path allowlist"; exit 1; }
echo "INDEX MEMBERSHIP CONFIRMED: all eight custody paths present"

git diff --name-only "HEAD^" HEAD > "$SCRATCH/head_vs_parent.txt" 2>"$SCRATCH/head_vs_parent.err"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: git diff HEAD^ HEAD rc=$rc"; exit 1; }
sort "$SCRATCH/head_vs_parent.txt" -o "$SCRATCH/head_vs_parent.sorted.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: sort head_vs_parent"; exit 1; }
diff "$SCRATCH/head_vs_parent.sorted.txt" "$SCRATCH/eight_expected.sorted.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: HEAD parent-relative change set != eight-path allowlist"; exit 1; }
echo "HEAD PARENT-RELATIVE CHANGE SET CONFIRMED: exactly the eight-path baseline"

# ---- 5. live/working/staged record-8 IDs equal and differ from the old committed blob; cached
# whitespace check; configured hook with full-repository-status invariance ----
LIVE_ID="$(git hash-object --path="$V3_PATH" -- "$LIVE_V3")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: hash-object live source"; exit 1; }
WORK_ID_PRE="$(git hash-object -- "$V3_PATH")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: hash-object working record 8"; exit 1; }
STAGED_ID_PRE="$(git rev-parse ":$V3_PATH")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: rev-parse staged record 8"; exit 1; }
test -n "$LIVE_ID" || { echo "FAIL: empty live-source id"; exit 1; }
test "$LIVE_ID" = "$WORK_ID_PRE" || { echo "FAIL: live-source id != working-file id ($LIVE_ID != $WORK_ID_PRE)"; exit 1; }
test "$WORK_ID_PRE" = "$STAGED_ID_PRE" || { echo "FAIL: working-file id != staged id ($WORK_ID_PRE != $STAGED_ID_PRE)"; exit 1; }
test "$STAGED_ID_PRE" != "$OLD_RECORD8_BLOB" || { echo "FAIL: staged id equals the old committed blob -- amend would be a no-op"; exit 1; }
echo "PRE-HOOK IDS EQUAL AND DIFFER FROM OLD COMMITTED BLOB: staged=$STAGED_ID_PRE old=$OLD_RECORD8_BLOB"

git diff --cached --check -- "$V2_PATH" "$V3_PATH"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: v2/v3 whitespace check rc=$rc"; exit 1; }

: > "$SCRATCH/pre_hook_full_status.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: pre-create pre_hook_full_status.txt"; exit 1; }
: > "$SCRATCH/post_hook_full_status.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: pre-create post_hook_full_status.txt"; exit 1; }

git status --short --untracked-files=all > "$SCRATCH/pre_hook_full_status.txt" 2>&1; rc=$?
test "$rc" -eq 0 || { echo "FAIL: pre-hook full status rc=$rc"; exit 1; }

uv sync --extra dev; rc=$?
test "$rc" -eq 0 || { echo "FAIL: uv sync --extra dev"; exit 1; }
uv run pre-commit run trailing-whitespace --all-files; rc=$?
test "$rc" -eq 0 || { echo "FAIL: trailing-whitespace hook exit $rc"; exit 1; }

git status --short --untracked-files=all > "$SCRATCH/post_hook_full_status.txt" 2>&1; rc=$?
test "$rc" -eq 0 || { echo "FAIL: post-hook full status rc=$rc"; exit 1; }
diff "$SCRATCH/pre_hook_full_status.txt" "$SCRATCH/post_hook_full_status.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: repository-wide status changed after hook"; exit 1; }
echo "FULL-REPOSITORY STATUS UNCHANGED BY HOOK"

# ---- 6. repeat identity, delta, membership, and global unstaged-cleanliness proofs post-hook ----
WORK_ID_POST="$(git hash-object -- "$V3_PATH")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: post-hook hash-object working record 8"; exit 1; }
STAGED_ID_POST="$(git rev-parse ":$V3_PATH")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: post-hook rev-parse staged record 8"; exit 1; }
test "$WORK_ID_POST" = "$WORK_ID_PRE" || { echo "FAIL: working id changed after hook"; exit 1; }
test "$STAGED_ID_POST" = "$STAGED_ID_PRE" || { echo "FAIL: staged id changed after hook"; exit 1; }
test "$WORK_ID_POST" = "$LIVE_ID" || { echo "FAIL: post-hook working id != live-source id"; exit 1; }
test "$STAGED_ID_POST" = "$LIVE_ID" || { echo "FAIL: post-hook staged id != live-source id"; exit 1; }
echo "POST-HOOK IDS EQUAL: $WORK_ID_POST"

git diff --cached --name-only > "$SCRATCH/delta_vs_head_post.txt" 2>"$SCRATCH/delta_vs_head_post.err"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: post-hook git diff --cached --name-only rc=$rc"; exit 1; }
DELTA_LINES_POST="$(wc -l < "$SCRATCH/delta_vs_head_post.txt")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: wc -l post-hook delta"; exit 1; }
test "$DELTA_LINES_POST" -eq 1 || { echo "FAIL: post-hook staged delta vs HEAD has $DELTA_LINES_POST paths, expected exactly 1"; exit 1; }
DELTA_PATH_POST="$(cat "$SCRATCH/delta_vs_head_post.txt")"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: cat post-hook delta path"; exit 1; }
test "$DELTA_PATH_POST" = "$V3_PATH" || { echo "FAIL: post-hook staged delta path '$DELTA_PATH_POST' != '$V3_PATH'"; exit 1; }

git ls-files --error-unmatch -- "${EIGHT[@]}" > "$SCRATCH/index_membership_post.txt" 2>"$SCRATCH/index_membership_post.err"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: post-hook git ls-files --error-unmatch rc=$rc"; exit 1; }
sort "$SCRATCH/index_membership_post.txt" -o "$SCRATCH/index_membership_post.sorted.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: sort post-hook index_membership"; exit 1; }
diff "$SCRATCH/index_membership_post.sorted.txt" "$SCRATCH/eight_expected.sorted.txt"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: post-hook index membership != eight-path allowlist"; exit 1; }

git diff --name-only > "$SCRATCH/global_unstaged_post.txt" 2>"$SCRATCH/global_unstaged_post.err"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: post-hook global git diff --name-only rc=$rc"; exit 1; }
test -s "$SCRATCH/global_unstaged_post.txt" && { echo "FAIL: unstaged changes remain somewhere in the repository after the hook"; exit 1; }
echo "POST-HOOK RE-VERIFICATION COMPLETE: one-path delta, eight-path membership, global unstaged diff empty"

# ---- 7. clean scratch through the exact-path guard FIRST, then authoritative final reporting;
# STOP -- never amend or force-push from inside this block ----
ROOT="$(pwd -P)"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: pwd -P (repo root, final cleanup)"; exit 1; }
SCRATCH_ABS="$(cd "$SCRATCH" && pwd -P)"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: pwd -P (scratch dir, final cleanup)"; exit 1; }
test "$SCRATCH_ABS" = "$ROOT/.custody_scratch" || {
  echo "FAIL: refusing recursive delete -- resolved $SCRATCH_ABS != $ROOT/.custody_scratch"; exit 1;
}
rm -rf -- "$SCRATCH_ABS"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: rm -rf $SCRATCH_ABS"; exit 1; }
test ! -e "$SCRATCH_ABS" || { echo "FAIL: $SCRATCH_ABS still exists after cleanup"; exit 1; }
test ! -e "$SCRATCH" || { echo "FAIL: $SCRATCH still exists after cleanup"; exit 1; }
echo "CLEANUP VERIFIED ABSENT: $SCRATCH_ABS and $SCRATCH"

FINAL_STATUS="$(git status --short)"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: final git status --short rc=$rc"; exit 1; }
EXPECTED_FINAL_STATUS="M  $V3_PATH"
test "$FINAL_STATUS" = "$EXPECTED_FINAL_STATUS" || { echo "FAIL: final porcelain state '$FINAL_STATUS' != expected '$EXPECTED_FINAL_STATUS'"; exit 1; }
echo "$FINAL_STATUS"

FINAL_DIFFSTAT="$(git diff --cached --stat)"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: final git diff --cached --stat rc=$rc"; exit 1; }
test -n "$FINAL_DIFFSTAT" || { echo "FAIL: empty final cached diffstat"; exit 1; }
echo "$FINAL_DIFFSTAT"

echo "FINAL STAGED RECORD 8 ID: $STAGED_ID_POST"
echo "PRE-SECOND-AMEND HEAD: $CURRENT_HEAD"
echo "K4 PASSED -- STOP HERE. Do not run 'git commit --amend' or 'git push --force-with-lease' from"
echo "this block. Report this output and stop for reviewer inspection before either command runs."
```

K4 never runs `git commit --amend` or `git push --force-with-lease` itself; those remain separate,
explicitly operator-authorized commands run only after K4's output is reviewed and a new
force-with-lease is issued against the current PR head `2bae3ed2645e5239c366b50e98bd45ed1dffcc2d`.

---

## Task 2 — atomic link, ownership, and allowlist

- [ ] **Step 1 (RED):** Add **four** literal paths to `PRODUCT_OWNED_DOCS`:
      `docs/superpowers/specs/evidence-handoff-a2a-ledger-remediation-scoping.md`,
      `docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure.md` (historical v1),
      `docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v2.md` (historical v2, per
      F1 — superseded by v3, no longer live), and
      `docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v3.md` (live). All three
      plan versions stay product-owned, matching the risk-slice v1/v2-both-owned precedent
      (`test_open_work_pool_hygiene.py:226-227`; product pool lines 81-82), extended one level for
      this plan's own v1→v2→v3 chain. Narrow docs test → expect FAIL on
      `listed_docs == PRODUCT_OWNED_DOCS`.
- [ ] **Step 2 (GREEN):** In the same cycle add all four to the pool's
      `## Product-owned documents temporarily hosted in Optimus` section and add the pool links.
      Re-run narrow docs test → green.
- [ ] **Step 3:** Assert no `reviews/` artifact appears as a markdown link anywhere in the pool.
      Stop for review.

## Task 3 — A2A row, six slice rows, Priority on Feature slices

New header: `Identity | State | Priority | Scope detail`. Every row `MEDIUM` except
`EVIDENCE-HANDOFF-FEAT-CREDENTIAL-LIFECYCLE`, whose authored **HIGH** moves from State prose into the
Priority cell with no duplicate inline label left behind.

A2A row must state: **not shipped / not supported / not trusted**; audit at `e5f7e339` returned NOT
SOUND (17 findings, 3 Critical); corrected facts — tip **`658042d`** (not `72c3b82`), **25** commits
from `8735885`, PR **#128** merged `7b5865f`, PR **#129** merged `74f7104`; **code remains merged and
console scripts remain present**; and verbatim:

> The feature is not on the ordinary Optimus runtime path and lifecycle activation is opt-in by
> default. However, merged code and installed console entry points remain manually callable. They
> are unsupported and untrusted and must not be enabled or used for trusted workflows.

The row links **live `_v3`** (`docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v3.md`)
and the tracked **scoping contract**
(`docs/superpowers/specs/evidence-handoff-a2a-ledger-remediation-scoping.md`) as markdown links, and
may reference historical v1 and historical `_v2` without making either the execution target. It
references the independent audit, sealed reviewer findings, scoping review chronology, and this
closure review chronology by **backticked path only** — never as a markdown link, per the pool's
product-owned-document link allowlist:

- `docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md`
- `docs/superpowers/reviews/evidence-handoff-a2a-ledger-sealed-reviewer-findings.md`
- `docs/superpowers/reviews/evidence-handoff-a2a-remediation-scoping-review.md`
- `docs/superpowers/reviews/evidence-handoff-a2a-not-shipped-closure-review.md`

Six new rows, `Tracked, Not Yet Scheduled` 2026-08-12, `MEDIUM`, order `Pre-A → A → {B,C,D} → E → F`:
`LEDGER-COMPOSITION` (C1,C3,H7,H9,M15) · `LEDGER-INTEGRITY-BOUNDARY` (C2,H13,M16c) ·
`LEDGER-DATAPATH` (H4,H5,H6) · `LEDGER-RUNTIME-BOUNDARY` (H8,M14,M16b) ·
`LEDGER-AUDIT-WIRING` (M16a) · `LEDGER-EVIDENCE-DOD` (H10,H11,H12b).

- [ ] **Step 1 (RED):** Add the six IDs to `PRODUCT_FEATURE_IDS`; replace
      `test_a2a_ledger_reachability_blocker_is_resolved_and_design_is_owned` with
      `test_a2a_ledger_row_records_not_shipped_state` asserting the wording, `658042d`, `25`,
      `PR #128`, `PR #129`, default-off, no ordinary Optimus ledger/runtime import, the
      installed-entry-point warning, the scoping-contract markdown link, the four backticked-only
      review references, and **absence** of `**Closed**` and `72c3b82`. Add the exact
      Feature-slices Priority contract: exactly one `Priority` header column; every body-row cell
      is exactly one of `HIGH`, `MEDIUM`, or `LOW`; `EVIDENCE-HANDOFF-FEAT-CREDENTIAL-LIFECYCLE` is
      the **sole** `HIGH` row and every other row is `MEDIUM`; and no body line anywhere in the pool
      matches a residual inline `Priority:` or `**HIGH** priority` label. Expect FAIL.
- [ ] **Step 2 (GREEN):** Make the edits; re-run to green.
- [ ] **Step 3:** Verify no `Plan N` token entered the pool. Stop for review.

## Task 4 — obligations table

`## A2A ledger audit obligations` — `| Obligation | Severity | Owning slice | Status | Priority |`,
**20 rows**, Priority `MEDIUM` throughout.

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

Counts: 3 CRITICAL, 11 HIGH, 6 MEDIUM. Owners: COMPOSITION 5, INTEGRITY-BOUNDARY 3, DATAPATH 3,
RUNTIME-BOUNDARY 3, EVIDENCE-DOD 3, AUDIT-WIRING 1, gate contract 1, closure plan 1. This table is an
index projecting slice state, not a second owner.

- [ ] **Step 1 (RED):** Encode `EXPECTED_OBLIGATIONS` as the exact `{obligation: (severity, owner)}`
      mapping; assert table equality, Status `Open|Closed` with M17 the sole `Closed`, all six slice
      states `Tracked, Not Yet Scheduled`, the parent A2A row not `Closed`, and this table's Priority
      contract. Expect FAIL.
- [ ] **Step 2 (GREEN):** Add the table; re-run to green.
- [ ] **Step 3:** Stop for review.

## Task 5 — adjacent custody, freshness, gates, closure commit

Pool custody edits, all four rows: **`A2A-LEDGER-DESIGN-REFRESH`** loses operation-entry guard
custody (now `LEDGER-INTEGRITY-BOUNDARY`), retains design v2 restatement / Docker-wslc / session
Option A. **`AT-REST-INTEGRITY`** retains periodic post-readiness verification; loses
operator-triggered on-demand full-audit wording. **`CREDENTIAL-LIFECYCLE`** retains OAuth/rotation and
Cursor discovery interoperability, and states the Evidence/DoD slice dependency or the obligation to
narrow the future native-client claim. **`PEER-LIVENESS-SIGNAL`** drops stale "in-flight Task 6/10/11"
phrasing.

**Optimus-pool correction (only Optimus edit authorized):** line ~1397 says *"as the A2A ledger's
hardened-Redis fallback path"*; no such path exists (the runtime is PostgreSQL). Narrow to generic
future consolidated-startup work.

- [ ] **Step 1 (RED):** Pin each adjacent-custody clause against restored dual ownership; pin the
      corrected Optimus Redis wording. Expect FAIL.
- [ ] **Step 2 (GREEN):** Make the edits; narrow docs test → green.
- [ ] **Step 3:** Full gate set below. A known flake is diagnostic context, **not** permission to
      check a failed gate: isolate, then rerun the original full command to exit 0. A
      deselected-or-failed command never becomes `[x]`.
- [ ] **Step 4:** Write the tracked custody manifest — deferred here from Task 1E per the chosen
      topology — into record 4 **outside** its preserved region, labelling every digest explicitly as
      a hash **of the custody commit**. The manifest covers **all eight** custody-baseline paths, not
      only the six preserved records. Both record 7 (`_v2`, now historical) and record 8 (`_v3`,
      live) get manifest entries that are digests **as committed in the custody commit** — i.e. the
      versions at the end of Task 1D, before this Task 5 further edits `_v3`'s checkboxes for the
      closure commit. Record 8's entry will legitimately differ from `_v3`'s working-tree bytes at
      the moment this step runs; record it as the custody-baseline digest, not as a mismatch to
      reconcile. Record 7 (`_v2`) is not touched again after Task 1D, so its manifest entry should
      match its then-current working-tree bytes exactly — a mismatch there **is** a real problem:

      ```bash
      CUSTODY_COMMIT="<paste the SHA reported after Task 1E Step 2>"

      EIGHT=(
        docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md
        docs/superpowers/reviews/evidence-handoff-a2a-ledger-sealed-reviewer-findings.md
        docs/superpowers/reviews/evidence-handoff-a2a-remediation-scoping-review.md
        docs/superpowers/reviews/evidence-handoff-a2a-not-shipped-closure-review.md
        docs/superpowers/specs/evidence-handoff-a2a-ledger-remediation-scoping.md
        docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure.md
        docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v2.md
        docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v3.md
      )
      test "${#EIGHT[@]}" -eq 8 || { echo "FAIL: EIGHT length ${#EIGHT[@]}"; exit 1; }

      : > /tmp/custody_manifest.txt
      i=0
      while [ "$i" -lt 8 ]; do
        P="${EIGHT[$i]}"
        git show "${CUSTODY_COMMIT}:${P}" > "/tmp/manifest_blob_$i.bin" 2>"/tmp/manifest_blob_$i.err"; rc=$?
        test "$rc" -eq 0 || { echo "FAIL: git show ${CUSTODY_COMMIT}:${P}"; exit 1; }
        sha256sum "/tmp/manifest_blob_$i.bin" > "/tmp/manifest_hash_$i.txt"; rc=$?
        test "$rc" -eq 0 || { echo "FAIL: sha256sum $P"; exit 1; }
        read -r h _ < "/tmp/manifest_hash_$i.txt"; rc=$?
        test "$rc" -eq 0 || { echo "FAIL: parse hash $P"; exit 1; }
        [[ "$h" =~ ^[0-9a-fA-F]{64}$ ]] || { echo "FAIL: invalid SHA-256 $P"; exit 1; }
        l=$(wc -l < "/tmp/manifest_blob_$i.bin"); rc=$?
        test "$rc" -eq 0 || { echo "FAIL: line count $P"; exit 1; }
        b=$(wc -c < "/tmp/manifest_blob_$i.bin"); rc=$?
        test "$rc" -eq 0 || { echo "FAIL: byte count $P"; exit 1; }
        printf '%s  custody=%s  sha256=%s  bytes=%s  lines=%s\n' "$P" "$CUSTODY_COMMIT" "$h" "$b" "$l" >> /tmp/custody_manifest.txt
        i=$((i + 1))
      done
      cat /tmp/custody_manifest.txt
      ```
- [ ] **Step 5:** Documentation-freshness audit across the product pool, Optimus pool, README and
      `AGENTS.md` for A2A current-state claims.
- [ ] **Step 6:** **Stop for explicit operator authorization** for the closure commit. No review
      grants it.

      **Step 7 — external evidence, not a checkbox.** On authorization: re-run `git status --short`
      immediately beforehand, reject any extra path, and commit exactly: the product pool; the
      Optimus pool; `tests/unit/docs/test_open_work_pool_hygiene.py`; record 4; and **`_v3`** (its
      checkboxes are the on-disk progress record — `_v2` is frozen history and is **not** part of
      this commit). Push and open/update the PR. The resulting commit/PR identifiers are
      **reported externally** — a commit cannot contain its own identifier, and a checkbox cannot
      truthfully be `[x]` before the command that it certifies has run.

### Gates

```bash
uv sync --all-extras
uv build --wheel --out-dir dist/plan99
test "$(ls -1 dist/plan99/*.whl | wc -l)" -eq 1
plan99_scratch="$(mktemp -d)"
uv run python tools/verify_plan99_noneditable_install.py --wheel-dir dist/plan99 --scratch-root "$plan99_scratch"
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
git diff --check          # ordinary repository gate, non-preserved paths
```

Narrow cycle after each red/green: `uv run pytest tests/unit/docs/test_open_work_pool_hygiene.py -q`.
Coverage floor `fail_under = 80`. Capture return codes directly; never read `$?` after a pipe. Known
tracked flakes: `P11-FU-7`, `P11-FU-6`.

---

## Definition of Done

**Part 1 — custody PR (Tasks 1A-1E):**

- [ ] Tooling PR merged; `check-attr` reports `text: unset` for the six and `text: auto`/`eol: lf`
      for **both** `_v2` and `_v3`.
- [ ] Eight records committed; every preserved body (records 1-6) byte-identical to its `$SDD`
      source **in the index**, with full SHA-256, byte and line counts recorded. Record 7 (`_v2`)
      reconstructed once with its status line corrected to historical; record 8 (`_v3`) is the live
      execution ledger.
- [ ] The configured hook ran at exit 0 and changed neither working files nor staged blobs, for all
      eight paths.
- [ ] v1's wrapper is static history; `_v2`'s wrapper is now **also** static history (superseded by
      `_v3`); `_v3` is live; record 4 names `_v3` as the latest disposition.
- [ ] No `src/`, tests, pool, or digest-pinned artifact touched.
- [ ] **No tracked manifest is required in Part 1** — digests are verified against the custody commit
      and recorded in Task 5 Step 4.

**Part 2 — M17 closure (Tasks 2-5), explicitly NOT satisfied by Part 1:**

- [ ] Four paths in the ownership list and `PRODUCT_OWNED_DOCS` (scoping, v1, `_v2`, `_v3`); pool
      links only plans/specs.
- [ ] A2A row not-shipped with corrected facts; six slice rows; both product tables carry one
      Priority column with `CREDENTIAL-LIFECYCLE` the sole HIGH.
- [ ] Obligations table matches `EXPECTED_OBLIGATIONS` exactly; M17 the sole `Closed`.
- [ ] Four adjacent custody rows corrected; Optimus Redis reference narrowed.
- [ ] Tracked custody manifest present, digests labelled as hashes of the custody commit.
- [ ] Every gate exits 0, any isolated flake followed by a clean rerun of the full command.

Until Part 2 completes: **M17 stays open**, the pool still records the ledger as `Closed`, the
obligations table does not exist, the six slices are unscheduled, and these records are not
discoverable through the pool.
