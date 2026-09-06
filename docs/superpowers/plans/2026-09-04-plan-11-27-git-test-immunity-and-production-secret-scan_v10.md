# Plan 11.27 v10 — Frozen-document baseline exception and local delivery implementation plan

> **For agentic workers:** Use superpowers:executing-plans task-by-task. Claude implements; Codex authors and reviews. Only fresh evidence supports new acceptance claims.

**Status / authority:** APPROVED FOR EXECUTION. Operator approved the exact three-entry policy exception and a new 75 combined-agent-minute box. Claude entered the box at **2026-09-05 08:17:36 UTC**, reporting 0.96 active minutes for entry checks. Codex sealing, review and reporting consume the same box. Relay idle is excluded; never charge the whole wall-clock gap as active time. Gate 2 may proceed once this complete contract is sealed; no repeat operator approval is required. Gate 3 still requires 40 minutes available at entry and final Codex concurrence before the actual candidate commit. V9 remains STOPPED frozen history; this document supersedes its execution authority, budget and candidate empty-baseline constraint only as specified below.

**Spec:** Approved v10 decision proposal SHA-256 `9215cc0eaeade30e2f0d56243c7beb2239c6b5f7f8031b4402e4c55f2eec3d58`; frozen scope `D:/Projects/Development/Python/optimus-agent-handoff/CODEX-BRIEF-2026-09-03-frozen-secret-scan-scope.md`, SHA-256 `f5d2b923b280999bb3ac68008b348e4933d59edd692d1b07efd8b5db3a3dad1b`, and reviewer handoff v2 `C:/worktrees/optimus-cost-agent-wt-codex-plan-11-26/tmp/static-first-ci-pickup-20260904/reviewer-handoff_v2.md`, SHA-256 `0b7a6933427bc7565071053e98e774ac2464ddb918e428ed1286216338989e43`. Read current reviewer checkpoint and shared CURRENT.md before mutation.


**Goal:** Preserve all frozen plan bytes while allowing the existing full local secret-scan hook to accept exactly three reviewed, non-credential integrity values in v9. Preserve scanning of every other finding.

**Architecture:** Keep the current hook commands, file selection, detectors and filters. Replace the blanket empty-baseline policy with an exact three-entry policy for one frozen document. Tests enforce that precise exception and prove that it does not exempt other values or paths.

**Tech stack:** Existing locked detect-secrets 1.5.0, Python 3.14, pytest and pre-commit; recovered Windows environment and existing native WSL environment. No dependencies or environment repair.

## Verified input and correction

Candidate: `C:/worktrees/optimus-cost-agent-wt-claude-ci-production`, branch `agent/claude/ci-production-secret-scan`, bound HEAD `c1989985171c3054916732f1306d5ffc85d5b094`. Accepted Task 3 functional patch SHA-256 is `b54da0a496eb5c649f9e190583e578009d42c87a9802487dac3fde4899af5a4b`; accepted Task 2 subdiff is `bff2b1a13689fb0296c8dd82f884b523b6ab95b41f75c4986f6bd332dbbdcbd9`. Those remain historical pins; approved subsequent changes must receive new pins.

Frozen v9 SHA-256: `823f269c05f9251b6594635a4881c23edb74ded3382469655f788c3b50cfb3dd`. Its path is `docs/superpowers/plans/2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v9.md`.

The failed full Windows rehearsal log reports three Hex High Entropy String findings in v9 and one Secret Keyword finding at `tests/unit/guardrails/test_ci_parity.py:86`. The rehearsal proposed tree was `9f2de4ec30cf01318e329132858aaa82a6493c17`; no Slice B commit exists. That tree is failed historical evidence, not a successful landing pin.

Codex verified all 64 entries in `D:/Projects/Development/Python/optimus-ci-production-evidence-slice-b-20260905/MANIFEST-sha256.txt`. The sealed report records 86.15% for the failed Slice B rehearsal. This is distinct from Slice A's committed 86.23% and rehearsal 86.08%. Codex inspected the sealed report and hashes; no tests or coverage calculation were independently rerun in this review.

Correction 04 is already externally recorded; verify it without recreating it: STOP-02 cites coverage filenames ending in `080539Z`; the actual sealed filenames end in `080505Z`:

- `task4-rehearsal-coverage-db-20260905T080505Z.coverage`, SHA-256 `e772ef08e750a749487f6879a50c50be3f9c01b5d8f476b0394926e7e6f3a0b0`.
- `task4-rehearsal-coverage-report-20260905T080505Z.txt`, SHA-256 `34de80d8c6f17b8aa3a2ee0130f3390782737e076ad70547b14097ca83e6ef46`.

Preserve STOP-02 unchanged and retain `task4-correction-04-stop02-coverage-filenames-20260905T081556Z.md` linking those names and hashes. Do not rename the artifacts or rewrite historical manifests.

Remaining work includes F1, F2, targeted controls, updated documentation and pins, a passing full-hook rehearsal, independent concurrence, the actual full-hook commit and final evidence. It is not only a commit command.

## Approved policy exception

Apply the approved candidate-local, exact three-entry exception to the empty-baseline policy. Explicitly supersede v9's baseline immutability and empty-results requirement only to this extent. Do not alter the baseline in main or any parked checkout. Do not grant broader baseline migration.

Each entry must have type `Hex High Entropy String`, `is_secret: false`, `is_verified: false`, and the exact v9 path above. The audit flag documents the classification; it is not what limits suppression. Detect-secrets 1.5.0 compares filename, detector type and value hash, ignoring line number. Therefore this exception also matches the same value repeated elsewhere in that same v9 file. Frozen whole-file hash verification supplies the separate byte-level constraint.

| v9 line | Meaning | detect-secrets SHA-1 of the literal value |
|---|---|---|
| 51 | Existing Git base object ID | `fe0cb7d0520c32a9541036d91d14e031c3b78580` |
| 53 | Historical empty baseline's SHA-256 | `64930e6006e5f8d3ffe66d522b3e9ff0071bc77e` |
| 54 | Locked uv.lock SHA-256 | `0403fd38ba560b5623bb067d208062ba7aa1b6ee` |

These scanner hashes were derived from the three literals in frozen v9 using the algorithm in the installed `PotentialSecret.hash_secret`; the real-hook controls below must validate the resulting baseline behavior before acceptance. Use the installed serializer's canonical path representation and prove Windows/WSL behavior; do not assume path separator equivalence without executing those controls.

Change only `results` in `.secrets.baseline`. Keep version, generated_at, plugin configuration, thresholds, filters and every other field unchanged. Do not run broad baseline regeneration or import another baseline. The historical generated_at remains historical; record the exception date and new raw file hash in new evidence. V9's old baseline pin remains a truthful historical pin, not the successor candidate's required pin. The successor must distinguish main's unchanged baseline from the candidate's reviewed new baseline.

Replace `test_detect_secrets_baseline_has_active_detectors_and_no_accepted_secrets` with an accurately named policy test requiring exactly the path, three entries, classifications and unchanged detector/filter configuration. Do not weaken it to a count, nonempty check, or all-is_secret-false check. Expected entries must be independent of the actual baseline; never derive the expected set from the file being tested. Verify v9's full frozen digest as a separate custody assertion.

F1's approved implementation is a same-line reasoned pragma on the workflow-label assignment. It changes no value or binding behavior. Review its exact diff and reseal the Task 2 subdiff; do not overwrite the old pin or claim the old acceptance covers newly changed bytes.

## Why this option

It preserves frozen custody, unchanged full hook coverage and the production inventory boundary. It introduces an explicit, testable policy exception instead of concealing one. Editing v9 would break custody; omitting required documents would change delivery; excluding documents would suppress an entire class of future findings. Those alternatives are not authorized. Any expansion beyond this exact exception stops for review.

## Scope of the successor

New implementation deltas are confined to `.secrets.baseline` and `tests/unit/guardrails/test_ci_parity.py` (F1, exact policy assertions and isolated failure controls). Codex may update README policy wording if needed, the sole backlog `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`, and the complete v10 execution document. Claude relays Codex's governance prose byte-exact. New raw evidence remains external.

Retain the existing seven functional files, README, backlog and nine frozen custody files from the v9 package. Add only `.secrets.baseline` and the approved complete v10 document to that delivery list. V2-v9 and archived scratch remain byte-exact. The ignored reviewer checkpoint, raw logs, temporary fixture files and the output decision proposal are not candidate commit inputs.

No new production behavior, configuration exclusions, scanner changes, hook bypass, marker changes, dependency sync or repair, Slice A edits, or fresh FU-6 revalidation. No push, PR, merge, installation or tag. Any new FU-6 hit preserves the established STOP rule and requires its own later authorization; this contract grants none.

## Approved budget and execution gates

The approved NEW 75 combined-agent-minute box began at 08:17:36 UTC: up to 35 for the complete execution-plan sealing, pickup, F1/F2 implementation, targeted controls, documentation and review; reserve the full remaining 40 before entering final rehearsal/commit delivery. Earlier balances do not transfer. Count both agents' active work, including reporting; exclude relay idle and sum concurrent activity. These are caps, not measured runtime promises. Stop if the complete remaining gates do not fit; do not shrink checks to finish.

### Gate 1 — Seal authority and recheck entry

- [ ] Verify this complete v10 contract against the digest published in the reviewer checkpoint and handoff. Copy it byte-exact from the reviewer plans directory into the candidate listed path. Approval and box start are recorded above; do not reset the box or reopen settled authority.
- [ ] Before freezing v10, check its own scan-bearing content in an external disposable fixture using the existing local scanner. Use reasoned annotations for any reviewed non-credential examples while it is still draft. Do not freeze another document that depends on an undeclared exception. No automatic fourth baseline entry.
- [ ] Recheck candidate HEAD, eight-file accepted functional delta, zero staged state, frozen documents, baseline/lock, recovered environment, Git/common-dir containment and manifests. Preserve the existing failed rehearsal and incident environment. Verify the already-recorded external correction 04. Entry custody is now reported as 66 entries; verify the live manifest and retain the prior 64-entry claim as historical.

### Gate 2 — Implement and prove the precise exception

- [ ] Claude applies F1 and the exact three-entry baseline change plus the independent policy assertion. All other baseline fields must compare equal to the original. Seal old/new raw baseline hashes and the exact candidate delta.
- [ ] In isolated repositories outside all tested roots, stage fixture baselines before invoking the real hook. The installed hook rejects an unstaged baseline change, so do not stage the real candidate early or misclassify exit 1 from that precondition as a detector control.
- [ ] Required real-hook control: frozen v9 with the old empty baseline fails on exactly the three known findings; the same file with the proposed baseline passes without baseline mutation.
- [ ] Required controls: a different detector-triggering value at the allowed path fails with that exact new finding; the original known value at a different path fails with its expected finding; a new credential canary under src fails. First show each positive specimen triggers the intended detector with no exception, so a non-triggering specimen cannot satisfy the control vacuously.
- [ ] Policy mutants independently reject an extra baseline entry, changed allowed hash/path/type, missing entry, and changed audit classification. Each must trip its own policy assertion. Real scanner rejection and policy rejection are separate claims.
- [ ] Execute affected guardrail tests and real-hook controls on Windows and WSL with native environments pinned, no sync/offline controls retained, and candidate Windows environment guarded before/after WSL. Preserve all existing binding mutants, timeout and containment controls. Reconfirm production clean/canary/empty behavior and baseline immutability in the isolated fixture.
- [ ] Because baseline results now contain document entries, verify the production-only invocation neither trims those entries nor rewrites baseline bytes. Use an isolated staged export for invocation checks that require a staged baseline; keep the real candidate index untouched until final concurrence.
- [ ] Codex reviews source, exact policy scope, control outputs, new Task 2/full-diff hashes, frozen custody, README and backlog. No premature Delivered or policy-closure claims. Any additional scanner finding stops for individual classification; do not extend this allowance silently.

### Gate 3 — Full delivery with 40 minutes available at entry

- [ ] Keep the failed v9 rehearsal untouched. Create one separately named independent full-history rehearsal at `C:/Users/pc/AppData/Local/Temp/claude/plan1127-v10-slice-b-rehearsal` only if absent, using --no-local --no-checkout and exact accepted Slice A parent. Verify contained Git/common dirs, no alternates, no shallow store and complete required history; strip inherited GIT variables.
- [ ] Apply the complete reviewed package and prove proposed tree equality using throwaway indexes, leaving the candidate index untouched. Verify exact path list and hook bytes. Pin uv invocations to the recovered Windows environment with UV_NO_SYNC=1; no environment creation or repair.
- [ ] Run the unchanged full default Windows rehearsal hook, preserving every status, exit and coverage database/report externally. A baseline rewrite or any hook failure is a failure requiring review, not an automatic re-stage/retry.
- [ ] Codex concurs on the precise successful rehearsal tree, evidence and final current-state documentation. Then Claude stages only that reviewed package, verifies staged/rehearsed tree equality, and runs the actual local commit's own full Windows hook with process-local `PYTEST_ADDOPTS=--junitxml=D:/Projects/Development/Python/optimus-ci-production-evidence-slice-b-20260905/b-commit-junit.xml`.
- [ ] Commit message remains `fix: enforce production-only CI secret scanning`. Require actual commit/JUnit/coverage evidence, unchanged lock/config/other Git state and frozen documents, no unintended baseline mutation, and final manifest verification. Preserve failures and prior manifests. No optional duplicate full-suite run; rehearsal and actual commit are separate mandatory gates.

## Global invariants and verification domains

- Candidate is the existing independent clone, never recreated or rebased. Parent tree is `258406df199720d19dbdd1f2640567f4f9aca4a8`; parent of Slice A is `5ea8f8f71548eb05a8562a10e98667e3d2061c4d`. Preserve parked `D:/Projects/Development/Python/optimus-cost-agent-wt-codex-ci-production`, its staged immunity work and unstaged Gateway diagnostic, and sandbox `0071b424c185fb45badb7e75be610ba44b9cfd0e`.
- Entry eight-file diff means the seven functional paths below plus README, explicitly scoped in `git diff --no-ext-diff --binary -- <paths>`. The relayed backlog is a ninth modified path; do not compare that whole diff with the eight-file pin. After Gate 2, publish fresh scoped and whole-package pins.
- Main baseline raw Git-blob SHA-256 remains `89eb6f47e9a1279ff6b9dad5f12e53a221914a16e0eabd873108bd7001397d71`. Lock raw Git-blob SHA-256 remains `f1caae185d41b02de2bf9a1cc4970e2517278c8a12b3a4728dd71fc2d826a097`. Shared main `.git/config` raw file SHA-256 remains `ae6059069cc62fde0eb237ecc9c6c0277974ff257b362c7ad596a5d35c651446`. Never apply the new candidate baseline pin to main or demand the old pin from the approved changed candidate.
- Capture binary Git output through subprocess.check_output without text decoding/re-encoding. Compare original base blob, index and working bytes at entry; after approval compare candidate baseline index/committed blob against its freshly reviewed expected bytes. Lock remains unchanged. Record both Git-blob and raw working-file hash domains; investigate CRLF/attributes before claiming drift. Scanner fixture baselines must remain byte-identical across invocations, not merely semantically equal.
- Windows environment: candidate `.venv`, standalone Python `C:/Users/pc/AppData/Local/Python/pythoncore-3.14-64/python.exe` 3.14.4; uv `C:/Users/pc/.local/bin/uv.exe` 0.11.29. Candidate cfg SHA-256 `9c503845220632572999aad4d94004d287277ec4971a5230d8a12fcd3ee91afb`; installed hook `e9e5a93b689822e50f6bb00c706332f4ff290f9c36811d9c2a48be58690e4f7c`. Locked pytest 9.1.1, pre-commit 4.6.0, detect-secrets 1.5.0, Ruff 0.15.20, coverage 7.14.3. No uv sync or repair. Before uv, pin invocation-only VIRTUAL_ENV and UV_PROJECT_ENVIRONMENT, set UV_NO_SYNC=1 and UV_OFFLINE=1, and verify resolved interpreter.
- WSL uses `/root/optimus-ci-venv` (Python 3.14.6) and `/root/.local/bin/uv` 0.11.31, with native environment pinning, UV_NO_SYNC=1 and UV_OFFLINE=1. Verify candidate Windows cfg/layout unchanged before/after. Git Bash Windows PATH uses `/c/worktrees/optimus-cost-agent-wt-claude-ci-production/.venv/Scripts`, not a colon-split literal C:/ element.
- Full default Windows hook and coverage threshold at least 80% remain unchanged; exact coverage hook entry is `pytest --cov=optimus --cov-branch --cov-report=term-missing` with pass_filenames false. No marker narrowing, optional duplicate full-suite run, bypass, Linux-only landing, or timeout widening. Preserve all four modules' full AST/docstring equality and all three migration SQL bytes; no production behavior change.
- Raw logs, scan-bearing scripts/caches/exports and normal full-suite temporary paths stay short and outside every tested tree. Gitignore is not a scanner exemption. Verify resolved Git-dir and common-dir containment before fixture config/index/ref writes. Use separate independent fixtures for mutants; force process teardown even on assertion failure.
- Evidence directory is `D:/Projects/Development/Python/optimus-ci-production-evidence-slice-b-20260905`. Preserve original failed v9 rehearsal at `C:/Users/pc/AppData/Local/Temp/claude/plan1127-v7-slice-b-rehearsal`, its 18 staged paths and coverage, and preserved incident environment `C:/Users/pc/AppData/Local/Temp/claude/plan1127-venv-incident-20260905`. Do not reuse or delete either.

**Frozen predecessors:** [v8](2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v8.md), SHA-256 `d41d6ba0ed1dc5e4a4e7e7c116dc12594501734277bb84d307f673897e811c7f`, remains the unrevised recovery proposal; operator Option 1 disposition overrides its reservation only for historical recovery/Task 3. Do not backdate it. [v7](2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v7.md), SHA-256 `9e05956c971310cbf9f6b31600c054e6172bdc4f29d98ddc0c63b2eb70d22b1b`, retains the preceding 75-minute box. [v6](2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v6.md), SHA-256 `83a8edf069863599830d9274e9073997aebe289490a762f942c6198afa130544`, owns accepted Task 2 and the budget stop before Task 3. Preserve all 34 Task 2 artifacts and the original failed attempts. [v5](2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v5.md), SHA-256 `f71006d3eb5662cffa5e8f9619efc83a440d2d92286a03a4ee861bf15fdfbc5a`, remains byte-exact and owns the accepted Slice A history and protocol corrections. V2 SHA-256 `577a1c7e5864d9d5d424f0dbf6ac5bd2b496b2ba809f714cdfe3c4574f641fc1`, v3 SHA-256 `dec4163fb294bfe56805ee6b1d245d25c1904b8424c2e567b90e94bb84168800`, and v4 SHA-256 `6fbb5600d18cfb9d570e68933439a441a12b674732d0fc384ae3e9e906400c83` also remain byte-exact at their review locations. The archived scratch predecessor SHA-256 is `4900776b5332a061a148b3ad35db9fa2cfe539504c458eb7b5bca48d5a603751`. Apply the established mechanical path-relocation proof before archiving any frozen predecessor. Until then their transitional custody remains registered; do not rewrite approved prose or relative links.

### Accepted Slice A prerequisite — read-only in v10

Candidate `C:/worktrees/optimus-cost-agent-wt-claude-ci-production`, branch `agent/claude/ci-production-secret-scan`, is an independent clone. Local commit `c1989985171c3054916732f1306d5ffc85d5b094` has parent `5ea8f8f71548eb05a8562a10e98667e3d2061c4d` and tree `258406df199720d19dbdd1f2640567f4f9aca4a8`, equal to the approved rehearsal. It changes exactly `tests/conftest.py`, `tests/unit/acp/test_stdio_ndjson.py`, and `tests/unit/tools/test_git_env_immunity.py`; reviewed raw hashes are `540decf8869143984ece18ec99fabb626d34c3ba43af1c65d08b75bcefbf5b08`, `87403e00b42a295b8ddc0820d56ba05818398b25c9546f220c7e2da25e31e585`, and `ba5a5329dcf5936fe004fed8dbb3a6addb196a4ac0f420dc165261df4b764619`.

The actual commit log, SHA-256 `cdf3d458daa906051a7c4c97caf5b2e511958275e66251ec19ac9467ae5ddea1`, records eight applicable hooks Passed and YAML/TOML Skipped. No FU-6 hit occurred. The hook-created coverage database is externally sealed at SHA-256 `da133c6b12c6780bbdc4a768a25c635ac8aa921110c67627d19e540f4d469a4e`; Codex independently derived TOTAL 13497 / 1456 missed / 3522 branches / 609 partial / **86.23%** from that external copy without rerunning tests. The report hashes to `b25b579584acee5ffffd3fd6693c5d0b91dca78efeb514d0de5a4a55d7c9f76f`. All 35 entries in external manifest SHA-256 `6522ecf5d80f0cecbd2956085026ea95c2ad9d918ffae1f3fab993a9569a29c8` match. The separate 86.08% figure belongs to the successful rehearsal. One original PATH-setup log remains irrecoverable and operator-accepted as an explicit gap; do not recreate or relabel it.

## File Scope and Commit Boundary

All implementation paths are relative to the existing candidate clone. No Slice A file and no other implementation file may change. The final package has 20 paths: the prior 18 plus baseline and v10. Preserve the existing four production annotation deltas; do not reimplement them.

| Class | File | Exact responsibility |
|---|---|---|
| B | `.pre-commit-config.yaml` | Preserve accepted Task 2 manual hook; include its existing delta in the final commit; existing local hooks unchanged. |
| B | `.github/workflows/guardrails.yml` | Preserve accepted Task 2 inventory check and production-hook invocation; include existing delta in final commit. |
| B | `tests/unit/guardrails/test_ci_parity.py` | Preserve accepted controls; apply F1 and exact baseline-policy assertion and isolated controls specified in Gate 2. |
| B | `src/evidence_handoff_runtime/migrations.py` | Annotate only the three recomputed SQL integrity hashes. |
| B | `src/optimus_gateway/observability.py` | Annotate only the four redaction labels, with unchanged AST. |
| B | `src/optimus/acp/launch_policy.py` | Annotate the enum label and synthetic URI text; preserve the docstring value and full AST. |
| B | `src/optimus/acp/local_gateway_secrets.py` | Annotate only the two keyring lookup names. |
| B docs | `README.md` | Describe the production CI boundary accurately, without claiming repository-wide or local-hook repair. |
| B docs | `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | Sole registry/custody; record local delivery, exclusions and later publication gate without closing the parent work. |
| B docs | `docs/superpowers/plans/2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v10.md` | Add this complete approved successor contract byte-exact. |
| B | `.secrets.baseline` | Only the exact three-entry results exception; preserve all other fields. |
| Frozen custody | Plan 11.27 v2, v3, v4, v5, v6, v7, v8 and v9 at their current root paths | Add byte-exact approved predecessor records and keep their Blocked transitional registry rows. Do not edit or move them without the mechanical Git-blob relocation proof. |
| Frozen custody | `docs/superpowers/plans/archive/2026-09-03-plan-11-27-git-test-immunity-and-production-secret-scan.md` | Add the byte-exact stopped scratch predecessor already located in the flat archive. |

The designated ignored reviewer checkpoint stays at `docs/superpowers/reviews/plan-11-27-review-checkpoints.md` and is never staged. Raw evidence, reports, scripts, rehearsals, copied trees and scan-bearing caches stay outside every tested tree and are never staged. The unrelated parked `tests/unit/optimus_gateway/test_server.py` diagnostic and parked lane remain untouched. This package neither diagnoses nor closes FU-6 or FU-7.

## FU-6 and Other Stop Conditions

The historical P1 grant names failed log SHA-256 `987c7444bfadf2f52a2387f65e3a45ad9b07a291fc2a85186a58b4d8b01ae632`. Its authorized attempts are historical; it is **spent**, not reusable. P1-P9 govern any later operator-authorized revalidation, but this plan does not grant one.

A new FU-6 hit in a focused gate, rehearsal or actual commit means STOP: retain the exact failed command/log/hash, tree and platform; notify the operator and Codex. No automatic retry, commit from WSL, timeout widening, skip, suppression or claim of closure. A later P1 must name that hit and its STOPPED artifact in writing. P8 allows one revalidation for the named hit; P9 still requires the actual commit hook. Retain failed evidence above any separately authorized clean result, preserve source equality, record the required dated FU-6 observation without changing its Status, and prove the full default Windows selection/normal temp layout. The old 111-deselected count is bound to its old base; do not manufacture that count on a different base.

Other STOP triggers: relevant base drift; unavailable locked tooling; config/Git-store escape; missing independent review; actual or unclassified secret; unapproved file/detector/baseline change; an out-of-scope test failure; production behavioral change; or cap exhaustion. Defects introduced by this implementation may be corrected within the listed scope and remaining box. Prior failing evidence is never overwritten or converted into a passing row.

## Explicit Exceptions

These obligations stay with the named owner in the [sole backlog](2026-07-23-consolidated-deferred-followups-backlog.md); this plan does not close them.

| Excluded obligation | Owning entry / next gate |
|---|---|
| Broader baseline migration beyond the exact three entries, repository-wide scan promotion, PR #194 collision, frozen-artifact relocation, local-hook redesign and remaining security-gate tension | `P11-FEAT-ACP-RUNTIME-HARDENING`; separately reviewed migration/design. |
| Focused production S110 enforcement; other Ruff families; evidence-handoff test findings | `P11-FEAT-ACP-RUNTIME-HARDENING`; next bounded static-analysis plan after CI. Preserve outbound-writer settlement/worker survival when disposing S110; do not introduce fallible logging or global ignores. |
| Gateway intermittent diagnosis, priority adjudication and closure; parked diagnostic | `P11-FU-6`; its separate Windows lifecycle lane. A per-hit observation does not change that Status. |
| Historical NDJSON coverage-flake closure and its remaining 25-process evidence gate | `P11-FU-7`; separate evidence lane. The explicit EOF prerequisite does not spend that gate or rewrite its diagnosis. |
| WP-27 runtime integration, helper-level isolation, live session evidence, publication and installation | `P11-FEAT-ZED-RESUME`; accepted runtime lane and operator publication authority. |
| Earlier unexplained watchdog assertion and shared-cache repair | `P11-FEAT-ACP-RUNTIME-HARDENING`; separate evidence/environment disposition. A capture abort before tests ran does not explain an executed-test assertion. |
| Main CI activation, branch protection, remote publication and merge | `P11-FEAT-ACP-RUNTIME-HARDENING`; operator publication gate after local review. No sandbox merge route is assumed. |

## Final evidence and completion

- [ ] Keep existing Slice A and Tasks 2/3 evidence, failures and previously accepted missing PATH-log gap. Do not reconstruct missing historical runs. Preserve manifests before extending them; correction 04 is additive.
- [ ] Produce explicit old/new baseline classification and hash records, policy mutants and real-hook controls per OS, new scoped Task 2/full-diff pins, inventory/AST/SQL invariants, exact file list and full proposed tree. A runner control exiting 7 must propagate nonzero; trailing output commands must not hide failures.
- [ ] Audit all affected README/roadmap/backlog current-state claims. Codex owns sole-backlog prose; a required out-of-scope document repair stops for review. Include baseline exception as a local reviewed disposition, not repository-wide cleanliness or main CI activation. Frozen history is never edited.
- [ ] Preserve failed and successful rehearsals separately. Record command, start/end, platform, exit, hook statuses and emitted coverage DB/report. For actual commit also require the named JUnit report, actual commit/tree IDs, complete reviewed staged path list and matching reviewed/rehearsed tree. Never reuse rehearsal coverage as actual commit evidence.
- [ ] Record Codex final concurrence, final invariant hashes and clean intended candidate state with no unrelated changes. All custody docs including v10 match their sealed hashes. Both local commits must have their own successful full Windows hooks before local delivery is claimed. If a gate fails, record STOPPED and exact remaining work instead.
- [ ] Deferred owner rows remain open as listed above; no push, PR, merge, installation, tag or fresh FU-6 authority is inferred from local completion.


## Prerequisites

This table was added during sandbox integration to satisfy the repository's prerequisite gate. The preceding v10 text is retained unchanged as historical execution authority; its completed box and stopped delivery are not reopened. Original approval bytes remain preserved externally and in the original candidate. Current execution is governed by the integration working agreement and the consolidated backlog.

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|---|
| custody | Preserve the original v10 approval bytes and failed-run evidence | yes | Codex / Fable | Original candidate and prior evidence remain unchanged; this integration copy adds only this table and explanation. |
| implementation | Retain the accepted scanning delta and exact baseline policy | yes | Fable / Codex | Existing accepted bytes are materialized in the isolated integration checkout. |
| validation | Review and verify the corrected combined integration tree | no | Codex / Fable | Genuinely absent final evidence; settle this documentation correction and complete the pending checks. |
| delivery | Successful full Windows rehearsal and actual local commit | no | Fable / Codex | Genuinely absent results; run within the approved integration budget after mutual review concurrence. |
| scope | Publication, merge, installation or rollout | no | Operator | Merely unauthorized; sandbox commit and tag authority does not grant publication or deployment. |
