# Plan 11.30 — Codex Checkpoint A review

**Date:** 2026-10-04. **Verdict:** ACCEPTED at Checkpoint A after the bounded corrections. Earlier HOLD sections below are historical snapshots; the current acceptance/release section governs. This is a review snapshot, not a new plan or work registry.

Reviewed Claude's branch `agent/claude/plan-11-30-test-profiles`, base `a929aab2092876ab0d83ecc4e46896ae3a0935c0`, with no implementation commit. Approved v4 raw pin remains `8A40DEF6D627EDC722D9FA925BBB0C193DE433ECCB91D2DCA19F1DA6AFC5C790`.



## 2026-10-04 15:04:45 UTC — Checkpoint A accepted; explicit local releases

C-M1 and C-M2 are closed. Accepted correction packet SHA-256 `1D58E6D633B651DB206933AAC706E192FD1933C3F41932B69C02CFB74396E4FC`, report `061FFD6AC366B2DD02920DBFCC942EA2C9CD88A6EEA063A0444D2B8FC31B1CD7`, manifest `09E9076413D37E8626F6E55DE8AC114E091D6817067C2EFF080BC092F616F303`. Eight final source hashes independently match. All four seals verify (161/208/223/240 files); newest seal SHA-256 `2A018AC0598373E4FF46BFDA12A0AD25B941C2330E7A5BB479CF1641D730AFC1`. Read actual code/tests and retained Windows 428-pass/1-skip, WSL 381-pass/48-skip (both TMPDIR states), docs 84-pass receipts. Final LF test-file normalization has its narrow 86-pass/1-skip receipt and matches WSL bytes; no semantic code change after Windows gate. Native unsupported/skipped cases and partial registry remain qualified. Full Task 6 is UNRUN, not implied by this acceptance.

Independent synthetic controls against actual lane module: valid receipt verify/archive 0/0; list disposition verify/archive 4/4 with named unreadable line; invalid UTC 4/3 with named UTC mismatch. No bytes moved. Whole-file refusal on structural damage is accepted; it prevents malformed un-attributable receipts satisfying interrupted moves. Read-only branch/HEAD/status/diff verification matches `agent/claude/plan-11-30-test-profiles` at `a929aab2`; `git diff --check` clean. Full lane Ruff independently reports `All checks passed!` using its prepared interpreter, no cache.

Claude correctly identified Codex's reversed predicate-strength statement. Corrected ADR-016: Windows PID/creation-time identity proof is stronger than the POSIX `/proc` fallback. Updated accepted evidence facts and relayed operator progress exception in the unpublished ADR. E2 provenance is a labelled hashed transcription, not fabricated original export. Operator-approved Plan 11.30 exception: existing backlog records verified completion with report/manifest; v4 stays frozen; no tick-only successor.

**Explicit releases under the confirmed operator delegation:**

1. Claude may make the local intake documentation/attributes commit, then the local Task 0 implementation/evidence commit. Import this final Codex-owned doc delta, verify exact v4/predecessor pins, inspect staged content for plan-only scope, and pass the normal narrow index-visible docs, secret and remaining commit hooks. Ignored reviewer checkpoint log must not be staged. No blanket `git add .` authorization.
2. For precisely these two commits, permit `SKIP=optimus-pytest-coverage` with the commands below. The legacy hook launches the intermediate full suite prohibited by approved cadence; accepted focused evidence substitutes for this temporary hook invocation only. Preserve all other hooks and run clean full-tree Ruff before each commit. No `--no-verify`. This exception expires after these two commits; Task 3 implements the approved permanent commit profile. No new full run is commissioned here.

```bash
SKIP=optimus-pytest-coverage uv run --no-sync git commit -m "docs(plan-11.30): file approved intake and decisions"
SKIP=optimus-pytest-coverage uv run --no-sync git commit -m "fix(testing): stabilize run records and validate registry receipts"
```

3. Release registry archival only for the reviewed 724-entry class, digest `28bc1799eebba5f132996b366ee255ca0ccaf85f0a332df4e26316343009134a`. Immediately before execution obtain a fresh read-only inventory and dry run; eligible count, names/content class digest and positive-ended/absent-worktree eligibility must still match. Any change or refusal means stop and return the fresh manifest for delta review; no permission to broaden the class or force entries. Execute with the fresh manifest and this exact class digest only, archive rather than delete, retain receipts and run `verify` afterward. Codex has not executed machine archival.
4. Task 1 may start after this accepted checkpoint and the local intake/Task 0 commits. Registry class drift pauses archival only; as v4 allows, it does not block independent profile unit work. No push, PR, merge, unrelated activation or paid/service-call grant. Whole-plan closure and final full-source acceptance remain later gates.

No additional human approval round is required for these released local actions. Return exact commit IDs, hooks/check outcomes, staged source identities and archival result or changed-class stop. Refresh the existing report/manifest with accepted checkpoint and any separately executed archival receipt; preserve previous diagnostic failures/UNKNOWN and immutable raw seals. No product/test-tool implementation or commit by Codex.

## Authority update — 2026-10-04 14:08:40 UTC

Operator relayed the confirmation in Codex chat on 2026-10-04: explicit Codex approval counts as the operator grant for Plan 11.30 local intake/Task 0 commits, any expressly named docs-only coverage-hook exception, and exact-class registry archival. This delegation is settled; no further operator reconfirmation is required. Each action still requires an explicit Codex release after its evidence/safety gates. No release has been issued; push/PR/merge and service/paid-call authority are not added. Progress-rule exception remains pending separately.

The earlier absence-of-delegation rationale below is historical and superseded. After the corrected packet passes, Codex can expressly release each named local action without another operator permission round. No action is released merely by this authority update.

## Latest correction review — 2026-10-04

**Current verdict: bounded HOLD.** C-M2 is closed. The original C-M1 forged-receipt counterexample is fixed; two remaining malformed-input cases require correction before acceptance. Earlier sections below retain the original review snapshot and are superseded by this delta where they describe current state.

Correction packet SHA-256 `2C9741F894501307A5C53A13FCE0C0D74FDBD249187652510AF6F8F87EACF07A`; report `060A0155D46889231F806F8F946CFEFAADFE5ADE8BC87670C84342388E07F5E9`; manifest `901759A3901F88331E3075A40A87E754B967C9E2DF3D7DB4E40B273BD88EF5CA`. Codex independently verified seals v1/v2/v3 (161/208/223 files, no mismatches). v3 seal SHA-256 `885933c55dd32de3e30989ffa261c192d4217ddcbbb8fddf2a6269d1906c0cca`. No new full or core diagnosis run is requested.

Current correction code bytes independently read (older manifest source maps remain historical):
- `tools/testing/registry_maintenance.py`: SHA-256 `5f8c69afe21daf7a38fe06646748c640562f1fe81999af57e82ffccbd60c79eb`.
- `tests/unit/tools/test_registry_maintenance.py`: SHA-256 `fb329635eaa0b9104aee0983bddcbeca80953e1319cd45bb0c4b45ec4124bd17`.
- `tools/testing/run_context.py`: SHA-256 `8532d2bb7e03bc55e8331f6f0cc45f582ec137f650b695ebb5fe2ce716e3d53c`.
- `tools/testing/run_context_records.py`: SHA-256 `f11d0400240f2956936dc1a5a8e342d67102b43a6de5af97abea1c4097005253`.

### Remaining C-M1 controls

1. With every other field matching, `disposition=[]` raises `TypeError: unhashable type: 'list'` in `_receipt_mismatch`; it must produce the named disposition refusal. Check the string type before set membership, using the same validator for archive and verify.
2. With every other field matching, `utc="2026-99-99T99:99:99+00:00"` returns no mismatch, verify exit 0 and archive `already_archived`. The regex accepts an impossible date/time. Retain the tool's UTC format and validate the actual calendar/time using the existing datetime import; return a named UTC refusal on malformed input.

Add these controls test-first and re-run the narrow maintenance gate, then the applicable focused changed-source platform gates. Preserve existing valid UTC/idempotency and interrupted-move controls. No new framework or widened task. Another grant's receipts for other names are append-only history and may remain; they cannot satisfy this grant's entries.

### Codex-owned corrections completed

- Kickoff's ignored reviewer-log reference is plain code text, not a published Markdown link. Fresh pickups still obtain reviewer handoff and verify disk.
- Scoped v4 current/future-archive rules are `-text whitespace=cr-at-eol`; approved bytes remain unchanged. Import these exact metadata/kickoff changes and include intake files in the normal index-visible docs gate.
- Filed [ADR-016](../../decisions/ADR-016-test-cadence-product-coverage-and-staged-delivery.md) as an unpublished review draft, implementing Claude's four agreed filing repairs: hashed original-message excerpt as global S3, distinct local source labels, current correction-snapshot facts with remaining C-M1 cases, and registry options/decisions. Conditional substance agreement is not a later byte review or Checkpoint A acceptance.
- Claude and Codex concur on the plan-specific progress proposal: evidence-bound completion in the existing backlog with report/manifest references, v4 byte-frozen, no tick-only successor. Operator disposition remains pending because AGENTS.md requires both frozen bytes and checkbox-only completion.

Next: only the two C-M1 controls, imported docs gate, updated evidence identities and ADR pickup. Task 1 remains pending Checkpoint A acceptance. No commit, hook exception or real-registry archive release is granted. The subsequent operator relay establishes reviewer-release delegation; see the authority update above. Publication remains held.

## Evidence inspected

- Complete consolidated packet SHA-256 `03D76AB436E33F467CB6410690708C5882C2CD625AE8E465E9887581CE4280E2`; candidate report `CBD4A6C6176B720A4B7EEF7942BFAB223BC1355A258A75213F52D704D5D895C9`; candidate manifest `4498FAF97547EB2006735C497F24CCC0EECB449D5BD373319B966A3024231BAD`. Source paths are Claude's corresponding `reports/` files; intake code and Git diff were read directly.
- Both raw receipt seals independently verified: v1 has 161 matching files, v2 has 208 matching files, zero missing or different files. Candidate per-file hashes all match the amended manifest; recorder code remains identical to fix-check source.
- Recomputed ordered gap predicate: pre-fix coverage-on 8.286, off 9.286, PASSIVE/on 8.571; post-fix coverage-on **1.096**, off **1.169**, both within the ratio-of-two predicate. Every source core run exited 1 on the intake docs failure. These are diagnostic measurement results, not green suite receipts or final acceptance.
- Read final Windows gate outputs (363 passed, 1 skipped in both TMPDIR states), WSL outputs/receipt entries (316 passed, 48 skipped in each state), native predicate and isolation controls, retained standalone held/reopen probes, lifecycle fixtures and recorder/maintenance code. Skips establish no corresponding native claim. No new full or focused implementation gate was run by Codex.
- Fable's SOUND WITH AMENDMENTS and eleven dispositions are recorded in the candidate report and operator relay. The original standalone Fable review is not separately retained in this packet; Codex's conclusions come from the inspected code/receipts, not that reported verdict alone.

## Findings requiring correction

### C-M1 — Maintenance accepts a foreign receipt as proof

`tools/testing/registry_maintenance.py` lines 109–127 validate receipt JSON/schema only. Lines 158–166 treat any matching name as `already_archived`; lines 207–209 count a matching name without checking its content. A synthetic registry with correct archived bytes and one schema-valid receipt containing the wrong SHA-256, wrong class digest, wrong source/target and `end_status=LIVE` produces **`verify == (0, [])`** and an `already_archived` outcome. Codex reproduced both without reading or moving host entries.

Validate the receipt's mandatory field shape and correspondence to the manifest entry and granted class, including content digest, run identity, source/target, positive-ended proof and valid archival/reconciliation disposition. Use that validated match in both idempotency and verification. Duplicate/conflicting/foreign/partial receipts must produce named nonzero mismatch/refusal; no unrelated source is moved. Keep legitimate interrupted link/unlink reconciliation and idempotent replay passing.

Claude owns the test-first correction and focused Windows/WSL maintenance controls. This is within the existing Task 0 safety contract; no successor implementation plan is needed. Host archival remains held pending the corrected tool, reviewed fresh exact class and direct operator grant.

### C-M2 — Host-load qualification overclaims what the data proves

The report says concurrent load can only lengthen gaps, hence post-fix PASS is conservative. That implication is unproved: contention, scheduling and cache effects can affect both decile medians and their ratio in either direction. A partial registry also cannot establish that pre-fix runs had no foreign load.

Use: **post-fix ratios satisfy the predicate under an identified overlapping lane; host load was not matched or completely observable, so no conservative-comparison or isolated wall-speedup claim is made.** Pre-fix samples identify no live foreign run, which is an observation with partial-registry limits. Coverage-off and PASSIVE reproduction rule out coverage/job/guard as necessary triggers in these controls; do not generalize that into absence of every possible interaction.

Update report/manifest wording and keep all exit-1, UNKNOWN and partial labels. No repeated diagnosis/core runs are requested solely for this wording correction; source-bound measurements remain useful and full-run confirmation is already required at Task 6.

## Codex-owned corrections and custody

1. Removed the stray `Priority:` prose from the drafting backlog and removed duplicated owner wording. The repository's exact priority-hygiene test function passes when invoked directly. A pytest-session attempt was blocked first by missing pytest-cov in the review environment and then by denied sandbox temp-registry replacement; neither is a passing pytest gate. Claude must run the normal focused docs gate after importing the corrected intake files.
2. Located the new-chat handoff at its original authoring output path and reverified `B1CAFA8914BC79B5762F87F4C5FC4C7691C750344DC38D140B700B62D8990DBD`. It is no longer unverified by Codex; Claude can amend provenance accordingly. The missing shared-folder copy was not a broken approval.
3. Approval-vs-LF difference independently verified: v4 has exactly two CRLF sequences. The `7D07ADA3…` digest is an LF derivative, not a second approval. Added path-scoped `-text` rules for current/future archived v4 in `.gitattributes`, preserving the `8A40DEF6…` approval bytes. Git's filtered blob ID now equals the raw-byte blob ID `3cef47af7a65010391d583b22cffa393959600ac`, without staging or writing an object. Intake must include these rules with v4; do not silently normalize the approved file. Predecessors already use LF and retain their pins.
4. Drafted the consolidated ADR as an unfiled working paper under `tmp/plan-11-30-ADR-016-draft.md`. Claude must review its exact source/decision/mechanism distinctions before it enters `docs/decisions/` under ADR-011. That Task 0 item remains open; no new operator approval of settled requirements is needed.
5. `P11-FEAT-TEST-PROFILES` takes explicit custody of residual written-file close cost inside test phases, the boundaries-file real-registry interruption window and a zero first-decile median remaining UNKNOWN. These are residuals, not waived evidence or a claim of complete host isolation. Stage A full-run gates still govern delivery.

## Consolidated answers to Claude's six questions

1. **Intake commit:** Claude is the intended committer after direct operator authorization. Codex has corrected the intake docs and byte-preservation metadata in the drafting checkout; import/review those specific changes without overwriting Claude's code. No commit or `SKIP=optimus-pytest-coverage` exception is granted by this review. A docs-only skip requires a direct operator grant for that exact procedure, with the remaining hooks/Ruff/docs gates passing.
2. **Task 0 local commit:** no release yet: C-M1/C-M2, normal docs validation and ADR agreement/filing remain. Commit authority was explicitly separate in the operator's v4 approval; no direct delegation making a reviewer release equivalent to an operator grant is present in the reviewed record. Technical acceptance and commit permission are distinct.
3. **724-entry archive:** no grant. The inventoried class digest remains `28bc1799eebba5f132996b366ee255ca0ccaf85f0a332df4e26316343009134a`; it is historical inventory, not current authority. After C-M1, obtain a fresh read-only inventory/dry-run and a direct operator grant for the exact reviewed class/manifest. Changed class means stop; never broaden. Run `verify` after any separately approved execution.
4. **ADR:** draft prepared; Claude review and joint agreement precede repository filing. Intake and Task 0 remain uncommitted.
5. **Progress:** keep frozen v4 bytes unchanged. Record reviewed observations, named evidence and current next gate in the sole backlog; keep handoff rulings in the reviewer log. Do not claim completed task checkboxes from a private ledger. The frozen-plan rule and checkbox-only completion rule conflict for future progress. Codex proposes a plan-specific operator disposition permitting evidence-bound completion status in the existing backlog while v4 stays frozen; Claude concurrence is needed before asking the operator. Until then no rule is overridden and no completed plan checkbox is claimed. Do not create a successor just to tick boxes without that disposition.
6. **Task 1:** Checkpoint A acceptance remains held for the bounded corrections above. Return the amended code/report/manifest, focused controls, imported intake-doc gate result and agreed/filed ADR. Codex will verify that delta; no new full suite or repeated diagnosis is requested. Machine archival may remain unauthorized without blocking profile unit work, as v4 permits, but the tool's safety defect cannot be called accepted.

No commit, push, PR, merge, archival, service activation or private-memory mutation was performed by Codex. This review adds no new approval ceremony inside Task 0; it enforces its existing checkpoint and evidence contracts.

Codex docs validation: changed-file relative links and whitespace, exact ignored-log index assertion and priority assertion pass by direct invocation. Full index assertion is blocked in drafting checkout by an unrelated `docs/adr` folder rejected by `_current_documents`; no folder was altered. Full normal index-visible docs gate remains required in Claude lane. Tracked `git diff --check` passes.
