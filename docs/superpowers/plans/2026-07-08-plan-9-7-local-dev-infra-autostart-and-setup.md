# Plan 9.7: Local Dev Infra Auto-Start and Keychain-Based Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. This plan does not touch Plan 9.6's live-verification
> scope — see "Relationship to Plan 9.6" below.

**Goal:** `optimus-agent` becomes responsible for ensuring its own local dependencies (a
TimeSeries-capable Redis, the local Optimus Gateway process) are running when it starts, instead
of requiring an operator to hand-edit two `.env` files and manually run `docker run` and
`tools/run_local_gateway.sh` in separate shells first. First-time secret configuration becomes an
optional one-time `optimus-agent --setup` wizard that stores the provider API key and a
generated shared secret in the Windows credential store via `keyring`, while `.env`/
`.env.gateway` remain supported as a transitional fallback.

**Status:** Drafted 2026-07-08, awaiting reviewer approval. Do not begin implementation tasks
until this plan is reviewed and approved.

**Architecture:** Two new modules on the agent side (`local_gateway_secrets.py`,
`local_infra.py`), wired into the existing `optimus.acp.__main__` entrypoint and
`optimus.acp.preflight` message text. No changes to `src/optimus_gateway/` itself — the gateway
service continues to read its own process environment exactly as today
(`GatewayServiceConfig.from_env()`); `optimus-agent` only becomes responsible for constructing
that environment and spawning/tracking the process.

**Tech Stack:** Python >=3.14, existing `optimus.acp` package, stdlib `subprocess`, `socket`,
`shutil`, `secrets`, `getpass`, `argparse`; new runtime dependency `keyring` (checked against
PyPI metadata for `keyring==25.7.0` on 2026-07-08: Windows backend pulls in only
`pywin32-ctypes`, a lightweight ctypes shim, not full `pywin32`). Pin `keyring>=25,<26` in
`pyproject.toml` rather than an open-ended `>=25`, since this claim is about a specific checked
release, not a guarantee that holds for every future 25.x/26.x release — re-verify the dependency
chain via PyPI metadata before widening the pin.

---

## Relationship to Plan 9.6

Plan 9.6 (`docs/superpowers/plans/2026-07-07-plan-9-6-live-verification-and-lld-alignment.md`)
owns live-verification proof that the already-built agent works against real dependencies.
This plan is orthogonal: it changes *how those dependencies get started before a session*, never
whether the agent's behavior against them is proven, and it must not weaken any preflight
fail-closed check Plan 9.6 established. Auto-start only removes manual setup steps that run
*before* those checks; every existing check still runs, still fails closed, and still exits
non-zero with an operator-actionable message if the dependency isn't actually up afterward.
Plan 9.6's live test tiers, evidence artifacts, and sign-off gate are unaffected.

## Relationship to Plan 9.8 (Tracked, Not Yet Scheduled)

During review (2026-07-08) the operator raised a separate, larger architectural gap: the
client-side one-key contract is already shaped for this — `src/optimus/evidence/acquisition.py:88`
posts to `/v1/tools/web/search` and `src/optimus/telemetry/observability.py:18` posts to
`/v1/observability/traces`, both through `GatewayClient`, the same gateway-only seam model calls
already use — but `src/optimus_gateway/server.py` currently only implements `/v1/responses`, so
those calls would 404 against the local gateway today. The gap is not in the agent-side contract;
it's that the local gateway stub hasn't grown routes/upstream adapters for web search or
observability export yet, and any real web-search or observability provider key (e.g. Tavily,
LangSmith) would need to live gateway-side once those routes exist. That is a
gateway-capability-surface redesign (new routes, upstream adapters, a secret taxonomy and
usage/cost normalization for non-model calls, fail-closed semantics for missing integration keys),
not a local-startup-ergonomics change, and is being tracked separately as **Plan 9.8: Unified
Gateway Capabilities
Broker** — out of scope for this plan and not designed here. The only amendment Plan 9.7 makes
for forward compatibility: `local_gateway_secrets.py`'s keychain schema (Task 1) must not
hardcode an assumption that the only secret category is "model provider key" — see Task 1's
storage-key naming note.

## Source Anchors

- Conversation 2026-07-08: operator flagged that starting Redis/Docker and the local gateway is
  manual ceremony today ("things like starting the gateway and Docker should be handled by the
  Python executable on start").
- `docs/superpowers/plans/2026-07-07-local-optimus-gateway-service.md`: defines the local gateway
  service (`optimus_gateway`), its wire contract, and provider configuration. This plan must not
  change that contract or its config surface — only how the process gets started.
- `src/optimus/acp/preflight.py`: existing fail-closed checks this plan must continue to satisfy,
  never bypass.
- `src/optimus/acp/subprocess_env.py` and `tests/integration/optimus_gateway/gateway_env.py`:
  existing precedent for building an isolated child-process env and loading `.env.gateway`
  without touching the parent process's `os.environ` — this plan follows the same shape for a
  new production (not test-only) use.
- `AGENTS.md`: "Preserve the one-key model: gateway adapters own vendor keys..."; "Local runtime
  credentials are limited to `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`". This plan's
  provider-key handling (Task 2) is designed to satisfy this: `optimus-agent` only ever
  transiently holds the provider key in memory to construct a spawned child's environment, never
  as its own operating credential, mirroring what a human running `tools/run_local_gateway.sh`
  already does today.
- `src/optimus/config/gateway.py:85`: `OptimusGatewaySettings.from_env()` defaults
  `production_mode=True` when `OPTIMUS_PRODUCTION_MODE` is unset, and `validate_trusted_gateway()`
  (line 100) only trusts a loopback `http://` origin when `production_mode` is `False`. A
  zero-env-var launch that defaults `OPTIMUS_GATEWAY_URL` to `http://127.0.0.1:8765` without also
  defaulting `OPTIMUS_PRODUCTION_MODE=false` raises `ValueError` before preflight ever runs. Found
  during 2026-07-08 review; addressed in Task 2.
- `src/optimus/agent/defaults.py:5` / `src/optimus_gateway/model_mapping.py`: `DEFAULT_AGENT_MODEL
  = "glm-5.2"`, but `PROVIDER_MODEL_ALIASES` and `is_plausible_passthrough()` have no entry or
  passthrough match for `"glm-5.2"` under any of the three local providers (anthropic/openrouter/
  openai) — every local-gateway planning call would raise `unsupported gateway model: glm-5.2`.
  README already tells operators to set `OPTIMUS_AGENT_MODEL=claude-haiku` for local dev
  (`README.md:256`). Found during 2026-07-08 review; addressed in Task 2.
- `src/optimus_gateway/models.py:45`: `GatewayServiceConfig.from_env()` reads `ANTHROPIC_API_KEY`
  when `provider == "anthropic"`, and `OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY` otherwise — the
  spawned gateway child's env must set the *correct* variable name for the resolved provider, not
  a single generic name. Found during 2026-07-08 review; addressed in Task 1/Task 2.

## Confirmed Design Decisions (from 2026-07-08 planning discussion)

1. **Windows-only for now.** Phase 2 is a planned Rust rewrite; Linux/WSL keyring-backend gaps
   (SecretStorage/jeepney require a running Secret Service daemon, not guaranteed headless) are
   explicitly out of scope for this plan.
2. **Gateway process lifecycle is tied to `optimus-agent`'s own serving session** — spawned as a
   child, stopped when `optimus-agent` exits. Not a persistent daemon reused indefinitely across
   sessions. Redis is the opposite: ensured-running, never stopped by us, since it holds real
   state (plan approvals, telemetry). Note the manual operator runbook's `docker run --rm -d`
   example is for a one-off session where the operator wants full cleanup on stop; the container
   Plan 9.7 manages automatically (Task 2) is a different, persistent-by-design instance and
   intentionally omits `--rm` so `docker start` can restart it by name across launches — see Task
   2 for the full reasoning, this item only states the ownership/lifecycle split, not the flag.
3. **Provider-key boundary:** `optimus-agent` may transiently hold the provider API key in memory
   only to construct the spawned gateway child's environment dict — never in its own
   `os.environ`, never used to call a model itself.
4. **`.env`/`.env.gateway` remain supported now but are transitional**, not permanent; keyring is
   the intended long-term default. Resolution precedence per secret: explicit env var →
   `.env.gateway` file → keyring.
5. **Auto-start only ever applies to the loopback local-gateway shape.** A real hosted
   `OPTIMUS_GATEWAY_URL` is never touched — we cannot start someone else's service and must not
   try.

## Scope

### In Scope

- `src/optimus/acp/local_gateway_secrets.py`: precedence-chain secret resolution (provider name,
  provider API key, shared secret) and an interactive `--setup` wizard storing values in the OS
  keychain via `keyring`.
- `src/optimus/acp/local_infra.py`: `apply_local_defaults()` (fills `OPTIMUS_REDIS_URL` /
  `OPTIMUS_GATEWAY_URL` / `OPTIMUS_API_KEY` / `OPTIMUS_PRODUCTION_MODE` / `OPTIMUS_AGENT_MODEL`
  with local defaults when unset and the resolved gateway URL is loopback), `ensure_local_redis()`
  (Docker auto-start/reuse, no `--rm` so the container survives across launches),
  `ensure_local_gateway()` (spawn/track the local gateway child process).
- `src/optimus/acp/__main__.py`: new `--setup` and `--no-auto-start` flags (the latter gates both
  `ensure_local_redis` and `ensure_local_gateway` consistently, in both the real serve path and
  `--check-config`); wiring auto-start into the real serve path; wiring defaults-and-redis-only
  (no gateway spawn, ever, regardless of the flag) into `--check-config`; stopping the gateway
  child in a `finally` block, only if this process started it.
- `src/optimus/acp/preflight.py`: additive message change pointing at `optimus-agent --setup`.
- `pyproject.toml`: add `keyring>=25,<26` to `[project.dependencies]`.
- README updates: new no-`.env`-required quickstart; existing `.env`/`.env.gateway` instructions
  retained under an explicit "transitional/advanced" subsection.

### Out of Scope

- Linux/WSL keyring backend support.
- Removing `.env`/`.env.gateway` support.
- Changing `tools/run_local_gateway.sh`/`.ps1` — remain as an independent manual option for
  operators who want to run the gateway completely outside `optimus-agent`; unaffected.
- Any change to the real hosted-gateway path (`OPTIMUS_GATEWAY_URL` pointing at a non-loopback
  origin).
- Any change to Plan 9.6's live test tiers, preflight check semantics/messages beyond the one
  additive string in Task 4, or its sign-off gate.
- Auto-starting Docker Desktop itself if the daemon isn't running — fails closed with an operator
  message instead, same as today.

### Dependency Notes

- Branch from latest `main` following `CONTRIBUTING.md`.
- Preserve the one-key model on the *agent* side: `optimus-agent`'s own `os.environ` never gains
  a provider key. Only a short-lived child-process env dict (for the spawned gateway) may contain
  one, and it is never persisted or logged.
- Keep commits approval-gated; do not run `git commit` unless explicitly approved.

## File Structure

- Create: `src/optimus/acp/local_gateway_secrets.py`
- Create: `tests/unit/acp/test_local_gateway_secrets.py`
- Create: `src/optimus/acp/local_infra.py`
- Create: `tests/unit/acp/test_local_infra.py`
- Modify: `src/optimus/acp/__main__.py` — `--setup`, `--no-auto-start`, wiring.
- Modify: `tests/unit/acp/test_entrypoint.py` (or add a new integration-style test file) — flag
  and wiring behavior with fakes/spies.
- Modify: `src/optimus/acp/preflight.py` — message text.
- Modify: `tests/unit/acp/test_preflight.py` — updated substring assertion.
- Modify: `pyproject.toml` — new dependency.
- Modify: `README.md` — quickstart rewrite.

## Human Agile Sizing

Roughly 3-5 days of human development effort: Day 1 secrets module + tests, Day 2 infra module +
tests, Day 3 entrypoint wiring + tests, Day 4 docs + manual end-to-end verification, Day 5
buffer/reviewer fixes.

---

## Task 1: `local_gateway_secrets.py` — Precedence Resolution + Setup Wizard

**Files:**
- Create: `src/optimus/acp/local_gateway_secrets.py`
- Create: `tests/unit/acp/test_local_gateway_secrets.py`

**Interfaces:**
```python
@dataclass(frozen=True)
class ProviderSecrets:
    provider: str  # "openai" | "openrouter" | "anthropic"
    model_provider_api_key: str

    def as_gateway_child_env(self) -> dict[str, str]:
        """Map to the exact var name GatewayServiceConfig.from_env() reads for this provider
        (src/optimus_gateway/models.py:45): ANTHROPIC_API_KEY for anthropic, else
        OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY. Only ever sets the one name the resolved
        provider needs; never sets the other provider-key family, even if it happens to be
        present in the operator's own environment (mirrors the existing pop()-based clearing
        already done in tests/integration/optimus_gateway/gateway_env.py's
        merge_gateway_subprocess_env, promoted here to a production code path)."""

def resolve_provider_secrets(environ, *, project_root, keyring_backend=keyring) -> ProviderSecrets | None
def resolve_shared_secret(environ, *, project_root, keyring_backend=keyring) -> str | None
def run_setup_wizard(*, project_root, keyring_backend=keyring, input_fn=input, getpass_fn=getpass.getpass, print_fn=print) -> int
```

- [ ] **Step 1: Write failing tests**

```python
class FakeKeyring:
    def __init__(self):
        self._store: dict[tuple[str, str], str] = {}
    def get_password(self, service, key):
        return self._store.get((service, key))
    def set_password(self, service, key, value):
        self._store[(service, key)] = value


def test_resolve_shared_secret_prefers_env_over_dotenv_and_keyring(tmp_path):
    (tmp_path / ".env.gateway").write_text("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET=from-dotenv\n", encoding="utf-8")
    fake_keyring = FakeKeyring()
    fake_keyring.set_password("optimus-cost-agent", "local_gateway_shared_secret", "from-keyring")

    resolved = resolve_shared_secret(
        {"OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "from-env"},
        project_root=tmp_path,
        keyring_backend=fake_keyring,
    )

    assert resolved == "from-env"


def test_resolve_shared_secret_falls_back_dotenv_then_keyring(tmp_path):
    fake_keyring = FakeKeyring()
    fake_keyring.set_password("optimus-cost-agent", "local_gateway_shared_secret", "from-keyring")

    assert resolve_shared_secret({}, project_root=tmp_path, keyring_backend=fake_keyring) == "from-keyring"

    (tmp_path / ".env.gateway").write_text("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET=from-dotenv\n", encoding="utf-8")
    assert resolve_shared_secret({}, project_root=tmp_path, keyring_backend=fake_keyring) == "from-dotenv"


def test_setup_wizard_stores_provider_key_and_generated_shared_secret(tmp_path):
    fake_keyring = FakeKeyring()
    inputs = iter(["openrouter"])
    exit_code = run_setup_wizard(
        project_root=tmp_path,
        keyring_backend=fake_keyring,
        input_fn=lambda _prompt: next(inputs),
        getpass_fn=lambda _prompt: "sk-test-key",
        print_fn=lambda *_a, **_k: None,
    )

    assert exit_code == 0
    assert fake_keyring.get_password("optimus-cost-agent", "model_provider") == "openrouter"
    assert fake_keyring.get_password("optimus-cost-agent", "model_provider_api_key") == "sk-test-key"
    assert fake_keyring.get_password("optimus-cost-agent", "local_gateway_shared_secret")  # generated, non-empty


def test_setup_wizard_declines_overwrite_without_confirmation(tmp_path):
    fake_keyring = FakeKeyring()
    fake_keyring.set_password("optimus-cost-agent", "model_provider_api_key", "existing-key")
    inputs = iter(["openrouter", "n"])  # provider, then "overwrite?" = no

    exit_code = run_setup_wizard(
        project_root=tmp_path,
        keyring_backend=fake_keyring,
        input_fn=lambda _prompt: next(inputs),
        getpass_fn=lambda _prompt: "sk-new-key",
        print_fn=lambda *_a, **_k: None,
    )

    assert exit_code == 1
    assert fake_keyring.get_password("optimus-cost-agent", "model_provider_api_key") == "existing-key"


def test_resolve_provider_secrets_returns_none_when_nothing_configured(tmp_path):
    assert resolve_provider_secrets({}, project_root=tmp_path, keyring_backend=FakeKeyring()) is None


def test_provider_secrets_maps_anthropic_to_anthropic_api_key_only(tmp_path):
    secrets_ = ProviderSecrets(provider="anthropic", model_provider_api_key="sk-ant-test")

    child_env = secrets_.as_gateway_child_env()

    assert child_env == {"ANTHROPIC_API_KEY": "sk-ant-test"}
    assert "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY" not in child_env


def test_provider_secrets_maps_openrouter_to_provider_api_key_var_only(tmp_path):
    secrets_ = ProviderSecrets(provider="openrouter", model_provider_api_key="sk-or-test")

    child_env = secrets_.as_gateway_child_env()

    assert child_env == {"OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "sk-or-test"}
    assert "ANTHROPIC_API_KEY" not in child_env


def test_no_keyring_backend_available_fails_with_dotenv_pointer(tmp_path):
    class RaisingKeyring:
        def get_password(self, *a, **k):
            raise RuntimeError("no backend")
        def set_password(self, *a, **k):
            raise RuntimeError("no backend")

    messages = []
    exit_code = run_setup_wizard(
        project_root=tmp_path,
        keyring_backend=RaisingKeyring(),
        input_fn=lambda _prompt: "openrouter",
        getpass_fn=lambda _prompt: "sk-test",
        print_fn=lambda msg="", **_k: messages.append(msg),
    )

    assert exit_code == 2
    assert any(".env.gateway" in msg for msg in messages)
```

- [ ] **Step 2: Run tests, confirm failure** —
  `pytest tests/unit/acp/test_local_gateway_secrets.py -v` (module doesn't exist yet, expect
  `ImportError`/collection failure).

- [ ] **Step 3: Implement** `src/optimus/acp/local_gateway_secrets.py`:
  - A minimal `.env.gateway` line parser scoped to this file (`KEY=VALUE`, `#` comments, optional
    surrounding quotes). Do **not** add `python-dotenv` as a runtime dependency for this — it is
    dev-only today (`[project.optional-dependencies].dev`), and promoting it to a hard runtime
    dependency just for this one file is disproportionate; a ~10-line parser is sufficient and
    keeps the dependency footprint minimal, consistent with this project's existing runtime
    dependency list (`confusable-homoglyphs`, `pydantic`, `redis`).
  - `resolve_shared_secret` / `resolve_provider_secrets`: env → `.env.gateway` →
    `keyring_backend.get_password("optimus-cost-agent", <key>)`, swallowing any keyring backend
    exception as "not available" (return `None`, never raise) so a real launch always falls
    through to the existing preflight fail-closed message rather than crashing with a traceback.
  - **Keychain key naming (forward-compat with Plan 9.8, tracked separately — see "Relationship
    to Plan 9.8" above):** use `model_provider`, `model_provider_api_key`, and
    `local_gateway_shared_secret` as the three keyring key names under service
    `optimus-cost-agent` — not the bare `provider`/`provider_api_key`/`shared_secret` from the
    first draft. This is namespaced by capability (`model_*`) precisely so a future Plan 9.8 can
    add sibling keys (e.g. a web-search or observability provider's key) under the same service
    without colliding with or restructuring what Plan 9.7 already stores. No other behavior change
    — this is a naming choice only, made now while the schema doesn't exist yet.
  - `run_setup_wizard`: prompts provider via `input_fn` (default `openrouter` on empty input),
    validates against `{"openai", "openrouter", "anthropic"}`, prompts the provider API key via
    `getpass_fn`, checks existing keyring values and asks to overwrite via `input_fn` (declining
    returns exit code `1` with no changes made), generates the shared secret via
    `secrets.token_urlsafe(32)` only on first-time setup or confirmed overwrite (never
    regenerated/prompted otherwise), stores all three (`model_provider`, `model_provider_api_key`,
    `local_gateway_shared_secret`) under service name `optimus-cost-agent`, prints a plain
    confirmation via `print_fn`. Returns `2` if the keyring backend itself raises on first use,
    printing a message that names `.env.gateway` as the fallback path.
  - `ProviderSecrets.as_gateway_child_env()`: exact one-to-one mapping per provider (see
    Source Anchors: `src/optimus_gateway/models.py:45`) — never sets both key names, never
    carries over an unrelated provider-key env var from the calling process. `ensure_local_gateway`
    (Task 2) calls this method rather than re-implementing the mapping.

- [ ] **Step 4: Run tests** — `pytest tests/unit/acp/test_local_gateway_secrets.py -v`, confirm
  green.

## Task 2: `local_infra.py` — Redis and Gateway Process Lifecycle

**Files:**
- Create: `src/optimus/acp/local_infra.py`
- Create: `tests/unit/acp/test_local_infra.py`

**Interfaces:**
```python
def apply_local_defaults(environ: Mapping[str, str], *, project_root: Path) -> dict[str, str]
def ensure_local_redis(redis_url: str, *, log: Callable[[str], None] = lambda _msg: None) -> None
def ensure_local_gateway(*, environ: Mapping[str, str], project_root: Path, log=lambda _msg: None) -> "LocalGatewayProcess | None"

@dataclass
class LocalGatewayProcess:
    process: subprocess.Popen | None
    log_path: Path | None
    def stop(self) -> None: ...
```

- [ ] **Step 1: Write failing tests**, using `monkeypatch.setattr` on module-level
  `subprocess.run` / `subprocess.Popen` / `socket.create_connection` (matching this repo's
  existing `monkeypatch.setattr("optimus.acp.bootstrap.RedisRuntime.from_url", ...)` style) — no
  real Docker or process spawned in this tier. Cover:
  - `apply_local_defaults` fills `OPTIMUS_REDIS_URL` / `OPTIMUS_GATEWAY_URL` only when absent,
    leaves explicit values untouched, resolves `OPTIMUS_API_KEY` via
    `local_gateway_secrets.resolve_shared_secret` only when the (now-resolved) gateway URL is
    loopback and the key is unset; returns a new dict, never mutates the input mapping or
    `os.environ`.
  - `apply_local_defaults` ALSO fills, only when the (now-resolved) gateway URL is loopback:
    - `OPTIMUS_PRODUCTION_MODE` → `"false"` when unset. Without this,
      `OptimusGatewaySettings.from_env()` raises `ValueError` on a loopback `http://` origin
      regardless of any other default (see Source Anchors: `src/optimus/config/gateway.py:85`).
      Test: zero-env-var input produces `OPTIMUS_PRODUCTION_MODE == "false"` in the result, and an
      explicit `OPTIMUS_PRODUCTION_MODE=true` set by the operator is never overridden even against
      a loopback URL (respect explicit operator intent).
    - `OPTIMUS_AGENT_MODEL` → `"claude-haiku"` when unset. Without this, `resolve_agent_model()`
      returns `DEFAULT_AGENT_MODEL = "glm-5.2"`, which has no alias or passthrough match in
      `PROVIDER_MODEL_ALIASES`/`is_plausible_passthrough()` for any local provider and would fail
      the first real planning call with `unsupported gateway model: glm-5.2` (see Source Anchors).
      Test: zero-env-var input produces `OPTIMUS_AGENT_MODEL == "claude-haiku"`; an explicit
      `OPTIMUS_AGENT_MODEL` or `--model` CLI override is never touched by this default (CLI
      `--model` is applied later in `__main__.py` and already takes precedence over the
      environment per `resolve_agent_model`'s existing `cli_model` parameter).
    - Neither of these two new defaults applies when `OPTIMUS_GATEWAY_URL` is (or resolves to) a
      non-loopback origin — a real hosted gateway must never be silently switched to
      non-production mode or have its model overridden.
  - `ensure_local_redis` no-ops when already TCP-reachable (assert the docker spy is never
    called).
  - `ensure_local_redis` no-ops when host is non-loopback (never touches a remote Redis).
  - `ensure_local_redis` no-ops when `docker` isn't on `PATH` (`shutil.which` returns `None`), and
    when the daemon is unreachable (`docker ps` fails) — leaving the same "not reachable" state
    preflight already reports, not raising.
  - `ensure_local_redis` runs `docker run -d --name optimus-redis -p <port>:6379 redis:8`
    (**no `--rm`**) when the named container doesn't exist, and `docker start optimus-redis` when
    it exists but is stopped. `--rm` and "restart a stopped container by name" are mutually
    exclusive — `--rm` makes Docker delete the container the instant it stops, so a later
    `docker start optimus-redis` would always fail with "no such container". The already-committed
    operator runbook (Plan 9.6, `README.md`) documents `docker run --rm -d ...` for a manual,
    one-off session where the operator explicitly wants full cleanup on stop; the container this
    plan manages automatically is a different, persistent-by-design instance (needs to survive
    across `optimus-agent` launches), so it intentionally omits `--rm`. Note this divergence in
    Task 5 docs rather than silently having two different `optimus-redis`-named containers behave
    differently depending on which path created them last.
  - `ensure_local_gateway` returns `None` (no-op) when already reachable, when the URL isn't
    loopback, and when no secrets can be resolved anywhere.
  - `ensure_local_gateway` spawns `[sys.executable, "-m", "optimus_gateway"]` with a **fully and
    explicitly asserted** child env — not just "contains the provider key" — matching exactly what
    `GatewayServiceConfig.from_env()` (`src/optimus_gateway/models.py`) reads:
    `OPTIMUS_LOCAL_GATEWAY_PROVIDER` (the resolved provider name), `OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET`
    (from `resolve_shared_secret`), `OPTIMUS_LOCAL_GATEWAY_BIND_HOST`/`OPTIMUS_LOCAL_GATEWAY_PORT`
    (derived from the loopback `OPTIMUS_GATEWAY_URL` being spawned for), and the correct
    provider-API-key variable via `ProviderSecrets.as_gateway_child_env()` (Task 1) — assert the
    complete env dict equals exactly this set, not merely `in`/superset checks, so a future edit
    can't silently add or drop a required key without failing a test. Also assert this dict is a
    distinct object from — never merged into — the calling process's own `os.environ`, and that
    stdout/stderr are redirected to a log file path, never `subprocess.PIPE` shared with the
    caller's own stdio.
  - `ensure_local_gateway` returns `None` and reports failure via `log(...)` if the spawned
    process exits before becoming reachable (simulate with a fake `Popen` whose `.poll()` returns
    a non-`None` exit code immediately).
  - `LocalGatewayProcess.stop()` terminates a running process and is a no-op if the process
    already exited.

- [ ] **Step 2: Run tests, confirm failure.**

- [ ] **Step 3: Implement** `src/optimus/acp/local_infra.py` per the interfaces above. Loopback
  detection reuses the same host allowlist already established in
  `src/optimus_gateway/models.py` (`_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}`) —
  import it rather than duplicating the frozenset, to avoid drift between the two definitions.

- [ ] **Step 4: Run tests** — confirm green.

## Task 3: Wire Into `__main__.py`

**Files:**
- Modify: `src/optimus/acp/__main__.py`
- Modify/Create: test coverage for the new flags and wiring (extend
  `tests/unit/acp/test_entrypoint.py` or add an integration-style test with fakes injected via
  monkeypatch)

**`--no-auto-start` semantics (single rule, applies everywhere):** it gates the two
*process/container-spawning* calls — `ensure_local_redis` and `ensure_local_gateway` — in both
the `--check-config` branch and the real serve branch, consistently. `apply_local_defaults` is
never gated by this flag: it only fills in env-var values (no side effects, nothing spawned), so
an operator who manages Redis/gateway themselves still benefits from the `OPTIMUS_PRODUCTION_MODE`
/ `OPTIMUS_AGENT_MODEL` defaults when pointed at loopback. (This corrects an inconsistency in the
first draft of this plan, where the test list said `--no-auto-start` skips both calls but the
implementation notes only gated `ensure_local_gateway`, leaving `ensure_local_redis` ungated.)

**`--check-config --strict` and the gateway auth probe:** `--check-config` never calls
`ensure_local_gateway` regardless of `--no-auto-start` (spawning a process tied to a command that
exits immediately would just start-and-orphan it — see Task 2). But `preflight.py`'s strict mode
performs a real `GatewayClient.create_response()` auth probe against whatever
`OPTIMUS_GATEWAY_URL` resolves to. This means **`--check-config --strict` against the local
auto-start shape requires a gateway to already be reachable** — either because a real
`optimus-agent` serve session is currently running and sharing the same loopback port, or because
the operator started one manually. Document this explicitly (Task 5): plain `--check-config`
(non-strict) is the correct pre-launch sanity check for the auto-start flow, since it only
validates credential-shape and Redis, neither of which requires the gateway to be up yet;
`--strict` is for validating an already-running stack (e.g. right before pointing an IDE at it),
not for validating a not-yet-started one. This plan does not add spawn-then-teardown-just-for-the-
probe logic to `--check-config --strict`, to keep it free of process side effects.

- [ ] **Step 1: Write failing tests** asserting:
  - `--setup` calls `run_setup_wizard` and returns its exit code without touching
    preflight/server construction.
  - `--no-auto-start` skips both `ensure_local_redis` and `ensure_local_gateway` calls in the real
    serve path (assert via monkeypatched spies that neither was called).
  - `--no-auto-start` also skips `ensure_local_redis` in the `--check-config` branch (assert via
    spy), while `apply_local_defaults` still runs in both branches regardless of the flag.
  - Without `--no-auto-start`, the real serve path calls `apply_local_defaults`, then
    `ensure_local_redis`, then `ensure_local_gateway`, then `build_configured_server`, in that
    order, and calls `.stop()` on the returned `LocalGatewayProcess` after `serve`/`serve_ndjson`
    returns — but only when `ensure_local_gateway` returned a non-`None` handle (assert `.stop()`
    is not called when it returned `None`), and also on the exception path (simulate `serve`
    raising).
  - Without `--no-auto-start`, `--check-config` calls `apply_local_defaults` and
    `ensure_local_redis` but does **not** call `ensure_local_gateway` (assert via spy/monkeypatch).

- [ ] **Step 2: Run tests, confirm failure.**

- [ ] **Step 3: Implement wiring** in `main()`:
  - Add `--setup` (runs the wizard, returns its exit code, short-circuits everything else) and
    `--no-auto-start` (`store_true`) argparse arguments.
  - In the `--check-config` branch: `environ = apply_local_defaults(os.environ,
    project_root=...)`; if not `args.no_auto_start`, `ensure_local_redis(environ["OPTIMUS_REDIS_URL"])`;
    then proceed to `run_preflight(environ, ...)` exactly as today.
  - In the real serve branch: same `apply_local_defaults`; if not `args.no_auto_start`,
    `ensure_local_redis(environ["OPTIMUS_REDIS_URL"])` and
    `gateway_process = ensure_local_gateway(environ=environ, project_root=...)`, else
    `gateway_process = None` (and `ensure_local_redis` is skipped too); wrap the existing
    `build_configured_server(...)` / `asyncio.run(server.serve(...))` call in `try/finally`,
    calling `gateway_process.stop()` in the `finally` only if `gateway_process is not None`.

- [ ] **Step 4: Run tests** — confirm green.

## Task 4: Preflight Message Update

**Files:**
- Modify: `src/optimus/acp/preflight.py`
- Modify: `tests/unit/acp/test_preflight.py`

- [ ] **Step 1:** Confirm the existing test asserts via substring (`in`), not exact equality, so
  appending a clause stays additive. If it currently asserts exact equality, update the assertion
  to `in` first (failing-test-first for the changed assertion).
- [ ] **Step 2:** Change `_require_gateway_credentials`'s message from
  `"Set OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY before launching the Optimus ACP agent."` to also
  mention `optimus-agent --setup`, e.g.:
  `"Set OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY before launching the Optimus ACP agent (or run"
  " optimus-agent --setup to configure the local gateway)."`
- [ ] **Step 3:** Run `pytest tests/unit/acp/test_preflight.py -v` — confirm green.

## Task 5: Documentation

**Files:**
- Modify: `README.md`

- [ ] New quickstart: `uv tool install --editable .` → `optimus-agent --setup` → Zed
  `agent_servers` example with **no `env` block** for the local case.
- [ ] Existing `.env`/`.env.gateway` instructions retained under an explicit "Manual / advanced
  setup (transitional)" subsection, noting keyring is the intended long-term default per this
  plan's decision.
- [ ] Document `--setup` and `--no-auto-start` next to the existing `--check-config`
  documentation, including that `--no-auto-start` disables both Redis and gateway auto-start
  consistently (not just the gateway).
- [ ] Document that `--check-config --strict` requires the gateway to already be reachable (it
  never spawns one itself); plain `--check-config` is the right pre-launch check for the
  auto-start flow.
- [ ] Note that the `optimus-redis` container this plan manages automatically omits `--rm` (so it
  can be restarted by name across launches), which differs from the manual runbook's
  `docker run --rm -d ...` one-off example — both are intentional, for different use cases.
- [ ] Keep the hosted-gateway Zed example (explicit `OPTIMUS_GATEWAY_URL`/`OPTIMUS_API_KEY` env
  values) — auto-start/keyring never engages there.

## Definition of Done

- [ ] `pytest tests/unit/acp/test_local_gateway_secrets.py tests/unit/acp/test_local_infra.py -v`
  green.
- [ ] Full `pytest -q` green, no regressions.
- [ ] `python -m ruff check .` clean.
- [ ] Manual verification on a real Windows machine (not just unit tests): remove/rename any
  local `.env.gateway`, run `optimus-agent --setup` with a real provider key, then `optimus-agent
  --workspace-root .` with **no environment variables set at all**, and confirm the
  `optimus-redis` Docker container and the local gateway process both come up, preflight passes,
  **and a real planning call succeeds against the auto-defaulted `claude-haiku` model** (not just
  that the process starts — the model-default bug found in review only surfaces once planning
  actually runs). Record the actual commands/output used, not just "tests passed."
- [ ] Explicitly verify the zero-env-var run also produces `OPTIMUS_PRODUCTION_MODE=false` being
  applied (e.g. via a debug print or by confirming `OptimusGatewaySettings.from_env()` does not
  raise on the loopback origin) — this is the specific failure this review found and is easy to
  regress silently since it only manifests as a `ValueError` deep inside settings construction.
- [ ] README changes reviewed for accuracy against the actual CLI flags implemented.
- [ ] No change to any Plan 9.6 preflight check's fail-closed behavior when auto-start is
  disabled (`--no-auto-start`) or when Docker/keyring are unavailable — verified by the no-op
  test cases in Task 2.
- [ ] `--no-auto-start` verified to skip Redis auto-start too, not only gateway auto-start (the
  inconsistency this review found between the plan's test list and implementation notes).

## Explicit Exceptions (do not silently expand scope to cover these)

- Linux/WSL keyring backend support.
- Removing `.env`/`.env.gateway`.
- Changing `tools/run_local_gateway.sh`/`.ps1`.
- Any change to the real hosted-gateway path.
- Auto-starting Docker Desktop itself.
- Any change to Plan 9.6's scope, live tiers, or sign-off gate.
