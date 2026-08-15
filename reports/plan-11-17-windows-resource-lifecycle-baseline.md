# Plan 11.17 Windows Resource-Lifecycle Investigation — Task 0 Baseline

**Status:** Task 0 custody and baseline record. This is an investigation record, not a closure or
root-cause finding.

**Recorded:** 2026-08-15, Windows 11 `10.0.26200`, CPython `3.14.4`, Git `2.55.0.windows.3`.

## Provenance and scope

The investigation branch starts at `702b3ca767e4710a5e2ab5ba8f53c11ab3d53305`, the merge commit
for Plan 11.17. It evaluates the two distinct follow-ups named in the frozen plan:

| Follow-up | Question | Current disposition |
| --- | --- | --- |
| `P11-FU-5` | Does the Windows `DuplicateHandle` / `WinError 6` failure have an applicable, reproducible subprocess-lifecycle cause? | Reproduced, context known; root cause not established. |
| `P11-FU-6` | Does the Gateway `test_server` full-suite port/teardown flake recur under independent full unit-suite processes? | Investigation begins with the plan's 59-process bound. |

`P11-FU-7` remains owned by Plan 11.16. Its Windows coverage gate stopped after 4 of 25
processes because FU-6 recurred; it is recorded as unrun, not passed, partially complete, restarted,
or spent by this investigation.

## FU-5 evidence custody

The operator-approved current disposition records **three** Windows `WinError 6` /
`DuplicateHandle` occurrences in the two Git-spawning selectors
`test_immutable_documents_match_approved_head_blobs` and
`test_product_checkpoint_log_location_remains_gitignored`. The source evidence records below
support the selector and mechanism history. They do not enumerate three individually timestamped
occurrences; the exact count is therefore retained as the operator-approved disposition rather than
inferred from the reports.

| Source | What it establishes | What it does not establish |
| --- | --- | --- |
| `reports/plan-11-14-p11-fu-21-custody-relay-exit-code-evidence.md` (Ruff/diff/sealed-artifact section) | Names both selectors and records a `DuplicateHandle` incident. | All three operator-recorded occurrences or a root cause. |
| `reports/plan-11-15-durable-approval-identity-baseline.md` (baseline failures section) | Records the same `subprocess.Popen` / `_make_inheritable` mechanism in four other Windows Git/DACL subprocess tests. | That those four failures are any of the three occurrences above; they are corroborating mechanism evidence only. |
| `reports/plan-11-15-windows-durable-approval-identity-evidence.md` (residuals) and `reports/plan-11-15-durable-approval-identity-release.md` (unrun/unclaimed tiers) | Retains FU-5 as open and keeps the separately injected FU-29 Git-fault behavior from receiving FU-5 credit. | A FU-5 correction, exclusion, or closure. |

The prior ten-run no-reproduction result is historical context, **not contrary evidence**. FU-5 has
no established recurrence rate, and later clean runs cannot prove its absence.

## FU-6 statistical boundary

Task 1 will launch 59 independent Windows `pytest tests/unit -q` processes without an artificial
retry or recovery path. At the previously observed 5% per-process recurrence rate, the chance of at
least one detection is `1 - 0.95^59 = 95.2%`; the model leaves a 4.8% chance of observing no
recurrence even if that rate persists. This calculation is conditional on independent,
representative 5% processes. It bounds this configuration and does **not** establish absence.

For comparison, 20 clean processes would provide only 64.2% detection confidence at that rate
(35.8% residual); 90 processes would provide 99.0%. The raw logs, process outcomes, environment,
and any failure selector comparisons belong in the Task 1 matrix outside the repository until they
are summarized in a committed evidence report.

## Task 0 Windows observations (not part of the 59-process bound)

The required documentation-hygiene validation itself supplied new FU-5 characterization evidence.
These invocations are not unit-suite processes for Task 1 and are not counted toward its 59-process
FU-6 bound.

| Invocation | Outcome | FU-5 observation | Raw evidence |
| --- | --- | --- | --- |
| Initial full documentation hygiene validation, before the scheduled-status contract was aligned | 8 failed, 38 passed | Both FU-5 selectors raised `WinError 6` in `subprocess._make_inheritable` while spawning Git (`DuplicateHandle`, handle `540`). | Terminal transcript only; this pre-matrix invocation has no standalone raw log. |
| FU-5 two-selector comparison after status-contract alignment | 2 passed | Clean comparison only; it does not contradict or erase the preceding recurrence. | `fu5-selectors-after-task0-status-contract.log`, 100 bytes, SHA-256 `07F9F031293F01F50E925E080B427F0A3B355820BEE476D6A45F4F6CC86A68D1`. |
| Containing-file comparison after status-contract alignment | 44 passed, 2 failed | `test_product_checkpoint_log_location_remains_gitignored` raised `WinError 6` / `DuplicateHandle` (handle `536`). The other failure was this task's then-unaligned status-prose assertion, not a lifecycle result. | `fu5-hygiene-file-after-task0-status-contract.log`, 4,048 bytes, SHA-256 `FC707D847D6EC9AF3E483E1C225891F1F7D6EEAD65BD63B426B59208F8344740`. |
| Focused scheduled-status contract | 3 passed | Confirms the pool's status projection and plan-link checks; it does not exercise Git subprocesses. | `task0-planned-status-contract.log`, 100 bytes, SHA-256 `5ECBA242B02EC850DA76FFDE88104DF086BE1F7CA54F1FA149C07AD3CA1373E6`. |
| Full documentation hygiene validation after the status contract was aligned | 44 passed, 2 failed | Both FU-5 selectors again raised `WinError 6` / `DuplicateHandle` while spawning Git (handle `552`). | `task0-doc-hygiene-final.log`, 4,023 bytes, SHA-256 `18B2E60BD4509931C84EDD7BA2A93890A2E358A1BEF3064C6CD3CB1A2F60E2BD`. |
| Subsequent full documentation-hygiene gate | 46 passed | A clean observation; it establishes only this invocation passed after the earlier failures, not that FU-5 is absent. | `task0-doc-hygiene-gate-attempt-2.log`, 101 bytes, SHA-256 `A116D8F77C3C48EAFD6E3FE0438994FA00B1C58EAEFDC3A2AAE2703B134AD489`. |

The named raw files are retained outside the repository under the system temporary evidence root
`C:\Users\pc\AppData\Local\Temp\plan-11-17-windows-unit-runs`. No FU-6 `test_server` unit-suite
process has started in Task 0.

## Task 1 Windows unit-process observations

The first four independently launched `pytest tests/unit -q` processes were clean. Process 5
reproduced FU-6 exactly at
`tests/unit/optimus_gateway/test_server.py::test_unknown_route_remains_not_found`:
`ConnectionAbortedError: [WinError 10053]` from `HTTPConnection.getresponse()`. The 59-clean
no-reproduction branch was therefore inapplicable. The already-started sixth process was interrupted
after the recurrence was classified; it is unrun and excluded from every count. No additional unit
processes were launched. This follows Task 1's recurrence branch to Task 2; it does not recast the
partial sequence as a five-run no-reproduction test.

| Process | Start (UTC) | Duration | Exit | Result and SHA-256 |
| ---: | --- | ---: | ---: | --- |
| 1 | 2026-08-15T08:35:47.4479813Z | 103.71s | 0 | Clean; `unit-01.log`, `3EFDBB4CB1D24783C8F4DCD4718EDDF5ECFDF3CDB365E5AB539F88A4E1001E45`. |
| 2 | 2026-08-15T08:37:31.2009766Z | 84.14s | 0 | Clean; `unit-02.log`, `529D4C690E91D595A42F64495C8E6C2F5AEC05D77D5FBF7DFA9E23E56DC08C71`. |
| 3 | 2026-08-15T08:38:55.3510307Z | 88.54s | 0 | Clean; `unit-03.log`, `6ACABE303426500FB907C909FF291C86F8CDE13820511FD857E48399F1E67A7E`. |
| 4 | 2026-08-15T08:40:23.8913191Z | 86.51s | 0 | Clean; `unit-04.log`, `AE284D6EBE78236EE70FF108D095030089B727CC9A83B878CDE106C29A215BBB`. |
| 5 | 2026-08-15T08:41:50.4117131Z | 86.30s | 1 | FU-6 recurrence; `unit-05.log`, `74C743AEC60DC3495FAE662C8F61E89116CFC888C5EA75516E48B2458B9CA2D9`. |
| 6 | started after process 5 | — | interrupted | Unrun partial process; `unit-06.log`, `63AA96B43DA925ED91E50FB0948918A91B86A06E721FAF68580AFF606ABA7A39`. |

The retained matrix `unit-process-matrix.tsv` has SHA-256
`6473ED819984B741F309B52875980527BF3DAE97EF72D5C048D24538D1F7408E` and records only the five
completed processes. The isolated failure selector then passed (`1 passed in 0.94s`;
`fu6-unknown-route-selector-after-unit05.log`, SHA-256
`A998F81FCA05F59418864E13634F26320D4B685104BFF9B253BC7CDADB8AF003`) and its containing file
passed (`34 passed in 17.97s`; `fu6-test-server-file-after-unit05.log`, SHA-256
`602628F043EBE8A354B01D1564C6CCB68BA0D4066514C0DDA0EE75748D906801`). Those are comparison
observations, not retries counted as success.

## Task 0 outcome

The consolidated follow-up pool now assigns FU-5 and FU-6 to Plan 11.17 with their distinct
evidence rules, preserves FU-29 separation, and marks FU-7's gate as blocked on FU-6's own recorded
disposition. The documentation-hygiene contract now recognizes `Scheduled ->` plan links as
unresolved and verifies their plan targets; no application source, fixture, retry, exception
suppression, or production behavior changed in Task 0.
