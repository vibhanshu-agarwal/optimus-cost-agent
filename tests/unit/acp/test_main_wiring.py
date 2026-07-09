from __future__ import annotations

import pytest

from optimus.acp import __main__ as acp_main


def test_setup_flag_calls_wizard_and_short_circuits(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(acp_main, "run_setup_wizard", lambda **kwargs: calls.append(kwargs) or 0)

    def _must_not_run(*_a, **_k):
        raise AssertionError("must not run during --setup short-circuit")

    monkeypatch.setattr(acp_main, "apply_local_defaults", _must_not_run)
    monkeypatch.setattr(acp_main, "build_configured_server", _must_not_run)

    exit_code = acp_main.main(["--setup"])

    assert exit_code == 0
    assert len(calls) == 1


def _patch_common(monkeypatch, *, gateway_url: str = "https://gateway.optimus.ai", server_factory=None):
    monkeypatch.setattr(
        acp_main,
        "apply_local_defaults",
        lambda environ, *, project_root: {
            "OPTIMUS_GATEWAY_URL": gateway_url,
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
        },
    )

    if server_factory is None:

        class FakeServer:
            def serve_ndjson(self, *_a, **_k):
                async def _noop():
                    return None

                return _noop()

        def server_factory(**_k):
            return FakeServer()

    monkeypatch.setattr(acp_main, "build_configured_server", server_factory)
    monkeypatch.setattr(acp_main, "StdioNdjsonLineReader", lambda *_a, **_k: object())
    monkeypatch.setattr(acp_main, "StdioNdjsonLineWriter", lambda *_a, **_k: object())


def test_no_auto_start_skips_redis_and_gateway_in_real_serve_path(monkeypatch, tmp_path) -> None:
    redis_calls: list[tuple[object, object]] = []
    gateway_calls: list[dict[str, object]] = []
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: redis_calls.append((a, k)))
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: gateway_calls.append(k) or None)
    _patch_common(monkeypatch)

    exit_code = acp_main.main(["--no-auto-start", "--workspace-root", str(tmp_path)])

    assert exit_code == 0
    assert redis_calls == []
    assert gateway_calls == []


def test_check_config_never_calls_ensure_local_gateway(monkeypatch, tmp_path) -> None:
    gateway_calls: list[dict[str, object]] = []
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: gateway_calls.append(k) or None)
    monkeypatch.setattr(acp_main, "run_preflight", lambda environ, **k: None)
    _patch_common(monkeypatch)

    exit_code = acp_main.main(["--check-config", "--workspace-root", str(tmp_path)])

    assert exit_code == 0
    assert gateway_calls == []


def test_no_auto_start_skips_redis_in_check_config_branch(monkeypatch, tmp_path) -> None:
    redis_calls: list[tuple[object, object]] = []
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: redis_calls.append((a, k)))
    monkeypatch.setattr(acp_main, "run_preflight", lambda environ, **k: None)
    _patch_common(monkeypatch)

    exit_code = acp_main.main(["--check-config", "--no-auto-start", "--workspace-root", str(tmp_path)])

    assert exit_code == 0
    assert redis_calls == []


def test_check_config_passes_sanitized_environ_to_preflight(monkeypatch, tmp_path) -> None:
    preflight_environ_seen: dict[str, str] = {}

    def fake_preflight(environ, **kwargs):
        preflight_environ_seen.update(environ)

    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "run_preflight", fake_preflight)
    monkeypatch.setattr(
        acp_main,
        "apply_local_defaults",
        lambda environ, *, project_root: {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "shared-secret",
            "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
            "ANTHROPIC_API_KEY": "sk-ant-real",
        },
    )

    exit_code = acp_main.main(["--check-config", "--workspace-root", str(tmp_path)])

    assert exit_code == 0
    assert preflight_environ_seen["OPTIMUS_API_KEY"] == "shared-secret"
    assert "ANTHROPIC_API_KEY" not in preflight_environ_seen


def test_gateway_process_stopped_only_if_it_was_started(monkeypatch, tmp_path) -> None:
    stop_calls: list[str] = []

    class FakeGatewayProcess:
        def stop(self) -> None:
            stop_calls.append("stopped")

    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: FakeGatewayProcess())
    _patch_common(monkeypatch, gateway_url="http://127.0.0.1:8765")

    exit_code = acp_main.main(["--workspace-root", str(tmp_path)])

    assert exit_code == 0
    assert stop_calls == ["stopped"]


def test_gateway_process_not_stopped_when_none_was_started(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: None)
    _patch_common(monkeypatch, gateway_url="http://127.0.0.1:8765")

    exit_code = acp_main.main(["--workspace-root", str(tmp_path)])

    assert exit_code == 0


def test_gateway_process_stopped_when_serve_raises(monkeypatch, tmp_path) -> None:
    stop_calls: list[str] = []

    class FakeGatewayProcess:
        def stop(self) -> None:
            stop_calls.append("stopped")

    class FailingServer:
        def serve_ndjson(self, *_a, **_k):
            async def _raise():
                raise RuntimeError("boom")

            return _raise()

    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: FakeGatewayProcess())
    _patch_common(monkeypatch, gateway_url="http://127.0.0.1:8765", server_factory=lambda **k: FailingServer())

    with pytest.raises(RuntimeError):
        acp_main.main(["--workspace-root", str(tmp_path)])

    assert stop_calls == ["stopped"]


def test_gateway_process_stopped_when_build_configured_server_raises_unexpectedly(monkeypatch, tmp_path) -> None:
    stop_calls: list[str] = []

    class FakeGatewayProcess:
        def stop(self) -> None:
            stop_calls.append("stopped")

    def raising_build_configured_server(**_k):
        raise ValueError("unexpected settings construction failure")

    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: FakeGatewayProcess())
    _patch_common(
        monkeypatch,
        gateway_url="http://127.0.0.1:8765",
        server_factory=raising_build_configured_server,
    )

    with pytest.raises(ValueError):
        acp_main.main(["--workspace-root", str(tmp_path)])

    assert stop_calls == ["stopped"]


def test_real_serve_path_calls_helpers_in_expected_order(monkeypatch, tmp_path) -> None:
    call_order: list[str] = []

    monkeypatch.setattr(
        acp_main,
        "apply_local_defaults",
        lambda environ, *, project_root: call_order.append("apply_local_defaults")
        or {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
        },
    )
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: call_order.append("ensure_local_redis"))
    monkeypatch.setattr(
        acp_main,
        "ensure_local_gateway",
        lambda **k: call_order.append("ensure_local_gateway") or None,
    )

    class FakeServer:
        def serve_ndjson(self, *_a, **_k):
            async def _noop():
                return None

            return _noop()

    def fake_build_configured_server(**_k):
        call_order.append("build_configured_server")
        return FakeServer()

    monkeypatch.setattr(acp_main, "build_configured_server", fake_build_configured_server)
    monkeypatch.setattr(acp_main, "StdioNdjsonLineReader", lambda *_a, **_k: object())
    monkeypatch.setattr(acp_main, "StdioNdjsonLineWriter", lambda *_a, **_k: object())

    exit_code = acp_main.main(["--workspace-root", str(tmp_path)])

    assert exit_code == 0
    assert call_order == [
        "apply_local_defaults",
        "ensure_local_redis",
        "ensure_local_gateway",
        "build_configured_server",
    ]


def test_anthropic_provider_key_reaches_gateway_child_but_not_agent_settings(monkeypatch, tmp_path) -> None:
    gateway_environ_seen: dict[str, str] = {}
    agent_environ_seen: dict[str, str] = {}

    def fake_ensure_local_gateway(*, environ, project_root, log):
        gateway_environ_seen.update(environ)
        return None

    def fake_build_configured_server(*, environ, workspace_root, model):
        agent_environ_seen.update(environ)

        class FakeServer:
            def serve_ndjson(self, *_a, **_k):
                async def _noop():
                    return None

                return _noop()

        return FakeServer()

    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "ensure_local_gateway", fake_ensure_local_gateway)
    monkeypatch.setattr(acp_main, "build_configured_server", fake_build_configured_server)
    monkeypatch.setattr(acp_main, "StdioNdjsonLineReader", lambda *_a, **_k: object())
    monkeypatch.setattr(acp_main, "StdioNdjsonLineWriter", lambda *_a, **_k: object())
    monkeypatch.setattr(
        acp_main,
        "apply_local_defaults",
        lambda environ, *, project_root: {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "shared-secret",
            "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER": "anthropic",
            "ANTHROPIC_API_KEY": "sk-ant-real",
        },
    )

    exit_code = acp_main.main(["--workspace-root", str(tmp_path)])

    assert exit_code == 0
    assert gateway_environ_seen["ANTHROPIC_API_KEY"] == "sk-ant-real"
    assert "ANTHROPIC_API_KEY" not in agent_environ_seen


def test_openrouter_provider_key_reaches_gateway_child_but_not_agent_settings(monkeypatch, tmp_path) -> None:
    gateway_environ_seen: dict[str, str] = {}
    agent_environ_seen: dict[str, str] = {}

    def fake_ensure_local_gateway(*, environ, project_root, log):
        gateway_environ_seen.update(environ)
        return None

    def fake_build_configured_server(*, environ, workspace_root, model):
        agent_environ_seen.update(environ)

        class FakeServer:
            def serve_ndjson(self, *_a, **_k):
                async def _noop():
                    return None

                return _noop()

        return FakeServer()

    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "ensure_local_gateway", fake_ensure_local_gateway)
    monkeypatch.setattr(acp_main, "build_configured_server", fake_build_configured_server)
    monkeypatch.setattr(acp_main, "StdioNdjsonLineReader", lambda *_a, **_k: object())
    monkeypatch.setattr(acp_main, "StdioNdjsonLineWriter", lambda *_a, **_k: object())
    monkeypatch.setattr(
        acp_main,
        "apply_local_defaults",
        lambda environ, *, project_root: {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "shared-secret",
            "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER": "openrouter",
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "sk-or-real",
            "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "shared-secret",
        },
    )

    exit_code = acp_main.main(["--workspace-root", str(tmp_path)])

    assert exit_code == 0
    assert gateway_environ_seen["OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY"] == "sk-or-real"
    assert "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY" not in agent_environ_seen
    assert "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET" not in agent_environ_seen
