from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from typing import Mapping

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

AGENT_MODEL_TO_ANTHROPIC_MODEL: dict[str, str] = {
    "claude-haiku": "claude-haiku-4-5-20251001",
}


@dataclass(frozen=True)
class GatewayServiceConfig:
    bind_host: str
    bind_port: int
    shared_secret: str
    anthropic_api_key: str

    def __post_init__(self) -> None:
        if self.bind_host.lower() not in _LOOPBACK_HOSTS:
            raise ValueError(f"bind host must be loopback, got {self.bind_host!r}")
        if not self.shared_secret.strip():
            raise ValueError("shared_secret is required")
        if not self.anthropic_api_key.strip():
            raise ValueError("anthropic_api_key is required")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> GatewayServiceConfig:
        env = os.environ if environ is None else environ
        return cls(
            bind_host=env.get("OPTIMUS_LOCAL_GATEWAY_BIND_HOST", "127.0.0.1"),
            bind_port=int(env.get("OPTIMUS_LOCAL_GATEWAY_PORT", "8765")),
            shared_secret=_required_env(env, "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET"),
            anthropic_api_key=_required_env(env, "ANTHROPIC_API_KEY"),
        )


def map_agent_model_id(model: str) -> str:
    try:
        return AGENT_MODEL_TO_ANTHROPIC_MODEL[model]
    except KeyError as exc:
        raise ValueError(f"unsupported gateway model: {model}") from exc


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
