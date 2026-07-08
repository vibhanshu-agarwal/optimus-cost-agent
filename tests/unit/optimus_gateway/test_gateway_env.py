from __future__ import annotations

import os

from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES
from tests.integration.optimus_gateway.gateway_env import (
    load_gateway_env_file,
    merge_gateway_subprocess_env,
)


def test_load_gateway_env_file_does_not_mutate_process_environ(tmp_path, monkeypatch):
    for key in (*LOCAL_PROVIDER_KEY_NAMES, "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    (tmp_path / ".env.gateway").write_text(
        "\n".join(
            [
                "OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter",
                "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY=sk-or-test",
                "OPENAI_API_KEY=sk-should-not-appear-in-process",
            ]
        ),
        encoding="utf-8",
    )

    loaded = load_gateway_env_file(tmp_path)

    assert loaded["OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY"] == "sk-or-test"
    assert os.environ.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY") is None
    assert os.environ.get("OPENAI_API_KEY") is None


def test_merge_gateway_subprocess_env_reads_provider_key_from_file(tmp_path, monkeypatch):
    monkeypatch.delenv("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", raising=False)
    (tmp_path / ".env.gateway").write_text(
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter\n"
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY=sk-or-test\n",
        encoding="utf-8",
    )

    gateway_env = merge_gateway_subprocess_env(
        base_environ={},
        root=tmp_path,
        port=9876,
        shared_secret="live-gateway-smoke-secret",
    )

    assert gateway_env["OPTIMUS_LOCAL_GATEWAY_PROVIDER"] == "openrouter"
    assert gateway_env["OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY"] == "sk-or-test"
    assert gateway_env["OPTIMUS_LOCAL_GATEWAY_PORT"] == "9876"
    assert "OPTIMUS_API_KEY" not in gateway_env
    assert gateway_env["PYTHONPATH"].startswith(str(tmp_path / "src"))


def test_merge_gateway_subprocess_env_preserves_existing_pythonpath(tmp_path, monkeypatch):
    monkeypatch.delenv("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", raising=False)
    (tmp_path / ".env.gateway").write_text(
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER=openai\n"
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY=sk-test\n",
        encoding="utf-8",
    )

    gateway_env = merge_gateway_subprocess_env(
        base_environ={"PYTHONPATH": "/existing/path"},
        root=tmp_path,
        port=9876,
        shared_secret="live-gateway-smoke-secret",
    )

    assert gateway_env["PYTHONPATH"] == f"{tmp_path / 'src'}{os.pathsep}/existing/path"
