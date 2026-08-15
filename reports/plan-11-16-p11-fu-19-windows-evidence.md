# Plan 11.16 P11-FU-19 Windows evidence

**Status:** Windows unit/supervisor starvation green and one full `--cov` suite recorded
at implementation SHA `6159200`. Native WSL 200-run evidence is in the sibling WSL report.

**Date:** 2026-08-15

## Checkout

| Ref | Value |
|---|---|
| Worktree | `D:\Projects\Development\Python\optimus-cost-agent-wt-cursor` |
| Branch | `agent/cursor/plan-11-16-deadline-seams` |
| SHA | `6159200137b76198307591f7496ed83046af45ab` |
| Git | `C:\Program Files\Git\cmd\git.exe` |

## Platform

| Item | Value |
|---|---|
| `sys.platform` | `win32` |
| `platform.platform()` | `Windows-11-10.0.26200-SP0` |
| Python | `3.14.4` (`MSC v.1944 64 bit (AMD64)`) |
| Filesystem | NTFS |

## Deterministic starvation (real adapter)

```powershell
uv run --frozen pytest tests/unit/mcp/test_client_sdk.py tests/unit/mcp/test_client_supervisor.py -q
```

**28 passed** in 2.18s. `test_operation_deadline_is_enforced` uses real
`ClientMcpSdkAdapter.open()` against a started `MCPAsyncSupervisor` with
`call_soon_threadsafe` loop starvation. No mocked adapter/supervisor.

```powershell
uv run --frozen pytest tests/unit/mcp/test_client_sdk.py tests/unit/mcp/test_client_supervisor.py --cov -q
```

28 passed; project-wide coverage 13.37% (`fail-under` on focused files only).
`client_sdk.py` 87%, `client_supervisor.py` 90%.

## Full Windows coverage suite

```powershell
uv run --frozen pytest --cov -q
```

**3142 passed, 28 skipped, 110 deselected**, coverage **81.66%**, 115.35s.
Skips are marker skips (unrun, not passes), including
`tests/integration/mcp/test_client_sdk_real.py` (`requires_mcp_http`, 2 deselected
in the focused integration command).

No `SUBMIT_TIMEOUT` from SDK entries. Direct generic supervisor expiry remains
`SUBMIT_TIMEOUT` in `test_submit_times_out_and_cancels_slow_coroutine`.
