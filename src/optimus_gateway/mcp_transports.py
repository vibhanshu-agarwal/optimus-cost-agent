"""Bounded MCP transport adapters owned by the Gateway."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import signal
import subprocess
import threading
import time
from http.client import HTTPResponse
from queue import Empty, Queue
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from optimus_gateway.mcp_profiles import MCPProfile, MCPStdioProfile

MCP_PROTOCOL_FLOOR = "2026-07-28"
MCPClientMeta = dict[str, object]
CredentialResolver = Callable[[str], Mapping[str, str] | str]

_FORBIDDEN_CAPABILITIES = frozenset({"roots", "sampling", "elicitation", "logging", "subscriptions", "extensions"})
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DIGEST_IMAGE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
_FORBIDDEN_DOCKER_TOKEN_PARTS = ("--mount", "--device", "/var/run/docker.sock")


class MCPTransportError(RuntimeError):
    """Raised when a transport violates the bounded MCP transport contract."""


class MCPTransport(Protocol):
    def server_discover(self, *, protocol_version: str, client_meta: MCPClientMeta) -> dict[str, Any]: ...

    def tools_list(
        self, *, cursor: str | None, protocol_version: str, client_meta: MCPClientMeta
    ) -> dict[str, Any]: ...

    def tools_call(self, *, upstream_tool_name: str, arguments: dict[str, Any], protocol_version: str) -> dict[str, Any]: ...

    def close(self) -> None: ...


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, _request, _fp, _code, _msg, _headers, _newurl):
        return None


def _is_loopback(host: str | None) -> bool:
    if host is None or host.lower() == "localhost":
        return host is not None
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _origin(parts) -> tuple[str, str, int | None]:
    return parts.scheme.lower(), (parts.hostname or "").lower(), parts.port


def _validate_capabilities(result: dict[str, Any]) -> None:
    capabilities = result.get("capabilities")
    if not isinstance(capabilities, dict):
        raise MCPTransportError("MCP discovery omitted capabilities")
    forbidden = set(capabilities).intersection(_FORBIDDEN_CAPABILITIES)
    if forbidden:
        raise MCPTransportError("MCP discovery advertised forbidden capabilities")


def _meta(protocol_version: str, client_meta: MCPClientMeta) -> dict[str, object]:
    name = client_meta.get("name")
    version = client_meta.get("version")
    capabilities = client_meta.get("capabilities", {"tools": {}})
    if not isinstance(name, str) or not name or not isinstance(version, str) or not version:
        raise MCPTransportError("client metadata requires name and version")
    if not isinstance(capabilities, dict) or set(capabilities) - {"tools"}:
        raise MCPTransportError("client metadata advertises forbidden capabilities")
    return {
        "protocolVersion": protocol_version,
        "clientInfo": {"name": name, "version": version},
        "capabilities": {"tools": {}},
    }


class StreamableHTTPMCPTransport:
    """Request-scoped Streamable HTTP adapter with no session or redirect behavior."""

    def __init__(
        self,
        profile: MCPProfile,
        *,
        opener=None,
        credential_resolver: CredentialResolver | None = None,
        max_response_bytes: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if profile.transport != "http":
            raise MCPTransportError("HTTP transport requires an HTTP profile")
        config = profile.transport_config
        parts = urlsplit(config.endpoint)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise MCPTransportError("HTTP endpoint has an invalid scheme, host, or userinfo")
        if parts.fragment:
            raise MCPTransportError("HTTP endpoint must not contain a fragment")
        if parts.scheme != "https" and not (config.allow_insecure_loopback and _is_loopback(parts.hostname)):
            raise MCPTransportError("HTTPS is required except for explicitly provisioned loopback")
        self.profile = profile
        self.endpoint = config.endpoint
        try:
            self._origin = _origin(parts)
        except ValueError as exc:
            raise MCPTransportError("HTTP endpoint has an invalid port") from exc
        self._opener = opener or build_opener(_NoRedirectHandler())
        self._credential_resolver = credential_resolver
        self._max_response_bytes = max_response_bytes or profile.limits.max_result_bytes
        self._clock = clock
        self._request_id = 0

    def server_discover(self, *, protocol_version: str, client_meta: MCPClientMeta) -> dict[str, Any]:
        result = self._request(
            method="server/discover",
            params={"_meta": _meta(protocol_version, client_meta)},
            protocol_version=protocol_version,
        )
        _validate_capabilities(result)
        return result

    def tools_list(
        self, *, cursor: str | None, protocol_version: str, client_meta: MCPClientMeta
    ) -> dict[str, Any]:
        params: dict[str, object] = {"_meta": _meta(protocol_version, client_meta)}
        if cursor is not None:
            params["cursor"] = cursor
        return self._request(method="tools/list", params=params, protocol_version=protocol_version)

    def tools_call(self, *, upstream_tool_name: str, arguments: dict[str, Any], protocol_version: str) -> dict[str, Any]:
        return self._request(
            method="tools/call",
            params={
                "name": upstream_tool_name,
                "arguments": arguments,
                "_meta": _meta(protocol_version, {"name": "optimus-gateway", "version": "1.0"}),
            },
            protocol_version=protocol_version,
        )

    def close(self) -> None:
        return None

    def _request(self, *, method: str, params: dict[str, object], protocol_version: str) -> dict[str, Any]:
        if self._credential_resolver is None:
            raise MCPTransportError("HTTP credential resolver is required")
        self._request_id += 1
        body = json.dumps(
            {"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": params},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(self.endpoint, data=body, method="POST")
        request.add_header("Accept", "application/json")
        request.add_header("Content-Type", "application/json")
        request.add_header("MCP-Protocol-Version", protocol_version)
        credential = self._credential_resolver(self.profile.credential_ref)
        if not isinstance(credential, str) or not credential:
            raise MCPTransportError("HTTP credential resolver returned no credential")
        request.add_header("Authorization", f"Bearer {credential}")
        started = self._clock()
        timeout = min(30.0, self.profile.limits.max_call_duration_seconds)
        try:
            response = self._opener.open(request, timeout=timeout)
            status = getattr(response, "status", None)
            if status is None and hasattr(response, "getcode"):
                status = response.getcode()
            if status is not None and 300 <= status < 400:
                raise MCPTransportError("redirects are disabled")
            response_url = response.geturl() if hasattr(response, "geturl") else self.endpoint
            if response_url != self.endpoint or _origin(urlsplit(response_url)) != self._origin:
                raise MCPTransportError("HTTP response crossed the pinned origin or path")
            raw = self._read_bounded(response, deadline=started + timeout)
        except MCPTransportError:
            raise
        except Exception as exc:
            raise MCPTransportError(f"HTTP MCP request failed: {type(exc).__name__}") from exc
        if self._clock() - started > timeout:
            raise MCPTransportError("HTTP MCP request exceeded duration limit")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MCPTransportError("HTTP MCP response was not valid JSON") from exc
        if not isinstance(payload, dict):
            raise MCPTransportError("HTTP MCP response must be an object")
        if "error" in payload:
            error = payload["error"]
            raise MCPTransportError(f"HTTP MCP request returned an error: {error}")
        result = payload.get("result", payload)
        if not isinstance(result, dict):
            raise MCPTransportError("HTTP MCP result must be an object")
        return result

    def _read_bounded(self, response: HTTPResponse, *, deadline: float) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while True:
            if self._clock() > deadline:
                raise MCPTransportError("HTTP MCP request exceeded duration limit")
            chunk = response.read(min(65_536, self._max_response_bytes - total + 1))
            if not chunk:
                break
            if self._clock() > deadline:
                raise MCPTransportError("HTTP MCP request exceeded duration limit")
            total += len(chunk)
            if total > self._max_response_bytes:
                raise MCPTransportError("HTTP MCP response exceeded byte limit")
            chunks.append(chunk)
        return b"".join(chunks)

class MCPProcessControl(Protocol):
    def readline(self, stream, *, timeout: float) -> bytes: ...

    def terminate_tree(self, process) -> None: ...


class DefaultMCPProcessControl:
    """Process-tree seam; platform-specific Job Object/limit implementations plug in here."""

    def readline(self, stream, *, timeout: float) -> bytes:
        result: Queue[bytes | BaseException] = Queue(maxsize=1)

        def read() -> None:
            try:
                result.put(stream.readline())
            except BaseException as exc:  # pragma: no cover - exercised by live process failures
                result.put(exc)

        threading.Thread(target=read, daemon=True).start()
        try:
            value = result.get(timeout=timeout)
        except Empty as exc:
            raise TimeoutError("stdio read timed out") from exc
        if isinstance(value, BaseException):
            raise value
        return value

    def terminate_tree(self, process) -> None:
        if os.name == "nt":
            process.terminate()
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except (AttributeError, ProcessLookupError):
                process.terminate()
        try:
            process.wait(timeout=1)
        except (subprocess.TimeoutExpired, AttributeError):
            process.kill()


def _default_process_factory(argv: list[str], env: dict[str, str]):
    kwargs: dict[str, object] = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "env": env,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(argv, **kwargs)


class DockerStdioMCPTransport:
    """Docker-contained, line-delimited MCP adapter with bounded child lifetime."""

    def __init__(
        self,
        profile: MCPProfile,
        *,
        process_factory: Callable[[list[str], dict[str, str]], object] | None = None,
        credential_resolver: CredentialResolver | None = None,
        process_control: MCPProcessControl | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if profile.transport != "stdio" or not isinstance(profile.transport_config, MCPStdioProfile):
            raise MCPTransportError("stdio transport requires a stdio profile")
        config = profile.transport_config
        if _DIGEST_IMAGE.fullmatch(config.image) is None:
            raise MCPTransportError("stdio image must be digest pinned")
        tokens = (config.command, *config.arguments)
        if any(any(part in token for part in _FORBIDDEN_DOCKER_TOKEN_PARTS) for token in tokens):
            raise MCPTransportError("stdio command contains a forbidden Docker isolation token")
        if any(_ENV_NAME.fullmatch(name) is None for name in config.environment_names):
            raise MCPTransportError("stdio environment names are invalid")
        env = self._project_environment(config, profile.credential_ref, credential_resolver)
        argv = ["docker", "run", "--rm", "--init", "--read-only", "--network", "none"]
        for name in config.environment_names:
            argv.extend(("--env", name))
        argv.extend((config.image, config.command, *config.arguments))
        self.profile = profile
        self._max_duration = min(30.0, profile.limits.max_call_duration_seconds)
        self._max_result_bytes = profile.limits.max_result_bytes
        self._clock = clock
        self._process_control = process_control or DefaultMCPProcessControl()
        self._process = (process_factory or _default_process_factory)(argv, env)
        attach = getattr(self._process_control, "attach", None)
        if attach is not None:
            attach(self._process)
        self._request_id = 0
        self._modern = True
        self._closed = False

    def server_discover(self, *, protocol_version: str, client_meta: MCPClientMeta) -> dict[str, Any]:
        try:
            result = self._request(
                method="server/discover",
                params={"_meta": _meta(protocol_version, client_meta)},
                protocol_version=protocol_version,
                close_on_failure=False,
            )
            _validate_capabilities(result)
            return result
        except MCPTransportError as exc:
            if "method not found" not in str(exc).lower() and "-32601" not in str(exc):
                self.close()
                raise
            self._modern = False
            result = self._request(
                method="initialize",
                params={
                    "protocolVersion": protocol_version,
                    "clientInfo": client_meta,
                    "capabilities": {"tools": {}},
                    "_meta": _meta(protocol_version, client_meta),
                },
                protocol_version=protocol_version,
            )
            _validate_capabilities(result)
            return result

    def tools_list(
        self, *, cursor: str | None, protocol_version: str, client_meta: MCPClientMeta
    ) -> dict[str, Any]:
        params: dict[str, object] = {"_meta": _meta(protocol_version, client_meta)}
        if cursor is not None:
            params["cursor"] = cursor
        return self._request(method="tools/list", params=params, protocol_version=protocol_version)

    def tools_call(self, *, upstream_tool_name: str, arguments: dict[str, Any], protocol_version: str) -> dict[str, Any]:
        return self._request(
            method="tools/call",
            params={
                "name": upstream_tool_name,
                "arguments": arguments,
                "_meta": _meta(protocol_version, {"name": "optimus-gateway", "version": "1.0"}),
            },
            protocol_version=protocol_version,
        )

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._process_control.terminate_tree(self._process)

    def _request(
        self, *, method: str, params: dict[str, object], protocol_version: str, close_on_failure: bool = True
    ) -> dict[str, Any]:
        if self._closed:
            raise MCPTransportError("stdio transport is closed")
        self._request_id += 1
        line = json.dumps(
            {"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": params},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        started = self._clock()
        try:
            written = self._process.stdin.write(line)
            if written is not None and written != len(line):
                raise MCPTransportError("stdio request was only partially written")
            self._process.stdin.flush()
            raw = self._process_control.readline(self._process.stdout, timeout=self._max_duration)
        except MCPTransportError:
            if close_on_failure:
                self.close()
            raise
        except Exception as exc:
            self.close()
            raise MCPTransportError(f"stdio MCP request failed: {type(exc).__name__}") from exc
        if self._clock() - started > self._max_duration:
            self.close()
            raise MCPTransportError("stdio MCP request exceeded duration limit")
        if not isinstance(raw, bytes) or len(raw) > self._max_result_bytes:
            self.close()
            raise MCPTransportError("stdio MCP response exceeded byte limit")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.close()
            raise MCPTransportError("stdio MCP response was not valid JSON") from exc
        if not isinstance(payload, dict):
            self.close()
            raise MCPTransportError("stdio MCP response must be an object")
        if "error" in payload:
            if close_on_failure:
                self.close()
            raise MCPTransportError(f"stdio MCP request returned an error: {payload['error']}")
        result = payload.get("result", payload)
        if not isinstance(result, dict):
            self.close()
            raise MCPTransportError("stdio MCP result must be an object")
        return result

    @staticmethod
    def _project_environment(
        config: MCPStdioProfile, credential_ref: str, resolver: CredentialResolver | None
    ) -> dict[str, str]:
        if not config.environment_names:
            return {}
        if resolver is None:
            raise MCPTransportError("stdio credential resolver is required")
        resolved = resolver(credential_ref)
        if isinstance(resolved, str):
            if len(config.environment_names) != 1:
                raise MCPTransportError("credential resolver must return named values")
            return {config.environment_names[0]: resolved}
        if not isinstance(resolved, Mapping):
            raise MCPTransportError("credential resolver returned invalid values")
        if any(name not in resolved or not isinstance(resolved[name], str) for name in config.environment_names):
            raise MCPTransportError("credential resolver omitted a selected environment value")
        return {name: resolved[name] for name in config.environment_names}


__all__ = [
    "DockerStdioMCPTransport",
    "MCPClientMeta",
    "MCPProcessControl",
    "MCPTransport",
    "MCPTransportError",
    "StreamableHTTPMCPTransport",
]
