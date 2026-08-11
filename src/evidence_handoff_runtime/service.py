"""Loopback Streamable HTTP MCP ledger service.

Task 6: audience-bound credentials, sessions, and role policy. Signing keys and
store conninfo cross the parent/child boundary only via a short-lived auth-bundle
file (path on argv); never via service_runtime.json.
"""

from __future__ import annotations

import base64
import contextlib
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
    resolve_mcp_protocol_version,
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


def _scope_with_canonical_mcp_protocol_version(
    scope: dict[str, Any],
    protocol_version: str,
) -> dict[str, Any]:
    """Collapse repeated/joined MCP-Protocol-Version to one token; leave absent headers absent."""
    raw_headers = list(scope.get("headers") or [])
    if not any(key.lower() == b"mcp-protocol-version" for key, _ in raw_headers):
        return scope
    rewritten: list[tuple[bytes, bytes]] = []
    replaced = False
    encoded = protocol_version.encode("latin-1")
    for key, value in raw_headers:
        if key.lower() == b"mcp-protocol-version":
            if not replaced:
                rewritten.append((b"mcp-protocol-version", encoded))
                replaced = True
            continue
        rewritten.append((key, value))
    return {**scope, "headers": rewritten}

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
            retired_raw = auth.get("retired_agent_ids") or ()
            payload.update(
                {
                    "ledger_instance_id": instance_id,
                    "issuer": auth["issuer"],
                    "audience": auth["audience"],
                    "enrollments": _serialize_enrollments(enrollments),
                    "retired_agent_ids": [str(item) for item in retired_raw],
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
            with contextlib.suppress(Exception):
                stderr_handle.close()
            detail = ""
            try:
                detail = stderr_path.read_text(encoding="utf-8", errors="replace")[-4000:]
            except OSError:
                detail = ""
            running.stop()
            raise RuntimeError(f"service_start_failed: {detail}") from None
        with contextlib.suppress(Exception):
            stderr_handle.close()
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
    sessions = SessionRegistry(
        ttl=timedelta(minutes=30),
        now=lambda: datetime.now(tz=UTC),
        allowed_protocol_versions=frozenset(str(item) for item in runtime["protocol_versions"]),
    )
    store = PostgresLedgerStore(
        conninfo=str(auth_bundle["store_conninfo"]),
        ledger_instance_id=instance_id,
    )
    path_aliases = tuple(
        PathAliasRule(source_root=str(item["source_root"]), alias=str(item["alias"]))
        for item in runtime.get("path_aliases") or ()
    )
    known_agent_ids = frozenset(enrollment.agent_id for enrollment in enrollments.values())
    retired_agent_ids = frozenset(
        str(item) for item in (runtime.get("retired_agent_ids") or ())
    )
    return {
        "validator": validator,
        "sessions": sessions,
        "store": store,
        "ledger_instance_id": instance_id,
        "known_agent_ids": known_agent_ids,
        "retired_agent_ids": retired_agent_ids,
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
    """Build Starlette Streamable HTTP app with auth, policy, and redaction ingress."""
    from mcp.server.mcpserver import MCPServer
    from mcp.server.transport_security import TransportSecuritySettings
    from starlette.responses import PlainTextResponse, Response
    from starlette.types import ASGIApp, Receive, Scope, Send

    from evidence_handoff.redaction.ingress import RequestRedactionInputs, StructuredIngress
    from evidence_handoff.redaction.models import RedactionRuntimeInputs
    from evidence_handoff_runtime.auth import AuthError
    from evidence_handoff_runtime.capabilities import (
        ActivationError,
        CapabilityCoordinator,
        ReaderCapability,
    )
    from evidence_handoff_runtime.delivery import DeliveryError, DeliveryService
    from evidence_handoff_runtime.observability import build_delivery_views
    from evidence_handoff_runtime.policy import (
        PolicyError,
        attempt_review_ruling_append,
        attempt_review_ruling_read,
    )
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
    _real_tools = frozenset(
        {
            "ledger.review_ruling_append",
            "ledger.review_ruling_read",
            "ledger.delivery_read",
            "ledger.delivery_confirm",
            "ledger.capabilities_status",
            "ledger.delivery_status",
        }
    )

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

    def _bound_auth() -> tuple[str, str, dict[str, Any]]:
        assert auth_ctx is not None
        bound = _BOUND_REQUEST.get() or auth_ctx.get("_bound_request") or {}
        header = bound.get("authorization")
        sid = bound.get("session_id")
        if not header or not sid:
            raise RuntimeError("auth_gate_rejected:missing_bound_request")
        return str(header), str(sid), bound

    def _stub_tool(name: str):
        @server.tool(name=name, description=f"Task 5/6 surface: {name}")
        def _handler() -> dict[str, str]:
            return {"status": "ok", "tool": name}

        return _handler

    if auth_ctx is None:
        for tool_name in sorted(ALLOWED_TOOL_NAMES):
            _stub_tool(tool_name)
    else:
        for tool_name in sorted(ALLOWED_TOOL_NAMES - _real_tools):
            _stub_tool(tool_name)

        @server.tool(
            name="ledger.review_ruling_append",
            description="Append a review-ruling entry",
            structured_output=False,
        )
        def review_ruling_append(
            context_id: str,
            recipient_agent_ids: list[str],
            idempotency_key: str,
            message: dict[str, Any] | None = None,
            message_text: str | None = None,
            schema_id: str = "review-ruling.v1",
            agent_id: str | None = None,
            caller_role: str | None = None,
            authority: str | None = None,
            principal_id: str | None = None,
            attestation: Any | None = None,
        ):
            # Dual-accept: structured message is primary; legacy message_text is
            # adapted into a single text part before EntryDraft ingress/final-scan.
            header, sid, bound = _bound_auth()
            client_fields: dict[str, Any] = {
                "kind": "review-ruling",
                "schema_id": schema_id,
                "context_id": context_id,
                "recipient_agent_ids": list(recipient_agent_ids),
                "idempotency_key": idempotency_key,
            }
            if message is not None:
                client_fields["message"] = message
            if message_text is not None:
                client_fields["message_text"] = message_text
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
            try:
                result = attempt_review_ruling_append(
                    authorization_header=header,
                    session_id=sid,
                    protocol_version=str(bound.get("protocol_version") or "2025-11-25"),
                    ledger_instance_id=auth_ctx["ledger_instance_id"],
                    client_fields=client_fields,
                    validator=auth_ctx["validator"],
                    sessions=auth_ctx["sessions"],
                    ingress=ingress,
                    store=auth_ctx["store"],
                    request_inputs=_request_inputs(credential),
                    known_agent_ids=auth_ctx["known_agent_ids"],
                    # Authoritative retirement comes from ReaderCapability.retired (Task 9),
                    # unioned with any static bootstrap set from Task 8.
                    retired_agent_ids=frozenset(auth_ctx["retired_agent_ids"])
                    | frozenset(auth_ctx["store"].retired_agent_ids()),
                )
            except PolicyError as exc:
                raise RuntimeError(f"policy_rejected:{exc.code}") from exc
            return {
                "entry_id": str(result.entry_id),
                "sequence": int(result.sequence),
                "ledger_instance_id": str(result.ledger_instance_id),
                "content_sha256": str(result.content_sha256),
                "idempotent_replay": bool(result.idempotent_replay),
            }

        @server.tool(
            name="ledger.review_ruling_read",
            description="Read a review-ruling entry summary",
            structured_output=False,
        )
        def review_ruling_read(sequence: int):
            header, sid, bound = _bound_auth()
            try:
                return attempt_review_ruling_read(
                    authorization_header=header,
                    session_id=sid,
                    protocol_version=str(bound.get("protocol_version") or "2025-11-25"),
                    ledger_instance_id=auth_ctx["ledger_instance_id"],
                    sequence=int(sequence),
                    validator=auth_ctx["validator"],
                    sessions=auth_ctx["sessions"],
                    store=auth_ctx["store"],
                )
            except PolicyError as exc:
                raise RuntimeError(f"policy_rejected:{exc.code}") from exc

        delivery = DeliveryService(store=auth_ctx["store"])
        _enrollments = auth_ctx["validator"].enrollments
        _registered_readers = {
            enrollment.principal_id: enrollment.agent_id
            for enrollment in _enrollments.values()
            if "ledger.read" in enrollment.scopes
        }
        capabilities = CapabilityCoordinator(
            store=auth_ctx["store"],
            registered_readers=_registered_readers,
        )

        def _serialize_witness(witness: Any) -> dict[str, Any]:
            return {
                "ledger_instance_id": witness.ledger_instance_id,
                "last_committed": int(witness.last_committed),
                "last_content_sha256": witness.last_content_sha256,
                "verified": bool(witness.verified),
            }

        def _serialize_token(token: Any) -> dict[str, Any]:
            return {
                "token_id": token.token_id,
                "principal_id": token.principal_id,
                "agent_id": token.agent_id,
                "ledger_instance_id": token.ledger_instance_id,
                "previous_cursor": int(token.previous_cursor),
                "previous_witness": _serialize_witness(token.previous_witness),
                "watermark": int(token.watermark),
                "resulting_witness": _serialize_witness(token.resulting_witness),
                "visible_entry_ids": list(token.visible_entry_ids),
                "page_digest": token.page_digest,
                "expires_at": token.expires_at.isoformat(),
            }

        @server.tool(
            name="ledger.delivery_read",
            description="Read visible ledger entries after the confirmed cursor",
            structured_output=False,
        )
        def delivery_read(
            cursor: int = 0,
            supported_schemas: list[str] | None = None,
        ):
            header, sid, bound = _bound_auth()
            try:
                principal = auth_ctx["validator"].validate(
                    header=header,
                    request={
                        "ledger_instance_id": auth_ctx["ledger_instance_id"],
                        "required_scope": "ledger.read",
                    },
                )
                auth_ctx["sessions"].validate(
                    sid,
                    principal,
                    protocol_version=str(bound.get("protocol_version") or "2025-11-25"),
                )
                schemas = frozenset(str(item) for item in (supported_schemas or ()))
                if not schemas:
                    raise DeliveryError("supported_schemas_required")
                page = delivery.read_entries(
                    principal_id=principal.principal_id,
                    agent_id=principal.agent_id,
                    ledger_instance_id=auth_ctx["ledger_instance_id"],
                    cursor=int(cursor),
                    supported_schemas=schemas,
                )
            except (DeliveryError, AuthError, SessionError) as exc:
                code = getattr(exc, "code", str(exc))
                raise RuntimeError(f"delivery_rejected:{code}") from exc
            except Exception as exc:
                from evidence_handoff_runtime.integrity import LedgerIntegrityError

                if isinstance(exc, LedgerIntegrityError):
                    raise RuntimeError("delivery_rejected:ledger_integrity_failed") from exc
                raise
            return {
                "entries": [entry.to_mapping() for entry in page.entries],
                "watermark": int(page.watermark),
                "page_digest": page.page_digest,
                "delivery_token": _serialize_token(page.delivery_token),
                "token_id": page.delivery_token.token_id,
                "unread_count": int(page.unread_count),
            }

        @server.tool(
            name="ledger.delivery_confirm",
            description="Confirm a delivery page and advance the reader cursor",
            structured_output=False,
        )
        def delivery_confirm(token_id: str):
            header, sid, bound = _bound_auth()
            try:
                principal = auth_ctx["validator"].validate(
                    header=header,
                    request={
                        "ledger_instance_id": auth_ctx["ledger_instance_id"],
                        "required_scope": "ledger.read",
                    },
                )
                auth_ctx["sessions"].validate(
                    sid,
                    principal,
                    protocol_version=str(bound.get("protocol_version") or "2025-11-25"),
                )
                status = delivery.confirm_delivery(
                    token_id=str(token_id),
                    principal_id=principal.principal_id,
                )
            except (DeliveryError, AuthError, SessionError) as exc:
                code = getattr(exc, "code", str(exc))
                raise RuntimeError(f"delivery_rejected:{code}") from exc
            return {
                "principal_id": status.principal_id,
                "agent_id": status.agent_id,
                "confirmed_sequence": int(status.confirmed_sequence),
                "last_advanced_at": status.last_advanced_at.isoformat(),
                "unread_count": int(status.unread_count),
                "witness": _serialize_witness(status.witness),
            }

        @server.tool(
            name="ledger.capabilities_status",
            description="Report reader capabilities, activate writers, or retire principals",
            structured_output=False,
        )
        def capabilities_status(
            action: str = "status",
            supported_schemas: list[str] | None = None,
            schema_id: str | None = None,
            principal_id: str | None = None,
        ):
            header, sid, bound = _bound_auth()
            try:
                principal = auth_ctx["validator"].validate(
                    header=header,
                    request={
                        "ledger_instance_id": auth_ctx["ledger_instance_id"],
                        "required_scope": "ledger.read",
                    },
                )
                auth_ctx["sessions"].validate(
                    sid,
                    principal,
                    protocol_version=str(bound.get("protocol_version") or "2025-11-25"),
                )
                now = datetime.now(tz=UTC)
                integrity = auth_ctx["store"].global_integrity_fact()
                warning_incident = (
                    str(integrity["incident_id"])
                    if integrity.get("latched") and integrity.get("incident_id")
                    else None
                )
                auth_ctx["store"].touch_authenticated_request(
                    principal_id=principal.principal_id,
                    agent_id=principal.agent_id,
                    now=now,
                    warning_incident_id=warning_incident,
                )
                action_name = str(action or "status")
                if action_name == "report":
                    schemas = frozenset(str(item) for item in (supported_schemas or ()))
                    if not schemas:
                        raise ActivationError("supported_schemas_required")
                    cap = ReaderCapability(
                        agent_id=principal.agent_id,
                        principal_id=principal.principal_id,
                        supported_schemas=schemas,
                        reported_at=now,
                        retired=False,
                    )
                    capabilities.record_capability(cap)
                    return {
                        "principal_id": cap.principal_id,
                        "agent_id": cap.agent_id,
                        "supported_schemas": sorted(cap.supported_schemas),
                        "reported_at": cap.reported_at.isoformat(),
                        "retired": False,
                    }
                if action_name == "activate_writer":
                    if not schema_id:
                        raise ActivationError("schema_id_required")
                    status = capabilities.activate_writer(str(schema_id), caller=principal)
                    return {
                        "schema_id": status.schema_id,
                        "writer_active": status.writer_active,
                        "activated_at": status.activated_at.isoformat(),
                    }
                if action_name == "retire_principal":
                    target = str(principal_id or "")
                    if not target:
                        raise ActivationError("principal_id_required")
                    agent = _registered_readers.get(target)
                    result = capabilities.retire_principal(
                        target, caller=principal, agent_id=agent
                    )
                    return {
                        "principal_id": result.principal_id,
                        "agent_id": result.agent_id,
                        "retired": result.retired,
                        "audit_event_id": result.audit_event_id,
                    }
                # Default: content-free capability/preflight surface.
                blockers = (
                    capabilities.preflight_activation(str(schema_id)).stale_or_incompatible_principal_ids
                    if schema_id
                    else frozenset()
                )
                return {
                    "action": "status",
                    "active_writer_schemas": sorted(
                        sid
                        for sid in ("review-ruling.v1", "handoff.v1")
                        if auth_ctx["store"].is_writer_active(sid)
                    ),
                    "activation_blockers": sorted(blockers),
                }
            except (ActivationError, AuthError, SessionError) as exc:
                code = getattr(exc, "code", str(exc))
                raise RuntimeError(f"capability_rejected:{code}") from exc

        @server.tool(
            name="ledger.delivery_status",
            description="Content-free per-reader delivery facts (no liveness guesses)",
            structured_output=False,
        )
        def delivery_status():
            header, sid, bound = _bound_auth()
            try:
                principal = auth_ctx["validator"].validate(
                    header=header,
                    request={
                        "ledger_instance_id": auth_ctx["ledger_instance_id"],
                        "required_scope": "ledger.read",
                    },
                )
                auth_ctx["sessions"].validate(
                    sid,
                    principal,
                    protocol_version=str(bound.get("protocol_version") or "2025-11-25"),
                )
                now = datetime.now(tz=UTC)
                integrity = auth_ctx["store"].global_integrity_fact()
                warning_incident = (
                    str(integrity["incident_id"])
                    if integrity.get("latched") and integrity.get("incident_id")
                    else None
                )
                auth_ctx["store"].touch_authenticated_request(
                    principal_id=principal.principal_id,
                    agent_id=principal.agent_id,
                    now=now,
                    warning_incident_id=warning_incident,
                )
                # Ensure enrolled readers appear even before first capability report.
                for pid, aid in _registered_readers.items():
                    try:
                        auth_ctx["store"].get_reader_capability(pid)
                    except Exception:
                        auth_ctx["store"].upsert_reader_capability(
                            ReaderCapability(
                                agent_id=aid,
                                principal_id=pid,
                                supported_schemas=frozenset(),
                                reported_at=now,
                                retired=False,
                            )
                        )
                views = build_delivery_views(store=auth_ctx["store"])
                return {
                    "readers": [view.to_mapping() for view in views],
                    "integrity": dict(integrity),
                }
            except (AuthError, SessionError) as exc:
                code = getattr(exc, "code", str(exc))
                raise RuntimeError(f"delivery_status_rejected:{code}") from exc

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

        # Cursor may send MCP-Protocol-Version twice (RFC 9110 → comma-joined). The MCP
        # SDK rejects the joined string; rewrite ASGI headers to one allowed token.
        # Do not synthesize the header when the client omitted it (avoids injecting the
        # resolve() default over a session negotiated on a different allowed version).
        raw_protocol_header = headers.get("mcp-protocol-version")
        protocol_version = resolve_mcp_protocol_version(
            raw_protocol_header,
            allowed_protocol_versions=protocol_versions,
        )
        if raw_protocol_header is not None and str(raw_protocol_header).strip() != "":
            headers["mcp-protocol-version"] = protocol_version
            scope = _scope_with_canonical_mcp_protocol_version(scope, protocol_version)

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
