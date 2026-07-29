from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from optimus.acp.launch_policy import LAUNCH_VARIABLE_POLICIES, PropagationTarget
from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES

# Plan 11.6 Task 1: the agent child's allowed names are a projection of the
# SINGLE registry (launch_policy.LAUNCH_VARIABLE_POLICIES). This module forwards
# only present AGENT_CHILD values plus safe system names. It does not require
# shell variables, inject loopback defaults, or resolve keychain credentials —
# an empty Optimus projection must stay empty so authorization digests match a
# direct zero-env optimus-agent launch.
_SYSTEM_ENV_KEYS = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP", "TMP")
_GATEWAY_ONLY_ENV_PREFIXES = ("OPTIMUS_LOCAL_GATEWAY_",)


def _agent_child_registry_names() -> frozenset[str]:
    """The set of names the registry authorizes for AGENT_CHILD propagation."""
    return frozenset(
        name
        for name, policy in LAUNCH_VARIABLE_POLICIES.items()
        if PropagationTarget.AGENT_CHILD in policy.propagation
    )


@dataclass(frozen=True)
class SubprocessEnvConfigurationError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


def build_acp_subprocess_env(
    *,
    operator_environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Project present registry-authorized agent names plus safe system names.

    Missing Optimus variables are not an error: the child resolves loopback
    defaults and keychain credentials through its existing launch path.

    :param operator_environ: Optional environ override; defaults to ``os.environ``.
    :return: Child environment containing only present AGENT_CHILD names and
        safe system keys.
    :raises SubprocessEnvConfigurationError: If provider or gateway-only secrets
        would otherwise be projected into the child.
    """
    source = dict(operator_environ or os.environ)
    env = {
        name: value.strip()
        for name in sorted(_agent_child_registry_names())
        if (value := source.get(name, "")).strip()
    }
    for name in _SYSTEM_ENV_KEYS:
        if value := source.get(name, "").strip():
            env[name] = value
    _assert_no_provider_or_gateway_secrets(env)
    return env


def _assert_no_provider_or_gateway_secrets(env: Mapping[str, str]) -> None:
    forbidden = {key for key in env if key in LOCAL_PROVIDER_KEY_NAMES}
    forbidden.update(key for key in env if key.startswith(_GATEWAY_ONLY_ENV_PREFIXES))
    if forbidden:
        raise SubprocessEnvConfigurationError(
            "ACP subprocess env must not include provider or gateway-only credentials: "
            + ", ".join(sorted(forbidden))
        )
