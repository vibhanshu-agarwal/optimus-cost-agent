from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from typing import Mapping

from optimus_security.launch_manifest import resolve_effective_base_url

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_SUPPORTED_PROVIDERS = frozenset({"openai", "openrouter", "anthropic"})


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
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        bind_host: str,
        bind_port: int,
    ) -> GatewayServiceConfig:
        """Build config from credential/provider env plus EXPLICIT bind values.

        Plan 9.96, Task 5 Step 4: bind_host/bind_port are never read from
        OPTIMUS_LOCAL_GATEWAY_BIND_HOST/PORT — the standalone entrypoint no
        longer trusts those inherited names at all. The authorized parent
        (or the operator via an explicit --bind-host/--port CLI argument)
        supplies bind_host/bind_port directly; this closes the standalone
        bind seam. Provider/credential fields still come from `environ`
        because that mapping is the authorized parent's explicit child
        environment construction, not ambient inherited state.
        """
        env = os.environ if environ is None else environ
        provider = env.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER", "openrouter").strip().lower()
        if provider not in _SUPPORTED_PROVIDERS:
            raise ValueError(f"unsupported provider: {provider}")

        base_url = env.get("OPTIMUS_LOCAL_GATEWAY_BASE_URL", "").strip()
        if provider == "anthropic":
            provider_api_key = _required_env(env, "ANTHROPIC_API_KEY")
        else:
            provider_api_key = _required_env(env, "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY")
        # Single shared resolver (optimus_security.launch_manifest) — the
        # parent side (ProviderSecrets / resolve_provider_credentials) calls
        # this exact function too, so an omitted OPTIMUS_LOCAL_GATEWAY_BASE_URL
        # resolves to the SAME concrete value on both sides.
        resolved_base_url = resolve_effective_base_url(provider=provider, base_url=base_url or None)

        return cls(
            bind_host=bind_host,
            bind_port=bind_port,
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
