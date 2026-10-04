# Plan 11.30 — Checkpoint B Codex review and local release

**Decision:** ACCEPTED for Tasks 1–2 on the source below, including the bounded recorder clock correction. Stage-final Task 6 is UNRUN. **Reviewer:** Codex, architect/reviewer; Claude implements. Decision recorded 2026-10-04 21:01:11 UTC (2026-10-05 operator-local date).

## Source and review provenance

The operator relayed Claude's final packet and Fable 5.1's SOUND WITH AMENDMENTS verdict in Codex chat `01a10617-9940-72c0-a5e2-e3f8c3241055`. Packet `2026-10-04-claude-checkpoint-b-packet-plan-11-30.md` SHA-256 `68eabad13deed304e85bd9ce5e6c07937e05a5f46f0f255ef4eec1148ea6b1c0`. Fable's final verdict is operator-relayed and recorded in the report/manifest; Codex independently inspected source and raw receipts rather than claiming to have read a separately retained final Fable transcript.

- Lane: `C:\worktrees\optimus-cost-agent-worktrees\optimus-cost-agent-wt-claude-p1130`; branch `agent/claude/plan-11-30-test-profiles`.
- HEAD: `d562e95ed6a6121884ceb85ee6464326f913323c`; cumulative checkpoint base: `a929aab2092876ab0d83ecc4e46896ae3a0935c0`.
- Tested working diff: `9d123df294f71a209a1e9c4b42ab33dea23bb087bcd0534b5faf40535fa4d267`, 18 files. This is dirty-tree evidence bound to the tested diff and hashes, not exact-commit evidence.
- Final working diff independently reproduced: `93598d932678eea96a35be7d4b08d1ff1c80bdef57fda647a5d70fd4893ee471`. All 16 non-report files match the sealed pre-run hashes; final backup matches all 18 current files. Post-run edits affect only the report and manifest. Windows and WSL pre-run source-hash lists are byte-identical.
- Repository-visible evidence when imported: `reports/plan-11-30-test-profiles-evidence.md`, section Checkpoint B, SHA-256 `7c2de99f3bb4f83d0af00c0112acb111f7050442b96817373baa5fd353f691b1`; `reports/plan-11-30-test-profiles-manifest.json`, `sections.checkpoint_b`, SHA-256 `c4ef05213bbe4701fa66278fde66a43034358d99af559e265c626f6904aeaf57`. These are snapshot identities; later report additions do not rebind earlier source evidence.
- Approved [v4](../plans/2026-10-04-plan-11-30-test-profiles-implementation_v4.md) remains byte-frozen at `8A40DEF6D627EDC722D9FA925BBB0C193DE433ECCB91D2DCA19F1DA6AFC5C790`. Completion uses the operator-approved Plan 11.30-only exception in the [sole backlog](../plans/2026-07-23-consolidated-deferred-followups-backlog.md#p11-feat-test-profiles-test-cadence-selection-and-attributable-core-parallelism).

## Independent verification and disposition

Codex read the classifier/plugin, selector/runner, clock correction and controls; recomputed raw record validity and Windows overlap intervals; verified current diff/source identities, all five attempt/receipt/archival seals and both 18-file backups. Prepared-lane full-tree Ruff (`python -m ruff check --no-cache <lane>`) and lane `git diff --check` independently pass. No new long checkpoint or full suite was run by Codex.

| Platform | Selected subrun | Full-depth current audits | Concurrency | Qualification |
|---|---|---|---|---|
| Windows | 5,038 passed / 40 skipped | 67 passed, 812.78 s | Three runs, each 373 passed / 8 skipped of 381 nodes | COMPLETE / ACTIVE; native valid, guard installed; parent not_found:ancestor_exited retained |
| WSL | 4,988 passed / 90 skipped | 67 passed, 555.02 s | Once serially in the selected run; no load repeats | COMPLETE / ACTIVE; native, guard and parent unsupported retained |

All seven terminal records validate through the existing field table and current runner validity boundary. Counts above are the retained pytest terminal counts, checked against each run's own records; skipped nodes are not passing tests. Raw Windows phase boundaries independently reproduce the manifest to the microsecond. Load `20261004T200844-7248-98efd6` test interval is 20:08:45.396193–20:22:17.023296 UTC; every counted repeat's entire session lies within it. Distinct run IDs, node argument files and separate temp/output resources support the same-worktree coverage-free audit load. No Windows identity parity is inferred from WSL.

**B-M1 closed.** The original review-only counterexample (ACTIVE / exit 0, never validated and no terminal time) now returns INVALID with `selected: not_validated`. Independent in-memory controls also confirm a valid subrun passes and a test failure remains failed even when its record is INVALID. Altering real terminal completeness to INVALID is rejected. The runner preserves allowed UNKNOWN/unsupported qualifications, rejects invalid native/guard evidence, and cannot turn a non-complete overlap verdict into pass.

**Clock correction accepted in this combined changeset.** Binding recorder clock functions at import isolates them from tests patching the shared `time` module. Codex independently exercised the patched-clock boundary in memory: no spurious sample, a genuinely due sample uses the recorder's clock, and no negative sample gap. The attempt-2 INVALID result stays INVALID; attempt 3 supplies fresh real WSL evidence. This repairs tooling, with no product behavior change or new plan scope.

**Fable amendments C1–C3 closed.** The attempts table is intact; the report retains WSL guest wall-clock jumps of approximately 47/15 seconds and minute-scale timestamp accuracy; post-edit docs gate 85 passed, detect-secrets exit 0, diff check exit 0 and report CR-byte checks are sealed separately. No precise cross-platform wall-clock or WSL gap-performance claim is accepted. Windows overlap relies on same-platform records. The narrow frozen-v4 Tooling-cell grammar compatibility repair preserves the exact approved bytes and all other prerequisite checks; its negative controls are in the tested source.

Failed attempt 1, its abandoned/orphan history, and attempt-2 WSL INVALID are sealed and retained, not overwritten by attempt 3. Review residuals remain with the existing feature owner in the sole backlog: abrupt hard-kill cleanup is not established by Task 2's supported interrupt/error/timeout paths; `GIT_INDEX_FILE` hook proof belongs to Task 3; pathspec-only/dynamic scanning remains a documented selector limitation; the two cheap AST audits remain full-depth audit-current. This accepts the stated Task 2 contract, not a blanket forced-kill guarantee or a waiver of Task 5's required worker cleanup.

## Archival result — final for this grant, PARTIAL / NON-PASSING

Original manifest SHA-256 `102fbd7c2f5265f5c308de4fe2d01e872d61a7cc7833edef1d6ef7b2e9132380`, class `28bc1799eebba5f132996b366ee255ca0ccaf85f0a332df4e26316343009134a`, 724 originally eligible members. Codex independently read all 723 actual archived files and receipts: original hashes, class, source/target, ENDED status and archived disposition match, with no original top-level copies remaining.

Member `20261003T073119-45712-82142a.json` was refused as `changed_since_inventory:root_unknown`; it remains byte-identical in place, without archived copy or receipt. All three verification problems name only this member. Archive exit 3 / verify exit 4 remain non-passing; the original manifest is incompletely reconciled. Accept the verified per-member result and conclude this one execution grant. No retry, extra members, deletion or foreign-process action is released. Custody of the refused member remains `P11-FEAT-TEST-PROFILES`, with shared registry design co-owned by `P11-FEAT-ACP-RUNTIME-HARDENING`.

Seals under the handoff test-profiles-research folder (archival provenance, never runtime dependencies): attempt 1 `f2ffefcf5d77234eb6b88dde51afeb166c35d90a912920423d6c3b0e13de690a` (188 files); attempt 2 `e67c3ac2e8881887b15746d34c5a8d91cfe08c373a848389c9c53fb27ecfd19c` (81); attempt 3 `e170d99308d6c05d73c8af3d87b9c6254f21d24db69aa6401f11c23c1bdcf476` (81); report receipts `eb7aaafc557991a31f7029b7841a90a969c03b735b372e1581480270235664e0` (8); archival `6a4bec8d76c63f6a34dc936fffdb7f27024990f96392130dd9b323bc445e0ee1` (11). Every listed seal independently matches all members.

## Explicit local release and Claude pickup

Under the settled operator delegation, **RELEASED** for Claude in the named lane:

1. Import the latest Codex documentation delta: this B review, ADR-016, sole backlog, docs/README.md and docs/decisions/README.md. Preserve the existing A review history; import its latest bytes if needed. Never stage the ignored reviewer checkpoint log. Check the actual diff before staging; do not copy stale main implementation files into the lane.
2. One docs commit for these rulings, then **one combined Tasks 1–2 commit** containing the tested code/tests/profile manifest, logging/child-site declarations, recorder clock fix and evidence report/manifest. This is the simplest tested path. Do not reconstruct an untested Task-1-only snapshot.
3. For exactly these two commits, `SKIP=optimus-pytest-coverage` is expressly approved; all other hooks, full-tree Ruff, docs and secret checks remain required. No `--no-verify`. Suggested Git Bash commands after deliberate staging: `SKIP=optimus-pytest-coverage git commit -m "docs: record Plan 11.30 Checkpoint B acceptance"`, then `SKIP=optimus-pytest-coverage git commit -m "test: add Plan 11.30 profiles and checkpoint selection"`. This exception supersedes the earlier two-separate-task-commit structure and expires after these two named commits.
4. The docs commit occurs while tested code remains in the working tree; it is not a tested standalone executable snapshot. Keep implementation files byte-identical to the accepted source. After doc import run the normal index-visible docs gate, secret scan and diff check; after hooks verify staged/committed source and retain both commit receipts. Hook-induced code changes require affected verification before a success claim. These delivery checks do not commission an intermediate full suite.
5. **Task 3 may start after both local commits and their required checks pass.** Include the real temporary-index `GIT_INDEX_FILE` hook control before switching the hook. Implement all Task 3 product coverage/floor, full-source-report validation, hook and already-approved narrow CI coverage wiring requirements; Checkpoint C is Fable 5.1 then Codex. Stage A still requires its own Task 6 full Windows/WSL/applicable CI evidence. Tasks 4–5 and Stage B remain required.

Push, PR, merge, service/paid-call authority and other Plan 11.28 activation/cleanup/branch-folding holds remain unchanged. Codex implemented no code, committed nothing and performed no host archival. Local commit receipts are still pending; acceptance and release are not a claim that delivery has occurred.
