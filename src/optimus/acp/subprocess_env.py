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
_SYSTEM_ENV_KEY_SET = frozenset(_SYSTEM_ENV_KEYS)
# PATHEXT is the one allowlisted name whose explicitly empty value is meaningful:
# for MCP command resolution it means "bare name only" (no default executable
# extensions), so the system view preserves its presence as "". Every other
# name drops an empty value, and a genuinely absent PATHEXT stays absent.
_PRESENCE_SIGNIFICANT_SYSTEM_KEYS = frozenset({"PATHEXT"})
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


def _windows_semantics_default() -> bool:
    return os.name == "nt"


def _fold_system_key_aliases(environ: Mapping[str, str], *, windows_semantics: bool) -> dict[str, str]:
    """Return a fresh copy of ``environ`` with system-key casing normalised.

    Windows semantics: environment names are case-insensitive, and a snapshot
    copied from a *supplied* mapping keeps whatever casing the caller used, so
    every spelling of one of the eight allowlisted system names folds onto the
    allowlist spelling. Spellings that carry differing values (ignoring
    surrounding whitespace) are an ambiguous configuration and are rejected,
    independent of the mapping's insertion order. Only the eight system names
    fold; registry-authorized names (``OPTIMUS_*``) keep exact matching, so
    folding never broadens credential-name matching.

    POSIX semantics: names are case-sensitive and nothing folds, so a supplied
    ``SystemRoot`` is simply not an allowlisted name.
    """
    if not windows_semantics:
        return dict(environ)
    folded: dict[str, str] = {}
    conflicts: set[str] = set()
    for key, value in environ.items():
        canonical = key.upper()
        if canonical not in _SYSTEM_ENV_KEY_SET:
            folded[key] = value
            continue
        if canonical in folded and folded[canonical].strip() != value.strip():
            conflicts.add(canonical)
        folded[canonical] = value
    if conflicts:
        raise SubprocessEnvConfigurationError(
            "conflicting spellings of Windows system environment names: " + ", ".join(sorted(conflicts))
        )
    return folded


def system_environ_view(environ: Mapping[str, str], *, windows_semantics: bool | None = None) -> dict[str, str]:
    """The system-only projection of a captured environment.

    One allowlist -- ``_SYSTEM_ENV_KEYS`` -- shared with the agent-child
    projection, so consumers needing PATH/PATHEXT/SystemRoot read a captured
    view rather than ambient state. It carries **no** registry-authorized name
    and therefore never the Gateway credential: this is deliberately not the
    agent-child environment. Values are stripped; an empty value is dropped,
    except that an explicitly present ``PATHEXT`` survives as ``""`` because
    that is a meaningful command-resolution input (bare name only), while an
    absent ``PATHEXT`` stays absent. The result is a fresh ``dict`` sharing
    nothing with ``environ``.

    :param environ: The captured mapping (for example ``LaunchEnvironmentSnapshot.values``).
    :param windows_semantics: Casing policy; ``None`` follows the running
        platform (``os.name == "nt"``). See ``_fold_system_key_aliases``.
    :raises SubprocessEnvConfigurationError: Under Windows semantics, when two
        spellings of one system name carry differing values.
    """
    windows = _windows_semantics_default() if windows_semantics is None else windows_semantics
    source = _fold_system_key_aliases(environ, windows_semantics=windows)
    view: dict[str, str] = {}
    for name in _SYSTEM_ENV_KEYS:
        if name not in source:
            continue
        value = source[name].strip()
        if value or name in _PRESENCE_SIGNIFICANT_SYSTEM_KEYS:
            view[name] = value
    return view


def build_acp_subprocess_env(
    *,
    operator_environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Project present registry-authorized agent names plus safe system names.

    Missing Optimus variables are not an error: the child resolves loopback
    defaults and keychain credentials through its existing launch path.

    :param operator_environ: Optional environ override. ``None`` -- and only
        ``None`` -- means capture ``os.environ``; an explicit empty mapping is a
        request to project nothing.
    :return: Child environment containing only present AGENT_CHILD names and
        safe system keys.
    :raises SubprocessEnvConfigurationError: If provider or gateway-only secrets
        would otherwise be projected into the child, or if Windows system-name
        spellings conflict.
    """
    # `{}` is a request to project nothing. The former `operator_environ or
    # os.environ` treated it as falsy and silently selected the broadest
    # possible source, so only None means ambient.
    supplied = os.environ if operator_environ is None else operator_environ
    source = _fold_system_key_aliases(supplied, windows_semantics=_windows_semantics_default())
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
