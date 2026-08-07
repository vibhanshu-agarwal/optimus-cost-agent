"""Local-only pending client-MCP candidate IPC (AF_PIPE / AF_UNIX)."""

from __future__ import annotations

import contextlib
import os
import tempfile
import threading
import uuid
from dataclasses import dataclass
from multiprocessing.connection import Client, Listener
from pathlib import Path
from typing import Any

from optimus.mcp.client_config import ClientMcpSafeIdentity

_OP_CONSUME = "consume_snapshot"


class LocalIpcError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def reject_network_endpoint_address(address: object) -> None:
    if isinstance(address, tuple):
        raise LocalIpcError("client_mcp.ipc_network_endpoint")
    if isinstance(address, str):
        lowered = address.strip().lower()
        if lowered.startswith(("tcp://", "http://", "https://")):
            raise LocalIpcError("client_mcp.ipc_network_endpoint")
        if (
            "\\" not in address
            and "/" not in address
            and address.count(":") == 1
            and not address.lower().startswith("af_unix:")
        ):
            host, _, port = address.partition(":")
            if host and port.isdigit():
                raise LocalIpcError("client_mcp.ipc_network_endpoint")


def default_local_candidate_address(*, token: str | None = None) -> tuple[str, str]:
    marker = token or uuid.uuid4().hex[:16]
    if os.name == "nt":
        return "af_pipe", rf"\\.\pipe\optimus-client-mcp-{marker}"
    sock = Path(tempfile.gettempdir()) / f"optimus-cmcp-{marker}.sock"
    if sock.exists():
        sock.unlink()
    return "af_unix", str(sock)


@dataclass(frozen=True)
class PendingClientMcpCandidate:
    workspace_digest: str
    session_id: str
    identity: ClientMcpSafeIdentity
    rendered_fingerprint: str
    provenance: str
    scanner_rule_ids: tuple[str, ...]


@dataclass(frozen=True)
class SafeCandidateSnapshot:
    candidate_id: str
    workspace_digest: str
    session_id: str
    server_name: str
    transport: str
    canonical_target: str
    arguments: tuple[str, ...]
    credential_name_fingerprints: tuple[str, ...]
    rendered_fingerprint: str
    provenance: str
    scanner_rule_ids: tuple[str, ...]
    safe_identity_summary: str


class PendingClientMcpCandidateEndpoint:
    def __init__(self, *, authkey: bytes, address: tuple[str, str] | None = None) -> None:
        self._authkey = authkey
        self._pending: dict[str, PendingClientMcpCandidate] = {}
        self._lock = threading.RLock()
        self._listener: Listener | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._endpoint_address: tuple[str, str] | None = address

    @property
    def endpoint_address(self) -> tuple[str, str]:
        with self._lock:
            if self._endpoint_address is None:
                raise LocalIpcError("client_mcp.ipc_not_listening")
            if self._listener is None and self._pending:
                self._start_listener_locked()
            return self._endpoint_address

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    @property
    def is_listening(self) -> bool:
        return self.pending_count > 0

    def publish(self, candidate: PendingClientMcpCandidate) -> str:
        candidate_id = uuid.uuid4().hex
        with self._lock:
            self._pending[candidate_id] = candidate
            if self._endpoint_address is None:
                self._endpoint_address = default_local_candidate_address()
                reject_network_endpoint_address(self._endpoint_address[1])
        return candidate_id

    def consume_snapshot(self, candidate_id: str) -> SafeCandidateSnapshot:
        should_stop = False
        with self._lock:
            candidate = self._pending.pop(candidate_id, None)
            if candidate is None:
                raise LookupError(candidate_id)
            snapshot = _to_snapshot(candidate_id, candidate)
            should_stop = not self._pending
        if should_stop:
            self._stop_listener()
        return snapshot

    def close(self) -> None:
        with self._lock:
            self._pending.clear()
        self._stop_listener()

    def _start_listener_locked(self) -> None:
        assert self._endpoint_address is not None
        kind, address = self._endpoint_address
        reject_network_endpoint_address(address)
        self._stop.clear()
        self._listener = Listener(address, authkey=self._authkey)
        self._thread = threading.Thread(target=self._serve, name=f"client-mcp-ipc-{kind}", daemon=True)
        self._thread.start()

    def _stop_listener(self) -> None:
        with self._lock:
            self._stop.set()
            listener = self._listener
            thread = self._thread
            endpoint = self._endpoint_address
            self._listener = None
            self._thread = None
        if listener is not None:
            with contextlib.suppress(OSError, ValueError):
                listener.close()
        # consume_snapshot() may stop the listener from inside _serve; never join self.
        if (
            thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(timeout=2.0)
        with self._lock:
            if endpoint is not None and endpoint[0] == "af_unix" and endpoint[1]:
                sock = Path(endpoint[1])
                if sock.exists():
                    with contextlib.suppress(OSError):
                        sock.unlink()
            if not self._pending:
                self._endpoint_address = None

    def _serve(self) -> None:
        while not self._stop.is_set():
            listener = self._listener
            if listener is None:
                return
            conn = None
            try:
                conn = listener.accept()
            except OSError:
                # Closed/interrupted listener while stopping, or transient accept failure.
                conn = None
            if conn is None:
                continue
            try:
                request = conn.recv()
                if not isinstance(request, dict) or request.get("op") != _OP_CONSUME:
                    conn.send({"ok": False, "error": "unsupported_op"})
                    continue
                candidate_id = str(request.get("candidate_id", ""))
                try:
                    snapshot = self.consume_snapshot(candidate_id)
                except LookupError:
                    conn.send({"ok": False, "error": "not_found"})
                else:
                    conn.send({"ok": True, "snapshot": snapshot.__dict__})
            except Exception:
                with contextlib.suppress(OSError, ValueError, BrokenPipeError):
                    conn.send({"ok": False, "error": "ipc_failure"})
            finally:
                with contextlib.suppress(OSError, ValueError):
                    conn.close()

    @staticmethod
    def consume_remote_snapshot(
        *,
        address: str,
        authkey: bytes,
        candidate_id: str,
        timeout_seconds: float = 2.0,
    ) -> SafeCandidateSnapshot:
        reject_network_endpoint_address(address)
        box: dict[str, Any] = {}

        def _run() -> None:
            try:
                with Client(address, authkey=authkey) as conn:
                    conn.send({"op": _OP_CONSUME, "candidate_id": candidate_id})
                    box["response"] = conn.recv()
            except BaseException as exc:  # noqa: BLE001 - marshal to caller thread
                box["error"] = exc

        # Windows AF_PIPE Client() can block indefinitely when no Listener remains
        # (CreateFile/WaitNamedPipe). Bound the wait so ceremony CLI fails closed.
        worker = threading.Thread(target=_run, name="client-mcp-ipc-consume", daemon=True)
        worker.start()
        worker.join(timeout=timeout_seconds)
        if worker.is_alive():
            raise LocalIpcError("client_mcp.ipc_timeout")
        if "error" in box:
            raise LookupError(candidate_id) from box["error"]
        response: dict[str, Any] = box["response"]
        if not response.get("ok"):
            raise LookupError(candidate_id)
        payload = response["snapshot"]
        return SafeCandidateSnapshot(
            candidate_id=str(payload["candidate_id"]),
            workspace_digest=str(payload["workspace_digest"]),
            session_id=str(payload["session_id"]),
            server_name=str(payload["server_name"]),
            transport=str(payload["transport"]),
            canonical_target=str(payload["canonical_target"]),
            arguments=tuple(payload["arguments"]),
            credential_name_fingerprints=tuple(payload["credential_name_fingerprints"]),
            rendered_fingerprint=str(payload["rendered_fingerprint"]),
            provenance=str(payload["provenance"]),
            scanner_rule_ids=tuple(payload["scanner_rule_ids"]),
            safe_identity_summary=str(payload["safe_identity_summary"]),
        )


def _to_snapshot(candidate_id: str, candidate: PendingClientMcpCandidate) -> SafeCandidateSnapshot:
    identity = candidate.identity
    summary = (
        f"{identity.transport}:{identity.server_name}:{identity.canonical_target}:"
        f"{list(identity.arguments)}"
    )
    return SafeCandidateSnapshot(
        candidate_id=candidate_id,
        workspace_digest=candidate.workspace_digest,
        session_id=candidate.session_id,
        server_name=identity.server_name,
        transport=identity.transport,
        canonical_target=identity.canonical_target,
        arguments=identity.arguments,
        credential_name_fingerprints=identity.credential_name_fingerprints,
        rendered_fingerprint=candidate.rendered_fingerprint,
        provenance=candidate.provenance,
        scanner_rule_ids=candidate.scanner_rule_ids,
        safe_identity_summary=summary,
    )
