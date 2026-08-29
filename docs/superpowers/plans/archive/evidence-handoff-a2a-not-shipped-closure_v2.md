# A2A Not-Shipped Closure Plan — v2 (live successor)

> **For agentic workers:** stop for review after every task. A checkbox may be marked `[x]` only
> after its stated command ran and passed. Prose claims count for nothing (`AGENTS.md:76`).

**Author:** Claude (drafter/implementer) · **Reviewer:** Codex · **Date:** 2026-08-12
**Supersedes:** `evidence-handoff-a2a-not-shipped-closure.md` (Revision 3, approved 2026-08-12).
**v1's preserved body is immutable.**
**Status:** Historical — superseded by live `_v3` (`evidence-handoff-a2a-not-shipped-closure_v3.md`). Current execution state lives only in `_v3`.

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
| 7 | *(this document)* | `docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v2.md` — **live, LF-normalized, not `-text`** |

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

- [ ] **Step 1:** Create a **dedicated sibling worktree** (not a branch switch inside an
      already-occupied worktree) from freshly fetched `origin/main`, with preflight checks that
      neither the path nor the branch is already taken:

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
- [ ] **Step 2:** Amend `.gitattributes`. Lines 5-7 assert *"Every text file in this repository is
      already stored LF-only"* — **false once exceptions exist**; rewrite that sentence to state that
      a small, enumerated set of preserved audit records is exempt via `-text` to protect raw bytes.
      Then append exactly:

      ```gitattributes
      docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md          -text
      docs/superpowers/reviews/evidence-handoff-a2a-ledger-sealed-reviewer-findings.md   -text
      docs/superpowers/reviews/evidence-handoff-a2a-remediation-scoping-review.md        -text
      docs/superpowers/reviews/evidence-handoff-a2a-not-shipped-closure-review.md        -text
      docs/superpowers/specs/evidence-handoff-a2a-ledger-remediation-scoping.md          -text
      docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure.md                 -text
      ```
- [ ] **Step 3:** Add `args: [--markdown-linebreak-ext=md]` to the `trailing-whitespace` hook.
      Unverified locally (`pre_commit_hooks` is not importable outside pre-commit's isolated env).
      Step 4 must prove it.
- [ ] **Step 4:** Probe at **an actual future preserved path**, literal commands, failing loudly:

      ```bash
      P=docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md
      printf 'alpha  \r\nbeta  \r\ngamma\r\n' > "$P"
      cp "$P" /tmp/probe_pre.bin
      git add -- "$P"
      git cat-file blob ":$P" > /tmp/probe_idx.bin 2>/tmp/probe_idx.err; rc=$?
      test "$rc" -eq 0 || { echo "FAIL: index blob retrieval"; exit 1; }
      python -c "import sys;d=open('/tmp/probe_idx.bin','rb').read();sys.exit(0 if b'\r\n' in d else 1)"; rc=$?
      test "$rc" -eq 0 || { echo "FAIL: -text did not preserve CRLF in the index"; exit 1; }
      uv run pre-commit run trailing-whitespace --files "$P" || { echo "FAIL: hook exit nonzero"; exit 1; }
      cmp -s /tmp/probe_pre.bin "$P" || { echo "FAIL: hook modified intentional hard breaks"; exit 1; }
      git restore --staged -- "$P"
      rm -f -- "$P" /tmp/probe_pre.bin /tmp/probe_idx.bin /tmp/probe_idx.err
      ```

      Every failure exits nonzero — no diagnostic that prints and passes. Cleanup removes **only**
      that exact path from index and working tree; no broad `git reset`.
- [ ] **Step 5:** Literal attribute check:

      ```bash
      git check-attr text eol -- \
        docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md \
        docs/superpowers/reviews/evidence-handoff-a2a-ledger-sealed-reviewer-findings.md \
        docs/superpowers/reviews/evidence-handoff-a2a-remediation-scoping-review.md \
        docs/superpowers/reviews/evidence-handoff-a2a-not-shipped-closure-review.md \
        docs/superpowers/specs/evidence-handoff-a2a-ledger-remediation-scoping.md \
        docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure.md \
        docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v2.md
      ```

      Expected: `text: unset` for the first six; for `_v2`, `text: auto` and `eol: lf`.
- [ ] **Step 6:** Gates, each expected exit 0:

      ```bash
      uv run pre-commit run check-yaml --all-files
      uv run pre-commit run check-toml --all-files
      uv run pre-commit run trailing-whitespace --all-files
      uv run pytest tests/unit/docs/test_open_work_pool_hygiene.py -q      # 43 passed
      uv run ruff check .
      git add -- .gitattributes .pre-commit-config.yaml
      git diff --cached --check                                            # non-vacuous: both staged, neither preserved
      ```
- [ ] **Step 7:** `git status --short` shows **exactly** `.gitattributes` and `.pre-commit-config.yaml`;
      the probe path is absent. Reject any extra. **Stop for explicit operator authorization** before
      commit, push, or PR.

**Step 8 — external evidence, not a checkbox.** On authorization: commit, push, open PR, then **wait
for merge**. The resulting commit/PR identifiers are reported externally; they cannot be recorded in
the commit that creates them.

---

## Task 1B — merge checkpoint

- [ ] **Step 1:** `git fetch origin`; confirm the tooling PR merged into `origin/main`.
- [ ] **Step 2:** On the custody branch, fast-forward only — no rebase fallback:

      ```bash
      git merge --ff-only origin/main; rc=$?
      test "$rc" -eq 0 || { echo "FAIL: fast-forward failed — STOP, do not rebase, request review"; exit 1; }
      git rev-list --left-right --count origin/main...HEAD    # expect: behind = 0
      MB="$(git merge-base HEAD origin/main)"; OM="$(git rev-parse origin/main)"
      test "$MB" = "$OM" || { echo "FAIL: merge-base != origin/main"; exit 1; }
      ```

      If `--ff-only` fails, **stop for review** — do not change branch topology to force a merge.
- [ ] **Step 3:** Re-run the Task 1A Step 5 `check-attr` command; same expectations. Stop for review.

---

## Task 1C — reconstruct the seven records

- [ ] **Step 1:** Rebuild records 1-6 from `$SDD` per the source/destination map, emitting the
      **exact preservation-envelope bytes** stated above (provenance header, then the literal
      `<!-- PRESERVED-BODY-START -->
` marker, then the source body verbatim, then the literal
      `
<!-- PRESERVED-BODY-END -->
` marker — including the required separator newline before
      the end marker). Nothing else inside the region.
- [ ] **Step 2:** Finalize v1's wrapper (record 6) as **static history**, outside the delimiters,
      never inside: v1 was the approved Revision 3 plan; superseded by live `_v2`; current execution
      state lives only in `_v2`. Remove mutable execution-state prose.
- [ ] **Step 3:** Write this document to record 7's destination, LF-clean, carrying the final approval
      disposition. Refresh record 4's wrapper to name **`_v2`** as the latest disposition.
- [ ] **Step 4:** Stop for review.

---

## Task 1D — staging and index-blob verification

No comparison may use a hash-producing pipeline or an unchecked producer. Bash arrays and other
shell state do **not** survive separate shell/tool invocations, so the script below is **one
continuous session** — if execution must split it into fragments, re-paste the "Shared setup"
block verbatim at the top of every fragment.

```bash
# ---- Shared setup ----
SDD="D:/Projects/Development/Python/optimus-cost-agent-wt-codex/.superpowers/sdd"

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

test "${#SOURCES[@]}" -eq 6 || { echo "FAIL: SOURCES length ${#SOURCES[@]}"; exit 1; }
test "${#DESTINATIONS[@]}" -eq 6 || { echo "FAIL: DESTINATIONS length ${#DESTINATIONS[@]}"; exit 1; }

SEVEN=("${DESTINATIONS[@]}" "$V2_PATH")
test "${#SEVEN[@]}" -eq 7 || { echo "FAIL: SEVEN length ${#SEVEN[@]}"; exit 1; }

# ---- Step 1: stage exactly the seven-path allowlist ----
git add -- "${SEVEN[@]}"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: git add"; exit 1; }

git diff --cached --name-only > /tmp/staged_actual.txt 2>/tmp/staged_actual.err; rc=$?
test "$rc" -eq 0 || { echo "FAIL: git diff --cached --name-only rc=$rc"; exit 1; }
sort /tmp/staged_actual.txt -o /tmp/staged_actual.sorted.txt; rc=$?
test "$rc" -eq 0 || { echo "FAIL: sort staged_actual"; exit 1; }

printf '%s\n' "${SEVEN[@]}" > /tmp/staged_expected.txt; rc=$?
test "$rc" -eq 0 || { echo "FAIL: printf staged_expected"; exit 1; }
sort /tmp/staged_expected.txt -o /tmp/staged_expected.sorted.txt; rc=$?
test "$rc" -eq 0 || { echo "FAIL: sort staged_expected"; exit 1; }

diff /tmp/staged_actual.sorted.txt /tmp/staged_expected.sorted.txt; rc=$?
test "$rc" -eq 0 || { echo "FAIL: staged set != seven-path allowlist"; exit 1; }

# ---- Step 2: verify each of records 1-6 against its named source, by index ----
i=0
while [ "$i" -lt 6 ]; do
  SRC="${SOURCES[$i]}"
  DST="${DESTINATIONS[$i]}"
  git cat-file blob ":$DST" > "/tmp/idx_$i.bin" 2>"/tmp/idx_$i.err"; rc=$?
  test "$rc" -eq 0 || { echo "FAIL: retrieval $DST rc=$rc"; exit 1; }
  python3 - "$SRC" "/tmp/idx_$i.bin" <<'PY'
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
  rc=$?
  test "$rc" -eq 0 || { echo "FAIL: extraction/comparison index $i ($DST)"; exit 1; }
  i=$((i + 1))
done
# Record the printed SHA-256 / byte-count / line-count triple for each of the six indices.

# ---- Step 3: restage _v2 (literal path), then snapshot pre-hook state for all seven paths ----
git add -- "$V2_PATH"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: restage $V2_PATH"; exit 1; }

git status --short > /tmp/pre_hook_status.txt 2>&1; rc=$?
test "$rc" -eq 0 || { echo "FAIL: git status rc=$rc"; exit 1; }

: > /tmp/pre_working_hashes.txt
: > /tmp/pre_index_hashes.txt
i=0
while [ "$i" -lt 7 ]; do
  P="${SEVEN[$i]}"
  sha256sum "$P" >> /tmp/pre_working_hashes.txt; rc=$?
  test "$rc" -eq 0 || { echo "FAIL: working hash $P"; exit 1; }
  git cat-file blob ":$P" > "/tmp/pre_idx_$i.bin" 2>"/tmp/pre_idx_$i.err"; rc=$?
  test "$rc" -eq 0 || { echo "FAIL: pre-hook index blob $P"; exit 1; }
  sha256sum "/tmp/pre_idx_$i.bin" >> /tmp/pre_index_hashes.txt; rc=$?
  test "$rc" -eq 0 || { echo "FAIL: pre-hook index hash $P"; exit 1; }
  i=$((i + 1))
done

# ---- Step 4: run the configured hook; prove it changed nothing ----
uv run pre-commit run trailing-whitespace --all-files; rc=$?
test "$rc" -eq 0 || { echo "FAIL: trailing-whitespace hook exit $rc"; exit 1; }

git status --short > /tmp/post_hook_status.txt 2>&1; rc=$?
test "$rc" -eq 0 || { echo "FAIL: post-hook git status rc=$rc"; exit 1; }
diff /tmp/pre_hook_status.txt /tmp/post_hook_status.txt; rc=$?
test "$rc" -eq 0 || { echo "FAIL: git status changed after hook"; exit 1; }

: > /tmp/post_working_hashes.txt
: > /tmp/post_index_hashes.txt
i=0
while [ "$i" -lt 7 ]; do
  P="${SEVEN[$i]}"
  sha256sum "$P" >> /tmp/post_working_hashes.txt; rc=$?
  test "$rc" -eq 0 || { echo "FAIL: post-hook working hash $P"; exit 1; }
  git cat-file blob ":$P" > "/tmp/post_idx_$i.bin" 2>"/tmp/post_idx_$i.err"; rc=$?
  test "$rc" -eq 0 || { echo "FAIL: post-hook index blob $P"; exit 1; }
  sha256sum "/tmp/post_idx_$i.bin" >> /tmp/post_index_hashes.txt; rc=$?
  test "$rc" -eq 0 || { echo "FAIL: post-hook index hash $P"; exit 1; }
  i=$((i + 1))
done

diff /tmp/pre_working_hashes.txt /tmp/post_working_hashes.txt; rc=$?
test "$rc" -eq 0 || { echo "FAIL: working-file hashes changed"; exit 1; }
diff /tmp/pre_index_hashes.txt /tmp/post_index_hashes.txt; rc=$?
test "$rc" -eq 0 || { echo "FAIL: index hashes changed"; exit 1; }

git diff --name-only -- "${SEVEN[@]}" > /tmp/unstaged_after_hook.txt 2>&1; rc=$?
test "$rc" -eq 0 || { echo "FAIL: git diff --name-only rc=$rc"; exit 1; }
test -s /tmp/unstaged_after_hook.txt && { echo "FAIL: unstaged changes remain"; exit 1; }

# ---- Step 5: cached whitespace check, scoped to _v2 only ----
git diff --cached --check -- "$V2_PATH"; rc=$?
test "$rc" -eq 0 || { echo "FAIL: _v2 whitespace check rc=$rc"; exit 1; }

# ---- Step 6: final state ----
git status --short
git diff --cached --stat
```

- [ ] **Step 1:** Staged set equals the seven-path allowlist exactly (script "Step 1" section).
- [ ] **Step 2:** All six index blobs verified byte-identical to their named `$SDD` source; SHA-256,
      byte count and line count recorded for each (script "Step 2" section).
- [ ] **Step 3:** `_v2` restaged at its literal path; pre-hook status, working-file hashes, and
      index hashes captured for all seven paths (script "Step 3" section).
- [ ] **Step 4:** Hook ran at exit 0; post-hook status, working-file hashes, and index hashes are
      **all identical** to pre-hook; no unstaged diff remains for any of the seven paths (script
      "Step 4" section).
- [ ] **Step 5:** `git diff --cached --check` scoped to `_v2` only passes; never run over records
      1-6 (script "Step 5" section).
- [ ] **Step 6:** Final seven-path `git status --short` and `git diff --cached --stat` recorded.
      Stop for review.

---

## Task 1E — custody commit (baseline only)

- [ ] **Step 1:** **Stop for explicit operator authorization.** No review grants it.

**Step 2 — external evidence, not a checkbox.** On authorization: re-run `git status --short`
immediately beforehand, reject any extra path, commit exactly the seven records, push, open the PR
described as **artifact-custody preservation only** (Tasks 2-5 open, M17 not closed, DoD Part 2 not
satisfied, records not yet discoverable through the pool). The custody-commit SHA and PR number are
**reported externally**; a commit cannot contain its own identifier.

**Commit topology (chosen, non-circular).** The custody commit is the seven-record baseline. **No
tracked manifest is written into it** — a manifest recording that commit's SHA cannot exist inside
it, and appending one would alter a file after its own verified baseline. The tracked manifest is
therefore **deferred to the Task 5 closure commit**, which records all digests explicitly as *hashes
of the custody commit*.

---

## Task 2 — atomic link, ownership, and allowlist

- [ ] **Step 1 (RED):** Add **three** literal paths to `PRODUCT_OWNED_DOCS`:
      `docs/superpowers/specs/evidence-handoff-a2a-ledger-remediation-scoping.md`,
      `docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure.md` (historical v1), and
      `docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v2.md` (live). Both plan
      versions stay product-owned, matching the risk-slice precedent
      (`test_open_work_pool_hygiene.py:226-227`; product pool lines 81-82). Narrow docs test →
      expect FAIL on `listed_docs == PRODUCT_OWNED_DOCS`.
- [ ] **Step 2 (GREEN):** In the same cycle add all three to the pool's
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

The row links **live `_v2`** (`docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v2.md`)
and the tracked **scoping contract**
(`docs/superpowers/specs/evidence-handoff-a2a-ledger-remediation-scoping.md`) as markdown links, and
may reference historical v1 without making it the execution target. It references the independent
audit, sealed reviewer findings, scoping review chronology, and this closure review chronology by
**backticked path only** — never as a markdown link, per the pool's product-owned-document link
allowlist:

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
      a hash **of the custody commit**. The manifest covers **all seven** custody-baseline paths, not
      only the six preserved records. Record 7's (`_v2`'s) manifest entry is the digest of `_v2` **as
      committed in the custody commit** — i.e. the version at the end of Task 1D, before this Task 5
      further edits `_v2`'s checkboxes for the closure commit. That entry will legitimately differ
      from `_v2`'s working-tree bytes at the moment this step runs; record it as the custody-baseline
      digest, not as a mismatch to reconcile:

      ```bash
      CUSTODY_COMMIT="<paste the SHA reported after Task 1E Step 2>"

      SEVEN=(
        docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md
        docs/superpowers/reviews/evidence-handoff-a2a-ledger-sealed-reviewer-findings.md
        docs/superpowers/reviews/evidence-handoff-a2a-remediation-scoping-review.md
        docs/superpowers/reviews/evidence-handoff-a2a-not-shipped-closure-review.md
        docs/superpowers/specs/evidence-handoff-a2a-ledger-remediation-scoping.md
        docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure.md
        docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v2.md
      )
      test "${#SEVEN[@]}" -eq 7 || { echo "FAIL: SEVEN length ${#SEVEN[@]}"; exit 1; }

      : > /tmp/custody_manifest.txt
      i=0
      while [ "$i" -lt 7 ]; do
        P="${SEVEN[$i]}"
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
      Optimus pool; `tests/unit/docs/test_open_work_pool_hygiene.py`; record 4; and `_v2` (its
      checkboxes are the on-disk progress record). Push and open/update the PR. The resulting
      commit/PR identifiers are **reported externally** — a commit cannot contain its own
      identifier, and a checkbox cannot truthfully be `[x]` before the command that it certifies
      has run.

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
      for `_v2`.
- [ ] Seven records committed; every preserved body byte-identical to its `$SDD` source **in the
      index**, with full SHA-256, byte and line counts recorded.
- [ ] The configured hook ran at exit 0 and changed neither working files nor staged blobs.
- [ ] v1's wrapper is static history; `_v2` is live; record 4 names `_v2` latest.
- [ ] No `src/`, tests, pool, or digest-pinned artifact touched.
- [ ] **No tracked manifest is required in Part 1** — digests are verified against the custody commit
      and recorded in Task 5 Step 4.

**Part 2 — M17 closure (Tasks 2-5), explicitly NOT satisfied by Part 1:**

- [ ] Three paths in the ownership list and `PRODUCT_OWNED_DOCS`; pool links only plans/specs.
- [ ] A2A row not-shipped with corrected facts; six slice rows; both product tables carry one
      Priority column with `CREDENTIAL-LIFECYCLE` the sole HIGH.
- [ ] Obligations table matches `EXPECTED_OBLIGATIONS` exactly; M17 the sole `Closed`.
- [ ] Four adjacent custody rows corrected; Optimus Redis reference narrowed.
- [ ] Tracked custody manifest present, digests labelled as hashes of the custody commit.
- [ ] Every gate exits 0, any isolated flake followed by a clean rerun of the full command.

Until Part 2 completes: **M17 stays open**, the pool still records the ledger as `Closed`, the
obligations table does not exist, the six slices are unscheduled, and these records are not
discoverable through the pool.
