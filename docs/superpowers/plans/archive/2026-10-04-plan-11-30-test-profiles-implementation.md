# Plan 11.30 — Test Profiles Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans, or superpowers:subagent-driven-development only when the operator selects that execution method. Complete the approved tasks in order; checkbox completion requires the stated verification to have run and passed. Codex is architect/reviewer, not implementer.

**Goal:** Reduce routine test turnaround while preserving default selection, current-code regression detection, platform obligations, full-suite coverage gates and attributable parallel-run evidence.

**Architecture:** A declarative node classification and dependency manifest feed a deterministic change selector and additive pytest profile plugin. A separate command runner manages checkpoint repeats and full-suite product coverage reports. xdist is restricted to reviewed core nodes and extends the merged Plan 11.28 controller/worker ownership contract before use.

**Tech stack:** Repository Python >=3.14, uv, pytest, pytest-asyncio, coverage.py, pytest-cov, Ruff, Git; proposed pytest-xdist dev dependency, version selected and locked during Task 0 after compatibility inspection.

**Spec:** The Requirements and Design Contract below are the complete draft specification. The operator requested this concrete draft; neither its proposed mechanisms nor execution are approved yet. Implementation agents must obtain written approval of the complete contract before execution. No commit, push, PR, merge, paid call or service activation is granted here.

## Authority, provenance and verified baseline

Draft requested in the continuation of `Plan 11.28 — review`, source chat `01a102cf-63b3-7582-9cc0-81366e05127c`, delegation dated 2026-10-04. Operator response in this chat: "Use current main". Main was clean at `980dad08cece20e109a5ee4eeecfcde04df2d71c`; authorized fetch and fast-forward produced clean main `a929aab2092876ab0d83ecc4e46896ae3a0935c0`. This is the drafting baseline, not a future implementation acceptance pin. Next available linear allocation is 11.30; 11.29 is already registered. No other lane's contract is changed.

Read inputs: AGENTS.md, CLAUDE.md, CONTRIBUTING.md, the live backlog, docs index and evidence policy; ADR-001 and decision-log rules; Test Strategy v1.7 (especially §8A), relevant HLD v2.18/LLD v2.41 passages, and Plan 11.28 design/code. The Test Strategy owns coverage authority over older summary cross-references.

Research provenance, not runtime/review dependencies:

| Input | SHA-256 / identity | Qualification |
|---|---|---|
| New-chat handoff, 2026-10-04 | `B1CAFA8914BC79B5762F87F4C5FC4C7691C750344DC38D140B700B62D8990DBD` | Digest checked during intake; operator requirements reproduced below |
| Claude test-profiles research, 2026-10-03 | Current pin `EEE91C285E8978977D29D096C6C5FDD6EB89D3549828C2F108CD7CC6D7123E25`; superseded handoff pin `756227DF3D3F9B19BF07E9C5AF8F529ED08FF395C365344DC78FB577477A8E95` | Operator disposition in this chat, 2026-10-04: "Use current report with new pin". Read current complete report; settled requirements also independently supplied by the delegation. Research remains non-acceptance evidence. |
| Fable review, 2026-10-03 | Verified `DC97731B7997C14D97ADC51847F3CB7D6E6B8DC3B647E44447011F220BC6E3DA` | SOUND WITH AMENDMENTS against its original research version; not proof of review of the changed report bytes. All twelve dispositions retained in tasks below. |
| Retained research data | `refrun-analysis.txt`, `tier-sizing.txt`, `win-vs-linux.txt`, `import-map.txt`; reference run `20261002T203101-45752-c1999b`, CI `36999076917` | Older `e9d6be0` import map; shared machine, failed Windows measurements and CI-UNRUN nodes; retained reference `run.json` directly checked: exit 1, completeness **INVALID**. Not current acceptance. |

The external handoff directory is archival provenance only. This complete draft carries the operative requirements; future tests and commands use repository paths. Task 0 files a sanitized repository research/evidence summary with verified retained-data hashes, original verdicts and limitations before those data support any acceptance claim.

Observed current code: root conftest starts run context before collection, records deselection and phases, then finishes and withdraws its own registry entry. `classify()` preserves ACTIVE for approved-marker file/`-k` subsets; collect-only is PASSIVE. `registry_entries()` reads at most 512 JSON entries and reports `partial` beyond that. On 2026-10-04 the real user Windows temp registry contained **727 JSON filenames**; sandbox temp registry was absent. This is a listing count, not a validated/live-entry count. No entry was removed. Current source has `optimus`, `optimus_gateway`, `optimus_security`, `evidence_handoff`, `evidence_handoff_runtime`; Plan 12 packages are absent on this main. Hook/CI explicitly use `--cov=optimus`, narrowing the configured five-package source list. xdist is not declared in dev dependencies.

## Requirements — settled operator decisions

These are labelled paraphrases from the handoff and research §12, not newly invented operator quotations.

| ID | Binding requirement |
|---|---|
| R1 / D1 | Pre-commit runs `commit`. Intermediate checkpoints run whole-checkpoint-diff selection, current-code audits at full depth, triggered platform tests on Windows and WSL, and concurrency/race repeats under load; **no full suite at intermediate checkpoints**. |
| R2 / D1 | Final checkpoint runs **one full Windows suite with coverage**, in a supported separate lane started alongside Fable review. It is the only required full Windows run before merge; reuse it for the Windows pre-finalize obligation if source/configuration are unchanged. |
| R3 / D2 | Coverage gates derive from full-suite data, not partial profiles. Optimus has an 80% gate; Context Engine has its own 80%; `optimus_model_policy` has its own 80% floor in addition to inclusion in Optimus. Safety-critical coverage must not regress without explicit review. |
| R4 / D2 | Evidence handoff/A2A threshold is 80%, enforcement deferred until revisited. Interim figures are informational and create **no new-test obligation**. |
| R5 / D3 | Option (c): `audit-current` at every checkpoint now; per commit at quick depth once audit optimization G is accepted. Checkpoints retain full depth. |
| R6 / D4–D5 | HIGH priority, main-based; xdist is inside this plan on merged Plan 11.28. Plan 11.28 implementation prerequisite is satisfied by PR #227 `f8231e85`, registry filing #228 `f98567e`, shared guidance #229 `a929aab2`. |
| R7 / D6 | No Windows CI runner or nightly lane is scheduled now. |
| R8 | The 2026-07-31 full WSL pre-finalize run remains mandatory. Triggered WSL profiles and Linux PR CI do not replace it. |

## Global constraints and Explicit Exceptions

Everything in this contract is in scope except the following named exclusions. An implementation agent cannot narrow it silently; substantive revisions use one complete `_vN` successor and operator approval.

- Preserve approved `addopts`/effective `-m`, root conftest, existing node IDs, test paths and binding manifests. Profiles use `--profile`, never a replacement `-m` or cleared addopts. No move/rename of tests; bounded audit test edits are permitted only for Task 4's depth/cache controls, preserving node identities and full-depth assertions.
- Independent worktrees and frozen environments; one coverage writer per worktree including hooks. Windows and WSL have separate environments. No environment sync while a run is active. No new shared-worktree coverage lock or automatic drift validator is presumed delivered by 11.28.
- Record source/branch/HEAD/status before and after, interpreter, platform, config/lock identities, exact command, run ID, exit/output and terminal records. Dirty development results are provisional, bound to diff/hashes. Acceptance checkout stays unchanged. Phase-boundary sampling is not periodic monitoring; Windows jobs are not filesystem sandboxes.
- INVALID, incomplete, absent, skipped and UNKNOWN evidence do not establish the corresponding claim. Preserve failures and detection-time verdicts; diagnostic joins never turn them into PASS. No retry-to-green acceptance, timeout widening, new exclusions or detector weakening.
- Named live tiers keep real dependencies; ACP protocol claims use independent acpx. Profile machinery may use synthetic unit fixtures, which establish selector/ownership logic only, never live product acceptance.
- Preserve one-key model and current unrelated tests/gates. Keep `optimus-check: pytest-coverage` labels in hook and CI; the label does not assert commit-profile coverage acceptance.

| Explicit exception | Custody / boundary |
|---|---|
| Product behavior changes, unrelated test optimization and debt remediation | Existing owners; this plan changes test orchestration and bounded audit implementation only |
| Plan 11.28 workflow activation, branch folding, worktree/WSL clone/fixture cleanup | `P11-FEAT-ACP-RUNTIME-HARDENING`; existing operator holds remain |
| 693 unadjudicated scan findings and broader scanner debt | `P11-FU-31`; 11.28 delivery exception v2 does not transfer here; no blanket scan waiver |
| Plan 12 implementation/CP4 correction or accepted-evidence repetition | Plan 12 / Plan 12.2 lane; coverage interface only here, no lane messages or modifications |
| A2A coverage enforcement or new tests solely to lift its percentage | `EVIDENCE-HANDOFF-FEAT-A2A-LEDGER`; deferred operator requirement R4 |
| Windows CI/nightly, CI job splitting, pre-push full hook, testmon/dynamic coverage-context TIA | `P11-FEAT-TEST-PROFILES` tracked unscheduled custody; not selected for this implementation |
| Historical bound-node CI blind spot and missing live desktop marker remediation | `P11.26-UNRUN-BINDING` / `P11-FEAT-ZED-RESUME`; Task 0 verifies actual node/marker inventory and links disposition, without resolving their product/live evidence |
| MAIN-5 overhead, broader FU-6/FU-33 reliability closure | `P11-FU-36`, `P11-FU-6`, `P11-FU-33`; preserve existing detector obligations and separate failures |

## Prerequisites

| Category / prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? | Establishment / dependent task |
|---|---|---|---|---|
| Code/state: merged 11.28 + shared guidance; clean current main | yes | Reviewer | — | Intake pin above; Task 0 re-pin latest main |
| Code/state: classification, complete dependency manifest and profile runner | no | Implementer | genuinely absent, buildable now | Tasks 1–3 before hook switch |
| Code/state: Context Engine/model-policy packages on main | no | Plan 12 lane | genuinely hard: external lane delivery/authority | Task 0 checks arrival; absent is N/A, never 100% coverage or an executed gate |
| Machine: accurate registry inventory and approved housekeeping mechanism | unknown | Operator (machine state); hardening owner (design) | genuinely hard until identity/query ability established; cleanup authority is merely unauthorized | Task 0 before attribution/performance acceptance or activation |
| Tooling: usable Git, Python 3.14, uv, frozen dev env, pytest/cov and compatible xdist | unknown | Implementer; operator for installation | early check distinguishes genuinely absent from merely unauthorized | Task 0 records versions/compatibility; no install authorized by this draft |
| Platform: native Windows + real WSL Ubuntu, independent env/worktree | unknown | Operator | merely unauthorized if available; otherwise difficulty unknown | Task 0 checks WSL inventory/tooling before Tasks 2/5 or final gate |
| Code/evidence: historical binding objects needed by bound audits | unknown | `P11.26-UNRUN-BINDING` owner | genuinely hard if unavailable from authorized source | Task 0 verifies availability on each platform; affected claims UNRUN until disposition |
| Parallel lane: independent frozen acceptance checkout at exact candidate state | no | Implementer/operator | merely unauthorized to create/prepare | Prepare before final Fable review/full Windows run |
| Human: Fable final review and independent Codex checkpoint review | unknown | Operator schedules reviewers | merely unauthorized | Task 0 establishes availability; no automatic messaging authority |
| Services/credentials: ordinary profiles use default exclusions; no external service or paid provider needed | yes | Implementer | — | Preserve live markers; a live claim would require separately granted real service/acpx/credentials |
| Authority: mechanism/implementation, local commits, publication, cleanup grants | no | Operator | merely unauthorized | Draft review first; separate specific grants later |
| Cost: no paid model/service call needed for test-profiles acceptance | yes | Operator | — | Reviewer model usage and local resource time remain operational costs, not provider-test calls |

Every unknown has a Task 0 check before its dependent work. Missing prerequisites block the relevant claim; they cannot be replaced with a fake, favorable skip or another lane's old receipt.

## Design Contract — proposed mechanisms for review

### 1. Classification, profiles and selector

`tests/profiles.toml` holds exactly one cost tier per collected node: `core`, `gates`, `proc`, `audit-current`, `audit-sealed`, `e2e-local`. Default core is allowed for cheap new nodes; any node with measured setup+call+teardown >2 seconds needs an explicit rule. Node-specific overrides replace a broad rule by documented precedence; conflicting overrides fail. Rules must match existing nodes; union is the default eligible universe, not live-excluded tests. Platform/concurrency tags are additive and have consumers. No additional behavior-tag taxonomy or empty memory profile ships.

Classify current-source/HEAD-reading guards by behavior: S1 execution closure, Zed import closure, logging manifest, walker allowlist, debug-trace rule, naming/package/collector boundaries and credit surface belong to `gates` or `audit-current`. Current-tree helper callers belong to `audit-current`; pinned replay/seeded historical models belong to `audit-sealed`, never product concurrency. Guard review combines AST/read-path inventories with explicit helper/domain declarations; static inspection cannot prove all dynamic dependencies.

| Profile | Selection and cadence |
|---|---|
| absent / `full` | Identity selection over current approved default universe. Default stays serial. |
| `quick` | Change-selected core for inner loop; optional `--lf`/`--ff` never acceptance evidence. |
| `commit` | All gates + dependency-selected eligible nodes in all tiers, except current audits use R5 cadence. Triggered platform nodes included. Docs-only uses docs gates; unknown docs paths still need a mapping/fallback. |
| `checkpoint` | Whole checkpoint diff's eligible selection + all gates + all `audit-current` at full depth; triggered Windows/WSL platform lane and repeated concurrency lane are mandatory runner subruns. Never silently full. |
| `platform` | Reviewed Windows-only, POSIX-only, platform-branch and relevant host-following nodes; existing skipif/live-marker semantics retained. |
| `concurrency` | Explicit current-product race/async/thread/teardown nodes, including relevant FU-33 detector obligations. |
| `audit` | Both audit tiers, full depth, focused use; not an implicit full-suite checkpoint. |

Selection inputs are NUL-safe Git paths/statuses, base SHA, HEAD, index tree and working diff identity. Commit uses committed changes since declared reviewed base plus staged names; checkpoint uses the whole declared checkpoint-base..HEAD plus index/development diff. Base defaults to merge-base with freshly pinned main but previous-checkpoint base is explicit. No reliance on the last commit alone. Tests execute working-tree bytes; partially staged or unstaged relevant divergence must be captured and included in provisional selection or rejected by the acceptance wrapper, never labelled an index-only exact-source run.

Reverse AST import closure includes relative imports, package `__init__`, tools and transitive test imports. Deletions/renames inspect both old and new dependency views; missing old view falls back. Explicit manifests cover string/dynamic imports, subprocess launch domains (including merged child-launch inventory), fixtures, reports, logging-surface manifest, `.secrets.baseline`, audit `*_SOURCE_PATHS`, configuration and generated data. New/unmapped code/data or malformed/stale manifest, unavailable base, Git error, unsupported path or incomplete dependency graph requests fallback. No importing application modules to discover dependencies, eval or execution of source/tool text.

Fallback rules are testable and conservative: root conftest, shared test support, profile manifest, pyproject, lock, pre-commit config, `.github/**`, sgconfig and unmapped paths request full. A commit profile may execute an explicit full fallback with a prominent reason, preserving ACTIVE and recording actual profile. At an **intermediate checkpoint**, full fallback returns nonzero `SELECTION_BLOCKED` before test launch. Reviewer must approve a complete conservative *focused* mapping for that whole diff in a versioned contract; if that cannot be established, the checkpoint remains blocked. It is never converted into full or a passing narrow subset. During this plan's bootstrap, changed orchestration files necessarily hit fallback: Tasks 1–5 have the explicit focused dependency inventory and gate commands below as their bootstrap disposition; Task 0 must enumerate every changed path to those suites and reject uncovered paths. Final full covers integration. This bootstrap exception is specific to reviewed orchestrator changes, not a generic future bypass.

Plugin adds `--profile` and deselects with `pytest_deselected`; it leaves effective `-m` unchanged. All default exclusions compose with profiles, explicit targets and `-k`. UNRUN count derives from final selected items after all deselection, preserving skip identities/reasons. No-profile collect-only node output and existing summary remain equivalent to baseline (variable run IDs/timestamps compared separately). Single-file subprocess collection must load the plugin. Foreign configs/overridden selection remain PASSIVE and cannot establish ACTIVE claims.

Record a sanitized bounded profile summary plus a hashed selection manifest: base/head/index/diff identities, classification/map digests, selected/deselected node IDs, every trigger/fallback reason and depth. Preserve native classification reason instead of replacing it with misleading `profile:full` protection text. Selection metadata is additive versioned schema; unknown fields/versions fail validation. A run manifest carries coverage intent and subrun/repeat IDs.

### 2. Registry housekeeping before increased run cadence

Task 0 must inspect the existing owner and validate host temp location, record schemas, PID+creation identity/query errors, terminal receipts and concurrency races. Proposed mechanism: **explicit operator-invoked maintenance**, no auto-prune at test start. Produce an inventory/dry-run with exact entries and digests; identify dead processes by positive native identity evidence, never age alone. A deletion candidate must have a valid schema, matching run ID, identity proven ended, and retained terminal evidence or an explicit reviewed abandoned-run disposition. Re-read identity/content immediately before a narrowly scoped removal; live, malformed, unreadable, replaced/reused PID and UNKNOWN entries stay untouched. Preserve sanitized before/after receipt and retained records. Native Windows and Linux maintenance differ in capability and must retain weaker labels.

This is a proposed bounded extension co-owned with `P11-FEAT-ACP-RUNTIME-HARDENING`, not a grant to clean the workstation. Review approves algorithm/tests first; machine cleanup needs exact inventory authorization separately. If >512 unresolved entries remain, keep `partial`/UNKNOWN and withhold full attribution acceptance. Raising the cap or ignoring unknown entries is not a substitute. Profile unit work can proceed while machine state is blocked; hook activation/parallel acceptance cannot.

### 3. Full-suite coverage and safety-critical protection

Proposed coverage classification partitions every importable production package under `src/` exactly once, excluding distribution metadata: Optimus = `optimus`, `optimus_gateway`, `optimus_security`, `optimus_model_policy` when present; Context Engine = `context_engine`; deferred A2A = `evidence_handoff`, `evidence_handoff_runtime`. The separate model-policy floor is an additional report over the same partitioned package, not a second membership. Unknown/new packages fail closed until reviewed. Missing future packages are explicitly N/A on that source SHA; when introduced, their named floors become mandatory without changing Plan 12 code.

One default full suite produces bare `--cov --cov-branch --cov-fail-under=0` data, JSON and terminal reports. A coverage-report tool evaluates unrounded line/branch-derived coverage using coverage.py's canonical calculation per group at >=80; missing/zero-denominator required data fails. Optimus aggregate and model-policy floor both apply. A2A is printed informationally with enforcement=false, never changes exit status or requests tests. Partial profiles default to `--no-cov`; optional partial coverage is report-only, separately named and cannot satisfy full gates. Do not combine different sources/platforms/partial profiles into full acceptance.

Use one controller-owned coverage writer/combine lifecycle per worktree; per-worker coverage shard files under that run are allowed only as one coordinated writer lifecycle in Task 5, not concurrent independent coverage commands. Child subprocess execution coverage remains an explicit limitation unless separately proven. Keep data source list in sync with package classification and negative-space tests; `--cov=optimus` must no longer silently narrow full acceptance.

Safety-critical baseline is measured at the same base/config/platform full-suite scope, or an existing valid equivalent retained artifact. ToolRegistry authorization, MutationGuard, GatewayUsage/accounting, ledger reconciliation, JSON-RPC framing, retry/fail-closed and policy enforcement get per-module line/branch reports and explicit reviewer non-regression comparison. A missing baseline is UNKNOWN and must be established/disposed before safety-critical acceptance; adding percentage floors is not presumed operator policy. Do not rerun accepted Plan 12 CP4 work to establish this plan's baseline.

### 4. Audit optimization and checkpoint stability

`--audit-depth=full|quick`, default full. Full retains all current repeat counts, seeded schedule counts, measurement windows, assertions and failure semantics. Quick proposal: one execution of each distinct current probe shape, retain all required context/provenance and failure assertions, lower only explicitly enumerated repeat/sample budgets. Task 0/4 reviews exact per-probe budgets with the Plan 11.26 owner before coding; unsupported quick probes remain full or block activation, never silently disappear. Quick is labelled reduced-depth and cannot prove checkpoint stability or replace a repeat-100 obligation. Transition R5 to commit quick only after reviewed quick/full parity controls pass.

Cache immutable baseline exports by commit + requested path set + tool/config version within session; current measurements keyed by exact source hashes, domain, depth, platform and environment. No reuse across source edits, seeds requiring independent observations, threads, sessions or incompatible shapes. Failure observations persist unchanged. Cached data cannot mint fresh execution contexts or merge repeat observations. Keep sealed inputs/approvals immutable; optimization of sealed replay is secondary and must not displace current-audit work.

Proposed checkpoint load protocol: three separately attributable executions of every selected concurrency node, at original internal repeat depth, while a bounded same-lane CPU load process is active (one process, one busy thread, 1800-second watchdog, owned cleanup). Capture load start/end, CPU time, platform/process identity, all seeds and per-repeat results; watchdog expiry or absent measurable load invalidates load evidence. Run serially; no xdist in timing/race lane. Platform trigger includes changed platform-divergent modules, path/case/line endings, keyring, ctypes/msvcrt, subprocess/env/shell and selector/runner/ownership changes. Windows and real WSL each execute triggered profile and relevant concurrency nodes; incompatible nodes retain reasons, not false parity. Three is an agent-proposed minimum for ordinary checkpoint repeats; existing repeat-100/200 or plan-specific counts remain binding. Failures stop acceptance, preserve all results and return to the owner for disposition; no automatic favorable rerun.

### 5. xdist compatibility contract

Only explicitly reviewed parallel-safe `core` nodes, excluding gates/audits/subprocess ownership/global-state and concurrency/timing domains, may run distributed. Start with `-n 2`, not `auto`; larger counts require measured evidence. Dispatcher partitions selected nodes into disjoint parallel core and serial remainder, records their union/digests and prevents omissions/duplicates. `full` remains one serial invocation for accumulation/order coverage; checkpoint orchestration can accelerate core as a separate subrun. Unsupported `-n` with unsafe/all profiles fails before workers start, never distributes arbitrary nodes.

Controller alone owns canonical run ID, Windows job/guard lifecycle, registry announcement, selection ledger and terminal verdict. Worker ID/process identity attach through authenticated run metadata and independently validated ancestry/creation identity, not an environment string alone. Each worker installs trusted-root redirection before collection in its interpreter and uses unique temp/resource namespaces. Workers never announce independent top-level ACTIVE runs or create unreviewed nested jobs. Each worker is in controller cleanup ownership and receives kill-on-close; worker grandchildren remain attributable to their worker and controller. Windows validity requires real native tests; WSL records its weaker capabilities explicitly.

Worker events have isolated streams or controller serialization, deterministic duplicate detection and complete node/phase attribution; no concurrent append to the same file. Preserve collection/deselection agreement, UNRUN accounting, node counts and source identities. Worker crash, restart, missing stream, mismatched selection, invalid association, failed guard or escaped descendants makes the affected evidence INVALID even if pytest would otherwise pass. Disable automatic worker restart for acceptance (`--max-worker-restart=0`). Coverage shard combination has one controller authority and checks shard source/config/run identity before reporting. Nested subprocess pytest belongs to validated parent context, never falsely another worker. MAIN-5 and its explicit plugins/targets remain serial with baseline semantics; do not count this feature as activation of held MAIN-5 workflows.

## Review Focus

1. Unmapped dynamic/data/launch dependency or stale base must block/fallback, never produce false selective PASS (Task 2).
2. Profile deselection must not remove current-source gates or alter ACTIVE/UNRUN semantics (Task 1).
3. Registry unknown/PID reuse cannot authorize deletion or favorable parent attribution (Task 0).
4. xdist worker crashes/children/guards cannot lose source attribution or leave survivors (Task 5).
5. Coverage denominator drift, missing package rows or partial-data reuse cannot hide a product below 80 (Task 3).

## File and interface map

Paths below are proposed implementation ownership, not files implemented by this draft.

| File | Responsibility |
|---|---|
| `tests/profiles.toml` | Tiers, tags, data/launch/domain dependency declarations and bootstrap mapping |
| `tools/testing/test_profiles.py` | Pure classification and deterministic selection contracts |
| `tests/support/test_profiles_plugin.py`; `tests/conftest.py` | Additive options/selection, final UNRUN and run-context integration |
| `tools/testing/run_profile.py` | CLI cadence, platform/repeat/load dispatch and evidence manifests |
| `tools/testing/coverage_products.py` | Product/package classification and full-data report gates |
| `tools/testing/run_context.py`, `run_context_records.py`, `run_context_windows.py`, `run_context_guard.py` | Additive schema/worker ownership/guard proof; bounded registry-maintenance support |
| `tools/testing/registry_maintenance.py` | Explicit inventory/dry-run and guarded authorized maintenance |
| `tools/plan1126_runtime_audit/source.py`, `measurement.py`, affected current probe modules | Bounded cache/depth extension; exact path set pinned at Task 0 review |
| `tests/unit/tools/test_test_profiles.py`, `test_test_profile_selection.py`, `test_run_profile.py`, `test_coverage_products.py`, `test_registry_maintenance.py`, `test_run_context_xdist.py` | Focused independent controls, including subprocess/native tests |
| Existing run-context suites, current-measurement audit suites and CI-parity tests | Retained regression controls; edits only where this contract requires additive controls |
| `pyproject.toml`, `uv.lock`, `.pre-commit-config.yaml`, `.github/workflows/guardrails.yml`, `AGENTS.md`, `CONTRIBUTING.md` | Dependency and approved cadence/coverage wiring, preserving labels/default selection |
| `reports/plan-11-30-test-profiles-evidence.md` plus hashed sanitized JSON artifacts | Durable evidence/claim mapping; raw temp records retained separately before pruning |

Pure interfaces in `test_profiles.py`: `classify_nodes(nodeids: tuple[str, ...], manifest: ProfileManifest) -> Classification`; `select_tests(changes: ChangeSet, classification: Classification, dependencies: DependencyMap, request: ProfileRequest) -> Selection`. Records carry immutable source/map identities; Selection has node IDs, per-node reasons, platform triggers and `fallback_required` reasons. `coverage_products.py`: `evaluate_products(coverage_json: Path, package_roots: tuple[str, ...], full_run_manifest: Path) -> CoverageVerdict`; rejects non-full/source-mismatched input. `run_profile.py` CLI is `python -m tools.testing.run_profile --profile NAME --base SHA [--bootstrap-map PATH] [--parallel-core 2]`; it resolves/pins the base, emits manifest and exits nonzero for selection-blocked, test failure or invalid evidence. Task 0 pins record schemas and fixture representations before dependent implementation; these public signatures are the draft contract.

## Tasks and checkpoints

All steps are unchecked. Commands are future execution gates, **not run during drafting**. Use the lane's prepared environment with `uv run --no-sync`; `uv sync --frozen --extra dev` only before runs. No commit is an automatic task step: obtain specific authority and run Ruff before any authorized commit/sign-off.

For Checkpoints B–D, the cadence command is `uv run --no-sync python -m tools.testing.run_profile --profile checkpoint --base <task0-pinned-base-SHA> --bootstrap-map tests/profiles.toml`, followed by its required real WSL platform/concurrency subruns in the independent WSL lane. The base is a recorded immutable SHA, not a moving branch name. Bootstrap-map entries enumerate each changed orchestration path, its tests and transitive dependents; they never disable all fallback rules. Task-specific focused commands below are additional controls, not replacements for full-depth current audits and load repeats. Checkpoint A approves prerequisite/design work before this runner exists and makes no product checkpoint PASS claim. Before the plugin exists, focused commands retain the baseline conftest/default selection and record provisional bootstrap evidence; afterward they use the same approved selection with additive profile metadata.

### Task 0 — Prerequisite discovery, evidence filing and bounded ownership design (4–6 hours)

- [ ] Verify latest main, clean source/worktree topology, frozen dependency/tool versions, WSL readiness, binding availability, actual node/package/helper/launch inventory and existing debt/owner records. Record each prerequisite yes/no/unknown and first blocking dependent task in `reports/plan-11-30-test-profiles-evidence.md`.
- [ ] Verify research pins and retained raw/derived data; file sanitized summary/hash manifest preserving failed-run/shared-load/older-map limitations. Do not copy raw secrets/private paths into Git.
- [ ] Produce registry dry-run design and current exact inventory; agree hardening ownership, bootstrap dependency map, quick probe budgets and xdist version/worker schema with reviewer. Record operator requirements/agent proposals in the next available unpublished ADR under `docs/decisions/`, with shared source references; Claude and Codex review before delivery. No accepted decision is overwritten.
- [ ] Add failing then passing unit controls for malformed/reused/unknown/live/dead registry identities and TOCTOU races. Verify with `uv run --no-sync pytest --no-cov tests/unit/tools/test_registry_maintenance.py tests/unit/tools/test_run_context.py tests/unit/tools/test_run_context_lifecycle.py`. Expect all applicable controls PASS; native unavailable controls UNRUN, not substituted.
- [ ] Obtain separate exact inventory authority before machine maintenance. Preserve before/after hashed receipts. If unresolved cap overflow remains, withhold registry/parallel validity acceptance and activation; do not auto-remove entries.

**Checkpoint A:** Codex reviews prerequisites, provenance, proposed mechanisms and every bootstrap mapping row. Implementation authority starts only after complete-plan approval; maintenance authority is separate. No baseline full measurement is scheduled at this intermediate checkpoint. Historical timing is not refreshed by narration.

### Task 1 — Classification and additive plugin (4–6 hours)

- [ ] Write failing controls for exactly-one tier, unmatched/conflicting rules, tier-union equality, >2-second explicit rules, current-source/helper guard placement and audit split. Include S1 and Zed closure regression nodes.
- [ ] Implement manifest/classifier/plugin and additive schema integration; preserve default marker expression and conftest isolation. Capture classification snapshot without acceptance claims.
- [ ] Write/verify subprocess single-file collection, no-profile selection/output equivalence, final UNRUN after deselection, explicit targets/`-k`, overridden-config PASSIVE, default ACTIVE subsets and MAIN-5 plugin compatibility controls.
- [ ] Run `uv run --no-sync pytest --no-cov tests/unit/tools/test_test_profiles.py tests/unit/tools/test_run_context.py tests/unit/tools/test_run_context_boundaries.py tests/unit/tools/test_run_context_lifecycle.py tests/unit/tools/test_plan1126_unrun_binding.py tests/unit/guardrails/test_ci_parity.py`; all applicable controls pass, with zero unexplained selected/deselected differences.

### Task 2 — Dependency selector and checkpoint/load runner (6–10 hours)

- [ ] Write failing synthetic repository controls: transitive/relative/package imports, rename/delete, staged plus whole-diff, partially staged/dirty source, paths with spaces, missing base, string imports, child launch domains, fixture/report/baseline/manifest mapping and each fallback path. Plant cross-module/fixture/launch changes that must select their dependent tests.
- [ ] Implement pure selector and deterministic reason manifest. No-profile remains identity. Test full fallback at commit and `SELECTION_BLOCKED` before any launch at checkpoint, plus complete reviewed bootstrap mapping and its uncovered-path rejection.
- [ ] Implement checkpoint runner/load lifecycle and test three per-node repeats, full audit depth, triggered Windows+WSL obligations, interrupted cleanup, failed/UNKNOWN observation preservation and no retry-to-green.
- [ ] Run `uv run --no-sync pytest --no-cov tests/unit/tools/test_test_profile_selection.py tests/unit/tools/test_run_profile.py tests/unit/tools/test_test_profiles.py tests/unit/tools/test_run_context_child_sites.py`; run those platform-sensitive controls on real Windows and WSL. Expect deterministic identical selection sets for equivalent source inputs, zero missed planted dependencies and correct platform capability labels.

**Checkpoint B:** Whole Task 0–2 diff; approved bootstrap focused gates, current audits full depth, triggered platform checks and concurrency repeats under load. No full suite. Codex reviews selector negative-space coverage and records unresolved baseline/registry limits.

### Task 3 — Product coverage reporting and hook wiring (4–6 hours)

- [ ] Write failing controls: unknown package, duplicate membership, absent future package N/A, present package missing data, Optimus pass/model-policy <80 failure, Context Engine <80 failure, boundary just below/exactly80, A2A <80 informational, partial/source-mismatched data rejection and safety-critical missing baseline UNKNOWN.
- [ ] Implement report tool/config. Use current five packages now and conditional future-package controls; do not import or change Plan 12 lane. File/acknowledge historical narrowing with that owner's already completed relay as context, not a new message or repeat correction request.
- [ ] Wire pre-commit to `python -m tools.testing.run_profile --profile commit` without coverage gate; full Linux CI to runner full/report logic. Preserve check labels, hygiene/security hooks and approved selection. CI wiring is a proposed change requiring plan execution approval; it does not activate held 11.28 operational workflows.
- [ ] Run `uv run --no-sync pytest --no-cov tests/unit/tools/test_coverage_products.py tests/unit/tools/test_run_profile.py tests/unit/guardrails/test_ci_parity.py tests/unit/evidence/test_naming_boundaries.py`; verify an actual commit-profile hook invocation against a disposable reviewed fixture index, without creating a commit. Expect partial profile never evaluated as full coverage and all existing check labels retained.

### Task 4 — Audit cost reduction and D3 transition (6–10 hours)

- [ ] Agree exact current-probe path/budget inventory with Plan 11.26 owner; write failing source/depth/cache invalidation, execution-context freshness and detection-time failure controls. Preserve historical/sealed digests.
- [ ] Implement immutable-export cache and explicitly keyed current-measurement reuse/depth controls. Full behavior stays equivalent to original counts/observations; quick never claims full stability.
- [ ] Run `uv run --no-sync pytest --no-cov tests/unit/tools/plan1126_runtime_audit --audit-depth=full` and the same focused audit folder with `--audit-depth=quick`; compare full baseline counts/contracts and injected detector failures. Add retained ACP/telemetry current-audit suites identified in Task 0, not merely this tooling directory. Expected every mandatory full probe executes and planted failure survives both depths.
- [ ] Measure active Windows core-only and quick/full current-audit wall/phase/collection/resource durations with no coverage, on same source/frozen env; active run is primary. Any optional passive recorder comparison is separately labelled diagnostic and cannot prove protection. Record host load; no full baseline measurement here. Activate commit quick only after acceptance of G; otherwise retain checkpoint-only cadence and hold completion of R5 transition.

**Checkpoint C:** Whole diff through Tasks 3–4; checkpoint profile obligations unchanged, using reviewed bootstrap mapping. Codex reviews coverage boundaries and full-depth audit fidelity. Safety-critical full-data comparison waits for final evidence if valid baseline already exists; missing baseline has an explicit Task 6 prerequisite gate.

### Task 5 — Core-only xdist integration (8–12 hours)

- [ ] Confirm official installed/dependency source for chosen pytest-xdist/pytest-cov version behavior and lock dev dependency, then refresh each idle independent environment. No dependency behavior assumed from old research.
- [ ] Write failing controller/worker/native controls: worker identity forgery, reused PID, worker guard absence, direct/launcher/grandchild containment, worker crash/no restart, interrupted controller cleanup, concurrent worker writes, collection disagreement, schema/source/config mismatch, duplicate/lost phases and missing coverage shard.
- [ ] Implement controller ownership, worker attachment/guard/event streams and core dispatcher. Reject unsafe profile/`-n` combinations before spawn. Coverage and registry lifecycle retain single ownership; cleanup kills only owned processes.
- [ ] Run `uv run --no-sync pytest --no-cov tests/unit/tools/test_run_context_xdist.py tests/unit/tools/test_run_context.py tests/unit/tools/test_run_context_boundaries.py tests/unit/tools/test_run_context_child_sites.py tests/unit/tools/test_run_context_lifecycle.py tests/unit/tools/test_test_profiles.py tests/unit/tools/test_run_profile.py` on real Windows and WSL. Native tests must use real workers/children, not unit fakes standing in for process ownership.
- [ ] Compare matched serial vs two-worker core-only runs at same source/platform/env, including selected-node union, outcomes, attribution, leftovers, recording validity and timing. Proposed acceptance: zero missing/duplicated nodes/escaping children/invalid records; median core wall improvement >=20% over three matched pairs, without increased failures. If performance fails, retain serial baseline and record unsatisfied xdist objective; no claim of completion or silent deferral outside a reviewed successor.

**Checkpoint D:** Whole diff through Task 5; focused bootstrap checkpoint checks, full current audits, real triggered Windows/WSL controls and serial concurrency repeats under load. No full suite. Review evidence validity independently from test exits.

### Task 6 — Final exact-source gate and handoff (4–6 hours plus full-run wall time)

- [ ] Audit current-state claims across backlog, roadmap, README, docs index, hook/CI guidance and this plan; do not change other lanes' plans/checkboxes. Re-pin latest main before any later authorized delivery. Obtain reviewed disposition of every residual and keep excluded work in its named registry owner.
- [ ] Prepare independent final Windows coverage lane and WSL environment; freeze exact candidate source/config/lock identities. Establish safety-critical comparable base full-data baseline from retained valid same-platform artifact; if none exists, a **separate approved base-only measurement** is a prerequisite, not a second candidate final run and not an intermediate checkpoint full suite. No baseline run is authorized now.
- [ ] Start Fable review and **one serial full Windows run with coverage** together, using `uv run --no-sync python -m tools.testing.run_profile --profile full`. Report all product gates from that same run. Fable's lane must not mutate the acceptance checkout or write its coverage file. Preserve acceptance manifests before another run can prune records.
- [ ] Run the mandatory full WSL pre-finalize gate at the same candidate source using a separate environment and coverage file. Keep platform results/skip reasons and weaker run-context capabilities distinct. No extra full Windows pre-finalize run if unchanged final evidence satisfies that obligation.
- [ ] Run `uv run --no-sync ruff check .`, narrow changed docs tests and `git diff --check`; map each claim to retained evidence. Fable findings that change source invalidate exact-source binding; another candidate full acceptance attempt needs a reviewed bounded disposition, not automatic rerun. Inherited scan failures remain failures pending applicable new disposition; 11.28 exception does not grant this plan one.
- [ ] Codex independently verifies disk/diffs/manifests, full-suite product reports, safety-critical comparison and current-doc freshness. Update the ignored reviewer checkpoint log; ask operator to review the concrete result. Commit/push/PR/merge remain separate grants; no working-agent sign-off outside Plan 9.6.

## Acceptance and claim-to-evidence mapping

Artifacts are proposed outputs under `reports/`; do not mark a checkbox merely because a filename exists. Each row needs command, exact source/config/environment/platform/run ID, stdout/stderr+exit, node/skip identities, verdict, digests and retained records. Failed/invalid/UNRUN evidence remains visible beside later dispositions.

| Claim | Measurable acceptance | Named evidence artifact / task |
|---|---|---|
| Default fidelity and ACTIVE subset protection | Zero unexplained no-profile node/output differences; approved-marker profiles ACTIVE, foreign overrides PASSIVE; correct final UNRUN | `plan-11-30-profile-fidelity.json`, Task 1 subprocess/retained-context controls |
| Complete classification/current-source gates | Exactly one tier/node, union equality, zero unmatched/conflicting rules, all >2s nodes explicit, all known source/helper gates included | `plan-11-30-classification.json`, Tasks 0–1 inventory/guard tests |
| Conservative whole-diff selection | All planted import/data/launch dependents selected; each fallback tested; checkpoint full fallback blocked before launch | `plan-11-30-selector-controls.json`, Task 2 |
| Registry attribution and maintenance safety | Exact inventoried state; no live/unknown/reused/replaced entry removed; bounded read complete or affected claims withheld | `plan-11-30-registry-receipt.json`, Task 0 real inventory + unit/native controls |
| Settled cadence implemented | Hook commit; each intermediate checkpoint manifests selection, full audits, triggers and load repeats; no intermediate full launch | `plan-11-30-checkpoints.json`, Tasks 2–6 |
| Audit optimization preserves detection | Full counts/assertions unchanged; stale context/cache invalidated; injected failures retained; quick clearly reduced | `plan-11-30-audit-parity.json`, Task 4 |
| Platform/concurrency obligations | Real Windows+WSL triggered runs; >=3 load repeats per selected node plus original internal counts; every failure/skip/UNKNOWN attributed | `plan-11-30-platform-stability.json`, Tasks 2/4/5/checkpoints |
| xdist correctness and value | Real two-worker proof, no lost/duplicate nodes, valid native containment/guards, no escaped owned child, >=20% median matched-core improvement | `plan-11-30-xdist-controls.json`, Task 5 |
| Full product coverage | Optimus >=80; present context_engine >=80; present model_policy >=80 separately; zero missing/new package data; A2A informational | `plan-11-30-full-windows.json`, `plan-11-30-full-wsl.json`, Task 6 raw coverage JSON/report manifests |
| Safety-critical non-regression | Comparable full base/candidate per-module line/branch reports, zero unapproved regressions; no baseline UNKNOWN hidden | `plan-11-30-safety-critical-comparison.json`, Task 6 |
| Final review/source/custody | Fable review and full Windows start in separate lanes, unchanged source throughout, WSL full completed, Ruff/doc checks pass, residual owners named | `plan-11-30-test-profiles-evidence.md`, Task 6 |

## Estimates, risks and completion boundaries

Proposed active engineering: **36–56 hours (roughly 5–7 working days)** plus independent review, prerequisite/maintenance authority and full-run elapsed time. Highest difficulty: conservative dependency completeness and native xdist ownership; classification and coverage wiring are medium. Full Windows historical hook wall 27:12 and core 3.5–11 minutes are failed/shared/older-state measurements, not promises. Three xdist matched pairs and full-depth checkpoint/load gates can dominate elapsed time. No guaranteed overall speedup is claimed before measurement; report docs/tools/core examples and whole-diff fallback rate separately.

Preferred approach is additive profiles + conservative manifest selection + bounded core xdist. Marker-only profiles were rejected because they make supported runs passive; testmon/dynamic contexts add baseline/subprocess gaps; indiscriminate xdist risks global-state/ownership; background audit/nightly has no approved vehicle. Serial/full remains the correctness baseline and profiles' selection optimization must earn evidence.

Residual custody is in the sole live backlog, not a second list in this plan. `P11-FEAT-TEST-PROFILES` owns profile/dynamic mapping/duration upkeep and unscheduled CI/TIA options; hardening owns registry/worker shared guarantees; Plan 12 owns its package delivery/evidence; existing FU/binding owners keep their debt. New findings must receive a named backlog entry before any exclusion or closure. Plan 11.29's future registry cutover must be reconciled at pickup; no GitHub issue writes are authorized here.

The operator reviews this draft first. All implementation, tests, installs, machine maintenance, acceptance runs and delivery remain unexecuted. The reviewer handoff log is `docs/superpowers/reviews/plan-11-30-review-checkpoints.md`, ignored and never staged. Approval freezes this contract under the versioned-successor policy; it does not authorize publication, merge or another lane's work.
