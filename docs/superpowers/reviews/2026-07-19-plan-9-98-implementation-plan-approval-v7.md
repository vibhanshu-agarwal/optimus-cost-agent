# Plan 9.98 Implementation Plan Approval Record — V7 Closure-Integrity Amendment

**Status:** Approved and frozen on 2026-07-19; final plan closure remains blocked until this record
and the exact revised plan bytes are committed together in Task 8A.

**Implementation plan:** `docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md`

**V6 immutable baseline:** commit `2ab3bcb8b4e870e9896174e342cf485a20080068`, with the v6
approval record and SHA-256 `D6D3E563655D8BDDB1FA852995DD9465DB8169273E82916C7AE4158C0AEF605B`.

**Landed implementation:** commit `74d4ff21173a597c3b274cf6e6cbdf8a7eb43697`.

**Landed evidence/docs:** commit `4e914b8e1506554b63f36bfa22aa9e588d9d27b5`.

**Frozen V7 SHA-256:** `25DA8DD69AE91B478F4EC86A7E8D8A698955B794715E76724107A079A871F4FC`

## Approvals

- **Reviewer-agent:** Approved these exact v7 bytes on 2026-07-19 after independently verifying the
  full diff against `2ab3bcb`, the exact 82/10/92 checkbox count, `git diff --check`, every frozen
  path and Plan 9.96 core file, all v1-v6 approval records, and the complete prescribed stale-reference
  sweep. The reviewer confirmed that the only substantive post-v6 corrections are the already-reviewed
  Task 4 RED-suite wording correction and three Task 5 `-m e2e` flags, with every other change limited
  to the closure-integrity gate, ten-commit accounting, and v7 closure-baseline mechanics.
- **Operator:** Vibhanshu (`vibhanshu-agarwal`) explicitly approved these exact revised plan bytes on
  2026-07-19 after the reviewer-agent's exact-byte approval.

## Freeze Semantics

This v7 record approves the exact revised plan bytes whose digest appears above. It supplements — and
does not alter, replace, or invalidate — the v1/v2/v3/v4/v5/v6 records or their immutable baseline
commits.

V7 introduces no new implementation, architecture, or security design. It formally incorporates only
two implementation-time text corrections that were independently reviewed when made: Task 4 Step 3
accurately distinguishes its initial RED suite from the cases that were still missing, and all three
Task 5 E2E commands pass `-m e2e` so the repository's default marker exclusion cannot silently
deselect them. The remaining v7 changes are mechanical consequences of that formalization: Task 8A,
the seventh immutable approval record, ten-commit accounting, and a final checkbox-only comparison
rebased from v6 to v7.

V6 remains the controlling implementation and security-design amendment. V7 is only the controlling
checkbox-closure baseline. It does not reinterpret evidence, waive any frozen Plan 9.96 requirement,
authorize production or test changes, or change the separately owned Plan 9.99 prerequisite.

After the Task 8A amendment commit lands, subsequent checkbox ticks in the working tree do not
invalidate this v7 snapshot. Any further substantive plan text change requires fresh reviewer-agent
and operator approval plus a new digest-pinned amendment record before closure.

Approval authorizes only the Task 8A docs-only amendment commit and the subsequent Task 8 Step 4
checkbox-only closure commit in the existing approved worktree and branch. It does not authorize
changes to Plan 9.96's frozen files, Plan 9.96 core digest/default files, Plan 9.98 implementation or
test files, or any excluded Plan 9.96 follow-up file.

## Mechanical Verification

Run from the repository root in a terminal where `uv` is genuinely on `PATH`:

```powershell
uv run python -c "from pathlib import Path; import hashlib; p=Path('docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md'); print(hashlib.sha256(p.read_bytes()).hexdigest().upper())"
```

Expected exact output, before any Task 8A checkbox is ticked:

```text
25DA8DD69AE91B478F4EC86A7E8D8A698955B794715E76724107A079A871F4FC
```
