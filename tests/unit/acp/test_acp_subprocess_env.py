from __future__ import annotations

import os

import pytest

from optimus.acp.subprocess_env import SubprocessEnvConfigurationError, build_acp_subprocess_env


def _set_required_agent_env(monkeypatch) -> None:
    monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "http://127.0.0.1:8765")
    monkeypatch.setenv("OPTIMUS_API_KEY", "shared-secret")
    monkeypatch.setenv("OPTIMUS_REDIS_URL", "redis://127.0.0.1:6379/0")


def test_build_acp_subprocess_env_includes_required_keys_without_pythonpath(monkeypatch):
    _set_required_agent_env(monkeypatch)
    monkeypatch.delenv("OPTIMUS_PRODUCTION_MODE", raising=False)

    env = build_acp_subprocess_env(operator_environ=os.environ)

    assert env["OPTIMUS_GATEWAY_URL"] == "http://127.0.0.1:8765"
    assert env["OPTIMUS_API_KEY"] == "shared-secret"
    assert env["OPTIMUS_REDIS_URL"] == "redis://127.0.0.1:6379/0"
    assert env["OPTIMUS_PRODUCTION_MODE"] == "false"
    assert "PYTHONPATH" not in env
    assert "OPENAI_API_KEY" not in env


def test_build_acp_subprocess_env_fails_when_gateway_url_missing(monkeypatch):
    monkeypatch.delenv("OPTIMUS_GATEWAY_URL", raising=False)
    monkeypatch.setenv("OPTIMUS_API_KEY", "shared-secret")
    monkeypatch.setenv("OPTIMUS_REDIS_URL", "redis://127.0.0.1:6379/0")

    with pytest.raises(SubprocessEnvConfigurationError, match="OPTIMUS_GATEWAY_URL"):
        build_acp_subprocess_env(operator_environ=os.environ)


def test_build_acp_subprocess_env_excludes_provider_keys_from_child_env(monkeypatch):
    _set_required_agent_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    env = build_acp_subprocess_env(operator_environ=os.environ)

    assert "OPENAI_API_KEY" not in env
    assert "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY" not in env


def test_build_acp_subprocess_env_passes_through_systemroot_and_still_excludes_secrets(
    monkeypatch,
):
    _set_required_agent_env(monkeypatch)
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "gateway-secret")

    env = build_acp_subprocess_env(operator_environ=os.environ)

    assert env["SYSTEMROOT"] == r"C:\Windows"
    assert "OPENAI_API_KEY" not in env
    assert "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY" not in env


# --- Task 5 Step 3: registry-projection tests ---
# subprocess_env's agent-child allowlist must be EXACTLY EQUAL to launch_policy's
# single source of truth (AGENT_CHILD propagation) in both directions, not
# merely a subset. A prior version only asserted the subset direction, which
# missed registry-authorized names (OPTIMUS_MAX_PLANNING_TURNS,
# OPTIMUS_EXTRA_GATEWAY_ORIGINS) that were never added to the module's
# hand-maintained optional-keys tuple and so never reached the agent child.


def test_specially_handled_and_derived_optional_keys_equal_registry_exactly():
    from optimus.acp import subprocess_env as subprocess_env_module
    from optimus.acp.launch_policy import LAUNCH_VARIABLE_POLICIES, PropagationTarget

    registry_agent_child_names = {
        name
        for name, policy in LAUNCH_VARIABLE_POLICIES.items()
        if PropagationTarget.AGENT_CHILD in policy.propagation
    }
    module_names = {
        *subprocess_env_module._REQUIRED_AGENT_ENV_KEYS,
        subprocess_env_module._PRODUCTION_MODE_ENV_KEY,
        *subprocess_env_module._optional_agent_env_keys(),
    }
    assert module_names == registry_agent_child_names


def test_optional_agent_env_keys_is_derived_not_hand_maintained():
    """_optional_agent_env_keys() must equal registry AGENT_CHILD names minus
    the specially-handled ones — proving it is computed, not a separately
    maintained list that could itself drift."""
    from optimus.acp import subprocess_env as subprocess_env_module

    registry_names = subprocess_env_module._agent_child_registry_names()
    specially_handled = {
        *subprocess_env_module._REQUIRED_AGENT_ENV_KEYS,
        subprocess_env_module._PRODUCTION_MODE_ENV_KEY,
    }
    assert subprocess_env_module._optional_agent_env_keys() == registry_names - specially_handled


def test_module_level_guard_raises_on_unauthorized_name(monkeypatch):
    """If subprocess_env's specially-handled names ever drift to include a
    name the registry has not authorized for AGENT_CHILD, the module-level
    guard must catch it (proven by calling the guard function directly with a
    deliberately unauthorized tuple, rather than mutating the real module
    state which other tests depend on)."""
    from optimus.acp import subprocess_env as subprocess_env_module

    monkeypatch.setattr(subprocess_env_module, "_REQUIRED_AGENT_ENV_KEYS", ("OPTIMUS_UNAUTHORIZED_NAME",))
    with pytest.raises(RuntimeError, match="OPTIMUS_UNAUTHORIZED_NAME"):
        subprocess_env_module._assert_agent_env_keys_are_registry_authorized()


def test_max_planning_turns_tightening_reaches_agent_child(monkeypatch):
    """A monotonic tightening of OPTIMUS_MAX_PLANNING_TURNS must actually
    arrive in the built agent child env — Global Constraint 12 allows
    tightening without approval, so silently dropping it here is fail-open."""
    _set_required_agent_env(monkeypatch)
    monkeypatch.setenv("OPTIMUS_MAX_PLANNING_TURNS", "2")

    env = build_acp_subprocess_env(operator_environ=os.environ)

    assert env["OPTIMUS_MAX_PLANNING_TURNS"] == "2"


def test_extra_gateway_origins_reaches_agent_child(monkeypatch):
    _set_required_agent_env(monkeypatch)
    monkeypatch.setenv("OPTIMUS_EXTRA_GATEWAY_ORIGINS", "https://example.com")

    env = build_acp_subprocess_env(operator_environ=os.environ)

    assert env["OPTIMUS_EXTRA_GATEWAY_ORIGINS"] == "https://example.com"


def test_built_agent_child_env_exactly_matches_registry_projection_for_full_input(monkeypatch):
    """With every registry AGENT_CHILD name present in the source environ,
    the built child env's key set must equal the registry projection exactly
    (aside from the always-added system keys) — the Step 3/Step 7 "exact
    child-key-set equals registry projection" assertion."""
    from optimus.acp import subprocess_env as subprocess_env_module

    _set_required_agent_env(monkeypatch)
    monkeypatch.setenv("OPTIMUS_AGENT_MODEL", "glm-5.2")
    monkeypatch.setenv("OPTIMUS_LIVE_MAX_COST_USD", "0.10")
    monkeypatch.setenv("OPTIMUS_MAX_PLANNING_TURNS", "2")
    monkeypatch.setenv("OPTIMUS_EXTRA_GATEWAY_ORIGINS", "https://example.com")
    monkeypatch.setenv("OPTIMUS_PRODUCTION_MODE", "true")

    env = build_acp_subprocess_env(operator_environ=os.environ)

    registry_names = subprocess_env_module._agent_child_registry_names()
    non_system_keys = {key for key in env if key not in subprocess_env_module._SYSTEM_ENV_KEYS}
    assert non_system_keys == registry_names
