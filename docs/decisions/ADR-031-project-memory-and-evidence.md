# ADR-031: Project memory architecture, one includable-files policy and registered project identity

Status: Proposed. It awaits the operator's acceptance at Plan 12.6's checkpoint ([#390](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/390)). It records the architecture of the [Plan 12.x memory design v4](../superpowers/specs/2026-10-22-plan12-memory-design_v4.md), and the two foundations that [Plan 12.6](../superpowers/plans/2026-10-30-plan-12-6-memory-foundations-implementation_v4.md) builds. Drafted by Claude.

## Context

Plan 12.x memory gives Optimus project context, durable cross-session memory and grounded project answers, so that cheaper models can do comparable work. The operator's product decisions are frozen at discovery v12, operator-accepted on 2026-10-22 (decision source S10). The design v4 turns them into components, and Plan 12.6 is its first product slice. Two facts shaped it:
- **#385.** Automatic workspace context sent `.env` and other secret files to the model provider, because it never applied the secret-path rule that guarded model reads.
- **No shared policy.** Each future consumer of workspace files (automatic context, an index, anchor reads) would otherwise grow its own file rules.

## Decision

**Architecture (the design v4, §1–2; operator-decided items are marked).**
- **Engine boundary.** The engine is a separately extractable `context_engine` package ([ADR-001](ADR-001-context-engine-separate-product.md)). It imports no `optimus`, Gateway, security, evidence or model-policy implementation. The host injects authorized file reads, sanitization, model calls and opaque project identities. Engine absence keeps today's behaviour.
- **Host-owned authority.** The host owns authority: ACP commands, notices, security decisions, the project registry, key custody and accounting. Memory never grants execution authority.
- **Storage and retrieval (operator).** Automatic memory, with no review queue. Hybrid retrieval. GraphRAG for project questions. Redis first, with no SQLite. Postgres for analytical facts. Option A for documentation code.
- **Delivery order.** M0a (now M0a-1 to M0a-3), then M0b, M1, M3, M2, M5a, M7, M6 and M5b. Each slice has its own plan and acceptance.

**One includable-files policy (`optimus.guardrails.file_policy`, delivered by Plan 12.6 Task 1).**
- **One callable.** `FilePolicy.decide(relative_path, purpose=automatic|index|anchor)` serves every purpose. Automatic workspace context uses it now; the future index and anchor reads will too.
- **Order of checks.**
  - First, security denials, judged from path metadata before any content is read: skipped tool folders (case-insensitively on Windows and macOS); the `.optimus` runtime tree; secret files (`optimus.guardrails.secret_paths`, #385, including `.env.*`); an unresolvable target; a target outside the workspace. The same rules apply to the spelling and to the workspace-relative real target.
  - Then `.gitignore` and `.optimusignore`. An ignore file that exists but cannot be evaluated (an alias, which Git does not follow either; a denied target; not a regular file; unreadable; over 1 MiB) makes every decision it would judge unavailable (`deny.ignore_unavailable`), never more permissive.
  - Then empty and binary files, and files over a 1 MiB limit for indexing only.
- **Ignore semantics.** Ignore files use Git wildmatch syntax, through `pathspec`'s `GitIgnoreSpec`.
  - Nested files apply below their folder, and a deeper file overrides a shallower one.
  - `.optimusignore` is read after `.gitignore` in each folder. The last match wins, so `.optimusignore` can re-include what Git ignores.
  - Nothing under an excluded folder is re-included.
  - On Windows and macOS, a file is ignored if either the exact rules or the case-folded rules ignore it. Git's `core.ignorecase` varies by repository there, so this never makes more files eligible than either reading would; it can exclude a few more.
  - **No ignore rule can negate a denial.**
- **How content is read.** Only the validated real target is opened, and nothing is read until the opened handle is proven to be that file: the operating system's real path of the handle (`GetFinalPathNameByHandleW` on Windows, `/proc/self/fd` on Linux, `F_GETPATH` on macOS) must be the validated target, so a folder swapped after validation is caught, and the handle's file identity (device and file index) must equal the one stat'd. After the read, the alias must still resolve to the same target and the file must be unchanged (identity, size, modification time), or the bytes are discarded (`deny.identity_changed`). Where the OS cannot report a handle's path (for example a filesystem without final-path support, or an SMB share whose parent cannot be queried), nothing is read: the file is refused as `deny.unverifiable`, because identity checks alone cannot rule out a swapped folder. An ignore file that cannot be verified the same way makes the files it judges `deny.ignore_unavailable` instead. Automatic context omits both kinds, visibly in its exclusion counts. This replaces Plan 12.2's pathname-only rule, which kept such files readable where only pathname resolution failed.
- **Excluded folders stay closed.** Each folder is judged by its ancestors' ignore rules before its own ignore files are opened, so an excluded folder's ignore files are never read.
- **What a decision records.** A decision carries a rule id, never content. A policy revision binds it to the ignore files that judged it, by SHA-256. Automatic context reports its excluded files, including any refused at read time, as counts by rule, and keeps its 16 KiB pack budget. A required file refused at read time stops preparation with its reason.
- **Explicit permissions.** Explicit model READ permissions stay authoritative and unchanged. The model-read guard keeps its own rule set, which shares the secret rule. It does not import this broader policy.
- **Parser dependency.** `pathspec==1.1.1` (MPL-2.0, pure Python, unmodified) is now a direct dependency. It was already in the lock file as mypy's dependency.

**Registered project identity (Plan 12.6 Task 2).**
- **Grouping.** Each trusted canonical Git common directory gets one local UUID, so linked worktrees share it and clones and forks do not. A folder that is not a Git repository is registered by its canonical path.
- **Storage.** The registry is versioned JSON under the per-user config root. A cross-process lock, an fsynced temporary file and an atomic replacement protect it against concurrent writers and an interrupted process on every platform. Power-loss durability of the replacement is POSIX-only: the directory is fsynced there, and a Windows rename is not written through. A failure after the replacement is reported as uncertain (`WRITE_UNCERTAIN`), to be reconciled by reopening.
- **Failure handling.** A marker written before the first registration tells first use apart from loss: a missing registry with prior state is `RECOVERY_REQUIRED`, and a corrupt one is `CORRUPT`. Neither is silently reallocated; only an explicit `restore()` of an exported snapshot writes a lost registry back, and it never overwrites an existing one. Unavailable Git evidence is refused rather than registered by folder. Workspace trust approvals, file permissions and branch applicability stay separate from the project ID.

## Options considered

1. **A file policy per consumer.** Rejected: #385 is what drift between two copies of one rule looks like.
2. **Shell out to `git check-ignore`.** Rejected: it does not exist for folders outside Git, needs a Git install, starts a process per decision, and has no `.optimusignore`. A test instead compares the policy with native Git on a synthetic repository.
3. **A hand-written wildmatch parser.** Rejected: more code to keep exact than an established library.
4. **`pathspec` behind one host module.** Chosen.

## Consequences and limits

- **Behaviour changes in automatic context.**
  - Gitignored and `.optimusignore`d files are no longer packed.
  - A file alias whose target is outside the workspace is no longer packed.
  - A task that names an excluded file is refused with the rule that excluded it, for example "excluded by .optimusignore".
- **Deliberately conservative.** `.env.example` counts as a secret file.
- **Not covered.** Secret values inside ordinary files are not redacted, and hard links cannot be detected. If both the registry and its marker are deleted, the next registration starts afresh.
- **Pinned parser.** Parser differences from Git are guarded by the native-Git comparison test. Upgrading `pathspec` is a deliberate change that must keep that test green.

## Decider and provenance

- **Architecture:** operator decisions, frozen at discovery v12 (S10), as carried by the design v4.
- **#385 absorption:** the operator, 2026-10-30, in Claude's chat: "Please fix any issues blocking this plan. Absorb it into this plan please."
- **Plan v4:** approved by the operator on 2026-10-30 ("Approve v4").
- **Mechanisms:** designed and implemented by Claude. Codex reviews them at the plan's checkpoint.
- **Acceptance of this ADR:** pending the operator.
