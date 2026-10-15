# Closed state ID port source and checkpoint evidence

This dated receipt records the bounded work under [#357](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/357), parent [#317](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/317), related [#302](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/302). The issue owns live status and next gates. It does not close either parent or establish successful-session unloading, broader memory bounds, live services or performance.

## Source and approved boundaries

Main base: `9e7626df3eff9e9a643650dd7af406ba723c120d`. At this source the only production store `remove` callers are the three `session/new` error branches in `src/optimus/acp/spec.py` (820, 844, 849); each operates on an attached empty MCP state. The selected change belongs only in `InMemoryAcpSpecSessionStore.remove` (335-338), not the adapter or other lifecycle owners. Successful sessions remain retained by the existing store and are outside this fix.

The source sandbox class is the annotated local-only tag `sandbox-mcp-closed-state-ids` -> `e5b29d76b77e62ef79a758287f459ec67e0011e0`, tree `269dc7ece91197a384650b09ec3de9ce1ffe6a19`. The tag names review MANIFEST `0fa79c0019ba9c6ab6bbe265271c13c7ffb8d74734b826bf647b3265cb88e6c0` and final-evidence MANIFEST `c023641067310dcaf0222e1dd5f5b3aa8af17a3c0f8b4d2798473b538247fa28`; these are historical provenance, not current-main test evidence. At preparation the tag/commit/source were inspected; the two raw manifest contents were not yet revalidated. Their existence is not a project runtime/test dependency.

Sandbox pickup snapshot: clean `experiment/cross-cutting-sandbox`, HEAD `e521264e9f0fae08a8b1e42887ce2e0ae8bd1c2c`, describe `sandbox-main7-ported-register-docs-20261014-0-ge521264`, post-tag range empty. That latest tag is documentation custody, not new code acceptance. Both selected paths overlap day-0 `63b5d8f..c69fd48`; this port re-derives tests from main and brings no day-0/held-MCP import, `attach`, `session/load`, SDK or catalog code. Store mutation methods remain synchronous; server request tasks are gathered before adapter teardown (`server.py:854-855`). No cross-thread/reentrant lifecycle guarantee is introduced.

The human directly approved exact v2 (`e45a9f9038662af0c212510e7335847cd41d41658f13bb0a7ff0439e47fdab44`), isolated implementation/local verification and Claude as sole independent reviewer, dropping Fable, in the Codex chat on 2026-10-15 with the message ending `[Vibhanshu] Approved by me.` The [issue comment](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/357#issuecomment-6188807103) corroborates the cadence decision but is not authority by itself. The complete [v3 execution successor](../plans/archive/2026-10-15-closed-state-ids-port_v3.md) records that approved change; its source SHA-256 is `28637a0c5d4f84c32e9c9c2d50830866a9cc990cf3254126e41cfc8c7ca4dc24`. V1/v2 were never canonical adopted predecessors and remain unchanged approval provenance. Scheduling identity is Plan 11.31 for existing issue #357; no new issue or backlog work entry is created. Commits, issue metadata changes, push, PR, merge, services and cleanup remain separately gated.

## Checkpoint 1 test-only regression evidence, 2026-10-15

Two independent main-based worktrees/environments separate a clean full-baseline source from the dirty test-only candidate. No timing claim follows concurrent host activity. Frozen Windows versions: CPython 3.14.4, pytest 9.1.1, coverage 7.14.3; uv 0.11.29. Candidate module origins resolve to its own checkout/environment. Baseline and candidate start at the same main base.

At this dated snapshot only `tests/unit/acp/test_spec_protocol.py` had changed in the candidate (171 added lines, four parameterized test groups). Production `spec.py` Git blob remained `24ec5233c846326c63cf5e64521b2c072da2507b`, identical to base. Test-file SHA-256: `5db0631d915baeea520285685e0e1a71e58fe269c8639b74708c4129d5442319`. Before/after binary-diff receipts both SHA-256 `8b1cbaf4edd2707e29d5f685d1c65beba42ab37db521ad75c7402017800b1a32`, proving unchanged source during this provisional development run.

Command, retaining normal repository selection/root conftest:

```bash
uv run --no-sync pytest --no-cov tests/unit/acp/test_spec_protocol.py -k 'session_store or session_new or close_all or session_load_still_method_not_found' -v
```

Run `20261015T093344-53452-e1e5b7`: **13 failed, 9 passed, 34 deselected; exit 1**. All 13 failures are stale-marker assertions, not fixture/import/API failures: normal/raising remove (5), synthetic defensive branches (2), ordering (2), and current `session/new` failure branches (4). Two unseeded defensive controls and seven existing compatibility controls passed. `KeyboardInterrupt`/`SystemExit` were caught inside sync tests; pytest did not abort. The resolver parameter counts the directly closed returned state and removed attached empty state separately; configuration normalization's never-returned object is excluded.

Typed context: active/default_selection, native valid, full protection/full audit depth, COMPLETE, selected 22, recording_errors 0, collection_errors 0. Parent UNKNOWN is retained. This is attributable expected-red development evidence; it is not a green acceptance run or coverage gate. Configuration SHA-256 `86963ae6e0d88666e3edc3ae0da4ffbf408d885c4e59ba9aa08be5d295f0e3ce`; lock SHA-256 `b0aa71b62b238973d81fb4ecfc188d9ac2053a704225250cef698513f926d00b`.

Raw pytest log SHA-256 `7bbf729da9dc537889577d56791ba7c596c466fd03c70aa62511e3f107081d17`; preserved context-file manifest SHA-256 `cdcd8d60220b13b6ce0c60b00a90be7f18ee16ad1f1d0e6d7c2eb4046bc4eb67`. Raw local packets are archival provenance under ignored `tmp/closed-state-ids/`; no project command/import depends on them. `uv run --no-sync ruff check .` and `git diff --check` passed on this test-only snapshot.

## Full-gate qualification at preparation

The clean baseline canonical full Windows gate was still running when this receipt was prepared. No baseline PASS, validity, safety comparison, CP1 acceptance, production GREEN, local-delivery or merge claim is made here. Subsequent source-bound results require their own dated evidence below.

The first wrapper source receipt used unquoted `HEAD^{tree}`, which PowerShell parsed incorrectly. The error is preserved; a separately labelled corrected read used quoted `HEAD^{tree}` while source stayed unchanged. The canonical gate records its own source identities. No gate retry or source mutation followed that wrapper mistake.

## Dated documentation adoption checks, 2026-10-15

The four approved documentation paths were staged without committing so the index-based documentation checks saw the complete local adoption. The test-only Python change remained unstaged; production was unchanged.

First docs run 20261015T093954-31024-1873aa: 1 failed, 120 passed, exit 1, active/default_selection/native valid/full protection/full audit depth/COMPLETE; parent UNKNOWN retained. The new README row used an inline external issue link; the existing index test resolves every inline target as a local document, producing the nonexistent target https:/github.com/vibhanshu-agarwal/optimus-cost-agent/issues/357. Root cause was confirmed in test_docs_index.py without changing that test or its parser. Failed log SHA-256: b729051899bc3c3f449d1132294d7e56813acaca94ef59e440b15b0212a9590b; complete failed context is preserved.

The row was corrected to plain issue text, preserving the issue link in the canonical plan and registry. Corrected docs run 20261015T094153-51156-a0fc6e: 121 passed, exit 0, active/default_selection/native valid/full protection/full audit depth/COMPLETE; parent UNKNOWN retained. Corrected log SHA-256: b7a35f3d2649ec2b388f2c4cfafba91f83c47bf3262eef28cf2a2a39f1a304b7; its complete context is preserved separately. This is a diagnosed in-scope documentation correction, not a repeated unchanged gate or production acceptance.
## Source provenance revalidation, 2026-10-15

The earlier raw-manifest unknown is resolved. Both named retained manifest files exactly match the SHA-256 identities in the annotated tag. Read-only verification parsed every manifest row, rejected paths outside its manifest directory, checked existence and recomputed every referenced file hash: review manifest 2,182/2,182 valid; final sealed manifest 189/189 valid; zero missing files, mismatches or invalid rows.

The source tag's three Git-blob contents match the final sealed file bindings exactly, without line-ending conversion: spec.py 2e844e516272c2525cb0884269aa654f7aa03324ff03e527dfd41d56b4719922; test_spec_protocol.py 111d3d59633b02c402bee3281e7052b1748ec8eef45a27d0e7a12f5e878f4bf9; class record 96f8260f6605a58a277328e46eb199bc81f5584cd34ab71f76dadf680529a8e2. The retained final tag-verification review records piece 1 accepted and closed, with the broader MCP/Redis lifecycle class still open. Historical final coverage was 4,408 passed, 32 skipped, 127 deselected, 86.41%; it is not a current-main pass. The sandbox attach-discard mutant and test remain outside the main port because main has no attach API.

Only sanitized provenance identities/results are carried here. Retained private raw folders are archival, not project operating inputs. This evidence closes source availability/identity for checkpoint 1; it does not substitute for fresh main baseline, regression, coverage or independent review gates. The 121-pass docs run above preceded this results-only receipt append; it is not relabelled as a run of later documentation bytes.


## CP1 red/control node mapping

Extracted from the preserved complete context for run 20261015T093344-53452-e1e5b7, not inferred from test names. All 13 failures are the retained-ID assertions described above; all 9 controls pass. Production remained unchanged.

| Node ID | Actual call outcome |
|---|---|
| `tests/unit/acp/test_spec_protocol.py::test_session_new_absent_or_empty_mcp_servers_is_exact_noop` | passed |
| `tests/unit/acp/test_spec_protocol.py::test_session_new_malformed_mcp_servers_removes_provisional_session` | passed |
| `tests/unit/acp/test_spec_protocol.py::test_session_new_awaits_transport_permission_with_opaque_safe_fields` | passed |
| `tests/unit/acp/test_spec_protocol.py::test_session_new_attaches_lazy_resolver_without_opening_transport` | passed |
| `tests/unit/acp/test_spec_protocol.py::test_session_new_timeout_and_reject_keep_usable_session_unavailable` | passed |
| `tests/unit/acp/test_spec_protocol.py::test_session_load_still_method_not_found` | passed |
| `tests/unit/acp/test_spec_protocol.py::test_session_store_remove_releases_closed_state_id[normal]` | failed |
| `tests/unit/acp/test_spec_protocol.py::test_session_store_remove_releases_closed_state_id[ordinary-error]` | failed |
| `tests/unit/acp/test_spec_protocol.py::test_session_store_remove_releases_closed_state_id[cancelled]` | failed |
| `tests/unit/acp/test_spec_protocol.py::test_session_store_remove_releases_closed_state_id[keyboard-interrupt]` | failed |
| `tests/unit/acp/test_spec_protocol.py::test_session_store_remove_releases_closed_state_id[system-exit]` | failed |
| `tests/unit/acp/test_spec_protocol.py::test_session_store_remove_without_state_or_session[no-marker-no-state]` | passed |
| `tests/unit/acp/test_spec_protocol.py::test_session_store_remove_without_state_or_session[no-marker-missing-session]` | passed |
| `tests/unit/acp/test_spec_protocol.py::test_session_store_remove_without_state_or_session[synthetic-stale-marker-no-state]` | failed |
| `tests/unit/acp/test_spec_protocol.py::test_session_store_remove_without_state_or_session[synthetic-stale-marker-missing-session]` | failed |
| `tests/unit/acp/test_spec_protocol.py::test_session_store_close_ordering_preserves_live_markers[close-all-first]` | failed |
| `tests/unit/acp/test_spec_protocol.py::test_session_store_close_ordering_preserves_live_markers[remove-first]` | failed |
| `tests/unit/acp/test_spec_protocol.py::test_session_new_failure_releases_closed_state_id[runtime-missing]` | failed |
| `tests/unit/acp/test_spec_protocol.py::test_session_new_failure_releases_closed_state_id[configuration]` | failed |
| `tests/unit/acp/test_spec_protocol.py::test_session_new_failure_releases_closed_state_id[disposition]` | failed |
| `tests/unit/acp/test_spec_protocol.py::test_session_new_failure_releases_closed_state_id[resolver]` | failed |
| `tests/unit/acp/test_spec_protocol.py::test_close_all_closes_session_states_exactly_once` | passed |


## Dated failed full-baseline attempt, 2026-10-15

Canonical command ran once on unchanged clean main 9e7626df3eff9e9a643650dd7af406ba723c120d, tree 7ef586fd2538a805785c6fba61ee0b5bf58fb4af. Gate dataset metadata records worktree_dirty False both before and after. The quoted source-after correction and a fresh empty Git status agree. Initial wrapper before/after tree receipts used the bad PowerShell spelling already disclosed; they are retained as failed wrapper receipts, not source proof.

Run 20261015T092620-17528-13250a: **7 failed, 7,724 passed, 40 skipped, 111 deselected, 36 setup errors, one warning; full-gate exit 1**. Selected 7,807; native valid, full protection/full audit depth, COMPLETE, recording_errors 0, collection_errors 0; parent UNKNOWN remains qualified. No test selection or audit-depth override was used, and no retry occurred.

Required measured coverage floors passed: Optimus product group 89.4584%, Context Engine 95.9243%, model-policy package 96.9880%. Aggregate 85.0515% is informational PASS; Evidence Handoff 68.4451% is informational BELOW. Coverage floors do not turn the failed suite into acceptance. Coverage JSON SHA-256: 7ad5d57462f7602bd3ea321bc87d90b90dc94c166771f9a0d0d6f4e71e9e2c46.

The normal producer validity command ran against that one exported dataset/report; it ran no second test suite. It bound the full session (99 records considered), returned exit 3, reported exit_status_differs and stated full-run validity NOT established. No safety-comparison or checkpoint-PASS claim follows. Baseline log SHA-256 541edc132c9926b8a1258fad33323b958eae8876e9997072f2d43af7fa8e48f2; validity log SHA-256 caad824becf2294848e385b16657208c6e802cdee131fa66ce714eff0d6fc85b; complete raw packet-manifest SHA-256 caddefe07ae5db49b6a5d61221ef914c837319508472f87975aa6a3b5bbdffc1. Raw packet/context files are retained separately under ignored tmp; sealed material is not rewritten.

Failed call nodes:

- `tests/unit/guardrails/test_ci_parity.py::test_production_secret_scan_rejects_nested_canary_and_restores_clean`
- `tests/unit/guardrails/test_ci_parity.py::test_production_secret_scan_rejects_empty_inventory[no_files]`
- `tests/unit/guardrails/test_ci_parity.py::test_production_secret_scan_rejects_empty_inventory[only_outside_src_text]`
- `tests/unit/guardrails/test_ci_parity.py::test_production_secret_scan_rejects_empty_inventory[only_binary_src]`
- `tests/unit/guardrails/test_ci_parity.py::test_run_timeout_terminates_descendant_processes`
- `tests/unit/guardrails/test_ci_parity.py::test_production_secret_scan_regression_controls`
- `tests/unit/tools/test_debug_trace_message_rule.py::test_fresh_process_resolves_then_scans_without_shell_path`

All 36 setup errors are in test_debug_trace_message_rule.py's provisioned ast-grep fixture. The diagnostics identify an unprovisioned/unhealthy repository-configured hook environment. The fresh-process test is the seventh call failure for the same health check. Five CI-parity scan failures show Bash resolving to the Windows WSL launcher and uv exiting 127 (command not found). The descendant timeout test did not raise its expected timeout assertion; it uses the same Bash resolver and is consistent with early wrong-shell termination, but corrected-environment confirmation has not run.

These are observed baseline/tool-environment failures, not failures of a production port: production remains untouched. The executor missed the Bash-resolution and hook-health preflights before the full attempt. A proposed bounded correction is invocation-only Git Bash PATH precedence plus provision of the existing pinned ast-grep hook in a project-local PRE_COMMIT_HOME, leaving shared cache, repository configuration and code untouched. Claude must review the failure packet/disposition before any new baseline attempt; no package-check, full-gate or hook bypass is proposed. Corrected narrow evidence cannot be relabelled as a green run of this failed full suite.

## Corrected-environment preflight and focused verification, 2026-10-15

Claude's independent CP1 packet review (issue comment 6189850192) found no blocking test/document findings and concurred with the diagnosed environment-only correction. CP1 remains open until a valid clean full baseline is reviewed. The original failed attempt above remains unchanged.

Invocation-only PATH precedence now resolves Bash to Git for Windows bin/bash.exe, GNU Bash 5.3.15(2)-release. The normally provisioned repository-pinned hook resolves healthy ast-grep 0.36.2 under a new isolated project-local PRE_COMMIT_HOME in the clean baseline lane's ignored tmp/closed-state-ids/pinned-precommit-cache. The normal optimus-ast-grep all-files hook passed. No global PATH, shared cache, tracked configuration, tests or production source were changed by setup. Hook-cache pre-full listing has 2,089 files, SHA-256 ef4a47ae5b9d2840c4d4503268728a01c63fadf8a3cba7a66b9d580cb13872e8. Health/version/preflight records and raw logs remain retained separately.

Corrected command: uv run --no-sync pytest --no-cov tests/unit/guardrails/test_ci_parity.py tests/unit/tools/test_debug_trace_message_rule.py. Run 20261015T102652-36804-0b7fa1: **94 passed, exit 0**, active/default_selection/native valid/full protection/COMPLETE, 586 processes, 282 phases, parent UNKNOWN. This includes the descendant-timeout case and all prior ast-grep setup errors. Clean HEAD 9e7626df3eff9e9a643650dd7af406ba723c120d and tree 7ef586fd2538a805785c6fba61ee0b5bf58fb4af match before/after. Focused log SHA-256 12005d8ba6a4882941540e7d453af0b3032273839ff152e115d29f745fa7c7d1; full context archived before the new suite. This is narrow verification, not full-gate acceptance.

A separately labelled clean full baseline is now running in cp1-baseline-corrected with the same invocation environment. Source remains pristine; no production edit or commit is permitted before CP1 evidence/review. The later candidate full gate must use the same corrected toolchain configuration for a like-for-like safety comparison.

Direct human instruction, 2026-10-15: Codex may seek Astra review when stuck on a complex issue, rather than repeatedly iterating. Trigger examples from the explicitly adopted screenshot are recurring failures, an unclear root cause after investigation, or several plausible design choices without a clear winner; Codex judges when escalation is warranted. This resolves the previously relayed outside-review instruction: authority now comes directly from this chat. Claude remains the independent checkpoint reviewer; Astra is conditional advisory escalation. Record any actual escalation on #357. No routine Astra step, automatic acceptance, or additional implementation/commit/publication authority is implied. Current baseline environment cause is diagnosed and affected cases pass, so no Astra escalation is presently needed. Preserve the exact reviewed v3; this later instruction is recorded in the ledger/receipt. No private-memory write was requested or performed.

## Corrected clean full baseline and producer validity, 2026-10-15

Separately labelled attempt cp1-baseline-corrected completed on pristine main 9e7626df3eff9e9a643650dd7af406ba723c120d, tree 7ef586fd2538a805785c6fba61ee0b5bf58fb4af. Before/after source receipts, clean Git status and gate dataset identities agree. The earlier failed attempt remains failed and preserved; this result is attributed only to the disclosed corrected invocation environment.

Run 20261015T103157-53676-1ca115: **7,767 passed, 40 skipped, 111 deselected, one warning; gate exit 0**, 7,807 selected, active/default_selection/native valid/full protection/full audit depth/COMPLETE, 14,989 processes, zero collection/recording errors. Parent remains UNKNOWN (access_denied), without an upgraded attribution claim. The recorded H5 audit uses its normal full 100 repeats. Full terminal context was copied before validation; the record was also read successfully through tools.testing.run_context_records.read_record.

Required coverage floors pass: Optimus group 89.3896%, Context Engine 95.9243%, model-policy package 96.9880%. Aggregate 84.9991% satisfies the repository aggregate >=80% requirement. Evidence Handoff remains informational BELOW at 68.4451%. Coverage JSON SHA-256 a590e7adb34f9a74c8cdacfac4056bd7154ca4cd777b000227f50c66e7f6c79d; raw coverage dataset was retained alongside it. Safety comparison with the later candidate remains UNRUN.

The normal producer validate command ran once against this exact coverage JSON and product report, without --run-record and without a new test suite. **Exit 0: full-run validity established**, binding full session 20261015T103157-53676-1ca115 after considering 199 records. This is the producer's default exactly-one eligible full-session binding, separate from the named-record reader check. Previous failed-session records remain present; the new gate window determines eligibility.

Exact invocation shell is C:/Program Files/Git/bin/bash.exe, GNU Bash 5.3.15(2)-release, with the same isolated pinned ast-grep 0.36.2 PRE_COMMIT_HOME used for the 94-test preflight. Claude's nonblocking consistency request 6190065917 is recorded: use this exact wrapper path again in the candidate's final preflight. Hook-cache before/after listings each contain 2,089 files, zero differing rows, identical SHA-256 ef4a47ae5b9d2840c4d4503268728a01c63fadf8a3cba7a66b9d580cb13872e8. No shared-cache repair or repository tool/config change occurred.

Full-gate log SHA-256 ae3689e294a56109ba1dc5261b0d0dc99cc3221cc37f50eccc143532e7e1f698; validity log SHA-256 bb92e0b75ce0a462feb367e2777cd46f21fb242791c98d69ef276d779a26977a. Complete raw packet manifest SHA-256 033c0c645225d672677441ff8a7319bfa0e07810324d7798773575abc41dbf21. Raw context, source/config identities, logs, exits, dataset and cache custody remain in the clean baseline lane's ignored tmp/closed-state-ids/cp1-baseline-corrected. These receipt-only additions follow the previously recorded docs pass and do not relabel those earlier tested bytes.

CP1 evidence is now ready for Claude's consolidated checkpoint assessment; it is not implementer acceptance. Production remains byte-identical to main and the reviewed regression test source is unchanged. No commit, push, PR, merge, metadata edit, cleanup or service action has occurred.

## CP1 independent acceptance and Task 2 provisional development checks

Claude's consolidated independent assessment at issue comment 6190899460 accepts CP1 with no blocking findings. It independently checks the clean baseline source, default-session record via the project reader, qualifiers, coverage, producer validity, cache custody and receipt hashes. This meets the planned prerequisite under the direct human implementation grant; it grants no commit or delivery authority.

Only InMemoryAcpSpecSessionStore.remove was changed: preserve the initial pop and existing conditional close, add try/finally, then discard the removed ID. No helper, adapter, signature or dependency changed. Current production file SHA-256 cfc2adbd0872f3cee2307efd1a03488bfbea1cd67c6220471855083261c336e9; regression file remains 5db0631d915baeea520285685e0e1a71e58fe269c8639b74708c4129d5442319.

Unchanged focused command now passes **22 tests, 34 deselected, exit 0**, run 20261015T112533-48592-2a4f4f. Active/default_selection/native valid/full protection/COMPLETE; parent UNKNOWN retained. This turns every previously attributable retained-ID red green with the nine controls still passing. Source diff SHA-256 d1c58527b87224749c7bd07b94ce3ae98c71393c3705edda61a12e73da1bf945 is identical before/after; full context archived under cp2-focused-green. Log SHA-256 5b3146afee13ea8d3e2e90dd8ba6dd9cf6c2ac2e3704e9307d68eab67b07c128. This is dirty-tree development evidence, not final committed-source acceptance. These receipt additions occur after that run and are not attributed to its tested diff.

Candidate's normally provisioned own pinned ast-grep hook passes all-files preflight and resolves healthy ast-grep 0.36.2. Invocation PATH resolves the same Git/bin/bash wrapper as the baseline; the Python resolver reports the case-insensitive Windows .EXE spelling. Candidate PRE_COMMIT_HOME is its own ignored pinned cache; the baseline cache and sealed packet are unchanged. No configuration, pinned dependency, global PATH or shared cache was changed. Normal hook deprecation warning is retained; no autoupdate or bypass was used.

Next authorized checks are the complete default ACP/MCP unit suites (including the complete protocol file), docs, Ruff and applicable normal hooks. The final clean committed full coverage/validity and safety-row comparison remain pending separate local-commit authority. Linux PR CI and publication/merge remain later separate gates.

## Local-commit authority and compatibility result, 2026-10-15

After the compatibility run began, the operator directly granted normal local commits for #357 with passing hooks and explicitly confirmed, This is my approval. Authority comes from those human messages in this Codex chat; Claude's issue record 6190924078 corroborates it only. The approval was first recorded in the ignored execution ledger so the measured tracked diff stayed unchanged. Push, PR, merge, issue metadata, services, cleanup and private-memory writes remain separately gated. The existing shared Git hook will be used without rewriting it or bypassing any check.

Claude's early read-only production-diff review 6190994834 reports no findings against the exact remove-only +5/-2 change and unchanged regression file. This is not CP2 acceptance.

Complete default ACP/MCP unit command uv run --no-sync pytest --no-cov tests/unit/acp tests/unit/mcp: **1,573 passed, 30 skipped, no deselections, one warning; exit 0**, run 20261015T112746-43524-c0da7e. All 1,603 selected cases include the complete protocol file. Active/default_selection/native valid/full protection/full audit depth/COMPLETE, zero recording/collection errors, withheld empty; parent UNKNOWN/access_denied remains qualified. Normal H5 budget is 100/100 repeats. The source and unchanged test hashes remain those above; diff SHA-256 90836c91972fb235c1def0975d617adc5f3174a7d4e01e1a32103a632e359569 matches before/after. Log SHA-256 68876070971745a859c4857aaf6310308afa57f6a4770d5a5ea9a707f560ecc2; archived packet manifest bc4dcda2bb65cf4ed6a5d33355f6b26947f532ffb266b904c41413e767f6b17e. The project reader verified the retained terminal record. This remains provisional dirty-tree development evidence.

These later receipt-only additions are disclosed separately from that tested diff. Docs/Ruff and normal commit-hook checks follow on the staged bounded candidate. After their success and the authorized normal local commit, the final clean committed full gate, producer validity and safety comparison must pass before Claude's consolidated CP2 assessment. No final-candidate or delivery acceptance is claimed here.

Dated precommit checks: docs run20261015T114719-51796-ef690e passed121/121exit0, active/default/nativevalid/fullprotection/COMPLETE with parentUNKNOWN. Source diff identical before/after; context retained separately. Fresh Ruff check passed. This paragraph follows those checks and is a disclosed receipt-only delta; the normal installed commit hook must check the staged candidate before any commit is created. Final committed full-gate/validity/safety comparison and CP2 independent assessment remain pending.

## Failed committed candidate and approved documentation successor, 2026-10-15

Normal local commit `7c3b5971b89860568b4076471141f28891428e66`, tree `4ee555ca1173d3baf9684f97231380f526480ef0`, parent `9e7626df3eff9e9a643650dd7af406ba723c120d`, contained only the six originally approved paths and passed all applicable installed hooks. The normal coverage-free commit profile `20261015T114907-37552-a3114f` passed selected 3,619 nodes/full audit and audit-current 77 nodes/quick audit; both records were native valid/full protection/COMPLETE with parent UNKNOWN. These are changed-index hook results, not full-default acceptance. No shared hook, configuration or tooling change occurred.

The subsequent canonical full Windows candidate at that clean committed HEAD, run `20261015T122708-53324-bc3c35`, **failed: 1 failed, 7,781 passed, 40 skipped, 111 deselected, one warning; gate exit 1**. Its only failure was `test_post_amendment_plans_declare_prerequisites_with_required_columns`. The project reader confirms full audit, active/default selection, native valid/full protection/COMPLETE, selected 7,822 and no collection/recording errors; parent UNKNOWN/access_denied remains qualified. Source HEAD/tree and clean status matched before and after. Product/test source stayed unchanged.

Root cause: the documentation guard discovers added plans using Git history through HEAD, so the earlier uncommitted docs checks and normal precommit profile did not select newly added v3. Once committed, v3's unclassified unsatisfied dispositions and its `not required` status violate the existing grammar. This is a plan-document defect; no exemption, guard weakening or production/test correction is proposed. Claude independently confirmed the cause and correction scope with no blockers at comment 6193086533, including direct checker v3 FAIL / proposed v4 PASS and archive-path discovery behavior.

Default producer validation ran once, bound that exact full session after considering 205 records, and returned **exit 3, exit_status_differs; full-run validity NOT established**. Safety comparison ran once and returned **exit 1, failed candidate incomparable**. Required product floors passed and aggregate measured 85.0987%; Evidence Handoff remained informational BELOW at 68.4451%. These percentages do not override the failed gate or establish safety acceptance. No unchanged suite/validation/comparison was retried.

The failed packet, context, raw dataset, source/config receipts, logs, exits and own-cache custody are retained unchanged. Full packet manifest SHA-256 `a0bae7ab1ab4a5c644fde1f77ebca4bd4ab8cca395e276d6d1c98de719dcc06b`; coverage JSON `aed1bdbc07619d4ad962ad4220ac16f004eea57b7a9a180a9046ecf582bec7df`. The 3,107 own hook-cache files match by normalized relative path plus content SHA before/after. The initial 6,208-row raw comparison used different slash spelling; both raw listings/diagnostic and normalized zero-difference proof are preserved. The sealed passing baseline and earlier failed baseline remain unchanged.

The human now directly approved, in this Codex implementing chat: “I'll approve v4 (7c97c247…), archiving v3 unchanged, and the seven-path scope in Codex's chat now.” This resolves operator decision 6193139217; Claude's earlier relay is corroboration only. The existing separate grant for normal local commits with passing hooks remains valid. Publication, issue metadata, services, cleanup and private-memory writes remain separately gated.

The complete [v4 successor](../plans/2026-10-15-closed-state-ids-port_v4.md) is adopted byte-for-byte at reviewed/approved SHA-256 `7c97c247c0773b1f2104fceb6b773b877308734c822ee6d1fe1b3906c7a8c06e`; its dated pending-review/approval header is preserved as approval-time history, not current authority. Subsequent approval is recorded here and in the execution ledger, addressing Claude's LOW wording note without an unreviewed header edit. Reviewed v3 is moved unchanged to the flat archive, still SHA-256 `28637a0c5d4f84c32e9c9c2d50830866a9cc990cf3254126e41cfc8c7ca4dc24`. The single issue-only registry pointer and docs index now select v4; this receipt's historical v3 link resolves to the archive. Seven cumulative paths include the unchanged archived predecessor. No production/test/tool/config source changed after the failed final.

The proposed v4 table already passed the existing checker directly as a draft; adopted-table verification, normal docs/hooks, a documentation-only local commit, actual committed-head docs check, and a fresh clean full candidate gate/default validity/safety comparison remain UNRUN at this dated correction. Claude CP2 remains required. Future evidence must bind its new source pin; no result is transferred from the failed committed pin.

## Approved clean-base sequencing exception, 2026-10-15

A read-only check of the existing normal-hook selection found that the prerequisite guard would still read invalid archived v3 while HEAD remained the failed candidate. A follow-up commit or amend could not pass unchanged normal hooks. No predictable failed suite was launched. Astra's conditional advisory consultation confirmed this ordering conflict and recommended a separate clean-base cumulative candidate; the actual consultation was reported in comment 6193235702. Claude independently confirmed the same technical sequence in 6193293508 and remains the sole checkpoint reviewer.

The operator directly approved in this implementing chat: “I'll approve the clean-base candidate rebuild (same seven-path v4 content, failed branch preserved) in Codex's chat now.” This resolves sequencing request 6193317457 and overrides only v4's documentation-only follow-up ordering. No complete v5, behavioral change or path-scope expansion is introduced. The cumulative seven-path candidate is rebuilt from the same verified current main `9e7626df3eff9e9a643650dd7af406ba723c120d` in a distinct isolated branch. The failed candidate branch at `7c3b5971b89860568b4076471141f28891428e66`, its approved working documentation and all evidence are preserved; no history is rewritten or cleaned.

The copied seven files were matched by SHA-256 before this dated receipt-only disposition. Production, regression, complete approved v4 and unchanged archived v3 retain the exact hashes above. The only later content delta is this operational receipt entry. The new lane uses its own frozen environment and pinned hook cache, normal installed hooks, direct v4 table verification, actual committed-head docs verification, and new clean-source full/default validity/safety comparison before Claude CP2. All publication and other separately gated actions remain closed. No prior passing or failed result is transferred to the new source pin.
