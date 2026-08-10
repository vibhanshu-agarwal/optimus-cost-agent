"""Live authenticated service evidence (Task 6).

Real Docker Desktop PostgreSQL + real LedgerService subprocess + official MCP client.
Reviewer success must reach a real append; rejections leave counter/head unchanged.
"""

from __future__ import annotations

import json
import secrets
import socket
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

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


@pytest.fixture()
def authenticated_ledger(tmp_path: Path):
    """Start real store + service wired for Task 6 auth/session/policy."""
    from evidence_handoff_runtime.auth import CredentialIssuer, Enrollment
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
    signing_key = secrets.token_bytes(32)
    capture = _abs(tmp_path, "capture")
    control_root = _abs(tmp_path, "control")
    config = FeatureConfig.from_mapping(
        {
            "enabled": "true",
            "backend_id": "docker",
            "bind_host": "127.0.0.1",
            "postgres_port": str(pg_port),
            "container_name": f"evidence-handoff-auth-{suffix}",
            "image": "postgres:16-alpine",
            "volume_name": f"evidence-handoff-auth-data-{suffix}",
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
        enrollment_principal_ids=("principal-reviewer", "principal-implementer"),
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
            except Exception:
                pass
        assert started is not None and started.running is True
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
        }
        issuer = CredentialIssuer(
            signing_key=signing_key,
            issuer="evidence-handoff-runtime",
            audience="evidence-handoff",
            enrollments=enrollments,
            now=lambda: datetime.now(tz=UTC),
            default_ttl=timedelta(minutes=10),
        )
        service_config = ServiceConfig(
            bind_host="127.0.0.1",
            bind_port=svc_port,
            allowed_origins=(f"http://127.0.0.1:{svc_port}",),
            request_limits={"max_body_bytes": 65536},
            protocol_versions=(EXPECTED_PROTOCOL,),
        )
        # Task 6: start must accept auth material without persisting raw tokens/keys.
        service = LedgerService.start(
            service_config,
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
        import time

        for _probe in range(20):
            try:
                store.current_status()
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError("store_unreachable_after_service_start")
        yield {
            "endpoint": service.endpoint,
            "store": store,
            "issuer": issuer,
            "enrollments": enrollments,
            "instance_id": instance_id,
            "origin": f"http://127.0.0.1:{svc_port}",
            "signing_key": signing_key,
            "password": password,
            "control_root": control_root,
            "service": service,
            "stderr_path": control_root / "service.stderr.log",
        }
    finally:
        if service is not None:
            service.stop()
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
    """Drive the official MCP Streamable HTTP client (no project-authored client)."""
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
                try:
                    result = await session.call_tool(tool, arguments)
                except Exception as exc:
                    detail = getattr(exc, "data", None) or getattr(exc, "message", None) or repr(exc)
                    code = getattr(exc, "code", None)
                    raise AssertionError(
                        f"call_tool failed: {type(exc).__name__}: code={code!r} detail={detail!r}"
                    ) from exc
                return result, bound


@pytest.mark.asyncio
async def test_reviewer_append_success_and_implementer_rejection_live(authenticated_ledger) -> None:
    from evidence_handoff_runtime.auth import AuthError, CredentialValidator

    harness = authenticated_ledger
    store = harness["store"]
    issuer = harness["issuer"]
    before = store.current_status()
    assert before.last_committed == 0

    reviewer_token = issuer.issue(
        instance_id=harness["instance_id"],
        enrollment=harness["enrollments"][(harness["instance_id"], "principal-reviewer")],
    )
    implementer_token = issuer.issue(
        instance_id=harness["instance_id"],
        enrollment=harness["enrollments"][(harness["instance_id"], "principal-implementer")],
    )

    def _is_tool_error(result: object) -> bool:
        return bool(getattr(result, "is_error", None) or getattr(result, "isError", None))

    try:
        ok, _session_id = await _mcp_call_tool(
            harness["endpoint"],
            origin=harness["origin"],
            authorization=f"Bearer {reviewer_token}",
            session_id=None,
            tool="ledger.review_ruling_append",
            arguments={
                "context_id": "ctx-live-1",
                "recipient_agent_ids": ["implementer-1"],
                "message_text": "live reviewer ruling",
                "idempotency_key": "idem-live-1",
                "schema_id": "review-ruling.v1",
            },
        )
    except Exception:
        stderr_path = harness.get("stderr_path")
        if stderr_path is not None and Path(stderr_path).is_file():
            print(Path(stderr_path).read_text(encoding="utf-8", errors="replace")[-8000:])
        raise
    assert _is_tool_error(ok) is False, getattr(ok, "content", ok)

    denied, _ = await _mcp_call_tool(
        harness["endpoint"],
        origin=harness["origin"],
        authorization=f"Bearer {implementer_token}",
        session_id=None,
        tool="ledger.review_ruling_append",
        arguments={
            "context_id": "ctx-live-2",
            "recipient_agent_ids": ["implementer-1"],
            "message_text": "implementer must not append",
            "idempotency_key": "idem-live-2",
            "schema_id": "review-ruling.v1",
        },
    )
    assert _is_tool_error(denied) is True

    closed, _ = await _mcp_call_tool(
        harness["endpoint"],
        origin=harness["origin"],
        authorization=f"Bearer {reviewer_token}",
        session_id=None,
        tool="ledger.review_ruling_append",
        arguments={
            "context_id": "ctx-live-3",
            "recipient_agent_ids": ["implementer-1"],
            "message_text": "spoof identity",
            "idempotency_key": "idem-live-3",
            "schema_id": "review-ruling.v1",
            "agent_id": "spoofed-agent",
        },
    )
    assert _is_tool_error(closed) is True

    after = store.current_status()
    assert after.last_committed == 1
    assert after.last_content_sha256 is not None

    for path in harness["control_root"].rglob("*"):
        if path.is_file() and path.name != "service.stderr.log":
            text = path.read_text(encoding="utf-8", errors="replace")
            assert reviewer_token not in text
            assert implementer_token not in text
            assert harness["signing_key"].hex() not in text
            assert harness["password"] not in text

    envelope = store.read_verified_global_range(start=1, watermark=1).entries[0]
    blob = json.dumps(envelope.to_mapping())
    assert reviewer_token not in blob
    assert "spoofed-agent" not in blob
    assert envelope.principal_id == "principal-reviewer"
    assert envelope.caller_role == "reviewer"
    assert envelope.authority == "review-ruling"

    # Session ID is never an auth credential (CSPRNG lookalike; MCP transport owns wire session).
    lookalike_session = secrets.token_urlsafe(32)
    with pytest.raises(AuthError) as raised:
        CredentialValidator(
            signing_key=harness["signing_key"],
            expected_issuer="evidence-handoff-runtime",
            expected_audience="evidence-handoff",
            enrollments=harness["enrollments"],
            now=lambda: datetime.now(tz=UTC),
            revoked_token_ids=frozenset(),
            consumed_jti=set(),
        ).validate(
            header=f"Bearer {lookalike_session}",
            request={"ledger_instance_id": harness["instance_id"]},
        )
    assert raised.value.code == "session_not_credential"


@pytest.mark.asyncio
async def test_cross_principal_session_id_is_rejected_live(authenticated_ledger) -> None:
    """Live regression: Principal B must not adopt Principal A's MCP session id."""
    import httpx2

    harness = authenticated_ledger
    before = harness["store"].current_status()
    reviewer_token = harness["issuer"].issue(
        instance_id=harness["instance_id"],
        enrollment=harness["enrollments"][(harness["instance_id"], "principal-reviewer")],
    )
    implementer_token = harness["issuer"].issue(
        instance_id=harness["instance_id"],
        enrollment=harness["enrollments"][(harness["instance_id"], "principal-implementer")],
    )

    # Establish a real MCP transport session under the reviewer credential.
    async with httpx2.AsyncClient(
        headers={
            "Origin": harness["origin"],
            "Authorization": f"Bearer {reviewer_token}",
            "MCP-Protocol-Version": EXPECTED_PROTOCOL,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        follow_redirects=False,
        trust_env=False,
        timeout=httpx2.Timeout(30.0),
    ) as client:
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": EXPECTED_PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": "hijack-probe", "version": "0.0.1"},
            },
        }
        response = await client.post(harness["endpoint"], json=init_payload)
        assert response.status_code in {200, 202}
        victim_session = response.headers.get("mcp-session-id")
        assert victim_session

        # Present victim session with a different principal's valid token.
        hijack = await client.post(
            harness["endpoint"],
            headers={
                "Origin": harness["origin"],
                "Authorization": f"Bearer {implementer_token}",
                "MCP-Protocol-Version": EXPECTED_PROTOCOL,
                "MCP-Session-Id": victim_session,
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "ledger.review_ruling_append",
                    "arguments": {
                        "context_id": "ctx-hijack",
                        "recipient_agent_ids": ["implementer-1"],
                        "message_text": "must not append",
                        "idempotency_key": "idem-hijack",
                        "schema_id": "review-ruling.v1",
                    },
                },
            },
        )

    assert hijack.status_code == 401
    body = hijack.text.lower()
    assert "session_principal_mismatch" in body or "session_expired_or_unknown" in body
    after = harness["store"].current_status()
    assert (after.last_committed, after.last_content_sha256) == (
        before.last_committed,
        before.last_content_sha256,
    )


@pytest.mark.asyncio
async def test_invalid_origin_rejected_before_authenticated_append(authenticated_ledger) -> None:
    import httpx2

    harness = authenticated_ledger
    before = harness["store"].current_status()
    token = harness["issuer"].issue(
        instance_id=harness["instance_id"],
        enrollment=harness["enrollments"][(harness["instance_id"], "principal-reviewer")],
    )

    async with httpx2.AsyncClient(
        follow_redirects=False,
        trust_env=False,
        timeout=httpx2.Timeout(10.0),
    ) as client:
        response = await client.post(
            harness["endpoint"],
            headers={
                "Host": f"127.0.0.1:{harness['service'].config.bind_port}",
                "Origin": "http://evil.example",
                "Authorization": f"Bearer {token}",
                "MCP-Protocol-Version": EXPECTED_PROTOCOL,
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            content=b"{}",
        )

    assert response.status_code == 403
    body = response.text
    assert "origin" in body.lower() or body == "origin_rejected"
    after = harness["store"].current_status()
    assert (after.last_committed, after.last_content_sha256) == (
        before.last_committed,
        before.last_content_sha256,
    )
    assert token not in body
