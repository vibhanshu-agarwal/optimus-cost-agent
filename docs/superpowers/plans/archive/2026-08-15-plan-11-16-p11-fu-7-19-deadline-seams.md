# P11-FU-7 and P11-FU-19 Deadline-Seam Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate two timing flakes without enlarging either affected timeout: make the ACP NDJSON sanitization test use finite-input completion rather than a one-second wall clock, and make each client-MCP operation expose one authoritative `OPERATION_TIMEOUT` rather than race its async deadline against a host deadline.

**Architecture:** The findings remain independent lanes. `P11-FU-7` changes only `tests/unit/acp/test_stdio_ndjson.py`: its one-message `BytesIO` reader already has deterministic EOF, so that lifecycle becomes the test's completion boundary. `P11-FU-19` changes shipped `ClientMcpSdkAdapter` behavior: all four synchronous SDK entries use the exact `operation_timeout_seconds` value; an expiry observed by either the operation's `asyncio.wait_for` or the synchronous supervisor wait becomes the same public `ClientMcpSdkError("OPERATION_TIMEOUT")`. The generic supervisor keeps explicit `SUBMIT_TIMEOUT` for non-SDK callers.

**Tech Stack:** Python 3.14, `asyncio`, `concurrent.futures`, `threading`, `pytest`, `pytest-asyncio`, `coverage.py`, `pytest-cov`, Ruff, Windows, native WSL2 ext4 with `/usr/bin/git`, `uv`, and Markdown evidence artifacts.

**Status:** Draft planning artifact. Implementation has not started. Before this branch was created, Plan 11.16 was verified unclaimed in `docs/superpowers/plans/`, local/remote branch names, and the consolidated pool. This branch was cut from `origin/main` `e1587aa07617e01ff2c2079c97f525aec0557f40`; `HEAD` and `origin/main` matched at creation.

## Authority and decision record

- `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` owns both open entries. Its Batch B correction is binding: P11-FU-19 reproduced 2/100 in standalone native WSL2 runs; suite load is not a prerequisite.
- `docs/superpowers/specs/2026-08-06-p11-fu-9-client-supplied-acp-mcp-servers-design.md:151-186` requires one supervisor, bounded submissions, safe shutdown, 30-second initialize/discovery/call deadlines, and no retry/replay.
- `docs/Optimus-Cost-Agent-LLD-v2.41.pdf` and the Test Strategy preserve client-owned MCP controls, untrusted tool output, and independently authored live client-MCP tiers.
- `docs/runbooks/local-live-dependencies.md:198-228` requires a native WSL ext4 clone for Linux evidence. `/mnt/d`, Windows Git, linked Windows worktrees, shared Windows environments, and `UV_PROJECT_ENVIRONMENT` are invalid.

### P11-FU-19 deadline decision

Do not try to make an async timeout beat an arbitrary larger host margin: loop starvation makes that unprovable. Do not remove host bounds either; P11-FU-9 requires bounded submissions. Instead make the adapter's operation deadline a single public contract:

```python
def _submit_operation(self, coro: Coroutine[object, object, T]) -> T:
    try:
        return self._supervisor.submit(coro, timeout_seconds=self._operation_timeout_seconds)
    except MCPSupervisorError as exc:
        if exc.code == "SUBMIT_TIMEOUT":
            raise ClientMcpSdkError("OPERATION_TIMEOUT") from exc
        raise
```

Route `open`, `discover`, `call`, and `read_streamed_bytes_for_tests` through this helper. Existing inner `asyncio.wait_for` paths retain their mapping. If a starved loop prevents them running, the same operation deadline expires at the synchronous boundary and yields the same public error. There is no externally observable race between timeout error types. The generic `MCPAsyncSupervisor` API and direct caller behavior do not change.

This is a production correction to live client-MCP behavior, not test scaffolding. It retains the 30-second default, no retries/replay, loop state/cancellation behavior, and a bounded streamed-byte path.

## Global constraints

- Create implementation worktrees from refreshed `origin/main`; never use this planning branch, another feature branch, or `optimus-cost-agent-wt-vibhanshu`.
- Keep pool rows, commits, reports, evidence, and closure decisions separate. P11-FU-7 may close while P11-FU-19 remains the named open owner.
- Do not widen the one-second NDJSON guard, the 0.2-second SDK test budget, or the 30-second production default. P11-FU-7 removes its test-owned clock and uses finite EOF completion; it does not substitute a longer clock.
- Do not re-diagnose P11-FU-7 as ACP, sanitization, port, or launch-trust behavior. Preserve every current redaction assertion.
- Do not call P11-FU-19 load-dependent. Its natural rate is characterization only; deterministic loop starvation/delay is the TDD gate.
- If a deterministic red passes first time, stop and repair the injection/test target before source changes or green claims.
- Preserve one supervisor loop, `RUNNING`/`STOPPING`/`DEAD`, no per-call `asyncio.run()`, no automatic retry/replay, transport limits, secret boundaries, and untrusted-output handling.
- Windows is mandatory for both lanes. P11-FU-7 requires 25 full Windows `--cov` processes; P11-FU-19 requires 200 standalone selectors in native WSL ext4.
- Use bare `--cov`; before every commit, push, or PR sign-off run `uv run --frozen ruff check .`. The approved plan is immutable; a changed decision requires forward-only `_v2` amendment.

## File map

### Modify during implementation

- `tests/unit/docs/test_open_work_pool_hygiene.py` — verify separate P11-FU-7/P11-FU-19 status and closure ownership.
- `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` — schedule both entries, then close each only on its own evidence.
- `tests/unit/acp/test_stdio_ndjson.py:151-175` — replace only the two target wrappers with finite EOF completion.
- `src/optimus/mcp/client_sdk.py:90-141` — private one-deadline helper and four callers.
- `tests/unit/mcp/test_client_sdk.py:140-180,430-453` — controlled loop-starvation and all-entry-point public-error tests.
- `tests/unit/mcp/test_client_supervisor.py:40-70` — retain direct generic `SUBMIT_TIMEOUT` coverage.

### Create during implementation, not in this plan PR

- `reports/plan-11-16-deadline-seams-baseline.md`
- `reports/plan-11-16-p11-fu-7-windows-evidence.md`
- `reports/plan-11-16-p11-fu-19-windows-evidence.md`
- `reports/plan-11-16-p11-fu-19-wsl-evidence.md`
- `reports/plan-11-16-deadline-seams-release.md`

### Read-only authority

- `src/optimus/mcp/client_supervisor.py:83-106` — generic timeout/cancel/error behavior; do not alter without an approved amendment.
- `src/optimus/mcp/client_sdk.py:143-267` — existing inner timeouts and streamed-byte behavior.
- `src/optimus/acp/server.py:245-350` — finite EOF/read/request-task lifecycle.
- `pyproject.toml`, `README.md`, roadmap, Plan 11 charter, and runbook — final freshness audit.
- `docs/superpowers/reviews/plan-11-16-review-checkpoints.md` — reviewer-owned/gitignored; read and verify it, never stage it.

---

### Task 0: Register separate Plan 11.16 custody and baseline the two lanes

**Files:**

- Modify: `tests/unit/docs/test_open_work_pool_hygiene.py`
- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md:132,567-604,156,1263-1302`
- Create: `reports/plan-11-16-deadline-seams-baseline.md`

**Interfaces:**

- Consumes: pool index/detail rows and the two settled diagnoses.
- Produces: two separate `Scheduled -> Plan 11.16` links, a baseline report, and a hygiene test that rejects cross-crediting.

- [ ] **Step 1: Create and validate the clean implementation worktree.**

```powershell
git fetch origin main
git worktree add -b agent/codex/plan-11-16-deadline-seams ..\optimus-cost-agent-wt-codex-11-16 origin/main
git -C ..\optimus-cost-agent-wt-codex-11-16 status --short --branch
git -C ..\optimus-cost-agent-wt-codex-11-16 rev-parse HEAD
git -C ..\optimus-cost-agent-wt-codex-11-16 rev-parse origin/main
Get-Content ..\optimus-cost-agent-wt-codex-11-16\docs\superpowers\reviews\plan-11-16-review-checkpoints.md -ErrorAction SilentlyContinue
```

Expected: clean status and equal hashes. Stop for drift, an unrelated change, or a checkpoint conflict.

- [ ] **Step 2: Write the deterministic pool-projection red.**

Add a hygiene test that parses both index rows/detail sections and requires:

```python
assert indexed["P11-FU-7"].status == "Scheduled"
assert indexed["P11-FU-19"].status == "Scheduled"
assert "Plan 11.16" in p11_fu_7
assert "Plan 11.16" in p11_fu_19
assert "P11-FU-19" not in p11_fu_7_closure_evidence
assert "P11-FU-7" not in p11_fu_19_closure_evidence
```

```powershell
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
```

Expected: FAIL because both entries are still open. If it passes, stop: the red is not reading the current pool rows.

- [ ] **Step 3: Promote both entries without closing either.**

Change only P11-FU-7 and P11-FU-19 to `Scheduled -> Plan 11.16`. Preserve P11-FU-7's settled test-only cause and P11-FU-19's 2/100 standalone correction. State explicitly that P11-FU-7 may close if P11-FU-19 fails a production/evidence gate.

- [ ] **Step 4: Record baseline provenance and commit only custody.**

Record base SHA, platform/tool versions, original 0.2/1.0/30 values, and red commands/results.

```powershell
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
git diff --check
git add tests/unit/docs/test_open_work_pool_hygiene.py docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md reports/plan-11-16-deadline-seams-baseline.md
git commit -m "docs: schedule separate deadline-seam findings"
```

---

### Task 1: Remove P11-FU-7's test-owned wall-clock oracle

**Files:**

- Modify: `tests/unit/acp/test_stdio_ndjson.py:151-175`
- Do not modify: `src/optimus/acp/server.py`
- Evidence: `reports/plan-11-16-p11-fu-7-windows-evidence.md`

**Interfaces:**

- Consumes: a finite one-message `StdioNdjsonLineReader(BytesIO(...))`, EOF, and `_CapturingNdjsonWriter.messages`.
- Produces: finite-input completion with response/message/stderr assertions unchanged and no target `asyncio.wait_for(..., timeout=1)`.

- [ ] **Step 1: Prove the existing one-second guard fails deterministically.**

Before changing current wrappers, add a temporary test-local blocker. It signals `entered`, waits for `release`, and a cleanup-safe releaser is released after exactly 1.1 seconds:

```python
entered = asyncio.Event()
release = asyncio.Event()

async def failing_handle_client_request(_self, _message):
    entered.set()
    await release.wait()
    raise RuntimeError("OPTIMUS_API_KEY=top-secret-canary")
```

```powershell
uv run --frozen pytest tests/unit/acp/test_stdio_ndjson.py::test_serve_ndjson_sanitizes_request_processing_response_and_stderr -q
```

Expected: FAIL with the target test's `TimeoutError`, not failed redaction. Record it, then remove the injector. If it passes, stop and repair the injection; natural recurrence is not a red gate.

- [ ] **Step 2: Replace exactly the two target wrappers.**

Directly await the finite server lifecycle; do not change input, timeout, assertions, logging, or production server:

```python
await configured.server.serve_ndjson(reader, writer)
# existing response and stderr assertions remain here
await configured.server.serve_ndjson(failed_reader, failed_writer)
```

The reader emits EOF after its sole line and `serve_ndjson` drains/awaits request tasks before return. This structural lifecycle, not a longer clock, is the completion oracle.

- [ ] **Step 3: Run green and prove production ACP code is untouched.**

```powershell
uv run --frozen pytest tests/unit/acp/test_stdio_ndjson.py -q
git diff -- src/optimus/acp/server.py
git diff --check
```

Expected: focused green, empty `server.py` diff, and intact sanitization assertions.

- [ ] **Step 4: Commit only the test-side remedy.**

```powershell
git add tests/unit/acp/test_stdio_ndjson.py
git commit -m "test: remove ACP ndjson wall-clock guard"
```

---

### Task 2: Close P11-FU-7 independently with Windows coverage evidence

**Files:**

- Create: `reports/plan-11-16-p11-fu-7-windows-evidence.md`
- Modify on pass only: consolidated pool

**Interfaces:** Consumes Task 1, real Windows, and coverage tracing; produces P11-FU-7-only evidence and closure.

- [ ] **Step 1: Record Windows provenance and focused coverage.**

```powershell
git status --short --branch
git rev-parse HEAD
where.exe git
uv run --frozen python -c "import platform,sys,pytest,coverage; print(sys.platform); print(platform.platform()); print(sys.version); print(pytest.__version__); print(coverage.__version__)"
uv run --frozen pytest tests/unit/acp/test_stdio_ndjson.py --cov -q
```

Record SHA, Windows/filesystem/tool versions, focused count, coverage, and retained assertions.

- [ ] **Step 2: Run 25 independent full Windows coverage suites.**

Keep every log and stop on the first failure instead of retrying it away.

```powershell
1..25 | ForEach-Object {
    $run = $_
    uv run --frozen pytest --cov -q *> "reports/plan-11-16-p11-fu-7-windows-cov-run-$run.log"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

Expected: 25/25 clean full suites. Report exact count, duration, coverage, and any unrelated failure. Isolated/non-coverage runs cannot replace this gate.

- [ ] **Step 3: Close and commit P11-FU-7 only if gates pass.**

Set only P11-FU-7 to `Closed`, cite this report/Task 1, state that the clock was removed rather than widened, and leave P11-FU-19 scheduled/open.

```powershell
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
git diff --check
git add docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md reports/plan-11-16-p11-fu-7-windows-evidence.md reports/plan-11-16-p11-fu-7-windows-cov-run-*.log
git commit -m "docs: close P11-FU-7 coverage timing flake"
```

---

### Task 3: Give live client-MCP operations one public deadline outcome

**Files:**

- Modify: `src/optimus/mcp/client_sdk.py:90-141`
- Modify: `tests/unit/mcp/test_client_sdk.py:140-180,430-453`
- Test/preserve: `tests/unit/mcp/test_client_supervisor.py:40-70`
- Do not modify without approved amendment: `src/optimus/mcp/client_supervisor.py`

**Interfaces:**

- Consumes: existing `MCPAsyncSupervisor.submit(coro, timeout_seconds=...)` and adapter `_operation_timeout_seconds`.
- Produces: a bounded public timeout contract for open/discover/call/stream; no SDK expiry exposes `SUBMIT_TIMEOUT`.

- [ ] **Step 1: Add a controlled loop-starvation red before production code.**

Schedule a callback on the started real supervisor loop. It signals entry, blocks until release, and is always released/joined in `finally`. Start real `adapter.open()` with a 0.2-second budget in a worker only after the blocker entered.

```python
loop_blocked = threading.Event()
release_loop = threading.Event()
outcome_ready = threading.Event()
outcome: list[BaseException] = []

def block_loop() -> None:
    loop_blocked.set()
    release_loop.wait()

supervisor._loop.call_soon_threadsafe(block_loop)  # test-only seam
assert loop_blocked.wait(timeout=1)
worker = threading.Thread(target=run_open, daemon=True)
worker.start()
```

With legacy `+ 1.0`, assert the operation has not completed by its 0.2 deadline plus a 0.4-second test-coordination allowance; release the loop and collect legacy `SUBMIT_TIMEOUT`. The test requires `ClientMcpSdkError("OPERATION_TIMEOUT")`, so it fails deterministically. Always release, join, and close in `finally`.

```powershell
uv run --frozen pytest tests/unit/mcp/test_client_sdk.py::test_operation_deadline_is_enforced -q
```

Expected: FAIL with legacy `MCPSupervisorError("SUBMIT_TIMEOUT")` or unmet completion-by-budget assertion. A first-run pass means the loop was not blocked before submission; stop and repair it.

- [ ] **Step 2: Add the one-deadline adapter helper and use all four entries.**

Add `_submit_operation()` beside synchronous SDK methods. Replace every `self._operation_timeout_seconds + 1.0` in `open`, `discover`, `call`, and `read_streamed_bytes_for_tests`. Keep existing inner `asyncio.wait_for`; the streamed-byte method is bounded by the exact synchronous deadline and must be tested.

Do not change the 30-second default, map shutdown/dead errors, add a margin, alter generic supervisor code, add a retry, or replay a call.

- [ ] **Step 3: Make the public contract exhaustive and run green.**

Add slow fake session/stream tests and retain the blocker for scheduling starvation:

```python
assert _open_with_starved_loop().code == "OPERATION_TIMEOUT"
assert _discover_over_budget().code == "OPERATION_TIMEOUT"
assert _call_over_budget().code == "OPERATION_TIMEOUT"
assert _stream_over_budget().code == "OPERATION_TIMEOUT"

with pytest.raises(MCPSupervisorError, match="SUBMIT_TIMEOUT"):
    supervisor.submit(_slow(), timeout_seconds=0.2)
```

```powershell
uv run --frozen pytest tests/unit/mcp/test_client_sdk.py tests/unit/mcp/test_client_supervisor.py -q
uv run --frozen pytest tests/integration/mcp/test_client_sdk_real.py -q
git diff --check
```

Expected: all SDK expiries are public `OPERATION_TIMEOUT`; direct generic expiry remains `SUBMIT_TIMEOUT`; shutdown behavior is unchanged. A marker skip is recorded as unrun, never as a pass.

- [ ] **Step 4: Commit production correction separately.**

```powershell
git add src/optimus/mcp/client_sdk.py tests/unit/mcp/test_client_sdk.py tests/unit/mcp/test_client_supervisor.py
git commit -m "fix: unify client MCP operation deadlines"
```

---

### Task 4: Collect P11-FU-19 Windows and native WSL evidence, then decide closure

**Files:**

- Create: `reports/plan-11-16-p11-fu-19-windows-evidence.md`
- Create: `reports/plan-11-16-p11-fu-19-wsl-evidence.md`
- Modify on pass only: consolidated pool

**Interfaces:** Consumes Task 3's exact SHA, real Windows, and native WSL ext4; produces P11-FU-19-only evidence/decision.

- [ ] **Step 1: Run mandatory Windows proof.**

```powershell
git status --short --branch
git rev-parse HEAD
where.exe git
uv run --frozen python -c "import platform,sys; print(sys.platform); print(platform.platform()); print(sys.version)"
uv run --frozen pytest tests/unit/mcp/test_client_sdk.py tests/unit/mcp/test_client_supervisor.py -q
uv run --frozen pytest tests/unit/mcp/test_client_sdk.py tests/unit/mcp/test_client_supervisor.py --cov -q
uv run --frozen pytest --cov -q
```

Record exact SHA, Windows/filesystem/tool versions, starvation green, full-suite count, coverage/duration, and every skip. The starvation proof must use real `ClientMcpSdkAdapter.open()`, not a mocked adapter/supervisor.

- [ ] **Step 2: Check out the exact SHA in native WSL ext4.**

```bash
cd ~/src/optimus-cost-agent
git fetch origin agent/codex/plan-11-16-deadline-seams
git switch --detach origin/agent/codex/plan-11-16-deadline-seams
test "$(command -v git)" = /usr/bin/git
test -z "$UV_PROJECT_ENVIRONMENT"
case "$PWD" in /mnt/*) exit 1;; esac
stat -f -c '%T' .
git rev-parse HEAD
git rev-parse origin/agent/codex/plan-11-16-deadline-seams
uv sync --frozen --extra dev
test -x .venv/bin/python
```

Expected: matching SHA, native Git/ext4 path, no shared Windows environment, and clone-local `.venv`. Any mismatch blocks evidence.

- [ ] **Step 3: Run deterministic green and 200 standalone WSL selectors.**

```bash
uv run --frozen pytest tests/unit/mcp/test_client_sdk.py::test_operation_deadline_is_enforced -q
for run in $(seq 1 200); do
  uv run --frozen pytest tests/unit/mcp/test_client_sdk.py::test_operation_deadline_is_enforced -q || exit $?
done
uv run --frozen pytest tests/unit/mcp/test_client_sdk.py tests/unit/mcp/test_client_supervisor.py -q
uv run --frozen pytest tests/unit -q
uv run --frozen ruff check .
```

Expected: deterministic green first, then 200/200 standalone passes with no `SUBMIT_TIMEOUT`. Record every process result plus distro/kernel/filesystem, `/usr/bin/git`, Python/uv, and unrelated failures separately.

- [ ] **Step 4: Apply the independent exit decision.**

Close P11-FU-19 only if red/green, four entry points, Windows, native WSL 200-run, full gates, coverage, and Ruff pass. Cite only its P11-FU-19 reports.

If any production/evidence gate fails, leave P11-FU-19 open as named owner and record the failed gate/residual. P11-FU-7 remains closed. A broader supervisor redesign requires Plan 11.16 `_v2` or a new named pool entry.

- [ ] **Step 5: Commit closure only when eligible.**

```powershell
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
uv run --frozen pytest -q
uv run --frozen pytest --cov -q
uv run --frozen ruff check .
git diff --check
git add docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md reports/plan-11-16-p11-fu-19-windows-evidence.md reports/plan-11-16-p11-fu-19-wsl-evidence.md
git commit -m "docs: close P11-FU-19 deadline race"
```

If not eligible, commit only the report/pool residual retaining open custody; never write a closure commit.

---

### Task 5: Publish distinct release evidence and audit current-state documentation

**Files:**

- Create: `reports/plan-11-16-deadline-seams-release.md`
- Audit/update only if stale: `README.md`, roadmap, Plan 11 charter, and runbook
- Preserve: this plan and all frozen plan/spec bytes

**Interfaces:** Consumes distinct reports and pool status; produces reviewable truthfulness/current-state evidence.

- [ ] **Step 1: Audit every current-state reference.**

```powershell
rg -n "P11-FU-7|P11-FU-19|NDJSON|sys.settrace|SUBMIT_TIMEOUT|OPERATION_TIMEOUT|deadline seam|Plan 11.16" README.md docs/superpowers/plans docs/runbooks reports
```

Update only statements made stale by a proved closure/residual. Historical/frozen records stay untouched.

- [ ] **Step 2: Write the release claim-to-evidence table.**

| Claim | Required evidence |
|---|---|
| P11-FU-7 is test-side only | `server.py` no-diff, retained assertions, 25 Windows coverage logs |
| P11-FU-7 did not widen a clock | captured deterministic red and finite-EOF test diff |
| P11-FU-19 is production code | four `client_sdk.py` entries and controlled real-adapter starvation red/green |
| SDK expiry never exposes `SUBMIT_TIMEOUT` | open/discover/call/stream tests |
| Generic supervisor remains bounded | direct `submit(..., timeout_seconds=0.2)` test |
| P11-FU-19 is not load-dependent | 200 standalone WSL results and separately reported full-unit run |
| Entries close independently | separate pool detail/report links |

List every unrun live tier, unrelated failure, or still-open P11-FU-19 gate explicitly.

- [ ] **Step 3: Run final gates and prepare the implementation PR.**

```powershell
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
uv run --frozen pytest -q
uv run --frozen pytest --cov -q
uv run --frozen ruff check .
git diff --check
git status --short --branch
git diff --name-only origin/main...HEAD
git fetch origin main
git rev-list --left-right --count HEAD...origin/main
```

Expected: full gates green, coverage at least 80%, Ruff/diff hygiene clean, and only planned files changed. Deliberately merge main drift and rerun affected gates; never stage the checkpoint log.

- [ ] **Step 4: Commit only truthful documentation and open the PR.**

```powershell
git add reports/plan-11-16-deadline-seams-release.md README.md docs/superpowers/plans/2026-07-01-phase-1-roadmap.md docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md docs/runbooks/local-live-dependencies.md
git commit -m "docs: publish deadline-seam verification"
```

Stage an audited file only if it changed. The PR must state whether both rows closed or name the still-open owner.

## Claim-to-task traceability

| Required result | Task | Required evidence |
|---|---:|---|
| Separate named custody before mutation | 0 | pool red/green and two scheduled rows |
| P11-FU-7 has no test-owned wall clock | 1 | deterministic delay red, finite EOF diff, focused green |
| P11-FU-7 does not hide a regression | 1, 2 | unchanged `server.py`, retained assertions, 25 Windows coverage suites |
| P11-FU-19 has one public timeout result | 3 | controlled starvation and four entry-point tests |
| Generic liveness remains distinct | 3 | direct supervisor `SUBMIT_TIMEOUT` test |
| P11-FU-19 standalone characterization is meaningful | 4 | ext4 provenance and 200 results |
| Entries close independently or retain ownership | 2, 4, 5 | separate pool detail/report links |

## Explicit residuals and exclusions

| Residual or excluded change | Disposition and owner |
|---|---|
| ACP server production behavior, sanitization policy, port/teardown, launch-trust, and Gateway behavior | Out of Plan 11.16. P11-FU-7 is test-only; new production evidence needs a separately named entry. |
| Increasing the one-second NDJSON or 0.2/30-second SDK budgets | Forbidden. This plan removes a test clock and unifies public timeout semantics; it does not mask latency. |
| Generic supervisor API redesign or unbounded submission wait | Out of scope. Preserve direct `SUBMIT_TIMEOUT`; retain P11-FU-19 open and amend/allocate future custody if necessary. |
| Claiming loop starvation is load-only | Rejected. P11-FU-19 owns standalone WSL characterization and deterministic injected proof. |
| Independently authored real client-MCP tier | A fake cannot discharge it. Record a marker skip honestly; it is not a pass. |

## Definition of Done for implementation

- [ ] The two entries have separate scheduled custody, reports, and closure decisions.
- [ ] The P11-FU-7 red deterministically exercises the former one-second guard; final finite-EOF test keeps every response/stderr assertion and changes no ACP production source.
- [ ] Twenty-five Windows full `pytest --cov -q` processes pass and are retained as evidence.
- [ ] All four SDK entries use exactly `operation_timeout_seconds`, have no `+ 1.0`, and expose public `OPERATION_TIMEOUT` on expiry.
- [ ] The real-adapter loop-starvation test is a deterministic legacy red and green without changing the 0.2-second budget; it cleans up loop/thread resources.
- [ ] Direct generic supervisor callers retain bounded `SUBMIT_TIMEOUT`; shutdown/dead errors are not remapped, and no retry/replay/default change exists.
- [ ] Windows and native WSL ext4 evidence use the same implementation SHA; WSL includes 200 standalone selector processes.
- [ ] Full fitness, bare coverage at or above 80%, Ruff, diff hygiene, and freshness audit pass before a closure claim.
- [ ] A P11-FU-19 failure leaves its named row open while P11-FU-7 may close; neither lane's evidence is attributed to the other.
