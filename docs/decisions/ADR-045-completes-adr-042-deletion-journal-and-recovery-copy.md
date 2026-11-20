# ADR-045: Completes ADR-042 with purge's deletion journal and the recovery copy, as delivered

**Status:** Proposed. It records mechanisms that Plan 12.11 delivered at its CP2 and CP3
([#490](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/490)). Codex reviews it at CP4; operator acceptance is separate.
Drafted by Claude. **Publication:** editable in pre-merge review, frozen byte for byte on first merge to `main`.

**Relationship:**
- **Completes** [ADR-042](ADR-042-memory-store-topology-commit-and-recovery.md). ADR-042 said that purge's journal (Task 2) and the recovery
  copy's format (Task 4) would amend it when they landed. Both have landed. ADR-042 is frozen and unchanged, so the completion is this new record
  (`docs/decisions/README.md`, rule 5). Where ADR-042 says an operation answers `MEMORY_OPERATION_UNAVAILABLE` "until" Task 2 or Task 4, or
  that losing the volume has no recovery "until Task 4's copy lands", this record states what now holds.
- **Unchanged:** ADR-042's topology, commit, confirmation and serving rules, and the operator's D2, D5 and D8 (quoted in ADR-042).
  [ADR-044](ADR-044-explicit-user-actions-for-user-memory.md) decides who may purge or restore: only the user's explicit commands.

## Context

ADR-042 fixed every route shape at CP1, but left `purge` and `purge_status` unavailable until a deletion journal backed them. It also left
`export`, `restore` and `restore_status` unavailable until a recovery copy did. Plan 12.11's CP2 (PR #496) delivered the journal and CP3 (PR
#500) the copy. Both were reviewed by Codex at those checkpoints.

## Options considered

| | (a) A new record that completes ADR-042 | (b) Edit ADR-042 in place | (c) Leave it to the code and the plan |
|---|---|---|---|
| What it does | States the delivered mechanisms beside a frozen ADR-042 | Rewrites ADR-042's "until" lines and adds an amendments section | Nothing in the decision log |
| Fit | Follows the publication-freeze rule | Breaks the freeze: ADR-042 is merged, and plan v5's tooling pins merged records by hash | ADR-042 keeps saying operations are unavailable that now serve |
| Outcome | Chosen | Rejected (Codex CP4 review 21, ruling 1) | Rejected |

## Decision

The mechanisms below are agent-selected; the operator approved their purpose through Plan 12.11's D5 and D8.

**Purge's deletion journal (Task 2, CP2).** `purge` destroys one item's text. Each step is recorded before it is dispatched, in a payload-free
journal under `<memory-store root>/journal/`. The journal sits outside the Redis volume, so a later restore still learns what was purged. It
reuses the durable outbox's streams ([ADR-032](ADR-032-durable-usage-capture-and-gateway-drain.md)): one per Gateway process, fsynced,
hash-chained, with verified-prefix recovery. Each record also carries an HMAC under a key derived from the Gateway's generated ACL password. A
record the Gateway did not write is refused (`MEMORY_JOURNAL_INVALID`). A record names the project by its key hash, plus the item, version,
idempotency key, stream ids and persistence counters; never a title or a statement. The phases are `intent`, `tombstoned`, `physical` and
`completed`. `purge_status` reports where a purge stands and moves it on; an intent with no later step is uncertain, never assumed done. Code:
`src/optimus_gateway/memory_journal.py`.

**The recovery copy (Task 4, CP3).** One location per project, `.optimus/memory-recovery/` in the trusted worktree the user confirmed:
- it is recorded privately in the host's config, and linked worktrees share it;
- it is ignored by Git: the location gets its own `.gitignore` holding `*` if it has none;
- a location under a known sync root needs the user's consent first.

While a session is open, a changed project is exported periodically, and `/memory export` exports it at once. A generation uses the Agent Memory
Repo layout:
- `MEMORY.md`;
- `entries.jsonl`: every item's latest event as the Gateway signed it, active items whole and the rest payload-free;
- `manifest.json`.

The Gateway's seal binds the entries, the host's metadata and the count of deletion-journal records. A withdrawal or purge retires every older
generation.

`restore` sends one generation, the one whose seal the user was shown, and the Gateway:
- verifies every entry and the seal;
- refuses a project that holds anything;
- applies the deletion journal (failing closed when the journal is damaged or shorter than when the copy was written) and this host's later
  deletions;
- publishes in one fenced transaction.

A mapped restore (`/memory restore <generation> --map`) maps a copy into this workspace's own registration, one to one. A store emptied for a
project that held memory is reported as recovery-required: nothing is served and nothing is written until it is restored. Code:
`src/optimus/context/memory_recovery.py` and `src/optimus_gateway/memory_store.py`.

## Consequences

- The five operations ADR-042 held back (`purge`, `purge_status`, `export`, `restore`, `restore_status`) now serve.
- Losing the volume no longer loses everything: the copy restores what it last held. It is same-drive plaintext, not a backup. Statements in
  it are readable by anything that can read the worktree, including an authorized TEST or shell command.
- A damaged or shortened journal makes restore fail closed, rather than bring back an item the user purged.

## Evidence

The CP2 and CP3 records on #490. `tests/integration/memory/` on the released store. CP4's final-head qualification (`reports/plan12-memory-m3/qualification.json`) carries the recovery cases and `revert_gaps`, whose mutants include restore mapping.
