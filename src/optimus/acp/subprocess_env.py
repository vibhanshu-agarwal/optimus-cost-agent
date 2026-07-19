from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from optimus.acp.launch_policy import LAUNCH_VARIABLE_POLICIES, PropagationTarget
from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES

# Plan 9.96, Task 5 Step 3: the agent child's allowed names are a projection
# of the SINGLE registry (launch_policy.LAUNCH_VARIABLE_POLICIES), not a
# separately hand-maintained list. _REQUIRED_AGENT_ENV_KEYS are the names this
# module treats specially (fail-closed if missing, or defaulted, for
# OPTIMUS_PRODUCTION_MODE). _OPTIONAL_AGENT_ENV_KEYS is DERIVED from the
# registry's AGENT_CHILD set minus those specially-handled names — not a
# separately maintained tuple — so a name added to (or removed from) the
# registry's AGENT_CHILD propagation set automatically changes what this
# module passes through, with no second place to remember to update.
#
# A prior version of this module hand-maintained _OPTIONAL_AGENT_ENV_KEYS as
# a tuple and only asserted it was a SUBSET of the registry's AGENT_CHILD
# names. That one-directional check caught names added here without registry
# authorization, but not the reverse: a registry-authorized AGENT_CHILD name
# that was never added to this module's tuple silently never reached the
# agent child. That gap was real and was caught in review — proven concretely
# for OPTIMUS_MAX_PLANNING_TURNS (a monotonic *tightening*, which Global
# Constraint 12 allows without approval, was silently dropped, which is a
# fail-open direction) and OPTIMUS_EXTRA_GATEWAY_ORIGINS. Deriving the
# optional set from the registry instead of a hand-maintained list makes this
# class of drift structurally impossible rather than merely detectable.
_REQUIRED_AGENT_ENV_KEYS = ("OPTIMUS_GATEWAY_URL", "OPTIMUS_API_KEY", "OPTIMUS_REDIS_URL")
_PRODUCTION_MODE_ENV_KEY = "OPTIMUS_PRODUCTION_MODE"
_SYSTEM_ENV_KEYS = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP", "TMP")
_GATEWAY_ONLY_ENV_PREFIXES = ("OPTIMUS_LOCAL_GATEWAY_",)


def _agent_child_registry_names() -> frozenset[str]:
    """The set of names the registry authorizes for AGENT_CHILD propagation."""
    return frozenset(
        name
        for name, policy in LAUNCH_VARIABLE_POLICIES.items()
        if PropagationTarget.AGENT_CHILD in policy.propagation
    )


def _optional_agent_env_keys() -> frozenset[str]:
    """Every registry AGENT_CHILD name except the specially-handled ones.

    Computed fresh from the registry (not cached at import time) so that
    _REQUIRED_AGENT_ENV_KEYS/_PRODUCTION_MODE_ENV_KEY mutations in tests (see
    test_module_level_guard_raises_on_unauthorized_name) are reflected
    immediately rather than through stale module state.
    """
    specially_handled = frozenset({*_REQUIRED_AGENT_ENV_KEYS, _PRODUCTION_MODE_ENV_KEY})
    return _agent_child_registry_names() - specially_handled


def _assert_agent_env_keys_are_registry_authorized() -> None:
    """Fail fast (at import time) if this module's specially-handled names
    drift from the single registry — the exact class of duplicated-allowlist
    bug Task 5 Step 3 exists to close. _optional_agent_env_keys() is derived
    directly from the registry so it cannot itself drift; only the
    specially-handled required/production-mode names need this check."""
    registry_names = _agent_child_registry_names()
    unauthorized = {
        name for name in (*_REQUIRED_AGENT_ENV_KEYS, _PRODUCTION_MODE_ENV_KEY) if name not in registry_names
    }
    if unauthorized:
        raise RuntimeError(
            "subprocess_env.py allowlist contains names not authorized for "
            f"AGENT_CHILD propagation in launch_policy.py: {sorted(unauthorized)}"
        )


_assert_agent_env_keys_are_registry_authorized()


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

    production_mode = source.get(_PRODUCTION_MODE_ENV_KEY, "").strip()
    env[_PRODUCTION_MODE_ENV_KEY] = production_mode or "false"

    for key in sorted(_optional_agent_env_keys()):
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
