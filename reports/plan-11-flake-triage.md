# Plan 11 flake-cluster triage — corrected Batch A

**Base invariant:**

```bash
git fetch origin main && git switch -c <branch> origin/main && git rev-parse HEAD && git rev-parse origin/main
```

The two hashes must match before any read or write. This report used dedicated worktree
`agent/codex/p11-flake-triage-main` at `9af7e44c5ceaf5b259b3ab9a29470b2033b52cbe`, matching
`origin/main`. No human-review worktree was used.

## Corrected findings

| Item | Classification | Evidence | Disposition |
|---|---|---|---|
| `P11-FU-17` | **MISFILED** — deterministic environment incompatibility, not a flake | WSL2 `/usr/bin/git rev-parse --show-toplevel` in a Windows-created worktree: 3/3 `exit 128`. The Git-pointer mechanism is unaffected by base freshness. | Close as a flake after recording a native WSL clone/worktree operating decision. |
| `P11-FU-18` | **MISFILED** as test infrastructure; **security design concern** | The source and test are unchanged from the stale review worktree. The accepted 100-run 0-hit bound still applies, while the existing reproduced coalescing condition can leave a durable workspace identity unchanged after an in-place directory change. | Refile as a workspace-identity fail-open; needs a written security design. |
| `P11-FU-19` | **NEEDS-PLAN** | WSL2 standalone selector: 100 runs, 2 `SUBMIT_TIMEOUT` failures (2%). One current-main full `tests/unit` run passed FU-19; the only failures were the two known P11-FU-17 Git-pointer tests. | Plan a controlled supervisor readiness/deadline seam. Do not widen the 0.2s budget. |

## Current lock check

On the verified `origin/main` base, both commands passed using an isolated environment:

```text
UV_PROJECT_ENVIRONMENT=/tmp/p11-fu19-main-venv uv lock --check
UV_PROJECT_ENVIRONMENT=/tmp/p11-fu19-main-venv uv sync --frozen --extra dev
```

The earlier unparsable-lock claim was a stale-worktree artifact and must not become backlog work.

## FU-19 commands and observations

```text
/tmp/p11-fu19-main-venv/bin/python -m pytest \
  tests/unit/mcp/test_client_sdk.py::test_operation_deadline_is_enforced -q
# WSL2 looped 100 times: 98 passed, 2 failed.

/tmp/p11-fu19-main-venv/bin/python -m pytest tests/unit -q
# 2971 passed, 11 skipped; FU-19 passed.
# 2 expected P11-FU-17 Git-pointer failures remained.
```

Both focused failures came from `MCPAsyncSupervisor.submit()`'s outer
`future.result(timeout=1.2)`, before `ClientMcpSdkAdapter`'s inner
`asyncio.wait_for(..., timeout=0.2)` produced its expected operation-timeout error. This is a
test/supervisor timing boundary, not evidence to relax the production operation deadline.

No implementation, retries-as-fixes, skips, commits, or pull requests were made.

## Batch B (2026-08-14)

**Base invariant:** Dedicated worktree branch `agent/codex/p11-flake-triage-batch-b` was cut from
`origin/main`; `HEAD` and `origin/main` both resolved to
`da2fc781ca803bd484577910d44166c8a921e589` before investigation. The Batch A report and its pool
entries were present on that base. No human-review worktree was used.

| Item | Classification | Evidence | Disposition |
|---|---|---|---|
| `P11-FU-7` | **REPRODUCED** test-infrastructure flake | Windows `pytest --cov -q`: 1/5 target failures (20%); the other four runs passed. | Needs a controlled test timing/readiness seam; do not widen either one-second deadline or reclassify as ACP production behavior. |
| `P11-FU-6` | **REPRODUCED** test-infrastructure flake | Windows `pytest tests/unit -q`: current successor route node failed 1/20 (5%) with `WinError 10053`; the stale named predecessor does not exist and had 0/20 hits. | Needs a written Gateway harness plan. Keep the production route assertions and do not add retries or safety weakening. |
| `P11.7-FU-2` | **MISFILED** duplicate | No independent test node or mechanism; its generic Gateway threaded-test description matches the FU-6 recurrence. | Closed into `P11-FU-6`; no second plan. |
| `P11-FU-21` | **MISFILED** product bug | Focused WSL2 loop: 2 failures / 200 (1%), exact `7` -> `1`. The relay converts a normal post-exit `BrokenPipeError` into `REASON_BROKEN_PIPE` and unconditionally returns 1. | Needs a custody-relay product behavior plan; retain EOF and exit-code assertions. |
| `P11-FU-5` | **MISFILED** combined custody | The historical ten-run no-reproduction result applies to the rare Windows handle flake. Its fault-injectable Git-probe/digest behavior is independently actionable. | Keep the flake under FU-5 and split the identity concern to `P11-FU-29`. |

### Commands and observations

```text
# Windows, five independent full-suite coverage processes
.\\.venv\\Scripts\\python.exe -m pytest --cov -q
# Four passed; one failed test_serve_ndjson_sanitizes_request_processing_response_and_stderr.

# Windows, twenty independent full unit-suite processes
.\\.venv\\Scripts\\python.exe -m pytest tests/unit -q
# 18 clean suites; two failures. The relevant failure was:
# test_tools_routes_return_not_found_when_dependencies_are_not_configured
# ConnectionAbortedError: [WinError 10053] at HTTPConnection.getresponse().

# WSL2, isolated environment (never the shared Windows .venv)
UV_PROJECT_ENVIRONMENT=/tmp/p11-fu21-batch-b-venv \\
  /tmp/p11-fu21-batch-b-venv/bin/python -m pytest \\
  tests/unit/tools/test_plan117_custody_relay.py::test_eof_either_direction_and_child_first_exit -q
# 200 iterations: 198 passed, 2 failed with exit_code == 1 rather than 7.
```

FU-7 remains coverage-specific; Batch A's FU-19 result means full-suite load is not a necessary
general explanation and must not be added as one. FU-6's current failing node is a renamed or
superseding version of the historical selector, not evidence that the port/teardown signal vanished.

`P11-FU-29` and `P11-FU-18` are siblings in a future durable-approval identity design, not one
merged issue: a transient Git probe yields a false change and spurious reauthorization, whereas
ctime coalescing can yield a missed change and fail-open revalidation.

No production code, test timing, retry, skip, or behavior was changed by Batch B.
