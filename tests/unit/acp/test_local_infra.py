from __future__ import annotations

import contextlib
import http.server
import json
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from collections.abc import Iterator
from unittest.mock import MagicMock
from urllib.parse import urlparse

import pytest

from optimus.acp import local_infra
from optimus.acp.local_gateway_secrets import (
    CredentialLayer,
    CredentialProvenance,
    ProviderCredentialResolution,
    ProviderSecrets,
)
from optimus_security import url_schemes

_HMAC_KEY = b"test-local-infra-hmac-key-32byt!"


@pytest.fixture(autouse=True)
def _no_listener_to_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    """These suites fake the child and the socket, so nothing answers. `test_gateway_attach.py` tests the check for real."""
    monkeypatch.setattr(local_infra, "verify_local_gateway", lambda *_a, **_k: None)



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
        "OPTIMUS_API_KEY": "shared-secret",  # pragma: allowlist secret - synthetic test fixture
        "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
        "ANTHROPIC_API_KEY": "sk-ant-leaked",  # pragma: allowlist secret - synthetic test fixture
        "OPENAI_API_KEY": "sk-oai-leaked",  # pragma: allowlist secret - synthetic test fixture
    }

    sanitized = local_infra.strip_local_provider_keys(environ)

    assert sanitized == {
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
        "OPTIMUS_API_KEY": "shared-secret",  # pragma: allowlist secret - synthetic test fixture
        "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
    }
    assert environ["ANTHROPIC_API_KEY"] == "sk-ant-leaked"  # pragma: allowlist secret - synthetic test fixture


def test_strip_local_provider_keys_also_removes_openrouter_key_and_shared_secret() -> None:
    environ = {
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
        "OPTIMUS_API_KEY": "shared-secret",  # pragma: allowlist secret - synthetic test fixture
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "sk-or-leaked",  # pragma: allowlist secret - synthetic test fixture
        "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "shared-secret",  # pragma: allowlist secret - synthetic test fixture
    }

    sanitized = local_infra.strip_local_provider_keys(environ)

    assert sanitized == {
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
        "OPTIMUS_API_KEY": "shared-secret",  # pragma: allowlist secret - synthetic test fixture
    }


def test_agent_projection_excludes_every_provider_and_gateway_child_secret() -> None:
    projected = local_infra.strip_local_provider_keys(
        {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "agent-secret",  # pragma: allowlist secret - synthetic test fixture
            "OPENROUTER_API_KEY": "or-secret",  # pragma: allowlist secret - synthetic test fixture
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "or-secret",  # pragma: allowlist secret - synthetic test fixture
            "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "child-secret",  # pragma: allowlist secret - synthetic test fixture
            "OPTIMUS_PRODUCTION_MODE": "false",
            "OPTIMUS_EXTRA_GATEWAY_ORIGINS": "https://example.com",
        }
    )

    assert projected == {
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
        "OPTIMUS_API_KEY": "agent-secret",  # pragma: allowlist secret - synthetic test fixture
    }


# --- apply_local_defaults: Task 5 signature (resolved_shared_secret param,
# no internal credential re-resolution) ---


def test_apply_local_defaults_fills_loopback_urls_when_unset(tmp_path) -> None:
    result = local_infra.apply_local_defaults({}, config_root=tmp_path)

    assert result["OPTIMUS_REDIS_URL"] == "redis://127.0.0.1:6379/0"
    assert result["OPTIMUS_GATEWAY_URL"] == "http://127.0.0.1:8765"
    assert "OPTIMUS_PRODUCTION_MODE" not in result
    assert result["OPTIMUS_AGENT_MODEL"] == "anthropic/claude-haiku-5.5"  # the shipped default (closure plan v3)


def test_apply_local_defaults_leaves_explicit_values_untouched(tmp_path) -> None:
    input_environ = {
        "OPTIMUS_REDIS_URL": "redis://custom:6380/1",
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:9999",
        "OPTIMUS_PRODUCTION_MODE": "true",
        "OPTIMUS_AGENT_MODEL": "gpt-4",
        "OPTIMUS_API_KEY": "explicit-key",  # pragma: allowlist secret - synthetic test fixture
    }

    result = local_infra.apply_local_defaults(input_environ, config_root=tmp_path)

    assert result == input_environ
    assert result is not input_environ


def test_apply_local_defaults_uses_passed_in_resolved_shared_secret(tmp_path) -> None:
    result = local_infra.apply_local_defaults({}, config_root=tmp_path, resolved_shared_secret="resolved-secret")

    assert result["OPTIMUS_API_KEY"] == "resolved-secret"  # pragma: allowlist secret - synthetic test fixture


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


# --- ensure_local_redis: an unreachable port ---


def test_ensure_local_redis_noops_for_non_loopback_host(monkeypatch) -> None:
    docker_calls: list[object] = []
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: False)
    monkeypatch.setattr(local_infra.subprocess, "run", lambda *a, **k: docker_calls.append((a, k)))

    local_infra.ensure_local_redis("redis://203.0.113.5:6379/0")

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
    confirmed: list[object] = []
    monkeypatch.setattr(local_infra, "_confirm_redis_identity", lambda *a, **k: confirmed.append((a, k)))
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

    assert confirmed == [(("127.0.0.1", 6379), {"tls": False})]  # #480: what answers after the start proves itself too

    assert run_calls == [
        ["docker", "run", "-d", "--name", "optimus-redis", "-p", "127.0.0.1:6379:6379", "redis:8"],
    ]
    assert "--rm" not in run_calls[0]


def test_ensure_local_redis_starts_existing_container(monkeypatch) -> None:
    run_calls: list[list[str]] = []
    confirmed: list[object] = []
    monkeypatch.setattr(local_infra, "_confirm_redis_identity", lambda *a, **k: confirmed.append((a, k)))
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

    assert confirmed == [(("127.0.0.1", 6379), {"tls": False})]  # #480: what answers after the start proves itself too

    assert run_calls == [["docker", "start", "optimus-redis"]]


# --- #480: a listening Redis must prove it is this setup's ---


def _fake_docker_ps_owner(name: str, image: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        ["docker", "ps"],
        0,
        stdout=f"{name}\t{image}\n",
        stderr="",
    )


def _assert_no_destructive_docker_args(run_calls: list[list[str]]) -> None:
    destructive = {"stop", "rm", "rename", "update", "kill"}
    for cmd in run_calls:
        assert destructive.isdisjoint(cmd), cmd


_OURS = "a" * 40
_FOREIGN = "f" * 40
_URLS = pytest.mark.parametrize("url", ["redis://127.0.0.1:6379/0", "redis://127.0.0.1:6380/0"], ids=["default", "custom"])
_EXEC = ["docker", "exec", "optimus-redis", "redis-cli", "INFO", "server"]


def _listening(monkeypatch, listener_run_id: str | None, *, container_run_id: str | None, docker: str | None = "docker",
               reachable: object = True) -> list[list[str]]:
    """A port held by a Redis that passes ordinary preflight and reports ``listener_run_id`` (None: something that is not
    a Redis answering INFO), and an optimus-redis container whose own server reports ``container_run_id`` (None: no such
    container running). Returns the recorded Docker calls."""
    run_calls: list[list[str]] = []
    if isinstance(reachable, bool):
        monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: reachable)
    else:
        monkeypatch.setattr(local_infra, "_tcp_reachable", reachable)
    monkeypatch.setattr(local_infra.shutil, "which", lambda _name: docker)
    monkeypatch.setattr(local_infra, "_redis_run_id", lambda *_a, **_k: listener_run_id)

    def fake_run(args, **_k):
        run_calls.append(list(args))
        if args == _EXEC:
            if container_run_id is None:
                return subprocess.CompletedProcess(args, 1, "", "Error response from daemon: No such container: optimus-redis")
            return subprocess.CompletedProcess(args, 0, f"# Server\r\nredis_version:8.0.2\r\nrun_id:{container_run_id}\r\n", "")
        if args[:2] == ["docker", "start"]:
            return subprocess.CompletedProcess(args, 1, "", "Bind for 127.0.0.1:6379 failed: port is already allocated")
        raise AssertionError(f"unexpected docker call: {args}")

    monkeypatch.setattr(local_infra.subprocess, "run", fake_run)
    return run_calls


@_URLS
@pytest.mark.parametrize("confirm", [local_infra.ensure_local_redis, local_infra.confirm_local_redis], ids=["start", "no-auto-start"])
def test_a_listening_redis_is_reused_when_it_is_the_optimus_redis_container_itself(monkeypatch, url, confirm) -> None:
    run_calls = _listening(monkeypatch, _OURS, container_run_id=_OURS)

    confirm(url)

    assert run_calls == [_EXEC]


@_URLS
@pytest.mark.parametrize("confirm", [local_infra.ensure_local_redis, local_infra.confirm_local_redis], ids=["start", "no-auto-start"])
def test_a_foreign_redis_is_refused_and_left_running(monkeypatch, url, confirm) -> None:
    run_calls = _listening(monkeypatch, _FOREIGN, container_run_id=_OURS)

    with pytest.raises(local_infra.LocalInfrastructureError) as exc_info:
        confirm(url)

    assert exc_info.value.code == "REDIS_IDENTITY_UNCONFIRMED"
    assert f"127.0.0.1:{urlparse(url).port}" in exc_info.value.user_message
    assert "will not stop or change it" in exc_info.value.user_message
    assert run_calls == [_EXEC]


@_URLS
@pytest.mark.parametrize("docker", ["docker", None], ids=["no-container", "no-docker"])
def test_a_listener_with_no_container_to_match_is_refused(monkeypatch, url, docker) -> None:
    """Plan 11.6 accepted a reachable Redis that no Docker container owned as native; nothing proved it was this setup's."""
    run_calls = _listening(monkeypatch, _FOREIGN, container_run_id=None, docker=docker)

    with pytest.raises(local_infra.LocalInfrastructureError) as exc_info:
        local_infra.ensure_local_redis(url)

    assert exc_info.value.code == "REDIS_IDENTITY_UNCONFIRMED"
    assert run_calls == ([] if docker is None else [_EXEC])


def test_a_listener_that_is_not_a_redis_answering_info_is_refused(monkeypatch) -> None:
    run_calls = _listening(monkeypatch, None, container_run_id=_OURS)

    with pytest.raises(local_infra.LocalInfrastructureError) as exc_info:
        local_infra.confirm_local_redis("redis://127.0.0.1:6379/0")

    assert exc_info.value.code == "REDIS_IDENTITY_UNCONFIRMED"
    assert run_calls == []


def test_a_foreign_redis_that_takes_the_port_while_optimus_redis_starts_is_refused(monkeypatch) -> None:
    """Codex #480 review item 4: the port was free, the container's start failed, and a foreign Redis now answers."""
    monkeypatch.setattr(local_infra, "_docker_daemon_reachable", lambda _docker: True)
    monkeypatch.setattr(local_infra, "_container_exists", lambda *_a, **_k: True)
    monkeypatch.setattr(local_infra.time, "sleep", lambda _seconds: None)
    run_calls = _listening(monkeypatch, _FOREIGN, container_run_id=None, reachable=MagicMock(side_effect=[False, True]))

    with pytest.raises(local_infra.LocalInfrastructureError) as exc_info:
        local_infra.ensure_local_redis("redis://127.0.0.1:6379/0")

    assert exc_info.value.code == "REDIS_IDENTITY_UNCONFIRMED"
    assert run_calls == [["docker", "start", "optimus-redis"], _EXEC]


@pytest.mark.parametrize("url", ["redis://127.0.0.1:6379/0", "redis://203.0.113.5:6379/0"], ids=["unreachable", "remote"])
def test_confirming_without_a_local_listener_leaves_redis_to_preflight(monkeypatch, url) -> None:
    run_calls = _listening(monkeypatch, _FOREIGN, container_run_id=None, reachable=False)

    local_infra.confirm_local_redis(url)

    assert run_calls == []


_RUNTIME_URLS = ["redis://127.0.0.1/0?port=6380", "redis://%31%32%37.0.0.1:6380/0", "redis://127.0.0.2:6380/0", "redis://[::1]:6380/0", "redis://localhost:6380/0"]


@pytest.mark.parametrize("url", _RUNTIME_URLS, ids=["query-port", "encoded-host", "loopback-range", "ipv6", "localhost"])
@pytest.mark.parametrize("confirm", [local_infra.ensure_local_redis, local_infra.confirm_local_redis], ids=["start", "no-auto-start"])
def test_the_endpoint_checked_is_the_one_the_runtime_connects_to(monkeypatch, url, confirm) -> None:
    """Codex #480 review round 2: optimus-redis on 6379, a foreign Redis on 6380, and a URL the runtime reads as 6380."""
    run_calls = _listening(monkeypatch, None, container_run_id=_OURS)
    monkeypatch.setattr(local_infra, "_redis_run_id", lambda _host, port, **_k: _OURS if port == 6379 else _FOREIGN)

    with pytest.raises(local_infra.LocalInfrastructureError) as exc_info:
        confirm(url)

    assert ":6380" in exc_info.value.user_message
    _assert_no_destructive_docker_args(run_calls)


@pytest.mark.parametrize("url", [*_RUNTIME_URLS, "redis://127.0.0.1:6379/0", "rediss://localhost:6390/0", "redis:///0"])
def test_the_endpoint_is_read_as_the_runtime_pool_reads_it(url) -> None:
    from redis.asyncio import ConnectionPool

    options = ConnectionPool.from_url(url).connection_kwargs
    assert local_infra._redis_endpoint(url)[:2] == (options.get("host", "localhost"), int(options.get("port", 6379)))  # noqa: SLF001


class _Listener:
    """A real loopback socket that accepts and answers every request with ``reply`` (None: never answers)."""

    def __init__(self, reply: bytes | None) -> None:
        self._server = socket.create_server(("127.0.0.1", 0))
        self.port = self._server.getsockname()[1]
        self._reply = reply
        self._open: list[socket.socket] = []
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while True:
            try:
                connection, _ = self._server.accept()
            except OSError:
                return
            self._open.append(connection)
            if self._reply is not None:
                with contextlib.suppress(OSError):
                    connection.recv(4096)
                    connection.sendall(self._reply)

    def close(self) -> None:
        for connection in self._open:
            connection.close()
        self._server.close()


@pytest.mark.parametrize("reply", [b":1\r\n", b"$-1\r\n", b"-ERR unknown command\r\n", b"+OK\r\n"], ids=["integer", "null", "error", "status"])
def test_a_malformed_info_reply_is_refused_as_unconfirmed(monkeypatch, reply) -> None:
    """Codex #480 review item 6: the real client against a real socket; a reply redis-py cannot read as INFO proves nothing."""
    listener = _Listener(reply)
    monkeypatch.setattr(local_infra, "_REDIS_PROBE_SECONDS", 0.3)
    monkeypatch.setattr(local_infra.shutil, "which", lambda _name: None)
    try:
        with pytest.raises(local_infra.LocalInfrastructureError) as exc_info:
            local_infra.confirm_local_redis(f"redis://127.0.0.1:{listener.port}/0")
    finally:
        listener.close()
    assert exc_info.value.code == "REDIS_IDENTITY_UNCONFIRMED"


def test_a_silent_listener_is_refused_within_the_probe_bound_whatever_the_url_asks(monkeypatch) -> None:
    """Codex #480 review item 5: URL options cannot lengthen or retry the identity probe."""
    listener = _Listener(None)
    monkeypatch.setattr(local_infra, "_REDIS_PROBE_SECONDS", 0.3)
    monkeypatch.setattr(local_infra.shutil, "which", lambda _name: None)
    url = f"redis://127.0.0.1:{listener.port}/0?socket_timeout=60&socket_connect_timeout=60&retry_on_timeout=true"
    started = time.monotonic()
    try:
        with pytest.raises(local_infra.LocalInfrastructureError):
            local_infra.ensure_local_redis(url)
    finally:
        listener.close()
    assert time.monotonic() - started < 2.0


# --- ensure_local_gateway: Task 5 signature (pre-resolved credentials,
# explicit bind CLI args + signed manifest, no OPTIMUS_LOCAL_GATEWAY_BIND_HOST/PORT) ---


def _ensure_gateway_kwargs(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "gateway_url": "http://127.0.0.1:8765",
        "provider_credentials": _resolution(
            ProviderSecrets(provider="openrouter", model_provider_api_key="sk-or-test")  # pragma: allowlist secret - synthetic test fixture
        ),
        "shared_secret": "shared-secret-value",  # pragma: allowlist secret - synthetic test fixture
        "workspace_digest": "a" * 64,
        "security_snapshot_digest": "b" * 64,
        "manifest_hmac_key": _HMAC_KEY,
        "policy_version": "P9.96-v1",
    }
    defaults.update(overrides)
    return defaults


@pytest.mark.parametrize("stop_error", [False, True])
def test_interrupted_post_popen_readiness_retains_failure_and_stops_owned_child(tmp_path, monkeypatch, stop_error):
    calls = []
    primary = KeyboardInterrupt()
    cause = ValueError("original cause")
    primary.__cause__ = cause

    class Process:
        pid = 4321
        returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            calls.append("terminate")
            self.returncode = 0

        def wait(self, *, timeout):
            calls.append(("wait", timeout))
            if stop_error:
                raise OSError("stop observation failed")
            return self.returncode

    process = Process()
    monkeypatch.setattr(local_infra.subprocess, "Popen", lambda *_a, **_k: process)
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: False)

    def interrupted(_seconds):
        raise primary

    monkeypatch.setattr(local_infra.time, "sleep", interrupted)
    with pytest.raises(KeyboardInterrupt) as raised:
        local_infra.ensure_local_gateway(**_ensure_gateway_kwargs(), runtime_root=tmp_path / ".optimus")
    assert raised.value is primary
    assert primary.__cause__ is cause
    assert calls == ["terminate", ("wait", 5)]
    if stop_error:
        assert any("gateway" in note for note in primary.__notes__)


def test_gateway_stop_interrupted_observer_rejoins_one_physical_stop(monkeypatch):
    import threading

    entered, release = threading.Event(), threading.Event()
    calls = []

    class Process:
        returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            calls.append("terminate")

        def wait(self, *, timeout):
            calls.append(("wait", timeout))
            entered.set()
            assert release.wait(5)
            self.returncode = 0
            return 0

    handle = local_infra.LocalGatewayProcess(Process(), None)
    assert hasattr(handle, "stop_pending"), "an interrupted observer must retain the same physical stop"
    real_join = threading.Thread.join
    interrupted = False

    def join(thread, timeout=None):
        nonlocal interrupted
        if thread.name == "optimus-gateway-stop" and not interrupted:
            interrupted = True
            raise KeyboardInterrupt
        return real_join(thread, timeout)

    monkeypatch.setattr(threading.Thread, "join", join)
    try:
        with pytest.raises(KeyboardInterrupt):
            handle.stop()
        assert entered.wait(2)
        assert handle.stop_pending
        release.set()
        handle.stop()
        handle.stop()
        assert calls == ["terminate", ("wait", 5)]
        assert not handle.stop_pending
    finally:
        release.set()
        handle.stop()


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
    assert gateway_env["OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET"] == "shared-secret-value"  # pragma: allowlist secret - synthetic test fixture
    assert gateway_env["OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY"] == "sk-or-test"  # pragma: allowlist secret - synthetic test fixture
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
                    model_provider_api_key="sk-test",  # pragma: allowlist secret - synthetic test fixture
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
                    model_provider_api_key="sk-or-test",  # pragma: allowlist secret - synthetic test fixture
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
    """Plan 11.2 Task 6 pre-work: tool vars from config_root/.env.gateway reach the child, through the launch gate's
    validated tool configuration; ensure_local_gateway itself never reads the file (#680)."""
    from optimus.acp.launch_gate import require_gateway_tool_urls

    reachable_calls = {"n": 0}

    def fake_tcp_reachable(host, port, *, timeout=1.0):
        reachable_calls["n"] += 1
        return reachable_calls["n"] > 1

    monkeypatch.setattr(local_infra, "_tcp_reachable", fake_tcp_reachable)
    monkeypatch.setattr(local_infra.time, "sleep", lambda _seconds: None)

    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / ".env.gateway").write_text(
        "TAVILY_API_KEY=tvly-from-config\n"  # pragma: allowlist secret - synthetic test fixture
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
        tool_environ=require_gateway_tool_urls(config_root, {}),
        config_root=config_root,
    )

    child_env = captured["env"]
    assert child_env["TAVILY_API_KEY"] == "tvly-from-config"  # pragma: allowlist secret - synthetic test fixture
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


# --- Plan 11.6 Task 3, then #481: local Phoenix lifecycle and attach identity ---


class _Docker:
    """A fake Docker that keeps optimus-phoenix's state, as `docker inspect` would report it. Starting the container fails,
    as Docker's exclusive bind does, while something else already listens on its port."""

    def __init__(self, monkeypatch, *, exists: bool, running: bool = False, image: str = "arizephoenix/phoenix:latest",
                 owners: list[tuple[str, str]] | None = None, port_taken: object = lambda: False,
                 engine: str = "npipe:////./pipe/dockerDesktopLinuxEngine") -> None:
        self.exists, self.running, self.image, self.port_taken, self.engine = exists, running, image, port_taken, engine
        self.bindings = [{"HostIp": "127.0.0.1", "HostPort": str(local_infra._PHOENIX_PORT)}]  # noqa: SLF001
        self.calls: list[list[str]] = []
        monkeypatch.setattr(local_infra.shutil, "which", lambda _name: "docker")
        monkeypatch.setattr(local_infra, "_docker_daemon_reachable", lambda _docker: True)
        monkeypatch.setattr(local_infra, "_docker_published_port_owners", lambda *_a, **_k: list(owners or []))
        monkeypatch.setattr(local_infra.time, "sleep", lambda _seconds: None)
        monkeypatch.setattr(local_infra.subprocess, "run", self.run)

    def run(self, args, **_k):
        args = list(args)
        if args[:3] == ["docker", "context", "inspect"]:
            self.calls.append(args)
            return subprocess.CompletedProcess(args, 0, f"{self.engine}\n", "")
        # Codex #481 review round 2: every other command is pinned to the engine just checked, so a context switched
        # meanwhile is not followed. An unpinned one fails the test.
        assert args[1:3] == ["--host", self.engine], f"unpinned docker call: {args}"
        args = [args[0], *args[3:]]
        self.calls.append(args)
        if args[:2] == ["docker", "ps"]:  # _container_exists
            return subprocess.CompletedProcess(args, 0, "optimus-phoenix\n" if self.exists else "", "")
        if args[:3] == ["docker", "inspect", "--format"]:  # _docker_container_image
            return subprocess.CompletedProcess(args, 0 if self.exists else 1, f"{self.image}\n" if self.exists else "", "")
        if args[:4] == ["docker", "inspect", "--type", "container"]:
            if not self.exists:
                return subprocess.CompletedProcess(args, 1, "", "Error: No such container: optimus-phoenix")
            ports = {f"{local_infra._PHOENIX_PORT}/tcp": self.bindings} if self.running else {}  # noqa: SLF001
            view = {"State": {"Running": self.running}, "Config": {"Image": self.image}, "NetworkSettings": {"Ports": ports}}
            return subprocess.CompletedProcess(args, 0, json.dumps([view]), "")
        if args[:2] in (["docker", "start"], ["docker", "run"]):
            self.exists = True
            self.running = not self.port_taken()
            return subprocess.CompletedProcess(args, 0 if self.running else 1, "", "" if self.running else "port is already allocated")
        raise AssertionError(f"unexpected docker call: {args}")


class _HealthyListener:
    """A real loopback HTTP server that passes Phoenix's health check: GET /healthz answers 200."""

    def __init__(self) -> None:
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - the standard library's name
                self.send_response(200 if self.path == "/healthz" else 404)
                self.end_headers()

            def log_message(self, *_args: object) -> None:
                return None

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture
def phoenix_port(monkeypatch) -> Iterator[_HealthyListener]:
    """Phoenix's fixed port, moved to a free one held by a foreign endpoint that passes the health checks. Tests that
    want the port free close it first."""
    listener = _HealthyListener()
    base = f"http://127.0.0.1:{listener.port}"
    monkeypatch.setattr(local_infra, "_PHOENIX_PORT", listener.port)
    monkeypatch.setattr(local_infra, "LOCAL_PHOENIX_BASE_URL", base)
    monkeypatch.setattr(local_infra, "_PHOENIX_HEALTHZ_URL", f"{base}/healthz")
    monkeypatch.setattr(local_infra, "LOCAL_PHOENIX_OTLP_ENDPOINT", f"{base}/v1/traces")
    yield listener
    listener.close()


def _ours_answers(monkeypatch) -> None:
    """The port is free until Optimus starts its container, which then answers the health check."""
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: False)
    monkeypatch.setattr(local_infra, "_phoenix_health_ready", lambda _url: True)


def test_ensure_local_phoenix_creates_named_container_when_missing(monkeypatch) -> None:
    docker = _Docker(monkeypatch, exists=False)
    _ours_answers(monkeypatch)

    endpoint = local_infra.ensure_local_phoenix()

    assert endpoint == local_infra.LOCAL_PHOENIX_OTLP_ENDPOINT == "http://127.0.0.1:6006/v1/traces"
    assert [call for call in docker.calls if call[1] == "run"] == [
        ["docker", "run", "-d", "--name", "optimus-phoenix", "-p", "127.0.0.1:6006:6006", "arizephoenix/phoenix:latest"],
    ]
    _assert_no_destructive_docker_args(docker.calls)


def test_ensure_local_phoenix_starts_existing_matching_container(monkeypatch) -> None:
    docker = _Docker(monkeypatch, exists=True)
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: False)
    health = iter([False, True])
    monkeypatch.setattr(local_infra, "_phoenix_health_ready", lambda _url: next(health))

    assert local_infra.ensure_local_phoenix() == local_infra.LOCAL_PHOENIX_OTLP_ENDPOINT
    assert [call for call in docker.calls if call[1] in ("start", "run")] == [["docker", "start", "optimus-phoenix"]]
    _assert_no_destructive_docker_args(docker.calls)


def test_ensure_local_phoenix_reuses_its_running_container(monkeypatch) -> None:
    docker = _Docker(monkeypatch, exists=True, running=True)
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: True)  # it is the container that answers
    monkeypatch.setattr(local_infra, "_phoenix_health_ready", lambda _url: True)

    assert local_infra.ensure_local_phoenix() == local_infra.LOCAL_PHOENIX_OTLP_ENDPOINT
    assert [call for call in docker.calls if call[1] in ("start", "run")] == []


@pytest.mark.parametrize("exists", [True, False], ids=["stopped-container", "no-container"])
def test_a_foreign_endpoint_that_passes_the_health_checks_is_refused_and_left_running(monkeypatch, phoenix_port, exists) -> None:
    """#481: before, a healthy foreign listener on the port skipped the start, or outlived a failed one, and got the traces."""
    docker = _Docker(monkeypatch, exists=exists, port_taken=lambda: True)

    with pytest.raises(local_infra.LocalInfrastructureError) as exc_info:
        local_infra.ensure_local_phoenix()

    assert exc_info.value.code == "PHOENIX_IDENTITY_UNCONFIRMED"
    assert f"127.0.0.1:{phoenix_port.port}" in exc_info.value.user_message
    assert [call for call in docker.calls if call[1] in ("start", "run")] == []
    _assert_no_destructive_docker_args(docker.calls)
    with urllib.request.urlopen(f"http://127.0.0.1:{phoenix_port.port}/healthz", timeout=2) as response:
        assert response.status == 200  # still serving


def test_a_foreign_endpoint_that_takes_the_port_while_the_container_starts_is_refused(monkeypatch, phoenix_port) -> None:
    """Codex #481 review item 2: the port is free and unhealthy at the check, the start is attempted and fails because a
    foreign listener bound first, and that listener then passes the health check."""
    taken = iter([False])
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: next(taken, True))
    real_health, probes = local_infra._phoenix_health_ready, []  # noqa: SLF001

    def health(url: str) -> bool:
        probes.append(url)
        return len(probes) > 1 and real_health(url)  # the first probe, before the start, finds nothing healthy

    monkeypatch.setattr(local_infra, "_phoenix_health_ready", health)
    docker = _Docker(monkeypatch, exists=True, port_taken=lambda: True)

    with pytest.raises(local_infra.LocalInfrastructureError) as exc_info:
        local_infra.ensure_local_phoenix()

    assert exc_info.value.code == "PHOENIX_IDENTITY_UNCONFIRMED"
    assert "is not running" in exc_info.value.user_message
    assert [call for call in docker.calls if call[1] in ("start", "run")] == [["docker", "start", "optimus-phoenix"]]
    _assert_no_destructive_docker_args(docker.calls)
    with urllib.request.urlopen(f"http://127.0.0.1:{phoenix_port.port}/healthz", timeout=2) as response:
        assert response.status == 200  # still serving


def test_a_remote_docker_engine_cannot_vouch_for_this_machine_s_port(monkeypatch, phoenix_port) -> None:
    """Codex #481 review item 1: a remote engine reports a matching optimus-phoenix while a foreign local endpoint is healthy."""
    docker = _Docker(monkeypatch, exists=True, running=True, engine="tcp://10.0.0.9:2375")

    with pytest.raises(local_infra.LocalInfrastructureError) as exc_info:
        local_infra.ensure_local_phoenix()

    assert exc_info.value.code == "PHOENIX_IDENTITY_UNCONFIRMED"
    assert "not on this machine" in exc_info.value.user_message
    assert [call for call in docker.calls if call[1] in ("start", "run")] == []


@pytest.mark.parametrize("engine", ["npipe:////remote-server/pipe/docker_engine", "npipe://server/pipe/docker_engine",
                                    "ssh://me@build-box", "tcp://127.0.0.1:2375"])
def test_only_a_local_pipe_or_socket_counts_as_this_machine_s_engine(monkeypatch, engine) -> None:
    _Docker(monkeypatch, exists=True, running=True, engine=engine)
    assert local_infra._local_docker_endpoint("docker") is None  # noqa: SLF001


@pytest.mark.parametrize("engine", ["npipe:////./pipe/dockerDesktopLinuxEngine", "unix:///var/run/docker.sock"])
def test_a_local_engine_is_pinned_for_every_later_command(monkeypatch, engine) -> None:
    """A context switched after the check is not followed: the fake answers only commands carrying the checked engine."""
    docker = _Docker(monkeypatch, exists=True, running=True, engine=engine)
    monkeypatch.setattr(local_infra, "_tcp_reachable", lambda *_a, **_k: True)
    monkeypatch.setattr(local_infra, "_phoenix_health_ready", lambda _url: True)

    assert local_infra.ensure_local_phoenix() == local_infra.LOCAL_PHOENIX_OTLP_ENDPOINT
    assert len(docker.calls) > 1  # the checked engine answered every one of them


@pytest.mark.parametrize(
    ("bindings", "image"),
    [
        ([{"HostIp": "0.0.0.0", "HostPort": "{port}"}], "arizephoenix/phoenix:latest"),
        ([{"HostIp": "127.0.0.1", "HostPort": "16006"}], "arizephoenix/phoenix:latest"),
        ([], "arizephoenix/phoenix:latest"),
        ([{"HostIp": "127.0.0.1", "HostPort": "{port}"}], "someone/else:1"),
    ],
    ids=["all-interfaces", "other-port", "unpublished", "other-image"],
)
def test_a_running_container_that_does_not_hold_the_endpoint_is_refused(monkeypatch, phoenix_port, bindings, image) -> None:
    """A healthy answer counts only while Docker holds exactly 127.0.0.1:<port> for optimus-phoenix running its image."""
    docker = _Docker(monkeypatch, exists=True, running=True, image="arizephoenix/phoenix:latest")
    docker.bindings = [{**binding, "HostPort": binding["HostPort"].format(port=phoenix_port.port)} for binding in bindings]
    docker.image = image
    monkeypatch.setattr(local_infra, "_docker_container_image", lambda *_a, **_k: "arizephoenix/phoenix:latest")

    with pytest.raises(local_infra.LocalInfrastructureError) as exc_info:
        local_infra.ensure_local_phoenix()

    assert exc_info.value.code == "PHOENIX_IDENTITY_UNCONFIRMED"
    _assert_no_destructive_docker_args(docker.calls)


def test_ensure_local_phoenix_raises_on_wrong_port_owner(monkeypatch) -> None:
    docker = _Docker(monkeypatch, exists=False, owners=[("other-phoenix", "arizephoenix/phoenix:latest")])

    with pytest.raises(local_infra.LocalInfrastructureError) as exc_info:
        local_infra.ensure_local_phoenix()

    assert exc_info.value.code == "PHOENIX_PORT_CONFLICT"
    assert "6006" in exc_info.value.user_message
    assert "other-phoenix" in exc_info.value.user_message
    assert docker.calls == [["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"]]  # read-only


def test_ensure_local_phoenix_raises_on_wrong_image_for_named_container(monkeypatch) -> None:
    docker = _Docker(monkeypatch, exists=True, owners=[("optimus-phoenix", "wrong/image:tag")])

    with pytest.raises(local_infra.LocalInfrastructureError) as exc_info:
        local_infra.ensure_local_phoenix()

    assert exc_info.value.code == "PHOENIX_IMAGE_CONFLICT"
    assert "wrong/image:tag" in exc_info.value.user_message
    assert docker.calls == [["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"]]  # read-only


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


def test_phoenix_approved_scheme_rejects_before_the_opener(monkeypatch):
    def unexpected_open(*args, **kwargs):
        pytest.fail("the Phoenix opener must not receive a rejected URL")

    monkeypatch.setattr(url_schemes, "_http_opener", lambda: MagicMock(open=unexpected_open))
    assert local_infra._phoenix_health_ready("policy-test://fixture.invalid") is False  # noqa: SLF001
