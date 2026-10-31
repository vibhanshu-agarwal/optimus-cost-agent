# ADR-032: Durable usage capture with a host outbox and a Gateway-owned Postgres drain

Status: Proposed. The operator accepted the credential boundary below on 2026-10-31 as part of approving Plan 12.8 at its exact hash; Codex accepted the mechanisms at Checkpoints A and B, and Checkpoint C (final K3 and release review) is pending. Delivered by Plan 12.8 ([#454](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/454)). Drafted by Claude.

## Context

Memory design v4 §7 requires complete, durable usage capture: an fsynced append-only outbox under the per-user config root, drained idempotently into an Optimus-owned Postgres ledger with committed cursors; durable coverage epochs; immutable receipts with linked reconciliation; and a bounded per-user Gateway diagnostic copy. It also requires extending the existing settlement path, with no second debit calculation, and that an outage never stops model work.

Two existing facts constrain where things live:
- **The credential rule.** `AGENTS.md`: "Local runtime credentials are limited to `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`." A Postgres DSN or password read by the ACP host would add a third.
- **The settlement path.** In production the host's only accounting is the per-session `TurnSettlement` (`optimus.usage.turn_settlement`). It is in memory. `UsageAccountingService` and the Redis settled-usage sink are not wired in production.

## Decision

**Credential boundary (operator-accepted, 2026-10-31).**
- The two-credential rule applies to the ACP host (the client runtime).
- The Postgres credential belongs to the Gateway service alone, as provider keys already do. The Gateway resolves it from its own OS-keyring namespace after verifying its authorized configuration. The host never reads, resolves, inherits or persists it, and no credential enters a workspace, command line, launch evidence, outbox or diagnostic.
- The host uploads capture records with its existing Gateway URL and key, to `POST /v1/observability/usage-capture`.

**Host outbox (agent-selected mechanism).**
- One owned writer thread per process, with bounded admission (1,024 queued records). Each writer lifetime starts a new stream directory under `<config_root>/accounting/outbox/host/`, locked for that lifetime.
- Records are checksummed, hash-chained JSON lines. A record is confirmed only after flush and fsync. Segments roll at 16 MiB.
- After a failed write, the segment is abandoned as it is. The next record opens a successor segment with a gap record naming the unconfirmed sequences, so a reader retracts bytes that landed without a confirmed fsync. Readers stop at any unexplained discontinuity.
- Only a stream's last record can have landed without a confirmed fsync. So, for an orphaned stream (its writer died), that record is withheld as an unverified tail unless it is the orderly `stream.end`.
- Acknowledgements are appended to an `ack.log`, never renamed into place, because Windows does not write a rename through. An acknowledgement must name a record the stream holds, with its digest. It also anchors a compacted stream's first record.
- Compaction deletes only closed, undamaged segments wholly inside the stored acknowledgement of the expected ledger instance. One record is at most 256 KiB, so it always fits in one upload batch.

**Coverage epochs.**
- One epoch per turn, driven by `TurnSettlement`:
  - The turn's first worker invocation begins it, before any dispatch.
  - Each host request's intent is recorded by the Gateway client just before it sends, from the identity the call site sets (`capturing`): the turn and the host request ID its receipts are numbered from. The intent waits at most 250 ms; a later write never counts as pre-dispatch. The ID travels in `X-Optimus-Capture-Request`, which the Gateway never forwards.
  - Accepted receipts are appended as accepted.
  - At terminal finalization with a worker still running, a terminal snapshot records the pending invocations, and the epoch stays open.
  - The close follows once every worker has settled. Ordered identity parts precede it, each with at most 256 IDs, and the close binds them by count and digest.
- `host_complete` requires a confirmed begin, every intent confirmed, no refused record, and a complete settlement summary.
- Model calls outside any turn (the JSON-RPC Gateway pass-through and the strict preflight probe) get one-call operation epochs of their own. `GatewayCompletionEvaluator` is constructed nowhere in production (the goal loop is retired), so it is reported unreachable rather than wired.
- Nothing infers a clean close. A close the queue refused leaves the epoch open. A queued close whose write failed reopens it. A receipt after a written close is appended `late=True`, and the close is never rewritten.
- Receipt fingerprints use a versioned canonical serialization that preserves the existing replay equality: equal decimals digest equally.

**Gateway.**
- **Ledger owner.** The Gateway owns the Postgres connection and the drain transaction. Migrations live under `migrations/optimus_usage/`, in their own schema, digest-pinned.
- **Immutability.** The database itself refuses changes to append-only facts, through row and TRUNCATE triggers.
- **Commit.** One transaction verifies the batch against the committed prefix, inserts events, accepts receipts or records replay and conflict dispositions, updates coverage and advances the cursor. The acknowledgement names the ledger instance, stream, sequence and digest.
- **Gateway stream.** The Gateway keeps a minimal intent-and-outcome stream for physical attempts the host cannot see: legacy internal retries, lost responses, and host death mid-call. It is evidence, never a second receipt store or debit.

**Configuration and launch binding.**
- The ledger's connection facts live in `<config_root>/accounting/gateway-accounting.json`: endpoint, database, role, connect timeout and the name of the password's entry in the Gateway's keyring namespace (`optimus-gateway-accounting`). Exactly that shape is accepted, so a password can never be read from it.
- The launch gate binds the file's exact bytes as the security literal `_accounting_config` (named like the other non-environment literals, such as `_model_registry`), so the operator approves it and any change needs re-approval. Without the file there is no literal, and existing approvals are unchanged.
- The signed Gateway manifest carries an optional accounting literal: the accounting root and the approved configuration literal. A manifest with it has its own version plus 3; manifests without it keep their versions and bytes. The parent passes the root only when the file still matches the approved literal.
- The Gateway composes the same literal itself and refuses to start unless the manifest binds exactly it. It opens the ledger lazily, with no connection at startup.
- Both processes drain their streams with one neutral drain (`optimus_security.outbox_drain`): the host over HTTP, the Gateway by committing directly. Without a ledger (no configuration, a refused one, or no credential), the Gateway's drain still measures its backlog and warns, and acknowledges nothing.

**Contract.** The neutral modules `optimus_security.durable_outbox` (mechanics) and `optimus_security.usage_capture_contract` serve both processes. The contract module pins each record kind's exact schema, the limits, and the request (including the sender's believed ledger instance) and acknowledgement shapes. The Gateway imports no `optimus.*` module.

## Options considered

1. **Host DSN or password.** Rejected: it adds the forbidden local client credential.
2. **Passwordless local Postgres.** Rejected: OS-authenticated connectivity was not established on every platform by Plan 12.7's P4.
3. **Share the evidence-handoff database.** Rejected: it would break ownership and isolation.
4. **Move receipt acceptance into the Gateway.** Rejected: the host owns accounting (ADR-031).
5. **Host outbox, Gateway-owned drain.** Chosen.

## Consequences and limits

- **Durability.** The outbox proves what the platform's fsync proves. On Windows a new file's directory entry is not separately flushed. No hardware power-loss guarantee is made.
- **Outages.** A Postgres outage leaves records accumulating locally. Pending bytes and the oldest pending age are visible, with warnings at 256 MiB or 24 hours. No cap deletes unacknowledged records. Disk exhaustion degrades capture visibly and never stops model work.
- **Prospective only.** History before M0b remains qualified. Surviving logs cannot prove billing completeness.
- **A dead writer's committed tail can stay local.** A writer may die after the ledger committed its last record but before it stored the acknowledgement. If that record was alone in its final batch, recovery has nothing to resend, so it stays on disk and is never compacted. The ledger holds it, so nothing is lost. It stays counted as pending, with its age warned, so the stream never reads as caught up. There is deliberately no probe on every orphan pass (Codex Checkpoint C ruling, #454).
- **Diagnostic copy.** Every Gateway of a user shares the per-user copy. Each line is written under the directory's lock file, so one sequence, the rollover, retention and the 256 MiB cap hold across processes. It is best effort and flushed, not fsynced.

## Decider and provenance

- **Credential boundary:** the operator, 2026-10-31, in Claude's Plan 12.8 chat. Asked "Approve plan hash 58d59e21…2619 (incl. ADR-032 boundary) and file the issue?", the operator answered "Approve and file". The plan's SHA-256 is `58d59e21b68e0973f78bd88452f2991536de4034b7ad9c74df01950889172619`.
- **Mechanisms and defaults:** agent-selected. Codex authored the plan (round 87); Claude implements; Codex reviews at the plan's checkpoints.
