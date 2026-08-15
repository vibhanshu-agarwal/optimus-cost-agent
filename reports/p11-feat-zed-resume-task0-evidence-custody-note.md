# P11-FEAT-ZED-RESUME Task 0 evidence custody note

## Recorded fact

At `origin/main` commit `e624632b10169de938188e8001dbc822ee6ebd31` on
2026-08-15, each frozen Task 0 path below was absent:

- `reports/plan-11-7-task0-client-discovery-and-refusal-baseline.md`
- `reports/plan-11-7-task0-artifact-manifest.json`
- `reports/plan-11-7-acpx-resume-evidence.md`

The check used `git cat-file -e origin/main:<path>` for each path. Later
amendment-era `task0-checkpoint.json` files under `origin-a-fixture-v2` and
`retry-preflight-gate` are different artifacts and do not replace these named
Task 0 records.

## Classification

**Custody convention or loss: undetermined.** This checkout does not establish
whether the missing paths were deliberately excluded by the feature-plan evidence
convention or were lost later. The absence therefore is not classified as a
historical defect and does not invalidate or re-diagnose the frozen 1.13.1 seal.

## Effect and forward requirement

The repository cannot independently re-verify the 1.13.1 client discovery or
diff a current Zed result against its raw baseline. Any separately authorized
current-version re-probe must commit sanitized, reviewable evidence: the captured
protocol exchange, exact agent capabilities, Zed and acpx versions, UTC
timestamp, source commit, hermetic user-data-root provenance, and cleanup result.
That future evidence is a new baseline; it cannot reconstruct the absent
historical artifacts.
