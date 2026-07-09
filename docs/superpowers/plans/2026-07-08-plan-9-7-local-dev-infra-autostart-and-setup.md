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

**Status:** Approved 2026-07-09. Task 1 complete; Tasks 2–5 in progress on branch
`agent/cursor/plan-9-7-local-dev-infra`.

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
- `src/optimus/config/gateway.py:18,112`: `LOCAL_PROVIDER_KEY_NAMES` (includes `ANTHROPIC_API_KEY`,
  not `OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY`) and `validate_no_local_provider_keys()`, called from
  `OptimusGatewaySettings.from_env()` at three sites — `src/optimus/acp/bootstrap.py:44` (inside
  `build_agent_runner_for_harness`), `bootstrap.py:73` (inside `build_configured_server`), and
  `src/optimus/acp/preflight.py:99` (strict `--check-config`). **Real conflict found in review
  2026-07-08, round 2:** the anthropic path is a hard collision — `ANTHROPIC_API_KEY` is
  simultaneously the var name the gateway child needs *and* a name the agent's own settings loader
  explicitly rejects with `ProviderKeyViolation`. If `ensure_local_gateway` and
  `build_configured_server` are handed the same `environ` object, an anthropic-provider auto-start
  would successfully spawn the gateway and then immediately crash agent startup.
  **Round 3 finding:** `OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY` (the openai/openrouter case) does
  not crash the same way — it isn't in `LOCAL_PROVIDER_KEY_NAMES`, precisely because it was
  invented to avoid the round-2 collision for those two providers (see
  `docs/superpowers/plans/2026-07-07-local-optimus-gateway-service.md`, Scope item 5) — but it is
  still a real provider API key, and the stricter architecture rule (Design Decision 3 below) is
  that the agent-facing view must never contain one at all, crash or no crash. The strip set
  (`_AGENT_ENVIRON_EXCLUDED_KEYS` in Task 2) must be broader than `LOCAL_PROVIDER_KEY_NAMES`:
  `LOCAL_PROVIDER_KEY_NAMES | {"OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY",
  "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET"}` — the latter because it's a gateway-internal duplicate
  of `OPTIMUS_API_KEY` once `apply_local_defaults()` has copied the value across, and the agent
  view should keep only the public contract name. Addressed in Task 2
  (`strip_local_provider_keys`, `_AGENT_ENVIRON_EXCLUDED_KEYS`) and Task 3 (two separate `environ`
  views in `main()`, with sibling regression tests for both the anthropic and openrouter cases).

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
3. **Provider-key boundary:** the actually-enforceable guarantee is narrower than "never in
   `os.environ`" — since Plan 9.7 supports explicit-env-var precedence for provider keys (Design
   Decision 4 below), an operator who launches `optimus-agent` with `ANTHROPIC_API_KEY` or
   `OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY` already set necessarily has that secret in the real
   process `os.environ` — nothing `optimus-agent` does can retroactively make that untrue, and this
   plan doesn't promise otherwise. What Plan 9.7 does guarantee: `optimus-agent` never *adds* a
   provider key to its own environment, never uses one to call a model itself, and the
   agent-facing `agent_environ` passed to `run_preflight`/`build_configured_server` never contains
   one — only the spawned gateway child's own environment does. This is stricter than "don't
   trigger `ProviderKeyViolation`" — it holds even for names (like
   `OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY`) that don't collide with the agent's explicit reject
   list but are still real vendor secrets.
   **Enforced mechanism (added after 2026-07-08 review, rounds 2-3):** `main()` keeps two distinct
   `environ` views — the unsanitized one (used only to resolve secrets for `ensure_local_gateway`'s
   child env) and a `strip_local_provider_keys()`-sanitized one, built from
   `_AGENT_ENVIRON_EXCLUDED_KEYS` (`LOCAL_PROVIDER_KEY_NAMES` plus
   `OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY` and `OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET`), used for
   everything that reaches `OptimusGatewaySettings.from_env()` — `build_configured_server` and, in
   strict `--check-config`, `run_preflight`. The two must never collapse into a single object
   passed to both call sites.
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
  `ensure_local_gateway()` (spawn/track the local gateway child process),
  `strip_local_provider_keys()` (produces the agent-facing `environ` view that must never contain
  a real vendor key — see the anthropic-collision finding above).
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
    provider: str  # "openai" | "openrouter" | "anthropic" — defaults to "openrouter" if
                   # unconfigured anywhere, matching GatewayServiceConfig.from_env()'s own default
                   # (src/optimus_gateway/models.py:40) so the two sides never disagree.
    model_provider_api_key: str
    base_url: str | None = None  # OPTIMUS_LOCAL_GATEWAY_BASE_URL pass-through; optional override
                                  # for OpenAI-compatible endpoints (models.py:44), not a secret.

    def as_gateway_child_env(self) -> dict[str, str]:
        """Map to the exact var names GatewayServiceConfig.from_env() reads for this provider
        (src/optimus_gateway/models.py:45): ANTHROPIC_API_KEY for anthropic, else
        OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY. Only ever sets the one name the resolved
        provider needs; never sets the other provider-key family, even if it happens to be
        present in the operator's own environment (mirrors the existing pop()-based clearing
        already done in tests/integration/optimus_gateway/gateway_env.py's
        merge_gateway_subprocess_env, promoted here to a production code path). Also passes
        through OPTIMUS_LOCAL_GATEWAY_BASE_URL when set, so a custom OpenAI-compatible endpoint
        configured anywhere in the precedence chain isn't silently dropped."""

def resolve_provider_secrets(environ, *, project_root, keyring_backend=keyring) -> ProviderSecrets | None
def resolve_shared_secret(environ, *, project_root, keyring_backend=keyring) -> str | None
def run_setup_wizard(*, project_root, keyring_backend=keyring, input_fn=input, getpass_fn=getpass.getpass, print_fn=print) -> int
```

- [x] **Step 1: Write failing tests**

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


def test_resolve_provider_secrets_defaults_provider_to_openrouter_when_unset(tmp_path):
    # Matches GatewayServiceConfig.from_env()'s own default (models.py:40) — an operator who only
    # sets the API key, without ever naming a provider, should still resolve, not fail closed.
    resolved = resolve_provider_secrets(
        {"OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "sk-or-implicit"},
        project_root=tmp_path,
        keyring_backend=FakeKeyring(),
    )

    assert resolved == ProviderSecrets(provider="openrouter", model_provider_api_key="sk-or-implicit")


def test_provider_secrets_includes_base_url_when_set(tmp_path):
    secrets_ = ProviderSecrets(
        provider="openai",
        model_provider_api_key="sk-test",
        base_url="https://custom.example.com/v1",
    )

    child_env = secrets_.as_gateway_child_env()

    assert child_env == {
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "sk-test",
        "OPTIMUS_LOCAL_GATEWAY_BASE_URL": "https://custom.example.com/v1",
    }


def test_resolve_provider_secrets_passes_through_base_url_from_dotenv(tmp_path):
    (tmp_path / ".env.gateway").write_text(
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER=openai\n"
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY=sk-test\n"
        "OPTIMUS_LOCAL_GATEWAY_BASE_URL=https://custom.example.com/v1\n",
        encoding="utf-8",
    )

    resolved = resolve_provider_secrets({}, project_root=tmp_path, keyring_backend=FakeKeyring())

    assert resolved == ProviderSecrets(
        provider="openai",
        model_provider_api_key="sk-test",
        base_url="https://custom.example.com/v1",
    )


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

- [x] **Step 2: Run tests, confirm failure** —
  `pytest tests/unit/acp/test_local_gateway_secrets.py -v` (module doesn't exist yet, expect
  `ImportError`/collection failure).

- [x] **Step 3: Implement** `src/optimus/acp/local_gateway_secrets.py`:

**Design notes to keep in mind while reading the code below:**
- A minimal `.env.gateway` line parser scoped to this file (`KEY=VALUE`, `#` comments, optional
  surrounding quotes). Do **not** add `python-dotenv` as a runtime dependency for this — it is
  dev-only today (`[project.optional-dependencies].dev`), and promoting it to a hard runtime
  dependency just for this one file is disproportionate; a ~10-line parser is sufficient and
  keeps the dependency footprint minimal, consistent with this project's existing runtime
  dependency list (`confusable-homoglyphs`, `pydantic`, `redis`).
- **Keychain key naming (forward-compat with Plan 9.8, tracked separately — see "Relationship to
  Plan 9.8" above):** `model_provider`, `model_provider_api_key`, and `local_gateway_shared_secret`
  as the three keyring key names under service `optimus-cost-agent` — namespaced by capability
  (`model_*`) precisely so a future Plan 9.8 can add sibling keys (e.g. a web-search or
  observability provider's key) under the same service without colliding with or restructuring
  what Plan 9.7 already stores.
- `run_setup_wizard`'s prompt order is provider **first**, then the overwrite check — matching the
  test input sequence `["openrouter", "n"]` above (provider, then the decline answer). Asking
  overwrite before provider would consume the test's inputs in the wrong order.

```python
from __future__ import annotations

import getpass
import re
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import keyring

_KEYRING_SERVICE = "optimus-cost-agent"
_KEY_MODEL_PROVIDER = "model_provider"
_KEY_MODEL_PROVIDER_API_KEY = "model_provider_api_key"
_KEY_SHARED_SECRET = "local_gateway_shared_secret"

_SUPPORTED_PROVIDERS = ("openai", "openrouter", "anthropic")
_DEFAULT_PROVIDER = "openrouter"

_ENV_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


@dataclass(frozen=True)
class ProviderSecrets:
    provider: str  # "openai" | "openrouter" | "anthropic"
    model_provider_api_key: str
    base_url: str | None = None

    def as_gateway_child_env(self) -> dict[str, str]:
        """Map to the exact var names GatewayServiceConfig.from_env() reads for this provider
        (src/optimus_gateway/models.py:45): ANTHROPIC_API_KEY for anthropic, else
        OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY. Only ever sets the one name the resolved
        provider needs. Also passes through OPTIMUS_LOCAL_GATEWAY_BASE_URL when set (models.py:44)
        — harmless to include for anthropic too, since GatewayServiceConfig.from_env() always
        forces base_url to None for that provider regardless of what's in its env."""
        env = {"ANTHROPIC_API_KEY": self.model_provider_api_key} if self.provider == "anthropic" else {
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": self.model_provider_api_key
        }
        if self.base_url:
            env["OPTIMUS_LOCAL_GATEWAY_BASE_URL"] = self.base_url
        return env


def _parse_env_gateway_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _ENV_LINE.match(line)
        if match is None:
            continue
        key, value = match.group(1), match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def _safe_get_password(keyring_backend: Any, key: str) -> str | None:
    try:
        value = keyring_backend.get_password(_KEYRING_SERVICE, key)
    except Exception:
        return None
    if value is None:
        return None
    value = value.strip()
    return value or None


def resolve_shared_secret(
    environ: Mapping[str, str],
    *,
    project_root: Path,
    keyring_backend: Any = keyring,
) -> str | None:
    env_value = environ.get("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", "").strip()
    if env_value:
        return env_value
    dotenv_value = _parse_env_gateway_file(project_root / ".env.gateway").get(
        "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", ""
    ).strip()
    if dotenv_value:
        return dotenv_value
    return _safe_get_password(keyring_backend, _KEY_SHARED_SECRET)


def resolve_provider_secrets(
    environ: Mapping[str, str],
    *,
    project_root: Path,
    keyring_backend: Any = keyring,
) -> ProviderSecrets | None:
    dotenv_values = _parse_env_gateway_file(project_root / ".env.gateway")

    # Default to "openrouter" when unconfigured anywhere — matches GatewayServiceConfig.from_env()'s
    # own default (models.py:40). Only a missing/unresolvable *API key* is a hard failure below;
    # the provider name alone should never block resolution when the gateway itself wouldn't block.
    provider = (
        environ.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER", "").strip()
        or dotenv_values.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER", "").strip()
        or _safe_get_password(keyring_backend, _KEY_MODEL_PROVIDER)
        or _DEFAULT_PROVIDER
    ).lower()
    if provider not in _SUPPORTED_PROVIDERS:
        return None

    if provider == "anthropic":
        api_key = (
            environ.get("ANTHROPIC_API_KEY", "").strip()
            or dotenv_values.get("ANTHROPIC_API_KEY", "").strip()
            or _safe_get_password(keyring_backend, _KEY_MODEL_PROVIDER_API_KEY)
            or ""
        )
    else:
        api_key = (
            environ.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "").strip()
            or dotenv_values.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "").strip()
            or _safe_get_password(keyring_backend, _KEY_MODEL_PROVIDER_API_KEY)
            or ""
        )
    if not api_key:
        return None

    # Not a secret — no keyring lookup, matching the design that keyring is reserved for secrets
    # only (see Task 1's keychain-schema note). Left as None if unset anywhere, letting
    # GatewayServiceConfig.from_env() apply its own per-provider default base URL.
    base_url = (
        environ.get("OPTIMUS_LOCAL_GATEWAY_BASE_URL", "").strip()
        or dotenv_values.get("OPTIMUS_LOCAL_GATEWAY_BASE_URL", "").strip()
        or None
    )
    return ProviderSecrets(provider=provider, model_provider_api_key=api_key, base_url=base_url)


def run_setup_wizard(
    *,
    project_root: Path,
    keyring_backend: Any = keyring,
    input_fn: Callable[[str], str] = input,
    getpass_fn: Callable[[str], str] = getpass.getpass,
    print_fn: Callable[..., None] = print,
) -> int:
    provider = (input_fn(f"Provider [{_DEFAULT_PROVIDER}]: ").strip() or _DEFAULT_PROVIDER).lower()
    if provider not in _SUPPORTED_PROVIDERS:
        print_fn(f"Unsupported provider: {provider!r}. Choose one of {_SUPPORTED_PROVIDERS}.")
        return 1

    existing_api_key = _safe_get_password(keyring_backend, _KEY_MODEL_PROVIDER_API_KEY)
    if existing_api_key:
        answer = input_fn("A provider key is already stored. Overwrite? [y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            print_fn("Setup cancelled; existing credentials unchanged.")
            return 1

    api_key = getpass_fn(f"{provider} API key: ").strip()
    if not api_key:
        print_fn("No API key entered; aborting setup.")
        return 1

    shared_secret = secrets.token_urlsafe(32)

    try:
        keyring_backend.set_password(_KEYRING_SERVICE, _KEY_MODEL_PROVIDER, provider)
        keyring_backend.set_password(_KEYRING_SERVICE, _KEY_MODEL_PROVIDER_API_KEY, api_key)
        keyring_backend.set_password(_KEYRING_SERVICE, _KEY_SHARED_SECRET, shared_secret)
    except Exception as exc:
        print_fn(
            f"Could not store credentials in the OS keychain ({exc}). "
            "Use .env.gateway instead (see .env.gateway.example)."
        )
        return 2

    print_fn(
        "Stored local gateway credentials in the OS keychain. "
        "You can now run `optimus-agent` with no environment variables required."
    )
    if (project_root / ".env.gateway").is_file():
        print_fn(
            "Note: .env.gateway also exists in this project; explicit env vars and that file "
            "take precedence over the keychain values just stored."
        )
    return 0
```

- [x] **Step 4: Run tests** — `pytest tests/unit/acp/test_local_gateway_secrets.py -v`, confirm
  green.

## Task 2: `local_infra.py` — Redis and Gateway Process Lifecycle

**Files:**
- Create: `src/optimus/acp/local_infra.py`
- Create: `tests/unit/acp/test_local_infra.py`

**Interfaces:**
```python
def apply_local_defaults(environ: Mapping[str, str], *, project_root: Path) -> dict[str, str]
def strip_local_provider_keys(environ: Mapping[str, str]) -> dict[str, str]
def ensure_local_redis(redis_url: str, *, log: Callable[[str], None] = lambda _msg: None) -> None
def ensure_local_gateway(*, environ: Mapping[str, str], project_root: Path, log=lambda _msg: None) -> "LocalGatewayProcess | None"

@dataclass
class LocalGatewayProcess:
    process: subprocess.Popen | None
    log_path: Path | None
    def stop(self) -> None: ...
```

- [x] **Step 1: Write failing tests**, using `monkeypatch.setattr` on module-level
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
  - `strip_local_provider_keys` removes every name in `_AGENT_ENVIRON_EXCLUDED_KEYS` — that's
    `LOCAL_PROVIDER_KEY_NAMES` (`src/optimus/config/gateway.py:18`) **plus**
    `OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY` and `OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET`, not
    `LOCAL_PROVIDER_KEY_NAMES` alone — from a copied dict, leaving everything else (including
    `OPTIMUS_API_KEY`, `OPTIMUS_GATEWAY_URL`, `OPTIMUS_REDIS_URL`) untouched. This is the function
    `main()` (Task 3) must call to build the agent-facing `environ` passed to
    `build_configured_server`/strict `run_preflight`, separate from the unsanitized `environ`
    `ensure_local_gateway` uses — see the anthropic- and openrouter-collision findings in Source
    Anchors above.
  - `ensure_local_redis` no-ops when already TCP-reachable (assert the docker spy is never
    called).
  - `ensure_local_redis` no-ops when host is non-loopback (never touches a remote Redis).
  - `ensure_local_redis` no-ops when `docker` isn't on `PATH` (`shutil.which` returns `None`), and
    when the daemon is unreachable (`docker ps` fails) — leaving the same "not reachable" state
    preflight already reports, not raising.
  - `ensure_local_redis` runs `docker run -d --name optimus-redis -p 127.0.0.1:<port>:6379 redis:8`
    (**no `--rm`**, loopback bind only — corrected 2026-07-09 review: unqualified `-p <port>:6379`
    publishes on `0.0.0.0`, exposing unauthenticated Redis to the LAN) when the named container
    doesn't exist, and `docker start optimus-redis` when it exists but is stopped. `--rm` and
    "restart a stopped container by name" are mutually exclusive — `--rm` makes Docker delete
    the container the instant it stops, so a later `docker start optimus-redis` would always fail
    with "no such container". The already-committed
    operator runbook (Plan 9.6, `README.md`) documents `docker run --rm -d ...` for a manual,
    one-off session where the operator explicitly wants full cleanup on stop; the container this
    plan manages automatically is a different, persistent-by-design instance (needs to survive
    across `optimus-agent` launches), so it intentionally omits `--rm`. Note this divergence in
    Task 5 docs rather than silently having two different `optimus-redis`-named containers behave
    differently depending on which path created them last.
  - `ensure_local_gateway` returns `None` (no-op) when already reachable, when the URL isn't
    loopback, and when no secrets can be resolved anywhere.
  - `ensure_local_gateway` spawns `[sys.executable, "-m", "optimus_gateway"]` with a child env
    containing the gateway-specific keys `GatewayServiceConfig.from_env()`
    (`src/optimus_gateway/models.py`) reads — `OPTIMUS_LOCAL_GATEWAY_PROVIDER`,
    `OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET`, `OPTIMUS_LOCAL_GATEWAY_BIND_HOST`,
    `OPTIMUS_LOCAL_GATEWAY_PORT`, and the correct provider-API-key variable via
    `ProviderSecrets.as_gateway_child_env()` — asserted with **exact values**, plus an explicit
    assertion that the unused provider-key family (e.g. `ANTHROPIC_API_KEY` when the resolved
    provider is `openrouter`) is absent. **Correction from an earlier draft of this plan:** this is
    *not* a check that the whole env dict equals only those five keys — the child process also
    needs `PATH`/`SYSTEMROOT`/etc. and `PYTHONPATH` to run at all on Windows (the same system-key
    passthrough pattern `build_acp_subprocess_env` in `subprocess_env.py` already uses), so the
    test asserts the gateway-specific subset exactly, not the entire dict. Also assert the env
    dict is a distinct object from — never merged into — the calling process's own `os.environ`,
    and that stdout/stderr are redirected to a log file, never `subprocess.PIPE` shared with the
    caller's own stdio. See the concrete test below.
  - `ensure_local_gateway` returns `None` and reports failure via `log(...)` if the spawned
    process exits before becoming reachable (simulate with a fake `Popen` whose `.poll()` returns
    a non-`None` exit code immediately).
  - `ensure_local_gateway` passes through `OPTIMUS_LOCAL_GATEWAY_BASE_URL` into the child env when
    `ProviderSecrets.base_url` is set (from any point in the precedence chain) — the local gateway
    config surface already supports this override for OpenAI-compatible endpoints
    (`src/optimus_gateway/models.py:44`); dropping it here would silently break an operator who
    points at a custom endpoint. `resolve_provider_secrets` also defaults the *provider name* to
    `"openrouter"` when unconfigured anywhere, matching `GatewayServiceConfig.from_env()`'s own
    default (`models.py:40`) — only a missing/unresolvable API key blocks resolution, not an
    absent provider name.
  - `ensure_local_gateway` fails closed (`return None`, via `log(...)`) rather than propagating an
    exception if preparing the log file (`mkdir`/`open`) or `subprocess.Popen(...)` itself raises
    `OSError` — a permissions issue or missing interpreter must not crash `optimus-agent`'s own
    `main()`; it should look identical to "gateway didn't come up" and let the existing preflight
    check report it with its own operator-actionable message.
  - `LocalGatewayProcess.stop()` terminates a running process and is a no-op if the process
    already exited.

```python
import os
import subprocess
import sys

from optimus.acp import local_infra
from optimus.acp.local_gateway_secrets import ProviderSecrets


def test_strip_local_provider_keys_removes_vendor_keys_but_keeps_optimus_vars():
    environ = {
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
        "OPTIMUS_API_KEY": "shared-secret",
        "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
        "ANTHROPIC_API_KEY": "sk-ant-leaked",
        "OPENAI_API_KEY": "sk-oai-leaked",
    }

    sanitized = local_infra.strip_local_provider_keys(environ)

    assert sanitized == {
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
        "OPTIMUS_API_KEY": "shared-secret",
        "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
    }
    assert environ["ANTHROPIC_API_KEY"] == "sk-ant-leaked"  # input untouched, a new dict returned


def test_strip_local_provider_keys_also_removes_openrouter_key_and_shared_secret():
    # Regression test (2026-07-08 review, round 3): OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY is
    # NOT in LOCAL_PROVIDER_KEY_NAMES (it was invented specifically to avoid the
    # ANTHROPIC_API_KEY-style collision — see the module-level comment above
    # _AGENT_ENVIRON_EXCLUDED_KEYS) and would otherwise leak through untouched for the
    # openai/openrouter path even though it is still a real provider API key.
    # OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET is likewise stripped as a gateway-internal duplicate of
    # OPTIMUS_API_KEY, not because it's a vendor key.
    environ = {
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
        "OPTIMUS_API_KEY": "shared-secret",
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "sk-or-leaked",
        "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "shared-secret",
    }

    sanitized = local_infra.strip_local_provider_keys(environ)

    assert sanitized == {"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765", "OPTIMUS_API_KEY": "shared-secret"}


def test_ensure_local_gateway_spawns_with_exact_gateway_env_and_no_stray_secrets(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    reachable_calls = {"n": 0}

    def fake_tcp_reachable(host, port, *, timeout=1.0):
        reachable_calls["n"] += 1
        return reachable_calls["n"] > 1  # not reachable on the pre-check; reachable once "up"

    monkeypatch.setattr(local_infra, "_tcp_reachable", fake_tcp_reachable)
    monkeypatch.setattr(
        local_infra,
        "resolve_provider_secrets",
        lambda environ, *, project_root: ProviderSecrets(provider="openrouter", model_provider_api_key="sk-or-test"),
    )
    monkeypatch.setattr(local_infra, "resolve_shared_secret", lambda environ, *, project_root: "shared-secret-value")

    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 4321
        returncode = None

        def poll(self):
            return None

    def fake_popen(args, *, env, stdin, stdout, stderr):
        captured["args"] = args
        captured["env"] = env
        captured["stdout"] = stdout
        return FakeProcess()

    monkeypatch.setattr(local_infra.subprocess, "Popen", fake_popen)

    result = local_infra.ensure_local_gateway(
        environ={"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765", "PATH": os.environ.get("PATH", "")},
        project_root=tmp_path,
    )

    assert result is not None
    assert captured["args"] == [sys.executable, "-m", "optimus_gateway"]
    gateway_env = captured["env"]
    assert gateway_env["OPTIMUS_LOCAL_GATEWAY_PROVIDER"] == "openrouter"
    assert gateway_env["OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET"] == "shared-secret-value"
    assert gateway_env["OPTIMUS_LOCAL_GATEWAY_BIND_HOST"] == "127.0.0.1"
    assert gateway_env["OPTIMUS_LOCAL_GATEWAY_PORT"] == "8765"
    assert gateway_env["OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY"] == "sk-or-test"
    assert "ANTHROPIC_API_KEY" not in gateway_env  # unused provider-key family never set
    assert gateway_env is not os.environ  # distinct object, never merged into the caller's own env
    assert captured["stdout"] != subprocess.PIPE  # redirected to a log file, never shared stdio


def test_ensure_local_gateway_passes_through_custom_base_url(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    reachable_calls = {"n": 0}

    def fake_tcp_reachable(host, port, *, timeout=1.0):
        reachable_calls["n"] += 1
        return reachable_calls["n"] > 1

    monkeypatch.setattr(local_infra, "_tcp_reachable", fake_tcp_reachable)
    monkeypatch.setattr(
        local_infra,
        "resolve_provider_secrets",
        lambda environ, *, project_root: ProviderSecrets(
            provider="openai", model_provider_api_key="sk-test", base_url="https://custom.example.com/v1"
        ),
    )
    monkeypatch.setattr(local_infra, "resolve_shared_secret", lambda environ, *, project_root: "shared-secret-value")

    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 1111
        returncode = None

        def poll(self):
            return None

    def fake_popen(args, *, env, stdin, stdout, stderr):
        captured["env"] = env
        return FakeProcess()

    monkeypatch.setattr(local_infra.subprocess, "Popen", fake_popen)

    result = local_infra.ensure_local_gateway(
        environ={"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765"},
        project_root=tmp_path,
    )

    assert result is not None
    assert captured["env"]["OPTIMUS_LOCAL_GATEWAY_BASE_URL"] == "https://custom.example.com/v1"


def test_ensure_local_gateway_fails_closed_when_popen_raises(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda host, port, *, timeout=1.0: False)
    monkeypatch.setattr(
        local_infra,
        "resolve_provider_secrets",
        lambda environ, *, project_root: ProviderSecrets(provider="openrouter", model_provider_api_key="sk-or-test"),
    )
    monkeypatch.setattr(local_infra, "resolve_shared_secret", lambda environ, *, project_root: "shared-secret-value")

    def raising_popen(*_a, **_k):
        raise OSError("spawn failed")

    monkeypatch.setattr(local_infra.subprocess, "Popen", raising_popen)

    messages = []
    result = local_infra.ensure_local_gateway(
        environ={"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765"},
        project_root=tmp_path,
        log=messages.append,
    )

    assert result is None  # fails closed, does not propagate the OSError
    assert any("could not start local gateway process" in msg for msg in messages)
```

- [x] **Step 2: Run tests, confirm failure.**

- [x] **Step 3: Implement** `src/optimus/acp/local_infra.py`:

```python
from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from optimus.acp.local_gateway_secrets import resolve_provider_secrets, resolve_shared_secret
from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES, _LOOPBACK_HOSTS

# _LOOPBACK_HOSTS reused from optimus.config.gateway (agent-side package, already imported
# elsewhere in bootstrap.py) rather than src/optimus_gateway/models.py's own separate copy of the
# same frozenset — the local-gateway-service plan documents optimus_gateway as "a distinct
# process/deployable, not a module the agent imports," so this module must not import across
# that boundary even though optimus_gateway/models.py happens to define an identical constant.

# The agent-facing environ (passed to build_configured_server / strict run_preflight) must never
# contain a real vendor key OR the local gateway's own auth secret. LOCAL_PROVIDER_KEY_NAMES alone
# is not enough: it's the set OptimusGatewaySettings.from_env() explicitly rejects (ANTHROPIC_API_KEY,
# OPENAI_API_KEY, etc.), but OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY — the var GatewayServiceConfig
# reads for the openai/openrouter path — was deliberately NOT put in that set (it exists precisely
# to avoid the ANTHROPIC_API_KEY-style collision; see
# docs/superpowers/plans/2026-07-07-local-optimus-gateway-service.md, Scope item 5), so it would
# otherwise leak through untouched even though it is still a real provider API key. Also strip
# OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET: once apply_local_defaults() has copied its value into
# OPTIMUS_API_KEY, the agent view should keep only that public contract name, not the
# gateway-internal duplicate under its own name. Found in 2026-07-08 review, round 3.
_AGENT_ENVIRON_EXCLUDED_KEYS = LOCAL_PROVIDER_KEY_NAMES | {
    "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY",
    "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET",
}

_REDIS_CONTAINER_NAME = "optimus-redis"
_REDIS_IMAGE = "redis:8"
_REDIS_READY_TIMEOUT_SECONDS = 15.0
_GATEWAY_READY_TIMEOUT_SECONDS = 10.0
_POLL_INTERVAL_SECONDS = 0.5
_DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"
_DEFAULT_GATEWAY_URL = "http://127.0.0.1:8765"
_DEFAULT_LOCAL_AGENT_MODEL = "claude-haiku"
_SYSTEM_ENV_KEYS = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP", "TMP")


def _noop_log(_message: str) -> None:
    return


def _is_loopback(host: str | None) -> bool:
    return (host or "").lower() in _LOOPBACK_HOSTS


def apply_local_defaults(environ: Mapping[str, str], *, project_root: Path) -> dict[str, str]:
    resolved = dict(environ)

    if not resolved.get("OPTIMUS_REDIS_URL", "").strip():
        resolved["OPTIMUS_REDIS_URL"] = _DEFAULT_REDIS_URL
    if not resolved.get("OPTIMUS_GATEWAY_URL", "").strip():
        resolved["OPTIMUS_GATEWAY_URL"] = _DEFAULT_GATEWAY_URL

    if not _is_loopback(urlparse(resolved["OPTIMUS_GATEWAY_URL"]).hostname):
        return resolved

    if not resolved.get("OPTIMUS_PRODUCTION_MODE", "").strip():
        resolved["OPTIMUS_PRODUCTION_MODE"] = "false"
    if not resolved.get("OPTIMUS_AGENT_MODEL", "").strip():
        resolved["OPTIMUS_AGENT_MODEL"] = _DEFAULT_LOCAL_AGENT_MODEL
    if not resolved.get("OPTIMUS_API_KEY", "").strip():
        shared_secret = resolve_shared_secret(resolved, project_root=project_root)
        if shared_secret:
            resolved["OPTIMUS_API_KEY"] = shared_secret

    return resolved


def strip_local_provider_keys(environ: Mapping[str, str]) -> dict[str, str]:
    """Produce the agent-facing environ view: never contains a real vendor key or the local
    gateway's own auth secret under its gateway-side name.

    ensure_local_gateway() legitimately reads provider keys and the shared secret from the
    UNSANITIZED environ to construct the spawned gateway's own child env. But
    OptimusGatewaySettings.from_env() — reached from build_configured_server and, in strict mode,
    run_preflight — explicitly rejects any LOCAL_PROVIDER_KEY_NAMES entry with
    ProviderKeyViolation (the anthropic-provider collision), and even where a name isn't on that
    reject list (OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY for openai/openrouter), it's still a real
    provider API key that should never sit in the agent's own view — see
    _AGENT_ENVIRON_EXCLUDED_KEYS above. The two call sites must never share one environ object.
    Callers pass this function's output to build_configured_server/run_preflight; they pass the
    original, unsanitized environ to ensure_local_gateway.
    """
    return {key: value for key, value in environ.items() if key not in _AGENT_ENVIRON_EXCLUDED_KEYS}


def _tcp_reachable(host: str, port: int, *, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _docker_daemon_reachable(docker: str) -> bool:
    try:
        result = subprocess.run([docker, "ps"], capture_output=True, text=True, check=False, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _container_exists(docker: str, name: str) -> bool:
    try:
        result = subprocess.run(
            [docker, "ps", "-a", "--filter", f"name=^/{name}$", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return name in result.stdout.split()


def ensure_local_redis(redis_url: str, *, log: Callable[[str], None] = _noop_log) -> None:
    parsed = urlparse(redis_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 6379
    if not _is_loopback(host):
        return
    if _tcp_reachable(host, port):
        return

    docker = shutil.which("docker")
    if docker is None:
        log("optimus-agent: docker not found on PATH; leaving Redis pre-flight to fail closed.")
        return
    if not _docker_daemon_reachable(docker):
        log("optimus-agent: Docker daemon not reachable; leaving Redis pre-flight to fail closed.")
        return

    if _container_exists(docker, _REDIS_CONTAINER_NAME):
        log(f"optimus-agent: starting existing {_REDIS_CONTAINER_NAME} container...")
        subprocess.run([docker, "start", _REDIS_CONTAINER_NAME], capture_output=True, text=True, check=False)
    else:
        log(f"optimus-agent: creating {_REDIS_CONTAINER_NAME} container ({_REDIS_IMAGE})...")
        subprocess.run(
            [docker, "run", "-d", "--name", _REDIS_CONTAINER_NAME, "-p", f"127.0.0.1:{port}:6379", _REDIS_IMAGE],
            capture_output=True,
            text=True,
            check=False,
        )

    deadline = time.monotonic() + _REDIS_READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _tcp_reachable(host, port):
            return
        time.sleep(_POLL_INTERVAL_SECONDS)
    log(f"optimus-agent: {_REDIS_CONTAINER_NAME} did not become reachable in time; leaving pre-flight to fail closed.")


@dataclass
class LocalGatewayProcess:
    process: subprocess.Popen | None
    log_path: Path | None

    def stop(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)


def ensure_local_gateway(
    *,
    environ: Mapping[str, str],
    project_root: Path,
    log: Callable[[str], None] = _noop_log,
) -> LocalGatewayProcess | None:
    gateway_url = environ.get("OPTIMUS_GATEWAY_URL", "").strip()
    if not gateway_url:
        return None
    parsed = urlparse(gateway_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8765
    if not _is_loopback(host):
        return None
    if _tcp_reachable(host, port):
        return None  # already up - ours from an earlier session, or someone else's; don't own it

    provider_secrets = resolve_provider_secrets(environ, project_root=project_root)
    shared_secret = resolve_shared_secret(environ, project_root=project_root)
    if provider_secrets is None or not shared_secret:
        log(
            "optimus-agent: no local gateway credentials found "
            "(run `optimus-agent --setup` or configure .env.gateway); "
            "leaving Gateway pre-flight to fail closed."
        )
        return None

    child_env: dict[str, str] = {
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER": provider_secrets.provider,
        "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": shared_secret,
        "OPTIMUS_LOCAL_GATEWAY_BIND_HOST": host,
        "OPTIMUS_LOCAL_GATEWAY_PORT": str(port),
        **provider_secrets.as_gateway_child_env(),
    }
    for key in _SYSTEM_ENV_KEYS:
        value = environ.get(key, "")
        if value:
            child_env[key] = value
    child_env["PYTHONPATH"] = str((project_root / "src").resolve())

    log_dir = project_root / "reports"
    log_path = log_dir / "local-gateway.log"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = open(log_path, "ab")
    except OSError as exc:
        log(f"optimus-agent: could not prepare local gateway log file ({exc}); leaving Gateway pre-flight to fail closed.")
        return None

    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "optimus_gateway"],
            env=child_env,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
    except OSError as exc:
        log(f"optimus-agent: could not start local gateway process ({exc}); leaving Gateway pre-flight to fail closed.")
        return None
    finally:
        log_file.close()  # the child holds its own duplicated fd; the parent doesn't need this one
    log(f"optimus-agent: starting local gateway (pid {process.pid}); logging to {log_path}")

    deadline = time.monotonic() + _GATEWAY_READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            log(f"optimus-agent: local gateway exited early (code {process.returncode}); see {log_path}")
            return None
        if _tcp_reachable(host, port):
            return LocalGatewayProcess(process=process, log_path=log_path)
        time.sleep(_POLL_INTERVAL_SECONDS)

    log(f"optimus-agent: local gateway did not become ready in time; see {log_path}")
    LocalGatewayProcess(process=process, log_path=log_path).stop()
    return None
```

- [x] **Step 4: Run tests** — confirm green.

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
probe logic to `--check-config --strict`, to keep it free of process side effects. **Also note:**
in strict mode, `_require_gateway_auth` (`preflight.py:99`) calls `OptimusGatewaySettings.from_env`
too — so the environ passed to `run_preflight` here must be the `strip_local_provider_keys()`-
sanitized one, same as `build_configured_server` below, not the unsanitized one `ensure_local_gateway`
uses.

**Two `environ` views, not one (2026-07-08 review finding):** `ensure_local_gateway` needs the
unsanitized `environ` (it may legitimately contain `ANTHROPIC_API_KEY` etc., read to build the
spawned gateway's own child env). But `build_configured_server` and strict `run_preflight` both
reach `OptimusGatewaySettings.from_env()`, which raises `ProviderKeyViolation` if any
`LOCAL_PROVIDER_KEY_NAMES` name is present. For the anthropic provider specifically, that's the
*same* variable name (`ANTHROPIC_API_KEY`) needed on one side and rejected on the other — so
passing one shared `environ` object to both would let an anthropic-provider auto-start spawn the
gateway successfully and then immediately crash agent startup with an unrelated-looking error.
`main()` must build a separate `agent_environ = strip_local_provider_keys(environ)` and pass
*that* — never the raw `environ` — to `build_configured_server`/`run_preflight`.

- [x] **Step 1: Write failing tests** asserting:
  - `--setup` calls `run_setup_wizard` and returns its exit code without touching
    preflight/server construction.
  - `--no-auto-start` skips both `ensure_local_redis` and `ensure_local_gateway` calls in the real
    serve path (assert via monkeypatched spies that neither was called).
  - `--no-auto-start` also skips `ensure_local_redis` in the `--check-config` branch (assert via
    spy), while `apply_local_defaults` still runs in both branches regardless of the flag.
  - Without `--no-auto-start`, the real serve path calls `apply_local_defaults`, then
    `ensure_local_redis`, then `ensure_local_gateway`, then `build_configured_server`, in that
    order (a dedicated ordering test, not just implied by the other tests), and calls `.stop()` on
    the returned `LocalGatewayProcess` after `serve`/`serve_ndjson` returns — but only when
    `ensure_local_gateway` returned a non-`None` handle (assert `.stop()` is not called when it
    returned `None`), and on the exception path both when `serve` raises AND when
    `build_configured_server` itself raises something other than `StartupConfigurationError`
    (two separate tests — an earlier draft of this plan only covered the `serve`-raises case).
  - Without `--no-auto-start`, `--check-config` calls `apply_local_defaults` and
    `ensure_local_redis` but does **not** call `ensure_local_gateway` (assert via spy/monkeypatch).
  - **Regression tests for the anthropic-collision finding above, plus its openrouter sibling
    (round 3 of review):** when `environ` (as returned by `apply_local_defaults`) contains
    `OPTIMUS_LOCAL_GATEWAY_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`, `ensure_local_gateway`
    must receive the value (asserted via a spy), while `build_configured_server` must never see it
    in its `environ` (asserted via a spy) — proving the two-`environ`-view split actually happens,
    not just that each function individually works. A second, sibling test does the same for
    `OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter` plus `OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY` and
    `OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET` — these don't trigger `ProviderKeyViolation` (they're not
    in `LOCAL_PROVIDER_KEY_NAMES`), so this case would pass silently without an explicit test even
    though it's still a real provider key reaching the agent view.

```python
import pytest

from optimus.acp import __main__ as acp_main


def test_setup_flag_calls_wizard_and_short_circuits(monkeypatch):
    calls = []
    monkeypatch.setattr(acp_main, "run_setup_wizard", lambda **kwargs: calls.append(kwargs) or 0)

    exit_code = acp_main.main(["--setup"])

    assert exit_code == 0
    assert len(calls) == 1


def _patch_common(monkeypatch, *, gateway_url="https://gateway.optimus.ai", server_factory=None):
    monkeypatch.setattr(
        acp_main,
        "apply_local_defaults",
        lambda environ, *, project_root: {
            "OPTIMUS_GATEWAY_URL": gateway_url,
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
        },
    )

    if server_factory is None:
        class FakeServer:
            def serve_ndjson(self, *_a, **_k):
                async def _noop():
                    return None
                return _noop()

        server_factory = lambda **k: FakeServer()

    monkeypatch.setattr(acp_main, "build_configured_server", server_factory)
    monkeypatch.setattr(acp_main, "StdioNdjsonLineReader", lambda *_a, **_k: object())
    monkeypatch.setattr(acp_main, "StdioNdjsonLineWriter", lambda *_a, **_k: object())


def test_no_auto_start_skips_redis_and_gateway_in_real_serve_path(monkeypatch, tmp_path):
    redis_calls = []
    gateway_calls = []
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: redis_calls.append((a, k)))
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: gateway_calls.append(k) or None)
    _patch_common(monkeypatch)

    exit_code = acp_main.main(["--no-auto-start", "--workspace-root", str(tmp_path)])

    assert exit_code == 0
    assert redis_calls == []
    assert gateway_calls == []


def test_check_config_never_calls_ensure_local_gateway(monkeypatch, tmp_path):
    gateway_calls = []
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: gateway_calls.append(k) or None)
    monkeypatch.setattr(acp_main, "run_preflight", lambda environ, **k: None)
    _patch_common(monkeypatch)

    exit_code = acp_main.main(["--check-config", "--workspace-root", str(tmp_path)])

    assert exit_code == 0
    assert gateway_calls == []


def test_no_auto_start_skips_redis_in_check_config_branch(monkeypatch, tmp_path):
    redis_calls = []
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: redis_calls.append((a, k)))
    monkeypatch.setattr(acp_main, "run_preflight", lambda environ, **k: None)
    _patch_common(monkeypatch)

    exit_code = acp_main.main(["--check-config", "--no-auto-start", "--workspace-root", str(tmp_path)])

    assert exit_code == 0
    assert redis_calls == []


def test_gateway_process_stopped_only_if_it_was_started(monkeypatch, tmp_path):
    stop_calls = []

    class FakeGatewayProcess:
        def stop(self):
            stop_calls.append("stopped")

    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: FakeGatewayProcess())
    _patch_common(monkeypatch, gateway_url="http://127.0.0.1:8765")

    exit_code = acp_main.main(["--workspace-root", str(tmp_path)])

    assert exit_code == 0
    assert stop_calls == ["stopped"]


def test_gateway_process_not_stopped_when_none_was_started(monkeypatch, tmp_path):
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: None)
    _patch_common(monkeypatch, gateway_url="http://127.0.0.1:8765")
    # No FakeGatewayProcess anywhere in this test — if main() ever calls .stop() on the None
    # returned by ensure_local_gateway, this test fails with AttributeError, not a soft assertion.

    exit_code = acp_main.main(["--workspace-root", str(tmp_path)])

    assert exit_code == 0


def test_gateway_process_stopped_when_serve_raises(monkeypatch, tmp_path):
    # Locks the fix for a leak an earlier draft of this plan had: only StartupConfigurationError
    # and the post-serve finally stopped the gateway, so any OTHER exception from serve (or from
    # build_configured_server itself) would leave a spawned gateway process orphaned.
    stop_calls = []

    class FakeGatewayProcess:
        def stop(self):
            stop_calls.append("stopped")

    class FailingServer:
        def serve_ndjson(self, *_a, **_k):
            async def _raise():
                raise RuntimeError("boom")
            return _raise()

    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: FakeGatewayProcess())
    _patch_common(monkeypatch, gateway_url="http://127.0.0.1:8765", server_factory=lambda **k: FailingServer())

    with pytest.raises(RuntimeError):
        acp_main.main(["--workspace-root", str(tmp_path)])

    assert stop_calls == ["stopped"]


def test_gateway_process_stopped_when_build_configured_server_raises_unexpectedly(monkeypatch, tmp_path):
    # Sibling to the serve-raises test above: this covers the OTHER half of the leak an earlier
    # draft had — build_configured_server itself raising something other than
    # StartupConfigurationError, before serve() is ever reached.
    stop_calls = []

    class FakeGatewayProcess:
        def stop(self):
            stop_calls.append("stopped")

    def raising_build_configured_server(**_k):
        raise ValueError("unexpected settings construction failure")

    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: FakeGatewayProcess())
    _patch_common(monkeypatch, gateway_url="http://127.0.0.1:8765", server_factory=raising_build_configured_server)

    with pytest.raises(ValueError):
        acp_main.main(["--workspace-root", str(tmp_path)])

    assert stop_calls == ["stopped"]


def test_real_serve_path_calls_helpers_in_expected_order(monkeypatch, tmp_path):
    call_order = []

    monkeypatch.setattr(
        acp_main,
        "apply_local_defaults",
        lambda environ, *, project_root: call_order.append("apply_local_defaults")
        or {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
        },
    )
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: call_order.append("ensure_local_redis"))
    monkeypatch.setattr(
        acp_main, "ensure_local_gateway", lambda **k: call_order.append("ensure_local_gateway") or None
    )

    class FakeServer:
        def serve_ndjson(self, *_a, **_k):
            async def _noop():
                return None
            return _noop()

    def fake_build_configured_server(**_k):
        call_order.append("build_configured_server")
        return FakeServer()

    monkeypatch.setattr(acp_main, "build_configured_server", fake_build_configured_server)
    monkeypatch.setattr(acp_main, "StdioNdjsonLineReader", lambda *_a, **_k: object())
    monkeypatch.setattr(acp_main, "StdioNdjsonLineWriter", lambda *_a, **_k: object())

    exit_code = acp_main.main(["--workspace-root", str(tmp_path)])

    assert exit_code == 0
    assert call_order == [
        "apply_local_defaults",
        "ensure_local_redis",
        "ensure_local_gateway",
        "build_configured_server",
    ]


def test_anthropic_provider_key_reaches_gateway_child_but_not_agent_settings(monkeypatch, tmp_path):
    # Regression test for the review finding: ANTHROPIC_API_KEY is both the var name
    # GatewayServiceConfig.from_env() reads for the anthropic provider AND a name
    # OptimusGatewaySettings.validate_no_local_provider_keys() explicitly rejects. The environ
    # ensure_local_gateway sees must still contain it (it needs to build the child env); the
    # environ build_configured_server sees must not (or agent startup would crash with
    # ProviderKeyViolation immediately after the gateway spawned successfully).
    gateway_environ_seen = {}
    agent_environ_seen = {}

    def fake_ensure_local_gateway(*, environ, project_root, log):
        gateway_environ_seen.update(environ)
        return None

    def fake_build_configured_server(*, environ, workspace_root, model):
        agent_environ_seen.update(environ)

        class FakeServer:
            def serve_ndjson(self, *_a, **_k):
                async def _noop():
                    return None
                return _noop()

        return FakeServer()

    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "ensure_local_gateway", fake_ensure_local_gateway)
    monkeypatch.setattr(acp_main, "build_configured_server", fake_build_configured_server)
    monkeypatch.setattr(acp_main, "StdioNdjsonLineReader", lambda *_a, **_k: object())
    monkeypatch.setattr(acp_main, "StdioNdjsonLineWriter", lambda *_a, **_k: object())
    monkeypatch.setattr(
        acp_main,
        "apply_local_defaults",
        lambda environ, *, project_root: {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "shared-secret",
            "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER": "anthropic",
            "ANTHROPIC_API_KEY": "sk-ant-real",
        },
    )

    exit_code = acp_main.main(["--workspace-root", str(tmp_path)])

    assert exit_code == 0
    assert gateway_environ_seen["ANTHROPIC_API_KEY"] == "sk-ant-real"  # gateway spawn legitimately sees it
    assert "ANTHROPIC_API_KEY" not in agent_environ_seen  # agent settings never do


def test_openrouter_provider_key_reaches_gateway_child_but_not_agent_settings(monkeypatch, tmp_path):
    # Sibling to the anthropic regression test above (2026-07-08 review, round 3):
    # OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY doesn't trigger ProviderKeyViolation (it isn't in
    # LOCAL_PROVIDER_KEY_NAMES), so this doesn't crash agent startup the way the anthropic case
    # does — but it's still a real provider API key and must not reach the agent-facing environ.
    gateway_environ_seen = {}
    agent_environ_seen = {}

    def fake_ensure_local_gateway(*, environ, project_root, log):
        gateway_environ_seen.update(environ)
        return None

    def fake_build_configured_server(*, environ, workspace_root, model):
        agent_environ_seen.update(environ)

        class FakeServer:
            def serve_ndjson(self, *_a, **_k):
                async def _noop():
                    return None
                return _noop()

        return FakeServer()

    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "ensure_local_gateway", fake_ensure_local_gateway)
    monkeypatch.setattr(acp_main, "build_configured_server", fake_build_configured_server)
    monkeypatch.setattr(acp_main, "StdioNdjsonLineReader", lambda *_a, **_k: object())
    monkeypatch.setattr(acp_main, "StdioNdjsonLineWriter", lambda *_a, **_k: object())
    monkeypatch.setattr(
        acp_main,
        "apply_local_defaults",
        lambda environ, *, project_root: {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "shared-secret",
            "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER": "openrouter",
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "sk-or-real",
            "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "shared-secret",
        },
    )

    exit_code = acp_main.main(["--workspace-root", str(tmp_path)])

    assert exit_code == 0
    assert gateway_environ_seen["OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY"] == "sk-or-real"
    assert "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY" not in agent_environ_seen
    assert "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET" not in agent_environ_seen
```

- [x] **Step 2: Run tests, confirm failure.**

- [x] **Step 3: Implement wiring** in `main()`:

```python
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from optimus.acp.bootstrap import StartupConfigurationError, build_configured_server
from optimus.acp.local_gateway_secrets import run_setup_wizard
from optimus.acp.local_infra import (
    apply_local_defaults,
    ensure_local_gateway,
    ensure_local_redis,
    strip_local_provider_keys,
)
from optimus.acp.preflight import PreflightFailure, run_preflight
from optimus.acp.server import StdioByteReader, StdioByteWriter, StdioNdjsonLineReader, StdioNdjsonLineWriter


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _print_log(message: str) -> None:
    print(message, file=sys.stderr)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="optimus-agent")
    parser.add_argument("--workspace-root", default=".", help="Workspace root exposed to the ACP agent.")
    parser.add_argument("--model", default=None, help="Gateway model for agent planning.")
    parser.add_argument("--check-config", action="store_true", help="Validate configuration and exit.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="With --check-config, probe gateway authentication in addition to Redis checks.",
    )
    parser.add_argument(
        "--framed",
        action="store_true",
        help="Use Content-Length framed JSON-RPC instead of newline-delimited JSON (IDE default is ndjson).",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Interactively store local gateway credentials in the OS keychain, then exit.",
    )
    parser.add_argument(
        "--no-auto-start",
        action="store_true",
        help="Do not auto-start local Redis or the local gateway process; assume they are already running.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    if args.setup:
        return run_setup_wizard(project_root=_project_root())

    workspace_root = Path(args.workspace_root)
    # `environ` may legitimately contain a real vendor key (e.g. ANTHROPIC_API_KEY in the
    # operator's own shell, or resolved from .env.gateway/keyring) — ensure_local_gateway needs
    # that to construct the spawned gateway's child env. It must NEVER be the same object passed
    # to build_configured_server/run_preflight, both of which reach
    # OptimusGatewaySettings.from_env(), which rejects any LOCAL_PROVIDER_KEY_NAMES entry with
    # ProviderKeyViolation. agent_environ (built just below each use) is that separate, sanitized
    # view. See the anthropic-collision finding in Source Anchors / Confirmed Design Decisions.
    environ = apply_local_defaults(os.environ, project_root=_project_root())

    if args.check_config:
        if not args.no_auto_start:
            ensure_local_redis(environ["OPTIMUS_REDIS_URL"], log=_print_log)
        agent_environ = strip_local_provider_keys(environ)
        try:
            run_preflight(
                agent_environ,
                workspace_root=workspace_root,
                strict=args.strict,
                require_timeseries=True,
            )
        except PreflightFailure as exc:
            print(exc.user_message, file=sys.stderr)
            return exc.exit_code
        print("Optimus ACP agent configuration OK.", file=sys.stderr)
        return 0

    gateway_process = None
    if not args.no_auto_start:
        ensure_local_redis(environ["OPTIMUS_REDIS_URL"], log=_print_log)
        gateway_process = ensure_local_gateway(environ=environ, project_root=_project_root(), log=_print_log)

    agent_environ = strip_local_provider_keys(environ)

    # Single try/finally around BOTH build_configured_server(...) and serve(...): an earlier draft
    # of this plan wrapped only the serve() call, so an unexpected (non-StartupConfigurationError)
    # exception from build_configured_server() would skip both the except block below and the
    # inner finally, leaking the already-spawned gateway_process. Nesting everything inside one
    # outer finally means every exit path — normal completion, StartupConfigurationError, or any
    # other exception — stops it exactly once.
    try:
        try:
            server = build_configured_server(environ=agent_environ, workspace_root=workspace_root, model=args.model)
        except StartupConfigurationError as exc:
            print(exc.user_message, file=sys.stderr)
            return exc.exit_code

        if args.framed:
            asyncio.run(server.serve(StdioByteReader(sys.stdin.buffer), StdioByteWriter(sys.stdout.buffer)))
        else:
            asyncio.run(
                server.serve_ndjson(
                    StdioNdjsonLineReader(sys.stdin.buffer),
                    StdioNdjsonLineWriter(sys.stdout.buffer),
                )
            )
    finally:
        if gateway_process is not None:
            gateway_process.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [x] **Step 4: Run tests** — confirm green.

## Task 4: Preflight Message Update

**Files:**
- Modify: `src/optimus/acp/preflight.py`
- Modify: `tests/unit/acp/test_preflight.py`

- [ ] **Step 1:** Verified (2026-07-08): `tests/unit/acp/test_preflight.py:57` already asserts
  `assert "OPTIMUS_GATEWAY_URL" in exc_info.value.user_message` — a substring check, not exact
  equality — so appending a clause below is additive and this existing test does not need to
  change.

- [ ] **Step 2:** In `src/optimus/acp/preflight.py`, `_require_gateway_credentials`:

```python
# Before
def _require_gateway_credentials(environ: Mapping[str, str]) -> None:
    missing = tuple(name for name in ("OPTIMUS_GATEWAY_URL", "OPTIMUS_API_KEY") if not environ.get(name, "").strip())
    if missing:
        raise PreflightFailure(
            exit_code=2,
            user_message="Set OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY before launching the Optimus ACP agent.",
        )

# After
def _require_gateway_credentials(environ: Mapping[str, str]) -> None:
    missing = tuple(name for name in ("OPTIMUS_GATEWAY_URL", "OPTIMUS_API_KEY") if not environ.get(name, "").strip())
    if missing:
        raise PreflightFailure(
            exit_code=2,
            user_message=(
                "Set OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY before launching the Optimus ACP agent "
                "(or run `optimus-agent --setup` to configure the local gateway)."
            ),
        )
```

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
