# Plan 11.3 Implementation Plan Approval Record v1

**Status:** Approved by reviewer-agent and operator for the exact Plan 11.3 identity and
plan-file digest frozen below; this record is the freeze artifact for Task 0 Steps 2–3.
**Implementation authority for Tasks 1–5 is granted** as scoped in this record. No adapter
source/test evidence is claimed by this record.

This record freezes the exact Plan 11.3 implementation-plan bytes. It does not claim Tavily,
package-registry, OSV, staging Gateway, coverage, or release evidence. It does not amend or
invalidate the Plan 11.2 approval record for Tasks 0–5.

**Feature:** Real Gateway tool provider adapters (Plan 11.3 at this pickup), unblocking Plan 11.2
Task 6 staging evidence without mutating frozen Plan 11.2.

**Review baseline:** Branch `agent/cursor/plan-11-2-gateway-tools` at
`ae03c5c39691593abfa129c2b2765c946d58b71b` (Plan 11.2 Tasks 0–5 complete, including Task 5
ledger/integration lock-in). `origin/main` may lag this branch; the binding baseline for Plan 11.3
is this commit (or a later commit that still contains Plan 11.2 Tasks 0–5 unchanged).

**Parent / dependency:**

- Frozen Plan 11.2 implementation plan:
  `docs/superpowers/plans/2026-07-26-plan-11-2-p11-feat-gateway-tools-implementation.md`
- Plan 11.2 approval record (still valid for Tasks 0–5):
  `docs/superpowers/reviews/2026-07-26-plan-11-2-implementation-plan-approval.md`
- Design spec (unchanged; still authoritative for TOOLS contracts):
  `docs/superpowers/specs/2026-07-26-plan-11-2-p11-feat-gateway-tools-design.md`

**Implementation plan (this plan):**
`docs/superpowers/plans/2026-07-27-plan-11-3-real-provider-adapters.md`

## Frozen digests

These values were independently recomputed over the exact final LF-normalized bytes of the Plan 11.3
file (zero CR bytes). They are the values expected from the working tree now, and from
`git show HEAD:<path>` after this documentation batch (plan + this approval record) is committed.
They are not implementation approval by themselves; any byte change requires a replacement
versioned record.

| Artifact | SHA-256 |
|---|---|
| Plan 11.3 implementation plan | `F43883188306690AC737D6C42061D5B52A9291BF81D012DA6D9B4FD1B0750963` |

Plan 11.2’s five frozen digests remain those recorded in the Plan 11.2 approval record and are
**not** restated or altered here.

## Authoritative source pins

The four Plan 11.2 PDF pins remain binding for TOOLS contracts and are unchanged:

| Source | Version | SHA-256 |
|---|---:|---|
| `docs/Optimus-Cost-Agent-Architecture-v2.15.pdf` | v2.15 | `A386EEE8463A169A20A18B59BA923CFA80C0F6707DF7FEA3DB91B83FE3386C0B` |
| `docs/Optimus-Cost-Agent-LLD-v2.38.pdf` | v2.38 | `0471DCAE8100F41340AD6F3FE30F19B7CA8042C2949A534973B2A8D9564944DB` |
| `docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.0.pdf` | v1.0 | `4669940B34C8C0CAAB5501C193213C3087C45FAE0CBA3011E1DBF87EB74B4D0C` |
| `docs/Optimus-Cost-Agent-Test-Strategy-v1.4.pdf` | v1.4 | `6F7EB2B48447F1CE3D882FC60E16DA8B41C1DD7C926C359F45185823492DA5DB` |

## Approval state

- **Reviewer-agent:** Approved Plan 11.3 identity (sequential `11.3`, not nested `11.2.1`), sibling
  architecture preserving frozen Plan 11.2 digests, scope/exclusions, and the exact plan-file digest
  above after independent recomputation and CR/stray-reference checks. Separately approved this
  approval-record’s bytes after independent re-verification (digest match, zero CR, baseline,
  Plan 11.2 untouched, PDF pins, freeze semantics).
- **Operator (plan identity / digest):** Approved by Vibhanshu for the exact Plan 11.3 identity and
  digest `F43883188306690AC737D6C42061D5B52A9291BF81D012DA6D9B4FD1B0750963` (post-rename
  verification).
- **Operator (this approval record):** Approved by Vibhanshu after independent re-verification of
  this record’s bytes and explicit sign-off.
- **Implementation authority:** Granted for Plan 11.3 Tasks 1–5 as written (config wiring,
  Tavily/registry/OSV adapters, extract returned-URL revalidation, fitness gates). Plan 11.2 Task 6
  staging §9D, MCP brokering, and budget enforcement remain unauthorized.

## Freeze semantics

After reviewer-agent and operator sign-off on this record, any byte change to the Plan 11.3
implementation plan invalidates this record and requires new digests, fresh review, explicit
operator approval, and a replacement versioned approval record. The record must not be amended in
place to change an approved scope.

Approval of Plan 11.3 does not authorize MCP brokering, unpark `P11-FU-3`, authorize budget
enforcement, unpark `P9.85-FU-3`, mutate frozen Plan 11.2, or close Plan 11.2 Task 6 §9D claims. It
authorizes only the reviewed real-provider-adapter lane that unblocks Plan 11.2 Task 6.

## Mechanical verification

Run from the repository root after the documentation batch (plan + this approval record) is
committed:

```bash
git status --short --branch
git rev-parse HEAD
sha256sum docs/superpowers/plans/2026-07-27-plan-11-3-real-provider-adapters.md | cut -d' ' -f1
git show HEAD:docs/superpowers/plans/2026-07-27-plan-11-3-real-provider-adapters.md | sha256sum | cut -d' ' -f1
git diff --check
git diff HEAD -- docs/superpowers/plans/2026-07-26-plan-11-2-p11-feat-gateway-tools-implementation.md
```

Expected: Plan 11.3 worktree and HEAD-blob digests both equal
`F43883188306690AC737D6C42061D5B52A9291BF81D012DA6D9B4FD1B0750963`; Plan 11.2 implementation-plan
diff is empty; zero CR bytes in the Plan 11.3 file. The checkpoint log is gitignored and must never
be staged.

## Closing digest reconciliation (Task 5 closure)

Current `docs/superpowers/plans/2026-07-27-plan-11-3-real-provider-adapters.md` SHA-256 over LF-normalized bytes is:
`46CB9A791098A9D0E3A81202910949D85AD9E8AF9948A1BF008108EE51DC7D7B`.

This differs from the originally frozen digests recorded above because, per the Task 3 review,
the Plan 11.3 Tech Stack line was amended to add the intentional third-party addition `defusedxml`
to safely parse untrusted Maven XML (entity-expansion DoS hardening). Task 5 then only updates
checkbox progress markers, and no further scope or adapter semantics were changed.
\n