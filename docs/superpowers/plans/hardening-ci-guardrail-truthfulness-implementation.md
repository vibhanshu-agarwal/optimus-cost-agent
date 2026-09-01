# CI Guardrail Truthfulness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

> **Custody:** The hardening runtime-quality masterplan owns this child plan's
> parent-level status; this plan owns only its task checkboxes and evidence gates.
> Promotion grants no blanket implementation authority. Task 0 has its separately
> recorded execution grant; Tasks 1-6 and every behavior-bearing commit retain their
> own review and operator gates.

**Goal:** Make four existing CI guardrails describe and enforce their real scope:
locked dependency synchronization, all-production-package coverage with a monotonic
path to 80%, repository-wide tracked-text secret scanning, and scheme-safe handling at
all three production `urlopen()` sites.

**Architecture:** Keep one detector configuration and one audited baseline for secret
scanning, with separate fail-closed venue inventories: pre-commit scans tracked text
outside `reports/`, while required CI scans all tracked text including `reports/`.
Coverage is a
compound gate: one run measures all five configured production packages, a
standard-library verifier preserves the existing 80% `optimus` floor, and accepted
transitional floors for the four newly measured packages and the aggregate may only
rise until all reach 80%. URL scheme policy stays at each existing ownership boundary;
this plan does not pre-empt the separately accepted domain-policy duplication work.

**Tech Stack:** Python 3.14, uv and `uv.lock`, GitHub Actions, pre-commit,
pytest/pytest-cov/coverage.py branch coverage, stdlib `json`, `tomllib`, `decimal`,
`pathlib`, `subprocess`, and `urllib.parse`, Bandit B310, detect-secrets, Ruff, and
pytest.

**Spec:** `docs/superpowers/plans/hardening-runtime-quality-masterplan.md`

## Custody boundary

This plan implements exactly these masterplan items:

- `HARDENING-ITEM-COVERAGE-SOURCE-SCOPE`;
- `HARDENING-ITEM-LOCKFILE-CI-ENFORCEMENT`;
- `HARDENING-ITEM-SECRET-SCAN-SCOPE`; and
- `HARDENING-ITEM-BANDIT-B310`.

It also records the accepted prerequisite repairs `C-CG2` through `C-CG9`: restore a
green full unit suite by classifying the Plan 11.26 digest-only logging-surface
overmatch, close the recurring C29 filesystem-walker class, drain rejected request
bodies before the Gateway 404, classify the complete sink inventory, install and
validate the two-venue secret-scan baseline, remove platform-dependent scanner drift,
declare the 37 binding-dependent tests as owner-attributed `UNRUN` only when their Git
object is unavailable, and require both CI jobs on `main`. These are child-plan
prerequisites and evidence, not second backlog features or new masterplan status rows.

It does not implement dependency CVE scanning, Dependabot, actionlint, zizmor, Ruff
rule widening, Ruff formatting, Mypy, audit-tool typing, general URL-policy
consolidation, or any Plan 11.26 runtime candidate. The consolidated backlog owns this
masterplan's feature state; the masterplan owns this child plan's state; this plan owns
only its task checkboxes. This document contains no plan-level status declaration.

## First-production-change disclosure (C-CG1 and C-CG4)

Plan 11.26 proved an empty `src/` diff at each of its eight gates. This child plan is
the first approved retirement of that invariant. The replacement is narrower and must
be stated honestly: from anchor commit `3eff64b`, every gate must prove that any
`src/` diff is a subset of exactly these four files:

- `src/optimus/gateway/client.py`;
- `src/optimus_gateway/upstream_client.py`; and
- `src/optimus/acp/local_infra.py`; and
- `src/optimus_gateway/server.py`.

The C-CG1 production grant permits only rejection of disallowed URL schemes before the
existing `urlopen()` calls in the first three files so B310 can be enabled. The C-CG4
grant permitted only draining the request body before the existing unavailable-route
404 in `src/optimus_gateway/server.py`; that three-line fix is accepted at `e3c52f1`
and does not widen Task 5 authority. Neither grant covers new host, userinfo, path,
port, normalization, retry, timeout, exception-selection, or refactoring. Existing
loopback and provider-boundary checks remain in force but are not widened by this
child.

At every gate, the worker records `git diff --name-only 3eff64b...HEAD -- src` and
reviews `git diff 3eff64b...HEAD --` for the four allowed files. The name set must be a
subset of the allowlist. A production hunk must be either the accepted C-CG4 drain or
scheme validation and its adjacent reviewed B310 rationale. A `# nosec B310` without
the local validator, negative scheme test, and written rationale fails the gate. The
C-CG1 scope grant still does not authorize Task 5 to start or authorize its commit;
those remain separate operator decisions.

## Prerequisites

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|---|
| Governance | `HARDENING-FEAT-RUNTIME-QUALITY` and `HARDENING-TRACK-CI-GUARDRAILS` exist in their promoted authorities | yes | consolidated backlog and hardening masterplan | satisfied; no disposition required |
| Scope | The four item identities above remain assigned only to this child filename | yes | hardening masterplan | satisfied; stop on any conflicting successor or duplicate custody |
| Review | An independent reviewer accepts this complete child plan | yes | reviewer | satisfied; review checkpoints C-CG1 through C-CG9 are accepted, while later task gates remain independent |
| Promotion | A promotion-only change creates the tracked child plan, changes the parent row from plain inline code to a valid relative link, and records the operator-authorized pickup | yes | masterplan owner and operator | satisfied by the paired parent-owned promotion; task checkboxes remain open for reviewer closure |
| Measurement execution | The operator explicitly authorizes review-time Task 0 evidence collection without tracked-file changes | yes | operator | satisfied; evidence remains provisional until it is rerun at the promoted `Active` pickup |
| Production authority | Production edits are limited to the accepted C-CG4 request-body drain and disallowed-scheme rejection before `urlopen()` in the three C-CG1 files | yes | operator | C-CG4 is accepted at `e3c52f1`; C-CG1 remains only a file-and-meaning scope grant and does not authorize Task 5 execution |
| Task and commit execution | The operator separately authorizes each behavior-bearing task and each commit | yes | operator | C-CG2 through C-CG9 and Task 0 measurement have bounded grants only; Tasks 1-6, Task 5 production execution, their commits, merge, and live rows remain unauthorized |
| C-CG2 repair | The checked-in full unit suite passes after the logging-manifest and tracked-file-walker regressions are repaired | yes | prerequisite repair worker and reviewer | accepted in `6dd5a54`; subsequent local and CI full-suite gates are green |
| Baseline | A clean all-five-package coverage run completes and its exact branch-aware totals are reviewer-accepted | yes | Task 0 worker and reviewer | accepted provisional values are `optimus 86.53`, `optimus_gateway 87.82`, `optimus_security 96.95`, `evidence_handoff 78.44`, `evidence_handoff_runtime 57.39`, and aggregate `82.18`; Task 0 freezes them only after the post-promotion rerun |
| Lock | `uv lock --check` succeeds at the pickup commit | yes | repository dependency owner | satisfied at draft time; re-run at every pickup |
| Secret scope | The all-tracked-text scan completes within the accepted CI time budget and has no unaudited finding | yes | Task 0 worker and security reviewer | 863 exact baseline entries are dispositioned with zero wildcard exclusions; local excludes only `reports/`, CI includes it, and Linux CI is green |
| Required CI | Both merge-gating contexts execute on every pull request and are required on `main` | yes | repository administrator | branch protection independently reads back `clean-environment-recheck` and `verify`, `strict: false`, with no path filter or review lockout |
| Security | The B310 inventory still contains exactly the three production sites named below | yes | Task 0 worker and security reviewer | satisfied at draft time; any added or removed site requires a reviewed plan amendment |
| Live systems | Redis, Zed, Gateway/provider calls, paid calls, OS credentials, and evidence promotion are unnecessary | yes | plan boundary | satisfied; this plan is offline-only |

## Global constraints

- Follow TDD for every behavior or executable guard: write the failing test, run it and
  confirm the intended failure, implement the minimum change, then rerun green.
- Stop after every task evidence bundle. The reviewer must accept that task and the
  operator must separately authorize its commit before the next task begins.
- Every review gate, including C-CG2 and Tasks 0-6, runs
  `uv run --frozen pytest tests/unit -q` with no node-id, module, package, or keyword
  selector. The gate report states the full pass/fail/skip counts and exact command.
  Focused tests may run first for diagnosis, but never substitute for this command.
- A review-time Task 0 run may collect provisional evidence only because the operator
  authorized it explicitly. It changes no tracked file, closes no checkbox, and does
  not satisfy parent-state prerequisites. Before Task 0 evidence is accepted as the
  frozen implementation baseline, the masterplan owner records the separately
  authorized pickup and the worker reruns every Task 0 command against that tree. If
  an external gate blocks progress, only the parent owner changes the parent row;
  this child plan never edits or self-declares its own parent-owned state.
- Before every task commit run the task's focused tests, Ruff on changed Python,
  `git diff --check`, and `git status --short`. Stage only the files named by that task.
- Never reduce `[tool.coverage.report] fail_under = 80`, remove branch coverage, or
  replace the existing `optimus` 80% floor with a lower aggregate floor.
- Coverage percentages use coverage.py's branch-aware denominator:
  `(covered_lines + covered_branches) / (num_statements + num_branches) * 100`.
  Floors use decimal arithmetic and are rounded down to two decimal places. Float
  comparison is forbidden.
- The production coverage universe remains exactly the five paths already declared in
  `[tool.coverage.run].source`: `src/optimus`, `src/optimus_gateway`,
  `src/optimus_security`, `src/evidence_handoff`, and
  `src/evidence_handoff_runtime`. `src/optimus_cost_agent.egg-info` is packaging
  metadata, not a sixth production package.
- The 80% target applies to aggregate production coverage. During transition,
  `optimus` remains at or above 80% and every newly visible package plus the aggregate
  receives an accepted nondecreasing floor derived from the clean Task 0 baseline.
  This track cannot close until the aggregate reaches 80%.
- The coverage policy verifier has no `--write`, `--update`, `--accept-current`, or
  baseline-generation mode. A measured result can never authorize its own floor.
- CI supplies the PR base SHA (or push-event `before` SHA) as
  `COVERAGE_POLICY_BASE_REF`. The verifier reads the previous policy with
  `git show BASE_COMMIT_SHA:tools/coverage-policy.toml` using an argument vector, then rejects
  any decreased package or aggregate floor. Local pre-commit has no trusted base ref
  and therefore verifies current coverage only; CI owns the cross-revision ratchet.
- CI and pre-commit call the same coverage runner. Secret scanning uses the same
  detector command and audited baseline through two hook identities: the local hook
  excludes only `reports/`, while the required CI hook has no path exclusion. A check
  name alone is not parity.
- Secret scanning covers every Git-tracked text file. Binary files are excluded
  structurally by `types: [text]`. The sole path exclusion is `^reports/` on the local
  hook because the measured reports-only runtime is 217.257 seconds; CI retains those
  216 files through a second manual-stage hook with no path exclusion. Tests assert
  both exact inventories and prove changing the local exclusion cannot alter CI.
- `.secrets.baseline` remains an audited exception ledger. Never accept a real secret,
  generated credential, or unexplained high-entropy value into it. Any proposed
  baseline entry blocks the task until the security reviewer dispositions it.
- Re-enable B310 globally by removing only `B310` from `[tool.bandit].skips`. Preserve
  the existing dispositions of B101, B105, B404, and B603.
- Each production `urlopen()` site must have a local supported-scheme proof before a
  site-local `# nosec B310` rationale. A suppression without the adjacent negative
  test is forbidden.
- Gateway-to-provider traffic requires the `https` scheme. The local
  Optimus-to-Gateway and Phoenix-health paths permit only the `http` and `https`
  schemes. `file`, `ftp`, and schemeless values fail before `urlopen`. Existing host
  policy is preserved but is outside this plan's production-change authority.
- Do not introduce a new shared URL-policy module in this plan. The accepted
  `T13-CAND-DOMAIN-HTTPS` work owns later consolidation; this task adds only the local
  proof needed to make B310 truthful now.
- No task may change product protocol schemas, retry behavior, timeouts, provider
  selection, authorization semantics, telemetry, dependencies, or `uv.lock`.
- No task may push, open a PR, merge, delete worktrees/branches, or rewrite history.
- The ignored reviewer checkpoint log is
  `docs/superpowers/reviews/hardening-ci-guardrail-truthfulness-review-checkpoints.md`.
  Read it first at every pickup and never stage it.

## File responsibility map

| File | Responsibility in this plan |
|---|---|
| `.github/workflows/guardrails.yml` | CI's authoritative invocations: locked sync, shared secret scan, and shared coverage runner |
| `.pre-commit-config.yaml` | Local invocation parity for secret scanning and coverage |
| `docs/superpowers/reviews/hardening-secret-scan-dispositions.json` | Reviewed category counts, all 28 Basic Auth findings, and all 10 production false-positive dispositions |
| `pyproject.toml` | Existing five-package source universe, branch setting, 80% target, and Bandit skip removal |
| `tools/coverage-policy.toml` | Reviewed package/aggregate floors and immutable 80% target; data only |
| `tools/verify_coverage_policy.py` | Pure parser and fail-closed coverage-policy verifier; never writes policy |
| `tools/run_coverage_guardrail.py` | Cross-platform owner of the single full-suite coverage command and temporary data paths |
| `tools/tracked_repository_files.py` | Fail-closed Git-index enumeration shared by repository-truth scanners; no filesystem fallback for a real repository |
| `tests/unit/tools/test_tracked_repository_files.py` | Two-sided tracked/untracked/ignored/pathspec behavior for the shared enumerator |
| `tests/unit/guardrails/test_tracked_file_scanners.py` | Reviewed inventory of recursive filesystem walkers; rejects any unclassified repository-tree walker |
| `tests/unit/tools/test_verify_coverage_policy.py` | Hand-derived policy arithmetic, malformed-input, package-universe, and threshold tests |
| `tests/unit/tools/test_run_coverage_guardrail.py` | Runner command, temporary-file, failure propagation, and verifier sequencing tests |
| `tests/unit/guardrails/test_ci_parity.py` | Declarative CI/pre-commit invocation contracts and real detect-secrets canaries |
| `tests/unit/test_credit_surface_retirement.py` | Tracked-only active-surface retirement scan; ignored dependency trees cannot affect local-only results |
| `tools/verify_plan996_logging_surfaces.py` | Tracked-only source/tool discovery for the logging-surface manifest |
| `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json` | Registers the Plan 11.26 digest-only JSON serialization as safe by construction |
| `tests/conftest.py` | Object-conditional collection hook for the exact binding-dependent test manifest |
| `tests/plan1126_unrun_binding.json` | Exact 37-node `P11.26-UNRUN-BINDING` scope with `P11-FEAT-ZED-RESUME` custody |
| `tools/plan1126_unrun_binding.py` | Fail-closed manifest validation, Git-object predicate, skip reason, and non-verification summary |
| `tests/unit/tools/test_plan1126_unrun_binding.py` | Count, identity, mutation, two-sided predicate, attribution, and no-laundering contracts |
| `src/optimus_gateway/server.py` | Accepted C-CG4 request-body drain before the unavailable-route 404; no further change owned here |
| `src/optimus/gateway/client.py` | Existing local Optimus-to-Gateway URL boundary and B310 site at `UrllibGatewayTransport.post_json` |
| `src/optimus_gateway/upstream_client.py` | HTTPS validation at the provider-client construction boundary and B310 site in `_urlopen_json` |
| `src/optimus/acp/local_infra.py` | Loopback HTTP(S) validation for Phoenix health and its B310 site |
| `tests/unit/gateway/test_client.py` | Local Gateway scheme/host rejection before transport I/O |
| `tests/unit/optimus_gateway/test_upstream_retry.py` | Provider-base scheme rejection without altering retry behavior |
| `tests/unit/acp/test_local_infra.py` | Phoenix disallowed-scheme rejection before the existing health request |
| `reports/hardening-ci-guardrail-truthfulness-release.md` | Sanitized final command evidence, accepted floors, timings, and remaining gap to 80% |

### Prerequisite Task C-CG2: Restore full-suite truth before Task 0

Task 0 cannot freeze a baseline until this prerequisite is independently reviewed,
separately authorized, committed, and followed by a green full `tests/unit` run. This
task changes no `src/` file.

**Files:**

- Create: `tools/tracked_repository_files.py`
- Create: `tests/unit/tools/test_tracked_repository_files.py`
- Create: `tests/unit/guardrails/test_tracked_file_scanners.py`
- Modify: `tests/unit/test_credit_surface_retirement.py`
- Modify: `tools/verify_plan996_logging_surfaces.py`
- Modify: `tests/unit/tools/test_verify_plan996_logging_surfaces.py`
- Modify: `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json`
- Modify: `tests/unit/acp/test_plan1126_cancellation.py`
- Modify tracked-source scanners found by the measured sweep:
  `tests/unit/docs/test_plan_directory_hygiene.py`,
  `tests/unit/evidence/test_collector_boundaries.py`,
  `tests/unit/evidence/test_import_boundaries.py`,
  `tests/unit/evidence/test_naming_boundaries.py`,
  `tests/unit/evidence_handoff/test_lifecycle.py`,
  `tests/unit/evidence_handoff/test_migration_manifest.py`,
  `tests/unit/acp/test_launch_policy.py`,
  `tests/unit/acp/test_error_code_registry.py`,
  `tests/unit/acp/test_outbound_writer.py`, and
  `tests/unit/tools/test_evidence_gather.py`
- Modify: `tools/run_plan1126_runtime_audit.py`
- Test: `tests/unit/tools/plan1126_runtime_audit/test_render.py`

**Interfaces:**

- Produces:
  `tracked_repository_files(project_root: Path, *, pathspecs: Sequence[str]) -> tuple[Path, ...]`
- Contract: invoke `git ls-files -z -- <pathspecs>` with `cwd=project_root`, an
  argument vector, `shell=False`, and a checked exit. Reject absolute or parent-
  traversing pathspecs. Return sorted, repository-relative tracked regular-file paths
  resolved beneath `project_root`. A missing Git repository, failed Git command,
  undecodable result, escaping path, or tracked-but-missing file fails closed; there
  is no filesystem-walk fallback for repository truth.
- Consumes: callers filter the returned tracked paths by suffix or owning subtree;
  callers never add ignored or untracked filesystem entries back into the inventory.

- [ ] **Step 1: Reproduce both inherited failures without changing files**

Run:

```text
uv run --frozen pytest tests/unit/test_credit_surface_retirement.py::test_no_legacy_provider_balance_identifiers_remain_in_active_surfaces -q
uv run --frozen pytest tests/unit/tools/test_verify_plan996_logging_surfaces.py::test_checked_in_manifest_covers_current_surface_inventory -q
```

Expected: the first reports identifiers from ignored
`tests/fixtures/plan1126_runtime_audit/typescript-client/node_modules/zod`; the second
reports exactly
`UNCLASSIFIED_SINK: tools.plan1126_runtime_audit.cancellation:_canonical_digest:json_serialization`.
If either identity differs, stop and amend the plan from the new evidence.

- [ ] **Step 2: Write RED tests for tracked-file enumeration**

In a temporary Git repository, test all of these two-sided cases:

1. a committed file under each requested pathspec is returned;
2. an untracked file and a `.gitignore`-ignored `node_modules/zod/index.d.ts` are absent;
3. `git add -f` of that same ignored file makes it present;
4. a file outside the requested pathspec is absent;
5. absolute and `..` pathspecs fail;
6. a non-Git directory and a mocked nonzero Git exit fail; and
7. a tracked path deleted from the working tree fails instead of silently narrowing
   the scan.

Run the new test module before implementation. Expected: import/contract failure.

- [ ] **Step 3: Implement the minimum shared tracked-file enumerator**

Create only the interface above. Decode the NUL-delimited result explicitly, normalize
separators to POSIX repository-relative names, prove every resolved path remains under
`project_root`, and return deterministic sorted paths. Do not add an option that
includes `--others`, bypasses Git, or accepts a caller-supplied fallback inventory.

- [ ] **Step 4: Close the measured C29 class, not only the Zod instance**

Replace repository-truth `rglob()`/`glob()` scans in the files listed above with the
shared tracked inventory. Preserve each existing subtree and suffix scope.
For `tools/run_plan1126_runtime_audit._path_fingerprint`, paths inside the repository
must expand through the tracked inventory; explicitly supplied directories outside the
repository remain byte-fingerprinted as complete throwaway harness trees.

Add an AST inventory test over tracked Python under `tests/unit` and `tools`. Its stable
keys are `relative module:function:walker:pattern`, not line numbers. Every `Path.glob`,
`Path.rglob`, `glob.glob`, `glob.iglob`, or `os.walk` call must be either:

- absent because repository truth now uses `tracked_repository_files`; or
- present in an exact reviewed rationale map for a temporary, evidence-output,
  quarantine, staging, shadow-workspace, or explicitly non-Git throwaway tree.

The deliberate Plan-root `glob("*.md")` checks in
`test_plan_directory_hygiene.py` remain separately rationalized because C-MP1 must see
an untracked child-plan file and fail before it can be committed. Any new or
unclassified recursive walker fails the inventory test.

- [ ] **Step 5: Register the digest-only surface instead of excluding audit tooling**

Add exactly this manifest classification:

```text
key: tools.plan1126_runtime_audit.cancellation:_canonical_digest:json_serialization
policy: safe-by-construction
rationale: canonicalizes an in-memory, source-derived audit value solely to compute
           SHA-256; the encoded JSON bytes are not persisted, logged, or exported by
           this helper
sanitizer: schema-limited functional path or AST overmatch; no raw diagnostic retention
test_node: tests/unit/acp/test_plan1126_cancellation.py::test_canonical_digest_is_deterministic_and_content_only
evidence_tier: unit
```

The named test proves reordered mappings have one lowercase 64-hex digest, a changed
value changes the digest, and the helper returns only the digest. Do not scope
`tools/plan1126_runtime_audit` out of discovery: the existing manifest already governs
tool sinks, and a package exclusion would hide future real writes or exports.

- [ ] **Step 6: Run focused GREEN and the walker mutation proof**

Run the helper tests, scanner-inventory tests, the two previously failing nodes, the
logging-surface verifier module, the cancellation digest test, and the offline harness
fingerprint tests. Then create an ignored Zod-like canary only inside a temporary Git
fixture: it must be invisible before `git add -f` and visible afterwards. Never create
the canary in the shared worktree.

- [ ] **Step 7: Run the mandatory full unit gate**

Run:

```text
uv run --frozen pytest tests/unit -q
```

Expected: exit zero with no failed or error count. Record the full pass/skip counts and
duration in the ignored checkpoint log. A focused selector is supplementary evidence
only. Also prove `git diff --name-only 3eff64b...HEAD -- src` is empty.

- [ ] **Step 8: Review and separately authorized prerequisite commit**

The reviewer checks the complete walker inventory and every exception rationale, the
manifest classification, full-suite output, tracked file list, and empty `src/` diff.
After explicit commit authorization, stage only the C-CG2 files and commit with:

```text
test: align repository scanners with tracked files
```

Stop after the commit. Task 0 remains blocked until the reviewer accepts the committed
tree and separately authorizes its post-repair baseline run.

### Task 0: Freeze pickup baselines without changing tracked files

Task 0 changes no tracked file and has no commit. It establishes the exact inputs that
the later coverage and secret-scan tasks consume. The review-time measurements remain
provisional: leave all Task 0 checkboxes open until the reviewer accepts the complete
post-promotion rerun. The frozen rerun requires the accepted prerequisite commits, a
green full `tests/unit` gate, both required CI contexts green, and the parent-owned
pickup recorded in the masterplan.

- [ ] **Step 1: Prove branch, authority, and scope before measurement**

Run:

```text
git status --short
git rev-parse HEAD
git branch --show-current
uv lock --check
rg -n "HARDENING-TRACK-CI-GUARDRAILS|HARDENING-ITEM-(COVERAGE-SOURCE-SCOPE|LOCKFILE-CI-ENFORCEMENT|SECRET-SCAN-SCOPE|BANDIT-B310)" docs/superpowers/plans/hardening-runtime-quality-masterplan.md
rg -n "urlopen" src/optimus src/optimus_gateway src/optimus_security src/evidence_handoff src/evidence_handoff_runtime
```

Expected at the promoted pickup: the parent row links this tracked child plan, the four
items occur only under this track, the lock is current, and production B310 scope is
exactly:

```text
src/optimus/gateway/client.py: UrllibGatewayTransport.post_json
src/optimus_gateway/upstream_client.py: _urlopen_json
src/optimus/acp/local_infra.py: _phoenix_health_ready
```

The parent-owned row must name Task 0 post-promotion baseline acceptance as its next
gate. The child plan contains no plan-level status declaration of its own.

- [ ] **Step 2: Prove the full unit suite is green, then measure coverage on a green suite**

Run from a clean worktree:

```text
uv run --frozen pytest tests/unit -q
uv run --frozen pytest --cov --cov-branch --cov-report=term-missing --cov-report=json:.coverage.guardrails-baseline.json --cov-fail-under=0 -q
```

Expected: both commands exit zero with no failed or error count. Record the complete
unit-suite pass/skip counts and duration. The coverage JSON contains files beneath all
five configured source paths. A coverage percentage from a process with any test
failure is rejected even when the JSON is readable. A timeout, interruption, missing
package, partial progress bar, or red suite is not a baseline and blocks the coverage
tasks.

- [ ] **Step 3: Derive floors independently and record them only in the ignored checkpoint**

For each package and the aggregate, compute the branch-aware percentage with
`Decimal`, then round down to two decimal places. The accepted initial floors are:

- exactly `80.00` for `src/optimus`;
- the rounded-down observed percentage for each of the other four packages; and
- the rounded-down observed five-package aggregate.

If `src/optimus` is below `80.00`, stop: the existing gate is already red and this
plan cannot preserve it by policy alone. If the aggregate is already at least
`80.00`, set every aggregate target/floor to `80.00`; do not create unnecessary
transition machinery.

- [ ] **Step 4: Measure all-tracked-text secret scanning after removing duplicate `src` input in a temporary copy**

Copy `.pre-commit-config.yaml` to an isolated temporary directory, remove the trailing
`src` positional argument from only the `optimus-secret-scan` entry, and run that
temporary configuration with `--all-files`. Record elapsed time, selected file count,
and finding count. Do not edit or stage the repository configuration in Task 0.

Expected: zero unaudited findings. A finding blocks Task 2 for security disposition.
The reviewer must also accept the measured time budget before Task 2 begins.

- [ ] **Step 5: Obtain reviewer acceptance of the Task 0 checkpoint**

Record the pickup commit, exact full-unit and coverage-run test counts, confirmation
that both runs were green, five package totals, aggregate total, derived floors,
secret-scan duration/scope, the three B310 sites, and `uv lock --check` result in the
ignored checkpoint. The reviewer reruns `uv run --frozen pytest tests/unit -q` rather
than a selector before accepting the baseline. Stop. There is no Task 0 commit.

### Task 1: Make dependency synchronization fail on lock drift

**Files:**

- Modify: `.github/workflows/guardrails.yml` (`Install dependencies` step)
- Modify: `tests/unit/guardrails/test_ci_parity.py`

**Interfaces:**

- Consumes: the existing `uv.lock` and `pyproject.toml`
- Produces: the exact CI argv `uv sync --locked --all-extras`

- [ ] **Step 1: Add the failing workflow contract test**

Parse the workflow with `yaml.safe_load`, locate the unique step named
`Install dependencies`, and assert its tokenized command is exactly:

```python
assert shlex.split(step["run"]) == ["uv", "sync", "--locked", "--all-extras"]
```

Also assert there is exactly one dependency-install step so a second permissive sync
cannot coexist with the locked one.

- [ ] **Step 2: Run RED**

Run:

```text
uv run --frozen pytest tests/unit/guardrails/test_ci_parity.py::test_ci_dependency_sync_is_locked -v
```

Expected: FAIL because `--locked` is absent.

- [ ] **Step 3: Apply the minimum workflow change**

Change only the command to:

```yaml
- name: Install dependencies
  run: uv sync --locked --all-extras
```

- [ ] **Step 4: Verify green and the real current lock**

Run:

```text
uv run --frozen pytest tests/unit/guardrails/test_ci_parity.py -q
uv lock --check
uv sync --locked --all-extras
uv run --frozen pre-commit run check-yaml --files .github/workflows/guardrails.yml
git diff --check
```

Expected: all commands exit zero and neither `pyproject.toml` nor `uv.lock` changes.

- [ ] **Step 5: Review and separately authorized commit**

Run `uv run --frozen pytest tests/unit -q` and state its full pass/skip counts and
duration in the gate report; the focused output above cannot substitute for it. Relay
that output, the RED/GREEN evidence, and `git diff --stat` to the reviewer. After
acceptance and explicit commit authorization, stage only the two Task 1 files and
commit with:

```text
ci: require locked dependency sync
```

Stop after the commit.

### Task 2: Scan tracked text through venue-specific, fail-closed secret hooks

**Files:**

- Modify: `.pre-commit-config.yaml` (`optimus-secret-scan` hook)
- Modify: `.github/workflows/guardrails.yml` (`optimus-check: secret-scan` step)
- Modify: `tests/unit/guardrails/test_ci_parity.py`
- Modify only after explicit security disposition: `.secrets.baseline`
- Create: `docs/superpowers/reviews/hardening-secret-scan-dispositions.json`

**Interfaces:**

- Consumes: pre-commit's Git-tracked `types: [text]` file selection and the single
  audited `.secrets.baseline`
- Produces: local hook `optimus-secret-scan`, excluding only `^reports/`; manual-stage
  hook `optimus-secret-scan-ci`, with no path exclusion; and required CI invocation
  `uv run pre-commit run optimus-secret-scan-ci --all-files --hook-stage manual`

- [ ] **Step 1: Add failing configuration-contract tests**

Assert the local hook removes the positional `src`, retains `types: [text]` and
filename passing, and excludes exactly `^reports/`. Assert the CI-only hook uses the
same detector entry and baseline, retains `types: [text]` and filename passing, has no
`files` or `exclude` key, and is limited to the manual stage.

Assert the unique CI secret step is required and exactly:

```python
assert shlex.split(step["run"]) == [
    "uv",
    "run",
    "pre-commit",
    "run",
    "optimus-secret-scan-ci",
    "--all-files",
    "--hook-stage",
    "manual",
]
assert step.get("continue-on-error", False) is False
assert "if" not in step
```

- [ ] **Step 2: Add real canary tests outside `src`**

Parameterize temporary paths representing `docs/guide.md`,
`tests/fixture.txt`, `.github/workflows/probe.yml`, and `pyproject.toml`. Build an AWS
canary at runtime so the complete token is not present in the test source:

```python
canary = "AKIA" + "ABCDEFGHIJKLMNOP"
candidate.write_text(f"credential={canary}\n", encoding="utf-8")
hook = shutil.which("detect-secrets-hook")
assert hook is not None
result = subprocess.run(
    [
        hook,
        "--baseline",
        str(REPO_ROOT / ".secrets.baseline"),
        str(candidate),
    ],
    check=False,
    capture_output=True,
    text=True,
)
assert result.returncode != 0
```

Do not mock the detector. Add a reports-only canary case that passes the local hook and
fails the CI hook. Mutate the local hook exclusion in the temporary repository and
prove the CI result is unchanged.

- [ ] **Step 3: Run RED**

Run the configuration, exact-inventory, degradation-mutation, and real-canary tests.
Expected: direct detector canaries already fail, while configuration tests fail because
the CI-only hook does not exist and the current hook/CI command are still `src`-scoped.

- [ ] **Step 4: Install the two venue inventories over one detector baseline**

Set the hook entry to:

```yaml
entry: detect-secrets-hook --baseline .secrets.baseline
language: system
types: [text]
exclude: ^reports/
```

Add a second `optimus-secret-scan-ci` hook with the same entry and type filter, no path
exclusion, and `stages: [manual]`. Set CI to:

```yaml
- name: "optimus-check: secret-scan"
  run: uv run pre-commit run optimus-secret-scan-ci --all-files --hook-stage manual
```

Do not add `pass_filenames: false`, a CI `files`/`exclude` key, `continue-on-error`, or
a conditional skip.

- [ ] **Step 5: Run the complete scope and enforce the accepted time budget**

Run:

```text
uv run --frozen pytest tests/unit/guardrails/test_ci_parity.py -q
uv run --frozen pre-commit run optimus-secret-scan-ci --all-files --hook-stage manual
uv run --frozen pre-commit run check-yaml --files .pre-commit-config.yaml .github/workflows/guardrails.yml
git diff --check
```

Expected: zero unaudited findings, CI selects every tracked text file, the local hook
selects exactly tracked text outside `reports/`, and runtime stays within the accepted
venue budgets. The baseline contains exact findings only, with zero wildcard file
exclusions. The disposition ledger reconciles all 863 entries, gives distinct reasons
for the five area categories, individually reviews all 28 Basic Auth findings, and
individually records all 10 production false positives.

- [ ] **Step 6: Review and separately authorized commit**

Run `uv run --frozen pytest tests/unit -q` and state its full pass/skip counts and
duration in the gate report. After reviewer acceptance and explicit commit
authorization, stage only Task 2 files and commit with:

```text
ci: scan all tracked text for secrets
```

Stop after the commit.

### Task 3: Create a fail-closed five-package coverage policy verifier

**Files:**

- Create: `tools/coverage-policy.toml`
- Create: `tools/verify_coverage_policy.py`
- Create: `tests/unit/tools/test_verify_coverage_policy.py`

**Interfaces:**

- Consumes: coverage.py JSON with branch totals and the reviewer-accepted Task 0 floors
- Produces:
  `verify(*, coverage_payload: Mapping[str, object], policy_payload: Mapping[str, object], previous_policy_payload: Mapping[str, object] | None) -> CoverageSummary`
  and CLI `--coverage-json PATH --policy PATH`; the optional trusted Git base comes
  only from validated `COVERAGE_POLICY_BASE_REF`
- Does not produce or mutate a policy file

- [ ] **Step 1: Write hand-derived failing tests for the policy model**

Use literal JSON/TOML fixtures and cover these cases independently:

1. exactly five package paths plus aggregate at their floors passes;
2. one package below its floor fails and names that package;
3. aggregate below its floor fails;
4. missing or unexpected production package fails;
5. a policy with `optimus < 80.00` fails before reading coverage;
6. a policy target other than `80.00` fails;
7. branch totals contribute to the percentage; and
8. malformed, negative, boolean-as-integer, zero-denominator, or non-finite values
   fail;
9. lowering any package or aggregate floor relative to a previous policy fails; and
10. raising floors or leaving them unchanged passes.

The arithmetic fixture must be independently derived, for example:

```python
# (80 covered lines + 8 covered branches) / (100 statements + 10 branches)
assert summary.packages["optimus"].percent == Decimal("80.00")
```

- [ ] **Step 2: Run RED**

Run:

```text
uv run --frozen pytest tests/unit/tools/test_verify_coverage_policy.py -q
```

Expected: collection fails because the verifier module does not exist.

- [ ] **Step 3: Implement the minimum pure verifier**

Use frozen dataclasses and these exact authorities:

```python
REQUIRED_PACKAGES = {
    "optimus": "src/optimus/",
    "optimus_gateway": "src/optimus_gateway/",
    "optimus_security": "src/optimus_security/",
    "evidence_handoff": "src/evidence_handoff/",
    "evidence_handoff_runtime": "src/evidence_handoff_runtime/",
}
TARGET_PERCENT = Decimal("80.00")


def covered_percent(*, covered_lines: int, covered_branches: int,
                    statements: int, branches: int) -> Decimal:
    numerator = Decimal(covered_lines + covered_branches)
    denominator = Decimal(statements + branches)
    if denominator <= 0:
        raise ValueError("coverage denominator must be positive")
    return (numerator * Decimal(100) / denominator).quantize(
        Decimal("0.01"), rounding=ROUND_DOWN
    )
```

Normalize coverage JSON file paths to POSIX form before prefix classification. Reject
files under an unknown `src/` package. Reject duplicate package entries, missing
coverage fields, booleans where integers are required, and policies that omit any
required key. When `COVERAGE_POLICY_BASE_REF` is set, require exactly 40 lowercase hex
characters and load the prior policy with
`subprocess.run(["git", "show", f"{ref}:tools/coverage-policy.toml"], ...)`; never
pass the ref through a shell. A missing prior file is allowed only for the first commit
that introduces the policy. Any other Git failure or any decreased floor fails closed.
Print a concise per-package and aggregate table on success; print errors to stderr and
exit nonzero on any violation.

- [ ] **Step 4: Create the reviewed policy data**

`tools/coverage-policy.toml` has schema version `1`, target `80.00`, an aggregate
floor, and one floor for every exact package name above. Set `optimus` to `80.00`.
Set the other four and aggregate floors to the reviewer-accepted, rounded-down Task 0
values. The file also records the Task 0 anchor commit and coverage.py version as
provenance strings. Do not copy values from an interrupted run.

- [ ] **Step 5: Verify GREEN and mutation behavior**

Run the focused suite, then mutate a temporary policy copy by lowering `optimus` to
`79.99`, omitting one package, and raising one floor above the fixture result. Each
mutation must exit nonzero. Restore nothing in the repository because mutations occur
only in `tmp_path`.

- [ ] **Step 6: Review and separately authorized commit**

Run `uv run --frozen pytest tests/unit -q` and state its full pass/skip counts and
duration in the gate report. After reviewer acceptance of the exact floors and tests,
stage only the three Task 3 files and commit with:

```text
test: define five-package coverage ratchet
```

Stop after the commit.

### Task 4: Route CI and pre-commit through one coverage runner

**Files:**

- Create: `tools/run_coverage_guardrail.py`
- Create: `tests/unit/tools/test_run_coverage_guardrail.py`
- Modify: `.github/workflows/guardrails.yml`
- Modify: `.pre-commit-config.yaml`
- Modify: `tests/unit/guardrails/test_ci_parity.py`
- Verify unchanged: `pyproject.toml`

**Interfaces:**

- Consumes: `tools/coverage-policy.toml`, `tools/verify_coverage_policy.py`, the full
  offline pytest suite, and `[tool.coverage.run].source`
- Produces: CLI `python tools/run_coverage_guardrail.py` with no scope-narrowing flags
  and a process exit code equal to the first failing phase

- [ ] **Step 1: Write failing runner tests**

The slow pytest subprocess is the external boundary; inject a narrow command runner
into a pure `run_guardrail()` orchestration function. Assert that it:

- creates coverage data and JSON paths beneath a temporary directory;
- invokes `sys.executable -m pytest` with `--cov` but never `--cov=optimus`;
- includes branch coverage and the JSON report;
- passes `--cov-fail-under=0` only for collection, then invokes the policy verifier;
- forwards `COVERAGE_POLICY_BASE_REF` as data to the verifier process without shell
  interpolation when CI supplies it;
- never invokes the verifier when pytest fails;
- returns the verifier's nonzero result unchanged; and
- cleans its temporary directory on success, pytest failure, verifier failure, and
  `KeyboardInterrupt`.

Do not assert merely that a mock was called; assert the exact argv and observable exit
code for each phase.

- [ ] **Step 2: Write failing CI/pre-commit parity tests**

Assert both surfaces use the same command:

```text
uv run --frozen python tools/run_coverage_guardrail.py
```

Assert neither config contains `--cov=optimus` and `[tool.coverage.report]` remains
`fail_under = 80` with `[tool.coverage.run] branch = true` and the exact five sources.

- [ ] **Step 3: Run RED**

Run both new test files. Expected: runner import failure and current config assertions
failing on the narrow `--cov=optimus` command.

- [ ] **Step 4: Implement the cross-platform runner**

The runner creates a `TemporaryDirectory`, sets `COVERAGE_FILE` only in the child
environment, and runs:

```text
python -m pytest --cov --cov-branch --cov-report=term-missing --cov-report=json:COVERAGE_JSON_PATH --cov-fail-under=0 -q
python tools/verify_coverage_policy.py --coverage-json COVERAGE_JSON_PATH --policy tools/coverage-policy.toml
```

`COVERAGE_JSON_PATH` above is the concrete path created by `TemporaryDirectory` for
that invocation; it is passed as one argument, not interpolated through a shell.

It does not accept user-supplied pytest arguments, package names, thresholds, or
output paths. Preserve Ctrl-C semantics (exit 130) and do not catch or relabel test
failures as coverage failures.

- [ ] **Step 5: Replace both narrow invocations**

Use the shared runner in the existing `optimus-check: pytest-coverage` CI step and
pre-commit hook. Keep the check name unchanged so existing phase-one rule-set parity
continues to hold. Set CI's `COVERAGE_POLICY_BASE_REF` from
`${{ github.event.pull_request.base.sha || github.event.before }}`; leave it unset in
pre-commit. The executable command remains identical on both surfaces.

- [ ] **Step 6: Verify focused behavior, then run the real compound gate**

Run:

```text
uv run --frozen pytest tests/unit/tools/test_verify_coverage_policy.py tests/unit/tools/test_run_coverage_guardrail.py tests/unit/guardrails/test_ci_parity.py -q
uv run --frozen python tools/run_coverage_guardrail.py
uv run --frozen ruff check tools/verify_coverage_policy.py tools/run_coverage_guardrail.py tests/unit/tools/test_verify_coverage_policy.py tests/unit/tools/test_run_coverage_guardrail.py tests/unit/guardrails/test_ci_parity.py
git diff --check
```

Expected: all five packages appear, `optimus >= 80.00`, every accepted floor holds,
and the aggregate gap to `80.00` is printed honestly. If the gate is too slow for the
Task 0 budget, optimize only duplicate invocation or file handling; do not narrow
package or test scope.

- [ ] **Step 7: Review and separately authorized commit**

Run `uv run --frozen pytest tests/unit -q` and state its full pass/skip counts and
duration in the gate report. After reviewer acceptance and explicit commit
authorization, stage only Task 4 files and commit with:

```text
ci: enforce five-package coverage policy
```

Stop after the commit.

## Coverage closure gate before Task 6

Task 6 may start only when the real compound gate reports a five-package aggregate of
at least `80.00`. If Task 4 installs honest transitional floors below that value, the
masterplan owner keeps this child nonterminal and the plan author prepares
`hardening-ci-guardrail-truthfulness-implementation_v2.md`. That reviewed successor
must name the exact below-floor modules, missing branches, test files, and bounded
coverage tranches derived from the accepted Task 4 report. No executor may invent
open-ended “add tests until green” work from this document, and the parent cannot mark
this child `Complete` merely because the truthful ratchet is installed.

### Task 5: Re-enable B310 with local scheme proofs at all three sites

**Files:**

- Modify: `pyproject.toml`
- Modify: `src/optimus/gateway/client.py`
- Modify: `src/optimus_gateway/upstream_client.py`
- Modify: `src/optimus/acp/local_infra.py`
- Modify: `tests/unit/gateway/test_client.py`
- Modify: `tests/unit/optimus_gateway/test_upstream_retry.py`
- Modify: `tests/unit/acp/test_local_infra.py`
- Modify: `tests/unit/guardrails/test_ci_parity.py`

**Interfaces:**

- Consumes: existing boundary validation, `UrllibOpenAICompatibleClient`
  construction, `_phoenix_health_ready`, and Bandit
- Produces: scheme rejection before every production `urlopen()` plus exactly three
  reviewed local `# nosec B310` rationales

- [ ] **Step 1: Add failing agent-to-Gateway tests**

Add a parameterized test proving `file://`, `ftp://`, and schemeless
`GatewayRequest.url` values are rejected by `UrllibGatewayTransport.post_json` before
the monkeypatched `urlopen` is called. Existing HTTP and HTTPS requests retain their
current behavior; do not add host or userinfo rejection in this task.

- [ ] **Step 2: Add failing provider-base tests**

Construct `UrllibOpenAICompatibleClient` with `file://`, `ftp://`, `http://`, and
schemeless base URLs. Each must raise `ValueError` at construction.
`https://openrouter.ai/api/v1` remains accepted, and existing retry tests must observe
unchanged attempt counts and exception types. Do not add host or userinfo rejection.

- [ ] **Step 3: Add failing Phoenix-health tests**

Call `_phoenix_health_ready` with `file://`, `ftp://`, and schemeless URLs. Each
returns `False` without calling the monkeypatched `urllib.request.urlopen`. Existing
HTTP(S) behavior remains unchanged; do not widen host or userinfo policy here.

- [ ] **Step 4: Run RED**

Run the new tests individually. Expected: each unsafe direct-boundary case currently
reaches the `urlopen` double or constructs successfully, demonstrating the missing
local proof.

- [ ] **Step 5: Add the minimum local validators**

- In `UrllibGatewayTransport.post_json`, parse `request.url` and require the `http` or
  `https` scheme before constructing/opening the request. Raise `ValueError` before
  I/O for any other or missing scheme.
- In `UrllibOpenAICompatibleClient.__init__`, require the `https` scheme before
  storing the existing stripped base URL. Do not add normalization or change retry
  code.
- In `_phoenix_health_ready`, require the `http` or `https` scheme and return `False`
  before I/O for any other or missing scheme.

Use local private helpers in the owning modules. Do not create a shared URL-policy
module or alter tool-provider URL policy.

- [ ] **Step 6: Add exactly three local Bandit dispositions and enable B310**

Each guarded `urlopen` line receives `# nosec B310` with a short adjacent comment
naming its local validator and negative test. Remove only `B310` from:

```toml
skips = ["B101", "B105", "B404", "B603"]
```

Add a guardrail test that parses this list and asserts B310 is absent while those four
existing skips remain exactly present. Add an AST/text inventory assertion that the
three production `urlopen` sites are the only B310 suppressions and every one contains
the local rationale marker.

- [ ] **Step 7: Verify Bandit and behavior**

Run:

```text
uv run --frozen pytest tests/unit/gateway/test_client.py tests/unit/optimus_gateway/test_upstream_retry.py tests/unit/acp/test_local_infra.py tests/unit/guardrails/test_ci_parity.py -q
uv run --frozen bandit -q -r src -c pyproject.toml
uv run --frozen ruff check src/optimus/gateway/client.py src/optimus_gateway/upstream_client.py src/optimus/acp/local_infra.py tests/unit/gateway/test_client.py tests/unit/optimus_gateway/test_upstream_retry.py tests/unit/acp/test_local_infra.py tests/unit/guardrails/test_ci_parity.py
git diff --check
```

Expected: Bandit exits zero with B310 globally active, invalid schemes never reach
I/O, valid local/provider flows preserve their current results, and
`git diff --name-only 3eff64b...HEAD -- src` is a subset of the three-file C-CG1
allowlist. Review the production hunks and reject any change that is not scheme
validation or its adjacent B310 rationale.

- [ ] **Step 8: Review and separately authorized commit**

Run `uv run --frozen pytest tests/unit -q` and state its full pass/skip counts and
duration in the gate report. After security-review acceptance and explicit commit
authorization, stage only Task 5 files and commit with:

```text
security: enforce urlopen scheme boundaries
```

Stop after the commit.

### Task 6: Prove the promoted guardrails and publish terminal evidence

**Files:**

- Create: `reports/hardening-ci-guardrail-truthfulness-release.md`
- Modify only if evidence makes a statement false:
  `docs/superpowers/plans/hardening-runtime-quality-masterplan.md`

**Interfaces:**

- Consumes: Tasks 1-5 commits and their accepted checkpoints
- Produces: one sanitized release report; parent-owned status transition remains a
  separate reviewer/operator action

- [ ] **Step 1: Run the full offline guardrail surface**

Run:

```text
uv sync --locked --all-extras
uv run --frozen pre-commit run trailing-whitespace --all-files
uv run --frozen pre-commit run check-yaml --all-files
uv run --frozen pre-commit run check-toml --all-files
uv run --frozen pre-commit run check-added-large-files --all-files
uv run --frozen ruff check .
uv run --frozen bandit -q -r src -c pyproject.toml
uv run --frozen pre-commit run optimus-ast-grep --all-files
uv run --frozen python -m optimus.guardrails.prompt_injection
uv run --frozen pre-commit run optimus-secret-scan-ci --all-files --hook-stage manual
uv run --frozen python tools/run_coverage_guardrail.py
uv run --frozen pytest tests/unit/docs tests/unit/guardrails tests/unit/tools/test_verify_coverage_policy.py tests/unit/tools/test_run_coverage_guardrail.py -q
git diff --check
git status --short
```

Expected: every command exits zero. The coverage output names five packages and the
aggregate; secret scanning covers all tracked text; Bandit has B310 enabled; locked
sync changes neither dependency file.

- [ ] **Step 2: Run fail-closed mutations in temporary copies**

Prove at least these mutations exit nonzero:

1. remove `--locked` from a copied workflow and run its contract test fixture;
2. add a tracked-text canary outside `src` and run the secret hook;
3. lower `optimus` policy to `79.99`;
4. lower one floor relative to a temporary previous-policy fixture;
5. omit one coverage package;
6. provide coverage below one accepted floor; and
7. pass `file://` to each of the three URL boundaries.

Do not mutate tracked repository files for this step.

- [ ] **Step 3: Write the release report**

Record commit IDs, exact commands and exits, test counts, timings, five package
percentages, aggregate percentage and remaining gap to 80%, secret-scan selected-file
count, the four retained Bandit skip rationales, and all three B310 local proofs. Do
not include absolute user paths, environment values, credentials, raw canaries, or
full exception text.

- [ ] **Step 4: Reconcile masterplan truth without self-updating status**

Identify every statement in the prerequisites, usability table, and CI-guardrail row
made false by the accepted evidence. Prepare the exact parent-owned edits for the
masterplan owner. This child plan does not edit its own status row or declare itself
complete.

- [ ] **Step 5: Review and separately authorized evidence commit**

Run `uv run --frozen pytest tests/unit -q` and state its full pass/skip counts and
duration in the gate report. After reviewer acceptance and explicit commit
authorization, stage only the release report and any reviewer-approved truthfulness
edits. Commit with:

```text
docs: record CI guardrail truthfulness evidence
```

Stop. Because the coverage closure gate required at least `80.00` before Task 6, the
parent owner may then move the plan to `archive/`, link the release report, and set the
child row to `Complete` in a separate parent-owned changeset. Neither this child nor
the feature can close below the five-package 80% aggregate policy.

## Promotion control-plane gate

The operator-authorized promotion changeset must:

1. creates `docs/superpowers/plans/hardening-ci-guardrail-truthfulness-implementation.md`
   with the accepted bytes;
2. change the `HARDENING-TRACK-CI-GUARDRAILS` board cell from plain inline code to a
   relative link and record the separately authorized Task 0 pickup in the
   parent-owned state and next gate;
3. leaves all task checkboxes open;
4. uses `Master-plan impact: updated — HARDENING-TRACK-CI-GUARDRAILS`;
5. adds no consolidated-backlog registry row; and
6. runs the documentation hygiene suite and C-MP1 mutation before commit.

Promotion does not authorize Tasks 1-6, Task 5 production execution, a behavior-bearing
commit, merge, or a live row. The explicit Task 0 grant permits its post-promotion
rerun and reviewer closure only. If the reviewer requests changes, revise the tracked
child plan through the parent update checklist before any later task proceeds.

## Plan completion criteria

- The CI dependency install is exactly `uv sync --locked --all-extras`.
- CI scans all Git-tracked text, while pre-commit scans the same tracked-text inventory
  minus `reports/`; both use the same detector entry and audited baseline, with zero
  unaudited entries and tests proving the CI inventory is independent of the local
  exclusion.
- One coverage command measures all five configured production packages with branch
  coverage.
- The existing `optimus` 80% floor remains enforced; four new package floors and the
  aggregate floor are reviewer-accepted and nondecreasing; the measured aggregate is
  at least 80% before terminal evidence or parent closure.
- The policy verifier cannot write or accept its own baseline and fails on missing,
  unknown, malformed, below-floor, or cross-revision floor-decrease input.
- B310 is globally enabled, all three production sites have local scheme guards,
  exactly three narrow suppressions remain, and invalid schemes fail before I/O.
- The full offline guardrails, focused mutations, Ruff, documentation tests, diff
  hygiene, and release evidence pass at the accepted commits.
- No dependency, protocol, telemetry, live-service, push, PR, or merge authority was
  inferred from this plan.
