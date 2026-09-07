from __future__ import annotations

import os

import pytest

from optimus.acp import subprocess_env as subprocess_env_module
from optimus.acp.subprocess_env import SubprocessEnvConfigurationError, build_acp_subprocess_env


def _set_present_agent_env(monkeypatch) -> None:
    monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "http://127.0.0.1:8765")
    monkeypatch.setenv("OPTIMUS_API_KEY", "shared-secret")
    monkeypatch.setenv("OPTIMUS_REDIS_URL", "redis://127.0.0.1:6379/0")


def test_empty_optimus_environment_stays_empty_for_keychain_default_child():
    env = build_acp_subprocess_env(operator_environ={"PATH": "/usr/bin"})
    assert env == {"PATH": "/usr/bin"}
    assert not any(name.startswith("OPTIMUS_") for name in env)


def test_build_acp_subprocess_env_includes_present_keys_without_pythonpath(monkeypatch):
    _set_present_agent_env(monkeypatch)
    monkeypatch.delenv("OPTIMUS_PRODUCTION_MODE", raising=False)

    env = build_acp_subprocess_env(operator_environ=os.environ)

    assert env["OPTIMUS_GATEWAY_URL"] == "http://127.0.0.1:8765"
    assert env["OPTIMUS_API_KEY"] == "shared-secret"  # pragma: allowlist secret
    assert env["OPTIMUS_REDIS_URL"] == "redis://127.0.0.1:6379/0"
    assert "OPTIMUS_PRODUCTION_MODE" not in env
    assert "PYTHONPATH" not in env
    assert "OPENAI_API_KEY" not in env


def test_build_acp_subprocess_env_excludes_provider_keys_from_child_env(monkeypatch):
    _set_present_agent_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    env = build_acp_subprocess_env(operator_environ=os.environ)

    assert "OPENAI_API_KEY" not in env
    assert "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY" not in env


def test_build_acp_subprocess_env_passes_through_systemroot_and_still_excludes_secrets(
    monkeypatch,
):
    _set_present_agent_env(monkeypatch)
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "gateway-secret")

    env = build_acp_subprocess_env(operator_environ=os.environ)

    assert env["SYSTEMROOT"] == r"C:\Windows"
    assert "OPENAI_API_KEY" not in env
    assert "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY" not in env


# --- Plan 11.6 Task 1: registry-only present projection ---
# subprocess_env projects only present registry AGENT_CHILD names plus safe
# system keys. It must not require shell variables, inject defaults, or keep a
# separate required/optional allowlist that can drift from launch_policy.


def test_agent_child_projection_derives_full_registry_set():
    from optimus.acp import subprocess_env as subprocess_env_module
    from optimus.acp.launch_policy import LAUNCH_VARIABLE_POLICIES, PropagationTarget

    registry_agent_child_names = {
        name
        for name, policy in LAUNCH_VARIABLE_POLICIES.items()
        if PropagationTarget.AGENT_CHILD in policy.propagation
    }
    assert subprocess_env_module._agent_child_registry_names() == registry_agent_child_names
    assert not hasattr(subprocess_env_module, "_REQUIRED_AGENT_ENV_KEYS")
    assert not hasattr(subprocess_env_module, "_optional_agent_env_keys")
    assert not hasattr(subprocess_env_module, "_assert_agent_env_keys_are_registry_authorized")
    assert not hasattr(subprocess_env_module, "_missing_env_message")


def test_forwards_only_present_registry_values(monkeypatch):
    monkeypatch.delenv("OPTIMUS_GATEWAY_URL", raising=False)
    monkeypatch.delenv("OPTIMUS_API_KEY", raising=False)
    monkeypatch.delenv("OPTIMUS_REDIS_URL", raising=False)
    monkeypatch.setenv("OPTIMUS_AGENT_MODEL", "glm-5.2")
    monkeypatch.setenv("OPTIMUS_UNRELATED_AMBIENT", "must-not-pass")

    env = build_acp_subprocess_env(operator_environ=os.environ)

    assert env.get("OPTIMUS_AGENT_MODEL") == "glm-5.2"
    assert "OPTIMUS_GATEWAY_URL" not in env
    assert "OPTIMUS_API_KEY" not in env
    assert "OPTIMUS_REDIS_URL" not in env
    assert "OPTIMUS_UNRELATED_AMBIENT" not in env


def test_max_planning_turns_tightening_reaches_agent_child(monkeypatch):
    """A monotonic tightening of OPTIMUS_MAX_PLANNING_TURNS must actually
    arrive in the built agent child env — Global Constraint 12 allows
    tightening without approval, so silently dropping it here is fail-open."""
    _set_present_agent_env(monkeypatch)
    monkeypatch.setenv("OPTIMUS_MAX_PLANNING_TURNS", "2")

    env = build_acp_subprocess_env(operator_environ=os.environ)

    assert env["OPTIMUS_MAX_PLANNING_TURNS"] == "2"


def test_extra_gateway_origins_reaches_agent_child(monkeypatch):
    _set_present_agent_env(monkeypatch)
    monkeypatch.setenv("OPTIMUS_EXTRA_GATEWAY_ORIGINS", "https://example.com")

    env = build_acp_subprocess_env(operator_environ=os.environ)

    assert "OPTIMUS_EXTRA_GATEWAY_ORIGINS" not in env


def test_built_agent_child_env_exactly_matches_registry_projection_for_full_input(monkeypatch):
    """With every registry AGENT_CHILD name present in the source environ,
    the built child env's key set must equal the registry projection exactly
    (aside from the always-added system keys)."""
    from optimus.acp import subprocess_env as subprocess_env_module

    _set_present_agent_env(monkeypatch)
    monkeypatch.setenv("OPTIMUS_AGENT_MODEL", "glm-5.2")
    monkeypatch.setenv("OPTIMUS_LIVE_MAX_COST_USD", "0.10")
    monkeypatch.setenv("OPTIMUS_MAX_PLANNING_TURNS", "2")

    env = build_acp_subprocess_env(operator_environ=os.environ)

    registry_names = subprocess_env_module._agent_child_registry_names()
    non_system_keys = {key for key in env if key not in subprocess_env_module._SYSTEM_ENV_KEYS}
    assert non_system_keys == registry_names


# --- seam 3: explicit-empty projection, the system-only view, platform casing ---
# Behavioural RED against main: `operator_environ or os.environ` makes `{}` select
# the broadest possible source, and no system-only projection exists at all.


def test_explicit_empty_environ_projects_nothing_rather_than_ambient(monkeypatch):
    """`operator_environ={}` is the most restrictive possible request. Only `None`
    may mean "use the ambient environment"."""
    monkeypatch.setenv("OPTIMUS_API_KEY", "ambient-gateway-credential")
    monkeypatch.setenv("PATH", "/ambient/bin")

    assert build_acp_subprocess_env(operator_environ={}) == {}


def test_only_none_requests_the_ambient_environment(monkeypatch):
    """Control for the test above: None is the one intentional ambient request."""
    monkeypatch.setenv("OPTIMUS_API_KEY", "ambient-gateway-credential")
    monkeypatch.setenv("PATH", "/ambient/bin")

    env = build_acp_subprocess_env(operator_environ=None)

    assert env["PATH"] == "/ambient/bin"
    assert env["OPTIMUS_API_KEY"] == "ambient-gateway-credential"  # pragma: allowlist secret


def test_system_environ_view_carries_only_allowlisted_system_names(monkeypatch):
    """The system-only view shares the allowlist with the agent-child projection but
    carries no registry-authorized name, so never the Gateway credential."""
    monkeypatch.setenv("OPTIMUS_API_KEY", "ambient-must-not-appear")

    view = subprocess_env_module.system_environ_view(
        {
            "OPTIMUS_API_KEY": "gateway-credential-must-not-cross",  # pragma: allowlist secret
            "OPENAI_API_KEY": "provider-credential-must-not-cross",  # pragma: allowlist secret
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "gateway-only-must-not-cross",  # pragma: allowlist secret
            "PATH": "  /captured/bin  ",
            "PATHEXT": ".EXE",
            "SYSTEMROOT": r"C:\Windows",
            "TEMP": "   ",
            "UNRELATED": "dropped",
        }
    )

    assert view == {"PATH": "/captured/bin", "PATHEXT": ".EXE", "SYSTEMROOT": r"C:\Windows"}
    assert set(view) <= set(subprocess_env_module._SYSTEM_ENV_KEYS)
    assert "must-not-cross" not in repr(view)


def test_system_environ_view_is_a_fresh_copy_in_both_directions():
    source = {"PATH": "/captured/bin", "PATHEXT": ".EXE"}
    view = subprocess_env_module.system_environ_view(source)

    source["PATH"] = "/mutated/after/capture"
    source["PATHEXT"] = ".CMD"
    assert view == {"PATH": "/captured/bin", "PATHEXT": ".EXE"}

    view["PATH"] = "/caller/mutation"
    assert source["PATH"] == "/mutated/after/capture"
    assert subprocess_env_module.system_environ_view(source)["PATH"] == "/mutated/after/capture"


def test_system_environ_view_accepts_the_read_only_launch_snapshot():
    from optimus.acp.launch_policy import LaunchEnvironmentSnapshot

    snapshot = LaunchEnvironmentSnapshot.capture({"PATH": "/captured/bin", "OPTIMUS_API_KEY": "x"})

    view = subprocess_env_module.system_environ_view(snapshot.values)

    assert view == {"PATH": "/captured/bin"}
    assert type(view) is dict


# Casing policy (recorded in the seam 3 work record):
#   * Windows semantics: every spelling of one of the eight allowlisted system
#     names folds onto the allowlist spelling; spellings that carry differing
#     values are rejected as an ambiguous configuration, independent of the
#     mapping's insertion order.
#   * POSIX semantics: names are case-sensitive; nothing folds, so ``SystemRoot``
#     is simply not an allowlisted name.
#   * Registry-authorized names (OPTIMUS_*) match exactly on every platform;
#     folding never broadens credential-name matching.
#   The default policy follows ``os.name``; the keyword exists so that both
#   policies are covered on both platforms.


def test_windows_semantics_fold_supplied_system_key_casing_onto_the_allowlist_spelling():
    view = subprocess_env_module.system_environ_view(
        {"SystemRoot": r"C:\Windows", "path": "/captured/bin", "PathExt": ".EXE"},
        windows_semantics=True,
    )

    assert view == {"SYSTEMROOT": r"C:\Windows", "PATH": "/captured/bin", "PATHEXT": ".EXE"}


def test_posix_semantics_leave_case_sensitive_names_alone():
    view = subprocess_env_module.system_environ_view(
        {
            "SystemRoot": "/not-a-system-key",
            "path": "/lowercase-is-a-different-variable",
            "PATH": "/captured/bin",
        },
        windows_semantics=False,
    )

    assert view == {"PATH": "/captured/bin"}


@pytest.mark.parametrize("ordering", ["exact-first", "alias-first"])
def test_windows_semantics_reject_conflicting_aliases_regardless_of_order(ordering):
    pairs = [("SYSTEMROOT", r"C:\Windows"), ("SystemRoot", r"D:\Other")]
    if ordering == "alias-first":
        pairs.reverse()

    with pytest.raises(SubprocessEnvConfigurationError, match="SYSTEMROOT"):
        subprocess_env_module.system_environ_view(dict(pairs), windows_semantics=True)


def test_windows_semantics_collapse_agreeing_aliases_ignoring_surrounding_whitespace():
    view = subprocess_env_module.system_environ_view(
        {"SYSTEMROOT": r"C:\Windows", "SystemRoot": r" C:\Windows "},
        windows_semantics=True,
    )

    assert view == {"SYSTEMROOT": r"C:\Windows"}


def test_posix_semantics_never_see_a_collision():
    view = subprocess_env_module.system_environ_view(
        {"SYSTEMROOT": "/exact", "SystemRoot": "/alias"},
        windows_semantics=False,
    )

    assert view == {"SYSTEMROOT": "/exact"}


def test_folding_never_broadens_registry_credential_name_matching():
    env = build_acp_subprocess_env(
        operator_environ={"optimus_api_key": "wrong-case", "Optimus_Api_Key": "wrong-case"},  # pragma: allowlist secret
    )

    assert env == {}


@pytest.mark.skipif(os.name != "nt", reason="default policy follows os.name: Windows folds")
def test_default_policy_on_windows_folds_supplied_casing_in_the_agent_child_projection():
    env = build_acp_subprocess_env(operator_environ={"SystemRoot": r"C:\Windows"})

    assert env == {"SYSTEMROOT": r"C:\Windows"}


@pytest.mark.skipif(os.name == "nt", reason="default policy follows os.name: POSIX is case-sensitive")
def test_default_policy_on_posix_does_not_fold_supplied_casing_in_the_agent_child_projection():
    env = build_acp_subprocess_env(operator_environ={"SystemRoot": "/not-a-system-key"})

    assert env == {}


# --- seam 3 R1: an explicitly empty PATHEXT is a value, not an absence ---
# Value semantics of the system view: every allowlisted value is stripped and an
# empty result is dropped, EXCEPT PATHEXT: its explicitly empty value means
# "bare name only" for MCP command resolution and therefore survives as "".
# A genuinely absent PATHEXT stays absent (the normalizer keeps its deterministic
# default). Casing folds and conflict rejection apply to the empty value exactly
# as to any other. The agent-child projection is unchanged: it never forwards
# empty values.


def test_system_environ_view_preserves_an_explicitly_empty_pathext():
    view = subprocess_env_module.system_environ_view({"PATH": "/captured/bin", "PATHEXT": ""})

    assert view == {"PATH": "/captured/bin", "PATHEXT": ""}


def test_system_environ_view_keeps_a_genuinely_absent_pathext_absent():
    view = subprocess_env_module.system_environ_view({"PATH": "/captured/bin"})

    assert view == {"PATH": "/captured/bin"}
    assert "PATHEXT" not in view


def test_system_environ_view_treats_whitespace_only_pathext_as_explicitly_empty():
    assert subprocess_env_module.system_environ_view({"PATHEXT": " \t "}) == {"PATHEXT": ""}


def test_system_environ_view_still_drops_other_empty_system_values():
    view = subprocess_env_module.system_environ_view({"PATH": "", "SYSTEMROOT": "  ", "TEMP": "", "PATHEXT": ""})

    assert view == {"PATHEXT": ""}


def test_windows_semantics_fold_an_explicitly_empty_pathext_alias():
    view = subprocess_env_module.system_environ_view({"PathExt": ""}, windows_semantics=True)

    assert view == {"PATHEXT": ""}


def test_windows_semantics_reject_an_empty_versus_non_empty_pathext_alias():
    with pytest.raises(SubprocessEnvConfigurationError, match="PATHEXT"):
        subprocess_env_module.system_environ_view({"PATHEXT": "", "PathExt": ".EXE"}, windows_semantics=True)


def test_windows_semantics_collapse_empty_and_whitespace_pathext_aliases():
    view = subprocess_env_module.system_environ_view({"PATHEXT": "", "pathext": "  "}, windows_semantics=True)

    assert view == {"PATHEXT": ""}


def test_posix_semantics_keep_only_the_exact_empty_pathext():
    view = subprocess_env_module.system_environ_view({"PATHEXT": "", "PathExt": ".EXE"}, windows_semantics=False)

    assert view == {"PATHEXT": ""}


def test_agent_child_projection_still_omits_an_empty_pathext():
    """Unrelated projection behaviour is unchanged by R1."""
    env = build_acp_subprocess_env(operator_environ={"PATHEXT": "", "PATH": "/captured/bin"})

    assert env == {"PATH": "/captured/bin"}
