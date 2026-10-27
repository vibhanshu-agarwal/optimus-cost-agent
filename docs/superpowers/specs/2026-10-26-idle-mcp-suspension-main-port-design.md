# Idle client-MCP lifetime contract

Work authority: [#427](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/427), native parent #317, related #302, #240 and #222.

This self-contained operating specification files the complete v2 contract below. The source plan's historical statements about unassigned implementation and unreleased development are superseded only by the operator's explicit 2026-10-26 development instruction in the accompanying receipt. Its scope, policy and review qualifications are unchanged. References to private packets are provenance, never execution dependencies. No historical test result certifies current main.

## Approved v3 continuation, 2026-10-27

The operator approved complete v3, including guard strengthening, byte-preserving local v2 archival before issue posting, normal-hook commit, sequential Windows/WSL acceptance and one compact delta review. Codex implements; actual Claude reviews. The inherited v2 sections below remain historical contract detail, qualified by this current section and the complete v3. Their old unassigned/UNRUN statements describe prior checkpoints, not current authorization. Publication, integration, merge, closure and cleanup remain held.


Candidate retirement first removes the session's actual permission candidates. The exact typed `LocalIpcError("client_mcp.ipc_stop_incomplete")` from that retirement callback denotes a retained shared listener generation, not uncertain release of the session's MCP peers. It does not by itself quarantine a successfully suspended session or refuse its Chat prompts. The endpoint retains its thread/listener/generation, refuses replacement while that generation lives, and final runtime close still reports incomplete while it is held. Actual SDK/peer uncertainty, another IPC error or a forged `.code` still fails session cleanup. After an incomplete final runtime-close observation, aggregate failure remains sticky; no separate endpoint sticky flag is invented.

Failure ordering attempts adapter, client-MCP runtime, owned writer and reader decision before the enclosing Redis-last cleanup. Preserve the genuine runtime outcome and one bounded MCP-incomplete diagnostic even when the adapter raises. Control-flow takes precedence after owned cleanup; otherwise preserve the first ordinary failure and chain a secondary failure. Repeated cancellation keeps the same MCP worker owned and joined.

There is no outer observation bound for a hung keyring read or arbitrary close hook: shield/join may wait indefinitely. The old N-c outer-bound sentence is not implemented or claimed; #302 retains this residual alongside synchronous session/new keyring access and the finite90k outbound request-ID iterator. No force-kill or new timeout policy is added.

A logging flip and revert entirely between endpoint snapshots can go undetected. Foreign filters on `mcp.client.stdio`, `dictConfig(disable_existing_loggers=True)` or global WARNING disablement can also make the channel unobservable; stdio suspension then remains disabled with bounded WARNING_UNOBSERVABLE diagnostics. No global logging reconfiguration is performed. These limits do not prove a PC-freeze cause or whole-process bounded exit.

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
- `tests/integration/mcp/sdk_stdio_peer.py` (owned peer script; no test_ prefix)
- `tests/support/idle_mcp.py` (only shared doubles/helpers; no unit imports from integration/e2e test modules)

Existing admitted test files:
- `tests/unit/mcp/test_client_sdk.py`, `test_client_disposition.py`, `test_client_catalog.py`, `test_local_ipc.py`, `test_client_trust.py`
- `tests/unit/acp/test_bootstrap.py`, `test_acp_subprocess_env.py`, `test_launch_gate.py`, `test_launch_policy.py`, `test_error_code_registry.py`, `test_spec_protocol.py`, `test_stdio_ndjson.py`, `test_outbound_writer.py`, `test_conversation.py`, `test_debug_trace.py`, `test_plan121_chat_mode.py`
- `tests/unit/agent/test_plan121_chat_runner.py`
- `tests/unit/acp/test_typing_contracts.py` and `tests/unit/tools/test_validate_publication.py` for connected API/fixture contracts.
- `tests/integration/acp/test_server_stream.py`; `tests/unit/acp/test_server_mcp_shutdown.py`, `test_server_reader_ownership.py`, `test_server_redis_shutdown.py`, `test_main_wiring.py`, `test_stage_c_launch.py`, `test_test_composition.py`; `tests/unit/mcp/test_client_supervisor.py`.
- Read-only live-tier comparison: `tests/integration/acp/test_server_stream_live_redis.py`, excluded from this local technical claim and not released for execution.

Governance filing, when separately released:
- `docs/superpowers/plans/2026-10-26-idle-mcp-suspension-main-port_v3.md`
- `docs/superpowers/plans/archive/2026-10-26-idle-mcp-suspension-main-port.md` (unchanged v1 provenance)
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
- Add `PendingClientMcpCandidateEndpoint.retire(candidate_id: str, *, session_id: str) -> bool` and `retire_session(session_id: str) -> int`. Retire only matching ownership, idempotently. Keep at most one pending candidate per live session/server; publishing a renewal atomically supersedes that server's older candidate. Candidates live through the permission answer and retire on session close/suspension or a same-server successor, preserving the later durable-trust ceremony. Cleanup runs in one serialized off-loop bookkeeping lane, not one unbounded to_thread job per candidate.

- [ ] Establish `test_real_sdk_contexts_enter_and_exit_in_same_owner_task` against unmodified main with an actual official ClientSession and local stdio child. Preserve the actual outcome; a missing expected red is a design observation to resolve, not a fabricated failure.
- [ ] Implement shared owner dispatch, including cancellation and failure of all queued/active responses in owner `finally`. A subsequent request/close observes the recorded terminal status immediately. A clean owner exit is not sufficient if context release, warning observability or survivor evidence is uncertain.
- [ ] Keep a connection pending until context/owner release is established. Never pop it or mark closed before release. Gather all close attempts even if the first fails; propagate control-flow failures, record ordinary failures stickily and make aggregate shutdown incomplete while any owner/failure remains.
- [ ] Route discovery and calls through owner dispatch with an internal direct path; retain main's discovery implementation and its budgets. Do not copy old A discovery bodies.
- [ ] Install the sanitized SDK warning observer at runtime construction, never module import. Keep at most one shared handler, explicit ownership across multiple runtimes and no strong references that prevent collection. Preserve warning endpoint checks and identity-bound survivor latches independent of ring overflow. Diagnostic capacity is 256 with an exact dropped count. Do not forward raw SDK messages, args, traceback or target data; do not mutate unrelated SDK records outside an owned context. Check the installed MCP 2.0.0 warning premise on each platform.
- [ ] Split server shutdown: serving-loop abandonment/cancellation of turns, permissions and reservations; stop sweeper and join all owned close tasks; detach/prepare session close on-loop; run blocking close hooks and runtime.close off-loop; apply state/outcomes on-loop; preserve existing Redis-last cleanup and primary failure behavior. Keep synchronous close_all compatibility for existing callers, but serving uses awaited `aclose()`.
- [ ] Clean `NdjsonOutboundChannel.request` in `finally`, including send failure, timeout and cancellation: remove only its own mapped future and cancel an unresolved future. Late responses become ignored, and cannot complete a replacement request.
- [ ] Tie candidate retirement to session lifetime, not a permission finally. Both session/new and renewal register ownership of published candidates; an answered permission must not prematurely remove the operator's later IPC trust path. Retire on session close/suspension and atomically replace the prior same-session/server candidate when publishing a successor. Each listener has a generation and fresh address. Stop/join/unlink only the captured generation; while its stop is incomplete, retain/report that handle and refuse or defer new listener start. At most one stale listener thread may remain owned. Serialize all IPC cleanup off-loop; never delete another session, concurrent candidate or newer listener/socket. Test real Windows pipe and WSL AF_UNIX stop/start behavior under owned local fixtures.
- [ ] Add focused tests: owner exit before/after queued call; open/exit failure; reserved close under pressure; ordinary and control-flow close failure; close-all attempts remaining peers; owned child exit; session isolation; cancellation/timeout/late response future cleanup; repeated denied renewals return future/candidate counts to baseline; concurrent IPC publish/consume/retire; listener handle retention if join is incomplete; warning unavailable/changed/survivor/ring overflow; no raw target secret in diagnostics; facade/connection/owner weakrefs become collectible after confirmed release.
- [ ] Verify `ClientMcpLeaseAuthority.acquire_allow_once` remains in-memory: source currently only returns a dataclass; `lookup_durable` only reads. Add a no-write spy regression across renewals; modify no trust-store production code.

Use one off-loop close worker per serial sweep. The existing eight-connection default and operation timeouts bound scheduled submissions; set a session close observation budget of server count times the effective operation timeout. A timed-out SDK context still retains its owner and is uncertain, not force-released. There is no new promise to forcibly kill Python threads or bound all process exit.

## Package 2 Idle admission and permission renewal

**Interfaces**
- Dedicated `DEFAULT_ACP_MCP_IDLE_SECONDS = 3600`, `MAX_ACP_MCP_IDLE_SECONDS = 2592000`, parser and `resolve_acp_mcp_idle_seconds(environ: Mapping[str,str]) -> int`; invalid input fails before `build_agent_harness_runtime`.
- Add registry/default/display for `OPTIMUS_ACP_MCP_IDLE_SECONDS`, agent-child-only, monotonic tighten/exact loosen. No TTL names or ambient environment reads.
- Adapter and library server constructors default `mcp_idle_seconds: int | None = None`; direct constructions remain disabled and start no sweeper. Bootstrap always resolves and threads the operator default 3600, including real Stage C composition. Keep injectable `monotonic_clock: Callable[[], float] = monotonic`. None is an internal composition default, not a new launch off setting.
- Add `record_turn_commit(session_id: str, turn_seq: int, *, committed: bool | None) -> None`, `note_turn_delivered(control: TurnControl, *, cancelled: bool = False) -> None`, `sweep_idle_mcp_once()`, `start_idle_mcp_sweeper()`, `stop_idle_mcp_sweeper()` and `aclose()`.
- Add public read-only `ConversationState.next_turn_seq`. Use it instead of adding idle reads of `_next_turn_seq`; no allocation behavior changes.
- Disposition adds `reopen_suspended(state: ClientMcpSessionState, request_permission: RequestPermissionFn) -> PermissionOutcome`, all-or-nothing publication.
- `submit_via_turn` and `deliver_envelope` return bool. Join only the normal TurnResponseEnvelope completion path; exception/outbound-error resend paths stay unarmed. Authoritative `rpc_response_delivery is FLUSHED` is separately required.

- [ ] In `_commit_turn`, record unknown immediately before prepare_commit, then known committed immediately after commit_after_final_flush (main line1604), before any notice/usage/alert await. In the prompt finally, record known noncommit only if no marker exists. A post-commit cancellation preserves committed; a partially failed preparation remains unknown.
- [ ] Verify writer ordering unchanged: normal outbound_writer lines228/233 publish authoritative state before line237 resolves source_future. Add real-writer tests including fallback/ambiguous/fail-closed branches; do not arm from future completion alone or change the writer's settlement algebra.
- [ ] Before allocation, use this prompt order: ordinary validation/busy checks; closing/reopen/quarantine gates; conversation.prepare_admission; if refused, retain the deadline and issue no renewal prompt; if admitted, snapshot execution mode and the attached-session context strategy/settings before any renewal await; invalidate the old idle_epoch; reserve/reopen only for a non-Chat suspended prompt according to that snapshot; recheck admission after renewal; then allocate the turn using the snapshot. Leave setters unchanged and responsive. A setter during renewal succeeds and affects only the next prompt. Use the captured configuration for AcpPromptTurn, AttachedTurn and associated notice decisions, and do not clear newer setter-publication/notice obligations. Test switching to Chat during Agent renewal: setter succeeds, the reserved turn still runs as captured Agent, the next prompt is Chat; also test a strategy change.
- [ ] Chat never reopens MCP and receives neither service nor permission broker, whether peers are active or suspended. The actual runner dispatches Chat to `_run_chat_answer` before tool planning, and that method accepts no MCP service; keep runner production unchanged. Test this through the real Chat runner with spies that fail on MCP open/list/call/permission. Returning to Plan/Agent later requires full renewal.
- [ ] Arm only after a known allocated turn outcome + matching idle_epoch/sequence + actual FLUSHED RPC result + no cancellation/teardown + still-live leased state with at least one actually opened peer. A distinct peer-close-hook indicator is acceptable; candidate-retirement hooks do not count as opened peers. Never-opened leases release nothing and must not trigger needless renewal. Pre-admission nonturns, unknown outcomes, ambiguous/suppressed/failed sends and server exception-resend paths never arm. A known allocated noncommit AcpOutboundError returned through the normal TurnResponseEnvelope does arm after FLUSHED. Writer _fail_closed resolves its future without authoritative publication, so NOT_ATTEMPTED correctly prevents arming. Pop consumed/stale markers and prune session state on teardown. The active map alone is insufficient. Name the idle counter idle_epoch to distinguish it from ConversationState.generation.
- [ ] Implement ACTIVE -> IDLE_CANDIDATE -> MCP_CLOSING -> MCP_SUSPENDED/QUARANTINED. The serial sweeper sleeps min(60, effective delay); it never busy-spins. Prepare/detach on-loop, run blocking hooks/pending query off-loop, finish state on-loop. Shield and track close work through sweeper cancellation and final shutdown.
- [ ] If warning observability is absent before close, perform no close, clear that deadline, record a fixed diagnostic and permit rearm only after a later determinate turn. Unknown release, changed channel or survivor evidence quarantines with `data.reason=mcp_cleanup_uncertain`. The documented entirely-between-snapshots logging-flip limitation remains.
- [ ] Reserve before renewal; renew former leased names in pinned order using fresh allow_once decisions; publish all leases and a new collectible facade atomically only after all succeed. Preserve unavailable servers and main's resolution-failure state. Denial/timeout/failure returns MCP_REOPEN_REFUSED, admits no turn and publishes no partial service set. session/cancel also cancels a pre-allocation reservation and its pending permission. It returns a non-turn success {"stopReason":"cancelled"}, restores MCP_SUSPENDED, allocates nothing, changes no conversation record and arms nothing. Do not log cancellation as a pre-run refusal. Clean its future immediately; manage candidates by the session-lifetime rule above.
- [ ] Add only MCP_REOPEN_REFUSED -32912, correct its docstring and error registries. Reuse REQUEST_CANCELLED for busy closing/reservation cases. Add the fixed reasons `mcp_reopen_refused`, `mcp_cleanup_uncertain`, `mcp_reopen_in_progress`, `mcp_closing` to the pre-run refusal allowlist and tests. Keep message content fixed and path-free.
- [ ] Tests cover exact boundary/deadline; unknown vs known noncommit vs postcommit cancellation; stale/out-of-order flush; busy refusal retaining markers; cap-closed and reservation refusals retaining deadlines/no permissions; Chat remaining suspended; Plan/Agent all-or-nothing reopen; cancellation before allocation returns a non-turn success with stopReason cancelled; successful setters during renewal affect only the next prompt; no-loop-blocking with another session answered while close remains in progress; shutdown joins through repeated cancellation; policy min/max/invalid/exact grant/default display; configuration invalidity before Redis construction; bootstrap/server wiring; no context/cost/route regressions.

Ordering is the primary responsiveness assertion. Retain the historical 0.5-second controlled slow-close and 0.25-second secondary timing bounds without returning to fragile 50 ms gates. Use events/handshakes; do not add deliberate CPU load.

## Verification and checkpoint

No commands in this section have run. Source inspection confirmed MCP 2.0.0 uses snake-case `InitializeResult.protocol_version`/`server_info`; keep those existing fields. Installed SDK modules are `mcp/client/stdio.py`, `mcp/client/session.py` and `mcp_types/_types.py`, rather than the old package layout. No initializer alias fix is proposed. Execute only after runtime/test authority and implementer assignment. Run from the new dedicated lane, with its own activated/frozen environment; never use a global interpreter or another lane's environment.

- [ ] Package-focused red/green selections preserve repository addopts, audit and run-context records. With the Windows environment activated:
  - SDK package: `uv run --no-sync pytest --no-cov tests/unit/mcp/test_client_sdk.py tests/unit/mcp/test_client_disposition.py tests/unit/mcp/test_local_ipc.py tests/unit/mcp/test_client_catalog.py tests/unit/mcp/test_client_trust.py tests/integration/mcp/test_client_sdk_local_stdio.py`
  - Adapter package: `uv run --no-sync pytest --no-cov tests/unit/acp/test_idle_mcp_suspension.py tests/unit/acp/test_spec_protocol.py tests/unit/acp/test_stdio_ndjson.py tests/unit/acp/test_outbound_writer.py tests/unit/acp/test_conversation.py tests/unit/acp/test_plan121_chat_mode.py tests/unit/agent/test_plan121_chat_runner.py tests/integration/acp/test_server_stream.py tests/unit/acp/test_server_mcp_shutdown.py tests/unit/acp/test_server_reader_ownership.py tests/unit/acp/test_server_redis_shutdown.py tests/unit/acp/test_main_wiring.py tests/unit/acp/test_stage_c_launch.py tests/unit/acp/test_test_composition.py tests/unit/mcp/test_client_supervisor.py`
  - Policy/observability: `uv run --no-sync pytest --no-cov tests/unit/acp/test_bootstrap.py tests/unit/acp/test_acp_subprocess_env.py tests/unit/acp/test_launch_policy.py tests/unit/acp/test_launch_gate.py tests/unit/acp/test_error_code_registry.py tests/unit/acp/test_debug_trace.py tests/unit/acp/test_typing_contracts.py tests/unit/tools/test_validate_publication.py tests/unit/tools/test_verify_plan996_logging_surfaces.py tests/unit/docs`
- [ ] The new local stdio module exercises the real official SDK and an owned local test peer. It is not marked requires_mcp_stdio, whose defined dependency is an independent digest-pinned Docker server. It claims no independent-server or external-ACP-client acceptance. Run children sequentially under existing containment. Validate PID plus creation identity before observing exit.
- [ ] Apply all affordable findings in a batch and rerun affected focused selections. Do not add a review after each subtask or run the full suite after each correction.
- [ ] Run `uv run --no-sync ruff check .`, one `uv run --no-sync mypy` (configured files=[src]), plus `git diff --check`; classify logging surfaces in the existing audit manifest, with no scanner exemption. Normal commit hooks remain required when a local commit is separately authorized.
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
| N7 bookkeeping | Future finally cleanup; session-lifetime candidates/successor replacement preserve trust ceremony; listener generations and serialized off-loop cleanup; in-memory allow_once verified; serialized off-loop durable reads; bounded close submissions. F6 renewal growth is included. |
| N8 privacy/logging | Counts/fixed codes/random internal tokens; no raw-path hash. Runtime-owned warning observer, premise tests, audit classification and retained snapshot limitation. |
| N9 configuration | Dedicated parser/default/display; validate before harness construction; no TTL names or hidden off value. |
| N10 errors | Main busy convention, new reopen code only, correct docstring and allowlisted refusal reasons. |
| N11 cancellation | Extend cancel to pre-allocation reopen and cancel/clean its permission; atomic facade publication retained. |
| N12 Chat | Keep suspended with no MCP service/broker and no permission; runner source confirms early no-tools Chat path. Snapshot configuration before await while leaving setters responsive; test old-turn/new-prompt behavior. |

## Explicit exceptions and completion boundary

No session TTL, durable runtime, eviction/Piece B, at-cap memory campaign, live model/service/editor proof, generic signal adapter, tool-output design, public Context7, user PC repair, shared hook/secret/inventory weakening, or cleanup. #240/#222 and existing parent owners retain those obligations. No whole-track closure follows.

Technical completion requires the full proposed contract, real SDK lifetime proof, focused checks, clean Windows/WSL gates/validity and consolidated independent acceptance. Local commit, publication, required PR CI, merge, actual-merge verification, issue closure and cleanup remain separately authorized operations.

Claude's final advisory 9–12 working days/difficulty high excludes approval waits; 13d is the permitted rounded estimate if later agreed for the implementing issue. It is not a delivery promise or a label edit.

## Final plan review corrections and recorded choices

The immutable v1 review is `evidence/2026-10-26-sandbox-delivery-audit/claude-review/claude-plan-review.md`. Claude accepted the plan conditionally on R1–R3 and explicitly said no further round was needed once those text corrections were folded in. This complete v2 folds all three in, and addresses the affordable material notes together. It does not convert plan acceptance into runtime execution authority.

| Final review item | v2 disposition |
|---|---|
| R1 setters | Setters stay unchanged/responsive. Snapshot the admitted prompt's mode/context configuration before await; allocation uses the snapshot. Add mode and strategy setter concurrency tests, including Agent-to-Chat during renewal. |
| R2 cancel response | Cancelled pre-allocation renewal returns a non-turn success with stopReason cancelled; no allocation/history/idle arm, no pre-run-refusal log. |
| R3 trust ceremony | Candidates survive the permission answer. Retire on session close/suspension or same-server successor; retain at most one candidate per live session/server. No answer-time retirement is authorized without separate ceremony evidence. |
| N-a owner warning record | The owner itself brackets its context exit with both warning snapshots and stores them with survivor/exception/exit facts. A close after natural owner exit consumes that terminal record immediately, never waits on a dead queue; only observable/equal snapshots, no survivor and clean context exit certify release. Test natural child death and unobservable/failed exit. |
| N-b IPC generations | Fresh generation/address; captured-generation-only stop/join/unlink; retain/report an incompletely stopped listener and admit no replacement until it terminates. One serialized off-loop cleanup lane. Tests cover real AF_PIPE/AF_UNIX, concurrent publication, no lost handles and no unlink of a newer socket. |
| N-c repeated cancellation | Shield and track every off-loop session/runtime/IPC close. A second cancellation must not detach the worker: continue joining the same owned job, retaining the underlying worker/future identity. An outer observation bound yields incomplete ownership, never a fabricated release or application of abandoned results. Add double-cancel tests. |
| N-d fixtures/tests | Create the peer script and shared support module; no unit imports from integration/e2e helpers. Admit the enumerated server stream, MCP/Redis shutdown, reader, composition, Stage C and supervisor tests. The live Redis module remains read-only/UNRUN under its separate tier. |
| N-e constructor defaults | Direct adapter/server default None; bootstrap always supplies resolved 3600. Existing library compositions remain disabled unless explicitly wired. |
| N-f join/counter | A normal TurnResponseEnvelope carrying a known allocated noncommit error can arm after FLUSHED; server exception-resend and writer fail-closed/NOT_ATTEMPTED paths cannot. Call the counter idle_epoch, distinct from ConversationState.generation. |
| N-g keyring reads | Newly repeated renewal lookup_durable reads run in the reserved renewal's serialized off-loop lane, with shielded/owned completion and no lease publication after cancellation. Keep trust-store production code read-only. Existing session/new synchronous keyring reads are a recorded pre-existing residual under #302, not newly multiplied by idle cadence or claimed fixed. |
| N-h unnecessary prompts | Arm only when an actual peer was opened; do not count retirement callbacks as peers. Decline the optional separate Chat-activity clock: retain the approved admitted-prompt activity semantics, so admitted Chat can postpone suspension of already-open peers; suspended Chat never reopens them. This avoids an unrequested second idle policy. |
| N-i commands/IDs | Run one configured Mypy selection. The existing finite outbound request-ID iterator (90k IDs) is a disclosed pre-existing server residual under #302, not silently fixed or represented as unbounded by this port. Renewal consumes IDs; the receipt must disclose that limit. No stress loop is authorized to exhaust it. |

**Additional exact interfaces and tests:** session state exposes `has_open_peer() -> bool` based only on registered actual peer ownership, separate from candidate-retirement hooks. Disposition serializes renewal keyring reads and IPC cleanup and provides an awaited drain of its tracked jobs before runtime teardown. Retire-session callbacks are detached/prepared on the serving loop and executed in that owned cleanup lane. Listener generation cleanup removes only the address it created; AF_UNIX ownership is checked before unlinking, and no newer generation may be removed.

Required final focused assertions additionally cover: a clean natural owner exit vs an exit exception or unobservable warning channel; a second serve-task cancellation while a worker is still closing; candidates remaining consumable after an answered permission until session lifetime ends; bounded replacements across repeated idle cycles; fresh listener generation/address and retained incomplete stop; default None library construction starting no sweeper; renewal keyring read leaving the serving loop responsive; current session/new behavior unchanged; known noncommit normal error envelope arming vs writer fail-closed not arming.

**Canonical filing:** the canonical design file is the self-contained operating specification created in the admitted specs path; old assessment/review paths in this planning package are archival provenance only. Canonical v2 and its receipt must carry these full contract corrections and source-bound acceptance qualifications; no workstation archive is an execution dependency.
