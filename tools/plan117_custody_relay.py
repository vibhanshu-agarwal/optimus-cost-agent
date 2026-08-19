"""Opaque full-duplex byte relay for Plan 11.7 custody feasibility.

Capture layout (documented): ``{capture-root}/{run-id}/``

  - ``zed-to-agent.bin`` - raw bytes from parent stdin to child stdin
  - ``agent-to-zed.bin`` - raw bytes from child stdout to parent stdout
  - ``relay-index.ndjson`` - gap-free per-chunk index (LF)
  - ``relay-summary.json`` - terminal summary via ``atomic_write_json`` (LF)

CLI::

    plan117_custody_relay.py --capture-root ABS --run-id ID --child-executable ABS -- <argv>

Relay-only args never reach the child. The live path never decodes ACP bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from multiprocessing.connection import AuthenticationError, Client, Listener
from pathlib import Path
from typing import Any, BinaryIO, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.plan117_custody_contract import (  # noqa: E402
    CustodyContractError,
    EvidenceReference,
    LiveSessionProof,
    atomic_create_json,
    atomic_write_json,
    build_live_session_proof,
    sha256_file,
    sha256_hex_equal,
)

SCHEMA_INDEX = "plan117-custody-relay-index-v1"
SCHEMA_SUMMARY = "plan117-custody-relay-summary-v1"
SCHEMA_CONTROL_DESCRIPTOR = "plan117-custody-relay-control-descriptor-v1"
DIR_ZED_TO_AGENT = "zed_to_agent"
DIR_AGENT_TO_ZED = "agent_to_zed"
EOF_ZED_TO_AGENT = "zed_to_agent_eof"
EOF_AGENT_TO_ZED = "agent_to_zed_eof"
RELAY_CHILD_STDERR_NAME = "relay-child-stderr.txt"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
READ_CHUNK = 1 << 16  # 64 KiB
REASON_RECORDER_FAILURE = "relay_recorder_failure"
REASON_INTERRUPTED = "relay_interrupted"
REASON_BROKEN_PIPE = "relay_broken_pipe"
CONTROL_OP_GET_PROOF = "get_live_session_proof"
CONTROL_OP_SEND_PROMPT = "send_existing_session_prompt"
CONTROL_DESCRIPTOR_FILENAME = "relay-control-descriptor.json"

PopenFactory = Callable[..., Any]
ProcessObserver = Callable[[int], "ObservedProcessIdentity | None"]
PromptForwarder = Callable[[bytes], None]


@dataclass(frozen=True)
class ObservedProcessIdentity:
    """Live process identity facts read from the OS/process observer."""

    pid: int
    process_start_time_utc: str
    alive: bool


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _control_error(reason_code: str, field_path: str = "") -> CustodyContractError:
    return CustodyContractError(reason_code, field_path)


def _require_caller_owner_id(caller_owner_id: str | None) -> str:
    """Out-of-band operator identity is mandatory; never infer from the descriptor."""
    if not isinstance(caller_owner_id, str) or not caller_owner_id.strip():
        raise _control_error(
            "invalid_probe_retry_control_channel_failure",
            "caller_owner_id",
        )
    return caller_owner_id


def _reject_network_endpoint_address(address: object) -> None:
    """Fail closed on TCP/IP or host-port network listeners."""
    if isinstance(address, tuple):
        raise _control_error(
            "invalid_probe_retry_control_channel_failure",
            "endpoint_address",
        )
    if isinstance(address, str):
        lowered = address.strip().lower()
        if lowered.startswith("tcp://") or lowered.startswith("http://") or lowered.startswith(
            "https://"
        ):
            raise _control_error(
                "invalid_probe_retry_control_channel_failure",
                "endpoint_address",
            )
        # host:port form (but allow Windows named-pipe paths).
        if (
            "\\" not in address
            and "/" not in address
            and address.count(":") == 1
            and not address.lower().startswith("af_unix:")
        ):
            host, _, port = address.partition(":")
            if host and port.isdigit():
                raise _control_error(
                    "invalid_probe_retry_control_channel_failure",
                    "endpoint_address",
                )


def _default_local_control_address(run_attempt_id: str, custody_root: Path) -> tuple[str, str]:
    """Return (endpoint_kind, address) for a local-only AF_PIPE / AF_UNIX endpoint.

    On POSIX the socket must stay under sockaddr_un.sun_path (~108 bytes). Custody
    roots under pytest/GHA checkouts routinely exceed that, so the descriptor stays
    under ``custody_root`` while the bind path uses the system temp directory.
    """
    token = uuid.uuid4().hex[:16]
    if os.name == "nt":
        pipe = rf"\\.\pipe\plan117-relay-control-{run_attempt_id}-{token}"
        return "af_pipe", pipe
    _ = custody_root  # descriptor lives here; socket path must stay short
    sock = Path(tempfile.gettempdir()) / f"p117rc-{token}.sock"
    if sock.exists():
        sock.unlink()
    return "af_unix", str(sock)


_DESCRIPTOR_DIGEST_EXCLUDE = frozenset(
    {
        "descriptor_sha256",
        "terminal",
        "prompt_sealed",
    }
)


def _descriptor_payload_for_digest(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Locator identity only - mutable terminal flags are never digest-bound."""
    return {
        key: payload[key]
        for key in sorted(payload)
        if key not in _DESCRIPTOR_DIGEST_EXCLUDE
    }


def _descriptor_sha256(payload: Mapping[str, Any]) -> str:
    body = _descriptor_payload_for_digest(payload)
    encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _load_control_descriptor(
    descriptor_path: Path,
    *,
    expected_descriptor_sha256: str,
) -> dict[str, Any]:
    path = Path(descriptor_path)
    if path.is_symlink() or not path.is_file():
        raise _control_error("invalid_probe_retry_control_channel_failure", "descriptor_path")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _control_error(
            "invalid_probe_retry_control_channel_failure",
            "descriptor_path",
        ) from exc
    if not isinstance(payload, dict):
        raise _control_error("invalid_probe_retry_control_channel_failure", "descriptor")
    if payload.get("schema") != SCHEMA_CONTROL_DESCRIPTOR:
        raise _control_error("invalid_probe_retry_control_channel_failure", "schema")
    digest = _descriptor_sha256(payload)
    stored = payload.get("descriptor_sha256")
    if not isinstance(stored, str) or not sha256_hex_equal(digest, stored):
        raise _control_error("invalid_probe_retry_control_channel_failure", "descriptor_sha256")
    if not sha256_hex_equal(digest, expected_descriptor_sha256):
        raise _control_error("invalid_probe_retry_control_channel_failure", "descriptor_sha256")
    if payload.get("prompt_sealed") is True:
        raise _control_error(
            "invalid_probe_retry_second_prompt_failure",
            "prompt_sealed",
        )
    if payload.get("terminal") is True:
        raise _control_error("invalid_probe_retry_control_channel_failure", "descriptor_terminal")
    return payload


def _proof_from_wire(payload: Mapping[str, Any]) -> LiveSessionProof:
    evidence_raw = payload.get("evidence")
    if not isinstance(evidence_raw, list) or not evidence_raw:
        raise _control_error("invalid_probe_retry_proof_unavailable", "evidence")
    evidence: list[EvidenceReference] = []
    for index, item in enumerate(evidence_raw):
        if not isinstance(item, Mapping):
            raise _control_error("invalid_probe_retry_proof_unavailable", f"evidence[{index}]")
        evidence.append(
            EvidenceReference(
                relative_path=str(item["relative_path"]),
                sha256=str(item["sha256"]),
                hash_method=str(item["hash_method"]),
            )
        )
    try:
        return build_live_session_proof(
            run_attempt_id=str(payload["run_attempt_id"]),
            zed_pid=int(payload["zed_pid"]),
            zed_process_start_time_utc=str(payload["zed_process_start_time_utc"]),
            connection_id=str(payload["connection_id"]),
            acp_session_id=str(payload["acp_session_id"]),
            zed_alive=bool(payload["zed_alive"]),
            relay_alive=bool(payload["relay_alive"]),
            acp_session_observed=bool(payload["acp_session_observed"]),
            captured_utc=str(payload["captured_utc"]),
            evidence=evidence,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _control_error("invalid_probe_retry_proof_unavailable", "proof") from exc


def _encode_session_prompt(*, session_id: str, prompt_text: str) -> bytes:
    """Build opaque ACP session/prompt request bytes (never session/new)."""
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "session/prompt",
        "params": {
            "sessionId": session_id,
            "prompt": [{"type": "text", "text": prompt_text}],
        },
    }
    return (json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


class RelayControlRuntime:
    """In-memory live facts for one run-bound relay control endpoint."""

    def __init__(
        self,
        *,
        run_attempt_id: str,
        zed_proc: Any,
        zed_process_start_time_utc: str,
        connection_id: str,
        acp_session_id: str | None,
        evidence: Sequence[EvidenceReference],
        process_observer: ProcessObserver,
        owner_id: str,
        prompt_forward: PromptForwarder,
    ) -> None:
        self.run_attempt_id = run_attempt_id
        self._zed_proc = zed_proc
        self.zed_process_start_time_utc = zed_process_start_time_utc
        self.connection_id = connection_id
        self.acp_session_id = acp_session_id
        self.evidence = tuple(evidence)
        self._process_observer = process_observer
        self.owner_id = owner_id
        self._prompt_forward = prompt_forward
        self._lock = threading.RLock()
        self.connection_eof = False
        self.prompt_forwarded = False
        self.closed = False
        self.relay_alive = True

    def mark_connection_eof(self) -> None:
        with self._lock:
            self.connection_eof = True

    def observe_acp_session(self, session_id: str) -> None:
        with self._lock:
            if not isinstance(session_id, str) or not session_id.strip():
                raise _control_error(
                    "invalid_probe_retry_acp_session_identity_mismatch",
                    "acp_session_id",
                )
            self.acp_session_id = session_id

    def close(self) -> None:
        with self._lock:
            self.closed = True
            self.relay_alive = False

    def _require_live_zed_process_identity(self) -> int:
        """Fail closed unless the relay-owned process PID/start identity is still live."""
        pid = int(getattr(self._zed_proc, "pid", 0) or 0)
        if pid <= 0:
            raise _control_error(
                "invalid_probe_retry_process_identity_mismatch",
                "zed_pid",
            )
        observed = self._process_observer(pid)
        if observed is None:
            raise _control_error(
                "invalid_probe_retry_process_identity_mismatch",
                "zed_process_identity",
            )
        if (
            observed.pid != pid
            or observed.process_start_time_utc != self.zed_process_start_time_utc
            or not observed.alive
        ):
            raise _control_error(
                "invalid_probe_retry_process_identity_mismatch",
                "zed_process_identity",
            )
        poll = getattr(self._zed_proc, "poll", None)
        if callable(poll) and poll() is not None:
            raise _control_error(
                "invalid_probe_retry_process_identity_mismatch",
                "zed_process_identity",
            )
        return pid

    def get_live_session_proof(
        self,
        *,
        run_attempt_id: str,
        descriptor_sha256: str,
        caller_owner_id: str,
        expected_descriptor_sha256: str,
    ) -> LiveSessionProof:
        with self._lock:
            if self.closed or not self.relay_alive:
                raise _control_error(
                    "invalid_probe_retry_control_channel_failure",
                    "relay_closed",
                )
            if caller_owner_id != self.owner_id:
                raise _control_error(
                    "invalid_probe_retry_control_channel_failure",
                    "caller_owner_id",
                )
            if not sha256_hex_equal(descriptor_sha256, expected_descriptor_sha256):
                raise _control_error(
                    "invalid_probe_retry_control_channel_failure",
                    "descriptor_sha256",
                )
            if run_attempt_id != self.run_attempt_id:
                raise _control_error(
                    "invalid_probe_retry_proof_unavailable",
                    "run_attempt_id",
                )
            if self.connection_eof:
                raise _control_error(
                    "invalid_probe_retry_connection_identity_mismatch",
                    "connection_eof",
                )
            pid = self._require_live_zed_process_identity()
            if not self.acp_session_id:
                raise _control_error(
                    "invalid_probe_retry_acp_session_identity_mismatch",
                    "acp_session_id",
                )
            return build_live_session_proof(
                run_attempt_id=self.run_attempt_id,
                zed_pid=pid,
                zed_process_start_time_utc=self.zed_process_start_time_utc,
                connection_id=self.connection_id,
                acp_session_id=self.acp_session_id,
                zed_alive=True,
                relay_alive=True,
                acp_session_observed=True,
                captured_utc=_utc_now_iso(),
                evidence=self.evidence,
            )

    def send_existing_session_prompt(
        self,
        *,
        run_attempt_id: str,
        connection_id: str,
        acp_session_id: str,
        prompt_fixture: Path,
        caller_owner_id: str,
        descriptor_sha256: str,
        expected_descriptor_sha256: str,
    ) -> dict[str, Any]:
        with self._lock:
            if self.closed or not self.relay_alive:
                raise _control_error(
                    "invalid_probe_retry_second_prompt_failure"
                    if self.prompt_forwarded
                    else "invalid_probe_retry_control_channel_failure",
                    "relay_closed",
                )
            if self.prompt_forwarded:
                raise _control_error(
                    "invalid_probe_retry_second_prompt_failure",
                    "prompt_ordinal",
                )
            if caller_owner_id != self.owner_id:
                raise _control_error(
                    "invalid_probe_retry_control_channel_failure",
                    "caller_owner_id",
                )
            if not sha256_hex_equal(descriptor_sha256, expected_descriptor_sha256):
                raise _control_error(
                    "invalid_probe_retry_control_channel_failure",
                    "descriptor_sha256",
                )
            if run_attempt_id != self.run_attempt_id:
                raise _control_error(
                    "invalid_probe_retry_control_channel_failure",
                    "run_attempt_id",
                )
            if self.connection_eof or connection_id != self.connection_id:
                raise _control_error(
                    "invalid_probe_retry_connection_identity_mismatch",
                    "connection_id",
                )
            if not self.acp_session_id or acp_session_id != self.acp_session_id:
                raise _control_error(
                    "invalid_probe_retry_acp_session_identity_mismatch",
                    "acp_session_id",
                )
            # Re-validate live process identity immediately before ACP forward.
            self._require_live_zed_process_identity()
            fixture = Path(prompt_fixture)
            if fixture.is_symlink() or not fixture.is_file():
                raise _control_error(
                    "invalid_probe_retry_control_channel_failure",
                    "prompt_fixture",
                )
            prompt_text = fixture.read_text(encoding="utf-8")
            payload = _encode_session_prompt(
                session_id=self.acp_session_id,
                prompt_text=prompt_text,
            )
            if b"session/new" in payload:
                raise _control_error(
                    "invalid_probe_retry_control_channel_failure",
                    "session_method",
                )
            try:
                self._prompt_forward(payload)
            except Exception as exc:
                raise _control_error(
                    "invalid_probe_retry_control_channel_failure",
                    "prompt_forward",
                ) from exc
            self.prompt_forwarded = True
            return {
                "ok": True,
                "run_attempt_id": self.run_attempt_id,
                "connection_id": self.connection_id,
                "acp_session_id": self.acp_session_id,
                "method": "session/prompt",
            }


class RelayControlEndpoint:
    """Same-run local AF_PIPE/AF_UNIX control server bound to one run attempt."""

    def __init__(
        self,
        *,
        runtime: RelayControlRuntime,
        descriptor_path: Path,
        descriptor_sha256: str,
        endpoint_kind: str,
        endpoint_path: str,
        authkey: bytes,
        listener: Listener,
        serve_thread: threading.Thread,
        stop: threading.Event,
    ) -> None:
        self._runtime = runtime
        self.descriptor_path = Path(descriptor_path)
        self.descriptor_sha256 = descriptor_sha256
        self.endpoint_kind = endpoint_kind
        self.endpoint_path = endpoint_path
        self._authkey = authkey
        self._listener = listener
        self._serve_thread = serve_thread
        self._stop = stop

    @classmethod
    def start(
        cls,
        *,
        run_attempt_id: str,
        custody_root: Path,
        zed_proc: Any,
        zed_process_start_time_utc: str,
        connection_id: str,
        evidence: Sequence[EvidenceReference],
        process_observer: ProcessObserver,
        owner_id: str,
        prompt_forward: PromptForwarder,
        acp_session_id: str | None = None,
        endpoint_address: object | None = None,
    ) -> RelayControlEndpoint:
        if endpoint_address is not None:
            _reject_network_endpoint_address(endpoint_address)
            if not isinstance(endpoint_address, str):
                raise _control_error(
                    "invalid_probe_retry_control_channel_failure",
                    "endpoint_address",
                )
            endpoint_kind = "af_pipe" if endpoint_address.startswith("\\\\.\\pipe\\") else "af_unix"
            address = endpoint_address
        else:
            endpoint_kind, address = _default_local_control_address(
                run_attempt_id,
                Path(custody_root),
            )
        _reject_network_endpoint_address(address)

        custody_root = Path(custody_root)
        custody_root.mkdir(parents=True, exist_ok=True)
        authkey = secrets.token_bytes(32)
        runtime = RelayControlRuntime(
            run_attempt_id=run_attempt_id,
            zed_proc=zed_proc,
            zed_process_start_time_utc=zed_process_start_time_utc,
            connection_id=connection_id,
            acp_session_id=acp_session_id,
            evidence=evidence,
            process_observer=process_observer,
            owner_id=owner_id,
            prompt_forward=prompt_forward,
        )
        try:
            listener = Listener(address, authkey=authkey)
        except OSError as exc:
            raise _control_error(
                "invalid_probe_retry_control_channel_failure",
                "listener",
            ) from exc

        descriptor_path = custody_root / CONTROL_DESCRIPTOR_FILENAME
        provisional = {
            "schema": SCHEMA_CONTROL_DESCRIPTOR,
            "run_attempt_id": run_attempt_id,
            "endpoint_kind": endpoint_kind,
            "endpoint_path": address,
            "connection_id": connection_id,
            "owner_id": owner_id,
            "authkey_hex": authkey.hex(),
            "terminal": False,
        }
        digest = _descriptor_sha256(provisional)
        provisional["descriptor_sha256"] = digest
        try:
            atomic_create_json(descriptor_path, provisional)
        except CustodyContractError:
            try:
                listener.close()
            except OSError:
                pass
            raise
        except Exception as exc:
            try:
                listener.close()
            except OSError:
                pass
            raise _control_error(
                "invalid_probe_retry_control_channel_failure",
                "descriptor_path",
            ) from exc

        stop = threading.Event()
        endpoint = cls(
            runtime=runtime,
            descriptor_path=descriptor_path,
            descriptor_sha256=digest,
            endpoint_kind=endpoint_kind,
            endpoint_path=address,
            authkey=authkey,
            listener=listener,
            serve_thread=threading.Thread(target=lambda: None, daemon=True),
            stop=stop,
        )

        def _serve() -> None:
            endpoint._serve_loop()

        serve_thread = threading.Thread(
            target=_serve,
            name=f"plan117-relay-control-{run_attempt_id}",
            daemon=True,
        )
        endpoint._serve_thread = serve_thread
        serve_thread.start()
        return endpoint

    def mark_connection_eof(self) -> None:
        self._runtime.mark_connection_eof()

    def observe_acp_session(self, session_id: str) -> None:
        self._runtime.observe_acp_session(session_id)

    def close(self) -> None:
        self._runtime.close()
        self._stop.set()

        def _wakeup_accept() -> None:
            try:
                with Client(self.endpoint_path, authkey=self._authkey) as conn:
                    conn.send({"op": "_shutdown"})
            except Exception:
                return

        # Never block forever on Client(): after prompt seal the serve loop may
        # already have exited, leaving no acceptor for a wakeup connect.
        if self._serve_thread.is_alive():
            waker = threading.Thread(
                target=_wakeup_accept,
                name="plan117-relay-control-wakeup",
                daemon=True,
            )
            waker.start()
            waker.join(timeout=1.0)
        try:
            self._listener.close()
        except OSError:
            pass
        self._serve_thread.join(timeout=2.0)
        self._mark_descriptor_terminal(
            prompt_sealed=self._runtime.prompt_forwarded,
        )
        if self.endpoint_kind == "af_unix":
            try:
                Path(self.endpoint_path).unlink(missing_ok=True)
            except OSError:
                pass

    def _mark_descriptor_terminal(self, *, prompt_sealed: bool = False) -> None:
        try:
            payload = json.loads(self.descriptor_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        payload["terminal"] = True
        if prompt_sealed or payload.get("prompt_sealed") is True:
            payload["prompt_sealed"] = True
        payload["descriptor_sha256"] = _descriptor_sha256(payload)
        try:
            atomic_write_json(self.descriptor_path, payload)
        except Exception:
            pass

    def _serve_loop(self) -> None:
        while not self._stop.is_set() and not self._runtime.closed:
            try:
                connection = self._listener.accept()
            except (OSError, EOFError, AuthenticationError):
                if self._stop.is_set() or self._runtime.closed:
                    return
                continue
            except Exception:
                if self._stop.is_set() or self._runtime.closed:
                    return
                continue
            try:
                with connection:
                    try:
                        request = connection.recv()
                    except (EOFError, OSError):
                        continue
                    if not isinstance(request, Mapping):
                        connection.send(
                            {
                                "ok": False,
                                "reason_code": "invalid_probe_retry_control_channel_failure",
                                "field_path": "request",
                            }
                        )
                        continue
                    if request.get("op") == "_shutdown":
                        return
                    response = self._dispatch(request)
                    connection.send(response)
            except Exception:
                continue

    def _dispatch(self, request: Mapping[str, Any]) -> dict[str, Any]:
        op = request.get("op")
        try:
            if op == CONTROL_OP_GET_PROOF:
                caller = _require_caller_owner_id(
                    request.get("caller_owner_id")
                    if isinstance(request.get("caller_owner_id"), str)
                    else None
                )
                proof = self._runtime.get_live_session_proof(
                    run_attempt_id=str(request.get("run_attempt_id", "")),
                    descriptor_sha256=str(request.get("descriptor_sha256", "")),
                    caller_owner_id=caller,
                    expected_descriptor_sha256=self.descriptor_sha256,
                )
                return {
                    "ok": True,
                    "proof": {
                        "run_attempt_id": proof.run_attempt_id,
                        "zed_pid": proof.zed_pid,
                        "zed_process_start_time_utc": proof.zed_process_start_time_utc,
                        "connection_id": proof.connection_id,
                        "acp_session_id": proof.acp_session_id,
                        "zed_alive": proof.zed_alive,
                        "relay_alive": proof.relay_alive,
                        "acp_session_observed": proof.acp_session_observed,
                        "captured_utc": proof.captured_utc,
                        "evidence": [
                            {
                                "relative_path": item.relative_path,
                                "sha256": item.sha256,
                                "hash_method": item.hash_method,
                            }
                            for item in proof.evidence
                        ],
                        "proof_sha256": proof.proof_sha256,
                    },
                }
            if op == CONTROL_OP_SEND_PROMPT:
                caller = _require_caller_owner_id(
                    request.get("caller_owner_id")
                    if isinstance(request.get("caller_owner_id"), str)
                    else None
                )
                result = self._runtime.send_existing_session_prompt(
                    run_attempt_id=str(request.get("run_attempt_id", "")),
                    connection_id=str(request.get("connection_id", "")),
                    acp_session_id=str(request.get("acp_session_id", "")),
                    prompt_fixture=Path(str(request.get("prompt_fixture", ""))),
                    caller_owner_id=caller,
                    descriptor_sha256=str(request.get("descriptor_sha256", "")),
                    expected_descriptor_sha256=self.descriptor_sha256,
                )
                # Seal control path after terminal prompt outcome.
                self._runtime.close()
                self._stop.set()
                self._mark_descriptor_terminal(prompt_sealed=True)
                return result
            raise _control_error(
                "invalid_probe_retry_control_channel_failure",
                "op",
            )
        except CustodyContractError as exc:
            return {
                "ok": False,
                "reason_code": exc.reason_code,
                "field_path": exc.field_path,
            }


def _control_request(
    *,
    descriptor_path: Path,
    expected_descriptor_sha256: str,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    descriptor = _load_control_descriptor(
        descriptor_path,
        expected_descriptor_sha256=expected_descriptor_sha256,
    )
    endpoint_path = descriptor.get("endpoint_path")
    authkey_hex = descriptor.get("authkey_hex")
    if not isinstance(endpoint_path, str) or not endpoint_path:
        raise _control_error("invalid_probe_retry_control_channel_failure", "endpoint_path")
    if not isinstance(authkey_hex, str) or not authkey_hex:
        raise _control_error("invalid_probe_retry_control_channel_failure", "authkey_hex")
    _reject_network_endpoint_address(endpoint_path)
    try:
        authkey = bytes.fromhex(authkey_hex)
    except ValueError as exc:
        raise _control_error(
            "invalid_probe_retry_control_channel_failure",
            "authkey_hex",
        ) from exc
    try:
        with Client(endpoint_path, authkey=authkey) as conn:
            conn.send(dict(request))
            response = conn.recv()
    except Exception as exc:
        raise _control_error(
            "invalid_probe_retry_control_channel_failure",
            "control_channel",
        ) from exc
    if not isinstance(response, Mapping):
        raise _control_error("invalid_probe_retry_control_channel_failure", "response")
    return dict(response)


def acquire_live_session_proof(
    *,
    run_attempt_id: str,
    descriptor_path: Path,
    expected_descriptor_sha256: str,
    caller_owner_id: str | None = None,
) -> LiveSessionProof:
    """Query the active relay control path; never reconstruct proof from the descriptor."""
    caller = _require_caller_owner_id(caller_owner_id)
    # Descriptor is loaded only as a locator after operator identity is present.
    _load_control_descriptor(
        descriptor_path,
        expected_descriptor_sha256=expected_descriptor_sha256,
    )
    response = _control_request(
        descriptor_path=descriptor_path,
        expected_descriptor_sha256=expected_descriptor_sha256,
        request={
            "op": CONTROL_OP_GET_PROOF,
            "run_attempt_id": run_attempt_id,
            "descriptor_sha256": expected_descriptor_sha256,
            "caller_owner_id": caller,
        },
    )
    if not response.get("ok"):
        reason = str(response.get("reason_code") or "invalid_probe_retry_proof_unavailable")
        field = str(response.get("field_path") or "")
        raise CustodyContractError(reason, field)
    proof_payload = response.get("proof")
    if not isinstance(proof_payload, Mapping):
        raise _control_error("invalid_probe_retry_proof_unavailable", "proof")
    proof = _proof_from_wire(proof_payload)
    # Never trust wire digest alone - rebind via builder.
    if proof.run_attempt_id != run_attempt_id:
        raise _control_error("invalid_probe_retry_proof_unavailable", "run_attempt_id")
    wire_digest = proof_payload.get("proof_sha256")
    if not isinstance(wire_digest, str) or not sha256_hex_equal(wire_digest, proof.proof_sha256):
        raise _control_error("invalid_probe_retry_proof_unavailable", "proof_sha256")
    return proof


def send_existing_session_prompt(
    *,
    run_attempt_id: str,
    descriptor_path: Path,
    expected_descriptor_sha256: str,
    connection_id: str,
    acp_session_id: str,
    prompt_fixture: Path,
    caller_owner_id: str | None = None,
) -> dict[str, Any]:
    """Forward exactly one session/prompt over the existing ACP connection."""
    caller = _require_caller_owner_id(caller_owner_id)
    _load_control_descriptor(
        descriptor_path,
        expected_descriptor_sha256=expected_descriptor_sha256,
    )
    response = _control_request(
        descriptor_path=descriptor_path,
        expected_descriptor_sha256=expected_descriptor_sha256,
        request={
            "op": CONTROL_OP_SEND_PROMPT,
            "run_attempt_id": run_attempt_id,
            "descriptor_sha256": expected_descriptor_sha256,
            "caller_owner_id": caller,
            "connection_id": connection_id,
            "acp_session_id": acp_session_id,
            "prompt_fixture": str(Path(prompt_fixture)),
        },
    )
    if not response.get("ok"):
        reason = str(
            response.get("reason_code") or "invalid_probe_retry_control_channel_failure"
        )
        field = str(response.get("field_path") or "")
        raise CustodyContractError(reason, field)
    return {
        "ok": True,
        "run_attempt_id": str(response.get("run_attempt_id") or run_attempt_id),
        "connection_id": str(response.get("connection_id") or connection_id),
        "acp_session_id": str(response.get("acp_session_id") or acp_session_id),
        "method": str(response.get("method") or "session/prompt"),
    }


class RelayRecorderError(RuntimeError):
    """Internal recorder failure; never falls back to an uncaptured path."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


class _LockedRecorder:
    """Append-only raw + index recorder with one lock for both directions."""

    def __init__(self, run_dir: Path, run_id: str, origin_monotonic: float) -> None:
        self._lock = threading.Lock()
        self._run_id = run_id
        self._origin = origin_monotonic
        self._sequence = 0
        self._offsets = {DIR_ZED_TO_AGENT: 0, DIR_AGENT_TO_ZED: 0}
        self._failed = False
        self._reason: str | None = None
        run_dir.mkdir(parents=True, exist_ok=True)
        self._bins = {
            DIR_ZED_TO_AGENT: (run_dir / "zed-to-agent.bin").open("wb"),
            DIR_AGENT_TO_ZED: (run_dir / "agent-to-zed.bin").open("wb"),
        }
        self._index = (run_dir / "relay-index.ndjson").open("w", encoding="utf-8", newline="\n")

    @property
    def failed(self) -> bool:
        return self._failed

    @property
    def reason_code(self) -> str | None:
        return self._reason

    def record_chunk(self, direction: str, chunk: bytes) -> None:
        if direction not in self._bins:
            raise RelayRecorderError("relay_invalid_direction")
        with self._lock:
            if self._failed:
                raise RelayRecorderError(self._reason or REASON_RECORDER_FAILURE)
            try:
                handle = self._bins[direction]
                offset = self._offsets[direction]
                handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
                digest = hashlib.sha256(chunk).hexdigest()
                record = {
                    "schema": SCHEMA_INDEX,
                    "run_id": self._run_id,
                    "sequence": self._sequence,
                    "direction": direction,
                    "monotonic_offset_ns": int((time.monotonic() - self._origin) * 1_000_000_000),
                    "directional_offset": offset,
                    "size": len(chunk),
                    "sha256": digest,
                }
                self._index.write(json.dumps(record, separators=(",", ":"), sort_keys=True))
                self._index.write("\n")
                self._index.flush()
                os.fsync(self._index.fileno())
                self._sequence += 1
                self._offsets[direction] = offset + len(chunk)
            except (OSError, ValueError) as exc:
                self._failed = True
                self._reason = REASON_RECORDER_FAILURE
                raise RelayRecorderError(REASON_RECORDER_FAILURE) from exc

    def record_eof(self, direction: str) -> None:
        eof_direction = {
            DIR_ZED_TO_AGENT: EOF_ZED_TO_AGENT,
            DIR_AGENT_TO_ZED: EOF_AGENT_TO_ZED,
        }[direction]
        with self._lock:
            if self._failed:
                raise RelayRecorderError(self._reason or REASON_RECORDER_FAILURE)
            try:
                record = {
                    "schema": SCHEMA_INDEX,
                    "run_id": self._run_id,
                    "sequence": self._sequence,
                    "direction": eof_direction,
                    "monotonic_offset_ns": int((time.monotonic() - self._origin) * 1_000_000_000),
                    "directional_offset": self._offsets[direction],
                    "size": 0,
                    "sha256": EMPTY_SHA256,
                }
                self._index.write(json.dumps(record, separators=(",", ":"), sort_keys=True))
                self._index.write("\n")
                self._index.flush()
                os.fsync(self._index.fileno())
                self._sequence += 1
            except (OSError, ValueError) as exc:
                self._failed = True
                self._reason = REASON_RECORDER_FAILURE
                raise RelayRecorderError(REASON_RECORDER_FAILURE) from exc

    def close(self) -> None:
        with self._lock:
            for handle in self._bins.values():
                try:
                    handle.close()
                except OSError:
                    pass
            try:
                self._index.close()
            except OSError:
                pass

    def totals(self) -> dict[str, int]:
        with self._lock:
            return dict(self._offsets)


def _read_pipe_chunk(stream: BinaryIO, size: int) -> bytes:
    """Read up to ``size`` bytes without waiting for a full buffer fill.

    Prefer ``read1`` so full-duplex Windows pipe relays do not deadlock when the
    peer is waiting for output before sending ``size`` more stdin bytes.
    """
    read1 = getattr(stream, "read1", None)
    if callable(read1):
        return read1(size)
    return stream.read(size)


def _forward_parent_to_child(
    *,
    parent_in: BinaryIO,
    child_stdin: BinaryIO,
    recorder: _LockedRecorder,
    stop: threading.Event,
    errors: list[BaseException],
) -> None:
    try:
        while not stop.is_set():
            chunk = _read_pipe_chunk(parent_in, READ_CHUNK)
            if not chunk:
                break
            recorder.record_chunk(DIR_ZED_TO_AGENT, chunk)
            try:
                child_stdin.write(chunk)
                child_stdin.flush()
            except BrokenPipeError as exc:
                errors.append(exc)
                return
        recorder.record_eof(DIR_ZED_TO_AGENT)
        try:
            child_stdin.close()
        except OSError:
            pass
    except (RelayRecorderError, KeyboardInterrupt, OSError) as exc:
        errors.append(exc)


def _forward_child_to_parent(
    *,
    child_stdout: BinaryIO,
    parent_out: BinaryIO,
    recorder: _LockedRecorder,
    stop: threading.Event,
    errors: list[BaseException],
) -> None:
    try:
        while not stop.is_set():
            chunk = _read_pipe_chunk(child_stdout, READ_CHUNK)
            if not chunk:
                break
            recorder.record_chunk(DIR_AGENT_TO_ZED, chunk)
            parent_out.write(chunk)
            parent_out.flush()
        recorder.record_eof(DIR_AGENT_TO_ZED)
    except (RelayRecorderError, KeyboardInterrupt, OSError) as exc:
        errors.append(exc)


def _terminate_owned_child(proc: Any) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
    except OSError:
        pass
    try:
        proc.wait(timeout=2.0)
    except Exception:
        try:
            proc.kill()
        except OSError:
            pass
        try:
            proc.wait(timeout=2.0)
        except Exception:
            pass


def _close_child_pipes(proc: Any) -> None:
    for name in ("stdin", "stdout"):
        stream = getattr(proc, name, None)
        if stream is None:
            continue
        try:
            stream.close()
        except OSError:
            pass


def _argv_digest(argv: Sequence[str]) -> str:
    encoded = "\0".join(argv).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _relay_module_digest() -> str:
    return sha256_file(Path(__file__).resolve())


def _emit_stderr(stderr: TextIO | BinaryIO, reason_code: str) -> None:
    line = reason_code + "\n"
    try:
        # Prefer text path for TextIO / StringIO; fall back to bytes for binary buffers.
        write = stderr.write
        try:
            write(line)  # type: ignore[arg-type]
        except TypeError:
            write(line.encode("utf-8"))  # type: ignore[arg-type]
        stderr.flush()
    except OSError:
        pass


def _open_private_child_stderr(run_dir: Path) -> BinaryIO:
    """Open the relay-child private stderr sink under a throwaway run-id directory."""
    return (Path(run_dir) / RELAY_CHILD_STDERR_NAME).open("wb")


def _write_summary(
    run_dir: Path,
    *,
    run_id: str,
    child_argv: Sequence[str],
    child_exit_code: int | None,
    totals: dict[str, int],
    zed_eof: bool,
    agent_eof: bool,
    terminal_disposition: str,
    reason_code: str | None,
) -> None:
    argv_list = [str(item) for item in child_argv]
    payload = {
        "schema": SCHEMA_SUMMARY,
        "run_id": run_id,
        "child_argv": argv_list,
        "child_argv_sha256": _argv_digest(argv_list),
        "relay_sha256": _relay_module_digest(),
        "child_exit_code": child_exit_code,
        "zed_to_agent_bytes": totals.get(DIR_ZED_TO_AGENT, 0),
        "agent_to_zed_bytes": totals.get(DIR_AGENT_TO_ZED, 0),
        "zed_to_agent_eof": zed_eof,
        "agent_to_zed_eof": agent_eof,
        "terminal_disposition": terminal_disposition,
        "reason_code": reason_code,
    }
    atomic_write_json(run_dir / "relay-summary.json", payload)


def run_relay(
    *,
    capture_root: Path,
    run_id: str,
    child_executable: str | Path,
    child_args: Sequence[str],
    stdin: BinaryIO | None = None,
    stdout: BinaryIO | None = None,
    stderr: TextIO | BinaryIO | None = None,
    popen_factory: PopenFactory | None = None,
    recorder_hook: Callable[[_LockedRecorder], None] | None = None,
) -> int:
    """Launch the child and relay opaque bytes; return the child exit code (or nonzero on failure)."""
    parent_in = stdin if stdin is not None else sys.stdin.buffer
    parent_out = stdout if stdout is not None else sys.stdout.buffer
    err_out: TextIO | BinaryIO = stderr if stderr is not None else sys.stderr
    run_dir = Path(capture_root) / run_id
    child_argv = [str(child_executable), *[str(a) for a in child_args]]
    factory = popen_factory or subprocess.Popen
    origin = time.monotonic()
    recorder = _LockedRecorder(run_dir, run_id, origin)
    if recorder_hook is not None:
        recorder_hook(recorder)

    stop = threading.Event()
    errors: list[BaseException] = []
    proc: Any | None = None
    child_stderr: BinaryIO | None = None
    terminal_disposition = "child_exited"
    reason_code: str | None = None
    child_exit: int | None = None

    try:
        child_stderr = _open_private_child_stderr(run_dir)
        proc = factory(
            child_argv,
            env=None,
            cwd=None,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=child_stderr,
            shell=False,
            bufsize=0,
        )
        assert proc.stdin is not None
        assert proc.stdout is not None

        t_in = threading.Thread(
            target=_forward_parent_to_child,
            kwargs={
                "parent_in": parent_in,
                "child_stdin": proc.stdin,
                "recorder": recorder,
                "stop": stop,
                "errors": errors,
            },
            name="relay-zed-to-agent",
            daemon=True,
        )
        t_out = threading.Thread(
            target=_forward_child_to_parent,
            kwargs={
                "child_stdout": proc.stdout,
                "parent_out": parent_out,
                "recorder": recorder,
                "stop": stop,
                "errors": errors,
            },
            name="relay-agent-to-zed",
            daemon=True,
        )
        t_in.start()
        t_out.start()
        t_in.join()
        t_out.join()

        if errors:
            first = errors[0]
            if isinstance(first, KeyboardInterrupt):
                terminal_disposition = "interrupted"
                reason_code = REASON_INTERRUPTED
            elif isinstance(first, RelayRecorderError):
                terminal_disposition = "recorder_failure"
                reason_code = first.reason_code
            elif isinstance(first, BrokenPipeError):
                child_exit = proc.poll()
                stop.set()
                _close_child_pipes(proc)
                if child_exit is not None:
                    terminal_disposition = "child_exited"
                    reason_code = None
                    return_code = int(child_exit)
                else:
                    terminal_disposition = "broken_pipe"
                    reason_code = REASON_BROKEN_PIPE
                    _terminate_owned_child(proc)
                    _emit_stderr(err_out, reason_code)
                    return_code = 1
            else:
                terminal_disposition = "recorder_failure"
                reason_code = REASON_RECORDER_FAILURE
            if not isinstance(first, BrokenPipeError):
                stop.set()
                _close_child_pipes(proc)
                _terminate_owned_child(proc)
                _emit_stderr(err_out, reason_code)
                child_exit = proc.poll()
                if child_exit is None:
                    child_exit = 1
                return_code = 1 if reason_code else int(child_exit)
        else:
            child_exit = proc.wait()
            return_code = int(child_exit)
    except KeyboardInterrupt:
        terminal_disposition = "interrupted"
        reason_code = REASON_INTERRUPTED
        if proc is not None:
            _close_child_pipes(proc)
            _terminate_owned_child(proc)
        _emit_stderr(err_out, reason_code)
        return_code = 1
        child_exit = proc.poll() if proc is not None else 1
    except Exception:
        terminal_disposition = "recorder_failure"
        reason_code = REASON_RECORDER_FAILURE
        if proc is not None:
            _close_child_pipes(proc)
            _terminate_owned_child(proc)
        _emit_stderr(err_out, reason_code)
        return_code = 1
        child_exit = proc.poll() if proc is not None else 1
    finally:
        if child_stderr is not None:
            try:
                child_stderr.close()
            except OSError:
                pass
        totals = recorder.totals()
        index_path = run_dir / "relay-index.ndjson"
        zed_eof = False
        agent_eof = False
        recorder.close()
        if index_path.is_file():
            try:
                for line in index_path.read_text(encoding="utf-8").splitlines():
                    if not line:
                        continue
                    record = json.loads(line)
                    if record.get("direction") == EOF_ZED_TO_AGENT:
                        zed_eof = True
                    elif record.get("direction") == EOF_AGENT_TO_ZED:
                        agent_eof = True
            except (OSError, json.JSONDecodeError):
                pass
        try:
            _write_summary(
                run_dir,
                run_id=run_id,
                child_argv=child_argv,
                child_exit_code=child_exit,
                totals=totals,
                zed_eof=zed_eof,
                agent_eof=agent_eof,
                terminal_disposition=terminal_disposition,
                reason_code=reason_code,
            )
        except Exception:
            # Summary write failure still leaves prior reason on stderr.
            if reason_code is None:
                reason_code = REASON_RECORDER_FAILURE
                _emit_stderr(err_out, reason_code)
            return_code = 1

    return int(return_code)


def verify_relay_capture(run_dir: Path) -> None:
    """Offline verification of a relay capture directory.

    Rejects mutated raw bytes, chunk sizes, offsets, sequences, directions,
    digests, run IDs, child argv digest, relay digest, and terminal exit
    records. Requires both directional EOF markers.
    """
    run_dir = Path(run_dir)
    summary_path = run_dir / "relay-summary.json"
    index_path = run_dir / "relay-index.ndjson"
    zed_path = run_dir / "zed-to-agent.bin"
    agent_path = run_dir / "agent-to-zed.bin"

    for path, field in (
        (summary_path, "relay-summary.json"),
        (index_path, "relay-index.ndjson"),
        (zed_path, "zed-to-agent.bin"),
        (agent_path, "agent-to-zed.bin"),
    ):
        if not path.is_file() or path.is_symlink():
            raise CustodyContractError("relay_capture_incomplete", field)

    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CustodyContractError("relay_summary_invalid", "relay-summary.json") from exc
    if not isinstance(summary, dict):
        raise CustodyContractError("relay_summary_invalid", "relay-summary.json")
    if summary.get("schema") != SCHEMA_SUMMARY:
        raise CustodyContractError("relay_summary_schema_mismatch", "schema")
    run_id = summary.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise CustodyContractError("relay_run_id_invalid", "run_id")

    if "child_argv_sha256" not in summary or not isinstance(summary["child_argv_sha256"], str):
        raise CustodyContractError("relay_child_argv_digest_missing", "child_argv_sha256")
    child_argv = summary.get("child_argv")
    if not isinstance(child_argv, list) or not all(isinstance(item, str) for item in child_argv):
        raise CustodyContractError("relay_child_argv_missing", "child_argv")
    expected_argv_digest = _argv_digest(child_argv)
    if str(summary["child_argv_sha256"]).lower() != expected_argv_digest.lower():
        raise CustodyContractError("relay_child_argv_digest_mismatch", "child_argv_sha256")
    if "relay_sha256" not in summary or not isinstance(summary["relay_sha256"], str):
        raise CustodyContractError("relay_digest_missing", "relay_sha256")
    if "terminal_disposition" not in summary:
        raise CustodyContractError("relay_terminal_disposition_missing", "terminal_disposition")
    if "child_exit_code" not in summary:
        raise CustodyContractError("relay_terminal_exit_missing", "child_exit_code")

    expected_relay = _relay_module_digest()
    if str(summary["relay_sha256"]).lower() != expected_relay.lower():
        raise CustodyContractError("relay_digest_mismatch", "relay_sha256")

    zed_raw = zed_path.read_bytes()
    agent_raw = agent_path.read_bytes()
    if int(summary.get("zed_to_agent_bytes", -1)) != len(zed_raw):
        raise CustodyContractError("relay_directional_length_mismatch", "zed_to_agent_bytes")
    if int(summary.get("agent_to_zed_bytes", -1)) != len(agent_raw):
        raise CustodyContractError("relay_directional_length_mismatch", "agent_to_zed_bytes")

    try:
        lines = index_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise CustodyContractError("relay_index_unreadable", "relay-index.ndjson") from exc

    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(lines):
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CustodyContractError("relay_index_invalid", f"relay-index.ndjson:{line_no}") from exc
        if not isinstance(record, dict):
            raise CustodyContractError("relay_index_invalid", f"relay-index.ndjson:{line_no}")
        records.append(record)

    if not records:
        raise CustodyContractError("relay_index_empty", "relay-index.ndjson")

    seen_eof = {EOF_ZED_TO_AGENT: False, EOF_AGENT_TO_ZED: False}
    expected_seq = 0
    cursors = {DIR_ZED_TO_AGENT: 0, DIR_AGENT_TO_ZED: 0}
    blobs = {DIR_ZED_TO_AGENT: zed_raw, DIR_AGENT_TO_ZED: agent_raw}
    prev_mono = -1

    for index, record in enumerate(records):
        field = f"relay-index.ndjson[{index}]"
        if record.get("schema") != SCHEMA_INDEX:
            raise CustodyContractError("relay_index_schema_mismatch", f"{field}.schema")
        if record.get("run_id") != run_id:
            raise CustodyContractError("relay_run_id_mismatch", f"{field}.run_id")
        if int(record.get("sequence", -1)) != expected_seq:
            raise CustodyContractError("relay_sequence_gap", f"{field}.sequence")
        expected_seq += 1
        mono = int(record.get("monotonic_offset_ns", -1))
        if mono < prev_mono:
            raise CustodyContractError("relay_monotonic_regression", f"{field}.monotonic_offset_ns")
        prev_mono = mono
        direction = record.get("direction")
        if direction in (EOF_ZED_TO_AGENT, EOF_AGENT_TO_ZED):
            if int(record.get("size", -1)) != 0:
                raise CustodyContractError("relay_eof_size_nonzero", f"{field}.size")
            if record.get("sha256") != EMPTY_SHA256:
                raise CustodyContractError("relay_eof_digest_mismatch", f"{field}.sha256")
            base = DIR_ZED_TO_AGENT if direction == EOF_ZED_TO_AGENT else DIR_AGENT_TO_ZED
            if int(record.get("directional_offset", -1)) != cursors[base]:
                raise CustodyContractError("relay_offset_mismatch", f"{field}.directional_offset")
            seen_eof[direction] = True
            continue
        if direction not in blobs:
            raise CustodyContractError("relay_direction_invalid", f"{field}.direction")
        size = int(record.get("size", -1))
        offset = int(record.get("directional_offset", -1))
        if size < 0:
            raise CustodyContractError("relay_chunk_size_invalid", f"{field}.size")
        if offset != cursors[direction]:
            raise CustodyContractError("relay_offset_mismatch", f"{field}.directional_offset")
        chunk = blobs[direction][offset : offset + size]
        if len(chunk) != size:
            raise CustodyContractError("relay_raw_bytes_mismatch", f"{field}.size")
        digest = hashlib.sha256(chunk).hexdigest()
        if digest != record.get("sha256"):
            raise CustodyContractError("relay_chunk_digest_mismatch", f"{field}.sha256")
        cursors[direction] = offset + size

    if cursors[DIR_ZED_TO_AGENT] != len(zed_raw) or cursors[DIR_AGENT_TO_ZED] != len(agent_raw):
        raise CustodyContractError("relay_raw_bytes_mismatch", "directional_bins")

    if not seen_eof[EOF_ZED_TO_AGENT] or not summary.get("zed_to_agent_eof"):
        raise CustodyContractError("relay_missing_directional_eof", "zed_to_agent_eof")
    if not seen_eof[EOF_AGENT_TO_ZED] or not summary.get("agent_to_zed_eof"):
        raise CustodyContractError("relay_missing_directional_eof", "agent_to_zed_eof")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--child-executable", type=Path, required=True)
    parser.add_argument(
        "child_args",
        nargs=argparse.REMAINDER,
        help="Exact child argv after --",
    )
    args = parser.parse_args(argv)
    child_args = list(args.child_args)
    if child_args and child_args[0] == "--":
        child_args = child_args[1:]
    return run_relay(
        capture_root=args.capture_root.resolve(),
        run_id=args.run_id,
        child_executable=args.child_executable.resolve(),
        child_args=child_args,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
