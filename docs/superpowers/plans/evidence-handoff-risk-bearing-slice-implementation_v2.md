# EVIDENCE-HANDOFF-FEAT-A2A-LEDGER Implementation Plan v2

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to execute this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. A checkbox may change only after its named verification
> command has passed and the reviewer checkpoint records the evidence.

**Goal:** Complete the risk-bearing ledger slice with Docker Desktop as the sole implemented,
explicitly selected local PostgreSQL backend and lifecycle-owned durable signing-key custody, while
preserving frozen v1 evidence and design artifacts.

**Architecture:** `backend_id` remains the explicit stopped-lifecycle selection point, backed by a
pluggable backend protocol/factory with Docker as its only concrete registration. This preserves the
seam for the deferred native-Windows adapter without hardwiring Docker or permitting runtime
failover. Signing-key bytes are minted/loaded only by lifecycle-owned OS-keyring custody and are
passed to the existing service start handshake; the service and `RuntimeInputSupplier` remain
keyring-free.

**Tech Stack:** Python 3.14, Docker Desktop CLI, PostgreSQL 16 Alpine, Windows OS keyring via
`keyring>=25,<26`, pytest/pytest-asyncio/coverage.py, Ruff, the official MCP client, and real
Windows process primitives.

## Status, authority, and frozen parents

This `_v2` file is the versioned successor to v1. It supersedes v1's implementation-scope
restriction that made wslc the sole shipped backend, supersedes **v1 Task 11 in full**, and folds
the separate signing-key amendment's execution contract. It does not edit, rename, or reinterpret
frozen artifacts.

| Artifact | Path | `git hash-object` pin | Treatment |
|---|---|---:|---|
| v1 implementation plan | `docs/superpowers/plans/evidence-handoff-risk-bearing-slice-implementation.md` | `905b4f2f9fd523cd5d9ea6e11ef4d3a0e59d8c21` | Immutable; do not edit or rename. |
| Frozen A2A ledger design | `docs/superpowers/specs/evidence-handoff-a2a-ledger-design.md` | `fa409ef5b36a2297dba281304468c206bcf33758` | Immutable; do not edit. |
| Folded, untracked custody amendment | `docs/superpowers/plans/2026-08-09-evidence-handoff-durable-signing-key-custody-amendment.md` | `c9b88c5bbf88eb695e475886041e9a0006529c72` | Superseded only after this v2 is independently approved; then delete it by explicit path. |

**Working-tree constraint:** Work only in
`D:\Projects\Development\Python\optimus-cost-agent-wt-cursor` on
`agent/cursor/evidence-handoff-a2a-ledger-risk-slice` at `2dce1a8`. Do not create a worktree or
branch and do not use `optimus-cost-agent-wt-codex`, whose branch is stale. Cursor is concurrently
working in `src/` and `tests/`; this plan author may touch only this file. Any later commit must use
explicit paths, never `git add .` or `git add -A`.

| Existing execution record | State retained by this v2 |
|---|---|
| v1 Tasks 1–9 | Committed and closed in `8735885` through `2dce1a8`; their wslc evidence remains valid historical evidence for work performed, but is superseded for the current product by v2 Task 3 Docker re-proof. Do not reopen their completed work. |
| v1 Task 10 Steps 1–2 | Approved but uncommitted in the shared tree. They are not a completion claim for v2 and must not be staged with v2. |
| Custody amendment Task 0 | PASS and independently verified: parent pins match; R9 baseline was 139 hits/11 files and is 168/12 after characterization; `test_auth.py` remains 36 hits. |
| Custody amendment Task 1 RED | Complete: `test_signing_key_custody_resolve.py` had 9 failed/1 passed because the module was absent; the live file was deselected; `test_signing_key_custody.py` passed 5. |

### Required non-blocking design refresh

The operator has removed wslc entirely. Frozen design lines 143–146 now name a primary backend that
will not exist, so a short non-frozen design successor is required. The pool owns
`EVIDENCE-HANDOFF-FEAT-A2A-LEDGER-DESIGN-REFRESH` for
`docs/superpowers/specs/evidence-handoff-a2a-ledger-design_v2.md`, which will restate the store
ladder as Docker then native Windows and record wslc's removal. That documentation work does not
block this plan: Docker stays loopback-only, MCP remains the access layer, and line 898's explicit
lifecycle selection/no-runtime-failover rule remains unchanged. Stop for a new design decision if
implementation instead needs a backend beyond Docker/native Windows, a changed loopback/security
boundary, or a change to line 265's service restriction.

## Global constraints

- Docker is the sole implemented local backend and the default `backend_id`; native Windows
  PostgreSQL remains deferred. Unknown backends fail content-free; no implicit running-process
  failover or backend switch is allowed.
- Every container publishes PostgreSQL only as `127.0.0.1:<port>:5432`. Use fixed `shell=False`
  argv and the supplied CLI surface: `run --detach --name --publish --volume --env-file`, `start`,
  `stop`, `inspect`, `volume create|inspect|remove`, `pull`, and `remove --force`.
- Store credentials belong only in the transient env file, never argv, status, `repr`, logs, test
  artifact content, or error messages. The lifecycle still owns administrator credentials.
- Design line 865 requires new Docker live evidence against Docker itself. Earlier wslc results are
  retained only as historical evidence and do not establish the current Docker-backed product.
- Preserve the service-only boundary at design line 265: lifecycle may query the OS keyring;
  `LedgerService`, `service_cli.py`, `RuntimeInputSupplier`, and MCP handlers must not.
- Durable custody uses Option A only: a DPAPI-backed OS-keyring entry per service installation, not
  per `ledger_instance_id`. Option B (ACL file) is rejected because its non-owner proof requires a
  second Windows account.
- Mint only when both `control/ledger_instance.json` is absent and the store has no instance row.
  Missing, unreadable, or corrupt custody after either record exists is a typed, fail-closed start;
  deletion of a keyring entry never reopens mint.
- Preserve the ephemeral auth-bundle delete-after-read behavior for `store_conninfo`. Durable
  custody changes signing-key sourcing only; it must not persist key material in the control root,
  runtime/bootstrap manifests, logs, ledger rows, audit output, or MCP responses.
- R9 is a stop gate: `CredentialIssuer.issue()` and `CredentialValidator.validate()` signatures are
  unchanged; decoded claims have identical keys and values except random `token_id`; `token_id` is
  present and well-formed; `eh1.` framing and HMAC-SHA256 construction are unchanged. Do not
  monkeypatch `secrets.token_urlsafe` to fake byte identity.
- R10 is fixed: chain-break recovery creates a new instance under the same installation key;
  pre-recovery tokens still fail existing instance-binding checks. Rotation, `kid`, JWKS, OAuth, and
  dynamic client registration remain deferred under `EVIDENCE-HANDOFF-FEAT-CREDENTIAL-LIFECYCLE`.
- `requires_os_keyring_write` is the only marker for tests that create, overwrite, or delete this
  feature's isolated keyring entry. Do not overload read-only `requires_os_keyring`.
- The reviewer-owned ignored checkpoint remains
  `docs/superpowers/reviews/evidence-handoff-a2a-ledger-review-checkpoints.md`; read and update it,
  but never stage it. Use an independently authored ACP client for ACP-protocol evidence.

## File and boundary map

| Area | Files | Responsibility |
|---|---|---|
| Backend selection | `src/evidence_handoff_runtime/backends.py`, `config.py`, `lifecycle.py`, `lifecycle_cli.py` | Extensible backend protocol/factory with Docker as the only registration, explicit stopped-lifecycle selection, loopback-only commands, and status. |
| Docker proof | `tests/unit/evidence_handoff/test_lifecycle.py`, `test_lifecycle_cli.py`, `tests/integration/evidence_handoff/test_docker_lifecycle.py`, existing real service fixtures | Unit argv/selection regressions and real Docker PostgreSQL/service evidence. |
| Marker contract | `pyproject.toml`, naming-boundary tests | Backend-neutral marker descriptions that still require the test to identify its real selected backend. |
| Signing-key custody | `src/evidence_handoff_runtime/signing_key_custody.py`, `lifecycle.py`, `service.py`, `service_cli.py`, `store.py` as needed for the real instance-row query | Lifecycle-only mint/load and consume-only service wiring. |
| Custody proof | Existing `test_signing_key_custody*.py`, `test_auth.py`, `test_import_boundaries.py`, `tests/integration/evidence_handoff/test_signing_key_custody_restart.py` | R1/R3/R4/R8/R9/R10, AST boundary enforcement, and real Windows keyring-write evidence. |
| Documentation custody | This v2, the open-work pool, Plan 9.96 audit, checkpoint, README, roadmap | Freshness, owner for rotation/OAuth deferral, and evidence claims. Do not alter frozen v1/design. |

---

## Ordered execution tasks

### Task 0: Pickup, continuity, and explicit backend decision

**Files:**

- Read: `AGENTS.md`, `CONTRIBUTING.md`, this v2, v1, frozen design, the custody amendment, the
  checkpoint, open-work pool, and current `git status`.
- Modify: the ignored checkpoint only after the commands below pass; no production change.

**Produces:** a reviewer-approved pickup record that identifies the current branch/dirty paths,
frozen object pins, the Docker executable/version, and the exact chosen backend `docker`.

- [x] **Step 1: Verify the frozen and folded inputs.**

  ```bash
  git status --short
  git branch --show-current
  git rev-parse HEAD
  git hash-object docs/superpowers/plans/evidence-handoff-risk-bearing-slice-implementation.md
  git hash-object docs/superpowers/specs/evidence-handoff-a2a-ledger-design.md
  git hash-object docs/superpowers/plans/2026-08-09-evidence-handoff-durable-signing-key-custody-amendment.md
  docker version --format '{{.Client.Version}}'
  docker info --format '{{.ServerVersion}}'
  ```

  Expected: branch `agent/cursor/evidence-handoff-a2a-ledger-risk-slice`, `HEAD` descended from
  `2dce1a8`, the three pins in this document, and a usable Docker Desktop client/server. Dirty paths
  outside the task's explicit ownership are expected and must remain untouched.

  Evidence: 2026-08-10T11:51:03Z checkpoint entry — pins match; `HEAD` `2dce1a8…`; Docker
  client/server `29.6.2`. Amendment hash captured before consolidation delete.

- [x] **Step 2: Record the selection and stop for approval.**

  Record Docker client/server identities, pins, the operator's removal ruling, and that Docker is
  an explicit lifecycle selection—not a runtime failover—in the checkpoint. Obtain review approval
  before v2 Task 1.

  Evidence: checkpoint `## 2026-08-10T11:51:03Z — v2 Task 0 pickup…`; `backend_id="docker"`;
  stopped for review before Task 1.

### Task 1: RED—pluggable Docker backend selection

**Files:**

- Modify: `tests/unit/evidence_handoff/test_lifecycle.py`,
  `tests/unit/evidence_handoff/test_lifecycle_cli.py`, and `tests/unit/evidence/test_naming_boundaries.py`.
- Create: `tests/integration/evidence_handoff/test_docker_lifecycle.py`.
- Modify: `pyproject.toml` only for marker descriptions/default backend selection tests as required.

**Interfaces:**

- Consumes: `FeatureConfig.backend_id` and `LifecycleManager`.
- Produces: an extensible backend contract selected by `backend_id`; `docker` returns
  `DockerPostgresBackend`, while an unrecognized identifier produces stable
  `unsupported_backend` without starting a process. The protocol/factory, rather than a hardcoded
  Docker call in lifecycle, is the reserved extension seam for native Windows.

- [x] **Step 1: Write the failing unit and marker-contract tests.**

  Add tests that assert the Docker adapter emits this exact credential-safe shape (with the selected
  executable as element zero), retains `--env-file`, and contains no password:

  ```python
  assert argv == [
      "docker", "run", "--detach", "--name", container_name,
      "--publish", f"127.0.0.1:{port}:5432",
      "--volume", f"{volume_name}:/var/lib/postgresql/data",
      "--env-file", str(env_file), "postgres:16-alpine",
  ]
  assert password not in " ".join(argv)
  assert manager.start().backend_id == "docker"
  ```

  Also test an unknown backend and a Docker executable missing from PATH are unavailable without a
  subprocess; switching while running remains `backend_switch_refused_while_running`; and the
  lifecycle CLI exposes an explicit `--backend-id` with Docker as its only accepted implemented
  value. Update marker assertions so `requires_evidence_handoff_postgres` and
  `requires_evidence_handoff_service` name real Docker Desktop PostgreSQL/service evidence on
  loopback. Add a regression assertion that neither `WslcPostgresBackend` nor `backend_id="wslc"`
  remains in runtime source.

  Evidence: 2026-08-10T11:57:55Z checkpoint — new RED tests added; existing wslc unit tests intact.

- [x] **Step 2: Run RED and preserve the result.**

  ```bash
  uv run --frozen pytest tests/unit/evidence_handoff/test_lifecycle.py tests/unit/evidence_handoff/test_lifecycle_cli.py tests/unit/evidence/test_naming_boundaries.py -q
  uv run --frozen pytest tests/integration/evidence_handoff/test_docker_lifecycle.py -m requires_evidence_handoff_postgres -q
  ```

  Expected: new Docker/selector/removal assertions fail because no Docker adapter/factory exists
  and wslc has not yet been removed. An environment-only Docker absence is a real dependency
  blocker, not a pass.

  Evidence: unit `13 failed, 21 passed`; integration `1 failed` (ImportError
  `DockerPostgresBackend`). Causes enumerated in checkpoint.

- [x] **Step 3: Stop for RED review.**

  Record the exact failing assertions and absence classification in the checkpoint. Do not begin
  Task 2 without approval.

  Evidence: checkpoint `## 2026-08-10T11:57:55Z — v2 Task 1 RED…`; stopped before Task 2.

### Task 2: GREEN—implement the two-rung backend boundary

**Files:**

- Modify: `src/evidence_handoff_runtime/backends.py`, `config.py`, `lifecycle.py`, and
  `lifecycle_cli.py`.
- Modify: the Task 1 unit/marker tests and `pyproject.toml`.

**Interfaces:**

- Produces a shared `StoreBackend` protocol/factory with `backend_id`, loopback properties,
  `write_env_file`, and `build_{run,start,stop,inspect,volume_inspect,volume_create,remove_container,remove_volume,pull}_argv`.
- `LifecycleManager` resolves the executable for the configured backend and calls the factory; it
  does not hardcode Docker outside that selection boundary.

- [x] **Step 1: Implement the minimal adapter/factory and lifecycle selection.**

  Keep backend selection narrow, value-free, and data-driven so a later native-Windows adapter is a
  registration plus class rather than a lifecycle rewrite:

  ```python
  def _build_docker_backend(*, config, bootstrap, executable):
      return DockerPostgresBackend(
          config=config, bootstrap=bootstrap, docker_executable=executable
      )

  _BACKEND_FACTORIES = {"docker": _build_docker_backend}

  def build_store_backend(*, config, bootstrap, executable):
      factory = _BACKEND_FACTORIES.get(config.backend_id)
      if factory is None:
          raise StoreBackendError("unsupported_backend")
      return factory(config=config, bootstrap=bootstrap, executable=executable)
  ```

  `DockerPostgresBackend` must use the Docker-compatible command set from the global constraints,
  validate `127.0.0.1`, write `POSTGRES_USER` and `POSTGRES_PASSWORD` only to the transient env
  file, and return `backend_id == "docker"`. Change the default `FeatureConfig` and lifecycle CLI
  default to `docker`; remove `WslcPostgresBackend`, wslc executable resolution, and every wslc
  `backend_id` option. Resolve only Docker, report a Docker-specific unavailable code, and keep all
  lifecycle resource-cleanup return-code checks. Delete
  `tests/integration/evidence_handoff/test_wslc_lifecycle.py` in this GREEN step.

  Evidence: 2026-08-10T12:09:45Z checkpoint — factory/adapter landed; runtime wslc gone;
  `test_wslc_lifecycle.py` deleted.

- [x] **Step 2: Run the unit/quality GREEN gate.**

  ```bash
  uv run --frozen pytest tests/unit/evidence_handoff/test_lifecycle.py tests/unit/evidence_handoff/test_lifecycle_cli.py tests/unit/evidence/test_naming_boundaries.py -q
  uv run --frozen ruff check src/evidence_handoff_runtime/backends.py src/evidence_handoff_runtime/config.py src/evidence_handoff_runtime/lifecycle.py src/evidence_handoff_runtime/lifecycle_cli.py tests/unit/evidence_handoff/test_lifecycle.py tests/unit/evidence_handoff/test_lifecycle_cli.py tests/unit/evidence/test_naming_boundaries.py
  git diff --check
  ```

  Expected: Docker selection/removal tests pass; no argv/repr/status contains the admin password;
  marker descriptions name Docker; Ruff and whitespace are clean.

  Evidence: `31 passed`; Ruff clean; `git diff --check` exit 0.

- [x] **Step 3: Stop for implementation review and commit approval.**

  The reviewer must confirm that selection is explicit while stopped, no `backend_id` branch
  bypasses the factory, the wslc adapter/live test are removed, and no source/test change rewrites
  v1's historical evidence. If approved, stage only named v2 Task 2 paths and use
  `feat: add pluggable Docker PostgreSQL backend`.

  Evidence: checkpoint entry; commit not created; awaiting approval.

### Task 3: Prove the Docker rung with real PostgreSQL and service processes

**Files:**

- Modify: `tests/integration/evidence_handoff/test_docker_lifecycle.py`.
- Modify: the active live fixtures `test_postgres_store.py`, `test_integrity_recovery.py`,
  `test_authenticated_service.py`, `test_redaction_service.py`, `test_delivery_service.py`,
  `test_capability_activation.py`, and `test_service_process.py` to select `backend_id="docker"`
  and identify Docker in their docstrings/evidence.
- Delete: `tests/integration/evidence_handoff/test_wslc_lifecycle.py`.
- Modify: the ignored checkpoint only for content-free evidence.

**Produces:** independent live proof for the actual Docker backend (design line 865), including
loopback bind, volume persistence, restart, cleanup, and a real service subprocess.

- [x] **Step 1: Write the Docker-specific real-dependency assertions.**

  The lifecycle test must use `shutil.which("docker")`, a unique container/volume/port, and
  `FeatureConfig(... backend_id="docker")`; it must prove start → health → stop → restart retains a
  real PostgreSQL value and `finally` removes both resources. Change every listed active fixture to
  the explicit Docker selection so the normal live suite exercises the shipped rung. The service
  fixture must start the real `LedgerService` child, use the official MCP client, and assert the
  status/evidence identifies `backend_id == "docker"`. No test may fake a Docker process or refer to
  a removed backend.

  Evidence: 2026-08-10T12:46:03Z checkpoint — Docker lifecycle + fixtures switched.

- [x] **Step 2: Run real Docker evidence and cleanup verification.**

  ```bash
  uv run --frozen pytest tests/integration/evidence_handoff/test_docker_lifecycle.py -m requires_evidence_handoff_postgres -q
  uv run --frozen pytest tests/integration/evidence_handoff/test_postgres_store.py tests/integration/evidence_handoff/test_integrity_recovery.py -m requires_evidence_handoff_postgres -q
  uv run --frozen pytest tests/integration/evidence_handoff/test_authenticated_service.py tests/integration/evidence_handoff/test_redaction_service.py tests/integration/evidence_handoff/test_delivery_service.py tests/integration/evidence_handoff/test_capability_activation.py tests/integration/evidence_handoff/test_service_process.py -m requires_evidence_handoff_service -q
  docker ps -a --format '{{.Names}}'
  docker volume ls --format '{{.Name}}'
  ```

  Expected: real Docker PostgreSQL and real service process pass; recorded per-test names/volumes no
  longer appear after `finally`. A Docker daemon, port, or readiness failure is a blocker recorded
  with the actual command/result, never converted to a fake test pass.

  Evidence: 2 + 13 + 17 passed; destroy argv fixed (`rm`); post-fix resources clean; pre-fix
  orphans disclosed.

- [x] **Step 3: Stop for live-evidence review.**

  Record Docker client/server version, image digest, generated resource identities, loopback port,
  PostgreSQL version, service process identity, official MCP client identity, result, and cleanup in
  the checkpoint. Obtain approval before custody wiring or v1 Task 10 Step 3.

  Evidence: checkpoint `## 2026-08-10T12:46:03Z — v2 Task 3 Docker live proof…`.

### Task 4: GREEN—durable signing-key custody (banked custody-amendment Tasks 0–1 carried forward)

**Files:**

- Create: `src/evidence_handoff_runtime/signing_key_custody.py`.
- Modify: `src/evidence_handoff_runtime/lifecycle.py`, `service.py`, `service_cli.py`, and `store.py`
  only where needed to obtain the real instance-row fact before minting.
- Modify: `tests/unit/evidence_handoff/test_signing_key_custody_resolve.py`,
  `test_signing_key_custody.py`, `tests/unit/evidence/test_import_boundaries.py`, and Plan 9.96's
  logging-surface audit if a new write/sink exists.

**Interfaces (already pinned by RED):**

```python
class SigningKeyCustodyError(Exception):
    code: str  # signing_key_missing, signing_key_mint_forbidden,
               # signing_key_corrupt, or signing_key_unreadable

def keyring_service_for_control_root(control_root: Path) -> str: ...
def load_signing_key(*, control_root: Path, keyring_backend: object) -> bytes: ...
def resolve_signing_key(*, control_root: Path, keyring_backend: object,
                        instance_record_present: bool, store_instance_present: bool) -> bytes: ...
```

- [x] **Step 1: Preserve completed custody-amendment Task 0 and Task 1 RED evidence.**

  Custody-amendment Task 0 R9 passed and custody-amendment Task 1 RED passed its required failure
  shape; do not re-run, rename, or reset this evidence merely because it moved into v2. The reviewer
  checkpoint is the authoritative raw-output record.

- [x] **Step 2: Replace the brittle boundary assertion before GREEN.**

  Convert `test_runtime_input_supplier_and_service_do_not_query_keyring` from source substring
  matching to AST detection, following `tests/unit/evidence/test_import_boundaries.py`. Fail on an
  import of `keyring`, an import-from keyring, or attribute/call access to `get_password`,
  `set_password`, or `delete_password` in `inputs.py` or `service.py`; allow the custody/lifecycle
  module to own those operations. Rename
  `test_r9_key_provenance_does_not_change_claim_set_or_hmac_construction` or use genuinely distinct
  provenance fixtures so it does not compare two indistinguishable key literals.

  Evidence: AST boundary + `test_r9_distinct_provenance_paths_…` (2026-08-10T13:00:33Z).

- [x] **Step 3: Implement lifecycle-only custody and consume-only service wiring.**

  Resolve the same 32-byte key from the OS keyring when present. Mint and write only when both
  instance facts are absent. Translate missing/unreadable/corrupt keyring results to the stable
  content-free `SigningKeyCustodyError` codes; propagate a failed custody resolution to an
  unavailable/non-listening service start with no remint. Pass resolved key bytes through the
  existing ephemeral auth-bundle start handshake while retaining `service_cli.py` delete-after-read
  for `store_conninfo`; do not let the child read the keyring. Keep `CredentialIssuer.issue()` and
  `CredentialValidator.validate()` signatures, claims, `eh1.` framing, and HMAC construction intact.

  Evidence: `signing_key_custody.py` + `resolve_installation_signing_key` + `instance_row_present`.

- [x] **Step 4: Run the custody unit/orthogonality gate.**

  ```bash
  uv run --frozen pytest tests/unit/evidence_handoff/test_signing_key_custody_resolve.py tests/unit/evidence_handoff/test_signing_key_custody.py tests/unit/evidence_handoff/test_auth.py tests/unit/evidence/test_import_boundaries.py -q
  uv run --frozen ruff check src/evidence_handoff_runtime/signing_key_custody.py src/evidence_handoff_runtime/lifecycle.py src/evidence_handoff_runtime/service.py src/evidence_handoff_runtime/service_cli.py tests/unit/evidence_handoff/test_signing_key_custody_resolve.py tests/unit/evidence_handoff/test_signing_key_custody.py tests/unit/evidence/test_import_boundaries.py
  git diff --check
  ```

  Expected: R3 combinations never mint after either instance fact exists; corrupt/unreadable paths
  have typed errors; no durable key text appears under the control root; AST rejects service/supplier
  keyring access; R9 passes. Any R9 failure is a stop, not a workaround.

  Evidence: **45 passed**; Ruff clean; `git diff --check` exit 0.

- [x] **Step 5: Stop for custody GREEN review and commit approval.**

  Review key provenance, both mint facts, no-service-keyring AST evidence, R9 result, and any Plan
  9.96 classification. If approved, stage only named Task 4 files; suggested message:
  `feat: preserve ledger signing keys across service restart`.

  Evidence: checkpoint; commit not created.

### Task 5: Real Windows custody acceptance and complete v1 Task 11 replacement gates

**Files:**

- Modify: `tests/integration/evidence_handoff/test_signing_key_custody_restart.py` for explicit
  Docker selection where required by the new default.
- Modify: `pyproject.toml`, the Plan 9.96 audit, checkpoint, pool, README, and roadmap only when
  their current-state claims require correction.

**Produces:** real OS-keyring write evidence and the complete, evidence-bound replacement for every
v1 Task 11 gate—not a claim that OAuth or rotation is complete. Do not run v1 Task 11 separately;
this task supersedes it in full.

- [x] **Step 1: Run the real keyring-write tests on Windows using Docker.**

  ```bash
  uv run --frozen pytest tests/integration/evidence_handoff/test_signing_key_custody_restart.py -m "requires_os_keyring_write and requires_evidence_handoff_service" -q
  ```

  Expected: a pre-crash token validates after taskkill/terminate and restart; missing/deleted,
  unreadable, and corrupt custody after an instance exists refuse to start with no listening port and
  no remint; test cleanup deletes only its isolated keyring service entry. The evidence identifies
  Docker, not a fake store or an unconfigured backend.

  Evidence: 2 passed (20.70s); `backend_id == "docker"` asserted; Docker 29.6.2;
  `postgres:16-alpine` digest `sha256:57c72fd2a128…`; post-run orphans 0/0.

- [x] **Step 2: Run Windows repository, coverage, and quality gates.**

  ```bash
  uv run --frozen pytest tests/unit/evidence tests/unit/evidence_handoff tests/unit/docs/test_open_work_pool_hygiene.py tests/unit/tools/test_verify_evidence_handoff_live.py -q
  uv run --frozen pytest tests/integration/evidence_handoff -q
  uv run --frozen pytest -q
  uv run --frozen pytest --cov=src/optimus --cov=src/optimus_gateway --cov=src/optimus_security --cov=src/evidence_handoff --cov=src/evidence_handoff_runtime --cov-report=term-missing --cov-report=xml --cov-fail-under=80
  uv run --frozen ruff check .
  uv run --frozen detect-secrets-hook --baseline .secrets.baseline src tools
  uv lock --check
  git diff --check
  ```

  Expected: selected and full untargeted suites, explicit 80%-floor coverage, and quality gates
  pass; skipped named dependencies are reported as blockers rather than successes.

  Evidence: unit evidence scope 505 passed/2 skipped; integration default-deselected exit 5
  (34 deselected, expected); full untargeted 3120 passed/27 skipped/116 deselected; coverage
  81.08% (≥80); ruff clean after import-order fix on restart fixture; detect-secrets/lock/diff-check
  exit 0.

- [x] **Step 3: Run mandatory WSL2 Linux-CI parity.**

  From the repository's `/mnt/d/Projects/Development/Python/optimus-cost-agent-wt-cursor` path in
  WSL2 Ubuntu, with the normal default deselection of named real-dependency markers, run:

  ```bash
  uv sync --frozen --extra dev
  uv run --frozen pytest tests/unit/evidence_handoff tests/integration/evidence_handoff -q
  ```

  Expected: portable, migration, and PostgreSQL-protocol behavior pass under WSL2. Do not force
  select Docker lifecycle, service, keyring, or other named real-dependency markers in this parity
  run. Windows remains mandatory for Docker Desktop, loopback, lifecycle, Windows keyring, path,
  ACL, service-process, and named-agent claims. A failure in the scoped portable/protocol parity run
  is a platform-shaped gate failure; absence of Docker Desktop WSL integration is not a blocker for
  this step.

  Evidence: `wsl -d Ubuntu-24.04` → 177 passed, 34 deselected. Note: WSL `uv sync` recreates the
  shared `.venv`; Windows `uv sync --frozen --extra dev` restored afterward.

- [x] **Step 4: Run static boundary, package, and status checks.**

  ```bash
  uv run --frozen pytest tests/unit/evidence/test_import_boundaries.py tests/unit/evidence/test_naming_boundaries.py tests/unit/docs/test_open_work_pool_hygiene.py -q
  uv build
  git status --short
  ```

  Expected: AST rejects forbidden imports/dynamic imports, names contain no scheduling coupling, the
  wheel contains the portable/runtime packages, and status contains only approved task paths plus
  known concurrent Cursor paths.

  Evidence: boundaries/hygiene green after allowlisting v2 plan + DESIGN-REFRESH; `uv build`
  produced sdist+wheel; status retains Task 5 + Task 10 leftovers (not broad-staged).

- [x] **Step 5: Run the documentation freshness and deferred-work audit.**

  Confirm v1/design remain byte-pinned; the pool retains named ownership for OAuth/rotation and the
  non-blocking `EVIDENCE-HANDOFF-FEAT-A2A-LEDGER-DESIGN-REFRESH`; marker descriptions name Docker;
  and the README/roadmap/open-work pool do not claim an unmerged or unproven Docker/custody state.
  Record every current-state document inspected in the checkpoint.

  Evidence: pins `905b4f2f…` / `fa409ef5…` match; amendment path already deleted (Task 0);
  pool A2A row → v2 active + DESIGN-REFRESH ownership; CREDENTIAL-LIFECYCLE retains OAuth/rotation
  after Option A; markers name Docker Desktop; README/roadmap have no false unmerged Docker/custody
  claim.

- [ ] **Step 6: Stop for acceptance review.**

  Provide the Windows/Docker/keyring evidence identities, R1/R3/R4/R8/R9/R10 mapping, full-gate
  results, documentation audit, and any remaining blocker. Do not claim Task 10 Step 3 or release
  completion at this gate.

### Task 6: Finish the existing native-agent capstone against final custody/backend behavior

**Files:**

- Modify only the already-approved Task 10 verifier/evidence files and the checkpoint as permitted
  by its separate authorization; do not rewrite v1 Task 10.

**Mid-run interop fix (not Task 6 evidence):** Cursor Streamable HTTP discovery failed when
`MCP-Protocol-Version` was sent twice and joined as `2025-11-25, 2025-11-25`. Production fix lives
in `src/evidence_handoff_runtime/transport.py` + `service.py` (parse/resolve joined tokens; rewrite
ASGI scope to one canonical token; leave an absent header absent). Land that change as its **own
reviewed commit** with unit coverage in `tests/unit/evidence_handoff/test_transport.py` — do not
fold it into Task 6 / v1 Task 10 evidence commits. Remaining OAuth/`WWW-Authenticate`/`/.well-known`
discovery gaps stay owned by `EVIDENCE-HANDOFF-FEAT-CREDENTIAL-LIFECYCLE`.

**Session protocol admission (Option A, operator ruling 2026-08-10):** Spec-correct clients omit
`MCP-Protocol-Version` on `initialize` (version negotiates in the JSON-RPC body). Headerless
initialize still defaults the create-time bind to `2025-11-25`, then follow-ups carry the
genuinely negotiated version (Codex: `2025-06-18`), which exact-match validation rejected as
`session_protocol_mismatch`. **Option A** (shipped): `SessionRegistry` accepts any version in the
service's admitted `protocol_versions` set; non-admitted versions still raise
`session_protocol_mismatch`. **Option B** (not shipped): bind the session to the version actually
negotiated in the initialize *response* — the strictly-faithful reading of "bound to the negotiated
protocol version." B remains on the agenda for `EVIDENCE-HANDOFF-FEAT-A2A-LEDGER-DESIGN-REFRESH`
when that design refresh lands; A is the deliberate pragmatic form for this capstone.
**Produces:** v1 Task 10 Step 3–5 evidence using Docker and durable custody after v2 Tasks 3–5
pass.

- [x] **Step 1: Reconfirm the v1 Task 10 Step 1–2 uncommitted paths and approval.**

  ```bash
  git status --short -- tests/e2e/evidence_handoff tests/fixtures/evidence_handoff tests/unit/tools/test_verify_evidence_handoff_live.py tools/evidence_handoff_live_support tools/verify_evidence_handoff_live.py
  ```

  Expected: only the separately approved uncommitted v1 Task 10 paths. If they changed outside that
  approval, stop for review rather than absorb them into Docker/custody commits.

- [x] **Step 2: Run the real native-agent scenario and evidence inspection.**

  ```bash
  uv run --frozen pytest tests/e2e/evidence_handoff/test_three_agent_live.py -m requires_real_agents -q
  uv run --frozen python tools/verify_evidence_handoff_live.py verify --evidence-root C:\evidence-handoff-live\run --service-endpoint http://127.0.0.1:PORT/mcp
  uv run --frozen python tools/verify_evidence_handoff_live.py inspect --evidence-root C:\evidence-handoff-live\run
  ```

  Expected: real Claude Code, Codex, and Cursor identities with distinct credentials prove the
  existing delivery/rejection/latch scenario using Docker and durable custody. The independent
  client rule, raw-canary scan, and no-fake-agent rule remain load-bearing.

- [x] **Step 3: Stop for named-agent evidence review.**

  Stage and commit only the named v1 Task 10 paths after their own approval. Do not combine them with
  Docker/custody files or this plan.

## Explicit exceptions

- Any edit, rename, or digest change to v1 or the frozen design.
- Native Windows PostgreSQL implementation, SQLite, remote/shared MCP, or an implicit/running
  backend failover. The protocol/factory seam is retained for native Windows; a native adapter needs
  its owned future work before registration.
- Docker credentials in argv or any secret-bearing status/log/manifest/evidence output.
- OAuth, dynamic client registration, JWKS, `kid`, key rotation, multi-key verification, or a
  key-per-`ledger_instance_id` design.
- A service, `RuntimeInputSupplier`, or MCP handler query to the OS keyring.
- Any change to token signatures, claims other than random `token_id`, `eh1.` framing, or HMAC
  construction.
- Changing the ephemeral `store_conninfo` auth-bundle deletion behavior.
- Staging Cursor's concurrent source/test paths or using broad Git staging.

## Plan consolidation after approval

Once this v2 receives independent review and operator approval, delete only
`docs/superpowers/plans/2026-08-09-evidence-handoff-durable-signing-key-custody-amendment.md` by
explicit path. It was never committed, so no Git history is removed; its decision/evidence history
is carried above and in the ignored reviewer checkpoint. Do not delete it while this v2 remains a
draft. The next `git status` must show only the intended deletion plus this v2 document before any
explicit-path documentation commit.

## Definition of done

- [x] Docker is the real, loopback-only sole implemented PostgreSQL backend; the pluggable
  protocol/factory remains, and no lifecycle operation performs implicit failover.
- [x] Docker lifecycle and service evidence use real Docker Desktop/PostgreSQL/official MCP client,
  record identities, and clean their named containers and volumes.
- [x] Durable lifecycle OS-keyring custody preserves a pre-crash credential across restart and
  fails closed with typed errors after any existing-instance signal.
- [x] R9 and R10 remain true, AST proves service/supplier keyring exclusion, and `requires_os_keyring_write`
  remains distinct from the read-only marker.
- [x] Windows repository/coverage gates, WSL2 parity, static boundary/package checks,
  documentation freshness audit, and v1 Task 10's real native-agent evidence are recorded; no
  deferred OAuth/rotation/design-refresh work is left unowned.
- [x] v1 and frozen design pins match, the amendment is deleted only after v2 approval, and no
  unrelated shared-worktree path was staged or committed.

### DoD / closure note (2026-08-11)

PASS on all six criteria.

Criterion 2 cites Task 3's Docker artifacts (`bd17dac`; client/server 29.6.2, image
`sha256:57c72fd2…`, PostgreSQL 16.14, `restart_persistence` true) rather than re-running, because
the live infrastructure is torn down — as the plan permits.

Task 6 evidence is archived at `C:\evidence-handoff-archive\task6\` (`task6-manifest.json` sha256
`5f9e5fe4…`).

The `P11-FU-6` pair recurred during the DoD coverage run (both `test_server` harness tests, under
`--cov`; passed isolated, in-file, and on coverage re-run at 81.34%). Recorded as a recurrence on
`P11-FU-6` only — do not merge with `P11-FU-7`.

### DoD addendum (post-closure, 2026-08-11)

The six checkboxes above remain correctly passed on their own terms. This addendum records what
was found after closure when PR CI first ran against the branch.

1. **Gate gap found after closure.** Criterion 5's "Windows repository/coverage gates" did not
   include four checks that exist only in CI: `bandit`, `pre-commit optimus-ast-grep`,
   `optimus.guardrails.prompt_injection`, and `detect-secrets`. Because the branch's 22 commits
   had never been pushed, CI had never run against them once — so a bandit B110 failure had been
   latent since the affected lines were written, and the DoD passed without exercising it.

2. **Sixth defect, fourth fail-open, fixed at `c963416`**
   (`fix(evidence-handoff): fail closed when the integrity mirror cannot be written`).
   `IntegrityMonitor._persist_latch` swallowed `mirror_integrity_incident` failures and
   duck-checked the method's presence. Since the Option B change made the DB mirror the
   service's **only** latch source in production (`control_root=None` there), a swallowed mirror
   failure meant a tampered ledger would keep serving as healthy. Now the mirror is called
   directly and failures propagate; the file latch still persists first.

3. **Process lesson for future slices:** run the **full** CI gate set locally before claiming a
   DoD pass, not just the plan's named gates. Future DoD criteria should name `bandit`,
   `ast-grep`, `prompt-injection`, and `detect-secrets` explicitly. Also: never read `$?` after
   a pipe — that returns the last pipeline element's exit code, which is how the bandit failure
   was initially misreported as passing.

## Review handoff

Review this v2 against the two pinned parents, the checkpoint's custody-amendment Task 0/1 evidence,
design lines 143–146, 265, 865, and 898, and the current shared-tree diff. In particular, confirm
that (1) Docker is proven as a real named backend rather than a fake or implicit fallback, (2) the
protocol/factory seam survives while all wslc runtime support is removed, (3) the non-blocking design
refresh has named pool custody, (4) v2 Task 5 fully replaces v1 Task 11, (5) every custody
ruling—including the AST test and differentiated R9 fixture findings—survives the fold, and (6) the
amendment remains present until this plan is approved.
