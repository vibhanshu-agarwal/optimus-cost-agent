from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

import pytest
from dotenv import dotenv_values

GATEWAY_ENV_FILENAME = ".env.gateway"


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def gateway_env_file_path(root: Path | None = None) -> Path:
    return (root or project_root()) / GATEWAY_ENV_FILENAME


def load_gateway_env_file(root: Path | None = None) -> dict[str, str]:
    """Load gateway secrets from disk without mutating ``os.environ``."""
    path = gateway_env_file_path(root)
    if not path.is_file():
        return {}
    values = dotenv_values(path)
    return {key: value for key, value in values.items() if key and value is not None}


def resolve_gateway_provider_api_key(provider: str, gateway_env: Mapping[str, str]) -> str:
    if provider == "anthropic":
        api_key = gateway_env.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            pytest.fail(
                "ANTHROPIC_API_KEY is required in .env.gateway when "
                "OPTIMUS_LOCAL_GATEWAY_PROVIDER=anthropic."
            )
        return api_key

    api_key = gateway_env.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "").strip()
    if not api_key:
        pytest.fail(
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY is required in .env.gateway for "
            "openai/openrouter live smoke tests."
        )
    return api_key


def merge_gateway_subprocess_env(
    *,
    base_environ: Mapping[str, str] | None = None,
    root: Path | None = None,
    port: int,
    shared_secret: str,
) -> dict[str, str]:
    gateway_env = dict(base_environ or os.environ)
    gateway_env.update(load_gateway_env_file(root))

    provider = gateway_env.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER", "openrouter").strip().lower()
    if provider not in {"openai", "openrouter", "anthropic"}:
        pytest.fail(f"unsupported OPTIMUS_LOCAL_GATEWAY_PROVIDER for live smoke: {provider}")

    gateway_env["OPTIMUS_LOCAL_GATEWAY_PROVIDER"] = provider
    gateway_env["OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET"] = shared_secret
    gateway_env["OPTIMUS_LOCAL_GATEWAY_BIND_HOST"] = "127.0.0.1"
    gateway_env["OPTIMUS_LOCAL_GATEWAY_PORT"] = str(port)
    gateway_env.pop("OPTIMUS_GATEWAY_URL", None)
    gateway_env.pop("OPTIMUS_API_KEY", None)

    if provider == "anthropic":
        gateway_env["ANTHROPIC_API_KEY"] = resolve_gateway_provider_api_key(provider, gateway_env)
        gateway_env.pop("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", None)
    else:
        gateway_env["OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY"] = resolve_gateway_provider_api_key(
            provider, gateway_env
        )
        gateway_env.pop("ANTHROPIC_API_KEY", None)

    _ensure_src_on_pythonpath(gateway_env, root or project_root())

    return gateway_env


def _ensure_src_on_pythonpath(gateway_env: dict[str, str], root: Path) -> None:
    src_path = str(root / "src")
    existing = gateway_env.get("PYTHONPATH", "").strip()
    if not existing:
        gateway_env["PYTHONPATH"] = src_path
        return
    prefix_entries = existing.split(os.pathsep)
    if prefix_entries[0] == src_path:
        return
    gateway_env["PYTHONPATH"] = f"{src_path}{os.pathsep}{existing}"
