# Plan 11.17 — P11-FU-5 Windows Disposition

**Status:** Reproduced, context known; root cause unestablished. This report does not close
P11-FU-5.

## Evidence boundary

The operator-approved historical disposition is three Windows `WinError 6` / `DuplicateHandle`
occurrences on 2026-08-14/15 in these real Git-spawning pool-hygiene selectors:

- `test_immutable_documents_match_approved_head_blobs`
- `test_product_checkpoint_log_location_remains_gitignored`

`reports/plan-11-14-p11-fu-21-custody-relay-exit-code-evidence.md` names both selectors and one
`DuplicateHandle` incident. `reports/plan-11-15-durable-approval-identity-baseline.md` records the
same `subprocess.Popen` / `_make_inheritable` mechanism in four other Windows Git/DACL tests, but
those are corroborating mechanism records, not part of the operator-approved three. The Plan 11.15
FU-29 injected Git fault remains a different mechanism and receives no FU-5 credit.

The historical ten-run no-reproduction result is context, **not contrary evidence**. FU-5 has no
established recurrence rate, so no later clean count proves absence.

## Current Windows observations

Task 0's full documentation-hygiene validation reproduced the exact `subprocess._make_inheritable`
failure in both selectors; two further containing-file runs reproduced it once and twice,
respectively. The targeted two-selector comparison and a later full-file run were clean. The complete
outcome matrix and raw-log hashes are in
`reports/plan-11-17-windows-resource-lifecycle-baseline.md`. Clean comparisons are recorded only as
observations; they do not neutralize the failures.

## Subprocess lifecycle timeline

| Stage | Evidence | Finding |
| --- | --- | --- |
| Parent | The pytest process calls `_head_blob_sha256()` or the checkpoint-ignore test. | The parent is the Windows pytest process. |
| Child request | Both selectors invoke `subprocess.run(["git", ...], cwd=REPO_ROOT, capture_output=True)`. | The intended child is Git. |
| Captured-handle preparation | The traceback is `subprocess.run` → `Popen._get_handles` → `Popen._make_inheritable` → `_winapi.DuplicateHandle`. | `WinError 6` occurs while preparing an inheritable captured handle. |
| Child launch / completion | No child PID, exit status, or Git output appears for the failing call. | The record does not establish that Git launched or completed. |

The error is therefore observed during Windows `Popen` handle-inheritance setup, before a successful
child launch is evidenced. The underlying invalid-handle cause remains unknown; this report does not
attribute it to Git, Python, pytest, or a product component.

## Relation to P11-FU-6

No FU-5 failure record contains a Gateway socket, `ThreadingHTTPServer`, `serve_forever` thread, or
HTTP client operation. FU-5 remains a Git child-process handle operation. This is a different
observed resource path from FU-6, but the plan's overall shared-cause classification is
`insufficient_evidence` because no deterministic causal chain has been shown for either failure.

## Disposition and next observation

P11-FU-5 remains open under Plan 11.17 as **reproduced, context known**. No deterministic
subprocess-handle ownership edge has been identified, so no FU-5 fixture or product change is
permitted. A future investigation must capture a failing `Popen` attempt's child-launch boundary and
handle ownership without replacing either real Git assertion or suppressing `WinError 6`.
