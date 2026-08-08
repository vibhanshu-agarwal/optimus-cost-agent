"""Loopback Streamable HTTP MCP ledger service (Task 5).

Full credential/session validation is Task 6. This module uses PreParseAuthGateStub
at the auth pipeline position only.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
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
            if self.runtime_path is not None:
                try:
                    self.runtime_path.unlink(missing_ok=True)
                except OSError:
                    pass
                tmp = self.runtime_path.with_suffix(".tmp")
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass


def list_advertised_tools() -> list[dict[str, str]]:
    return [{"name": name} for name in sorted(ALLOWED_TOOL_NAMES)]


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
    def start(cls, config: ServiceConfig, store: Any, bootstrap: Any) -> RunningService:
        # store is reserved for later tool wiring; Task 5 must not persist DB credentials.
        _ = store
        control_root = Path(bootstrap.control_root)
        control_root.mkdir(parents=True, exist_ok=True)
        runtime_path = control_root / "service_runtime.json"
        # Bind/transport only — never conninfo, passwords, or ledger_instance_id.
        payload = {
            "bind_host": config.bind_host,
            "bind_port": config.bind_port,
            "allowed_origins": list(config.allowed_origins),
            "request_limits": dict(config.request_limits),
            "protocol_versions": list(config.protocol_versions),
        }
        tmp = runtime_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, runtime_path)
        try:
            os.chmod(runtime_path, 0o600)
        except OSError:
            pass

        process = subprocess.Popen(  # noqa: S603 - controlled argv, no shell
            [
                sys.executable,
                "-m",
                "evidence_handoff_runtime.service_cli",
                "serve",
                "--runtime-file",
                str(runtime_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            cwd=str(Path(__file__).resolve().parents[2]),
        )
        endpoint = f"http://{config.bind_host}:{config.bind_port}/mcp"
        running = RunningService(
            endpoint=endpoint,
            process=process,
            config=config,
            runtime_path=runtime_path,
        )
        try:
            running.wait_ready(timeout_seconds=30.0)
        except Exception:
            err = b""
            if process.stderr is not None:
                try:
                    err = process.stderr.read() or b""
                except Exception:
                    err = b""
            running.stop()
            raise RuntimeError(f"service_start_failed: {err.decode('utf-8', errors='replace')}") from None
        return running


def build_asgi_app(runtime: dict[str, Any]):
    """Build Starlette Streamable HTTP app with preamble middleware."""
    from mcp.server.mcpserver import MCPServer
    from mcp.server.transport_security import TransportSecuritySettings
    from starlette.responses import PlainTextResponse, Response
    from starlette.types import ASGIApp, Receive, Scope, Send

    bind_host = str(runtime["bind_host"])
    bind_port = int(runtime["bind_port"])
    allowed_origins = frozenset(str(item) for item in runtime["allowed_origins"])
    max_body = int(runtime["request_limits"]["max_body_bytes"])
    protocol_versions = frozenset(str(item) for item in runtime["protocol_versions"])

    server = MCPServer(name="evidence-handoff-ledger", version="0.1.0")

    def _tool(name: str):
        @server.tool(name=name, description=f"Task 5 surface: {name}")
        def _handler() -> dict[str, str]:
            return {"status": "ok", "tool": name}

        return _handler

    for tool_name in sorted(ALLOWED_TOOL_NAMES):
        _tool(tool_name)

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
        decision = evaluate_http_preamble(
            bind_host=bind_host,
            bind_port=bind_port,
            allowed_origins=allowed_origins,
            headers=headers,
            content_length=content_length,
            max_body_bytes=max_body,
            auth_present=auth_present,
            allowed_protocol_versions=protocol_versions,
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
