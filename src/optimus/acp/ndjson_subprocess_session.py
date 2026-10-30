from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from typing import Any, Never

from optimus.acp.admission import DEFAULT_LIMITS, AdmissionAccount, AdmissionClass, AdmissionLimits, Reservation
from optimus.acp.e2e_transcript import E2eAcpTranscriptWriter
from optimus_security.sanitization import sanitize_for_persistence


class LiveSessionError(Exception):
    def __init__(self, message: str, *, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr


_GATE_REJECTION_PREFIX = "optimus-agent: "


def _extract_gate_rejection_message(stderr_text: str) -> str | None:
    """If stderr contains a value-free launch-gate rejection (printed by
    __main__.py's _authorize_or_exit/main() before any Redis/Gateway/agent/
    ACP-protocol activity), return that message CLEANLY — with no
    "timed out"/"exited early" wrapper prepended, since the gate rejection
    happens before the ACP protocol handshake even begins and is not a
    timeout in any meaningful sense.

    All of __main__.py's own error prints use this exact "optimus-agent: "
    prefix (LaunchGateError codes, NO_APPROVAL/SNAPSHOT_MISMATCH
    remediation, OperatorPathConfigurationError messages, TrustedPathError
    messages) — this checks for the prefix rather than a specific code so a
    newly added rejection message is picked up automatically without this
    function needing to enumerate every current and future LaunchGateError
    code by hand.
    """
    for line in stderr_text.splitlines():
        if line.startswith(_GATE_REJECTION_PREFIX):
            # Return from the first matching line through the end of
            # stderr, since remediation messages span multiple lines (e.g.
            # NO_APPROVAL's "Review the effective configuration and author
            # one with:\n  optimus-trust ... approve --mode durable").
            start = stderr_text.index(line)
            return stderr_text[start:].rstrip("\n")
    return None


class NdjsonSubprocessSession:
    """
    Handles a subprocess session that communicates using newline-delimited JSON (NDJSON) format.

    This class provides methods to send messages to, read responses from, and control a subprocess
    that reads and writes NDJSON-formatted messages. It also logs inbound and outbound communications
    and manages subprocess lifecycle and error handling.

    :ivar process: The subprocess instance to communicate with.
    :type process: subprocess.Popen[str]
    :ivar transcript: The transcript writer that records inbound and outbound messages.
    :type transcript: E2eAcpTranscriptWriter
    """
    def __init__(self, *, process: subprocess.Popen[str], transcript: E2eAcpTranscriptWriter, limits: AdmissionLimits = DEFAULT_LIMITS) -> None:
        self._process = process
        self._transcript = transcript
        self._limits = limits
        self._inbound: queue.Queue[tuple[dict[str, Any], Reservation]] = queue.Queue(maxsize=limits.subprocess_items)
        self._admission = AdmissionAccount(count=limits.subprocess_items, bytes=limits.inbound_bytes, queue_id="subprocess")
        self._stdout_done = threading.Event()
        self._fatal: str | None = None
        self._stderr_lines: deque[str] = deque()
        self._stderr_lock = threading.Lock()
        self._stderr_bytes = 0
        self._stderr_omitted = 0
        self._gate_rejection = ""
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_reader = threading.Thread(target=self._read_stderr, daemon=True)
        self._reader.start()
        self._stderr_reader.start()

    def send(self, message: Mapping[str, object]) -> None:
        self._check_fatal()
        if self._process.stdin is None:
            raise LiveSessionError("subprocess stdin is not available")
        payload = dict(message)
        self._transcript.record_outbound(payload)
        try:
            self._process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
            self._process.stdin.flush()
        except OSError:
            # The child already exited and closed its end of the pipe before
            # this write landed -- the same race wait_for()/read_next()
            # detect via poll() after the fact. Delegate to the shared
            # _fail_subprocess_exited(), which itself waits for the process
            # and drains the stderr reader before building its message, so a
            # send-time pipe closure produces the identical clean,
            # value-free LiveSessionError a read-time exit already
            # produces, instead of letting a raw OSError escape.
            self._fail_subprocess_exited("ACP subprocess stdin closed while sending an ndjson message")

    def close_stdin(self) -> None:
        if self._process.stdin is not None:
            try:
                self._process.stdin.close()
            except OSError:
                # Best-effort cleanup only: a child that already closed its
                # end of the pipe makes this close() redundant, not an error.
                pass

    def wait_for(  # noqa: RET503 - terminal _fail_timeout/_fail_subprocess_exited helpers return Never
        self,
        *,
        deadline: float,
        predicate: Callable[[dict[str, Any]], bool],
        error_message: str,
    ) -> dict[str, Any]:
        while time.monotonic() < deadline:
            self._check_fatal()
            if self._process.poll() is not None:
                self._fail_subprocess_exited(error_message)
            try:
                message, reservation = self._inbound.get(timeout=min(0.2, max(0.0, deadline - time.monotonic())))
            except queue.Empty:
                self._check_fatal()
                if not self._stdout_done.is_set():
                    continue
                try:
                    message, reservation = self._inbound.get_nowait()
                except queue.Empty:
                    self._fail_subprocess_exited(error_message)
            reservation.release()
            self._check_fatal()
            if predicate(message):
                return message
        self._fail_timeout(error_message)

    def wait_for_response(self, request_id: str | int, *, deadline: float) -> dict[str, Any]:
        return self.wait_for(
            deadline=deadline,
            predicate=lambda message: message.get("id") == request_id and ("result" in message or "error" in message),
            error_message=f"timed out waiting for JSON-RPC response id={request_id!r}",
        )

    def wait_for_request(self, method: str, *, deadline: float) -> dict[str, Any]:
        return self.wait_for(
            deadline=deadline,
            predicate=lambda message: message.get("method") == method and "result" not in message and "error" not in message,
            error_message=f"timed out waiting for JSON-RPC request method={method!r}",
        )

    def read_next(self, *, deadline: float) -> dict[str, Any] | None:
        self._check_fatal()
        if self._process.poll() is not None:
            self._fail_subprocess_exited("ACP subprocess exited while waiting for ndjson traffic")
        try:
            message, reservation = self._inbound.get(timeout=max(0.0, min(0.2, deadline - time.monotonic())))
        except queue.Empty:
            self._check_fatal()
            if not self._stdout_done.is_set():
                return None
            try:
                message, reservation = self._inbound.get_nowait()
            except queue.Empty:
                self._fail_subprocess_exited("ACP subprocess stdout closed while waiting for ndjson traffic")
        reservation.release()
        self._check_fatal()
        return message

    def terminate(self) -> None:
        if self._process.poll() is None:
            self._process.kill()
        self._reader.join(timeout=5)
        self._stderr_reader.join(timeout=5)

    def stderr_text(self) -> str:
        with self._stderr_lock:
            tail = "".join(self._stderr_lines)
            gate = self._gate_rejection if self._gate_rejection not in self._stderr_lines else ""
            omitted = f"[stderr omitted lines: {self._stderr_omitted}]\n" if self._stderr_omitted else ""
            return gate + omitted + tail

    def _check_fatal(self) -> None:
        if self._fatal is not None:
            raise LiveSessionError(self._fatal, stderr=self.stderr_text())

    def _read_stdout(self) -> None:
        assert self._process.stdout is not None
        parts: list[str] = []
        size = 0
        try:
            while True:
                chunk = self._process.stdout.readline(4096)
                if not chunk:
                    if parts:
                        self._fatal = self._fatal or "ACP subprocess incomplete frame"
                    return
                if self._fatal is not None:
                    continue  # Bounded drain; the caller retains child teardown authority.
                size += len(chunk.encode("utf-8"))
                if size > self._limits.frame_bytes:
                    parts.clear()
                    self._fatal = "ACP subprocess frame too large"
                    continue
                parts.append(chunk)
                if not chunk.endswith("\n"):
                    continue
                line = "".join(parts)
                parts.clear()
                if not line.strip():
                    size = 0
                    continue
                message = json.loads(line)
                if not isinstance(message, dict):
                    self._fatal = "ACP subprocess invalid frame"
                    continue
                reservation = self._admission.try_reserve(1, size, AdmissionClass.ORDINARY)
                size = 0
                if reservation is None:
                    self._fatal = "ACP subprocess inbound capacity exceeded"
                    continue
                try:
                    self._transcript.record_inbound(message)
                    self._inbound.put_nowait((message, reservation))
                except BaseException:
                    reservation.release()
                    raise
        except Exception:
            self._fatal = self._fatal or "ACP subprocess reader failed"
        finally:
            self._admission.close()
            self._stdout_done.set()

    def _read_stderr(self) -> None:
        assert self._process.stderr is not None
        parts: list[str] = []
        size = 0
        discarded = False
        while True:
            try:
                chunk = self._process.stderr.readline(4096)
                chunk_size = len(chunk.encode("utf-8"))
            except Exception:
                self._fatal = self._fatal or "ACP subprocess stderr reader failed"
                self._retain_stderr(None)
                return
            size = min(self._limits.stderr_line_bytes + 1, size + chunk_size)
            if size > self._limits.stderr_line_bytes:
                parts.clear()
                discarded = True
            if not discarded:
                parts.append(chunk)
            if chunk and not chunk.endswith("\n"):
                continue
            if size:
                self._retain_stderr(None if discarded else "".join(parts))
            if not chunk:
                return
            parts.clear()
            size = 0
            discarded = False

    def _retain_stderr(self, line: str | None) -> None:
        sanitized: str | None = None
        if line is not None:
            try:
                value = sanitize_for_persistence(line).value
                if isinstance(value, str) and len(value.encode("utf-8")) <= min(self._limits.stderr_line_bytes, self._limits.stderr_bytes):
                    sanitized = value
            except Exception:
                sanitized = None
        with self._stderr_lock:
            if not sanitized:
                self._stderr_omitted = min(2**63 - 1, self._stderr_omitted + 1)
                return
            if not self._gate_rejection and sanitized.startswith(_GATE_REJECTION_PREFIX):
                self._gate_rejection = sanitized
            size = len(sanitized.encode("utf-8"))
            while self._stderr_bytes + size > self._limits.stderr_bytes:
                self._stderr_bytes -= len(self._stderr_lines.popleft().encode("utf-8"))
                self._stderr_omitted = min(2**63 - 1, self._stderr_omitted + 1)
            self._stderr_lines.append(sanitized)
            self._stderr_bytes += size

    def _fail_subprocess_exited(self, error_message: str) -> Never:
        # wait_for()'s and read_next()'s poll() checks (and send()'s
        # broken-pipe handler) can reach this the instant the child exits,
        # before the background _read_stderr thread has drained the child's
        # already-printed gate-rejection line. Wait for the process to be
        # reapable and join the reader thread FIRST -- both return
        # near-instantly once the child has actually exited -- so
        # stderr_text() below reflects the complete output instead of
        # whatever had been read by pure luck at the moment of the check.
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        self._stderr_reader.join(timeout=5)
        code = self._process.poll()
        code_text = "closing" if code is None else str(code)
        stderr_text = self.stderr_text()
        # Plan 9.96, Task 5 Batch 3 (operator_verify.py threading): if the
        # child exited because the launch gate (__main__.py's
        # _authorize_or_exit) rejected it before ever starting the ACP
        # protocol, surface that value-free remediation CLEANLY rather than
        # burying it behind a misleading "timed out waiting for JSON-RPC
        # response" wrapper — the child never even reached a point where a
        # JSON-RPC response could have been expected. This is detected by a
        # stable prefix ("optimus-agent: ") the gate's own remediation
        # messages always use (see __main__.py's _no_approval_remediation /
        # _snapshot_mismatch_remediation and the generic LaunchGateError
        # print), not by string-matching a specific error code, so any
        # current or future gate rejection message is surfaced cleanly.
        gate_rejection = _extract_gate_rejection_message(stderr_text)
        if gate_rejection is not None:
            raise LiveSessionError(gate_rejection, stderr=stderr_text)
        raise LiveSessionError(
            f"{error_message}\nACP subprocess exited early (code={code_text}).\nstderr:\n{stderr_text}",
            stderr=stderr_text,
        )

    def _fail_timeout(self, error_message: str) -> Never:
        raise LiveSessionError(f"{error_message}\nstderr:\n{self.stderr_text()}")
