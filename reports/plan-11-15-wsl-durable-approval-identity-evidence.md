# Plan 11.15 native WSL ext4 durable-approval identity evidence

Implementation SHA: `12b881a28b4a736a0d18ccdf1c02c49b94167e41`
Branch: `origin/agent/cursor/plan-11-15-durable-approval-identity`
Date (UTC): 2026-08-15

Linux-parity evidence from a native ext4 clone. Not `/mnt/d`. Not Windows Git.
Not a shared Windows `.venv`.

## Checkout and platform provenance

| Field | Observed value |
|---|---|
| Native clone | `/root/src/optimus-cost-agent` |
| `pwd -P` | `/root/src/optimus-cost-agent` (rejected if `/mnt/*`) |
| Filesystem | `/` on `/dev/sdf`, **ext4** (`df -T`); GNU `stat -f -c '%T'` reports `ext2/ext3` for the same ext4 volume |
| Kernel | `Linux DESKTOP-PL17VTM 6.18.35.2-microsoft-standard-WSL2` |
| Git executable / version | `/usr/bin/git`, `git version 2.43.0` |
| `HEAD` | `12b881a28b4a736a0d18ccdf1c02c49b94167e41` |
| `origin/agent/cursor/plan-11-15-durable-approval-identity` | `12b881a28b4a736a0d18ccdf1c02c49b94167e41` |
| `UV_PROJECT_ENVIRONMENT` | Unset |
| `uv` | `0.11.31` (`/root/.local/bin/uv`) |
| Interpreter | CPython 3.14.6 via clone-local `.venv/bin/python` (`Clang 22.1.3`, glibc 2.39) |

Frozen spec SHA-256: `B445693AFB9B110E61D860F1B63D8836FF0EA651E0AC327BABA1CC906C84543B`
(`git hash-object` `292041621ded61313cbdcc41686d98a719d3a413`). Matches Windows Task 7.

## Focused POSIX / security matrix

Command:

```bash
uv run --frozen pytest tests/unit/acp/test_trusted_paths.py tests/unit/acp/test_launch_approvals.py tests/unit/acp/test_launch_gate.py tests/unit/acp/test_main_wiring.py tests/unit/acp/test_launch_approval_cli.py tests/unit/acp/test_launch_audit.py tests/integration/acp/test_launch_trust_flow.py -q -rs
```

Result: **332 passed, 10 skipped in 4.12s**.

All ten skips are Windows-only guards (case-insensitive identity, Known Folder APIs,
DACL enumeration, case-insensitive Git-redirect stripping, ordinal case-insensitive
exclusions). They do not discharge a cross-platform claim.

Named POSIX/FU-18/migration subset: **29 passed, 1 skipped, 198 deselected in 0.44s**.
The one skip is `test_exclusion_policy_windows_ordinal_case_insensitive`.

### Named POSIX claims

| Claim | Evidence |
|---|---|
| Byte-sensitive exclusions | `test_exclusion_policy_posix_byte_sensitive` ran |
| FU-18 equal-ctime add | `test_fu18_equal_ctime_non_excluded_add_is_root_topology_mismatch` ran unguarded |
| Legacy ctime characterization | `test_revalidation_fails_after_workspace_directory_metadata_change` ran (POSIX); comment points at the unguarded FU-18 proof |
| Symlink retarget | `test_revalidation_fails_for_symlink_target_change` ran |
| Git worktree marker | `test_git_context_present_worktree_git_file` ran |
| EINTR / EAGAIN / ETIMEDOUT | parametrized Git-retry ids in `test_trusted_paths.py` ran as part of the focused 332 |
| Preserve-approval | `test_preserve_approval_when_identity_unavailable_at_final_revalidation` ran |
| Migration | unreachable-legacy, one-shot mismatch, snapshot-mismatch, promotion tests ran |
| Audit self-consistency | unit and integration tests ran |
| Inode-reuse relocation | WSL `/tmp` `rmdir`+`mkdir` reuses `st_ino`; production `revalidate_workspace_security_state` still fails closed via `root_topology_mismatch` when included entries differ. Sibling rename is used when a test requires `stable_identity_mismatch`. |

## Native full fitness

```bash
uv run --frozen pytest -q
uv run --frozen pytest --cov -q
uv run --frozen ruff check .
git diff --check
```

| Gate | Result |
|---|---|
| Full pytest | **3152 passed, 14 skipped, 110 deselected**, 1 warning, **55.64s** |
| Coverage | **80.46%** aggregate (`TOTAL 18997 3144 5284 906`); `fail_under = 80` reached; **57.69s** |
| Ruff | `All checks passed!` |
| `git diff --check` | clean (`WSL_GATES_OK`) |

Skipped platform tiers are not treated as passes. The extra passes versus Windows are
Windows-skipped POSIX tests (byte-sensitive exclusions, file-mode checks, EINTR family
already counted in focused, etc.).

## Residuals (not this plan)

- Path/topology TOCTOU control, not workspace content integrity.
- Compiled exclusion-policy drop locations.
- Same-path directory replacement with reused `st_ino` is not a stable-identity change
  on this filesystem; topology remains the remaining signal when names/inodes of
  included children differ.
- WinError 6 / `DuplicateHandle` remains **P11-FU-5**.
