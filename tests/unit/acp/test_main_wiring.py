from __future__ import annotations

import json
import shutil
import sys
from unittest.mock import Mock

import pytest

from optimus.acp import __main__ as acp_main
from tests.unit.acp.conftest import FakeKeyring, authorize_workspace_for_test


def _base_env(*, gateway_url: str = "http://127.0.0.1:8765") -> dict[str, str]:
    return {
        "OPTIMUS_GATEWAY_URL": gateway_url,
        "OPTIMUS_API_KEY": "test-key",
        "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
    }


def _authorize(monkeypatch, tmp_path, env):
    """Author a durable approval matching `env`, set the env vars, and patch
    acp_main.keyring to the same fake backend used for authoring — matching
    main()'s own KeyringApprovalStore construction."""
    fake_keyring = FakeKeyring()
    authorize_workspace_for_test(env=env, workspace_root=tmp_path, fake_keyring=fake_keyring)
    monkeypatch.setattr(acp_main, "keyring", fake_keyring)
    for name, value in env.items():
        monkeypatch.setenv(name, value)


def _patch_common(monkeypatch, *, server_factory=None):
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


def test_setup_flag_calls_wizard_and_short_circuits(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(acp_main, "run_setup_wizard", lambda **kwargs: calls.append(kwargs) or 0)

    def _must_not_run(*_a, **_k):
        raise AssertionError("must not run during --setup short-circuit")

    monkeypatch.setattr(acp_main, "build_configured_server", _must_not_run)

    exit_code = acp_main.main(["--setup"])

    assert exit_code == 0
    assert len(calls) == 1


def test_setup_uses_operator_config_root_not_workspace(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    config = tmp_path / "operator-config"
    captured = {}

    def fake_setup(*, config_root):
        captured["root"] = config_root
        return 0

    monkeypatch.setenv("OPTIMUS_CONFIG_ROOT", str(config))
    monkeypatch.setattr(acp_main, "run_setup_wizard", fake_setup)
    assert acp_main.main(["--workspace-root", str(workspace), "--setup"]) == 0
    assert captured["root"] == config.resolve()


def test_workspace_contained_config_root_exits_before_setup_or_infra(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("OPTIMUS_CONFIG_ROOT", str(workspace / "config"))
    setup = Mock()
    redis = Mock()
    monkeypatch.setattr(acp_main, "run_setup_wizard", setup)
    monkeypatch.setattr(acp_main, "ensure_local_redis", redis)
    assert acp_main.main(["--workspace-root", str(workspace), "--setup"]) == 2
    setup.assert_not_called()
    redis.assert_not_called()


def test_setup_workspace_contained_config_root_error_has_agent_prefix(monkeypatch, tmp_path, capsys) -> None:
    """Plan 9.96 review finding: __main__.py's --setup branch prints
    OperatorPathConfigurationError.user_message raw, unlike its sibling
    TrustedPathError/LaunchGateError handlers which all prepend
    'optimus-agent: '. operator_verify.py's gate-rejection detector keys on
    that exact prefix, so every __main__.py error print must carry it."""
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("OPTIMUS_CONFIG_ROOT", str(workspace / "config"))
    setup = Mock()
    monkeypatch.setattr(acp_main, "run_setup_wizard", setup)

    exit_code = acp_main.main(["--workspace-root", str(workspace), "--setup"])

    assert exit_code == 2
    setup.assert_not_called()
    err = capsys.readouterr().err
    assert err.startswith("optimus-agent: "), err


def test_authorize_workspace_contained_config_root_error_has_agent_prefix(monkeypatch, tmp_path, capsys) -> None:
    """Same regression as above, but for the non-setup gated launch path
    (_authorize_or_exit), which has its own separate
    OperatorPathConfigurationError handler.

    The workspace directory must actually exist here: otherwise
    resolve_workspace_identity() raises WORKSPACE_NOT_FOUND (a
    TrustedPathError, already prefixed) before the operator-paths check is
    ever reached, which would make this test pass vacuously without
    exercising the OperatorPathConfigurationError handler at all."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("OPTIMUS_CONFIG_ROOT", str(workspace / "config"))
    redis = Mock()
    monkeypatch.setattr(acp_main, "ensure_local_redis", redis)

    exit_code = acp_main.main(["--workspace-root", str(workspace)])

    assert exit_code == 2
    redis.assert_not_called()
    err = capsys.readouterr().err
    assert "Refusing to load local gateway configuration" in err, err
    assert err.startswith("optimus-agent: "), err


def test_unapproved_workspace_fails_closed_before_any_side_effect(monkeypatch, tmp_path) -> None:
    """Plan 9.96, Task 5 Step 1 (fail-before-side-effect matrix, serve path):
    an unapproved workspace must be rejected by authorize_launch() before
    ensure_local_redis/ensure_local_gateway/build_configured_server are ever
    called."""
    env = _base_env()
    fake_keyring = FakeKeyring()
    monkeypatch.setattr(acp_main, "keyring", fake_keyring)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    redis_calls: list[object] = []
    gateway_calls: list[object] = []
    server_calls: list[object] = []
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: redis_calls.append((a, k)))
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: gateway_calls.append(k) or None)
    monkeypatch.setattr(acp_main, "build_configured_server", lambda **k: server_calls.append(k) or None)

    exit_code = acp_main.main(["--workspace-root", str(tmp_path)])

    assert exit_code == 2
    assert redis_calls == []
    assert gateway_calls == []
    assert server_calls == []
    assert not (tmp_path / ".optimus").exists()


def test_approved_fresh_workspace_audits_and_revalidates_after_approval_ceremony(
    monkeypatch, tmp_path
) -> None:
    """A completed TTY approval creates the root before identity capture.

    This deliberately drives the real approval preparation boundary rather
    than the direct-record helper used by older unit tests.
    """
    from optimus.acp import launch_approval_cli as cli_module
    from optimus.acp.launch_approvals import KeyringApprovalStore

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    env = _base_env()
    fake_keyring = FakeKeyring()
    approval_runtime = tmp_path / "approval-runtime"
    store = KeyringApprovalStore(keyring_backend=fake_keyring, runtime_root=approval_runtime)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    monkeypatch.setattr(cli_module, "_require_tty", lambda: None)
    monkeypatch.setattr(cli_module, "_resolve_store", lambda _workspace: (store, approval_runtime))
    monkeypatch.setattr(acp_main, "keyring", fake_keyring)
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **_kwargs: None)
    _patch_common(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")

    assert cli_module._cmd_approve(workspace, mode="durable", target_argv=[]) == 0
    assert (workspace / ".optimus").is_dir()
    assert acp_main.main(["--no-auto-start", "--workspace-root", str(workspace)]) == 0

    audit_lines = (workspace / ".optimus" / "launch-audit.ndjson").read_text(encoding="utf-8").splitlines()
    assert len(audit_lines) == 1


def test_legacy_approved_workspace_missing_root_fails_without_recreating_it(monkeypatch, tmp_path, capsys) -> None:
    """A launch consumes a completed approval but never repairs its root."""
    from optimus.acp import launch_approval_cli as cli_module
    from optimus.acp.launch_approvals import KeyringApprovalStore

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    env = _base_env()
    fake_keyring = FakeKeyring()
    approval_runtime = tmp_path / "approval-runtime"
    store = KeyringApprovalStore(keyring_backend=fake_keyring, runtime_root=approval_runtime)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    monkeypatch.setattr(cli_module, "_require_tty", lambda: None)
    monkeypatch.setattr(cli_module, "_resolve_store", lambda _workspace: (store, approval_runtime))
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")
    assert cli_module._cmd_approve(workspace, mode="durable", target_argv=[]) == 0
    (workspace / ".optimus").rmdir()

    redis = Mock()
    gateway = Mock()
    server = Mock()
    monkeypatch.setattr(acp_main, "keyring", fake_keyring)
    monkeypatch.setattr(acp_main, "ensure_local_redis", redis)
    monkeypatch.setattr(acp_main, "ensure_local_gateway", gateway)
    monkeypatch.setattr(acp_main, "build_configured_server", server)

    assert acp_main.main(["--workspace-root", str(workspace)]) == 2
    stderr = capsys.readouterr().err
    if sys.platform == "win32":
        assert "AUDIT_DIR_UNAVAILABLE" in stderr
    else:
        assert stderr.startswith(
            "optimus-agent: no launch approval found for this workspace."
        )
        assert "optimus-trust --workspace-root" in stderr
    assert not (workspace / ".optimus").exists()
    redis.assert_not_called()
    gateway.assert_not_called()
    server.assert_not_called()


def test_unclassified_variable_fails_closed_before_any_side_effect(monkeypatch, tmp_path) -> None:
    """An unknown OPTIMUS_* name in the inherited environment is rejected by
    resolve_launch_candidate() itself — even before authorize_launch() is
    reached — and must still leave every side-effect probe untouched."""
    env = _base_env()
    env["OPTIMUS_TOTALLY_UNKNOWN_SETTING"] = "1"
    fake_keyring = FakeKeyring()
    monkeypatch.setattr(acp_main, "keyring", fake_keyring)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    redis_calls: list[object] = []
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: redis_calls.append((a, k)))
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(acp_main, "build_configured_server", lambda **k: (_ for _ in ()).throw(AssertionError()))

    exit_code = acp_main.main(["--workspace-root", str(tmp_path)])

    assert exit_code == 2
    assert redis_calls == []


def test_snapshot_mismatch_fails_closed_with_remediation(monkeypatch, tmp_path, capsys) -> None:
    """Changing the effective configuration after approval invalidates the
    durable approval (SNAPSHOT_MISMATCH) and must still leave every
    side-effect probe untouched, with a remediation message naming the exact
    re-approval command."""
    env = _base_env()
    _authorize(monkeypatch, tmp_path, env)
    # Change the effective configuration after authoring the approval.
    # OPTIMUS_PRODUCTION_MODE is SECURITY-tier, so it is folded into
    # security_literals and therefore the security snapshot digest —
    # OPERATIONAL-tier names like OPTIMUS_AGENT_MODEL are not.
    monkeypatch.setenv("OPTIMUS_PRODUCTION_MODE", "true")

    redis_calls: list[object] = []
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: redis_calls.append((a, k)))
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(acp_main, "build_configured_server", lambda **k: (_ for _ in ()).throw(AssertionError()))

    exit_code = acp_main.main(["--workspace-root", str(tmp_path)])

    assert exit_code == 2
    assert redis_calls == []
    err = capsys.readouterr().err
    assert "changed since" in err
    assert "optimus-trust" in err
    assert "approve" in err


def test_startup_configuration_error_has_agent_prefix(monkeypatch, tmp_path, capsys):
    env = _base_env()
    _authorize(monkeypatch, tmp_path, env)

    def fail_build(**_kwargs):
        raise acp_main.StartupConfigurationError(exit_code=2, user_message="startup configuration failed")

    monkeypatch.setattr(acp_main, "build_configured_server", fail_build)

    assert acp_main.main(["--no-auto-start", "--workspace-root", str(tmp_path)]) == 2
    assert capsys.readouterr().err == "optimus-agent: startup configuration failed\n"


def test_no_auto_start_skips_redis_and_gateway_in_real_serve_path(monkeypatch, tmp_path) -> None:
    env = _base_env()
    _authorize(monkeypatch, tmp_path, env)
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
    env = _base_env()
    _authorize(monkeypatch, tmp_path, env)
    gateway_calls: list[dict[str, object]] = []
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: gateway_calls.append(k) or None)
    monkeypatch.setattr(acp_main, "run_preflight", lambda environ, **k: None)
    _patch_common(monkeypatch)

    exit_code = acp_main.main(["--check-config", "--workspace-root", str(tmp_path)])

    assert exit_code == 0
    assert gateway_calls == []


def test_no_auto_start_skips_redis_in_check_config_branch(monkeypatch, tmp_path) -> None:
    env = _base_env()
    _authorize(monkeypatch, tmp_path, env)
    redis_calls: list[tuple[object, object]] = []
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: redis_calls.append((a, k)))
    monkeypatch.setattr(acp_main, "run_preflight", lambda environ, **k: None)
    _patch_common(monkeypatch)

    exit_code = acp_main.main(["--check-config", "--no-auto-start", "--workspace-root", str(tmp_path)])

    assert exit_code == 0
    assert redis_calls == []


def test_check_config_passes_sanitized_environ_to_preflight(monkeypatch, tmp_path) -> None:
    env = _base_env()
    env["ANTHROPIC_API_KEY"] = "sk-ant-real"
    _authorize(monkeypatch, tmp_path, env)
    preflight_environ_seen: dict[str, str] = {}

    def fake_preflight(environ, **kwargs):
        preflight_environ_seen.update(environ)

    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "run_preflight", fake_preflight)

    exit_code = acp_main.main(["--check-config", "--workspace-root", str(tmp_path)])

    assert exit_code == 0
    assert preflight_environ_seen["OPTIMUS_API_KEY"] == "test-key"
    assert "ANTHROPIC_API_KEY" not in preflight_environ_seen


def test_gateway_process_stopped_only_if_it_was_started(monkeypatch, tmp_path) -> None:
    env = _base_env()
    _authorize(monkeypatch, tmp_path, env)
    stop_calls: list[str] = []

    class FakeGatewayProcess:
        def stop(self) -> None:
            stop_calls.append("stopped")

    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: FakeGatewayProcess())
    _patch_common(monkeypatch)

    exit_code = acp_main.main(["--workspace-root", str(tmp_path)])

    assert exit_code == 0
    assert stop_calls == ["stopped"]


def test_gateway_process_not_stopped_when_none_was_started(monkeypatch, tmp_path) -> None:
    env = _base_env()
    _authorize(monkeypatch, tmp_path, env)
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: None)
    _patch_common(monkeypatch)

    exit_code = acp_main.main(["--workspace-root", str(tmp_path)])

    assert exit_code == 0


def test_gateway_process_stopped_when_serve_raises(monkeypatch, tmp_path) -> None:
    env = _base_env()
    _authorize(monkeypatch, tmp_path, env)
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
    _patch_common(monkeypatch, server_factory=lambda **k: FailingServer())

    with pytest.raises(RuntimeError):
        acp_main.main(["--workspace-root", str(tmp_path)])

    assert stop_calls == ["stopped"]


def test_gateway_process_stopped_when_build_configured_server_raises_unexpectedly(monkeypatch, tmp_path) -> None:
    env = _base_env()
    _authorize(monkeypatch, tmp_path, env)
    stop_calls: list[str] = []

    class FakeGatewayProcess:
        def stop(self) -> None:
            stop_calls.append("stopped")

    def raising_build_configured_server(**_k):
        raise ValueError("unexpected settings construction failure")

    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: FakeGatewayProcess())
    _patch_common(monkeypatch, server_factory=raising_build_configured_server)

    with pytest.raises(ValueError):
        acp_main.main(["--workspace-root", str(tmp_path)])

    assert stop_calls == ["stopped"]


def test_real_serve_path_calls_helpers_in_expected_order(monkeypatch, tmp_path) -> None:
    env = _base_env()
    _authorize(monkeypatch, tmp_path, env)
    call_order: list[str] = []

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
        "ensure_local_redis",
        "ensure_local_gateway",
        "build_configured_server",
    ]


def test_anthropic_provider_key_reaches_gateway_child_but_not_agent_settings(monkeypatch, tmp_path) -> None:
    env = _base_env()
    env["OPTIMUS_LOCAL_GATEWAY_PROVIDER"] = "anthropic"
    env["ANTHROPIC_API_KEY"] = "sk-ant-real"
    _authorize(monkeypatch, tmp_path, env)

    gateway_call_seen: dict[str, object] = {}
    agent_environ_seen: dict[str, str] = {}

    def fake_ensure_local_gateway(*, provider_credentials, **_k):
        gateway_call_seen["provider_credentials"] = provider_credentials
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

    exit_code = acp_main.main(["--workspace-root", str(tmp_path)])

    assert exit_code == 0
    assert gateway_call_seen["provider_credentials"].secrets.provider == "anthropic"
    assert gateway_call_seen["provider_credentials"].secrets.model_provider_api_key == "sk-ant-real"
    assert "ANTHROPIC_API_KEY" not in agent_environ_seen


def test_openrouter_provider_key_reaches_gateway_child_but_not_agent_settings(monkeypatch, tmp_path) -> None:
    env = _base_env()
    env["OPTIMUS_LOCAL_GATEWAY_PROVIDER"] = "openrouter"
    env["OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY"] = "sk-or-real"
    env["OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET"] = "shared-secret"
    _authorize(monkeypatch, tmp_path, env)

    gateway_call_seen: dict[str, object] = {}
    agent_environ_seen: dict[str, str] = {}

    def fake_ensure_local_gateway(*, provider_credentials, shared_secret, **_k):
        gateway_call_seen["provider_credentials"] = provider_credentials
        gateway_call_seen["shared_secret"] = shared_secret
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

    exit_code = acp_main.main(["--workspace-root", str(tmp_path)])

    assert exit_code == 0
    assert gateway_call_seen["provider_credentials"].secrets.model_provider_api_key == "sk-or-real"
    assert "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY" not in agent_environ_seen
    assert "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET" not in agent_environ_seen


def test_audit_event_appended_before_redis_or_gateway_startup(monkeypatch, tmp_path) -> None:
    """Plan 9.96, Task 5 Step 6: the LaunchAuditEvent must be appended
    BEFORE any Redis/Gateway/agent startup side effect."""
    env = _base_env()
    _authorize(monkeypatch, tmp_path, env)
    call_order: list[str] = []

    original_append = acp_main.append_launch_audit_event

    def recording_append(*a, **k):
        call_order.append("append_launch_audit_event")
        return original_append(*a, **k)

    monkeypatch.setattr(acp_main, "append_launch_audit_event", recording_append)
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: call_order.append("ensure_local_redis"))
    monkeypatch.setattr(
        acp_main, "ensure_local_gateway", lambda **k: call_order.append("ensure_local_gateway") or None
    )
    _patch_common(monkeypatch)

    exit_code = acp_main.main(["--workspace-root", str(tmp_path)])

    assert exit_code == 0
    assert call_order.index("append_launch_audit_event") < call_order.index("ensure_local_redis")
    assert call_order.index("append_launch_audit_event") < call_order.index("ensure_local_gateway")


def test_audit_append_failure_stops_startup_before_any_side_effect(monkeypatch, tmp_path) -> None:
    """Step 6: audit append failure is fatal — there is no raw fallback, and
    no Redis/Gateway/agent startup may occur if the audit cannot be written."""
    from optimus.acp.launch_audit import LaunchAuditError

    env = _base_env()
    _authorize(monkeypatch, tmp_path, env)

    def failing_append(*_a, **_k):
        raise LaunchAuditError(code="AUDIT_APPEND_FAILED", detail="disk full")

    monkeypatch.setattr(acp_main, "append_launch_audit_event", failing_append)
    redis_calls: list[object] = []
    gateway_calls: list[object] = []
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: redis_calls.append((a, k)))
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: gateway_calls.append(k) or None)

    exit_code = acp_main.main(["--workspace-root", str(tmp_path)])

    assert exit_code == 2
    assert redis_calls == []
    assert gateway_calls == []


def test_diagnostic_grant_id_consumed_and_attached_to_authorized_launch(monkeypatch, tmp_path) -> None:
    """Plan 9.96, Task 6 Batch 2: --diagnostic-grant-id is the internal-only
    argument optimus-trust's `run --elevated-debug` substitutes into the
    argv it spawns (same slot pattern as --launch-approval-id/
    --launch-session-id). When present and valid, _authorize_or_exit must
    consume the grant (delete-on-consume, via
    KeyringApprovalStore.consume_diagnostic_grant) and thread a real
    DiagnosticGrant onto AuthorizedLaunch.diagnostic_grant -- not leave it
    permanently None as Task 5 left it."""
    from dataclasses import replace as dc_replace
    from datetime import datetime, timedelta, timezone

    from optimus.acp.launch_approvals import DIAGNOSTIC_TTL_SECONDS, DiagnosticGrant, compute_grant_hmac

    env = _base_env()
    fake_keyring = FakeKeyring()
    authorize_workspace_for_test(env=env, workspace_root=tmp_path, fake_keyring=fake_keyring)
    monkeypatch.setattr(acp_main, "keyring", fake_keyring)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    # Author a diagnostic grant matching the launch-session-id this test
    # will pass via --launch-session-id, signed with the SAME store's
    # hmac_key so it verifies for real (not a placeholder).
    from optimus.acp.launch_approvals import KeyringApprovalStore

    store = KeyringApprovalStore(keyring_backend=fake_keyring, runtime_root=tmp_path / ".optimus-runtime")
    unsigned = DiagnosticGrant(
        grant_id="diag_test_wiring",
        workspace_digest="placeholder",  # overwritten below once workspace identity is known
        approval_id="appr_placeholder",
        launch_session_id="sess_fixed_for_test",
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=DIAGNOSTIC_TTL_SECONDS),
        record_hmac="",
    )
    from optimus.acp.trusted_paths import resolve_workspace_identity

    ws_identity = resolve_workspace_identity(tmp_path)
    unsigned = dc_replace(unsigned, workspace_digest=ws_identity.digest)
    signed = dc_replace(unsigned, record_hmac=compute_grant_hmac(unsigned, hmac_key=store.hmac_key))
    store.write_diagnostic_grant(signed)

    captured_server_kwargs: dict[str, object] = {}

    def fake_build_configured_server(**kwargs):
        captured_server_kwargs.update(kwargs)

        class FakeServer:
            def serve_ndjson(self, *_a, **_k):
                async def _noop():
                    return None

                return _noop()

        return FakeServer()

    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: None)
    monkeypatch.setattr(acp_main, "build_configured_server", fake_build_configured_server)
    monkeypatch.setattr(acp_main, "StdioNdjsonLineReader", lambda *_a, **_k: object())
    monkeypatch.setattr(acp_main, "StdioNdjsonLineWriter", lambda *_a, **_k: object())

    exit_code = acp_main.main(
        [
            "--workspace-root",
            str(tmp_path),
            "--launch-session-id",
            "sess_fixed_for_test",
            "--diagnostic-grant-id",
            "diag_test_wiring",
            "--debug-trace",
        ]
    )

    assert exit_code == 0
    log_entries = [
        json.loads(line)
        for line in (tmp_path / ".optimus" / "debug-acp.ndjson").read_text(encoding="utf-8").splitlines()
    ]
    comparison_entries = [
        entry for entry in log_entries if entry["location"] == "launch_authorization_comparison"
    ]
    assert len(comparison_entries) == 1
    tags = comparison_entries[0]["data"]["correlation_tags"]
    assert tags == [{"field_name": "OPTIMUS_API_KEY", "tag": tags[0]["tag"]}]
    assert len(tags[0]["tag"]) == 32
    assert "test-key" not in json.dumps(comparison_entries)
    # Grant is consumed exactly once: the entry must no longer exist in the
    # keyring after the launch (delete-before-use semantics), proving
    # consume_diagnostic_grant (not just a read) was actually called.
    assert fake_keyring.get_password("optimus-cost-agent-approvals", "grant:diag_test_wiring") is None


def test_invalid_diagnostic_grant_id_downgrades_to_ordinary_not_launch_failure(monkeypatch, tmp_path) -> None:
    """Plan 9.96, Task 6 Batch 2: expiry/mismatch/not-found for a diagnostic
    grant must SILENTLY DOWNGRADE the launch to ordinary mode (no tags), not
    fail the launch closed -- the opposite of the launch gate's own
    fail-closed default. Ordinary mode is the SAFE mode here; failing the
    whole launch over an invalid diagnostic grant would be a
    denial-of-service on an otherwise fully-authorized launch, for a
    diagnostics feature that isn't security-critical to have.

    This test passes a --diagnostic-grant-id that was never written to the
    keyring at all -- the simplest invalid-grant case -- and asserts the
    launch proceeds to completion (exit_code == 0) exactly as it would with
    no --diagnostic-grant-id at all.
    """
    env = _base_env()
    _authorize(monkeypatch, tmp_path, env)

    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: None)
    _patch_common(monkeypatch)

    exit_code = acp_main.main(
        [
            "--workspace-root",
            str(tmp_path),
            "--diagnostic-grant-id",
            "diag_never_written",
        ]
    )

    assert exit_code == 0


def test_workspace_relocated_after_authorization_fails_closed_before_side_effect(
    monkeypatch, tmp_path
) -> None:
    """Plan 9.96, Task 5 Step 7 (TOCTOU matrix): unlike os.environ/config
    bytes/the keyring HMAC key -- all captured ONCE into an immutable value
    that downstream code never rereads -- workspace identity is a filesystem
    BINDING that gets consumed again at spawn time (the child cwd's into
    workspace_root and operates on whatever it resolves to THEN). Capture-
    once cannot defend this: retargeting the workspace directory (e.g. by
    deleting and recreating it, simulating a symlink retarget or relocation)
    between authorization and the first side effect must be caught by an
    explicit revalidate_workspace_identity() call, not silently ignored.

    This retargets the REAL filesystem binding (delete + recreate the actual
    workspace directory, changing its inode) rather than mutating a digest
    string in memory, so it proves the guard catches a real-world TOCTOU
    rather than an artificial in-memory-only signal.

    The mutation happens INSIDE the append_launch_audit_event call -- the
    earliest hookable point strictly AFTER authorize_launch() has already
    succeeded against the ORIGINAL workspace identity/digest, and strictly
    BEFORE the first side effect (ensure_local_redis). A mutation performed
    before calling main() (i.e. before authorization even runs) would just
    trip the pre-existing NO_APPROVAL check trivially, proving nothing about
    a genuine post-authorization TOCTOU window -- this is the mistake the
    first draft of this test made, caught by re-reading what NO_APPROVAL vs.
    a real TOCTOU revalidation gap actually requires.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    env = _base_env()
    _authorize(monkeypatch, workspace, env)

    original_append_audit = acp_main.append_launch_audit_event

    def relocating_append_audit(*a, **k):
        result = original_append_audit(*a, **k)
        # Retarget the real filesystem binding strictly AFTER authorization
        # succeeded: delete and recreate the directory, allocating a new
        # inode on platforms where that changes identity, while the path
        # string stays the same.
        shutil.rmtree(workspace)
        workspace.mkdir()
        return result

    monkeypatch.setattr(acp_main, "append_launch_audit_event", relocating_append_audit)

    redis_calls: list[object] = []
    gateway_calls: list[object] = []
    server_calls: list[object] = []
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: redis_calls.append((a, k)))
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: gateway_calls.append(k) or None)
    monkeypatch.setattr(acp_main, "build_configured_server", lambda **k: server_calls.append(k) or None)

    exit_code = acp_main.main(["--workspace-root", str(workspace)])

    assert exit_code == 2
    assert redis_calls == []
    assert gateway_calls == []
    assert server_calls == []


def test_gateway_child_construction_ignores_os_environ_mutated_after_capture(monkeypatch, tmp_path) -> None:
    """Plan 9.96, Task 5 Step 7 (TOCTOU matrix): the sibling test below
    (test_no_gated_helper_reads_os_environ_after_capture) only proves the
    AGENT side of Constraint 6 -- it observes environ via
    build_configured_server, never exercising ensure_local_gateway at all.
    The Gateway child is constructed from a SEPARATE candidate field
    (candidate.provider_credentials/candidate.shared_secret, plus
    snapshot.values passed through as system_env for a small allowlist of
    OS keys like PATH) -- a completely different code path that could,
    independently, reread os.environ without this test ever catching it.
    This asserts a mutation to OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY made
    strictly AFTER capture has no effect on what ensure_local_gateway
    receives: this is the REQUIRED reading per Constraint 6 ("performs no
    later os.environ reads") -- a test that expected the launch to instead
    FAIL on this mutation would require an os.environ reread, which the
    constraint forbids. No-effect is the only constraint-consistent
    assertion, and it is also the stronger proof: a passing "it failed"
    test here would actually indicate a Constraint 6 violation.
    """
    env = _base_env()
    env["OPTIMUS_LOCAL_GATEWAY_PROVIDER"] = "openrouter"
    env["OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY"] = "sk-or-original"
    env["OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET"] = "shared-secret-original"
    _authorize(monkeypatch, tmp_path, env)

    gateway_call_seen: dict[str, object] = {}

    original_append_audit = acp_main.append_launch_audit_event

    def mutating_append_audit(*a, **k):
        result = original_append_audit(*a, **k)
        # Mutate os.environ strictly AFTER capture/authorization -- the
        # earliest hookable point -- before ensure_local_gateway ever runs.
        import os as os_module

        os_module.environ["OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY"] = "sk-or-ATTACKER-INJECTED"
        os_module.environ["OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET"] = "shared-secret-ATTACKER-INJECTED"
        return result

    def fake_ensure_local_gateway(*, provider_credentials, shared_secret, **_k):
        gateway_call_seen["provider_credentials"] = provider_credentials
        gateway_call_seen["shared_secret"] = shared_secret
        return None

    monkeypatch.setattr(acp_main, "append_launch_audit_event", mutating_append_audit)
    monkeypatch.setattr(acp_main, "ensure_local_gateway", fake_ensure_local_gateway)
    _patch_common(monkeypatch)

    exit_code = acp_main.main(["--workspace-root", str(tmp_path)])

    assert exit_code == 0
    assert gateway_call_seen["provider_credentials"].secrets.model_provider_api_key == "sk-or-original"
    assert gateway_call_seen["shared_secret"] == "shared-secret-original"


def test_no_gated_helper_reads_os_environ_after_capture(monkeypatch, tmp_path) -> None:
    """Global Constraint 6: after LaunchEnvironmentSnapshot.capture(os.environ)
    is called once at the top of main(), no subsequent os.environ mutation
    should change the outcome of authorization or child construction — proof
    that every downstream decision reads from the snapshot/candidate, not a
    second live os.environ read."""
    env = _base_env()
    _authorize(monkeypatch, tmp_path, env)

    import os as os_module

    agent_environ_seen: dict[str, str] = {}

    original_append_audit = acp_main.append_launch_audit_event

    def mutating_append_audit(*a, **k):
        # Mutate os.environ immediately after authorization/audit — the
        # earliest point after capture that a test can hook — simulating a
        # TOCTOU window between capture and the agent_environ construction
        # that happens next inside main(). If apply_local_defaults() (or
        # anything else downstream) re-reads os.environ instead of using
        # candidate.agent_environ, this mutation would be observed in the
        # environ build_configured_server receives.
        result = original_append_audit(*a, **k)
        os_module.environ["OPTIMUS_API_KEY"] = "attacker-injected-key"
        return result

    def fake_build_configured_server(*, environ, workspace_root, model):
        agent_environ_seen.update(environ)

        class FakeServer:
            def serve_ndjson(self, *_a, **_k):
                async def _noop():
                    return None

                return _noop()

        return FakeServer()

    monkeypatch.setattr(acp_main, "append_launch_audit_event", mutating_append_audit)
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "ensure_local_gateway", lambda **k: None)
    monkeypatch.setattr(acp_main, "build_configured_server", fake_build_configured_server)
    monkeypatch.setattr(acp_main, "StdioNdjsonLineReader", lambda *_a, **_k: object())
    monkeypatch.setattr(acp_main, "StdioNdjsonLineWriter", lambda *_a, **_k: object())

    exit_code = acp_main.main(["--workspace-root", str(tmp_path)])

    assert exit_code == 0
    assert agent_environ_seen["OPTIMUS_API_KEY"] == "test-key"
