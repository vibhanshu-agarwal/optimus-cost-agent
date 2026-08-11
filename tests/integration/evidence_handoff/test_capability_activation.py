"""Live capability / activation / delivery-view evidence (Task 9).

Real Docker Desktop PostgreSQL + LedgerService + official MCP client.
"""

from __future__ import annotations

import json
import secrets
import socket
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest

pytestmark = pytest.mark.requires_evidence_handoff_service

EXPECTED_PROTOCOL = "2025-11-25"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _abs(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _is_tool_error(result: object) -> bool:
    return bool(getattr(result, "is_error", None) or getattr(result, "isError", None))


def _tool_payload(result: object) -> str:
    chunks: list[str] = []
    content = getattr(result, "content", None) or ()
    for item in content:
        text = getattr(item, "text", None)
        if text:
            chunks.append(str(text))
    structured = getattr(result, "structuredContent", None) or getattr(
        result, "structured_content", None
    )
    if structured is not None:
        chunks.append(json.dumps(structured, default=str))
    chunks.append(repr(result))
    return "\n".join(chunks)


def _structured(result: object) -> dict:
    structured = getattr(result, "structuredContent", None) or getattr(
        result, "structured_content", None
    )
    if isinstance(structured, dict):
        return structured
    for item in getattr(result, "content", ()) or ():
        text = getattr(item, "text", None)
        if text and str(text).strip().startswith("{"):
            return json.loads(str(text))
    raise AssertionError(f"no structured payload: {_tool_payload(result)}")


@pytest.fixture()
def capability_ledger(tmp_path: Path):
    from evidence_handoff_runtime.auth import CredentialIssuer, Enrollment
    from evidence_handoff_runtime.config import FeatureConfig, LifecycleBootstrapContext
    from evidence_handoff_runtime.lifecycle import LifecycleError, LifecycleManager
    from evidence_handoff_runtime.migrations import apply_migrations
    from evidence_handoff_runtime.service import LedgerService, ServiceConfig
    from evidence_handoff_runtime.store import PostgresLedgerStore
    from optimus_security.sanitization import PathAliasRule

    password = f"svc-{secrets.token_hex(8)}"
    signing_key = secrets.token_bytes(32)
    capture = _abs(tmp_path, "capture")
    control_root = _abs(tmp_path, "control")
    service = None
    manager = None
    harness = None
    last_error: Exception | None = None
    try:
        for _attempt in range(5):
            pg_port = _free_port()
            svc_port = _free_port()
            suffix = uuid.uuid4().hex[:8]
            config = FeatureConfig.from_mapping(
                {
                    "enabled": "true",
                    "backend_id": "docker",
                    "bind_host": "127.0.0.1",
                    "postgres_port": str(pg_port),
                    "container_name": f"evidence-handoff-cap-{suffix}",
                    "image": "postgres:16-alpine",
                    "volume_name": f"evidence-handoff-cap-data-{suffix}",
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
                enrollment_principal_ids=(
                    "principal-reviewer",
                    "principal-implementer",
                    "principal-codex",
                ),
                capabilities=("review-ruling",),
                lock_path=tmp_path / f"lifecycle-{suffix}.lock",
                control_root=control_root,
                store_admin_user="handoff",
                store_admin_password=password,
            )
            manager = LifecycleManager(config, bootstrap)
            conninfo = (
                f"host=127.0.0.1 port={pg_port} user=handoff password={password} "
                "dbname=postgres connect_timeout=5"
            )
            try:
                started = manager.start()
                if not started.running:
                    raise RuntimeError("lifecycle_not_running")
                assert started.backend_id == "docker"
                for _probe in range(30):
                    try:
                        with psycopg.connect(conninfo) as conn:
                            conn.execute("SELECT 1")
                        break
                    except Exception:
                        time.sleep(0.5)
                else:
                    raise RuntimeError("postgres_not_ready")
                instance_id = started.ledger_instance_id
                assert instance_id
                apply_migrations(conninfo)
                store = PostgresLedgerStore(
                    conninfo=conninfo,
                    ledger_instance_id=instance_id,
                    control_root=control_root,
                )
                store.ensure_instance_metadata()
                store.current_status()
                enrollments = {
                    (instance_id, "principal-reviewer"): Enrollment(
                        principal_id="principal-reviewer",
                        agent_id="reviewer-1",
                        caller_role="reviewer",
                        scopes=frozenset({"ledger.write", "ledger.read", "ledger.admin"}),
                        instance_id=instance_id,
                    ),
                    (instance_id, "principal-implementer"): Enrollment(
                        principal_id="principal-implementer",
                        agent_id="implementer-1",
                        caller_role="implementer",
                        scopes=frozenset({"ledger.write", "ledger.read"}),
                        instance_id=instance_id,
                    ),
                    (instance_id, "principal-codex"): Enrollment(
                        principal_id="principal-codex",
                        agent_id="codex-1",
                        caller_role="implementer",
                        scopes=frozenset({"ledger.write", "ledger.read"}),
                        instance_id=instance_id,
                    ),
                }
                issuer = CredentialIssuer(
                    signing_key=signing_key,
                    issuer="evidence-handoff-runtime",
                    audience="evidence-handoff",
                    enrollments=enrollments,
                    now=lambda: datetime.now(tz=UTC),
                    default_ttl=timedelta(minutes=10),
                )
                # No static retired_agent_ids — Task 9 retirement must populate that path.
                service = LedgerService.start(
                    ServiceConfig(
                        bind_host="127.0.0.1",
                        bind_port=svc_port,
                        allowed_origins=(f"http://127.0.0.1:{svc_port}",),
                        request_limits={"max_body_bytes": 65536},
                        protocol_versions=(EXPECTED_PROTOCOL,),
                    ),
                    store,
                    bootstrap,
                    auth={
                        "signing_key": signing_key,
                        "issuer": "evidence-handoff-runtime",
                        "audience": "evidence-handoff",
                        "enrollments": enrollments,
                    },
                )
                service.wait_ready(timeout_seconds=30.0)
                for _probe in range(20):
                    try:
                        store.current_status()
                        break
                    except Exception:
                        time.sleep(0.5)
                else:
                    raise RuntimeError("store_unreachable_after_service_start")
                harness = {
                    "endpoint": service.endpoint,
                    "store": store,
                    "issuer": issuer,
                    "enrollments": enrollments,
                    "instance_id": instance_id,
                    "origin": f"http://127.0.0.1:{svc_port}",
                    "service": service,
                    "conninfo": conninfo,
                }
                break
            except Exception as exc:
                last_error = exc
                if service is not None:
                    try:
                        service.stop()
                    except Exception:
                        pass
                    service = None
                if manager is not None:
                    try:
                        manager.stop()
                    except Exception:
                        pass
                    try:
                        manager.destroy_for_test_cleanup()
                    except Exception:
                        pass
                time.sleep(1.0)
        assert harness is not None, f"capability_ledger_start_failed: {last_error!r}"
        yield harness
    finally:
        if service is not None:
            service.stop()
        if manager is not None:
            manager.stop()
            try:
                manager.destroy_for_test_cleanup()
            except LifecycleError:
                pass


async def _mcp_call_tool(
    endpoint: str,
    *,
    origin: str,
    authorization: str,
    session_id: str | None,
    tool: str,
    arguments: dict,
):
    import httpx2
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    headers = {
        "Origin": origin,
        "Authorization": authorization,
        "MCP-Protocol-Version": EXPECTED_PROTOCOL,
    }
    if session_id:
        headers["MCP-Session-Id"] = session_id

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
            get_session_id = streams[2] if isinstance(streams, tuple) and len(streams) > 2 else None
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                bound = get_session_id() if callable(get_session_id) else session_id
                result = await session.call_tool(tool, arguments)
                return result, bound


@pytest.mark.asyncio
async def test_activation_blocked_until_all_active_readers_report_support_live(
    capability_ledger,
) -> None:
    harness = capability_ledger
    reviewer = harness["issuer"].issue(
        instance_id=harness["instance_id"],
        enrollment=harness["enrollments"][(harness["instance_id"], "principal-reviewer")],
    )
    implementer = harness["issuer"].issue(
        instance_id=harness["instance_id"],
        enrollment=harness["enrollments"][(harness["instance_id"], "principal-implementer")],
    )
    codex = harness["issuer"].issue(
        instance_id=harness["instance_id"],
        enrollment=harness["enrollments"][(harness["instance_id"], "principal-codex")],
    )

    # All enrolled readers must report; leave codex without handoff.v1 so activation refuses.
    for token, schemas in (
        (reviewer, ["review-ruling.v1", "handoff.v1"]),
        (implementer, ["review-ruling.v1", "handoff.v1"]),
        (codex, ["review-ruling.v1"]),
    ):
        reported, _ = await _mcp_call_tool(
            harness["endpoint"],
            origin=harness["origin"],
            authorization=f"Bearer {token}",
            session_id=None,
            tool="ledger.capabilities_status",
            arguments={"supported_schemas": schemas, "action": "report"},
        )
        assert _is_tool_error(reported) is False, _tool_payload(reported)
        body = _structured(reported)
        # Must not be the Task 5 stub.
        assert body.get("tool") != "ledger.capabilities_status"
        assert "supported_schemas" in body or "reported_at" in body

    blocked, _ = await _mcp_call_tool(
        harness["endpoint"],
        origin=harness["origin"],
        authorization=f"Bearer {reviewer}",
        session_id=None,
        tool="ledger.capabilities_status",
        arguments={"schema_id": "handoff.v1", "action": "activate_writer"},
    )
    assert _is_tool_error(blocked) is True
    assert any(
        part in _tool_payload(blocked).lower()
        for part in ("activation_blocked", "readers_not_ready", "stale", "missing")
    )

    # Codex catches up — activation may proceed.
    caught_up, _ = await _mcp_call_tool(
        harness["endpoint"],
        origin=harness["origin"],
        authorization=f"Bearer {codex}",
        session_id=None,
        tool="ledger.capabilities_status",
        arguments={
            "supported_schemas": ["review-ruling.v1", "handoff.v1"],
            "action": "report",
        },
    )
    assert _is_tool_error(caught_up) is False, _tool_payload(caught_up)

    activated, _ = await _mcp_call_tool(
        harness["endpoint"],
        origin=harness["origin"],
        authorization=f"Bearer {reviewer}",
        session_id=None,
        tool="ledger.capabilities_status",
        arguments={"schema_id": "handoff.v1", "action": "activate_writer"},
    )
    assert _is_tool_error(activated) is False, _tool_payload(activated)
    status = _structured(activated)
    assert status.get("writer_active") is True or status.get("schema_id") == "handoff.v1"


@pytest.mark.asyncio
async def test_non_admin_cannot_retire_or_activate_writer_live(capability_ledger) -> None:
    """Implementer has ledger.read/write but not ledger.admin — admin actions must fail."""
    harness = capability_ledger
    implementer = harness["issuer"].issue(
        instance_id=harness["instance_id"],
        enrollment=harness["enrollments"][(harness["instance_id"], "principal-implementer")],
    )
    denied_retire, _ = await _mcp_call_tool(
        harness["endpoint"],
        origin=harness["origin"],
        authorization=f"Bearer {implementer}",
        session_id=None,
        tool="ledger.capabilities_status",
        arguments={"action": "retire_principal", "principal_id": "principal-codex"},
    )
    assert _is_tool_error(denied_retire) is True
    retire_payload = _tool_payload(denied_retire).lower()
    assert any(
        part in retire_payload
        for part in ("admin_required", "scope_not_permitted", "role_not_permitted")
    ), retire_payload

    denied_activate, _ = await _mcp_call_tool(
        harness["endpoint"],
        origin=harness["origin"],
        authorization=f"Bearer {implementer}",
        session_id=None,
        tool="ledger.capabilities_status",
        arguments={"schema_id": "handoff.v1", "action": "activate_writer"},
    )
    assert _is_tool_error(denied_activate) is True
    activate_payload = _tool_payload(denied_activate).lower()
    assert any(
        part in activate_payload
        for part in ("admin_required", "scope_not_permitted", "role_not_permitted")
    ), activate_payload


@pytest.mark.asyncio
async def test_retire_principal_feeds_retired_recipient_rejection_live(capability_ledger) -> None:
    harness = capability_ledger
    reviewer = harness["issuer"].issue(
        instance_id=harness["instance_id"],
        enrollment=harness["enrollments"][(harness["instance_id"], "principal-reviewer")],
    )
    # Retire codex principal via admin capability surface.
    retired, _ = await _mcp_call_tool(
        harness["endpoint"],
        origin=harness["origin"],
        authorization=f"Bearer {reviewer}",
        session_id=None,
        tool="ledger.capabilities_status",
        arguments={"action": "retire_principal", "principal_id": "principal-codex"},
    )
    assert _is_tool_error(retired) is False, _tool_payload(retired)
    body = _structured(retired)
    assert body.get("retired") is True or "retired" in json.dumps(body).lower()

    before = harness["store"].current_status()
    denied, _ = await _mcp_call_tool(
        harness["endpoint"],
        origin=harness["origin"],
        authorization=f"Bearer {reviewer}",
        session_id=None,
        tool="ledger.review_ruling_append",
        arguments={
            "context_id": "ctx-retire-live",
            "recipient_agent_ids": ["codex-1"],
            "message_text": "must not append to retired recipient",
            "idempotency_key": f"idem-retire-{uuid.uuid4().hex[:8]}",
            "schema_id": "review-ruling.v1",
        },
    )
    assert _is_tool_error(denied) is True
    assert "retired_recipient" in _tool_payload(denied).lower()
    after = harness["store"].current_status()
    assert (after.last_committed, after.last_content_sha256) == (
        before.last_committed,
        before.last_content_sha256,
    )


@pytest.mark.asyncio
async def test_delivery_status_facts_only_and_warning_delivery_live(capability_ledger) -> None:
    harness = capability_ledger
    reviewer = harness["issuer"].issue(
        instance_id=harness["instance_id"],
        enrollment=harness["enrollments"][(harness["instance_id"], "principal-reviewer")],
    )
    status, _ = await _mcp_call_tool(
        harness["endpoint"],
        origin=harness["origin"],
        authorization=f"Bearer {reviewer}",
        session_id=None,
        tool="ledger.delivery_status",
        arguments={},
    )
    assert _is_tool_error(status) is False, _tool_payload(status)
    body = _structured(status)
    # Must not be the Task 5 stub.
    assert body.get("tool") != "ledger.delivery_status"
    blob = json.dumps(body).lower()
    for forbidden in ("online", "dead", "healthy", "is_alive", "process_status"):
        assert forbidden not in blob
    # Content-free factual rows for registered readers.
    rows = body.get("readers") or body.get("views") or body.get("delivery_views")
    assert rows is not None and len(rows) >= 1
    # Warning fact uses delivered / not_yet_requested vocabulary when present.
    serialized = json.dumps(rows)
    assert "not_yet_requested" in serialized or "warning_delivery" in serialized.lower()


@pytest.mark.asyncio
async def test_unsupported_schema_whole_query_no_token_live(capability_ledger) -> None:
    harness = capability_ledger
    reviewer = harness["issuer"].issue(
        instance_id=harness["instance_id"],
        enrollment=harness["enrollments"][(harness["instance_id"], "principal-reviewer")],
    )
    implementer = harness["issuer"].issue(
        instance_id=harness["instance_id"],
        enrollment=harness["enrollments"][(harness["instance_id"], "principal-implementer")],
    )
    # Append review-ruling (active writer). Delivery with only an unrelated schema set fails wholly.
    ok, _ = await _mcp_call_tool(
        harness["endpoint"],
        origin=harness["origin"],
        authorization=f"Bearer {reviewer}",
        session_id=None,
        tool="ledger.review_ruling_append",
        arguments={
            "context_id": "ctx-unsup",
            "recipient_agent_ids": ["implementer-1"],
            "message_text": "visible ruling",
            "idempotency_key": f"idem-unsup-{uuid.uuid4().hex[:8]}",
            "schema_id": "review-ruling.v1",
        },
    )
    assert _is_tool_error(ok) is False, _tool_payload(ok)

    denied, _ = await _mcp_call_tool(
        harness["endpoint"],
        origin=harness["origin"],
        authorization=f"Bearer {implementer}",
        session_id=None,
        tool="ledger.delivery_read",
        arguments={"cursor": 0, "supported_schemas": ["handoff.v1"]},
    )
    assert _is_tool_error(denied) is True
    assert "unsupported_entry_schema" in _tool_payload(denied).lower()
