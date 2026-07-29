# Plan 11.6: P11.5-FU-2 Local Startup Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILLS: Use `superpowers:executing-plans` to execute
> this plan task-by-task and `superpowers:test-driven-development` for every behavior change.
> Steps use checkbox syntax (`- [ ]`) for tracking. No implementation may begin until Task 0
> records reviewer and operator approval of the final plan SHA-256.

**Status:** Drafted for Claude review and operator approval on 2026-07-29. Implementation is not
authorized. No source, test, launcher, runbook, dependency, or runtime-service change has started
from this plan.

**Goal:** Consolidate local live/evidence startup around the authorized `optimus-agent` session
path and the existing `optimus-trust run-gateway` persistent security ceremony, while removing
the stricter evidence-child environment gate and misleading shell wrappers.

**Architecture:** Preserve `optimus-agent`'s post-authorization Redis/Gateway auto-start as the
session-bound path, and preserve `optimus-trust run-gateway` as the foreground persistent Gateway
ceremony needed by direct clients and live evidence. `build_acp_subprocess_env` will project only
present registry-authorized agent variables plus safe system variables, so an empty Optimus
environment reaches the child unchanged and the child resolves loopback defaults and keychain
credentials through its existing launch path. Optional local Phoenix startup is an explicit
`--with-local-phoenix` mode on either existing entrypoint; its fixed loopback OTLP endpoint is
passed only to the Gateway child. The default Redis port remains 6379, with Docker-owner identity
checks and a native/no-owner escape before real TimeSeries preflight.

**Tech Stack:** Python 3.14+, existing keyring and Redis packages, Docker CLI, Redis 8,
`arizephoenix/phoenix:latest`, OpenTelemetry OTLP HTTP/protobuf, pytest, pytest-asyncio,
pytest-cov, coverage.py, Ruff, PowerShell and Bash documentation, and the independently authored
`acpx` client. No new Python dependency or Phoenix SDK is permitted.

## Global Constraints

- Drafting baseline is `origin/main` commit
  `e388258dc77bbeafbfe1b6f0f06229c3261416b0`, verified after `git fetch origin` on
  2026-07-29. The drafting branch is
  `agent/codex/plan-11-6-local-startup-consolidation`, created directly from that commit in the
  existing linked worktree.
- `P11.5-FU-2` is the stable backlog identity. This file allocates Plan 11.6; do not create a new
  follow-up ID, a second backlog, or another Plan 11.x number for the same work.
- The authoritative requirement source is the complete `P11.5-FU-2` entry in
  `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`. This plan refines
  that entry; it does not replace or delete its history.
- This remediation goes directly to an implementation plan, following Plans 10.1-10.3. No
  separate design-spec file is required because the backlog already supplies reviewed
  requirements and this plan makes the remaining decisions explicit.
- The single documented live-run mechanism has two explicit lifecycle entrypoints: the
  session-bound `optimus-agent` auto-start path and the foreground `optimus-trust run-gateway`
  security ceremony for a persistent Gateway. `--with-local-phoenix` is an option on each existing
  entrypoint, not a new command or script family. Do not add `run-local-stack`, Docker Compose,
  Makefile, task-runner, or another wrapper.
- `optimus-trust setup-credentials` and `optimus-trust approve` remain prerequisite credential and
  authorization ceremonies, not competing dependency launchers.
- Retain `optimus-trust run-gateway` as the documented persistent foreground Gateway path; extend
  it only as needed to start the same optional named Phoenix service. Delete only
  `tools/run_local_gateway.sh` / `.ps1` and their wrapper-specific test. Do not preserve hidden
  aliases or copy wrapper behavior into a renamed script.
- `build_acp_subprocess_env` must honor the proven keychain/default contract. It must not require
  `OPTIMUS_GATEWAY_URL`, `OPTIMUS_API_KEY`, or `OPTIMUS_REDIS_URL`, and must not inject their
  defaults into the child: an empty Optimus projection must stay empty so authorization digests
  match a direct zero-env `optimus-agent` launch.
- Parent-only verification code may resolve the existing Redis loopback default for its own
  connection, but must pass the original registry projection to the child. It must not resolve,
  copy, or log keychain secrets.
- Preserve the one-key boundary: the agent child may receive `OPTIMUS_API_KEY`, never a vendor key
  or `OPTIMUS_LOCAL_GATEWAY_*` secret. Provider keys, the local shared secret, and
  `OTEL_EXPORTER_OTLP_ENDPOINT` remain Gateway-child-only.
- Local Phoenix uses the fixed loopback HTTP/OTLP contract
  `http://127.0.0.1:6006` / `http://127.0.0.1:6006/v1/traces`. Production code must not import a
  Phoenix SDK or accept a Phoenix credential. The image identity used by this local-only path is
  `arizephoenix/phoenix:latest`; live evidence must record its resolved Docker image ID/digest.
- `--with-local-phoenix` and `--no-auto-start` are mutually exclusive. Phoenix starts only after
  launch authorization, audit append, and workspace-identity revalidation, and before the Gateway
  child. The Gateway process retains its existing stop-on-exit ownership; Redis and Phoenix remain
  named Docker services and are not deleted automatically.
- When `--with-local-phoenix` is combined with `--check-config`, `--strict` is required so the
  smoke actually starts and authenticates the Gateway path that receives OTLP configuration.
- Keep the established Redis default
  `redis://127.0.0.1:6379/0`, container `optimus-redis`, and image `redis:8`. A fixed non-default
  port would merely move the collision and would churn README examples, tests, configurations, and
  durable approvals without adding identity.
- On the default Redis URL, a reachable 6379 is accepted when Docker proves the running owner is
  `optimus-redis` (the configured image is recorded but functional TimeSeries preflight remains the
  capability gate), or when no Docker owner is visible and the listener is treated as an explicit
  native/operator-managed Redis. A different Docker container is a typed conflict; native Redis
  remains usable and must still pass real TimeSeries preflight.
- An explicitly configured non-default Redis URL remains operator-owned and is validated by the
  existing reachability/TimeSeries preflight. The auto-start path never stops, removes, renames, or
  reconfigures an unrelated container.
- Live-tier evidence must use real dependencies: `requires_redis` uses TimeSeries-capable Redis,
  `requires_gateway` uses real Optimus credentials/Gateway, `requires_phoenix` uses real Phoenix,
  and ACP evidence uses external `acpx`. Unit fakes may not justify live sign-off.
- Every behavior task follows RED, focused failing command, minimum implementation, focused green,
  then checkpoint. Checkboxes may be marked only after their literal verification commands pass.
- The reviewer owns
  `docs/superpowers/reviews/plan-11-6-review-checkpoints.md`; it is gitignored and must never be
  staged. Record rulings, RED/GREEN output, changed paths, dependency identities, and commit SHAs.
- Before sign-off, run affected suites, the default suite, aggregate production coverage at or
  above 80%, `uv run --frozen ruff check .`, live dependency gates, the retirement/presence audit,
  `git diff --check`, and `git status --short --branch`.
- Commit, push, PR creation, merge, branch deletion, history rewrite, runtime-container deletion,
  and stopping unrelated containers require separate operator authorization. This plan does not
  grant it.

## Explicit Exceptions

- `P11-FU-8` (`OPTIMUS_LOCAL_GATEWAY_BASE_URL` naming and HMAC migration) is excluded. Do not rename
  that variable or change its fingerprint/approval behavior.
- `P11.5-FU-1` (real `OTLPSpanExporter` `FAILURE` to `queued` mapping) is excluded. Do not change
  trace delivery-state semantics or retry classification.
- The Plan 11.5 multi-root OTel trace-grouping disposition is excluded.
- No Gateway route, model-provider, search-provider, accounting, budget, telemetry-event, or
  persistence capability is added or changed.
- No provider key, local shared secret, OTLP endpoint, Phoenix setting, or Redis URL is migrated to
  a new environment-variable name.
- No Docker daemon, container, or image is installed, removed, stopped, or upgraded by the
  implementation. Auto-start may create/start only `optimus-redis` and `optimus-phoenix` after
  identity checks.
- Frozen Plan 9.x, Plan 10.x, and Plan 11.5 plan/spec files are read-only. Their checkboxes and
  wording are not implementation scope.

## Decisions at Pickup

### Decision 1: Make evidence subprocesses honor the agent contract

Choose the backlog's preferred direction: remove the three-variable required-shell gate. Do not
document a deliberate divergence.

`optimus-agent` captures its environment, authorizes that exact snapshot, then fills loopback
URLs/model and the keychain-resolved shared secret from the authorized candidate. If a parent
helper injected defaults first, those values would become inherited digest inputs and could cause
an approval mismatch that a direct zero-env launch does not have. Therefore
`build_acp_subprocess_env` projects only present registry-authorized values; it neither resolves
credentials nor applies defaults.

### Decision 2: Keep port 6379 and verify identity

Choose an explicit identity/ownership check rather than a project-specific non-default port. Any
fixed port can collide; changing the default would also expand the blast radius across launch
snapshots, examples, tests, and operator configuration. The safer rule is:

- if Docker reports a container owner, default 6379 must belong to named container `optimus-redis`;
  a different Docker container is a typed, non-destructive startup failure with exact diagnostics;
- if Docker reports no owner (including a native Redis or a Docker daemon that is unavailable),
  preserve the existing reachable-listener behavior and let real TimeSeries preflight decide;
- a deliberate custom Redis URL is operator-owned and still must pass real TimeSeries preflight.

### Decision 3: Extend the existing launcher for Phoenix

Add `--with-local-phoenix` to both existing lifecycle entrypoints: `optimus-agent` for a
session-bound child and `optimus-trust run-gateway` for the persistent foreground Gateway. Neither
is a new executable. The shared helper ensures named container `optimus-phoenix` using
`arizephoenix/phoenix:latest`, waits for `/healthz`, and supplies the fixed loopback `/v1/traces`
value only as an argument to Gateway-child environment assembly. The agent-facing environment and
`.env.example` remain free of OTLP/Phoenix configuration.

## Acceptance Ledger

| Backlog requirement | Implementation tasks | Evidence |
|---|---:|---|
| One documented live-run sequence with explicit session-bound and persistent lifecycle entrypoints | 3, 4, 5 | Presence/retirement test and runbook |
| Evidence subprocess honors keychain/default contract | 1 | Zero-env unit and external-`acpx` evidence |
| Misleading Gateway wrappers removed while the persistent ceremony remains documented | 4, 5 | CLI persistence/flag test, wrapper path absence, active-surface `rg` |
| Phoenix belongs to the same mechanism and remains Gateway-only | 3, 5, 6 | Lifecycle/boundary tests and real Phoenix OTLP |
| Runbook text and code match | 5, 6 | Presence test and zero-env strict smoke |
| Launch trust, one-key, and Gateway-only OTLP remain intact | 1, 2, 3, 6 | Ordering/secret-boundary tests and live evidence |
| Wrong Redis on the default port is detected with a recovery path | 2, 5, 6 | Ownership tests, runbook diagnosis, isolated live conflict |
| Real dependency evidence, full fitness, and custody closure | 6 | Consolidated live report, coverage, Ruff, backlog closure |

## Source Anchors and Baseline Evidence

- `src/optimus/acp/__main__.py:281-416` captures the environment once, authorizes/audits/
  revalidates, applies local defaults, starts Redis/Gateway, and stops the owned Gateway process.
- `src/optimus/acp/local_infra.py:48-55,150-184,203-320` defines the current Redis identity/default,
  best-effort startup, and launch-authorized Gateway child.
- `src/optimus/acp/subprocess_env.py:30,81-145` imposes the separate three-variable gate and points
  errors to the soon-to-be-retired scripts.
- `src/optimus/acp/operator_verify.py:246-268` directly indexes `OPTIMUS_REDIS_URL` before calling
  `build_acp_subprocess_env`; it must use a parent-only resolved view without changing the child
  snapshot.
- `tools/run_plan115_acpx_cost_obs_evidence.py:100-159` builds the external-`acpx` child
  environment and invocation. Its unit tests are in
  `tests/unit/tools/test_run_plan115_acpx_cost_obs_evidence.py`.
- `src/optimus/acp/launch_approval_cli.py:130,495-639` and
  `tools/run_local_gateway.sh` / `.ps1` are the overlapping interactive Gateway path and wrappers.
- `tests/integration/telemetry/test_phoenix_live.py:1-104` contains the only Phoenix launcher hint.
- `.env.gateway.example:13-16` correctly keeps `OTEL_EXPORTER_OTLP_ENDPOINT` off the agent side,
  but no current auto-start path supplies that value to the Gateway child.
- `README.md` currently documents auto-start, the manual Gateway scripts, and several inline Redis
  Docker commands; those competing live-run instructions must collapse to the runbook link.
- Official Phoenix Docker documentation states that port 6006 serves both the UI and OTLP HTTP
  `/v1/traces`, and demonstrates `arizephoenix/phoenix:latest`:
  <https://arize.com/docs/phoenix/self-hosting/deployment-options/docker> and
  <https://arize.com/docs/phoenix/self-hosting/configuration>.
- Drafting baseline command:

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_acp_subprocess_env.py tests/unit/acp/test_local_infra.py tests/unit/tools/test_run_local_gateway_scripts.py tests/integration/release/test_verify_live_agent_cli.py -q
  ```

  Result on 2026-07-29: `62 passed in 2.62s`.

## File and Responsibility Map

| File | Responsibility in this plan |
|---|---|
| `src/optimus/acp/subprocess_env.py` | Project present registry-authorized agent names without a required-shell gate or injected defaults. |
| `src/optimus/acp/operator_verify.py` | Resolve the existing Redis default only for the parent verifier while preserving the original child projection. |
| `src/optimus/acp/local_infra.py` | Typed local-infrastructure failures, Docker port/image ownership checks, Phoenix lifecycle, and Gateway-only OTLP injection. |
| `src/optimus/acp/__main__.py` | Parse the Phoenix option, preserve authorization ordering, start the one local dependency path, and clean up the Gateway on all exits. |
| `src/optimus/acp/launch_approval_cli.py` | Retain the `run-gateway` security ceremony, add optional Phoenix startup, and remove only wrapper-era stale comments/imports. |
| `src/optimus/acp/preflight.py` | Replace inline Redis launcher hints with the single runbook remediation. |
| `tools/run_plan115_acpx_cost_obs_evidence.py` | Launch external `acpx` with the same zero-env agent contract and optional Phoenix mode. |
| `tools/run_local_gateway.sh`, `tools/run_local_gateway.ps1` | Delete after replacement tests pass. |
| `tests/unit/acp/test_acp_subprocess_env.py` | Pin empty projection, registry parity, and secret exclusion. |
| `tests/integration/release/test_verify_live_agent_cli.py` | Pin parent-only Redis default resolution and unchanged child projection. |
| `tests/unit/acp/test_local_infra.py` | Pin Redis ownership failure, Phoenix lifecycle/health, and Gateway-only endpoint propagation. |
| `tests/unit/acp/test_main_wiring.py` | Pin option conflicts, authorization/startup ordering, strict check-config startup, and cleanup. |
| `tests/unit/acp/test_launch_approval_cli.py` | Pin persistent `run-gateway` plus `--with-local-phoenix`, while preserving setup/approve/run commands. |
| `tests/unit/tools/test_run_plan115_acpx_cost_obs_evidence.py` | Pin no-required-env capture and `--with-local-phoenix` invocation. |
| `tests/unit/tools/test_run_local_gateway_scripts.py` | Delete with the retired wrappers. |
| `tests/integration/telemetry/test_phoenix_live.py` | Remove the ad-hoc Docker hint and point dependency failures to the runbook. |
| `tests/unit/tools/test_plan116_local_startup_docs.py` | Presence/retirement contract between code, runbook, README, examples, and live-test hints. |
| `docs/superpowers/plans/2026-07-29-plan-11-6-local-live-dependencies-operator-runbook.md` | Single operator source of truth for credentials, approval, startup, smoke, identity diagnosis, and recovery. |
| `README.md`, `.env.gateway.example` | Link to the runbook and describe Gateway-only OTLP projection without competing launcher commands. |
| `reports/plan-11-6-local-startup-live-evidence.md` | Named real Redis/Gateway/Phoenix/acpx/runbook-smoke evidence artifact. |
| `reports/plan-11-6-local-startup-acpx-evidence.md` | Sanitized external-`acpx` transcript/result evidence consumed by the consolidated live report. |
| `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | Promotion now; implementation closure only after Task 6 evidence. |
| `docs/superpowers/reviews/plan-11-6-review-checkpoints.md` | Gitignored reviewer handoff/evidence log; never stage. |
| `docs/superpowers/reviews/2026-07-29-plan-11-6-implementation-plan-approval.md` | Create only after Claude and operator approve the exact plan digest. |

---

### Task 0: Re-verify allocation, freeze the reviewed plan, and re-derive blast radius

**Files:**

- Inspect every source anchor and file in the responsibility map.
- Create after approval:
  `docs/superpowers/reviews/2026-07-29-plan-11-6-implementation-plan-approval.md`.
- Create/update only as a gitignored handoff:
  `docs/superpowers/reviews/plan-11-6-review-checkpoints.md`.

**Produces:** A digest-pinned implementation contract based directly on current `origin/main`,
with a fresh blast-radius inventory and no collision with another Plan 11.6 allocation.

- [ ] **Step 1: Verify branch ancestry, clean state, and plan allocation.**

  Run:

  ```powershell
  git fetch origin
  git status --short --branch
  git merge-base HEAD origin/main
  git rev-parse origin/main
  rg -n "Plan 11\.6|P11\.5-FU-2" docs README.md
  ```

  Expected: implementation starts on an approved `agent/<id>/<slug>` branch forked directly from
  then-current `origin/main`; only this plan/backlog promotion allocate Plan 11.6; no unexplained
  dirty source/test path exists.

- [ ] **Step 2: Re-read authority and stop on conflict.**

  Read `AGENTS.md`, `CONTRIBUTING.md`, the full backlog entry, this plan, the Plan 9.6 Phase C
  runbook precedent, and the current HLD/LLD/Test Strategy citations governing one-key,
  Gateway-only OTLP, launch trust, and real evidence. Record exact blob IDs/digests. If those
  authorities conflict with this plan, stop for an operator ruling.

- [ ] **Step 3: Re-derive the blast radius mechanically.**

  Run:

  ```powershell
  rg -n "ensure_local_(redis|gateway)|build_acp_subprocess_env|run-gateway|run_local_gateway|OPTIMUS_REDIS_URL|OTEL_EXPORTER_OTLP_ENDPOINT|PHOENIX_TEST_BASE_URL|redis:8|arizephoenix/phoenix|6379|6006" src tests tools README.md .env.example .env.gateway.example pyproject.toml
  ```

  Classify every active hit as modify, delete, verify-only, or explicit exception in the checkpoint
  log. Historical frozen plans/reports may be verify-only; no active runtime/test/doc hit may be
  silently omitted.

- [ ] **Step 4: Re-run the focused baseline.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_acp_subprocess_env.py tests/unit/acp/test_local_infra.py tests/unit/acp/test_launch_approval_cli.py tests/unit/acp/test_main_wiring.py tests/unit/tools/test_run_local_gateway_scripts.py tests/unit/tools/test_run_plan115_acpx_cost_obs_evidence.py tests/integration/release/test_verify_live_agent_cli.py -q
  ```

  Expected: green before implementation. A failure is investigated and ruled on; it is not
  normalized into this plan.

- [ ] **Step 5: Obtain digest-pinned review approval.**

  Compute:

  ```powershell
  Get-FileHash -Algorithm SHA256 docs/superpowers/plans/2026-07-29-plan-11-6-p11-5-fu-2-local-startup-consolidation.md
  ```

  Claude independently verifies every cited path/behavior. After Claude and the operator approve,
  create the approval record with plan path, SHA-256, baseline commit, decisions, exceptions, and
  approval identities/timestamps. No implementation checkbox may be marked before this passes.

### Task 1: Remove the evidence-only required-shell gate

**Files:**

- Modify: `src/optimus/acp/subprocess_env.py`
- Modify: `src/optimus/acp/operator_verify.py`
- Modify: `tools/run_plan115_acpx_cost_obs_evidence.py`
- Modify: `tests/unit/acp/test_acp_subprocess_env.py`
- Modify: `tests/integration/release/test_verify_live_agent_cli.py`
- Modify: `tests/unit/tools/test_run_plan115_acpx_cost_obs_evidence.py`

**Interfaces:**

- Produces:
  `build_acp_subprocess_env(*, operator_environ: Mapping[str, str] | None) -> dict[str, str]`
  that projects only present `AGENT_CHILD` registry names plus safe system names.
- Preserves: `SubprocessEnvConfigurationError` for an actually unapproved output name; no missing
  variable is an error.
- Consumes later: Task 3's external-`acpx` invocation adds the Phoenix mode without changing this
  environment contract.

- [x] **Step 1: Write RED zero-env and digest-parity tests.**

  Replace the missing-Gateway failure test with:

  ```python
  def test_empty_optimus_environment_stays_empty_for_keychain_default_child():
      env = build_acp_subprocess_env(operator_environ={"PATH": "/usr/bin"})
      assert env == {"PATH": "/usr/bin"}
      assert not any(name.startswith("OPTIMUS_") for name in env)
  ```

  Update `test_specially_handled_and_derived_optional_keys_equal_registry_exactly`,
  `test_optional_agent_env_keys_is_derived_not_hand_maintained`,
  `test_module_level_guard_raises_on_unauthorized_name`, and the registry-parity test to assert the
  implementation derives the full `AGENT_CHILD` set directly and forwards only values present in
  input. Remove or rewrite the 20-line design comment above `_REQUIRED_AGENT_ENV_KEYS` so the
  module documents the registry-only projection rather than a deleted required-key split. Add an
  operator-verifier test that passes no Optimus variables, asserts the parent opens
  `redis://127.0.0.1:6379/0`, and asserts the spawned child environment still contains no
  `OPTIMUS_*` name. Add a Plan 11.5 helper test that the empty projection is accepted.
  Fold-in (operator+Claude ruling): classify and delete dead
  `bootstrap._DEFAULT_REDIS_URL_HINT` with a RED absence test.

- [x] **Step 2: Run RED selectors.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_acp_subprocess_env.py tests/integration/release/test_verify_live_agent_cli.py tests/unit/tools/test_run_plan115_acpx_cost_obs_evidence.py -q
  ```

  Expected: failures identify the three-key loop, missing-URL error, and verifier's direct Redis
  indexing; existing secret-exclusion tests remain green.
  Observed RED (with bootstrap fold-in): 6 failed, 46 passed — empty env / registry / verifier
  KeyError / plan115 empty / bootstrap dead constant.

- [x] **Step 3: Implement the minimal registry projection.**

  The core loop is:

  ```python
  source = dict(operator_environ or os.environ)
  env = {
      name: value.strip()
      for name in sorted(_agent_child_registry_names())
      if (value := source.get(name, "")).strip()
  }
  for name in _SYSTEM_ENV_KEYS:
      if value := source.get(name, "").strip():
          env[name] = value
  _assert_no_provider_or_gateway_secrets(env)
  return env
  ```

  Remove `_REQUIRED_AGENT_ENV_KEYS`, `_optional_agent_env_keys`,
  `_assert_agent_env_keys_are_registry_authorized`, and `_missing_env_message`. Do not call
  `apply_local_defaults` or keyring from this module.

  In `run_operator_live_session`, build a parent-only view with existing
  `apply_local_defaults(environ, config_root=config.workspace_root, resolved_shared_secret=None)`
  to obtain its Redis URL, but call `build_acp_subprocess_env` with the original `environ`.
  Do not add the resolved view to the subprocess environment.
  Also delete dead `bootstrap._DEFAULT_REDIS_URL_HINT`.

- [x] **Step 4: Run focused green and secret-boundary tests.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_acp_subprocess_env.py tests/integration/release/test_verify_live_agent_cli.py tests/unit/tools/test_run_plan115_acpx_cost_obs_evidence.py -q
  ```

  Expected: all pass; empty input stays empty; full registry input projects exactly; provider,
  Gateway-only, Python-path, and unrelated ambient variables remain absent.
  Observed GREEN (plus bootstrap unit): `52 passed`. Child-key set for full registry input:
  `OPTIMUS_AGENT_MODEL`, `OPTIMUS_API_KEY`, `OPTIMUS_GATEWAY_URL`, `OPTIMUS_LIVE_MAX_COST_USD`,
  `OPTIMUS_MAX_PLANNING_TURNS`, `OPTIMUS_REDIS_URL`, plus `PATH`.

- [x] **Step 5: Record checkpoint; commit only with separate approval.**

  Record RED/GREEN output and the exact child-key set. If authorized, commit only these Task 1
  paths with subject `fix(acp): honor zero-env child startup contract`.
  Commit authorized by Claude review + operator; seven Task 1 paths committed.
### Task 2: Fail closed on wrong Redis ownership without changing the default port

**Files:**

- Modify: `src/optimus/acp/local_infra.py`
- Modify: `src/optimus/acp/__main__.py`
- Modify: `tests/unit/acp/test_local_infra.py`
- Modify: `tests/unit/acp/test_main_wiring.py`

**Interfaces:**

- Produces:

  ```python
  @dataclass(frozen=True)
  class LocalInfrastructureError(Exception):
      code: str
      user_message: str
  ```

- `ensure_local_redis(redis_url: str, *, log: Callable[[str], None]) -> None` keeps its public
  signature but raises the typed error only when Docker reports a different container owning the
  established default port; native/no-owner listeners remain eligible for functional preflight.
- Task 3 reuses the Docker identity helpers for Phoenix.

- [x] **Step 1: Write RED ownership and non-destruction tests.**

  Add tests for:

  - reachable default 6379 owned by `optimus-redis` / any image returns normally and leaves image
    identity plus TimeSeries capability to evidence/preflight;
  - reachable default 6379 owned by `optimus-plan112-redis` raises
    `REDIS_PORT_CONFLICT` and names both the port and observed owner;
  - reachable default with Docker missing/unreachable or with no Docker port owner logs the native
    operator-managed disposition and proceeds to real preflight;
  - a free default port still creates/starts only `optimus-redis` from `redis:8`;
  - a reachable explicitly configured non-default URL remains operator-owned and returns for real
    preflight validation;
  - no command contains `stop`, `rm`, `rename`, or `update` for an unrelated name;
  - `main()` prints `optimus-agent: <message>` and exits 2 before Gateway/agent startup.

- [x] **Step 2: Run RED selectors.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_local_infra.py tests/unit/acp/test_main_wiring.py -q
  ```

  Expected: new conflict tests fail because current code returns on any reachable TCP listener and
  has no typed error.
  Observed RED: `6 failed, 60 passed`.

- [x] **Step 3: Implement default-port owner/image inspection.**

  Add bounded Docker helpers using argument arrays and `shell=False`:

  ```python
  docker ps --filter publish=6379 --format "{{.Names}}\t{{.Image}}"
  docker inspect --format "{{.Config.Image}}" optimus-redis
  ```

  Parse exact tab-separated name/image fields; do not use substring identity. Apply the strict
  ownership rule only when the normalized URL is the established default and Docker reports a
  running port owner. If `docker ps` reports no owner, or Docker cannot be queried, preserve the
  reachable-listener behavior and emit a safe native/operator-managed diagnostic. Preserve the
  existing Docker availability checks for an unbound port, named-container create/start, readiness
  wait, and subsequent real TimeSeries preflight. Record the configured image on the named
  container, but do not reject a named alternate image before the capability check.

- [x] **Step 4: Catch the typed failure after authorization and before later side effects.**

  Catch `LocalInfrastructureError` around Redis startup in both check-config and serving paths,
  print its safe `user_message` with the existing `optimus-agent:` prefix, return exit 2, and never
  start Gateway or build the agent server after the conflict.

- [x] **Step 5: Run focused green.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_local_infra.py tests/unit/acp/test_main_wiring.py tests/unit/acp/test_preflight.py -q
  ```

  Expected: wrong-container ownership/non-destruction tests, native Redis escape-path tests, and
  existing TimeSeries fail-closed tests pass.
  Observed GREEN: `74 passed`; Ruff clean on Task 2 paths.

- [x] **Step 6: Record checkpoint; commit only with separate approval.**

  If authorized, commit Task 2 paths with subject
  `fix(acp): reject ambiguous default Redis ownership`.
  Commit authorized by Claude review + operator.

### Task 3: Add optional Phoenix to the authorized session-bound auto-start path

**Files:**

- Modify: `src/optimus/acp/local_infra.py`
- Modify: `src/optimus/acp/__main__.py`
- Modify: `tools/run_plan115_acpx_cost_obs_evidence.py`
- Modify: `tests/unit/acp/test_local_infra.py`
- Modify: `tests/unit/acp/test_main_wiring.py`
- Modify: `tests/unit/tools/test_run_plan115_acpx_cost_obs_evidence.py`

**Interfaces:**

- Produces:

  ```python
  LOCAL_PHOENIX_BASE_URL = "http://127.0.0.1:6006"
  LOCAL_PHOENIX_OTLP_ENDPOINT = "http://127.0.0.1:6006/v1/traces"

  def ensure_local_phoenix(
      *, log: Callable[[str], None] = _noop_log
  ) -> str:
      """Return the fixed OTLP endpoint after named-container health succeeds."""
  ```

- Extends `ensure_local_gateway(..., otlp_endpoint: str | None = None)`; a non-`None` value is
  inserted only into the Gateway child as `OTEL_EXPORTER_OTLP_ENDPOINT`.
- Extends `build_agent_invocation(..., with_local_phoenix: bool = False) -> str`; the generic
  builder remains optional, while the Plan 11.5 cost-observability evidence tool passes
  `with_local_phoenix=True` explicitly.

- [x] **Step 1: Write RED Phoenix lifecycle and boundary tests.**

  Add tests asserting:

  - parser rejects `--with-local-phoenix --no-auto-start`;
  - parser rejects `--check-config --with-local-phoenix` without `--strict`;
  - no Phoenix side effect occurs before authorization, audit, and workspace revalidation;
  - missing named container runs exactly
    `docker run -d --name optimus-phoenix -p 127.0.0.1:6006:6006 arizephoenix/phoenix:latest`;
  - an existing stopped matching container is started, while wrong owner/image raises a typed
    conflict and no unrelated container is mutated;
  - readiness polls `http://127.0.0.1:6006/healthz` with a bounded timeout;
  - Gateway child receives the exact OTLP endpoint when enabled;
  - agent child/environment never receives `OTEL_EXPORTER_OTLP_ENDPOINT`;
  - strict check-config starts Redis -> Phoenix -> Gateway -> preflight and always stops its Gateway;
  - normal serve startup uses the same order and existing Gateway cleanup;
  - the generic Plan 11.5 external-`acpx` invocation remains Phoenix-off by default, while its
    cost-observability capture opts in explicitly and its environment remains zero-Optimus when
    the shell is empty.

- [x] **Step 2: Run RED selectors.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_local_infra.py tests/unit/acp/test_main_wiring.py tests/unit/acp/test_acp_subprocess_env.py tests/unit/tools/test_run_plan115_acpx_cost_obs_evidence.py -q
  ```

  Expected: failures identify the missing agent option, Phoenix helper, endpoint argument, strict
  check-config Gateway startup, and cost-observability invocation flag.
  Observed RED: `13 failed, 102 passed`.

- [x] **Step 3: Implement Phoenix in the existing lifecycle.**

  Reuse Task 2's exact owner/image helpers. Health-check with Python stdlib HTTP only; no Phoenix
  dependency. The enabled `optimus-agent` startup sequence after authorization is:

  ```text
  ensure_local_redis
    -> ensure_local_phoenix (only when requested)
    -> ensure_local_gateway(otlp_endpoint=returned_endpoint)
    -> strict preflight or ACP serve
    -> stop only the Gateway process owned by this invocation
  ```

  Keep Redis and Phoenix named containers running for reuse. Do not auto-remove them, pull images
  explicitly, or send the endpoint through `agent_environ`.

- [x] **Step 4: Share strict check-config and serving cleanup.**

  Ensure `--check-config --strict` can auto-start the Gateway instead of requiring a separate
  manual launcher. Wrap Gateway lifetime in `try/finally` for both strict check-config and serving.
  Non-strict check-config retains its Redis-only behavior unless Phoenix was explicitly requested.

- [x] **Step 5: Run focused green and one-key boundary tests.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_local_infra.py tests/unit/acp/test_main_wiring.py tests/unit/acp/test_launch_approval_cli.py tests/unit/acp/test_acp_subprocess_env.py tests/unit/tools/test_run_plan115_acpx_cost_obs_evidence.py tests/unit/tools/test_plan115_docs.py -q
  ```

  Expected: all pass; `OTEL_EXPORTER_OTLP_ENDPOINT` appears only in Gateway-child construction and
  the Gateway-side living example, never in agent child output.
  Observed GREEN: `158 passed, 6 skipped`; Ruff clean on Task 3 paths.

- [x] **Step 6: Record checkpoint; commit only with separate approval.**

  If authorized, commit Task 3 paths with subject
  `feat(acp): auto-start local Phoenix for live evidence`.

### Task 4: Retire the misleading wrappers and preserve the persistent Gateway ceremony

**Files:**

- Modify: `src/optimus/acp/launch_approval_cli.py`
- Modify: `tests/unit/acp/test_launch_approval_cli.py`
- Delete: `tools/run_local_gateway.sh`
- Delete: `tools/run_local_gateway.ps1`
- Delete: `tests/unit/tools/test_run_local_gateway_scripts.py`

**Interfaces:**

- Preserves `optimus-trust setup-credentials`, `approve`, `inspect`, `revoke`, `rotate-key`,
  `run`, and the foreground `run-gateway` ceremony.
- Extends `run-gateway` with the Task 3 `--with-local-phoenix` option and keeps its blocking
  `subprocess.run`/manifest/TTY behavior.
- Deletes only the misleading `tools/run_local_gateway.sh` / `.ps1` wrappers and their dedicated
  test file.

- [x] **Step 1: Write RED persistence and wrapper-retirement tests.**

  Add a parser test for the new persistent-mode option:

  ```python
  def test_run_gateway_accepts_local_phoenix_option():
      args = parse_args(["run-gateway", "--with-local-phoenix"])
      assert args.command == "run-gateway"
      assert args.with_local_phoenix is True
  ```

  Add a non-TTY-isolated unit assertion that `_cmd_run_gateway` invokes the blocking Gateway child
  and does not return until the mocked `subprocess.run` completes. Keep the existing provider,
  shared-secret, safe-display, manifest, and TTY tests. Delete wrapper-specific tests only after
  the replacement runbook/presence test owns their absence.

- [x] **Step 2: Run RED selector.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_launch_approval_cli.py -q
  ```

  Expected: the new option test fails because the current `run-gateway` parser has no Phoenix
  option; existing persistent-command tests remain green.

- [x] **Step 3: Extend the existing ceremony and delete only wrappers.**

  Add `--with-local-phoenix` to the existing `run-gateway` parser and thread it through
  `_cmd_run_gateway_default` and `_cmd_run_gateway`. After the existing TTY/config/credential
  checks and before the blocking child, call Task 3's Phoenix helper and overlay its returned
  endpoint in the Gateway child environment. Keep the HMAC manifest, safe configuration snapshot,
  `subprocess.run`, and foreground lifetime unchanged. Delete both wrapper scripts and
  `tests/unit/tools/test_run_local_gateway_scripts.py`; do not add aliases, deprecation shims, or
  renamed launch scripts.

- [x] **Step 4: Run focused green and wrapper retirement audit.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_launch_approval_cli.py -q
  rg -n "run_local_gateway" src tools tests README.md .env.example .env.gateway.example
  ```

  Expected: CLI tests pass; `run-gateway` remains present in its parser/implementation/tests, and
  `run_local_gateway` has no active hit. Documentation for the retained ceremony is handled in
  Task 5 rather than hidden here.

- [x] **Step 5: Record checkpoint; commit only with separate approval.**

  If authorized, commit Task 4 paths with subject
  `refactor(acp): retire misleading local Gateway wrappers`.

### Task 5: Publish and mechanically enforce the single operator runbook

**Files:**

- Create:
  `docs/superpowers/plans/2026-07-29-plan-11-6-local-live-dependencies-operator-runbook.md`
- Create: `tests/unit/tools/test_plan116_local_startup_docs.py`
- Modify: `README.md`
- Modify: `.env.gateway.example`
- Modify: `src/optimus/acp/preflight.py`
- Modify: `tests/integration/telemetry/test_phoenix_live.py`

**Interfaces:**

- Produces one operator sequence: keychain setup and approval, then
  `optimus-trust --workspace-root <path> run-gateway --with-local-phoenix` for the persistent
  Gateway/Phoenix terminal, with `optimus-agent --no-auto-start` or the external `acpx` client in
  the consumer terminal. The session-bound `optimus-agent --check-config --strict` smoke remains
  documented as the bounded auto-start verification path.
- Produces a presence/retirement test that rejects competing active instructions.

- [x] **Step 1: Write RED presence and retirement assertions.**

  The new test reads active code/docs and asserts:

  ```python
  assert "optimus-trust setup-credentials" in runbook
  assert "optimus-trust --workspace-root" in runbook
  assert "optimus-agent --workspace-root" in runbook
  assert "run-gateway --with-local-phoenix" in runbook
  assert "--check-config --strict" in runbook
  assert "--with-local-phoenix" in runbook
  assert "REDIS_PORT_CONFLICT" in runbook
  assert "docker ps --filter publish=6379" in runbook
  assert not Path("tools/run_local_gateway.sh").exists()
  assert not Path("tools/run_local_gateway.ps1").exists()
  ```

  Also assert active README/preflight/Phoenix-test guidance contains no
  `docker run ... redis`, `docker run ... arizephoenix`, or `run_local_gateway`, and that
  `.env.example` contains no OTLP/Phoenix name. The retained `run-gateway` ceremony must appear
  only through the runbook's single documented sequence and its own CLI implementation/tests.

- [x] **Step 2: Run the docs test and verify RED.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_plan116_local_startup_docs.py tests/unit/tools/test_plan115_docs.py -q
  ```

  Expected: missing runbook and stale active launcher hints fail.

- [x] **Step 3: Write the operator runbook.**

  Use the Plan 9.6 Phase C structure and include:

  1. checkout/PATH provenance;
  2. zero-Optimus-shell precondition and no `.env` requirement;
  3. `optimus-trust setup-credentials`;
  4. durable workspace approval;
  5. the bounded session-bound Redis+Gateway strict check-config smoke;
  6. the persistent `optimus-trust --workspace-root <path> run-gateway --with-local-phoenix`
     terminal, including its foreground lifetime and the `optimus-agent --no-auto-start`/
     external-`acpx` consumer terminal;
  7. real `acpx`, Redis, Gateway, and Phoenix evidence commands;
  8. expected named containers/images, health URLs, and the distinction between persistent
     `run-gateway` lifetime and session-bound agent cleanup;
  9. default-port conflict diagnosis using `docker ps --filter publish=6379`, including the native
     Redis/no-Docker escape path;
  10. non-destructive recovery choices: the operator may stop/reconfigure the unrelated project
      themselves or explicitly configure a custom Redis URL and re-approve;
  11. restore steps for any shell-only test variables.

  State explicitly that Optimus never stops or deletes the conflicting container.

- [x] **Step 4: Repoint living guidance.**

  Replace competing README commands with one concise runbook link and summary. Keep the retained
  `run-gateway` command only in that runbook and its CLI help/tests. Update
  `.env.gateway.example` to state that local Phoenix mode projects the displayed loopback OTLP
  reference only to the Gateway child; it is never exported into the agent shell. Replace
  preflight and Phoenix-test inline Docker commands with the runbook path and dependency name.

- [x] **Step 5: Run docs/presence green and active-surface audit.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_plan116_local_startup_docs.py tests/unit/tools/test_plan115_docs.py -q
  rg -n "run_local_gateway|docker run.*(redis|arizephoenix)" README.md .env.example .env.gateway.example src tests tools
  git diff --check
  ```

  Expected: tests pass; no competing active launcher instruction remains. Any `rg` hit must be a
  test assertion proving absence or an exact command generated inside the single production
  auto-start implementation, not operator guidance. `run-gateway` may appear only in the retained
  CLI/tests and the runbook sequence.

- [x] **Step 6: Record checkpoint; commit only with separate approval.**

  If authorized, commit Task 5 paths with subject
  `docs: establish one local dependency startup runbook`.

### Task 6: Prove the runbook with real dependencies and close custody

**Files:**

- Create: `reports/plan-11-6-local-startup-live-evidence.md`
- Create: `reports/plan-11-6-local-startup-acpx-evidence.md`
- Modify after all evidence passes:
  `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`
- Update only as gitignored:
  `docs/superpowers/reviews/plan-11-6-review-checkpoints.md`

**Produces:** Named real-dependency evidence that the runbook works from an empty Optimus shell,
plus final closure of `P11.5-FU-2`. No fake may substitute for a named dependency.

- [ ] **Step 1: Run all affected non-live tests.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_acp_subprocess_env.py tests/unit/acp/test_local_infra.py tests/unit/acp/test_launch_approval_cli.py tests/unit/acp/test_main_wiring.py tests/unit/acp/test_preflight.py tests/unit/tools/test_run_plan115_acpx_cost_obs_evidence.py tests/unit/tools/test_plan115_docs.py tests/unit/tools/test_plan116_local_startup_docs.py tests/integration/release/test_verify_live_agent_cli.py -q
  ```

  Expected: all pass with no Docker, keyring, Gateway, Phoenix, or `acpx` fake presented as live
  evidence.

- [ ] **Step 2: Execute the runbook's zero-env strict smoke.**

  In a fresh shell, record and clear inherited `OPTIMUS_*` names for the command scope, confirm the
  required durable approval exists, then run exactly:

  ```powershell
  optimus-agent --workspace-root . --check-config --strict --with-local-phoenix
  ```

  Expected: exit 0; Redis and Phoenix are real named containers with correct image identities and
  health; the real Gateway authenticates; no provider key or OTLP endpoint appears in agent output.
  If approval/credentials are absent, perform only the runbook's setup/approve steps and rerun.

- [ ] **Step 3: Record dependency identities and collision behavior.**

  ```powershell
  docker ps --filter "name=^/optimus-redis$" --format "{{.Names}}`t{{.Image}}`t{{.Ports}}"
  docker ps --filter "name=^/optimus-phoenix$" --format "{{.Names}}`t{{.Image}}`t{{.Ports}}"
  docker inspect --format "{{.Name}}`t{{.Config.Image}}`t{{.Image}}" optimus-redis optimus-phoenix
  ```

  Record resolved image IDs/digests. Exercise the wrong-owner branch only with an isolated,
  reviewer-approved test port/container fixture; never stop or repurpose an unrelated live
  container. Expected: typed failure names the conflict and no later Gateway/agent side effect
  occurs.

- [ ] **Step 4: Run real Redis, Phoenix, Gateway, and independent ACP evidence.**

  Keep the Step 2 zero-env smoke and the external-`acpx` capture as the proof of the consolidated
  launcher contract. Before the pre-existing direct-client live tiers, open Terminal A and keep
  this persistent Gateway ceremony running in the foreground:

  ```powershell
  optimus-trust --workspace-root . run-gateway --with-local-phoenix
  ```

  Run the tests from Terminal B while Terminal A remains alive; stop Terminal A with Ctrl-C only
  after all Gateway/acpx/direct-client evidence is collected. For an independently authored
  `acpx` invocation that consumes the persistent Gateway, use an agent command containing
  `optimus-agent --no-auto-start`; the Plan 11.5 cost-observability tool remains a separate
  consolidated-launcher exercise and explicitly opts into its own Phoenix mode. Supply the
  direct-client fixtures' already-defined variables in Terminal B (`OPTIMUS_REDIS_URL`, one-key
  `OPTIMUS_GATEWAY_URL`/`OPTIMUS_API_KEY`, and Phoenix query/OTLP values) exactly as their fixtures
  require. Those explicit direct-test inputs are regression-fixture configuration, not proof that
  the agent needs shell variables. The retained foreground ceremony is what makes
  `tests/integration/gateway/test_gateway_live.py`'s pre-existing external-Gateway contract
  executable; do not replace it with a fake or with the session-bound process from Step 2. Then
  run:

  ```powershell
  uv run --frozen pytest tests/integration/agent/test_redis_live_agent.py -m requires_redis -q
  uv run --frozen pytest tests/integration/telemetry/test_phoenix_live.py -m requires_phoenix -q
  uv run --frozen pytest tests/integration/gateway/test_gateway_live.py -m requires_gateway -q
  uv run --frozen pytest tests/integration/optimus_gateway/test_gateway_live_smoke.py -m requires_live_gateway -q
  uv run --frozen python tools/run_plan115_acpx_cost_obs_evidence.py --workspace . --task "Return a one-sentence cost-observability smoke result." --report reports/plan-11-6-local-startup-acpx-evidence.md
  ```

  Expected: every selected real tier executes and passes (a skip/deselection is not evidence);
  external `acpx` separately drives the real ACP process with no shell-required Optimus variables;
  Phoenix receives real OTLP; the Gateway remains the only provider/OTLP owner. Record which
  commands are consolidated-launcher evidence and which are explicit direct-client regression
  evidence, including the persistent `run-gateway` terminal and its shutdown time.

- [ ] **Step 5: Reproduce the platform-sensitive contract on WSL2.**

  From the Windows host, run the focused POSIX projection in a real Ubuntu WSL2 environment:

  ```powershell
  wsl.exe -d Ubuntu-24.04 -- bash -lc 'cd /mnt/d/Projects/Development/Python/optimus-cost-agent-wt-codex && uv sync --frozen --extra dev && env -i PATH="$PATH" uv run --frozen pytest tests/unit/acp/test_acp_subprocess_env.py tests/unit/acp/test_local_infra.py -q && command -v acpx && env -i PATH="$PWD/.venv/bin:$PATH" .venv/bin/python tools/run_plan115_acpx_cost_obs_evidence.py --workspace . --task "Return a one-sentence POSIX zero-env smoke result." --report /tmp/plan-11-6-local-startup-acpx-wsl-evidence.md'
  ```

  The first `env -i` invocation deliberately preserves only `PATH` for the focused tests. The
  second invocation is the real external-`acpx` path with a PATH-only environment reaching both
  the evidence Python process and its `acpx` child; it must not add `HOME`,
  `DBUS_SESSION_BUS_ADDRESS`, or any `OPTIMUS_*` name. Record the distro, commit, external `acpx`
  identity, exit codes, and captured output in the live-evidence report. If the PATH-only smoke
  cannot authenticate because the Linux SecretStorage/D-Bus backend is unavailable, record that
  exact failure as an unverified POSIX residual risk and do not claim Linux zero-env evidence;
  Windows success does not discharge that gap.

- [ ] **Step 6: Run full fitness and retirement gates.**

  ```powershell
  uv run --frozen pytest -q
  uv run --frozen pytest --cov=src/optimus --cov=src/optimus_gateway --cov=src/optimus_security --cov-report=term-missing --cov-fail-under=80
  uv run --frozen ruff check .
  rg -n "run_local_gateway|docker run.*(redis|arizephoenix)" README.md .env.example .env.gateway.example src tests tools
  git diff --check
  git status --short --branch
  ```

  Expected: default suite and coverage pass; coverage is at least 80%; Ruff/diff hygiene are clean;
  retirement hits are limited to absence assertions and the exact auto-start Docker argument arrays
  in production plus their focused expected-command tests; `run-gateway` is present only in its
  retained CLI/tests/runbook sequence, and no launcher wrapper or stale inline operator hint exists.

- [ ] **Step 7: Write evidence and close the backlog item.**

  Write `reports/plan-11-6-local-startup-live-evidence.md` with plan/approval digests, commands,
  exit codes, test counts, coverage, Ruff, real dependency names/images/digests, Windows and WSL2
  zero-env results (or the explicitly recorded POSIX residual risk), secret/endpoint boundary
  proof, external-`acpx` identity, conflict disposition, and changed-file scope. Then update the
  existing `P11.5-FU-2` status from promoted to closed with implementation commit/PR and this
  evidence link. Leave the full entry/history in place.

- [ ] **Step 8: Final reviewer/operator handoff.**

  Update the checkpoint log, present the complete on-disk diff and evidence, and stop for review.
  Do not push, create a PR, merge, delete branches/containers, or claim the Phase 1 agent is
  "working" outside the separate Plan 9.6 sign-off authority.

## Definition of Done

- Plan 11.6 is reviewed by Claude, approved by the operator, SHA-256 pinned, and implemented from
  a branch based directly on current `origin/main`.
- `build_acp_subprocess_env` accepts an empty Optimus environment, projects only present
  registry-authorized agent names plus safe system names, and does not inject defaults or resolve
  credentials.
- Parent verification can use the existing Redis default without adding it to the child snapshot;
  direct and evidence-driven zero-env launches therefore share authorization behavior.
- The documented live-run sequence uses `optimus-agent` for session-bound Redis+Gateway auto-start
  and the retained foreground `optimus-trust run-gateway` ceremony for a persistent Gateway;
  `--with-local-phoenix` is an explicit opt-in on either existing entrypoint.
- Both `tools/run_local_gateway.*` wrappers and their wrapper-specific test/docs are removed, with
  no alias or replacement launcher family; the persistent `run-gateway` command remains available
  and its role is explicit in the runbook.
- Default Redis 6379 accepts a Docker-proven `optimus-redis` owner or a reachable native/no-owner
  Redis, and still passes real TimeSeries preflight. A different Docker owner is a typed,
  non-destructive conflict; custom URLs remain explicit operator choices.
- Local Phoenix uses named container `optimus-phoenix`, records the resolved image identity, passes
  real health/OTLP evidence, and adds no Phoenix SDK or credential.
- `OTEL_EXPORTER_OTLP_ENDPOINT` reaches only the Gateway child when local Phoenix mode is enabled;
  it is absent from agent environment/config and one-key boundaries remain intact.
- The short Plan 11.6 operator runbook is the single active source of truth. README, examples,
  preflight errors, and live tests link to it instead of carrying alternate Docker/launcher steps.
- Real Redis, Gateway, Phoenix, and external-`acpx` evidence follows the runbook from an empty
  Optimus shell; fake-only evidence cannot close the plan.
- Affected tests, default tests, coverage at or above 80%, Ruff, retirement/presence audit, and
  diff/status hygiene pass.
- `P11.5-FU-2` retains its history, is promoted to Plan 11.6 when this plan exists, and is closed
  only after the named implementation/live evidence exists.
- `P11-FU-8`, `P11.5-FU-1`, frozen prior plans, and all other explicit exceptions remain unchanged.
