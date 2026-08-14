# P11-FU-21 Custody Relay Exit-Code Transparency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore opaque custody-relay transparency when the child has already exited: preserve its exit code and record `child_exited`, while retaining fail-closed behavior for a genuine mid-stream broken pipe, interruption, or recorder failure.

**Architecture:** Keep the full-duplex forwarding and `relay-summary.json` v1 schema. Change only the live `BrokenPipeError` terminal path: inspect `proc.poll()` before cleanup; a known code is a benign post-exit pipe race, while `None` remains a relay failure. A deterministic test starts a real exit-7 child, waits for it, injects only the next child-stdin write error, then uses the unmodified relay threads, terminal dispatch, summary writer, and verifier.

**Tech Stack:** Python 3.14, `subprocess`, `threading`, `pytest`, `coverage.py`, `pytest-cov`, Ruff, native WSL2 ext4 Git/`uv`, and Markdown custody/evidence documents.

**Status:** Draft planning artifact. Implementation has not started. Plan 11.14 was verified unclaimed on `origin/main` `bfe32a3e8184634117e50737b9ba10f25ff6b8af`; Plan 11.13 remains reserved for the authoritative four-document reversal.

## Global Constraints

- Cut the implementation branch from then-current `origin/main`. Never implement from this plan branch, a stale worktree, or `optimus-cost-agent-wt-vibhanshu`.
- The contract is settled: the relay is opaque and transparent. Do not reinterpret child exit code `1` as a relay status channel.
- `BrokenPipeError` with non-`None` pre-cleanup `proc.poll()` returns that child code and records `child_exited`. `BrokenPipeError` with `proc.poll() is None` returns `1` and records `broken_pipe`.
- Preserve the `KeyboardInterrupt` / `REASON_INTERRUPTED` and recorder-failure / `REASON_RECORDER_FAILURE` paths exactly. They remain exit `1`.
- A known post-exit pipe closure is not a relay failure: it must have `reason_code is None` and emit no broken-pipe stderr. A genuine unknown-exit broken pipe retains `REASON_BROKEN_PIPE` and its stderr signal.
- Keep `SCHEMA_SUMMARY = "plan117-custody-relay-summary-v1"` and all field names. The preflight audit found no `relay-summary.json` model in `tools/plan117_custody_contract.py`; `verify_relay_capture()` remains the verifier for complete two-EOF captures and is not weakened for a partial broken-pipe capture.
- Never modify `reports/plan-11-7-server-custody-artifacts/amendments/origin-a-fixture-v2/pre-fix-relay/plan117_custody_relay.py` or any digest-pinned sibling artifact.
- Live code scope is `tools/plan117_custody_relay.py` plus `tests/unit/tools/test_plan117_custody_relay.py`. Post-green documentation scope is the pool and one new evidence report.
- Linux/CI-parity evidence runs from a native WSL ext4 clone using `/usr/bin/git` and its own `.venv`, with `UV_PROJECT_ENVIRONMENT` unset. A `/mnt/d` worktree or Windows `git.exe` PATH override is not parity evidence.
- Use bare `--cov` for the aggregate gate so it inherits the five configured source packages and `fail_under = 80` from `pyproject.toml`.

## File Map

### Modify

- `tools/plan117_custody_relay.py:1230-1254` — distinguish known post-exit pipe closure from unknown mid-stream pipe failure before cleanup.
- `tests/unit/tools/test_plan117_custody_relay.py:118-145, 234-249, 382-465` — add deterministic boundary-injection tests and retain the existing real-world race test unchanged.
- `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md:158, 1352-1394` — close `P11-FU-21` only after all evidence is green.

### Create during implementation, not in this plan PR

- `reports/plan-11-14-p11-fu-21-custody-relay-exit-code-evidence.md` — implementation SHA; native clone provenance; deterministic red/green; 200-run result; contract audit; full-suite, coverage, Ruff, and diff gates; sealed-file hash before/after.

### Read-only audit targets

- `tools/plan117_custody_contract.py` — no direct summary-schema consumer is expected to change.
- `tools/plan117_custody_relay.py:1313-1436` — verify that `verify_relay_capture()` remains a complete-capture verifier and needs no schema change.
- `tools/run_plan117_custody_feasibility.py:424-560` — `mutate_settings_insert_relay()` inserts the relay for Zed but does not consume a relay exit-code convention.
- `reports/plan-11-7-server-custody-artifacts/amendments/origin-a-fixture-v2/pre-fix-relay/plan117_custody_relay.py` — read/hash only.

---

### Task 0: Establish the implementation base and frozen boundary

**Files:**

- Read: `AGENTS.md`, `tools/plan117_custody_relay.py:1022-1052, 1156-1310`
- Read: `tests/unit/tools/test_plan117_custody_relay.py:118-145, 234-249, 382-465`
- Preserve: `reports/plan-11-7-server-custody-artifacts/amendments/origin-a-fixture-v2/pre-fix-relay/plan117_custody_relay.py`

**Interfaces:**

- Consumes: the merged Plan 11.14 plan and the settled transparency contract.
- Produces: a clean branch, a sealed-file checksum, and an exact mutation boundary.

- [ ] **Step 1: Cut the implementation branch from refreshed main.**

```powershell
git fetch origin main
git switch -c agent/cursor/plan-11-14-custody-relay-exit-code origin/main
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
```

Expected: clean status and identical hashes. If they differ, stop and recreate from current main.

- [ ] **Step 2: Freeze and inspect the boundary before editing.**

```powershell
git hash-object reports/plan-11-7-server-custody-artifacts/amendments/origin-a-fixture-v2/pre-fix-relay/plan117_custody_relay.py
git grep -n -E "return_code = 1 if reason_code|REASON_BROKEN_PIPE|terminal_disposition" -- tools/plan117_custody_relay.py tests/unit/tools/test_plan117_custody_relay.py
git grep -n -E "relay-summary|child_exit_code|terminal_disposition|reason_code" -- tools/plan117_custody_contract.py tools/plan117_custody_relay.py
```

Record the sealed-file SHA in the later evidence report. Expected: live relay/test own terminal handling; summary v1 fields are already present; no contract-model migration is needed.

- [ ] **Step 3: Characterize, but do not use, the existing race as the red gate.**

```powershell
uv run --frozen pytest tests/unit/tools/test_plan117_custody_relay.py::test_eof_either_direction_and_child_first_exit -q
```

Record the result as context only. A green result does not clear the known approximately-1% race, and no pre-fix loop/retry is authorized.

---

### Task 1: Add deterministic relay-path tests before production code

**Files:**

- Modify: `tests/unit/tools/test_plan117_custody_relay.py`
- Test: `tests/unit/tools/test_plan117_custody_relay.py::test_post_exit_broken_pipe_preserves_child_exit_and_summary`

**Interfaces:**

- Consumes: `_run_relay_inprocess` with `capture_root: Path`, `run_id: str`, `child_argv: Sequence[str]`, `stdin_bytes: bytes`, and optional `popen_factory: Callable[..., Any]`; the real `run_relay()`; and `subprocess.Popen`.
- Produces: a deterministic post-exit red test and a deterministic unknown-exit preservation test.

- [ ] **Step 1: Add a post-exit test that injects only the process-stdin boundary.**

Place this beside the existing `test_eof_either_direction_and_child_first_exit`; leave that existing test unchanged.

```python
def test_post_exit_broken_pipe_preserves_child_exit_and_summary(tmp_path: Path) -> None:
    class _InjectedBrokenPipeStdin:
        def __init__(self, wrapped: Any) -> None:
            self._wrapped = wrapped

        def write(self, _data: bytes) -> int:
            raise BrokenPipeError("injected-after-child-exit")

        def flush(self) -> None:
            raise AssertionError("flush must not follow a failed write")

        def close(self) -> None:
            self._wrapped.close()

    def exited_child_popen(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        proc = subprocess.Popen(*args, **kwargs)
        assert proc.wait(timeout=5) == 7
        assert proc.poll() == 7
        assert proc.stdin is not None
        proc.stdin = _InjectedBrokenPipeStdin(proc.stdin)  # type: ignore[assignment]
        return proc

    exit_code, _forwarded, err, run_dir = _run_relay_inprocess(
        capture_root=tmp_path,
        run_id="post-exit-broken-pipe",
        child_argv=_exit_first_child_args(code=7),
        stdin_bytes=b"write-after-child-exit",
        popen_factory=exited_child_popen,
    )
    summary = json.loads((run_dir / "relay-summary.json").read_text(encoding="utf-8"))
    assert exit_code == 7
    assert summary["child_exit_code"] == 7
    assert summary["terminal_disposition"] == "child_exited"
    assert summary["reason_code"] is None
    assert err == b""
```

This starts and reaps a real child and uses real reader/forwarder threads, error dispatch, and summary writing. It must not monkeypatch `_forward_parent_to_child`, `run_relay`, the error list, or `_write_summary`. Do not call `verify_relay_capture(run_dir)` here: a forwarding failure correctly omits parent-side EOF, and that verifier deliberately accepts only complete two-EOF captures.

- [ ] **Step 2: Add an explicit unknown-exit discriminator test.**

Use a test-local process double whose `stdin.write()` raises `BrokenPipeError`, whose `poll()` returns `None` before cleanup, and whose `terminate()` / `wait()` provide cleanup only. Invoke it through `_run_relay_inprocess` with non-empty input and assert:

```python
assert exit_code == 1
assert summary["terminal_disposition"] == "broken_pipe"
assert summary["reason_code"] == plan117_custody_relay.REASON_BROKEN_PIPE
assert b"relay_broken_pipe" in err
```

Do not make this test the red gate; it protects behavior that is already correct before the fix.

- [ ] **Step 3: Run the deterministic red gate before editing the relay.**

```powershell
uv run --frozen pytest tests/unit/tools/test_plan117_custody_relay.py::test_post_exit_broken_pipe_preserves_child_exit_and_summary -q
```

Expected: deterministic failure at `assert exit_code == 7`, observing `1`; the summary also reports `broken_pipe`. If this passes, stop because the injection does not exercise the intended live path or main already changed behavior.

- [ ] **Step 4: Verify the new test boundary is narrow.**

```powershell
uv run --frozen pytest tests/unit/tools/test_plan117_custody_relay.py -q -k "post_exit_broken_pipe or broken_pipe_is_nonzero"
```

Expected before source edit: post-exit test red, existing unknown-pipe behavior green. Do not weaken `test_broken_pipe_is_nonzero_no_fallback`.

---

### Task 2: Implement the pre-cleanup exit discriminator

**Files:**

- Modify: `tools/plan117_custody_relay.py:1230-1254`
- Test: both new Task 1 tests and unchanged `test_eof_either_direction_and_child_first_exit`

**Interfaces:**

- Consumes: `errors[0]`, `proc.poll() -> int | None`, `REASON_BROKEN_PIPE`, `_close_child_pipes(proc)`, `_terminate_owned_child(proc)`.
- Produces: transparent known-exit `(return_code, child_exit_code, terminal_disposition)` and fail-closed unknown-exit behavior without a schema change.

- [ ] **Step 1: Make the only live behavior change in the `BrokenPipeError` branch.**

Use this branch structure. Keep the `KeyboardInterrupt`, `RelayRecorderError`, and generic-error branches textually and semantically unchanged.

```python
elif isinstance(first, BrokenPipeError):
    child_exit = proc.poll()
    stop.set()
    _close_child_pipes(proc)
    if child_exit is not None:
        terminal_disposition = "child_exited"
        reason_code = None
        return_code = int(child_exit)
    else:
        terminal_disposition = "broken_pipe"
        reason_code = REASON_BROKEN_PIPE
        _terminate_owned_child(proc)
        _emit_stderr(err_out, reason_code)
        return_code = 1
```

Do not synthesize a post-cleanup child exit for the unknown case: retain pre-cleanup `child_exit = None` in `relay-summary.json` rather than recording the relay's later termination status as the child's normal exit.

- [ ] **Step 2: Run deterministic green and real-world race checks.**

```powershell
uv run --frozen pytest tests/unit/tools/test_plan117_custody_relay.py::test_post_exit_broken_pipe_preserves_child_exit_and_summary tests/unit/tools/test_plan117_custody_relay.py::test_eof_either_direction_and_child_first_exit -q
```

Expected: both pass; the new test proves `7`, `child_exit_code == 7`, and `child_exited` together.

- [ ] **Step 3: Prove fail-closed branches remain fail-closed.**

```powershell
uv run --frozen pytest tests/unit/tools/test_plan117_custody_relay.py -q -k "post_exit_broken_pipe or broken_pipe_is_nonzero or recorder_failure_terminates_owned_child_no_fallback or ctrl_c_termination_emits_summary"
```

Expected: known post-exit is transparent; unknown pipe, recorder failure, and interruption remain nonzero with their existing reason/disposition semantics.

- [ ] **Step 4: Commit the TDD-sized source/test change and make it available to the native clone.**

```powershell
git add tools/plan117_custody_relay.py tests/unit/tools/test_plan117_custody_relay.py
git commit -m "fix: preserve exited child code through custody relay"
git push -u origin agent/cursor/plan-11-14-custody-relay-exit-code
```

Never stage a file under `reports/plan-11-7-server-custody-artifacts/amendments/origin-a-fixture-v2/pre-fix-relay/`.

---

### Task 3: Confirm summary compatibility and run focused regressions

**Files:**

- Read-only: `tools/plan117_custody_contract.py`, `tools/run_plan117_custody_feasibility.py:424-497`
- Test: `tests/unit/tools/test_plan117_custody_relay.py`, `tests/unit/tools/test_plan117_custody_contract.py`, `tests/unit/tools/test_run_plan117_custody_feasibility.py`

**Interfaces:**

- Consumes: unchanged `plan117-custody-relay-summary-v1` fields (`child_exit_code`, `terminal_disposition`, `reason_code`).
- Produces: a documented no-migration decision backed by the existing complete-capture verifier audit and focused regression tests.

- [ ] **Step 1: Audit summary and Zed-settings consumers at the implementation SHA.**

```powershell
git grep -n -E "relay-summary|child_exit_code|terminal_disposition|reason_code" -- tools/plan117_custody_contract.py tools/plan117_custody_relay.py tests/unit/tools
git grep -n -C 8 "def mutate_settings_insert_relay" -- tools/run_plan117_custody_feasibility.py
```

Expected: v1 schema remains, the relay verifier accepts required fields, and settings insertion does not map a relay failure exit code. Do not change the contract module or schema because existing fields now hold truthful values.

- [ ] **Step 2: Run relay and custody-contract regressions.**

```powershell
uv run --frozen pytest tests/unit/tools/test_plan117_custody_relay.py tests/unit/tools/test_plan117_custody_contract.py tests/unit/tools/test_run_plan117_custody_feasibility.py -q
```

Expected: all pass. Record that no summary schema consumer changes: the v1 field set already separates child exit, terminal disposition, and reason code. The complete-capture verifier's existing two-EOF rule remains unchanged and is not an acceptance criterion for the injected partial-capture test.

---

### Task 4: Collect native-WSL evidence and close P11-FU-21

**Files:**

- Create: `reports/plan-11-14-p11-fu-21-custody-relay-exit-code-evidence.md`
- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`
- Preserve: sealed `pre-fix-relay/plan117_custody_relay.py`

**Interfaces:**

- Consumes: pushed implementation SHA, native ext4 clone, unchanged real-world race test, and all focused green evidence.
- Produces: 200/200 native evidence, named closure custody, and a reviewable implementation PR boundary.

- [ ] **Step 1: Check out the exact implementation SHA in the native ext4 clone.**

```bash
cd ~/src/optimus-cost-agent
git fetch origin agent/cursor/plan-11-14-custody-relay-exit-code
git switch --detach origin/agent/cursor/plan-11-14-custody-relay-exit-code
test "$(command -v git)" = /usr/bin/git
git rev-parse HEAD
git rev-parse origin/agent/cursor/plan-11-14-custody-relay-exit-code
printenv UV_PROJECT_ENVIRONMENT && exit 1 || true
uv sync --frozen --extra dev
test -x .venv/bin/python
```

Expected: native ext4 clone, `/usr/bin/git`, identical branch/revision hashes, unset environment override, and clone-local `.venv`. A mounted path or Windows Git blocks the evidence run.

- [ ] **Step 2: Re-run the unchanged original race test 200 times.**

```bash
cd ~/src/optimus-cost-agent
log_root=/tmp/p11-fu21-plan-11-14-loop
mkdir -p "$log_root"
passes=0
failures=0
started=$(date +%s)
for iteration in $(seq 1 200); do
  if .venv/bin/python -m pytest tests/unit/tools/test_plan117_custody_relay.py::test_eof_either_direction_and_child_first_exit -q >"$log_root/$iteration.log" 2>&1; then
    passes=$((passes + 1))
  else
    failures=$((failures + 1))
    tail -n 80 "$log_root/$iteration.log"
  fi
done
ended=$(date +%s)
printf 'iterations=200 passes=%s failures=%s wall_seconds=%s\n' "$passes" "$failures" "$((ended - started))"
test "$failures" -eq 0
```

Expected: exactly 200 iterations, zero failures, and exit 0. Any failure blocks closure; retain the `/tmp` log and investigate without adding retries or skips.

- [ ] **Step 3: Run native full-suite and aggregate coverage gates.**

```bash
cd ~/src/optimus-cost-agent
uv run --frozen pytest -q
uv run --frozen pytest --cov -q
```

Expected: full suite green and aggregate coverage at least 80%. Record counts, percentage, wall-clock, implementation SHA, clone path/filesystem, and `/usr/bin/git` provenance in the evidence report.

- [ ] **Step 4: Write evidence, then close the pool only if every gate is green.**

The report must include: deterministic red/green outcome; focused contract suite; 200/200 loop; full/coverage output; native environment provenance; schema/consumer no-migration audit; Ruff/diff output from Task 5; and sealed-file SHA before/after equality. Then update the P11-FU-21 table to `Closed`, name Plan 11.14 and this report, and update its detail with the known-exit and unknown-exit outcomes. Preserve the historical PR #128 and Batch B narrative.

---

### Task 5: Run final integrity gates and publish the implementation PR

**Files:**

- Modify: pool and named evidence report only after green evidence
- Preserve: all sealed historical artifacts

**Interfaces:**

- Consumes: Task 0-4 evidence.
- Produces: a clean implementation PR whose changed files exclude sealed custody evidence.

- [ ] **Step 1: Run documentation, lint, and frozen-boundary gates.**

```powershell
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
uv run --frozen ruff check .
git diff --check
git diff --exit-code origin/main...HEAD -- reports/plan-11-7-server-custody-artifacts/amendments/origin-a-fixture-v2/pre-fix-relay/plan117_custody_relay.py
git diff --name-only origin/main...HEAD
```

Expected: pool hygiene and Ruff pass, no whitespace errors, sealed-file diff exits 0, and only the live relay, relay unit test, pool, and named evidence report changed.

- [ ] **Step 2: Commit documentation closure separately from the source fix.**

```powershell
git add docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md reports/plan-11-14-p11-fu-21-custody-relay-exit-code-evidence.md
git commit -m "docs: close FU-21 custody relay exit-code defect"
git push
```

- [ ] **Step 3: Open the implementation PR with the exact evidence statement.**

```powershell
gh pr create --base main --head agent/cursor/plan-11-14-custody-relay-exit-code --title "fix: preserve exited child code through custody relay" --body "P11-FU-21: deterministic post-exit BrokenPipe regression is green; unchanged native WSL race test is 200/200; full suite, bare --cov >=80, Ruff, pool hygiene, and sealed-artifact diff checks are recorded in reports/plan-11-14-p11-fu-21-custody-relay-exit-code-evidence.md."
```

Do not publish the PR as ready if any Task 4 or Task 5 command is nonzero.

## Definition of Done

- The deterministic test starts and reaps a real exit-7 child, injects only its stdin write failure, and fails before the live relay edit.
- After the edit it proves together: process exit `7`, `summary["child_exit_code"] == 7`, and `summary["terminal_disposition"] == "child_exited"`.
- A `proc.poll() is None` broken pipe remains exit `1`, `broken_pipe`, and `REASON_BROKEN_PIPE`; interruption and recorder failure remain unchanged.
- The existing `test_eof_either_direction_and_child_first_exit` is unchanged and reaches 200/200 in the native WSL ext4 clone.
- Summary schema remains v1; `verify_relay_capture()` retains its complete two-EOF invariant; no contract or Zed settings consumer change is needed after audit.
- Native full suite, bare aggregate `--cov` >=80, Ruff, pool hygiene, and `git diff --check` pass.
- The sealed pre-fix relay artifact is byte-for-byte unchanged and the pool closes P11-FU-21 with Plan 11.14 and the named evidence report.

## Plan Self-Review

| Requirement | Plan coverage |
|---|---|
| Settled transparency contract and false custody record | Global constraints; Tasks 1-2 |
| Known-exit versus unknown-pipe discriminator | Tasks 1-2 |
| Deterministic real-path red test | Task 1 Steps 1 and 3 |
| Unchanged race test plus 200-run native proof | Tasks 1 and 4 |
| Summary schema and consumer audit | Task 3 |
| Pool closure, evidence, standard gates, frozen artifact | Tasks 4-5 |

No task changes a sealed artifact, widens timing, adds retries/skips, changes interruption or recorder-failure semantics, or treats a mounted Windows worktree as Linux-parity evidence.

## Execution Handoff

This PR is plan-only. After review and merge, create the implementation branch from current `origin/main`, run Tasks 0-5 in order, and do not mark a checkbox complete until its stated command has passed and the result is recorded. This planning PR authorizes no implementation or pool closure by itself.
