# Plan 11.1 Implementation Plan Approval Record v2

**Status:** Reviewer-agent and operator approved on 2026-07-25 for the exact committed-blob
digests below. Implementation is authorized but has not started.

**Predecessor:** `docs/superpowers/reviews/2026-07-25-plan-11-1-implementation-plan-approval.md`
is retained as historical record and is explicitly invalidated. This v2 record replaces it as the
current approval authority.

**Design spec:** `docs/superpowers/specs/2026-07-25-plan-11-1-p11-feat-gateway-core-design.md`

**Implementation plan:** `docs/superpowers/plans/2026-07-25-plan-11-1-p11-feat-gateway-core-implementation.md`

**Requirement inventory:**
`docs/superpowers/reports/2026-07-25-plan-11-p11-feat-gateway-deep-requirement-inventory.md`

## Approved committed-blob digests

These SHA-256 values are over the exact bytes returned by `git show HEAD:<path>`, not an
unverified working-tree representation.

| Artifact | SHA-256 (committed blob) |
|---|---|
| Design spec | `937FB654399B8E25217B38E6450F7CF871B7CFF5C73BCB2752C044458862F7F6` |
| Implementation plan | `254A6ACC56511BBCCEB8FC101B190F213FD65450327145C88979077D845D6D3E` |
| Requirement inventory | `7DD4FA40916B2306C55492B36D37FC0178798CC20552B6E73CF13CBF5B69FDC5` |

## Approvals

- **Operator scope authorization:** The Stage 3 handoff explicitly authorized the
  `P11-FEAT-GATEWAY-CORE` specification and implementation-plan lane. That scope authorization is
  separate from approval of these frozen plan bytes and does not authorize scope expansion into
  TOOLS, COST-OBS, MCP, or parked budget enforcement.
- **Reviewer-agent:** Approved on 2026-07-25 after independently verifying all three committed-blob
  digests, worktree-equals-blob checks, zero CR bytes, inventory equivalence at 191 requirement
  rows, R3 guardrails, budget deferral, and absence of implementation changes.
- **Operator:** Vibhanshu explicitly approved these exact committed-blob design-spec,
  implementation-plan, and inventory digests on 2026-07-25.

## Freeze semantics

Any byte change to the design spec, implementation plan, or requirement inventory invalidates this
approval and requires new digests, reviewer-agent approval, operator approval, and a replacement
versioned approval record before implementation may continue. The v1 approval record remains in the
repository as invalidated history; it is not replaced in place.

This approval authorizes execution of the approved implementation plan in the existing worktree
only. It does not claim that implementation or test evidence exists, and it does not unpark
`P9.85-FU-3` budget enforcement.

## Status-line precedence

The `Pending reviewer-agent and operator approval; implementation is not authorized.` status lines
in the frozen design spec and implementation plan predate approval and are intentionally retained
to preserve their approved digests. This v2 approval record supersedes those pre-approval status
lines for execution authority; Task 0 must read this record before implementation begins.

## Task 0 shell requirement

The Task 0 verification block in the implementation plan must be run in **Git Bash** from the
repository root. It intentionally uses `sha256sum`, `cut`, and POSIX equality assertions so the
committed-blob bytes are hashed without PowerShell pipeline encoding ambiguity. The block is
read-only and must pass before implementation begins.

## Mechanical verification

Run this block in Git Bash from the repository root:

```bash
git status --short --branch
git show HEAD:docs/superpowers/specs/2026-07-25-plan-11-1-p11-feat-gateway-core-design.md | sha256sum
git show HEAD:docs/superpowers/plans/2026-07-25-plan-11-1-p11-feat-gateway-core-implementation.md | sha256sum
git show HEAD:docs/superpowers/reports/2026-07-25-plan-11-p11-feat-gateway-deep-requirement-inventory.md | sha256sum
[ "$(sha256sum docs/superpowers/specs/2026-07-25-plan-11-1-p11-feat-gateway-core-design.md | cut -d' ' -f1)" = "$(git show HEAD:docs/superpowers/specs/2026-07-25-plan-11-1-p11-feat-gateway-core-design.md | sha256sum | cut -d' ' -f1)" ]
[ "$(sha256sum docs/superpowers/plans/2026-07-25-plan-11-1-p11-feat-gateway-core-implementation.md | cut -d' ' -f1)" = "$(git show HEAD:docs/superpowers/plans/2026-07-25-plan-11-1-p11-feat-gateway-core-implementation.md | sha256sum | cut -d' ' -f1)" ]
[ "$(sha256sum docs/superpowers/reports/2026-07-25-plan-11-p11-feat-gateway-deep-requirement-inventory.md | cut -d' ' -f1)" = "$(git show HEAD:docs/superpowers/reports/2026-07-25-plan-11-p11-feat-gateway-deep-requirement-inventory.md | sha256sum | cut -d' ' -f1)" ]
git diff --check
```

Expected committed-blob output:

```text
937FB654399B8E25217B38E6450F7CF871B7CFF5C73BCB2752C044458862F7F6
254A6ACC56511BBCCEB8FC101B190F213FD65450327145C88979077D845D6D3E
7DD4FA40916B2306C55492B36D37FC0178798CC20552B6E73CF13CBF5B69FDC5
```
