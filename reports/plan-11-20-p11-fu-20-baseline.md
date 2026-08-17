# Plan 11.20 P11-FU-20 — Task 0 baseline

**Status:** Pre-change characterization completed on the implementation branch.
Implementation of the real catalog/authorizer attachment has not started. P11-FU-20 is
scheduled (Promoted to Plan 11.20), not Closed.

**Date:** 2026-08-18

## Checkout

| Ref | Value |
|---|---|
| Worktree | `D:\Projects\Development\Python\optimus-cost-agent-wt-cursor-11-20` |
| Branch | `agent/cursor/plan-11-20-client-mcp-one-call` |
| `HEAD` (committed base) | `f40aa301c465aa6af207d8bceb3064bf83e39c98` |
| `origin/main` | `f40aa301c465aa6af207d8bceb3064bf83e39c98` |
| Status | clean except untracked `.superpowers/` SDD ledger; hashes identical before Task 0 edits |

Reviewer checkpoint `docs/superpowers/reviews/plan-11-20-review-checkpoints.md` is absent
(expected: reviewer-owned, gitignored, not yet authored). No recorded ruling contradicted
the plan.

Kickoff overrode the plan's Step 1 worktree add: implementation uses the existing Cursor
worktree and `agent/cursor/plan-11-20-client-mcp-one-call` already cut from `origin/main`.
No second worktree was created.

## WP-2 ruling 5 — living-pool status token

The plan Task 0 brief says update status to `Scheduled — Plan 11.20`. That string is **not**
a valid pool `_status_token`. Pool "How to use this document" allows only
`Open`, `Promoted -> <markdown link>`, `Partially implemented`, `Closed`, and
`Reviewed disposition`.

Canonical living-pool promotion applied here:

`Promoted -> [Plan 11.20](2026-08-17-plan-11-20-p11-fu-20-client-mcp-one-call-approval.md)`

- Index Status cell = that exact token.
- Detail `**Status:**` line = that token, then `.`, then prose.

The hygiene RED parses both the Follow-up status index row and the P11-FU-20 detail
section. It requires the Promoted Plan 11.20 link (this is how "Scheduled plus Plan 11.20"
is expressed in this pool). It rejects:

- closure wording that cites only the frozen P11-FU-9 Task 6 fail-closed seam
- the fabricated token `Scheduled — Plan 11.20`

It failed while current status was `Open` (`assert 'Open' == 'Promoted -> [Plan 11.20](...)'`
on the P11-FU-20 index row). That proves the parser observed P11-FU-20 rather than an
unrelated row.

P11-FU-20 was not marked Closed. Frozen P11-FU-9 plan/spec bytes were not edited.
Production code was not changed. Only P11-FU-20 was scheduled.

## Platform provenance

| Item | Value |
|---|---|
| `sys.platform` | `win32` |
| `platform.platform()` | `Windows-11-10.0.26200-SP0` |
| Python | `3.14.4` (`MSC v.1944 64 bit (AMD64)`) |
| pytest | `9.1.1` |
| coverage | `7.14.3` |
| `uv` | `0.11.29` |
| Git | `git version 2.55.0.windows.3` |
| Filesystem | NTFS (Windows worktree) |

## Behavior anchors (captured, not guessed)

Commands:

```powershell
uv run --frozen pytest tests/unit/acp/test_spec_protocol.py::test_spec_mcp_broker_issue_fails_closed_until_catalog_authorizer_attached tests/unit/mcp/test_client_disposition.py -q
```

Result: **12 passed** in 0.76s (1 spec + 11 disposition).

| Anchor | Observed at `f40aa30` |
|---|---|
| `src/optimus/acp/spec.py` `AcpDuplexAdapter._mcp_permission_broker_for` | Returns `None` when `session.client_mcp_state is None`. When state exists, returns an `AcpMcpPermissionBroker` whose `issue_approval` closure discards the request and **returns `None`** (fail closed; comment names P11-FU-20). |
| `tests/unit/acp/test_spec_protocol.py::test_spec_mcp_broker_issue_fails_closed_until_catalog_authorizer_attached` | **PASSED.** Constructs a real `AcpDuplexAdapter`, sets `client_mcp_state`, and asserts `broker._issue_approval(request) is None`. |
| `src/optimus/mcp/client_disposition.py` `ClientMcpDisposition.disposition_for_new_session` | Transport-free: no `open`, `discover`, `call_tool`, or `tool_service.register` in the method body. It normalizes entries, may request allow-once permission, and records lease/unavailable state only. |
| `tests/unit/mcp/test_client_disposition.py` | **11 passed**, including `test_valid_entry_requests_safe_approval_without_opening_transport` and `test_absent_and_empty_entries_are_exact_noop` (`probe.open_calls == 0`). No transport opens during disposition. |

Existing fail-closed result: allow-path issuance returns `None` until a per-server catalog
authorizer is attached. That P11-FU-9 Task 6 seam is diagnosis, not P11-FU-20 closure.

## Task 0 red / green

Command:

```powershell
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
```

Red (before pool promotion): **1 failed, 49 passed.**
`test_plan_1120_p11_fu_20_scheduled_custody_rejects_p11_fu_9_task_6_closure`
`AssertionError: assert 'Open' == 'Promoted -> [Plan 11.20](2026-08-17-plan-11-20-p11-fu-20-client-mcp-one-call-approval.md)'`
on the P11-FU-20 index status.

After promoting only P11-FU-20 to Plan 11.20:

```powershell
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
```

Result: **50 passed** in 0.86s.

The row is not Closed. Original diagnosis (fail-closed `issue` → `None`, disposition
transport-free, real-adapter evidence required) remains in the detail body.
