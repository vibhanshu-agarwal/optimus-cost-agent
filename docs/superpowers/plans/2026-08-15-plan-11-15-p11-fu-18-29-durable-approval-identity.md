# P11-FU-18 and P11-FU-29 Durable-Approval Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace volatile/ambiguous workspace identity with a stable v3 Git-aware identity plus an immediate-root topology snapshot, while preserving valid durable approvals through transient probe uncertainty and safely promoting reachable v2 durable records.

**Architecture:** Resolve one coherent workspace security state containing a stable v3 identity, an ephemeral exclusion-policy-v1 topology snapshot, and an exact legacy-v2 migration address derived only from confirmed facts. Git discovery becomes `PRESENT` / `ABSENT` / `UNAVAILABLE`, uses one bounded probe with repository-redirection variables stripped, and never hashes uncertainty. Authorization uses the stable v3 digest; final revalidation compares stable identity and topology independently. Durable v2 promotion is HMAC-verified, snapshot-verified, locked, read-back verified, visible, and never applies to one-shots.

**Tech Stack:** Python 3.14, `dataclasses`, `enum`, `hashlib`, `os.scandir`/`lstat`, `subprocess`, OS keyring, cross-platform file locking, `pytest`, `coverage.py`, `pytest-cov`, Ruff, Windows, native WSL2 ext4 Git/`uv`, and Markdown evidence artifacts.

**Status:** Draft planning artifact. Implementation has not started. Plan 11.15 was verified unclaimed across `docs/superpowers/plans/`, local/remote branch names, and the consolidated pool on `origin/main` `414afc4587dffaf30d4853c24865e82cd15df3f1`. Plan 11.13 remains reserved for the authoritative four-document reversal; Plan 11.14 is already used.

## Frozen authority

The implementation contract is the immutable design:

- `docs/superpowers/specs/2026-08-15-p11-fu-18-29-durable-approval-workspace-identity-design.md`
- SHA-256: `B445693AFB9B110E61D860F1B63D8836FF0EA651E0AC327BABA1CC906C84543B`

Task 0 completes the currently missing pool registration. Never edit this spec in place. If implementation evidence proves it wrong, stop and author a forward-only `_v2` amendment for review.

## Global constraints

- Cut implementation from then-current `origin/main`; never implement from this planning branch, another feature branch, or `optimus-cost-agent-wt-vibhanshu`.
- Keep `P11-FU-18` and `P11-FU-29` distinct in the pool and evidence. They share Plan 11.15 because identity format, security-snapshot input, and durable-key migration must change atomically.
- Preserve the error taxonomy: initial missing/unstatable workspace is `WORKSPACE_NOT_FOUND`; only a confirmed stable/topology mismatch is `WORKSPACE_IDENTITY_CHANGED`; probe, scan, or policy uncertainty is `WORKSPACE_IDENTITY_UNAVAILABLE`.
- `WORKSPACE_IDENTITY_UNAVAILABLE` stops launch with exit `2`, preserves every approval record, performs no lookup under a fallback digest, and never becomes or prints `NO_APPROVAL`.
- Residual boundary: **Path/topology TOCTOU control, not workspace content integrity.**
- Exclusions are compiled application policy, independent of Git, `.gitignore`, Git config, environment, manifests, and operator input. Anything matching an exclusion is an accepted undetected drop location.
- Git `PRESENT` is one coherent successful result containing repository root and common directory. Never assemble it from two independent subprocess outcomes.
- Git and immediate-root transient operations use exactly three total attempts with injected 25 ms / 100 ms backoff. Unknown failures are permanent; no timestamp sleep/retry is permitted.
- Strip at least `GIT_DIR`, `GIT_WORK_TREE`, and `GIT_COMMON_DIR`, plus the related redirect variables named by the frozen spec's implementation review, from the subprocess environment. Do not strip ordinary executable lookup variables such as `PATH`.
- Do not weaken trust, HMAC, TTY, no-secret, single-environment-capture, audit-before-runtime, or no-side-effect-before-authorization controls.
- A v3 record always wins. A corrupt, incompatible, mismatched, or otherwise failed v3 record must never fall back to v2.
- Promotion inherits any compromise or false negative that predated migration. The current topology snapshot proves only current state; it does not upgrade the historical assurance of the v2 approval.
- Outstanding one-shot records are never migrated; they fail explicitly on version mismatch and must be reissued.
- Windows is mandatory. Linux-parity evidence must run from the native WSL ext4 clone described in `docs/runbooks/local-live-dependencies.md`, with `/usr/bin/git`, a clone-local `.venv`, and no `UV_PROJECT_ENVIRONMENT`. `/mnt/d` evidence is rejected.
- Platform-sensitive tests must carry explicit `sys.platform` guards and a reason. Do not hide cross-platform product behavior behind a skip.
- Use bare `--cov` so `pyproject.toml` supplies all configured production packages and the aggregate 80% gate.
- The plan file is the implementation contract. Any later revision is a forward-only `_v2`; never edit approved/frozen Plan 11.15 bytes in place.

## File map

### Modify during implementation

- `src/optimus/acp/trusted_paths.py` — tri-state Git result, retry classification, v3 digest, exact exclusion policy, topology snapshot, legacy-v2 address, typed diagnostics, and final comparison.
- `src/optimus/acp/launch_approvals.py` — schema/version dispatch, tamper-evident migration provenance, locked promotion/read-back verification, current/legacy lookup result, and revocation of known keys.
- `src/optimus/acp/launch_gate.py` — carry initial topology state, ordered durable lookup/promotion, one-shot version rejection, and authorization outcome metadata.
- `src/optimus/acp/__main__.py` — typed initial/revalidation remediation, preserve-approval behavior, audit disposition, and final stable/topology comparison before runtime effects.
- `src/optimus/acp/launch_approval_cli.py` — v3 approval authoring, inspect/revoke migration state, explicit reapproval text, and one-shot behavior.
- `src/optimus/acp/launch_audit.py` — value-safe workspace-identity and migration dispositions without creating/replacing an included root entry.
- `tests/unit/acp/test_trusted_paths.py` — exact policy, Git tri-state/retry/env, v3 digest, snapshot, FU-18, and residual tests.
- `tests/unit/acp/test_launch_approvals.py` — schema/HMAC compatibility, promotion ordering/locking/read-back/revocation, unreachable legacy, and one-shot non-migration.
- `tests/unit/acp/test_launch_gate.py` — ordered lookup, migration candidate snapshot equivalence, v3 precedence, and one-shot version failure.
- `tests/unit/acp/test_main_wiring.py` — no-side-effect ordering, preserve-approval on unavailable, error/remediation taxonomy, audit/revalidation order, and FU-29 end-to-end fault injection.
- `tests/unit/acp/test_launch_approval_cli.py` — approve/inspect/revoke output and migration visibility without secret or raw Git stderr leakage.
- `tests/unit/acp/test_launch_audit.py` — new value-safe dispositions and audit self-consistency.
- `tests/integration/acp/test_launch_trust_flow.py` — real seam from initial state through durable authorization, audit, revalidation, migration, and runtime release.
- `tests/unit/docs/test_open_work_pool_hygiene.py` — protect the frozen spec and keep the pool projection exact.
- `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` — Task 0 immutable registration/promotion custody; final distinct closure only after all evidence passes.

### Create during implementation, not in this plan PR

- `reports/plan-11-15-durable-approval-identity-baseline.md` — base SHA, frozen-spec digest, pre-change characterizations, platform provenance, and mutation boundary.
- `reports/plan-11-15-windows-durable-approval-identity-evidence.md` — deterministic red/green, focused/full/coverage/Ruff results, CLI subprocess evidence, and Windows filesystem/Git provenance.
- `reports/plan-11-15-wsl-durable-approval-identity-evidence.md` — exact implementation SHA, native ext4 proof, `/usr/bin/git`, focused/full/coverage/Ruff results, and POSIX semantics.
- `reports/plan-11-15-durable-approval-identity-release.md` — claim-to-evidence table, migration limitation, residuals, freshness audit, and distinct FU-18/FU-29 closure decision.

### Read-only authority and audit targets

- Frozen spec and the four authoritative documents/digests it pins.
- `docs/runbooks/local-live-dependencies.md:211-248` — native WSL clone gate.
- `pyproject.toml` — Python, pytest markers/addopts, Ruff, and bare coverage configuration.
- `README.md`, `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, and the Plan 11 charter — final current-state freshness audit; edit only if Plan 11.15 makes a claim stale.
- `docs/superpowers/reviews/plan-11-15-review-checkpoints.md` — reviewer-owned, gitignored handoff log; implementers read/verify it but never stage it.

---

### Task 0: Complete the frozen-spec registration and allocate live custody

**Files:**

- Modify: `tests/unit/docs/test_open_work_pool_hygiene.py:64-104`
- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md:47-76, 153-155, 472-493, 1198-1255`
- Read/hash only: frozen spec
- Create: `reports/plan-11-15-durable-approval-identity-baseline.md`

**Interfaces:**

- Consumes: `PROTECTED_BLOB_SHA256`, `_frozen_authority_rows()`, and the pool's exact-projection tests.
- Produces: the fourteenth protected artifact, exact owner links to both live FU entries, Plan 11.15 custody, and a baseline that records the unmodified design bytes.

- [ ] **Step 1: Cut a clean implementation branch from refreshed main and read the reviewer checkpoint.**

```powershell
git fetch origin main
git switch -c agent/cursor/plan-11-15-durable-approval-identity origin/main
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
Get-Content docs/superpowers/reviews/plan-11-15-review-checkpoints.md -ErrorAction SilentlyContinue
```

Expected: clean status and identical hashes. If the hashes differ, or the checkpoint contradicts the plan, stop.

- [ ] **Step 2: Verify the authority and baseline the current behavior.**

```powershell
Get-FileHash -Algorithm SHA256 docs/superpowers/specs/2026-08-15-p11-fu-18-29-durable-approval-workspace-identity-design.md
git hash-object docs/superpowers/specs/2026-08-15-p11-fu-18-29-durable-approval-workspace-identity-design.md
uv run --frozen pytest tests/unit/acp/test_trusted_paths.py tests/unit/acp/test_launch_approvals.py tests/unit/acp/test_launch_gate.py tests/unit/acp/test_main_wiring.py tests/unit/acp/test_launch_approval_cli.py tests/unit/acp/test_launch_audit.py tests/integration/acp/test_launch_trust_flow.py -q
```

The SHA-256 must equal the frozen value above. Record test counts, platform, Python, Git, and base SHA in the baseline report. A baseline failure is investigated and recorded before feature work; it is not silently inherited.

- [ ] **Step 3: Write the deterministic pool-registration red first.**

Add the frozen spec and exact digest to `PROTECTED_BLOB_SHA256`, then run:

```powershell
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py::test_immutable_documents_match_approved_head_blobs tests/unit/docs/test_open_work_pool_hygiene.py::test_immutable_pool_authority_rows_are_an_exact_projection -q
```

Expected: blob-hash test passes; exact projection fails because the pool still has 13 rows. If both pass, stop: the red does not exercise the missing registration.

- [ ] **Step 4: Register the fourteenth artifact and assign both entries without merging them.**

Change `These 13 artifacts` to `These 14 artifacts`; add one frozen-authority row with the exact digest and live owners linking both `P11-FU-18` and `P11-FU-29`. Change each index/detail entry from `Open` / future design to `Promoted -> Plan 11.15`, preserving its own mechanism and acceptance criteria. Do not mark either entry closed.

- [ ] **Step 5: Run green and commit only Task 0 custody.**

```powershell
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
git diff --check
git add tests/unit/docs/test_open_work_pool_hygiene.py docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md reports/plan-11-15-durable-approval-identity-baseline.md
git commit -m "docs: register Plan 11.15 identity design authority"
```

---

### Task 1: Introduce one coherent tri-state Git probe with bounded retry

**Files:**

- Modify: `tests/unit/acp/test_trusted_paths.py`
- Modify: `src/optimus/acp/trusted_paths.py:255-415`

**Interfaces:**

```python
class GitContextDisposition(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    UNAVAILABLE = "unavailable"

@dataclass(frozen=True)
class ProbeDiagnostic:
    phase: str
    probe: str
    attempt: int
    classification: Literal["transient", "permanent"]
    disposition: str
    exception_type: str | None
    errno: int | None
    winerror: int | None
    return_code: int | None
    duration_ms: int

@dataclass(frozen=True)
class GitContextResult:
    disposition: GitContextDisposition
    repository_root: str | None
    git_common_dir: str | None
    diagnostics: tuple[ProbeDiagnostic, ...]

def resolve_git_context(
    workspace: Path,
    *,
    environ: Mapping[str, str] | None = None,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    sleeper: Callable[[float], None] = time.sleep,
) -> GitContextResult: ...
```

`PRESENT` requires both canonical paths; `ABSENT` requires a completed non-following marker walk with no supported marker; `UNAVAILABLE` carries diagnostics and cannot feed a digest. The one Git command must emit both paths in a parseable, length-safe format; retain `shell=False`, argument-list invocation, bounded output expectations, and a timeout.

- [ ] **Step 1: Add RED tests for all three dispositions and the single-probe invariant.**

Cover ordinary `.git` directory, worktree `.git` file, no marker without a subprocess, missing Git, corrupt/invalid/empty/inconsistent output, marker-walk access error, and confirmation that two `PRESENT` paths come from one invocation. Assert no old `_git_repository_root` / `_git_common_dir` `None` path remains reachable.

- [ ] **Step 2: Add the exact retry RED matrix.**

Parameterize transient `winerror in {6, 50}`, POSIX `errno in {EINTR, EAGAIN, ETIMEDOUT}`, and `subprocess.TimeoutExpired`. Assert success on attempt 1/2/3 yields identical `PRESENT` facts; exhaustion yields `UNAVAILABLE/retry_exhausted` with attempts `[1, 2, 3]` and sleeper calls `[0.025, 0.100]`; a permanent error invokes once and never sleeps. Unknown `OSError` values are permanent.

- [ ] **Step 3: Add the redirect-environment RED.**

Seed `GIT_DIR`, `GIT_WORK_TREE`, and `GIT_COMMON_DIR` with hostile values, capture the exact `env` passed to the runner, and assert those keys are absent while an innocuous sentinel and `PATH` remain. Also cover case-insensitive key removal on Windows. The result must describe the supplied workspace, not the redirect target.

- [ ] **Step 4: Run the red gate before source changes.**

```powershell
uv run --frozen pytest tests/unit/acp/test_trusted_paths.py -q -k "git_context or retry_contract or git_redirect"
```

Expected: deterministic failures due to missing types/behavior. If the new tests pass, stop and correct the test boundary.

- [ ] **Step 5: Implement the minimum Git adapter and make the matrix green.**

Marker inspection uses non-following filesystem operations. Missing executable, access denial, corrupt/unsupported repository, invalid output, and non-transient return codes are permanent unavailable. Sanitize diagnostics: no raw Git stderr, environment values, or untrusted path content.

- [ ] **Step 6: Run focused regressions and commit.**

```powershell
uv run --frozen pytest tests/unit/acp/test_trusted_paths.py -q
uv run --frozen ruff check src/optimus/acp/trusted_paths.py tests/unit/acp/test_trusted_paths.py
git add src/optimus/acp/trusted_paths.py tests/unit/acp/test_trusted_paths.py
git commit -m "refactor: make workspace git context tri-state"
git push -u origin agent/cursor/plan-11-15-durable-approval-identity
```

---

### Task 2: Build v3 stable identity and the exact topology snapshot

**Files:**

- Modify: `tests/unit/acp/test_trusted_paths.py`
- Modify: `src/optimus/acp/trusted_paths.py`

**Interfaces:**

```python
WORKSPACE_IDENTITY_FORMAT_VERSION = 3
WORKSPACE_EXCLUSION_POLICY_VERSION = 1

@dataclass(frozen=True)
class WorkspaceIdentity:
    format_version: int
    lexical_path: str
    canonical_path: str
    device: int
    inode: int
    git_context: GitContextResult
    digest: str

@dataclass(frozen=True)
class WorkspaceChangeSnapshot:
    canonical_path: str
    device: int
    inode: int
    exclusion_policy_version: int
    immediate_root_digest: str
    diagnostics: tuple[ProbeDiagnostic, ...]

@dataclass(frozen=True)
class WorkspaceSecurityState:
    identity: WorkspaceIdentity
    change_snapshot: WorkspaceChangeSnapshot
    legacy_v2_digest: str

def resolve_workspace_security_state(
    workspace_root: Path,
    *,
    git_probe: Callable[..., GitContextResult] = resolve_git_context,
    scandir: Callable[..., ContextManager[Iterable[os.DirEntry[str]]]] = os.scandir,
    sleeper: Callable[[float], None] = time.sleep,
) -> WorkspaceSecurityState: ...

def revalidate_workspace_security_state(expected: WorkspaceSecurityState) -> None: ...
```

The wrapper makes the v3 identity, initial snapshot, and exact legacy-v2 migration address come from one successful resolution. `change_time_ns` exists only while reproducing the exact v2 digest; it is absent from `WorkspaceIdentity`, the v3 domain, and approval address.

- [ ] **Step 1: Add RED tests for v3 canonical encoding.**

Assert the domain is `workspace-identity-v3`, fields are length-delimited, `ABSENT` has an explicit sentinel, `PRESENT` binds both canonical Git paths, retry diagnostics do not affect digest, and unavailable produces no identity/digest. Prove same facts with different `st_ctime_ns` have the same v3 digest, while lexical/canonical path, object identity, or confirmed Git topology changes it. Retain an exact v2 golden-vector test so migration cannot drift.

- [ ] **Step 2: Add the exact exclusion-policy member-set RED.**

Assert equality—not subset membership—for these exact names:

```python
{
    ".pytest_cache", ".ruff_cache", ".coverage", "coverage.xml",
    ".venv", ".venv-wsl", ".venv_wsl", "build", "dist",
    ".uv-cache", ".uv-cache-plan118", "tmp",
}
```

Assert the exact anchored pattern identities for `.coverage.<non-empty-suffix>`, `.uv-cache-<non-empty-suffix>`, `hs_err_pid<digits>.log`, and `replay_pid<digits>.log`. Cover negative near-misses (`.coverage.`, `xhs_err_pid1.log`, `hs_err_pid.log`, nested paths, arbitrary `.log`, IDE/cache-like names), basename-only anchoring, Windows ordinal case-insensitivity, and POSIX byte-sensitive matching. An addition, removal, broad glob, version change, or workspace-controlled widening must fail loudly.

Also inject a missing/invalid compiled policy and assert permanent `WORKSPACE_IDENTITY_UNAVAILABLE` after one attempt, with no `.gitignore`, include-all, exclude-all, or cached-policy fallback.

- [ ] **Step 3: Add RED topology serialization and scan-failure tests.**

Cover deterministic sorting, exact name bytes, non-following kind, device/inode, symlink target bytes, add/remove/rename/replace/retarget, duplicate/unencodable representation rejection, and unchanged nested content under an existing immediate child. Run retryable root-stat, scan, and child-lstat errors through exactly the Task 1 three-attempt policy; permanent failures stop once; no failure becomes an empty digest.

- [ ] **Step 4: Add the original FU-18 RED without sleep.**

Capture `WorkspaceSecurityState`, create immediate child `added-after-authorization`, inject/confirm equal before/after root `st_ctime_ns`, and assert `WORKSPACE_IDENTITY_CHANGED` with reason `root_topology_mismatch`. Add separate residual tests showing `.coverage`, `hs_err_pid123.log`, and a file below existing `tmp` are intentionally not detected. The non-excluded reproduction is the closure test; excluded cases document the accepted weakness.

- [ ] **Step 5: Run deterministic red before implementation.**

```powershell
uv run --frozen pytest tests/unit/acp/test_trusted_paths.py -q -k "v3 or exclusion or topology or fu18 or legacy_v2"
```

If the FU-18 red passes before the topology implementation, stop: it is probably still depending on the nondeterministic ctime behavior.

- [ ] **Step 6: Implement the state and comparison contract.**

Map initial missing/unstatable path to `WORKSPACE_NOT_FOUND`. During revalidation, disappearance/replacement is confirmed `WORKSPACE_IDENTITY_CHANGED`; scan/Git/policy uncertainty is `WORKSPACE_IDENTITY_UNAVAILABLE`. Compare stable digest first (`stable_identity_mismatch`), then topology (`root_topology_mismatch`). Never persist the topology snapshot in an approval record.

- [ ] **Step 7: Run focused green, current call-site tests, and commit.**

```powershell
uv run --frozen pytest tests/unit/acp/test_trusted_paths.py tests/unit/acp/test_launch_approvals.py tests/unit/acp/test_launch_gate.py -q
uv run --frozen ruff check src/optimus/acp/trusted_paths.py tests/unit/acp/test_trusted_paths.py
git add src/optimus/acp/trusted_paths.py tests/unit/acp/test_trusted_paths.py tests/unit/acp/test_launch_approvals.py tests/unit/acp/test_launch_gate.py
git commit -m "feat: add stable v3 identity and root topology snapshot"
git push
```

Only fixture/signature adjustments needed to keep existing approval/gate tests compiling belong in this commit; migration behavior belongs to later tasks.

---

### Task 3: Wire unavailable-versus-changed semantics through authorization and final revalidation

**Files:**

- Modify: `tests/unit/acp/test_launch_gate.py`
- Modify: `tests/unit/acp/test_main_wiring.py`
- Modify: `tests/integration/acp/test_launch_trust_flow.py`
- Modify: `src/optimus/acp/launch_gate.py:76-121, 427-724`
- Modify: `src/optimus/acp/__main__.py:149-368`
- Modify: `src/optimus/acp/launch_approval_cli.py:291-479, 719-785`

**Interfaces:**

- `LaunchCandidate` carries the initial `WorkspaceSecurityState` (not only a digest).
- Candidate security-snapshot hashing continues to consume only `candidate.workspace_identity.digest`; the topology snapshot is an ephemeral comparison input.
- `_authorize_or_exit()` resolves state before constructing/consulting `KeyringApprovalStore`.
- Final revalidation consumes the exact initially authorized state after audit and before Redis/Gateway/agent/debug/preflight/child effects.

- [ ] **Step 1: Write the preserve-approval RED as a direct property test.**

Create a real fake-keyring durable entry, retain its serialized bytes, inject `WORKSPACE_IDENTITY_UNAVAILABLE` at final revalidation, invoke `main()`, and assert all together:

```python
assert exit_code == 2
assert keyring_backend.get_password(service, durable_key) == original_record_bytes
assert "WORKSPACE_IDENTITY_UNAVAILABLE" in captured.err
assert "NO_APPROVAL" not in captured.err
assert "no launch approval found" not in captured.err
assert "re-approve" not in captured.err
assert side_effects == []
```

Also inject initial unavailability and assert the store constructor/lookup is never called and no audit/debug/runtime file is created. This is the primary FU-29 regression; it must not be replaced by a mock-only assertion that `revoke_workspace()` was not called.

- [ ] **Step 2: Add the FU-29 transient Git fault RED.**

Start from an approved real Git workspace, inject one `OSError(winerror=6)` followed by success, and assert the stable digest equals the no-fault digest and authorization succeeds without reapproval. Inject three failures and assert unavailable, three attempts, durable bytes unchanged, no fallback lookup, no `NO_APPROVAL`, and no runtime effect. Record that rerunning the unrelated P11-FU-5 handle test is not FU-29 evidence.

- [ ] **Step 3: Add the typed remediation/error matrix RED.**

Pin initial missing/unstatable, confirmed stable mismatch, confirmed topology mismatch, exhausted transient unavailable, permanent unavailable, and genuine missing approval. Only confirmed mismatch/genuine missing approval may recommend reapproval; unavailable recommends retry or repair. All trusted-path outcomes remain process exit `2`, sanitized, and free of raw Git stderr/path payloads.

- [ ] **Step 4: Run red before wiring changes.**

```powershell
uv run --frozen pytest tests/unit/acp/test_main_wiring.py tests/integration/acp/test_launch_trust_flow.py -q -k "identity_unavailable or fu29 or topology_mismatch or remediation"
```

Expected: deterministic failures in state carriage/remediation/final comparison. If preserve-approval passes without exercising a real stored record and `main()`, strengthen the test before continuing.

- [ ] **Step 5: Implement the ordered flow and typed messages.**

Resolve identity then topology before store access; authorize; append audit; re-resolve identity and topology; fail on unavailable or mismatch; only equality releases runtime effects. Preserve the single `os.environ` capture: pass a sanitized copy only to Git subprocess construction and never reread ambient configuration downstream.

- [ ] **Step 6: Run focused green and commit.**

```powershell
uv run --frozen pytest tests/unit/acp/test_trusted_paths.py tests/unit/acp/test_launch_gate.py tests/unit/acp/test_main_wiring.py tests/unit/acp/test_launch_approval_cli.py tests/integration/acp/test_launch_trust_flow.py -q
uv run --frozen ruff check src/optimus/acp/trusted_paths.py src/optimus/acp/launch_gate.py src/optimus/acp/__main__.py src/optimus/acp/launch_approval_cli.py tests/unit/acp/test_main_wiring.py tests/integration/acp/test_launch_trust_flow.py
git add src/optimus/acp/trusted_paths.py src/optimus/acp/launch_gate.py src/optimus/acp/__main__.py src/optimus/acp/launch_approval_cli.py tests/unit/acp/test_launch_gate.py tests/unit/acp/test_main_wiring.py tests/unit/acp/test_launch_approval_cli.py tests/integration/acp/test_launch_trust_flow.py
git commit -m "fix: preserve approvals when workspace identity is unavailable"
git push
```

---

### Task 4: Version approval records and implement locked v2-to-v3 durable promotion

**Files:**

- Modify: `tests/unit/acp/test_launch_approvals.py`
- Modify: `src/optimus/acp/launch_approvals.py:30-410, 418-650`

**Interfaces:**

```python
APPROVAL_SCHEMA_VERSION = 2

@dataclass(frozen=True)
class ApprovalMigrationProvenance:
    disposition: Literal["legacy_v2_to_v3"]
    source_identity_format_version: Literal[2]
    source_workspace_digest: str
    inherited_trust: Literal["pre_migration_assurance_not_upgraded"]

@dataclass(frozen=True)
class ApprovalRecord:
    # existing approval/configuration fields remain
    schema_version: int
    identity_format_version: int
    workspace_digest: str
    migration_provenance: ApprovalMigrationProvenance | None

@dataclass(frozen=True)
class DurableApprovalLookup:
    record: ApprovalRecord | None
    state: Literal["current", "migrated", "legacy_reapproval_required"]

def KeyringApprovalStore.promote_legacy_durable(
    self,
    *,
    current_identity: WorkspaceIdentity,
    legacy_workspace_digest: str,
    expected_legacy_snapshot_digest: str,
    current_security_snapshot_digest: str,
) -> DurableApprovalLookup: ...
```

Replace the current deserialized placeholder `WorkspaceIdentity` shell with explicit record binding fields (`identity_format_version`, `workspace_digest`); a stored record must not masquerade as a live resolved identity. Schema v1 deserialization/HMAC uses the exact old field set and domain and yields identity format 2; schema v2 includes identity format version and optional migration provenance in canonical serialization and HMAC. New approval records are schema 2 / identity 3. Promotion preserves the operator-approved fields and approval identity, changes only versioned binding/current snapshot/provenance fields, then re-signs.

- [ ] **Step 1: Add schema/HMAC compatibility RED tests.**

Use committed golden raw v1 JSON/HMAC fixtures generated from the pre-change serializer—not a v2 serializer pretending to be legacy. Assert v1 verifies only with its original domain/fields, v2 verifies all new fields, and tampering with identity version, source digest, disposition, or inherited-trust marker fails integrity. Keep canonical JSON/no-secret/size-boundary tests.

- [ ] **Step 2: Add successful promotion RED.**

Write a valid durable v1 record under the exact legacy digest, leave v3 absent, and require: legacy HMAC/policy/mode/workspace digest/current-candidate legacy snapshot all match; v3 write occurs under the v3 workspace lock; read-back verification succeeds before return; lookup reports `migrated`; provenance names the authenticated legacy key; subsequent lookup uses v3 without rereading v2.

- [ ] **Step 3: Add refusal and precedence RED cases.**

Cover legacy HMAC failure, policy mismatch, non-durable mode, workspace digest mismatch, legacy snapshot mismatch, degraded-`None` legacy address mismatch, v3 write/read-back failure, lock contention, and a present corrupt/mismatched v3. All fail closed without authorizing or overwriting/deleting the source. Present v3 always wins and never falls back.

- [ ] **Step 4: Pin unreachable legacy and one-shot behavior.**

Because generic keyring enumeration is unavailable, no speculative search is permitted and a truly new workspace cannot be distinguished from one whose v2 record became unreachable. During the compatibility window, when neither v3 nor the exactly derived legacy key exists, return typed `legacy_reapproval_required` with wording that says no reachable current approval exists and an explicit approval ceremony is required; do not falsely claim that a legacy record was found. A later removal of the compatibility window requires a reviewed policy change. Existing one-shot schema-v1 records are never promoted and fail with an explicit version mismatch/reissue result; durable migration code must never read or write an `oneshot:` key.

- [ ] **Step 5: Pin concurrency and revocation.**

Two concurrent promoters must converge on one byte-identical verified v3 result. A divergent v3 created under lock fails closed. `revoke_workspace()` for a migrated record deletes the current v3 key and the exact authenticated source legacy key in provenance; a fresh v3 record has no speculative legacy deletion.

- [ ] **Step 6: Run deterministic red, then implement minimum migration.**

```powershell
uv run --frozen pytest tests/unit/acp/test_launch_approvals.py -q -k "schema_v2 or legacy or migration or promotion or one_shot_version or revoke_migrated"
```

If successful promotion passes before production code, stop and verify the test is reading an actual v1 key and requiring a v3 read-back.

- [ ] **Step 7: Run green and commit.**

```powershell
uv run --frozen pytest tests/unit/acp/test_launch_approvals.py -q
uv run --frozen ruff check src/optimus/acp/launch_approvals.py tests/unit/acp/test_launch_approvals.py
git add src/optimus/acp/launch_approvals.py tests/unit/acp/test_launch_approvals.py
git commit -m "feat: promote valid durable approvals to identity v3"
git push
```

---

### Task 5: Integrate ordered migration with the gate and CLI

**Files:**

- Modify: `tests/unit/acp/test_launch_gate.py`
- Modify: `tests/unit/acp/test_launch_approval_cli.py`
- Modify: `tests/integration/acp/test_launch_trust_flow.py`
- Modify: `src/optimus/acp/launch_gate.py:76-121, 622-724`
- Modify: `src/optimus/acp/launch_approval_cli.py:314-479, 687-785`

**Interfaces:**

- `authorize_launch()` calculates the exact legacy security-snapshot digest by reusing `candidate.security_literals`, `candidate.secret_fingerprints`, `candidate.registry_version`, and `candidate.workspace_state.legacy_v2_digest`; no second configuration read is allowed.
- `AuthorizedLaunch` carries `approval_record_state: Literal["current", "migrated"]` and authenticated migration provenance for later audit/display.
- Inspect reports `current`, `migrated from v2`, or `legacy approval requires explicit reapproval`; revoke uses authenticated provenance.

- [ ] **Step 1: Add the gate RED for lookup order and exact snapshot validation.**

Assert: v3 lookup first; exact v2 lookup only when v3 is absent; legacy snapshot recomputation reuses candidate inputs; valid legacy promotion authorizes only after v3 read-back; v3 failure never falls back; unreachable legacy returns explicit reapproval; and no unavailable state reaches either lookup.

- [ ] **Step 2: Add CLI RED tests for author/inspect/revoke and one-shot.**

New approval writes schema v2/identity v3. A read-only inspection path reports an exactly found v1 record as `legacy` without silently promoting it; after authorization promotion it reports `migrated from v2`, and a fresh v3 reports `current`. The migrated display includes the inherited-trust limitation, while the no-exact-key case gives explicit approval-required remediation without claiming that a legacy record was found. Revoke removes only authenticated known keys. One-shot approval remains new-schema only; an old outstanding one-shot produces version-mismatch/reissue text and is not migrated. No output exposes secrets or raw keyring values.

- [ ] **Step 3: Add integration RED for full promotion.**

Drive initial state -> candidate -> v1 durable lookup -> HMAC/policy/mode/old digest/legacy snapshot validation -> locked v3 write/read-back -> authorization -> audit -> equal revalidation -> runtime release. A mismatched old snapshot, unreachable key, or failed v3 verification must stop before runtime.

- [ ] **Step 4: Run red before integration changes.**

```powershell
uv run --frozen pytest tests/unit/acp/test_launch_gate.py tests/unit/acp/test_launch_approval_cli.py tests/integration/acp/test_launch_trust_flow.py -q -k "migration or legacy or identity_version or one_shot"
```

- [ ] **Step 5: Implement ordered lookup and safe operator surfaces.**

Do not duplicate snapshot-hash logic or reread `.env.gateway`, keyring credentials, or `os.environ`. Preserve TTY gates for approval/revocation. A migration is compatibility, not fresh assurance; display the limitation and fresh-ceremony alternative.

- [ ] **Step 6: Run green and commit.**

```powershell
uv run --frozen pytest tests/unit/acp/test_launch_approvals.py tests/unit/acp/test_launch_gate.py tests/unit/acp/test_launch_approval_cli.py tests/integration/acp/test_launch_trust_flow.py -q
uv run --frozen ruff check src/optimus/acp/launch_approvals.py src/optimus/acp/launch_gate.py src/optimus/acp/launch_approval_cli.py tests/unit/acp/test_launch_gate.py tests/unit/acp/test_launch_approval_cli.py tests/integration/acp/test_launch_trust_flow.py
git add src/optimus/acp/launch_approvals.py src/optimus/acp/launch_gate.py src/optimus/acp/launch_approval_cli.py tests/unit/acp/test_launch_approvals.py tests/unit/acp/test_launch_gate.py tests/unit/acp/test_launch_approval_cli.py tests/integration/acp/test_launch_trust_flow.py
git commit -m "feat: integrate durable approval identity migration"
git push
```

---

### Task 6: Make migration/revalidation auditable without self-triggering the topology control

**Files:**

- Modify: `tests/unit/acp/test_launch_audit.py`
- Modify: `tests/unit/acp/test_main_wiring.py`
- Modify: `tests/integration/acp/test_launch_trust_flow.py`
- Modify: `src/optimus/acp/launch_audit.py:39-144`
- Modify: `src/optimus/acp/__main__.py:268-368`

**Interfaces:**

```python
@dataclass(frozen=True)
class LaunchAuditEvent:
    # existing fields remain
    event_type: Literal["authorization", "approval_migration", "workspace_revalidation_failure"] = "authorization"
    workspace_identity_disposition: str = "equal"
    workspace_identity_attempts: tuple[dict[str, object], ...] = ()
    approval_migration_disposition: str = "none"
```

Only bounded structured values are serialized. A migrated authorization appends a distinct `approval_migration` event with value `legacy_v2_to_v3`, tied to authenticated `AuthorizedLaunch` provenance, before the ordinary authorization event. A failed final comparison appends a later `workspace_revalidation_failure` event. Revalidation values distinguish `stable_identity_mismatch`, `root_topology_mismatch`, `unavailable_retry_exhausted`, and permanent unavailable classes without raw errors or Git stderr.

- [ ] **Step 1: Write RED value-safety and migration-observability tests.**

Assert the migration event exposes `legacy_v2_to_v3` and the inherited-trust marker, fresh v3 emits no migration event, and a separate revalidation-failure event carries typed attempt summaries. Canary raw Git stderr, paths, environment values, and secrets must not appear.

- [ ] **Step 2: Write the audit self-consistency RED.**

Use the real workspace-local runtime root shape. Capture initial topology, authorize, append the real audit event, recapture, and assert equal immediate-root digest and object identities. Also assert the audit append neither creates nor replaces an included immediate-root entry. If setup requires the runtime-root immediate entry, bootstrap it before the initial snapshot exactly as the approval ceremony does.

- [ ] **Step 3: Pin failure ordering.**

Migration/authorization audit appends remain before final revalidation and runtime effects. After authorization, a revalidation failure appends its value-safe failure event without mutating/revoking approval. If that append itself fails, startup remains stopped and the stable audit failure is reported. Before authorization, identity failure creates no audit/debug file. Audit append failure still stops startup.

- [ ] **Step 4: Run red, implement, and run focused green.**

```powershell
uv run --frozen pytest tests/unit/acp/test_launch_audit.py tests/unit/acp/test_main_wiring.py tests/integration/acp/test_launch_trust_flow.py -q -k "migration or identity_disposition or self_consistency or unavailable"
uv run --frozen pytest tests/unit/acp/test_launch_audit.py tests/unit/acp/test_main_wiring.py tests/integration/acp/test_launch_trust_flow.py -q
uv run --frozen ruff check src/optimus/acp/launch_audit.py src/optimus/acp/__main__.py tests/unit/acp/test_launch_audit.py tests/unit/acp/test_main_wiring.py tests/integration/acp/test_launch_trust_flow.py
```

The first command must fail before source edits. If self-consistency passes only because `.optimus` was excluded, stop: the frozen exact exclusion set does not include it.

- [ ] **Step 5: Commit the auditable flow.**

```powershell
git add src/optimus/acp/launch_audit.py src/optimus/acp/__main__.py tests/unit/acp/test_launch_audit.py tests/unit/acp/test_main_wiring.py tests/integration/acp/test_launch_trust_flow.py
git commit -m "feat: audit workspace identity migration and revalidation"
git push
```

---

### Task 7: Collect mandatory Windows evidence

**Files:**

- Create: `reports/plan-11-15-windows-durable-approval-identity-evidence.md`
- Test/read: all Plan 11.15 source/test seams

**Interfaces:**

- Consumes: exact pushed implementation SHA, real Windows filesystem, real Windows Git worktree, and deterministic injected adapters.
- Produces: named evidence for both FU entries, retry classification, operator output, and full fitness gates.

- [ ] **Step 1: Prove checkout and platform provenance.**

```powershell
git status --short --branch
git rev-parse HEAD
git rev-parse origin/agent/cursor/plan-11-15-durable-approval-identity
where.exe git
uv run --frozen python -c "import platform,sys; print(sys.platform); print(platform.platform())"
```

Record exact SHA, Windows version/filesystem, Git executable/version, Python, and `uv` in the report. Hash the frozen spec again.

- [ ] **Step 2: Run the focused security matrix.**

```powershell
uv run --frozen pytest tests/unit/acp/test_trusted_paths.py tests/unit/acp/test_launch_approvals.py tests/unit/acp/test_launch_gate.py tests/unit/acp/test_main_wiring.py tests/unit/acp/test_launch_approval_cli.py tests/unit/acp/test_launch_audit.py tests/integration/acp/test_launch_trust_flow.py -q
```

Report named results for: exact exclusions; FU-18 non-excluded reproduction; FU-29 one/transient/exhausted injections; three-attempt/permanent retry; redirect stripping; preserve-approval/no-NO_APPROVAL; migration success/refusal/unreachable/one-shot; audit self-consistency.

- [ ] **Step 3: Run real CLI subprocess cases.**

In an isolated temporary ordinary workspace and Git worktree, use the installed branch CLI or `uv run --frozen` entry points to capture sanitized exit `2` for exhausted unavailable and confirmed changed cases. Assert unavailable gives retry/repair remediation without reapproval/`NO_APPROVAL`; confirmed topology change gives reapproval remediation; inspect shows migrated/current state without secrets. Do not use or modify the operator's real approval records.

- [ ] **Step 4: Run Windows full fitness.**

```powershell
uv run --frozen pytest -q
uv run --frozen pytest --cov -q
uv run --frozen ruff check .
git diff --check
```

Expected: full suite green, aggregate coverage at least 80%, Ruff clean, and no whitespace errors. Record exact counts/coverage/durations; skipped platform tiers are not passes.

---

### Task 8: Reproduce the contract in the native WSL ext4 clone

**Files:**

- Create: `reports/plan-11-15-wsl-durable-approval-identity-evidence.md`
- Read: `docs/runbooks/local-live-dependencies.md:211-248`

**Interfaces:**

- Consumes: the exact pushed Windows-tested SHA in a separate native clone.
- Produces: POSIX byte-sensitive exclusion, symlink, inode, Git, retry, FU-18, migration, full-suite, coverage, and Ruff evidence.

- [ ] **Step 1: Check out the exact SHA in native ext4.**

```bash
cd ~/src/optimus-cost-agent
git fetch origin agent/cursor/plan-11-15-durable-approval-identity
git switch --detach origin/agent/cursor/plan-11-15-durable-approval-identity
test "$(command -v git)" = /usr/bin/git
git rev-parse HEAD
git rev-parse origin/agent/cursor/plan-11-15-durable-approval-identity
case "$PWD" in /mnt/*) exit 1;; esac
test -z "${UV_PROJECT_ENVIRONMENT:-}"
stat -f -c '%T' .
uv sync --frozen --extra dev
test -x .venv/bin/python
```

Record distro/kernel, native path, filesystem type, `/usr/bin/git` version, Python/uv, and matching SHA. Any `/mnt/d`, Windows Git, shared Windows environment, or SHA mismatch blocks the run.

- [ ] **Step 2: Run focused POSIX/security evidence.**

```bash
uv run --frozen pytest tests/unit/acp/test_trusted_paths.py tests/unit/acp/test_launch_approvals.py tests/unit/acp/test_launch_gate.py tests/unit/acp/test_main_wiring.py tests/unit/acp/test_launch_approval_cli.py tests/unit/acp/test_launch_audit.py tests/integration/acp/test_launch_trust_flow.py -q
```

Explicitly record POSIX case sensitivity, symlink retargeting, `EINTR`/`EAGAIN`/`ETIMEDOUT`, Git worktree marker handling, non-excluded equal-ctime FU-18 reproduction, preserve-approval, and migration results. A skip must be justified by a platform-specific boundary and cannot discharge a cross-platform claim.

- [ ] **Step 3: Run native full fitness.**

```bash
uv run --frozen pytest -q
uv run --frozen pytest --cov -q
uv run --frozen ruff check .
git diff --check
```

Expected: full suite green, aggregate coverage at least 80%, Ruff clean, and diff hygiene clean. Record exact counts, coverage, and durations.

---

### Task 9: Audit current-state documentation, close both findings distinctly, and publish implementation evidence

**Files:**

- Create: `reports/plan-11-15-durable-approval-identity-release.md`
- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`
- Audit/update only if stale: `README.md`, `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, Plan 11 charter, `docs/runbooks/local-live-dependencies.md`
- Preserve: frozen spec and approved Plan 11.15 bytes

**Interfaces:**

- Consumes: Windows and WSL reports plus all Task 0-8 commits.
- Produces: two independently justified closure rows, a final evidence map, and a reviewable implementation PR.

- [ ] **Step 1: Run the documentation freshness audit.**

```powershell
rg -n "P11-FU-18|P11-FU-29|ctime|workspace identity|durable approval|WORKSPACE_IDENTITY_(CHANGED|UNAVAILABLE)|These 14 artifacts|Plan 11.15" README.md docs/superpowers/plans docs/runbooks reports
```

Read every current-state claim, not only the two pool entries. Update only newly stale statements. Historical frozen artifacts remain unchanged; deferred work keeps named custody.

- [ ] **Step 2: Write the release claim-to-evidence table.**

The report must map every frozen-spec DoD and every brief requirement to a named test and Windows/WSL artifact. Include exact implementation SHA; frozen digest; deterministic red/green observations; retry counts/backoffs; exclusion exact-set result and accepted blind spot; Git redirect stripping; preserve-approval bytes/no-`NO_APPROVAL`; FU-18 reproduction; FU-29 fault injection; migration/one-shot/revocation/CLI/audit results; full suites; bare coverage; Ruff; diff hygiene; and every unrun/unclaimed tier.

- [ ] **Step 3: Close FU-18 and FU-29 separately only if their own gates pass.**

`P11-FU-18` closure cites the non-excluded `added-after-authorization` equal-ctime reproduction, protected topology changes, and explicit excluded-drop-location/content-integrity residuals. `P11-FU-29` closure cites one/transient/exhausted Git fault injection, stable successful digest, preserve-approval/no-`NO_APPROVAL`, exact exclusion policy, and observable migration. Each index row links Plan 11.15 and the release report; neither closure may rely on the other's evidence or the unrelated P11-FU-5 rerun.

- [ ] **Step 4: Re-run final repository gates after documentation edits.**

```powershell
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
uv run --frozen pytest -q
uv run --frozen pytest --cov -q
uv run --frozen ruff check .
git diff --check
git status --short --branch
git diff --name-only origin/main...HEAD
Get-FileHash -Algorithm SHA256 docs/superpowers/specs/2026-08-15-p11-fu-18-29-durable-approval-workspace-identity-design.md
```

Expected: all green; coverage at least 80%; frozen digest unchanged; only planned source/tests/pool/current-state docs/reports changed; reviewer checkpoint remains untracked/ignored.

- [ ] **Step 5: Commit closure separately and open the implementation PR.**

```powershell
git add docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md reports/plan-11-15-windows-durable-approval-identity-evidence.md reports/plan-11-15-wsl-durable-approval-identity-evidence.md reports/plan-11-15-durable-approval-identity-release.md
git add README.md docs/superpowers/plans/2026-07-01-phase-1-roadmap.md docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md docs/runbooks/local-live-dependencies.md
git commit -m "docs: close durable approval identity findings"
git fetch origin main
git rev-list --left-right --count HEAD...origin/main
```

Stage the four audited current-state files only if they actually changed. Merge current `origin/main` before push if drift exists, rerun affected gates, push, and open a PR. Do not stage `docs/superpowers/reviews/plan-11-15-review-checkpoints.md`.

## Claim-to-task traceability

| Required claim | Primary task | Required evidence |
|---|---:|---|
| Frozen spec cannot drift silently | 0 | protected-blob hash + exact pool projection |
| Git `PRESENT` / `ABSENT` / `UNAVAILABLE`, one coherent probe | 1 | unit adapter matrix |
| Exactly three transient attempts; permanent stops once | 1, 7, 8 | injected Windows/POSIX results |
| Git redirect environment stripped | 1, 7 | exact runner environment assertion |
| v3 excludes ctime/diagnostics/unavailable | 2 | golden/cross-attempt digest tests |
| Exact compiled exclusion policy | 2 | equality test for names/patterns/version/case rules |
| Original FU-18 reproduction is caught | 2, 7, 8 | non-excluded equal-ctime test |
| Unavailable preserves approval and is never NO_APPROVAL | 3, 7, 8 | stored-byte main-path test + CLI stderr |
| FU-29 transient fault does not change identity | 3, 7 | WinError 6 success/exhaustion injection |
| Valid v2 durable approval promotes safely | 4, 5 | HMAC/snapshot/lock/read-back integration |
| Unreachable legacy requires explicit reapproval | 4, 5 | no-enumeration/refusal tests + CLI output |
| One-shot records are not migrated | 4, 5 | key-prefix/version tests |
| Migration visible in audit/CLI | 5, 6 | inspect/revoke and audit fields |
| Audit cannot trip topology control | 6 | real append/recapture self-consistency test |
| Windows and native Linux support | 7, 8 | named evidence reports at same SHA |
| FU-18/FU-29 close distinctly | 9 | separate pool rows and closure evidence |

## Explicit residuals and exclusions

| Residual/excluded capability | Disposition and owner |
|---|---|
| Same-object file-content mutation beneath an unchanged immediate-root entry | Out of this contract. **Path/topology TOCTOU control, not workspace content integrity.** Future content-integrity work requires its own roadmap entry before being claimed. |
| Any change matching the exact exclusion policy, including attacker-chosen excluded basenames/drop locations | Accepted security trade-off in the frozen spec; remains explicit in operator/security docs and tests. |
| Recursive workspace hashing, Git-index/worktree content integrity, or `.gitignore`-derived policy | Rejected by the frozen spec; do not add. |
| Recovery of unreachable v2 keyring records by enumeration/speculative search | Unsupported by the keyring boundary; explicit fresh approval is required. |
| Promotion of outstanding v1 one-shots | Excluded; reissue within the existing five-minute model. |
| Historical assurance before v2-to-v3 promotion | Not upgraded. Migration inherits pre-existing compromise/false negatives; fresh assurance requires revoke/new ceremony. |
| Bare repositories and environment-only repository selection | Explicit spec exception; ordinary worktrees/submodules only. |

## Definition of Done for implementation

- [ ] Task 0 protects the exact frozen spec bytes as the fourteenth immutable artifact and promotes both live entries to Plan 11.15 without merging them.
- [ ] Git discovery has exactly three typed outcomes, one coherent `PRESENT` probe, explicit transient allowlist, three total attempts, correct backoff, first-attempt permanent stop, sanitized diagnostics, and stripped repository redirects.
- [ ] Workspace identity v3 uses canonical length-delimited stable facts, excludes ctime/snapshot/diagnostics/unavailable, and retains an exact tested v2 address only for migration.
- [ ] Exclusion policy version 1 is compiled, Git-independent, exact-set tested, basename-anchored, Windows ordinal-insensitive, POSIX byte-sensitive, and cannot be widened by workspace data.
- [ ] The original non-excluded FU-18 equal-ctime reproduction fails closed as `WORKSPACE_IDENTITY_CHANGED/root_topology_mismatch`; excluded and same-object-content residuals remain explicit.
- [ ] Initial and final unavailable conditions exit `2`, stop effects, preserve durable bytes, perform no fallback lookup, and never raise/print `NO_APPROVAL` or reapproval remediation.
- [ ] Confirmed stable/topology mismatch remains distinct from unavailable and missing workspace, with stable sanitized remediation.
- [ ] Valid reachable v2 durable records are HMAC/policy/mode/digest/snapshot checked, promoted under lock, read-back verified, and thereafter lose to v3 precedence; failures never authorize/fallback.
- [ ] Unreachable legacy records require explicit reapproval; one-shots are not migrated; migrated revocation deletes only authenticated known keys.
- [ ] Migration is visible in CLI/audit and states the inherited-trust limitation; no secret, raw Git stderr, or untrusted content is persisted.
- [ ] Real audit append does not create/replace an included immediate-root entry or change the topology snapshot; audit and revalidation remain before runtime effects.
- [ ] Windows and native WSL ext4 focused/full suites pass at the same SHA; bare coverage is at least 80% on both; Ruff and `git diff --check` pass.
- [ ] Current-state documentation is audited; FU-18 and FU-29 close separately with named evidence; the exact residual statement remains: **Path/topology TOCTOU control, not workspace content integrity.**
- [ ] Reviewer checkpoint log is current, gitignored, and unstaged. Only after operator plan approval may implementation begin.
