# ADR-042: Accepted memory lives in one fenced stream per project, on its own durable Redis, and is served only once on disk

**Status:** Proposed. The operator approved Plan 12.11, including its decisions D1 to D8, at its exact hash on 2026-11-16 (verbatim below).
Codex reviews the mechanism at the plan's first checkpoint; operator acceptance of this record is separate. Delivered under Plan 12.11
([#490](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/490)). Drafted by Claude.

**Relationship:** reuses the topology of [ADR-037](ADR-037-context-index-storage-setup-and-worker.md): a Gateway-owned route, a dedicated Redis set up
once in a terminal from a hash-only ACL, a launch approval, and the manifest and attach identity ([ADR-036](ADR-036-local-gateway-attach-identity.md))
binding its configuration. It departs from ADR-037 where accepted memory differs from an index: memory cannot be rebuilt from the workspace, so the
store must keep every acknowledged write and never adopt data it cannot vouch for. Unchanged: alerts, not limits
([ADR-005](ADR-005-cost-alerts-not-limits.md)); models are configuration ([ADR-025](ADR-025-models-are-configuration-per-model-admission.md)). This
record decides topology, the commit and the recovery boundary. Purge's journal (Task 2) and the recovery copy's format (Task 4) amend it when they land.

## Context

M3 makes memory a durable record: what the user said to remember, what they corrected, and where each session left off. The M1 index Redis runs with
`everysec` persistence and accepts losing about a second, because a worker rebuilds what was lost. Accepted memory has no such source. A lost save
is lost, and a save the user was told about but that never reached disk is worse.

## The operator's decision (2026-11-16, verbatim, Claude's Plan 12.11 chat)

"Approve hash", for Plan 12.11 at SHA-256 `77a7aec144b7b85ad379ff59bdb95912411b7753e6b3338628aa09e2f995824d`, whose D2 recommends "Use a separate
instance behind Gateway. Sharing index Redis needs capacity isolation it does not enforce. Memory cannot be rebuilt from files.", whose D5 recommends
"Add export and restore now for three extra days", and whose D8 recommends "Use one confirmed location per project and refuse healthy non-empty
restore targets."

## Options considered

| Decision | Option | Outcome | Reason |
|---|---|---|---|
| D2, instance | A separate Redis behind the Gateway | Chosen | Its memory ceiling, eviction policy and persistence are its own. The index can be rebuilt; memory cannot. |
| | The index's Redis, another key prefix | Rejected | One `maxmemory` for both: an index build could push memory to refusal, and the index's `everysec` loss window would apply to saves. |
| | SQLite or a file in the workspace | Rejected | A second storage stack, and a file in the workspace travels with copies and sync tools the user did not choose. |
| Agent-selected, commit | One stream per project, one append per change under a fenced lease | Chosen | `WATCH`/`MULTI` on the lease and the stream makes a lost lease or a moved head publish nothing, with one key changed, so there is no partial write to roll back. |
| | A hash per item, versions checked by script | Rejected | Needs `+eval`; ADR-037 kept scripting out of the ACL. |
| Agent-selected, confirmation | `WAITAOF 1 0` on the appending connection | Chosen | Says the append itself reached the local disk. The writer is one connection with retries off, and `CLIENT ID` before and after proves no reconnect came between. |
| | `appendfsync always` and trust the reply | Rejected | Proves the configuration, not this write. |
| Agent-selected, fsync policy | `appendfsync always`, with `WAITAOF` on the appending connection still the proof | Chosen (Codex CP1 review 1) | Every memory write is waited on anyway. Measured on the released store: 50 saves in a row confirmed at p50 8.7 ms, max 15.6 ms. |
| | `appendfsync everysec`, as Plan 12.11 proposed | Rejected after measurement | `WAITAOF` waited for the next periodic fsync: p50 1.003 s, max 1.006 s per save. With one serialized writer per Gateway that is about one save a second, so four simultaneous saves finish at about 1, 2, 3 and 4 seconds against a p95 target of 1.5 s. |
| | A pool of writer connections sharing one fsync | Rejected | More concurrency machinery than `always` for the same effect. |
| D5 and D8, recovery | A plaintext copy in the workspace, one confirmed location, restore only into an empty store | Chosen; lands with Task 4 | Volume loss would otherwise lose everything. |
| | No copy in this part | Rejected by the operator | Thirteen days instead of sixteen, and no recovery from volume loss. |

## Decision

The mechanism below is an agent recommendation that the operator approved through the plan; names and limits are agent-selected until Task 5's
qualification freezes them.

### Topology

`optimus-trust memory-setup --store` writes `memory-store/memory-store.json`, a hash-only `users.acl` and a generated password under keyring service
`optimus-gateway-memory-store`. It changes nothing about index setup. The launch approval binds the configuration's digest as
`_memory_store_config`; the signed manifest's `memory_store` field (schema offset 12) and the attach identity's `memory_store` field bind the store's
literal. An absent configuration changes none of them: no approval literal, the manifest's bytes as before, and the attach identity without the
field, so its digest is the one before Plan 12.11 (a test pins Plan 12.10's digest). A reply's `memory_store` field is optional, and a launch with
a store never attaches to a Gateway without one. The ACP host starts container `optimus-memory-store-redis` (volume `optimus-memory-store-data`,
loopback port 6394, the M1 image by digest) with AOF on and fsync on every write, `noeviction`, `maxmemory` 512 MiB and a 1024 MiB container cap.
It never adopts or replaces a container or listener with other settings.

The ACL opens only `omem:*` and named commands: no scripting, `KEYS`, `CONFIG`, `FLUSH*`, `DEBUG`, `ACL` or `SHUTDOWN`.

### The route

`POST /v1/context/memory` takes a closed set of operations: `capabilities`, `lease`, `append`, `read`, `list`, `checkpoint`, `checkpoints`, `purge`,
`purge_status`, `export`, `restore` and `restore_status`. The bearer is checked before any body byte is read. Limits: 256 KiB requests, 1 MiB replies,
a 5 second deadline that covers waiting and execution, two serving workers and a queue of eight;
a full queue is refused at once, and memory traffic never holds a model or capture request. No command, key or filesystem path crosses the route,
and a field outside the schema is refused. Every shape is fixed now; `purge` and `purge_status` answer `MEMORY_OPERATION_UNAVAILABLE` until Task 2's
journal backs them, and `export`, `restore` and `restore_status` until Task 4's recovery copy does.

**Projects are host-asserted, as ADR-037's scopes are.** A host holding the Gateway key can name another project; a test pins that residual. List
cursors are sealed with HMAC to their project and scope.

### Opening the store

Before it first serves, and again after any outage, the Gateway checks that AOF is on, eviction is `noeviction`, `WAITAOF` confirms a local fsync,
and the instance is the resource setup provisioned. It marks an empty instance as that resource. An unmarked instance that holds any key is refused
(`MEMORY_STORE_UNIDENTIFIED_DATA`) and never initialized, because nothing can vouch for what it holds.

### The commit

Each project has one authoritative stream. An event binds its item, version, event id, idempotency key, trust, status, kind, scope, anchors, lineage
and validity interval; the stream entry's id is its transaction time. The writer for a project holds a lease whose token is a global monotonic
fence: a new holder always gets a higher token, so the old one can no longer append.

An append runs on the writer's single connection: `WATCH` the lease and the stream, check the token, rebuild the item lookup up to the stream's head,
check the expected version and the idempotency key there (not in what is served), then `MULTI` with exactly one `XADD`. `WAITAOF 1 0` follows on that
connection. Only when it reports the local fsync, and `CLIENT ID` is unchanged, does the confirmed watermark move to the new entry. AOF is ordered, so
the watermark confirms every earlier entry too. A lost or replaced connection, during the wait or reported by redis-py as a `WatchError`, is not an
fsync failure: the request answers `MEMORY_UNAVAILABLE`, the Gateway drops every cached fold, and every operation, including one already queued, is
refused until the resource proves itself again, because Redis may have lost writes a cache still holds or another instance may now hold the port.
Whether a transaction already sent took effect is uncertain; a retry under the same key reconciles it.

The store has two single connections, one for writes and one for reads, each under its own lock. Each connection registers itself when it is
created, and every attempt to establish it, failed or not, is a new generation, including the silent reconnect redis-py's pool makes when it
finds a closed socket at checkout. Any new generation since the last verification makes the store suspect before the next command runs or result
is returned. Verification establishes both connections first and refuses a proof if either changes while it is collected, and checks both reach
the same resource. While a connection is in use, its connect timeout, its socket timeout and its parser's cached timeout are the request's
remaining budget, refreshed before each command; a watchdog closes its socket at the absolute deadline, and after the deadline the connection
neither connects nor sends, redis-py's own cleanup included, so no handshake, fragmented reply or
sequence of commands outlasts the request. Past the deadline nothing new starts; a write already sent stays uncertain, and the cut connection is
a new generation that must be verified.

A retry under the same key with the same content returns the first result and appends nothing; different content under that key is
`IDEMPOTENCY_CONFLICT`. A reply that never confirmed is `unconfirmed`, and admission stops until a fresh `WAITAOF` succeeds; withdrawals and off records
still go through. New saves are also refused at the 384 MiB admission ceiling, keeping the rest for deletion and control; a retry of a save already in the
stream is answered from it, not refused. A lease's fence is confirmed on disk before its token is handed out.

### Serving

`read`, `list` and `checkpoints` fold the stream only up to the confirmed watermark, so an unconfirmed event is never served. The folds are caches
rebuilt from the stream alone; a stream that went back discards them.

### Recovery (D5, D8)

A plaintext copy of active payloads goes under `.optimus/memory-recovery/`, excluded from Git, in one confirmed location per project, and a restore
refuses a healthy store that is not empty. Task 4 delivers it and amends this record with its format.

## Consequences

- Every write to the memory store is fsynced before Redis answers. Confirmed saves measured p50 8.7 ms, max 15.6 ms; a slow disk is bounded by the
  request's deadline, after which the save is reported as uncertain, never as confirmed. This departs from Plan 12.11's proposed `everysec`; `reports/plan12-memory-m3/targets.json` keeps its frozen thresholds and its
  description of the proposal, and Task 2's K2 measures contention and slow storage under `always`.
- One writer per project at a time. A second writer waits for the lease or is refused; nothing merges.
- Two workspaces on one key are not isolated from each other by the store.
- An `unconfirmed` reply is honest, not a failure to report: the host must not say "Remembered" for it.
- Losing the volume loses the store. Until Task 4's copy lands, there is no recovery from that.
- `users.acl` holds only the hash of a generated high-entropy password.

## Evidence

`tests/integration/memory/`, on the released dedicated Redis under its real ACL: setup, access control, persistence and restart after a kill, refusal of
foreign and unclaimed data, leases and fencing, versions, idempotent retries, the confirmed watermark, cursors and checkpoints.
`tests/integration/memory/test_native_keyring.py` on the real OS keyring under an isolated service name. `tests/unit/context/test_memory_store_setup.py`
runs a launch's real child arguments through the real Gateway entrypoint. Revert checks are recorded with CP1's review.
