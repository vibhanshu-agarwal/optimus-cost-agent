import inspect

import pytest

from optimus.acp import bootstrap as bootstrap_module
from optimus.acp.bootstrap import (
    StartupConfigurationError,
    build_agent_runner_for_harness,
    build_client_mcp_runtime,
    build_configured_server,
)
from optimus.acp.preflight import PreflightFailure
from optimus.agent.runner import AgentRunner
from optimus.mcp.client_sdk import ClientMcpSdkAdapter


def test_bootstrap_has_no_divergent_dead_redis_default_constant():
    """Plan 11.6 Task 1 fold-in: remove the unused localhost Redis hint that disagreed
    with local_infra's live 127.0.0.1 default.
    """
    assert not hasattr(bootstrap_module, "_DEFAULT_REDIS_URL_HINT")
    source = inspect.getsource(bootstrap_module)
    assert "_DEFAULT_REDIS_URL_HINT" not in source
    assert "redis://localhost:6379/0" not in source


def test_bootstrap_reports_missing_optimus_credentials(tmp_path):
    with pytest.raises(StartupConfigurationError) as exc_info:
        build_configured_server(environ={"OPTIMUS_REDIS_URL": "redis://localhost:6379/0"}, workspace_root=tmp_path)

    assert exc_info.value.exit_code == 2
    assert "Set OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY" in exc_info.value.user_message


def test_bootstrap_reports_missing_redis_url(tmp_path):
    env = {"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765", "OPTIMUS_API_KEY": "opt-test"}

    with pytest.raises(StartupConfigurationError) as exc_info:
        build_configured_server(environ=env, workspace_root=tmp_path)

    assert exc_info.value.exit_code == 2
    assert "Set OPTIMUS_REDIS_URL" in exc_info.value.user_message


def test_bootstrap_builds_agent_configured_server(tmp_path, monkeypatch):
    class FakeStore:
        def ping(self):
            return None

    class FakeRuntime:
        def ping(self):
            return None

        def sync_state_store(self):
            return FakeStore()

        def telemetry_adapter(self):
            return object()

    class FakeClientRuntime:
        disposition = object()
        supervisor = object()
        mcp_http_enabled = False
        mcp_sse_enabled = False

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        "optimus.acp.preflight.run_preflight",
        lambda environ, **kwargs: "redis://localhost:6379/0",
    )
    monkeypatch.setattr("optimus.acp.bootstrap.RedisRuntime.from_url", lambda url: FakeRuntime())
    monkeypatch.setattr(
        "optimus.acp.bootstrap.build_client_mcp_runtime",
        lambda **kwargs: FakeClientRuntime(),
    )
    server = build_configured_server(
        environ={
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "opt-test",
            "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
        },
        workspace_root=tmp_path,
        model="glm-5.2",
        gateway_timeout_seconds=90.0,
    )

    assert server is not None
    assert server._dispatcher._gateway_client._timeout_seconds == 90.0
    assert server._dispatcher._agent_runner._gateway_client._timeout_seconds == 90.0


def test_bootstrap_gateway_timeout_defaults_to_thirty_seconds(tmp_path, monkeypatch):
    class FakeStore:
        def ping(self):
            return None

    class FakeRuntime:
        def ping(self):
            return None

        def sync_state_store(self):
            return FakeStore()

        def telemetry_adapter(self):
            return object()

    class FakeClientRuntime:
        disposition = object()
        supervisor = object()
        mcp_http_enabled = False
        mcp_sse_enabled = False

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        "optimus.acp.preflight.run_preflight",
        lambda environ, **kwargs: "redis://localhost:6379/0",
    )
    monkeypatch.setattr("optimus.acp.bootstrap.RedisRuntime.from_url", lambda url: FakeRuntime())
    monkeypatch.setattr(
        "optimus.acp.bootstrap.build_client_mcp_runtime",
        lambda **kwargs: FakeClientRuntime(),
    )
    server = build_configured_server(
        environ={
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "opt-test",
            "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
        },
        workspace_root=tmp_path,
        model="glm-5.2",
    )

    assert server._dispatcher._gateway_client._timeout_seconds == 30.0
    assert server._dispatcher._agent_runner._gateway_client._timeout_seconds == 30.0


def test_bootstrap_reports_unreachable_redis(tmp_path, monkeypatch):
    def _raise_unreachable(*args, **kwargs):
        raise PreflightFailure(exit_code=2, user_message="Redis is not reachable.")

    monkeypatch.setattr("optimus.acp.preflight.run_preflight", _raise_unreachable)

    with pytest.raises(StartupConfigurationError) as exc_info:
        build_configured_server(
            environ={
                "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
                "OPTIMUS_API_KEY": "opt-test",
                "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
            },
            workspace_root=tmp_path,
        )

    assert exc_info.value.exit_code == 2
    assert "Redis is not reachable" in exc_info.value.user_message


def test_bootstrap_wires_workspace_context_observer(monkeypatch, tmp_path):
    from optimus.acp.debug_trace import log_planning_replan_event, log_workspace_context_result

    captured_kwargs: dict = {}

    class CapturingAgentRunner(AgentRunner):
        def __init__(self, **kwargs) -> None:
            captured_kwargs.update(kwargs)
            super().__init__(**kwargs)

    class FakeStore:
        def ping(self):
            return None

    class FakeRuntime:
        def ping(self):
            return None

        def sync_state_store(self):
            return FakeStore()

        def telemetry_adapter(self):
            return object()

    monkeypatch.setattr("optimus.acp.bootstrap.AgentRunner", CapturingAgentRunner)
    monkeypatch.setattr(
        "optimus.acp.preflight.run_preflight",
        lambda environ, **kwargs: "redis://localhost:6379/0",
    )
    monkeypatch.setattr("optimus.acp.bootstrap.RedisRuntime.from_url", lambda url: FakeRuntime())

    build_agent_runner_for_harness(
        environ={
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "opt-test",
            "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
        },
        workspace_root=tmp_path,
        model="glm-5.2",
    )

    assert captured_kwargs["workspace_context_observer"] is log_workspace_context_result
    assert captured_kwargs["planning_progress_observer"] is log_planning_replan_event


def test_bootstrap_wires_one_telemetry_fanout_with_jsonl_redis_and_gateway_exporter(monkeypatch, tmp_path):
    from optimus.telemetry.fanout import TelemetryFanout
    from optimus.telemetry.jsonl import JsonlTelemetryWriter
    from optimus.telemetry.observability import GatewayObservabilityExporter
    from optimus.telemetry.redis_sink import RedisTelemetryEventSink

    captured_kwargs: dict = {}

    class CapturingAgentRunner(AgentRunner):
        def __init__(self, **kwargs) -> None:
            captured_kwargs.update(kwargs)
            super().__init__(**kwargs)

    class FakeStore:
        def ping(self):
            return None

    class FakeRuntime:
        def ping(self):
            return None

        def sync_state_store(self):
            return FakeStore()

        def telemetry_adapter(self):
            return object()

    monkeypatch.setattr("optimus.acp.bootstrap.AgentRunner", CapturingAgentRunner)
    monkeypatch.setattr(
        "optimus.acp.preflight.run_preflight",
        lambda environ, **kwargs: "redis://localhost:6379/0",
    )
    monkeypatch.setattr("optimus.acp.bootstrap.RedisRuntime.from_url", lambda url: FakeRuntime())

    build_agent_runner_for_harness(
        environ={
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "opt-test",
            "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
        },
        workspace_root=tmp_path,
        model="glm-5.2",
    )

    fanout = captured_kwargs["event_sink"]
    assert isinstance(fanout, TelemetryFanout)
    assert isinstance(fanout.jsonl_writer, JsonlTelemetryWriter)
    assert fanout.jsonl_writer.path == tmp_path.resolve() / ".optimus" / "telemetry.jsonl"
    assert isinstance(fanout.redis_sink, RedisTelemetryEventSink)
    assert isinstance(fanout.gateway_exporter, GatewayObservabilityExporter)


def test_bootstrap_builds_process_lifetime_client_mcp_runtime(tmp_path, monkeypatch):
    class FakeStore:
        def ping(self):
            return None

    class FakeRuntime:
        def ping(self):
            return None

        def sync_state_store(self):
            return FakeStore()

        def telemetry_adapter(self):
            return object()

    from optimus.mcp.client_config import ClientMcpConfigNormalizer
    from optimus.mcp.client_disposition import ClientMcpDisposition, ClientMcpRuntime
    from optimus.mcp.client_supervisor import MCPAsyncSupervisor
    from optimus.mcp.client_trust import ClientMcpDurableStore, ClientMcpLeaseAuthority

    class _MemKeyring:
        def __init__(self) -> None:
            self._store = {}

        def get_password(self, service, key):
            return self._store.get((service, key))

        def set_password(self, service, key, value):
            self._store[(service, key)] = value

        def delete_password(self, service, key):
            self._store.pop((service, key), None)

    mem = _MemKeyring()
    hmac_key = b"0" * 32
    durable = ClientMcpDurableStore(keyring_backend=mem, hmac_key=hmac_key)
    supervisor = MCPAsyncSupervisor()
    supervisor.start()
    runtime = ClientMcpRuntime(
        disposition=ClientMcpDisposition(
            normalizer=ClientMcpConfigNormalizer(),
            lease_authority=ClientMcpLeaseAuthority(store=durable),
            hmac_key=hmac_key,
            controlled_path="",
            workspace_digest="c" * 64,
        ),
        supervisor=supervisor,
        mcp_http_enabled=False,
        mcp_sse_enabled=False,
    )

    monkeypatch.setattr(
        "optimus.acp.preflight.run_preflight",
        lambda environ, **kwargs: "redis://localhost:6379/0",
    )
    monkeypatch.setattr("optimus.acp.bootstrap.RedisRuntime.from_url", lambda url: FakeRuntime())
    monkeypatch.setattr("optimus.acp.bootstrap.build_client_mcp_runtime", lambda **kwargs: runtime)

    server = build_configured_server(
        environ={
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "opt-test",
            "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
        },
        workspace_root=tmp_path,
        model="glm-5.2",
    )
    assert server.client_mcp_runtime is runtime
    assert runtime.disposition is not None
    assert runtime.supervisor is not None
    assert runtime.mcp_http_enabled is False
    assert runtime.mcp_sse_enabled is False
    assert not hasattr(server._dispatcher, "client_mcp_capability")
    runtime.close()


def test_bootstrap_retains_one_real_sdk_adapter_without_opening_a_capability(tmp_path, monkeypatch):
    """Bootstrap must construct capability wiring without manufacturing a session/new connection."""
    monkeypatch.setenv("OPTIMUS_CLIENT_MCP_EPHEMERAL_HMAC", "1")

    runtime = build_client_mcp_runtime(workspace_root=tmp_path)
    try:
        assert isinstance(runtime.sdk_adapter, ClientMcpSdkAdapter)
        assert runtime.sdk_adapter._connections == {}
        assert runtime.supervisor.state.value == "RUNNING"
        with pytest.raises(TypeError, match="not serializable"):
            runtime.sdk_adapter.__getstate__()
    finally:
        runtime.close()
