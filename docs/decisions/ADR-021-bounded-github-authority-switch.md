# Bounded GitHub authority switch for 49 Optimus work records

**Status at drafting (2026-10-12):** Proposed mechanism. The mutable decisions index records the effective status and activation evidence. **Draft date:** 2026-10-12 (Asia/Calcutta). **Deciders:** the operator owns requirements and activation/publication authority; Claude proposed the mechanism and Codex accepted its bounded design with clarifications on 2026-10-12. This record itself does not grant execution authority. Assign the next available ADR number at filing.

## Requirement and provenance

The operator requires a clean, current tabular status view, minimal repository documentation and one status authority per work record. Preserve evidence and history. GitHub Issues hold issue details; the live work-status page reads GitHub on open/reload. This is a paraphrase of operator messages in Codex chat 01a1027e-9c55-7952-979b-af01fd93aa9f.

Operator, verbatim (2026-10-11, 23:29:18.943 IST; UTC 17:59:18.943), from that chat's cutover-proposal request:

> Please draft a message for Claude to prepare the minimal cutover proposal for the 49 Optimus issues, accounting for P11-FU-42 separately. Keep A2A and cleanup on hold; no writes are authorized yet.

Shared source: the Codex-produced single-message excerpt 2026-10-11-codex-cutover-operator-excerpt.json, SHA-256 D79F6A29713E7EC054F5BE567634F07D57001193269FEE171234364747964AF8, in optimus-handoff/github-issues-migration/. It contains the original response_item at source line 3184, timestamp 2026-10-11T17:59:18.943Z. Register this explicitly scoped source in the mutable decisions README (proposed S6; confirm the next source id at filing). It is archival provenance, not an operating/test dependency. Claude independently verifies the quoted content. The drafting date does not substitute for the message date, and the operator did not choose the mechanisms below.

Related governance: ADR-011 and the decisions index govern provenance, joint review, publication and first-merge immutability. No frozen ADR is changed by this record.

## Context

Plan 11.29 delivered the migration tool and live table through PR #282, merge cb959a38, and the scoped tool adjustment through PR #284, merge d3114bea54d742abffcf104b630cb7104301de15 (fixed cutover base C). At cb959a38, the accepted staged Optimus set contained 49 records and implementation delivery had not switched authority. The consolidated backlog still owned their status at that commit. Activation of this proposed mechanism is the separately operator-approved cutover merge, not the earlier implementation delivery.

The historical migration manifest covers a larger population. Completing that entire manifest would expand scope. Replacing the entire pool with a global authority stub would also leave other live work without discoverable custody. Frozen status mirrors would retain clutter and stale status representations.

## Options considered

| Option | Benefit | Cost / reason not selected |
|---|---|---|
| Entire-manifest migration and global pool stub | One global authority | Exceeds the 49-record scope and involves held work |
| Keep detailed frozen mirrors for the 49 | Fewer docs-check changes | Retains clutter and stale status text beside live GitHub status |
| Per-record switch with compact issue pointers | Removes migrated detail from the live pool while retaining history and other live work | Requires bounded pointer-aware checks and scoped validation; selected |
| Adopt only 48, leaving #232 pool-owned | Avoids a hardening owner edit | Changes the agreed set and leaves a needless split; not selected |

## Proposed decision

Only the accepted 49 records change authority. The repository-visible finalized mapping identifies them exactly: seven plans, six features and 36 follow-ups. Each maps to one GitHub issue. #33 and #225 are outside this switch and remain untouched. No new issue is created by it.

After the authorized cutover merge, GitHub issue state, status/priority/difficulty/estimate/handler metadata and issue details own these records. Closure still requires the accepted completion/disposition criteria; a PR merge alone is insufficient. The operator-specified defaults remain Medium priority/difficulty and NA planned estimate. The existing unassigned handler default is retained; it was an agent-selected mechanism. No new defaults are introduced here. The live table is the status view, refreshed on open/reload, not a separately maintained status source.

The pool retains each migrated identity/title, heading/anchor, issue pointer and pinned link to historical detail. It no longer repeats their live status or full issue narratives. Moved means authority moved, not work completed. Unmigrated records retain their existing live custody in the pool and governing masterplan boards. Do not retire them merely because they are outside this batch.

For new independent work, retain the existing pool-first intake until a later explicitly approved migration changes it; there is no automatic issue creation under this 49-record cutover. Updates to a migrated record belong in its existing issue. A distinct follow-up is a new pool record with an appropriate owning/related entry, not a second copy of that issue's status.

Issue #232 becomes the hardening program feature's status owner; the masterplan continues to own its existing child-plan boards, sequencing and obligations. Issue #275 owns FU-30 status/acceptance. The other migrated feature pointers are consistent with this boundary. The existing PR gate and hardening obligations remain; the authority-change PR uses the truthful updated declaration.

## Agent-selected mechanism and trade-offs

Codex selected the uniform 98-update sequence proposed by Claude: 49 pre-merge updates, then 49 post-merge updates, with no creates or bindings. This is not an operator grant. Pre-merge updates adopt the three Optimus pilots, make the two reviewed source corrections (including #237 Active), and give every selected issue neutral authority wording. After merge, final updates remove the trial banner and shadow-pilot label. The extra banner edits make the meaning truthful if finalization stops midway.

Historical a929aab quotes/permalinks remain historical. The sealed migration manifest may hold reviewed status_current and source_updates fields solely as one-time expected migration state and dated source evidence. They are not maintained as another status registry. After final acceptance, normal issue updates must not be overwritten from this historical manifest.

A scoped reconcile/plan/finalize validates exactly the 49 while preserving global source-marker integrity checks. A clean scoped mapping does not make the unscoped reconcile pass: pending-record and #225 findings remain separately reported as failures. Out-of-scope issues receive no writes. Invalid scope, conflicting identity, unexpected drift or unknown write outcome stops the applicable step; no retry-to-green or recovery write is authorized automatically.

## Switch and incomplete-finalization semantics

The scoped tool adjustment was delivered by PR #284, merge d3114bea54d742abffcf104b630cb7104301de15. Cutover base C is fixed at that commit; the source/issue assessment at C is complete and retained separately. Recheck drift against C, review the exact real-tool batches and obtain the operator's execution grants before execution. If main advances, report the drift rather than silently moving C. Partial pre-merge batches have explicitly expected remaining findings; all 49 must reconcile cleanly before the authority-switch PR is accepted.

The operator-approved cutover PR merge is the switch point. Before it, the pool owns the 49. After it, their issue pointers govern, including if some neutral trial banners remain. If post-merge writes stop, report "switch complete, finalization incomplete", retain evidence and identify the remaining issues. Do not revert authority implicitly or claim Plan 11.29 complete. Further writes need the applicable fresh authority.

## Authority and holds

Operator requirements and the already accepted staged-set boundary are settled. The mechanism here is an agent design pending operator implementation/execution authority. This ADR does not authorize code, hooks/test runs, commits, branch delivery, PR creation, merge, issue updates, closure or cleanup. Technical acceptance and each publication/activation decision remain distinct.

A2A migration and #225 remain held with existing live custody. #33 is untouched. P11-FU-42 filing delivery and GitHub migration are separate proposals, not prerequisites to these 49. No general cleanup, archival move, branch/worktree removal or evidence deletion is included.

## Filing and acceptance items

Claude reviews this draft with Codex before repository delivery. Verify the excerpt/hash and register its source, allocate the next ADR number (021 at the reviewed main; re-check at filing), and include the mutable authority wording in the reviewed cutover diff. In particular update decisions README rule 9 and its Plan 12.2 publication/next-gate sentence, the corresponding AGENTS.md sole-registry clauses, and the agreed README/index/pool wording. Frozen ADRs remain unchanged. Actual tool regressions, pointer-aware checks, unchanged gate behavior and exact payloads must be accepted at the implementing commit; prototype simulations alone do not satisfy those gates. Applicable hooks/CI and publication approvals remain required. Once first merged, this record freezes under ADR-011; later corrections or supersession use a new record. A Proposed status at drafting is historical and does not forbid freezing a Proposed record. Before the authorized switch merge, record the actual operator acceptance in the mutable index. Its row identifies activation as the merge of the PR that introduces this record and the reviewed authority-switch changes; the post-merge verification evidence records the actual merge hash. Keep post-merge finalization as an open item until verified. No extra documentation PR is required merely to insert that hash. Publication alone does not fabricate acceptance or authority.
