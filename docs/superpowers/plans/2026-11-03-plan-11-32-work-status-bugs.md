# Separate Bugs table — issue #354 implementation plan v3

> For the implementing agent: follow the approved repository workflow and execute the three checkpoints sequentially. This is a planning proposal, not implementation authority. Codex owns this 11.x lane; Claude reviews through its CLI. No implementation has begun.

**Tracking issue:** https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/354
**Date:** 3 November 2026, Asia/Calcutta.
**Goal:** separate defect work from general follow-ups on the existing live status page without losing, duplicating or changing the meaning of any issue.
**Architecture:** add one vocabulary kind/table, retain the existing flat renderer, and add one matching informational summary count. Existing issue identity, metadata, relation, filtering, sorting and diagnostic paths remain shared.
**Tech stack:** existing inline HTML/JavaScript, Node built-in test runner, existing Python work-tracking tooling and pytest. No dependency or API design change.
**Spec:** issue #354 plus the design decisions and classification appendix below form the complete bounded specification.

## Authority and source binding

The operator selected #354 in the originating chat; its handoff commissions assessment, planning and independent Claude CLI review here, followed by operator approval before implementation. The source issue still records the original deferral; that historical text is not overwritten by this draft. Owner assignment comes from the operator handoff, not today's unchanged handler label.

Base: main `026b3fd18dbed0793b93a0072a430fac62ff56e4`, refreshed from origin on 3 November. Isolated checkout recorded in the local provenance receipt; branch `agent/codex/issue354-bugs-table`. Initial Git status was clean. Native worktree creation rejected the nested sourceRoot; the authorized Git fallback used the evidence policy's prescribed agent-worktree directory. Restricted Git access to that directory failed; elevated read-only Git confirmed cleanliness. These are tooling limitations, not source/test failures.

Read governing AGENTS.md, CONTRIBUTING.md, evidence policy, ADR-022 and the decision index. This draft is outside the live-plan directory pending approval, so it creates no unregistered live plan and no second live work pool. After approval, file the complete approved plan as proposed Plan 11.32 (11.31 is already used by #357), subject to an allocation refresh, with exactly one issue-only registry pointer and a docs-index row. Existing #354 remains the work owner; no duplicate issue.

## Design decisions (Codex proposals, not operator rulings)

1. Add `"bug": "Bug"` to `kinds`; add `{"key":"bugs","title":"Bugs","kinds":["bug"]}` immediately before `follow-ups`. Both tables default expanded. Rename the existing table to `Follow-ups`, retaining key `follow-ups` so its in-memory filter state/IDs remain compatible. Table order: features, plans, bugs, follow-ups, hardening, obligations.
2. Retain all common columns and behaviors, including Open/Closed/All state, per-table filters and focus retention, product and status tiles, parent links/cycles, sort, counts and Untriaged diagnostics. A conflicting `kind:bug` plus `kind:follow-up` stays Untriaged exactly once. No title/body heuristics and no legacy bare `bug` alias. Valid kind with an invalid product also stays Untriaged.
3. Add `summary.bugs` counting `kindKey === "bug"`, and a non-clickable `Bugs` count tile beside the existing non-clickable Follow-ups tile. `summary.followUps` continues counting only follow-up. Counts keep their existing selected-state/dataset semantics; column filters do not redefine summary counts. Zero-row tables stay hidden, as today; a present table with zero matches keeps its No matching issues row. Add this page-note sentence: "Existing closed issues keep their prior classification; the Bugs table starts with the separately reviewed open-issue batch." No other UI redesign.
4. Add only `kind:bug` to `LABEL_SPECS`: description `Observed or source-supported defect in existing product, tooling, tests or integration behavior`; color `d73a4a`. Keep every existing label definition, historical migration kind, PILOT_LABELS fixture, manifest, sealed report and pointer mapping unchanged. This is an additive live-vocabulary maintenance change, not a replay or redesign of the frozen migration. Existing label/page parity test requires the Python addition. ADR-022 item 7 says the migration tool stays unchanged, and its holds include label-definition changes: operator approval of this exact plan must explicitly dispose of those two constraints for this one additive live LABEL_SPECS entry and the named kind:bug definition only; historical migration behavior and records remain protected. No new ADR is proposed for this bounded maintenance disposition. Do not add `bug` to historical record-classification schemas merely because it is a new live issue kind.
5. Use the exact classification appendix, not the historical provisional count. Classification means the nature of the remaining issue, not whether its fix is scheduled, whether its root cause is known, or whether all work named in its historical title remains outstanding.

Rejected alternatives: splitting by title/description creates hidden classification rules; treating both kinds as follow-ups fails the requested table distinction; a broad taxonomy or migration rewrite is outside #354.

## Exact proposed external changes — separate approval and release gates

The dated [classification appendix](../reports/2026-11-03-issue354-work-status-bugs.md#classification-proposal) accounts for all 58 currently open follow-ups. In this pre-filing packet it is classification-v3.md; file that entire appendix into the linked report in the same commit as the plan, never as an extra file at the plans root. Its input includes current bodies, all labels, parent URLs and timestamps; comments on every one of those issues with comments were retrieved. Classification is not a fresh reproduction of the underlying defects.

Propose replacing **only** `kind:follow-up` with `kind:bug` on these **13** issues:
`252, 253, 260, 269, 272, 273, 287, 361, 369, 379, 423, 433, 436`.
All other issue fields, labels, native parent links and child relationships remain unchanged. No closed issue is reclassified. #293 is excluded under separate Evidence Handoff ownership for this batch; its issue body explicitly distinguishes it from the A2A deferral. The A2A hold itself stays unchanged. #330 is excluded from inspection/disposition and all writes. #331 stays deferred; #369 and #273 receive no implementation/scheduling authority from a kind-only proposal.

For #354 itself, include title and labels in the same explicit pre-implementation release. Use targeted label add/remove operations for its three changed dimensions as well, with readback and no full-array replacement. Propose title `Separate Bugs table on the work-status page`; replace `priority:medium` with `priority:high`, `handler:unassigned` with `handler:codex`, and `estimate:na` with `estimate:2d`; retain `difficulty:medium`, `status:open`, `kind:follow-up` and `product:optimus`. Claude agreed with medium difficulty and estimate:2d in the first independent review. The operator must release these #354 tracking-label edits before implementation, separately from the later kind:bug rollout; no status transition is needed to record the assessment. No status transition is bundled. After authorization, append a dated reviewed-plan/next-gate comment without rewriting the historical deferral body. The CLI reviews must be posted verbatim with the required reviewer/model/effort/session heading; posting is an explicit operator-approved external write, not implied by permission to run a read-only review.

Sequence: deliver and verify the page vocabulary on hosted main first; only then create the reviewed label and apply the exact reviewed issue batch under separate operator release. Otherwise an old page would show newly labelled issues in Untriaged. A page can safely deploy before reclassification: Bugs is empty/hidden and existing rows remain in Follow-ups.

Before starting the released reclassification batch, read the repository label definition and require kind:bug to exist with exactly the reviewed description and color; stop on absence or drift before any add operation. Immediately before each released kind-change pair, reread the issue, current labels, body, state and relationships. Stop on a closed issue, a kind set other than exactly kind:follow-up, or a changed classification basis; never substitute issue IDs. Preserve unrelated concurrent label edits rather than replacing the whole array. Use targeted add/remove operations: add only kind:bug, read back, then remove only kind:follow-up and read back. The temporary dual-kind state must remain visible exactly once in Untriaged with the existing red conflict diagnostic. Regression fixtures cover every such pair; check the hosted intermediate state once for the first pair, then use API readback for each pair to conserve the page's unauthenticated quota. Snapshot other fields/labels immediately before the pair and check them afterward; an unrelated concurrent change is recorded and assessed, never written back to the old snapshot. After the pair the kind must be exactly bug. Failure/unknown outcome stops the batch and records completed/unknown/unattempted actions; no automatic retry, rollback or continuation. The reviewer checks the exact connector/API operations and payloads before release; do not assume a convenience CLI preserves unrelated labels. A relabel-only receipt never claims a reopened or repaired defect.

Never replay the historical migration publisher/reconciler as a maintenance action on these reclassified issues: kind is a source dimension and merged_labels would restore kind:follow-up. Report such historical drift as expected dated migration drift; do not amend manifests, suppress validation or broaden the tool. No current workflow or pre-commit step invokes that replay, as inspected in review. Recheck this before delivery.

## Scope and Explicit Exceptions

In scope: vocabulary/table, summary count/tile, label-spec parity, regression tests, exact reviewed kind-change proposal, narrow approved-plan/index filing, review/evidence receipts, and separately released hosted/metadata verification.

Explicit exceptions with custody: #330 closure/automation is owned by its original chat; audit typing #331; broader POSIX repair #369; process-tree cleanup #273; Evidence/A2A and #293 retain their independent owners. #290 and #291 own tracking-policy/header-gate migration. #354 owns any later reconsideration of the retained classification rows; this pass neither creates a new pool nor repairs the defects on the proposed list. No page redesign, new backend/API, new dependency, generic migration automation, closed-issue cleanup, frozen-document edits, paid/live product tests, credential access, services, push/PR/merge/publication or cleanup without the corresponding explicit authority.

## Prerequisites

| Category / requirement | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|
| Current-main isolated checkout and clean source | yes | Codex | Refresh before implementation; review any overlapping drift |
| Existing generic grouping/filtering/diagnostics | yes | Codex | Source inspected; 98 baseline Node fixtures passed |
| Node executable | yes | Operator machine / Codex | v26.5.0 observed; baseline successful |
| Checkout-specific frozen Python dev environment | no | Codex / operator machine | Merely unauthorized for implementation until approval; create its own .venv with uv sync --frozen --extra dev, never borrow another checkout's |
| Claude Opus 5.5 high read-only plan review | yes | Codex | First review obtained; this successor requires its focused recheck, no model substitution |
| Source implementation and local verification approval | no | Operator | Merely unauthorized; exact reviewed plan approval required |
| GitHub reads | yes | Codex | Public repository and issue snapshots verified; no token copying |
| GitHub label/issue write grants | no | Operator | Merely unauthorized; release exact payloads, with #354 assessment before implementation and kind changes after hosted verification |
| Hosted Pages deploy from approved main merge | no | Operator / repository workflow | Merely unauthorized; publication and merge are later gates |
| Browser smoke of local and hosted page | unknown | Codex | Merely unauthorized until the approved local verification step; establish browser access before dependent acceptance, no operator GUI ceremony expected |
| Product services, paid model probes, Redis/Gateway | yes | Existing owners | No product-service or paid probe needed for #354; review CLI uses the existing authorized account |

## Change surface

| File | Planned change |
|---|---|
| docs/work-status.html | kinds/tables JSON; buildModel summary.bugs and matching informational tile; one historical-classification page note |
| tools/testing/work_status_page.test.cjs | exact table order, mixed-kind conservation, summary and browser-controller regressions |
| tools/github_work_tracking.py | one additive LABEL_SPECS entry only |
| tests/unit/tools/test_github_work_tracking.py | explicit bug label metadata and validity assertion; preserve frozen pilot fixtures |
| tests/unit/docs/test_work_status_pages.py | validation unchanged; edit only if an actual new assertion is justified |
| docs/superpowers/plans/2026-11-03-plan-11-32-work-status-bugs.md | approved complete plan, after allocation refresh |
| docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md | one issue-only live-plan registry pointer; no work/status entries or frozen custody edits |
| docs/README.md | index plan and sanctioned evidence record |
| docs/superpowers/reports/2026-11-03-issue354-work-status-bugs.md | sanitized source-bound review/classification receipt filed in the same approved change as the plan, with a ## Classification proposal anchor; add validation as it is obtained |
| docs/superpowers/reviews/issue354-review-checkpoints.md | ignored local continuity log, owner records CLI output; never staged |

## Review Focus and executable acceptance

Each issue from the fetched dataset occurs exactly once across all model tables plus Untriaged in the unfiltered view; PRs remain excluded by the existing fetch layer. Verify identities, not just aggregate count. Classification does not change any row field except its kind and table placement. Unknown/conflicting kind/product remains visible with diagnostics. Pin the cases explicitly: valid bug plus bad product counts in Bugs but renders in Untriaged; dual-kind counts in neither kind tile, adds one to attention, and shows kind conflict. Tile order puts bugs immediately before followUps. A duplicate bug across API pages must be deduplicated through loadView; buildModel alone is not the fetch deduplication boundary. Summary total and unrelated counts are invariant when a fixture changes only its kind; followUps decreases by one and bugs increases by one.

Required cases: bug + ordinary follow-up with the same status and parent; closed/completed and closed/not_planned bugs; dual-kind bug/follow-up; valid bug with missing/unknown product; malformed/cyclic/missing-parent links; both product values; multiple unrelated tables; empty Bugs table; all Bug rows filtered out. Exercise a Bugs header filter, clear, collapse/reopen and focus restoration, proving Follow-ups filters are independent; global product/status filters still apply to both. Retain hostile-title/URL escaping and diagnostics coverage through the existing shared render path.

## Checkpoint 1 — reviewed contract and failing regression

- [ ] Obtain independent Claude CLI plan/classification review, resolve blockers in a complete successor, and obtain operator approval of the exact plan. Technical GO never substitutes for authority. Obtain and perform the separately approved #354 assessment-label changes before implementation; retain historical body and status. Review-comment publication needs its own exact payload grant.
- [ ] Revalidate latest main, branch/HEAD/cleanliness, overlapping page/tool changes and the issue classification snapshot. Establish the dedicated frozen dev environment and browser availability before dependent verification. Retain failures; stop for unexplained baseline defects rather than widening.
- [ ] After approval, file the plan and issue-only index entries as above; retain predecessor draft bytes and hashes.
- [ ] Add `test_bug_table_partition_and_metadata_conservation`, `test_bug_summary_counts_do_not_inflate_followups`, `test_bug_conflicts_stay_untriaged_once`, and `test_bug_filters_are_independent_and_preserve_focus` to the existing Node suite using its `issue`, `withKind`, `allRows`, fake DOM and event helpers. Update exact table-order, summary, tile count/order and click-behavior expectations (current fixture anchors at lines 172, 292, 971, 974, 1064, 1273 and 1276; rederive after edits). Add the cross-page duplicate-bug loadView control and explicit invalid-product/dual-kind summary assertions. Use the cases above, with exact row/field equality assertions.
- [ ] Add an assertion for `LabelSpec("kind:bug", "Observed or source-supported defect in existing product, tooling, tests or integration behavior", "d73a4a")` and `_valid_label("kind:bug")` in the existing Python vocabulary test. Preserve PILOT_LABELS. Run the changed relevant tests against unchanged production bytes and retain expected RED failures. Claude checkpoint review covers contract and test intent.

## Checkpoint 2 — minimal implementation and local evidence

- [ ] Make the page and label-spec edits specified in Design decisions; reuse generic `buildModel`, `renderTable`, `initialUi`, `visibleRows`, `renderRow` and controller behavior. No new grouping algorithm.
- [ ] Run `node --test tools/testing/work_status_page.test.cjs`; all existing and added cases must pass.
- [ ] Run `uv run --no-sync pytest --no-cov tests/unit/tools/test_github_work_tracking.py tests/unit/docs/test_work_status_pages.py` using normal repository configuration. Retain pass/fail/skip identities, mode/native/parent validity and COMPLETE/INVALID records; this is focused evidence, not full-suite coverage.
- [ ] Run relevant docs hygiene checks for the filed plan/index paths, `uv run --no-sync python -m ruff check .`, and `git diff --check`. Perform a local browser smoke of both tables, filters, links, keyboard operation, counts and narrow-width wrapping using a browser-intercepted API fixture containing bugs; live data has no kind:bug yet. Label this fixture-driven UI evidence; first real-data proof is CP3. Offline model fixtures are not hosted deployment evidence.
- [ ] Bind commands, exit codes, platform/environment, HEAD, source diff/hash and before/after status in the receipt; dirty-tree results stay provisional. Inspect diff scope and verify frozen migration records have no change. Claude reviews final implementation and evidence; no code changes in this planning turn.

## Checkpoint 3 — authorized delivery and exact metadata batch

- [ ] With separate commit/push/PR authority, include `Master-plan impact: none: This page-vocabulary and issue-kind maintenance changes no hardening-track scope or acceptance.` in the PR body, refresh main intentionally and run normal hooks and required checks; no bypass or retry-to-green. Use the existing commit/checkpoint profiles and CI full-suite/coverage gates. Current focused passes never substitute for these later gates. Re-review overlapping drift and changed conclusions before publication.
- [ ] Obtain separate operator merge authority, then verify the actual merge SHA's required CI and Pages deployment. Record PR-head and actual-merge evidence separately. Review current-state docs at closing/merge; frozen records remain untouched.
- [ ] Verify hosted bytes contain bug vocabulary and the new table definition before label creation/reclassification. Obtain Claude review of the exact external-write payload and then operator release (definition, 13 IDs, and any still-unpublished review-comment payloads; #354 assessment labels were an earlier gate); perform guarded reads/writes/readback as specified above. Keep external failures/unknowns visible.
- [ ] Verify the hosted page's Open, Closed and All modes, every changed issue exactly once, unchanged metadata/parents, diagnostic behavior and counts relative to a fresh complete dataset. Concurrent unrelated issue changes mean snapshot totals cannot be hardcoded to the planning baseline.
- [ ] Present source delivery and classification results separately. Close #354 only with operator authority and after both requested outcomes are accepted. No closure, relabel or automation change for #330. No cleanup authority follows from completion.

## Estimate and stopping rule

Codex estimate for the whole bounded item: **1–2 working days**, excluding operator waits; propose medium difficulty and estimate:2d, independently agreed by Claude in the first review. Assessment/classification/plan review: roughly half a day. Implementation, focused checks, review, normal delivery and guarded metadata verification: roughly half to one-and-a-half days. Hook/full-suite runtime and substantive review findings are the main variability. If this requires a new classification framework, migration rewrite, unresolved policy decision or more than two working days, stop and re-estimate before expanding; do not silently absorb it.

## Evidence so far and limitations

Planning baseline only: Windows Node v26.5.0, exact main above, 98 tests passed, 0 failed, 0 skipped, 0 cancelled. No #354 source/test edits, Python tests, Ruff, full suite, product services, hosted browser smoke or GitHub mutations have run. Raw baseline and read snapshots are local provenance; before delivery, file a sanitized repository-visible receipt with hashes. No project build/review decision may depend permanently on an untracked workstation file.

Appendix hashes: classification-v3.md `5086457b4f028ad43e368069fbe9a1638c428f05386df6bcea0ce8d15f1d4a74`; classification-input-v2.json `03de00233daf89b39d5d92319df4e353289e94758996ccd4fdf94f90c3d2a297`. Source issue/label/comment snapshot hashes remain in the provenance receipt; they are dated review inputs, never execution authority.

## Revision and review disposition

V1 and its exact bytes remain preserved. V2 closes B1 by retaining #262 and #400, and adopts the optional conservative #249 retain (13 proposed kind changes). It addresses B2 with the strict prerequisite cells, repository-relative filed appendix, same-commit report/index filing and no local checkout/chat identifier in the filed plan. B3 now uses targeted add/remove operations. The source-count dispute is resolved mechanically: all 58 kind:follow-up rows are covered once and #330 is absent. Review corrections also name the ADR-022 conflict and proposed operator disposition, prohibit migration replay, specify closed-history/page-note behavior, strengthen pagination/summary/UI tests, put #354 assessment before implementation, and require exact-write-payload review plus the existing PR declaration. The independent v2 recheck and operator authority remain separate. No v1 NO-GO is erased by this successor.

V3 applies only the nonblocking refinements from Claude's technical GO on v2: initialUi naming; accurate page/edit-count wording; label-definition precheck; #354 title and targeted-method release; same-change report with the exact Classification proposal anchor; one hosted intermediate-state check plus per-operation API reads. The 13 IDs, classification rationales, source snapshot, architecture, authority boundaries and agreed estimate are unchanged. V2's technical GO remains recorded; the focused final recheck is separate from operator approval.
