# Plan 11.16 P11-FU-7 Windows coverage evidence

**Status:** Evidence gate **not met**. P11-FU-7 remains scheduled under Plan 11.16.
The Task 1 test-side clock removal is in `72f3cc8`. This report does **not** close the row.

**Date:** 2026-08-15

## Checkout

| Ref | Value |
|---|---|
| Worktree | `D:\Projects\Development\Python\optimus-cost-agent-wt-cursor` |
| Branch | `agent/cursor/plan-11-16-deadline-seams` |
| SHA | `72f3cc8e10fdc2f9f5e5d0e1c99219dfee962a61` |
| Status | `ahead 2` of `origin/main`; Task 0 + Task 1 only |

Reviewer checkpoint `docs/superpowers/reviews/plan-11-16-review-checkpoints.md` is absent.

## Platform provenance

| Item | Value |
|---|---|
| `sys.platform` | `win32` |
| `platform.platform()` | `Windows-11-10.0.26200-SP0` |
| Python | `3.14.4` (`MSC v.1944 64 bit (AMD64)`) |
| pytest | `9.1.1` |
| coverage | `7.14.3` |
| Git | `C:\Program Files\Git\cmd\git.exe` |
| Filesystem | NTFS |

## Task 1 red (deterministic)

Temporary cancellation-resistant 1.1s blocker in
`test_serve_ndjson_sanitizes_request_processing_response_and_stderr` produced
`asyncio.TimeoutError` from the test-owned `wait_for(..., timeout=1)`, not a
redaction assertion failure. A first injector that used a cancellable
`Event.wait()` returned before the clock (`IndexError` on `writer.messages[0]`)
and was repaired before source changes. The injector was then removed.

## Focused file

```powershell
uv run --frozen pytest tests/unit/acp/test_stdio_ndjson.py -q
```

**12 passed** in 0.74s. `git diff -- src/optimus/acp/server.py` empty.
Sanitization assertions retained. Bare `--cov` on this file alone is 17%
(project `fail-under=80`); that is focused-scope coverage, not the 25-run gate.

```powershell
uv run --frozen pytest tests/unit/acp/test_stdio_ndjson.py --cov -q
```

12 passed; coverage fail-under on the full production tree as expected for a
single-file run.

## 25 full Windows `--cov` processes

Command (stopped on first non-zero, no retry):

```powershell
1..25 | ForEach-Object {
    $run = $_
    uv run --frozen pytest --cov -q *> "reports/plan-11-16-p11-fu-7-windows-cov-run-$run.log"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

| Run | Exit | Duration | Notes |
|---|---:|---:|---|
| 1 | 0 | 149s | 3139 passed, 28 skipped, 110 deselected; coverage 81.63% |
| 2 | 0 | 101s | clean |
| 3 | 0 | 110s | clean |
| 4 | 0 | 101s | clean |
| 5 | 1 | 104s | **unrelated** `P11-FU-6` / WinError 10053 |
| 6–25 | unrun | — | stopped after first failure |

Run 5 failure:

`tests/unit/optimus_gateway/test_server.py::test_tools_routes_return_not_found_when_dependencies_are_not_configured`

`ConnectionAbortedError: [WinError 10053] An established connection was aborted by the software in your host machine`

3138 passed, 28 skipped, 110 deselected, coverage 81.63%. The P11-FU-7 target
`test_serve_ndjson_sanitizes_request_processing_response_and_stderr` did not fail.
This is the named `P11-FU-6` Gateway `_start_server` / `_stop_server` flake
(Plan 11.12 transferred WinError 10053). It is not an NDJSON sanitization or
ACP production failure.

**Result: 4/25 clean full coverage suites; 21 unrun.** Isolated or non-coverage
runs are not substituted. P11-FU-7 is not Closed.

## Clock disposition

The two target wrappers now `await configured.server.serve_ndjson(...)` with no
timeout. No longer clock was substituted.
