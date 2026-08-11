"""Real service subprocess + official MCP Streamable HTTP client evidence (Task 5).

Uses mcp.ClientSession and mcp.client.streamable_http.streamable_http_client only.
No project-authored MCP client. Authentication success is NOT claimed here (Task 6).
"""

from __future__ import annotations

import secrets
import socket
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.requires_evidence_handoff_service

EXPECTED_PROTOCOL = "2025-11-25"
ALLOWED_TOOLS = frozenset(
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


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _abs(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture()
def running_ledger_service(tmp_path: Path):
    """Start real Docker Desktop PostgreSQL + real LedgerService subprocess on loopback."""
    from evidence_handoff_runtime.config import FeatureConfig, LifecycleBootstrapContext
    from evidence_handoff_runtime.lifecycle import LifecycleError, LifecycleManager
    from evidence_handoff_runtime.migrations import apply_migrations
    from evidence_handoff_runtime.service import LedgerService, ServiceConfig
    from evidence_handoff_runtime.store import PostgresLedgerStore
    from optimus_security.sanitization import PathAliasRule

    pg_port = _free_port()
    svc_port = _free_port()
    suffix = uuid.uuid4().hex[:8]
    password = f"svc-{secrets.token_hex(8)}"
    capture = _abs(tmp_path, "capture")
    control_root = _abs(tmp_path, "control")
    config = FeatureConfig.from_mapping(
        {
            "enabled": "true",
            "backend_id": "docker",
            "bind_host": "127.0.0.1",
            "postgres_port": str(pg_port),
            "container_name": f"evidence-handoff-svc-{suffix}",
            "image": "postgres:16-alpine",
            "volume_name": f"evidence-handoff-svc-data-{suffix}",
        }
    )
    bootstrap = LifecycleBootstrapContext(
        service_secrets=("svc-secret-alpha",),
        identity_values=("operator@example.test",),
        path_aliases=(PathAliasRule(source_root=str(capture), alias="<temp>"),),
        temporary_capture_root=capture,
        staging_root=_abs(tmp_path, "staging"),
        quarantine_root=_abs(tmp_path, "quarantine"),
        forbidden_persistence_roots=(_abs(tmp_path, "forbidden"),),
        allowed_origins=(f"http://127.0.0.1:{svc_port}",),
        enrollment_principal_ids=("reviewer-1",),
        capabilities=("review-ruling",),
        lock_path=tmp_path / "lifecycle.lock",
        control_root=control_root,
        store_admin_user="handoff",
        store_admin_password=password,
    )
    manager = LifecycleManager(config, bootstrap)
    service = None
    try:
        started = None
        for _attempt in range(3):
            started = manager.start()
            if started.running:
                break
            try:
                manager.stop()
            except Exception:
                pass
            try:
                manager.destroy_for_test_cleanup()
            except LifecycleError:
                pass
            manager = LifecycleManager(config, bootstrap)
        assert started is not None and started.running is True, getattr(started, "summary_code", None)
        assert started.backend_id == "docker"
        instance_id = started.ledger_instance_id
        assert instance_id
        conninfo = (
            f"host=127.0.0.1 port={pg_port} user=handoff password={password} "
            "dbname=postgres connect_timeout=5"
        )
        apply_migrations(conninfo)
        store = PostgresLedgerStore(
            conninfo=conninfo,
            ledger_instance_id=instance_id,
            control_root=control_root,
        )
        store.ensure_instance_metadata()
        service_config = ServiceConfig(
            bind_host="127.0.0.1",
            bind_port=svc_port,
            allowed_origins=(f"http://127.0.0.1:{svc_port}",),
            request_limits={"max_body_bytes": 65536},
            protocol_versions=(EXPECTED_PROTOCOL,),
        )
        service = LedgerService.start(
            service_config, store, bootstrap, allow_unauthenticated_stub=True
        )
        service.wait_ready(timeout_seconds=30.0)
        yield {
            "service": service,
            "endpoint": service.endpoint,
            "origin": f"http://127.0.0.1:{svc_port}",
            "store": store,
            "manager": manager,
            "control_root": control_root,
        }
    finally:
        if service is not None:
            service.stop()
        try:
            manager.stop()
        except Exception:
            pass
        try:
            manager.destroy_for_test_cleanup()
        except LifecycleError:
            pass


@pytest.mark.asyncio
async def test_official_mcp_client_initializes_and_lists_only_allowed_tools(
    running_ledger_service,
) -> None:
    import httpx2
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    endpoint = running_ledger_service["endpoint"]
    origin = running_ledger_service["origin"]
    # Structural probe header only — not a real Task-6 credential proof.
    headers = {
        "Origin": origin,
        "Authorization": "Bearer task5-preparse-auth-gate-stub-probe",
    }
    async with httpx2.AsyncClient(
        headers=headers,
        follow_redirects=False,
        trust_env=False,
        timeout=httpx2.Timeout(30.0),
    ) as http_client:
        async with streamable_http_client(endpoint, http_client=http_client) as streams:
            if hasattr(streams, "read_stream"):
                read_stream, write_stream = streams.read_stream, streams.write_stream
            else:
                read_stream, write_stream = streams[0], streams[1]
            async with ClientSession(read_stream, write_stream) as session:
                init = await session.initialize()
                negotiated = getattr(init, "protocolVersion", None) or getattr(
                    init, "protocol_version", None
                )
                assert negotiated == EXPECTED_PROTOCOL
                listed = await session.list_tools()
                names = {tool.name for tool in listed.tools}
                assert names == ALLOWED_TOOLS


@pytest.mark.asyncio
async def test_official_client_sees_origin_rejection_before_session(
    running_ledger_service,
) -> None:
    import httpx2

    endpoint = running_ledger_service["endpoint"]
    async with httpx2.AsyncClient(
        headers={
            "Origin": "http://evil.example",
            "Authorization": "Bearer task5-preparse-auth-gate-stub-probe",
        },
        follow_redirects=False,
        trust_env=False,
        timeout=httpx2.Timeout(10.0),
    ) as client:
        response = await client.post(endpoint, content=b"{}")
    assert response.status_code == 403
    body = response.text.lower()
    assert "origin" in body or response.headers.get("x-evidence-handoff-code") == "origin_rejected"


def test_running_service_binds_loopback_only(running_ledger_service) -> None:
    endpoint = running_ledger_service["endpoint"]
    assert "127.0.0.1" in endpoint
    assert "0.0.0.0" not in endpoint
