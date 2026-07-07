from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from typing import Mapping

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_SUPPORTED_PROVIDERS = frozenset({"openai", "openrouter", "anthropic"})
_DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}


@dataclass(frozen=True)
class GatewayServiceConfig:
    bind_host: str
    bind_port: int
    shared_secret: str
    provider: str
    provider_api_key: str
    base_url: str | None = None

    def __post_init__(self) -> None:
        if self.bind_host.lower() not in _LOOPBACK_HOSTS:
            raise ValueError(f"bind host must be loopback, got {self.bind_host!r}")
        if not self.shared_secret.strip():
            raise ValueError("shared_secret is required")
        if self.provider not in _SUPPORTED_PROVIDERS:
            raise ValueError(f"unsupported provider: {self.provider}")
        if not self.provider_api_key.strip():
            raise ValueError("provider_api_key is required")
        if self.provider != "anthropic" and not (self.base_url or "").strip():
            raise ValueError(f"base_url is required for provider {self.provider!r}")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> GatewayServiceConfig:
        env = os.environ if environ is None else environ
        provider = env.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER", "openrouter").strip().lower()
        if provider not in _SUPPORTED_PROVIDERS:
            raise ValueError(f"unsupported provider: {provider}")

        base_url = env.get("OPTIMUS_LOCAL_GATEWAY_BASE_URL", "").strip()
        if provider == "anthropic":
            provider_api_key = _required_env(env, "ANTHROPIC_API_KEY")
            resolved_base_url = None
        else:
            provider_api_key = _required_env(env, "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY")
            resolved_base_url = base_url or _DEFAULT_BASE_URLS[provider]

        return cls(
            bind_host=env.get("OPTIMUS_LOCAL_GATEWAY_BIND_HOST", "127.0.0.1"),
            bind_port=int(env.get("OPTIMUS_LOCAL_GATEWAY_PORT", "8765")),
            shared_secret=_required_env(env, "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET"),
            provider=provider,
            provider_api_key=provider_api_key,
            base_url=resolved_base_url,
        )


def authorize_bearer(*, authorization_header: str | None, shared_secret: str) -> bool:
    if authorization_header is None:
        return False
    prefix = "Bearer "
    if not authorization_header.startswith(prefix):
        return False
    token = authorization_header[len(prefix) :].strip()
    return secrets.compare_digest(token, shared_secret)


def _required_env(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value
