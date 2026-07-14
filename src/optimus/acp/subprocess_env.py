from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES

_REQUIRED_AGENT_ENV_KEYS = ("OPTIMUS_GATEWAY_URL", "OPTIMUS_API_KEY", "OPTIMUS_REDIS_URL")
_OPTIONAL_AGENT_ENV_KEYS = ("OPTIMUS_AGENT_MODEL", "OPTIMUS_LIVE_MAX_COST_USD")
_SYSTEM_ENV_KEYS = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP", "TMP")
_GATEWAY_ONLY_ENV_PREFIXES = ("OPTIMUS_LOCAL_GATEWAY_",)


@dataclass(frozen=True)
class SubprocessEnvConfigurationError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


def build_acp_subprocess_env(
    *,
    operator_environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """
    Builds and configures a subprocess environment dictionary necessary for ACP operations.

    This function assembles an environment dictionary by extracting necessary and
    optional environment variables. It ensures that the required environment keys
    are present and assigns them to the resulting environment dictionary. Optional
    keys and system keys are conditionally added if they have a non-empty value.
    The resulting environment contains only the agent contract and safe system settings.

    :param operator_environ: A mapping of environment variables that may override
        or complement the current environment. If not provided, the existing
        environment variables from `os.environ` will be used.
    :type operator_environ: Mapping[str, str] | None
    :return: A dictionary of environment variables configured for ACP operations.
    :rtype: dict[str, str]
    :raises SubprocessEnvConfigurationError: If any of the required environment
        keys are missing or if specific validation conditions fail.
    """
    source = dict(operator_environ or os.environ)
    env: dict[str, str] = {}

    for key in _REQUIRED_AGENT_ENV_KEYS:
        value = source.get(key, "").strip()
        if not value:
            raise SubprocessEnvConfigurationError(_missing_env_message(key))
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

    _assert_no_provider_or_gateway_secrets(env)
    return env


def _missing_env_message(key: str) -> str:
    if key == "OPTIMUS_REDIS_URL":
        return (
            "Set OPTIMUS_REDIS_URL=redis://127.0.0.1:6379/0 and start Redis before running the live agent "
            "(docker run --rm -d -p 6379:6379 redis:8)."
        )
    if key == "OPTIMUS_GATEWAY_URL":
        return (
            "Set OPTIMUS_GATEWAY_URL and start the local gateway before running the live agent "
            "(bash tools/run_local_gateway.sh)."
        )
    return f"Set {key} in the environment before running the live agent."


def _assert_no_provider_or_gateway_secrets(env: Mapping[str, str]) -> None:
    forbidden = {key for key in env if key in LOCAL_PROVIDER_KEY_NAMES}
    forbidden.update(key for key in env if key.startswith(_GATEWAY_ONLY_ENV_PREFIXES))
    if forbidden:
        raise SubprocessEnvConfigurationError(
            "ACP subprocess env must not include provider or gateway-only credentials: "
            + ", ".join(sorted(forbidden))
        )
