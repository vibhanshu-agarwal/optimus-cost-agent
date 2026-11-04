# ADR-037: The context index lives behind a Gateway route, on a dedicated Redis set up once

**Status:** Proposed. The operator approved Plan 12.10, including its decisions D3 and D4, at its exact hash on 2026-11-03
(verbatim below). Codex reviews the mechanism at the plan's second checkpoint; operator acceptance of this record is separate.
Delivered under Plan 12.10 ([#469](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/469)). Drafted by Claude.

**Relationship:** adds one authenticated Gateway route beside those of ADR-032, ADR-034 and ADR-036, and keeps their boundary: the
host holds only its Gateway URL and key. It departs from design spec v4 §2, which placed the storage adapter with the engine; D3 moved
it to the Gateway. Unchanged: alerts, not limits ([ADR-005](ADR-005-cost-alerts-not-limits.md)); models are configuration
([ADR-025](ADR-025-models-are-configuration-per-model-admission.md)), so the embedding artifact is named only in its configuration
file. This record decides storage access, setup and the worker. Retrieval, assembly, tools and caching get their own record when
they land.

## Context

M1 needs a hybrid index of a large repository that survives restarts and never holds source bodies. The Plan 12.7 probes showed Redis
with Search can carry the load on one dedicated instance. They did not decide who holds that instance's credential, how it gets
provisioned without a startup prompt, or how a build stays coherent across edits, branches, crashes and outages.

## The operator's decision (2026-11-03, verbatim, Claude's Plan 12.10 chat)

"Approve this hash", for Plan 12.10 at SHA-256 `f136397fe605d51bd6dfee1ab4ed8705e7c3a45d05eb52b6c5cf569a7d02adb1`, whose D3 recommends a
Gateway-owned proxy "subject to latency/throughput qualification", and whose D4 recommends "Opt-in at CP3 and closure. Explicit
artifact/ACL administration; ACP host starts the dedicated container from hash-only ACL configuration. No new agent CLI target, startup
TTY or hidden download. Incomplete setup shows status and preserves today's context."

## Options considered

| Decision | Option | Outcome | Reason |
|---|---|---|---|
| D3, storage access | Gateway-owned proxy | Chosen, subject to the pilot | The host keeps its two credentials, the Gateway can bound and validate every operation, and a local process cannot read or alter the index without the Gateway's key. Costs one local HTTP hop per call; the pilot measures it. |
| | Direct unauthenticated loopback | Rejected | No proxy cost, but any local process could read or alter the index and bypass admission and scoping. Kept only as a pilot benchmark. |
| | Host holds an ACL credential | Rejected | Breaks the rule that the host holds only the Gateway URL and key. |
| D4, setup | One-time `optimus-trust memory-setup`, then a launch approval | Chosen | Download and credential creation happen once, in a terminal, with what will happen shown first. Ordinary launches need no prompt. |
| | Provisioning at agent start | Rejected | Would need a startup TTY or a hidden download. |
| Agent-selected | Numbered epochs in one line per branch | Chosen | A reader pins one epoch, so a publish is atomic and an edit needs no rebuild. |
| | A full generation per revision | Rejected | Every commit would rebuild, and most records are unchanged. |
| Agent-selected | `WATCH`/`MULTI` fencing | Chosen | Needs no scripting permission, so the ACL can leave `EVAL` out. |
| | Lua scripts | Rejected | Would need `+eval`, a much wider grant. |

## Decision

The mechanism below is an agent recommendation that the operator approved through the plan; names and limits are agent-selected until
the pilot freezes them.

### The route

`POST /v1/context/index` takes a closed set of operations: `batch`, `catalogue`, `cleanup`, `coverage`, `cursor`, `generation`, `lease` and
`query`. The bearer is checked before any body byte is read, and identity binding (ADR-036) applies before dispatch. Limits: 256 records, 1 MiB
either way, a 5 second deadline that covers execution as well as waiting, two serving workers and a queue of eight; a full queue is refused at once. Index traffic never holds a
model or capture request. No command, key or filesystem path crosses the route, and a record with any field outside the schema is refused.

### Scopes are host-asserted

The Gateway authenticates the shared key, not the workspace. The trusted host derives a scope from the registered project, worktree, branch and
the embedding, parser, policy and schema versions, and the model never selects one. **A host holding the key can assert another scope.** A test pins
that residual, which is why this is not a security boundary between workspaces on one key. A stronger one needs separate capabilities, which M1 does not
add. Cursors are sealed with HMAC to their scope, so a cursor cannot change scope.

### Coherence

A line holds records carrying the epoch that added them and the epoch that removed them. A reader sees what is live at one published epoch, or
the current one by default. A publish is one atomic step, so a half-written epoch is invisible. A file record is written last, so one that exists
proves its whole file arrived and a resume can skip it. The catalogue names paths with records but no file record, so what a crash left is deleted
when that file is next written, or removed if the file has gone, and no reader ever saw it. A record's retirement is written once, so an earlier view
stays as it was. A prune raises the oldest readable epoch to the published one as it starts removing, so a reader pinned earlier is refused with
`EPOCH_EXPIRED` and retries; it never gets part of a view. Epochs come from one counter and a new line's floor starts at its current value, so nothing from
before a drop can name the line that replaced it, and a read overtaken by a drop is refused rather than answered empty. A drop's first step takes the line out of
service in one transaction, so nothing reads a part of it, and an interrupted drop stays out of service until it is run again. A pass is called complete only if the
same files still hold the same bytes it read: size and time can stay the same when contents do not. That final check stops for a cancel and gives way to a turn. A folder
that cannot be listed also stops a pass being called complete: what is missing must not look like what was excluded. Files past Windows' path limit are reached through
the extended path form for their I/O alone; without that, the first real Java corpus lost a quarter of its files in silence. Revision and dirty state are published inside the line; a
changed ignore file is reconciled inside it.

Writers hold a lease whose fencing token every write checks under `WATCH`. A resuming owner takes a new token and retires its old one; another owner
is refused until the lease expires. One machine-wide cold-build slot stops two workspaces saturating the machine at once. A build holds it until a
complete publication, including across a resume, and a worker that loses it stops.

### What may persist (B1)

Identifiers, signatures with literals masked, deterministic structural descriptions, relative paths and hashes, documentation prose with code
blocks removed, vectors, and pointers. Source bodies, comments, docstrings and literals stay out. The text sent to the local embedder may contain
them; it stays in RAM. Vectors keep the inversion risk the design records. Documentation code keeps only its pointer, names and vector (Option A).
Whatever may be code counts as code: fences, indented and literal blocks, directives, doctests, inline spans and HTML blocks. Unusual layout loses prose
rather than keeping a body.

### Setup and lifecycle

`optimus-trust memory-setup` needs a terminal and shows what it will do first. It downloads the configured artifact at its pinned revision and
verifies its digest. It then writes a generated password to the Gateway's keyring namespace, `users.acl` with only the password's hash, and
`memory-index.json` with non-secret facts. Any failure configures nothing, and a rerun never replaces a working password.

The launch gate binds that file's digest, which covers the ACL file's and the artifact's, so a change needs a new approval. The signed Gateway manifest and
the attach identity bind it too. With no file, the feature is off and an existing approval, the manifest's bytes and today's context are unchanged.

The ACP host starts the dedicated container from that configuration, with `default` off and the index user limited to `oidx:*` and named commands.
It needs no secret and no running Gateway, so any launch can ensure it, and concurrent launches agree on the one named resource. It refuses an unexpected
container, volume or listener, including a lookalike with another memory limit, other server settings or no ACL mount, and never adopts or replaces one.
`--no-auto-start` only checks. Persistence is AOF `everysec` with periodic RDB, and
`noeviction`. A logical database or the shared Redis is not an alternative.

The Gateway resolves the password itself and proves authentication, Search, persistence, eviction and resource identity before it first serves, and again
after an outage. While Redis is down the route refuses with a stable code and model service continues.

### The worker

Open and named files go first, and the first indexed file is published at once, with coverage saying it is incomplete. A pass compares the source with the
building epoch, so a cancelled, killed or paused worker resumes by doing only what still differs. It uses one orchestration thread and at most two native
embedding threads, in bounded batches, and yields while a foreground turn is busy. Indexing makes no generative or provider call.

## Consequences

- Every index call pays one local HTTP hop. The pilot's measured cost is in `reports/plan12-memory-m1/pilot.json`; a failure there blocks D3's acceptance.
- Two workspaces on one key are not isolated from each other by the index. A hostile local process holding the Gateway key can assert any scope.
- An owning host's exit can stop a borrowed Gateway. Borrowers pause and show the index as unavailable; there is no takeover and no new port. Redis and its
  volume survive for a later compatible launch.
- `users.acl` is world-readable on POSIX so the container's user can read its bind mount. It holds only the hash of a generated high-entropy password.
- A branch's first build is a cold build; no vectors are shared between lines yet.
- Leases expire on the container's clock. Docker Desktop's VM clock was measured running slow and then jumping forward by a few seconds. The 60 second lease renewed
  every 15 seconds has 45 seconds of margin; a larger jump, as after a host sleep, loses the lease, and the worker stops and resumes on its next pass. Nothing is corrupted.
- Rebuildable data accepts losing up to about a second on a crash (`everysec`). A worker replays what was not confirmed and never labels missing data complete.

## Evidence

`tests/integration/context/`, on the released dedicated Redis under its real ACL: the route, lifecycle, conflicts, concurrent launches, outage and recovery, the worker on
real Git with a real process kill, and the B1 canary scan of keys, AOF and RDB after a restart and a rewrite. `tests/unit/context/test_memory_setup.py` runs a launch's real child
arguments through the real Gateway entrypoint with no password in either. `reports/plan12-memory-m1/` binds the pilot.
