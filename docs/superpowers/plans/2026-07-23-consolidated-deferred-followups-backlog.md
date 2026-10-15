# Consolidated Open Work Pool

## Purpose

This document is a transitional register ([ADR-022](../../decisions/ADR-022-github-issues-as-the-work-register.md)). GitHub Issues are the work register: every
feature, plan, defect and follow-up has its status, priority, owner and next gate in its issue. This document owns those facts, and
each item's existence, only for the records that have not moved to a GitHub issue: charter-ratified feature slices, deferred
follow-ups, parked items and tracked defects that stay deferred, closed or historical: the A2A work, finished records awaiting archival disposition and the frozen custody tables. It takes no new work entries; the one permitted addition is a new plan's issue-only registry pointer row. The relevant charter or
source document owns scope, sequencing, and detailed acceptance criteria. Anything that is neither listed here nor an issue is not
tracked as Optimus work.

**Authority boundary (Plan 11.29).** A row or entry marked `Moved` has its authority in the linked GitHub issue: status, priority,
owner and next gate. This document keeps only that pointer, the anchor and a pinned link to the former detail. A `Moved` pointer is
never evidence that the work is closed. Every open non-A2A record has its issue. The frozen G6 and G7 custody tables below keep their historical tuples unchanged, and the hardening masterplan's board and custody tables keep sequencing and plan-file text only;
the live state of the records they list is in the issues named in the masterplan's "GitHub issue map". The A2A work stays deferred here in its own sections.

**Live view and fallback.** The hosted [work status table](https://vibhanshu-agarwal.github.io/optimus-cost-agent/work-status.html) (source: [`docs/work-status.html`](../../work-status.html), which also opens from a checkout) reads the
repository's GitHub issues on every open and reload; the fallback is the [open issues on GitHub](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues?q=is%3Aissue%20is%3Aopen).

Before this document existed, each follow-up lived only inside the "Deferred Follow-Ups" section of
whichever plan originally raised it, cross-referenced (if at all) by a one-line mention in the
roadmap. Two of them (Plan 9.98-FU-1 and FU-2) were fully implemented and merged without ever
getting a roadmap entry at all, discovered only by manual audit. This document exists so that stops
happening: everything still open lives in exactly one place (its GitHub issue; this document only for the deferred A2A work), and
nothing gets promoted into a real plan without its issue or entry recording the promotion first.

This document does not itself implement anything. Every open entry below either becomes its own
numbered plan (following [[plan-numbering-convention]]-style sequential allocation) or gets folded
into an already-designated future plan (e.g. Plan 12 or a reviewed Plan 11 feature slice) when that plan is actually
scheduled. The roadmap's Plan 11 v1.0 milestone section links here; it does
not duplicate this content.

## How to use this document

- **Adding a new item:** Do not add it here ([ADR-022](../../decisions/ADR-022-github-issues-as-the-work-register.md)); the only line that may be added is an issue-only registry pointer row for a new live plan. When a plan's implementation or review surfaces a new
  deferred follow-up, defect or independent piece of work, create it directly as a GitHub issue carrying the same facts every entry here
  carries (origin, designated owner or plan, trigger or acceptance criteria, status), using the migration defaults unless the operator
  says otherwise. A distinct follow-up gets its own issue, linked to its owner, never a copy of another record's status; an update to a
  moved record is made in its issue. Other documents may link to the issue but must not carry its live status or become a second
  register. An entry that is still here is edited only for a pointer conversion or a correction the transition needs.
- **Using status tokens:** Make the first text after `**Status:**` exactly one of these five
  canonical forms, terminated by a period or colon: `Open`, `Promoted -> <markdown link to a file
  under docs/superpowers/plans/>`, `Partially implemented`, `Closed`, or `Reviewed disposition`.
  Free prose may follow the terminating punctuation. `Partially implemented` means merged work
  advances this entry's own acceptance criteria, not merely that work exists in the owning lane. `Moved` is a pointer, not a status
  token: a `Moved` row or entry carries no status here, its issue does, and the pointer never means `Closed`.
- **Promoting an item:** When an item is scheduled into an implementation plan or a complete
  versioned successor (`_v2`, `_v3`, and so on), mark its Status as `Promoted -> <linked plan>` with
  the date, and leave the entry in place
  (do not delete history) rather than removing the row. A `Moved` record, and any new work (which has no entry here), is promoted in its issue.
- **Closing an item:** When an item is fully implemented, mark Status as `Closed` with the
  implementation commit/PR and evidence citation, the same way other closed follow-ups are recorded
  elsewhere in this project's roadmap. A `Moved` record, and any new work, is closed or given its reviewed disposition in its issue, against the same criteria.
- **Applying the v1.0 pool-closure gate:** Only `Closed` and `Reviewed disposition` satisfy the
  gate. `Open`, `Promoted -> ...`, and `Partially implemented` remain incomplete for that purpose. A `Moved` record never satisfies
  the gate from this document; it counts once its issue is closed with the evidence the criteria require.
- **Reading frozen artifacts:** Approval-time status and checkbox text inside a protected artifact
  is historical. The protected-artifact list below identifies the live pool row (or, once that row is `Moved`, its linked issue)
  that owns current
  state; never reconcile that state by editing the approved bytes.

## Live implementation plan registry

This table is the sole list of implementation plans that remain live at
`docs/superpowers/plans/`. `Active` means execution may proceed under the plan's own authority;
`Blocked` means the obligation remains live but its next gate is unsatisfied. A blocked plan stays
at the root. Terminal and superseded plans live in the flat `archive/` directory and never appear
in this table. A `Moved` row keeps its plan listed here; its state and next gate are in the linked issue.

| Plan | State | Backlog owner | Next gate |
|---|---|---|---|
| [Plan 11.31 — Closed state ID lifecycle port](2026-10-15-closed-state-ids-port_v4.md) | — | — | [#357](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/357) |
| [Plan 11.29 — GitHub Issues migration and live status view](2026-10-04-plan-11-29-github-issues-migration.md) | Moved | — | [#236](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/236) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L58-L58) |
| [Plan 12.2 — Context Engine](2026-10-01-plan-12-2-context-engine-implementation_v4.md) | Moved | — | [#237](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/237) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L59-L59) |
| [Plan 12.1 — Plan/Chat advisory answer](2026-09-29-plan-12-1-plan-chat-advisory-answer-implementation.md) | Moved | — | [#238](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/238) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L60-L60) |
| [Local-hook UTF-8 decoding repair](2026-09-06-local-hook-utf8-repair.md) | `Blocked` | `P11-FEAT-ACP-RUNTIME-HARDENING` | Local delivery at `c9745898` is independently accepted and published to PR #196 with both first-execution checks passed. The operator authorized documentation review and normal merge conditional on the final head passing required checks; PR #196 records the result. Retained under transitional custody pending separate archival disposition; no further implementation or inherited budget is released. Preserve baseline identities, frozen documents and CI scope. |
| [Plan 11.27 v12 — integrate accepted correction and deliver locally](2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v12.md) | `Blocked` | `P11-FEAT-ACP-RUNTIME-HARDENING` | Delivery and publication complete: local integration `2bd316bc`, merged via PR #195 at `32f32ef4`, with independent local/CI acceptance and restored protection. Retained at the root under transitional custody; the remaining gate is the separate archival/custody disposition. No further v12 execution or inherited budget is available. Scanner decoding repair remains with the backlog owner. |
| [Plan 11.28 — Parallel local test context](2026-10-02-plan-11-28-parallel-local-test-context-implementation.md) | Moved | — | [#239](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/239) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L63-L63) |
| [P11-FU-6 — bounded early POST rejection corrective plan v2](2026-09-05-p11-fu6-bounded-early-post-rejection_v2.md) | `Blocked` | `P11-FU-6` | The bounded early-POST correction is delivered and merged through PR #195 at `32f32ef4`. The corrective plan remains frozen under transitional custody pending archival disposition; `P11-FU-6` remains Open for separately defined broader reliability closure. No additional product behavior, installation or rollout is authorized by this status update. |
| [Plan 11.7 v3 — Zed Resume](2026-07-29-plan-11-7-p11-feat-zed-resume-implementation_v3.md) | Moved | — | [#240](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/240) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L65-L65) |
| [Plan 11.24 v6 — guided session-load probe](2026-08-18-plan-11-24-zed-guided-session-load-probe_v6.md) | Moved | — | [#241](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/241) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L66-L66) |
| [Plan 11.23 — client-MCP runtime composition](2026-08-18-plan-11-23-p11-fu-20-client-mcp-runtime-composition.md) | Moved | — | [#222](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/222) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L67-L67) |
| [Evidence collector](evidence-handoff-evidence-collector-implementation.md) | Moved | — | [#295](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/295) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/c99af82365b83eccc6fdb24525cafd2a064c9f09/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L81-L81) |

**2026-09-06 current outcome — Plan 11.27 integration delivered and merged; broader FU-6 remains Open.** The accepted Slice A and Slice B production CI scanning work, together with the bounded early-POST correction, were delivered locally at `2bd316bc` and merged through [PR #195](https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/195) into main at `32f32ef4`. The resulting tree is the independently accepted integration tree. The first PR CI run and the post-merge main CI run passed. Local Windows actual-commit coverage was 86.16%; each GitHub Linux run reported 85.47% for the existing `optimus` coverage gate. These are separate run results, not whole-repository coverage or a universal reliability claim. The temporary `verify` exception was closed immediately after merge, and the original protection was independently verified as restored.

The delivery and publication gates described as pending in the earlier dated records below are complete. Those records remain historical custody, including failed attempts and the previously disclosed loss of two derived correction summaries. The eight-document local-hook decoding limitation remains accepted and disclosed: default CP1252 scanning skipped v2-v8 and FU-6 v2; supplementary UTF-8 evidence found 25 reviewed non-credential values in v2-v8 and found FU-6 v2 clean. Repair remains separately owed. Broader FU-6 closure, recognition-route hardening, local installation and rollout are not established by this merge. Frozen predecessor plans remain unchanged pending their separate archival-custody disposition.

**Plan 11.27 scheduling custody (2026-09-04):** the bounded pickup under
`P11-FEAT-ACP-RUNTIME-HARDENING` covers central Git-test immunity, the explicitly scoped
sanitization-test response-before-EOF port, and required CI scanning of every tracked production
text file. It targets an independent main-based clone on C:, not the never-merged sandbox or
the preserved, dirty linked CI worktree. Its first proposed commit has three prerequisite test
files; its second has seven scanner files and bounded documentation. Main's baseline and
local-hook coverage remain unchanged. The parent hardening entry remains Open: this approved plan is
not a promotion or closure of the entire architecture-audit obligation.

Claude conditionally approved v2, requiring post-cancel task settlement (F1) and explicit Git-blob
hash domains (F3). The complete v3 also protects cleanup when reader close fails and preserves
the primary response error (F2). It retains the 180-minute cap, with a stop during Task 2 or 3
the conservative scheduling assumption, never a reason to skip a gate. V3 received execution
authority and is now stopped at the portability finding below. V2's reviewed bytes remain at their original location pending the required mechanical
archival path proof; this custody step must not alter frozen prose or leave broken links.

**Technical approval recorded:** Claude approved v3 at SHA-256
`dec4163fb294bfe56805ee6b1d245d25c1904b8424c2e567b90e94bb84168800`, closing F1/F2/F3
with no remaining findings. Claude's independently repeated helper probes are attributed to
Claude; they validate the proposed helper's control flow, not the real server port or the future
implementation. Task 1 still owes that real acceptance evidence. Technical approval alone did
not start implementation, spend the execution box, or authorize publication.

**Operator go recorded, 2026-09-04 15:48:39 UTC:** Vibhanshu's direct instruction was,
"Whose approval? If my approval is needed, I approve". This grants the requested independent
clone, isolated locked Windows/WSL tool downloads, and two local commits after their required
reviews and actual full Windows hooks. No repeat confirmation of that original grant is needed.
The 180 combined agent-minute execution budget is authorized from this go: count all work
under it, including setup and review, and record actual pickup time/attribution without resetting
the allowance at handoff. Waiting for an agent to pick up is not agent work; elapsed time is
recorded separately as the plan requires. Claude implements; Codex reviews. The approval itself
did not certify execution; the subsequent stopped run is recorded below.
Push, PR publication, merge, installation and fresh FU-6 revalidation remain withheld. All
pre-decided stop conditions stand; no re-asking is needed for the already authorized actions.

**Prior Task 1 stop / v4 proposal, 2026-09-04:** Claude started at 15:52:54 UTC and reports
16 minutes spent. The independent candidate remains at the bound base with exactly three
Slice A files and no commit. The bound 112-line test's `bare = true` assertion fails with
Linux Git even though identity contamination occurs. Codex reproduced this in Linux-native
temporary files. V4 proposes only replacing that assertion with explicit config-hash inequality;
full protected-state equality and the `Probe` assertion remain unchanged. The corrected file
hash is `ba5a5329dcf5936fe004fed8dbb3a6addb196a4ac0f420dc165261df4b764619`.
In Codex's disposable complete exports, all five corrected cases pass on each OS; removing
protection and replacing the injected identity each fail their intended assertions on each OS.
This is proposal evidence, not a completed Slice A/full-hook claim. All post-go review work
counts against the same cap; Claude's quoted 164 minutes is not the combined remaining balance.
The v4 approval request is solely the exception to v3's exact source binding and its resume
contract, as required by plan-fidelity rules. Existing clone/setup/local-commit approval stands.
Claude's original candidate, failed output and v2/v3 bytes are unchanged. V4 explicitly resumes
the existing owned clone after live checks; no re-clone, clock reset, gate waiver or new FU-6
grant is implied. Actual affected-file Windows/WSL gates, rehearsal, review and commit remain.

**Current Slice A review / v5 proposal, 2026-09-04:** Codex verified the corrected candidate
against independent rehearsal commit `192fe1d3ae87eebffc1b89bc26673a401d1f6a5e`, parent
`5ea8f8f71548eb05a8562a10e98667e3d2061c4d`, tree `258406df199720d19dbdd1f2640567f4f9aca4a8`.
The candidate itself has no later commit and exactly three Slice A paths. Codex independently
ran the actual two files on Windows and WSL (17 passed each), Ruff, six actual-helper failure
controls and a real-server acknowledged barrier proving response-before-EOF in both sanitizer
modes. The successful rehearsal log has eight applicable hooks passed and two skipped; its
retained coverage database reports 86.08026323520771%, distinct from the failed rehearsal's
86.16%. Codex did not rerun the full hook or infer a passing test count from the failed suite.

The two plan defects are confirmed: a historyless rehearsal lacks historical objects required
by doc gates, and raw evidence under ignored `tmp/` is still scanned by those gates. V5 replaces
only the full-hook rehearsal construction with a complete independent clone at the exact parent
and requires raw custody outside tested trees. Its scope also adopts the existing v4 one-line
correction; no operator approval of that specific exception has yet appeared in the review
conversation, so Claude's technical concurrence is not recorded as such approval. The reviewed
evidence folder lacks the actual runner's exit-7 control and a separate original PATH-failure
record. Claude must locate/seal retained originals and relocation hashes, or disclose unavailable
bytes for an explicit disposition; no historical re-execution or blanket preservation claim.
No new implementation defect was found, but commit concurrence remains held for the v5 decision,
evidence seal and actual commit hook. Original go, file scope and combined 180-minute cap stand.

**Prior custody review, 2026-09-04:** Claude disclosed that retrying overwrote the first
PATH-failure log. Codex recommends accepting this one irrecoverable setup-log gap explicitly,
with the historical diagnosis remaining Claude-attributed; no recreation, substituted artifact,
complete-preservation claim or additional recovery search is needed. This recommendation is not
the operator's disposition. V5 already defines that decision path and remains byte-unchanged.
The new 32-entry manifest matches every current file, and all 28 files hashed in Codex's prior
review are unchanged. Recovered WSL controls fail their intended assertions.

The new commit-control claim is unsupported: `runner-negative-control-commit.log` contains only
pre-commit's unstaged-configuration error, and the disposable control still has its config
unstaged. The injected exit-7 hook never ran in that commit attempt. The standalone hook log
does show exit 7, but does not itself record the caller command or parent exit. Seal the actual
required-runner invocation and its propagated nonzero exit; no optional full-suite commit
negative control is required by v5. If retaining that extra claim, correct its fixture setup
and obtain evidence that reaches the intended hook. Keep the rejected control as failed evidence.

**Current runner review, 2026-09-04:** The corrected commit-control log now contains the injected
hook's exit 7; the disposable control's config is staged and has `fail_fast: true`, and HEAD
remains `192fe1d3...`. The log stops before the full suite. Parent exit 1 is attributed to
Claude's recorded execution; Codex inspected the artifacts/state without rerunning the control.
The current 32-entry manifest matches all files. The retry reused the earlier control filename,
but Codex recovered that earlier log and manifest from its prior captured output, reproducing
their previously recorded SHA-256 values exactly. Both versions now survive under external
review custody (`runner-control-custody-r2`), so this introduces no second missing-log gap.
The causal runner finding is closed.

**Operator approval recorded, 2026-09-04 17:52 UTC:** the direct reply "yes approved"
approves complete v5 (`f71006d3...`) and accepts the single irrecoverable original
PATH-setup log gap as disclosed. The historical diagnosis remains Claude-attributed;
this is neither recovered evidence nor a complete-preservation claim. V5 and all three
reviewed candidate file hashes remain unchanged; the candidate is still uncommitted
at the bound base. Claude may run its actual required full Windows commit hook,
without another optional rehearsal, code review or approval request. Reconcile the
remaining combined 180-minute balance first; no reset or expansion is authorized.
A new failure or drift invokes the existing STOP rules. Push, PR, merge, installation
and any fresh FU-6 revalidation remain withheld. Frozen predecessors remain byte-exact
pending their already-recorded mechanical archival custody; no plan bytes were edited.

**Slice A commit review, 2026-09-04 18:15 UTC:** candidate HEAD
`c1989985171c3054916732f1306d5ffc85d5b094` has the bound parent and tree
`258406df199720d19dbdd1f2640567f4f9aca4a8`, equal to the approved rehearsal.
Exactly the three reviewed paths changed; the candidate is clean and untagged. The
actual commit log records eight applicable hooks Passed and YAML/TOML Skipped; all
33 current external-manifest entries match. The hook-created `.coverage` database,
SHA-256 `da133c6b12c6780bbdc4a768a25c635ac8aa921110c67627d19e540f4d469a4e`,
remains only in the candidate and is absent from external custody. V5 requires that
database/report to be preserved when passing-hook stdout is suppressed. Claude must
seal those existing bytes under a fresh external name and update its manifest before
another hook can overwrite them; no suite rerun is needed. The shared-ledger derived
header is also stale and remains Claude-owned. Until those custody items are closed,
record the commit as landed without a formal Task 1 completion claim. The budget STOP
before unstarted Slice B is correct; Tasks 2-4 require a separately scheduled bounded
box. Push, PR, merge, installation and fresh FU-6 revalidation remain withheld.

**Slice A custody closure, 2026-09-04 18:25 UTC:** external
`a-commit-coverage.data` is byte-identical to the candidate's hook-created `.coverage`,
SHA-256 `da133c6b12c6780bbdc4a768a25c635ac8aa921110c67627d19e540f4d469a4e`.
Codex independently read the sealed copy without rerunning tests and confirmed TOTAL
13497 / 1456 missed / 3522 branches / 609 partial / 86.23%. The external report hashes
to `b25b579584acee5ffffd3fd6693c5d0b91dca78efeb514d0de5a4a55d7c9f76f`;
all 35 entries in manifest `6522ecf5...` match. The separate 86.08% figure belongs to
the successful rehearsal run, so both figures remain correctly attributed. Candidate
is clean and the shared-ledger header is current. Task 1 evidence is complete.

**Slice B Task 0 review, 2026-09-05 03:54 UTC:** v6 execution began at
03:34:53 UTC under the separately approved 120 combined-agent-minute box. Candidate,
isolation, canary, pins, toolchains and external custody substantively pass; Task 2 is
released. The immutable Task 0 log mislabels proposal digest `0ba9...` as approved:
final digest `83a8...` was approved after the required JUnit clarification. Preserve
the log and add a freshly named correction artifact to the external manifest; update
shared `CURRENT.md`. No rerun or v7 is required. Windows Git 2.55 and WSL Git 2.43
are accepted per-platform identities, and invocation-scoped MSYS path-conversion
suppression is accepted with exact command/script evidence. The reported 107.2-minute
balance precedes Codex's review charge. Recalculate at each boundary; Task 4 must not
start unless all 40 minutes can fit. Publication and any fresh FU-6 revalidation
remain withheld.

**Slice B Task 2 review, 2026-09-05 04:16 UTC:** the current three-file diff
matches sealed patch `4d3cdf8d...`; all 14 external manifest entries match, and the
recorded Windows/WSL results are 13 passed on each platform. Task 2 remains open.
The timeout helper kills only its shell then re-enters unbounded `communicate()`, the
required per-binding fixture mutants are absent, and the selection fixture stages the
files it calls untracked while providing no ignored control or representatives for
all actual source packages. Correct these three requirements with targeted controls
before Task 3. Add a fresh custody correction for the two `T035500Z` MSYS filenames,
whose content records the actual rerun at 03:58:29Z; preserve all earlier bytes.
WSL uv 0.11.31 is accepted as observed platform state. The 85.6-minute balance was
measured before Codex review; recompute after Task 2 closes and stop before any later
mandatory task that cannot fit whole.

**Slice B corrected Task 2 review, 2026-09-05 04:38:57 UTC:** live patch d5df1171... matches the sealed bytes; all 22 manifest entries match. Selection controls and additive MSYS timestamp correction are accepted. Task 2 remains open: bound tasklist/failure teardown and ensure fallback reap if tree-kill fails; reject job-level continue-on-error and pin the full approved hook entry/settings with independent mutants; verify both fixture Git directories before writes. Platform logs record 22 passed each; Codex inspected logs without rerunning tests. Prior post-go Codex active turns total approximately 15.2564 minutes, plus this review beginning 04:34:37 UTC. Claude's elapsed-since-go figure does not distinguish relay idle; active intervals requested before the Task 3/4 budget decision. Task 3 remains held; no publication or fresh FU-6 authority.

**Slice B second corrected Task 2 review, 2026-09-05 04:48:12 UTC:** 0b9d2e6c... matches live bytes; 27 manifest hashes verified; Claude logs record 26 passed on each OS. Binding accepted. Timeout-control teardown still begins after the invocation/expectation, poll does not establish bounded reap, and the requested common-directory escape control remains absent. Correct those existing requirements with targeted controls. Task 3 held. Claude's 68.8 upper bound ends before final reporting; conservatively charge 70.7667 through relay receipt at 04:45:39, plus subsequent active work. Prior Codex turns total 20.0532 minutes; current review starts 04:45:39. Recompute before entry and stop if the complete 25-minute Task 3 cannot fit; Task 4 still needs 40. Frozen v6 and publication/FU-6 boundaries unchanged.

**Slice B Task 2 acceptance and STOP, 2026-09-05 06:30:52 UTC:** final live patch bff2b1a... equals sealed bytes; all 34 manifest hashes match. Remaining timeout/containment findings closed from code and Claude's Windows/WSL 29-passed logs; prior WSL injected-failure log retained. Codex did not rerun tests/Ruff. Slice B stops before Task 3: about 21.7 conservative minutes remained before reporting/review, below the complete 25-minute gate. Relay idle is excluded; this is a gate stop, not an exact exhaustion claim. Three-file delta is accepted but unstaged/uncommitted at c1989985. Tasks 3/4, production dispositions/evidence, README, final audit/custody/rehearsal and enforced local commit remain owned here. Await operator scheduling; frozen v6 is unchanged and cannot silently reset. No publication or fresh FU-6 authority.

**V7 execution release, 2026-09-05 06:55:22 UTC:** operator approved execution and the recommended new 75-minute box (10 successor/pickup, 25 Task 3, 40 Task 4), beginning with Codex turn 06:48:50. Complete v7 sealed at 9e05956c971310cbf9f6b31600c054e6172bdc4f29d98ddc0c63b2eb70d22b1b; Task 3 is byte-exact to v6, frozen v6 unchanged, 57 plan/registry checks pass. Accepted Task 2 patch/custody and baseline/lock/shared-config pins verify. Claude completes Task 0 pickup then Task 3 if its whole gate fits; Task 4 needs all 40 minutes and final reviewer concurrence. No old-box reset, publication or fresh FU-6 grant.

**V7 environment incident, 2026-09-05 07:16:18 UTC:** live candidate .venv is Linux after WSL uv replacement; WSL production step exited 1. Codex independently verified four annotation ASTs/docstring, three SQL hashes, 47 evidence hashes, exact partial patch 012f1e99..., accepted Task 2 subdiff and baseline/lock/canary invariants. Partial source accepted; Task 3 incomplete and Task 4 blocked. V8 proposal d41d6ba0... requests only preservation, one offline locked Windows rebuild and pinned no-sync WSL retry under the existing 75-minute box; no repair executed or authorized. Full 40-minute Task 4 gate and publication/FU-6 restrictions remain. Await operator approval.

**Recovery and Task 3 review, 2026-09-05 07:31:54 UTC:** exact b54da0a4... final patch and 55 hashes verified; AST/docstring/SQL and Task 2/invariant pins unchanged. Windows environment restored, Linux replacement preserved externally, WSL retry exit 0 with pinned no-sync environment; logged inventory sets equal at 200. Recovered Windows records 144 passed; Codex inspected without rerunning. Task 3 technically accepted; Task 4 held. Operator Option 1 approval is quoted in Claude's ledger but original message absent from this conversation. Preserve unrevised v8; do not backdate a revision or treat removal of its 40-minute reservation as mere subset execution. Resolve actual approval custody separately from technical acceptance.

**Option 1 approval confirmation, 2026-09-05 07:35:07 UTC:** operator directly confirms he relayed approval after Codex recommended Option 1. Recovery and Task 3 execution were authorized; approval-record issue closed without repeated approval or backdated v8 editing. Task 4 remains separately gated and deferred.

**Task 4 execution release, 2026-09-05 07:43:17 UTC:** operator approved the separate 40-minute box; entry at 07:36:45 with Codex final-document/contract preparation counted inside Task 4. V9 sealed at 823f269c05f9251b6594635a4881c23edb74ded3382469655f788c3b50cfb3dd; 57 plan/registry checks pass, candidate b54da0a4... and 55 evidence hashes unchanged. Claude continues the same box for final custody/rehearsal, with Codex concurrence before actual full-hook local commit. No second 40-minute allowance, old-box reset, publication or fresh FU-6 grant.

The [original stopped Plan 11.27 scratch draft](archive/2026-09-03-plan-11-27-git-test-immunity-and-production-secret-scan.md)
is superseded as a proposal by the complete successor series; its archived copy preserves SHA-256
`4900776b5332a061a148b3ad35db9fa2cfe539504c458eb7b5bca48d5a603751`. Historical execution
authority and failed evidence are not rewritten. A new FU-6 hit stops and needs a new recorded
per-hit P1; the previous grant is spent. `P11-FU-6` and `P11-FU-7` retain their existing
statuses and separate closure gates. The EOF port does not claim either closure.

After this CI package, the next bounded static-analysis proposal remains focused production
S110 enforcement under `P11-FEAT-ACP-RUNTIME-HARDENING`. Both outbound-writer dispositions
must preserve future settlement and worker survival; no broad Ruff selection is enabled here.
That same parent owns broader scanner/baseline migration, PR #194 collision, guardrail tension,
unexplained watchdog-assertion disposition and shared-cache repair. `P11-FEAT-ZED-RESUME`
continues to own WP-27 runtime/live evidence. Publication, main CI activation, merge and
installation remain separate operator gates; local delivery alone will not close them.

**Current Zed Resume position (accepted runtime lane, 2026-08-28):** runtime commit
`fac32284888850bacde93815265cbabe3afd4663` and its independent R9/V2 reviews are accepted. Real
Zed 1.16.3 resumed a non-empty session with ordered replay before success, no replacement
`session/new`, and continuation on the same durable ledger. Raw Optimus stdio emitted every replay
frame; acpx does not display load-time replay. Zero-entry load fails closed with `INVALID_REQUEST`.
Current Zed UI close abruptly terminates the wrapper and child without orderly stdin EOF, so the
normal close path does not reach `aclose()` / `store.release()`; immediate reopen can therefore
return `SESSION_BUSY` until the exact 300-second lease expires, after which recovery succeeds.
The ruling is **`DEMO_READY_UNSEALED — CURRENT ZED CLOSE RECOVERS AFTER BOUNDED LEASE EXPIRY`**.
It always carries these limitations: acpx replay visibility is not demonstrated; current Zed does
not provide graceful agent shutdown; immediate reopen can remain busy for up to 300 seconds; and
Task 0, formal evidence, release, push, merge, backlog closure, and Plan 11.7 closure remain open.
The docs-only runtime-branch record at `d18fd93` is not imported by this directory-cleanup change.
Any publication of those facts as the Plan 11.7 execution contract must be one complete reviewed
`_v4` successor, never another separately named amendment plan.

## Frozen approval bytes and live-status authority

These 20 artifacts retain their approved committed bytes. Each live owner named below, rather than
the artifact's approval-time status prose, answers the current-state question.

- `docs/superpowers/plans/archive/2026-07-23-plan-10-2-p9-96-fu7-effective-row-display-provenance.md` — SHA-256 `4303D6AD5C44ED62A85A0509C8C87366505D4D470DD7BC4E0B4309BBE6E3C771` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P9.96-FU-7` disposition](#p996-task-9-disclosed-follow-ups-closed-historical-plan-10-custody).
- `docs/superpowers/plans/archive/2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md` — SHA-256 `E66ECA48C588E7DB618D4850FDF0CEE901B4966BC0AB405E21C857AE6BE24F32` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [Plan 10.3 historical correction](#plan-103-frozen-plan-status-correction-historical).
- `docs/superpowers/plans/archive/2026-07-25-plan-11-1-p11-feat-gateway-core-implementation.md` — SHA-256 `254A6ACC56511BBCCEB8FC101B190F213FD65450327145C88979077D845D6D3E` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FEAT-GATEWAY-CORE`](#feature-slices).
- `docs/superpowers/plans/archive/2026-07-26-plan-11-2-p11-feat-gateway-tools-implementation.md` — SHA-256 `8C96C9BFA67FB87F4A90FAE37169D27B437C5FD0CEE3AB2E6AB399E67B2874E5` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FEAT-GATEWAY-TOOLS`](#feature-slices).
- `docs/superpowers/plans/archive/2026-07-28-plan-11-5-p11-feat-gateway-cost-obs-implementation.md` — SHA-256 `0BAC146974984EA663B7A59802A1B5ED74F90EB682F855C0E05AAAB5B9A2C396` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FEAT-GATEWAY-COST-OBS`](#feature-slices).
- `docs/superpowers/plans/archive/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md` — SHA-256 `F52AD9A5A85DC50B0DFD3206B6BD09FD8FF0AE79B1A6049DF1017F978B1C462D` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FEAT-ZED-RESUME`](#feature-slices).
- `docs/superpowers/plans/archive/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md` — SHA-256 `79F3C92A852CB7EAA6108D8F0757F6612A0C908FE032CE7CFAB58B46721C06E6` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FEAT-ZED-RESUME`](#feature-slices).
- `docs/superpowers/plans/archive/2026-08-02-plan-11-7-origin-a-fixture-v2-amendment.md` — SHA-256 `5BB327D88761AE329869B90866839D03F61EFF6AF0E5AE47F8D3D7551F849A4D` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FEAT-ZED-RESUME`](#feature-slices).
- `docs/superpowers/plans/archive/2026-08-04-plan-11-7-retry-preflight-gate-amendment.md` — SHA-256 `0AA1007309C26B072A37310F01B65B38E874A88625B9DF1215C0C61EA7620B2B` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FU-11`](#p11-fu-11-plan-117-retry-preflight-and-live-session-proof).
- `docs/superpowers/plans/archive/2026-08-18-plan-11-24-zed-guided-session-load-probe.md` — SHA-256 `BA1372E1D638AC2F12A4852E304DCE02196C26C78017F3AE1CA566F4A08DD017` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FEAT-ZED-RESUME`](#feature-slices).
- `docs/superpowers/plans/archive/2026-08-18-plan-11-24-zed-guided-session-load-probe_v2.md` — SHA-256 `BA67D5021FF767D9574BA452E39ECB2E642999C0CAEFBD6431D82E93D3842E05` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FEAT-ZED-RESUME`](#feature-slices).
- `docs/superpowers/plans/archive/2026-08-18-plan-11-24-zed-guided-session-load-probe_v3.md` — SHA-256 `C76121F5A35A698183ADEB1B028AEE6E7C0FE26621ED798586F5AF9081CB81F4` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FEAT-ZED-RESUME`](#feature-slices).
- `docs/superpowers/plans/archive/2026-08-18-plan-11-24-zed-guided-session-load-probe_v4.md` — SHA-256 `1CFBB6E0BEDD8FBB3A111DE5C9AEA11F96F36D742A1469B50EEC03EB3116B13C` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FEAT-ZED-RESUME`](#feature-slices).
- `docs/superpowers/plans/archive/2026-08-18-plan-11-24-zed-guided-session-load-probe_v5.md` — SHA-256 `26B8A69BE2A3CD4E5A021CB21A507C27D0C880D5322EF22B9A59D4257ECC96A8` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FEAT-ZED-RESUME`](#feature-slices).
- `docs/superpowers/specs/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md` — SHA-256 `8B67FC187B92F0B66A9932AAAD9A013C476C19C165A1044F57F338245A01786C` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [P9.96 historical summary and disposition](#p996-task-9-disclosed-follow-ups-closed-historical-plan-10-custody).
- `docs/superpowers/specs/2026-07-26-plan-11-2-p11-feat-gateway-tools-design.md` — SHA-256 `2E679F105A250C7DF9F3757F72C43810B92810DD080EC6A4A985B778D163BFEC` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FEAT-GATEWAY-TOOLS`](#feature-slices).
- `docs/superpowers/specs/2026-08-04-plan-11-7-retry-preflight-gate-design.md` — SHA-256 `3D4FBA5BE86399F4FD7CABB319847A847A06394BE2CEEB5D795952C2901EB90E` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FU-11`](#p11-fu-11-plan-117-retry-preflight-and-live-session-proof).
- `docs/superpowers/specs/2026-08-06-plan-11-8-p11-feat-gateway-mcp-design.md` — SHA-256 `AC48C0AEF1778D6EBE93005BC3993AE204F81A1C59CDC8DB17CFB7EDB6A040F8` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FEAT-GATEWAY-MCP`](#feature-slices).
- `docs/superpowers/specs/2026-08-15-p11-fu-18-29-durable-approval-workspace-identity-design.md` — SHA-256 `B445693AFB9B110E61D860F1B63D8836FF0EA651E0AC327BABA1CC906C84543B` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`P11-FU-18`](#p11-fu-18-workspace-identity-ctime-coalescing-fail-open) and [`P11-FU-29`](#p11-fu-29-durable-approval-identity-instability-on-transient-git-probe-failure).
- `docs/superpowers/specs/evidence-handoff-a2a-ledger-design.md` — SHA-256 `2AA21D8A5569A6427C2E34C9B785467AD7CD934D708AE16D5A43D52C2F9A71A1` — Frozen approval bytes — live status is owned by the consolidated open-work pool. Live owner: [`EVIDENCE-HANDOFF-FEAT-A2A-LEDGER`](#evidence-and-handoff-feature-registry).

**Archive-relocation re-pins (2026-08-28).** The archive move exposed relative Markdown
paths that became invalid one directory deeper. The retry-preflight plan was re-pinned
`106FD92B8E43F44A7115D7EDB1F9CF1E3EE643E4B6F594FA656FB4119A969B82` ->
`0AA1007309C26B072A37310F01B65B38E874A88625B9DF1215C0C61EA7620B2B`; its design
was re-pinned `EB34FA10148CE813A03E60E0770116ABA4AC9857E4DFBEE87E00C39BFDB0D392` ->
`3D4FBA5BE86399F4FD7CABB319847A847A06394BE2CEEB5D795952C2901EB90E`. The
executable relocation registry in
`tests/unit/docs/test_plan_relocation_digest_equivalence.py` proves each re-pin from
source commit `63b5d8f7853c57030426a01776905b0c521f1036`: it applies the exact
registered path substitutions and requires byte-for-byte equality with the committed
destination. This exception is limited to frozen Markdown path repair; evidence
artifacts and custody records remain byte-immutable.

#### Historical numbering-rule provenance

The following four documents retain statements about the numbering rule used when their work was
scheduled. Those statements are historical provenance, not live governance; the current rule lives
in `AGENTS.md` and the Plan 11 charter. Preserve each document according to its pin status:

- `docs/superpowers/plans/archive/2026-07-23-plan-10-1-p9-96-follow-up-remediation.md` — SHA-256 `FA35912C3E5AC343A1092E7B5A88CA93C0E1293061CB53D5810BB1BA3C1002F8` — Historical closed-plan task instruction. Pin status: not digest-pinned. It is in-scope and editable for Plan 11.10, but deliberately unchanged because its sentence records the rule used at the time.
- `docs/superpowers/specs/2026-07-28-plan-11-5-p11-feat-gateway-cost-obs-design.md` — SHA-256 `5608AD5520B8960E070A4A4F32C992D152A2CA19F21C177B44AC9805F371F3AA` — Historical assignment provenance. Pin status: pinned elsewhere by the Plan 11.5 implementation plan and outside the covered set. Never edit to modernize its numbering wording.
- `docs/superpowers/specs/2026-08-06-plan-11-8-p11-feat-gateway-mcp-design.md` — SHA-256 `AC48C0AEF1778D6EBE93005BC3993AE204F81A1C59CDC8DB17CFB7EDB6A040F8` — Historical assignment provenance. Pin status: one of the 13 immutable artifacts above. Never edit; `P11-FEAT-GATEWAY-MCP` owns live state.
- `docs/superpowers/specs/2026-08-08-plan-11-9-p11-7-fu-1-gateway-timeout-design.md` — SHA-256 `BBB033051B8238A50E72D20F6C59A79BF94A0EBE19A43428CCB440EAF8B37F73` — Historical assignment provenance. Pin status: not digest-pinned and outside the covered set. It is deliberately unchanged; any future edit requires its own reviewed scope.

## Feature slices

For each feature not marked `Moved`, the pool owns existence and state (a `Moved` feature's authority is its GitHub issue); the
[Plan 11 v1.0 milestone charter](2026-07-25-plan-11-v1-milestone-charter.md) owns feature scope and sequencing. Plan 12 is listed so its post-v1.0 custody cannot fall off the
open-work inventory.

| Identity                        | Status                | Priority   | Scope detail                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
|---------------------------------|-----------------------|------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| ~~`P11-FEAT-GATEWAY-CORE`~~     | ~~Closed~~            | ~~MEDIUM~~ | ~~Plan 11.1 — closed; merged to `main` as PR #85 (`6ae6997`, tip `6c39599`). Migration closed by **Plan 11.4**, merged to `main` as PR #91 (`d80e112`), 2026-07-28. [Charter](2026-07-25-plan-11-v1-milestone-charter.md#p11-feat-gateway-core---gateway-core-and-observability-route); migration custody: strict-loopback completion, OpenRouter-default OpenAI-compatible aggregator transport, provider-reported accounting, and direct-adapter retirement — all implemented and independently re-verified task-by-task. The bounded Vercel Python transport check is complete as a design decision: Vercel is backlogged under this identity (its public OpenAI-compatible transport doesn't document the mandatory per-response provider-cost fields the settled `GatewayUsage` contract requires; no comparison matrix, no second endpoint added). Closure evidence: [design spec](../specs/2026-07-28-plan-11-4-p11-feat-gateway-core-migration-design.md), [implementation plan](archive/2026-07-28-plan-11-4-gateway-core-migration.md) (all 36 checkboxes checked against their named verification commands)~~                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ~~`P11-FEAT-GATEWAY-TOOLS`~~    | ~~Closed~~            | ~~MEDIUM~~ | ~~Plan 11.2 — closed by PR #88 (merge `4590dbf`); migration follow-ups remain assigned here and receive a new Plan 11.x number only at pickup. [Charter](2026-07-25-plan-11-v1-milestone-charter.md#p11-feat-gateway-tools-and-p11-feat-gateway-cost-obs); migration custody: deterministic search/direct extract, route-specific dependency availability, replacement acceptance, and Tavily rollback-reviewed retirement; closure evidence: [Plan 11.2 approval](../reviews/2026-07-27-plan-11-2-implementation-plan-approval-v2.md), [local-process evidence](../../../reports/plan-11-2-gateway-tools-local-process-evidence.md), [staging evidence](../../../reports/plan-11-2-gateway-tools-staging-evidence.md), and [fitness report](../../../reports/plan-11-2-gateway-tools-task7-fitness.md)~~                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| ~~`P11-FEAT-GATEWAY-COST-OBS`~~ | ~~Closed~~            | ~~MEDIUM~~ | ~~Plan 11.5 — closed by PR #95 (merge `e388258`), 2026-07-29; migration follow-ups remain assigned here (`P11.5-FU-1` Closed via Plan 11.21; `P11.5-FU-2` closed via Plan 11.6) and receive a new Plan 11.x number only at pickup. [Charter](2026-07-25-plan-11-v1-milestone-charter.md#p11-feat-gateway-tools-and-p11-feat-gateway-cost-obs); [implementation plan](archive/2026-07-28-plan-11-5-p11-feat-gateway-cost-obs-implementation.md); migration custody: OTel/OTLP-to-Phoenix and the separately reviewed USD field migration~~                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ~~`P11-FEAT-GATEWAY-MCP`~~      | ~~Retired~~           | ~~MEDIUM~~ | ~~Retired by Plan 11.12. [Plan 11.8](archive/2026-08-06-plan-11-8-p11-feat-gateway-mcp-implementation.md) and [Plan 11.11](archive/2026-08-13-plan-11-11-p11-feat-gateway-mcp-2026-07-28-http-compatibility.md) are historical precursor work; their frozen design and merged implementation records are not rewritten. Plan 11.13 published HLD v2.18, LLD v2.41, Guardrails v1.3, and Test Strategy v1.7 through the sibling reversal package; immutable amendment inputs remain historical. Client-owned MCP remains live and separate. This completed publication remains a pre-`P11-FEAT-REGISTRY` / v1.0 dependency. [Evidence](../reports/2026-08-15-plan-11-13-authoritative-document-reversal-evidence.md). [Charter](2026-07-25-plan-11-v1-milestone-charter.md#p11-feat-gateway-mcp---gateway-mcp-tool-call-brokering)~~                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `P11-FEAT-ZED-RESUME` | Moved | — | [#230](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/230) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L347-L347) |
| ~~`P11-FEAT-MULTI-TURN-CONVERSATION`~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Plan 11.25 Slice 1 — same-process in-memory multi-turn conversation on ACP `session/prompt` (canonical history, byte-budget admission/commitment, settlement, dedicated NDJSON writer), merged through PR #188 and follow-up PR #189. Does **not** include persistence, `session/resume`/`session/load`, compression/summarization/pruning/eviction (Plan 12), or non-AGENT-mode carriage; `MT-FU-1` and `MT-FU-2` remain separately open below. Evidence: [baseline](../../../reports/plan-11-25-multi-turn-baseline.md), [contract evidence](../../../reports/plan-11-25-multi-turn-contract-evidence.md), [release review](../../../reports/plan-11-25-multi-turn-release-review.md); [archived implementation plan](archive/2026-08-21-plan-11-25-multi-turn-conversation-implementation.md). Current-source discrepancy: [producer-instrumentation correction](../reviews/2026-10-01-plan-11-25-effect-instrumentation-correction.md); narrow effect/cancellation repair is owned by Plan 12.2 Task 2, not established by the historical checked steps.~~ |
| `P11-FEAT-ACP-RUNTIME-HARDENING` | Moved | — | [#231](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/231) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L349-L349) |
| `HARDENING-FEAT-RUNTIME-QUALITY` | Moved | — | [#232](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/232) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L350-L350) |
| `P11-FEAT-REGISTRY` | Moved | — | [#233](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/233) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L351-L351) |
| `P11-FEAT-IDE` | Moved | — | [#234](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/234) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L352-L352) |
| `Plan 12` | Moved | — | [#235](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/235) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L353-L353) |

## P11-FEAT-TEST-PROFILES: test cadence, selection and attributable core parallelism

**Moved:** tracked in [#292](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/292). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/c99af82365b83eccc6fdb24525cafd2a064c9f09/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L368-L434).

## Plan 12 Context Engine Package A custody

**Raised / source:** ADR-013/S2 preserves original Package A/docs-first selections; S3 in the
[decision index](../../decisions/README.md#rules-for-every-record) covers later local commits,
the [exact exception](../../decisions/ADR-017-package-a-coverage-exception.md) and [checkpoint/publication decisions](../../decisions/ADR-016-checkpoint-review-cadence.md).

**Owning contract:** Plan 12.2 and its filed design; no separate hardening item or work pool.
The frozen first plan edition, the complete `_v2` (accepted by the operator on 2026-10-02 with the first
Task 1 contracts) and `_v3` (CP4 corrections) are archived unchanged. The current plan is the complete `_v4`
(CP4 offline closure), filed locally on 2026-10-05; it does not inherit the 2026-10-02 acceptance.

**Status:** Open. Package A's Tasks 0/2/3 and the separately approved lock controls were implemented
and offline technically accepted at `38a465f`. They reached `main` with the Plan 12.2 offline delivery through
[PR #276](https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/276) (merge commit `c509fc8`, 2026-10-08); PR #216 is marked merged.
See the [merge record](../reviews/2026-10-08-plan-12-2-offline-merge-record.md).
Docs-first PR #214 merged as `1f7b6a2`; ADR-001-015 remain frozen. Four commits and measured residual
are in the [delivery record](../reviews/2026-10-02-plan-12-2-package-a-delivery.md). This does not close Plan 12 or certify live Zed.

**Next gates:** Publication and merge are complete. The three deferred live obligations remain under Plan 12.2
ownership. When separately released and their own prerequisites are satisfied, Task 13's absent-engine cases
may run before summary qualification. Attached-engine maintenance cases still require an eligible summarizer
route and a genuine summary-quality receipt. The sandbox retains its reported effect-producer gap until
separately authorized synchronization.
Paid/live calls, service/settings changes and sandbox synchronization require their own authority.

**Open presentation observation (Plan 12 owner):** when a cancelled Agent turn has completed one
or more file writes, its completion text still begins "Completed:" and lists those writes. The
listed writes are true, but the text can obscure that the turn was cancelled and that later tests
were suppressed. Keep outcome, effect completion and test verdict distinct. Record/assess a targeted wording treatment within
Plan 12's presentation work; no code change or new plan is commissioned by this intake.
Trigger: next relevant host/UI work. Acceptance: truthful text for success, cancellation, PARTIAL
and failed tests, backed by focused UI/payload evidence. Status Open; not excluded from Plan 12.

**Known cancellation diagnostic limitation (Plan 12 owner):** the engine can internally label a cancelled
summary as failed while ACP shows the turn as cancelled. Recorded by the CP4 offline closure (LLD v2.42
§13.2; the closure sources' migration map) as a nonblocking known limitation; no code change is commissioned.

## Package A repeatability observations — P11.26-CAND-5 intake

**Moved:** tracked in [#306](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/306). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/c99af82365b83eccc6fdb24525cafd2a064c9f09/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L473-L497).

## Package A sanitizer throughput — security-text owner intake

**Moved:** tracked in [#339](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/339). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/c99af82365b83eccc6fdb24525cafd2a064c9f09/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L499-L510).

## Plan 11.26 reviewed disposition and remediation custody

This Task 12 disposition was accepted at G6 and is frozen. It ranks independently schedulable candidates by
latent surface closed, then severity. Candidate IDs are custody labels, not assigned plan numbers;
each pickup must first run the backlog conflict check. Deterministic source findings may support a
candidate even when repeatability evidence is excluded. No row claims production repair, live
acceptance, release acceptance, or that a historical flake is fixed.

H1 is `SUPERSEDED` as an audit unit by the narrower H3 task-ownership, H5 shutdown-ownership, and
H9 health-deadline records. H2 is `SUPERSEDED` as a standalone hypothesis by H10 while its runtime
claim remains `PROVISIONAL_OVERLAY` under `P11-FEAT-ZED-RESUME`. The baseline-scope register and
evidence/disposition union now cover H1-H10 mechanically.

C15 is retained as two `MISSING` Task 12 findings without widening the raw `CLEAN`/`LEAKED`
observation enum: sink class must distinguish `gateway_export` external egress from local retention,
and clean semantics must distinguish `CLEAN_REDACTED` from `CLEAN_NOT_STORED`. C19 retains the
10 `HARNESS` / 4 `UNRESOLVED` timeout split; the four product-or-harness-indeterminate rows are
excluded from remediation ranking evidence. C20 makes the 25-repeat shutdown group authoritative
and treats the single green terminal row only as execution evidence. The cancellation group remains
`FLAKY`; no historical flake is claimed fixed.

This G6 custody table is a historical acceptance record, not live remediation-plan status; its tested tuples remain unchanged.

| Kind | Identity | Rank | Shape | Surface | Severity | Disposition | Owner-to-be | Next gate |
|---|---|---:|---|---|---|---|---|---|
| Candidate | `P11.26-CAND-1-RESOURCE-LIFETIME` | 1 | Consolidation | 15 discovered close paths; H3 escaped-child and H9 health-deadline citations remain separately traceable. | HIGH | `ACCEPTED_OPEN` | `P11-FEAT-ACP-RUNTIME-HARDENING` / ACP runtime lifecycle owner | G6 accepted custody; pickup establishes one lifecycle owner and makes close ordering, bounded completion, and idempotence structural contracts. |
| Candidate | `P11.26-CAND-2-TELEMETRY-CONTRACT` | 2 | Consolidation | 50 telemetry sites, 16 event kinds, and 5 sinks; includes C15 precision. | HIGH | `ACCEPTED_OPEN` | `P11-FEAT-ACP-RUNTIME-HARDENING` / typed telemetry boundary owner | G6 accepted custody; pickup establishes one schema, correlation, containment, sink-class, and storage-disposition authority. |
| Candidate | `P11.26-CAND-3-SEMANTIC-ERROR-SELECTION` | 3 | Consolidation | 13 exact H7 symbol citations across 6 findings; the intentional sanitizer exception is retained, not repaired. | HIGH | `ACCEPTED_OPEN` | `P11-FEAT-ACP-RUNTIME-HARDENING` / semantic error-selection owner | G6 accepted custody; pickup centralizes runtime-outcome-to-wire-code selection while preserving Plan 11.18 authority. |
| Candidate | `P11.26-CAND-4-QUEUE-BACKPRESSURE` | 4 | Consolidation | 3 constructor-declared unbounded queues and the separately cited full-operation health deadline. | HIGH | `ACCEPTED_OPEN` | `P11-FEAT-ACP-RUNTIME-HARDENING` / queue admission owner | G6 accepted custody; pickup establishes one bounded admission and overload-disposition contract before changing individual queues. |
| Candidate | `P11.26-CAND-5-REPEATABILITY-ATTRIBUTION` | 5 | Consolidation | Narrow and group shutdown tiers; 14 timeouts retain 10 HARNESS / 4 UNRESOLVED row attribution. | MEDIUM | `ACCEPTED_OPEN` | `P11-FEAT-ACP-RUNTIME-HARDENING` / repeatability evidence owner | G6 accepted custody; pickup replaces scenario-wide masking with per-row attribution and composite reporting. Related Package A audit-Git timeout and coverage-repeatability intake below; original 14 sealed rows are unchanged. |
| Obligation | `P11.26-UNRUN-BINDING` | — | Scope-out | Missing session-lease binding predicate; Task 10's five tests corroborate the stop but do not substitute for it. | N/A | `UNRUN_BINDING` | `P11-FEAT-ZED-RESUME` | Reconcile branches, nominate the binding commit, implement the predicate, then run it. |
| Obligation | `P11.26-UNRUN-REDIS` | — | Scope-out | Missing live Redis owner/revision predicate and no live Redis grant. | N/A | `UNRUN` | operator | Grant the real Redis row after binding and provenance prerequisites are satisfied. |
| Obligation | `P11.26-UNRUN-ZED` | — | Scope-out | Missing Zed E2E predicate/manual observation bundle and no Zed grant. | N/A | `UNRUN` | operator | Grant the five manual Zed rows after trusted-workspace and installed-artifact provenance prerequisites are satisfied. |

## MAIN-5 residuals under existing 11.x owners

Raised 2026-10-02 from MAIN-5 local-delivery, telemetry, harness and guarded-runner review.
The UNC1-UNC7 sandbox checkpoint at `f6b0b602291b933ac1f493f397cad2b6f53620bf`
(`sandbox-main5-guarded-runner-y5`) is independently accepted. The original main
port merged through PR #215 at `78c1f7c`; that merge does not include the y5 correction.
These entries record custody and acceptance criteria only. They commission no
implementation, assign no new numbered plan; priority stays at the default MEDIUM.
They change no Plan 12 state.
Associations without a dedicated existing ID remain proposed under the named owner.

### P11-FU-31: MAIN-5 synthetic-fixture and complete-scan delivery debt

**Moved:** tracked in [#249](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/249). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L544-L554).

### P11-FU-32: MAIN-5 Windows harness environment dependence

**Moved:** tracked in [#250](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/250). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L555-L567).

### P11-FU-33: MAIN-5 shutdown repeatability evidence

**Status:** Closed. Through [PR #219](https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/219),
merge `4797112e9ecca5526e874698dcfda719471dd6d9` (2026-10-03); merged tree equals
independently accepted `82b8d952553a1d087472f7b38ea47f530d8c86e2`.
**Origin:** Retained shutdown repeat-100 failure records; distinct from FU-5/FU-6/FU-7.
**Designated future plan / owner:** `P11.26-CAND-5-REPEATABILITY-ATTRIBUTION`;
escalate to `P11.26-CAND-1-RESOURCE-LIFETIME` only if causal evidence warrants.
**Trigger or acceptance criteria:** Capture failed rows with timing, process ownership and
quiescence evidence; classify harness, product or unresolved and retain the complete group
outcome. A passing retry cannot erase a failure or close historical obligations.

**Evidence (2026-10-02):** The repeat-100 `unexpected_persistent_threads` assertion
failed in the port-Y guarded full run (pre-`-y5`) and the R4 unguarded manual run
on `a219831`. The reviewed Windows full-suite record is 2 failures in 6 runs.
Linux/WSL bundle and PR #217 CI runs skipped the test under `P11.26-UNRUN-BINDING`
because binding commit `fac32284888850bacde93815265cbabe3afd4663` was missing;
those runs prove nothing about this test. Root cause is not established.
Public anchors: [PR #217 description](https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/217)
and [PR #217 CI](https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/36977760586).

**Root cause and proposed closure (2026-10-02):** `RedisRuntime.close()` and
`close_async()` returned once `record.completed` was set, but the
`optimus-redis-runtime-teardown` thread sets it inside its own `finally` and only then
exits, so the H5 schedule could enumerate that thread before it left. OS preemption in
that window produced the failures. A deterministic reproduction pauses only that thread
after it publishes completion: 200/200 failures, and 0/200 once the thread is joined.
`RedisLoopOwner`'s finalizer thread had the same signal-before-exit shape. The fix joins
each thread within the caller's existing observation budget and reports shutdown as
incomplete, rather than complete, while it lives. The H5 schedule now records
detection-time context (thread target and stack) and measures pending asyncio tasks
from real state, and the concurrency tests name the offending thread, task, process or
row instead of a bare assertion. Two bounded joins that return silently on timeout
remain, outside the H5 schedule: `NdjsonSubprocessSession.terminate()` (5 s) and the
client-MCP local IPC listener stop (2 s); custody `P11.26-CAND-1-RESOURCE-LIFETIME`.
Proposed closure: Closed when the fix lands on `main`, citing the merge, with this entry
escalated per its criteria to `P11.26-CAND-1-RESOURCE-LIFETIME`.

**Same batch, round 2 (2026-10-02/03):** the batch's guarded full run then failed a test
outside its diff. The plan1126 offline timeout used `taskkill /T`, which walks parent
pids at the moment it runs, so a descendant started during the walk, or one whose parent
had already exited, escaped the kill and kept the capture pipes open. `tools/process_tree.py`
now owns whole-tree kills (Windows: the child starts suspended inside a job object; POSIX:
its own process group), and all four `taskkill /T` sites in `tools/` use it. Tests that used
elapsed time as a proxy for a tree kill now name the surviving process. Remaining under
custody `P11.26-CAND-1-RESOURCE-LIFETIME`, not changed by this batch: on timeout
`tools/evidence_gather_support/acp.py::spawn_acpx` kills only its direct child and then
reads the pipes without a bound; the Plan 9.96 ordinary capture timeout kills only its
direct child (its plain-child spawn is pinned); and the live-only Zed investigation test
`tests/investigation/evidence/test_zed_user_data_live.py` still uses `taskkill /T`.
Consolidation obligation: the unmerged parallel-test-context work
(`tools/testing/run_context_windows.py`) owns a second set of Windows job-object bindings;
the two are to become one owner once both are on `main`. Real Zed under a no-breakaway job
is unverified until the next authorized live probe.

**Closure evidence and disposition (2026-10-03):** Classification: **product**.
The deterministic 200/200 failing pause reproduction and 0/200 after joining,
recorded above, establish the signal-before-thread-exit resource-lifetime cause;
the bounded joins report incomplete shutdown while either thread remains alive.
The retained failed rows and complete group outcomes, including the historical
2-in-6 failures and the round-2 failure, remain evidence; a passing retry does not
erase them or close other historical obligations. The entry's conditional escalation
is warranted and recorded: this cause is a resource-lifetime instance, and all deferred
joins, child/pipe/tree-kill paths and job-binding consolidation already listed above
remain in `P11.26-CAND-1-RESOURCE-LIFETIME` custody. Neither that candidate nor
`P11.26-CAND-5-REPEATABILITY-ATTRIBUTION` is closed by this filing.

The Windows guarded full run and all-files pytest-coverage commit hook on accepted
`82b8d95` both passed and are the repeat-100 execution evidence in the sealed reviewed
packets. The repeat-100 test runs only on Windows full-history checkouts; Linux/WSL
and CI skip it. PR #219's `verify` and `clean-environment-recheck` checks succeeded,
and [post-merge guardrails run 37117424517](https://github.com/vibhanshu-agarwal/optimus-cost-agent/actions/runs/37117424517)
completed successfully on exact merge `4797112`; these CI results are delivery checks,
not repeat-100 evidence. Real Zed under the no-breakaway job remains untested; a fresh
Plan 11.24 establishing report is required before any future live drive. Those live
boundaries remain open and are neither reopened nor closed here.

**Deferred-work pickup (2026-10-03):** The open residuals now have explicit Plan 11.x
entries: `P11-FU-38` (bounded joins/waits), `P11-FU-39` (timeout/capture cleanup class),
`P11-FU-40` (real Zed containment) and `P11-FU-41` (job-binding consolidation). Their
existing owners and evidence gates remain unchanged; this FU33 entry stays Closed.
The establishing-report prerequisite stays solely with Plan 11.24's Task-13 gate.

### P11-FU-34: MAIN-5 settlement telemetry truth

**Moved:** tracked in [#271](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/271). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L651-L660).

### P11-FU-35: MAIN-5 y5 correction port

**Status:** Closed. Through [PR #217](https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/217),
merge `df703857a7304abd36beedce9fcb9737a24fcc46`; merged tree equals tested `a219831`.
**Origin:** UNC/device prevention gap, SQLite file-URI classification, PowerShell absent/empty idiom and UNC7 lane-ledger correction.
**Designated future plan / owner:** `P11-FEAT-ACP-RUNTIME-HARDENING`, MAIN-5 safety and test tooling.
**Trigger or acceptance criteria:** Port `sandbox-main5-guarded-runner-y5` to main in the
reviewed four-file scope, preserving network/device alias prevention before and after
resolution, strict SQLite file-URI classification, PowerShell 7/5.1 environment removal,
blank-target/argument refusal and ordinal executed-versus-planned lane checks. Retain
the independent audit-only self-test lane, whole runner-file integrations, process-tree
signals, clean protected roots and stop/seal on CONFOUNDED. Sandbox acceptance resolves
the fix there; main-side closure requires its separate port review and delivery approvals.

### P11-FU-36: MAIN-5 remaining guarded-runner mechanics

**Moved:** tracked in [#251](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/251). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L675-L686).

## Plan 11.x resource-lifetime and live-evidence residuals from FU33

Raised 2026-10-03 at the operator's request to expose deferred work as open entries
in this consolidated log. These residuals were identified during
[Closed P11-FU-33](#p11-fu-33-main-5-shutdown-repeatability-evidence), delivered by
[PR #219](https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/219) and filed through
[PR #220](https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/220). The seed lists
in that historical entry are not exhaustive class inventories. These entries preserve
existing custody, historical failures and the default MEDIUM priority. They do not
reopen FU33, change candidate/parent/Plan 12 statuses, commission implementation,
allocate an implementation-plan number, or grant a live drive.

### P11-FU-38: Bounded join and wait outcome classification

**Moved:** tracked in [#272](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/272). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L699-L729).

### P11-FU-39: Process-tree timeout and captured-pipe cleanup class

**Moved:** tracked in [#273](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/273). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L730-L768).

### P11-FU-40: Real Zed process containment and live-only tree-kill path

**Moved:** tracked in [#224](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/224). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L769-L786).

### P11-FU-41: Windows job-object binding owner consolidation

**Moved:** tracked in [#274](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/274). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L787-L802).

### P11-FU-43: Planning-progress notice ordering race

**Moved:** tracked in [#288](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/288). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/c99af82365b83eccc6fdb24525cafd2a064c9f09/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L698-L731).

## Plan 11.26 H4 verifier follow-ups from Seam 2 checkpoint A

**Moved:** tracked in [#252](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/252). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L838-L854).

## Plan 11.26 Task 13 reviewed duplication disposition

This G7 table is separate from the frozen Task 12/G6 custody above. It contains only semantically
confirmed duplication from the immutable `b62462f` source snapshot; the 176 raw groups remain a
high-recall upper bound, not a defect count. Rank is reproduced from confirmed member-symbol surface,
then severity. No row claims consolidation complete, production remediation, or live acceptance, and
no historical flake is claimed fixed. Every row is accepted as `ACCEPTED_OPEN` custody; remediation remains open under its named owner-to-be and next gate.

This G7 custody table is a historical acceptance record, not live remediation-plan status; its tested tuples remain unchanged.

| Identity | Rank | Shape | Surface | Severity | Disposition | Owner-to-be | Next gate |
|---|---:|---|---:|---|---|---|---|
| `T13-CAND-RUNNER-CONTRACTS` | 1 | `consolidation` | 37 | `MEDIUM` | `ACCEPTED_OPEN` | `P11-REMEDIATION-RUNNER-CONTRACTS` | Independent remediation plan and focused regression gate for evidence-runner helpers and pinned contract values. |
| `T13-CAND-AUDIT-PRIMITIVES` | 2 | `consolidation` | 25 | `MEDIUM` | `ACCEPTED_OPEN` | `P11-REMEDIATION-AUDIT-PRIMITIVES` | Independent remediation plan and focused regression gate for audit-tool canonicalization, symbol, citation, and visitor helpers. |
| `T13-CAND-CREDENTIAL-CONTRACTS` | 3 | `consolidation` | 15 | `HIGH` | `ACCEPTED_OPEN` | `P11-REMEDIATION-CREDENTIAL-CONTRACTS` | Independent remediation plan and focused regression gate for credential fingerprints and launch-security constants. |
| `T13-CAND-SECURITY-TEXT` | 4 | `consolidation` | 13 | `HIGH` | `ACCEPTED_OPEN` | `P11-REMEDIATION-SECURITY-TEXT-POLICY` | Independent remediation plan and focused regression gate for security text sanitization and validation primitives. Related Package A sanitizer-throughput observation recorded below; no remedy commissioned. |
| `T13-CAND-DOMAIN-HTTPS` | 5 | `consolidation` | 12 | `HIGH` | `ACCEPTED_OPEN` | `P11-REMEDIATION-DOMAIN-POLICY` | Independent remediation plan and focused regression gate for domain and HTTPS normalization and matching policy. |
| `T13-CAND-LEDGER-ACCOUNTING` | 6 | `consolidation` | 10 | `HIGH` | `ACCEPTED_OPEN` | `P11-REMEDIATION-LEDGER-ACCOUNTING` | Independent remediation plan and focused regression gate for evidence and provider-usage ledger settlement logic. |
| `T13-CAND-REDACTION-LIFETIME` | 7 | `consolidation` | 10 | `HIGH` | `ACCEPTED_OPEN` | `P11-REMEDIATION-REDACTION-LIFETIME` | Independent remediation plan and focused regression gate for redaction cleanup, containment, hashing, and count aggregation. |
| `T13-CAND-DIRECTIVE-GRAMMAR` | 8 | `consolidation` | 6 | `HIGH` | `ACCEPTED_OPEN` | `P11-REMEDIATION-DIRECTIVE-GRAMMAR` | Independent remediation plan and focused regression gate for planner directive grammar. |
| `T13-CAND-EVIDENCE-SERVICE` | 9 | `consolidation` | 6 | `MEDIUM` | `ACCEPTED_OPEN` | `P11-REMEDIATION-EVIDENCE-SERVICES` | Independent remediation plan and focused regression gate for evidence acquisition and package-advisory recording helpers. |
| `T13-CAND-SHARED-DEFAULTS` | 10 | `consolidation` | 4 | `MEDIUM` | `ACCEPTED_OPEN` | `P11-REMEDIATION-SHARED-CONFIG` | Independent remediation plan and focused regression gate for shared model defaults and MCP name grammar. |
| `T13-CAND-REDIS-HEALTH` | 11 | `consolidation` | 2 | `HIGH` | `ACCEPTED_OPEN` | `P11-REMEDIATION-REDIS-RUNTIME` | Independent remediation plan and focused regression gate for Redis health-check exception normalization. |
| `T13-CAND-RETRY-TIMING` | 12 | `consolidation` | 2 | `MEDIUM` | `ACCEPTED_OPEN` | `P11-REMEDIATION-RETRY-POLICY` | Independent remediation plan and focused regression gate for retry delay conversion. |

**Plan 11.7 digest-pinned amendment status convention:** the
[server-side custody feasibility amendment](archive/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md),
[origin-A fixture-v2 amendment](archive/2026-08-02-plan-11-7-origin-a-fixture-v2-amendment.md), and
[retry-preflight amendment](archive/2026-08-04-plan-11-7-retry-preflight-gate-amendment.md) intentionally
retain their approval-time `Draft` status text and unchecked checkboxes. That is a load-bearing
choice to preserve their approval digests, not incomplete progress tracking. Current execution state
is owned by this living pool and the committed evidence chain: the
[artifact manifest](../../../reports/plan-11-7-server-custody-artifact-manifest.json),
[origin-A Option B seal](../../../reports/plan-11-7-server-custody-artifacts/amendments/origin-a-fixture-v2/origin-a-3-seal-b.json),
[retry Task 0 digest checkpoint](../../../reports/plan-11-7-server-custody-artifacts/amendments/retry-preflight-gate/task0-checkpoint.json),
[Path A terminal seal](../../../reports/plan-11-7-server-custody-artifacts/amendments/retry-preflight-gate/path-a-run/path-a-terminal-seal.json), and
[Task 6 checkpoint](../../../reports/plan-11-7-server-custody-artifacts/amendments/retry-preflight-gate/task6-checkpoint.json).
Do not reconcile those historical files by changing their status lines or checkboxes.

## Work tracking maintenance (Plan 11.29 residuals)

The two entries below are mechanisms that [Plan 11.29](2026-10-04-plan-11-29-github-issues-migration.md) specified and that the bounded
49-record cutover ([ADR-021](../../decisions/ADR-021-bounded-github-authority-switch.md)) did not deliver. Plan 11.29 is their origin.
Their continuing owner is the roadmap entry "Work tracking maintenance (Tracked, Not Yet Scheduled)" in the
[Phase 1 roadmap](2026-07-01-phase-1-roadmap.md); no implementation plan exists for either, and each is tracked in its issue ([#290](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/290) and
[#291](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/291)), which keeps its priority, difficulty and estimate.

### P11.29-FU-1: Work tracking impact declaration replacing the masterplan-impact gate

**Moved:** tracked in [#290](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/290). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/c99af82365b83eccc6fdb24525cafd2a064c9f09/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L784-L802).

### P11.29-FU-2: Plan-header tracking-issue convention and offline check

**Moved:** tracked in [#291](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/291). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/c99af82365b83eccc6fdb24525cafd2a064c9f09/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L804-L820).

## Follow-up status index

The detailed entries own explanatory prose; tests enforce this index as the exact ID/title/status
projection of every stable-ID follow-up heading.

**Closure partition:** `Open`, `Promoted -> ...`, and `Partially implemented` are unresolved;
`Closed` and `Reviewed disposition` are resolved. Promotion remains unresolved until the item's own
status changes through the normal status workflow; the target plan's status is not copied here.

**Priority and scheduling policy (2026-08-15):** `MEDIUM` is the default resting state and requires
no justification. Analysis may leave an unresolved entry at `MEDIUM` or move it to `HIGH` or `LOW`.
Every unresolved `HIGH` and `LOW` row must have written justification in its detail entry. Work
`HIGH` and `MEDIUM` entries first; defer `LOW` entries to the end of the Plan. For defects, `LOW`
requires no functional impact and low occurrence rate. Capability gaps, audits, process gates,
reconciliations, and other non-defect entries have no occurrence-rate criterion; justify them on
functional impact alone. This pass changes triage only; it does not change any follow-up status.

**Plan 12 custody note (2026-08-15):** `P9.8-FU-2`, `P9.8-FU-3`, `P9.85-FU-1`, and
`P9.85-FU-2` retain `MEDIUM` only as the default resting state. They do not carry a Plan 11
priority or scheduling claim; their designated owner remains Plan 12.

| ID | Item | Status | Priority   | Owning slice / designated plan | Evidence |
|---|---|---|------------|---|---|
| `P9.8-FU-2` | Intelligent ambiguous-reference ranking | Moved | — | — | [#242](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/242) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L917-L917) |
| `P9.8-FU-3` | Dynamic context budgets and required-file summarization | Moved | — | — | [#243](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/243) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L918-L918) |
| `P9.8-FU-5` | Zed Refusal-Rendering Stability | Moved | — | — | [#253](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/253) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L919-L919) |
| `P9.85-FU-1` | Intelligent observation compression | Moved | — | — | [#244](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/244) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L920-L920) |
| `P9.85-FU-2` | Dynamic planning-evidence partition | Moved | — | — | [#245](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/245) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L921-L921) |
| `P9.85-FU-3` | Cross-Run/Session Spend Policy | Moved | — | — | [#257](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/257) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L922-L922) |
| `P9.87-FU-1` | Mechanical Current-Raw-Evidence Grounding Guard | Moved | — | — | [#258](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/258) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L923-L923) |
| `P9.96-FU-8` | Launch approval record capacity | Moved | — | — | [#289](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/289) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/c99af82365b83eccc6fdb24525cafd2a064c9f09/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L852-L852) |
| `P11-FU-1` | ACP Session Resume Capability | Moved | — | — | [#254](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/254) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L925-L925) |
| ~~`P11-FU-2`~~ | ~~Package Lookup and Security Advisory Gateway Capability~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~`P11-FEAT-GATEWAY-TOOLS` / Plan 11.2~~ | ~~PR #88 / `4590dbf`~~ |
| ~~`P11-FU-3`~~ | ~~MCP Route/Typed-Contract Publication Gate~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~`P11-FEAT-GATEWAY-MCP`~~ | ~~PR #112; PR #113 / `edd1f04`~~ |
| `P11-FU-4` | Re-pin FU-4A/FU-5 Live Evidence | Moved | — | — | [#259](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/259) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L928-L928) |
| `P11-FU-5` | Windows Subprocess Handle-Duplication Flake (WinError 6/50) | Moved | — | — | [#260](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/260) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L929-L929) |
| `P11-FU-6` | Gateway `test_server` Full-Suite Port/Teardown Flake | Moved | — | — | [#261](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/261) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L930-L930) |
| `P11-FU-7` | Windows Coverage/`sys.settrace` Timing Flake in ACP NDJSON Sanitization Test | Moved | — | — | [#262](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/262) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L931-L931) |
| ~~`P11.5-FU-1`~~ | ~~Map live OTLPSpanExporter FAILURE into Gateway QUEUED/retry semantics~~ | ~~Closed~~ | ~~MEDIUM~~     | ~~`P11-FEAT-GATEWAY-COST-OBS`~~ | ~~[phoenix evidence](../../../reports/plan-11-21-p11-5-fu-1-phoenix-evidence.md); [release](../../../reports/plan-11-21-p11-5-fu-1-release.md); Task 8 watch remains Plan 11.5 Task 8~~ |
| `P11-FU-8` | Align `OPTIMUS_LOCAL_GATEWAY_BASE_URL` with `OPTIMUS_GATEWAY_<THING>_BASE_URL` naming | Moved | — | — | [#263](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/263) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L933-L933) |
| ~~`P11-FU-9`~~ | ~~Client-Supplied ACP `mcpServers` Disposition~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Dedicated P11-FU-9 lane~~ | ~~PR #119 / `9a93137`; [closure evidence](../../../reports/p11-fu-9-client-mcp-closure-evidence.md)~~ |
| ~~`P11-FU-10`~~ | ~~Complete ACP Error-Code Registry Audit~~ | ~~Closed~~ | ~~HIGH~~       | ~~[Plan 11.18](archive/2026-08-15-plan-11-18-acp-error-code-registry-audit-implementation.md)~~ | ~~PR #158 (merge 7d4e466); [acpx evidence](../../../reports/plan-11-18-p11-fu-10-acpx-error-code-evidence.md)~~ |
| ~~`P11.7-FU-1`~~ | ~~Configurable Gateway request timeout for debug/investigation workflows~~ | ~~Closed~~ | ~~HIGH~~   | ~~Plan 11.9~~ | ~~PR #123 / `d0253be`~~ |
| ~~`P11.7-FU-2`~~ | ~~Gateway threaded-test flake under full-suite load~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~`P11-FU-6` Gateway harness custody~~ | ~~Batch B 2026-08-14; misfiled duplicate~~ |
| `P11.7-FU-3` | Committed `plan117_custody_relay.py` docstring `\ufffd` / em-dash corruption | Moved | — | — | [#255](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/255) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L938-L938) |
| `P11-FU-11` | Plan 11.7 Retry Preflight and Live Session Proof | Moved | — | — | [#256](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/256) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L939-L939) |
| ~~`P11-FU-12`~~ | ~~MCP OAuth 2.1 Lifecycle~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Retired `P11-FEAT-GATEWAY-MCP`~~ | ~~Plan 11.12; won't-do~~ |
| ~~`P11-FU-13`~~ | ~~Deferred MCP Capabilities and Long-Lived Interaction~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Retired `P11-FEAT-GATEWAY-MCP`~~ | ~~Plan 11.12; won't-do~~ |
| ~~`P11-FU-14`~~ | ~~MCP Registry Discover-and-Connect~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Retired `P11-FEAT-GATEWAY-MCP`~~ | ~~Plan 11.12; won't-do~~ |
| ~~`P11-FU-15`~~ | ~~MCP Tool Search and Context Minimization~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Retired `P11-FEAT-GATEWAY-MCP`~~ | ~~Plan 11.12; won't-do~~ |
| `P11-FU-16` | Reverse Research-to-Documentation Freshness Gate | Moved | — | — | [#264](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/264) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L944-L944) |
| ~~`P11-FU-22`~~ | ~~Durable effect-aware MCP indeterminate-call custody~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Retired `P11-FEAT-GATEWAY-MCP`~~ | ~~Plan 11.12; won't-do~~ |
| `P11-FU-23` | Durable client-MCP descriptor-surface pinning and named tool allowlists | Moved | — | — | [#265](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/265) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L946-L946) |
| `P11-FU-24` | Client-MCP durable HTTP/SSE trust relaxation | Moved | — | — | [#266](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/266) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L947-L947) |
| `P11-FU-25` | Authenticated client-owned MCP upstream evidence | Moved | — | — | [#267](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/267) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L948-L948) |
| ~~`P11-FU-26`~~ | ~~Plan 11.8 Windows `WinError 10053` MCP test flake~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Retired `P11-FEAT-GATEWAY-MCP`; signal under `P11-FU-6`~~ | ~~Plan 11.12; obsolete-by-retirement~~ |
| ~~`P11-FU-27`~~ | ~~Publication-Plan Historical-State Reconciliation~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Plan 11.22~~ | ~~[Plan 11.22 reconciliation evidence](../../../reports/plan-11-22-p11-fu-27-publication-reconciliation.md); merged PR #113 / `verification.md`~~ |
| ~~`P11-FU-28`~~ | ~~WSL2 `uv sync` shared-Windows-`.venv` destruction hazard~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Native WSL clone operating decision~~ | ~~Obsolete for supported Linux-parity gates; `P11-FU-17` proof 2026-08-14~~ |
| ~~`P11-FU-29`~~ | ~~Durable-approval identity instability on transient Git probe failure~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Plan 11.15~~ | ~~[release report](../../../reports/plan-11-15-durable-approval-identity-release.md); preserve-approval / Git-retry / migration evidence only~~ |
| `P11-FU-30` | No log-level categorization; stdlib `logging` is absent project-wide | Moved | — | — | [#275](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/275) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L953-L953) |
| ~~`P11-FU-17`~~ | ~~WSL2 native git cannot parse a Windows-git-created linked worktree's `.git` pointer~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Native WSL clone operating decision~~ | ~~Resolved by verified ext4 native-clone gate; proof report 2026-08-14~~ |
| ~~`P11-FU-18`~~ | ~~Workspace-identity `ctime` coalescing fail-open~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Plan 11.15~~ | ~~[release report](../../../reports/plan-11-15-durable-approval-identity-release.md); equal-ctime topology evidence only~~ |
| ~~`P11-FU-19`~~ | ~~WSL client-SDK operation-deadline supervisor race~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Plan 11.16~~ | ~~[Windows](../../../reports/plan-11-16-p11-fu-19-windows-evidence.md); [WSL](../../../reports/plan-11-16-p11-fu-19-wsl-evidence.md)~~ |
| `P11-FU-20` | Attach per-server catalog/authorizer to session tool service for real one-call issuance | Moved | — | — | [#223](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/223) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L957-L957) |
| ~~`P11-FU-21`~~ | ~~Custody Relay Broken-Pipe Exit-Code Propagation Defect~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Plan 11.14~~ | ~~Plan 11.14; `reports/plan-11-14-p11-fu-21-custody-relay-exit-code-evidence.md`~~ |
| ~~`P11.5-FU-2`~~ | ~~Consistent local env / Redis / Phoenix / Gateway startup for live runs~~ | ~~Closed~~ | ~~HIGH~~   | ~~Plan 11.6~~ | ~~PR #97 / `dc9a080`; [operator runbook](../../runbooks/local-live-dependencies.md)~~ |
| `P11.25-FU-1` | Non-AGENT-mode conversation carriage (contract term: MT-FU-1) | Moved | — | — | [#246](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/246) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L960-L960) |
| `P11.25-FU-2` | Structured ACP stop-reason metadata (contract term: MT-FU-2) | Moved | — | — | [#268](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/268) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L961-L961) |
| `P12-FU-1` | Plan/Chat advisory-answer capability (residual of HLD §7) | Moved | — | — | [#247](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/247) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L962-L962) |
| `P12-FU-2` | User-facing net cost-savings report | Moved | — | — | [#248](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/248) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L963-L963) |
| `P12.1-FU-1` | Local Gateway missed the agent's startup readiness deadline | Moved | — | — | [#269](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/269) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L964-L964) |
| `P12.1-FU-2` | Goal-loop iterations bypass turn cancellation and directive tracking | Moved | — | — | [#270](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/270) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L965-L965) |
| `P11-FU-31` | MAIN-5 synthetic-fixture and complete-scan delivery debt | Moved | — | — | [#249](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/249) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L966-L966) |
| `P11-FU-32` | MAIN-5 Windows harness environment dependence | Moved | — | — | [#250](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/250) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L967-L967) |
| ~~`P11-FU-33`~~ | ~~MAIN-5 shutdown repeatability evidence~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~`P11.26-CAND-5-REPEATABILITY-ATTRIBUTION`~~ | ~~Through [PR #219](https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/219), merge `4797112`; deferred items retain CAND-1 custody~~ |
| `P11-FU-34` | MAIN-5 settlement telemetry truth | Moved | — | — | [#271](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/271) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L969-L969) |
| ~~`P11-FU-35`~~ | ~~MAIN-5 y5 correction port~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~`P11-FEAT-ACP-RUNTIME-HARDENING`~~ | ~~Through [PR #217](https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/217), merge `df70385`; merged tree equals tested `a219831`~~ |
| `P11-FU-36` | MAIN-5 remaining guarded-runner mechanics | Moved | — | — | [#251](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/251) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L971-L971) |
| `P11-FU-37` | MAIN-5 Windows evidence-bundle promotion residual | Moved | — | — | [#293](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/293) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/c99af82365b83eccc6fdb24525cafd2a064c9f09/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L900-L900) |
| `P11-FU-38` | Bounded join and wait outcome classification | Moved | — | — | [#272](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/272) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L973-L973) |
| `P11-FU-39` | Process-tree timeout and captured-pipe cleanup class | Moved | — | — | [#273](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/273) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L974-L974) |
| `P11-FU-40` | Real Zed process containment and live-only tree-kill path | Moved | — | — | [#224](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/224) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L975-L975) |
| `P11-FU-41` | Windows job-object binding owner consolidation | Moved | — | — | [#274](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/274) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L976-L976) |
| `P11-FU-43` | Planning-progress notice ordering race | Moved | — | — | [#288](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/288) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/c99af82365b83eccc6fdb24525cafd2a064c9f09/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L905-L905) |
| `P11.29-FU-1` | Work tracking impact declaration replacing the masterplan-impact gate | Moved | — | — | [#290](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/290) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/c99af82365b83eccc6fdb24525cafd2a064c9f09/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L906-L906) |
| `P11.29-FU-2` | Plan-header tracking-issue convention and offline check | Moved | — | — | [#291](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/291) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/c99af82365b83eccc6fdb24525cafd2a064c9f09/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L907-L907) |

## Evidence and handoff feature registry

This section replaces the former second status pool, now preserved only as
[`archive/evidence-handoff-open-work-pool.md`](archive/evidence-handoff-open-work-pool.md).
Designs and archived plans continue to own detailed scope. A row marked `Moved` has its current state, priority and next gate in its GitHub issue ([ADR-022](../../decisions/ADR-022-github-issues-as-the-work-register.md)). This backlog owns them
only for the other rows: the deferred A2A work (ADR-022 item 9) and closed or reviewed history.

| Identity | Status | Priority | Scope / next gate |
|---|---|---|---|
| `EVIDENCE-HANDOFF-FEAT-ZED-RENDER-OBSERVATION` | Moved | — | [#296](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/296) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/c99af82365b83eccc6fdb24525cafd2a064c9f09/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L918-L918) |
| ~~`EVIDENCE-HANDOFF-FEAT-REDACTION-GATE`~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Closed 2026-07-31 through commits `2f5e4b8`…`eb5f5d8`. [Archived plan](archive/evidence-handoff-redaction-gate-implementation.md).~~ |
| `EVIDENCE-HANDOFF-FEAT-EVIDENCE-COLLECTOR` | Moved | — | [#294](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/294) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/c99af82365b83eccc6fdb24525cafd2a064c9f09/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L920-L920) |
| `EVIDENCE-HANDOFF-FEAT-A2A-LEDGER` | Reviewed disposition | MEDIUM | Not shipped, not supported, and not trusted after the independent audit returned `NOT SOUND`; merged opt-in code must not be used for trusted workflows. [Archived closure plan](archive/evidence-handoff-a2a-not-shipped-closure_v3.md). Current design authority: [design v2](../specs/evidence-handoff-a2a-ledger-design_v2.md); the frozen [v1 design](../specs/evidence-handoff-a2a-ledger-design.md) is immutable history. |
| ~~`EVIDENCE-HANDOFF-FEAT-A2A-LEDGER-DESIGN-REFRESH`~~ | ~~Closed~~ | ~~MEDIUM~~ | ~~Closed 2026-09-28 by the complete successor [design v2](../specs/evidence-handoff-a2a-ledger-design_v2.md): Docker Desktop store ladder with wslc removed, Option A session protocol admission, and the audit's normative corrections; the operation-entry integrity guard stays owned by `EVIDENCE-HANDOFF-FEAT-LEDGER-INTEGRITY-BOUNDARY`.~~ |
| `EVIDENCE-HANDOFF-FEAT-A2A-CHANNEL` | Open | MEDIUM | Deferred 2026-09-28 by operator decision (estimated two to two-and-a-half weeks including remediation, over the one-week threshold). Owns the [design v2](../specs/evidence-handoff-a2a-ledger-design_v2.md) channel slice: two-seat conversations paired by a ledger-minted code with per-seat cursors; channel activation of `question`, `answer`, `handoff`, and `acknowledgement`; the unattended-exchange budget; and client-owned same-thread scheduled polling for Claude Code and Codex, with Cursor on the operator nudge path. Next gate: an implementation plan whose first task settles the design's `unknown` prerequisites (Codex Windows thread-automation reliability, static-Bearer MCP connectivity), sequenced after the six remediation slices. |
| `EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION` | Open | MEDIUM | Owns audit findings C1, C3, H7, H9, and M15. |
| `EVIDENCE-HANDOFF-FEAT-LEDGER-INTEGRITY-BOUNDARY` | Open | MEDIUM | Owns audit findings C2, H13, and M16c. |
| `EVIDENCE-HANDOFF-FEAT-LEDGER-DATAPATH` | Open | MEDIUM | Owns audit findings H4, H5, and H6. |
| `EVIDENCE-HANDOFF-FEAT-LEDGER-RUNTIME-BOUNDARY` | Open | MEDIUM | Owns audit findings H8, M14, and M16b. |
| `EVIDENCE-HANDOFF-FEAT-LEDGER-AUDIT-WIRING` | Open | MEDIUM | Owns audit finding M16a. |
| `EVIDENCE-HANDOFF-FEAT-LEDGER-EVIDENCE-DOD` | Open | MEDIUM | Owns audit findings H10, H11, and H12b. |
| `EVIDENCE-HANDOFF-FEAT-APPROVAL-RECORD` | Moved | — | [#297](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/297) · [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/c99af82365b83eccc6fdb24525cafd2a064c9f09/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L930-L930) |
| `EVIDENCE-HANDOFF-FEAT-PEER-LIVENESS-SIGNAL` | Open | MEDIUM | Design-needed, unscheduled; requires an explicit heartbeat/session-health mechanism rather than inference from cursor activity. |
| `EVIDENCE-HANDOFF-FEAT-CREDENTIAL-LIFECYCLE` | Open | HIGH | Design-needed OAuth/rotation/`kid`/JWKS/dynamic-registration work, including discovery and Bearer-challenge interoperability. |
| `EVIDENCE-HANDOFF-FEAT-AT-REST-INTEGRITY` | Open | MEDIUM | Design-needed full-chain detector covering historical sequences behind confirmed cursors. |

### P11-FU-37: MAIN-5 Windows evidence-bundle promotion residual

**Moved:** tracked in [#293](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/293). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/c99af82365b83eccc6fdb24525cafd2a064c9f09/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L935-L947).

## A2A ledger audit obligations

This table projects the feature owners above; it is not a second status owner.

| Obligation | Severity | Owning slice | Status | Priority |
|---|---|---|---|---|
| C1 | CRITICAL | `EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION` | Open | MEDIUM |
| C2 | CRITICAL | `EVIDENCE-HANDOFF-FEAT-LEDGER-INTEGRITY-BOUNDARY` | Open | MEDIUM |
| C3 | CRITICAL | `EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION` | Open | MEDIUM |
| H4 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-DATAPATH` | Open | MEDIUM |
| H5 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-DATAPATH` | Open | MEDIUM |
| H6 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-DATAPATH` | Open | MEDIUM |
| H7 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION` | Open | MEDIUM |
| H8 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-RUNTIME-BOUNDARY` | Open | MEDIUM |
| H9 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION` | Open | MEDIUM |
| H10 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-EVIDENCE-DOD` | Open | MEDIUM |
| H11 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-EVIDENCE-DOD` | Open | MEDIUM |
| H12a | HIGH | program gate contract (pre-work, unscheduled) | Open | MEDIUM |
| H12b | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-EVIDENCE-DOD` | Open | MEDIUM |
| H13 | HIGH | `EVIDENCE-HANDOFF-FEAT-LEDGER-INTEGRITY-BOUNDARY` | Open | MEDIUM |
| M14 | MEDIUM | `EVIDENCE-HANDOFF-FEAT-LEDGER-RUNTIME-BOUNDARY` | Open | MEDIUM |
| M15 | MEDIUM | `EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION` | Open | MEDIUM |
| M16a | MEDIUM | `EVIDENCE-HANDOFF-FEAT-LEDGER-AUDIT-WIRING` | Open | MEDIUM |
| M16b | MEDIUM | `EVIDENCE-HANDOFF-FEAT-LEDGER-RUNTIME-BOUNDARY` | Open | MEDIUM |
| M16c | MEDIUM | `EVIDENCE-HANDOFF-FEAT-LEDGER-INTEGRITY-BOUNDARY` | Open | MEDIUM |
| M17 | MEDIUM | archived closure plan | Closed | MEDIUM |

## Settled risks and historical entries

This companion table keeps accepted risks and closed historical entries discoverable without
mixing them into the active follow-up index. Its rows still participate in the exact heading/index
bijection.

| Item                                                                                                                                 | Status               | Priority | Disposition / evidence                                                  |
|--------------------------------------------------------------------------------------------------------------------------------------|----------------------|--------|-------------------------------------------------------------------------|
| Plan 11.7 accepted risk: `optimus-redis` ACP-session durability boundary                                                             | Reviewed disposition | MEDIUM | Accepted bounded durability risk recorded in the entry                  |
| ~~Plan 10.3 frozen-plan status correction (historical)~~                                                                             | ~~Closed~~               | ~~MEDIUM~~ | ~~Frozen source remains unchanged; pool-side correction recorded in the entry~~ |
| ~~`uv.lock` missing direct dependencies: `keyring`, `redis`, and their transitive chain (disclosed 2026-07-23 during Plan 10.1 Task 1)~~ | ~~Closed~~               | ~~MEDIUM~~ | ~~Historical dependency-lock correction retained in the entry~~             |
| ~~Tools: `SurfaceAuditError` frozen-dataclass CI wart (disclosed 2026-07-23 during Plan 10.1 Task 7)~~                               | ~~Closed~~               | ~~MEDIUM~~ | ~~Historical CI correction retained in the entry~~                          |

## Open items

### P9.8-FU-2: Intelligent ambiguous-reference ranking

**Moved:** tracked in [#242](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/242). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L1061-L1077).

### P9.8-FU-3: Dynamic context budgets and required-file summarization

**Moved:** tracked in [#243](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/243). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L1078-L1089).

### P9.8-FU-5: Zed Refusal-Rendering Stability

**Moved:** tracked in [#253](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/253). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L1090-L1125).

### P9.85-FU-1: Intelligent observation compression

**Moved:** tracked in [#244](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/244). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L1126-L1138).

### P9.85-FU-2: Dynamic planning-evidence partition

**Moved:** tracked in [#245](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/245). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L1139-L1150).

### P9.85-FU-3: Cross-Run/Session Spend Policy

**Moved:** tracked in [#257](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/257). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L1151-L1178).

### P9.87-FU-1: Mechanical Current-Raw-Evidence Grounding Guard

**Moved:** tracked in [#258](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/258). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L1179-L1198).

### P11-FU-1: ACP Session Resume Capability

**Moved:** tracked in [#254](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/254). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L1199-L1258).

### P11-FU-2: Package Lookup and Security Advisory Gateway Capability

**Raised:** 2026-07-25 during the Plan 11 Gateway requirement review. At intake, the pinned LLD named
`POST /v1/tools/package/lookup` and `POST /v1/tools/security/advisory` as Gateway-facing typed
endpoints, and §9A/§9B define their package/advisory tool class and routing signals. At intake, the
local repository did not yet implement these Gateway routes as dedicated endpoints. Existing policy
behavior is not absent: `src/optimus/tools/policy.py:85-93` routes `DEPENDENCY_VERSION_CHECK` and
`SECURITY_OR_CVE_CHECK` into `WEB_SEARCH_TRIGGERS`, while LLD §9B's `DEFAULT_POLICY_MATRIX`
(p.26) maps both signals to `ToolClass.PACKAGE_AND_ADVISORY_METADATA`. At intake, dependency and
CVE evidence was therefore served via generic web search, against a different tool class than the
LLD specified. Picking up FU-2 changed existing, tested policy behavior, not merely adding routes.

**Origin:** `docs/Optimus-Cost-Agent-LLD-v2.39.pdf`, §0.D (p.3), §9A (p.24), and §9B (p.25).

**Designated slice:** `P11-FEAT-GATEWAY-TOOLS` (Plan 11.2 at pickup). This capability was
implemented and closed in PR #88 / merge `4590dbf`; future search-independence and migration work
remains owned by the same feature identity. It is not part of the `P9.85-FU-3` cumulative
cross-run policy. The reviewed artifacts are the [design specification](../specs/2026-07-26-plan-11-2-p11-feat-gateway-tools-design.md)
and [implementation plan](archive/2026-07-26-plan-11-2-p11-feat-gateway-tools-implementation.md).

**Acceptance criteria:** The reviewed `P11-FEAT-GATEWAY-TOOLS` design and implementation must:

- define and serve the package-registry lookup and security-advisory request/response contracts;
- route `PACKAGE_AND_ADVISORY_METADATA` using `PACKAGE_VERSION` and `SECURITY_ADVISORY` signals;
- preserve the zero-upstream-credential boundary, Gateway-side provider secrets, policy revalidation, usage/cost
  envelope, and evidence/provenance contracts; and
- provide named unit, integration, and real-Gateway evidence for both endpoint families.

**Closure evidence:** The checked Plan 11.2 Definition of Done and closing approval are recorded
in the [v2 approval record](../reviews/2026-07-27-plan-11-2-implementation-plan-approval-v2.md).
Named evidence reports are the [real local-process HTTP artifact](../../../reports/plan-11-2-gateway-tools-local-process-evidence.md),
[real staging-Gateway artifact](../../../reports/plan-11-2-gateway-tools-staging-evidence.md), and
[fitness/release-gate report](../../../reports/plan-11-2-gateway-tools-task7-fitness.md).

**Status:** Closed. Implemented by PR #88 / merge `4590dbf`; the dedicated package/advisory routes and their
evidence are complete. Remaining migration work stays with `P11-FEAT-GATEWAY-TOOLS` and is not a
reopening of this closed item.

### P11-FU-3: MCP Route/Typed-Contract Publication Gate

**Raised:** 2026-07-25 during the Plan 11 Gateway requirement review. The original LLD §0.B was
clipped at the rendered page boundary around `/v1/tools/web/extract`, and §0.C named MCP tool
brokering without an MCP endpoint or Gateway request/response shape in §0.D.

**Origin:** `docs/Optimus-Cost-Agent-LLD-v2.39.pdf`, §0.B (rendered p.2), §0.C (p.3), and §0.D
(p.3), final SHA-256 `82513729FD1A6E87FAD310DD90A18C996981B68024204E56CCA65377495585DE`.

**Completed source repair:** The v2.39 §0.B clip and hosted-content repair are complete. The
published source is extractable, its component flow is complete, and the §0.B diagram states that
no MCP endpoint is shown or implied. The repair is documentation-complete; it does not authorize
MCP implementation or endpoint inference.

**Operator decision (2026-07-29):** Affirmative—MCP brokering is supported. Operator's stated
rationale: non-negotiable for any agent, especially a coding agent.

**Acceptance criteria (both now met):**

- ~~The operator must explicitly decide whether MCP brokering is supported.~~ Decided 2026-07-29:
  yes.
- ~~The route and typed request/response contract must be represented in the amended, source-pinned
  HLD, LLD, Guardrails, and Test Strategy PDFs.~~ Satisfied 2026-08-06: the MCP Gateway architecture
  amendment charter update (PR #112, merged 2026-08-05) and the publication of all four amended PDFs
  — HLD v2.17, LLD v2.40, Guardrails v1.2, Test Strategy v1.6 (PR #113, merge commit `edd1f04`,
  merged 2026-08-06) — are both live on `main`. Independently confirmed the typed contract is
  actually present, not just nominally referenced: the published LLD contains
  `POST /v1/tools/mcp/discover`, `POST /v1/tools/mcp/call`, and the named component types
  (`MCPProfileRegistry`, `MCPDiscoveryBroker`, `MCPDiscoveryPaginator`, `MCPInvocationBroker`,
  `MCPConnectionManager`).

**Status:** Closed. On 2026-08-06, both acceptance criteria were met. Later pickup produced the
[Plan 11.8 design](../specs/2026-08-06-plan-11-8-p11-feat-gateway-mcp-design.md) and living
[Plan 11.8 implementation plan](archive/2026-08-06-plan-11-8-p11-feat-gateway-mcp-implementation.md).
Its partial checkpoint is 27 of 46 checks complete (Tasks 0-7 and Task 8 Step 1 complete; Task 8
Steps 2-4 and Task 9 incomplete), with implementation in PR #116 and CI custody repair in PR #118.
`P11-FEAT-ZED-RESUME` remains a separate, independently blocked lane.

### P11-FU-4: Re-pin FU-4A/FU-5 Live Evidence

**Moved:** tracked in [#259](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/259). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L1335-L1358).

### P11-FU-5: Windows Subprocess Handle-Duplication Flake (WinError 6/50)

**Moved:** tracked in [#260](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/260). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L1359-L1412).

### P11-FU-29: Durable-approval identity instability on transient Git probe failure

**Raised:** 2026-08-14 by Batch B triage, split from `P11-FU-5`'s historical feasibility findings.

**Classification:** Durable-approval workspace-identity security design concern; not a test flake.

**Origin:** `src/optimus/acp/trusted_paths.py` catches `OSError` from
`_git_repository_root` / `_git_common_dir` and returns `None`. Those values feed the workspace
identity digest that names durable approval. The roadmap records that fault injection of a transient
Windows `WinError 6` makes an otherwise unchanged workspace acquire a different digest and therefore
produce a spurious `NO_APPROVAL`.

**Designated slice:** Plan 11.15, coordinated with but not merged into `P11-FU-18`. Mechanism remains
durable-approval identity instability on transient Git probe failure (`None` conflation).

**Acceptance criteria (draft):** Define the identity contract for transient Git-probe failure,
including whether to fail closed without changing identity, how to retain diagnostic evidence, and
how any digest/migration behavior affects already-issued approvals. Prove the selected behavior by
fault injection. Do not treat a clean rerun of the unrelated Windows handle flake as resolution.

**Status:** Closed. Plan 11.15 SHA `12b881a28b4a736a0d18ccdf1c02c49b94167e41`. Own evidence:
Git tri-state plus three-attempt transient injection, preserve-approval / no-`NO_APPROVAL` through
real `main()`, exact exclusion policy v1, and HMAC-verified observable v2→v3 migration with
inherited-trust limitation. Windows CLI unavailable cases print retry/repair and never
`NO_APPROVAL`. Reports:
[Windows](../../../reports/plan-11-15-windows-durable-approval-identity-evidence.md),
[WSL](../../../reports/plan-11-15-wsl-durable-approval-identity-evidence.md),
[release](../../../reports/plan-11-15-durable-approval-identity-release.md).
Not closed by `P11-FU-18` topology evidence and not closed by a `P11-FU-5` handle-flake rerun.

### P11-FU-6: Gateway `test_server` Full-Suite Port/Teardown Flake

**Moved:** tracked in [#261](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/261). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L1443-L1575).

### P11-FU-7: Windows Coverage/`sys.settrace` Timing Flake in ACP NDJSON Sanitization Test

**Moved:** tracked in [#262](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/262). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L1576-L1641).

### P11.5-FU-1: Map live OTLPSpanExporter FAILURE into Gateway QUEUED/retry semantics

**Raised:** 2026-07-29 during Plan 11.5 Task 4 independent operator verification (and matching
linked task review). Confirmed by reading installed
`opentelemetry-exporter-otlp-proto-http` 1.44.0 `OTLPSpanExporter.export()`: every failure path,
including the exporter's internal retry-with-backoff loop, ends in
`return SpanExportResult.FAILURE` and never raises.

**Origin:** Plan 11.5 Gateway `OpenTelemetryTraceExporter` / `_RetryTrackingSpanExporter` only
classifies `exhausted_transient=True` (→ delivery state `queued`) when the delegate *raises*
`TransientTraceExportError`. Against the real SDK exporter that path is unreachable; unit tests
reach `QUEUED` only via an injected `_AlwaysTransientSpanExporter` double. Live collector
outages therefore surface as `failed` rather than `queued`.

**Severity / non-blocking rationale:** Does not crash the agent, does not mask failure as
success, and does not invent cost/accounting. A genuinely transient network hiccup loses
retry-worthiness signal but remains honest (`failed`). Accepted as non-blocking for Task 4
sign-off; must retain named pool custody before Plan 11.5 close.

**Designated slice:** [Plan 11.21](archive/2026-08-17-plan-11-21-p11-5-fu-1-otlp-failure-delivery-state.md).
Parent slice remains `P11-FEAT-GATEWAY-COST-OBS`; do not silently fold this mapping into an
unfinished Plan 11.5 Task 4/5/8 checkpoint.

**Acceptance criteria:** A future pickup must:

- preserve the four explicit delivery states (`delivered` / `queued` / `failed` /
  `not_configured`) and the rule that a missing endpoint is never reported as successful
  delivery;
- map real `OTLPSpanExporter` / `SpanExportResult.FAILURE` (and any bounded transient class
  the design chooses) into Gateway delivery results without requiring the SDK to raise;
- keep agent-side code free of OTLP/Phoenix endpoints and credentials;
- prove the path with focused unit evidence against a double that returns `FAILURE` (not only
  a raising double), plus at least one live/Phoenix-tier check or an explicit documented
  disposition if live evidence remains Task 8-owned;
- never invent model failure, reverse a completed mutation, or add a model charge when export
  fails.

**Evidence anchors:** Plan 11.5 Task 4 brief/report/review
(`.superpowers/sdd/task-4-*.md` on the Plan 11.5 branch),
`src/optimus_gateway/observability.py`, and `opentelemetry.exporter.otlp.proto.http.trace_exporter`
1.44.0 source for `OTLPSpanExporter.export`.

**Related Task 8 watch (not this FU's scope):** `_emit_spans` starts a fresh empty `Context()`
for every event with no `parent_span_id`, so multiple independent root-level events that share
a wire `trace_id` may land as separate real OTel traces. Task 4 tests only exercise single-root
batches; Plan 11.5 Task 8 real Phoenix evidence must prove or disposition this.

**Status:** Closed. Plan 11.21 live Phoenix collector path **passed** (2 passed). Raising
`_AlwaysTransientSpanExporter`, Plan 11.5 Task 4, and the Task 8 trace-grouping watch are not this
entry's identity. The live test **codifies** the multi-root split as expected behavior
(`root_a_real_trace_id != root_b_real_trace_id`); that watch stays owned by Plan 11.5 Task 8 and is
**not** fixed or closed here. Evidence:
[phoenix evidence](../../../reports/plan-11-21-p11-5-fu-1-phoenix-evidence.md),
[release](../../../reports/plan-11-21-p11-5-fu-1-release.md). Historical unrun:
[Phoenix disposition](../../../reports/plan-11-21-p11-5-fu-1-phoenix-disposition.md).

**Operator confirmation (2026-08-15):** Confirmed at the default `MEDIUM`. The gap changes live
telemetry delivery-state semantics when the real exporter returns `FAILURE`, but the current detail
also records that it does not crash the agent, report success, or invent cost/accounting. No priority
change is made.

### P11-FU-8: Align `OPTIMUS_LOCAL_GATEWAY_BASE_URL` with `OPTIMUS_GATEWAY_<THING>_BASE_URL` naming

**Moved:** tracked in [#263](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/263). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L1703-L1769).

### P11-FU-9: Client-Supplied ACP `mcpServers` Disposition

**Raised:** 2026-07-29 during Plan 11.7 design review after validating the vendored ACP v1 schema.
**Classification:** Protocol-honesty / trust-boundary follow-up; not a Plan 11.7 prerequisite.

**Intake finding (2026-07-29):** ACP requires `mcpServers` on both `NewSessionRequest` and
`LoadSessionRequest`. At raising, Optimus accepted `session/new` while ignoring that field; existing
tests and live payloads sent `[]`. This is not the same system as `P11-FEAT-GATEWAY-MCP`:
ACP `mcpServers` asks the agent to connect outward to client-nominated servers, while Gateway MCP
brokering routes Optimus-owned tool calls through the Gateway. Sequencing Gateway-MCP first would
not resolve the current ACP behavior.

**Designated custody:** This entry owns the cross-lifecycle ACP-input decision for current
`session/new` and future methods, including `session/load`. Plan 11.7 preserves the shipped
posture and records the field without creating a client-nominated connection; it does not claim
that Gateway-MCP implements this capability.

PR #119 subsequently resolved the ignored-`mcpServers` behavior under this entry's acceptance
criteria.

**Acceptance criteria:**

- Decide explicitly whether non-empty client-supplied MCP server arrays are rejected, accepted but
  deliberately unsupported, or honored through a separately reviewed agent-side MCP client.
- Apply the decision consistently to every ACP lifecycle method that carries `mcpServers`; do not
  fix only `session/load` while leaving `session/new` semantically different.
- Preserve the zero-upstream-credential/Gateway trust boundary, reject arbitrary side-effecting connectivity unless
  explicitly authorized, and distinguish client-nominated MCP from Gateway-brokered tools in docs
  and telemetry.
- Add schema-pinned unit tests plus real-client evidence for empty and non-empty arrays, with no
  raw server credentials or untrusted configuration persisted or logged.

**Status:** Closed. All nine tasks were implemented and independently reviewed, then merged to
`main` through PR #119 (`9a93137`) on 2026-08-07. Task 9 completed the documentation/custody audit;
the [closure evidence](../../../reports/p11-fu-9-client-mcp-closure-evidence.md) records the
real-dependency and fitness gates. Design:
[`2026-08-06-p11-fu-9-client-supplied-acp-mcp-servers-design.md`](../specs/2026-08-06-p11-fu-9-client-supplied-acp-mcp-servers-design.md)
(frozen body SHA-256 `66606036b37ddc59cf9f2f4c8a713156a1f839fb771679a16937a5263c9ca4a2`). Deferred capabilities remain
owned by their named backlog headers (descriptor pinning/allowlists, HTTP/SSE trust relaxation,
authenticated upstream evidence, Plan 11.8 `WinError 10053` flake) and are not closed by this entry.
Not a hard prerequisite for Plan 11.7 and not owned by `P11-FEAT-GATEWAY-MCP`.

### P11-FU-10: Complete ACP Error-Code Registry Audit

**Raised:** 2026-07-29 during Plan 11.7 design review after the vendored ACP schema exposed the
current `MUTATION_FORBIDDEN = -32002` collision with ACP `RESOURCE_NOT_FOUND`.
**Classification:** Conformance hardening. The unimplemented forced Plan 11.7 subset is owned by
Plan 11.18 / `P11-FU-10` after the 2026-08-15 operator custody transfer.

**Forced Plan 11.7 subset (now Plan 11.18):** On `7da16b6` the live collision was: reserve ACP
`-32002` for `RESOURCE_NOT_FOUND`, relocate ACP-adapter mutation refusal to Optimus code `-32910`,
map duplicate-ID refusal to `-32911`, and remove the duplicate raw wire-code constant from
`src/optimus/runtime/mutation.py`. That forced Plan 11.7 subset is completed by Plan 11.18 because frozen
Plan 11.7 is blocked. The 2026-08-15 operator ruling transferred this custody forward-only; frozen
Plan 11.7 files and amendments are unchanged and `session/load` work is not unblocked.

**This entry also retains the general audit:**

- audit `DUPLICATE_REQUEST_ID = -32001` against ACP/JSON-RPC allocations and actual client
  behavior;
- eliminate remaining production raw error-code literals outside the central ACP registry;
- reduce the Plan 11.7 exact path-and-symbol legacy allowlist to zero; and
- retain frozen historical plan references as expected evidence rather than rewriting history.

**Acceptance criteria:**

- A schema-derived oracle proves registry uniqueness, disjointness from ACP allocations, and
  exclusion from JSON-RPC's complete `-32768…-32000` reserved band for Optimus application codes.
- An AST-based source audit rejects raw JSON-RPC/application code literals outside the central
  registry. Any temporary baseline allowlist is exact by path and symbol and cannot grow.
- Runtime exceptions remain semantic; the ACP adapter alone maps them to wire codes.
- Current user-facing documentation is updated when codes move, while frozen historical plans
  remain byte-for-byte historical records with explicit audit disposition.

**Status:** Closed. Implemented through [Plan 11.18](archive/2026-08-15-plan-11-18-acp-error-code-registry-audit-implementation.md)
and draft PR #158. Mutation refusal moved from ACP `-32002` (`RESOURCE_NOT_FOUND`) to Optimus `MUTATION_FORBIDDEN = -32910`;
duplicate-ID refusal moved from reserved-band `-32001` to `DUPLICATE_REQUEST_ID = -32911`. The
schema-derived registry oracle and the AST oracle (`EXPECTED_LEGACY_ERROR_CODE_SITES == frozenset()`)
prove the allocation. Real-`acpx` 0.12.0 evidence:
[plan-11-18-p11-fu-10-acpx-error-code-evidence.md](../../../reports/plan-11-18-p11-fu-10-acpx-error-code-evidence.md).
Frozen Plan 11.7 bytes are unchanged and `session/load` was not transferred.

**Operator-confirmed triage justification for HIGH (2026-08-15):** Wrong ACP/application codes
reaching real clients can cause protocol errors to be misclassified. The operator confirmed HIGH
and approved transferring the unimplemented forced Plan 11.7 subset to Plan 11.18.

### P11.7-FU-1: Configurable Gateway request timeout for debug/investigation workflows

**Raised:** 2026-07-30 during Plan 11.7 Task 0 Case 1 live Zed evidence capture, by operator
([Vibhanshu]).

**Origin / core problem:** `GatewayClient` hardcodes `timeout_seconds: float = 30.0`
(`src/optimus/gateway/client.py:96`) with no override anywhere — both construction sites in
`bootstrap.py` (lines 72, 129) call `GatewayClient(settings=settings)` unconditionally. During live
Task 0 evidence capture, `z-ai/glm-5.2` via OpenRouter twice exceeded the 30s window on the
identical fixture/task that had succeeded in ~16s moments earlier, terminating the planning loop as
`PLANNING_GATEWAY_COST_UNKNOWN` — a deliberate fail-closed path
(`planning_loop.py:907-912,953-956`: unknown transport cost stops rather than risks a silent
double-charge on retry). That safety behavior is correct and must not be weakened. The problem is
that there is no way to raise the timeout without a code change, so any investigation/debug
workflow is at the mercy of whatever a given model's live latency happens to be.

**Deliverable:** An overridable Gateway request timeout for debug/investigation workflows (e.g. an
env var and/or CLI flag consumed where `bootstrap.py` constructs `GatewayClient`), leaving default
production behavior (30s, fail-closed on unknown cost) unchanged when unset.

**Designated future plan:** None yet named — tracked in this pool until scheduled. Do not silently
fold into Plan 11.7 Task 0 / implementation without a reviewed versioned successor; Plan 11.7 must keep
the fail-closed unknown-cost path unchanged.

**Acceptance criteria (draft — refine at pickup):**

- A documented override raises `GatewayClient`'s effective `timeout_seconds` for a single
  invocation/session.
- Default behavior (30s timeout, fail-closed/no-retry on unknown cost) is unchanged when the
  override is not set.
- The override is discoverable (e.g. `optimus-agent --help`), not just a source-level constant.

**Evidence anchors:** `src/optimus/gateway/client.py:96`; `src/optimus/acp/bootstrap.py:72,129`;
`src/optimus/agent/planning_loop.py:907-912,953-956`; live Task 0 Case 1 Zed captures 2026-07-30
(two consecutive `PLANNING_GATEWAY_COST_UNKNOWN` timeouts on `z-ai/glm-5.2`, ~30s each, vs. a prior
successful ~16s response on the identical fixture/task, same worktree).

**Status:** Closed. Implemented and merged to `main` through PR #123 (implementation commit `d0253be`, merge commit `11448fe`). All Plan 11.9 Definition-of-Done gates were independently re-verified on Windows (focused tests, full suite, coverage ≥80%, Ruff, diff-check, `--help`); no dedicated `reports/` evidence bundle is required for this single-commit CLI-only follow-up.

### P11.7-FU-2: Gateway threaded-test flake under full-suite load

**Raised:** 2026-08-02 during Plan 11.7 origin-A fixture v2 Task 3 review prep.
**Classification:** MISFILED duplicate of `P11-FU-6`; not a Task 3 blocker.

**Origin:** Pre-existing Gateway threaded-test instability observed under full `tests/unit`
suite load (not introduced by origin-A fixture v2 supersession/ledger work).

**Designated custody:** `P11-FU-6` only. Batch B reproduced the same current `test_server.py`
ThreadingHTTPServer/`WinError 10053` class under full-suite load; this entry had no independently
identified node or mechanism.

**Disposition (2026-08-14):** Merge into `P11-FU-6`; do not create a second Gateway harness plan.

**Status:** Closed. Misfiled duplicate; `P11-FU-6` retains the live Gateway harness custody.

### P11.7-FU-3: Committed `plan117_custody_relay.py` docstring `\ufffd` / em-dash corruption

**Moved:** tracked in [#255](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/255). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L1911-L1927).

### P11-FU-11: Plan 11.7 Retry Preflight and Live Session Proof

**Moved:** tracked in [#256](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/256). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L1928-L1990).

### P11-FU-12: MCP OAuth 2.1 Lifecycle

**Raised:** 2026-08-05 by the approved MCP Gateway architecture redline.

**Designated custody:** This entry owns a future MCP OAuth 2.1 lifecycle design; a Plan 11.x number
is assigned only when it is picked up.

**Rationale and acceptance boundary:** v1 has static credential profiles only. OAuth acquisition,
token custody, and step-up are absent. A future design must keep automatic same-binding refresh
distinct from reapproval-triggering grant, issuer, resource, subject, scope, client, store, or
policy rotation.

**Status:** Closed. Won't-do because Plan 11.12 retired the Gateway MCP feature. This follow-up
targeted Gateway-brokered OAuth 2.1 lifecycle that no longer exists. Identifier preserved.

### P11-FU-13: Deferred MCP Capabilities and Long-Lived Interaction

**Raised:** 2026-08-05 by the approved MCP Gateway architecture redline.

**Designated custody:** This entry owns future prompts, resources, elicitation, completion,
subscriptions, tasks, and resumable discovery-cursor checkpoints; a Plan 11.x number is assigned
only when it is picked up.

**Rationale and acceptance boundary:** These capabilities need new trust and user-experience
vocabulary. Roots are not access control; sampling reverses the prompt/cost direction and retains a
separate double-human-approval and linked-accounting gate. External MCP logging remains unable to
alter Optimus audit logging.

**Status:** Closed. Won't-do because Plan 11.12 retired the Gateway MCP feature. This follow-up
targeted Gateway-brokered prompts, resources, elicitation, completion, subscriptions, tasks, and
resumable discovery that no longer exist. Identifier preserved.

### P11-FU-14: MCP Registry Discover-and-Connect

**Raised:** 2026-08-05 by the approved MCP Gateway architecture redline.

**Designated custody:** This entry owns future MCP catalog, discover, install, update, connect, and
activation semantics; a Plan 11.x number is assigned only when it is picked up.

**Rationale and acceptance boundary:** Catalog metadata is not code trust or operator approval.
Automated install, update, or connect would invalidate v1's preprovisioned-only safety answer.
This is explicitly distinct from ACP registry publication identity and release work under
`P11-FEAT-REGISTRY`.

**Status:** Closed. Won't-do because Plan 11.12 retired the Gateway MCP feature. This follow-up
targeted Gateway catalog/discover/install/update/connect semantics that no longer exist. Identifier
preserved. Distinct from ACP registry publication identity under `P11-FEAT-REGISTRY`.

### P11-FU-15: MCP Tool Search and Context Minimization

**Raised:** 2026-08-05 by the approved MCP Gateway architecture redline.

**Designated custody:** This entry owns future semantic per-turn tool selection and context
minimization; a Plan 11.x number is assigned only when it is picked up.

**Rationale and acceptance boundary:** v1 bounds and records an operator-selected descriptor subset,
but provides no semantic per-turn selection seam and no code-mode sandbox.

**Status:** Closed. Won't-do because Plan 11.12 retired the Gateway MCP feature. This follow-up
targeted Gateway-brokered semantic per-turn tool selection that no longer exists. Identifier
preserved.

### P11-FU-16: Reverse Research-to-Documentation Freshness Gate

**Moved:** tracked in [#264](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/264). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L2053-L2070).

### P11-FU-22: Durable effect-aware MCP indeterminate-call custody

**Raised:** 2026-08-06 during Plan 11.8 Task 7 closure review.

**Designated custody:** This entry owns durable effect-aware MCP indeterminate-call custody: read-only
explicit re-invocation and side-effecting operator-acknowledgment hold across agent restart. The
follow-up identifier and Plan 11.x number are assigned only when this item is picked up.

**Acceptance criteria:** Extend `PreToolGuard` and its approval store so a post-dispatch timeout or
loss is durably classified by effect: read-only calls can be explicitly re-invoked with the original
binding and `gateway_request_id`, while side-effecting calls remain held until an operator
acknowledges the outcome. Custody must survive agent restart, preserve no-automatic-redispatch
behavior, and produce auditable disposition and accounting evidence.

**Status:** Closed. Won't-do because Plan 11.12 retired the Gateway MCP feature. This follow-up
targeted Gateway-brokered indeterminate-call custody (`gateway_request_id` re-invocation / hold)
that no longer exists. Identifier preserved.

### P11-FU-23: Durable client-MCP descriptor-surface pinning and named tool allowlists

**Moved:** tracked in [#265](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/265). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L2089-L2102).

### P11-FU-24: Client-MCP durable HTTP/SSE trust relaxation

**Moved:** tracked in [#266](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/266). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L2103-L2116).

### P11-FU-25: Authenticated client-owned MCP upstream evidence

**Moved:** tracked in [#267](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/267). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L2117-L2130).

### P11-FU-26: Plan 11.8 Windows `WinError 10053` MCP test flake

**Raised:** 2026-08-06 during the paused Plan 11.8 Gateway-MCP lane's test review.

**Designated custody:** This entry owns investigation of the intermittent Windows connection-aborted
(`WinError 10053`) MCP test failure. The follow-up identifier and Plan 11.x number are assigned only
when this item is picked up.

**Acceptance criteria:** Establish a minimized reproduction or bounded no-reproduction evidence;
separate test-fixture teardown/network timing from product behavior; reproduce on Windows and WSL2
where relevant; and avoid weakening production transport safety or masking the failure with retries.

**Status:** Closed. Obsolete-by-retirement: Plan 11.12 removed the Gateway MCP transport and test
code that this investigation targeted, so the original reproduction criteria can no longer be
performed meaningfully. The observed Windows `WinError 10053` socket-teardown signal is transferred
to still-open `P11-FU-6`, which owns Gateway `test_server` port/teardown flake custody. No production
retry or safety weakening was added.

### P11-FU-27: Publication-Plan Historical-State Reconciliation

**Raised:** 2026-08-11 during the Plan 11.10 closing audit, after the named reconciliation owner was
found only in a gitignored task report and an untracked implementation-plan artifact rather than in
the pool.

**Origin:** The excluded
[`archive/2026-08-05-mcp-gateway-architecture-amendment-publication-plan.md`](archive/2026-08-05-mcp-gateway-architecture-amendment-publication-plan.md)
retains historical Task 10 Steps 1-7 as unchecked and still says the four architecture PDFs await
approval, although their final hashes match
[`verification.md`](../../sources/mcp-gateway-architecture-amendment/verification.md) and PR #113
delivered the publication. Task 11 Step 7 is correctly unchecked and is not part of that correction.

**Designated custody:** This entry owns only the publication plan's historical checkbox/status
reconciliation. Pickup requires a separate reviewed scope and the next linear plan number available
at that time; do not fold the edit into another documentation cleanup.

**Acceptance criteria:** Reconcile Task 10 Steps 1-7 and the stale awaiting-approval prose only
against the four published PDF hashes in `verification.md` and PR #113; preserve Task 11 Step 7
unless independent evidence satisfies it; retain the publication plan's historical evidence; and
avoid changing unrelated architecture or implementation scope.

**Status:** Closed. Plan 11.22 reconciled only the historical Task 10 Steps 1-7 and stale
pending-publication wording after independently verifying the four published PDF hashes against
`verification.md` and merged PR #113. Task 11 Step 7 remains unchecked. Evidence:
[Plan 11.22 reconciliation report](../../../reports/plan-11-22-p11-fu-27-publication-reconciliation.md).

### P11-FU-17: WSL2 native git cannot parse a Windows-git-created linked worktree's `.git` pointer

**Raised:** 2026-08-06 during the MCP Gateway architecture amendment publication plan's Task 11 WSL2
full-suite gate.

**Classification:** Resolved test-infrastructure operating decision; not a code defect.

**Origin:** A linked worktree created by Windows' `git.exe` writes its `.git` file as
`gitdir: D:/Projects/Development/Python/optimus-cost-agent/.git/worktrees/<name>` — a correct,
absolute path for Windows git. When that same worktree is accessed from WSL2 and `git` resolves to
Ubuntu's own `/usr/bin/git` (wins over `/mnt/c/Program Files/Git/...` because native `/usr/bin`
entries sit earlier in WSL's default `PATH`), that Linux git binary cannot parse `D:/...` as
absolute, treats it as relative, and prepends the current directory — producing a self-evidently
mangled path in the error (`fatal: not a git repository:
/mnt/d/.../<worktree>/D:/Projects/Development/Python/...`).

**Reproduction:** Fully deterministic — reproduced identically 3 times across 2 independent reviewer
reruns plus the executing agent's own reconciliation rerun, both during Task 11 and again during
Task 12's final WSL2 suite rerun. Any test that shells out to `git` inside such a worktree fails
with returncode 128 every time, for as long as that worktree exists and is tested via native WSL
git — currently observed via
`tests/unit/docs/test_open_work_pool_hygiene.py::test_product_checkpoint_log_location_remains_gitignored`
(which calls `git check-ignore`), but the mechanism is general and not specific to that one test.

**Suspected cause:** Not a code defect — confirmed root cause is the PATH-resolution mismatch above,
not an assertion or production-code problem. A disposable Git-wrapper diagnostic (redirecting WSL's
`git` to the Windows binary for one run) did make the suite pass, but was correctly not counted as
clean POSIX evidence since it changes what is being tested rather than fixing the underlying
mismatch.

**Related prior art:** A different flake class from `P11-FU-5`/`P11-FU-6`/`P11-FU-7` (those are
Windows-native subprocess/coverage timing races; this is WSL2-against-a-Windows-worktree path
resolution) — do not conflate root causes across these entries at pickup.

**Designated slice:** Resolved by the native WSL clone operating decision; no numbered plan or source
change is required.

**Closure criteria (satisfied 2026-08-14):** Demonstrate the current mounted-worktree failure,
choose a POSIX-valid operating environment, retain both Git-calling assertions unchanged, and prove
they pass there under native `/usr/bin/git`. Record the setup and any mounted-worktree exception
rule so future Linux gates do not re-diagnose the pointer mismatch.

**Evidence anchors:** MCP Gateway architecture amendment publication plan Task 11/12 review notes;
`tests/unit/docs/test_open_work_pool_hygiene.py::test_product_checkpoint_log_location_remains_gitignored`.

**Resolution (2026-08-14):** Linux/CI-parity gates run only from a native WSL clone on the WSL ext4
filesystem (for example `~/src/optimus-cost-agent`), never from a Windows-created linked worktree
under `/mnt/d`. The clone is a normal POSIX checkout, not a linked worktree, so native `/usr/bin/git`
resolves its `.git` metadata end to end. The standing setup and exception rule are in
[`docs/runbooks/local-live-dependencies.md`](../../runbooks/local-live-dependencies.md#12-wsl2-linuxci-parity-gates).

**Rejected alternatives:** A repo-local PATH override to Windows `git.exe` can make the tests pass,
but changes the POSIX implementation being tested and crosses the WSL/Windows boundary for every Git
call. A WSL-created linked worktree fixes this particular pointer yet remains on slower `drvfs` and
introduces mixed-path administrative metadata in the shared `.git` that Windows Git cannot reliably
consume. Neither is the supported gate environment.

**Proof:** On native ext4 clone `/root/optimus-cost-agent-p11-fu-17-proof`, `/usr/bin/git` 2.43.0
at `origin/main` `2770e0f` ran `pytest tests/unit -q` with **2973 passed, 11 skipped, 1 warning**
in 72 wall-clock seconds. The two unchanged former FU-17 selectors
`test_immutable_documents_match_approved_head_blobs` and
`test_product_checkpoint_log_location_remains_gitignored` then passed explicitly (2 passed).
The equivalent isolated mounted-worktree run produced **2971 passed, 11 skipped, 2 failed** in 96
seconds, and its only failures were those two selectors with the documented native-Git `D:/...`
pointer error. Full command, environment, and virtual-environment isolation evidence are recorded in
[`reports/p11-fu-17-wsl-native-clone-evidence.md`](../../../reports/p11-fu-17-wsl-native-clone-evidence.md).

**Status:** Closed. Native WSL clone decision accepted and demonstrated; no test assertion or
production code changed.

### P11-FU-28: WSL2 `uv sync` shared-Windows-`.venv` destruction hazard

**Raised:** 2026-08-14 during corrected Batch A triage on `origin/main`.

**Classification:** Obsolete under the resolved native-WSL-clone operating decision; not a
product-code defect.

**Origin:** A WSL2 `uv sync` against a Windows-hosted worktree can select and replace the
repository's shared Windows `.venv`, corrupting the Windows environment and making the WSL
evidence non-isolated.

**Resolution (2026-08-14):** The accepted `P11-FU-17` native ext4 clone has its own `.venv`.
With `UV_PROJECT_ENVIRONMENT` unset, `uv sync --frozen --extra dev` created
`/root/optimus-cost-agent-p11-fu-17-proof/.venv`. A before/after fingerprint of the dedicated
Windows worktree's `.venv/pyvenv.cfg` was identical (length 184, SHA-256
`9C503845220632572999AAD4D94004D287277EC4971A5230D8A12FCD3EE91AFB`, unchanged UTC mtime).
The supported Linux-parity workflow therefore has no shared Windows environment to destroy.

**Exception rule:** A temporary diagnostic run from a mounted Windows worktree remains unsupported
as Linux-parity evidence and must set `UV_PROJECT_ENVIRONMENT=/tmp/<task>-venv`; if it clobbers a
Windows `.venv`, restore it with Windows `uv sync --frozen --extra dev`. This is an operating note,
not a remaining scheduled follow-up.

**Status:** Closed. Obsolete for supported native-clone gates; the exception rule remains in the
runbook and proof report.

### P11-FU-18: Workspace-identity `ctime` coalescing fail-open

**Raised:** 2026-08-06 during the MCP Gateway architecture amendment publication plan's Task 12 final
WSL2 suite rerun.

**Classification:** Durable-approval workspace-identity security concern; prior test-infrastructure
classification was misfiled.

**Origin:**
`tests/unit/acp/test_trusted_paths.py::TestWorkspaceIdentityRevalidation::test_revalidation_fails_after_workspace_directory_metadata_change`
asserts that adding a file to a directory changes that directory's `st_ctime_ns` (part of the
workspace-identity digest `resolve_workspace_identity`/`revalidate_workspace_identity` use for
path-trust revalidation in `src/optimus/acp/trusted_paths.py`), with no sleep between the two
`stat()` calls. A direct filesystem probe in this WSL2 environment confirmed `st_ctime_ns` can read
identically across two `stat()` calls that bracket a real file-creation write, despite genuine
elapsed wall-clock time between them. Because `resolve_workspace_identity()` binds that value into
the durable workspace identity digest, and `revalidate_workspace_identity()` accepts an unchanged
digest, the coalescing can fail open for an in-place workspace-directory change whose path,
device, inode, and Git topology remain unchanged.

**Reproduction:** Nondeterministic. Original isolation probe (2026-08-06): 4 passed, 1 failed in 5
standalone runs. Refined (2026-08-07 Task 7 review): 2 failures in 5 repeated isolated runs on
WSL2 — confirmed as a timing race even without full-suite load, not an order-dependent or
environment-static failure. Not caused by P11-FU-9 Task 7 (different file list).

**Suspected cause:** WSL2's virtual-disk-backed filesystem appears to coalesce or truncate directory
`ctime` updates under some timing conditions, unlike the nanosecond-resolution behavior the test
assumes. This is distinct from `P11-FU-17`: that entry is a git-binary PATH-resolution problem;
this one is filesystem-timestamp granularity/coalescing, and the two must not be conflated at
pickup even though both surfaced during the same WSL2 gate runs.

**Related prior art:** Same general "WSL2 as CI substitute has its own environment quirks" class as
`P11-FU-17`, but a different mechanism. Also loosely related to the Windows-native timing flakes
(`P11-FU-5`, `P11-FU-6`, `P11-FU-7`) in spirit (test asserts on OS-timestamp/scheduling behavior
without a sleep) but on a different platform and different underlying primitive.

**Designated slice:** Plan 11.15. Mechanism remains workspace-identity `ctime` coalescing fail-open.
It must define a cross-filesystem tamper-detection invariant before any production change.

**Acceptance criteria (draft — refine at pickup):**

- Preserve fail-closed revalidation when an authorized workspace changes in place, across the
  supported filesystem matrix; a passing rerun cannot establish this property.
- Design and review a reliable replacement or augmentation for the weak metadata signal. Do not use
  sleeps, retries, or marker skips to conceal it.
- Define migration and durable-approval invalidation behavior before changing the identity digest.

**Evidence anchors:** MCP Gateway architecture amendment publication plan Task 12 review notes;
`tests/unit/acp/test_trusted_paths.py::TestWorkspaceIdentityRevalidation::test_revalidation_fails_after_workspace_directory_metadata_change`;
`src/optimus/acp/trusted_paths.py` (`resolve_workspace_identity`, `revalidate_workspace_identity`).

**Status:** Closed. Plan 11.15 SHA `12b881a28b4a736a0d18ccdf1c02c49b94167e41`. Own evidence: `st_ctime_ns`
removed from v3 identity; non-excluded `added-after-authorization` with equal before/after ctime
fails closed as `WORKSPACE_IDENTITY_CHANGED`/`root_topology_mismatch`
(`test_fu18_equal_ctime_non_excluded_add_is_root_topology_mismatch`, unguarded on Windows and native
WSL). Topology add/remove/rename and symlink-retarget named. Residuals: compiled exclusion drop
locations and path/topology TOCTOU (not content integrity). Reports:
[Windows](../../../reports/plan-11-15-windows-durable-approval-identity-evidence.md),
[WSL](../../../reports/plan-11-15-wsl-durable-approval-identity-evidence.md),
[release](../../../reports/plan-11-15-durable-approval-identity-release.md).
Not closed by `P11-FU-29` Git-retry or preserve-approval evidence.

**Recurrence:** 2026-08-07 during P11-FU-9 Task 4 independent review (operator + Cursor WSL full
`tests/unit` runs). The same node failed intermittently under full-suite WSL/DrvFs load and passed
standalone — same custody as this entry; do not open a duplicate FU.

**Refinement (2026-08-07, P11-FU-9 Task 7 review):** Confirmed flaky even in isolation — 2 failures
in 5 repeated standalone runs on WSL2, not only under full-suite load. Characterization upgraded
from "full-suite-only" to "standalone-reproducible ctime coalescing race"; still not a product defect
and still unrelated to Task 7's file list.

### P11-FU-19: WSL client-SDK operation-deadline supervisor race

**Raised:** 2026-08-07 during P11-FU-9 Task 4 independent review (operator Vibhanshu / Cursor).

**Classification:** Test-harness/supervisor timing race; requires a written reliability plan. Not a
Task 4 feature regression.

**Origin:**
`tests/unit/mcp/test_client_sdk.py::test_operation_deadline_is_enforced` uses a 0.2s
`operation_timeout_seconds` budget around a deliberately slow fake `initialize`. Corrected Batch A
triage on a fresh `origin/main` worktree reproduced 2 failures in 100 standalone WSL2 runs (2%).
Both failures were `MCPSupervisorError(code="SUBMIT_TIMEOUT")` from the outer
`future.result(timeout=1.2)`, rather than the expected `ClientMcpSdkError(code="OPERATION_TIMEOUT")`
from the inner `asyncio.wait_for(..., timeout=0.2)`. One full `tests/unit` WSL2 run passed this
node; its only two failures were the known P11-FU-17 native-Git-pointer tests.

**Mechanism:** The cross-thread supervisor's outer 1.2s wait can expire before the event-loop task
reaches its inner 0.2s timeout. This makes host scheduling the test oracle and exposes either a
supervisor-start/readiness race or an inadequately controlled deadline seam. It is not evidence
that the production 30s default deadline should change.

**Designated slice:** [Plan 11.16](archive/2026-08-15-plan-11-16-p11-fu-7-19-deadline-seams.md). Production
client-MCP deadline unification; Batch A 2/100 standalone WSL correction remains the diagnosis.

**Acceptance criteria (draft — refine at pickup):**

- Preserve the assertion that an over-budget initialize raises
  `ClientMcpSdkError(code="OPERATION_TIMEOUT")`, while removing host scheduling as its oracle.
- Design a controlled supervisor-readiness/deadline test seam; do not widen the 0.2s test budget
  merely to reduce the hit rate, and do not change the production 30s default deadline.
- Establish whether the controlled seam belongs solely in the test harness or requires a
  production supervisor readiness contract before implementation.
- Keep custody distinct from `P11-FU-7` (Windows coverage/trace) and `P11-FU-18` (ctime coalescing).

**Evidence anchors:** P11-FU-9 Task 4 review notes (2026-08-07);
`tests/unit/mcp/test_client_sdk.py::test_operation_deadline_is_enforced`;
`src/optimus/mcp/client_sdk.py`.

**Related prior art:** `P11-FU-7` (NDJSON / coverage timing), `P11-FU-18` (WSL ctime), and the
Task 2 review note that the NDJSON flake remains backlog-owned and non-blocking.

**Status:** Closed. Plan 11.16 production correction: SDK `open`/`discover`/`call`/streamed-byte
entries use exact `operation_timeout_seconds` and surface `ClientMcpSdkError("OPERATION_TIMEOUT")`.
Direct generic supervisor expiry remains `MCPSupervisorError("SUBMIT_TIMEOUT")`. Evidence:
[Windows](../../../reports/plan-11-16-p11-fu-19-windows-evidence.md),
[WSL](../../../reports/plan-11-16-p11-fu-19-wsl-evidence.md). SHA `6159200`. The 0.2s test budget
and 30s production default were not widened. No retry/replay.

### P11-FU-20: Attach per-server catalog/authorizer to session tool service for real one-call issuance

**Moved:** tracked in [#223](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/223). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L2391-L2442).

### P11-FU-21: Custody Relay Broken-Pipe Exit-Code Propagation Defect

**Raised:** 2026-08-11 during PR #128 guardrails / `clean-environment-recheck` on
`ubuntu-latest` (operator Vibhanshu / Cursor).

**Classification:** MISFILED product bug; not a test-infrastructure flake.

**Origin:**
`tests/unit/tools/test_plan117_custody_relay.py::test_eof_either_direction_and_child_first_exit`
failed once with `assert exit_code == 7` observing `1` — the custody-relay child process exited
`1` instead of the expected `7`. Not a WinError, not an assertion about payload content.

**Environment:** GitHub Actions guardrails / `clean-environment-recheck` on `ubuntu-latest`,
PR #128, full suite (3148 passed, 12 skipped, 116 deselected). Immediate re-run with **no code
change** was green — no durable local reproduction.

**Not caused by PR #128:** that branch never touched any `plan117` path, and the code is
pre-existing on `main` (`128af65` is an ancestor of `origin/main`). The commit immediately
before the failure was docs-only (+25 lines of markdown).

**Batch B root cause (2026-08-14):** In the observed child-first-exit race, the child correctly
exits `7` and the parent-to-child forwarding task then receives the normal `BrokenPipeError` caused
by writing its remaining input to the already-exited child. `run_relay()` records that exception,
sets `REASON_BROKEN_PIPE`, terminates/cleans up, and unconditionally returns `1` whenever a reason
code exists. The relay therefore overwrites the child exit code rather than the test misreading it.

**Related prior art — do not merge:** Distinct from `P11-FU-5` (Windows-specific WinError 6/50
handle duplication) and from `P11.7-FU-3` (docstring `\ufffd` / em-dash corruption in the same
file). Neither entry covers this relay behavior defect.

**Designated slice:** Plan 11.14
([`archive/2026-08-14-plan-11-14-p11-fu-21-custody-relay-exit-code.md`](archive/2026-08-14-plan-11-14-p11-fu-21-custody-relay-exit-code.md)).

**Acceptance criteria:** Define the contract for expected child-first exit and the error precedence
between benign post-exit pipe closure and true relay failure; preserve real relay errors; implement
only after a reviewed product plan; and retain the EOF / exit-code assertions as proof.

**Evidence anchors:** PR #128 CI run that failed then passed on re-run with no code change;
`tests/unit/tools/test_plan117_custody_relay.py::test_eof_either_direction_and_child_first_exit`;
`tools/plan117_custody_relay.py`; precursor Linux socket-path fix `128af65`.

**Resolution (2026-08-14):** Plan 11.14 restores opaque-relay transparency. `BrokenPipeError` with
non-`None` pre-cleanup `proc.poll()` returns that child code and records `child_exited` /
`reason_code is None`. `BrokenPipeError` with `proc.poll() is None` remains exit `1`,
`broken_pipe`, and `REASON_BROKEN_PIPE`. Interruption and recorder-failure paths still force `1`.
A deterministic stdin-boundary injection test fails red at `assert exit_code == 7` observing `1`
before the edit and proves `7` / `child_exit_code == 7` / `child_exited` after it. The unchanged
`test_eof_either_direction_and_child_first_exit` is 200/200 on the native WSL ext4 clone. Full
suite, bare `--cov` >=80, Ruff, pool hygiene, and sealed-artifact hash equality are in
[`reports/plan-11-14-p11-fu-21-custody-relay-exit-code-evidence.md`](../../../reports/plan-11-14-p11-fu-21-custody-relay-exit-code-evidence.md).

**Status:** Closed. Plan 11.14 implemented the known-exit versus unknown-pipe discriminator; PR #128
and Batch B remain the historical discovery record.

### P11.5-FU-2: Consistent local env / Redis / Phoenix / Gateway startup for live runs

**Raised:** 2026-07-29 during Plan 11.5 Task 8 (real Redis / Phoenix / ACP release-evidence
capture), by operator ([Vibhanshu]). Surfaced while attempting live E7 `acpx` capture and
`requires_gateway` evidence and hitting four inconsistent mechanisms for getting local
dependencies running before landing on a workaround.

**Origin / core problem at raising (2026-07-29):** `optimus-agent` startup (`__main__.py`) resolved
runtime configuration from the OS keychain + sensible defaults with **zero required env vars** — the
documented Plan 9.7 / Plan 9.6 Phase C "no `.env` files required" path, confirmed then working. But
`src/optimus/acp/subprocess_env.py`'s `build_acp_subprocess_env` (used by both the Plan 11.5 Task 8
`acpx` evidence tool and the older Plan 9.87 one) imposed a separate, stricter gate that
`OPTIMUS_GATEWAY_URL` / `OPTIMUS_API_KEY` / `OPTIMUS_REDIS_URL` be **explicitly present in the
shell**. That stricter gate is not technically required by the agent contract and is what forced
a manual workaround during Task 8.

**Four divergent mechanisms found on 2026-07-29 (do not add a fifth):**

1. **`optimus-agent` auto-start** (`ensure_local_gateway` / `ensure_local_redis`) — zero env vars,
   keychain-based, non-interactive.
2. **`optimus-trust run-gateway`** — interactive ceremony, TTY-required, displays a config
   snapshot.
3. **`tools/run_local_gateway.sh` / `.ps1`** — look like standalone non-interactive launchers
   (names/docstrings still describe old direct-source behavior) but now just delegate to #2.
4. **`build_acp_subprocess_env`** — a stricter, explicit-env-var gate layered on top of #1 for
   evidence tooling specifically.

**Explicit requirement — consolidate, don't bolt on another option:** The fix must reduce this
to **one clear path**. Preferred direction: make #4 honor #1's proven keychain-only contract. If
evidence-capture truly needs stricter/explicit config, that divergence must be deliberate and
documented — and #3 must be deleted or clearly repointed so it is not a false lead. Whichever
direction, there must be exactly one documented answer to "how do I get local deps running for a
live run," not several scripts that look interchangeable but aren't.

**Also found at raising (2026-07-29):** No launcher existed for **Phoenix** — only an inline
`docker run` hint was buried in a test docstring. Plan 11.6 / PR #97 subsequently added the
`optimus-phoenix` launcher using `arizephoenix/phoenix:latest` on port 6006, with `/healthz` and
port-identity checks, and documented the living runbook. Phoenix is now part of the same local
dependency mechanism rather than an ad-hoc path.

**Deliverable:** One short operator runbook (matching the existing Plan 9.6 Phase C runbook
precedent at
`docs/runbooks/plan-9-6-phase-c-operator-path.md`) that is the **single
source of truth**, backed by code that actually matches what the runbook says — not a doc layered
on top of still-divergent scripts.

**Designated slice / plan shape:** Future small dedicated startup/runbook consolidation plan
(Plan number assigned at pickup). Do **not** silently fold into an unfinished Plan 11.5 Task 8
checkpoint without a reviewed amendment; retain named pool custody before Plan 11.5 close.

**Acceptance criteria (draft — refine at pickup):**

- Exactly one documented, operator-usable path for local Redis + Gateway (+ Phoenix where needed)
  for live/evidence runs.
- `build_acp_subprocess_env` either honors the keychain-only agent contract (#1) or documents and
  tests a deliberate, reviewed divergence — no implicit stricter shell-env gate.
- `tools/run_local_gateway.sh` / `.ps1` either match that single path (names + behavior) or are
  removed/repointed so they cannot mislead.
- Phoenix local startup is part of the same mechanism/runbook (not a fifth ad-hoc docker hint).
- Runbook text and code paths are verified against each other (presence tests and/or a focused
  live smoke that follows the runbook steps).
- Does not invent a fifth launcher family; does not weaken launch-trust / zero-upstream-credential /
  Gateway-only OTLP contracts.
  OTLP contracts.

**Evidence anchors:** Plan 11.5 Task 8 review conversation and evidence attempt (E7 /
`requires_gateway` capture that surfaced all four mechanisms); `.superpowers/sdd/task-8-report.md`
incomplete live E7 / `requires_gateway` dispositions; `src/optimus/acp/subprocess_env.py`;
`tools/run_plan115_acpx_cost_obs_evidence.py`; `tools/run_local_gateway.sh` / `.ps1`;
`optimus-trust run-gateway`; Plan 9.6 Phase C runbook
(`docs/runbooks/plan-9-6-phase-c-operator-path.md`).

**New finding (2026-07-29, discovered while attempting live `requires_gateway`/E7 evidence):** the
established `optimus-redis` (`redis:8`, port 6379) container had stopped — likely from a
machine/Docker Desktop restart since its last use, not a code or process regression. In its
absence, an unrelated project's container (`optimus-plan112-redis`, `redis:7-alpine`, no
TimeSeries module) took over the same default host port. `optimus-agent`'s preflight correctly
detected and rejected the TimeSeries-less Redis — the fail-closed check itself worked as
designed — but there is no protection against an unrelated project's container colliding on the
same default port, and no documented recovery path. This also reconfirms the divergent-mechanism
finding above at the Docker/port layer: separately-named, non-default-port containers
(`optimus-task8-redis` on 16379, `optimus-task8-phoenix` on 16006) were found running alongside
the default-port containers, consistent with different sessions standing up isolated instances
instead of one shared, documented one. The eventual design must nail this down explicitly (e.g. a
project-specific non-default port, or an explicit identity check) rather than depend on ambient
port availability.

**Status:** Closed. On 2026-07-29, Plan 11.6 implemented on
`agent/cursor/plan-11-6-local-startup-consolidation` with commits
`d123779`, `01f7849`, `24158ce`, `1618591`, `ef3dbd8` (Tasks 1–5) and Task 6 live evidence in
[`reports/plan-11-6-local-startup-live-evidence.md`](../../../reports/plan-11-6-local-startup-live-evidence.md)
(plus [`reports/plan-11-6-local-startup-acpx-evidence.md`](../../../reports/plan-11-6-local-startup-acpx-evidence.md)
and WSL residual
[`reports/plan-11-6-local-startup-acpx-wsl-evidence.md`](../../../reports/plan-11-6-local-startup-acpx-wsl-evidence.md)).
Operator runbook:
[`docs/runbooks/local-live-dependencies.md`](../../runbooks/local-live-dependencies.md).
Retain this entry for history; do not reopen without a new deferred-follow-up ID.

### P11.25-FU-1: Non-AGENT-mode conversation carriage (contract term: MT-FU-1)

**Moved:** tracked in [#246](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/246). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L2595-L2618).

### P11.25-FU-2: Structured ACP stop-reason metadata (contract term: MT-FU-2)

**Moved:** tracked in [#268](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/268). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L2619-L2640).

### P12-FU-1: Plan/Chat advisory-answer capability (residual of HLD §7)

**Moved:** tracked in [#247](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/247). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L2641-L2711).

### P12-FU-2: User-facing net cost-savings report

**Moved:** tracked in [#248](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/248). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L2712-L2745).

### P12.1-FU-1: Local Gateway missed the agent's startup readiness deadline

**Moved:** tracked in [#269](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/269). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L2746-L2788).

### P12.1-FU-2: Goal-loop iterations bypass turn cancellation and directive tracking

**Moved:** tracked in [#270](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/270). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L2789-L2825).

### P11-FU-30: No log-level categorization; stdlib `logging` is absent project-wide

**Moved:** tracked in [#275](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/275). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/d3114bea54d742abffcf104b630cb7104301de15/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L2826-L2870).

### P9.96-FU-8: Launch approval record capacity

**Moved:** tracked in [#289](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/289). Status, priority, owner and next gate are kept there; this entry's former detail is preserved in the [pinned detail](https://github.com/vibhanshu-agarwal/optimus-cost-agent/blob/c99af82365b83eccc6fdb24525cafd2a064c9f09/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md?plain=1#L1899-L1911).

## Accepted risks and warnings

Entries in this section record operator-accepted limitations. They are not open work and do not
reserve a future plan number.

### Plan 11.7 accepted risk: `optimus-redis` ACP-session durability boundary

**RISK (accepted by operator 2026-07-30):** `optimus-redis` provides no real durability for
[Plan 11.7](archive/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md)'s "durable Redis ACP
sessions." Live-inspected container state has no volume mounts, `appendonly no` (periodic RDB
snapshots only), and a default user configured as `nopass ~* &* +@all`; strict loopback binding
mitigates the unauthenticated default-user exposure.

**Consequence:** Container removal loses all ACP session state. Container restart recovers only to
the latest RDB snapshot. The accepted Plan 11.7 meaning of "durable" is survival across
process/agent restarts, not container lifecycle events.

**Revisit trigger:** Revisit only if session-state loss occurs in practice or a future plan—such
as the consolidated local-startup configuration source of truth—already changes Redis persistence
configuration.
In that case, fix persistence once in the consolidated startup mechanism under the single-config
rule.

**Status:** Reviewed disposition. Accepted as-is by the operator on 2026-07-30; recorded warning,
not open work.

## P9.96 Task 9 Disclosed Follow-Ups (Closed; historical Plan 10 custody)

**Raised:** Disclosed by Plan 9.96 Task 9 on 2026-07-23 under the 2026-07-18 scope-conflict ruling.
Plan 9.96 closes only `P9.85-FU-7` and `P9.9-FU-1`; these seven disclosures are named custody, not
silent drops.

**Origin:** `reports/plan-9-96-operator-debug-launch-trust-evidence.md`, limitations table.

**Historical designated future plan:** Plan 10 (retired). These seven distinct stable-ID catalog
entries are now closed; no Plan 10.x slot or new Plan 10 work remains.

| ID | Summary | Priority |
|---|---|---|
| `P9.96-FU-1` | `StartupConfigurationError` missing `optimus-agent:` prefix in `acp/__main__.py` | MEDIUM |
| `P9.96-FU-2` | Duplicated TOCTOU comment block in `acp/__main__.py` | MEDIUM |
| `P9.96-FU-3` | `append_launch_audit_event` docstring says trusted external runtime root but uses `workspace/.optimus` | MEDIUM |
| `P9.96-FU-4` | Latent unroutable `DEFAULT_AGENT_MODEL = "glm-5.2"` in `agent/defaults.py` (ACP path injects `claude-haiku`) | MEDIUM |
| `P9.96-FU-5` | Frozen dataclass exceptions mask real codes via `@contextmanager` (`FrozenInstanceError`) | MEDIUM |
| `P9.96-FU-6` | Frozen plan Task 9 CLI arg-order / PATH assumptions; execution uses `uv run` plus `--workspace-root` before the subcommand (applied; not a code defect) | MEDIUM |
| `P9.96-FU-7` | Approve ceremony writes durable approval with no y/N confirm; bare-shell display rows may be empty when settings are keyring/default-sourced | MEDIUM |

**Acceptance / disposition:** The rows were open until a reviewed implementation or explicit closure
record resolved each one with evidence. `P9.96-FU-6` is an applied execution correction, not a code
defect, and closed through the explicit reviewed disposition below.

**Plan 10.1 dispositions (updated 2026-07-23; the pool's first allocated slot):**

| ID | Disposition | Priority |
|---|---|---|
| `P9.96-FU-1` | **Closed** by Plan 10.1, commit `daccb0d7469814930922eae67a86552435258cf6` ("fix(acp): prefix PreflightFailure and StartupConfigurationError stderr"). Named tests: `tests/unit/acp/test_main_check_config.py::test_check_config_prints_preflight_failure`, `tests/unit/acp/test_main_wiring.py::test_startup_configuration_error_has_agent_prefix`. | MEDIUM |
| `P9.96-FU-2` | **Closed** by Plan 10.1, same commit `daccb0d7469814930922eae67a86552435258cf6` (duplicate TOCTOU comment block removed; one copy retained, verified via `rg -n -F "Plan 9.96, Task 5 Step 7 (TOCTOU matrix): workspace identity is a" src/optimus/acp/__main__.py` returning a single hit). | MEDIUM |
| `P9.96-FU-3` | **Closed** by Plan 10.1, commit `d83953880a15419097e91da262678f736905cccd` ("docs(acp): align launch-audit docstrings with workspace-local runtime root"). Named test: `tests/unit/acp/test_launch_audit.py::test_launch_audit_docs_describe_workspace_local_runtime_root`. | MEDIUM |
| `P9.96-FU-4` | **Closed** by Plan 10.1, commit `cc66d660cd8580eb3b821d0eb25ed04b27605dc0` ("fix(agent): use routable shared default"). Named tests: `tests/unit/agent/test_defaults.py::test_resolve_agent_model_falls_back_to_routable_shared_default`, `tests/unit/optimus_gateway/test_models.py::test_resolve_model_id_accepts_shared_agent_default_for_every_provider`. | MEDIUM |
| `P9.96-FU-5` | **Closed** by Plan 10.1 evidence; no source or test change. Static inventory found zero `@contextmanager`/`FrozenInstanceError` occurrences in `src`/`tests`; the two candidate frozen exceptions (`StartupConfigurationError`, `AcpOutboundError`) only ever construct once via `raise ... from` / `future.set_exception(...)` and never reassign a field post-construction on any real call path. Behavior selector (`tests/unit/acp/test_bootstrap.py`, `test_outbound_errors.py`, `test_trusted_paths.py`, `test_preflight.py`) passed 36 passed, 5 skipped (environment-legitimate skips). Full record: `docs/superpowers/reviews/plan-10-1-review-checkpoints.md`, 2026-07-23T13:20:00Z entry. | MEDIUM |
| `P9.96-FU-6` | **Closed** by reviewed Plan 10.1 disposition; execution correction only, no code change — see the disposition paragraph below. | MEDIUM |
| `P9.96-FU-7` | **Closed** by Plan 10.2 for the remaining effective-row display provenance gap, while Plan 10.1's confirmation-gate half remains part of the same stable finding (commit `278d95bec4e9a62c55c5de1237a61af1ca661309`). Plan 10.2 implementation commit `4350ae6f455c83f6d8a79c2a0bbdfe149755a4ef` ("feat(acp): display effective credential provenance in optimus-trust approve"). Named tests: `tests/unit/acp/test_local_gateway_secrets.py` (shared-secret provenance / wrapper / base-URL keyring ignore), `tests/unit/acp/test_launch_gate.py::TestEffectiveCredentialDisplayRows`, `TestMissingKeyNonDisclosureAndGoldenDigest`, `tests/unit/acp/test_launch_approval_cli.py::test_display_candidate_prints_source_class`. Frozen plan: `docs/superpowers/plans/archive/2026-07-23-plan-10-2-p9-96-fu7-effective-row-display-provenance.md` (SHA-256 `4303D6AD5C44ED62A85A0509C8C87366505D4D470DD7BC4E0B4309BBE6E3C771`). Approval: `docs/superpowers/reviews/2026-07-23-plan-10-2-implementation-plan-approval.md`. Evidence: gitignored `docs/superpowers/reviews/plan-10-2-review-checkpoints.md`. Plan 10.2 does **not** change the approval digest contract; golden digest `f7af89af0acce664b27825e5af9823c25b11579490bccc73e8f82d4ec316f248` remains byte-identical. | MEDIUM |

**`P9.96-FU-6` disposition paragraph:** `P9.96-FU-6` named the frozen Plan 9.96 Task 9 plan's own CLI
arg-order assumption against `optimus-trust`'s `argparse` contract. `--workspace-root`
(`src/optimus/acp/launch_approval_cli.py:78-82`) is declared on the top-level `ArgumentParser`
*before* `subparsers = parser.add_subparsers(dest="command")` (line 84), so under normal `argparse`
semantics it must be supplied before the subcommand token — e.g.
`optimus-trust --workspace-root <path> approve --mode durable`, not after. The corrected command
shape (`uv run` plus global options such as `--workspace-root` preceding the subcommand) was already
applied during Plan 9.96 Task 9's own real-`acpx` evidence capture
(`reports/plan-9-96-operator-debug-launch-trust-evidence.md`), not by Plan 10.1. Plan 10.1 (Task 6,
2026-07-23) re-verified this reviewed disposition by re-reading the current `argparse` source and
confirming the contract is unchanged. `P9.96-FU-6` was never a source-code defect and required no
production or test change under Plan 10.1 or any prior plan; no commit is recorded for this
disposition.

**Also disclosed (Plan 9.98 custody handoff):** inner `optimus-agent` launch-audit `agent_child`
may omit keyring-resolved `OPTIMUS_API_KEY` because audit precedes `apply_local_defaults`; outer
post-default audit remains the authoritative child-key evidence source. This is a custody note, not
an additional Plan 10 item.

**Status:** Closed. `P9.96-FU-1` through `P9.96-FU-4` and `P9.96-FU-6` are closed by Plan 10.1 (see the
dispositions table above); `P9.96-FU-5` is closed by Plan 10.1 evidence with no source/test change;
`P9.96-FU-7` is **closed** under its original stable ID: Plan 10.1 closed the confirmation-gate half
and Plan 10.2 (commit `4350ae6f455c83f6d8a79c2a0bbdfe149755a4ef`) closed the effective-row display
provenance half. No new catalog ID or Plan 10.x plan document was created by either pickup. The
remaining open items are now carried by this pool, except for the parked, undecided
`P9.85-FU-3` entry above.

## Closed Historical Follow-Ups (formerly tracked lightweight notes)

### Plan 10.3 frozen-plan status correction (historical)

**Status:** Closed.

The frozen Plan 10.3 implementation plan retains its pre-approval draft status because its
approval record pins the plan bytes. The digest-pinned approval record and the roadmap's closed
Plan 10.3 entry are authoritative for the lane's closed state; this pool records the closure
without editing the historical frozen plan.

### `uv.lock` missing direct dependencies: `keyring`, `redis`, and their transitive chain (disclosed 2026-07-23 during Plan 10.1 Task 1)

**Status:** Closed.

At disclosure on 2026-07-23, the committed `uv.lock` was out of sync with `pyproject.toml`, not
just stale: `uv lock --dry-run`
shows 13 packages a regeneration would add, including `keyring` and `redis` (both **direct**
dependencies declared in `pyproject.toml`, not stray transitives) and the Linux SecretStorage
keyring-backend chain (`cryptography`, `jeepney`, `secretstorage`, `cffi`, `pycparser`, `jaraco-*`).
`uv run --locked` and `uv lock --check` both fail on current `main`. Confirmed `cryptography` is
genuinely unimportable in a `--frozen`-synced venv on both Windows and a fresh WSL2 environment
(`ModuleNotFoundError`); `keyring`/`redis` only appear to work locally because of packages left over
from an older install, not because the lock is sound — a fresh clone or Linux CI doing
`uv sync --frozen` gets exactly the lock's packages and nothing else, so `keyring`'s SecretStorage
backend would fail to import there. Traced via `git log`: the lock was last regenerated at `9c1206d`
(2026-07-04) while `pyproject.toml` changed again at `1f7116b` (2026-07-15, Plan 9.9's approval-
ceremony work) — the drift predates Plan 10.1 and passed through several already-merged,
already-reviewed plans undetected.

**Fix:** regenerate the lock (`uv lock`), review the diff for anything beyond the expected
keyring/redis/dotenv chain, then re-run the default test suite and a WSL2 cross-check to confirm
`keyring`/`redis`/`cryptography` all import cleanly from a fresh sync. Not a Plan 10.1 blocker —
Plan 10.1 used `uv run --frozen` as a standing substitute for the plan's literal `--locked` command
text rather than regenerate the lock mid-plan, since that would have been its own scope change; not
scheduled.

**Promoted -> Plan 10.3** (2026-07-24): Closed by
[`archive/2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md`](archive/2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md).
Lock commit `1b152a8` ("chore: refresh uv lock for declared gateway dependencies") adds exactly the
reviewed 13-package chain (`cffi`, `cryptography`, `jaraco-classes`, `jaraco-context`,
`jaraco-functools`, `jeepney`, `keyring`, `more-itertools`, `pycparser`, `python-dotenv`,
`pywin32-ctypes`, `redis`, `secretstorage`); `pyproject.toml` unchanged; `uv lock --check` exits 0.
Windows acceptance: `uv run --frozen pytest -q` → 1495 passed, 20 skipped, 27 deselected.
WSL2 Ubuntu-24.04 disposable fresh-sync import printed `keyring redis cryptography`. No new catalog
ID; this note is closed by Plan 10.3.

### Tools: `SurfaceAuditError` frozen-dataclass CI wart (disclosed 2026-07-23 during Plan 10.1 Task 7)

**Status:** Closed.

At disclosure on 2026-07-23, `tools/verify_plan996_logging_surfaces.py` raised a
`@dataclass(frozen=True)` `SurfaceAuditError`.
When that exception is raised under pytest's generator-based failure capture, pytest teardown can
attempt to attach `.__traceback__` and surface a secondary `FrozenInstanceError` in the CI log.
Standalone `main()` outside pytest raises `SurfaceAuditError` cleanly with no crash — this is a
pytest-harness wart, not a production or `src`/`tests` FU-5 recurrence. Trivial later fix: drop
`frozen=True` on that tools-only exception class (nothing in that type needs immutability). Not a
Plan 10.1 blocker; not scheduled.

**Promoted -> Plan 10.3** (2026-07-24): Closed by
[`archive/2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md`](archive/2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md).
Tools commit `4d1f086` ("fix(tools): allow surface audit errors to carry tracebacks") drops only
`frozen=True` from `SurfaceAuditError`. Named regression:
`tests/unit/tools/test_verify_plan996_logging_surfaces.py::test_surface_audit_error_allows_pytest_traceback_attachment`
(RED `FrozenInstanceError` → GREEN); full tools unit file 13 passed; standalone `main()` still exits
0 with `Plan 9.96 logging-surface audit passed`. No new catalog ID; this note is closed by Plan 10.3.

## Closed custody excluded from the open pool

Plan 9.96's two sole-custody follow-ups (`P9.85-FU-7`, `P9.9-FU-1`) are closed with the Plan 9.96
Task 9 evidence report and are intentionally not listed as open backlog entries.
