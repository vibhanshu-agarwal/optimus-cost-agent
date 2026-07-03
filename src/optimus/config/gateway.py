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
