# Plan 11.27 v12 — Integrate accepted FU-6 correction and deliver Slice B locally

> **For agentic workers:** Use the executing-plans workflow task-by-task. Fable 5.1 is the proposed integration executor; Codex authors governance and independently reviews. Do not rebuild either accepted implementation.

**Authority:** The operator approved commissioning the six-task integration plan. This sealed document is the concrete execution proposal. Its proposed new 120 combined-active-minute allowance is not yet granted. Accepting v12 and that allowance releases Tasks 1–3; Task 4 separately requires an operator P1 bound to the actual combined tree before any integrated Gateway execution or delivery hook. No inherited investigation, correction or historical P1 grant substitutes for that gate.

**New authoring finding requiring disposition:** the existing Windows local hook is encoding-sensitive on frozen v2–v8 documents. Execution approval must explicitly accept preserving that disclosed local-hook limitation within this production-only delivery scope, or commission a separate repair/policy disposition first. General commissioning approval is not a waiver. No baseline expansion or encoding workaround is proposed here.

**Review incorporation:** This is the complete successor to the frozen v11 proposal, incorporating Fable's `REVIEW-2026-09-05-fable-plan-11-27-v11-integration.md`. V11 remains unchanged at its reviewer/output locations and is not an integration commit input; v12 occupies that one successor slot, keeping the package at 24 paths. No execution grant is created by publishing a revision.

**Goal:** Produce one reviewed local commit containing the preserved production CI scanning work and the accepted bounded early-POST correction, with separate full Windows rehearsal and actual-commit evidence.

**Architecture:** Materialize the two preserved deltas on the exact accepted Slice A parent in a new independent Git clone. Preserve all original lanes. Resolve only README/backlog overlap using Codex's supplied merged documents, review the combined tree, then run the unchanged Windows gates under a new exact-hit grant.

**Tech stack:** Existing Windows CPython 3.14.4 and locked pytest/pre-commit/detect-secrets/Ruff/coverage tools, native WSL CPython 3.14.6 for comparison, Git, existing hooks. No dependency, baseline-policy, protocol or infrastructure redesign.

**Spec and full identities:** This complete plan incorporates the final states of [v10](2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v10.md) and the accepted [FU-6 v2 correction](2026-09-05-p11-fu6-bounded-early-post-rejection_v2.md). Full input digests, exact paths and the 24-path package inventory are in the external companion `plan-11-27-v12-inputs.json`; the release manifest binds both documents. Short identifiers in this plan are labels only: execution compares full recorded identities. The external pin record is an execution/evidence input, never a commit input. It contains integrity values rather than credentials; keeping full digests there avoids adding new scan-bearing literals to frozen plan custody.

## Prerequisites

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|---|
| authority | Commissioning this six-task plan | yes | Operator / Codex | Granted by the operator's latest approval. |
| authority | Accept v12 and its new 120-minute execution box | no | Operator | Merely unauthorized; this is the concrete budget proposal, with no transfer from the correction box. |
| authority | Disposition of the verified local-hook encoding limitation | no | Operator | Merely unauthorized; preserve it explicitly within this narrow delivery scope or commission separate repair before execution. |
| authority | P1 naming the failed delivery log and final combined tree | no | Operator | Merely unauthorized; the final tree must first exist and receive Codex review. |
| executor | Proposed executor Fable 5.1 and reviewer Codex | yes | Operator / Fable / Codex | Continues the established implementation/review separation; execution still obeys the grants above. |
| inputs | Accepted Slice A parent, stopped Slice B, accepted FU-6 correction | yes | Fable / Codex | Full input record binds preserved paths and hashes; recheck at entry. |
| custody | Correction closeout and historical evidence | yes | Fable / Codex | Final 65-entry and prior 47-entry manifests verified; older two-summary loss remains disclosed. |
| isolation | New integration and rehearsal directories | no | Fable | Genuinely absent until authorized setup; require absent destinations and contained independent Git stores. |
| tooling | Existing Windows and native WSL installations at execution pickup | unknown | Fable | Genuinely absent fresh entry verification; use pinned installed tools without repair or sync. |
| package | Reviewed combined tree and stageable exact path list | no | Fable / Codex | Genuinely absent until Tasks 2–3; no tree hash is invented in this draft. |
| delivery | At least 65 combined active minutes remaining at Task 4 entry | no | Fable / Codex | Genuinely absent measured execution balance; reserve the whole final sequence before staging. |

## 1. Inputs, isolated destinations and current facts

- Read-only Slice B source: `C:/worktrees/optimus-cost-agent-wt-claude-ci-production`. HEAD is the accepted c1989985 Slice A commit, whose parent is 5ea8f8f and whose tree is 258406df. The input record supplies full values. It currently has ten modified and ten untracked in-scope files, no staged changes. Its complete tracked-diff hash and every individual file hash are pinned externally.
- Read-only correction source: `C:/Users/pc/AppData/Local/Temp/fu6-correction-20260905T114209Z/checkout`. Same parent; source eff6ec9e and regression c9cbcf3f are accepted unchanged. The sibling evidence contains `correction-closeout.patch` (9af1bf4c) and `MANIFEST-sha256-closeout.txt` (862c6da1). The correction is accepted and uncommitted, not integrated.
- Failed delivery log: `D:/Projects/Development/Python/optimus-ci-production-evidence-slice-b-20260905/gate3-05-full-hook-rehearsal-updated-backlog-20260905T095009Z.log`, label d5113893. It failed on the committed Gateway route test with WinError10053. The full digest is in the input record. The failed proposed tree b32fd969 is an uncommitted tree, not a commit from which to clone.
- Preserve the failed v10 rehearsal at `C:/Users/pc/AppData/Local/Temp/claude/plan1127-v10-slice-b-rehearsal`, the earlier v9 rehearsal, the passing historical rehearsal refs, the incident Linux environment, main, the parked diagnostic lane and sandbox. No reset, clean, delete, tag, rebase, branch removal or repair in any of them.
- On the actual first execution action record UTC and choose a previously absent root `C:/Users/pc/AppData/Local/Temp/plan1127-v12-<UTC-start>`. Its children are `integration`, `rehearsal`, `evidence` and `tmp`; the latter two must remain outside both tested checkouts. The label is derived from the measured start, not an estimated timestamp. No tools write into frozen evidence directories.
- Proposed new integration branch: `agent/fable/plan1127-integration-v12`, created only inside the new independent integration clone at the bound Slice A commit. Rehearsal stays detached. Preserve both new repositories after any outcome. No remote fetch or drift absorption; a changed bound source stops for review.

### Evidence interpretation and preservation

The accepted host-local result is that unread-body-before-close behavior was causally involved in the tested failure mode. Packet-level mechanism, universality and zero-flake probability were not established. Two older derived correction JSON summaries were overwritten; their raw log survives. Exact-hash reconstructions recovered the prior test, patch and end marker. Retain the custody deviation and reconciliation, not a claim of uninterrupted preservation.

The existing scanner uses a default-encoding file read and catches `UnicodeDecodeError`, returning without scanning the file and treating it as binary. Its verbose “Checking file” message precedes the read and is not proof of scanning. Independent authoring and Fable controls found the exact unchanged Windows local hook exits 0 in its inherited CP1252 mode, while enabling UTF-8 produces 25 findings: 18 integrity-digest findings and 7 example-URL findings in frozen v2–v8. These reviewed values are non-credential; they are not 25 newly discovered live credentials.

**Eight commit-input documents are skipped entirely under the observed CP1252 mode.** All are under `docs/superpowers/plans/`:

| Skipped file | Required disposition / supplementary check |
|---|---|
| `2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v2.md` | Frozen; explicit local-hook limitation disposition, no edit or baseline expansion. |
| `2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v3.md` | Same frozen-document disposition. |
| `2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v4.md` | Same frozen-document disposition. |
| `2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v5.md` | Same frozen-document disposition. |
| `2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v6.md` | Same frozen-document disposition. |
| `2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v7.md` | Same frozen-document disposition. |
| `2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v8.md` | Same frozen-document disposition. |
| `2026-09-05-p11-fu6-bounded-early-post-rejection_v2.md` | Clean under UTF-8; explicitly scan this file alongside the new successor and merged documentation. |

Preserve the v11 paired-control records and Fable's review in external evidence. The default local pass for these eight files is vacuous, not a complete scan. The v9 three-entry exception remains path-bound and unchanged. The production CI/manual hook already uses explicit UTF-8 and tracks production text; that guarantee is still required.

The pre-existing local-hook decoding/completeness issue belongs to `P11-FEAT-ACP-RUNTIME-HARDENING`. Operator execution approval must explicitly accept preserving this limitation for the narrow production-only delivery or commission a separate repair/policy first. Do not claim repository-wide cleanliness, alter frozen documents, add baseline entries or change encoding to make delivery pass. A repair requiring all frozen documents to be UTF-8-scanned is outside the present policy; v12 remains blocked if that is the operator's choice. The conditional recommendation is to retain the limitation for this delivery and keep its separate owner, not to declare it fixed.

Use unique run directories and names from measured UTC. Once an artifact appears in a manifest, never overwrite it, including patches, snapshots, JSON, end markers and the manifest itself. Each extension creates a new manifest and verifies the preceding one against retained original paths or an explicit exact-hash relocation map. Do not regenerate an old artifact and label it original unless its previous full hash matches.

## 2. Exact package and merge policy

The external inventory enumerates **24 commit paths**:

| Group | Paths | Treatment |
|---|---|---|
| Preserved Slice B functional delta | `.github/workflows/guardrails.yml`, `.pre-commit-config.yaml`, `.secrets.baseline`, `tests/unit/guardrails/test_ci_parity.py`, `src/evidence_handoff_runtime/migrations.py`, `src/optimus/acp/launch_policy.py`, `src/optimus/acp/local_gateway_secrets.py`, `src/optimus_gateway/observability.py` | Copy exact current accepted Slice B bytes. No new annotation, detector, filter, threshold or configuration changes. |
| Shared documentation | `README.md`, `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | Use only the supplied, hashed merged README/backlog. Preserve both scopes and their historical records; do not replace the backlog with either lane's whole copy. |
| Slice B frozen custody | Plan 11.27 v2–v10 at their existing root paths; the archived 2026-09-03 scratch predecessor | Copy all ten records byte-exact from Slice B. The input inventory supplies every filename. |
| Accepted correction | `src/optimus_gateway/server.py`, `tests/unit/optimus_gateway/test_request_body_rejection.py`, `docs/superpowers/plans/2026-09-05-p11-fu6-bounded-early-post-rejection_v2.md` | Copy exact correction bytes. Do not transplant the separate parked `test_server.py` diagnostic. |
| This complete successor | `docs/superpowers/plans/2026-09-04-plan-11-27-git-test-immunity-and-production-secret-scan_v12.md` | Copy sealed v12 byte-exact with its one live-registry row. |

The only overlap is README/backlog. No runtime overlap exists between the accepted correction's server file and Slice B's observability annotation. Before applying anything, prove the two sources still have the recorded common parent. Do not apply either complete patch blindly over the other: that would overwrite shared documentation.

### Explicit exceptions and retained limits

1. V12 replaces v10's instruction to commit in the original candidate: the actual commit occurs only in the new integration clone. Original candidate and correction checkout remain read-only evidence throughout.
2. The bound Slice A commit, rather than current remote main, is the intentional integration parent. Its three prerequisite test changes remain unchanged. No rebase or opportunistic dependency update is included.
3. V10's no-production-behavior-change rule is superseded only for the accepted FU-6 `server.py` delta. Its 64 KiB rejected-body cap, two-second total body deadline, separate two-second shared response budget, HTTP/1.0 policy and unchanged recognized routes are preserved exactly. The four Slice B annotated modules must still retain base AST/docstring/SQL equality.
4. Retain registered v2–v10 predecessors in place under the already approved transitional custody exception. Do not archive or rewrite them. Moving frozen v9 would invalidate the exact baseline path policy; broader archival requires its own proof and disposition. FU-6 v1 and the unexecuted v11 proposal are reviewer-only and not imported. V11 remains registered Blocked only in the reviewer lane; the integration registry contains v12 instead. V10 is explicitly Blocked in the merged registry, with its spent grant and failed delivery retained as history.
5. Only inside the two new clones, copy the exact existing generated pre-commit hook into `.git/hooks/pre-commit`; prove byte equality. This narrowly permits local hook-file setup, not installing tools or regenerating the hook. No `pre-commit install`, environment rebuild, package upgrade or sync.
6. The operator's later P1 may authorize the bounded tests and two commit-hook attempts specified here. It does not authorize a third attempt, a new-hit retry, marker narrowing, timeout widening, WSL substitution, skipped hook or baseline expansion.
7. External evidence and release records carry post-run outcomes. All commit-input prose is settled before the reviewed tree is pinned; do not insert a premature Delivered claim or edit the backlog after a passing rehearsal. Later documentary closure/publication is separately owned by the consolidated backlog.

## 3. Tooling and environment

Use Windows `C:/worktrees/optimus-cost-agent-wt-claude-ci-production/.venv/Scripts/python.exe` directly, with `PYTHONDONTWRITEBYTECODE=1`. Verify installed tool identities against the input record. In Git Bash, prepend `/c/worktrees/optimus-cost-agent-wt-claude-ci-production/.venv/Scripts` to PATH. Reuse the existing cache at `/c/Users/pc/AppData/Local/Temp/claude/pc-home-rehearsal`; a missing cached dependency stops, not installs.

If an existing workflow command requires uv, set per-invocation `VIRTUAL_ENV` and `UV_PROJECT_ENVIRONMENT` to the Windows candidate venv, plus `UV_NO_SYNC=1` and `UV_OFFLINE=1`. No `uv sync`, Python download, cache repair or environment creation. WSL uses `/root/optimus-ci-venv/bin/python` and its native venv variables, never the Windows venv. Verify candidate `pyvenv.cfg` hash and `Scripts/python.exe` before/after WSL. Prove imported `optimus_gateway.server.__file__` points into the tested checkout for every platform/process; an editable install pointing elsewhere is not evidence.

Strip inherited `GIT_*` variables for Git setup, source reads, commits and fixture subprocesses. Set task-specific temporary variables only for explicit throwaway-index calculations. Resolve both `--absolute-git-dir` and `--git-common-dir` before writes; require equality inside each new clone, no alternates and no shallow store. Never change a global Git configuration to pass this check. Capture Git binary output as bytes, not PowerShell-decoded text.

### Record the scanner child's encoding, not just its parent

At Task 1 entry and immediately before each Task 5/6 hook attempt, resolve the actual `detect-secrets-hook` launcher and the interpreter it binds. Record the child's inherited `PYTHONUTF8`, `sys.flags.utf8_mode`, `locale.getencoding()` and `sys.executable` using that same bound interpreter under the exact hook environment. Run the probe without `-X utf8` and without an environment override. A parent invoked with `python -X utf8 -m pre_commit` does not transmit that flag to its scanner child; only recording the parent's mode is invalid evidence. If the launcher's interpreter binding cannot be established, stop.

The child probe's code is:

```python
import json, locale, os, sys
print(json.dumps({
    "PYTHONUTF8": os.environ.get("PYTHONUTF8"),
    "utf8_mode": sys.flags.utf8_mode,
    "file_encoding": locale.getencoding(),
    "executable": sys.executable,
}))
```

Use it in a separate no-flag child process with the verified interpreter; do not edit the hook, wrap its entry or install a startup injector to obtain this record. Verify the same launcher/environment again at the attempt boundary. If `PYTHONUTF8` enables UTF-8, the child reports UTF-8 mode, or its effective encoding differs from the dispositioned CP1252 case, STOP before the hook. Never unset that variable, set it to zero, add a flag or substitute an interpreter to clear the condition. A changed shell requires a new disposition, not an automatic run in the older mode.

Keep pytest basetemp, JUnit, coverage custody copies, logs and scanner scratch outside tested roots. `.coverage` created by the unchanged hook in the tested checkout is an explicit temporary exception: preserve and hash it immediately after its run, then derive reports only from a separate external copy. Do not rerun tests to obtain coverage or force all run figures to agree.

## 4. New budget proposal and execution gates

**Proposed allowance: 120 combined-agent active minutes**, starting only on authorized Task 1 pickup. Count executor work, Codex reviews, reporting and concurrent work from both agents; exclude relay idle. No balance transfers from the completed correction box. Record each turn's actual start/end; carry unmeasured tails conservatively, not as fictitious measurements.

| Allocation | Maximum / reserve |
|---|---|
| Task 1 — entry and isolated source | 10 minutes |
| Task 2 — exact materialization | 20 minutes |
| Task 3 — package validation and independent review | 25 minutes |
| Task 4 — exact-tree P1 and gate accounting | 5 active minutes; operator relay idle excluded |
| Task 5 — bounded comparison tests, rehearsal and concurrence | 25 minutes |
| Task 6 — actual commit and immediate proofs | 20 minutes |
| Final evidence, reviewer receipt and reporting reserve | 15 minutes |

Require **at least 65 combined active minutes remaining at Task 4 entry**, then **at least 60 after the Task 4 record is complete**, before any rehearsal or integration staging. The extra five minutes are Task 4 itself; they cannot also be counted in the 60-minute delivery reserve. This retains the historical mandatory-full-gate discipline with room for both commits, review and custody. If preparation overruns or the complete remainder cannot fit, STOP with the uncommitted assembled package. Do not compress the gate, reuse historical coverage, or treat unused budget as new authority.

Preparation has a hard 55-minute maximum across Tasks 1–3, including Codex's review. At Task 3 entry recompute its remaining work against the protected 65-minute Task 4-and-delivery balance; do not borrow from that reserve. If the 24-path export/proofs/review cannot fit, hand off the uncommitted package and stop. This accepts Fable's tight-budget warning without silently enlarging the proposed box.

## Task 1 — Verify entry and create the isolated integration checkout

- [ ] Read v12, external input record, release manifest, the correction closeout receipt, v10 STOP record and governing investigation addendum. Verify full digests; document the actual grant, executor and start in a new entry record.
- [ ] Recheck parent/HEAD/tree, zero staged source indexes, twenty Slice B and five correction paths, exact source/test/baseline/lock/hook/frozen-document hashes, and correction manifests. Record original candidate/rehearsal/other-lane HEAD/ref/status fingerprints and canary before new writes. Drift stops; no repair.
- [ ] Require absent new root and absent integration/rehearsal destinations. With sanitized Git environment, run `git clone --no-local --no-checkout` from the read-only candidate into the new integration directory. In that new clone only, `git checkout -b agent/fable/plan1127-integration-v12` at the full bound Slice A commit from the input record.
- [ ] Prove HEAD/tree identity, complete 984-commit bound history, no shallow/alternates, contained equal Git/common directories, and byte-exact local hook copy. Require the proposed branch name absent before creating it; never reset an existing ref. Record directory, interpreter and the verified scanner-child encoding provenance described above. Do not execute a hook yet.

**Deliverable:** `entry.json`, input verification and untouched-source evidence. An independent clone exists at the bound parent, with an empty index delta and no assembled changes.

## Task 2 — Materialize the exact 24-path package

- [ ] Copy the eighteen non-overlapping Slice B paths and the three correction-only paths from the inventory, verifying raw bytes individually. Copy the two supplied merged documents and this sealed plan. Do not copy `.git`, `.venv`, temp files, parked diagnostics, raw evidence or the external input JSON.
- [ ] Confirm the resulting status has exactly the twenty-four listed changed/new paths, no staged changes, unchanged parent, preserved lock and accepted source/test pins. Check all Slice B functional/frozen file hashes against the source record; the baseline must remain the exact approved three-entry baseline.
- [ ] Use a new throwaway index outside the checkout. Construct a separate child environment containing `GIT_INDEX_FILE` only for `git read-tree HEAD`, `git add --` the explicit 24 paths, and `git write-tree`. Pass that environment to exactly those three Git calls; never export it into the parent shell or reuse it for status, verification, fixtures, staging or commits. All subsequent Git calls use the sanitized environment without it. These calls may add objects only to the new independent integration store. Retain the temporary index as evidence and never use the real index for this calculation. Record the prospective tree and a complete binary patch including untracked files. Prove the real index is unchanged afterwards.

**Deliverable:** exact path/hash map, uncommitted patch, prospective tree and merge proof. README and backlog are the only composed inputs; their full supplied hashes must match.

## Task 3 — Validate and independently review the combined package

- [ ] Validate v12's exact bytes with the repository's `_assert_prerequisites_table`; also call the prospective added-path classifier. A history-only test can miss an uncommitted plan. Run the six plan-directory hygiene checks in a clean complete export and confirm every new plan has one registered row. Do not import unrelated reviewer-only plans.
- [ ] Run installed Ruff, applicable hygiene/config-trust checks and the exact unchanged local scanner hook on the complete prospective staged text inventory in a fresh contained export. Stage only this disposable export's baseline before invocation, satisfying its baseline precondition. Preserve baseline bytes before/after, actual file arguments and inherited encoding; do not label an encoding-sensitive local pass a UTF-8-complete audit. Separately UTF-8-scan this explicit four-file set: the new v12, merged README, merged backlog, and `docs/superpowers/plans/2026-09-05-p11-fu6-bounded-early-post-rejection_v2.md`. The FU-6 plan is mandatory here because the default local hook skips it. Record the exact four paths, full input hashes, exit and unchanged baseline; do not substitute a statement that it appeared in the default hook file list. Preserve the recorded wider UTF-8 audit failure as the operator-disposed limitation; do not repeat it merely to accumulate failures. Do not run the full pytest coverage hook or a commit.
- [ ] Verify the exact baseline structures and the existing binding/policy tests using the focused `tests/unit/guardrails/test_ci_parity.py` selection. Preserve exact assertions, failures and no index leakage. A new scanner finding needs individual review; no automatic pragma or exception. Preserve input source/test hashes.
- [ ] Re-prove full AST equality for the four Slice B annotated modules versus the bound base, including the launch-policy docstring constant. Recompute the three migration SQL integrity comparisons and prove the migration SQL files are unchanged. Compare the accepted correction source/test bytes directly; no redesign or new mutant is needed for byte-identical implementation.
- [ ] Codex reviews the complete diff, documentation, exact proposed tree, source/test/scan/custody proofs and untouched-source invariants. Any change returns to an explicit new tree and named evidence. Settle all commit-input prose now. Do not run the combined Gateway tests yet; their authority is the next gate.

**Deliverable:** `combined-review.md` naming the full prospective tree and all inputs. Preparation success is not a P1 grant or delivery acceptance.

## Task 4 — Record the exact-hit grant and full remaining gate

- [ ] Check at least sixty-five combined active minutes remain at entry, then at least sixty after recording the grant. Report the measured charge and reserve. If insufficient, stop before staging and seek a successor disposition.
- [ ] Obtain one written operator P1 record naming: the full failed-log digest from the input record; the full Task 3 combined tree; the sealed v12/input-record digests; new integration/rehearsal paths; Fable as executor and Codex as reviewer; the bounded Windows/WSL focused checks below; one full Windows rehearsal commit and, only after concurrence, one actual local commit attempt. It must explicitly allow staging the twenty-four listed paths in those new clones only. It is not another budget extension.
- [ ] Record the grant outside commit inputs. No branch of this gate treats elapsed waiting or the current general commissioning approval as the missing exact-tree P1. A tree change voids the tree-bound release and requires a new disposition before delivery execution.

**Deliverable:** exact-tree P1 record and budget checkpoint. Original candidate/correction indexes remain untouched permanently.

## Task 5 — Run the bounded checks and full Windows rehearsal

- [ ] Under the P1, run the new correction file and unchanged Gateway route file on Windows, and once on pinned native WSL. Command shape: `python -X utf8 -m pytest -q -p no:cacheprovider --basetemp=<external-run-temp> tests/unit/optimus_gateway/test_request_body_rejection.py tests/unit/optimus_gateway/test_server.py`. Use the absolute native interpreter, preserve selection defaults, record imports and compare source/test pins. Expected focused count is the accepted 79 unless the exact collection proves a reviewed difference. Unexpected corrected FU-6 failure stops immediately, no retry or WSL substitution.
- [ ] In the new integration checkout, run the workflow's exact tracked-production inventory preflight and manual production hook under pinned no-sync/offline settings; retain the authoritative file count (previously 200), reject empty inventory and prove baseline unchanged. This does not replace the full local staged-text hook.
- [ ] Create a new full-history rehearsal with `--no-local --no-checkout` from the integration clone while it is still at the bound parent. Check out that parent detached, prove independent containment/history/no alternates, and copy the exact twenty-four proposed files and unchanged generated hook. Preserve the original failed rehearsals untouched.
- [ ] With explicit path staging in the new rehearsal, prove its staged tree equals the operator-released tree. Verify source/test/baseline/lock/hook/custody hashes and the scanner-child encoding record immediately before the attempt. The integration real index remains unstaged at this point.
- [ ] Run one real rehearsal `git commit -m "fix: enforce production-only CI secret scanning"` through the complete unchanged Windows hook. Use process-local `PYTEST_ADDOPTS` for an external, uniquely named rehearsal JUnit file and external basetemp only; no marker/coverage overrides. Preserve all hook statuses and the actual command exit. Require commit parent/tree equality, clean rehearsal worktree/index and no baseline rewrite.
- [ ] Seal that run's coverage database before reading, copy externally, derive the report from another copy and prove original bytes unchanged. Label it integration rehearsal coverage, distinct from every previous figure. The unchanged aggregate coverage gate is at least 80%; do not narrow sources, lower thresholds or claim coverage for untested modules.
- [ ] Codex reviews exact successful rehearsal commit/tree, complete hook/JUnit/coverage output, invariants and remaining budget. No post-rehearsal README/backlog edit. A failure stops with preserved staged state and evidence; no reset/clean/tag or automatic repeat rehearsal.

**Deliverable:** a successful rehearsal of the exact P1 tree and Codex concurrence for Task 6, or STOPPED evidence. A rehearsal commit is not delivery.

## Task 6 — Actual local commit, independent proof and stop

- [ ] Recheck integration HEAD, every proposed file, operator-released/rehearsed tree equality, baseline, lock, hook, frozen custody and source invariants. Stage only the explicit twenty-four paths in the new integration checkout. Require staged tree equal to the accepted rehearsal tree and no unstaged tracked delta. Drift stops before commit.
- [ ] Repeat the scanner-child encoding check without overrides and stop on a changed mode. Run exactly one actual local `git commit -m "fix: enforce production-only CI secret scanning"` with the unchanged full Windows hook. Set a new process-local external JUnit path and external basetemp, distinct from rehearsal. Do not use `--no-verify`, `SKIP`, amend, a narrowed test command or recycled coverage.
- [ ] Require exit 0, expected commit parent, exact committed tree, clean tracked worktree/index and no unexpected untracked files. Verify all twenty-four committed paths and immutable inputs. Preserve actual-commit JUnit and its own coverage database/report with the same copy-before-read custody. A fresh hit stops; P1 never grants an automatic second actual attempt.
- [ ] Within the reserved fifteen minutes, Codex reviews the actual commit evidence and final manifest, then records local-delivery acceptance or its precise outstanding gate. Record commit/tree/parent, path map, both run identities, truthful coverage, original-lane/canary invariance, custody gaps and unused budget. No additional optional full-suite run.
- [ ] STOP. The new integration branch holds the local commit; do not copy it into old candidate/main or publish it. If a later docs status update is desired, propose it separately rather than changing the committed tree after its accepted hook run.

## 5. Stop conditions, exclusions and final result

Stop on input drift, unexpected scope, missing tool/cache, containment failure, a new scanner finding without disposition, changed baseline/lock, hook failure, new FU-6 error, unmatched staged/rehearsed/committed tree, insufficient gate time or evidence loss. Preserve every failed attempt. Do not infer causality from a single prior pass or reclassify an unexpected integrated failure as an old control.

| Excluded work | Existing owner / next gate |
|---|---|
| Push, PR, merge, tagging, installation and production rollout | Operator / `P11-FEAT-ACP-RUNTIME-HARDENING`; separate publication/deployment decision after local acceptance. |
| General recognized-route framing/body/header limits and global resource admission | `P11-FEAT-ACP-RUNTIME-HARDENING`; separate compatible hardening design. |
| Universal Windows reliability or packet-level proof; broader FU-6 closure | `P11-FU-6`; separately reviewed closure criteria, no automatic closure from two passing hooks. |
| FU-5, FU-7 and unrelated parked diagnostics | Their existing backlog owners; unchanged and outside this integration. |
| Dependency repair, broad baseline migration, detector/filter changes or frozen-plan archival | `P11-FEAT-ACP-RUNTIME-HARDENING`; separate explicit disposition. |
| Existing Windows local-hook decoding/completeness for frozen documents | `P11-FEAT-ACP-RUNTIME-HARDENING`; verified encoding-sensitive result, requires explicit narrow-scope acceptance or a separate repair/policy plan before v12 execution. |

Success means one independently accepted **local** Slice B plus FU-6 commit in the new integration clone, with the exact released tree and its own full hook evidence. Until that result is actually verified, Slice B remains stopped and FU-6 remains open. This plan does not assert that any integration checkout, P1, staging, rehearsal or actual commit already exists.
