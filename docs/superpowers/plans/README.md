# Implementation Plan Directory

This directory contains only governance documents and implementation plans that are still live.
The [consolidated deferred-followups backlog](2026-07-23-consolidated-deferred-followups-backlog.md)
is the sole authority for feature, defect, follow-up, plan status, priority, ownership, and next gate.
Do not infer current status from a plan's checkboxes or prose.

## Directory contract

- Active and blocked plans stay at this directory root. A blocked plan is still live and is never
  moved merely because it is waiting for authority, a dependency, or a design ruling.
- Completed, superseded, retired, abandoned, and reviewed-disposition plans move once to the flat
  [`archive/`](archive/) directory. The move preserves file bytes; only references change.
- The backlog's `Live implementation plan registry` must name every live root plan exactly once as
  either `Active` or `Blocked`. Files in `archive/` must never appear in that registry.
- The roadmap and milestone charter may summarize historical sequencing, but they do not own live
  status.

## Maintenance workflow

1. Register every feature, defect, and follow-up in the consolidated backlog before scheduling it.
2. Add a new implementation plan at this root and add exactly one registry row in the same change.
3. Record priority, ownership, blocking state, and the next gate only in the backlog.
4. Revise a plan by publishing the next complete `_vN` file. Keep only the newest live version at
   the root and move its frozen predecessors to `archive/` after the new version becomes authority.
5. Do not create separately named amendment plans. Existing historical amendment files are frozen
   provenance and remain byte-identical in `archive/`.
6. When work reaches a terminal disposition, update the backlog first, remove the live-registry row,
   and move the plan to `archive/` in the same PR.

The documentation hygiene tests enforce the root/registry/archive relationship. A plan whose state
is uncertain remains at the root as `Blocked` until the backlog records a reviewed disposition.
