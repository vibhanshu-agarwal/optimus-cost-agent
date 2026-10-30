# Ruff first-tranche disposition and Windows verification

Date: 2026-10-30. Scope: the approved C4/PERF/RET/ASYNC tranche under [issue #324](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/324). This report records a bounded uncommitted implementation and its evidence; the issue remains the work register. No issue-closure or publication claim is made.

## Source and outcome

**Evidence boundary:** the 685-passed/6-skipped run measured the preserved pre-review source. Later changes are an AST-equivalent comment/format delta plus docs/index/manifest corrections; only the targeted docs and Ruff checks below measured that later state.

Base commit: `e346e7ac75f2f24ec4699ab2b46e5441507085cd`; tree: `b3c1df5499717ce8d17d7fcdc88358aca87fd7e7`. Branch: `agent/codex/ruff-first-tranche`. Windows 11, CPython 3.14.4, pytest 9.1.1, Ruff 0.15.20; this checkout has its own frozen development environment.

The exact baseline contained 27 diagnostics in 22 production files: C401=4, C420=2, PERF401=10, PERF403=1, RET503=1, RET504=5, ASYNC109=2, ASYNC240=2. The result is 22 semantics-preserving refactors and five contract-based exact-line exceptions, plus a src-only gate. No runtime defect is asserted from these warnings. The [source/evidence manifest](2026-10-30-ruff-first-tranche-manifest.yaml) gives every changed source/test/config byte hash and retained raw-artifact hashes.

Raw before/after JSON, command logs, source diff, caller/function inventory and copied run-context records are retained locally under `.superpowers/sdd/ruff-first-tranche/`. Those workstation artifacts are archival provenance, excluded from the deliverable patch, and are not runtime or acceptance prerequisites. The reproducible commands and individual dispositions are recorded here. Original 685-test source patch SHA-256: `e448221f02796bc9481930446ba2a4f30adc2f9884cf0626c646d6497e42122d`. The manifest separates those tested bytes from the subsequent comment/format/documentation review delta.

## Gate and contract decisions

[src/ruff.toml](../../../src/ruff.toml) extends the root `pyproject.toml` and adds C4/PERF/RET/ASYNC only beneath `src`. Existing CI and pre-commit already run `ruff check .`, which discovers the inherited gate; no new gate script or hook is needed. Root E/F/I/B selection, E501 ignore, target Python and other settings remain inherited. No SIM/TRY rule is enabled and no global tools/tests tranche is enabled.

Six stdin probes checked one regression from each selected family (C401, PERF401, RET504, ASYNC109), the same snippet beneath tools/tests, inherited E/F/B, inherited I001, ignored E501, and a corrected transformed comprehension. Production code was never regressed to run those probes.

Actual callers were inspected before edits. ProcessLifecycle.observe is called by the CLI lifecycle runner with a budget measured from cleanup start through self.remaining(timeout); expiry reports and returns an incomplete ShutdownObservation rather than raising. RedisRuntime.close_async is called by the server and startup cleanup, with public timeout= usage, a default SHUTDOWN_OBSERVATION_BUDGET_SECONDS, and a typed RedisRuntimeShutdownIncomplete outcome. Its single deadline covers both shared completion and physical teardown-thread exit. Existing expiry/cancellation/later-observation tests exercise retained cleanup/owner custody. An outer timeout scope alone does not supply these deadline and result contracts; parameter renaming would also break public callers. NdjsonSubprocessSession.wait_for is shared by response/request waits; its terminal helpers already have Never return annotations and always raise. It must never fabricate an optional result.

Both ASYNC240 exceptions deliberately retain synchronous path resolution. Each flagged resolve occurs before provisional ownership acquisition, so inserting an await there would not by itself split owned setup. The session store and MCP normalizer perform additional synchronous path work. Offloading only the two flagged calls would not bound serving-loop latency; moving the broader setup responsibility requires a worker, cancellation and shutdown contract. These exact-line exceptions retain current behavior without claiming that selective offloading is inherently unsafe. They do not prove filesystem atomicity against external actors, a filesystem latency bound, or a non-blocking serving loop. A slow filesystem remains a latency exposure. No new helper/owner is introduced for mechanical comprehensions.

## Original diagnostics, individually attributable

Rows use original baseline locations; line movement in the final tree is expected.

| ID | Rule | Baseline source location | Disposition and preserved contract |
|---|---|---|---|
| 01 | RET504 | `src/evidence_handoff/collector/bundles.py:172` | Return the same verified tuple directly after digest/security checks. |
| 02 | PERF401 | `src/evidence_handoff/collector/classification.py:108` | Extend per render in the same crash order; preserve repeated reasons and later ordered deduplication. |
| 03 | RET504 | `src/evidence_handoff/redaction/ingress.py:365` | Return the rebuilt SanitizedDraft after all residual/final scans and deterministic round trip. |
| 04 | PERF401 | `src/evidence_handoff_runtime/observability.py:58` | Build delivery views in store order, retaining shared integrity reference and per-row conversion order. |
| 05 | PERF401 | `src/evidence_handoff_runtime/service.py:170` | Return enrollment rows in insertion order with identical field reads and sorted scopes. |
| 06 | PERF403 | `src/evidence_handoff_runtime/service.py:512` | Update the populated client_fields mapping with ordered non-None fields; retain existing message/schema fields and identity-policy validation. |
| 07 | C401 | `src/optimus/acp/auto_hybrid.py:91` | Use a set comprehension for normalized string matches; preserve scoring, deduplication and clamps. |
| 08 | C401 | `src/optimus/acp/auto_hybrid.py:92` | Use a set comprehension for normalized string matches; preserve scoring, deduplication and clamps. |
| 09 | C401 | `src/optimus/acp/auto_hybrid.py:93` | Use a set comprehension for normalized string matches; preserve scoring, deduplication and clamps. |
| 10 | PERF401 | `src/optimus/acp/evidence_redaction_adapter.py:200` | Extend existing alias rules in user-root order; resolve each root once and keep stable longest-first sorting. |
| 11 | RET504 | `src/optimus/acp/launch_approval_cli.py:434` | Return the same trusted candidate after snapshot/workspace resolution; preserve one-key and fail-closed checks. |
| 12 | RET503 | `src/optimus/acp/ndjson_subprocess_session.py:113` | EXCEPTION: both terminal helpers already return Never and raise LiveSessionError; Ruff does not infer member-call termination. |
| 13 | PERF401 | `src/optimus/acp/operator_verify.py:492` | Return changed names in the same sorted union order, using identical before/after lookups. |
| 14 | ASYNC109 | `src/optimus/acp/process_lifecycle.py:203` | EXCEPTION: the public budget is anchored to cleanup start; expiry reports and returns an incomplete ShutdownObservation, with retained cleanup custody. |
| 15 | ASYNC240 | `src/optimus/acp/spec.py:1465` | EXCEPTION: the session store also performs synchronous path setup; a broader worker/cancellation/shutdown contract is needed to offload that responsibility. No latency bound is claimed. |
| 16 | PERF401 | `src/optimus/acp/spec.py:3259` | Keep only string text blocks in input order; preserve type checks, newline join and stripping. |
| 17 | PERF401 | `src/optimus/guardrails/mcp_trust.py:80` | Extend environment descriptors in sorted key order; preserve secret digest redaction and tool order. |
| 18 | ASYNC240 | `src/optimus/mcp/client_disposition.py:448` | EXCEPTION: the normalizer also performs synchronous path setup; a broader worker/cancellation/shutdown contract is needed to offload that responsibility. No latency bound is claimed. |
| 19 | ASYNC109 | `src/optimus/redis/runtime.py:457` | EXCEPTION: preserve the default budget, typed incomplete error and single deadline through shared completion and physical teardown exit, plus public timeout= callers. |
| 20 | C401 | `src/optimus/release/credentials.py:70` | Preserve mutable provider-hit set, allowed credential checks, config union and sorted output. |
| 21 | PERF401 | `src/optimus/skills/registry.py:168` | Extend ordered glob reasons after optional description reason; preserve glob/path short-circuit checks and duplicates. |
| 22 | RET504 | `src/optimus_gateway/server.py:257` | Construct and return the same ThreadingHTTPServer after handler/dependency/exporter binding. |
| 23 | RET504 | `src/optimus_gateway/tool_state.py:78` | Return the identifier inside the existing lock; bucket mutation and counter/string evaluation remain protected, lock releases before caller receives the result. |
| 24 | PERF401 | `src/optimus_model_policy/validation.py:256` | Extend missing-origin issues in original CHINA/NON_CHINA order, retaining prior issues and deterministic final sort. |
| 25 | C420 | `src/optimus_security/failure_facts.py:243` | Use dict.fromkeys with immutable unrecognized sentinel; preserve original ordered keys, independent mutable result and fail-closed raw-value removal. |
| 26 | C420 | `src/optimus_security/failure_facts.py:244` | Use dict.fromkeys with immutable unrecognized sentinel; preserve original ordered keys, independent mutable result and fail-closed raw-value removal. |
| 27 | PERF401 | `src/optimus_security/sanitization.py:459` | Extend match spans in original pattern/match order before the unchanged final sort; keep all protection and redaction boundaries. |

## Verification and limitations

All test commands retained repository addopts, default marker selection and root conftest, and used `--no-cov`. The snapshots recorded worktree, branch, HEAD/status, all 809 source/test/config/dependency hashes, platform/interpreter and exact command before and after. All 809 hashes matched before/after and the then-current pre-review source for the focused run, including the untracked src gate. Later review fixes are separately attributed below and in the manifest. Dirty-tree results are provisional development evidence, not exact-commit acceptance.

| Run or check | Result and attribution |
|---|---|
| Frozen environment, attempt 1 | FAILED, exit 1: sandbox cache persist access denied and Ruff-wheel DNS/download failure; retained setup-1.log. No tests ran before setup completed. |
| Frozen environment, attempt 2 | PASS, exit 0: identical `uv sync --frozen --extra dev` with native/network access; 92 packages installed, hardlink-to-copy warning retained. |
| `uv run --no-sync` lint attempt | FAILED before interpreter query completed: sandbox uv-cache persist access denied. Subsequent checks use this same checkout's `.venv/Scripts/python.exe`; no borrowed environment or resync. |
| Characterization startup, sandbox | FAILED, pytest exit 3: run-context registry os.replace denied before collection; no assertion failures or passing-test claim. |
| Characterization before production refactors | PASS: 32 tests; run `20261030T144708-19640-2c6c71`. Includes two newly parameterized sanitizer fallback cases (non-mapping result / sanitizer exception), which pass on original and refactored production code. These are characterization, not bug-fix red evidence. |
| Final focused verification | PASS: 685 passed, 6 skipped, 691 selected, 0 deselected; 50.65s; run `20261030T144943-41848-22e1a1`. |
| Normal Ruff, initial local helper | FAILED: local-only evidence helper E401/I001/E701/E702 formatting; no product finding. Fixed helper, retained initial JSON. |
| Final normal Ruff | PASS, exit 0: `.venv/Scripts/python.exe -m ruff check . --no-cache`. |
| Final tranche Ruff | PASS, exit 0, JSON `[]`: `.venv/Scripts/python.exe -m ruff check src --select C4,PERF,RET,ASYNC --no-cache --output-format json --output-file .superpowers/sdd/ruff-first-tranche/ruff-after-tranche.json`. Baseline used the same selection with `ruff-before-direct.json`, exit 1. |
| Gate probe, initial positive control | FAILED: the proposed clean identity set comprehension correctly triggered C416; this was a probe defect. Only the probe was corrected to transform strings. |
| Gate probes, corrected | PASS, six stdin probes; no source changes. |
| Whitespace | `git diff --check` passed; Git reported CRLF-to-LF normalization notices for two edited files. |

Both successful pytest runs were `mode=active`, `reason=default_selection`, `native.valid=true`, `protection=full`, `guard_mode=pytest_process_guard`, `completeness=COMPLETE`, with terminal exit 0, no schema violations and all nodes/phases/samples streams read back with state ok and zero errors. Focused record counts: nodes=691, phases=2070, samples=10, reconciled=true, truncated=false. Parent attribution remains `UNKNOWN`, reason `access_denied`; this is preserved, not upgraded to known ancestry. The sandbox initialization failure cannot establish native protection or a completed measurement.

Before characterization command:

```powershell
.venv/Scripts/python.exe -m pytest --no-cov tests/unit/security/test_failure_facts.py -q -ra
```

Final focused command (exact file selection):

```powershell
.venv/Scripts/python.exe -m pytest --no-cov -q -ra tests/unit/security/test_failure_facts.py tests/unit/security/test_sanitization.py tests/unit/security/test_sanitization_properties.py tests/unit/release/test_credentials.py tests/unit/acp/test_auto_hybrid.py tests/unit/acp/test_evidence_redaction_adapter.py tests/unit/acp/test_launch_approval_cli.py tests/unit/acp/test_ndjson_subprocess_session.py tests/unit/acp/test_ndjson_subprocess_backpressure.py tests/unit/acp/test_operator_verify_custody.py tests/unit/acp/test_process_lifecycle.py tests/unit/acp/test_spec_protocol.py tests/unit/mcp/test_client_disposition.py tests/unit/redis/test_runtime.py tests/unit/guardrails/test_mcp_trust.py tests/unit/skills/test_registry.py tests/unit/optimus_gateway/test_server.py tests/unit/optimus_gateway/test_tool_state.py tests/unit/model_policy/test_registry.py tests/unit/evidence/test_collector_classification.py tests/unit/evidence/test_collector_pipeline.py tests/unit/evidence/test_structured_ingress.py tests/unit/evidence_handoff/test_capabilities.py tests/unit/evidence_handoff/test_review_ruling.py tests/unit/evidence_handoff/test_transport.py
```

The selection covers the changed credential scan, classifier, alias construction, trusted launch resolution, NDJSON failure contracts, operator custody, process and Redis cleanup, ACP setup/text handling, MCP disposition, descriptor redaction, skill matching, Gateway construction/provenance, model-policy validation, collector pipeline/classification, structured ingress, delivery views and ledger transport/policy surface. No test syntax/fixture contract or security audit was weakened.

Exact skipped identities and reasons:

- `tests/unit/acp/test_launch_approval_cli.py::TestWorkspaceRuntimeRootBootstrap::test_bootstrap_creates_runtime_root_at_resolved_workspace_target`: Skipped: symlink creation unavailable.
- `tests/unit/acp/test_launch_approval_cli.py::TestWorkspaceRuntimeRootBootstrap::test_bootstrap_rejects_regular_file_runtime_root`: Skipped: symlink creation unavailable.
- `tests/unit/acp/test_launch_approval_cli.py::TestWorkspaceRuntimeRootBootstrap::test_bootstrap_rejects_final_symlink_without_writing_target`: Skipped: symlink creation unavailable.
- `tests/unit/acp/test_launch_approval_cli.py::TestConfigFilePermissionsWiredIntoResolution::test_group_readable_env_gateway_fails_closed`: Skipped: POSIX-only: permission bit checks.
- `tests/unit/acp/test_launch_approval_cli.py::TestConfigFilePermissionsWiredIntoResolution::test_owner_only_env_gateway_passes`: Skipped: POSIX-only: permission bit checks.
- `tests/unit/acp/test_launch_approval_cli.py::TestRunGatewayCommand::test_run_gateway_rejects_insecure_env_gateway_permissions`: Skipped: POSIX-only: permission bit checks.

Full suite and coverage are UNRUN by the approved focused scope; coverage floors and hooks are unchanged, and no coverage acceptance is claimed. WSL/Linux checks are UNRUN: runtime path/permission/subprocess behavior was not changed, no platform-shaped failure was introduced, and no alternate-OS parity is claimed. The native Windows symlink/POSIX skips remain limitations. Live/paid/external-service acceptance, main-push CI, and broader issue #324 completion are not established here. No commits, staging, push, publication, tags, merge, issue writes or cleanup were performed.

The sandbox register addendum was read-only verified at SHA-256 `2cbfe94babcb85d22d68ba882d88864a376d851bdee0913dcb1d3d3b793e0ebd`. Historical watchdog FAILED / cause UNKNOWN at 100 ms, K-scaling/RSS, whole-session TTL/durable resume and other lanes remain separately owned and unaltered.

## Consolidated review fixes and evidence delta

Claude CLI review session `f78f4d4e-946f-42fb-aa3a-a898b3677c69` identified the missing manifest index entry (F1), more precise timeout and path-offloading rationales (F2/F3), an optional RET503 alternative (F4), and comprehension readability (F5). The architect independently confirmed F1 and authorized one consolidated fix wave. F1 was reproduced before the index edit; F2/F3 were checked against the actual control flow.

| Finding | Disposition |
|---|---|
| F1 | Added the repository-visible manifest to docs/README.md. The exact index test first failed on that manifest path, then the complete index module passed. |
| F2 | Corrected comments and report: ProcessLifecycle measures from cleanup start and returns/reports incomplete observation; Redis retains its default budget, typed incomplete error and deadline through physical teardown exit. |
| F3 | Removed the claim that awaiting before acquisition necessarily splits owned setup. The exception rationale is the broader synchronous setup responsibility and worker/cancellation/shutdown contract needed to offload it. No bounded loop latency is claimed. |
| F4 | Retained the precise RET503 exception for Never-annotated raising helpers; the optional return-expression rewrite was unnecessary. |
| F5 | Expanded the text-block comprehension over multiple lines without changing its AST. |

The original report, manifest, source diff and all four changed production files were preserved byte-for-byte in the local `pre-review-fixes-v1` archive before fixes. The original 685-passed/6-skipped measurement remains bound to its original source hashes and original source patch `e448221f02796bc9481930446ba2a4f30adc2f9884cf0626c646d6497e42122d`. It was not rerun or relabelled as a measurement of later bytes. The final manifest retains the original tested hashes separately from current hashes. Four production files changed only comments or formatting; parsing each before/after file and comparing ast.dump(include_attributes=False) gave equality. This supports the claimed non-behavioral delta without constituting a new runtime test of later bytes.

| Targeted check | Exact result |
|---|---|
| Docs index red | `.venv/Scripts/python.exe -m pytest --no-cov tests/unit/docs/test_docs_index.py::test_index_lists_every_current_document -q -ra`; 1 failed, exit 1, missing only the new manifest; run `20261030T150052-28568-66fb6b`. |
| Docs index green | `.venv/Scripts/python.exe -m pytest --no-cov tests/unit/docs/test_docs_index.py -q -ra`; 7 passed, 0 skipped/deselected, exit 0; run `20261030T150144-10040-4d1073`. |
| Review-fix normal Ruff | `.venv/Scripts/python.exe -m ruff check . --no-cache`; pass, exit 0. |
| Review-fix tranche Ruff | `.venv/Scripts/python.exe -m ruff check src --select C4,PERF,RET,ASYNC --no-cache --output-format json --output-file .superpowers/sdd/ruff-first-tranche/ruff-after-review-fix.json`; pass, exit 0, JSON `[]`. |
| Whitespace | `git diff --check`; pass. |

Both red/green docs sessions retained normal addopts/conftest and had active/default_selection, native valid, full protection, COMPLETE records, schema-valid JSON and zero stream-read errors; parent attribution remains UNKNOWN/access_denied. The complete seven-case index module covers index completeness, stale/missing/archived links, archive folders and local-only checkpoint-log exclusions. Other docs modules govern plan relocation, plan/open-work hygiene or hosted work-status pages; this fix changes none of those contracts, so no broader docs rerun is required. Report/manifest metadata updates following the index run do not change the document inventory or index links it checked. No behavior, test selection, test fixture, audit guard, coverage floor or hook changed in the fix wave.

The architect's GitHub-connector recheck still reported main at `e346e7ac75f2f24ec4699ab2b46e5441507085cd` and main-push run `41072576397` in progress at coverage. That is not a CI pass and was not rerun here. This statement is architect-provided current evidence; the implementer made no GitHub write or independent remote-status claim.

## Final technical review and dated handoff observations

On 2026-10-30 the scoped Claude CLI re-review returned **SPEC PASS / QUALITY PASS, nothing remains to fix**. Reviews 2 and 3 used session `f78f4d4e-946f-42fb-aa3a-a898b3677c69`; F1/F2/F3/F5 were addressed; declining the optional F4 rewrite and retaining the precise exception was accepted. This is technical review acceptance, not authority to stage, commit, publish, merge or close the issue. No GitHub review publication was authorized or performed.

The initial sandboxed Claude attempt, session `4bb27c7a-d075-4d45-bbd5-a2fe7d1142c0`, failed with ENOTFOUND and supplied no review verdict. Its earlier stalled-wait/UNKNOWN disposition remains retained alongside the later error output. Automatic approval review blocked the network retry on disclosure grounds; the user then explicitly authorized Claude API review. The authorized named-model review and scoped re-review subsequently completed. Failed attempts and the approval boundary are preserved rather than presented as successful reviews.

The architect's later GitHub `fetch_workflow_run_jobs` observation superseded the earlier in-progress observation: run `41072576397` completed successfully, including pytest-coverage and coverage-validity steps. This is **base-main CI** for `e346e7ac75f2f24ec4699ab2b46e5441507085cd`, not CI for this uncommitted Ruff tranche. The earlier in-progress evidence remains historical and is not relabelled.

The sandbox register changed externally on 2026-10-30 (architect-recorded modification time 20:31:29 Asia/Calcutta). Its final observed SHA-256 is `9c0f5a8f08e12158a822b2ac29950a0b356a8085f18a0334050fd10979c7452d`, also verified by a final read-only hash here. The architect established that only the CI-status clause changed: replacing that clause in the observed copy reproduces the intake SHA-256 `2cbfe94babcb85d22d68ba882d88864a376d851bdee0913dcb1d3d3b793e0ebd`. The locally preserved `sandbox-register-final-observed.md` is the observed final copy; `sandbox-register-intake-hash-reconstructed.md` is explicitly a reconstructed intake-hash copy, not an original intake capture. No original sandbox file was mutated by this task. The earlier unchanged-hash observation remains valid for its earlier observation time.

This final handoff changes documentation/evidence metadata only. No source, test or gate byte changed, and no tests were rerun. Final report/README hashes are regenerated last in the manifest, which keeps original 685-test hashes separate from current reviewed hashes and contains no self-referential manifest hash. Full-suite, coverage and alternate-OS tranche checks remain UNRUN as scoped; synchronous path latency and UNKNOWN parent attribution remain disclosed. The historical watchdog remains FAILED / cause UNKNOWN at 100 ms.

## Publication preparation: failed normal hooks and format correction

The operator subsequently authorized normal-hook commit, named-branch push and PR preparation, with merge separate. The first normal commit attempt failed (exit 1); no commit or push was created. All hooks stayed enabled. Hygiene, Ruff, Bandit, ast-grep, config-trust and mypy passed; the YAML hook had no selected YAML files at that point. The secret scan failed on nonsecret hexadecimal evidence digests in the JSON manifest. The configured commit test profile also failed in its separate quick audit-current subrun.

The profile selected 10,848 nodes and deselected 67 through its existing broad fallback: the new src/ruff.toml and evidence-manifest JSON lacked narrow dependency mappings. Its selected subrun `20261030T153237-3148-91ddf4` passed with **10,692 passed / 50 skipped**, 10,742 selected and zero deselections. Its audit-current subrun `20261030T161402-53144-7cdab9` had **4 failed / 102 passed**, with quick depth explicitly reduced (H5 repeats 1/100; eight earlier current measurements reused and named in its record). Both records were active/default_selection, native valid/full and COMPLETE, with UNKNOWN/access_denied parent attribution. The profile verdict is FAILED, not full default-suite or coverage acceptance; its WSL notice remains for the next checkpoint. Complete first-attempt output, selection, manifest, attributed records and hashes were retained before edits.

All four audit failures are in tests/unit/acp/test_plan1126_delivery_contract.py: test_delivery_contract_model_1000_seed_schedule, test_h4_behavioral_mutations_change_or_invalidate_primary_observation, test_h4_execution_emits_only_citations_for_behaviors_it_runs and test_h4_literal_scenarios_are_coherent_primary_transitions. Each raises ValueError for production transition authority drift in src/optimus/acp/lifecycle.py at delivery_characterization.py:600. That file is outside the Ruff delta and is byte-identical to HEAD. The canonical helper, imported lifecycle module and interpreter all resolve to this checkout. The first rejected symbol is TurnControl.__init__: historical and current ASTs differ through existing settlement initialization, introduced by a2c1330863c97cb14045f516c2a275d48b378306. Both source versions are LF; this is neither CRLF drift nor a foreign import root. Seven selected lifecycle authority symbols differ from the historical pin.

The architect found these same failures already tracked on main in [open issue #447](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/447); no duplicate issue or repair was created. Base-main CI success does not discharge these cases: the read-only connector extract for run 41072576397/job 124120198545 explicitly reports **P11.26-UNRUN-BINDING: 37 tests skipped as UNRUN**, including all four failing nodes. The historical fac32284888850bacde93815265cbabe3afd4663 object is available locally, so these cases execute here; CI skipped them when the object was unavailable. This explains the different execution coverage, not an OS-specific pass. No historical pin, Git object, skip binding, audit or guard was altered. Second commit/push remains on hold pending the separately owned issue #447 gate; no bypass or retry-to-green was used.

Independently, the manifest was converted from JSON to YAML so standard per-line scanner annotations can identify reviewed evidence digests. Original JSON bytes are preserved locally at their original SHA-256 103bbffdb100c31af270f3815a84af626e148ce6c1946a9db5c9213f80edac37. Parsed mapping/value equality was proved before metadata refresh; every detected value was checked as a known source/evidence or Git digest. Only actual digest findings receive inline pragmas, following existing repository YAML conventions; the pinned YAML transformer and scanner honor them. The secret baseline, scanner settings and source/test/gate bytes are unchanged. Subsequent parsed deltas are explicitly limited to two current document-hash updates, the two-path publication_normalization mapping and enumerated new archival evidence hashes. Original source_files and original_tested_source_files remain unchanged. The normalization metadata records measured working hashes and LF-normalized staged hashes for observability.py and service.py without relabelling either measurement.

Format-correction validation: the configured `.venv/Scripts/python.exe -X utf8 tools/local_secret_scan.py --baseline .secrets.baseline src <all 27 intended staged deliverables>` passed (exit 0). `.venv/Scripts/python.exe -m pytest --no-cov tests/unit/docs/test_docs_index.py -q -ra` passed all seven cases, run `20261030T162706-47128-3a167d`, active/default_selection, native valid/full, COMPLETE, parent UNKNOWN/access_denied. Normal root Ruff and the existing PR masterplan-impact declaration validator passed. Parsed-data checks retain all 24 source/test/gate and original-tested mappings and explicitly enumerate only the approved metadata deltas. These narrow checks do not change the failed normal-hook verdict or discharge issue #447. No second commit attempt, push or PR occurred; the corrected 27 deliverables remain staged for handoff.

## Combined integration checkpoint (#324 and #447)

The operator subsequently authorized resolving #447, integrating its independently accepted repair and resuming the publication path after one combined review/gate. This checkpoint is on latest-main base `18093a78961172ec3478b6e40dbc5fc2c64fd6f8`. The repair was reviewed on `76848d0dd02cb5db569099418e7a5990ccc1d697`; the additional main drift archives Plans 12.5/12.6 and changes their index/backlog rows only. Incoming ADR-031 and archive state are preserved together with the two Ruff index rows and the repair report row. Main also carries the earlier Plan 12.6 runtime dependency `pathspec==1.1.1`, lock and classification changes; this checkout's own `uv sync --frozen --extra dev` completed before verification, retaining its hardlink-to-copy warning. No environment was borrowed.

The exact accepted five-path repair patch has SHA-256 `46e22794dd693eb79f5b265e35d4ef500c47abee534da0be5d94a73a5c7a0cde`. Its four non-README files match the accepted hashes byte-for-byte; README is the deliberate latest-main/Ruff/repair union. The [H4 repair report](2026-10-30-h4-historical-replay-test-contract-repair.md), SHA-256 `2ceccaf0f182c269d8199a2f52134366f7c2de0b81f09a0a8864262a898b48fd`, defines the changed test obligations and limitations. Four obsolete historical-execution tests now validate sealed replay; the behavioral-mutation execution obligation is explicitly retired, not replaced by equivalent fresh runtime evidence. Current runtime suites retain ownership of runtime behavior. Production modules/helpers/pins, the 37-ID binding/conditional-skip semantics and scanner baseline are unchanged by that repair; only three node identities are renamed in the binding, with conservative explicit tiers retained. Three stale measured-slow entries were removed because the replacement nodes were never timed in those historical runs.

Repair measurements remain separately bound: its pre-review run had 61 passed; a later 23-case run had 22 passed / 1 failed, and the only subsequent Python delta added multiline mode to two exact reason-line regexes. The affected citation-node rerun passed once; the other 22 cases were not rerun or relabelled as testing later bytes. Those accepted focused results do not establish an integrated-tree product/full-suite or historical schedule-execution pass.

All 24 Ruff source/test/config working-byte hashes and original-tested maps remain exactly preserved, including the disclosed two CRLF-working/LF-staged pairs. The original 27-path stash was restored by immutable identity and retained, never popped/dropped. The original staged patch, working/staged copies, failed first-hook records and original JSON/YAML metadata snapshots remain preserved. The earlier failed gate and publication-hold observations above remain historical facts; the accepted repair is now integrated, with the combined review and one new normal gate still pending.

Integration attempts are retained. A README comparison guard initially refused an implicit text comparison; exact Git-blob equality and the accepted patch confirmed only the approved report-row addition before applying its union. Root Ruff first encountered copied forensic snapshot configurations (missing companion config, then snapshot-only I001 import-resolution findings). The architect authorized reversible relocation of that intact forensic directory outside the repository: all 69 file hashes matched before/after. No source fix, scanner exclusion, blanket ignore, configuration weakening or evidence deletion was used. The final root check has zero findings, including the new-main modules now beneath the src gate.

Narrow integrated checks: Ruff 0.15.20 `.venv/Scripts/python.exe -m ruff check . --no-cache --output-format json` passed; the configured pinned `.venv/Scripts/python.exe -X utf8 tools/local_secret_scan.py --baseline .secrets.baseline src <31 combined deliverables>` passed; staged diff-check passed. `.venv/Scripts/python.exe -m pytest --no-cov tests/unit/docs/test_docs_index.py -q -ra` passed all seven cases in run `20261030T175226-63092-eb8c24`, active/default_selection, valid/full native protection, COMPLETE, parent UNKNOWN/access_denied. That run checked the reconciled inventory before this metadata append; README inventory links and indexed filenames remained unchanged afterward. This report append added the H4 repair cross-link above, which was not part of that earlier docs-index measurement. The following manifest integration section records current document/dependency/repair bindings while leaving prior source and document snapshot maps intact. No manual broad test, integrated normal commit hook, commit, push, PR, main merge, issue write or cleanup has run at this checkpoint.
