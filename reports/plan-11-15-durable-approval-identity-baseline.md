# Plan 11.15 durable-approval identity — Task 0 baseline

**Status:** Pre-change characterization completed on a clean implementation branch.
Implementation has not started.

**Date:** 2026-08-15

## Checkout

| Ref | Value |
|---|---|
| Worktree | `D:\Projects\Development\Python\optimus-cost-agent-wt-cursor-plan-11-15-durable-approval-identity` |
| Branch | `agent/cursor/plan-11-15-durable-approval-identity` |
| `HEAD` | `ced5d10c1f671ff2ea13c1062058b2ae51ea76d4` |
| `origin/main` | `ced5d10c1f671ff2ea13c1062058b2ae51ea76d4` |
| Status | clean; hashes identical |

Reviewer checkpoint `docs/superpowers/reviews/plan-11-15-review-checkpoints.md` is absent
(expected: reviewer-owned, gitignored, not yet authored). No recorded ruling contradicted
the plan.

## Frozen spec bytes

| Method | Digest |
|---|---|
| Frozen contract SHA-256 | `B445693AFB9B110E61D860F1B63D8836FF0EA651E0AC327BABA1CC906C84543B` |
| `Get-FileHash -Algorithm SHA256` | `B445693AFB9B110E61D860F1B63D8836FF0EA651E0AC327BABA1CC906C84543B` |
| `git hash-object` (SHA-1 blob) | `292041621ded61313cbdcc41686d98a719d3a413` |
| In-memory `git show origin/main:<spec>` SHA-256 | `B445693AFB9B110E61D860F1B63D8836FF0EA651E0AC327BABA1CC906C84543B` |

The working-tree file matches the frozen SHA-256. The spec was not edited.

## Platform provenance

| Item | Value |
|---|---|
| `sys.platform` | `win32` |
| `platform.platform()` | `Windows-11-10.0.26200-SP0` |
| Python | `3.14.4` (`MSC v.1944 64 bit (AMD64)`) |
| `uv` | `0.11.29` |
| Git | `2.55.0.windows.3` (`C:\Program Files\Git\cmd\git.exe`) |
| Filesystem | NTFS (Windows worktree) |

## Pre-change focused suite

Command:

```powershell
uv run --frozen pytest tests/unit/acp/test_trusted_paths.py tests/unit/acp/test_launch_approvals.py tests/unit/acp/test_launch_gate.py tests/unit/acp/test_main_wiring.py tests/unit/acp/test_launch_approval_cli.py tests/unit/acp/test_launch_audit.py tests/integration/acp/test_launch_trust_flow.py -q
```

Result: **235 passed, 18 skipped, 4 failed** in 6.03s.

### Baseline failures — recorded as `P11-FU-5`, not Plan 11.15

All four failures are `subprocess.Popen` `DuplicateHandle` during pipe setup
(`_make_inheritable`), not identity-digest or DACL-logic assertions:

| Test | First-run error | Isolated re-run |
|---|---|---|
| `tests/unit/acp/test_trusted_paths.py::TestWorkspaceIdentity::test_identity_includes_git_root_when_present` | `OSError: [WinError 6] The handle is invalid` at `git init` | same `WinError 6` |
| `tests/unit/acp/test_launch_gate.py::TestRealWindowsDaclEnumeration::test_everyone_granted_file_is_rejected` | `OSError: [WinError 50] The request is not supported` at `icacls` | `WinError 6` |
| `tests/unit/acp/test_launch_gate.py::TestRealWindowsDaclEnumeration::test_users_group_granted_file_is_rejected` | `WinError 50` at `icacls` | `WinError 6` |
| `tests/unit/acp/test_launch_gate.py::TestRealWindowsDaclEnumeration::test_explicit_current_user_grant_is_accepted` | `WinError 50` at `icacls` | `WinError 6` |

`P11-FU-5` already names Windows subprocess handle-duplication (`WinError 6/50`).
This is not `P11-FU-17` (WSL native-git Windows worktree pointer) and is not a
Plan 11.15 identity defect. The failures were not skipped, patched, or rerouted.

Outside pytest, `git init` in `%TEMP%\plan-11-15-git-init-probe` succeeded
(exit 0). The flake is the pytest/subprocess handle path, not Git itself.

These four tests are therefore **not inherited as Plan 11.15 blockers**. They remain
open under `P11-FU-5`. Plan 11.15 work continues; later evidence must not treat a
clean rerun of this flake as `P11-FU-29` proof.

## Mutation boundary

At the time of this baseline:

- No production source, tests, or pool rows had been edited.
- Identity still binds `st_ctime_ns` and collapses Git probe failure to `None`
  (`src/optimus/acp/trusted_paths.py`).
- Pool still lists 13 frozen artifacts; `P11-FU-18` and `P11-FU-29` remain `Open`.
