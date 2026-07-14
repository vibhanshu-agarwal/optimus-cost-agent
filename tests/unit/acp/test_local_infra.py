from __future__ import annotations

import os
import subprocess
import sys
from unittest.mock import MagicMock

from optimus.acp import local_infra
from optimus.acp.local_gateway_secrets import (
    CredentialLayer,
    CredentialProvenance,
    ProviderCredentialConfigurationError,
    ProviderCredentialResolution,
    ProviderSecrets,
)


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


def test_apply_local_defaults_fills_loopback_urls_when_unset(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(local_infra, "resolve_shared_secret", lambda *_a, **_k: None)

    result = local_infra.apply_local_defaults({}, config_root=tmp_path)

    assert result["OPTIMUS_REDIS_URL"] == "redis://127.0.0.1:6379/0"
    assert result["OPTIMUS_GATEWAY_URL"] == "http://127.0.0.1:8765"
    assert result["OPTIMUS_PRODUCTION_MODE"] == "false"
    assert result["OPTIMUS_AGENT_MODEL"] == "claude-haiku"


def test_apply_local_defaults_leaves_explicit_values_untouched(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(local_infra, "resolve_shared_secret", lambda *_a, **_k: None)
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


def test_apply_local_defaults_resolves_api_key_from_shared_secret_on_loopback(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(local_infra, "resolve_shared_secret", lambda *_a, **_k: "resolved-secret")

    result = local_infra.apply_local_defaults({}, config_root=tmp_path)

    assert result["OPTIMUS_API_KEY"] == "resolved-secret"


def test_apply_local_defaults_skips_production_mode_and_model_for_hosted_gateway(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(local_infra, "resolve_shared_secret", lambda *_a, **_k: None)

    result = local_infra.apply_local_defaults(
        {"OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai"},
        config_root=tmp_path,
    )

    assert result == {"OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai", "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0"}
    assert "OPTIMUS_PRODUCTION_MODE" not in result
    assert "OPTIMUS_AGENT_MODEL" not in result


def test_apply_local_defaults_does_not_mutate_input_or_os_environ(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(local_infra, "resolve_shared_secret", lambda *_a, **_k: None)
    input_environ: dict[str, str] = {}

    result = local_infra.apply_local_defaults(input_environ, config_root=tmp_path)

    assert input_environ == {}
    assert result is not input_environ


def test_ensure_local_redis_noops_when_already_reachable(monkeypatch) -> None:
    docker_calls: list[object] = []
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: True)
    monkeypatch.setattr(local_infra.subprocess, "run", lambda *a, **k: docker_calls.append((a, k)))

    local_infra.ensure_local_redis("redis://127.0.0.1:6379/0")

    assert docker_calls == []


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


def test_ensure_local_gateway_noops_when_already_reachable(tmp_path, monkeypatch) -> None:
    popen_calls: list[object] = []
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: True)
    monkeypatch.setattr(local_infra.subprocess, "Popen", lambda *a, **k: popen_calls.append((a, k)))

    result = local_infra.ensure_local_gateway(
        environ={"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765"},
        config_root=tmp_path,
        runtime_root=tmp_path / ".optimus",
    )

    assert result is None
    assert popen_calls == []


def test_credential_conflict_stops_before_log_or_spawn(tmp_path, monkeypatch):
    runtime_root = tmp_path / "workspace" / ".optimus"
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: False)
    monkeypatch.setattr(
        local_infra,
        "resolve_provider_credentials",
        MagicMock(side_effect=ProviderCredentialConfigurationError("sanitized mismatch")),
    )
    popen = MagicMock()
    monkeypatch.setattr(local_infra.subprocess, "Popen", popen)
    messages = []
    assert local_infra.ensure_local_gateway(
        environ={"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765"},
        config_root=tmp_path / "config",
        runtime_root=runtime_root,
        log=messages.append,
    ) is None
    popen.assert_not_called()
    assert not runtime_root.exists()
    assert messages == ["sanitized mismatch"]


def test_reused_gateway_creates_no_log_in_second_workspace(tmp_path, monkeypatch):
    runtime_root = tmp_path / "second-workspace" / ".optimus"
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: True)
    assert local_infra.ensure_local_gateway(
        environ={"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765"},
        config_root=tmp_path / "config",
        runtime_root=runtime_root,
    ) is None
    assert not (runtime_root / "local-gateway.log").exists()


def test_ensure_local_gateway_noops_for_non_loopback_url(tmp_path, monkeypatch) -> None:
    popen_calls: list[object] = []
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: False)
    monkeypatch.setattr(local_infra.subprocess, "Popen", lambda *a, **k: popen_calls.append((a, k)))

    result = local_infra.ensure_local_gateway(
        environ={"OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai"},
        config_root=tmp_path,
        runtime_root=tmp_path / ".optimus",
    )

    assert result is None
    assert popen_calls == []


def test_ensure_local_gateway_noops_when_no_secrets(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: False)
    monkeypatch.setattr(local_infra, "resolve_provider_credentials", lambda *_a, **_k: _resolution(None))
    monkeypatch.setattr(local_infra, "resolve_shared_secret", lambda *_a, **_k: None)
    messages: list[str] = []

    result = local_infra.ensure_local_gateway(
        environ={"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765"},
        config_root=tmp_path,
        runtime_root=tmp_path / ".optimus",
        log=messages.append,
    )

    assert result is None
    assert any("run `optimus-agent --setup`" in msg for msg in messages)


def test_ensure_local_gateway_reports_unsupported_provider_without_setup_pointer(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: False)
    messages: list[str] = []

    result = local_infra.ensure_local_gateway(
        environ={
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER": "typo-provider",
        },
        config_root=tmp_path,
        runtime_root=tmp_path / ".optimus",
        log=messages.append,
    )

    assert result is None
    assert any("unsupported provider" in msg for msg in messages)
    assert not any("run `optimus-agent --setup`" in msg for msg in messages)


def test_ensure_local_gateway_spawns_with_exact_gateway_env_and_no_stray_secrets(tmp_path, monkeypatch) -> None:
    (tmp_path / "src").mkdir()
    reachable_calls = {"n": 0}

    def fake_tcp_reachable(host, port, *, timeout=1.0):
        reachable_calls["n"] += 1
        return reachable_calls["n"] > 1

    monkeypatch.setattr(local_infra, "_tcp_reachable", fake_tcp_reachable)
    monkeypatch.setattr(
        local_infra,
        "resolve_provider_credentials",
        lambda environ, *, config_root: _resolution(
            ProviderSecrets(provider="openrouter", model_provider_api_key="sk-or-test")
        ),
    )
    monkeypatch.setattr(local_infra, "resolve_shared_secret", lambda environ, *, config_root: "shared-secret-value")
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
        environ={"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765", "PATH": os.environ.get("PATH", "")},
        config_root=tmp_path,
        runtime_root=tmp_path / ".optimus",
        log=messages.append,
    )

    assert result is not None
    assert captured["args"] == [sys.executable, "-m", "optimus_gateway"]
    gateway_env = captured["env"]
    assert gateway_env["OPTIMUS_LOCAL_GATEWAY_PROVIDER"] == "openrouter"
    assert gateway_env["OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET"] == "shared-secret-value"
    assert gateway_env["OPTIMUS_LOCAL_GATEWAY_BIND_HOST"] == "127.0.0.1"
    assert gateway_env["OPTIMUS_LOCAL_GATEWAY_PORT"] == "8765"
    assert gateway_env["OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY"] == "sk-or-test"
    assert "ANTHROPIC_API_KEY" not in gateway_env
    assert gateway_env is not os.environ
    assert captured["stdout"] != subprocess.PIPE
    assert result.log_path == tmp_path / ".optimus" / "local-gateway.log"
    startup_output = "\n".join(messages)
    assert "sk-or-test" not in startup_output
    assert "shared-secret-value" not in startup_output


def test_ensure_local_gateway_passes_through_custom_base_url(tmp_path, monkeypatch) -> None:
    (tmp_path / "src").mkdir()
    reachable_calls = {"n": 0}

    def fake_tcp_reachable(host, port, *, timeout=1.0):
        reachable_calls["n"] += 1
        return reachable_calls["n"] > 1

    monkeypatch.setattr(local_infra, "_tcp_reachable", fake_tcp_reachable)
    monkeypatch.setattr(
        local_infra,
        "resolve_provider_credentials",
        lambda environ, *, config_root: _resolution(
            ProviderSecrets(
                provider="openai",
                model_provider_api_key="sk-test",
                base_url="https://custom.example.com/v1",
            )
        ),
    )
    monkeypatch.setattr(local_infra, "resolve_shared_secret", lambda environ, *, config_root: "shared-secret-value")
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
        environ={"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765"},
        config_root=tmp_path,
        runtime_root=tmp_path / ".optimus",
    )

    assert result is not None
    assert captured["env"]["OPTIMUS_LOCAL_GATEWAY_BASE_URL"] == "https://custom.example.com/v1"


def test_ensure_local_gateway_fails_closed_when_log_file_preparation_raises(tmp_path, monkeypatch) -> None:
    runtime_root = tmp_path / ".optimus"
    runtime_root.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: False)
    monkeypatch.setattr(
        local_infra,
        "resolve_provider_credentials",
        lambda environ, *, config_root: _resolution(
            ProviderSecrets(provider="openrouter", model_provider_api_key="sk-or-test")
        ),
    )
    monkeypatch.setattr(local_infra, "resolve_shared_secret", lambda environ, *, config_root: "shared-secret-value")
    popen_calls: list[object] = []
    monkeypatch.setattr(local_infra.subprocess, "Popen", lambda *a, **k: popen_calls.append((a, k)))
    messages: list[str] = []

    result = local_infra.ensure_local_gateway(
        environ={"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765"},
        config_root=tmp_path,
        runtime_root=runtime_root,
        log=messages.append,
    )

    assert result is None
    assert any("could not prepare local gateway log file" in msg for msg in messages)
    assert popen_calls == []


def test_ensure_local_gateway_fails_closed_when_popen_raises(tmp_path, monkeypatch) -> None:
    (tmp_path / "src").mkdir()
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda host, port, *, timeout=1.0: False)
    monkeypatch.setattr(
        local_infra,
        "resolve_provider_credentials",
        lambda environ, *, config_root: _resolution(
            ProviderSecrets(provider="openrouter", model_provider_api_key="sk-or-test")
        ),
    )
    monkeypatch.setattr(local_infra, "resolve_shared_secret", lambda environ, *, config_root: "shared-secret-value")

    def raising_popen(*_a, **_k):
        raise OSError("spawn failed")

    monkeypatch.setattr(local_infra.subprocess, "Popen", raising_popen)
    messages: list[str] = []

    result = local_infra.ensure_local_gateway(
        environ={"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765"},
        config_root=tmp_path,
        runtime_root=tmp_path / ".optimus",
        log=messages.append,
    )

    assert result is None
    assert any("could not start local gateway process" in msg for msg in messages)


def test_ensure_local_gateway_returns_none_when_process_exits_early(tmp_path, monkeypatch) -> None:
    (tmp_path / "src").mkdir()
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: False)
    monkeypatch.setattr(
        local_infra,
        "resolve_provider_credentials",
        lambda environ, *, config_root: _resolution(
            ProviderSecrets(provider="openrouter", model_provider_api_key="sk-or-test")
        ),
    )
    monkeypatch.setattr(local_infra, "resolve_shared_secret", lambda environ, *, config_root: "shared-secret-value")
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
        environ={"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765"},
        config_root=tmp_path,
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
