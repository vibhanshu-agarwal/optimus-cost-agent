# Plan 11.12 Coverage Evidence

Pre-removal and post-removal aggregate coverage for `P11-FEAT-GATEWAY-MCP` retirement.
Both runs use bare `--cov` so they inherit the same five configured source packages and
`fail_under = 80` from `pyproject.toml`. Raw JSON lives under `$env:TEMP` and is not committed.

Inherited coverage sources (`[tool.coverage.run] source`):

- `src/optimus`
- `src/optimus_gateway`
- `src/optimus_security`
- `src/evidence_handoff`
- `src/evidence_handoff_runtime`

## Pre-removal baseline

| Field | Value |
|---|---|
| Commit | `4b7f622499d3e4d197652943b85df3da7c6259a0` (`origin/main` at branch cut) |
| Command | `uv run --frozen pytest -q --cov --cov-report=term-missing "--cov-report=json:$baselineJson"` |
| `$baselineJson` | `C:\Users\pc\AppData\Local\Temp\optimus-plan-11-12-pre-removal-coverage.json` |
| `$baselineExit` | `0` |
| Tests | 3169 passed, 27 skipped, 117 deselected, 1 warning in 146.45s |
| Aggregate (`percent_covered`) | **81.4189711107678%** (display 81%) |
| Statements | 17097 covered / 20200 |
| Branches | 3984 covered / 5692 |
| `fail_under` | 80.0% reached. Total coverage: 81.42% |
| Platform | win32, python 3.14.4-final-0 |

Pre-existing sub-80 disposition: none. The tree was already above the 80% threshold before deletion.

## Post-removal

| Field | Value |
|---|---|
| Working tree | `agent/cursor/plan-11-12-gateway-mcp-removal` on `4b7f622499d3e4d197652943b85df3da7c6259a0` plus retirement edits (uncommitted at capture) |
| Command | `uv run --frozen pytest -q --cov --cov-report=term-missing "--cov-report=json:$postJson"` |
| `$postJson` | `C:\Users\pc\AppData\Local\Temp\optimus-plan-11-12-post-removal-coverage.json` |
| `$postExit` | `0` |
| Tests | 3052 passed, 27 skipped, 110 deselected, 1 warning in 106.51s |
| Aggregate (`percent_covered`) | **81.56004394489986%** (display 82% in the term table; fail_under summary 81.56%) |
| Statements | 15689 covered / 18530 |
| Branches | 3613 covered / 5136 |
| `fail_under` | 80.0% reached. Total coverage: 81.56% |
| Platform | win32, python 3.14.4-final-0 |

Post-removal aggregate is above 80%. Coverage rose slightly after deleting uncovered Gateway-MCP modules; no tests were added for retired Gateway behavior. Pre-existing sub-80 disposition: none.

## WSL2 alternate-platform gate

Literal plan commands from `/mnt/d/Projects/Development/Python/optimus-cost-agent-wt-cursor`:

```bash
uv sync --frozen --extra dev
uv run pytest -q
```

| Field | Value |
|---|---|
| Branch | `agent/cursor/plan-11-12-gateway-mcp-removal` |
| Interpreter | CPython 3.14.6 (WSL2) |
| Result | **2 failed**, 3065 passed, 12 skipped, 110 deselected, 1 warning in 107.82s |
| Failed tests | `test_immutable_documents_match_approved_head_blobs`; `test_product_checkpoint_log_location_remains_gitignored` |
| Owner | **`P11-FU-17`** — WSL2 native git cannot parse a Windows-git-created linked worktree's `.git` pointer (pool line 1044). Origin is the `gitdir: D:/Projects/...` pointer; WSL `/usr/bin/git` treats it as relative and fails closed. Test-infra environment gap, not a product defect. |
| Failure class | Hygiene tests that spawn `git show` / `git check-ignore` hit that pointer. Not a Gateway `test_server` teardown and not `P11-FU-6`. |
| `P11-FU-6` | Did **not** reproduce. No production retry or safety weakening was added. |
| Task 6 Step 3 | Closed honestly: the WSL2 command ran; the two failures are the known `P11-FU-17` worktree pointer, not an open Plan 11.12 gate. No clean-WSL2 claim. |

`uv sync` on WSL also replaced the shared Windows `.venv` with a Linux environment. That was restored on Windows with `uv sync --frozen --extra dev`. A follow-up WSL run used `UV_PROJECT_ENVIRONMENT=/tmp/optimus-plan-11-12-venv` so the Windows venv is not destroyed again. Exporting `GIT_DIR`/`GIT_WORK_TREE` leaked into tests that create temporary repos and is not a valid gate.
