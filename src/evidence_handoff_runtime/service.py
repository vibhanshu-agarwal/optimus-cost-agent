"""Loopback Streamable HTTP MCP ledger service.

Task 6: audience-bound credentials, sessions, and role policy. Signing keys and
store conninfo cross the parent/child boundary only via a short-lived auth-bundle
file (path on argv); never via service_runtime.json.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import sys
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from evidence_handoff_runtime.integrity import IntegrityLatchError
from evidence_handoff_runtime.transport import (
    evaluate_http_preamble,
    is_legacy_sse_path,
)

ALLOWED_TOOL_NAMES = frozenset(
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

_BOUND_REQUEST: ContextVar[dict[str, Any] | None] = ContextVar("eh_bound_request", default=None)


class ServiceConfigError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __repr__(self) -> str:
        return f"ServiceConfigError(code={self.code!r})"

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class ServiceConfig:
    bind_host: str
    bind_port: int
    allowed_origins: tuple[str, ...]
    request_limits: dict[str, int]
    protocol_versions: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.bind_host not in {"127.0.0.1", "::1", "localhost"}:
            raise ServiceConfigError("bind_host_not_loopback")


@dataclass(frozen=True, slots=True)
class HealthReport:
    ready: bool
    code: str


@dataclass
class RunningService:
    endpoint: str
    process: subprocess.Popen[bytes]
    config: ServiceConfig
    runtime_path: Path | None = None
    auth_bundle_path: Path | None = None
    secret_paths: list[Path] = field(default_factory=list)

    def wait_ready(self, timeout_seconds: float = 30.0) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("service_process_exited")
            try:
                with socket.create_connection(
                    (self.config.bind_host, self.config.bind_port), timeout=0.25
                ):
                    return
            except OSError:
                time.sleep(0.1)
        raise TimeoutError("service_not_ready")

    def stop(self) -> None:
        try:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
        finally:
            for path in [self.runtime_path, self.auth_bundle_path, *self.secret_paths]:
                if path is None:
                    continue
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
                tmp = path.with_suffix(".tmp")
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass


def list_advertised_tools() -> list[dict[str, str]]:
    return [{"name": name} for name in sorted(ALLOWED_TOOL_NAMES)]


def _write_json_private(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _serialize_enrollments(enrollments: dict[Any, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for enrollment in enrollments.values():
        rows.append(
            {
                "principal_id": enrollment.principal_id,
                "agent_id": enrollment.agent_id,
                "caller_role": enrollment.caller_role,
                "scopes": sorted(enrollment.scopes),
                "instance_id": enrollment.instance_id,
            }
        )
    return rows


class LedgerService:
    @staticmethod
    def health_from_control_root(config: ServiceConfig, bootstrap: Any, *, store: Any) -> HealthReport:
        control_root = getattr(bootstrap, "control_root", None)
        if control_root is None:
            return HealthReport(ready=False, code="control_root_missing")
        try:
            from evidence_handoff_runtime.integrity import IntegrityLatch

            IntegrityLatch(control_root=Path(control_root)).load()
        except IntegrityLatchError:
            return HealthReport(ready=False, code="integrity_latch_corrupt")
        except Exception:
            return HealthReport(ready=False, code="health_check_failed")
        return HealthReport(ready=True, code="ok")

    @classmethod
    def start(
        cls,
        config: ServiceConfig,
        store: Any,
        bootstrap: Any,
        auth: dict[str, Any] | None = None,
        *,
        allow_unauthenticated_stub: bool = False,
    ) -> RunningService:
        if auth is None and not allow_unauthenticated_stub:
            raise ServiceConfigError("auth_required")
        control_root = Path(bootstrap.control_root)
        control_root.mkdir(parents=True, exist_ok=True)
        runtime_path = control_root / "service_runtime.json"
        auth_bundle_path: Path | None = None

        payload: dict[str, Any] = {
            "bind_host": config.bind_host,
            "bind_port": config.bind_port,
            "allowed_origins": list(config.allowed_origins),
            "request_limits": dict(config.request_limits),
            "protocol_versions": list(config.protocol_versions),
        }
        argv = [
            sys.executable,
            "-m",
            "evidence_handoff_runtime.service_cli",
            "serve",
            "--runtime-file",
            str(runtime_path),
        ]

        if auth is not None:
            instance_id = getattr(store, "ledger_instance_id", None) or getattr(
                store, "_ledger_instance_id", None
            )
            conninfo = getattr(store, "_conninfo", None)
            if not instance_id or not conninfo:
                raise ServiceConfigError("store_runtime_missing")
            signing_key = auth["signing_key"]
            if not isinstance(signing_key, (bytes, bytearray)):
                raise ServiceConfigError("signing_key_invalid")
            enrollments = auth["enrollments"]
            auth_bundle_path = control_root / "auth_bundle.json"
            # Ephemeral secrets file — child unlinks immediately after load.
            _write_json_private(
                auth_bundle_path,
                {
                    "signing_key_b64": base64.b64encode(bytes(signing_key)).decode("ascii"),
                    "store_conninfo": conninfo,
                    "service_secrets": list(getattr(bootstrap, "service_secrets", ()) or ()),
                    "identity_values": list(getattr(bootstrap, "identity_values", ()) or ()),
                },
            )
            payload.update(
                {
                    "ledger_instance_id": instance_id,
                    "issuer": auth["issuer"],
                    "audience": auth["audience"],
                    "enrollments": _serialize_enrollments(enrollments),
                    "temporary_capture_root": str(bootstrap.temporary_capture_root),
                    "staging_root": str(bootstrap.staging_root),
                    "quarantine_root": str(bootstrap.quarantine_root),
                    "forbidden_persistence_roots": [
                        str(path) for path in bootstrap.forbidden_persistence_roots
                    ],
                    "path_aliases": [
                        {"source_root": rule.source_root, "alias": rule.alias}
                        for rule in bootstrap.path_aliases
                    ],
                }
            )
            argv.extend(["--auth-bundle-file", str(auth_bundle_path)])

        # Bind/transport (+ non-secret enrollments/paths). Never signing keys/passwords/conninfo.
        _write_json_private(runtime_path, payload)

        stderr_path = control_root / "service.stderr.log"
        stderr_handle = open(stderr_path, "wb")  # noqa: SIM115 — lifetime tied to subprocess
        process = subprocess.Popen(  # noqa: S603 - controlled argv, no shell
            argv,
            stdout=subprocess.DEVNULL,
            stderr=stderr_handle,
            cwd=str(Path(__file__).resolve().parents[2]),
        )
        endpoint = f"http://{config.bind_host}:{config.bind_port}/mcp"
        running = RunningService(
            endpoint=endpoint,
            process=process,
            config=config,
            runtime_path=runtime_path,
            auth_bundle_path=auth_bundle_path,
            secret_paths=[stderr_path],
        )
        try:
            running.wait_ready(timeout_seconds=30.0)
        except Exception:
            try:
                stderr_handle.close()
            except Exception:
                pass
            detail = ""
            try:
                detail = stderr_path.read_text(encoding="utf-8", errors="replace")[-4000:]
            except OSError:
                detail = ""
            running.stop()
            raise RuntimeError(f"service_start_failed: {detail}") from None
        try:
            stderr_handle.close()
        except Exception:
            pass
        # Child should already have unlinked the bundle; parent best-effort sweep.
        if auth_bundle_path is not None:
            try:
                auth_bundle_path.unlink(missing_ok=True)
            except OSError:
                pass
        return running


def _load_auth_context(runtime: dict[str, Any], auth_bundle: dict[str, Any] | None) -> dict[str, Any] | None:
    if auth_bundle is None:
        return None
    from evidence_handoff_runtime.auth import CredentialValidator, Enrollment
    from evidence_handoff_runtime.sessions import SessionRegistry
    from evidence_handoff_runtime.store import PostgresLedgerStore
    from optimus_security.sanitization import PathAliasRule

    signing_key = base64.b64decode(str(auth_bundle["signing_key_b64"]).encode("ascii"))
    enrollments: dict[tuple[str, str], Enrollment] = {}
    for row in runtime.get("enrollments") or []:
        enrollment = Enrollment(
            principal_id=str(row["principal_id"]),
            agent_id=str(row["agent_id"]),
            caller_role=str(row["caller_role"]),
            scopes=frozenset(str(item) for item in row["scopes"]),
            instance_id=str(row["instance_id"]),
        )
        enrollments[(enrollment.instance_id, enrollment.principal_id)] = enrollment
    instance_id = str(runtime["ledger_instance_id"])
    validator = CredentialValidator(
        signing_key=signing_key,
        expected_issuer=str(runtime["issuer"]),
        expected_audience=str(runtime["audience"]),
        enrollments=enrollments,
        now=lambda: datetime.now(tz=UTC),
        revoked_token_ids=frozenset(),
        consumed_jti=set(),
    )
    sessions = SessionRegistry(ttl=timedelta(minutes=30), now=lambda: datetime.now(tz=UTC))
    store = PostgresLedgerStore(
        conninfo=str(auth_bundle["store_conninfo"]),
        ledger_instance_id=instance_id,
    )
    path_aliases = tuple(
        PathAliasRule(source_root=str(item["source_root"]), alias=str(item["alias"]))
        for item in runtime.get("path_aliases") or ()
    )
    return {
        "validator": validator,
        "sessions": sessions,
        "store": store,
        "ledger_instance_id": instance_id,
        "service_secrets": tuple(auth_bundle.get("service_secrets") or ()),
        "identity_values": tuple(auth_bundle.get("identity_values") or ()),
        "path_aliases": path_aliases,
        "temporary_capture_root": Path(str(runtime["temporary_capture_root"])),
        "staging_root": Path(str(runtime["staging_root"])),
        "quarantine_root": Path(str(runtime["quarantine_root"])),
        "forbidden_persistence_roots": tuple(
            Path(str(path)) for path in runtime.get("forbidden_persistence_roots") or ()
        ),
    }


def build_asgi_app(runtime: dict[str, Any], *, auth_bundle: dict[str, Any] | None = None):
    """Build Starlette Streamable HTTP app with preamble middleware and Task 6 tools."""
    from mcp.server.mcpserver import MCPServer
    from mcp.server.transport_security import TransportSecuritySettings
    from starlette.responses import PlainTextResponse, Response
    from starlette.types import ASGIApp, Receive, Scope, Send

    from evidence_handoff.redaction.ingress import RequestRedactionInputs, StructuredIngress
    from evidence_handoff.redaction.models import RedactionRuntimeInputs
    from evidence_handoff_runtime.auth import AuthError
    from evidence_handoff_runtime.policy import PolicyError, attempt_review_ruling_append
    from evidence_handoff_runtime.sessions import SessionError
    from optimus_security.sensitive_values import SensitiveValueInventory, SensitiveValueSourceClass

    bind_host = str(runtime["bind_host"])
    bind_port = int(runtime["bind_port"])
    allowed_origins = frozenset(str(item) for item in runtime["allowed_origins"])
    max_body = int(runtime["request_limits"]["max_body_bytes"])
    protocol_versions = frozenset(str(item) for item in runtime["protocol_versions"])
    auth_ctx = _load_auth_context(runtime, auth_bundle)

    server = MCPServer(name="evidence-handoff-ledger", version="0.1.0")
    ingress = StructuredIngress()

    def _request_inputs(credential: str) -> RequestRedactionInputs:
        assert auth_ctx is not None
        inventory = SensitiveValueInventory()
        for secret in auth_ctx["service_secrets"]:
            if secret:
                inventory.add_secret(secret, source_class=SensitiveValueSourceClass.CONFIG_FILE)
        if credential:
            inventory.add_secret(credential, source_class=SensitiveValueSourceClass.ENVIRONMENT)
        for identity in auth_ctx["identity_values"]:
            if identity:
                inventory.add_pii(identity, source_class=SensitiveValueSourceClass.INJECTED_PII)
        runtime_inputs = RedactionRuntimeInputs(
            sensitive_values=inventory,
            path_aliases=auth_ctx["path_aliases"],
            temporary_capture_root=auth_ctx["temporary_capture_root"],
            staging_root=auth_ctx["staging_root"],
            quarantine_root=auth_ctx["quarantine_root"],
            forbidden_persistence_roots=auth_ctx["forbidden_persistence_roots"],
        )
        return RequestRedactionInputs(runtime=runtime_inputs)

    def _stub_tool(name: str):
        @server.tool(name=name, description=f"Task 5/6 surface: {name}")
        def _handler() -> dict[str, str]:
            return {"status": "ok", "tool": name}

        return _handler

    if auth_ctx is None:
        for tool_name in sorted(ALLOWED_TOOL_NAMES):
            _stub_tool(tool_name)
    else:
        for tool_name in sorted(ALLOWED_TOOL_NAMES - {"ledger.review_ruling_append"}):
            _stub_tool(tool_name)

        @server.tool(
            name="ledger.review_ruling_append",
            description="Append a review-ruling entry",
            structured_output=False,
        )
        def review_ruling_append(
            context_id: str,
            recipient_agent_ids: list[str],
            message_text: str,
            idempotency_key: str,
            schema_id: str = "review-ruling.v1",
            agent_id: str | None = None,
            caller_role: str | None = None,
            authority: str | None = None,
            principal_id: str | None = None,
            attestation: str | None = None,
        ):
            bound = _BOUND_REQUEST.get() or auth_ctx.get("_bound_request") or {}
            header = bound.get("authorization")
            sid = bound.get("session_id")
            if not header or not sid:
                raise RuntimeError("auth_gate_rejected:missing_bound_request")
            client_fields: dict[str, Any] = {
                "kind": "review-ruling",
                "schema_id": schema_id,
                "context_id": context_id,
                "recipient_agent_ids": list(recipient_agent_ids),
                "message_text": message_text,
                "idempotency_key": idempotency_key,
            }
            for key, value in (
                ("agent_id", agent_id),
                ("caller_role", caller_role),
                ("authority", authority),
                ("principal_id", principal_id),
                ("attestation", attestation),
            ):
                if value is not None:
                    client_fields[key] = value
            credential = header[7:].strip() if header.lower().startswith("bearer ") else header
            result = attempt_review_ruling_append(
                authorization_header=header,
                session_id=str(sid),
                protocol_version=str(bound.get("protocol_version") or "2025-11-25"),
                ledger_instance_id=auth_ctx["ledger_instance_id"],
                client_fields=client_fields,
                validator=auth_ctx["validator"],
                sessions=auth_ctx["sessions"],
                ingress=ingress,
                store=auth_ctx["store"],
                request_inputs=_request_inputs(credential),
            )
            return {
                "sequence": int(result.sequence),
                "content_sha256": str(result.content_sha256),
                "idempotent_replay": bool(result.idempotent_replay),
            }

    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[f"{bind_host}:{bind_port}", bind_host],
        allowed_origins=list(allowed_origins),
    )
    inner: ASGIApp = server.streamable_http_app(
        streamable_http_path="/mcp",
        host=bind_host,
        max_request_body_size=max_body,
        transport_security=security,
        json_response=True,
    )

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await inner(scope, receive, send)
            return
        path = scope.get("path", "")
        if is_legacy_sse_path(path):
            response = PlainTextResponse("legacy_sse_disabled", status_code=404)
            await response(scope, receive, send)
            return

        headers = {key.decode("latin-1"): value.decode("latin-1") for key, value in scope.get("headers", [])}
        content_length = int(headers.get("content-length", "0") or "0")
        auth_present = bool(headers.get("authorization"))
        validator = auth_ctx["validator"] if auth_ctx is not None else None
        instance_id = auth_ctx["ledger_instance_id"] if auth_ctx is not None else None
        decision = evaluate_http_preamble(
            bind_host=bind_host,
            bind_port=bind_port,
            allowed_origins=allowed_origins,
            headers=headers,
            content_length=content_length,
            max_body_bytes=max_body,
            auth_present=auth_present,
            allowed_protocol_versions=protocol_versions,
            credential_validator=validator,
            ledger_instance_id=instance_id,
        )
        if not decision.allowed:
            response = Response(
                content=decision.code,
                status_code=decision.http_status,
                headers={"x-evidence-handoff-code": decision.code},
                media_type="text/plain",
            )
            await response(scope, receive, send)
            return

        if auth_ctx is not None and auth_present:
            try:
                principal = auth_ctx["validator"].validate(
                    headers["authorization"],
                    {
                        "ledger_instance_id": auth_ctx["ledger_instance_id"],
                        "required_scope": "ledger.write",
                    },
                )
                session_header = headers.get("mcp-session-id")
                protocol_version = headers.get("mcp-protocol-version") or "2025-11-25"
                # Request path: validate only. Never adopt a client-presented unknown
                # session id here — that is the hijack vector. Adoption happens only
                # when this authenticated response carries a new MCP session id.
                if session_header:
                    auth_ctx["sessions"].validate(
                        session_header,
                        principal,
                        protocol_version=protocol_version,
                    )
                    bound_session = session_header
                else:
                    bound_session = auth_ctx["sessions"].create(
                        principal, protocol_version=protocol_version
                    ).session_id
                auth_ctx["_bound_request"] = {
                    "authorization": headers["authorization"],
                    "session_id": bound_session,
                    "protocol_version": protocol_version,
                }
                _BOUND_REQUEST.set(auth_ctx["_bound_request"])

                async def send_with_session(message: dict[str, Any]) -> None:
                    if message["type"] == "http.response.start":
                        raw_headers = list(message.get("headers") or [])
                        mcp_sid = None
                        for key, value in raw_headers:
                            if key.lower() == b"mcp-session-id":
                                mcp_sid = value.decode("latin-1")
                                break
                        if mcp_sid:
                            try:
                                auth_ctx["sessions"].validate(
                                    mcp_sid,
                                    principal,
                                    protocol_version=protocol_version,
                                )
                            except SessionError as exc:
                                if exc.code != "session_expired_or_unknown":
                                    raise
                                auth_ctx["sessions"].attach(
                                    mcp_sid,
                                    principal,
                                    protocol_version=protocol_version,
                                )
                            auth_ctx["_bound_request"]["session_id"] = mcp_sid
                            _BOUND_REQUEST.set(auth_ctx["_bound_request"])
                        elif not session_header:
                            if not any(key.lower() == b"mcp-session-id" for key, _ in raw_headers):
                                raw_headers.append(
                                    (b"mcp-session-id", bound_session.encode("latin-1"))
                                )
                                message = {**message, "headers": raw_headers}
                    await send(message)

                await inner(scope, receive, send_with_session)
                return
            except (AuthError, SessionError, PolicyError) as exc:
                response = Response(
                    content=str(exc),
                    status_code=401 if isinstance(exc, (AuthError, SessionError)) else 403,
                    headers={"x-evidence-handoff-code": str(exc)},
                    media_type="text/plain",
                )
                await response(scope, receive, send)
                return

        await inner(scope, receive, send)

    return app


__all__ = [
    "ALLOWED_TOOL_NAMES",
    "HealthReport",
    "LedgerService",
    "RunningService",
    "ServiceConfig",
    "ServiceConfigError",
    "build_asgi_app",
    "list_advertised_tools",
]
