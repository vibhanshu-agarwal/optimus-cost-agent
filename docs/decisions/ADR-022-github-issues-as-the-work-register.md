# GitHub Issues are the work register for all non-A2A Optimus work: future intake and migration of the remaining open work

**Status at drafting (2026-10-13):** The requirement is stated and accepted by the operator: the operator's own message is reproduced verbatim below (source S8), and Codex relayed the remaining points. The mechanism below is an agent proposal that Codex reviewed for repository delivery and technically accepted on 2026-10-13, subject to wording corrections made in the same delivery. The mutable decisions index records the effective status. **Draft date:** 2026-10-13 (Asia/Calcutta). **Deciders:** the operator owns the requirement; Codex relayed it, found the conflict and reviewed the delivery; Claude drafted this record. This record does not grant execution authority. Assign the next available ADR number at filing (022 at the reviewed main, merge `c99af823`).

**Corrects:** [ADR-021](ADR-021-bounded-github-authority-switch.md), the paragraph beginning "For new independent work, retain the existing pool-first intake". Nothing else in ADR-021 changes: the 49-record switch, its mechanism, its activation and its holds stand, and the completed 49-record delivery remains valid historical evidence that does not establish completion of the broader migration. Frozen ADR-021 is not edited; the mutable index links the correction.

## Requirement and provenance

Operator, verbatim (2026-10-13, 02:41:22.999 IST; UTC 2026-10-12 21:11:22.999), from a message in Codex chat 01a1027e-9c55-7952-979b-af01fd93aa9f (source S8):

> I had clearly stated that any open items should be migrated. Why would new plans and followups be recorded in the backlog? That would defeat the benefit of migrating to Github Issues

Shared source: the Codex-produced single-message excerpt `2026-10-13-codex-work-register-operator-excerpt.json`, SHA-256 A5E20507490AC8A6D3258DB9C94BCD3EB54A4A845EB644EAE1A19106738D9AEC, in `optimus-handoff/decisions-sources/`. It contains the original response_item at line 5653 of the Codex session file (message `msg_01a131f4-b477-7df2-ad6d-30c73c402069`, timestamp 2026-10-12T21:11:22.999Z). Claude verified it independently against that session file: the excerpt's record equals the session file's line in every field, the message is a single user input text, and the quotation above is that text without its single trailing line feed. The mutable decisions index registers this explicitly scoped source as S8. It is archival provenance, not an operating, test or release dependency. The drafting date does not substitute for the message date, and the operator did not choose the mechanisms below.

Relayed wording (a labelled paraphrase, not a verbatim source): Codex's directive of 2026-10-13, pasted into the Claude session by the operator, records the operator's clarification as:

- All current open/pending/blocked Optimus work must migrate to GitHub Issues.
- All future plans, defects and independent follow-ups must be created directly in GitHub Issues. Updates belong in their existing issues.
- Documents retain scope, design, history and issue pointers, not a second live status registry.
- A2A remains deferred in its own backlog.

S8 directly grounds the first point and the first sentence of the second (open items migrate; new plans and follow-ups are not recorded in the backlog). The update rule in the second point and the whole of the third and fourth points are not in S8: they remain Codex's relay of the operator's directive and are labelled as such.

The same directive records Codex's finding that ADR-021 and the backlog explicitly retained pool-first intake, which this record corrects. The operator has accepted the issue-first requirement; this record does not ask for that acceptance again.

## Context

ADR-021 moved the status authority of 49 records to their GitHub issues and, for everything else, retained the pool: new independent work was recorded in the backlog first, and the backlog stayed the live registry for every record not marked `Moved`. The same rule was written into `AGENTS.md`, the backlog's "How to use this document", the plans folder guide, the docs index and the roadmap. The result is two live registers: issues for 49 records, and a backlog for the rest, which has since gained work filed after the migration baseline and one defect (`P11-FU-42`) filed only in an unpublished commit. The operator's standing requirement is one status authority per work record and a clean, current status view; two registers contradict it.

## Options considered

| Option | Benefit | Cost / reason |
|---|---|---|
| A. Keep pool-first intake for new work until every historical record has migrated (the ADR-021 position) | No change now | Both registers keep growing, every new item must be migrated later, and the operator's direction is not followed. Not selected |
| B. Issue-first intake for all new work, and the unfinished remainder of the open work migrated in reviewed batches; the backlog transitional | Matches the four points; one authority per record; each batch is bounded and separately approved; finished work is not turned into open issues | Each moved pool entry needs a pointer conversion, and the pool tests presently fix exactly 49 moved records, so a larger move needs its own approved, minimal accommodation. Selected as the agent-proposed mechanism |
| C. Migrate every historical manifest record at once | One step | It would create issues for finished, closed and history records, include the deferred A2A work and need a very large write volume. Not selected |

## Decision

**Requirement (the operator's clarification: verbatim in S8 for the first point and the first sentence of the second, as relayed by Codex for the rest; accepted):** the four points.

**Proposed mechanism (agent-selected; the operator did not choose these details):**

**Future intake.**

1. **New work is created as an issue.** Every new plan, defect and independent follow-up is created directly as a GitHub issue with the ADR-021 defaults unless the operator says otherwise (priority Medium, difficulty Medium, planned estimate NA, handler unassigned). Existing record identifiers are kept; a new follow-up is identified by its GitHub issue number and takes no new `P11-FU-NN`-style identifier. It takes a native parent link when its owning feature or plan is itself an issue, and named owner prose otherwise (owner prose does not by itself establish a parent). A distinct follow-up found while working gets its own issue, never a copy of another record's status. Updates to a record, its promotion into a plan and its disposition are recorded in its issue.
2. **The backlog is transitional.** It receives no new work entries: no new feature, defect, follow-up or plan entry and no new index or feature row. The one permitted addition is an issue-only plan-registry pointer: the single row that lists a new live plan in the `Live implementation plan registry` (the plan-directory contract requires every live plan to be registered) and points to the plan's issue; the row carries no status, priority, owner or next gate. For a record not yet marked `Moved` it remains the authority, for that record only, until the record's issue exists and its entry becomes a `Moved` pointer. `Moved` means authority moved, not work completed (ADR-021). An existing entry is edited only for a pointer conversion or a correction the transition needs.
3. **Documents keep scope, design, history and pointers.** Plans, the roadmap, the charter and the indexes carry no live status registry. The deferred-work custody rule in `AGENTS.md` is met by a named owning issue, or by a "Tracked, Not Yet Scheduled" roadmap entry that points to the owning issue.

**Migration of the remaining open Optimus work.**

4. **Only unfinished work migrates.** A record whose implementation is finished and merged, and whose row only awaits archival disposition, is not migrated and gets no issue. Today that is the local-hook UTF-8 decoding repair plan (merged through PR #196), Plan 11.27 v12 and the P11-FU-6 corrective plan v2 (both merged through PR #195). The distinction is recorded here; nothing is archived, moved or deleted, and each registry row stays until a reviewed archival disposition. The same applies to a delivered item inside an open program.
5. **Exclusions follow actual ownership, not product names.** The operator's deferral covers A2A: the A2A ledger and channel work, its remediation features, its audit obligations and the A2A pilot issue. Other evidence-handoff records (the evidence collector, the Zed render observation, the approval record and the redaction-gate residuals) are not A2A by their own sources; where they are unfinished, they migrate like any other open work. A record is never classified by the label the old migration manifest gave it.
6. **A completed plan with residual custody is tracked by its residuals only.** An issue for such a record opens by saying the plan is complete and lists only the custody that is genuinely open (Plan 11.30 is the current case).
7. **Historical migration evidence is preserved.** The sealed 49-record manifest, its tool and every sealed evidence folder stay unchanged. Pointer mappings for later records live in a supplementary mapping (`reports/github-work-tracking-pointers.json`) validated generically beside the sealed manifest, and the pool hygiene test is accommodated minimally; the migration framework is not redesigned.
8. **Execution groups.** Remaining work migrates in groups sized by dependencies and recovery boundaries, not issue by issue. A group states its exact payloads, its parent-first link order and the expected parent changes before any write, and the operator approves it as a unit. Verification is proportionate: exact payload and membership checks, parent changes attributable to the group's own links, preserved failures and sealed evidence. A failed or unknown write stops the group with no automatic retry or recovery. A group starts from the accepted snapshot of the one before it. Hardening work migrated only after the current status of each of its records was established from the sources at the time.
9. **A2A stays deferred in its own sections of the backlog,** with issue #225 held, until a separate decision.
10. **Frozen historical tables stay frozen.** The G6 and G7 custody tables of the backlog are historical acceptance records whose tuples are unchanged, and the hardening masterplan's board and custody tables keep their sequencing and plan-file text but are not live status; the live state of the records they list is in their issues, named in the masterplan's "GitHub issue map", which the pool hygiene test projects exactly. A record whose pool row or entry could move was converted to a `Moved` pointer instead, and the two Package A intake sections of the backlog, whose text the issues of `P11.26-CAND-5-REPEATABILITY-ATTRIBUTION` and `T13-CAND-SECURITY-TEXT` quote whole, are history pointers to those issues.

## Authority and holds

This record grants no GitHub write (creating an issue is a write and needs the operator's approval, as every earlier write did), no commit, push, pull request or merge, no migration batch, no archival, deletion or cleanup. Still held and unchanged: A2A and issue #225, writes to issue #33, label-definition changes, retention of the main-push CI logs, the P11-FU-42 lane (its unpublished commit is neither delivered nor investigated here) and all cleanup.

## Filing and acceptance items

Source S8 is registered in the mutable decisions index with its excerpt and SHA-256, and the verbatim message is reproduced above. Decisions README rule 9 and the ADR-021 index row carry the correction, and the corrected wording is kept in `AGENTS.md`, the backlog preamble, the plans folder guide, the docs index and the roadmap. The delivery that carries this record includes the bounded pool-test accommodation named in item 7: the sealed cutover keeps exactly its 49 `Moved` records and its one pin, and each later batch is validated generically against its own pin. Existing hooks and CI, and each publication approval, remain required. Once first merged this record freezes under ADR-011; later corrections or supersession use a new record.

## Migration record

Executed on 2026-10-13 under the operator's typed approvals; the A2A work and issue #225 stay deferred. The sealed evidence of each group is kept in the handoff folders named `policy-correction-11-29-batch-*-result` and `consolidated-migration-g*-result`.

| Group | Records | Issues |
|---|---|---|
| A | `P11-FU-42` (its pool entry exists only in an unpublished lane commit, which is neither delivered nor investigated here) | #287 |
| B | `P11-FU-43`, `P9.96-FU-8`, `P11.29-FU-1`, `P11.29-FU-2` and the Plan 11.30 residual custody | #288–#292 |
| E | The evidence collector feature and plan, the Zed render observation, the approval record and `P11-FU-37` (evidence-handoff work that is not A2A) | #293–#297 |
| Labels | `kind:track`, `kind:item`, `kind:candidate` (label definitions only) | — |
| H1 | The CI-guardrails track and three of its items (the lockfile item was already delivered) | #298–#301 |
| G1 | Five Plan 11.26 runtime candidates and three live obligations | #302–#309 |
| G2 | The other 14 hardening tracks, 12 items and 12 duplication candidates | #310–#347 |
