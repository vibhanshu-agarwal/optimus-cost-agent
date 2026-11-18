# Plan 12.11: Memory and continuity (M3)

## Operator summary

Deliver automatic, checked memory that a person sees remembered, cited and forgotten in real Zed, with cross-session continuity and a welcome-back brief. Knowledge never expires through inactivity. There is no review queue.

CP2 may deliver extraction and accounting with automatic user-origin mutations disabled. New user admissions, updates and natural-language withdrawals remain off until an approved mechanism establishes the required authority. Explicit host commands remain Task 4 work. This interim safety disposition does not establish completion of automatic user admission or remove it from this plan.

Split M3 into two plans. Include plaintext recovery export and restore here; leave backups, cloud, encryption, rotation, recovery channel, import and pilot to the later plan. Closing this part closes neither M3 nor #235. Do not add a replacement loop, replay store, model picker, Postgres mirror or learning service.

```mermaid
flowchart LR
 U[User turns and commands] --> H[Host: trust, scans and authority]
 H --> E[Engine: Gate, memory and continuity]
 E --> G[Gateway]
 G --> R[Dedicated durable Redis]
 G --> F[Host recovery files and journal]
 R --> E
 E --> H
 H --> Z[Zed notices, citations and brief]
 H --> A[Existing usage capture]
```

| Decision | Recommendation and alternative |
|---|---|
| D1: Split | Allow 16 working days here and 12 later, excluding waits. All M3 needs approximately 28 days and is too large for four useful checkpoints. |
| D2: Redis | Use a separate instance behind Gateway. Sharing index Redis needs capacity isolation it does not enforce. Memory cannot be rebuilt from files. |
| D3: Extraction | Run concurrently with or after the answer. Prefilter turns without candidates and freeze latency, calls per 100 turns and cost forecasts. |
| D4: Display | Use qualified host cards or appended host text. Show the brief after seven days and through `/welcome`. Pre-prompt display is optional; neither surface is confidential. |
| D5: Recovery | Add export and restore now for three extra days. This moves M21 and export erasure here. The 13-day alternative has no copy and loses everything on volume loss. Declined sync consent disables export and shows that risk. |
| D6: Model switch | Do not force new route qualification for closure. With one eligible shipped route, use controlled bindings. If no second real route qualifies, actual-model proof stays UNRUN with the later issue as owner. Operator acceptance permits this part to close, not an M3-wide claim. Alternatively block closure on qualification of unknown duration. Run an available qualified route under separate release. |
| D7: Releases | Release operations separately. Hash approval grants no service, credential, Zed, paid, publication or merge authority. |
| D8: Recovery boundary | Use one confirmed location per project and refuse healthy non-empty restore targets. Export active payloads only, clean withdrawn copies, verify Git exclusion and disclose shell and sync limits. |
| D9: CP2 authority boundary | Select review ruling (c): automatic user-origin admissions, updates and natural-language withdrawals go off. Preserve optional agent admission and explicit host withdrawal capability. Reject residual acceptance (a). Confirmation-based alternative (b) requires a recorded disposition against the existing automatic-memory/no-review-queue decision before implementation. |

D1-D8 retain their approved provenance. D9 is the Codex-selected disposition requested in the CP2 re-review after review 8; it becomes governing only through authorized adoption of this successor.

The original estimate allocates three days to setup, four to store and Gate, five to integration and recovery, and four to qualification. Re-estimate remaining work at checkpoints. Issue labels and status live in #490.

## Goal and authority

Issue: #490 under #235. Later M3 custody: #491.

File: `docs/superpowers/plans/2026-11-16-plan-12-11-memory-and-continuity-implementation_v3.md`.

Original planning source: main `5b28b2b19b0a665484d04614044bd87abe179eef`, branch `agent/claude/plan12-11-m3-plan`, no reported changes. Original numbering inspection found 12.10 as the last numbered plan.

Successor review source: branch `agent/claude/p490-cp2`, HEAD `a9dec6b45c9df973d919a50b17b38dcf53c84c15`, no reported working-tree changes. The reviewed production fix is `bddcbcf545ea38066237f1bfd1f8cc8494378679`; the following commit changes only six reports.

Authority:
- Discovery v12, SHA-256 `33670c6b84aceccd629437c14f03609ba4293d70cde95b242dd93a2b0ad4fb14`, section 7 sole slice table.
- [Design v4](../specs/2026-10-22-plan12-memory-design_v4.md), SHA-256 `708e0e7831f6d4c56b5f6442cd37c4e02eecffd2659db04f3e6a6b1c54506ff9`, sections 2-6, memory accounting 7, K1, K2, K5, K6, 8.1 and 9.
- ADR-001, 005, 012, 025, 031-033 and 036-042, with the [decision index](../../decisions/README.md).
- Archived 12.10 v3/v1, 12.7 v4 and the source-bound memory reports and code.

Claude implements and owns chat; Codex reviews read-only. Follow Superpowers and AGENTS. Private provenance is never a project dependency. Decision acceptance, implementation, service operation, paid use, publication and merge remain separate authorities.

### Successor provenance and adoption

The operator approved the original plan at SHA-256 `77a7aec144b7b85ad379ff59bdb95912411b7753e6b3338628aa09e2f995824d` and D1-D8 on 2026-11-16: “Approve hash” ([approval record](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/490#issuecomment-6921405051)).

V2 recorded the Codex CP1 recommendation for `appendfsync always`, retaining same-connection WAITAOF and the unchanged CLIENT ID check. Its adoption provenance remains unchanged. Reviewed v2 SHA-256: `75ba9164e65dc9241fcb5d8af8af54005b6309484f31fdea8004eeff4e07f55e`.

[CP2 review 4](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/490#issuecomment-6952811578) approved the successor expectation of 12 user calls, zero agent calls, 12 total and eight `user_items_in_scope` skips for the scope-present workload behavior. Sealed targets, workload and historical results remain unchanged.

This successor records that expectation and the post-review-8 authority disposition D9. The operator's re-review request offered residual acceptance, confirmation or automatic user admission off, and asked Codex to choose. Codex selects off and extends it to automatic natural-language withdrawals because lexical target matching does not establish the meaning of the withdrawal.

This is a complete successor, not an amendment. On authorized adoption, update the Live implementation plan registry and docs index, archive frozen predecessors under repository relocation rules, record the review and disposition on #490, and preserve approval bytes and historical evidence. Do not claim an approval hash for this draft.

D9 is an interim checkpoint safety boundary. It does not silently supersede ADR-031 or design v4's automatic-memory/no-review-queue requirement. Before implementing a confirmation-based alternative, record the conflict and obtain the operator's disposition through a new decision record and any required complete successor. Do not edit frozen authorities.

No checkbox is set by this draft. Historical completion evidence remains attributed to its actual source and commands.

## Scope and Explicit Exceptions

In scope: automatic and compaction-time Gate; lifecycle/conflicts; durable events, projection, acknowledgement and retry; withdrawal/purge; commands, notices and citations; checked assembly; checkpoints, lookup, handoff and brief; scheduled/on-demand Agent Memory Repo export, journal and restore; real-store and real-Zed proof. Anything not excluded remains in scope.

D9 permits CP2 to deliver a safe off path. It does not exclude automatic user admission from the plan's final scope or justify closing the plan without its approved authority mechanism and evidence.

| Explicit Exception | Owner and obligation |
|---|---|
| Backups, cloud, daily snapshots, 30-day rotation | #491 under #235, Claude. Off by default; other-drive warnings, cloud consent and erasure boundaries. Here: same-drive recovery only. |
| Encryption, rotation, channel, encrypted restore and encryption-key retirement | #491. Design 6.1-6.2 and encrypted 6.3, P1, P5-d, M22-M24 and native K5-R1/R2. |
| Import, import K1/round-trip controls and consented 20-30-item pilot | #491. M13, M18-c, OC-2 isolation, private-source custody and optional ceiling. Export stays here. |
| Strength decay, consolidation and Postgres archive | #235 M6. Original M20 decay assertions; no-expiry/no-promotion checks stay here. |
| Model-callable `RECALL` | #235 M2. Automatic assembly and `/memory` suffice here; existing four model tools unchanged. |
| Actual second-model evidence without a qualified route | #491 under D6. Controlled-binding implementation/tests stay here. |
| `/why`, ambiguity and ranking/budget refinements | #235 M2; #242, #243, #245. Baseline ranking/fitting stays here. |
| Graph and decision linking; dependency intelligence | #235 M7; #258 and M5a. Invalidation IDs only here. |
| Broad telemetry, savings and general benchmark campaign | #303, #248, #463, respectively. |
| Conversation/live-approval replay | P11-FEAT-ZED-RESUME, existing session-load lane. |

Preserve full remainder custody under #491 and #235; no second work pool or later plan number is created here.

### Later-plan security contract

Excluded security, copy and import obligations move whole; Task 0 files their full design-v4 and M3 acceptance checklist in #491.

The recovery channel requires proven mediation of every enabled automatic, file, native, MCP and shell path on Windows and Linux; otherwise the channel, encryption and rotation stay visibly unavailable.

`cryptography` is not added here; later P1 requalifies its licence, Windows CPython 3.14 wheel and Linux support while preserving historical custody fixtures.

## Design choices

### Package, credential and setup boundaries

Neutral engine owns contracts, Gate, folding, applicability, ranking and continuation; no host, Gateway, security, evidence or model-policy imports. Inject typed ports, not keys or Redis commands.

Host owns canonical inputs/lineage, trust, registry, FilePolicy/scans, user actions/notices, files/journal, authority and final sanitization. Gateway owns Redis credentials/connections and authenticated recovery data.

Engine absence preserves today's floor. Outages degrade independently, never stop ordinary work or create authority. Lost/corrupt registry requires recovery.

Use container `optimus-memory-store-redis`, volume `optimus-memory-store-data`, loopback `6394` and M1 image `redis@sha256:298e5b3bc566bade82f46ad5511777a4a07a294097ce16ada2f6a42be5239df5`.

Limits remain maxmemory 512 MiB, container 1024 MiB, noeviction, AOF `appendfsync always` and periodic RDB. Verify version, WAITAOF, persistence and resource at open/reconnect. No SQLite, shared test Redis or mirror.

Add `optimus-trust memory-setup --store` without changing index setup. Bind config, hash-only ACL and resource to approval, manifest and Gateway identity; absent config preserves identities. Reuse ADR-037 topology/concurrency checks; never adopt unidentified resources.

Only new keystore secret: Gateway's generated Redis ACL password, service `optimus-gateway-memory-store`. Tests use isolated password entries, never encryption keys. Host keeps URL/key only. Qualify Windows Credential Manager and Linux Secret Service; CI without Secret Service proves unavailable.

Same-key hosts can assert another scope; test this residual and cursor binding. Dedicated setup uses neither shared `ensure_local_redis` nor index Redis.

Task 4 checks merged #487's run-ID reuse/refusal, including no-auto-start; do not redo #480. Authenticate dedicated identity beyond TCP. #488/Phoenix is unnecessary; #486's record-replace retry is merged. Validate Windows records.

### Durable commit and capacity

One stream is authoritative for lifecycle order. Events bind immutable project, item, version and event IDs, expected version, idempotency, origin, status, scope, anchors, lineage and bitemporal validity. Projection, version, dedupe, notice and checkpoint indexes rebuild.

Keep purgeable payloads outside stream entries, in the project's payload hash. The event append and associated payload write share the checked transaction. Purge removes every affected payload version; payload-free lifecycle records remain. Missing required payload is damage, never an empty accepted memory.

One monotonic fenced lease reconstructs lookup at verified head before admission. Check expected version/idempotency there, not in serving projection. `WATCH` and `MULTI` validate lease, fence and head with one event append; lease bookkeeping is separate. Lost lease or moved head prevents publication. Do not claim multi-key rollback from Redis transactions; test refusal and partial-write hazards explicitly.

Hold the same physical connection through append/EXEC and separate `WAITAOF 1 0 <timeout>`; compare local count >=1. Serve only confirmed matching projected versions. AOF-off, unsupported/malformed replies or fsync failure disable admission, never weaken durability.

The unchanged CLIENT ID check remains part of the per-write proof; `appendfsync always` does not replace it. If watermark publication cannot establish availability, report projection pending.

Timeout is unconfirmed. Retry same key/digest reconciles the existing event and verifies persistence on its connection; no second logical mutation. Different payload conflicts; no hidden retry loop.

No accepted-record, checkpoint or deletion TTL/eviction. Ceiling remains 384 MiB logical plus 128 MiB reserved for deletion/control. Refuse new saves visibly, preserve knowledge and report history/off-archive growth. Measure RSS, COW and disk separately.

K2 remains frozen: 100k events, 10k live items, four clients; ack p95 <=1.5 s, projection-after-ack p95 <=250 ms, restart <=60 s, logical purge <=1 s after confirmed tombstone, rewrite/snapshot <=120 s, RAM <=1 GiB, disk <=4 GiB. Include slow persistence and separate index rebuild; preserve misses. Zero acknowledged loss covers tested crashes with volume intact, not hardware or volume loss.

Preserve the released-test-store measurements:
- Under `appendfsync everysec`, 50 consecutive confirmed saves took p50 1.003 s, max 1.006 s, run `20261116T201743-42348-455d0c`.
- Under `appendfsync always`, 50 consecutive confirmed saves took p50 8.7 ms, p95 11.7 ms, max 15.6 ms, run `20261116T204113-43152-751697`.

These sequential measurements do not establish K2 acceptance. Its thresholds remain unchanged; K2 measures contention, slow storage and watermark loss/reconstruction under `always`.

### Gate, extraction and accounting

Gate alone writes; no model mutation. Every candidate, command, edit and switch-on passes the existing tool-output injection scanner, secret, B1 and source-overlap checks and origin, speech-act, span, scope, revision and conflict validation. Blocked payload never persists.

User extraction sees sanitized raw user blocks and host spans only. Assertions, preferences and decisions may support origin; questions, hypotheticals and quotations do not. Span coverage alone establishes neither the meaning of an act nor authority to change an item. Ambiguity goes off.

Agent extraction sees completed work and host evidence with transitive lineage: optional episode, procedure or lesson only. External, document or tool directives, gaps and user conflicts go off, including followed README instructions. Repetition, tests, compaction, pinning, type and citations never raise trust; only established user origin constrains.

Off records contain pointer, origin, scanned title/reason, no payload; active cap 200 and 512 KiB per project, recoverable unserved archive overflow and growth alert. No inactivity deletion.

Switch-on repeats deterministic exact-source extraction/scans without raising the optional ceiling. Absent/RAM-lost source refuses; never mine diagnostics. Untrusted workspaces are read-only. Authorized user updates supersede with history; stale versions never overwrite.

Compaction uses covered raw spans before release, never summary_text. Digests/watermarks dedupe; gaps stay off/unavailable. D9 applies equally to user candidates reached through compaction or switch-on.

#### D9: interim CP2 user-off policy

In CP2, automatic user-origin proposals cannot admit, update, supersede or withdraw an item. Apply this at the automatic extraction boundary independently of English patterns, model speech-act labels, model-selected targets or otherwise valid spans.

Valid automatic user candidates go off; existing question, malformed-input, dropped-candidate, scan-block and refusal outcomes retain their meaning. Off records never count as accepted user items, constrain agent work or become serving candidates.

Keep explicit store/Gate withdrawal capability. Model-interpreted natural-language withdrawal is off. `/forget <id>` and other authenticated host commands are Task 4 interfaces, not delivered CP2 alternatives.

Preserve raw-source, scan, scope, version, trust and lineage controls. D9 does not authorize retaining full candidate payload in an off record, promoting an agent lesson, bypassing the Gate or weakening receipt accounting.

No automatic path may resume user mutation through a configuration default, restart, compaction, switch-on or a model-provided field. The off outcome must not generate Remembered, Updated or Forgotten notices.

Task 4 owns resolution of safe resumption under #490. A notice displayed to the user, silence, elapsed time, an earlier approval or a model response does not establish confirmation. Alternative (b), if selected through a recorded operator disposition, must bind a fresh authenticated user action to the exact candidate/source and the current target/version where applicable. Missing source or stale binding refuses.

Keep authorization acceptance separate from durability's `unconfirmed` state. Do not call a candidate saved merely because the user accepted it; the ordinary Gate and durable commit still apply.

Do not add a review queue or silently change the accepted automatic-memory product requirement. If a safe conforming mechanism remains unestablished, preserve the off path and withhold the dependent final completion claim.

#### Scheduling and capture

Extract concurrently or after answer dispatch: current user text is already in its prompt. Bounded workers own settlement; stale results recheck head/conflicts. Agent extraction follows completed evidence.

Deterministic prefilter skips empty turns, commands, acknowledgements, status-only turns, pure questions without assertions, extracted spans and agent results without new evidence. Known hostile/quoted content can yield off metadata without inference. Ambiguous assertions proceed; test paraphrases/retractions against omission.

Allow one user request `memory.extract_user` and one agent request `memory.extract_agent`. Compaction `memory.compaction` shares the user slot; no third call. Commands, switch-on, checkpoints, brief and recovery use zero inference; ambiguous switch-on refuses.

Use the configured summarization role and `stage=summarization` through existing GatewaySummarizerCall, capturing/CaptureIntent, TurnSettlement and durable capture, with purpose in receipts. No new debit or automatic extraction retry.

Cap each request at 8,192 estimated input tokens including framing and 512 output. Registry USD 0.50/M input and 2.50/M output gives USD 0.001664 for a 2,048/256-token planning call, USD 0.0003328 per turn at 20 calls/100 turns (USD 0.03328/100), and USD 0.010752 for two capped calls.

These are zero-paid workload forecasts, not measured charges or universal bounds. Reprice the approved registry before release.

#### Task 3 expectations and historical evidence

Keep sealed `targets.json`, workload and rubric unchanged. Historical baseline expectation remains 12 user and eight agent calls, <=20 calls/100 turns; added first-response p95 <=100 ms versus off, settlement p95 <=3 s, inference latency separate. Production frequency remains unknown.

The approved successor expectation is 12 user calls, zero agent calls, 12 total and eight `user_items_in_scope` skips when a live user item is present before the workload's relevant agent turns. Preserve the empty-scope positive control for optional agent admission.

D9 prevents automatic user saves from creating that initial condition. Therefore qualify two explicitly identified initial states without changing sealed turn text:
- Empty user scope under D9: expect 12 user calls and eight agent calls, 20 total, with zero `user_items_in_scope` skips and zero automatic user mutations.
- Scope-present control, with a separately declared real user item established through the checked host path: expect 12 user calls, zero agent calls, 12 total and eight scope skips. The fixture's creation and source identity must be recorded; it is not an automatic admission result.

Never count off records as live user items or silently seed the empty-scope run. Declare initial state before each run. Keep all latency, accounting, safety and maximum-call gates operative. Preserve the lease-time check for a user item arriving during agent inference.

Report historical `matches_expected`, the named effective expectation and every other gate separately. Once this successor is authoritative, the tool's exit follows the effective scenario and all applicable gates; an historical comparison alone is not an operative failure. Do not erase earlier false verdicts or exit codes.

The bddcbcf measurement remains historical: 12 user calls, zero agent calls, nine admits, three off records, eight scope skips and zero incomplete outcomes. It does not test D9. Its `m3a_exit=1` remains unchanged.

Failed, cancelled, malformed or uncertain extraction admits no unsupported item and shows incompleteness. Settle late, discarded and failed attempts; unknown cost is not zero. Close capture after workers settle or record an incomplete lifecycle. Preserve CF-2 and alerts-only policy.

### Serving and prompt caching

Linked worktrees share project identity; clones/forks do not. Applicability, trust and authority stay separate.

Check current event/projection version, status and FilePurpose.ANCHOR hashes. Changed, missing or denied support becomes needs-reverify: omit or label an optional unverified hint.

Rank anchor, scope and type with stable ID/version ties; protect user constraints and initially allow three optional memories with omissions. Typed memory hits bypass file-shaped Hit/readers; memory works without index.

Order protected state, constraints, required evidence, optional material; truncate brief first and report required overflow.

Mutable memory, constraints, brief and handoff stay after ADR-039's breakpoint, outside both indexed builders. Preserve ADR-041; changed memory, brief or non-ASCII must preserve prefix bytes/boundary and full payload binding.

Serve ID, version, origin, status, applicability and evidence. Validate `[memory:<id>@<version>]` against current served versions. Invented, obsolete or missing required citations fail qualification; a supplied-memory footer cannot repair support. No paid repair loop.

### Commands, notices and continuity

Host commands run before inference/classification, never from model/tool text:
- `/remember <statement>` submits a checked user candidate with confirmed, pending, refused or unconfirmed outcome.
- `/forget <id>` and `/memory forget <id>` withdraw while retaining internal history.
- `/forget <id> --purge` requests confirmed deletion.
- `/memory` and `/memory view <id>` show paginated history, state, source, capacity, notices and recovery limits.
- `/memory edit <id> <statement>` uses expected version and scans, never origin promotion.
- `/memory switch-on <id>` runs deterministic exact-source checks or refuses.
- `/welcome` displays the historical brief.
- `/memory export` and `/memory restore <generation>` use the fixed recovery location, no arbitrary path/import.

Malformed syntax/attachments get help, not paid inference. Advertise commands with /savings via available_commands_update after session/new flush, independently of savings setup. Preserve slot, cancellation and delivery ownership.

Purge uses ACP `session/request_permission`: host-generated request/tool-call identity, project, item, version and boundary and one-shot Purge/cancel. Server pending state accepts only its matching client RPC response, never always approval.

Recheck version; change, reconnect, cancel or expiry needs fresh confirmation. Model text, tools, fake commands and card IDs cannot create or answer it. Test forgery, replay, wrong session, stale version, unsupported client and cancel: zero purge writes. Bind restore mapping and sync consent similarly.

Host `MemoryNotice(event_id,item_id,version,action,durable_state,projection_state)` derives from outcomes. Only fsync-confirmed Remembered/Updated; delay and uncertainty explicit.

Qualify model-free ACP tool-call/update cards with reserved `memory/<event_id>`; separate model IDs and escape bounded labels, controls, bidi and Markdown. Prefix stripping alone is insufficient.

Resend the same ID/state on reconnect; durable backlog preserves notice obligations without changing commits. Purge scrubs obsolete text. P5-c fallback: appended host text; P5-b: first response plus /welcome; neither proves P5-d privacy.

Checkpoint every ordinary settlement. Bind project, session, sequence, branch, worktree, baseline, provenance and outcome. Include objective, amendments, plan hash and references for completion, verification, pending decisions and remaining work.

Scan fields; source text becomes pointers/incompleteness. Separate from SummaryCheckpoint and session ledger. Lookup prefers latest eligible same branch/worktree; killed turns retain the last settled checkpoint. Status questions never replace objective.

Handoff preserves live host state across bindings, not authority; fresh sessions receive history only.

After >=7 days show the brief at first response, never below threshold; /welcome always works. Check gap before resetting last-session time. Target 1-2K tokens: dated work, pinned/applicable facts, invalidations, relevant changes “N of M commits”; missing, shallow or rewritten baseline explicit. No 30/120-day expiry.

### Workspace recovery copies

One confirmed export location per project: `.optimus/memory-recovery/` in the chosen trusted worktree. Persist canonical destination privately; linked hosts share it and writer lock, not one copy each.

Missing destination means unavailable, no automatic replacement. Confirm relocation and inventory prior locations until cleaned.

Export dirty projects every 15 minutes while host runs, at clean shutdown best effort and via /memory export; catch up next launch.

Agent Memory Repo generations carry active payloads, registry, payload-free lifecycle, version and exclusion metadata and authenticated manifest. Recheck format first. One writer, staged/fsynced atomic publication; retain Windows rename limits.

Runtime protection: `src/optimus/guardrails/runtime_tree.py` already denies model READ, WRITE and automatic context for `.optimus`, lexically and by resolved target. Reuse it.

Test export paths through file guards and FilePolicy, Windows casing, a real junction and a real Linux symlink; verify no bytes opened and ordinary-path positive controls. Keep explicit runtime command-token denials.

TEST/shell residual: this rule is not an execution sandbox; authorized code may read indirectly. Export active payloads only; off, withdrawn, purged, conflicted and superseded states carry no old text or titles.

Withdrawal retires every managed generation containing the payload and publishes replacement exclusion state; Redis history remains. Until cleanup succeeds, /memory shows “withdrawn; plaintext recovery cleanup pending.”

Test indirect canary access by an authorized synthetic test, then its absence from all managed generations after withdrawal. No confidentiality, forensic or external-copy promise; shell authorization and untrusted-output rules still apply.

Git residual: before first payload, create export-local `.gitignore` containing `*` if absent; never overwrite the user's file.

Check effective git check-ignore exclusion and git ls-files for tracked destination content before publication. Ineffective, tracked or unverifiable exclusion refuses export before payload write and shows remedy; non-Git folders need no Git check.

Test unignored workspace, incompatible existing rules, tracked content, force-add detection and normal ignored publication. This cannot prevent forced addition, subsequent ignore edits, copying or pushing old commits; disclose at setup and /memory, with no history rewrite or root-ignore change. Intentional host writes do not grant model WRITE.

Known sync roots need bound warning/consent before first write; refusal writes nothing. Show last success, dirty age, failure, cleanup and loss window. Same-drive plaintext is not backup; sync history, recycle bins and external copies lack guaranteed erasure.

### Restore and deletion continuity

Gateway signs manifest with domain-separated HMAC derived from its generated ACL password, no new host secret. Bind hashes, project, registry and store identities, generation and deletion sequence/checksum. Setup preserves password.

Recover same-machine volume loss only with surviving keystore, config and journal; missing root/continuity means unavailable/unknown.

No live merge: restore only an empty target project or recovery-required project held out of serving without a healthy committed head; other projects may stay live. No flag bypasses healthy non-empty state.

Refuse `RESTORE_TARGET_NOT_EMPTY` before altering live events/idempotency. No winner selection for live version conflicts.

Stage and authenticate chosen generation; apply freshest verified withdrawals/tombstones, validate anchors and confirm registry mapping. ProjectRegistry.restore repairs missing registry only, never overwrites existing or merges ambiguous/many-to-one mappings.

Fence/compare target again before publish; concurrent write or moved head aborts. Interrupted staging stays unserved and resumable/discardable.

If linked-worktree copies or supplied generations differ, show authenticated project, head and deletion frontier and require selection; no merge or timestamp winner. Current deletion journal applies regardless of age. Unknown continuity stays unserved; metadata grants no trust or approvals.

Fsync payload-free deletion intent before dispatch, then its authenticated journal outcome. Unfinished/uncertain journal blocks restore publication. Test crash between exclusion/journal confirmation followed by volume loss; old export alone cannot prove freshness.

Withdrawal excludes the item, invalidates dependants and cleans exported payloads, retaining internal history.

Purge confirms tombstone before destruction, journals it, removes event, projection and vector payloads and affected checkpoints, summaries, notices and all managed export generations, completes AOF rewrite/fresh RDB and regenerates clean export.

Reconcile multipart/orphan files and interrupted publication; failures preserve exclusion. Counters alone do not establish physical completion. Trusted inventory must cover the declared boundary; unexplained or malformed files keep purge pending. Gateway removes no files based on resemblance. Operator-assisted cleanup follows the repository runbook and its coordinated stopped-store maintenance requirement.

Inventory Redis, files, RAM and delivered context. Separate exclusion from `pending`, `completed-within-declared-boundary`, `completed-attested` and `unbounded/unavailable`.

Here prove managed live/export boundaries, never crypto-erasure/external attestation. Known synced plaintext prevents overall “fully erased”; Q27 remains excluded.

## Prerequisites

The original plan's prerequisite statements were planning-time facts, not current status. Recheck every dependent capability before use; issues own work status.

| Requirement | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|
| Original number, hash and D1-D8 approval | yes | Operator | Original approval is recorded on #490; this grants no additional operation release. |
| V3 adoption and D9 authority | no | Operator/Claude | Merely unauthorized: record the disposition and adopt the complete successor before relying on changed gates. |
| Isolated checkout and M0a, M0b, M1 interfaces | yes | Claude | Recheck source, branch, cleanliness and interfaces before execution. |
| CP2 user-off policy | no | Claude | Genuinely absent at the reviewed head: buildable now, before dependent verification. |
| Production continuity/recovery paths and compaction integration | no | Claude | Genuinely absent: Task 4 delivers them; CP2 cannot claim their evidence. |
| Later M3 issue | yes | Claude | #491 owns the excluded obligations; verify its full checklist before closure. |
| Machine readiness for each dependent run | unknown | Operator owns machine; Claude inventories | Genuinely hard until established: verify Python, uv, frozen environments, Docker capacity, image, AOF, WAITAOF, native keyring, Zed, acpx, GUI, WSL and valid run recording before dependent work. |
| #487 merge | yes | Owner/operator | Task 4 verifies the merged identity check. |
| Second real route | unknown | Operator/Claude | Genuinely hard until established: check availability; D6 assigns absent real-model evidence to #491. |
| Recovery readiness | unknown | Operator/Claude | Genuinely hard until established: verify format, destination, Git exclusion, sync consent, integrity and deletion state before dependent work. |
| Safe automatic user-mutation resumption | unknown | Claude/Operator | Genuinely hard until the mechanism and any authority conflict are dispositioned. Task 4 establishes it before dependent implementation or final admission claims. |
| Operation/publication releases | unknown | Operator | Merely unauthorized where capability exists: verify the exact existing release or obtain the named release before use. |

Unknown prerequisites require explicit early establishment before dependent tasks. An unavailable prerequisite cannot support a Definition-of-Done claim.

## Files and inventories

| Boundary | Files and obligations |
|---|---|
| Engine/host | `src/context_engine/{memory_contracts,memory_gate,memory_projection,continuity}.py` and typed retrieval/context_pack branch. `src/optimus/context/{authored_memory,memory_extraction,memory_recovery}.py`; integrate assembly, session, maintenance and registry. |
| Storage/ACP | `src/optimus_gateway/{memory_store,memory_files,memory_journal}.py`, `src/optimus_security/{memory_store_contract,memory_store_config}.py`, packaged `src/optimus/context/memory_store_defaults.json`, `src/optimus/acp/{memory_commands,memory_notices}.py`. Integrate setup, launch, manifest, identity, Gateway/spec, local_infra and prompts; reuse runtime_tree guards. |
| Real boundaries | `tests/integration/memory/{conftest,test_store,test_lifecycle,test_continuity,test_recovery,test_native_keyring}.py`, `tools/plan12_memory/{m3_admission,m3_k2,m3_evaluate}.py`, `reports/plan12-memory-m3/`. Keep sealed workload and original comparison oracles. |
| D9 controls | `tests/unit/context/test_memory_extraction.py`, `tests/unit/context/test_memory_extractor.py`, extraction wiring tests, Gate tests and `tests/unit/tools/test_plan12_memory_m3_admission.py`. Exercise public extraction and real-store paths, not only helper predicates. |
| Inventories | Closure entrants join ESTABLISHING_EXECUTION_GIT_PATHS in `tools/probe_p11_zed_session_load.py`. Sinks join `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json`; JSON uses ensure_ascii=True. Join Gateway route, auth, framing, dispatch, identity and redaction inventories. |
| Walkers/children | Reasons: `tests/unit/guardrails/test_tracked_file_scanners.py`. Git listings: _INDEX_LISTINGS in `tests/unit/tools/test_tracked_repository_files.py`. Child sites: `tests/unit/tools/run_context_child_sites.json`; cheap launchers: _REVIEWED_CHEAP_LAUNCHERS in `tests/unit/tools/test_test_profiles.py`. Applicable core nodes join `tests/profiles.toml` [parallel].serial; process tiers stay outside core parallelism. |
| Configuration/docs | Register/exclude requires_plan12_memory_redis in pyproject, run-context and profile guards; reuse/update isolated requires_os_keyring_write. Platform readers get platform tag. Preserve historical pyproject fixtures/pins. ADR, indexes, ADR-022 pointer, runbook and gitignored checkpoint log follow custody rules. |

## Tasks and verification

Use TDD, real-boundary checks, class sweeps and revert controls. Preserve default selection/conftest, frozen environments and one coverage writer. Commands grant no live release.

### Task 0 - attainable work and custody

- [ ] Verify source, status, worktree/branch choice, inputs, numbering, every unknown and price arithmetic; record availability separately from authority.
- [ ] Preserve authorized issue/plan/index filing and #491's full excluded M3 acceptance checklist: design 6.1-6.3, K5-R1/R2, M22-M24, native backends, P1, complete channel mediation, erasure attestations, backups/cloud and OC-2 pilot. Add D6 custody; no personal content.
- [ ] Preserve sealed targets.json, workload, rubric, manifests, releases and original exact hash. Bind this successor's adopted bytes and source separately. Verify with `Get-FileHash -Algorithm SHA256`, `git status --porcelain=v1 --untracked-files=all`, `git rev-parse HEAD` and `git worktree list --porcelain`.
- [ ] Establish each unknown prerequisite before its dependent task. Record D9 and any later authority disposition on #490; update the registry/index and maintain the owner-held checkpoint log.

### Task 1 - contracts, setup and capabilities (CP1)

- [ ] Define typed candidate, event, commit, notice, served-memory and checkpoint contracts, injected ports, MemoryGate.admit, folding and lookup. Reject invalid origin/status and unknown fields.
- [ ] Implement setup and authenticated `POST /v1/context/memory` for capabilities, admission, read/list, withdrawal, purge/status, checkpoints and recovery. No raw command, key or arbitrary path. Bound requests to 256 KiB, replies to 1 MiB and writer queue; erasure cannot monopolize reads. Define and test closed recovery request/reply shapes (`export`, `restore`, `restore_status`); return `MEMORY_OPERATION_UNAVAILABLE` until Task 4 implements recovery.
- [ ] Test auth-before-body, framing/deadlines, identity replacement, cursor binding and same-key residual, no-config compatibility and real isolated password custody/deletion.
- [ ] Release Z0: synthetic zero-paid real-Zed P5-b/c proof, versions, screenshots and logs and fallback; no P5-d secret or privacy claim.

Run `uv run --no-sync pytest --no-cov tests/unit/context_engine tests/unit/context tests/unit/acp/test_memory_wiring.py tests/unit/optimus_gateway -q` and Ruff; native cases separately with `-m requires_os_keyring_write`.

Produce setup, credential-boundary and client-capabilities JSON.

### Task 2 - durable store and deletion

- [ ] Implement all commit and capacity controls. Test real Redis for competing writers, expired fence and moved head, identical and conflicting retries, disconnections around append, fsync timeout, AOF-off, OOM and killed projection recovery.
- [ ] Implement journal, withdrawal and resumable purge. Interrupt each tombstone, journal, payload-removal, rewrite and snapshot boundary; inspect real keys and multipart AOF/RDB using encoded canaries and allowed-record controls. Preserve pending states, malformed-inventory negatives and operator-assisted cleanup boundaries.
- [ ] Qualify frozen K2 with independent expected identities, slow persistence, COW and separate index load. Record `durability.json`, `capacity-k2.json` and `erasure.json`.

Run `uv run --no-sync pytest --no-cov -m requires_plan12_memory_redis tests/integration/memory/test_store.py tests/integration/memory/test_lifecycle.py -q`.

### Task 3 - automatic extraction and capture (CP2 with Task 2)

- [ ] Implement extraction, prefilter and workers; test every Gate case above, including summary-attribution forgery and short-paste residual. Preserve genuine user-command/Gate and optional agent positive controls without representing them as automatic user admission under D9.
- [ ] Implement D9 at the automatic extraction boundary. Exercise new admission, targeted update, retraction, forged labels/spans/targets, word-order changes and multiple proposals through `submit()` and the Gate/store. Assert zero active user admissions, updates and withdrawals; pre-existing user items remain byte/version equivalent.
- [ ] Verify off metadata contains no authoritative payload, cannot be served, cannot satisfy `user_items_in_scope` and cannot produce save/update/forget success notices. Preserve scan, malformed, question, refusal and incomplete outcomes.
- [ ] Retain empty-scope agent admission, scope-present pre-call skip and lease-time race controls. A revert of D9 must make a named test fail.
- [ ] Integrate existing Gateway capture and settlement. Test known, unknown, late, discarded and failed attempts; purpose, cancellation and worker-close ordering. Offer every physical receipt despite an earlier receipt failure.
- [ ] Qualify the named empty-scope and scope-present expectations, frozen latency/call ceilings and accounting gates. Record `admission-k1.json`, `accounting.json` and `extraction-overhead.json`, with initial state and effective-policy identity. Controlled upstream proves plumbing, not extraction quality.
- [ ] After all source, successor and drift changes, run the one final-head broad unit selection, Ruff and applicable hooks. Preserve earlier failed/incomplete attempts. Do not call focused or coverage-free evidence a full-suite result.

Run Task 1's command, `uv run --no-sync pytest --no-cov tests/unit/usage -q` and Task 2's real lifecycle selection where affected.

The CP2 broad selection is:

```bash
uv run --no-sync pytest -p no:cacheprovider --no-cov -q tests/unit/acp tests/unit/context tests/unit/usage tests/unit/agent tests/unit/context_engine tests/unit/optimus_gateway tests/unit/gateway tests/unit/security tests/unit/tools tests/unit/guardrails tests/unit/docs
uv run --no-sync python -m ruff check .
```

Run the broad selection once on the final head under the standing cadence. A failure or later source change needs disposition before repetition.

### Task 4 - continuity, recovery and Zed (CP3)

- [ ] Before dependent implementation, establish the safe user-authority mechanism and disposition any conflict with ADR-031/design v4. Keep D9 until that mechanism is approved and verified. A notice or silence alone cannot activate a candidate. Record any confirmation-based product change in a new decision record and complete successor; no queue or silent authority change.
- [ ] Verify merged #487 behavior. Implement commands, bound permissions, notices and reconnect. Test all command/notice design cases and both prefix builders, including non-ASCII changes. Q4: bounded, paginated `/memory view` history preserves earlier versions through withdrawal and respects purge; latest-event `read` remains sufficient for the current store primitive.
- [ ] Implement serving, checkpoints, lookup, brief and handoff; test real Git worktrees, clones and branches, fresh and killed processes, rewritten baseline, 7-, 30- and 120-day clocks and distinct controlled bindings.
- [ ] Complete compaction extraction from covered raw source, explicit gap outcomes, off-source availability/refusal and recoverable unserved overflow archival/growth visibility. D9 remains effective on every user-origin path until approved resumption.
- [ ] Implement recovery and every stated residual test: runtime aliases, indirect TEST, active-only exports and withdrawal cleanup, Git exclusion/tracked refusal, one destination/divergent generations, consent, integrity/deletion frontier, mapping, non-empty refusal with unchanged live events/idempotency, concurrent admission and crash/volume loss. Q3: durable host knowledge detects that an existing project previously held memory after its store is emptied, shows recovery-required and prevents replacing its recovery copy with an empty export.
- [ ] Released zero-paid Zed: operator types; Claude launches and captures commands, remembered, cited and forgotten memory, brief and recovery status. Independent real acpx proves protocol separately.

Produce continuity, prompt-layout, citations, recovery, copy-inventory and zed-ui JSON reports.

Run Task 1's command, `uv run --no-sync pytest --no-cov tests/unit/acp tests/unit/agent tests/unit/guardrails -q` and `uv run --no-sync pytest --no-cov -m requires_plan12_memory_redis tests/integration/memory/test_continuity.py tests/integration/memory/test_recovery.py -q`.

### Task 5 - qualification and final gate (CP4)

- [ ] Drive observed production transitions through `tools/plan12_memory/m3_evaluate.py` and the existing grader; never manufacture traces from expected events. Run the case matrix, Windows and real WSL/Linux checks, class sweeps and reversions.
- [ ] Qualify the approved final admission mechanism. D9 off-path proof alone cannot establish automatic-user-admission completion.
- [ ] Run released paid Zed comparisons and return proof; actual second-route proof follows D6. Audit every current-state document and inventory, then run one final-head Windows full suite with coverage from PowerShell and Linux PR CI.
- [ ] Bind failures, limits, source identities and actual CI SHAs in `verification.json` and `qualification.json`. Publication/merge need separate authority.

```bash
uv run --no-sync python -m tools.plan12_memory.evaluate --validate-only tests/fixtures/plan12_memory
uv run --no-sync python -m tools.plan12_memory.m3_evaluate --config reports/plan12-memory-m3/run-config.json --output tmp/plan12-memory-m3
uv run --no-sync pytest --no-cov tests/unit/tools/test_verify_plan996_logging_surfaces.py tests/unit/tools/test_run_context_child_sites.py tests/unit/tools/test_test_profiles.py tests/unit/tools/test_tracked_repository_files.py tests/unit/guardrails/test_tracked_file_scanners.py tests/unit/docs -q
uv run --no-sync python -m ruff check .
```

```powershell
uv run --no-sync python tools/check_product_coverage.py --run-full-suite --groups tools/product-coverage-groups.json --report-json tmp/coverage/product-coverage-report.json --coverage-json tmp/coverage/coverage.json
uv run --no-sync python -m tools.testing.coverage_products validate --coverage-json tmp/coverage/coverage.json --gate-report tmp/coverage/product-coverage-report.json
```

## Evaluation and releases

Run real-store M01-M12, M14-M17, M19, M18-a, M18-b, M18-d and all M21, including mapping collisions, unknown frontier and later withdrawal/purge. M20 gets separate no-expiry and no-promotion assertions; its decay verdict stays UNRUN under M6. M13, M18-c and M22-M24 stay with #491. Fixture validation is not runtime proof.

Cross-session uses a fresh host and ACP session without conversation RAM and with the real store. Binding-switch preserves objective, scope, verification, mode and decisions; actual-model proof needs distinct resolved eligible identities under D6.

Pair on/off save, switch-on, forget, conflict and return with fixed tasks, route and rubric. Report retrieval, correctness, lifecycle, latency and fully loaded cost separately. Require zero authority, secret or isolation failures; no broad superiority/savings claim.

Revert checks must catch missing notices, citations or fsync, stale fences, wrong projects, premature purge/restore completion and bypass of the effective user-authority boundary.

Count every physical attempt, including extraction, retry and fallback. Bind config, prices and token forecast, gate the first prompt, and never transfer allowance.

| Session/release | Expected/max attempts | Maximum USD |
|---|---:|---:|
| Z0 and each named controlled-upstream Zed session | 0/0 | 0 |
| M3-ZED-OFF | 5/8 | 0.50 |
| M3-ZED-ON | 15/20 | 1.50 |
| M3-ZED-RETURN | 3/4 | 0.50 |
| M3-ZED-SWITCH, only qualified and released | 6/8 | 0.50 |
| M3-ROUTE-QUAL, only separately commissioned | 2/6 | 0.50 |

Zero-paid sessions use their own Gateway port, verified identity and no paid egress: plumbing, UI and Redis proof only, not extraction quality/cache hits. Unknown cost suspends qualification, not ordinary work.

## Checkpoints and Definition of Done

CP1: Task 1; CP2: Tasks 2-3; CP3: Task 4; CP4: Task 5.

AGENTS requires stronger owner-side review first, then consolidated read-only Codex review with explicit CLI model/effort. No per-task reviews.

Standing operator rule 2026-10-24: one final Windows full suite/coverage, then Linux PR CI. Skip only `optimus-pytest-coverage` on commits; other hooks and Ruff pass. Failures/later code invalidate acceptance; obtain disposition before repeating.

Codex acceptance is a review verdict only. Claude posts reviews verbatim and maintains the gitignored checkpoint log. Issue status, labels, owners and next gates remain in #490, not duplicated as a second work register.

CP2's conditional push/PR review release requires adopted D9, discriminating source-bound off-path verification, correctly identified effective expectations, intentional drift resolution, the one final-head broad run, Ruff and applicable hooks. It grants no merge authority and no final automatic-memory completion claim.

| Done claim | Named JSON evidence and real dependency |
|---|---|
| Scope, setup and admission | manifest, setup, credential-boundary, admission-k1, accounting: approved custody, effective authority policy, real Gateway/Redis and native backend where claimed. Distinguish interim off proof from final automatic admission. |
| Durability/recovery | durability, capacity-k2, erasure, recovery, copy-inventory: real AOF, RDB, filesystem and journal, crash/restore, aliases, Git, withdrawal cleanup and non-empty refusal. |
| Serving/continuity | citations, prompt-layout, continuity: current anchors, real Git, processes and store; actual route or D6 UNRUN custody. |
| Visible product/overhead | zed-ui, client-capabilities, extraction-overhead, paid-attempts: operator-typed real Zed, screenshots, ACP/debug logs, versions and paid receipts; named workload initial state and effective expectations. |
| Valid delivery | revert-checks, verification, qualification: discriminating negatives, valid Windows coverage, product floors and no safety regression, Ruff, inventories, platform proof and Linux CI SHA. |

Files are `.json` under `reports/plan12-memory-m3/`; apply AGENTS attribution, validity, archival and freshness. Default full excludes live markers. Tracked content is synthetic only; JSON digests use `hex:<lowercase-digest>`. No private dependencies.

Retain failures, skips, UNKNOWN, incomplete attempts and historical comparison misses. Bind each result to its own source, command, environment and retained records. Reports copied from bddcbcf remain bddcbcf evidence, not evidence for later D9 bytes. COMPLETE records do not establish every acceptance criterion.

Before closing and before merge, audit current-state claims throughout README, roadmap, transitional registry, linked issues and other affected documents, not only edited entries. Preserve named ownership of every deferred obligation.

Authorized closure removes the status label, closes this part, archives the plan unchanged and updates the docs index; #491 stays open. Do not close while final admission authority or another in-scope evidence obligation remains unresolved.

This draft was authored read-only. It grants no implementation, service, paid, publication or merge release.

Risk: plaintext same-drive recovery does not cover disk loss, declined consent, indirect shell reads or external synced copies.
