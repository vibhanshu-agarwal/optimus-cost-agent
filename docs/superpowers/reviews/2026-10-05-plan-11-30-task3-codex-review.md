# Plan 11.30 — Task 3 / Stage A Codex review

## Stage B Task 6 — local final evidence accepted; results composition released

Recorded 2026-10-09 07:24:20 UTC. This is an agent-selected technical acceptance under the settled operator delegation, not new operator policy or publication authority. Final packet SHA-256 `e32e3137e82bd59d6611ae062260f0cce3c105c2a6e5842945ebf63a06b1cfe8`; final evidence seal `69c9ff9aca4d3fb2c8c0e7a7a7feffc78cbbaa26b546b7c5836ee5d4aa37cea1` (69 members); governance-commit seal `1299d153cb3a80fe76589f6c1af69ba6d91a11b19b983e493782eba887753d0c` (20 members). Codex independently verified both seals and all members, the actual seven committed blobs, parent/subject, normal-hook receipts, raw records and coverage arithmetic.

**ACCEPT local governance delivery and Stage B Task 6 evidence at `3cece0a887a80f2250cf1e720afcdd527136a412`, tree `fabb67208f0dbd2513a4c39618e82be05d14ab4a`.** Parent is `66ddabfdf5bb3acccfffe39fa45f70b4b47924ad`. Exactly the seven released documentary paths changed; implementation/tests/config/lock/baseline did not. All applicable normal hooks passed; YAML/TOML had no files. The commit profile selected 4,567: 4,530 passed, 37 skipped, exit 0, valid full-depth ACTIVE record with `parent=UNKNOWN:access_denied`. This parent-HEAD hook evidence is distinct from the new final runs.

### Independently verified final results

| Evidence | Native Windows | WSL |
|---|---|---|
| Full run | `20261009T054057-42656-acf1b7`: 5,533 passed / 40 skipped / 111 deselected, exit 0 | `20261009T064009-595-4738a3`: 5,398 passed / 175 skipped / 111 deselected, exit 0 |
| Selection/depth/validity | 5,573 selected; default selection, ACTIVE, COMPLETE, full audit depth; native valid/full guard; `parent=not_found:ancestor_exited` | Same selection and full depth; COMPLETE/ACTIVE; native/guard/parent unsupported, protection none |
| Optimus production coverage | 15,076/16,659 statements + 3,466/4,466 branches = **87.772781%**, PASS floor 80 | 14,972/16,659 + 3,452/4,466 = **87.214201%**, PASS floor 80 |
| A2A informational coverage | 3,824/5,312 + 972/1,698 = **68.416548%**, not enforced | 3,680/5,312 + 944/1,698 = **65.962910%**, not enforced |
| Recorded-order inter-phase gap | 16,689 transitions; first/last deciles 1,668 each; medians 0.380500/0.381000 ms; ratio **1.001314**, PASS; no negative gaps | 16,544 transitions; deciles 1,654 each; 0.649000/0.591500 ms; ratio **0.911402**, informational only; two negative gaps retained |
| Nodes over two seconds | 284, zero implicit/default-tier classifications | 76, zero implicit/default-tier classifications |

Both runs use independent detached clones, separate frozen environments/data, the approved C1 serial coverage command and full H5 100/100 budget. Windows finished before WSL started. Both clones and the implementing lane are still clean at the pin. Selected-node digest is `709277bb4db8b4c493a9be41f5e98fec551c0b0888cd744f075bb3de63b520d2` on both platforms. Raw phases cover exactly the selected nodes; eight known intentional recorder controls have no call phase but passing setup/teardown, corroborated by pytest summaries. This is not a new missing-call failure.

Automatic coverage binding was independently executed through the existing environment on each measuring platform and returned the true full record; Windows explicit-record and automatic product reports agree. Both corrected six-check binding receipts pass. Coverage timestamps are local-time data and must be interpreted on the measuring platform. Common package versions match; Windows-only colorama/pywin32/pywin32-ctypes/tzdata and Linux-only jeepney/secretstorage are platform differences. Recorded Python/uv versions differ by platform; do not claim identical interpreters.

Fresh reviewer full-tree Ruff passes. Retained pin gates: docs **85 passed**, active/default/COMPLETE with parent UNKNOWN; Ruff/diff checks clean, valid manifest and unchanged pin. Those retained tests were read and verified, not rerun by Codex. The existing runpy ACP warning remains disclosed. Host load was recorded, not idle: Windows 31.7% before / 19.2% after; WSL has 30-second /proc/process snapshots. WSL unsupported protection and guest-clock qualifications remain; two negative gaps are not clamped or used for Windows performance acceptance. These serial final runs do not newly measure xdist speed: Checkpoint D and E-only pairs5 retain their own source-specific acceptance.

### Fable amendments and corrected collection history

Fable final review SHA-256 `9bc401e86e7ff3e5a9adbeca4b34ab33163efd2a9f09b2672c661444d7dd0511`: SOUND WITH AMENDMENTS, three LOW, no delivered-source defect. Codex concurs. Amendments 1/2 are accepted as applied: proof of measured-run binding and WSL ambient-load receipts. Amendment 3 is expressly authorized in the documentary follow-up: rename `current_delivery.head` to `delivered_source_head` with a dated drafting-source explanation; separately name measured final HEAD/tree.

The initial Windows collection chose `20261009T063630-33472-602c76`, the product report's later collection session outside the measured window. Its copy, empty gap output and initial incomplete binding receipt remain sealed as failed evidence collection. The corrected copy is the actual earlier full session; automatic/explicit binding, selection/window/pin/exit checks and recomputed gap support acceptance. No full test was rerun, no failed result is relabelled PASS, and this does not excuse the heuristic for future gates.

### Bounded results composition; exact commit grant still pending

**Release Claude to prepare exactly seven documentary paths:** the two existing report/manifest files plus `docs/README.md`, `docs/decisions/README.md`, the sole backlog, ADR-016 and this formal review. Use the immutable five-file reviewer snapshot identified in the shared checkpoint log, not later changing reviewer bytes. Do not stage the ignored checkpoint log, frozen plans, `.gitattributes`, source/tests/config/lock/baseline or raw/private evidence. No implementation change is authorized.

Append a dated Stage B Task 6 section/manifest entry bound to measured `3cece0a` and the full run IDs, hashes and qualifications above. Preserve prior report lines and manifest results, source pins, failed/INVALID histories, archival 723/724 PARTIAL/NON-PASSING and all residual owners. Reconcile current-status wording; apply Fable's head-field clarification. State local acceptance separately from Linux CI and base/candidate safety UNKNOWN. A later documentary commit does not become the source of these full-run measurements, and no self-commit/hash repair is required.

Run fresh changed-docs tests, both existing secret scans with unchanged baseline, full-tree Ruff, JSON/LF/diff checks, named seven-path identity and unchanged source/config/lock checks. Return the assembled two files and complete seven-path byte table/staged diff plus sealed receipts. **The local commit is HOLD until those concrete final bytes are checked and a separate one-attempt normal-hook release is filed.** This is the existing final-byte gate, not an additional operator decision or code checkpoint. No new Fable source review or full Windows/WSL run solely for these documentary edits; new source drift or failure requires disposition. Do not commit yet or retry-to-green.

### CI direction and remaining authority

Prepare the results write-up first, then the concrete publication-readiness handoff identifying the final branch/HEAD, current main drift, proposed push/PR scope and the exact base-main/candidate Linux CI coverage receipts required by Task 6. Preserve coverage version/branch/config comparability and per-file safety totals/misses. Missing comparable reports remain UNKNOWN; no extra Windows base-only full run is commissioned. Narrow CI coverage wiring is already in scope, but that is not a push/PR grant. Complete Task 6/plan closure, push/PR/merge, cleanup, services/paid calls and other Plan 11.28 activation remain held. No project commit or implementation by Codex.

## Stage B governance final bytes — accepted; one local commit and conditional final runs released

Recorded 2026-10-09 05:27:50 UTC. This supersedes the preceding final-byte HOLD without changing the frozen plan or the already staged candidate. Operator-relayed final-byte packet SHA-256 `2b08c5fec9a6250ce97f74a8a38bf4a36e0c55de206f2134ab43495b2f679fa6`; 25-member preflight seal `bb3240d6d78a7105d3919744212815983ffe46373d3d2b33767002bb140074fa`. **The complete seven-path documentary candidate is ACCEPTED.** Codex verified the packet, seal and every member, actual lane HEAD `66ddabfdf5bb3acccfffe39fa45f70b4b47924ad`, exact staged/working file equality, no other modified or untracked paths, and staged binary diff SHA-256 `93b81b64732469250dca64b6ce06f390174ae344b4e71da1dd6f2ee1a039633c`.

### Accepted interpretations and evidence

1. **Historical JSON status:** additive `status_recorded` objects correctly date the original historical `status` strings. All previous manifest sections are content-identical apart from those objects; other historical metadata is unchanged. `current_delivery` is a dated composition snapshot at `66ddabf`, not the unknown future governance commit or a final measured pin. The nine listed commits and first-recording commit metadata are provenance. Six new Stage B sections distinguish candidate measurements from delivered source; Stage B Task 6 remains `not_run` with null measurements. No self-commit/hash update is required after this commit.
2. **P11-FU-39:** “lifecycle-tooling inventory custody, if taken up as future work” is accepted. It points to the existing process-tree/captured-pipe inventory owner, not a proven additional defect, commissioned fix or broad closure. P11-FU-32 owns the separate TEST_VENV observation. This does not change another lane's plan, status or authority.
3. **Current-status placement:** the near-top dated section is appropriate. All original report lines survive in order, with the original opening status retained verbatim behind its historical label. Additive annotations reconcile delivered residuals and retain every original source/qualification. The append-only evidence rule protects historical results; it does not prohibit a clearly distinguished current-status section. No relabelled old measurement is accepted.

Codex reviewed the assembled additions against the previously reviewed section drafts and dispositions, verified preservation of all previous full digests, 16 exactly reconstructible sealed-location pairs, LF/no-BOM/final-newline and JSON style. Independently recomputed all five medians, ratios of means and newly displayed means of per-pair improvements. The recorded walls, calculated figures and reviewer assertions are separated. Unknown WSL splits, ambient-load/foreign-overlap qualifiers, failed attempts, e2 survivor, serial-cache guarantee boundary and source-specific performance acceptance remain.

Retained preflight: docs gate **85 passed**, run `20261009T051552-52612-f3cfb3`, ACTIVE/default-selection/COMPLETE/exit 0/native-valid/full guard with `parent=not_found`; staged-set local secret scan and detect-secrets exit 0 with unchanged baseline; staged/working diff checks clean. Fresh independent full-tree Ruff and both diff checks pass on the actual lane candidate. These focused docs receipts establish the documentary gate, not new full-suite/final coverage evidence.

The custom literal-link check is **exit 1, with 10 missing references**, not a blanket passing link scan. Codex verified all 10 targets already occur in both `66ddabf` and base main `a929aab`; no Plan 11.30 link defect is introduced. The changed-docs gate passes. Do not repair other-lane historical paths in this seven-path batch or add test/scanner exemptions. This qualification is accepted for this local documentary release; it does not waive later relevant closing/merge freshness checks.

### Exact one-commit release

**Expressly release Claude to make one local commit of exactly the following seven staged paths at these SHA-256 values**, in `agent/claude/plan-11-30-test-profiles`, parent `66ddabfdf5bb3acccfffe39fa45f70b4b47924ad`:

| Path | SHA-256 of working and staged bytes |
|---|---|
| `docs/README.md` | `56ee26fa50a96fbf30df8288f57589b655b08b1db53cb2f0eb8fd0ce0d216b05` |
| `docs/decisions/README.md` | `0bed8783a556012e45b91eaa4a8c09ad667b932a9da51488cecf6ecd45291364` |
| `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | `f4593b35a7e1fd71a637d1079e0ceebf7c6bb2469fd5cec579042abbdcf65a4b` |
| `docs/decisions/ADR-016-test-cadence-product-coverage-and-staged-delivery.md` | `3e8320819a3b322e35c46a99b62683aebba6f4625e06cfbec5dac45572878cfc` |
| `docs/superpowers/reviews/2026-10-05-plan-11-30-task3-codex-review.md` | `26cee1c2762fd325fc217f9f1c4439aef8f91b80eb8ffc1adb445630ced18a4e` |
| `reports/plan-11-30-test-profiles-evidence.md` | `48b26b2770d523576a4fc7f009007851be01ea559a6fa802cff6bd47dd8fbe7e` |
| `reports/plan-11-30-test-profiles-manifest.json` | `80fadde54db5d0275ab631e43105ed512ab26a7ad2d9fcbb343eed388773a5e5` |

Subject: `docs: record Plan 11.30 Stage B delivery before final gates`.

Use normal applicable hooks, no SKIP and no `--no-verify`. Before committing re-check parent, exactly seven staged paths, all seven hashes, no unstaged/untracked changes and unchanged source/config/lock/baseline. The reviewed documentary candidate has fresh checks; do not rerun the entire preflight solely because this release was filed. New changes, drift or material delay require the affected checks again. Any hook failure stops; retain stdout/stderr, verdict, index/working identity and seal, report it, and do not make an automatic retry or source change. The grant expires after this single attempt.

**Do not re-import this new release prose or later reviewer-file changes into the staged candidate.** The five earlier audit-snapshot hashes above are final for this commit. This dated authorization and the ignored shared reviewer checkpoint log govern execution; they do not add an eighth path or force a self-referential governance-import loop. Later review/delivery/final-result filings belong to the appropriate subsequent documentary batch. The ignored log, `.gitattributes`, frozen plans, source, tests, CI/config/lock files and scratch/private artefacts are excluded.

### Conditional Stage B Task 6 execution release

After the one commit succeeds with all applicable normal hooks, verify its subject/parent/exact seven committed blobs against this table and staging, a clean tree and unchanged implementation/config/lock. Record and seal the commit receipts. **Then Claude is expressly released to execute the existing local Stage B Task 6 without another operator or pre-run approval round.** The actual successful governance commit HEAD/tree is the final pin; `66ddabf` is the pre-commit source snapshot. Report the delivery promptly; evidence acceptance remains a later Fable-then-Codex decision.

Follow the confirmed command/topology section below: independent frozen native Windows and WSL clones, each detached at the actual pin, its own frozen environment/data and one serial coverage writer; record before/after source, command, interpreter/dependencies/config and host/owned-process identities. Preserve full default selection and full audit depth. Windows full coverage and Fable 5.1 read-only final review start together; WSL full coverage follows after Windows finishes, never overlapping measured chains. Use the exact C1 serial full pytest/product-report commands, verify coverage bound to that full run, apply the recorded-order Windows Task 0 gap predicate, retain unsupported WSL labels and slow-node classifications. No xdist coverage, extra base Windows run or new paid/live service action is commissioned. Run the remaining Task 6 gates, seal attributable evidence and return the final packet. A failed/INVALID/missing record or unmet prerequisite stops the dependent acceptance claim; preserve the attempt and seek disposition rather than retrying to green.

This completes the pre-pin documentary audit within the reviewed local scope. It does not accept unrun final evidence, remote Linux CI/base-candidate safety reports, complete plan closure, publication, push/PR/merge, cleanup or other Plan 11.28 activation. Codex changed reviewer governance only and made no implementation or project commit.


## Stage B Task 6 preparation — audit dispositions and final-byte gate

Recorded 2026-10-09 04:32:07 UTC. Preparation packet SHA-256 `baed89eb474b73234df46d2cc5aaf8e80f56cdddf4293c927a7e01afa4e57508`; 15-member preparation seal `ae94f6b4ed4f28b4800c538c35f6466e6c62fd959124fe4779f1e46cc7e5fd10`. Reviewed the complete report-section draft `cccf67c6a03f3de0be77e4e726268f982cc69bd8cd768f886a597413af2d3dc5` and manifest-section draft `0a99bf7aab3cedfad2e561cdf8f42b59f6684f551298d5a490ce8dd9d414527f`, notes and preparation plan. These are sections, **not the two assembled final report files**. Codex independently verified 42 delivered source-blob hashes, all 13 distinct referenced seal identities and the five pair sets' arithmetic. That seal-identity check is not a new recount of every member of the older seals, which were reviewed at their original gates. Lane remains clean at delivered `66ddabf`; no final run exists.

### Nine audit questions — dispositions

| Question | Required report/manifest treatment |
|---|---|
| 1. C1 label collision | Use **Task 6 command substitution C1** for the operator-approved command ruling, **Checkpoint C candidate C1** for `41ee2f9c…`, and **pre-amendment formal source** for `de18263d…`. Keep every full digest and run source distinct. C2 has no exact C2 Windows formal-parity claim. |
| 2. Missing C2/C6 WSL splits | Preserve the reported node counts and exits (5,192 / 5,200 nodes, exit 0); mark the passed/skipped split **not established in this summary**. Do not infer all nodes passed, borrow Windows skips or commission reruns for held historical candidates. Distinguish ledger-reported C1 counts from independent raw recounts. |
| 3. OPTIMUS_TEST_VENV custody | Link the pre-existing observation to existing `P11-FU-32` under `P11-FEAT-ACP-RUNTIME-HARDENING`. The Option A rename preserves launch policy; no metadata classification/rename change or new work item is commissioned. |
| 4. Checkpoint B Task 5 obligation | Discharge worker kill-on-close/attribution **for the accepted native Windows controller topology**: `test_an_interrupted_controller_leaves_no_worker_running`, `test_a_grandchild_left_running_by_a_worker_is_an_escaped_descendant` and the accepted D-M1 phase/channel controls. The real grandchild control checks parent-worker attribution, INVALID and termination. WSL remains weaker. This does not discharge F4 arbitrary outer-runner hard-kill orphan limitations. |
| 5. Historical status lines | Keep earlier status text and measured identities intact. Add explicit dated **historical status at recording** annotations and one current delivery/status section. Update the opening current status. In JSON add `current_delivery`/dated status metadata; retain the original section `status` strings as historical and explain that convention. The Task 0 environment table is a historical snapshot; xdist is installed in Task 5, not retroactively in Task 0. |
| 6. Delivered residuals shown open | A dated current reconciliation states IPC rule/measurement refresh delivered at `43eb190`, partial-index fix and quick commit switch at `66ddabf`. Retain the earlier open statements as historical. Final full/CI backstops remain open; do not label source work still required. |
| 7. Reviewer backlog contradictions/readability | Codex repaired the live registry row, first-IPC/partial-commit paragraphs, Stage B progress and Checkpoint B obligation, and labelled earlier pickup dispositions historical. Other lanes and frozen v4 remain unchanged. Read the current reviewer files, not the older observed import hashes. |
| 8. Ruling hash prefixes | Prefixes are display/provenance identifiers, never a claim of full digest verification. Keep the draft's `0d50118a…` full digest only as the explicitly dated **review snapshot read during drafting**; the reviewer file now changes. Current authority is the imported tracked ruling's dated section. Historical snapshot hashes belong to retained sealed snapshots, not a claim that current bytes still equal them. Avoid report/review self-hash cycles. |
| 9. Computed figures | Label report-derived calculations with formula, inputs and candidate; separate them from recorded assertions and Codex acceptance. Median = `1 - median(two-worker wall)/median(serial wall)`; ratio of means and mean per-pair improvement are distinct. The independently recomputed five medians/ratios agree with the draft. pairs5 remains E-source timing with ambient-load/UNKNOWN overlap qualifications, not an idle-host or delivered-HEAD measurement. |

The proposed opening sentence that both commits include every Stage B correction should instead say that **the delivered Stage B source contains them**: b0 was delivered in Task 4, the index fix and quick switch in Task 5. In the final residual table, e2 is accepted survivor evidence, cache cost is a qualified observation, and serial cache topology is a guarantee boundary, not omitted required implementation. The pre-existing non-UTF-8 reader-thread limitation, if presented as future work, points to existing `P11-FU-39` lifecycle-tooling inventory custody; no repair is commissioned by this audit.

### JSON locations and fresh checks

Use separate `location_root` and `location_folder` strings for each new handoff receipt location, reconstructed exactly as `location_root + "/" + location_folder`. Keep the seal hash and file count unchanged. Do not encode/obfuscate strings, widen the baseline, add detector exemptions or put comments in JSON. This is evidence-index metadata; no runtime or test consumer of this Plan 11.30 report manifest was found. Existing historical entries may keep their original representation. A scratch conversion of all 16 new location entries parses and passes the actual unchanged local secret scanner. The review environment initially lacked detect-secrets; the proof then used Claude's installed frozen interpreter without installation or configuration change. Scan the **assembled final report and manifest** again, as part of the seven-path preflight.

### Current-state documentation audit and remaining delivery gate

Audit covered the sole backlog/live-plan row and feature custody, roadmap, README, CONTRIBUTING, AGENTS, docs/decisions indices, ADR-016, current reviewer rulings and the report/manifest status surfaces. README/roadmap make no newly false Plan 11.30 delivery claim; the lane's CONTRIBUTING/CI already describe the delivered selection hook and product coverage commands. Main's older implementation documentation is not a source file to import into this lane. Historical rulings and source-specific evidence remain historical. Five mutable reviewer governance files are prepared for import; neither the ignored reviewer log nor `.gitattributes`, frozen plans, source, tests, configuration or lockfile belongs in this commit.

**Release composition only:** Claude may apply the bounded report corrections above and import exactly the five named reviewer files from the final audit snapshot. Return the resulting **seven-path diff and all seven final file hashes**, LF/JSON/link checks, changed-docs gate, staged-set local secret scan and fresh full-tree Ruff. No seven-path commit is released yet: the two assembled final deliverables did not exist in this packet, so their bytes have not been reviewed. This is the final byte/check gate, not a new architecture review, Task 5 retry or operator permission round. Proposed subject: `docs: record Plan 11.30 Stage B delivery before final gates`. The eventual release will authorize one normal-hook local commit; any hook failure stops for a filed disposition, never automatic retry or bypass.

### Stage B final topology and commands — confirmed

The existing operator-approved **Plan 11.30 Task 6 C1 command substitution applies to Stage B**. No full CLI implementation or renewed operator decision is required. Preserve frozen v4 and use:

```bash
uv run --no-sync pytest --cov --cov-branch --cov-fail-under=0 --cov-report=term-missing --cov-report=json:tmp/coverage/full.json -v
uv run --no-sync python -m tools.testing.coverage_products report --coverage-json tmp/coverage/full.json
```

Default/root selection and full audit depth stay intact, with one serial coverage writer per checkout. Verify automatic coverage binding points to that exact full run; use its verified explicit run-record path if ambiguous. `--cov-fail-under=0` does not waive the per-product floors or safety-module comparison. The Task 0 recorded-order gap predicate uses the same full Windows run; WSL gap performance remains informational.

After the separately released governance commit passes hooks and yields a clean tree, pin its actual HEAD and tree. Independent Windows clone `C:\worktrees\optimus-cost-agent-worktrees\optimus-cost-agent-wt-claude-p1130f` and separate WSL clone `/root/p1130-sb-t6-<UTC>` are acceptable, each detached at that pin with its own frozen environment, coverage data and run records. Verify the actual path budget, resolved interpreter/plugins, lock/config/package identities and source fingerprints before running; no force overwrite of an existing checkout. Keep the implementing lane and acceptance source unchanged throughout. Record pin/status before and after, owned-process identities and host load; never require other lanes to stop or kill stale PIDs. Start the native Windows full run with Fable's read-only final review, then run WSL after Windows finishes; do not overlap the measured test chains. Retain all validity/skip/unsupported labels and seal the new evidence. Final execution remains sequenced behind the exact governance release and successful delivery; its release may then proceed without another pre-run operator question.

No Stage B Task 6 result, complete plan closure, remote CI/safety acceptance, push, PR, merge, cleanup, service/paid-call or other Plan 11.28 activation grant is created. Codex reviewed and edited governance prose only; it implemented no code and made no project commit.


## Task 5 local delivery verified — 66ddabf

Disposition date2026-10-09 Asia/Calcutta; recorded2026-10-08 19:38:33 UTC. **ACCEPT local Task5 delivery** at `66ddabfdf5bb3acccfffe39fa45f70b4b47924ad`, parent `43eb19078a07d06e2d91d0913674b24af3616730`. Codex independently verified delivery packet `5813197f72c39980466734a59f176b3d62bdcf4b3c1103400690c6b4e0a78a12`, all39 receipt members and seal `7b89fec9469e34ac25cfc423777b0eee189217a8969527cd7ab9525866d9823e`, actual Git parent/message/exact23 paths and every committed blob against the released post-pragma table. Sealed staged/committed hash tables are identical; the only F change is the exact annotated file3dbbcb1a, whose AST equals retained F. Current lane clean, fresh full-tree Ruff passes. The bounded third-attempt release is fulfilled; failed attempts1/2 remain unchanged history. No further Task5 correction/retry is required.

All applicable normal hooks pass, including secret-scan and pytest-coverage; YAML no-files-to-check/Skipped is not a bypass. Commit profile20261008T185820-46316-861d92 verdict pass. Selected record20261008T185847-48092-647199 has exit0, full/ACTIVE/COMPLETE/native-valid, parent=not_found:ancestor_exited; raw5,305 passing call phases,19 call-skipped,21 setup-skipped, zero failed phases and eight known intentional recorder-control nodes without call rows. Preserve call-count terminology rather than inventing a captured pytest summary total. Quick audit20261008T192958-22616-a85679 independently counts77 passing calls, exit0, valid with audit_depth=quick. The hook names precommit parent43eb190, with verified staged/committed bytes binding it to delivered source; **these are not independent66ddabf full-coverage/final measurements**. No SKIP/no --no-verify.

### Next gate

Claude may proceed with the previously authorized **StageBTask6 preparation** from clean66ddabf: draft report/manifest write-up of Tasks4/5 and qualified source-bound evidence, prepare the named governance import and independent Windows/WSL checkout topology. Reviewer current-state documentation freshness audit and a separately reviewed/released governance commit remain prerequisites before the final measurement pin. This delivery ruling does not release an extra docs commit or final measurement execution, and66ddabf is not presumed to be the final starting HEAD. Do not mutate already measured candidates/report them as later-source evidence. No new routine operator approval is required merely for preparation.

Task4/C/G43eb190 and source-qualified Task5/D worker/performance mechanisms remain accepted. Required StageB independent Windows/WSL final coverage/product/gap gates, CI/safety comparison and named residual custody remain; optional UNKNOWN inter-subrun pause stays owned, not a new implementation scope. No StageB/plan closure, push/PR/merge, cleanup/process termination, paid/live-service or other held activation authority. Codex performed review/governance filing only, no implementation or Git commit.

## Task 5 commit attempt 2 — synthetic-fixture pragma and one retry released

Disposition date2026-10-09 Asia/Calcutta; recorded2026-10-08 18:45:18 UTC. Codex verified packet `407ae97242928dce1ea563ad6228a154c49a9655476e1b948a0fe284d3d992d3`, all28 failure-receipt members and seal `408df6b3df0bab402074209c7777ecd4c6fe7962b6afaa4ea3af298e5660a9fa`. Actual HEAD43eb190, working/staged F diff7cc417fe/exact23 paths unchanged. **No commit; attempt2 FAILED** solely at secret-scan. Retain this and attempt1 unchanged. YAML no-files Skipped is not a bypass; all applicable other hooks, including pytest-coverage, pass.

### Evidence and correction

Actual hook/profile verdict pass confirms F's namespace correction under Git's real hook environment. Record20261008T175524-54796-e7cd81 is full/ACTIVE/COMPLETE/native-valid, exit0, parent=not_found:ancestor_exited. Raw stream contains **5,305 passing call phases**,19 call-skipped and21 setup-skipped nodes, zero failed phases, plus eight nodes with passing setup/teardown but no call row. Those exact eight identities match the known intentional serial recorder controls retained in attempt1; do not reject them via xdist's distinct phase rule. There are5,353 represented nodes. The passing hook hides its pytest stdout summary; the packet's5,305 is a call-phase count, not an independently established final pytest passed-summary total. Delivery reports must keep that distinction. Quick audit20261008T182426-47628-a8bda8 independently recounts77 passed and passes record_validity with explicit quick qualification. Neither measurement is a new final full-coverage gate.

Scanner log/enumeration identifies exactly one Secret Keyword at test_run_profile.py:115: the literal synthetic OPTIMUS_API_KEY test-key fixture. Existing file uses inline pragmas for synthetic fixture false positives; no real credential or baseline enlargement is involved. Codex independently created before/after reviewer-owned scratch copies, proved identical Python ASTs, and ran the actual local-secret adapter with the unchanged baseline: before exit1, after exit0. No lane file was edited. This accepts the narrowly scoped annotation, not a scanner exemption for a whole file/class.

### Exact bounded correction and retry grant

**Authorize Claude to append exactly this comment to the existing fixture line115, with no other byte change:**

```python
# pragma: allowlist secret - synthetic fixture value the launch gate classifies
```

The full expected corrected file SHA-256 is `3dbbcb1a63b645f208313d16900949da6e0e87abd0748fdf945e9ed381c76aa1` (two spaces before the comment, existing LF retained). Check exact textual one-line delta and AST equality against F. No secrets baseline, scanner, hook configuration, executable behavior, selection or other source change.

**Release ONE further local normal-hook attempt of the same23 paths/subject**, conditional on: both new runner regression tests passing, fresh full-tree Ruff, staged/working diff checks, and the actual `python -X utf8 tools/local_secret_scan.py --baseline .secrets.baseline src <all23 named staged files>` returning0 after re-staging. Read and verify the scanner is scanning the intended corrected bytes; exact23 staged path set, no unstaged/extra files, hashes below must match. Add this explicit staged-set scan to future local commit preflight; it complements normal hooks and grants no bypass. Do not invoke commit until these checks pass. Stop/report any check or hook failure; no further automatic retry, SKIP or --no-verify. Preserve both failed histories and seal the new successful/failed attempt.

No extra Fable review, WSL rehearsal, checkpoint or timing run is required solely for this exact AST-identical synthetic-fixture annotation. Fable/Codex acceptance of F's underlying behavior remains; the independent scanner negative/positive proof and required controls plus actual normal hooks cover this mechanical correction. If a different change becomes necessary, stop at this bounded grant and report it. Stage all23 by name and compare committed blobs with the staged/reviewed table after success; record actual commit/parent, valid hook terminals, clean lane and sealed receipt. Local delivery remains PENDING until verified.

| Released path | SHA-256 after the exact pragma |
|---|---|
| `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json` | `b2f6d180357630ca470745c29763e03eec8bdb7cc18763b807b5002ab937ccb3` |
| `pyproject.toml` | `a95422bcae40efab3a0fec635de8f23c4c29349324d01d873b15879822fed957` |
| `tests/conftest.py` | `f718bac53f4873bd7fd967e5f7e3178c751f04b4200200ca6cb6a3ce293a5c5a` |
| `tests/profiles.toml` | `f9f841e464e40df964d801b054f34b733eb6d9d94a33ecb8f8ec5b3674f72982` |
| `tests/support/profiles_plugin.py` | `57184f3b0b860ee9df46e8ba37c8db9ff99fa68614d6c656475ed48e66302e78` |
| `tests/support/xdist_faults.py` | `09bbc557407674d77be4bd14bc81782639d54c0f1659daf0ac4c30afc34ad782` |
| `tests/unit/docs/test_docs_index.py` | `7ea75dcfd2eba750b532d7f560a05e66c51f1f7566d2beed9bde2c577d018cd9` |
| `tests/unit/docs/test_plan_directory_hygiene.py` | `3ba5de20ab303f99cf07a9967b98beec3517e468e19914a6dad3ae71a3d7b395` |
| `tests/unit/tools/run_context_child_sites.json` | `25c912d1f01144ad75bdd993c4e4da091ee34bcf0d5bcc55568286cc75567094` |
| `tests/unit/tools/test_run_context_xdist.py` | `d25c80f1295e709d3eea7e065921863b281d1fb38618842c3310dd49ec1b225e` |
| `tests/unit/tools/test_run_context_xdist_probes.py` | `092c4da9fa68cc45ccadfc0657ffdbfdc073318c2210d1d94777858934f5db8c` |
| `tests/unit/tools/test_run_profile.py` | `3dbbcb1a63b645f208313d16900949da6e0e87abd0748fdf945e9ed381c76aa1` |
| `tests/unit/tools/test_test_profile_selection.py` | `ecf84cf8531ff905ec64469d198d2a1774fbb543af0c4516c6674131371b30d5` |
| `tests/unit/tools/test_test_profiles.py` | `dc548b47aaaac9789da1ca3f4aec91280eda6b3dda8feebacbb12b8ad3c3c539` |
| `tests/unit/tools/test_tracked_repository_files.py` | `3af1b6c9def2ec104614cc3ed35cae39607036366b7cf9f623c89e3a31ed857e` |
| `tools/doc_paths.py` | `1320fca6bb32bb1f96bce970a66a8f5edbbf20140e580f7a5b3951d0016c208d` |
| `tools/testing/run_context.py` | `bc78a5001ead1f84a802532e2a43618ce431a2bba44794c739023c190a19fe76` |
| `tools/testing/run_context_records.py` | `ebd439769efbef5c4bd98c9d28eec716d06e4fa9c8369bde37e83c424e4bf961` |
| `tools/testing/run_context_xdist.py` | `550723968c840a67d9765f03a97e561b773cc132b157ddf8a3280b2e9801c5ef` |
| `tools/testing/run_profile.py` | `1039200f8c31a7f0a62147ba9cf1963686908a2d9086346b3b67a159747562da` |
| `tools/testing/test_profiles.py` | `e82b55dfdc2f05425bcb9d80370cced4f4c7b710aedcfb1afcfe40262b348f4c` |
| `tools/tracked_repository_files.py` | `0fbcb6f51ba2f93804b1c4a974d99c46e4aab84750892b2ff599f75267a35ddc` |
| `uv.lock` | `a1a25b3afa02e8ff5e660a6a5a7f27980b58d1f6e60811fe083f689852297a5b` |

Task4/C/G and Task5/D source-qualified worker/performance acceptance remain settled. StageBTask6 preparation follows successful delivery; reviewer current-state documentation audit and separately released governance commit precede final pin/measurements. No plan closure, remote push/PR/merge, cleanup/process termination or other activation authority. Codex reviewed/filed governance and tested scratch copies only, no implementation or Git commit.

## Task 5 candidate F — correction accepted; one 23-path retry released

Disposition date2026-10-08 Asia/Calcutta; recorded2026-10-08 17:51:59 UTC. Codex verified packet `db1584c441c079f8d6670b166ba4078b284ec8db17eee98d1044991c58bc2c88`, all40 members and seal `a693e9b01ae731abe79de9cfd5f2db6fbaad829554715e3853fc5229c0eb94be`. Current HEAD43eb190 remains unchanged; working binary diff `7cc417fecbfac10c7ec8aa93c8b9c5dfbf4ab8973050727e98ccbb7c1227df71` is F, staged binary diff2bd48b7d is still E. Exactly23 total paths, exactlyfour unstaged correction paths. All23 current/table/retained WSL bytes match F. Prior failed29-member receipt remains immutable.

**ACCEPT the OptionA correction and affected hook-environment compatibility evidence on F.** Actual E-to-F delta contains only two shared constant values/comment, scanner test names, two runner regressions plus inherited-variable table, and one nested_pytest child-site entry. No product/launch-policy change, legacy alias, selection, xdist or cache change. Root ownership, missing-index refusal and forwarding bodies remain unchanged. Fable narrow review SOUND read; no further finding. Retained RED correctly shows both real-gate/nested ACP failures; its nested pytest exits1 while acp_main inside it returns2, so do not confuse inner product exit with outer pytest exit.

Codex independently ran both new regression controls on native Windows using F's own frozen environment and on the real F WSL clone: all pass. An initial reviewer-native nested probe used the reviewer's interpreter lacking pytest-cov and failed argument parsing at --no-cov before test execution; it was a reviewer environment error, not F failure. Repeating with F's interpreter passes. Fresh full-tree Ruff and HEAD diff check pass; retired OPTIMUS_COMMIT_INDEX names are absent from current tools/tests. The guard judges newly added metadata, demands forwarding and leaves inherited product/MAIN-5 variables intact. The real-gate test excludes inherited MAIN-5 OPTIMUS_TEST_VENV from its product gate call explicitly; that established boundary is not silently reclassified by this correction.

Retained affected receipts pass: Windows rehearsal138/6, controls269, gates336, Ruff/diff clean and identity unchanged; realWSL rehearsal144 and controls261/8 in both TMPDIR states. Rehearsal script inspected: four failed ACP files plus real hook controls/new regressions through actual subrun_environment with Git's index input; both platforms record TEST_RUN_COMMIT_INDEX_FILE/ROOT, zero namespace refusals. This establishes the affected boundary, not a successful whole commit. The actual normal-hook retry remains necessary. A claim that hooks categorically cannot be invoked without creating a commit is not needed for acceptance; no extra rehearsal is commissioned.

### Exact one-attempt retry release

Under existing operator delegation, **release Claude to re-stage all23 named paths below and make ONE local normal-hook commit of F**, with the same subject `test: add Plan 11.30 core-only xdist, index scanning and quick commit audits (Task 5)`. Explicitly replace staged E with F; before invoking commit verify exact staged path set, working and staged hashes against the F table, nothing unstaged/extra, fresh Ruff and normal diff checks. No governance import or other source change. No SKIP/no --no-verify. Stop/report any precommit or hook failure, preserve receipts; no automatic further retry. After success verify actual commit/parent, all23 committed blobs equal staged/reviewed bytes, clean lane and normal-hook terminal results, then seal the delivery receipt. Delivery remains PENDING until verified.

| Released path | SHA-256 of candidate F bytes |
|---|---|
| `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json` | `b2f6d180357630ca470745c29763e03eec8bdb7cc18763b807b5002ab937ccb3` |
| `pyproject.toml` | `a95422bcae40efab3a0fec635de8f23c4c29349324d01d873b15879822fed957` |
| `tests/conftest.py` | `f718bac53f4873bd7fd967e5f7e3178c751f04b4200200ca6cb6a3ce293a5c5a` |
| `tests/profiles.toml` | `f9f841e464e40df964d801b054f34b733eb6d9d94a33ecb8f8ec5b3674f72982` |
| `tests/support/profiles_plugin.py` | `57184f3b0b860ee9df46e8ba37c8db9ff99fa68614d6c656475ed48e66302e78` |
| `tests/support/xdist_faults.py` | `09bbc557407674d77be4bd14bc81782639d54c0f1659daf0ac4c30afc34ad782` |
| `tests/unit/docs/test_docs_index.py` | `7ea75dcfd2eba750b532d7f560a05e66c51f1f7566d2beed9bde2c577d018cd9` |
| `tests/unit/docs/test_plan_directory_hygiene.py` | `3ba5de20ab303f99cf07a9967b98beec3517e468e19914a6dad3ae71a3d7b395` |
| `tests/unit/tools/run_context_child_sites.json` | `25c912d1f01144ad75bdd993c4e4da091ee34bcf0d5bcc55568286cc75567094` |
| `tests/unit/tools/test_run_context_xdist.py` | `d25c80f1295e709d3eea7e065921863b281d1fb38618842c3310dd49ec1b225e` |
| `tests/unit/tools/test_run_context_xdist_probes.py` | `092c4da9fa68cc45ccadfc0657ffdbfdc073318c2210d1d94777858934f5db8c` |
| `tests/unit/tools/test_run_profile.py` | `8552c1bd79f10cc89d735e4e1a98fc9aba582289687ae2cedb9f2e1f5b2ff0cd` |
| `tests/unit/tools/test_test_profile_selection.py` | `ecf84cf8531ff905ec64469d198d2a1774fbb543af0c4516c6674131371b30d5` |
| `tests/unit/tools/test_test_profiles.py` | `dc548b47aaaac9789da1ca3f4aec91280eda6b3dda8feebacbb12b8ad3c3c539` |
| `tests/unit/tools/test_tracked_repository_files.py` | `3af1b6c9def2ec104614cc3ed35cae39607036366b7cf9f623c89e3a31ed857e` |
| `tools/doc_paths.py` | `1320fca6bb32bb1f96bce970a66a8f5edbbf20140e580f7a5b3951d0016c208d` |
| `tools/testing/run_context.py` | `bc78a5001ead1f84a802532e2a43618ce431a2bba44794c739023c190a19fe76` |
| `tools/testing/run_context_records.py` | `ebd439769efbef5c4bd98c9d28eec716d06e4fa9c8369bde37e83c424e4bf961` |
| `tools/testing/run_context_xdist.py` | `550723968c840a67d9765f03a97e561b773cc132b157ddf8a3280b2e9801c5ef` |
| `tools/testing/run_profile.py` | `1039200f8c31a7f0a62147ba9cf1963686908a2d9086346b3b67a159747562da` |
| `tools/testing/test_profiles.py` | `e82b55dfdc2f05425bcb9d80370cced4f4c7b710aedcfb1afcfe40262b348f4c` |
| `tools/tracked_repository_files.py` | `0fbcb6f51ba2f93804b1c4a974d99c46e4aab84750892b2ff599f75267a35ddc` |
| `uv.lock` | `a1a25b3afa02e8ff5e660a6a5a7f27980b58d1f6e60811fe083f689852297a5b` |

No new CheckpointD or timing pairs required solely for this reviewed four-file correction. Unchanged worker/selection/performance mechanisms retain the source-qualified E acceptance; do not relabel pairs5 as a newly measured F timing run. Task4/C/G43eb190 remains settled. After successful local delivery, prepare StageBTask6 under the prior conditions; reviewer current-state docs audit and separately released governance commit precede the independent final measurement pin. No final execution, plan closure, remote push/PR/merge, cleanup/process termination or other activation grant. Codex performed review/governance only, no implementation or Git commit.

## Task 5 commit attempt 1 — failed; namespace correction authorized, retry held

Disposition date 2026-10-08 Asia/Calcutta; recorded2026-10-08 16:21:35 UTC. Codex verified packet `4c41cb0e2c14fe03243776c10a484b4a4f77dd34ea78277db1837182bdc1ed8a`, all29 receipt members and seal `c41851de8bf36b6918d3b2dc098c047a7dc868437b151eeec24279877719e872`. No commit: actual HEAD remains43eb190; working and staged binary diffs both2bd48b7d, exact23 paths staged. The one-attempt release was consumed by this failed attempt; **no retry is currently released**. Preserve all failure receipts unchanged.

Raw selected run20261008T153230-55460-6de6f3 independently recounts69 failed/5,242 passed/40 skipped, exit1. Its record remains COMPLETE/ACTIVE/full/native-valid with parent=not_found:ancestor_exited; record validity does not turn failed tests into PASS. Quick audit20261008T161048-37976-08a2f7 recounts77 passed, exit0, valid with explicit audit_depth=quick. Eight other hooks pass; pytest-coverage fails. This is a real harness defect, not timing contamination or a reason to bypass a hook.

### Diagnosis and bounded correction

The actual runner forwards GIT_INDEX_FILE through `OPTIMUS_COMMIT_INDEX_FILE` and `OPTIMUS_COMMIT_INDEX_ROOT`. Codex independently called subrun_environment with a synthetic index input (no process environment or index changed): both newly injected names are rejected by the real launch classifier. Product launch_gate rejects unknown OPTIMUS_* names, and the hook traceback names UNCLASSIFIED_VARIABLE:OPTIMUS_COMMIT_INDEX_FILE. The real partial-commit control covered scanner reach but not an ACP launch under the forwarded environment. Implementation, Fable and Codex review all missed that integration boundary; earlier source-specific evidence remains retained, but complete hook compatibility was not established.

**Select Option A and authorize Claude's test-first correction:** rename the two private harness metadata keys to `TEST_RUN_COMMIT_INDEX_FILE` / `TEST_RUN_COMMIT_INDEX_ROOT`, updating their scanner/runner consumers and tests. Keep the existing resolved-root ownership, temporary-index selection, missing-index refusal and foreign-repository isolation. No legacy OPTIMUS_* alias or launch-policy exemption: this interface has not been delivered. Do not edit product source, launch_gate or its classification registry; do not strip metadata before the scanner can consume it. This is a bounded test-harness correction within existing Task5 scope, not new operator policy.

Use the existing23-path scope: the shared constants in tools/tracked_repository_files.py, any necessary runner forwarding/comment adjustments, and regression controls in the already-released tool test files. Do not add unrelated tooling or change selection/worker/cache behavior. If another path proves necessary, identify it for review rather than silently widening commit scope.

Required evidence: RED on E against the real launch-gate inherited-environment path and an affected ACP entry point under runner-produced commit-index environment; GREEN after rename. Add a discriminating guard on names newly injected by subrun_environment with explicit GIT_INDEX_FILE (do not ban legitimate inherited product variables or established MAIN-5 metadata). Run affected scanner/runner/child-site controls on native Windows and real WSL, preserving TMPDIR/identity qualifications and source pins. Rehearse all four failed ACP files (test_main_wiring, test_launch_approval_cli, test_main_check_config, test_main_debug_trace) plus the real partial-commit hook control with GIT_INDEX_FILE supplied through the actual runner forwarding path. Preserve real scanner/index semantics and the root conftest; never weaken launch classification to get GREEN. Current gates and fresh full-tree Ruff/diff checks are required. Fable's narrow corrected-source review precedes Codex verification and a separately filed bounded normal-hook retry release.

No new CheckpointD chain or timing pairs are commissioned solely for this metadata rename and affected controls. Task5/D correctness/worker/performance acceptance on E remains source-specific settled evidence; verify the correction does not alter selection or xdist logic before carrying forward unaffected claims. The namespace/hook compatibility and local delivery are held until corrected evidence and successful released commit. Any broader behavior change invalidates this no-repeat disposition and must be reviewed. No automatic retry, SKIP or --no-verify is granted now.

StageBTask6/final pin remain dependent on delivery and the existing documentation audit/governance release. No push/PR/merge, plan closure, cleanup or process-termination authority. Foreign correctness-test overlap is disclosed and is not the demonstrated cause; it grants no timing claim. Codex performed review/governance filing only, with no implementation or Git commit.

## Checkpoint D / Task 5 — E accepted; exact 23-path local commit released

Disposition date 2026-10-08 Asia/Calcutta; recorded 2026-10-08 15:23:56 UTC. Source: operator-relayed pairs5 receipt SHA-256 `df3376ead5179d452bc7b73edddf34221a1fee35c28e6778507b997ebc45c064`; Fable review copy `0baac9baf4b975358ca2c9fc690ea268edbf4b8ac97ca81fb77d5387cfe0dc63`. Codex independently verified every one of89 timing-evidence members and seal `f00f585150a8a316b06f413a63e6ac0e58c67bada9ffd960a62e1d008bd3a35d`, current base HEAD `43eb19078a07d06e2d91d0913674b24af3616730`, binary diff `2bd48b7d2702dd978ec3abbf0a65108afab757442fd1109d0f3568b435d83cd2`, exactly23 paths and all23 pre/post/current hashes equal to E's original recorded table. Four new files remain intent-to-add/index-visible. Fresh full-tree Ruff passes. This supersedes the remaining timing hold; prior D-M1/correctness acceptance and all failed/loaded histories remain unchanged.

### Timing and Task5 acceptance

**ACCEPT Task5 and CheckpointD on E**, including the partial-commit scanner correction and profile-specific changed-input quick-audit switch already reviewed within this source. Codex independently recomputed serial298.708/277.770/268.679seconds and two-worker247.869/204.983/200.993seconds: median serial277.770, two-worker204.983, improvement **26.2040537135percent >=20percent PASS**. The ratio-of-means improvement is22.6362675811percent; the arithmetic mean of per-pair improvements is22.8052762367percent. Both definitions are explicitly distinguished; acceptance uses the specified median, not a requirement that each pair individually exceeds20percent (pair1 is17.02percent).

All9 sealed terminal records pass the actual E record_validity predicate; all12 recorded-order serial/per-worker gap checks independently pass, with zero negative gaps. Each of six invocations covers the identical4,104-node set; two-worker subruns are disjoint2,747+1,357. Each serial run4,067 passed/37 skipped; each parallel subrun2,737/10, serial remainder1,330/27. Native Windows xdist valid and parent=not_found:ancestor_exited qualifications remain. The shell caller walls include runner/collection work and the entire inter-subrun pause; no cost is subtracted. Earlier independently accepted exact-E Windows/WSL checkpoint/control evidence supplies correctness, including WSL weaker capability labels; this timing receipt does not extend it to other source identities.

Fable SOUND WITH AMENDMENTS is read and both receipt wording amendments are present. Fresh identity/CPU observations show the disclosed owned diagnostic chain absent; the frozen-environment dry-run reports no changes. Host load is disclosed before27.2percent and after15.2percent; TextInputHost consumes about one core. A foreign pytest appears at the close of load-pre; its reported end before the pairs is explicitly unreceipted, and foreign overlap during the run remains UNKNOWN. **Accept these ambient-load qualifications; do not call pairs5 idle or wholly unloaded.** The previous request targeted removal of the known stray owned diagnostic load, absence of owned overlap and honest ambient observations, not permission to stop foreign processes or a requirement to establish machine-wide idleness. No correction for an assumed direction of bias, no repeat-to-idle round, and no more pairs/checkpoint runs are required for this acceptance.

The31.5second seam in pair1 is charged against caller wall and remains cause UNKNOWN, not a failed test or timing invalidity. No process-exit timestamp establishes whether time was controller shutdown or next launch. `P11-FEAT-TEST-PROFILES` owns optional unscheduled diagnosis of this recurring inter-subrun observation; it is not a required-functionality deferral, source-fix grant or closing blocker. Preserve the pair1 result and every historical FAILED/INVALID/loaded run unchanged.

### Exact bounded local commit release

Under the settled operator delegation, **release Claude to make one local commit of exactly the23 paths and bytes below**, on the existing implementing branch, with subject `test: add Plan 11.30 core-only xdist, index scanning and quick commit audits (Task 5)`. Stage every path by name, including all four intent-to-add files. No governance file, frozen plan or extra implementation change is included. Compare both working and staged blob hashes to this table and verify the exact staged path set before committing. Normal hooks only: no SKIP and no --no-verify. Fresh Ruff has passed on these bytes; perform ordinary required precommit checks/diff checks without another checkpoint rehearsal.

If any hook or precommit check fails, stop and report with retained receipts; this paragraph grants neither an automatic retry nor a bypass. After success, record actual commit/parent, normal hook command/exits/terminal records, staged-to-committed equality of all23 blobs and clean lane status; seal the delivery receipt before temporary records can be pruned. Task5 local delivery remains PENDING that verified successful commit, and these dirty-candidate runs are not final-commit full-coverage evidence.

| Released path | SHA-256 of reviewed bytes |
|---|---|
| `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json` | `b2f6d180357630ca470745c29763e03eec8bdb7cc18763b807b5002ab937ccb3` |
| `pyproject.toml` | `a95422bcae40efab3a0fec635de8f23c4c29349324d01d873b15879822fed957` |
| `tests/conftest.py` | `f718bac53f4873bd7fd967e5f7e3178c751f04b4200200ca6cb6a3ce293a5c5a` |
| `tests/profiles.toml` | `f9f841e464e40df964d801b054f34b733eb6d9d94a33ecb8f8ec5b3674f72982` |
| `tests/support/profiles_plugin.py` | `57184f3b0b860ee9df46e8ba37c8db9ff99fa68614d6c656475ed48e66302e78` |
| `tests/support/xdist_faults.py` | `09bbc557407674d77be4bd14bc81782639d54c0f1659daf0ac4c30afc34ad782` |
| `tests/unit/docs/test_docs_index.py` | `7ea75dcfd2eba750b532d7f560a05e66c51f1f7566d2beed9bde2c577d018cd9` |
| `tests/unit/docs/test_plan_directory_hygiene.py` | `3ba5de20ab303f99cf07a9967b98beec3517e468e19914a6dad3ae71a3d7b395` |
| `tests/unit/tools/run_context_child_sites.json` | `688220989fa92ad1bca362370858060b268029eff6fe1b1bf21124f92791c125` |
| `tests/unit/tools/test_run_context_xdist.py` | `d25c80f1295e709d3eea7e065921863b281d1fb38618842c3310dd49ec1b225e` |
| `tests/unit/tools/test_run_context_xdist_probes.py` | `092c4da9fa68cc45ccadfc0657ffdbfdc073318c2210d1d94777858934f5db8c` |
| `tests/unit/tools/test_run_profile.py` | `ad0cc03d25d32f3eec75a1244ac4c60097d4aa4b6b32795fe2adbeaa3cc3ef89` |
| `tests/unit/tools/test_test_profile_selection.py` | `ecf84cf8531ff905ec64469d198d2a1774fbb543af0c4516c6674131371b30d5` |
| `tests/unit/tools/test_test_profiles.py` | `dc548b47aaaac9789da1ca3f4aec91280eda6b3dda8feebacbb12b8ad3c3c539` |
| `tests/unit/tools/test_tracked_repository_files.py` | `348f039d1315ec54a8566ccd312981a754d5a1ec400be7ace58ac0cf1dcb7b17` |
| `tools/doc_paths.py` | `1320fca6bb32bb1f96bce970a66a8f5edbbf20140e580f7a5b3951d0016c208d` |
| `tools/testing/run_context.py` | `bc78a5001ead1f84a802532e2a43618ce431a2bba44794c739023c190a19fe76` |
| `tools/testing/run_context_records.py` | `ebd439769efbef5c4bd98c9d28eec716d06e4fa9c8369bde37e83c424e4bf961` |
| `tools/testing/run_context_xdist.py` | `550723968c840a67d9765f03a97e561b773cc132b157ddf8a3280b2e9801c5ef` |
| `tools/testing/run_profile.py` | `1039200f8c31a7f0a62147ba9cf1963686908a2d9086346b3b67a159747562da` |
| `tools/testing/test_profiles.py` | `e82b55dfdc2f05425bcb9d80370cced4f4c7b710aedcfb1afcfe40262b348f4c` |
| `tools/tracked_repository_files.py` | `734342a9bf6ac75eacbfcda8d36dfb58c65053e07c810ed0c74fbe8bdf5fe892` |
| `uv.lock` | `a1a25b3afa02e8ff5e660a6a5a7f27980b58d1f6e60811fe083f689852297a5b` |

### Next gate and authority boundaries

After the successful clean local commit, Claude may prepare the already-required StageBTask6: report/manifest write-up and named governance import, plus independent final Windows and WSL checkout preparation. The reviewer must complete the current-state documentation freshness audit and separately release any governance commit before the final measurement pin. Do not start final measurements from an assumed Task5 pin while pending required docs would change HEAD; no pre-pin governance commit or StageBfinal execution release is bundled here. No additional routine operator reconfirmation is required for the named local Task5 commit.

Task4/C/G/local43eb190 remains accepted. Full-depth checkpoint/final/coverage protection, independent final Windows/WSL checkouts, CI/safety comparison and existing named residual obligations remain. No StageB/plan closure, remote push, PR, merge, cleanup, process termination, paid/live-service or other Plan11.28 activation authority is granted. Codex performed review/governance filing only, no implementation or Git commit.

## Checkpoint D / Task 5 — E correction accepted; unloaded timing remains

Disposition date 2026-10-07 Asia/Calcutta; recorded 2026-10-07 12:27:23 UTC. Codex independently verified the correction packet SHA-256 `461d41faee8066fb6e3a6616022306db704e21cc0562f2743fe4175b12d04ae9`, disclosure addendum `43c3ade42c92c9c2ecd0f6dd7b3cdbd1c3391f33258be06233ef752aa36d9008`, all 2,356 evidence members and seal `62c8c21adc459bba979b79c4af6d5b30a8796af4273606eca7b24533002ed7e3`. Actual lane remains HEAD `43eb19078a07d06e2d91d0913674b24af3616730` plus diff `2bd48b7d2702dd978ec3abbf0a65108afab757442fd1109d0f3568b435d83cd2`, exactly the existing 23 paths, four new files intent-to-add. No governance import or commit is released by this ruling. Frozen v4 remains unchanged.

### D-M1 and correctness disposition

**D-M1 CLOSED; E's Checkpoint D correctness evidence ACCEPTED.** The existing controller now retains outcome/channel facts, requires a call after passing setup, refuses calls after skipped/failed setup, checks selected-node membership and single-worker node ownership, and records claim/channel disagreement. Serial recorder controls are untouched. Attribute real reports to their xdist channel; fallback to the claim is confined to synthetic controls without a channel. Installed xdist's channel contract was independently reviewed by Fable; no new stream redesign is required.

Codex read Fable's final E SOUND review and the retained RED/GREEN and seven-mutant logs. Seven bounded direct controls independently pass on native Windows and the actual E WSL clone: the three original balanced counterexamples, complete-run validity, legitimate setup skip/failure, unexpected call, and channel attribution. These are direct unit-model assertions, not additional real-worker executions. The retained real nested fault controls exercise missing_call and foreign_node through actual two-worker sessions, checking INVALID, the named problem, nonzero exit and matching recorded exit. RED retains both real false-pass histories; GREEN records44 passed. Fresh full-tree Ruff passes. No implementation was changed by Codex.

Raw E main checkpoint records independently recount Windows5,312 passed/40 skipped plus77 full audits and three373-passed/8-skipped concurrency repeats; each repeat is contained in the retained audit load window. WSL5,259 passed/93 skipped plus77 full audits. All named main/core/pair records pass the actual E record_validity predicate. Core partition remains4,104=2,747 parallel+1,357 serial; Windows parallel2,737 passed/10 skipped, serial1,330/27; WSL parallel2,747 passed, serial1,317/40. Retain native Windows parent=not_found:ancestor_exited qualifications and WSL native/guard/parent unsupported with xdist=weaker. Retained23 WSL file hashes match the current lane, and Windows before/after identities agree. Gates336, Windows controls622, WSL controls508/47 in both TMPDIR states are retained passing receipts. The background load qualifies the environment; passing executions do not prove that every possible unloaded interleaving would also pass.

### Stray-process disclosure and timing disposition

The separate addendum supersedes the packet's claim that nothing else of Claude's was running on the host. It reports one diagnostic process consuming approximately one core throughout E's chain and pairs4, also through historical D timing. Preserve both originals and the addendum; do not rewrite sealed history or call the historical pairs unloaded. Codex's current read-only Get-Process and elevated Win32_Process inventory found none of the five disclosed PIDs. This establishes absence at that check, not their historical identity, termination mechanism or blanket cleanup authority. **Do not execute the stale five-PID Stop-Process list:** PIDs can be reused. Any later termination needs fresh process identity and ownership verification and its existing applicable authority; no kill or cleanup is granted here.

Codex recomputed pairs4 serial302.639/285.049/283.997seconds and two-worker208.253/218.128/220.092seconds: median improvement **23.477016percent**, mean **25.836397percent**. All12 recorded-order serial/per-worker decile predicates pass, with zero negative gaps; all paired records are valid. Keep this as an actual measured loaded-host result. The addendum's expectation that load understates the benefit is unmeasured: constant load can affect collection, serial tests, workers and scheduling differently. No direction or adjustment is accepted.

**Overall Task5/CheckpointD acceptance and the23-path commit remain HOLD solely for unloaded matched performance confirmation.** This narrows the previous D-M1 hold; it does not reopen the accepted code correction or demand another checkpoint/full suite.

Under existing Task5 evidence authority, expressly commission the offered **pairs5: three matched native Windows serial/two-worker core pairs on unchanged E**, about25 minutes, new immutable label/seal. Before running, verify clean candidate identity relative to E's recorded dirty diff (HEAD/diff/status and23 file hashes, new files index-visible), frozen environment/config and absence of this stray load using fresh process identities/CPU observations. Do not kill foreign processes, require other lanes to stop, or claim an idle machine from a PID list alone. Avoid overlapping owned diagnostics/WSL/test runs; record ambient host load before/after. Keep the same selection/partition, flags and worksteal configuration, include both collections and every inter-subrun pause in caller wall, preserve all exits/terminal records and repeat the existing node/record/gap checks. No source change, new optimization or selection adjustment is authorized by this timing grant.

Retain pairs4 and every earlier FAILED/INVALID/qualified attempt. Report all three pairs and the median >=20-percent predicate without a load-direction correction. Fable reviews the short new timing receipt/addendum disposition, then Codex verifies it and decides the local commit; no new whole-source Fable round or operator permission is needed solely for this unchanged-source timing confirmation. If the target is missed or a record/source check fails, preserve the result and report; no retry-to-green or hook bypass grant. No further Windows/WSL Checkpoint D chain is required unless source changes or new evidence supplies a reason.

Task4/C/G/local43eb190 remains settled; the partial-index fix and quick changed-input audit mechanism remain accepted within held E. StageBTask6 and its governance import follow successful separately released Task5 delivery. Independent final Windows/WSL checkouts, CI/safety comparison, publication/activation/cleanup and all named residual obligations remain. This ruling is an agent-selected evidence decision under existing operator delegation, not new operator policy or a frozen-plan revision. Codex performed review/governance filing only; no process termination, implementation, Git commit or external message.

## Checkpoint D / Task 5 — candidate D requires phase-integrity correction

Recorded 2026-10-07 08:45:34 UTC (Asia/Calcutta disposition date2026-10-07). Source: operator-relayed Claude update and packet SHA-256 `3779620eddfc585a307ae53ad55eb91b9571c11405edbead411333519b437405`. Candidate D is HEAD `43eb19078a07d06e2d91d0913674b24af3616730` plus binary diff `e24d24252795ad2fb0a8042a8fba23f5cd0e5e822f9ed257d7a7de01d4d3582f`, exactly23 paths with four new files intent-to-add. Codex verified all1,497 evidence members and seal `de697a9d2452aba68fd7e5513a3a529bbd48e19b7eedb93ae226c61c89a42244`, actual lane base/diff/status and all23 current WSL-D/Windows bytes. Fresh full-tree Ruff passes. Read Fable's three rounds and final D SOUND; this new independent finding remains to resolve. Frozen v4 and Task4/C/G acceptance/delivery are unchanged.

### D-M1 — Controller phase counts do not establish node execution or worker attribution (major)

`tools/testing/run_context_xdist.py::Controller.phase` stores only `(node,when) -> worker`, while `verdict` requires setup and teardown presence and compares per-worker totals. It neither requires a call after a passing setup, nor verifies that a node's phases all belong to one worker, nor rejects reports for nodes outside the agreed selection. Consistent totals can therefore hide incomplete execution or incorrect attribution. The gap is in the new controller's acceptance predicate, not a claim that the retained successful runs actually exhibited these faults.

Codex used candidate D's own `_valid_run` fixture from `test_run_context_xdist.py`, which builds two signed worker records, four agreed selected tests and12 passing phases with independently-confirmed-member flags. Its baseline verdict is valid. Three isolated in-memory counterexamples, reproduced on native Windows and real WSL-D, all also return **valid with no problems**:

| Counterexample | Changes to the valid fixture | Current verdict |
|---|---|---|
| Call omitted after passing setup | Delete `(node_key(test_0),call)`; reduce gw0 received and worker-output phase total from6 to5. Setup/teardown remain passing. | valid |
| Wrong worker attribution | Swap only test_0 and test_2 call-phase workers (gw0/gw1); all node phases and per-worker totals remain present and balanced. | valid |
| Unselected test report | Feed a call report for `test_foreign` from expected gw0, and increment its worker-output total to match received. | valid |

These are executable unit-model fault injections against the actual candidate verdict, not fabricated real worker executions or evidence of a hostile test. Reviewer-owned temporary record fixtures were removed; no implementation/installed environment was changed. The current missing-phase control tests teardown loss and mismatched totals but omits these balanced cases. Existing unknown-worker rejection does not reject an unknown node reported by a known worker.

**Bounded test-first correction:** preserve enough per-node phase facts/outcomes to require the valid phase sequence appropriate to setup's actual result, one worker ownership for every phase of a node, and exact agreed selected-node membership. A passing setup requires a call; genuine setup skip/failure may legitimately omit it. Retain setup/teardown checks, duplicate/lost-phase detection and valid skipped/failed test handling. Do not apply an unconditional call requirement to existing serial recorder-stream controls or invent a broad omission exemption. Reject unexpected selected-node phases and mixed ownership even when counters balance. Add negative controls for allthree cases plus legitimate setup-skip/failure and complete-run controls; at least bounded real xdist fault coverage must show INVALID forces a non-zero exit through the controller/runner, not only a returned string. Use the existing controller seam, no new architecture or other-lane scope.

### Retained executions and timing

Codex recomputed Windows CheckpointD raw main5,304 passed/40 skipped, full audit77 passed, and three supported-load repeats373 passed/8 skipped each. Full-depth records pass the current validator with parent=not_found:ancestor_exited. Windows core partition is4104=2747parallel+1357serial; core-parallel2737 passed/10 skipped and remainder1330 passed/27 skipped, with valid native xdist verdict under the current predicate. WSL candidateC full checkpoint raw main5,251 passed/93 skipped plus77audit and core2747parallel passed plus1317serial passed/40 skipped are retained as actual passing executions, with native/guard/parent unsupported and xdist=weaker qualifications.

The sealed C-to-D patch comparison changes only `test_run_context_xdist.py` and `test_tracked_repository_files.py`, strengthening tests without production change. D's focused WSL39passed/1skipped in both TMPDIR states and23 current byte matches qualify that test-only delta; the full WSL chain remains explicitly C-source evidence, not a silently relabelled exact-D run. This bounded composition is acceptable for these unchanged production paths; D-M1 remains an independent blocker.

Codex recomputed pair3 wall figures: serial317.297/314.818/312.165seconds and two-worker231.156/260.334/232.359seconds, median improvement **26.1926percent**, mean **23.3438percent**. All paired terminal records pass the current validator. This meets the numeric20percent target on D but does not override D-M1 or transfer to a later corrected production candidate. The roughly30second inter-subrun pause in pair2 is included in the parallel caller wall measurement, so it is charged rather than removed; attribution of its cause remains UNKNOWN. The reported12 gap checks remain retained report evidence. Earlier13.5percent attempt is FAILED history,23.6percent is pre-Fable source history, and the isolated19percent comparison is not a matched pair. Preserve all failed Windows/WSL and rate-limit histories.

### Requested dispositions and next gate

1. **Task5 / CheckpointD acceptance: HOLD for D-M1.** Current Fable SOUND and passing runs remain honestly retained. Controller/job/metadata guard architecture, conservative serial partition, worksteal scheduling and serial-only coverage are acceptable mechanisms in principle. Coverage sharding is unnecessary when every coverage gate remains serial; no coverage writer overlap or weakening is authorized. Cosmetic synthetic crash `???` adds an INVALID problem and needs no fix merely for cleaner wording. `_run_record` own-root preference/ambiguity refusal is accepted.
2. **Partial-commit scanner correction: ACCEPTED within the reviewed candidate.** Named commit-index propagation scoped to the owning repository, missing-index refusal, inventory-site controls and independent Fable real-hook probes address the recorded residual. No optional index-selection bypass is approved. **Quick commit-audit mechanism: ACCEPTED within the candidate** after Task4G: retain only changed-input-reached current audits at quick, never through broad fallback; full checkpoint/final/coverage protection remains. Neither acceptance is a separate immediate commit/activation grant while the combined candidate is held.
3. **23-path local commit: HOLD.** No commit, SKIP or --no-verify release. Under existing implementation authority, Claude may make the bounded D-M1 correction test-first, preserve failed attempts, obtain Fable's narrow correction review before expensive validation, and verify affected controls on native Windows and real WSL, current gates/freshRuff, corrected-source normal CheckpointD on both platforms and three matched Windows core pairs on the actual corrected candidate. New files must remain index-visible. No extra intermediate full suite or routine operator approval round is commissioned. Speed missing its target remains unaccepted; do not modify selection or evidence to manufacture a pass.
4. Task4/C/G and delivered43eb190 remain settled. StageBTask6 preparation/final delivery is dependent on corrected Task5/D acceptance and its separately released successful commit. Governance imports remain in the existing StageBTask6 docs/report follow-up. Independent final Windows/WSL gates, CI/safety comparison, publication/activation/cleanup holds and named residual owners remain. No plan closure or new external authority.

Codex performed architecture/review and governance filing only; no implementation or project commit.

## Task 4 local delivery verified — 43eb190

Disposition date 2026-10-07 Asia/Calcutta; recorded 2026-10-06 21:17:42 UTC. Source: operator-relayed Claude delivery note SHA-256 `d193aa70296d9b8cf88e23fb27e1c34111ac63222be50bd25025ec3e172e6e9c`. **Task4 local delivery is ACCEPTED at `43eb19078a07d06e2d91d0913674b24af3616730`**, parent `1c7be2da61263e6fa47092346f65218104388740`. This closes the delivery-pending item and fulfills the bounded19-path retry grant; no additional Task4 correction or commit release is required.

Codex independently verified all27 sealed receipt members and seal `9fdae92adbf18ce7509ebaaa9974b267fb6cabf99daa17f0f221219cf8a3760f`, actual Git parent/message and exact19 committed paths, all18 original committed blob hashes against the C7c reviewed table, and the map's sole semantic delta. The added entry equals the accepted `_pytest#1` classification; deleting it yields the parent map (82 to83 sites). Staged/committed hash receipts are identical, and the current lane is clean. The reviewed cache/depth implementation is unchanged. Fresh full-tree Ruff passes; retained pre-retry controls report202 guard/proof/reuse passed and336 gates passed with identity unchanged. Actual normal hook output passes every applicable hook; YAML is correctly no-files-to-check/Skipped, not an authorized bypass. No SKIP or --no-verify used.

Raw selected-run phases `20261006T192622-56960-ebe4f2` recount5,170 passed/40 skipped across5,210 nodes, exit0, COMPLETE/ACTIVE/full depth, native valid/full guard. Candidate record_validity passes with parent=not_found:ancestor_exited. Commit profile `20261006T192556-46092-095959` verdict pass retains the obligation `wsl-platform: next checkpoint`. There are5,162 recorded passing call phases and eight nodes with only passing setup/teardown phases; their exact node set matches the intentional recorder-stream lifecycle controls in the accepted C7c checkpoint. The terminal hook summary confirms5,170 passed, not eight failures. Missing call rows alone are not a general license to infer passing tests; here the known recorder controls, matching node identities and actual pytest summary qualify this specific evidence. The hook record names parent HEAD1c7be2d; verified staged/committed bytes bind it to the delivered candidate, but it is not an independent43eb190 full-coverage/final gate. Earlier failed attempt1 remains FAILED and sealed unchanged.

**Next:** Claude may continue the already-released Task5 core-only xdist implementation, required partial-commit scanner control/fix and separate test-first profile-specific quick commit-audit switch from this clean delivered commit, then CheckpointD (Fable5.1, then Codex). All new files must be staged or intent-to-add before index-based checkpoint inventories run. Retain full-depth audit/checkpoint/final/coverage protections; G acceptance does not prove worker isolation or the Task5 matched >=20-percent speed target. The controller/worker design may be developed within the approved Task5 scope without another routine operator approval. Flag a genuinely conflicting shared contract or new external scope rather than widening the frozen plan.

Governance import remains at StageBTask6 pre-pin docs/report follow-up; no immediate extra docs commit. Required independent final Windows/WSL gates, CI/safety comparison and all residual owners remain. No Task5 commit, plan closure, push, PR, merge, cleanup or other held activation is granted here. Codex performed review/governance filing only; no implementation or project commit.

## Task 4 commit attempt 1 — failed; one-entry correction and 19-path retry released

Disposition date 2026-10-07 Asia/Calcutta; recorded 2026-10-06 19:18:34 UTC. Source: operator-relayed Claude delivery update and packet SHA-256 `21e1d1bdae0f9394c9ad2ac6bce201353b12e30ae05fb9810d2e99d7af46f135`. Codex verified all14 receipt members and seal `86a233763a97ad8c4aced62ffcebb8b8ccc66b22b9a48baee854bde34d9a8c88`, the unchanged HEAD1c7be2d and exact18 staged paths, all working/staged SHA-256 identities against the C7c release table, and raw hook phases. **No commit was made.** The commit-profile run `20261006T184508-34948-35da0c` is FAILED: 1 failed,5,169 passed,40 skipped, COMPLETE/ACTIVE/native-valid/full guard/exit1, parent qualification retained. Other hook passes do not convert this attempt to PASS. Preserve the full failed receipts unchanged.

### Root cause and correction review

`tests/support/child_launch_inventory.py::launch_sites` enumerates `tracked_repository_files`, so the previously untracked `test_measurement_reuse.py` was omitted from that guard's inventory. Staging exposed its real nested-pytest launch. Earlier C7c executions remain actual passing executions; their child-site completeness claim was insufficient and is corrected here. Codex's checkpoint review also missed this index-dependent visibility requirement. This is a genuine missing classification, not a flaky test or reason to bypass the guard.

Codex independently enumerated exactly one missing site and ran the existing guard against the lane map (RED) and a reviewer-owned temporary map with the proposed entry (GREEN); no lane file was edited. The new launch runs this repository's nested pytest with root conftest preserved, TMPDIR/TEMP/TMP under its own tmp_path and retained terminal records. Its existing proof is the appropriate guarded-child proof, not an exemption or weakening. Copy exactly the existing `test_test_profiles.py::_pytest#1` entry under this new key:

```json
"tests/unit/tools/plan1126_runtime_audit/test_measurement_reuse.py::test_the_terminal_record_names_every_reuse#1": {
  "mechanism": "python:nested_pytest",
  "disposition": "nested_pytest",
  "proof": "tests/unit/tools/test_run_context.py::test_a_nested_pytest_is_guarded_too",
  "basis": "Nested pytest of this repository with its temporary folders, and so its run registry, under the test's tmp_path: an active child guards itself; collection-only children execute no test."
}
```

### Exact bounded release

Under the existing operator delegation, **release Claude to add only this one sites entry to `tests/unit/tools/run_context_child_sites.json`, and retry one local commit of19 paths**: the unchanged18 C7c paths/hashes in the preceding release plus this JSON map. No existing entry, disposition, proof or executable source may change. Object ordering/indentation needed to insert the entry is mechanical; verify semantic equality after deleting the new key. Same commit subject and normal hooks, no SKIP/no --no-verify. This supersedes the18-path-only scope for this retry, not any publication hold.

Before retry: run the child-site guard and relevant map/proof controls and the gates tier on the actual corrected lane with all new files indexed; fresh full-tree Ruff and diff checks must pass. Verify exactly19 staged paths, the original18 reviewed bytes unchanged, and the map's one-entry semantic delta. Do not consume the retry grant before these checks pass. If an affected check or any normal hook fails, stop and report; no further retry or bypass is granted by this paragraph. After success, verify committed19 blobs against staged/reviewed identities, clean status, actual commit SHA and sealed hook/delivery receipts.

**No new Checkpoint C or formal parity/fault run is required solely for this map entry.** The executable/depth/cache source remains C7c; the missing assertion has an independent negative/positive control and the failed staged broad run passed every other test. The prescribed corrected guard/gates and normal hook retry provide the affected evidence. Task4 mechanism/G acceptance remains; local delivery and complete corrected child-site acceptance are pending the actual checks/commit. This does not retroactively make the failed hook or earlier omitted-site completeness claim passing.

**Checkpoint visibility rule:** before subsequent reviewed checkpoint runs, every candidate new repository file must be visible to the actual index-based inventories (staged or intent-to-add), with HEAD/status/diff identities recorded. Do not infer that an explicit pytest target makes a new file visible to other inventory guards. This is a verification prerequisite, not permission to change production scanner selection or implement a new broad guard. Preserve Task5/partial-commit scope and D review; implementation proceeds only after the successful clean Task4 commit as previously released. Governance import stays at StageBTask6. Push/PR/merge/cleanup, final/CI/safety and other holds remain.

## Checkpoint C / Task 4 — C7c accepted; local commit released

Disposition date 2026-10-07 (Asia/Calcutta); recorded 2026-10-06 18:40:36 UTC. Source: direct operator-relayed Claude handoff in this Codex chat and packet SHA-256 `ada87afdf19431f99234574c9fef0877738e128407c17b034991f379a3861b4f`. Candidate C7c is HEAD `1c7be2da61263e6fa47092346f65218104388740` plus binary diff `0fc9024f86febcb59422200c5214e930f39751dbda0a44e13931c281fd63ac1f` and new reuse test SHA-256 `6db052a6768363ad9bd05885a30960558bac6fe82301c062f6f13dc6e3a42026`, exactly the existing 18 paths. Codex verified all 123 evidence members and seal `980af30a1ae2c38342476a3fdb5b2c58853b145a43a15ad97782e41174293627`, actual lane HEAD/status/diff and all 18 current WSL/Windows source bytes. Fable's three pre-validation reviews and final C7c SOUND were read in `c7/fable-c7.md`. Frozen v4 remains byte-identical. This section supersedes the C6 hold; previous findings and failed attempts remain historical evidence.

### Acceptance and mechanism disposition

**Task 4 and Checkpoint C: ACCEPTED on C7c.** Original C-M1/C-M2 corrections remain accepted. C-M3 is resolved by refusing cross-reader export reuse whenever export-subst may apply. Codex accepts this replacement for its prescribed HEAD-object key: Claude reproduced relative-date output following the clock, so the object key would not cover the entire class. Bypassing reuse is the simpler complete solution for these exports; required caching remains enabled for unaffected immutable exports. No production behavior, owner schema or frozen plan is changed. Raw-byte attribute detection closes the identified grep/encoding/pathspec/symlink gaps, and removing mailmap keying is appropriate because the only affected substitution path is now unreusable. Textual over-detection conservatively costs another export. Unknown rule inputs still refuse reuse. A single GitCommitSource reader retains its existing loaded snapshot; this disposition concerns reuse across readers and does not claim live reloading of an already-loaded source view.

Codex's fresh isolated native-Windows reproduction of C-M3 now passes: detach at A => HEAD decoration; move detached HEAD to B => new reader exports A without that decoration, key None throughout. No lane or installed-environment edit was made. Real WSL controls and Fable's independent two-platform probes corroborate the correction. The pre-existing Windows reader-thread behavior on other non-UTF-8 Git outputs fails loudly and cannot establish stale-cache acceptance; it was not introduced here and does not expand this bounded correction's scope.

**G: ACCEPTED for the Task 4 mechanism on this candidate.** Codex independently recomputed raw full/quick selections and every node's phase outcomes on Windows (full `20261006T161146-44836-9d6430`, quick `20261006T163550-59340-0cbf8e`) and real WSL (full `20261006T161559-7035-a43e79`, quick `20261006T160531-3383-de57ec`): identical digests and 362 nodes/outcomes per platform, COMPLETE/ACTIVE/exit 0, H5 full100 versus quick1 attribution. Retained mutation/fault outputs show f1 child refusal and f2 persistent-thread detection at both depths on both platforms. Mutation is 52/53 killed; e2 remains a survivor with the repository key retained, not proven equivalent or a 100-percent result. Reuse still names earlier measurements, executes no new probe/context on a hit, and provides no fresh independent repeat or repeat-100 claim at quick depth.

The existing quick refusal stays in place until a **separate test-first, profile-specific changed-input commit-audit switch**, reviewed at Checkpoint D. G does not authorize blanket quick acceptance for checkpoints, final or coverage gates; all those remain full. Task 5 must independently prove worker attribution, isolation/session behavior and its matched post-fix core speed target. Today's serial cache topology establishes no inherited worker guarantee.

### Evidence and practical limits

Fresh full-tree Ruff passes. The sealed Windows chain records gates336 and Task4 controls580; WSL narrow controls203 passed/7 skipped in both TMPDIR states. Codex independently recounted the raw Checkpoint C Windows terminal/phase records: main5,170 passed/40 skipped, full audit load77 passed, three repeats373 passed/8 skipped each. Every full-depth Windows record passes candidate record_validity with only parent=not_found:ancestor_exited. Manifest stability is complete with all three recorded repeat intervals contained in one full-depth load run. WSL raw checkpoint is main5,120 passed/90 skipped plus audit77 passed, each full-depth/COMPLETE/ACTIVE/exit0 and valid with native=unsupported, guard=unsupported_platform, parent=unsupported retained. Selection5287=5210main+77audits; no skipped node is counted as passing. Earlier failed WSL setup (uv absent from non-login PATH) ran no tests and remains FAILED, separate from the passing attempt. C3/C4 invalid/failed histories remain preserved.

Formal Windows measurements were contended with WSL. This acceptance makes no clean overall cache-saving claim and no Task5 speed claim. Optional validation-cost optimization and LOW synthetic overlap-window margin retain named P11-FEAT-TEST-PROFILES custody without waiving any future overlap gate. Stage A's existing full-coverage evidence remains tied to acc2a1c and does not become a C7c final measurement. Stage B still needs its own independent final Windows/WSL checkouts and all remaining Task6/CI/safety gates.

### Exact local commit release

Under the settled operator delegation (“Codex-approved means operator-approved; confirmed, go ahead.”), **expressly release Claude to make one local commit of exactly the following 18 reviewed paths**, staged by name, in the existing implementation lane at the reviewed base and bytes. Use the normal hooks, with no SKIP and no --no-verify. Commit message:

`test: add Plan 11.30 audit depth, export cache and measurement reuse (Task 4)`

| Released path | Reviewed SHA-256 |
|---|---|
| `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json` | `8c4ec4fcccbf4551ad2742aa984f74c300de84f6c9600a2ce83181191b0df1d2` |
| `tests/conftest.py` | `8546f2b66e0fd53107f41a35d0e5399eaf0980b5b8fd95e79924b811ad7dd1f3` |
| `tests/profiles.toml` | `2578866595c45fcb5fa5f28c284cdf8ebbd17114b62d09ed3b609ecf47e5ef65` |
| `tests/support/profiles_plugin.py` | `79dca5839c93ae19a71737a18ba111f071c97cbf70957b4c70e7999277d823a2` |
| `tests/unit/acp/test_plan1126_queue_policy.py` | `092dc7da2c72aeff49c89212f86bda05df81657b60091d9e12951fb01593839f` |
| `tests/unit/acp/test_plan1126_shutdown.py` | `1c0e882a6b430aa3393d2c1b8d8adbc1e6cfac417c506515a327a12e47c1799f` |
| `tests/unit/tools/plan1126_runtime_audit/test_current_measurement.py` | `9acef1b8ae36bff2d833fc1350ceafc5b4a235d7da35320bca948844bf276c08` |
| `tests/unit/tools/plan1126_runtime_audit/test_measurement_reuse.py` | `6db052a6768363ad9bd05885a30960558bac6fe82301c062f6f13dc6e3a42026` |
| `tests/unit/tools/plan1126_runtime_audit/test_source.py` | `b0b5b452f2506f731fed66b491aada8f9876064c9ab83f37e939c8d41a00198b` |
| `tests/unit/tools/test_coverage_products.py` | `5102c4a5523d1b54c48030da474cfeb9dbfe3cf02b22728c2ec4ca727112c016` |
| `tests/unit/tools/test_run_profile.py` | `30e343a9ccfc35cc2012e831ea23571525bef4a76e5a56a13e6241ded575ef7f` |
| `tests/unit/tools/test_test_profiles.py` | `c2200655394343e632dfeddc146dae1d815210a9f9378a064325fc2cc11756d4` |
| `tools/plan1126_runtime_audit/current_envelope.py` | `c1eeb3a554fdd81e3f4f7edc426d4e07ada29d0bf687293d383c3ecf058a260e` |
| `tools/plan1126_runtime_audit/measurement.py` | `5b6b582d506c7aa089202993d62b79d893708c9ee2cfd17caa805318fe5c7e0d` |
| `tools/plan1126_runtime_audit/source.py` | `9db40e6a3d73f96363864bac94f61193c30a77ec18acc5fcd0bc4380073963fd` |
| `tools/testing/run_context.py` | `15d63a60edea551ef8ff134149180adc5e5f39ea9aedd1b489c9690dfc103020` |
| `tools/testing/run_context_records.py` | `d4bedb341aa63987acf8e843102df698dad50230e60ae0bc3e30fef4384c6304` |
| `tools/testing/run_profile.py` | `597f910cf9b45ec46ca049033cf8289c1ad3cb059e78d8d0ae006216c477b872` |

Before committing, verify candidate source identity and the staged set/blobs against the reviewed identities above. Preserve actual hook command/output/run IDs, outcomes and valid records; stop and report any material failure instead of treating this grant as a bypass. After a successful normal-hook commit, record the actual new SHA, verify all18 committed blobs against the staged/reviewed files, confirm a clean tree and seal the commit receipts. Acceptance here is of the tested dirty candidate; commit delivery is not yet verified. Do not relabel parent-HEAD hook records as independent final-head full-coverage evidence.

**Next execution release:** after that successful commit and clean-tree verification, Claude may proceed under the existing Stage B grant to Task5 core-only xdist, the required LOW partial-commit scanner control/fix, and the separately test-first quick commit-audit switch. Checkpoint D remains Fable5.1 then Codex with normal full-depth current audits and platform/concurrency obligations. No extra immediate docs commit is commissioned. Import final reviewed governance by name during the existing Stage B Task6 pre-pin docs/report follow-up; do not expand this18-path code commit with the D: backlog or other governance files. The ignored reviewer log must never be staged.

No push, PR, merge, cleanup, paid-call/service change, other Plan11.28 activation or plan closure authority is granted. Codex performed review and governance filing only, with no implementation or project commit.

## Checkpoint C / Task 4 — C6 reviewed; detached-HEAD correction required

Recorded 2026-10-06 04:41:52 UTC. Source: operator-relayed correction update and packet SHA-256 `fc6d5ad640d9098348030284d416b89e9a6699c759fa4f796c388f62e97a6a40`. Reviewed candidate C6 is HEAD `1c7be2da61263e6fa47092346f65218104388740` plus binary diff `c6fe012ea8bd4cfa1a678fec88967feab4a9af0650acb8d95f870c500d49bd32` and new reuse test SHA-256 `6db052a6768363ad9bd05885a30960558bac6fe82301c062f6f13dc6e3a42026`, the same 18 paths. Codex independently verified all 37 evidence members and seal `7a5f1e5955105b32fcf85d480124ad0196a96f8dc7bad3787840788ed2367078`, actual Windows Git identity and all 18 current WSL/Windows file bytes. Fable's C6 SOUND is in `fable-c-m-rounds.md`; the separately retained `fable-cpc-final.md` describes historical C2 and is not represented as a C6 verdict. Frozen v4 is unchanged.

**Original corrections accepted:** C-M1 now fingerprints effective external attribute contents, moving attribute/mailmap objects, replace refs and redirection, refusing unknown inputs and reuse with detected filter drivers. C-M2 verifies installed dependency integrity for the specification plus entry floor before lookup and checks the earlier binding on a hit. These resolve the two original findings. The conservative filter detection and scoped export-subst key are acceptable mechanisms, subject to the missing HEAD object below. Retain the repository key: e2 is one surviving mutant, not proven equivalent or harmless and not a correctness blocker while the component remains. Mutation evidence is 50/51 killed, not 100 percent.

**Passing execution evidence retained:** fresh full-tree Ruff passes. Codex recomputed raw formal records: Windows full `20261005T183720-53128-0ac4b8` and quick `20261005T190351-47188-da123a`, WSL full `20261005T184105-10570-d49b64` and quick `20261005T182958-4363-79233b` each cover the same 352 nodes, identical selection digests and per-node phase outcomes, COMPLETE/ACTIVE/exit 0. Full H5=100 and quick H5=1 remain explicitly attributed. Windows checkpoint main is 5,160 passed/40 skipped, full audit load 77 passed, three repeats each 373 passed/8 skipped. All full-depth Windows records pass candidate record_validity with only parent=not_found:ancestor_exited. WSL checkpoint manifests and raw terminal records pass with native/guard/parent unsupported qualifications retained. No skipped node is counted as passing and no WSL Windows-native parity is inferred. The retained fault summaries/mutation logs show both under-close and persistent-thread faults refused at both depths on both platforms. These establish the measured parity executions, not acceptance of an export cache with the counterexample below.

### C-M3 — Detached HEAD object omitted from export-subst identity (bounded major)

At `tools/plan1126_runtime_audit/source.py:156`, the export-subst branch binds all refs and HEAD's symbolic full name, but not the object HEAD currently resolves to. In detached state that name is the literal `HEAD`; moving detached HEAD changes no branch/tag ref and leaves this key unchanged. `$Format:%D$` nevertheless includes HEAD decoration when the exported commit is HEAD and removes it when HEAD moves away.

Codex independently reproduced a real stale export on native Windows and real WSL Git 2.43 using isolated two-commit temporary Git repositories:

1. Commit A contains `.gitattributes` with `a.txt export-subst` and `a.txt` with `$Format:%D$`; commit B adds b.txt. Keep the branch at B.
2. Detach HEAD at A and read A through GitCommitSource: exported a.txt is `HEAD\n`.
3. Move detached HEAD to B without changing any ref/config/attribute or the requested commit A. A new reader has the same export key and returns cached `HEAD\n`.
4. Clear the session export cache and read A again: a fresh archive returns `\n`.

Both platforms reported key equality and cached/fresh inequality. This is an executable counterexample, not an enumeration-based hypothetical. The implementation lane, its clone and installed environments were not edited; only reviewer-owned temporary fixtures were created and removed. It violates the exact export identity contract. The earlier cache defects are resolved; this is a new, narrow omission in the correction's export-subst support.

**Minimum correction:** test-first, add the resolved HEAD object identity alongside its symbolic identity in the existing export-subst branch. Preserve fail-closed behavior when it cannot be established. Cover detached HEAD moving onto/away from the fixed exported commit, and retain branch/tag/history and no-export-subst controls. Use the existing Git/source seam; no redesign, cross-process cache, schema change or other-lane edits are needed.

### Current requested dispositions

1. **Task 4 / Checkpoint C acceptance: HOLD solely for C-M3 on C6.** Original C-M1/C-M2 corrections and passing evidence are accepted within the qualifications above. Fable's SOUND remains recorded; this independent new counterexample needs its bounded correction reviewed by Fable then Codex.
2. **Same 18-path local commit: HOLD.** No named commit release, SKIP or --no-verify grant yet. Under existing implementation authority, Claude may make the bounded test-first C-M3 correction, retain failed history, then verify affected source/cache controls on native Windows and real WSL, full-tree Ruff/current gates, corrected-candidate full/quick/fault evidence and the normal frozen-v4 Checkpoint C. Have Fable inspect the narrow correction before launching expensive validation so another key omission need not cost another checkpoint. No extra full-suite ceremony or operator approval round is commissioned. Do not inherit exact-source acceptance from C6 after editing the cache.
3. **G and quick commit activation: HOLD until the corrected cache candidate is accepted.** C6's 352-node parity and injected-fault executions pass but cannot override C-M3. Once corrected evidence passes, the proposed profile-specific changed-input quick switch remains a separate test-first Stage B change for Checkpoint D; full checkpoint/final/coverage protection remains mandatory.
4. **Governance import: Stage B Task 6 docs/report follow-up.** Do not add the D: backlog or other governance files to the 18-path code candidate/commit. Preserve this shared ruling and current backlog custody now; import reviewed final governance bytes at the existing Stage B pre-pin docs gate. No extra interim docs commit is required.
5. **LOW overlap-control margin:** accepted as a non-passing designed UNRUN historical attempt, not a false pass. Optional margin hardening has unscheduled named custody under P11-FEAT-TEST-PROFILES; retain the failed attempt and actual passing checkpoint evidence. It is no waiver of future required overlap gates. Mixed, contended C6 timings support no clean overall cache-gain claim; required Task 5 matched speed evidence remains separate.

Task 5/partial-commit implementation sequencing remains after Task 4 release. Stage B independent final checkouts, CI/safety comparison, push, PR, merge, cleanup and other Plan 11.28 holds remain unchanged. Codex performed review and governance filing only, with no implementation or project commit.

## Checkpoint C / Task 4 — C2 correction required

Recorded 2026-10-05 15:36:01 UTC. Source: operator-pasted Claude update and packet SHA-256 `09507fd60852c64b4fdc4baf4293d6db631eacf269c8043e5601f0bf958384f9`. Candidate is HEAD `1c7be2da61263e6fa47092346f65218104388740` + binary diff `9fc1385b6a9dddf09c082813b71dbc385a66a898ed3880f61c3e89f75199bd29` + new reuse test SHA-256 `2d789300953aac4cd552a4a51b7164d8b262629d98b30d389a6c4a026d77d741`. Exact dirty set is the proposed 18 paths. Codex verified all 51 seal members and seal `f1df55db6db58b2e2426b3162920f850600acaf9a9554e721a0001bbc2ee1461`, read both returned condensed Fable verdicts, reviewed implementation/control diffs, and ran fresh full-tree Ruff successfully. Frozen v4 remains unchanged. Claude's concurrence with all five budget answers is recorded in the relayed update and packet.

The retained C2 checkpoint manifests report pass on both platforms. Codex independently validated/recounted the actual Windows terminal/phase records: main 5,152 passed/40 skipped, full audit 74 passed, each of three load-overlap repeats 373 passed/8 skipped. All five Windows records are ACTIVE/full-depth/COMPLETE/native valid with the stated parent qualification. WSL manifest records full-depth ACTIVE/default-selection subruns, exit 0, with native/guard/parent unsupported labels retained. These are passing test executions, not acceptance of a cache implementation whose identity predicate has counterexamples. Earlier failed C1 checkpoint remains FAILED history; formal Windows full/quick 340-node parity is C1-source evidence, while C2 WSL formal runs cover 341 nodes. No exact C2 Windows parity claim is manufactured from unchanged depth code alone: C2 also changed the caching/provenance controls that G covers.

### C-M1 — Export key omits effective global attribute-file content (major)

`tools/plan1126_runtime_audit/source.py:78` hashes the Git config text (including a core.attributesFile path) and repository info/attributes, but not the contents of the configured global attribute file. Git archive uses those contents. An isolated real Git fixture reproduced the defect on **native Windows and real WSL**: read a.py, change only the configured global attributes file to `a.py export-ignore`, construct a new reader. Its key remains identical and the cache returns a.py; after clearing the cache, a fresh archive correctly omits it and raises KeyError. Thus stale cached data can contradict the same commit's effective export, violating the tool/config-key contract and the archive-refusal controls.

Fix test-first: cover content edits at an unchanged core.attributesFile path and other effective external attribute sources, or explicitly demonstrate they cannot affect the supported export. Fingerprint the actual effective export-rule inputs (not just their path/config string) and invalidate/refuse on drift. Preserve existing export behavior, bounded read-only storage and failed-export refusal; do not bypass attributes or rewrite historical files to hide the difference. Include real Windows/WSL regression evidence. Initial reviewer fixture attempts were diagnostic failures (sandbox temp permissions, then an entirely empty archive); the final two-file fixture establishes the stated result and was cleaned up. No implementation checkout files or installed environment were modified.

### C-M2 — Reuse identity omits installed dependency-file integrity (major)

`measurement_identity` at `measurement.py:920` hashes the request payload, depth, interpreter/platform and environment variables. The payload's specification names dependencies but does not fingerprint installed dependency files. H5 and H9 require redis. A hit at line 963 reconstructs the earlier EnvironmentBinding and returns copied observations without validating those installed files. The existing EnvironmentBinding contract explicitly distinguishes same-version installed-file edits; they must not be treated as an identical environment.

Codex's bounded in-memory fault-injection probe changed the integrity verifier's redis fingerprint while holding the request/env fixed: the key remained identical and the integrity verifier was called zero times by key generation. Source inspection shows the hit path likewise performs no integrity revalidation. This demonstrates the identity omission; it is not claimed as an actual edit of the shared venv or a new fresh measurement. The current key-sensitivity control does not exercise dependency drift.

Fix test-first: incorporate/revalidate actual dependency integrity for the full specification plus entry requirement floor before accepting a hit. Same-version content drift, missing/corrupt installation and mismatch with the earlier binding must invalidate or refuse reuse; checking a package name/version or lock hash alone is insufficient. Use the existing integrity/binding mechanism and preserve fresh child-only contexts, exact source/options/depth keys, copies and named earlier-data provenance. A hit must execute neither the probe nor a new context, but that does not prohibit checking whether its environment is still identical. Do not weaken the existing installed-file verification to make caching pass.

### Five requested decisions

1. **Task 4 / Checkpoint C acceptance: HOLD on C2** for C-M1/C-M2. Fable's SOUND and passing execution receipts are retained honestly; these new counterexamples prevent technical acceptance. Budget/depth mechanism, terminal-only registry-safe fields and the bounded whole-tree approach are acceptable in principle. F5's no surviving cache-worker observation remains qualified to today's topology; Task 5 may not inherit a cross-session worker-cache guarantee without its own proof.
2. **Plan 9.96 manifest entry: ACCEPT the single additive living-manifest classification**, including its digest-only control, as the narrow current-source correction required by this task. Actual diff adds exactly one key, leaves other entries unchanged, and classifies a non-persisted serialization used only for the reuse digest. It edits neither a frozen plan nor the canonical sealed audit artifact and weakens no sink policy. This bounded scope ruling does not approve unrelated Plan 9.96 edits.
3. **18-path local commit: HOLD.** No SKIP or --no-verify release; do not stage/commit C2 as accepted. Claude may implement the two bounded test-first cache corrections in the affected existing files, preserving old seals and candidate evidence. Fresh narrow cache/provenance controls on native Windows and real WSL, full-tree Ruff/current gates, corrected-source parity and the required corrected-candidate Checkpoint C review remain before commit release. Run the normal v4 checkpoint, not an added full-suite gate. Submit corrected identities/receipts through Fable then Codex; no extra operator approval round is needed for these in-scope fixes.
4. **G / changed-input quick activation: HOLD.** Current passing parity/fault results are valuable but do not close G's exact-environment/cache controls. Corrected candidate must prove full/quick mandatory-probe/failure parity with attributable source identities on both platforms; retain C1 Windows evidence as historical. Do not switch commit audits or remove the required objective. The currently conservative runner/coverage quick refusal stays until a separately reviewed profile-specific quick activation implementation; full checkpoint/final/coverage acceptance must still refuse quick.
5. **Validation-cost follow-up owner: P11-FEAT-TEST-PROFILES**, with shared Plan 11.26 contract consultation if ever scheduled. About 130 of 276 seconds is reported full-document validation; the report is a measured cost observation, not a promised cacheable saving. Record named custody in the sole backlog as unscheduled optional optimization; no new implementation or schema change now. This does not exclude Task 4's required caches or close its objectives.

The recommended report/manifest update at Stage B Task 6 is acceptable; preserve candidate/source-specific receipts now and record all failed attempts and corrections then. Task 5/partial-commit work remains required after the corrected Task 4 release. No push, PR, merge, cleanup, service/paid-call or other activation grant. Codex performed review/probes/governance filing only; no implementation, lane staging or commit.

## Task 4 probe-budget and shared-contract disposition

Recorded 2026-10-05. Source: operator-relayed Claude proposal SHA-256 `348a91addcbd3b6f7360dc4af814475d370e0efd224d3a6d1d35e7e133fbfccd`. Read the inventory at the implementing lane's `.superpowers/sdd/2026-10-04-plan-11-30-test-profiles-implementation_v4/stageb/task4/audit-current-inventory.md` (SHA-256 `2cee7d57b4f41b726a2e465d74092d5443fa8c07d043fa5561c6a3366ecf4849`) and costs TSV (`6bdd92e5a53e04f98bfdbc4eafd6aa6076e93b4c2406f2812dcb1b8f87b0bca8`). The shared copy is at `C:/worktrees/optimus-cost-agent-worktrees/optimus-handoff/test-profiles-research/plan-11-30-task4-budget-inventory-20261005/`; its seal verifies and its two content hashes match the inspected working copy. These are private survey provenance, not new project dependencies. Codex answers the shared Plan 11.26 contract questions in its existing architecture/review role; `P11-FEAT-ACP-RUNTIME-HARDENING` retains ownership. No other lane's plan or sealed record is revised.

Independent source inspection verifies H5's options flow and >=1 repeat capability, the 100-count current test's complete assertion set, H4's exact 1,000-seed refusal, the existing record/sidecar depth gap, fresh child-only execution contexts and per-instance Git archive memo. Independent raw-phase/classifier recomputation gives 67 current-audit nodes, **936.741816 s**, of which H5 is **534.613345 s**. The TSV's 936.72 s sums individually rounded rows; it is not a contradictory raw total. The five rebuild/envelope/schema nodes total about 275.815 s, but their costs are not yet partitioned into cacheable work. The approximately 409.5 s quick projection substitutes a different repeat-1 control's 7.4 s, so remains an estimate, not a measured quick run or promised cache saving.

### Answers to the five questions

1. **H5: pin quick=1 repeat per applicable close-path × terminal-cause family; full=100.** This agrees with Claude's simplest v4-compatible proposal. Quick retains every applicable family, exact N-count checks, complete/context/source provenance, idempotence, allowlist, unexpected thread/task detection, probe_error rejection and latency semantics. It provides no repeat-100/accumulation-stability acceptance. Keep existing node identities and full behavior; reduced-depth execution of the repeat-100-named node must be labelled explicitly, never cited as fulfilling its full obligation. Full checkpoints, sealed constructors/schemas and FU-33 remain 100. No change to the historical records or unrun binding.
2. **H4 stays full: 1,000 derived seeds plus its unchanged literal corpus.** Every other audited probe remains at its existing counts/windows. Do not introduce a 32-seed path, alter the sealed count guard, or silently reduce the S1 timeout/settling windows. Unsupported quick domains retain full execution.
3. **Keep Plan 11.26 record/sidecar schemas unchanged; make depth attribution durable at the runner layer.** Extend the existing selection/run manifest and terminal reporting with actual effective depth and H5 repeat budget, including direct pytest audit invocations without `--profile`. The proposal's claim that the terminal line already carries audit_depth is not true of the inspected profiles plugin; it must be implemented and verified. If a quick run retains current measurement outputs, its companion run manifest must bind their exact paths/hashes, source/environment, entry/domain, counts and run ID to the reduced-depth label. A console line or assertion message alone is insufficient. Quick outputs may not be filed as canonical/full evidence or satisfy checkpoint/repeat-100 obligations; missing/mismatched provenance refuses that acceptance claim. If existing CLI/export behavior cannot keep this distinction without changing the owner schema, hold that affected export path for a bounded contract disposition rather than silently changing the schema.
4. **Agree to measure cacheable cost first, then implement Task 4's required bounded caches.** No extra operator approval round is needed between measurement and coding inside this contract. Measure export/rebuild/schema and fresh-probe costs separately; fresh CLI subprocesses mean an in-process memo alone cannot be credited with all five tests' cost. Reuse the existing immutable Git export path with session-scoped keys: resolved commit, exact path set and tool/config identity. Current-measurement reuse must be keyed by exact source, domain/probe shape, depth and all repeat/seed/options, platform and environment. Preserve failure observations. A cache hit is reuse of the named earlier data, never a new execution, new independent repeat or minted execution context; fresh execution still requires its verified child-only context and unchanged detection-time semantics. No reuse across incompatible sources/options, threads or sessions. Keep sealed replay optimization secondary. This approves the bounded mechanism, not any performance estimate. A small measured gain is not permission to omit required caching; if it proves impossible to meet the complete contract, flag that specific gap rather than closing Task 4.
5. **Use the existing pytest profiles plugin for `--audit-depth=full|quick`, default full**, with the option passed only to the affected test helper/probe invocation. The public CLI's existing repeats path, production behavior and record schemas remain unchanged. Ensure the profile runner actually propagates the chosen effective depth to each subrun and records it truthfully. Checkpoint/final operations enforce full depth; commit current audits remain full until G is independently accepted. No quick-hook activation merely because the new option exists or focused tests pass.

**Execution disposition:** the enumerated budgets and scope above are Codex's shared-contract answer to Claude's proposal, with provenance/cache qualifications. Claude may record concurrence with these exact qualifications and proceed test-first inside Task 4 under the existing implementation grant; no additional operator decision or new mid-task review ceremony is required. If Claude disagrees with a qualification, resolve that affected contract point before dependent code. No claim that Claude already accepted newly stated qualifications is made. Source/depth/cache/context/detection-time negative controls, full/quick mandatory-probe execution and failure parity remain required. Checkpoint C remains Fable 5.1 then Codex. Quick activation waits for G; Task 5 and its performance acceptance remain separate required work. No commit/publication/cleanup grant or frozen-v4 revision.

## Stage A documentary delivery verified; Stage B execution go-ahead

Recorded 2026-10-05 10:37:35 UTC. Operator-relayed delivery note SHA-256 `8f5209b80c737f12452fb6f4285f3ce28cabb708b11b9be42c8626fee6c5d46c`. Codex independently verifies commit `1c7be2da61263e6fa47092346f65218104388740`, parent `acc2a1cadb435352f0e26ece58ffb4faba92cf3c`, branch `agent/claude/plan-11-30-test-profiles`, and a clean implementing tree. Exactly the seven released paths changed. All seven actual Git blobs equal the sealed staged identities; all five governance hashes equal Codex's released bytes. The 29-member seal `8b9e2a2527829b5b7d56d56a28a77d8e995b05a0116f07fd39fbea1b6b539e86` verifies. Source, tests, tools, config, lock and CI are unchanged from acc2a1c.

The report/manifest record accepted Task 6 results at acc2a1c, the exact operator checkout approval, corrected owner/opening status and qualified/UNKNOWN claims. The index row is correctly inside its table. This documentary commit does not inherit the full-run evidence as a measurement of 1c7be2d. All applicable normal hooks passed, no SKIP/no --no-verify; YAML/TOML were not applicable. Retained pre-edit-to-commit receipts show docs 85 passed, secret scans/diff/LF/JSON checks clean; fresh independent full-tree Ruff and diff check pass.

**Correct hook count:** run `20261005T093835-60588-94ebe4` selected 4,530 nodes: **4,493 passed, 37 skipped**, zero failed. Codex recomputed these outcomes from all raw phases, verified exact selected/phase-node set equality, terminal COMPLETE/ACTIVE/default selection/native-valid/full-guard status and retained parent qualification `parent=not_found:ancestor_exited`. Its staged selection digest equals the actual acc2a1c-to-1c7be2d binary diff, with no provisional files. “4,530 tests passed” is not accepted wording; retain the sealed note unchanged and use the corrected split in future summaries. No source correction, rerun or additional docs-only commit is required solely for this relay wording.

**Disposition:** the seven-path local documentary release is fulfilled. Stage A's implementation, local final measurements and local documentary delivery are accepted within their recorded source/qualification boundaries. Complete CI-backed Stage A delivery, Linux base/candidate safety comparison and plan closure remain open; main-based lanes do not yet receive the hook benefit because nothing has been published.

**Stage B go-ahead:** Claude may start the already-approved required Stage B in its current lane from verified clean 1c7be2d. First source change: add the explicit core rule for the WSL IPC node and refresh slow-node measurements/classifier-selection/affected Windows–WSL controls as previously ruled. Then execute frozen-v4 Tasks 4–5 and the required LOW partial-commit scanner regression/correction under `P11-FEAT-TEST-PROFILES`. Use test-first bounded fixes and the simplest implementation meeting every required objective. Task 4's exact quick-depth probe budgets must be pinned with the Plan 11.26 owner before dependent implementation; preserve full-depth counts/assertions/context and unsupported-domain obligations. Do not edit another lane's plan or weaken its evidence.

Review cadence remains Checkpoint C after Task 4, Checkpoint D after Task 5, each Fable 5.1 then Codex; checkpoints retain full current audits, native Windows/real WSL controls and the approved Windows audit-load overlap, with no added full-suite ceremony. Preserve coverage-writer/environment isolation. The xdist >=20% matched post-fix core target remains required: failure keeps serial operation and the objective open, never silently closes it. Stage A evidence is historical for changed Stage B source. Stage B needs its own Task 6 and independent frozen acceptance checkouts; the Stage A Windows exception does not extend to it.

This is execution sequencing under existing operator approval, not a new Stage B commit, push, PR, merge, cleanup, service/paid-call or other Plan 11.28 activation grant. Local Stage B commits remain subject to their named review releases and normal gates. Do not import this new reviewer filing as an extra immediate docs-only commit; read the current ruling/log and keep live custody current through the next appropriately released delivery. Codex implemented no code, ran no full suite, and committed nothing.

## Stage A Task 6 — local acceptance finalized

Reviewed 2026-10-05 (UTC review clock 09:17:24). Evidence pin `acc2a1cadb435352f0e26ece58ffb4faba92cf3c`, tree `64266896398ceaa2f92c0013af2af731c10d20cd`. Operator-relayed packet `2026-10-05-claude-task6-stage-a-final-packet-plan-11-30.md`, SHA-256 `c388e2808475b497ca16d58b625bfd17f29e309e645c2be075f375dd6b232406`. Codex verified all 69 seal members; seal `38b9b8fac7c5c24b614d909e91bd698e5d461d87a8f1a1a16020cccafd1673ca`. Read both sealed Fable returned verdict summaries: SOUND WITH AMENDMENTS; the first has 0 major/3 minor findings. These summaries are retained as returned, not claimed as an original independent transcript export.

### A — Local measured results

The local measured tests, product floors and Windows Task 0 full-run confirmation are accepted at acc2a1c. The operator approved the Stage A-only checkout exception below on 2026-10-05, finalizing local Task 6 technical/procedural acceptance without a rerun. Remote CI/safety, documentary delivery and complete Stage A delivery remain open.

| Evidence at acc2a1c | Windows | WSL |
|---|---|---|
| Full run | 5,427 passed, 40 skipped, 111 deselected | 5,293 passed, 174 skipped, 111 deselected |
| Selection/terminal | 5,467 selected, zero collection/recording errors, COMPLETE/ACTIVE, exit 0 | Same selection/terminal result |
| Validity | Valid Windows native/full process guard; parent=not_found:ancestor_exited | native/guard/parent unsupported qualifications retained |
| Optimus full branch-inclusive coverage | 87.87218934911243%, passes 80% | 87.20473372781065%, passes 80% |
| A2A | 68.41654778887303%, informational | 65.96291012838802%, informational |
| Context Engine/model policy | Absent, N/A | Absent, N/A |
| Nodes above 2 seconds | 233; no default-origin nodes | 77; one default-origin node addressed in B |

Independent raw-phase recount includes eight setup/teardown-only recorder controls: Windows 5,419 call passes + 8, WSL 5,285 + 8. Selected/deselected record states reconcile to 5,467/111, not 5,578 selected. Independent Windows gap calculation: 16,371 transitions, k=1,637; first median 0.00037200000001291755 s, last 0.00039499999957115506 s, ratio 1.0618279557995667 <=2; zero negative gaps; gap sum 18.347725000017682 s. This satisfies Task 0's outstanding full-run predicate. WSL ratio 0.7814245808579946 remains informational, with guest wall-clock uncertainty; no Windows parity or cross-platform performance claim.

Both reports have 202 current tracked source rows. Codex independently checked row-set equality and every statement/branch count against coverage.py's analysis of the actual pinned source; both product predicates pass and all seven safety rows exist. Coverage SHA-256: Windows `0b1f7e12d350f9021c021bcd7f2d8aedb5bdbccfeff81aa36974c687a7efc167`, WSL `d7c33c18b353d5fa5fb5b5592bb1407602868ebc52010acfd29a87f80e06a62f`. Write timestamps convert on the measuring hosts to 08:42:28.998986Z / 08:23:26.614389Z, inside their runs. Automatic and explicit report outputs agree on both platforms. Collection binding is supported by those retained CLI proofs; Codex did not rerun full collection. Its additional label-based digest probes could not reconstruct the eight withheld labels and are not extra passing selection proof. No files changed or tests rerun during these probes.

Actual clean HEAD/tree/config/lock match the pin; latest tracked Windows source/test/config mtime predates the run. Docs commit acc2a1c contains exactly the five released path bytes; its 17-file seal `6de9b0f9a433addef0f01bc982250dbd042975f851a2fd888aec474789a3e829` verifies. Docs commit hooks completed successfully with YAML/TOML not applicable and its 149-node commit profile passing. Fresh full-tree Ruff passes. The reports' original wrong-session copies remain harness-error history; the corrected ACTIVE full run records, not PASSIVE collection sessions, support this review. The RuntimeWarning is present in both full outputs and concerns the pre-existing entrypoint test. Coverage differences are consistent with additional WSL skips/platform-specific paths, but skip counts alone do not establish sole causation. No cross-platform safety subtraction is accepted; comparable Linux base/candidate evidence is still missing.

### Windows checkout deviation — operator-approved Stage A exception

Recorded 2026-10-05 09:31:33 UTC. Direct operator reply in Codex chat `01a10617-9940-72c0-a5e2-e3f8c3241055`, immediately after relaying the request to retain the existing Windows run:

> Yes approve windows run above

Decider: Vibhanshu (operator). Status: Accepted for this existing Stage A Windows run at `acc2a1cadb435352f0e26ece58ffb4faba92cf3c`. Frozen v4 calls for an independent acceptance checkout; Windows instead used the clean frozen implementing lane. Its unchanged pin, source identities, report checks and independent WSL clone support the joint Fable/Claude/Codex recommendation to retain it. The explicit operator exception resolves that procedural departure; no Windows rerun is required. C1's earlier command approval alone did not grant this exception. Frozen v4 remains byte-identical, and this decision grants no general exception for future runs.

Codex finalizes local Stage A Task 6 acceptance on the already-verified evidence above. The seven-path documentary release below may proceed after its normal checks; no further topology or local-commit approval is needed. Remote CI/safety, complete delivery, required Stage B and publication/cleanup boundaries remain unchanged.

### B — Recorded C2 disposition of the new WSL slow node

Accept the reviewed, source-bound classification exception for this pin only. `tests/unit/mcp/test_local_ipc.py::test_remote_consume_after_listener_stop_fails_quickly` totals 2.002187 s on WSL (call 2.001567 s), versus 1.015521 s Windows. This is a genuine >2-second omission, not rounding it down. The current test deliberately waits for bounded IPC failure in-process and asserts completion under 3 seconds; there is no child process to justify proc. Claude/Fable/Codex agree explicit core is correct and preserves today's tier/selection.

Required first Stage B source change under existing `P11-FEAT-TEST-PROFILES`: add the explicit core node rule with rationale “designed bounded IPC-timeout wait; platform-dependent (1.0 s Windows, 2.0 s WSL)” and include the retained observation in the pre-Stage-B measurement refresh. Verify classification/selection and affected Windows/WSL controls. Do not rewrite acc2a1c or repeat both final suites for this metadata-only classification. This is the recorded C2 disposition before Stage A sign-off, with named required custody; no scope exclusion or plan closure waiver. Task 4/5 and partial-commit correction remain required.

### C — Post-run documentary follow-up

Select a tracked post-run report/docs follow-up, rather than leaving required evidence only in external delivery packets. Codex repaired its misplaced ADR-016 index row in D:. Claude may prepare the report/manifest Task 6 section and import the following reviewed governance delta. Preserve every seal and the original acc2a1c evidence; do not rerun the product report at the descendant and imply it was measured there.

Required report content: both full commands/run IDs, measured HEAD/tree/config/lock/interpreters, raw counts with the eight controls, product row counts/formula/percentages, gap fields and values, weaker WSL labels/clock uncertainty, the new slow-node disposition, corrected run-picker provenance, auto/explicit binding agreement, measuring-host timezone requirement, warning, host-overlap qualification and the approved Stage A-only Windows checkout exception and exact operator words. Fix the two Task 0 owner clauses to current `P11-FEAT-TEST-PROFILES` custody. The report's opening “Task 0 pending / Tasks 1–6 not started” is also stale: add current overall status and label the original intake status as historical; keep failed/INVALID original receipts and snapshot claims intact. Qualify the platform coverage explanation as consistent with skips/platform paths, not solely proven by skip counts.

The manifest must name the acc2a1c measured source and immutable Windows/WSL receipt/coverage identities, explicit per-claim PASS/qualified/UNKNOWN status, approved Stage A-only topology disposition, required Stage B owner and remote CI/safety UNKNOWN. A later documentation commit has its own identity; it records results at acc2a1c and receives normal docs/hook checks, never an inherited full-run claim for its new HEAD. This is an express bounded post-run documentation-recording disposition under C2, not a source/test/config/lock change.

Claude may prepare exactly these seven paths now: `reports/plan-11-30-test-profiles-evidence.md`, `reports/plan-11-30-test-profiles-manifest.json`, `docs/README.md`, `docs/decisions/README.md`, `docs/decisions/ADR-016-test-cadence-product-coverage-and-staged-delivery.md`, `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`, and this Task 3 review. Under existing local reviewer delegation, one normal-hook docs/report commit of this exact bounded content is expressly released now, with the topology condition fulfilled by the operator approval above. Before committing, the report must accurately record that approval, fresh docs/secrets/Ruff/diff/LF checks must pass, and staged paths/source identities must be verified. No SKIP/no --no-verify; no implementation or new explicit-core rule in that commit. Retain normal-hook/commit blobs/status receipts and seal them. No further operator commit permission is required for that bounded release; stop for review if content or source scope changes.

This documentary follow-up does not release Stage A publication, merge, cleanup or a full rerun. Stage B remains owned/open and its already-approved sequencing still applies; do not describe it as cancelled. Codex implemented no code, changed no pinned checkout, and started no full tests.


## Task 6 command substitution authorized — 2026-10-05

Recorded 2026-10-05 06:07:16 UTC. Direct operator words in Codex chat `01a10617-9940-72c0-a5e2-e3f8c3241055`, immediately after Codex verified Task 3 delivery and restated the jointly recommended pending command substitution:

> Authorized

**Disposition:** C1 is approved. The authorization applies to the Plan 11.30-only substitution of the unsupported frozen-v4 `run_profile --profile full` command with the agreed direct serial default pytest coverage command, followed by the product report. Claude and Codex had already agreed on this mechanism. It avoids an additional CLI implementation/review round while preserving the same full-suite, coverage, recorder and acceptance obligations. The frozen v4 bytes remain unchanged. This explicit operator disposition supersedes the prior C1 pending/execution hold; historical records below retain their original state.

Claude is authorized to prepare and execute Stage A's local Task 6 using these exact commands in its frozen acceptance checkout:

```bash
uv run --no-sync pytest --cov --cov-branch --cov-fail-under=0 --cov-report=term-missing --cov-report=json:tmp/coverage/full.json -v
uv run --no-sync python -m tools.testing.coverage_products report --coverage-json tmp/coverage/full.json
```

Complete the already-required reviewer current-state documentation audit and any separately reviewed/released governance delivery before pinning the candidate. Verify the resulting clean HEAD, source/config/lock identities and prepared environments; do not assume the final pin is Task 3 HEAD if documentation has since been delivered. Then run one serial full Windows coverage suite alongside Fable's read-only final review and the mandatory full WSL gate in its independent environment/data location, with one coverage writer per worktree and no source/index/environment mutation during measurement. Preserve default selection/root conftest, native/guard and terminal-record validity, the product floors, skip qualifications, complete per-run evidence and Task 0's gap-decile measurement. Final timings remain evidence; do not rewrite the measured candidate afterward. No additional operator reconfirmation of C1 or CLI repair is needed.

This grants local Task 6 preparation/execution, not acceptance of unrun gates, further commits, push, PR, merge, clone cleanup, service activation or paid calls. Linux CI and comparable safety-module evidence stay UNKNOWN/held until separately authorized publication and actual receipts. Required Stage B and the LOW partial-commit correction remain open; all other Plan 11.28 holds remain. Codex remains reviewer, implements no code and has not started the test runs.


## Current delivery — Task 3 local commit verified

Recorded 2026-10-05 05:59:18 UTC. Codex confirms the released local commit `1b300cfe9f1afc8c1b02e164fc3bd5f698e0fef1`, parent `1f8ca301c435377bdd29f7e5c54159ebb06d0c1c`, branch `agent/claude/plan-11-30-test-profiles`; implementing tree is clean. All 16 released paths and actual Git blob identities match the sealed staging/commit receipts. The committed 14-file tested-source diff remains `4373b171f4f771a25b91b249560cdb8ba7a6e7f0959e8dd83d21ae4994b947e5`. Complete committed diff is `1ee2dedcb8a8f369604458a066dff2916c132708555e6da314eb027b3db3f1c3`. Both precise report-only conditions below are satisfied, closing this local release action. No further Task 3 corrections or source re-review are requested.

Evidence source: operator-relayed `2026-10-05-claude-task3-commit-report-plan-11-30.md`, SHA-256 `a3ea2a264d49f0c4b00b10f4f226c454125afbee915a877eeb0005cc7e5440b0`. Codex independently verified all 31 files in the commit-receipt seal `8d963be63181577948763f5010b6927171d26c0a943f5418ac922b73db650403`, read actual hook output, checked committed report/manifest and recounted raw hook node/phase records. Repository report SHA-256 `e0e9d503c0477c6e812a66d3ea61fcf99559fdca206b5f56b85697d1d8802376`; manifest `82c263007cfbf602d6e22fc537b91246f3d3f9bde3a0390fc2e006bd29965330`. The qualified Redis-helper reach and original-module count wording are present in the committed records; old seals remain historical.

All ten normal hooks report Passed, without SKIP or --no-verify. Fresh post-edit receipts report docs 85 passed, both secret scans/whitespace/Ruff/LF clean. Codex also ran fresh full-tree Ruff successfully. Real commit-hook run `20261005T043841-39004-dd54e8` independently recounts 5,131 selected, 5,091 passed, 40 skipped, zero failed. Terminal record validates COMPLETE/ACTIVE, native valid, full process guard, with retained `parent=not_found:ancestor_exited` qualification. Raw duration/classification join: 136 nodes above 2 seconds, none default-origin.

The 26-node increase from hook5 is confirmed by set difference: 26 additions, no removals. Staging the report/manifest adds the unmapped manifest fallback and its dependency readers, including the two fu_10 timeout controls. Selection records bind to the final staged diff, 16 changes, zero provisional. The run's recorded HEAD is the pre-commit parent; this is valid staged-hook evidence tied to the verified committed blobs, not a post-commit full-coverage or exact-final gate. WSL's next-checkpoint obligation remains.

Task 6 C1 still awaits the operator's explicit command-substitution disposition; no execution release is inferred from this commit relay. Claude/Codex continue to recommend direct CI-equivalent serial default pytest coverage plus the product report. The reviewer owns the current-state document audit before the final pin; any required governance delivery is separately reviewed/released before that pin. Full Windows/WSL final coverage, actual Linux CI/safety comparison and required Stage B remain open. Stage B work remains authorized by the approved plan but sequenced after Stage A, not cancelled. Push/PR/merge, clone cleanup, service/paid-call and other Plan 11.28 holds remain. Codex performed review/governance filing only and no implementation or commit.


## Current decision — T3-M1 resolved; Task 3 accepted with report corrections

Recorded 2026-10-05 03:10:01 UTC. This disposition supersedes the earlier A/B HOLD below; the earlier finding and receipts remain history. Codex accepts Task 3 on `1f8ca301c435377bdd29f7e5c54159ebb06d0c1c` plus tested 14-file diff `4373b171f4f771a25b91b249560cdb8ba7a6e7f0959e8dd83d21ae4994b947e5`, including the bounded unit-isolation repair in `tests/unit/acp/test_main_wiring.py`. This is source-bound implementation acceptance, not Stage A final or exact-commit acceptance. C1 still awaits the operator; Task 6 execution is held.

### Independently checked evidence

Return packet `2026-10-05-claude-task3-t3m1-packet-plan-11-30.md`, SHA-256 `ad254c66a73d44618592eef132816b52ea52df8af10b3e9cf128b4c9433af0b3`, was relayed by the operator in this Codex chat. Codex read it and the complete sealed Fable bounded verdict. The 107-file seal `9831fa427f381d2cb9774afa2fd73e6c5baa6d71d420989d1749e2709340aff3` verifies without mismatches; the 15-member source backup also verifies and its 14 source files match the lane. Current complete diff recomputes to `6f6586a3f2439bab9fe5905b8a0c7cbbf91a116c8fdba656dc2f7f449b68b1b7`. All 14 current source hashes match the retained Windows, WSL and hook5 identities. Report/manifest reviewed snapshot hashes are `1de75e9f3ffb047f798b0add2bf3ed55fc20fc03dec9480200d6c958d5d0cb1a` and `0d8b8fa084af4b5fba29c241e4e32c03704501de662cf1b245f38d2f98d628db`; the report corrections below will produce new identities.

- Hook5 raw node/phase recount: 5,105 selected, 5,065 passed, 40 skipped, no failures; 132 nodes above 2 seconds, none default-origin. Its real selection index digest equals the tested source diff, with no provisional files. Terminal record and runner validity pass with the retained `parent=not_found:ancestor_exited` qualification.
- Windows g3: stdout reports 1,140 passed/2 skipped; actual terminal record is COMPLETE/ACTIVE with valid native job and full process guard. Independent raw-phase/classifier join finds 71 slow nodes and no default-origin omissions.
- WSL: retained real terminal output reports 648 passed/24 skipped in each TMPDIR state, COMPLETE/exit 0. Native/parent/guard remain unsupported-platform qualifications, not Windows parity. Cross-platform file hashes match; retained census reports ten slow nodes and no default-origin omissions in each run.
- Retained post-report docs gate: 85 passed; actual record validates. Secret/whitespace/LF receipts pass. Fresh independent full-tree lane Ruff and Git diff check pass. Codex verified receipts and source; it did not rerun the long suites or hook.
- Test-first RED catches the previously unstubbed Redis helper; final amended controls report 128 passed. All eight final mutation outputs show their intended guard/assertion failures. Earlier ambiguous-anchor and invalid-TOML attempts remain weaker failed history, not targeted mutation successes.

### Why the correction is accepted

The six-node union includes both earlier hook runs; 235 measured nodes now have explicit classifications. The collection-dependent selector belongs with the existing gates sharing its universe fixture. Real process-tree, teardown-child and Git end-to-end controls receive proc rules for their actual work. The wiring control remains explicit core after isolation. Fable's two source wording amendments are present before hook5/g3/WSL final evidence; earlier hook4 bytes are not relabelled as final.

Explicitly accept the additional wiring file as the narrow correction necessary to resolve T3-M1 within the existing task: one missing Redis stub and a module tripwire, with a control anchored to the actual imported helper names. The original environment-capture/Gateway assertions remain unchanged; no production behavior or scope objective changes. Tiering an unintended host-infrastructure call would leave the unit-isolation defect in place. No successor plan or new service-start authority is inferred.

### Two report-only amendments before the released commit

1. Replace the report's claim that these runs executed `docker start optimus-redis` with the supported claim: the test reached the real `ensure_local_redis` helper, whose conditional implementation can probe Docker and attempt a start/create with readiness polling. The tripwire and timing support that reach; they do not preserve a per-command subprocess trace. The observed container StartedAt `2026-10-04T22:01:11Z` postdates both slow reaches and is not attributable to them. State this qualification in the repository report and any equivalent manifest claim. Preserve sealed historical packets/Fable verdicts unchanged; their stronger attribution is not adopted by Codex.
2. Replace “unlike its 69 siblings” with “unlike the other tests in the original 69-test module”: the original subject had 68 siblings; the new tripwire control brings the module to 70 tests.

Claude may apply these precise report/manifest corrections, take fresh post-edit docs/secret/diff/LF receipts and seal new report/manifest/final-diff identities while preserving the old seal. No source change, long-suite rerun or further review round is required for these mechanical corrections. The accepted tested source must still recompute to `4373b171…`; stop for review if it changes.

Reviewer filing checks: current changed Markdown links and four direct docs-index/backlog controls pass; frozen v4 SHA remains unchanged. Full main docs suite was not run. A broader link scan encountered unchanged historical backlog links outside this lane; no other lane was edited. Main Git diff check passes.

### A/B release and remaining boundaries

**A: accepted**, including the named isolation repair and the two report-only pre-commit conditions. **B: expressly release one local Task 3 commit**, after those corrections and checks, with all 16 paths below staged by name in the actual default index. Normal hooks, full-tree Ruff, docs and secret checks are mandatory; no SKIP and no `--no-verify`. Verify staged paths and unchanged tested-source identity before committing; retain the normal hook's new receipt and report actual commit SHA/status afterward. Earlier hook5 is dirty-source evidence, not proof for the eventual commit SHA. Reviewer documentation is read from this checkout; do not silently add its import to this 16-path code commit. Any separate governance delivery precedes the final candidate pin and remains separately reviewed/released.

```text
.github/workflows/guardrails.yml
.pre-commit-config.yaml
AGENTS.md
CONTRIBUTING.md
docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json
reports/plan-11-30-test-profiles-evidence.md
reports/plan-11-30-test-profiles-manifest.json
tests/profiles.toml
tests/unit/acp/test_main_wiring.py
tests/unit/guardrails/test_ci_parity.py
tests/unit/guardrails/test_tracked_file_scanners.py
tests/unit/tools/run_context_child_sites.json
tests/unit/tools/test_coverage_products.py
tests/unit/tools/test_run_profile.py
tests/unit/tools/test_test_profiles.py
tools/testing/coverage_products.py
```

C1 remains pending operator approval of the jointly recommended direct full command; no Task 6 run is released by this acceptance. C2 known omissions are resolved; new final timings remain evidence and require a recorded disposition for any new omission. C3 current-state documentation audit and exact final pin precede final runs; remote CI/safety proof remains UNKNOWN/held. D remains required LOW Stage B work under the same backlog owner. Checkpoint C stays after Task 4. Failed evidence, weaker WSL capabilities, other-lane g3 host overlap and the partial archival refusal remain qualified. No solo-host timing claim, push/PR/merge, service/paid action, clone cleanup or other Plan 11.28 release is added. Codex changed reviewer/governance documents only.


**Historical decision (superseded above):** bounded HOLD on Task 3 acceptance and its local commit release: one newly demonstrated duration-classification contract gap, T3-M1. Product-floor implementation, normal fully staged hook attribution and Fable's three report corrections are supported. Codex is architect/reviewer and implemented no code. Recorded 2026-10-05 01:39:41 UTC; operator-local date 2026-10-05.

## Verified source and evidence

Operator relayed Claude's Task 3 packet in Codex chat `01a10617-9940-72c0-a5e2-e3f8c3241055`. Full packet `2026-10-05-claude-task3-stage-a-packet-plan-11-30.md` SHA-256 `3ec2471bdc29896ad7e8994337cc4f88ffa4199121b7e69e7c58c13709fc0ccc`. Codex read the sealed final Fable verdict in full. Fable confirms SOUND WITH AMENDMENTS, report amendments applied, the two failed hook exercises attributable to setup, normal fully staged hook pass, and LOW partial-commit residual. T3-M1 below is new evidence against the frozen contract, not a silent reclassification of those settled findings.

- Claude lane: `C:\worktrees\optimus-cost-agent-worktrees\optimus-cost-agent-wt-claude-p1130`, branch `agent/claude/plan-11-30-test-profiles`.
- Local B commits independently confirmed: docs `0a6660955654dd22d27f40a171ac44673800c006`; combined Tasks 1–2 `1f8ca301c435377bdd29f7e5c54159ebb06d0c1c` (current HEAD). Their named coverage-hook exception has expired.
- Tested 13-file diff independently recomputed: `913926d1999227990d16d0448d4ba27ae346a13d4d7a31162bfb1b0db8e84f9a`.
- Final 15-file diff, report-only additions: `56823a0ff4e52174c7a5cf2f64fcd0909bd93d228313fbdcd899674635b0b2d2`. Current implementation bytes match the 13-file backup and Windows/WSL/hook3 hash lists. Both intent-to-add files must be fully staged by explicit name at any later released commit.
- Final report `reports/plan-11-30-test-profiles-evidence.md`, Task 3 section: SHA-256 `e9e8597b9b71737e5e1dbb5a04d10243f21b3c86dc3e53de038d976a28cce1fc`; manifest `reports/plan-11-30-test-profiles-manifest.json`, `sections.task3`: SHA-256 `7b5dc9bb4187378e6ff737c89d027d58248cc8ab82e1b3a9a147f3dd76e5f592`. These are reviewed snapshot identities, not commit identities.
- All 87 receipt files match seal `7da0361754f1e22cbe207153db358262a37572f23a675f299682cc24c12bacea`; all 16 post-amendment files match seal `e6e85fcdcf070b41527202ef52b5173e14bbdbbf75ecdd7629362beb03231123`. Void first seal remains explained, not counted as valid. Raw handoff material is archival provenance; durable claims belong in the repository report/manifest.
- Frozen [v4](../plans/2026-10-04-plan-11-30-test-profiles-implementation_v4.md) raw pin independently remains `8A40DEF6D627EDC722D9FA925BBB0C193DE433ECCB91D2DCA19F1DA6AFC5C790`.

Codex independently checked workflow/hook diffs, coverage-product implementation/controls and real run validity; full-tree lane Ruff and diff check pass. Twelve direct pure floor, full-binding, completeness and safety-comparison controls pass. No full suite or new hook exercise was run by Codex.

| Retained verification | Result and qualification |
|---|---|
| Windows focused gate | 1,048 passed / 2 skipped, 1,050 nodes; COMPLETE / ACTIVE / valid native job / installed guard |
| WSL final focused gate | 555 passed / 24 skipped in each TMPDIR state; real WSL, weaker capability labels retained |
| Real hook exercise 3 | 5,107 selected; independently recounted 5,067 passed / 40 skipped / zero failed; COMPLETE / ACTIVE / valid native / full guard protection; parent not_found:ancestor_exited retained |
| Hook index binding | Commit view, 13 changes, no provisional divergence; index SHA-256 equals `913926d1…`; default index and hook index agree; no commit created |
| Post-report checks | Docs 85 passed, secret scans/diff exit 0, all changed-file CR counts zero |

The eight recorder-control nodes with setup/teardown only are distinguished from the 5,059 passing call nodes; the combined hook total is 5,067. Only the pytest hook was exercised, so all other normal commit hooks remain required. The two previous failed hook exercises remain failed and attributable to setup. The three report corrections (37 controls, qualification of fully staged commits, mutation result labelled per ledger) are applied. Missing original mutation stdout is not independently verified mutation proof and cannot be recovered merely by sealing later; any later retained rerun is new evidence, not retrospective stdout.

## T3-M1 — Four known slow nodes still have implicit core classification

**Major plan-fidelity finding; bounded fix.** V4 design section 1 states: "Default core is allowed for cheap new nodes; measured setup+call+teardown >2 seconds requires an explicit rule." Task 1 requires a duration-explicit guard. Codex independently summed each node's setup/call/teardown `seconds` in hook3's sealed `phases.jsonl`, joined its digest to `selection.json`, and applied the current manifest with `classify_nodes`. Of 137 nodes above two seconds, exactly four have origin `default`:

| Node | Recorded phase seconds | Current tier / origin |
|---|---:|---|
| `tests/unit/tools/test_coverage_products.py::test_a_real_repository_s_current_full_run_data_is_evaluated_end_to_end` | 2.526856 | core / default |
| `tests/unit/tools/test_run_p11_fu_10_acpx_error_code_evidence.py::test_acpx_timeout_kills_every_descendant[middle-exited]` | 5.274831 | core / default |
| `tests/unit/tools/test_run_p11_fu_10_acpx_error_code_evidence.py::test_acpx_timeout_kills_every_descendant[parent-alive]` | 5.268861 | core / default |
| `tests/unit/tools/test_test_profiles.py::test_a_session_hook_change_selects_the_run_context_controls[tests/conftest.py]` | 19.373105 | core / default |

These are recorded phase durations, not session wall time or unmeasured estimates. Other slow core nodes already have explicit rules. Historical snapshot guards alone did not catch the four newly demonstrated omissions. No gate escape or coverage-floor defect is inferred from this finding.

Claude should add a failing control for these known measurements, then the smallest explicit rules with documented tier rationale; use the measured node identities/prefixes without inventing another timing framework. Explicit core is permitted if justified by the cost/purpose contract; do not classify every slow node as proc solely by duration. Reconcile the reviewed measurement input/evidence before pinning Stage A. Do not silently narrow the >2-second contract to only the older reference snapshot or defer these known omissions to Stage B.

Run affected classifier/selector/product controls and the four affected nodes on real Windows/WSL, with existing cross-cutting declarations/guards, and document any deliberate selection changes. Obtain Fable's bounded disposition of T3-M1, retain source-bound hashes and a fresh normal fully staged hook proof for the changed candidate, then return the corrected packet to Codex. No repeated Checkpoint B, Task 0 diagnosis or intermediate full suite is requested. Earlier hook evidence remains valid for its old source, never relabelled as proof for changed manifest bytes.

## Rulings A–D

**A — Task 3 acceptance / labels:** HOLD pending T3-M1. Keep v4's labels: this is Task 3 / Stage A implementation review; Checkpoint C remains after Task 4. The prior Codex B review's instruction calling Task 3 Checkpoint C was a reviewer error, corrected here without editing the historical B release bytes.

**B — Local commit:** HOLD pending the corrected source, Fable then Codex acceptance. Agree with one local Task 3 commit, all final paths fully staged by name, normal hooks, no SKIP and no --no-verify. No present commit release or new coverage-hook exception. Implementation corrections remain within the existing plan grant; Claude may make the bounded test-first fix without another operator coding-approval round.

**C1 — Final command discrepancy:** Claude and Codex agree on the simpler direct serial default pytest command below, plus the product report. Actual `run_profile` accepts only commit/checkpoint/quick; static full is identity, and v4's exact Task 6 command is unsupported. AGENTS.md says the plan file is the contract and conflicting execution needs an operator disposition. The specific Plan 11.30-only substitution has been presented to the operator; it is PENDING, not granted by this review. Preserve v4 bytes. Alternative if declined: Claude repairs support for the promised full CLI and verifies it within the plan; Codex implements no code.

Proposed Windows command, matching CI flags including verbosity and adding prepared-environment `--no-sync`:

```bash
uv run --no-sync pytest --cov --cov-branch --cov-fail-under=0 --cov-report=term-missing --cov-report=json:tmp/coverage/full.json -v
uv run --no-sync python -m tools.testing.coverage_products report --coverage-json tmp/coverage/full.json
```

One serial coverage writer, untouched root/default selection, full universe, valid terminal record, product floors and gap-decile checks remain mandatory. Use an explicit verified run-record path if automatic binding is ambiguous; never accept another nested/partial run. Separate prepared WSL environment/data and its full pre-finalize gate remain required. No full run is released while Task 3 or C1 remains held.

**C2 — Measurement refresh:** reject blanket deferral of known missing explicit rules. Fix T3-M1 and reconcile current reviewed measurements before the candidate is pinned. Once pinned, retain new final-run timings as evidence without rewriting tracked tests/manifest during or after the measured run. A later Stage B snapshot refresh remains owned under the same feature; any newly demonstrated classification omission must receive a recorded contract disposition before Stage A sign-off, never silently ignored to preserve a green exact-source claim. No promise to edit final-source files after a passing run, and no unnecessary full rerun to refresh metadata.

**C3 — CI and document audit:** agreed. Local final evidence can be gathered once the candidate and command are released, while Linux CI/safety-row comparison remains UNKNOWN/held until appropriate push/PR authority and comparable exact-base/candidate receipts exist. Do not substitute a Windows base-only full run. Stage A delivery/CI sign-off and plan closure remain held. Perform the reviewer current-state doc audit before final candidate pinning; any justified docs changes are reviewed and locally delivered before that pin. Their actual commit release remains separate, with normal hooks. A docs-only post-run change cannot silently rebind a commit-sensitive final report to a new HEAD.

**D — Partial-commit file-list gap:** agree with Fable/Claude LOW grade and Stage B custody under `P11-FEAT-TEST-PROFILES`. This is the pre-existing conftest GIT_* isolation / default-index walker interaction, separate from the selector's correctly proved hook-index view. The false-pass direction is demonstrated at file-list level and reasoned at end-to-end gate level; do not claim the latter was reproduced. Require a failing real partial-commit scanner control and the narrowest reviewed fix in Stage B before Plan 11.30 closure. This is owned required follow-up within the still-open plan, not an unowned exclusion or a second work pool. Stage A named local commits must stage every included file in the actual index; actual full Linux CI remains the delivery backstop, not currently passing evidence. No shared scanner change is requested now.

## Next pickup and boundaries

Claude reads this review and the reviewer log, verifies the current tree, then corrects T3-M1 test-first and seeks Fable/Codex bounded acceptance. C1 operator disposition remains pending independently. Task 3 commit and Task 6 execution are not released by this record. Keep the three disposable hook clones and all failed/sealed evidence until further disposition; no cleanup grant is added. Push, PR, merge, paid/service actions and other Plan 11.28 holds remain unchanged. No source implementation, commit, host archival, cleanup, external message or memory write by Codex.
