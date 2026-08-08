"""Unit tests for loopback Streamable HTTP transport boundaries (Task 5).

Authentication is NOT proven here: PreParseAuthGateStub only asserts pipeline ordering.
Full credential/session evidence belongs to Task 6.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ALLOWED_MCP_TOOL_NAMES = frozenset(
    {
        "ledger.capabilities_status",
        "ledger.review_ruling_append",
        "ledger.review_ruling_read",
        "ledger.delivery_read",
        "ledger.delivery_confirm",
        "ledger.delivery_status",
        "ledger.integrity_recovery_status",
    }
)

FORBIDDEN_MCP_TOOL_SUBSTRINGS = (
    "collect",
    "process_launch",
    "window_capture",
    "approval",
    "mutation",
    "mutate",
)


def test_service_config_rejects_non_loopback_bind() -> None:
    from evidence_handoff_runtime.service import ServiceConfig, ServiceConfigError

    with pytest.raises(ServiceConfigError) as raised:
        ServiceConfig(
            bind_host="0.0.0.0",
            bind_port=8765,
            allowed_origins=("http://127.0.0.1:8765",),
            request_limits={"max_body_bytes": 65536},
            protocol_versions=("2025-11-25",),
        )
    assert raised.value.code == "bind_host_not_loopback"

    with pytest.raises(ServiceConfigError) as wildcard:
        ServiceConfig(
            bind_host="*",
            bind_port=8765,
            allowed_origins=("http://127.0.0.1:8765",),
            request_limits={"max_body_bytes": 65536},
            protocol_versions=("2025-11-25",),
        )
    assert wildcard.value.code == "bind_host_not_loopback"


def test_service_config_accepts_loopback_only() -> None:
    from evidence_handoff_runtime.service import ServiceConfig

    config = ServiceConfig(
        bind_host="127.0.0.1",
        bind_port=8765,
        allowed_origins=("http://127.0.0.1:8765",),
        request_limits={"max_body_bytes": 65536},
        protocol_versions=("2025-11-25",),
    )
    assert config.bind_host == "127.0.0.1"
    assert config.protocol_versions == ("2025-11-25",)


def test_transport_rejects_dns_rebinding_host_header() -> None:
    from evidence_handoff_runtime.transport import TransportDecision, evaluate_http_preamble

    decision = evaluate_http_preamble(
        bind_host="127.0.0.1",
        bind_port=8765,
        allowed_origins=frozenset({"http://127.0.0.1:8765"}),
        headers={"host": "evil.example", "origin": "http://127.0.0.1:8765"},
        content_length=10,
        max_body_bytes=65536,
        auth_present=True,
    )
    assert isinstance(decision, TransportDecision)
    assert decision.allowed is False
    assert decision.http_status == 403
    assert decision.code == "host_header_rejected"


def test_transport_rejects_origin_not_on_exact_allowlist() -> None:
    from evidence_handoff_runtime.transport import evaluate_http_preamble

    decision = evaluate_http_preamble(
        bind_host="127.0.0.1",
        bind_port=8765,
        allowed_origins=frozenset({"http://127.0.0.1:8765"}),
        headers={"host": "127.0.0.1:8765", "origin": "http://evil.example"},
        content_length=10,
        max_body_bytes=65536,
        auth_present=True,
    )
    assert decision.allowed is False
    assert decision.http_status == 403
    assert decision.code == "origin_rejected"


def test_transport_enforces_request_limits_before_parse() -> None:
    from evidence_handoff_runtime.transport import evaluate_http_preamble

    decision = evaluate_http_preamble(
        bind_host="127.0.0.1",
        bind_port=8765,
        allowed_origins=frozenset({"http://127.0.0.1:8765"}),
        headers={"host": "127.0.0.1:8765", "origin": "http://127.0.0.1:8765"},
        content_length=1024 * 1024,
        max_body_bytes=65536,
        auth_present=True,
    )
    assert decision.allowed is False
    assert decision.http_status == 413
    assert decision.code == "request_too_large"
    assert decision.reached_mcp_parse is False


def test_transport_rejects_unsupported_protocol_version_header() -> None:
    from evidence_handoff_runtime.transport import evaluate_http_preamble

    decision = evaluate_http_preamble(
        bind_host="127.0.0.1",
        bind_port=8765,
        allowed_origins=frozenset({"http://127.0.0.1:8765"}),
        headers={
            "host": "127.0.0.1:8765",
            "origin": "http://127.0.0.1:8765",
            "mcp-protocol-version": "1999-01-01",
        },
        content_length=10,
        max_body_bytes=65536,
        auth_present=True,
        allowed_protocol_versions=frozenset({"2025-11-25"}),
    )
    assert decision.allowed is False
    assert decision.code == "unsupported_protocol_version"
    assert decision.reached_mcp_parse is False


def test_no_legacy_http_sse_fallback_route() -> None:
    from evidence_handoff_runtime.transport import LEGACY_SSE_PATHS, is_legacy_sse_path

    for path in ("/sse", "/messages", "/mcp/sse"):
        assert is_legacy_sse_path(path) is True
    assert "/sse" in LEGACY_SSE_PATHS
    assert is_legacy_sse_path("/mcp") is False


def test_preparse_auth_gate_stub_runs_before_mcp_parse_and_is_named() -> None:
    """Structural only: stub exists at Task-6 replacement point; does not prove auth."""
    from evidence_handoff_runtime.transport import (
        PreParseAuthGateStub,
        evaluate_http_preamble,
    )

    assert PreParseAuthGateStub.__name__ == "PreParseAuthGateStub"
    assert PreParseAuthGateStub.__doc__ is not None
    assert "stub" in PreParseAuthGateStub.__doc__.lower()
    assert "task 6" in PreParseAuthGateStub.__doc__.lower()

    decision = evaluate_http_preamble(
        bind_host="127.0.0.1",
        bind_port=8765,
        allowed_origins=frozenset({"http://127.0.0.1:8765"}),
        headers={"host": "127.0.0.1:8765"},
        content_length=10,
        max_body_bytes=65536,
        auth_present=False,
    )
    assert decision.allowed is False
    assert decision.code == "auth_gate_rejected"
    assert decision.reached_mcp_parse is False
    assert decision.auth_gate_class == "PreParseAuthGateStub"


def test_mcp_tool_surface_excludes_forbidden_capabilities() -> None:
    from evidence_handoff_runtime.service import ALLOWED_TOOL_NAMES, list_advertised_tools

    tools = list_advertised_tools()
    names = {tool["name"] for tool in tools}
    assert names == ALLOWED_TOOL_NAMES
    assert names == ALLOWED_MCP_TOOL_NAMES
    joined = " ".join(sorted(names)).lower()
    for forbidden in FORBIDDEN_MCP_TOOL_SUBSTRINGS:
        assert forbidden not in joined


def test_service_cli_rejects_password_on_argv(tmp_path: Path) -> None:
    """Watch item: credential-bearing values must not appear as argv flags (Task 2 lesson)."""
    from evidence_handoff_runtime import service_cli

    parser = service_cli.build_parser()
    option_strings = {opt for action in parser._actions for opt in action.option_strings}
    assert "--admin-password" not in option_strings
    assert "--password" not in option_strings
    assert "--admin-password-file" in option_strings or "--credential-file" in option_strings
    # Bind comes only from runtime file — unused CLI bind flags removed.
    assert "--bind-host" not in option_strings
    assert "--bind-port" not in option_strings


def test_health_status_catches_integrity_latch_corrupt(tmp_path: Path) -> None:
    """Watch item: corrupt latch must not become an unhandled exception in status/health."""
    from evidence_handoff_runtime.integrity import IntegrityLatch, IntegrityLatchError
    from evidence_handoff_runtime.service import LedgerService, ServiceConfig

    control = tmp_path / "control"
    control.mkdir()
    (control / "integrity_latch.json").write_text("{not-json", encoding="utf-8")
    config = ServiceConfig(
        bind_host="127.0.0.1",
        bind_port=8765,
        allowed_origins=("http://127.0.0.1:8765",),
        request_limits={"max_body_bytes": 65536},
        protocol_versions=("2025-11-25",),
    )

    class _Store:
        pass

    class _Bootstrap:
        control_root = control

    report = LedgerService.health_from_control_root(config, _Bootstrap(), store=_Store())
    assert report.ready is False
    assert report.code == "integrity_latch_corrupt"
    with pytest.raises(IntegrityLatchError):
        IntegrityLatch(control_root=control).load()


def test_service_runtime_manifest_never_persists_store_password(tmp_path: Path) -> None:
    """Task 5 must not write Postgres passwords into service_runtime.json (design 263-265)."""
    import socket

    from evidence_handoff_runtime.service import LedgerService, ServiceConfig

    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    canary = "CANARY-PASSWORD-MUST-NOT-PERSIST-9f3a"
    control = tmp_path / "control"
    control.mkdir()
    port = _free_port()
    config = ServiceConfig(
        bind_host="127.0.0.1",
        bind_port=port,
        allowed_origins=(f"http://127.0.0.1:{port}",),
        request_limits={"max_body_bytes": 65536},
        protocol_versions=("2025-11-25",),
    )

    class _Store:
        _conninfo = f"host=127.0.0.1 port=1 user=handoff password={canary} dbname=postgres"
        ledger_instance_id = "inst-canary"

    class _Bootstrap:
        control_root = control

    running = LedgerService.start(config, _Store(), _Bootstrap())
    try:
        runtime_path = control / "service_runtime.json"
        assert runtime_path.is_file()
        text = runtime_path.read_text(encoding="utf-8")
        assert canary not in text
        assert "password=" not in text.lower()
        assert "conninfo" not in text
        running.wait_ready(timeout_seconds=15.0)
        # Still absent while the service process is alive.
        assert canary not in runtime_path.read_text(encoding="utf-8")
    finally:
        running.stop()
    # Manifest must be removed on stop (store.env pattern: no leftover bootstrap file).
    assert not (control / "service_runtime.json").exists()
