# ADR-016: Review implementation at package checkpoints

**Status:** Accepted. **Decider:** Operator. **Date:** 2026-10-02 (Asia/Calcutta).
**Relation:** Supersedes the session's per-task Codex review and review-before-local-commit rules.
It changes delivery cadence, not the frozen feature contracts or code-safety requirements.

## Operator words and source

> "We need to change the mode of working here - too slow as of now. Please do not review with Codex
> after every task. Establish sensible checkpoints say 3-4 checkpoints per plan at most and get the
> checkpoint reviewed by Fable 5.1, followed by Codex. Current cadence is a NO-GO."

Source S3 in the [decision index](README.md#rules-for-every-record), archive `optimus-handoff\decisions-sources\2026-10-02-claude-session-context-engine-package-a-export.zip`,
SHA-256 `9B89272060555D1542B14F25C37807F21C5763222D0A93CF2C1ECC791D642A66`. Original user message UTC `2026-10-01T18:33:12.945Z`; the local date is October 2.

Question: "Between checkpoints, how should Claude commit each finished task? Today's rule is a local
commit only after Codex reviews, with every hook, including the ~35-minute full suite."
Selected: **"Per task; full suite at CP (Recommended)"**. Selected option description:

> "Each task is committed locally once its focused tests pass, running every hook except the
> full-suite coverage hook (SKIP=optimus-pytest-coverage). One full suite with coverage runs at each
> checkpoint, before Fable and Codex review it. Fixes become follow-up commits. Fastest; a broken full
> suite is caught at the checkpoint, not per task. Nothing is pushed without you."

Alternatives were "Per task, every hook" and "One commit per checkpoint". The selected approach
reduces repeated suite/reviewer cost while retaining task-level focused tests and a package gate;
integration failures are caught later. One commit per checkpoint would reduce commit isolation.

Question: "Package A is done (4 local commits) and Task 3 is accepted. What next?"
Selected: **"Package A PR, then CP1 (Recommended)"**. Selected option description:

> "Codex drafts Package A's backlog and docs update (needs a fresh transcript export), then Claude
> pushes the branch and opens the PR; merge stays yours. Meanwhile Codex drafts Task 1's contracts,
> which Tasks 4 onward need before CP1 can start."

Alternatives were "Start CP1 now, PR later" and "Pause Plan 12.2". Publishing the already accepted
repair avoids holding it behind the entire engine, while contract drafting can proceed alongside it.
Original question-tool selections: UTC `2026-10-01T18:34:45.829Z`, reproduced by S3.

## Decision and execution boundary

Standing rule: no per-task Codex reviews; at most four planned checkpoints per plan, Fable 5.1 then
Codex, with no reviews in between. Existing Package A reviews are historical, not repeated.

| Remaining Plan 12.2 checkpoint | Package | Tasks |
|---|---|---|
| CP1 | B: registry/request transport | 4-5 |
| CP2 | C: engine contracts/strategies/summary gate tooling | 6-8 |
| CP3 | D: host integration/full picker/accounting | 9-11 |
| CP4 | E: calibration/real-client evidence | 12-13 |

Claude may make local task commits after focused checks, with only `optimus-pytest-coverage` skipped.
Each checkpoint gets one scheduled full suite/coverage run, Fable review, focused fixes and one
consolidated Codex review. Disclose tested commit and later fix delta; passing output cannot be
attributed to later bytes. No random retries or erased failures.

Claude reviews Package A's proposed docs before its docs-only commit, push and PR. No intermediate
Codex re-clearance of that docs commit is added. Merge, paid/live authority and any other hook skip
remain the operator's. Task 1 contracts require acceptance before CP1. Later work proceeds under
the accepted scope and these checkpoints, not fresh per-task approval requests. Live status and
next gates belong solely to the consolidated backlog. No general paid/operational authority follows.
