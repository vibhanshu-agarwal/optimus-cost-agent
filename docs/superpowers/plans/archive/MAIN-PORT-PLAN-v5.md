# Sandbox-to-main Port Implementation Plan (v5 — main logging-surface classification)

> For agentic workers: this is the complete successor to v4, approved by the operator in chat on 2026-10-14. Its four product paths, six behavior-test paths and two documentation-check paths remain unchanged. The operator approved the single additional main logging-inventory entry and normal local verification/commits; publication and issue metadata edits retain their separate gates. Implementation belongs to the separately authorized implementing agent. Use the applicable execution skill only after the operator approves the route and exact slice. Codex retains the standing architecture role except for the MAIN-7 implementation assignment reported in #350 and supplied in the operator handoff. This successor grants no additional authority by itself.

**Goal:** port accepted sandbox concerns through bounded main-based changes, beginning with an explicit disposition of MAIN-7's local-telemetry prerequisite.

**Architecture:** adapt selected behavior to current main interfaces. MAIN-7 bounds recent diagnostic windows; its complete telemetry behavior also needs the Plan 11.7 R9 local-sink containment seam absent on main. The recommended route isolates that seam together with its bounds in one reviewed MAIN-7 change, without importing the durable session runtime. Route C and the implementing handler are recorded in [#350](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/350); execution acceptance remains a separate gate.

**Tech stack:** repository-pinned Python, uv, pytest/coverage, Ruff, applicable Mypy, pre-commit, native Windows and separate WSL/Linux environments. Establish exact versions from the execution checkout before running gates.

**Spec:** operator requirements and route C acceptance in [#350](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/350), this complete plan and the [dated source receipt](../reports/2026-10-14-main7-port-checkpoint.md#source-and-file-freeze). Predecessor/review digests identify archival provenance; no workstation draft is an operating dependency. Current-main governance: `AGENTS.md` and [ADR-022](../../decisions/ADR-022-github-issues-as-the-work-register.md).

This canonical plan is filed in the dedicated main-based port lane. [#350](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/350) now records Claude confirmation, route/scope acceptance and the implementing handler. Task 1's [source and file freeze](../reports/2026-10-14-main7-port-checkpoint.md#source-and-file-freeze) identifies the dedicated delivery lane; The plan registry and documentation index point to this canonical home. V1, v2, the sandbox register and accepted tags remain byte-preserved. GitHub issues hold current work metadata; this plan records scope, decisions, a dated source comparison and future gates.

The October 14 caller-review revision remains part of unpublished v3. Its pre-revision bytes, final revised bytes and original caller-review note remain in hash-backed archival custody outside this repository. The [dated source receipt](../reports/2026-10-14-main7-port-checkpoint.md#source-and-file-freeze) records the source pin, inspection scope and predecessor custody.

The subsequent targeted agent-run revision promotes the bootstrap-wired return boundary to the primary regression and keeps accounting as an injected-path control. Its [dated source receipt](../reports/2026-10-14-main7-port-checkpoint.md#source-and-file-freeze) and hashed before/after draft copies preserve this change without altering the four production-file scope.

## Global constraints

- Serve the original one-owner, centralize-then-migrate, logging-first and rapid safe sandbox requirements. MAIN-7 serves logging/telemetry and lifecycle/signals within the 15-track hardening programme. This slice establishes no whole-track completion or live memory-profile pass.
- Source HEAD must be a verified known-good sandbox tag; use selected tag blobs and reviewed hunks, never whole sandbox files or mixed commits. Preserve exact failures, UNKNOWN, skipped and UNRUN evidence.
- Main-based branches start at newly verified main, never a feature branch. Check status, branch, HEAD, tags, post-tag commit classes and source/target overlap before execution. Preserve existing work before using any dirty lane.
- Code implementation, local commits, publication, merge, live services and paid calls retain their respective authority boundaries. The drafted scope grants none of them. No MAIN-7 tests need paid model calls or operator Redis.
- Keep current-main hooks, one-key credentials, protected-root checks, test attribution and coverage policy. No automatic inheritance of sandbox hook exceptions. Use distinct frozen Windows and WSL environments, and one coverage writer per worktree.
- Do not copy `.secrets.baseline`, lock/configuration files, the shared logging-audit JSON, profiling tools, or unrelated test fixtures from the sandbox. No configuration change is expected for MAIN-7.
- GitHub Issues are the work register. Prepare each new issue's exact payload and relationship for approval; do not add a second open-work pool or allocate another `P11-FU-NN` identifier. Existing work is updated in its existing issue.
- V5 replaces the earlier planning recipe only after adoption; approved v4 and every failed attempt remain byte-preserved in archival custody. Adoption and delivery follow current document/versioning rules; this draft performs no archival moves and changes no existing plan checkboxes.

## Dated source comparison — 2026-10-14, Asia/Calcutta

| Source fact | Observation at review |
|---|---|
| Remote main and local `origin/main` | `d23a0e0683aeb2874a8e30af57aff795f77eb365`; 210 commits after v2's `ed0bfdf`. The local clone's checked-out main is older, so comparisons used pinned blobs. |
| Sandbox HEAD | `f6b0b602291b933ac1f493f397cad2b6f53620bf`, branch `experiment/cross-cutting-sandbox`, describe `sandbox-main5-guarded-runner-y5-0-gf6b0b60`. No commits follow the newest reachable tag. |
| Sandbox documents | Register modified; v1/v2 untracked. Three byte-for-byte backups and their SHA-256 values are retained in the review evidence. A backup preserves drafts; it does not commit them or create a new code checkpoint. |
| MAIN-5 delivery | Register records PR #217 merged at `df703857a7304abd36beedce9fcb9737a24fcc46`, and PR #218 residual filing at `e9d6be0c5318b52dbb2efbf7424e29a2afddbc18`. Existing harness residual points to [#250](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/250). No repeat port is proposed. |
| MAIN-7 source | Annotated tag `sandbox-main7-bounded-diagnostics`, target `9e523e29abde6d372fe38ac9e7d36e123650406b`, class delta `5592b2f..9e523e2`. Prior v1 names Claude review MANIFEST `36d5cc6fe0f5ad7662be716b6a849bb054dbd8c4e9eb884be9055a7f9a29c663`; retrieve and verify that review before execution. |
| MAIN-7 target drift | All four product blobs unchanged since `ed0bfdf`. Audit-path hunk contexts match; several fanout hunk contexts do not. Unchanged target files do not establish missing prerequisites. |
| Plan 11.7 runtime | `c69fd48646645a487b2a9521db8a92c22e536f3a` is not an ancestor of pinned main; `lease_owner.py` and named durable runtime symbols are absent. Source `spec.py` has 2,040 lines and no `attach()`, superseding the 1,135-line observation. |
| Main configuration | `pyproject.toml`, `uv.lock`, hooks and secret baseline all changed since v2. Re-derive execution commands and guardrail expectations from the actual target. |

Full commands, hashes, blob identities and inspection failures remain in archival custody outside this repository; the [dated source receipt](../reports/2026-10-14-main7-port-checkpoint.md#source-and-file-freeze) records the source freeze and evidence limits. At that planning snapshot, no red/green or execution-gate PASS had been obtained.

## Dependency disposition and route choice

MAIN-7's original four product paths are `src/optimus/acp/dispatcher.py`, `src/optimus/guardrails/audit.py`, `src/optimus/guardrails/pre_tool.py`, and `src/optimus/telemetry/fanout.py`. Its two new tests are `tests/unit/guardrails/test_bounded_audit.py` and `tests/unit/telemetry/test_fanout_bounded_diagnostics.py`.

Only dispatcher and fanout intersect `63b5d8f..c69fd48`. The dispatcher change forwards the guard's dropped counter and needs no durable runtime. Fanout's existing Gateway-result list can also be bounded independently.

However, main's ordinary fanout directly invokes JSONL then Redis. It has no local-sink failure collection, failure record type, containment helper or warning reporter. Those were introduced by Plan 11.7 R9 within that runtime range. MAIN-7 assumes them when bounding local failures and proving the other sinks still run. The full original slice therefore fails the static prerequisite check. Read-only import/hunk review cannot replace v2's required red/green proof on a main-based candidate.

The bootstrap-wired failure is in `AgentRunner.run`: it builds the result, sends `agent_run` through the fanout, then returns. A JSONL delivery exception can therefore replace a completed result after model usage and approved file changes already exist. The flush comment in `finally` covers flush only; it does not protect this preceding send. The primary regression below pins this reachable path using a successful approved mutation and supplied Gateway usage, with no live paid call.

The secondary, injectable path is `UsageAccountingService.record_gateway_usage`, which updates its provider ledger before calling its configured sink. A failing fanout JSONL append can raise after accepted usage has been recorded and replace its successful return. No source composition constructs that service or supplies `usage_accounting=` at the pinned main. If it is wired into `AgentRunner` later, `_record_ledger_entry` can additionally mark the accepted charge as an integrity failure. The provider ledger here is in-memory; no persistence or paid/live reproduction is claimed. Plan 11.5's quoted non-interference contract explicitly covers Gateway delivery; extending it to ordinary local delivery is the proposed correction, with the same one-owner motivation. It remains a reviewed behavior change even though it fixes an observable bug.

| Route | Scope and consequence |
|---|---|
| B: runtime before full MAIN-7 | Appoint the Plan 11.7 port handler, resolve its issue's reviewed-v4 gate, deliver its reviewed runtime, then re-derive MAIN-7. Preserves the old sequence, with a larger prerequisite. |
| C: explicitly isolated telemetry prerequisite with MAIN-7 — recommended | Review only R9's fanout failure contract plus the complete diagnostic bounds. Four product paths remain; add the primary completed-turn regression in existing `tests/unit/agent/test_runner.py`, containment/visibility tests in existing `tests/unit/telemetry/test_fanout.py`, and secondary accounting regression/controls in existing `tests/unit/usage/test_accounting.py`. The prerequisite collection is bounded from its introduction. Prove no durable session or held MCP dependency. This expressly fixes completed-result/failed-telemetry propagation and expands the original six-file recipe; route/scope acceptance is recorded in [#350](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/350). |
| C: reduced MAIN-7 subset | Port audit and Gateway-result bounds only, with explicit approval of that reduced scope and issue custody for local-failure diagnostics. This cannot close the original MAIN-7 class. It is not the recommended route because it leaves the known prerequisite unresolved. |

The October 14 route C decision is recorded in [#350](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/350); the following fallback remains part of its acceptance contract. If the isolated seam cannot pass its executable independence gate, fall back to B. A Plan 11.7 port handler remains a real decision for that runtime lane, even if MAIN-7 becomes independent.

## Prerequisites

This table preserves the planning snapshot; subsequent established facts and proofs are dated in the receipt.

| Requirement | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|
| Tagged MAIN-7 source and latest sandbox HEAD | yes | Source custodian | Verified tag targets and empty post-tag range; refresh before use. |
| Draft custody | yes | Codex, backup only | Three original documents preserved byte-for-byte; canonical adoption remains separate. |
| Original class acceptance record available and verified | unknown | Implementer / reviewer | Genuinely absent as verified evidence at that snapshot; the early task retrieves the named MANIFEST and its evidence; establish before dependent work. |
| Ordinary local-sink containment on main | no | Selected MAIN-7 or Plan 11.7 handler | Genuinely absent but buildable now; approve C's isolated contract or use B. |
| Route, scope and implementing handler | yes | Operator / [#350](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/350) | Consult the issue for the accepted route, handler and authority boundaries; this plan is not a second status register. |
| Main-based execution lane and frozen Windows/WSL environments | unknown | Implementer; operator owns machine state | Genuinely absent as a prepared pair of environments at that snapshot; establish early using current worktree rules and repository pins. |
| Protected full-suite invocation and valid attributed run context | unknown | Implementer / reviewer | Genuinely absent as a verified invocation at that snapshot; inspect current main runner, root conftest and run-context contract before executing. |
| Live services, paid credentials or GUI ceremony for this slice | yes | Implementer | Not required for the unit-level MAIN-7 contract; do not claim live-service acceptance. |
| MAIN-7 issue | yes | [#350](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/350) | Existing issue under the logging/telemetry track; each further issue edit requires operator approval. |

## Review focus

- Ordinary local sink failures: preserve the bootstrap-wired `AgentRunner.run` completed result and its existing cost/mutation facts; retain independent JSONL/Redis/Gateway attempts and one sanitized warning per failed sink. The primary agent-run regression and secondary injected accounting regression below must both be red on unmodified main and green after the fanout-only correction. Mandatory ledger, audit and durable-session failure handling remains unchanged.
- Control-flow exceptions: `CancelledError`, `KeyboardInterrupt` and `SystemExit` propagate without being recorded as ordinary diagnostics.
- Diagnostic retention: 16 recent records by default, exact drop accounting, list identity where public, positive custom limits and no unbounded prerequisite cache.
- Visibility and secrets: diagnostics still visible with project debug tracing disabled; no exception text, credentials, workspace path, prompt, response or traceback; stdout remains the protocol channel.
- Existing readers and delivery semantics: guard and dispatcher counters agree; repeated flush is a no-op once empty; Gateway exceptions/malformed responses remain contained; successful durable sink delivery is not reduced by retention.

### Every production telemetry caller and the failure boundary

Inspection at `d23a0e0` enumerated every `event_sink` reference, `Callable[[TelemetryEvent], ...]` contract and `TelemetryEvent` factory use under `src`, then read each caller's enclosing decision/exception path. There are nine emission owners (retry emits two event kinds), plus the agent's flush boundary. The table includes injectable production APIs as well as the paths wired by bootstrap; it does not imply all nine run in default composition.

| Caller and pinned source location | Emission and composition | Relies on ordinary fanout sink exceptions as a safety veto? / preserved authority |
|---|---|---|
| `UsageAccountingService.record_gateway_usage`, `src/optimus/usage/accounting.py:99–124` | `gateway_usage` after ledger update; injected callback. No source composition constructs this service or supplies `usage_accounting=` at the pin. | No such reliance found. Ledger validation/divergent-duplicate rejection occurs before emission and must still raise. This is the secondary injected-path red/green control. |
| `AgentRunner._emit_agent_run` / `_flush_event_sink`, `src/optimus/agent/runner.py:326–355,1173–1204` | `agent_run` after result construction and before return; flush in `finally`. Bootstrap passes the fanout at `bootstrap.py:147`. | No intentional veto found; however, the flush-only comment does not protect the earlier send, so a local delivery error currently replaces the completed return. The primary regression covers that boundary. Preserve transport-abandonment suppression and actual model/operation failures. `_record_ledger_entry` at lines 937–975 must still mark and re-raise real ledger failures; future accounting composition must not misclassify fanout-only failures as ledger refusal. |
| `SkillRegistry._emit_selection`, `src/optimus/skills/registry.py:44–91` | `skill_selection` after draft-skill exclusion and match creation. AgentRunner forwards the fanout at line 360. | No: matching and trust filtering determine the result; sink return is unused. Manifest parsing/content-hash failures remain outside containment. |
| `SkillInvocationPolicy._emit`, `src/optimus/skills/invocation.py:114–179` | `skill_invocation` after policy decision, before blocked/held return or pre-tool guard. Injectable; no production composition supplying the bootstrap fanout was found. | No: explicit BLOCK/HOLD and the independent `guard.check` remain authoritative. Telemetry success cannot authorize a forbidden tool. |
| `GoalLoopController._emit_stop`, `src/optimus/loops/controller.py:90–156` | `goal_loop` after stop selection and progress-ledger recording. AgentRunner forwards the fanout at line 389. | No: stop reason, completion evaluator and progress ledger determine stopping. Ledger append errors and budget/time/iteration/halt limits remain authoritative. |
| `GatedRetryRunner._emit_fitness_gate` / `_emit_retry_decision`, `src/optimus/retry/gated_run.py:92–149,157–193` | `fitness_gate` after shadow runner result; `retry_decision` after failure classification/policy choice. Injectable. | No: `gate_result.passed` and retry policy control promotion/retry, not the sink return. Failed gates must not promote writes; candidate/gate errors stay outside fanout containment. |
| `ReleaseGateRunner.run`, `src/optimus/release/runner.py:117–146` | `release_gate` after appending the gate result. Injectable. | No: gate exceptions become failed results and `ReleaseGateReport.passed` is their conjunction. Telemetry failure containment must not turn a failed result into a pass. |
| `evaluate_golden_task_suite`, `src/optimus/golden/runner.py:35–70` | `golden_task` after evaluation; injectable free callback. `release/defaults.py:72` calls it without a sink. | No: evaluator results and `GoldenTaskSuiteReport.passed` determine acceptance. Harness/evaluator errors and failed evaluations remain outside fanout containment. |
| `AcpDuplexAdapter._settlement_evidence_callback`, `src/optimus/acp/spec.py:543–575` | `acp_turn_settlement` via `emit_acp_turn_settlement_contained`; server forwards `AgentRunner.event_sink` at `server.py:524`. | Already ordinary-exception-contained. Settlement/transport fields are established before emission; preserve them and control-flow propagation. No durable runtime port is needed. |

**Mandatory-write boundary:** `PreToolGuard._audit` at `pre_tool.py:287` calls its separate audit sink's `append` directly. `ProviderUsageLedger.record`, progress-ledger append, session/state persistence and the runner's integrity-failure handling are not fanout diagnostic writes. Do not catch their exceptions, weaken guard decisions, or implement a generic wrapper around all caller callbacks. Arbitrary directly injected callables retain their existing propagation behavior; only ordinary local delivery inside `TelemetryFanout` is contained. If fresh-main inspection identifies a caller that requires a fanout diagnostic to be a mandatory audit, stop for explicit contract disposition rather than silently absorbing it.

### Primary AgentRunner completed-turn regression

Modify existing `tests/unit/agent/test_runner.py` to add `test_run_with_telemetry_fanout_preserves_completed_result_when_jsonl_fails`. Follow the existing `test_run_with_telemetry_fanout_isolates_gateway_trace_failure_from_agent_result` approved-mutation fixture: real `AgentRunner`, existing `FakeGatewayClient`, a real `TelemetryFanout`, temporary-path `JsonlTelemetryWriter`, and recording Redis/Gateway unit doubles. Use `batch_size=1` and a valid successful Gateway trace response so the injected JSONL error is the only delivery failure. Do not stub `run`, `_run_once`, `_emit_agent_run`, or mutation execution.

Prepare the pending WRITE plan with healthy JSONL delivery, then supply its actual plan hash through `AgentApproval` on the approved execution request. Only before that approved run, monkeypatch the writer's `append` to raise a synthetic `OSError` on its final `AGENT_RUN` event. Inside the failing append, first assert that `example.py` already contains the approved docstring, and the emitted event reports completed status, one mutation and the fixture's `Decimal("0.002")` total cost. This verifies failure after completed work and accepted usage facts rather than during planning, approval or setup. Snapshot recording-sink/export counts after preparation to distinguish the approved-run event from the earlier planning event.

Expected red on unmodified execution main: `runner.run(approved_request)` raises that controlled `OSError` after the file/event assertions succeed. Preserve the failed desired-behavior test and traceback. Expected green after the fanout-only change: the same run returns `AgentRunStatus.COMPLETED`, mutation count one, total cost `Decimal("0.002")`, with the file change intact; the approved-run `AGENT_RUN` reaches Redis and the Gateway exactly once each; one bounded sanitized JSONL failure and one warning are recorded, with no exception-message sentinel, traceback or stdout diagnostic. The final flush must not export the same event again. Capture warnings only for the approved run. This unit test simulates settled Gateway usage and a controlled I/O failure; it makes no paid call or production filesystem change.

### Secondary accounting regression and controls

Extend existing `tests/unit/usage/test_accounting.py`; do not change accounting production code. Specify `test_accounting_records_usage_when_jsonl_telemetry_fails` using the existing `gateway_usage("gw-1", "0.003", 3)` helper and its July 4 UTC attribution fixture. Configure the real `UsageAccountingService` with a real `TelemetryFanout` (`batch_size=1`), a temporary-path `JsonlTelemetryWriter` whose `append` is monkeypatched to raise synthetic `OSError`, and recording Redis/Gateway unit doubles. The failing append first asserts that the service's ledger already contains exactly `gw-1`, cost `Decimal("0.003")`, three billing units, then raises. This pins the failure after recording rather than at setup or provider validation.

The test expects the service call to return its provider ledger, still with exactly one entry and unchanged cost/units; Redis and Gateway each receive the one usage event; one sanitized JSONL failure and warning are recorded; no exception-message sentinel reaches logs or stdout. On unmodified pinned main this desired-behavior test must fail with that `OSError` after the callback's ledger assertion; after the fanout-only adaptation it must pass. Keep both run artifacts; no test claiming that propagation is the desired behavior is retained. This uses supplied usage and controlled I/O failure, not a paid call or actual disk exhaustion.

Retain or extend `test_accounting_service_does_not_emit_event_for_rejected_divergent_duplicate` with the configured fanout: a same-ID change from cost `0.003` to `0.004` must raise `DuplicateGatewayRequestError`, leave the ledger unchanged, and make no additional telemetry attempts. Add `test_accounting_preserves_direct_callback_failure` using a raw raising callback instead of fanout; it must still raise after recording. These controls prove that containment is owned by fanout and is not a blanket change to accounting or mandatory writes. Preserve existing agent flush/error tests and BLOCK/HOLD, failed-gate/non-promotion, loop-stop and failed-release/golden assertions when running their caller suites.

## Task 1 — adopt the route and freeze a reviewable slice

**Files:** this successor plan, canonical plan filing/index/issue-only registry pointer and sanitized receipt; the two documentation-check files are approved in v4; the one new logging-inventory artifact entry below requires v5 approval. No product code at Task 1.

- [x] The completed Claude review condition and operator route/scope decision are recorded in [#350](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/350); this row references that record rather than granting authority itself.
- [x] Fresh main and tags rechecked; original class review MANIFEST and all 215 entries verified. The Task 1 review records exact source identities, baseline and retained qualifications.
- [x] Use [#350](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/350) as the existing MAIN-7 work record. Its handler/status/next gate remain authoritative; do not recreate it or post an update without approval. #303 retains its broader contract, and #230/#240 retain runtime-port custody.
- [x] Freeze the hunk/import/test matrix at main `d23a0e0683aeb2874a8e30af57aff795f77eb365` in the Task 1 review. C selects only fanout's R9 failure contract from the day-0 range, together with MAIN-7's bounded behavior from its tag. Do not cherry-pick `8a1b635`, `d1e8b6c`, `4a1e6c4` or `9e523e2` whole; their commits carry unrelated runtime, Redis, audit or profiling changes.

**Check:** frozen scope identifies four product modules, two new behavior-test files, selected additions to existing `tests/unit/agent/test_runner.py`, `test_fanout.py` and `tests/unit/usage/test_accounting.py`, and any necessary current-main dispatcher reader test in `tests/unit/acp/test_dispatcher.py`. Refresh the complete caller/mandatory-write table against the execution pin before implementation; no unexplained reliance on diagnostic exception propagation may remain. No unlisted production path is admitted. Necessary documentation/evidence follows current main's audit rules and is projected before implementation.

## Canonical-filing correction — scope approved in v4

The initial canonical filing used a `Moved` plan-registry row. The native Windows docs run `20261013T195850-3544-b1bfd5` reported **1 failed, 94 passed, exit 1**: `test_every_moved_pointer_names_its_manifest_issue_and_pins_its_former_detail` treated MAIN-7 as a migrated historical entry and required a Plan-number/manifest identity and pinned former backlog detail. Neither exists: MAIN-7 was created directly as #350. ADR-022 explicitly permits an issue-only pointer for a new live plan, but the two current governance checks do not represent that exception. Do not fabricate a source record, alter sealed migration inventory or bypass a check.

This successor adds only `tests/unit/docs/test_plan_directory_hygiene.py` and `tests/unit/docs/test_open_work_pool_hygiene.py` to the six previously frozen behavior-test mutation paths. The v5 canonical row is:

```markdown
| [MAIN-7 — sandbox-to-main bounded diagnostics](MAIN-PORT-PLAN-v5.md) | — | — | [#350](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/350) |
```

The placeholders carry no status or owner; the issue link carries no copied next-gate narrative. This is a new issue-only pointer, not a migration `Moved` pointer and not a source-status row.

1. In the plan-directory test helper, recognize the exact issue-only row shape and include its filename in the set of registered live plans. Keep the existing Active/Blocked/Moved paths and flat-archive checks intact. A current plan must still be registered exactly once.
2. In the work-pool checks, explicitly validate issue-only plan-registry rows: exactly one existing plan link and one canonical nonzero issue link; both metadata cells exactly `—`; no pinned-former-detail field, duplicate plan/issue, status, priority, owner or next-gate prose. Add meaningful positive and denial controls using synthetic rows (duplicate identity, metadata injection, wrong URL/issue and malformed/missing cells). Do not count these rows in the historical migration inventory; preserve every old sealed-record and former-detail assertion.
3. Red first: demonstrate that the old plan-directory helper does not register the legitimate issue-only row, while the original `Moved` filing failure remains preserved. Change only the two test helper/check files. Run all docs tests, the MAIN-7 behavior files and Ruff; record source identity, exit, skips and run-context validity. No production or work-tracking-tool change is included.
4. File the complete canonical v5 at `docs/superpowers/plans/MAIN-PORT-PLAN-v5.md`, the issue-only registry row, the docs index and a sanitized dated receipt. Preserve v3 and the failed four-file filing projection in local archival custody; they were never adopted as tracked authority. No frozen predecessor edit or invented migration source is needed.
5. Use normal hooks for local delivery. The final clean committed source must pass the protected Windows product-coverage gate and validity check, the separate frozen Linux gate and required independent review. An earlier core-only full run can support only its original pin; the governance correction creates a new final source obligation.

**Gate:** the operator approved complete v4 and its local correction on 2026-10-14. That correction has its own red/green evidence below. V5 approval precedes the additional logging-inventory artifact write and v5 canonical filing. No issue write, push, PR or merge is authorized by this proposal. The code port can be validated and locally committed separately within its already supplied four/six scope.

**Risk/rollback:** exact row validation must not admit a second live work pool or weaken sealed migration evidence. Denial controls protect those boundaries. Revert the added check branches and canonical row together if rejected; the four-file telemetry/audit behavior port is independent of this document representation.

## Logging-surface classification — one additional artifact proposed in v5

The first normal local-commit attempt failed its selected run (`20261013T200325-56724-929e5c`): **1 failed, 4,953 passed, 20 skipped**, exit 1. Its typed record is COMPLETE, native valid, full protection and full audit depth. The sole failed node was `tests/unit/tools/test_verify_plan996_logging_surfaces.py::test_checked_in_manifest_covers_current_surface_inventory`, which reported `UNCLASSIFIED_SINK: optimus.telemetry.fanout:_report_local_sink_failure:logger_export`. The hook's subsequent 78-test audit run passed, but used quick/reduced depth and does not supersede the failed selected run. The hook rejected the commit; HEAD remains `d23a0e0683aeb2874a8e30af57aff795f77eb365`. This was a selected development run, not the clean canonical full-suite coverage gate.

**Additional mutation path:** `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json`. Add exactly the entry below to the current main-derived inventory. Preserve all old entries and metadata; never replace it with the sandbox's manifest. This is required classification of the new warning already in the approved product contract, not a new product behavior, exemption or test-rule weakening. No inventory tool, secret baseline, configuration or dependency changes are proposed.

```json
{
  "key": "optimus.telemetry.fanout:_report_local_sink_failure:logger_export",
  "policy": "safe-by-construction",
  "rationale": "Inspection: the fixed warning format exports only a fixed sink label, TelemetryEventKind value, fixed telemetry_sink_raised reason and exception class name. No exception message, traceback, event payload, prompt, response, credential or workspace location is passed to the logger.",
  "sanitizer": "Four-field metadata-only construction in TelemetryFanout._attempt_local_sink; no exception text or event payload is exported.",
  "test_node": "tests/unit/telemetry/test_fanout.py::test_fanout_warning_reaches_stderr_with_debug_disabled",
  "evidence_tier": "unit"
}
```

The existing main inventory validator must discover exactly one missing surface before the addition and validate the proposed entry against the current candidate in memory. Preserve that proof and the failed hook packet. After approval, apply only the one-entry addition, require the existing inventory test green and rerun all docs/MAIN-7 behavior tests and Ruff. Existing positive/denial inventory controls remain unchanged. Stage the approved complete files and use normal hooks for the local commit; never bypass or mask the failed gate. Then run the final clean committed Windows product-coverage gate and validity check, separate frozen Linux gate and independent review. No clean-source full gate has been run yet.

The v4 registration red (`20261013T204032-54648-db5120`) failed because the old helper omitted the legitimate issue-only row. After the two approved helper/check edits and canonical filing, **234 tests passed**, no skips, exit 0 (`20261013T204058-61296-bae8bd`): all 121 docs checks plus all 113 MAIN-7 behavior tests. Both contexts are active/default selection, native valid, full protection and COMPLETE; each run's source snapshot was unchanged. Ruff passed. These remain dirty-tree development evidence, not a commit or delivery acceptance claim.

Canonical v5 filing supersedes only the uncommitted v4 projection: back up that projection byte for byte before removing it from the live root, point the one issue-only row/index/receipt at complete v5 and keep the approved draft/failed projections as archival provenance. No adopted or frozen main predecessor is moved or rewritten. Local execution/verification/commits retain the supplied approval boundary; each issue write, push, PR and merge remains separately approved.

**Approval gate:** do not write the shared logging inventory until the operator approves this complete successor and the exact additional entry. If not approved, leave the failed candidate undelivered and report the logging-inventory gate as unsatisfied. Do not delete the warning or hide its logger call to evade discovery.

## Task 2 — implement and prove the complete bounded contract, if C is approved

**Completion snapshot — 2026-10-14:** the seven checked items below are evidenced by the [dated receipt](../reports/2026-10-14-main7-port-checkpoint.md#dated-local-technical-acceptance). Red/green and final-run source identities remain distinct; current work and authority remain in [#350](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/350).

**Modify:** four named product files; primary completed-turn regression in `tests/unit/agent/test_runner.py`; selected containment tests in `tests/unit/telemetry/test_fanout.py`; secondary accounting regression/controls in `tests/unit/usage/test_accounting.py`; dispatcher reader test if its existing coverage does not exercise the new counter. **Create/adapt:** the two named MAIN-7 test files. **Interfaces:** retain existing constructor/call signatures with keyword-only positive limits defaulting to 16; expose `audit_event_limit`, `audit_events_dropped`, `delivery_results_dropped`, `local_sink_failures_dropped`. `LocalTelemetrySinkFailure` has only `sink`, `event_kind`, `reason_code`, `exception_type` and reason code `telemetry_sink_raised`.

- [x] Retain attributable red controls on pre-port main: after 20 audit events retain runs 4–19 and drop four; after 20 Gateway deliveries retain batches 5–20 and drop four without replacing the public list; ordinary JSONL or Redis exceptions must not suppress the other sink and Gateway attempt. Record unsupported missing APIs separately from behavioral controls that already run.
- [x] Write and run the primary `test_run_with_telemetry_fanout_preserves_completed_result_when_jsonl_fails` on unmodified execution main exactly as specified above. Require the controlled `OSError` after approved mutation/cost/event assertions and preserve that red run. After the fanout-only adaptation, require the same test green with the completed result, unchanged work/usage facts, one approved-run event at each independent sink and one sanitized warning.
- [x] Write and run `test_accounting_records_usage_when_jsonl_telemetry_fails` exactly as specified above against unmodified execution main. Require the controlled `OSError` after the verified single ledger entry, and preserve the failed desired-behavior run. Run that same test after adaptation and require successful return, unchanged accepted charge, independent delivery attempts and one sanitized warning. Run the divergent-duplicate and raw-callback controls; ledger/mandatory audit failures remain propagating.
- [x] Implement the approved R9 fanout seam and bounds together. Catch ordinary `Exception` per local sink, emit the four-field sanitized warning, continue to independent sinks/buffering, and bound retained local failures at creation. Preserve the settlement helper, durable commit code, protocol behavior and current Redis owner interfaces.
- [x] Adapt the six named tests from the tagged class, including 100 concurrent audit appends producing 16 retained records and 84 dropped; reject zero/negative limits. Add positive custom-limit coverage and dispatcher counter forwarding without introducing runtime-only fixtures.
- [x] Add main-compatible tests for each failed sink, both failed sinks, healthy fanout, existing Gateway failure/invalid-response containment, exact warning counts, debug tracing disabled, stdout cleanliness, and secret-sentinel exclusion from record/log output. Test all three control-flow exception classes. Preserve ordinary failure evidence independently of the diagnostic window.
- [x] Inspect current test selection and attribution settings, then run focused tests with the lane's frozen runtime: `uv run --frozen --extra dev pytest tests/unit/agent/test_runner.py tests/unit/guardrails/test_bounded_audit.py tests/unit/telemetry/test_fanout_bounded_diagnostics.py tests/unit/telemetry/test_fanout.py tests/unit/usage/test_accounting.py tests/unit/acp/test_dispatcher.py`. Also run existing caller suites `tests/unit/skills/test_registry.py`, `tests/unit/skills/test_invocation.py`, `tests/unit/retry/test_gated_run.py`, `tests/unit/loops`, `tests/unit/release/test_runner.py`, and `tests/unit/golden/test_runner.py` to retain their mandatory decision/error controls. Preserve repository defaults/root conftest. Record exact command, source tree, context validity, exit status and skips; require behavioral tests green and valid evidence.

**Check:** all approved contracts demonstrated on main interfaces; no day-0 symbols/imports, no held MCP source, no whole-file transplant, no tests importing the sandbox Redis fixture `tool_loop_run_sync`. Passing this task establishes focused behavior only.

## Task 3 — verify the main boundary and deliver only on authority

**Completion snapshot — 2026-10-14:** the first two checked items record local gates and Claude's source-bound technical acceptance at `8177b9b`. Publication, PR CI, merge and post-merge verification remain open. A later documentation-only successor is verified separately and does not relabel those full runs as new-HEAD evidence.

- [x] Run the then-current protected Windows full-suite/coverage invocation and the required Linux/WSL suite in separate frozen environments. Inspect guards, protected-root evidence, native capability and attribution; preserve weaker platform labels. Run Ruff (`uv run --frozen --extra dev ruff check .`), applicable Mypy, secret hooks and current main hooks. Meet aggregate coverage policy and safety-module non-regression.
- [x] Independently review the exact candidate and full-run source pin, including post-run fix deltas. Retain current repository checkpoint cadence; do not add routine per-test review gates. Audit governing docs and the issue for freshness, with no second live status registry.
- [ ] Obtain explicit publication approval, create the bounded PR, verify required CI and the final diff against current main. Obtain separate merge approval. Reconcile later runtime integration against the isolated seam to avoid reintroducing unbounded records or duplicate failure ownership.
- [ ] After merge, verify main and record attributable checks in the issue. Roll back by reverting the approved complete class change and tests after reversing any dependent dropped-counter consumers. If containment was introduced in that same change, rollback restores main's prior ordinary sink-exception behavior; explicitly disclose that consequence. Durable session and Redis runtime ports are outside the rollback.

**Check:** no final acceptance from focused tests alone; full gates, independent review, CI and merge remain separately evidenced. No live-service or full memory-profile claim follows this change.

## Remaining portfolio and explicit exceptions

This successor retains the earlier portfolio; selecting MAIN-7 does not erase or close its neighbours. Each requires its own current-main source matrix and issue custody before scheduling.

| Slice / concern | Retained scope or boundary |
|---|---|
| `_closed_state_ids` | Re-derive the minimal `remove()` discard/close-once contract from main's current 2,040-line spec and actual concurrency. Test existing session-new failure/close-raises/repeated remove/close-all paths. No `attach()` or failed-load/reattach tests while that API is absent; no wholesale sandbox spec transplant. |
| Hypothesis sanitizer oracle | Selected six-property suite plus exact required dev dependency and freshly derived lock. Verify class acceptance and meaningful mutants before approval; never copy old configuration. |
| Static typing | Fresh module-contract cohorts and main Mypy baseline, with prerequisite test-double review; no 71-file transplant. Exclude held MCP contracts, and defer runtime-dependent cohorts until their prerequisite exists. |
| Held MCP lifecycle, then idle suspension A | T1/T2/N1/R1, tool visibility and class acceptance/tag remain prerequisites. A additionally needs durable runtime joining. Do not import held SDK/catalog changes via MAIN-7. |
| Session eviction/K-scaling, fallback and reader hygiene | Original register/requirement custody remains; each gets its issue disposition before scheduling. Piece B full conversation unloading remains outside this port proposal. |
| MAIN-5 N4/F5/F6, MAIN-1–4, Ruff after typing, other hardening tracks | Maintain existing issue custody or migrate the actual untracked remainder through an approved batch. #250 owns only its named harness residual. No parent-track completion inferred. |
| Memory profiling / Stage 3 | Closed investigation findings and unmeasured campaign limits remain historical evidence. Exclude profiling tool/method files and the shared logging-audit JSON from product port material. |
| Plan 11.7 runtime and Plan 12 lanes | Separately owned, reviewed and authorized. No owner assignment or priority change is made here; later Plan 12 operator priority in the register is preserved. |

## MAIN-7 work record

[#350](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/350) replaces the former unpublished issue payload. Consult it for the native parent, handler, status, accepted route, acceptance criteria and next gate. Each issue edit needs operator approval. #303 keeps the broader typed telemetry contract; #230/#240 keep the runtime lane and #250 keeps the MAIN-5 harness residual.

## Dated core-port development evidence

On unchanged main production blobs, the primary AgentRunner and secondary accounting desired-behavior tests both failed with the controlled OSError after their completed-work/ledger assertions (`20261013T195336-33552-3094f6`). The bounds/controls run had 13 failed and 19 passed (`20261013T195457-21564-1564db`); missing constructor/property APIs are explicitly distinguished from behavioral retention/propagation failures. After the four-file adaptation, all six behavior files passed 113 tests (`20261013T195550-60240-ea736a`). Caller suites passed 77 with one symlink-platform skip (`20261013T195621-5492-4e7e9f`). All contexts reported active/default selection, Windows native valid/full protection/COMPLETE. These are provisional dirty-tree development runs, not final-commit acceptance. Initial Ruff I001 was corrected by whitespace only; the subsequent full Ruff check passed.

The canonical docs run failed 1/94 as described above. Its raw output is retained, and its typed terminal context is COMPLETE/exit 1, but the wrapper failed decoding cp1252 output as UTF-8 before writing its after-source snapshot: that wrapper receipt is incomplete. Source attribution for that failed filing is not upgraded to a final acceptance claim. Future runner output uses UTF-8 without clearing project configuration.

Original source/failure evidence remains intact. Full gates and subsequent local delivery bind to their separately recorded source pins; no later success erases the documented failed filing.

## Adoption and execution boundary

Claude's confirmation and the operator decisions are recorded in [#350](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/350). Task 1's fresh-main file/import/test freeze and clean baseline are recorded in [the Task 1 review](../reports/2026-10-14-main7-port-checkpoint.md#source-and-file-freeze). The reviewed pre-edit v3 bytes are preserved in that evidence folder. The product and v4 documentation reds/greens above are provisional; the rejected local commit and its classification gap remain visible. Final Windows/Linux gates, independent execution review, push, PR and merge require their separate evidence and authority. Consult the issue and direct operator instructions for each authority boundary; no implementation acceptance follows from this planning checkpoint.
