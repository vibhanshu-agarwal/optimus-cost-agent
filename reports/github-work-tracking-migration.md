# Plan 11.29 release record: bounded GitHub authority switch for 49 Optimus work records

**Date:** 2026-10-12 (Asia/Calcutta). **Decision:** [ADR-021](../docs/decisions/ADR-021-bounded-github-authority-switch.md).
**Authority-switch commit:** `f4f0e2f8a7ee0192b2020553575dcb66758d5ca7`, the merge of PR #285 (2026-10-12 14:09:01 UTC, 19:39:01 IST),
parents `d3114bea` and `488d7a32`, tree `64bd2e5c2a5b3661dcb8e1b6da922699e9309927`.

This record states what the release delivered and how it was verified. It is not a status board: live status is in the GitHub issues
(`docs/work-status.html` reads them), and [`github-work-tracking-migration.json`](github-work-tracking-migration.json) (sha256
`34205961ef966f5ad45b57928ddd1899dc6df914b6f1cf818f6509542750b69e`) is the one-time source-to-issue mapping, never updated for future
work. The raw workstation evidence behind the figures below is archival provenance kept outside the repository, not a dependency.

## Scope

49 records of the 203 in the baseline `a929aab` (138 marked migrating): 7 plans, 6 features and 36 follow-ups, the pilots #222, #223
and #224 plus issues #230 to #275. Their status, priority, owner and next gate are now in their issues; the backlog keeps a `Moved`
pointer and a link pinned to the former detail at `d3114bea`. Not part of this release: the 87 other migrating records (they retain
their existing authorities, including the hardening boards), #33 (reconciled read-only, untouched) and the A2A pilot #225.

## Delivery

| PR | content | merge on `main` | main-push CI |
|---|---|---|---|
| #282 | migration tool, live page, manifest, offline gates | `cb959a38` (2026-10-11) | 7,469 passed |
| #284 | scoped cutover tool: `--scope`, neutral banner, reviewed source-update fields | `d3114bea` (2026-10-12) | 7,533 passed |
| #285 | the switch: manifest identities, pointer backlog, ten authority-wording edits, ADR-021, one pointer-integrity test | `f4f0e2f8` (2026-10-12) | 7,534 passed; required coverage floors pass |

## Issue updates (98 in all: no creates, no label-definition writes, no sub-issue bindings, nothing written to #33 or #225)

| step | issues | plan sha256 | published (2026-10-12, IST) |
|---|---|---|---|
| A: adopt the three pilots | 3 | `d96cf6e8…` | 10:25 |
| B: two reviewed source updates | 2 | `9c7516d3…` | 10:30 |
| C: neutral staged-copy banner on the rest | 44 | `9fc85d50b0b8581a0215026cf8503f06d836eb5329a7095c112f701f3dadc84b` | 10:47 to 10:49 |
| after the merge: remove the staged banner and the `shadow-pilot` label | 49 | `4b6db2115b21ba294dca80091d6964af052a65105a6b4ca38cd1f79b9f5063bf` | 19:56 to 19:59 |

Each batch was published once from a plan byte-identical to the reviewed one, with an intent journal, fingerprint checks and no retry.
After each, the changed set equalled the batch exactly, and the real reconcile output equalled the output computed beforehand on a
simulated GitHub, line for line.

## Verification

- **Reconcile after the final batch:** scoped to the 49, 0 findings (49 mapped; #33 and #225 untouched). Unscoped, 89 findings (the 87
  records without an issue, plus the A2A pilot's source-format record and its `shadow-pilot` label); the failed verdict is kept and was
  accepted by Codex for this scope. It is the baseline the next migration batch must change by exactly its own records.
- **Trial markers:** no issue body holds the staged banner; `shadow-pilot` remains only on #225; the 27 label definitions are unchanged.
- **Live page:** the committed page (Git blob `c745216c3d5d939dcae6806119b6957bf75f59b6`) was read in a real browser after the switch
  against the 51 open issues (Optimus 49, Evidence/A2A 1, untriaged #33): every row equalled rows derived independently from GitHub's
  labels and parents (40 of 40 checks; 4 of 4 negative controls caught); the Closed view was empty (no issue is closed); Reload
  re-read GitHub. That read was over loopback `http`, not a `file://` open; no post-switch human direct-file open is recorded.
- **CI:** the main-push guardrails and page workflows at `f4f0e2f8` succeeded (7,534 passed, 0 failed); the Linux guard limitations
  (`native`, `parent`, `guard` unsupported) are the same as at the previous main push.

## Reviews

Checkpoints 1 to 3 (Fable 5.1, then Codex) were accepted before publication. Checkpoint 4 (after the cutover): Fable 5.1 found the
delivery sound with amendments, none blocking; Codex accepted it with amendments the same day. As of this record Plan 11.29 is not
closed; its tracking issue is [#236](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/236).

## Not delivered by this release

The migration of the 87 pending records, #33 and the A2A pilot; the `Work tracking impact:` pull-request declaration and the
`**Tracking issue:**` plan-header convention (the existing masterplan-impact gate was kept; both are recorded as `P11.29-FU-1` and `P11.29-FU-2` in the backlog and owned by the
roadmap entry "Work tracking maintenance (Tracked, Not Yet Scheduled)"); the pool-edit freeze announcement; any
change to the plan's task checkboxes. Housekeeping outside this release (merged PR branches, lanes, local caches) is held.
