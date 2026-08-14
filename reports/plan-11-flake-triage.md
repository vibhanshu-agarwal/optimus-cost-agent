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
