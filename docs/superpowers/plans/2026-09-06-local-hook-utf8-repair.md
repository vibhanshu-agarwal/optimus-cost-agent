# Local-hook UTF-8 repair implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Codex remains the architect/reviewer; the executor implements. Steps use checkbox syntax for tracking.

**Goal:** Make the local secret-scan hook scan selected UTF-8 text consistently on Windows and Linux, and reject selected text it cannot read or decode instead of silently succeeding.

**Architecture:** A small local-hook adapter validates selected file bytes with strict UTF-8 decoding, then delegates to the existing pinned detect-secrets hook in a UTF-8 Python process. Retain pre-commit's existing filename selection, scanner plugins, filters, baseline identities and exit semantics. CI's production-only venue is unchanged.

**Tech stack:** Repository Python >=3.14, locked detect-secrets 1.5.0 installation verified during this review, pre-commit, pytest, Ruff, Windows CP1252 and Linux/WSL validation.

**Spec:** This document contains the bounded specification. Supporting custody: `outputs/pr194-merge/merge-receipt.md`, `outputs/pr194-reconciliation-review-and-plan.md`, and `outputs/local-hook-utf8-root-cause.jsonl` in the architect workspace. Existing owner: `P11-FEAT-ACP-RUNTIME-HARDENING`; governance track: `HARDENING-TRACK-CI-GUARDRAILS`.

## Starting point and authority

Remote main was read at `0ec91225c6f05dfccc62105f7367e5e30879a48b` on 2026-09-06. Its tree is `222183f361ba3ae51128326ca51bec9d3ae4733e`. Recheck before implementation; do not build on the old PR #194 audit head or reuse a sealed delivery lane. Create an isolated checkout from current main and record any drift before adapting the plan.

The operator approved the Fable/Codex commission: 90 executor minutes and 30 independent-review minutes, including tests, hooks, WSL and evidence work. Fable implemented; Codex authored governance prose and independently accepted the local delivery at `c9745898`. That commission is complete. Separate operator approvals authorized publication to PR #196, this pre-merge documentation review, and normal merge if the final head satisfies the required checks. PR #196 records the publication and merge results. No executor clock is restarted; tags, protection changes, installation and rollout remain outside these approvals.

## Prerequisites

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|---|
| Starting point | PR #194 is merged and its post-merge guardrails passed at main `0ec91225` | yes | Codex | satisfied by the merge receipt; recheck identities at pickup |
| Design | Review the UTF-8 adapter, strict decoding rejection and preserved scanner-policy boundaries | yes | Codex and Fable | satisfied by accepted Task 1 evidence, corrected Task 2 review and final local-delivery acceptance; all 43 focused Windows cases passed with the real CP1252 control executed |
| Execution grant | Fable executes within 90 executor minutes and Codex reviews within 30 minutes, including tests and hooks | yes | Operator | satisfied by the recorded operator approval and Task 1/Task 2 continuation receipts; no publication authority or automatic extension |
| Repository promotion | This plan and its matching live-plan registry row are assembled together and pass repository hygiene | yes | Fable, with Codex-authored prose | satisfied by accepted local delivery at `c9745898`, its full hook and the prerequisite test at the delivered HEAD |
| Toolchain | Locked Python/scanner environment, lock and baseline match the reviewed checkout | yes | Fable | satisfied by the Task 3 environment record and unchanged lock/baseline proofs; platform results are recorded separately |
| Platform evidence | Windows CP1252 control executes and Linux/WSL repaired-hook cases pass on the candidate | yes | Fable | satisfied by the two recorded platform runs; the Linux-only historical-control skip is disclosed and is not substituted for Windows execution |
| Local delivery | Codex accepts the candidate and concurs with its normal full-hook local commit | yes | Codex | satisfied by the candidate concurrence, successful normal-hook commit `c9745898` and final independent local acceptance |
| Publication | Authorize push, PR edits and merge of the reviewed repair | yes | Operator | satisfied by separate publication approval and subsequent approval for documentation review and normal merge conditional on the final head's checks; no bypass or protection change |

## Current execution checkpoint

Local delivery at `c9745898` is independently accepted and published to PR #196. Its full-hook JUnit records 3,821 passed, zero failures/errors and 91 classified skips; the separate focused Windows module passed all 43 cases, including the CP1252 control. Corrected WSL evidence records 139 passed and one Windows-only control skip, with the disclosed file-mode qualification. The first PR guardrails run 34043564308 and masterplan run 34043564404 passed on a synthetic merge tree equal to the accepted contents. This documentation successor requires its own full hook and fresh required PR checks before the authorized normal merge. The plan remains under transitional custody pending a separate archival disposition; no further implementation is released.

The corrected adapter accounts for incremental-decoder buffered bytes in error offsets, and the historical CP1252 control skips with measured reasons on other hosts. The 50 UTF-16 transcripts remain byte-exact and reject if selected as local text; staging, renaming or explicit all-file runs can therefore fail. The UTF-8 inventory contains 763 records at 745 distinct path/detector/line locations, not 763 unique locations and not 763 adjudicated false positives. These observations do not widen the 34-entry baseline. The original task checklists below preserve the commissioned work instructions; checkpoint and delivery evidence, including the final acceptance receipt, are retained without retroactively rewriting the sealed records.

## Evidence and limits

The installed `detect_secrets/core/scan.py` opens files without an explicit encoding in `_get_lines_from_file`, catches `UnicodeDecodeError`, and returns no lines. The pre-commit entry point can subsequently return success when there are no findings; it can also update the baseline on its normal maintenance path.

A disposable probe invoked that real reader in separate processes. Valid UTF-8 containing U+0081 returned zero chunks under `-X utf8=0` with CP1252, and one under `-X utf8`. Invalid UTF-8 containing byte FF returned zero chunks under UTF-8 mode. These are reader-level proofs, not end-to-end hook tests; Task 1 supplies the latter.

Previously recorded UTF-8 findings include 25 non-credential values in frozen Plan 11.27 v2-v8; FU-6 v2's supplementary scan was clean. Do not misattribute the 25 to FU-6. Some files decode under both encodings into different text, so successful decoding is not proof of identical scanner results. Current counts must be measured, not copied as new evidence.

## Global constraints

- Preserve all 34 approved baseline entries: three frozen-v9 identities plus 31 identities in five frozen reports. Preserve detector/filter configuration and all baseline-policy negative controls.
- No dependency upgrade, directory exclusion, blanket allowlist, baseline widening, frozen-document edit, or report rewrite.
- Keep local `types: [text]`, filename passing, commit stage and hook identity. Keep CI's tracked production text scope and empty-inventory rejection unchanged.
- Retain full commit-time pytest/coverage. No bypass, skip variable, new environment-wide UTF-8 setting, or global Git configuration change.
- UTF-8 validation covers filenames selected for this local hook; it does not establish whole-repository coverage, binary scanning, race-free snapshots or broader FU-6 closure.
- Existing non-UTF-8 selected text is rejected with an actionable path diagnostic. It is not silently converted, ignored or decoded with replacement characters.

## Task 1: Reproduce the boundary and capture inventory

**Files:** Create `tests/unit/guardrails/test_local_secret_scan_encoding.py`. Keep scratch fixtures and output outside tracked source; use temporary Git repositories and copies of the approved baseline.

**Interface:** Tests invoke the actual configured hook through pre-commit, not just a mocked scanner. A separate direct-reader control may reproduce the historical omission. Use argv lists with `shell=False`; pass paths containing spaces and non-ASCII characters as single arguments.

- [ ] Record Python version, scanner version, lock hash, baseline hash, configured hook entry and current main/head/tree.
- [ ] Add a valid UTF-8 text fixture containing a CP1252-undecodable code point and an artificial detector canary. First prove the canary is detected when read correctly. Assemble artificial canaries in scratch data so regression source does not become a new finding source.
- [ ] Run the historical scanner in a CP1252 process and retain the observed omission. Windows acceptance requires `sys.flags.utf8_mode == 0` and preferred encoding CP1252 in that control; Linux does not substitute for this proof.
- [ ] Add selected invalid-UTF-8 text, a clean Unicode fixture, a clean ASCII fixture and a filename with spaces/non-ASCII characters. The desired invalid-text assertion is nonzero exit with path/reason and no baseline mutation. Show it fails under the old entry.
- [ ] Inventory current tracked text in disposable copies under explicit UTF-8, preserving results by path/detector/location without copying credential-like values into reports. Record decode failures separately from detector findings. Compare known frozen-document results with historical evidence; do not require a clean entire inventory.

**Deliverable:** A reproducible failing regression and an honest findings inventory. Unexpected findings block their own disposition; they do not authorize new exceptions or automatically invalidate the encoding mechanism.

## Task 2: Implement the narrow local adapter

**Files:** Create `tools/local_secret_scan.py`; modify only the local secret-scan entry in `.pre-commit-config.yaml`; extend the new regression file and the relevant entry-contract assertions in `tests/unit/guardrails/test_ci_parity.py`.

**Proposed entry:**

```yaml
entry: python -X utf8 tools/local_secret_scan.py --baseline .secrets.baseline src
```

**Interface:** `main(argv: list[str] | None = None) -> int`. Recognize the baseline path and candidate filenames. Delegate the original arguments unchanged to `detect_secrets.pre_commit_hook.main` after validation, preserving its normal status codes, including baseline-maintenance status 3. Import the pinned scanner only after validation succeeds. Reject malformed arguments or validation failures with status 2.

The existing literal `src` argument is a compatibility directory marker, not recursive scanning. Validate it as the expected existing directory and pass it through as before; never enumerate it. All other candidate arguments must resolve to readable files for strict validation. Reject unexpected directory arguments. Preserve pre-commit's selection; do not invent additional file discovery.

Algorithm for the executor:

```text
parse the supported baseline/filename arguments without changing their order
require interpreter UTF-8 mode; otherwise fail with an actionable invocation error
validate the baseline and selected files using strict UTF-8 text reads
  consume the whole file in chunks, not just a prefix
  on decode or I/O failure: report path and reason, return 2 before delegation
delegate the original argv to the pinned detect-secrets pre-commit entry point
return its result unchanged
```

- [ ] Implement that adapter without editing the scanner dependency or adding a new package.
- [ ] Make the failing UTF-8 regression pass through the real configured hook with parent `PYTHONUTF8=0`; the command-line flag must control the scanner process.
- [ ] Verify invalid input at the start and near the end of a file rejects before scanner delegation or baseline changes. Report path/offset/reason, never file contents.
- [ ] Verify unreadable/missing selected files reject; use a controlled I/O-error unit test where platform permissions cannot reliably create the condition.
- [ ] Verify clean ASCII, Unicode, BOM-bearing UTF-8 and spaced/non-ASCII paths pass when finding-free; artificial canaries reject regardless of the parent locale.
- [ ] Verify only selected files are scanned: an unstaged/unselected fixture is not pulled into the hook. Preserve pre-commit's normal handling of staged content and deleted/binary files; do not claim the adapter scans files pre-commit omits.
- [ ] Use disposable baseline copies to test unchanged pass/finding status and the existing maintenance-status path. Check that adapter validation errors leave the baseline byte-identical.
- [ ] Update only exact entry expectations genuinely superseded by this repair. Keep baseline mutants and production CI regression controls intact; do not broadly loosen substring or contract assertions.

**Deliverable:** A local adapter with demonstrated detection and rejection behavior. A one-line `-X utf8` change alone does not satisfy this task.

## Task 3: Governance, validation and reviewed local delivery

**Files:** Promote this complete plan at `docs/superpowers/plans/2026-09-06-local-hook-utf8-repair.md` together with the live-plan registry row supplied in `outputs/local-hook-utf8-execution-commission.md`. Update current prose in `README.md`, `docs/superpowers/plans/hardening-runtime-quality-masterplan.md`, `docs/superpowers/plans/hardening-ci-guardrail-truthfulness-implementation.md`, and the owning `P11-FEAT-ACP-RUNTIME-HARDENING` row of `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`. Do not change frozen predecessor records. At authorized pickup, update the execution-grant prerequisite from `no` to `yes` with the actual operator receipt; update other prerequisites only when supported by evidence.

- [ ] State: selected local text is decoded as UTF-8 and unreadable text rejects; CI remains production-only; historical frozen-document findings are still unresolved policy/custody items. Mark delivery pending until it is actually verified. Do not declare scanner completeness or FU-6 closure.
- [ ] Run `python -m pytest tests/unit/guardrails/test_local_secret_scan_encoding.py tests/unit/guardrails/test_ci_parity.py tests/unit/tools/test_verify_masterplan_impact.py -q` in the locked environment. Run applicable documentation hygiene tests identified from current repository configuration as well.
- [ ] Run the new real-hook regressions on Windows with the CP1252 control and on Linux/WSL. Retain exact environment and result identities. No platform-success substitution if either cannot run.
- [ ] Run Ruff and normal hook preflights on the complete changed-file set; obtain Codex's candidate concurrence before invoking the normal full commit hook for a coherent local delivery. Preserve JUnit through process-local forward-slash absolute `--junitxml` options, leaving coverage and temporary-root behavior unchanged.
- [ ] If a changed file exposes a finding, identify its exact site and seek a specific disposition. Do not edit frozen files or widen the baseline to make the commit pass. A full-inventory diagnostic returning the known frozen findings is expected disclosure, not a reason to bypass the staged-file hook.
- [ ] Return head/tree/parent, exact path list, hook log and exit, JUnit identities/skips, coverage copied from its database if quoting a percentage, Windows/Linux proofs, and a hashed evidence manifest. Recheck the 34 baseline identities and frozen/report hashes against main.
- [ ] Prepare the PR body with exactly one declaration: `Master-plan impact: updated — HARDENING-TRACK-CI-GUARDRAILS`. Run the real verifier against the actual changed-file set. Return for Codex's review before publication.

**Acceptance:** Valid selected UTF-8 containing a canary cannot disappear because of CP1252; invalid/unreadable selected text cannot silently pass; clean selected UTF-8 succeeds; selection, baseline policy, CI venue and full local coverage gate remain intact. Known findings remain visible and separately governed.

## Planning self-review

Root cause, invalid-input behavior, locale inheritance, selection, baseline side effects, immutable custody, platform evidence and governance each have an explicit task above. The plan changes no application behavior and prescribes no broad secret-scan policy replacement. New finding disposition is intentionally separate from proving the decoding repair. No new time ceiling or claim of completed repair is implied.
