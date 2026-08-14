# P11-FU-18 and P11-FU-29: Durable-Approval Workspace-Identity Security Design

**Status:** Draft for independent security review. This document approves neither an
implementation plan nor implementation.

**Concern ownership:** This is one design for two sibling concerns. `P11-FU-18` and
`P11-FU-29` remain separate backlog entries with separate acceptance criteria.

## 1. Purpose

Correct two opposite failure directions in the durable workspace-approval boundary without
turning the safety gate into a capability gate:

- `P11-FU-18` fails open when `st_ctime_ns` coalesces and a real immediate-root directory change
  is not seen by `revalidate_workspace_identity()`.
- `P11-FU-29` fails closed spuriously when a transient Git probe failure becomes `None`, changes
  the digest of an unchanged repository, and makes durable lookup return `NO_APPROVAL`.

The design separates stable workspace identity from short launch-window change detection. Git
context becomes an explicit tri-state result, transient probes receive a bounded retry contract,
and unavailable evidence never becomes digest input. A deterministic immediate-root topology
snapshot replaces `st_ctime_ns` as the revalidation signal, subject to a narrow, versioned,
application-owned exclusion policy for volatile development artifacts.

The central limitation is deliberate and normative:

> This is a path/topology TOCTOU control, not workspace content integrity.

## 2. Grounded source basis

This design was prepared from `origin/main` commit
`9c4e8ed3fc941efedf7917222309b2f8480cfbc7` and the following current sources:

- `src/optimus/acp/trusted_paths.py`;
- `src/optimus/acp/launch_approvals.py`;
- `src/optimus/acp/launch_gate.py`;
- `src/optimus/acp/__main__.py` and `src/optimus/acp/launch_approval_cli.py`;
- `tests/unit/acp/test_trusted_paths.py` and
  `tests/integration/acp/test_launch_trust_flow.py`;
- `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`;
- `reports/plan-11-flake-triage.md`;
- the prior workspace-identity design at
  `docs/superpowers/specs/2026-07-19-plan-9-98-fu-1-workspace-identity-ci-design.md`; and
- the current authoritative HLD v2.17, LLD v2.40, Guardrails v1.2, and Test Strategy v1.6 PDFs.

The authoritative documents require fail-closed trust handling, explicit approval, stable typed
failure behavior, real platform evidence where behavior differs, and fault-injected security
proof. They do not define a conflicting durable workspace-identity digest. This design preserves
their approval, no-secret, audit, and evidence-tier boundaries.

### 2.1 Verified production defect

`_git_repository_root()` and `_git_common_dir()` currently return `None` for all of these facts:

1. the workspace genuinely is not a Git repository;
2. Git is not installed or cannot be resolved;
3. `subprocess.run()` raises `OSError` or times out;
4. Git exits unsuccessfully; and
5. Git returns malformed or empty success output.

The first fact is stable and legitimate. The remaining facts are unavailable or invalid evidence.
Collapsing them into the same digest input is the concrete `P11-FU-29` defect.

The current digest also binds the workspace root's `st_ctime_ns`. The POSIX test creates
`added-after-authorization` directly under the root and expects revalidation to fail. WSL2 has
demonstrated that the two directory `ctime` observations can remain equal around that creation.
Digest equality then incorrectly authorizes the changed launch target. This is the concrete
`P11-FU-18` defect.

## 3. Scope and explicit exceptions

### 3.1 In scope

- Stable workspace identity and its digest inputs.
- Git-repository context discovery, retry classification, and diagnostics.
- Short launch-window immediate-root topology change detection.
- Durable approval lookup, compatibility migration, inspection, and revocation consequences.
- Typed operator-visible outcomes and structured diagnostic evidence.
- Windows, native Linux, and native WSL ext4 evidence obligations.
- Fault injection that proves both opposite failure directions.

### 3.2 Explicit exceptions

- Recursive workspace content hashing, Merkle trees, and source-code integrity.
- Detection of same-object file-content edits or changes beneath an already-present directory.
- Detection of a topology change that is completely reverted between the two observations.
- New workspace ACL, ownership, mount-integrity, or malware controls.
- Bare repositories, repositories selected only by inherited `GIT_DIR`/`GIT_WORK_TREE`, and other
  non-working-tree Git layouts. Supporting one requires a later explicit trust design; inherited
  Git environment cannot silently redirect identity discovery.
- General refactoring of the launch audit, retry, approval, or Git abstractions beyond the seams
  required by this contract.
- Implementation planning and implementation.

## 4. Security invariants

1. **Identity is stable:** a durable approval binds to the operator's lexical workspace path, its
   canonical target, filesystem object identity, and confirmed Git topology. It does not bind to a
   timestamp or a sampled content state.
2. **Change detection is launch-local:** a change snapshot covers the interval from current launch
   candidate resolution to the final pre-runtime-start revalidation. The existing append-only
   authorization audit may occur inside that interval; it is not persisted as the durable approval
   key.
3. **Unknown is not absent:** unavailable Git or filesystem evidence never enters a digest and
   never causes `NO_APPROVAL`.
4. **Uncertainty fails closed:** after bounded retry exhaustion, launch stops before Redis,
   Gateway, agent, debug-file, preflight, or child startup. The durable approval is neither deleted
   nor rewritten.
5. **Confirmed change is distinct from uncertainty:** `WORKSPACE_IDENTITY_CHANGED` means a
   comparison completed and differed. It must not mean that a probe failed.
6. **Volatility does not become authority:** neither `.gitignore`, Git's ignore engine, repository
   configuration, nor a workspace-controlled file may widen the snapshot exclusions.
7. **Excluded paths are an explicit weakness:** an entry matching the application-owned exclusion
   policy is an undetected drop location and is never described as protected by this control.
8. **No trust-control weakening for portability:** platform differences alter evidence and
   diagnostics, not the fail-closed decision.

## 5. Architecture

### 5.1 Separate data contracts

The later implementation introduces three conceptually separate values. Exact class placement is
an implementation-plan decision, but their contracts are fixed here.

#### Stable `WorkspaceIdentity`

The stable identity contains:

- normalized absolute lexical path;
- canonical resolved path;
- workspace-root `st_dev` and `st_ino` (or the existing Python platform equivalents);
- confirmed Git state: `ABSENT` or `PRESENT(repository_root, git_common_dir)`;
- identity format version; and
- `workspace-identity-v3` digest.

`st_ctime_ns` is removed from the stable identity and durable approval address. It may be retained
temporarily as a diagnostic/legacy-migration input, but it has no v3 security meaning.

#### Ephemeral `WorkspaceChangeSnapshot`

The change snapshot contains:

- canonical workspace root and its filesystem object identity;
- exclusion-policy version;
- a canonical digest of included immediate-root entries; and
- collection diagnostics needed to distinguish a comparison from an unavailable scan.

It exists only in the live launch candidate and is never serialized into a durable approval.

#### `GitContextResult`

Git discovery returns exactly one state:

- `PRESENT`: one successful probe produced both canonical repository root and common directory;
- `ABSENT`: filesystem discovery confirmed that the supported ordinary worktree marker is absent;
  or
- `UNAVAILABLE`: the workspace appears to require Git interpretation, but evidence could not be
  obtained or validated.

`UNAVAILABLE` carries diagnostics and is not hashable.

### 5.2 Git discovery without `None` conflation

Git discovery follows this sequence:

1. Walk from the canonical workspace root toward the filesystem root looking for an ordinary
   `.git` directory or worktree/submodule `.git` file. Each lookup is non-following and errors are
   classified rather than converted to absence.
2. If no marker exists, return `ABSENT` without spawning Git. This stable fact is represented by an
   explicit domain-separated sentinel in the v3 digest.
3. If a marker exists, resolve `git` from the trusted process execution environment and run one
   argument-list, `shell=False`, bounded subprocess that returns both repository root and common
   directory. The implementation must not produce a mixed pair from two independent probe
   outcomes.
4. Canonicalize and validate both returned paths. A success with empty, malformed, inaccessible,
   or inconsistent output is permanent `UNAVAILABLE`, not absence.
5. A missing executable, access denial, corrupt repository, unsupported repository form, or
   invalid output is a permanent unavailable condition and is not retried.
6. A recognized transient spawn/handle error, interrupt, or timeout uses the retry contract below.

The implementation must execute Git with inherited repository-redirection variables removed. A
workspace identity is derived from the supplied workspace path, not from untrusted `GIT_DIR`,
`GIT_WORK_TREE`, `GIT_COMMON_DIR`, or related inherited overrides.

#### Bounded retry contract

- Maximum: **three total attempts** (the initial attempt plus at most two retries).
- Only errors on an explicit allowlist of transient OS/subprocess conditions are retryable. The
  initial Git-spawn set is `winerror in {6, 50}`, POSIX `errno in {EINTR, EAGAIN, ETIMEDOUT}`, and
  `subprocess.TimeoutExpired`. Other values are permanent until a reviewed policy revision adds
  evidence for them.
- Permanent failures stop after the first attempt.
- Backoff is 25 ms before attempt two and 100 ms before attempt three, with an injectable sleeper
  for tests. No retry, delay, or sleep may be used to make a timestamp comparison pass; timestamps
  are not the new change signal.
- Success on attempt two or three returns the same `PRESENT` value and v3 digest that a first-attempt
  success would have returned.
- Exhaustion returns `UNAVAILABLE(retry_exhausted, attempts=3)`. It does not return `ABSENT`, `None`,
  an empty path, or a fallback digest.

The same maximum applies to retryable immediate-root enumeration/stat failures. It does not turn
unknown exceptions into transient ones.

### 5.3 Stable v3 identity digest

The v3 digest uses a new domain separator and canonical length-delimited encoding for:

1. identity format version;
2. normalized lexical path;
3. canonical path;
4. device and inode/object identity; and
5. either the explicit `git:absent` sentinel or both confirmed Git paths.

The digest excludes:

- `st_ctime_ns` and other timestamps;
- the change snapshot;
- retry counts, error strings, and diagnostics; and
- every `UNAVAILABLE` value, because no digest is emitted in that state.

Consequently, a retry that later succeeds cannot change the identity of an unchanged workspace.
Confirmed Git topology change still changes the stable digest and invalidates the binding.

### 5.4 Immediate-root topology snapshot

The snapshot enumerates only direct children of the canonical workspace root. For every included
entry it encodes, in a deterministic order:

- exact filesystem name bytes through the platform filesystem encoding;
- entry kind without following a child symlink;
- available filesystem object identity (`st_dev`, `st_ino` or platform equivalent); and
- for a symlink, its link target bytes.

The implementation must sort the canonical entry encodings before hashing and must reject duplicate
or unencodable representations. Adding, removing, renaming, replacing, or retargeting an included
immediate-root entry therefore changes the snapshot without relying on directory timestamp
granularity.

Enumeration or `lstat` failure is not treated as an empty entry set. Retryable failures use the
three-attempt contract; permanent failure or exhaustion produces `WORKSPACE_IDENTITY_UNAVAILABLE`.

### 5.5 Versioned application-owned exclusions

The exclusion policy is mandatory. Version 1 is a compiled, reviewable application policy; it is
not computed from `.gitignore`, Git configuration, a workspace manifest, environment variables, or
operator-supplied globbing.

The initial exact immediate-root exclusions are deliberately limited to the volatile artifacts
observed in the supported developer workflow:

- test/coverage/lint artifacts: `.pytest_cache`, `.ruff_cache`, `.coverage`, and `coverage.xml`;
- virtual/build caches: `.venv`, `.venv-wsl`, `.venv_wsl`, `build`, `dist`, `.uv-cache`, and
  `.uv-cache-plan118`; and
- local scratch root: `tmp`.

The initial narrowly anchored filename patterns are:

- `.coverage.<non-empty-suffix>`;
- `.uv-cache-<non-empty-suffix>`;
- `hs_err_pid<decimal-digits>.log`; and
- `replay_pid<decimal-digits>.log`.

There is deliberately no `*.log`, `.*`, cache-substring, virtual-environment-name family, IDE-name
family, or general Git-ignore rule. Pattern matching is over the immediate basename only and is
fully anchored. Windows matching uses ordinal case-insensitive comparison; POSIX matching is
byte-for-byte case-sensitive. An exclusion-policy change is a security-semantic change: it requires
security review, a version bump, fault-injected tests, and an explicit launch-policy compatibility
ruling. Workspace data cannot add an exclusion.

Because version 1 is compiled, exclusion computation has no Git dependency. If the policy cannot
be loaded or validated, that is a permanent `WORKSPACE_IDENTITY_UNAVAILABLE`; the implementation
must not fall back to `.gitignore`, include-all, exclude-all, or a stale cached policy.

#### Accepted exclusion weakness

Anything matching an exclusion can be created, removed, replaced, or retargeted during the launch
window without changing this snapshot. In particular, an attacker could place content under an
excluded directory or choose an excluded crash-dump-shaped basename. The exclusions are accepted
because these volatile paths otherwise make routine tests, lint, environment synchronization,
builds, IDE activity, and crash reporting spuriously reject legitimate workspaces. They must remain
narrow, code-owned, and visible in operator/security documentation.

This trade-off improves `P11-FU-29` by preventing predictable volatility from masquerading as an
identity change. It narrows `P11-FU-18` coverage for excluded entries, so the original reproduction
and every protected change class must be tested with a non-excluded name.

### 5.6 Resolution, authorization, and revalidation flow

1. Resolve stable v3 identity. If Git or filesystem evidence is unavailable after its applicable
   retry budget, stop with `WORKSPACE_IDENTITY_UNAVAILABLE`; do not consult approval storage.
2. Capture the initial topology snapshot using exclusion policy v1. If capture is unavailable,
   stop with the same typed outcome and retain diagnostics.
3. Resolve the launch candidate and perform durable or one-shot authorization against the stable
   identity.
4. At the existing final pre-runtime-start revalidation point, resolve stable identity and topology
   again. The append-only authorization audit is allowed before this point and must not create or
   replace an included immediate-root entry.
5. If either operation is unavailable, stop with `WORKSPACE_IDENTITY_UNAVAILABLE`, preserve the
   approval, and emit the diagnostic disposition.
6. If stable identity differs, stop with `WORKSPACE_IDENTITY_CHANGED` and reason
   `stable_identity_mismatch`.
7. If the included topology digest differs, stop with `WORKSPACE_IDENTITY_CHANGED` and reason
   `root_topology_mismatch`.
8. Only an available, equal comparison may proceed to Redis, Gateway, agent, debug-file, preflight,
   or child startup.

`WORKSPACE_NOT_FOUND` remains the initial-resolution contract for a missing or unstatable workspace
path. During revalidation, disappearance or confirmed replacement remains
`WORKSPACE_IDENTITY_CHANGED`; probe uncertainty is not remapped to changed.

## 6. Explicit `P11-FU-18` reproduction trace

The original test scenario remains protected and must be carried forward without a sleep:

1. Create an ordinary workspace root.
2. Resolve v3 identity and capture exclusion-policy-v1 topology.
3. Create the immediate child `added-after-authorization`.
4. Force or demonstrate that the root's before/after `st_ctime_ns` values are equal.
5. Revalidate.

`added-after-authorization` matches neither an exact exclusion nor an anchored exclusion pattern.
Its name and object identity therefore enter the second canonical entry set, the topology digest
differs, and revalidation returns `WORKSPACE_IDENTITY_CHANGED/root_topology_mismatch`.

If the injected name is instead `hs_err_pid123.log`, `.coverage`, or a child under `tmp`, the change
is intentionally not detected. That is the accepted excluded-drop-location weakness, not evidence
that the original non-excluded FU-18 scenario remains open.

## 7. Observable failure and diagnostic contract

### 7.1 Typed outcomes

| Condition | Outcome | Approval/store effect | Retry |
|---|---|---|---|
| Initial path missing/unstatable | `WORKSPACE_NOT_FOUND` | None | Only explicitly transient stat errors |
| Confirmed stable identity mismatch | `WORKSPACE_IDENTITY_CHANGED` | Preserve record | None |
| Confirmed included-root topology mismatch | `WORKSPACE_IDENTITY_CHANGED` | Preserve record | None |
| Transient probe succeeds within budget | Normal comparison | None | At most three total attempts |
| Transient probe exhausts budget | `WORKSPACE_IDENTITY_UNAVAILABLE` | Preserve record; no lookup under fallback key | Stop |
| Permanent Git/scan/policy failure | `WORKSPACE_IDENTITY_UNAVAILABLE` | Preserve record | No retry |
| Confirmed non-repository workspace | Stable `ABSENT` identity | Normal lookup | No Git subprocess |

The CLI/agent process keeps the existing trusted-path exit code `2`. Stderr names the stable error
code, phase, and remediation: retry for an exhausted transient condition; repair Git/repository or
filesystem access for a permanent unavailable condition; reapprove only for a confirmed identity
change or genuine missing approval. `UNAVAILABLE` must never print the `NO_APPROVAL` remediation.

### 7.2 Diagnostic evidence

Every attempt records a sanitized structured diagnostic containing:

- launch/session correlation when already available;
- phase (`initial_identity`, `initial_snapshot`, `revalidate_identity`, or
  `revalidate_snapshot`);
- probe name and attempt number;
- transient/permanent classification and final disposition;
- exception type plus numeric `errno`/`winerror` or child return code when present;
- bounded duration; and
- exclusion-policy and identity format versions.

Raw Git stderr and untrusted filesystem content are not persisted. Secret values are never logged.

Before authorization, the no-side-effect invariant permits only the sanitized structured stderr
diagnostic; it does not permit creating a debug/audit file merely because identity resolution
failed. After authorization, a revalidation failure additionally appends an audit disposition with
the same reason and attempt summary. The earlier approval decision does not suppress the final
revalidation failure record.

## 8. Durable approval migration

### 8.1 Versioned records and lookup

New records carry an explicit identity format version and use the v3 stable digest as their durable
key and security-snapshot input. The approval schema and HMAC serialization are versioned so the
identity version and any migration provenance are tamper-evident.

For a compatibility window, durable lookup is ordered:

1. look up and validate the v3 record;
2. only if absent, compute the exact legacy v2 digest from the same successfully resolved facts and
   current `st_ctime_ns`;
3. look up the legacy key without converting any unavailable probe to `None`;
4. verify the legacy record HMAC, policy compatibility, mode, legacy workspace digest, and legacy
   security snapshot against the current candidate; and
5. under the existing workspace lock, write and read-verify a v3 record with explicit migration
   provenance before using it for authorization.

Promotion is observable through CLI inspection and an append-only `legacy_v2_to_v3` migration audit
event. It is not silent invalidation and does not require a second approval ceremony when the exact
legacy approval remains valid for the current workspace/configuration. Once v3 exists it always
wins; no failed v3 check falls back to weaker v2 authorization.

If the current legacy digest no longer addresses the old record, the generic keyring API provides
no safe enumeration mechanism. That record remains unreachable, the operator receives an explicit
one-time reapproval requirement, and no speculative key search occurs. Inspection reports whether
a found record is legacy, migrated, or current. Revocation deletes the current v3 record and every
known legacy key recorded in its authenticated migration provenance.

A legacy record authored while either Git probe had degraded to `None` cannot match the exact
legacy digest derived from confirmed current Git facts. It is deliberately not promoted and
requires a fresh approval ceremony; migration must not recreate the old unavailable-as-absent bug
for compatibility.

Outstanding one-shot records are not migrated. Their existing maximum five-minute lifetime makes
an explicit version-mismatch failure and reissue safer and simpler than promotion.

### 8.2 Inherited-trust limitation

Migration validates an approval created under the weaker v2 digest. The new topology snapshot proves
only the current launch interval: it cannot prove that no tampering occurred before the v3 snapshot
was captured. Promotion therefore inherits any compromise or false negative that predated migration.
It upgrades record format and future behavior; it does **not** upgrade the historical assurance of
the operator's original approval.

The migration event and operator documentation must state this limitation. An operator who requires
fresh assurance revokes/replaces the legacy record through a new approval ceremony instead of
promoting it.

## 9. Effect on both failure directions

| Proposed change | Effect on `P11-FU-18` fail-open | Effect on `P11-FU-29` spurious fail-closed |
|---|---|---|
| Remove `st_ctime_ns` from stable identity | Timestamp equality no longer masquerades as proof of no change; protection moves to the explicit snapshot | Routine timestamp drift no longer changes durable address |
| Tri-state Git result | Confirmed Git topology changes still fail closed; unavailable evidence stops launch | Probe failure cannot become `None`, change a digest, or produce `NO_APPROVAL` |
| Three-attempt transient retry | Does not retry confirmed topology mismatch | A one-off `WinError 6` does not stop a legitimate workspace; exhaustion remains fail closed |
| Immediate-root canonical snapshot | Detects the original non-excluded add even when `ctime` coalesces | Deterministic comparison avoids timestamp/platform noise |
| Static exclusions | Creates an explicit undetected class for excluded names | Prevents normal test/lint/build/IDE/crash artifacts from becoming constant false changes |
| Separate unavailable error | Unknown state cannot be accepted as unchanged | Unknown state is not mislabeled as approval absence or confirmed change |
| Versioned migration | Future v3 launches use the stronger split contract; historical assurance is not overstated | Existing valid approvals are promoted rather than silently mass-invalidated |

No row improves one direction without its cost to the other being stated.

## 10. Platform position

### Windows

- `st_ctime_ns` is not a portable directory-change token and has no v3 security role.
- Real Windows evidence must cover ordinary worktrees, non-repositories, case normalization, and
  actual filesystem object identity behavior.
- Fault injection must use an `OSError` carrying `winerror == 6`, prove success after one and two
  failures, and prove typed unavailability after three total failures.
- PID-varying JVM crash files and the named volatile root artifacts must not cause topology mismatch.

### Native Linux

- The same topology serialization and exclusion policy apply; POSIX object identity and symlink
  semantics receive real filesystem tests.
- Equal/coalesced `ctime` is irrelevant to the decision and may be injected directly.

### WSL2

- Linux-parity evidence runs in the native WSL ext4 clone described by
  `docs/runbooks/local-live-dependencies.md`, not a Windows linked worktree under `/mnt/<drive>`.
- The original no-sleep creation scenario must pass repeatedly while asserting that its decision
  comes from topology difference, not an observed timestamp change.
- DrvFS observations may be retained as diagnostic evidence but cannot substitute for the native
  ext4 parity gate.

## 11. Evidence obligations for the later implementation plan

These behaviors are specified now and executed only by the later reviewed implementation plan.
Fakes and monkeypatch fault injection remain unit-tier evidence; platform and process claims require
the real dependency named by their tier.

### 11.1 Unit fault injection

Injection points and required assertions:

| Injection point | Scenario | Observable assertions |
|---|---|---|
| Git subprocess adapter | Attempt 1 raises `OSError(winerror=6)`, attempt 2 succeeds | Same `PRESENT` paths/digest as first-attempt success; two attempt diagnostics; no `NO_APPROVAL` |
| Git subprocess adapter | Attempts 1-2 raise `WinError 6`, attempt 3 succeeds | Same identity and successful durable lookup; exactly three attempts |
| Git subprocess adapter | Three `WinError 6` failures | `WORKSPACE_IDENTITY_UNAVAILABLE/retry_exhausted`; no digest fallback, store lookup, record deletion, or `NO_APPROVAL` |
| Git subprocess adapter | Permanent access/corruption/malformed-output failure | One attempt; typed unavailable with permanent classification |
| Git marker discovery | No marker in an ordinary workspace | `ABSENT` sentinel; Git subprocess not called; repeat digest stable |
| Git marker discovery | Marker lookup itself inaccessible | Typed unavailable, never absent |
| Root enumerator/stat adapter | Transient failure then success | Equal snapshot and normal launch; attempt evidence retained |
| Root enumerator/stat adapter | Permanent failure or three transient failures | Typed unavailable; no empty-set digest |
| Snapshot clock/stat seam | Before/after root `st_ctime_ns` forced equal, then add `added-after-authorization` | `WORKSPACE_IDENTITY_CHANGED/root_topology_mismatch` |
| Exclusion matcher | Add/remove `.coverage`, `.ruff_cache`, `.venv_wsl`, `hs_err_pid123.log`, and `replay_pid456.log` | Snapshot equality; policy version reported; no Git call |
| Exclusion matcher | Add `added-after-authorization` | Snapshot inequality and confirmed change |
| Exclusion matcher | Attempt workspace-defined ignore widening | Widening rejected/ignored; non-excluded add remains visible |
| Durable store migration seam | Valid legacy record | HMAC/policy/snapshot checked, v3 write read-verified under lock, migration event emitted, v3 wins thereafter |
| Durable store migration seam | Legacy HMAC/snapshot mismatch or v3 record failure | No promotion and no fallback authorization |

Characterization tests must also name the accepted residuals: a same-object content edit, a change
below an existing directory, an excluded-name change, and change/revert between observations are not
claimed as detected.

### 11.2 Integration and real-platform evidence

- The real launch chain must prove initial identity -> durable lookup -> authorization -> audit ->
  revalidation -> disposition, including preservation of the record on unavailable/change outcomes.
- Windows runs must exercise the real filesystem and real Git for unchanged, confirmed absent,
  repository-present, included-add, excluded-volatility, rename/replacement, and symlink/reparse
  cases supported by the platform.
- Native WSL ext4 runs must exercise the original FU-18 scenario without sleeps and independently
  show that equal `ctime` does not affect the topology verdict.
- CLI subprocess evidence must assert exit code `2`, stable sanitized error text, retry remediation
  for unavailable, reapproval remediation only where appropriate, and absence of `NO_APPROVAL` for
  probe exhaustion.
- The existing default unit suite, focused integration suite, aggregate production coverage at or
  above 80%, full-repository Ruff, `git diff --check`, and one-key release scan remain mandatory.
- A clean rerun of the unrelated Windows handle flake is not evidence for `P11-FU-29`.

## 12. Expected implementation responsibility map

This is a design map, not authorization to edit these files.

| Surface | Later responsibility |
|---|---|
| `src/optimus/acp/trusted_paths.py` | Tri-state Git context, retry classification, v3 identity, snapshot/exclusion policy, typed diagnostics, revalidation |
| `src/optimus/acp/launch_approvals.py` | Versioned serialization/HMAC, v3 addressing, legacy promotion and provenance |
| `src/optimus/acp/launch_gate.py` | Ordered v3/legacy authorization behavior and no weaker fallback after v3 failure |
| `src/optimus/acp/__main__.py` | Typed remediation and final revalidation audit disposition |
| `src/optimus/acp/launch_approval_cli.py` | Approve/inspect/revoke/migration observability and one-shot version behavior |
| `tests/unit/acp/test_trusted_paths.py` | Deterministic identity/snapshot/retry/exclusion fault injection |
| `tests/unit/acp/test_launch_approvals.py` and launch-gate/CLI tests | Migration, HMAC, lookup order, remediation, revocation |
| `tests/integration/acp/test_launch_trust_flow.py` | Real authorization-to-revalidation behavior |
| Platform evidence artifacts named by the later plan | Windows and native WSL ext4 proof |

## 13. Alternatives rejected

### 13.1 Retain v2 identity and merely supplement `ctime`

This avoids record migration but leaves a volatile change signal inside the durable approval address,
continues to conflate identity with sampled state, and keeps ordinary root changes capable of
invalidating approval before launch begins. It treats the architectural cause rather than only the
two observed symptoms as out of scope, so it is rejected.

### 13.2 Hash all Git-ignored versus non-ignored entries

This depends on the very Git probe that can be unavailable, allows repository-controlled ignore
rules to weaken a trust control, and converts every ignore pattern into implicit security policy.
It is circular and rejected.

### 13.3 Hash the recursive workspace tree

This detects a wider content class but is expensive, races active editors/builds, conflicts with
runtime/audit writes, and rejects legitimate everyday workspaces. It would make the launch safety
gate a broad content-integrity/capability gate and is rejected.

### 13.4 Use sleeps, timestamp retries, or test skips

These can make the existing test appear stable without making the security signal sound. They do
nothing for the `None` conflation and are rejected.

## 14. Distinct acceptance criteria

### `P11-FU-18`

1. `st_ctime_ns` is absent from v3 stable identity and is not a decisive revalidation signal.
2. The exact non-excluded `added-after-authorization` reproduction fails closed through topology
   mismatch even when before/after `ctime` is equal.
3. Included immediate-root add/remove/rename/replacement and symlink-retarget cases have named
   fault-injected and real-platform evidence.
4. The exclusion weakness and all other residual gaps remain explicit: path/topology TOCTOU control,
   not workspace content integrity.

### `P11-FU-29`

1. Confirmed absence, present Git topology, and unavailable evidence are distinct typed states.
2. A transient `WinError 6` receives no more than three total attempts; success preserves identity,
   while exhaustion stops with `WORKSPACE_IDENTITY_UNAVAILABLE`.
3. No unavailable path emits a fallback digest, queries a different durable key, deletes an
   approval, or reports `NO_APPROVAL`.
4. The application-owned exclusion policy prevents named routine volatile artifacts from producing
   spurious topology changes without relying on Git.
5. Migration behavior is observable, HMAC-verified, and documents its inherited-trust limitation;
   there is no silent mass invalidation.
6. Resolution is proved by fault injection. A clean unrelated Windows flake run does not count.

## 15. Review and next gate

The independent reviewer must rule specifically on:

- the static exclusion set and the accepted excluded-drop-location weakness;
- the three-total-attempt transient taxonomy;
- whether the ordinary-worktree-only Git marker contract is sufficiently explicit;
- the original FU-18 reproduction trace;
- migration's inherited-trust limitation; and
- the exact residual statement that this is a path/topology TOCTOU control, not workspace content
  integrity.

Only after this specification is approved may a separately numbered implementation plan be drafted,
reviewed, and approved. `P11-FU-18` and `P11-FU-29` remain open until their distinct implementation
and evidence criteria are satisfied.
