from __future__ import annotations

import os

import pytest
from _pytest.outcomes import Failed

from tests.e2e.acp.acp_subprocess_env import build_acp_subprocess_env


def _set_required_agent_env(monkeypatch) -> None:
    monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "http://127.0.0.1:8765")
    monkeypatch.setenv("OPTIMUS_API_KEY", "shared-secret")
    monkeypatch.setenv("OPTIMUS_REDIS_URL", "redis://127.0.0.1:6379/0")


def test_build_acp_subprocess_env_includes_required_keys_and_pythonpath(tmp_path, monkeypatch):
    _set_required_agent_env(monkeypatch)
    monkeypatch.delenv("OPTIMUS_PRODUCTION_MODE", raising=False)

    env = build_acp_subprocess_env(operator_environ=os.environ, root=tmp_path)

    assert env["OPTIMUS_GATEWAY_URL"] == "http://127.0.0.1:8765"
    assert env["OPTIMUS_API_KEY"] == "shared-secret"
    assert env["OPTIMUS_REDIS_URL"] == "redis://127.0.0.1:6379/0"
    assert env["OPTIMUS_PRODUCTION_MODE"] == "false"
    assert env["PYTHONPATH"].startswith(str(tmp_path / "src"))
    assert "OPENAI_API_KEY" not in env


def test_build_acp_subprocess_env_fails_when_gateway_url_missing(monkeypatch):
    monkeypatch.delenv("OPTIMUS_GATEWAY_URL", raising=False)
    monkeypatch.setenv("OPTIMUS_API_KEY", "shared-secret")
    monkeypatch.setenv("OPTIMUS_REDIS_URL", "redis://127.0.0.1:6379/0")

    with pytest.raises(Failed, match="OPTIMUS_GATEWAY_URL"):
        build_acp_subprocess_env(operator_environ=os.environ)


def test_build_acp_subprocess_env_excludes_provider_keys_from_child_env(monkeypatch, tmp_path):
    _set_required_agent_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    env = build_acp_subprocess_env(operator_environ=os.environ, root=tmp_path)

    assert "OPENAI_API_KEY" not in env
    assert "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY" not in env


def test_build_acp_subprocess_env_passes_through_systemroot_and_still_excludes_secrets(
    monkeypatch, tmp_path
):
    _set_required_agent_env(monkeypatch)
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "gateway-secret")

    env = build_acp_subprocess_env(operator_environ=os.environ, root=tmp_path)

    assert env["SYSTEMROOT"] == r"C:\Windows"
    assert "OPENAI_API_KEY" not in env
    assert "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY" not in env
