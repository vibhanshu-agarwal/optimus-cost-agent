from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any

from optimus.acp.e2e_transcript import E2eAcpTranscriptWriter


class LiveSessionError(Exception):
    def __init__(self, message: str, *, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr


class NdjsonSubprocessSession:
    def __init__(self, *, process: subprocess.Popen[str], transcript: E2eAcpTranscriptWriter) -> None:
        self._process = process
        self._transcript = transcript
        self._inbound: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._stderr_lines: list[str] = []
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_reader = threading.Thread(target=self._read_stderr, daemon=True)
        self._reader.start()
        self._stderr_reader.start()

    def send(self, message: Mapping[str, object]) -> None:
        if self._process.stdin is None:
            raise LiveSessionError("subprocess stdin is not available")
        payload = dict(message)
        self._transcript.record_outbound(payload)
        self._process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        self._process.stdin.flush()

    def close_stdin(self) -> None:
        if self._process.stdin is not None:
            self._process.stdin.close()

    def wait_for(
        self,
        *,
        deadline: float,
        predicate: Callable[[dict[str, Any]], bool],
        error_message: str,
    ) -> dict[str, Any]:
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                self._fail_subprocess_exited(error_message)
            try:
                message = self._inbound.get(timeout=0.2)
            except queue.Empty:
                continue
            if message is None:
                self._fail_subprocess_exited(error_message)
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
        if self._process.poll() is not None:
            self._fail_subprocess_exited("ACP subprocess exited while waiting for ndjson traffic")
        try:
            message = self._inbound.get(timeout=max(0.0, min(0.2, deadline - time.monotonic())))
        except queue.Empty:
            return None
        if message is None:
            self._fail_subprocess_exited("ACP subprocess stdout closed while waiting for ndjson traffic")
        return message

    def terminate(self) -> None:
        if self._process.poll() is None:
            self._process.kill()
        self._reader.join(timeout=5)
        self._stderr_reader.join(timeout=5)

    def stderr_text(self) -> str:
        return "".join(self._stderr_lines)

    def _read_stdout(self) -> None:
        assert self._process.stdout is not None
        for line in self._process.stdout:
            stripped = line.strip()
            if not stripped:
                continue
            message = json.loads(stripped)
            self._transcript.record_inbound(message)
            self._inbound.put(message)
        self._inbound.put(None)

    def _read_stderr(self) -> None:
        assert self._process.stderr is not None
        for line in self._process.stderr:
            self._stderr_lines.append(line)

    def _fail_subprocess_exited(self, error_message: str) -> None:
        code = self._process.poll()
        code_text = "closing" if code is None else str(code)
        raise LiveSessionError(
            f"{error_message}\nACP subprocess exited early (code={code_text}).\nstderr:\n{self.stderr_text()}"
        )

    def _fail_timeout(self, error_message: str) -> None:
        raise LiveSessionError(f"{error_message}\nstderr:\n{self.stderr_text()}")
