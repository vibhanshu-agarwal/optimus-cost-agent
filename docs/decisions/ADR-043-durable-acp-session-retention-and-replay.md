# ADR-043: Durable ACP sessions keep sealed history only, replay it exactly and refuse interrupted state

**Status:** Accepted-with-open-items. The operator accepted the decision package D1–D13, including the mechanisms and
values below, by adopting Plan 11.7 v5 at its exact hash on 2026-11-14 (verbatim below). No further mechanism or
numeric approval is needed. The open items are the empirical prerequisites listed below, not approvals. Implementation
is released only for v5's evidence-machinery tasks E1–E2; no task that implements these mechanisms (P1–P6) is
released. Owner issue: [#240](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/240); retained feature
custody: [#230](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/230). Drafted by Claude from Codex's
local v5 draft. **Publication:** this file is an unpublished draft, editable in review until its first merge to
`main`, then frozen byte for byte; filing it needs publication authority, which is held.

**Number:** 043 is the next free number in the decision index at `main` `84fb87ca`, where ADR-042 is the memory store's
topology record. This record was first drafted locally as "ADR-042" against `main` `71d1c1ef`, where 042 was free. That
draft was never pushed or published, and main's ADR-042 took the number first, so this record moved to 043 without any
change to its decision, mechanisms or values. No number is reserved; recheck the index before publication. Codex's
earlier local draft was written as "ADR-039" against `main` `6e5478a0`; that number was never filed for this record.

**Relationship:**
- **Implements a decision anticipated by** [ADR-027](ADR-027-idle-client-mcp-lifetime-contract.md), which kept main's
  in-memory ACP continuity and left durable resume to #240. ADR-027's idle-MCP policy is unchanged: its idle delay
  and this record's retention TTL stay independent.
- **Unchanged and applied:** the context strategies and limits of [ADR-002](ADR-002-history-strategies-and-picker.md) and
  [ADR-003](ADR-003-context-ceiling-and-history-limits.md); the privacy and storage boundaries of
  [ADR-031](ADR-031-project-memory-and-evidence.md), [ADR-037](ADR-037-context-index-storage-setup-and-worker.md) and
  [ADR-038](ADR-038-context-index-retrieval-tools-and-caching.md) (the memory-index Redis is not the ACP session store);
  the memory store of [ADR-042](ADR-042-memory-store-topology-commit-and-recovery.md), which keeps accepted memory on
  its own Redis behind the Gateway and can store and serve continuation checkpoint records, is a separate service and
  is not the ACP session store either (automatic checkpoint capture and new-session continuation were later Plan 12.11
  work, delivered at its CP3, not established by this record);
  durable usage capture ([ADR-032](ADR-032-durable-usage-capture-and-gateway-drain.md)); alerts, not limits
  ([ADR-005](ADR-005-cost-alerts-not-limits.md)); the checkpoint cadence ([ADR-016](ADR-016-checkpoint-review-cadence.md)).
- **The plan is the contract.** The exact field lists, outcome map and task gates are in
  [Plan 11.7 v5](../superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation_v5.md). This record gives
  the rationale and the disclosed consequences; it is not a second execution amendment.

## The operator's words (verbatim)

- **2026-11-14, adoption.** "Approved. Adopt the reviewed v5 plan and have Claude implement E1–E2 only, with Codex
  reviewing. Don’t run live probes, publish records, commit, push or open a PR yet."
- **2026-11-16, this documentation.** "Approved. Have Claude refresh PR #476 against current main and complete the v5
  documentation updates, with Codex reviewing. Don’t commit, push, publish records, merge, run live probes, close #240 or
  clean up yet."

**Source.** Both are direct operator messages in the shared Codex coordination chat for #240: the adoption is the turn
that adopted v5, and the second is the turn that granted this refresh and documentation batch. Codex's adoption receipt
binds the first to plan SHA-256 `288bf4f896a559a6ca91a14bc1065806357883b5e09ebc4fca6856afe717c83c` and "D1–D13".
`2026-11-14T17:11:43.662160Z` is the receipt's recording time; the original message timestamp is not recorded. No
transcript export or excerpt is filed in the decision log's source list. That is a provenance limitation of this record,
not a condition on the accepted decision.

The v5 plan defines what adoption means: "A later explicit adoption may accept the whole package without repeated
numeric micro-approvals; implementation scope, live/paid/service/GUI release, publication, merge and cleanup remain
separate grants." The operator's adoption accepted the whole package; the operator chose none of its numbers individually, and none
needs a separate approval.

## Context

Main has no `session/load`. An ACP session lives in one process, and closing Zed loses it. The sandbox's durable
implementation predates main's mutable mode and context strategy, attached context limits, receipt settlement, memory
indexing and bounded session retirement, so importing it would lose facts main now owns. Plan 11.7 v3 described the
durable contract against an older main; the P0 assessment after v4 found the gaps that v5's D1–D13 resolve. The current
Zed client's empty-load reachability is still unmeasured: v5's Task 0 gate (E3–E4) must accept it before any production
task starts, and a positive empty-reopen signal stops the production port.

## Options considered

| Question | Options | Choice and trade-off |
|---|---|---|
| Data model (D2) | (a) import sandbox schema 1; (b) a new main-compatible schema | **(b)** schema version 2 under the existing `optimus:acp:session:{session_id}` family. More projection work; keeps mode, strategy, attached limits, approval facts, cost receipts and routing state that schema 1 cannot hold. Old keys are rejected, never reinterpreted or migrated |
| Interrupted work (D2) | (a) reload the last snapshot; (b) write a cancelled turn; (c) refuse unsealed state | **(c)** An old snapshot could hide an applied effect, and a synthesized cancel violates main's final-flush commit authority. Even a no-tool Chat turn closed mid-turn becomes non-resumable |
| Clean close mid-turn | (a) treat stdin EOF as a clean end; (b) keep the in-flight marker | **(b)**, the plan's "review option b". Completed, sealed turns restart cleanly; recovery of unsealed no-effect turns stays with #230 |
| Redis failure | (a) continue in RAM; (b) retry; (c) fail durability explicitly | **(c)** Refuse before dispatch; after divergence keep the authoritative result, stop new effects and show a best-effort notice. Availability is lower than today's in-memory prompting |
| Idle and retention (D3) | (a) tie the TTL to the MCP idle delay; (b) independent policies | **(b)** The idle owner releases MCP peers, not history. The sandbox parser's 1-second TTL minimum is not adopted |
| Transcript (D6) | (a) store every live callback; (b) rebuild from telemetry; (c) a closed classification | **(c)** Exact stored-and-replayed updates plus canonical history; meters, alerts, configuration, cards and status stay live-only and are republished from current state |
| Healthy uncommitted turn (D8) | (a) discard its UI stream; (b) retain it inert | **(b)** The exact user and terminal updates replay; canonical history is unchanged and sequence and cost advance. Discarding is rejected, not deferred |
| Empty-load reachability (D9) | (a) A-prime and prompted A/B only; (b) also each registered first-refusal class | **(b)** Six refusal wire classes with an empty stream; any positive empty-reopen signal is a non-waivable STOP. Fixtures characterize the client only |
| Cost completeness (D10) | (a) `finalize_turn` or a queued close; (b) written capture coverage at a watermark | **(b)** Known costs are kept; missing, late or gapped coverage stays incomplete. With capture disabled, resumed executed work stays incomplete |
| Size (D7) | (a) unbounded; (b) truncate; (c) a fixed cap with refusal | **(c)** 8,388,608 encoded bytes for the ledger and for staging. Never truncated or evicted |
| Evidence trust (D11) | (a) public self-consistency as proof; (b) trusted checkout inputs plus an accepting private receipt | **(b)** Public verification proves integrity, not that a hostile same-privilege host told the truth |

## Decision (D1–D13, as adopted with the plan)

- **D1** Rebase the evidence gate on a pinned current main; a source drift needs a reviewed applicability delta.
- **D2** Schema 2 with inert interruption markers; unknown versions refuse; no migration or interrupted-turn recovery.
- **D3** Sliding retention, Redis server time, a lease that must be reacquired when idle, refusal of an expired record.
- **D4** Absent-engine and attached-engine launches, mode and strategy changes, Auto, cost and opt-in memory indexing are
  all covered; runtime resources are rebuilt from current approved configuration, never serialized.
- **D5** The positive zero-entry reachability stop and every evidence tier stay; four checkpoints.
- **D6** The closed emission inventory; stage before send, finalize atomically after the authoritative outcome.
- **D7** The 8 MiB ledger and staging bounds.
- **D8** Retain healthy uncommitted UI replay.
- **D9** The six first-refusal classes in the current-Zed gate.
- **D10** Cost completeness by acknowledged capture coverage at a verified watermark.
- **D11** Trusted checkout scenario and run registry outside the bundle; hash-bound accepting private receipt.
- **D12** The evidence lane stays on main; shared #469 files are released by a reviewed integrated pin or exact owner
  clearance before P1.
- **D13** Control reserve, renewal cadence and mutation deadline; no Redis wait under lifecycle, settlement or writer
  locks.

**Values and who chose them.** Every new number is agent-selected (proposed by Codex in v5, reviewed by Claude) and
unmeasured. The operator adopted them as part of the package, not one by one.

| Value | Source |
|---|---|
| TTL default 86,400 s, range 300–2,592,000 s, lease 300 s (TTL ≥ lease) | Agent-selected (D3) |
| Ledger and staging bound 8,388,608 encoded bytes each | Agent-selected (D7) |
| Control reserve 8,192 bytes; renewal every 100 s; mutation deadline 5 s | Agent-selected (D13) |
| 64 sessions per process; absent-engine history 524,288 bytes; shipped attached source limit 1,048,576 and reservation 131,072 bytes | Existing main policy, unchanged |
| MCP idle delay (default 3,600 s) | Existing policy ([ADR-027](ADR-027-idle-client-mcp-lifetime-contract.md)), unchanged |

## Consequences and limits

- **Retention is time since the last refresh.** Ongoing activity can keep conversation text in Redis indefinitely. An
  idle record can expire while its process still runs; it then refuses continuation and is never recreated.
- **No user purge or delete API** is delivered, and TTL expiry is not immediate deletion (#230 keeps the feature).
- **Stored text.** Canonical sanitized user and agent text and the exact replay stream become Redis data. Sanitization
  does not remove every secret a person can type into ordinary text.
- **Lower availability.** A Redis outage or an uncertain marker can stop a prompt that works in RAM today.
- **Interruption.** Closing Zed before a turn is sealed blocks later resume, even for Chat with no tool. A lost
  acknowledgement is UNCERTAIN: it does not prove a rollback, and a later independent load checks the actual state.
- **A short busy window.** After a healthy uncommitted refusal is replied to, an immediate next prompt can receive the
  existing `REQUEST_CANCELLED` "a turn is already in progress" for up to the 5-second deadline.
- **Cost certainty.** With optional capture disabled, resumed executed work keeps its known subtotal but stays
  incomplete. This is a disclosed limit, not an integrity failure or a new mandatory setting.
- **No new guarantee** of power-loss durability, Redis persistence, replication, backup or a global key quota. The
  64-session cap is local; it does not bound all durable keys.
- **Compatibility refusals.** A changed client, source, attachment or route policy can refuse reuse until compatibility
  is reviewed or a fresh evidence gate passes. Historical acpx or Zed results cannot substitute.

## Unresolved empirical prerequisites

- The current-Zed gate (E3–E4) is unrun. A positive empty-reopen signal stops the production port and needs an
  operator-approved successor policy.
- The new agent-selected values (the TTL default and range, the lease, the 8 MiB bounds, the 8,192-byte reserve, the
  100-second renewal and the 5-second deadline) are unmeasured. P2 must qualify bytes, RSS, write amplification,
  latency, deadlines and declared Redis capacity and eviction policy before CP3; failure means re-estimation through a
  reviewed successor. The existing main policy values in the table are unchanged and not reclassified.
- Real Redis, Gateway, acpx, Zed and memory-on tiers are UNRUN. Fake-based tests cannot stand in for them.
- The #469 shared-file release (D12) and the owner reconciliation (E4) are not established.

## Authority boundaries

- **Decision:** accepted. The operator accepted the D1–D13 mechanisms and values by adopting the plan at its exact
  hash on 2026-11-14. Editing this unpublished record does not reopen them.
- **Implementation:** released for E1–E2 only. P1–P6 need their own release after both Task 0 acceptances.
- **Publication:** none. Filing this record, recording v5's adoption and v3's supersession in #240, the archive move,
  commit, push and any merge each need explicit operator authority. #240's adoption and supersession note is published
  before the change that delivers v5 and archives v3 merges.

## Decider and provenance

- **Decision:** the operator (adoption, 2026-11-14). **Mechanisms and values:** proposed by Codex, reviewed by Claude
  in three read-only rounds (Claude CLI, `claude-opus-5-5` high, session `ca980d75-01a6-4f93-acce-036701862ee9`); the last
  found the plan fit for adoption.
- **This record:** drafted by Claude on 2026-11-16 from Codex's local draft (SHA-256
  `f67c2489a1fbb021c526a466135029dd511cc440d59e4a06760249f02dabc4ad`). It reorganizes that draft, adds the operator's
  words, the value sources and the authority boundaries, and changes no mechanism. Codex reviewed it locally on
  2026-11-16 and again after the move to 043 on 2026-11-17. Its documentation findings were addressed, and Codex's
  final readback on 2026-11-17 closed them before the record was committed as part of `11d7f779` (draft PR #476).
  Changes made after that readback are reviewed separately. No review is operator approval of publication, commit or
  merge.
- Private planning artifacts are archival provenance only, never a dependency of this record.
