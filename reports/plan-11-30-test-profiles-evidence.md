# Plan 11.30 test profiles — evidence report

**Plan:** `docs/superpowers/plans/2026-10-04-plan-11-30-test-profiles-implementation_v4.md` (approved working bytes SHA-256 `8A40DEF6D627EDC722D9FA925BBB0C193DE433ECCB91D2DCA19F1DA6AFC5C790`; LF-normalised blob `7D07ADA39CE1F8987E529C7FD8838952B4607F6F2CBD8773D39220D44DB6AF1E`, differing only by CRLF on lines 32–33).
**Live plan (since 2026-10-09):** `docs/superpowers/plans/2026-10-04-plan-11-30-test-profiles-implementation_v5.md`, approved frozen bytes SHA-256 `149002fa5c61b366900c535bee883dd07289dc2317bdf4064cff2e20a7f7035e`. The v4 line above is the original plan reference, kept as written; v4 is superseded and archived byte-identically at `docs/superpowers/plans/archive/2026-10-04-plan-11-30-test-profiles-implementation_v4.md`.
**Machine-readable index:** [`plan-11-30-test-profiles-manifest.json`](plan-11-30-test-profiles-manifest.json).
**Status (2026-10-11, after Codex's 10:45:23 UTC acceptance):** The live plan is approved frozen v5 (`149002fa…`). Stage A and Stage B are delivered and accepted locally (Stage B finals at `3cece0a`; results commit `26bd667`). I1 is on main: the coverage bootstrap merged through PR #279 at `4ed9b25`, and its main-push baseline is accepted. The I2/I3 integration merge `ea88814e` (tree `9048bc8d`) and its I4 exact-source finals stay accepted at the old acceptance pin `ea88814e`. The S1 correction is local commit C `343b233a`, and the corrected-source I4 finals are accepted at that measurement pin (Windows and WSL full canonical gates and validation pass on the 7,412-node universe; Optimus 89.4515 % / 88.8835 %). The documentary delivery D2 `281f8ce7` (single parent C, tree `a45e448d`) is accepted, and its forward WSL platform obligation is discharged (1,574 nodes reused from C plus the 55 `test_ci_parity` nodes run on WSL at D2). Under the operator's exact approval the branch was pushed at `281f8ce7` without force and PR #280 opened to `main`; the PR body's masterplan declaration was corrected under release. Codex accepted the candidate Linux CI and the seven-module safety comparison at the actual PR merge commit `1946713e` (tree equal to D2's; the commits are distinct, and the CI evidence is bound to `1946713e`): Optimus 88.8591 %, Context Engine 95.9243 % and model policy 96.9880 % pass; all seven safety modules are identical to the I1 baseline, so there is no regression. The commit that records these results (D3) is documentary only and is not measured; it and any update of the published branch each need their own bounded authority. Merge to main, main-push evidence at the actual main commit, terminal acceptance, closure, archival and cleanup are held. See "Current delivery and status (2026-10-11)", "D2 delivery and WSL discharge (2026-10-11)", "I5 publication and PR-body correction (2026-10-11)" and "I5 candidate CI and seven-module safety comparison (2026-10-11)".
*Historical status at recording (committed with `281f8ce7`, 2026-10-11), kept as written:* **Status (2026-10-11):** The live plan is approved frozen v5 (`149002fa…`). Stage A and Stage B are delivered and accepted locally (Stage B finals at `3cece0a`; results commit `26bd667`). I1 is on main: the coverage bootstrap merged through PR #279 at `4ed9b25`, and its main-push baseline is accepted. The I2/I3 integration merge `ea88814e` (tree `9048bc8d`) is committed locally and accepted. The I4 exact-source finals stay accepted exactly at the old acceptance pin `ea88814e` (2026-10-10). The S1 reader correction, with the S2 workflow comment and the I4 results composition, was delivered as local commit `343b233a` (single parent `ea88814e`, tree `8a39467d`) with normal hooks, and Codex accepted that delivery on 2026-10-11 together with the corrected-source I4 finals at it, the new measurement pin C: the Windows and WSL full canonical gates and validation pass on the 7,412-node universe; Optimus 89.4515 % (Windows) / 88.8835 % (WSL), Context Engine 95.9243 %, model policy 96.9880 %, Windows gap ratio 0.966. The forward WSL platform obligation is discharged at C only. The commit that records these results is a third, documentary-only HEAD; it is not measured. This documentary delivery, I5 (concrete operator push/PR authority after latest-main reconciliation, actual Linux CI and artifact origin, and the safety comparison), merge, closure, archival and cleanup are held; the lane branch is not pushed. See "Current delivery and status (2026-10-11)", "S1 delivery at `343b233a` (2026-10-11)" and "Corrected-source I4 finals at C `343b233a` (2026-10-11)".
*Historical status at recording (committed with `343b233a`, 2026-10-10), kept as written:* **Status (2026-10-10):** The live plan is approved frozen v5 (`149002fa…`). Stage A and Stage B are delivered and accepted locally (Stage B finals at `3cece0a`; results commit `26bd667`). I1 is on main: the coverage bootstrap merged through PR #279 at `4ed9b25`, and its main-push baseline is accepted. The I2/I3 integration merge `ea88814e` (tree `9048bc8d`) is committed locally and accepted, with its I3 evidence and WSL platform remainder. Codex accepted the I4 exact-source finals at `ea88814e` on 2026-10-10: the Windows and WSL full canonical gates and validation pass; Optimus 89.37 % (Windows) / 88.95 % (WSL), Context Engine 95.92 %, model policy 96.99 %, Windows gap ratio 1.003. Separately, the S1 reader correction is prepared and pending review; it needs a newly reviewed committed candidate pin before I5. I5 (publication/PR, candidate Linux CI and the safety comparison), closure and cleanup are held; the lane branch is not pushed. See "Current delivery and status (2026-10-10)" and "I4 — exact-source finals at `ea88814e` (2026-10-10)".
*Historical status at recording (committed with `26bd667`, 2026-10-09), kept as written:* **Status (2026-10-09, 07:24 UTC):** Stage A and Stage B Tasks 4–5 are accepted and locally committed. The Stage B Task 6 final gates ran at the governance commit `3cece0a` (tree `fabb6720…`) on independent native Windows and WSL clones and pass: Optimus coverage 87.772781 % (Windows) and 87.214201 % (WSL), Windows gap ratio 1.001314. Codex accepted the local evidence on 2026-10-09 at 07:24:20 UTC. Remote Linux CI and the base/candidate safety-row comparison are UNKNOWN; complete Task 6 and plan closure remain open. Nothing is pushed. See "Current delivery and status (2026-10-09)" and "Stage B Task 6 — final gates at `3cece0a` (2026-10-09)".
*Historical status at recording (committed with `3cece0a`, 2026-10-09), kept as written:* **Status (2026-10-09):** Stage A (Tasks 0–3) and its Task 6 at `acc2a1c` are accepted and locally committed. Stage B Tasks 4–5 are accepted and locally committed, and the delivered Stage B source contains the Stage B corrections: b0 (the explicit `core` rule for the WSL IPC node and the slow-node measurement refresh) was delivered in Task 4 at `43eb190`, and the partial-index correction and the quick commit-audit switch in Task 5 at `66ddabf`. Checkpoint C and G were accepted on candidate C7c and Checkpoint D on candidate E (pairs5 median core wall improvement 26.2040537 %, E-source timing under ambient load). Stage B Task 6 (independent final Windows and WSL gates) has not run. Remote Linux CI and the safety-row comparison are UNKNOWN. Nothing is pushed. See "Current delivery and status (2026-10-09)".
*Historical status at recording (committed with `1c7be2d`, 2026-10-05), kept as written:* **Status (2026-10-05):** Stage A (Tasks 0–3) is accepted and locally committed. Its Task 6 final gates ran at `acc2a1c`, pass on Windows and WSL, and are accepted locally (section "Task 6"). Remote Linux CI and the safety-row comparison are UNKNOWN. Stage B (Tasks 4–5, and the partial-commit correction) is required and open under `P11-FEAT-TEST-PROFILES`. Nothing is pushed.

*Historical intake status, kept as written:* Task 0 complete pending Checkpoint A (Fable 5.1, then Codex). Every result here is provisional development evidence bound to the stated source identity. The final full-run confirmation of the overhead fix belongs to the first delivery's Task 6. Tasks 1–6 are not started.

This report is the plan's single evidence report. Each later stage appends its own sections and never relabels an earlier one.

## Current delivery and status (2026-10-11)

This is the report's one current-status section; it is updated in place (last on 2026-10-11, after Codex's 10:45:23 UTC acceptance of the PR #280 CI and safety evidence; earlier on 2026-10-11 after the C acceptance; it was dated 2026-10-10 before that, and 2026-10-09 before then). The status lines of the dated sections below are **historical status at recording**: they are kept as written, and where one no longer describes the current state it carries a dated annotation. The manifest follows the same convention: its top-level `current_delivery` holds the current state, and each section's `status` string is historical.

### Local commits on `agent/claude/plan-11-30-test-profiles` (original base `main` `a929aab`; `main` `4ed9b25` merged in at `ea88814`)

| Commit | Subject | Delivers |
|---|---|---|
| `e3fe91f` | docs(plan-11.30): file approved intake and decisions | intake documents |
| `d562e95` | fix(testing): stabilize run records and validate registry receipts | Task 0 |
| `0a66609` | docs: record Plan 11.30 Checkpoint B acceptance | Checkpoint B acceptance record |
| `1f8ca30` | test: add Plan 11.30 profiles and checkpoint selection | Tasks 1–2 |
| `1b300cf` | test: add Plan 11.30 product coverage gates and commit-profile hook | Task 3 |
| `acc2a1c` | docs: record Plan 11.30 Task 3 acceptance and Task 6 authorization | the Stage A Task 6 measured pin |
| `1c7be2d` | docs: record Plan 11.30 Stage A Task 6 results at acc2a1c | the Stage A Task 6 report and docs |
| `43eb190` | test: add Plan 11.30 audit depth, export cache and measurement reuse (Task 4) | Task 4 and Stage B's first change (b0) |
| `66ddabf` | test: add Plan 11.30 core-only xdist, index scanning and quick commit audits (Task 5) | Task 5, the partial-commit correction and the quick commit-audit switch |
| `3cece0a` | docs: record Plan 11.30 Stage B delivery before final gates | the seven-path governance commit; the measured Stage B Task 6 pin (tree `fabb6720…`) |
| `26bd667` | docs: record Plan 11.30 Stage B final gates at 3cece0a | the Stage B results documentary commit; it records results measured at `3cece0a` and is not itself measured source |
| `ea88814` | Merge main 4ed9b25 into the Plan 11.30 profiles lane: one canonical coverage gate, validity layer, ADR-020 | the I2/I3 integration merge (tree `9048bc8d`; parents `26bd667` then `4ed9b25`); the accepted I4 exact-source final pin |
| `343b233` | fix(coverage): read compare's run records through the run-context reader; record I4 results | the S1 reader correction with the S2 workflow comment and the I4 results composition (tree `8a39467d`; single parent `ea88814e`); a new source candidate and the accepted corrected-source I4 measurement pin C |
| `281f8ce` | docs: record Plan 11.30 S1 delivery and corrected-source finals at 343b233a | the D2 documentary delivery (tree `a45e448d`; single parent `343b233a`); documentary only, not measured source; pushed without force as the head of PR #280 |

**Published and CI identities (2026-10-11).** Under the operator's exact approval, the branch was pushed without force at exactly `281f8ce77b6c7e8c43545e7c610b1aab475e5981` (D2) and [PR #280](https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/280) was opened to `main` (base `4ed9b252bc63a4ffd7179c34083af28566bee0a7`). The PR's candidate Linux CI ran on the actual PR merge commit `1946713e6c86a4a1f6db7335955c982e980c404c` (parents base then branch; tree `a45e448db244e4f5cd78e38f4fa2e3b180b1e467`, equal to D2's). The trees are equal, but the commits are distinct: the CI evidence is bound to `1946713e`, not to the branch head. The commit that records these results (D3) is documentary only and is not measured source. Merge to main, cleanup and any update of the published branch are held; the existing push grant covered exact D2 only. Separately, the I1 bootstrap was published from its own branch `agent/claude/plan-11-30-coverage-bootstrap` (commit `6f1935d`) and merged to main through PR #279 at `4ed9b25`, under the operator's bootstrap publication grant; that grant does not cover this lane.

*Superseded (2026-10-11, after Codex's 10:45:23 UTC acceptance), kept as written:* The lane branch is not pushed; its push, PR, merge to main and cleanup are held (I5). The commit that will record the 2026-10-11 results is a third, documentary-only HEAD after the old acceptance pin `ea88814e` and the new measurement pin C `343b233a`; it is not measured source. Separately, the I1 bootstrap was published from its own branch `agent/claude/plan-11-30-coverage-bootstrap` (commit `6f1935d`) and merged to main through PR #279 at `4ed9b25`, under the operator's bootstrap publication grant; that grant does not cover this lane.

### Measured and documentary pins (kept separate)

| Pin | Status |
|---|---|
| `ea88814e` | old acceptance: the I4 exact-source finals (2026-10-10) |
| C `343b233a` | the local Windows and WSL corrected-source finals (2026-10-11) |
| D2 `281f8ce7` | documentary; the published PR #280 head; not measured |
| `1946713e` | the PR #280 CI merge ref: candidate Linux CI and the seven-module safety comparison |
| D3 | the eventual commit recording these results; documentary only, not measured |

### Status

- **Stage A** (Tasks 0–3 and Task 6 at `acc2a1c`): accepted and locally committed, within the qualifications in its sections.
- **Stage B Tasks 4–5:** accepted and locally committed. The delivered Stage B source contains the Stage B corrections: b0 (the explicit `core` rule for the WSL IPC node and the slow-node measurement refresh) was delivered in Task 4 at `43eb190`; the partial-index correction and the quick commit-audit switch were delivered in Task 5 at `66ddabf`.
- **Checkpoint B's Task 5 worker obligation** (kill-on-close and attribution) is discharged for the accepted native Windows controller topology, by `test_an_interrupted_controller_leaves_no_worker_running`, `test_a_grandchild_left_running_by_a_worker_is_an_escaped_descendant` and the accepted D-M1 phase/channel controls. The real grandchild control checks parent-worker attribution, the INVALID verdict and termination. WSL keeps its weaker capability label. This does not discharge F4: the abrupt hard kill of the outer runner still orphans its subruns.
- **Stage B Task 6 (updated 2026-10-09 07:24 UTC):** the final gates ran at `3cece0a` on independent native Windows and WSL clones and pass. Codex accepted the local evidence on 2026-10-09 at 07:24:20 UTC (section "Stage B Task 6 — final gates at `3cece0a` (2026-10-09)").
- **v5 (2026-10-09):** the operator approved complete v5 `149002fa…`; v4 is superseded and archived. The approved v5 bytes are frozen.
- **I1:** the coverage bootstrap merged to main through PR #279 at `4ed9b25`. Codex accepted its main-push baseline (run 37964416192) with the Q-C1/Q-C2/Q-C3 qualifications (section "I1 — coverage bootstrap on main via PR #279 and main-push baseline `4ed9b25` (2026-10-09)").
- **I2/I3:** the integration merge `ea88814e` (tree `9048bc8d`) is committed locally with normal hooks and accepted. The I3 audits, stability repeats and WSL platform remainder are accepted and stay bound to their tested trees (section "I2/I3 — integration candidate, I3 evidence and the integration merge `ea88814e` (2026-10-10)").
- **I4 (accepted at `ea88814e`, 2026-10-10):** the Windows and WSL full canonical gates and validation pass; Optimus 89.37 % / 88.95 %, Context Engine 95.92 %, model policy 96.99 %, Windows gap ratio 1.003; the forward WSL platform obligation is discharged at this pin (section "I4 — exact-source finals at `ea88814e` (2026-10-10)"). This acceptance is exact-source and does not transfer to a later pin.
- **S1 (delivered and accepted, 2026-10-11):** the `compare` reader correction, with the S2 workflow comment and the I4 results composition, is local commit `343b233a` (single parent `ea88814e`, tree `8a39467d`, 10 paths), delivered with normal hooks; Codex accepted the delivery with the disclosed receipt defect (section "S1 delivery at `343b233a` (2026-10-11)").
- **Corrected-source I4 finals at C (accepted, 2026-10-11):** at the new measurement pin C `343b233a`, the Windows and WSL full canonical gates and validation pass on the 7,412-node universe; Optimus 89.4515 % / 88.8835 %, Context Engine 95.9243 %, model policy 96.9880 %, Windows gap ratio 0.966; S1's forward WSL platform obligation is discharged at C only (section "Corrected-source I4 finals at C `343b233a` (2026-10-11)"). The I4 acceptance at the old acceptance pin `ea88814e` stays as recorded and bound to that pin.
- **D2 (delivered and accepted, 2026-10-11):** documentary commit `281f8ce7` (single parent C `343b233a`, tree `a45e448d`), delivered with normal hooks on the one released attempt; commit seal `0d64b375…`; the pre-attempt owned-process check is receipted (08:15:02Z, 0 lane-owned processes). Its hook run `20261011T081551-28460-343e44` (6,365 passed, 37 skipped, 0 failed) is coverage-free and not a final. D2's forward WSL platform obligation is discharged at D2: 1,574 nodes reused from C under Codex's input-specific scope disposition, plus the 55 `test_ci_parity` nodes run on WSL at D2 (run `20261011T083201-525-8c700e`, 55 passed); 1,629 in total, 0 failed or missing (section "D2 delivery and WSL discharge (2026-10-11)").
- **I5 publication (2026-10-11):** under the operator's exact approval, the branch was pushed at exactly `281f8ce7` with no force, and PR #280 was opened to `main` (base `4ed9b252`) with the reviewed title and body. The original `Masterplan impact` run `38125646844` failed on a malformed declaration that Codex itself supplied; the body was corrected under release to `Master-plan impact: updated — HARDENING-TRACK-CI-GUARDRAILS` (r3 SHA-256 `e51d1be7…`), and the edited-event run `38126187842` succeeded. Both runs are kept (section "I5 publication and PR-body correction (2026-10-11)").
- **I5 candidate Linux CI and safety (accepted 2026-10-11 10:45:23 UTC):** guardrails run `38125646691` on the PR merge commit `1946713e` succeeded; Optimus 88.8591 %, Context Engine 95.9243 % and model policy 96.9880 % pass; Evidence Handoff and the aggregate are informational; exactly one eligible full session, `20261011T084124-2858-534abb`; all seven safety modules are identical to the accepted I1 baseline, so there is no regression (section "I5 candidate CI and seven-module safety comparison (2026-10-11)"). The concrete merge-ref run and its provenance are accepted; universal metadata independence is not claimed, and the acceptance does not transfer automatically to a future main commit.
- **Retained residuals (unchanged by the CI acceptance):** optional seam, overlap, cache-validation and lookup upkeep under `P11-FEAT-TEST-PROFILES`; the MAIN-5 environment observation under P11-FU-32; A2A, binding/desktop, hardening registry/activation and the existing finding owners, unchanged. Registry archival stays **723/724 PARTIAL/non-passing**, with the UNKNOWN entry untouched; successful CI does not clear it. S4 stays an explicit exactly-one evidence obligation, discharged for this candidate by the replay.
- **Open (all held):** (1) the D3 documentary commit and any update of the published branch, each under its own bounded authority (the existing push grant was for exact D2 only); (2) merge to main, then main-push evidence at the actual main commit; (3) terminal acceptance, closure, archival and cleanup, including the Stage B, I4 and C final clones. The CI backstop for the partial-commit correction also remains open.
- *Superseded (2026-10-11, after Codex's 10:45:23 UTC acceptance), kept as written:* the earlier 2026-10-11 bullet was "**Open (all held):** (1) this documentary delivery, under its own reviewed commit grant; (2) concrete operator push/PR authority for the lane after latest-main reconciliation (the bootstrap publication approval does not cover this branch); (3) actual Linux CI and artifact origin, and the seven-module safety comparison against the accepted I1 baseline; (4) merge to main, closure, archival and cleanup, including the Stage B, I4 and C final clones. The CI backstop for the partial-commit correction also remains open."
- *Superseded (2026-10-11), kept as written:* the 2026-10-10 bullets were "**S1 (pending, separate from the I4 acceptance):** the `compare` reader correction, with the S2 workflow comment, is prepared test-first and pending Fable then Codex review. It then needs a separately released local commit that becomes a newly reviewed candidate pin, with its own verification disposition, before I5." and "**Open:** I5, that is publication/PR of the lane, candidate Linux CI and the base/candidate safety-row comparison (the base is the accepted I1 main-push run; the candidate side is UNKNOWN), and merge to main; the CI backstop for the partial-commit correction; plan closure. Cleanup is held, including the Stage B and I4 final clones."

### Decision-record number at integration

The Plan 11.30 decision record was drafted, reviewed and committed on this branch as `docs/decisions/ADR-016-test-cadence-product-coverage-and-staged-delivery.md`, citing source S3. Main had meanwhile filed its own ADR-016 to ADR-019 and sources S3/S4, so the integration renumbers the unpublished record ADR-020 and its source S5. Every dated section, receipt, manifest entry and sealed snapshot below keeps the draft number and path it recorded.

### Reconciliation of earlier open statements (2026-10-09)

The following earlier statements describe work that is now delivered. They are kept as historical text:
- the 2026-10-05 top status line;
- the Task 3 residuals on the partial-commit gap and the later snapshot refresh;
- the Stage A Task 6 qualification calling the IPC rule "the first required Stage B source change", and its "Still open" list.

The IPC rule and the measurement refresh were delivered at `43eb190`. The partial-index correction and the quick commit-audit switch were delivered at `66ddabf`. No source work from those statements remains required. The final full gates have since run and been accepted locally (2026-10-09 07:24 UTC); the CI backstop remains open. The earlier "Stage B Task 6 — not yet run" placeholder is historical.

**2026-10-10:** the 2026-10-09 top status line and the "Still open" list of "Stage B Task 6 — final gates at `3cece0a` (2026-10-09)" describe the state before the v5 integration; they are kept as historical text. Under v5, remote Linux CI and the base/candidate safety comparison are I5; the I1 base is accepted, the candidate side is not yet run.

**2026-10-11:** the S1 "pending" wording committed with `343b233a` (the 2026-10-10 top status line, the S1 bullet above and the "Still open" list of "I4 — exact-source finals at `ea88814e` (2026-10-10)") is an approval-time snapshot, not a claim that the later commit failed to land. It is kept as historical text. S1 was delivered at `343b233a` and accepted, and the corrected-source I4 finals at C were accepted (sections "S1 delivery at `343b233a` (2026-10-11)" and "Corrected-source I4 finals at C `343b233a` (2026-10-11)").

**2026-10-11, after Codex's 10:45:23 UTC acceptance:** the wording committed with `281f8ce7` that describes the documentary delivery, publication or CI as held, or the lane branch as unpushed (the top status line now labelled historical, the superseded paragraph and bullet in the section above, and the "Still open" list of "Corrected-source I4 finals at C `343b233a` (2026-10-11)"), is an approval-time snapshot. It is kept as historical text. D2 was delivered and accepted, PR #280 was published, and its candidate Linux CI and safety comparison were accepted at merge ref `1946713e` (sections "D2 delivery and WSL discharge (2026-10-11)", "I5 publication and PR-body correction (2026-10-11)" and "I5 candidate CI and seven-module safety comparison (2026-10-11)"). Merge and closure remain held.

### Provenance conventions

- **Current authority** for the Stage B dispositions is Codex's dated sections in [`docs/superpowers/reviews/2026-10-05-plan-11-30-task3-codex-review.md`](../docs/superpowers/reviews/2026-10-05-plan-11-30-task3-codex-review.md), the newest being "Stage B Task 6 — local final evidence accepted; results composition released" (recorded 2026-10-09 07:24:20 UTC), after "Stage B Task 6 preparation — audit dispositions and final-byte gate" (recorded 2026-10-09 04:32:07 UTC). This report deliberately does not cite that file's current hash.
- **Current authority for the v5 integration (updated 2026-10-11):** Codex's dated sections in the same reviewer file, the newest being "PR280 CI and safety accepted — final documentary composition released" (recorded 2026-10-11 10:45:23 UTC), after "PR280 declaration correction verified — main CI evidence remains pending" (2026-10-11). Earlier on 2026-10-11 the newest was "S1 delivery and corrected-source I4 finals accepted — documentary composition released", after "S1/results batch accepted — one local commit attempt and conditional new-pin finals released" (2026-10-11). On 2026-10-10 the newest was "I4 accepted at ea88814e — bounded reader correction and results composition released", after "Integration delivery accepted — I4 exact-source finals released at ea88814e".
- **Review snapshots imported for the final documentary composition (D3, 2026-10-11, after the 10:45:23 UTC acceptance):** Codex's review file at SHA-256 `f8de3161ee834590af9c314c8a3c99dfb4fa0a1a7fd508afef600282b2a23613` and the reviewer-owned kickoff at SHA-256 `cc1058fd7490e59dc7d9a1e6f5240d8a754d857a890f18baef0c514e43189b27`, each copied byte for byte into `docs/superpowers/reviews/` from a verified immutable snapshot. These digests identify only those snapshots.
- **Review snapshots imported for the 2026-10-11 documentary composition:** Codex's review file at SHA-256 `b8ba78f634c736aa8619f431b37b00e8b382c1a8d8a74512efc7a6e977f04696` and the refreshed reviewer-owned kickoff at SHA-256 `f5516cada46ed33f1a1074bb7be1fd85f95464e1df18b1151a2d7556ce518c8d`, each copied byte for byte into `docs/superpowers/reviews/` from a verified immutable snapshot. These digests identify only those snapshots.
- **Review snapshot imported for the 2026-10-10 results composition:** SHA-256 `d665e5b467a189eb2399c6dd7d5aabe8c91ab62b3ecaa67abe06f6b313316f05`, copied byte for byte into `docs/superpowers/reviews/`. This digest identifies only that snapshot.
- **Review snapshot read during drafting (2026-10-09):** SHA-256 `0d50118aea616e169593bc873c7ba3f829b521e4df06e28751cdf62b670572b2`. The file has changed since; this digest identifies only that snapshot.
- **Abbreviated hashes** ending in "…" are display and provenance identifiers, not claims of full-digest verification; full digests are in the manifest. A historical snapshot hash identifies a retained sealed snapshot, not current bytes.
- **Report-derived calculations** are labelled with their formula, inputs and candidate. They are kept apart from recorded values and from Codex's acceptance.

## Task 0 — Windows overhead, registry pollution and archival design

### Source, environment and identities

| Item | Value |
|---|---|
| Implementation lane | worktree `C:\worktrees\optimus-cost-agent-worktrees\optimus-cost-agent-wt-claude-p1130`, branch `agent/claude/plan-11-30-test-profiles` |
| Base | `main` `a929aab2092876ab0d83ecc4e46896ae3a0935c0` (unchanged at fetch, 2026-10-04) |
| Pre-fix source | base + intake documentation diff SHA-256 `8bc1c6f984bcccd93df5a97ab255aa59de744999012168f22681630d2fc9a53b` (docs index and backlog only) |
| Post-fix source (first attempt) | base + diff `bd5dabc87546367b898accdc6d9fd88afd57e08921a4c45f61c55e0f37a7af0e` |
| Post-fix source (fix-check runs) | base + diff `8ac5f80f454ef1fd1367011a2324175f9c7612b9884b813495044469e644ccbc` |
| Checkpoint A amended source | recorder code (`tools/testing/run_context.py`, `run_context_records.py`) byte-identical to the fix-check source; after Fable 5.1's review only the lifecycle test file, the maintenance tool and its tests, and these reports changed. Per-file SHA-256 in the manifest |
| Windows | Windows 11 Pro 10.0.26300; Python 3.14.4; pytest 9.1.1; coverage 7.14.3; pytest-cov 7.1.0; uv 0.11.29; Git 2.56.0.windows.1; `pyproject.toml` `9fee0c4c…`, `uv.lock` `f1caae18…`; frozen env from `uv sync --frozen --extra dev` |
| WSL | Ubuntu-24.04, kernel 6.18.40.1-microsoft-standard-WSL2, Python 3.14.6, uv 0.11.31; separate native clone and frozen env |
| pytest-xdist | not installed; version and compatibility are selected in Task 5 (no install is authorised by Task 0) |
| Host security product | Bitdefender Antivirus active; Microsoft Defender passive (`AMRunningMode: Not running`) |

*Historical snapshot (annotation 2026-10-09): this table records the Task 0 environment. pytest-xdist 3.8.0 and execnet 2.1.2 were added to the lock in Task 5 (`66ddabf`), not retroactively in Task 0.*

### Provenance inputs (v4 Task 0 item 1)

External research is archival provenance, not a dependency. Each input below was hashed at Task 0 against its v4 pin. Only the qualification shown applies.

| Input | SHA-256 at Task 0 | v4 pin | Original verdict / limitation |
|---|---|---|---|
| Claude research report, corrected §13 / §13.4 | `f991c06a7ae51a30a10cfa1cefd7e7d472a012e303fed379028b45e384c6d9de` | `F991C06A…` match | Windows overhead cause **unknown**; append/antivirus attribution withdrawn. Its Linux-flat observation (2–4 ms CI gaps) is a research observation from retained CI logs, not re-measured here |
| Fable review of the research | `dc97731b7997c14d97adc51847f3cb7d6e6b8dc3b647e44447011f220bc6e3da` | `DC97731B…` match | SOUND WITH AMENDMENTS against the original research version |
| Claude review of the v1 draft | `8fea78cf6d4167ad5689d99195eb45ceb6dc65e48a80d3b26c7a25fffe2f3242` | `8FEA78CF…` match | NOT READY, 7 MAJOR / 6 MINOR |
| Claude re-review of v2 | `797fd9d04184e4fc9ea9136ec0ab9f4520fe1d5dc151d547f008aa2395dc0ef9` | `797FD9D0…` match | SOUND WITH AMENDMENTS, 2 MAJOR / 5 MINOR |
| Claude concurrence on v3 | `dff868d0b255838f49ee5c03c351b75ebf0b88dc085e965c8dddf823f080d2f4` | `DFF868D0…` match | Agreement on reuse, CI grant and staged route |
| New-chat handoff, 2026-10-04 | `b1cafa8914bc79b5762f87f4c5fc4c7691c750344dc38d140b700b62d8990dbd`, reverified by Codex at its original authoring output path (Checkpoint A review) | `B1CAFA89…` match | No copy exists in the shared handoff folder. Not relied on for any Task 0 claim |
| Retained research data `tier-runs-95505c4.txt` | `dafb7e4102b9934188e825514d68e2bd8b9539f2cc393cc565c03a2760bc154a` | named in v4 | Derived table; used only for the transition-kind breakdown below |
| `refrun-analysis.txt`, `tier-sizing.txt`, `win-vs-linux.txt`, `import-map.txt` | `83844b33…`, `76d21891…`, `415514e2…`, `b4f11a9a…` | named in v4 | Older `e9d6be0`/shared-machine data; not used for any Task 0 claim |
| Plan 11.28 acceptance-3 reference run `20261003T104058-46816-ca116c` (`95505c4`) | `run.json` `5e122943e134d19050520e8c24b74b15f5a92294892d17e554813d371348be4d`; `phases.jsonl` `82c71adc992c23f90918e894c10cb8c30b6e6e056cba976975f4b8b8b586c645` | named in v4 | ACTIVE, COMPLETE, exit 0, parent UNKNOWN (`registry_partial`). Used only to show the growth is equal in all three transition kinds |
| Older reference run `20261002T203101-45752-c1999b` | `run.json` `c358780a5fdf5af5f270c51a6b18b8dc91c2c02bf94f053be77adb8ca3f26e49` | named in v4 | Exit 1, completeness **INVALID**; not used |

### Prerequisite dispositions

| Prerequisite (v4) | Disposition at Task 0 |
|---|---|
| Merged 11.28 + shared guidance; clean current main | Satisfied: `a929aab` |
| Cause of Windows overhead and regression fixture | Established and fixed (below); full-run confirmation is Task 6 |
| Context Engine / `optimus_model_policy` on main | Absent on `a929aab` (`src/` holds `optimus`, `optimus_gateway`, `optimus_security`, `evidence_handoff`, `evidence_handoff_runtime`): N/A on this source, never a gate result |
| Registry inventory and housekeeping mechanism | Inventory taken read-only; mechanism built; host archival awaits an exact class grant |
| Tooling versions / xdist | Recorded above; xdist UNKNOWN until Task 5 |
| Real WSL, independent env | Available and used |
| Historical binding objects for bound audits | `tests/plan1126_unrun_binding.json` present; bound-audit claims are outside Task 0 |
| Fable 5.1 and Codex reviewers | Operator schedules; not messaged by the implementer |
| Paid calls / services | None used |

### Inventory

- Default selection on the base: 5,184 collected, 111 deselected by the default marker expression.
- Temporary core node list `tmp/plan-11-30-core-nodeids.txt` (ignored, SHA-256 `062320611a0c6a003ae51a02ff767001de504fca3f020d4333906924d05dcdc7`): 3,821 node IDs, the default selection minus the research tier exclusions (run-context/process-tree, the Plan 11.26 audit family, the five proc-heavy gate files, `tests/e2e`, the MAIN-5 guard). Passed as `@file`; `-m` unchanged, so every run is ACTIVE unless `--test-run-context=passive` is given.
- Child launch-site map `tests/unit/tools/run_context_child_sites.json`: 78 sites in 30 files after this task (one site added, below).

### Reproduction and discrimination (pre-fix)

All runs serial, same frozen environment, identical node-list bytes, one coverage writer. Gap predicate exactly as v4 §6 (`gap_i = next.at - (prev.at + prev.seconds)` in recorded order; first and last `k = floor(N/10)` transitions; ordinary medians; `last <= 2 x first`; UNKNOWN for `N < 10` or a non-positive first median; negative gaps reported, never clamped).

| Run | Mode | Coverage | Wall | Phase sum | Gap sum | N / k | First / last median | Ratio | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| `20261004T103059-24588-6332c9` | ACTIVE | on | 628 s | 203.5 s | 403.0 s | 11443 / 1144 | 7.0 / 58.0 ms | 8.29 | FAIL (reproduces) |
| `20261004T104215-55844-00df20` | ACTIVE | off | 647 s | 207.0 s | 423.7 s | 11443 / 1144 | 7.0 / 65.0 ms | 9.29 | FAIL (reproduces) |
| `20261004T105330-42060-4ddeb5` | PASSIVE | on | 675 s | 204.9 s | 449.5 s | 11443 / 1144 | 7.0 / 60.0 ms | 8.57 | FAIL (reproduces) |
| `20261004T110548-20320-f3b48f` | ACTIVE, instrumented | on | 651 s | 212.8 s | 421.5 s | 11443 / 1144 | 7.0 / 61.0 ms | 8.71 | FAIL (reproduces) |

Every run: exit 1 from one unrelated documentation failure (below), 3,782 passed, 38 skipped, records COMPLETE, 11,444 phases. Precision of these records: 1 ms. Every run's parent is UNKNOWN (`registry_partial`): the host registry holds more than the 512 entries a run reads, so every sample reports `registry: partial`. No ancestry or overlap claim is made from these runs.

**Host load.** The runs' own samples list the other registered runs alive at each phase boundary. Pre-fix runs r1–r3 list no live foreign run; the only listings are stale roots whose process query failed (`unknown`). That is an observation with the partial-registry limit: a run reads at most 512 registry entries, so it cannot establish that no foreign load existed. **Every post-fix run (r5–r8) overlapped, in every sample, a live default run from another lane** (`20261004T114222-51636-016cc7`, worktree `wt-claude-plan12-cp4`, relation `outside`). **The post-fix ratios satisfy the predicate under an identified overlapping lane. Host load was neither matched nor completely observable, so no conservative-comparison claim and no isolated wall-time speedup claim is made.** Contention, scheduling and cache effects can move both decile medians and their ratio in either direction. (Amended after Codex's Checkpoint A review, C-M2.)

**Instrumentation overhead.** The instrumented run d1 versus the uninstrumented r1 (same mode): wall 651 s vs 623 s to the last phase end, phase sum +9.3 s, gap medians 7.0/61.0 ms vs 7.0/58.0 ms, ratio 8.71 vs 8.29. Instrumentation did not create or hide the growth.

**Discrimination.** Coverage off reproduces as strongly as coverage on, and PASSIVE (no job, no guard) reproduces as strongly as ACTIVE. In these controls, then, neither coverage nor the Plan 11.28 job and guard is a necessary trigger of the growth. That does not establish the absence of every possible interaction with them. Both coverage modes are required fix-check modes.

### Diagnosis

Each step was measured before any harness change.

1. **Where the time goes.** A diagnostic plugin timed every `pytest_runtest_makereport`/`pytest_runtest_logreport` implementation per phase (run `20261004T110548-20320-f3b48f`). The whole growing gap is the root conftest's `pytest_runtest_logreport`, i.e. `run_context.record_phase`: decile medians 6.7 → 60.7 ms. Every other hook stayed below 0.2 ms. GC time, Python threads (1–4), native threads (4–7) and the process handle count (≈300) stayed flat. The retained `95505c4` reference run shows the same growth in all three transition kinds (setup→call, call→teardown, teardown→setup), which fits a per-phase-report cost, not a per-test fixture.
2. **Which part of the recorder.** In-process timings over a 1,500-test prefix: `record_phase` ≈ `append_entries` (5.2 → 25.3 ms). The shared sanitizer, the field table, `sys.audit`, `stat` and `open` stayed flat. `close()` of a separate small probe file grew 3.1 → 9.2 ms in the same process.
3. **Kernel wait, not computation.** A raw `os.close()` after a write grew 2.5 → 16.4 ms with zero thread CPU time, while a read-only open/close stayed at 0.3 ms. No Python hook was involved (`open` is `io.open`; no trace, profile or `sys.monitoring` tool). Over run `…6332c9` the job used 175 s of CPU in 628 s of wall time.
4. **Standalone controls, all flat.** Replaying `append_entries` (≈0.17 ms per close), writing 20,000 distinct files, starting 400 child processes, and 120 rounds of `other_runs` (≈61,000 `OpenProcess` calls) all stayed flat in a fresh process.
5. **The trigger.** Milestone probes (retained, d4) showed `close()` fast through configure, session start and collection, then jumping during the call phase of `tests/integration/evidence/test_mixed_artifact_gate.py::test_mixed_artifact_dispositions`. Bisected in bare processes: certain Pillow PNG encode paths flip the process, after which every later `close()` of a file it wrote costs about 2 ms instead of 0.08 ms.
   - One encode into memory suffices.
   - A single encode straight to a file did not flip it, even 3 s later; a second file encode did.
   - zlib alone, opening or decoding a PNG, and the redaction gate's DACL calls do not flip it.
   - Which step inside Pillow, and which host component, is not established.
6. **The growth.** In a flipped process, open/append/close per entry of one growing stream costs ≈5 → 29 ms over 6,000 entries. A held handle with write + flush per entry costs a flat ≈0.011 ms, with one ≈31 ms close at the end. In an unflipped process, reopen per entry stays at ≈0.2 ms and a held handle at ≈0.013 ms. Whether the cost grows with the number of closes or with file size is not separated by this data. The fix removes the per-phase close either way.

   Steps 4–6 were first measured during diagnosis, and their numbers were transcribed into the implementer's ledger. The probes were then re-run after the Checkpoint A review on the same host, with every output retained (`probes-retained-20261004T124616/` in the receipts). The re-runs reproduce the transcribed values; the figures above are the retained ones. Steps 1–3 and the d4 milestones rest on outputs retained from the original runs.

**Cause.** On this host, once a process has encoded a PNG through Pillow, every `close()` of a file that process wrote blocks in the kernel, and for longer as the run proceeds. This is consistent with an on-access file-system filter; which component is not established, and host security settings are out of scope. The run-context recorder opened, appended to and closed `phases.jsonl` once per test phase, so every inter-phase gap paid one such close. The research's observation that Linux CI gaps stay flat (2–4 ms) fits this, but it was not re-measured here. The cause is in the harness's use of the file system, not in product behaviour.

### Fix (test-first)

- **Held streams.** `run_context_records.append_entries(..., held=...)` opens each stream once per run, lazily, after every in-memory check. Each append is written and flushed to the operating system before the call returns. A failed stream is closed and dropped, and the existing restore-by-truncation, deferred-append and INVALID semantics are unchanged. `run_context` passes its `held` map and closes it before the terminal read-back (a failed close is a recording error) and again in `finish_run`'s `finally`.
  - RED → GREEN: `test_each_stream_is_opened_once_and_held_until_the_run_ends` (60 opens → 1).
  - Kept green: `test_an_append_with_unknown_progress_is_restored_then_retried_or_made_invalid`, with its injection moved from a failing close to a failing flush and its assertions unchanged.
  - Durability control: in the abrupt planted case, the setup phase recorded before the kill is readable.
- **Measurement precision.** `record_phase` now keeps phase `at`/`seconds` to microseconds (same fields, more digits). After the fix, gaps fall below 1 ms, and at 1 ms resolution the coverage-off post-fix run's first-decile median was 0, so §6 returned UNKNOWN. RED → GREEN: `test_phase_times_keep_sub_millisecond_precision`.

### Fix check (post-fix, matched)

Same node-list bytes, flags and frozen environment as the pre-fix runs; both coverage modes reproduced pre-fix, so both are fix-check modes. The fix-check result is provisional until the first delivery's serial full Windows coverage run (Task 6).

| Run | Source | Mode | Coverage | Wall | Gap sum | First / last median | Ratio | Verdict |
|---|---|---|---|---|---|---|---|---|
| `20261004T115442-33504-b8e39c` | `bd5dabc8` | ACTIVE | on | 212 s | 11.3 s | 1.0 / 1.0 ms (1 ms precision; 592 negative gaps) | 1.0 | PASS |
| `20261004T115840-42472-aa79f7` | `bd5dabc8` | ACTIVE | off | 200 s | 11.3 s | 0.0 / 1.0 ms (1 ms precision; 604 negative gaps) | — | UNKNOWN (retained) |
| `20261004T120544-17508-047bbb` | `8ac5f80f` | ACTIVE | on | 209 s | 9.5 s | 0.371 / 0.407 ms (1 µs precision; 0 negative gaps) | 1.10 | **PASS** |
| `20261004T120919-34428-c7ee88` | `8ac5f80f` | ACTIVE | off | 204 s | 9.6 s | 0.350 / 0.409 ms (1 µs precision; 0 negative gaps) | 1.17 | **PASS** |

### Registry pollution and archival

**Amended after the Checkpoint A review (Fable 5.1, Finding 1).** Python resolves its temporary directory from TMPDIR first, then TEMP, then TMP, on every platform. The first isolation set only TEMP/TMP. In an environment that exports TMPDIR (as this host's agent shell sometimes does), every child therefore announced itself in the **real** registry. The environment of the original focused gate was not recorded, so that gate's isolation proof is **withdrawn**; the proofs below replace it.
- RED: with TMPDIR set, a nested child listed real-registry runs and never saw the synthetic marker.
- Fix: the fixture now sets TMPDIR, TEMP and TMP, through its own MonkeyPatch, so a test's `monkeypatch.undo()` cannot end the isolation.
- Each test's synthetic registry carries a **passive marker announcement** that exists nowhere else. The nested-outcome and repeated-session children must list it in their own samples, which positively proves they read the synthetic registry. The abrupt planted case asserts its killed root's entry is in the synthetic registry and absent from the real one.
- The module-level negative-space control can attribute added entries only where validated ancestry exists (Windows). Elsewhere the positive marker checks carry the proof.

- **Leak isolation (lifecycle file).** Every nested, planted and repeated-session child now inherits TEMP/TMP pointing at one test-only temporary root, so it announces itself in a synthetic registry. The outer run's own announcement is copied in, so children still find their parent by validated ancestry. The parent reads and withdraws synthetic entries only inside a `view()` block within one phase. Between phases the outer run keeps sampling the real registry, so its overlap records never report a false empty registry. Job, guard and ancestry behaviour are unchanged.
- **Negative-space control.** A module-scoped fixture in `test_run_context_lifecycle.py` compares real registry names and bytes before and after the file while the outer run is active.
  - Added entries count as this file's only when their recorded parent chain reaches this run.
  - Removing an entry whose root had already ended is never legitimate.
  - Bytes of entries that stayed must not change.
  - Concurrent lanes are neither paused nor suppressed.
  - RED (pre-isolation, `abrupt_exit-venv_launcher`): 4 attributable leaked entries, and the killed planted root's entry was in the real registry. GREEN on Windows: the focused gate passes, and the real registry listing is identical before and after.
  - The RED demonstration itself leaked 4 entries into the host registry (`20261004T114340-17304-8fffcf`, `20261004T114340-3484-beeda6`, `20261004T114342-34364-3d06c4`, `20261004T114342-46164-476c42`; their worktree is present, so they are kept by the inventory).
- **Shared positive-end predicate.** `run_context.process_end_status(pid, creation_time)` returns `(ENDED | LIVE | UNKNOWN, basis)`:
  - Windows: `not_found`, `replaced` (the recorded process ended; the replacement is not touched) and `terminated` are ENDED; a denied or failed query and a missing creation time are UNKNOWN.
  - Elsewhere: `proc_absent` is ENDED, and `proc_present` is UNKNOWN, never identity proof.
  - `other_runs` uses it with one handle per root, as before.
- **Maintenance tool.** `python -m tools.testing.registry_maintenance` provides `inventory` (read-only; one new manifest; refuses a manifest the shared sanitizer would change), `archive` (dry run unless `--execute`; requires the manifest's class digest as the grant) and `verify`.
  - Eligible means a conforming record filed under its own run ID, whose recorded worktree is absent and whose root is ENDED.
  - Moves are link-then-unlink to `registry/ended/` (never an overwrite), with one append-only receipt per entry.
  - Changed bytes, changed status or a conflicting destination are refused and kept.
  - Interrupted moves are reconciled from disk.
  - Controls cover LIVE, UNKNOWN, access failure, PID reuse, replaced bytes, destination conflict, interrupted move and receipt, idempotent re-run and verify mismatches.
- **Host inventory (read-only; registry bytes identical before and after).** 732 entries, 724 eligible (701 `not_found`, 23 `replaced`), class digest `28bc1799eebba5f132996b366ee255ca0ccaf85f0a332df4e26316343009134a`.
  - Eligible origins: removed worktrees `wt-claude-runctx` (656), `ptc-int` (30), `ptc-va` (20) and `ptc-vb` (10), plus 8 children dated 2026-10-02 whose worktree was a pytest temp folder of `test_git_env_immunity` (older reason vocabulary; today's runs added none).
  - Kept: 3 UNKNOWN, 4 with a present worktree, and 1 LIVE run in another lane.
  - **No host entry was moved.** Archival needs the operator's grant naming this class digest.

### Verification

| Gate | Platform | Result |
|---|---|---|
| v4 Task 0 focused verify + maintenance gate + cross-cutting guards (logging-surface inventory, child-site map, walker review), final source | Windows | 361 passed, 1 skipped (POSIX-only), 124 s |
| Same, first post-fix source `bd5dabc8` | WSL attempt 3 | 313 passed, 48 skipped (Windows-native), exit 0; clone diff equals the Windows candidate |
| Same, final source `8ac5f80f` | WSL | 314 passed, 48 skipped (Windows-native), exit 0; all 9 changed files byte-identical to Windows (per-file SHA-256 in the manifest; the `git diff` stream hash differs only by git-version formatting) |
| Ruff on changed Python | Windows | clean |
| Focused gate after the Checkpoint A amendments, `TMPDIR` set to the real temp folder | Windows | 363 passed, 1 skipped; registry names unchanged except one foreign `plan12-cp4` run arriving (attributed by its worktree) |
| Same, `TMPDIR` unset | Windows | 363 passed, 1 skipped; real registry names unchanged |
| Same, `TMPDIR=/tmp` and `TMPDIR` unset | WSL (`wsl-final2-a1`) | 316 passed, 48 skipped each, exit 0; all changed files byte-identical to Windows |
| Focused gate after Codex's C-M1 correction and intake import, `TMPDIR` set / unset | Windows (gate5) | 378 passed, 1 skipped in each; registry changes during both runs were only `plan12-cp4` and `ghissues` lane runs arriving and withdrawing |
| Same, `TMPDIR=/tmp` / unset | WSL (`wsl-final3-a1`) | 331 passed, 48 skipped in each, exit 0. Every changed file is byte-identical to Windows except the backlog: Windows keeps Codex's two CRLF bytes in the working copy; the WSL clone holds Git's LF-normalised form, which is what any commit stores |
| Docs gate, imported intake (`tests/unit/docs`) | Windows | 84 passed with the intake plan files untracked. With them visible: 83 passed, 1 failed (the kickoff's link to the gitignored reviewer log; returned to Codex) |

### Failed, invalid and UNKNOWN outcomes (retained)

- Every core run exits 1 on `tests/unit/docs/test_open_work_pool_hygiene.py::test_priority_is_authored_only_in_table_cells`. The intake backlog edit (Codex-authored, uncommitted) contains `Priority:` outside a table cell. It is unrelated to timing and left for Codex.
- WSL attempt 1: 3 failed (the clone did not mirror the intent-to-add index). Attempt 2: 6 failed (`git apply --intent-to-add` replaced the clone index). Both are harness errors, retained; attempt 3 passed.
- Post-fix coverage-off run at 1 ms precision: UNKNOWN (above).
- The isolation RED leaked 4 host entries (above).
- The TMPDIR RED (Checkpoint A amendment) ran only the normal nested case. Its child announced and withdrew in the real registry, leaving nothing.
- The first post-amendment gate failed the logging-surface inventory: the new unreadable-receipt message exported exception text. Fixed by building the message from the line number; the next gate passed.

### Residuals and owners

- The host's per-process close cost still applies to files that tests themselves write after the Pillow trigger, inside their own phases. Phase sum fell 203.5 → 181.3 s rather than staying flat. Diagnosing or isolating the trigger test is outside Task 0. Owner: `P11-FEAT-TEST-PROFILES` (custody assigned in the backlog's Task 0 residual entry).
- At microsecond precision the §6 predicate's absolute medians are small. A future full run whose first-decile median reaches 0 µs would be UNKNOWN by contract.
- Plan 11.28 activation, cleanup and branch-folding holds are unchanged.
- `tests/unit/tools/test_run_context_boundaries.py` still plants two malformed/misfiled entries in the real registry and announces one nested run there. This is by ruling: it is `try/finally`-cleaned and proves live ancestry against the real outer run. A run interrupted inside that window would leave `zzz-*` entries the maintenance tool keeps forever. Owner: `P11-FEAT-TEST-PROFILES` (custody assigned in the backlog's Task 0 residual entry).
- The host registry exceeds 512 entries, so every run's parent is UNKNOWN (`registry_partial`) until an authorised archival reduces it.

### Raw receipts

Archival provenance, not a project dependency: `optimus-handoff\test-profiles-research\plan-11-30-task0-evidence-20261004\` (first seal: 161 files, `SHA256SUMS.txt` SHA-256 `5dc4c91b1170588ed16a550dfb5a526f25c40f643198353839457d3f4ecbd0d5`; after the Checkpoint A amendments: 208 files, `SHA256SUMS-v2.txt` SHA-256 `4703c118459dc0dad663f8b89cfb056598800a8ac18b86ee76cf5e64f5fea32a`, with v1 left unchanged and still verifying; after Codex's corrections: 223 files, `SHA256SUMS-v3.txt` SHA-256 `885933c55dd32de3e30989ffa261c192d4217ddcbbb8fddf2a6269d1906c0cca`, with v1 and v2 still verifying). It holds every run's `meta.txt`, console output and run-context record, the diagnostic plugin outputs, the WSL attempts, the host registry inventory and the diagnostic scripts and node lists. The manifest names each run's record digests.

### Checkpoint A review — Fable 5.1 (2026-10-04)

Verdict: **SOUND WITH AMENDMENTS**, 3 MAJOR / 8 MINOR. Fable independently re-derived every §6 verdict from the raw records and confirmed the following:
- the diagnosis chain (steps 1–3);
- the fix code and failure semantics;
- `other_runs` equivalence with the base;
- the maintenance tool's safety;
- the host inventory;
- all repository gates.

| Finding | Disposition |
|---|---|
| 1 MAJOR: TMPDIR defeats registry isolation | Fixed (RED → GREEN); positive marker proofs added; proven under TMPDIR set and unset on Windows and WSL; original gate's isolation proof withdrawn |
| 2 MAJOR: diagnosis steps 4–6 lacked retained outputs | Probes re-run with outputs retained and hashed; wording corrected (trigger path; Linux observation softened) |
| 3 MAJOR: provenance hashes not filed | Provenance table added above; the handoff pin was later reverified by Codex at its original authoring path |
| 4 MINOR: parent UNKNOWN / registry partial not surfaced | Stated above and per run in the manifest |
| 5 MINOR: no held-close terminal failure control | Added `test_a_held_stream_that_cannot_be_closed_makes_the_record_invalid` (a coverage control: the behaviour already existed, so it passed on first run) |
| 6 MINOR: scratch contexts keep held handles | Autouse finalizer closes every scratch context's held streams |
| 7 MINOR: `monkeypatch.undo()` could end isolation | Fixture uses its own MonkeyPatch |
| 8 MINOR: damaged receipt file raised a traceback | RED → GREEN: `ReceiptsUnreadable` → named `EXIT_MISMATCH`, nothing moved (`test_a_damaged_receipt_file_is_a_named_mismatch_never_a_crash`) |
| 9 MINOR: boundaries file still plants in the real registry | Recorded as a residual with owner (above) |
| 10 MINOR: instrumentation overhead not stated | Stated above |
| 11 MINOR (Codex-owned): intake backlog text stale | For Codex's intake-doc release and freshness audit |

### Checkpoint A review — Codex (2026-10-04)

Verdict: **HOLD for bounded corrections**. Codex independently verified both receipt seals and the per-file hashes, and recomputed the post-fix ratios (1.096 and 1.169). No new full suite or repeated diagnosis was requested.

| Finding | Disposition |
|---|---|
| C-M1: maintenance accepted a schema-valid but wrong receipt (wrong digest, class, paths, `LIVE`) as proof in `verify` and as `already_archived` in `archive` | Fixed test-first (14 RED → GREEN). A receipt now counts only if it is exactly the receipt the tool writes for that entry under that grant: exact field set; same name, digest, run ID, source, target, end basis and class digest; positive ENDED status; `archived`/`reconciled` disposition; well-formed UTC time. `archive` idempotency and `verify` share that match. Duplicates, mismatches, a receipt of this class that names no eligible entry, and a valid receipt without its archived copy are each named nonzero outcomes, and nothing unrelated moves. Interrupted-move reconciliation, idempotent replay and other grants' receipt history still pass. |
| C-M2: the host-load qualification overclaimed | Wording replaced (Host load and Discrimination paragraphs above). |
| Intake corrections (Codex) | Imported byte-identically into this lane: `.gitattributes` `-text` rules for v4 (filtered blob equals raw blob `3cef47af7a65010391d583b22cffa393959600ac`), corrected backlog and docs index, and the review itself. v4, the archives and the kickoff are unchanged. |
| Docs gate on the imported intake | Untracked intake files: 84 passed. With the intake files visible to index-scoped gates: one failure, `test_relative_markdown_links_resolve_except_registered_stale_links`. The kickoff links to the gitignored reviewer log `plan-11-30-review-checkpoints.md`, which exists only in the drafting checkout. This is Codex's file, so it is returned to Codex. |

### Checkpoint A follow-up — Codex E1 re-check (2026-10-04)

Codex confirmed the forged-receipt correction and reproduced two remaining receipt defects. Both are now fixed test-first, and the whole class was enumerated rather than only the two reported values.

| Defect | Fix and controls |
|---|---|
| `disposition=[]` raised `TypeError` instead of a named refusal | **The receipt file's structure is validated as a whole.** Every line must be a JSON object with exactly the receipt fields, the receipt schema, and **text values only**; otherwise the file is untrusted. `verify` returns `receipts unreadable at line N`; `archive` refuses with nothing moved. Controls (42 RED → GREEN): list, dict, integer and null values in each of the ten receipt fields, an extra field, a missing field, and Codex's exact `disposition=[]`. The enumeration also found a non-text `name`: such a receipt cannot be attributed to an entry, and would otherwise have let the entry be reconciled while a damaged receipt sat in the file. |
| `utc="2026-99-99T99:99:99+00:00"` passed `verify` and idempotency | **A receipt time must be ASCII, in the tool's own form, parse as a real datetime, and carry a zero UTC offset.** Controls (3 RED → GREEN, plus 5 shape cases): Codex's exact value, other impossible fields and days, full-width digits, a non-UTC offset, a space separator, a `Z` suffix and seven fraction digits. The tool's own microsecond times still verify. |

Semantic mismatches (wrong digest, run, paths, end basis, class, status, disposition or time) remain per-entry named mismatches. The structural rule moved the earlier "extra field" and "missing field" cases into the structural test, where they are now reported as unreadable lines.

**Intake documents re-imported** from Codex's corrections, byte-identically: `.gitattributes` (`-text whitespace=cr-at-eol` for v4), the docs index, the decision-log README (source S3, export SHA-256 `3ddd90f7…`, independently re-hashed), the backlog, ADR-016 (unpublished draft), the Codex review, and the kickoff. The kickoff changed from its intake pin `AC182523…` to `34cb257c…`: the reviewer-log reference is now plain text, not a link. v4 and its archives are unchanged; v4's Git blob still equals its raw bytes (`3cef47af…`).

| Gate | Platform | Result |
|---|---|---|
| Docs gate, every intake file visible to index-scoped tests | Windows | 84 passed |
| `git diff --check`, whole tree | Windows | clean |
| Local secret scan, every changed file (including the plan files and ADR-016) | Windows | 0 findings |
| Focused gate, `TMPDIR` set / unset (gate6) | Windows | 428 passed, 1 skipped in each; real registry listing unchanged |
| Same, `TMPDIR=/tmp` / unset (`wsl-final4-a1`) | WSL | 381 passed, 48 skipped in each, exit 0 |

**Retained harness error.** One edit of `tests/unit/tools/test_registry_maintenance.py` was written with CRLF line endings on Windows (Python `write_text`). The WSL byte comparison caught it (433 CR bytes; a commit would have stored LF). The file was normalised to LF and re-tested (86 passed, 1 skipped). The Windows gate6 ran the CRLF copy, which is content-identical to Python. Every other changed file is byte-identical between Windows and WSL; v4 keeps its two approved CRLF lines on both.

**Returned to Codex (ADR-016 draft, line 48):** the predicate row says "Windows identity evidence is weaker than Linux". It is the reverse: Windows checks PID plus creation time through a process handle, while POSIX has only `/proc/<pid>` presence, which v4 §2 calls the weaker capability.

### Checkpoint A accepted; local release (2026-10-04)

Codex accepted Checkpoint A at 15:04:45 UTC (`docs/superpowers/reviews/2026-10-04-plan-11-30-checkpoint-a-codex-review.md`). It released:
- the local intake commit and the local Task 0 commit, with `SKIP=optimus-pytest-coverage` for those two commits only;
- archival of the reviewed 724-entry class `28bc1799eebba5f132996b366ee255ca0ccaf85f0a332df4e26316343009134a`, only if a fresh inventory and dry run still match it;
- Task 1 after local delivery.

Push, PR, merge, service activation and paid calls stay held.

**Final documentation delta imported byte-identically:** the docs index, the decision-log README, the backlog, ADR-016 and the Codex review. Pins re-verified: v4 raw `8A40DEF6…`, staged and committed blob `3cef47af…`; predecessors v1 `E267774C…`, v2 `128E4FED…`, v3 `791E79E2…`, matching v4's own pins.

| Check | Result |
|---|---|
| Docs gate, intake visible (before the intake commit) | 84 passed |
| `ruff check .` | clean |
| `git diff HEAD --check` | clean |
| Local secret scan, every changed file | 1 finding, in this manifest (retained harness error below); 0 after the fix |
| Intake commit `e3fe91f` hooks | trailing whitespace, file size, Ruff, Bandit, ast-grep, config-trust scan and secret scan passed; YAML/TOML had no files; coverage hook skipped as released |
| Lane files after the hook's stash and restore | byte-identical to the pre-commit backup (20 files) |
| Docs gate after the intake commit | **1 failed, 83 passed** (below) |

**Docs gate failure after the intake commit (returned to Codex).** `test_post_amendment_plans_declare_prerequisites_with_required_columns` checks plans added in commits since the prerequisites amendment (`087560a8`). It could not see v4 until v4 was committed, so every earlier docs gate passed. v4's Tooling prerequisite row gives the disposition "early check distinguishes genuinely absent from merely unauthorized". The check requires a disposition that *starts with* "genuinely hard", "genuinely absent" or "merely unauthorized". v4 is byte-frozen, so this cannot be corrected in the implementation lane. Task 0 touches neither v4 nor the check.

**Retained harness error (secret scan).** The E1 follow-up recorded "0 findings", but that scan ran before the follow-up's verification block was added to this manifest. The block's key `secret_scan` trips the scanner's Secret Keyword detector, so Codex's accepted manifest snapshot (`09E90764…`) contained one finding that the commit hook would have refused. This refresh renames the key; nothing else in that snapshot changes.

**Registry archival: STOPPED, nothing moved.** The fresh read-only inventory (15:12:48 UTC; registry listing identical before and after) has 789 entries, 724 of them eligible. Its class digest is `57a4afe0ce9867b23a3d422e87195d7044e023e38e0a1fb61803fcf2e280c98e`, not the granted `28bc1799…`. The read-only delta:
- 722 reviewed entries are still eligible, with identical names and bytes.
- 2 left the class (`20261003T082415-47540-ade221`, `20261003T172719-54948-9e6cbf`). Their recorded root PIDs are now held by processes this account cannot query, so their end status is UNKNOWN (`query_failed`). That is the conservative result.
- 2 joined (`20261002T161642-50540-15569b`, `20261002T191731-50540-19494d`). They were UNKNOWN (`query_failed`) at review time and are now `not_found`.
- 13 stayed eligible with a different ENDED basis (7 `not_found` → `replaced`, 6 `replaced` → `not_found`): PID reuse.
- 58 new names, all with a present worktree (`ghissues` 46, `plan12-cp4` 11, `mut-t4b` 1), so none is eligible. The LIVE `plan12-cp4` run seen at review time has gone.
- A read-only dry run of the reviewed manifest would archive 722 entries and refuse the 2 now-UNKNOWN entries (`changed_since_inventory:root_unknown`, exit 3). The registry was unchanged, and no `ended/` folder exists.

The release says a changed class stops execution, and the fresh manifest goes back to Codex. Receipts are in `codex-release-archival/` under the raw receipts folder.

## Task 1 — Classification and additive plugin (2026-10-04)

**Status: complete, uncommitted** (base `d562e95`; a commit waits for Codex's answer on Task 1–2 commits). Receipts: `optimus-handoff/test-profiles-research/plan-11-30-task1-evidence-20261004/`.

*Historical status at recording (committed with `1f8ca30`, 2026-10-05). Current (2026-10-09): Tasks 1–2 are committed in `1f8ca30`; see "Current delivery and status (2026-10-09)".*

### What was built

| File | Responsibility |
|---|---|
| `tests/profiles.toml` | The one manifest: 18 tier rules, 3 tag rules and a measured-slow snapshot (164 nodes) |
| `tools/testing/test_profiles.py` | Pure contract: `load_manifest`, `classify_nodes`, `profile_members`, `unexplained_slow_nodes`, and the two maintained signals |
| `tests/support/profiles_plugin.py` | `--profile`: after every other deselection, it deselects through `pytest_deselected` and prints one `test-profiles:` line |
| `tests/conftest.py` | Registers the plugin. The UNRUN count is now taken from the final items. |
| `tests/unit/tools/test_test_profiles.py` | 55 nodes: the pure contract, the plugin controls and the repository guards |
| `tests/unit/tools/run_context_child_sites.json` | One new `nested_pytest` launch site |

**Precedence.** The longest matching node rule decides. Otherwise the single matching path rule decides; otherwise the node is `core`.
- Two path rules claiming one file are a conflict.
- A rule that decides no node fails the full-universe guard.
- Static profiles: `full` (identity), `core`, `proc`, `audit`, `platform`, `concurrency`.
- `quick`, `commit` and `checkpoint` arrive with the Task 2 selector.
- The effective `-m` is never touched, so run-context ACTIVE/PASSIVE classification is unchanged.

### Classification of the default selection (5,329 nodes)

| Tier | Nodes | Source of the rules |
|---|---|---|
| core | 3,999 | Default, plus reviewed explicit rules for 7 measured-slow in-process tests and the cheap remainder of the audit family |
| proc | 835 | Run-context/process-tree files, child-launching tool files, subprocess-heavy nodes |
| gates | 325 | Current-source guards (S1 and Zed closures, logging manifest, walker allowlist, debug-trace, boundaries, credit surface, docs hygiene, UNRUN binding, this manifest's own guards) |
| audit-sealed | 90 | Pinned-commit or sealed-artifact replay |
| audit-current | 67 | Current-tree measurement or current-source reads |
| e2e-local | 12 | Unmarked `tests/e2e/**` |

Tags: `platform` 1,488 nodes (28 signal files), `concurrency` 381 nodes (9 signal files plus 4 reviewed product-race files).

**Source of the audit/gates split.** A per-node survey of the audit family (357 nodes) and the proc candidates (504 nodes), plus a repository-wide search for current-source guards (278 nodes in 50 files). Each row carries file:line evidence. The survey was parsed mechanically: 0 node-count or target mismatches against the real collection. Its 16 ambiguities were ruled in the ledger: the proposed tier stands in each case, and A11 (unrun-binding guards) is `gates`.

### Controls (test-first)

- **Pure contract.** RED (module missing), then 37 passed. 5/5 classifier mutants were killed: prefix boundary, shortest-wins, no conflict check, shadowed rule counted, audit as one tier.
- **Plugin controls.** 9 RED (no option, no manifest, no final-items UNRUN), then GREEN. They cover:
  - no-profile output byte-identical with the plugin blocked (MAIN-5 argument shape);
  - honest deselected counts;
  - composition with `-k` and explicit targets;
  - single-file sessions;
  - unknown or change-selected profile names as usage errors;
  - unchanged ACTIVE/PASSIVE classification (active default, `-m` passive, requested passive);
  - UNRUN counted from the final items.
- **Repository guards** (whole default selection):
  - no dead rule;
  - every measured-slow node has an explicit rule;
  - run-context/process-tree files are `proc` except current-source gate nodes;
  - `tests/e2e/**` is `e2e-local`;
  - concurrency and platform tags follow their maintained signals;
  - every child-launching file with `core` nodes has a written review (17 files);
  - v4's named current-source guards are `gates` or `audit-current`.
- **9/9 manifest mutants killed.** The first pass found a real defect: the manifest generator kept the measured-seconds column, so every snapshot entry matched no node, and the duration guard was vacuous. The guard now requires every snapshot entry to be a collected node ID (RED 164, then GREEN after the generator fix).

### Verification

| Check | Platform | Result |
|---|---|---|
| Task 1 gate command + cross-cutting guards, `TMPDIR` set / unset | Windows | 629 passed, 2 skipped in each |
| Same, `TMPDIR=/tmp` / unset (native clone at `d562e95` + Task 1 diff) | WSL | 580 passed, 51 skipped in each |
| Changed files Windows vs WSL | both | 6/6 byte-identical, no CR bytes |
| No-profile collection, plugin vs plugin blocked | Windows | identical (5,329/5,440, 111 deselected by `-m`) |
| Default collection vs the pre-Task-1 baseline | Windows | +55 nodes, all in `test_test_profiles.py`; nothing removed |
| Each static profile through the plugin vs the classifier | Windows | identical for full, core, proc, audit, platform and concurrency |
| `ruff check .`, `git diff HEAD --check`, local secret scan of changed files | Windows | clean, clean, 0 findings |

The real registry listing changed during the Windows runs only through another lane's runs (`mut-t4b`); no run of this lane remained.

### Residuals and limits

- **The selection record is deferred to Task 2**, because it carries the base/head/index/diff. In Task 1 a profile's deselection is visible in run-context's node stream, pytest's deselected count and the `test-profiles:` line.
- **The measured-slow snapshot comes from the 2026-10-02 reference run.** Tests added since then are unmeasured until Task 6 refreshes the snapshot. Stale snapshot entries fail the guard.
- **Tags and launcher reviews are file-level.** The `platform` tag selects every node of a file that reads the platform.
- **The tier survey is a reviewed snapshot.** New tests default to `core` unless a maintained-signal, launcher, slow-node or named-guard check catches them. A new current-source guard outside the named categories is caught only by review.

## Task 2 — Per-commit selector, bounded broad fallback and supported-load checkpoint runner (2026-10-04)

**Status: complete, uncommitted.** Base `d562e95`; Task 1 lies beneath it. Receipts: `optimus-handoff/test-profiles-research/plan-11-30-task2-evidence-20261004/`.

*Historical status at recording (committed with `1f8ca30`, 2026-10-05). Current (2026-10-09): Tasks 1–2 are committed in `1f8ca30`; see "Current delivery and status (2026-10-09)".*

### What was built

| File | Responsibility |
|---|---|
| `tools/testing/test_profiles.py` | Adds the pure selector: `parse_name_status`, `build_dependency_map`, `select_tests`, plus the `[selection]` and `[[inputs]]` manifest sections |
| `tools/testing/run_profile.py` | `python -m tools.testing.run_profile --profile commit\|checkpoint\|quick [--base SHA] [--exact] [--dry-run]`: Git change views, selection record, supervised subruns, Windows load-overlap repeats, evidence manifest |
| `tests/profiles.toml` | Broad paths, docs gates and three declared inputs (sealed Plan 11.26 data → audit-sealed; `tools/testing/**`, the process tree and `tests/support/child_*` → run-context proc tests; `src/optimus/**` → the e2e tests' dynamic launch of the ACP server) |
| `tests/unit/tools/test_test_profile_selection.py`, `tests/unit/tools/test_run_profile.py` | Selector controls over a synthetic repository; runner controls with temporary Git repositories and real nested sessions |

### Selection contract (as built)

- **Views.**
  - `commit` is the index against HEAD. Unstaged divergence is selected and hashed as provisional.
  - `checkpoint` is the recorded base against the working tree, plus untracked files. Everything not yet committed is provisional.
  - `--exact` refuses any provisional divergence.
  - An empty index is `no-commit-input` and runs nothing; it is never a pass.
  - Git is read with the caller's environment, so inside a hook the selection follows the hook's `GIT_INDEX_FILE`.
- **Dependencies.**
  - Import edges are keyed by module name. They cover packages, relative imports and string imports, including `-m` launches.
  - A deleted or renamed module still finds its importers by its old name.
  - Data references (a tracked file, or a folder without Python code) propagate through importers. Only the changed path's own readers count; the importers of those readers then carry the change further.
  - Naming a folder of code (`ROOT / "src"`, `"tests/unit"`) scans or runs it. The reading test is selected, but it never makes a change count as mapped.
  - A change is mapped only when it reaches a test.
- **Fallback.**
  - Broad paths (configuration, conftest files, `tests/support/**`, the manifest), unmapped non-prose paths and an unavailable old view select all `core`, all `gates` and native platform tests.
  - Expensive domains are included only through declared inputs or real dependencies.
  - `fallback:broad` reasons and every expensive domain's included/omitted reason are recorded.
- **Prose.**
  - `docs/**` other than machine-readable data, root `*.md` and `reports/**/*.md` select the docs gates and the readers of the changed file.
  - Prose never falls back.
  - Every non-prose change selects all gates.
- **R5.** Current audits stay out of commits until audit optimization G is accepted. Checkpoints run all of them at full depth.
- **Platform.**
  - Triggers:
    - a source that reads the platform or imports `ctypes`, `msvcrt`, `winreg`, `keyring` or `_winapi`;
    - production code that imports `subprocess`;
    - a declared platform path;
    - the broad path.
  - A trigger adds platform-tagged `core` and `gates` nodes.
  - A commit records a WSL obligation, which the next checkpoint's own whole-diff selection on WSL discharges.
- **Checkpoint load (Windows only).**
  1. The full-depth current-audit subrun runs as load.
  2. The selected concurrency nodes run as three separately attributable repeats.
  3. A repeat starts only after the load has recorded its first test phase. It counts only if that same load run is still running when the repeat ends, and run-record times confirm it.
  4. The load workload is repeated only as needed.
  5. A failure stops the lane and is kept.
  6. Overlap that cannot be held is `stability-unrun` (exit 3), never a pass.
  7. Cleanup stops only this runner's own process trees.

  POSIX runs the selection, including its concurrency nodes, serially without load.
- **Selection record and evidence manifest.**
  - Node IDs appear only as digests plus run-context labels, because some carry credential-shaped test parameters.
  - Each document is refused if the shared sanitizer would change it.
  - Subrun console output is not kept: identity, mode and times come from each subrun's own run records.

### How the real repository shaped the rules (test-first refinements)

A mapping survey over all 1,218 tracked files led to five refinements, each RED → GREEN in the selector controls:
- Only whole `a / b / c` chains name paths.
- Whole-code-folder scanners never make a change mapped.
- A rename is mapped when either of its paths is.
- `docs/**` is prose except machine-readable data.
- Code-folder references select only test readers, and mapped means reaching a test.

A "reaches a conftest ⇒ broad" rule was tried and then removed (ruling in the ledger). 129 of 135 `src/optimus` modules sit in the root conftest's import closure, and v4 maps `tools/testing/**` explicitly. Conftest-imported code runs inside every selected session anyway.

### Controls and mutation

- **Selector:** 38 controls. Every dependency kind is planted: imports, package `__init__`, relative imports (single-dot and parent), string imports, `-m` launches, path joins, tool readers, declared inputs, rename, delete, prose, machine data, configuration, platform and the old view. Also covered: determinism, reasons, `no-commit-input`, and that no single change turns a commit into the full suite.
- **Runner:** 16 controls.
  - Temporary Git repositories: index-vs-HEAD only, earlier commits in the checkpoint view only, unstaged provisional hashing, `--exact`, untracked files, rename/delete/Unicode names, a missing base.
  - Real nested sessions: an ACTIVE recorded subrun, complete overlap, a kept failure, unobtainable overlap reported as `unrun`, an interrupt that stops only owned processes, a dry-run CLI selection record, and sanitizer refusals.
- **Mutation:** 14/14 mutants killed across the selector and the runner. One equivalent mutant was dropped with its boundary proof, after the missing relative-import control had been added.

### Defects found and fixed during the task

- **The runner hung on the first execution.** On Windows a venv's `python.exe` is a launcher, and the run record names its child. The runner now matches the root or root-parent PID, and load iterations are bounded.
  - Stopping my own stuck session leaked one real-registry entry, `20261004T165602-47672-d6a805`. Its worktree is present, so it was kept, not deleted.
- **In-loop counting overcounted repeats.** The loop now stops on covered repeats.
- **The selection record carried raw node IDs.** The sanitizer refused it; the record now uses digests.
- **Four cross-cutting guards caught real gaps**, all fixed:
  - 2 child sites;
  - 3 logging sinks, now classified with demonstrating tests;
  - test globs;
  - the platform tag and tier of `test_run_profile.py`.

### Verification

| Check | Platform | Result |
|---|---|---|
| Tasks 1–2 focused gate (both briefs' commands + cross-cutting guards), `TMPDIR` set | Windows | 684 passed, 2 skipped |
| Same, `TMPDIR` unset | Windows | 684 passed, 2 skipped |
| Same (native clone at `d562e95` + Tasks 1–2 diff), `TMPDIR=/tmp` / unset | WSL | 632 passed, 54 skipped in each |
| Changed files Windows vs WSL | both | 12/12 byte-identical, no CR bytes |

Checkpoint B's own `--profile checkpoint` runs on Windows and WSL follow in the Checkpoint B section.

## Checkpoint B — Tasks 0–2 cumulative checkpoint profile (2026-10-04)

**Status: attempt 3 passed on the final Tasks 1–2 source on both platforms; Fable 5.1 accepted (SOUND WITH AMENDMENTS, report-only, applied); awaiting Codex.** Nothing is committed: the Task 1–2 commits (coverage-hook skip only) need Fable then Codex to accept Checkpoint B on this tested source. Push, PR and merge stay held.

*Historical status at recording (committed with `1f8ca30`, 2026-10-05). Current (2026-10-09): Codex accepted Checkpoint B (recorded in `0a66609`), and Tasks 1–2 are committed in `1f8ca30`.*

Checkpoint B runs the change-selected `checkpoint` profile itself (`python -m tools.testing.run_profile --profile checkpoint --base a929aab2092876ab0d83ecc4e46896ae3a0935c0`) on native Windows and real WSL: the cumulative Tasks 0–2 selection from main, every current audit at full depth, the triggered platform lanes, Windows concurrency repeats overlapping the current audit and serial WSL concurrency without load. No full suite.

### Attempts (all sealed; failures and invalid runs retained)

| Attempt | Source | Windows | WSL | Receipts (seal) |
|---|---|---|---|---|
| 1 | Tasks 1–2 as first delivered | `win1` aborted by me (block-buffered console misread as lost); its orphaned subrun finished 4 failed / 4,992 passed: the two failures below plus two child-site tests whose real ancestor chain ended at the killed runner. `win2` cancelled before launch | **failed**: 2 failed / 4,949 passed / 86 skipped; audits 67 passed | `plan-11-30-checkpoint-b-attempt1-evidence-20261004` (`f2ffefcf…`) |
| 2 | after the fix pass below | **pass** (selected 5,028 passed / 40 skipped; audit load 67 passed; 3 counted repeats). Each record carries `parent=not_found:ancestor_exited`, which that runner did not yet label (round 2 adds it) | **invalid**: every test passed (4,982 / 86 skipped; audits 67) but the selected subrun's own record was INVALID | `plan-11-30-checkpoint-b-attempt2-evidence-20261004` (`e67c3ac2…`) |
| 3 | after the recorder clock fix | **pass** (exit 0) | **pass** (exit 0) | `plan-11-30-checkpoint-b-attempt3-evidence-20261004` (`e170d993…`) |

Correction to the sealed attempt-2 note (Fable M1): the WSL lane ended at 19:03:35.89Z, before the Windows overlap lane began (19:05:24.99Z); it overlapped only the Windows `selected` subrun, not the stability repeats.

Attempt-1 failures: the committed-plan docs gate (frozen v4 Tooling cell) and the provider-balance retirement guard (the Task 1 manifest and guard map spelled its retired token). The second was a real Task 1 defect that the Tasks 1–2 focused gates had missed because they did not run the whole `gates` tier; every later pre-checkpoint gate does.

### Reviews and the fix pass (test-first; one pass, then the recorder fix)

Fable 5.1 reviewed attempt 1 and returned **NOT SOUND** (three MAJOR). Codex independently recorded **B-M1**. Fable's re-review of that fix pass returned **NOT SOUND** again (R1 MAJOR: F2 only partly closed; R2–R4 MINOR), and all four were fixed before attempt 3. Fable then found R1–R4 and the recorder fix **SOUND** (with report corrections M1–M3), and its final check of attempt 3 and this section is **SOUND WITH AMENDMENTS** (C1–C3, report-only, applied): it recomputed both lanes from the raw run records, verified every seal, and accepts Checkpoint B on `d562e95` + `9d123df2…`. Every fix has a control that failed first; 19 + 6 + 10 + 2 + 2 mutants were killed (`cpb-fix/mutate_fixes.py`, `cpb-fix/mutate_docs.py`, `cpb3/mutate_round2.py`, the clock-site mutants, the two sanitizer demonstrations).

| Finding | Fix | Control |
|---|---|---|
| F1 (MAJOR) retirement token in `tests/` | the guard is classified by a gates path rule `tests/unit/test_*_surface_retirement.py`; the test-side name is assembled at runtime; the guard still runs as `gates` | the guard itself (failed in attempt 1) and the current-source guard map |
| F2 (MAJOR) prose omitted gates that scan the docs tree | a prose change also selects the **gates-tier** whole-folder readers of its folder | `test_prose_in_a_scanned_folder_selects_the_gates_that_scan_it_and_no_cost_tier_scanner` |
| F3 (MAJOR) a root-conftest change omitted the run-context controls | the root conftest and the profile plugin are inputs of the run-context lane | `test_a_session_hook_change_selects_the_run_context_controls` (both paths) |
| B-M1 (Codex) / F6 a pass without valid terminal or capability evidence | `record_validity` reads each finished subrun's own terminal record: terminal checkpoint and time, ACTIVE, no terminal failure, COMPLETE, recorded exit equal to the process exit, and on Windows a valid native job and an installed guard. POSIX unsupported labels, an UNKNOWN parent (with its reason) and reduced protection are kept as qualifications, never failures. A subrun never validated is `not_validated`. Failures stay failures | 13 refusal cases, 5 qualification cases, Codex's exit-0/ACTIVE/no-terminal-time probe, verdict-level controls, real supported-Windows and qualified-POSIX subruns |
| F5 overlap bounded by the load's session end | a repeat counts only inside the load's recorded test phases (first phase start to last recorded phase end); both records must support a pass, except a load this runner stopped | `test_a_repeat_counts_only_inside_its_load_s_recorded_test_phases` |
| F7 a start timeout escaped as a traceback (exit 1) | the run stops its own process trees and is `invalid` with the sanitized reason in the manifest | two controls, one with credential-shaped text |
| R1 (MAJOR, re-review) prose still omitted gates that scan the docs through a tool (`tools/doc_paths.py`) | for prose only, a scanning tool's importers are followed to tests (then gates-tier only); code changes keep direct scanners, as the earlier "a runner's own tests do not consume the folder it runs" ruling requires, and already run every gate | `test_prose_in_a_folder_a_tool_scans_selects_the_gates_that_use_the_tool`; on the real repository a new `docs/new-topic.md` now selects `test_document_names_under_docs_are_unique` |
| R2 a stall after repeats dropped what ran | the overlap lane catches a start timeout, stops its own load, keeps every load and repeat, and is `invalid` with the sanitized reason | a real-process stall after `repeat-1`; a sanitizer demonstration (new classified sink `run_profile:overlap:exception_export`) |
| R3 weaker labels dropped | `parent=not_found[:reason]`, `processes=QUERY_FAILED` and `members=incomplete` are kept as qualifications, as the run's own summary line shows them | three qualification cases |
| R4 `unrun` hid a load's record problem | record problems are named before `unrun`; any other overlap verdict is `invalid` (an `invalid` outcome previously fell through to `pass` in the control before the fix) | three verdict-mapping cases |
| F8 snapshot provenance | the reference run is stated as exit 1 / INVALID diagnostic data | — |
| Docs gate (Codex-authorized) | a hash-pinned exception for exactly v4's Tooling disposition cell of exactly the approved raw bytes; every other check stays | approved snapshot passes only with it; same bytes under another name, altered bytes, another row with the same text and a broken status/owner all fail; 6/6 mutants |

**Attempt-2 WSL invalid, root cause and fix.** `tests/unit/tools/test_probe_p11_zed_session_load.py`'s two-lifecycle tests patch the global `time.monotonic` (through the probe module's `time`) to 100–1,100. The enclosing session's run-context recorder read that clock while their call phase was reported. On a WSL VM booted minutes earlier (session start at monotonic ≈253 s) the patched 1,100 fired a sample at 846.74 s (gap 707.138 s, exactly the patched value minus the last real sample), pushed the next sample 707 s out, and made the terminal sample's gap negative, which the samples table refuses: one recording error, so the record was INVALID. Windows uptime is far above 1,100, so it never triggers there; attempt 1 ran on an older VM. B-M1 refused the pass, as intended. Fix: the recorder binds its clocks at import (`tools/testing/run_context.py`), so no test's patch reaches it. Control `test_a_test_that_patches_the_global_clock_cannot_move_the_session_s_sampling` reproduced the failure in-process (1 sample, 1 recording error) before the fix; both clock-site mutants are killed. The probe tests are unchanged.

**Pre-checkpoint focused gate on the final source (Windows):** 1,009 nodes (the whole gates tier, the Tasks 1–2 gate files, the docs file and the retirement guard): 1,007 passed, 2 skipped. The commit hooks (ast-grep through pre-commit's own environment, Ruff, TOML, trailing whitespace, config trust, Bandit), both secret scans and `git diff --check` pass over the working tree. The fix pass also classified one new logging sink (`run_profile:execute:exception_export`, shared sanitizer, with a demonstrating test).

### Attempt 3 (final source) — results

Source: HEAD `d562e95` plus the working diff `9d123df294f7…` (Windows) / the identical patch on a native WSL clone. Selection on both: **5145 selected, 281 deselected**, fallback `broad` (`.gitattributes`, `tests/conftest.py`, `tests/profiles.toml`, `tests/support/profiles_plugin.py`; `unmapped: reports/plan-11-30-test-profiles-manifest.json`), platform `triggered` (8 triggers), expensive domains: audit-current and audit-sealed included, proc included, e2e-local omitted (no dependency or declared input changed), audit depth `full`, 381 concurrency nodes.

| Platform | Subrun | Run ID | Nodes | pytest | Exit | Record | Qualifications |
|---|---|---|---|---|---|---|---|
| Windows | `selected` | `20261004T195132-15248-06ed9d` | 5078 | 5038 passed, 40 skipped, 1 warning in 1027.43s (0:17:07) | exit 0 | valid | parent=not_found:ancestor_exited |
| Windows | `load-1` | `20261004T200844-7248-98efd6` | 67 | 67 passed in 812.78s (0:13:32) | exit 0 | valid | parent=not_found:ancestor_exited |
| Windows | `repeat-1` | `20261004T200848-41940-2e9039` | 381 | 373 passed, 8 skipped in 61.16s (0:01:01) | exit 0 | valid | parent=not_found:ancestor_exited |
| Windows | `repeat-2` | `20261004T200953-52988-073933` | 381 | 373 passed, 8 skipped in 44.54s | exit 0 | valid | parent=not_found:ancestor_exited |
| Windows | `repeat-3` | `20261004T201042-35188-e01641` | 381 | 373 passed, 8 skipped in 44.49s | exit 0 | valid | parent=not_found:ancestor_exited |
| WSL | `selected` | `20261004T195200-522-b5f07d` | 5078 | 4988 passed, 90 skipped, 1 warning in 228.70s (0:03:48) | exit 0 | valid | native=unsupported, guard=unsupported_platform, parent=unsupported |
| WSL | `audit-current` | `20261004T195606-4381-099015` | 67 | 67 passed in 555.02s (0:09:15) | exit 0 | valid | native=unsupported, guard=unsupported_platform, parent=unsupported |

- **Windows verdict:** **pass** (exit 0). Stability: **complete**: 3 repeats each inside one load run's recorded test phases; load run `20261004T200844-7248-98efd6`; counted repeats `20261004T200848-41940-2e9039`, `20261004T200953-52988-073933`, `20261004T201042-35188-e01641`.
- **WSL verdict:** **pass** (exit 0). Stability: none (POSIX runs the selection, its concurrency nodes included, serially without load).

Windows overlap (UTC; a repeat counts only inside its load's recorded test phases):

| Subrun | Run ID | Started | First phase | Last phase end | Finished | Counted inside |
|---|---|---|---|---|---|---|
| `load-1` | `20261004T200844-7248-98efd6` | 2026-10-04T20:08:44.278259+00:00 | 2026-10-04T20:08:45.396193+00:00 | 2026-10-04T20:22:17.023296+00:00 | 2026-10-04T20:22:17.277579+00:00 | — |
| `repeat-1` | `20261004T200848-41940-2e9039` | 2026-10-04T20:08:48.254385+00:00 | 2026-10-04T20:08:51.693219+00:00 | 2026-10-04T20:09:32.708857+00:00 | 2026-10-04T20:09:32.980502+00:00 | 20261004T200844-7248-98efd6 |
| `repeat-2` | `20261004T200953-52988-073933` | 2026-10-04T20:09:53.888485+00:00 | 2026-10-04T20:09:57.451751+00:00 | 2026-10-04T20:10:38.388195+00:00 | 2026-10-04T20:10:38.678429+00:00 | 20261004T200844-7248-98efd6 |
| `repeat-3` | `20261004T201042-35188-e01641` | 2026-10-04T20:10:42.655635+00:00 | 2026-10-04T20:10:45.889000+00:00 | 2026-10-04T20:11:27.108869+00:00 | 2026-10-04T20:11:27.403396+00:00 | 20261004T200844-7248-98efd6 |

The WSL lane ran 19:52:00–20:06:08Z and overlapped these Windows subruns: `selected`. Other lanes' runs may also have been active. No timing claim is made from these runs.

**Receipts after the final edit of this section** (Fable C3): the docs gate and detect-secrets were re-run on the final report and manifest; their outputs and run record are sealed in `plan-11-30-checkpoint-b-report-receipts-20261004`, named in the Codex packet.

### Registry archival (Codex option A, executed 2026-10-04 ~18:15 UTC)

Against the original reviewed manifest (class `28bc1799…`, 724 eligible): the fresh dry run was 723 `would_archive` and 1 `changed_since_inventory:root_unknown`; execution archived 723 and refused the same member (exit 3); `verify` exited 4 with 3 problems, all on that refused member, which is still in place, byte-unchanged, with no copy and no receipt. **PARTIAL, NON-PASSING**: 723 archived with per-member proof; the original manifest remains incompletely reconciled. Receipts: `plan-11-30-archival-evidence-20261004` (`6a4bec8d…`).

### Residuals and deferred items

- **Abrupt runner kill** (Fable F4, deferred): `tools.process_tree` jobs carry no kill-on-close, so killing the runner process itself orphans its subruns (as `win1` showed). Interrupts, failures, start timeouts and normal ends stop every owned tree.
- **Hook context** (F9, deferred to Task 3): no control yet runs the runner inside a real hook with `GIT_INDEX_FILE`; Task 3 wires the hook and adds it.
- **Two cheap AST audits stay `audit-current`** (A4): tiered by audit family; checkpoints run them; `gates` would fit equally.
- **Selection limits** (Task 2 rulings): a fixture used only by name through conftest-wrapped product code is not followed; `Path(__file__).parent / "fixtures"` readers and `reports/*.json` take the bounded broad path; `no-commit-input` exits 0 with that label, never `pass`. The final full runs remain the backstop.
- **Subrun console output** is kept only because the checkpoint scripts redirect the runner's console; their digests are in the attempt receipts.
- **Recorder clock**: fixed at the recorder; other code that reads a patchable clock during a test is not audited here.
- **WSL wall-clock timestamps** (Fable C2): in attempt 3 the WSL guest wall clock advanced about 47 s (audits) and 15 s (selected) more than monotonic time (VM time re-sync: wall spans 602.0 s and 243.8 s against 554.8 s and 228.5 s monotonic, pytest 555.02 s and 228.70 s; inter-phase wall gaps up to 24.3 s, Windows at most 0.044 s). WSL `started_utc`/`finished_utc`/phase `at` values are therefore accurate only to about a minute. No claim here depends on them: WSL runs serially without load, counts and outcomes are unaffected, and the lane-overlap statement survives a one-minute error. Gap arithmetic on WSL records needs this caveat.
- **Scans seen through path joins only** (Fable M3): a gate that scans the docs solely through a loose pathspec string (for example `tracked_repository_files(..., pathspecs=["docs"])`) would be invisible to the prose scanner rule. None exists outside `tests/unit/docs/**` today, and `tools/doc_paths.py` joins `REPO_ROOT / "docs"`, so it is reached.

*Annotation (2026-10-09): F9 was closed by Task 3's real temporary-index hook control (`1b300cf`). The Task 5 worker kill-on-close and attribution obligation is discharged for the accepted native Windows controller topology (Stage B Task 5 section, "Checkpoint B worker obligation"); WSL keeps its weaker label. F4, the abrupt runner kill, is not discharged.*

## Task 3 — Product coverage gates and commit-hook wiring (2026-10-04)

**Status: complete, uncommitted (base `1f8ca30`); corrected for Codex's bounded hold T3-M1; Fable 5.1 SOUND WITH AMENDMENTS on the build, the final evidence and the T3-M1 disposition (all applied); awaiting Codex.** Final Task 3 diff `4373b171f4f7…` (14 files). Coverage floors on real full-run data, the safety-row baseline and remote CI evidence belong to Stage A's Task 6.

*Historical status at recording (committed with `1b300cf`, 2026-10-05). Current (2026-10-09): Codex accepted Task 3 with T3-M1 resolved and verified its local delivery at `1b300cf`.*

### What was built

| File | Responsibility |
|---|---|
| `tools/testing/coverage_products.py` | Classifies every tracked production package under `src/` into exactly one product (unknown or doubly claimed fails closed); measures each product unrounded with coverage.py's formula and gates Optimus (aggregate), model policy (own floor) and Context Engine at 80 when present, A2A reported only; binds the report to one full default-selection run of this source; compares the seven safety-critical module rows between a base and a candidate report |
| `.pre-commit-config.yaml` | The `optimus-check: pytest-coverage` hook keeps its id and label and now runs `python -m tools.testing.run_profile --profile commit`, coverage-free, `always_run` |
| `.github/workflows/guardrails.yml` | Same check label and default full invocation; coverage widened to bare `--cov --cov-branch --cov-fail-under=0` with a JSON report, then the product gate. CI selects no profile and changes no run-record activation |
| `CONTRIBUTING.md`, `AGENTS.md` | The full coverage and product-gate commands; the commit hook is coverage-free |
| `tests/profiles.toml` (T3-M1) | Explicit rules for every node measured over 2 s on the Task 3 source, and the `[measurement]` snapshot united with those runs |
| `tests/unit/acp/test_main_wiring.py` (T3-M1) | A host-starter tripwire for the module, and the one test that reached the real `ensure_local_redis` helper now stubs it |

### Coverage contract (as built)

- **Packages.** Importable top-level directories of tracked Python files under `src/`; distribution metadata (`*.egg-info`) is never a package. Optimus = `optimus`, `optimus_gateway`, `optimus_security`, `optimus_model_policy`; Context Engine = `context_engine`; A2A = `evidence_handoff`, `evidence_handoff_runtime`. Absent future packages are N/A on this source; when one appears its floor applies. A gates control keeps `[tool.coverage.run] source` equal to the discovered packages.
- **Measurement.** (covered lines + covered branches) / (statements + branches), unrounded, `>= 80`: exactly 80 passes, 79.99 (displayed as 80 %) fails. A present enforced product with nothing to measure fails.
- **Complete, current data.** Every current source file needs a row; a row for a file not in the source fails; each row's statement and branch counts must equal coverage.py's own analysis of the current file under the repository's exclusions (a real coverage.py run proves the parity); line-only data fails.
- **Full-run binding.** The run-context terminal record must support a result (`run_profile.record_validity`, exit 0), be the default selection with no collection errors, have selected exactly the default universe collected from this source now (count and node-digest set), name this HEAD, `pyproject.toml` and `uv.lock`, and contain the report's write time (local-naive coverage timestamps are converted with the host zone; up to 5 minutes after the terminal record). The source, tests and configuration must be clean, and none of their tracked files may have been rewritten after the run started (a dirty run followed by `git stash`/`checkout` is refused — Fable T1). Without `--run-record`, the record is the one largest default-selection run containing the write time; a tie is no answer.
- **Safety rows.** Base against candidate for the seven named `optimus` modules: missing rows, different coverage versions or line-only data are refused; any increase in missing lines or branches, or a lower unrounded percentage, is a regression. The output names both reports' SHA-256 (Fable T2); platform, interpreter and the base main-push SHA remain custody of the evidence that names the CI runs.

### Controls and mutation

- `test_coverage_products.py`: 37 collected controls from 26 test functions (classification, floors and boundary, model policy, Context Engine, A2A, empty product, rows and drift, real coverage.py parity, every binding clause, the post-start rewrite end to end, run lookup, safety rows and their file digests, sanitized output).
- `test_ci_parity.py`: the hook entry, label, `always_run` and coverage-free state; the CI step's exact commands and the absence of any profile selection.
- `test_run_profile.py`: a real temporary-index control — `git commit -- a.py` with `b.py` staged only in the real index runs a pre-commit hook on git's temporary index (`GIT_INDEX_FILE`); the runner's commit view stages `a.py`, holds `b.py` as provisional, and the hook's refusal leaves no commit (this closes Checkpoint B's F9).
- Mutation (per the ledger; the harness's output was not retained): 29 of 29 Task 3 mutants in `task3/mutate_task3.py` killed, plus the two review-amendment mutants, which were run outside that script. That missing output is not recoverable proof.
- T3-M1 mutation (harness output retained, `task3m1/mutate_t3m1.py` → `mutation4/`): 8 of 8 killed, each by its intended assertion. Five drop one new rule entry (the slow-node guard names the node), one removes the test's `ensure_local_redis` stub (the tripwire), and two weaken the tripwire (its control).
- Declarations the guards required once the new files were tracked: one coverage.py child site (census), four logging sinks (shared sanitizer, each with a demonstrating test), the run-record glob as a reviewed non-repository walker, the cheap-launcher review, five new current-source guards tiered `gates`.

### Verification

| Check | Platform | Result |
|---|---|---|
| Focused gate on the final source: the brief's command, the whole `gates` tier, the Tasks 1–2 gate files, docs, retirement and naming guards, and the three T3-M1 modules | Windows | 1,140 passed, 2 skipped (run 20261005T024356-34788-3864a3; records COMPLETE, native valid, guard pytest_process_guard, protection full; 0 default-tier nodes over 2 s) |
| Brief command + cross-cutting guards + the three T3-M1 modules, native clone at `1f8ca30` + the final diff, `TMPDIR=/tmp` | WSL | 648 passed, 24 skipped (0 default-tier nodes over 2 s) |
| Same, `TMPDIR` unset | WSL | 648 passed, 24 skipped (0 default-tier nodes over 2 s) |
| ast-grep (pre-commit's environment), Ruff, detect-secrets, the local secret scan, `git diff --check` | Windows | clean |
| The same focused gate on the pre-T3-M1 13-file diff `913926d1…` (historical) | Windows / WSL | 1,048 passed, 2 skipped / 555 passed, 24 skipped in both `TMPDIR` states |

**The actual commit hook, exercised without a commit.** In a fresh disposable Windows clone (`1f8ca30` + the final Task 3 diff, all 14 files byte-identical to the lane), the whole change was staged in the clone's own index, and `GIT_INDEX_FILE` was set to `.git/index` — exactly what git sets for a normal `git commit`, as a scratch-repository probe confirmed. `pre-commit run optimus-pytest-coverage` then ran the real hook (exercise 5).

Earlier exercises are retained, each as evidence for its own source only:

- **Exercise 3** (the 13-file diff `913926d1…`, same setup): pass, 5,107 selected, 5,067 passed, 40 skipped, record valid.
- **Exercise 4** (the T3-M1 candidate before Fable's two wording amendments, `fa49dce6…`): pass, 5,105 selected, 5,065 passed, 40 skipped, record valid; 133 nodes over 2 s, none with a default tier.

Exercises 1 and 2 refused; both refusals came from a setup that did not match a real commit:

- **Exercise 1** (before the review amendments) staged only `.pre-commit-config.yaml` and `CONTRIBUTING.md` from an index that also held the two new files as intent-to-add entries. pre-commit stashed the unstaged declarations those files need, so three repository-scanner tests reported them undeclared (4,472 passed, 3 failed, 37 skipped; hook exit 1, no commit).
- **Exercise 2** (the 13-file source) staged all 13 files into a separate index file named by `GIT_INDEX_FILE`, leaving the clone's default index at HEAD. The test session strips `GIT_*`, so the same three scanners listed the default index, could not see the new files, and reported their declarations as stale (5,064 passed, 3 failed, 40 skipped; hook exit 1, no commit).
- The probe shows a normal commit's hook index *is* the default index, so neither split arises from a commit with everything staged, which is how Task 3 will be committed. Partial commits do diverge (residual below).

- Selection: view `commit`, 5105 selected / 362 deselected, changes .github/workflows/guardrails.yml, .pre-commit-config.yaml, AGENTS.md, CONTRIBUTING.md, docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json, tests/profiles.toml, tests/unit/acp/test_main_wiring.py, tests/unit/guardrails/test_ci_parity.py, tests/unit/guardrails/test_tracked_file_scanners.py, tests/unit/tools/run_context_child_sites.json, tests/unit/tools/test_coverage_products.py, tests/unit/tools/test_run_profile.py, tests/unit/tools/test_test_profiles.py, tools/testing/coverage_products.py, provisional 0, fallback `broad: .github/workflows/guardrails.yml; broad: .pre-commit-config.yaml; broad: tests/profiles.toml`, obligations `wsl-platform: next checkpoint`.
- Verdict: **pass** (exit 0).
- Tests: selected subrun 20261005T022750-56116-11591b: 5105 nodes, 5065 passed, 40 skipped, 0 failed (per-node outcome from the run record's phases.jsonl; pre-commit hides a passing hook's output); hook exit 0.

| Subrun | Run ID | Nodes | Exit | Record | Qualifications |
|---|---|---|---|---|---|
| `selected` | `20261005T022750-56116-11591b` | 5105 | exit 0 | valid | parent=not_found:ancestor_exited |

HEAD before=1f8ca301c435377bdd29f7e5c54159ebb06d0c1c after=1f8ca301c435377bdd29f7e5c54159ebb06d0c1c (no commit created)

### T3-M1: explicit rules for measured slow nodes (Codex's bounded hold)

v4 allows a default `core` tier only for cheap nodes: measured setup+call+teardown over 2 seconds requires an explicit rule. The guard checked only the old reference snapshot, so four nodes measured over 2 s in exercise 3 still had a default tier (Codex T3-M1).

- **Census.** Every retained run of the 13-file Task 3 source was checked, not only exercise 3:
  - Windows exercises 3 and 2 (5,107 nodes each) and the focused gate (1,050);
  - WSL's two final runs (579 each).

  Six nodes over 2 s had a default tier. Exercise 1 (pre-amendment source) and two earlier lane runs add nothing.
- **Root causes.**
  - The conftest-parametrised selector control's 19–27 s was setup: the module's shared collection of the whole default universe (a nested `pytest --collect-only`), billed to whichever node requests it first.
  - `test_main_wiring.py::test_gateway_child_construction_ignores_os_environ_mutated_after_capture` did not stub `ensure_local_redis`, unlike the other tests in the original 69-test module. So `main()` reached the real `ensure_local_redis` helper, whose conditional implementation can probe Docker and attempt a container start or create, then poll for readiness; it fails open, so the test still passed. The tripwire and the timings support that reach: 22.8 s with about 1 s of CPU while local Redis was down, and 0.28 s once it was up. The runs kept no per-command subprocess trace. The `optimus-redis` container's recorded start (2026-10-04T22:01:11Z) postdates both slow reaches and is not attributable to them.
- **Rules** (the reasons are the cost contract, not duration alone):

  | Node | Before | After | Why |
  |---|---|---|---|
  | `test_test_profiles.py::test_a_session_hook_change_selects_the_run_context_controls` (both parameters) | core | gates | It holds the manifest against the current collected universe, like every other user of that shared collection (the manifest's own guards) |
  | `test_run_p11_fu_10_acpx_error_code_evidence.py::test_acpx_timeout_kills_every_descendant` (both parameters) | core | proc | It kills a real process tree on a 5 s timeout, like the capture-timeout probe |
  | `test_server_reader_ownership.py::test_seam4_b2_teardown_completes_in_a_child_while_the_parent_holds_stdin_open` | core | proc | It spawns and times a teardown child |
  | `test_coverage_products.py::test_a_real_repository_s_current_full_run_data_is_evaluated_end_to_end` | core | proc | It runs Git children in a per-test repository |
  | `test_main_wiring.py::test_gateway_child_construction_ignores_os_environ_mutated_after_capture` | core | core (explicit) | It is in-process once stubbed; the rule records the root cause |

- **The wiring fix.** A module-level tripwire replaces `ensure_local_redis`, `ensure_local_phoenix` and `ensure_local_gateway` with recorders and fails any test that reaches one, at teardown, even when `main()` swallows the error. Exactly one test reached one, and it now stubs it like its siblings. A control pins the tripwire to every `ensure_local_*` name `main()` imports. This is the one file outside the plan's file map; a tier would have misdescribed a unit test that runs Docker on the host.
- **Selection changes,** all deliberate:
  - The selector control now runs on every code or data commit, with the other manifest guards that already pay for the shared collection.
  - The four `proc` nodes leave broad fallback and the quick profile. They are still selected when their own tool, product or test changes (verified by simulation), and full and CI runs are unchanged.
  - No tags changed.
- **Measurement input.** `[measurement]` now lists the reference snapshot united with every retained run above: 164 → 235 nodes. Its source text names those runs, including exercise 2's setup-attributable exit 1. Runs on the corrected candidate (exercises 4 and 5, these gates) are checked against the same rule and retained as evidence; they are not written back, since that would change the candidate again. The Task 6 final run's timings will likewise stay evidence (Codex C2). Exercises 4 and 5 found no node over 2 s with a default tier.
- **Review.** Fable 5.1's bounded disposition was SOUND WITH AMENDMENTS. It recomputed the census independently and verified the selection consequences by simulation. Its two wording amendments (exercise 2's exit status in the measurement source; the launcher-review notes for the two files whose launching nodes are now `proc`) are applied, which is why exercise 5 was run on the amended bytes.

### Residuals

- The product floors have not yet run on real full-run data: the first full Windows coverage run (and the full WSL run and actual CI) is Stage A's Task 6. If a product is below 80 then, CI fails by design.
- The CI wiring is in the workflow file but has not run remotely: push and PR stay held, so CI-backed claims remain pending, not complete.
- The safety-row comparison needs the base SHA's retained main-push Linux CI report and the candidate's CI report (Task 6).
- Child-subprocess execution coverage remains the stated limitation. The post-start rewrite check relies on file modification times on the same host.
- A Windows commit runs native platform tests and records the WSL obligation for the next checkpoint (unchanged from Task 2).
- Inside a hook run, tests strip `GIT_*`, so repository scanners read the worktree's default index rather than a partial commit's temporary index. pre-commit aligns the working tree's file contents with the commit, but those scanners take their file list from the default index. For a partial commit (`git commit -- <paths>`) that list can differ from the commit's. A file staged outside the commit is scanned and can make the hook refuse. A file whose deletion is staged outside the commit is not listed although the commit keeps it (the probe demonstrates this file-list divergence), so a commit that removes that file's declaration could pass. This is the test session's existing `GIT_*` isolation, unchanged by Task 3. A commit with everything staged is unaffected. `commit -a` after a plain `rm` of a tracked file also diverges, but in the refusing direction: the default index still lists the file, which is missing, and the inventory fails closed. CI's full run on the pushed tree remains the backstop. Graded LOW by Fable and Codex. It is required Stage B work under `P11-FEAT-TEST-PROFILES`: a failing real partial-commit scanner control and the narrowest reviewed fix, before Plan 11.30 closes. The end-to-end false pass is reasoned, not reproduced.
- Test timings measured by the Task 6 final runs are retained as evidence and never written back into the measured candidate. A later snapshot refresh belongs to Stage B, under the same owner. Any newly demonstrated slow node with a default tier needs a recorded disposition before Stage A sign-off.

*Historical at recording (committed with `1b300cf`, 2026-10-05). Reconciliation (2026-10-09): the partial-commit source correction was delivered at `66ddabf` (Stage B Task 5), and the measurement snapshot refresh (b0) at `43eb190` (Stage B Task 4). No source work from these residuals remains required; the final full gate and the CI backstop remain open.*

## Task 6 — Stage A final gates at `acc2a1c` (2026-10-05)

**Status: accepted. Stage A's local Task 6 gates pass on Windows and WSL. Codex verified them independently and finalized local acceptance, with the operator-approved Windows checkout exception below. Fable 5.1: SOUND WITH AMENDMENTS.** Every result in this section was measured at `acc2a1c`. A later documentation commit records them; it is not itself measured.

### What was measured

- **Pin.** `acc2a1cadb435352f0e26ece58ffb4faba92cf3c` (tree `64266896…`): Task 3 `1b300cf` plus Codex's pre-pin documentation commit, after its current-state audit. `pyproject.toml` `9fee0c4c…`, `uv.lock` `f1caae18…`. Clean tree before and after both runs.
- **Commands** (the operator-authorized substitution for v4's unsupported `run_profile --profile full`; frozen v4 unchanged), run serially with one coverage writer per checkout:
  - `uv run --no-sync pytest --cov --cov-branch --cov-fail-under=0 --cov-report=term-missing --cov-report=json:tmp/coverage/full.json -v`
  - `uv run --no-sync python -m tools.testing.coverage_products report --coverage-json tmp/coverage/full.json`
- **Windows:** the implementing lane at the pin; Python 3.14.4, uv 0.11.29; the environment matched the lock (`uv sync --frozen --dry-run`: no changes).
- **WSL:** a fresh clone at the pin with its own environment and data (`/root/p1130-t6-20261005T075438`); Python 3.14.6, uv 0.11.31, `TMPDIR` unset.

### Results

| | Windows | WSL |
|---|---|---|
| Full suite | exit 0; 5,427 passed, 40 skipped, 111 deselected (47 min 58 s) | exit 0; 5,293 passed, 174 skipped, 111 deselected (26 min 3 s) |
| Raw recount (`phases.jsonl`) | 5,419 call passes + 8 recorder-control nodes with setup and teardown only = 5,427; skips 21 at setup + 19 at call | 5,285 + 8 = 5,293; skips 165 + 9 |
| Run record | `20261005T075433-47356-fcfdf0`: active, default selection, 5,467 selected / 111 deselected, no collection or recording errors, COMPLETE, exit 0; native job valid, guard `pytest_process_guard`, protection full; qualification `parent=not_found:ancestor_exited` | `20261005T075522-438-1b3ada`: same selection and terminal result; qualifications native unsupported, guard `unsupported_platform`, parent unsupported (WSL's weaker labels) |
| Optimus (floor 80) | **87.8722 %**: 15,089/16,659 statements + 3,474/4,466 branches — pass | **87.2047 %**: 14,972/16,659 + 3,450/4,466 — pass |
| Model policy / Context Engine | absent on this source: N/A | N/A |
| A2A (informational) | 68.4165 % | 65.9629 % |
| Coverage data | 202 rows (every current source file), coverage 7.14.3 with branches, all seven safety-module rows; SHA-256 `0b1f7e12…` | 202 rows, seven safety rows; `d7c33c18…` |
| Report binding | automatic and explicit `--run-record` agree | automatic and explicit agree |
| Nodes over 2 s | 233, none with a default tier | 77, one with a default tier (below) |

Products are measured as (covered statements + covered branches) / (statements + branches), unrounded. The Windows and WSL Optimus figures differ in a way consistent with WSL's additional skips and platform-specific paths; skip counts alone do not prove that cause, and no cross-platform subtraction is made.

**Task 0's full-run confirmation (v4 §6, Windows):** **PASS**. Over 16,371 phase transitions (k = 1,637), the first-decile median gap is 0.372 ms and the last 0.395 ms: ratio 1.062, within 2. There are no negative gaps, and the gap sum is 18.3 s. WSL's ratio, 0.781, is informational only, because the guest's wall clock jumps.

### Qualifications

- **Run-record provenance.** Both run drivers first copied the product report's own collect-only session (same node count, no phases) as "the run". The corrected files name the active default-selection runs above. The product report's own binding was unaffected: automatic and explicit lookups agree on both platforms. The wrong copies are kept as harness-error history.
- **Coverage timestamps are host-local.** coverage.py writes a naive local time, and the binding converts it with the measuring host's zone. So the report must run on the host that measured. WSL's data read on the Windows host would fall 5.5 hours outside its run. Each report ran on its own host: Windows wrote at 08:42:29Z, WSL at 08:23:27Z, each inside its run.
- **One warning, pre-existing.** `'optimus.acp.__main__' found in sys.modules`, from `tests/unit/acp/test_entrypoint.py::test_module_entrypoint_exists`, on both platforms. It is unrelated to this plan.
- **Shared host.** Other lanes may have run during these tests. Timings are evidence only, with no solo-host claim, and they are not written back into the measured candidate.
- **One new slow node with a default tier.** `tests/unit/mcp/test_local_ipc.py::test_remote_consume_after_listener_stop_fails_quickly` took 2.002 s on WSL (call 2.0016 s) and 1.016 s on Windows. It is a designed bounded IPC-timeout wait, in-process. Codex's recorded disposition: an exception for this pin only. The explicit `core` rule ("designed bounded IPC-timeout wait; platform-dependent (1.0 s Windows, 2.0 s WSL)") and this observation's measurement refresh are the first required Stage B source change, under `P11-FEAT-TEST-PROFILES`. `acc2a1c` is not rewritten and no final suite is repeated.
- **Windows checkout.** v4 calls for an independent frozen acceptance checkout; the Windows run used the clean frozen implementing lane at the pin. The operator approved retaining it as a Stage A-only exception (2026-10-05 09:31:33 UTC, Codex chat `01a10617-9940-72c0-a5e2-e3f8c3241055`): "Yes approve windows run above". The exception rests on the unchanged pin and source identities, the report's clean-tree and post-start rewrite checks, and the independent WSL clone. No Windows rerun is required, frozen v4 is unchanged, and the exception does not extend to future runs. The command approval (C1) alone did not grant it.

### Still open

- Remote Linux CI and the base/candidate safety-row comparison: UNKNOWN until a publication grant and comparable CI reports.
- Stage B: Tasks 4–5, the explicit rule above, and the partial-commit scanner control and fix (LOW). All are required and owned by `P11-FEAT-TEST-PROFILES`.
- Push, PR, merge and cleanup: held.

*Historical status at recording (committed with `1c7be2d`, 2026-10-05), including the qualification above that calls the explicit `core` rule "the first required Stage B source change". Reconciliation (2026-10-09): that rule and the measurement refresh were delivered at `43eb190`; Tasks 4–5, the partial-commit correction and the quick commit-audit switch are delivered at `66ddabf`. Remote Linux CI, the safety-row comparison and Stage B Task 6 remain open; push, PR, merge and cleanup remain held.*

Evidence: `plan-11-30-task6-stage-a-final-evidence-20261005` (69 files, seal `38b9b8fa…`); the pin's documentation commit `plan-11-30-task6-docs-commit-20261005` (seal `6de9b0f9…`).

## Task 4 — Audit depth, export cache and measurement reuse (2026-10-05 to 2026-10-07)

**Status: accepted and locally committed.** Codex accepted Task 4, Checkpoint C and G on candidate C7c (2026-10-06 18:40:36 UTC). The first commit attempt FAILED in the hooks (an untracked new test was an unclassified child launch site). The bounded 19-path retry committed `43eb19078a07d06e2d91d0913674b24af3616730` (parent `1c7be2d`), and Codex verified that delivery (2026-10-06 21:17:42 UTC). Every result below is bound to the candidate it names. The hook runs of the delivery name the parent HEAD `1c7be2d`; they are not independent `43eb190` final or coverage evidence.

The Task 4 commit also carries Stage B's first change (b0): the explicit `core` rule for `tests/unit/mcp/test_local_ipc.py::test_remote_consume_after_listener_stop_fails_quickly` and the slow-node measurement refresh.

### What was built

| File | Responsibility |
|---|---|
| `tests/support/profiles_plugin.py` | `--audit-depth=full\|quick` (default `full`). The only budget is `AUDIT_BUDGETS = {"h5.shutdown_schedule": full 100 / quick 1}`; any other probe is refused. `audit_budget` fixture, the `audit-depth:` summary line (`REDUCED-DEPTH` when quick), and a per-session audit state kept as a stack (pushed at configure, popped at unconfigure) |
| `tools/testing/run_context.py`, `run_context_records.py` | Additive optional fields in the run's **terminal** record only: `audit_depth`, `audit_budgets`, `audit_reuse`. Never in the start payload, which is also the host-wide registry announcement that older validators read |
| `tools/testing/run_profile.py` | Passes `--audit-depth=full` to every subrun. `record_validity` refuses a terminal record whose `audit_depth` is missing or not `full` |
| `tests/conftest.py` | Hands the plugin's audit record to the recorder; clears the export and reuse caches at session start and finish (through `sys.modules`, without importing the audit package) |
| `tools/plan1126_runtime_audit/source.py` | Session export cache for `git archive` of a resolved commit: read-only, thread-local, bounded to each thread's most recent export, keyed by the effective export inputs (below). A failed export is never cached |
| `tools/plan1126_runtime_audit/measurement.py` | Measurement reuse: `measurement_identity`, `MeasurementReuse`, `session_measurement_reuse`, `clear_measurement_reuse`; the key binds installed dependency integrity |
| `tools/plan1126_runtime_audit/current_envelope.py` | Additive `measure_current(measure=…)`, defaulting to `run_fresh_measurement`; only test helpers pass another |
| `tests/unit/acp/test_plan1126_shutdown.py`, `test_plan1126_queue_policy.py`, `tests/unit/tools/plan1126_runtime_audit/test_current_measurement.py` | The H5 test takes its repeat count from `audit_budget`; the three helpers opt in to reuse |
| `tests/unit/tools/plan1126_runtime_audit/test_measurement_reuse.py` (new), `test_source.py` | Reuse controls; export-cache controls against real Git repositories |
| `tests/unit/tools/test_test_profiles.py`, `test_run_profile.py`, `test_coverage_products.py` | Budget table bound to both schemas' `repeats_per_family` constant; nested-session depth record and summary; unknown-depth usage error; depth refusals in `record_validity` and the coverage binding |
| `tests/profiles.toml` | b0 rule and `[measurement]` 235 → 251 nodes; audit-current path rule for the reuse test; plugin-controls rule extended |
| `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json` | One additive safe-by-construction entry, `measurement:measurement_identity:json_serialization` (480 → 481 keys); accepted by Codex as a bounded living-manifest classification |
| `tests/unit/tools/run_context_child_sites.json` | One `nested_pytest` entry for `test_measurement_reuse.py::test_the_terminal_record_names_every_reuse#1` (82 → 83 sites), added for the retry |

### Contract as built

**b0 (first Stage B change).** `[measurement]` was refreshed with the Stage A Task 6 full runs (Windows `20261005T075433-47356-fcfdf0`, 233 nodes over 2 s; WSL `20261005T075522-438-1b3ada`, 77): 235 → 251 nodes. The slow-node guard then failed on exactly the IPC node (RED, which is also the rule-removed mutant); the explicit `core` rule with Codex's reason made it GREEN. Tier and tags are unchanged, so selection is unchanged. Windows `test_test_profiles` + `test_local_ipc` 66 passed; WSL clone 66 passed with TMPDIR set and unset. Patch `8ab3e5cfc6b6…`.

**Depth and budgets** (Codex's shared-contract answers Q1–Q5, Plan 11.26 owner `P11-FEAT-ACP-RUNTIME-HARDENING`; Claude concurred with every qualification).
- H5: quick = 1 repeat per applicable close-path × terminal-cause family; full = 100; same node identity. Quick execution of the repeat-100-named node is labelled reduced depth and is never repeat-100 or accumulation evidence.
- H4 (1,000 seeds and the literal corpus), the S1 windows and every other probe run at their existing counts. Plan 11.26 code, schemas, records and CLI are unchanged.
- Checkpoint, final and coverage operations require full depth. Commits stayed full until G was accepted; the changed-input quick switch is a separate Task 5-stage change (below).

**Export cache key (as accepted on C7c).** Repository; resolved commit; path set; a digest of the export arguments, `git version` and `git config --list`; every attribute source by content (`info/attributes`, `git var GIT_ATTR_GLOBAL`, `GIT_ATTR_SYSTEM`, the raw bytes of every `.gitattributes` blob of the exported tree read with `git ls-tree -r -z` and `git cat-file --batch`); `attr.tree` / `GIT_ATTR_SOURCE` by the tree they resolve to; replace refs and their environment switches; repository and object-store redirection. Reuse is refused (key `None`) whenever an input cannot be established, whenever `export-subst` is in effect (its output follows the wall clock and HEAD decoration), and whenever a configured `filter` smudge/process driver meets a `filter=` attribute in effect. The real sealed commit keeps a reusable key on this host.

**Measurement reuse key.** The child's exact payload (measured source, bound identity text, specification, entry and options), depth, platform and interpreter, the inherited environment minus `PYTEST_CURRENT_TEST`, and verified installed dependency content for the specification plus the entry's requirement floor. A hit returns a deep copy, names the measuring test, executes no probe and mints no execution context; it is refused if the earlier binding's dependency files differ from the installed content. Failures are never stored. The store is thread-local and session-scoped. Production code and the CLI never reuse.

### Measurement before caching (Codex Q4)

Five rebuild/envelope/schema nodes, measured on `1c7be2d` + the working diff before any cache code (`stageb/task4/cache-measure/`): plain walls 112.1 / 75.7 / 21.1 / 21.0 / 22.3 s. Full-document jsonschema validation of the 30.8 MB sealed or successor payload took 12.7–13.8 s each, about 130 s of about 276 s across the five; `git archive` of the same commit about 0.96 s, seven times per `_verify_artifact`; the fresh identity probe about 1.55 s. Codex recomputed the Stage A audit-current baseline from raw phases as 936.741816 s for 67 nodes, of which H5 is 534.613345 s; the 409.5 s quick projection is an estimate, not a measured run.

The dominant cost, schema validation, lies outside both v4 cache keys; only identical (schema, payload) pairs could be memoized and successor payloads differ per test. Codex assigned it as optional, unscheduled custody (residuals).

**Cache effect, contended (C6 Windows formal full, which overlapped the WSL chain):** against Stage A, the successor node 100.87 → 77.41 s; three reuse nodes 25.55 → 19.38, 24.36 → 17.89 and 24.15 → 16.94 s; the CLI node 100.88 → 117.68 s (fresh CLI subprocesses cannot reuse, and each reader now pays about a dozen bounded Git calls for its key). Codex: no clean overall cache-saving claim is made.

### Controls and mutation

- Depth: 9 RED for the expected reasons, then GREEN (`test_test_profiles` + `test_run_profile` + `test_coverage_products` 158 passed). The unknown-depth control first passed for the wrong reason and was tightened to require the choices message.
- Export cache and reuse: every correction round was RED on the previous candidate and GREEN after (outputs in the Checkpoint C seals).
- Injected H5 faults at both depths: f1 (one cause family under-closes) is refused by the observation model inside the child; f2 (a planted persistent thread, a valid observation) fails the repeat-100 node's own leak assertion. Killed on Windows by the mutation harness and on WSL by injection into the clone, restored from HEAD each time (C6 and C7c).
- Mutation on the accepted candidate C7c: **52 of 53 killed** (`mutation11`, lane identity equal before and after). `e2` (export key without the repository) is a survivor: unkilled by design, not proven equivalent; the repository component stays as the backstop against inputs not enumerated. The full history is in the Checkpoint C section.

### Delivery

| Attempt | When (UTC) | Result | Receipts (seal) |
|---|---|---|---|
| 1 (18 paths) | hooks 2026-10-06 18:44:24Z–19:13:55Z | **FAILED, no commit.** Hygiene, Ruff, Bandit, ast-grep, config-trust and secret-scan passed; `pytest-coverage` failed. Commit profile manifest `20261006T184438-59604-3f56c9`, selected run `20261006T184508-34948-35da0c`: 1 failed, 5,169 passed, 40 skipped (Codex recount; COMPLETE/ACTIVE/native-valid, exit 1). The failure: `test_run_context_child_sites.py::test_every_default_launch_site_is_mapped_to_a_proof` named the new reuse test's nested pytest. The guard enumerates git-tracked files; the reuse test had been untracked in every earlier run, so the launch site first became visible when staged | `plan-11-30-task4-commit-attempt1-failed-20261007` (14 files, `86a233763a97…`) |
| 2 (19 paths: the 18 plus one sites entry identical to `test_test_profiles.py::_pytest#1`) | pre-retry checks: guard + proof + reuse 202 passed, gates 336 passed, Ruff and `git diff --check` clean; hooks 2026-10-06 19:25:45Z–19:52:10Z | **Committed `43eb190`.** All applicable hooks passed (YAML had no files). Commit profile `20261006T192556-46092-095959` verdict pass, obligation `wsl-platform: next checkpoint`. Selected run `20261006T192622-56960-ebe4f2`: 5,210 nodes, 5,170 passed, 40 skipped, exit 0, COMPLETE/ACTIVE/full depth/native valid, `parent=not_found:ancestor_exited`. Of the 5,170, 5,162 have passing call phases; the other 8 are the `test_run_context_lifecycle.py` recorder controls whose call phase is not recorded by design (same node set as the C7c checkpoint main run); the pytest summary confirms 5,170 passed. 18 committed blobs equal the C7c table; map `c31ee8c3…`; lane clean | `plan-11-30-task4-commit-43eb190-delivery-20261007` (27 files, `9fdae92adbf1…`) |

Codex's attempt-1 ruling (2026-10-06 19:18:34 UTC) recorded that its own Checkpoint C review also missed the index-visibility requirement, and set the **checkpoint visibility rule**: every candidate new file must be staged or intent-to-add before index-based inventories run, with HEAD, status and diff identities recorded.

## Checkpoint C — Stage B through Task 4 (2026-10-05 to 2026-10-06)

**Status: accepted on C7c** (Codex, 2026-10-06 18:40:36 UTC), after Fable 5.1's final C7c SOUND. Codex HELD C2 (C-M1, C-M2) and C6 (C-M3). Passing executions on those candidates are retained as passing history, not acceptance of the cache they ran. Frozen v4 is unchanged. All candidates share base `1c7be2da61263e6fa47092346f65218104388740` and the same 18 paths.

### Candidates

| Label | Working diff (`git diff --binary` SHA-256) | Reuse test SHA-256 | What changed | Disposition |
|---|---|---|---|---|
| pre-amendment formal source | `de18263dfc8e7d6580925c9d5bb3834f9bac85820160046485492196ecd13a27` | `47b6f2f622c8…` | first complete Task 4 | Windows and WSL formal parity runs only |
| Checkpoint C candidate C1 | `41ee2f9cd72e90f87ccbad61d0d654e3c1921489d5f9da96bf03436b67901f6f` | `a48ce88fe574…` | Fable first-pass amendments F1–F4 | checkpoint FAILED (below) |
| C2 | `9fc1385b6a9dddf09c082813b71dbc385a66a898ed3880f61c3e89f75199bd29` | `2d789300953a…` | digest-only control; Plan 9.96 entry | checkpoint passed; Codex HOLD: C-M1, C-M2 |
| C3 | `8e9c94ff4db29d9a5dee4c678f06abf6ba0d90fff9888289a6f37318b3d674e8` | `5dd7be7725fc…` | C-M1/C-M2 corrections | runs STOPPED for Fable's C3 amendments |
| C4 | clean diff `7b19f9280bd5ae2d2fbb9171f02d52932177a8e4dac969a5a60b5b2240cf60f8` | `5dd7be7725fc…` | `attr.tree`/`GIT_ATTR_SOURCE` by tree; undecodable output fails closed | patch `c05d6d7f…` and its backup are **INVALID** (taken while a mutant was applied); not used for any run |
| C5 | `9aef8a442de31a9ff3bed349c598ae5e380eb3f2eefa403302f3183f57cee4ff` | `6db052a67683…` | replace refs, mailmap, environment switches | superseded by C6 after Fable's C5 check |
| C6 | `c6fe012ea8bd4cfa1a678fec88967feab4a9af0650acb8d95f870c500d49bd32` | `6db052a67683…` | filter drivers, export-subst key, redirection | checkpoint passed; Codex HOLD: C-M3 |
| C7 | `bce944098c503c895e36bc62bb218dfa4fe8ae780d2deb5d56eb7ed8caaf4dfc` | `6db052a67683…` | export-subst in effect → never reuse | Fable: SOUND WITH AMENDMENTS (pre-validation) |
| C7b | `19a65daca87cf6eb3f722639405177e36c7f2d2bb83412507604cbfda5e5fd01` | `6db052a67683…` | raw-byte attribute detection; mailmap keying removed | Fable: SOUND WITH AMENDMENTS |
| **C7c** | **`0fc9024f86febcb59422200c5214e930f39751dbda0a44e13931c281fd63ac1f`** | **`6db052a6768363ad9bd05885a30960558bac6fe82301c062f6f13dc6e3a42026`** | byte-level `ls-tree`; `cat-file` parsed by header | Fable SOUND; **Codex ACCEPTED** |

### Findings and corrections

| Round | Finding | Disposition |
|---|---|---|
| Fable first pass (on the pre-amendment source) | SOUND WITH AMENDMENTS, five MINOR. F1: H9 was not reused across files. Claude's ledger cause (known-folder redirection) was wrong and is struck; the real cause was Claude's own control clearing the running session's store. F2: export key lacked `.git/info/attributes`. F3: mutant r12 (key without the payload) added. F4: plugin audit state became a stack. F5: no session token for worker threads (ruling) | F1–F4 fixed test-first in Checkpoint C candidate C1; F5 ruling accepted by Fable. Codex later qualified F5 to today's serial topology: Task 5 may not inherit a cross-session worker-cache guarantee without its own proof |
| Checkpoint C run 1 (Checkpoint C candidate C1) | FAILED on both platforms on one gates-tier guard: `test_verify_plan996_logging_surfaces.py::test_checked_in_manifest_covers_current_surface_inventory`, `UNCLASSIFIED_SINK tools.plan1126_runtime_audit.measurement:measurement_identity:json_serialization`. Claude's focused Task 4 runs had not included the gates tier | The failing guard was the RED; added a digest-only control and the Plan 9.96 entry; all 336 gates-tier nodes passed → C2 |
| Codex C-M1 (major, on C2) | The export key hashed config text (including a `core.attributesFile` path) but not the global attribute file's content; Codex reproduced a stale export on Windows and WSL | Fixed in C3 (content of every attribute source), widened by Claude's own audit to replace refs (a real stale export: cached `A = 1` after `git replace` made it `A = 9`) and mailmap sources in C5 |
| Codex C-M2 (major, on C2) | The reuse key omitted installed dependency-file integrity; a hit revalidated nothing (Codex fault injection: key identical, verifier called 0 times) | Fixed in C3: the key binds verified dependency content; a hit whose binding disagrees with installed files is refused |
| Fable C3 check | SOUND WITH AMENDMENTS: MAJOR `attr.tree`/`GIT_ATTR_SOURCE` bound only by text; MINOR undecodable Git output escaped the key path | Fixed in C4 (Claude's probe: neither changes archive output on Git 2.56 or 2.43; bound anyway) |
| Fable C5 check | SOUND WITH AMENDMENTS, three MINOR: filter drivers, export-subst placeholders reading refs and history, `GIT_DIR`-family redirection; reword the e2 ruling | Fixed in C6; e2 reworded to "unkilled by design" |
| Codex C-M3 (bounded major, on C6) | The export-subst key omitted the detached HEAD object: `$Format:%D$` stale after detached HEAD moves; reproduced on Windows and WSL Git 2.43 | Claude reproduced it and found the same class for `%cr`/`%ar` (wall-clock dates, stale after 3 s on both platforms), so a HEAD-object key would not cover it. C7: export-subst in effect → never reuse (Codex accepted this replacement for its prescribed key) |
| Fable C7 / C7b / C7c (before expensive validation, as Codex required) | C7: MEDIUM four `git grep` detection gaps (NUL byte in `.gitattributes`, attributes marking it binary or `-diff`, `GIT_LITERAL_PATHSPECS=1`, symlinked `.gitattributes`), each reproduced on 2.56 and 2.43; LOW remove mailmap keying. C7b: LOW-MEDIUM a non-UTF-8 tree path crashed on Windows; LOW a rule line ending " missing" disabled reuse. C7c: SOUND | Each fixed test-first; C7c accepted |

### Checkpoint C runs

`python -m tools.testing.run_profile --profile checkpoint --base 1c7be2d`. Windows runs the main selection, then the full-depth audit-current subrun as load with three concurrency repeats inside it; WSL runs the selection and audits serially without load. Counts marked † are Codex's independent raw recounts. Counts marked ‡ are reported in Claude's ledger only and were not independently recounted.

| Candidate | Platform | Profile | Selected | Main subrun | Audit (full depth) | Repeats | Verdict |
|---|---|---|---|---|---|---|---|
| Checkpoint C candidate C1 | Windows | `20261005T132919-60064-5f4507` | 5,138 / 349 deselected | `20261005T132955-38776-f1257b`: 1 failed, 5,026 passed, 38 skipped ‡, exit 1 | `20261005T140041-37216-a21b44` 73 passed (817.29 s) | 3 × (373 passed, 8 skipped), stability complete | **FAILED** |
| Checkpoint C candidate C1 | WSL | `20261005T132940-435-b79cdb` | 5,138 | `20261005T133008-459-3f6684`: 1 failed, 4,974 passed, 90 skipped ‡, exit 1 | `20261005T134608-4725-1bd160` 73 passed ‡ | — | **FAILED** |
| C2 | Windows | `20261005T142119-3620-122aef` | 5,266 / 222 | `20261005T142148-31388-555572`: 5,152 passed, 40 skipped † | `20261005T145000-61796-f9f754` 74 passed † | `…145004-58048-8a4f3f`, `…145105-59008-6ab62d`, `…145154-34684-a0d12d`: 373/8 each †, complete | pass (held) |
| C2 | WSL | `20261005T142137-433-860a9f` | 5,266 | `20261005T142157-456-31e8f9`: 5,192 nodes, exit 0; passed/skipped split not established in this summary | `20261005T143625-4800-ef0381` 74 nodes, exit 0 | — | pass (held) |
| C6 | Windows | `20261005T192150-56284-034800` | 5,277 / 222 | `20261005T192219-47988-57f35d`: 5,160 passed, 40 skipped † | `20261005T195104-33780-5e488f` 77 passed † | `…195107-44768-283849`, `…195203-51036-27d952`, `…195251-32816-62c630`: 373/8 each †, complete | pass (held) |
| C6 | WSL | `20261005T185622-22840-381e21` | 5,277 | `20261005T185633-22860-e96e81`: 5,200 nodes, exit 0; passed/skipped split not established in this summary | `20261005T191221-32102-3fc5b3` 77 nodes, exit 0 | — | pass (held) |
| **C7c** | Windows | `20261006T165203-17936-8e9c8e` | 5,287 / 222 (= 5,210 main + 77 audits) | `20261006T165231-17364-a27677`: 5,170 passed, 40 skipped † | `20261006T172240-34904-cec2b9` 77 passed † | `…172245-58920-2d7c69`, `…172354-11236-036a75`, `…172445-41728-634eda`: 373/8 each †, complete | **pass, accepted** |
| **C7c** | WSL | `20261006T163015-16613-b5b03e` | 5,287 | `20261006T163028-16633-001370`: 5,120 passed, 90 skipped † | `20261006T164406-23777-c2a176` 77 passed † | — | **pass, accepted** |

Every subrun of the passing checkpoints ran at full depth with no record problem. Windows qualifications: `parent=not_found:ancestor_exited` only. WSL: `native=unsupported`, `guard=unsupported_platform`, `parent=unsupported`. The WSL clone on C7c held all 18 files byte-identical to the lane (`c7-wsl/files-wsl.sha256`); its `git diff` hash differs only through Git 2.43's diff formatting.

Supporting C7c checks: Windows gates tier 336 passed, Task 4 controls 580 passed, full-tree Ruff clean (identity unchanged before and after); WSL narrow controls 203 passed / 7 skipped with TMPDIR set and unset.

### G — full/quick parity and failure parity

| Source | Platform | Full | Quick | Comparison |
|---|---|---|---|---|
| pre-amendment `de18263d…` | Windows | `20261005T120957-14020-8dfeac`: 340 passed in 1,361.04 s; budget h5 100/100 | `20261005T123242-55416-27ae6c`: 340 passed in 821.34 s; h5 1/100 | selection digests, node sets and per-node phase outcomes equal; audit-current 846.1 s full vs 344.4 s quick (73 nodes) |
| pre-amendment `de18263d…` | WSL | `20261005T130159-2430-08a42c`: 340 passed in 833.1 s | `20261005T125106-1325-6756ef`: 340 passed in 597.6 s | g1 controls 444 passed / 42 skipped, TMPDIR set and unset |
| Checkpoint C candidate C1 `41ee2f9c…` | WSL | `20261005T140601-12489-a55ae8`: 340 passed in 822.26 s | `20261005T135514-11250-da20cb`: 340 passed in 591.48 s | — |
| C2 | WSL | `20261005T145457-12585-ca6a4f`: 341 passed in 768.92 s | `20261005T144454-11337-ef490f`: 341 passed in 553.95 s | there is no exact C2 Windows formal-parity claim; Codex: none is made from unchanged depth code alone |
| C6 | Windows | `20261005T183720-53128-0ac4b8`: 352 passed in 1,588.18 s (contended) | `20261005T190351-47188-da123a`: 352 passed in 1,077.37 s | equal digests, nodes, outcomes |
| C6 | WSL | `20261005T184105-10570-d49b64`: 352 passed in 822.91 s | `20261005T182958-4363-79233b`: 352 passed in 608.04 s | equal |
| **C7c** | Windows | **`20261006T161146-44836-9d6430`**: 362 passed in 1,441.66 s (contended) | **`20261006T163550-59340-0cbf8e`**: 362 passed in 971.36 s | Codex recomputed: identical digests, 362 nodes and outcomes, COMPLETE/ACTIVE/exit 0, H5 100 vs 1 |
| **C7c** | WSL | **`20261006T161559-7035-a43e79`**: 362 passed in 802.29 s | **`20261006T160531-3383-de57ec`**: 362 passed in 586.20 s | same |

Failure parity on C7c: f1 and f2 fail as required at quick and full depth on both platforms (Windows through the mutation harness; WSL injected into the clone and restored from HEAD). Codex accepted G for the Task 4 mechanism on C7c. G does not authorize quick depth for checkpoints, final runs or coverage gates, and supplies no fresh independent repeat or repeat-100 claim at quick depth. Windows formal timings overlapped the WSL chain; no clean cache-saving or Task 5 speed claim follows from them.

### Mutation history (Task 4 harness `mutate_task4.py`; restore from a byte copy, empty `PYTHONPYCACHEPREFIX`)

| Run | Source | Result |
|---|---|---|
| mutation1 | pre-amendment | 25/26; e2 survived (a real control gap: fixed with a twin repository) |
| mutation3 | after the e2 control fix | e1–e6 6/6 |
| mutation6 | Checkpoint C candidate C1 amendments | r12, e7, d9 3/3 |
| cumulative to C2 | C2 | 32/32 (d1–d9, e1–e7, r1–r12, f1q/f1f/f2q/f2f), e2 killed only after its control fix (ledger correction of an earlier "30/30") |
| mutation7 | C3 | c1–c5, m1–m4, e7 10/10 |
| mutation8 | C4 | 39/43: r5 and r10 stale anchors; r8 survived (a real control gap introduced by the F1 fix, then fixed); e2 survived |
| mutation9 | C5 | 46/47; e2 |
| mutation10 | C6 | 50/51; e2 |
| **mutation11** | **C7c** | **52/53; e2 unkilled by design** |

### Retained failed, invalid and stopped attempts

- Checkpoint C run 1 on Checkpoint C candidate C1: FAILED on Windows and WSL (above).
- C3 controls on Windows: 548 passed, 1 FAILED: `test_run_profile.py::test_every_counted_repeat_is_completely_overlapped_by_one_load_run` returned `unrun` ("only 2 of 3 repeats were completely overlapped in 4 attempts"), the designed refusal, never a false pass. Isolated reruns passed in 31, 42 and 58 s; it passed on C5, C6, C7c and in every checkpoint. Codex: a non-passing designed UNRUN; LOW margin custody (residuals).
- C3 Windows formal run STOPPED mid full run and C3 WSL STOPPED after narrow controls (187 passed / 7 skipped), for Fable's C3 amendments. The surviving lane pytest tree and its children were stopped; no lane python process remained.
- C4 patch and backup `plan-11-30-lane-backup-stageb-c4-20261005T1618-INVALID-mutant-snapshot`: INVALID, taken while a mutant was applied; kept, never used.
- C5 WSL chain STOPPED after narrow controls (190 passed / 7 skipped) because Fable's C5 check required C6.
- C7c WSL attempt 1: FAILED before any test (`uv` not on PATH in a non-login shell); kept as `c7-wsl/attempt1-uv-not-on-path/`.
- C2 and C6 passing checkpoints: retained as passing executions of held candidates, not acceptance.

### Codex acceptance (2026-10-06 18:40:36 UTC)

Task 4 and Checkpoint C ACCEPTED on C7c; G ACCEPTED for the Task 4 mechanism; the 18-path local commit released. Codex independently verified all 123 seal members (seal `980af30a…`), the lane identity and all 18 Windows/WSL source bytes, reproduced C-M3's fix as passing on native Windows, and recounted the raw checkpoint and formal records above. The pre-existing Windows `_run` reader-thread behaviour on other non-UTF-8 Git output fails loudly and is out of this correction's scope. Stage A's acceptance remains tied to `acc2a1c` and is not a C7c final measurement.

Receipts: `plan-11-30-task4-budget-inventory-20261005` (seal `76a581e2…`); `plan-11-30-checkpoint-c-evidence-20261005` (pre-amendment formal source, Checkpoint C candidate C1, C2; 51 files, `f1df55db…`); `plan-11-30-checkpoint-c-c6-evidence-20261005` (C3–C6, 37 files, `7a5f1e59…`); `plan-11-30-checkpoint-c-c7c-evidence-20261006` (C7–C7c, 123 files, `980af30a…`).

## Task 5 — Core-only xdist under one controller-owned run, partial-commit index scanning, quick commit audits (2026-10-07 to 2026-10-08)

**Status: accepted on candidate E; delivered locally at `66ddabf` (Task 5 delivery section).** Codex accepted Task 5 and Checkpoint D on E, including the partial-commit scanner correction and the quick commit-audit switch, after the pairs5 timing receipt (2026-10-08 15:23:56 UTC). Candidate F (Option A rename) and the exact pragma later changed four test-harness files; Codex carried E's worker, selection and performance acceptance forward to them without new pairs or checkpoint runs. pairs5 is E timing evidence, not a measurement of F or `66ddabf`.

Base for every Task 5 candidate: `43eb19078a07d06e2d91d0913674b24af3616730`.

### What was built

| File | Responsibility |
|---|---|
| `pyproject.toml`, `uv.lock` | `pytest-xdist>=3.6` in the dev extra; the lock adds only pytest-xdist 3.8.0 and execnet 2.1.2 |
| `tools/testing/run_context_xdist.py` (new) | Controller verdict and worker start/output: signed worker records (HMAC), job-membership confirmation of each worker, phase facts per `(node, when)` with the receiving channel and outcome, execution checks, escaped-descendant attribution, `finish_controller` guarded to INVALID `controller_failure` |
| `tools/testing/run_context.py`, `run_context_records.py` | `phases.worker`, the terminal `xdist` table, the worker-record table and a shared `_persist` sink; `finish_run(xdist=…)` (a non-valid verdict makes the record INVALID); summary `xdist=` |
| `tests/conftest.py` | Worker and controller hooks; guard installed in workers before collection; an INVALID verdict forces `session.exitstatus = INTERNAL_ERROR` when pytest would otherwise exit OK, before `finish_run`, so the record and the exit agree |
| `tests/support/profiles_plugin.py` | Pre-spawn refusal of `-n/--dist/--tx/--numprocesses` unless profile `core-parallel`, `-n 2`, `--max-worker-restart=0`, `--dist load\|worksteal`, no looponfail, no coverage |
| `tools/testing/test_profiles.py`, `tests/profiles.toml` | `core-parallel` = core tier minus tagged nodes minus the reviewed `[parallel].serial` list (the serial probe plus 18 core files that launch child processes, enforced by a gate); `core-serial` = the remainder |
| `tools/testing/run_profile.py` | `--profile core --workers 2`: disjoint, complete partition, selection digests, xdist verdict, `--dist worksteal`; subrun record matched by run folders created after launch with the subrun's own root PID first (no cross-process wall clock); commit-index forwarding; quick commit audits |
| `tools/tracked_repository_files.py`, `tools/doc_paths.py`, `tests/unit/docs/test_docs_index.py`, `test_plan_directory_hygiene.py` | Partial-commit correction: `index_environment` honours the forwarded commit index for that repository only (missing named index → `commit_index_missing`); the index-listing sites route through it |
| `tests/support/xdist_faults.py` (new) | Real two-worker fault plugin (`missing_call`, `foreign_node`) |
| `tests/unit/tools/test_run_context_xdist.py` (new), `test_run_context_xdist_probes.py` (new), `test_run_profile.py`, `test_test_profiles.py`, `test_test_profile_selection.py`, `test_tracked_repository_files.py` | Controls (below) |
| `tests/unit/tools/run_context_child_sites.json` | Four entries: two `nested_pytest`, one `literal_program` grandchild, and (candidate F) one `nested_pytest` for the hook-environment test |
| Plan 9.96 manifest JSON | `write_record` keys renamed to `_persist`; `run_context_xdist:sign:json_serialization` (digest-only, demonstrating test); `run_profile:_main_core:stdout_export` |

### Contract as built

- **One controller-owned run.** xdist runs only as the runner's `core-parallel` subrun. The controller keeps the unchanged job, guard, registry, streams and verdict; workers never start a run, enrol or open its streams. Run metadata reaches workers in execnet `workerinput`, never the environment, and is popped once validated.
- **Workers.** Install the guard in `pytest_configure` before collection; check ancestry to the controller (Windows: creation-time ancestry; elsewhere the `/proc` parent chain, labelled `xdist=weaker`); write one signed record.
- **INVALID verdict** on: a missing, unsigned or mismatched record; identity, ancestry, guard or source differences; a crash; lost, duplicate or unknown-worker phases; collection disagreement; a worker the controller could not confirm in its job; a reused identity; a worker still running after 15 s; unknown job members; escaped descendants (attributed to their parent worker); and, after D-M1, `unselected_phase`, `node_incomplete`, `call_missing` (passing setup, no call), `call_unexpected` (call after a non-passing setup), `mixed_owner` and `attribution:<gw>`. An INVALID verdict forces a non-zero exit.
- **Coverage stays serial.** `-n` with coverage is refused before spawn (ruling; Codex: shard combination is unnecessary while every coverage gate is serial).
- **Partial-commit correction (Task 3 LOW residual).** Inside a commit hook the runner forwards git's `GIT_INDEX_FILE` to every subrun under harness names; as delivered these are `TEST_RUN_COMMIT_INDEX_FILE` / `TEST_RUN_COMMIT_INDEX_ROOT` (renamed from `OPTIMUS_COMMIT_INDEX_*` in candidate F). A guard enumerates all 9 index-listing sites: 4 read the commit's index, 5 are reviewed exemptions. RED: `test_inside_a_commit_hook_run_the_scanner_lists_the_commit_s_own_index` (a kept file hidden by a deletion staged outside the commit) and a real partial-commit hook test.
- **Quick commit audits (R5 after G).** A commit keeps only the current audits its changed inputs reach (never through broad fallback), runs them at `audit_depth=quick`, and `record_validity` accepts a quick record only for a subrun asked for quick, adding qualification `audit_depth=quick`. Checkpoint and final profiles stay full.

### Fable 5.1 findings 1–7

| # | Finding | Disposition |
|---|---|---|
| 1 | MEDIUM: the controller never validated a worker's identity itself (self-report only; a dead identity passed `survivor`) | Controller confirms job membership at node collection; `membership:<gw>` when unconfirmed on native |
| 2 | LOW: the run secret was readable by worker tests | `workerinput.pop` after validation |
| 3 | LOW: `finish_controller` unguarded | wrapped; INVALID `controller_failure` and `finish_run` still called |
| 4 | LOW: a native run without the run's job judged as having no escaped descendants | `members_unknown` |
| 5 | LOW: escaped descendants unattributed | `escaped: [{pid, creation_time, parent_pid}]` |
| 6 | Info: a crash also yields xdist's synthetic `???` report → `unknown_worker` | kept (fail-closed, cosmetic; Codex: no fix needed) |
| 7 | LOW (candidate-b round): `_run_record` could return another new folder | root PID match first, `root_parent` only when none, ambiguity → `None` |

Fable rounds: candidate `361b5ab0…` (pre-validation) SOUND WITH AMENDMENTS (1–6); candidate b `a23a74d0ef8a…` SOUND WITH AMENDMENTS (1–5 closed; new 7; WSL clock-step diagnosis confirmed from the records); candidate D SOUND (its first confirmation attempt failed on a Fable rate limit, 429, before any verdict); candidate E SOUND; candidate F SOUND; pairs5 receipt SOUND WITH AMENDMENTS.

### WSL failures (retained)

| Attempt | Source | Result | Root cause and fix |
|---|---|---|---|
| WSL 1 | `43eb190` + `4e33ffb04e1d…` (clone `/root/p1130-t5-20261007T044039`) | focused 441 passed, 46 skipped, **1 FAILED**: `test_a_worker_without_run_metadata_refuses_to_start`. Worker gw1 refused correctly and the record was INVALID, but xdist on Linux **exited 0** although gw1's tests never ran. Core `--workers 2` verdict pass (2,745/1,357) | An INVALID verdict left a passing exit status (the same faults also exited 0 on Windows). Fixed test-first: the conftest forces a non-zero exit and the record's exit equals it (4 RED on Windows, then GREEN) |
| WSL 2 | `43eb190` + `361b5ab00801…` (clone `/root/p1130-t5-20261007T050143`) | focused 444 passed, 46 skipped, **1 FAILED**: `test_core_runs_on_two_real_workers_and_a_serial_remainder` ("core-serial: no_run_record"). Core `--workers 2` verdict pass (4,104 = 2,747 + 1,357) | The serial subrun's record `20261007T050313-939` was valid but its `started_utc` was 3.3 s earlier than the parallel subrun's although its process was created later: the WSL2 wall clock stepped back, and the runner's cross-process recency check rejected the subrun's own record. A pre-existing Task 2 runner fragility. Fixed test-first: match only run folders created after launch, no cross-process wall-clock comparison |

### Matched pairs (three serial vs two-worker core pairs, native Windows; caller wall includes collection, runner work and every inter-subrun pause)

**Recorded values** (caller walls from each set's sealed `summary.txt`; candidate source as recorded in `identity-before.txt`):

| Attempt | Source | Serial walls (s) | Two-worker walls (s) | Disposition |
|---|---|---|---|---|
| pairs | `43eb190` + `4077f44e5769…`; `--dist load`; partition 2,883 / 1,219 (core 4,102) | 266.948 / 273.500 / 274.160 | 236.519 / 236.298 / 237.647 | **FAILED** (< 20 %). Cause measured: `--dist load` imbalance (gw0 idle from 56 s while gw1 ran to 138 s). Also exposed 18 child-launching core files admitted to workers |
| pairs2 | `43eb190` + `4e33ffb04e1d…`; worksteal; launchers serial; 2,745 / 1,357 | 269.693 / 274.867 / 274.066 | 201.561 / 209.377 / 210.218 | pre-Fable source history; not evidence for a later candidate |
| pairs3 | candidate D `e24d2425…`; 2,747 / 1,357 (core 4,104) | 317.297 / 314.818 / 312.165 | 231.156 / 260.334 / 232.359 | numeric target met on D; does not transfer to E (Codex). Loaded host (stray process, below). Pair 2: an unexplained ~30 s gap between the parallel record's finish (08:24:36.7Z) and the serial record's start (08:25:06.9Z) |
| pairs4 | candidate E `2bd48b7d…` | 302.639 / 285.049 / 283.997 | 208.253 / 218.128 / 220.092 | an actual loaded-host result on E (stray process); kept; Codex required an unloaded confirmation |
| **pairs5** | **candidate E `2bd48b7d…`**, Codex-commissioned | **298.708 / 277.770 / 268.679** | **247.869 / 204.983 / 200.993** | **PASS, accepted** (below) |

**Report-derived calculations** (computed by this report from the recorded walls above, each for its own candidate; inputs are the three serial walls S and three two-worker walls W of one set):
- median improvement = `1 - median(W) / median(S)`, the plan's acceptance definition;
- ratio of means = `1 - mean(W) / mean(S)`;
- mean per-pair improvement = `mean(1 - W_i / S_i)`.

| Attempt (candidate) | median(S) / median(W) (s) | Median improvement | Ratio of means | Mean per-pair improvement | Per pair |
|---|---|---|---|---|---|
| pairs (`4077f44e…`) | 273.500 / 236.519 | 13.521389 % | 12.784554 % | 12.773059 % | 11.40 / 13.60 / 13.32 % |
| pairs2 (`4e33ffb0…`) | 274.066 / 209.377 | 23.603439 % | 24.122127 % | 24.128482 % | 25.26 / 23.83 / 23.30 % |
| pairs3 (D) | 314.818 / 232.359 | 26.192594 % | 23.343818 % | 23.340072 % | 27.15 / 17.31 / 25.57 % |
| pairs4 (E) | 285.049 / 218.128 | 23.477016 % | 25.836397 % | 25.722222 % | 31.19 / 23.48 / 22.50 % |
| pairs5 (E) | 277.770 / 204.983 | 26.204054 % | 22.636268 % | 22.805276 % | 17.02 / 26.20 / 25.19 % |

**Recorded assertions and Codex's figures**, kept separate from the calculations above:
- Claude's ledger and packets recorded 13.5 % (pairs), 23.6 % (pairs2), 26.2 % (pairs3) and 23.48 % (pairs4), and the pairs5 receipt recorded 26.204054 %. The pairs3 and pairs4 packets' "mean" (23.3 %, 25.84 %) is the ratio of means.
- Codex recomputed pairs3 as a 26.1926 % median and a 23.3438 % mean, and pairs4 as 23.477016 % and 25.836397 %; both means are ratios of means.
- For pairs5 Codex gave 26.2040537135 % (median), 22.6362675811 % (ratio of means) and 22.8052762367 % (mean of per-pair improvements).
- Codex's 2026-10-09 audit independently recomputed the five medians and ratios and found they agree with these calculations.

Acceptance uses only Codex's pairs5 median on candidate E.

In every pair set all 9 subrun records were valid and all 12 recorded-order gap predicates passed (serial runs, and per worker for parallel subruns; decile ratios 0.887–1.45 in pairs, 1.02–1.393 in pairs2, 1.05–1.372 in pairs3, 1.093–1.295 in pairs4; pairs5 below). On core 4,104 (pairs3 onward):
- every serial run had 4,067 passing calls and 37 skips;
- each parallel subrun had 2,737 passing calls and 10 skips (7 call-skipped, 3 setup-skipped);
- each serial remainder had 1,330 passing calls and 27 skips.

On core 4,102 the serial runs had 4,065 and 37.

Also retained, not a pair:
- The correctness probe `core-probe1` on the pairs-attempt-1 source: `core-parallel` `20261007T034059-32712-4ee8d1` 2,873 passed / 10 skipped; `core-serial` `20261007T034323-25080-1b964a` 1,192 passed / 27 skipped; qualification `parent=UNKNOWN:access_denied`.
- One Checkpoint D core run on D: 221.8 s step wall, which the ledger recorded as about 19 % against pairs2's serial median. It is a single run, not a matched pair.

### D-M1 → candidate E

Codex (2026-10-07 08:45:34 UTC, on D): **D-M1 (major).** `Controller.phase` kept only `(node, when) → worker`, so balanced totals could hide a missing call after a passing setup, a node's phases split across workers, or a phase for an unselected node. Codex demonstrated all three with in-memory counterexamples against D's own fixture, on Windows and WSL.

- **RED on D** (`task5/dm1/red.txt`): 7 failed, 3 passed. Unit controls for Codex's three cases plus `call_unexpected` and channel attribution; and two **real** nested two-worker faults, `missing_call` (gw1 runs one test with pytest's setup-only switch: setup and teardown sent, no call, counts balanced) and `foreign_node` (gw1 sends a counted report for an unselected node through xdist's own channel), both with verdict `valid` on D. The legitimate-sequence control and the existing complete-run control passed.
- **Fix** (existing controller seam): `Controller.phases` maps `(node, when)` to `(channel worker, outcome)`; phases are attributed by `report.node.gateway.id`, the worker's own `worker_id` kept only as its claim (ruling); the verdict's `_execution_problems()` adds the checks listed under the contract. Serial recorder streams are untouched.
- **GREEN on E:** xdist + probes 44 passed (both real faults INVALID, named problem, non-zero exit equal to the recorded exit); runner 66 passed; Ruff clean. Mutants x50–x56: 7/7 killed (x54 attributes by the claim; x56 requires a call after every setup and is killed by the legitimate control).
- **Candidate E** = `43eb190` + `2bd48b7d2702dd978ec3abbf0a65108afab757442fd1109d0f3568b435d83cd2` (changes vs D: `run_context_xdist.py`, `test_run_context_xdist.py`, `xdist_faults.py`; 23 paths, 4 new files intent-to-add).

Codex closed D-M1 (2026-10-07 12:27:23 UTC): seven bounded direct controls pass on native Windows and the E WSL clone; these are unit-model assertions, and the retained real nested faults exercise `missing_call` and `foreign_node` through actual two-worker sessions.

### Stray-process disclosure

At 10:57:34 IST on 2026-10-07 one of Claude's diagnostic commands left an inline Python process (PID 24500, with parents 51640, 57404, 48376, 18456) running. It did no plan work and wrote nothing to the lane or evidence. At 17:48:16 IST it had used 24,257 CPU-seconds (about one core; a 10-second sample showed 0.99 CPU-s/s). It overlapped every timed run after 10:57: the Windows mutation `mutation-t5` and WSL Checkpoint D on C, Windows Checkpoint D on D, pairs3, the D-M1 work, and the whole E chain (WSL and Windows Checkpoint D on E and pairs4, 14:35:09–16:31:40 IST). The Checkpoint D packet's and the D-M1 packet's statements that nothing else of Claude's was running are superseded by the addendum (`43c3ade4…`).

Codex's disposition: correctness verdicts stand; pairs3 and pairs4 stay as loaded-host results; the addendum's expectation that the load understated the benefit is unmeasured and no direction or adjustment is accepted; the stale PID list must never be used to stop processes. Codex commissioned pairs5.

### pairs5 acceptance

Preconditions (2026-10-08, 19:34–19:40 IST): identity `43eb190` + `2bd48b7d…` with all 23 file hashes equal to E's record and the 4 new files index-visible; `uv sync --frozen --extra dev --dry-run` "Would make no changes", freeze hash `e56fd1c3…`, pytest 9.1.1, pytest-xdist 3.8.0, execnet 2.1.2; the stray chain absent (host restarted about 17:24 IST), established from fresh process identities and CPU sampling, with nothing stopped.

Ambient load: load-pre (19:39:34, 30 s) mean 27.2 % of 12 logical processors, `TextInputHost` about 0.94 core; a foreign pytest from another session started at 19:40:04 and its end before pairs5 (19:40:49) is unreceipted. load-post (20:05:50) mean 15.2 %, `TextInputHost` about 1.01 core, no foreign pytest. Two earlier load receipts are kept (attempt 1: probe format error; attempt 2: 37.1 % with a foreign Claude session's pytest running in another repository). **pairs5 is not an idle-host result**; foreign overlap during the run is UNKNOWN. It is timing evidence for candidate E only, not a measurement of the delivered HEAD (`66ddabf`) or of candidate F.

Result (19:40:49–20:05:49 IST, `matched_pairs.sh` exit 0, identity unchanged after): median serial 277.770 s, two-worker 204.983 s, **median improvement 26.2040537135 % ≥ 20 %: PASS** (Codex recomputation). Per pair 17.02 / 26.20 / 25.19 %; acceptance uses the specified median, not each pair. All 9 terminal records pass E's `record_validity`; all 12 gap predicates pass with zero negative gaps (decile ratios 0.917–1.32); each invocation covers the identical 4,104-node set, two-worker subruns disjoint 2,747 + 1,357.

| Pair | Serial run | Two-worker runs (parallel; serial remainder) |
|---|---|---|
| 1 | `20261008T141120-40872-943969` | `20261008T141614-46124-145be9`; `20261008T141838-38244-be891d` |
| 2 | `20261008T142021-49528-172f13` | `20261008T142455-49196-ce5411`; `20261008T142642-40480-669ec5` |
| 3 | `20261008T142820-16952-54ab69` | `20261008T143249-7456-d888e8`; `20261008T143437-44564-b983eb` |

Pair 1's two-worker run has 31.5 s between the parallel record's finish (14:18:07.30Z) and the serial record's start (14:18:38.76Z), against 3.9 s and 6.7 s in pairs 2 and 3: the second occurrence of the ~30 s pause. It is charged in the caller wall; its cause is UNKNOWN (no process-exit timestamp separates controller shutdown from the next launch).

Receipt `2026-10-08-claude-pairs5-timing-receipt-plan-11-30.md` (`df3376ea…`); Fable review copy `0baac9ba…`; seal `plan-11-30-pairs5-timing-20261008` (89 files, `f00f5851…`).

### Checkpoint B worker obligation (annotation 2026-10-09)

Checkpoint B left a required Task 5 obligation: worker kill-on-close and attribution. Codex's 2026-10-09 audit discharged it **for the accepted native Windows controller topology**. The evidence is `tests/unit/tools/test_run_context_xdist.py::test_an_interrupted_controller_leaves_no_worker_running` and `::test_a_grandchild_left_running_by_a_worker_is_an_escaped_descendant`, together with the accepted D-M1 phase/channel controls. The real grandchild control checks parent-worker attribution, the INVALID verdict and termination. WSL keeps its weaker capability label (`xdist=weaker`). This does not discharge Checkpoint B's F4: an abrupt hard kill of the outer runner can still orphan its subruns, and no arbitrary forced-kill cleanup is promised.

### Mutation (Task 5 harness `mutate_task5.py`)

| Run | Source | Result |
|---|---|---|
| mutation-t5 | C `5b9a13f9…` | 47/49; x17 (verdict with `survivors=None` never asserted `members_unknown`) and x45 (the other-repository check tracked the same file as the committed repository) survived: test gaps, no code defect |
| mutation-t5-recheck | D `e24d2425…` | x17, x45 killed (2/2) after the two tests were strengthened |
| mutation-dm1 | E `2bd48b7d…` | x50–x56 7/7 |

## Checkpoint D — Stage B through Task 5 (2026-10-07)

**Status: accepted on E** (Codex, 2026-10-08 15:23:56 UTC). Codex HELD D for D-M1 (2026-10-07 08:45:34 UTC), then accepted E's correctness evidence and closed D-M1 (12:27:23 UTC), holding only for unloaded timing, which pairs5 supplied.

### On candidate D (Windows) and C (WSL)

Candidate C = `43eb190` + `5b9a13f9268d5021af19897e0c061e45ee9e47d84a0b2b964e7035728e46ced3`. Candidate D = `43eb190` + `e24d24252795ad2fb0a8042a8fba23f5cd0e5e822f9ed257d7a7de01d4d3582f`; D differs from C only in two test files (`test_run_context_xdist.py`, `test_tracked_repository_files.py`), with no production change.

| Platform | Source | Checks |
|---|---|---|
| Windows (`cpd-win`, one serial chain, identity unchanged) | D | gates 336 passed; controls 614 passed; Ruff clean; core `--workers 2` (`20261007T061804-49108-e96f0a`: parallel `20261007T061825-54076-0d6c8b`, serial `20261007T062030-39260-1e6273`) pass, 4,104 = 2,747 + 1,357; checkpoint `20261007T062146-39684-ced0e3` pass, 5,421 selected / 142 deselected, broad fallback: main `20261007T062215-30976-13c1f9` 5,304 passed / 40 skipped †, audit load `20261007T065540-33148-609230` 77 passed †, repeats `…065544-55672-b82e14`, `…065641-30952-55b517`, `…065728-4112-5bb42f` 373/8 each †, stability complete |
| WSL (`cpd-wsl`, clone `/root/p1130-cpd-20261007T053553`, Git 2.43) | **C** | focused 500 passed / 47 skipped, TMPDIR set and unset; core `--workers 2` pass (`20261007T053931-1524-45b6d5`; `xdist=weaker`); checkpoint `20261007T054107-3866-5b3585` pass, 5,421 / 142: main `20261007T054124-3887-d409f3` 5,251 passed / 93 skipped †, audit `20261007T055731-11228-93b4f5` 77 passed † |
| WSL delta (`cpd-wsl-d`, clone `/root/p1130-cpd-d-20261007T060658`) | D | the two changed test files: 39 passed / 1 skipped, TMPDIR set and unset; all 23 files byte-identical lane vs clone (clone whole-diff hash `cdfc1bfa…` differs only by Git 2.43 diff formatting) |

Codex: the full WSL chain is C-source evidence, not a relabelled exact-D run; the bounded C→D composition is acceptable for the unchanged production paths. The Windows mutation run shared the host with WSL's focused and core runs.

### On candidate E (serial chain 14:35–16:31 IST, 2026-10-07; loaded by the stray process)

| Platform | Checks |
|---|---|
| WSL (`cpd-wsl-e`, clone `/root/p1130-cpd-20261007T090512`, all 23 files byte-identical to the lane) | focused 508 passed / 47 skipped, TMPDIR set and unset; core `--workers 2` pass (`20261007T090926-1587-a89bcf`: parallel `…090934-1597-046dcd` 2,747 passed †, serial `…091004-3219-f981c8` 1,317 passed / 40 skipped †; `xdist=weaker`); checkpoint `20261007T091054-3931-37f5f4` pass, 5,429 / 142: main `20261007T091109-3951-879862` 5,259 passed / 93 skipped †, audit `20261007T092632-11405-f997a0` 77 passed † |
| Windows (`cpd-win-e`, identity before = after) | gates 336 passed; controls 622 passed; Ruff clean; core `--workers 2` pass (`20261007T094509-42020-906df7`: parallel `…094530-47288-a21877` 2,737 / 10 †, serial `…094724-57008-18aa55` 1,330 / 27 †); checkpoint `20261007T094843-60836-d03a96` pass, 5,429 / 142 (2,857 s): main `20261007T094911-37452-8dfc41` 5,312 passed / 40 skipped †, audit load `20261007T102313-39468-e4071f` 77 passed †, repeats `…102317-12100-0f8fab`, `…102415-54184-8c95da`, `…102502-29384-0514a5` 373/8 each †, stability complete |
| Timing | pairs4 (loaded; above), then pairs5 (above) |

† Codex raw recount. Qualifications retained: Windows `parent=not_found:ancestor_exited`; WSL `native=unsupported`, `guard=unsupported_platform`, `parent=unsupported`, `xdist=weaker`. Codex: the background load qualifies the environment; passing executions do not prove every possible unloaded interleaving would pass.

### What Codex accepted

Task 5 and Checkpoint D on E, including the partial-commit scanner correction (named commit-index propagation scoped to the owning repository, missing-index refusal, inventory-site controls and Fable's real-hook probes; no optional index-selection bypass) and the profile-specific changed-input quick audit switch (never through broad fallback; full checkpoint, final and coverage protection retained). Also accepted as mechanisms: the controller/job/metadata guard architecture, the conservative serial partition, worksteal scheduling, serial-only coverage, `_run_record`'s own-root preference and ambiguity refusal, and the cosmetic `???` report. pairs5 at 26.2040537 % supplies the matched timing. Receipts: `plan-11-30-checkpoint-d-evidence-20261007` (candidates b/C/D, 1,497 files, `de697a9d…`); `plan-11-30-checkpoint-d-e-evidence-20261007` (all of D's evidence unchanged plus E, 2,356 files, `62c8c21a…`); addendum `43c3ade4…` (outside the seal); `plan-11-30-pairs5-timing-20261008` (`f00f5851…`).

## Task 5 delivery — local commit `66ddabf` (2026-10-08)

**Status: delivered and verified.** Codex verified the delivery (2026-10-08 19:38:33 UTC): commit `66ddabfdf5bb3acccfffe39fa45f70b4b47924ad`, parent `43eb190`, exactly 23 paths, all committed blobs equal to the released post-pragma table, lane clean, fresh full-tree Ruff passes. The hook records name the parent HEAD `43eb190`; with the verified staged/committed bytes they bind to the delivered source, but **they are not independent `66ddabf` full-coverage or final measurements**.

| Attempt | Source | Hooks (UTC) | Result | Receipts (seal) |
|---|---|---|---|---|
| 1 | E (`2bd48b7d…`) | 2026-10-08 15:31:41Z–16:17:28Z | **FAILED, no commit.** `pytest-coverage` failed: commit profile `20261008T153159-2800-2953a7` (5,428 selected / 143 deselected, broad) verdict failed; selected `20261008T153230-55460-6de6f3` 69 failed / 5,242 passed / 40 skipped, exit 1, record COMPLETE/ACTIVE/full/native-valid (Codex recount); quick audit `20261008T161048-37976-08a2f7` 77 passed, valid with `audit_depth=quick`. Every failure was in the ACP entry point (`test_main_wiring.py` 46, `test_launch_approval_cli.py` 17, `test_main_check_config.py` 4, `test_main_debug_trace.py` 2) with 88 refusals `UNCLASSIFIED_VARIABLE: OPTIMUS_COMMIT_INDEX_FILE`: inside a hook the runner forwarded the commit index as `OPTIMUS_COMMIT_INDEX_*`, and the product launch gate refuses any unclassified `OPTIMUS_*` name. Checkpoints, controls and pairs had run without `GIT_INDEX_FILE`; the real partial-commit hook control ran only the scanner. Implementation, Fable and Codex review all missed this boundary | `plan-11-30-task5-commit-attempt1-failed-20261008` (29 files, `c41851de…`) |
| — | Option A → candidate F (`7cc417fecbfac10c7ec8aa93c8b9c5dfbf4ab8973050727e98ccbb7c1227df71`) | — | Codex selected Option A (16:21:35 UTC): rename to `TEST_RUN_COMMIT_INDEX_FILE` / `_ROOT`; no product, launch-gate or registry edit, no `OPTIMUS_*` alias. RED on E: the real `resolve_launch_candidate` over the runner's subrun environment raised `UNCLASSIFIED_VARIABLE`, and a nested ACP entry-point test exited 2. GREEN on F: runner + scanner + child-site tests 256 passed. Changes vs E: two constants and a comment in `tools/tracked_repository_files.py`, two `setenv` names, two runner regression tests with an `_INHERITED` table, one sites entry. Windows: hook-environment rehearsal 138 passed / 6 skipped with 0 `UNCLASSIFIED_VARIABLE`, gates 336, affected controls 269, Ruff and `git diff --check HEAD` clean. WSL (fresh clone, 23 files byte-identical): controls 261 passed / 8 skipped with TMPDIR set and unset, rehearsal 144 passed, 0 `UNCLASSIFIED_VARIABLE`. Fable F: SOUND. Codex accepted F and released one retry (17:51:59 UTC) | `plan-11-30-task5-option-a-evidence-20261008` (40 files, `a693e9b0…`) |
| 2 | F | 2026-10-08 17:54:43Z–18:30:53Z | **FAILED, no commit.** `secret-scan` failed: detect-secrets `Secret Keyword` at `tests/unit/tools/test_run_profile.py:115`, the synthetic `OPTIMUS_API_KEY` fixture value in the new `_INHERITED` table; a read-only scan of the 23 staged files found exactly that one. `pytest-coverage` **passed**: commit profile `20261008T175455-47292-051c06` verdict pass; selected `20261008T175524-54796-e7cd81` exit 0, full/ACTIVE/COMPLETE/native-valid: 5,305 passing call phases, 19 call-skipped, 21 setup-skipped, zero failed phases, and 8 known recorder-control nodes with no call row (5,353 nodes). This is a call-phase count, not a pytest summary total. Quick audit `20261008T182426-47628-a8bda8` 77 passed. This confirmed the namespace fix under the real hook. Claude had not run the local secret scan over the staged set before committing | `plan-11-30-task5-commit-attempt2-failed-20261009` (28 files, `408df6b3…`) |
| — | exact pragma | — | Codex released (18:45:18 UTC) exactly one allowlist comment on line 115; expected file SHA-256 `3dbbcb1a63b6…` (applied and matched; one-line delta; AST equal to F; Codex proved before exit 1 / after exit 0 with the unchanged baseline on scratch copies). Pre-commit: regressions 2 passed, Ruff clean, 23 re-staged by name, staged blobs equal the table, `git diff --check` clean, `python -X utf8 tools/local_secret_scan.py --baseline .secrets.baseline src <23 staged files>` exit 0, staged diff `2184d40ce611…` | (in the delivery seal) |
| 3 | F + pragma | 2026-10-08 18:58:07Z–19:36:01Z | **Committed `66ddabf`.** All applicable hooks passed (YAML had no files). Commit profile `20261008T185820-46316-861d92` verdict pass, obligation `wsl-platform: next checkpoint`; selected `20261008T185847-48092-647199` exit 0, full/ACTIVE/COMPLETE/native-valid, `parent=not_found:ancestor_exited`: 5,305 passing call phases, 19 call-skipped, 21 setup-skipped, zero failed, 8 known no-call recorder controls (call-phase count, not a pytest summary total); quick audit `20261008T192958-22616-a85679` 77 passing calls, exit 0, valid with `audit_depth=quick`. Committed paths and blobs equal the released table; message equals the release; `git status --porcelain --untracked-files=all` empty | `plan-11-30-task5-commit-66ddabf-delivery-20261009` (39 files, `7b89fec9469e…`); delivery receipt `5813197f…` |

**Correction to the Option A packet** (`db1584c4…`). Its disclosure said the full normal-hook run "cannot be rehearsed short of committing". That was wrong. Task 3 had already run the real hook without creating a commit: in a disposable clone, with the change staged in the clone's own index and `GIT_INDEX_FILE` set to `.git/index` as for a normal commit, `pre-commit run optimus-pytest-coverage` ran the actual hook (Task 3 exercises 1–5, HEAD unchanged). Codex recorded that the claim was not needed for acceptance and commissioned no further rehearsal; the actual retry remained the required proof.

**Process rule added by Codex (attempt 2):** the explicit staged-set local secret scan is part of future local commit preflight; it complements the normal hooks and grants no bypass.

## Stage B residuals and owners (2026-10-09)

None of these rows is omitted required implementation. Each is accepted evidence, a qualified observation, a guarantee boundary, optional custody or an evidence obligation, as stated.

| Residual | Kind and status | Owner |
|---|---|---|
| A recurring ~30 s pause between the parallel record's finish and the serial record's start (pairs3 pair 2 on D; pairs5 pair 1 on E, 31.5 s) | Optional, unscheduled observation. Cause UNKNOWN; charged in caller wall; the median target passes. Not a correctness defect or closure blocker; no source change or timing run commissioned | `P11-FEAT-TEST-PROFILES` (backlog: inter-subrun timing observation custody) |
| Overlap-control margin: the fixed 25 s synthetic load window of `test_every_counted_repeat_is_completely_overlapped_by_one_load_run` is sensitive to host contention | LOW, optional, unscheduled. One designed UNRUN on Checkpoint C candidate C3 is retained as non-passing; no future overlap gate is waived | `P11-FEAT-TEST-PROFILES` (backlog: overlap-control margin custody) |
| Validation cost: repeated full-document validation of the 30.8 MB sealed or successor payload (12.7–13.8 s each; about 130 of 276 s across five nodes) | Optional, unscheduled optimization. A measured cost, not proof of achievable saving; audit-contract changes coordinate with `P11-FEAT-ACP-RUNTIME-HARDENING` | `P11-FEAT-TEST-PROFILES` (backlog: validation-cost optimization custody) |
| `OPTIMUS_TEST_VENV` (MAIN-5 runner metadata) is not classified in `launch_policy`; the Option A test keeps it out of the gate call and asserts only pass-through | A pre-existing observation, noted by Fable on candidate F. The Option A rename preserves launch policy; no rename, classification change or new item is commissioned | existing `P11-FU-32` under `P11-FEAT-ACP-RUNTIME-HARDENING` |
| Mutant e2 (export key without the repository) survives | Accepted survivor evidence: unkilled by design and not proven equivalent; the repository component stays as the backstop for unenumerated inputs | Task 4 as accepted |
| Cache cost (C6 and C7c formal timings; the CLI node slower) | Qualified observation: contended, mixed; no cache-saving claim | — |
| Cache thread topology: the conftest clears only the calling thread's stores (F5); audit-current probes are outside the core-parallel partition | Guarantee boundary of Task 4: no cross-session worker-cache guarantee; no new cache work accepted | `P11-FEAT-TEST-PROFILES` (backlog: recorded with the MAIN-5 custody paragraph) |
| Pre-existing Windows `_run` reader-thread behaviour on non-UTF-8 Git output other than tree paths | Fails loudly, never stale; outside the C-M3 correction; no repair commissioned | existing `P11-FU-39` (lifecycle-tooling inventory custody), if taken up as future work |
| xdist with coverage refused; PASSIVE parallel runs on Windows always INVALID; the xdist test file's platform tag triggers broad fallback and platform obligations | Accepted mechanisms and fail-closed behaviour | `P11-FEAT-TEST-PROFILES` |
| Checkpoint B F4: abrupt hard kill of the outer runner orphans its subruns | Not discharged by Task 5 (the worker obligation is discharged for native Windows only, above) | `P11-FEAT-TEST-PROFILES` |
| Commit-hook records of `43eb190` and `66ddabf` carry `wsl-platform: next checkpoint` and name their parent HEADs | They bind to the delivered bytes but are not final measurements; an evidence obligation for Stage B Task 6 | `P11-FEAT-TEST-PROFILES` |
| Partial-commit correction: CI backstop | A held evidence obligation, not a current pass; the source correction is delivered | `P11-FEAT-TEST-PROFILES` |
| Remote Linux CI and base/candidate safety-row comparison | UNKNOWN until a publication grant and comparable CI reports | `P11-FEAT-TEST-PROFILES` |
| Stage A residuals: registry archival PARTIAL/NON-PASSING with one refused member; registry over 512 entries; written-file close latency; boundaries-file interruption window; zero-µs first-decile medians UNKNOWN; WSL wall-clock minute-scale uncertainty | Unchanged by Stage B | as recorded in the earlier sections and the backlog |

## Stage B Task 6 — not yet run (PLACEHOLDER)

**PLACEHOLDER. No Stage B Task 6 measurement exists. Nothing in this section is a result.**

*Historical status at recording (committed with `3cece0a`, 2026-10-09). Current (2026-10-09 07:24 UTC): the final gates ran at `3cece0a` and Codex accepted the local evidence; see "Stage B Task 6 — final gates at `3cece0a` (2026-10-09)".*

**Prerequisites, in order** (Codex, 2026-10-08 19:38:33 and 2026-10-09 04:32:07 UTC):
1. Codex's current-state documentation audit (done 2026-10-09).
2. A separately reviewed and released seven-path governance commit carrying this report, the manifest and five reviewer files.
3. After that commit passes its hooks and leaves a clean tree, its actual HEAD and tree become the final pin. `66ddabf` is not the pin.

**Commands.** The operator-approved Task 6 command substitution C1 applies to Stage B (Codex, 2026-10-09):
- `uv run --no-sync pytest --cov --cov-branch --cov-fail-under=0 --cov-report=term-missing --cov-report=json:tmp/coverage/full.json -v`
- `uv run --no-sync python -m tools.testing.coverage_products report --coverage-json tmp/coverage/full.json`

Default selection and full audit depth stay intact, with one serial coverage writer per checkout. `--cov-fail-under=0` waives neither the per-product floors nor the safety-module comparison. The Task 0 recorded-order gap predicate uses the same full Windows run; WSL gap performance stays informational.

**Checkouts.** Two independent clones, each detached at the pin with its own frozen environment, coverage data and run records:
- Windows: `C:\worktrees\optimus-cost-agent-worktrees\optimus-cost-agent-wt-claude-p1130f`;
- WSL: `/root/p1130-sb-t6-<UTC>`.

The Stage A Windows checkout exception does not extend to Stage B. The native Windows full run starts together with Fable's read-only final review; WSL runs after Windows finishes, with no overlap of the measured chains.

**Still UNKNOWN:** the base main-push and candidate Linux CI safety-module reports. There is no extra Windows base-only run.

**Not Stage B Task 6 evidence:** the commit-hook runs of `43eb190` and `66ddabf`; every checkpoint and pair run above; Stage A's results at `acc2a1c`.

## Stage B Task 6 — final gates at `3cece0a` (2026-10-09)

**Status: local evidence accepted** (Codex, 2026-10-09 07:24:20 UTC; see "Local acceptance" below). Every result in this section was measured at the pin `3cece0a887a80f2250cf1e720afcdd527136a412`, tree `fabb67208f0dbd2513a4c39618e82be05d14ab4a`. A later documentary commit that records these results is not itself the measured source.

### Pin: the seven-path governance commit

- **Commit:** `3cece0a887a80f2250cf1e720afcdd527136a412`, parent `66ddabfdf5bb3acccfffe39fa45f70b4b47924ad`, subject `docs: record Plan 11.30 Stage B delivery before final gates`.
- **Paths:** exactly the seven released documentary paths: this report, the manifest, `docs/README.md`, `docs/decisions/README.md`, `docs/decisions/ADR-016-test-cadence-product-coverage-and-staged-delivery.md`, `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` and `docs/superpowers/reviews/2026-10-05-plan-11-30-task3-codex-review.md`. The committed blobs equal the release table, and implementation, tests, configuration, lock and secrets baseline are unchanged from `66ddabf`.
- **Hooks** (2026-10-09 05:31:45Z–05:38:57Z): every applicable normal hook passed; YAML and TOML had no files.
- **Commit-profile hook:** `20261009T053202-52988-61dd41` verdict pass, obligation `wsl-platform: next checkpoint`. Its selected subrun `20261009T053233-48828-7c10ea` selected 4,567 nodes: **4,530 passed, 37 skipped**, exit 0. The record is valid, full-depth and ACTIVE, with qualification `parent=UNKNOWN:access_denied`. This is parent-HEAD hook evidence, distinct from the final runs below.

### Commands, checkouts and environments

**Commands.** Task 6 command substitution C1, run serially with one coverage writer per clone:
- `uv run --no-sync pytest --cov --cov-branch --cov-fail-under=0 --cov-report=term-missing --cov-report=json:tmp/coverage/full.json -v`
- `uv run --no-sync python -m tools.testing.coverage_products report --coverage-json tmp/coverage/full.json`

| | Native Windows | WSL |
|---|---|---|
| Independent clone | `C:\worktrees\optimus-cost-agent-worktrees\optimus-cost-agent-wt-claude-p1130f`, detached at the pin, clean; path budget 227 of 260 | `/root/p1130-sb-t6-20261009T063925`, detached at the pin, clean |
| Environment | the clone's own `.venv` from `uv sync --frozen` (dry-run: no changes; `uv lock --check` passes); Python 3.14.4, uv 0.11.29; pytest 9.1.1, pytest-cov 7.1.0, coverage 7.14.3 | its own frozen environment (no changes); Python 3.14.6, uv 0.11.31, Git 2.43; `TMPDIR` unset |
| `pyproject.toml` / `uv.lock` | `a95422bc…` / `a1a25b3a…` (equal to the delivered source) | same hashes |
| Time (UTC) | 05:40:53Z–06:36:25Z, together with Fable's read-only final review | 06:40:08Z–07:04:55Z, after Windows finished |

Common package versions match. The platform differences are Windows-only `colorama`, `pywin32`, `pywin32-ctypes` and `tzdata`, and Linux-only `jeepney` and `secretstorage`. The recorded Python and uv versions differ by platform, so no identical-interpreter claim is made. Both clones and the implementing lane were clean at the pin after the runs.

### Results (Codex's independent verification, 2026-10-09)

| Evidence | Native Windows | WSL |
|---|---|---|
| Full run | `20261009T054057-42656-acf1b7`: **5,533 passed, 40 skipped, 111 deselected**, exit 0 (3,325.50 s; 1 warning) | `20261009T064009-595-4738a3`: **5,398 passed, 175 skipped, 111 deselected**, exit 0 (1,376.16 s) |
| Selection, depth and validity | 5,573 selected; default selection, ACTIVE, COMPLETE, full audit depth, 0 collection and 0 recording errors; native job valid, guard `pytest_process_guard`, protection full; qualification `parent=not_found:ancestor_exited` | 5,573 selected; same selection and full depth; COMPLETE, ACTIVE; `native=unsupported`, `guard=unsupported_platform`, `parent=unsupported`, protection none |
| H5 budget | full depth, `h5.shutdown_schedule` 100/100 | full depth, 100/100 |
| Optimus production coverage (floor 80) | 15,076/16,659 statements + 3,466/4,466 branches = **87.772781 %**: PASS | 14,972/16,659 + 3,452/4,466 = **87.214201 %**: PASS |
| Model policy / Context Engine | absent on this source: N/A | N/A |
| A2A (informational, not enforced) | 3,824/5,312 + 972/1,698 = **68.416548 %** | 3,680/5,312 + 944/1,698 = **65.962910 %** |
| Coverage JSON SHA-256 | `887cb5918b1ce394634fdd207e2b2530e6b389dd4694d1f466abcc8ebfeb397b` | `87ca25f1c189eaa6cabec6693deb53793b4520d7af7250ec0c9d7e1594229190` |
| Coverage binding | automatic binding returns the full run; the explicit `--run-record` report agrees; corrected six-check binding receipt passes | automatic binding returns the full run; six-check binding receipt passes |
| Recorded-order inter-phase gap (Task 0 predicate) | 16,689 transitions; first and last deciles 1,668 each; medians 0.380500 / 0.381000 ms; ratio **1.001314: PASS**; 0 negative gaps | 16,544 transitions; deciles 1,654 each; 0.649000 / 0.591500 ms; ratio **0.911402**, informational only; **2 negative gaps**, retained and not clamped |
| Nodes over 2 s | 284, zero with an implicit (default-tier) classification | 76, zero with an implicit classification |

Products are measured as (covered statements + covered branches) / (statements + branches), unrounded.

- **Selected nodes.** The selected-node digest is `709277bb4db8b4c493a9be41f5e98fec551c0b0888cd744f075bb3de63b520d2` on both platforms. Raw phases cover exactly the selected nodes.
- **Recorder controls without a call phase.** Eight known intentional recorder-control nodes have passing setup and teardown and no call phase. The pytest summaries corroborate them. This is not a missing-call failure.
- **Coverage timestamps** are local-time data and must be interpreted on the measuring platform.
- **The existing runpy ACP warning** remains disclosed.
- **WSL qualifications** remain: unsupported protection and the guest clock. Its two negative gaps are not used for any Windows performance acceptance.

### Pin gates (implementing lane at the pin, identity unchanged)

- Changed-docs gate `pytest tests/unit/docs`, run `20261009T070554-35288-59b1d1`: **85 passed**. The record is active, default selection and COMPLETE, with parent UNKNOWN.
- `ruff check --no-cache .`: clean.
- `git diff --check 1c7be2d 3cece0a` and the worktree check: clean.
- The manifest parses, and the pin was unchanged.

Codex read and verified these retained gates; it did not rerun them. Its own fresh full-tree Ruff passes.

### Host load (not idle)

- **Windows** (30 s, read-only receipts): mean CPU 31.7 % before (Fable's read-only review active; Telegram and `TextInputHost` at about half a core each) and 19.2 % after.
- **WSL:** 30-second `/proc/loadavg` and top-process snapshots, load average about 0.22 before and about 0.90 after, on 12 CPUs.

Foreign load was recorded and not touched; no owned run overlapped. These runs are not idle-host measurements.

### xdist speed

These serial final runs **do not newly measure xdist speed**. Checkpoint D and the E-only pairs5 timing keep their own source-specific acceptance.

### Fable 5.1 final review: SOUND WITH AMENDMENTS

Fable's review (`fable-final-stageb.md`, SHA-256 `9bc401e86e7ff3e5a9adbeca4b34ab33163efd2a9f09b2672c661444d7dd0511`) found no defect in the delivered Stage B source and returned three Low amendments. Codex concurs.

1. Prove the measured-run binding instead of choosing the record by the most `nodes.jsonl` lines. **Applied:** `bind_check.py`, and the WSL script takes its record from the product report's automatic binding.
2. WSL ambient-load receipts. **Applied.**
3. Rename the manifest's `current_delivery.head` to `delivered_source_head`. **Applied in this composition**, with the measured final HEAD and tree named separately.

### Failed evidence collection (retained)

The initial Windows collection chose the run folder with the most `nodes.jsonl` lines. It copied `20261009T063630-33472-602c76`, which is the product report's later collection session, started 06:36:30Z, after the measured window ended at 06:36:25Z.
- **Retained as failed collection:** the misselected copy, its empty gap output (`gap-decile-misselected.json`) and the initial binding receipt (`bind-check.json`, 5 of 6 checks, incomplete because the product report does not print its run).
- **The correction:** the corrected copy is the actual full session `20261009T054057-42656-acf1b7`. Automatic and explicit binding, the selection, window, pin and exit checks, and the recomputed gap support acceptance. The automatic-binding receipt is `bind-check-2.json`.
- **No full test was rerun**, and no failed result is relabelled PASS.
- **No future excuse:** this does not excuse the heuristic for future gates.

### Local acceptance (Codex, 2026-10-09 07:24:20 UTC)

Codex accepted the local governance delivery and the Stage B Task 6 evidence at `3cece0a887a80f2250cf1e720afcdd527136a412`, tree `fabb67208f0dbd2513a4c39618e82be05d14ab4a`. It independently verified:
- both seals and all their members;
- the seven committed blobs, parent and subject;
- the normal-hook receipts;
- the raw records;
- the coverage arithmetic.

The acceptance is agent-selected technical acceptance under the settled operator delegation, not publication authority.

### Still open, stated separately from the local acceptance

*Annotation (2026-10-10): this list is historical. Under v5 the remote CI and safety comparison are I5 (the I1 base is accepted); see "Current delivery and status (2026-10-10)" and "I4 — exact-source finals at `ea88814e` (2026-10-10)".*

- **Remote Linux CI and the base/candidate safety-row comparison: UNKNOWN.** No extra Windows base-only full run is made; missing comparable reports stay UNKNOWN.
- **Complete Task 6 and plan closure: open.**
- **Push, PR, merge and cleanup are held**, including the two final clones. Services and paid calls are held too.
- Residual owners are unchanged (section "Stage B residuals and owners"). The registry archival stays 723 of 724 archived, PARTIAL/NON-PASSING.

### Receipts

- `plan-11-30-stageb-task6-final-evidence-20261009`: 69 members, seal `69c9ff9aca4d3fb2c8c0e7a7a7feffc78cbbaa26b546b7c5836ee5d4aa37cea1`.
- `plan-11-30-stageb-governance-commit-3cece0a-20261009`: 20 members, seal `1299d153cb3a80fe76589f6c1af69ba6d91a11b19b983e493782eba887753d0c`.
- Final packet `2026-10-09-claude-stageb-task6-final-packet-plan-11-30.md`: SHA-256 `e32e3137e82bd59d6611ae062260f0cce3c105c2a6e5842945ebf63a06b1cfe8`.

## I1 — coverage bootstrap on main via PR #279 and main-push baseline `4ed9b25` (2026-10-09)

**Status: accepted** (Codex, "I1 main-push baseline accepted — bounded I2 integration execution released", recorded 2026-10-09 17:40:21 UTC). Every figure in this section is from Codex's dated entries in the reviewer record, as imported in the 2026-10-10 snapshot (SHA-256 `d665e5b4…`). For the raw evidence see the packets `optimus-handoff/test-profiles-research/2026-10-09-claude-plan-11-30-i1-bootstrap-delivery-packet.md` and `2026-10-09-claude-plan-11-30-i1-main-push-baseline-packet.md`. This section was added on 2026-10-10 by the documentary results composition; it records earlier results and is not itself measured source.

### What I1 delivered

- **Approval:** the operator approved complete v5 (`149002fa5c61b366900c535bee883dd07289dc2317bdf4064cff2e20a7f7035e`) on 2026-10-09 (Codex record 13:28:24 UTC) with the direct reply "yes". v4 is superseded and archived byte-identically.
- **Scope:** three files on the separate branch `agent/claude/plan-11-30-coverage-bootstrap`: `tools/check_product_coverage.py`, `tests/unit/tools/test_check_product_coverage.py` and `.github/workflows/guardrails.yml`. The canonical gate exports the same measured dataset as coverage JSON with additive run receipts, and CI uploads it with the run-context records. Floors, selection and the existing hook were unchanged.
- **Local delivery:** commit `6f1935d9cdcf7dd2f8f52b3cbf7a724bfb6b4be5`, parent `f04c2cd`, tree `4b3eb5b701e3656e9303bc0308e7ae33dd93a978`; delivery packet `36e57206…`, seal `55e0d1b0…` (ten members). Full-hook run `20261009T150256-45424-5b5e41`: 6,883 selected; setup 6,863 passed/20 skipped; call 6,838 passed/19 skipped; no failed or errored phase. Six named recorder-lifecycle controls have a passing setup and no call phase; they are disclosed, not added to the call-pass total. Parent `UNKNOWN:access_denied`. This is pre-commit parent-HEAD evidence, not a CI baseline.
- **Publication:** under the operator's bootstrap publication grant ("Approved", recorded 2026-10-09 16:40:57 UTC), PR #279 merged normally at 17:10:43 UTC as `4ed9b252bc63a4ffd7179c34083af28566bee0a7` (parents `f04c2cd`, `6f1935d`; tree `4b3eb5b7…`). The grant covered the bootstrap only, not this profiles lane.

### Main-push baseline (accepted)

| Evidence | Value |
|---|---|
| CI run | main-push run 37964416192, job 113935048027, attempt 1, event push/main, success |
| Artifact | 11633307691 `product-coverage-4ed9b252bc63a4ffd7179c34083af28566bee0a7-1`, 247,813 bytes, digest `4dc03df9f2b6f24785d3c59b8044a041970b9721548b11022cb139d4973ce102` |
| Environment | coverage 7.14.3, CPython 3.14.8, linux, precision 0; the producer's UTC+00:00 offset is an observation/inference from timestamps, not a TZ environment dump |
| Coverage JSON | `47994ad93b111d172d292e22d3757c8faaafd67a7005d2d690eed7771ad83d66` |
| Floors (recomputed by Codex) | Optimus 88.83479389808504 %, Context Engine 95.92430858806405 %, model policy 96.98795180722891 %: all pass. Evidence Handoff 65.96291012838802 % and aggregate 84.02844334518473 % informational |
| Full session | exactly one of 27 copied records is eligible: `20261009T171130-2886-51e966`, 6,883 selected/111 deselected, COMPLETE, exit 0 |
| CI log | 6,687 passed/196 skipped/111 deselected/1 warning. No raw phases were uploaded, so there is no independent phase recount |

**Qualifications kept:**
- **Q-C1:** the base record has no `audit_depth` key; it qualifies only as `audit_depth_unrecorded:no-option-at-base`. The candidate must record full depth explicitly. There is no blanket missing-depth waiver.
- **Q-C3 with Q-C2:** the exact-base default universe is 6,883 selected IDs, digest `ba22b3a5c9cb0c080d065435fc4e2f1c10b3744b5c7f52a61efc36ebf29a968e`, proven in a WSL clone on CPython 3.14.6 against CI's 3.14.8. The patch difference is accepted for this selection proof only, with no timing or execution equivalence.
- Linux native/parent/guard unsupported and protection none are explicit, not Windows protection parity. The raw `.coverage` was not uploaded and is not independently rehashed.
- **Same-tree observation:** against the PR artifact, only `src/optimus/acp/lifecycle.py` differs (seven fewer covered lines and six fewer covered branches on the main-push run); all seven safety rows are structurally equal. This is observed variance, not a regression waiver; any affected I5 observation belongs to `P11-FEAT-TEST-PROFILES`.

Packet `3801b9e3dcaff6d1da0e23fe09f75ed235d94863993d52b468fb59087b24f1ac`; seal `22c75999585cd2876cb2581db721896e78376d60b254a1ca3dc325173725129e` (43 verified members). This run is the accepted base for the later I5 safety comparison.

## I2/I3 — integration candidate, I3 evidence and the integration merge `ea88814e` (2026-10-10)

**Status: accepted locally** (Codex: "I3 audits/stability accepted — remaining WSL platform evidence required", "I3 accepted — one normal-hook local integration merge attempt released" and "Integration delivery accepted — I4 exact-source finals released at ea88814e", all 2026-10-10). Figures are from the sealed packets in `C:\worktrees\optimus-cost-agent-worktrees\optimus-handoff\test-profiles-research\` and Codex's acceptance text. This section was added by the documentary results composition; it is not measured source.

### I2 candidate (staged, held for I3 evidence)

- I2 merged exact `4ed9b25` into the delivered lane with a non-auto-committing merge (`--no-commit --no-ff`), preserving both histories. Staged tree `63e6e6a02c89eaf1481114afdabe2022315cd985`; packet `83382531274d26a10a93ed0fac831bcbaa0c2ca726358ee594084d41f86c1ac0`, seal `db48ce2a97db3bd87960d83007d9fbcb06af9b24d17ac660f3b40b28db318f0a` (67 members).
- The integration keeps main's canonical checker, groups and precision 0 as the sole enforced floor, adds `coverage_products validate` after the canonical gate in CI, and renames the unpublished decision record ADR-020, with source S5.
- Codex's independent coverage-free validator controls: 169 passed, run `20261010T062320-44096-f66bbb`. Codex **held** the commit for missing I3 evidence (no code defect asserted) and authorized one Status-paragraph correction (F2), which produced staged tree `caffe9ad04b8a6b4dfa017e6e9bd5c474fac83d5`.

### I3 audits and stability on `caffe9ad` (accepted)

Packet `2026-10-10-claude-plan-11-30-i3-evidence-packet.md` (`7dbf7eeaae40da791647dd3ee2a6fa46c373773fbc398e1c5587558b20ce70bb`); sealed `plan-11-30-i3-evidence-caffe9ad-20261010`, seal `a4f4da81c55695b8f857eba4b10d90423ca2048d6e006ffe459dac3f6325cba7` (44 members). The selection is the runner's own checkpoint selection (`--base 26bd667`): 381 concurrency nodes (`c154b0f3…`) and 78 full-depth audit-current nodes (`fa75a52e…`). The broad 7,323-node subrun was not run, per Codex's ruling.

| Platform | Run | Result |
|---|---|---|
| Windows, CPython 3.14.4 | full-depth current audit `20261010T123038-22600-5ec19e` | 78 passed / 234 phases, exit 0, ACTIVE, COMPLETE |
| Windows | three concurrency repeats `…123041-46288-5801aa`, `…123133-5128-14c30e`, `…123219-60892-b201ff` | each 373 passed and 8 skipped (runner-only probe plants) / 1,143 phases, exit 0; all three lie wholly inside the audit's phases (Codex margins 1.445/782.910 s, 53.825/730.676 s and 99.578/685.050 s) |
| WSL, CPython 3.14.6 | full-depth current audit `20261010T124627-486-9fc7d2` | 78 passed / 234 phases, exit 0, COMPLETE |
| WSL | concurrency once, serially, no load: `20261010T125437-7438-09cbd8` | 373 passed, 8 skipped / 1,143 phases, exit 0 |

Qualifications: Windows `parent=not_found:ancestor_exited`; WSL POSIX `native`, `guard` and `parent` unsupported; the selection record's `index_sha256` differs between Git 2.56 and Git 2.43 (same tree). No host-idle claim. Fable 5.1: SOUND WITH AMENDMENTS (applied as wording).

**Disclosed slips (retained):**
1. An intended dry run was launched without `--dry-run`: the real Windows I3 run started at 12:30:37Z in a folder named `win-dry`. The folder is kept unrenamed; Codex ruled that the name does not make the executed run a dry run.
2. A driver (`i3_subruns.py`) replaced `run_profile --profile checkpoint`, because the runner cannot skip its broad subrun. Codex reviewed the driver's use of the existing selection, overlap and validity functions and accepted it for these bounded subruns.
3. An inline WSL `bash -c` record copy expanded its variables empty. It was redone by a script, with a stray-file receipt.

### I3 WSL platform remainder on `9048bc8d` (accepted)

Packet `2026-10-10-claude-plan-11-30-i3b-platform-remainder-packet.md` (`d5c175a3a1ce05e0bb1fee81e61c760c548832229a3049b1df2da04d70fbb6d1`); sealed `plan-11-30-i3b-platform-remainder-9048bc8d-20261010`, seal `1715bba2d24dc5cabc838d0dd81335d3841b1f676284f941c6b17af9d7e8f8a3` (43 members).

- **Platform set:** 1,629 checkpoint-selected platform nodes (`d79185015cc55b96a2fae2b6fd3d34fab82967e566cc3b73fba461672932c9ed`): 1,627 visible plus two credential-URI nodes with null sanitized labels, bound by digest to the unsanitized list. 51 had a passed call in the accepted WSL concurrency run (`4852c469…`); the remainder is 1,578 (`3a6ec98f…`).
- **Run:** `20261010T143117-430-24b184`, once, serially, at full depth, in the unchanged frozen I3 WSL clone: pytest 1,410 passed, 168 skipped, exit 0. Raw phases (4,559): 1,402 call-passed, 168 skipped and 8 `test_run_context_lifecycle` nodes with no outer call entry (those tests swap `run_context._current`); no failed or errored phase. Codex reviewed all 28 skip reasons: Windows-specific or capability skips, no missing dependency.
- **Accounting:** 1,461 passed, 168 legitimate platform skips, 0 failed, errored or unrun. Codex discharged the I3 candidate's attributed WSL platform obligation on this basis.
- **Reviewer import (documentary only):** the I3 candidate imported Codex's review-file snapshot `039d6c1b…` (+23/−0). Code equality from `caffe9ad` to `9048bc8d`: only the review file differs, and the `ls-tree` digest over `src tools tests pyproject.toml uv.lock .github` is `b651d85b…` on both trees.
- Fable 5.1: SOUND (two Minor and two Low findings, applied as wording).

### The integration merge commit `ea88814e` (accepted)

Packet `2026-10-10-claude-plan-11-30-i2-merge-commit-delivery-packet.md` (`0b05061da1d7094e4b3c301945aeffb47001c1c8cd545e3b4d6b89b14d390e5c`); sealed `plan-11-30-i2-merge-commit-attempt1-20261010`, seal `5d97454b77f3e8b613eae47138f1cd3677adadef8a58a6081096aeada321c69b` (20 members).

| Item | Value |
|---|---|
| Commit | `ea88814e4187c81c3a9781669bb2c17a71546949`: one attempt, normal hooks, no SKIP or `--no-verify` |
| Parents (ordered) / tree | `26bd667feb0ad9c9287260936165d029574ea1d5` then `4ed9b252bc63a4ffd7179c34083af28566bee0a7` / `9048bc8dead2c5b3633703f04a2c2232ea2d29b6` |
| Subject | `Merge main 4ed9b25 into the Plan 11.30 profiles lane: one canonical coverage gate, validity layer, ADR-020` |
| Committed blobs | all 1,396 equal the sealed pre-commit index; clean status; remote main still `4ed9b25` |
| Hook window | 14:52:14Z–15:32:16Z; every hook passed |
| Commit-profile subrun `selected` | `20261010T145302-43252-c315b8`: 7,323 selected, full depth, 21,940 phases; 7,275 call-passed, 40 skipped, 8 lifecycle nodes with no outer call entry, 0 failed or errored; `parent=not_found:ancestor_exited` |
| Commit-profile subrun `audit-current` | `20261010T152541-55856-1fb464`: 78 call-passed / 234 phases at **quick** depth (the commit profile's design); not a full-depth audit claim |
| Forward obligation | `wsl-platform: next checkpoint`, recorded by the hook and not discharged in advance (discharged at I4, below) |

The accepted I3 audits, stability repeats and WSL platform runs remain bound to the tested trees `caffe9ad` and `9048bc8d`, which are code-equal to the committed tree. They are not relabelled as committed-head runs.

## I4 — exact-source finals at `ea88814e` (2026-10-10)

**Status: accepted** (Codex, "I4 accepted at ea88814e — bounded reader correction and results composition released", 2026-10-10). Every result here was measured at commit `ea88814e4187c81c3a9781669bb2c17a71546949`, tree `9048bc8dead2c5b3633703f04a2c2232ea2d29b6`. This section, and any later commit that records it, is a documentary-only descendant, not measured source. The acceptance is stated separately from the pending S1 correction and from I5 (see "Still open" below).

Packet `2026-10-10-claude-plan-11-30-i4-finals-packet.md` (`3cdc7f1eaf9252cc067ffebb0d4c880cccfb8ba34faf0fc8ca604ec5a7f8fef6`); sealed `plan-11-30-i4-finals-ea88814e-20261010`, seal `61e3ad78a8c6115937e72f375b7c4cb10b556bfa5004b47b4a283956b53d47f5` (75 members); summary `i4-final-summary.md` (`3d82641f…`).

### Pin, commands and environments

- **Identities**, equal in both clones before, after re-pin and after the run: `pyproject.toml` `86963ae6…`, `uv.lock` `b0aa71b6…`, `tools/product-coverage-groups.json` `55278b5e…`, `tests/profiles.toml` `1b656b4a…`, src/tools/tests `ls-tree` digest `771a6fd5…`. All 1,396 tracked files are byte-identical across the clones. Each clone was clean, pinned before environment setup and re-pinned after it; the frozen `uv sync --frozen --all-extras` dry run reported no changes.
- **Commands:** exactly the approved v5 I4 sequence. First the canonical gate, `uv run --no-sync python tools/check_product_coverage.py --run-full-suite --groups tools/product-coverage-groups.json --report-json tmp/coverage/product-coverage-report.json --coverage-json tmp/coverage/coverage.json`; then `uv run --no-sync python -m tools.testing.coverage_products validate --coverage-json tmp/coverage/coverage.json --gate-report tmp/coverage/product-coverage-report.json --run-record <the identified full-session run.json>`, on the producing machine.
- **Windows:** independent clone `C:\worktrees\optimus-cost-agent-worktrees\optimus-cost-agent-wt-claude-p1130g`; CPython 3.14.4, pytest 9.1.1, pytest-cov 7.1.0, coverage 7.14.3, uv 0.11.29, Git 2.56.0; path budget 227/260.
- **WSL:** independent clone `/root/p1130-i4-20261010T165139`, started only after Windows wrote `DONE`; CPython 3.14.6, pytest 9.1.1, pytest-cov 7.1.0, coverage 7.14.3. Windows 3.14.4 versus WSL 3.14.6 is a patch-level difference; the CI-candidate comparison belongs to I5.

### Results (Codex's independent recount)

| Evidence | Native Windows | WSL |
|---|---|---|
| Canonical gate | exit 0, 15:59:34–16:49:50Z; pytest 7,364 passed, 40 skipped, 111 deselected (2,998.8 s) | exit 0, 16:52:24–17:17:53Z; pytest 7,228 passed, 176 skipped, 111 deselected (1,447.4 s) |
| Full session | `20261010T155938-55592-da98bc` | `20261010T165225-624-76badd` |
| Raw phases (Codex) | 7,356 call-passed plus 8 recorder-test no-outer-call passes, 40 skipped, 0 failed or errored; 7,404 selected | 7,220 call-passed plus the same 8, 176 skipped, 0 failed or errored; 7,404 selected |
| Record | terminal ACTIVE, `default_selection`, COMPLETE, full depth, exit 0; native valid, guard full; `parent=not_found:ancestor_exited` | terminal ACTIVE, `default_selection`, COMPLETE, full depth, exit 0; `native=unsupported`, `guard=unsupported_platform`, `parent=unsupported` |
| Exactly one eligible full record | 1 of 101 records (99 at identification; validate's collection record and the docs-gate run came later) | 1 of 68 (67 at identification) |
| `validate` | exit 0, "full-run validity established" | exit 0, "full-run validity established" |
| Optimus (floor 80, compared at precision 0) | **89.37033430704317 %** (89): PASS | **88.95245050308341 %** (89): PASS |
| Context Engine (floor 80) | **95.92430858806405 %** (96): PASS | **95.92430858806405 %** (96): PASS |
| Model policy (floor 80) | **96.98795180722891 %** (97): PASS | **96.98795180722891 %** (97): PASS |
| Evidence Handoff (informational) | 68.41654778887303 % | 65.96291012838802 % |
| Aggregate (informational) | 84.9683 % (85), as printed by the gate | 84.1181 % (84), as printed by the gate |
| Coverage JSON | `882bd6430897199b71d24bd2a8c3d39a004904bf36a14ecadcf021c3cb0418b6` | `5937a133687b296a0a2353bdb1f10a05c27e1fc6b1f897c7e679a6e1f3bc458c` |
| `.coverage` (post-run receipt) | `9560eda2fff7f71ac4ce33e468ddf348da857aa8c29fd9b66e3d31e2b987ad05` | `4055b52daae0f1f901c20f10476bf88026072f8a5228442c8eb92ec520883224` |
| Gate report / `.run.json` | `7452e58a…` / `6c1b802b…` | `d0742052…` / `105a4215…` |
| Task 0 gap predicate | **PASS**: N 22,182, k 2,218, first/last-decile medians 0.327/0.328 ms, ratio **1.003058102837912**, 0 negative gaps | informational only: N 22,036, k 2,203, 0.239/0.236 ms, ratio 0.9874476981521637, **2 negative gaps** |

Codex independently replayed record validity and the gate-window/head/config/lock/universe matching over the preserved clones. It rehashed both `.coverage` files against the gate receipts and both JSON exports against the gate reports; the embedded run receipts equal the separately retained records. The universe digest is `7145df24…`.

### Qualifications (all kept)

- **Recorder-test no-call 8:** in each run, eight `test_run_context_lifecycle` nodes pass with no outer call entry, because they swap `run_context._current`. They are not counted as independently recorded call passes.
- **Capability labels:** Windows `parent=not_found:ancestor_exited`; WSL the weaker POSIX labels.
- **WSL negative gaps:** two call→teardown gaps of one node (−11.8 ms and −205.5 ms). Cause: `run_context.py` takes `at` from the wall clock and `seconds` from `perf_counter`, and WSL2 stepped its wall clock (the same PIDs' `ps lstart` shifted by +73 s between the load receipts). The WSL gap is informational, and no WSL timing equivalence is asserted.
- **Plan 12 overlap during the Windows run (Codex's disposition):** the Plan 12 cp4 lane was idle at launch, then started a live ACP qualification session and a gateway on 127.0.0.1:8765 at about 16:13Z; both were still running at the after-receipt at 16:50Z. Codex accepted the Windows run with this disclosure: the overlap is neither owned stray load nor an overlap of the two I4 timed runs. The start receipt does not prove absence throughout the run, and the earlier statement is corrected. The retained load receipts (window mean 15.4 % against 14.5 % before), the passing Windows gap predicate, valid protection and zero test failures support acceptance, and the code's only port-8765 probe is replaced in every test that reaches it. There is no host-idle or general no-interference claim, no foreign process control and no speed-equivalence conclusion. No rerun was required.
- **Interpreters:** Windows CPython 3.14.4 versus WSL 3.14.6.
- **Skip reasons:** the canonical `-q` command does not print `-rs`. The platform character of the 168 WSL platform skips rests on Codex's I3b review of the reasons for the identical scope.
- **Extra PASSIVE collection records** from the finals' `_bound_record` identification and from `validate` are not evidence; eligibility filters them out.
- **Uniqueness (S4):** the named-record `--run-record` path does not itself establish uniqueness. For these finals, the separate exactly-one receipts (`full-session.txt`) and Codex's replay discharge it.
- **WSL host load:** about 0.38 before and about 1.0 after; not idle.

### Forward WSL platform obligation (discharged at this pin)

Codex matched the exact 1,629-ID platform list (`d7918501…`) to the WSL full run's raw phases: 1,453 call-passed, 8 qualified recorder-test passes, 168 capability skips (167 at setup, 1 at call), 0 missing or failed. The I3 commit's forward `wsl-platform: next checkpoint` obligation is **discharged at `ea88814e`**. The discharge is source-specific, not advance clearance for later commits.

### Fresh checks at the pin and reviews

- In the clean Windows clone: `ruff check --no-cache .` passes; the docs gate has 86 passed; `local_secret_scan` over `src` and every file changed against main exits 0; `git diff --check` against `4ed9b25` and against `26bd667` is clean.
- Fable 5.1 final source review (`fable-final-i4.md`, `8ab8df42…`): SOUND WITH AMENDMENTS. Fable 5.1 evidence recount (`fable-i4-recount.md`, `61352400…`): SOUND WITH AMENDMENTS, documentary only; F1–F4 are applied as disclosures.

### Source dispositions (Codex, 2026-10-10)

- **S1 (required before I5):** `compare` loaded each record with plain JSON, bypassing the run-context schema reader; Codex reproduced the violation with an `unexpected_field` record. The narrow test-first correction must read both sides through the existing `records.read_record`, with a labelled unreadable-record refusal. The defect is not reachable in I4, which runs `validate`. Once corrected, a missing record file is refused like any other unreadable record: exit 1 (incomparable) with the labelled, path-free side message, where it was previously exit 2, an input failure naming the path.
- **S2:** the workflow comment must say that collection-only records can be uploaded after a pre-pytest gate failure but are not eligible full evidence.
- **S3:** no new lookup or logging feature now. Optional, more detailed rejection logging stays with `P11-FEAT-TEST-PROFILES`.
- **S4:** no source change. Keep the explicit exactly-one receipt for named-record use; CI's automatic binding keeps its exactly-one refusal.

### Still open, stated separately from the `ea88814e` acceptance

- **S1 corrected-source delivery: pending.** The correction, with the S2 comment, is prepared and pending Fable then Codex review. It then needs a separately released local commit that becomes a newly reviewed candidate pin, with its own verification disposition, before I5. The `ea88814e` exact-source final claim does not transfer to it, and no source-equivalence waiver is granted.
  - *Superseded (2026-10-11); the line above is kept as written:* S1 was delivered as local commit `343b233a` (single parent `ea88814e`, tree `8a39467d`) and accepted, and the corrected-source I4 finals at that commit (pin C) were accepted; see "S1 delivery at `343b233a` (2026-10-11)" and "Corrected-source I4 finals at C `343b233a` (2026-10-11)". The `ea88814e` finals remain bound to `ea88814e`.
- **I5: held.** Publication, push and PR of the lane; candidate Linux CI and the base/candidate safety-row comparison against the accepted I1 base; merge to main.
- **Closure and cleanup: held**, including the I4 clones. Residual owners are unchanged.

## S1 delivery at `343b233a` (2026-10-11)

**Status: accepted** (Codex, "S1 delivery and corrected-source I4 finals accepted — documentary composition released", recorded 2026-10-11), with the explicit receipt defect below. The release was "S1/results batch accepted — one local commit attempt and conditional new-pin finals released" (2026-10-11): staged batch `8a39467d` on parent `ea88814e`, packet `ec9181e9b784839afedc1c8e68eb8289e59db9ec3d2c5202bcf71d2e44467d97`, seal `efc70dfd8e510e3284446be128861e642313a1a51e669a131cd364cdce5257e4` (29 members). This section was added by the 2026-10-11 documentary composition; it is not measured source.

Commit receipts: sealed `plan-11-30-s1-commit-attempt1-20261011` in `C:\worktrees\optimus-cost-agent-worktrees\optimus-handoff\test-profiles-research\`, seal `9df84d166cf877b4cc2e508a1984111a28e3c940030ac450b1dc26213a53d95c` (19 members), which Codex verified independently.

### What the commit delivers

- **S1:** `compare` now reads the base and candidate records through the existing `records.read_record`. An unreadable record on either side gets a labelled, path-free refusal. A missing record file is now exit 1 (incomparable), where it was previously exit 2 (an input failure naming the path); the commit message and this report disclose that change.
- **S1 tests:** two positive controls through the real CLI and six RED controls (each side × unexpected field, malformed, oversized). These 8 new nodes enter the default selection, so the universe at this commit is 7,412 (I4's 7,404 plus 8).
- **S2:** the `.github/workflows/guardrails.yml` comment now says that collection-only records can be uploaded after a pre-pytest gate failure but are not eligible full evidence.
- **The I4 results composition** (report, manifest, ADR-020, indices, backlog and the 2026-10-10 review snapshot `d665e5b4…`).

### The commit

| Item | Value |
|---|---|
| Commit | `343b233ab7b470690eb21fe20c4662460694955c`: one attempt, normal hooks, no SKIP, `--no-verify` or retry |
| Parent / tree | single parent `ea88814e4187c81c3a9781669bb2c17a71546949` / `8a39467d4607f29f1905a55e62844865f6f76fc3` |
| Subject | `fix(coverage): read compare's run records through the run-context reader; record I4 results` |
| Paths | exactly the 10 authorized paths, each blob equal to Codex's SHA-256 table: `.github/workflows/guardrails.yml`, `docs/README.md`, ADR-020, `docs/decisions/README.md`, the backlog, the review file, this report, the manifest, `tests/unit/tools/test_coverage_products.py` and `tools/testing/coverage_products.py` |
| Committed blobs | all 1,396 equal the staged index; status clean afterwards; remote main still `4ed9b25` |
| Message | the commit object's message bytes equal the sealed `msg-s1.txt` (`f433935b2e8e389b0768cac93cf022d74aa3e5579ac438dca57d3c50308f5c9a`) |
| Committer date / hooks | 2026-10-11T05:08:43Z; all ten hooks passed (the toml hook was skipped: no files), 05:08:43–05:22:04Z |

### The commit-profile hook run (not a final)

- **Run** `20261011T050931-61376-f46efe`, 05:09:31–05:22:02Z, in the lane worktree: terminal ACTIVE, `default_selection`, COMPLETE, exit 0, 20,643 phases; native job valid, guard full; qualification `parent=not_found:ancestor_exited`. Codex replayed it independently.
- **Selection:** 6,890 of the 7,412 collected nodes (522 deselected by the profile), chosen mainly by `fallback:broad` (5,242 nodes, from the workflow path and the manifest). Coverage-free.
- **Raw phases:** 6,844 call-passed, 38 skipped, 8 qualified recorder-test passes without an outer call (the same eight `test_run_context_lifecycle` nodes), 0 failed. The pytest total is 6,852 passed.
- **Not a final full suite.** The selection omits `audit-current` (selection `audit_depth` `none`), so the record's default `audit_depth: full` is the pytest option's default and proves no audit execution. It is not eligible as a final: 6,890 is not the 7,412 universe, it ran in the lane rather than a clean clone, and it produced no coverage dataset.
- **Forward obligation:** the hook recorded `wsl-platform: next checkpoint` (a `fallback:broad` platform trigger under the commit profile). It was discharged at C only; see the next section.
- The hook created 62 new run folders in the lane's `tmp/test-runs`; they are attributable by run ID and `worktree`, and are in neither finals clone.

### Disclosures and Codex's rulings (2026-10-11)

- **Missing pre-attempt owned-process receipt.** The release required a check for owned stray processes before the attempt. `prerequisites.txt` (05:08:39Z) and the commit script receipt every other prerequisite, but no process listing was retained. Claude's session-only claim (an in-session check at about 05:08Z: 0 lane-owned processes, 6 foreign Plan 12 processes, CPU 19 %) **remains unverified by retained evidence**. Codex accepted this completed delivery with that explicit receipt defect; the prerequisite checklist is not fully evidenced. The exact staged and committed source, the valid hook records and the separately receipted final-run process checks support acceptance, but the later check (the 05:24Z Windows load receipt) does not prove earlier absence. There is no retrospective receipt, new pin or rerun; the check is to be retained on future attempts.
- **Commit message check.** The commit script's raw `%B` comparison printed `message_bytes_equal=no`; that was a formatting false negative. The commit-object message bytes are independently equal to `msg-s1.txt` (Fable by `cmp`; Codex independently). Both statements are kept together.

## Corrected-source I4 finals at C `343b233a` (2026-10-11)

**Status: accepted** (Codex, "S1 delivery and corrected-source I4 finals accepted — documentary composition released", recorded 2026-10-11). Every result here was measured at the new measurement pin C, commit `343b233ab7b470690eb21fe20c4662460694955c`, tree `8a39467d4607f29f1905a55e62844865f6f76fc3`. The old acceptance pin `ea88814e` and its finals (section "I4 — exact-source finals at `ea88814e` (2026-10-10)") stay as recorded and bound to that pin. This section, and the commit that records it, is a third, documentary-only HEAD; it is not measured. The finals were repeated at the corrected source with no equivalence waiver.

Packet `2026-10-11-claude-plan-11-30-i4c-finals-packet.md` (`861236fec30ef7b700b556056d25a99f8c3a991e15da650875081744d0d30e63`); sealed `plan-11-30-i4c-finals-343b233a-20261011`, seal `b47f17490914f24e44b5ed27169e602ce5f69056fe69212e1cedace30ca19ba3` (76 members); summary `i4c-final-summary.md` (`fc2e4153…`).

### Pin, commands and environments

- **Identities**, equal in both clones before, after re-pin and after the run: `pyproject.toml` `86963ae6…`, `uv.lock` `b0aa71b6…`, `tools/product-coverage-groups.json` `55278b5e…`, `tests/profiles.toml` `1b656b4a…` (all equal to I4's), and src/tools/tests `ls-tree` digest `a827f630…` (it differs from I4's `771a6fd5…` only by the two changed source paths). All 1,396 tracked files are byte-identical across the clones; Codex hashed every Windows clone file against the committed blobs and the WSL clone.
- **Commands:** exactly the approved v5 I4 sequence, as at I4: the canonical gate `uv run --no-sync python tools/check_product_coverage.py --run-full-suite --groups tools/product-coverage-groups.json --report-json tmp/coverage/product-coverage-report.json --coverage-json tmp/coverage/coverage.json`, then `uv run --no-sync python -m tools.testing.coverage_products validate --coverage-json tmp/coverage/coverage.json --gate-report tmp/coverage/product-coverage-report.json --run-record <the identified full-session run.json>`, on each producing machine.
- **Windows:** independent clone `C:\worktrees\optimus-cost-agent-worktrees\optimus-cost-agent-wt-claude-p1130h`; CPython 3.14.4, pytest 9.1.1, pytest-cov 7.1.0, coverage 7.14.3, uv 0.11.29, Git 2.56.0; path budget 227/260.
- **WSL:** independent clone `/root/p1130-i4c-20261011T061711`, started only after Windows wrote `DONE`; CPython 3.14.6, pytest 9.1.1, pytest-cov 7.1.0, coverage 7.14.3. The two timed runs did not overlap. The I4 clones (`…-p1130g` at `ea88814e`, `/root/p1130-i4-20261010T165139`) remain intact, so old and new records stay separately attributable.

### Results (sealed receipts, Fable's sealed recount and Codex's independent verification)

| Evidence | Native Windows | WSL |
|---|---|---|
| Canonical gate | exit 0, 05:24:41–06:15:32Z; pytest 7,372 passed, 40 skipped, 111 deselected (3,032.7 s) | exit 0, 06:17:52–06:41:36Z; pytest 7,236 passed, 176 skipped, 111 deselected (1,310.0 s) |
| Full session | `20261011T052446-4340-f0f821` | `20261011T061753-630-549fc3` |
| Raw phases | 7,364 call-passed plus 8 qualified recorder-test passes, 40 skipped, 0 failed, errored or missing | 7,228 call-passed plus the same 8, 176 skipped, 0 failed, errored or missing |
| Universe | **7,412** selected nodes, digest `a1006e75018a18b51783e94f83b82068bffcd2fae3f92670cba2f7ec36fa926a` | same |
| Record | terminal ACTIVE, `default_selection`, COMPLETE, full depth, exit 0; `parent=not_found:ancestor_exited` | terminal ACTIVE, `default_selection`, COMPLETE, full depth, exit 0; `native=unsupported`, `guard=unsupported_platform`, `parent=unsupported` |
| Exactly one eligible full record | 1 of 99 at identification (`full-session.txt`); still 1 of 101 at Fable's recount | 1 of 67 at identification; still 1 of 68 at recount |
| `validate` | exit 0, "full-run validity established" | exit 0, "full-run validity established" |
| Optimus (floor 80, compared at precision 0) | **89.45147679324894 %** (89): PASS | **88.8834793898085 %** (89): PASS |
| Context Engine (floor 80) | **95.92430858806405 %** (96): PASS | **95.92430858806405 %** (96): PASS |
| Model policy (floor 80) | **96.98795180722891 %** (97): PASS | **96.98795180722891 %** (97): PASS |
| Evidence Handoff (informational) | 68.41654778887303 % | 65.96291012838802 % |
| Aggregate (informational) | 85.0301437625599 % (85) | 84.06554336064306 % (84) |
| Coverage JSON | `1b800cc6b5388cd744d2f81bb692f170ff08676bb79bfe7db2302883c6e7693a` | `934d2043e77e5d8df637baf65350bbb8a35510c728cbb8b24668180a5627e74a` |
| `.coverage` (post-run receipt) | `0d81e1dc7fa05ad49cb98207654a0ab8129b02a2287a05c5f6cf93257c4f0c4a` | `2156e95ce4548b91be087b7d4a700fda2581338e9b912ab1cd72f0904bfaade1` |
| Gate report / `.run.json` | `8c0d1466…` / `84b94964…` | `486bcaa6…` / `1a6e0063…` |
| Task 0 gap predicate | **PASS**: N 22,206, k 2,220, first/last-decile medians 0.322/0.311 ms, ratio **0.9658385086098185**, 0 negative gaps | informational only: N 22,060, k 2,206, 0.232/0.200 ms, ratio 0.8599137931489925, **3 negative gaps** (wall-clock steps) |

Codex independently verified record validity, the raw outcomes and the gate receipts binding the clean unchanged head and tree, config, lock, groups, coverage JSON and raw data, and recomputed the floors and both gap ratios. The gate windows do not overlap. Codex's replay across the retained clone records finds exactly one matching full session per platform; named-record validation alone remains insufficient to prove uniqueness.

### Qualifications (all kept)

- **Recorder-test no-call 8:** in each run, eight `test_run_context_lifecycle` nodes pass with no outer call entry, because they swap `run_context._current`. They are not counted as independently recorded call passes.
- **Capability labels:** Windows `parent=not_found:ancestor_exited`; WSL the weaker POSIX labels.
- **WSL negative gaps:** three call→teardown gaps, one in each of three nodes (−4.8 ms, −334.1 ms and −388.5 ms). As at I4, `at` comes from the wall clock and `seconds` from `perf_counter`, and WSL2 stepped its wall clock during the run (the same PIDs' `STARTED` shifted from 06:17:07 to 06:18:58 between the load receipts). The WSL gap is informational; no WSL timing equivalence is asserted.
- **Interpreters:** Windows CPython 3.14.4 versus WSL 3.14.6.
- **Skip reasons:** the canonical `-q` command does not print `-rs`. The platform character of the 168 WSL platform skips rests on the accepted I3b review of the reasons for the identical scope.
- **Extra PASSIVE collection records** from the `_bound_record` identification and from `validate` are not evidence; eligibility filters them out.
- **Script header:** `win_i4c.sh` line 2 still cites the `ea88814e` release; attribution is exact through the pin argument, the hard-coded tree and the identity receipts.
- **WSL host load:** 0.40 before and about 0.87 after; not idle.

### Forward WSL platform obligation (discharged at C only)

Codex independently matched the retained 1,629 platform IDs (`d79185015cc55b96a2fae2b6fd3d34fab82967e566cc3b73fba461672932c9ed`; `tests/profiles.toml` is unchanged and none of the 8 new nodes is platform-tagged) to the WSL full run's raw phases: **1,453 call-passed, 8 qualified recorder-test passes, 168 skips (167 at setup, 1 at call), 0 missing or failed.** S1's forward `wsl-platform: next checkpoint` obligation is **discharged at `343b233a` only**. The skip interpretation keeps the accepted identical-scope I3b reason qualification, because the canonical finals omit `-rs`. There is no advance clearance for later source commits.

### Disclosure rulings (Codex, 2026-10-11)

- **Plan 12 load at C: accepted with qualification, no rerun.** The Plan 12 cp4 lane's ACP qualification session and its gateway on 127.0.0.1:8765 (six Python processes, started about 16:13Z on 2026-10-10) were already running when the Windows final started; they were not owned by this lane and were not touched. The endpoint load receipts (05:24:09Z before, 06:16:08Z after) show the same foreign processes. Their presence throughout the run is *inferred* from their start times and the endpoint receipts; it was not continuously observed. Their sampled CPU rates stayed below the per-process threshold (the window mean was 35.6 % before, from a 74 % opening spike, and 8.7 % after). The host is not claimed idle. The Windows gap predicate passes and no phase failed. There is no foreign-process control and no timing-equivalence claim.
- **Missing pre-attempt owned-process receipt:** see "S1 delivery at `343b233a` (2026-10-11)". The session-only claim remains unverified by retained evidence; the delivery is accepted with that explicit receipt defect; the prerequisite checklist is not called fully evidenced; there is no retrospective receipt.
- **Static checks at C: an exit-code receipt only.** `static-at-pin-c.txt` (06:42:55–06:43:32Z, in the clean Windows clone at `343b233a`) records exit 0 for Ruff, "86 passed" with exit 0 for the docs controls, exit 0 for the secret scan, exit 0 for both diff checks, and clone status 0 before and after, but not the command lines. The reconstructed commands are: `ruff check --no-cache .`; the coverage-free docs controls (`pytest --no-cov -q -p no:cacheprovider tests/unit/docs`; run `20261011T064258-44028-1e92bd`, 86 selected); the local secret scan (`local_secret_scan` over `src` plus the files changed against main `4ed9b25`); and `git diff --check` against main `4ed9b25` and against the parent `ea88814e`. This reconstruction is **not** a new executed-command receipt.
- **Commit message check:** the raw `%B` comparison was a false negative; the commit-object bytes are independently equal (section "S1 delivery at `343b233a` (2026-10-11)").
- **Two launcher slips while preparing, retained with no results claimed from them.** A bare `python` call (the PyManager launcher in Git Bash) tried to launch a script by its shebang; bash crashed at startup and nothing ran. A later `python - … || …` call hung on stdin and was stopped, leaving no process. The scripts were then edited with an explicit interpreter.

### Reviews

- Fable 5.1 source review at C (`fable-final-i4c.md`, `4cbba2d5…`): SOUND WITH AMENDMENTS; no source defect. R-A (the Plan 12 disclosure) and R-D (the 7,412 universe) are carried above.
- Fable 5.1 recount (`fable-i4c-recount.md`, `af02ae81…`): SOUND WITH AMENDMENTS, documentary only. F1 (the missing pre-attempt receipt) and F2 (the static-check commands) are disclosed above; F3 to F9 are kept as qualifications.
- Codex (2026-10-11): accepted the S1 delivery and the finals at C; Fable's source review and recount stand as SOUND WITH AMENDMENTS, with the documentary qualifications above preserved.

### Still open, stated separately from the C acceptance

All held:
1. **This documentary delivery**, under its own reviewed commit grant (Fable then Codex review of the exact final staged paths, tree and hashes first).
2. **Concrete operator push/PR authority** for the lane after latest-main reconciliation. The bootstrap publication approval does not cover this branch.
3. **Actual Linux CI and artifact origin**, and the seven-module safety comparison against the accepted I1 baseline.
4. **Merge to main, closure, archival and cleanup**, including the I4 and C final clones. Residual owners are unchanged.
   - *Superseded in part (2026-10-11); the list above is kept as written:*
     - Item 1 was delivered as documentary commit `281f8ce7` and accepted.
     - Item 2 was granted and executed: the branch was pushed at `281f8ce7` and PR #280 opened.
     - Item 3 was accepted at the PR merge ref `1946713e` (guardrails run `38125646691`; all seven safety rows identical to the I1 base).
     - Item 4 stays held, together with this D3 documentary commit and any update of the published branch.

     See "D2 delivery and WSL discharge (2026-10-11)", "I5 publication and PR-body correction (2026-10-11)" and "I5 candidate CI and seven-module safety comparison (2026-10-11)" below.

## D2 delivery and WSL discharge (2026-10-11)

**Status: accepted** (Codex, ["D2 local delivery accepted — bounded WSL CI-parity remainder released"](../docs/superpowers/reviews/2026-10-05-plan-11-30-task3-codex-review.md#d2-local-delivery-accepted--bounded-wsl-ci-parity-remainder-released), recorded 2026-10-11), and D2's forward WSL platform obligation **discharged at D2** (Codex, ["D2 WSL obligation discharged — publication readiness passed; operator grant pending"](../docs/superpowers/reviews/2026-10-05-plan-11-30-task3-codex-review.md#d2-wsl-obligation-discharged--publication-readiness-passed-operator-grant-pending), 2026-10-11). The release was "D2 documentary batch accepted — one normal-hook local commit attempt released" (2026-10-11): staged tree `a45e448d` on parent C `343b233a`, packet `f40e788440dfd9fc153ca52cbe83a5368da9375cd26402fa713730089fffa723`, seal `aa29f85ce1d892a9cdaf12f4a8d22da583fb7905b2013c3f8d85aa95679e74ed` (20 members). This section was added by the final documentary composition (D3); it is not measured source.

Receipts, all in `C:\worktrees\optimus-cost-agent-worktrees\optimus-handoff\test-profiles-research\`:
- **Delivery:** packet `2026-10-11-claude-plan-11-30-d2-delivery-packet.md` (`25ff70c2b24083d78e0bb726cd4c8b6457d7fd0565e7853ad08f8bcc3b488de3`); sealed `plan-11-30-d2-commit-attempt1-20261011`, seal `0d64b375d941799d20495bfb360562462c29add02325b0abe4b796df8c189c30` (20 members).
- **WSL scope comparison:** sealed `plan-11-30-d2-wsl-scope-281f8ce7-20261011`, seal `687575f35825fe1d4d935f4a6501973b540e897e20bf4a2e6b476751e3472750` (2 members).
- **WSL parity run:** packet `2026-10-11-claude-plan-11-30-d2-parity-packet.md` (`f819a0efdfe5a614f598130493b99ee397527dbf10f7812c5de4bdaaf6514d5d`); sealed `plan-11-30-d2-parity-and-publication-handoff-20261011`, seal `286fa9ad617628be9268c7eeaf24720e99526f13f9649585ca0c8d2128825e8c` (22 members).

Codex verified all of these independently.

### The commit

| Item | Value |
|---|---|
| Commit | `281f8ce77b6c7e8c43545e7c610b1aab475e5981`: one attempt, normal hooks, no SKIP, `--no-verify` or retry |
| Parent / tree | single parent C `343b233ab7b470690eb21fe20c4662460694955c` / `a45e448db244e4f5cd78e38f4fa2e3b180b1e467` (exactly the released tree) |
| Subject | `docs: record Plan 11.30 S1 delivery and corrected-source finals at 343b233a` |
| Paths | the 9 released paths, each blob equal to Codex's SHA-256 table: `docs/README.md`, ADR-020, `docs/decisions/README.md`, the backlog, the masterplan, the kickoff, the review file, this report and the manifest. Source, tools, tests, workflow, configuration, lock, baseline and pre-commit identities are unchanged from C |
| Committed blobs | all 1,396 equal the staged index; status clean afterwards; remote main still `4ed9b25` |
| Message | the commit object's message bytes equal the sealed `msg-d2.txt` (`bd5546464aa8424347702ed42fbd65129540646b8a954af2c886428cad505ecb`) |
| Committer date / hooks | 2026-10-11T08:15:06Z; 08:15–08:22Z. Passed: trailing whitespace, file size, ruff, bandit, ast-grep, config-trust-scan, secret-scan and pytest-coverage. The yaml and toml hooks were skipped: no files |

**The owned-process check, receipted this time.** `prerequisites.txt` records it with its time, exact command, script hash and result: at 2026-10-11T08:15:02Z, `proc_check.ps1` (in the seal) found **0 lane-owned Python/pytest processes**; six foreign Plan 12 Python processes were left untouched; host CPU 27 %. This is a new receipted check. It is not retrospective proof for S1's earlier missing receipt.

### The commit-profile hook run (not a final)

- **Run** `20261011T081551-28460-343e44`: terminal ACTIVE, COMPLETE, exit 0; valid with the qualification `parent=not_found:ancestor_exited`. Codex replayed it independently.
- **Selection:** 6,402 of the 7,412 collected nodes (1,010 deselected), as Codex's verified dry run predicted (audit depth none; fallback `unmapped: reports/plan-11-30-test-profiles-manifest.json`). Coverage-free.
- **Raw phases:** 6,365 call-passed, 37 skipped (18 at setup, 19 at call), 0 failed, 0 no-call nodes. The recorder-test nodes were not selected this time.
- **Not a final full suite:** a coverage-free commit profile, not the 7,412 universe.
- **Forward obligation:** the hook emitted `wsl-platform: next checkpoint` (a `fallback:broad` trigger on the unmapped manifest). It is discharged at D2; see below.

### WSL scope disposition and the 55-node run at D2

Codex accepted **input-specific reuse** of C's accepted WSL evidence for the **1,574** platform nodes outside `tests/unit/guardrails/test_ci_parity.py`. Implementation, dependency, configuration, policy and classification identities are unchanged, the platform scope is identical (1,629 platform-tagged nodes, `d79185015cc55b96a2fae2b6fd3d34fab82967e566cc3b73fba461672932c9ed`, set-equal at C and D2) and C's original qualifications are retained. This is an explicit obligation disposition for this documentary descendant. It does not turn C's raw records or coverage into D2 measurements.

The **55** `test_ci_parity` nodes read the whole tracked-file list, so the changed documents are part of their input. Codex chose a small real WSL run for them rather than a qualification alone, because Windows evidence is not WSL evidence (only 45 of them were in the D2 Windows hook).

| Item | Value |
|---|---|
| Checkout | fresh independent clone `/root/p1130-d2parity-20261011T083120` at `281f8ce7` (tree `a45e448d`), detached and clean; earlier acceptance clones untouched |
| Environment | its own frozen environment; CPython 3.14.6, pytest 9.1.1, coverage 7.14.3 (not writing) |
| Identity | head, tree, clean status, `pyproject.toml`, `uv.lock`, profiles, groups, pre-commit, baseline and the src/tools/tests `ls-tree` digest: equal before and after |
| Node list | the retained 1,629-ID list's 55 `test_ci_parity` IDs, identical to D2's own classification; digest `241319bbdcacdc9f9524d4834c3a2c1ccb02f34627bec74ceb5c61760911165f` |
| Command | `uv run --no-sync pytest --no-cov -p no:cacheprovider -q -rs @<nodes.txt>`, with normal selection and the root conftest; no addopts or marker override |
| Result | **55 passed** in 11.47 s, exit 0; one serial attempt, no retry |
| Record | `20261011T083201-525-8c700e`: ACTIVE, `default_selection`, terminal COMPLETE, exit 0, 55 selected, full depth, head `281f8ce7`; valid with `native=unsupported`, `guard=unsupported_platform`, `parent=unsupported`. Raw phases: 55 call-passed, 0 skipped, failed or missing |
| Load | 0.54 before, 0.39 after |

**Platform accounting for D2's forward obligation:**

| Part | Nodes | Evidence |
|---|---|---|
| Reused from C under Codex's input-specific scope disposition | 1,574 | C's accepted WSL full run |
| Run on WSL at D2 | 55 | run `20261011T083201-525-8c700e`, 55 passed |
| **Total** | **1,629** | 0 failed or missing |

D2's forward `wsl-platform: next checkpoint` obligation is **discharged at `281f8ce7`**. C's recorder, skip and capability qualifications are retained. C's full-run coverage and timing stay measured at C and are not relabelled as D2 measurements.

## I5 publication and PR-body correction (2026-10-11)

**Status: executed under the operator's exact approval; the body correction accepted** (Codex, ["PR280 publication verified — bounded masterplan declaration correction released"](../docs/superpowers/reviews/2026-10-05-plan-11-30-task3-codex-review.md#pr280-publication-verified--bounded-masterplan-declaration-correction-released) and ["PR280 declaration correction verified — main CI evidence remains pending"](../docs/superpowers/reviews/2026-10-05-plan-11-30-task3-codex-review.md#pr280-declaration-correction-verified--main-ci-evidence-remains-pending), both 2026-10-11). This section was added by the final documentary composition (D3).

### The operator's approval

Recorded in ["Operator publication approval — exact D2 branch push and one PR released"](../docs/superpowers/reviews/2026-10-05-plan-11-30-task3-codex-review.md#operator-publication-approval--exact-d2-branch-push-and-one-pr-released) (2026-10-11): a direct operator reply in Codex chat `01a10617-9940-72c0-a5e2-e3f8c3241055`, quoted there verbatim. It allowed Claude to push the branch at `281f8ce7` without force and to open the PR with the reviewed text; merge, closure and cleanup stay held. The grant covers exact D2 only, not a later HEAD.

### Publication, as executed

Receipts: sealed `plan-11-30-pr280-masterplan-impact-fix-20261011` in `C:\worktrees\optimus-cost-agent-worktrees\optimus-handoff\test-profiles-research\`, seal `55ff76a88d80d7b049d1037f9284cd944fdae4323f4a32a8813eea0d237190cc` (13 members); packet `2026-10-11-claude-plan-11-30-pr280-masterplan-impact-packet.md` (`e99ac5b54a3a16f4d46f0d9f7dca6602f0fed29cab24709668413c3cd24de15c`).

| Item | Value |
|---|---|
| Pre-publication recheck (08:40:15Z) | branch `agent/claude/plan-11-30-test-profiles`, head `281f8ce7`, tree `a45e448d`, clean; frozen v5 `149002fa…`; source/tools/tests/workflow/configuration/lock `ls-tree` digest equal to C; remote branch absent; remote main `4ed9b25` |
| Push (08:40:20Z) | `git push origin 281f8ce77b6c7e8c43545e7c610b1aab475e5981:refs/heads/agent/claude/plan-11-30-test-profiles`: a new branch, **no force**, exit 0; the remote branch is exactly `281f8ce7` |
| PR (created 08:40:37Z) | [#280](https://github.com/vibhanshu-agarwal/optimus-cost-agent/pull/280) to `main`, base `4ed9b252bc63a4ffd7179c34083af28566bee0a7`, head `281f8ce7`, with the reviewed title and body. The only extra body content is the disclosed Claude Code attribution line, which Codex accepted as attribution with no scope or authority effect |
| Merge ref (08:40:56Z) | `1946713e6c86a4a1f6db7335955c982e980c404c`, parents `4ed9b252` then `281f8ce7`, tree `a45e448d`, equal to the lane tree. This is content equality only; CI binds to `1946713e` |

### The masterplan declaration correction

- **The failure:** the `Masterplan impact` workflow's original run **`38125646844`** (job `114429346409`, check `verify`) failed with "malformed Master-plan impact declaration". The reviewed body's declaration, which Codex itself supplied, matched neither strict form the checker accepts. Because the PR changes the masterplan, only the `updated` form was available. Codex reproduced the refusal with the real `tools.verify_masterplan_impact.verify` and the PR's actual 63 changed paths. The failed run and its retained failure log are kept.
- **The correction:** Codex refined Claude's proposed r2 (the PR changes both the CI-guardrails custody row 268 and the capability row 296, not only row 296) and released r3, with the declaration `Master-plan impact: updated — HARDENING-TRACK-CI-GUARDRAILS`. The r3 body's UTF-8/LF SHA-256 is `e51d1be76de51505927e957ed1e8b13055a971be8730ed7ef835a51fbce72409`.
- **The edit** (08:49:40–08:49:44Z; receipts `06-pr-body-edit.txt` and `07-runs-after-edit.txt` in the CI-safety seal below): the prechecks passed (PR open; head, base and title unchanged; live body equal to the published body apart from the transport newline). Then one `gh pr edit 280 --body-file pr-body-r3.md` ran, exit 0. The readback equals r3 apart from the transport newline and holds exactly one declaration line; the `gh api` output hashes are `53292092…` before and `f540afe9…` after. No tested source or head changed.
- **The re-run:** the edited-event run **`38126187842`** (`pull_request`, attempt 1, head `281f8ce7`, 08:49:49Z–08:50:06Z) succeeded. This success does not erase the original failure; both runs are kept.

## I5 candidate CI and seven-module safety comparison (2026-10-11)

**Status: accepted** (Codex, ["PR280 CI and safety accepted — final documentary composition released"](../docs/superpowers/reviews/2026-10-05-plan-11-30-task3-codex-review.md#pr280-ci-and-safety-accepted--final-documentary-composition-released), recorded 2026-10-11 10:45:23 UTC) at the **actual PR merge commit, not the branch head**. Codex verified independently the packet `2026-10-11-claude-plan-11-30-pr280-ci-safety-packet.md` (`2ceb0e33c49e51730e24e5d58cf85b4bb755ca063d0ffd98a84d5eb11b2c93d1`) and the sealed `plan-11-30-pr280-ci-safety-1946713e-20261011` in `C:\worktrees\optimus-cost-agent-worktrees\optimus-handoff\test-profiles-research\`, all 94 members, seal `3f24e592ddf1ea89881fbdc39c38b46a5a91d212a23e5051875e5de39d1c45c2`. This section was added by the final documentary composition (D3). A pass here is not merge authority.

### The tested commit

- **Run:** guardrails run `38125646691`, attempt 1, event `pull_request`, job `114429345970` (`clean-environment-recheck`, `ubuntu-latest`): **success**. All 17 steps through upload succeeded, among them pytest-coverage (step 14), the product-coverage validation (15), the record copy (16) and the upload (17), and so did the four later cleanup and completion steps.
- **Tested commit:** the actual PR **merge commit `1946713e6c86a4a1f6db7335955c982e980c404c`**, parents base `4ed9b252` then branch `281f8ce7`, tree `a45e448db244e4f5cd78e38f4fa2e3b180b1e467`. The retained checkout log, the gate receipt and the Git objects agree on it.
  - The tree equals D2's, but **the commits are distinct**.
  - The CI evidence is bound to `1946713e`, not to the branch head.
- **Git-metadata wording:** Codex accepts this concrete merge-ref run and its provenance. The git-sensitive source and record tools bind the actual SHA and include it in the export and reuse identity; the inspected real-checkout paths consume committed content and provenance rather than any assertion about the branch's parent count. **Universal metadata independence is not claimed**, and the acceptance does not transfer automatically to a future main commit.

### Artifact, coverage and floors

- **Artifact:** `11697417824`, of run `38125646691`. Its ZIP SHA-256 `a86fc33d6dbeabbf7c613e8e453d2acd161d313e790b8546ae54d36a1a8c13ab` equals the GitHub digest.
- **Coverage JSON:** `20bfdadd5a36000ce9413a7f780f5a1cd5d1ad11a905693ea0c86b951d926037`, covering the exact 226-file configured source inventory. The configuration, lock and groups hashes were recomputed from the tested commit.
- **Floors**, measured and compared at precision 0:

  | Product | Measured | Compared | Result |
  |---|---|---|---|
  | Optimus | 88.85913664394677 | 89 | pass |
  | Context Engine | 95.92430858806405 | 96 | pass |
  | Model policy | 96.98795180722891 | 97 | pass |
  | Evidence Handoff | 65.96291012838802 | 66 | informational |
  | Aggregate | 84.0469933529139 | 84 | informational |

### Records, the full session and the outcome count

- **Records:** all 67 uploaded run-context headers pass the schema reader.
- **Exactly one full session:** `20261011T084124-2858-534abb`.
  - ACTIVE, `default_selection`; 7,412 selected and 111 deselected; selection digest `a1006e75018a18b51783e94f83b82068bffcd2fae3f92670cba2f7ec36fa926a`; full audit depth; terminal COMPLETE; exit 0; no recording errors or withheld results.
  - Valid with the POSIX labels `native=unsupported`, `guard=unsupported_platform`, `parent=unsupported`.
- **Universe:** CI's own `validity.txt` names that session ("67 records considered") and establishes the own-checkout universe.
- **Outcome count:** the job log reports **7,199 passed, 213 skipped, 111 deselected and one warning**. This is a **job-log outcome count, not a reviewer raw-phase recount**: the artifact exports run headers, not phase sidecars.
- **Producer:** CPython 3.14.8 and coverage 7.14.3, the same as the base. UTC is **inferred, not a timezone receipt**; read as UTC, the JSON export landed 4.413324 s after the gate window.

### Seven-module safety comparison

Against the accepted I1 main-push base: run `37964416192`, artifact `11633307691`, coverage JSON `47994ad93b111d172d292e22d3757c8faaafd67a7005d2d690eed7771ad83d66`. The `compare` command read both records through the corrected S1 reader path and printed "safety rows comparable, no regression" (exit 0).

| Module | Summaries, missing lines, missing branches |
|---|---|
| `tools/registry.py` | identical |
| `runtime/mutation.py` | identical |
| `gateway/models.py` | identical |
| `evidence/ledger.py` | identical |
| `acp/framing.py` | identical |
| `retry/policy.py` | identical |
| `tools/policy.py` | identical |

- **No regression.**
- Q-C1's proven base-only absent audit-depth option is retained (`base: audit_depth_unrecorded:no-option-at-base`).
- Neither side has a Python patch mismatch.
- The earlier C Windows and WSL measurements keep their original pin and qualifications.

### Residuals and what stays held

- **Retained residuals:** optional seam, overlap, cache-validation and lookup upkeep under `P11-FEAT-TEST-PROFILES`; the MAIN-5 environment observation under P11-FU-32; A2A, binding/desktop, hardening registry/activation and the existing finding owners, unchanged.
- **Registry archival** stays **723/724 PARTIAL/non-passing**, with the UNKNOWN entry untouched. Successful CI does not clear it or authorize cleanup.
- **S4** stays an explicit exactly-one evidence obligation. The replay above discharges it for this candidate.
- **Still held:** the D3 documentary commit and any update of the published branch (each needs its own bounded authority; the existing push grant was for exact D2 only); merge to main, then main-push evidence at the actual main commit; terminal acceptance, closure, archival and cleanup.
