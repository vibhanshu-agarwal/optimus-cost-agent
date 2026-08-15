# Plan 11.16 deadline seams — Task 0 baseline

**Status:** Pre-change characterization completed on a clean implementation branch.
Implementation of P11-FU-7 / P11-FU-19 remedies has not started.

**Date:** 2026-08-15

## Checkout

| Ref | Value |
|---|---|
| Worktree | `D:\Projects\Development\Python\optimus-cost-agent-wt-cursor` |
| Branch | `agent/cursor/plan-11-16-deadline-seams` |
| `HEAD` | `f29b59301762af2da60ed4ac74b91ec7699ba1be` |
| `origin/main` | `f29b59301762af2da60ed4ac74b91ec7699ba1be` |
| Status | clean; hashes identical before Task 0 edits |

Reviewer checkpoint `docs/superpowers/reviews/plan-11-16-review-checkpoints.md` is absent
(expected: reviewer-owned, gitignored, not yet authored). No recorded ruling contradicted
the plan.

Kickoff overrode the plan's Codex worktree/branch names: implementation uses the existing
Cursor worktree and `agent/cursor/plan-11-16-deadline-seams` cut from `origin/main`.

Pool status uses the canonical token `Promoted -> [Plan 11.16](...)` (pool "How to use"
promotion rule). Literal `Scheduled` is not a `_status_token` form; scheduled custody is
the Promoted token plus Plan 11.16 in both index and detail rows.

## Platform provenance

| Item | Value |
|---|---|
| `sys.platform` | `win32` |
| `platform.platform()` | `Windows-11-10.0.26200-SP0` |
| Python | `3.14.4` (`MSC v.1944 64 bit (AMD64)`) |
| pytest | `9.1.1` |
| coverage | `7.14.3` |
| `uv` | `0.11.29` |
| Git | `C:\Program Files\Git\cmd\git.exe` |
| Filesystem | NTFS (Windows worktree) |

## Frozen pre-change timeout values

| Bound | Location | Value | Plan 11.16 disposition |
|---|---|---|---|
| NDJSON test wall clock | `tests/unit/acp/test_stdio_ndjson.py` `asyncio.wait_for(..., timeout=1)` | `1.0` | P11-FU-7 removes this clock; does not widen it |
| SDK test budget | `test_operation_deadline_is_enforced` `operation_timeout_seconds=` | `0.2` | Unchanged |
| SDK host margin | `ClientMcpSdkAdapter` `timeout_seconds=self._operation_timeout_seconds + 1.0` | `+ 1.0` | P11-FU-19 removes the margin; public timeout stays `operation_timeout_seconds` |
| Production default | `ClientMcpSdkAdapter.__init__` `operation_timeout_seconds` | `30.0` | Unchanged |

## Task 0 red / green

Command:

```powershell
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py::test_plan_1116_deadline_seams_keep_separate_scheduled_custody -q
```

Red (before pool promotion): **FAIL** `AssertionError: Open` on P11-FU-7 index status.

After promoting only P11-FU-7 and P11-FU-19 to Plan 11.16:

```powershell
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
```

Result: **46 passed**.

Neither row is Closed. Evidence columns do not cross-credit the other lane. P11-FU-7 may
close independently if P11-FU-19 fails a production or evidence gate.
