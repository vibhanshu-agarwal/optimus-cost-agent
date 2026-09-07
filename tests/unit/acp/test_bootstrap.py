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
from optimus.mcp.client_disposition import ClientMcpRuntime
from optimus.mcp.client_sdk import ClientMcpSdkAdapter


def _test_sdk_adapter(supervisor) -> ClientMcpSdkAdapter:
    class _NoopProcessControl:
        def terminate_tree(self, *, seam: str) -> None:
            del seam

    return ClientMcpSdkAdapter(
        supervisor=supervisor,
        session_factory=lambda _capability: None,
        http_client_factory=object,
        stdio_transport_factory=lambda _capability: None,
        process_control=_NoopProcessControl(),
    )


def test_bootstrap_has_no_divergent_dead_redis_default_constant():
    """Plan 11.6 Task 1 fold-in: remove the unused localhost Redis hint that disagreed
    with local_infra's live 127.0.0.1 default.
    """
    assert not hasattr(bootstrap_module, "_DEFAULT_REDIS_URL_HINT")
    source = inspect.getsource(bootstrap_module)
    assert "_DEFAULT_REDIS_URL_HINT" not in source
    assert "redis://localhost:6379/0" not in source


def test_client_mcp_runtime_requires_an_sdk_adapter() -> None:
    """A runtime without an owned adapter would silently skip connection teardown."""
    with pytest.raises(TypeError, match="sdk_adapter"):
        ClientMcpRuntime(disposition=object(), supervisor=object())  # type: ignore[arg-type]


def test_client_mcp_runtime_rejects_an_explicitly_missing_sdk_adapter() -> None:
    """An explicit None must fail at construction, before the later close path."""
    with pytest.raises(ValueError, match="sdk_adapter"):
        ClientMcpRuntime(  # type: ignore[arg-type]
            disposition=object(),
            supervisor=object(),
            sdk_adapter=None,
        )


def test_bootstrap_reports_missing_optimus_credentials(tmp_path):
    with pytest.raises(StartupConfigurationError) as exc_info:
        build_configured_server(environ={"OPTIMUS_REDIS_URL": "redis://localhost:6379/0"}, workspace_root=tmp_path)

    assert exc_info.value.exit_code == 2
    assert "Set OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY" in exc_info.value.user_message


def test_bootstrap_reports_missing_redis_url(tmp_path):
    env = {"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765", "OPTIMUS_API_KEY": "opt-test"}  # pragma: allowlist secret

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
            "OPTIMUS_API_KEY": "opt-test",  # pragma: allowlist secret
            "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
        },
        workspace_root=tmp_path,
        model="glm-5.2",
        gateway_timeout_seconds=90.0,
    )

    assert server is not None
    assert server._dispatcher._gateway_client._timeout_seconds == 90.0
    assert server._dispatcher._agent_runner._gateway_client._timeout_seconds == 90.0
    assert server.conversation_sanitizer_inputs is not None
    assert "opt-test" in server.conversation_sanitizer_inputs.known_secrets
    assert server.conversation_sanitizer_inputs.known_pii == ()


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
            "OPTIMUS_API_KEY": "opt-test",  # pragma: allowlist secret
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
                "OPTIMUS_API_KEY": "opt-test",  # pragma: allowlist secret
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
            "OPTIMUS_API_KEY": "opt-test",  # pragma: allowlist secret
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
            "OPTIMUS_API_KEY": "opt-test",  # pragma: allowlist secret
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
        sdk_adapter=_test_sdk_adapter(supervisor),
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
            "OPTIMUS_API_KEY": "opt-test",  # pragma: allowlist secret
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
    import keyring as keyring_module

    def _no_backend(*_a, **_k):
        raise AssertionError("this test must never reach the real keyring backend")

    for name in ("get_password", "set_password", "delete_password"):
        monkeypatch.setattr(keyring_module, name, _no_backend)

    # Seam 3: the ephemeral flag crosses as an explicit boolean bound to captured
    # input; it is no longer read from the ambient environment. Setting the env
    # var here would silently select a real keyring-backed key, which the guard
    # above now makes impossible to miss.
    runtime = build_client_mcp_runtime(
        workspace_root=tmp_path,
        system_environ={"PATH": "/probe/bin"},
        ephemeral_hmac=True,
    )
    try:
        assert isinstance(runtime.sdk_adapter, ClientMcpSdkAdapter)
        assert runtime.sdk_adapter._connections == {}
        assert runtime.supervisor.state.value == "RUNNING"
        assert runtime.disposition._controlled_path == "/probe/bin"
        with pytest.raises(TypeError, match="not serializable"):
            runtime.sdk_adapter.__getstate__()
    finally:
        runtime.close()


# --- seam 3: captured system values reach MCP construction; ambient never does ---


class _RecordingKeyring:
    """In-memory keyring that records every call. Never touches the OS keychain."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, key: str) -> str | None:
        self.calls.append(("get", service, key))
        return self._store.get((service, key))

    def set_password(self, service: str, key: str, value: str) -> None:
        self.calls.append(("set", service, key))
        self._store[(service, key)] = value

    def delete_password(self, service: str, key: str) -> None:
        self.calls.append(("delete", service, key))
        self._store.pop((service, key), None)


def _install_recording_keyring(monkeypatch) -> _RecordingKeyring:
    """bootstrap passes the `keyring` module itself as the backend, so guard its functions."""
    import keyring as keyring_module

    recorder = _RecordingKeyring()
    for name in ("get_password", "set_password", "delete_password"):
        monkeypatch.setattr(keyring_module, name, getattr(recorder, name))
    return recorder


def _patch_preflighted_runtime(monkeypatch) -> None:
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

    monkeypatch.setattr(
        "optimus.acp.preflight.run_preflight",
        lambda environ, **kwargs: "redis://localhost:6379/0",
    )
    monkeypatch.setattr("optimus.acp.bootstrap.RedisRuntime.from_url", lambda url: FakeRuntime())


def _fake_client_runtime():
    class FakeClientRuntime:
        disposition = object()
        supervisor = object()
        mcp_http_enabled = False
        mcp_sse_enabled = False

        def close(self) -> None:
            return None

    return FakeClientRuntime()


def _server_environ() -> dict[str, str]:
    return {
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
        "OPTIMUS_API_KEY": "opt-test-gateway-credential",  # pragma: allowlist secret
        "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, False), ("", False), ("1", True), ("true", True), (" ", True)],
    ids=["unset", "empty", "one", "true", "whitespace-only-preserved-truthiness"],
)
def test_resolve_ephemeral_hmac_flag_preserves_the_pre_seam_3_interpretation(value, expected):
    """Any non-empty value requests an ephemeral key, exactly as the former
    `os.environ.get(...)` truthiness did. Whitespace-only is preserved rather
    than silently re-interpreted (the work record raises it as an open question).
    The launch gate rejects any inherited value whose stripped form is non-empty,
    so through optimus-agent's real entry point only unset, empty or whitespace
    values can reach this helper."""
    environ = {} if value is None else {"OPTIMUS_CLIENT_MCP_EPHEMERAL_HMAC": value}

    assert bootstrap_module.resolve_ephemeral_hmac_flag(environ) is expected


def test_resolve_ephemeral_hmac_flag_reads_the_captured_mapping_not_ambient(monkeypatch):
    monkeypatch.setenv("OPTIMUS_CLIENT_MCP_EPHEMERAL_HMAC", "1")
    assert bootstrap_module.resolve_ephemeral_hmac_flag({}) is False

    monkeypatch.delenv("OPTIMUS_CLIENT_MCP_EPHEMERAL_HMAC")
    assert bootstrap_module.resolve_ephemeral_hmac_flag({"OPTIMUS_CLIENT_MCP_EPHEMERAL_HMAC": "1"}) is True


def test_build_client_mcp_runtime_binds_path_and_hmac_choice_to_captured_input_not_ambient(tmp_path, monkeypatch):
    """The two ambient rereads bootstrap used to make: PATH and the ephemeral flag."""
    recorder = _install_recording_keyring(monkeypatch)
    monkeypatch.setenv("PATH", "/ambient/changed/after/capture")
    monkeypatch.setenv("OPTIMUS_CLIENT_MCP_EPHEMERAL_HMAC", "1")
    system_view = {"PATH": "/captured/bin", "PATHEXT": ".EXE", "SYSTEMROOT": r"C:\Windows"}

    runtime = build_client_mcp_runtime(workspace_root=tmp_path, system_environ=system_view, ephemeral_hmac=False)
    try:
        system_view["PATH"] = "/mutated/after/construction"
        system_view["PATHEXT"] = ".CMD"
        assert runtime.disposition._controlled_path == "/captured/bin"
        assert runtime.disposition._normalizer._pathext == ".EXE"
        assert runtime.disposition._normalizer._system_root == r"C:\Windows"
        assert recorder.calls, "ephemeral_hmac=False selects the keyring-backed store even when the ambient flag is set"
    finally:
        runtime.close()


def test_build_client_mcp_runtime_explicit_ephemeral_request_never_touches_the_keyring(tmp_path, monkeypatch):
    recorder = _install_recording_keyring(monkeypatch)
    monkeypatch.delenv("OPTIMUS_CLIENT_MCP_EPHEMERAL_HMAC", raising=False)

    runtime = build_client_mcp_runtime(workspace_root=tmp_path, system_environ={}, ephemeral_hmac=True)
    try:
        assert recorder.calls == []
        assert runtime.disposition._controlled_path == ""
    finally:
        runtime.close()


def test_build_configured_server_defaults_to_an_empty_system_view_never_ambient(tmp_path, monkeypatch):
    """Missing or explicitly empty injected context is empty; it never reopens os.environ."""
    captured: dict[str, object] = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return _fake_client_runtime()

    _patch_preflighted_runtime(monkeypatch)
    monkeypatch.setattr("optimus.acp.bootstrap.build_client_mcp_runtime", _capture)
    monkeypatch.setenv("PATH", "/ambient/bin")
    monkeypatch.setenv("OPTIMUS_CLIENT_MCP_EPHEMERAL_HMAC", "1")

    build_configured_server(environ=_server_environ(), workspace_root=tmp_path, model="glm-5.2")
    assert set(captured) == {"workspace_root", "system_environ", "ephemeral_hmac"}
    assert captured["system_environ"] == {}
    assert captured["ephemeral_hmac"] is False

    captured.clear()
    build_configured_server(environ=_server_environ(), system_environ={}, workspace_root=tmp_path, model="glm-5.2")
    assert captured["system_environ"] == {}
    assert captured["ephemeral_hmac"] is False


def test_bootstrap_never_hands_the_gateway_credential_to_the_mcp_child(tmp_path):
    """Only a bootstrap-side test proves what bootstrap *passes*, so start from a
    real captured snapshot that contains the credential and assert the handoff
    drops it. This pins the exact mistake an earlier design proposal would have
    made: routing MCP through the agent-child projection, which legitimately
    carries OPTIMUS_API_KEY because the agent child needs it. MCP servers are a
    different trust boundary.

    Scope note: this forbids *inherited* propagation. A client that explicitly
    supplies a variable of that name is a separate, still-permitted case; do not
    widen this into a blanket ban without changing that contract deliberately.
    """
    from optimus.acp.launch_policy import LaunchEnvironmentSnapshot
    from optimus.acp.subprocess_env import system_environ_view

    snapshot = LaunchEnvironmentSnapshot.capture(
        {
            "OPTIMUS_API_KEY": "gateway-credential-must-not-cross",  # pragma: allowlist secret
            "PATH": "/captured/bin",
            "SYSTEMROOT": r"C:\Windows",
        }
    )
    handoff = system_environ_view(snapshot.values)

    assert "OPTIMUS_API_KEY" not in handoff
    assert "gateway-credential-must-not-cross" not in repr(handoff)
    assert handoff == {"PATH": "/captured/bin", "SYSTEMROOT": r"C:\Windows"}


def test_real_startup_wiring_hands_captured_system_values_to_mcp(monkeypatch, tmp_path):
    """The decisive seam-3 regression at the bootstrap boundary: it drives the REAL
    build_configured_server → build_client_mcp_runtime call path and asserts the
    actual kwargs. A helper-only projection test cannot prove bootstrap forwards it.

    Requires: captured system values survive a later ambient change and a later
    mutation of the caller's mapping, the inherited Gateway credential does not
    cross, the system view is not the agent environ, and the explicit ephemeral
    request passes through unchanged.
    """
    captured: dict[str, object] = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return _fake_client_runtime()

    _patch_preflighted_runtime(monkeypatch)
    monkeypatch.setattr("optimus.acp.bootstrap.build_client_mcp_runtime", _capture)
    monkeypatch.setenv("PATH", "/ambient/changed/after/capture")
    agent_environ = _server_environ()
    system_view = {"PATH": "/captured/bin", "PATHEXT": ".EXE", "SYSTEMROOT": r"C:\Windows"}

    build_configured_server(
        environ=agent_environ,
        system_environ=system_view,
        ephemeral_hmac=True,
        workspace_root=tmp_path,
        model="glm-5.2",
    )
    system_view["PATH"] = "/mutated/after/call"

    assert set(captured) == {"workspace_root", "system_environ", "ephemeral_hmac"}
    view = captured["system_environ"]
    assert view == {"PATH": "/captured/bin", "PATHEXT": ".EXE", "SYSTEMROOT": r"C:\Windows"}
    assert view is not system_view, "bootstrap must hand over a fresh copy, not the caller's mapping"
    assert "OPTIMUS_API_KEY" not in view, "the inherited Gateway credential must not cross to MCP"
    assert "opt-test-gateway-credential" not in repr(view)
    assert view is not agent_environ
    assert captured["ephemeral_hmac"] is True


def test_real_startup_wiring_strips_a_misrouted_agent_environ_down_to_system_names(monkeypatch, tmp_path):
    """Defense in depth at the bootstrap boundary: even if a caller hands the
    credential-bearing agent environ as the system view, only allowlisted system
    names reach MCP construction."""
    captured: dict[str, object] = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return _fake_client_runtime()

    _patch_preflighted_runtime(monkeypatch)
    monkeypatch.setattr("optimus.acp.bootstrap.build_client_mcp_runtime", _capture)
    misrouted = {**_server_environ(), "PATH": "/captured/bin"}

    build_configured_server(environ=_server_environ(), system_environ=misrouted, workspace_root=tmp_path, model="glm-5.2")

    assert captured["system_environ"] == {"PATH": "/captured/bin"}


# --- seam 3 R1: an explicitly empty PATHEXT survives the bootstrap boundary ---


def test_build_configured_server_preserves_explicitly_empty_pathext_and_keeps_absent_absent(tmp_path, monkeypatch):
    """Dropping the empty value upstream would silently re-enable the default
    executable extensions that the caller explicitly switched off."""
    captured: dict[str, object] = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return _fake_client_runtime()

    _patch_preflighted_runtime(monkeypatch)
    monkeypatch.setattr("optimus.acp.bootstrap.build_client_mcp_runtime", _capture)
    monkeypatch.setenv("PATHEXT", ".CMD")  # ambient must not fill the gap either way

    build_configured_server(
        environ=_server_environ(),
        system_environ={"PATH": "/captured/bin", "PATHEXT": ""},
        workspace_root=tmp_path,
        model="glm-5.2",
    )
    assert captured["system_environ"] == {"PATH": "/captured/bin", "PATHEXT": ""}

    captured.clear()
    build_configured_server(
        environ=_server_environ(),
        system_environ={"PATH": "/captured/bin"},
        workspace_root=tmp_path,
        model="glm-5.2",
    )
    assert captured["system_environ"] == {"PATH": "/captured/bin"}


def test_build_client_mcp_runtime_binds_explicit_empty_versus_missing_pathext(tmp_path, monkeypatch):
    recorder = _install_recording_keyring(monkeypatch)
    monkeypatch.setenv("PATHEXT", ".CMD")

    empty = build_client_mcp_runtime(workspace_root=tmp_path, system_environ={"PATHEXT": ""}, ephemeral_hmac=True)
    try:
        assert empty.disposition._normalizer._pathext == ""
    finally:
        empty.close()

    missing = build_client_mcp_runtime(workspace_root=tmp_path, system_environ={}, ephemeral_hmac=True)
    try:
        assert missing.disposition._normalizer._pathext == ".COM;.EXE;.BAT;.CMD"
    finally:
        missing.close()
    assert recorder.calls == []
