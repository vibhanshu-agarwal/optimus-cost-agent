# Plan 11.7 v6 — durable ACP sessions and Zed resume

> **For implementers:** use the repository's execution workflow after approval of the exact
> successor and the offline implementation scope. Checkboxes below describe verification tasks.

Prepared 2026-11-26. **Draft for operator review.** This is a complete forward-only successor to
Plan 11.7 v5. It reconciles the #304 wire contract with #240's first-prompt gate and carries forward
the durable-session design. Issue [#240](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/240)
owns the plan. Issues [#230](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/230) and
[#254](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/254) retain feature and capability
custody. [#304](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/304) and
[#319](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/319) own the scoped wire delivery.

**Goal.** Ship the reviewed #304 ACP wire behavior with a compatible offline collector checkpoint,
then retain the existing durable session and current-Zed acceptance sequence.

**Architecture.** Use main's existing conversation, turn, writer, session retention, context, cost
and MCP authorities. Redis supplies a persistence projection for the future feature. The existing
evidence pipeline uses a separately versioned scenario for v6 with seven exact refusal descriptors
and a new empty approved-run registry.

**Stack.** Existing Python/uv lock, pytest and Ruff, existing collector, Redis and ACP interfaces.
Real acpx and Zed remain requirements for the corresponding live acceptance tiers.

**Specifications.** The adopted D1–D13 package and rationale are in [ADR-043](../../decisions/ADR-043-durable-acp-session-retention-and-replay.md)
and the [v5 adoption record](../reviews/2026-11-16-plan-11-7-v5-adoption-record.md). The proposed #304
wire decisions are in ADR-047 in the #304 candidate. This plan restates the execution contract.
The predecessor and historical data listed below are independently source-bound.

## Authority and forward-only adoption

- The operator's 2026-11-26 reply, “Approved,” immediately followed the request to extend the offline
  scope to a versioned #240 plan and collector update. That turn records scope. The changed fixture
  contract, architecture choices and acceptance commands in this draft are Codex proposals.
- This supersession carries forward the operator's adopted D1–D13 decisions and expands D9's
  first-refusal case inventory from six to seven. Exact plan adoption, implementation and publication
  follow the repository's approval workflow. The proposed release covers the offline compatibility work only.
- Keep v5 byte-identical. Its adopted SHA-256 is
  `288bf4f896a559a6ca91a14bc1065806357883b5e09ebc4fca6856afe717c83c`
  and its Git blob is `df78e84bc44181ebb8ab9d78aeff8c92289506e7`. After the approved issue disposition,
  deliver this complete v6 under `docs/superpowers/plans/` and move v5 to the flat archive with
  identical bytes. Update mutable indexes, roadmap and the single live-plan pointer in the same PR.
  Keep v1–v4, historic amendments, ADR-043, approval records, seals and raw/sanitized artifacts immutable.
- #240 remains Codex-owned, open and blocked on its live gate. #304 stays in scope until reviewed
  offline code and verified CI can proceed through a separately authorized merge. #334 keeps its
  existing custody.
- The offline checkpoint releases no E3 invocation, E4 acceptance, paid/provider call, real Optimus
  keyring access, historical rerun, P1–P6 implementation, merge or worktree cleanup. Existing E3
  design and budget issues remain with #240. The current plan leaves production feature prerequisites
  visible and retains the completion gate.
- #256 remains under its own issue custody and is open for its own disposition. Retain its failed,
  UNRUN and superseded-premise evidence. #241's dormant prerequisite drive/two-Zed gate remains held.

## Baseline and adopted decisions

On 2026-11-26 the integration base was verified at main `e3272e7` and the ACP source was staged as `3886a8f` after two test-only corrections. The prior source census passed on main and rejected the staged source. The source records below describe the original v5 assessment and provide historical custody.

| Input | Exact identity and use |
|---|---|
| Original v5 assessment base | `6e5478a0225671ae9ed566b494f66a300562a6b5`, merge #475; source assessment only, not an acceptance result |
| Sandbox code reference | Tag `sandbox-main7-ported-register-docs-20261014`, target `e521264e9f0fae08a8b1e42887ce2e0ae8bd1c2c`; selective reference only. This docs milestone is not acceptance of a durable-session class |
| Observed sandbox checkout | `f49cc0bb7a33f299917eb672770672c8ca780a89`, `experiment/cross-cutting-sandbox`, describe `sandbox-main7-ported-register-docs-20261014-2-gf49cc0b`; final two commits change only the register. Git diff confirms no src/tools/tests/pyproject/lock delta from the tag |
| V3 ratified historical source | `3e9b8fa26e00d3c90d0b9ea4182bc67f13a3de47` |
| V2 planned historical source | `cd7014d894576483fe4d2f9d59d2ecbb2c67ee03` |
| Historical candidate repairs | `fc80403060f578986c287686c27d935a8043dc5a`; Git object available, acceptance not established |
| Later v3 candidate | `6208177b55237132c4087652de87c78f21159fb2`; contracts/collector/verifier available, authorizing redaction emission still deferred; not accepted evidence |
| Unfinished v3 successor | `60488daa3df31a0d12d22db61ebc3797a9ffd0b1`; preserve registry/gather/test repair history, inspect selectively, never promote its fixtures as live evidence |

| ID | Adopted v5 choice carried forward in v6, reason and acceptance boundary |
|---|---|
| D1 | Rebase the authorizing gate onto the pinned current main, then re-pin at execution. Do not claim equivalence to cd7014d/3e9b8fa. Old runs remain supporting history; a fresh, pipeline-native current-source run is mandatory. Source drift requires a reviewed applicability delta before reuse. |
| D2 | Use a new main ledger schema version 2 under the existing `optimus:acp:session:{session_id}` family. Sandbox schema-v1 assumes fixed mode and the old 512 KiB conversation; main has mutable mode/strategy, attached source limits, exact approval facts, cost receipts and routing state. Add inert durable interruption markers so old history cannot load as complete after an effect/crash. **Proposed conservative consequence: closing Zed before a turn is sealed blocks later resume even for no-tool Chat; expiry deletes the record rather than repairing it.** Do not bypass final-flush commit authority to manufacture a cancelled turn. Reject incompatible/unknown versions; do not reinterpret/overwrite sandbox keys. No automatic legacy migration or interrupted-turn recovery is included. |
| D3 | Preserve main's independent positive MCP idle delay, process-local 64-session cap and retirement/quarantine owners. Proposed durable TTL default 86,400 seconds, range **300–2,592,000**, and lease 300 seconds: TTL must be at least the lease. Refresh on acknowledged durable state writes, active-turn renewal and successful load; clean release preserves remaining retention, and read/refused load never refreshes it. Use Redis server time/TTL, not cross-process wall clocks. Active turns renew through the existing runtime owner; idle ownership may lapse and must be reacquired before admission. An expired/missing live record refuses continuation with an explicit notice, never a partial recreate. The detailed safety/cleanup contract below applies. These are new proposals, not existing main policy; the sandbox parser's 1-second minimum is deliberately not adopted. |
| D4 | Cover both absent-engine and attached-engine launches, mode/strategy changes, current Auto/cost behavior and opt-in memory indexing. Restore durable semantic state; rebuild runtime resources from current approved configuration. Never serialize live workers, buffers, tools, secrets, grants or pending effects. Attached-only support is not deferred out of #240. |
| D5 | Retain v3's non-waivable positive zero-entry reachability stop and all required evidence tiers. Do not weaken the gate to make current Zed pass. Keep four implementation checkpoints, including pre-live machinery acceptance and final evidence acceptance. |
| D6 | Adopt the closed emission inventory below: preserve main's live payloads/best-effort behavior, store exact required UI history and rebuild current status/configuration. Stage before send; finalize atomically after the authoritative committed or healthy NOT_COMMITTED outcome under D8. Retain the local pending intent/staging until acknowledgement; atomic storage may apply despite a lost reply, as qualified below. No live output is removed or uncommitted UI stream silently discarded. |
| D7 | Fix the proposed **8,388,608-byte** encoded ledger and equal staged-buffer bounds, including replay, attempts, accounting and markers. This is an unmeasured agent-selected safety limit. P1 proves exact fit/refusal/headroom; P2 qualifies real Redis/deadline/resource behavior before CP3. Bounds are not a memory pass. Never truncate or silently evict; changing an adopted value needs a complete reviewed successor. |
| D8 | Select **retain healthy uncommitted UI replay**. Persist an inert NOT_COMMITTED attempt projection and its exact staged stream, preserving canonical model records while retaining consumed sequence/cost facts. Reject the discard/live-only alternative. Exact healthy-finalization criteria below prevent this from becoming interrupted-effect recovery. |
| D9 | Expand the current-Zed gate to each registered first-refusal response class with an empty persisted stream, including the v6 busy case, in addition to no-prompt A-prime and prompted A/B. Any positive empty-reopen binding/load signal latches ZERO_ENTRY_REACHABLE_STOP. Fixture-based client characterization is not production/Gateway/MCP acceptance. Healthy finalized uncommitted attempts are non-empty by construction and need a separate real-production proof in P5. |
| D10 | Resolve cost completeness by acknowledged capture coverage at an explicit watermark, not finalize_turn or a queued close. Preserve known costs; missing/gapped/late/unconfirmed coverage remains incomplete. Restore without re-appending old events. Detailed rule below; no new billing authority or provider polling. |
| D11 | Trust inputs come from the reviewed checkout: registered scenario plus committed sanitized approved-run registry/run spec, outside bundle-root. Accept only hash-bound accepting private-review receipts. Acquisition host/operator is trusted; public integrity checking does not authenticate a malicious same-privilege collector. No new PKI/service is added. |
| D12 | Evidence lane stays on the accepted main and does not import #469's unmerged shared files. Before P1 touches local_infra/memory_session/memory_workspace, use a reviewed integrated main pin or exact owner clearance. That release gate is not a declaration that the owner has cleared anything or that all #469 work must close first. |
| D13 | Fix metadata mechanisms: 8,192-byte intent/control reserve, active renewal every 100 seconds and five-second end-to-end mutation deadline, with no Redis wait under lifecycle/settlement/writer locks. These are unmeasured proposals requiring resource qualification. The 64-session cap is local, not a global Redis quota; deployment budget/no-silent-eviction policy must be established, no new quota/config service is implemented. |

### P0 decision disposition

The operator adopted D1–D13 on the exact v5 bytes. ADR-043 records the accepted durable-session design and empirical open items. The seven-case refusal inventory and offline tasks below are the v6 design changes. Execution needs its own main re-pin, verified artifacts and the applicable authority at each tier. The historical Aug22 seven-file manifest is byte-matched supporting history. Failed, invalid, unsealed and UNRUN material keeps its original disposition.

## Scope

Included: pipeline-native Task 0; private/hygienic provenance; new session ledger, canonical snapshot
and hydration; Redis CAS/TTL/lease recovery; durable new/prompt/finalize/load; MCP re-disposition;
ordered, fully flushed non-empty replay; crash/concurrency/failure handling; current context and cost
compatibility; independent acpx restart proof; real-Zed binding retention; release evidence and
documentation freshness. The v2 obligations are restated below rather than incorporated by title.

### Explicit Exceptions and retained custody

| Excluded action or feature | Owning custody and retained obligation |
|---|---|
| Automatic import/migration of sandbox sessions or bulk Redis key cleanup | #240/#230: document schema incompatibility and preserve old keys; any requested migration needs a reviewed successor before execution |
| ACP `session/resume`, `session/list`, `session/fork`, `session/delete`, including a new user purge API | #230 retains future feature custody; #240 documents that no user purge path is supplied and TTL is not immediate deletion |
| Raising either current conversation/source cap; new compression, summarization, pruning or eviction beyond approved TTL/current retention | #230 and existing Plan 12/#469 custody; preserve current attached strategies and configured limits, without introducing a new history policy |
| Machine-power-loss durability, Redis persistence configuration changes or a new backup/recovery service | #240/#230: qualify process-restart durability against the configured Redis service; no fsync/AOF/replication guarantee is added |
| Provider-key custody, Gateway redesign, new MCP catalog/discover-and-connect or old origin-A correlation budgets | Existing #222/#469 and #256/#241 custody as applicable; #240 integrates existing services only |
| Resuming an in-flight tool operation, replaying an effect or restoring a permission grant | #240: load historical committed state only, classify unresolved delivery/effects fail-closed; new actions require current authority |
| Automatic recovery of any unsealed interrupted turn, including no-effect Chat | #230 retains this limitation/future recovery custody; #240 may close only with the limitation accepted and documented. Do not close #230 by implication while it owns this deferred obligation |
| Discarding healthy uncommitted UI replay | Rejected alternative under D8, not a deferred shortcut; #240 must retain it while preserving canonical NOT_COMMITTED semantics |
| Global application session-key quota, broad capture closed-map retention, new Redis administration service | #230/#302 retain broader resource work; #240 requires declared deployment capacity/no-silent-eviction qualification and truthful OOM/expiry handling, without claiming a global key-count bound |
| Reviving the old #256 retry campaign or #241 two-Zed experiment | #256/#241: dormant until separately dispositioned; neither is completed by this plan |
| Closing broader MCP/resource or runtime-audit work | #222, #302, #317 and #307–309 remain separate; reuse verified interfaces without claiming class-wide closure |
| New context strategies, model routes, memory-index mechanisms or changes to M1 evaluation | #469 and its existing Plan 12 custody; #240 tests compatibility only |
| Broader P9.8-FU-5 depth/refusal work | Existing P9.8-FU-5 record in the transitional register until migration; report the resume-dependent criteria separately, never close the parent implicitly |
| Publication beyond the scoped offline draft, merge, live services, paid calls, and cleanup | Operator authority retains these gates. #240 owns E3 and future release. |

## Prerequisites

`unknown` is not a pass. P0 establishes each unknown before the dependent task. Machine state belongs
to the operator; implementers prepare exact bounded commands and need not ask repeated routine
questions within an existing grant.

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|---|
| Code/state | Main contains durable end-to-end session/load | no | Implementation agent / #240 | genuinely absent, buildable; P1–P4 |
| Code/state | Pipeline-native v5 collector, registry, private-receipt ingress and offline verifier present | yes | Codex / #240 | E1–E2 machinery shipped; the v6 source compatibility and checkpoint acceptance need their exact checks |
| Code/state | Current-owner map independently accepted, including Plan 12 session state | no | Codex / #240 | genuinely absent, buildable at P0/E4 |
| Code/state | Historical custody locatable | yes | Operator / evidence custodian | September archive found; seven Aug22 bytes match their CSV. Validity/redaction/acceptance are not established by that check |
| Code/state | Accepted integration boundary for #469 shared memory files | no | #240/#469 owners | genuinely hard external release before P1 touches three known files; E1/E2 exclude them, no need to wait for whole-issue closure |
| Services | Dedicated test Redis with required TimeSeries capability and isolated session-key namespace | unknown | Operator | P0 inventories; provisioning/start is merely unauthorized if available; unavailable service is genuinely hard |
| Services | Real Gateway and current approved launch/configuration usable | unknown | Operator | P0 inventories; merely unauthorized if provisioned, otherwise genuinely hard |
| Services | Memory-on restart tier: approved ADR-037 dedicated index Redis, provisioned embedding artifact, authenticated Gateway index route and current memory launch approval | unknown | Operator / #469 service custodian | P0 inventories separately from ACP test Redis; merely unauthorized if provisioned, otherwise genuinely hard. Memory-on acceptance remains required, not satisfied by memory-off units |
| Tooling | uv/Python/frozen deps and separate Windows/WSL environments | unknown | Implementation agent; operator machine custody | P0 inventory; missing environment genuinely absent/buildable |
| Tooling | Current real Zed binary/version/revision, exact executable and supported profile/DB ceremony | unknown | Operator | P0 preflight; client behavior external/genuinely hard until measured |
| Tooling | Independent acpx client version compatible with pinned ACP schema | unknown | Implementation agent | P0 inventory; historical 0.12.0 is reference, not an unverified current version mandate |
| Credentials/authority | Exact v6 adoption and scoped offline implementation from current main | no | Operator | merely unauthorized; v5 adoption and historical TTL decisions are already recorded |
| Credentials/authority | Separate bounded live/paid approval and current credentials without disclosure | no | Operator | merely unauthorized if provisioned; otherwise genuinely hard |
| Human interaction | Trusted hermetic Zed workspace, Agent-panel start and lifecycle GUI ceremony | unknown | Operator | P0 preflight; merely unauthorized if available |
| Cost | Per-run prospective cost reservation and stop on unknown usage/cost; paid prompts authorized | no | Operator | merely unauthorized; no dollar budget invented in this plan |
| Services/capacity | Declared ACP Redis capacity/eviction/retention budget and resource-qualification release | unknown | Operator | no service queried; genuinely hard until established. A 64-session process cap does not bound all retained server keys |

P0 found installed Zed1.27.0/app revisionc84af5b99cbc366d675064e52b23664a015b6e35, acpx0.12.0,
Node26.5.0 and WSL2 registration by metadata only. These do not satisfy runtime/client/environment
readiness. Re-pin binaries/versions/launch modules when their future tier is separately released.

## Global constraints and durable contract

1. One canonical `ConversationState`/`AttachedConversationState` family; one `TurnControl` per turn;
   one process `NoticeControl`; existing response handles, settlement and `DedicatedOutboundWriter`.
   Add immutable projection/hydration APIs, not parallel execution state machines or a second adapter.
2. One process `RedisRuntime` client/owner loop for session persistence; use `required_client` and
   `run_async`/the established runtime submission boundary. No second session Redis pool, cross-loop
   raw-client use, hidden retry, silent memory fallback, or fabricated capability success.
   The separately governed Gateway memory-index Redis is a different existing service, not a pool
   to repurpose for ACP sessions.
3. Schema v2 contains exact session ID, canonical cwd, creation/expiry, monotonic revision, bounded
   ownership lease, current execution/configuration state, canonical conversation, ordered sanitized
   replay and the semantic session fields listed below. Closed-world validation rejects duplicate
   keys, unknown fields, non-finite numbers, bool-as-int, malformed hashes, impossible ordering,
   mismatched session IDs, unsupported schemas and over-limit or invalid snapshots.
4. Snapshot round-trip preserves exact five-field canonical turns, generation/next sequence,
   disposition, warning state, storage class/limit/reservation, canonical cost projection and its
   identities. Never reconstruct model history from replay or telemetry. Absent-engine storage
   keeps `524_288` bytes. Bind attached snapshots to the actual attachment's source limit and record
   reservation, not a hard-coded hydration constant. Current shipped defaults are `1_048_576` and
   `131_072` respectively (`src/optimus/context/shipped_policy.py`); other approved attachment values
   must round-trip exactly or refuse a mismatch. Preserve recoverable-refusal semantics.
5. Also project current mode, context strategy, exact historical approval facts, valid checkpoint
   provenance, cost/settlement idempotence, alert crossings, and previous Auto-routing facts needed
   for the next turn. Historical approval facts are permitted inert data, not executable permission
   answers or grants. Revalidate checkpoint/history compatibility and current launch policy on load.
   Recompute derived config publications/notices safely; do not replay obsolete permission prompts.
   Receipts may arrive after finalization. Persist outstanding invocation/attempt identities and an
   incomplete-accounting flag until D10
   coverage/identity closure is proven at its verified watermark; a crash never turns unknown cost into zero
   or complete. Hydration restores inert receipt/deduplication state without re-appending historical
   events to DurableCapture. Reconcile only attributable retained receipts; otherwise remain incomplete.
6. Rebuild MCP and memory workers from current request/configuration and trust. No serialized
   credentials, env values, raw permission answers, raw telemetry, unsaved text, index bodies,
   locks/futures/clients/handles or executable pending-effect payloads. Inert closed-schema intent and
   finalization facts are permitted. Sanitize all replay paths, including new
   context/memory/tool/cost notices. Preserve replay-versus-live provenance explicitly.
7. A replay entry is the exact sanitized ACP `session/update` payload plus turn sequence, within-turn
   ordinal, provenance and canonical SHA-256. Include user_message_chunk from the admitted sanitized
   prompt and every stored+replayed update in D6's inventory. No JSON-RPC request IDs persist in the
   ledger. Preserve current live behavior and existing sanitization. Do not add file/source bodies,
   context packs, READ results or index/unsaved text beyond already-admitted sanitized canonical
   conversation text. A stored-class payload failing privacy validation makes durability fail closed;
   do not remove live output, alter the sent transcript or silently omit entries while claiming a
   complete durable session.
8. Creation grants ownership atomically with SET NX; append/finalize/config persistence and lease
   renewal use one revision/CAS transaction. WATCH conflict is classified, not retried. TTL stamping
   and expiry use Redis server TIME/expiry. Clean detach releases exactly its own known lease; ambiguous
   mutation leaves bounded expiry instead of issuing an unsafe release against an unknown revision.
9. Local use leases/capacity and durable ownership leases are distinct. Load reserves provisional
   capacity before expensive setup; a failed load retires that provisional identity using the current
   owner and quarantines uncertain cleanup. Repeated loads cannot grow maps, close-result retention,
   pending setup, worker futures or active MCP ownership without bound.
10. Load permits no `{}` success for zero-entry replay. Every required replay notification must have
    a conclusive dedicated-writer flush before the single final `{}`. Cancellation, uncertain flush,
    teardown and persistence failures preserve the authoritative classification and never re-execute
    a tool, erase an effect, double-count cost or send a second response.
11. Top-level `agentCapabilities.loadSession` is advertised only when the production durable path is
    configured and supported; never `sessionCapabilities.resume`. Preserve all other current
    capability/configOptions fields. Startup and storage failure never downgrade silently.
12. Freeze failed attempts, source/tree identities, skips, UNRUN, unsupported platforms, reused
    measurements and warnings. Acceptance evidence must identify actual tested bytes and command
    context. A previous PR synthetic merge or an earlier branch head is not actual-merge CI.

### Schema-v2 and healthy finalization contract

Use exact session ID `^session-[0-9a-f]{32}$`, not bare UUID hex. Every nested record is closed;
reject duplicate/unknown keys, bool-as-int, nonfinite numbers, invalid UTF-8/identity/digest/order and
unsupported variants. Canonical JSON sorts keys, uses compact separators and lossless finite decimal
strings for money. Integers/counters are signed64 where bounded; no overflow/coercion. Gateway IDs
are accounting identities, never JSON-RPC request IDs.

Root fields: schema_version=2; session_id; canonical_cwd/path_platform; positive revision;
created_server_ms/expires_server_ms; lease{owner_token,expires_server_ms}; compatibility;
configuration{execution_mode,context_strategy}; conversation; replay; attempt_finalizations;
interruption; accounting; context; routing; notices; mcp_identities. No alternate runtime model.

TurnIntent is null or closed {state=in_flight, turn_seq, base_revision, base_history_generation,
base_history_digest, intent_nonce, armed_operation_id|null, effect_may_have_applied,
model_accounting_may_be_open, started_server_ms, last_precondition_server_ms}. Non-null refuses load
even after lease expiry. Nonce32 lowerhex, digests64 lowerhex, counters signed64/nonnegative as
appropriate; host-generated operation ID max512 non-escaping ASCII bytes; exact booleans/enums.
No tool arguments or copied execution gate. Reserve8192 encoded bytes before admission; maximum
offline marker shape968 bytes is arithmetic only. Lease owner_token/expires both null only on
release; otherwise exact non-secret owner identity and server time, no caller clock.

Conversation stores exact ordered five-field records keyed by turn_seq, generation, next_turn_seq,
disposition, actual storage class/limit/reservation, warning state and legacy/projected cost facts.
Allocated sequences may have gaps; never require next_turn_seq==record_count+1 or roll it back.
Context stores inert ApprovalFact{turn_seq,artifact_hash,decision,scope} and optional valid
SummaryCheckpoint{revision,covered_turn_ids,source_digests,strategy,parameters_digest,format_version,
summary_text}; HistoryRevision{session_key,generation,last_committed_seq,digest}. Preserve committed
AutoDecision values/last committed tier; an uncommitted Auto attempt never becomes previous-tier state.
Current mode/config persist through their existing setter/publication owner. Safe MCP fingerprints
use the existing keyed normalization, never raw descriptor credentials, argv secrets or grants.

ReplayEntry stores session/update params, turn_seq, nonnegative within_attempt_ordinal, provenance
(replay_user_prompt/live_agent_update), canonical SHA-256 and owner_kind(committed_turn/
uncommitted_attempt). It must match exactly one canonical committed record OR an eligible inert
AttemptFinalization; never both, never an unresolved attempt. A sanitized admitted user chunk is
ordinal0, followed by that attempt's exact stored-class live updates. Order is consumed sequence then
ordinal, including healthy uncommitted attempts, not regenerated text or model-history insertion.

AttemptFinalization fields: turn_seq, base_history_generation/digest, conversation_commit=
NOT_COMMITTED, authoritative terminal settlement, final_delivery, rpc_response_delivery, effect_state,
mcp_dispatch_armed, replay_count, first/last replay ordinal, sanitized_prompt_sha256, accounting
generation. It is persistence DTO only. Persist this record plus exact staged replay and the current
allocator/cost facts in one CAS; leave canonical records/generation unchanged. All allocated
sequence/replay/receipt identities remain unique. A later model request still excludes this attempt
from canonical model history, exactly as same-process main does.

**Healthy eligibility is conjunctive:** valid admitted attempt and original TurnControl facts;
transport intact; RPC response conclusively FLUSHED; every declared terminal update conclusively
flushed (or none required); authoritative NOT_COMMITTED; refreshed effect NONE; no armed/started
MCP call; no delivery-indeterminate state; no persistence/lease uncertainty. Everything else retains
intent and refuses load. Pre-admission/MCP-renewal refusals never allocate an attempt or intent.

Begin intent after final prepare_admission, sequence allocation and binding the original active
TurnControl, before Auto/model/tool dispatch. For a committed turn retain the existing final-
notification-flush/commit boundary; do not invent an extra canonical insertion. For a healthy
uncommitted turn finalize only after its RPC flush. Freeze the original outcome but retain the
existing active-session reservation/use lease until persistence acknowledgement or classified
failure. Defer its existing removal callback as needed; no second active-turn map/controller.
An immediately pipelined next prompt is refused by main's existing REQUEST_CANCELLED
"a turn is already in progress" while healthy-uncommitted finalization is pending, for up to the
five-second deadline after its RPC reply. Choose this explicit refusal rather than a new wait queue.
For committed turns await seal_committed after original canonical commit/required terminal update
flushes and before returning the response envelope for RPC send; do not defer it to an unawaited
queue. Existing RPC/delivery authority remains intact. For healthy-uncommitted cases only, RPC flush
necessarily precedes finalize_uncommitted; retain the active slot/use lease through its acknowledgement.
Failure after a response never produces a second RPC response; keep divergence/intent and the original outcome.
Use the existing server finalization path after delivery classification and before releasing the
request use lease: freeze original TurnControl once, defer only its active_map_remover callback
while the storage projection finalizes (a wrapper installed at original TurnControl construction
defers that existing synchronous remover; no replacement control), await bounded durable completion, then invoke the existing
remover once or retire/classify on failure. Keep settlement telemetry/frozen outcome authority.
Storage outcomes are handled inside this path, never raised into a second ordinary RPC error send.
Transport/cancelled/unknown outcomes fail eligibility and retain intent; no new controller/map.

### Accounting closure and hydration contract (D10)

ReceiptRecord has exactly the current StageReceipt26 fields: session_id,turn_id,stage,attempt_id,
gateway_request_id,outcome,reported_cost_usd,recorded_at,requested_model,role,route,reasoning,
quantizations,resolved_model,provider,resolved_provider,strategy,revision_digest,registry_hash,
input_tokens,output_tokens,cached_tokens,provider_request_id,http_status,gateway_usage,post_teardown.
Nested normalized GatewayUsage21 fields: gateway_request_id,provider,provider_request_id,cache_hit,
billing_units,cost_usd,service,native_unit,model,model_version,price_snapshot_id,resolved_provider,
resolved_model,input_tokens,output_tokens,total_tokens,reasoning_tokens,cached_tokens,cache_age_seconds,
route_request_id,attempt. Reject raw response/extras; enforce source equality/finite/nonnegative rules.
Recorded_at/post_teardown retain bookkeeping, excluded from facts() equality as source defines.

Snapshot receipt/dedup identities, finalized IDs, invocation IDs/states/pending counts, integrity/
unknown facts, legacy-cost application identities and alert crossings under existing owner locks.
Never wait for Redis/capture tickets while holding those locks; enqueue immutable generation-tagged
projections and choose the current storage revision inside serialized runtime-owner execution.
Config/canonical/cost commands merge their own domain only; stale cost/config snapshots cannot
overwrite a newer domain generation. A local obsolete projection is classified without a write;
that is not a retry of a cross-process WATCH conflict.

TurnSettlement.finalize_turn is not proof of cost closure. DurableCapture.close returns when queued,
not written; pending workers keep an epoch open, failed close reopens it, and late receipts append
without rewriting the old close. Add owner-local capture-coverage export: epoch/stream identity,
acknowledged close record locator/hash, ordered identity-parts digest/counts, rejected/unconfirmed/
pending/unknown/integrity counts and capture watermark/generation. Completeness requires a written
host_complete close, attributable exact expected/settled identities, zero unresolved counts and no
later contradictory/late/gap event through the verified watermark. Pure no-dispatch state can prove
zero without inventing receipts. A queued close or absent capture cannot establish completeness for an executed invocation.
Keep this strict rule: if optional DurableCapture was disabled/unavailable, resumed accounting for
executed work remains coverage_unverified/incomplete even when in-process settlement had completed.
Known subtotal is retained; pure conclusively proven no-dispatch zero is the stated exception. This
is a deliberate availability-of-cost-certainty limit, not an integrity failure or a newly mandatory
capture setting. The ADR and P1/P5 reports must disclose it.

Before load or publishing a resumed cost meter, reconcile stored coverage against retained capture
records through an existing host-config-root resolver, not a path supplied by the ledger. Missing,
unreadable, gapped or later invalidating evidence preserves known subtotal/receipt identities but
sets an explicit owner-local coverage_unverified/incomplete flag. No fabricated integrity conflict,
zero charge or fallback history. Completeness is qualified as-of the verified watermark, not an
irrevocable future claim. New late receipts invalidate/recompute through the same owner and CAS.
Hydrate inert receipt state without record_attempt/capture append, invocation dispatch or old epoch
reopening. Existing capture event meanings remain unchanged. Test crash/late/queue-failure and
same-process/as-of restoration; all such behavior is UNRUN in this planning task.

### Interruption, divergence, expiry and size contract

Schema-v2 markers are inert projections of existing TurnControl/settlement facts, not another
execution authority. After final admission/allocation/control binding and before dispatch, acknowledge one CAS
marker naming the turn, base revision and `in_flight`. Before an irreversible operation, record
`effect_may_have_applied` at the existing effect gate; after its outcome is known record the existing
effect classification when possible. An after-effect write alone cannot close the crash window.
A failed/uncertain marker write prevents new dispatch/effects. A crash with a marker, including a
crash between the actual effect and its acknowledgement, **refuses load** as `DURABLE_INTERRUPTED`;
it never hydrates older state as complete or automatically executes work. Clear intent only by an
atomic eligible committed seal or D8 healthy-uncommitted finalization, including exact staged
replay, current allocator and accounting. No canonical insertion is invented. Unknown delivery/
effects, unsafe no-insertion cases and transport loss remain blocked.

**Chosen proposed clean-close policy (review option b):** clean stdin EOF during a running,
unsealed turn does not clear the marker, whether or not an effect marker exists. Even a no-tool Chat
turn then refuses later load as DURABLE_INTERRUPTED. Main's `TurnControl.commit_conversation`
requires confirmed final delivery and rejects transport abandonment; this plan does not synthesize
a CANCELLED conversation commit or declare cleanup equivalent to delivery. Once TTL expires the
record becomes missing, not resumable. Completed-and-sealed turns retain the ordinary clean-restart
path. Improving interrupted no-effect recovery requires a separately reviewed successor policy;
do not hide this limitation as an implementation detail or claim broad interrupted-session recovery.

Stored entries stage **before** their existing live send, stay within the buffer cap, and finalize
under the committed or D8 healthy-uncommitted path; staging invents no canonical outcome. This is
per-attempt atomic finalization with durable safety markers, not a claim each live byte is already
in Redis. Never discard a healthy uncommitted attempt's staged UI stream.
Any non-applied/uncertain write latches divergence, stops further durable writes and new effects, and
emits an explicit best-effort live durability-loss notice through the existing notice/writer owner.
A failed notice remains a recorded undelivered warning. Existing result/effect/cost classification
is not retroactively changed. A conclusively non-applied final seal leaves the prior in-flight
marker. A timeout/lost acknowledgement is different: the atomic CAS may have applied the complete
eligible seal, or may not have applied. Never assert rollback or that the prior marker certainly
survived. The original attachment remains diverged/UNCERTAIN, reports no acknowledged durable success,
retains local staging/future custody and performs no clearing/retry/release write against an unknown
revision. Preserve that failed/uncertain evidence even if a later result proves the write applied.
A later independent load validates actual Redis state: an unresolved marker refuses; a fully valid
atomic seal may load through ordinary ownership/compatibility/delivery checks, never stale RAM or an
assumed partial write. A seal is submitted only after its complete committed/D8 eligibility and
required flushes are proved; unknown effects/delivery never become seal candidates. This is not
interrupted-effect recovery or a way to waive UNKNOWN at the original request. Apply the same
uncertain-ack distinction to begin/renew/config/cost/load mutations. This diagnostic notice is
live-only, separate from the historical transcript.

Active turns renew the bounded lease through the runtime owner before its deadline (proposed cadence
lease/3, operation deadline below the renewal margin). Renewal failure halts further dispatch/effects
via existing gates; an already-running effect may finish, but its unresolved marker prevents another
process from loading and executing it again. Idle sessions may let ownership expire: before the next
prompt/config mutation, CAS-reacquire only if the exact known revision is still current and no foreign
lease/marker exists. Otherwise refuse with an expired/owned-elsewhere notice and retire the stale
local attachment safely; never fork or rebuild from stale RAM. An expired record is not recreated
under its old session ID. TTL and MCP idle delay remain independent; neither timer fabricates the
other's continuity guarantee.

Use Redis TIME plus Redis expiry as shared time authority; refuse unknown time/TTL state. Reclaim a
still-unexpired lease early only on independently proved dead same-host PID+creation-identity
evidence under CAS. ALIVE/UNKNOWN is not DEAD; WSL retains weaker capability labels. Normal Zed
shutdown must close agent stdin and await clean EOF/lease release. Record that exit mechanism.
A forced kill is a separate failure row: reopen may be busy until valid dead-owner reclaim or
expiry, never clean-restart acceptance. A sleep is not liveness proof.

Count encoded bytes including canonical/replay/accounting/markers before writes and bound in-memory
staging too. Reserve bounded marker/finalization headroom at admission. If a turn cannot fit, refuse
before mutation/effects, leave completed history loadable and explain the storage limit. If an
unpredictable mid-turn stream hits the bound, halt new effects, retain its unresolved marker, report
divergence and refuse later load; never truncate, recreate or exceed the limit. The P0 offline size model quantified only
headroom and serialized consequences: 64 maximum-sized values alone are 512 MiB serialized,
before objects/copies. Historical profiling is not acceptance of this limit.
Measure write amplification too: admission/pre-effect markers, sealing and active renewal at lease/3
can each rewrite a value up to the limit. P2 measures representative latency/bytes/workload effects before CP3. At 64 full values renewal
alone is about 5.12 MiB/s at 100 seconds; four full-value mutations are 32 MiB per turn before
Redis/network/object overhead. Staging adds another 512 MiB at the local cap. These are arithmetic,
not latency/RSS evidence. Reject qualification and re-estimate if deadlines cannot be met.

### Original execution authority and physical dispatch boundary

Proposed SessionPersistenceProjection exposes begin_turn, stage_update, seal_committed,
finalize_uncommitted, persist_config, persist_cost, renew and release. Add one bounded per-session
storage serialization primitive **inside the existing RedisRuntime owner**; main has run_sync/
run_async, not an existing session mutation queue. Select expected_revision inside its serialized
operation. Coalesce only obsolete cost-domain snapshots, never effect/admission/finalization
preconditions; bound pending storage work and prove no lost acknowledgements in P3/P4. These are storage projections, never a controller. Async owners
await runtime submission; synchronous producer workers use the established run_sync seam only
outside all lifecycle/settlement/writer locks and never on the runtime-owner/ACP loop thread.

For WRITE/EDIT/TEST, extend existing runner `_run_gated`: obtain the original directive start lease,
then durability precondition outside its lock before invoking the producer. Recheck original
cancel/transport authority after the wait. Failure before producer settles existing failed_no_effect;
if already frozen, retain the frozen outcome and add only its no-producer diagnostic. Never leave a
granted operation without a terminal. Extend existing finalization to invoke its existing not-started
suppression helper before freezing; no invented user cancel, transport loss, duplicate-start error or
new halt source. MCP bypasses that runner, so use its original guarded SDK call boundary separately:
acknowledge a conservative possible-effect marker before any actual call, keep permission/invocation
guards, and disallow healthy-uncommitted sealing once armed. Fence actual tool dispatch between
ClientMcpToolService guard.check ALLOW and _dispatch. Include an ACP-turn lazy ensure_server
resolver/server launch in the conservative armed criterion before invoking that resolver; a cached
service lookup and its pure catalog list_tools need no new effect marker. ClientMcpServices.list_tools
can trigger ensure_server, so it must pass that same resolver boundary. Startup/load re-disposition
outside an admitted turn remains its existing lifecycle/permission authority and cleanup contract. Do not claim WRITE/TEST effect algebra
already describes arbitrary MCP effects; broader repair stays with #222/#230.

Every physical paid model dispatch needs the same current-lease/no-divergence check, including
classifier/planner/answer/maintenance summarizer and later retries. GatewayClient is synchronous.
Set/reset one optional trusted ContextVar callback around ACP worker submission, **before** existing
_in_worker copies context; its worker inherits the original TurnControl/session projection. Keep it
independent of CaptureIntent (including summarizer turn_id=None). Absent callback preserves
non-ACP behavior, including independent strict preflight/pass-through. No ledger/request text can
supply it. The worker uses existing run_sync outside all owner locks; the event loop only awaits
worker/runtime work. There is no new async GatewayClient API.

In create_response and create_decision, invoke this callback immediately after
validate_trusted_gateway(), **before** _dispatch_headers()/CaptureHook and transport construction/
send. On refusal, record no capture intent for that request. post_tool_json is also fenced at its
corresponding pre-header/pre-send point when scoped to an ACP turn; conservatively arm possible
effect before a Gateway tool producer. post_observability_json is diagnostic export and remains
outside this model/tool dispatch fence, preserving best-effort accounting diagnostics.

Define one content-free DurabilityDispatchRefused as a direct GatewayError subclass in existing
gateway/errors.py, distinct from
GatewayHttpError/response errors, raised only by this pre-send boundary. Its typed proof is that
this new request was not sent, even if an earlier Redis write is uncertain. In gateway/attempts.py,
attempts_from_failure tests this type before its generic fallback and maps it to one ProviderAttempt(number=1,outcome=not_sent,
cost_usd=Decimal("0"),gateway_request_id=None,gateway_usage=None,routed=False). Do not fabricate an
upstream rejection/HTTP status. It cannot stop an experimental route, raise AttemptIntegrityError
or induce integrity_failure/ACCOUNTING_INTEGRITY; an already-started GATEWAY directive settles
failed rather than cost_unknown unless original authority was already frozen. Existing unexpected
exception behavior remains uncertain, never generic zero. Preserve unknown costs from prior sends.
All callers offer the normal not_sent receipt once, retain the durability-loss reason and end the
current execution path without retry/fallback dispatch; test classifier/planner/answer/summarizer,
operation-capture wrapper and any local retry loop. Gateway tool callers
(evidence/acquisition.py and package_advisory.py) propagate typed no-send without fabricating model
ProviderAttempt receipts or Gateway tool usage: preserve their distinct existing accounting owners,
no provider request/usage exists for a refused send; retain a content-free durability diagnostic.
Test web search/fetch and package/advisory entrypoints cannot swallow it into fallback dispatch. Context propagation/reset must be
tested across concurrent sessions so one session cannot inherit another's callback.

Existing capturing/CaptureHook stays best effort; it does not gate HTTP today. A lost capture still
means incomplete accounting even when a valid dispatch was allowed. No provider polling, new client
or new execution authority is added. A mutation deadline timeout is always UNCERTAIN: run_sync's
future.result(timeout) does not cancel submitted work. Latch divergence/no further dispatch, retain
the local pending intent/staging and bounded future custody, never assume Redis rollback or issue an unsafe release/retry; a later acknowledgement is
retained as diagnostic evidence and cannot silently restore a diverged attachment.

### Closed emission inventory (D6 proposal)

At main `6e5478a`, an AST read found **23 direct** `notify("session/update", ...)` sites in
`src/optimus/acp/spec.py`. The following table covers each. The P0 trace also found gateway_refusal.py:85 startup-refusal notification (live-only; no admitted
session) and operator_verify.py:498/514 observation sites (not emitters). Execution re-pin must follow
indirect/dynamic sends, other modules and callbacks, so a wrapper cannot evade the inventory. Baseline lines locate
source; they are not future line-number tests. An unclassified emitter fails the structural gate.

| Baseline owner / direct lines | Classification | Persistence/load rule |
|---|---|---|
| `_handle_savings` 1417; `after_response` 1469 | live-only | Non-turn savings answer/current command catalogue; do not invent a canonical turn |
| `_apply_session_config` 1646/1651 | live-only, reconstructed current state | Persist semantic config; publish current full mode/config on load, never replay obsolete setters |
| `_refuse_prompt` 2340 | live-only | Current main's non-admitted refusal; preserve RPC/notice and non-admission semantics. Explicit D6 refinement of old v2 wording |
| `_index_tool_cards.card` 2476; `_emit_index_line` 2535; `_emit_grounding` 2545 | live-only | Preserve informational best-effort/worker behavior; no source/unsaved bodies or stale worker cards in replay |
| `_emit_auto_notice` 2560; `_prepare_attached_context` 2658; `_emit_sliding_notice` 2690; `_blocking_notice.deliver` 2703 | live-only | Current routing/context/config/maintenance status; required semantic facts persist separately |
| `_send_terminal` 2789 | stored+replayed | Exact existing sanitized terminal plan/message associated with its admitted turn |
| `_emit_cost_alerts` 3032; `_emit_capacity_notice` 3060; `_emit_usage_update` 3099; `_emit_request_capacity_warning` 3115 | live-only | Preserve alert/warning confirmation and cost completeness; do not replay old meters/threshold notices |
| `_recovery_escalation_for.notify` 3210 | live-only | Preserve current informational delivery/route-switch semantics; historical routing facts remain inert |
| `_emit_result_updates` 3371/3394; `_emit_completion_message` 3412/3432; `_emit_planning_progress` 3464 | stored+replayed for an admitted turn | Exact sanitized plan/tool-summary/final/progress payloads; turnless compatibility calls cannot manufacture a turn or claim durable completeness |
| Admitted sanitized user prompt (new derived entry, no live echo) | stored+replayed | Schema-derived user_message_chunk precedes that turn's agent entries |
| Permission request/answer/grant; raw telemetry, context/index/READ bodies or unsaved buffers | forbidden persistence | Never admitted to the historical stream; canonical user/agent text retains declared sanitization/retention |

Reconstructed current config/status publications are distinguished from replay entries in the final
evidence vector. Preserve required replay order first, publish current full config through its
existing owner, then the one `{}` after all required flushes. Informational/live-only failures keep
their current best-effort semantics. AST/dispatch tests enumerate every static/indirect emitter and
require exactly one classification plus privacy/order controls. Do not make live-only telemetry durable.

### Load outcome map

| Condition | Required result/side effects |
|---|---|
| Invalid shape/cwd/additional root or zero-entry ledger | `INVALID_REQUEST`; no replay, TTL refresh or attach |
| Missing/expired session | ACP `RESOURCE_NOT_FOUND`; no replay |
| Live foreign lease | central `SESSION_BUSY = -32900`; no replay/TTL refresh |
| Same-process attached or synchronously reserved same ID | `SESSION_BUSY`; no revision bump, replay or TTL refresh; no second provisional attachment |
| Capacity exhausted | preserve main `REQUEST_CANCELLED`, reason `SESSION_CAPACITY`; no durable mutation |
| In-flight/effect-uncertain marker or unsealed/diverged state | sanitized `INTERNAL_ERROR`, stable reason `DURABLE_INTERRUPTED`; no stale-history hydrate, replay, TTL refresh or automatic effect recovery |
| Sealed `DELIVERY_INDETERMINATE` disposition | sanitized `INTERNAL_ERROR`, stable reason `DURABLE_DELIVERY_INDETERMINATE`; refuse attachment/replay/TTL refresh, never reopen it as a healthy promptable session |
| Malformed/unsupported/incompatible state, Redis error or uncertain mutation | sanitized classified failure, normally `INTERNAL_ERROR`; no fallback or success; preserve uncertain ownership |
| Successful compatible non-empty load | validate, atomically acquire/recover + refresh revision/TTL, hydrate exact ID, re-dispose MCP, replay in order through writer, then `{}` |
| Any replay not conclusively flushed | no `{}`; stop remaining replay, abandon provisional attachment and classify cleanup/lease release or expiry |

Compatibility is conjunctive: same trusted canonical cwd/path platform and registered project/
worktree identity where attachment requires it; currently approved launch class; same storage class,
actual source limit/reservation and supported selected strategy; compatible engine/checkpoint format
and parameter digest; same trusted route-policy/registry identity; current request MCP descriptors
matching existing keyed normalized identities. Current credentials/launch approval are rechecked,
never restored. TTL tightening and MCP idle delay remain current startup policy. Reject mismatch
before CAS/TTL mutation, no silent downgrade/cross-OS conversion/schema-policy migration. A sealed
cap-closed ledger can replay but remains cap-closed. Execution re-pin must show applicability to
these exact checks or return a complete successor.

## Task 0 evidence contract (preserved, current-source successor)

Implement within the existing `tools/evidence_gather.py` validate/prepare/check/collect/classify/
redact/inspect pipeline. Helpers live under `tools/evidence_gather_support/`; do not create a second
collection CLI or let the old probe own a hand-written manifest. Reuse its isolated-copy,
trampoline/relay and closed-SQLite primitives after verifying applicability to D1.

Private raw schema `plan-11-7-v5-current-client-raw-v1` is derived from a verified CollectionBatch:
scenario/run/bundle/classification digests; wall+monotonic bounds and approval ID; exact Zed path,
hash, versions and revision; exact launcher path/bytes/hashes; every file-backed imported module
inside the isolated source root captured after bootstrap before the first ACP request; historical,
approved and actual source pins, diff/untracked/module closure and before/after restoration hashes;
separate arm profile/workspace/DB identities; SQLite/WAL/SHM custody hashes and exact thread binding
from closed copies; ordered protocol observations, IDs, parameters and exact result bytes; cleanup
targets and existence checks. Derive counts, IDs, classification and DB facts from artifacts only.
Unknown keys, type coercion, missing module closure, chronology/hash/run mismatch fail derivation.
One run ID owns one immutable bundle; repeated collect for that ID fails, never appends/merges runs.
Existing non-Plan11.7 scenarios stay behavior-compatible. Generic provisional classification is a
digest-bound custody artifact, never translated from `rendered_stable` into gate acceptance.

Preserve `windows-path-v1`: require existing absolute path and strict resolution; NFC; `\\`
separators, redundant-dot removal and uppercase drive only; preserve other casing, no later expansion;
UTF-8 of `b"windows-path-v1\\0" + canonical_path`. Per-run random private 32-byte HMAC key never
appears in promotable data. V5 commitment domain is `b"plan-11-7-v5:path:v1\\0"`; do not relabel
an old v3 commitment. Sanitized semantic aliases contain no user/drive/workspace fragments.

Public schema `plan-11-7-v5-current-client-sanitized-v1` contains only role, opaque alias, keyed
commitment, safe source-relative locator, hash/size and sanitized derived observations. The adapter-
derived `plan-11-7-v5-current-client-redaction-attestation-v1` binds scenario/run, raw manifest and
bundle digests, sanitized manifest, ordered mapping, every derivative digest, redaction-report digest,
independent reviewer identity/time. Private reviewer recomputes commitments and checks provenance.
Offline public verification establishes sanitized integrity only; it cannot reconstruct private
paths or prove the private-to-public collector mapping without that separate attestation.

### Trusted inputs and private-review receipt (D11)

Keep the verifier's three arguments manifest/attestation/bundle-root. Resolve the registered
scenario from the reviewed checkout at `tests/fixtures/evidence/scenarios/plan117-current-client-gate-v6.toml`
and expected run binding from `reports/plan-11-7-v6-approved-runs.json` in that checkout, never
from bundle-root or a path supplied by the bundle. A pre-live reviewed sanitized RunSpec binds run ID,
evidence kind, scenario+fixture+patch digests, source commit/tree/module expectation, client binary
identity, launch/config digest, declared arm IDs, approval ID/window, budget-policy digest and
private-root opaque commitments. The registry records its exact hash. Unknown/missing/duplicate run
ID or mismatch fails verification; a bundle cannot register itself. The verifier cannot detect whether a registry edit was reviewed: review/custody is a trusted
external precondition. Pin the exact registry blob hash, scenario blob and checkout commit in the
reviewed invocation record outside bundle-root, and verify those bytes before execution. The
executing source pin can be a separate reviewed base plus approved isolated patch; adding a run
registry must not require a self-referential source commit/hash. This
registry is an evidence input, not another work/status register. E2 creates its schema; the actual
run row is prepared/reviewed before the separate E3 live release, no invented approval today.

The private reviewer supplies a closed PrivateReviewReceipt with accepting verdict, reviewer identity,
reviewer session/model, review time, run/scenario/source identity, raw manifest/bundle hash, sanitized
manifest hash, ordered mapping/derivative hashes and redaction-report hash. Bind its hash into the
attestation. Missing/negative/conditional verdict or any hash mismatch cannot promote. This receipt
is not an operator/live approval or a source of observation counts. Capture existing path identities
with strict resolution before cleanup. Later private attestation rehashes retained captured facts/
commitments; it must not require deleted live roots still to exist. No private key/path enters the
promotable registry, receipt or bundle. Trust the approved acquisition/reviewer host/operator and
reviewed checkout custody; this design does not authenticate a hostile same-privilege host.

### Non-waivable reducer and lifecycle choreography

Primary precedence: **positive empty-stream reopen signal → ZERO_ENTRY_REACHABLE_STOP**, then schema/
custody invalidity, A-prime/first-refusal choreography invalidity, prompted-arm invalidity, source/profile/
cleanup/redaction invalidity, then acceptance. Ordered secondary reasons remain visible. A positive
signal cannot be masked by absent/inconsistent counts/IDs, redaction failure or another invalidity.
A first-launch load is invalid fresh-profile choreography, not proof of reopen reachability.
Primary dispositions are `ZERO_ENTRY_REACHABLE_STOP`, `INVALID_CURRENT_CLIENT_GATE`,
`INDETERMINATE_CURRENT_CLIENT_GATE`, or `ACCEPTED_CURRENT_CLIENT_GATE`. Only the last carries the
derived reachability `ZERO_ENTRY_UNREACHABLE`; that label alone is never an acceptance verdict.

- A-prime: fresh profile/workspace; first launch exactly initialize=1/new=1/load=0 and no prompt;
  clean stop, closed DB row exists with null binding; reopen same profile/thread exactly initialize=1/
  new=1/load=0/no load IDs; clean stop/copy leaves null binding on the same DB identity.
- **Both A-prime launches run the frozen isolated load-only stub.** Capture exact initialize result
  bytes; require top-level `agentCapabilities.loadSession: true` on each and no `resume` field.
  Missing/false load support is INVALID, never unreachability. Positive-signal STOP takes precedence
  over this invalidity. Bind both launches' stub/patch/module identities.
- A-prime positive: pre-reopen binding non-null, reopen load count >0 or any captured reopen load ID
  latches STOP, even when other fields are invalid. Continue only already-authorized sealing,
  cleanup and prompted arm; no production implementation follows.
- Registered first-refusal cases R: each source-valid wire class has a fresh profile/workspace.
  The seven classes are successful stopReason=end_turn, refusal and cancelled; and JSON-RPC
  INVALID_REQUEST, REQUEST_CANCELLED, TURN_BUSY and INTERNAL_ERROR. The v6 checkpoint below
  fixes the exact current-source descriptors and census. MCP_REOPEN_REFUSED requires prior
  idle suspension and remains a separate resumed-session case. Malformed and missing-session
  requests remain negative controls. The synthetic server advertises loadSession=true with
  no resume on both launches. It emits one exact reply/notice set with zero stored-class entries.
  First launch has initialize=1/new=1/load=0/prompt=1, followed by clean stop and closed copy.
  Reopen the same thread with initialize=1/new=1/load=0/no prompt and verify null binding.
  Any pre-reopen non-null binding, reopen load count or captured load ID latches STOP before
  invalidity. All seven arms are required for acceptance. The fixture characterizes the client's
  empty-stream boundary. Real Gateway/MCP/Redis, production overlap and durable admission
  require the corresponding independent evidence.
- Prompted A/B: separate fresh profile, one prompted session, clean stop with exact session binding;
  reopen against isolated current-source **load-only stub**, initialize=1, one distinct load for the
  same ID, new=0, replay=0, exact result bytes `b"{}"`; clean stop/copy shows null binding.
- Temporary capability/stub/instrumentation patch is allowed only in the recorded throwaway Task 0
  source. It may not enter production or be called feature acceptance. Daily source/profile stays
  untouched. Freeze the minimal patch and imported-module closure before live approval.
- Only independently accepted `ZERO_ENTRY_UNREACHABLE` and current-owner reconciliation permit
  P1–P5. STOP requires another operator-approved forward-only policy successor; INVALID/INDETERMINATE
  requires a new separately authorized clean run, never editing a failed manifest into validity.
- Aug22 matched A/B and Aug23 ad hoc evidence remain historical, separately redacted/supporting only.
  W1 stays under-evidenced, not proved stale-install causation. If raw custody is missing, the custody record states
  the precise gap and required disposition; no completion claim or fabricated replacement derivative.

## File and responsibility map

Paths below are intended repository paths, not changes made during this assessment. Create only
absent files, otherwise extend the existing owner. Execution re-pin checks current paths before implementation.

| Files | Responsibility / callers and tests |
|---|---|
| `tools/evidence_gather_support/plan117_current_client_contract.py`, `plan117_current_client_collector.py`; `tools/verify_plan117_v5_current_client_evidence.py` | Pure exact schemas/reducer; collector/derivation; offline verifier. Reuse `evidence_gather.py`, support fixtures/redaction/registry, evidence_handoff collector contracts and `probe_p11_zed_session_load.py` |
| `tests/fixtures/evidence/scenarios/plan117-current-client-gate-v6.toml`; `tests/unit/tools/test_plan117_current_client_contract.py`, `test_plan117_current_client_collector.py`, `test_verify_plan117_v5_current_client_evidence.py`, existing gather/probe tests | Gate fixture, pipeline and tamper/omission/masking/private-path tests |
| `src/optimus/acp/session_models.py`, `session_store.py`, selectively `lease_owner.py` | New main DTOs, typed persistence outcomes and CAS store; owner-liveness logic only if portable/required, UNKNOWN never dead |
| `src/optimus/acp/conversation.py`, `session_config.py`, existing context adapter/contracts, usage settlement/alerts and Auto composition | Owner-local snapshot/hydration seams; same authoritative semantics, no second context/cost model |
| `src/optimus/redis/runtime.py`, `src/optimus/acp/harness_runtime.py`, `bootstrap.py`, `server.py` | Shared-client factory, dependency injection, loop/teardown ownership; reuse harness runtime rather than creating another runtime |
| `src/optimus/acp/spec.py`, `shapes.py`, `errors.py` | Durable new/prompt/config/load, exact-ID provisional attachment, replay builders and central error allocation |
| `src/optimus/acp/session_retention.py`, `lifecycle.py`, `settlement.py`, `outbound_writer.py` | Preserve current owners; change only a demonstrated seam, test cancellation/retirement/flush integration |
| `src/optimus/agent/runner.py`, `planning_loop.py`, `tools.py`, `operation_control.py`; existing guarded MCP SDK call owner | Reuse directive start/terminal authority, pre-producer durability boundary, no unresolved operation; preserve existing MCP invocation guard, conservatively fence calls without expanding effect algebra |
| `src/optimus/gateway/client.py`, `gateway/errors.py`, `gateway/attempts.py`, current Auto/planner/answer/context-maintenance callers and operation_capture | Separate optional scoped ACP durability pre-dispatch condition before capture; typed not_sent/zero mapping, no route stop/integrity failure; all paid model roles, no change to best-effort capture policy or non-ACP callers |
| `src/optimus/evidence/acquisition.py`, `package_advisory.py` and existing tool caller tests | Preserve distinct tool-usage accounting on typed pre-send refusal; no fabricated model receipt/usage; test all four post_tool_json callers |
| `src/optimus/usage/durable_capture.py`, `operation_capture.py`, `turn_settlement.py`, `cost_alerts.py`; existing capture reader | Owner-local immutable coverage snapshots, written-close/watermark proof, capture-free hydration and late reconciliation; corresponding usage/Gateway/runner/MCP tests |
| `reports/plan-11-7-v6-approved-runs.json`, existing scenario/registry/redaction support and fixtures | Reviewed sanitized expected-run trust input outside bundles, typed accepting private receipt and two-layer proof tests |
| `src/optimus/mcp/client_disposition.py`, existing MCP lease/close owners; `src/optimus/acp/launch_policy.py` and launch/security classification tests | Load re-disposition, no restored grants; independent TTL/idle policy and approved-environment/config hash coverage |
| Existing `src/optimus/context/memory_session.py`, `spec.py` memory factory/start/stop seams and memory wiring tests | Recreate approved index resources; do not serialize workers, unsaved text or stale views |
| `tests/unit/acp/test_session_models.py`, `test_session_store.py`, `test_shapes.py`, `test_spec_protocol.py`, `test_error_code_registry.py`, `test_bootstrap.py`, `test_conversation.py`, `test_session_retention.py`, `test_session_retirement.py`, existing writer/settlement/config/context/memory/Auto tests; `tests/unit/mcp/test_client_disposition.py`; Redis/usage tests | Focused unit regression surface; real-path tier separately below |
| `tests/integration/acp/test_session_store_live_redis.py`, `test_session_load_live_redis.py`; `tests/e2e/acp/test_session_load_restart.py`; existing context memory integration tests | Real Redis CAS/TTL, independent-client process restart, current context/resource compatibility |
| `reports/plan-11-7-v6-current-client-gate/`, `reports/plan-11-7-v6-architecture-reconciliation.md`, `reports/plan-11-7-v6-acpx-restart/`, `reports/plan-11-7-v6-zed-resume/`, `reports/plan-11-7-v6-release-review.md` | Sanitized source-bound acceptance artifacts and custody, no raw profiles/DBs/keys |
| `docs/decisions/ADR-043-durable-acp-session-retention-and-replay.md`, `docs/decisions/README.md` | Adopted rationale and execution-pin index; D2/D3/D6/D7 rationale, alternatives, content/retention/privacy, no purge API, interruption/expiry experience and configuration authority |
| `README.md`, `docs/README.md`, existing roadmap and live-plan registry pointer, relevant docs hygiene tests; #240/#230/#254 and retained sibling custody | Adoption/feature documentation and truthful issue updates only under separately granted publication authority |

Forbidden: `src/optimus/agent/conversation.py`, a second physical ACP writer, parallel turn/effect/
cancellation controller, standalone collection CLI, new ACP-session Redis pool or whole-sandbox merge.

## v6 offline checkpoint — ACP wire and collector compatibility

**Goal.** Unblock the #304 draft PR by proving the new wire contract and its source-bound collector agree on one staged tree. #240 keeps custody of the current-client gate. The checkpoint exercises the collector offline and records what a later E3 would need.

**Prerequisites for this checkpoint.**

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|---|
| Code/state | #304 patch and both ACP test corrections available as a single staged diff | yes | Codex / #304 | Recheck the staged tree and transferred diff before execution. |
| Code/state | v5 source census matches the clean integration base and rejects the proposed #304 tree | yes | Codex / #240 | Repeat the source-bound comparison at the execution pin if main moves. The most recent verification at drafting time used main `e3272e7`. |
| Code/state | v6 fixture, scenario and reducer accept the #304 source together | no | Codex / #240 and #304 | Genuinely absent, locally buildable by the tasks below. |
| Tooling | Frozen Windows and WSL environments with separate test records | yes | Implementer | Verify the interpreter, lock and supported guard mode for each run. Recreate a stale environment offline. |
| Credentials/authority | Operator approval of this exact successor and authorization for its offline implementation | no | Operator | Merely unauthorized. The 2026-11-26 scope approval asked for the successor and collector update. The project requires approval of the concrete implementation plan. |
| Services / human interaction / cost | This checkpoint uses local files and hermetic tests. GitHub CI uses the existing sign-in and standard branch workflow. | yes | Implementer | No Zed GUI, service, paid Gateway call, Optimus keyring operation or historical CI rerun is a prerequisite. |

### Wire contract and evidence identities

| Case | Current production evidence | v6 fixture disposition |
|---|---|---|
| Unregistered or retired session | `RESOURCE_NOT_FOUND` (`-32002`), `unknown session`, no error data | Negative control in the prompt census. The former unleased pre-dispatch error disappears. Keep the prompt validation and malformed-request controls. |
| Active turn or usage report | `TURN_BUSY` (`-32913`), `a turn is already in progress`, no error data | Add `r_turn_busy` as a required refusal descriptor. The production case needs overlap. Its synthetic fixture observes only the client's response to the wire class in a fresh thread. |
| MCP refusal without prior idle suspension | `REQUEST_CANCELLED` (`-32800`), `session unavailable`, `{"reason":"mcp_cleanup_uncertain"}` for the representative branch | Keep `r_request_cancelled`; pin this current payload including `data`. Retain the other existing pre-idle MCP cancellation sites and all existing prior-idle dispositions. |
| Six previously registered case IDs | Existing v5 fixture and historical source | Retain all six IDs in v6. Update only the cancellation payload in an existing descriptor. Insert `r_turn_busy` before `r_internal_error` in the ordered R list. |
| Missing dispatcher dependency | `INTERNAL_ERROR` (`-32603`) with `data.reason=DEPENDENCY_UNAVAILABLE` | Keep the #304 dispatcher regression. This path is outside the duplex first-prompt census. |

Version the registered scenario as `plan117-current-client-gate-v6`, the fixture file as
`tests/fixtures/evidence/plan117-v6-first-refusal-descriptors.json` and its schema as
`plan-11-7-v6-first-refusal-descriptors-v1`. Use ordered arms A-prime, the seven R arms, prompted A/B.
The two added launch slots are the synthetic busy fixture's first and reopen launches. A future
E3 must requalify its whole schedule under separate authorization. The busy fixture issues no
provider requests. Authorization for the offline checkpoint grants zero live budget.

Keep the existing collector and verifier entry points and adapter IDs. Bind the current scenario
to a new committed `reports/plan-11-7-v6-approved-runs.json` with schema
`plan-11-7-v6-approved-runs-v1` and `runs: []`. Use a new `plan-11-7-v6-invocation-record-v1`
schema with the same fields. The reviewed checkout, invocation record, run spec and verification
must agree on the scenario, registry, descriptor bytes, arm order, patch hashes and launch
configuration. Retain existing raw, sanitized, attestation, path-commitment and private-receipt wire
formats. The new scenario and its registered hashes distinguish the plan version. Check both source
files against the gated normal-source root before rendering any stub. Current
acceptance rejects v5 or mixed-version trust inputs. Historical v5 verification uses the exact
v5 source and trust inputs recorded with the artifact. Preserve the prior fixture blob
`39a7982868d594768674eecf8dd521a8a37bbac1`, scenario blob
`fd5f3814b77d595943e627b13c9573ccabf06092` and empty registry blob
`808e0e2a2c94b6cb5a9fea4ad2136d803d71d821`, verified on main `e3272e7`.

**Options considered.** Treating busy as an offline-only overlap exclusion would save two future
fixture launches. It would narrow the existing source census's conservative coverage of
pre-admission errors when a thread can still lack a stored entry. Aliasing busy to cancellation
would fail to test the response code the client actually receives. A required busy case keeps
the client coverage explicit and gives missing, mismatched or unobserved arms the existing
failure treatment. This is the proposed design choice for v6.

### Task V6.1 — Pin the refusal census and exact fixture bodies

**Files.** `tools/evidence_gather_support/plan117_current_client_collector.py`,
`tools/evidence_gather_support/plan117_current_client_contract.py`, the new v6 fixture,
`tests/unit/tools/test_plan117_current_client_collector.py`,
`tests/unit/tools/test_plan117_current_client_contract.py` and synthetic support builders.

- [ ] Capture main and the staged #304 diff. In a clean-base checkout confirm the v5 fixture matches its
  source. In the candidate confirm the expected pre-v6 refusal. Verify that `3886a8f` differs from the accepted `6ac680e` production tree only in
  `tests/e2e/acp/test_multi_turn_conversation.py` and `tests/unit/acp/test_plan121_chat_mode.py`.
  The latter keeps `INVALID_REQUEST` for malformed setters and expects `RESOURCE_NOT_FOUND`
  for valid setters targeting a missing session, with the existing no-mutation checks.
- [ ] Extend the census tests to expect one `error:RESOURCE_NOT_FOUND:unknown session` prompt negative
  control and one `error:TURN_BUSY:a turn is already in progress` prompt descriptor. Retain the
  direct-error and MCP controls. Assert that an unknown selector, dynamic selector argument, moved or
  removed branch, and a change to an independently declared code/message fail the structural gate.
  Compare expected tuples and literal wire bodies against the source and selector separately.
- [ ] Extend `trace_first_prompt_census(spec_text: str, *, errors_text: str)` and
  `verify_census(fixture, spec_text, *, errors_text: str)` in the existing collector. Load `spec.py`
  and `errors.py` from the same gated normal-source checkout. Resolve the two selector arms from
  the `AcpErrorOutcome` cases in the parsed `errors.py` and their module-local integer constants.
  Accept only the uniquely matched, constant message and exact code shape. Validate the recognized
  call shape and source imports. Unrecognized, ambiguous or dynamic selectors fail with
  `r_census_mismatch`. Parse only source text, without executing it or using an import from the
  collector's own checkout as the mapping authority. Keep the alternative direct-error and MCP
  site accounting and test drift in `errors.py` with `spec.py` held constant.
- [ ] Add a required `error_data` member to each v6 descriptor. Accept JSON null or the single
  structured MCP reason above for `r_request_cancelled`. Other descriptor data is invalid. Use one
  normalized response body for the expected hash and stub rendering. The single-prompt stub renders
  only validated literals and uses the registry code for busy without introducing a production import
  for a throwaway stub. Keep invalid-prompt handling, one-prompt guard, load-only behavior and notices.
- [ ] Assert the exact wire bodies for both errors using independent expectations. Test invalid or
  forged data and no data on busy. Independently observe the representative MCP cancellation body
  through the normal ACP adapter in a hermetic fixture so synthetic stubs are not their own oracle. Run the census, registry, fixture-parser and rendered-stub tests
  with their existing negative controls. Prove each new check fails for its named fault before the fix.

### Task V6.2 — Bind collection, derivation and verification to the v6 scenario

**Files.** Existing collector/contract/gather/verifier entry points, the new registered scenario and
empty run registry, corresponding gather/verifier tests and synthetic support. Keep the frozen v5
fixture, scenario and registry bytes.

- [ ] Write failing cases for omitted, duplicate, reordered, and wrong-body busy arms in the approved
  run spec and observed manifests as applicable. A readable positive reopen signal from the busy arm
  must remain `ZERO_ENTRY_REACHABLE_STOP` even alongside separate malformed or missing evidence.
  Keep parameterized coverage of every reopen arm, raw/sanitized verification and capture-loss controls.
- [ ] Update the current scenario/registry/fixture and invocation bindings. Use the existing checkout-owned
  constants and rules for order, patch plans, hashes and separate roots. Detect v5, copied scenarios and
  mixed inputs at trust boundaries. Reuse the existing legacy-scenario routing for unrelated scenarios.
  No registered v6 run ID is added. Test that the trusted empty registry reaches refusal before launch.
- [ ] Prove the complete, valid synthetic v6 pipeline accepts; missing/wrong busy evidence alone is INVALID
  or INDETERMINATE according to the existing verdict taxonomy; a positive survives those faults.
  Test v5 inputs at the v6 gate, including the case where only a registry or descriptor pin is swapped.
  Preserve existing HMAC, provisional classification, source identity and private-receipt protections.
- [ ] Run the focused four-module gate below plus the ACP end-to-end, session retirement, savings, queue
  and registry checks on Windows and WSL. Preserve fail/skip/UNRUN and guard qualifications. Exercise
  any real platform-shaped failures on both native Windows and WSL before relying on CI.

### Task V6.3 — Review and publish one atomic offline candidate

- [ ] Re-pin current main and construct the combined candidate in an isolated branch from main using the
  approved #304 diff and the compatibility slice. Run the source census and the product wire tests on
  the combined tree. The old v5 fault remains a historical negative, with the source identities retained.
  Keep unrelated #240 draft work and the #334 inventory in their current checkouts.
- [ ] Review the combined staged tree (scope, fail-closed validation, STOP precedence, no trial launch,
  historic byte integrity and documentation freshness). Codex owns the work; the independent CLI
  reviewer follows the operator's Max-only rule. Review output and precise tree hashes go to the
  applicable issue and checkpoint log within the authorized publication scope.
- [ ] On authorized adoption, record the supersession and next gate in #240, archive v5 byte for byte,
  update the mutable index, live-plan pointer and roadmap, and verify archive-aware historical links.
  Preserve the adoption record and ADR-043 frozen bytes. The original v5 SHA-256 and Git blob must
  match exactly before and after the move.
- [ ] Run Ruff, staged diff checks and the standard commit hooks on the final candidate. Commit and
  open one draft PR covering #304 and the scoped #240 compatibility. Verify all fresh CI statuses,
  actual test-merge parents/tree and coverage validity. Keep the different local and CI identities in
  the evidence, along with the failed original commit-gate attempt. #240 stays open and blocked.
  Merge, later checkpoint acceptance and every live E3 action require their own grants.

**Focused commands for this checkpoint.** Run in the isolated locked environments with the null
keyring and live credentials absent. Do this once per exact tree and platform unless a verified
change invalidates relevant evidence.

```powershell
uv run --no-sync pytest --no-cov -q -rs tests/unit/tools/test_plan117_current_client_contract.py tests/unit/tools/test_plan117_current_client_collector.py tests/unit/tools/test_evidence_gather_plan117_v5.py tests/unit/tools/test_verify_plan117_v5_current_client_evidence.py
uv run --no-sync pytest --no-cov -q -rs tests/e2e/acp/test_multi_turn_conversation.py tests/unit/acp/test_plan121_chat_mode.py tests/unit/acp/test_dispatcher.py tests/unit/acp/test_spec_protocol.py tests/unit/acp/test_session_retirement.py tests/unit/acp/test_queue_backpressure.py tests/unit/acp/test_savings_command.py tests/unit/acp/test_error_code_registry.py
uv run --no-sync pytest --no-cov -q -rs tests/unit/docs/test_docs_index.py tests/unit/docs/test_plan_directory_hygiene.py tests/unit/docs/test_open_work_pool_hygiene.py tests/unit/docs/test_plan_relocation_digest_equivalence.py
uv run --no-sync ruff check .
git diff --cached --check
```

**Offline definition of done.** Production ACP and the seven-descriptor collector share one reviewed
tree. The census, exact reply, scenario isolation and STOP regressions pass on Windows and WSL with
complete records. The frozen v5 plan and trust artifacts rehash to the recorded identities. The
normal hooks pass and the draft PR's exact test merge has verified green CI. This closes the
compatibility blocker. Overall Plan 11.7 completion still requires every applicable gate below.

## Tasks and dependency order

Every implementation task follows RED → smallest owner-local change → focused GREEN/Ruff/diff.
Record exact commands and source before/after; all checkboxes below are intentionally unchecked.
Ordinary applicable hooks govern every commit. E1 and E2 below describe the carried-forward baseline contracts. The proposed implementation grant covers Tasks V6.1–V6.3. New APIs named here
are proposed interfaces, not claims that main already provides them.

### P0 — adoption and execution re-pin

**Files.** The reviewed v6 bytes, historical pins, ADR-043 and current decision index, approved #304
candidate evidence, and the current owner map.

- [ ] Record operator adoption of the exact reviewed v6 SHA-256, its offline task scope and implementer.
  The operator's v5 adoption already covers the carried-forward D1–D13 mechanisms, subject to v6's
  explicit first-refusal update. Live execution and production implementation remain separate.
- [ ] Re-pin main, candidate/history blobs, sandbox context and clean isolated implementation checkout.
  Verify overlap in ACP source and collector tests. Preserve v5 history and both #304 test-only
  deltas. Re-review an affected contract if main drift changes it.
- [ ] Before a separately authorized later tier, establish every applicable unknown prerequisite with
  bounded metadata/preflight, and record the evidence against its exact pin. Keep unauthorized or
  unavailable tests UNRUN. P1's three shared files still require reviewed integrated main or exact
  owner clearance.
- [ ] Reuse ADR-043 for the already adopted production design and its disclosed consequences. If a
  new decision record is necessary for subsequent requirements, allocate it against the current
  index under the normal decision process.
- [ ] Freeze the scenario/fixture/registry and invocation blobs for the offline v6 checkpoint. Approval,
  production budget and the human/GUI ceremony remain future E3 prerequisites. Preserve all historical
  failed, INVALID and UNRUN attempts with their original source identities.

### E1 — pure evidence contracts and two-layer derivation

**Files:** current-client contract helper + tests, existing redaction support. **Interfaces:**
`Plan117RawManifest`, `Plan117SanitizedManifest`, `Plan117RedactionAttestation`,
`GateVerificationResult`, pure `reduce_gate(raw)`; strict path commitment/derivation helpers.

- [ ] Write failing schema/reducer tests: recursive unknown fields, bool counts, duplicate semantic
  roles, mismatched IDs/hashes/run windows, omitted modules and artifact substitutions.
- [ ] Pin both positive-signal masking attacks, duplicate/inconsistent count/list cases and invalid
  first-launch load. Any reopen positive must remain STOP with secondary invalidity reasons.
- [ ] Add RED controls where either A-prime initialize lacks/denies loadSession or advertises resume:
  INVALID even with zero loads; if a reopen signal is positive the primary verdict is still STOP.
- [ ] Implement pure contracts and separate I/O derivation. Test NFC/drive/separator canonicalization,
  per-run commitment isolation, forbidden raw paths, private-key leakage and untrusted manifest input.
- [ ] Pin accepting/private receipt ingress, trusted registry outside bundle-root, self-registration
  attack, approval/hash mismatches, failed/missing reviewer verdict and cleanup-before-attestation
  controls. One missing R descriptor or unregistered source branch invalidates coverage.
- [ ] Run the focused contract tests, scoped Ruff and `git diff --check`; preserve RED/GREEN records.

### E2 — pipeline collector, redaction and offline verifier

**Files:** collector helper, existing gather/fixtures/registry/redaction/probe owners, v6 scenario,
verifier and corresponding unit tests. **Interfaces:** verified CollectionBatch → derived raw
manifest → eligible sanitized bundle/attestation → `GateVerificationResult`; no caller-authored counts.

- [ ] Write failing full-pipeline tests with deterministic artifacts for A-prime, all R cases and prompted A/B, module capture,
  exact stub patch, DB copies/chronology, normal-source restoration and failed cleanup.
- [ ] Complete candidate6208177's deferred sanitized/attestation generation through the existing
  pipeline using the typed receipt above. Keep candidate60488daa defect/correction history intact.
  Capture expected fixtures separately from observations; prove R response-class coverage against
  source without pretending a stub observed real Gateway/MCP/Redis behavior.
- [ ] Reuse current evidence pipeline/probe primitives. Capture executing entrypoint and complete
  in-root imported-module closure before requests; pin temporary instrumentation/patch separately.
- [ ] Pin one-run-ID/no-append behavior, generic-classification versus gate-verdict separation,
  unchanged legacy/default scenarios and transition-token chronology in failing collector tests.
- [ ] Require distinct raw/staging/quarantine/sanitized roots. Recompute private mapping before
  attestation. Test omission, unsalted-path leakage, cross-run alias substitution and patched bytes.
- [ ] Verify sanitized bytes with private raw roots unavailable; tampered byte/module/commitment/count
  copies must fail. Keep public verification limitations explicit. Run focused gather/probe/verifier
  tests, redaction checks, Ruff and diff. Prepare exact live command without launching it.

### Checkpoint 1 — pre-live machinery acceptance

Current-source v6 E1–E2 compatibility and the required checkpoint verification below precede any live release. Follow the applicable operator-directed review cadence for the implementation lane. Reviewer traces every manifest field to evidence
and attacks positive-signal masking cases across A-prime and R, raw-path exposure and omitted module closure. Acceptance of machinery
alone is **not** Task 0 acceptance or live authority. Stop before live execution without its separate
approval ID and current budget/service preflight.

### E3 — one authorized current-source pipeline run

**Files:** private run-root only. **Interface:** immutable raw CollectionBatch/bundle with A-prime, all R cases and prompted A/B.

- [ ] Revalidate exact accepted code/config/patch/scenario/Zed/launcher/module/profile identities and
  empty run roots. Confirm daily source/profile untouched; record approval and prospective cost cap.
- [ ] Execute exact A-prime, all seven registered R cases and prompted A/B choreography above. Latch positive reachability before
  invalidity checks. Stop unauthorized work; preserve failed arms instead of retrying to green.
- [ ] Capture both A-prime initialize results with the load-only stub and require loadSession=true,
  no resume. Record whether each shutdown uses clean stdin EOF/awaited exit or a forced kill. Do not
  call a busy lease after forced kill a clean-restart failure/pass; preserve its separate outcome.
- [ ] Cleanly stop only recorded test processes, copy closed DB/WAL/SHM custody, prove restoration,
  and derive classification/raw manifest from artifacts. Cleanup only verified throwaway targets
  specifically covered by the live grant; preserve evidence and unrelated worktrees.

### E4 — promotion, architecture reconciliation and Task 0 acceptance

**Files:** v6 current-client report/manifest/attestation and architecture report. **Interface:** two
independent acceptances: valid current-client gate and current-main owner compatibility.

- [ ] Private reviewer recomputes mapping; run pipeline redaction, promote eligible derivatives only,
  and verify exact promoted bytes from a private-data-free checkout. Reject altered copies.
- [ ] Give Aug22/23 historical material a separate custody/redaction disposition, never mingle it
  with this run. Missing originals remain missing and require explicit disposition before completion.
- [ ] Freeze exact owners for conversation/context, lifecycle, notice/response/writer, runtime,
  retention/MCP/memory, cost/Auto and config. Prove no duplicate owner proposed; map all v2 duties.
- [ ] Review evidence and architecture independently. Only accepted ZERO_ENTRY_UNREACHABLE plus
  accepted reconciliation releases the production dependency. STOP or invalid evidence retains #240's
  blocked gate; no fake success via a technical pass.

### Checkpoint 2 — evidence gate and architecture acceptance

E3–E4, same checkpoint verification and review order. Record exact private/public trust distinction,
historical-custody disposition and D1 applicability. This is a checkpoint, not per-task review.
Production P1 begins only after its implementation authority and both acceptances exist.

### P1 — current-main ledger and exact semantic hydration

**Files:** session_models, conversation/config/context/usage owner-local projection seams; schema,
conversation/config/cost/Auto tests. **Interfaces:** `AcpSessionLedger`, `ConversationSnapshot`,
`ReplayEntry`; proposed `snapshot_session(session)` and `hydrate_session(snapshot, approved_context)`
with exact closed-world DTO types frozen at P0. No runtime resources cross this interface.

- [ ] Write failing round-trip/privacy tests for exact turns/generation/cost/warnings, attached limits
  and reservations, strategy/checkpoint/approval facts, mode/config changes and Auto prior routing.
- [ ] Pin healthy NOT_COMMITTED attempt round trips: canonical records/generation unchanged, exact
  stored user/terminal UI retained, consumed next_turn_seq gaps and cost retained, next model history
  excludes the uncommitted attempt. Reject contradictory ownership/ranges/terminal facts.
- [ ] Pin incomplete receipts around finalization/crash and rehydration: pending attempts remain
  incomplete; attributable late receipts reconcile once; no historical event is re-appended to
  DurableCapture and no unknown charge becomes zero. Restore exact attachment values or refuse.
- [ ] Prove written host_complete close versus queued/failed close, pending worker, lost capture,
  rejected/unconfirmed intent, later receipt and missing retained path. Complete only at verified
  watermark; preserve known subtotal/incomplete facts, no fabricated integrity conflict. Cross-domain
  generation/barrier tests prevent stale cost/config from overwriting newer canonical state.
  Explicitly test capture-disabled with fully settled executed work: resumed known subtotal remains
  intact but completeness is false/coverage_unverified; separate proven no-send zero can be complete.
- [ ] Write malformed/unsupported schema, impossible chronology, capacity boundary and launch-policy
  incompatibility controls; unsupported sandbox-v1 data refuses without alteration.
- [ ] Adapt sandbox pure validators/canonicalization selectively. Preserve current source semantics,
  historical inert approvals and receipt idempotence; no new execution model or reconstruction.
- [ ] Run focused model/conversation/config/context/usage tests; compare pre/post planner envelopes,
  exact-history digest and cost once, not only serializer self-round-trips.

### P2 — Redis store, startup, configuration and durable session/new

**Files:** session_store, runtime, harness/bootstrap/server, launch_policy and spec new-session seams;
store/bootstrap/launch/MCP/retention tests and real Redis store tests.
**Interfaces:** typed create/load/acquire/append/finalize/release outcomes, session store factory over
the existing runtime; one revision/lease/TTL owner. Adapt existing sandbox AcpSessionStore signatures,
including operation_id/expected_revision, only where they fit accepted current-owner contracts.

- [ ] Write deterministic clock/barrier tests for SET NX atomic initial lease, one CAS revision,
  lease renewal/expiry/recovery, conflict with no retries, unknown owner liveness and uncertain writes.
- [ ] Write RED rows for server-time versus skewed process clocks, sliding TTL refresh only on
  allowed writes, release retaining TTL, TTL>=lease validation, idle lease loss/reacquisition, live
  record expiry/no partial recreate, and active renewal failure. Real Redis TIME/expiry tests must
  back the unit clock model; no local-wall-clock ownership proof.
- [ ] Prove a turn/tool call lasting beyond the lease cannot continue an effect after another process
  acquires ownership for a next action. An already-running effect may finish and its unresolved
  marker continues to refuse foreign load; no promise of external rollback or interrupting arbitrary
  producers is made. Prove the foreign owner cannot load an unresolved marker even after expiry.
  Use existing admission/effect gates with CAS fencing/renewal as necessary;
  an old owner must fail closed before the next effect, and expiry alone is not proof it died.
  If safety requires a new execution authority, stop and revise the architecture rather than add one.
- [ ] Add startup/config parsing and approved-launch hash/classification tests: independent TTL and
  idle delay, bad/missing Redis, capability absent when no supported store, no hidden new pool.
- [ ] Create provisional retained sessions under the existing 64-session cap. Persist valid new
  state before returning identity; if failure retire once, stop memory/MCP resources and classify
  uncertain cleanup. Never leak a provisional use lease or lie about capacity release.
- [ ] Add load-specific MCP normalization/re-disposition over current owner; fresh request servers
  and permission flow, mismatch/failure cleanup, no stored credential or allow_once restoration.
- [ ] Qualify 8MiB ledger/staging, 8192-byte control reserve, 64 local sessions, 100-second renewals
  and five-second mutation deadline on real test Redis: bytes/RSS, write amplification, realistic
  concurrent renew+foreground latency, no silent eviction and declared deployment capacity. If reserve
  cannot encode every bounded control fact, refuse before dispatch; no unbounded exception string/ID.
  A local64 pass is not a global key quota or all-load guarantee. Failure blocks CP3 and re-estimation.
- [ ] Test through real isolated TimeSeries Redis; Windows/WSL cross-loop and process-liveness cases
  retain platform capability differences. Never inspect unrelated keys.

### P3 — durable prompt/config/finalize and exact replay stream

**Files:** spec/shapes, existing runner/planning/tools/MCP guard/Gateway client, writer/lifecycle/
settlement/context/config/usage seams and their tests.
**Interfaces:** immutable sanitized user/live update entries, authoritative turn outcome/effect/cost,
and one CAS append/finalize/config transaction, consumed by P4.

- [ ] Write failing tests at admission, permission/cancel, pre-effect/post-effect, last flush,
  commit and late-cost receipt boundaries. Pin no cost duplication or lost historical approval facts.
- [ ] Pin acknowledged admission/pre-effect markers, crash immediately before/after an effect,
  ambiguous acknowledgement, failed post-effect write and failed final seal. Exercise Redis EXEC
  applied/reply-lost and not-applied separately: original request stays UNCERTAIN/no retry; independent
  load refuses an actual unresolved marker or validates an actually complete eligible seal. Never
  assert an uncertain write rolled back or turn missing/gapped state into stale load success. A model/tool never dispatches after a failed intent write.
- [ ] Add clean stdin EOF mid-turn rows with and without an effect marker: preserve authoritative
  teardown classification, do not synthesize a canonical CANCELLED commit, retain the unresolved
  marker and refuse resume. Separately test completed-and-sealed EOF success and sealed
  DELIVERY_INDETERMINATE refusal; marker expiry yields missing, never repaired history.
- [ ] Test every new paid-model role (Auto classifier, planner, answer, maintenance summarizer) and
  WRITE/EDIT/TEST/MCP boundary: cancellation during durability check, failure before producer, original
  gate frozen, registered-but-not-started suppression, terminal once, no retry or later producer leak.
  Capture-hook failure stays best effort; separate ACP refusal precedes capture and proves no
  physical send. Test each caller's one not_sent/zero receipt, no orphan capture intent, no integrity
  error/route-stop, GATEWAY failed terminal, no fallback/retry; include summarizer turn_id=None,
  concurrent ContextVar propagation/reset and scoped post_tool_json, with non-ACP unchanged.
- [ ] Test Auto refusal, classifier/config failure and eligible cancellation finalization after all
  required RPC/update flushes. Keep original active-slot/use lease until CAS ack; pipelined prompt is
  busy. Failure after RPC flush sends no second response, retains local pending intent/staging; any uncertain/MCP/effect/
  transport case refuses load. Assert exact REQUEST_CANCELLED during post-reply CAS and committed
  seal awaited before response-envelope return; timeout stays uncertain even if work later finishes.
  No synthetic canonical insertion or allocator rollback.
- [ ] Build user_message_chunk from vendored schema. Capture exact sanitized replayable updates
  through the existing outbound path; persist user and agent sides with provenance and stable order.
- [ ] Apply the closed emission inventory with structural/dispatch controls. Stage stored payloads
  before send, atomically finalize after authoritative commit or D8 healthy-uncommitted outcome,
  and preserve live-only best-effort paths.
  Add privacy sentinels for tool/context/unsaved bodies and direct/dynamic send bypass controls.
- [ ] Pin ledger/buffer cap and marker-headroom boundaries, including unpredictable progress floods,
  refusal before effects, mid-turn divergence and explicit delivered/undelivered durability notices.
- [ ] Integrate persistence staging/finalize with existing final-flush and commit decisions. A Redis
  failure after an effect is not an effect rollback; ambiguous delivery never becomes ordinary success.
- [ ] Serialize config updates via existing config_lock/publication authority and CAS; restore mode/
  strategy truthfully after a failure/crash. Recompute safe current config/notice publication on load.
- [ ] Prove attached compaction/hybrid/sliding and absent-engine history match their same-process
  paths, including cost receipts that arrive after terminal finalization and incomplete usage.

### P4 — non-empty load, concurrency and bounded resources

**Files:** spec, store, retention, MCP, shapes/errors, corresponding protocol/lifecycle/registry tests.
**Interfaces:** accepted load outcome map; exact-ID provisional reservation → validated lease/hydrate/
re-disposition → ordered conclusive notify flushes → one non-turn `{}` result.

- [ ] Write failing request/schema/cwd/root/missing/expired/foreign-lease/capacity/zero-entry tests.
  Error/zero-entry paths prove no replay, attachment or TTL refresh. Centralize only SESSION_BUSY.
- [ ] Reserve same-process identity synchronously before the first await; duplicate attached/reserved
  loads return SESSION_BUSY with no revision/TTL change. Unresolved markers refuse before acquiring
  ownership or hydrating an old snapshot, even after lease expiry.
- [ ] Implement load through NoticeControl/ResponseHandle and the dedicated writer; no direct stdout
  write. Recreate current approved memory worker, fresh MCP authority and compatible attached context;
  follow-up history uses canonical state once, not replay-derived state.
- [ ] After the load response is conclusively flushed, arm the existing idle-MCP owner for any opened
  re-disposed peers, even if no prompt follows. Do not simulate a committed turn to do so. Test no-
  prompt expiry, cancel/failed response, current config publication and retirement/quarantine once.
- [ ] Test two simultaneous loads, load/prompt/retire races, same-process duplicate identity, process
  loss, expired lease recovery, CAS conflict, replay teardown/cancel, response loss after final flush,
  cleanup failure and unknown lease ownership. Never release another owner's revision.
- [ ] Run race selectors at least 25 times on Windows using barriers/futures, not timing sleeps;
  exercise platform-shaped path/subprocess/lease cases in real WSL. Repeated load/retire demonstrates
  bounded maps, provisional states, MCP closures, memory workers and pending futures at current cap.
- [ ] Run focused protocol/store/writer/settlement/retention/MCP/context/memory/config/error-registry
  regression tests, real Redis selectors, scoped Ruff and diff.

### Checkpoint 3 — production persistence/load and compatibility

P1–P4 complete, current full checkpoint gate and review order. Include failure-stage matrix, retained
race counts/platform limits, main-only behaviors compared with source pin and exact schema contract.
Passing units do not replace real Redis or release either live client tier.

### P5 — history/refusal, independent-client and real-Zed feature acceptance

**Files:** integration/e2e/probe/verifier tests and v6 acpx/Zed evidence folders.
**Interfaces:** same evidence family bound to exact production source (no Task 0 stub/patch).

- [ ] First write failing schema/verifier tests for **both** acpx-restart and zed-resume evidence
  kinds: no temporary patch, non-empty exact replay, every required flush before `{}`, exact source/
  module/launch provenance, correct pre/post DB binding and follow-up canonical history digest. For
  acpx the equivalent client session identity/protocol evidence replaces Zed-only DB custody, not
  production source or replay proof. Omission/tamper/zero-entry/reordered-byte controls must fail.
- [ ] Pin restart history capacity below warning/at warning/at cap/over-cap; absent-engine 512 KiB and
  attached measured source/reservation behavior. Prove complete canonical history survives restart;
  attached strategy selection may summarize/drop ordinary model-context history only as current
  accepted policy permits. Exact protected outcome/effect/approval state survives in every strategy.
- [ ] On both real clients prove a first admitted healthy-uncommitted refusal: non-empty exact user/
  terminal replay, original NOT_COMMITTED and no canonical insertion, advanced sequence/cost, then
  follow-up canonical history once. Zed must retain the same binding after replay. Keep non-admitted
  empty refusals in R characterization and interrupted/uncertain refusal as separate failure cases.
- [ ] Cover genuine model refusal pre/post restart and context-window exhaustion; do not invent
  errors or reopen completed Plan 11.18. Record the resume-dependent P9.8-FU-5 criteria only.
- [ ] Use real independent acpx, actual optimus-agent processes, real Redis and Gateway. Lifecycle A
  creates the session and at least two prompts including approved effect-free and refusal/cancel
  paths; save exact live-update hashes, revision/TTL/history digest, cleanly exit. Lifecycle B loads
  same ID/cwd/MCP set, all replay hashes in order before `{}`, then continues with canonical history
  exactly once. Test missing/expired/live foreign/recovered lease/zero-entry/CAS cases on isolated keys.
- [ ] For **both acpx and Zed Lifecycle A**, stop only after the final turn's durable seal is
  acknowledged; record its exact revision. A flushed ACP response alone is not proof of that seal.
  Keep deliberate mid-turn close/failure cases separate from this completed-turn acceptance path.
- [ ] Under separate live approval use current real Zed, fresh hermetic profile/workspace and exact
  production entrypoint/module/source hashes. A creates prompted non-empty ledger; clean stop/copy
  proves non-null binding to exact ID. B advertises only actual top-level load support, sends exactly
  one distinct load and zero new; every replay flush precedes `{}`; a follow-up uses hydrated history.
  Clean B stop/copy retains the same non-null binding. Null/different binding is a failed feature gate.
- [ ] Bind feature acceptance to Task 0's exact Zed binary hash/version/revision. If it changed, run
  the full current-client gate (A-prime, all R cases and prompted A/B, including a fresh A-prime, private mapping, redaction and
  review) on the new identity under separate live authority before relying on production acceptance.
- [ ] Prove memory-on restart with the dedicated approved index Redis/Gateway/artifact configuration,
  and off/unavailable paths with their actual requirements. Keep index/unsaved buffers out of the
  ledger and revalidate current project/branch scope. Missing live memory-on prerequisites stay UNRUN
  and block its acceptance; #469's merged source is not service readiness.
- [ ] Redact all outputs; derive manifests, attest and verify committed sanitized bytes offline with
  private roots absent; tampered copies fail. Compare Task 0 null-binding boundary with final retained
  binding without claiming W1/stale-install cause was proved. Record actual versions/cost/skips/UNRUN.

### P6 — release evidence and truthful closure preparation

**Files:** release review; README, roadmap, registry pointer, docs hygiene and issue-record drafts.
**Interface:** source-bound acceptance report and proposed completion records; publication/closure
remain separately authorized.

- [ ] Search for duplicate conversation/turn/notice/writer/runtime owners, physical replay writes,
  unsupported resume advertisement, raw credentials/buffers/telemetry in persistence, zero-entry
  success and stale source claims. Audit *all* documents making changed current-state claims.
- [ ] Run release commands below and every offline verifier on the exact final source. Audit actual
  skipped/unrun tiers and independently preserve failed runs. Report coverage validity/product floors,
  reused measurements and unsupported-platform qualifications without rounding away failures.
- [ ] Prepare final evidence links, issue updates and independent review records. #240/#230/#254 can
  be closed only when their exact acceptance criteria are met and operator publication/closure is
  granted. Keep #256 pending its own accepted retirement disposition; never mark it proved/completed.
  Do not close #241/#222/#307–309 or parent resource/context work by implication.
- [ ] Before separately authorized PR/merge re-audit docs and CI identities. Following any authorized
  merge verify actual-merge workflows/checks, tested source/tree and logs; no synthetic-merge
  substitution. No cleanup before separately granted evidence-preserving cleanup authority.

### Checkpoint 4 — final release acceptance

P5–P6, same review order; exact-source full gate plus independent acpx/Zed/Redis evidence and private-
to-public attestation. Reviewer rejects any claim that a stub run proves production resume, that old
Windows/CI counts transfer, that Zed always could load, or that W1 was demonstrated.

## Verification commands and evidence accounting

These are **future commands**, not results of this assessment. Run from the isolated implementation
worktree after `uv sync --frozen --extra dev`; each native platform uses its own environment. A new
test/verifier path is executable only after the owning task creates it. P0 resolves versions and
exact pipeline scenario bindings from current `--help`; do not improvise an unsupported live command.

Focused tasks use coverage-free selectors for their affected files, for example:

```powershell
uv run --no-sync pytest --no-cov tests/unit/tools/test_plan117_current_client_contract.py tests/unit/tools/test_plan117_current_client_collector.py tests/unit/tools/test_verify_plan117_v5_current_client_evidence.py -q
uv run --no-sync pytest --no-cov tests/unit/acp/test_session_models.py tests/unit/acp/test_session_store.py tests/unit/acp/test_spec_protocol.py tests/unit/acp/test_session_retention.py tests/unit/acp/test_session_retirement.py tests/unit/mcp/test_client_disposition.py -q
uv run --no-sync pytest --no-cov -m requires_redis tests/integration/acp/test_session_store_live_redis.py tests/integration/acp/test_session_load_live_redis.py -q
uv run --no-sync pytest --no-cov -m e2e tests/e2e/acp/test_session_load_restart.py -q
uv run --no-sync python tools/verify_plan117_v5_current_client_evidence.py --manifest reports/plan-11-7-v6-current-client-gate/manifest.json --attestation reports/plan-11-7-v6-current-client-gate/redaction-attestation.json --bundle-root reports/plan-11-7-v6-current-client-gate
uv run --no-sync python tools/verify_plan117_v5_current_client_evidence.py --manifest reports/plan-11-7-v6-acpx-restart/manifest.json --attestation reports/plan-11-7-v6-acpx-restart/redaction-attestation.json --bundle-root reports/plan-11-7-v6-acpx-restart
uv run --no-sync python tools/verify_plan117_v5_current_client_evidence.py --manifest reports/plan-11-7-v6-zed-resume/manifest.json --attestation reports/plan-11-7-v6-zed-resume/redaction-attestation.json --bundle-root reports/plan-11-7-v6-zed-resume
uv run --frozen ruff check .
git diff --check
```

At each of the four implementation checkpoints run one current-repository full suite with coverage
before Fable then Codex review, as required by AGENTS/ADR-016. Use the current source's documented
profile/product report commands and floors, not v2's stale monolithic `--cov-fail-under=80` as an
invented substitute. Current CONTRIBUTING's canonical full gate and its separate validity check are:

```powershell
uv run --no-sync python tools/check_product_coverage.py --run-full-suite --groups tools/product-coverage-groups.json --report-json tmp/coverage/product-coverage-report.json --coverage-json tmp/coverage/coverage.json
uv run --no-sync python -m tools.testing.coverage_products validate --coverage-json tmp/coverage/coverage.json --gate-report tmp/coverage/product-coverage-report.json
```

The one full default-selection dataset enforces the Optimus group, Context Engine and model policy
at 80% using coverage precision-0 comparison; Evidence Handoff and aggregate are informational.
The validity check runs no second suite and requires the clean exact source/full default session,
known packages, complete rows and matching reports/run records. Checkpoint dependency selection is
also available as `python -m tools.testing.run_profile --profile checkpoint --base <recorded SHA>`;
it does not replace the required full coverage run. Default markers exclude live tiers; an e2e file
with zero selected tests is UNRUN, never acceptance. P5 marks its restart test `e2e` and uses the
explicit selector above, with real acpx/Redis/Gateway prerequisites. Execution re-pin verifies commands/floors
against the execution pin. Run required real alternate-OS checks for platform-shaped behavior.
Do not run a full suite for this document-only assessment.

The current-client verifier requires all three inputs: manifest, attestation and sanitized bundle root.
Its schema discriminates current-client-gate/acpx-restart/zed-resume; a gate/stub bundle cannot pass a
feature-evidence rule. Resolve/re-hash every eligible artifact beneath the named root, reject missing
attestation, path escape or substituted bundle, and fail when any required artifact is unavailable.

One coverage writer per worktree. Ordinary applicable hooks remain enabled. The narrow Plan12.2
intervening-commit coverage-hook bypass is not generalized to #240. If a review fix follows a full
run, keep the tested commit and exact fix delta distinct, run focused checks, and state whether new
full evidence is needed. CI checks must distinguish PR head/synthetic merge/actual merge.

## Review focus

1. Current Zed can reach empty-load despite contradictory observations: E1/E2 positive-signal latch.
2. Restart under different attachment/route/config can erase authority or change meaning: P1/P4
   compatibility refusal before mutation and exact protected state tests.
3. Crash after an effect/flush/write can create convincing false success: P2–P4 failure-stage matrix.
4. Repeated load/cancel/retire can leak ownership or exceed capacity: P4 deterministic races and
   bounded-resource tests, native Windows plus WSL capability qualifications.
5. New memory/tool/cost notices can persist private bytes or duplicate permissions/cost: P1/P3/P5
   privacy sentinel, inert-approval and receipt-once tests; pipeline tamper controls at E2/P5.

## Effort and stop boundaries

Engineering-day estimates include implementation, focused tests, evidence preparation and normal
review fixes for one implementer; exclude operator/GUI/service/CI waiting, paid usage and a new policy
design following a STOP. They are estimates, not an agreed issue label or a completion promise.

| Stage | Effort basis | Dependency / exit |
|---|---|---|
| v6 offline compatibility | Re-estimate after the scoped source pin, tests and review. | Combined reviewed #304/#240 draft PR with verified CI. |
| E3–E4 and CP2 current-Zed gate and reconciliation | Original v5 estimate 1–3 active days; re-estimate for the extra fixture and current prerequisites. | CP1, approved run row and current live authority. Any positive empty reachability stops production. |
| P1–P4 and CP3 durable port | Original v5 estimate 11–17 days, subject to owner release and current-source assessment. | Accepted Task 0, owner map, shared-file release and resource qualification. |
| P5–P6 and CP4 feature acceptance | Original v5 estimate 3–5 days, subject to current client and service readiness. | Production checkpoint, independent clients, approved services and release. |

The active estimates omit approval, CI, service and GUI waits. Reassess each at its checkpoint. A positive STOP requires a separate approved successor before production work.

## Definition of Done

- [ ] Exact v6 adopted under #240 with immutable predecessors and truthful issue custody.
- [ ] The scoped #304 compatibility candidate meets the offline definition of done above.
- [ ] Current-source pipeline gate independently accepted as ZERO_ENTRY_UNREACHABLE; owner map accepted.
- [ ] Historical evidence custody dispositioned without rewriting failures. #256 may explicitly remain
  pending under its own issue; accepting its retirement is not a prerequisite to closing #240.
- [ ] Healthy uncommitted exact UI replay, unchanged canonical history and sequence/cost continuity proved.
- [ ] Main-compatible durable state round-trips with exact current context/cost/config authority.
- [ ] Redis lease/CAS/TTL/recovery, non-empty replay-before-success and failure classification proved.
- [ ] Empty-load reachability tested for A-prime and every registered R class with real advertised support; interrupted effects cannot load as
  stale complete history; bounded replay, late-accounting and live-only classifications verified.
- [ ] Current session-cap/retention/idle-MCP/memory behavior preserved across load and repeated retirement.
- [ ] Real independent acpx restart and real-Zed binding retention/follow-up pass on exact source.
- [ ] All required redaction, private mapping, offline/tamper, unit, Redis, e2e, platform, checkpoint
  coverage/product-validity, Ruff, docs and authorized CI gates accounted for with qualifications.
- [ ] Final reviews and requested release records prepared; publication/merge/closure/cleanup occur only
  within their separately granted authority. Until then no claim of delivery or closure.
