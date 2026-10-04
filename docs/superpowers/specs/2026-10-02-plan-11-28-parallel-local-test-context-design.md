# Plan 11.28 — Parallel local test context design

Date: 2026-10-02. Filing derivative of the operator-approved v2 design with Codex's checkpoint A technical amendment. Codex is architect/reviewer; Fable is the approved implementer. The consolidated backlog owns current state. Sealed predecessor bytes remain unchanged. Read [the implementing plan](../plans/2026-10-02-plan-11-28-parallel-local-test-context-implementation.md) and its checkpoint amendment together.

## Decision

Proceed with a local context implementation plan that permits full suites in separate worktrees to overlap. There is no lock, admission queue, foreign-process veto or requirement for another lane to pause. Windows job objects supply ownership, accounting and cleanup; independent worktrees and test fixtures supply state separation. Neither is evidence that contention caused a historical failure.

The operator approved v2 implementation, dedicated worktree/branch, local commits and the narrow coverage-hook procedure. The implementing plan records the exact approval and source receipt. This design does not grant publication or wider execution authority. The v2 inputs supersede the old lock proposal; historical spike evidence remains unchanged. Checkpoint A at `0d6c38a` is on HOLD pending the implementation plan's bounded corrections and complete sealed evidence, not cleared for Tasks 2–6.

## Evidence and limitations

Reviewed inventory: `2026-10-02-claude-shared-resource-inventory.md`, SHA-256 `66E97A0EAD0D7DBAE322E8FF9FCC5EA7A1E4D8AB3482B48C1DBF6353863E314E`. Reviewed operator inputs: `2026-10-02-operator-local-runner-plan-decision-and-claude-inputs_v2.md`. The inventory is useful planning evidence, not a proof that one run cannot affect another.

Preserve the spike dispositions: **runtime INCOMPLETE**, because independently retained control skipped-node identity is missing; **gate feasibility FAIL**, because two new persistence/serialization sinks lacked manifest classifications. The successful count comparison, native enrollment, named nested cases and observed normal-exit cleanup support proceeding. They do not retroactively close the missing criterion. See the unchanged `2026-10-02-codex-local-runner-spike-findings-ruling.md`.

The inventory covers the Plan 12 CP1 branch at `4b79a30`. For the draft, I also inspected committed main revision `e9d6be0c5318b52dbb2efbf7424e29a2afddbc18`, including its MAIN-5 guard and runner, root conftest, logging gate and backlog. The nearby `claude-fu33` worktree has staged implementation changes and was used only to read installed dependency source; its uncommitted changes are not the implementation base. Fable must refresh the relevant inventory at the actual base before execution.

The latest committed conftest still makes Windows known-folder isolation opt-in. The MAIN-5 guard protects the real roaming and local `optimus-cost-agent` folders plus the local and ProgramData `Python Keyring` folders. Those exact protected roots and existing test contracts remain authoritative; an environment-only APPDATA substitution does not establish isolation of the product's OS-derived trusted roots.

Accept the inventory's resource observations as bounded findings, with these qualifications:

- Listener port 0, random pipe names and fixture Git repositories are suitable existing isolation mechanisms. Check the changed default-selection tests at the implementation base rather than claiming all future tests safe.
- Approval-lock history supports a concrete shared-state risk. Timestamps alone do not establish which historical process created every file or which change stopped writes.
- The two real-port test contacts and real keyring reads are reported observations to trace and assign. They are not established harmless because they are reads: behavior can depend on live service contents. Do not claim the contacted service received no side effect without checking the operation.
- Job I/O counts are logical process accounting. They do not establish physical disk throughput, cache misses or that disk is the bottleneck. Record them alongside wall time without a causal conclusion.
- Shared uv/Node caches and Git metadata remain bounded environmental dependencies. Read-only test Git calls do not make simultaneous agent commits irrelevant to provenance; record HEAD/status at both ends and mark a changing checkout invalid for exact-commit acceptance.

## Architecture

Load a side-effect-free test-only context helper from root `tests/conftest.py`. Before collection, recognize the approved repository baseline marker expression and its focused subsets independently of mutable pytest configuration overrides, then activate native ownership and pytest-process protection. Non-default/live/e2e/investigation/unrecognized/mixed and collection-only requests retain passive records without a new job or root guard. An `-o addopts` or alternate config selecting e2e cannot redefine the approved default. Verify earlier imports do not touch real application state. Existing MAIN-5 protection stays intact; its active lanes use the integration without a new launcher. Deliberately bypassed conftest is outside the contract.

On native Windows, each active default pytest process owns a newly named job with a non-inheritable kill-on-close handle, retained until process exit. Do not close it during session finish while pytest is a member. Repeated default sessions reuse the retained handle; a live/passive session in that enrolled interpreter is refused before collection and must use an independent interpreter outside the job. Standalone live pytest remains passive. Passive children still inherit an active parent's job ownership: disclose that inheritance, support existing collection-only/synthetic unit children, and do not promise persistent live services within a default-run child contract. Such an unsafe launch blocks acceptance. Native failures invalidate context acceptance; PID/creation time and query outcomes remain explicit. Parent accounting includes nested jobs and is not summed again. See [Windows job semantics](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects).

Store bounded allowlisted records, with per-test phase identity, skip identity/reason, active test windows, observed member identities and job totals. A child first observed during a test is labelled `observed_during`, not asserted to have been launched by that test. Short-lived processes may be absent from sampled member lists; aggregate process count is retained separately. A total of 3,154 processes is not 3,154 individually retained process histories. Exhaustive native event tracing is outside this estimate.

A local registry associates runs with bounded, validated and sanitized metadata. Liveness uses identity-validated process handles; foreign exclusion uses this run's own job. Never open another run's job. The checkpoint's native diagnostic showed an interpreter's immediate job contains only itself; CPython's [Windows venv redirector](https://github.com/python/cpython/blob/3.14/PC/venvlauncher.c) creates a job for its interpreter. Therefore use identity-validated process ancestry to identify the nearest registered run relationship, labelled `validated_process_ancestry`, with live-state and creation-time checks and explicit UNKNOWN handling for incomplete/error cases. Ancestry is not proof of job membership. Own-job membership remains the ownership, accounting and cleanup authority through [IsProcessInJob](https://learn.microsoft.com/en-us/windows/win32/api/jobapi/nf-jobapi-isprocessinjob). Registry metadata is not authentication, exhaustive foreign ownership, kill authority or an admission lease. Never read argv, turn a failed query into GONE/none, or mutate an existing named job after a creation collision.

Sampling is synchronous at pytest phase boundaries and startup/terminal checkpoints. There is no context-created sampler thread, timer worker or background process. Partial records survive through those appends; a hung phase has no new snapshot until its next boundary. Report last-sample time and that limitation rather than promise periodic visibility. Sampling cannot prove exact child-launch causation or enumerate every short-lived process.

WSL2 Ubuntu supplies both actual WSL and local Linux validation with a separate Linux environment. Retain weaker process/accounting/cleanup capability labels and no Windows parity claim. Existing Linux workflow and MAIN-5 runner stay unchanged. Remote GitHub CI success awaits separately authorized publication.

### Coverage and worktree rule

The supported parallel topology is independent worktrees, each with its own frozen environment and a single coverage writer at a time. This is a worktree-use condition, not a scheduling lock. A coverage-producing focused run can collide with a full run in the same worktree too. Such concurrent writers are outside acceptance; use another worktree or a coverage-free focused command.

Do not promise to relocate coverage by setting COVERAGE_FILE in `pytest_configure`: the installed pytest-cov starts its central controller in `pytest_load_initial_conftests`, before root conftest is loaded. Its [configuration](https://pytest-cov.readthedocs.io/en/latest/config.html) also requires care about configuration-file selection. Preserve implicit per-worktree coverage files, caller-owned explicit paths and MAIN-5's scored/self-test combine contract. Per-run context files use unique directories. Same-worktree concurrent coverage support requires a separate early-loading design and is excluded.

### App-data protection boundary

Make the existing trusted-root fixture default only for active default-mode tests, preserving synthetic inputs and passive live-dependency contracts. Enforce refusal/audited write denial in the pytest process and nested pytest that loads conftest, with MAIN-5 retaining its stronger startup guard. For non-pytest children, deliver per-launch-site behavioral proofs of effective non-real product roots or inability to reach real-root access. Parent patches and ordinary APPDATA environment claims do not supply those proofs. Do not overwrite a MAIN-5 refusal with a permissive resolver.

Checkpoint A freezes the reachable default-selection launch inventory and demonstrates each distinct mechanism; Task 4 completes a linked proof for every site. Any unsafe or unproven site blocks final parallel acceptance even when a follow-up owner is assigned. Small test-only fixture corrections are in scope; product/launcher/startup-injection changes are not. A native job is not a filesystem sandbox, and proof-based child separation is not a universal runtime guard. Preserve that distinction in all claims. Arbitrary native programs, live integration services and hostile bypass remain outside scope.

## Ownership and estimate

Proposed custody: `P11-FEAT-ACP-RUNTIME-HARDENING`, test tooling, adjacent to `P11-FU-32` and `P11-FU-36`. Create a distinct bounded plan under that parent; do not imply that those broader residuals are closed. Filing selects an available plan number after checking the current registry. Plan 12 is a consumer, not the owner.

ACP cancellation/coverage variance stays with `P11.26-CAND-5-REPEATABILITY-ATTRIBUTION`; context measurements do not fix or close it. Trace the two port-contact tests and keyring reads to the same hardening parent's default-test isolation custody as separate proposed follow-ups. Their reported combined 1.5–3 hours are excluded from this implementation. Do not invent an already-filed ID or mark them repaired. If they actually prevent this plan's acceptance, record the dependency and return it for disposition.

Use **13–20 hands-on hours**, planning at **17 hours with approximately 15% contingency (19.6 hours)**. This is an estimate, not a guaranteed fixed-price commitment. The already completed inventory is not charged again. A two-hour early checkpoint and a 20-hour ceiling on proceeding without a revised authorization bound the remaining uncertainty. Full-suite machine time and independent review are reported separately; no monthly infrastructure charge is introduced.

Fable's working forecast is 17–20 hours; acceptance elapsed machine time is approximately 2.5–3.5 hours. Use the unchanged coverage hook as the single reference, followed by two direct concurrent suites and one full MAIN-5 gate. The v2 plan explicitly requires operator approval for local commits and temporary omission of the duplicate coverage hook on preparatory commits/non-coverage invocations; the exact committed candidate's reference hook then runs unskipped. No skip is reported as a passing coverage gate. Without that narrow approval, the exact-commit four-run schedule needs amendment.

## Handoff

The operator's approval releases only the named bounded local implementation/validation and local-commit procedure. Push, PR, merge and activation remain separate. At the checkpoint A hold, Fable may correct the slice and file these supplied documents within the existing remaining checkpoint budget; broader Tasks 2–6 await Codex acceptance. Evidence is copied and verified in the shared handoff before cleanup. Codex performs independent reviews and does not implement.
