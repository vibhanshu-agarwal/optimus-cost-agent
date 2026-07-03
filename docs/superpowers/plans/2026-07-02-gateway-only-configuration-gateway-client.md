# Gateway-Only Configuration and Gateway Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build the Phase 1 gateway-only configuration model and typed Optimus Gateway client so local runtime needs only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`.

**Architecture:** Add a focused `optimus.config` package for `OptimusGatewaySettings`, trusted origin validation, local provider-key handling, and masked secret serialization. Add a focused `optimus.gateway` package for request payload construction, authorization, sync HTTP transport, gateway usage envelope parsing, and typed fail-closed gateway errors. Wire one minimal ACP method to the gateway client so the transport foundation can exercise a mocked `/v1/responses` call without any local provider credential.

**Tech Stack:** Python >=3.14, pydantic >=2.8, pytest, pytest-asyncio, coverage.py, pytest-cov, stdlib `urllib.request`, stdlib `urllib.error`, stdlib `decimal`, stdlib `json`.

---

## Source Anchors

- `docs/Optimus-Cost-Agent-Architecture-v2.15.pdf`, section 5A: `OPTIMUS_API_KEY` maps to a tenant/user/project wallet; upstream provider keys are owned by the gateway and never configured locally.
- `docs/Optimus-Cost-Agent-Architecture-v2.15.pdf`, section 11: all model completions and tool calls flow through the Optimus AI Gateway; local runtime holds only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; every response includes gateway usage fields.
- `docs/Optimus-Cost-Agent-LLD-v2.38.pdf`, section 0A: Phase 1 local runtime configuration allows only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; local Tavily, OpenAI, OpenRouter, GLM, LangSmith, and provider keys are rejected for Phase 1 runtime use.
- `docs/Optimus-Cost-Agent-LLD-v2.38.pdf`, section 0A: model completions use `POST /v1/responses` with Responses API `input`; the gateway injects server-side provider keys and returns `gateway_request_id`, `cost_usd`, `billing_units`, and `cache_hit`.
- `docs/Optimus-Cost-Agent-Test-Strategy-v1.4.pdf`, section 7: `OptimusGatewaySettings` origin allowlist, production-mode handling, masked API key, `/v1/responses` request shape, auth headers, and one-key mocked run coverage.
- `docs/superpowers/plans/2026-07-01-mode-state-machine-mutation-guard.md`: Plan 2 foundation for `RuntimeContext`, `ExecutionMode`, `AgentState`, and JSON-RPC dispatcher extension points.
- `AGENTS.md`: local runtime credentials are limited to `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; provider keys must not be loaded locally; use TDD and keep coverage >= 80%.

## Scope

### In Scope

- Runtime dependency on Pydantic v2 because the authoritative Test Strategy calls this a Pydantic model surface and requires `SecretStr` masking behavior.
- `OptimusGatewaySettings` with:
  - `gateway_url`
  - `optimus_api_key`
  - `production_mode`
  - `extra_trusted_origins`
  - `signed_tenant_profile_origins`
  - `provider_key_policy`
- Built-in trusted origin validation for `https://gateway.optimus.ai`.
- Development/test-only support for `OPTIMUS_EXTRA_GATEWAY_ORIGINS`.
- Production-mode rejection of `extra_trusted_origins`; production-mode acceptance only for built-in origins and explicit signed tenant profile origins.
- `signed_tenant_profile_origins` is treated as an already-verified input seam only; this plan does not implement tenant profile signature verification or loading.
- Authorization header construction: `{"Authorization": "Bearer <OPTIMUS_API_KEY>"}`.
- Deterministic local provider-key detection for common provider and observability key names.
- Provider key handling that rejects at the env-bootstrap seam in production/default strict mode and ignores without loading in explicit non-production ignore mode.
- `/v1/responses` request payload construction using `input`, not `messages`.
- `/v1/chat/completions` payload construction using `messages`, not `input`, to prove endpoint shapes are not mixed.
- Sync `GatewayClient` with an injectable transport for unit/integration tests.
- Direct unit coverage for the stdlib `UrllibGatewayTransport` production transport seam.
- Billing-safe JSON decoding that preserves numeric gateway `cost_usd` values as `Decimal`.
- Typed errors for HTTP failures and malformed gateway responses.
- Minimal `GatewayUsage` parsing from gateway response fields.
- Responses-compatible `output` array text extraction fallback, covered by tests.
- Minimal ACP dispatch path for a mocked gateway response call. Gateway model calls are intentionally allowed in Plan/Chat mode because they are advisory generation calls, not local file/shell mutation; wallet/budget enforcement remains gateway-side.
- Tests proving only Optimus credentials are required for a mocked full gateway run.

### Out of Scope

- Tool policy, web search/extract wrappers, URL provenance, and evidence acquisition. Those belong to Plan 4.
- ProviderUsage persistence, Redis HASH/TimeSeries writes, EvidenceLedger reconciliation, and observability export. Those belong to Plan 7.
- Retry/backoff, transient/permanent classification, and composite release gates. Those belong to Plan 8.
- Staging gateway E2E tests, provider failover, cache pricing, and server-side gateway policy revalidation. This plan creates client-side seams; staging validation lands in release-gate work.
- Network egress instrumentation with respx or mitmproxy. This repo has no HTTP test dependency yet; this plan uses an injectable transport and leaves outbound intercept tooling to a later release-gate slice.
- Secret scanning of config files or process state beyond deterministic environment key handling in this slice.
- Signature verification for tenant gateway profiles. A later enterprise trust-profile plan must verify signatures before passing origins into `signed_tenant_profile_origins`; this slice only models the post-verification setting.
- Environment-driven opt-in to `ProviderKeyPolicy.IGNORE`. `from_env()` intentionally defaults to strict rejection and does not read a provider-key-policy environment variable in this slice.

## File Structure

- Modify: `pyproject.toml` - add runtime dependency `pydantic>=2.8`.
- Modify: `uv.lock` - refresh dependency lock after updating `pyproject.toml`.
- Create: `src/optimus/config/__init__.py` - public settings exports.
- Create: `src/optimus/config/gateway.py` - `OptimusGatewaySettings`, provider-key policy, origin validation, env loading, auth headers, and secret-safe dumps.
- Create: `src/optimus/gateway/__init__.py` - public gateway exports.
- Create: `src/optimus/gateway/errors.py` - typed gateway error hierarchy.
- Create: `src/optimus/gateway/models.py` - `GatewayUsage`, `GatewayResponse`, payload builders, and response parser.
- Create: `src/optimus/gateway/client.py` - sync gateway client, request envelope, stdlib transport, and injectable transport protocol.
- Modify: `src/optimus/acp/dispatcher.py` - optional gateway client dependency and `optimus.gateway.responses` dispatch method.
- Modify: `README.md` - add Phase 1 gateway-only configuration note.
- Create: `tests/unit/config/test_gateway_settings.py` - settings, masking, origins, env loading, provider-key handling.
- Create: `tests/unit/gateway/test_models.py` - payload shapes and response parsing.
- Create: `tests/unit/gateway/test_client.py` - auth/header/URL construction, transport calls, typed errors.
- Modify: `tests/unit/acp/test_dispatcher.py` - ACP mocked gateway dispatch coverage.
- Create: `tests/integration/gateway/test_one_key_mocked_run.py` - mocked full gateway run with only Optimus credentials.

## Human Agile Sizing

This plan is sized for roughly 2 weeks of human development effort:

- Days 1-2: dependency update, settings model, env loading, and secret masking.
- Days 3-4: trusted origin validation and provider-key policy.
- Days 5-7: gateway payload builders, usage parsing, and typed errors.
- Days 8-9: gateway client with injectable transport and stdlib HTTP transport.
- Days 10-11: ACP integration and mocked one-key run.
- Days 12-13: README, focused coverage, full tests, and implementation review.

## Task 1: Add Pydantic Runtime Dependency

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`

- [x] **Step 1: Write the dependency expectation test**

Append to `tests/unit/test_package_imports.py`:

```python
def test_pydantic_is_available_for_gateway_settings():
    import pydantic

    assert pydantic.VERSION.split(".")[0] == "2"
```

- [x] **Step 2: Run the test to verify it fails or confirms the missing declared dependency**

Run:

```bash
pytest tests/unit/test_package_imports.py::test_pydantic_is_available_for_gateway_settings -v
```

Expected before dependency update: FAIL with `ModuleNotFoundError: No module named 'pydantic'` if the local environment is clean. If it passes because another package installed Pydantic transitively, still continue because `pyproject.toml` must declare the runtime dependency explicitly.

- [x] **Step 3: Add Pydantic to runtime dependencies**

Update `pyproject.toml`:

```toml
[project]
name = "optimus-cost-agent"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
  "pydantic>=2.8",
]
```

- [x] **Step 4: Refresh the lockfile**

Run:

```bash
uv lock
```

Expected: `uv.lock` updates with Pydantic and its transitive dependencies.

- [x] **Step 5: Sync the local environment**

Run:

```bash
uv sync --all-extras
```

Expected: the active project environment installs the locked Pydantic dependency and dev test dependencies.

- [x] **Step 6: Run the dependency test**

Run:

```bash
pytest tests/unit/test_package_imports.py::test_pydantic_is_available_for_gateway_settings -v
```

Expected: PASS.

- [x] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock tests/unit/test_package_imports.py
git commit -m "Declare Pydantic for gateway settings."
```

## Task 2: Gateway Settings, Secret Masking, and Auth Headers

**Files:**
- Create: `src/optimus/config/__init__.py`
- Create: `src/optimus/config/gateway.py`
- Test: `tests/unit/config/test_gateway_settings.py`

- [x] **Step 1: Write failing settings and masking tests**

Create `tests/unit/config/test_gateway_settings.py`:

```python
import pytest
from pydantic import ValidationError

from optimus.config.gateway import (
    BUILT_IN_TRUSTED_GATEWAY_ORIGINS,
    OptimusGatewaySettings,
)


def test_builtin_gateway_origin_is_trusted():
    settings = OptimusGatewaySettings(
        gateway_url="https://gateway.optimus.ai",
        optimus_api_key="opt_live_abc",
    )

    assert settings.validate_trusted_gateway() is None


def test_auth_headers_use_optimus_key_only():
    settings = OptimusGatewaySettings(
        gateway_url="https://gateway.optimus.ai",
        optimus_api_key="opt_live_abc",
    )

    assert settings.auth_headers() == {"Authorization": "Bearer opt_live_abc"}


def test_secret_is_masked_in_repr_str_and_model_dump():
    settings = OptimusGatewaySettings(
        gateway_url="https://gateway.optimus.ai",
        optimus_api_key="opt_live_secret",
    )

    assert "opt_live_secret" not in repr(settings)
    assert "**********" in repr(settings)
    assert "opt_live_secret" not in str(settings)
    assert "**********" in str(settings)
    dumped = settings.safe_model_dump()
    assert dumped["optimus_api_key"] == "**********"
    assert "opt_live_secret" not in str(dumped)


def test_empty_api_key_is_rejected():
    with pytest.raises(ValidationError):
        OptimusGatewaySettings(
            gateway_url="https://gateway.optimus.ai",
            optimus_api_key="",
        )


def test_builtin_origin_constant_is_exact_phase_1_origin():
    assert BUILT_IN_TRUSTED_GATEWAY_ORIGINS == frozenset({"https://gateway.optimus.ai"})
```

- [x] **Step 2: Run the tests to verify they fail**

Run:

```bash
pytest tests/unit/config/test_gateway_settings.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'optimus.config'`.

- [x] **Step 3: Implement settings model and auth headers**

Create `src/optimus/config/__init__.py`:

```python
"""Configuration models for Optimus Cost Agent."""

from optimus.config.gateway import (
    BUILT_IN_TRUSTED_GATEWAY_ORIGINS,
    OptimusGatewaySettings,
    ProviderKeyPolicy,
    ProviderKeyViolation,
)

__all__ = [
    "BUILT_IN_TRUSTED_GATEWAY_ORIGINS",
    "OptimusGatewaySettings",
    "ProviderKeyPolicy",
    "ProviderKeyViolation",
]
```

Create `src/optimus/config/gateway.py`:

```python
from __future__ import annotations

import os
from enum import StrEnum
from typing import Mapping
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

BUILT_IN_TRUSTED_GATEWAY_ORIGINS = frozenset({"https://gateway.optimus.ai"})


class ProviderKeyPolicy(StrEnum):
    REJECT = "reject"
    IGNORE = "ignore"


class ProviderKeyViolation(ValueError):
    def __init__(self, keys: list[str]) -> None:
        self.keys = keys
        super().__init__(f"local provider keys are not allowed: {', '.join(keys)}")


class OptimusGatewaySettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    gateway_url: str
    optimus_api_key: SecretStr = Field(min_length=1)
    production_mode: bool = True
    extra_trusted_origins: tuple[str, ...] = ()
    # Populated only by an already-verified tenant profile loader. This model
    # stores verified origins; it does not perform signature verification.
    signed_tenant_profile_origins: tuple[str, ...] = ()
    provider_key_policy: ProviderKeyPolicy = ProviderKeyPolicy.REJECT

    @field_validator("gateway_url", mode="before")
    @classmethod
    def strip_gateway_url(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().rstrip("/")
        return value

    @field_validator("extra_trusted_origins", "signed_tenant_profile_origins", mode="before")
    @classmethod
    def normalize_origin_tuple(cls, value: object) -> object:
        if value is None or value == "":
            return ()
        if isinstance(value, str):
            return tuple(_normalize_origin(part) for part in value.split(",") if part.strip())
        return tuple(_normalize_origin(str(part)) for part in value)

    @model_validator(mode="after")
    def validate_production_extra_origins(self) -> OptimusGatewaySettings:
        if self.production_mode and self.extra_trusted_origins:
            raise ValueError("extra_trusted_origins must not be set in production_mode")
        return self

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> OptimusGatewaySettings:
        env = os.environ if environ is None else environ
        production_mode = _env_bool(env.get("OPTIMUS_PRODUCTION_MODE"), default=True)
        extra_origins = "" if production_mode else env.get("OPTIMUS_EXTRA_GATEWAY_ORIGINS", "")
        return cls(
            gateway_url=_required_env(env, "OPTIMUS_GATEWAY_URL"),
            optimus_api_key=_required_env(env, "OPTIMUS_API_KEY"),
            production_mode=production_mode,
            extra_trusted_origins=extra_origins,
        )

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.optimus_api_key.get_secret_value()}"}

    def validate_trusted_gateway(self) -> None:
        origin = _origin(self.gateway_url)
        trusted = set(BUILT_IN_TRUSTED_GATEWAY_ORIGINS)
        trusted.update(self.signed_tenant_profile_origins)
        if not self.production_mode:
            trusted.update(self.extra_trusted_origins)
        if origin not in trusted:
            raise ValueError(f"gateway origin not in trusted set: {origin}")

    def safe_model_dump(self) -> dict[str, object]:
        data = self.model_dump()
        data["optimus_api_key"] = "**********"
        return data


def _required_env(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if value is None or value.strip() == "":
        raise ValueError(f"{name} is required")
    return value


def _env_bool(value: str | None, *, default: bool) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_origin(value: str) -> str:
    parsed = urlparse(value.strip().rstrip("/"))
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"gateway origin must be an https origin: {value}")
    return f"{parsed.scheme}://{parsed.netloc.lower()}"


def _origin(url: str) -> str:
    return _normalize_origin(url)
```

- [x] **Step 4: Run settings tests**

Run:

```bash
pytest tests/unit/config/test_gateway_settings.py -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/optimus/config tests/unit/config/test_gateway_settings.py
git commit -m "Add gateway settings and auth headers."
```

## Task 3: Trusted Origins, Env Loading, and Provider-Key Handling

**Files:**
- Modify: `src/optimus/config/gateway.py`
- Test: `tests/unit/config/test_gateway_settings.py`

- [x] **Step 1: Add failing origin and provider-key policy tests**

Append to `tests/unit/config/test_gateway_settings.py`:

```python
from optimus.config.gateway import ProviderKeyPolicy, ProviderKeyViolation


def test_rogue_gateway_origin_is_rejected():
    settings = OptimusGatewaySettings(
        gateway_url="https://rogue.attacker.com",
        optimus_api_key="opt_live_abc",
    )

    with pytest.raises(ValueError, match="gateway origin not in trusted set"):
        settings.validate_trusted_gateway()


def test_non_production_extra_origin_is_accepted():
    settings = OptimusGatewaySettings(
        gateway_url="https://internal.corp.com/path",
        optimus_api_key="opt_live_abc",
        production_mode=False,
        extra_trusted_origins=("https://internal.corp.com",),
    )

    assert settings.validate_trusted_gateway() is None


def test_production_extra_origins_are_rejected():
    with pytest.raises(ValueError, match="extra_trusted_origins must not be set in production_mode"):
        OptimusGatewaySettings(
            gateway_url="https://gateway.optimus.ai",
            optimus_api_key="opt_live_abc",
            production_mode=True,
            extra_trusted_origins=("https://internal.corp.com",),
        )


def test_production_env_ignores_extra_gateway_origins():
    settings = OptimusGatewaySettings.from_env(
        {
            "OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai",
            "OPTIMUS_API_KEY": "opt_live_abc",
            "OPTIMUS_PRODUCTION_MODE": "true",
            "OPTIMUS_EXTRA_GATEWAY_ORIGINS": "https://internal.corp.com",
        }
    )

    assert settings.production_mode is True
    assert settings.extra_trusted_origins == ()


def test_non_production_env_loads_extra_gateway_origins():
    settings = OptimusGatewaySettings.from_env(
        {
            "OPTIMUS_GATEWAY_URL": "https://internal.corp.com",
            "OPTIMUS_API_KEY": "opt_live_abc",
            "OPTIMUS_PRODUCTION_MODE": "false",
            "OPTIMUS_EXTRA_GATEWAY_ORIGINS": "https://internal.corp.com",
        }
    )

    assert settings.production_mode is False
    assert settings.extra_trusted_origins == ("https://internal.corp.com",)
    assert settings.validate_trusted_gateway() is None


def test_already_verified_signed_tenant_profile_origin_is_accepted_in_production():
    settings = OptimusGatewaySettings(
        gateway_url="https://tenant-gateway.example.com",
        optimus_api_key="opt_live_abc",
        production_mode=True,
        signed_tenant_profile_origins=("https://tenant-gateway.example.com",),
    )

    assert settings.validate_trusted_gateway() is None


def test_from_env_rejects_provider_keys_in_production():
    with pytest.raises(ProviderKeyViolation) as exc_info:
        OptimusGatewaySettings.from_env(
            {
                "OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai",
                "OPTIMUS_API_KEY": "opt_live_abc",
                "OPTIMUS_PRODUCTION_MODE": "true",
                "OPENAI_API_KEY": "sk-local",
            }
        )

    assert exc_info.value.keys == ["OPENAI_API_KEY"]


def test_from_env_validates_trusted_gateway_before_returning_settings():
    with pytest.raises(ValueError, match="gateway origin not in trusted set"):
        OptimusGatewaySettings.from_env(
            {
                "OPTIMUS_GATEWAY_URL": "https://rogue.attacker.com",
                "OPTIMUS_API_KEY": "opt_live_abc",
                "OPTIMUS_PRODUCTION_MODE": "true",
            }
        )


def test_provider_keys_are_rejected_by_default():
    settings = OptimusGatewaySettings(
        gateway_url="https://gateway.optimus.ai",
        optimus_api_key="opt_live_abc",
    )

    with pytest.raises(ProviderKeyViolation) as exc_info:
        settings.validate_no_local_provider_keys(
            {
                "OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai",
                "OPTIMUS_API_KEY": "opt_live_abc",
                "OPENAI_API_KEY": "sk-local",
                "TAVILY_API_KEY": "tvly-local",
                "LANGSMITH_API_KEY": "lsv2-local",
            }
        )

    assert exc_info.value.keys == ["LANGSMITH_API_KEY", "OPENAI_API_KEY", "TAVILY_API_KEY"]


def test_provider_keys_can_be_ignored_without_loading_in_non_production():
    settings = OptimusGatewaySettings(
        gateway_url="https://gateway.optimus.ai",
        optimus_api_key="opt_live_abc",
        production_mode=False,
        provider_key_policy=ProviderKeyPolicy.IGNORE,
    )

    ignored = settings.validate_no_local_provider_keys(
        {
            "OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai",
            "OPTIMUS_API_KEY": "opt_live_abc",
            "OPENROUTER_API_KEY": "or-local",
            "GLM_API_KEY": "glm-local",
        }
    )

    assert ignored == ("GLM_API_KEY", "OPENROUTER_API_KEY")
    assert "or-local" not in repr(ignored)
    assert "glm-local" not in repr(ignored)


def test_ignore_policy_cannot_be_used_in_production():
    with pytest.raises(ValueError, match="provider_key_policy=ignore is valid only outside production_mode"):
        OptimusGatewaySettings(
            gateway_url="https://gateway.optimus.ai",
            optimus_api_key="opt_live_abc",
            production_mode=True,
            provider_key_policy=ProviderKeyPolicy.IGNORE,
        )
```

- [x] **Step 2: Run the tests to verify they fail**

Run:

```bash
pytest tests/unit/config/test_gateway_settings.py -v
```

Expected: FAIL with missing `validate_no_local_provider_keys`, missing bootstrap validation, and ignore-policy production validation.

- [x] **Step 3: Implement provider-key policy**

Update `src/optimus/config/gateway.py`:

```python
LOCAL_PROVIDER_KEY_NAMES = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "GLM_API_KEY",
        "LANGCHAIN_API_KEY",
        "LANGSMITH_API_KEY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "TAVILY_API_KEY",
        "ZHIPUAI_API_KEY",
    }
)
```

Update `OptimusGatewaySettings.validate_production_extra_origins`:

```python
    @model_validator(mode="after")
    def validate_production_constraints(self) -> OptimusGatewaySettings:
        if self.production_mode and self.extra_trusted_origins:
            raise ValueError("extra_trusted_origins must not be set in production_mode")
        if self.production_mode and self.provider_key_policy is ProviderKeyPolicy.IGNORE:
            raise ValueError("provider_key_policy=ignore is valid only outside production_mode")
        return self
```

Add the provider-key method to `OptimusGatewaySettings`:

```python
    def validate_no_local_provider_keys(self, environ: Mapping[str, str] | None = None) -> tuple[str, ...]:
        env = os.environ if environ is None else environ
        found = sorted(name for name in LOCAL_PROVIDER_KEY_NAMES if env.get(name))
        if not found:
            return ()
        if self.provider_key_policy is ProviderKeyPolicy.IGNORE and not self.production_mode:
            return tuple(found)
        raise ProviderKeyViolation(found)
```

Update `OptimusGatewaySettings.from_env()` so env bootstrap validates both the gateway origin and local provider-key absence before returning settings:

```python
    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> OptimusGatewaySettings:
        env = os.environ if environ is None else environ
        production_mode = _env_bool(env.get("OPTIMUS_PRODUCTION_MODE"), default=True)
        extra_origins = "" if production_mode else env.get("OPTIMUS_EXTRA_GATEWAY_ORIGINS", "")
        settings = cls(
            gateway_url=_required_env(env, "OPTIMUS_GATEWAY_URL"),
            optimus_api_key=_required_env(env, "OPTIMUS_API_KEY"),
            production_mode=production_mode,
            extra_trusted_origins=extra_origins,
        )
        settings.validate_trusted_gateway()
        settings.validate_no_local_provider_keys(env)
        return settings
```

Update `src/optimus/config/__init__.py` imports and `__all__`:

```python
from optimus.config.gateway import (
    BUILT_IN_TRUSTED_GATEWAY_ORIGINS,
    LOCAL_PROVIDER_KEY_NAMES,
    OptimusGatewaySettings,
    ProviderKeyPolicy,
    ProviderKeyViolation,
)

__all__ = [
    "BUILT_IN_TRUSTED_GATEWAY_ORIGINS",
    "LOCAL_PROVIDER_KEY_NAMES",
    "OptimusGatewaySettings",
    "ProviderKeyPolicy",
    "ProviderKeyViolation",
]
```

- [x] **Step 4: Run settings tests**

Run:

```bash
pytest tests/unit/config/test_gateway_settings.py -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/optimus/config tests/unit/config/test_gateway_settings.py
git commit -m "Validate gateway origins and local provider keys."
```

## Task 4: Gateway Payload Builders and Usage Parsing

**Files:**
- Create: `src/optimus/gateway/__init__.py`
- Create: `src/optimus/gateway/errors.py`
- Create: `src/optimus/gateway/models.py`
- Test: `tests/unit/gateway/test_models.py`

- [x] **Step 1: Write failing payload and parser tests**

Create `tests/unit/gateway/test_models.py`:

```python
from decimal import Decimal

import pytest
from pydantic import ValidationError

from optimus.gateway.errors import GatewayResponseError
from optimus.gateway.models import (
    GatewayResponse,
    GatewayUsage,
    build_chat_completions_payload,
    build_responses_payload,
    parse_gateway_response,
)


def test_responses_payload_uses_input_not_messages():
    payload = build_responses_payload(
        model="glm-5.2",
        input_text="Explain the change.",
        metadata={"run_id": "run-1"},
    )

    assert payload == {
        "model": "glm-5.2",
        "input": "Explain the change.",
        "metadata": {"run_id": "run-1"},
    }
    assert "messages" not in payload


def test_chat_completions_payload_uses_messages_not_input():
    messages = [{"role": "user", "content": "hello"}]

    payload = build_chat_completions_payload(model="claude-haiku", messages=messages)

    assert payload == {"model": "claude-haiku", "messages": messages}
    assert "input" not in payload


def test_gateway_usage_rejects_negative_values():
    with pytest.raises(ValidationError):
        GatewayUsage(
            gateway_request_id="gw-1",
            provider="openai",
            cache_hit=False,
            billing_units=-1,
            cost_usd=Decimal("0.01"),
        )

    with pytest.raises(ValidationError):
        GatewayUsage(
            gateway_request_id="gw-1",
            provider="openai",
            cache_hit=False,
            billing_units=1,
            cost_usd=Decimal("-0.01"),
        )


def test_parse_gateway_response_extracts_output_and_usage():
    parsed = parse_gateway_response(
        {
            "id": "resp-1",
            "output_text": "done",
            "gateway_usage": {
                "gateway_request_id": "gw-1",
                "provider": "glm",
                "provider_request_id": "provider-1",
                "cache_hit": False,
                "billing_units": 42,
                "cost_usd": "0.0042",
            },
        }
    )

    assert parsed == GatewayResponse(
        response_id="resp-1",
        output_text="done",
        gateway_usage=GatewayUsage(
            gateway_request_id="gw-1",
            provider="glm",
            provider_request_id="provider-1",
            cache_hit=False,
            billing_units=42,
            cost_usd=Decimal("0.0042"),
        ),
        raw={
            "id": "resp-1",
            "output_text": "done",
            "gateway_usage": {
                "gateway_request_id": "gw-1",
                "provider": "glm",
                "provider_request_id": "provider-1",
                "cache_hit": False,
                "billing_units": 42,
                "cost_usd": "0.0042",
            },
        },
    )


def test_parse_gateway_response_extracts_responses_output_array_when_output_text_absent():
    parsed = parse_gateway_response(
        {
            "id": "resp-1",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "hello "},
                        {"type": "text", "text": "world"},
                    ],
                }
            ],
            "gateway_usage": {
                "gateway_request_id": "gw-1",
                "provider": "glm",
                "cache_hit": False,
                "billing_units": 2,
                "cost_usd": "0.0002",
            },
        }
    )

    assert parsed.output_text == "hello world"
    assert parsed.gateway_usage.gateway_request_id == "gw-1"


@pytest.mark.parametrize(
    "body, message",
    [
        ({"id": "resp-1", "output_text": "done"}, "gateway_usage missing"),
        ({"id": "resp-1", "output_text": "done", "gateway_usage": {}}, "gateway_request_id"),
        (
            {
                "id": "resp-1",
                "output_text": "done",
                "gateway_usage": {
                    "gateway_request_id": "",
                    "provider": "glm",
                    "cache_hit": False,
                    "billing_units": 1,
                    "cost_usd": "0.01",
                },
            },
            "gateway_request_id",
        ),
        (
            {
                "id": "resp-1",
                "output_text": "done",
                "gateway_usage": {
                    "gateway_request_id": "gw-1",
                    "provider": "glm",
                    "cache_hit": False,
                    "billing_units": 1,
                    "cost_usd": None,
                },
            },
            "cost_usd",
        ),
    ],
)
def test_parse_gateway_response_fails_closed_for_malformed_usage(body, message):
    with pytest.raises(GatewayResponseError, match=message):
        parse_gateway_response(body)
```

- [x] **Step 2: Run the tests to verify they fail**

Run:

```bash
pytest tests/unit/gateway/test_models.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'optimus.gateway'`.

- [x] **Step 3: Implement gateway errors**

Create `src/optimus/gateway/errors.py`:

```python
from __future__ import annotations


class GatewayError(Exception):
    """Base class for Optimus Gateway failures."""


class GatewayHttpError(GatewayError):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


class GatewayResponseError(GatewayError):
    """Raised when a gateway response is malformed or missing required usage."""
```

- [x] **Step 4: Implement gateway models, payload builders, and parser**

Create `src/optimus/gateway/models.py`:

```python
from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from optimus.gateway.errors import GatewayResponseError


class GatewayUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    gateway_request_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    provider_request_id: str | None = None
    cache_hit: bool = False
    billing_units: int = Field(ge=0)
    cost_usd: Decimal = Field(ge=Decimal("0"))


class GatewayResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    response_id: str | None = None
    output_text: str
    gateway_usage: GatewayUsage
    raw: dict[str, Any]


def build_responses_payload(
    *,
    model: str,
    input_text: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"model": model, "input": input_text}
    if metadata:
        payload["metadata"] = metadata
    return payload


def build_chat_completions_payload(
    *,
    model: str,
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    return {"model": model, "messages": messages}


def parse_gateway_response(body: dict[str, Any]) -> GatewayResponse:
    usage_body = body.get("gateway_usage")
    if not isinstance(usage_body, dict):
        raise GatewayResponseError("gateway_usage missing")
    try:
        usage = GatewayUsage.model_validate(usage_body)
    except ValidationError as exc:
        raise GatewayResponseError(str(exc)) from exc

    output_text = body.get("output_text")
    if output_text is None:
        output_text = _extract_text_from_output(body.get("output"))
    if not isinstance(output_text, str):
        raise GatewayResponseError("output_text missing")

    response_id = body.get("id")
    if response_id is not None and not isinstance(response_id, str):
        raise GatewayResponseError("id must be a string when present")

    return GatewayResponse(
        response_id=response_id,
        output_text=output_text,
        gateway_usage=usage,
        raw=body,
    )


def _extract_text_from_output(output: object) -> str | None:
    if not isinstance(output, list):
        return None
    chunks: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") in {"output_text", "text"}:
                text = part.get("text")
                if isinstance(text, str):
                    chunks.append(text)
    if not chunks:
        return None
    return "".join(chunks)
```

- [x] **Step 5: Export gateway models**

Create `src/optimus/gateway/__init__.py`:

```python
"""Optimus Gateway client and wire models."""

from optimus.gateway.errors import GatewayError, GatewayHttpError, GatewayResponseError
from optimus.gateway.models import (
    GatewayResponse,
    GatewayUsage,
    build_chat_completions_payload,
    build_responses_payload,
    parse_gateway_response,
)

__all__ = [
    "GatewayError",
    "GatewayHttpError",
    "GatewayResponse",
    "GatewayResponseError",
    "GatewayUsage",
    "build_chat_completions_payload",
    "build_responses_payload",
    "parse_gateway_response",
]
```

- [x] **Step 6: Run gateway model tests**

Run:

```bash
pytest tests/unit/gateway/test_models.py -v
```

Expected: PASS.

- [x] **Step 7: Commit**

```bash
git add src/optimus/gateway tests/unit/gateway/test_models.py
git commit -m "Add gateway wire models and usage parsing."
```

## Task 5: Gateway Client and Stdlib Transport

**Files:**
- Create: `src/optimus/gateway/client.py`
- Modify: `src/optimus/gateway/__init__.py`
- Test: `tests/unit/gateway/test_client.py`

- [x] **Step 1: Write failing client tests**

Create `tests/unit/gateway/test_client.py`:

```python
import io
import json
from decimal import Decimal
from urllib.error import HTTPError, URLError

import pytest

from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import GatewayClient, GatewayRequest, UrllibGatewayTransport, _decode_gateway_json
from optimus.gateway.errors import GatewayHttpError, GatewayResponseError


class FakeTransport:
    def __init__(self, response: dict[str, object] | None = None, error: Exception | None = None) -> None:
        self.response = response or {
            "id": "resp-1",
            "output_text": "ok",
            "gateway_usage": {
                "gateway_request_id": "gw-1",
                "provider": "glm",
                "cache_hit": False,
                "billing_units": 7,
                "cost_usd": "0.0007",
            },
        }
        self.error = error
        self.requests: list[GatewayRequest] = []

    def post_json(self, request: GatewayRequest) -> dict[str, object]:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.response


def settings() -> OptimusGatewaySettings:
    return OptimusGatewaySettings(
        gateway_url="https://gateway.optimus.ai",
        optimus_api_key="opt_live_abc",
    )


def test_create_response_posts_to_responses_endpoint_with_auth_and_json_headers():
    transport = FakeTransport()
    client = GatewayClient(settings=settings(), transport=transport)

    response = client.create_response(model="glm-5.2", input_text="hello", metadata={"run_id": "run-1"})

    assert response.output_text == "ok"
    assert response.gateway_usage.cost_usd == Decimal("0.0007")
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.method == "POST"
    assert request.url == "https://gateway.optimus.ai/v1/responses"
    assert request.headers == {
        "Authorization": "Bearer opt_live_abc",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    assert request.payload == {"model": "glm-5.2", "input": "hello", "metadata": {"run_id": "run-1"}}
    assert "messages" not in request.payload


def test_create_response_validates_trusted_gateway_before_transport_call():
    transport = FakeTransport()
    client = GatewayClient(
        settings=OptimusGatewaySettings(
            gateway_url="https://rogue.attacker.com",
            optimus_api_key="opt_live_abc",
        ),
        transport=transport,
    )

    with pytest.raises(ValueError, match="gateway origin not in trusted set"):
        client.create_response(model="glm-5.2", input_text="hello")

    assert transport.requests == []


def test_transport_http_error_is_typed():
    transport = FakeTransport(error=GatewayHttpError(503, "gateway unavailable"))
    client = GatewayClient(settings=settings(), transport=transport)

    with pytest.raises(GatewayHttpError) as exc_info:
        client.create_response(model="glm-5.2", input_text="hello")

    assert exc_info.value.status_code == 503


def test_malformed_gateway_response_is_typed():
    transport = FakeTransport(response={"id": "resp-1", "output_text": "ok"})
    client = GatewayClient(settings=settings(), transport=transport)

    with pytest.raises(GatewayResponseError, match="gateway_usage missing"):
        client.create_response(model="glm-5.2", input_text="hello")


def test_urllib_transport_serializes_json_without_secret_leak_in_repr():
    request = GatewayRequest(
        method="POST",
        url="https://gateway.optimus.ai/v1/responses",
        headers={"Authorization": "Bearer opt_live_abc", "Content-Type": "application/json"},
        payload={"model": "glm-5.2", "input": "hello"},
        timeout_seconds=10.0,
    )

    assert "opt_live_abc" not in repr(request)
    assert json.loads(request.body_bytes().decode("utf-8")) == {"model": "glm-5.2", "input": "hello"}
    assert isinstance(UrllibGatewayTransport(), UrllibGatewayTransport)


def test_decode_gateway_json_preserves_numeric_cost_as_decimal():
    decoded = _decode_gateway_json(
        '{"id":"resp-1","output_text":"ok","gateway_usage":'
        '{"gateway_request_id":"gw-1","provider":"glm","cache_hit":false,'
        '"billing_units":7,"cost_usd":0.0042}}'
    )

    assert decoded["gateway_usage"]["cost_usd"] == Decimal("0.0042")


class FakeHttpResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def test_urllib_transport_posts_json_and_decodes_decimal_cost(monkeypatch):
    captured: dict[str, object] = {}

    def fake_urlopen(request: object, timeout: float) -> FakeHttpResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeHttpResponse(
            b'{"id":"resp-1","output_text":"ok","gateway_usage":'
            b'{"gateway_request_id":"gw-1","provider":"glm","cache_hit":false,'
            b'"billing_units":7,"cost_usd":0.0042}}'
        )

    monkeypatch.setattr("optimus.gateway.client.urlopen", fake_urlopen)
    request = GatewayRequest(
        method="POST",
        url="https://gateway.optimus.ai/v1/responses",
        headers={"Authorization": "Bearer opt_live_abc", "Content-Type": "application/json"},
        payload={"model": "glm-5.2", "input": "hello"},
        timeout_seconds=3.5,
    )

    decoded = UrllibGatewayTransport().post_json(request)

    assert captured["timeout"] == 3.5
    assert decoded["gateway_usage"]["cost_usd"] == Decimal("0.0042")


def test_urllib_transport_maps_http_error_to_gateway_http_error(monkeypatch):
    def fake_urlopen(request: object, timeout: float) -> FakeHttpResponse:
        raise HTTPError(
            url="https://gateway.optimus.ai/v1/responses",
            code=503,
            msg="Service Unavailable",
            hdrs=None,
            fp=io.BytesIO(b"gateway down"),
        )

    monkeypatch.setattr("optimus.gateway.client.urlopen", fake_urlopen)

    with pytest.raises(GatewayHttpError) as exc_info:
        UrllibGatewayTransport().post_json(
            GatewayRequest(
                method="POST",
                url="https://gateway.optimus.ai/v1/responses",
                headers={"Content-Type": "application/json"},
                payload={"model": "glm-5.2", "input": "hello"},
            )
        )

    assert exc_info.value.status_code == 503
    assert str(exc_info.value) == "gateway down"


def test_urllib_transport_maps_url_error_to_gateway_http_error(monkeypatch):
    def fake_urlopen(request: object, timeout: float) -> FakeHttpResponse:
        raise URLError("connection refused")

    monkeypatch.setattr("optimus.gateway.client.urlopen", fake_urlopen)

    with pytest.raises(GatewayHttpError) as exc_info:
        UrllibGatewayTransport().post_json(
            GatewayRequest(
                method="POST",
                url="https://gateway.optimus.ai/v1/responses",
                headers={"Content-Type": "application/json"},
                payload={"model": "glm-5.2", "input": "hello"},
            )
        )

    assert exc_info.value.status_code == 0
    assert "connection refused" in str(exc_info.value)


@pytest.mark.parametrize(
    "body, message",
    [
        (b"not-json", "gateway returned invalid JSON"),
        (b'["not", "object"]', "gateway returned non-object JSON"),
    ],
)
def test_urllib_transport_rejects_malformed_json_response(monkeypatch, body, message):
    def fake_urlopen(request: object, timeout: float) -> FakeHttpResponse:
        return FakeHttpResponse(body)

    monkeypatch.setattr("optimus.gateway.client.urlopen", fake_urlopen)

    with pytest.raises(GatewayHttpError, match=message):
        UrllibGatewayTransport().post_json(
            GatewayRequest(
                method="POST",
                url="https://gateway.optimus.ai/v1/responses",
                headers={"Content-Type": "application/json"},
                payload={"model": "glm-5.2", "input": "hello"},
            )
        )
```

- [x] **Step 2: Run the tests to verify they fail**

Run:

```bash
pytest tests/unit/gateway/test_client.py -v
```

Expected: FAIL with missing `optimus.gateway.client`.

- [x] **Step 3: Implement gateway client**

Create `src/optimus/gateway/client.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.errors import GatewayHttpError
from optimus.gateway.models import (
    GatewayResponse,
    build_responses_payload,
    parse_gateway_response,
)


@dataclass(frozen=True)
class GatewayRequest:
    method: str
    url: str
    headers: dict[str, str]
    payload: dict[str, Any]
    timeout_seconds: float = 30.0

    def __repr__(self) -> str:
        safe_headers = dict(self.headers)
        if "Authorization" in safe_headers:
            safe_headers["Authorization"] = "Bearer **********"
        return (
            "GatewayRequest("
            f"method={self.method!r}, url={self.url!r}, headers={safe_headers!r}, "
            f"payload={self.payload!r}, timeout_seconds={self.timeout_seconds!r})"
        )

    def body_bytes(self) -> bytes:
        return json.dumps(self.payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


class GatewayTransport(Protocol):
    def post_json(self, request: GatewayRequest) -> dict[str, Any]:
        """Send JSON to the gateway and return a decoded JSON object."""


class UrllibGatewayTransport:
    def post_json(self, request: GatewayRequest) -> dict[str, Any]:
        urllib_request = Request(
            request.url,
            data=request.body_bytes(),
            headers=request.headers,
            method=request.method,
        )
        try:
            with urlopen(urllib_request, timeout=request.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise GatewayHttpError(exc.code, detail or exc.reason) from exc
        except URLError as exc:
            raise GatewayHttpError(0, str(exc.reason)) from exc

        return _decode_gateway_json(body)


class GatewayClient:
    def __init__(
        self,
        *,
        settings: OptimusGatewaySettings,
        transport: GatewayTransport | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._settings = settings
        self._transport = transport or UrllibGatewayTransport()
        self._timeout_seconds = timeout_seconds

    def create_response(
        self,
        *,
        model: str,
        input_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> GatewayResponse:
        self._settings.validate_trusted_gateway()
        body = self._transport.post_json(
            GatewayRequest(
                method="POST",
                url=self._url("/v1/responses"),
                headers=self._json_headers(),
                payload=build_responses_payload(model=model, input_text=input_text, metadata=metadata),
                timeout_seconds=self._timeout_seconds,
            )
        )
        return parse_gateway_response(body)

    def _url(self, path: str) -> str:
        return f"{self._settings.gateway_url.rstrip('/')}{path}"

    def _json_headers(self) -> dict[str, str]:
        headers = self._settings.auth_headers()
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"
        return headers


def _decode_gateway_json(body: str) -> dict[str, Any]:
    try:
        decoded = json.loads(body, parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise GatewayHttpError(0, "gateway returned invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise GatewayHttpError(0, "gateway returned non-object JSON")
    return decoded
```

- [x] **Step 4: Export gateway client**

Update `src/optimus/gateway/__init__.py`:

```python
from optimus.gateway.client import GatewayClient, GatewayRequest, GatewayTransport, UrllibGatewayTransport
```

Add to `__all__`:

```python
"GatewayClient",
"GatewayRequest",
"GatewayTransport",
"UrllibGatewayTransport",
```

- [x] **Step 5: Run client tests**

Run:

```bash
pytest tests/unit/gateway/test_client.py -v
```

Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add src/optimus/gateway tests/unit/gateway/test_client.py
git commit -m "Add Optimus Gateway client."
```

## Task 6: ACP Gateway Dispatch Method

**Files:**
- Modify: `src/optimus/acp/dispatcher.py`
- Modify: `tests/unit/acp/test_dispatcher.py`

**Design decision:** `optimus.gateway.responses` is intentionally callable from `PLAN` / `CHAT_ONLY` context because model generation is required to produce advisory plans and chat answers. This is not a local file, shell, patch, or repository mutation. Gateway-side budget, wallet, provider-key injection, usage recording, and policy revalidation remain mandatory for the billed external call.

- [ ] **Step 1: Add failing ACP gateway dispatch tests**

Append to `tests/unit/acp/test_dispatcher.py`:

```python
from decimal import Decimal

from optimus.gateway.models import GatewayResponse, GatewayUsage


class FakeGatewayClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create_response(self, *, model: str, input_text: str, metadata: dict[str, object] | None = None) -> GatewayResponse:
        self.calls.append({"model": model, "input_text": input_text, "metadata": metadata})
        return GatewayResponse(
            response_id="resp-1",
            output_text="planned",
            gateway_usage=GatewayUsage(
                gateway_request_id="gw-1",
                provider="glm",
                cache_hit=False,
                billing_units=12,
                cost_usd=Decimal("0.0012"),
            ),
            raw={"id": "resp-1"},
        )


def test_dispatcher_routes_gateway_responses_method_to_gateway_client():
    gateway_client = FakeGatewayClient()
    dispatcher = JsonRpcDispatcher(gateway_client=gateway_client)

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "gw-call-1",
            "method": "optimus.gateway.responses",
            "params": {
                "model": "glm-5.2",
                "input": "Write a plan.",
                "metadata": {"run_id": "run-1"},
            },
        }
    )

    assert response["id"] == "gw-call-1"
    assert response["result"] == {
        "response_id": "resp-1",
        "output_text": "planned",
        "gateway_usage": {
            "gateway_request_id": "gw-1",
            "provider": "glm",
            "provider_request_id": None,
            "cache_hit": False,
            "billing_units": 12,
            "cost_usd": "0.0012",
        },
    }
    assert gateway_client.calls == [
        {"model": "glm-5.2", "input_text": "Write a plan.", "metadata": {"run_id": "run-1"}}
    ]


def test_gateway_responses_are_allowed_in_plan_chat_mode_by_design():
    gateway_client = FakeGatewayClient()
    dispatcher = JsonRpcDispatcher(
        gateway_client=gateway_client,
        runtime_context=RuntimeContext(
            execution_mode=ExecutionMode.PLAN,
            state=AgentState.CHAT_ONLY,
        ),
    )

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "gw-plan-chat-1",
            "method": "optimus.gateway.responses",
            "params": {"model": "glm-5.2", "input": "Draft an advisory answer."},
        }
    )

    assert "error" not in response
    assert response["result"]["output_text"] == "planned"
    assert gateway_client.calls == [
        {"model": "glm-5.2", "input_text": "Draft an advisory answer.", "metadata": None}
    ]


def test_dispatcher_rejects_gateway_responses_messages_shape():
    dispatcher = JsonRpcDispatcher(gateway_client=FakeGatewayClient())

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "gw-call-2",
            "method": "optimus.gateway.responses",
            "params": {"model": "glm-5.2", "messages": [{"role": "user", "content": "wrong"}]},
        }
    )

    assert response["error"]["code"] == -32600
    assert response["error"]["message"] == "invalid request"
```

- [ ] **Step 2: Run dispatcher tests to verify they fail**

Run:

```bash
pytest tests/unit/acp/test_dispatcher.py -v
```

Expected: FAIL with unexpected `gateway_client` argument or method not found.

- [ ] **Step 3: Add optional gateway client and dispatch method**

Update `src/optimus/acp/dispatcher.py` imports:

```python
from decimal import Decimal

from optimus.gateway.client import GatewayClient
from optimus.gateway.errors import GatewayError
from optimus.gateway.models import GatewayResponse
```

Update `JsonRpcDispatcher.__init__`:

```python
    def __init__(
        self,
        request_ids: RequestIdTracker | None = None,
        runtime_context: RuntimeContext | None = None,
        gateway_client: GatewayClient | None = None,
    ) -> None:
        self._request_ids = request_ids or RequestIdTracker()
        self._runtime_context = runtime_context or RuntimeContext(
            execution_mode=ExecutionMode.PLAN,
            state=AgentState.CHAT_ONLY,
        )
        self._gateway_client = gateway_client
```

Add this branch inside `dispatch()` before the mutation method:

```python
            if method == "optimus.gateway.responses":
                if self._gateway_client is None:
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=METHOD_NOT_FOUND, message="gateway client not configured"),
                    )
                params = request.get("params")
                if (
                    not isinstance(params, dict)
                    or not isinstance(params.get("model"), str)
                    or not isinstance(params.get("input"), str)
                    or "messages" in params
                ):
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
                    )
                metadata = params.get("metadata")
                if metadata is not None and not isinstance(metadata, dict):
                    return error_response(
                        request_id=request_id,
                        error=JsonRpcError(code=INVALID_REQUEST, message="invalid request"),
                    )
                gateway_response = self._gateway_client.create_response(
                    model=params["model"],
                    input_text=params["input"],
                    metadata=metadata,
                )
                return success_response(
                    request_id=request_id,
                    result=_gateway_response_payload(gateway_response),
                )
```

Add a gateway exception mapping next to the existing mutation exception handling:

```python
        except GatewayError as exc:
            return error_response(
                request_id=request_id,
                error=JsonRpcError(code=INTERNAL_ERROR, message=str(exc)),
            )
```

Add helper function at the bottom of `src/optimus/acp/dispatcher.py`:

```python
def _gateway_response_payload(response: GatewayResponse) -> dict[str, Any]:
    return {
        "response_id": response.response_id,
        "output_text": response.output_text,
        "gateway_usage": {
            "gateway_request_id": response.gateway_usage.gateway_request_id,
            "provider": response.gateway_usage.provider,
            "provider_request_id": response.gateway_usage.provider_request_id,
            "cache_hit": response.gateway_usage.cache_hit,
            "billing_units": response.gateway_usage.billing_units,
            "cost_usd": str(response.gateway_usage.cost_usd),
        },
    }
```

If `INTERNAL_ERROR` is not already imported from `optimus.acp.errors`, add it to the existing import list.

- [ ] **Step 4: Run dispatcher and ACP integration tests**

Run:

```bash
pytest tests/unit/acp/test_dispatcher.py tests/integration/acp/test_server_stream.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/optimus/acp/dispatcher.py tests/unit/acp/test_dispatcher.py
git commit -m "Route ACP gateway response calls."
```

## Task 7: Mocked One-Key Gateway Run Integration

**Files:**
- Create: `tests/integration/gateway/test_one_key_mocked_run.py`
- Verify: `src/optimus/config/*`, `src/optimus/gateway/*`, `src/optimus/acp/dispatcher.py`

- [ ] **Step 1: Write the mocked full-run integration test**

Create `tests/integration/gateway/test_one_key_mocked_run.py`:

```python
from decimal import Decimal

from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import GatewayClient, GatewayRequest


class CapturingGatewayTransport:
    def __init__(self) -> None:
        self.requests: list[GatewayRequest] = []

    def post_json(self, request: GatewayRequest) -> dict[str, object]:
        self.requests.append(request)
        return {
            "id": "resp-plan-1",
            "output_text": "Plan-mode advisory response.",
            "gateway_usage": {
                "gateway_request_id": "gw-plan-1",
                "provider": "glm",
                "provider_request_id": "provider-plan-1",
                "cache_hit": False,
                "billing_units": 31,
                "cost_usd": "0.0031",
            },
        }


def test_mocked_full_gateway_run_uses_only_optimus_credentials(monkeypatch):
    monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "https://gateway.optimus.ai")
    monkeypatch.setenv("OPTIMUS_API_KEY", "opt_live_test")
    for key in [
        "ANTHROPIC_API_KEY",
        "GLM_API_KEY",
        "LANGSMITH_API_KEY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "TAVILY_API_KEY",
        "ZHIPUAI_API_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)

    settings = OptimusGatewaySettings.from_env()
    assert settings.validate_no_local_provider_keys() == ()

    transport = CapturingGatewayTransport()
    dispatcher = JsonRpcDispatcher(
        gateway_client=GatewayClient(settings=settings, transport=transport)
    )

    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": "plan-call-1",
            "method": "optimus.gateway.responses",
            "params": {
                "model": "glm-5.2",
                "input": "Create an advisory plan.",
                "metadata": {"run_id": "run-1", "session_id": "session-1"},
            },
        }
    )

    assert "error" not in response
    assert response["result"]["output_text"] == "Plan-mode advisory response."
    assert response["result"]["gateway_usage"]["cost_usd"] == str(Decimal("0.0031"))
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.url == "https://gateway.optimus.ai/v1/responses"
    assert request.headers["Authorization"] == "Bearer opt_live_test"
    assert request.payload["input"] == "Create an advisory plan."
    assert "messages" not in request.payload
```

- [ ] **Step 2: Run the integration test to verify it passes**

Run:

```bash
pytest tests/integration/gateway/test_one_key_mocked_run.py -v
```

Expected: PASS with no provider key configured in the test environment.

- [ ] **Step 3: Run the full gateway/config/ACP focused suite**

Run:

```bash
pytest tests/unit/config tests/unit/gateway tests/unit/acp/test_dispatcher.py tests/integration/gateway tests/integration/acp -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/gateway/test_one_key_mocked_run.py
git commit -m "Verify mocked one-key gateway run."
```

## Task 8: README Gateway Foundation Note

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add the README gateway foundation note**

Append under the existing Phase 1 Mode Boundary Foundation section:

```markdown
### Phase 1 Gateway Configuration Foundation

The gateway configuration foundation keeps the local runtime on the one-key
model: `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`. `OptimusGatewaySettings`
validates trusted gateway origins, masks the Optimus API key in safe dumps and
representations, rejects local provider keys in strict mode, and supports
development-only extra trusted origins. The gateway client posts model requests
to `/v1/responses` using the Responses API `input` shape and parses the
GatewayUsage envelope before returning generated text.
```

- [ ] **Step 2: Run focused smoke tests**

Run:

```bash
pytest tests/unit/config tests/unit/gateway tests/integration/gateway -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Document gateway configuration foundation."
```

## Task 9: Coverage and Final Verification

**Files:**
- Verify: all files from Tasks 1-8

- [ ] **Step 1: Run focused test suite with scoped coverage**

Run:

```bash
pytest tests/unit/config tests/unit/gateway tests/unit/acp/test_dispatcher.py tests/integration/gateway tests/integration/acp --cov=optimus.config --cov=optimus.gateway --cov=optimus.acp.dispatcher --cov-branch --cov-report=term-missing --cov-fail-under=80
```

Expected: PASS with focused coverage at or above 80% for the Plan 3 slice. Safety-critical `optimus.config.gateway`, `optimus.gateway.models`, and `optimus.gateway.client` should have high branch coverage for origin validation, provider-key handling, malformed responses, Decimal cost parsing, and auth header construction.

- [ ] **Step 2: Run the full package coverage gate**

Run:

```bash
pytest --cov=optimus --cov-branch --cov-report=term-missing -v
```

Expected: PASS with aggregate Python production-code coverage at or above the `pyproject.toml` `fail_under = 80` gate.

- [ ] **Step 3: Run the full test suite without coverage instrumentation**

Run:

```bash
pytest -v
```

Expected: PASS.

- [ ] **Step 4: Check provider key absence in the implementation test environment**

Run:

```bash
python -c "import os; keys=['ANTHROPIC_API_KEY','GLM_API_KEY','LANGSMITH_API_KEY','OPENAI_API_KEY','OPENROUTER_API_KEY','TAVILY_API_KEY','ZHIPUAI_API_KEY']; found=[k for k in keys if os.environ.get(k)]; print('FOUND=' + ','.join(found)); raise SystemExit(1 if found else 0)"
```

Expected: PASS with output `FOUND=`. If this fails on a developer workstation, unset the provider key variables before running the release-gate subset. Do not add those keys to local config.

- [ ] **Step 5: Check working tree**

Run:

```bash
git status --short
```

Expected: only intentional Plan 3 implementation files are modified or added. Pre-existing unrelated IDE, extracted-doc, generated cache, or Plan 2 artifacts must not be staged.

- [ ] **Step 6: Commit final verification adjustments if needed**

If Task 9 required code or docs adjustments after verification, commit only those intentional files:

```bash
git add pyproject.toml uv.lock README.md src/optimus/config src/optimus/gateway src/optimus/acp/dispatcher.py tests/unit tests/integration
git commit -m "Complete gateway-only configuration foundation."
```

Skip this commit if Tasks 1-8 already committed all implementation changes and Task 9 made no edits.

## Self-Review

- Spec coverage: The plan implements the one-key local runtime from HLD section 5A, HLD section 11, LLD section 0A, and Test Strategy section 7. It includes trusted gateway origin validation, production-mode rules, dev/test extra origins, already-verified signed tenant profile origins, masked API key handling, env-bootstrap provider-key rejection/ignore behavior, `/v1/responses` payload shape, `/v1/chat/completions` shape separation, typed gateway errors, direct `UrllibGatewayTransport` coverage, Decimal-safe gateway usage parsing, Responses `output` array fallback parsing, and a mocked full run using only Optimus credentials.
- Placeholder scan: The plan has no `TBD`, `TODO`, "implement later", or unexpanded "write tests" steps. Later roadmap work is named only in Out of Scope with the owning roadmap plan.
- Type consistency: `OptimusGatewaySettings`, `ProviderKeyPolicy`, `ProviderKeyViolation`, `GatewayUsage`, `GatewayResponse`, `GatewayRequest`, `GatewayClient`, `GatewayHttpError`, and `GatewayResponseError` are defined before use. ACP serialization converts `Decimal` cost values to strings so JSON-RPC responses stay deterministic.
- Dependency consistency: Pydantic is introduced explicitly because Test Strategy section 7 and schema-validation tests name Pydantic models and `SecretStr` masking behavior. Task 1 now runs both `uv lock` and `uv sync --all-extras`, so the dependency is installed before tests expect it. HTTP transport uses stdlib `urllib.request` to avoid adding a second runtime dependency in this slice.
- Coverage consistency: Focused coverage is scoped to the Plan 3 packages and dispatcher seam; the full `--cov=optimus` 80% gate runs against the full test suite so omitted modules do not create a false narrow-suite failure.
- Boundary consistency: Gateway model calls are explicitly allowed in Plan/Chat because advisory generation requires them; local mutation remains guarded by Plan 2, and wallet/provider side effects stay gateway-side.
- TDD compliance: Every production change starts with a failing test, then minimal implementation, then focused verification.
- Deferral clarity: Evidence acquisition, usage persistence, retry policy, egress instrumentation, tenant-profile signature verification, staging gateway E2E, and final release gates are not hidden inside this plan; they remain assigned to later roadmap plans.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-02-gateway-only-configuration-gateway-client.md`. Two execution options:

**1. Subagent-Driven (recommended when available)** - dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - execute tasks in this session task-by-task with checkpoints. Use `superpowers:executing-plans` if available; otherwise follow this plan directly with the same red/green/refactor discipline.

Before implementation, create or switch to a dedicated branch from latest `main`, for example `agent/codex/gateway-only-configuration`, or create a separate worktree if this Plan 2 branch must remain untouched. Do not run `git commit`, push, or create/delete branches unless the user explicitly approves those actions.
