"""Live redaction / review-ruling evidence (Task 7).

Real Docker Desktop PostgreSQL + LedgerService + official MCP client. Canaries must not
appear in rows, logs, errors, or MCP responses after success or failure.
"""

from __future__ import annotations

import base64
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
SECRET_CANARY = "live-redaction-secret-canary-7f2c"
PII_CANARY = "operator@example.test"
REQUEST_CRED_MARKER = "request-credential"  # token itself scanned via Bearer value


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


@pytest.fixture()
def redaction_ledger(tmp_path: Path):
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
                    "container_name": f"evidence-handoff-redact-{suffix}",
                    "image": "postgres:16-alpine",
                    "volume_name": f"evidence-handoff-redact-data-{suffix}",
                }
            )
            bootstrap = LifecycleBootstrapContext(
                service_secrets=(SECRET_CANARY, "svc-secret-alpha"),
                identity_values=(PII_CANARY,),
                path_aliases=(PathAliasRule(source_root=str(capture), alias="<temp>"),),
                temporary_capture_root=capture,
                staging_root=_abs(tmp_path, "staging"),
                quarantine_root=_abs(tmp_path, "quarantine"),
                forbidden_persistence_roots=(_abs(tmp_path, "forbidden"),),
                allowed_origins=(f"http://127.0.0.1:{svc_port}",),
                enrollment_principal_ids=("principal-reviewer", "principal-implementer"),
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
                # Re-check store after the service child attaches — Docker loopback port
                # forwarding can flap briefly around process start.
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
                    "signing_key": signing_key,
                    "password": password,
                    "control_root": control_root,
                    "service": service,
                    "capture": capture,
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
        assert harness is not None, f"redaction_ledger_start_failed: {last_error!r}"
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


def _scan_control_and_db(harness: dict, *canaries: str) -> None:
    import psycopg

    for path in harness["control_root"].rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for canary in canaries:
            assert canary not in text, f"canary leaked in {path.name}"
    with psycopg.connect(harness["conninfo"]) as conn:
        rows = conn.execute(
            "SELECT message_json::text, artifacts_json::text, content_sha256 "
            "FROM evidence_handoff_entries"
        ).fetchall()
    for row in rows:
        blob = "|".join("" if item is None else str(item) for item in row)
        for canary in canaries:
            assert canary not in blob


@pytest.mark.asyncio
async def test_reviewer_success_sanitizes_canaries_and_supports_read(redaction_ledger) -> None:
    harness = redaction_ledger
    store = harness["store"]
    before = store.current_status()
    assert before.last_committed == 0
    reviewer_token = harness["issuer"].issue(
        instance_id=harness["instance_id"],
        enrollment=harness["enrollments"][(harness["instance_id"], "principal-reviewer")],
    )
    leak_path = str(harness["capture"] / "nested" / "note.txt")
    ok, _ = await _mcp_call_tool(
        harness["endpoint"],
        origin=harness["origin"],
        authorization=f"Bearer {reviewer_token}",
        session_id=None,
        tool="ledger.review_ruling_append",
        arguments={
            "context_id": "ctx-redact-ok",
            "recipient_agent_ids": ["implementer-1"],
            "message": {
                "parts": [
                    {
                        "kind": "text",
                        "text": (
                            f"ruling mentions {SECRET_CANARY} and {PII_CANARY} "
                            f"path {leak_path}"
                        ),
                    }
                ]
            },
            "idempotency_key": "idem-redact-ok",
            "schema_id": "review-ruling.v1",
        },
    )
    assert _is_tool_error(ok) is False, _tool_payload(ok)
    payload = _tool_payload(ok)
    assert SECRET_CANARY not in payload
    assert PII_CANARY not in payload
    assert reviewer_token not in payload
    # Response shape: immutable IDs + digest only.
    structured = getattr(ok, "structuredContent", None) or getattr(ok, "structured_content", None)
    if structured is None:
        # Fall back to parsing text JSON if the transport returns text content.
        for item in getattr(ok, "content", ()) or ():
            text = getattr(item, "text", None)
            if text and text.strip().startswith("{"):
                structured = json.loads(text)
                break
    assert isinstance(structured, dict)
    assert set(structured) >= {
        "entry_id",
        "sequence",
        "ledger_instance_id",
        "content_sha256",
    }
    assert structured["sequence"] == 1
    assert structured["ledger_instance_id"] == harness["instance_id"]
    assert len(structured["content_sha256"]) == 64
    assert "message" not in structured

    read_result = None
    for _attempt in range(3):
        read_result, _ = await _mcp_call_tool(
            harness["endpoint"],
            origin=harness["origin"],
            authorization=f"Bearer {reviewer_token}",
            session_id=None,
            tool="ledger.review_ruling_read",
            arguments={"sequence": 1},
        )
        if not _is_tool_error(read_result):
            break
        payload = _tool_payload(read_result).lower()
        if not any(
            needle in payload
            for needle in ("connection failed", "connection abort", "connection timeout", "timeout expired")
        ):
            break
        time.sleep(1.0)
    assert read_result is not None
    assert _is_tool_error(read_result) is False, _tool_payload(read_result)
    read_payload = _tool_payload(read_result)
    assert SECRET_CANARY not in read_payload
    assert PII_CANARY not in read_payload
    assert "message" not in read_payload or SECRET_CANARY not in read_payload

    after = store.current_status()
    assert after.last_committed == 1
    envelope = store.read_verified_global_range(start=1, watermark=1).entries[0]
    blob = json.dumps(envelope.to_mapping())
    assert SECRET_CANARY not in blob
    assert PII_CANARY not in blob
    assert leak_path not in blob
    _scan_control_and_db(harness, SECRET_CANARY, PII_CANARY, reviewer_token, harness["password"])


@pytest.mark.asyncio
async def test_final_scan_failure_leaves_no_row_or_sequence(redaction_ledger) -> None:
    harness = redaction_ledger
    store = harness["store"]
    before = store.current_status()
    reviewer_token = harness["issuer"].issue(
        instance_id=harness["instance_id"],
        enrollment=harness["enrollments"][(harness["instance_id"], "principal-reviewer")],
    )
    encoded = base64.b64encode(SECRET_CANARY.encode("utf-8")).decode("ascii")
    denied, _ = await _mcp_call_tool(
        harness["endpoint"],
        origin=harness["origin"],
        authorization=f"Bearer {reviewer_token}",
        session_id=None,
        tool="ledger.review_ruling_append",
        arguments={
            "context_id": "ctx-final-scan",
            "recipient_agent_ids": ["implementer-1"],
            # message_text keeps the call on today's tool surface; final_scan_hit is Task 7.
            "message_text": f"token={encoded}",
            "idempotency_key": "idem-final-scan",
            "schema_id": "review-ruling.v1",
        },
    )
    assert _is_tool_error(denied) is True
    payload = _tool_payload(denied)
    assert SECRET_CANARY not in payload
    assert encoded not in payload or "final_scan" in payload.lower()
    after = store.current_status()
    assert (after.last_committed, after.last_content_sha256) == (
        before.last_committed,
        before.last_content_sha256,
    )
    _scan_control_and_db(harness, SECRET_CANARY, reviewer_token)


@pytest.mark.asyncio
async def test_implementer_client_authority_unknown_recipient_attestation_rejected(
    redaction_ledger,
) -> None:
    harness = redaction_ledger
    store = harness["store"]
    before = store.current_status()
    reviewer_token = harness["issuer"].issue(
        instance_id=harness["instance_id"],
        enrollment=harness["enrollments"][(harness["instance_id"], "principal-reviewer")],
    )
    implementer_token = harness["issuer"].issue(
        instance_id=harness["instance_id"],
        enrollment=harness["enrollments"][(harness["instance_id"], "principal-implementer")],
    )

    # Use current tool field surface (message_text) so rejections exercise policy, not
    # pydantic shape errors. Unknown-recipient is the Task 7-specific gate.
    cases = [
        (
            implementer_token,
            {
                "context_id": "ctx-impl",
                "recipient_agent_ids": ["implementer-1"],
                "message_text": "nope",
                "idempotency_key": "idem-impl",
                "schema_id": "review-ruling.v1",
            },
            ("role_not_permitted", "not_permitted", "role"),
        ),
        (
            reviewer_token,
            {
                "context_id": "ctx-auth",
                "recipient_agent_ids": ["implementer-1"],
                "message_text": "spoof",
                "idempotency_key": "idem-auth",
                "schema_id": "review-ruling.v1",
                "authority": "review-ruling",
            },
            ("closed_schema_field_rejected", "closed_schema"),
        ),
        (
            reviewer_token,
            {
                "context_id": "ctx-recip",
                "recipient_agent_ids": ["unknown-agent"],
                "message_text": "bad recipient",
                "idempotency_key": "idem-recip",
                "schema_id": "review-ruling.v1",
            },
            ("unknown_recipient",),
        ),
        (
            reviewer_token,
            {
                "context_id": "ctx-attest",
                "recipient_agent_ids": ["implementer-1"],
                "message_text": "attest",
                "idempotency_key": "idem-attest",
                "schema_id": "review-ruling.v1",
                "attestation": {"claim": "x"},
            },
            ("closed_schema_field_rejected", "closed_schema", "attestation"),
        ),
    ]
    for token, arguments, needles in cases:
        denied, _ = await _mcp_call_tool(
            harness["endpoint"],
            origin=harness["origin"],
            authorization=f"Bearer {token}",
            session_id=None,
            tool="ledger.review_ruling_append",
            arguments=arguments,
        )
        assert _is_tool_error(denied) is True, arguments
        payload = _tool_payload(denied).lower()
        assert SECRET_CANARY not in payload
        assert any(needle in payload for needle in needles), (arguments, payload)

    after = store.current_status()
    assert (after.last_committed, after.last_content_sha256) == (
        before.last_committed,
        before.last_content_sha256,
    )
    _scan_control_and_db(
        harness,
        SECRET_CANARY,
        reviewer_token,
        implementer_token,
        harness["password"],
    )
