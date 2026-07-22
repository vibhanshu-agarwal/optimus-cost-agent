# Plan 9.99 Implementation Plan Approval Record

**Status:** Reviewer-agent approved on 2026-07-22; implementation has not started; operator approval pending.

**Implementation plan:** `docs/superpowers/plans/2026-07-22-plan-9-99-credential-uri-security-snapshot-canonicalization.md`

**Frozen SHA-256:** `BEDF2340F8473F2FDCB2E582255E4A09C42B0B9017AFAC5847FD962C2FD6AFA1`

## Approvals

- **Reviewer-agent:** Approved on 2026-07-22 after independently confirming `POLICY_MISMATCH` and
  `SNAPSHOT_MISMATCH` against their real raise sites (`launch_approvals.py:469,560` and
  `launch_gate.py:678`), confirming the IPv6-bracket and mixed-case-host regressions and the
  original-text slicing technique required at design review carried through faithfully into Task 1,
  confirming the gitignored reviewer checkpoint log matches `.gitignore:96` and reflects accurate
  state, and noting two non-blocking observations (the `_record_security_value` private-naming
  refinement, and manual interpretation needed for Task 7 Step 5's version-string grep against the
  Explicit Exceptions clause).
- **Operator:** Pending.

## Freeze Semantics

Any byte change to the implementation plan invalidates this approval and requires a new digest,
reviewer-agent approval, operator approval, and replacement approval record before implementation may
begin. Approval authorizes implementation only after this docs-only branch merges and a fresh
implementation branch/worktree is created from the latest `origin/main` — not the Plan 9.98 branch.

## Mechanical Verification

Run from the repository root:

```powershell
(Get-FileHash -Algorithm SHA256 `
  docs/superpowers/plans/2026-07-22-plan-9-99-credential-uri-security-snapshot-canonicalization.md).Hash
```

Expected exact output:

```text
BEDF2340F8473F2FDCB2E582255E4A09C42B0B9017AFAC5847FD962C2FD6AFA1
```
