# Plan 11.30 — Claude implementation kickoff

**Date:** 2026-10-04. **Implementer:** Claude. **Architect/reviewer:** Codex. This is a static intake note, not a successor specification or progress registry. The approved plan governs; the consolidated backlog owns live status.

## Direct operator approval and assignment

Source: operator messages in Codex chat `01a10617-9940-72c0-a5e2-e3f8c3241055` on 2026-10-04.

Codex's approval question was:

> Do you approve v4 for implementation by another agent, including this staged route and the narrow CI change? Commit, push, PR and merge authorization remain separate.

The operator replied:

> Yes. Agreed as per comments above

The operator then assigned the implementer:

> Claude will implement. Please create a task kickoff note for Claude

Receive these direct operator messages in your visible intake context before mutation; a coordinator paraphrase alone is not execution authority. Implementation and plan-required verification are approved. Commit, push, PR, merge, real-host registry cleanup, paid calls and service activation have no grant from these messages.

## Read and verify before starting

1. Read the **Current State** of the local reviewer checkpoint log, `docs/superpowers/reviews/plan-11-30-review-checkpoints.md`, first, then verify it against the actual tree. It is an ignored handoff aid and is not a published Markdown link. The reviewing agent owns it; never stage it. If absent from a fresh checkout, obtain the current handoff from the reviewer and verify its rulings against the tracked plan, backlog and evidence.
2. Read [the complete approved Plan 11.30 v4](../plans/2026-10-04-plan-11-30-test-profiles-implementation_v4.md). Approved intake SHA-256: `8A40DEF6D627EDC722D9FA925BBB0C193DE433ECCB91D2DCA19F1DA6AFC5C790`. Preserve approval bytes; substantive changes require an approved complete successor. Later verified checkbox progress must not be mistaken for a new approval pin.
3. Read [the sole backlog owner](../plans/2026-07-23-consolidated-deferred-followups-backlog.md#p11-feat-test-profiles-test-cadence-selection-and-attributable-core-parallelism), `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, the evidence policy, decision index/relevant records and plan prerequisites. Use the applicable superpowers execution workflow.
4. Inspect branch, HEAD, status and worktree topology. Drafting used main `a929aab2092876ab0d83ecc4e46896ae3a0935c0`; re-pin current main for implementation. The operator's “Use current main” choice applied to drafting, not permission to share main for implementation. Resolve worktree/branch intake under AGENTS.md. Use a dedicated Claude lane based on latest main; suggested branch `agent/claude/plan-11-30-test-profiles`, agent worktree under `C:\worktrees\optimus-cost-agent-worktrees` per the evidence policy. Do not reuse another plan's branch or checkout.

**Pickup caveat:** the approved plan and its predecessor archives are currently untracked in the drafting checkout; backlog/index edits are uncommitted. A fresh Git worktree will not inherit them. Arrange a byte-identical intake copy of the approved plan and the relevant custody records, verify its hash, and preserve the existing changes. Do not assume the plan is already on main or create a preparatory commit without authorization. External research is provenance; acceptance claims require the repository-visible summary/manifest specified by Task 0.

## Start with Task 0

Execute Task 0 through **Checkpoint A**, including the narrow diagnosed fix; do not stop for a pre-coding fix approval. Establish versions, frozen environments, real WSL availability, binding inputs, package/launch inventory and relevant registry prerequisites before dependent work.

- Create the temporary core node argument file specified in the plan. Reproduce native Windows serial ACTIVE growth with coverage on **and** off, preserving default selection/root conftest and exact node-list bytes.
- Match ACTIVE/PASSIVE diagnosis in the mode that reproduces growth. Fix-check every reproducing mode. No reproduction means UNKNOWN, never a trivial no-cov PASS. Use the plan's exact ordered `at`/`seconds` gap calculation.
- Diagnose before changing the harness. Implement the narrow fix test-first within Task 0; preserve protection, attribution and failure semantics. Verify platform-shaped controls on real WSL.
- Isolate direct lifecycle registry accesses and every nested/planted child's TEMP/TMP. Develop the shared positive-ended predicate and archival dry-run/class design with Codex and the hardening owner. No host archival without an exact inventory/class grant; absent worktree alone does not prove ended.
- Prepare the single evidence report/manifest and required jointly reviewed decision provenance. Preserve source/config/node identities and all failed, INVALID, UNKNOWN and UNRUN outcomes.

Task 0 has a discovery-dependent **6–10 engineering-hour allowance**; about four initial core runs/~40 minutes are included. Extra fix checks may add elapsed time. If diagnosis exceeds the allowance, report the evidence and revised schedule; do not mask unresolved growth with xdist.

## Agreed implementation and delivery rules

- Choose the smallest additive use of existing pytest, run-context, coverage and audit mechanisms. Required functionality stays in scope.
- Windows checkpoint concurrency repeats overlap the checkpoint's coverage-free full-depth current audits in the same unchanged worktree where resources are independent, with distinct ACTIVE records and complete overlap proof. Use the separate proc lane only as fallback. WSL concurrency stays serial without load. Commit platform tests are native Windows; record WSL obligations for the next checkpoint.
- CI authorization covers existing full pytest coverage flags and per-product reporting/gates only. All other Plan 11.28 activation, cleanup and branch-folding holds remain. Local hook/report work is independent of CI wiring.
- **Stage A:** Tasks 0–3, then Task 6 for that candidate. **Stage B:** required Tasks 4–5, then a new Task 6 for its changed source. Stage A delivery does not close this plan or waive audit/xdist acceptance.
- Checkpoints **A–D: Fable 5.1, then Codex**. No intermediate full suites. Each delivered candidate retains its one serial full Windows coverage run alongside final review, full WSL gate and applicable exact-source CI evidence. Publication grants remain separate.

At Checkpoint A provide the actual diff, prerequisite dispositions, exact commands/results, reproducing-mode pre/post measurements, native lifecycle/registry controls and report/manifest references. Complete checkbox claims only after their stated commands pass. Stop early only for the plan's safety, operator-owned decision or unexpected scope/product-behavior boundaries; otherwise continue within the approved task.
