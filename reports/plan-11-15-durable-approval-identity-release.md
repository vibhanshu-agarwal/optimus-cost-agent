# Plan 11.15 durable-approval identity — release claim-to-evidence

Implementation SHA: `12b881a28b4a736a0d18ccdf1c02c49b94167e41`
Frozen spec SHA-256: `B445693AFB9B110E61D860F1B63D8836FF0EA651E0AC327BABA1CC906C84543B`
(`git hash-object` `292041621ded61313cbdcc41686d98a719d3a413`)
Date (UTC): 2026-08-15

Windows evidence: `reports/plan-11-15-windows-durable-approval-identity-evidence.md`
Native WSL ext4 evidence: `reports/plan-11-15-wsl-durable-approval-identity-evidence.md`

This report maps frozen-spec Definition of Done and brief requirements to named tests
and platform artifacts. `P11-FU-18` and `P11-FU-29` are closed separately below; neither
closure uses the other's evidence, and neither uses a `P11-FU-5` WinError 6 hygiene rerun.

## Claim-to-evidence

| Claim | Primary tests | Windows | WSL |
|---|---|---|---|
| Frozen spec bytes unchanged | Task 0 hash; `Get-FileHash` / `hashlib.sha256` | `B445693A…` | `B445693A…` |
| Git `PRESENT` / `ABSENT` / `UNAVAILABLE`, one probe | `TestGitContextDispositions` in `test_trusted_paths.py` | focused 324 passed | focused 332 passed |
| Exactly three transient attempts; permanent stops once | parametrized Git retry (`winerror-6`, `EINTR`, `EAGAIN`, `ETIMEDOUT`, `TimeoutExpired`) | yes | yes |
| Git redirect env stripped | Windows case-insensitive strip test; POSIX exact-key strip in Git helper tests | Windows-only skip on POSIX | POSIX tests ran |
| v3 excludes ctime; digest stable across equal-ctime | `test_fu18_equal_ctime_non_excluded_add_is_root_topology_mismatch` | unguarded | unguarded |
| Exact compiled exclusion policy v1 | `test_exclusion_policy_exact_member_set`; near-misses `.coverage.`, `xhs_err_pid1.log`, `hs_err_pid.log` | yes | yes |
| Original FU-18 reproduction caught | equal-ctime non-excluded add → `root_topology_mismatch` | yes | yes |
| Unavailable preserves approval; never `NO_APPROVAL` | `test_preserve_approval_when_identity_unavailable_at_final_revalidation`; CLI exhausted/permanent unavailable | unit + CLI exit 2, retry/repair, no `NO_APPROVAL` | unit |
| FU-29 transient fault does not change identity | WinError 6 three-attempt injections in `test_main_wiring.py` | yes | EINTR/EAGAIN/ETIMEDOUT family |
| Valid v2 durable promotes to v3 | `test_promotion_writes_verified_v3_and_reports_migrated` | yes | yes |
| Unreachable legacy requires reapproval | `test_unreachable_legacy_requires_explicit_reapproval` | yes | yes |
| One-shot not migrated | `test_one_shot_version_mismatch_is_not_migrated` | yes | yes |
| Snapshot mismatch refuses promotion | `test_legacy_snapshot_mismatch_refuses_promotion` | yes | yes |
| Migration visible in inspect/audit | CLI inspect `migrated from v2` + `pre_migration_assurance_not_upgraded`; audit fields | isolated file-keyring CLI | unit/integration |
| Audit cannot trip topology control | `test_audit_append_self_consistency_does_not_change_topology`; `test_full_launch_trust_flow_audit_self_consistency` | both tiers | both tiers |
| Windows + native Linux | this SHA on NTFS and ext4 | 3138 passed / 28 skipped / 110 deselected; cov **81.64%**; Ruff clean | 3152 passed / 14 skipped / 110 deselected; cov **80.46%**; Ruff clean |

CLI (Windows, isolated file keyring, not the operator vault):

- Permanent Git `exit 128` → exit 2, `WORKSPACE_IDENTITY_UNAVAILABLE`, repair phrasing, no `NO_APPROVAL`
- Exhausted hang (5s × 3) → exit 2, retry phrasing, no `NO_APPROVAL`
- Intra-launch topology TOCTOU via installed `main()` → exit 2, `root_topology_mismatch`, re-approve
- Inter-launch add of `added-after-authorization` is the next process baseline (topology is ephemeral)
- `optimus-trust inspect` current / legacy / migrated; no API key / no `hmac_integrity_key`

## `P11-FU-18` closure (own evidence only)

- Non-excluded `added-after-authorization` with forced equal `st_ctime_ns` fails closed as
  `WORKSPACE_IDENTITY_CHANGED` / `root_topology_mismatch`
  (`test_fu18_equal_ctime_non_excluded_add_is_root_topology_mismatch`), unguarded on Windows and WSL.
- Add/remove/rename/symlink-retarget covered by
  `test_topology_detects_add_remove_rename_and_ignores_nested_content` and
  `test_revalidation_fails_for_symlink_target_change`.
- Residuals explicit: compiled exclusion drop locations (`.coverage`, `hs_err_pid123.log`, nested
  under existing `tmp`); path/topology TOCTOU, not content integrity; same-path inode reuse on
  WSL `/tmp` is not a stable-identity change when children are identical.

Does not cite Git-retry, preserve-approval, or migration tests.

## `P11-FU-29` closure (own evidence only)

- One/transient/exhausted Git fault injection: three attempts then
  `WORKSPACE_IDENTITY_UNAVAILABLE`; success path preserves digest.
- Preserve-approval / no `NO_APPROVAL`: stored durable bytes unchanged through `main()`; CLI
  unavailable cases print retry/repair, never `NO_APPROVAL`.
- Exact exclusion policy v1 pins version and member set so routine gitignored churn is not a
  topology false change.
- Observable HMAC-verified v2→v3 promotion with inherited-trust
  `pre_migration_assurance_not_upgraded`; unreachable legacy and one-shots are not migrated.

Does not cite the FU-18 equal-ctime add test. Does not treat a `P11-FU-5` handle-flake rerun as
resolution.

## Out-of-subsystem adaptation

`tools/run_plan117_custody_feasibility.py` reads `record.workspace_digest` instead of the removed
`record.workspace_identity.digest`. Compile-time field rename only.

## Reviewer notes absorbed

- Comment on skipped legacy POSIX ctime test at
  `tests/unit/acp/test_trusted_paths.py` pointing at
  `test_fu18_equal_ctime_non_excluded_add_is_root_topology_mismatch`.
- `.uv-cache-plan118` remains a redundant exact-name (already matched by `^\.uv-cache-.+$`);
  policy v1 is frozen, not silently edited.
- Plan 117 tool sentence: above.

## Unrun / unclaimed tiers

Default `addopts` deselects live markers (`requires_redis`, `requires_gateway`,
`requires_os_keyring`, `e2e`, `requires_acpx`, …): **110 deselected** on both platforms.
Those tiers are not claimed. `P11-FU-5` remains open.

## Freshness audit

- `README.md`: no stale Plan 11.15 / FU-18 / FU-29 current-state claims.
- Plan 11 charter: no matching current-state claims.
- `docs/runbooks/local-live-dependencies.md`: native-clone gate unchanged; no identity-contract
  claims to update.
- Roadmap Plan 9.98-FU-1 still describes the historical `st_ctime_ns` binding in present tense;
  a current-state pointer to Plan 11.15 v3 identity was added there.
- Pool index/detail rows for `P11-FU-18` and `P11-FU-29` close separately with this report.
- Frozen spec and Plan 11.15 plan bytes were not edited.
