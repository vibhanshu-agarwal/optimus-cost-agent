# Implementation Plan Directory

This directory contains only governance documents and implementation plans that are still live.
GitHub Issues are the work register ([ADR-022](../../decisions/ADR-022-github-issues-as-the-work-register.md)): a record's status, priority, ownership, blocking state and
next gate live in its issue. The [consolidated deferred-followups backlog](2026-07-23-consolidated-deferred-followups-backlog.md) is
transitional: it holds them only for records that have not moved to an issue (a row or entry marked `Moved` is authoritative in its
linked issue) and takes no new work entries (a new plan's issue-only registry pointer row excepted). Do not infer current status from a plan's checkboxes or prose.

## Directory contract

- Active and blocked plans stay at this directory root. A blocked plan is still live and is never
  moved merely because it is waiting for authority, a dependency, or a design ruling.
- Completed, superseded, retired, abandoned, and reviewed-disposition plans move once to the flat
  [`archive/`](archive/) directory. The move preserves file bytes. Repair references in mutable
  documents, but do not edit frozen plans, approval records, release reports, or evidence artifacts
  merely to update a historical path; their pinned bytes take precedence.
- The backlog's `Live implementation plan registry` must name every live root plan exactly once as
  either `Active` or `Blocked`. Files in `archive/` must never appear in that registry.
- The roadmap and milestone charter may summarize historical sequencing, but they do not own live
  status.

## Maintenance workflow

1. Create each new feature, defect, follow-up and plan as a GitHub issue before scheduling it; the backlog takes no new work entries, and a new plan is listed by its issue-only registry pointer row (step 2).
2. Add a new implementation plan at this root and add exactly one registry row, a pointer to the plan's issue, in the same change.
3. Record priority, ownership, blocking state, and the next gate only in the record's issue (in the backlog only for a record not yet moved).
4. Revise a plan by publishing the next complete `_vN` file. Keep only the newest live version at
   the root and move its frozen predecessors to `archive/` after the new version becomes authority.
5. Do not create separately named amendment plans. Existing historical amendment files are frozen
   provenance and remain byte-identical in `archive/`.
6. When work reaches a terminal disposition, update its issue (the backlog entry only if the record has not moved) first, remove the live-registry row,
   and move the plan to `archive/` in the same PR.

All docs folders follow the same root/`archive/` rule, and [the docs index](../../README.md) lists every
current document. Tests find documents by file name (`tools/doc_paths.py`), so moving a plan into
`archive/` needs no test change.

The documentation hygiene tests enforce the root/registry/archive relationship. A plan whose state
is uncertain remains at the root as `Blocked` until a reviewed disposition is recorded: in its GitHub issue for a migrated record, in the backlog otherwise.
