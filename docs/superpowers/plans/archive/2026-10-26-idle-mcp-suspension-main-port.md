# A derived main MCP lifetime implementation plan

> Planning draft for independent review. Use the existing approved single-batch cadence. This plan authorizes no execution by itself. Codex is architect/author and Claude is reviewer; implementation remains with an agent explicitly assigned by the operator.

**Goal:** release idle client-MCP resources safely on current main while retaining the ACP session and its in-memory conversation.

**Architecture:** put SDK context entry/exit, bounded request dispatch and truthful cleanup under one connection owner. Add serving-loop idle/admission/reopen state around that shared owner. Join explicit conversation outcomes to actual RPC response delivery; do not import the durable-resume runtime.

**Tech stack:** repository Python >=3.14, locked MCP 2.0.0, pytest/asyncio, Ruff/Mypy, current native guard and product-coverage tooling; separate Windows and WSL environments.

**Spec:** approved assessment `evidence/2026-10-26-sandbox-delivery-audit/piece-a-assessment.md`, SHA256 `2100b6cf9862d4123109f1ac6f7c2ad594f609834a65511ddc9b44cc322e6048`; complete Claude architecture review at `evidence/2026-10-26-sandbox-delivery-audit/claude-review/claude-review-complete.md`. Main pin `be93393fc27f22bafa58fd9c2404e17b347a209d`; accepted historical A `12aa0e7b51dbb561ba59d9705e2875ec14ab9cf6`.

## Authority and settled decisions

The operator said “Approved”, then “Please get it reviewed”, “It is an advance approval from my end for you and Claude” and “No need to ask again” in this chat on 26 October 2026. That accepts the assessment route and its two contract changes and commissions this review workflow. Frozen assessment sentences saying those choices still need acceptance are historical. The complete implementation plan is a new work product; no runtime implementation, test execution, commit, publication, merge or cleanup has occurred.

1. Preserve main's in-memory conversation continuity. Add no session/load, ledger, replay, durable lease renewal or session expiry.
2. Idle MCP limit defaults to 3,600 seconds and accepts positive integers through 2,592,000. Tightening follows existing monotonic authorization; loosening requires an exact grant. No “off” environment value exists. Display that a very short value can cause frequent fresh permission prompts.
3. Add no synthetic ACP session TTL or TTL parser. When #240 later introduces real TTL, its integration must reconcile idle < TTL, including the accepted unset-short-TTL disablement. That later responsibility is not implemented here.
4. Chat retains its no-tools/no-permission contract. An admitted Chat prompt may use a suspended session without reopening MCP and receives no MCP service/broker. Plan/Agent prompts renew the entire former leased set before allocation. Quarantined sessions still return the fixed cleanup-uncertain refusal.
5. Use main's REQUEST_CANCELLED busy convention for closing/reopen reservations. Add only MCP_REOPEN_REFUSED (-32912) as the new application error after checking registry/schema non-collision.
6. Diagnostics use fixed codes, bounded counts and random opaque connection correlation only where internally required. Do not hash or log raw target paths. No global warning handler is installed at import.

**Original requirements:** one owner per resource lifetime, centralize then migrate, logging first. #302 and #317 retain resource-lifetime and track custody; #240 and #222 retain durable-resume and external acceptance. This class does not close those parents or diagnose the PC freezes.

## Global constraints

- One delivery batch, two connected engineering packages, one final independent execution review. Focused red/green development checks between packages; no per-fix full suite or model-review round.
- Start execution only in a clean dedicated contributor lane based on then-current hosted main. Preserve all sandbox tags, frozen plans, failed attempts and evidence. Do not merge main into the old sandbox under the still-unsatisfied conditional grant.
- Keep #377 discovery normalization/pagination, typed failures and budget semantics; keep main's newer catalog resolution-failure fields, Plan12 context/cost/routes and Chat behavior.
- No new dependencies, configuration/lock/secret-baseline changes, root-conftest changes, hook weakening, reduced test budgets, or inherited sandbox coverage-hook substitution.
- No external services or credentials are needed for the bounded technical claim. A hermetic official-SDK child proves SDK/resource lifetime only; it does not replace independent-server/ACP-client acceptance.
- A failed/timed-out observation is not clean release. Preserve primary failures and control-flow exceptions. Report source identity, platform qualifications, failures, skips and UNKNOWNs separately.

## Prerequisites

| Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|
| Approved route and continuity/TTL choices | yes | Operator | Recorded above; original bytes preserved. |
| Source, historical A and intact acceptance packet | yes | Architect | 195 final validation plus six tag-verification payload hashes matched. Historical only. |
| Complete plan independent review | no | Codex and Claude | merely unauthorized until review completes; this draft is the review target. |
| Implementing agent and runtime release | no | Operator | merely unauthorized; architect role is not an implementation assignment. |
| Dedicated current-main lane and native/WSL frozen environments | unknown | Implementer; operator owns machine state | Establish early with a bounded preflight before checks; absence has not been demonstrated. |
| Official local SDK stdio fixture and main lifetime owner | no | Implementer | genuinely absent on main, buildable in Package 1. |
| Owned-child containment and safe machine envelope | unknown | Implementer; operator owns machine state | Verify before child tests. Use one local test child at a time, no stress workers, load tests or xdist expansion. |
| Runtime tests, normal commits and final full gates | no | Operator and implementer | merely unauthorized now; release separately before execution. |
| Paid/live/Redis/Gateway/Zed/acpx campaign | no | Existing #222/#240 owners | Excluded. No fake or skipped test substitutes for those claims. |

## Exact proposed file scope

Production (12 existing modules):
- `src/optimus/mcp/client_sdk.py`: owner task/queue/terminal accounting, warning observation and bounded sanitized diagnostics.
- `src/optimus/mcp/client_disposition.py`: suspension/close preparation and completion, atomic renewal and truthful aggregate outcome.
- `src/optimus/mcp/client_catalog.py`: collectible replacement facade; retain `_resolution_failures`.
- `src/optimus/mcp/local_ipc.py`: retire owned permission candidates without unbounded renewal growth or lost listener ownership.
- `src/optimus/acp/spec.py`: admission, commit markers, generation join, idle phases, cancellation and shutdown composition.
- `src/optimus/acp/server.py`: delivery-result join, outbound-future cleanup and asynchronous ordered shutdown.
- `src/optimus/acp/conversation.py`: read-only public `next_turn_seq: int` property; no admission/commit semantics change.
- `src/optimus/acp/debug_trace.py`: fixed pre-run refusal reasons and corresponding sanitized surfaces.
- `src/optimus/acp/bootstrap.py`: resolve idle setting before runtime construction; thread trusted value and warning ownership.
- `src/optimus/acp/launch_policy.py`, `launch_gate.py`: dedicated idle parser/constant, registry and monotonic default/display.
- `src/optimus/acp/errors.py`: correctly documented application error and registry.

Create tests:
- `tests/unit/acp/test_idle_mcp_suspension.py`
- `tests/integration/mcp/test_client_sdk_local_stdio.py`

Existing admitted test files:
- `tests/unit/mcp/test_client_sdk.py`, `test_client_disposition.py`, `test_client_catalog.py`, `test_local_ipc.py`, `test_client_trust.py`
- `tests/unit/acp/test_bootstrap.py`, `test_acp_subprocess_env.py`, `test_launch_gate.py`, `test_launch_policy.py`, `test_error_code_registry.py`, `test_spec_protocol.py`, `test_stdio_ndjson.py`, `test_outbound_writer.py`, `test_conversation.py`, `test_debug_trace.py`, `test_plan121_chat_mode.py`
- `tests/unit/agent/test_plan121_chat_runner.py`
- `tests/unit/acp/test_typing_contracts.py` and `tests/unit/tools/test_validate_publication.py` for connected API/fixture contracts.

Governance filing, when separately released:
- `docs/superpowers/plans/2026-10-26-idle-mcp-suspension-main-port.md`
- `docs/superpowers/specs/2026-10-26-idle-mcp-suspension-main-port-design.md`
- `docs/superpowers/reports/2026-10-26-idle-mcp-suspension-main-port-receipt.md`
- `docs/decisions/ADR-027-idle-client-mcp-lifetime-contract.md`, `docs/decisions/README.md`
- `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json`
- `docs/README.md`; the sole transitional backlog's issue-only registry row.

ADR-027 is unused at this source pin; verify again before filing. Do not overwrite another lane's allocation. File the full plan/design/receipt under an approved issue and native parent #317, related #302, before implementation. No issue or label is created by this draft. Mutable checkpoint logs are never staged. Canonical documents must carry the full operating contract and sanitized receipts; private paths remain provenance, not execution dependencies.

Required read-only connected files: `outbound_writer.py`, `lifecycle.py`, `settlement.py`, `client_supervisor.py`, `client_trust.py`, `agent/runner.py`, current SDK source and repository test/coverage guards. These production files are outside mutation scope.

## Review focus

1. A dead SDK owner must fail every outstanding request and never leave close waiting on a dead queue.
2. A response may finish after a newer prompt; only a known matching turn and actual FLUSHED response can arm idle.
3. Capacity refusals and Chat must not reopen peers or disable an existing deadline.
4. Repeated denial/timeout/cancellation must not grow outbound-future, candidate or thread ownership.
5. Shutdown must keep permission futures loop-affine while blocking peer/runtime cleanup runs off-loop and remains joined.

## Package 1 Shared SDK lifetime and truthful cleanup

**Interfaces to preserve/add**
- Keep `ClientMcpSdkAdapter.open/discover/call/close/close_all` public behavior and #377 typed results.
- Preserve existing `_open_owned_sdk_contexts(capability, *, session_id, identity_key)` arguments. Its connection owner enters/exits the SDK contexts. Use the historical bounded request-dispatch design, a queue capacity of two with one operation slot and reserved close admission.
- Add `pending_connections() -> tuple[str, ...]`, `has_pending_connections_for_session(session_id: str) -> bool`, sticky `close_failure_recorded`, and bounded `diagnostics`/drop count. Pending tokens are random opaque IDs; diagnostics expose counts/fixed codes, never raw identity-key or path hashes.
- Session state provides `prepare_suspend() -> tuple[Callable[[], None], ...] | None`, `complete_suspend(failures: tuple[str, ...]) -> bool`, `has_leased_stdio_server() -> bool`. Add `prepare_close() -> tuple[Callable[[], None], ...]` and `complete_close(failures: tuple[str, ...]) -> None`. Preparation marks terminal state and detaches/snapshots hooks exactly once on-loop; completion records sticky failures. Keep sync `close()` as their compatibility wrapper. Disposition wires a `record_session_close_failure() -> None` callback into every real session state; its sticky `close_failure_recorded` is consumed by ClientMcpRuntime.close, including failures observed through old sync callers. Do not move permission cancellation or state mutation off-loop.
- Add `PendingClientMcpCandidateEndpoint.retire(candidate_id: str, *, session_id: str) -> bool`: retire only the matching session's candidate, idempotently, preserving concurrent candidates and live listener ownership. Listener stop/join work must not block the serving loop.

- [ ] Establish `test_real_sdk_contexts_enter_and_exit_in_same_owner_task` against unmodified main with an actual official ClientSession and local stdio child. Preserve the actual outcome; a missing expected red is a design observation to resolve, not a fabricated failure.
- [ ] Implement shared owner dispatch, including cancellation and failure of all queued/active responses in owner `finally`. A subsequent request/close observes the recorded terminal status immediately. A clean owner exit is not sufficient if context release, warning observability or survivor evidence is uncertain.
- [ ] Keep a connection pending until context/owner release is established. Never pop it or mark closed before release. Gather all close attempts even if the first fails; propagate control-flow failures, record ordinary failures stickily and make aggregate shutdown incomplete while any owner/failure remains.
- [ ] Route discovery and calls through owner dispatch with an internal direct path; retain main's discovery implementation and its budgets. Do not copy old A discovery bodies.
- [ ] Install the sanitized SDK warning observer at runtime construction, never module import. Keep at most one shared handler, explicit ownership across multiple runtimes and no strong references that prevent collection. Preserve warning endpoint checks and identity-bound survivor latches independent of ring overflow. Diagnostic capacity is 256 with an exact dropped count. Do not forward raw SDK messages, args, traceback or target data; do not mutate unrelated SDK records outside an owned context. Check the installed MCP 2.0.0 warning premise on each platform.
- [ ] Split server shutdown: serving-loop abandonment/cancellation of turns, permissions and reservations; stop sweeper and join all owned close tasks; detach/prepare session close on-loop; run blocking close hooks and runtime.close off-loop; apply state/outcomes on-loop; preserve existing Redis-last cleanup and primary failure behavior. Keep synchronous close_all compatibility for existing callers, but serving uses awaited `aclose()`.
- [ ] Clean `NdjsonOutboundChannel.request` in `finally`, including send failure, timeout and cancellation: remove only its own mapped future and cancel an unresolved future. Late responses become ignored, and cannot complete a replacement request.
- [ ] Both new-session and reopen permission flows retire each published candidate in `finally`, including denial, cancellation, failed send and timeout. Await blocking IPC cleanup off-loop. Retain any still-live listener/thread handle through incomplete shutdown, rather than forgetting it. Candidate retirement must not delete a different session or a newly published candidate.
- [ ] Add focused tests: owner exit before/after queued call; open/exit failure; reserved close under pressure; ordinary and control-flow close failure; close-all attempts remaining peers; owned child exit; session isolation; cancellation/timeout/late response future cleanup; repeated denied renewals return future/candidate counts to baseline; concurrent IPC publish/consume/retire; listener handle retention if join is incomplete; warning unavailable/changed/survivor/ring overflow; no raw target secret in diagnostics; facade/connection/owner weakrefs become collectible after confirmed release.
- [ ] Verify `ClientMcpLeaseAuthority.acquire_allow_once` remains in-memory: source currently only returns a dataclass; `lookup_durable` only reads. Add a no-write spy regression across renewals; modify no trust-store production code.

Use one off-loop close worker per serial sweep. The existing eight-connection default and operation timeouts bound scheduled submissions; set a session close observation budget of server count times the effective operation timeout. A timed-out SDK context still retains its owner and is uncertain, not force-released. There is no new promise to forcibly kill Python threads or bound all process exit.

## Package 2 Idle admission and permission renewal

**Interfaces**
- Dedicated `DEFAULT_ACP_MCP_IDLE_SECONDS = 3600`, `MAX_ACP_MCP_IDLE_SECONDS = 2592000`, parser and `resolve_acp_mcp_idle_seconds(environ: Mapping[str,str]) -> int`; invalid input fails before `build_agent_harness_runtime`.
- Add registry/default/display for `OPTIMUS_ACP_MCP_IDLE_SECONDS`, agent-child-only, monotonic tighten/exact loosen. No TTL names or ambient environment reads.
- Adapter accepts `mcp_idle_seconds: int | None = 3600` plus `monotonic_clock: Callable[[], float] = monotonic`. None is an internal disabled state, not a new launch setting.
- Add `record_turn_commit(session_id: str, turn_seq: int, *, committed: bool | None) -> None`, `note_turn_delivered(control: TurnControl, *, cancelled: bool = False) -> None`, `sweep_idle_mcp_once()`, `start_idle_mcp_sweeper()`, `stop_idle_mcp_sweeper()` and `aclose()`.
- Add public read-only `ConversationState.next_turn_seq`. Use it instead of adding idle reads of `_next_turn_seq`; no allocation behavior changes.
- Disposition adds `reopen_suspended(state: ClientMcpSessionState, request_permission: RequestPermissionFn) -> PermissionOutcome`, all-or-nothing publication.
- `submit_via_turn` and `deliver_envelope` return bool. Join only the normal TurnResponseEnvelope completion path; exception/outbound-error resend paths stay unarmed. Authoritative `rpc_response_delivery is FLUSHED` is separately required.

- [ ] In `_commit_turn`, record unknown immediately before prepare_commit, then known committed immediately after commit_after_final_flush (main line1604), before any notice/usage/alert await. In the prompt finally, record known noncommit only if no marker exists. A post-commit cancellation preserves committed; a partially failed preparation remains unknown.
- [ ] Verify writer ordering unchanged: normal outbound_writer lines228/233 publish authoritative state before line237 resolves source_future. Add real-writer tests including fallback/ambiguous/fail-closed branches; do not arm from future completion alone or change the writer's settlement algebra.
- [ ] Before allocation, use this prompt order: ordinary validation/busy checks; closing/reopen/quarantine gates; conversation.prepare_admission; if refused, retain the existing deadline and issue no renewal prompt; if admitted, invalidate old generation; reserve and reopen only for a non-Chat suspended prompt; recheck admission after awaited renewal; then allocate and capture mode/context. Keep same-session setters busy during close/reopen to prevent mode changes across permission awaits. Preserve earlier public setter behavior otherwise.
- [ ] Chat never reopens MCP and receives neither service nor permission broker, whether peers are active or suspended. The actual runner dispatches Chat to `_run_chat_answer` before tool planning, and that method accepts no MCP service; keep runner production unchanged. Test this through the real Chat runner with spies that fail on MCP open/list/call/permission. Returning to Plan/Agent later requires full renewal.
- [ ] Arm only after known allocated turn outcome + matching generation/sequence + actual FLUSHED RPC result + no cancellation/teardown + still-live leased state. Pre-admission nonturns, unknown outcomes, ambiguous/suppressed/failed sends and error resend paths never arm. Pop consumed/stale markers and prune session state on teardown. The active-turn map alone is insufficient because finalization removes it before transmission.
- [ ] Implement ACTIVE -> IDLE_CANDIDATE -> MCP_CLOSING -> MCP_SUSPENDED/QUARANTINED. The serial sweeper sleeps min(60, effective delay); it never busy-spins. Prepare/detach on-loop, run blocking hooks/pending query off-loop, finish state on-loop. Shield and track close work through sweeper cancellation and final shutdown.
- [ ] If warning observability is absent before close, perform no close, clear that deadline, record a fixed diagnostic and permit rearm only after a later determinate turn. Unknown release, changed channel or survivor evidence quarantines with `data.reason=mcp_cleanup_uncertain`. The documented entirely-between-snapshots logging-flip limitation remains.
- [ ] Reserve before renewal; renew former leased names in pinned order using fresh allow_once decisions; publish all leases and a new collectible facade atomically only after all succeed. Preserve prior unavailable servers and main's resolution-failure state. Denial/timeout/cancellation admits no turn and no partial service set. session/cancel must also cancel a pre-allocation reopen reservation and its pending permission, restore suspended state and retire the candidate/future.
- [ ] Add only MCP_REOPEN_REFUSED -32912, correct its docstring and error registries. Reuse REQUEST_CANCELLED for busy closing/reservation cases. Add the fixed reasons `mcp_reopen_refused`, `mcp_cleanup_uncertain`, `mcp_reopen_in_progress`, `mcp_closing` to the pre-run refusal allowlist and tests. Keep message content fixed and path-free.
- [ ] Tests cover exact boundary/deadline; unknown vs known noncommit vs postcommit cancellation; stale/out-of-order flush; busy refusal retaining markers; cap-closed and reservation refusals retaining deadlines/no permissions; Chat remaining suspended; Plan/Agent all-or-nothing reopen; cancel before allocation; setters during reopen; no-loop-blocking with another session answered while close remains in progress; shutdown joins; policy min/max/invalid/exact grant/default display; configuration invalidity before Redis construction; bootstrap/server wiring; no context/cost/route regressions.

Ordering is the primary responsiveness assertion. Retain the historical 0.5-second controlled slow-close and 0.25-second secondary timing bounds without returning to fragile 50 ms gates. Use events/handshakes; do not add deliberate CPU load.

## Verification and checkpoint

No commands in this section have run. Source inspection confirmed MCP 2.0.0 uses snake-case `InitializeResult.protocol_version`/`server_info`; keep those existing fields. Installed SDK modules are `mcp/client/stdio.py`, `mcp/client/session.py` and `mcp_types/_types.py`, rather than the old package layout. No initializer alias fix is proposed. Execute only after runtime/test authority and implementer assignment. Run from the new dedicated lane, with its own activated/frozen environment; never use a global interpreter or another lane's environment.

- [ ] Package-focused red/green selections preserve repository addopts, audit and run-context records. With the Windows environment activated:
  - SDK package: `uv run --no-sync pytest --no-cov tests/unit/mcp/test_client_sdk.py tests/unit/mcp/test_client_disposition.py tests/unit/mcp/test_local_ipc.py tests/unit/mcp/test_client_catalog.py tests/unit/mcp/test_client_trust.py tests/integration/mcp/test_client_sdk_local_stdio.py`
  - Adapter package: `uv run --no-sync pytest --no-cov tests/unit/acp/test_idle_mcp_suspension.py tests/unit/acp/test_spec_protocol.py tests/unit/acp/test_stdio_ndjson.py tests/unit/acp/test_outbound_writer.py tests/unit/acp/test_conversation.py tests/unit/acp/test_plan121_chat_mode.py tests/unit/agent/test_plan121_chat_runner.py`
  - Policy/observability: `uv run --no-sync pytest --no-cov tests/unit/acp/test_bootstrap.py tests/unit/acp/test_acp_subprocess_env.py tests/unit/acp/test_launch_policy.py tests/unit/acp/test_launch_gate.py tests/unit/acp/test_error_code_registry.py tests/unit/acp/test_debug_trace.py tests/unit/acp/test_typing_contracts.py tests/unit/tools/test_validate_publication.py tests/unit/tools/test_verify_plan996_logging_surfaces.py tests/unit/docs`
- [ ] The new local stdio module exercises the real official SDK and an owned local test peer. It is not marked requires_mcp_stdio, whose defined dependency is an independent digest-pinned Docker server. It claims no independent-server or external-ACP-client acceptance. Run children sequentially under existing containment. Validate PID plus creation identity before observing exit.
- [ ] Apply all affordable findings in a batch and rerun affected focused selections. Do not add a review after each subtask or run the full suite after each correction.
- [ ] Run `uv run --no-sync ruff check .`, `uv run --no-sync mypy` and `uv run --no-sync mypy src`, plus `git diff --check`; classify logging surfaces in the existing audit manifest, with no scanner exemption. Normal commit hooks remain required when a local commit is separately authorized.
- [ ] At one final clean candidate, run on Windows:
  `uv run --no-sync python tools/check_product_coverage.py --run-full-suite --groups tools/product-coverage-groups.json --report-json tmp/coverage/product-coverage-report.json --coverage-json tmp/coverage/coverage.json`
  then
  `uv run --no-sync python -m tools.testing.coverage_products validate --coverage-json tmp/coverage/coverage.json --gate-report tmp/coverage/product-coverage-report.json`.
  Repeat in the separate frozen WSL lane on matching source bytes, sequentially. Keep native protection/ancestry qualifications, required product floors and producing-run validity separate from pytest exit.
- [ ] Preserve source/tree/command/context, failures, skips, UNKNOWNs, raw logs and source-bound release proofs. Confirm old facade, connection and owner collection, real child exit, writer ordering and bounded renewal bookkeeping on the final candidate. Historical slopes or 4,462-test results do not transfer.
- [ ] One consolidated Claude implementation/evidence review. No unchanged failed gate retry; if a source correction invalidates a prior acceptance pin, explain the delta and run only the justified replacement acceptance. Keep initial failures intact.

## Claude architecture note disposition

| Note | Plan resolution |
|---|---|
| N1 commit marker | Package2: unknown before preparation; committed immediately after line1604; finally defaults only missing markers. |
| N2 flush ordering | Source verified: writer publishes before resolving future. Preserve writer, add ordering test, normal envelope-only join and public sequence accessor. |
| N3 refusal ordering | Probe admission before invalidating deadline or asking permission; recheck after renewal. |
| N4 dead owner queue | Owner finally fails queued/active responses and records terminal outcome; no dead queue wait. |
| N5 truthful cleanup | Real SDK red control first; pending and sticky failures; close every peer; aggregate reflects uncertainty. |
| N6 loop affinity | Three-phase awaited shutdown; permission cancellation/state on-loop, blocking hooks/runtime off-loop, Redis last. |
| N7 bookkeeping | Future finally cleanup; owned candidate retirement and listener retention; in-memory allow_once verified; serial bounded close submissions. F6 is included here for renewals, not dismissed as unrelated. |
| N8 privacy/logging | Counts/fixed codes/random internal tokens; no raw-path hash. Runtime-owned warning observer, premise tests, audit classification and retained snapshot limitation. |
| N9 configuration | Dedicated parser/default/display; validate before harness construction; no TTL names or hidden off value. |
| N10 errors | Main busy convention, new reopen code only, correct docstring and allowlisted refusal reasons. |
| N11 cancellation | Extend cancel to pre-allocation reopen and cancel/clean its permission; atomic facade publication retained. |
| N12 Chat | Keep suspended with no MCP service/broker and no permission; runner source confirms early no-tools Chat path; test this contract. |

## Explicit exceptions and completion boundary

No session TTL, durable runtime, eviction/Piece B, at-cap memory campaign, live model/service/editor proof, generic signal adapter, tool-output design, public Context7, user PC repair, shared hook/secret/inventory weakening, or cleanup. #240/#222 and existing parent owners retain those obligations. No whole-track closure follows.

Technical completion requires the full proposed contract, real SDK lifetime proof, focused checks, clean Windows/WSL gates/validity and consolidated independent acceptance. Local commit, publication, required PR CI, merge, actual-merge verification, issue closure and cleanup remain separately authorized operations.

Claude's advisory 8–11 working days/difficulty high excludes approval waits; 13d is the permitted rounded estimate if later agreed for the implementing issue. It is not a delivery promise or a label edit.
