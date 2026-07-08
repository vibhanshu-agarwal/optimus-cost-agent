from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

import pytest

from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES
from tests.integration.optimus_gateway.gateway_env import _ensure_src_on_pythonpath, project_root

_REQUIRED_AGENT_ENV_KEYS = ("OPTIMUS_GATEWAY_URL", "OPTIMUS_API_KEY", "OPTIMUS_REDIS_URL")
_OPTIONAL_AGENT_ENV_KEYS = ("OPTIMUS_AGENT_MODEL", "OPTIMUS_LIVE_MAX_COST_USD")
_SYSTEM_ENV_KEYS = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP", "TMP")
_GATEWAY_ONLY_ENV_PREFIXES = ("OPTIMUS_LOCAL_GATEWAY_",)


def build_acp_subprocess_env(
    *,
    operator_environ: Mapping[str, str] | None = None,
    root: Path | None = None,
) -> dict[str, str]:
    """Build a minimal child-process env for ``python -m optimus.acp`` without provider keys."""
    source = dict(operator_environ or os.environ)
    env: dict[str, str] = {}

    for key in _REQUIRED_AGENT_ENV_KEYS:
        value = source.get(key, "").strip()
        if not value:
            pytest.fail(_missing_env_message(key))
        env[key] = value

    production_mode = source.get("OPTIMUS_PRODUCTION_MODE", "").strip()
    env["OPTIMUS_PRODUCTION_MODE"] = production_mode or "false"

    for key in _OPTIONAL_AGENT_ENV_KEYS:
        value = source.get(key, "").strip()
        if value:
            env[key] = value

    for key in _SYSTEM_ENV_KEYS:
        value = source.get(key, "").strip()
        if value:
            env[key] = value

    _ensure_src_on_pythonpath(env, root or project_root())
    _assert_no_provider_or_gateway_secrets(env)
    return env


def _missing_env_message(key: str) -> str:
    if key == "OPTIMUS_REDIS_URL":
        return (
            "Set OPTIMUS_REDIS_URL=redis://127.0.0.1:6379/0 and start Redis before running e2e tests "
            "(docker run --rm -d -p 6379:6379 redis:8)."
        )
    if key == "OPTIMUS_GATEWAY_URL":
        return (
            "Set OPTIMUS_GATEWAY_URL and start the local gateway before running e2e tests "
            "(bash tools/run_local_gateway.sh)."
        )
    return f"Set {key} in the environment before running e2e tests."


def _assert_no_provider_or_gateway_secrets(env: Mapping[str, str]) -> None:
    forbidden = {key for key in env if key in LOCAL_PROVIDER_KEY_NAMES}
    forbidden.update(key for key in env if key.startswith(_GATEWAY_ONLY_ENV_PREFIXES))
    if forbidden:
        pytest.fail(
            "ACP subprocess env must not include provider or gateway-only credentials: "
            + ", ".join(sorted(forbidden))
        )
