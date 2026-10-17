# Static typing hardening Implementation Plan — v2

> Repository filing of operator-approved v2, source SHA-256 `68e5a0484243825cd96aa3340723bd5f5e10a5c1535fd362f6de25b0c34f616e`.
> [Claude accepted the plan](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/329#issuecomment-6221744734).
> The operator then directly approved implementation, one unpushed local commit and Windows/WSL verification, with Claude reviewing results; push and PR are prohibited.
> The pre-approval prerequisite rows below are retained as reviewed history; this receipt satisfies the implementation/local-commit authority rows. Current work state belongs only to [#329](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/329).
> The contract body is unchanged except public repository/evidence reference repairs. Ten exact `.gitattributes` entries support its frozen-byte requirement ([reviewed scope ruling](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/329#issuecomment-6222013429)); no new typing cohort or production tool is added.
> The existing `tests/unit/tools/run_context_child_sites.json` proof map also registers the real Mypy test child, protected by the existing startup tripwire; this preserves the required child protection rather than exempting a new launch.
> Registration compatibility correction ([Claude's review](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/329#issuecomment-6223733211), [Codex's agreement](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/329#issuecomment-6223771263)): the existing hardening masterplan registers this linked Active child. No backlog registry row is added; its independent custody rules forbid duplicate registration. The existing directory-hygiene state assertion follows the board's two Active and thirteen Not drafted children while preserving all fifteen identities and link/disjointness rules. This supersedes only v2's conflicting backlog-pointer instruction; the approved source is retained unchanged.

Complete successor to the first draft, incorporating Claude's review in #329 comment 6221673566. The prior draft and its review remain unchanged. This revision is still a proposal, not implementation authority.

> **For agentic workers:** Use `superpowers:executing-plans` for inline execution. Codex implements; Claude independently reviews. No delegated implementation. Checkboxes describe future work, not authorization or completed work.

**Goal:** Enforce typing on all source modules, contain measured debt with a decreasing exception set, and close telemetry as the first cohort.

**Architecture:** Mypy checks `src` through one configuration. One pytest policy module compares exact source exceptions with accepted Git history; a separately bound initial fixture permits the first bootstrap only. Telemetry factories supply their existing trace ID explicitly without changing runtime contracts.

**Tech Stack:** Python 3.14, uv, Mypy 2.3.1, pytest, TOML, Git, pre-commit, GitHub Actions; native Windows and Ubuntu 24.04 WSL environments.

**Spec:** [Accepted proposal v3](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/329#issuecomment-6220390839), [accepted C1 baseline](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/329#issuecomment-6221031385), and [retained C1 baseline](../../../reports/static-typing-baseline-2026-10-16_v2.md). These are provenance; future repository filing carries a self-contained contract below and repository-visible bootstrap data.

## Approval requested — operator section

Approve one local implementation batch: the all-source Mypy gate, its Git-backed exception ratchet, and telemetry as cohort 1. Codex implements and Claude reviews the result. Existing issues #329 and #328 retain custody; no new issue or general test-double conversion.

The accepted baseline is **231 errors / 46 files on Windows; 222 / 45 on real WSL**, covering 226 source files. The union is **46 exact modules**. The initial exception set may contain only those modules; telemetry's 16 diagnostics must close and its exception must be removed, leaving **45**. A masked green result does not establish that those 45 modules are clean.

Keep Mypy locked at 2.3.1, the two reviewed exact stub pins, and the single justified third-party import exception. Upgrades or exception growth require a separately reviewed, operator-approved re-baseline. The bootstrap fixture binds the accepted list once; later checks use Git history, never the original list as a reusable allowance.

Local work includes the files listed below, plan/index registration, necessary staging, and a native WSL verification clone with its own environment. Preserve all baseline and failed-run evidence. Run focused checks, whole-diff checkpoint checks, then serial Windows and WSL product-coverage verification; Claude reviews the actual results before delivery approval.

**Explicit local-commit decision:** include one unpushed local implementation commit after focused/checkpoint checks and Claude's pre-commit review, before the final full Windows/WSL runs. This lets both hosts verify one SHA and lets committed-plan hygiene checks see the new plan. This is a request for that authority, not a commit already authorized or made.

**Excluded:** other source cohorts, registry override fixes, new production tooling, services, paid calls, watchers, memory writes and cleanup. The proposed local commit does not authorize push, PR, merge or activation. Further commits after a failed final gate require a bounded follow-up decision.

## Global Constraints

- Source pin: `c5ea5a1673b957f1e2dd3a09321c6a34ff293880`; lane `agent/codex/static-typing-port` at `C:\worktrees\optimus-cost-agent-worktrees\optimus-cost-agent-wt-codex-typing`. Refresh identity and overlaps before mutation; source drift requires review, not silent rebasing. A later main tip may be a bootstrap comparison base only under the ancestry and configuration rules below; that allowance does not approve new source diagnostics.
- Setup already exists as uncommitted `pyproject.toml` / `uv.lock` changes. Reuse it; do not resolve dependencies again. `mypy>=2.3,<3` is locked to 2.3.1; `types-pyyaml==6.0.12.20260906` and `types-defusedxml==0.7.0.20260504` are intentional pins. Keep the exact `confusable_homoglyphs` import exception and no additional third-party suppression.
- Keep `files = ["src"]`, `python_version = "3.14"`, `show_error_codes = true`; no global ignore, excluded source tree, wildcard exception, skipped import traversal, or weakened diagnostic selection.
- Source exceptions use one `[[tool.mypy.overrides]]` group, exact module names, `ignore_errors = true`, and a debt comment linking #329. Do not suppress all of `optimus.*` or exempt new/clean modules.
- One policy-test module, no `tools/check_mypy_ratchet.py`, CLI, second mutable allowance list, or general bypass environment variable.
- Telemetry keeps all method signatures, validator behavior, direct-construction semantics, payloads, redaction and settlement fields. Its tests use real models; no mocks or newly invented conversions for #328.
- Preserve source/environment identities, stdout, stderr, exit codes, failed attempts, skips and UNKNOWN qualifications. Baseline and historical evidence remain immutable; use new successor files.
- Repository AGENTS.md, CONTRIBUTING.md, evidence policy, ADR-020/022 and current test-profile/coverage contracts apply. Operator decisions here supersede generic implementer-role defaults only for this port.

## Review Focus

1. A removed exception must fail if reintroduced against a later accepted baseline (Task 1 history control).
2. A valid working file must not hide a broader staged configuration (Task 1 index control).
3. Missing or wrong CI history must fail, rather than treating candidate HEAD as accepted (Task 1 event controls).
4. An original bootstrap module must not remain permanently eligible (Task 1 post-bootstrap control).
5. Factory typing changes must preserve explicit direct trace IDs, fallback and redaction (Task 2 runtime controls).

## Prerequisites

| Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|
| Implementer/reviewer assignment and signed #329 coordination | yes | Operator / Codex / Claude | Codex implements; Claude is sole independent reviewer |
| Main-based lane, environments, fresh baseline and C1 review | yes | Codex / Claude | Accepted in comment 6221031385; setup remains uncommitted |
| Telemetry is a complete first cohort; test doubles classified | yes | Claude / #328 | Sixteen matching diagnostics on each host; existing tests use real models |
| Concrete implementation plan independently reviewed | no | Claude | Genuinely absent; first draft reviewed, successor acceptance pending before operator presentation |
| This implementation batch approved | no | Operator | Merely unauthorized; approval requested only after Claude accepts the plan |
| Current file overlap and source identity refreshed | yes | Codex / Claude | Claude checked main and open/local lane overlaps in comment 6221673566; refresh before edits |
| Git-native WSL verification copy prepared | no | Codex | Merely unauthorized; included in proposed local verification scope |
| One unpushed local commit for final verification | no | Operator | Merely unauthorized; explicitly requested in this revision's approval section |
| Publication and merge | no | Operator | Merely unauthorized; separate delivery decisions |
| Services, credentials or paid runs needed | yes | Codex | This batch is offline and needs none |

## File responsibilities

Paths below are relative to the implementation lane, except the private plan draft. Production scope is telemetry plus the one-name guardrail-parity addition below.

| File | Responsibility |
|---|---|
| `pyproject.toml` | Retain approved setup; install exact measured source exceptions, then remove telemetry |
| `uv.lock` | Retain reviewed setup bytes; no further dependency change |
| `tests/unit/tools/test_mypy_ratchet.py` (new) | Git/base selection, closed configuration contract, history/index controls and gate-wiring tests |
| `tests/fixtures/typing/mypy-bootstrap.json` (new) | Byte-for-byte accepted C1 candidate JSON, immutable initial approval anchor |
| `src/optimus/telemetry/events.py` | Sixteen explicit `trace_id=run_id` arguments only |
| `src/optimus/guardrails/ci_parity.py` | Add `"mypy"` to the existing `GuardrailRuleSet.phase1()` name set; reuse existing parity checks |
| `tests/unit/telemetry/test_events.py` | All-factory correlation and direct-construction runtime invariants |
| `.pre-commit-config.yaml` | All-source Mypy hook; existing pytest hook continues to run the policy gate |
| `.github/workflows/guardrails.yml` | All-source native Linux and Windows-target Mypy steps; keep full history checkout |
| `tests/profiles.toml` | Classify new synthetic subprocess/history tests as `proc`; actual policy and wiring guards as `gates` |
| `docs/superpowers/plans/hardening-static-type-checking-implementation.md` (new filing) | Approved self-contained plan, including approval/review receipts |
| `docs/superpowers/plans/hardening-runtime-quality-masterplan.md` | Register bounded typing child and existing issue custody |
| `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | Issue-only pointer for the live work, without a second status register |
| `docs/README.md` | Index the registered plan |
| `reports/static-typing-baseline-2026-10-16*` | Retain all nine existing baseline reports/candidates, including v2; do not rewrite |
| `reports/static-typing-port-verification.md` (new) | Pre-commit focused/checkpoint receipts and source/config hashes; explicitly leave final full results pending. Final post-commit evidence/review is a separate private successor and issue receipt, not an edit to the measured tree |

## Accepted data and comparison contract

The initial 46-module list is the `modules` array of `reports/static-typing-baseline-2026-10-16-exceptions.candidate_v2.json`, SHA-256 `b6a756129365762efe42c77593313507fd1be1a039a85ef4ebc22490194c5bab`. Copy its bytes unchanged to the bootstrap fixture; its historical wording remains provenance, and this approved plan supplies the installation authority. The fixture's `source_head` is the source pin above. Do not transcribe a second tuple.

Accepted setup hashes: `pyproject.toml` `ab0840ae87dbe9e16311f1ebd0662a78553e8b009e9f65bb5502f57e1b829d91`; `uv.lock` `b3669ad80c64effed108e0a90a33ba00a92814435153b85059889bae6790eb46`. Installing source exceptions changes the former, never retroactively these baseline identities. Baseline report v2 is `567f8da4f06564eff6f2c62e706719c9f134a60411f1135af266faceea82eb27`.

**Candidate bytes:** check the current working `pyproject.toml`, and independently check its staged blob against the same baseline when different. Use the existing `tools.tracked_repository_files.index_environment(root)` to honor `TEST_RUN_COMMIT_INDEX_FILE` / `TEST_RUN_COMMIT_INDEX_ROOT` inside profile subprocesses; a directly invoked hook also honors `GIT_INDEX_FILE`. Missing named index, missing config blob or invalid TOML fails closed. Stage the declared candidate configuration before expecting the actual guard to pass; the pre-setup index is not an alternative bootstrap candidate. Synthetic repository fixtures must not inherit another repository's index environment.

**Accepted baseline:** local/pre-commit uses resolved `HEAD`. PR CI reads `GITHUB_EVENT_PATH`, resolves the actual target `pull_request.base.sha` and compares against `git merge-base HEAD <base.sha>`; require the target identity to be present and the checkout to contain that target (normal merge checkout). Main push CI uses event `before`, the actual previous main; a regular merge's first parent must agree. Other push shapes use that same prior-main identity, never an intermediate candidate commit. All-zero, absent, unresolvable or non-ancestor identities fail closed. Unsupported CI events fail closed; no CI fallback to local mode. Print context and resolved immutable SHA on every real guard run. Local comparison does not retroactively prove an already committed HEAD was approved; CI and delivery review provide that history boundary.

**Bootstrap:** allow a baseline without Mypy configuration only when the fixture's `source_head` is an ancestor of or equal to the resolved baseline (`git merge-base --is-ancestor <source_head> <baseline>`), and that baseline Git version contains no Mypy configuration. Candidate source exceptions must be a subset of the fixture's 46 modules. A sibling/unrelated baseline fails even if its config is absent. The digest is a one-time reviewed data anchor, not a manually bumped comparison SHA. Once the accepted baseline has Mypy configuration, compare with that baseline's exact module set only; the fixture grants nothing. Deleting configuration from a candidate always fails the shape check. Changing the anchor or re-baselining requires new operator approval and Claude review; no in-band reset switch.

**Configuration shape:** `_source_exceptions(config_bytes: bytes) -> frozenset[str]` validates the entire Mypy section before returning exceptions. Accept only the three global values fixed above, the exact third-party import override, and zero or one exact source-exception group with `ignore_errors = true`. Reject unknown global/override keys, duplicates, package globs and third-party names in the source list. The caller also rejects nonexistent source modules, resolving candidate entries against the candidate tree and baseline entries against the baseline Git tree. Validate baseline policy shapes too; absence is allowed only by the bootstrap rule. This rejects alternate suppression mechanisms, not just list growth.

**Comparison:** `_resolve_baseline(repo: Path, environ: Mapping[str, str]) -> str` resolves history; `_assert_ratchet(candidate: bytes, baseline: bytes, *, bootstrap_modules: frozenset[str] | None = None) -> None` rejects growth and malformed configuration with actionable failures. Helpers live inside the test module and have no production API. The caller alone supplies bootstrap modules after identity and digest checks. Baseline read/identity errors are failures, not an empty set or SKIP.

## Task 1: Install the ratchet and initial measured exceptions

**Files:** `pyproject.toml`, new policy-test module and bootstrap fixture, `tests/profiles.toml`. Consumes accepted data above; produces the actual guard `test_repository_mypy_exception_ratchet` and its parser/resolver helpers for Task 3.

- [ ] Refresh HEAD, status, registered worktrees and active file ownership with Claude; preserve unrelated changes. Stop for source drift or unresolved overlap.
- [ ] Write named synthetic controls in the one test module: `test_exception_sets_only_shrink` (same/subset pass, new module fails); `test_removed_exception_cannot_return` (accepted A+B, then accepted A, then attempted B fails); `test_configuration_cannot_widen_scope` (each prohibited global/override mechanism fails); `test_bootstrap_is_exact_and_one_time` (46/subset pass at the pinned pre-config base and a descendant base still without configuration; sibling/non-descendant base, digest drift, candidate configuration deletion and reintroduction against an accepted 45-module configuration fail); `test_baseline_contexts_fail_closed` (local HEAD, PR target merge-base, regular merge, multi-commit push, and all invalid identities/events); `test_staged_growth_is_not_hidden` (staged growth fails despite a reduced working file, including the profile-runner alternate index); `test_new_module_is_checked` (real Mypy child rejects an ill-typed clean/new temporary source module with the production configuration).
- [ ] Run `uv run --no-sync pytest --no-cov tests/unit/tools/test_mypy_ratchet.py`. Record the expected initial failure for the absent helpers/guard; do not call an unrelated failure RED evidence.
- [ ] Implement only the test-local parser, baseline resolution, bootstrap and candidate handling described above. Use real temporary Git repositories for history controls and synthetic source for the Mypy control; no real source mutation or repo commit for a negative test.
- [ ] Copy and hash-check the accepted fixture, install all 46 exact source exceptions, and implement `test_repository_mypy_exception_ratchet`. Classify synthetic controls as `proc` and the actual repository guard as `gates`. Stage only declared candidate files for index-aware verification; inspect the staged diff without committing. Do not classify all controls as always-on gates.
- [ ] Rerun the focused module and `uv run --no-sync python -m mypy --config-file pyproject.toml`. Expected: policy controls pass; masked Mypy succeeds while 46 modules remain explicitly reported debt. Run the whole-diff checkpoint command in Task 3 and obtain Claude's bounded ratchet review before Task 2. Preserve this intermediate config identity, without creating a project commit.

## Task 2: Close telemetry and reduce the exception set to 45

**Files:** `src/optimus/telemetry/events.py`, its existing test file, `pyproject.toml`. Consumes Task 1's gate; produces a telemetry-clean source module with no exception.

- [ ] Add `test_all_factory_trace_ids_match_run_id`, parametrized over the 16 factories below using valid existing test inputs; assert the model and serialized `trace_id` equal `run_id`. Add `test_direct_trace_id_is_preserved_and_missing_trace_defaults`: an explicit different trace survives, an omitted trace defaults to run ID, and invalid missing correlation input still raises validation error. Preserve existing redaction and exact settlement-field tests.
- [ ] Run `uv run --no-sync pytest --no-cov tests/unit/telemetry/test_events.py`. These runtime invariants can pass before the fix because the existing validator already works; do not invent a runtime regression. The accepted 16 `call-arg` diagnostics supply the static failure evidence. Remove only the telemetry exception temporarily and run Mypy to reproduce those same 16 diagnostics before the fix; retain output and config hash.
- [ ] Add `trace_id=run_id` to each `cls(...)` construction in `model_call`, `gateway_usage`, `reconciliation`, `pricing_fallback`, `tool_call`, `guardrail_audit`, `error`, `retry_decision`, `fitness_gate`, `golden_task`, `release_gate`, `goal_loop`, `agent_run`, `skill_invocation`, `skill_selection` and `acp_turn_settlement`. No signature, validator or payload change.
- [ ] Leave telemetry out of the exception group permanently and refresh the declared staged candidate for index-aware verification. Rerun the focused telemetry tests, policy module and standard all-source Mypy command. Require all to pass, exactly 45 remaining exceptions, and all 16 factories covered. Claude records the bounded #328 real-model review; do not claim the entire test-double track complete.

## Task 3: Wire enforcement, register the plan and verify the whole batch

**Files:** guardrail parity, hook/CI/profile files, documentation and verification report from the file table. Consumes `test_repository_mypy_exception_ratchet` and telemetry closure. Produces an independently reviewed batch verified at one local commit, awaiting publication authority.

- [ ] Add `test_mypy_gate_wiring` in the policy module: assert one always-run local hook `optimus-mypy`, name `optimus-check: mypy`, `language: system`, `pass_filenames: false`, exact entry `python -m mypy --config-file pyproject.toml`; assert the existing always-run commit-profile pytest hook still selects the repository ratchet and wiring guards as `gates`. Assert two CI steps named `optimus-check: mypy` and `optimus-check: mypy-win32`, full-history checkout, and exact commands `uv run --no-sync python -m mypy --config-file pyproject.toml` and the same plus `--platform win32`. Classify this current-tree wiring test as `gates`.
- [ ] Run the policy module to observe wiring failures, then modify only the declared hook/CI/profile files and add `"mypy"` to `GuardrailRuleSet.phase1().check_names` through its existing factory literal. Existing parity tests then require the Mypy name on both hook and CI sides; the exact wiring test requires both CI commands, since name-substring parity alone cannot distinguish the Windows-target step. No separate wiring-mutant suite or second policy hook.
- [ ] Register this plan at its canonical repository path, with repository-relative evidence links instead of private planning dependencies; retain the contract, approval and review hashes. Update only the named masterplan/index/backlog pointers. Record issue #329 as live authority; no duplicate progress narrative and no claim of parent-track closure.
- [ ] Run focused tests and checks: `uv run --no-sync pytest --no-cov tests/unit/tools/test_mypy_ratchet.py tests/unit/telemetry/test_events.py tests/unit/guardrails/test_ci_parity.py tests/unit/tools/test_test_profiles.py tests/unit/docs/test_open_work_pool_hygiene.py`; `uv run --no-sync ruff check .`; `uv run --no-sync pre-commit run optimus-mypy --all-files`; and the two CI Mypy command forms above. Zero exit is expected; record failures without expanding scope.
- [ ] At Task 1 and after integration run `uv run --no-sync python -m tools.testing.run_profile --profile checkpoint --base c5ea5a1673b957f1e2dd3a09321c6a34ff293880`. Require a valid passing whole-diff checkpoint. Before any later authorized commit use the repository's ordinary commit profile/hooks; do not bypass them. Avoid repeated full suites between these meaningful checkpoints.
- [ ] After the focused checks and integration checkpoint pass, have Claude review the complete pre-commit diff and bounded #328 receipt. If this plan's explicit local-commit decision is approved, create exactly one unpushed implementation commit using the normal hooks and the lane environment (`uv run --no-sync git commit -m "feat: gate source typing and close telemetry cohort"`). No `--no-verify`. Record the SHA and tree. If approval excludes this commit, stop before the final full pair and return that gate; do not substitute a dirty full run.
- [ ] Immediately rerun `uv run --no-sync pytest --no-cov tests/unit/docs/test_open_work_pool_hygiene.py` at that commit, so new-plan prerequisites/index/registry rules selected by Git history actually execute. A failure holds final verification and further commits; preserve the attempt for a bounded correction decision.
- [ ] Make a Git bundle of the committed lane and its reachable history, then create a new native Linux verification clone from it under `/root/optimus-verification/static-typing-port-20261016`, with its own `.venv` and frozen dev sync. Do not reuse or change another agent's checkout. Require matching committed SHA, tree and source/config/lock hashes, and clean tracked status before and after runs on both hosts. No staged-byte transfer or global `GIT_DIR`; Linux Git owns its clone normally. Preserve the bundle as local provenance, outside tracked product files.
- [ ] Capture fresh unmasked Windows and real WSL diagnostics using a derived temporary config that removes only the source `ignore_errors` group, retaining the accepted pins and third-party policy. Compare diagnostic identities to accepted v2: require telemetry's 16 cleared, no new diagnostics, and explicit retained/cleared/new listings, including the two known registry override diagnostics as retained debt. Predicted totals 215 Windows / 206 WSL are hypotheses, not acceptance claims. Explain any other delta before proceeding; do not change other cohorts to chase totals. Run both standard masked command forms on the committed Windows tree and Linux clone as well.
- [ ] Run final native Windows, then separate WSL verification serially, from the matching committed trees: `uv run --no-sync python tools/check_product_coverage.py --run-full-suite --groups tools/product-coverage-groups.json --report-json tmp/coverage/product-coverage-report.json --coverage-json tmp/coverage/coverage.json`, then `uv run --no-sync python -m tools.testing.coverage_products validate --coverage-json tmp/coverage/coverage.json --gate-report tmp/coverage/product-coverage-report.json`. Preserve run records, coverage data, current product floors, safety-critical non-regression and exactly-one eligibility qualifications. If required prior-source coverage evidence is unavailable or mismatched, report that comparison UNKNOWN and hold acceptance rather than inventing a baseline.
- [ ] Have Claude inspect the committed diff, source/config hashes, ratchet adversarial controls, diagnostics delta, product coverage/validity and #328 receipt. Record ACCEPT/OBJECT points on #329 and in a successor verification report kept outside the pinned tracked tree; any later repository filing is separately authorized so the measured commit stays unchanged. For failures preserve evidence and propose the smallest correction/re-run before another commit. Return concise results and any held gate to the operator; do not publish, activate or clean up under this plan alone.

## Completion and stop conditions

Local technical completion requires: 45 exact exceptions; telemetry independently type-clean; working/index/history/bootstrap controls pass; hooks/CI select the same configuration; both actual platforms measured on the same local commit; runtime invariants and current coverage/validity requirements pass; no unexplained new diagnostic; Claude accepts the evidence. Publication and merge remain separate decisions.

Stop before expansion if the 16-line telemetry cohort is not independently sufficient, the bootstrap contract cannot be made fail-closed, source pin/ownership changes, or verification requires another product change. A newly landed module outside the frozen 46 that fails Mypy must make the gate fail, including on a valid descendant bootstrap base: review and re-measure the changed source rather than widening the fixture or ignoring that module. Record the concrete obstacle for Claude review and a revised operator decision. No implementation or verification result is claimed by this plan.
