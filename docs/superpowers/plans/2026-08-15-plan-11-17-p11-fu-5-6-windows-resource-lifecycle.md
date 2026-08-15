# P11-FU-5 and P11-FU-6 Windows Resource-Lifecycle Investigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a reviewable disposition for the reproduced Windows subprocess-handle flake (`P11-FU-5`) and either eliminate, or conclusively bound, the Windows Gateway server lifecycle flake (`P11-FU-6`) without weakening route assertions or masking failures.

**Architecture:** This is an investigation-first plan, not a preselected fix. It first records the missing `P11-FU-5` reproduction disposition, gathers Windows evidence for both resource classes, and makes one explicit causal decision: shared root cause, separate causes, or insufficient evidence. `P11-FU-6` then branches to a test-harness correction, a production Gateway correction, or a bounded no-reproduction disposition; `P11-FU-5` has no absence-count closure because its rate is unknown.

**Tech Stack:** Python 3.14, `ThreadingHTTPServer`, `http.client`, `subprocess`, `threading`, pytest, coverage.py, pytest-cov, Ruff, Windows, native WSL2 ext4 with `/usr/bin/git`, `uv`, Git, and Markdown evidence artifacts.

**Status:** Draft planning artifact. This branch was created from `origin/main` `f5437df8f29eec7eac6f4f3ecbc15a4551811e90`; `HEAD` and `origin/main` matched at branch creation. Plan number `11.17` was unclaimed in the plans directory, the consolidated pool, and remote branch names before branch creation.

## Authority and decision record

- `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` is the current-state owner for `P11-FU-4`, `P11-FU-5`, `P11-FU-6`, `P11-FU-7`, and the transferred `P11-FU-26` signal.
- `P11-FU-5` already satisfies the first half of its acceptance criterion: it reproduced three times on Windows on 2026-08-14/15 as `WinError 6` / `DuplicateHandle` in the two Git-spawning pool-hygiene selectors. The detailed entry does not yet say so. The Plan 11.14 and Plan 11.15 committed evidence reports are the source records; Task 0 records their exact locations and preserves the earlier ten-run no-reproduction result as historical context, not contrary evidence.
- `P11-FU-6` reproduced once in 20 Windows `pytest tests/unit -q` processes (5%) as `ConnectionAbortedError: [WinError 10053]` on the successor target. The `ThreadingHTTPServer` helpers in `tests/unit/optimus_gateway/test_server.py` are a hypothesis only. The pool specifically leaves readiness, shutdown, and server-thread exception propagation unresolved.
- `P11-FU-26` is closed only because its retired MCP surface is obsolete; its `WinError 10053` signal belongs to `P11-FU-6`. It is corroborating evidence, not proof of the current Gateway server's cause.
- `P11-FU-7` is a separate coverage/`sys.settrace` timing lane under Plan 11.16. Its 25-process Windows `--cov` gate stopped at 4/25 on an unrelated `P11-FU-6` failure. This plan records the dependency but does not spend, restart, or claim that gate.
- `docs/runbooks/local-live-dependencies.md:198-236` requires a native WSL ext4 clone for any Linux-parity claim. `/mnt/d`, a Windows-created linked worktree, Windows Git, and a shared Windows `.venv` are invalid Linux evidence.

### Decision table — no fix before this record is complete

| Observed evidence | Classification | Permitted next action | Prohibited inference |
|---|---|---|---|
| 59 clean Windows `pytest tests/unit -q` processes, with complete per-process logs and no target selector skipped or deselected | `P11-FU-6` bounded no-reproduction | Close only `P11-FU-6` with the exact run bound, environment, log artifact, and conditional 95% detection-power statement | That absence is proved, that `P11-FU-5` is absent, or that the historical 5% rate was a product fix |
| `P11-FU-6` recurs and deterministic test-local lifecycle evidence identifies a helper-owned resource not released before the next test | Test-harness defect | Write a deterministic red, then make the smallest test-harness correction | That `serve_gateway()` production teardown is defective |
| `P11-FU-6` recurs and the same lifecycle failure occurs through an independently driven Gateway lifecycle, outside `_start_server()` / `_stop_server()` | Gateway production defect | Stop for the recorded reviewer gate, then make the scoped production correction with TDD | That a test-only helper change is enough |
| A `P11-FU-6` recurrence cannot be made deterministic after the bounded investigation | Reproduced, root cause unestablished | Publish the evidence and leave the named entry open with a precise next observation target | That a natural 5% failure is a valid red gate or that a clean rerun resolves it |
| Additional `P11-FU-5` runs are clean | No additional observation | State the exact bound and stop the FU-5 chase | That any run count proves FU-5 absent; its recurrence rate is unknown |
| A single controlled causal chain reproduces both the Git-handle failure and the Gateway socket failure | Shared root cause | Merge only the investigation narrative; retain separate acceptance and closure evidence | That coincident Windows failures alone establish a shared root cause |

### FU-6 no-reproduction statistical basis

The observed FU-6 characterization rate is one failure in 20 Windows unit-suite processes (5%). If that rate is representative and independent between processes, the probability of observing no recurrence in `n` processes is `0.95^n`, and the chance of detecting at least one recurrence is `1 - 0.95^n`.

- Twenty clean processes would provide only **64.2% conditional detection power** (`1 - 0.95^20`), leaving a **35.8%** chance of observing no failure even if the historical rate persists. Twenty is therefore not a FU-6 closure threshold.
- Fifty-nine clean processes provide **95.2% conditional detection power** (`1 - 0.95^59`), leaving 4.8% under that model. At the recorded approximately 186 seconds per full Windows suite, this budgets roughly three hours.
- Ninety clean processes would provide **99.0% conditional detection power** (`1 - 0.95^90`), but are not required for this bounded-disposition gate.

This is a detection-power statement conditional on the estimated historical rate and independence assumptions, not the probability that the flake is gone. The one-in-twenty estimate itself is uncertain, so even 59 clean runs establish only the explicitly stated bounded no-reproduction disposition, never proof of absence.

## Global constraints

- This plan PR changes only this Markdown plan. Implementation begins only after approval, from a fresh dedicated worktree and latest `origin/main`; never use `optimus-cost-agent-wt-vibhanshu` or this planning worktree for implementation.
- Windows is mandatory for every recurrence, root-cause, deterministic-red, and closure claim. A clean native WSL run can be parity evidence only; it cannot close a Windows flake.
- No retry-as-fix, sleep-as-fix, timeout widening, marker skip, deselection, assertion weakening, or suppression of a `WinError` is permitted. A skipped or deselected tier is unrun, never a pass.
- Preserve the actual route assertions in `test_tools_routes_remain_not_found`, `test_unknown_route_remains_not_found`, and all other `test_server.py` cases. Preserve the immutable-document and Git-ignore assertions in both `P11-FU-5` selectors.
- A production-code change is conditional. Before changing `src/optimus_gateway/server.py` or `src/optimus_gateway/__main__.py`, the evidence report must name the independent production reproduction, the affected ownership boundary, and why a test-harness-only correction cannot satisfy it. Record a reviewer approval of that decision in the gitignored Plan 11.17 checkpoint log.
- TDD applies to either correction path. The proposed deterministic red must fail against the pre-fix implementation on every attempted run; if it passes once, stop and repair the injection before editing the implementation. The natural recurrence rate is characterization evidence only.
- Because the missing lifecycle edge is the investigation result, Task 2's signed cause record names the one concrete red selector before Task 3 can run it. That evidence-bound name is intentionally not predeclared in this plan; inventing one now would assume the fix shape this plan is designed to discover.
- Use `uv run --frozen`; before every commit, push, or PR sign-off run `uv run --frozen ruff check .`. Maintain at least 80% aggregate production coverage and record every unrun tier.
- The approved plan is immutable. A changed causal decision, file set, execution scope, or closure rule requires a forward-only `..._v2.md` amendment rather than an edit to this plan.

## File map

### Create during implementation, not in this plan PR

- `reports/plan-11-17-windows-resource-lifecycle-baseline.md` — exact Windows checkout, environment, process-level result matrix, and target-selector observations.
- `reports/plan-11-17-p11-fu-5-windows-disposition.md` — three historical reproductions, any incidental new observations, bounded investigation outcome, and explicit absence-limit statement.
- `reports/plan-11-17-p11-fu-6-root-cause.md` — lifecycle timeline, `P11-FU-26` comparison, shared/separate decision, and reviewer decision record.
- `reports/plan-11-17-windows-resource-lifecycle-release.md` — per-entry closure/open state, command results, commit SHA, documentation audit, and unrun tiers.
- `reports/plan-11-17-wsl-resource-lifecycle-parity.md` — only if a Linux-parity comparison is performed from a native ext4 clone.

### Modify during implementation

- `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` — record FU-5's reproduction disposition first; schedule/disposition FU-5 and FU-6 separately; add the two-line FU-7 dependency statement; evaluate P11-FU-4 custody only after the FU-5 decision.
- `tests/unit/optimus_gateway/test_server.py:59-75,172-175,405-412` — conditional test-harness seam and deterministic lifecycle evidence, while retaining route assertions.
- `tests/unit/docs/test_open_work_pool_hygiene.py:291-298,556-559,1323-1333` — conditional deterministic FU-5 fixture/test seam; retain the real `git` subprocess behavior in the two existing selectors.
- `src/optimus_gateway/server.py:92-120` — conditional production correction only after the production-defect branch is approved.
- `src/optimus_gateway/__main__.py:97-109` — conditional only if the independently reproduced production lifecycle requires entrypoint ownership changes.

### Audit/update only if a current-state claim is stale

- `README.md`
- `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
- `docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md`
- `docs/runbooks/local-live-dependencies.md`

### Read-only authority

- `docs/superpowers/reviews/plan-11-17-review-checkpoints.md` — reviewer-owned, gitignored, and never staged. Read its Current State before any implementation mutation and verify it against the worktree.
- `docs/superpowers/plans/2026-08-14-plan-11-14-p11-fu-21-custody-relay-exit-code.md` and `reports/plan-11-14-p11-fu-21-custody-relay-exit-code-evidence.md` — one committed FU-5 Windows reproduction record.
- `docs/superpowers/plans/2026-08-15-plan-11-15-p11-fu-18-29-durable-approval-identity.md`, `reports/plan-11-15-windows-durable-approval-identity-evidence.md`, and `reports/plan-11-15-durable-approval-identity-release.md` — current FU-5 residual/custody records; do not conflate FU-29's injected `WinError 6` with a FU-5 recurrence.

---

### Task 0: Record current custody and the missing FU-5 reproduction disposition

**Files:**

- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md:129-132,424-471,496-572,574-625`
- Test/read: `tests/unit/docs/test_open_work_pool_hygiene.py`
- Create: `reports/plan-11-17-windows-resource-lifecycle-baseline.md`

**Interfaces:**

- Consumes: committed Plan 11.14/11.15 reports, current pool rows, and the verified implementation-worktree SHA.
- Produces: a pool entry whose FU-5 status is `reproduced, context known`; separately scheduled FU-5/FU-6 entries; an explicit FU-7 blocker statement; and a baseline artifact that later tasks append to rather than overwrite.

- [ ] **Step 1: Create and verify the clean implementation worktree.**

```powershell
git fetch origin main
git worktree add -b agent/codex/plan-11-17-windows-resource-lifecycle-impl ..\optimus-cost-agent-wt-codex-11-17 origin/main
git -C ..\optimus-cost-agent-wt-codex-11-17 status --short --branch
git -C ..\optimus-cost-agent-wt-codex-11-17 rev-parse HEAD
git -C ..\optimus-cost-agent-wt-codex-11-17 rev-parse origin/main
Get-Content ..\optimus-cost-agent-wt-codex-11-17\docs\superpowers\reviews\plan-11-17-review-checkpoints.md -ErrorAction SilentlyContinue
```

Expected: a clean dedicated `codex` worktree and equal `HEAD` / `origin/main` hashes. Stop on drift, unrelated changes, an existing branch name, or a checkpoint ruling that conflicts with this plan.

- [ ] **Step 2: Capture the immutable historical FU-5 facts before editing the pool.**

```powershell
rg -n -C 12 "P11-FU-5|DuplicateHandle|WinError 6|test_immutable_documents_match_approved_head_blobs|test_product_checkpoint_log_location_remains_gitignored" reports/plan-11-14-p11-fu-21-custody-relay-exit-code-evidence.md reports/plan-11-15-windows-durable-approval-identity-evidence.md reports/plan-11-15-durable-approval-identity-release.md
git -C ..\optimus-cost-agent-wt-codex-11-17 rev-parse HEAD
uv run --frozen python -c "import platform,sys; print(sys.platform); print(platform.platform()); print(sys.version)"
where.exe git
git --version
```

Record the three 2026-08-14/15 Windows occurrences, the two named selectors, reported `WinError 6` / `DuplicateHandle` form, exact report anchors, Git executable/version, and checkout SHA. Record that the Plan 11.15 FU-29 fault injection is a different mechanism and cannot be counted as a FU-5 occurrence.

- [ ] **Step 3: Update the pool without claiming a fix.**

Change only current-state pool prose needed to say all of the following:

1. `P11-FU-5` is **reproduced, context known** on Windows; it reproduced three times in the two Git-spawning hygiene selectors on 2026-08-14/15, and its source reports are named.
2. The historical ten-run no-reproduction remains historical context. It is not a contrary result and does not establish durable absence.
3. `P11-FU-5` and `P11-FU-6` are scheduled to Plan 11.17 with distinct mechanisms and independently required closure evidence.
4. `P11-FU-7` has two concise current-state lines: its 25-run Windows `--cov` gate remains unrun after 4/25 because `P11-FU-6` failed; do not resume or claim that gate until FU-6 has a recorded disposition.

Do not close, merge, retry, skip, or otherwise minimize either flake in this step. Do not revise a frozen Plan 11.14/11.15 artifact.

- [ ] **Step 4: Verify the documentation-only custody change and commit it separately.**

```powershell
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
uv run --frozen ruff check .
git diff --check
git diff -- docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md
git add docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md reports/plan-11-17-windows-resource-lifecycle-baseline.md
git commit -m "docs: record Windows resource lifecycle custody"
```

Expected: pool hygiene and Ruff pass, diff hygiene is clean, and the commit contains no production or test behavior change.

---

### Task 1: Establish the Windows observation bound before attributing a cause

**Files:**

- Create: `reports/plan-11-17-windows-resource-lifecycle-baseline.md`
- Read: `tests/unit/optimus_gateway/test_server.py:59-75,172-175,405-412`; `tests/unit/docs/test_open_work_pool_hygiene.py:291-298,556-559,1323-1333`

**Interfaces:**

- Consumes: a clean Windows implementation worktree and Task 0's exact checkout/platform provenance.
- Produces: fifty-nine separately logged unit-suite processes, isolated comparisons for any occurrence, and an observation matrix that distinguishes FU-5, FU-6, FU-7, and unrelated failures.

- [ ] **Step 1: Run exactly fifty-nine independently launched Windows unit-suite processes.**

```powershell
$logRoot = Join-Path $env:TEMP "plan-11-17-windows-unit-runs"
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
1..59 | ForEach-Object {
  $run = $_
  $log = Join-Path $logRoot ("unit-{0:D2}.log" -f $run)
  uv run --frozen pytest tests/unit -q *>&1 | Tee-Object -FilePath $log
  if ($LASTEXITCODE -ne 0) { Write-Host "run $run failed" }
}
```

Do not retry a failed process as though it passed. Keep each raw log outside the repository or attach it through the approved evidence channel; the committed report lists its SHA-256, result, duration, and matching selector(s).

- [ ] **Step 2: Characterize every observed FU-5/FU-6 failure without consuming another lane.**

For each failure, run only the affected selector and then its containing file once. For FU-6 use the current successor selector and `tests/unit/optimus_gateway/test_server.py`; for FU-5 use the two named pool-hygiene selectors and `tests/unit/docs/test_open_work_pool_hygiene.py`. Record whether each comparison passes, fails, skips, or deselects.

```powershell
uv run --frozen pytest tests/unit/optimus_gateway/test_server.py::test_tools_routes_remain_not_found -q
uv run --frozen pytest tests/unit/optimus_gateway/test_server.py -q
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py::test_immutable_documents_match_approved_head_blobs tests/unit/docs/test_open_work_pool_hygiene.py::test_product_checkpoint_log_location_remains_gitignored -q
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
```

If a `P11-FU-7` selector fails, log it as out-of-scope confirmation only; do not begin its `--cov` run, alter its tests, or call it a Plan 11.17 result.

- [ ] **Step 3: Apply the branch condition from the observation matrix.**

- If all fifty-nine unit-suite processes are clean for FU-6, mark the **FU-6 bounded no-reproduction branch** eligible and skip to Task 5. Record the 95.2% conditional detection power, the 4.8% model residual, and the rate/independence assumptions. The fifty-nine-run evidence closes only FU-6; it does not prove absence.
- If FU-6 recurs, continue to Task 2; preserve the failing log and the resulting isolated/file comparisons.
- Whether or not FU-5 appears again, continue its bounded source/lifecycle comparison in Task 2. A clean FU-5 observation adds a datum but cannot select a no-reproduction closure branch.

---

### Task 2: Determine whether the two resource failures share a causal chain

**Files:**

- Create: `reports/plan-11-17-p11-fu-5-windows-disposition.md`
- Create: `reports/plan-11-17-p11-fu-6-root-cause.md`
- Read: `tests/unit/optimus_gateway/test_server.py:59-75,172-175`; `src/optimus_gateway/server.py:92-120`; `src/optimus_gateway/__main__.py:97-109`; `tests/unit/docs/test_open_work_pool_hygiene.py:291-298,1323-1333`

**Interfaces:**

- Consumes: Task 1 occurrence logs and the source ownership boundaries.
- Produces: a causal decision signed by evidence rather than resemblance, plus a narrow deterministic-injection target if a correction branch is justified.

- [ ] **Step 1: Build an event timeline for every FU-6 recurrence.**

For each relevant log, record the order and ownership of: `serve_gateway()` construction; `ThreadingHTTPServer` bind; `serve_forever` thread start; client request; handler completion or exception; `server.shutdown()`; `server.server_close()`; and `thread.join(timeout=5)`. Record `server.server_address`, whether the server thread was still alive after join, and any thread exception. The timeline must identify whether the client-side `HTTPConnection.getresponse()` error is upstream of, simultaneous with, or after teardown.

Use temporary local-only diagnostics only when they observe an already-existing lifecycle edge and can be removed before the deterministic red. Do not add logging, sleeps, retries, or broad exception handlers as a proposed remedy.

- [ ] **Step 2: Build the FU-5 subprocess lifecycle timeline.**

Trace only the real `subprocess.run(["git", ...], cwd=REPO_ROOT, capture_output=True)` calls in `_head_blob_sha256()` and `test_product_checkpoint_log_location_remains_gitignored()`: parent process, Git child creation, inherited/captured handles, error origin, and process completion. State explicitly whether the observed `DuplicateHandle` occurred before child launch, during handle inheritance, or on completion; if the record cannot prove a phase, label it unknown rather than infer it.

- [ ] **Step 3: Compare against P11-FU-26 and make the shared/separate decision.**

The decision record must answer all of these, with a log or source reference for each answer:

1. Does the `P11-FU-26` `WinError 10053` signal pass through the same current `ThreadingHTTPServer` lifecycle edge as FU-6?
2. Does any FU-5 observation include a socket/server/thread resource, or does it remain a Git child-process handle operation?
3. Can one deterministic causal chain reproduce both failures? If not, retain two fully independent investigations.
4. Is the observed FU-6 fault test-local only, or does independently driven Gateway lifecycle behavior reproduce it outside `_start_server()` / `_stop_server()`?

Record one of `shared`, `separate`, or `insufficient_evidence`. `shared` requires the single deterministic chain; Windows co-occurrence, similar error numbers, or both being resource-lifecycle failures is insufficient.

- [ ] **Step 4: Hold the production-scope reviewer gate when evidence requires it.**

If Step 3 identifies a production reproduction, add a dated ruling to the gitignored checkpoint log before source edits. It must name the public Gateway lifecycle, the independent driver, the concrete production failure, the narrowest candidate source boundary, the unchanged route assertions, and the required production evidence. If that ruling is absent, only the harness/no-code branches remain permitted.

---

### Task 3: Establish a deterministic red only for a supported correction

**Files:**

- Modify (harness branch): `tests/unit/optimus_gateway/test_server.py`
- Modify (FU-5 test-local branch): `tests/unit/docs/test_open_work_pool_hygiene.py`
- Modify (production branch): `tests/unit/optimus_gateway/test_server.py`, with production files still read-only until the red is proven

**Interfaces:**

- Consumes: Task 2's cause and approved scope classification.
- Produces: one narrow test or controlled injection that fails reliably on the pre-fix behavior and proves the named lifecycle invariant without changing the existing functional assertions.

- [ ] **Step 1: Choose the injection point from the recorded failed lifecycle edge.**

- For a Gateway harness defect, inject only the measured incomplete lifecycle edge, such as completion observed before the server thread has stopped or before the listening socket is released. The test must retain the real route request and status/body assertion.
- For a Gateway production defect, drive the public `serve_gateway()` / process lifecycle independently from the test helpers and assert the public cleanup behavior identified in Task 2. Do not mock the failure away or use the test helper as the only driver.
- For an established FU-5 test-local cause, inject only the proved subprocess handle-ownership edge while leaving the actual `git show HEAD:<path>` and `git check-ignore --quiet -- <path>` assertions intact.

If no injection point follows from evidence, make no source/test edit, mark the deterministic-red path unavailable in the report, and proceed directly to Task 5's open-custody branch.

- [ ] **Step 2: Run the evidence-named red selector three times against the pre-fix behavior.**

Use the exact selector written in the Task 2 cause record, unchanged, for three independent `uv run --frozen pytest` invocations targeting that selector. The evidence report writes all three complete commands and outputs. The expected result is failure on all three runs with the intended lifecycle assertion. If any invocation passes, stop: remove or repair the injection, document the false green, and do not edit implementation code. Do not substitute a sleep, a longer timeout, a retry, or an xfail/skip.

- [ ] **Step 3: Record the red evidence and approve the applicable correction branch.**

The report must include the exact assertion, three command outputs, the mapped failing edge, and the branch (`harness` or `production`). Production source edits additionally require the Task 2 checkpoint ruling. A natural full-suite recurrence by itself does not satisfy this step.

---

### Task 4: Apply and verify only the selected lifecycle correction

**Files:**

- Modify (harness branch): `tests/unit/optimus_gateway/test_server.py`
- Modify (FU-5 test-local branch): `tests/unit/docs/test_open_work_pool_hygiene.py`
- Modify (production branch only): `src/optimus_gateway/server.py`; `src/optimus_gateway/__main__.py` only if the approved production evidence establishes entrypoint ownership
- Test: all selectors named in Tasks 1 and 3

**Interfaces:**

- Consumes: a deterministic red and the Task 2 classification.
- Produces: the smallest lifecycle correction, green focused/containing-file tests, and a Windows run matrix that exercises FU-6 without claiming the FU-7 gate.

- [ ] **Step 1: Make the minimum change at the proven ownership boundary.**

For the harness branch, change only test-owned lifecycle coordination necessary to establish a closed server/thread before the next test; do not alter `serve_gateway()` or route behavior. For the production branch, change only the verified production owner and retain a separate test of the helper's correct use of that public lifecycle. For FU-5, change only the proved subprocess-handle ownership seam and preserve both real Git commands and their asserted results.

- [ ] **Step 2: Prove the evidence-named former red is green and retain the existing assertions.**

Run the exact concrete selector recorded in Task 2, then run the Gateway containing file and the two real FU-5 selectors:

```powershell
uv run --frozen pytest tests/unit/optimus_gateway/test_server.py -q
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py::test_immutable_documents_match_approved_head_blobs tests/unit/docs/test_open_work_pool_hygiene.py::test_product_checkpoint_log_location_remains_gitignored -q
```

The evidence report includes the concrete former-red command and result. Expected: all commands pass. Inspect the diff to prove the target route status/body assertions and the two Git subprocess assertions are unchanged except for necessary lifecycle setup/teardown evidence.

- [ ] **Step 3: Run the FU-6-specific Windows confirmation matrix.**

Run the fifty-nine independently launched `uv run --frozen pytest tests/unit -q` processes from Task 1 again, retaining the same per-process log format and result table. This is FU-6 evidence, not the P11-FU-7 coverage gate. Do not run 25 `--cov` processes or close P11-FU-7 under this plan.

If FU-6 recurs after the correction, do not retry past it. Return to Task 2 with the new lifecycle event and leave FU-6 open unless the evidence changes the classification.

- [ ] **Step 4: Run Windows final gates and make the correction available for native-WSL parity.**

```powershell
uv run --frozen pytest tests/unit -q
uv run --frozen pytest --cov -q
uv run --frozen ruff check .
git diff --check
git status --short --branch
```

Any `P11-FU-7` failure is recorded as an unrun/failed separate lane, not hidden or credited to this work. Do not commit a correction while its required test/coverage/Ruff gates are red. Commit only the selected files and its matching evidence report; do not stage the reviewer checkpoint log. Fetch and intentionally merge `origin/main` if it drifted, then push the verified correction branch so a native WSL clone can check out its exact SHA.

- [ ] **Step 5: Reproduce the selected correction from a native WSL ext4 clone.**

This step is mandatory if any test or production correction was made. It is Linux-parity evidence only and cannot close the Windows flake.

```bash
cd ~/src/optimus-cost-agent
git fetch origin agent/codex/plan-11-17-windows-resource-lifecycle-impl
git switch --detach origin/agent/codex/plan-11-17-windows-resource-lifecycle-impl
test "$(command -v git)" = /usr/bin/git
case "$PWD" in /mnt/*) exit 1;; esac
test -z "${UV_PROJECT_ENVIRONMENT:-}"
stat -f -c '%T' .
uv sync --frozen --extra dev
uv run --frozen pytest tests/unit/optimus_gateway/test_server.py tests/unit/docs/test_open_work_pool_hygiene.py -q
uv run --frozen pytest --cov -q
uv run --frozen ruff check .
```

Record the exact pushed SHA, native path/filesystem, `/usr/bin/git` and `uv` versions, every pass/fail/skip/deselect result, and any known-Windows flake that does not reproduce. If the WSL check fails, preserve the evidence and return to Task 2; do not claim cross-platform readiness.

---

### Task 5: Publish the independently bounded dispositions and audit custody

**Files:**

- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`
- Create: `reports/plan-11-17-p11-fu-5-windows-disposition.md`
- Create: `reports/plan-11-17-p11-fu-6-root-cause.md`
- Create: `reports/plan-11-17-windows-resource-lifecycle-release.md`
- Audit/update only if stale: `README.md`, roadmap, Plan 11 charter, runbook

**Interfaces:**

- Consumes: Task 0-4 reports, review rulings, exact implementation SHA, and any native-WSL parity artifact.
- Produces: a current pool that never cross-credits FU-5/FU-6/FU-7, an explicit P11-FU-4 status, and an auditable release/disposition artifact.

- [ ] **Step 1: Apply the correct FU-6 terminal status, and no broader one.**

- **Bounded no-reproduction:** Close FU-6 only after fifty-nine clean Windows unit-suite processes with raw-log hashes, target-selector visibility, exact checkout/tool versions, and no skipped/deselected substitution. State the conditional 95.2% detection power / 4.8% residual using the observed 5% rate, that this assumes independent representative processes, and that it is not proof of absence.
- **Corrected harness or production cause:** Close FU-6 only after the deterministic red/green evidence, the matching Task 4 Windows matrix, and (for production) the checkpoint ruling plus independent lifecycle proof.
- **Recurrence without deterministic cause:** Leave FU-6 open. Record `reproduced, root cause unestablished`, the exact next observation target, and its existing named pool custody. Do not invent a closure from a clean rerun.

In every branch, mention P11-FU-26 only as transferred signal and retain P11-FU-7 as an unrun dependent lane until it executes its own 25-process gate.

- [ ] **Step 2: Apply the distinct FU-5 disposition and its explicit limit.**

The final FU-5 entry/report must always retain: the three Windows reproductions; the two real Git-spawning selectors; `WinError 6` / `DuplicateHandle`; report anchors; and the separate FU-29 injected-fault exclusion. It must state that FU-5's rate is unknown, so clean additional runs are observations only and do not prove absence.

Close FU-5 only if its own reviewed causal/fix or explicitly accepted reproduction disposition meets its acceptance criteria. Otherwise leave it open with the new `reproduced, context known` status and named future Windows-investigation custody. Never borrow FU-6's socket evidence or its fifty-nine-clean-run bound.

- [ ] **Step 3: Determine P11-FU-4's exact custody status without name-based inference.**

Read P11-FU-4's acceptance criterion and distinguish its historical `FU-4A`/`FU-5` evidence labels from the current `P11-FU-5` Windows flake identifier. Record one of `not discharged`, `partly discharged`, or `discharged`, with named proof for every part. If it remains open, its pool row must retain a named owning roadmap entry and say exactly what fresh real-`acpx` evidence remains required. A similar spelling is not evidence of shared closure.

- [ ] **Step 4: Perform the current-state documentation freshness audit.**

```powershell
rg -n "P11-FU-4|P11-FU-5|P11-FU-6|P11-FU-7|P11-FU-26|DuplicateHandle|WinError 10053|resource.lifecycle|Plan 11.17" README.md docs/superpowers/plans docs/runbooks reports
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
uv run --frozen ruff check .
git diff --check
git diff --name-only origin/main...HEAD
git status --short --branch
```

Update every current-state claim made stale by the actual disposition, but preserve historical/frozen documents unchanged. The final report must identify the documents read, those changed, those found current, all unrun tiers, and the exact implementation/report SHA(s).

- [ ] **Step 5: Commit the disposition evidence and publish the implementation PR only after final drift checks.**

```powershell
git add docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md reports/plan-11-17-p11-fu-5-windows-disposition.md reports/plan-11-17-p11-fu-6-root-cause.md reports/plan-11-17-windows-resource-lifecycle-release.md
git add README.md docs/superpowers/plans/2026-07-01-phase-1-roadmap.md docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md docs/runbooks/local-live-dependencies.md
git commit -m "docs: disposition Windows resource lifecycle findings"
git fetch origin main
git rev-list --left-right --count HEAD...origin/main
```

Stage the audited current-state documents only if they changed. If `origin/main` drifted, merge it intentionally, re-run all affected gates, and then push/open the implementation PR. Never stage `docs/superpowers/reviews/plan-11-17-review-checkpoints.md`.

## Claim-to-task traceability

| Required claim | Primary task | Required evidence |
|---|---:|---|
| FU-5's three historical Windows reproductions are current-state record, not orphaned report facts | 0 | exact pool text plus Plan 11.14/11.15 report anchors |
| FU-5 and FU-29 remain distinct | 0, 2, 5 | pool wording and separate mechanism statement |
| FU-6 has a 59-process Windows observation bound with explicit statistical power | 1 | raw per-process logs, provenance matrix, and 95.2% conditional detection-power calculation |
| Clean 59-process FU-6 result closes only that entry | 1, 5 | bounded no-reproduction record with exact config, 4.8% model residual, and stated assumptions |
| Gateway socket and Git-handle causes are not presumed shared | 2 | event timelines and `shared`/`separate`/`insufficient_evidence` decision |
| P11-FU-26 transfer is evaluated without reopening a retired lane | 2, 5 | comparison to current `test_server` lifecycle |
| Test harness vs production scope is evidence-bound | 2, 3 | independent driver result and, if needed, checkpoint ruling |
| Any correction has a deterministic red | 3 | three pre-fix failures from the exact lifecycle injection |
| Assertions and safety are not weakened | 3, 4 | diff review plus focused test results |
| FU-7's 25-run coverage gate is protected from false credit | 0, 4, 5 | two-line dependency statement and unrun-tier report |
| P11-FU-4 has explicit, non-ambiguous custody | 5 | status ruling against its own acceptance criterion |
| Windows claims are not substituted with WSL evidence | 1-5 | Windows provenance; any native ext4 report is labelled parity only |

## Definition of Done for implementation

- [ ] P11-FU-5's detailed pool entry records the three 2026-08-14/15 Windows `DuplicateHandle` reproductions, both selector names, report anchors, and the separate FU-29 mechanism; historical ten-run cleanliness remains correctly bounded.
- [ ] P11-FU-6 has exactly one of the evidence-supported states in the decision table; no natural-rate recurrence is represented as a deterministic red.
- [ ] The investigation says whether FU-5 and FU-6 are shared, separate, or insufficiently evidenced, and names the P11-FU-26 comparison result.
- [ ] No retry, sleep, skip, deselection, timeout widening, weakened assertion, or unreviewed production mutation was used to make a result green.
- [ ] Any correction has a three-run deterministic pre-fix red, a focused green, its containing-file green, fifty-nine Windows FU-6 confirmation processes, required coverage/Ruff/diff gates, and no unreported separate-lane failure.
- [ ] P11-FU-7's 25-run coverage gate remains explicitly gated on P11-FU-6 and is neither run nor closed by this plan.
- [ ] P11-FU-4 is explicitly recorded as discharged, partly discharged, or still open from its own acceptance criteria, with named custody for any remaining work.
- [ ] The release report distinguishes Windows evidence, optional native-ext4 parity evidence, unrun tiers, exact SHAs, and every current-state document audited.
- [ ] The reviewer checkpoint log is current, gitignored, and unstaged. Only after operator plan approval may implementation begin.
