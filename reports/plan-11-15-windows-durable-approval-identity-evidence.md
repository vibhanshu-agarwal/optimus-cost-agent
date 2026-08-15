# Plan 11.15 Windows durable-approval identity evidence

Implementation SHA: `12b881a28b4a736a0d18ccdf1c02c49b94167e41`
Branch: `agent/cursor/plan-11-15-durable-approval-identity`
Date (UTC): 2026-08-15

Mandatory Windows evidence for Tasks 7. Fitness-gate adaptations after
`3c0db4d` (empty-`.git` UNAVAILABLE, Plan 9.96 lock-file surface, audit-append
print location) and POSIX inode-reuse test alignment are included in this SHA.
Isolated CLI cases used the installed entry points against an isolated file
keyring; operator-facing stderr is unchanged.

## Checkout and platform provenance

| Field | Observed value |
|---|---|
| Worktree | `D:\Projects\Development\Python\optimus-cost-agent-wt-cursor-plan-11-15-durable-approval-identity` |
| Branch | `agent/cursor/plan-11-15-durable-approval-identity` |
| `HEAD` | `12b881a28b4a736a0d18ccdf1c02c49b94167e41` |
| `sys.platform` | `win32` |
| `platform.platform()` | `Windows-11-10.0.26200-SP0` |
| Python | `3.14.4` (`MSC v.1944 64 bit (AMD64)`) |
| `uv` | `0.11.29` |
| Git executable / version | `C:\Program Files\Git\cmd\git.exe`, `2.55.0.windows.3` |
| Filesystem | NTFS (`D:` volume type `NTFS`, label `New Volume`) |

### Frozen spec

| Method | Digest |
|---|---|
| SHA-256 (`Get-FileHash`) | `B445693AFB9B110E61D860F1B63D8836FF0EA651E0AC327BABA1CC906C84543B` |
| `git hash-object` (SHA-1 blob) | `292041621ded61313cbdcc41686d98a719d3a413` |

The spec was not edited. Bytes match Task 0 and the frozen contract pin.

## Focused security matrix

Command:

```powershell
uv run --frozen pytest tests/unit/acp/test_trusted_paths.py tests/unit/acp/test_launch_approvals.py tests/unit/acp/test_launch_gate.py tests/unit/acp/test_main_wiring.py tests/unit/acp/test_launch_approval_cli.py tests/unit/acp/test_launch_audit.py tests/integration/acp/test_launch_trust_flow.py -q
```

Result at `12b881a`: **324 passed, 18 skipped in 5.72s**.

The skip count dropped by one versus Tasks 0–6 because
`test_approval_bootstrap_allows_audit_then_revalidation_but_later_mutation_fails`
is no longer POSIX-ctime-gated; it now asserts topology mismatch on both platforms.

Named identity/migration/audit subset (`-k` over exclusion policy, FU-18 equal-ctime,
topology, unreachable legacy, one-shot mismatch, snapshot-mismatch, preserve-approval,
and audit self-consistency): **22 passed, 2 skipped, 204 deselected in 3.40s**.

The two skips are platform-guarded:

- `test_exclusion_policy_posix_byte_sensitive` — POSIX-only byte-sensitive names
- `test_revalidation_fails_after_workspace_directory_metadata_change` — legacy
  characterization kept under its original POSIX ctime skip; the unguarded FU-18
  proof is `test_fu18_equal_ctime_non_excluded_add_is_root_topology_mismatch`

### Named claims (Windows)

| Claim | Evidence |
|---|---|
| Exact exclusion policy | `test_exclusion_policy_exact_member_set` pins `WORKSPACE_EXCLUSION_POLICY_VERSION == 1` and the full member set; near-misses `.coverage.`, `xhs_err_pid1.log`, `hs_err_pid.log` are not excluded |
| FU-18 equal-ctime add | `test_fu18_equal_ctime_non_excluded_add_is_root_topology_mismatch` is unguarded and ran on Windows |
| Topology add/remove/rename | `test_topology_detects_add_remove_rename_and_ignores_nested_content` unguarded |
| Migration promotion / refusal | `test_promotion_writes_verified_v3_and_reports_migrated`; `test_legacy_snapshot_mismatch_refuses_promotion` (both digest and snapshot must match) |
| Unreachable legacy | `test_unreachable_legacy_requires_explicit_reapproval` |
| One-shot not migrated | `test_one_shot_version_mismatch_is_not_migrated` |
| Preserve-approval / no `NO_APPROVAL` | `test_preserve_approval_when_identity_unavailable_at_final_revalidation` plus FU-29 WinError 6 injections in `test_main_wiring.py` |
| Audit self-consistency | unit `test_audit_append_self_consistency_does_not_change_topology`; integration `test_full_launch_trust_flow_audit_self_consistency` |

Skipped platform tiers are not treated as passes.

## Isolated CLI subprocess cases

Harness: `%TEMP%\plan115-cli-evidence\_tmp_plan115_windows_cli_evidence.py`
(kept outside `tools/` so Plan 9.96 surface discovery does not classify it).
`PYTHON_KEYRING_BACKEND` pointed at an isolated file keyring. The operator
Windows Credential Manager service `optimus-cost-agent-approvals` was not read
or written.

Installed entry points:

- `.venv\Scripts\optimus-agent.exe`
- `.venv\Scripts\optimus-trust.exe`

| Case | Exit | Operator stderr / stdout | `NO_APPROVAL` | Secrets |
|---|---:|---|---|---|
| Permanent Git failure (`git.cmd` `exit /b 128`) | 2 | `WORKSPACE_IDENTITY_UNAVAILABLE` … `Repair Git or filesystem access, then retry.` | absent | absent |
| Exhausted hang (`git.cmd` ping loop; 5s × 3 timeouts) | 2 | `WORKSPACE_IDENTITY_UNAVAILABLE` … `Retry the launch after the probe condition clears.` | absent | absent |
| Inter-launch add of `added-after-authorization` | 0 | Topology is ephemeral and recaptured per process; this is the new baseline, not a change | n/a | absent |
| Intra-launch TOCTOU: real `main()`; mutate after audit append | 2 | `WORKSPACE_IDENTITY_CHANGED` `(reason=root_topology_mismatch)` plus `re-approve` / `optimus-trust … approve --mode durable` | absent | absent |
| `optimus-trust inspect` current | 0 | `approval record state: current` | n/a | no API key / no `hmac_integrity_key` |
| `optimus-trust inspect` legacy v1 | 0 | `approval record state: legacy` | n/a | absent |
| After `authorize_launch` promotion | 0 | `approval record state: migrated from v2`; `pre_migration_assurance_not_upgraded` | n/a | absent |

Confirmed-changed CLI evidence is intra-launch: a file added *between* launches
is the next process's topology baseline. The unit/integration suites wrap
`append_launch_audit_event` for the same TOCTOU window; the CLI case used the
installed `optimus.acp.__main__.main` with that wrap.

`--check-config --no-auto-start` exits before Redis/Gateway start when identity
or revalidation fails.

## Windows full fitness

```powershell
uv run --frozen pytest -q
uv run --frozen pytest --cov -q
uv run --frozen ruff check .
git diff --check
```

| Gate | Result |
|---|---|
| Full pytest | **3138 passed, 28 skipped, 110 deselected**, 1 warning, **92.93s** |
| Coverage | **81.64%** aggregate (`TOTAL 18997 2903 5284 936`); `fail_under = 80` reached; **89.22s** |
| Ruff | `All checks passed!` |
| `git diff --check` | clean (exit 0) |

The warning is the pre-existing `runpy` `optimus.acp.__main__` RuntimeWarning in
`test_module_entrypoint_exists`. Deselected tests are the configured live-tier
markers (`requires_redis`, `requires_gateway`, `requires_os_keyring`, `e2e`, …).

### Fitness-gate adaptations included in this SHA

Empty `.git` mkdir is now `UNAVAILABLE` (correct; the old unavailable-as-absent
bug is gone). Tests that used that shortcut now resolve identity without a fake
Git directory:

- `tests/unit/acp/test_evidence_redaction_adapter.py`
- `tests/unit/tools/test_evidence_gather.py`
- `tests/integration/evidence/test_runtime_inputs_live.py`
- `tests/integration/evidence/test_collector_redaction_live.py`

Plan 9.96 logging-surface inventory:

- `_append_audit_or_exit` remains the stderr-export owner (print not moved off
  that function)
- new safe-by-construction entry for
  `KeyringApprovalStore._exclusive_workspace_lock:file_open`

## Out-of-subsystem note (for Task 9)

`tools/run_plan117_custody_feasibility.py` has a one-line adaptation from Task 4:

```diff
-        "workspace_digest": record.workspace_identity.digest,
+        "workspace_digest": record.workspace_digest,
```

`ApprovalRecord` stores `workspace_digest` directly; the old
`workspace_identity.digest` attribute no longer exists. This is a necessary
compile-time adaptation, not a custody-behavior change.

## Residuals (not this plan)

- Path/topology TOCTOU control, not workspace content integrity.
- Anything matching the compiled exclusion policy is an accepted undetected drop
  location.
- Same-path directory replacement that reuses `st_ino` (observed on WSL `/tmp`
  `rmdir`+`mkdir`) is not a stable-identity change; topology still fails closed
  when included immediate-root entries differ. Sibling-rename is used when the
  test specifically requires `stable_identity_mismatch`.
- WinError 6 / `DuplicateHandle` subprocess hygiene remains **P11-FU-5**.
- `.uv-cache-plan118` is redundant with `^\.uv-cache-.+$` (harmless exact-name
  duplicate; policy contents are frozen at version 1).
