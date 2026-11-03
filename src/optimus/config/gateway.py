from __future__ import annotations

import os
from typing import Mapping
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from optimus_security import gateway_identity

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_DEFAULT_GATEWAY_URL = "http://127.0.0.1:8765"
# Set in-process on the launch's already-authorized agent view; registered reject-inherited, so it is never taken from outside.
GATEWAY_IDENTITY_ENVIRON = "OPTIMUS_GATEWAY_IDENTITY"

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


class ProviderKeyViolation(ValueError):
    def __init__(self, keys: list[str]) -> None:
        self.keys = keys
        super().__init__(f"local provider keys are not allowed: {', '.join(keys)}")


class OptimusGatewaySettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    gateway_url: str = _DEFAULT_GATEWAY_URL
    optimus_api_key: SecretStr = Field(min_length=1)
    # #465 (ADR-036): the identity this launch expects of a local Gateway, sent on every request so a Gateway that took
    # over the port refuses it before dispatch. A keyed digest, not a credential. None: this launch has no expectation.
    gateway_identity: str | None = None

    @field_validator("gateway_url", mode="before")
    @classmethod
    def validate_gateway_url(cls, value: object) -> str:
        return _validate_loopback_gateway_url(value)

    @model_validator(mode="after")
    def validate_gateway_at_construction(self) -> OptimusGatewaySettings:
        self.validate_trusted_gateway()
        return self

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> OptimusGatewaySettings:
        env = os.environ if environ is None else environ
        settings = cls(
            gateway_url=env.get("OPTIMUS_GATEWAY_URL", _DEFAULT_GATEWAY_URL),
            optimus_api_key=SecretStr(_required_env(env, "OPTIMUS_API_KEY")),
            gateway_identity=env.get(GATEWAY_IDENTITY_ENVIRON) or None,
        )
        settings.validate_no_local_provider_keys(env)
        return settings

    def auth_headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.optimus_api_key.get_secret_value()}"}
        if self.gateway_identity is not None:
            headers[gateway_identity.HEADER] = self.gateway_identity
        return headers

    def validate_trusted_gateway(self) -> None:
        _validate_loopback_gateway_url(self.gateway_url)

    def validate_no_local_provider_keys(self, environ: Mapping[str, str] | None = None) -> tuple[str, ...]:
        env = os.environ if environ is None else environ
        found = sorted(name for name in LOCAL_PROVIDER_KEY_NAMES if env.get(name))
        if not found:
            return ()
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


def _validate_loopback_gateway_url(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("gateway_url must be a string")
    url = value.strip().rstrip("/")
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"gateway_url is malformed: {value}") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or hostname is None
        or hostname.lower() not in _LOOPBACK_HOSTS
    ):
        raise ValueError("gateway_url must use an http(s) loopback host without userinfo")
    del port
    return url
