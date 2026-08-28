# Plan 10.3: uv.lock Dependency Drift and SurfaceAuditError CI Wart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILLS: Use `superpowers:executing-plans` to execute
> this plan task-by-task and `superpowers:test-driven-development` for the
> `SurfaceAuditError` behavior change. Steps use checkbox syntax (`- [ ]`) for tracking.
> No implementation may begin until Task 0 has produced the reviewer/operator approval record
> containing the final plan SHA-256.

**Status:** Drafted for reviewer/operator approval on 2026-07-24; implementation is not
authorized and no source, test, lock, backlog, roadmap, or README change has started from this
plan.

**Goal:** Repair the committed dependency lock so a frozen install contains the declared
`keyring`/`redis` chain on Windows and Linux, and remove the tools-only frozen-dataclass behavior
that can turn pytest traceback capture of `SurfaceAuditError` into a secondary
`FrozenInstanceError`.

**Architecture:** Keep the two fixes independent and narrow. Item 1 regenerates only `uv.lock`
from the existing `pyproject.toml` declarations and validates the result with the Windows suite
and a fresh WSL2 Ubuntu-24.04 sync. Item 2 changes only the mutability declaration of the existing
tools-only exception and adds a focused regression for traceback attachment; it does not alter the
exception fields, message formatting, manifest validation, or standalone CLI behavior. Living
backlog, roadmap, and README custody is reconciled only after both fixes have their required
evidence.

**Tech Stack:** Python 3.14+, uv, existing `pyproject.toml` dependencies, dataclasses, pytest,
pytest-asyncio, pytest-cov, coverage.py, Ruff, PowerShell on Windows, and a real WSL2
Ubuntu-24.04 environment. No new dependency and no provider credential is required.

## Global Constraints

- The implementation baseline is the latest fetched `origin/main`, currently
  `ba6168cf28750bbde0f3c8e4f18c30c47d54c61e` (Plan 10.2 merge, verified 2026-07-24).
- This is the next sequential Plan 10 slot. Plan 10.3 is unallocated on `origin/main`; do not
  create another Plan 10.x number or a second consolidated backlog document.
- The current planning checkout has user-owned `uv.lock` changes and an untracked `.claude/`
  directory. Preserve both exactly; do not stage, revert, regenerate, or otherwise modify either
  path while drafting or reviewing this plan.
- Implementation must begin only in a fresh branch/worktree based directly on the then-current
  `origin/main`, after Task 0 approval. Never fork the implementation branch from the old Plan
  10.2 planning branch or from a Plan 10.1 feature branch.
- The implementation scope is exactly two named items: lockfile dependency drift and the
  `SurfaceAuditError` frozen-dataclass CI wart. Do not expand into a dependency upgrade audit,
  exception-hygiene audit, provider-key audit, or unrelated test cleanup.
- Item 1 may modify only `uv.lock`. Do not edit `pyproject.toml`, change declared version ranges,
  pin unrelated packages, or remove direct `keyring`/`redis` dependencies.
- Item 1's expected lock additions are exactly the declared/runtime and keyring-backend chain:
  `cffi`, `cryptography`, `jaraco-classes`, `jaraco-context`, `jaraco-functools`, `jeepney`,
  `keyring`, `more-itertools`, `pycparser`, `python-dotenv`, `pywin32-ctypes`, `redis`, and
  `secretstorage`. Any unrelated package/version/platform-marker change requires stopping and
  obtaining a scope ruling before continuing.
- Item 2 may change only `tools/verify_plan996_logging_surfaces.py` and its focused unit test.
  The source change is limited to dropping `frozen=True` from `SurfaceAuditError`; retain the
  `code` and `key` fields, defaults, inheritance, `__str__`, manifest validation, and `main()`.
- Because the dataclass keeps its default `eq=True`, dropping `frozen=True` changes the generated
  `__hash__` from a value-based hash to `None`, making `SurfaceAuditError` instances unhashable.
  A repository-wide usage audit found the exception is only raised and matched via
  `pytest.raises(...)`, never hashed or used as a set member/dict key; do not add `unsafe_hash=True`
  to preserve an unused control-flow property.
- Use TDD for Item 2: add the named failing regression, run it and record the expected
  `FrozenInstanceError`, apply the one-line production change, then rerun the selector and the
  full tools test file. Item 1 is a lock regeneration and validation task, not a reason to add
  source behavior or unrelated tests.
- `uv lock --check` and the Windows full suite must pass from the implementation branch. The WSL2
  check must use a disposable fresh sync and real imports of `keyring`, `redis`, and
  `cryptography`; a pre-existing Windows or WSL environment is not evidence.
- Do not mark a plan checkbox complete until its literal verification command passed. Record the
  command, exit status, relevant output, changed-file list, and commit SHA in the gitignored
  `docs/superpowers/reviews/plan-10-3-review-checkpoints.md` log. Never stage that log.
- Do not modify the consolidated backlog, phase roadmap, or README until Task 3 has evidence for
  both implementation items. Those documents must record `Promoted -> Plan 10.3`, final evidence,
  and ownership without deleting the original backlog notes.
- Before final handoff, run the affected tests, the default Windows suite with `--frozen`, the
  repository's 80% coverage gate, `uv lock --check`, Ruff, diff hygiene, and the WSL2 fresh-sync
  import check. No merge, push, branch deletion, or history rewrite is authorized by this plan.

## Source Anchors and Current Evidence

- `pyproject.toml:11` declares direct `keyring>=25,<26`; `pyproject.toml:13` declares direct
  `redis>=5`; `pyproject.toml:27` declares the dev `python-dotenv>=1.0` dependency.
- The committed `uv.lock` on current `origin/main` is out of sync with those declarations:
  `uv lock --check` fails and `uv lock --dry-run` reports the 13-package chain named above. The
  direct-dependency status of `keyring` and `redis` must remain explicit in the implementation
  evidence.
- `tools/verify_plan996_logging_surfaces.py:18-19` currently declares
  `SurfaceAuditError` with `@dataclass(frozen=True)`. The exception is constructed with `code`
  and optional `key`, and its `__str__` returns the existing code/key text.
- `tests/unit/tools/test_verify_plan996_logging_surfaces.py:1-167` covers manifest loading,
  discovery, `main()`, and the existing `SurfaceAuditError` failure cases using
  `pytest.raises(...)`; the new regression belongs beside those tests.
- `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` contains the two
  open lightweight notes under `Tracked, Not Yet Scheduled`; they are the sole custody source for
  these items until Task 3 promotes and closes them.
- `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` contains the Plan 10 umbrella and the
  Plan 10.1/10.2 entries. Plan 10.3 must be added alongside those entries without closing the
  remaining Plan 10 pool.
- `README.md` contains the short Plan 10 status pointer. Add one concise Plan 10.3 sentence there;
  do not duplicate the backlog's detailed evidence table.

## File and Responsibility Map

| File | Responsibility in this plan |
|---|---|
| `uv.lock` | Regenerated from the existing `pyproject.toml`; only the expected 13-package dependency chain may be added or changed. |
| `tools/verify_plan996_logging_surfaces.py` | Drop `frozen=True` from the existing `SurfaceAuditError` dataclass and change no behavior around validation or CLI output. |
| `tests/unit/tools/test_verify_plan996_logging_surfaces.py` | Regression-pin traceback assignment/pytest failure capture and preserve existing tool tests. |
| `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | Promote both lightweight notes to Plan 10.3 and record final implementation evidence/closure. |
| `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` | Add the Plan 10.3 status/link beside Plan 10.1 and Plan 10.2 while keeping the pool open. |
| `README.md` | Add one concise Plan 10.3 pointer. |
| `docs/superpowers/reviews/2026-07-24-plan-10-3-implementation-plan-approval.md` | Create only after reviewer/operator approval of the exact digest-pinned plan. |
| `docs/superpowers/reviews/plan-10-3-review-checkpoints.md` | Gitignored reviewer/implementation handoff log; never stage or commit. |

---

### Task 0: Verify the baseline, allocate Plan 10.3, and freeze the plan

**Files:**

- Inspect: `AGENTS.md`, `CONTRIBUTING.md`, `pyproject.toml`, the current Plan 10.1/10.2 plans,
  the consolidated backlog, the phase roadmap, and `README.md`.
- Create only after approval: `docs/superpowers/reviews/2026-07-24-plan-10-3-implementation-plan-approval.md`.
- Create/update as a gitignored handoff log:
  `docs/superpowers/reviews/plan-10-3-review-checkpoints.md`.

**Produces:** A reviewer- and operator-approved, SHA-256-pinned Plan 10.3 scope with proof that
the implementation branch starts at current `origin/main`, Plan 10.3 is the next unused slot, and
the pre-existing dirty paths are preserved outside the implementation scope.

- [ ] **Step 1: Verify the implementation branch baseline and preserved user state.**

  Run from the fresh implementation branch/worktree, not from the dirty planning checkout:

  ```powershell
  git status --short --branch
  git branch --show-current
  git rev-parse HEAD
  git rev-parse origin/main
  git diff --name-only -- uv.lock
  git status --short -- .claude
  ```

  Expected: the implementation branch is dedicated to Plan 10.3; `HEAD` equals the then-current
  `origin/main`; the implementation checkout has no unrelated source/test/documentation changes;
  and the original planning checkout's `uv.lock`/`.claude/` state remains preserved and unstaged.
  If the branch is not based directly on `origin/main`, stop and recreate it from `main` using the
  repository's worktree rules.

- [ ] **Step 2: Verify Plan 10.3 is the next unallocated Plan 10 slot.**

  Run:

  ```powershell
  git grep -n -E "Plan 10\.3|plan-10-3" origin/main -- docs README.md
  git ls-tree -r --name-only origin/main docs/superpowers/plans | Select-String -Pattern "plan-10-3"
  git grep -n -E "Plan 10\.[0-9]" origin/main -- docs/superpowers/plans README.md
  ```

  Expected: the first two commands produce no Plan 10.3 match; the third shows the already
  allocated Plan 10.1 and Plan 10.2 references but no Plan 10.3 allocation. Record the actual
  output and the baseline SHA in the checkpoint log.

- [ ] **Step 3: Capture the current lock-drift baseline and direct-dependency evidence.**

  Run:

  ```powershell
  uv lock --check
  uv lock --dry-run
  git grep -n -E '"keyring|"redis|python-dotenv' origin/main -- pyproject.toml
  ```

  Expected: `uv lock --check` exits nonzero because the committed lock is out of sync;
  `uv lock --dry-run` reports the expected 13-package chain; and `pyproject.toml` proves that
  `keyring` and `redis` are direct dependencies while `python-dotenv` is declared in the dev
  extra. A cache/permission failure is environment evidence only and must be recorded separately;
  it is not a lock-drift result.

- [ ] **Step 4: Capture the `SurfaceAuditError` baseline and tool-test selectors.**

  Run:

  ```powershell
  rg -n -A5 -B3 "class SurfaceAuditError|dataclass\(frozen=True\)" tools/verify_plan996_logging_surfaces.py
  uv run --frozen pytest tests/unit/tools/test_verify_plan996_logging_surfaces.py -q
  ```

  Expected: the source shows `@dataclass(frozen=True)` immediately above `SurfaceAuditError`,
  and the existing tool tests pass or expose only an environment/dependency problem. Do not
  classify a generic collection failure as evidence of the CI wart.

- [ ] **Step 5: Obtain reviewer and operator approval for these exact plan bytes.**

  The reviewer must verify the two-item scope boundary, the exact 13-package lock allowlist, the
  fresh WSL2 evidence requirement, the traceback-capture regression, the standalone `main()`
  preservation, and the final custody task. The operator must approve the same scope. Record both
  statements and the exact plan path in
  `docs/superpowers/reviews/2026-07-24-plan-10-3-implementation-plan-approval.md`.

- [ ] **Step 6: Freeze the approved plan digest before implementation.**

  Run:

  ```powershell
  (Get-FileHash -Algorithm SHA256 docs/superpowers/plans/2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md).Hash
  ```

  Record the exact uppercase hash, baseline commit, reviewer statement, operator statement,
  allowed files, excluded files, and scope in the approval record. Any substantive plan-text
  change after this step invalidates the approval and requires a new review, new hash, and
  replacement approval record; checkbox-only progress remains subject to the evidence protocol.

- [ ] **Step 7: Hand off to implementation only after the approval record exists.**

  The implementing agent must read the checkpoint log first, verify the frozen plan digest and
  current `origin/main`, and confirm that no production/test/lock/custody mutation has started in
  the planning checkout. No Task 1 or Task 2 checkbox may be marked before that handoff.

---

### Task 1: Regenerate and validate the dependency lock

**Files:**

- Modify: `uv.lock` only.
- Inspect: `pyproject.toml` and the lock diff.
- Record: `docs/superpowers/reviews/plan-10-3-review-checkpoints.md` only; never stage it.

**Interfaces:**

- Consumes the existing direct dependency declarations in `pyproject.toml`.
- Produces a committed lock that passes `uv lock --check`, supports `uv sync --frozen`, and
  contains the expected keyring/redis/SecretStorage/dotenv/pywin32 chain without unrelated drift.

- [ ] **Step 1: Regenerate the lock from the approved implementation baseline.**

  Run:

  ```powershell
  uv lock
  git diff --name-only
  git diff -- pyproject.toml
  git diff -- uv.lock
  ```

  Expected: `uv lock` completes; only `uv.lock` is modified; `pyproject.toml` has no diff; and
  every lock hunk is attributable to the expected 13 packages: `cffi`, `cryptography`,
  `jaraco-classes`, `jaraco-context`, `jaraco-functools`, `jeepney`, `keyring`, `more-itertools`,
  `pycparser`, `python-dotenv`, `pywin32-ctypes`, `redis`, and `secretstorage`. Reject unrelated
  package additions, removals, version changes, metadata changes, or platform-resolution drift.

- [ ] **Step 2: Verify lock consistency and the resolved package names.**

  Run:

  ```powershell
  uv lock --check
  rg -n '^name = "(cffi|cryptography|jaraco-classes|jaraco-context|jaraco-functools|jeepney|keyring|more-itertools|pycparser|python-dotenv|pywin32-ctypes|redis|secretstorage)"$' uv.lock
  git diff --check
  ```

  Expected: `uv lock --check` exits 0; each expected package name is present in the lock; no
  unrelated lockfile path has a diff; and `git diff --check` is clean.

- [ ] **Step 3: Run the Windows frozen full suite.**

  Run:

  ```powershell
  uv run --frozen pytest -q
  ```

  Expected: the repository's default marker policy passes the complete Windows suite with no
  lock or import failure. Record the collected/passed/skipped counts and the exact commit-ready
  changed-file list in the checkpoint log.

- [ ] **Step 4: Commit only the reviewed lock change.**

  Run:

  ```powershell
  git status --short --branch
  git add uv.lock
  git commit -m "chore: refresh uv lock for declared gateway dependencies"
  ```

  Expected: only `uv.lock` is staged and committed; `.claude/`, checkpoint logs, and unrelated
  paths remain unstaged. Record the commit SHA after verifying `git show --stat --oneline HEAD`.

- [ ] **Step 5: Verify a fresh WSL2 Ubuntu-24.04 sync and imports.**

  From the implementation checkout containing the lock commit, run the real WSL2 environment
  check. The archive is extracted into a disposable directory so the test does not reuse the
  Windows `.venv` or a prior Linux environment:

  ```powershell
  wsl.exe -d Ubuntu-24.04 -- bash -lc 'set -euo pipefail; repo=/mnt/d/Projects/Development/Python/optimus-cost-agent-wt-codex; temp_dir=$(mktemp -d); trap '\''rm -rf "$temp_dir"'\'' EXIT; git -C "$repo" archive --format=tar HEAD | tar -xf - -C "$temp_dir"; cd "$temp_dir"; uv sync --frozen; .venv/bin/python -c "import keyring, redis, cryptography; print(keyring.__name__, redis.__name__, cryptography.__name__)"'
  ```

  Expected: WSL2 `uv sync --frozen` exits 0 from the disposable copy, and the Python import
  command exits 0 and prints the three module names. This is the required real Linux evidence;
  packages already installed in another WSL venv do not satisfy the gate. If the implementation
  worktree uses a different path, substitute its absolute `/mnt/<drive>/...` path and record it.

- [ ] **Step 6: Record Item 1 evidence and scope.**

  Add a newest-first checkpoint entry containing the baseline SHA, lock commit SHA, exact output of
  `uv lock --check`, the full-suite result, the WSL2 distro and fresh-sync/import result, the
  reviewed 13-package diff list, and the statement that `pyproject.toml` was unchanged. Do not
  mark this task complete if any unrelated lock hunk remains unexplained.

---

### Task 2: Remove the frozen-dataclass CI wart without changing tool behavior

**Files:**

- Modify: `tools/verify_plan996_logging_surfaces.py:18-26`.
- Modify: `tests/unit/tools/test_verify_plan996_logging_surfaces.py`.
- Inspect: the existing manifest fixtures and `main()` tests in the same test file.
- Record: `docs/superpowers/reviews/plan-10-3-review-checkpoints.md` only; never stage it.

**Interfaces:**

- `SurfaceAuditError(code: str, key: str = "")` remains the same exception constructor and
  `str(error)` output.
- `load_manifest`, `discover_surfaces`, `validate_manifest`, and `main()` retain their current
  signatures, exit behavior, and messages.
- The exception becomes traceback-attachable so pytest generator-based failure capture cannot
  raise a secondary `FrozenInstanceError` while handling the original error.

- [ ] **Step 1: Add and run the focused RED regression.**

  Add this test beside the existing `SurfaceAuditError` tests:

  ```python
  def test_surface_audit_error_allows_pytest_traceback_attachment() -> None:
      error = SurfaceAuditError(code="TRACEBACK_CAPTURE")

      error.__traceback__ = None

      assert str(error) == "TRACEBACK_CAPTURE"
  ```

  Run:

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_verify_plan996_logging_surfaces.py::test_surface_audit_error_allows_pytest_traceback_attachment -q
  ```

  Expected before the production change: the selector fails with `dataclasses.FrozenInstanceError`
  while assigning `__traceback__`, proving the exact mutability defect. Do not accept a generic
  collection or environment failure as the RED result.

- [ ] **Step 2: Apply the one-line production correction.**

  In `tools/verify_plan996_logging_surfaces.py`, change only:

  ```python
  @dataclass(frozen=True)
  ```

  to:

  ```python
  @dataclass
  ```

  Keep `code`, `key`, the default value, the `__str__` implementation, and every caller unchanged.
  Do not add a custom exception base, `__post_init__`, mutability policy, `unsafe_hash=True`, or
  adjacent exception edits.

- [ ] **Step 3: Run the focused GREEN test and the complete tools unit file.**

  Run:

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_verify_plan996_logging_surfaces.py::test_surface_audit_error_allows_pytest_traceback_attachment -q
  uv run --frozen pytest tests/unit/tools/test_verify_plan996_logging_surfaces.py -q
  ```

  Expected: the new selector passes and the complete tools unit file passes, including all
  existing `pytest.raises(SurfaceAuditError, ...)` cases, discovery tests, and `main()` tests.

- [ ] **Step 4: Verify standalone `main()` behavior and tool lint.**

  Run:

  ```powershell
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json --project-root .
  uv run --frozen ruff check tools/verify_plan996_logging_surfaces.py tests/unit/tools/test_verify_plan996_logging_surfaces.py
  git diff --check
  ```

  Expected: the standalone command exits 0 and prints `Plan 9.96 logging-surface audit passed`;
  Ruff is clean; and diff hygiene is clean. No manifest, source inventory, exception message,
  or CLI output changes beyond traceback mutability are permitted.

- [ ] **Step 5: Commit only the tools fix and regression.**

  Run:

  ```powershell
  git status --short --branch
  git add tools/verify_plan996_logging_surfaces.py tests/unit/tools/test_verify_plan996_logging_surfaces.py
  git commit -m "fix(tools): allow surface audit errors to carry tracebacks"
  ```

  Expected: only the named source and test files are staged and committed. Record the commit SHA
  and the RED/GREEN selector results in the checkpoint log; never stage `uv.lock`, `.claude/`, or
  the checkpoint log.

---

### Task 3: Reconcile Plan 10.3 custody after implementation evidence

**Files:**

- Modify after Tasks 1 and 2 evidence: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`.
- Modify after Tasks 1 and 2 evidence: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`.
- Modify after Tasks 1 and 2 evidence: `README.md`.
- Modify only as a gitignored handoff record: `docs/superpowers/reviews/plan-10-3-review-checkpoints.md`.

**Interfaces:**

- The consolidated backlog remains the detailed custody ledger for the two original lightweight
  notes; preserve their original summaries and dates.
- The roadmap remains the Plan 10 sequencing/status source and must keep the rest of the Plan 10
  pool tracked, not yet scheduled.
- README remains a concise pointer and must not become a second detailed backlog.
- No frozen Plan 9.96 plan, design, evidence report, approval record, or Plan 10.1/10.2 plan may be
  rewritten as part of this task.

- [ ] **Step 1: Record implementation evidence before changing status text.**

  Append a newest-first checkpoint entry containing the two implementation commit SHAs, the final
  changed-file list, the exact lock diff package review, `uv lock --check`, Windows suite,
  coverage, Ruff, standalone tool command, focused tool tests, WSL2 distro/fresh-sync/import
  result, and every final scope command. Status text must not claim closure before these artifacts
  exist.

- [ ] **Step 2: Promote and close the two backlog notes under Plan 10.3.**

  In the `Tracked, Not Yet Scheduled` section, retain each original note and add a dated
  `Promoted -> Plan 10.3` disposition with a link to
  `2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md`. After evidence, record the lock
  commit, the exact 13-package diff review, Windows and WSL2 acceptance results, the tools commit,
  the named regression test, and the standalone `main()` result. The final text must state that
  both notes are closed by Plan 10.3, with no new catalog ID and no unowned deferred follow-up.

- [ ] **Step 3: Add Plan 10.3 to the phase roadmap without closing the Plan 10 pool.**

  Add a dated Plan 10.3 entry alongside Plan 10.1 and Plan 10.2, linking the frozen plan, the
  approval record, both implementation commits, and the checkpoint evidence. State that Plan 10.3
  closes the two promoted notes and that all other Plan 10 pool items remain tracked and
  unscheduled. Do not reserve or invent Plan 10.4.

- [ ] **Step 4: Add the one-sentence README pointer.**

  Add one concise sentence after the existing Plan 10.2 pointer linking Plan 10.3 and summarizing
  only the two closed items: the frozen dependency lock and the traceback-safe tools exception.
  Keep the detailed package list, commands, and evidence in the backlog/plan rather than copying
  them into README.

- [ ] **Step 5: Verify cross-document custody and scope.**

  Run:

  ```powershell
  rg -n -i "Plan 10\.3|Promoted -> Plan 10\.3|uv\.lock|SurfaceAuditError|frozen-dataclass|traceback" README.md docs/superpowers/plans/2026-07-01-phase-1-roadmap.md docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md docs/superpowers/plans/2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md
  git diff --check
  git diff --name-only -- docs/superpowers/plans/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md
  git diff --name-only
  ```

  Expected: both original notes point to Plan 10.3 and final evidence; the roadmap and README
  point to the same plan; no frozen Plan 9.96 file is modified; and the only intentional tracked
  paths are `uv.lock`, the named tools source/test files, the three custody documents, and the
  approved plan/approval artifacts. `.claude/` and checkpoint logs remain unstaged.

- [ ] **Step 6: Commit the custody reconciliation.**

  Run:

  ```powershell
  git add README.md docs/superpowers/plans/2026-07-01-phase-1-roadmap.md docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md
  git commit -m "docs: reconcile Plan 10.3 custody"
  ```

  Expected: only the three named living-status documents are staged for this commit. Do not stage
  frozen plan files, approval/checkpoint logs, `.claude/`, or any unrelated lock/source/test path.

---

### Task 4: Repository-wide fitness and final handoff

**Files:**

- Inspect all intentional implementation and custody changes.
- Modify only `docs/superpowers/reviews/plan-10-3-review-checkpoints.md` for final evidence; never
  stage it.

**Produces:** Evidence sufficient for reviewer/operator sign-off that both defects are fixed, the
lock is portable to a fresh Linux environment, and the final custody has no scope drift.

- [ ] **Step 1: Run the affected tests and the default Windows suite.**

  Run:

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_verify_plan996_logging_surfaces.py -q
  uv run --frozen pytest -q
  ```

  Expected: both commands pass under the repository's default marker policy. The tools selector
  must include the traceback regression and all existing manifest/discovery/main tests.

- [ ] **Step 2: Run coverage, Ruff, lock consistency, and diff hygiene.**

  Run:

  ```powershell
  uv run --frozen pytest --cov=optimus --cov=optimus_gateway --cov=optimus_security --cov-report=term-missing --cov-fail-under=80 -q
  uv run --frozen ruff check .
  uv lock --check
  git diff --check
  git status --short --branch
  ```

  Expected: aggregate production coverage is at least 80%; Ruff is clean; `uv lock --check`
  exits 0; diff hygiene is clean; and final status contains only intentional committed history
  plus the explicitly preserved user-owned `.claude/`/checkpoint state. No uncommitted source,
  test, lock, or custody change may be unexplained.

- [ ] **Step 3: Re-run the final WSL2 fresh-sync import gate.**

  Repeat the Task 1 Step 5 disposable-copy command from the final implementation commit. Expected:
  Ubuntu-24.04 `uv sync --frozen` succeeds and a fresh `.venv/bin/python` imports `keyring`,
  `redis`, and `cryptography` successfully. Record the final command and output separately from
  any earlier WSL2 run.

- [ ] **Step 4: Perform the exact two-item scope audit.**

  Run:

  ```powershell
  rg -n -F "@dataclass(frozen=True)" tools/verify_plan996_logging_surfaces.py
  rg -n -F "class SurfaceAuditError" tools/verify_plan996_logging_surfaces.py
  rg -n -E "^name = \"(cffi|cryptography|jaraco-classes|jaraco-context|jaraco-functools|jeepney|keyring|more-itertools|pycparser|python-dotenv|pywin32-ctypes|redis|secretstorage)\"$" uv.lock
  git diff --name-only origin/main...HEAD
  ```

  Expected: the first command produces no output; the second finds the unchanged exception class;
  all 13 expected package names are present in the committed lock; and the final diff contains no
  unrelated package, exception, source, test, or documentation scope. If the final branch is
  ahead of `origin/main`, review the complete diff rather than relying on a partial path list.

- [ ] **Step 5: Complete the handoff record.**

  Update the checkpoint log with the final implementation/custody commit SHAs, frozen-plan SHA,
  approval-record path, all passing commands and counts, coverage percentage, Ruff result, lock
  package allowlist review, WSL2 distro and import output, standalone `main()` result, backlog/
  roadmap/README status, and preserved dirty paths. Present the exact diff and evidence for final
  reviewer/operator sign-off. No merge, push, branch deletion, or history rewrite is authorized.

## Definition of Done

- Plan 10.3 was reviewed, operator-approved, and SHA-256 pinned before implementation began.
- `uv.lock` is regenerated from the existing direct `keyring`/`redis` declarations; the diff is
  confined to the expected 13-package keyring/redis/SecretStorage/dotenv/pywin32 chain; and
  `uv lock --check` passes.
- The full Windows suite passes with `uv run --frozen pytest -q`, coverage remains at least 80%,
  Ruff is clean, and diff hygiene is clean.
- A fresh WSL2 Ubuntu-24.04 `uv sync --frozen` imports `keyring`, `redis`, and `cryptography`
  successfully without relying on a pre-existing environment.
- `SurfaceAuditError` is no longer frozen, the focused traceback-attachment regression has a
  verified RED/GREEN result, all existing tools tests pass, and standalone `main()` output/exit
  behavior is unchanged.
- The source/test change is limited to the named tools exception and regression; no broader
  exception-hygiene audit or unrelated dependency change is included.
- Both consolidated-backlog notes are marked `Promoted -> Plan 10.3` and closed with named lock,
  WSL2, test, and tool evidence; the roadmap and README point to Plan 10.3; and the remaining Plan
  10 pool stays tracked and unscheduled.
- No frozen Plan 9.96 artifact, prior Plan 10.1/10.2 artifact, `.claude/`, or checkpoint log is
  staged or modified as implementation scope.
