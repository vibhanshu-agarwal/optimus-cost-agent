# Static typing cohort 2: provisional candidate verification

**PRE-COMMIT DEVELOPMENT SNAPSHOT - NOT FINAL ACCEPTANCE.** This report is filed with the candidate and will not be amended to attach later results. Exact-source post-commit Windows/WSL finals and Claude review belong to [#329](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/329) and retained external evidence.

The [approved repository contract](../docs/superpowers/plans/hardening-static-type-checking-implementation_v3.md) closes only `optimus_model_policy.registry`. Base main is `f704db0c8cd1905807fb334af9bcd332e9143f1f`, tree `1873d9e287562ecdd0e1a42d543ac5c3da11fcad`. The candidate changes one import and two annotations, preserves every executable loader statement and its string-key guard, removes exactly one Mypy exception (45 to 44), and adds three existing-matrix real-YAML rejection cases. `uv.lock`, source selection, ratchet/bootstrap implementation and security policy are unchanged. Registry tests use real values/files; #328 has no mock conversion claim.

## Fresh baseline evidence

| Host | Interpreter / Mypy | Configured result | Unmasked errors / error files / checked files |
|---|---|---|---|
| Native Windows | Python 3.14.4 / Mypy 2.3.1 | clean | 215 / 45 / 226 |
| Ubuntu-24.04 WSL | Python 3.14.8 / Mypy 2.3.1 | clean | 206 / 44 / 226 |

Separate environments were synced frozen and hook environments provisioned before measurement. The WSL runtime archive matched the approved digest. Derived unmasked configs remove only the source-debt override. Complete diagnostic multisets match the accepted predecessor evidence, including both registry override errors; their module union equals the actual 45-entry configuration.

## Provisional static and runtime evidence

After removing only the registry exception, native Windows configured Mypy produced exactly two `override` failures at `registry.py:148`, against PyYAML SafeConstructor and BaseConstructor, with all 226 source files checked. This is the static RED case.

Changing the import and return/local annotations to `Hashable` made configured native and explicit `--platform win32` Mypy pass all 226 source files. The permitted registry file passed **77 tests before and 77 after** the annotation change, including the three added YAML-key cases. Existing runtime behavior already rejected those keys. Both runs were coverage-free, without xdist, active/default/native-valid with full guard and COMPLETE records; parent observation was UNKNOWN. Their source was dirty and is only provisional development evidence. The actual executable, clone and pytest basetemp paths passed the current literal repr-absence sentinel inventory; variable-bound values are not exhaustively inferred.

At this snapshot, Plan 12's signed concurrent-work clearance imposes a live-window restriction. Broader preflight modules, commit-profile/ratchet/whole-model-policy checks, staged documentation/security gates, commit, final unmasked deltas, full default product coverage/validity and exactly-one eligibility receipts remain required and are not claimed here. Forecast final totals are Windows 213 / 44 / 226 and WSL 204 / 43 / 226, with exactly the two registry diagnostics cleared and zero new entries. These are forecasts until exact-source final runs.

## Delivery boundary

No successful source commit exists at this snapshot. The authorized limit is one normal-hook unpushed local commit, transferred to the WSL clone through a verified full-history local Git bundle. Final Windows then WSL checks must bind to the identical clean commit/tree. Claude reviews the staged candidate and final results. Any failed gate remains visible and stops its attempt. A new secret-scanner finding requires a separately reviewed and approved disposition; this report grants no exception or bypass. No push, PR, merge, issue closure, cleanup or retired watcher restart is authorized. All new environments remain retained.
