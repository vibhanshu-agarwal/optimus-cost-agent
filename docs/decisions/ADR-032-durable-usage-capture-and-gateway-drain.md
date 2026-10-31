# ADR-032: Durable usage capture with a host outbox and a Gateway-owned Postgres drain

Status: Proposed. The operator accepted the credential boundary below on 2026-10-31 as part of approving Plan 12.8 at its exact hash; the mechanisms await Codex's Checkpoint A review. Delivered by Plan 12.8 ([#454](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/454)). Drafted by Claude.

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
- Acknowledgements are appended to an `ack.log`, never renamed into place, because Windows does not write a rename through. Only closed segments wholly inside a committed acknowledgement are deleted.

**Coverage epochs.**
- One epoch per turn, driven by `TurnSettlement`:
  - The turn's first worker invocation begins it, before any dispatch.
  - Each host request appends an intent before it is sent. The intent waits at most 250 ms; a later write never counts as pre-dispatch.
  - Accepted receipts are appended as accepted.
  - The close follows terminal finalization once no invocation is running.
- `host_complete` requires a confirmed begin, every intent confirmed, no refused record, and a complete settlement summary.
- Nothing infers a clean close. A late receipt is appended `late=True`, and the close is never rewritten.

**Gateway.**
- **Ledger owner.** The Gateway owns the Postgres connection and the drain transaction. Migrations live under `migrations/optimus_usage/`, in their own schema, digest-pinned.
- **Immutability.** The database itself refuses changes to append-only facts, through row and TRUNCATE triggers.
- **Commit.** One transaction verifies the batch against the committed prefix, inserts events, accepts receipts or records replay and conflict dispositions, updates coverage and advances the cursor. The acknowledgement names the ledger instance, stream, sequence and digest.
- **Gateway stream.** The Gateway keeps a minimal intent-and-outcome stream for physical attempts the host cannot see: legacy internal retries, lost responses, and host death mid-call. It is evidence, never a second receipt store or debit.

**Contract.** The neutral modules `optimus_security.durable_outbox` (mechanics) and `optimus_security.usage_capture_contract` (kinds, limits, request and acknowledgement shapes) serve both processes. The Gateway imports no `optimus.*` module.

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

## Decider and provenance

- **Credential boundary:** the operator, 2026-10-31, in Claude's Plan 12.8 chat. Asked "Approve plan hash 58d59e21…2619 (incl. ADR-032 boundary) and file the issue?", the operator answered "Approve and file". The plan's SHA-256 is `58d59e21b68e0973f78bd88452f2991536de4034b7ad9c74df01950889172619`.
- **Mechanisms and defaults:** agent-selected. Codex authored the plan (round 87); Claude implements; Codex reviews at the plan's checkpoints.
