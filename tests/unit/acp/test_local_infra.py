from __future__ import annotations

import json
import subprocess
import sys
from unittest.mock import MagicMock

import pytest

from optimus.acp import local_infra
from optimus.acp.local_gateway_secrets import (
    CredentialLayer,
    CredentialProvenance,
    ProviderCredentialResolution,
    ProviderSecrets,
)

_HMAC_KEY = b"test-local-infra-hmac-key-32byt!"
_MCP_PROFILE = {
    "profile_id": "context7",
    "revision": "rev-1",
    "manifest_hash": "a" * 64,
    "transport": "http",
    "credential_ref": "gateway://mcp/context7",
    "upstream_allowlist": ["search"],
    "limits": {"max_pages": 10, "max_tools": 50, "max_descriptor_bytes": 65536},
    "attribution_policy": {"allow_unattributed_spend": False},
    "transport_config": {"endpoint": "https://context7.example/mcp"},
}


def _resolution(secrets: ProviderSecrets | None) -> ProviderCredentialResolution:
    provenance = CredentialProvenance(CredentialLayer.ENVIRONMENT, "test")
    return ProviderCredentialResolution(
        secrets=secrets,
        provider_provenance=provenance,
        api_key_provenance=provenance,
        base_url_provenance=provenance,
    )


def test_strip_local_provider_keys_removes_vendor_keys_but_keeps_optimus_vars() -> None:
    environ = {
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
        "OPTIMUS_API_KEY": "shared-secret",
        "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
        "ANTHROPIC_API_KEY": "sk-ant-leaked",
        "OPENAI_API_KEY": "sk-oai-leaked",
    }

    sanitized = local_infra.strip_local_provider_keys(environ)

    assert sanitized == {
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
        "OPTIMUS_API_KEY": "shared-secret",
        "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
    }
    assert environ["ANTHROPIC_API_KEY"] == "sk-ant-leaked"


def test_strip_local_provider_keys_also_removes_openrouter_key_and_shared_secret() -> None:
    environ = {
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
        "OPTIMUS_API_KEY": "shared-secret",
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "sk-or-leaked",
        "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "shared-secret",
    }

    sanitized = local_infra.strip_local_provider_keys(environ)

    assert sanitized == {
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
        "OPTIMUS_API_KEY": "shared-secret",
    }


def test_agent_projection_excludes_every_provider_and_gateway_child_secret() -> None:
    projected = local_infra.strip_local_provider_keys(
        {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "agent-secret",
            "OPENROUTER_API_KEY": "or-secret",
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "or-secret",
            "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "child-secret",
            "OPTIMUS_PRODUCTION_MODE": "false",
            "OPTIMUS_EXTRA_GATEWAY_ORIGINS": "https://example.com",
        }
    )

    assert projected == {
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
        "OPTIMUS_API_KEY": "agent-secret",
    }


# --- apply_local_defaults: Task 5 signature (resolved_shared_secret param,
# no internal credential re-resolution) ---


def test_apply_local_defaults_fills_loopback_urls_when_unset(tmp_path) -> None:
    result = local_infra.apply_local_defaults({}, config_root=tmp_path)

    assert result["OPTIMUS_REDIS_URL"] == "redis://127.0.0.1:6379/0"
    assert result["OPTIMUS_GATEWAY_URL"] == "http://127.0.0.1:8765"
    assert "OPTIMUS_PRODUCTION_MODE" not in result
    assert result["OPTIMUS_AGENT_MODEL"] == "claude-haiku"


def test_apply_local_defaults_leaves_explicit_values_untouched(tmp_path) -> None:
    input_environ = {
        "OPTIMUS_REDIS_URL": "redis://custom:6380/1",
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:9999",
        "OPTIMUS_PRODUCTION_MODE": "true",
        "OPTIMUS_AGENT_MODEL": "gpt-4",
        "OPTIMUS_API_KEY": "explicit-key",
    }

    result = local_infra.apply_local_defaults(input_environ, config_root=tmp_path)

    assert result == input_environ
    assert result is not input_environ


def test_apply_local_defaults_uses_passed_in_resolved_shared_secret(tmp_path) -> None:
    result = local_infra.apply_local_defaults({}, config_root=tmp_path, resolved_shared_secret="resolved-secret")

    assert result["OPTIMUS_API_KEY"] == "resolved-secret"


def test_apply_local_defaults_no_resolved_secret_means_no_api_key(tmp_path) -> None:
    result = local_infra.apply_local_defaults({}, config_root=tmp_path, resolved_shared_secret=None)

    assert "OPTIMUS_API_KEY" not in result


def test_apply_local_defaults_skips_production_mode_and_model_for_hosted_gateway(tmp_path) -> None:
    result = local_infra.apply_local_defaults(
        {"OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai"},
        config_root=tmp_path,
    )

    assert result == {"OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai", "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0"}
    assert "OPTIMUS_PRODUCTION_MODE" not in result
    assert "OPTIMUS_AGENT_MODEL" not in result


def test_apply_local_defaults_does_not_mutate_input_or_os_environ(tmp_path) -> None:
    input_environ: dict[str, str] = {}

    result = local_infra.apply_local_defaults(input_environ, config_root=tmp_path)

    assert input_environ == {}
    assert result is not input_environ


# --- ensure_local_redis: unchanged ---


def test_ensure_local_redis_noops_when_already_reachable(monkeypatch) -> None:
    run_calls: list[list[str]] = []
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: True)
    monkeypatch.setattr(local_infra.shutil, "which", lambda _name: "docker")

    def fake_run(args, **_k):
        run_calls.append(list(args))
        if args[:3] == ["docker", "ps", "--filter"]:
            return _fake_docker_ps_owner("optimus-redis", "redis:8")
        raise AssertionError(f"unexpected docker call: {args}")

    monkeypatch.setattr(local_infra.subprocess, "run", fake_run)

    local_infra.ensure_local_redis("redis://127.0.0.1:6379/0")

    assert run_calls == [
        ["docker", "ps", "--filter", "publish=6379", "--format", "{{.Names}}\t{{.Image}}"],
    ]


def test_ensure_local_redis_noops_for_non_loopback_host(monkeypatch) -> None:
    docker_calls: list[object] = []
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: False)
    monkeypatch.setattr(local_infra.subprocess, "run", lambda *a, **k: docker_calls.append((a, k)))

    local_infra.ensure_local_redis("redis://remote.example.com:6379/0")

    assert docker_calls == []


def test_ensure_local_redis_noops_when_docker_missing(monkeypatch) -> None:
    docker_calls: list[object] = []
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: False)
    monkeypatch.setattr(local_infra.shutil, "which", lambda _name: None)
    monkeypatch.setattr(local_infra.subprocess, "run", lambda *a, **k: docker_calls.append((a, k)))
    messages: list[str] = []

    local_infra.ensure_local_redis("redis://127.0.0.1:6379/0", log=messages.append)

    assert docker_calls == []
    assert any("docker not found" in msg for msg in messages)


def test_ensure_local_redis_noops_when_docker_daemon_unreachable(monkeypatch) -> None:
    docker_calls: list[object] = []
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: False)
    monkeypatch.setattr(local_infra.shutil, "which", lambda _name: "/usr/bin/docker")
    monkeypatch.setattr(local_infra, "_docker_daemon_reachable", lambda _docker: False)
    monkeypatch.setattr(local_infra.subprocess, "run", lambda *a, **k: docker_calls.append((a, k)))
    messages: list[str] = []

    local_infra.ensure_local_redis("redis://127.0.0.1:6379/0", log=messages.append)

    assert docker_calls == []
    assert any("Docker daemon not reachable" in msg for msg in messages)


def test_ensure_local_redis_creates_container_when_missing(monkeypatch) -> None:
    run_calls: list[list[str]] = []
    monkeypatch.setattr(local_infra.shutil, "which", lambda _name: "docker")
    monkeypatch.setattr(local_infra, "_docker_daemon_reachable", lambda _docker: True)
    monkeypatch.setattr(local_infra, "_container_exists", lambda *_a, **_k: False)
    monkeypatch.setattr(local_infra.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        local_infra,
        "_tcp_reachable",
        MagicMock(side_effect=[False, False, True]),
    )

    def fake_run(args, **_k):
        run_calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(local_infra.subprocess, "run", fake_run)

    local_infra.ensure_local_redis("redis://127.0.0.1:6379/0")

    assert run_calls == [
        ["docker", "run", "-d", "--name", "optimus-redis", "-p", "127.0.0.1:6379:6379", "redis:8"],
    ]
    assert "--rm" not in run_calls[0]


def test_ensure_local_redis_starts_existing_container(monkeypatch) -> None:
    run_calls: list[list[str]] = []
    monkeypatch.setattr(local_infra.shutil, "which", lambda _name: "docker")
    monkeypatch.setattr(local_infra, "_docker_daemon_reachable", lambda _docker: True)
    monkeypatch.setattr(local_infra, "_container_exists", lambda *_a, **_k: True)
    monkeypatch.setattr(local_infra.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        local_infra,
        "_tcp_reachable",
        MagicMock(side_effect=[False, False, True]),
    )

    def fake_run(args, **_k):
        run_calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(local_infra.subprocess, "run", fake_run)

    local_infra.ensure_local_redis("redis://127.0.0.1:6379/0")

    assert run_calls == [["docker", "start", "optimus-redis"]]


# --- Plan 11.6 Task 2: default-port Redis ownership ---


def _fake_docker_ps_owner(name: str, image: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        ["docker", "ps"],
        0,
        stdout=f"{name}\t{image}\n",
        stderr="",
    )


def _assert_no_destructive_docker_args(run_calls: list[list[str]]) -> None:
    destructive = {"stop", "rm", "rename", "update"}
    for cmd in run_calls:
        assert destructive.isdisjoint(cmd), cmd


def test_ensure_local_redis_accepts_default_port_owned_by_optimus_redis(monkeypatch) -> None:
    run_calls: list[list[str]] = []
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: True)
    monkeypatch.setattr(local_infra.shutil, "which", lambda _name: "docker")

    def fake_run(args, **_k):
        run_calls.append(list(args))
        if args[:3] == ["docker", "ps", "--filter"]:
            return _fake_docker_ps_owner("optimus-redis", "redis:7-alpine")
        raise AssertionError(f"unexpected docker call: {args}")

    monkeypatch.setattr(local_infra.subprocess, "run", fake_run)

    local_infra.ensure_local_redis("redis://127.0.0.1:6379/0")

    assert run_calls == [
        ["docker", "ps", "--filter", "publish=6379", "--format", "{{.Names}}\t{{.Image}}"],
    ]
    _assert_no_destructive_docker_args(run_calls)


def test_ensure_local_redis_raises_port_conflict_for_wrong_docker_owner(monkeypatch) -> None:
    run_calls: list[list[str]] = []
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: True)
    monkeypatch.setattr(local_infra.shutil, "which", lambda _name: "docker")

    def fake_run(args, **_k):
        run_calls.append(list(args))
        if args[:3] == ["docker", "ps", "--filter"]:
            return _fake_docker_ps_owner("optimus-plan112-redis", "redis:7-alpine")
        raise AssertionError(f"unexpected docker call: {args}")

    monkeypatch.setattr(local_infra.subprocess, "run", fake_run)

    with pytest.raises(local_infra.LocalInfrastructureError) as exc_info:
        local_infra.ensure_local_redis("redis://127.0.0.1:6379/0")

    assert exc_info.value.code == "REDIS_PORT_CONFLICT"
    assert "6379" in exc_info.value.user_message
    assert "optimus-plan112-redis" in exc_info.value.user_message
    _assert_no_destructive_docker_args(run_calls)


def test_ensure_local_redis_treats_reachable_default_without_docker_owner_as_native(monkeypatch) -> None:
    run_calls: list[list[str]] = []
    messages: list[str] = []
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: True)
    monkeypatch.setattr(local_infra.shutil, "which", lambda _name: "docker")

    def fake_run(args, **_k):
        run_calls.append(list(args))
        if args[:3] == ["docker", "ps", "--filter"]:
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected docker call: {args}")

    monkeypatch.setattr(local_infra.subprocess, "run", fake_run)

    local_infra.ensure_local_redis("redis://127.0.0.1:6379/0", log=messages.append)

    assert any("native" in msg.lower() or "operator-managed" in msg.lower() for msg in messages)
    _assert_no_destructive_docker_args(run_calls)


def test_ensure_local_redis_treats_reachable_default_when_docker_missing_as_native(monkeypatch) -> None:
    messages: list[str] = []
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: True)
    monkeypatch.setattr(local_infra.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        local_infra.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("docker must not be invoked")),
    )

    local_infra.ensure_local_redis("redis://127.0.0.1:6379/0", log=messages.append)

    assert any("native" in msg.lower() or "operator-managed" in msg.lower() for msg in messages)


def test_ensure_local_redis_non_default_reachable_url_skips_ownership_gate(monkeypatch) -> None:
    run_calls: list[object] = []
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: True)
    monkeypatch.setattr(local_infra.subprocess, "run", lambda *a, **k: run_calls.append((a, k)))

    local_infra.ensure_local_redis("redis://127.0.0.1:6380/0")

    assert run_calls == []


# --- ensure_local_gateway: Task 5 signature (pre-resolved credentials,
# explicit bind CLI args + signed manifest, no OPTIMUS_LOCAL_GATEWAY_BIND_HOST/PORT) ---


def _ensure_gateway_kwargs(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "gateway_url": "http://127.0.0.1:8765",
        "provider_credentials": _resolution(
            ProviderSecrets(provider="openrouter", model_provider_api_key="sk-or-test")
        ),
        "shared_secret": "shared-secret-value",
        "workspace_digest": "a" * 64,
        "security_snapshot_digest": "b" * 64,
        "manifest_hmac_key": _HMAC_KEY,
        "policy_version": "P9.96-v1",
    }
    defaults.update(overrides)
    return defaults


def test_ensure_local_gateway_noops_when_already_reachable(tmp_path, monkeypatch) -> None:
    popen_calls: list[object] = []
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: True)
    monkeypatch.setattr(local_infra.subprocess, "Popen", lambda *a, **k: popen_calls.append((a, k)))
    runtime_root = tmp_path / ".optimus"

    result = local_infra.ensure_local_gateway(
        **_ensure_gateway_kwargs(),
        runtime_root=runtime_root,
    )

    assert result is None
    assert popen_calls == []
    assert not (runtime_root / "local-gateway.log").exists()


def test_ensure_local_gateway_noops_for_non_loopback_url(tmp_path, monkeypatch) -> None:
    popen_calls: list[object] = []
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: False)
    monkeypatch.setattr(local_infra.subprocess, "Popen", lambda *a, **k: popen_calls.append((a, k)))

    result = local_infra.ensure_local_gateway(
        **_ensure_gateway_kwargs(gateway_url="https://gateway.optimus.ai"),
        runtime_root=tmp_path / ".optimus",
    )

    assert result is None
    assert popen_calls == []


def test_ensure_local_gateway_noops_when_provider_credentials_none(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: False)
    messages: list[str] = []

    result = local_infra.ensure_local_gateway(
        **_ensure_gateway_kwargs(provider_credentials=None),
        runtime_root=tmp_path / ".optimus",
        log=messages.append,
    )

    assert result is None
    assert any("no compatible local gateway credentials" in msg for msg in messages)


def test_ensure_local_gateway_noops_when_secrets_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: False)
    messages: list[str] = []

    result = local_infra.ensure_local_gateway(
        **_ensure_gateway_kwargs(provider_credentials=_resolution(None)),
        runtime_root=tmp_path / ".optimus",
        log=messages.append,
    )

    assert result is None
    assert any("no compatible local gateway credentials" in msg for msg in messages)


def test_ensure_local_gateway_noops_when_shared_secret_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: False)
    messages: list[str] = []

    result = local_infra.ensure_local_gateway(
        **_ensure_gateway_kwargs(shared_secret=None),
        runtime_root=tmp_path / ".optimus",
        log=messages.append,
    )

    assert result is None
    assert any("no compatible local gateway credentials" in msg for msg in messages)


def test_ensure_local_gateway_spawns_with_exact_cli_args_and_manifest(tmp_path, monkeypatch) -> None:
    reachable_calls = {"n": 0}

    def fake_tcp_reachable(host, port, *, timeout=1.0):
        reachable_calls["n"] += 1
        return reachable_calls["n"] > 1

    monkeypatch.setattr(local_infra, "_tcp_reachable", fake_tcp_reachable)
    monkeypatch.setattr(local_infra.time, "sleep", lambda _seconds: None)
    messages: list[str] = []

    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 4321
        returncode = None

        def poll(self):
            return None

    def fake_popen(args, *, env, stdin, stdout, stderr):
        captured["args"] = args
        captured["env"] = env
        captured["stdout"] = stdout
        return FakeProcess()

    monkeypatch.setattr(local_infra.subprocess, "Popen", fake_popen)

    result = local_infra.ensure_local_gateway(
        **_ensure_gateway_kwargs(),
        runtime_root=tmp_path / ".optimus",
        system_env={"PATH": "C:/some/path"},
        log=messages.append,
    )

    assert result is not None
    args = captured["args"]
    assert args[:3] == [sys.executable, "-m", "optimus_gateway"]
    assert "--bind-host" in args and args[args.index("--bind-host") + 1] == "127.0.0.1"
    assert "--port" in args and args[args.index("--port") + 1] == "8765"
    assert "--manifest" in args
    # No OPTIMUS_LOCAL_GATEWAY_BIND_HOST/PORT in the child env — bind is CLI-only now.
    gateway_env = captured["env"]
    assert "OPTIMUS_LOCAL_GATEWAY_BIND_HOST" not in gateway_env
    assert "OPTIMUS_LOCAL_GATEWAY_PORT" not in gateway_env
    assert gateway_env["OPTIMUS_LOCAL_GATEWAY_PROVIDER"] == "openrouter"
    assert gateway_env["OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET"] == "shared-secret-value"
    assert gateway_env["OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY"] == "sk-or-test"
    assert gateway_env["PATH"] == "C:/some/path"
    assert "ANTHROPIC_API_KEY" not in gateway_env
    assert captured["stdout"] != subprocess.PIPE
    assert result.log_path == tmp_path / ".optimus" / "local-gateway.log"
    startup_output = "\n".join(messages)
    assert "sk-or-test" not in startup_output
    assert "shared-secret-value" not in startup_output
    # The manifest itself must not contain the raw secret either.
    manifest_arg = args[args.index("--manifest") + 1]
    assert "sk-or-test" not in manifest_arg
    assert "shared-secret-value" not in manifest_arg


def test_ensure_local_gateway_forwards_non_secret_mcp_profile_bootstrap(tmp_path, monkeypatch) -> None:
    reachable_calls = {"n": 0}

    def fake_tcp_reachable(host, port, *, timeout=1.0):
        reachable_calls["n"] += 1
        return reachable_calls["n"] > 1

    monkeypatch.setattr(local_infra, "_tcp_reachable", fake_tcp_reachable)
    monkeypatch.setattr(local_infra.time, "sleep", lambda _seconds: None)
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 4322
        returncode = None

        def poll(self):
            return None

    def fake_popen(args, *, env, stdin, stdout, stderr):
        captured["args"] = args
        return FakeProcess()

    monkeypatch.setattr(local_infra.subprocess, "Popen", fake_popen)
    local_infra.ensure_local_gateway(
        **_ensure_gateway_kwargs(),
        runtime_root=tmp_path / ".optimus",
        mcp_profiles=(_MCP_PROFILE,),
    )

    args = captured["args"]
    manifest_arg = args[args.index("--manifest") + 1]
    assert json.loads(manifest_arg)["mcp_profiles"][0]["profile_id"] == "context7"
    assert "sk-or-test" not in manifest_arg
    assert "shared-secret-value" not in manifest_arg


def test_ensure_local_gateway_passes_through_custom_base_url(tmp_path, monkeypatch) -> None:
    reachable_calls = {"n": 0}

    def fake_tcp_reachable(host, port, *, timeout=1.0):
        reachable_calls["n"] += 1
        return reachable_calls["n"] > 1

    monkeypatch.setattr(local_infra, "_tcp_reachable", fake_tcp_reachable)
    monkeypatch.setattr(local_infra.time, "sleep", lambda _seconds: None)

    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 1111
        returncode = None

        def poll(self):
            return None

    def fake_popen(args, *, env, stdin, stdout, stderr):
        captured["env"] = env
        return FakeProcess()

    monkeypatch.setattr(local_infra.subprocess, "Popen", fake_popen)

    result = local_infra.ensure_local_gateway(
        **_ensure_gateway_kwargs(
            provider_credentials=_resolution(
                ProviderSecrets(
                    provider="openrouter",
                    model_provider_api_key="sk-test",
                    base_url="https://custom.example.com/v1",
                )
            )
        ),
        runtime_root=tmp_path / ".optimus",
    )

    assert result is not None
    assert captured["env"]["OPTIMUS_LOCAL_GATEWAY_BASE_URL"] == "https://custom.example.com/v1"


def test_ensure_local_gateway_fails_closed_when_log_file_preparation_raises(tmp_path, monkeypatch) -> None:
    runtime_root = tmp_path / ".optimus"
    runtime_root.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: False)
    popen_calls: list[object] = []
    monkeypatch.setattr(local_infra.subprocess, "Popen", lambda *a, **k: popen_calls.append((a, k)))
    messages: list[str] = []

    result = local_infra.ensure_local_gateway(
        **_ensure_gateway_kwargs(),
        runtime_root=runtime_root,
        log=messages.append,
    )

    assert result is None
    assert any("could not prepare local gateway log file" in msg for msg in messages)
    assert popen_calls == []


def test_ensure_local_gateway_fails_closed_when_popen_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda host, port, *, timeout=1.0: False)

    def raising_popen(*_a, **_k):
        raise OSError("spawn failed")

    monkeypatch.setattr(local_infra.subprocess, "Popen", raising_popen)
    messages: list[str] = []

    result = local_infra.ensure_local_gateway(
        **_ensure_gateway_kwargs(),
        runtime_root=tmp_path / ".optimus",
        log=messages.append,
    )

    assert result is None
    assert any("could not start local gateway process" in msg for msg in messages)


def test_ensure_local_gateway_returns_none_when_process_exits_early(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: False)
    monkeypatch.setattr(local_infra.time, "sleep", lambda _seconds: None)
    messages: list[str] = []

    class ExitingProcess:
        pid = 9999
        returncode = 1

        def poll(self):
            return 1

        def terminate(self):
            return None

        def wait(self, timeout=None):
            return 1

        def kill(self):
            return None

    monkeypatch.setattr(local_infra.subprocess, "Popen", lambda *a, **k: ExitingProcess())

    result = local_infra.ensure_local_gateway(
        **_ensure_gateway_kwargs(),
        runtime_root=tmp_path / ".optimus",
        log=messages.append,
    )

    assert result is None
    assert any("exited early" in msg for msg in messages)


def test_local_gateway_process_stop_terminates_running_process() -> None:
    process = MagicMock()
    process.poll.return_value = None

    handle = local_infra.LocalGatewayProcess(process=process, log_path=None)
    handle.stop()

    process.terminate.assert_called_once()
    process.wait.assert_called()


def test_local_gateway_process_stop_noops_when_already_exited() -> None:
    process = MagicMock()
    process.poll.return_value = 0

    handle = local_infra.LocalGatewayProcess(process=process, log_path=None)
    handle.stop()

    process.terminate.assert_not_called()


# --- Registry-projection exact key-set tests (review follow-up) ---
# Mirrors the agent-side exact-equality fix in subprocess_env.py: the Gateway
# child's env must not silently omit a registry-authorized GATEWAY_CHILD name,
# nor include a name the registry doesn't authorize for GATEWAY_CHILD. Unlike
# the agent side, only ONE provider-key name is ever "applicable" per launch
# (whichever provider is resolved), so the comparison is against the
# applicable subset of the registry's GATEWAY_CHILD names for that provider,
# not the full cross-provider set.


def _gateway_child_registry_names() -> set[str]:
    from optimus.acp.launch_policy import LAUNCH_VARIABLE_POLICIES, PropagationTarget

    return {name for name, policy in LAUNCH_VARIABLE_POLICIES.items() if PropagationTarget.GATEWAY_CHILD in policy.propagation}


def test_openrouter_gateway_child_env_exactly_matches_applicable_registry_projection(tmp_path, monkeypatch) -> None:
    reachable_calls = {"n": 0}

    def fake_tcp_reachable(host, port, *, timeout=1.0):
        reachable_calls["n"] += 1
        return reachable_calls["n"] > 1

    monkeypatch.setattr(local_infra, "_tcp_reachable", fake_tcp_reachable)
    monkeypatch.setattr(local_infra.time, "sleep", lambda _seconds: None)

    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 3333
        returncode = None

        def poll(self):
            return None

    def fake_popen(args, *, env, stdin, stdout, stderr):
        captured["env"] = env
        return FakeProcess()

    monkeypatch.setattr(local_infra.subprocess, "Popen", fake_popen)

    local_infra.ensure_local_gateway(
        **_ensure_gateway_kwargs(
            provider_credentials=_resolution(
                ProviderSecrets(
                    provider="openrouter",
                    model_provider_api_key="sk-or-test",
                    base_url="https://openrouter.ai/api/v1",
                )
            )
        ),
        runtime_root=tmp_path / ".optimus",
    )

    registry_names = _gateway_child_registry_names()
    applicable = {
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER",
        "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET",
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY",
        "OPTIMUS_LOCAL_GATEWAY_BASE_URL",
    }
    assert applicable.issubset(registry_names)
    inapplicable = registry_names - applicable
    child_env = captured["env"]
    assert applicable.issubset(child_env.keys())
    assert not (inapplicable & child_env.keys())


def test_ensure_local_gateway_forwards_tool_env_from_config_root_env_gateway(tmp_path, monkeypatch) -> None:
    """Plan 11.2 Task 6 pre-work: tool vars from config_root/.env.gateway reach the child."""
    reachable_calls = {"n": 0}

    def fake_tcp_reachable(host, port, *, timeout=1.0):
        reachable_calls["n"] += 1
        return reachable_calls["n"] > 1

    monkeypatch.setattr(local_infra, "_tcp_reachable", fake_tcp_reachable)
    monkeypatch.setattr(local_infra.time, "sleep", lambda _seconds: None)

    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / ".env.gateway").write_text(
        "TAVILY_API_KEY=tvly-from-config\n"
        "OPTIMUS_GATEWAY_TOOL_ALLOWED_DOMAINS=python.org\n"
        "OPTIMUS_GATEWAY_TOOL_REDIS_URL=redis://127.0.0.1:6379/0\n",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 4444
        returncode = None

        def poll(self):
            return None

    def fake_popen(args, *, env, stdin, stdout, stderr):
        captured["env"] = env
        return FakeProcess()

    monkeypatch.setattr(local_infra.subprocess, "Popen", fake_popen)

    local_infra.ensure_local_gateway(
        **_ensure_gateway_kwargs(),
        runtime_root=tmp_path / ".optimus",
        config_root=config_root,
    )

    child_env = captured["env"]
    assert child_env["TAVILY_API_KEY"] == "tvly-from-config"
    assert child_env["OPTIMUS_GATEWAY_TOOL_ALLOWED_DOMAINS"] == "python.org"
    assert child_env["OPTIMUS_GATEWAY_TOOL_REDIS_URL"] == "redis://127.0.0.1:6379/0"


def test_retired_origin_configuration_is_not_in_gateway_child_registry() -> None:
    from optimus.acp.launch_policy import LAUNCH_VARIABLE_POLICIES
    from optimus.acp.local_infra import RETIRED_AGENT_ENVIRON_KEYS

    assert "OPTIMUS_PRODUCTION_MODE" not in LAUNCH_VARIABLE_POLICIES
    assert "OPTIMUS_EXTRA_GATEWAY_ORIGINS" not in LAUNCH_VARIABLE_POLICIES
    assert RETIRED_AGENT_ENVIRON_KEYS == frozenset(
        {
            "OPTIMUS_PRODUCTION_MODE",
            "OPTIMUS_EXTRA_GATEWAY_ORIGINS",
        }
    )


# --- Plan 11.6 Task 3: local Phoenix lifecycle ---


def test_ensure_local_phoenix_creates_named_container_when_missing(monkeypatch) -> None:
    run_calls: list[list[str]] = []
    health_urls: list[str] = []
    monkeypatch.setattr(local_infra.shutil, "which", lambda _name: "docker")
    monkeypatch.setattr(local_infra, "_docker_daemon_reachable", lambda _docker: True)
    monkeypatch.setattr(local_infra, "_container_exists", lambda *_a, **_k: False)
    monkeypatch.setattr(local_infra, "_docker_published_port_owners", lambda *_a, **_k: [])
    monkeypatch.setattr(local_infra.time, "sleep", lambda _seconds: None)

    def fake_run(args, **_k):
        run_calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(local_infra.subprocess, "run", fake_run)
    monkeypatch.setattr(
        local_infra,
        "_phoenix_health_ready",
        lambda url: health_urls.append(url) or True,
    )

    endpoint = local_infra.ensure_local_phoenix()

    assert endpoint == local_infra.LOCAL_PHOENIX_OTLP_ENDPOINT
    assert run_calls == [
        [
            "docker",
            "run",
            "-d",
            "--name",
            "optimus-phoenix",
            "-p",
            "127.0.0.1:6006:6006",
            "arizephoenix/phoenix:latest",
        ],
    ]
    assert health_urls == ["http://127.0.0.1:6006/healthz"]
    _assert_no_destructive_docker_args(run_calls)


def test_ensure_local_phoenix_starts_existing_matching_container(monkeypatch) -> None:
    run_calls: list[list[str]] = []
    health_calls = {"n": 0}
    monkeypatch.setattr(local_infra.shutil, "which", lambda _name: "docker")
    monkeypatch.setattr(local_infra, "_docker_daemon_reachable", lambda _docker: True)
    monkeypatch.setattr(local_infra, "_container_exists", lambda *_a, **_k: True)
    monkeypatch.setattr(
        local_infra,
        "_docker_published_port_owners",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        local_infra,
        "_docker_container_image",
        lambda *_a, **_k: "arizephoenix/phoenix:latest",
    )

    def fake_health(_url: str) -> bool:
        health_calls["n"] += 1
        return health_calls["n"] > 1

    monkeypatch.setattr(local_infra, "_phoenix_health_ready", fake_health)
    monkeypatch.setattr(local_infra.time, "sleep", lambda _seconds: None)

    def fake_run(args, **_k):
        run_calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(local_infra.subprocess, "run", fake_run)

    endpoint = local_infra.ensure_local_phoenix()

    assert endpoint == local_infra.LOCAL_PHOENIX_OTLP_ENDPOINT
    assert run_calls == [["docker", "start", "optimus-phoenix"]]
    _assert_no_destructive_docker_args(run_calls)


def test_ensure_local_phoenix_raises_on_wrong_port_owner(monkeypatch) -> None:
    run_calls: list[list[str]] = []
    monkeypatch.setattr(local_infra.shutil, "which", lambda _name: "docker")
    monkeypatch.setattr(local_infra, "_docker_daemon_reachable", lambda _docker: True)
    monkeypatch.setattr(
        local_infra,
        "_docker_published_port_owners",
        lambda *_a, **_k: [("other-phoenix", "arizephoenix/phoenix:latest")],
    )
    monkeypatch.setattr(local_infra.subprocess, "run", lambda *a, **k: run_calls.append(list(a[0])))

    with pytest.raises(local_infra.LocalInfrastructureError) as exc_info:
        local_infra.ensure_local_phoenix()

    assert "PHOENIX" in exc_info.value.code
    assert "6006" in exc_info.value.user_message
    assert "other-phoenix" in exc_info.value.user_message
    _assert_no_destructive_docker_args(run_calls)


def test_ensure_local_phoenix_raises_on_wrong_image_for_named_container(monkeypatch) -> None:
    monkeypatch.setattr(local_infra.shutil, "which", lambda _name: "docker")
    monkeypatch.setattr(local_infra, "_docker_daemon_reachable", lambda _docker: True)
    monkeypatch.setattr(local_infra, "_container_exists", lambda *_a, **_k: True)
    monkeypatch.setattr(
        local_infra,
        "_docker_published_port_owners",
        lambda *_a, **_k: [("optimus-phoenix", "wrong/image:tag")],
    )
    monkeypatch.setattr(
        local_infra.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not mutate")),
    )

    with pytest.raises(local_infra.LocalInfrastructureError) as exc_info:
        local_infra.ensure_local_phoenix()

    assert "PHOENIX" in exc_info.value.code
    assert "wrong/image:tag" in exc_info.value.user_message or "arizephoenix/phoenix:latest" in exc_info.value.user_message


def test_ensure_local_gateway_injects_otlp_endpoint_into_child_env_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(local_infra, "_tcp_reachable", MagicMock(side_effect=[False, True]))
    monkeypatch.setattr(local_infra.time, "sleep", lambda _seconds: None)
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 1
        returncode = None

        def poll(self):
            return None

    def fake_popen(args, *, env, stdin, stdout, stderr):
        captured["env"] = env
        return FakeProcess()

    monkeypatch.setattr(local_infra.subprocess, "Popen", fake_popen)

    result = local_infra.ensure_local_gateway(
        **_ensure_gateway_kwargs(),
        runtime_root=tmp_path / ".optimus",
        otlp_endpoint="http://127.0.0.1:6006/v1/traces",
    )

    assert result is not None
    child_env = captured["env"]
    assert isinstance(child_env, dict)
    assert child_env["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://127.0.0.1:6006/v1/traces"
    assert set(k for k in child_env if k.startswith("OTEL_")) == {"OTEL_EXPORTER_OTLP_ENDPOINT"}


def test_ensure_local_gateway_omits_otlp_when_endpoint_none(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(local_infra, "_tcp_reachable", MagicMock(side_effect=[False, True]))
    monkeypatch.setattr(local_infra.time, "sleep", lambda _seconds: None)
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 1
        returncode = None

        def poll(self):
            return None

    monkeypatch.setattr(
        local_infra.subprocess,
        "Popen",
        lambda args, *, env, stdin, stdout, stderr: captured.update(env=env) or FakeProcess(),
    )

    local_infra.ensure_local_gateway(
        **_ensure_gateway_kwargs(),
        runtime_root=tmp_path / ".optimus",
        otlp_endpoint=None,
    )

    assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in captured["env"]
