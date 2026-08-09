"""Live delivery / cursor evidence (Task 8).

Real wslc PostgreSQL + LedgerService + official MCP client.
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
def delivery_ledger(tmp_path: Path):
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
                    "backend_id": "wslc",
                    "bind_host": "127.0.0.1",
                    "postgres_port": str(pg_port),
                    "container_name": f"evidence-handoff-delivery-{suffix}",
                    "image": "postgres:16-alpine",
                    "volume_name": f"evidence-handoff-delivery-data-{suffix}",
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
                    "principal-retired",
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
                        scopes=frozenset({"ledger.write", "ledger.read"}),
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
                    # Known but retired — must be enrolled so RED cannot false-pass
                    # as unknown_recipient before the retirement check exists.
                    (instance_id, "principal-retired"): Enrollment(
                        principal_id="principal-retired",
                        agent_id="retired-agent",
                        caller_role="implementer",
                        scopes=frozenset({"ledger.read"}),
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
                        # Task 8: minimal retirement set (no Task 9 admin API yet).
                        "retired_agent_ids": frozenset({"retired-agent"}),
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
        assert harness is not None, f"delivery_ledger_start_failed: {last_error!r}"
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
async def test_delivery_read_confirm_unread_and_redelivery_live(delivery_ledger) -> None:
    harness = delivery_ledger
    reviewer_token = harness["issuer"].issue(
        instance_id=harness["instance_id"],
        enrollment=harness["enrollments"][(harness["instance_id"], "principal-reviewer")],
    )
    implementer_token = harness["issuer"].issue(
        instance_id=harness["instance_id"],
        enrollment=harness["enrollments"][(harness["instance_id"], "principal-implementer")],
    )

    # Append two rulings: one visible only to codex, one to implementer.
    for args in (
        {
            "context_id": "ctx-del-1",
            "recipient_agent_ids": ["codex-1"],
            "message_text": "hidden from implementer",
            "idempotency_key": "idem-del-1",
            "schema_id": "review-ruling.v1",
        },
        {
            "context_id": "ctx-del-2",
            "recipient_agent_ids": ["implementer-1"],
            "message_text": "visible to implementer",
            "idempotency_key": "idem-del-2",
            "schema_id": "review-ruling.v1",
        },
    ):
        appended, _ = await _mcp_call_tool(
            harness["endpoint"],
            origin=harness["origin"],
            authorization=f"Bearer {reviewer_token}",
            session_id=None,
            tool="ledger.review_ruling_append",
            arguments=args,
        )
        assert _is_tool_error(appended) is False, _tool_payload(appended)

    read1, _ = await _mcp_call_tool(
        harness["endpoint"],
        origin=harness["origin"],
        authorization=f"Bearer {implementer_token}",
        session_id=None,
        tool="ledger.delivery_read",
        arguments={
            "cursor": 0,
            "supported_schemas": ["review-ruling.v1"],
        },
    )
    assert _is_tool_error(read1) is False, _tool_payload(read1)
    page1 = _structured(read1)
    assert "delivery_token" in page1 or "token_id" in page1
    entries = page1.get("entries") or ()
    assert len(entries) == 1
    blob = json.dumps(page1)
    assert "hidden from implementer" not in blob
    assert "codex-1" not in blob or page1.get("unread_count") == 1
    token_id = page1.get("delivery_token", {}).get("token_id") or page1.get("token_id")
    assert token_id

    # Lost confirmation → redelivery of the same visible entry.
    read2, _ = await _mcp_call_tool(
        harness["endpoint"],
        origin=harness["origin"],
        authorization=f"Bearer {implementer_token}",
        session_id=None,
        tool="ledger.delivery_read",
        arguments={"cursor": 0, "supported_schemas": ["review-ruling.v1"]},
    )
    assert _is_tool_error(read2) is False, _tool_payload(read2)
    page2 = _structured(read2)
    assert len(page2.get("entries") or ()) == 1

    confirm, _ = await _mcp_call_tool(
        harness["endpoint"],
        origin=harness["origin"],
        authorization=f"Bearer {implementer_token}",
        session_id=None,
        tool="ledger.delivery_confirm",
        arguments={"token_id": token_id},
    )
    assert _is_tool_error(confirm) is False, _tool_payload(confirm)
    status = _structured(confirm)
    assert int(status["confirmed_sequence"]) >= 2
    assert int(status["unread_count"]) == 0

    # Replay token must fail without cursor change.
    replay, _ = await _mcp_call_tool(
        harness["endpoint"],
        origin=harness["origin"],
        authorization=f"Bearer {implementer_token}",
        session_id=None,
        tool="ledger.delivery_confirm",
        arguments={"token_id": token_id},
    )
    assert _is_tool_error(replay) is True
    assert "token_replayed" in _tool_payload(replay).lower() or "replay" in _tool_payload(replay).lower()


@pytest.mark.asyncio
async def test_retired_wildcard_and_unknown_recipients_rejected_live(delivery_ledger) -> None:
    harness = delivery_ledger
    reviewer_token = harness["issuer"].issue(
        instance_id=harness["instance_id"],
        enrollment=harness["enrollments"][(harness["instance_id"], "principal-reviewer")],
    )
    before = harness["store"].current_status()
    # Exact codes — do not accept unknown_recipient for retired/wildcard/aliases
    # (those shapes must get dedicated Task 8 codes; retired-agent is enrolled).
    cases = [
        (["retired-agent"], "retired_recipient"),
        (["*"], "wildcard_recipient"),
        (["role:reviewer"], "role_alias_recipient"),
        (["context:ctx-x"], "context_alias_recipient"),
        (["not-enrolled-agent"], "unknown_recipient"),
    ]
    for recipients, code in cases:
        denied, _ = await _mcp_call_tool(
            harness["endpoint"],
            origin=harness["origin"],
            authorization=f"Bearer {reviewer_token}",
            session_id=None,
            tool="ledger.review_ruling_append",
            arguments={
                "context_id": f"ctx-{code}",
                "recipient_agent_ids": recipients,
                "message_text": "must not append",
                "idempotency_key": f"idem-{code}-{uuid.uuid4().hex[:8]}",
                "schema_id": "review-ruling.v1",
            },
        )
        assert _is_tool_error(denied) is True, recipients
        payload = _tool_payload(denied).lower()
        assert code in payload, (recipients, code, payload)
    after = harness["store"].current_status()
    assert (after.last_committed, after.last_content_sha256) == (
        before.last_committed,
        before.last_content_sha256,
    )


@pytest.mark.asyncio
async def test_hidden_commitment_not_disclosed_live(delivery_ledger) -> None:
    harness = delivery_ledger
    reviewer_token = harness["issuer"].issue(
        instance_id=harness["instance_id"],
        enrollment=harness["enrollments"][(harness["instance_id"], "principal-reviewer")],
    )
    implementer_token = harness["issuer"].issue(
        instance_id=harness["instance_id"],
        enrollment=harness["enrollments"][(harness["instance_id"], "principal-implementer")],
    )
    ok, _ = await _mcp_call_tool(
        harness["endpoint"],
        origin=harness["origin"],
        authorization=f"Bearer {reviewer_token}",
        session_id=None,
        tool="ledger.review_ruling_append",
        arguments={
            "context_id": "ctx-secret-audience",
            "recipient_agent_ids": ["codex-1"],
            "message_text": "secret-audience-body-canary",
            "idempotency_key": "idem-secret-audience",
            "schema_id": "review-ruling.v1",
        },
    )
    assert _is_tool_error(ok) is False, _tool_payload(ok)

    read, _ = await _mcp_call_tool(
        harness["endpoint"],
        origin=harness["origin"],
        authorization=f"Bearer {implementer_token}",
        session_id=None,
        tool="ledger.delivery_read",
        arguments={"cursor": 0, "supported_schemas": ["review-ruling.v1"]},
    )
    assert _is_tool_error(read) is False, _tool_payload(read)
    page = _structured(read)
    # Require a real DeliveryPage shape so the Task 5 stub
    # ({"status":"ok","tool":"ledger.delivery_read"}) cannot false-pass.
    assert "delivery_token" in page or "token_id" in page, page
    token = page.get("delivery_token") or {}
    assert token.get("token_id") or page.get("token_id")
    payload = json.dumps(page)
    assert "secret-audience-body-canary" not in payload
    assert len(page.get("entries") or ()) == 0
    # Non-disclosure: no total/global/hidden counts for the invisible commitment.
    for forbidden_key in ("total_committed", "hidden_count", "global_entry_count", "all_sequences"):
        assert forbidden_key not in page
    assert int(page.get("unread_count", 0)) == 0
    assert "codex-1" not in payload
