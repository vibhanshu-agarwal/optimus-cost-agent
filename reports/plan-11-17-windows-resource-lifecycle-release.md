# Plan 11.17 Windows Resource-Lifecycle Investigation — Release Record

**Status:** Investigation disposition complete; neither follow-up is closed and no code correction is
claimed.

## Final per-entry disposition

| Entry | Disposition | What the evidence establishes | What it does not establish |
| --- | --- | --- | --- |
| `P11-FU-5` | Open — reproduced, context known; root cause unestablished. | Historical three Windows occurrences, the two real Git-spawning selectors, new intermittent Task 0 observations, and failure in `Popen._make_inheritable` during captured-handle preparation. | A Git/Python/product root cause, an absence result, or credit for FU-29's injected fault. |
| `P11-FU-6` | Open — reproduced, root cause unestablished. | A full-unit-process `WinError 10053` recurrence at the current successor, followed by isolated and in-file clean comparisons. | A deterministic red, test-harness defect, production defect, or 59-clean no-reproduction disposition. |
| `P11-FU-7` | Unrun dependent lane under Plan 11.16. | Its historical 25-process coverage gate stopped at 4/25 because FU-6 recurred. | A pass, partial completion, restart, or closure by Plan 11.17. |
| `P11-FU-4` | Not discharged. | Its distinct real-`acpx` freshness acceptance criteria were read. | That the similarly named current `P11-FU-5` Windows flake supplies fresh FU-4A/FU-5 live evidence. |

P11-FU-26 remains closed only as obsolete-by-retirement. Its prior `WinError 10053` is retained as
a transferred historical signal, not reopened and not proof of the current `test_server` cause.

## Evidence artifacts

- [FU-5 disposition](plan-11-17-p11-fu-5-windows-disposition.md) records the historical three,
  source-report boundaries, current observations, and absence limit.
- [FU-6 root-cause record](plan-11-17-p11-fu-6-root-cause.md) records the process-5 failure,
  source/traceback lifecycle timeline, P11-FU-26 comparison, and `insufficient_evidence` decision.
- [Baseline matrix](plan-11-17-windows-resource-lifecycle-baseline.md) records platform provenance,
  each retained raw-log SHA-256, the five completed unit processes, the unrun partial sixth process,
  and all selector/file comparisons. Raw logs remain outside the repository under the named system
  temporary evidence root.

The implementation worktree began from merged Plan 11.17 SHA
`702b3ca767e4710a5e2ab5ba8f53c11ab3d53305`; Task 0 custody landed as `8a05970`; the disposition
evidence commit is `e71c0c2f65281243afdf2f04c794b415b6607b07`.

## Deterministic-red and correction decision

Task 2 found no evidence-named lifecycle edge. The observed FU-6 exception occurs before that test's
`finally` teardown, but runtime address, thread-liveness, handler-completion, and thread-exception
facts are absent; FU-5 fails in a different, pre-child-launch handle-preparation path. No
independently driven public `serve_gateway()` lifecycle failed. Therefore Tasks 3 and 4 are
unavailable by the frozen plan: no temporary injection was promoted into a red, no test fixture or
production source changed, and no 59-process post-correction matrix was run.

The next eligible FU-6 observation is failure-time lifecycle data for the still-real route assertion:
server address, serve-thread liveness before and after teardown, and handler/thread exceptions. The
next eligible FU-5 observation is a failing `Popen` attempt's child-launch/handle-ownership boundary.
Neither permits retry-as-fix, sleep, timeout widening, skip, deselection, weakened assertions, or
`WinError` suppression.

## Documentation freshness audit

| Document | Result |
| --- | --- |
| Consolidated deferred-followups backlog | Updated: FU-5/FU-6 returned to open, evidence-bound future lanes; FU-7 records its separate unrun boundary. |
| Phase 1 roadmap | Updated: its FU-5 rationale now states reproduced, context-known rather than no reproduction. |
| Plan 11 milestone charter | Updated: current FU-5 state and historical no-reproduction context are both stated. |
| `README.md` | Read; its P11-FU-4 freshness claim remains current and unchanged. |
| Local live-dependencies runbook | Read; no current FU-5/FU-6/FU-7 claim required an update. |
| Frozen Plans 11.14, 11.15, and 11.17 | Read-only historical/approved authority; unchanged. |

## Gates and unrun tiers

- Passed before Task 0 commit: focused pool-status contract (3 passed), a final full
  `test_open_work_pool_hygiene.py` gate (46 passed), Ruff, and `git diff --check`.
- Final disposition documentation gate: `test_open_work_pool_hygiene.py` (46 passed in 0.94s), raw
  `release-docs-hygiene.log` SHA-256
  `58AB68139F45D9F035B8A17EFA009C51411F6A3BD0A5EB4D32113AB6E2C90D19`.
- Task 1: four clean Windows full-unit processes, one retained FU-6 failure, one unrun interrupted
  partial process. The 59-clean gate is not met and is not claimed.
- Selector/file comparison after FU-6 recurrence: 1 passed; 34 passed. These comparisons do not
  erase the full-suite failure.
- Not run: a deterministic red/green, correction matrix, Task 4 Windows coverage, and native-WSL
  parity. Each requires a correction path that the evidence did not authorize.
- P11-FU-7's 25-process `--cov` gate was neither resumed nor spent.
