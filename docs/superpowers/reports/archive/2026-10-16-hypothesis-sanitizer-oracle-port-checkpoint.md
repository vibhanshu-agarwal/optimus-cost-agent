# Hypothesis sanitizer oracle — CP2 pre-commit evidence

Evidence snapshot: 2026-10-16 (Asia/Calcutta). Work authority and next gates live in [#364](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/364). This is source-bound development evidence, not final CP2 acceptance or publication authority.

Base/HEAD: `b27e99a347428a063050d7460e031eb47369b71c`. Branch: `agent/codex/hypothesis-sanitizer-oracle-port`. The working candidate has exactly `pyproject.toml`, `uv.lock` and the new `tests/unit/security/test_sanitization_properties.py`. No production, conftest, profile, ignore, hook, CI or secret-baseline changes. Git index unchanged; no commit, push, PR or merge.

Plan v2 SHA256: `d203eb4167ac3e204406558067b24f50d9276c7918935a7baca23a74bf7245c6`. CP1 was [independently accepted](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/364#issuecomment-6205789554); its 405-file packet remains unchanged. CP1 establishes two incremental mutant detections only relative to `tests/unit/security/test_sanitization.py`'s direct public-function calls, not the whole suite.

## Timing and reproducibility

| Observation (wall seconds) | Windows | Linux |
|---|---:|---:|
| Baseline security, three fresh processes | 4.036 / 1.857 / 1.918 | 13.696 / 5.130 / 5.330 |
| Candidate security, three fresh processes | 5.710 / 6.382 / 5.760 | 12.543 / 11.993 / 10.387 |
| Paired added time | 1.674 / 4.525 / 3.842 | -1.153 / 6.863 / 5.057 |
| Median paired added time | 3.842 | 5.057 |
| Difference of medians | 3.842 | 6.663 |
| Ordinary six-test serial | 4.185 | 7.682 |
| Ordinary supported two-worker xdist | 5.086 | 12.041 |

All sixteen active timing/compatibility invocations passed without timeout, source/status drift, collection errors or refused stream lines. Each security pair selects 124 baseline / 130 candidate nodes, zero deselected; the six additions match AST-derived exact node digests. Existing node outcomes and all existing dependency versions remain stable across each platform's three repetitions. All tracked candidate bytes agree across Windows and Linux; within each OS, baseline/candidate bytes differ only in the approved three paths. The dependencies added are exactly Hypothesis 6.167.1 and sortedcontainers 2.4.0.

Observed six-test serial <=30 s and median added security-selection <=30 s budgets pass on each host, by both paired-median and difference-of-medians interpretations. Claude independently recomputed all sixteen packets and [verified these pre-commit timing/compatibility results](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/364#issuecomment-6208616807), explicitly withholding final CP2 acceptance. No speedup or universal runtime claim. The timeout was an external 120-second invocation watchdog with child-tree teardown, not a Hypothesis deadline.

Windows Python 3.14.4 and Linux Python 3.14.6 use separate frozen environments. Both keep pytest 9.1.1, xdist 3.8.0 and normal root conftest/addopts. Candidate Hypothesis plugin is auto-loaded. The five decorated settings objects retain `derandomize=True, database=None, max_examples=300, deadline=None`; source strings remain bounded at 200. No health-check warning or suppression was observed. Generation is not claimed identical between Python/platform versions. Linux checkouts reside under `/mnt/c`, so absolute Linux timings include the WSL Windows-filesystem bridge qualification; they are not native-filesystem or hosted-CI measurements. CP3 retains its separate hosted Linux observations.

Only the paired timing invocations export fresh absolute ignored `tmp/hypothesis-sanitizer-port/timing/<invocation>/storage` paths. Ordinary serial/xdist commands use the existing ignored `.hypothesis/` cache and no storage export. Windows and WSL share a machine: campaigns are sequential, with all environment setup finished before campaign v2. Baseline pair 1 had cold bytecode; the candidate was already warm from CP1. Retain all samples and host/process snapshots. Foreign workload remains a noise qualification; no lane was paused and no uncontended-host claim is made. WSL process snapshots see the Linux namespace; a separate Windows host snapshot during that campaign is retained.

All Windows packets retain active/COMPLETE, native valid and full protection. Linux retains active/COMPLETE with native unsupported, guard unsupported_platform, protection none and weaker xdist capability. Both xdist packets select/execute all six tests, have zero deselected, two attached worker records and a valid controller verdict. UNKNOWN Windows parent ancestry and unsupported Linux parent labels are preserved.

## Collection, installation and focused checks

Separate collection-only invocations are passive diagnostics, not execution acceptance:

| Collection-only invocation | Selected | Process wall seconds | Pytest summary |
|---|---:|---:|---|
| collect-win-baseline | 124 | 1.376 | ======================== 124 tests collected in 0.18s ========================= |
| collect-win-candidate | 130 | 2.037 | ======================== 130 tests collected in 0.73s ========================= |
| collect-linux-baseline | 124 | 4.532 | ========================= 124 tests collected in 0.45s ========================= |
| collect-linux-candidate | 130 | 7.893 | ========================= 130 tests collected in 3.12s ========================= |

These diagnostic wall times include startup/exit overhead; pytest's collection summary is reported separately where emitted. They are warm ordinary-cache observations, not cold controlled timing pairs. CP1's resolver reported 3.04 s; its Windows candidate sync reported package preparation 3.17 s and installation 0.397 s, not a separately measured clean install experiment. CP2 baseline environment setup is separately retained in setup receipts (Windows short baseline wall 7.386 s; Linux sync wall 19.815 s). Install/resolution are outside all test timing windows.

Focused native Windows active runs (all selected calls passed, zero skips):

| Selection | Passed | Process wall seconds | Run ID |
|---|---:|---:|---|
| focus-run-context | 13 | 9.530 | `20261016T050627-39400-338f7a` |
| focus-profiles | 70 | 66.080 | `20261016T050642-59236-c1aef4` |
| focus-profile-selection | 41 | 1.865 | `20261016T050858-56700-932031` |
| focus-xdist | 39 | 75.302 | `20261016T050904-51912-7ba753` |
| focus-docs | 110 | 6.482 | `20261016T051025-51360-9a28db` |

Nested control/collection records remain archived; their expected negative/passive verdicts are not represented as outer gate failures or active acceptance. Current docs checks cover the existing checkout; they do not claim adoption of the proposed documentation projection.

Eight normal static/hygiene hooks pass with all-files input at unchanged configuration: trailing whitespace, YAML, TOML, file size, Ruff, Bandit, ast-grep and config trust. The unchanged local secret-scan hook passes on the three actual execution paths, and the new test file also passes the explicit strict local-secret scanner. These are separate from production-only CI scanning. The broader all-files secret scan FAILED with 683 locations in unchanged exact-base files outside the three execution paths; it is not a passing gate, not waived, and not classified here as real credentials or harmless. No baseline edits. The commit test-profile hook remains UNRUN at this step because the local commit is separately gated; all normal hooks on the exact eventual seven-path staged change remain owed when that commit is authorized. No --no-verify or SKIP exception.

## Preserved diagnostics and repairs

1. The initial deep Windows baseline checkout hit filename-length errors. Git core.longpaths repaired its missing checkout files, but Python still could not read a 274-character tracked path. The two first timing packets (4.463 s baseline, 6.951 s candidate) passed pytest but remain diagnostic only, excluded from acceptance statistics. They also overlapped Linux environment setup. Claude reviewed the repair: a new short sibling baseline, a fresh campaign and full tracked-file reads that fail closed. The old clone/logs remain untouched.
2. A wrong `Ubuntu` distribution launch failed before execution. Verified installed `Ubuntu-24.04` was used thereafter. No test or setup script ran in the wrong-name attempt. Pre-execution orchestration syntax errors and restricted Git reads likewise started no test and are retained in the task transcript.
3. Timing report helpers v1/v2 incorrectly relied on sanitized display labels (not unique, and nullable). Their error logs/helpers remain. V3 compares stable node digests against independently AST-derived new-test digests; no pytest invocation was repeated for reporting repairs.
4. The profile-focused pytest invocation passed all 70 tests, but its first reporter found the anchor in nested collect-only sessions too. The original incomplete result/helper/error remain. A separate recovered receipt binds the existing outer stdout terminal run ID to its typed archived record, without rerunning pytest. Subsequent wrappers use that outer terminal identity.
5. Normal static hooks initially failed before execution because the shared pre-commit cache lacked a pinned repository's manifest. The failure log remains. A fresh ignored task-local PRE_COMMIT_HOME ran the same pinned hooks; the shared cache was not repaired/deleted, no hook was bypassed and the environment override was restored. Upstream deprecated-stage-name warnings are retained; configuration was not auto-updated.
6. The additional all-files secret audit completed with exit 1 and 683 reported locations. The attempted owned-process cancellation did not execute because its identity guard found the process already gone; no process was stopped. `broad-scanner-disposition.json` binds all finding files to byte-identical exact-base content and proves none is a port execution path. The same hook then passed on the three actual changed execution files, a distinct normal-input scope. The original failed audit remains visible and has not been relabelled, waived or fixed in this test-only port.

## Remaining authority and verification

The four documentation paths in the approved plan are prepared as review-only copies under `projection/`; none was applied to tracked docs. The full plan is byte-identical, the checkpoint is a sanitized evidence snapshot, docs/README links both, and the transitional registry gains only an issue pointer. No new plan number or parallel work pool.

Canonical adoption and local commit still need their reserved operator grants. The final CP2 gate needs the hook-enforced committed candidate, committed-head docs checks, one canonical native Windows full-product coverage gate plus validate, separate exactly-one eligible full-default-session proof, and attributable exact-base safety-critical statement/branch comparison. None is claimed here. Linux full/default integration evidence remains an explicit CP3 PR-CI obligation. Push, PR, merge, issue metadata/closure, cleanup, services and private-memory writes remain outside this work.

Reproducible packet data: `cp2-timing-audit-v3.json`, `checks-audit.json`, per-invocation `before.json`, `after.json`, `invocation.json`, process snapshots, stdout/stderr and typed `run-context` archives. The packet manifest excludes baseline Git clones, their virtual environments and hook caches; those remain retained locally. Source candidate hashes are in the timing audit. Hashes in the manifest bind this review snapshot, not a future commit.
