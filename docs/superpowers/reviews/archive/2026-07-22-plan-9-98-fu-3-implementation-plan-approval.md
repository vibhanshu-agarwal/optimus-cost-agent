# Plan 9.98-FU-3 Implementation-Plan Approval

## Approval snapshot

- Plan: `docs/superpowers/plans/2026-07-22-plan-9-98-fu-3-posix-runtime-root-tests.md`
- Design: `docs/superpowers/specs/2026-07-22-plan-9-98-fu-3-posix-runtime-root-tests-design.md`
- Baseline: `origin/main` at `41634cd2dcc8fae31315f9dfacdd1b95c679d82f`
- Plan SHA-256: `CA96915E5E992B5BF4AF4CABF22765272B986EFAD8B5A2D3C4C4B29FB2DFB27E`
- Design SHA-256: `00E47D4517C40F498618B3715840F79C98406C4DF0AEC539D1C4FEB0321FE421`
- Approval date: 2026-07-22

## Reviewer approval

The reviewing agent independently read the full design and implementation plan and verified the
POSIX/Windows assertion split, the exact per-entrypoint remediation strings, the real
post-authorization wrapper seam for the composed capture tests, the frozen-file list, the WSL
interim gate, the full CI-equivalent command sequence, and the checkbox-only closure protocol.
The plan is approved for execution at the exact digests above.

## Operator approval

The operator approved the exact plan bytes and explicitly authorized execution. The operator's
approval includes the Task 0 planning commit and the task-scoped implementation commits described
by the plan, while preserving `uv.lock` and `.claude/` as user-owned unstaged state.

## Scope and binding decisions

- This lane changes test code and test-only helpers only; no file under `src/` may change.
- Bucket A preserves POSIX `NO_APPROVAL` at durable-record lookup after pre-authorization mutation.
- Bucket B reaches the real audit consumer only after real authorization and must preserve
  `AUDIT_DIR_UNAVAILABLE` for missing or unsafe runtime roots.
- The composed tests must patch only the module-level `authorize_capture` binding with a wrapper that
  calls the real authorization first; audit functions, gate functions, and exceptions remain real.
- The five FU-3 Linux tests must execute without skip, deselect, xfail, or platform-xfail.

