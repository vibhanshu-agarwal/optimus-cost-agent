from __future__ import annotations

import os
from enum import StrEnum
from typing import Mapping
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

BUILT_IN_TRUSTED_GATEWAY_ORIGINS = frozenset({"https://gateway.optimus.ai"})

# Non-production trust-boundary exception for the local Optimus Gateway stub
# (see docs/superpowers/plans/2026-07-07-local-optimus-gateway-service.md).
# Traffic stays on-loopback; TLS adds no protection for that shape. Production
# mode continues to require https for every origin.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

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
    # Development/test-only allowlist extensions (e.g. internal staging gateways).
    # Loaded from OPTIMUS_EXTRA_GATEWAY_ORIGINS when production_mode is false;
    # must be empty in production and is ignored by from_env() in production mode.
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
    def validate_production_constraints(self) -> OptimusGatewaySettings:
        if self.production_mode and self.extra_trusted_origins:
            raise ValueError("extra_trusted_origins must not be set in production_mode")
        if self.production_mode and self.provider_key_policy is ProviderKeyPolicy.IGNORE:
            raise ValueError("provider_key_policy=ignore is valid only outside production_mode")
        return self

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

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.optimus_api_key.get_secret_value()}"}

    def validate_trusted_gateway(self) -> None:
        allow_insecure_http = not self.production_mode
        origin = _origin(self.gateway_url, allow_insecure_http=allow_insecure_http)
        trusted = set(BUILT_IN_TRUSTED_GATEWAY_ORIGINS)
        trusted.update(self.signed_tenant_profile_origins)
        if not self.production_mode:
            trusted.update(self.extra_trusted_origins)
            if _is_loopback_host(urlparse(self.gateway_url).hostname):
                trusted.add(origin)
        if origin not in trusted:
            raise ValueError(f"gateway origin not in trusted set: {origin}")

    def validate_no_local_provider_keys(self, environ: Mapping[str, str] | None = None) -> tuple[str, ...]:
        env = os.environ if environ is None else environ
        found = sorted(name for name in LOCAL_PROVIDER_KEY_NAMES if env.get(name))
        if not found:
            return ()
        if self.provider_key_policy is ProviderKeyPolicy.IGNORE and not self.production_mode:
            return tuple(found)
        raise ProviderKeyViolation(found)

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


def _is_loopback_host(hostname: str | None) -> bool:
    return (hostname or "").lower() in _LOOPBACK_HOSTS


def _normalize_origin(value: str, *, allow_insecure_http: bool = False) -> str:
    parsed = urlparse(value.strip().rstrip("/"))
    scheme_ok = parsed.scheme == "https" or (allow_insecure_http and parsed.scheme == "http")
    if not scheme_ok or not parsed.netloc:
        raise ValueError(f"gateway origin must be an https origin: {value}")
    return f"{parsed.scheme}://{parsed.netloc.lower()}"


def _origin(url: str, *, allow_insecure_http: bool = False) -> str:
    return _normalize_origin(url, allow_insecure_http=allow_insecure_http)
