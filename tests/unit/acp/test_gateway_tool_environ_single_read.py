"""#680: an ACP launch hands its Gateway exactly the tool configuration the launch gate validated. `.env.gateway` is read
once, at the gate; an edit after that reaches neither the Gateway's expected identity nor the spawned child's environment.
Fake keyring, stub child (Popen is replaced and never starts a process); synthetic values only."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from optimus.acp import __main__ as acp_main
from optimus.acp import local_infra
from tests.unit.acp.test_main_wiring import _authorize, _base_env, _patch_common

pytestmark = pytest.mark.usefixtures("isolated_windows_known_folders")

_TOOL_REDIS = "OPTIMUS_GATEWAY_TOOL_REDIS_URL"
_VALIDATED = "redis://127.0.0.1:6379/0"
# U+FF03 NFKC-normalizes to "#": the gate refuses this value (#671), so it must never reach the child.
_UNVALIDATED = "redis://user:synthpw" + chr(0xFF03) + "@127.0.0.1:6379/0"


def _write_env_gateway(config: Path, value: str) -> None:
    path = config / ".env.gateway"
    path.write_text(f"{_TOOL_REDIS}={value}\n", encoding="utf-8")
    path.chmod(0o600)  # owner-only, or POSIX refuses on permissions first


def test_an_edit_after_the_gate_reaches_neither_the_identity_nor_the_gateway(monkeypatch, tmp_path: Path) -> None:
    workspace, config = tmp_path / "workspace", tmp_path / "config"
    workspace.mkdir()
    config.mkdir()
    _write_env_gateway(config, _VALIDATED)
    env = {
        **_base_env(),
        "OPTIMUS_CONFIG_ROOT": str(config),
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER": "openrouter",
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "sk-or-v1-" + "c" * 24,  # pragma: allowlist secret - synthetic
        "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "shared-" + "s" * 24,  # pragma: allowlist secret - synthetic
    }
    _authorize(monkeypatch, workspace, env)

    real_resolve = acp_main.resolve_launch_candidate

    def resolve_then_edit(**kwargs: Any) -> Any:
        candidate = real_resolve(**kwargs)
        _write_env_gateway(config, _UNVALIDATED)  # the window between the gate and the Gateway's start
        return candidate

    identity_tools: list[dict[str, str]] = []
    real_compose = local_infra.gateway_identity.compose_identity

    def compose(**kwargs: Any) -> Any:
        identity_tools.append(dict(kwargs["tool_environ"]))
        return real_compose(**kwargs)

    spawned: list[dict[str, str]] = []

    def popen(_args: list[str], **kwargs: Any) -> Any:
        spawned.append(dict(kwargs["env"]))
        raise OSError("stub child: not started")

    monkeypatch.setattr(acp_main, "resolve_launch_candidate", resolve_then_edit)
    monkeypatch.setattr(local_infra.gateway_identity, "compose_identity", compose)
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: False)
    monkeypatch.setattr(local_infra.subprocess, "Popen", popen)
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *_a, **_k: None)
    _patch_common(monkeypatch)

    acp_main.main(["--workspace-root", str(workspace)])

    assert identity_tools and spawned, (identity_tools, len(spawned))
    assert all(tools.get(_TOOL_REDIS) == _VALIDATED for tools in identity_tools)
    assert spawned[0].get(_TOOL_REDIS) == _VALIDATED
