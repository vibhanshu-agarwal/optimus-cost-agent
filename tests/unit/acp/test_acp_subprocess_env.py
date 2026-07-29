from __future__ import annotations

import os

from optimus.acp.subprocess_env import build_acp_subprocess_env


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
    assert env["OPTIMUS_API_KEY"] == "shared-secret"
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
