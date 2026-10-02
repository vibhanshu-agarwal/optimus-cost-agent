# Plan 11.28 — Parallel local test context implementation

Date: 2026-10-02. Filing derivative of the operator-approved v2 contract, with Codex's checkpoint A technical amendment. The consolidated backlog owns current execution state. This document does not change the sealed v1/v2 handoff files.

Operator approval was given in the direct answer: “Approve v2, including local commits and the narrow hook procedure.” The question explicitly covered Fable's dedicated main-based worktree/branch, local commits and temporary omission of only the coverage hook on preparatory commits, followed by an unskipped reference. Source: `2026-10-02-operator-approval-parallel-test-context-v2.md`, SHA-256 `0E58934511B4CE8B5901E620820987A4084BF97134B0FF34356296B0B5C011E4`, in the shared `optimus-handoff/plan-12-discovery` folder. Push, PR, merge and activation remain separate decisions.

**Goal:** Let Plan 12 and sandbox lanes run full default suites concurrently in different worktrees, with trustworthy run/process attribution, protected application state and bounded evidence.

**Architecture:** Selection-aware root conftest integration; native Windows job ownership/cleanup for default runs; unique artifacts; a metadata-only overlap registry; pytest-process root protection and per-child launch proofs; boundary-only sampling; passive non-default runs; weaker WSL/Linux fallback. See [the governing design](../specs/2026-10-02-plan-11-28-parallel-local-test-context-design.md).

## Checkpoint A amendment — 2026-10-02

This is a technical correction within the approved goal/budget, not new delivery authority. The review at local `0d6c38a6a779bf3504374c5e12c072d47657aa47` is on HOLD pending the checkpoint corrections and complete sealed evidence. Bounded Task 0/1 corrections and mechanical filing remain authorized within the remaining two-hour hands-on checkpoint budget; Tasks 2–6 await Codex's checkpoint acceptance. Do not start a full suite to satisfy this checkpoint.

- Default means the repository's approved baseline marker expression, not whatever `config.getini('addopts')` returns after overrides. An alternate config, `-o addopts` selecting live/e2e, or an unrecognized selector remains passive. Prove these with synthetic marker/collection probes; never launch a real live dependency as a negative control.
- Replace inherited-immediate-job parent discovery with identity-validated native process ancestry, explicitly labelled `validated_process_ancestry`. Windows venv redirectors introduce their own immediate jobs. Ancestry supplies only a relationship; own-job membership remains the ownership and cleanup authority. No foreign/parent job handle is opened.
- A failed snapshot/iteration/creation-time/liveness query is UNKNOWN unless there is positive evidence of termination or PID reuse. Do not return `none` merely because a native query failed. Validate the nearest registered ancestor's creation time and live state; distinguish a partial chain from a proven absent relationship.
- New record classifications must describe actual behavior. Enforce or sanitize the bounded allowlisted schema and untrusted string fields before persistence/summary; reserve the schema field. The current test that inspects one ordinary record does not prove this policy. Add negative synthetic payload/registry-ID and sensitive-string cases. Do not weaken the logging gate or merely relabel an unsafe sink.
- Freeze a representative proof-to-site map for each distinct reachable default child mechanism, including indirect helpers. The current 103-site AST scan is a candidate inventory, not a complete call graph or 103 passing isolation proofs. Refresh it for the new slice; Task 4 still owes each reachable site's proof. Unresolved unsafe sites block acceptance.
- Preserve all earlier focused failures, gate/environment failures and the failed MAIN-5 attempt. A failed integration run is not converted into passing acceptance by calling it a negative control. Retain source/command/runtime identity for each corrective run, and seal the actual finished evidence before a checkpoint PASS claim.

The full correction details and source lines are in `2026-10-02-codex-plan-11-28-checkpoint-a-ruling.md` in the shared handoff. The two-hour and twenty-hour limits, four-run final acceptance schedule and all publication boundaries are unchanged.

**Stack:** Existing locked Python/pytest toolchain, ctypes Windows APIs, standard-library JSON/filesystem helpers, existing security sanitization and logging-surface manifest. No new service, agent launcher or third-party process-inspection dependency.

**Implementer:** Fable 5.1 / Claude. **Architect and independent reviewer:** Codex. Proposed backlog owner: `P11-FEAT-ACP-RUNTIME-HARDENING`, test tooling. This plan does not execute or close the other items under that owner.

## Constraints and acceptance budget

- No lock, queue, machine-wide admission rule, foreign-process veto, CPU quota or demand that other lanes pause. Each supported coverage writer uses its own worktree.
- Active enrollment, kill-on-close and root isolation apply only to the recognized default selection, including its focused subsets. Non-default/live/e2e/investigation/collection-only runs get passive records, not a new job or root guard. Do not terminate their services or replace their real dependencies. Mixed or unrecognized selection is passive and cannot pass native-context acceptance.
- Preserve current coverage sources, floors and exclusions; pytest selection rules; Git environment immunity; existing launch-variable classification; guard fail-closed behavior; and closed evidence-redaction features.
- Do not change `tools/testing/run_main5_guarded_suite.ps1`, the MAIN-5 scoring/guard partition, the Linux workflow, product code, the Azure lane or Windows CI.
- No raw argv, environment dumps, credential values, raw exception repr or unbounded foreign-process census in records. Use existing sanitization policy and explicit schema/bounds.
- Prepare fixes and meaningful focused tests locally. Do not weaken repository gates or the logging scanner. Skips, deselections and UNRUN checks remain distinct from passes.
- Execution is bounded by the checkpoints below. Fable must receive the operator's approval in its own visible context. This draft is not authority to push, create a PR, merge, activate services or make paid calls.

## Prerequisites

| Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|
| Native job prototype and retained spike evidence | yes | Fable/Codex | Planning evidence only; original runtime INCOMPLETE and gate FAIL remain |
| Permanent test helper and complete child-launch proofs | no | Fable | Genuinely absent, buildable now within this plan; unsafe child sites block acceptance |
| Dedicated main-based branch/worktree and frozen runtime | yes | Fable | Approved and created at `e9d6be0`; local slice `0d6c38a`, subject to checkpoint A corrections |
| Local commits and temporary coverage-hook omission for preparatory commits | yes | Operator | Direct approval recorded above; preserve the narrow procedure and four-run schedule |
| Windows native API access and unchanged MAIN-5 kit/runtime | yes | Fable verifies | Available and demonstrated in focused checkpoint work; keep the pinned kit/runner. Native boundary corrections and full final acceptance are still owed |
| WSL2 Ubuntu and its Linux frozen environment | yes | Fable verifies | Available and executed in a native clone, including `ec02c8a`; its current receipt fails the prerequisites gate. Final candidate validation is still owed |
| Live services, provider credentials, GUI ceremony or paid calls | yes | Operator | Not required by this default-selection scope; no new authority requested |

## Selection and handle-lifetime contract

At configuration time, before collection/test execution, classify the effective marker selection against the repository's approved baseline default expression, independently of pytest's `-o`/alternate-config overrides. A recognized default expression with file or `-k` narrowing remains active; alternate marker expressions, collection-only and unrecognized/mixed requests remain passive. Freeze this conservative classifier at Task 0 and test it. A `--test-run-context=passive` option may deliberately request passive records; acceptance commands cannot use it. Do not infer permission for a live dependency from conftest discovery or from an overridden `addopts` calling itself the default.

Bootstrap imports must be side-effect-free; do not install the new guard unconditionally on module import. Verify that existing imports before configuration do not use real application state. Install default-mode protection before test collection; a setup fixture alone cannot protect collection-time writes. Existing MAIN-5 protection stays intact in every mode.

A process already enrolled by a default session cannot detach from its job. Repeated default sessions reuse its retained native handle, with separately labelled session records/accounting deltas. A subsequent live/passive session in that same interpreter must be refused before collection and instructed to use an independent interpreter outside the job. Standalone live pytest remains passive. A passive child of an active default run still inherits the parent's ownership and cleanup: record that inheritance, do not promise detach or persistence. Existing collection-only and synthetic unit children must remain supported and receive their per-site safety proofs. Default-run child contracts must not launch persistent live services; such a discovered site blocks acceptance. Prove selection/repeated-session boundaries with synthetic collection sentinels, not real live tests. This is a process-lifetime safety restriction, not a scheduling lock or queue.

## Files and proposed interfaces

Use the following small test-only modules, or an equivalent split approved at checkpoint A:

| File | Responsibility |
|---|---|
| `tests/conftest.py` | Early install, pytest hooks/fixtures; preserve existing hooks and semantics |
| `tools/testing/run_context.py` | Run lifecycle, per-test phase records, overlap correlation and terminal summary |
| `tools/testing/run_context_windows.py` | Native job enrollment, PID/creation identity, accounting and explicit query errors |
| `tools/testing/run_context_records.py` | Bounded sanitized schema, atomic metadata registry, evidence writers |
| `tools/testing/run_context_guard.py` | Default test-root isolation/refusal and audited protected-root write boundary |
| `tests/unit/tools/test_run_context*.py` | Lifecycle, native/fallback, child/overlap, protection and record-policy proofs |
| `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json` | Classify every actual new sink and cite its behavioral policy proof |

No product imports should run before protection that is intended to cover them. Make initialization idempotent for repeated discovery, and explicitly handle a second pytest session in the same interpreter. Do not create a second destructive job or close the original one while that interpreter remains alive.

Proposed lifecycle API: `start_run(config) -> RunContext`, `record_phase(context, report)`, `sample_run(context)`, and `finish_run(context, exit_status)`. `finish_run` writes the terminal checkpoint but retains the native owner handle until interpreter exit. Native query methods return a success value or an explicit error state, never fabricated zeros.

### Record contract

Versioned schema `test-run-context-v1`; unique run ID; optional verified parent run ID; worktree path; HEAD and cleanliness before/after; branch/declared agent; platform and capability flags; interpreter/pytest/plugin versions and lock hash; normalized selection/config hashes; private output paths; monotonic and UTC event times; root PID/creation time; job name/flags; native accounting; overlap metadata; exit and evidence-completeness status.

Per-test records retain setup/call/teardown outcomes, duration, selected/deselected identity, skipped identity/reason, and active phase windows. Keep an exact SHA-256 identity of the raw pytest node ID alongside a sanitized display label; identical display sanitization must not collapse different parameterized cases. Apply bounded sanitization to reasons and labels. Never substitute positional dot/skip strings for independently retained identities.

Process observations contain PID plus creation time and native membership. Temporal association is `observed_during`, not a proven launch-parent or causal assertion. Account for missed short-lived observations and reconcile final live members. Aggregate native counters include terminated children; do not add nested totals to their parent totals. If an abrupt root exit prevents terminal output, the surviving record is PARTIAL until the outside verifier supplies bounded independent evidence.

Registry entries use unique atomically written files under a local temporary registry root outside protected application folders. Validate bounded field schema, root PID/creation time and live state through process handles before using another run's metadata. Confirm ownership/exclusion through this run's own job only; a registered foreign root is not proof of its entire tree. Never open a foreign/parent job. Identify the nearest registered parent relationship through a native process ancestry walk with creation-time validation at every hop and explicit iteration/query failure states. Label its method as ancestry, never job membership. Missing/ambiguous/query-failed evidence is UNKNOWN, not guessed. Registry data cannot grant kill/admission authority; malformed/stale entries cannot block another run. No automatic deletion of another run's evidence.

Context output is unique per run under the worktree's ignored `tmp/test-runs/<run-id>/` area, or an already-owned explicit artifact root. Capture caller-owned coverage/basetemp/cache paths without changing their contracts. Shared Git/uv/Node state and live service reads are declared environmental dependencies; this plan does not promise exhaustive I/O tracing.

## Task 0 — pin base and freeze bounded inputs (0.5 hour)

- [x] File/register the approved plan under the available main-based plan slot and existing parent, using the current docs rules. Keep this draft immutable in the handoff. Check for another registered local-context implementation before assigning a number.
- [x] Fable creates its own worktree from the then-current approved main revision. Proposed branch: `agent/claude/parallel-test-run-context`; use CONTRIBUTING's approved sibling-worktree path. Never modify another agent's worktree or reuse the Plan 12 implementation branch.
- [x] Record branch, complete HEAD, clean status, worktree inventory and frozen runtime. Use that worktree's `uv sync --frozen --extra dev` and its own interpreter. Verify imported modules come from it.
- [x] Refresh only resource-relevant changes since inventory head `4b79a30`, particularly tests, conftest, trusted roots, child launches and MAIN-5. Record retained controls/kit/runtime availability. Do not fetch or merge other agents' unpublished work as a side effect.
- [x] Freeze schema limits, selection classifier, child launch-site inventory, protected roots and the exact invocation forms below. Use `.venv\Scripts\python.exe -m pytest` for direct Windows calls. Check interpreter/pytest executable resolution for the unchanged hook. Freeze the checkpoint smoke command and unchanged MAIN-5 parameters. If prerequisites are unavailable, report UNRUN rather than substituting a different lane silently.

## Task 1 — early compatibility checkpoint A (1.5 hours; Tasks 0–1 together capped at two)

Build the smallest reviewable integration slice and focused tests before the broader recorder:

- [x] Root conftest automatically enrolls a recognized default native Windows run; read back flags/membership; preserve Git-environment hooks. Show direct and nested pytest complete without a wrapper, no context-created background thread, and no foreign/parent job open. Check live/e2e/investigation and collection-only requests remain passive; inventory their long-lived launches to verify this boundary, without executing live tests.
- [x] Exercise the unchanged MAIN-5 startup/process interception with the slice using a tiny test fixture or existing focused guard harness. Verify no guard is disabled, no new unclassified environment variable leaks into child launch policy, and explicit MAIN-5 artifact/coverage paths remain untouched.
- [x] Exercise actual WSL2 Ubuntu import/fallback behavior with a separate Linux environment. This one execution supplies both WSL and local Linux validation. If unavailable, record UNRUN; native-Windows simulation of Linux is not a substitute.
- [x] Verify pytest-process redirection, early real-adapter refusal and audited write denial for an omitted-fixture test, including nested pytest that discovers conftest. Preserve synthetic-root tests and MAIN-5's stronger refusal. For non-pytest children, freeze every reachable default-selection launch site and prove it receives explicit non-real product roots or cannot reach real-root resolution/writing. APPDATA/LOCALAPPDATA substitution alone is insufficient.
- [x] Test at least one representative child per distinct launch mechanism now and identify the remaining per-site proofs for Task 4. Record unsafe/unproven sites and their hardening owner; they block final parallel acceptance rather than being waived by filing. No startup injection, persistent venv installation, new launcher, MAIN-5 rewrite or OS sandbox is added.

**Checkpoint A handoff to Codex:** small diff, focused results, startup/enrollment order, child-protection coverage and any exclusions, unchanged runner hash, remaining work estimate. If the two-hour cap is reached without demonstrating the boundary, seal and stop before Tasks 2–6. A larger design needs an explicit revised scope/estimate. Do not bury it in the contingency.

## Task 2 — ownership and lifecycle (3.5 hours)

- [ ] Add meaningful failing tests for enrollment error, nested membership, handle inheritance, repeated pytest sessions, PID reuse/query denial and normal/abrupt root exit. Implement the native helper to satisfy them.
- [ ] Use a unique named job, non-inheritable retained handle, kill-on-close, no breakaway and no scheduling/resource limits. Existing outer jobs must be handled explicitly; assignment failure yields invalid native-context evidence, not an unannounced PID-tree fallback.
- [ ] Discover other registered roots through identity-validated process handles and test exclusion against the current job. For nesting, use the approved validated process ancestry relationship; do not query the inherited immediate job as though it identified a parent run. Never infer job ownership from ancestry or argv. Test parent exit while nested pytest is running: child cleanup must not be delayed by a context-held parent-job handle. Test absent/reused parent, access/query failure, snapshot/iteration failure and hop limit with explicit UNKNOWN behavior where evidence is incomplete.
- [ ] Provide accounting snapshots and sampled member identities. Signal/query failures are UNKNOWN. Membership enumeration races are represented and reconciled, not treated as clean exit.
- [ ] Build a focused outside-observer verifier for both exit modes. Hold identity-validated process handles, not a job handle across root exit. Kill only the deliberately planted test root. Verify its children terminate while a separate planted run continues. Never stop another agent's process.

## Task 3 — test context, overlap and evidence (4 hours)

- [ ] Add lifecycle and sanitization tests first, then the versioned bounded records and atomic per-run registry. Check corrupt/truncated records, stale PID reuse and concurrent publication by two runs.
- [ ] Preserve precise selected/skipped/deselected identities, phase results and independent control records. Exercise collection error, setup skip, teardown failure, Ctrl-C and abrupt termination; none may silently produce PASS/CLEAN.
- [ ] Record counters/overlap synchronously at test-phase boundaries, with startup/terminal checkpoints. No sampler thread, timer worker or observer process is created by the production helper. Append bounded partial records at those boundaries. A long/hung phase has no intervening sample: expose last-sample time and retain that diagnostic gap. Outside observers are limited to focused acceptance probes. Freeze byte/record ceilings; the estimated 15,000 phase appends are not an unlimited retention allowance.
- [ ] Emit a compact terminal summary giving record path, native capability/activation, job name/count where available, exit and completeness. Native process count greater than one is required in the planted child acceptance case, not in a child-free focused run.
- [ ] Keep Linux/WSL records and capability-labelled weaker process observation. Do not kill broad process groups or claim orphan-cleanup parity. Preserve original pytest exit failures; a recording error makes the context invalid and is visibly disclosed.

## Task 4 — complete default app-state protection (1.5 hours)

- [ ] Make the existing isolation fixture default only in active default-mode sessions, preserving explicit synthetic-root inputs. Apply the pytest-process refusal/protection boundary proven at checkpoint A before test collection. Passive live/non-default sessions keep their existing real-dependency contracts. Linux tests simulating Windows roots retain their contracts.
- [ ] Verify the actual protected locations through the OS-derived adapter and exact MAIN-5 root contract; do not trust environment claims. Keep context artifacts outside them.
- [ ] Prove omitted-fixture writes in pytest are denied before real modification and synthetic-root writes succeed. For every reachable default child launch site, link a behavioral test asserting effective non-real product roots or proven inability to reach real state; an assertion on launch arguments alone is insufficient if the child ignores them. Include negative sensitivity showing the proof fails when the isolation input is removed/misrouted, without writing to real state. Check real-root snapshots before/after acceptance.
- [ ] Do not add real keyring access or live-service contacts to implement the guard. Non-pytest children have proof-based separation, not a universal runtime guard; state this in records and final claims. If any launch is unsafe/unproven, retain its finding/owner and stop acceptance pending disposition. A small test-only fixture correction within these files is allowed; product/launcher changes need revised scope.

## Task 5 — logging policy and repository gates (2 hours)

- [ ] Discover every actual new logging/printing/JSON/file sink. Add exact manifest keys under the existing policy with tests proving sanitization, bounded retention and absence of raw payloads. Do not copy prototype sink counts as the final inventory.
- [ ] Stage only the approved files when the gates require tracked-file discovery. Execute the logging-surface gate and applicable gate-contract tests, plus Ruff, Bandit and secret/config/AST hooks at existing scopes. Record hook exclusions and no-file skips accurately; a skipped hook is not a scanned-file proof.
- [ ] Execute non-coverage hooks with temporary `SKIP=optimus-pytest-coverage`, restoring the prior value immediately afterward. The exact coverage hook is the reference acceptance run in Task 6, not a skipped gate. This targeted omission also applies to preparatory local commits only if the operator explicitly approves the procedure below. Never use --no-verify, alter hook config or claim all hooks passed during a skipped-coverage invocation. Run docs hygiene if filing changes backlog/masterplan projection; retain the future `Master-plan impact:` obligation.
- [ ] Report new versus pre-existing failures. No scanner, baseline, source scope, gate threshold or test-selection weakening is allowed. Necessary broader repairs go back to their owner.

## Task 6 — fixed acceptance and custody (4 hours hands-on)

Prepare two isolated validation worktrees at one final committed candidate identity once local commit authority is provided; no push is required. If only uncommitted validation is authorized, retain source-file hashes and label it provisional rather than exact-commit acceptance. The two validation checkouts have their own frozen environments and matching dependency/config identities.

Use `pre-commit run optimus-pytest-coverage --all-files` as the one reference full suite at the committed candidate, with SKIP cleared for that invocation. Capture its actual unchanged pytest flags and executable resolution. Then start two direct full default suites together using their own `.venv\Scripts\python.exe -m pytest` and those same hook flags: `--cov=optimus --cov-branch --cov-report=term-missing`. The reference retains independent node identities/reasons; it is not a claim that the entire host was uncontended. Disclose other registered activity without stopping it. Keep candidate/selection/config fixed.

Run one complete guarded MAIN-5 acceptance with its unchanged script and valid kit. During a bounded portion, run the independent protection/overlap probe from the other worktree. MAIN-5's partitioned counts/selection follow its own contract. This is **four full-suite-level executions** total: hook reference, concurrent A/B, guarded MAIN-5. Focused checks, including the checkpoint command smoke below, are additional. Allow approximately **2.5–3.5 hours of elapsed machine time**, separately from hands-on work; actual guarded overhead remains measured, not guaranteed.

| # | Acceptance check | Required evidence |
|---|---|---|
| 1 | Automatic entry points | Direct `.venv` pytest in the concurrent pair, actual unchanged coverage hook as reference, and the named CP1-style checkpoint-command smoke below emit records without a wrapper; preserve executable/selection provenance; smoke is focused and not a full CP1 rerun |
| 2 | Parallel full suites | Both selected-node identity sets, outcomes/counts and skipped identity/reason sets match the independent reference; no failures/incomplete phases; exact HEAD/lock/config equivalence and measured root-lifetime overlap; record coverage metrics without claiming deterministic coverage percentages |
| 3 | Ownership and overlap | Native positive membership for own planted processes; negative membership for the other run; independent run/agent/worktree provenance; no argv access; aggregate accounting distinguished from sampled history |
| 4 | Normal and abrupt cleanup | Outside observer uses identity-validated process handles; own planted descendants, including nested pytest, gone within five seconds of detected root exit with resolved queries; independent planted run continues; no foreign/parent job open anywhere |
| 5 | Gates and protected state | Actual sinks have behavioral manifest proofs; non-coverage gates and the reference coverage hook pass; pytest-process denial and every default child launch proof pass; snapshots show no test-origin real-state writes; no context sampler thread |
| 6 | Existing lanes | Full unchanged MAIN-5 satisfies its original contract; actual WSL2 Ubuntu execution supplies local Linux/fallback evidence; conservative passive selection and repeated-session protections pass; no Windows-native parity or remote CI-success claim |

Do not hard-code historical `4922/38/111` counts at a new main-based candidate. Establish expected counts from its reference, including new context tests. This forward acceptance does not backfill the old spike's missing skip IDs.

**No automatic favorable full-suite rerun.** If acceptance differs, retain the failed evidence and diagnose the named test with its context. Focused diagnostic reruns do not replace the failed original or grant full-suite PASS. Any additional full-suite acceptance attempt requires a reviewed bounded disposition. Missing Linux/WSL execution or a required kit means that criterion remains UNRUN; lack of push authority is not a reason to silently enable remote CI.

Seal selected node/outcome records, environment/source identity, run summaries, native observer records, gates, unchanged MAIN-5 script hash and before/after state. Hash the manifest and copy/verify every artifact to `optimus-handoff/plan-12-discovery/<approved-plan>-acceptance/` before cleanup. Retain failure and partial records alongside successful records; no raw secrets in the bundle. Codex independently checks the diff, artifacts and all six dispositions. Only then seek the separate delivery/publication decision if desired.

## Effort and stop rule

| Task | Planned hands-on hours |
|---|---:|
| 0–1: base and early compatibility | 2.0 |
| 2: native ownership/lifecycle | 3.5 |
| 3: context/records/overlap | 4.0 |
| 4: default app-state protection | 1.5 |
| 5: manifest and gates | 2.0 |
| 6: acceptance and custody | 4.0 |
| **Target** | **17.0** |
| **Target plus 15% contingency** | **19.6** |

Practical estimate: **13–20 hands-on hours**, excluding already completed research, independent reviewer time and waiting for operator decisions. Full-suite elapsed time is accounted for separately above; it is not additive hands-on work when unattended. No recurring VM expense. Beyond the two-hour checkpoint, stop before exceeding 20 hands-on hours unless a concrete revised scope/budget is approved. Optional ports/keyring fixes, exhaustive process-event tracing, same-worktree concurrent coverage, new launch infrastructure and broader runtime repairs are excluded.

Fable's reviewed working forecast is **17–20 hours**; retain 17 as the target. The checkpoint/ceiling bound authorized work and force early reporting; they do not guarantee that a failed prerequisite can be resolved within 15%.

## Local commit and four-run procedure

Operator approval must explicitly cover the dedicated branch/worktree, local implementation/filing commits, and **temporary SKIP of only optimus-pytest-coverage on preparatory local commits and non-coverage gate invocations**. All other applicable hooks remain enabled. Restore the original SKIP value on every exit path, even if empty versus absent. No persistent hook/config change or --no-verify is allowed.

This avoids an extra full suite during the commit that creates the final candidate. The coverage hook then runs once, unskipped, at that exact committed HEAD as the reference. Do not call the earlier local commit fully gated until this passes. After the reference starts, freeze the acceptance candidate: a corrective code/documentation commit creates a new candidate and requires a new reviewed acceptance disposition, rather than borrowing the old results. Keep acceptance evidence external/ignored and backed up so finishing evidence does not force another candidate commit.

If local commits or this narrow SKIP procedure are not approved, retain backed-up provisional evidence and return the exact-commit/four-run schedule for amendment. Do not silently exceed four full-suite-level runs or bypass a hook to meet the count.

## Independent review focus

Checkpoint A: correct startup boundary, child protection, early coverage-plugin interaction, MAIN-5 compatibility and a credible remaining estimate.

Final review: native ownership versus inference; handle lifetime and PID reuse; skipped-node/control provenance; protection in every supported default pytest lane and relevant child; sanitization/sink completeness; measured concurrent acceptance; explicit weaker fallback; immutable evidence custody. No claim that this work repairs ACP cancellation variance or proves a timing failure caused by load.

## Validation command templates

These are instructions for the approved implementing lane, not commands executed by Codex. Run from that lane's repository root. Record exit codes and keep each invocation separate. The implementer freezes concrete checkpoint-script and MAIN-5 kit paths at Task 0; no placeholder counts or substituted evidence are acceptable.

```powershell
uv sync --frozen --extra dev
.\.venv\Scripts\python.exe -m pytest tests/unit/tools -k run_context -q
.\.venv\Scripts\python.exe -m pytest tests/unit/tools/test_verify_plan996_logging_surfaces.py -q
.\.venv\Scripts\python.exe -m pre_commit run optimus-pytest-coverage --all-files
.\.venv\Scripts\python.exe -m pytest --cov=optimus --cov-branch --cov-report=term-missing
```

The fourth command is the single hook reference; use the fifth in each concurrent validation worktree. Pre-commit's unchanged entry is `pytest`, so first verify that its process PATH resolves pytest to the candidate `.venv` script. Use normal verified venv activation/tool PATH if necessary, restore it afterward, and record interpreter identity from inside the emitted context. Do not alter the hook entry or inject a guard/context propagation variable into children. Abort a shim/system-interpreter mismatch before running the reference.

For all other hooks, use `.\.venv\Scripts\python.exe -m pre_commit run --all-files` only within the temporary/restored `SKIP=optimus-pytest-coverage` procedure. This is explicitly a non-coverage gate invocation, not a fifth full-suite run.

Named **CP1-style checkpoint-command smoke** (focused; not CP1 acceptance and not a coverage-floor proof):

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/tools/test_plan1126_unrun_binding.py tests/unit/tools/test_git_env_immunity.py --cov --cov-branch --cov-report=term-missing --cov-fail-under=0
```

Its existing CP1-style flags exercise that entry form and the two nested pytest modules without another full suite. The unchanged coverage hook and MAIN-5 still enforce their original gate floors/source policies. Verify the selected modules match the pinned base before invocation; retain changed outcomes honestly.

For MAIN-5, use the existing PowerShell script's `-Mode Coverage -AttemptDirectory <unique owned attempt> -KitDirectory <verified kit> -DependencyPython <frozen interpreter> -PreCommitHome <isolated cache> -RequireClean` contract. These parameters are already present in the pinned script. Preserve its complete collection/scored/self-test behavior and original verdict. Early focused integration uses a supported focused target/harness, never a claim that the full guarded gate ran.

For WSL2 Ubuntu, create/use a Linux virtual environment separate from the Windows `.venv`, synchronize the frozen dev dependencies, and invoke its Python with `-m pytest` for context-focused and relevant unchanged conftest/launch/guardrail tests. Use uv's documented [project-environment selection](https://docs.astral.sh/uv/concepts/projects/config/#project-environment-path) to avoid replacing the Windows environment. Capture Linux/interpreter identity. This is actual local Linux validation; a remote GitHub verdict belongs to later authorized delivery.
